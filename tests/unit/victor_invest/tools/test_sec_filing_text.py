from __future__ import annotations

import pytest

from victor_invest.tools.sec_filing_text import SECFilingTextTool


def test_mda_extraction_prefers_body_over_table_of_contents() -> None:
    tool = SECFilingTextTool()
    filing = """
    <html><body>
      <div>TABLE OF CONTENTS</div>
      <div>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations 42</div>
      <div>Item 7A. Quantitative and Qualitative Disclosures About Market Risk 68</div>
      <h1>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</h1>
      <p>BODY_MARKER. Revenue increased because subscription volume and pricing improved.</p>
      <p>Management also described liquidity, capital expenditure, margin, and demand trends in substantive detail.</p>
      <h1>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</h1>
      <p>NEXT_SECTION_MARKER</p>
    </body></html>
    """

    section = tool._extract_section_by_patterns(
        filing,
        tool._mda_patterns_for_form("10-K"),
        max_chars=10_000,
    )

    assert section is not None
    assert "BODY_MARKER" in section
    assert "NEXT_SECTION_MARKER" not in section
    assert "TABLE OF CONTENTS" not in section


def test_quarterly_mda_uses_part_one_item_two_boundary() -> None:
    tool = SECFilingTextTool()
    filing = """
    <h1>PART I — FINANCIAL INFORMATION</h1>
    <h2>Item 2. Management’s Discussion and Analysis of Financial Condition and Results of Operations</h2>
    <p>QUARTERLY_MDA. Unit volume declined while price and gross margin increased.</p>
    <p>Cash generation funded the current quarter capital expenditure program.</p>
    <h2>Item 3. Quantitative and Qualitative Disclosures About Market Risk</h2>
    <p>MARKET_RISK_SECTION</p>
    """

    section = tool._extract_section_by_patterns(
        filing,
        tool._mda_patterns_for_form("10-Q"),
        max_chars=10_000,
    )

    assert section is not None
    assert "QUARTERLY_MDA" in section
    assert "MARKET_RISK_SECTION" not in section


class _FakeSecClient:
    async def get_filing_by_symbol(self, **_: object) -> dict[str, object]:
        return {
            "text": """
                <h1>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</h1>
                <p>Quarterly revenue increased because unit demand and pricing improved materially.</p>
                <p>Management expects capital expenditures to remain within the approved annual plan.</p>
                <h1>Item 3. Quantitative and Qualitative Disclosures About Market Risk</h1>
            """,
            "accession_number": "0000320193-26-000001",
            "filing_date": "2026-05-01",
            "period_end": "2026-03-28",
            "form_url": "https://www.sec.gov/Archives/edgar/data/320193/1/aapl.htm",
        }

    async def search_filings(self, **_: object) -> list[dict[str, str]]:
        return [
            {
                "cik": "0000320193",
                "accession_number": "0000320193-26-000002",
                "filing_date": "2026-05-02",
            }
        ]

    async def get_filing(self, accession_number: str, cik: str) -> str:
        assert accession_number == "0000320193-26-000002"
        assert cik == "0000320193"
        return """
            <h1>Item 2.02 Results of Operations and Financial Condition</h1>
            <p>RESULTS_EVENT. The issuer furnished its quarterly earnings release.</p>
            <p>Management discussed current demand, margin, and liquidity developments.</p>
            <h1>Item 9.01 Financial Statements and Exhibits</h1>
            <p>EXHIBITS_SECTION</p>
            <DOCUMENT>
              <TYPE>EX-99.1
              <TEXT><h1>Earnings Release</h1><p>EXHIBIT_MARKER. Management issued explicit quarterly revenue and margin outlook with supporting operational detail.</p></TEXT>
            </DOCUMENT>
        """


@pytest.mark.asyncio
async def test_mda_result_retains_filing_provenance() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._sec_client = _FakeSecClient()

    result = await tool._get_mda("AAPL", "10-Q", "latest", 5_000)

    assert result.success
    assert result.output["accession_number"] == "0000320193-26-000001"
    assert result.output["period_end"] == "2026-03-28"
    assert "Quarterly revenue increased" in result.output["text"]


@pytest.mark.asyncio
async def test_8k_development_uses_cik_and_stops_at_next_item() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._sec_client = _FakeSecClient()

    result = await tool._get_developments("AAPL", num_filings=1, max_chars=5_000)

    assert result.success
    assert "RESULTS_EVENT" in result.output["text"]
    assert "EXHIBITS_SECTION" not in result.output["text"]
    assert "EXHIBIT_MARKER" in result.output["text"]
    assert result.output["sources"][0]["accession_number"] == "0000320193-26-000002"
    assert result.output["sources"][0]["sections"] == ["item_2_02", "exhibit_99_1"]


@pytest.mark.asyncio
async def test_execute_rejects_direct_invocation_outside_schema_bounds() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._sec_client = _FakeSecClient()

    result = await tool.execute(symbol="AAPL", action="get_mda", max_chars=999)

    assert not result.success
    assert "max_chars" in result.error


def test_truncation_marker_stays_inside_character_limit() -> None:
    tool = SECFilingTextTool()

    result = tool._truncate_text("x" * 2_000, 1_000)

    assert len(result) == 1_000
    assert result.endswith("... [truncated]")
