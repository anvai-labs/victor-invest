"""
Company Metadata Service

Centralized service for fetching company metadata (sector, industry, etc.)
from multiple sources with fallback priority and caching.

Author: InvestiGator Team
Date: 2025-11-07
"""

import json
import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class CompanyMetadataService:
    """
    Service for fetching company metadata from multiple sources.

    Features:
    - Multi-source fallback (database → JSON → defaults)
    - Sector name normalization
    - In-memory caching for performance
    - Configurable sector mappings

    Priority for sector/industry lookup:
    1. sec_sector (SEC CompanyFacts - most authoritative)
    2. Sector (Yahoo Finance - good coverage)
    3. Peer Group JSON (data/sector_mapping.json)
    4. "Unknown" (final fallback)
    """

    def __init__(
        self,
        database_engine: Engine | None = None,
        sector_normalization: dict[str, list] | None = None,
        peer_group_json_path: str = "data/sector_mapping.json",
        sector_map_txt_path: str = "data/sector_industry_ticker_map.txt",
    ):
        """
        Initialize CompanyMetadataService.

        Args:
            database_engine: SQLAlchemy engine connected to stock database.
                           If None, will create default connection.
            sector_normalization: Dict mapping canonical sector → [variants]
                                Example: {"Technology": ["Information Technology", "Tech", ...]}
            peer_group_json_path: Path to peer group sector mapping JSON file
        """
        self.engine = database_engine or self._create_default_engine()
        self.sector_normalization = sector_normalization or {}
        self.peer_group_json_path = peer_group_json_path
        self.sector_map_txt_path = sector_map_txt_path

        # Load peer group mapping
        self.peer_group_mapping = self._load_peer_group_sectors()
        self.extended_sector_mapping = self._load_sector_map_txt()
        self.sector_overrides = self._load_sector_overrides()
        self.industry_overrides = self._load_industry_overrides()

        # Cache for database lookups (symbol → (sector, industry))
        # Using functools.lru_cache for automatic size management
        self._cache: dict[str, tuple[str, str | None]] = {}

    def _create_default_engine(self) -> Engine:
        """
        Create default database engine for stock database.

        Returns:
            SQLAlchemy engine connected to stock database
        """
        from investigator.config import get_config

        config = get_config()
        stock_password = os.environ.get("STOCK_DB_PASSWORD")
        stock_host = os.environ.get("STOCK_DB_HOST", config.database.host)
        if not stock_password:
            raise OSError(
                "STOCK_DB_PASSWORD environment variable not set. Please set it or source your ~/.investigator/env file."
            )
        stock_db_url = f"postgresql://stockuser:{stock_password}@{stock_host}:{config.database.port}/stock"
        engine = create_engine(stock_db_url, pool_pre_ping=True)
        logger.info("Created default database engine for stock database")
        return engine

    def _load_peer_group_sectors(self) -> dict[str, str]:
        """
        Load peer group sector mapping from JSON file.

        Returns:
            Dict mapping symbol → sector (e.g., {"NVDA": "Technology", ...})
        """
        if not os.path.exists(self.peer_group_json_path):
            logger.warning(f"Peer group sector mapping file not found: {self.peer_group_json_path}")
            return {}

        try:
            with open(self.peer_group_json_path, "r") as f:
                sector_mapping = json.load(f)

            logger.info(f"Loaded {len(sector_mapping)} symbols from peer group sector mapping")
            return sector_mapping

        except Exception as e:
            logger.warning(f"Error loading peer group sector mapping: {e}")
            return {}

    def _load_sector_map_txt(self) -> dict[str, dict[str, str | None]]:
        """
        Parse the comprehensive sector/industry map exported as a pipe-delimited text table.
        """
        mapping: dict[str, dict[str, str | None]] = {}
        if not os.path.exists(self.sector_map_txt_path):
            logger.debug("Sector map txt not found: %s", self.sector_map_txt_path)
            return mapping

        try:
            with open(self.sector_map_txt_path, "r") as handle:
                for line in handle:
                    if "|" not in line:
                        continue
                    parts = [part.strip() for part in line.split("|")]
                    if len(parts) < 5:
                        continue
                    ticker = parts[0]
                    if not ticker or ticker.lower() == "ticker":
                        continue
                    sec_sector = parts[1]
                    alt_sector = parts[2]
                    sec_industry = parts[3]
                    alt_industry = parts[4]

                    sector_value = sec_sector or alt_sector
                    industry_value = sec_industry or alt_industry or None

                    ticker_upper = ticker.upper()
                    mapping[ticker_upper] = {
                        "sector": sector_value.strip() if sector_value else "Unknown",
                        "industry": industry_value.strip() if industry_value else None,
                    }

            logger.info("Loaded %s symbols from sector_industry_ticker_map", len(mapping))
        except Exception as exc:
            logger.warning("Failed to load sector map txt (%s): %s", self.sector_map_txt_path, exc)

        return mapping

    def _load_sector_overrides(self) -> dict[str, str]:
        """
        Load sector overrides from config.yaml for misclassified companies.

        Returns:
            Dict mapping symbol → overridden sector name
        """
        import yaml

        try:
            config_path = "config.yaml"
            if not os.path.isfile(config_path):
                return {}

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            dcf_config = config.get("dcf_valuation", {})
            overrides = dcf_config.get("sector_override", {})

            if overrides:
                logger.info(f"Loaded {len(overrides)} sector overrides from config.yaml")

            return overrides
        except Exception as exc:
            logger.warning(f"Failed to load sector overrides from config.yaml: {exc}")
            return {}

    def _load_industry_overrides(self) -> dict[str, str]:
        """
        Load industry overrides from config.yaml for business-model corrections.

        Returns:
            Dict mapping symbol -> overridden industry name
        """
        import yaml

        try:
            config_path = "config.yaml"
            if not os.path.isfile(config_path):
                return {}

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            dcf_config = config.get("dcf_valuation", {})
            overrides = dcf_config.get("industry_override", {})

            if overrides:
                logger.info(f"Loaded {len(overrides)} industry overrides from config.yaml")

            return overrides
        except Exception as exc:
            logger.warning(f"Failed to load industry overrides from config.yaml: {exc}")
            return {}

    def get_sector_industry(self, symbol: str, use_cache: bool = True) -> tuple[str, str | None]:
        """
        Get normalized sector and industry for a symbol.

        Priority:
        0. Config.yaml sector overrides (highest priority - for misclassified companies)
        1. Database (sec_sector, then Sector column)
        2. Peer group JSON mapping
        3. "Unknown" fallback

        Args:
            symbol: Stock ticker symbol
            use_cache: Whether to use in-memory cache (default: True)

        Returns:
            (normalized_sector, industry) tuple
            Example: ("Technology", "Semiconductors")
        """
        # Priority 0: Check for sector/industry overrides (for misclassified companies)
        symbol_upper = symbol.upper()
        has_sector_override = symbol_upper in self.sector_overrides
        has_industry_override = symbol_upper in self.industry_overrides
        if has_sector_override or has_industry_override:
            db_sector = "Unknown"
            db_industry = None
            needs_db_lookup = not has_sector_override or not has_industry_override
            if needs_db_lookup:
                db_sector, db_industry = self._get_from_database(symbol)

            if has_sector_override:
                override_sector = self.sector_overrides[symbol_upper]
                logger.info(
                    f"{symbol} - Using sector override from config.yaml: {override_sector} (correcting database misclassification)"
                )
                normalized_sector = self._normalize_sector_name(override_sector)
            else:
                normalized_sector = db_sector

            if has_industry_override:
                industry = self.industry_overrides[symbol_upper]
                logger.info(
                    f"{symbol} - Using industry override from config.yaml: {industry} (business-model override)"
                )
            else:
                industry = db_industry

            mapped = self.extended_sector_mapping.get(symbol_upper)
            if mapped:
                mapped_sector = mapped.get("sector")
                mapped_industry = mapped.get("industry")
                if normalized_sector == "Unknown" and mapped_sector:
                    normalized_sector = self._normalize_sector_name(mapped_sector)
                if not industry and mapped_industry:
                    industry = mapped_industry
                    logger.info(f"{symbol} - Using industry from sector map fallback: {industry}")

            if use_cache:
                self._cache[symbol] = (normalized_sector, industry)
            return (normalized_sector, industry)

        # Priority 1: Check cache
        if use_cache and symbol in self._cache:
            return self._cache[symbol]

        # Priority 2: Try database lookup
        sector, industry = self._get_from_database(symbol)

        # If database returned "Unknown", try peer group fallback
        symbol_upper = symbol.upper()
        if sector == "Unknown" and self.peer_group_mapping:
            json_sector = self.peer_group_mapping.get(symbol_upper)
            if json_sector:
                logger.info(f"{symbol} - Using peer group sector: {json_sector}")
                sector = self._normalize_sector_name(json_sector)
                industry = None  # JSON doesn't have industry

        # Last resort: use comprehensive text mapping with sector + industry
        if sector == "Unknown" and self.extended_sector_mapping:
            mapped = self.extended_sector_mapping.get(symbol_upper)
            if mapped:
                sector = self._normalize_sector_name(mapped["sector"])
                industry = mapped.get("industry")
                logger.info(
                    "%s - Using sector map txt fallback: sector=%s industry=%s",
                    symbol,
                    sector,
                    industry,
                )

        # Clean up whitespace (especially trailing newlines from database)
        if industry:
            industry = industry.strip()

        # Cache result
        if use_cache:
            self._cache[symbol] = (sector, industry)

        return sector, industry

    def _get_from_database(self, symbol: str) -> tuple[str, str | None]:
        """
        Fetch sector and industry from database.

        Args:
            symbol: Stock ticker symbol

        Returns:
            (normalized_sector, industry) tuple
        """
        query = text("""
            SELECT
                COALESCE(sec_sector, "Sector", 'Unknown') as sector,
                COALESCE(sec_industry, "Industry") as industry
            FROM symbol
            WHERE ticker = :symbol
        """)

        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"symbol": symbol}).fetchone()

            if result:
                raw_sector = result[0]
                industry = result[1]

                # Normalize sector name
                normalized_sector = self._normalize_sector_name(raw_sector)

                logger.debug(f"{symbol} - DB: sector={raw_sector} → {normalized_sector}, industry={industry}")
                return normalized_sector, industry
            else:
                # Symbol not in database
                logger.warning(f"{symbol} - Not found in symbol table")
                return "Unknown", None

        except Exception as e:
            # Database error
            logger.warning(f"{symbol} - Error fetching from database: {e}")
            return "Unknown", None

    def _normalize_sector_name(self, raw_sector: str) -> str:
        """
        Normalize sector name using SectorIndustryMapper.

        Args:
            raw_sector: Raw sector name from database or JSON

        Returns:
            Normalized canonical sector name
        """
        if not raw_sector:
            return "Unknown"

        # Use SectorIndustryMapper for normalization (single source of truth)
        from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

        return SectorIndustryMapper.to_standard(raw_sector)

    def _normalize_industry_and_infer_sector(
        self, raw_industry: str | None, raw_sector: str | None = None
    ) -> tuple[str | None, str]:
        """
        Normalize industry name and ensure sector is inferred if needed.

        Args:
            raw_industry: Raw industry name from database or JSON
            raw_sector: Raw sector name (used for validation)

        Returns:
            (normalized_industry, normalized_sector) tuple
        """
        from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

        # Normalize sector first
        normalized_sector = self._normalize_sector_name(raw_sector) if raw_sector else "Unknown"

        # If industry is provided, validate it maps to the sector
        if raw_industry:
            # Check if industry maps to a different sector than what we have
            industry_sector = SectorIndustryMapper.get_sector_for_industry(raw_industry)
            if industry_sector and industry_sector != "Unknown":
                # Industry provides authoritative sector mapping
                if normalized_sector == "Unknown" or normalized_sector != industry_sector:
                    normalized_sector = industry_sector
            return raw_industry, normalized_sector

        return None, normalized_sector

    def get_sector(self, symbol: str, use_cache: bool = True) -> str:
        """
        Get normalized sector only (convenience method).

        Args:
            symbol: Stock ticker symbol
            use_cache: Whether to use cache

        Returns:
            Normalized sector name
        """
        sector, _ = self.get_sector_industry(symbol, use_cache=use_cache)
        return sector

    def get_industry(self, symbol: str, use_cache: bool = True) -> str | None:
        """
        Get industry only (convenience method).

        Args:
            symbol: Stock ticker symbol
            use_cache: Whether to use cache

        Returns:
            Industry name or None
        """
        _, industry = self.get_sector_industry(symbol, use_cache=use_cache)
        return industry

    def batch_get_sector_industry(self, symbols: list[str]) -> dict[str, tuple[str, str | None]]:
        """
        Fetch sector/industry for multiple symbols efficiently.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dict mapping symbol → (sector, industry)
        """
        results = {}

        # Check cache first
        uncached_symbols = [s for s in symbols if s not in self._cache]
        cached_symbols = [s for s in symbols if s in self._cache]

        # Return cached results
        for symbol in cached_symbols:
            results[symbol] = self._cache[symbol]

        if not uncached_symbols:
            return results

        # Batch query database for uncached symbols
        query = text("""
            SELECT
                ticker,
                COALESCE(sec_sector, "Sector", 'Unknown') as sector,
                COALESCE(sec_industry, "Industry") as industry
            FROM symbol
            WHERE ticker = ANY(:symbols)
        """)

        try:
            with self.engine.connect() as conn:
                db_results = conn.execute(query, {"symbols": uncached_symbols}).fetchall()

            # Process database results
            found_symbols = set()
            for row in db_results:
                symbol = row[0]
                raw_sector = row[1]
                industry = row[2]

                normalized_sector = self._normalize_sector_name(raw_sector)
                results[symbol] = (normalized_sector, industry)
                self._cache[symbol] = (normalized_sector, industry)
                found_symbols.add(symbol)

            # For symbols not found in DB, try peer group fallback
            not_found = set(uncached_symbols) - found_symbols
            for symbol in not_found:
                json_sector = self.peer_group_mapping.get(symbol)
                if json_sector:
                    normalized_sector = self._normalize_sector_name(json_sector)
                    results[symbol] = (normalized_sector, None)
                    self._cache[symbol] = (normalized_sector, None)
                else:
                    results[symbol] = ("Unknown", None)
                    self._cache[symbol] = ("Unknown", None)

        except Exception as e:
            logger.error(f"Error in batch query: {e}")
            # Fallback to individual lookups
            for symbol in uncached_symbols:
                results[symbol] = self.get_sector_industry(symbol, use_cache=True)

        return results

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.info("Cleared company metadata cache")

    def reload_sector_map(self):
        """Reload the sector map from file and clear related cache.

        Use this to pick up changes to sector_industry_ticker_map.txt
        without restarting the process.
        """
        self.extended_sector_mapping = self._load_sector_map_txt()
        logger.info("Reloaded sector map from file")
        # Clear the cache so new values will be used
        self._cache.clear()
        logger.info("Cleared cache after sector map reload")

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with cache metrics
        """
        return {
            "cached_symbols": len(self._cache),
            "peer_group_symbols": len(self.peer_group_mapping),
            "normalization_rules": len(self.sector_normalization),
        }
