# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
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

"""Sector multiple lookups from configuration.

Provides centralized access to sector/industry valuation multiples from config.yaml:
- P/E multiples by sector
- P/S multiples by sector
- EV/EBITDA multiples by sector
- Industry-level overrides

This eliminates duplicate config reading logic between legacy CLI and victor_invest.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class SectorMultiples:
    """Lookup sector and industry valuation multiples from config.yaml.

    Singleton class that loads config once and caches sector multiples.

    Methods:
        get_sector_multiple: Get sector PE/PS/EV_EBITDA multiple
        get_industry_override: Check for industry-level override
        load_config: Load or reload config from YAML

    Example:
        >>> pe = SectorMultiples.get_sector_multiple("Technology", "pe")
        >>> print(f"Technology P/E: {pe}")
        18.0
        >>> ps = SectorMultiples.get_industry_override("Software - Application", "ps")
    """

    _config: Optional[Dict[str, Any]] = None
    _config_path: Optional[Path] = None

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load sector multiples configuration from config.yaml.

        Args:
            config_path: Path to config.yaml (defaults to repo root config.yaml)

        Returns:
            Configuration dictionary with sector_multiples section

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
            # Go up: common/ -> valuation/ -> services/ -> domain/ -> investigator/ -> src/ -> repo_root/
            repo_root = current_file.parent.parent.parent.parent.parent.parent.parent
            cls._config_path = repo_root / "config.yaml"

        if not cls._config_path.exists():
            # Fallback to environment or investigator config module
            try:
                from investigator.config import get_config

                config_obj = get_config()
                # Convert Config object to dict for sector_multiples access
                cls._config = {
                    "sector_multiples": {
                        "technology": (
                            config_obj.sector_pe_multiples if hasattr(config_obj, "sector_pe_multiples") else {}
                        ),
                        "default": {
                            "pe": 15.0,
                            "ps": 5.0,
                            "ev_ebitda": 11.0,
                            "pb": 2.0,
                        },
                    },
                    "industry_overrides": (
                        config_obj.industry_ev_ebitda_overrides
                        if hasattr(config_obj, "industry_ev_ebitda_overrides")
                        else {}
                    ),
                }
                return cls._config
            except ImportError:
                raise FileNotFoundError(f"Config file not found: {cls._config_path}")

        with open(cls._config_path, "r") as f:
            config = yaml.safe_load(f)

        cls._config = config
        logger.info(f"Loaded sector multiples config from {cls._config_path}")
        return config

    @classmethod
    def _ensure_config_loaded(cls) -> None:
        """Ensure config is loaded, load if not."""
        if cls._config is None:
            cls.load_config()

    @classmethod
    def get_sector_multiple(cls, sector: str, metric: str) -> Optional[float]:
        """Get sector valuation multiple from config.

        Args:
            sector: Sector name (e.g., "Technology", "Healthcare")
            metric: Metric type ("pe", "ps", "ev_ebitda", "pb")

        Returns:
            Sector multiple value or None if not found

        Example:
            >>> pe = SectorMultiples.get_sector_multiple("Technology", "pe")
            >>> print(f"Technology sector P/E: {pe}")
            18.0
        """
        cls._ensure_config_loaded()

        if cls._config is None:
            return None

        # Handle actual config structure: pe_multiples.sector_defaults.Technology
        # Try the metric-specific section first (pe_multiples, ps_multiples, etc.)
        metric_section = cls._config.get(f"{metric}_multiples", {})
        if metric_section:
            # Check sector_defaults
            sector_defaults = metric_section.get("sector_defaults", {})
            # Case-insensitive lookup
            for key, value in sector_defaults.items():
                if key.lower() == sector.lower():
                    return float(value) if value is not None else None

            # Check industry_overrides if industry was provided
            industry_overrides = metric_section.get("industry_overrides", {})
            for key, value in industry_overrides.items():
                if key.lower() == sector.lower():
                    return float(value) if value is not None else None

        # Fallback to legacy sector_multiples structure (for backward compatibility)
        sector_multiples = cls._config.get("sector_multiples", {})
        sector_key = sector.lower().replace(" ", "_")

        # Try sector-specific value
        sector_data = sector_multiples.get(sector_key, {})
        if sector_data:
            value = sector_data.get(metric)
            if value is not None:
                return float(value)

        # Fall back to default
        default = sector_multiples.get("default", {})
        return default.get(metric)

    @classmethod
    def get_industry_override(cls, industry: str, metric: str) -> Optional[float]:
        """Check for industry-level override in config.

        Industry overrides provide more granular multiples when sector-level
        is too broad. For example, "Internet Content & Information" may have
        a different EV/EBITDA multiple than the broader "Technology" sector.

        Args:
            industry: Industry name (e.g., "Software - Application")
            metric: Metric type ("pe", "ps", "ev_ebitda", "pb")

        Returns:
            Industry override multiple or None if not defined

        Example:
            >>> ev_ebitda = SectorMultiples.get_industry_override(
            ...     "Internet Content & Information", "ev_ebitda"
            ... )
            >>> print(f"Industry EV/EBITDA override: {ev_ebitda}")
            28.0
        """
        cls._ensure_config_loaded()

        if cls._config is None:
            return None

        # Handle actual config structure: pe_multiples.industry_overrides
        metric_section = cls._config.get(f"{metric}_multiples", {})
        if metric_section:
            industry_overrides = metric_section.get("industry_overrides", {})
            if industry_overrides:
                # Try exact match first
                if industry in industry_overrides:
                    value = industry_overrides[industry]
                    if value is not None:
                        return float(value)

                # Try case-insensitive match
                industry_lower = industry.lower() if industry else ""
                for key, value in industry_overrides.items():
                    if key.lower() == industry_lower and value is not None:
                        return float(value)

        # Fallback to legacy industry_overrides structure
        overrides = cls._config.get("industry_overrides", {})

        for metric_key, override_config in overrides.items():
            if metric_key == f"{metric}_industry_overrides":
                # This is a dict of industry -> multiple
                if isinstance(override_config, dict):
                    # Try exact match first
                    if industry in override_config:
                        value = override_config[industry]
                        if value is not None:
                            return float(value)

                    # Try case-insensitive match
                    industry_lower = industry.lower()
                    for key, value in override_config.items():
                        if key.lower() == industry_lower and value is not None:
                            return float(value)

        return None

    @classmethod
    def get_multiple_with_override(cls, sector: str, industry: Optional[str], metric: str) -> float:
        """Get valuation multiple with industry override check.

        This is the primary method to use - it checks for industry overrides
        first, then falls back to sector multiple, then to default.

        Args:
            sector: Sector name (e.g., "Technology", "Healthcare")
            industry: Industry name for override check (optional)
            metric: Metric type ("pe", "ps", "ev_ebitda", "pb")

        Returns:
            Multiple value (industry override > sector > default)

        Raises:
            ValueError: If no multiple found at all

        Example:
            >>> multiple = SectorMultiples.get_multiple_with_override(
            ...     sector="Technology",
            ...     industry="Software - Application",
            ...     metric="ev_ebitda"
            ... )
            >>> print(f"EV/EBITDA multiple: {multiple}x")
            30.0  # Industry override
        """
        # First check industry override
        if industry:
            override = cls.get_industry_override(industry, metric)
            if override is not None:
                logger.debug(f"Using industry override for {industry}: {metric}={override}")
                return override

        # Then check sector multiple
        sector_value = cls.get_sector_multiple(sector, metric)
        if sector_value is not None:
            return sector_value

        # Finally, check default
        cls._ensure_config_loaded()
        if cls._config:
            default = cls._config.get("sector_multiples", {}).get("default", {})
            default_value = default.get(metric)
            if default_value is not None:
                return default_value

        raise ValueError(f"No {metric} multiple found for sector={sector}, industry={industry}")
