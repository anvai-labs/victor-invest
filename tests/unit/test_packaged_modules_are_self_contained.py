"""Packaged code must not import trees the wheel does not ship.

`pyproject.toml` ships `investigator*` and `victor_invest*` only. Anything under
`utils/`, `data/`, `patterns/`, `scripts/`, `core/`, `admin/` or `api/` exists in
the repo but not in an install, so a packaged module importing one raises
ImportError for anyone who pip-installed rather than cloned.

Verified empirically before this test was written: building the wheel and
importing all 400 packaged modules with the repo root off ``sys.path`` produced
three such failures, plus ``investigator.__main__`` reaching for a root-level
``cli_orchestrator``.

Deferred imports -- inside a function, or wrapped in try/except -- are a
different and milder problem: they do not break import, they silently disable a
feature. One was observable during that run:

    utils.industry_classifier not available - company classification limited

Those are deliberately not failed here, because fixing them is a larger piece of
work; this test guards the hard breakage only, and counts the soft cases so the
number cannot quietly grow.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGED_ROOTS = [REPO_ROOT / "src" / "investigator", REPO_ROOT / "victor_invest"]
UNPACKAGED_TREES = {"utils", "data", "patterns", "scripts", "core", "admin", "api", "cli_orchestrator"}

# Deferred (function-local or try//except-guarded) imports of unpackaged trees.
# These degrade features in an install rather than breaking import. Ratchet only:
# the number may fall, never rise.
KNOWN_DEFERRED_BUDGET = 45


def _module_level_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Top-level imports only -- the ones that run when the module is imported."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module.split(".")[0]))
    return found


def _all_imports(tree: ast.Module) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module.split(".")[0]))
    return found


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in PACKAGED_ROOTS:
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_no_packaged_module_imports_an_unpackaged_tree_at_import_time():
    """The hard failure: an install cannot even import the module."""
    offenders = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - would fail the lint gate first
            continue
        for lineno, top in _module_level_imports(tree):
            if top in UNPACKAGED_TREES:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} imports {top!r}")

    assert not offenders, (
        "packaged modules import trees the wheel does not ship, so `pip install` "
        "produces modules that cannot be imported:\n  " + "\n  ".join(sorted(offenders))
    )


def test_deferred_imports_of_unpackaged_trees_do_not_grow():
    """The soft failure: an install imports fine but silently loses a feature."""
    deferred = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover
            continue
        module_level = set(_module_level_imports(tree))
        for lineno, top in _all_imports(tree):
            if top in UNPACKAGED_TREES and (lineno, top) not in module_level:
                deferred.append(f"{path.relative_to(REPO_ROOT)}:{lineno} -> {top}")

    assert len(deferred) <= KNOWN_DEFERRED_BUDGET, (
        f"deferred imports of unpackaged trees rose to {len(deferred)} "
        f"(budget {KNOWN_DEFERRED_BUDGET}). Each one silently disables a feature "
        f"in an installed wheel:\n  " + "\n  ".join(sorted(deferred))
    )


@pytest.mark.parametrize(
    "module",
    [
        "investigator.sec",
        "investigator.infrastructure.sec.quarterly_processor",
        "investigator.infrastructure.cache.sec_cache_analyzer",
        "investigator.infrastructure.credential_sanitizer",
    ],
)
def test_previously_unimportable_modules_import(module: str):
    """Regression pins for the four modules that could not be imported.

    The first three reached into `data/` or `utils/`. The fourth annotated a
    parameter as ``callable | None`` -- the builtin, not typing.Callable -- which
    raises TypeError while the class body executes, so a credential-scanning
    module was unusable everywhere, not just in a wheel.
    """
    __import__(module)
