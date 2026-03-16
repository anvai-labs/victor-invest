import json

from investigator.application.synthesizer_context import (
    DEFAULT_MARKET_ENVIRONMENT_CONTEXT,
    UNKNOWN_SECTOR_CONTEXT,
    create_financial_trends_analysis,
    extract_financial_metrics_from_quarter,
    extract_quarterly_trends,
    get_market_environment_context,
    get_sector_context,
)


def test_extract_quarterly_trends_summarizes_available_quarters():
    quarterly_analyses = [
        {"period": "2025-Q1", "form_type": "10-Q"},
        {"period": "2025-Q2", "form_type": "10-Q"},
    ]

    result = extract_quarterly_trends(quarterly_analyses)

    assert "Quarterly Analysis Summary (2 quarters)" in result
    assert "- 2025-Q1 (10-Q)" in result
    assert "- 2025-Q2 (10-Q)" in result


def test_extract_financial_metrics_from_quarter_normalizes_common_keys():
    quarter_data = {
        "revenues": 1250,
        "earnings": 110,
        "profit_margin": 13.2,
        "eps": 1.45,
        "total_debt": 400,
    }

    result = extract_financial_metrics_from_quarter(quarter_data, "2025-Q2")

    assert result == {
        "period": "2025-Q2",
        "revenue": 1250,
        "net_income": 110,
        "profit_margin": 13.2,
        "eps": 1.45,
        "total_debt": 400,
    }


def test_create_financial_trends_analysis_formats_growth_and_progression():
    metrics_by_quarter = [
        {"period": "2024-Q4", "revenue": 1000, "profit_margin": 10.0},
        {"period": "2025-Q1", "revenue": 1100, "profit_margin": 11.0},
        {"period": "2025-Q2", "revenue": 1200, "profit_margin": 12.0},
    ]

    result = create_financial_trends_analysis(metrics_by_quarter)

    assert "📊 FINANCIAL TRENDS ANALYSIS (3 quarters):" in result
    assert "📈 Revenue Trend: +20.0% over 3 quarters" in result
    assert "💰 Margin Trend: +2.0pp change in profit margin" in result
    assert "2025-Q2: Revenue $1,200M, Margin 12.0%" in result


def test_get_sector_context_uses_specific_mapping_and_default(tmp_path):
    sector_mapping = {
        "sector_mappings": {
            "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
        },
        "default_mapping": {"sector": "Unknown", "industry": "Unclassified"},
    }
    (tmp_path / "sector_mapping.json").write_text(json.dumps(sector_mapping), encoding="utf-8")

    specific = get_sector_context("AAPL", tmp_path)
    fallback = get_sector_context("MSFT", tmp_path)

    assert specific == "Technology - Consumer Electronics"
    assert fallback == "Unknown - Unclassified"


def test_get_sector_context_returns_unknown_when_mapping_missing(tmp_path):
    assert get_sector_context("AAPL", tmp_path) == UNKNOWN_SECTOR_CONTEXT


def test_get_market_environment_context_returns_default_summary():
    assert get_market_environment_context() == DEFAULT_MARKET_ENVIRONMENT_CONTEXT
