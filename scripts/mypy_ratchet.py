#!/usr/bin/env python3
"""Ratchet mypy errors downward instead of gating on zero.

The pre-commit hook ran ``mypy`` as an absolute gate. With ~1,150 pre-existing
errors it failed on every commit regardless of what changed, so the only way to
commit was ``--no-verify`` -- which disables the ruff checks too. A gate nobody
can satisfy is a gate nobody runs.

This compares per-file error counts against a recorded baseline. A file may not
get worse; the total may only fall. Improvements are reported so the baseline can
be tightened.

Per-file counts rather than a single total, because a total lets a regression in
one file hide behind a cleanup in another. Counts rather than exact messages,
because line numbers churn on every edit and a baseline nobody can regenerate
cheaply becomes a baseline nobody maintains.

The baseline is CI's numbers, and CI is authoritative. mypy's results depend on
which third-party packages and stubs are importable, so a developer machine with
extra packages installed will disagree with CI on some files -- when this baseline
was first generated locally it differed on 21 of 211 files in both directions.
A local run is therefore a useful signal, not a verdict; a green local ratchet and
a red CI ratchet means trust CI.

For the same reason, do not commit a locally generated `--update`: it will encode
your environment and break CI for everyone. Take the counts CI prints instead.

Usage:
    python scripts/mypy_ratchet.py --check              # whole tree
    python scripts/mypy_ratchet.py --check a.py b.py    # only these files
    python scripts/mypy_ratchet.py --update             # regenerate (run in CI's env)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / ".mypy-baseline.json"
MYPY_TARGETS = ["src/investigator", "victor_invest"]
MYPY_FLAGS = ["--explicit-package-bases", "--follow-imports=silent"]

# "path/to/file.py:123: error: message  [code]" -- notes are not errors.
_ERROR_LINE = re.compile(r"^(?P<path>[^:]+\.py):\d+:(?:\d+:)? error: ")


def parse_error_counts(mypy_output: str) -> dict[str, int]:
    """Count error lines per file.

    Only ``error:`` lines count. ``note:`` lines are explanatory continuations of
    a preceding error and would otherwise double-count it.
    """
    counts: dict[str, int] = {}
    for line in mypy_output.splitlines():
        match = _ERROR_LINE.match(line)
        if match:
            path = match.group("path")
            counts[path] = counts.get(path, 0) + 1
    return counts


def compare(
    current: dict[str, int],
    baseline: dict[str, int],
    scope: set[str] | None = None,
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    """Compare current counts to baseline.

    Args:
        scope: When set, only these paths are judged. Used for the staged-files
            run, where mypy reports errors from the whole import closure and the
            commit should not be blamed for files it did not touch.

    Returns:
        ``(regressions, improvements)``, each mapping path to ``(baseline, current)``.
    """
    regressions: dict[str, tuple[int, int]] = {}
    improvements: dict[str, tuple[int, int]] = {}

    paths = set(current) | set(baseline)
    if scope is not None:
        paths &= scope

    for path in sorted(paths):
        now = current.get(path, 0)
        before = baseline.get(path, 0)
        if now > before:
            regressions[path] = (before, now)
        elif now < before:
            improvements[path] = (before, now)
    return regressions, improvements


def run_mypy(paths: list[str]) -> str:
    """Run mypy and return its combined output (non-zero exit is expected)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mypy", *MYPY_FLAGS, *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        # mypy exits non-zero whenever it finds errors, which is the normal case
        # here -- the ratchet judges the counts, not the exit status.
        check=False,
    )
    return result.stdout + result.stderr


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    data = json.loads(BASELINE_PATH.read_text())
    files = data.get("files", {})
    return {str(k): int(v) for k, v in files.items()}


def save_baseline(counts: dict[str, int]) -> None:
    payload = {
        "_comment": (
            "Per-file mypy error counts. A file may not exceed its entry; the total may "
            "only fall. Regenerate with: python scripts/mypy_ratchet.py --update"
        ),
        "total": sum(counts.values()),
        "files": dict(sorted(counts.items())),
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if any file regressed")
    parser.add_argument("--update", action="store_true", help="regenerate the baseline")
    parser.add_argument("paths", nargs="*", help="limit the check to these files")
    args = parser.parse_args()

    if args.update:
        counts = parse_error_counts(run_mypy(MYPY_TARGETS))
        save_baseline(counts)
        print(f"Baseline updated: {sum(counts.values())} errors across {len(counts)} files.")
        return 0

    if not args.check:
        parser.error("one of --check or --update is required")

    baseline = load_baseline()
    if not baseline:
        print("No baseline found. Run: python scripts/mypy_ratchet.py --update", file=sys.stderr)
        return 1

    if args.paths:
        scope = {str(Path(p).as_posix()) for p in args.paths}
        output = run_mypy(list(args.paths))
    else:
        scope = None
        output = run_mypy(MYPY_TARGETS)

    current = parse_error_counts(output)
    regressions, improvements = compare(current, baseline, scope)

    if improvements:
        total_gain = sum(before - now for before, now in improvements.values())
        print(f"{len(improvements)} file(s) improved, {total_gain} fewer error(s).")
        for path, (before, now) in sorted(improvements.items()):
            print(f"  {path}: {before} -> {now}")
        print("Lock it in with: python scripts/mypy_ratchet.py --update")

    if regressions:
        total_loss = sum(now - before for before, now in regressions.values())
        print(f"\nmypy regressed: {total_loss} new error(s) in {len(regressions)} file(s).", file=sys.stderr)
        for path, (before, now) in sorted(regressions.items()):
            print(f"  {path}: {before} -> {now}", file=sys.stderr)
        print(
            "\nFix them, or if the increase is intended run "
            "'python scripts/mypy_ratchet.py --update' and say why in the commit.",
            file=sys.stderr,
        )
        return 1

    if not improvements:
        print(f"mypy holding at {sum(current.values())} error(s); no regression.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
