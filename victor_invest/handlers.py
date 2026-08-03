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

"""Domain handlers for Investment vertical workflows.

Registers compute node handlers for investment analysis workflows using
Victor's @handler_decorator pattern for automatic registration and
boilerplate elimination via BaseHandler.

Example YAML usage:
    - id: fetch_sec_data
      type: compute
      handler: fetch_sec_data
      output: sec_data

Migration Notice:
    Migrated 2025-01-26 from manual NodeResult pattern to @handler_decorator + BaseHandler.
    Reduced boilerplate from ~87% to ~0% (2,100 lines → 280 lines).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# Victor framework imports for new pattern
from victor_invest.compat.handlers import BaseHandler, handler_decorator

if TYPE_CHECKING:
    from victor_contracts.verticals.protocols.tools import ToolRegistryProtocol as ToolRegistry
    from victor_contracts.workflows import ComputeNodeProtocol as ComputeNode
    from victor_contracts.workflows import WorkflowContextProtocol as WorkflowContext

logger = logging.getLogger(__name__)

# Import sector name mapper for use in handlers (available but not required)
# Handlers that need sector normalization can use this as needed
try:
    from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

    SECTOR_MAPPER_AVAILABLE = True
except ImportError:
    SECTOR_MAPPER_AVAILABLE = False
    SectorIndustryMapper = None


# =============================================================================
# Data Collection Handlers
# =============================================================================


@handler_decorator("fetch_sec_data", vertical="investment", description="Fetch SEC filing data")
@dataclass
class FetchSECDataHandler(BaseHandler):
    """Fetch SEC filing data for analysis."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute SEC data fetch.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        symbol = context.get("symbol", "")

        if not symbol:
            return {"status": "error", "error": "No symbol provided", "data": None}, 0

        from victor_invest.tools.sec_filing import SECFilingTool

        sec_tool = SECFilingTool()
        result = await sec_tool.execute(
            {},  # _exec_ctx (not used by investment tools)
            symbol=symbol,
            action="get_company_facts",
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator("fetch_market_data", vertical="investment", description="Fetch market/price data")
@dataclass
class FetchMarketDataHandler(BaseHandler):
    """Fetch market/price data for analysis."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute market data fetch.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        symbol = context.get("symbol", "")

        if not symbol:
            return {"status": "error", "error": "No symbol provided", "data": None}, 0

        from victor_invest.tools.market_data import MarketDataTool

        market_tool = MarketDataTool()
        result = await market_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            action="get_history",
            days=365,
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator("fetch_macro_data", vertical="investment", description="Fetch macroeconomic data")
@dataclass
class FetchMacroDataHandler(BaseHandler):
    """Fetch macroeconomic data for context."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute macro data fetch.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from datetime import date

        from investigator.domain.services.data_sources import get_data_source_facade

        symbol = context.get("symbol", "SPY")
        facade = get_data_source_facade()
        analysis_data = facade.get_historical_data_sync(symbol=symbol, as_of_date=date.today())

        macro_data = {
            "treasury": {},
            "volatility": {},
            "fed_indicators": {},
            "status": "success",
        }

        if analysis_data.treasury_data:
            treasury = analysis_data.treasury_data
            macro_data["treasury"] = {
                "yield_10y": treasury.get("yield_10y"),
                "yield_2y": treasury.get("yield_2y"),
                "yield_curve_slope": treasury.get("curve_slope"),
            }

        if analysis_data.cboe_data:
            vol = analysis_data.cboe_data
            macro_data["volatility"] = {
                "vix": vol.get("vix"),
                "skew": vol.get("skew"),
            }

        return macro_data, 0


@handler_decorator(
    "fetch_management_discussion",
    vertical="investment",
    description="Fetch SEC management discussion text",
)
@dataclass
class FetchManagementDiscussionHandler(BaseHandler):
    """Fetch SEC management discussion and commentary for LLM synthesis.

    Extracts MD&A, guidance, and recent developments from SEC filings
    to provide real-time management insights for investment analysis.
    """

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute management discussion fetch.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        symbol = context.get("symbol", "")

        if not symbol:
            return {"status": "error", "error": "No symbol provided", "data": None}, 0

        from victor_invest.tools.sec_filing_text import SECFilingTextTool

        sec_text_tool = SECFilingTextTool()
        result = await sec_text_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            action="get_management_discussion",
            max_chars=15000,
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "fetch_company_news",
    vertical="investment",
    description="Fetch real-time company news",
)
@dataclass
class FetchCompanyNewsHandler(BaseHandler):
    """Fetch real-time company news and events for LLM synthesis.

    Searches for recent company news, product updates, management
    commentary, and analyst coverage to supplement the analysis.
    """

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute company news fetch.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        symbol = context.get("symbol", "")
        company_name = context.get("company_name", "")

        if not symbol:
            return {"status": "error", "error": "No symbol provided", "data": None}, 0

        from victor_invest.tools.web_search import WebSearchTool

        web_search_tool = WebSearchTool()
        result = await web_search_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            company_name=company_name,
            action="comprehensive_search",
            max_results=5,
            days_back=30,
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


# =============================================================================
# Analysis Handlers
# =============================================================================


@handler_decorator(
    "run_fundamental_analysis",
    vertical="investment",
    description="Run fundamental analysis",
)
@dataclass
class RunFundamentalAnalysisHandler(BaseHandler):
    """Run fundamental analysis on SEC data."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute fundamental analysis.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        # Validate credentials before execution
        try:
            from investigator.infrastructure.node_credentials import (
                NodeCredentialContext,
            )

            cred_ctx = NodeCredentialContext.from_node(node, context)
            cred_errors = cred_ctx.validate_requirements()
            if cred_errors:
                logger.warning(f"Credential warnings for {node.id}: {cred_errors}")
        except ImportError:
            pass  # Credential validation optional

        sec_data = context.get("sec_data", {})

        if sec_data.get("status") != "success":
            return {"status": "skipped", "reason": "No SEC data"}, 0

        symbol = context.get("symbol", "")

        from victor_invest.tools.valuation import ValuationTool

        valuation_tool = ValuationTool()
        result = await valuation_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            model="all",
        )

        output_data = result.output if result.success else None

        # Add overall_score for compatibility with synthesis
        if output_data and result.success:
            current_price = output_data.get("current_price")
            consensus_fair_value = output_data.get("consensus_fair_value")

            if current_price and consensus_fair_value:
                # Calculate score based on valuation
                upside = (consensus_fair_value / current_price) - 1
                if upside > 0.20:
                    overall_score = 85
                elif upside > 0:
                    overall_score = 70
                elif upside > -0.10:
                    overall_score = 50
                elif upside > -0.30:
                    overall_score = 30
                else:
                    overall_score = 15

                output_data["overall_score"] = overall_score

        # Include SEC data (quarterly metrics, guidance, filings) for UI/compact format
        # This ensures the fundamental analysis output has the SEC context
        sec_output_data = {}
        if isinstance(sec_data, dict) and sec_data.get("status") == "success":
            sec_info = sec_data.get("data", sec_data)
            # Extract key SEC data for compact format/UI
            if isinstance(sec_info, dict):
                sec_output_data["quarterly_metrics"] = sec_info.get("quarterly_metrics", [])
                sec_output_data["forward_guidance"] = sec_info.get("forward_guidance")
                sec_output_data["recent_filings"] = sec_info.get("recent_filings", [])
                sec_output_data["company_facts"] = sec_info.get("companyfacts_summary")

        return {
            "status": "success" if result.success else "error",
            "data": output_data,
            "error": result.error if not result.success else None,
            # Include SEC data for downstream consumption (compact format, UI)
            "sec_data": sec_output_data if sec_output_data else None,
        }, 0


@handler_decorator(
    "run_technical_analysis",
    vertical="investment",
    description="Run technical analysis",
)
@dataclass
class RunTechnicalAnalysisHandler(BaseHandler):
    """Run technical analysis on market data with multi-tier granularity."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute technical analysis with weekly (strategic) and daily (tactical) data.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        market_data = context.get("market_data", {})

        if market_data.get("status") != "success":
            return {"status": "skipped", "reason": "No market data"}, 0

        symbol = context.get("symbol", "")

        from victor_invest.tools.technical_indicators import TechnicalIndicatorsTool

        tech_tool = TechnicalIndicatorsTool()

        # Get weekly data for strategic analysis (2 years = 104 weeks)
        weekly_result = await tech_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            action="calculate_all",
            granularity="weekly",  # NEW parameter
            days=104,  # 104 weeks = 2 years
        )

        # Get daily data for tactical signals (1 year = 365 days)
        daily_result = await tech_tool.execute(
            {},  # _exec_ctx
            symbol=symbol,
            action="calculate_all",
            granularity="daily",
            days=365,
        )

        # Combine results
        # Also include current_price from market data for convenience
        current_price = None
        if market_data.get("data"):
            market_data_dict = market_data.get("data", {})
            if hasattr(market_data_dict, "get"):
                current_price = market_data_dict.get("current_price")
            elif isinstance(market_data_dict, dict):
                # Try to get current_price from various possible locations
                current_price = (
                    market_data_dict.get("current_price")
                    or market_data_dict.get("price")
                    or (
                        market_data_dict.get("quote", {}).get("price")
                        if isinstance(market_data_dict.get("quote"), dict)
                        else None
                    )
                )

        return {
            "status": "success",
            "weekly": weekly_result.output if weekly_result.success else None,
            "daily": daily_result.output if daily_result.success else None,
            "summary": self._summarize_multi_tier(weekly_result, daily_result),
            "current_price": current_price,
        }, 0

    def _summarize_multi_tier(self, weekly_result, daily_result) -> dict:
        """Create a combined summary of weekly and daily technical signals."""
        summary = {
            "strategic_trend": None,  # From weekly
            "tactical_signal": None,  # From daily
            "overall_bias": "neutral",
        }

        # Extract strategic trend from weekly data
        if weekly_result.success and weekly_result.output:
            weekly_latest = weekly_result.output.get("latest", {})
            weekly_price = weekly_latest.get("price", {})
            weekly_ma = weekly_latest.get("moving_averages", {})

            current_price = weekly_price.get("close")
            sma_200 = weekly_ma.get("sma_200")

            if current_price and sma_200:
                if current_price > sma_200:
                    summary["strategic_trend"] = "bullish"
                else:
                    summary["strategic_trend"] = "bearish"

        # Extract tactical signal from daily data
        if daily_result.success and daily_result.output:
            daily_latest = daily_result.output.get("latest", {})
            daily_momentum = daily_latest.get("momentum", {})

            rsi = daily_momentum.get("rsi_14")

            # Combine trend + momentum for tactical signal
            if summary["strategic_trend"] == "bullish" and rsi and rsi < 70:
                summary["tactical_signal"] = "buy"
            elif summary["strategic_trend"] == "bearish" and rsi and rsi > 30:
                summary["tactical_signal"] = "sell"
            else:
                summary["tactical_signal"] = "hold"

        # Overall bias
        if summary["strategic_trend"] == "bullish" and summary["tactical_signal"] == "buy":
            summary["overall_bias"] = "strong_buy"
        elif summary["strategic_trend"] == "bearish" and summary["tactical_signal"] == "sell":
            summary["overall_bias"] = "strong_sell"
        elif summary["strategic_trend"] == "bullish":
            summary["overall_bias"] = "moderate_buy"
        elif summary["strategic_trend"] == "bearish":
            summary["overall_bias"] = "moderate_sell"

        return summary


@handler_decorator(
    "run_market_context_analysis",
    vertical="investment",
    description="Run market context analysis",
)
@dataclass
class RunMarketContextHandler(BaseHandler):
    """Run market regime/context analysis."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute market context analysis.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from investigator.config import get_config

        cfg = get_config()
        symbol = context.get("symbol", "SPY")

        try:
            from victor_invest.tools.market_regime import MarketRegimeTool

            regime_tool = MarketRegimeTool()

            # Get lookback_days from config with fallback
            lookback_days = 252  # Default 1 year
            if hasattr(cfg, "market_context") and hasattr(cfg.market_context, "lookback_days"):
                lookback_days = cfg.market_context.lookback_days

            result = await regime_tool.execute(
                {},  # _exec_ctx
                symbol=symbol,
                lookback_days=lookback_days,
            )

            return {
                "status": "success" if result.success else "error",
                "data": result.output if result.success else None,
                "error": result.error if not result.success else None,
            }, 0

        except Exception as e:
            logger.warning(f"Market regime analysis unavailable: {e}")
            return {
                "status": "success",
                "data": {"market_regime": "unknown", "trend": "neutral"},
                "error": None,
            }, 0


# =============================================================================
# Synthesis Handlers
# =============================================================================


@handler_decorator("run_synthesis", vertical="investment", description="Run multi-model synthesis")
@dataclass
class RunSynthesisHandler(BaseHandler):
    """Synthesize analysis from multiple sources.

    Combines fundamental, technical, and market context analysis into
    a unified investment recommendation with optional LLM enhancement.
    """

    _config: Any = None
    _llm_client: Any = None
    _victor_providers: dict[str, Any] = field(default_factory=dict)  # Cache Victor providers

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute synthesis analysis.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        symbol = context.get("symbol", "UNKNOWN")
        fundamental = context.get("fundamental_analysis", {})
        technical = context.get("technical_analysis", {})
        market_context = context.get("market_context", {})
        peer_data = context.get("peer_data") or {}

        # Get LLM provider/model from context (set by CLI --provider/--model)
        llm_provider = context.get("llm_provider", None)
        llm_model = context.get("llm_model", None)

        # Respect workflow constraints: only use LLM when explicitly allowed.
        constraints = getattr(node, "constraints", None)
        llm_allowed = bool(getattr(constraints, "llm_allowed", False))
        llm_result = None
        if llm_allowed:
            llm_result = await self._llm_synthesis(
                symbol,
                technical,
                fundamental,
                market_context,
                peer_data,
                llm_provider,
                llm_model,  # Pass provider/model
            )

        if llm_result:
            output = {
                "status": "success",
                "synthesis_method": "llm",
                "executive_summary": llm_result.get("executive_summary", ""),
                "recommendation": llm_result.get("recommendation", "HOLD"),
                "confidence": llm_result.get("confidence", "MEDIUM"),
                "composite_score": llm_result.get("composite_score", 50),
                "key_catalysts": llm_result.get("key_catalysts", []),
                "key_risks": llm_result.get("key_risks", []),
                "price_target": llm_result.get("price_target"),
                "stop_loss": llm_result.get("stop_loss"),
                "time_horizon": llm_result.get("time_horizon", "MEDIUM-TERM"),
                "technical_strength": llm_result.get("technical_strength", "NEUTRAL"),
                "valuation_summary": llm_result.get("valuation_summary", ""),
                "peer_comparison_summary": llm_result.get("peer_comparison_summary", ""),
                "reasoning": llm_result.get("reasoning", ""),
                "fundamental_analysis_thinking": llm_result.get("fundamental_analysis_thinking", ""),
                "technical_analysis_thinking": llm_result.get("technical_analysis_thinking", ""),
                "key_technical_signals": llm_result.get("key_technical_signals", []),
                "risk_factors_detailed": llm_result.get("risk_factors_detailed", []),
                "score_breakdown": llm_result.get("score_breakdown", {}),
                "individual_scores": {},
            }
        else:
            output = self._rule_based_synthesis(fundamental, technical, market_context)

        # Add fair_value_estimate from fundamental data
        fund_data = fundamental.get("data", {}) if fundamental else {}
        if fund_data.get("consensus_fair_value") and not output.get("fair_value_estimate"):
            output["fair_value_estimate"] = fund_data.get("consensus_fair_value")
            output["price_target"] = fund_data.get("consensus_fair_value")
            # Override recommendation if valuation suggests strong buy/sell
            consensus_upside = fund_data.get("consensus_upside", 0)
            if consensus_upside > 20:
                output["recommendation"] = "BUY"
                output["confidence"] = "HIGH"
            elif consensus_upside < -20:
                output["recommendation"] = "SELL"
                output["confidence"] = "HIGH"

        # Calculate composite score
        tech_data = technical.get("data", {}) if technical else {}
        fundamental_score = fund_data.get("overall_score", 50) if fund_data else 50
        technical_score = tech_data.get("overall_score", 50) if tech_data else 50

        trend = tech_data.get("trend", {}) if tech_data else {}
        if trend:
            trend_signal = trend.get("overall_signal", "neutral")
            trend_scores = {"bullish": 70, "neutral": 50, "bearish": 30}
            technical_score = trend_scores.get(trend_signal, 50)

        composite_score = fundamental_score * 0.6 + technical_score * 0.4
        output["composite_score"] = composite_score
        output["individual_scores"] = {
            "fundamental": fundamental_score,
            "technical": technical_score,
        }

        # Cleanup LLM client
        if self._llm_client is not None:
            try:
                await self._llm_client.close()
                self._llm_client = None
            except Exception:
                pass

        return output, 1 if llm_result else 0

    def _get_config(self) -> Any:
        """Lazy load config."""
        if self._config is None:
            from investigator.config import get_config

            self._config = get_config()
        return self._config

    def _get_llm_client(self) -> Any:
        """Lazy load LLM client."""
        if self._llm_client is None:
            from investigator.infrastructure.llm import OllamaClient

            # Get config for Ollama base URL
            try:
                from investigator.config import get_config

                config = get_config()
                base_url = getattr(config.ollama, "base_url", None) or "http://localhost:11434"
            except Exception:
                base_url = "http://localhost:11434"

            self._llm_client = OllamaClient(base_url=base_url)
        return self._llm_client

    def _build_synthesis_prompt(
        self,
        symbol: str,
        technical: dict,
        fundamental: dict,
        market_context: dict,
        peer_data: dict | None = None,
        management_discussion: dict | None = None,
        company_news: dict | None = None,
    ) -> str:
        """Build synthesis prompt for LLM with enhanced context.

        Returns formatted prompt string.
        """
        # Format real-time data sections
        mda_section = ""
        if management_discussion and management_discussion.get("status") == "success":
            mda_data = management_discussion.get("data", {})
            mda_text = mda_data.get("text", "")
            if mda_text:
                # Truncate if too long (keep first 8000 chars)
                if len(mda_text) > 8000:
                    mda_text = mda_text[:8000] + "\n\n... [truncated]"
                mda_section = f"""
## Management Discussion & Analysis (From SEC Filings)
{mda_text}

**IMPORTANT**: This is ACTUAL management commentary from recent SEC filings. Use this for:
- Product announcements and roadmap (e.g., specific chip generations, platform names)
- Management guidance on revenue, margins, and growth
- Recent business developments and strategic initiatives
- Risk factors and challenges discussed by management

Do NOT rely on your training data for product names, timelines, or management statements.
Always use the information provided in this section first.
"""

        news_section = ""
        if company_news and company_news.get("status") == "success":
            news_data = company_news.get("data", {})
            news_text = news_data.get("text", "")
            if news_text:
                # Truncate if too long (keep first 5000 chars)
                if len(news_text) > 5000:
                    news_text = news_text[:5000] + "\n\n... [truncated]"
                news_section = f"""
## Recent News & Developments (From Web Search)
{news_text}

**IMPORTANT**: This is CURRENT information from the web. Use this for:
- Breaking news and recent announcements
- Current analyst coverage and rating changes
- Recent management interviews and commentary
- Product launch updates and competitive developments

This information supersedes any outdated knowledge from your training data.
"""

        prompt = f"""You are a senior investment analyst at a top-tier institutional research firm. Your task is to provide a comprehensive, professional investment recommendation for {symbol}.

## CRITICAL INSTRUCTIONS

1. **USE SPECIFIC NUMBERS**: Every claim must be backed by actual data from the analysis
2. **BE THOROUGH**: The fundamental_analysis_thinking and technical_analysis_thinking fields must be 500-800 words EACH
3. **PROFESSIONAL TONE**: Write like a Wall Street research report, not a blog post
4. **STRUCTURED THINKING**: Follow the exact paragraph structure specified below
5. **ACTIONABLE INSIGHTS**: Provide specific catalysts, risks, and price targets with clear reasoning
6. **USE REAL-TIME DATA**: The Management Discussion and Recent News sections below contain CURRENT information.
   Prioritize this over your training data, which may be outdated.
   - Use actual product names, generations, and timelines from SEC filings
   - Reference management's actual guidance and commentary
   - Include recent news and analyst coverage in your analysis

{mda_section}

{news_section}

## Fundamental Analysis
{_format_fundamental(fundamental)}

{_format_quarterly_trends_and_filings(fundamental)}

## Technical Analysis
{_format_technical(technical)}

## Market Context
- Market Regime: {market_context.get("market_regime", "unknown")}
- Sector: {market_context.get("sector", "unknown")}
- Industry: {market_context.get("industry", "unknown")}
- VIX Level: {market_context.get("vix_level", "N/A")}
- 10-Year Treasury: {market_context.get("treasury_10y", "N/A")}
- S&P 500 Trend: {market_context.get("spy_trend", "N/A")}

## Peer Comparison
{self._format_peer_comparison(peer_data if peer_data is not None else {})}

---

## YOUR ANALYSIS FRAMEWORK

### Valuation Assessment
- Compare the company's current price to the DCF, P/E, P/S, EV/EBITDA models
- Assess whether the market is overvaluing or undervaluing the business
- Consider sector/industry typical multiples and historical ranges

### Fundamental Health
- Revenue growth trend and sustainability
- Margin profile and competitive positioning
- Balance sheet strength and financial flexibility
- Cash generation quality and capital allocation

### Technical Positioning
- Primary trend (uptrend/downtrend/range-bound) with evidence
- Key support/resistance levels and their significance
- Momentum indicators and potential reversals
- Volume patterns and institutional accumulation/distribution

### Risk/Reward Profile
- Clear upside catalysts with probability estimates
- Downside risks with potential magnitude
- Time horizon for thesis to play out
- Entry/exit strategy recommendations

---

## REQUIRED JSON RESPONSE STRUCTURE

Provide your response as a JSON object with this exact structure:

{{
    "executive_summary": "2-3 compelling sentences that summarize the investment thesis. Must reference: 1) valuation vs current price, 2) primary catalyst, 3) key risk. Example: 'NVDA trades at a 20% discount to our DCF-derived fair value of $650, driven by exceptional data center AI demand. Key catalysts include Blackwell platform ramp and expanding GPU TAM. Risks include export controls and cyclicality in hyperscaler capex.'",

    "recommendation": "BUY" or "HOLD" or "SELL",
    "confidence": "HIGH" or "MEDIUM" or "LOW",
    "composite_score": <number 0-100 based on weighted average of all factors>,

    "key_catalysts": [
        "<specific catalyst 1 with timeline and probability estimate>",
        "<specific catalyst 2 with timeline and probability estimate>",
        "<specific catalyst 3 with timeline and probability estimate>"
    ],

    "key_risks": [
        "<specific risk 1 with quantification and mitigation>",
        "<specific risk 2 with quantification and mitigation>",
        "<specific risk 3 with quantification and mitigation>"
    ],

    "price_target": <number based on weighted average of applicable valuation models, rounded to 2 decimals>,
    "stop_loss": <number based on technical support level, rounded to 2 decimals>,
    "time_horizon": "SHORT-TERM" (0-6 months) or "MEDIUM-TERM" (6-18 months) or "LONG-TERM" (18+ months),
    "technical_strength": "STRONG" or "NEUTRAL" or "WEAK",

    "valuation_summary": "<3-4 sentences summarizing valuation conclusions. Mention: 1) which models are applicable, 2) fair value range, 3) key assumptions, 4) margin of safety. Example: 'Our DCF model ($650) assumes 25% CAGR over 5 years with 13% WACC. P/E analysis ($580) suggests 35% premium to sector median reflects growth expectations. EV/EBITDA ($620) accounts for strong FCF generation. Blended fair value of $617 implies 18% upside from current levels.'>",

    "peer_comparison_summary": "<2-3 sentences comparing to peers. Mention: 1) valuation relative to peer group, 2) operational metrics comparison, 3) relative strengths/weaknesses. Example: 'NVDA trades at a P/E of 60x vs peer median of 35x, justified by superior growth (65% vs 25% YoY) and higher margins (72% GM vs 58% median). ROE of 58% leads all peers while debt-to-equity of 0.45 provides financial flexibility.'>",

    "reasoning": "<4-6 detailed paragraphs explaining your recommendation. Paragraph 1: VALUATION SYNTHESIS - Explain how different models converge/diverge and what this signals about market expectations. Paragraph 2: GROWTH DRIVERS - Detail the specific business dynamics driving revenue/earnings. Paragraph 3: COMPETITIVE POSITIONING - Discuss moats, market share, and sustainability. Paragraph 4: FINANCIAL HEALTH - Analyze balance sheet, cash flow, and capital allocation. Paragraph 5: RISK/REWARD - Quantify upside/downside scenarios and key variables to watch. Paragraph 6: TIMING - Explain current setup and why now is (or isn't) the right entry point. USE SPECIFIC NUMBERS throughout.>",

    "fundamental_analysis_thinking": "CRITICAL - 6 paragraphs minimum (500-800 words):\n\nPARAGRAPH 1 - FINANCIAL OVERVIEW: Summarize the company's financial scale and health. Must include: total revenue ($XXB or $XXM), revenue growth rate (XX% YoY, XX% QoQ), gross margin (XX%), operating margin (XX%), net income ($XXB or $XXM), EPS ($XX), and market cap ($XXB). Example: 'NVIDIA generated $226.1B in TTM revenue, growing 262% YoY and 22% QoQ, demonstrating extraordinary demand for AI infrastructure. Gross margin expanded to 78.1% while operating margin reached 57.2%, reflecting pricing power and scale advantages. Net income of $105.2B translates to $42.75 EPS, with a market capitalization of $3.2T.\n\nPARAGRAPH 2 - BUSINESS QUALITY & COMPETITIVE POSITIONING: Analyze the company's competitive advantages. Must include: ROE (XX%), ROA (XX%), ROIC (XX%), asset turnover, and any mention of moat factors. Example: 'The company's return on equity of 58% and return on invested capital of 45% are exceptional, indicating a highly scalable business model with strong pricing power. The CUDA ecosystem creates high switching costs for developers and enterprises, while manufacturing leadership (TSMC 4nm process) provides supply constraints that support margins. Asset turnover of 0.9x reflects efficient capital utilization in a fabless model.\n\nPARAGRAPH 3 - GROWTH TRAJECTORY & SUSTAINABILITY: Assess revenue and earnings momentum. Must include: quarterly revenue trend (XXB → XXB → XXB), revenue growth consistency, margin trends, and guidance. Example: 'Revenue has accelerated from $13.5B (Q1 FY24) to $22.6B (Q3 FY25) to $26.0B (Q4 FY25), showing both sequential and year-over-year acceleration. Management raised long-term non-GAAP gross margin guidance to the low-70% range, suggesting sustainable operating leverage. Data center revenue grew 217% YoY and now represents 87% of total revenue, indicating successful pivot to AI-focused product mix.\n\nPARAGRAPH 4 - CASH FLOW & CAPITAL ALLOCATION: Detail sources and uses of cash. Must include: operating cash flow ($XXB), free cash flow ($XXB), capex ($XXB), FCF margin (XX%), dividend/buybacks. Example: 'Operating cash flow of $76.8B and free cash flow of $58.2B demonstrate exceptional cash generation, with FCF margin of 26%. Capital expenditures of $12.3B were primarily for manufacturing capacity expansion. The company returned $14.2B to shareholders via dividends and buybacks, representing 24% of FCF, while retaining $44B for strategic investments in R&D and capacity.\n\nPARAGRAPH 5 - BALANCE SHEET STRENGTH: Analyze financial flexibility. Must include: cash & investments ($XXB), total debt ($XXB), debt-to-equity (X.XX), current ratio (X.XX), and working capital trends. Example: 'The balance sheet remains robust with $38.1B in cash, investments, and short-term instruments against $11.2B in total debt, resulting in a debt-to-equity ratio of 0.45. Current ratio of 3.2x provides excellent liquidity. Working capital of $23.5B has grown 45% YoY, supporting the rapid business expansion. Net cash position of $26.9B provides substantial flexibility for strategic M&A or continued share repurchases.\n\nPARAGRAPH 6 - QUARTERLY PERFORMANCE & OUTLOOK: Assess the most recent quarter vs expectations. Must include: actual vs consensus revenue/EPS, key beats/misses, management tone, forward guidance. Example: 'The most recent quarter significantly exceeded expectations with revenue of $26.0B vs $25.2B consensus (+3%) and EPS of $5.16 vs $4.60 consensus (+12%). Management commentary highlighted continued supply constraints and strong demand visibility extending into calendar 2026. Forward guidance of $27.5B ± 2% for Q1 implies continued sequential growth, though the beat幅度 narrowed from prior quarters.',

    "technical_analysis_thinking": "CRITICAL - 6 paragraphs minimum (500-800 words):\n\nPARAGRAPH 1 - PRICE & TREND ANALYSIS: Analyze the current price position and trend. Must include: current price ($XXX), 20-day SMA ($XXX), 50-day SMA ($XXX), 200-day SMA ($XXX), and trend classification. Example: 'NVIDIA currently trades at $950, sitting 8.5% above its 20-day SMA ($875) and 15% above its 50-day SMA ($825), while the 200-day SMA ($650) is far below, confirming a strong uptrend. The stock is trading 22% below its 52-week high of $1,150 and 45% above its 52-week low of $650, suggesting it is in a consolidation phase within a longer-term uptrend. The price action shows higher highs followed by shallow pullbacks, characteristic of a strong uptrend with healthy corrections.\n\nPARAGRAPH 2 - MOMENTUM INDICATORS: Analyze RSI, MACD, and other momentum metrics. Must include: RSI (XX), MACD line (X.XX), signal line (X.XX), histogram, and interpretation. Example: 'The 14-day RSI stands at 58, indicating the stock is neither overbought (>70) nor oversold (<30). The MACD histogram shows declining momentum, with the MACD line at 15.2 crossing below the signal line at 16.8, suggesting short-term weakness. This negative divergence is reinforced by declining volume on recent up days, potentially signaling exhaustion after the 180% year-to-date rally. However, the overall uptrend remains intact with the 50-day SMA providing dynamic support.\n\nPARAGRAPH 3 - SUPPORT & RESISTANCE LEVELS: Identify key price levels. Must include: support levels ($XXX, $XXX), resistance levels ($XXX, $XXX), 52-week high/low, and their significance. Example: 'Primary support exists at $875 (20-day SMA and recent consolidation level), reinforced by volume-based profile from August-September. Secondary support sits at $825 (50-day SMA and breakout level from Q2). On the upside, resistance at $1,000 represents a psychological barrier and previous consolidation zone, with the all-time high of $1,150 marking major resistance. The stock is currently consolidating between $875 and $1,000, with a breakout above $1,000 potentially signaling the next leg higher.\n\nPARAGRAPH 4 - VOLUME & FLOW ANALYSIS: Analyze trading volume patterns. Must include: average volume (X.XM shares), recent volume trend, accumulation/distribution signals, and institutional activity. Example: 'Average daily volume over the past 50 days is 45M shares, with recent consolidation days showing below-average volume of 30-35M shares, indicating shareholder holding and lack of distribution. The late-October rally from $875 to $950 occurred on strong volume of 55-65M shares, suggesting institutional accumulation. On-balance volume analysis shows positive accumulation despite the recent sideways price action, typically a bullish leading indicator.\n\nPARAGRAPH 5 - ENTRY/EXIT STRATEGY: Provide actionable trading guidance. Must include: current entry rating, ideal entry point, stop loss level, profit targets. Example: 'Given the strong uptrend with healthy correction phase and positive on-balance volume, the current price represents a reasonable entry for investors with a 3-6 month time horizon. A more attractive entry would be on a pullback to the 50-day SMA at $825, which would provide better risk/reward. A stop loss should be placed below recent support at $850 (8% downside), while the primary profit target of $1,100 represents 16% upside. Traders should watch for volume confirmation on any breakout above $1,000.\n\nPARAGRAPH 6 - TECHNICAL VERDICT: Summarize technical positioning. Must include: overall rating (STRONG BUY/BUY/HOLD/SELL/STRONG SELL), key confirming indicators, and invalidating factors. Example: 'The technical setup remains BULLISH with confirmation from: 1) price above all major moving averages, 2) on-balance volume accumulation, 3) manageable RSI levels not signaling overbought conditions. The recent consolidation is healthy, allowing moving averages to catch up. Key technical risks include: 1) MACD bearish crossover, 2) declining volume on up moves, 3) extended price versus historical valuation multiples. A break below $875 would shift the technical outlook to neutral, while a confirmed breakout above $1,000 with strong volume would confirm the next leg higher.',

    "key_technical_signals": [
        "<signal 1 with specific numeric value and implication>",
        "<signal 2 with specific numeric value and implication>",
        "<signal 3 with specific numeric value and implication>"
    ],

    "risk_factors_detailed": [
        "<risk 1 with probability (low/medium/high), magnitude (%, $), and mitigation>",
        "<risk 2 with probability (low/medium/high), magnitude (%, $), and mitigation>",
        "<risk 3 with probability (low/medium/high), magnitude (%, $), and mitigation>"
    ],

    "score_breakdown": {{
        "income_statement": <0-100 score based on revenue growth, margins, earnings quality>,
        "cash_flow": <0-100 score based on OCF, FCF, FCF margin, capex efficiency>,
        "balance_sheet": <0-100 score based on liquidity, leverage, solvency>,
        "growth": <0-100 score based on revenue/earnings growth rates and sustainability>,
        "value": <0-100 score based on valuation multiples relative to intrinsic value>,
        "business_quality": <0-100 score based on ROIC, margins, competitive positioning>,
        "data_quality": <0-100 score based on completeness and recency of SEC filing data>
    }}
}}

## FORMATTING REQUIREMENTS

1. **executive_summary**: Must be 2-3 sentences, reference specific numbers, mention catalyst + risk + valuation
2. **fundamental_analysis_thinking**: Must be 6 paragraphs with headings in ALL CAPS followed by colon, 500-800 words total
3. **technical_analysis_thinking**: Must be 6 paragraphs with headings in ALL CAPS followed by colon, 500-800 words total
4. **All numeric fields**: Round to 2 decimal places where appropriate
5. **key_catalysts/key_risks**: Must be specific and quantified with timelines where applicable
6. **Respond ONLY with the JSON object**: No markdown formatting, no code blocks, no explanatory text"""

        return prompt

    def _format_peer_comparison(self, peer_data: dict) -> str:
        """Format peer comparison data for the synthesis prompt.

        Returns formatted string.
        """
        if not peer_data:
            return "## Peer Comparison\nNo peer data available."

        peers = peer_data.get("peers", [])
        metrics = peer_data.get("peer_metrics", {})

        if not peers:
            return "## Peer Comparison\nNo peer companies found for comparison."

        parts = ["## Peer Comparison"]
        parts.append(f"Found {len(peers)} comparable companies:")

        for peer in peers[:5]:
            symbol = peer.get("symbol", "N/A")
            peer.get("name", "")
            match_type = peer.get("match_type", "sector")
            val = peer.get("valuation") or {}

            mcap = peer.get("market_cap")
            mcap_str = f"${mcap / 1e9:.1f}B" if mcap else "N/A"

            pe = val.get("pe_ratio")
            pe_str = f"{pe:.1f}x" if pe else "N/A"

            upside = val.get("upside_pct")
            upside_str = f"{upside:+.1f}%" if upside else "N/A"

            parts.append(
                f"  - {symbol} ({match_type}): Market Cap {mcap_str}, P/E {pe_str}, Predicted Upside {upside_str}"
            )

        if metrics:
            parts.append("\n### Peer Group Medians:")
            if "pe_ratio_median" in metrics:
                parts.append(
                    f"  - P/E Median: {metrics['pe_ratio_median']:.1f}x (range: {metrics.get('pe_ratio_min', 0):.1f}x - {metrics.get('pe_ratio_max', 0):.1f}x)"
                )
            if "revenue_growth_median" in metrics:
                parts.append(f"  - Revenue Growth Median: {metrics['revenue_growth_median'] * 100:.1f}%")
            if "fcf_margin_median" in metrics:
                parts.append(f"  - FCF Margin Median: {metrics['fcf_margin_median'] * 100:.1f}%")
            if "upside_pct_median" in metrics:
                parts.append(f"  - Predicted Upside Median: {metrics['upside_pct_median']:+.1f}%")

        return "\n".join(parts)

    async def _llm_synthesis(
        self,
        symbol: str,
        technical: dict,
        fundamental: dict,
        market_context: dict,
        peer_data: dict | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> dict | None:
        """Use LLM for intelligent synthesis with retry logic.

        Args:
            symbol: Stock symbol
            technical: Technical analysis data
            fundamental: Fundamental analysis data
            market_context: Market context data
            peer_data: Optional peer comparison data
            llm_provider: LLM provider (ollama, anthropic, openai, or None for default)
            llm_model: Model identifier

        Returns LLM-generated synthesis dict or None if unavailable after retries.

        Note: Always uses Victor's provider framework for proper retry logic and error handling.
        The legacy OllamaClient path has been removed to ensure consistent behavior.
        """
        # Resolve provider: use provided, or default to env var
        from victor_invest.framework_bootstrap import (
            resolve_model_from_env,
            resolve_provider_from_env,
        )

        if not llm_provider:
            # No provider specified - resolve from environment
            llm_provider = resolve_provider_from_env()
        if not llm_model:
            # No model specified - resolve from environment
            llm_model = resolve_model_from_env(llm_provider or "", llm_model)
            if not llm_model:
                llm_model = "default"  # Fallback to provider default

        # Always use Victor's provider framework (ollama, anthropic, openai, etc.)
        # This gives us proper retry logic, error handling, and re-request capabilities
        return await self._llm_synthesis_victor(
            symbol,
            technical,
            fundamental,
            market_context,
            peer_data,
            llm_provider or "ollama",  # Default to ollama if still None
            llm_model if llm_model else "default",
        )

    async def _llm_synthesis_victor(
        self,
        symbol: str,
        technical: dict,
        fundamental: dict,
        market_context: dict,
        peer_data: dict | None = None,
        provider: str = "ollama",
        model: str | None = None,
    ) -> dict | None:
        """Use Victor's provider API for LLM synthesis (all providers).

        Uses ProviderRegistry.create() which leverages:
        - Built-in retry logic and re-request on failure
        - Victor's default profile when provider not specified
        - Provider-specific error handling
        - Automatic API key retrieval from keyring

        Args:
            symbol: Stock symbol
            technical: Technical analysis data
            fundamental: Fundamental analysis data
            market_context: Market context data
            peer_data: Optional peer comparison data
            provider: LLM provider (ollama, anthropic, openai, etc.)
            model: Model identifier (uses default profile if not specified)

        Returns LLM-generated synthesis dict or None if unavailable.
        """
        try:
            from victor_invest.compat.providers import create_provider
            from victor_invest.framework_bootstrap import (
                PROVIDER_DEFAULT_MODELS,
                resolve_model_from_env,
            )

            # Resolve model if not specified
            resolved_model = model or resolve_model_from_env(provider, None)
            if not resolved_model:
                resolved_model = PROVIDER_DEFAULT_MODELS.get(provider, "gpt-oss:20b")

            # Cache key for provider instance (reduces keychain access)
            cache_key = f"{provider}:{resolved_model}"
            if cache_key not in self._victor_providers:
                provider_instance = create_provider(
                    provider,
                    model=resolved_model,
                    temperature=0.3,
                    max_tokens=4096,
                )
                if provider_instance is None:
                    return None
                self._victor_providers[cache_key] = provider_instance
                logger.debug(f"Cached Victor provider: {cache_key}")
            else:
                provider_instance = self._victor_providers[cache_key]
                logger.debug(f"Using cached Victor provider: {cache_key}")

            # Fetch real-time data for LLM synthesis
            # This ensures the LLM uses current information instead of training data
            management_discussion = None
            company_news = None

            try:
                from victor_invest.tools.sec_filing_text import SECFilingTextTool

                sec_text_tool = SECFilingTextTool()
                mda_result = await sec_text_tool.execute(
                    {},  # _exec_ctx
                    symbol=symbol,
                    action="get_management_discussion",
                    max_chars=12000,
                )
                if mda_result.success:
                    management_discussion = {
                        "status": "success",
                        "data": mda_result.output,
                    }
                    logger.info(f"Retrieved management discussion for {symbol}")
                else:
                    logger.debug(f"No management discussion available for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to fetch management discussion for {symbol}: {e}")

            try:
                from victor_invest.tools.web_search import WebSearchTool

                web_search_tool = WebSearchTool()
                news_result = await web_search_tool.execute(
                    {},  # _exec_ctx
                    symbol=symbol,
                    company_name="",  # Will be inferred from symbol
                    action="comprehensive_search",
                    max_results=5,
                    days_back=30,
                )
                if news_result.success:
                    company_news = {"status": "success", "data": news_result.output}
                    logger.info(f"Retrieved company news for {symbol}")
                else:
                    logger.debug(f"No company news available for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to fetch company news for {symbol}: {e}")

            # Build prompt with real-time data
            prompt = self._build_synthesis_prompt(
                symbol,
                technical,
                fundamental,
                market_context,
                peer_data,
                management_discussion,
                company_news,
            )

            # Generate response using Victor's chat API
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    from victor_contracts.provider_runtime import Message

                    # Create message list
                    messages = [Message(role="user", content=prompt)]

                    response = await provider_instance.chat(
                        messages=messages,
                        model=resolved_model,
                        temperature=0.3,
                        max_tokens=4096,
                    )

                    response_text = response.content if hasattr(response, "content") else str(response)

                    # Try to extract and validate JSON
                    result = self._extract_and_validate_json(response_text, symbol)
                    if result:
                        logger.info(
                            f"Successfully parsed LLM synthesis JSON (attempt {attempt + 1}/{max_retries}, {len(result)} keys)"
                        )
                        return result
                    else:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries}: Failed to parse JSON from LLM response")
                        if attempt < max_retries - 1:
                            logger.info("Retrying with stronger JSON formatting instructions...")
                            # Add JSON formatting instructions to prompt
                            prompt += (
                                "\n\n**IMPORTANT**: Your previous response was not valid JSON. "
                                "You must respond ONLY with a valid JSON object. "
                                "Do NOT include any explanatory text before or after the JSON. "
                                "The response must start with '{' and end with '}'."
                            )
                        continue

                except Exception as e:
                    logger.warning(f"LLM synthesis attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        logger.error(f"LLM synthesis failed after {max_retries} attempts: {e}")
                        return None

            logger.warning(f"LLM synthesis failed after {max_retries} attempts, falling back to rule-based")
            return None

        except Exception as e:
            logger.warning(f"Victor provider LLM synthesis failed: {e}")
            return None

    def _extract_and_validate_json(self, response_text: str, symbol: str) -> dict | None:
        """Extract and validate JSON from LLM response.

        Args:
            response_text: Raw LLM response text
            symbol: Stock symbol for logging

        Returns:
            Parsed dict if valid JSON found, None otherwise
        """
        import json

        # Debug: Log response for troubleshooting
        logger.debug(f"LLM raw response (first 1000 chars): {response_text[:1000]}")

        # Find JSON object in response - look for complete object
        start = response_text.find("{")
        if start < 0:
            logger.debug("No '{' found in LLM response")
            return None

        # Count braces to find matching end
        brace_count = 0
        in_string = False
        escape_next = False
        for i in range(start, len(response_text)):
            char = response_text[i]
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        json_str = response_text[start:end]
                        try:
                            result: dict = json.loads(json_str)
                            # Validate required fields
                            required_fields = ["recommendation", "confidence"]
                            missing_fields = [f for f in required_fields if f not in result]
                            if missing_fields:
                                logger.warning(f"JSON missing required fields: {missing_fields}")
                                return None
                            return result
                        except json.JSONDecodeError as e:
                            logger.warning(f"JSON decode error: {e}")
                            return None

        logger.debug("Could not find complete JSON object in LLM response")
        return None

    def _rule_based_synthesis(self, fundamental: dict, technical: dict, market_context: dict) -> dict:
        """Fallback rule-based synthesis when LLM is unavailable.

        Returns synthesis dict.
        """
        fundamental = fundamental or {}
        technical = technical or {}
        market_context = market_context or {}

        fund_data = fundamental.get("data", {})
        tech_data = technical.get("data", {})

        # Extract valuation data to determine recommendation
        fair_value = fund_data.get("consensus_fair_value")
        current_price = fund_data.get("current_price")

        # Calculate fundamental score based on valuation if available
        if fair_value and current_price:
            # Convert upside to score:
            # >20% upside = 80+ (strong buy)
            # 0-20% upside = 60-80 (buy)
            # -10% to 0% = 40-60 (hold)
            # -10% to -30% = 20-40 (sell)
            # < -30% = <20 (strong sell)
            upside = (fair_value / current_price) - 1
            if upside > 0.20:
                fundamental_score = 85
            elif upside > 0:
                fundamental_score = 70
            elif upside > -0.10:
                fundamental_score = 50
            elif upside > -0.30:
                fundamental_score = 30
            else:
                fundamental_score = 15
        else:
            fundamental_score = fund_data.get("overall_score", 50)

        technical_score = tech_data.get("overall_score", 50)

        # Weight valuation more heavily than technical for recommendation
        composite_score = fundamental_score * 0.7 + technical_score * 0.3

        if composite_score >= 70:
            recommendation = "BUY"
            confidence = "HIGH"
        elif composite_score >= 55:
            recommendation = "BUY"
            confidence = "MEDIUM"
        elif composite_score >= 45:
            recommendation = "HOLD"
            confidence = "MEDIUM"
        elif composite_score >= 30:
            recommendation = "SELL"
            confidence = "MEDIUM"
        else:
            recommendation = "SELL"
            confidence = "HIGH"

        # Build score_breakdown from available data
        score_breakdown = self._build_score_breakdown(fund_data, tech_data)

        # Generate thinking sections from structured data
        fundamental_thinking = self._generate_fundamental_thinking(fund_data)
        technical_thinking = self._generate_technical_thinking(tech_data)

        # Extract key signals from technical data
        key_signals = self._extract_key_signals(tech_data)

        # Generate risk factors and catalysts
        risk_factors = self._generate_risk_factors(fund_data, tech_data, market_context)
        catalysts = self._generate_catalysts(fund_data, tech_data)

        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            recommendation, confidence, fund_data, tech_data, market_context
        )

        # Generate valuation summary
        valuation_summary = self._generate_valuation_summary(fund_data)

        return {
            "status": "success",
            "synthesis_method": "rule_based",
            "composite_score": composite_score,
            "individual_scores": {
                "fundamental": fundamental_score,
                "technical": technical_score,
            },
            "recommendation": recommendation,
            "confidence": confidence,
            "price_target": fair_value if fair_value else None,
            "fair_value_estimate": fair_value if fair_value else None,
            "market_regime": market_context.get("market_regime", "unknown"),
            "score_breakdown": score_breakdown,
            "fundamental_analysis_thinking": fundamental_thinking,
            "technical_analysis_thinking": technical_thinking,
            "key_technical_signals": key_signals,
            "risk_factors_detailed": risk_factors,
            "key_risks": risk_factors[:4] if risk_factors else [],
            "key_catalysts": catalysts,
            "executive_summary": executive_summary,
            "valuation_summary": valuation_summary,
        }

    def _build_score_breakdown(self, fund_data: dict, tech_data: dict) -> dict:
        """Build detailed score breakdown from fundamental and technical data.

        Returns score breakdown dict.
        """
        breakdown = {}

        # Extract from fundamental data if available
        if fund_data:
            models = fund_data.get("models", {})

            # Estimate component scores from valuation models
            dcf = models.get("dcf", {})
            pe = models.get("pe", {})
            models.get("ps", {})

            # Cash flow score from DCF model success/margin
            if dcf and dcf.get("fair_value_per_share"):
                fcf_margin = dcf.get("assumptions", {}).get("fcf_margin", 0)
                breakdown["cash_flow"] = min(100, max(0, 50 + fcf_margin * 100))
            else:
                breakdown["cash_flow"] = 50

            # Value score from upside potential
            consensus_upside = fund_data.get("consensus_upside", 0)
            if consensus_upside:
                breakdown["value"] = min(100, max(0, 50 + consensus_upside))
            else:
                breakdown["value"] = 50

            # Income statement score from PE model
            if pe and pe.get("fair_value_per_share"):
                eps = pe.get("eps_ttm", 0)
                breakdown["income_statement"] = 70 if eps and eps > 0 else 40
            else:
                breakdown["income_statement"] = 50

            # Growth score estimation
            growth_rate = dcf.get("assumptions", {}).get("fcf_growth_rate", 0)
            if growth_rate:
                breakdown["growth"] = min(100, max(0, 50 + growth_rate * 200))
            else:
                breakdown["growth"] = 50

            # Balance sheet (estimate from debt levels if available)
            breakdown["balance_sheet"] = 60  # Default moderate

            # Business quality from model confidence
            confidences = [m.get("confidence", 50) for m in models.values() if isinstance(m, dict)]
            if confidences:
                breakdown["business_quality"] = sum(confidences) / len(confidences)
            else:
                breakdown["business_quality"] = 50

        # Data quality based on models available
        models_count = len(fund_data.get("models", {})) if fund_data else 0
        breakdown["data_quality"] = min(100, models_count * 20)

        return breakdown

    def _generate_fundamental_thinking(self, fund_data: dict) -> str:
        """Generate fundamental analysis narrative from structured data.

        Returns narrative string.
        """
        if not fund_data:
            return ""

        parts = []
        models = fund_data.get("models", {})
        current_price = fund_data.get("current_price", 0)
        consensus_fv = fund_data.get("consensus_fair_value")
        consensus_upside = fund_data.get("consensus_upside")

        # Opening assessment
        if consensus_upside:
            if consensus_upside > 20:
                parts.append("The stock appears significantly undervalued based on our multi-model analysis.")
            elif consensus_upside > 0:
                parts.append("The stock shows moderate upside potential based on fundamental analysis.")
            elif consensus_upside > -20:
                parts.append("The stock appears fairly valued to slightly overvalued at current levels.")
            else:
                parts.append("The stock appears significantly overvalued relative to intrinsic value estimates.")

        # DCF analysis
        dcf = models.get("dcf", {})
        if dcf and dcf.get("fair_value_per_share"):
            dcf_fv = dcf.get("fair_value_per_share")
            dcf_upside = dcf.get("upside_downside_pct", 0)
            wacc = dcf.get("assumptions", {}).get("wacc", 0)
            terminal_growth = dcf.get("assumptions", {}).get("terminal_growth_rate", 0)

            parts.append(
                f"\n\nDiscounted Cash Flow Analysis: Our DCF model yields a fair value of ${dcf_fv:.2f} per share, implying {dcf_upside:+.1f}% from current levels."
            )
            if wacc:
                # wacc and terminal_growth are already percentages from DCF model (13.0 for 13%)
                parts.append(
                    f"We use a weighted average cost of capital (WACC) of {wacc:.1f}% and terminal growth rate of {terminal_growth:.1f}%."
                )

        # Multiple-based valuations
        pe = models.get("pe", {})
        ps = models.get("ps", {})

        if pe and pe.get("fair_value_per_share"):
            pe_fv = pe.get("fair_value_per_share")
            pe_ratio = pe.get("pe_ratio", 0)
            sector_pe = pe.get("sector_pe", 0)
            parts.append(
                f"\n\nP/E Multiple Analysis: Using a target P/E of {pe_ratio:.1f}x (sector median: {sector_pe:.1f}x), we derive a fair value of ${pe_fv:.2f}."
            )

        if ps and ps.get("fair_value_per_share"):
            ps_fv = ps.get("fair_value_per_share")
            ps_ratio = ps.get("ps_ratio", 0)
            parts.append(
                f"\n\nP/S Multiple Analysis: The price-to-sales approach suggests a fair value of ${ps_fv:.2f} using a {ps_ratio:.1f}x multiple."
            )

        # Conclusion
        if consensus_fv and current_price:
            parts.append(
                f"\n\nBlended Valuation: Weighing all models, our consensus fair value is ${consensus_fv:.2f}, compared to the current price of ${current_price:.2f}."
            )

        return "".join(parts) if parts else ""

    def _generate_technical_thinking(self, tech_data: dict) -> str:
        """Generate technical analysis narrative from structured data.

        Returns narrative string.
        """
        if not tech_data:
            return ""

        parts = []
        trend = tech_data.get("trend", {})
        sr = tech_data.get("support_resistance", {})
        momentum = tech_data.get("momentum", {})

        # Trend analysis
        if trend:
            signal = trend.get("overall_signal", "neutral")
            current_price = trend.get("current_price", 0)

            if signal.lower() == "bullish":
                parts.append("Technical indicators are showing bullish momentum across multiple timeframes.")
            elif signal.lower() == "bearish":
                parts.append("Technical indicators suggest bearish pressure with potential for further downside.")
            else:
                parts.append("Technical indicators are mixed, suggesting a consolidation phase.")

            if current_price:
                parts.append(f" The stock is currently trading at ${current_price:.2f}.")

        # Support/Resistance
        if sr:
            support_levels = sr.get("support_levels", {})
            resistance_levels = sr.get("resistance_levels", {})
            w52 = sr.get("52_week", {})

            support_1 = support_levels.get("support_1")
            resistance_1 = resistance_levels.get("resistance_1")

            if support_1 and resistance_1:
                parts.append(
                    f"\n\nKey Levels: Immediate support at ${support_1:.2f} and resistance at ${resistance_1:.2f}."
                )

            if w52:
                w52_high = w52.get("high")
                w52_low = w52.get("low")
                if w52_high and w52_low:
                    parts.append(f" The 52-week trading range is ${w52_low:.2f} to ${w52_high:.2f}.")

        # Momentum indicators
        if momentum:
            rsi = momentum.get("rsi_14")
            macd = momentum.get("macd_histogram")

            if rsi:
                if rsi > 70:
                    parts.append(f"\n\nMomentum: RSI at {rsi:.1f} indicates overbought conditions.")
                elif rsi < 30:
                    parts.append(
                        f"\n\nMomentum: RSI at {rsi:.1f} indicates oversold conditions, potentially signaling a bounce."
                    )
                else:
                    parts.append(f"\n\nMomentum: RSI at {rsi:.1f} is in neutral territory.")

            if macd:
                macd_signal = "positive" if macd > 0 else "negative"
                parts.append(
                    f" MACD histogram is {macd_signal}, suggesting {'bullish' if macd > 0 else 'bearish'} momentum."
                )

        return "".join(parts) if parts else ""

    def _extract_key_signals(self, tech_data: dict) -> list:
        """Extract key technical signals from data.

        Returns list of signal strings.
        """
        signals = []

        trend = tech_data.get("trend", {})
        sr = tech_data.get("support_resistance", {})
        momentum = tech_data.get("momentum", {})

        # Trend signals
        if trend:
            signal = trend.get("overall_signal", "neutral")
            signals.append(f"Overall trend signal: {signal.upper()}")

            signal_pcts = trend.get("signal_percentages", {})
            if signal_pcts:
                bullish_pct = signal_pcts.get("bullish", 0)
                bearish_pct = signal_pcts.get("bearish", 0)
                signals.append(f"Indicator breakdown: {bullish_pct:.0f}% bullish, {bearish_pct:.0f}% bearish")

        # Support/Resistance signals
        if sr:
            current = trend.get("current_price", 0) if trend else 0
            support_1 = sr.get("support_levels", {}).get("support_1")
            resistance_1 = sr.get("resistance_levels", {}).get("resistance_1")

            if current and support_1:
                pct_above_support = ((current - support_1) / support_1) * 100
                signals.append(f"Trading {pct_above_support:.1f}% above key support at ${support_1:.2f}")

            if current and resistance_1:
                pct_below_resistance = ((resistance_1 - current) / current) * 100
                signals.append(f"Resistance {pct_below_resistance:.1f}% higher at ${resistance_1:.2f}")

        # Momentum signals
        if momentum:
            rsi = momentum.get("rsi_14")
            if rsi:
                if rsi > 70:
                    signals.append(f"RSI overbought at {rsi:.1f}")
                elif rsi < 30:
                    signals.append(f"RSI oversold at {rsi:.1f}")
                else:
                    signals.append(f"RSI neutral at {rsi:.1f}")

        return signals[:5]  # Limit to 5 signals

    def _generate_risk_factors(self, fund_data: dict, tech_data: dict, market_context: dict) -> list:
        """Generate risk factors from available data.

        Returns list of risk strings.
        """
        risks = []

        # Valuation risk
        consensus_upside = fund_data.get("consensus_upside", 0) if fund_data else 0
        if consensus_upside < -20:
            risks.append("Significant overvaluation risk with limited margin of safety")
        elif consensus_upside < 0:
            risks.append("Stock trading above fair value estimates")

        # Model divergence risk
        models = fund_data.get("models", {}) if fund_data else {}
        fair_values = [
            m.get("fair_value_per_share", 0)
            for m in models.values()
            if isinstance(m, dict) and m.get("fair_value_per_share")
        ]
        if len(fair_values) >= 2:
            fv_range = max(fair_values) - min(fair_values)
            fv_avg = sum(fair_values) / len(fair_values)
            if fv_avg > 0 and (fv_range / fv_avg) > 0.5:
                risks.append("High valuation model divergence indicates uncertainty")

        # Technical risks
        trend = tech_data.get("trend", {}) if tech_data else {}
        if trend.get("overall_signal", "").lower() == "bearish":
            risks.append("Bearish technical momentum may pressure near-term performance")

        momentum = tech_data.get("momentum", {}) if tech_data else {}
        rsi = momentum.get("rsi_14")
        if rsi and rsi > 70:
            risks.append("Overbought RSI suggests potential near-term pullback")

        # Market regime risk
        regime = market_context.get("market_regime", "unknown") if market_context else "unknown"
        if regime.lower() in ["bearish", "risk_off", "bear"]:
            risks.append("Unfavorable market environment may limit upside")

        # Data quality risk
        if len(models) < 3:
            risks.append("Limited valuation model coverage reduces confidence")

        return risks

    def _generate_catalysts(self, fund_data: dict, tech_data: dict) -> list:
        """Generate potential catalysts from available data.

        Returns list of catalyst strings.
        """
        catalysts = []

        # Valuation catalysts
        consensus_upside = fund_data.get("consensus_upside", 0) if fund_data else 0
        if consensus_upside > 30:
            catalysts.append("Significant undervaluation provides margin of safety")
        elif consensus_upside > 15:
            catalysts.append("Attractive valuation with upside potential")

        # Technical catalysts
        trend = tech_data.get("trend", {}) if tech_data else {}
        if trend.get("overall_signal", "").lower() == "bullish":
            catalysts.append("Bullish technical momentum supports near-term appreciation")

        momentum = tech_data.get("momentum", {}) if tech_data else {}
        rsi = momentum.get("rsi_14")
        if rsi and rsi < 30:
            catalysts.append("Oversold conditions suggest potential mean reversion")

        # Model agreement catalyst
        models = fund_data.get("models", {}) if fund_data else {}
        upsides = [
            m.get("upside_downside_pct", 0) or m.get("upside_percent", 0)
            for m in models.values()
            if isinstance(m, dict)
        ]
        if upsides and all(u > 0 for u in upsides):
            catalysts.append("All valuation models indicate upside potential")

        return catalysts

    def _generate_executive_summary(
        self,
        recommendation: str,
        confidence: str,
        fund_data: dict,
        tech_data: dict,
        market_context: dict,
    ) -> str:
        """Generate executive summary paragraph.

        Returns summary string.
        """
        parts = []

        current_price = fund_data.get("current_price", 0) if fund_data else 0
        consensus_fv = fund_data.get("consensus_fair_value") if fund_data else None
        consensus_upside = fund_data.get("consensus_upside", 0) if fund_data else 0

        # Opening
        if recommendation == "BUY":
            parts.append(f"We rate this stock a {recommendation} with {confidence} confidence.")
        elif recommendation == "SELL":
            parts.append(
                f"We rate this stock a {recommendation} with {confidence} confidence due to valuation concerns."
            )
        else:
            parts.append(f"We rate this stock a {recommendation} as it appears fairly valued at current levels.")

        # Valuation context
        if consensus_fv and current_price:
            parts.append(
                f" Our blended fair value of ${consensus_fv:.2f} implies {consensus_upside:+.1f}% from the current price of ${current_price:.2f}."
            )

        # Technical context
        trend = tech_data.get("trend", {}) if tech_data else {}
        tech_signal = trend.get("overall_signal", "neutral")
        parts.append(f" Technical indicators are {tech_signal}.")

        # Market context
        regime = market_context.get("market_regime", "unknown") if market_context else "unknown"
        if regime != "unknown":
            parts.append(f" The current market environment is {regime}.")

        return "".join(parts)

    def _generate_valuation_summary(self, fund_data: dict) -> str:
        """Generate valuation summary paragraph.

        Returns summary string.
        """
        if not fund_data:
            return ""

        models = fund_data.get("models", {})
        consensus_fv = fund_data.get("consensus_fair_value")
        consensus_upside = fund_data.get("consensus_upside")

        if not models:
            return "Insufficient data for comprehensive valuation analysis."

        parts = []
        model_count = len(models)
        parts.append(
            f"We applied {model_count} valuation model{'s' if model_count > 1 else ''} to derive our fair value estimate."
        )

        if consensus_fv:
            parts.append(f" The blended fair value is ${consensus_fv:.2f}")
            if consensus_upside:
                parts.append(f" ({consensus_upside:+.1f}% from current levels).")
            else:
                parts.append(".")

        # Model range
        fair_values = [
            m.get("fair_value_per_share", 0)
            for m in models.values()
            if isinstance(m, dict) and m.get("fair_value_per_share")
        ]
        if len(fair_values) >= 2:
            parts.append(f" Fair value estimates range from ${min(fair_values):.2f} to ${max(fair_values):.2f}.")

        return "".join(parts)


# =============================================================================
# Report Generation Handlers
# =============================================================================


@handler_decorator(
    "generate_report",
    vertical="investment",
    description="Generate professional PDF report",
)
@dataclass
class GenerateReportHandler(BaseHandler):
    """Generate professional PDF report from analysis."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute report generation.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        import json

        from investigator.infrastructure.reporting.professional_report import (
            ProfessionalReportGenerator,
        )

        synthesis = context.get("synthesis") or {}
        symbol = context.get("symbol", "UNKNOWN")
        technical = context.get("technical_analysis") or {}
        fundamental = context.get("fundamental_analysis") or {}
        market_data = context.get("market_data") or {}

        # Handle synthesis as string (from agent node) or dict
        if isinstance(synthesis, str):
            try:
                start_idx = synthesis.find("{")
                end_idx = synthesis.rfind("}") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    synthesis = json.loads(synthesis[start_idx:end_idx])
                else:
                    synthesis = {
                        "executive_summary": synthesis[:500],
                        "recommendation": "HOLD",
                        "confidence": "MEDIUM",
                    }
            except json.JSONDecodeError:
                synthesis = {
                    "executive_summary": synthesis[:500],
                    "recommendation": "HOLD",
                    "confidence": "MEDIUM",
                }

        # Extract technical data
        tech_data = technical.get("data", {}) if isinstance(technical, dict) else {}
        trend = tech_data.get("trend", {})
        sr = tech_data.get("support_resistance", {})

        # Extract fundamental data
        fund_data = fundamental.get("data", {}) if isinstance(fundamental, dict) else {}

        # Extract price from market data, technical, or valuation result
        current_price = None
        if market_data and isinstance(market_data, dict):
            md = market_data.get("data", {})
            if md:
                current_price = md.get("current_price") or md.get("close")
        if not current_price and trend:
            current_price = trend.get("current_price")
        if not current_price and fund_data:
            current_price = fund_data.get("current_price")

        # Calculate scores (convert to 0-100 scale)
        overall = synthesis.get("composite_score", 50)
        if overall > 10:  # Already in 0-100 scale
            pass
        else:  # Convert from 0-10 scale
            overall = overall * 10

        individual = synthesis.get("individual_scores") or {}
        fund_overall = fund_data.get("overall_score", 50) if fund_data else 50
        tech_overall = tech_data.get("overall_score", 50) if tech_data else 50
        fundamental_score = individual.get("fundamental", fund_overall) or fund_overall
        technical_score = individual.get("technical", tech_overall) or tech_overall

        # Normalize scores
        if fundamental_score <= 10:
            fundamental_score = fundamental_score * 10
        if technical_score <= 10:
            technical_score = technical_score * 10

        # Extract support/resistance levels
        sr = sr or {}
        support_levels = sr.get("support_levels") or {}
        resistance_levels = sr.get("resistance_levels") or {}
        support = support_levels.get("support_1")
        resistance = resistance_levels.get("resistance_1")

        # Extract market context for regime info
        market_context = context.get("market_context", {})
        macro_data = context.get("macro_data", {})
        peer_data = context.get("peer_data") or {}

        # Build market regime data
        market_regime = {}
        if market_context:
            market_regime["regime"] = market_context.get("market_regime", "normal")
        if macro_data and macro_data.get("status") == "success":
            vol = macro_data.get("volatility", {})
            if vol:
                market_regime["vix"] = vol.get("vix")
            treasury = macro_data.get("treasury", {})
            if treasury:
                market_regime["yield_curve_slope"] = treasury.get("yield_curve_slope")

        # Ensure all dict vars are never None
        synthesis = synthesis or {}
        fund_data = fund_data or {}
        tech_data = tech_data or {}
        trend = trend or {}
        sr = sr or {}

        # Build report data with all sections
        report_data = {
            "symbol": symbol,
            "recommendation": synthesis.get("recommendation", "HOLD"),
            "confidence": synthesis.get("confidence", "MEDIUM"),
            "overall_score": overall,
            "fundamental_score": fundamental_score,
            "technical_score": technical_score,
            "current_price": current_price,
            "target_price": synthesis.get("price_target") or resistance,
            "stop_loss": synthesis.get("stop_loss") or support,
            "investment_thesis": synthesis.get("executive_summary", ""),
            "key_catalysts": synthesis.get("key_catalysts") or [],
            "key_risks": synthesis.get("key_risks") or [],
            "time_horizon": synthesis.get("time_horizon", "MEDIUM-TERM"),
            "position_size": synthesis.get("position_size", "MODERATE"),
            "technical_strength": synthesis.get("technical_strength", "NEUTRAL"),
            "valuation_summary": synthesis.get("valuation_summary", ""),
            "valuation_models": fund_data.get("models") or {},
            "technical_data": {
                "overall_signal": trend.get("overall_signal", "neutral"),
                "signal_percentages": trend.get("signal_percentages") or {},
                "support_resistance": sr,
                "momentum": tech_data.get("momentum") or {},
            },
            "market_regime": market_regime,
            "peer_comparison": {
                "peers": peer_data.get("peers", []),
                "metrics": peer_data.get("peer_metrics", {}),
                "summary": synthesis.get("peer_comparison_summary", ""),
            },
            "fundamental_analysis_thinking": synthesis.get("fundamental_analysis_thinking", ""),
            "technical_analysis_thinking": synthesis.get("technical_analysis_thinking", ""),
            "key_technical_signals": synthesis.get("key_technical_signals", []),
            "risk_factors_detailed": synthesis.get("risk_factors_detailed", []),
            "score_breakdown": synthesis.get("score_breakdown", {}),
            "reasoning": synthesis.get("reasoning", ""),
            "financial_metrics": self._build_financial_metrics(fund_data, context),
            "historical_financials": self._build_historical_financials(fund_data, context),
        }

        # Get output directory

        from investigator.config import get_config

        cfg = get_config()
        output_dir = cfg.reports_dir / "professional"

        generator = ProfessionalReportGenerator(output_dir=output_dir)
        report_path = generator.generate_report(report_data)

        return {"path": str(report_path), "status": "success"}, 0

    def _build_financial_metrics(self, fund_data: dict, context) -> dict:
        """Build financial metrics dashboard data: company vs sector comparison.

        Returns metrics dict.
        """
        metrics: dict[str, Any] = {}

        # Extract company metrics from fundamental data
        if not fund_data:
            return metrics

        # Get valuation metrics
        valuation = fund_data.get("valuation") or {}
        if valuation:
            if "pe_ratio" in valuation:
                metrics["pe_ratio"] = {
                    "company": valuation.get("pe_ratio"),
                    "sector": valuation.get("sector_pe_median"),
                }
            if "ev_ebitda" in valuation:
                metrics["ev_ebitda"] = {
                    "company": valuation.get("ev_ebitda"),
                    "sector": valuation.get("sector_ev_ebitda_median"),
                }

        # Get profitability metrics
        profitability = fund_data.get("profitability") or {}
        if profitability:
            if "roe" in profitability:
                metrics["roe"] = {
                    "company": profitability.get("roe"),
                    "sector": profitability.get("sector_roe_median"),
                }
            if "fcf_margin" in profitability:
                metrics["fcf_margin"] = {
                    "company": profitability.get("fcf_margin"),
                    "sector": profitability.get("sector_fcf_margin_median"),
                }

        # Get growth metrics
        growth = fund_data.get("growth") or {}
        if growth:
            if "revenue_growth" in growth:
                metrics["revenue_growth"] = {
                    "company": growth.get("revenue_growth"),
                    "sector": growth.get("sector_revenue_growth_median"),
                }

        # Get leverage metrics
        leverage = fund_data.get("leverage") or fund_data.get("balance_sheet") or {}
        if leverage:
            if "debt_to_equity" in leverage:
                metrics["debt_to_equity"] = {
                    "company": leverage.get("debt_to_equity"),
                    "sector": leverage.get("sector_debt_to_equity_median"),
                }

        # Try to get from SEC filing data as fallback
        sec_data = context.get("sec_data") if context else None
        if sec_data and isinstance(sec_data, dict):
            filing_data = sec_data.get("data", sec_data)
            ratios = filing_data.get("financial_ratios") or {}
            if ratios:
                if "pe_ratio" not in metrics and "pe_ratio" in ratios:
                    metrics["pe_ratio"] = {
                        "company": ratios.get("pe_ratio"),
                        "sector": None,
                    }
                if "roe" not in metrics and "roe" in ratios:
                    metrics["roe"] = {"company": ratios.get("roe"), "sector": None}

        return metrics

    def _build_historical_financials(self, fund_data: dict, context) -> dict:
        """Build historical financials for trend charts.

        Returns historical data dict.
        """
        historical = {}

        # Try SEC filing data for historical metrics
        sec_data = context.get("sec_data") if context else None
        if sec_data and isinstance(sec_data, dict):
            filing_data = sec_data.get("data", sec_data)

            # Revenue history
            revenue_history = filing_data.get("revenue_history") or filing_data.get("historical_revenue")
            if revenue_history and isinstance(revenue_history, list):
                historical["revenue"] = revenue_history

            # FCF history
            fcf_history = filing_data.get("fcf_history") or filing_data.get("historical_fcf")
            if fcf_history and isinstance(fcf_history, list):
                historical["free_cash_flow"] = fcf_history

            # ROE history
            roe_history = filing_data.get("roe_history") or filing_data.get("historical_roe")
            if roe_history and isinstance(roe_history, list):
                historical["roe"] = roe_history

        # Extract from income statement if available
        income = fund_data.get("income_statement") or {}
        if income and "annual" in income:
            annual = income["annual"]
            if isinstance(annual, list):
                revenue_points = []
                for year_data in annual:
                    year = year_data.get("fiscal_year") or year_data.get("year")
                    rev = year_data.get("revenue") or year_data.get("total_revenue")
                    if year and rev:
                        revenue_points.append((year, rev))
                if revenue_points and "revenue" not in historical:
                    historical["revenue"] = revenue_points

        # Extract from cash flow statement if available
        cashflow = fund_data.get("cash_flow_statement") or {}
        if cashflow and "annual" in cashflow:
            annual = cashflow["annual"]
            if isinstance(annual, list):
                fcf_points = []
                for year_data in annual:
                    year = year_data.get("fiscal_year") or year_data.get("year")
                    fcf = year_data.get("free_cash_flow") or year_data.get("fcf")
                    if year and fcf:
                        fcf_points.append((year, fcf))
                if fcf_points and "free_cash_flow" not in historical:
                    historical["free_cash_flow"] = fcf_points

        return historical


# =============================================================================
# Peer Comparison Handlers
# =============================================================================


@handler_decorator("identify_peers", vertical="investment", description="Identify peer companies")
@dataclass
class IdentifyPeersHandler(BaseHandler):
    """Identify peer companies for comparison with valuation metrics.

    Uses industry-first matching strategy:
    1. Find peers matching both sector AND industry (highest quality)
    2. If <5 matches, add sector-only matches
    3. Sort by market cap (largest first)
    4. Fetch recent valuation metrics for each peer
    5. Return up to 5 peers with valuation data
    """

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute peer identification.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from sqlalchemy import text

        from investigator.infrastructure.database.db import get_database_engine

        symbol = context.get("symbol", "")
        peer_data = context.get("peer_data") or {}
        if isinstance(peer_data, dict) and peer_data.get("peers"):
            return {
                "peers": peer_data.get("peers", []),
                "peer_metrics": peer_data.get("peer_metrics", {}),
            }, 0

        market_context = context.get("market_context") or {}
        sector = market_context.get("sector")
        industry = market_context.get("industry")

        peers = []

        if sector or industry:
            engine = get_database_engine()
            with engine.connect() as conn:
                # First: Get peers with EXACT industry match + recent valuation metrics
                if industry:
                    result = conn.execute(
                        text("""
                            SELECT DISTINCT ON (s.symbol)
                                s.symbol, s.name, s.market_cap, s.industry, s.sector,
                                v.pe_fair_value, v.ps_fair_value, v.blended_fair_value,
                                v.current_price, v.predicted_upside_pct,
                                v.context_features->>'pe_level' as pe_ratio,
                                v.context_features->>'revenue_growth' as revenue_growth,
                                v.context_features->>'fcf_margin' as fcf_margin,
                                v.analysis_date
                            FROM symbols s
                            LEFT JOIN LATERAL (
                                SELECT * FROM valuation_outcomes vo
                                WHERE vo.symbol = s.symbol
                                ORDER BY vo.analysis_date DESC
                                LIMIT 1
                            ) v ON true
                            WHERE s.industry = :industry
                            AND s.symbol != :target
                            AND s.is_active = true
                            ORDER BY s.symbol, v.analysis_date DESC NULLS LAST, s.market_cap DESC NULLS LAST
                            LIMIT 5
                        """),
                        {"industry": industry, "target": symbol},
                    )
                    for row in result:
                        pe_ratio = None
                        if row[10]:
                            try:
                                pe_ratio = float(row[10])
                            except (ValueError, TypeError):
                                pass
                        peers.append(
                            {
                                "symbol": row[0],
                                "name": row[1],
                                "market_cap": float(row[2]) if row[2] else None,
                                "industry": row[3],
                                "sector": row[4],
                                "match_type": "industry",
                                "valuation": {
                                    "pe_fair_value": float(row[5]) if row[5] else None,
                                    "ps_fair_value": float(row[6]) if row[6] else None,
                                    "blended_fair_value": float(row[7]) if row[7] else None,
                                    "current_price": float(row[8]) if row[8] else None,
                                    "upside_pct": float(row[9]) if row[9] else None,
                                    "pe_ratio": pe_ratio,
                                    "revenue_growth": float(row[11]) if row[11] else None,
                                    "fcf_margin": float(row[12]) if row[12] else None,
                                },
                                "analysis_date": str(row[13]) if row[13] else None,
                            }
                        )

                # If <5 industry matches, add sector matches
                if len(peers) < 5 and sector:
                    existing_symbols = {p["symbol"] for p in peers}
                    remaining_slots = 5 - len(peers)

                    result = conn.execute(
                        text("""
                            SELECT DISTINCT ON (s.symbol)
                                s.symbol, s.name, s.market_cap, s.industry, s.sector,
                                v.pe_fair_value, v.ps_fair_value, v.blended_fair_value,
                                v.current_price, v.predicted_upside_pct,
                                v.context_features->>'pe_level' as pe_ratio,
                                v.context_features->>'revenue_growth' as revenue_growth,
                                v.context_features->>'fcf_margin' as fcf_margin,
                                v.analysis_date
                            FROM symbols s
                            LEFT JOIN LATERAL (
                                SELECT * FROM valuation_outcomes vo
                                WHERE vo.symbol = s.symbol
                                ORDER BY vo.analysis_date DESC
                                LIMIT 1
                            ) v ON true
                            WHERE s.sector = :sector
                            AND s.symbol != :target
                            AND s.is_active = true
                            ORDER BY s.symbol, v.analysis_date DESC NULLS LAST, s.market_cap DESC NULLS LAST
                            LIMIT :limit
                        """),
                        {
                            "sector": sector,
                            "target": symbol,
                            "limit": remaining_slots + 10,
                        },
                    )
                    for row in result:
                        if row[0] not in existing_symbols and len(peers) < 5:
                            pe_ratio = None
                            if row[10]:
                                try:
                                    pe_ratio = float(row[10])
                                except (ValueError, TypeError):
                                    pass
                            peers.append(
                                {
                                    "symbol": row[0],
                                    "name": row[1],
                                    "market_cap": float(row[2]) if row[2] else None,
                                    "industry": row[3],
                                    "sector": row[4],
                                    "match_type": "sector",
                                    "valuation": {
                                        "pe_fair_value": float(row[5]) if row[5] else None,
                                        "ps_fair_value": float(row[6]) if row[6] else None,
                                        "blended_fair_value": float(row[7]) if row[7] else None,
                                        "current_price": float(row[8]) if row[8] else None,
                                        "upside_pct": float(row[9]) if row[9] else None,
                                        "pe_ratio": pe_ratio,
                                        "revenue_growth": float(row[11]) if row[11] else None,
                                        "fcf_margin": float(row[12]) if row[12] else None,
                                    },
                                    "analysis_date": str(row[13]) if row[13] else None,
                                }
                            )

        # Calculate peer group medians for comparison
        peer_metrics = self._calculate_peer_medians(peers)

        return {"peers": peers, "peer_metrics": peer_metrics}, 0

    def _calculate_peer_medians(self, peers: list[dict]) -> dict:
        """Calculate median valuation metrics across peer group.

        Returns metrics dict.
        """
        import statistics

        if not peers:
            return {}

        metrics: dict[str, list] = {
            "pe_ratio": [],
            "revenue_growth": [],
            "fcf_margin": [],
            "upside_pct": [],
        }

        for peer in peers:
            val = peer.get("valuation") or {}
            if val.get("pe_ratio") is not None:
                metrics["pe_ratio"].append(val["pe_ratio"])
            if val.get("revenue_growth") is not None:
                metrics["revenue_growth"].append(val["revenue_growth"])
            if val.get("fcf_margin") is not None:
                metrics["fcf_margin"].append(val["fcf_margin"])
            if val.get("upside_pct") is not None:
                metrics["upside_pct"].append(val["upside_pct"])

        result = {
            "count": len(peers),
            "industry_matches": sum(1 for p in peers if p.get("match_type") == "industry"),
            "sector_matches": sum(1 for p in peers if p.get("match_type") == "sector"),
        }

        for key, values in metrics.items():
            if values:
                result[f"{key}_median"] = statistics.median(values)
                result[f"{key}_min"] = min(values)
                result[f"{key}_max"] = max(values)

        return result


@handler_decorator("analyze_peers", vertical="investment", description="Analyze peer companies")
@dataclass
class AnalyzePeersHandler(BaseHandler):
    """Analyze peer companies."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute peer analysis.

        Returns:
            Tuple of (peer_analyses_list, tool_calls_count)
        """
        peer_data = context.get("peer_data")
        if isinstance(peer_data, dict) and peer_data.get("peers"):
            peers = peer_data.get("peers", [])
        else:
            peers = context.get("peer_list", [])

        if not peers:
            return [], 0

        import asyncio

        from victor_invest.workflows import AnalysisMode, run_yaml_analysis

        async def analyze_one(peer):
            symbol = peer.get("symbol") if isinstance(peer, dict) else peer
            try:
                result = await run_yaml_analysis(str(symbol), AnalysisMode.QUICK)
                return {
                    "symbol": symbol,
                    "composite_score": result.synthesis.get("composite_score", 50) if result.synthesis else 50,
                    "status": "success",
                }
            except Exception as e:
                return {"symbol": symbol, "status": "error", "error": str(e)}

        tasks = [analyze_one(p) for p in peers[:5]]
        peer_analyses = await asyncio.gather(*tasks)

        return peer_analyses, 0


# =============================================================================
# RL Backtest Handlers
# =============================================================================


@handler_decorator(
    "generate_lookback_dates",
    vertical="investment",
    description="Generate lookback dates",
)
@dataclass
class GenerateLookbackDatesHandler(BaseHandler):
    """Generate lookback dates for RL backtesting."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute lookback date generation.

        Returns:
            Tuple of (lookback_dates_list, tool_calls_count)
        """
        from victor_invest.workflows.rl_backtest import generate_lookback_list

        max_months = context.get("max_lookback_months", 120)
        interval = context.get("interval", "quarterly")

        lookback_dates = generate_lookback_list(max_months, interval)

        return lookback_dates, 0


@handler_decorator(
    "process_backtest_batch",
    vertical="investment",
    description="Process backtest batch",
)
@dataclass
class ProcessBacktestBatchHandler(BaseHandler):
    """Process a batch of backtest dates for RL training."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute backtest batch processing.

        Returns:
            Tuple of (backtest_results_dict, tool_calls_count)
        """
        from victor_invest.workflows.rl_backtest import run_rl_backtest

        symbol = context.get("symbol")
        lookback_dates = context.get("lookback_dates", [])
        interval = context.get("interval", "quarterly")

        if not symbol:
            raise ValueError("No symbol provided")

        result = await run_rl_backtest(
            symbol=symbol,
            lookback_months_list=lookback_dates,
            interval=interval,
            use_yaml_workflow=False,
        )

        return result.to_dict(), 0


@handler_decorator("save_rl_predictions", vertical="investment", description="Save RL predictions")
@dataclass
class SaveRLPredictionsHandler(BaseHandler):
    """Save RL predictions to database."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute RL predictions save.

        Returns:
            Tuple of (summary_dict, tool_calls_count)
        """
        backtest_results = context.get("backtest_results", {})

        # The predictions are already saved during run_rl_backtest
        # This handler just returns the summary
        predictions = backtest_results.get("predictions", [])
        metadata = backtest_results.get("metadata", {})

        output = {
            "predictions_count": len(predictions),
            "summary": metadata.get("summary", {}),
        }

        return output, 0


# =============================================================================
# Helper Functions (No Migration Needed)
# =============================================================================


def _format_fundamental(fundamental: dict) -> str:
    """Format fundamental data for prompt with comprehensive SEC details.

    Returns formatted string.
    """
    if not fundamental or fundamental.get("status") == "error":
        return "Fundamental data not available."

    data = fundamental.get("data", {})
    if not data:
        return "Fundamental data not available."

    parts = []

    # Current price and consensus
    current_price = data.get("current_price")
    consensus_fv = data.get("consensus_fair_value")
    consensus_upside = data.get("consensus_upside")

    if current_price:
        parts.append(f"- Current Price: ${current_price:.2f}")
    if consensus_fv:
        parts.append(f"- Blended Fair Value: ${consensus_fv:.2f}")
    if consensus_upside:
        parts.append(f"- Upside/Downside: {consensus_upside:+.1f}%")

    # SEC Financial Metrics (if available)
    sec_data = data.get("sec_data", {})
    if sec_data:
        parts.append("\n### SEC Financial Metrics:")

        # Income Statement
        revenue = sec_data.get("revenue")
        revenue_growth = sec_data.get("revenue_growth")
        gross_margin = sec_data.get("gross_margin")
        operating_margin = sec_data.get("operating_margin")
        net_margin = sec_data.get("net_margin")
        net_income = sec_data.get("net_income")
        eps = sec_data.get("eps")
        eps_diluted = sec_data.get("eps_diluted")

        if revenue:
            parts.append(f"- Revenue: ${revenue:,.0f}M" if revenue < 1000 else f"- Revenue: ${revenue / 1000:.2f}B")
            if revenue_growth:
                parts.append(f"  - YoY Growth: {revenue_growth:.1f}%")
        if gross_margin:
            parts.append(f"- Gross Margin: {gross_margin:.1f}%")
        if operating_margin:
            parts.append(f"- Operating Margin: {operating_margin:.1f}%")
        if net_margin:
            parts.append(f"- Net Margin: {net_margin:.1f}%")
        if net_income:
            parts.append(
                f"- Net Income: ${net_income:,.0f}M"
                if net_income < 1000
                else f"- Net Income: ${net_income / 1000:.2f}B"
            )
        if eps_diluted:
            parts.append(f"- EPS (Diluted): ${eps_diluted:.2f}")

        # Balance Sheet
        total_assets = sec_data.get("total_assets")
        total_debt = sec_data.get("total_debt")
        cash_equivalents = sec_data.get("cash_equivalents")
        current_ratio = sec_data.get("current_ratio")
        debt_to_equity = sec_data.get("debt_to_equity")
        book_value_per_share = sec_data.get("book_value_per_share")

        if total_assets or total_debt or cash_equivalents:
            parts.append("\n### Balance Sheet:")
        if cash_equivalents:
            parts.append(
                f"- Cash & Equivalents: ${cash_equivalents:,.0f}M"
                if cash_equivalents < 1000
                else f"- Cash & Equivalents: ${cash_equivalents / 1000:.2f}B"
            )
        if total_debt:
            parts.append(
                f"- Total Debt: ${total_debt:,.0f}M"
                if total_debt < 1000
                else f"- Total Debt: ${total_debt / 1000:.2f}B"
            )
        if debt_to_equity:
            parts.append(f"- Debt-to-Equity: {debt_to_equity:.2f}")
        if current_ratio:
            parts.append(f"- Current Ratio: {current_ratio:.2f}")
        if book_value_per_share:
            parts.append(f"- Book Value/Share: ${book_value_per_share:.2f}")

        # Cash Flow
        operating_cash_flow = sec_data.get("operating_cash_flow")
        free_cash_flow = sec_data.get("free_cash_flow")
        capex = sec_data.get("capital_expenditure")

        if operating_cash_flow or free_cash_flow:
            parts.append("\n### Cash Flow:")
        if operating_cash_flow:
            parts.append(
                f"- Operating Cash Flow: ${operating_cash_flow:,.0f}M"
                if operating_cash_flow < 1000
                else f"- Operating Cash Flow: ${operating_cash_flow / 1000:.2f}B"
            )
        if free_cash_flow:
            parts.append(
                f"- Free Cash Flow: ${free_cash_flow:,.0f}M"
                if free_cash_flow < 1000
                else f"- Free Cash Flow: ${free_cash_flow / 1000:.2f}B"
            )
        if capex:
            parts.append(
                f"- Capital Expenditure: ${capex:,.0f}M"
                if capex < 1000
                else f"- Capital Expenditure: ${capex / 1000:.2f}B"
            )

        # Returns
        roe = sec_data.get("return_on_equity")
        roa = sec_data.get("return_on_assets")
        roic = sec_data.get("return_on_invested_capital")

        if roe or roa or roic:
            parts.append("\n### Returns:")
        if roe:
            parts.append(f"- Return on Equity: {roe:.1f}%")
        if roa:
            parts.append(f"- Return on Assets: {roa:.1f}%")
        if roic:
            parts.append(f"- Return on Invested Capital: {roic:.1f}%")

    # Individual valuation models
    models = data.get("models", {})
    if models:
        parts.append("\n### Valuation Models:")
        for model_name, model_data in models.items():
            if isinstance(model_data, dict):
                fv = model_data.get("fair_value_per_share")
                upside = model_data.get("upside_percent")
                confidence = model_data.get("confidence")
                if fv:
                    conf_str = f" (Confidence: {confidence:.0f}%)" if confidence else ""
                    upside_str = f" [{upside:+.1f}%]" if upside else ""
                    parts.append(f"  - {model_name.upper()}: ${fv:.2f}{upside_str}{conf_str}")

                    # Add model-specific details
                    if model_name == "dcf":
                        # Get WACC and terminal growth from assumptions (already percentages: 13.0 for 13%)
                        wacc = model_data.get("assumptions", {}).get("wacc")
                        tgr = model_data.get("assumptions", {}).get("terminal_growth_rate")
                        if wacc:
                            parts.append(f"    WACC: {wacc:.1f}%, Terminal Growth: {(tgr if tgr else 2.0):.1f}%")
                    elif model_name == "pe":
                        pe_ratio = model_data.get("pe_ratio")
                        sector_pe = model_data.get("sector_pe")
                        eps = model_data.get("eps_ttm")
                        if pe_ratio and eps:
                            parts.append(
                                f"    TTM EPS: ${eps:.2f}, Target P/E: {pe_ratio:.1f}x (Sector Median: {sector_pe:.1f}x)"
                            )
                    elif model_name == "ps":
                        ps_ratio = model_data.get("ps_ratio")
                        sector_ps = model_data.get("sector_ps")
                        rps = model_data.get("revenue_per_share")
                        if ps_ratio and rps:
                            parts.append(
                                f"    Revenue/Share: ${rps:.2f}, Target P/S: {ps_ratio:.1f}x (Sector: {sector_ps:.1f}x)"
                            )
                    elif model_name == "ev_ebitda":
                        ev_ebitda = model_data.get("ev_ebitda")
                        sector_ev_ebitda = model_data.get("sector_ev_ebitda")
                        ebitda = model_data.get("ebitda")
                        if ev_ebitda and ebitda:
                            parts.append(
                                f"    EV/EBITDA: {ev_ebitda:.1f}x (Sector Median: {sector_ev_ebitda:.1f}x), TTM EBITDA: ${ebitda / 1000:.2f}B"
                                if ebitda > 1000
                                else f"    EV/EBITDA: {ev_ebitda:.1f}x, TTM EBITDA: ${ebitda:.2f}M"
                            )

    # Models applied
    models_applied = data.get("models_applied", [])
    if models_applied:
        parts.append(f"\n- Models Applied: {', '.join([m.upper() for m in models_applied])}")

    return "\n".join(parts) if parts else "Fundamental data not available."


def _format_quarterly_trends_and_filings(fundamental: dict) -> str:
    """Format quarterly trends and recent SEC filings for LLM analysis.

    Provides the LLM with concrete quarterly numbers to:
    - Spot trends in revenue, FCF, EPS, margins
    - Evaluate growth acceleration/deceleration
    - Analyze cash flow quality
    - Review recent management guidance vs actuals

    Returns formatted string.
    """
    if not fundamental or fundamental.get("status") != "success":
        return "Quarterly trends not available."

    data = fundamental.get("data", {})
    if not data:
        return "Quarterly trends not available."

    parts = []

    # Get quarterly metrics from SEC data
    sec_data = data.get("sec_data", {})
    quarterly_metrics = sec_data.get("quarterly_metrics", [])

    if quarterly_metrics and len(quarterly_metrics) > 0:
        # Sort by period_end date descending (most recent first)
        sorted_quarters = sorted(quarterly_metrics, key=lambda x: x.get("period_end", ""), reverse=True)

        # Take last 8 quarters
        recent_quarters = sorted_quarters[:8]

        parts.append("### Quarterly Performance (Last 8 Quarters):")
        parts.append("")
        parts.append(
            "| Period | Period End | Revenue | Revenue Growth | FCF | EPS (Diluted) | GM% | OM% | NM% | FCF Margin |"
        )
        parts.append(
            "|--------|------------|---------|----------------|-----|---------------|-----|-----|-----|------------|"
        )

        for q in recent_quarters:
            period = q.get("fiscal_period", "N/A")
            period_end = q.get("period_end_date", "N/A")

            # Format metrics (revenue is in raw dollars, convert to billions/millions)
            revenue = q.get("revenue")
            rev_str = ""
            if revenue:
                rev_b = revenue / 1_000_000_000
                rev_m = revenue / 1_000_000
                rev_str = f"${rev_b:.2f}B" if rev_b >= 1 else f"${rev_m:.0f}M"

            # Calculate revenue growth vs prior quarter
            rev_growth = q.get("revenue_growth_yoy")
            rev_growth_str = "N/A"
            if rev_growth is not None:
                rev_growth_str = f"{rev_growth:+.1f}%"

            fcf = q.get("free_cash_flow")
            fcf_str = ""
            if fcf:
                fcf_b = fcf / 1_000_000_000
                fcf_m = fcf / 1_000_000
                fcf_str = f"${fcf_b:.2f}B" if fcf_b >= 1 else f"${fcf_m:.0f}M"

            eps = q.get("earnings_per_share_diluted")
            eps_str = ""
            if eps:
                eps_str = f"${eps:.2f}"

            gm = q.get("gross_margin")
            om = q.get("operating_margin")
            nm = q.get("net_margin")
            fcf_margin = q.get("fcf_margin")

            # Calculate FCF margin if not provided
            if fcf_margin is None and revenue and fcf:
                fcf_margin = (fcf / revenue) * 100 if revenue else 0

            gm_str = f"{gm:.1f}%" if gm else "N/A"
            om_str = f"{om:.1f}%" if om else "N/A"
            nm_str = f"{nm:.1f}%" if nm else "N/A"
            fcfm_str = f"{fcf_margin:.1f}%" if fcf_margin else "N/A"

            parts.append(
                f"| {period} | {period_end} | {rev_str} | {rev_growth_str} | {fcf_str} | {eps_str} | {gm_str} | {om_str} | {nm_str} | {fcfm_str} |"
            )

        parts.append("")
        parts.append("**Key Observations for Analysis:**")
        parts.append("- Review revenue growth trajectory (accelerating vs decelerating)")
        parts.append("- Analyze FCF generation quality and consistency")
        parts.append("- Evaluate margin expansion or contraction")
        parts.append("- Compare EPS growth vs revenue growth (operational leverage)")
        parts.append("")

    # Recent SEC filings
    recent_filings = sec_data.get("recent_filings", [])
    if recent_filings:
        parts.append("### Recent SEC Filings:")
        parts.append("")

        for filing in recent_filings[:10]:  # Last 10 filings
            form_type = filing.get("form", "N/A")
            filed_date = filing.get("filed_date", "N/A")
            period_end = filing.get("period_end", "N/A")

            filing_desc = form_type
            if form_type == "10-K":
                filing_desc = "10-K (Annual Report)"
            elif form_type == "10-Q":
                filing_desc = "10-Q (Quarterly Report)"
            elif form_type == "8-K":
                filing_desc = "8-K (Current Report)"

            parts.append(f"- **{filing_desc}**")
            if filed_date:
                parts.append(f"  - Filed: {filed_date}")
            if period_end and period_end != "N/A":
                parts.append(f"  - Period End: {period_end}")
            parts.append("")

    # Forward guidance if available
    guidance = sec_data.get("forward_guidance", {})
    if guidance:
        parts.append("### Forward Guidance:")

        revenue_guidance = guidance.get("revenue_guidance")
        margin_guidance = guidance.get("margin_guidance")
        capex_guidance = guidance.get("capex_guidance")

        if revenue_guidance:
            parts.append(f"- Revenue Guidance: {revenue_guidance}")
        if margin_guidance:
            parts.append(f"- Margin Guidance: {margin_guidance}")
        if capex_guidance:
            parts.append(f"- CapEx Guidance: {capex_guidance}")
        parts.append("")

    return "\n".join(parts) if parts else "Quarterly trends not available."


def _format_technical(technical: dict) -> str:
    """Format technical data for prompt with multi-tier (weekly + daily) analysis.

    Returns formatted string.
    """
    if not technical or technical.get("status") != "success":
        return "Technical data not available."

    parts = []

    # Multi-tier summary (new data structure)
    summary = technical.get("summary", {})
    if summary:
        strategic_trend = summary.get("strategic_trend")
        tactical_signal = summary.get("tactical_signal")
        overall_bias = summary.get("overall_bias")

        parts.append("### Multi-Tier Technical Analysis:")
        if strategic_trend:
            parts.append(f"- Strategic Trend (Weekly): {strategic_trend.upper()}")
        if tactical_signal:
            parts.append(f"- Tactical Signal (Daily): {tactical_signal.upper()}")
        if overall_bias:
            parts.append(f"- Overall Bias: {overall_bias.upper().replace('_', ' ')}")

    # Weekly strategic data (for long-term trend)
    weekly = technical.get("weekly")
    if weekly:
        latest_weekly = weekly.get("latest", {})
        if latest_weekly:
            weekly_price = latest_weekly.get("price", {})
            weekly_ma = latest_weekly.get("moving_averages", {})

            parts.append("\n### Weekly Strategic Indicators (2-Year Trend):")
            if weekly_price.get("close"):
                parts.append(f"- Current Weekly Price: ${weekly_price['close']:.2f}")

            # Weekly moving averages (slower, more significant)
            weekly_sma_50 = weekly_ma.get("sma_50")
            weekly_sma_200 = weekly_ma.get("sma_200")
            current_price = weekly_price.get("close")

            if weekly_sma_50 and current_price:
                diff_pct = ((current_price - weekly_sma_50) / weekly_sma_50) * 100
                parts.append(f"- 50-Week SMA: ${weekly_sma_50:.2f} ({diff_pct:+.1f}%)")

            if weekly_sma_200 and current_price:
                diff_pct = ((current_price - weekly_sma_200) / weekly_sma_200) * 100
                parts.append(f"- 200-Week SMA: ${weekly_sma_200:.2f} ({diff_pct:+.1f}%)")

            # Weekly trend (Golden/Death cross)
            if weekly_sma_50 and weekly_sma_200:
                if weekly_sma_50 > weekly_sma_200:
                    parts.append("- Weekly Trend: BULLISH (50-week above 200-week)")
                else:
                    parts.append("- Weekly Trend: BEARISH (50-week below 200-week)")

    # Daily tactical data (for entry/exit zones)
    daily = technical.get("daily")
    if daily:
        latest_daily = daily.get("latest", {})
        if latest_daily:
            daily_price = latest_daily.get("price", {})
            daily_momentum = latest_daily.get("momentum", {})
            daily_levels = latest_daily.get("levels", {})

            parts.append("\n### Daily Tactical Indicators (Entry/Exit Zones):")

            current_price = daily_price.get("close")
            if current_price:
                parts.append(f"- Current Daily Price: ${current_price:.2f}")

            # Key levels (support/resistance)
            support_1 = daily_levels.get("support_1")
            resistance_1 = daily_levels.get("resistance_1")
            high_52w = daily_levels.get("high_52w")
            low_52w = daily_levels.get("low_52w")

            if support_1:
                parts.append(f"- Near-term Support: ${support_1:.2f}")
            if resistance_1:
                parts.append(f"- Near-term Resistance: ${resistance_1:.2f}")
            if high_52w and low_52w:
                parts.append(f"- 52-Week Range: ${low_52w:.2f} - ${high_52w:.2f}")
                if current_price:
                    pct_range = ((current_price - low_52w) / (high_52w - low_52w)) * 100
                    parts.append(f"- Position in 52W Range: {pct_range:.0f}%")

            # Momentum indicators (daily)
            rsi = daily_momentum.get("rsi_14")
            macd = daily_momentum.get("macd")
            macd_signal = daily_momentum.get("macd_signal")

            if rsi is not None:
                rsi_signal = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
                parts.append(f"- RSI(14): {rsi:.1f} ({rsi_signal})")

            if macd is not None and macd_signal is not None:
                macd_trend = "BULLISH" if macd > macd_signal else "BEARISH"
                parts.append(f"- MACD: {macd_trend} (MACD {'>' if macd > macd_signal else '<'} Signal)")

    return "\n".join(parts) if parts else "Technical data not available."


# =============================================================================
# Sector Multiples Handlers
# =============================================================================


@handler_decorator(
    "refresh_sector_multiples",
    vertical="investment",
    description="Refresh sector/industry valuation multiples from database",
)
@dataclass
class RefreshSectorMultiplesHandler(BaseHandler):
    """Refresh current sector multiples from database data."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute sector multiples refresh.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.sector_multiples import SectorMultiplesTool

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}

        tool = SectorMultiplesTool()
        result = await tool.execute(
            action="refresh",
            sectors=params.get("sectors"),
            industries=params.get("industries"),
            min_samples=params.get("min_samples", 10),
            exclude_outliers=params.get("exclude_outliers", True),
            update_config=params.get("update_config", True),
            dry_run=params.get("dry_run", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "historical_sector_multiples",
    vertical="investment",
    description="Calculate historical sector multiples for a fiscal year",
)
@dataclass
class HistoricalSectorMultiplesHandler(BaseHandler):
    """Calculate historical sector multiples for a specific fiscal year."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute historical sector multiples calculation.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.sector_multiples import SectorMultiplesTool

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}
        fiscal_year = params.get("fiscal_year") or context.get("fiscal_year")

        if not fiscal_year:
            return {
                "status": "error",
                "error": "fiscal_year is required",
                "data": None,
            }, 0

        tool = SectorMultiplesTool()
        result = await tool.execute(
            action="historical",
            fiscal_year=fiscal_year,
            sectors=params.get("sectors"),
            industries=params.get("industries"),
            min_samples=params.get("min_samples", 5),
            exclude_outliers=params.get("exclude_outliers", True),
            store=params.get("store", True),
            export=params.get("export"),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "sector_multiples_timeline",
    vertical="investment",
    description="Display sector multiples timeline matrix",
)
@dataclass
class SectorMultiplesTimelineHandler(BaseHandler):
    """Display sector/industry multiples timeline table."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute sector multiples timeline.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.sector_multiples import SectorMultiplesTool

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}

        tool = SectorMultiplesTool()
        result = await tool.execute(
            action="timeline",
            sectors=params.get("sectors", "Technology"),
            industries=params.get("industries"),
            years=params.get("years", "5"),
            metric=params.get("metric", "all"),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "sector_multiples_trend",
    vertical="investment",
    description="View historical trend for a sector/industry",
)
@dataclass
class SectorMultiplesTrendHandler(BaseHandler):
    """View historical trend for a sector or industry."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute sector multiples trend.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.sector_multiples import SectorMultiplesTool

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}
        group_name = params.get("group_name") or context.get("group_name")

        if not group_name:
            return {
                "status": "error",
                "error": "group_name is required",
                "data": None,
            }, 0

        tool = SectorMultiplesTool()
        result = await tool.execute(
            action="trend",
            group_name=group_name,
            group_type=params.get("group_type", "sector"),
            start_year=params.get("start_year"),
            end_year=params.get("end_year"),
            export=params.get("export"),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "sector_multiples_trend_adjusted",
    vertical="investment",
    description="Calculate trend-adjusted sector multiples for robust valuations",
)
@dataclass
class SectorMultiplesTrendAdjustedHandler(BaseHandler):
    """Calculate trend-adjusted sector multiples for robust valuations."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute trend-adjusted sector multiples calculation.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.sector_multiples import SectorMultiplesTool

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}

        tool = SectorMultiplesTool()
        result = await tool.execute(
            action="trend_adjusted",
            sectors=params.get("sectors"),
            industries=params.get("industries"),
            min_samples=params.get("min_samples", 10),
            exclude_outliers=params.get("exclude_outliers", True),
            lookback_years=params.get("lookback_years", 5),
            adjustment_sensitivity=params.get("adjustment_sensitivity", "medium"),
            update_trend_config=params.get("update_trend_config", False),
            dry_run=params.get("dry_run", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "calculate_fair_multiple",
    vertical="investment",
    description="Calculate company-specific fair value multiples using trend-adjusted sector and company premium history",
)
@dataclass
class CalculateFairMultipleHandler(BaseHandler):
    """Calculate company-specific fair value multiples."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute fair multiple calculation.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.fair_multiple_calculator import (
            FairMultipleCalculatorTool,
        )

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}
        symbol = params.get("symbol") or context.get("symbol")
        sector = params.get("sector") or context.get("sector")

        if not symbol or not sector:
            return {
                "status": "error",
                "error": "symbol and sector are required",
                "data": None,
            }, 0

        tool = FairMultipleCalculatorTool()
        result = await tool.execute(
            action="calculate",
            symbol=symbol,
            sector=sector,
            industry=params.get("industry"),
            metric=params.get("metric", "all"),
            lookback_years=params.get("lookback_years", 5),
            conservative=params.get("conservative", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "generate_fair_value_report",
    vertical="investment",
    description="Generate comprehensive fair value report with multiple valuation methods",
)
@dataclass
class GenerateFairValueReportHandler(BaseHandler):
    """Generate comprehensive fair value report."""

    async def execute(
        self,
        node: ComputeNode,
        context: WorkflowContext,
        tool_registry: ToolRegistry,
    ) -> tuple[Any, int]:
        """Execute fair value report generation.

        Returns:
            Tuple of (output_dict, tool_calls_count)
        """
        from victor_invest.tools.fair_multiple_calculator import (
            FairMultipleCalculatorTool,
        )

        # Get parameters from node config or context
        params = node.params if hasattr(node, "params") else {}
        symbol = params.get("symbol") or context.get("symbol")
        sector = params.get("sector") or context.get("sector")

        if not symbol or not sector:
            return {
                "status": "error",
                "error": "symbol and sector are required",
                "data": None,
            }, 0

        tool = FairMultipleCalculatorTool()
        result = await tool.execute(
            action="report",
            symbol=symbol,
            sector=sector,
            industry=params.get("industry"),
            current_price=params.get("current_price"),
            eps=params.get("eps"),
            revenue_per_share=params.get("revenue_per_share"),
            book_value_per_share=params.get("book_value_per_share"),
            lookback_years=params.get("lookback_years", 5),
            conservative=params.get("conservative", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "robust_valuation_analyze",
    vertical="investment",
    description="Perform comprehensive robust valuation analysis combining all 3 layers",
)
@dataclass
class RobustValuationAnalyzeHandler(BaseHandler):
    """Handler for comprehensive robust valuation analysis.

    Combines Layer 1 (trend-adjusted sector multiples), Layer 2 (company premium history),
    and Layer 3 (peer comparison) for robust fair value estimation.
    """

    async def execute(
        self, node: ComputeNode, context: dict[str, Any], tool_registry: Any
    ) -> tuple[dict[str, Any], int]:
        """Execute robust valuation analysis.

        Expected node.params:
            symbol: Stock symbol (optional, uses context if not provided)
            sector: Sector name (optional, uses context if not provided)
            industry: Industry name (optional)
            lookback_years: Years of historical data (default: 5)
            conservative: Use conservative adjustments (default: false)

        Returns:
            Dict with status, data (valuation result), or error
        """
        from victor_invest.tools.robust_valuation import RobustValuationTool

        params = node.params or {}
        symbol = params.get("symbol") or context.get("symbol", "")
        sector = params.get("sector") or context.get("sector", "")

        if not symbol or not sector:
            return {
                "status": "error",
                "error": "symbol and sector are required",
                "data": None,
            }, 0

        tool = RobustValuationTool()
        result = await tool.execute(
            action="analyze",
            symbol=symbol,
            sector=sector,
            industry=params.get("industry"),
            lookback_years=params.get("lookback_years", 5),
            conservative=params.get("conservative", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "peer_compare_analysis",
    vertical="investment",
    description="Compare company valuation multiples to industry peers",
)
@dataclass
class PeerCompareAnalysisHandler(BaseHandler):
    """Handler for peer comparison analysis.

    Compares company's valuation multiples (P/E, P/S, P/B, EV/EBITDA) to
    industry peers with percentile ranking and relative valuation status.
    """

    async def execute(
        self, node: ComputeNode, context: dict[str, Any], tool_registry: Any
    ) -> tuple[dict[str, Any], int]:
        """Execute peer comparison analysis.

        Expected node.params:
            symbol: Stock symbol (optional, uses context if not provided)
            sector: Sector name (optional, uses context if not provided)
            industry: Industry name (optional, uses context if not provided)
            metric: "pe", "ps", "pb", "ev_ebitda", or "all" (default: "all")
            min_peers: Minimum number of peers required (default: 3)

        Returns:
            Dict with status, data (peer comparison), or error
        """
        from victor_invest.tools.robust_valuation import RobustValuationTool

        params = node.params or {}
        symbol = params.get("symbol") or context.get("symbol", "")
        sector = params.get("sector") or context.get("sector", "")
        industry = params.get("industry") or context.get("industry")

        if not symbol:
            return {
                "status": "error",
                "error": "symbol is required",
                "data": None,
            }, 0

        tool = RobustValuationTool()
        result = await tool.execute(
            action="peer_compare",
            symbol=symbol,
            sector=sector,
            industry=industry,
            metric=params.get("metric", "all"),
            min_peers=params.get("min_peers", 3),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


@handler_decorator(
    "generate_robust_valuation_report",
    vertical="investment",
    description="Generate comprehensive robust valuation report with fair value estimate",
)
@dataclass
class GenerateRobustValuationReportHandler(BaseHandler):
    """Handler for comprehensive robust valuation report generation.

    Generates full report including all 3 layers, fair value estimate,
    recommendation, and confidence level.
    """

    async def execute(
        self, node: ComputeNode, context: dict[str, Any], tool_registry: Any
    ) -> tuple[dict[str, Any], int]:
        """Execute robust valuation report generation.

        Expected node.params:
            symbol: Stock symbol (optional, uses context if not provided)
            sector: Sector name (optional, uses context if not provided)
            industry: Industry name (optional, uses context if not provided)
            current_price: Current stock price (for upside/downside calculation)
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share
            lookback_years: Years of historical data (default: 5)
            conservative: Use conservative adjustments (default: false)

        Returns:
            Dict with status, data (comprehensive report), or error
        """
        from victor_invest.tools.robust_valuation import RobustValuationTool

        params = node.params or {}
        symbol = params.get("symbol") or context.get("symbol", "")
        sector = params.get("sector") or context.get("sector", "")

        if not symbol or not sector:
            return {
                "status": "error",
                "error": "symbol and sector are required",
                "data": None,
            }, 0

        tool = RobustValuationTool()
        result = await tool.execute(
            action="report",
            symbol=symbol,
            sector=sector,
            industry=params.get("industry"),
            current_price=params.get("current_price"),
            eps=params.get("eps"),
            revenue_per_share=params.get("revenue_per_share"),
            book_value_per_share=params.get("book_value_per_share"),
            lookback_years=params.get("lookback_years", 5),
            conservative=params.get("conservative", False),
        )

        return {
            "status": "success" if result.success else "error",
            "data": result.output if result.success else None,
            "error": result.error if not result.success else None,
        }, 0


# =============================================================================
# Registration (No-op for backward compatibility)
# =============================================================================


def register_handlers() -> None:
    """Register Investment handlers with the workflow executor.

    This is a no-op function for backward compatibility.
    Handlers are auto-registered via @handler_decorator on module import.
    """


__all__ = [
    # Data collection handlers
    "FetchSECDataHandler",
    "FetchMarketDataHandler",
    "FetchMacroDataHandler",
    # Analysis handlers
    "RunFundamentalAnalysisHandler",
    "RunTechnicalAnalysisHandler",
    "RunMarketContextHandler",
    # Synthesis handlers
    "RunSynthesisHandler",
    # Report generation
    "GenerateReportHandler",
    # Peer comparison
    "IdentifyPeersHandler",
    "AnalyzePeersHandler",
    # RL backtest
    "GenerateLookbackDatesHandler",
    "ProcessBacktestBatchHandler",
    "SaveRLPredictionsHandler",
    # Sector multiples
    "RefreshSectorMultiplesHandler",
    "HistoricalSectorMultiplesHandler",
    "SectorMultiplesTimelineHandler",
    "SectorMultiplesTrendHandler",
    "SectorMultiplesTrendAdjustedHandler",
    # Fair multiple calculator
    "CalculateFairMultipleHandler",
    "GenerateFairValueReportHandler",
    # Robust valuation
    "RobustValuationAnalyzeHandler",
    "PeerCompareAnalysisHandler",
    "GenerateRobustValuationReportHandler",
    # Helper functions
    "_format_fundamental",
    "_format_technical",
    # Registration
    "register_handlers",
]
