# Copyright 2025 Vijaykumar Singh
# SPDX-License-Identifier: Apache-2.0
"""
Centralized Sector/Industry Name Mapping Service.

Provides bidirectional mapping between standard sector/industry names
and their database variants. This is the single source of truth for all
sector/industry name normalization across the codebase.

Usage:
    from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

    # Normalize database name to standard
    standard = SectorIndustryMapper.to_standard("Information Technology")
    # Returns: "Technology"

    # Get all database variants for querying
    variants = SectorIndustryMapper.to_database_variants("Financials")
    # Returns: ["Financials", "Finance", "Financial Services"]

    # Get parent sector for an industry
    sector = SectorIndustryMapper.get_sector_for_industry("Semiconductors")
    # Returns: "Technology"
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SectorIndustryMapper:
    """
    Centralized service for sector/industry name mapping.

    This class provides:
    1. Standardization of database variant names to canonical names
    2. Expansion of standard names to all database variants for querying
    3. Mapping of industries to their parent sectors

    All sector/industry name normalization should use this service.
    """

    # Standard sector name to database variants mapping
    # Key: Canonical sector name, Value: List of database variants
    SECTOR_MAPPING: Dict[str, List[str]] = {
        "Communication Services": ["Communication Services", "Telecommunications"],
        "Technology": ["Technology", "Information Technology"],
        "Financials": ["Financials", "Finance", "Financial Services"],
        "Healthcare": ["Healthcare", "Health Care"],
        "Consumer Discretionary": ["Consumer Discretionary", "Consumer Cyclical"],
        "Consumer Staples": ["Consumer Staples", "Consumer Defensive"],
        "Industrials": ["Industrials", "Industrial"],
        "Energy": ["Energy"],
        "Real Estate": ["Real Estate", "REITs"],
        "Utilities": ["Utilities"],
        "Materials": ["Materials", "Basic Materials"],
    }

    # Industry to sector mapping for granular lookups
    # Key: Industry name, Value: Parent sector
    INDUSTRY_TO_SECTOR: Dict[str, str] = {
        # Technology industries
        "Semiconductors": "Technology",
        "Semiconductor Equipment": "Technology",
        "Semiconductors & Semiconductor Equipment": "Technology",
        "Software": "Technology",
        "Software - Application": "Technology",
        "Software - Infrastructure": "Technology",
        "Information Technology Services": "Technology",
        "Computer Hardware": "Technology",
        "Technology Hardware": "Technology",
        "Communications Equipment": "Technology",
        "Electronics": "Technology",
        # Financials industries
        "Banks": "Financials",
        "Banks - Regional": "Financials",
        "Banks - Major": "Financials",
        "Asset Management": "Financials",
        "Insurance": "Financials",
        "Insurance - Brokers": "Financials",
        "Capital Markets": "Financials",
        "Credit Services": "Financials",
        "Financial Conglomerates": "Financials",
        # Healthcare industries
        "Biotechnology": "Healthcare",
        "Medical Devices": "Healthcare",
        "Pharmaceuticals": "Healthcare",
        "Drug Manufacturers": "Healthcare",
        "Drug Manufacturers - General": "Healthcare",
        "Healthcare Providers": "Healthcare",
        "Healthcare Plans": "Healthcare",
        # Consumer industries
        "Internet Retail": "Consumer Discretionary",
        "Specialty Retail": "Consumer Discretionary",
        "Retail": "Consumer Discretionary",
        "Restaurants": "Consumer Discretionary",
        "Auto Manufacturing": "Consumer Discretionary",
        "Automobile Manufacturers": "Consumer Discretionary",
        "Motor Vehicles": "Consumer Discretionary",
        "Auto Parts": "Consumer Discretionary",
        "Apparel": "Consumer Discretionary",
        "Luxury Goods": "Consumer Discretionary",
        "Packaged Foods": "Consumer Staples",
        "Beverages": "Consumer Staples",
        "Tobacco": "Consumer Staples",
        "Household Products": "Consumer Staples",
        # Industrials industries
        "Aerospace & Defense": "Industrials",
        "Defense": "Industrials",
        "Defense Contractors": "Industrials",
        "Machinery": "Industrials",
        "Industrial Products": "Industrials",
        "Construction & Engineering": "Industrials",
        "Transportation": "Industrials",
        "Airlines": "Industrials",
        "Railroads": "Industrials",
        # Real Estate
        "REITs": "Real Estate",
        "Real Estate Services": "Real Estate",
        # Energy industries
        "Oil & Gas": "Energy",
        "Oil & Gas E&P": "Energy",
        "Oil & Gas Integrated": "Energy",
        "Oil & Gas Refining": "Energy",
        "Energy Equipment": "Energy",
        # Utilities industries
        "Electric Utilities": "Utilities",
        "Gas Utilities": "Utilities",
        "Water Utilities": "Utilities",
        # Materials industries
        "Chemicals": "Materials",
        "Specialty Chemicals": "Materials",
        "Metals & Mining": "Materials",
        "Mining": "Materials",
        "Paper & Forest Products": "Materials",
        "Construction Materials": "Materials",
    }

    # Reverse mapping: database variant -> standard name (built lazily)
    _DATABASE_TO_STANDARD: Optional[Dict[str, str]] = None

    # All valid sector names cache (built lazily)
    _ALL_SECTOR_NAMES: Optional[List[str]] = None

    @classmethod
    def _build_reverse_mapping(cls) -> Dict[str, str]:
        """Build reverse mapping from database variants to standard names."""
        if cls._DATABASE_TO_STANDARD is None:
            cls._DATABASE_TO_STANDARD = {}
            for standard, variants in cls.SECTOR_MAPPING.items():
                for variant in variants:
                    cls._DATABASE_TO_STANDARD[variant] = standard
                    # Also add lowercase version for case-insensitive lookup
                    cls._DATABASE_TO_STANDARD[variant.lower()] = standard
        return cls._DATABASE_TO_STANDARD

    @classmethod
    def to_standard(cls, name: str) -> str:
        """
        Convert database sector/industry name to standard canonical name.

        Args:
            name: Database sector/industry name (any case)

        Returns:
            Standard canonical name. Returns input as-is if not found.

        Examples:
            >>> SectorIndustryMapper.to_standard("Information Technology")
            'Technology'
            >>> SectorIndustryMapper.to_standard("Health Care")
            'Healthcare'
            >>> SectorIndustryMapper.to_standard("Unknown Sector")
            'Unknown Sector'
        """
        if not name:
            return "Unknown"

        # Build reverse mapping if not already built
        reverse_map = cls._build_reverse_mapping()

        # Try exact match first
        if name in reverse_map:
            return reverse_map[name]

        # Try case-insensitive lookup
        name_lower = name.lower()
        if name_lower in reverse_map:
            return reverse_map[name_lower]

        # Return as-is if not found (may be an industry name or new sector)
        return name

    @classmethod
    def to_database_variants(cls, standard_name: str) -> List[str]:
        """
        Get all database variants for a standard sector name.

        Useful for building database queries that need to match any variant.

        Args:
            standard_name: Standard canonical sector name

        Returns:
            List of database variants. Returns [standard_name] if not found.

        Examples:
            >>> SectorIndustryMapper.to_database_variants("Financials")
            ['Financials', 'Finance', 'Financial Services']
            >>> SectorIndustryMapper.to_database_variants("Unknown")
            ['Unknown']
        """
        if not standard_name:
            return []

        # Try direct lookup
        variants = cls.SECTOR_MAPPING.get(standard_name)
        if variants:
            return variants.copy()

        # Return single-item list with input if not found
        return [standard_name]

    @classmethod
    def get_sector_for_industry(cls, industry: str) -> str:
        """
        Get parent sector for an industry.

        Args:
            industry: Industry name

        Returns:
            Parent sector name. Returns "Unknown" if not found.

        Examples:
            >>> SectorIndustryMapper.get_sector_for_industry("Semiconductors")
            'Technology'
            >>> SectorIndustryMapper.get_sector_for_industry("Banks")
            'Financials'
            >>> SectorIndustryMapper.get_sector_for_industry("Unknown Industry")
            'Unknown'
        """
        if not industry:
            return "Unknown"

        # Try direct lookup
        sector = cls.INDUSTRY_TO_SECTOR.get(industry)
        if sector:
            return sector

        # Try case-insensitive lookup
        industry_lower = industry.lower()
        for ind_name, sec_name in cls.INDUSTRY_TO_SECTOR.items():
            if ind_name.lower() == industry_lower:
                return sec_name

        # Try to normalize industry as if it were a sector
        # (some sources use sector names as industry values)
        normalized = cls.to_standard(industry)
        if normalized in cls.SECTOR_MAPPING:
            return normalized

        return "Unknown"

    @classmethod
    def is_valid_sector(cls, name: str) -> bool:
        """
        Check if a name is a valid standard sector name.

        Args:
            name: Sector name to check

        Returns:
            True if name is a valid standard sector
        """
        if not name:
            return False
        return name in cls.SECTOR_MAPPING

    @classmethod
    def get_all_sectors(cls) -> List[str]:
        """
        Get list of all valid standard sector names.

        Returns:
            List of sector names in alphabetical order
        """
        return sorted(cls.SECTOR_MAPPING.keys())

    @classmethod
    def get_all_industries(cls) -> List[str]:
        """
        Get list of all industries with sector mappings.

        Returns:
            List of industry names in alphabetical order
        """
        return sorted(cls.INDUSTRY_TO_SECTOR.keys())

    @classmethod
    def normalize_metadata(
        cls, sector: Optional[str] = None, industry: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """
        Normalize sector and industry metadata to standard names.

        Also ensures industry is mapped to its parent sector.

        Args:
            sector: Raw sector name from database
            industry: Raw industry name from database

        Returns:
            Dict with 'sector' and 'industry' keys (normalized)

        Examples:
            >>> SectorIndustryMapper.normalize_metadata("Information Technology", "Software")
            {'sector': 'Technology', 'industry': 'Software'}
            >>> SectorIndustryMapper.normalize_metadata(None, "Banks")
            {'sector': 'Financials', 'industry': 'Banks'}
        """
        result = {"sector": None, "industry": None}

        # Normalize sector
        if sector:
            result["sector"] = cls.to_standard(sector)

        # Normalize industry
        if industry:
            result["industry"] = industry

            # If sector is not provided, infer from industry
            if not result["sector"]:
                result["sector"] = cls.get_sector_for_industry(industry)

        return result

    @classmethod
    def expand_sectors_for_query(cls, sectors: List[str]) -> List[str]:
        """
        Expand sector names to include all database variants for SQL queries.

        Args:
            sectors: List of sector names (can be standard or variant)

        Returns:
            Expanded list with all database variants

        Examples:
            >>> SectorIndustryMapper.expand_sectors_for_query(["Financials", "Technology"])
            ['Financials', 'Finance', 'Financial Services', 'Technology', 'Information Technology']
        """
        expanded = []
        for sector in sectors:
            if not sector:
                continue
            # Normalize first to get standard name
            standard = cls.to_standard(sector)
            # Then expand to all variants
            expanded.extend(cls.to_database_variants(standard))
        return list(set(expanded))  # Remove duplicates


# Convenience functions for backward compatibility
def normalize_sector_name(name: str) -> str:
    """Normalize sector name to standard format (convenience function)."""
    return SectorIndustryMapper.to_standard(name)


def get_sector_variants(standard_name: str) -> List[str]:
    """Get database variants for a standard sector (convenience function)."""
    return SectorIndustryMapper.to_database_variants(standard_name)


def get_sector_for_industry(industry: str) -> str:
    """Get parent sector for an industry (convenience function)."""
    return SectorIndustryMapper.get_sector_for_industry(industry)
