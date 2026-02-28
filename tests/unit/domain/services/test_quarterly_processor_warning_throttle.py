import copy
import logging

import pytest

from investigator.domain.services import quarterly_processor


@pytest.fixture(autouse=True)
def clear_q4_warning_cache():
    quarterly_processor._q4_warning_log_counts.clear()
    yield
    quarterly_processor._q4_warning_log_counts.clear()


@pytest.fixture
def periods_with_missing_q3_for_legacy_fy():
    # FY 2022 has no matching Q3; only newer Q1-Q3 periods exist.
    return [
        {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "fiscal_period": "Q3",
            "period_end_date": "2025-03-27",
        },
        {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "fiscal_period": "Q2",
            "period_end_date": "2024-12-27",
        },
        {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "fiscal_period": "Q1",
            "period_end_date": "2024-09-27",
        },
        {
            "symbol": "TEST",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "period_end_date": "2022-06-27",
        },
    ]


def test_q4_missing_q3_logs_warning_first_occurrence(
    caplog, periods_with_missing_q3_for_legacy_fy
):
    with caplog.at_level(
        logging.WARNING, logger="investigator.domain.services.quarterly_processor"
    ):
        quarterly_processor.get_rolling_ttm_periods(
            copy.deepcopy(periods_with_missing_q3_for_legacy_fy),
            compute_missing=True,
            num_quarters=4,
        )

    warning_messages = [record.message for record in caplog.records]
    assert any(
        "No Q3 found within 30-150 days for FY 2022 ending 2022-06-27" in message
        for message in warning_messages
    )
    assert any(
        "No Q3 found within 30-180 days, attempting fiscal year match only" in message
        for message in warning_messages
    )
    assert any(
        "No Q3 found for FY 2022 ending 2022-06-27, skipping Q4 computation" in message
        for message in warning_messages
    )


def test_q4_missing_q3_downgrades_duplicate_warnings_to_debug(
    caplog, periods_with_missing_q3_for_legacy_fy
):
    quarterly_processor.get_rolling_ttm_periods(
        copy.deepcopy(periods_with_missing_q3_for_legacy_fy),
        compute_missing=True,
        num_quarters=4,
    )

    caplog.clear()
    with caplog.at_level(
        logging.DEBUG, logger="investigator.domain.services.quarterly_processor"
    ):
        quarterly_processor.get_rolling_ttm_periods(
            copy.deepcopy(periods_with_missing_q3_for_legacy_fy),
            compute_missing=True,
            num_quarters=4,
        )

    duplicate_warning_records = [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and "No Q3 found" in record.message
    ]
    assert not duplicate_warning_records

    duplicate_debug_records = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "suppressed duplicate Q4 warning" in record.message
    ]
    assert duplicate_debug_records
