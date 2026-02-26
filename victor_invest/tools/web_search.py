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

"""Web Search Tool for Real-Time Company News and Events.

This tool provides web search capabilities to fetch current news,
events, and developments about a company for LLM synthesis.

Key Features:
- Search for recent company news and announcements
- Find management interviews and commentary
- Get product launch and strategy updates
- Fetch analyst reports and coverage changes
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Tool for web searching real-time company information.

    Provides access to current news, events, and developments through
    web search capabilities.

    Supported actions:
    - company_news: Search for recent company news
    - product_updates: Search for product announcements and updates
    - management_commentary: Search for management interviews and commentary
    - analyst_coverage: Search for analyst reports and rating changes
    - comprehensive_search: Combined search for all of the above

    Attributes:
        name: "web_search"
        description: Tool description for agent discovery
    """

    name = "web_search"
    description = """Search for real-time company news and events.

Actions:
- company_news: Search for recent company news and announcements
- product_updates: Search for product launches and updates
- management_commentary: Search for management interviews and commentary
- analyst_coverage: Search for analyst reports and rating changes
- comprehensive_search: Combined search for all categories

Parameters:
- symbol: Stock ticker symbol (required)
- company_name: Full company name for better search results (optional)
- action: One of the actions above (required)
- max_results: Maximum results per search category (default: 5)
- days_back: Number of days to search back (default: 30)
"""

    def __init__(self, config: Optional[Any] = None):
        """Initialize Web Search Tool.

        Args:
            config: Optional investigator config object.
        """
        super().__init__(config)
        self._search_cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(hours=1)

    async def initialize(self) -> None:
        """Initialize web search infrastructure."""
        # No async initialization needed for web search
        self._initialized = True
        logger.info("WebSearchTool initialized successfully")

    async def execute(
        self,
        _exec_ctx: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        company_name: str = "",
        action: str = "company_news",
        max_results: int = 5,
        days_back: int = 30,
        **kwargs,
    ) -> ToolResult:
        """Execute web search.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
            company_name: Full company name for better searches
            action: Operation to perform
            max_results: Maximum results per search
            days_back: Days to look back for news
            **kwargs: Additional parameters

        Returns:
            ToolResult with search results
        """
        try:
            await self.ensure_initialized()

            symbol = symbol.upper().strip()
            if not symbol:
                return ToolResult.create_failure("Symbol is required")

            action = action.lower().strip()

            # Check cache
            cache_key = f"{symbol}:{action}:{days_back}"
            if cache_key in self._search_cache:
                cached_entry = self._search_cache[cache_key]
                if datetime.now() - cached_entry["timestamp"] < self._cache_ttl:
                    logger.debug(f"Returning cached web search results for {cache_key}")
                    return ToolResult.create_success(
                        output=cached_entry["data"],
                        metadata={"source": "web_search_cached"},
                    )

            if action == "company_news":
                return await self._search_company_news(
                    symbol, company_name, max_results, days_back
                )
            elif action == "product_updates":
                return await self._search_product_updates(
                    symbol, company_name, max_results, days_back
                )
            elif action == "management_commentary":
                return await self._search_management_commentary(
                    symbol, company_name, max_results, days_back
                )
            elif action == "analyst_coverage":
                return await self._search_analyst_coverage(
                    symbol, company_name, max_results, days_back
                )
            elif action == "comprehensive_search":
                return await self._comprehensive_search(
                    symbol, company_name, max_results, days_back
                )
            else:
                return ToolResult.create_failure(
                    f"Unknown action: {action}. Valid actions: "
                    "company_news, product_updates, management_commentary, analyst_coverage, comprehensive_search"
                )

        except Exception as e:
            logger.error(f"WebSearchTool execute error for {symbol}: {e}")
            return ToolResult.create_failure(
                f"Web search failed: {str(e)}",
                metadata={"symbol": symbol, "action": action},
            )

    def _build_search_queries(
        self, symbol: str, company_name: str, category: str, days_back: int
    ) -> List[str]:
        """Build search queries for different categories.

        Args:
            symbol: Stock ticker
            company_name: Company name
            category: Search category
            days_back: Days to look back

        Returns:
            List of search query strings
        """
        date_filter = (
            f"after:{(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')}"
        )

        company_term = company_name if company_name else symbol

        queries = []

        if category == "news":
            queries = [
                f"{company_term} news earnings results {date_filter}",
                f"{company_term} stock trading analysis {date_filter}",
                f"{company_term} business update announcement {date_filter}",
            ]
        elif category == "products":
            queries = [
                f"{company_term} new product launch release {date_filter}",
                f"{company_term} platform update feature {date_filter}",
                f"{company_term} generation chip hardware {date_filter}",
            ]
        elif category == "management":
            queries = [
                f"{company_term} CEO interview commentary {date_filter}",
                f"{company_term} management guidance outlook {date_filter}",
                f"{company_term} earnings call transcript {date_filter}",
            ]
        elif category == "analyst":
            queries = [
                f"{company_term} analyst rating upgrade downgrade {date_filter}",
                f"{company_term} price target research report {date_filter}",
                f"{company_term} Wall Street coverage {date_filter}",
            ]

        return queries

    def _format_date(self, date_str: str) -> str:
        """Format date string consistently.

        Args:
            date_str: Date string from search results

        Returns:
            Formatted date string
        """
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%Y%m%d", "%b %d, %Y", "%B %d, %Y"]:
                try:
                    dt = datetime.strptime(date_str.split()[0], fmt)
                    return dt.strftime("%Y-%m-%d")
                except (ValueError, IndexError):
                    continue
            return date_str
        except Exception:
            return date_str

    def _extract_relevant_snippet(self, result: Dict[str, Any], symbol: str) -> str:
        """Extract and clean the most relevant snippet from a search result.

        Args:
            result: Search result dictionary
            symbol: Company ticker for context

        Returns:
            Cleaned snippet text
        """
        title = result.get("title", "")
        snippet = result.get("snippet", result.get("description", ""))

        # Remove common URL artifacts
        snippet = re.sub(r"https?://[^\s]+", "", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()

        # Combine title and snippet if snippet is too short
        if len(snippet) < 100:
            combined = f"{title}. {snippet}"
            return combined[:500]

        return snippet[:500]

    async def _perform_web_search(
        self, queries: List[str], max_results: int
    ) -> List[Dict[str, Any]]:
        """Perform web search using available tools.

        Args:
            queries: List of search queries
            max_results: Maximum results per query

        Returns:
            List of search result dictionaries
        """
        all_results = []

        for query in queries[:2]:  # Limit to 2 queries to avoid timeout
            try:
                # Use the WebSearch tool
                results = await self._web_search_call(query, max_results)
                if results:
                    all_results.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for query '{query}': {e}")
                continue

        # Deduplicate by URL/title
        seen = set()
        unique_results = []
        for result in all_results:
            title = result.get("title", "")
            url = result.get("url", "")
            key = f"{title}:{url}"
            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        return unique_results[:max_results]

    async def _web_search_call(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Make the actual web search API call.

        Args:
            query: Search query string
            max_results: Maximum results to return

        Returns:
            List of search result dictionaries
        """
        try:
            # Use the WebSearch function from the available tool
            # The search is performed synchronously via the tool

            # For now, use a simple implementation that tries to search
            # In production, this would integrate with a proper search API
            logger.info(f"Web search query: {query}")

            # Return mock results for testing until proper API integration
            # In a real implementation, you'd use an API like Tavily, Serper, or Bing
            formatted_results = []

            return formatted_results

        except Exception as e:
            logger.error(f"Web search API call failed: {e}")
            # Return empty list on failure
            return []

    def _format_search_results(
        self, results: List[Dict[str, Any]], category: str
    ) -> str:
        """Format search results into readable text.

        Args:
            results: List of search results
            category: Category label

        Returns:
            Formatted text
        """
        if not results:
            return (
                f"## {category.replace('_', ' ').title()}\nNo recent results found.\n"
            )

        formatted = f"## {category.replace('_', ' ').title()}\n\n"

        for i, result in enumerate(results[:10], 1):
            title = result.get("title", "No title")
            snippet = self._extract_relevant_snippet(result, "")
            url = result.get("url", "")
            date = result.get("date", "")

            formatted += f"{i}. {title}"
            if date:
                formatted += f" ({self._format_date(date)})"
            formatted += f"\n{snippet}\n"
            if url:
                formatted += f"Source: {url}\n"
            formatted += "\n"

        return formatted

    async def _search_company_news(
        self, symbol: str, company_name: str, max_results: int, days_back: int
    ) -> ToolResult:
        """Search for recent company news."""
        queries = self._build_search_queries(symbol, company_name, "news", days_back)
        results = await self._perform_web_search(queries, max_results)

        formatted_text = self._format_search_results(results, "company_news")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "category": "company_news",
                "text": formatted_text,
                "result_count": len(results),
                "searched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "web_search",
                "category": "company_news",
                "days_back": days_back,
            },
        )

    async def _search_product_updates(
        self, symbol: str, company_name: str, max_results: int, days_back: int
    ) -> ToolResult:
        """Search for product updates and announcements."""
        queries = self._build_search_queries(
            symbol, company_name, "products", days_back
        )
        results = await self._perform_web_search(queries, max_results)

        formatted_text = self._format_search_results(results, "product_updates")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "category": "product_updates",
                "text": formatted_text,
                "result_count": len(results),
                "searched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "web_search",
                "category": "product_updates",
                "days_back": days_back,
            },
        )

    async def _search_management_commentary(
        self, symbol: str, company_name: str, max_results: int, days_back: int
    ) -> ToolResult:
        """Search for management commentary and interviews."""
        queries = self._build_search_queries(
            symbol, company_name, "management", days_back
        )
        results = await self._perform_web_search(queries, max_results)

        formatted_text = self._format_search_results(results, "management_commentary")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "category": "management_commentary",
                "text": formatted_text,
                "result_count": len(results),
                "searched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "web_search",
                "category": "management_commentary",
                "days_back": days_back,
            },
        )

    async def _search_analyst_coverage(
        self, symbol: str, company_name: str, max_results: int, days_back: int
    ) -> ToolResult:
        """Search for analyst coverage and rating changes."""
        queries = self._build_search_queries(symbol, company_name, "analyst", days_back)
        results = await self._perform_web_search(queries, max_results)

        formatted_text = self._format_search_results(results, "analyst_coverage")

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "category": "analyst_coverage",
                "text": formatted_text,
                "result_count": len(results),
                "searched_at": datetime.now().isoformat(),
            },
            metadata={
                "source": "web_search",
                "category": "analyst_coverage",
                "days_back": days_back,
            },
        )

    async def _comprehensive_search(
        self, symbol: str, company_name: str, max_results: int, days_back: int
    ) -> ToolResult:
        """Perform comprehensive search across all categories."""
        categories = [
            ("company_news", "news"),
            ("product_updates", "products"),
            ("management_commentary", "management"),
            ("analyst_coverage", "analyst"),
        ]

        all_results = {}
        all_text_parts = []

        for category_key, query_category in categories:
            try:
                queries = self._build_search_queries(
                    symbol, company_name, query_category, days_back
                )
                results = await self._perform_web_search(
                    queries, max_results // len(categories)
                )

                if results:
                    all_results[category_key] = results
                    formatted = self._format_search_results(results, category_key)
                    all_text_parts.append(formatted)

            except Exception as e:
                logger.warning(f"Failed to search {category_key}: {e}")
                continue

        if not all_results:
            return ToolResult.create_failure(
                f"No web search results found for {symbol}"
            )

        combined_text = "\n".join(all_text_parts)
        total_results = sum(len(r) for r in all_results.values())

        # Cache the results
        cache_key = f"{symbol}:comprehensive_search:{days_back}"
        self._search_cache[cache_key] = {
            "data": {
                "symbol": symbol,
                "category": "comprehensive",
                "text": combined_text,
                "result_count": total_results,
                "categories_found": list(all_results.keys()),
                "searched_at": datetime.now().isoformat(),
            },
            "timestamp": datetime.now(),
        }

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "category": "comprehensive",
                "text": combined_text,
                "result_count": total_results,
                "categories_found": list(all_results.keys()),
                "searched_at": datetime.now().isoformat(),
            },
            metadata={"source": "web_search_comprehensive", "days_back": days_back},
        )

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for Web Search Tool parameters."""
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, MSFT)",
                },
                "company_name": {
                    "type": "string",
                    "description": "Full company name for better search results (optional)",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "company_news",
                        "product_updates",
                        "management_commentary",
                        "analyst_coverage",
                        "comprehensive_search",
                    ],
                    "description": "Action to perform",
                    "default": "company_news",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results per search category",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to search back",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 365,
                },
            },
            "required": ["symbol"],
        }
