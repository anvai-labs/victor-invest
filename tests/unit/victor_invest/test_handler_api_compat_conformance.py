from pathlib import Path


def test_handlers_module_uses_compat_layer_imports():
    handlers_py = Path("victor_invest/handlers.py").read_text(encoding="utf-8")

    assert (
        "from victor_invest.compat.handlers import BaseHandler, handler_decorator"
        in handlers_py
    )
    assert (
        "from victor.framework.handler_registry import handler_decorator"
        not in handlers_py
    )
    assert (
        "from victor.framework.workflows.base_handler import BaseHandler"
        not in handlers_py
    )


def test_no_direct_legacy_handler_api_imports_outside_compat_layer():
    violations = []
    for path in Path("victor_invest").rglob("*.py"):
        rel = str(path)
        if rel.startswith("victor_invest/compat/"):
            continue

        content = path.read_text(encoding="utf-8")
        if "from victor.framework.handler_registry import handler_decorator" in content:
            violations.append(rel)
        if "from victor.framework.workflows.base_handler import BaseHandler" in content:
            violations.append(rel)

    assert not violations, (
        f"Direct legacy handler API imports found: {sorted(set(violations))}"
    )
