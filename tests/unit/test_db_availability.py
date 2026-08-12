"""Database-backed tests must skip when there is no database, not error.

20 integration tests errored on every local run because `dataserver1.singh.local`
is not reachable outside its network. A permanently red failure list is a list
nobody reads -- four failures carried that way this session turned out to be a
credential-scanning module that could not be imported at all.

`pyproject.toml` has registered a `db` marker the whole time. Nothing used it.
"""

from __future__ import annotations

import pytest

from tests import db_availability


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    db_availability.reset_cache()
    yield
    db_availability.reset_cache()


def test_missing_host_is_reported_with_the_fix(monkeypatch):
    monkeypatch.delenv("STOCK_DB_HOST", raising=False)
    reason = db_availability.database_unavailable_reason()
    assert reason and "STOCK_DB_HOST" in reason
    assert "investigator/env" in reason, "the skip reason should say how to fix it"


def test_missing_password_is_reported(monkeypatch):
    monkeypatch.setenv("STOCK_DB_HOST", "localhost")
    monkeypatch.delenv("STOCK_DB_PASSWORD", raising=False)
    reason = db_availability.database_unavailable_reason()
    assert reason and "STOCK_DB_PASSWORD" in reason


def test_a_non_numeric_port_is_reported_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("STOCK_DB_HOST", "localhost")
    monkeypatch.setenv("STOCK_DB_PASSWORD", "x")
    monkeypatch.setenv("STOCK_DB_PORT", "not-a-port")
    reason = db_availability.database_unavailable_reason()
    assert reason and "not a number" in reason


def test_unreachable_host_is_reported_not_raised(monkeypatch):
    """The whole point: absence is a fact to report, not an exception."""
    monkeypatch.setenv("STOCK_DB_HOST", "192.0.2.1")  # TEST-NET-1, never routable
    monkeypatch.setenv("STOCK_DB_PASSWORD", "x")
    monkeypatch.setenv("STOCK_DB_PORT", "5432")

    reason = db_availability.database_unavailable_reason()
    assert reason and "not reachable" in reason


def test_a_reachable_socket_means_available(monkeypatch):
    """A listening socket is enough; the probe deliberately does not authenticate."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    threading.Thread(target=lambda: server.accept(), daemon=True).start()

    monkeypatch.setenv("STOCK_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("STOCK_DB_PASSWORD", "x")
    monkeypatch.setenv("STOCK_DB_PORT", str(port))
    try:
        assert db_availability.database_unavailable_reason() is None
    finally:
        server.close()


def test_the_probe_is_cached(monkeypatch):
    """Probing per test would multiply a 2s timeout across the whole suite."""
    calls = []
    real_create = db_availability.socket.create_connection

    def counting(*args, **kwargs):
        calls.append(args)
        raise OSError("nope")

    monkeypatch.setattr(db_availability.socket, "create_connection", counting)
    try:
        db_availability._can_connect("192.0.2.1", 5432)
        db_availability._can_connect("192.0.2.1", 5432)
        assert len(calls) == 1, "the unreachable host was probed more than once"
    finally:
        monkeypatch.setattr(db_availability.socket, "create_connection", real_create)
