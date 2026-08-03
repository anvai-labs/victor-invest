# Changelog

**All notable changes to victor-invest**

---

## [2026-02-22] Compact Format & Web UI Integration

### ✨ New Features

**Compact Format Support**
- Added `--detail/-d` flag to victor-invest CLI
- Choices: minimal, standard, compact, verbose
- Schema: `analysis.compact.v1`
- Size reduction: ~87% (2KB vs 15KB per symbol)

**Automated UI Cache Sweep**
- Script: `scripts/sweep_ui_cache.py`
- Populates `artifacts/ui_cache/` for web UI
- Processes all 3,719 SEC-filing symbols
- Ordered by stockid

**Shared Converter Module**
- Created: `src/investigator/application/victor_result_converter.py`
- Eliminated ~100 lines of code duplication
- Single source of truth for both CLIs

### 🐛 Bug Fixes

**EBITDA Data Quality**
- Fixed missing `depreciation_amortization` column in quarterly data query
- EV/EBITDA model now working for all symbols
- Commit: `bd54ab2`

**Code Duplication**
- Refactored conversion logic to shared module
- Both CLIs now use same converter
- Commit: `ecfee32`

### 📝 Documentation

**New Structure**
```
docs/
├── README.md                 # Navigation hub (visual)
├── user/                     # End-user docs
├── developer/                # Developer docs
├── technical/                # Technical reference
├── api/                       # API docs
├── operations/                # Operations
└── insights/                  # Analysis insights
```

**Consolidated Docs**
- [Compact Format Guide](user/cli-commands.md#compact-format)
- [Web UI Cache Sweep](operations/web-ui-cache-sweep.md)
- [Architecture Overview](developer/architecture.md)
- [Troubleshooting Guide](user/troubleshooting.md)

### 🔄 Breaking Changes

- **None**

### ⚡ Performance

| Metric | Before | After |
|--------|--------|-------|
| Compact file size | 15KB | 2KB (87% reduction) |
| Web UI load time | ~5s | ~50ms (100x faster) |
| Code duplication | 100 lines | 10 lines (shared module) |

---

## [Previous Releases]

See [git log](https://github.com/anvai-labs/victor-invest/commits/main) for full history.

---

## 🏷️ Version Tags

- `v1.0.0` - Initial release
- `v1.1.0` - Victor framework integration
- `v1.2.0` - Compact format and web UI cache

---

## 📞 Support

- **Issues**: https://github.com/anvai-labs/victor-invest/issues
- **Discussions**: https://github.com/anvai-labs/victor-invest/discussions
