"""The historical valuation path must be point-in-time.

Audit finding A (CRITICAL): `run_historical_valuation` called `ValuationTool.execute`
with no as-of date, so every historical fair value was computed from *today's*
fundamentals. Price and shares services already supported point-in-time; only the
fundamentals path leaked, which made the harness look correct while it was not.
"""

from __future__ import annotations

import inspect

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
