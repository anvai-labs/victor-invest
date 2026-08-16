"""An import behind a degrading fallback must actually resolve.

Three separate defects this session were found *behind* one of these handlers,
never *by* one:

    YAML pipeline        "falling back to StateGraph"        every analysis
    industry_classifier  "company classification limited"    every install
    delisting service    "terminal exits disabled"           silently

The shape is always the same: a `try` acquires a collaborator, an `except`
substitutes None or an alternative, and the only evidence is one log line. A
failing import and a genuinely-optional dependency look identical in the source;
the difference is only visible by resolving the name.

So this resolves them. First-party modules must exist -- if the repo guards an
import of its own code, that code had better be there. Third-party ones are
legitimately optional and are listed explicitly, which keeps the list of things
we have decided to live without visible rather than implicit.

Found by this check when written: `investigator.domain.services.valuation.shared`
does not exist, so the PB and EV/EBITDA models in unified_valuation_executor
could never run and reported failure at debug level.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGED_ROOTS = [REPO_ROOT / "src" / "investigator", REPO_ROOT / "victor_invest"]

# First-party namespaces: a guarded import of these must resolve.
FIRST_PARTY = ("investigator", "victor_invest")

# Third-party imports we have deliberately chosen to treat as optional. Adding an
# entry is a decision to ship without it; leaving one out means CI tells you the
# dependency is missing rather than a log line telling a user at runtime.
OPTIONAL_THIRD_PARTY = {
    "line_profiler",  # profiling aid, only used when profiling
    "jinja2",  # template rendering; prompt manager has a non-template path
    "uvicorn",  # only needed to serve the API
    "json_repair",  # malformed-LLM-JSON repair
    "psutil",
    "matplotlib",
    "seaborn",
    "plotly",
    "yfinance",
    "lxml_html_clean",
    "victor",  # the host runtime; verticals must degrade without it
    "victor_contracts",
}

# Repo-local top-level modules that are neither packaged nor third-party. Guarded
# imports of these are dead unless the module exists at the repo root.
_REPO_LOCAL_HINT = {"dao", "sec_fundamental", "utils", "data", "patterns", "scripts", "core"}


def _is_degrading(handler: ast.ExceptHandler) -> bool:
    """A handler that swallows and continues, rather than re-raising."""
    if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
        return False
    if handler.type is None:
        return True
    node = handler.type
    names = [getattr(e, "id", "") for e in node.elts] if isinstance(node, ast.Tuple) else [getattr(node, "id", "")]
    return any(n in {"Exception", "BaseException", "ImportError", "ModuleNotFoundError"} for n in names)


def _guarded_imports() -> list[tuple[str, str, int]]:
    """(module, file, lineno) for every import inside a degrading try/except."""
    found: list[tuple[str, str, int]] = []
    for root in PACKAGED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                if not any(_is_degrading(h) for h in node.handlers):
                    continue
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.ImportFrom):
                            if sub.level == 0 and sub.module:
                                found.append((sub.module, str(path.relative_to(REPO_ROOT)), sub.lineno))
                        elif isinstance(sub, ast.Import):
                            for alias in sub.names:
                                found.append((alias.name, str(path.relative_to(REPO_ROOT)), sub.lineno))
    return found


def _resolves(module: str) -> bool:
    """Whether the name can be located, without executing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return False


def test_first_party_guarded_imports_resolve():
    """A guarded import of our own code must point at code that exists."""
    dead = []
    for module, file, lineno in _guarded_imports():
        top = module.split(".")[0]
        if top not in FIRST_PARTY:
            continue
        if not _resolves(module):
            dead.append(f"{file}:{lineno} guards `{module}`, which does not exist")

    assert not dead, (
        "these fallbacks are permanently active, so the feature behind each one "
        "never runs and says so only in a log line:\n  " + "\n  ".join(sorted(dead))
    )


def test_third_party_optional_dependencies_are_declared_choices():
    """Every optional third-party dependency is listed, not discovered at runtime.

    The point is not that these must be installed -- it is that shipping without
    one should be a recorded decision rather than something a user finds out
    when a feature quietly does nothing.
    """
    undeclared = []
    for module, file, lineno in _guarded_imports():
        top = module.split(".")[0]
        if top in FIRST_PARTY or top in _REPO_LOCAL_HINT:
            continue
        if top in OPTIONAL_THIRD_PARTY:
            continue
        if not _resolves(module):
            undeclared.append(f"{file}:{lineno} guards `{module}`, which is neither installed nor declared optional")

    assert not undeclared, (
        "add these to OPTIONAL_THIRD_PARTY if shipping without them is intended, "
        "or to the dependencies if it is not:\n  " + "\n  ".join(sorted(undeclared))
    )
