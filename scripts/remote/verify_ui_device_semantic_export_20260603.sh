#!/usr/bin/env bash
# AI_PURPOSE: Verify ui_device_semantics export from the feature branch using production Python dependencies.
# AI_BOUNDARY: Read/export-only into /tmp; does not switch production current or call device control APIs.
set -euo pipefail

BRANCH="${SMART_CENTER_VERIFY_BRANCH:-codex/mac-ui-device-semantic-knowledge-index-20260603}"
REPO_URL="${SMART_CENTER_REPO_URL:-/srv/git/smart-center-clean.git}"
WORKDIR="/tmp/smart-center-ui-semantic-verify-${BRANCH//\//-}"
OUT_DIR="/tmp/smart-center-ui-semantic-training"
PYTHON="/srv/smart-center/.venv/bin/python"

echo "== prepare branch =="
rm -rf "$WORKDIR" "$OUT_DIR"
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$WORKDIR"
git -C "$WORKDIR" rev-parse --short HEAD
mkdir -p "$OUT_DIR"

echo
echo "== export training into tmp =="
cd "$WORKDIR"
SMART_CENTER_DATA_DIR="$OUT_DIR" \
SMART_CENTER_CONFIG_FILE="/srv/smart-center-data/config.json" \
"$PYTHON" "$WORKDIR/scripts/export_local_model_training.py" --skip-full-code-context > /tmp/smart-center-ui-semantic-export.json

echo
echo "== semantic summary =="
"$PYTHON" - <<'PY'
import json
from collections import Counter
from pathlib import Path
payload = json.loads(Path("/tmp/smart-center-ui-semantic-export.json").read_text(encoding="utf-8"))
export = payload.get("export") or {}
files = export.get("files") or {}
semantic_path = Path(files.get("ui_device_semantics") or "")
rows = []
if semantic_path.is_file():
    rows = [json.loads(line) for line in semantic_path.read_text(encoding="utf-8").splitlines() if line.strip()]
modules = Counter(str(row.get("module") or "") for row in rows)
sources = Counter(str(row.get("source") or "") for row in rows)
samples = []
for module in ("node_red", "hvac", "light", "power", "server", "projector", "sequencer", "door", "env", "current_collector", "meter", "ups", "snmp", "proxy"):
    sample = next((row for row in rows if row.get("module") == module), None)
    if sample:
        samples.append({
            "module": module,
            "ui_text": sample.get("ui_text"),
            "device_name": sample.get("device_name"),
            "query_api": sample.get("query_api"),
            "control_api": sample.get("control_api"),
            "risk": sample.get("risk"),
        })
print(json.dumps({
    "ok": payload.get("ok"),
    "counts": export.get("counts"),
    "ui_device_semantics_file": str(semantic_path),
    "ui_device_semantics_exists": semantic_path.is_file(),
    "ui_semantic_count": len(rows),
    "modules": dict(modules),
    "sources": dict(sources),
    "samples": samples,
}, ensure_ascii=False, indent=2))
PY

echo
echo "== cleanup tmp branch =="
rm -rf "$WORKDIR"

