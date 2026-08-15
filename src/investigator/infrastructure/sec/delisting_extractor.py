"""Extract delisting events from SEC EDGAR submissions.

EDGAR exposes a per-company submissions JSON (parallel arrays under
``filings.recent``). A delisting is signalled by Form 25 / 25-NSE (notification of
removal from listing) and, for deregistration, Form 15 variants. This module
parses those out and (optionally) backfills the last traded price.

``extract_delisting_from_submissions`` is a pure function over the submissions
dict so it is unit-testable without any network access. ``backfill_delisting``
wires it to the existing SEC client and a price lookup.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from collections.abc import Callable

from investigator.domain.services.market_data.delisting_service import DelistingRecord

logger = logging.getLogger(__name__)

# Forms that indicate removal from listing / deregistration, in priority order.
REMOVAL_FORMS = {"25", "25-NSE"}
DEREGISTRATION_FORMS = {"15-12B", "15-12G", "15-15D", "15F-12B", "15F-12G", "15F-15D", "15"}


def _parse_iso(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _recent_rows(submissions: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the parallel-array ``filings.recent`` block into per-filing dicts."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accns = recent.get("accessionNumber") or []
    rows: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        rows.append(
            {
                "form": form,
                "filing_date": dates[i] if i < len(dates) else None,
                "accession": accns[i] if i < len(accns) else None,
            }
        )
    return rows


def _symbol_from(submissions: dict[str, Any], fallback: str | None) -> str | None:
    tickers = submissions.get("tickers") or []
    if tickers:
        return str(tickers[0]).upper()
    return fallback.upper() if fallback else None


def extract_delisting_from_submissions(
    submissions: dict[str, Any],
    symbol: str | None = None,
) -> DelistingRecord | None:
    """Return the earliest delisting/deregistration event, or None.

    Prefers a Form 25/25-NSE (removal from listing) date; falls back to a Form 15
    deregistration date. Reason is left ``unknown`` (the form alone does not
    distinguish bankruptcy vs voluntary vs compliance).
    """
    rows = _recent_rows(submissions)
    sym = _symbol_from(submissions, symbol)
    if not sym:
        return None

    removal_dates: list[date] = []
    dereg_dates: list[date] = []
    for row in rows:
        form = str(row.get("form") or "").upper()
        fdate = _parse_iso(row.get("filing_date"))
        if fdate is None:
            continue
        if form in REMOVAL_FORMS:
            removal_dates.append(fdate)
        elif form in DEREGISTRATION_FORMS:
            dereg_dates.append(fdate)

    if removal_dates:
        return DelistingRecord(symbol=sym, delist_date=min(removal_dates), reason="unknown", source="edgar_form25")
    if dereg_dates:
        return DelistingRecord(symbol=sym, delist_date=min(dereg_dates), reason="unknown", source="edgar_form15")
    return None


async def backfill_delisting(
    symbol: str,
    cik: str,
    sec_client: Any,
    last_close_lookup: Callable[[str], tuple[date, float] | None] | None = None,
) -> DelistingRecord | None:
    """Fetch submissions for a symbol and extract its delisting event, if any.

    Args:
        sec_client: object exposing ``async get_submissions(cik)`` (SECFilingsClient).
        last_close_lookup: optional ``symbol -> (last_trade_date, last_close)`` used to
            backfill the terminal ``last_price``. ``PriceService.get_last_close`` is the
            intended source: a delisted name's ``tickerdata`` rows stop at delisting, so
            the final row is the last traded price. When the last-trade date is later
            than the form date, it refines ``delist_date``.
    """
    try:
        submissions = await sec_client.get_submissions(cik)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch submissions for %s (cik %s): %s", symbol, cik, exc)
        return None

    record = extract_delisting_from_submissions(submissions, symbol=symbol)
    if record is None:
        return None
    if last_close_lookup is not None and record.last_price is None:
        try:
            last = last_close_lookup(record.symbol)
            if last is not None:
                last_date, last_price = last
                record.last_price = last_price
                if last_date and last_date > record.delist_date:
                    record.delist_date = last_date
        except Exception as exc:  # noqa: BLE001
            logger.debug("Last-close backfill failed for %s: %s", record.symbol, exc)
    return record
