import logging

import pytest

from investigator.infrastructure.sec.data_strategy import SECDataStrategy


@pytest.fixture(autouse=True)
def _reset_stale_warning_cache():
    SECDataStrategy._stale_warning_symbols.clear()
    yield
    SECDataStrategy._stale_warning_symbols.clear()


def test_stale_bulk_warning_logged_once_per_symbol(caplog):
    strategy = SECDataStrategy(engine=None)
    strategy._get_from_bulk_tables = lambda _cik: (2025, "Q2", "0000000000-00-000000")
    strategy._check_bulk_data_age = lambda _cik: 120

    with caplog.at_level(logging.WARNING, logger="investigator.infrastructure.sec.data_strategy"):
        result_1 = strategy.get_latest_fiscal_period("STX", "0001137789")
        result_2 = strategy.get_latest_fiscal_period("STX", "0001137789")

    stale_warnings = [r for r in caplog.records if "Bulk data for STX is stale" in r.message]

    assert result_1 == (None, None, None)
    assert result_2 == (None, None, None)
    assert len(stale_warnings) == 1


def test_stale_bulk_warning_still_emitted_for_different_symbols(caplog):
    strategy = SECDataStrategy(engine=None)
    strategy._get_from_bulk_tables = lambda _cik: (2025, "Q2", "0000000000-00-000000")
    strategy._check_bulk_data_age = lambda _cik: 120

    with caplog.at_level(logging.WARNING, logger="investigator.infrastructure.sec.data_strategy"):
        strategy.get_latest_fiscal_period("STX", "0001137789")
        strategy.get_latest_fiscal_period("AAPL", "0000320193")

    assert sum("Bulk data for STX is stale" in r.message for r in caplog.records) == 1
    assert sum("Bulk data for AAPL is stale" in r.message for r in caplog.records) == 1
