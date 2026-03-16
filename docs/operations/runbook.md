# Operations Runbook

**Deployment, monitoring, and maintenance**

---

## 🚀 Deployment

### Environment Setup

```bash
# 1. System requirements
# - Ubuntu 22.04+ / macOS 12+
# - Python 3.11+
# - PostgreSQL 14+
# - 16GB RAM minimum

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Database setup
createdb victor
psql -d victor < schema/schema.sql  # If needed

# 4. Start services
pg_ctl start
ollama serve

# 5. Verify
victor-invest --help
```

---

## 📊 Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database
pg_ctl status
psql -d victor -c "SELECT COUNT(*) FROM symbol"

# Ollama
curl http://localhost:11434/api/tags
```

### Log Monitoring

```bash
# Application logs
tail -f logs/victor-invest.log

# PostgreSQL logs
tail -f /var/log/postgresql/postgresql.log

# Ollama logs
journalctl -u ollama -f
```

### API Exposure

```bash
# Canonical UI route
open http://localhost:8000/ui

# Restrict cross-origin access explicitly when serving beyond localhost
export VICTOR_ALLOWED_ORIGINS="https://research.example.com"

# Require bearer auth for analysis/refresh/cache mutation endpoints
export VICTOR_API_BEARER_TOKEN="replace-with-long-random-token"
```

---

## 🗄️ Database Maintenance

### Backup

```bash
# Dump database
pg_dump victor > backup_$(date +%Y%m%d).sql

# Restore
psql victor < backup_20260222.sql
```

### Vacuum

```sql
VACUUM FULL ANALYZE sec_companyfacts_processed;
VACUUM FULL ANALYZE symbol;
```

### Indexes

```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
```

---

## 🔄 Cache Management

### UI Cache Sweep

```bash
# Full sweep (all symbols)
python scripts/sweep_ui_cache.py --parallel 8

# Incremental (daily)
0 2 * * * cd /path/to/victor-invest && python scripts/sweep_ui_cache.py --parallel 8 >> /var/log/sweep.log 2>&1
```

### Cache Stats

```bash
# Cache size
du -sh artifacts/ui_cache/

# File count
ls -1 artifacts/ui_cache/*.json | wc -l

# Age of files
find artifacts/ui_cache/*.json -mtime +7 -ls
```

---

## 🐛 Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
pg_ctl status
pg_ctl start
```

**Ollama Not Responding**
```bash
ollama serve
curl http://localhost:11434/api/tags
```

**Cache Empty**
```bash
python scripts/sweep_ui_cache.py --parallel 8
```

### Log Analysis

```bash
# Error patterns
grep -i "error" logs/victor-invest.log | tail -20

# Performance issues
grep "completed in" logs/victor-invest.log | tail -20

# Warnings
grep -i "warning" logs/victor-invest.log | tail -20
```

---

## 📈 Performance Tuning

### Database

```sql
-- Connection pool
ALTER SYSTEM SET max_connections = 200;

-- Shared buffers
ALTER SYSTEM SET shared_buffers = '4GB';

-- Work memory
ALTER SYSTEM SET work_mem = '1GB';
```

### Ollama

```yaml
# config.yaml
ollama:
  timeout: 300          # Request timeout
  num_parallel: 4      # Parallel requests
  retry_attempts: 3    # Retry logic
```

### Application

```python
# victor_invest/cli.py
WORKFLOW_TIMEOUT = 600.0  # Workflow timeout
MAX_PARALLEL = 16            # Max parallel workers
```

---

## 🔐 Security

### Secrets Management

```bash
# Use environment variables
export DATABASE_URL="postgresql://user:pass@localhost/db"
export OLLAMA_API_KEY="sk-..."
```

### Firewall

```bash
# Allow PostgreSQL
sudo ufw allow 5432/tcp

# Allow Ollama
sudo ufw allow 11434/tcp

# Allow API server
sudo ufw allow 8000/tcp
```

---

## 📝 Maintenance Schedule

### Daily
- Cache sweep (auto via cron)
- Log rotation
- Health checks

### Weekly
- Database vacuum
- Review logs for errors
- Check disk space

### Monthly
- Update dependencies
- Review and clean cache
- Performance audit

---

## 🔗 Related

- [Development](../developer/development.md) - Setup guide
- [Troubleshooting](../user/troubleshooting.md) - Common issues
- [Web UI Cache](web-ui-cache-sweep.md) - Cache operations
