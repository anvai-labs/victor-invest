import logging
from types import SimpleNamespace

from investigator.domain.agents.fundamental.agent import FundamentalAnalysisAgent


class _Loader:
    def __init__(self, record=None, error=None):
        self._record = record
        self._error = error

    def get(self, _sector):
        if self._error:
            raise self._error
        return self._record


def _make_agent(loader):
    agent = SimpleNamespace()
    agent.logger = logging.getLogger(
        "investigator.domain.agents.fundamental.test_sector_lookup"
    )
    agent._sector_multiples_loader = loader
    agent.config = SimpleNamespace(valuation={"sector_multiples": {}})
    return agent


def test_lookup_sector_multiple_debug_logs_not_warning_for_normal_lookup(caplog):
    agent = _make_agent(_Loader(record=SimpleNamespace(pe=25.0)))

    with caplog.at_level(
        logging.DEBUG,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(
            agent, "Technology", "pe"
        )

    assert value == 25.0
    # Should get value from loader (priority 2), not from shared SectorMultiples
    debug_messages = [
        record.message for record in caplog.records if record.levelno == logging.DEBUG
    ]
    assert any("Returning value from loader" in message for message in debug_messages)


def test_lookup_sector_multiple_warns_when_loader_raises(caplog):
    """Test that when loader raises, shared SectorMultiples provides fallback.

    With the new shared modules, even if the loader fails, the shared SectorMultiples
    module provides a fallback value from config.yaml defaults.
    """
    agent = _make_agent(_Loader(error=RuntimeError("loader failed")))

    with caplog.at_level(
        logging.DEBUG,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(
            agent, "Technology", "pe"
        )

    # Shared SectorMultiples provides a fallback (default 15.0 for pe)
    assert value is not None and value > 0
    # Should log that it's using shared SectorMultiples as fallback
    debug_messages = [
        record.message for record in caplog.records if record.levelno == logging.DEBUG
    ]
    assert any(
        "Returning value from shared SectorMultiples" in message
        for message in debug_messages
    )
