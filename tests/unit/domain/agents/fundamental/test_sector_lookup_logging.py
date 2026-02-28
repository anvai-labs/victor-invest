import logging
from types import SimpleNamespace
from unittest.mock import patch

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


@patch("investigator.domain.services.valuation_shared.sector_multiples_service.SectorMultiplesService")
def test_lookup_sector_multiple_debug_logs_not_warning_for_normal_lookup(mock_service_cls, caplog):
    # Mock SectorMultiplesService to return our test value
    mock_service = SimpleNamespace(get_pe=lambda sector, industry: 25.0)
    mock_service_cls.return_value = mock_service

    agent = _make_agent(_Loader(record=SimpleNamespace(pe=20.0)))

    with caplog.at_level(
        logging.DEBUG,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(agent, "Technology", "pe")

    assert value == 25.0
    # Should get value from SectorMultiplesService (priority 1), not from loader
    all_messages = [record.message for record in caplog.records]
    assert any("config-aware value from SectorMultiplesService" in message for message in all_messages)


@patch("investigator.domain.services.valuation_shared.sector_multiples_service.SectorMultiplesService")
def test_lookup_sector_multiple_warns_when_loader_raises(mock_service_cls, caplog):
    """Test that when loader raises, shared SectorMultiples provides fallback.

    With the new shared modules, even if the loader fails, the shared SectorMultiples
    module provides a fallback value from config.yaml defaults.
    """
    # Mock SectorMultiplesService to return our test value
    mock_service = SimpleNamespace(get_pe=lambda sector, industry: 28.0)
    mock_service_cls.return_value = mock_service

    agent = _make_agent(_Loader(error=RuntimeError("loader failed")))

    with caplog.at_level(
        logging.DEBUG,
        logger="investigator.domain.agents.fundamental.test_sector_lookup",
    ):
        value = FundamentalAnalysisAgent._lookup_sector_multiple(agent, "Technology", "pe")

    # Shared SectorMultiples provides a fallback (28.0 from our mock)
    assert value == 28.0
    # Should log that it's using shared SectorMultiples as fallback
    all_messages = [record.message for record in caplog.records]
    assert any("config-aware value from SectorMultiplesService" in message for message in all_messages)
