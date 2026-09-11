# Copyright 2026 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Read-only access to immutable SEC filing documents produced by ibkrtrading.

The producer owns SEC network access and persists exact response bytes.  Victor
only consumes those bytes from PostgreSQL, verifies their integrity, and applies
point-in-time bounds before making a document available to analysis code.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import URL, Engine, create_engine, text

MAX_SEC_DOCUMENT_BYTES = 256 * 1024 * 1024
_SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_QUARTER_RE = re.compile(r"^(?P<year>\d{4})-Q(?P<quarter>[1-4])$", re.IGNORECASE)


class SecDocumentIntegrityError(ValueError):
    """Raised when persisted SEC evidence does not satisfy its source contract."""


@dataclass(frozen=True, slots=True)
class StoredSecDocument:
    """An immutable SEC source document with integrity and provenance fields."""

    accession_no: str
    content_sha256: str
    document_kind: str
    issuer_cik: int
    issuer_ticker: str
    form_type: str
    is_amendment: bool
    filed_at: date
    accepted_at: datetime | None
    available_at: datetime
    report_period_end: date | None
    document_url: str
    content_type: str | None
    byte_length: int
    content_bytes: bytes
    retrieved_at: datetime
    last_verified_at: datetime

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> StoredSecDocument:
        """Build a document from a SQLAlchemy row mapping."""
        content = row["content_bytes"]
        if isinstance(content, memoryview):
            content = content.tobytes()
        if not isinstance(content, bytes):
            raise SecDocumentIntegrityError("SEC document content_bytes must be bytes")

        return cls(
            accession_no=str(row["accession_no"]),
            content_sha256=str(row["content_sha256"]),
            document_kind=str(row["document_kind"]),
            issuer_cik=int(row["issuer_cik"]),
            issuer_ticker=str(row["issuer_ticker"]),
            form_type=str(row["form_type"]),
            is_amendment=bool(row["is_amendment"]),
            filed_at=row["filed_at"],
            accepted_at=row["accepted_at"],
            available_at=row["available_at"],
            report_period_end=row["report_period_end"],
            document_url=str(row["document_url"]),
            content_type=str(row["content_type"]) if row["content_type"] is not None else None,
            byte_length=int(row["byte_length"]),
            content_bytes=content,
            retrieved_at=row["retrieved_at"],
            last_verified_at=row["last_verified_at"],
        )

    def verified_text(self) -> str:
        """Verify exact bytes and decode without silently discarding evidence."""
        actual_length = len(self.content_bytes)
        if actual_length > MAX_SEC_DOCUMENT_BYTES:
            raise SecDocumentIntegrityError(f"SEC document exceeds {MAX_SEC_DOCUMENT_BYTES} byte safety limit")
        if self.byte_length != actual_length:
            raise SecDocumentIntegrityError(
                f"SEC document byte length mismatch: stored={self.byte_length}, actual={actual_length}"
            )
        if not _DIGEST_RE.fullmatch(self.content_sha256):
            raise SecDocumentIntegrityError("SEC document digest has an invalid shape")
        actual_digest = hashlib.sha256(self.content_bytes).hexdigest()
        if actual_digest != self.content_sha256:
            raise SecDocumentIntegrityError("SEC document digest does not match content bytes")

        form = self.form_type.upper()
        expected_kind = "complete_submission" if form.startswith("8-K") else "primary"
        if form not in _SUPPORTED_FORMS or self.document_kind != expected_kind:
            raise SecDocumentIntegrityError(
                f"SEC document kind {self.document_kind!r} is invalid for form {self.form_type!r}"
            )

        parsed_url = urlsplit(self.document_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc != "www.sec.gov"
            or not parsed_url.path.startswith("/Archives/edgar/data/")
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise SecDocumentIntegrityError("SEC document URL is not a canonical SEC archive URL")

        return self.content_bytes.decode("utf-8", errors="surrogateescape")

    def provenance(self) -> dict[str, Any]:
        """Return serialization-safe source metadata for downstream audit trails."""
        return {
            "accession_number": self.accession_no,
            "content_sha256": self.content_sha256,
            "document_kind": self.document_kind,
            "cik": str(self.issuer_cik),
            "ticker": self.issuer_ticker,
            "form_type": self.form_type,
            "is_amendment": self.is_amendment,
            "filing_date": self.filed_at.isoformat(),
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "available_at": self.available_at.isoformat(),
            "period_end": self.report_period_end.isoformat() if self.report_period_end else None,
            "form_url": self.document_url,
            "content_type": self.content_type,
            "byte_length": self.byte_length,
            "retrieved_at": self.retrieved_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat(),
        }


_SELECT_DOCUMENTS = """
SELECT accession_no, content_sha256, document_kind, issuer_cik, issuer_ticker,
       form_type, is_amendment, filed_at, accepted_at, available_at,
       report_period_end, document_url, content_type, byte_length,
       content_bytes, retrieved_at, last_verified_at
FROM sec_filing_document
WHERE issuer_ticker = :symbol
  AND form_type IN (:base_form, :amended_form)
  AND document_kind = :document_kind
  AND available_at <= :as_of
  AND retrieved_at <= :as_of
  AND byte_length <= :max_document_bytes
  AND (CAST(:period_start AS DATE) IS NULL OR report_period_end >= CAST(:period_start AS DATE))
  AND (CAST(:period_end AS DATE) IS NULL OR report_period_end <= CAST(:period_end AS DATE))
ORDER BY available_at DESC, retrieved_at DESC, accepted_at DESC NULLS LAST,
         accession_no DESC, content_sha256 DESC
LIMIT :limit
"""


class PostgresSecDocumentStore:
    """Small, read-only PostgreSQL adapter for immutable SEC documents."""

    def __init__(
        self,
        database_url: str | URL | None = None,
        *,
        config: Any | None = None,
        engine: Engine | Any | None = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
            return

        resolved_url = database_url or self._database_url(config)
        candidate = create_engine(
            resolved_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        if candidate.url.get_backend_name() != "postgresql":
            candidate.dispose()
            raise ValueError("SEC document store requires PostgreSQL")
        self._engine = candidate

    @staticmethod
    def _database_url(config: Any | None) -> str | URL:
        explicit_url = os.getenv("SEC_DOCUMENT_DATABASE_URL")
        if explicit_url:
            return explicit_url

        env_fields = {
            "host": os.getenv("SEC_DB_HOST"),
            "port": os.getenv("SEC_DB_PORT"),
            "database": os.getenv("SEC_DB_NAME"),
            "username": os.getenv("SEC_DB_USER"),
            "password": os.getenv("SEC_DB_PASSWORD"),
        }
        if all(value is not None for value in env_fields.values()):
            return URL.create(
                "postgresql+psycopg2",
                username=env_fields["username"],
                password=env_fields["password"],
                host=env_fields["host"],
                port=int(env_fields["port"] or "5432"),
                database=env_fields["database"],
            )

        database = getattr(config, "database", None)
        if database is not None:
            return URL.create(
                "postgresql+psycopg2",
                username=getattr(database, "username", None),
                password=getattr(database, "password", None),
                host=getattr(database, "host", None),
                port=getattr(database, "port", None),
                database=getattr(database, "database", None),
            )

        raise ValueError("Configure SEC_DOCUMENT_DATABASE_URL or all SEC_DB_HOST/PORT/NAME/USER/PASSWORD variables")

    @staticmethod
    def _query_params(
        symbol: str,
        form_type: str,
        period: str,
        as_of: datetime,
        limit: int,
    ) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        normalized_form = form_type.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        if normalized_form not in {"10-K", "10-Q", "8-K"}:
            raise ValueError("form_type must be 10-K, 10-Q, or 8-K")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone")

        period_start, period_end = _parse_period(period)
        return {
            "symbol": normalized_symbol,
            "base_form": normalized_form,
            "amended_form": f"{normalized_form}/A",
            "document_kind": "complete_submission" if normalized_form == "8-K" else "primary",
            "as_of": as_of.astimezone(UTC),
            "max_document_bytes": MAX_SEC_DOCUMENT_BYTES,
            "period_start": period_start,
            "period_end": period_end,
            "limit": limit,
        }

    def _read(self, params: dict[str, Any]) -> list[StoredSecDocument]:
        with self._engine.connect() as connection:
            rows = connection.execute(text(_SELECT_DOCUMENTS), params).mappings().all()
        return [StoredSecDocument.from_mapping(row) for row in rows]

    async def get_latest_document(
        self,
        symbol: str,
        form_type: str,
        period: str,
        as_of: datetime,
    ) -> StoredSecDocument | None:
        """Return the newest document that existed at ``as_of``."""
        params = self._query_params(symbol, form_type, period, as_of, limit=1)
        documents = await asyncio.to_thread(self._read, params)
        return documents[0] if documents else None

    async def list_recent_documents(
        self,
        symbol: str,
        form_type: str,
        as_of: datetime,
        *,
        limit: int = 5,
    ) -> list[StoredSecDocument]:
        """Return a bounded list of recent documents available at ``as_of``."""
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        params = self._query_params(symbol, form_type, "latest", as_of, limit=limit)
        return await asyncio.to_thread(self._read, params)

    def close(self) -> None:
        """Dispose pooled database connections."""
        self._engine.dispose()


def _parse_period(period: str) -> tuple[date | None, date | None]:
    normalized = (period or "latest").strip()
    if normalized.lower() == "latest":
        return None, None

    quarter_match = _QUARTER_RE.fullmatch(normalized)
    if quarter_match:
        year = int(quarter_match.group("year"))
        quarter = int(quarter_match.group("quarter"))
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        if quarter == 4:
            next_quarter = date(year + 1, 1, 1)
        else:
            next_quarter = date(year, start_month + 3, 1)
        return start, date.fromordinal(next_quarter.toordinal() - 1)

    try:
        exact = date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("period must be 'latest', YYYY-Q1..Q4, or an ISO date") from exc
    return exact, exact
