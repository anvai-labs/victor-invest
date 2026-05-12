#!/usr/bin/env python3
"""
Compare cached pipeline valuation vs manual valuation built from cached SEC + Yahoo metrics.

This script intentionally avoids rerunning the full pipeline. It reads:
- data/sec_cache/quarterlymetrics/<SYMBOL>/metrics_*.json.gz
- artifacts/logs/* (latest run log with [Full Analysis] JSON)
- Optional Yahoo Finance snapshot (yfinance)
- Optional direct local LLM valuation via Ollama
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass
class QuarterPoint:
    fiscal_year: int
    fiscal_period: str
    period_end_date: str
    shares_outstanding: Optional[float]
    revenue: Optional[float]
    net_income: Optional[float]
    operating_cash_flow: Optional[float]
    capex: Optional[float]
    free_cash_flow: Optional[float]
    total_debt: Optional[float]
    cash: Optional[float]
    derived: bool = False


def _read_gzip_json(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _safe_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_quarters(symbol: str) -> List[QuarterPoint]:
    base = Path("data/sec_cache/quarterlymetrics") / symbol.upper()
    files = sorted(base.glob("metrics_*.json.gz"))
    if not files:
        raise FileNotFoundError(f"No quarterly metric cache files found under {base}")

    points: List[QuarterPoint] = []
    for file in files:
        payload = _read_gzip_json(file).get("data", {})
        if not isinstance(payload, dict):
            continue

        fp = str(payload.get("fiscal_period") or "")
        fy = int(payload.get("fiscal_year") or 0)
        period_end = str(payload.get("period_end_date") or "")

        inc = payload.get("income_statement") or {}
        cf = payload.get("cash_flow") or {}
        bs = payload.get("balance_sheet") or {}

        ocf = _safe_num(cf.get("operating_cash_flow"))
        capex = _safe_num(cf.get("capital_expenditures"))
        fcf = _safe_num(cf.get("free_cash_flow"))
        if fcf in (None, 0.0) and ocf is not None and capex is not None:
            fcf = ocf - capex

        points.append(
            QuarterPoint(
                fiscal_year=fy,
                fiscal_period=fp,
                period_end_date=period_end,
                shares_outstanding=_safe_num(payload.get("shares_outstanding")),
                revenue=_safe_num(inc.get("total_revenue")),
                net_income=_safe_num(inc.get("net_income")),
                operating_cash_flow=ocf,
                capex=capex,
                free_cash_flow=fcf,
                total_debt=_safe_num(bs.get("total_debt")),
                cash=_safe_num(bs.get("cash_and_equivalents")),
                derived=False,
            )
        )
    return points


def derive_missing_q4(points: List[QuarterPoint]) -> List[QuarterPoint]:
    by_fy: Dict[int, Dict[str, QuarterPoint]] = {}
    for p in points:
        by_fy.setdefault(p.fiscal_year, {})[p.fiscal_period] = p

    derived: List[QuarterPoint] = []
    for fy, items in by_fy.items():
        if "Q4" in items:
            continue
        if not all(k in items for k in ("FY", "Q1", "Q2", "Q3")):
            continue

        fy_point = items["FY"]
        q1, q2, q3 = items["Q1"], items["Q2"], items["Q3"]

        def d(name: str) -> Optional[float]:
            vals = [getattr(q1, name), getattr(q2, name), getattr(q3, name)]
            total = getattr(fy_point, name)
            if total is None or any(v is None for v in vals):
                return None
            return float(total - sum(vals))

        q4 = QuarterPoint(
            fiscal_year=fy,
            fiscal_period="Q4",
            period_end_date=fy_point.period_end_date,
            shares_outstanding=fy_point.shares_outstanding
            or q3.shares_outstanding
            or q2.shares_outstanding
            or q1.shares_outstanding,
            revenue=d("revenue"),
            net_income=d("net_income"),
            operating_cash_flow=d("operating_cash_flow"),
            capex=d("capex"),
            free_cash_flow=None,
            total_debt=fy_point.total_debt,
            cash=fy_point.cash,
            derived=True,
        )
        if q4.operating_cash_flow is not None and q4.capex is not None:
            q4.free_cash_flow = q4.operating_cash_flow - q4.capex
        derived.append(q4)

    return points + derived


def _period_sort_key(point: QuarterPoint) -> Tuple[datetime, int]:
    dt = datetime.strptime(point.period_end_date, "%Y-%m-%d")
    rank = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}.get(point.fiscal_period, 0)
    return dt, rank


def select_recent_quarters(points: List[QuarterPoint], n: int = 8) -> List[QuarterPoint]:
    quarters = [p for p in points if p.fiscal_period.startswith("Q")]
    quarters.sort(key=_period_sort_key)
    return quarters[-n:]


def sum_metric(points: List[QuarterPoint], field: str) -> Optional[float]:
    vals = [getattr(p, field) for p in points]
    if any(v is None for v in vals):
        return None
    return float(sum(vals))


def load_pipeline_valuation_from_log(symbol: str, log_path: Optional[Path]) -> Dict[str, Any]:
    symbol = symbol.upper()

    if log_path is None:
        candidates = sorted(
            Path("artifacts/logs").glob(f"{symbol.lower()}_comprehensive_run_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError("No comprehensive run logs found under artifacts/logs")
        log_path = candidates[0]

    text = log_path.read_text(errors="ignore")
    marker = "[Full Analysis]"
    idx = text.find(marker)
    if idx < 0:
        raise ValueError(f"[Full Analysis] block not found in {log_path}")

    block = text[idx + len(marker) :]
    start = block.find("{")
    if start < 0:
        raise ValueError("Could not find JSON start after [Full Analysis] marker")

    js = block[start:]
    depth = 0
    end = None
    for i, ch in enumerate(js):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError("Could not locate end of [Full Analysis] JSON block")

    obj = json.loads(js[:end])
    fund = obj.get("agents", {}).get("fundamental", {})
    valuation = fund.get("valuation", {})
    methods = valuation.get("valuation_methods", {})

    return {
        "log_path": str(log_path),
        "fair_value_blended": _safe_num(valuation.get("fair_value_estimate")),
        "current_price": _safe_num(valuation.get("current_price")),
        "valuation_payload": valuation,
        "company_profile": valuation.get("company_profile", {}) or {},
        "ratios": fund.get("ratios", {}) or {},
        "methods": {
            "dcf_professional": methods.get("dcf_professional", {}),
            "pe": methods.get("pe", {}),
            "ev_ebitda": methods.get("ev_ebitda", {}),
            "ps": methods.get("ps", {}),
            "pb": methods.get("pb", {}),
            "ggm": methods.get("ggm", {}),
            "damodaran_dcf": methods.get("damodaran_dcf", {}),
        },
    }


def fetch_yahoo_snapshot(symbol: str) -> Dict[str, Any]:
    import yfinance as yf

    ticker = yf.Ticker(symbol.upper())
    info = ticker.info
    fast = ticker.fast_info
    return {
        "current_price": _safe_num(info.get("currentPrice")) or _safe_num(fast.get("lastPrice")),
        "market_cap": _safe_num(info.get("marketCap")) or _safe_num(fast.get("marketCap")),
        "shares_outstanding": _safe_num(info.get("sharesOutstanding")) or _safe_num(fast.get("shares")),
        "beta": _safe_num(info.get("beta")),
        "trailing_pe": _safe_num(info.get("trailingPE")),
        "forward_pe": _safe_num(info.get("forwardPE")),
        "price_to_sales": _safe_num(info.get("priceToSalesTrailing12Months")),
        "price_to_book": _safe_num(info.get("priceToBook")),
        "enterprise_value": _safe_num(info.get("enterpriseValue")),
        "ebitda": _safe_num(info.get("ebitda")),
        "enterprise_to_ebitda": _safe_num(info.get("enterpriseToEbitda")),
        "trailing_eps": _safe_num(info.get("trailingEps")),
        "source": "yahoo",
    }


def fetch_db_snapshot(symbol: str) -> Dict[str, Any]:
    from investigator.config import get_config
    from investigator.infrastructure.database.market_data import get_market_data_fetcher

    config = get_config()
    fetcher = get_market_data_fetcher(config)
    info = fetcher.get_stock_info(symbol.upper()) or {}

    return {
        "current_price": _safe_num(info.get("current_price")),
        "market_cap": _safe_num(info.get("market_cap")),
        "shares_outstanding": _safe_num(info.get("shares_outstanding")),
        "beta": _safe_num(info.get("beta")),
        "trailing_pe": None,
        "forward_pe": None,
        "price_to_sales": None,
        "price_to_book": None,
        "enterprise_value": None,
        "ebitda": None,
        "enterprise_to_ebitda": None,
        "trailing_eps": None,
        "source": "db",
    }


def fetch_pipeline_snapshot(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    company_profile = pipeline.get("company_profile", {}) or {}
    ratios = pipeline.get("ratios", {}) or {}
    methods = pipeline.get("methods", {}) or {}

    current_price = (
        _safe_num(pipeline.get("current_price"))
        or _safe_num(ratios.get("current_price"))
        or _safe_num(company_profile.get("current_price"))
    )
    market_cap = _safe_num(ratios.get("market_cap")) or _safe_num(company_profile.get("market_cap"))
    shares = _safe_num(ratios.get("shares_outstanding")) or _safe_num(company_profile.get("shares_outstanding"))
    beta = _safe_num(company_profile.get("beta"))
    trailing_pe = _safe_num(ratios.get("pe_ratio"))
    price_to_sales = _safe_num(ratios.get("price_to_sales"))
    price_to_book = _safe_num(ratios.get("price_to_book"))
    ebitda = _safe_num(company_profile.get("ebitda")) or _safe_num(
        (methods.get("ev_ebitda") or {}).get("assumptions", {}).get("ttm_ebitda")
    )
    enterprise_value = _safe_num((methods.get("ev_ebitda") or {}).get("assumptions", {}).get("enterprise_value_fair"))
    enterprise_to_ebitda = enterprise_value / ebitda if enterprise_value and ebitda and ebitda > 0 else None

    if market_cap is None and current_price and shares and shares > 0:
        market_cap = current_price * shares

    return {
        "current_price": current_price,
        "market_cap": market_cap,
        "shares_outstanding": shares,
        "beta": beta,
        "trailing_pe": trailing_pe,
        "forward_pe": None,
        "price_to_sales": price_to_sales,
        "price_to_book": price_to_book,
        "enterprise_value": enterprise_value,
        "ebitda": ebitda,
        "enterprise_to_ebitda": enterprise_to_ebitda,
        "trailing_eps": _safe_num(ratios.get("eps")),
        "source": "pipeline_log",
    }


def get_market_snapshot(symbol: str, market_source: str, pipeline: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    source = (market_source or "auto").lower()

    if source in {"auto", "yahoo"}:
        try:
            return fetch_yahoo_snapshot(symbol), errors
        except Exception as exc:
            errors.append(f"yahoo_error: {exc}")
            if source == "yahoo":
                raise

    if source in {"auto", "pipeline"}:
        pipeline_snapshot = fetch_pipeline_snapshot(pipeline)
        if pipeline_snapshot.get("current_price"):
            return pipeline_snapshot, errors
        errors.append("pipeline_error: current_price missing in pipeline log")
        if source == "pipeline":
            raise RuntimeError("; ".join(errors))

    try:
        return fetch_db_snapshot(symbol), errors
    except Exception as exc:
        errors.append(f"db_error: {exc}")
        raise RuntimeError("; ".join(errors))


def is_financial_company(sector: Optional[str], industry: Optional[str]) -> bool:
    sector_l = (sector or "").lower()
    industry_l = (industry or "").lower()
    tokens = ("financial", "bank", "insurance", "reit", "real estate")
    return any(t in sector_l for t in tokens) or any(t in industry_l for t in tokens)


def dcf_per_share(
    base_fcf: float,
    growth_rates: List[float],
    wacc: float,
    terminal_growth: float,
    net_debt: float,
    shares: float,
) -> float:
    if wacc <= terminal_growth:
        raise ValueError("WACC must be greater than terminal growth")
    if shares <= 0:
        raise ValueError("Shares must be positive")

    fcf = base_fcf
    pv_fcf = 0.0
    for i, growth in enumerate(growth_rates, start=1):
        fcf = fcf * (1 + growth)
        pv_fcf += fcf / ((1 + wacc) ** i)

    terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** len(growth_rates))
    enterprise_value = pv_fcf + pv_terminal
    equity_value = enterprise_value - net_debt
    return equity_value / shares


def linear_fade(start: float, end: float, years: int = 5) -> List[float]:
    if years <= 1:
        return [end]
    step = (start - end) / (years - 1)
    return [start - i * step for i in range(years)]


def llm_direct_valuation(
    model: str,
    symbol: str,
    context: Dict[str, Any],
    ollama_url: str = "http://localhost:11434",
) -> Dict[str, Any]:
    prompt = f"""
You are an equity valuation analyst.
Use ONLY the provided metrics. Return ONLY valid JSON with keys:
- fair_value_usd (number)
- confidence_0_to_1 (number)
- methods (array of objects with keys method, value_usd, weight)
- assumptions (object)
- notes (string)

Symbol: {symbol}
Context:
{json.dumps(context, indent=2)}
"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }

    response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=240)
    response.raise_for_status()
    raw = response.json().get("response", "")
    parsed = json.loads(raw)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare cached manual valuation vs pipeline valuation")
    parser.add_argument("--symbol", default="STX")
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--llm-model", default="qwen3-coder-tools:30b-64K")
    parser.add_argument(
        "--market-source",
        choices=["auto", "yahoo", "pipeline", "db"],
        default="auto",
        help="Market snapshot source for current price and market multiples",
    )
    parser.add_argument("--skip-llm", action="store_true")
    args = parser.parse_args()

    symbol = args.symbol.upper()

    points = load_quarters(symbol)
    points = derive_missing_q4(points)
    recent_8 = select_recent_quarters(points, n=8)
    if len(recent_8) < 8:
        raise ValueError(f"Need at least 8 quarters, found {len(recent_8)} for {symbol}")

    prior_4 = recent_8[:4]
    latest_4 = recent_8[4:]
    latest_4.sort(key=_period_sort_key)
    prior_4.sort(key=_period_sort_key)

    ttm_revenue = sum_metric(latest_4, "revenue")
    ttm_net_income = sum_metric(latest_4, "net_income")
    ttm_fcf = sum_metric(latest_4, "free_cash_flow")
    prior_ttm_revenue = sum_metric(prior_4, "revenue")

    if ttm_revenue is None or ttm_net_income is None or ttm_fcf is None:
        raise ValueError("TTM computation failed due to missing key metrics")

    revenue_growth = 0.0
    if prior_ttm_revenue and prior_ttm_revenue > 0:
        revenue_growth = (ttm_revenue / prior_ttm_revenue) - 1.0

    latest_q = latest_4[-1]
    shares = latest_q.shares_outstanding or 0.0
    if shares <= 0:
        raise ValueError("shares_outstanding missing/invalid for latest quarter")

    cash = latest_q.cash or 0.0
    debt = latest_q.total_debt or 0.0
    net_debt = max(0.0, debt - cash)
    eps_ttm = ttm_net_income / shares
    revenue_per_share = ttm_revenue / shares

    pipeline = load_pipeline_valuation_from_log(symbol, args.log_path)
    pipeline_methods = pipeline.get("methods", {})
    pipeline_company_profile = pipeline.get("company_profile", {}) or {}
    pipeline_ratios = pipeline.get("ratios", {}) or {}
    market_snapshot, market_snapshot_errors = get_market_snapshot(symbol, args.market_source, pipeline)
    current_price = market_snapshot.get("current_price") or pipeline.get("current_price") or 0.0

    # Manual DCF assumptions anchored on SEC trend + market risk proxy.
    rf = 0.0416
    erp = 0.055
    beta = market_snapshot.get("beta") or 1.6
    cost_of_equity = rf + beta * erp
    wacc_conservative = max(0.09, min(0.16, cost_of_equity * 0.75 + 0.055 * 0.25))
    growth_start_cons = max(0.06, min(0.18, revenue_growth * 0.55))
    growth_cons = linear_fade(growth_start_cons, 0.03, years=5)
    fair_dcf_conservative = dcf_per_share(
        base_fcf=ttm_fcf,
        growth_rates=growth_cons,
        wacc=wacc_conservative,
        terminal_growth=0.03,
        net_debt=net_debt,
        shares=shares,
    )

    growth_start_risk = max(0.08, min(0.28, revenue_growth + 0.03))
    growth_risk = linear_fade(growth_start_risk, 0.035, years=5)
    fair_dcf_risk = dcf_per_share(
        base_fcf=ttm_fcf,
        growth_rates=growth_risk,
        wacc=0.20,
        terminal_growth=0.035,
        net_debt=net_debt,
        shares=shares,
    )

    pipeline_sector_pe = _safe_num((pipeline_methods.get("pe") or {}).get("assumptions", {}).get("sector_median_pe"))
    target_pe = market_snapshot.get("forward_pe") or market_snapshot.get("trailing_pe") or pipeline_sector_pe or 20.0
    target_pe = max(10.0, min(40.0, target_pe))
    fair_pe = eps_ttm * target_pe

    pipeline_sector_ps = _safe_num((pipeline_methods.get("ps") or {}).get("assumptions", {}).get("sector_median_ps"))
    current_ps = market_snapshot.get("price_to_sales")
    target_ps = max(2.0, min(12.0, current_ps * 0.65)) if current_ps and current_ps > 0 else (pipeline_sector_ps or 5.0)
    fair_ps = revenue_per_share * target_ps

    fair_ev_ebitda = None
    market_ebitda = market_snapshot.get("ebitda")
    pipeline_sector_ev = _safe_num(
        (pipeline_methods.get("ev_ebitda") or {}).get("assumptions", {}).get("sector_median_ev_ebitda")
    )
    target_ev_ebitda = (
        max(6.0, min(20.0, (market_snapshot.get("enterprise_to_ebitda") or 0.0) * 0.65))
        if market_snapshot.get("enterprise_to_ebitda")
        else (pipeline_sector_ev or 12.0)
    )
    if market_ebitda and market_ebitda > 0:
        fair_ev_ebitda = ((market_ebitda * target_ev_ebitda) - net_debt) / shares

    pipeline_sector_pb = _safe_num((pipeline_methods.get("pb") or {}).get("assumptions", {}).get("sector_median_pb"))
    current_pb = market_snapshot.get("price_to_book")
    target_pb = max(0.8, min(8.0, current_pb * 0.65)) if current_pb and current_pb > 0 else (pipeline_sector_pb or 2.0)
    book_value_per_share = _safe_num(pipeline_ratios.get("book_value_per_share")) or _safe_num(
        pipeline_company_profile.get("book_value_per_share")
    )
    fair_pb = book_value_per_share * target_pb if book_value_per_share and book_value_per_share > 0 else None

    is_financial = is_financial_company(
        pipeline_company_profile.get("sector"),
        pipeline_company_profile.get("industry"),
    )

    if is_financial:
        # Financials are balance-sheet driven; avoid DCF/EV-EBITDA as primary anchors.
        blend_weights = {
            "pe_anchor": 0.45 if fair_pe > 0 else 0.0,
            "pb_anchor": 0.45 if fair_pb is not None else 0.0,
            "ps_anchor": 0.10 if fair_ps > 0 else 0.0,
        }
        total_weight = sum(blend_weights.values()) or 1.0
        blend_weights = {k: (v / total_weight) for k, v in blend_weights.items() if v > 0}
        manual_blended = (
            fair_pe * blend_weights.get("pe_anchor", 0.0)
            + (fair_pb or 0.0) * blend_weights.get("pb_anchor", 0.0)
            + fair_ps * blend_weights.get("ps_anchor", 0.0)
        )
    else:
        blend_weights = {
            "dcf_conservative": 0.35,
            "pe_anchor": 0.25,
            "ps_anchor": 0.20,
            "ev_ebitda_anchor": 0.20 if fair_ev_ebitda is not None else 0.0,
        }
        if fair_ev_ebitda is None:
            blend_weights["dcf_conservative"] += 0.10
            blend_weights["pe_anchor"] += 0.10

        manual_blended = (
            fair_dcf_conservative * blend_weights["dcf_conservative"]
            + fair_pe * blend_weights["pe_anchor"]
            + fair_ps * blend_weights["ps_anchor"]
            + (fair_ev_ebitda or 0.0) * blend_weights["ev_ebitda_anchor"]
        )

    llm_direct = None
    llm_error = None
    if not args.skip_llm:
        llm_context = {
            "current_price": current_price,
            "ttm_revenue": ttm_revenue,
            "ttm_net_income": ttm_net_income,
            "ttm_free_cash_flow": ttm_fcf,
            "ttm_revenue_growth": revenue_growth,
            "shares_outstanding": shares,
            "cash": cash,
            "total_debt": debt,
            "net_debt": net_debt,
            "eps_ttm": eps_ttm,
            "revenue_per_share_ttm": revenue_per_share,
            "market_snapshot": market_snapshot,
        }
        try:
            llm_direct = llm_direct_valuation(
                model=args.llm_model,
                symbol=symbol,
                context=llm_context,
            )
        except Exception as exc:
            llm_error = str(exc)

    pipeline_summary = {
        "blended_fair_value": pipeline.get("fair_value_blended"),
        "current_price": pipeline.get("current_price"),
        "dcf_professional": _safe_num((pipeline_methods.get("dcf_professional") or {}).get("fair_value_per_share")),
        "pe": _safe_num((pipeline_methods.get("pe") or {}).get("fair_value_per_share")),
        "ev_ebitda": _safe_num((pipeline_methods.get("ev_ebitda") or {}).get("fair_value_per_share")),
        "ps": _safe_num((pipeline_methods.get("ps") or {}).get("fair_value_per_share")),
        "pb": _safe_num((pipeline_methods.get("pb") or {}).get("fair_value_per_share")),
        "ggm": _safe_num((pipeline_methods.get("ggm") or {}).get("fair_value_per_share")),
        "damodaran_dcf": _safe_num((pipeline_methods.get("damodaran_dcf") or {}).get("fair_value_per_share")),
    }

    manual_summary = {
        "dcf_conservative": fair_dcf_conservative,
        "dcf_market_risk": fair_dcf_risk,
        "pe_anchor": fair_pe,
        "ps_anchor": fair_ps,
        "pb_anchor": fair_pb,
        "ev_ebitda_anchor": fair_ev_ebitda,
        "blended_fair_value": manual_blended,
        "method_profile": "financial_relative" if is_financial else "general_mixed",
        "blend_weights": blend_weights,
    }

    pipeline_blended = pipeline_summary["blended_fair_value"] or 0.0
    compare = {}
    for key, value in manual_summary.items():
        if value is None or not isinstance(value, (int, float)):
            continue
        diff = value - pipeline_blended
        diff_pct = (diff / pipeline_blended * 100.0) if pipeline_blended else None
        compare[key] = {
            "manual_value": value,
            "pipeline_blended_value": pipeline_blended,
            "difference": diff,
            "difference_pct": diff_pct,
        }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("artifacts/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{symbol.lower()}_manual_vs_pipeline_{ts}.json"
    out_md = out_dir / f"{symbol.lower()}_manual_vs_pipeline_{ts}.md"

    output = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "source_files": {
            "quarterlymetrics_dir": f"data/sec_cache/quarterlymetrics/{symbol}",
            "pipeline_log": pipeline["log_path"],
        },
        "metrics": {
            "ttm_revenue": ttm_revenue,
            "ttm_net_income": ttm_net_income,
            "ttm_free_cash_flow": ttm_fcf,
            "ttm_revenue_growth": revenue_growth,
            "shares_outstanding": shares,
            "cash": cash,
            "total_debt": debt,
            "net_debt": net_debt,
            "eps_ttm": eps_ttm,
            "revenue_per_share_ttm": revenue_per_share,
            "latest_4_quarters": [
                {
                    "fy": p.fiscal_year,
                    "fp": p.fiscal_period,
                    "period_end": p.period_end_date,
                    "derived": p.derived,
                }
                for p in latest_4
            ],
        },
        "market_snapshot": market_snapshot,
        "market_snapshot_errors": market_snapshot_errors,
        "pipeline_valuation": pipeline_summary,
        "manual_valuation": manual_summary,
        "comparison_vs_pipeline_blended": compare,
        "llm_direct_valuation": llm_direct,
        "llm_direct_error": llm_error,
    }

    out_json.write_text(json.dumps(output, indent=2))

    def fmt(x: Optional[float]) -> str:
        if x is None:
            return "N/A"
        return f"${x:,.2f}"

    llm_fv = None
    if isinstance(llm_direct, dict):
        llm_fv = _safe_num(llm_direct.get("fair_value_usd"))

    md_lines = [
        f"# {symbol} Valuation Comparison",
        "",
        f"- Generated: `{output['timestamp']}`",
        f"- Pipeline log: `{pipeline['log_path']}`",
        "",
        "## Core Inputs (SEC Cache + Market Snapshot)",
        f"- Market Snapshot Source: `{market_snapshot.get('source', 'unknown')}`",
        f"- Current Price: {fmt(current_price)}",
        f"- TTM Revenue: {fmt(ttm_revenue)}",
        f"- TTM Net Income: {fmt(ttm_net_income)}",
        f"- TTM Free Cash Flow: {fmt(ttm_fcf)}",
        f"- Revenue Growth (TTM vs prior TTM): `{revenue_growth * 100:.1f}%`",
        f"- Shares Outstanding: `{shares:,.0f}`",
        f"- Net Debt: {fmt(net_debt)}",
        "",
        "## Valuation Side-by-Side",
        "",
        "| Method | Value |",
        "|---|---:|",
        f"| Pipeline Blended Fair Value | {fmt(pipeline_summary['blended_fair_value'])} |",
        f"| Pipeline DCF Professional | {fmt(pipeline_summary['dcf_professional'])} |",
        f"| Manual DCF (Conservative) | {fmt(manual_summary['dcf_conservative'])} |",
        f"| Manual DCF (Market-Risk) | {fmt(manual_summary['dcf_market_risk'])} |",
        f"| Manual P/E Anchor | {fmt(manual_summary['pe_anchor'])} |",
        f"| Manual P/S Anchor | {fmt(manual_summary['ps_anchor'])} |",
        f"| Manual P/B Anchor | {fmt(manual_summary['pb_anchor'])} |",
        f"| Manual EV/EBITDA Anchor | {fmt(manual_summary['ev_ebitda_anchor'])} |",
        f"| Manual Blended Fair Value | {fmt(manual_summary['blended_fair_value'])} |",
        f"| Direct LLM Fair Value | {fmt(llm_fv)} |",
        "",
        "## Notes",
        "- Manual Q4 values are derived from FY - (Q1+Q2+Q3) when Q4 was absent in raw quarterly cache.",
        f"- Manual blend profile: `{manual_summary['method_profile']}`.",
        "- This report compares valuation strategies, not recommendation text quality.",
    ]
    if market_snapshot_errors:
        md_lines.append(f"- Market snapshot fallback notes: `{'; '.join(market_snapshot_errors)}`")
    if llm_error:
        md_lines.append(f"- Direct LLM valuation error: `{llm_error}`")

    out_md.write_text("\n".join(md_lines))

    print(f"Wrote JSON: {out_json}")
    print(f"Wrote Markdown: {out_md}")
    print(f"Pipeline blended fair value: {fmt(pipeline_summary['blended_fair_value'])}")
    print(f"Manual blended fair value: {fmt(manual_summary['blended_fair_value'])}")
    if llm_fv is not None:
        print(f"Direct LLM fair value: {fmt(llm_fv)}")


if __name__ == "__main__":
    main()
