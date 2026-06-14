#!/usr/bin/env python3
"""Load point-in-time index membership from a CSV into ``index_membership``.

Source-agnostic: the CSV can come from a paid feed (Sharadar/Norgate/CRSP) or a
free reconstruction (e.g. historical S&P change lists). Expected columns:

    symbol,index_name,effective_date,removal_date,source

``removal_date`` may be blank (still a member). Dates are ISO (YYYY-MM-DD).

Usage:
    source ~/.investigator/env
    python3 scripts/load_index_membership.py --csv data/sp500_membership.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    return date.fromisoformat(value[:10])


def main() -> int:
    parser = argparse.ArgumentParser(description="Load index membership CSV into index_membership")
    parser.add_argument("--csv", required=True, help="Path to membership CSV")
    parser.add_argument("--default-source", default="csv_import", help="Source label when a row omits one")
    args = parser.parse_args()

    from investigator.domain.services.market_data.universe_service import UniverseService

    service = UniverseService()
    loaded = 0
    skipped = 0
    with open(args.csv, newline="") as fh:
        for row in csv.DictReader(fh):
            symbol = (row.get("symbol") or "").strip().upper()
            index_name = (row.get("index_name") or "").strip()
            effective = _parse_date(row.get("effective_date"))
            if not symbol or not index_name or effective is None:
                skipped += 1
                continue
            ok = service.upsert_membership(
                symbol=symbol,
                index_name=index_name,
                effective_date=effective,
                removal_date=_parse_date(row.get("removal_date")),
                source=(row.get("source") or args.default_source).strip(),
            )
            loaded += 1 if ok else 0
            skipped += 0 if ok else 1

    logger.info("Index membership load complete: %d upserted, %d skipped", loaded, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
