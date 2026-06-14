"""Tests for the canonical UniverseService (PIT membership + live fallback)."""

from contextlib import contextmanager
from datetime import date

from investigator.domain.services.market_data.universe_service import (
    UniverseService,
)


# ----------------------------------------------------------------- pure membership
def test_members_as_of_window():
    rows = [
        {"symbol": "AAA", "effective_date": date(2018, 1, 1), "removal_date": None},  # still member
        {"symbol": "BBB", "effective_date": date(2019, 6, 1), "removal_date": date(2021, 3, 1)},  # removed after as-of
        {"symbol": "CCC", "effective_date": date(2021, 1, 1), "removal_date": None},  # added after as-of
        {"symbol": "DDD", "effective_date": date(2019, 1, 1), "removal_date": date(2020, 12, 31)},  # in window
    ]
    as_of = date(2020, 6, 1)
    members = UniverseService.members_as_of(rows, as_of)
    # AAA (still), BBB (removal 2021 > as_of), DDD (removal 2020-12 > as_of) are members; CCC added later.
    assert set(members) == {"AAA", "BBB", "DDD"}


def test_members_as_of_explicit_cases():
    as_of = date(2020, 6, 1)
    assert UniverseService.members_as_of([{"symbol": "X", "effective_date": date(2018, 1, 1)}], as_of) == ["X"]
    # effective in the future -> excluded
    assert UniverseService.members_as_of([{"symbol": "X", "effective_date": date(2021, 1, 1)}], as_of) == []
    # removed before as_of -> excluded
    assert (
        UniverseService.members_as_of(
            [{"symbol": "X", "effective_date": date(2018, 1, 1), "removal_date": date(2020, 1, 1)}], as_of
        )
        == []
    )
    # removed after as_of -> included
    assert UniverseService.members_as_of(
        [{"symbol": "X", "effective_date": date(2018, 1, 1), "removal_date": date(2021, 1, 1)}], as_of
    ) == ["X"]


# ----------------------------------------------------------------- orchestration (fake DB)
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, router):
        self._router = router

    def execute(self, query, params=None):
        return _FakeResult(self._router(str(query), params or {}))


class _FakeDB:
    def __init__(self, router):
        self._router = router

    @contextmanager
    def get_session(self):
        yield _FakeSession(self._router)


def test_get_universe_pit_when_membership_exists():
    def router(sql, params):
        if "LIMIT 1" in sql and "index_membership" in sql:
            return [(1,)]  # has_membership_data -> True
        if "FROM index_membership" in sql:
            return [("AAPL", "sp500"), ("MSFT", "sp500")]
        return []

    svc = UniverseService(db_manager=_FakeDB(router))
    result = svc.get_universe(as_of_date=date(2020, 1, 1), index="sp500")
    assert result.mode == "pit"
    assert result.survivorship_safe is True
    assert set(result.symbols) == {"AAPL", "MSFT"}


def test_get_universe_falls_back_to_live_when_no_membership():
    def router(sql, params):
        if "LIMIT 1" in sql and "index_membership" in sql:
            return []  # no membership data
        if "FROM symbol" in sql:
            return [("AAPL", "Tech"), ("XOM", "Energy")]
        return []

    svc = UniverseService(db_manager=_FakeDB(router))
    result = svc.get_universe(as_of_date=date(2020, 1, 1), index="sp500")
    assert result.mode == "live"
    assert result.survivorship_safe is False
    assert set(result.symbols) == {"AAPL", "XOM"}


def test_get_universe_live_mode_explicit():
    def router(sql, params):
        if "FROM symbol" in sql:
            return [("AAPL", "Tech")]
        return []

    svc = UniverseService(db_manager=_FakeDB(router))
    result = svc.get_universe(top_n=10, mode="live")
    assert result.mode == "live"
    assert result.symbols == ["AAPL"]
    assert result.survivorship_safe is False
