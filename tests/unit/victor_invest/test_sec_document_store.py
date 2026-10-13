from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any, Self

import pytest

from victor_invest.sec_document_store import (
    MAX_SEC_DOCUMENT_BYTES,
    PostgresSecDocumentStore,
    SecDocumentIntegrityError,
    StoredSecDocument,
)


def _row(**overrides: Any) -> dict[str, Any]:
    content = overrides.pop("content_bytes", b"<h1>Item 7. Management's Discussion</h1>")
    row: dict[str, Any] = {
        "accession_no": "0000320193-26-000001",
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "document_kind": "primary",
        "issuer_cik": 320193,
        "issuer_ticker": "AAPL",
        "form_type": "10-K",
        "is_amendment": False,
        "filed_at": date(2026, 8, 1),
        "accepted_at": datetime(2026, 8, 1, 12, tzinfo=UTC),
        "available_at": datetime(2026, 8, 1, 12, tzinfo=UTC),
        "report_period_end": date(2026, 6, 30),
        "document_url": "https://www.sec.gov/Archives/edgar/data/320193/aapl.htm",
        "content_type": "text/html; charset=utf-8",
        "byte_length": len(content),
        "content_bytes": content,
        "retrieved_at": datetime(2026, 8, 1, 13, tzinfo=UTC),
        "last_verified_at": datetime(2026, 8, 1, 14, tzinfo=UTC),
    }
    row.update(overrides)
    return row


def test_stored_document_verifies_exact_bytes_and_source_contract() -> None:
    document = StoredSecDocument.from_mapping(_row())

    assert document.verified_text().startswith("<h1>Item 7")

    with pytest.raises(SecDocumentIntegrityError, match="digest"):
        StoredSecDocument.from_mapping(_row(content_sha256="0" * 64)).verified_text()
    with pytest.raises(SecDocumentIntegrityError, match="byte length"):
        StoredSecDocument.from_mapping(_row(byte_length=999)).verified_text()
    with pytest.raises(SecDocumentIntegrityError, match="document kind"):
        StoredSecDocument.from_mapping(_row(form_type="8-K", document_kind="primary")).verified_text()
    with pytest.raises(SecDocumentIntegrityError, match="canonical SEC archive"):
        StoredSecDocument.from_mapping(_row(document_url="https://example.com/aapl.htm")).verified_text()


def test_stored_document_rejects_oversized_content() -> None:
    content = b"x" * (MAX_SEC_DOCUMENT_BYTES + 1)
    with pytest.raises(SecDocumentIntegrityError, match="exceeds"):
        StoredSecDocument.from_mapping(_row(content_bytes=content)).verified_text()


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict[str, Any]], calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._rows = rows
        self._calls = calls

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: object, params: dict[str, Any]) -> _FakeResult:
        self._calls.append((str(statement), params))
        return _FakeResult(self._rows)


class _FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.disposed = False

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self.rows, self.calls)

    def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_latest_query_is_symbol_form_role_size_and_point_in_time_bounded() -> None:
    engine = _FakeEngine([_row()])
    store = PostgresSecDocumentStore(engine=engine)
    as_of = datetime(2026, 8, 2, tzinfo=UTC)

    document = await store.get_latest_document("aapl", "10-K", "latest", as_of)

    assert document is not None
    query, params = engine.calls[0]
    assert "available_at <= :as_of" in query
    assert "retrieved_at <= :as_of" in query
    assert "byte_length <= :max_document_bytes" in query
    assert params == {
        "symbol": "AAPL",
        "base_form": "10-K",
        "amended_form": "10-K/A",
        "document_kind": "primary",
        "as_of": as_of,
        "max_document_bytes": MAX_SEC_DOCUMENT_BYTES,
        "period_start": None,
        "period_end": None,
        "limit": 1,
    }

    store.close()
    assert engine.disposed


@pytest.mark.asyncio
async def test_recent_8k_query_requires_complete_submissions_and_bounded_limit() -> None:
    engine = _FakeEngine([_row(form_type="8-K", document_kind="complete_submission")])
    store = PostgresSecDocumentStore(engine=engine)
    as_of = datetime(2026, 8, 2, tzinfo=UTC)

    documents = await store.list_recent_documents("AAPL", "8-K", as_of, limit=3)

    assert len(documents) == 1
    _, params = engine.calls[0]
    assert params["document_kind"] == "complete_submission"
    assert params["limit"] == 3
    with pytest.raises(ValueError, match="between 1 and 20"):
        await store.list_recent_documents("AAPL", "8-K", as_of, limit=21)


@pytest.mark.asyncio
async def test_period_and_as_of_inputs_fail_closed() -> None:
    store = PostgresSecDocumentStore(engine=_FakeEngine([]))
    aware = datetime(2026, 8, 2, tzinfo=UTC)

    await store.get_latest_document("AAPL", "10-Q", "2026-Q2", aware)
    params = store._engine.calls[0][1]
    assert params["period_start"] == date(2026, 4, 1)
    assert params["period_end"] == date(2026, 6, 30)

    with pytest.raises(ValueError, match="period"):
        await store.get_latest_document("AAPL", "10-Q", "2026-Q5", aware)
    with pytest.raises(ValueError, match="timezone"):
        await store.get_latest_document("AAPL", "10-Q", "latest", datetime(2026, 8, 2))
