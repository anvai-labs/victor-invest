# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""SEC Filing Text Extraction Tool for Management Commentary.

This tool extracts Management's Discussion and Analysis (MD&A) and other
relevant textual content from durable SEC filings (10-K, 10-Q, 8-K) to provide
point-in-time, source-attributed management commentary for synthesis.

Key Features:
- Extract MD&A section from 10-K/10-Q filings
- Extract recent developments from 8-K filings
- Extract management guidance and forward-looking statements
- Extract risk factors and business overview sections
- Verify immutable source bytes and expose exact evidence offsets
"""

from __future__ import annotations

import hashlib
import html
import io
import logging
import re
from array import array
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from victor_invest.sec_document_store import PostgresSecDocumentStore, StoredSecDocument
from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

SEC_TEXT_PARSER_VERSION = "sec-text-v2"


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    """Normalized text tied to an exclusive byte range in immutable evidence."""

    text: str
    source_start_byte: int
    source_end_byte: int
    truncated: bool

    @property
    def normalized_text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", errors="surrogateescape")).hexdigest()


@dataclass(frozen=True, slots=True)
class _MappedText:
    text: str
    starts: array
    ends: array


class SECFilingTextTool(BaseTool):
    """Tool for extracting textual content from SEC filings.

    Provides access to management commentary, MD&A, and other
    narrative sections from SEC filings for real-time insights.

    Supported actions:
    - get_mda: Extract Management's Discussion and Analysis
    - get_guidance: Extract management guidance and outlook
    - get_developments: Extract recent developments from 8-K filings
    - get_risk_factors: Extract risk factors from filings
    - get_business_overview: Extract business description and overview
    - get_management_discussion: Get combined management commentary sections

    Attributes:
        name: "sec_filing_text"
        description: Tool description for agent discovery
    """

    name = "sec_filing_text"
    description = """Extract textual content and management commentary from SEC filings.

Actions:
- get_mda: Extract Management's Discussion and Analysis (MD&A) section
- get_guidance: Extract management guidance, outlook, and forward-looking statements
- get_developments: Extract recent developments from 8-K filings
- get_risk_factors: Extract risk factors and cautionary statements
- get_business_overview: Extract business description and operations overview
- get_management_discussion: Get source-attributed 10-Q/10-K MD&A and 8-K developments

Parameters:
- symbol: Stock ticker symbol (required)
- action: One of the actions above (required)
- form_type: Filing form type for specific filing lookup (default: "10-K")
- period: Filing period ("latest" or specific quarter like "2024-Q3")
- num_filings: Number of recent filings to search for developments (default: 5)
- max_chars: Maximum characters to return per section (default: 15000)
- as_of: Optional timezone-aware point-in-time cutoff (default: now)
"""

    def __init__(self, config: Any | None = None):
        """Initialize SEC Filing Text Tool.

        Args:
            config: Optional investigator config object.
        """
        super().__init__(config)
        self._document_store: PostgresSecDocumentStore | Any | None = None

        # Section patterns for extraction
        self._guidance_patterns = [
            r"(?mi)^\s*(?:business\s+)?outlook\s*$",
            r"(?mi)^\s*(?:financial\s+)?guidance\s*$",
            r"future\s+prospects?",
        ]

        self._developments_patterns = [
            r"item\s*1\.?\s*[:\s]*entry\s+into\s+a\s+material\s+definitive\s+agreement",
            r"item\s*2\.02\s*[:\s]*results\s+of\s+operations\s+and\s+financial\s+condition",
            r"item\s*8\.?\s*[:\s]*other\s+events?",
            r"recent\s+developments?",
            r"material\s+events?",
        ]

    async def initialize(self) -> None:
        """Initialize SEC infrastructure components."""
        try:
            config: Any = getattr(self, "config", None)
            if config is None:
                from investigator.config import get_config

                config = get_config()
                self.config = config

            self._document_store = PostgresSecDocumentStore(config=config)
            self._initialized = True
            logger.info("SECFilingTextTool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SECFilingTextTool: {e}")
            raise

    def close(self) -> None:
        """Close pooled PostgreSQL connections when a direct-use tool is finished."""
        if self._document_store is not None and hasattr(self._document_store, "close"):
            self._document_store.close()
        self._document_store = None
        self._initialized = False

    async def execute(
        self,
        _exec_ctx: dict[str, Any] | None = None,
        symbol: str = "",
        action: str = "get_mda",
        form_type: str = "10-K",
        period: str = "latest",
        num_filings: int = 5,
        max_chars: int = 15000,
        as_of: str | datetime | None = None,
        **kwargs,
    ) -> ToolResult:
        """Execute SEC filing text extraction.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
            action: Operation to perform
            form_type: SEC form type for specific filing lookup
            period: Filing period ("latest" or specific period)
            num_filings: Number of recent filings to search
            max_chars: Maximum characters to return per section
            as_of: Optional timezone-aware point-in-time cutoff
            **kwargs: Additional action-specific parameters

        Returns:
            ToolResult with extracted text content
        """
        try:
            await self.ensure_initialized()

            symbol = symbol.upper().strip()
            if not symbol:
                return ToolResult.create_failure("Symbol is required")

            if not 1_000 <= max_chars <= 50_000:
                return ToolResult.create_failure("max_chars must be between 1000 and 50000")
            if not 1 <= num_filings <= 20:
                return ToolResult.create_failure("num_filings must be between 1 and 20")
            query_as_of = self._parse_as_of(as_of)

            action = action.lower().strip()

            if action == "get_mda":
                return await self._get_mda(symbol, form_type, period, max_chars, query_as_of)
            elif action == "get_guidance":
                return await self._get_guidance(symbol, form_type, period, max_chars, query_as_of)
            elif action == "get_developments":
                return await self._get_developments(symbol, num_filings, max_chars, query_as_of)
            elif action == "get_risk_factors":
                return await self._get_risk_factors(symbol, form_type, period, max_chars, query_as_of)
            elif action == "get_business_overview":
                return await self._get_business_overview(symbol, form_type, period, max_chars, query_as_of)
            elif action == "get_management_discussion":
                return await self._get_management_discussion(symbol, max_chars, query_as_of)
            else:
                return ToolResult.create_failure(
                    f"Unknown action: {action}. Valid actions: "
                    "get_mda, get_guidance, get_developments, get_risk_factors, get_business_overview, get_management_discussion"
                )

        except Exception as e:
            logger.error(f"SECFilingTextTool execute error for {symbol}: {e}")
            return ToolResult.create_failure(
                f"SEC filing text extraction failed: {e!s}",
                metadata={"symbol": symbol, "action": action},
            )

    @staticmethod
    def _parse_as_of(value: str | datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        return parsed.astimezone(UTC)

    def _normalize_text(self, text: str) -> str:
        """Normalize filing text while preserving structural line boundaries."""
        return self._normalize_with_offsets(text).text

    @staticmethod
    def _normalize_with_offsets(content: bytes | str, base_byte_offset: int = 0) -> _MappedText:
        """Normalize SEC HTML while retaining the source span for every character."""
        raw = content if isinstance(content, bytes) else content.encode("utf-8", errors="surrogateescape")
        decoded = raw.decode("utf-8", errors="surrogateescape")
        char_bytes = array("Q", [base_byte_offset])
        for character in decoded:
            char_bytes.append(char_bytes[-1] + len(character.encode("utf-8", errors="surrogateescape")))

        structural = re.compile(
            r"^<\s*(?:br\s*/?\s*>|/\s*(?:p|div|tr|td|th|li|h[1-6]|section|article|table)\s*>)",
            re.IGNORECASE,
        )
        output = io.StringIO()
        starts = array("Q")
        ends = array("Q")
        output_length = 0
        line_has_content = False
        between_lines = False
        line_break_start = base_byte_offset
        line_break_end = base_byte_offset
        whitespace_start: int | None = None
        whitespace_end = base_byte_offset

        def emit(character: str, start: int, end: int) -> None:
            nonlocal output_length
            output.write(character)
            output_length += 1
            starts.append(start)
            ends.append(end)

        def consume_newline(start: int, end: int) -> None:
            nonlocal between_lines, line_break_start, line_break_end, line_has_content, whitespace_start
            whitespace_start = None
            if line_has_content:
                between_lines = True
                line_break_start = start
                line_break_end = end
                line_has_content = False
            elif between_lines:
                line_break_end = end

        def consume_whitespace(start: int, end: int) -> None:
            nonlocal whitespace_start, whitespace_end
            if whitespace_start is None:
                whitespace_start = start
            whitespace_end = end

        def consume_character(character: str, start: int, end: int) -> None:
            nonlocal between_lines, line_has_content, whitespace_start
            if character in "\r\n":
                consume_newline(start, end)
                return
            if character.isspace():
                consume_whitespace(start, end)
                return
            if between_lines and output_length:
                emit("\n", line_break_start, max(line_break_end, start))
                between_lines = False
            elif whitespace_start is not None and line_has_content:
                emit(" ", whitespace_start, whitespace_end)
            whitespace_start = None
            emit(character, start, end)
            line_has_content = True

        index = 0
        while index < len(decoded):
            if decoded[index] == "<":
                tag_end = decoded.find(">", index + 1)
                if tag_end >= 0:
                    if structural.match(decoded[index : tag_end + 1]):
                        consume_newline(char_bytes[index], char_bytes[tag_end + 1])
                    else:
                        consume_whitespace(char_bytes[index], char_bytes[tag_end + 1])
                    index = tag_end + 1
                    continue
            if decoded[index] == "{":
                artifact_end = decoded.find("}", index + 1)
                newline = decoded.find("\n", index + 1)
                if artifact_end >= 0 and (newline < 0 or artifact_end < newline):
                    consume_whitespace(char_bytes[index], char_bytes[artifact_end + 1])
                    index = artifact_end + 1
                    continue
            if decoded[index] == "&":
                entity_end = decoded.find(";", index + 1, min(len(decoded), index + 33))
                if entity_end >= 0:
                    entity = decoded[index : entity_end + 1]
                    unescaped = html.unescape(entity)
                    if unescaped != entity:
                        for character in unescaped:
                            consume_character(character, char_bytes[index], char_bytes[entity_end + 1])
                        index = entity_end + 1
                        continue

            consume_character(decoded[index], char_bytes[index], char_bytes[index + 1])
            index += 1
        return _MappedText(text=output.getvalue(), starts=starts, ends=ends)

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Bound text without allowing the truncation marker to exceed the limit."""
        if len(text) <= max_chars:
            return text
        marker = "... [truncated]"
        if max_chars <= len(marker):
            return text[:max_chars]
        return text[: max_chars - len(marker)].rstrip() + marker

    @staticmethod
    def _mda_patterns_for_form(form_type: str) -> list[str]:
        form = (form_type or "").upper()
        if form.startswith("10-Q"):
            return [
                r"(?mi)^\s*item\s*2\.?\s+management[’']s\s+discussion\s+and\s+analysis",
                r"(?mi)^\s*management[’']s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations",
            ]
        if form.startswith("10-K"):
            return [
                r"(?mi)^\s*item\s*7\.?\s+management[’']s\s+discussion\s+and\s+analysis",
                r"(?mi)^\s*management[’']s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations",
            ]
        return []

    @staticmethod
    def _risk_patterns_for_form(form_type: str) -> list[str]:
        form = (form_type or "").upper()
        if form.startswith(("10-K", "10-Q")):
            return [r"(?mi)^\s*item\s*1a\.?\s+risk\s+factors"]
        return []

    @staticmethod
    def _business_patterns_for_form(form_type: str) -> list[str]:
        if (form_type or "").upper().startswith("10-K"):
            return [r"(?mi)^\s*item\s*1\.?\s+business(?:\s+overview)?"]
        return []

    def _extract_exhibit_99_1(self, text: str, max_chars: int) -> str | None:
        """Extract an earnings-release exhibit from complete submission text."""
        section = self._extract_exhibit_99_1_with_provenance(text, max_chars)
        return section.text if section else None

    def _extract_exhibit_99_1_with_provenance(self, content: bytes | str, max_chars: int) -> ExtractedSection | None:
        """Select one substantive Exhibit 99.1 and retain its exact byte span."""
        raw = content if isinstance(content, bytes) else content.encode("utf-8", errors="surrogateescape")
        decoded = raw.decode("utf-8", errors="surrogateescape")
        char_bytes = array("Q", [0])
        for character in decoded:
            char_bytes.append(char_bytes[-1] + len(character.encode("utf-8", errors="surrogateescape")))

        exhibits: list[_MappedText] = []
        for document_match in re.finditer(r"<DOCUMENT>(.*?)</DOCUMENT>", decoded, re.IGNORECASE | re.DOTALL):
            document = document_match.group(1)
            if not re.search(r"<TYPE>\s*EX-99(?:\.1)?(?:\s|<|$)", document, re.IGNORECASE):
                continue
            text_match = re.search(r"<TEXT>(.*?)</TEXT>", document, re.IGNORECASE | re.DOTALL)
            if text_match:
                start_char = document_match.start(1) + text_match.start(1)
                end_char = document_match.start(1) + text_match.end(1)
            else:
                start_char = document_match.start(1)
                end_char = document_match.end(1)
            start_byte = char_bytes[start_char]
            end_byte = char_bytes[end_char]
            normalized = self._normalize_with_offsets(raw[start_byte:end_byte], base_byte_offset=start_byte)
            if len(normalized.text) >= 80:
                exhibits.append(normalized)

        if not exhibits:
            return None
        best = max(exhibits, key=lambda exhibit: len(exhibit.text))
        return self._mapped_section(best, 0, len(best.text), max_chars)

    def _extract_section_by_patterns(self, text: str, patterns: list[str], max_chars: int) -> str | None:
        """Extract a section from filing text using regex patterns.

        Args:
            text: Full filing text
            patterns: List of regex patterns to identify section start
            max_chars: Maximum characters to return

        Returns:
            Extracted section text or None
        """
        section = self._extract_section_with_provenance(text, patterns, max_chars)
        return section.text if section else None

    def _extract_section_with_provenance(
        self,
        content: bytes | str,
        patterns: list[str],
        max_chars: int,
    ) -> ExtractedSection | None:
        """Extract one contiguous section and retain exclusive source-byte offsets."""
        normalized = self._normalize_with_offsets(content)
        item_heading = re.compile(
            r"(?mi)^\s*(?:part\s+(?:i|ii)\s+)?item\s+\d+[a-z]?(?:\.\d+)?\s*[.：:\-]?",
        )
        candidates: list[tuple[int, int, int]] = []

        for pattern in patterns:
            for match in re.finditer(pattern, normalized.text, re.IGNORECASE | re.MULTILINE):
                next_section = item_heading.search(normalized.text, match.end())
                end_pos = next_section.start() if next_section else len(normalized.text)
                start_pos, end_pos = self._trim_mapped_range(normalized.text, match.start(), end_pos)
                section_text = normalized.text[start_pos:end_pos]
                if len(section_text) < 80:
                    continue
                # A filing table of contents commonly repeats the same heading.
                # Prefer the candidate with substantive body content rather than
                # accepting the first plausible match.
                candidates.append((len(section_text), start_pos, end_pos))

        if not candidates:
            return None

        _, start_pos, end_pos = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        return self._mapped_section(normalized, start_pos, end_pos, max_chars)

    @staticmethod
    def _trim_mapped_range(text: str, start: int, end: int) -> tuple[int, int]:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return start, end

    @classmethod
    def _mapped_section(cls, mapped: _MappedText, start: int, end: int, max_chars: int) -> ExtractedSection:
        start, end = cls._trim_mapped_range(mapped.text, start, end)
        original = mapped.text[start:end]
        result = cls._truncate_text(original, max_chars)
        truncated = result != original
        retained_chars = len(result)
        if truncated and result.endswith("... [truncated]"):
            retained_chars -= len("... [truncated]")
        retained_chars = max(1, retained_chars)
        mapped_end = min(end, start + retained_chars)
        return ExtractedSection(
            text=result,
            source_start_byte=mapped.starts[start],
            source_end_byte=mapped.ends[mapped_end - 1],
            truncated=truncated,
        )

    def _extract_guidance_sentences(self, text: str, max_sentences: int = 50) -> list[str]:
        """Extract sentences containing guidance/forward-looking statements.

        Args:
            text: Text to search
            max_sentences: Maximum sentences to return

        Returns:
            List of guidance sentences
        """
        guidance_cues = [
            r"we\s+(?:expect|anticipate|project|forecast|believe|intend|plan)",
            r"(?:revenue|earnings|sales|growth|margin|cash flow)\s+(?:is\s+)?expected",
            r"outlook.*?revenue",
            r"guidance.*?revenue",
            r"forward.*?looking",
            r"future.*?results?",
            r"we\s+continue\s+to\s+(?:expect|see)",
            r"we\s+are\s+(?:optimistic|confident|cautious)",
        ]

        sentences = re.split(r"[.!?]+\s+", text)
        guidance_sentences: list[str] = []

        for sentence in sentences:
            if len(guidance_sentences) >= max_sentences:
                break
            for cue in guidance_cues:
                if re.search(cue, sentence, re.IGNORECASE):
                    guidance_sentences.append(sentence.strip())
                    break

        return guidance_sentences

    async def _get_filing_data(
        self,
        symbol: str,
        form_type: str,
        period: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Get verified filing text and provenance from the shared store.

        Args:
            symbol: Stock ticker
            form_type: Form type
            period: Filing period

        Returns:
            Filing metadata with text, or None
        """
        if self._document_store is None:
            return None

        try:
            document = await self._document_store.get_latest_document(
                symbol,
                form_type,
                period,
                as_of or datetime.now(UTC),
            )
            if document is None:
                return None
            filing_data = document.provenance()
            filing_data["text"] = document.verified_text()
            filing_data["document"] = document
            return filing_data
        except Exception as e:
            logger.error(f"Error reading verified filing text: {e}")
            return None

    async def _get_filing_text(
        self, symbol: str, form_type: str, period: str, as_of: datetime | None = None
    ) -> str | None:
        """Compatibility helper returning only filing text."""
        filing_data = await self._get_filing_data(symbol, form_type, period, as_of)
        text = filing_data.get("text") if filing_data else None
        return text if isinstance(text, str) else None

    async def _get_mda(
        self,
        symbol: str,
        form_type: str,
        period: str,
        max_chars: int,
        as_of: datetime | None = None,
    ) -> ToolResult:
        """Extract Management's Discussion and Analysis section."""
        filing_data = await self._get_filing_data(symbol, form_type, period, as_of)
        if not filing_data:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")
        document: StoredSecDocument = filing_data["document"]

        section = self._extract_section_with_provenance(
            document.content_bytes,
            self._mda_patterns_for_form(form_type),
            max_chars,
        )

        if not section:
            return ToolResult.create_failure(f"Could not extract MD&A section from {form_type} filing for {symbol}")

        source = self._source_with_evidence(document, "mda", section)
        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": document.form_type,
                "section": "mda",
                "text": section.text,
                "char_count": len(section.text),
                **source,
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "postgres_sec_filing_document",
                "form_type": document.form_type,
                "period": period,
                "parser_version": SEC_TEXT_PARSER_VERSION,
            },
        )

    async def _get_guidance(
        self,
        symbol: str,
        form_type: str,
        period: str,
        max_chars: int,
        as_of: datetime | None = None,
    ) -> ToolResult:
        """Extract management guidance and outlook."""
        filing_data = await self._get_filing_data(symbol, form_type, period, as_of)
        if not filing_data:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")
        document: StoredSecDocument = filing_data["document"]
        text = filing_data["text"]

        # First try to find a dedicated guidance section
        guidance_section = self._extract_section_with_provenance(
            document.content_bytes, self._guidance_patterns, max_chars
        )

        if guidance_section:
            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": document.form_type,
                    "section": "guidance",
                    "text": guidance_section.text,
                    "char_count": len(guidance_section.text),
                    **self._source_with_evidence(document, "guidance", guidance_section),
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
                metadata={
                    "source": "postgres_sec_filing_document",
                    "form_type": document.form_type,
                    "period": period,
                    "parser_version": SEC_TEXT_PARSER_VERSION,
                },
            )

        # Fallback: extract guidance sentences from the full text
        guidance_sentences = self._extract_guidance_sentences(text, max_sentences=100)
        if guidance_sentences:
            complete_guidance = " ".join(guidance_sentences)
            guidance_text = self._truncate_text(complete_guidance, max_chars)
            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": document.form_type,
                    "section": "guidance",
                    "text": guidance_text,
                    "char_count": len(guidance_text),
                    "extraction_method": "sentence_level",
                    **document.provenance(),
                    "parser_version": SEC_TEXT_PARSER_VERSION,
                    "normalized_text_sha256": hashlib.sha256(
                        guidance_text.encode("utf-8", errors="surrogateescape")
                    ).hexdigest(),
                    "source_start_byte": 0,
                    "source_end_byte": document.byte_length,
                    "truncated": len(complete_guidance) > max_chars,
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
                metadata={
                    "source": "postgres_sec_filing_document",
                    "form_type": document.form_type,
                    "period": period,
                    "parser_version": SEC_TEXT_PARSER_VERSION,
                },
            )

        return ToolResult.create_failure(f"Could not extract guidance from {form_type} filing for {symbol}")

    async def _get_developments(
        self,
        symbol: str,
        num_filings: int,
        max_chars: int,
        as_of: datetime | None = None,
    ) -> ToolResult:
        """Extract recent developments from 8-K filings."""
        if self._document_store is None:
            return ToolResult.create_failure("SEC document store not initialized")

        try:
            documents = await self._document_store.list_recent_documents(
                symbol,
                "8-K",
                as_of or datetime.now(UTC),
                limit=num_filings,
            )

            if not documents:
                return ToolResult.create_failure(
                    f"No recent 8-K filings found for {symbol}",
                    metadata={"symbol": symbol, "form_type": "8-K"},
                )

            developments: list[str] = []
            sources: list[dict[str, Any]] = []
            total_chars = 0

            for document in documents:
                if total_chars >= max_chars:
                    break

                filing_date = document.filed_at.isoformat()
                heading = f"## Filing Date: {filing_date}\n"
                separator_size = 1 if developments else 0
                content_budget = max_chars - total_chars - len(heading) - separator_size
                if content_budget < 80:
                    break

                try:
                    document.verified_text()
                    dev_section = self._extract_section_with_provenance(
                        document.content_bytes,
                        self._developments_patterns,
                        content_budget,
                    )
                    remaining = content_budget - len(dev_section.text if dev_section else "")
                    exhibit_section = (
                        self._extract_exhibit_99_1_with_provenance(document.content_bytes, remaining)
                        if remaining >= 80
                        else None
                    )

                    filing_parts = [section.text for section in (dev_section, exhibit_section) if section]
                    if filing_parts:
                        filing_text = self._truncate_text("\n\n".join(filing_parts), content_budget)
                        entry = f"{heading}{filing_text}"
                        developments.append(entry)
                        total_chars += len(entry) + separator_size
                        source = document.provenance()
                        evidence = [
                            self._evidence("item_2_02", dev_section) if dev_section else None,
                            self._evidence("exhibit_99_1", exhibit_section) if exhibit_section else None,
                        ]
                        source.update(
                            {
                                "parser_version": SEC_TEXT_PARSER_VERSION,
                                "sections": [item["section"] for item in evidence if item],
                                "evidence": [item for item in evidence if item],
                            }
                        )
                        sources.append(source)

                except Exception as e:
                    logger.warning(f"Error processing 8-K filing {document.accession_no}: {e}")
                    continue

            if not developments:
                return ToolResult.create_failure(f"Could not extract developments from 8-K filings for {symbol}")

            combined_text = self._truncate_text("\n".join(developments), max_chars)

            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": "8-K",
                    "section": "developments",
                    "text": combined_text,
                    "char_count": len(combined_text),
                    "filing_count": len(developments),
                    "sources": sources,
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
                metadata={
                    "source": "postgres_sec_filing_document",
                    "num_filings": num_filings,
                    "parser_version": SEC_TEXT_PARSER_VERSION,
                },
            )

        except Exception as e:
            logger.error(f"Error getting developments for {symbol}: {e}")
            return ToolResult.create_failure(f"Failed to get developments: {e!s}")

    async def _get_risk_factors(
        self,
        symbol: str,
        form_type: str,
        period: str,
        max_chars: int,
        as_of: datetime | None = None,
    ) -> ToolResult:
        """Extract risk factors section."""
        filing_data = await self._get_filing_data(symbol, form_type, period, as_of)
        if not filing_data:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")
        document: StoredSecDocument = filing_data["document"]

        section = self._extract_section_with_provenance(
            document.content_bytes,
            self._risk_patterns_for_form(form_type),
            max_chars,
        )

        if not section:
            return ToolResult.create_failure(f"Could not extract risk factors from {form_type} filing for {symbol}")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": document.form_type,
                "section": "risk_factors",
                "text": section.text,
                "char_count": len(section.text),
                **self._source_with_evidence(document, "risk_factors", section),
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "postgres_sec_filing_document",
                "form_type": document.form_type,
                "period": period,
                "parser_version": SEC_TEXT_PARSER_VERSION,
            },
        )

    async def _get_business_overview(
        self,
        symbol: str,
        form_type: str,
        period: str,
        max_chars: int,
        as_of: datetime | None = None,
    ) -> ToolResult:
        """Extract business overview section."""
        filing_data = await self._get_filing_data(symbol, form_type, period, as_of)
        if not filing_data:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")
        document: StoredSecDocument = filing_data["document"]

        section = self._extract_section_with_provenance(
            document.content_bytes,
            self._business_patterns_for_form(form_type),
            max_chars,
        )

        if not section:
            return ToolResult.create_failure(
                f"Could not extract business overview from {form_type} filing for {symbol}"
            )

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": document.form_type,
                "section": "business_overview",
                "text": section.text,
                "char_count": len(section.text),
                **self._source_with_evidence(document, "business_overview", section),
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "postgres_sec_filing_document",
                "form_type": document.form_type,
                "period": period,
                "parser_version": SEC_TEXT_PARSER_VERSION,
            },
        )

    async def _get_management_discussion(
        self, symbol: str, max_chars: int, as_of: datetime | None = None
    ) -> ToolResult:
        """Get comprehensive management commentary from multiple sources.

        Prioritizes quarterly MD&A, then annual MD&A and recent 8-K developments.
        """
        sections = {}
        sources = []
        char_budget = max_chars

        # Current quarterly commentary is the highest-value input.
        try:
            mda_result = await self._get_mda(symbol, "10-Q", "latest", max(1000, char_budget // 2), as_of)
            if mda_result.success:
                sections["mda_10q"] = mda_result.output.get("text", "")
                char_budget -= len(sections["mda_10q"])
                sources.append(self._management_source("mda_10q", mda_result.output))
        except Exception as e:
            logger.warning(f"Could not get 10-Q MD&A for {symbol}: {e}")

        if char_budget > 2000:
            try:
                mda_result = await self._get_mda(symbol, "10-K", "latest", min(char_budget, 5000), as_of)
                if mda_result.success:
                    sections["mda_10k"] = mda_result.output.get("text", "")
                    char_budget -= len(sections["mda_10k"])
                    sources.append(self._management_source("mda_10k", mda_result.output))
            except Exception as e:
                logger.warning(f"Could not get 10-K MD&A for {symbol}: {e}")

        # Get recent developments from 8-K
        if char_budget > 2000:
            try:
                dev_result = await self._get_developments(symbol, 3, min(char_budget, 5000), as_of)
                if dev_result.success:
                    sections["developments_8k"] = dev_result.output.get("text", "")
                    sources.extend(dev_result.output.get("sources", []))
            except Exception as e:
                logger.warning(f"Could not get 8-K developments for {symbol}: {e}")

        if not sections:
            return ToolResult.create_failure(f"Could not extract any management commentary from filings for {symbol}")

        # Combine sections with headers
        combined_parts = []
        if "mda_10k" in sections:
            combined_parts.append(f"# Management's Discussion and Analysis (10-K)\n{sections['mda_10k']}")
        if "mda_10q" in sections:
            combined_parts.insert(0, f"# Management's Discussion and Analysis (10-Q)\n{sections['mda_10q']}")
        if "developments_8k" in sections:
            combined_parts.append(f"# Recent Developments (8-K)\n{sections['developments_8k']}")

        combined_text = self._truncate_text("\n\n".join(combined_parts), max_chars)

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "section": "management_discussion_comprehensive",
                "text": combined_text,
                "char_count": len(combined_text),
                "sections_included": list(sections.keys()),
                "sources": sources,
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "sec_edgar_comprehensive",
                "sections": list(sections.keys()),
            },
        )

    @staticmethod
    def _management_source(section: str, output: dict[str, Any]) -> dict[str, Any]:
        source_fields = (
            "accession_number",
            "content_sha256",
            "document_kind",
            "cik",
            "filing_date",
            "accepted_at",
            "available_at",
            "period_end",
            "form_url",
            "byte_length",
            "retrieved_at",
            "parser_version",
            "normalized_text_sha256",
            "source_start_byte",
            "source_end_byte",
            "truncated",
        )
        return {"section": section, **{field: output.get(field) for field in source_fields}}

    @staticmethod
    def _evidence(section_name: str, section: ExtractedSection) -> dict[str, Any]:
        return {
            "section": section_name,
            "source_start_byte": section.source_start_byte,
            "source_end_byte": section.source_end_byte,
            "truncated": section.truncated,
            "normalized_text_sha256": section.normalized_text_sha256,
        }

    @classmethod
    def _source_with_evidence(
        cls,
        document: StoredSecDocument,
        section_name: str,
        section: ExtractedSection,
    ) -> dict[str, Any]:
        return {
            **document.provenance(),
            "parser_version": SEC_TEXT_PARSER_VERSION,
            **cls._evidence(section_name, section),
        }

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for SEC Filing Text Tool parameters."""
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, MSFT)",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "get_mda",
                        "get_guidance",
                        "get_developments",
                        "get_risk_factors",
                        "get_business_overview",
                        "get_management_discussion",
                    ],
                    "description": "Action to perform",
                    "default": "get_mda",
                },
                "form_type": {
                    "type": "string",
                    "enum": ["10-K", "10-Q", "8-K"],
                    "description": "SEC form type",
                    "default": "10-K",
                },
                "period": {
                    "type": "string",
                    "description": "Filing period (e.g., 'latest', '2024-Q3')",
                    "default": "latest",
                },
                "num_filings": {
                    "type": "integer",
                    "description": "Number of recent filings to search for developments",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return per section",
                    "default": 15000,
                    "minimum": 1000,
                    "maximum": 50000,
                },
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Point-in-time cutoff; must include a timezone (default: now)",
                },
            },
            "required": ["symbol"],
        }
