#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$HOME/.investigator/env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.investigator/env"
fi

mkdir -p artifacts/logs artifacts/reports

STAMP="$(date -u +%Y%m%d_%H%M%S)"
PRECOMPUTE_LOG="artifacts/logs/precompute_full_forward_1y_${STAMP}.log"
GUIDANCE_VALIDATION_LOG="artifacts/logs/guidance_validation_forward_1y_${STAMP}.log"

python scripts/precompute_dashboard_cache.py \
  --max-stockid 1000 \
  --mode comprehensive \
  --valuation-basis forward \
  --forward-horizon 1y \
  --force-refresh \
  --no-skip-cached \
  --source-env-file "$HOME/.investigator/env" | tee "$PRECOMPUTE_LOG"

python scripts/validate_forward_guidance_basket.py \
  --top-per-sector 5 \
  --mode comprehensive \
  --valuation-basis forward \
  --forward-horizon 1y \
  --use-cache-only \
  --source-env-file "$HOME/.investigator/env" | tee "$GUIDANCE_VALIDATION_LOG"

python - <<'PY'
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from victor_invest.api.app import _compute_rankings, _rankings_to_csv

payload = _compute_rankings(
    limit=50,
    per_sector=5,
    min_quality=50.0,
    max_age_hours=24.0 * 365.0,
    min_model_agreement=0.35,
    max_dispersion=0.8,
    basis="forward",
    forward_horizon="1y",
    pair_limit=100,
    pair_per_sector=3,
    min_pair_spread=5.0,
    portfolio_legs=20,
    min_confidence=40.0,
    require_model_agreement=True,
    require_dispersion=True,
    max_single_model_weight=0.8,
    require_multi_model=True,
    min_target_multiple=0.1,
    max_target_multiple=10.0,
    require_positive_target=True,
    exclude_split_suspects=True,
)

reports_dir = Path("artifacts/reports")
reports_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

json_path = reports_dir / f"rankings_forward_1y_strict_{stamp}.json"
json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

for export_type in ("overall", "sectors", "pairs", "portfolio"):
    csv_path = reports_dir / f"rankings_{export_type}_forward_1y_strict_{stamp}.csv"
    csv_path.write_text(_rankings_to_csv(payload, export_type), encoding="utf-8")

summary_lines = [
    f"generated_at: {payload.get('generated_at')}",
    f"cached_symbols: {(payload.get('universe') or {}).get('cached_symbols')}",
    f"eligible_symbols: {(payload.get('universe') or {}).get('eligible_symbols')}",
    f"sector_count: {(payload.get('universe') or {}).get('sector_count')}",
    "",
    "top_longs:",
]

for row in ((payload.get("overall") or {}).get("longs") or [])[:10]:
    summary_lines.append(
        f"  {row.get('symbol')}: exp_ret={row.get('expected_return_pct')} "
        f"quality={row.get('data_quality_score')} agree={row.get('model_agreement_score')} "
        f"disp={row.get('dispersion_ratio')}"
    )

summary_lines.append("")
summary_lines.append("top_shorts:")
for row in ((payload.get("overall") or {}).get("shorts") or [])[:10]:
    summary_lines.append(
        f"  {row.get('symbol')}: exp_ret={row.get('expected_return_pct')} "
        f"quality={row.get('data_quality_score')} agree={row.get('model_agreement_score')} "
        f"disp={row.get('dispersion_ratio')}"
    )

summary_path = reports_dir / f"rankings_summary_forward_1y_strict_{stamp}.txt"
summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

print(f"Rankings JSON: {json_path}")
print(f"Rankings summary: {summary_path}")
PY
