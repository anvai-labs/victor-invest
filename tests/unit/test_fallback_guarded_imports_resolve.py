"""An import behind a degrading fallback must resolve -- module *and* symbol.

Defects found *behind* one of these handlers, never *by* one:

    YAML pipeline        "falling back to StateGraph"        every analysis
    industry_classifier  "company classification limited"    every install
    delisting service    "terminal exits disabled"           silently
    valuation.shared.*   {"success": False} at debug level   PB and EV/EBITDA
    get_sec_bulk_dao     "Falling back to JSON API"          7 months

The shape is always the same: a `try` acquires a collaborator, an `except`
substitutes None or an alternative, and the only evidence is one log line. A
failing import and a genuinely-optional dependency look identical in the source;
the difference is only visible by resolving the name.

Two gaps in the first version of this check, both found the hard way:

* It resolved modules but never the *symbols* imported from them, so
  `from dao.sec_bulk_dao import get_sec_bulk_dao` looked healthy while that
  factory had never been written. The SEC bulk-table fast path was dead for seven
  months behind exactly that.
* It skipped repo-local trees (`dao`, `utils`, `patterns`, ...) entirely. Those
  are first-party code that simply is not packaged; excluding them exempted the
  code most likely to rot.

So symbols are now checked by parsing the target module -- no execution, since
importing for a test would run arbitrary module-level code.
"""

from __future__ import annotations

import ast
import importlib.util
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGED_ROOTS = [REPO_ROOT / "src" / "investigator", REPO_ROOT / "victor_invest"]

# Namespaces that are ours: packaged, or repo-local but still our own code.
FIRST_PARTY = ("investigator", "victor_invest")
REPO_LOCAL = ("dao", "utils", "data", "patterns", "scripts", "core", "sec_fundamental")

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

# Symbols we accept as unverifiable: re-exported through a star import or defined
# dynamically, so a source parse cannot see them.
SYMBOL_CHECK_SKIP: set[str] = set()


def _is_degrading(handler: ast.ExceptHandler) -> bool:
    """A handler that swallows and continues, rather than stopping.

    `sys.exit(...)` counts as stopping even though it is a call rather than a
    `raise`: a CLI command that prints an error and exits non-zero has reported
    the failure, which is the opposite of degrading silently. Treating those as
    degradations produced false positives on two backtest subcommands.
    """
    if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
        return False
    for n in ast.walk(handler):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in {"exit", "_exit", "abort"}:
                return False
    if handler.type is None:
        return True
    node = handler.type
    names = [getattr(e, "id", "") for e in node.elts] if isinstance(node, ast.Tuple) else [getattr(node, "id", "")]
    return any(n in {"Exception", "BaseException", "ImportError", "ModuleNotFoundError"} for n in names)


def _guarded_imports() -> list[tuple[str, tuple[str, ...], str, int]]:
    """(module, imported_names, file, lineno) for imports inside a degrading try."""
    found: list[tuple[str, tuple[str, ...], str, int]] = []
    for root in PACKAGED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            rel = str(path.relative_to(REPO_ROOT))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try) or not any(_is_degrading(h) for h in node.handlers):
                    continue
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.ImportFrom) and sub.level == 0 and sub.module:
                            names = tuple(a.name for a in sub.names if a.name != "*")
                            found.append((sub.module, names, rel, sub.lineno))
                        elif isinstance(sub, ast.Import):
                            for alias in sub.names:
                                found.append((alias.name, (), rel, sub.lineno))
    return found


@lru_cache(maxsize=None)
def _repo_local_path(module: str) -> Path | None:
    """Resolve a repo-local module to a file, by path rather than by import.

    find_spec is unreliable here: `scripts/` has no __init__.py, so any real
    `scripts` package elsewhere on sys.path wins the name -- on this machine it
    resolves into an unrelated repository. Resolving against REPO_ROOT keeps the
    check deterministic and immune to whatever else is installed.
    """
    parts = module.split(".")
    base = REPO_ROOT.joinpath(*parts)
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=None)
def _module_source(module: str) -> str | None:
    """Source of *module*, or None if it cannot be located."""
    if module.split(".")[0] in REPO_LOCAL:
        path = _repo_local_path(module)
        return path.read_text() if path else None
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return None
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return None
    try:
        return Path(spec.origin).read_text()
    except OSError:  # pragma: no cover
        return None


@lru_cache(maxsize=None)
def _defines(module: str, symbol: str) -> bool:
    """Whether *module* defines or re-exports *symbol*, by parsing its source.

    Parsed rather than imported: importing a module to test it would execute
    arbitrary top-level code, which is not something a lint-style check should do.
    A star import anywhere means we cannot tell, so we accept.
    """
    src = _module_source(module)
    if src is None:
        return False
    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.name == symbol:
            return True
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == symbol:
                    return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == symbol:
            return True
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    return True  # cannot resolve through a star import
                if (alias.asname or alias.name.split(".")[0]) == symbol:
                    return True
    return False


def _resolves(module: str) -> bool:
    if module.split(".")[0] in REPO_LOCAL:
        return _repo_local_path(module) is not None
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return False


def test_first_party_guarded_modules_resolve():
    """A guarded import of our own code must point at code that exists."""
    dead = []
    for module, _names, file, lineno in _guarded_imports():
        top = module.split(".")[0]
        if top not in FIRST_PARTY and top not in REPO_LOCAL:
            continue
        if not _resolves(module):
            dead.append(f"{file}:{lineno} guards `{module}`, which does not exist")

    assert not dead, (
        "these fallbacks are permanently active, so the feature behind each one "
        "never runs and says so only in a log line:\n  " + "\n  ".join(sorted(set(dead)))
    )


def test_first_party_guarded_symbols_exist():
    """The module resolving is not enough; the imported name must exist too.

    `from dao.sec_bulk_dao import get_sec_bulk_dao` passed the module check for
    seven months. The module was real; the factory was never written.
    """
    missing = []
    for module, names, file, lineno in _guarded_imports():
        top = module.split(".")[0]
        if top not in FIRST_PARTY and top not in REPO_LOCAL:
            continue
        if not _resolves(module):
            continue  # reported by the module test above
        for name in names:
            if name in SYMBOL_CHECK_SKIP:
                continue
            if not _defines(module, name):
                missing.append(f"{file}:{lineno} imports `{name}` from `{module}`, which does not define it")

    assert not missing, (
        "the module exists but the imported name does not, so the fallback is "
        "permanently active:\n  " + "\n  ".join(sorted(set(missing)))
    )


def test_third_party_optional_dependencies_are_declared_choices():
    """Every optional third-party dependency is listed, not discovered at runtime.

    The point is not that these must be installed -- it is that shipping without
    one should be a recorded decision rather than something a user finds out when
    a feature quietly does nothing, or worse, computes different numbers.
    """
    undeclared = []
    for module, _names, file, lineno in _guarded_imports():
        top = module.split(".")[0]
        if top in FIRST_PARTY or top in REPO_LOCAL or top in OPTIONAL_THIRD_PARTY:
            continue
        if not _resolves(module):
            undeclared.append(f"{file}:{lineno} guards `{module}`, which is neither installed nor declared optional")

    assert not undeclared, (
        "add these to OPTIONAL_THIRD_PARTY if shipping without them is intended, "
        "or to the dependencies if it is not:\n  " + "\n  ".join(sorted(set(undeclared)))
    )
