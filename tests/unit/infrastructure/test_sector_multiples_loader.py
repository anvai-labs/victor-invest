from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from investigator.infrastructure.data.sector_multiples_loader import (
    SectorMultiplesLoader,
)


def _write_multiples_file(path, tech_age_days: int, util_age_days: int) -> None:
    payload = {
        "_metadata": {"source": "unit-test"},
        "Technology": {
            "pe": 25.0,
            "ev_ebitda": 18.0,
            "ps": 6.0,
            "pb": 5.0,
            "sample_size": 50,
            "last_updated": (
                datetime.now(timezone.utc) - timedelta(days=tech_age_days)
            ).isoformat(),
        },
        "Utilities": {
            "pe": 15.0,
            "ev_ebitda": 10.0,
            "ps": 2.0,
            "pb": 1.5,
            "sample_size": 25,
            "last_updated": (
                datetime.now(timezone.utc) - timedelta(days=util_age_days)
            ).isoformat(),
        },
    }
    path.write_text(json.dumps(payload))


def test_get_validates_only_requested_sector(tmp_path, caplog):
    reference = tmp_path / "sector_multiples.json"
    _write_multiples_file(reference, tech_age_days=400, util_age_days=400)

    loader = SectorMultiplesLoader(reference_path=reference, freshness_days=7)

    with caplog.at_level(
        logging.INFO, logger="investigator.infrastructure.data.sector_multiples_loader"
    ):
        loader.load()
        loader.get("Technology")

    messages = [record.message for record in caplog.records]
    assert any(
        "Sector multiples for Technology are stale" in message for message in messages
    )
    assert not any(
        "Sector multiples for Utilities are stale" in message for message in messages
    )


def test_get_stale_recent_logs_info_not_warning(tmp_path, caplog):
    reference = tmp_path / "sector_multiples.json"
    _write_multiples_file(reference, tech_age_days=331, util_age_days=30)

    loader = SectorMultiplesLoader(reference_path=reference, freshness_days=7)

    with caplog.at_level(
        logging.INFO, logger="investigator.infrastructure.data.sector_multiples_loader"
    ):
        loader.get("Technology")

    stale_logs = [
        record
        for record in caplog.records
        if "Sector multiples for Technology are stale" in record.message
    ]
    assert len(stale_logs) == 1
    assert stale_logs[0].levelno == logging.INFO


def test_get_stale_severe_logs_warning(tmp_path, caplog):
    reference = tmp_path / "sector_multiples.json"
    _write_multiples_file(reference, tech_age_days=500, util_age_days=30)

    loader = SectorMultiplesLoader(reference_path=reference, freshness_days=7)

    with caplog.at_level(
        logging.WARNING,
        logger="investigator.infrastructure.data.sector_multiples_loader",
    ):
        loader.get("Technology")
        loader.get("Technology")  # Should not duplicate warnings after first validation

    stale_warnings = [
        record
        for record in caplog.records
        if "Sector multiples for Technology are stale" in record.message
    ]
    assert len(stale_warnings) == 1
    assert stale_warnings[0].levelno == logging.WARNING
