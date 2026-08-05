"""This package must not import deprecated ``victor_contracts`` bridge modules.

victor-contracts 0.9.0 classified six bridge modules Deprecated, with removal in
0.10.0. Removing them is a deliberate narrowing of the contract layer: the bridges
were lazy re-exports of host runtime symbols, which blurred the line between the
definition layer and the framework. Every other vertical in the Victor tree
already imports the host directly and uses none of them.

The correct posture is therefore to follow, not to pin against it. These tests
keep the package there:

* no source file may import any of the six bridges;
* the victor-contracts pin must stay open across the removal release, so this
  package cannot quietly re-acquire the coupling by holding an old contracts.

Three bridged symbols -- ``BaseHandler``, ``handler_decorator`` and
``sync_handlers_with_executor`` -- have no implementation anywhere in victor-ai;
the bridge defined them inline as shims. The first two are owned locally now, in
``victor_invest/compat/handlers.py``. ``sync_handlers_with_executor`` was dropped
outright: it was never importable, because its lazy map pointed at a module that
does not export it, so the call site was dead code behind a broad ``except``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Source of truth: victor_contracts/_deprecation.py :: DEPRECATED_BRIDGE_REPLACEMENTS
DEPRECATED_BRIDGES = {
    "agent_spec_runtime": "victor.agent.specs.models",
    "graph_runtime": "victor.framework.graph",
    "handler_runtime": "victor.framework.handler_registry (+ local shims)",
    "subagent_runtime": "victor.agent.subagents.protocols",
    "tool_runtime": "victor.framework.tools",
    "workflow_executor_runtime": "victor_contracts.workflow_runtime",
}


def _source_files() -> list[Path]:
    roots = (_REPO_ROOT / "src", _REPO_ROOT / "victor_invest")
    return [p for root in roots if root.exists() for p in root.rglob("*.py")]


def _bridge_usage() -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        for bridge in DEPRECATED_BRIDGES:
            if re.search(rf"\bvictor_contracts\.{bridge}\b", source):
                usage.setdefault(bridge, []).append(str(path.relative_to(_REPO_ROOT)))
    return usage


def test_no_deprecated_contracts_bridges_are_imported():
    """The migration is complete and must stay complete."""
    usage = _bridge_usage()
    detail = "; ".join(
        f"{bridge} in {', '.join(files)} -> use {DEPRECATED_BRIDGES[bridge]}" for bridge, files in sorted(usage.items())
    )
    assert not usage, f"Deprecated victor_contracts bridges are back: {detail}"


def test_contracts_pin_is_open_across_the_removal_release():
    """Nothing here depends on the removed modules, so the pin must not hold them back."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    pins = [d for d in data["project"]["dependencies"] if d.startswith("victor-contracts")]
    assert pins, "victor-contracts must be declared in [project.dependencies]"
    assert "<0.10" not in pins[0], (
        f"victor-contracts is pinned as {pins[0]!r}. That bound existed only to avoid the "
        f"0.10.0 bridge removal; the migration is done, so it should no longer be capped there."
    )


def test_handler_shims_are_owned_locally():
    """The symbols victor-ai never implemented must live here, not be re-imported."""
    shim = (_REPO_ROOT / "victor_invest" / "compat" / "handlers.py").read_text(encoding="utf-8")
    assert "victor_contracts.handler_runtime" not in shim
    for symbol in ("BaseHandler", "handler_decorator"):
        assert symbol in shim, f"{symbol} must be defined locally now that the bridge is gone"
