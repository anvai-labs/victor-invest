from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self

import pytest

from victor_invest.sec_document_store import StoredSecDocument
from victor_invest.sec_section_materializer import (
    SEC_DERIVATION_CONFIDENCE_BASIS,
    DerivationStatus,
    PostgresSecDerivedSectionStore,
    SecDerivedSectionConflictError,
    derive_document_sections,
    materialize_pending_sections,
)
from victor_invest.tools.sec_filing_text import SEC_TEXT_PARSER_VERSION

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "sec"


def _document(fixture: str, form_type: str, **overrides: Any) -> StoredSecDocument:
    content = (FIXTURE_ROOT / fixture).read_bytes()
    row: dict[str, Any] = {
        "accession_no": "0000320193-26-000001",
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "document_kind": "primary",
        "issuer_cik": 320193,
        "issuer_ticker": "AAPL",
        "form_type": form_type,
        "is_amendment": form_type.endswith("/A"),
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
    return StoredSecDocument.from_mapping(row)


def test_materializer_derives_all_annual_sections_without_truncation() -> None:
    document = _document("10k_noncalendar_incorporation.html", "10-K")

    outcomes = derive_document_sections(document)

    assert {outcome.canonical_section for outcome in outcomes} == {
        "10k_item_1_business",
        "10k_item_1a_risk_factors",
        "10k_item_7_mda",
        "10k_item_7a_market_risk",
    }
    assert all(outcome.status is DerivationStatus.SUCCESS for outcome in outcomes)
    assert all(outcome.parser_version == SEC_TEXT_PARSER_VERSION for outcome in outcomes)
    assert all(outcome.confidence == Decimal("1.000") for outcome in outcomes)
    assert all(outcome.confidence_basis == SEC_DERIVATION_CONFIDENCE_BASIS for outcome in outcomes)
    assert all(outcome.normalized_text and not outcome.truncated for outcome in outcomes)
    for outcome in outcomes:
        assert outcome.source_start_byte is not None
        assert outcome.source_end_byte is not None
        assert outcome.normalized_text_sha256 == hashlib.sha256(outcome.normalized_text.encode()).hexdigest()
        source = document.content_bytes[outcome.source_start_byte : outcome.source_end_byte]
        assert outcome.heading.encode() in source


def test_materializer_persists_explicit_missing_outcomes() -> None:
    document = _document("10q_absent_canonical_items.html", "10-Q")

    outcomes = derive_document_sections(document)

    assert len(outcomes) == 3
    assert all(outcome.status is DerivationStatus.MISSING for outcome in outcomes)
    assert all(outcome.failure_code == "section_not_found" for outcome in outcomes)
    assert all(outcome.failure_reason for outcome in outcomes)
    assert all(outcome.normalized_text is None for outcome in outcomes)
    assert all(outcome.confidence is None for outcome in outcomes)


def test_materializer_records_source_integrity_failure_for_every_expected_section() -> None:
    document = _document("10q_inline_xbrl_amendment.html", "10-Q/A", content_sha256="0" * 64)

    outcomes = derive_document_sections(document)

    assert len(outcomes) == 3
    assert all(outcome.status is DerivationStatus.INVALID_SOURCE for outcome in outcomes)
    assert all(outcome.failure_code == "source_integrity_error" for outcome in outcomes)
    assert all("digest" in (outcome.failure_reason or "") for outcome in outcomes)


class _FakeResult:
    def __init__(self, row: dict[str, Any] | None, rows: list[dict[str, Any]] | None = None) -> None:
        self._row = row
        self._rows = rows or []

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConnection:
    def __init__(self, existing: dict[str, Any] | None) -> None:
        self.existing = existing
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: object, params: dict[str, Any]) -> _FakeResult:
        sql = str(statement)
        self.calls.append((sql, params))
        if "RETURNING" in sql:
            return _FakeResult({"inserted": True} if self.existing is None else None)
        return _FakeResult(self.existing)


class _FakeEngine:
    def __init__(self, existing: dict[str, Any] | None = None) -> None:
        self.connection = _FakeConnection(existing)
        self.disposed = False

    def begin(self) -> _FakeConnection:
        return self.connection

    def connect(self) -> _FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def test_store_is_idempotent_only_for_an_identical_immutable_outcome() -> None:
    outcome = derive_document_sections(_document("10k_noncalendar_incorporation.html", "10-K"))[0]
    engine = _FakeEngine()
    store = PostgresSecDerivedSectionStore(engine=engine)

    assert store.persist(outcome)
    insert_sql, params = engine.connection.calls[0]
    assert "ON CONFLICT (accession_no, document_kind, content_sha256, canonical_section, parser_version)" in insert_sql
    assert "DO NOTHING" in insert_sql
    assert params["parser_version"] == SEC_TEXT_PARSER_VERSION

    existing = dict(params)
    engine.connection.existing = existing
    assert not store.persist(outcome)

    existing["normalized_text_sha256"] = "f" * 64
    with pytest.raises(SecDerivedSectionConflictError, match="immutable derivation conflict"):
        store.persist(outcome)


def test_pending_query_is_version_point_in_time_size_and_batch_bounded() -> None:
    engine = _FakeEngine()
    store = PostgresSecDerivedSectionStore(engine=engine)
    as_of = datetime(2026, 8, 2, tzinfo=UTC)

    assert store.list_pending_documents(limit=100, as_of=as_of) == []

    query, params = engine.connection.calls[0]
    assert "document.available_at <= :as_of" in query
    assert "document.retrieved_at <= :as_of" in query
    assert "document.byte_length <= :max_document_bytes" in query
    assert "derived.parser_version = :parser_version" in query
    assert params["parser_version"] == SEC_TEXT_PARSER_VERSION
    assert params["limit"] == 100
    with pytest.raises(ValueError, match="limit"):
        store.list_pending_documents(limit=101, as_of=as_of)


class _FakeMaterializationStore:
    def __init__(self, document: StoredSecDocument) -> None:
        self.document = document
        self.persisted = 0

    def list_pending_documents(self, *, limit: int, as_of: datetime) -> list[StoredSecDocument]:
        assert limit == 1
        assert as_of.tzinfo is not None
        return [self.document]

    def persist(self, outcome: object) -> bool:
        self.persisted += 1
        return True


def test_dry_run_reports_outcomes_without_writing() -> None:
    store = _FakeMaterializationStore(_document("10q_inline_xbrl_amendment.html", "10-Q/A"))

    summary = materialize_pending_sections(
        store=store,
        limit=1,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        dry_run=True,
    )

    assert summary.documents == 1
    assert summary.success == 3
    assert summary.failed == 0
    assert summary.inserted == 0
    assert store.persisted == 0
