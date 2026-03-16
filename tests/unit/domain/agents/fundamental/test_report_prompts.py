from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.report_prompts import (
    build_forecast_prompt,
    build_fundamental_report_data_section,
    build_fundamental_report_prompt,
    build_fundamental_report_system_prompt,
)


def test_build_forecast_prompt_includes_key_sections():
    prompt = build_forecast_prompt(
        data_quality={
            "quality_grade": "Good",
            "data_quality_score": 82,
            "assessment": "Mostly complete",
            "core_metrics_populated": 12,
            "consistency_issues": ["None"],
        },
        trend_context="Trend Context Block",
        historical_financials={"revenue": [1, 2, 3]},
        growth_analysis={"growth_score": 75},
        safe_fmt_pct=lambda value: f"{value}%",
    )

    assert "Generate financial forecasts" in prompt
    assert "Trend Context Block" in prompt
    assert '"growth_score": 75' in prompt
    assert "confidence_intervals" in prompt


def test_build_fundamental_report_data_section_uses_toon_when_available():
    analysis_data = {
        "quarterly_data": [{"period": "Q1", "revenue": 10}],
        "other": "value",
    }

    result = build_fundamental_report_data_section(
        analysis_data=analysis_data,
        symbol="AAPL",
        use_toon=True,
        to_toon_quarterly=lambda rows: f"TOON({len(rows)})",
        logger=MagicMock(),
    )

    assert result.startswith("TOON(1)")
    assert "Additional Analysis" in result
    assert '"other": "value"' in result


def test_build_fundamental_report_data_section_falls_back_to_json_on_toon_error():
    logger = MagicMock()
    analysis_data = {"quarterly_data": [{"period": "Q1"}], "other": "value"}

    result = build_fundamental_report_data_section(
        analysis_data=analysis_data,
        symbol="AAPL",
        use_toon=True,
        to_toon_quarterly=lambda _rows: (_ for _ in ()).throw(RuntimeError("boom")),
        logger=logger,
    )

    assert '"quarterly_data"' in result
    logger.warning.assert_called_once()


def test_build_fundamental_report_prompt_includes_quality_confidence_and_schema():
    prompt = build_fundamental_report_prompt(
        data_quality={
            "quality_grade": "Good",
            "data_quality_score": 80,
            "assessment": "Solid coverage",
            "core_metrics_populated": 10,
            "market_metrics_populated": 6,
            "ratio_metrics_populated": 8,
            "consistency_issues": [],
            "extraction_quality": 70,
            "quality_improvement": 10.5,
            "enhancement_summary": "Enriched from processed data",
        },
        confidence={
            "confidence_level": "HIGH",
            "confidence_score": 88,
            "rationale": "Coverage is strong",
            "quality_grade": "Good",
        },
        data_section="DATA BLOCK",
        safe_fmt_pct=lambda value: f"{value}%",
        safe_fmt_float=lambda value, digits: f"{value:.{digits}f}",
    )

    assert "Synthesize a comprehensive fundamental analysis report" in prompt
    assert "DATA BLOCK" in prompt
    assert "Investment Recommendation" in prompt
    assert '"investment_recommendation": "buy"' in prompt


def test_build_fundamental_report_system_prompt_appends_toon_explanation_only_when_enabled():
    enabled = build_fundamental_report_system_prompt(
        use_toon=True,
        has_quarterly_data=True,
        toon_format_explanation="TOON FORMAT",
    )
    disabled = build_fundamental_report_system_prompt(
        use_toon=False,
        has_quarterly_data=True,
        toon_format_explanation="TOON FORMAT",
    )

    assert "TOON FORMAT" in enabled
    assert "TOON FORMAT" not in disabled
