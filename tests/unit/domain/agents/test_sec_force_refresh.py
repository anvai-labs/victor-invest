from types import SimpleNamespace

from investigator.domain.agents import sec as sec_module
from investigator.domain.agents.sec import SECAnalysisAgent


def _build_agent() -> SECAnalysisAgent:
    agent = SECAnalysisAgent.__new__(SECAnalysisAgent)
    agent.cache = None
    return agent


def _cfg(force_refresh=False, symbols=None):
    return SimpleNamespace(
        cache_control=SimpleNamespace(
            force_refresh=force_refresh,
            force_refresh_symbols=symbols,
        )
    )


def test_resolve_force_refresh_honors_task_context(monkeypatch):
    agent = _build_agent()
    monkeypatch.setattr(sec_module, "get_config", lambda: _cfg(False, None))

    task = SimpleNamespace(context={"force_refresh": True})

    assert agent._resolve_force_refresh("STX", task) is True


def test_resolve_force_refresh_honors_cache_manager_override(monkeypatch):
    agent = _build_agent()
    agent.cache = SimpleNamespace(
        _force_refresh_override=True,
        _force_refresh_symbols_override=["STX"],
    )
    monkeypatch.setattr(sec_module, "get_config", lambda: _cfg(False, None))

    task = SimpleNamespace(context={})

    assert agent._resolve_force_refresh("STX", task) is True
    assert agent._resolve_force_refresh("AAPL", task) is False


def test_resolve_force_refresh_honors_global_config_symbols(monkeypatch):
    agent = _build_agent()
    monkeypatch.setattr(sec_module, "get_config", lambda: _cfg(True, ["STX", "MSFT"]))

    task = SimpleNamespace(context={})

    assert agent._resolve_force_refresh("STX", task) is True
    assert agent._resolve_force_refresh("AAPL", task) is False


def test_is_weak_guidance_payload_flags_zero_growth_only_signal():
    payload = {
        "source": "sec_filing_regex",
        "confidence_score": 0.15,
        "revenue_growth_guidance": 0.0,
    }

    assert SECAnalysisAgent._is_weak_guidance_payload(payload) is True


def test_is_weak_guidance_payload_accepts_range_signal():
    payload = {
        "source": "sec_filing_regex",
        "confidence_score": 0.4,
        "revenue_guidance": {"low": 10_000_000_000.0, "high": 11_000_000_000.0},
    }

    assert SECAnalysisAgent._is_weak_guidance_payload(payload) is False
