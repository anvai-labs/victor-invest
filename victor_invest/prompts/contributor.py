"""Investment Prompt Contributor — task hints and prompt extensions.

Registers investment-specific task type hints and system prompt sections
with the framework via the victor.prompt_contributors entry point.
"""

from typing import Dict, List, Optional

from victor_contracts.verticals import PromptContributorProtocol, TaskTypeHint

INVESTMENT_TASK_TYPE_HINTS: Dict[str, TaskTypeHint] = {
    "equity_analysis": TaskTypeHint(
        task_type="equity_analysis",
        hint="""[EQUITY ANALYSIS] Institutional-grade stock analysis:
1. Pull SEC filings (10-K, 10-Q) for financial data
2. Run multi-model valuation (DCF, P/E, P/S, P/B, GGM, EV/EBITDA)
3. Compute technical indicators for entry/exit timing
4. Assess market context (sector, macro, regime)
5. Synthesize into investment thesis with price target""",
        tool_budget=25,
        priority_tools=["sec_filing", "valuation", "technical_indicators", "market_data"],
    ),
    "quick_screen": TaskTypeHint(
        task_type="quick_screen",
        hint="""[QUICK SCREEN] Rapid technical assessment (~5 seconds):
1. Fetch recent price data
2. Compute key technical indicators
3. Generate entry/exit signals
4. Provide brief assessment""",
        tool_budget=8,
        priority_tools=["market_data", "technical_indicators", "entry_exit_signals"],
    ),
    "peer_comparison": TaskTypeHint(
        task_type="peer_comparison",
        hint="""[PEER COMPARISON] Compare against industry peers:
1. Identify peer group by sector/market cap
2. Pull comparative financials
3. Compute relative valuation multiples
4. Rank on key metrics (growth, margin, valuation)""",
        tool_budget=20,
        priority_tools=["sec_filing", "valuation", "market_data"],
    ),
    "risk_assessment": TaskTypeHint(
        task_type="risk_assessment",
        hint="""[RISK ASSESSMENT] Comprehensive risk analysis:
1. Analyze financial health (debt ratios, cash flow)
2. Check insider trading patterns
3. Review institutional holdings trends
4. Assess credit risk indicators
5. Evaluate market regime exposure""",
        tool_budget=18,
        priority_tools=["sec_filing", "market_data", "valuation"],
    ),
}


class InvestmentPromptContributor(PromptContributorProtocol):
    """Contributes investment-specific task hints to the system prompt."""

    def get_task_type_hints(self) -> Dict[str, TaskTypeHint]:
        """Return investment task type hints for tool budget guidance."""
        return INVESTMENT_TASK_TYPE_HINTS

    def get_system_prompt_sections(self) -> List[str]:
        """Return additional system prompt sections for investment context."""
        return [
            "When analyzing investments, always cite specific financial metrics "
            "and data sources. Provide explicit confidence levels for price targets "
            "and clearly separate factual analysis from forward-looking projections.",
        ]

    def get_grounding_addendum(self) -> Optional[str]:
        """Return investment-specific grounding rules."""
        return (
            "INVESTMENT GROUNDING: All financial data must come from SEC filings "
            "or verified market data sources. Never fabricate financial figures. "
            "Distinguish between historical data and projections. Include standard "
            "disclaimers for forward-looking statements."
        )
