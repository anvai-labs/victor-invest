# Copyright 2026 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Deterministically materialize versioned SEC narrative derivation outcomes.

This module is deliberately separate from the interactive SEC tool.  The tool
remains a read-only consumer; an operator invokes this batch boundary with a
role that can read immutable source documents and write only Victor's derived
table.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, cast

from sqlalchemy import URL, Engine, create_engine, text

from victor_invest.sec_document_store import MAX_SEC_DOCUMENT_BYTES, SecDocumentIntegrityError, StoredSecDocument
from victor_invest.tools.sec_filing_text import (
    SEC_TEXT_PARSER_VERSION,
    SECFilingTextTool,
    canonical_sections_for_form,
)

SEC_DERIVATION_CONFIDENCE_BASIS = "exact_form_part_item_title"


class DerivationStatus(str, Enum):
    """Durable, fail-closed outcome states for one canonical section."""

    SUCCESS = "success"
    MISSING = "missing"
    INVALID_SOURCE = "invalid_source"
    PARSE_ERROR = "parse_error"


class SecDerivedSectionConflictError(RuntimeError):
    """Raised if one immutable parser key produces two different outcomes."""


@dataclass(frozen=True, slots=True)
class DerivedSectionOutcome:
    """One parser-versioned outcome tied to an immutable source document."""

    accession_no: str
    document_kind: str
    content_sha256: str
    canonical_section: str
    parser_version: str
    status: DerivationStatus
    heading: str | None = None
    source_start_byte: int | None = None
    source_end_byte: int | None = None
    normalized_text_sha256: str | None = None
    normalized_text: str | None = None
    truncated: bool | None = None
    confidence: Decimal | None = None
    confidence_basis: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None

    def parameters(self) -> dict[str, Any]:
        """Return SQL parameters with enum values normalized for the driver."""
        values = asdict(self)
        values["status"] = self.status.value
        return values


def _failure_outcome(
    document: StoredSecDocument,
    canonical_section: str,
    status: DerivationStatus,
    failure_code: str,
    failure_reason: str,
) -> DerivedSectionOutcome:
    return DerivedSectionOutcome(
        accession_no=document.accession_no,
        document_kind=document.document_kind,
        content_sha256=document.content_sha256,
        canonical_section=canonical_section,
        parser_version=SEC_TEXT_PARSER_VERSION,
        status=status,
        failure_code=failure_code,
        failure_reason=failure_reason,
    )


def derive_document_sections(
    document: StoredSecDocument,
    *,
    parser: SECFilingTextTool | None = None,
) -> tuple[DerivedSectionOutcome, ...]:
    """Derive every canonical section expected for one stored 10-K or 10-Q."""
    expected_sections = canonical_sections_for_form(document.form_type)
    if not expected_sections:
        raise ValueError(f"No canonical sections are defined for form {document.form_type!r}")

    try:
        document.verified_text()
    except SecDocumentIntegrityError as exc:
        return tuple(
            _failure_outcome(
                document,
                canonical_section,
                DerivationStatus.INVALID_SOURCE,
                "source_integrity_error",
                str(exc),
            )
            for canonical_section, _ in expected_sections
        )

    extractor = parser or SECFilingTextTool()
    outcomes: list[DerivedSectionOutcome] = []
    for canonical_section, section_name in expected_sections:
        try:
            extracted = extractor._extract_canonical_section_with_provenance(
                document.content_bytes,
                document.form_type,
                section_name,
                MAX_SEC_DOCUMENT_BYTES,
            )
        except Exception as exc:
            outcomes.append(
                _failure_outcome(
                    document,
                    canonical_section,
                    DerivationStatus.PARSE_ERROR,
                    "parser_exception",
                    f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        if extracted is None:
            outcomes.append(
                _failure_outcome(
                    document,
                    canonical_section,
                    DerivationStatus.MISSING,
                    "section_not_found",
                    f"No exact form/part/item/title match for {canonical_section}",
                )
            )
            continue

        extracted_identifier, section = extracted
        if extracted_identifier != canonical_section:
            outcomes.append(
                _failure_outcome(
                    document,
                    canonical_section,
                    DerivationStatus.PARSE_ERROR,
                    "canonical_identifier_mismatch",
                    f"Expected {canonical_section}, parser returned {extracted_identifier}",
                )
            )
            continue

        outcomes.append(
            DerivedSectionOutcome(
                accession_no=document.accession_no,
                document_kind=document.document_kind,
                content_sha256=document.content_sha256,
                canonical_section=canonical_section,
                parser_version=SEC_TEXT_PARSER_VERSION,
                status=DerivationStatus.SUCCESS,
                heading=section.text.splitlines()[0],
                source_start_byte=section.source_start_byte,
                source_end_byte=section.source_end_byte,
                normalized_text_sha256=section.normalized_text_sha256,
                normalized_text=section.text,
                truncated=section.truncated,
                confidence=Decimal("1.000"),
                confidence_basis=SEC_DERIVATION_CONFIDENCE_BASIS,
            )
        )
    return tuple(outcomes)


_INSERT_OUTCOME = """
INSERT INTO public.victor_sec_derived_section (
    accession_no, document_kind, content_sha256, canonical_section,
    parser_version, status, heading, source_start_byte, source_end_byte,
    normalized_text_sha256, normalized_text, truncated, confidence,
    confidence_basis, failure_code, failure_reason
) VALUES (
    :accession_no, :document_kind, :content_sha256, :canonical_section,
    :parser_version, :status, :heading, :source_start_byte, :source_end_byte,
    :normalized_text_sha256, :normalized_text, :truncated, :confidence,
    :confidence_basis, :failure_code, :failure_reason
)
ON CONFLICT (accession_no, document_kind, content_sha256, canonical_section, parser_version)
DO NOTHING
RETURNING TRUE AS inserted
"""

_SELECT_OUTCOME = """
SELECT accession_no, document_kind, content_sha256, canonical_section,
       parser_version, status, heading, source_start_byte, source_end_byte,
       normalized_text_sha256, normalized_text, truncated, confidence,
       confidence_basis, failure_code, failure_reason
FROM public.victor_sec_derived_section
WHERE accession_no = :accession_no
  AND document_kind = :document_kind
  AND content_sha256 = :content_sha256
  AND canonical_section = :canonical_section
  AND parser_version = :parser_version
"""

_SELECT_PENDING_DOCUMENTS = """
SELECT accession_no, content_sha256, document_kind, issuer_cik, issuer_ticker,
       form_type, is_amendment, filed_at, accepted_at, available_at,
       report_period_end, document_url, content_type, byte_length,
       content_bytes, retrieved_at, last_verified_at
FROM public.sec_filing_document AS document
WHERE document.form_type IN ('10-K', '10-K/A', '10-Q', '10-Q/A')
  AND document.available_at <= :as_of
  AND document.retrieved_at <= :as_of
  AND document.byte_length <= :max_document_bytes
  AND (
      SELECT count(*)
      FROM public.victor_sec_derived_section AS derived
      WHERE derived.accession_no = document.accession_no
        AND derived.document_kind = document.document_kind
        AND derived.content_sha256 = document.content_sha256
        AND derived.parser_version = :parser_version
        AND (
            (
                document.form_type LIKE '10-K%'
                AND derived.canonical_section IN (
                    '10k_item_1_business', '10k_item_1a_risk_factors',
                    '10k_item_7_mda', '10k_item_7a_market_risk'
                )
            )
            OR
            (
                document.form_type LIKE '10-Q%'
                AND derived.canonical_section IN (
                    '10q_part_i_item_2_mda', '10q_part_i_item_3_market_risk',
                    '10q_part_ii_item_1a_risk_factors'
                )
            )
        )
  ) < CASE WHEN document.form_type LIKE '10-K%' THEN 4 ELSE 3 END
ORDER BY document.available_at, document.retrieved_at,
         document.accession_no, document.content_sha256
LIMIT :limit
"""

_OUTCOME_FIELDS = (
    "accession_no",
    "document_kind",
    "content_sha256",
    "canonical_section",
    "parser_version",
    "status",
    "heading",
    "source_start_byte",
    "source_end_byte",
    "normalized_text_sha256",
    "normalized_text",
    "truncated",
    "confidence",
    "confidence_basis",
    "failure_code",
    "failure_reason",
)


class PostgresSecDerivedSectionStore:
    """PostgreSQL adapter for append-only Victor SEC derivation outcomes."""

    def __init__(self, database_url: str | URL | None = None, *, engine: Engine | Any | None = None) -> None:
        if engine is not None:
            self._engine = engine
            return
        resolved_url = database_url or os.getenv("SEC_DERIVATION_DATABASE_URL")
        if not resolved_url:
            raise ValueError("Configure SEC_DERIVATION_DATABASE_URL for the materializer role")
        candidate = create_engine(resolved_url, pool_pre_ping=True, pool_size=1, max_overflow=1)
        if candidate.url.get_backend_name() != "postgresql":
            candidate.dispose()
            raise ValueError("SEC derived section store requires PostgreSQL")
        self._engine = candidate

    def list_pending_documents(self, *, limit: int, as_of: datetime) -> list[StoredSecDocument]:
        """Return a bounded batch missing at least one current-version outcome."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        params = {
            "as_of": as_of.astimezone(UTC),
            "limit": limit,
            "max_document_bytes": MAX_SEC_DOCUMENT_BYTES,
            "parser_version": SEC_TEXT_PARSER_VERSION,
        }
        with self._engine.connect() as connection:
            rows = connection.execute(text(_SELECT_PENDING_DOCUMENTS), params).mappings().all()
        return [StoredSecDocument.from_mapping(cast(Mapping[str, Any], row)) for row in rows]

    def persist(self, outcome: DerivedSectionOutcome) -> bool:
        """Insert one immutable outcome, or verify an identical prior insert."""
        params = outcome.parameters()
        key_params = {field: params[field] for field in _OUTCOME_FIELDS[:5]}
        with self._engine.begin() as connection:
            inserted = connection.execute(text(_INSERT_OUTCOME), params).mappings().first()
            if inserted is not None:
                return True
            existing = connection.execute(text(_SELECT_OUTCOME), key_params).mappings().first()

        if existing is None or any(existing[field] != params[field] for field in _OUTCOME_FIELDS):
            raise SecDerivedSectionConflictError(
                "immutable derivation conflict for "
                f"{outcome.accession_no}/{outcome.content_sha256}/{outcome.canonical_section}/"
                f"{outcome.parser_version}"
            )
        return False

    def close(self) -> None:
        """Dispose pooled database connections."""
        self._engine.dispose()


class SecDerivedSectionStore(Protocol):
    """Minimal materialization boundary used by the deterministic batch."""

    def list_pending_documents(self, *, limit: int, as_of: datetime) -> list[StoredSecDocument]: ...

    def persist(self, outcome: DerivedSectionOutcome) -> bool: ...


@dataclass(frozen=True, slots=True)
class MaterializationSummary:
    documents: int
    inserted: int
    unchanged: int
    success: int
    failed: int
    dry_run: bool


def materialize_pending_sections(
    *,
    store: SecDerivedSectionStore,
    limit: int,
    as_of: datetime,
    dry_run: bool = False,
) -> MaterializationSummary:
    """Materialize one bounded batch and return content-free operator counts."""
    documents = store.list_pending_documents(limit=limit, as_of=as_of)
    inserted = unchanged = success = failed = 0
    for document in documents:
        for outcome in derive_document_sections(document):
            if outcome.status is DerivationStatus.SUCCESS:
                success += 1
            else:
                failed += 1
            if dry_run:
                continue
            if store.persist(outcome):
                inserted += 1
            else:
                unchanged += 1
    return MaterializationSummary(
        documents=len(documents),
        inserted=inserted,
        unchanged=unchanged,
        success=success,
        failed=failed,
        dry_run=dry_run,
    )
