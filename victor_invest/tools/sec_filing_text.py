# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
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
real-time management guidance and commentary for LLM synthesis.

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
from datetime import datetime
from typing import Any, Dict, List, Optional

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
- get_management_discussion: Get comprehensive management commentary (MD&A + guidance + developments)

Parameters:
- symbol: Stock ticker symbol (required)
- action: One of the actions above (required)
- form_type: Filing form type for specific filing lookup (default: "10-K")
- period: Filing period ("latest" or specific quarter like "2024-Q3")
- num_filings: Number of recent filings to search for developments (default: 5)
- max_chars: Maximum characters to return per section (default: 15000)
"""

    def __init__(self, config: Optional[Any] = None):
        """Initialize SEC Filing Text Tool.

        Args:
            config: Optional investigator config object.
        """
        super().__init__(config)
        self._sec_client: Optional[Any] = None

        # Section patterns for extraction
        self._mda_patterns = [
            r"item\s*7\.?\s*[:\s]*management['']?s\s+discussion\s+and\s+analysis",
            r"management['']?s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations",
            r"MD&A\s*\n",
            r"II\.?\s*MANAGEMENT['']?S\s+DISCUSSION\s+AND\s+ANALYSIS",
        ]

        self._guidance_patterns = [
            r"item\s*7\.?\s*[:\s]*management['']?s\s+discussion",
            r"outlook\s*\n",
            r"forward[- ]?looking\s+statements?",
            r"guidance\s*\n",
            r"future\s+prospects?",
            r"business\s+outlook",
            r"we\s+(?:expect|anticipate|project|forecast)",
        ]

        self._risk_factors_patterns = [
            r"item\s*1a\.?\s*[:\s]*risk\s+factors",
            r"risk\s+factors\s*\n",
            r"key\s+risk\s+factors",
            r"significant\s+risk",
        ]

        self._business_overview_patterns = [
            r"item\s*1\.?\s*[:\s]*business",
            r"business\s+overview\s*\n",
            r"our\s+business\s*\n",
            r"company\s+overview",
            r"description\s+of\s+business",
        ]

        self._developments_patterns = [
            r"item\s*1\.?\s*[:\s]*entry\s+into\s+a\s+material\s+definitive\s+agreement",
            r"item\s*2\.?\s*[:\s]*results\s+of\s+operations\s+and\s+financial\s+condition",
            r"item\s*8\.?\s*[:\s]*other\s+events?",
            r"recent\s+developments?",
            r"material\s+events?",
        ]

    async def initialize(self) -> None:
        """Initialize SEC infrastructure components."""
        try:
            from investigator.infrastructure.sec.sec_api import SECApiClient

            if self.config is None:
                from investigator.config import get_config

                self.config = get_config()

            self._sec_client = SECApiClient(config=self.config)
            self._initialized = True
            logger.info("SECFilingTextTool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SECFilingTextTool: {e}")
            raise

    async def execute(
        self,
        _exec_ctx: Optional[Dict[str, Any]] = None,
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

            action = action.lower().strip()

            if action == "get_mda":
                return await self._get_mda(symbol, form_type, period, max_chars)
            elif action == "get_guidance":
                return await self._get_guidance(symbol, form_type, period, max_chars)
            elif action == "get_developments":
                return await self._get_developments(symbol, num_filings, max_chars)
            elif action == "get_risk_factors":
                return await self._get_risk_factors(
                    symbol, form_type, period, max_chars
                )
            elif action == "get_business_overview":
                return await self._get_business_overview(
                    symbol, form_type, period, max_chars
                )
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
                f"SEC filing text extraction failed: {str(e)}",
                metadata={"symbol": symbol, "action": action},
            )

    def _normalize_text(self, text: str) -> str:
        """Normalize filing text by removing HTML tags and extra whitespace."""
        # Decode HTML entities
        decoded = html.unescape(text or "")
        # Remove HTML tags
        no_tags = re.sub(r"<[^>]+>", " ", decoded)
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", no_tags)
        # Remove XBRL artifacts
        normalized = re.sub(r"\{[^}]+\}", " ", normalized)
        return normalized.strip()

    def _extract_section_by_patterns(
        self, text: str, patterns: List[str], max_chars: int
    ) -> Optional[str]:
        """Extract a section from filing text using regex patterns.

        Args:
            text: Full filing text
            patterns: List of regex patterns to identify section start
            max_chars: Maximum characters to return

        Returns:
            Extracted section text or None
        """
        normalized = self._normalize_text(text)

        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE | re.MULTILINE)
            if match:
                start_pos = match.start()
                # Look for the next major section (ITEM heading)
                next_section = re.search(
                    r"\nitem\s+\d+[a-z]?\.",
                    normalized[start_pos + 100 :],
                    re.IGNORECASE,
                )

                if next_section:
                    end_pos = start_pos + 100 + next_section.start()
                else:
                    # No next section, take up to max_chars
                    end_pos = min(len(normalized), start_pos + max_chars)

                section_text = normalized[start_pos:end_pos]
                # Truncate to max_chars
                if len(section_text) > max_chars:
                    section_text = section_text[:max_chars] + "... [truncated]"

                return section_text.strip()

        return None

    def _extract_guidance_sentences(
        self, text: str, max_sentences: int = 50
    ) -> List[str]:
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
        guidance_sentences = []

        for sentence in sentences:
            if len(guidance_sentences) >= max_sentences:
                break
            for cue in guidance_cues:
                if re.search(cue, sentence, re.IGNORECASE):
                    guidance_sentences.append(sentence.strip())
                    break

        return guidance_sentences

    async def _get_filing_text(
        self, symbol: str, form_type: str, period: str
    ) -> Optional[str]:
        """Get filing text from SEC.

        Args:
            symbol: Stock ticker
            form_type: Form type
            period: Filing period

        Returns:
            Filing text or None
        """
        if self._sec_client is None:
            return None

        try:
            filing_data = await self._sec_client.get_filing_by_symbol(
                symbol=symbol, form_type=form_type, period=period
            )
            return filing_data.get("text", "")
        except Exception as e:
            logger.error(f"Error fetching filing text: {e}")
            return None

    async def _get_mda(
        self, symbol: str, form_type: str, period: str, max_chars: int
    ) -> ToolResult:
        """Extract Management's Discussion and Analysis section."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(
                f"Could not retrieve {form_type} filing text for {symbol}"
            )

        mda_text = self._extract_section_by_patterns(
            text, self._mda_patterns, max_chars
        )

        if not mda_text:
            # Fallback: try to extract any discussion-like content
            normalized = self._normalize_text(text)
            # Look for paragraphs discussing results, operations, etc.
            discussion_keywords = [
                r"(?:revenue|sales|earnings|income).{0,300}(?:increased|decreased|grew|declined)",
                r"(?:operating|gross|net).{0,200}margin.{0,200}%",
                r"cash\s+flow.{0,200}(?:increased|decreased|generated)",
            ]
            extracted_sentences = []
            for keyword in discussion_keywords:
                matches = re.finditer(keyword, normalized, re.IGNORECASE)
                for match in matches:
                    start = max(0, match.start() - 100)
                    end = min(len(normalized), match.end() + 200)
                    sentence = normalized[start:end].strip()
                    if len(sentence) > 50 and sentence not in extracted_sentences:
                        extracted_sentences.append(sentence)
                        if len(extracted_sentences) >= 20:
                            break
                if len(extracted_sentences) >= 20:
                    break

            if extracted_sentences:
                mda_text = " ".join(extracted_sentences)[:max_chars]
            else:
                return ToolResult.create_failure(
                    f"Could not extract MD&A section from {form_type} filing for {symbol}"
                )

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": form_type,
                "section": "mda",
                "text": mda_text,
                "char_count": len(mda_text),
                "fetched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "sec_edgar_mda",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_guidance(
        self, symbol: str, form_type: str, period: str, max_chars: int
    ) -> ToolResult:
        """Extract management guidance and outlook."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(
                f"Could not retrieve {form_type} filing text for {symbol}"
            )

        # First try to find a dedicated guidance section
        guidance_section = self._extract_section_by_patterns(
            text, self._guidance_patterns, max_chars
        )

        if guidance_section:
            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": form_type,
                    "section": "guidance",
                    "text": guidance_section,
                    "char_count": len(guidance_section),
                    "fetched_at": datetime.now().isoformat(),
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
                    "fetched_at": datetime.now().isoformat(),
                },
                metadata={
                    "source": "sec_edgar_guidance",
                    "form_type": form_type,
                    "period": period,
                },
            )

        return ToolResult.create_failure(
            f"Could not extract guidance from {form_type} filing for {symbol}"
        )

    async def _get_developments(
        self, symbol: str, num_filings: int, max_chars: int
    ) -> ToolResult:
        """Extract recent developments from 8-K filings."""
        if self._sec_client is None:
            return ToolResult.create_failure("SEC client not initialized")

        try:
            # Search for recent 8-K filings
            filings = await self._sec_client.search_filings(
                symbol=symbol, form_type="8-K", limit=num_filings
            )

            if not filings:
                return ToolResult.create_failure(
                    f"No recent 8-K filings found for {symbol}",
                    metadata={"symbol": symbol, "form_type": "8-K"},
                )

            developments = []
            total_chars = 0

            for filing in filings[:num_filings]:
                if total_chars >= max_chars:
                    break

                filing_date = filing.get("filing_date", "")
                accession_number = filing.get("accession_number", "")

                # Try to get the full filing text
                try:
                    cik = filing.get("cik", "")
                    if not cik:
                        continue

                    text = await self._sec_client.get_filing(accession_number, cik)
                    if not text:
                        continue

                    # Extract developments section
                    dev_text = self._extract_section_by_patterns(
                        text, self._developments_patterns, max_chars - total_chars
                    )

                    if dev_text:
                        developments.append(
                            f"## Filing Date: {filing_date}\n{dev_text}\n"
                        )
                        total_chars += len(dev_text)
                    else:
                        # Fallback: take first 2000 chars of the filing
                        normalized = self._normalize_text(text)
                        snippet = normalized[: min(2000, max_chars - total_chars)]
                        developments.append(
                            f"## Filing Date: {filing_date}\n{snippet}\n"
                        )
                        total_chars += len(snippet)

                except Exception as e:
                    logger.warning(
                        f"Error processing 8-K filing {accession_number}: {e}"
                    )
                    continue

            if not developments:
                return ToolResult.create_failure(
                    f"Could not extract developments from 8-K filings for {symbol}"
                )

            combined_text = "\n".join(developments)

            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "form_type": "8-K",
                    "section": "developments",
                    "text": combined_text,
                    "char_count": len(combined_text),
                    "filing_count": len(developments),
                    "fetched_at": datetime.now().isoformat(),
                },
                metadata={"source": "sec_edgar_8k", "num_filings": num_filings},
            )

        except Exception as e:
            logger.error(f"Error getting developments for {symbol}: {e}")
            return ToolResult.create_failure(f"Failed to get developments: {str(e)}")

    async def _get_risk_factors(
        self, symbol: str, form_type: str, period: str, max_chars: int
    ) -> ToolResult:
        """Extract risk factors section."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(
                f"Could not retrieve {form_type} filing text for {symbol}"
            )

        risk_text = self._extract_section_by_patterns(
            text, self._risk_factors_patterns, max_chars
        )

        if not risk_text:
            return ToolResult.create_failure(
                f"Could not extract risk factors from {form_type} filing for {symbol}"
            )

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "form_type": form_type,
                "section": "risk_factors",
                "text": risk_text,
                "char_count": len(risk_text),
                "fetched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "sec_edgar_risk_factors",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_business_overview(
        self, symbol: str, form_type: str, period: str, max_chars: int
    ) -> ToolResult:
        """Extract business overview section."""
        text = await self._get_filing_text(symbol, form_type, period)
        if not text:
            return ToolResult.create_failure(
                f"Could not retrieve {form_type} filing text for {symbol}"
            )

        business_text = self._extract_section_by_patterns(
            text, self._business_overview_patterns, max_chars
        )

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
                "fetched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "sec_edgar_business_overview",
                "form_type": form_type,
                "period": period,
            },
        )

    async def _get_management_discussion(
        self, symbol: str, max_chars: int
    ) -> ToolResult:
        """Get comprehensive management commentary from multiple sources.

        Combines MD&A from 10-K, guidance from latest 10-Q/8-K, and recent developments.
        """
        sections = {}
        char_budget = max_chars

        # Get MD&A from 10-K (highest priority)
        try:
            mda_result = await self._get_mda(symbol, "10-K", "latest", char_budget // 2)
            if mda_result.success:
                sections["mda_10k"] = mda_result.output.get("text", "")
                char_budget -= len(sections["mda_10k"])
        except Exception as e:
            logger.warning(f"Could not get 10-K MD&A for {symbol}: {e}")

        # Get guidance from latest 10-Q
        if char_budget > 3000:
            try:
                guidance_result = await self._get_guidance(
                    symbol, "10-Q", "latest", min(char_budget // 2, 5000)
                )
                if guidance_result.success:
                    sections["guidance_10q"] = guidance_result.output.get("text", "")
                    char_budget -= len(sections["guidance_10q"])
            except Exception as e:
                logger.warning(f"Could not get 10-Q guidance for {symbol}: {e}")

        # Get recent developments from 8-K
        if char_budget > 2000:
            try:
                dev_result = await self._get_developments(
                    symbol, 3, min(char_budget, 5000)
                )
                if dev_result.success:
                    sections["developments_8k"] = dev_result.output.get("text", "")
            except Exception as e:
                logger.warning(f"Could not get 8-K developments for {symbol}: {e}")

        if not sections:
            return ToolResult.create_failure(
                f"Could not extract any management commentary from filings for {symbol}"
            )

        # Combine sections with headers
        combined_parts = []
        if "mda_10k" in sections:
            combined_parts.append(
                f"# Management's Discussion and Analysis (10-K)\n{sections['mda_10k']}"
            )
        if "guidance_10q" in sections:
            combined_parts.append(
                f"# Management Guidance (10-Q)\n{sections['guidance_10q']}"
            )
        if "developments_8k" in sections:
            combined_parts.append(
                f"# Recent Developments (8-K)\n{sections['developments_8k']}"
            )

        combined_text = "\n\n".join(combined_parts)

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "section": "management_discussion_comprehensive",
                "text": combined_text,
                "char_count": len(combined_text),
                "sections_included": list(sections.keys()),
                "fetched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "sec_edgar_comprehensive",
                "sections": list(sections.keys()),
            },
        )

    def get_schema(self) -> Dict[str, Any]:
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
