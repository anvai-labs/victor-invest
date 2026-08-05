"""Every declared dependency must carry an upper bound.

Without one, ``pip`` resolves whatever is newest at install time, so a major
release lands in CI with no review and no commit. That is not hypothetical here:
the Code Quality gate broke when an unpinned ``ruff>=0.4.0`` floated to 0.16.1 and
its widened default rule set produced 10775 findings.

Auditing the runtime set afterwards showed the same drift had already happened
repeatedly and silently -- eleven packages were running majors ahead of their
declared floor, including pyarrow (declared >=13, resolved 25), cryptography
(>=41, resolved 50), websockets (>=12, resolved 17) and pandas (>=2, resolved 3).

An upper bound does not freeze anything: minor and patch releases, including
security fixes, still resolve freely. It makes crossing a major an explicit edit.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _declared() -> dict[str, list[str]]:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    groups = {"[project.dependencies]": list(data["project"]["dependencies"])}
    for extra, items in data["project"].get("optional-dependencies", {}).items():
        groups[f"[optional-dependencies.{extra}]"] = list(items)
    return groups


def _unbounded(specs: list[str]) -> list[str]:
    out = []
    for spec in specs:
        req = Requirement(spec)
        ops = {s.operator for s in req.specifier}
        # `==` and `~=` are already bounded above; `<`/`<=` are explicit caps.
        if not ops & {"<", "<=", "==", "~="}:
            out.append(spec)
    return out


def test_runtime_dependencies_are_bounded():
    """A major release must not be able to land without a commit saying so."""
    specs = _declared()["[project.dependencies]"]
    unbounded = _unbounded(specs)
    assert not unbounded, (
        f"{len(unbounded)} runtime dependencies have no upper bound, so pip will install "
        f"the next major silently: {unbounded}"
    )


def test_declared_dependencies_parse():
    """A malformed specifier fails at install time, which is far too late."""
    for group, specs in _declared().items():
        for spec in specs:
            try:
                Requirement(spec)
            except Exception as exc:  # noqa: BLE001 - surfaced with context below
                raise AssertionError(f"{group}: {spec!r} is not a valid requirement: {exc}") from exc


def test_lint_toolchain_stays_bounded():
    """These gate CI, so drift here breaks the build rather than the product."""
    dev = _declared().get("[optional-dependencies.dev]", [])
    gating = {"ruff", "mypy", "flake8", "isort"}
    seen = {Requirement(s).name.lower(): s for s in dev}
    for tool in sorted(gating):
        assert tool in seen, f"{tool} must be declared in the dev extra"
        assert not _unbounded([seen[tool]]), f"{tool} must keep an upper bound: {seen[tool]!r}"
