# Development Guide

**Setup, testing, and contribution workflow**

---

## 🛠️ Development Setup

```bash
# 1. Clone and install
git clone https://github.com/vjsingh1984/victor-invest.git
cd victor-invest
pip install -e ".[dev]"

# 2. Setup git hooks
./scripts/setup-git-hooks.sh

# 3. Start services
pg_ctl start                    # PostgreSQL
ollama serve                    # LLM server

# 4. Verify installation
pytest tests/ -v -m unit
```

---

## 🧪 Testing

### Test Structure

```
tests/
├── unit/                   # Fast, isolated tests
│   ├── victor_invest/      # Framework tests
│   └── domain/             # Domain service tests
├── integration/            # Service integration tests
├── db/                     # Database tests
└── lint/                   # Code quality checks
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Unit only (fast)
pytest tests/ -v -m unit

# Skip slow tests
pytest tests/ -v -m "not slow"

# With coverage
pytest --cov=src/investigator --cov=victor_invest tests/
```

### Markers

- `unit` - Fast, isolated tests
- `integration` - Service integration
- `slow` - Takes > 10 seconds
- `db` - Requires database
- `llm` - Requires LLM service

---

## 📝 Code Quality

```bash
# Format code
make format
# or
ruff format .

# Check linting
make lint
# or
ruff check .

# Type checking
make type-check
# or
mypy victor_invest/

# All quality checks
make ci
```

### Pre-commit Hooks

Automatically runs on `git commit`:
- Ruff format (black + isort)
- Ruff lint
- Mypy type checks

---

## 🏗️ Adding Features

### 1. Add New Handler

```python
# victor_invest/handlers.py

@handler_decorator("my_analysis", vertical="investment")
@dataclass
class MyAnalysisHandler(BaseHandler):
    async def execute(self, node, context, tool_registry) -> Tuple[Any, int]:
        symbol = context.get("symbol")
        tool = MyTool()
        result = await tool.execute({}, symbol=symbol)
        return {"data": result}, 1
```

### 2. Add New Tool

```python
# victor_invest/tools/my_tool.py

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        try:
            # Call domain service
            return ToolResult.create_success(data)
        except Exception as e:
            return ToolResult.create_failure(str(e))
```

### 3. Add YAML Workflow

```yaml
# victor_invest/workflows/my_analysis.yaml

name: my_analysis
description: My custom analysis workflow

entry_point: fetch_data
nodes:
  fetch_data:
    handler: fetch_market_data
    next: analyze_data

  analyze_data:
    handler: my_analysis
    next: display_results

  display_results:
    handler: display_results
```

---

## 🔄 Workflow

### Development Loop

```
┌─────────────┐
│  Make       │
│  Changes    │
└──────┬──────┘
       ↓
┌─────────────┐
│  Test       │
│  pytest -v  │
└──────┬──────┘
       ↓
┌─────────────┐
│  Format     │
│  make format│
└──────┬──────┘
       ↓
┌─────────────┐
│  Commit     │
│  git commit │
└──────┬──────┘
       ↓
┌─────────────┐
│  Push       │
│  git push   │
└─────────────┘
```

---

## 🐛 Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Add Breakpoints

```python
import pdb; pdb.set_trace()
```

### Inspect State

```python
# In victor_invest/cli.py
import json
print(json.dumps(result.__dict__, indent=2))
```

---

## 📦 Release Process

```bash
# 1. Update version
# Edit version in setup.py or pyproject.toml

# 2. Run tests
pytest tests/ -v
make ci

# 3. Tag release
git tag -a v1.x.x

# 4. Push tags
git push origin main --tags

# 5. Build package
python -m build

# 6. Upload to PyPI (optional)
twine upload dist/*
```

---

## 🤝 Contributing

### Pull Request Process

1. Fork repository
2. Create feature branch
3. Make changes
4. Add tests
5. Run `make ci`
6. Submit PR

### Code Review Checklist

- [ ] Tests added/updated
- [ ] All tests passing
- [ ] Code formatted (`make format`)
- [ ] Linting clean (`make lint`)
- [ ] Type checks pass (`make type-check`)
- [ ] Documentation updated
- [ ] CLAUDE.md updated (if needed)

---

## 🔗 Resources

- [Architecture](../developer/architecture.md) - System design
- [API Reference](../api/api-reference.md) - API docs
- [Troubleshooting](../user/troubleshooting.md) - Common issues

---

## 📞 Getting Help

- **Issues**: https://github.com/vjsingh1984/victor-invest/issues
- **Discussions**: https://github.com/vjsingh1984/victor-invest/discussions
- **CLAUDE.md**: In repo root (dev guidelines)
