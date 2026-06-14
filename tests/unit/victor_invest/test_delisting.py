"""Tests for delisting extraction, terminal-exit logic, and reward integration (C1/C2)."""

import asyncio
from datetime import date, timedelta

from investigator.domain.services.market_data.delisting_service import (
    DelistingRecord,
    DelistingService,
)
from investigator.infrastructure.sec.delisting_extractor import (
    backfill_delisting,
    extract_delisting_from_submissions,
)
from victor_invest.tools.rl_backtest import RLBacktestTool


# ----------------------------------------------------------------- EDGAR extractor
def _submissions(forms_dates, tickers=("ZZZ",)):
    return {
        "tickers": list(tickers),
        "filings": {
            "recent": {
                "form": [f for f, _ in forms_dates],
                "filingDate": [d for _, d in forms_dates],
                "accessionNumber": [f"acc-{i}" for i in range(len(forms_dates))],
            }
        },
    }


def test_extract_form25_delisting():
    subs = _submissions([("8-K", "2019-01-01"), ("25", "2020-03-15"), ("25-NSE", "2020-03-20")])
    rec = extract_delisting_from_submissions(subs)
    assert rec is not None
    assert rec.symbol == "ZZZ"
    assert rec.delist_date == date(2020, 3, 15)  # earliest removal form
    assert rec.source == "edgar_form25"


def test_extract_form15_fallback_when_no_form25():
    subs = _submissions([("10-K", "2019-01-01"), ("15-12B", "2021-06-30")])
    rec = extract_delisting_from_submissions(subs)
    assert rec is not None
    assert rec.delist_date == date(2021, 6, 30)
    assert rec.source == "edgar_form15"


def test_extract_none_when_no_delisting_forms():
    subs = _submissions([("10-K", "2019-01-01"), ("8-K", "2020-02-02")])
    assert extract_delisting_from_submissions(subs) is None


def test_extract_uses_symbol_fallback_when_no_tickers():
    subs = _submissions([("25", "2020-03-15")], tickers=())
    rec = extract_delisting_from_submissions(subs, symbol="abc")
    assert rec is not None and rec.symbol == "ABC"


def test_backfill_uses_last_close_and_refines_date():
    subs = _submissions([("25", "2020-03-15")], tickers=("ZZZ",))

    class _FakeSecClient:
        async def get_submissions(self, cik):
            return subs

    # tickerdata stops at delisting; last row is 2020-03-18 @ $4.20 (later than form date).
    def last_close_lookup(symbol):
        return (date(2020, 3, 18), 4.20)

    rec = asyncio.run(backfill_delisting("ZZZ", "0000000000", _FakeSecClient(), last_close_lookup))
    assert rec is not None
    assert rec.last_price == 4.20
    assert rec.delist_date == date(2020, 3, 18)  # refined to the actual last-trade date


def test_backfill_returns_none_when_no_delisting():
    subs = _submissions([("10-K", "2019-01-01")], tickers=("ZZZ",))

    class _FakeSecClient:
        async def get_submissions(self, cik):
            return subs

    assert asyncio.run(backfill_delisting("ZZZ", "0", _FakeSecClient())) is None


# ----------------------------------------------------------------- terminal exit math
def test_terminal_exit_total_loss():
    rec = DelistingRecord("ZZZ", date(2020, 6, 1), reason="bankruptcy", last_price=5.0)
    # recovery defaults to 0 for bankruptcy -> total loss
    assert DelistingService.terminal_exit_price(rec, date(2020, 7, 1)) == 0.0


def test_terminal_exit_before_delisting_is_none():
    rec = DelistingRecord("ZZZ", date(2020, 6, 1), reason="bankruptcy", last_price=5.0)
    assert DelistingService.terminal_exit_price(rec, date(2020, 5, 1)) is None


def test_terminal_exit_acquired_realizes_last_price():
    rec = DelistingRecord("ZZZ", date(2020, 6, 1), reason="acquired", last_price=42.0)
    assert DelistingService.terminal_exit_price(rec, date(2020, 7, 1)) == 42.0


def test_terminal_exit_explicit_recovery_overrides_reason():
    rec = DelistingRecord("ZZZ", date(2020, 6, 1), reason="acquired", last_price=10.0, recovery_assumption=0.5)
    assert DelistingService.terminal_exit_price(rec, date(2020, 7, 1)) == 5.0


def test_terminal_exit_no_last_price_is_none():
    rec = DelistingRecord("ZZZ", date(2020, 6, 1), reason="bankruptcy", last_price=None)
    assert DelistingService.terminal_exit_price(rec, date(2020, 7, 1)) is None


# ----------------------------------------------------------------- reward integration
class _NoPriceService:
    """Simulates a delisted name: no future market price available."""

    def get_price(self, symbol, target_date, search_days=5):
        return None


class _FakeDelistingService:
    def __init__(self, record):
        self._record = record

    def get_delisting(self, symbol):
        return self._record

    terminal_exit_price = staticmethod(DelistingService.terminal_exit_price)


def test_reward_path_uses_terminal_exit_for_bankruptcy():
    from investigator.domain.services.rl.reward_calculator import get_reward_calculator

    analysis = date(2020, 1, 1)
    # Bankruptcy ~200 days out, total loss from a $5 last price; entry was $100.
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    tool = RLBacktestTool()
    tool._price_service = _NoPriceService()  # noqa: SLF001
    tool._reward_calculator = get_reward_calculator()  # noqa: SLF001
    tool._delisting_service = _FakeDelistingService(record)  # noqa: SLF001

    data = asyncio.run(tool._get_multi_period_data("ZZZ", analysis, current_price=100.0, beta=1.0))  # noqa: SLF001

    assert data["delisted"] is True
    # Horizons before the delist date have no price and no terminal -> dropped.
    assert data["prices"]["1m"] is None  # 30d < 200d
    assert data["terminal_exits"]["1m"] is False
    # Horizons spanning the delisting realize a terminal (near-total-loss) exit.
    assert data["terminal_exits"]["12m"] is True  # 365d > 200d
    assert data["prices"]["12m"] is not None and data["prices"]["12m"] > 0  # floored, not zero
    assert data["exit_dates"]["12m"] == record.delist_date.isoformat()
    # A LONG into a near-total loss must be strongly negative; SHORT strongly positive.
    assert data["long_rewards"]["12m"] < -0.5
    assert data["short_rewards"]["12m"] > 0.5


def test_reward_path_no_delisting_drops_missing_prices():
    from investigator.domain.services.rl.reward_calculator import get_reward_calculator

    tool = RLBacktestTool()
    tool._price_service = _NoPriceService()  # noqa: SLF001
    tool._reward_calculator = get_reward_calculator()  # noqa: SLF001
    tool._delisting_service = _FakeDelistingService(None)  # noqa: SLF001

    data = asyncio.run(tool._get_multi_period_data("ZZZ", date(2020, 1, 1), current_price=100.0, beta=1.0))  # noqa: SLF001
    assert data["delisted"] is False
    assert all(v is None for v in data["prices"].values())
    assert all(v is False for v in data["terminal_exits"].values())
