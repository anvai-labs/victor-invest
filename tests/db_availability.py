"""Decide whether the database backing the integration tests is reachable.

Tests that need a database currently *error* when it is absent rather than
skipping, so 20 of them sat permanently red. That is not a cosmetic problem: a
suite whose failure list never changes stops being read, and a real defect can
sit in it indefinitely. Four failures carried in exactly that way this session
turned out to be a credential-scanning module that could not be imported at all.

A skip says "not checked here". An error says "broken". Only one of those is true
when the host is simply not on this network.

The probe is a bare TCP connect with a short timeout -- no driver, no
credentials, no query. It only answers "is something listening", which is all
that is needed to distinguish "no database here" from "the code is wrong".
"""

from __future__ import annotations

import os
import socket

# Short: this runs during collection, and the answer is either immediate or the
# host is not there. An unbounded wait during collection is how a test run turns
# into a hang.
_PROBE_TIMEOUT_SECONDS = 2.0

# Populated once per session; probing per test would multiply the timeout.
_cached: dict[tuple[str, int], bool] = {}


def _can_connect(host: str, port: int, timeout: float = _PROBE_TIMEOUT_SECONDS) -> bool:
    """True if something accepts a TCP connection at host:port."""
    key = (host, port)
    if key in _cached:
        return _cached[key]
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result = True
    except (OSError, ValueError):
        result = False
    _cached[key] = result
    return result


def database_unavailable_reason() -> str | None:
    """Why database tests cannot run here, or None if they can.

    Returns a human-readable reason so the skip message says what to do rather
    than just "skipped".
    """
    host = os.environ.get("STOCK_DB_HOST")
    if not host:
        return "STOCK_DB_HOST is not set (source ~/.investigator/env)"

    try:
        port = int(os.environ.get("STOCK_DB_PORT", "5432"))
    except ValueError:
        return f"STOCK_DB_PORT is not a number: {os.environ.get('STOCK_DB_PORT')!r}"

    if not os.environ.get("STOCK_DB_PASSWORD"):
        return "STOCK_DB_PASSWORD is not set (source ~/.investigator/env)"

    if not _can_connect(host, port):
        return f"{host}:{port} is not reachable from here"

    return None


def reset_cache() -> None:
    """Forget probe results. For tests of this module."""
    _cached.clear()
