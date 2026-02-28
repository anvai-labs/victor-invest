import logging
import math
from datetime import datetime
from types import SimpleNamespace

from investigator.infrastructure.sec.data_processor import SECDataProcessor


def _processor():
    # Bypass __init__ to avoid eager DB connections during unit tests
    return SECDataProcessor.__new__(SECDataProcessor)


def test_enrich_debt_fields_derives_short_and_net_debt():
    processor = _processor()
    filing = {
        "data": {
            "long_term_debt": 7_000_000_000.0,
            "total_debt": 7_800_000_000.0,
            "short_term_debt": None,
            "cash_and_equivalents": 950_000_000.0,
        }
    }

    processor._enrich_debt_fields(filing)

    derived_short = filing["data"]["short_term_debt"]
    net_debt = filing["data"]["net_debt"]

    assert math.isclose(derived_short, 800_000_000.0)
    assert math.isclose(net_debt, 6_850_000_000.0)


def test_enrich_debt_fields_backfills_total_from_components():
    processor = _processor()
    filing = {
        "data": {
            "long_term_debt": 5_100_000_000.0,
            "short_term_debt": 600_000_000.0,
            "total_debt": None,
        }
    }

    processor._enrich_debt_fields(filing)

    assert math.isclose(filing["data"]["total_debt"], 5_700_000_000.0)


def test_enrich_share_counts_uses_diluted_weighted_average():
    processor = _processor()
    filing = {
        "data": {
            "shares_outstanding": None,
            "weighted_average_diluted_shares_outstanding": 1_234_000_000.0,
        }
    }

    processor._enrich_share_counts(filing)

    assert filing["data"]["shares_outstanding"] == 1_234_000_000.0


def test_enrich_book_value_per_share_uses_equity_and_shares():
    processor = _processor()
    filing = {
        "data": {
            "stockholders_equity": 212_000_000.0,
            "shares_outstanding": 822_500_000.0,
            "book_value_per_share": None,
        }
    }

    processor._enrich_book_value_per_share(filing)

    equity = filing["data"]["stockholders_equity"]
    shares = filing["data"]["shares_outstanding"]
    expected = equity / shares

    assert math.isclose(filing["data"]["book_value_per_share"], expected, rel_tol=1e-9)


def test_enrich_debt_fields_uses_financial_deposit_heuristics():
    processor = _processor()
    filing = {
        "data": {
            "financial_total_deposits": 900_000_000.0,
            "financial_fhlb_borrowings": 125_000_000.0,
            "long_term_debt": 275_000_000.0,
            "total_debt": None,
            "short_term_debt": None,
        }
    }

    processor._enrich_debt_fields(filing)

    assert math.isclose(filing["data"]["total_debt"], 1_300_000_000.0)


def test_enrich_debt_fields_sets_short_term_from_repo_components():
    processor = _processor()
    filing = {
        "data": {
            "financial_repo_borrowings": 200_000_000.0,
            "financial_other_short_term_borrowings": 50_000_000.0,
            "total_debt": None,
            "long_term_debt": None,
            "short_term_debt": None,
        }
    }

    processor._enrich_debt_fields(filing)

    assert math.isclose(filing["data"]["short_term_debt"], 250_000_000.0)
    assert math.isclose(filing["data"]["total_debt"], 250_000_000.0)


def test_normalize_ytd_missing_prev_period_logs_boundary_info_for_earliest_year(caplog):
    processor = _processor()
    data = {"total_revenue": 1_000_000.0}
    all_filings = [
        {
            "fiscal_year": 2011,
            "fiscal_period": "Q2",
            "data": {"total_revenue": 1_000_000.0},
        },
        {
            "fiscal_year": 2011,
            "fiscal_period": "Q3",
            "data": {"total_revenue": 2_000_000.0},
        },
        {
            "fiscal_year": 2012,
            "fiscal_period": "Q1",
            "data": {"total_revenue": 1_100_000.0},
        },
    ]

    with caplog.at_level(logging.INFO, logger="investigator.infrastructure.sec.data_processor"):
        processor._normalize_ytd_to_pit(
            data=data,
            income_qtrs=2,
            cashflow_qtrs=1,
            fiscal_period="Q2",
            fiscal_year=2011,
            all_filings=all_filings,
            symbol="TEST",
        )

    assert any("[YTD_NORM_BOUNDARY]" in record.message for record in caplog.records)
    assert not any("[YTD_NORM_CRITICAL]" in record.message for record in caplog.records)


def test_normalize_ytd_missing_prev_period_keeps_critical_warning_for_non_boundary_year(
    caplog,
):
    processor = _processor()
    data = {"total_revenue": 1_000_000.0}
    all_filings = [
        {
            "fiscal_year": 2023,
            "fiscal_period": "Q3",
            "data": {"total_revenue": 2_000_000.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q2",
            "data": {"total_revenue": 1_000_000.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q3",
            "data": {"total_revenue": 2_000_000.0},
        },
    ]

    with caplog.at_level(logging.WARNING, logger="investigator.infrastructure.sec.data_processor"):
        processor._normalize_ytd_to_pit(
            data=data,
            income_qtrs=2,
            cashflow_qtrs=1,
            fiscal_period="Q2",
            fiscal_year=2024,
            all_filings=all_filings,
            symbol="TEST",
        )

    assert any("[YTD_NORM_CRITICAL]" in record.message for record in caplog.records)


def test_extract_from_json_derives_oci_when_direct_tag_missing():
    class _StubOrchestrator:
        def extract(self, canonical_key, **kwargs):
            if canonical_key == "other_comprehensive_income":
                return SimpleNamespace(success=False, value=None, error="not found")
            if canonical_key == "comprehensive_income":
                return SimpleNamespace(success=True, value=125.0)
            if canonical_key == "net_income":
                return SimpleNamespace(success=True, value=100.0)
            return SimpleNamespace(success=False, value=None, error="unsupported")

    processor = _processor()
    processor.metric_orchestrator = _StubOrchestrator()
    processor.canonical_mapper = SimpleNamespace(
        mappings={
            "other_comprehensive_income": {"unit": "USD"},
            "comprehensive_income": {"unit": "USD"},
        },
        get_tags=lambda *args, **kwargs: [],
    )
    processor.sector = None
    processor.industry = None

    value, source = processor._extract_from_json_for_filing(
        canonical_key="other_comprehensive_income",
        us_gaap={},
        adsh="0000000000-00-000000",
        fiscal_year=2024,
        fiscal_period="Q2",
        period_end="2023-12-29",
    )

    assert value == 25.0
    assert source == "derived:comprehensive_income-net_income"


def test_select_best_entries_invalid_fy_historical_logs_info_not_warning(caplog):
    processor = _processor()
    processor._detect_fiscal_year_end = lambda *_args, **_kwargs: None
    processor._score_period_for_selection = lambda *_args, **_kwargs: 1.0

    historical_year = datetime.now().year - (processor.ADSH_INVALID_FY_WARNING_YEARS + 1)
    period_end = f"{historical_year}-03-31"
    all_entries = [
        {
            "accn": "0000000000-00-000001",
            "start": f"{historical_year - 1}-12-31",
            "end": period_end,
            "fp": "Q3",
            "fy": historical_year + 1,
            "filed": f"{historical_year + 1}-05-01",
        },
        {
            "accn": "0000000000-00-000002",
            "start": f"{historical_year - 1}-12-31",
            "end": period_end,
            "fp": "Q3",
            "fy": historical_year + 2,
            "filed": f"{historical_year + 1}-05-03",
        },
    ]

    with caplog.at_level(logging.INFO, logger="investigator.infrastructure.sec.data_processor"):
        best_entries = processor._select_best_entries_per_period(all_entries, "TEST", {})

    assert len(best_entries) == 1
    matching_records = [r for r in caplog.records if "All entries for period ending" in r.message]
    assert any(r.levelno == logging.INFO for r in matching_records)
    assert not any(r.levelno >= logging.WARNING for r in matching_records)


def test_select_best_entries_invalid_fy_recent_keeps_warning(caplog):
    processor = _processor()
    processor._detect_fiscal_year_end = lambda *_args, **_kwargs: None
    processor._score_period_for_selection = lambda *_args, **_kwargs: 1.0

    recent_year = datetime.now().year - 1
    period_end = f"{recent_year}-03-31"
    all_entries = [
        {
            "accn": "0000000000-00-000003",
            "start": f"{recent_year - 1}-12-31",
            "end": period_end,
            "fp": "Q3",
            "fy": recent_year + 1,
            "filed": f"{recent_year + 1}-05-01",
        },
        {
            "accn": "0000000000-00-000004",
            "start": f"{recent_year - 1}-12-31",
            "end": period_end,
            "fp": "Q3",
            "fy": recent_year + 2,
            "filed": f"{recent_year + 1}-05-03",
        },
    ]

    with caplog.at_level(logging.WARNING, logger="investigator.infrastructure.sec.data_processor"):
        best_entries = processor._select_best_entries_per_period(all_entries, "TEST", {})

    assert len(best_entries) == 1
    assert any(r.levelno == logging.WARNING and "All entries for period ending" in r.message for r in caplog.records)
