import victor_invest.workflows as workflows


def test_ensure_handlers_registered_is_idempotent(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "sync_handlers": 0}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    def _sync_handlers_with_executor(*, direction):
        calls["sync_handlers"] += 1
        assert direction == "to_executor"

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
    monkeypatch.setattr(
        handler_registry_module,
        "sync_handlers_with_executor",
        _sync_handlers_with_executor,
    )

    workflows.ensure_handlers_registered()
    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    assert calls["sync_handlers"] == 1


def test_ensure_handlers_registered_short_circuits_when_marked_done(monkeypatch):
    monkeypatch.setattr(workflows, "_handlers_registered", True)
    workflows.ensure_handlers_registered()
    assert workflows._handlers_registered is True


def test_ensure_handlers_registered_falls_back_to_registry_sync_method(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "registry_sync": 0}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    class _FakeRegistry:
        def sync_with_executor(self, *, direction):
            calls["registry_sync"] += 1
            assert direction == "to_executor"

    def _sync_handlers_with_executor(*, direction):
        raise RuntimeError("sync helper unavailable")

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
    monkeypatch.setattr(
        handler_registry_module,
        "sync_handlers_with_executor",
        _sync_handlers_with_executor,
    )
    monkeypatch.setattr(
        handler_registry_module,
        "get_handler_registry",
        lambda: _FakeRegistry(),
    )

    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    assert calls["registry_sync"] == 1


def test_ensure_handlers_registered_last_resort_pushes_registry_entries(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module
    import victor.workflows.executor as executor_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "executor_register": []}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    def _sync_handlers_with_executor(*, direction):
        raise RuntimeError("sync helper unavailable")

    class _Entry:
        def __init__(self, name, handler):
            self.name = name
            self.handler = handler

    class _FakeRegistry:
        def list_entries(self):
            return [_Entry("h1", object()), _Entry("h2", object())]

    def _register_compute_handler(name, handler):
        calls["executor_register"].append((name, handler))

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
    monkeypatch.setattr(
        handler_registry_module,
        "sync_handlers_with_executor",
        _sync_handlers_with_executor,
    )
    monkeypatch.setattr(
        handler_registry_module,
        "get_handler_registry",
        lambda: _FakeRegistry(),
    )
    monkeypatch.setattr(
        executor_module,
        "register_compute_handler",
        _register_compute_handler,
    )

    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    assert [name for name, _ in calls["executor_register"]] == ["h1", "h2"]


def test_ensure_handlers_registered_warns_when_no_sync_path_available(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "warning": 0}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    def _sync_handlers_with_executor(*, direction):
        raise RuntimeError("sync helper unavailable")

    class _RegistryWithoutSync:
        pass

    def _warn(message, *args, **kwargs):
        calls["warning"] += 1
        assert "Handler sync helpers unavailable" in message

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
    monkeypatch.setattr(
        handler_registry_module,
        "sync_handlers_with_executor",
        _sync_handlers_with_executor,
    )
    monkeypatch.setattr(
        handler_registry_module,
        "get_handler_registry",
        lambda: _RegistryWithoutSync(),
    )
    monkeypatch.setattr(workflows.logger, "warning", _warn)

    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    assert calls["warning"] == 1
    assert workflows._handlers_registered is True
