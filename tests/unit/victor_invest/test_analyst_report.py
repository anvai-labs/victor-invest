"""Tests for the analyst-report package (schema/builder/scoring/markdown/tool)."""

import asyncio

from victor_invest.reporting import build_analyst_report, render_markdown
from victor_invest.reporting import scoring
from victor_invest.reporting.financial_health import compute_quality_flags
from victor_invest.tools.analyst_report import AnalystReportTool


def _sample_state():
    return {
        "symbol": "AAPL",
        "mode": "comprehensive",
        "llm_provider": "ollama",
        "llm_model": "gpt-oss:20b",
        "synthesis": {
            "synthesis_method": "rule_based",
            "executive_summary": "Strong franchise with fair upside.",
            "individual_scores": {"fundamental": 78, "technical": 62},
            "key_catalysts": ["Services growth", "Buybacks"],
            "key_risks": ["China demand", "Regulatory pressure"],
            "score_breakdown": {"cash_flow": 80, "value": 55, "balance_sheet": 72},
            "fundamental_analysis_thinking": "DCF implies upside.",
            "technical_analysis_thinking": "Uptrend intact.",
        },
        "fundamental_analysis": {
            "data": {
                "current_price": 200.0,
                "consensus_fair_value": 240.0,
                "consensus_upside": 20.0,
                "tier_classification": "balanced",
                "model_agreement_score": 0.8,
                "divergence_flag": False,
                "models": {
                    "dcf": {
                        "fair_value_per_share": 250.0,
                        "upside_percent": 25.0,
                        "weight": 40,
                        "wacc": 0.09,
                        "terminal_growth_rate": 0.025,
                    },
                    "pe": {"fair_value_per_share": 230.0, "upside_percent": 15.0, "weight": 35, "pe_ratio": 28.0},
                    "ggm": {"fair_value_per_share": 210.0, "upside_percent": 5.0, "weight": 25},
                },
            }
        },
        "technical_analysis": {
            "daily": {
                "latest": {
                    "price": {"close": 200.0},
                    "moving_averages": {"sma_20": 198, "sma_50": 190, "sma_200": 175},
                    "momentum": {"rsi_14": 58.3, "macd": 1.2, "macd_signal": 0.9, "macd_histogram": 0.3},
                    "volatility": {"bb_upper": 210, "bb_lower": 188, "atr_14": 3.5},
                    "volume": {"obv": 1.2e9, "vwap": 199.4},
                    "levels": {
                        "support_1": 192,
                        "resistance_1": 208,
                        "pivot_point": 200,
                        "high_52w": 215,
                        "low_52w": 160,
                        "fib_38_2": 194,
                        "fib_50_0": 188,
                        "fib_61_8": 182,
                    },
                }
            },
            "summary": {"overall_bias": "bullish", "strategic_trend": "up", "tactical_signal": "buy"},
        },
        "errors": [],
    }


# ---------------------------------------------------------------- scoring rubric
def test_composite_score_uses_canonical_weights():
    # 0.6 * 80 + 0.4 * 60 = 72
    assert scoring.composite_score(80, 60) == 72.0


def test_composite_score_treats_missing_as_neutral():
    assert scoring.composite_score(None, None) == 50.0


def test_derive_rating_thresholds_and_override():
    assert scoring.derive_rating(75, None) == ("BUY", "MEDIUM")
    assert scoring.derive_rating(50, None) == ("HOLD", "MEDIUM")
    assert scoring.derive_rating(30, None) == ("SELL", "MEDIUM")
    # decisive upside forces BUY regardless of a low score
    assert scoring.derive_rating(30, 25.0) == ("BUY", "HIGH")
    assert scoring.derive_rating(90, -25.0) == ("SELL", "HIGH")


def test_derive_price_target_precedence():
    assert scoring.derive_price_target(240.0, 230.0, 208.0) == 240.0
    assert scoring.derive_price_target(None, 230.0, 208.0) == 230.0
    assert scoring.derive_price_target(None, None, 208.0) == 208.0
    assert scoring.derive_price_target(None, None, None) is None


# ---------------------------------------------------------------- builder
def test_builder_assembles_rating_valuation_scenarios():
    report = build_analyst_report(_sample_state(), data_as_of="2026-06-14")

    assert report.symbol == "AAPL"
    # composite = 0.6*78 + 0.4*62 = 71.6 -> with +20% upside override -> BUY/HIGH
    assert report.rating.composite_score == 71.6
    assert report.rating.action == "BUY"
    assert report.rating.price_target == 240.0
    assert report.rating.upside_pct == 20.0

    v = report.valuation
    assert v.fair_value_low == 210.0
    assert v.fair_value_high == 250.0
    assert v.margin_of_safety_pct == 16.7  # (240-200)/240*100
    assert {m.model for m in v.models} == {"dcf", "pe", "ggm"}

    # probability-weighted target = 0.25*250 + 0.5*240 + 0.25*210 = 235
    assert report.scenarios.probability_weighted_target == 235.0
    assert [s.name for s in report.scenarios.scenarios] == ["Bull", "Base", "Bear"]

    assert report.catalysts == ["Services growth", "Buybacks"]
    assert [r.description for r in report.risks] == ["China demand", "Regulatory pressure"]
    assert report.provenance is not None
    assert report.provenance.workflow_mode == "comprehensive"


def test_builder_handles_empty_state_gracefully():
    report = build_analyst_report({"symbol": "ZZZ"})
    assert report.symbol == "ZZZ"
    assert report.rating.composite_score == 50.0  # neutral
    assert report.scenarios.scenarios == []
    assert report.valuation.models == []


# ---------------------------------------------------------------- markdown
def test_markdown_contains_core_sections():
    md = render_markdown(build_analyst_report(_sample_state(), data_as_of="2026-06-14"))
    for marker in (
        "# AAPL",
        "## Rating",
        "## Valuation",
        "## Scenario Analysis",
        "## Technical Setup",
        "## Financial-Health Screens",
        "RSI(14)",
        "Fibonacci",
        "_Provenance_",
    ):
        assert marker in md, f"missing section: {marker}"


# ---------------------------------------------------------------- financial health
def test_compute_quality_flags_from_fundamentals():
    metrics = {
        "total_assets": 350_000,
        "current_assets": 130_000,
        "current_liabilities": 120_000,
        "total_liabilities": 280_000,
        "stockholders_equity": 70_000,
        "retained_earnings": 5_000,
        "total_revenue": 390_000,
        "operating_income": 110_000,
        "net_income": 95_000,
        "gross_profit": 170_000,
        "operating_cash_flow": 110_000,
        "total_debt": 110_000,
        "long_term_debt": 95_000,
        "shares_outstanding": 15_000,
    }
    flags = compute_quality_flags("AAPL", metrics, market_cap=3_000_000)
    # Altman should compute with market_cap backfilling X4.
    assert flags.altman_z is not None
    # Piotroski needs a prior period for several signals but should not raise.
    assert isinstance(flags.warnings, list)


def test_compute_quality_flags_no_metrics():
    flags = compute_quality_flags("AAPL", None)
    assert flags.altman_z is None
    assert any("No fundamentals" in w for w in flags.warnings)


# ---------------------------------------------------------------- tool
def test_analyst_report_tool_returns_report_and_markdown():
    tool = AnalystReportTool()
    result = asyncio.run(tool.execute(state=_sample_state(), as_of="2026-06-14"))
    assert result.success is True
    assert result.output["report"]["symbol"] == "AAPL"
    assert "## Valuation" in result.output["markdown"]


def test_analyst_report_tool_requires_state():
    tool = AnalystReportTool()
    result = asyncio.run(tool.execute(state=None))
    assert result.success is False
    assert "state" in (result.error or "")
