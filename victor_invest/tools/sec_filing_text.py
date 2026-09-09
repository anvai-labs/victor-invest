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
relevant textual content from SEC filings (10-K, 10-Q, 8-K) to provide
current, source-attributed management commentary for LLM synthesis.

Key Features:
- Extract MD&A section from 10-K/10-Q filings
- Extract recent developments from 8-K filings
- Extract management guidance and forward-looking statements
- Extract risk factors and business overview sections
"""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime
from typing import Any

from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


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
"""

    def __init__(self, config: Any | None = None):
        """Initialize SEC Filing Text Tool.

        Args:
            config: Optional investigator config object.
        """
        super().__init__(config)
        self._sec_client: Any | None = None

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
            from investigator.infrastructure.sec.sec_api import SECApiClient

            config: Any = getattr(self, "config", None)
            if config is None:
                from investigator.config import get_config

                config = get_config()
                self.config = config

            self._sec_client = SECApiClient(config=config)
            self._initialized = True
            logger.info("SECFilingTextTool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SECFilingTextTool: {e}")
            raise

    def close(self) -> None:
        """Close the underlying SEC sessions when a direct-use tool is finished."""
        if self._sec_client is not None and hasattr(self._sec_client, "close"):
            self._sec_client.close()
        self._sec_client = None
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

            action = action.lower().strip()

            if action == "get_mda":
                return await self._get_mda(symbol, form_type, period, max_chars)
            elif action == "get_guidance":
                return await self._get_guidance(symbol, form_type, period, max_chars)
            elif action == "get_developments":
                return await self._get_developments(symbol, num_filings, max_chars)
            elif action == "get_risk_factors":
                return await self._get_risk_factors(symbol, form_type, period, max_chars)
            elif action == "get_business_overview":
                return await self._get_business_overview(symbol, form_type, period, max_chars)
            elif action == "get_management_discussion":
                return await self._get_management_discussion(symbol, max_chars)
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

    def _normalize_text(self, text: str) -> str:
        """Normalize filing text while preserving structural line boundaries."""
        decoded = html.unescape(text or "")
        structured = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", decoded)
        structured = re.sub(
            r"(?i)</\s*(?:p|div|tr|td|th|li|h[1-6]|section|article|table)\s*>",
            "\n",
            structured,
        )
        no_tags = re.sub(r"<[^>]+>", " ", structured)
        no_xbrl_artifacts = re.sub(r"\{[^}\n]+\}", " ", no_tags)
        lines = [re.sub(r"[\t \f\v]+", " ", line).strip() for line in no_xbrl_artifacts.splitlines()]
        return "\n".join(line for line in lines if line).strip()

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
        exhibits: list[str] = []
        for document in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.IGNORECASE | re.DOTALL):
            if not re.search(r"<TYPE>\s*EX-99(?:\.1)?(?:\s|<|$)", document, re.IGNORECASE):
                continue
            text_match = re.search(r"<TEXT>(.*?)</TEXT>", document, re.IGNORECASE | re.DOTALL)
            normalized = self._normalize_text(text_match.group(1) if text_match else document)
            if len(normalized) >= 80:
                exhibits.append(normalized)

        if not exhibits:
            return None
        combined = "\n\n".join(exhibits)
        return self._truncate_text(combined, max_chars)

    def _extract_section_by_patterns(self, text: str, patterns: list[str], max_chars: int) -> str | None:
        """Extract a section from filing text using regex patterns.

        Args:
            text: Full filing text
            patterns: List of regex patterns to identify section start
            max_chars: Maximum characters to return

        Returns:
            Extracted section text or None
        """
        normalized = self._normalize_text(text)
        item_heading = re.compile(
            r"(?mi)^\s*(?:part\s+(?:i|ii)\s+)?item\s+\d+[a-z]?(?:\.\d+)?\s*[.：:\-]?",
        )
        candidates: list[tuple[int, int, str]] = []

        for pattern in patterns:
            for match in re.finditer(pattern, normalized, re.IGNORECASE | re.MULTILINE):
                next_section = item_heading.search(normalized, match.end())
                end_pos = next_section.start() if next_section else len(normalized)
                section_text = normalized[match.start() : end_pos].strip()
                if len(section_text) < 80:
                    continue
                # A filing table of contents commonly repeats the same heading.
                # Prefer the candidate with substantive body content rather than
                # accepting the first plausible match.
                candidates.append((len(section_text), match.start(), section_text))

        if not candidates:
            return None

        _, _, section_text = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        return self._truncate_text(section_text, max_chars)

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

    async def _get_filing_data(self, symbol: str, form_type: str, period: str) -> dict[str, Any] | None:
        """Get filing text and provenance from SEC.

        Args:
            symbol: Stock ticker
            form_type: Form type
            period: Filing period

        Returns:
            Filing metadata with text, or None
        """
        if self._sec_client is None:
            return None

        try:
            filing_data = await self._sec_client.get_filing_by_symbol(symbol=symbol, form_type=form_type, period=period)
            return filing_data if filing_data.get("text") else None
        except Exception as e:
            logger.error(f"Error fetching filing text: {e}")
            return None

    async def _get_filing_text(self, symbol: str, form_type: str, period: str) -> str | None:
        """Compatibility helper returning only filing text."""
        filing_data = await self._get_filing_data(symbol, form_type, period)
        text = filing_data.get("text") if filing_data else None
        return text if isinstance(text, str) else None

    async def _get_mda(self, symbol: str, form_type: str, period: str, max_chars: int) -> ToolResult:
        """Extract Management's Discussion and Analysis section."""
        filing_data = await self._get_filing_data(symbol, form_type, period)
        if not filing_data:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")
        text = filing_data["text"]

        mda_text = self._extract_section_by_patterns(text, self._mda_patterns_for_form(form_type), max_chars)

        if not mda_text:
            return ToolResult.create_failure(f"Could not extract MD&A section from {form_type} filing for {symbol}")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": form_type,
                "section": "mda",
                "text": mda_text,
                "char_count": len(mda_text),
                "accession_number": filing_data.get("accession_number"),
                "filing_date": filing_data.get("filing_date"),
                "period_end": filing_data.get("period_end"),
                "form_url": filing_data.get("form_url"),
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "sec_edgar_mda",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_guidance(self, symbol: str, form_type: str, period: str, max_chars: int) -> ToolResult:
        """Extract management guidance and outlook."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")

        # First try to find a dedicated guidance section
        guidance_section = self._extract_section_by_patterns(text, self._guidance_patterns, max_chars)

        if guidance_section:
            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": form_type,
                    "section": "guidance",
                    "text": guidance_section,
                    "char_count": len(guidance_section),
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
                metadata={
                    "source": "sec_edgar_guidance",
                    "form_type": form_type,
                    "period": period,
                },
            )

        # Fallback: extract guidance sentences from the full text
        guidance_sentences = self._extract_guidance_sentences(text, max_sentences=100)
        if guidance_sentences:
            guidance_text = " ".join(guidance_sentences)[:max_chars]
            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": form_type,
                    "section": "guidance",
                    "text": guidance_text,
                    "char_count": len(guidance_text),
                    "extraction_method": "sentence_level",
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
                metadata={
                    "source": "sec_edgar_guidance",
                    "form_type": form_type,
                    "period": period,
                },
            )

        return ToolResult.create_failure(f"Could not extract guidance from {form_type} filing for {symbol}")

    async def _get_developments(self, symbol: str, num_filings: int, max_chars: int) -> ToolResult:
        """Extract recent developments from 8-K filings."""
        if self._sec_client is None:
            return ToolResult.create_failure("SEC client not initialized")

        try:
            # Search for recent 8-K filings
            filings = await self._sec_client.search_filings(symbol=symbol, form_type="8-K", limit=num_filings)

            if not filings:
                return ToolResult.create_failure(
                    f"No recent 8-K filings found for {symbol}",
                    metadata={"symbol": symbol, "form_type": "8-K"},
                )

            developments: list[str] = []
            sources: list[dict[str, Any]] = []
            total_chars = 0

            for filing in filings[:num_filings]:
                if total_chars >= max_chars:
                    break

                filing_date = filing.get("filing_date", "")
                accession_number = filing.get("accession_number", "")
                heading = f"## Filing Date: {filing_date}\n"
                separator_size = 1 if developments else 0
                content_budget = max_chars - total_chars - len(heading) - separator_size
                if content_budget < 80:
                    break

                # Try to get the full filing text
                try:
                    cik = filing.get("cik", "")
                    if not cik:
                        continue

                    text = await self._sec_client.get_filing(accession_number, cik)
                    if not text:
                        continue

                    # Extract developments section
                    dev_text = self._extract_section_by_patterns(text, self._developments_patterns, content_budget)
                    remaining = content_budget - len(dev_text or "")
                    exhibit_text = self._extract_exhibit_99_1(text, remaining) if remaining >= 80 else None

                    filing_parts = [part for part in (dev_text, exhibit_text) if part]
                    if filing_parts:
                        filing_text = self._truncate_text("\n\n".join(filing_parts), content_budget)
                        entry = f"{heading}{filing_text}"
                        developments.append(entry)
                        total_chars += len(entry) + separator_size
                        sources.append(
                            {
                                "cik": cik,
                                "accession_number": accession_number,
                                "filing_date": filing_date,
                                "form_url": filing.get("form_url"),
                                "sections": [
                                    section
                                    for section, present in (
                                        ("item_2_02", bool(dev_text)),
                                        ("exhibit_99_1", bool(exhibit_text)),
                                    )
                                    if present
                                ],
                            }
                        )

                except Exception as e:
                    logger.warning(f"Error processing 8-K filing {accession_number}: {e}")
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
                metadata={"source": "sec_edgar_8k", "num_filings": num_filings},
            )

        except Exception as e:
            logger.error(f"Error getting developments for {symbol}: {e}")
            return ToolResult.create_failure(f"Failed to get developments: {e!s}")

    async def _get_risk_factors(self, symbol: str, form_type: str, period: str, max_chars: int) -> ToolResult:
        """Extract risk factors section."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")

        risk_text = self._extract_section_by_patterns(text, self._risk_patterns_for_form(form_type), max_chars)

        if not risk_text:
            return ToolResult.create_failure(f"Could not extract risk factors from {form_type} filing for {symbol}")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": form_type,
                "section": "risk_factors",
                "text": risk_text,
                "char_count": len(risk_text),
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "sec_edgar_risk_factors",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_business_overview(self, symbol: str, form_type: str, period: str, max_chars: int) -> ToolResult:
        """Extract business overview section."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(f"Could not retrieve {form_type} filing text for {symbol}")

        business_text = self._extract_section_by_patterns(text, self._business_patterns_for_form(form_type), max_chars)

        if not business_text:
            return ToolResult.create_failure(
                f"Could not extract business overview from {form_type} filing for {symbol}"
            )

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": form_type,
                "section": "business_overview",
                "text": business_text,
                "char_count": len(business_text),
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            metadata={
                "source": "sec_edgar_business_overview",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_management_discussion(self, symbol: str, max_chars: int) -> ToolResult:
        """Get comprehensive management commentary from multiple sources.

        Prioritizes quarterly MD&A, then annual MD&A and recent 8-K developments.
        """
        sections = {}
        sources = []
        char_budget = max_chars

        # Current quarterly commentary is the highest-value input.
        try:
            mda_result = await self._get_mda(symbol, "10-Q", "latest", max(1000, char_budget // 2))
            if mda_result.success:
                sections["mda_10q"] = mda_result.output.get("text", "")
                char_budget -= len(sections["mda_10q"])
                sources.append(self._management_source("mda_10q", mda_result.output))
        except Exception as e:
            logger.warning(f"Could not get 10-Q MD&A for {symbol}: {e}")

        if char_budget > 2000:
            try:
                mda_result = await self._get_mda(symbol, "10-K", "latest", min(char_budget, 5000))
                if mda_result.success:
                    sections["mda_10k"] = mda_result.output.get("text", "")
                    char_budget -= len(sections["mda_10k"])
                    sources.append(self._management_source("mda_10k", mda_result.output))
            except Exception as e:
                logger.warning(f"Could not get 10-K MD&A for {symbol}: {e}")

        # Get recent developments from 8-K
        if char_budget > 2000:
            try:
                dev_result = await self._get_developments(symbol, 3, min(char_budget, 5000))
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
        return {
            "section": section,
            "accession_number": output.get("accession_number"),
            "filing_date": output.get("filing_date"),
            "period_end": output.get("period_end"),
            "form_url": output.get("form_url"),
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
            },
            "required": ["symbol"],
        }
