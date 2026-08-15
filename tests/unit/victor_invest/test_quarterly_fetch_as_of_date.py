"""Point-in-time guard for fundamentals fetch (no look-ahead bias)."""

from contextlib import contextmanager
from datetime import date

from investigator.domain.agents.fundamental.quarterly_fetch import (
    query_recent_processed_periods,
)


class _FakeResult:
    def fetchall(self):
        return []


class _FakeSession:
    def __init__(self, capture):
        self._capture = capture

    def execute(self, query, params):
        self._capture["query"] = str(query)
        self._capture["params"] = params
        return _FakeResult()


class _FakeDBManager:
    def __init__(self, capture):
        self._capture = capture

    @contextmanager
    def get_session(self):
        yield _FakeSession(self._capture)


class _NullLogger:
    def warning(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass


def test_as_of_date_adds_filed_date_predicate():
    capture: dict = {}
    query_recent_processed_periods(
        symbol="AAPL",
        num_quarters=12,
        db_manager=_FakeDBManager(capture),
        fiscal_period_service=None,
        logger=_NullLogger(),
        as_of_date=date(2020, 1, 15),
    )
    assert "filed_date <= :as_of_date" in capture["query"]
    assert capture["params"]["as_of_date"] == date(2020, 1, 15)


def test_no_as_of_date_omits_predicate():
    capture: dict = {}
    query_recent_processed_periods(
        symbol="AAPL",
        num_quarters=12,
        db_manager=_FakeDBManager(capture),
        fiscal_period_service=None,
        logger=_NullLogger(),
    )
    assert "filed_date <= :as_of_date" not in capture["query"]
    assert "as_of_date" not in capture["params"]
