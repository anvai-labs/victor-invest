# Copyright 2025 Vijaykumar Singh
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for SectorIndustryMapper service.

Tests the centralized sector/industry name mapping service.
"""

import pytest

from investigator.domain.services.sector_name_mapper import (
    SectorIndustryMapper,
    get_sector_for_industry,
    get_sector_variants,
    normalize_sector_name,
)


class TestSectorIndustryMapper:
    """Test suite for SectorIndustryMapper class."""

    def test_to_standard_technology_variants(self):
        """Test standardization of Technology sector variants."""
        assert SectorIndustryMapper.to_standard("Technology") == "Technology"
        assert SectorIndustryMapper.to_standard("Information Technology") == "Technology"
        assert SectorIndustryMapper.to_standard("information technology") == "Technology"
        assert SectorIndustryMapper.to_standard("IT") == "IT"  # Not a mapped variant

    def test_to_standard_financials_variants(self):
        """Test standardization of Financials sector variants."""
        assert SectorIndustryMapper.to_standard("Financials") == "Financials"
        assert SectorIndustryMapper.to_standard("Finance") == "Financials"
        assert SectorIndustryMapper.to_standard("Financial Services") == "Financials"
        assert SectorIndustryMapper.to_standard("financial services") == "Financials"

    def test_to_standard_healthcare_variants(self):
        """Test standardization of Healthcare sector variants."""
        assert SectorIndustryMapper.to_standard("Healthcare") == "Healthcare"
        assert SectorIndustryMapper.to_standard("Health Care") == "Healthcare"
        assert SectorIndustryMapper.to_standard("health care") == "Healthcare"

    def test_to_standard_consumer_variants(self):
        """Test standardization of Consumer sector variants."""
        assert (
            SectorIndustryMapper.to_standard("Consumer Discretionary")
            == "Consumer Discretionary"
        )
        assert SectorIndustryMapper.to_standard("Consumer Cyclical") == "Consumer Discretionary"
        assert SectorIndustryMapper.to_standard("Consumer Staples") == "Consumer Staples"
        assert SectorIndustryMapper.to_standard("Consumer Defensive") == "Consumer Staples"

    def test_to_standard_communication_services(self):
        """Test standardization of Communication Services variants."""
        assert (
            SectorIndustryMapper.to_standard("Communication Services")
            == "Communication Services"
        )
        assert SectorIndustryMapper.to_standard("Telecommunications") == "Communication Services"

    def test_to_standard_materials_variants(self):
        """Test standardization of Materials sector variants."""
        assert SectorIndustryMapper.to_standard("Materials") == "Materials"
        assert SectorIndustryMapper.to_standard("Basic Materials") == "Materials"

    def test_to_standard_empty_and_none(self):
        """Test handling of empty and None inputs."""
        assert SectorIndustryMapper.to_standard("") == "Unknown"
        assert SectorIndustryMapper.to_standard(None) == "Unknown"

    def test_to_standard_unknown_sector(self):
        """Test handling of unknown sector names."""
        assert SectorIndustryMapper.to_standard("Unknown Sector") == "Unknown Sector"
        assert SectorIndustryMapper.to_standard("New Sector") == "New Sector"

    def test_to_database_variants_financials(self):
        """Test getting database variants for Financials."""
        variants = SectorIndustryMapper.to_database_variants("Financials")
        assert set(variants) == {"Financials", "Finance", "Financial Services"}

    def test_to_database_variants_technology(self):
        """Test getting database variants for Technology."""
        variants = SectorIndustryMapper.to_database_variants("Technology")
        assert set(variants) == {"Technology", "Information Technology"}

    def test_to_database_variants_unknown(self):
        """Test getting database variants for unknown sector."""
        variants = SectorIndustryMapper.to_database_variants("Unknown")
        assert variants == ["Unknown"]

    def test_to_database_variants_empty(self):
        """Test getting database variants for empty input."""
        assert SectorIndustryMapper.to_database_variants("") == []

    def test_get_sector_for_industry_technology(self):
        """Test getting parent sector for technology industries."""
        assert SectorIndustryMapper.get_sector_for_industry("Semiconductors") == "Technology"
        assert SectorIndustryMapper.get_sector_for_industry("Software") == "Technology"
        assert (
            SectorIndustryMapper.get_sector_for_industry("Information Technology Services")
            == "Technology"
        )

    def test_get_sector_for_industry_financials(self):
        """Test getting parent sector for financial industries."""
        assert SectorIndustryMapper.get_sector_for_industry("Banks") == "Financials"
        assert (
            SectorIndustryMapper.get_sector_for_industry("Banks - Regional") == "Financials"
        )
        assert SectorIndustryMapper.get_sector_for_industry("Asset Management") == "Financials"
        assert SectorIndustryMapper.get_sector_for_industry("Insurance") == "Financials"

    def test_get_sector_for_industry_healthcare(self):
        """Test getting parent sector for healthcare industries."""
        assert SectorIndustryMapper.get_sector_for_industry("Biotechnology") == "Healthcare"
        assert SectorIndustryMapper.get_sector_for_industry("Medical Devices") == "Healthcare"
        assert SectorIndustryMapper.get_sector_for_industry("Pharmaceuticals") == "Healthcare"

    def test_get_sector_for_industry_consumer(self):
        """Test getting parent sector for consumer industries."""
        assert (
            SectorIndustryMapper.get_sector_for_industry("Internet Retail")
            == "Consumer Discretionary"
        )
        assert SectorIndustryMapper.get_sector_for_industry("Restaurants") == "Consumer Discretionary"
        assert SectorIndustryMapper.get_sector_for_industry("Packaged Foods") == "Consumer Staples"

    def test_get_sector_for_industry_empty_and_none(self):
        """Test handling of empty and None inputs for industry."""
        assert SectorIndustryMapper.get_sector_for_industry("") == "Unknown"
        assert SectorIndustryMapper.get_sector_for_industry(None) == "Unknown"

    def test_get_sector_for_industry_unknown(self):
        """Test handling of unknown industry names."""
        assert (
            SectorIndustryMapper.get_sector_for_industry("Unknown Industry") == "Unknown"
        )

    def test_is_valid_sector(self):
        """Test validation of sector names."""
        assert SectorIndustryMapper.is_valid_sector("Technology") is True
        assert SectorIndustryMapper.is_valid_sector("Financials") is True
        assert SectorIndustryMapper.is_valid_sector("Unknown Sector") is False
        assert SectorIndustryMapper.is_valid_sector("") is False
        assert SectorIndustryMapper.is_valid_sector(None) is False

    def test_get_all_sectors(self):
        """Test getting list of all sectors."""
        sectors = SectorIndustryMapper.get_all_sectors()
        assert len(sectors) == 11  # 11 GICS sectors
        assert "Technology" in sectors
        assert "Financials" in sectors
        assert "Healthcare" in sectors
        # Should be sorted
        assert sectors == sorted(sectors)

    def test_get_all_industries(self):
        """Test getting list of all industries."""
        industries = SectorIndustryMapper.get_all_industries()
        assert len(industries) > 50  # Should have many industries
        assert "Semiconductors" in industries
        assert "Banks" in industries
        assert "Biotechnology" in industries
        # Should be sorted
        assert industries == sorted(industries)

    def test_normalize_metadata_sector_only(self):
        """Test normalizing metadata with sector only."""
        result = SectorIndustryMapper.normalize_metadata(sector="Information Technology")
        assert result["sector"] == "Technology"
        assert result["industry"] is None

    def test_normalize_metadata_industry_only(self):
        """Test normalizing metadata with industry only."""
        result = SectorIndustryMapper.normalize_metadata(industry="Semiconductors")
        assert result["sector"] == "Technology"  # Inferred from industry
        assert result["industry"] == "Semiconductors"

    def test_normalize_metadata_both(self):
        """Test normalizing metadata with both sector and industry."""
        result = SectorIndustryMapper.normalize_metadata(
            sector="Information Technology", industry="Software"
        )
        assert result["sector"] == "Technology"
        assert result["industry"] == "Software"

    def test_normalize_metadata_none(self):
        """Test normalizing metadata with None values."""
        result = SectorIndustryMapper.normalize_metadata()
        assert result["sector"] is None
        assert result["industry"] is None

    def test_expand_sectors_for_query_single(self):
        """Test expanding single sector for query."""
        result = SectorIndustryMapper.expand_sectors_for_query(["Financials"])
        assert set(result) == {"Financials", "Finance", "Financial Services"}

    def test_expand_sectors_for_query_multiple(self):
        """Test expanding multiple sectors for query."""
        result = SectorIndustryMapper.expand_sectors_for_query(
            ["Financials", "Technology"]
        )
        assert "Financials" in result
        assert "Finance" in result
        assert "Financial Services" in result
        assert "Technology" in result
        assert "Information Technology" in result
        # No duplicates
        assert len(result) == len(set(result))

    def test_expand_sectors_for_query_variants(self):
        """Test expanding sectors that use variant names."""
        result = SectorIndustryMapper.expand_sectors_for_query(
            ["Financial Services", "Information Technology"]
        )
        # Should still normalize and expand
        assert "Financials" in result
        assert "Finance" in result
        assert "Financial Services" in result
        assert "Technology" in result
        assert "Information Technology" in result

    def test_expand_sectors_for_query_empty(self):
        """Test expanding empty sector list."""
        result = SectorIndustryMapper.expand_sectors_for_query([])
        assert result == []

    def test_case_insensitive_industry_lookup(self):
        """Test case-insensitive industry lookup."""
        assert SectorIndustryMapper.get_sector_for_industry("semiconductors") == "Technology"
        assert SectorIndustryMapper.get_sector_for_industry("BANKS") == "Financials"


class TestConvenienceFunctions:
    """Test suite for convenience functions."""

    def test_normalize_sector_name(self):
        """Test normalize_sector_name convenience function."""
        assert normalize_sector_name("Information Technology") == "Technology"
        assert normalize_sector_name("Health Care") == "Healthcare"

    def test_get_sector_variants(self):
        """Test get_sector_variants convenience function."""
        variants = get_sector_variants("Financials")
        assert set(variants) == {"Financials", "Finance", "Financial Services"}

    def test_get_sector_for_industry_convenience(self):
        """Test get_sector_for_industry convenience function."""
        assert get_sector_for_industry("Semiconductors") == "Technology"
        assert get_sector_for_industry("Banks") == "Financials"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_industry_that_is_sector_name(self):
        """Test industry name that matches a sector name."""
        # Some sources use sector names as industry values
        result = SectorIndustryMapper.get_sector_for_industry("Technology")
        assert result == "Technology"  # Should recognize as sector

    def test_mixed_case_normalization(self):
        """Test normalization with mixed case."""
        # The mapper normalizes "Information Technology" to "Technology"
        assert SectorIndustryMapper.to_standard("iNfOrMaTiOn TeChNoLoGy") == "Technology"

    def test_whitespace_handling(self):
        """Test handling of whitespace in names."""
        # Note: Current implementation doesn't strip whitespace
        # This test documents current behavior
        result = SectorIndustryMapper.to_standard(" Technology ")
        assert result == " Technology "  # Whitespace preserved

    def test_synthetic_industry_not_in_mapping(self):
        """Test handling of industries not in the mapping."""
        result = SectorIndustryMapper.get_sector_for_industry("Synthetic New Industry")
        assert result == "Unknown"

    def test_real_estate_variants(self):
        """Test Real Estate sector variants."""
        assert SectorIndustryMapper.to_standard("Real Estate") == "Real Estate"
        assert SectorIndustryMapper.to_standard("REITs") == "Real Estate"

    def test_utilities_variants(self):
        """Test Utilities sector variants."""
        assert SectorIndustryMapper.to_standard("Utilities") == "Utilities"
        # "utility" lowercase is not in the mapping, so returns as-is
        assert SectorIndustryMapper.to_standard("utility") == "utility"

    def test_industrials_variants(self):
        """Test Industrials sector variants."""
        assert SectorIndustryMapper.to_standard("Industrials") == "Industrials"
        assert SectorIndustryMapper.to_standard("Industrial") == "Industrials"

    def test_energy_variants(self):
        """Test Energy sector (has no variants)."""
        assert SectorIndustryMapper.to_standard("Energy") == "Energy"
        variants = SectorIndustryMapper.to_database_variants("Energy")
        assert variants == ["Energy"]

    def test_industry_to_sector_oil_gas(self):
        """Test Oil & Gas industry mapping."""
        assert SectorIndustryMapper.get_sector_for_industry("Oil & Gas") == "Energy"
        assert SectorIndustryMapper.get_sector_for_industry("Oil & Gas E&P") == "Energy"

    def test_industry_to_sector_aerospace_defense(self):
        """Test Aerospace & Defense industry mapping."""
        assert SectorIndustryMapper.get_sector_for_industry("Aerospace & Defense") == "Industrials"
        assert SectorIndustryMapper.get_sector_for_industry("Defense") == "Industrials"
        assert SectorIndustryMapper.get_sector_for_industry("Defense Contractors") == "Industrials"
