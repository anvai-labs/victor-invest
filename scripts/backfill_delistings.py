#!/usr/bin/env python3
"""Backfill delisting events from SEC EDGAR into ``delisting_events``.

For each symbol: resolve its CIK, scan EDGAR submissions for a Form 25/25-NSE
(removal from listing) or Form 15 (deregistration), set ``last_price`` from the
final ``tickerdata`` close (rows stop at delisting), and upsert the event.

Requires DB + EDGAR connectivity.

Usage:
    source ~/.investigator/env
    python3 scripts/backfill_delistings.py --symbols LEHMQ BBBYQ SIVBQ
    python3 scripts/backfill_delistings.py --symbols-file data/maybe_delisted.txt
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _load_symbols(args: argparse.Namespace) -> list[str]:
    symbols: list[str] = list(args.symbols or [])
    if args.symbols_file:
        with open(args.symbols_file) as fh:
            symbols.extend(line.strip() for line in fh if line.strip())
    return [s.upper() for s in symbols]


async def _run(symbols: list[str]) -> int:
    from investigator.domain.services.market_data.delisting_service import DelistingService
    from investigator.domain.services.market_data.price_service import PriceService
    from investigator.infrastructure.sec.delisting_extractor import backfill_delisting
    from investigator.infrastructure.sec.sec_api import SECApiClient

    sec_client = SECApiClient()
    price_service = PriceService()
    delisting_service = DelistingService()

    found = 0
    for symbol in symbols:
        cik = None
        if getattr(sec_client, "ticker_mapper", None):
            cik = sec_client.ticker_mapper.get_cik_padded(symbol)
        if not cik:
            logger.warning("No CIK for %s; skipping", symbol)
            continue

        record = await backfill_delisting(
            symbol=symbol,
            cik=cik,
            sec_client=sec_client,
            last_close_lookup=price_service.get_last_close,
        )
        if record is None:
            logger.info("%s: no delisting event found", symbol)
            continue
        if delisting_service.upsert_delisting(record):
            found += 1
            logger.info(
                "%s: delisted %s (%s), last_price=%s source=%s",
                symbol,
                record.delist_date,
                record.reason,
                record.last_price,
                record.source,
            )

    logger.info("Delisting backfill complete: %d events upserted across %d symbols", found, len(symbols))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill delisting events from SEC EDGAR")
    parser.add_argument("--symbols", nargs="*", help="Symbols to check for delisting")
    parser.add_argument("--symbols-file", help="File with one symbol per line")
    args = parser.parse_args()

    symbols = _load_symbols(args)
    if not symbols:
        parser.error("Provide --symbols or --symbols-file")
    return asyncio.run(_run(symbols))


if __name__ == "__main__":
    sys.exit(main())
