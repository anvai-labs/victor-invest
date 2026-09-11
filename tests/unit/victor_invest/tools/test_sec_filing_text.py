from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pytest

from victor_invest.sec_document_store import StoredSecDocument
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


def test_source_offsets_preserve_utf8_entities_and_self_closing_breaks() -> None:
    tool = SECFilingTextTool()
    filing = (
        "<h1>Item 7. Management's Discussion and Analysis</h1>"
        "<p>Café &amp; subscriptions improved.<br/>Liquidity remained strong for the quarter.</p>"
        "<h1>Item 7A. Market Risk</h1>"
    ).encode()

    section = tool._extract_section_with_provenance(filing, tool._mda_patterns_for_form("10-K"), 5_000)

    assert section is not None
    assert "Café & subscriptions improved.\nLiquidity" in section.text
    assert b"Caf\xc3\xa9 &amp; subscriptions" in filing[section.source_start_byte : section.source_end_byte]


def _stored_document(form_type: str, content: str, accession: str) -> StoredSecDocument:
    content_bytes = content.encode()
    return StoredSecDocument.from_mapping(
        {
            "accession_no": accession,
            "content_sha256": hashlib.sha256(content_bytes).hexdigest(),
            "document_kind": "complete_submission" if form_type == "8-K" else "primary",
            "issuer_cik": 320193,
            "issuer_ticker": "AAPL",
            "form_type": form_type,
            "is_amendment": False,
            "filed_at": date(2026, 5, 1),
            "accepted_at": datetime(2026, 5, 1, 12, tzinfo=UTC),
            "available_at": datetime(2026, 5, 1, 12, tzinfo=UTC),
            "report_period_end": date(2026, 3, 28),
            "document_url": f"https://www.sec.gov/Archives/edgar/data/320193/{accession}.txt",
            "content_type": "text/html; charset=utf-8",
            "byte_length": len(content_bytes),
            "content_bytes": content_bytes,
            "retrieved_at": datetime(2026, 5, 1, 13, tzinfo=UTC),
            "last_verified_at": datetime(2026, 5, 1, 14, tzinfo=UTC),
        }
    )


class _FakeDocumentStore:
    def __init__(self) -> None:
        self.quarterly = _stored_document(
            "10-Q",
            """
                <h1>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</h1>
                <p>Quarterly revenue increased because unit demand and pricing improved materially.</p>
                <p>Management expects capital expenditures to remain within the approved annual plan.</p>
                <h1>Item 3. Quantitative and Qualitative Disclosures About Market Risk</h1>
            """,
            "0000320193-26-000001",
        )
        self.current = _stored_document(
            "8-K",
            """
            <h1>Item 2.02 Results of Operations and Financial Condition</h1>
            <p>RESULTS_EVENT. The issuer furnished its quarterly earnings release.</p>
            <p>Management discussed current demand, margin, and liquidity developments.</p>
            <h1>Item 9.01 Financial Statements and Exhibits</h1>
            <p>EXHIBITS_SECTION</p>
            <DOCUMENT>
              <TYPE>EX-99.1
              <TEXT><h1>Earnings Release</h1><p>EXHIBIT_MARKER. Management issued explicit quarterly revenue and margin outlook with supporting operational detail.</p></TEXT>
            </DOCUMENT>
            """,
            "0000320193-26-000002",
        )

    async def get_latest_document(
        self, symbol: str, form_type: str, period: str, as_of: datetime
    ) -> StoredSecDocument | None:
        assert symbol == "AAPL"
        assert form_type == "10-Q"
        assert period == "latest"
        assert as_of.tzinfo is not None
        return self.quarterly

    async def list_recent_documents(
        self, symbol: str, form_type: str, as_of: datetime, *, limit: int
    ) -> list[StoredSecDocument]:
        assert (symbol, form_type, limit) == ("AAPL", "8-K", 1)
        assert as_of.tzinfo is not None
        return [self.current]


@pytest.mark.asyncio
async def test_mda_result_retains_filing_provenance() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._document_store = _FakeDocumentStore()

    result = await tool._get_mda("AAPL", "10-Q", "latest", 5_000)

    assert result.success
    assert result.output["accession_number"] == "0000320193-26-000001"
    assert result.output["period_end"] == "2026-03-28"
    assert result.output["document_kind"] == "primary"
    assert len(result.output["content_sha256"]) == 64
    assert result.output["available_at"] == "2026-05-01T12:00:00+00:00"
    assert "Quarterly revenue increased" in result.output["text"]
    source = tool._document_store.quarterly.content_bytes[
        result.output["source_start_byte"] : result.output["source_end_byte"]
    ]
    assert b"Quarterly revenue increased" in source


@pytest.mark.asyncio
async def test_8k_development_uses_cik_and_stops_at_next_item() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._document_store = _FakeDocumentStore()

    result = await tool._get_developments("AAPL", num_filings=1, max_chars=5_000)

    assert result.success
    assert "RESULTS_EVENT" in result.output["text"]
    assert "EXHIBITS_SECTION" not in result.output["text"]
    assert "EXHIBIT_MARKER" in result.output["text"]
    assert result.output["sources"][0]["accession_number"] == "0000320193-26-000002"
    assert result.output["sources"][0]["sections"] == ["item_2_02", "exhibit_99_1"]
    assert result.output["sources"][0]["document_kind"] == "complete_submission"
    expected_markers = {"item_2_02": b"RESULTS_EVENT", "exhibit_99_1": b"EXHIBIT_MARKER"}
    for evidence in result.output["sources"][0]["evidence"]:
        raw = tool._document_store.current.content_bytes[evidence["source_start_byte"] : evidence["source_end_byte"]]
        assert expected_markers[evidence["section"]] in raw


@pytest.mark.asyncio
async def test_execute_rejects_direct_invocation_outside_schema_bounds() -> None:
    tool = SECFilingTextTool()
    tool._initialized = True
    tool._document_store = _FakeDocumentStore()

    result = await tool.execute(symbol="AAPL", action="get_mda", max_chars=999)

    assert not result.success
    assert "max_chars" in result.error


def test_truncation_marker_stays_inside_character_limit() -> None:
    tool = SECFilingTextTool()

    result = tool._truncate_text("x" * 2_000, 1_000)

    assert len(result) == 1_000
    assert result.endswith("... [truncated]")
