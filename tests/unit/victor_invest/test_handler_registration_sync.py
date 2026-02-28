import victor_invest.workflows as workflows


def test_ensure_handlers_registered_is_idempotent(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module
    import victor.workflows.executor as executor_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "executor_register": []}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    # Mock the handler registry to return test handlers
    class _TestHandler:
        pass

    class _FakeRegistry:
        def list_handlers(self, vertical_name=None):
            return {"investment": ["handler1", "handler2"]}

        def get_handler(self, vertical_name, handler_name):
            return _TestHandler()

    def _register_compute_handler(name, handler):
        calls["executor_register"].append((name, handler))

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
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
    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    # Should have called register_compute_handler for each handler found
    assert len(calls["executor_register"]) == 2


def test_ensure_handlers_registered_short_circuits_when_marked_done(monkeypatch):
    monkeypatch.setattr(workflows, "_handlers_registered", True)
    workflows.ensure_handlers_registered()
    assert workflows._handlers_registered is True


def test_ensure_handlers_registered_last_resort_pushes_registry_entries(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module
    import victor.workflows.executor as executor_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "executor_register": []}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    class _TestHandler1:
        pass

    class _TestHandler2:
        pass

    class _FakeRegistry:
        def list_handlers(self, vertical_name=None):
            # Return handlers from different verticals
            return {"investment": ["h1", "h2"], "global": ["h3"]}

        def get_handler(self, vertical_name, handler_name):
            if handler_name == "h1":
                return _TestHandler1()
            elif handler_name == "h2":
                return _TestHandler2()
            return object()

    def _register_compute_handler(name, handler):
        calls["executor_register"].append((name, handler))

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
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
    # Should have registered h1, h2, h3
    assert len(calls["executor_register"]) == 3
    assert [name for name, _ in calls["executor_register"]] == ["h1", "h2", "h3"]


def test_ensure_handlers_registered_warns_when_no_sync_path_available(monkeypatch):
    import victor.framework.handler_registry as handler_registry_module

    import victor_invest.handlers as handlers_module

    calls = {"register_handlers": 0, "warning": 0}

    monkeypatch.setattr(workflows, "_handlers_registered", False)

    def _register_handlers():
        calls["register_handlers"] += 1

    class _RegistryWithoutHandlers:
        def list_handlers(self, vertical_name=None):
            # Return empty dict to simulate no handlers
            return {}

    def _warn(message, *args, **kwargs):
        calls["warning"] += 1
        assert "Handler sync helpers unavailable" in message

    monkeypatch.setattr(handlers_module, "register_handlers", _register_handlers)
    monkeypatch.setattr(
        handler_registry_module,
        "get_handler_registry",
        lambda: _RegistryWithoutHandlers(),
    )
    monkeypatch.setattr(workflows.logger, "warning", _warn)

    workflows.ensure_handlers_registered()

    assert calls["register_handlers"] == 1
    assert calls["warning"] == 1
    assert workflows._handlers_registered is True
