"""The historical valuation path must be point-in-time.

Audit finding A (CRITICAL): `run_historical_valuation` called `ValuationTool.execute`
with no as-of date, so every historical fair value was computed from *today's*
fundamentals. Price and shares services already supported point-in-time; only the
fundamentals path leaked, which made the harness look correct while it was not.
"""

from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import MagicMock

import pytest

from victor_invest.tools.sec_filing import SECFilingTool
from victor_invest.tools.valuation import ValuationTool


def test_valuation_tool_accepts_as_of_date():
    assert "as_of_date" in inspect.signature(ValuationTool.execute).parameters


def test_fetch_valuation_data_accepts_as_of_date():
    assert "as_of_date" in inspect.signature(ValuationTool._fetch_valuation_data).parameters


def test_sec_filing_quarterly_accepts_as_of_date():
    assert "as_of_date" in inspect.signature(SECFilingTool._get_quarterly_financials).parameters


def test_backtest_passes_as_of_date_to_the_valuation_tool():
    """The whole chain is pointless if the call site does not supply the date."""
    import victor_invest.workflows.rl_backtest as backtest

    source = inspect.getsource(backtest.run_historical_valuation)
    assert "as_of_date=" in source, "run_historical_valuation must pass as_of_date to the valuation tool"


@pytest.mark.asyncio
async def test_date_blind_db_path_is_not_used_for_a_point_in_time_request():
    """A point-in-time request must never be served by a date-blind source.

    `_fetch_valuation_data` tries `db_manager.get_quarterly_metrics(symbol)` before
    the SEC query, and that call takes no as-of date. `initialize()` currently pins
    `_db_manager` to None, so the branch is dead today -- but if anything ever
    populates it, a historical valuation would silently be computed from present-day
    fundamentals, reintroducing exactly the lookahead this module exists to prevent.
    """
    tool = ValuationTool()

    db_manager = MagicMock()
    db_manager.get_quarterly_metrics.return_value = [{"fiscal_year": 2026, "total_revenue": 999.0}]
    db_manager.get_multi_year_data.return_value = [{"fiscal_year": 2026}]
    tool._db_manager = db_manager

    await tool._fetch_valuation_data("AAPL", as_of_date=date(2020, 1, 1))

    assert not db_manager.get_quarterly_metrics.called, (
        "the date-blind database path was used to serve a point-in-time request; "
        "its rows carry today's fundamentals and would leak lookahead into the backtest"
    )


@pytest.mark.asyncio
async def test_db_path_is_still_used_when_no_as_of_date_is_requested():
    """Live valuation keeps the faster database path; only PIT requests bypass it."""
    tool = ValuationTool()

    db_manager = MagicMock()
    db_manager.get_quarterly_metrics.return_value = [{"fiscal_year": 2026, "total_revenue": 999.0}]
    db_manager.get_multi_year_data.return_value = [{"fiscal_year": 2026}]
    tool._db_manager = db_manager

    result = await tool._fetch_valuation_data("AAPL", as_of_date=None)

    assert db_manager.get_quarterly_metrics.called
    assert result["success"]
