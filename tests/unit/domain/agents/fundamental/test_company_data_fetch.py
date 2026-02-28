"""Unit tests for company-data fetch helper functions."""

from unittest.mock import MagicMock

import pytest

from investigator.domain.agents.fundamental.company_data_fetch import (
    build_company_cache_key,
    build_company_data_payload,
    build_financial_statements_from_processed,
    cache_company_data_payload,
    get_cached_company_data,
    resolve_cik_for_symbol,
    validate_financial_statements,
)
from investigator.infrastructure.cache.cache_types import CacheType


def test_resolve_cik_for_symbol_handles_failures():
    mapper = MagicMock()
    mapper.resolve_cik.side_effect = RuntimeError("not found")
    cik = resolve_cik_for_symbol(
        symbol="AAPL", ticker_mapper=mapper, logger=MagicMock()
    )
    assert cik is None


def test_build_company_cache_key_includes_cik_when_present():
    with_cik = build_company_cache_key(
        symbol="AAPL", fiscal_period="2025-Q1", cik="0000320193"
    )
    without_cik = build_company_cache_key(
        symbol="AAPL", fiscal_period="2025-Q1", cik=None
    )
    assert with_cik == {
        "symbol": "AAPL",
        "fiscal_period": "2025-Q1",
        "cik": "0000320193",
    }
    assert without_cik == {"symbol": "AAPL", "fiscal_period": "2025-Q1"}


def test_get_cached_company_data_requires_financials():
    cache = MagicMock()
    key = {"symbol": "AAPL", "fiscal_period": "2025-Q1"}
    cache.get.return_value = {"financials": {"revenues": 100}}
    cached = get_cached_company_data(
        cache=cache, cache_key=key, symbol="AAPL", logger=MagicMock()
    )
    assert cached is not None

    cache.get.return_value = {"financials": {}}
    cached = get_cached_company_data(
        cache=cache, cache_key=key, symbol="AAPL", logger=MagicMock()
    )
    assert cached is None


def test_build_financial_statements_from_processed_maps_short_term_debt_fallback():
    statements = build_financial_statements_from_processed(
        financial_metrics={
            "revenues": 10.0,
            "assets": 20.0,
            "equity": 5.0,
            "liabilities": 15.0,
            "total_debt": 8.0,
            "long_term_debt": 6.0,
            "cash_and_equivalents": 3.0,
            "weighted_average_diluted_shares_outstanding": 2.0,
        },
        financial_ratios={"current_ratio": 1.5},
        data_source="clean_architecture",
        derive_short_term_debt=lambda _metrics: 2.0,
    )
    assert statements["short_term_debt"] == 2.0
    assert statements["cash"] == 3.0
    assert statements["shares_outstanding"] == 2.0
    assert statements["data_source"] == "clean_architecture"


def test_validate_financial_statements_raises_clear_error():
    with pytest.raises(ValueError) as exc:
        validate_financial_statements(financial_statements={}, symbol="MSFT", cik=None)
    assert "CIK=not found" in str(exc.value)


def test_cache_company_data_payload_stores_when_facts_exist():
    cache = MagicMock()
    payload = build_company_data_payload(
        symbol="AAPL",
        cik="0000320193",
        company_facts={"revenues": 100},
        financial_statements={"revenues": 100},
        market_data={"current_price": 10},
        fiscal_period_label="2025-Q1",
    )
    cache_company_data_payload(
        cache=cache,
        cache_key={"symbol": "AAPL", "fiscal_period": "2025-Q1"},
        company_data=payload,
        company_facts={"revenues": 100},
        symbol="AAPL",
        cik="0000320193",
        logger=MagicMock(),
    )
    cache.set.assert_called_once()
    args, _kwargs = cache.set.call_args
    assert args[0] == CacheType.COMPANY_FACTS
