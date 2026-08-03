from pathlib import Path


def test_no_generated_victor_state_under_importable_package_dirs():
    generated = []
    for root in (Path("victor_invest"), Path("src")):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if ".victor" in path.parts:
                generated.append(str(path))
            elif path.suffix in {".db", ".sqlite", ".sqlite3"}:
                generated.append(str(path))
            elif path.name.endswith((".db-wal", ".db-shm")):
                generated.append(str(path))
            elif path.name == "index.lock":
                generated.append(str(path))

    assert not generated, f"Generated runtime state must stay out of package dirs: {sorted(generated)}"


def test_gitignore_excludes_generated_victor_state():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert ".victor/" in gitignore
    assert "*.db" in gitignore
    assert "*.sqlite" in gitignore
