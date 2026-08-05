"""No declared dependency may shadow a standard-library module.

`requirements.txt` declared `asyncio>=3.4.3`, which is not the standard library
module but the PyPI package of the same name -- a backport for Python 3.3/3.4
whose own summary reads "Deprecated backport of asyncio; use the stdlib package
instead". Installing it places an obsolete `asyncio` on the path ahead of the
real one.

It went unnoticed because CI installs from pyproject, where it was never listed.
The Dockerfile installs requirements.txt, so container builds were the exposure --
and the package, dormant since 2015, published a 4.0.0 in August 2025, so those
builds would have started pulling a decade-newer artifact under the same name.

This guards the whole class rather than the one instance.
"""

from __future__ import annotations

import sys
from pathlib import Path

from packaging.requirements import Requirement

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Distributions on PyPI that shadow a stdlib module if installed. These are real
# packages, not typos: each is an obsolete backport of something now built in.
STDLIB_SHADOWING_DISTRIBUTIONS = {
    "asyncio",
    "argparse",
    "configparser",
    "dataclasses",
    "enum34",
    "functools32",
    "futures",
    "importlib",
    "pathlib",
    "statistics",
    "typing",
    "unittest2",
}


def _declared_requirement_files() -> list[Path]:
    return sorted(_REPO_ROOT.glob("requirements*.txt"))


def _parsed_name(line: str) -> str | None:
    """The distribution name, or None when the line is not a requirement."""
    try:
        return Requirement(line).name.lower()
    except Exception:  # noqa: BLE001 - malformed lines are another test's concern
        return None


def _requirement_names(path: Path) -> list[str]:
    names = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _parsed_name(line)
        if name:
            names.append(name)
    return names


def test_requirements_files_do_not_shadow_the_standard_library():
    offenders: list[str] = []
    for path in _declared_requirement_files():
        for name in _requirement_names(path):
            if name in STDLIB_SHADOWING_DISTRIBUTIONS:
                offenders.append(f"{path.name}: {name}")
    assert not offenders, (
        f"These declared dependencies shadow standard-library modules and must be removed: "
        f"{offenders}. The stdlib version is already available on the supported Pythons."
    )


def test_the_shadowing_list_names_real_stdlib_modules():
    """A guard listing modules that are not in the stdlib would protect nothing."""
    missing = [
        n for n in ("asyncio", "argparse", "configparser", "pathlib", "typing") if n not in sys.stdlib_module_names
    ]
    assert not missing, f"not stdlib modules on this interpreter: {missing}"
