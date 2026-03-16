"""Selection and sector-multiple helpers extracted from FundamentalAnalysisAgent."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from investigator.domain.services.valuation.models import CompanyProfile


def lookup_sector_multiple(
    sector: Optional[str],
    multiple: str,
    *,
    industry: Optional[str] = None,
    loader: Any = None,
    config: Any = None,
    logger: Any = None,
) -> Optional[float]:
    """Fetch sector-level reference multiples from layered sources."""
    if not sector:
        if logger is not None:
            logger.debug("[SECTOR_LOOKUP_DEBUG] sector is None, returning None")
        return None

    if logger is not None:
        logger.debug(f"[SECTOR_LOOKUP_DEBUG] Looking up {sector}/{industry or 'sector'}/{multiple}")
        logger.debug(f"[SECTOR_LOOKUP_DEBUG] _sector_multiples_loader exists: {loader is not None}")
        logger.info(f"[SECTOR_LOOKUP] Looking up {multiple} for sector={sector}, industry={industry}")

    try:
        from investigator.domain.services.valuation_shared.sector_multiples_service import (
            SectorMultiplesService,
        )

        sector_service = SectorMultiplesService()
        config_method = getattr(sector_service, f"get_{multiple}", None)
        if config_method:
            sig = inspect.signature(config_method)
            config_value = config_method(sector, industry) if "industry" in sig.parameters else config_method(sector)
            if config_value is not None:
                if logger is not None:
                    logger.info(
                        f"[SECTOR_LOOKUP] Using config-aware value from SectorMultiplesService.{multiple}"
                        f"({sector}, {industry}): {config_value}"
                    )
                return config_value

        historical_value = sector_service.get_historical_median_multiple(
            sector=sector,
            metric=multiple,
            lookback_years=3,
        )
        if historical_value is not None:
            if logger is not None:
                logger.debug(
                    f"[SECTOR_LOOKUP_DEBUG] Returning historical median from SectorMultiplesService: {historical_value}"
                )
            return historical_value
    except Exception as exc:
        if logger is not None:
            logger.debug(f"[SECTOR_LOOKUP_DEBUG] SectorMultiplesService failed: {exc}, trying fallback")

    if loader:
        try:
            record = loader.get(sector)
            if logger is not None:
                logger.debug(f"[SECTOR_LOOKUP_DEBUG] Loader record for {sector}: {record}")
            if record:
                value = getattr(record, multiple, None)
                if logger is not None:
                    logger.debug(f"[SECTOR_LOOKUP_DEBUG] Record.{multiple} = {value}")
                if value is not None:
                    if logger is not None:
                        logger.debug(f"[SECTOR_LOOKUP_DEBUG] Returning value from loader: {value}")
                    return float(value)
        except Exception as exc:
            if logger is not None:
                logger.debug(f"[SECTOR_LOOKUP_DEBUG] Loader failed: {exc}, trying fallback")

    try:
        from investigator.domain.services.valuation.common import SectorMultiples

        value = SectorMultiples.get_sector_multiple(sector, multiple)
        if value is not None:
            if logger is not None:
                logger.debug(f"[SECTOR_LOOKUP_DEBUG] Returning value from shared SectorMultiples: {value}")
            return value
    except Exception as exc:
        if logger is not None:
            logger.debug(f"[SECTOR_LOOKUP_DEBUG] Shared SectorMultiples not available: {exc}")

    try:
        valuation_settings = getattr(config, "valuation", None)
        if logger is not None:
            logger.debug(f"[SECTOR_LOOKUP_DEBUG] valuation_settings exists: {valuation_settings is not None}")
        if isinstance(valuation_settings, dict):
            multiples = valuation_settings.get("sector_multiples", {}) or {}
        elif valuation_settings is not None:
            multiples = getattr(valuation_settings, "sector_multiples", {}) or {}
        else:
            if logger is not None:
                logger.debug("[SECTOR_LOOKUP_DEBUG] No valuation_settings, returning None")
            return None

        if logger is not None:
            logger.debug(
                f"[SECTOR_LOOKUP_DEBUG] Config multiples keys: {list(multiples.keys()) if multiples else 'empty'}"
            )
        sector_key = sector.lower()
        for key, values in multiples.items():
            if key.lower() == sector_key:
                value = values.get(multiple)
                if logger is not None:
                    logger.debug(f"[SECTOR_LOOKUP_DEBUG] Found {key} matching {sector_key}, {multiple}={value}")
                if value is not None:
                    if logger is not None:
                        logger.debug(f"[SECTOR_LOOKUP_DEBUG] Returning value from config: {value}")
                    return float(value)
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Sector multiple lookup failed for {sector}/{multiple}: {exc}")
            logger.debug(f"Failed to load sector multiple for {sector}/{multiple}: {exc}")

    if logger is not None:
        logger.debug("[SECTOR_LOOKUP_DEBUG] No value found, returning None")
    return None


def calculate_enterprise_value(market_data: Dict[str, Any], financials: Dict[str, Any]) -> Optional[float]:
    """Calculate enterprise value from explicit EV fields or from market cap, debt, and cash."""
    ev_candidates = [
        market_data.get("enterprise_value"),
        market_data.get("enterpriseValue"),
        market_data.get("enterprise_value_real_time"),
    ]
    for ev in ev_candidates:
        if ev is not None:
            try:
                return float(ev)
            except (TypeError, ValueError):
                continue

    market_cap = market_data.get("market_cap") or market_data.get("marketCap")
    if market_cap is None:
        return None

    total_debt = financials.get("total_debt") or financials.get("long_term_debt") or market_data.get("total_debt")
    cash = financials.get("cash") or financials.get("cash_and_equivalents") or market_data.get("cash")

    try:
        market_cap_val = float(market_cap)
        debt_val = float(total_debt) if total_debt is not None else 0.0
        cash_val = float(cash) if cash is not None else 0.0
        return market_cap_val + debt_val - cash_val
    except (TypeError, ValueError):
        return None


def load_model_selection_rules(rules_path: Path, *, logger: Any = None) -> Dict[str, Any]:
    """Load model-selection rules from disk, returning an empty mapping when unavailable."""
    if not rules_path.exists():
        return {}
    try:
        with rules_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Failed to load model selection rules: {exc}")
        return {}


def select_models_for_company(
    profile: CompanyProfile,
    model_selection_rules: Dict[str, Any],
) -> Optional[List[str]]:
    """Select valuation models for a company profile based on configured archetype rules."""
    if not model_selection_rules:
        return None

    rules = model_selection_rules if isinstance(model_selection_rules, dict) else {}
    defaults = rules.get("defaults", {}) if isinstance(rules.get("defaults"), dict) else {}

    include = set(defaults.get("include", []))
    exclude = set(defaults.get("exclude", []))
    blocking_flags: Dict[str, List[str]] = {}

    def _merge_blocking(rule_blocking: Optional[Dict[str, Any]]) -> None:
        if not isinstance(rule_blocking, dict):
            return
        for flag, models in rule_blocking.items():
            if not isinstance(models, (list, tuple)):
                continue
            existing = blocking_flags.setdefault(flag.upper(), [])
            existing.extend(str(model) for model in models)

    _merge_blocking(defaults.get("blocking_flags"))

    archetype_rules = rules.get("archetypes", {}) if isinstance(rules.get("archetypes"), dict) else {}
    primary = profile.primary_archetype.name.lower() if profile.primary_archetype else None
    if primary and archetype_rules.get(primary):
        rule = archetype_rules[primary] or {}
        include.update(rule.get("include", []))
        exclude.update(rule.get("exclude", []))
        _merge_blocking(rule.get("blocking_flags"))

        secondary_rules = rule.get("secondary") if isinstance(rule.get("secondary"), dict) else {}
        secondary = profile.secondary_archetype.name.lower() if profile.secondary_archetype else None
        if secondary and secondary in secondary_rules:
            sec_rule = secondary_rules[secondary] or {}
            include.update(sec_rule.get("include", []))
            exclude.update(sec_rule.get("exclude", []))
            _merge_blocking(sec_rule.get("blocking_flags"))

    allowed = [model for model in include if model not in exclude]
    if blocking_flags and profile.data_quality_flags:
        active_flags = {flag.name.upper() for flag in profile.data_quality_flags}
        for flag in active_flags:
            blocked = blocking_flags.get(flag)
            if not blocked:
                continue
            allowed = [model for model in allowed if model not in blocked]

    min_models = defaults.get("min_models")
    if isinstance(min_models, int) and min_models > 0 and len(allowed) < min_models:
        return None

    return allowed if allowed else None
