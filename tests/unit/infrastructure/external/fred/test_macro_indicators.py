import asyncio
from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd

from investigator.infrastructure.external.fred import macro_indicators
from investigator.infrastructure.external.fred.macro_indicators import (
    MacroIndicatorsFetcher,
    format_indicator_for_display,
)


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, *args, **kwargs):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeFirstResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


def make_fetcher_with_session(session):
    fetcher = MacroIndicatorsFetcher.__new__(MacroIndicatorsFetcher)
    fetcher.logger = macro_indicators.logger

    @contextmanager
    def fake_context():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    fetcher.get_session = fake_context
    return fetcher


def test_get_latest_values_supports_canonical_series_schema_and_change_calculation():
    rows = [
        ("id",),
        ("series_id",),
        ("name",),
        ("frequency",),
        ("units",),
    ]
    value_rows = [
        SimpleNamespace(
            series_id="GDP",
            date=date(2026, 3, 31),
            value=30000,
            prev_date=date(2025, 12, 31),
            prev_value=29000,
            name="Gross Domestic Product",
            frequency="Quarterly",
            units="Billions of Dollars",
        )
    ]
    session = FakeSession([rows, [("indicator_id",), ("date",), ("value",), ("is_current",)], value_rows])
    fetcher = make_fetcher_with_session(session)

    indicators = fetcher.get_latest_values(["GDP"])

    assert indicators["GDP"]["value"] == 30000.0
    assert indicators["GDP"]["prev_value"] == 29000.0
    assert indicators["GDP"]["change_abs"] == 1000.0
    assert indicators["GDP"]["change_pct"] == (1000 / 29000 * 100)
    assert indicators["GDP"]["units"] == "Billions of Dollars"
    assert session.committed is True
    assert session.closed is True


def test_get_latest_values_handles_legacy_indicator_schema_and_errors():
    legacy_indicator_columns = [("id",), ("indicator_id",), ("label",), ("frequency",), ("unit",)]
    legacy_value_columns = [("indicator_id",), ("date",), ("value",)]
    session = FakeSession([legacy_indicator_columns, legacy_value_columns, RuntimeError("query failed")])
    fetcher = make_fetcher_with_session(session)

    indicators = fetcher.get_latest_values(["GDP"])

    assert indicators == {}
    assert session.rolled_back is True


def test_get_time_series_returns_sorted_dataframe_and_empty_on_error():
    rows = [
        SimpleNamespace(date=date(2026, 2, 1), value=2),
        SimpleNamespace(date=date(2026, 1, 1), value=1),
        SimpleNamespace(date=date(2026, 3, 1), value=None),
    ]
    session = FakeSession([[("series_id",)], [("is_current",)], rows])
    fetcher = make_fetcher_with_session(session)

    frame = fetcher.get_time_series("GDP", start_date=datetime(2026, 1, 1), limit=10)

    assert list(frame["value"]) == [1.0, 2.0]
    assert list(frame["date"]) == [date(2026, 1, 1), date(2026, 2, 1)]

    error_fetcher = make_fetcher_with_session(FakeSession([RuntimeError("boom")]))
    empty = error_fetcher.get_time_series("GDP")

    assert isinstance(empty, pd.DataFrame)
    assert list(empty.columns) == ["date", "value"]
    assert empty.empty


def test_vti_price_buffett_indicator_and_macro_summary(monkeypatch):
    session = FakeSession([FakeFirstResult(SimpleNamespace(close=350.0, date=date(2026, 5, 20)))])
    fetcher = make_fetcher_with_session(session)

    assert fetcher.get_vti_price() == {"price": 350.0, "date": date(2026, 5, 20)}

    monkeypatch.setattr(
        fetcher,
        "get_latest_values",
        lambda indicator_ids=None: {
            "GDP": {
                "value": 30000.0,
                "date": date(2026, 3, 31),
                "name": "GDP",
                "change_pct": 2.0,
            },
            "UNRATE": {
                "value": 4.0,
                "date": date(2026, 4, 30),
                "name": "Unemployment",
                "change_pct": 25.0,
            },
        },
    )
    monkeypatch.setattr(fetcher, "get_vti_price", lambda: {"price": 100.0, "date": date(2026, 5, 20)})

    buffett = fetcher.calculate_buffett_indicator()

    assert buffett["ratio"] == 100.0 * 200 / 30000.0 * 100
    assert buffett["signal"] == "strong_buy"
    assert buffett["estimated_market_cap"] == 20000.0

    summary = fetcher.get_macro_summary()

    assert summary["categories"]["growth"]["GDP"]["value"] == 30000.0
    assert summary["categories"]["employment"]["UNRATE"]["value"] == 4.0
    assert summary["buffett_indicator"]["signal"] == "strong_buy"
    assert summary["overall_assessment"] == "mixed"
    assert any(alert["type"] == "large_change" for alert in summary["alerts"])
    assert any(alert["type"] == "buffett_indicator" for alert in summary["alerts"])


def test_buffett_indicator_missing_inputs_returns_none(monkeypatch):
    fetcher = MacroIndicatorsFetcher.__new__(MacroIndicatorsFetcher)
    fetcher.logger = macro_indicators.logger

    monkeypatch.setattr(fetcher, "get_latest_values", lambda ids: {})
    monkeypatch.setattr(fetcher, "get_vti_price", lambda: {"price": 350.0, "date": date(2026, 5, 20)})
    assert fetcher.calculate_buffett_indicator() is None


def test_fetcher_init_get_session_close_and_alias(monkeypatch):
    session = FakeSession([])
    monkeypatch.setattr(macro_indicators, "get_stock_db_manager", lambda: lambda: session)
    monkeypatch.setattr(macro_indicators, "_get_fred_api_key", lambda: "fred-key")

    fetcher = MacroIndicatorsFetcher()

    assert fetcher._api_key == "fred-key"
    with fetcher.get_session() as active_session:
        assert active_session is session
    assert session.committed is True
    assert session.closed is True

    error_session = FakeSession([])
    fetcher.SessionLocal = lambda: error_session
    try:
        with fetcher.get_session():
            raise RuntimeError("fail")
    except RuntimeError:
        pass
    assert error_session.rolled_back is True

    monkeypatch.setattr(fetcher, "get_latest_values", lambda indicator_ids=None, lookback_days=1095: {"GDP": {}})
    assert fetcher.get_latest_indicators(["GDP"]) == {"GDP": {}}

    class FakeAioSession:
        closed = False

        async def close(self):
            self.closed = True

    aio_session = FakeAioSession()
    fetcher._session = aio_session
    asyncio.run(fetcher.close())
    assert aio_session.closed is True


def test_get_indicator_data_without_api_key_returns_empty():
    fetcher = MacroIndicatorsFetcher.__new__(MacroIndicatorsFetcher)
    fetcher.logger = macro_indicators.logger
    fetcher._api_key = None

    assert asyncio.run(fetcher.get_indicator_data("GDP", "2026-01-01", "2026-05-20")) == {}


def test_buffett_indicator_interpretation_ranges(monkeypatch):
    fetcher = MacroIndicatorsFetcher.__new__(MacroIndicatorsFetcher)
    fetcher.logger = macro_indicators.logger
    monkeypatch.setattr(fetcher, "get_latest_values", lambda ids: {"GDP": {"value": 10000.0, "date": "2026-03-31"}})

    scenarios = [
        (40.0, "buy"),
        (50.0, "neutral"),
        (65.0, "caution"),
        (80.0, "warning"),
    ]
    for vti_price, expected_signal in scenarios:
        monkeypatch.setattr(fetcher, "get_vti_price", lambda price=vti_price: {"price": price, "date": "2026-05-20"})
        assert fetcher.calculate_buffett_indicator()["signal"] == expected_signal


def test_vti_price_handles_missing_rows_and_errors():
    no_row_fetcher = make_fetcher_with_session(FakeSession([FakeFirstResult(None)]))
    assert no_row_fetcher.get_vti_price() is None

    error_fetcher = make_fetcher_with_session(FakeSession([RuntimeError("tickerdata unavailable")]))
    assert error_fetcher.get_vti_price() is None


def test_format_indicator_for_display_covers_units_and_change_arrows():
    assert format_indicator_for_display("GDP", {}) == "GDP: No data available"
    assert "4.00%" in format_indicator_for_display(
        "UNRATE",
        {"name": "Unemployment", "value": 4, "units": "Percent", "change_pct": -5, "date": "2026-05-01"},
    )
    assert "$30,000.0B" in format_indicator_for_display(
        "GDP",
        {"name": "GDP", "value": 30000, "units": "Billions of Dollars", "change_pct": 2, "date": "2026-03-31"},
    )
    assert "$100.0M" in format_indicator_for_display(
        "TEST",
        {"name": "Millions", "value": 100, "units": "Millions", "date": "2026-03-31"},
    )
    assert "1,000K" in format_indicator_for_display(
        "TEST",
        {"name": "Thousands", "value": 1000, "units": "Thousands", "date": "2026-03-31"},
    )
    assert "5,000.00" in format_indicator_for_display(
        "SP500",
        {"name": "Index", "value": 5000, "units": "Index", "date": "2026-03-31"},
    )


def test_api_key_resolution_prefers_environment(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fred-test")

    assert macro_indicators._get_fred_api_key() == "fred-test"
