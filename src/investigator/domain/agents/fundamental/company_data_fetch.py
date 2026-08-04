"""Helpers for company-data fetch orchestration and compatibility mapping."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from investigator.infrastructure.cache.cache_types import CacheType


def resolve_cik_for_symbol(*, symbol: str, ticker_mapper: Any, logger: Any) -> str | None:
    """Resolve symbol->CIK with safe error handling."""
    try:
        cik = ticker_mapper.resolve_cik(symbol)
        if cik:
            logger.debug("Resolved CIK %s for %s", cik, symbol)
        return cik
    except Exception as exc:
        logger.warning("Failed to resolve CIK for %s: %s", symbol, exc)
        return None


def build_company_cache_key(*, symbol: str, fiscal_period: str, cik: str | None) -> dict[str, Any]:
    """Build quarter-specific company cache key to avoid fiscal-period overwrites."""
    cache_key: dict[str, Any] = {"symbol": symbol, "fiscal_period": fiscal_period}
    if cik:
        cache_key["cik"] = cik
    return cache_key


def get_cached_company_data(
    *, cache: Any, cache_key: dict[str, Any], symbol: str, logger: Any
) -> dict[str, Any] | None:
    """Return cached company payload only when financials are present."""
    if not cache:
        return None
    cached = cache.get(CacheType.COMPANY_FACTS, cache_key)
    if cached and cached.get("financials"):
        logger.info("Using cached company data for %s", symbol)
        return cached
    return None


def build_financial_statements_from_processed(
    *,
    financial_metrics: dict[str, Any],
    financial_ratios: dict[str, Any],
    data_source: str,
    derive_short_term_debt: Callable[[dict[str, Any]], float | None],
) -> dict[str, Any]:
    """Build compatibility financial_statements payload from processed-table data."""
    return {
        "revenues": financial_metrics.get("revenues", 0),
        "net_income": financial_metrics.get("net_income", 0),
        "gross_profit": financial_metrics.get("gross_profit", 0),
        "operating_income": financial_metrics.get("operating_income", 0),
        "total_assets": financial_metrics.get("assets", 0),
        "stockholders_equity": financial_metrics.get("equity", 0),
        "current_assets": financial_metrics.get("assets_current", 0),
        "current_liabilities": financial_metrics.get("liabilities_current", 0),
        "total_liabilities": financial_metrics.get("liabilities", 0),
        "total_debt": financial_metrics.get("total_debt", 0),
        "long_term_debt": financial_metrics.get("long_term_debt", 0),
        "short_term_debt": (
            financial_metrics.get("short_term_debt")
            or financial_metrics.get("debt_current")
            or derive_short_term_debt(financial_metrics)
            or 0
        ),
        "operating_cash_flow": financial_metrics.get("operating_cash_flow", 0),
        "capital_expenditures": financial_metrics.get("capital_expenditures", 0),
        "free_cash_flow": financial_metrics.get("free_cash_flow", 0),
        "dividends_paid": financial_metrics.get("dividends_paid", 0),
        "preferred_stock_dividends": financial_metrics.get("preferred_stock_dividends", 0),
        "cash_and_equivalents": financial_metrics.get("cash_and_equivalents", 0),
        "cash": financial_metrics.get("cash", financial_metrics.get("cash_and_equivalents", 0)),
        "shares_outstanding": (
            financial_metrics.get("shares_outstanding")
            or financial_metrics.get("weighted_average_diluted_shares_outstanding", 0)
        ),
        "current_ratio": financial_ratios.get("current_ratio", 0),
        "quick_ratio": financial_ratios.get("quick_ratio", 0),
        "debt_to_equity": financial_ratios.get("debt_to_equity", 0),
        "roe": financial_ratios.get("roe", 0),
        "roa": financial_ratios.get("roa", 0),
        "gross_margin": financial_ratios.get("gross_margin", 0),
        "operating_margin": financial_ratios.get("operating_margin", 0),
        "net_margin": financial_ratios.get("net_margin", 0),
        "data_source": data_source,
    }


def build_company_data_payload(
    *,
    symbol: str,
    cik: str | None,
    company_facts: dict[str, Any],
    financial_statements: dict[str, Any],
    market_data: dict[str, Any],
    fiscal_period_label: str | None,
) -> dict[str, Any]:
    """Assemble final company_data payload."""
    return {
        "symbol": symbol,
        "cik": cik,
        "facts": company_facts,
        "financials": financial_statements,
        "market_data": market_data,
        "fiscal_period": fiscal_period_label,
        "fetched_at": datetime.now().isoformat(),
    }


def validate_financial_statements(*, financial_statements: dict[str, Any], symbol: str, cik: str | None) -> None:
    """Raise clear ValueError when no usable financial statements are available."""
    if financial_statements:
        return
    raise ValueError(
        f"No financial data available for {symbol} from cache, database, or SEC API. "
        f"This may indicate: (1) Invalid ticker symbol, (2) No SEC filings available, "
        f"(3) CIK resolution failure. CIK={'found' if cik else 'not found'}"
    )


def cache_company_data_payload(
    *,
    cache: Any,
    cache_key: dict[str, Any],
    company_data: dict[str, Any],
    company_facts: dict[str, Any],
    symbol: str,
    cik: str | None,
    logger: Any,
) -> None:
    """Persist company payload to cache when facts are present."""
    if not cache or not company_facts:
        return
    try:
        cache.set(CacheType.COMPANY_FACTS, cache_key, company_data)
        logger.debug("Cached company data for %s with CIK %s", symbol, cik)
    except Exception as exc:
        logger.warning("Failed to cache company data: %s", exc)
