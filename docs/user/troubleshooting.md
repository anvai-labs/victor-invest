# Troubleshooting

**Quick solutions to common issues**

---

## 🚨 Installation Issues

### ModuleNotFoundError: victor-ai

```bash
# Install victor-ai framework
pip install 'victor-ai>=0.5.0,<0.6.0'
```

### Database Connection Failed

```bash
# Check PostgreSQL status
pg_ctl status

# Start PostgreSQL
pg_ctl start

# Check connection
psql -U postgres -d victor
```

### Ollama Not Responding

```bash
# Start Ollama
ollama serve

# Verify
curl http://localhost:11434/api/tags
```

---

## 📊 Analysis Issues

### Analysis Returns "BUY" at $0

**Cause**: Missing data (revenue=0, book_value=0)

**Fix**:
```bash
# Warm SEC data cache
investigator cache warm --symbols AAPL --process-raw
```

### EV/EBITDA Model Filtered Out

**Cause**: Missing `depreciation_amortization` data

**Fix**: Should be fixed (commit `bd54ab2`)

Verify:
```python
# Check if D&A column exists
import sqlalchemy
from investigator.infrastructure.database.db import DatabaseManager

db = DatabaseManager()
with db.get_session() as session:
    result = session.execute(
        sqlalchemy.text("SELECT COUNT(*) FROM sec_companyfacts_processed WHERE depreciation_amortization IS NOT NULL")
    )
    print(f"Rows with D&A: {result.scalar()}")
```

### Technical Analysis Missing

**Cause**: No market data in database

**Fix**:
```bash
# Fetch market data
investigator market-data fetch --symbols AAPL --days 365
```

---

## 🌐 Web UI Issues

### Cache Not Loading

**Check 1**: Cache files exist
```bash
ls -la artifacts/ui_cache/AAPL.json
```

**Check 2**: Valid format
```python
import json
d = json.load(open('artifacts/ui_cache/AAPL.json'))
assert d['payload']['schema_version'] == 'analysis.compact.v1'
```

**Check 3**: API accessible
```bash
curl http://localhost:8000/ui/api/analysis/AAPL/latest
```

### Dashboard Shows No Data

**Fix**: Run cache sweep
```bash
python scripts/sweep_ui_cache.py --parallel 8
```

---

## 🔧 CLI Issues

### Command Not Found

```bash
# Ensure PATH includes local installs
export PATH="$HOME/.local/bin:$PATH"

# Reinstall
pip install -e .
```

### Permission Denied

```bash
# Use python -m instead
python -m victor_invest.cli analyze AAPL
```

---

## 🗄️ Database Issues

### Lock Timeout

```bash
# Check for long-running queries
SELECT pid, query, state, wait_event_type
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;

# Kill blocking query if needed
SELECT pg_terminate_backend(pid);
```

### Disk Space

```bash
# Check database size
SELECT pg_size_pretty(pg_database_size('victor'));

# Vacuum database
VACUUM FULL ANALYZE;
```

---

## 🐛 Python Issues

### Import Error: investigator

```bash
# Ensure you're in project root
cd /path/to/victor-invest

# Check PYTHONPATH
echo $PYTHONPATH  # Should include project root
```

### Type Check Failures

```bash
# Install mypy
pip install mypy

# Run type check
mypy victor_invest/
```

---

## 📝 Pre-commit Hooks

### Hook Failed

```bash
# Check what failed
cat .git/hooks/pre-commit

# Run manually
pre-commit run --all-files

# Fix issues
make format
make lint
```

### Commit Rejected (No AI Attribution)

```bash
# Check commit message
git log -1 --pretty=%B

# Remove Co-Authored-By trailer
git commit --amend
```

---

## 🔗 Get Help

| Resource | Link |
|----------|------|
| **Issues** | https://github.com/anvai-labs/victor-invest/issues |
| **Discussions** | https://github.com/anvai-labs/victor-invest/discussions |
| **CLAUDE.md** | In repo root (dev guidelines) |

---

## 📚 Common Error Patterns

| Error | Likely Cause | Solution |
|-------|--------------|----------|
| `psycopg2.OperationalError` | Database not running | `pg_ctl start` |
| `ModuleNotFoundError` | Missing dependency | `pip install -e ".[dev]"` |
| `KeyError: 'valuation'` | Config missing | Check `config.yaml` |
| `Connection refused` | Ollama not running | `ollama serve` |
| `FileNotFoundError` | Wrong directory | `cd /path/to/victor-invest` |

---

## 🎯 Quick Diagnosis

```bash
# Health check script
python << 'EOF'
import sys
sys.path.insert(0, '.')

print("=== Victor Invest Health Check ===")

# 1. Database
try:
    from investigator.infrastructure.database.db import DatabaseManager
    db = DatabaseManager()
    with db.get_session() as session:
        result = session.execute(text("SELECT COUNT(*) FROM symbol LIMIT 1"))
        print(f"✅ Database: OK ({result.scalar()} symbols)")
except Exception as e:
    print(f"❌ Database: {e}")

# 2. Ollama
try:
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=2)
    print(f"✅ Ollama: OK ({len(r.json())} models)")
except Exception as e:
    print(f"❌ Ollama: {e}")

# 3. Config
try:
    from investigator.config import get_config
    config = get_config()
    print(f"✅ Config: OK (database={bool(config.database.url)})")
except Exception as e:
    print(f"❌ Config: {e}")

print("=" * 50)
EOF
```

---

**Still stuck?** Open an issue with:
- Error message
- Command you ran
- System info (OS, Python version)
