from __future__ import annotations

from pathlib import Path

import pytest

from victor_invest.tools.sec_filing_text import SECFilingTextTool

FIXTURE_ROOT = Path(__file__).parents[3] / "fixtures" / "sec"


@pytest.mark.parametrize(
    ("section_name", "expected_identifier", "included", "excluded"),
    [
        ("mda", "10q_part_i_item_2_mda", "QUARTERLY_MDA_BODY", "PART_ONE_MARKET_RISK"),
        (
            "market_risk",
            "10q_part_i_item_3_market_risk",
            "PART_ONE_MARKET_RISK",
            "PART_TWO_RISK_FACTORS",
        ),
        (
            "risk_factors",
            "10q_part_ii_item_1a_risk_factors",
            "PART_TWO_RISK_FACTORS",
            "PART_TWO_NEXT_ITEM",
        ),
    ],
)
def test_10q_amendment_uses_explicit_part_boundaries(
    section_name: str,
    expected_identifier: str,
    included: str,
    excluded: str,
) -> None:
    filing = (FIXTURE_ROOT / "10q_inline_xbrl_amendment.html").read_bytes()
    tool = SECFilingTextTool()

    extracted = tool._extract_canonical_section_with_provenance(filing, "10-Q/A", section_name, 10_000)

    assert extracted is not None
    identifier, section = extracted
    assert identifier == expected_identifier
    assert included in section.text
    assert excluded not in section.text
    assert included.encode() in filing[section.source_start_byte : section.source_end_byte]


@pytest.mark.parametrize(
    ("section_name", "expected_identifier", "included", "excluded"),
    [
        ("business_overview", "10k_item_1_business", "BUSINESS_BODY", "INCORPORATED_RISK_BODY"),
        (
            "risk_factors",
            "10k_item_1a_risk_factors",
            "INCORPORATED_RISK_BODY",
            "ITEM_ONE_B_BODY",
        ),
        ("mda", "10k_item_7_mda", "ANNUAL_MDA_BODY", "ANNUAL_MARKET_RISK_BODY"),
        (
            "market_risk",
            "10k_item_7a_market_risk",
            "ANNUAL_MARKET_RISK_BODY",
            "FINANCIAL_STATEMENTS_BODY",
        ),
    ],
)
def test_10k_noncalendar_sections_have_canonical_identifiers(
    section_name: str,
    expected_identifier: str,
    included: str,
    excluded: str,
) -> None:
    filing = (FIXTURE_ROOT / "10k_noncalendar_incorporation.html").read_bytes()
    tool = SECFilingTextTool()

    extracted = tool._extract_canonical_section_with_provenance(filing, "10-K", section_name, 10_000)

    assert extracted is not None
    identifier, section = extracted
    assert identifier == expected_identifier
    assert included in section.text
    assert excluded not in section.text
    assert included.encode() in filing[section.source_start_byte : section.source_end_byte]


@pytest.mark.parametrize("section_name", ["mda", "market_risk", "risk_factors"])
def test_absent_canonical_section_fails_closed(section_name: str) -> None:
    filing = (FIXTURE_ROOT / "10q_absent_canonical_items.html").read_bytes()

    assert SECFilingTextTool()._extract_canonical_section_with_provenance(filing, "10-Q", section_name, 10_000) is None


def test_market_risk_is_a_public_action() -> None:
    schema = SECFilingTextTool().get_schema()

    assert "get_market_risk" in schema["properties"]["action"]["enum"]
