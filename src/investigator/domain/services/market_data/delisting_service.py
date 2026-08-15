"""Delisting events service.

Reads/writes the ``delisting_events`` table and computes the realized terminal
exit value when a position's holding period spans a delisting. This lets the RL
backtest model a delisting as a (usually loss-bearing) terminal exit instead of
silently dropping the observation — removing the delisting half of survivorship
bias (audit finding C).

The DB access is isolated in ``get_delisting``/``upsert_delisting``; the exit math
is a pure staticmethod (``terminal_exit_price``) so it is unit-testable without a
database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Default fraction of last price realized at exit, by delisting reason.
RECOVERY_BY_REASON: dict[str, float] = {
    "bankruptcy": 0.0,
    "compliance": 0.0,  # delisted for non-compliance (penny stock / filing failure)
    "voluntary": 0.0,
    "acquired": 1.0,  # acquisition typically realizes ~last price (refine with deal price)
    "unknown": 0.0,  # conservative default
}


@dataclass
class DelistingRecord:
    symbol: str
    delist_date: date
    reason: str = "unknown"
    last_price: float | None = None
    recovery_assumption: float | None = None
    acquirer_symbol: str | None = None
    source: str = "unknown"

    def effective_recovery(self) -> float:
        if self.recovery_assumption is not None:
            return float(self.recovery_assumption)
        return RECOVERY_BY_REASON.get((self.reason or "unknown").lower(), 0.0)


class DelistingService:
    """Lookup and apply delisting terminal exits."""

    def __init__(self, db_manager: Any | None = None):
        if db_manager is None:
            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
        self.db = db_manager

    # ------------------------------------------------------------------ pure logic
    @staticmethod
    def terminal_exit_price(record: DelistingRecord | None, target_date: date) -> float | None:
        """Realized exit price if the position is held through a delisting.

        Returns ``last_price * recovery`` when the symbol delisted on or before
        ``target_date`` and a last price is known; otherwise None (no terminal
        event applies for that horizon).
        """
        if record is None or record.last_price is None:
            return None
        if record.delist_date > target_date:
            return None  # delisting happens after this horizon; not terminal yet
        return round(float(record.last_price) * record.effective_recovery(), 4)

    # ------------------------------------------------------------------ DB access
    def get_delisting(self, symbol: str) -> DelistingRecord | None:
        """Return the (earliest) delisting event for a symbol, or None."""
        from sqlalchemy import text

        try:
            with self.db.get_session() as session:
                row = session.execute(
                    text(
                        """
                        SELECT symbol, delist_date, reason, last_price,
                               recovery_assumption, acquirer_symbol, source
                        FROM delisting_events
                        WHERE symbol = :symbol
                        ORDER BY delist_date ASC
                        LIMIT 1
                        """
                    ),
                    {"symbol": symbol.upper()},
                ).fetchone()
        except Exception as exc:  # noqa: BLE001 - lookup is best-effort
            logger.debug("Delisting lookup failed for %s: %s", symbol, exc)
            return None

        if not row:
            return None
        return DelistingRecord(
            symbol=row[0],
            delist_date=row[1],
            reason=row[2] or "unknown",
            last_price=float(row[3]) if row[3] is not None else None,
            recovery_assumption=float(row[4]) if row[4] is not None else None,
            acquirer_symbol=row[5],
            source=row[6] or "unknown",
        )

    def get_delistings(self, symbols: list[str]) -> dict[str, DelistingRecord]:
        """Batch lookup: {symbol: earliest DelistingRecord} for symbols that delisted."""
        from sqlalchemy import text

        if not symbols:
            return {}
        result: dict[str, DelistingRecord] = {}
        try:
            with self.db.get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT DISTINCT ON (symbol)
                               symbol, delist_date, reason, last_price,
                               recovery_assumption, acquirer_symbol, source
                        FROM delisting_events
                        WHERE symbol = ANY(:symbols)
                        ORDER BY symbol, delist_date ASC
                        """
                    ),
                    {"symbols": [s.upper() for s in symbols]},
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Batch delisting lookup failed: %s", exc)
            return {}

        for row in rows:
            result[row[0]] = DelistingRecord(
                symbol=row[0],
                delist_date=row[1],
                reason=row[2] or "unknown",
                last_price=float(row[3]) if row[3] is not None else None,
                recovery_assumption=float(row[4]) if row[4] is not None else None,
                acquirer_symbol=row[5],
                source=row[6] or "unknown",
            )
        return result

    def upsert_delisting(self, record: DelistingRecord) -> bool:
        """Insert or update a delisting event (idempotent on symbol+delist_date)."""
        from sqlalchemy import text

        try:
            with self.db.get_session() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO delisting_events (
                            symbol, delist_date, reason, last_price,
                            recovery_assumption, acquirer_symbol, source, updated_at
                        ) VALUES (
                            :symbol, :delist_date, :reason, :last_price,
                            :recovery_assumption, :acquirer_symbol, :source, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (symbol, delist_date) DO UPDATE SET
                            reason = EXCLUDED.reason,
                            last_price = COALESCE(EXCLUDED.last_price, delisting_events.last_price),
                            recovery_assumption = EXCLUDED.recovery_assumption,
                            acquirer_symbol = EXCLUDED.acquirer_symbol,
                            source = EXCLUDED.source,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "symbol": record.symbol.upper(),
                        "delist_date": record.delist_date,
                        "reason": record.reason,
                        "last_price": record.last_price,
                        "recovery_assumption": record.effective_recovery(),
                        "acquirer_symbol": record.acquirer_symbol,
                        "source": record.source,
                    },
                )
                session.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upsert delisting for %s: %s", record.symbol, exc)
            return False
