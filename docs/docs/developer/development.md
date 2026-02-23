# Development

**Development workflow & contribution**

---

## 🛠️ Setup

```bash
# Install
pip install -e ".[dev]"

# Git hooks
./scripts/setup-git-hooks.sh

# Start services
pg_ctl start && ollama serve
```

---

## 🧪 Testing

```bash
# All tests
pytest tests/ -v

# Unit only
pytest tests/ -v -m unit

# Skip slow
pytest tests/ -v -m "not slow"

# With coverage
pytest --cov=src/investigator --cov=victor_invest tests/
```

---

## 📝 Code Quality

```bash
# Format
make format
# or
ruff format .

# Lint
make lint
# or
ruff check .

# Type check
make type-check
# or
mypy victor_invest/
```

---

## 🔄 Development Loop

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Make       │ →  │  Test       │ →  │  Format     │
│  Changes    │    │  pytest -v  │    │  make format│
└─────────────┘    └─────────────┘    └─────────────┘
                                                ↓
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Commit     │ ←  │  Push       │ ←  │  Lint       │
│  git commit │    │  git push   │    │  make lint  │
└─────────────┘    └─────────────┘    └─────────────┘
```

---

## 🔗 Related

- [Architecture](architecture.md) - System design
- [System Diagram](system-diagram.md) - Visual diagrams
