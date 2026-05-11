#!/usr/bin/env python3
"""
Validate forward-guidance extraction quality on a representative symbol basket.

Basket composition:
1) Top N symbols by market cap in each sector (default: N=5)
2) FAANG symbols
3) AI-trade symbols

The script can run fresh analyses (default) or inspect existing UI cache records.
It produces a JSON + CSV report with issue flags and summary metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import bindparam, text

from investigator.infrastructure.database.symbol_repository import SymbolRepository

DEFAULT_FAANG = ["META", "AAPL", "AMZN", "NFLX", "GOOGL"]
DEFAULT_AI_TRADE = [
    "NVDA",
    "MSFT",
    "AMD",
    "AVGO",
    "SMCI",
    "PLTR",
    "TSM",
    "ARM",
    "MU",
    "QCOM",
    "ANET",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "MSTR",
]


@dataclass
class BasketSymbol:
    ticker: str
    sector: str = "Unknown"
    mktcap: Optional[float] = None
    sources: List[str] = field(default_factory=list)


def _normalize_symbol_list(raw: str) -> List[str]:
    tokens = [t.strip().upper() for t in (raw or "").replace("\n", ",").split(",")]
    return [t for t in tokens if t]


def _source_env_vars(env_file: Path) -> Dict[str, str]:
    if not env_file.exists():
        return {}
    wrapped = f"source {shlex.quote(str(env_file))} >/dev/null 2>&1 && env -0"
    proc = subprocess.run(["bash", "-lc", wrapped], text=False, capture_output=True)
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


def _is_analysis_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    schema = str(payload.get("schema_version", ""))
    if schema.startswith("analysis.compact."):
        return True
    return "valuation" in payload and ("price" in payload or "recommendation" in payload)


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


def _load_cached_ui_payload(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        record = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    payload = record.get("payload") if isinstance(record, dict) else None
    return payload if _is_analysis_payload(payload) else None


def _write_ui_cache(cache_dir: Path, symbol: str, payload: Dict[str, Any], source: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / f"{symbol.upper()}.json"
    record = {
        "symbol": symbol.upper(),
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }
    out_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return out_path


def _build_analyze_command(
    *,
    python_bin: str,
    symbol: str,
    mode: str,
    valuation_basis: str,
    forward_horizon: str,
    output_path: Path,
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
    return subprocess.run(cmd, cwd=str(repo_root), env=env, text=True, capture_output=True)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _load_top_per_sector(
    repo: SymbolRepository,
    *,
    top_n: int,
    us_only: bool,
) -> List[BasketSymbol]:
    filters = [
        "islisted = TRUE",
        "isstock = TRUE",
        "(isetf IS NULL OR isetf = FALSE)",
        "mktcap IS NOT NULL",
        "mktcap > 0",
    ]
    if us_only:
        filters.append("cik IS NOT NULL")

    query = text(
        f"""
        WITH ranked AS (
            SELECT
                ticker,
                COALESCE(sec_sector, "Sector", 'Unknown') AS sector,
                mktcap,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(sec_sector, "Sector", 'Unknown')
                    ORDER BY mktcap DESC NULLS LAST, stockid ASC NULLS LAST
                ) AS rn
            FROM symbol
            WHERE {" AND ".join(filters)}
        )
        SELECT ticker, sector, mktcap
        FROM ranked
        WHERE rn <= :top_n
        ORDER BY sector ASC, mktcap DESC NULLS LAST
    """
    )

    with repo.stock_engine.connect() as conn:
        rows = conn.execute(query, {"top_n": max(1, top_n)}).fetchall()

    symbols: List[BasketSymbol] = []
    for row in rows:
        ticker = str(row[0]).upper()
        sector = str(row[1] or "Unknown")
        mktcap = _coerce_float(row[2])
        symbols.append(BasketSymbol(ticker=ticker, sector=sector, mktcap=mktcap, sources=["top_per_sector"]))
    return symbols


def _enrich_symbol_metadata(repo: SymbolRepository, symbols: Iterable[str]) -> Dict[str, Tuple[str, Optional[float]]]:
    tickers = [s.upper() for s in symbols if s]
    if not tickers:
        return {}

    query = text(
        """
            SELECT ticker, COALESCE(sec_sector, "Sector", 'Unknown') AS sector, mktcap
            FROM symbol
            WHERE ticker IN :tickers
        """
    ).bindparams(bindparam("tickers", expanding=True))

    with repo.stock_engine.connect() as conn:
        rows = conn.execute(query, {"tickers": tickers}).fetchall()
    return {str(r[0]).upper(): (str(r[1] or "Unknown"), _coerce_float(r[2])) for r in rows}


def _merge_basket(
    *,
    top_per_sector: List[BasketSymbol],
    faang: List[str],
    ai_trade: List[str],
    manual_symbols: List[str],
    metadata_lookup: Dict[str, Tuple[str, Optional[float]]],
) -> List[BasketSymbol]:
    merged: Dict[str, BasketSymbol] = {}

    def _upsert(
        symbol: str,
        source: str,
        sector: str = "Unknown",
        mktcap: Optional[float] = None,
    ) -> None:
        ticker = symbol.upper()
        existing = merged.get(ticker)
        meta_sector, meta_mktcap = metadata_lookup.get(ticker, (sector, mktcap))
        if existing is None:
            merged[ticker] = BasketSymbol(
                ticker=ticker,
                sector=meta_sector or sector or "Unknown",
                mktcap=meta_mktcap if meta_mktcap is not None else mktcap,
                sources=[source],
            )
            return

        if source not in existing.sources:
            existing.sources.append(source)
        if existing.sector == "Unknown" and meta_sector:
            existing.sector = meta_sector
        if existing.mktcap is None and meta_mktcap is not None:
            existing.mktcap = meta_mktcap

    for row in top_per_sector:
        _upsert(row.ticker, "top_per_sector", sector=row.sector, mktcap=row.mktcap)
    for symbol in faang:
        _upsert(symbol, "faang")
    for symbol in ai_trade:
        _upsert(symbol, "ai_trade")
    for symbol in manual_symbols:
        _upsert(symbol, "manual")

    return list(merged.values())


def _contains_markup(snippet: str) -> bool:
    if not snippet:
        return False
    lowered = snippet.lower()
    return any(token in lowered for token in ("<xbrli:", "<xbrl", "xbrli:", "<div", "<table"))


def _collect_guidance_applied_models(payload: Dict[str, Any]) -> List[str]:
    valuation = payload.get("valuation")
    if not isinstance(valuation, dict):
        return []
    models = valuation.get("models")
    if not isinstance(models, dict):
        return []

    applied: List[str] = []
    for model_name, model_payload in models.items():
        if not isinstance(model_payload, dict):
            continue
        assumptions = model_payload.get("assumptions")
        if not isinstance(assumptions, dict):
            continue
        if assumptions.get("guidance_applied"):
            applied.append(str(model_name))
    return applied


def _analyze_issues(
    *,
    payload: Dict[str, Any],
    weak_conf_threshold: float,
    eps_high_cap: float,
    max_target_multiple: float,
    min_target_multiple: float,
) -> Tuple[str, List[Dict[str, str]]]:
    issues: List[Dict[str, str]] = []

    sec = payload.get("sec")
    fg = sec.get("forward_guidance") if isinstance(sec, dict) else None
    fg = fg if isinstance(fg, dict) else {}

    revenue_guidance = fg.get("revenue_guidance") if isinstance(fg.get("revenue_guidance"), dict) else None
    eps_guidance = fg.get("eps_guidance") if isinstance(fg.get("eps_guidance"), dict) else None
    has_any_range = bool(revenue_guidance or eps_guidance)

    confidence = _coerce_float(fg.get("confidence_score")) or 0.0
    growth_values = [
        _coerce_float(fg.get("revenue_growth_guidance")),
        _coerce_float(fg.get("earnings_growth_guidance")),
    ]
    growth_values = [v for v in growth_values if v is not None]

    if not fg:
        issues.append({"severity": "medium", "code": "missing_forward_guidance"})
    elif not has_any_range and growth_values and confidence <= weak_conf_threshold:
        issues.append({"severity": "high", "code": "weak_growth_only_guidance"})
        if all(abs(v) < 1e-9 for v in growth_values):
            issues.append({"severity": "high", "code": "zero_growth_only_guidance"})

    for range_blob in (revenue_guidance, eps_guidance):
        if not isinstance(range_blob, dict):
            continue
        snippet = str(range_blob.get("snippet", ""))
        if _contains_markup(snippet):
            issues.append({"severity": "medium", "code": "guidance_snippet_markup_leak"})
            break

    if isinstance(eps_guidance, dict):
        low = _coerce_float(eps_guidance.get("low"))
        high = _coerce_float(eps_guidance.get("high"))
        if high is not None and high > eps_high_cap:
            issues.append({"severity": "high", "code": "eps_guidance_out_of_bounds"})
        if low is not None and high is not None and low > 0 and (high / max(low, 1e-9)) > 5.0:
            issues.append({"severity": "high", "code": "eps_guidance_ratio_outlier"})

    guidance_applied_models = _collect_guidance_applied_models(payload)
    if guidance_applied_models and not fg:
        issues.append({"severity": "high", "code": "guidance_applied_without_payload"})

    price = payload.get("price") if isinstance(payload.get("price"), dict) else {}
    valuation = payload.get("valuation") if isinstance(payload.get("valuation"), dict) else {}
    current = _coerce_float(price.get("current"))
    target = _coerce_float(valuation.get("blended_fair_value"))
    if current and target and current > 0:
        ratio = target / current
        if ratio > max_target_multiple:
            issues.append({"severity": "high", "code": "target_multiple_too_high"})
        elif ratio < min_target_multiple:
            issues.append({"severity": "high", "code": "target_multiple_too_low"})

    status = "pass"
    if any(i["severity"] == "high" for i in issues):
        status = "fail"
    elif issues:
        status = "warn"
    return status, issues


def _load_symbol_payload(
    *,
    symbol: str,
    args: argparse.Namespace,
    repo_root: Path,
    cache_dir: Path,
    validate_run_dir: Path,
    env: Dict[str, str],
    source_env_file: Optional[Path],
) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
    cache_path = cache_dir / f"{symbol}.json"
    if args.use_cache_only or (args.skip_cached and cache_path.exists() and not args.force_refresh):
        payload = _load_cached_ui_payload(cache_path)
        status = "cache_hit" if payload else "cache_missing_or_invalid"
        return status, payload, {"cache_path": str(cache_path)}

    output_path = validate_run_dir / f"{symbol}_validation_{int(time.time() * 1000)}.json"
    cmd = _build_analyze_command(
        python_bin=args.python_bin or sys.executable,
        symbol=symbol,
        mode=args.mode,
        valuation_basis=args.valuation_basis,
        forward_horizon=args.forward_horizon,
        output_path=output_path,
        force_refresh=bool(args.force_refresh),
    )
    started = time.time()
    proc = _run_command(
        cmd=cmd,
        repo_root=repo_root,
        env=env,
        source_env_file=source_env_file if not args.no_source_env else None,
    )
    duration = round(time.time() - started, 3)

    payload = _load_payload_from_file(output_path)
    if payload is None:
        payload = _extract_payload_from_stdout(proc.stdout or "", symbol)
    if output_path.exists() and not args.keep_validation_outputs:
        try:
            output_path.unlink()
        except OSError:
            pass

    if proc.returncode == 0 and payload:
        _write_ui_cache(cache_dir, symbol, payload, source="guidance_validation")
        return "analyzed", payload, {"duration_seconds": duration}

    return (
        "analyze_failed",
        None,
        {
            "duration_seconds": duration,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-3000:],
            "stderr_tail": (proc.stderr or "")[-1500:],
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate forward-guidance robustness on top-sector/FAANG/AI baskets.")
    parser.add_argument(
        "--top-per-sector",
        type=int,
        default=5,
        help="Top symbols per sector by market cap (set 0 to disable sector basket).",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "comprehensive"],
        default="comprehensive",
    )
    parser.add_argument("--valuation-basis", choices=["ttm", "forward"], default="forward")
    parser.add_argument("--forward-horizon", choices=["1q", "2q", "3q", "1y"], default="1y")
    parser.add_argument("--symbols", default="", help="Extra comma-separated symbols.")
    parser.add_argument(
        "--manual-only",
        action="store_true",
        help="Use only --symbols (ignore top-per-sector, FAANG, and AI defaults).",
    )
    parser.add_argument("--faang-symbols", default=",".join(DEFAULT_FAANG))
    parser.add_argument("--ai-symbols", default=",".join(DEFAULT_AI_TRADE))
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional cap after basket build.")
    parser.add_argument(
        "--include-non-us",
        action="store_true",
        help="Include non-US filers in sector top list.",
    )
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        default=True,
        help="Use cached UI payloads when present.",
    )
    parser.add_argument("--no-skip-cached", dest="skip_cached", action="store_false")
    parser.add_argument(
        "--use-cache-only",
        action="store_true",
        help="Do not run analyses; validate cache only.",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Force fresh analysis runs.")
    parser.add_argument("--legacy", action="store_true", default=True, help="Set INVESTIGATOR_LEGACY=1.")
    parser.add_argument("--no-legacy", dest="legacy", action="store_false")
    parser.add_argument("--python-bin", default=None, help="Python interpreter for analyze command.")
    parser.add_argument("--source-env-file", default="~/.investigator/env")
    parser.add_argument("--no-source-env", action="store_true")
    parser.add_argument("--weak-confidence-threshold", type=float, default=0.25)
    parser.add_argument("--eps-high-cap", type=float, default=250.0)
    parser.add_argument("--max-target-multiple", type=float, default=10.0)
    parser.add_argument("--min-target-multiple", type=float, default=0.1)
    parser.add_argument(
        "--fail-on-high-issues",
        action="store_true",
        help="Exit non-zero when any high issue is found.",
    )
    parser.add_argument(
        "--keep-validation-outputs",
        action="store_true",
        help="Keep per-symbol raw output files.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = repo_root / "artifacts" / "ui_cache"
    reports_dir = repo_root / "artifacts" / "reports"
    validate_run_dir = cache_dir / "validation_runs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    validate_run_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    source_env_file: Optional[Path] = None
    if args.source_env_file:
        source_env_file = Path(args.source_env_file).expanduser()

    if not args.no_source_env and source_env_file and source_env_file.exists():
        sourced = _source_env_vars(source_env_file)
        if sourced:
            os.environ.update(sourced)

    repo = SymbolRepository()
    manual_symbols = _normalize_symbol_list(args.symbols)

    top_rows: List[BasketSymbol] = []
    faang: List[str] = []
    ai_trade: List[str] = []
    if not args.manual_only and args.top_per_sector > 0:
        try:
            top_rows = _load_top_per_sector(
                repo,
                top_n=args.top_per_sector,
                us_only=not args.include_non_us,
            )
        except Exception as exc:
            print(
                f"Warning: failed to load top-per-sector basket from DB: {exc}",
                flush=True,
            )
    if not args.manual_only:
        faang = _normalize_symbol_list(args.faang_symbols)
        ai_trade = _normalize_symbol_list(args.ai_symbols)
    metadata_lookup: Dict[str, Tuple[str, Optional[float]]] = {}

    try:
        metadata_lookup = _enrich_symbol_metadata(
            repo,
            [r.ticker for r in top_rows] + faang + ai_trade + manual_symbols,
        )
    except Exception:
        metadata_lookup = {}

    basket = _merge_basket(
        top_per_sector=top_rows,
        faang=faang,
        ai_trade=ai_trade,
        manual_symbols=manual_symbols,
        metadata_lookup=metadata_lookup,
    )
    if args.max_symbols and args.max_symbols > 0:
        basket = basket[: args.max_symbols]

    if not basket:
        print("No symbols in validation basket.", flush=True)
        return 1

    print(
        f"Validation basket size={len(basket)} "
        f"(top_per_sector={len(top_rows)}, faang={len(faang)}, ai={len(ai_trade)}, manual={len(manual_symbols)})",
        flush=True,
    )

    env = os.environ.copy()
    if args.legacy:
        env.setdefault("INVESTIGATOR_LEGACY", "1")

    results: List[Dict[str, Any]] = []
    issue_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    sector_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pass": 0, "warn": 0, "fail": 0, "skipped": 0, "error": 0}
    )

    total = len(basket)
    durations: List[float] = []
    for idx, row in enumerate(basket, start=1):
        started = time.time()
        load_status, payload, detail = _load_symbol_payload(
            symbol=row.ticker,
            args=args,
            repo_root=repo_root,
            cache_dir=cache_dir,
            validate_run_dir=validate_run_dir,
            env=env,
            source_env_file=source_env_file,
        )
        elapsed = round(time.time() - started, 3)
        durations.append(elapsed)

        result: Dict[str, Any] = {
            "symbol": row.ticker,
            "sector": row.sector,
            "sources": list(row.sources),
            "mktcap": row.mktcap,
            "load_status": load_status,
            "duration_seconds": elapsed,
            "issues": [],
            "status": "error",
        }
        result.update(detail)

        if payload:
            status, issues = _analyze_issues(
                payload=payload,
                weak_conf_threshold=args.weak_confidence_threshold,
                eps_high_cap=args.eps_high_cap,
                max_target_multiple=args.max_target_multiple,
                min_target_multiple=args.min_target_multiple,
            )
            result["status"] = status
            result["issues"] = issues
            sec = payload.get("sec") if isinstance(payload.get("sec"), dict) else {}
            fg = sec.get("forward_guidance") if isinstance(sec.get("forward_guidance"), dict) else {}
            price = payload.get("price") if isinstance(payload.get("price"), dict) else {}
            valuation = payload.get("valuation") if isinstance(payload.get("valuation"), dict) else {}
            result["guidance"] = {
                "source": fg.get("source"),
                "source_form": fg.get("source_form"),
                "filing_date": fg.get("filing_date"),
                "confidence_score": fg.get("confidence_score"),
                "has_revenue_guidance": bool(isinstance(fg.get("revenue_guidance"), dict)),
                "has_eps_guidance": bool(isinstance(fg.get("eps_guidance"), dict)),
                "revenue_growth_guidance": fg.get("revenue_growth_guidance"),
                "earnings_growth_guidance": fg.get("earnings_growth_guidance"),
            }
            result["valuation_snapshot"] = {
                "current_price": price.get("current"),
                "target_price": valuation.get("blended_fair_value"),
                "expected_return_pct": price.get("expected_return_pct"),
                "action": (
                    (payload.get("recommendation") or {}).get("action")
                    if isinstance(payload.get("recommendation"), dict)
                    else None
                ),
            }
            for issue in issues:
                issue_counter[issue["code"]] += 1
        else:
            if args.use_cache_only and load_status == "cache_missing_or_invalid":
                result["status"] = "skipped"
            else:
                result["status"] = "error"
                issue_counter["analysis_unavailable"] += 1

        status_counter[result["status"]] += 1
        sector_bucket = sector_counts[row.sector]
        sector_bucket["total"] += 1
        if result["status"] in {"pass", "warn", "fail", "skipped", "error"}:
            sector_bucket[result["status"]] += 1

        avg = sum(durations) / len(durations)
        remaining = max(total - idx, 0)
        eta = int(avg * remaining)
        print(
            f"[{idx}/{total}] {row.ticker:<8} {result['status']:<5} "
            f"load={load_status:<18} issues={len(result['issues'])} eta={eta}s",
            flush=True,
        )
        results.append(result)

    ended_at = datetime.now(timezone.utc)
    summary = {
        "started_at": started_at.isoformat(),
        "completed_at": ended_at.isoformat(),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
        "basket_size": len(basket),
        "status_counts": dict(status_counter),
        "issue_counts": dict(issue_counter),
        "sector_counts": dict(sector_counts),
        "config": {
            "top_per_sector": args.top_per_sector,
            "valuation_basis": args.valuation_basis,
            "forward_horizon": args.forward_horizon,
            "mode": args.mode,
            "force_refresh": bool(args.force_refresh),
            "use_cache_only": bool(args.use_cache_only),
            "weak_confidence_threshold": args.weak_confidence_threshold,
            "eps_high_cap": args.eps_high_cap,
            "max_target_multiple": args.max_target_multiple,
            "min_target_multiple": args.min_target_multiple,
        },
    }
    report = {"summary": summary, "results": results}

    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"forward_guidance_validation_{stamp}.json"
    csv_path = reports_dir / f"forward_guidance_validation_{stamp}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "symbol",
                "sector",
                "status",
                "load_status",
                "issue_codes",
                "guidance_form",
                "guidance_confidence",
                "has_revenue_guidance",
                "has_eps_guidance",
                "revenue_growth_guidance",
                "earnings_growth_guidance",
                "current_price",
                "target_price",
                "expected_return_pct",
                "action",
                "sources",
            ]
        )
        for row in results:
            guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else {}
            valuation_snapshot = (
                row.get("valuation_snapshot") if isinstance(row.get("valuation_snapshot"), dict) else {}
            )
            issue_codes = ",".join(i.get("code", "") for i in row.get("issues", []))
            writer.writerow(
                [
                    row.get("symbol"),
                    row.get("sector"),
                    row.get("status"),
                    row.get("load_status"),
                    issue_codes,
                    guidance.get("source_form"),
                    guidance.get("confidence_score"),
                    guidance.get("has_revenue_guidance"),
                    guidance.get("has_eps_guidance"),
                    guidance.get("revenue_growth_guidance"),
                    guidance.get("earnings_growth_guidance"),
                    valuation_snapshot.get("current_price"),
                    valuation_snapshot.get("target_price"),
                    valuation_snapshot.get("expected_return_pct"),
                    valuation_snapshot.get("action"),
                    ",".join(row.get("sources", [])),
                ]
            )

    print("", flush=True)
    print(f"Report JSON: {json_path}", flush=True)
    print(f"Report CSV : {csv_path}", flush=True)
    print(
        f"Summary -> pass={status_counter.get('pass', 0)}, warn={status_counter.get('warn', 0)}, "
        f"fail={status_counter.get('fail', 0)}, skipped={status_counter.get('skipped', 0)}, "
        f"error={status_counter.get('error', 0)}",
        flush=True,
    )
    if issue_counter:
        top_issues = ", ".join(f"{k}:{v}" for k, v in issue_counter.most_common(8))
        print(f"Top issues: {top_issues}", flush=True)

    if args.fail_on_high_issues and status_counter.get("fail", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    parser = build_parser()
    raise SystemExit(run(parser.parse_args()))
