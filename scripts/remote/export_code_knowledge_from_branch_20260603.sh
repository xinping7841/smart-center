#!/usr/bin/env bash
set -euo pipefail

BRANCH="${SMART_CENTER_CODE_KNOWLEDGE_BRANCH:-codex/mac-code-knowledge-index-ai-markers-20260603}"
REPO_URL="${SMART_CENTER_REPO_URL:-/srv/git/smart-center-clean.git}"
WORKDIR="/tmp/smart-center-code-knowledge-export-${BRANCH//\//-}"
DATA_DIR="/srv/smart-center-data"
PYTHON="/srv/smart-center/.venv/bin/python"

echo "== prepare branch workdir =="
if [ ! -d "$WORKDIR/.git" ]; then
  rm -rf "$WORKDIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$WORKDIR"
else
  git -C "$WORKDIR" fetch origin "$BRANCH"
  git -C "$WORKDIR" checkout "$BRANCH"
  git -C "$WORKDIR" reset --hard "origin/$BRANCH"
fi
git -C "$WORKDIR" rev-parse --short HEAD

echo
echo "== export code knowledge =="
sudo -n SMART_CENTER_DATA_DIR="$DATA_DIR" "$PYTHON" "$WORKDIR/scripts/export_code_knowledge.py"

echo
echo "== latest code knowledge files =="
sudo -n find "$DATA_DIR/training/local_model" -maxdepth 1 -type f \
  \( -name 'code_*' -o -name 'module_cards_*' -o -name 'full_code_context_*' -o -name 'ai_marker_coverage_*' \) \
  -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %f\n' | sort | tail -n 18

echo
echo "== latest manifest and coverage summary =="
sudo -n python3 - <<'PY'
import json
from pathlib import Path
base = Path("/srv/smart-center-data/training/local_model")
manifests = sorted(base.glob("code_manifest_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
coverages = sorted(base.glob("ai_marker_coverage_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
manifest = json.loads(manifests[0].read_text(encoding="utf-8")) if manifests else {}
coverage = json.loads(coverages[0].read_text(encoding="utf-8")) if coverages else {}
print(json.dumps({
    "manifest": manifests[0].name if manifests else "",
    "manifest_counts": manifest.get("counts") or {},
    "coverage": coverages[0].name if coverages else "",
    "coverage_counts": coverage.get("counts") or {},
    "missing_required_top": (coverage.get("missing_required_top") or [])[:10],
}, ensure_ascii=False, indent=2))
PY
