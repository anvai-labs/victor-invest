"""
Fundamental Analysis Agent
Specialized agent for fundamental analysis and financial metrics evaluation using Ollama LLMs
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from investigator.domain.agents.base import InvestmentAgent
from investigator.domain.models.analysis import AgentResult, AgentTask, TaskStatus
from investigator.domain.services.company_metadata_service import CompanyMetadataService
from investigator.domain.services.data_normalizer import (  # TODO: Move to infrastructure
    DataNormalizer,
)
from investigator.domain.services.deterministic_competitive_analyzer import (
    analyze_competitive_position,
)

# Deterministic services (replace LLM calls with rule-based computation)
from investigator.domain.services.dynamic_model_weighting import (
    DynamicModelWeightingService,
)
from investigator.domain.services.fiscal_period_service import get_fiscal_period_service
from investigator.domain.services.safe_formatters import format_currency as _fmt_currency
from investigator.domain.services.safe_formatters import format_int_with_commas as _fmt_int_comma
from investigator.domain.services.safe_formatters import format_percentage as _fmt_pct
from investigator.domain.services.toon_formatter import TOONFormatter, to_toon_quarterly
from investigator.domain.services.valuation import (  # Sector-aware valuation routing
    SectorValuationRouter,
)

# New valuation models (Milestone 7 - Plan implementation)
from investigator.domain.services.valuation.dcf import DCFValuation
from investigator.domain.services.valuation.ggm import GordonGrowthModel

# Clean architecture imports (Phase 6-7 migration)
from investigator.domain.services.valuation.helpers import (
    normalize_model_output,
    serialize_company_profile,
)

# Clean architecture imports (migrated from utils/valuation/framework)
from investigator.domain.services.valuation.models import (
    CompanyProfile,
)
from investigator.domain.services.valuation.orchestrator import (
    MultiModelValuationOrchestrator,
)
from investigator.infrastructure.cache import CacheManager
from investigator.infrastructure.cache.cache_key_builder import build_cache_key
from investigator.infrastructure.cache.cache_types import CacheType
from investigator.infrastructure.data.sector_multiples_loader import (
    SectorMultiplesLoader,
)
from investigator.infrastructure.database.market_data import (  # Singleton pattern
    get_market_data_fetcher,
)
from investigator.infrastructure.database.ticker_mapper import (  # TODO: Move to infrastructure
    TickerCIKMapper,
)
from investigator.infrastructure.formatters import ValuationTableFormatter
from investigator.infrastructure.sec.canonical_mapper import get_canonical_mapper

from .company_data_fetch import (
    build_company_cache_key,
    build_company_data_payload,
    build_financial_statements_from_processed,
    cache_company_data_payload,
    get_cached_company_data,
    resolve_cik_for_symbol,
    validate_financial_statements,
)
from .company_fetch import fetch_latest_company_data_from_processed_table
from .company_profile_enrichment import enrich_company_profile
from .constants import (
    FALLBACK_CANONICAL_KEYS,
    PROCESSED_ADDITIONAL_FINANCIAL_KEYS,
    PROCESSED_RATIO_KEYS,
)
from .cost_of_capital import apply_cost_of_capital_penalty as apply_cost_of_capital_penalty_helper
from .cost_of_capital import evaluate_cost_of_capital_inputs as evaluate_cost_of_capital_inputs_helper
from .cost_of_capital import hydrate_cost_of_capital_inputs as hydrate_cost_of_capital_inputs_helper
from .cost_of_equity import calculate_cost_of_equity_capm
from .data_quality_assessor import get_data_quality_assessor
from .deterministic_analyzer import DeterministicAnalyzer
from .deterministic_payloads import (
    build_deterministic_cache_record,
    build_deterministic_response,
)
from .financial_ratios import (
    add_market_context_ratios,
    apply_balance_sheet_and_cashflow_ratios,
    apply_valuation_ratios,
    calculate_revenue_growth_yoy,
    calculate_ttm_metrics,
    log_ratio_calc_debug,
    resolve_market_inputs,
)
from .formatters import safe_fmt_float as _safe_fmt_float
from .formatters import safe_fmt_int_comma as _safe_fmt_int_comma
from .formatters import safe_fmt_pct as _safe_fmt_pct
from .llm_sanitization import sanitize_for_llm_inputs
from .logging_utils import (
    format_trend_context,
    log_data_quality_issues,
    log_individual_model_result,
    log_quarterly_snapshot,
    log_valuation_snapshot,
)
from .models import QuarterlyData
from .quarterly_fetch import (
    fetch_processed_quarter_payload,
    query_recent_processed_periods,
    resolve_quarter_data,
)
from .summaries import extract_latest_financials as _extract_latest_financials_helper
from .summaries import get_historical_trend as _get_historical_trend_helper
from .summaries import summarize_company_data as _summarize_company_data_helper
from .trend_analyzer import get_trend_analyzer
from .valuation_extensions import calculate_valuation_extensions
from .valuation_models import calculate_relative_valuation_models
from .valuation_orchestrator import (
    assign_and_log_relative_models,
    dispatch_valuation_synthesis,
    log_multi_model_summary,
    run_multi_model_blending,
    run_sector_and_dcf,
)
from .valuation_synthesis import (
    build_models_detail_lines,
    build_valuation_synthesis_prompt,
)
from .valuation_weighting import resolve_fallback_weights


class FundamentalAnalysisAgent(InvestmentAgent):
    """
    Agent specialized in fundamental analysis and company valuation.

    High-level flow (ascii schematic):

        ┌────────────┐        ┌────────────────────┐        ┌────────────────────┐
        │  SEC Agent │ ─────▶ │  Processed Tables  │ ─────▶ │ Fundamental Agent  │
        │ (raw facts)│        │  (sec_companyfacts)│        │  (ratios + models) │
        └────────────┘        └────────┬───────────┘        └─────────┬──────────┘
                                       │                                │
                                       │ company_data                   │ blended outputs
                                       ▼                                ▼
                                deterministic health/growth      Multi-model valuation
                                scoring + DCF/GGM/multiples      → cached for synthesis
    """

    def __init__(self, agent_id: str, ollama_client, event_bus, cache_manager: CacheManager):
        from investigator.config import get_config

        config = get_config()
        self.config = config

        self.primary_model = config.ollama.models.get("fundamental_analysis", "deepseek-r1:32b")
        self.comparison_model = config.ollama.models.get("comparison", self.primary_model)

        # Specialized models for different analysis types
        self.models = {
            "valuation": self.primary_model,
            "quality": self.primary_model,
            "comparison": self.comparison_model,
        }

        super().__init__(agent_id, ollama_client, event_bus, cache_manager)
        self.market_data = get_market_data_fetcher(config)
        self.ticker_mapper = TickerCIKMapper()

        # Initialize canonical key mapper for sector-aware XBRL tag extraction
        self.canonical_mapper = get_canonical_mapper()

        # Initialize CompanyMetadataService for centralized sector/industry lookup with override support
        self.company_metadata_service = CompanyMetadataService()

        # Cache for shares outstanding (avoid redundant DB queries per symbol)
        self._shares_cache = {}

        # Cache for sector information (avoid redundant DB queries per symbol)
        # NOTE: Kept for backward compatibility but now delegating to CompanyMetadataService
        self._sector_cache = {}

        # Sector multiples loader (lazy to allow missing reference file)
        self._sector_multiples_loader: Optional[SectorMultiplesLoader] = None

        valuation_cfg = getattr(config, "valuation", None)
        multiples_path: Optional[str] = None
        freshness_days = 7
        delta_threshold = 0.15
        if isinstance(valuation_cfg, dict):
            multiples_path = valuation_cfg.get("sector_multiples_path")
            freshness_days = valuation_cfg.get("sector_multiples_freshness_days", freshness_days)
            delta_threshold = valuation_cfg.get("sector_multiples_delta_threshold", delta_threshold)
        elif valuation_cfg is not None:
            multiples_path = getattr(valuation_cfg, "sector_multiples_path", None)
            freshness_days = getattr(valuation_cfg, "sector_multiples_freshness_days", freshness_days)
            delta_threshold = getattr(valuation_cfg, "sector_multiples_delta_threshold", delta_threshold)

        if multiples_path:
            reference_path = Path(multiples_path)
        else:
            reference_path = Path("config/sector_multiples.json")

        self._sector_multiples_loader = SectorMultiplesLoader(
            reference_path=reference_path,
            freshness_days=freshness_days,
            delta_threshold=delta_threshold,
        )

        # Load model selection rules
        self._model_selection_rules = self._load_model_selection_rules()

        # Multi-model valuation orchestrator (weights and diagnostics)
        self.multi_model_orchestrator = MultiModelValuationOrchestrator()

        # Dynamic model weighting service (tier-based weight determination)
        # Load valuation config from config.yaml (migrated from config.json)
        config_file = getattr(config, "config_file", "config.yaml")
        with open(config_file, "r") as f:
            raw_config = yaml.safe_load(f)
        valuation_config_dict = raw_config.get("valuation", {})
        self.dynamic_weighting_service = DynamicModelWeightingService(valuation_config_dict)

        # Deterministic processing config (replaces LLM calls with rule-based computation)
        deterministic_config = valuation_config_dict.get("deterministic", {})
        self.use_deterministic = deterministic_config.get("enabled", True)
        self.deterministic_valuation_synthesis = deterministic_config.get("valuation_synthesis", True)
        self.deterministic_competitive_analysis = deterministic_config.get("competitive_analysis", True)
        self.deterministic_forecast_generation = deterministic_config.get("forecast_generation", True)
        self.deterministic_fundamental_report_generation = deterministic_config.get(
            "fundamental_report_generation", True
        )

        # Key fundamental metrics to analyze
        self.key_metrics = [
            "pe_ratio",
            "peg_ratio",
            "price_to_book",
            "price_to_sales",
            "debt_to_equity",
            "current_ratio",
            "quick_ratio",
            "roe",
            "roa",
            "roic",
            "gross_margin",
            "operating_margin",
            "net_margin",
            "revenue_growth",
            "earnings_growth",
            "free_cash_flow",
            "fcf_yield",
            "dividend_yield",
        ]

        # Valuation models to apply
        self.valuation_models = [
            "dcf",
            "ddm",
            "relative_valuation",
            "asset_based",
            "earnings_power",
        ]

    def _debug_log_prompt(self, label: str, prompt: str) -> None:
        """Emit prompt text when debug logging is enabled."""
        if self.logger.isEnabledFor(logging.DEBUG):
            trimmed = prompt if len(prompt) <= 6000 else f"{prompt[:6000]}\n...[truncated]"
            self.logger.debug("📤 %s PROMPT:\n%s", label, trimmed)

    def _debug_log_response(self, label: str, response: Any) -> None:
        """Emit LLM response when debug logging is enabled."""
        if not self.logger.isEnabledFor(logging.DEBUG):
            return

        if isinstance(response, (dict, list)):
            try:
                payload = json.dumps(response, indent=2, default=str)
            except (TypeError, ValueError):
                payload = str(response)
        else:
            payload = str(response)

        if len(payload) > 6000:
            payload = f"{payload[:6000]}\n...[truncated]"

        self.logger.debug("📥 %s RESPONSE:\n%s", label, payload)

    def _get_current_fiscal_period(
        self, symbol: str, financials: Optional[Dict] = None, cik: Optional[str] = None
    ) -> str:
        """
        Determine current fiscal period using 2-tier strategy.

        TIER 1 (Preferred): Bulk-loaded SEC DERA tables (sec_sub_data)
        TIER 2 (Fallback): Financial data or calendar approximation

        This is CRITICAL for fiscal period-based caching (Phase 2 enhancement).
        Ensures different fiscal quarters don't overwrite each other in cache.

        Args:
            symbol: Stock ticker symbol
            financials: Optional financial data dict (if already loaded)
            cik: Optional CIK for querying bulk tables

        Returns:
            Fiscal period string in format 'YYYY-QN' (e.g., '2025-Q2')

        Examples:
            '2025-Q2' - Second quarter 2025 (from sec_sub_data)
            '2024-FY' - Full year 2024 (from sec_sub_data)
        """

        # DEBUG: Entry point logging
        self.logger.debug(
            "🔍 [FISCAL_PERIOD_ENTRY] %s - _get_current_fiscal_period() called with cik=%s, financials=%s",
            symbol,
            cik,
            "present" if financials else "None",
        )

        try:
            # TIER 1: Try bulk-loaded tables first (authoritative source)
            if cik:
                try:
                    from investigator.infrastructure.sec.data_strategy import (
                        get_fiscal_period_strategy,
                    )

                    strategy = get_fiscal_period_strategy()  # Uses db_manager internally
                    fy, fp, adsh = strategy.get_latest_fiscal_period(symbol, cik)

                    if fy and fp:
                        self.logger.info(
                            f"Using fiscal period from bulk tables for {symbol}: " f"{fy}-{fp} (ADSH: {adsh})"
                        )
                        return f"{fy}-{fp}"

                except Exception as e:
                    self.logger.debug(f"Bulk table lookup failed for {symbol}: {e}")

            # TIER 1.5: Query sec_companyfacts_processed for latest filing metadata
            if cik:
                self.logger.info(f"🔍 TIER 1.5: Checking processed SEC filings for {symbol}")
                try:
                    from sqlalchemy import text

                    from investigator.infrastructure.database.db import get_db_manager

                    db_manager = get_db_manager()
                    with db_manager.engine.connect() as conn:
                        latest = conn.execute(
                            text(
                                """
                                SELECT fiscal_year, fiscal_period, filed_date
                                FROM sec_companyfacts_processed
                                WHERE symbol = :symbol
                                ORDER BY filed_date DESC NULLS LAST,
                                         period_end_date DESC NULLS LAST
                                LIMIT 1
                                """
                            ),
                            {"symbol": symbol.upper()},
                        ).fetchone()

                    if latest and latest.fiscal_year and latest.fiscal_period:
                        self.logger.info(
                            "✅ Using fiscal period from processed table for %s: %s-%s (filed: %s)",
                            symbol,
                            latest.fiscal_year,
                            latest.fiscal_period,
                            latest.filed_date,
                        )
                        return f"{latest.fiscal_year}-{latest.fiscal_period}"
                except Exception as e:
                    self.logger.warning(f"Processed SEC lookup failed for {symbol}: {e}", exc_info=True)

            # TIER 2A: Check if financials have fiscal period from SEC data
            if financials:
                fiscal_year = financials.get("fiscal_year") or financials.get("fy")
                fiscal_period = financials.get("fiscal_period") or financials.get("fp")

                if fiscal_year and fiscal_period:
                    # Validate it's not a future period (indicates calendar-based)
                    now = datetime.now()
                    current_year = now.year
                    current_quarter = ((now.month - 1) // 3) + 1

                    if isinstance(fiscal_period, str) and fiscal_period.startswith("Q"):
                        quarter_num = int(fiscal_period[1])
                    elif fiscal_period == "FY":
                        quarter_num = 4
                    else:
                        quarter_num = 0

                    # Accept if historical or valid current quarter
                    is_future = (fiscal_year > current_year) or (
                        fiscal_year == current_year and quarter_num >= current_quarter
                    )

                    if not is_future:
                        return f"{fiscal_year}-{fiscal_period}"
                    else:
                        self.logger.warning(
                            f"Fiscal period {fiscal_year}-{fiscal_period} appears to be "
                            f"future/current quarter (not filed yet). Using fallback."
                        )

            # TIER 2B: Calendar-based fallback (last resort)
            now = datetime.now()
            year = now.year
            month = now.month

            # Use PREVIOUS quarter (current quarter not filed yet)
            quarter = ((month - 1) // 3) + 1
            if quarter == 1:
                # If current quarter is Q1, use previous year Q4
                year -= 1
                quarter = 4
            else:
                quarter -= 1

            self.logger.warning(
                f"Using calendar-based PREVIOUS quarter {year}-Q{quarter} for {symbol}. "
                f"This is a fallback - actual fiscal periods should come from bulk tables."
            )

            return f"{year}-Q{quarter}"

        except Exception as e:
            self.logger.warning(
                f"Failed to determine fiscal period for {symbol}: {e}. " f"Using 'unknown' as fallback."
            )
            return "unknown"

    def _require_financials(self, company_data: Dict) -> Dict:
        """Ensure financial data exists and normalize field names, raising a clear error if not."""
        financials = company_data.get("financials") or {}
        if not financials:
            # FIX #4: More helpful error message
            symbol = company_data.get("symbol", "UNKNOWN")
            cik = company_data.get("cik", "unknown")
            raise ValueError(
                f"Financial statement data is unavailable for {symbol}. "
                f"Data sources checked: cache, database, SEC API. "
                f"This may indicate: (1) Invalid ticker symbol, (2) No SEC filings available, "
                f"(3) CIK resolution failure. CIK={cik}. Check logs for details."
            )

        # CRITICAL: Normalize field names to snake_case for internal consistency
        # This ensures all internal Python code uses snake_case, matching CLAUDE.md standards
        # SEC data from extractors should be converted to snake_case at source
        normalized_financials = DataNormalizer.normalize_field_names(financials, to_camel_case=False)

        return normalized_financials

    def _build_company_profile(self, symbol: str, company_data: Dict, ratios: Dict) -> CompanyProfile:
        """
        Assemble a CompanyProfile snapshot from the data already loaded by the agent.

        The profile focuses on universally available metrics so later phases can
        refine archetype detection without re-plumbing the fundamentals workflow.
        """
        self.logger.debug(f"Building company profile for {symbol}")

        financials = self._require_financials(company_data)
        market_data = company_data.get("market_data") or {}
        data_quality = company_data.get("data_quality") or {}

        # CRITICAL: Use CompanyMetadataService first to respect config overrides.
        # This keeps sector/industry classification consistent across weighting/routing.
        sector, metadata_industry = self.company_metadata_service.get_sector_industry(symbol, use_cache=True)
        if not sector:
            sector = self._get_sector_for_symbol(symbol)
        industry = metadata_industry or market_data.get("industry") or company_data.get("industry")

        profile = CompanyProfile(symbol=symbol, sector=sector or "Unknown", industry=industry)
        enrich_company_profile(
            profile=profile,
            symbol=symbol,
            sector=sector,
            company_data=company_data,
            ratios=ratios,
            financials=financials,
            market_data=market_data,
            data_quality=data_quality,
            logger=self.logger,
        )
        return profile

    def _get_sector_for_symbol(self, symbol: str) -> str:
        """
        Get sector classification for a symbol with caching and config override support.

        This sector information is used by CanonicalKeyMapper for sector-aware
        XBRL tag fallback chains (e.g., Utilities use different revenue tags than Technology).

        Priority order (via CompanyMetadataService):
        0. Config.yaml sector overrides (highest priority - for misclassified companies)
        1. Instance cache (avoid redundant calls)
        2. Database (sec_sector, then Sector column)
        3. Peer group JSON mapping
        4. Sector map text file
        5. Fallback to 'Unknown' (uses global fallback tags only)

        Returns:
            str: Sector name (e.g., 'Technology', 'Utilities'), or 'Unknown' if not available
        """
        # Check instance cache first
        if symbol in self._sector_cache:
            self.logger.debug(f"Using cached sector for {symbol}: {self._sector_cache[symbol]}")
            return self._sector_cache[symbol]

        # Use CompanyMetadataService for centralized sector lookup with override support
        try:
            sector = self.company_metadata_service.get_sector(symbol, use_cache=True)
            self._sector_cache[symbol] = sector
            self.logger.debug(f"CompanyMetadataService returned sector for {symbol}: {sector}")
            return sector
        except Exception as e:
            self.logger.warning(
                f"Error fetching sector via CompanyMetadataService for {symbol}: {e}, using 'Unknown' fallback"
            )
            self._sector_cache[symbol] = "Unknown"
            return "Unknown"

    def _get_shares_outstanding(self, symbol: str, cik: str) -> float:
        """
        Extract shares outstanding from SEC NUM data with caching.

        Priority order:
        1. Instance cache (avoid redundant DB queries)
        2. CommonStockSharesOutstanding (most recent filing)
        3. WeightedAverageNumberOfSharesOutstandingBasic (if above missing)
        4. EntityCommonStockSharesOutstanding (fallback)

        Returns:
            float: Shares outstanding, or 0 if not available
        """
        # Check instance cache first
        cache_key = f"{symbol}:{cik}"
        if cache_key in self._shares_cache:
            self.logger.debug(f"Using cached shares outstanding for {symbol}: {self._shares_cache[cache_key]:,.0f}")
            return self._shares_cache[cache_key]

        try:
            from sqlalchemy import text

            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_session() as session:
                # Query for shares outstanding with priority ordering
                # Priority: EntityCommonStockSharesOutstanding (DEI - always actual shares) > CommonStock > WeightedAverage
                query = text(
                    """
                    SELECT n.value, n.ddate, n.tag
                    FROM sec_num_data n
                    JOIN sec_sub_data s ON n.adsh = s.adsh
                    WHERE s.cik = :cik
                      AND n.tag IN (
                          'EntityCommonStockSharesOutstanding',
                          'CommonStockSharesOutstanding',
                          'WeightedAverageNumberOfSharesOutstandingBasic'
                      )
                      AND n.ddate IS NOT NULL
                    ORDER BY n.ddate DESC,
                             CASE n.tag
                                 WHEN 'EntityCommonStockSharesOutstanding' THEN 1
                                 WHEN 'CommonStockSharesOutstanding' THEN 2
                                 WHEN 'WeightedAverageNumberOfSharesOutstandingBasic' THEN 3
                                 ELSE 4
                             END
                    LIMIT 1
                """
                )

                result = session.execute(query, {"cik": cik}).fetchone()

                if result and result[0]:
                    shares = float(result[0])
                    tag_used = result[2]

                    # Scale normalization: Some companies report shares in millions (value < 100,000)
                    # For large-cap companies (market cap > $1B), this is likely in millions
                    # DEI namespace (EntityCommonStockSharesOutstanding) is always in actual shares
                    if tag_used != "EntityCommonStockSharesOutstanding" and shares < 100_000:
                        # Cross-check with market data to detect millions reporting
                        stock_info = self.market_data.get_stock_info(symbol)
                        market_cap = stock_info.get("market_cap", 0)
                        price = stock_info.get("current_price") or stock_info.get("price", 0)

                        if market_cap and market_cap > 1_000_000_000:  # $1B+ market cap
                            # Shares value < 100k but market cap > $1B indicates millions reporting
                            self.logger.warning(
                                f"⚠️  {symbol}: Detected shares in millions ({shares:,.0f}) - "
                                f"normalizing to actual count (×1M). Market cap: ${market_cap / 1e9:.1f}B"
                            )
                            shares = shares * 1_000_000
                        elif price and price > 0:
                            # Alternative: estimate expected shares from market_cap/price
                            implied_shares = market_cap / price if market_cap else 0
                            if implied_shares > 1_000_000 and shares < 10_000:
                                self.logger.warning(
                                    f"⚠️  {symbol}: Shares ({shares:,.0f}) seems low vs implied ({implied_shares:,.0f}) - "
                                    f"normalizing to actual count (×1M)"
                                )
                                shares = shares * 1_000_000

                    self._shares_cache[cache_key] = shares
                    self.logger.info(
                        f"Found shares outstanding for {symbol}: {shares:,.0f} shares (tag: {tag_used}, date: {result[1]})"
                    )
                    return shares

            # Fall back to market data service
            stock_info = self.market_data.get_stock_info(symbol)
            fallback_shares = stock_info.get("shares_outstanding")
            if fallback_shares:
                shares = float(fallback_shares)
                self._shares_cache[cache_key] = shares
                self.logger.info(
                    "Using market data fallback for %s shares outstanding: %s",
                    symbol,
                    f"{shares:,.0f}",
                )
                return shares

            self.logger.warning(f"No shares outstanding found for {symbol} (CIK: {cik})")
            self._shares_cache[cache_key] = 0
            return 0

        except Exception as e:
            self.logger.error(f"Error fetching shares outstanding for {symbol}: {e}")
            return 0

    def _get_public_float(self, symbol: str, cik: str) -> float:
        """
        Extract public float (EntityPublicFloat) from SEC DEI namespace.

        Public float is the portion of shares available for trading, excluding
        shares held by insiders and controlling shareholders. This is always
        reported in USD in the DEI namespace.

        Args:
            symbol: Stock ticker
            cik: Company CIK (numeric string)

        Returns:
            float: Public float in USD, or 0 if not available
        """
        # Check instance cache first
        cache_key = f"{symbol}:{cik}:float"
        if hasattr(self, "_float_cache") and cache_key in self._float_cache:
            return self._float_cache[cache_key]

        if not hasattr(self, "_float_cache"):
            self._float_cache = {}

        try:
            from sqlalchemy import text

            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_session() as session:
                # EntityPublicFloat is in DEI namespace, reported in USD
                query = text(
                    """
                    SELECT n.value, n.ddate, n.uom
                    FROM sec_num_data n
                    JOIN sec_sub_data s ON n.adsh = s.adsh
                    WHERE s.cik = :cik
                      AND n.tag = 'EntityPublicFloat'
                      AND n.ddate IS NOT NULL
                    ORDER BY n.ddate DESC
                    LIMIT 1
                    """
                )

                result = session.execute(query, {"cik": cik}).fetchone()

                if result and result[0]:
                    public_float = float(result[0])
                    uom = result[2]
                    self._float_cache[cache_key] = public_float
                    self.logger.info(
                        f"Found public float for {symbol}: ${public_float:,.0f} (unit: {uom}, date: {result[1]})"
                    )
                    return public_float

            self.logger.debug(f"No public float found for {symbol} (CIK: {cik})")
            self._float_cache[cache_key] = 0
            return 0

        except Exception as e:
            self.logger.error(f"Error fetching public float for {symbol}: {e}")
            return 0

    def register_capabilities(self) -> List:
        """Register agent capabilities"""
        from investigator.domain.agents.base import AgentCapability, AnalysisType

        return [
            AgentCapability(
                analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
                min_data_required={"symbol": str},
                max_processing_time=360,  # Increased 2x for slower hardware
                required_models=[self.primary_model],
                cache_ttl=3600,
            )
        ]

    async def process(self, task: AgentTask) -> AgentResult:
        """Process fundamental analysis task"""
        symbol = task.context.get("symbol")
        analysis_depth = task.context.get("depth", "comprehensive")
        include_forecast = task.context.get("include_forecast", True)
        valuation_basis = str(task.context.get("valuation_basis", "ttm")).strip().lower()
        forward_horizon = str(task.context.get("forward_horizon", "1y")).strip().lower()

        # DEBUG: Explicit logging to trace execution
        self.logger.debug("FundamentalAgent.process() START for %s", symbol)
        self.logger.info(f"Performing {analysis_depth} fundamental analysis for {symbol}")

        try:
            # Fetch company facts and financials
            self.logger.debug("Calling _fetch_company_data for %s", symbol)
            company_data = await self._fetch_company_data(symbol)
            self.logger.debug(
                "_fetch_company_data returned %s keys: %s",
                len(company_data),
                list(company_data.keys())[:10],
            )

            # NEW: Multi-quarter historical analysis
            try:
                # CRITICAL: Request 12 quarters (3 years) to ensure we get ≥8 after Q4 computation
                # AVGO showed only 7 quarters when requesting 8 (boundary case - Q4 not yet filed)
                quarterly_data = await self._fetch_historical_quarters(symbol, num_quarters=12)

                # CRITICAL FIX: Add quarterly_data to company_data for valuation methods
                # DCF and GGM need this data for FCF, dividends, and growth rate calculations
                company_data["quarterly_data"] = quarterly_data
                self.logger.info(
                    f"Added {len(quarterly_data)} quarters to company_data for {symbol} (for DCF/GGM valuation)"
                )

                if len(quarterly_data) >= 4:
                    # Analyze trends across quarters
                    revenue_trend = self._analyze_revenue_trend(quarterly_data)
                    margin_trend = self._analyze_margin_trend(quarterly_data)
                    cash_flow_trend = self._analyze_cash_flow_trend(quarterly_data)
                    comparisons = self._calculate_quarterly_comparisons(quarterly_data)
                    cyclical = self._detect_cyclical_patterns(quarterly_data)

                    # Add trend analysis to company_data
                    company_data["trend_analysis"] = {
                        "revenue": revenue_trend,
                        "margins": margin_trend,
                        "cash_flow": cash_flow_trend,
                        "comparisons": comparisons,
                        "cyclical": cyclical,
                        "num_quarters": len(quarterly_data),
                    }

                    self.logger.info(
                        f"Multi-quarter analysis for {symbol}: "
                        f"Revenue={revenue_trend['trend']}, "
                        f"Margins={margin_trend['net_margin_trend']}, "
                        f"Cash Quality={cash_flow_trend['quality_of_earnings']}/100, "
                        f"Cyclical={cyclical['seasonal_pattern']}"
                    )
                else:
                    self.logger.warning(f"Insufficient quarterly data for {symbol}: {len(quarterly_data)} quarters")
                    company_data["trend_analysis"] = None

            except Exception as e:
                self.logger.warning(f"Multi-quarter analysis failed for {symbol}: {e}", exc_info=True)
                company_data["trend_analysis"] = None
                company_data["quarterly_data"] = []  # Ensure empty list if extraction fails

            # Calculate financial ratios
            ratios = await self._calculate_financial_ratios(company_data)

            # CRITICAL FIX: Update company_data with calculated market_cap and shares
            # This ensures LLM prompts receive correct values (not market_cap=0, price=0)
            if "market_cap" in ratios:
                company_data["market_cap"] = ratios["market_cap"]
                self.logger.info(f"Updated company_data market_cap for {symbol}: ${ratios['market_cap']:,.0f}")
            if "shares_outstanding" in ratios:
                company_data["shares_outstanding"] = ratios["shares_outstanding"]
                self.logger.info(f"Updated company_data shares for {symbol}: {ratios['shares_outstanding']:,.0f}")
            if "current_price" in ratios:
                if "market_data" not in company_data:
                    company_data["market_data"] = {}
                company_data["market_data"]["current_price"] = ratios["current_price"]

            # FEATURE #1: Assess data quality (migrated from old solution)
            data_quality = self._assess_data_quality(company_data, ratios)
            company_data["data_quality"] = data_quality
            self.logger.info(
                f"Data quality for {symbol}: {data_quality['quality_grade']} "
                f"({data_quality['data_quality_score']:.1f}% - "
                f"{data_quality['core_metrics_populated']} core metrics)"
            )

            # FEATURE #3: Log quality improvement metrics
            if data_quality.get("quality_improvement", 0) > 0:
                self.logger.info(f"Data enrichment for {symbol}: {data_quality['enhancement_summary']}")

            # FEATURE #2: Calculate confidence level based on data quality
            confidence = self._calculate_confidence_level(data_quality)
            company_data["confidence"] = confidence
            self.logger.info(
                f"Analysis confidence for {symbol}: {confidence['confidence_level']} "
                f"({confidence['confidence_score']}/100) - {confidence['rationale']}"
            )

            # CRITICAL FIX #4: Sanitize data before LLM calls
            company_data, ratios = self._sanitize_for_llm(company_data, ratios, symbol)

            # Analyze financial health (with data quality in prompt)
            health_analysis = await self._analyze_financial_health(company_data, ratios, symbol)

            # Analyze growth metrics
            growth_analysis = await self._analyze_growth(company_data, symbol)

            # Analyze profitability
            profitability = await self._analyze_profitability(company_data, ratios, symbol)

            sec_analysis = task.context.get("sec_analysis", {})
            forward_guidance = sec_analysis.get("forward_guidance", {}) if isinstance(sec_analysis, dict) else {}
            if isinstance(forward_guidance, dict) and forward_guidance:
                company_data["forward_guidance"] = forward_guidance
                self.logger.info(
                    "%s - Forward guidance available from SEC agent (%s, confidence=%s)",
                    symbol,
                    forward_guidance.get("source_form", "unknown"),
                    forward_guidance.get("confidence_score", "n/a"),
                )

            # Perform valuation analysis
            valuation = await self._perform_valuation(
                company_data,
                ratios,
                symbol,
                valuation_basis=valuation_basis,
                forward_horizon=forward_horizon,
                guidance_context=forward_guidance if isinstance(forward_guidance, dict) else None,
            )

            # Analyze competitive position
            competitive = await self._analyze_competitive_position(company_data, symbol)

            # Generate earnings forecast if requested
            forecast = None
            if include_forecast:
                forecast = await self._generate_forecast(company_data, growth_analysis, symbol)

            # Calculate quality score
            quality_score = await self._calculate_quality_score(
                health_analysis, growth_analysis, profitability, competitive
            )

            # Synthesize comprehensive report
            report = await self._synthesize_fundamental_report(
                {
                    "symbol": symbol,
                    "company_data": self._summarize_company_data(company_data),
                    "ratios": ratios,
                    "health_analysis": health_analysis,
                    "growth_analysis": growth_analysis,
                    "profitability": profitability,
                    "valuation": valuation,
                    "competitive_analysis": competitive,
                    "forecast": forecast,
                    "quality_score": quality_score,
                    "data_quality": data_quality,  # FEATURE #1: Include data quality in synthesis
                    "confidence": confidence,  # FEATURE #2: Include confidence in synthesis
                    "fiscal_period": company_data.get("fiscal_period"),  # Period for caching
                }
            )

            # Extract multi-model summary from valuation results
            # NOTE: _perform_valuation() returns wrapped response: {"response": {...}, "prompt": ..., "model_info": ..., "metadata": ...}
            # The actual data is in valuation["response"]["valuation_methods"]["multi_model"]
            multi_model_summary = {}
            llm_fair_value_estimate = 0

            # CRITICAL FIX: valuation is wrapped by _wrap_llm_response, so data is in valuation["response"]
            valuation_unwrapped = {}
            if isinstance(valuation, dict):
                response_data = valuation.get("response", {})
                if isinstance(response_data, dict):
                    valuation_unwrapped = response_data
                    # Get valuation_methods from the response data
                    valuation_methods = response_data.get("valuation_methods", {})
                    if isinstance(valuation_methods, dict):
                        multi_model_summary = valuation_methods.get("multi_model", {})

                    # Also get LLM fair value estimate from response data
                    llm_fair_value_estimate = response_data.get("fair_value_estimate", 0)

            blended_fair_value = multi_model_summary.get("blended_fair_value")

            # Use blended fair value as primary (fallback to LLM estimate if unavailable)
            primary_fair_value = blended_fair_value if blended_fair_value else llm_fair_value_estimate
            report_response = (
                report.get("response", {})
                if isinstance(report, dict) and isinstance(report.get("response"), dict)
                else {}
            )
            recommendation_value = report_response.get(
                "investment_recommendation",
                report_response.get("recommendation", "hold"),
            )
            investment_grade_value = report_response.get("investment_grade", "B")

            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.COMPLETED,
                result_data={
                    "status": "success",
                    "symbol": symbol,
                    "analysis": report_response,
                    "valuation": valuation_unwrapped,  # CRITICAL FIX: Store unwrapped valuation data
                    "ratios": ratios,  # FIX #2: Include calculated ratios in output
                    "quality_score": quality_score,
                    "data_quality": data_quality,  # FEATURE #1: Include in results
                    "confidence": confidence,  # FEATURE #2: Include in results
                    "investment_grade": investment_grade_value,
                    # PRIMARY FIX: Use blended fair value from multi-model orchestrator
                    "fair_value": primary_fair_value,
                    "llm_fair_value_estimate": llm_fair_value_estimate,  # Keep for reference
                    "multi_model_summary": multi_model_summary,  # Full multi-model data for synthesis
                    "recommendation": recommendation_value,
                    "fiscal_period": company_data.get("fiscal_period"),  # Include fiscal period in output
                },
                processing_time=0,  # Will be calculated by base class
            )

        except Exception as e:
            self.logger.error(f"Fundamental analysis failed for {symbol}: {e}", exc_info=True)
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                result_data={"status": "error", "symbol": symbol, "error": str(e)},
                processing_time=0,
                error=str(e),
            )

    async def recalculate_derived_metrics(self, task: AgentTask, cached_result: Dict) -> Dict:
        """
        HYBRID CACHING FIX (Phase 1):
        Recalculate deterministic metrics (CompanyProfile, ratios) from cached LLM responses.

        This method is called by base.py when cache hits occur. It ensures that:
        1. Expensive LLM responses stay cached (30-60s synthesis)
        2. Deterministic metrics are always fresh (~100ms calculation)
        3. CompanyProfile.revenue_growth_yoy is populated for P/S model

        Args:
            task: Original AgentTask with symbol
            cached_result: Cached LLM response data

        Returns:
            Enriched cached_result with fresh CompanyProfile and derived metrics
        """
        symbol = task.symbol
        self.logger.debug(f"{symbol} - Recalculating derived metrics from cached LLM response")

        try:
            # Step 1: Re-fetch company_data (cheap database queries ~100ms)
            company_data = await self._fetch_company_data(symbol)

            if not company_data or "error" in company_data:
                self.logger.warning(f"{symbol} - Failed to re-fetch company_data for metric recalculation")
                return cached_result  # Return original cached result if fetch fails

            # Step 2: Re-calculate financial ratios (deterministic, ~50ms)
            ratios = await self._calculate_financial_ratios(company_data)

            # Step 3: Re-build CompanyProfile (ensures revenue_growth_yoy is populated)
            profile = self._build_company_profile(symbol, company_data, ratios)

            # Step 4: Update cached_result with fresh CompanyProfile and ratios
            # Preserve LLM synthesis results but update deterministic metrics
            enriched_result = cached_result.copy()

            # Replace CompanyProfile in valuation section
            if "valuation" in enriched_result and isinstance(enriched_result["valuation"], dict):
                if "company_profile" in enriched_result["valuation"]:
                    # Convert CompanyProfile dataclass to dict for JSON serialization
                    from dataclasses import asdict

                    enriched_result["valuation"]["company_profile"] = asdict(profile)
                    self.logger.debug(f"{symbol} - Updated CompanyProfile in cached valuation data")

            # Update ratios (used by valuation models)
            if "ratios" in enriched_result:
                enriched_result["ratios"].update(ratios)
                self.logger.debug(f"{symbol} - Updated {len(ratios)} ratios in cached data")

            # Update company_data reference (for consistency)
            if "company_data" in enriched_result:
                enriched_result["company_data"] = company_data

            revenue_growth_str = (
                f"{profile.revenue_growth_yoy:.1%}" if profile.revenue_growth_yoy is not None else "None"
            )
            self.logger.info(
                f"{symbol} - Successfully recalculated derived metrics (revenue_growth_yoy: {revenue_growth_str})"
            )

            return enriched_result

        except Exception as e:
            self.logger.warning(f"{symbol} - Failed to recalculate derived metrics: {e}", exc_info=True)
            return cached_result  # Fallback to original cached data on error

    async def _fetch_company_data(self, symbol: str) -> Dict:
        """Fetch comprehensive company financial data.

        Data flow reference:

            ┌────────────┐     canonical mapping + normalization     ┌────────────────────────┐
            │  SEC AGENT │ ────────────────────────────────────────▶ │ sec_companyfacts_proc. │
            └─────┬──────┘                                         └────────────┬───────────┘
                  │   raw filings / company facts                                │ SELECT + safe_float()
                  v                                                              v
            ┌──────────────┐      enrichment + cache      ┌────────────────────────────────────────┐
            │ company_data │ ◀──────────────────────────── │ FundamentalAgent._fetch_company_data() │
            └──────────────┘                               └────────────────┬───────────────────────┘
                                                                            │
                                                                            ├─► company_data['financials']
                                                                            │      (used by ratio + quality logic)
                                                                            └─► quarterly_data → DCF / multiples
        """
        try:
            cik = resolve_cik_for_symbol(symbol=symbol, ticker_mapper=self.ticker_mapper, logger=self.logger)
            fiscal_period = self._get_current_fiscal_period(symbol, financials=None, cik=cik)
            cache_key = build_company_cache_key(symbol=symbol, fiscal_period=fiscal_period, cik=cik)
            self.logger.debug(
                f"Cache key for {symbol}: {cache_key} " f"(fiscal_period ensures quarter-specific caching)"
            )

            cached = get_cached_company_data(cache=self.cache, cache_key=cache_key, symbol=symbol, logger=self.logger)
            if cached:
                return cached

            try:
                self.logger.info(f"[CLEAN ARCH] Fetching company data for {symbol} from processed table")
                processed_data = self._fetch_company_data_from_processed_table(symbol)
                if not processed_data:
                    raise ValueError(
                        f"No processed data found for {symbol}. "
                        f"Ensure SEC Agent has run successfully to populate sec_companyfacts_processed table."
                    )
                financial_metrics = processed_data["financial_metrics"]
                financial_ratios = processed_data["financial_ratios"]
                data_source = "clean_architecture"
                self.logger.info(
                    f"[CLEAN ARCH] ✅ Successfully fetched {symbol} data from processed table "
                    f"(quality: {processed_data.get('data_quality_score', 0):.2f})"
                )
                fiscal_year = financial_metrics.get("fiscal_year")
                fiscal_period_name = financial_metrics.get("fiscal_period")
                fiscal_period_label = (
                    f"{fiscal_year}-{fiscal_period_name}" if fiscal_year and fiscal_period_name else None
                )
                company_facts = financial_metrics
                financial_statements = build_financial_statements_from_processed(
                    financial_metrics=financial_metrics,
                    financial_ratios=financial_ratios,
                    data_source=data_source,
                    derive_short_term_debt=self._derive_short_term_debt,
                )
            except ValueError as cache_error:
                raise ValueError(
                    f"SEC Agent cache miss for {symbol}: {cache_error}. "
                    f"Ensure SEC Agent runs before Fundamental Agent."
                )
            except Exception as api_error:
                self.logger.error(
                    "Failed to hydrate company data for %s from SEC cache pipeline: %s",
                    symbol,
                    api_error,
                    exc_info=True,
                )
                # Explicitly surface migration guidance instead of silently falling back
                raise RuntimeError(
                    f"{symbol} - Clean-architecture cache miss. Please ensure the SEC agent has "
                    "persisted data via sec_companyfacts_processed before running the fundamental agent."
                ) from api_error

            market_data = await self.market_data.get_quote(symbol)
            company_data = build_company_data_payload(
                symbol=symbol,
                cik=cik,
                company_facts=company_facts,
                financial_statements=financial_statements,
                market_data=market_data,
                fiscal_period_label=fiscal_period_label,
            )
            validate_financial_statements(financial_statements=financial_statements, symbol=symbol, cik=cik)
            cache_company_data_payload(
                cache=self.cache,
                cache_key=cache_key,
                company_data=company_data,
                company_facts=company_facts,
                symbol=symbol,
                cik=cik,
                logger=self.logger,
            )

            return company_data

        except ValueError:
            # Re-raise ValueError for missing data (already has good error message)
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch company data for {symbol}: {e}", exc_info=True)
            raise ValueError(f"Failed to fetch company data for {symbol}: {str(e)}")

    @staticmethod
    def _derive_short_term_debt(metrics: Dict[str, Any]) -> Optional[float]:
        """Infer short-term debt when only total vs long-term components are available."""
        try:
            total = metrics.get("total_debt")
            long_term = metrics.get("long_term_debt")
            if total is None or long_term is None:
                return None
            delta = float(total) - float(long_term)
            return delta if delta > 0 else None
        except (TypeError, ValueError):
            return None

    async def _fetch_historical_quarters(self, symbol: str, num_quarters: int = 12) -> List[QuarterlyData]:
        """
        Fetch historical quarterly data using HYBRID 12-quarter strategy

        Phase 9 Implementation: ALWAYS returns 12 quarters for geometric mean calculation
        - 10-12 quarters from bulk tables (sec_sub_data) - fast, ADSH-linked
        - 0-2 quarters from API - fresh, fills gaps

        This ensures consistent multi-quarter trend analysis (QoQ, YoY, 3-year geometric mean)

        Args:
            symbol: Stock ticker symbol
            num_quarters: Number of quarters to fetch (default: 12 = 3 years)

        Returns:
            List[QuarterlyData] with exactly 12 quarters, sorted chronologically (oldest → newest)
            Each quarter includes: fy, fp, adsh, revenues, assets, etc.

        Raises:
            ValueError: If insufficient quarterly data available
        """
        cik = self.ticker_mapper.resolve_cik(symbol)
        if not cik:
            raise ValueError(f"No CIK found for {symbol}")

        # TD2: always include fiscal_period for QUARTERLY_METRICS cache keys to prevent collisions.
        # Use latest known fiscal period when available; otherwise keep a deterministic fallback token.
        fiscal_period_for_cache = f"latest-{num_quarters}"
        try:
            resolved_period = self._get_current_fiscal_period(symbol=symbol, cik=cik)
            if resolved_period:
                fiscal_period_for_cache = f"{resolved_period}-latest-{num_quarters}"
        except Exception as exc:
            self.logger.debug(
                "Could not resolve fiscal period for %s quarterly cache key: %s. " "Using fallback token %s.",
                symbol,
                exc,
                fiscal_period_for_cache,
            )

        cache_key = build_cache_key(
            CacheType.QUARTERLY_METRICS,
            symbol=symbol,
            fiscal_period=fiscal_period_for_cache,
            num_quarters=num_quarters,
        )
        cached_data = self.cache.get(CacheType.QUARTERLY_METRICS, cache_key) if self.cache else None

        if cached_data:
            if isinstance(cached_data, list) and all(isinstance(q, QuarterlyData) for q in cached_data):
                self.logger.info(f"🔍 CACHE HIT: Fetched historical quarters for {symbol} from cache.")
                return cached_data
            else:
                self.logger.warning(
                    f"⚠️  Cached historical quarters for {symbol} found but is malformed "
                    f"(type: {type(cached_data)}). Invalidate and re-fetching."
                )
                # Invalidate cache entry to prevent recurring issues
                self.cache.delete(CacheType.QUARTERLY_METRICS, cache_key)
                # Proceed to fetch from DB

        self.logger.info(f"Fetching {num_quarters} quarters from processed table for {symbol}")

        try:
            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
            fiscal_period_service = get_fiscal_period_service()
            quarters_data = query_recent_processed_periods(
                symbol=symbol,
                num_quarters=num_quarters,
                db_manager=db_manager,
                fiscal_period_service=fiscal_period_service,
                logger=self.logger,
            )
            if not quarters_data:
                return []

            quarterly_data_list: List[QuarterlyData] = []
            from investigator.infrastructure.sec.data_strategy import (
                get_fiscal_period_strategy,
            )

            bulk_strategy = None

            for q in reversed(quarters_data):
                qdata, bulk_strategy = resolve_quarter_data(
                    symbol=symbol,
                    quarter=q,
                    cache=self.cache,
                    cache_type=CacheType.QUARTERLY_METRICS,
                    build_cache_key=build_cache_key,
                    quarterly_data_cls=QuarterlyData,
                    fetch_from_processed_table=self._fetch_from_processed_table,
                    get_sector_for_symbol=self._get_sector_for_symbol,
                    get_fiscal_period_strategy=get_fiscal_period_strategy,
                    bulk_strategy=bulk_strategy,
                    canonical_mapper=self.canonical_mapper,
                    fallback_canonical_keys=FALLBACK_CANONICAL_KEYS,
                    calculate_quarterly_ratios=self._calculate_quarterly_ratios,
                    assess_quarter_quality=self._assess_quarter_quality,
                    logger=self.logger,
                )
                quarterly_data_list.append(qdata)

            log_quarterly_snapshot(self.logger, symbol, quarterly_data_list)
            self.logger.info(
                "Successfully fetched %s quarters for %s using hybrid strategy: %s → %s",
                len(quarterly_data_list),
                symbol,
                quarterly_data_list[0].period_label,
                quarterly_data_list[-1].period_label,
            )
            return quarterly_data_list

        except ValueError:
            # Re-raise ValueError for no data
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch historical quarters for {symbol}: {e}")
            raise ValueError(f"Failed to fetch historical quarters for {symbol}: {str(e)}")

    def _fetch_company_data_from_processed_table(self, symbol: str) -> Optional[Dict]:
        """
        Fetch latest company-level data from sec_companyfacts_processed table (CLEAN ARCHITECTURE).

        This replaces the old extractor (utils/sec_companyfacts_extractor.py) with a direct
        database query for company-level financial data.

        Migration: Phase 1.2b (Company-Level Data Path)
        - Reads from sec_companyfacts_processed table (populated by SECDataProcessor)
        - Returns same structure as old extractor for downstream compatibility
        - Prefers FY data, falls back to most recent quarter

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with financial_metrics and financial_ratios matching old extractor output,
            or None if no data found
        """
        try:
            from investigator.infrastructure.database.db import get_db_manager

            db_manager = get_db_manager()
            return fetch_latest_company_data_from_processed_table(
                symbol=symbol,
                db_manager=db_manager,
                logger=self.logger,
                processed_additional_financial_keys=PROCESSED_ADDITIONAL_FINANCIAL_KEYS,
                processed_ratio_keys=PROCESSED_RATIO_KEYS,
            )

        except Exception as e:
            self.logger.error(f"[CLEAN ARCH] Failed to fetch company data from processed table for {symbol}: {e}")
            return None

    def _fetch_from_processed_table(
        self, symbol: str, fiscal_year: int, fiscal_period: str, adsh: str
    ) -> Optional[Dict]:
        """
        Fetch pre-processed quarterly data from sec_companyfacts_processed table (3-table architecture)

        This provides fast access to already-extracted financial data and pre-calculated ratios,
        avoiding the need to parse raw us-gaap structure or query bulk tables.

        Args:
            symbol: Stock ticker
            fiscal_year: Fiscal year
            fiscal_period: Fiscal period (Q1, Q2, Q3, Q4, FY)
            adsh: Accession number (unique filing identifier)

        Returns:
            Dictionary with financial_data, ratios, and quality, or None if not found
        """
        try:
            from investigator.infrastructure.database.db import get_db_manager

            engine = get_db_manager().engine
            fiscal_period_service = get_fiscal_period_service()
            return fetch_processed_quarter_payload(
                symbol=symbol,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                adsh=adsh,
                engine=engine,
                fiscal_period_service=fiscal_period_service,
                logger=self.logger,
            )

        except Exception as e:
            self.logger.warning(f"Error fetching from processed table for {symbol}: {e}")
            return None

    def _calculate_quarterly_ratios(self, financial_data: Dict) -> Dict:
        """
        Calculate financial ratios for a single quarter.

        Handles both float and Decimal types (bulk tables return Decimal).

        Args:
            financial_data: Financial metrics for the quarter

        Returns:
            Dictionary of calculated ratios
        """
        from decimal import Decimal

        # Helper to convert Decimal to float
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val if val else 0

        ratios = {}

        revenue = to_float(financial_data.get("revenues", 0))
        net_income = to_float(financial_data.get("net_income", 0))
        assets = to_float(financial_data.get("total_assets", 0))
        equity = to_float(financial_data.get("stockholders_equity", 0))
        ocf = to_float(financial_data.get("operating_cash_flow", 0))
        capex = to_float(financial_data.get("capital_expenditures", 0))
        total_debt = to_float(financial_data.get("total_debt", 0))

        # Profitability ratios
        if revenue > 0:
            ratios["profit_margin"] = (float(net_income) / float(revenue)) * 100
            ratios["revenue_per_asset"] = float(revenue) / float(assets) if assets > 0 else 0

        # Efficiency ratios
        if assets > 0:
            ratios["roa"] = (float(net_income) / float(assets)) * 100

        if equity > 0:
            ratios["roe"] = (float(net_income) / float(equity)) * 100

        # Solvency ratios (FIXED: Use total_debt instead of total_liabilities)
        if assets > 0:
            ratios["debt_to_assets"] = (float(total_debt) / float(assets)) * 100

        if equity > 0:
            ratios["debt_to_equity"] = (float(total_debt) / float(equity)) * 100

        # Cash flow ratios
        if net_income > 0:
            ratios["cash_conversion"] = (float(ocf) / float(net_income)) * 100

        ratios["free_cash_flow"] = float(ocf) - float(capex)

        return ratios

    def _assess_quarter_quality(self, financial_data: Dict) -> Dict:
        """Delegate single-quarter quality checks to DataQualityAssessor."""
        return self._get_data_quality_assessor().assess_quarter_quality(financial_data)

    def _get_data_quality_assessor(self):
        """Lazily resolve data quality assessor to keep agent methods thin and testable."""
        assessor = getattr(self, "_data_quality_assessor", None)
        if assessor is None:
            assessor = get_data_quality_assessor(getattr(self, "logger", None))
            self._data_quality_assessor = assessor
        return assessor

    def _get_trend_analyzer(self):
        """Lazily resolve trend analyzer to keep agent methods thin and testable."""
        analyzer = getattr(self, "_trend_analyzer", None)
        if analyzer is None:
            analyzer = get_trend_analyzer(getattr(self, "logger", None))
            self._trend_analyzer = analyzer
        return analyzer

    def _get_deterministic_analyzer(self) -> DeterministicAnalyzer:
        """Lazily resolve per-agent deterministic analyzer for rule-based sub-analyses."""
        analyzer = getattr(self, "_deterministic_analyzer", None)
        if analyzer is None:
            analyzer = DeterministicAnalyzer(
                agent_id=getattr(self, "agent_id", "fundamental_analysis"),
                logger=getattr(self, "logger", None),
            )
            self._deterministic_analyzer = analyzer
        return analyzer

    def _analyze_revenue_trend(self, quarterly_data: List[QuarterlyData]) -> Dict:
        """Delegate revenue trend analysis to dedicated TrendAnalyzer service."""
        return self._get_trend_analyzer().analyze_revenue_trend(quarterly_data)

    def _analyze_margin_trend(self, quarterly_data: List[QuarterlyData]) -> Dict:
        """Delegate margin trend analysis to dedicated TrendAnalyzer service."""
        return self._get_trend_analyzer().analyze_margin_trend(quarterly_data)

    def _analyze_cash_flow_trend(self, quarterly_data: List[QuarterlyData]) -> Dict:
        """Delegate cash flow trend analysis to dedicated TrendAnalyzer service."""
        return self._get_trend_analyzer().analyze_cash_flow_trend(quarterly_data)

    def _calculate_quarterly_comparisons(self, quarterly_data: List[QuarterlyData]) -> Dict:
        """Delegate quarterly comparisons to dedicated TrendAnalyzer service."""
        return self._get_trend_analyzer().calculate_quarterly_comparisons(quarterly_data)

    def _detect_cyclical_patterns(self, quarterly_data: List[QuarterlyData]) -> Dict:
        """Delegate cyclical pattern detection to dedicated TrendAnalyzer service."""
        return self._get_trend_analyzer().detect_cyclical_patterns(quarterly_data)

    async def _calculate_financial_ratios(self, company_data: Dict) -> Dict:
        """Calculate comprehensive financial ratios"""
        financials = self._require_financials(company_data)
        market_data = company_data["market_data"]

        symbol = company_data.get("symbol", "UNKNOWN")
        cik = company_data.get("cik", "")
        ratios: Dict[str, Any] = {}
        price = 0.0
        shares = 0.0
        market_cap = 0.0

        log_ratio_calc_debug(logger=self.logger, symbol=symbol, company_data=company_data)
        quarterly_data = company_data.get("quarterly_data", [])
        ttm_metrics = calculate_ttm_metrics(
            quarterly_data=quarterly_data,
            symbol=symbol,
            logger=self.logger,
        )
        if ttm_metrics:
            existing_ttm_metrics = company_data.get("ttm_metrics", {})
            if not isinstance(existing_ttm_metrics, dict):
                existing_ttm_metrics = {}
            company_data["ttm_metrics"] = {**existing_ttm_metrics, **ttm_metrics}

        if market_data and financials:
            market_inputs = resolve_market_inputs(
                symbol=symbol,
                cik=cik,
                financials=financials,
                market_data=market_data,
                get_shares_outstanding=self._get_shares_outstanding,
                get_public_float=self._get_public_float,
                logger=self.logger,
                ratios=ratios,
            )
            price = market_inputs["price"]
            shares = market_inputs["shares"]
            market_cap = market_inputs["market_cap"]

            apply_valuation_ratios(
                symbol=symbol,
                financials=financials,
                quarterly_data=quarterly_data,
                ttm_metrics=ttm_metrics,
                ratios=ratios,
                market_cap=market_cap,
                shares=shares,
                calculate_ttm_net_income=self._calculate_ttm_net_income,
                calculate_growth_rate=self._calculate_growth_rate,
                logger=self.logger,
            )

        apply_balance_sheet_and_cashflow_ratios(
            financials=financials,
            ratios=ratios,
            market_cap=market_cap,
            price=price,
        )
        add_market_context_ratios(
            ratios=ratios,
            market_data=market_data,
            financials=financials,
            market_cap=market_cap,
            shares=shares,
            price=price,
        )

        self.logger.info(
            "REVENUE_GROWTH_DEBUG - quarterly_data exists: %s, length: %s",
            quarterly_data is not None,
            len(quarterly_data) if quarterly_data else 0,
        )
        try:
            yoy_growth = calculate_revenue_growth_yoy(quarterly_data=quarterly_data, logger=self.logger)
            if yoy_growth is not None:
                ratios["revenue_growth_yoy"] = yoy_growth
                ratios["revenue_growth"] = yoy_growth
        except Exception as e:
            self.logger.warning(f"Failed to calculate revenue_growth_yoy from quarterly data: {e}")

        return ratios

    def _assess_data_quality(self, company_data: Dict, ratios: Dict) -> Dict:
        """Delegate comprehensive data quality scoring to DataQualityAssessor."""
        return self._get_data_quality_assessor().assess_data_quality(company_data, ratios)

    def _calculate_confidence_level(self, data_quality: Dict) -> Dict:
        """Delegate confidence mapping to DataQualityAssessor."""
        return self._get_data_quality_assessor().calculate_confidence_level(data_quality)

    def _sanitize_for_llm(self, company_data: Dict, ratios: Dict, symbol: str) -> tuple:
        """
        Sanitize data before sending to LLM prompts.

        CRITICAL FIX #4: Validates and fixes data quality issues that could lead to
        incorrect analysis (market_cap=0, price=0, ratio inconsistencies).

        Args:
            company_data: Company data dict
            ratios: Financial ratios dict
            symbol: Stock symbol for logging

        Returns:
            Tuple of (sanitized_company_data, sanitized_ratios)
        """
        return sanitize_for_llm_inputs(
            company_data=company_data,
            ratios=ratios,
            symbol=symbol,
            logger=self.logger,
            log_data_quality_issues=log_data_quality_issues,
        )

    def _log_data_quality_issues(self, symbol: str, company_data: Dict, ratios: Dict):
        """Compatibility shim that delegates to shared logging helpers."""
        log_data_quality_issues(self.logger, symbol, company_data, ratios)

    def _format_trend_context(self, company_data: Dict) -> str:
        return format_trend_context(company_data)

    def _log_quarterly_snapshot(self, symbol: str, quarterly_data: List["QuarterlyData"]) -> None:
        """
        Backwards-compatible hook for legacy callers; prefer log_quarterly_snapshot helper.
        """
        log_quarterly_snapshot(self.logger, symbol, quarterly_data)

    def _log_valuation_snapshot(self, symbol: str, valuation_results: Dict[str, Any]) -> None:
        """Compatibility shim for legacy callers."""
        log_valuation_snapshot(self.logger, symbol, valuation_results)

    def _build_deterministic_response(self, label: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a structure consistent with _wrap_llm_response for rule-based analyses."""
        return build_deterministic_response(self.agent_id, label, payload)

    def _store_deterministic_analysis(
        self,
        *,
        symbol: str,
        label: str,
        payload: Dict[str, Any],
        period: Optional[str],
    ) -> None:
        """Persist deterministic analyses in the LLM cache for downstream reuse."""
        if not self.cache or not isinstance(payload, dict):
            return

        cache_key, wrapped = build_deterministic_cache_record(
            symbol=symbol,
            agent_id=self.agent_id,
            label=label,
            payload=payload,
            period=period,
        )

        try:
            self.cache.set(CacheType.LLM_RESPONSE, cache_key, wrapped)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.debug("Failed to store deterministic %s for %s: %s", label, symbol, exc)

    async def _analyze_financial_health(self, company_data: Dict, ratios: Dict, symbol: str) -> Dict:
        """Delegate deterministic financial-health analysis to specialized analyzer."""
        return await self._get_deterministic_analyzer().analyze_financial_health(company_data, ratios, symbol)

    async def _analyze_growth(self, company_data: Dict, symbol: str) -> Dict:
        """Delegate deterministic growth analysis to specialized analyzer."""
        return await self._get_deterministic_analyzer().analyze_growth(company_data, symbol)

    async def _analyze_profitability(self, company_data: Dict, ratios: Dict, symbol: str) -> Dict:
        """Delegate deterministic profitability analysis to specialized analyzer."""
        return await self._get_deterministic_analyzer().analyze_profitability(company_data, ratios, symbol)

    def _hydrate_cost_of_capital_inputs(
        self,
        profile: CompanyProfile,
        company_data: Dict[str, Any],
        ratios: Dict[str, Any],
        symbol: str,
    ) -> None:
        """Populate missing beta/debt inputs with readily available data."""
        hydrate_cost_of_capital_inputs_helper(
            profile=profile,
            company_data=company_data,
            ratios=ratios,
            symbol=symbol,
            get_stock_info=self.market_data.get_stock_info,
            require_financials=self._require_financials,
        )

    def _evaluate_cost_of_capital_inputs(
        self,
        profile: CompanyProfile,
        company_data: Dict[str, Any],
    ) -> List[str]:
        """Identify missing inputs that force the DCF to fall back to defaults."""
        return evaluate_cost_of_capital_inputs_helper(
            profile=profile,
            company_data=company_data,
            require_financials=self._require_financials,
        )

    def _apply_cost_of_capital_penalty(
        self,
        valuation_dict: Dict[str, Any],
        issues: List[str],
    ) -> Dict[str, Any]:
        """Reduce confidence when DCF had to assume default WACC inputs."""
        return apply_cost_of_capital_penalty_helper(
            valuation_dict=valuation_dict,
            issues=issues,
        )

    def _calculate_cost_of_equity(self, symbol: str) -> float:
        """
        Calculate Cost of Equity using CAPM for Gordon Growth Model

        Formula: Re = Rf + β × (Rm - Rf)

        Args:
            symbol: Stock ticker symbol

        Returns:
            Cost of equity as decimal (e.g., 0.10 for 10%)
        """
        from investigator.infrastructure.database.market_data import (
            get_market_data_fetcher,
        )
        from investigator.infrastructure.external.fred import MacroIndicatorsFetcher

        fetcher = get_market_data_fetcher(self.config)
        macro_fetcher = MacroIndicatorsFetcher()
        return calculate_cost_of_equity_capm(
            symbol=symbol,
            get_stock_info=fetcher.get_stock_info,
            get_latest_indicators=macro_fetcher.get_latest_indicators,
            logger=self.logger,
        )

    async def _calculate_dcf_professional(
        self,
        symbol: str,
        quarterly_data: List[Dict],
        company_profile: CompanyProfile,
    ) -> Dict:
        """
        Calculate DCF valuation using professional DCFValuation module with WACC

        Uses:
        - Free Cash Flow (Operating Cash Flow - CapEx)
        - WACC with levered beta from symbol table
        - 10Y Treasury rate from FRED
        - 3-5 year projections with terminal value

        Args:
            symbol: Stock ticker symbol
            quarterly_data: List of quarterly financial data (8 quarters from hybrid strategy)

        Returns:
            DCF valuation result dict with fair_value_per_share, upside_downside_pct, assumptions
        """
        try:
            from investigator.infrastructure.database.db import get_db_manager

            # Hybrid strategy already provides 8 quarters (2 years) of data
            # DCF module will aggregate and project forward
            # Convert QuarterlyData objects to dicts if needed
            quarterly_metrics = [q.to_dict() if isinstance(q, QuarterlyData) else q for q in quarterly_data]
            multi_year_data = []  # DCF will aggregate from quarterly_metrics

            db_manager = get_db_manager()

            model = DCFValuation(
                symbol=symbol,
                quarterly_metrics=quarterly_metrics,
                multi_year_data=multi_year_data,
                db_manager=db_manager,
            )
            result = model.calculate_dcf_valuation()

            if result.get("applicable", True) and (result.get("fair_value_per_share") or 0) > 0:
                pass
            else:
                self.logger.warning(
                    f"{symbol} - DCF valuation not applicable: {result.get('reason', 'unknown reason')}"
                )
            return result
        except Exception as e:
            self.logger.error(f"{symbol} - DCF calculation error: {e}", exc_info=True)
            return {"fair_value_per_share": 0, "applicable": False, "error": str(e)}

    async def _calculate_ggm(
        self,
        symbol: str,
        cost_of_equity: float,
        quarterly_data: List[Dict],
        company_profile: CompanyProfile,
    ) -> Dict:
        """
        Calculate Gordon Growth Model valuation for dividend-paying stocks

        Formula: Fair Value = D₁ / (r - g)
        Where:
        - D₁ = Next year's expected dividend per share
        - r = Cost of equity (from CAPM)
        - g = Sustainable growth rate = ROE × (1 - Payout Ratio)

        Args:
            symbol: Stock ticker symbol
            cost_of_equity: Required return on equity (from CAPM)
            quarterly_data: List of quarterly financial data (8 quarters from hybrid strategy)

        Returns:
            GGM valuation result dict with fair_value_per_share, upside_downside_pct, assumptions
        """
        try:
            from investigator.infrastructure.database.db import get_db_manager

            # Hybrid strategy already provides 8 quarters (2 years) for growth calculation
            # Convert QuarterlyData objects to dicts if needed
            quarterly_metrics = [q.to_dict() if isinstance(q, QuarterlyData) else q for q in quarterly_data]
            multi_year_data = []  # GGM will aggregate from quarterly_metrics

            db_manager = get_db_manager()

            model = GordonGrowthModel(
                symbol=symbol,
                quarterly_metrics=quarterly_metrics,
                multi_year_data=multi_year_data,
                db_manager=db_manager,
            )
            result = model.calculate_ggm_valuation(cost_of_equity=cost_of_equity)
            # GGM returns a dict directly (not ValuationModelResult), so no normalization needed

            if not result.get("applicable"):
                self.logger.info(f"{symbol} - GGM not applicable: {result.get('reason', 'Unknown')}")
            return result
        except Exception as e:
            self.logger.error(f"{symbol} - GGM calculation error: {e}", exc_info=True)
            return {
                "applicable": False,
                "reason": f"Error: {str(e)}",
                "fair_value_per_share": 0,
            }

    async def _perform_valuation(
        self,
        company_data: Dict,
        ratios: Dict,
        symbol: str,
        *,
        valuation_basis: str = "ttm",
        forward_horizon: str = "1y",
        guidance_context: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        Perform comprehensive valuation analysis with DCF and GGM (Gordon Growth Model)

        Valuation Methods:
        1. Professional DCF (all stocks) - uses WACC with levered beta and 10Y Treasury
        2. Gordon Growth Model (dividend stocks only) - uses CAPM cost of equity
        3. Relative Valuation (P/E, P/B, P/S multiples)
        4. Asset-based Valuation (book value)
        5. Earnings Power Value (EPV)
        """
        market_data = company_data["market_data"]
        financials = self._require_financials(company_data)
        data_quality = company_data.get("data_quality", {})
        trend_context = format_trend_context(company_data)
        self.logger.info(
            "%s - Relative valuation basis=%s, forward_horizon=%s",
            symbol,
            valuation_basis,
            forward_horizon,
        )
        if isinstance(guidance_context, dict) and guidance_context:
            self.logger.info(
                "%s - Guidance context detected for forward valuation (%s, confidence=%s)",
                symbol,
                guidance_context.get("source_form", "unknown"),
                guidance_context.get("confidence_score", "n/a"),
            )

        valuation_results = {}

        company_profile = self._build_company_profile(symbol, company_data, ratios)
        company_profile_payload = serialize_company_profile(company_profile)

        # Get quarterly data from hybrid strategy (8 quarters = 2 years)
        quarterly_data = company_data.get("quarterly_data", [])

        # Hydrate cost-of-capital inputs before kicking off valuation
        self._hydrate_cost_of_capital_inputs(company_profile, company_data, ratios, symbol)
        cost_of_capital_issues = self._evaluate_cost_of_capital_inputs(company_profile, company_data)

        from investigator.config import get_config

        sector_and_dcf = await run_sector_and_dcf(
            symbol=symbol,
            company_profile=company_profile,
            company_data=company_data,
            market_data=market_data,
            financials=financials,
            quarterly_data=quarterly_data,
            valuation_results=valuation_results,
            cost_of_capital_issues=cost_of_capital_issues,
            router_cls=SectorValuationRouter,
            get_config=get_config,
            calculate_dcf_professional=self._calculate_dcf_professional,
            apply_cost_of_capital_penalty=self._apply_cost_of_capital_penalty,
            store_deterministic_analysis=self._store_deterministic_analysis,
            log_model_result=log_individual_model_result,
            logger=self.logger,
        )
        dcf_professional = sector_and_dcf["dcf_professional"]
        relative_models = assign_and_log_relative_models(
            symbol=symbol,
            valuation_results=valuation_results,
            company_profile=company_profile,
            company_data=company_data,
            ratios=ratios,
            financials=financials,
            market_data=market_data,
            config=self.config,
            calculate_relative_models=calculate_relative_valuation_models,
            lookup_sector_multiple=self._lookup_sector_multiple,
            calculate_enterprise_value=self._calculate_enterprise_value,
            log_model_result=log_individual_model_result,
            logger=self.logger,
            valuation_basis=valuation_basis,
            forward_horizon=forward_horizon,
            guidance_context=guidance_context,
        )
        normalized_pe = relative_models["pe"]
        normalized_ev_ebitda = relative_models["ev_ebitda"]
        normalized_ps = relative_models["ps"]
        normalized_pb = relative_models["pb"]

        payout_ratio = await calculate_valuation_extensions(
            symbol=symbol,
            valuation_results=valuation_results,
            financials=financials,
            ratios=ratios,
            market_data=market_data,
            company_profile=company_profile,
            quarterly_data=quarterly_data,
            calculate_cost_of_equity=self._calculate_cost_of_equity,
            calculate_ggm=self._calculate_ggm,
            normalize_model_output=normalize_model_output,
            log_model_result=log_individual_model_result,
            logger=self.logger,
        )

        # === MULTI-MODEL BLENDING + SUMMARY LOGGING ===
        multi_model_summary, tier_classification = run_multi_model_blending(
            symbol=symbol,
            valuation_results=valuation_results,
            company_profile=company_profile,
            company_data=company_data,
            ratios=ratios,
            financials=financials,
            dcf_professional=dcf_professional,
            normalized_pe=normalized_pe,
            normalized_ev_ebitda=normalized_ev_ebitda,
            normalized_ps=normalized_ps,
            normalized_pb=normalized_pb,
            select_models_for_company=self._select_models_for_company,
            resolve_fallback_weights=self._resolve_fallback_weights,
            multi_model_orchestrator=self.multi_model_orchestrator,
            logger=self.logger,
        )
        summary_metrics = log_multi_model_summary(
            symbol=symbol,
            valuation_results=valuation_results,
            company_data=company_data,
            tier_classification=tier_classification,
            dcf_professional=dcf_professional,
            normalized_pe=normalized_pe,
            normalized_ev_ebitda=normalized_ev_ebitda,
            normalized_ps=normalized_ps,
            normalized_pb=normalized_pb,
            log_valuation_snapshot=log_valuation_snapshot,
            format_valuation_summary_table=ValuationTableFormatter.format_valuation_summary_table,
            logger=self.logger,
        )
        blended_fair_value = summary_metrics["blended_fair_value"]
        overall_confidence = summary_metrics["overall_confidence"]
        model_agreement_score = summary_metrics["model_agreement_score"]
        divergence_flag = summary_metrics["divergence_flag"]
        applicable_models = summary_metrics["applicable_models"]
        notes = summary_metrics["notes"]

        models_detail_lines = build_models_detail_lines(
            multi_model_summary.get("models", []),
            format_currency=_fmt_currency,
            format_percentage=_fmt_pct,
        )
        archetype_labels = ", ".join(company_profile.archetype_labels()) or "Unclassified"
        prompt = build_valuation_synthesis_prompt(
            data_quality=data_quality,
            trend_context=trend_context,
            sector=company_profile.sector,
            industry=company_profile.industry,
            archetype_labels=archetype_labels,
            data_quality_flags=company_profile_payload.get("data_quality_flags", []),
            current_price=market_data.get("price"),
            market_cap=market_data.get("market_cap", 0),
            payout_ratio=payout_ratio,
            blended_fair_value=blended_fair_value,
            overall_confidence=overall_confidence,
            model_agreement_score=model_agreement_score,
            divergence_flag=divergence_flag,
            applicable_models=applicable_models,
            notes=notes,
            models_detail_lines=models_detail_lines,
            format_currency=_fmt_currency,
            format_int_with_commas=_fmt_int_comma,
            format_percentage=_safe_fmt_pct,
        )

        return await dispatch_valuation_synthesis(
            symbol=symbol,
            prompt=prompt,
            company_data=company_data,
            market_data=market_data,
            valuation_results=valuation_results,
            multi_model_summary=multi_model_summary,
            data_quality=data_quality,
            company_profile_payload=company_profile_payload,
            notes=notes,
            use_deterministic=self.use_deterministic,
            deterministic_valuation_synthesis=self.deterministic_valuation_synthesis,
            build_deterministic_response=self._build_deterministic_response,
            debug_log_prompt=self._debug_log_prompt,
            debug_log_response=self._debug_log_response,
            ollama_client=self.ollama,
            valuation_model=self.models["valuation"],
            cache_llm_response=self._cache_llm_response,
            wrap_llm_response=self._wrap_llm_response,
            logger=self.logger,
        )

    async def _analyze_competitive_position(self, company_data: Dict, symbol: str) -> Dict:
        """Analyze company's competitive position"""
        # Check if deterministic competitive analysis is enabled (saves tokens, faster)
        if self.use_deterministic and self.deterministic_competitive_analysis:
            self.logger.debug(f"{symbol} - Using deterministic competitive analysis (LLM bypass)")

            response_data = analyze_competitive_position(symbol=symbol, company_data=company_data)

            return self._build_deterministic_response("competitive_position", response_data)

        # === LLM Path (fallback when deterministic is disabled) ===
        financials = self._require_financials(company_data)
        data_quality = company_data.get("data_quality", {})
        trend_context = format_trend_context(company_data)

        prompt = f"""
        Analyze the competitive position of {company_data["symbol"]}:

        DATA QUALITY ASSESSMENT:
        - Overall Quality: {data_quality.get("quality_grade", "Unknown")} ({_safe_fmt_pct(data_quality.get("data_quality_score", 0))})
        - {data_quality.get("assessment", "Data quality information not available")}
        - Core Metrics: {data_quality.get("core_metrics_populated", "N/A")} populated
        - Consistency Issues: {", ".join(data_quality.get("consistency_issues", [])) or "None detected"}
        {trend_context}

        Company Metrics:
        Market Cap: ${_safe_fmt_int_comma(company_data.get("market_data", {}).get("market_cap"))}
        Revenue: ${_safe_fmt_int_comma(financials.get("revenues"))}

        Evaluate:
        1. Market position and share
        2. Competitive advantages (moat analysis)
        3. Industry dynamics and trends
        4. Barriers to entry
        5. Supplier and customer power
        6. Threat of substitutes
        7. Competitive risks
        8. Strategic positioning score (0-100)

        Use Porter's Five Forces and moat analysis frameworks.

        IMPORTANT: Consider the data quality assessment when determining confidence levels.
        If data quality is below 75%, flag this in your analysis and adjust confidence accordingly.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return a JSON object that strictly follows the schema below (values are illustrative):
        {{
          "market_position_and_share": {{
            "assessment": "Leader",
            "commentary": "The company is the market leader with a 40% market share."
          }},
          "competitive_advantages_moat": {{
            "assessment": "Wide",
            "commentary": "The company has a wide economic moat due to its strong brand, network effects, and high switching costs."
          }},
          "industry_dynamics_and_trends": {{
            "assessment": "Favorable",
            "commentary": "The industry is growing at a healthy rate, and the company is well-positioned to benefit from this growth."
          }},
          "barriers_to_entry": {{
            "assessment": "High",
            "commentary": "The industry has high barriers to entry, which limits the threat of new entrants."
          }},
          "supplier_and_customer_power": {{
            "assessment": "Low",
            "commentary": "The company has a diversified supplier base and a large, fragmented customer base, which limits the power of suppliers and customers."
          }},
          "threat_of_substitutes": {{
            "assessment": "Low",
            "commentary": "There are few substitutes for the company's products."
          }},
          "competitive_risks": [
            "Intensifying competition from existing players",
            "Technological disruption"
          ],
          "strategic_positioning_score": 85
        }}
        """

        # Save prompt to cache for auditing

        prompt_name = "_analyze_competitive_position_prompt"
        self._debug_log_prompt(prompt_name, prompt)

        response = await self.ollama.generate(
            model=self.models["quality"],
            prompt=prompt,
            system="Analyze competitive position and strategic advantages.",
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
            prompt_name=prompt_name,
        )

        self._debug_log_response(prompt_name, response)

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["quality"],
            symbol=symbol,
            llm_type="fundamental_competitive_position",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["quality"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
        )

    def _lookup_sector_multiple(self, sector: Optional[str], multiple: str) -> Optional[float]:
        """Fetch sector-level reference multiples from configuration if available."""
        if not sector:
            self.logger.debug("[SECTOR_LOOKUP_DEBUG] sector is None, returning None")
            return None

        try:
            self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Looking up {sector}/{multiple}")
            self.logger.debug(
                f"[SECTOR_LOOKUP_DEBUG] _sector_multiples_loader exists: {self._sector_multiples_loader is not None}"
            )

            if self._sector_multiples_loader:
                record = self._sector_multiples_loader.get(sector)
                self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Loader record for {sector}: {record}")
                if record:
                    value = getattr(record, multiple, None)
                    self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Record.{multiple} = {value}")
                    if value is not None:
                        self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Returning value from loader: {value}")
                        return float(value)

            valuation_settings = getattr(self.config, "valuation", None)
            self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] valuation_settings exists: {valuation_settings is not None}")
            if isinstance(valuation_settings, dict):
                multiples = valuation_settings.get("sector_multiples", {}) or {}
            elif valuation_settings is not None:
                multiples = getattr(valuation_settings, "sector_multiples", {}) or {}
            else:
                self.logger.debug("[SECTOR_LOOKUP_DEBUG] No valuation_settings, returning None")
                return None

            self.logger.debug(
                f"[SECTOR_LOOKUP_DEBUG] Config multiples keys: {list(multiples.keys()) if multiples else 'empty'}"
            )
            sector_key = sector.lower()
            for key, values in multiples.items():
                if key.lower() == sector_key:
                    value = values.get(multiple)
                    self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Found {key} matching {sector_key}, {multiple}={value}")
                    if value is not None:
                        self.logger.debug(f"[SECTOR_LOOKUP_DEBUG] Returning value from config: {value}")
                        return float(value)
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.warning(f"Sector multiple lookup failed for {sector}/{multiple}: {exc}")
            self.logger.debug(f"Failed to load sector multiple for {sector}/{multiple}: {exc}")

        self.logger.debug("[SECTOR_LOOKUP_DEBUG] No value found, returning None")
        return None

    @staticmethod
    def _calculate_enterprise_value(market_data: Dict, financials: Dict) -> Optional[float]:
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

    def _resolve_fallback_weights(
        self,
        company_profile: CompanyProfile,
        models_for_blending: List[Dict[str, Any]],
        financials: Optional[Dict[str, Any]] = None,
        ratios: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, float]], str]:
        """Delegate dynamic/static fallback weighting logic to shared helper."""
        return resolve_fallback_weights(
            company_profile=company_profile,
            models_for_blending=models_for_blending,
            financials=financials,
            ratios=ratios,
            dynamic_weighting_service=self.dynamic_weighting_service,
            config=self.config,
            logger=self.logger,
        )

    def _load_model_selection_rules(self) -> Dict[str, Any]:
        rules_path = Path("config/model_selection.yaml")
        if not rules_path.exists():
            return {}
        try:
            with rules_path.open("r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception as exc:
            self.logger.warning(f"Failed to load model selection rules: {exc}")
            return {}

    def _select_models_for_company(self, profile: CompanyProfile) -> Optional[List[str]]:
        if not self._model_selection_rules:
            return None

        rules = self._model_selection_rules if isinstance(self._model_selection_rules, dict) else {}
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

    async def _generate_forecast(self, company_data: Dict, growth_analysis: Dict, symbol: str) -> Dict:
        """Generate earnings and revenue forecast"""
        financials = self._require_financials(company_data)
        data_quality = company_data.get("data_quality", {})
        trend_context = format_trend_context(company_data)

        if self.use_deterministic and self.deterministic_forecast_generation:
            self.logger.debug(
                "%s - Using deterministic forecast generation (LLM bypass)",
                symbol,
            )
            deterministic_payload = self._build_deterministic_forecast_payload(
                financials=financials,
                growth_analysis=growth_analysis,
            )
            return self._wrap_llm_response(
                response=deterministic_payload,
                model=self.models["valuation"],
                prompt="deterministic_forecast_generation",
                temperature=0.3,
                top_p=0.9,
                format="json",
                period=company_data.get("fiscal_period"),
            )

        prompt = f"""
        Generate financial forecasts based on historical data and growth analysis:

        DATA QUALITY ASSESSMENT:
        - Overall Quality: {data_quality.get("quality_grade", "Unknown")} ({_safe_fmt_pct(data_quality.get("data_quality_score", 0))})
        - {data_quality.get("assessment", "Data quality information not available")}
        - Core Metrics: {data_quality.get("core_metrics_populated", "N/A")} populated
        - Consistency Issues: {", ".join(data_quality.get("consistency_issues", [])) or "None detected"}
        {trend_context}

        Historical Financials:
        {json.dumps(self._get_historical_trend(financials), indent=2)}

        Growth Analysis:
        {json.dumps(growth_analysis, indent=2)}

        Provide forecasts for next 3 years:
        1. Revenue forecast (with growth rates)
        2. Earnings forecast
        3. Free cash flow forecast
        4. Margin projections
        5. Key assumptions
        6. Scenario analysis (base/bull/bear)
        7. Confidence intervals

        Be realistic and consider industry trends.

        IMPORTANT: Consider the data quality assessment when determining confidence levels.
        If data quality is below 75%, flag this in your analysis and adjust confidence accordingly.
        Lower confidence should result in wider confidence intervals.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return a JSON object that strictly follows the schema below (values are illustrative):
        {{
          "revenue_forecast": [
            {{ "year": 2026, "revenue": 110, "growth_rate": 0.10 }},
            {{ "year": 2027, "revenue": 121, "growth_rate": 0.10 }},
            {{ "year": 2028, "revenue": 133, "growth_rate": 0.10 }}
          ],
          "earnings_forecast": [
            {{ "year": 2026, "eps": 5.50 }},
            {{ "year": 2027, "eps": 6.05 }},
            {{ "year": 2028, "eps": 6.65 }}
          ],
          "free_cash_flow_forecast": [
            {{ "year": 2026, "fcf": 15 }},
            {{ "year": 2027, "fcf": 18 }},
            {{ "year": 2028, "fcf": 21 }}
          ],
          "margin_projections": {{
            "gross_margin": 0.45,
            "operating_margin": 0.25,
            "net_margin": 0.15
          }},
          "key_assumptions": [
            "Market growth of 5% per year",
            "Stable competitive landscape",
            "No major economic downturns"
          ],
          "scenario_analysis": {{
            "base_case": {{ "revenue_growth": 0.10, "eps": 6.65 }},
            "bull_case": {{ "revenue_growth": 0.15, "eps": 7.50 }},
            "bear_case": {{ "revenue_growth": 0.05, "eps": 5.80 }}
          }},
          "confidence_intervals": {{
            "revenue_2028": [125, 140],
            "eps_2028": [6.50, 7.00]
          }}
        }}
        """

        # Save prompt to cache for auditing

        prompt_name = "_generate_forecast_prompt"
        self._debug_log_prompt(prompt_name, prompt)

        response = await self.ollama.generate(
            model=self.models["valuation"],
            prompt=prompt,
            system="Generate realistic financial forecasts with clear assumptions.",
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
            prompt_name=prompt_name,
        )

        self._debug_log_response(prompt_name, response)

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["valuation"],
            symbol=symbol,
            llm_type="fundamental_forecast",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
        )

        return self._wrap_llm_response(
            response=response,
            model=self.models["valuation"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=company_data.get("fiscal_period"),  # Period-based caching
        )

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _build_deterministic_forecast_payload(
        self, financials: Dict[str, Any], growth_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build deterministic 3-year forecast payload when LLM is bypassed/unavailable."""
        current_year = datetime.now().year
        revenue = max(self._coerce_float(financials.get("revenue"), 0.0), 0.0)
        net_income = max(self._coerce_float(financials.get("net_income"), 0.0), 0.0)
        free_cash_flow = max(
            self._coerce_float(
                financials.get("free_cash_flow", financials.get("operating_cash_flow", 0.0)),
                0.0,
            ),
            0.0,
        )
        shares = self._coerce_float(financials.get("shares_outstanding"), 0.0)
        eps = net_income / shares if shares > 0 else self._coerce_float(financials.get("eps"), 0.0)

        raw_growth = growth_analysis.get("revenue_growth_rate", growth_analysis.get("revenue_growth", 0.05))
        growth = self._coerce_float(raw_growth, 0.05)
        if abs(growth) > 1:
            growth = growth / 100.0
        growth = min(max(growth, -0.20), 0.30)

        rev_forecast: List[Dict[str, Any]] = []
        eps_forecast: List[Dict[str, Any]] = []
        fcf_forecast: List[Dict[str, Any]] = []

        revenue_run = revenue
        eps_run = eps
        fcf_run = free_cash_flow

        for year_offset in range(1, 4):
            fade = max(0.5, 1.0 - (year_offset - 1) * 0.15)
            annual_growth = growth * fade

            revenue_run *= 1 + annual_growth
            eps_run *= 1 + annual_growth
            fcf_run *= 1 + annual_growth

            forecast_year = current_year + year_offset
            rev_forecast.append(
                {
                    "year": forecast_year,
                    "revenue": round(revenue_run, 2),
                    "growth_rate": round(annual_growth, 4),
                }
            )
            eps_forecast.append({"year": forecast_year, "eps": round(eps_run, 4)})
            fcf_forecast.append({"year": forecast_year, "fcf": round(fcf_run, 2)})

        bull_growth = min(growth + 0.03, 0.40)
        bear_growth = max(growth - 0.03, -0.25)
        revenue_2028 = rev_forecast[-1]["revenue"] if rev_forecast else revenue
        eps_2028 = eps_forecast[-1]["eps"] if eps_forecast else eps

        return {
            "revenue_forecast": rev_forecast,
            "earnings_forecast": eps_forecast,
            "free_cash_flow_forecast": fcf_forecast,
            "margin_projections": {
                "gross_margin": round(self._coerce_float(financials.get("gross_margin"), 0.35), 4),
                "operating_margin": round(self._coerce_float(financials.get("operating_margin"), 0.15), 4),
                "net_margin": round(self._coerce_float(financials.get("net_margin"), 0.10), 4),
            },
            "key_assumptions": [
                "Deterministic forecast mode enabled",
                "Growth rate derived from existing growth analysis inputs",
                "Linear fade applied to avoid over-extrapolation",
            ],
            "scenario_analysis": {
                "base_case": {"revenue_growth": round(growth, 4), "eps": round(eps_2028, 4)},
                "bull_case": {
                    "revenue_growth": round(bull_growth, 4),
                    "eps": round(eps_2028 * (1 + max(bull_growth - growth, 0)), 4),
                },
                "bear_case": {
                    "revenue_growth": round(bear_growth, 4),
                    "eps": round(eps_2028 * (1 - max(growth - bear_growth, 0)), 4),
                },
            },
            "confidence_intervals": {
                "revenue_2028": [
                    round(revenue_2028 * 0.9, 2),
                    round(revenue_2028 * 1.1, 2),
                ],
                "eps_2028": [round(eps_2028 * 0.9, 4), round(eps_2028 * 1.1, 4)],
            },
            "fallback_used": True,
        }

    def _build_deterministic_fundamental_report_payload(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build deterministic fundamental report payload."""
        valuation_data = analysis_data.get("valuation", {})
        if isinstance(valuation_data, dict) and isinstance(valuation_data.get("response"), dict):
            valuation_data = valuation_data.get("response", {})
        elif not isinstance(valuation_data, dict):
            valuation_data = {}

        ratios = analysis_data.get("ratios", {}) or {}
        company_profile = analysis_data.get("company_data", {}) or {}
        current_price = self._coerce_float(ratios.get("current_price"), 0.0)
        fair_value = self._coerce_float(
            valuation_data.get("fair_value_estimate")
            or valuation_data.get("fair_value")
            or company_profile.get("current_price")
            or current_price,
            0.0,
        )
        upside_pct = ((fair_value - current_price) / current_price) * 100 if current_price > 0 else 0.0

        if upside_pct >= 15:
            recommendation = "buy"
        elif upside_pct <= -15:
            recommendation = "sell"
        else:
            recommendation = "hold"

        return {
            "executive_summary": (
                "Deterministic fallback used because LLM fundamental synthesis returned empty output."
            ),
            "investment_thesis": (
                "Focus on valuation discipline and execution quality while monitoring cyclical risk."
            ),
            "financial_analysis_summary": (
                "Core valuation and ratio inputs are available; narrative synthesis used fallback mode."
            ),
            "valuation_assessment": valuation_data.get("valuation_stance", "uncertain"),
            "growth_prospects": "Moderate growth with scenario uncertainty.",
            "risk_analysis": valuation_data.get(
                "valuation_risks",
                "Model divergence and macro sensitivity remain key risks.",
            ),
            "competitive_position": "Refer to deterministic competitive analysis output.",
            "investment_grade": valuation_data.get("investment_grade", "B"),
            "price_target": round(fair_value, 2),
            "investment_recommendation": recommendation,
            "recommendation": recommendation,
            "key_catalysts": [
                "Execution versus guidance",
                "Margin stability",
                "Cash flow resilience",
            ],
            "key_risks": [
                "Valuation compression risk",
                "Demand cyclicality",
                "Macro regime shift",
            ],
            "fallback_used": True,
        }

    async def _calculate_quality_score(
        self, health: Dict, growth: Dict, profitability: Dict, competitive: Dict
    ) -> float:
        """Calculate overall company quality score"""
        scores = []
        weights = []

        # Financial health score (30% weight)
        if "overall_health_score" in health:
            scores.append(health["overall_health_score"])
            weights.append(0.30)

        # Growth score (25% weight)
        if "growth_score" in growth:
            scores.append(growth["growth_score"])
            weights.append(0.25)

        # Profitability score (25% weight)
        if "profitability_score" in profitability:
            scores.append(profitability["profitability_score"])
            weights.append(0.25)

        # Competitive position score (20% weight)
        if "strategic_positioning_score" in competitive:
            scores.append(competitive["strategic_positioning_score"])
            weights.append(0.20)

        # Calculate weighted average
        if scores and weights:
            quality_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
            return float(quality_score)

        return 50.0  # Default middle score

    async def _synthesize_fundamental_report(self, analysis_data: Dict) -> Dict:
        """Synthesize comprehensive fundamental analysis report"""
        # Extract symbol, data quality, confidence, and period for caching
        symbol = analysis_data.get("symbol", "UNKNOWN")
        data_quality = analysis_data.get("data_quality", {})
        confidence = analysis_data.get("confidence", {})
        fiscal_period = analysis_data.get("fiscal_period")  # Extract period from analysis_data

        if self.use_deterministic and self.deterministic_fundamental_report_generation:
            self.logger.debug(
                "%s - Using deterministic fundamental report generation (LLM bypass)",
                symbol,
            )
            deterministic_payload = self._build_deterministic_fundamental_report_payload(analysis_data)
            return self._wrap_llm_response(
                response=deterministic_payload,
                model=self.models["quality"],
                prompt="deterministic_fundamental_report_generation",
                temperature=0.3,
                top_p=0.9,
                format="json",
                period=fiscal_period,
            )

        # Check if TOON format is enabled
        use_toon = getattr(self.config.ollama, "use_toon_format", False) and getattr(
            self.config.ollama, "toon_agents", {}
        ).get("fundamental_analysis", False)

        # Format data section (TOON or JSON)
        if use_toon:
            # Extract quarterly data for TOON formatting (63% token savings)
            quarterly_data = analysis_data.get("quarterly_data", [])

            if quarterly_data and isinstance(quarterly_data, list) and len(quarterly_data) > 0:
                try:
                    # Convert QuarterlyData objects to dicts if needed
                    quarterly_dicts = []
                    for q in quarterly_data:
                        if hasattr(q, "__dict__"):
                            quarterly_dicts.append(vars(q))
                        elif isinstance(q, dict):
                            quarterly_dicts.append(q)

                    if quarterly_dicts:
                        # Convert to TOON format
                        toon_quarterly = to_toon_quarterly(quarterly_dicts)

                        # Remove quarterly_data from analysis_data to avoid duplication
                        remaining_data = {k: v for k, v in analysis_data.items() if k != "quarterly_data"}

                        # Build data section with TOON quarterly + JSON for other data
                        data_section = (
                            f"{toon_quarterly}\n\nAdditional Analysis:\n{json.dumps(remaining_data, indent=2)[:8000]}"
                        )
                    else:
                        # No valid quarterly data, fall back to JSON
                        data_section = json.dumps(analysis_data, indent=2)[:10000]
                except Exception as e:
                    self.logger.warning(f"Failed to convert quarterly data to TOON for {symbol}: {e}")
                    data_section = json.dumps(analysis_data, indent=2)[:10000]
            else:
                # No quarterly data, use JSON
                data_section = json.dumps(analysis_data, indent=2)[:10000]
        else:
            # TOON disabled, use JSON (current behavior)
            data_section = json.dumps(analysis_data, indent=2)[:10000]

        prompt = f"""
        Synthesize a comprehensive fundamental analysis report:

        DATA QUALITY ASSESSMENT:
        - Overall Quality: {data_quality.get("quality_grade", "Unknown")} ({_safe_fmt_pct(data_quality.get("data_quality_score", 0))})
        - {data_quality.get("assessment", "Data quality information not available")}
        - Core Metrics: {data_quality.get("core_metrics_populated", "N/A")} populated
        - Market Data: {data_quality.get("market_metrics_populated", "N/A")} populated
        - Ratio Metrics: {data_quality.get("ratio_metrics_populated", "N/A")} populated
        - Consistency Issues: {", ".join(data_quality.get("consistency_issues", [])) or "None detected"}

        DATA ENRICHMENT IMPACT (FEATURE #3):
        - Raw Extraction Quality: {_safe_fmt_pct(data_quality.get("extraction_quality", 0))}
        - Enhanced Quality (after enrichment): {_safe_fmt_pct(data_quality.get("data_quality_score", 0))}
        - Quality Improvement: +{_safe_fmt_float(data_quality.get("quality_improvement", 0), 1)} points
        - Enhancement Summary: {data_quality.get("enhancement_summary", "N/A")}

        ANALYSIS CONFIDENCE LEVEL:
        - Confidence: {confidence.get("confidence_level", "UNKNOWN")} ({confidence.get("confidence_score", 0)}/100)
        - Rationale: {confidence.get("rationale", "No confidence assessment available")}
        - Based on Data Quality: {confidence.get("quality_grade", "Unknown")} quality data

        {data_section}

        Create a structured investment report with:
        1. Executive Summary
        2. Investment Thesis
        3. Financial Analysis Summary
        4. Valuation Assessment
        5. Growth Prospects
        6. Risk Analysis
        7. Competitive Position
        8. Investment Grade (AAA to D)
        9. Price Target (12-month)
        10. Investment Recommendation (strong buy/buy/hold/sell/strong sell)
        11. Key Catalysts
        12. Key Risks

        Provide clear, actionable insights for investors.

        IMPORTANT: The data quality assessment above should influence your confidence levels.
        - If data quality is Excellent/Good (≥75%): High confidence in analysis
        - If data quality is Fair (60-75%): Moderate confidence, note data limitations
        - If data quality is Poor/Very Poor (<60%): Low confidence, significant data concerns

        Adjust your investment recommendation strength and price target confidence based on data quality.

        Before generating the JSON, think step-by-step about the analysis. Put your thinking process inside <think> and </think> tags.

        Return a JSON object that strictly follows the schema below (values are illustrative):
        {{
          "executive_summary": "The company is a market leader with strong growth prospects and a wide economic moat. The stock is currently undervalued and offers an attractive risk/reward profile.",
          "investment_thesis": "The company is well-positioned to benefit from the secular growth in its industry. Its strong brand, network effects, and high switching costs provide a sustainable competitive advantage.",
          "financial_analysis_summary": "The company has a strong financial profile, with a history of consistent revenue growth, expanding margins, and strong cash flow generation.",
          "valuation_assessment": "The stock is currently trading at a discount to its intrinsic value, with a potential upside of 20% to our fair value estimate of $150.",
          "growth_prospects": "The company has multiple growth drivers, including new product launches, expansion into new markets, and strategic acquisitions.",
          "risk_analysis": "The main risks to our thesis are increased competition, regulatory changes, and a slowdown in the overall economy.",
          "competitive_position": "The company has a strong competitive position, with a dominant market share and a wide economic moat.",
          "investment_grade": "A",
          "price_target": 150.00,
          "investment_recommendation": "buy",
          "key_catalysts": [
            "Successful launch of new products",
            "Expansion into new geographic markets"
          ],
          "key_risks": [
            "Increased competition",
            "Regulatory changes"
          ]
        }}

        """

        prompt_name = "_synthesize_fundamental_report_prompt"
        self._debug_log_prompt(prompt_name, prompt)

        # Build system prompt with optional TOON explanation
        system_prompt = "You are a senior equity analyst providing investment recommendations."
        if use_toon and quarterly_data:
            system_prompt += "\n\n" + TOONFormatter.get_format_explanation()

        response = await self.ollama.generate(
            model=self.models["quality"],
            prompt=prompt,
            system=system_prompt,
            format="json",
            period=fiscal_period,  # Period-based caching
            prompt_name=prompt_name,
        )

        self._debug_log_response(prompt_name, response)

        # DUAL CACHING: Cache LLM response separately
        await self._cache_llm_response(
            response=response,
            model=self.models["quality"],
            symbol=symbol,
            llm_type="fundamental_investment_thesis",
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=fiscal_period,  # Period-based caching
        )

        wrapped_report = self._wrap_llm_response(
            response=response,
            model=self.models["quality"],
            prompt=prompt,
            temperature=0.3,
            top_p=0.9,
            format="json",
            period=fiscal_period,  # Period-based caching
        )

        payload = wrapped_report.get("response", {})
        if not isinstance(payload, dict) or not payload:
            self.logger.warning(
                "Fundamental synthesis returned empty/invalid payload for %s. Using deterministic fallback report.",
                symbol,
            )
            fallback_payload = self._build_deterministic_fundamental_report_payload(analysis_data)

            return self._wrap_llm_response(
                response=fallback_payload,
                model=self.models["quality"],
                prompt=prompt,
                temperature=0.3,
                top_p=0.9,
                format="json",
                period=fiscal_period,
            )

        return wrapped_report

    def _calculate_growth_rate(self, financials: Dict, metric: str) -> float:
        """Calculate compound annual growth rate for a metric"""
        # Simplified CAGR calculation (would use historical data in production)
        # This is a placeholder that would access historical data
        return 0.10  # 10% placeholder growth rate

    def _calculate_ttm_net_income(self, quarterly_data: List, symbol: str) -> float:
        """
        Calculate Trailing Twelve Months (TTM) net income from quarterly data.

        This is CRITICAL for accurate P/E ratio calculations. Market P/E ratios
        should ALWAYS use TTM earnings, not quarterly earnings.

        Args:
            quarterly_data: List of quarterly data objects (last 12 quarters)
            symbol: Stock symbol for logging

        Returns:
            TTM net income (sum of last 4 quarters), or 0 if insufficient data
        """
        ttm_metrics = calculate_ttm_metrics(
            quarterly_data=quarterly_data,
            symbol=symbol,
            logger=self.logger,
        )
        ttm_net_income = float(ttm_metrics.get("net_income", 0.0))

        if ttm_net_income > 0:
            self.logger.info("✅ %s - TTM Net Income: $%s", symbol, format(ttm_net_income, ",.0f"))
        else:
            self.logger.warning(
                "❌ %s - TTM Net Income is zero or negative: $%s",
                symbol,
                format(ttm_net_income, ",.0f"),
            )

        return ttm_net_income

    def _get_historical_trend(self, financials: Dict) -> Dict:
        """Get historical financial trends"""
        return _get_historical_trend_helper(financials)

    def _summarize_company_data(self, company_data: Dict) -> Dict:
        """Create summary of company data for report"""
        return _summarize_company_data_helper(company_data)

    def _extract_latest_financials(self, quarterly_data: List) -> Dict:
        """Extract latest financial statement from quarterly data (supports both Dict and QuarterlyData objects)"""
        return _extract_latest_financials_helper(quarterly_data)
