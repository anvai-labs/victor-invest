"""Canonical backtest/universe selection service.

One place to choose the universe of symbols, with two modes:

- **live**: today's snapshot (current `islisted`/index flags) — correct for the
  production ``analyze``/screener paths, but survivorship-biased for backtests.
- **pit**: point-in-time membership as of a past date from ``index_membership``,
  including names later delisted — survivorship-free when paired with the
  ``delisting_events`` terminal-exit handling.

The membership-as-of filter is a pure staticmethod (``members_as_of``) so it is
unit-testable without a database. ``get_universe`` orchestrates mode selection and
reports ``survivorship_safe`` honestly: True only when a real PIT membership set
backs the result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class UniverseMember:
    symbol: str
    index_name: Optional[str] = None
    sector: Optional[str] = None


@dataclass
class UniverseResult:
    members: List[UniverseMember] = field(default_factory=list)
    as_of_date: Optional[date] = None
    mode: str = "live"
    index_name: Optional[str] = None
    survivorship_safe: bool = False
    source: str = "live_snapshot"

    @property
    def symbols(self) -> List[str]:
        return [m.symbol for m in self.members]


class UniverseService:
    def __init__(self, db_manager: Optional[Any] = None):
        if db_manager is None:
            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
        self.db = db_manager

    # ------------------------------------------------------------------ pure logic
    @staticmethod
    def members_as_of(rows: Sequence[Dict[str, Any]], as_of_date: date) -> List[str]:
        """Symbols whose membership window contains ``as_of_date``.

        Each row needs ``symbol``, ``effective_date`` and optional ``removal_date``
        (None = still a member). Inclusive of the effective date, exclusive of the
        removal date.
        """
        out: List[str] = []
        for row in rows:
            eff = row.get("effective_date")
            rem = row.get("removal_date")
            if eff is None or eff > as_of_date:
                continue
            if rem is not None and rem <= as_of_date:
                continue
            sym = row.get("symbol")
            if sym:
                out.append(str(sym).upper())
        return out

    # ------------------------------------------------------------------ PIT (DB)
    def has_membership_data(self, index_name: str) -> bool:
        from sqlalchemy import text

        try:
            with self.db.get_session() as session:
                row = session.execute(
                    text("SELECT 1 FROM index_membership WHERE index_name = :idx LIMIT 1"),
                    {"idx": index_name},
                ).fetchone()
                return row is not None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Membership-data check failed for %s: %s", index_name, exc)
            return False

    def get_pit_universe(self, index_name: str, as_of_date: date) -> UniverseResult:
        from sqlalchemy import text

        members: List[UniverseMember] = []
        try:
            with self.db.get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT symbol, index_name
                        FROM index_membership
                        WHERE index_name = :idx
                          AND effective_date <= :as_of
                          AND (removal_date IS NULL OR removal_date > :as_of)
                        ORDER BY symbol
                        """
                    ),
                    {"idx": index_name, "as_of": as_of_date},
                ).fetchall()
            members = [UniverseMember(symbol=str(r[0]).upper(), index_name=r[1]) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("PIT universe query failed for %s @ %s: %s", index_name, as_of_date, exc)

        return UniverseResult(
            members=members,
            as_of_date=as_of_date,
            mode="pit",
            index_name=index_name,
            survivorship_safe=bool(members),
            source="index_membership",
        )

    # ------------------------------------------------------------------ live (DB)
    def get_live_universe(
        self,
        index: Optional[str] = None,
        top_n: Optional[int] = None,
        sector: Optional[str] = None,
    ) -> UniverseResult:
        from sqlalchemy import text

        where = [
            "COALESCE(islisted, true) = true",
            "COALESCE(isstock, true) = true",
            "COALESCE(isetf, false) = false",
            "stockid IS NOT NULL",
        ]
        params: Dict[str, Any] = {}
        if index:
            where.append(f"COALESCE({index}, false) = true")  # index is a controlled column name
        if sector:
            where.append("sec_sector = :sector")
            params["sector"] = sector
        limit_clause = ""
        if top_n:
            limit_clause = "LIMIT :limit"
            params["limit"] = top_n

        sql = (
            "SELECT ticker, sec_sector FROM symbol "
            f"WHERE {' AND '.join(where)} ORDER BY mktcap DESC NULLS LAST {limit_clause}"
        )
        members: List[UniverseMember] = []
        try:
            with self.db.get_session() as session:
                rows = session.execute(text(sql), params).fetchall()
            members = [UniverseMember(symbol=str(r[0]).upper(), index_name=index, sector=r[1]) for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live universe query failed: %s", exc)

        return UniverseResult(
            members=members,
            as_of_date=None,
            mode="live",
            index_name=index,
            survivorship_safe=False,
            source="live_snapshot",
        )

    # ------------------------------------------------------------------ orchestration
    def get_universe(
        self,
        as_of_date: Optional[date] = None,
        index: Optional[str] = None,
        top_n: Optional[int] = None,
        sector: Optional[str] = None,
        mode: str = "auto",
    ) -> UniverseResult:
        """Select a universe.

        mode='auto' (default): use PIT membership when an ``as_of_date`` and ``index``
        are given and membership data exists; otherwise fall back to the live
        snapshot (with ``survivorship_safe=False``). mode='live'/'pit' force a mode.
        """
        if mode == "pit" or (mode == "auto" and as_of_date and index):
            if as_of_date and index and (mode == "pit" or self.has_membership_data(index)):
                result = self.get_pit_universe(index, as_of_date)
                if result.members:
                    return result
                logger.info("No PIT membership for %s @ %s; falling back to live snapshot", index, as_of_date)

        return self.get_live_universe(index=index, top_n=top_n, sector=sector)
