#!/usr/bin/env python3
"""Materialize a bounded batch of canonical SEC section outcomes."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime

from victor_invest.sec_section_materializer import PostgresSecDerivedSectionStore, materialize_pending_sections


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--as-of must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="maximum source documents (1-100)")
    parser.add_argument("--as-of", type=_aware_datetime, default=None, help="timezone-aware evidence cutoff")
    parser.add_argument("--dry-run", action="store_true", help="derive and count without writing outcomes")
    args = parser.parse_args()

    store = PostgresSecDerivedSectionStore()
    try:
        summary = materialize_pending_sections(
            store=store,
            limit=args.limit,
            as_of=args.as_of or datetime.now(UTC),
            dry_run=args.dry_run,
        )
        print(json.dumps(asdict(summary), sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
