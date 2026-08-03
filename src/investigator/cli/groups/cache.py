"""
Cache management commands for InvestiGator CLI
"""

import sys
from pathlib import Path

import click


@click.group()
@click.pass_context
def cache(ctx):
    """Cache management commands

    Manage analysis caches including LLM responses, SEC data, and technical data.

    Examples:
        investigator cache clean --all
        investigator cache clean --symbol AAPL
        investigator cache inspect --symbol AAPL
        investigator cache sizes
    """


@cache.command("clean")
@click.option("--all", "clean_all", is_flag=True, help="Clean all caches")
@click.option("--db", "clean_db", is_flag=True, help="Clean database cache only")
@click.option("--disk", "clean_disk", is_flag=True, help="Clean disk cache only")
@click.option("--symbol", "-s", help="Clean cache for specific symbol")
@click.option(
    "--type",
    "cache_type",
    type=click.Choice(["llm", "sec", "technical", "market_context"]),
    help="Clean specific cache type",
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def clean(ctx, clean_all, clean_db, clean_disk, symbol, cache_type, force):
    """Clean analysis caches

    Remove cached data to force fresh fetches on next analysis.

    Examples:
        investigator cache clean --all
        investigator cache clean --symbol AAPL
        investigator cache clean --type llm
    """
    from investigator.infrastructure.cache import get_cache_manager
    from investigator.infrastructure.cache.cache_types import CacheType

    cache_manager = get_cache_manager()

    # Confirmation for all
    if clean_all and not force:
        if not click.confirm("This will delete ALL cached data. Continue?"):
            click.echo("Cancelled")
            return

    try:
        if clean_all:
            click.echo("Cleaning all caches...")
            for ct in CacheType:
                try:
                    cache_manager.clear(ct)
                except Exception:
                    pass
            click.echo("All caches cleared")

        elif clean_db:
            click.echo("Cleaning database cache...")
            if symbol:
                _clean_db_symbol(cache_manager, symbol)
            else:
                cache_manager.clear(CacheType.LLM_RESPONSE, storage_type="rdbms")
                cache_manager.clear(CacheType.COMPANY_FACTS, storage_type="rdbms")
                cache_manager.clear(CacheType.SEC_RESPONSE, storage_type="rdbms")
            click.echo("Database cache cleared")

        elif clean_disk:
            click.echo("Cleaning disk cache...")
            if symbol:
                _clean_disk_symbol(cache_manager, symbol)
            else:
                cache_manager.clear(CacheType.LLM_RESPONSE, storage_type="disk")
                cache_manager.clear(CacheType.TECHNICAL_DATA, storage_type="disk")
                cache_manager.clear(CacheType.SEC_RESPONSE, storage_type="disk")
            click.echo("Disk cache cleared")

        elif symbol:
            click.echo(f"Cleaning cache for {symbol}...")
            cache_manager.delete_by_symbol(symbol.upper())
            click.echo(f"Cache cleared for {symbol}")

        elif cache_type:
            type_map = {
                "llm": CacheType.LLM_RESPONSE,
                "sec": CacheType.SEC_RESPONSE,
                "technical": CacheType.TECHNICAL_DATA,
                "market_context": CacheType.MARKET_CONTEXT,
            }
            ct = type_map.get(cache_type)
            if ct:
                cache_manager.clear(ct)
                click.echo(f"{cache_type} cache cleared")

        else:
            click.echo("Cleaning LLM response cache...")
            cache_manager.clear(CacheType.LLM_RESPONSE)
            click.echo("LLM response cache cleared")

    except Exception as e:
        click.echo(f"Error cleaning cache: {e}", err=True)
        sys.exit(1)


def _clean_db_symbol(cache_manager, symbol: str):
    """Clean database cache for specific symbol"""
    from investigator.infrastructure.cache.rdbms_cache_handler import (
        RdbmsCacheStorageHandler,
    )

    deleted = 0
    for handlers in cache_manager.handlers.values():
        for handler in handlers:
            if isinstance(handler, RdbmsCacheStorageHandler):
                try:
                    deleted += handler.delete_by_symbol(symbol)
                except Exception:
                    pass
    click.echo(f"Deleted {deleted} database cache entries for {symbol}")


def _clean_disk_symbol(cache_manager, symbol: str):
    """Clean disk cache for specific symbol"""
    from investigator.infrastructure.cache.file_cache_handler import (
        FileCacheStorageHandler,
    )

    deleted = 0
    for handlers in cache_manager.handlers.values():
        for handler in handlers:
            if isinstance(handler, FileCacheStorageHandler):
                try:
                    deleted += handler.delete_by_symbol(symbol)
                except Exception:
                    pass
    click.echo(f"Deleted {deleted} disk cache entries for {symbol}")


@cache.command("inspect")
@click.option("--symbol", "-s", help="Inspect cache for specific symbol")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.pass_context
def inspect(ctx, symbol, verbose):
    """Inspect cache contents and statistics

    View what data is cached for a symbol or overall cache stats.

    Examples:
        investigator cache inspect
        investigator cache inspect --symbol AAPL --verbose
    """
    from investigator.infrastructure.cache import get_cache_manager
    from investigator.infrastructure.cache.cache_types import CacheType

    cache_manager = get_cache_manager()

    click.echo("Cache Inspection Report")
    click.echo("=" * 60)

    if symbol:
        symbol = symbol.upper()
        click.echo(f"\nSymbol: {symbol}")
        click.echo("-" * 40)

        for cache_type in CacheType:
            try:
                key = {"symbol": symbol}
                data = cache_manager.get(cache_type, key)
                if data:
                    size = len(str(data))
                    click.echo(f"  {cache_type.value:20s}: CACHED ({size:,} bytes)")
                    if verbose and isinstance(data, dict):
                        for k in list(data.keys())[:3]:
                            click.echo(f"    - {k}")
                else:
                    click.echo(f"  {cache_type.value:20s}: NOT CACHED")
            except Exception:
                click.echo(f"  {cache_type.value:20s}: ERROR")
    else:
        click.echo("\nCache Statistics:")
        click.echo("-" * 40)

        stats = cache_manager.get_stats() if hasattr(cache_manager, "get_stats") else {}
        if stats:
            for key, value in stats.items():
                click.echo(f"  {key}: {value}")
        else:
            click.echo("  Statistics not available")
            click.echo("\n  Use --symbol to inspect specific symbol cache")


@cache.command("sizes")
@click.pass_context
def sizes(ctx):
    """Show cache sizes by type

    Displays disk space used by each cache directory.
    """
    click.echo("Cache Directory Sizes")
    click.echo("=" * 60)

    cache_dirs = {
        "SEC Cache": "data/sec_cache",
        "LLM Cache": "data/llm_cache",
        "Technical Cache": "data/technical_cache",
        "Vector DB": "data/vector_db",
        "Reports": "reports",
        "Results": "results",
    }

    total_size = 0
    for name, path in cache_dirs.items():
        if Path(path).exists():
            size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
            total_size += size
            size_mb = size / (1024 * 1024)
            count = sum(1 for _ in Path(path).rglob("*") if _.is_file())
            click.echo(f"{name:20s}: {size_mb:10.2f} MB  ({count:,} files)")
        else:
            click.echo(f"{name:20s}: Not found")

    click.echo("-" * 60)
    click.echo(f"{'Total':20s}: {total_size / (1024 * 1024):10.2f} MB")


@cache.command("warm")
@click.option("--symbols", "-s", help="Comma-separated symbols to cache")
@click.option(
    "--file",
    "-f",
    "symbols_file",
    type=click.Path(exists=True),
    help="File with symbols",
)
@click.option("--parallel", "-p", default=5, type=int, help="Parallel fetch workers")
@click.option(
    "--process-raw/--raw-only",
    default=False,
    show_default=True,
    help="Also populate sec_companyfacts_processed so analysis can consume latest filings",
)
@click.option(
    "--force-refresh",
    is_flag=True,
    help="Bypass 90-day SEC raw cache reuse and fetch fresh CompanyFacts from SEC API",
)
@click.option(
    "--include-submissions",
    is_flag=True,
    help="Also fetch and cache submissions (filing list) along with CompanyFacts",
)
@click.pass_context
def warm(ctx, symbols, symbols_file, parallel, process_raw, force_refresh, include_submissions):
    """Warm up cache for symbols

    Pre-fetch data for symbols without running full analysis.

    Examples:
        investigator cache warm --symbols AAPL,MSFT,GOOGL
        investigator cache warm --file sp100.txt --parallel 10
        investigator cache warm --symbols STX --process-raw --force-refresh
        investigator cache warm --symbols AAPL --include-submissions
    """
    import asyncio

    # Load symbols
    symbol_list = []
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
    elif symbols_file:
        with open(symbols_file) as f:
            symbol_list = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    else:
        click.echo("Provide --symbols or --file", err=True)
        sys.exit(1)

    click.echo(f"Warming cache for {len(symbol_list)} symbols...")
    click.echo(f"Parallel workers: {parallel}")
    click.echo(
        "Mode: "
        + ("raw + processed ingestion" if process_raw else "raw-only cache")
        + (", force-refresh enabled" if force_refresh else "")
        + (", +submissions" if include_submissions else "")
    )

    async def warm_cache():
        from investigator.domain.agents.sec import SECAnalysisAgent
        from investigator.infrastructure.cache import get_cache_manager
        from investigator.infrastructure.events import EventBus
        from investigator.infrastructure.sec.sec_api import SECApiClient

        cache_manager = get_cache_manager()
        event_bus = EventBus()
        sec_agent = SECAnalysisAgent(
            "cache_warmer",
            ollama_client=None,
            event_bus=event_bus,
            cache_manager=cache_manager,
        )
        sec_client = SECApiClient()

        sem = asyncio.Semaphore(parallel)
        results = []

        async def fetch(symbol: str):
            async with sem:
                try:
                    # Step 1: Fetch CompanyFacts
                    await sec_agent._fetch_and_cache_companyfacts(
                        symbol,
                        process_raw=process_raw,
                        force_refresh=force_refresh,
                    )
                    results.append((symbol, True, ""))
                    click.echo(f"  Cached: {symbol}{' (processed)' if process_raw else ' (raw-only)'}")

                    # Step 2: Optionally fetch submissions
                    if include_submissions:
                        try:
                            cik = sec_client._resolve_cik(symbol)
                            if cik:
                                await sec_client._load_submissions(symbol, cik)
                                click.echo(f"    + Submissions cached for {symbol}")
                        except Exception as e:
                            click.echo(f"    ! Submissions fetch failed for {symbol}: {e}")

                except Exception as e:
                    results.append((symbol, False, str(e)))
                    click.echo(f"  Failed: {symbol} - {e}")

        await asyncio.gather(*(fetch(s) for s in symbol_list))

        success = sum(1 for _, ok, _ in results if ok)
        click.echo(f"\nCompleted: {success}/{len(results)} symbols cached")

    asyncio.run(warm_cache())


@cache.command("stats")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def stats(ctx, json_output):
    """Show cache hit/miss statistics

    Displays cache performance metrics.
    """
    import json

    from investigator.infrastructure.cache import get_cache_manager

    cache_manager = get_cache_manager()

    stats = {}
    if hasattr(cache_manager, "get_stats"):
        stats = cache_manager.get_stats()

    # Add computed metrics
    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0

    stats["hit_rate_pct"] = hit_rate
    stats["total_requests"] = total

    if json_output:
        click.echo(json.dumps(stats, indent=2, default=str))
        return

    click.echo("Cache Performance Statistics")
    click.echo("=" * 60)
    click.echo(f"  Hits:       {hits:,}")
    click.echo(f"  Misses:     {misses:,}")
    click.echo(f"  Hit Rate:   {hit_rate:.1f}%")
    click.echo(f"  Total:      {total:,}")

    if "avg_latency_ms" in stats:
        click.echo(f"  Avg Latency: {stats['avg_latency_ms']:.1f}ms")


@cache.command("refresh-submissions")
@click.option("--symbols", "-s", help="Comma-separated symbols to refresh")
@click.option(
    "--file",
    "-f",
    "symbols_file",
    type=click.Path(exists=True),
    help="File with symbols",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.pass_context
def refresh_submissions(ctx, symbols, symbols_file, verbose):
    """Refresh SEC submissions cache from EDGAR

    Force refresh only the submissions (filing list) cache from SEC EDGAR.
    This fetches the latest 10-K, 10-Q, 8-K and other filings without
    touching CompanyFacts or other cached data.

    Use this after a company files earnings to get the latest filings.

    Examples:
        investigator cache refresh-submissions --symbols ZS
        investigator cache refresh-submissions --file earnings_watchlist.txt
        investigator cache refresh-submissions --symbols AAPL,MSFT --verbose
    """
    import asyncio

    from investigator.infrastructure.cache.cache_types import CacheType
    from investigator.infrastructure.cache.file_cache_handler import (
        FileCacheStorageHandler,
    )
    from investigator.infrastructure.sec.sec_api import SECApiClient

    # Load symbols
    symbol_list = []
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
    elif symbols_file:
        with open(symbols_file) as f:
            symbol_list = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    else:
        click.echo("Provide --symbols or --file", err=True)
        sys.exit(1)

    click.echo(f"Refreshing submissions cache for {len(symbol_list)} symbols...")
    click.echo()

    async def refresh_symbol(symbol: str) -> dict:
        """Refresh submissions for a single symbol"""
        result = {
            "symbol": symbol,
            "success": False,
            "cik": None,
            "latest_filings": [],
            "error": None,
        }

        try:
            # Initialize SEC API client
            client = SECApiClient()

            # Resolve CIK
            cik = client._resolve_cik(symbol)
            if not cik:
                result["error"] = "Could not resolve CIK"
                return result

            result["cik"] = cik

            # Delete existing submissions cache
            cache_key = {"symbol": symbol, "cik": cik}
            cache_manager = client.cache_manager

            # Try to delete from file cache
            try:
                for handlers in cache_manager.handlers.get(CacheType.SUBMISSION_DATA, []):
                    if isinstance(handlers, FileCacheStorageHandler):
                        handlers.delete(cache_key)
                        if verbose:
                            click.echo(f"  {symbol}: Deleted old submissions cache")
            except Exception as e:
                if verbose:
                    click.echo(f"  {symbol}: No existing cache to delete ({e})")

            # Fetch fresh submissions from SEC
            submissions = await client._load_submissions(symbol, cik)

            # Extract recent filings info
            recent = submissions.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accs = recent.get("accessionNumber", [])

            # Get latest 5 filings
            for i in range(min(len(forms), 5)):
                result["latest_filings"].append(
                    {
                        "form": forms[i],
                        "filed": dates[i],
                        "accession": accs[i],
                    }
                )

            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    async def refresh_all():
        """Refresh all symbols"""
        tasks = [refresh_symbol(s) for s in symbol_list]
        results = await asyncio.gather(*tasks)

        # Display results
        success = 0
        for r in results:
            symbol = r["symbol"]
            if r["success"]:
                success += 1
                click.echo(f"✅ {symbol}: Refreshed successfully")
                if verbose:
                    click.echo(f"   CIK: {r['cik']}")
                    click.echo("   Latest filings:")
                    for f in r["latest_filings"]:
                        click.echo(f"     {f['form']:8} | {f['filed']} | {f['accession']}")
            else:
                click.echo(f"❌ {symbol}: Failed - {r['error']}", err=True)

        click.echo()
        click.echo(f"Completed: {success}/{len(results)} symbols refreshed")

    asyncio.run(refresh_all())
