"""Guards on this package's use of deprecated ``victor_contracts`` bridge modules.

victor-contracts 0.9.0 classified six bridge modules as Deprecated and scheduled
their removal for 0.10.0. Its own CONTRACT_STABILITY.md justifies that by noting
the modules have "zero consumers in the Victor monorepo" -- a count that does not
see this package, which uses all six.

These tests exist so that fact cannot go quiet again:

* the dependency pin must stay below the removal release, so a routine resolve
  cannot install a victor-contracts that deletes the modules this package imports;
* the set of deprecated bridges in use is pinned, so migration progress is visible
  and new usage cannot be added silently.

Four of the six replacements live in ``victor.*`` -- the host framework this
package deliberately keeps optional (see ``test_pyproject_framework_is_optional``).
Completing the migration therefore needs a decision in both repositories, not a
local edit. That tension is the reason this debt is tracked rather than fixed here.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Deprecated in victor-contracts 0.9.0, removal scheduled for 0.10.0.
# Source of truth: victor_contracts/_deprecation.py :: DEPRECATED_BRIDGE_REPLACEMENTS
DEPRECATED_BRIDGES = {
    "agent_spec_runtime": "victor.agent.specs.models",
    "graph_runtime": "victor.framework.graph",
    "handler_runtime": "victor_contracts.workflow_runtime or victor.framework.handler_registry",
    "subagent_runtime": "victor.agent.subagents.protocols",
    "tool_runtime": "victor.framework.tools",
    "workflow_executor_runtime": "victor_contracts.workflow_runtime",
}

REMOVAL_VERSION = "0.10"

# Bridges this package still imports. Shrink as the migration proceeds; never grow.
BRIDGES_IN_USE = frozenset(DEPRECATED_BRIDGES)


def _source_files() -> list[Path]:
    roots = (_REPO_ROOT / "src", _REPO_ROOT / "victor_invest")
    return [p for root in roots if root.exists() for p in root.rglob("*.py")]


def _bridges_used() -> set[str]:
    used: set[str] = set()
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        for bridge in DEPRECATED_BRIDGES:
            if re.search(rf"\bvictor_contracts\.{bridge}\b", source):
                used.add(bridge)
    return used


def test_contracts_pin_excludes_the_removal_release():
    """The pin must not admit the release that deletes the modules we import."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    pins = [d for d in data["project"]["dependencies"] if d.startswith("victor-contracts")]
    assert pins, "victor-contracts must be declared in [project.dependencies]"
    assert f"<{REMOVAL_VERSION}" in pins[0], (
        f"victor-contracts is pinned as {pins[0]!r}. That range admits "
        f"{REMOVAL_VERSION}.0, which removes the deprecated bridges this package "
        f"still imports ({', '.join(sorted(_bridges_used()))}). Complete the migration "
        f"before widening the pin."
    )


def test_deprecated_bridge_usage_has_not_grown():
    """New code must not reach for a bridge that is already scheduled for deletion."""
    unexpected = _bridges_used() - BRIDGES_IN_USE
    replacements = {bridge: DEPRECATED_BRIDGES[bridge] for bridge in sorted(unexpected)}
    assert not unexpected, (
        f"New use of deprecated victor_contracts bridges: {sorted(unexpected)}. Replacements: {replacements}"
    )


def test_migration_progress_is_recorded():
    """If a bridge has been migrated away, tighten BRIDGES_IN_USE so it stays gone."""
    stale = BRIDGES_IN_USE - _bridges_used()
    assert not stale, (
        f"These bridges are no longer used: {sorted(stale)}. "
        f"Remove them from BRIDGES_IN_USE so the migration cannot regress."
    )
