import asyncio

import pytest

from victor_invest.compat import handlers as compat_handlers


def _requires_fallback_basehandler():
    return compat_handlers.BaseHandler.__module__ == "victor_invest.compat.handlers"


def _requires_fallback_decorator():
    return (
        compat_handlers.handler_decorator.__module__ == "victor_invest.compat.handlers"
    )


def test_fallback_basehandler_success_path():
    if not _requires_fallback_basehandler():
        pytest.skip(
            "Native Victor BaseHandler is active; fallback-specific test skipped"
        )

    from victor.workflows.executor import ExecutorNodeStatus

    class _Node:
        id = "node-1"
        output_key = "result"

    class _Context:
        def __init__(self):
            self.data = {}

        def set(self, key, value):
            self.data[key] = value

    class _Handler(compat_handlers.BaseHandler):
        async def execute(self, node, context, tool_registry):
            return {"ok": True}, 2

    ctx = _Context()
    result = asyncio.run(_Handler().__call__(_Node(), ctx, None))

    assert result.status == ExecutorNodeStatus.COMPLETED
    assert result.output == {"ok": True}
    assert result.tool_calls_used == 2
    assert ctx.data["result"] == {"ok": True}


def test_fallback_basehandler_failure_path():
    if not _requires_fallback_basehandler():
        pytest.skip(
            "Native Victor BaseHandler is active; fallback-specific test skipped"
        )

    from victor.workflows.executor import ExecutorNodeStatus

    class _Node:
        id = "node-2"
        output_key = "result"

    class _Context:
        def set(self, key, value):
            pass

    class _Handler(compat_handlers.BaseHandler):
        async def execute(self, node, context, tool_registry):
            raise ValueError("boom")

    result = asyncio.run(_Handler().__call__(_Node(), _Context(), None))

    assert result.status == ExecutorNodeStatus.FAILED
    assert "boom" in str(result.error)


def test_fallback_handler_decorator_registers_with_registry_and_executor(monkeypatch):
    if not _requires_fallback_decorator():
        pytest.skip(
            "Native Victor handler_decorator is active; fallback-specific test skipped"
        )

    import victor.framework.handler_registry as handler_registry_module
    import victor.workflows.executor as executor_module

    calls = {
        "registry": [],
        "executor": [],
    }

    def _register_handler(**kwargs):
        calls["registry"].append(dict(kwargs))
        if "replace" in kwargs:
            # Simulate older API variant that doesn't accept `replace`.
            raise TypeError("replace unsupported")

    def _register_compute_handler(name, handler):
        calls["executor"].append((name, handler))

    monkeypatch.setattr(handler_registry_module, "register_handler", _register_handler)
    monkeypatch.setattr(
        executor_module, "register_compute_handler", _register_compute_handler
    )

    @compat_handlers.handler_decorator(
        "unit_test_handler",
        vertical="investment",
        description="compat test",
    )
    class _Handler(compat_handlers.BaseHandler):
        async def execute(self, node, context, tool_registry):
            return {"ok": True}, 0

    # First call includes replace=True (simulated TypeError), second retries without replace.
    assert calls["registry"][0]["name"] == "unit_test_handler"
    assert calls["registry"][0]["vertical"] == "investment"
    assert "replace" in calls["registry"][0]
    assert calls["registry"][1]["name"] == "unit_test_handler"
    assert "replace" not in calls["registry"][1]

    assert len(calls["executor"]) == 1
    assert calls["executor"][0][0] == "unit_test_handler"
    assert isinstance(calls["executor"][0][1], _Handler)
