"""The LLM pattern modules must exist exactly once.

They previously existed in three near-identical copies -- `patterns/llm/`,
`src/investigator/llm/` and `src/investigator/infrastructure/llm/`. Nothing
imported `src/investigator/llm/` at all; `patterns/llm/` was an un-modernised
snapshot still imported by packaged code. The copies drifted only cosmetically,
which is precisely what made the duplication easy to miss: each looked
maintained.

The canonical home is `src/investigator/infrastructure/llm/`, matching the
architecture's infrastructure layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

PATTERN_MODULES = [
    "llm_facade.py",
    "llm_interfaces.py",
    "llm_model_config.py",
    "llm_processors.py",
    "llm_strategies.py",
]

CANONICAL_DIR = REPO_ROOT / "src" / "investigator" / "infrastructure" / "llm"


@pytest.mark.parametrize("module", PATTERN_MODULES)
def test_pattern_module_exists_only_at_the_canonical_path(module: str) -> None:
    """Exactly one copy, and it is the infrastructure-layer one."""
    found = [
        p
        for p in REPO_ROOT.rglob(module)
        # Ignore build/venv/cache trees, which legitimately contain installed copies.
        if not any(
            part in {".git", "build", "dist", "node_modules", "__pycache__", ".venv", "site-packages"}
            for part in p.parts
        )
    ]

    assert found == [CANONICAL_DIR / module], (
        f"{module} should exist only at {CANONICAL_DIR.relative_to(REPO_ROOT)}; found "
        f"{[str(p.relative_to(REPO_ROOT)) for p in found]}"
    )


def test_canonical_llm_modules_do_not_import_unpackaged_trees() -> None:
    """The wheel ships `investigator*` only; reaching outside it breaks installs.

    `llm_processors` imported `utils.api_client` and `llm_strategies` imported
    `utils.prompt_manager` -- both mere shims re-exporting the canonical packaged
    modules, so the indirection bought nothing and broke the wheel.
    """
    offenders = []
    for module in PATTERN_MODULES:
        text = (CANONICAL_DIR / module).read_text()
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("from utils.", "import utils.", "from patterns.", "import patterns.")):
                offenders.append(f"{module}:{lineno}: {stripped}")

    assert not offenders, "canonical LLM modules import unpackaged trees:\n" + "\n".join(offenders)
