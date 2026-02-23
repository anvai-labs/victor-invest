# Operations Runbook

**Deployment, monitoring, maintenance**

---

## 🚀 Deployment

```bash
# Install
pip install -e ".[dev]"

# Setup database
createdb victor

# Start services
pg_ctl start
ollama serve

# Verify
victor-invest --help
```

---

## 📊 Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/api/health

# Database
pg_ctl status

# Ollama
curl http://localhost:11434/api/tags
```

### Log Monitoring

```bash
# Application logs
tail -f logs/victor-invest.log

# PostgreSQL logs
tail -f /var/log/postgresql/postgresql.log
```

---

## 🗄️ Database Maintenance

### Backup

```bash
# Dump
pg_dump victor > backup_$(date +%Y%m%d).sql

# Restore
psql victor < backup_20260222.sql
```

### Vacuum

```sql
VACUUM FULL ANALYZE sec_companyfacts_processed;
VACUUM FULL ANALYZE symbol;
```

---

## 🔄 Cache Management

### UI Cache Sweep

```bash
# Full sweep
python scripts/sweep_ui_cache.py --parallel 8

# Incremental (daily cron)
0 2 * * * cd /path/to/victor-invest && python scripts/sweep_ui_cache.py --parallel 8
```

### Cache Stats

```bash
# Cache size
du -sh artifacts/ui_cache/

# File count
ls -1 artifacts/ui_cache/*.json | wc -l
```

---

## 🐛 Troubleshooting

### Common Issues

```
Database Connection Failed → pg_ctl start
Ollama Not Responding     → ollama serve
Cache Empty               → python scripts/sweep_ui_cache.py
```

---

## 📝 Maintenance Schedule

```
Daily:   Cache sweep, log rotation, health checks
Weekly:  Database vacuum, review logs
Monthly: Update dependencies, performance audit
```

---

## 🔗 Related

- [Development](../developer/development.md) - Dev setup
- [Cache Sweep](web-ui-cache-sweep.md) - Cache operations
