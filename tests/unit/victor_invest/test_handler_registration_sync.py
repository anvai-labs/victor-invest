"""Handler registration contract (Victor v0.7.0 canonical compute registry).

Convergence note: handlers register via the ``@handler_decorator`` import
side-effect, which calls ``register_compute_handler`` directly. The legacy
sync-bridge fallbacks (``sync_handlers_with_executor`` / ``registry.sync_with_executor``
/ manual push) were removed, so these tests assert the canonical behavior:
``ensure_handlers_registered`` is idempotent, imports the handlers module once,
and the handlers end up resolvable in the framework compute registry.
"""

import victor_invest.workflows as workflows


def test_ensure_handlers_registered_is_idempotent(monkeypatch):
    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)

    workflows.ensure_handlers_registered()
    workflows.ensure_handlers_registered()

    # Registration runs exactly once despite two calls.
    assert calls["register_handlers"] == 1
    assert workflows._handlers_registered is True


def test_ensure_handlers_registered_short_circuits_when_marked_done(monkeypatch):
    monkeypatch.setattr(workflows, "_handlers_registered", True)
    workflows.ensure_handlers_registered()
    assert workflows._handlers_registered is True


def test_handlers_resolve_in_canonical_compute_registry(monkeypatch):
    """The real contract: handlers land in the framework compute registry."""
    from victor.workflows.compute_registry import get_compute_handler

    monkeypatch.setattr(workflows, "_handlers_registered", False)
    workflows.ensure_handlers_registered()

    # Every handler referenced by the YAML workflows must resolve.
    for name in [
        "fetch_sec_data",
        "fetch_market_data",
        "run_fundamental_analysis",
        "run_technical_analysis",
        "run_synthesis",
        "generate_report",
        "process_backtest_batch",
        "save_rl_predictions",
    ]:
        assert get_compute_handler(name) is not None, f"handler {name!r} not registered"
