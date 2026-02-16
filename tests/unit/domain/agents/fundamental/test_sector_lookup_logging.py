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
    agent.logger = logging.getLogger("investigator.domain.agents.fundamental.test_sector_lookup")
    agent._sector_multiples_loader = loader
    agent.config = SimpleNamespace(valuation={"sector_multiples": {}})
    return agent


def test_lookup_sector_multiple_debug_logs_not_warning_for_normal_lookup(caplog):
    agent = _make_agent(_Loader(record=SimpleNamespace(pe=25.0)))

    with caplog.at_level(
        logging.DEBUG,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(agent, "Technology", "pe")

    assert value == 25.0
    warning_messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
    assert not any("[SECTOR_LOOKUP_DEBUG]" in message for message in warning_messages)


def test_lookup_sector_multiple_warns_when_loader_raises(caplog):
    agent = _make_agent(_Loader(error=RuntimeError("loader failed")))

    with caplog.at_level(
        logging.WARNING,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(agent, "Technology", "pe")

    assert value is None
    assert any(
        "Sector multiple lookup failed for Technology/pe: loader failed" in record.message
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )
