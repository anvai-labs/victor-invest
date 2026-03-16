from pathlib import Path

ACTIVE_DOCS = [
    Path("README.md"),
    Path("README.adoc"),
    Path("docs/README.md"),
    Path("docs/api/api-reference.md"),
    Path("docs/developer/architecture.md"),
    Path("docs/developer/development.md"),
    Path("docs/operations/runbook.md"),
    Path("docs/user/getting-started.md"),
    Path("docs/user/cli-commands.md"),
    Path("docs/user/ui-dashboard.md"),
]


def test_active_docs_do_not_use_legacy_cli_commands_or_stale_dashboard_paths():
    legacy_patterns = [
        "python3 cli_orchestrator.py",
        "python cli_orchestrator.py",
        "http://localhost:8000/dashboard",
        "| Dashboard | `/dashboard` |",
    ]

    violations = {}
    for doc in ACTIVE_DOCS:
        if not doc.exists():
            continue
        content = doc.read_text(encoding="utf-8")
        found = [pattern for pattern in legacy_patterns if pattern in content]
        if found:
            violations[str(doc)] = found

    assert not violations, f"Legacy CLI command references found in active docs: {violations}"
