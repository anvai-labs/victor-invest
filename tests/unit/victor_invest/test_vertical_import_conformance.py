from pathlib import Path


def test_no_package_level_verticals_imports_with_side_effects():
    """Prevent imports that trigger external vertical discovery at import time."""
    violations = []
    for path in Path("victor_invest").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "from victor.core.verticals import " in content:
            violations.append(str(path))

    assert not violations, (
        "Use 'victor.core.verticals.base' imports in victor_invest to avoid "
        f"package-level vertical discovery side effects: {sorted(violations)}"
    )
