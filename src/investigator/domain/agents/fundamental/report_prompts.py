"""Prompt-building helpers extracted from FundamentalAnalysisAgent."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def build_forecast_prompt(
    *,
    data_quality: dict[str, Any],
    trend_context: str,
    historical_financials: dict[str, Any],
    growth_analysis: dict[str, Any],
    safe_fmt_pct: Callable[[Any], str],
) -> str:
    """Build the LLM prompt for forward revenue/earnings/cash-flow forecasting."""
    return f"""
        Generate financial forecasts based on historical data and growth analysis:

        DATA QUALITY ASSESSMENT:
        - Overall Quality: {data_quality.get("quality_grade", "Unknown")} ({safe_fmt_pct(data_quality.get("data_quality_score", 0))})
        - {data_quality.get("assessment", "Data quality information not available")}
        - Core Metrics: {data_quality.get("core_metrics_populated", "N/A")} populated
        - Consistency Issues: {", ".join(data_quality.get("consistency_issues", [])) or "None detected"}
        {trend_context}

        Historical Financials:
        {json.dumps(historical_financials, indent=2)}

        Growth Analysis:
        {json.dumps(growth_analysis, indent=2)}

        Provide forecasts for next 3 years:
        1. Revenue forecast (with growth rates)
        2. Earnings forecast
        3. Free cash flow forecast
        4. Margin projections
        5. Key assumptions
        6. Scenario analysis (base/bull/bear)
        7. Confidence intervals

        Be realistic and consider industry trends.

        IMPORTANT: Consider the data quality assessment when determining confidence levels.
        If data quality is below 75%, flag this in your analysis and adjust confidence accordingly.
        Lower confidence should result in wider confidence intervals.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return a JSON object that strictly follows the schema below (values are illustrative):
        {{
          "revenue_forecast": [
            {{ "year": 2026, "revenue": 110, "growth_rate": 0.10 }},
            {{ "year": 2027, "revenue": 121, "growth_rate": 0.10 }},
            {{ "year": 2028, "revenue": 133, "growth_rate": 0.10 }}
          ],
          "earnings_forecast": [
            {{ "year": 2026, "eps": 5.50 }},
            {{ "year": 2027, "eps": 6.05 }},
            {{ "year": 2028, "eps": 6.65 }}
          ],
          "free_cash_flow_forecast": [
            {{ "year": 2026, "fcf": 15 }},
            {{ "year": 2027, "fcf": 18 }},
            {{ "year": 2028, "fcf": 21 }}
          ],
          "margin_projections": {{
            "gross_margin": 0.45,
            "operating_margin": 0.25,
            "net_margin": 0.15
          }},
          "key_assumptions": [
            "Market growth of 5% per year",
            "Stable competitive landscape",
            "No major economic downturns"
          ],
          "scenario_analysis": {{
            "base_case": {{ "revenue_growth": 0.10, "eps": 6.65 }},
            "bull_case": {{ "revenue_growth": 0.15, "eps": 7.50 }},
            "bear_case": {{ "revenue_growth": 0.05, "eps": 5.80 }}
          }},
          "confidence_intervals": {{
            "revenue_2028": [125, 140],
            "eps_2028": [6.50, 7.00]
          }}
        }}
        """


def build_fundamental_report_data_section(
    *,
    analysis_data: dict[str, Any],
    symbol: str,
    use_toon: bool,
    to_toon_quarterly: Callable[[list[dict[str, Any]]], str],
    logger: Any | None = None,
) -> str:
    """Build the data section for the fundamental report prompt, optionally using TOON format."""
    if not use_toon:
        return json.dumps(analysis_data, indent=2)[:10000]

    quarterly_data = analysis_data.get("quarterly_data", [])
    if not quarterly_data or not isinstance(quarterly_data, list):
        return json.dumps(analysis_data, indent=2)[:10000]

    try:
        quarterly_dicts = []
        for quarter in quarterly_data:
            if hasattr(quarter, "__dict__"):
                quarterly_dicts.append(vars(quarter))
            elif isinstance(quarter, dict):
                quarterly_dicts.append(quarter)

        if quarterly_dicts:
            toon_quarterly = to_toon_quarterly(quarterly_dicts)
            remaining_data = {key: value for key, value in analysis_data.items() if key != "quarterly_data"}
            return f"{toon_quarterly}\n\nAdditional Analysis:\n{json.dumps(remaining_data, indent=2)[:8000]}"
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Failed to convert quarterly data to TOON for {symbol}: {exc}")

    return json.dumps(analysis_data, indent=2)[:10000]


def build_fundamental_report_prompt(
    *,
    data_quality: dict[str, Any],
    confidence: dict[str, Any],
    data_section: str,
    safe_fmt_pct: Callable[[Any], str],
    safe_fmt_float: Callable[[Any, int], str],
) -> str:
    """Build the LLM prompt for the final fundamental report synthesis."""
    return f"""
        Synthesize a comprehensive fundamental analysis report:

        DATA QUALITY ASSESSMENT:
        - Overall Quality: {data_quality.get("quality_grade", "Unknown")} ({safe_fmt_pct(data_quality.get("data_quality_score", 0))})
        - {data_quality.get("assessment", "Data quality information not available")}
        - Core Metrics: {data_quality.get("core_metrics_populated", "N/A")} populated
        - Market Data: {data_quality.get("market_metrics_populated", "N/A")} populated
        - Ratio Metrics: {data_quality.get("ratio_metrics_populated", "N/A")} populated
        - Consistency Issues: {", ".join(data_quality.get("consistency_issues", [])) or "None detected"}

        DATA ENRICHMENT IMPACT (FEATURE #3):
        - Raw Extraction Quality: {safe_fmt_pct(data_quality.get("extraction_quality", 0))}
        - Enhanced Quality (after enrichment): {safe_fmt_pct(data_quality.get("data_quality_score", 0))}
        - Quality Improvement: +{safe_fmt_float(data_quality.get("quality_improvement", 0), 1)} points
        - Enhancement Summary: {data_quality.get("enhancement_summary", "N/A")}

        ANALYSIS CONFIDENCE LEVEL:
        - Confidence: {confidence.get("confidence_level", "UNKNOWN")} ({confidence.get("confidence_score", 0)}/100)
        - Rationale: {confidence.get("rationale", "No confidence assessment available")}
        - Based on Data Quality: {confidence.get("quality_grade", "Unknown")} quality data

        {data_section}

        Create a structured investment report with:
        1. Executive Summary
        2. Investment Thesis
        3. Financial Analysis Summary
        4. Valuation Assessment
        5. Growth Prospects
        6. Risk Analysis
        7. Competitive Position
        8. Investment Grade (AAA to D)
        9. Price Target (12-month)
        10. Investment Recommendation (strong buy/buy/hold/sell/strong sell)
        11. Key Catalysts
        12. Key Risks

        Provide clear, actionable insights for investors.

        IMPORTANT: The data quality assessment above should influence your confidence levels.
        - If data quality is Excellent/Good (≥75%): High confidence in analysis
        - If data quality is Fair (60-75%): Moderate confidence, note data limitations
        - If data quality is Poor/Very Poor (<60%): Low confidence, significant data concerns

        Adjust your investment recommendation strength and price target confidence based on data quality.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return a JSON object that strictly follows the schema below (values are illustrative):
        {{
          "executive_summary": "The company is a market leader with strong growth prospects and a wide economic moat. The stock is currently undervalued and offers an attractive risk/reward profile.",
          "investment_thesis": "The company is well-positioned to benefit from the secular growth in its industry. Its strong brand, network effects, and high switching costs provide a sustainable competitive advantage.",
          "financial_analysis_summary": "The company has a strong financial profile, with a history of consistent revenue growth, expanding margins, and strong cash flow generation.",
          "valuation_assessment": "The stock is currently trading at a discount to its intrinsic value, with a potential upside of 20% to our fair value estimate of $150.",
          "growth_prospects": "The company has multiple growth drivers, including new product launches, expansion into new markets, and strategic acquisitions.",
          "risk_analysis": "The main risks to our thesis are increased competition, regulatory changes, and a slowdown in the overall economy.",
          "competitive_position": "The company has a strong competitive position, with a dominant market share and a wide economic moat.",
          "investment_grade": "A",
          "price_target": 150.00,
          "investment_recommendation": "buy",
          "key_catalysts": [
            "Successful launch of new products",
            "Expansion into new geographic markets"
          ],
          "key_risks": [
            "Increased competition",
            "Regulatory changes"
          ]
        }}
        """


def build_fundamental_report_system_prompt(
    *,
    use_toon: bool,
    has_quarterly_data: bool,
    toon_format_explanation: str,
) -> str:
    """Build the system prompt for fundamental report synthesis."""
    system_prompt = "You are a senior equity analyst providing investment recommendations."
    if use_toon and has_quarterly_data:
        system_prompt += "\n\n" + toon_format_explanation
    return system_prompt
