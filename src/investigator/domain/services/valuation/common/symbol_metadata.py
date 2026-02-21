# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Symbol metadata lookup for sector/industry classification.

Provides centralized access to symbol metadata:
- Sector classification with config-based overrides
- Industry classification with config-based overrides
- Normalized sector names for consistent lookup

This eliminates duplicate metadata lookup logic between legacy CLI and victor_invest.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class SymbolMetadata:
    """Lookup symbol metadata (sector, industry) from configuration.

    Singleton class that loads config once and caches metadata lookups.

    Methods:
        get_sector_industry: Get sector and industry for a symbol
        get_sector: Get sector only
        get_industry: Get industry only
        load_config: Load or reload config from YAML

    Example:
        >>> sector, industry = SymbolMetadata.get_sector_industry("AAPL")
        >>> print(f"AAPL - Sector: {sector}, Industry: {industry}")
        Technology, Technology Hardware
    """

    _config: Optional[Dict] = None
    _config_path: Optional[Path] = None
    _sector_overrides: Dict[str, str] = {}
    _industry_overrides: Dict[str, str] = {}

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> Dict:
        """Load symbol metadata configuration from config.yaml.

        Args:
            config_path: Path to config.yaml (defaults to repo root config.yaml)

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If config.yaml not found
            yaml.YAMLError: If config.yaml is invalid
        """
        if config_path:
            cls._config_path = Path(config_path)
        else:
            # Default: config.yaml in repository root
            current_file = Path(__file__)
            # Navigate from: src/investigator/domain/services/valuation/common/
            # to: repo_root/config.yaml
            repo_root = (
                current_file.parent.parent.parent.parent.parent.parent.parent
            )
            cls._config_path = repo_root / "config.yaml"

        if not cls._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {cls._config_path}")

        with open(cls._config_path, "r") as f:
            config = yaml.safe_load(f)

        cls._config = config

        # Load sector overrides
        cls._load_sector_overrides(config)
        cls._load_industry_overrides(config)

        logger.info(f"Loaded symbol metadata config from {cls._config_path}")
        return config

    @classmethod
    def _load_sector_overrides(cls, config: Dict) -> None:
        """Load sector overrides from config.yaml."""
        cls._sector_overrides = {}
        if not config:
            return

        # Check for symbol_sectors section (legacy structure)
        symbol_sectors = config.get("symbol_sectors", {})
        if symbol_sectors:
            cls._sector_overrides.update(symbol_sectors)

        # Check for sector_override in company_metadata section
        company_metadata = config.get("company_metadata", {})
        if company_metadata:
            sector_overrides = company_metadata.get("sector_override", {})
            if sector_overrides:
                cls._sector_overrides.update(sector_overrides)

        # Check for sector_override in dcf_valuation section
        dcf_valuation = config.get("dcf_valuation", {})
        if dcf_valuation:
            sector_overrides = dcf_valuation.get("sector_override", {})
            if sector_overrides:
                cls._sector_overrides.update(sector_overrides)

        logger.debug(f"Loaded {len(cls._sector_overrides)} sector overrides")

    @classmethod
    def _load_industry_overrides(cls, config: Dict) -> None:
        """Load industry overrides from config.yaml."""
        cls._industry_overrides = {}
        if not config:
            return

        # Check for company_metadata section
        company_metadata = config.get("company_metadata", {})
        if company_metadata:
            industry_overrides = company_metadata.get("industry_overrides", {})
            if industry_overrides:
                cls._industry_overrides.update(industry_overrides)

        logger.debug(f"Loaded {len(cls._industry_overrides)} industry overrides")

    @classmethod
    def _ensure_config_loaded(cls) -> None:
        """Ensure config is loaded, load if not."""
        if cls._config is None:
            cls.load_config()

    @classmethod
    def get_sector_industry(
        cls, symbol: str, *, fallback_sector: Optional[str] = None, fallback_industry: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Get sector and industry for a symbol from config overrides.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
            fallback_sector: Sector to use if no override found
            fallback_industry: Industry to use if no override found

        Returns:
            Tuple of (sector, industry). Industry may be None if not found.

        Example:
            >>> sector, industry = SymbolMetadata.get_sector_industry("DASH")
            >>> print(f"DASH - Sector: {sector}, Industry: {industry}")
            ('Technology', 'Internet Content & Information')
        """
        cls._ensure_config_loaded()

        symbol = symbol.upper().strip()

        # Check sector override
        sector = cls._sector_overrides.get(symbol)
        if not sector and fallback_sector:
            sector = fallback_sector

        # Check industry override
        industry = cls._industry_overrides.get(symbol)
        if not industry and fallback_industry:
            industry = fallback_industry

        if not sector:
            raise ValueError(f"No sector found for {symbol} and no fallback provided")

        return sector, industry

    @classmethod
    def get_sector(cls, symbol: str, *, fallback_sector: Optional[str] = None) -> str:
        """Get sector for a symbol.

        Args:
            symbol: Stock ticker symbol
            fallback_sector: Sector to use if no override found

        Returns:
            Sector name

        Raises:
            ValueError: If no sector found and no fallback provided
        """
        sector, _ = cls.get_sector_industry(symbol, fallback_sector=fallback_sector)
        return sector

    @classmethod
    def get_industry(cls, symbol: str, *, fallback_industry: Optional[str] = None) -> Optional[str]:
        """Get industry for a symbol.

        Args:
            symbol: Stock ticker symbol
            fallback_industry: Industry to use if no override found

        Returns:
            Industry name or None if not found
        """
        _, industry = cls.get_sector_industry(symbol, fallback_industry=fallback_industry)
        return industry
