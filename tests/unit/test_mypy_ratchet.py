"""The ratchet must block regressions without blocking commits.

The pre-commit hook previously ran mypy as an absolute gate. With ~1,150
pre-existing errors it failed on every commit regardless of the change, so the
only way to commit was ``--no-verify`` -- which skips the ruff checks too. Every
commit in this session carried that flag. A gate nobody can satisfy is a gate
nobody runs.

These cover the comparison logic directly, so they do not need mypy to run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("mypy_ratchet", REPO_ROOT / "scripts" / "mypy_ratchet.py")
assert _SPEC and _SPEC.loader
ratchet = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ratchet)


SAMPLE = """\
src/a.py:10: error: Incompatible types  [assignment]
src/a.py:12: error: Missing return  [return]
src/a.py:12: note: See https://mypy.readthedocs.io/
src/b.py:3: error: Name "x" is not defined  [name-defined]
Found 3 errors in 2 files (checked 5 source files)
"""


def test_notes_are_not_counted_as_errors():
    """A note is a continuation of the error above it; counting it double-counts."""
    counts = ratchet.parse_error_counts(SAMPLE)
    assert counts == {"src/a.py": 2, "src/b.py": 1}


def test_column_qualified_error_lines_are_counted():
    """mypy emits `file:line:col: error:` when column output is on."""
    counts = ratchet.parse_error_counts("src/c.py:7:15: error: Bad thing  [misc]\n")
    assert counts == {"src/c.py": 1}


def test_a_file_getting_worse_is_a_regression():
    regressions, improvements = ratchet.compare({"src/a.py": 5}, {"src/a.py": 3})
    assert regressions == {"src/a.py": (3, 5)}
    assert improvements == {}


def test_a_file_getting_better_is_an_improvement_not_a_failure():
    regressions, improvements = ratchet.compare({"src/a.py": 1}, {"src/a.py": 3})
    assert regressions == {}
    assert improvements == {"src/a.py": (3, 1)}


def test_a_brand_new_file_with_errors_regresses():
    """Absent from the baseline means a budget of zero."""
    regressions, _ = ratchet.compare({"src/new.py": 2}, {})
    assert regressions == {"src/new.py": (0, 2)}


def test_a_cleaned_file_is_an_improvement():
    _, improvements = ratchet.compare({}, {"src/gone.py": 4})
    assert improvements == {"src/gone.py": (4, 0)}


def test_a_total_that_holds_still_catches_a_per_file_regression():
    """The reason this is per-file: a total would net these two out to zero."""
    current = {"src/a.py": 5, "src/b.py": 1}
    baseline = {"src/a.py": 3, "src/b.py": 3}
    regressions, improvements = ratchet.compare(current, baseline)

    assert sum(current.values()) == sum(baseline.values()), "premise: the totals match"
    assert regressions == {"src/a.py": (3, 5)}, "a regression hid behind an unrelated cleanup"
    assert improvements == {"src/b.py": (3, 1)}


def test_scope_limits_blame_to_the_files_under_test():
    """mypy reports the whole import closure; a commit owns only what it touched."""
    current = {"src/touched.py": 2, "src/untouched.py": 99}
    baseline = {"src/touched.py": 2, "src/untouched.py": 3}

    regressions, _ = ratchet.compare(current, baseline, scope={"src/touched.py"})
    assert regressions == {}, "the commit was blamed for a file it did not touch"

    regressions, _ = ratchet.compare(current, baseline)
    assert "src/untouched.py" in regressions, "without scope, everything is judged"


@pytest.mark.parametrize("path", [".mypy-baseline.json"])
def test_baseline_is_committed_and_wellformed(path: str):
    """A ratchet with no baseline silently degrades to no check at all."""
    import json

    baseline_file = REPO_ROOT / path
    assert baseline_file.exists(), "the ratchet baseline must be committed"

    data = json.loads(baseline_file.read_text())
    assert data["total"] == sum(data["files"].values()), "recorded total disagrees with the per-file counts"
    assert all(isinstance(v, int) and v > 0 for v in data["files"].values())
