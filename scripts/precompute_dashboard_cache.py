#!/usr/bin/env python3
"""
Precompute dashboard-ready analysis cache for a stock universe slice.

Runs `cli_orchestrator.py analyze` sequentially for symbols selected from the
`symbol` table and writes canonical UI cache records to `artifacts/ui_cache`.

Example:
  python scripts/precompute_dashboard_cache.py \
    --max-stockid 1000 \
    --mode comprehensive \
    --valuation-basis forward \
    --forward-horizon 1y \
    --force-refresh
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from investigator.infrastructure.database.symbol_repository import SymbolRepository


@dataclass
class SymbolRow:
    ticker: str
    stockid: int
    sector: str


def _is_analysis_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    schema = str(payload.get("schema_version", ""))
    if schema.startswith("analysis.compact.") or "agents" in payload or "valuation" in payload:
        return True
    return "summary" in payload and ("fundamental" in payload or "technical" in payload)


def _extract_payload_from_stdout(raw: str, symbol: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None

    marker_index = raw.rfind("[Full Analysis]")
    candidates: List[str] = []
    if marker_index >= 0:
        candidates.append(raw[marker_index + len("[Full Analysis]") :])
    candidates.append(raw)

    decoder = json.JSONDecoder()
    symbol_upper = symbol.upper()
    for candidate in candidates:
        start = candidate.find("{")
        if start < 0:
            continue
        blob = candidate[start:].lstrip()
        try:
            parsed, _ = decoder.raw_decode(blob)
        except Exception:
            continue
        if _is_analysis_payload(parsed):
            parsed_symbol = str(parsed.get("symbol", "")).upper()
            if not parsed_symbol or parsed_symbol == symbol_upper:
                return parsed
    return None


def _load_payload_from_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return parsed if _is_analysis_payload(parsed) else None


def _write_ui_cache(cache_dir: Path, symbol: str, payload: Dict[str, Any], source: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol.upper()}.json"
    record = {
        "symbol": symbol.upper(),
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }
    cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return cache_path


def _load_symbols(
    *,
    min_stockid: int,
    max_stockid: int,
    limit: Optional[int],
    us_only: bool,
) -> List[SymbolRow]:
    repo = SymbolRepository()
    filters = [
        "islisted = TRUE",
        "isstock = TRUE",
        "(isetf IS NULL OR isetf = FALSE)",
        "stockid IS NOT NULL",
        "stockid >= :min_stockid",
        "stockid <= :max_stockid",
    ]
    if us_only:
        filters.append("cik IS NOT NULL")

    limit_clause = "LIMIT :limit" if limit and limit > 0 else ""
    query = text(
        f"""
        SELECT ticker, stockid, COALESCE(sec_sector, 'Unknown') AS sec_sector
        FROM symbol
        WHERE {' AND '.join(filters)}
        ORDER BY stockid ASC
        {limit_clause}
    """
    )

    params: Dict[str, Any] = {"min_stockid": min_stockid, "max_stockid": max_stockid}
    if limit and limit > 0:
        params["limit"] = int(limit)

    with repo.stock_engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [SymbolRow(ticker=str(r[0]).upper(), stockid=int(r[1]), sector=str(r[2])) for r in rows]


def _source_env_vars(env_file: Path) -> Dict[str, str]:
    """
    Source a shell env file and return exported variables.

    Uses `bash -lc` so shell syntax in ~/.investigator/env is respected.
    """
    if not env_file.exists():
        return {}

    wrapped = f"source {shlex.quote(str(env_file))} >/dev/null 2>&1 && env -0"
    proc = subprocess.run(
        ["bash", "-lc", wrapped],
        text=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return {}

    out: Dict[str, str] = {}
    for chunk in proc.stdout.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        key, value = chunk.split(b"=", 1)
        try:
            out[key.decode("utf-8")] = value.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out


def _parse_symbols_arg(raw_symbols: str) -> List[SymbolRow]:
    tokens = [token.strip().upper() for token in (raw_symbols or "").replace("\n", ",").split(",")]
    clean = [token for token in tokens if token]
    deduped = list(dict.fromkeys(clean))
    return [SymbolRow(ticker=symbol, stockid=-1, sector="Unknown") for symbol in deduped]


def _build_command(
    *,
    python_bin: str,
    symbol: str,
    mode: str,
    output_path: Path,
    valuation_basis: str,
    forward_horizon: str,
    force_refresh: bool,
) -> List[str]:
    cmd = [
        python_bin,
        "cli_orchestrator.py",
        "analyze",
        symbol,
        "-m",
        mode,
        "--detail-level",
        "compact",
        "--format",
        "json",
        "--output",
        str(output_path),
        "--valuation-basis",
        valuation_basis,
        "--forward-horizon",
        forward_horizon,
    ]
    if force_refresh:
        cmd.append("--force-refresh")
    return cmd


def _run_command(
    *,
    cmd: List[str],
    repo_root: Path,
    env: Dict[str, str],
    source_env_file: Optional[Path],
) -> subprocess.CompletedProcess[str]:
    if source_env_file and source_env_file.exists():
        shell_cmd = " ".join(shlex.quote(part) for part in cmd)
        wrapped = f"source {shlex.quote(str(source_env_file))} && {shell_cmd}"
        return subprocess.run(
            ["bash", "-lc", wrapped],
            cwd=str(repo_root),
            env=env,
            text=True,
            capture_output=True,
        )

    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
    )


def _extract_failure_hint(output: str) -> Optional[str]:
    text_blob = output or ""
    if "Database credentials for 'stock' not found" in text_blob:
        return "Stock DB credentials not loaded. Source ~/.investigator/env or pass --source-env-file."
    if "No Ollama servers available" in text_blob:
        return "No Ollama endpoint reachable. Ensure Ollama/remote endpoint is up and env is loaded."
    if "NameError: name 'List' is not defined" in text_blob:
        return "Code import error (List). Pull latest code including the data_normalizer typing fix."
    return None


def _format_eta(seconds: float) -> str:
    if seconds < 0:
        return "unknown"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = repo_root / "artifacts" / "ui_cache"
    run_dir = cache_dir / "precompute_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    run_stamp = started_at.strftime("%Y%m%d_%H%M%S")

    source_env_file: Optional[Path] = None
    if args.source_env_file:
        source_env_file = Path(args.source_env_file).expanduser()

    # Load runtime credentials into this process before DB symbol lookup.
    if not args.no_source_env and source_env_file and source_env_file.exists():
        sourced = _source_env_vars(source_env_file)
        if sourced:
            os.environ.update(sourced)

    if args.symbols:
        symbols = _parse_symbols_arg(args.symbols)
    else:
        try:
            symbols = _load_symbols(
                min_stockid=args.min_stockid,
                max_stockid=args.max_stockid,
                limit=args.limit,
                us_only=not args.include_non_us,
            )
        except Exception as exc:
            print(f"Failed to load symbols from database: {exc}", flush=True)
            return 1

    if not symbols:
        print("No symbols matched the selection criteria.", flush=True)
        return 1

    if args.symbols:
        print(
            f"Loaded {len(symbols)} symbols from --symbols "
            f"(mode={args.mode}, basis={args.valuation_basis}/{args.forward_horizon})",
            flush=True,
        )
    else:
        print(
            f"Loaded {len(symbols)} symbols (stockid {args.min_stockid}..{args.max_stockid}, "
            f"mode={args.mode}, basis={args.valuation_basis}/{args.forward_horizon})",
            flush=True,
        )
    if args.skip_cached:
        print("Skip mode: existing artifacts/ui_cache/<SYMBOL>.json entries will be reused.", flush=True)

    run_log: Dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "mode": args.mode,
        "valuation_basis": args.valuation_basis,
        "forward_horizon": args.forward_horizon,
        "min_stockid": args.min_stockid,
        "max_stockid": args.max_stockid,
        "limit": args.limit,
        "force_refresh": bool(args.force_refresh),
        "skip_cached": bool(args.skip_cached),
        "results": [],
    }

    success_count = 0
    fail_count = 0
    skipped_count = 0
    durations: List[float] = []

    python_bin = args.python_bin or sys.executable
    env = os.environ.copy()
    if args.legacy:
        env.setdefault("INVESTIGATOR_LEGACY", "1")

    total = len(symbols)
    hint_counts: Dict[str, int] = {}
    for idx, row in enumerate(symbols, start=1):
        symbol = row.ticker
        canonical_cache_path = cache_dir / f"{symbol}.json"
        if args.skip_cached and canonical_cache_path.exists():
            skipped_count += 1
            run_log["results"].append(
                {
                    "symbol": symbol,
                    "stockid": row.stockid,
                    "status": "skipped_cached",
                    "cache_file": str(canonical_cache_path),
                }
            )
            print(f"[{idx}/{total}] {symbol:<8} stockid={row.stockid:<5} skipped (cached)", flush=True)
            continue

        tick_start = time.time()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        refresh_file = cache_dir / f"{symbol}_refresh_{timestamp}.json"
        cmd = _build_command(
            python_bin=python_bin,
            symbol=symbol,
            mode=args.mode,
            output_path=refresh_file,
            valuation_basis=args.valuation_basis,
            forward_horizon=args.forward_horizon,
            force_refresh=bool(args.force_refresh),
        )

        proc = _run_command(
            cmd=cmd,
            repo_root=repo_root,
            env=env,
            source_env_file=source_env_file if not args.no_source_env else None,
        )
        duration = time.time() - tick_start
        durations.append(duration)

        payload = _load_payload_from_file(refresh_file)
        if payload is None:
            payload = _extract_payload_from_stdout(proc.stdout or "", symbol)

        status = "success" if proc.returncode == 0 and payload else "error"
        entry: Dict[str, Any] = {
            "symbol": symbol,
            "stockid": row.stockid,
            "sector": row.sector,
            "status": status,
            "returncode": int(proc.returncode),
            "duration_seconds": round(duration, 3),
            "refresh_file": str(refresh_file),
        }

        if status == "success":
            cached_path = _write_ui_cache(cache_dir, symbol, payload, source="precompute_wrapper")
            entry["cache_file"] = str(cached_path)
            summary = payload.get("recommendation", {}) if isinstance(payload.get("recommendation"), dict) else {}
            entry["action"] = summary.get("action")
            entry["confidence_score"] = summary.get("confidence_score")
            success_count += 1
            print(
                f"[{idx}/{total}] {symbol:<8} stockid={row.stockid:<5} ok "
                f"({duration:.1f}s, action={entry.get('action')})",
                flush=True,
            )
        else:
            fail_count += 1
            stdout_tail = (proc.stdout or "")[-3000:]
            stderr_tail = (proc.stderr or "")[-1500:]
            entry["stdout_tail"] = stdout_tail
            entry["stderr_tail"] = stderr_tail
            print(
                f"[{idx}/{total}] {symbol:<8} stockid={row.stockid:<5} failed "
                f"(rc={proc.returncode}, {duration:.1f}s)",
                flush=True,
            )
            combined_output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
            hint = _extract_failure_hint(combined_output)
            if hint:
                hint_counts[hint] = hint_counts.get(hint, 0) + 1
                if hint_counts[hint] <= 3:
                    print(f"          hint: {hint}", flush=True)
            if not args.continue_on_error:
                run_log["results"].append(entry)
                break

        run_log["results"].append(entry)

        avg = sum(durations) / len(durations) if durations else 0.0
        remaining = total - idx
        eta = _format_eta(avg * remaining)
        print(
            f"          progress: success={success_count}, failed={fail_count}, " f"skipped={skipped_count}, eta={eta}",
            flush=True,
        )

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

        if not args.keep_refresh_files and refresh_file.exists():
            try:
                refresh_file.unlink()
            except OSError:
                pass

    ended_at = datetime.now(timezone.utc)
    elapsed = (ended_at - started_at).total_seconds()
    run_log["completed_at"] = ended_at.isoformat()
    run_log["duration_seconds"] = round(elapsed, 3)
    run_log["summary"] = {
        "total_selected": total,
        "success": success_count,
        "failed": fail_count,
        "skipped_cached": skipped_count,
    }

    run_log_file = run_dir / f"precompute_{run_stamp}.json"
    run_log_file.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nDone.", flush=True)
    print(
        f"  success={success_count}, failed={fail_count}, skipped={skipped_count}, " f"elapsed={_format_eta(elapsed)}",
        flush=True,
    )
    print(f"  run log: {run_log_file}", flush=True)

    return 0 if fail_count == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Precompute sequential dashboard cache from symbol table.")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbol list (skips DB lookup), e.g. AAPL,MSFT,TRV",
    )
    parser.add_argument("--min-stockid", type=int, default=1, help="Minimum stockid to include (default: 1)")
    parser.add_argument("--max-stockid", type=int, default=1000, help="Maximum stockid to include (default: 1000)")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap after stockid filtering")
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "comprehensive"],
        default="comprehensive",
        help="Analysis mode for cli_orchestrator.py",
    )
    parser.add_argument(
        "--valuation-basis",
        choices=["ttm", "forward"],
        default="forward",
        help="Valuation basis used for analysis",
    )
    parser.add_argument(
        "--forward-horizon",
        choices=["1q", "2q", "3q", "1y"],
        default="1y",
        help="Forward horizon for forward basis",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Pass --force-refresh into each per-symbol analyze call",
    )
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        default=True,
        help="Skip symbols that already have artifacts/ui_cache/<SYMBOL>.json",
    )
    parser.add_argument(
        "--no-skip-cached",
        dest="skip_cached",
        action="store_false",
        help="Recompute even when canonical UI cache files already exist",
    )
    parser.add_argument(
        "--include-non-us",
        action="store_true",
        help="Include symbols without CIK (default filters to domestic SEC filers only)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional sleep between symbols (default: 0)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        default=True,
        help="Continue processing remaining symbols when one symbol fails (default: on)",
    )
    parser.add_argument(
        "--stop-on-error",
        dest="continue_on_error",
        action="store_false",
        help="Abort at first failed symbol",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        default=True,
        help="Set INVESTIGATOR_LEGACY=1 while executing analyses (default: on)",
    )
    parser.add_argument(
        "--no-legacy",
        dest="legacy",
        action="store_false",
        help="Do not force legacy orchestrator environment",
    )
    parser.add_argument(
        "--keep-refresh-files",
        action="store_true",
        help="Keep per-run *_refresh_*.json payload files (default removes after cache write)",
    )
    parser.add_argument(
        "--python-bin",
        default=None,
        help="Python interpreter for invoking cli_orchestrator.py (default: current interpreter)",
    )
    parser.add_argument(
        "--source-env-file",
        default="~/.investigator/env",
        help="Shell env file to source before each analysis command (default: ~/.investigator/env)",
    )
    parser.add_argument(
        "--no-source-env",
        action="store_true",
        help="Do not source env file before running per-symbol analysis commands",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    raise SystemExit(run(parser.parse_args()))
