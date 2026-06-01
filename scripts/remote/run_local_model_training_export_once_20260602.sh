#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_local_model_training_export_once
# AI_PURPOSE: 在 node-120 生产环境手动生成一次本地模型知识包，用于发布后验证。
# AI_BOUNDARY: 只运行知识导出脚本和读取生成文件，不调用任何设备控制接口。
# AI_RUNTIME: 通过 scripts/ssh_exec.sh 上传执行；生产路径使用 sudo -n。

APP_ROOT="/srv/smart-center"
CURRENT="$APP_ROOT/current"
PYTHON="$APP_ROOT/.venv/bin/python"
DATA_DIR="/srv/smart-center-data"

echo "current=$(sudo -n readlink -f "$CURRENT")"
echo "revision=$(sudo -n cat "$CURRENT/REVISION")"
cd "$CURRENT"
sudo -n SMART_CENTER_DATA_DIR="$DATA_DIR" "$PYTHON" "$CURRENT/scripts/export_local_model_training.py" --skip-full-code-context >/tmp/smart-center-local-model-export-once.json
sudo -n python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/smart-center-local-model-export-once.json").read_text(encoding="utf-8"))
export = payload.get("export") or {}
counts = export.get("counts") or {}
files = export.get("files") or {}
print("ok=" + str(payload.get("ok")))
for key in ("devices", "device_inventory", "control_capabilities", "query_intents", "control_intents", "nl_intent_examples", "insights"):
    print(f"{key}={counts.get(key)}")
for key in ("system_map", "device_inventory", "control_capabilities", "query_intents", "control_intents", "nl_intent_examples"):
    path = Path(str(files.get(key) or ""))
    print(f"{key}_file={path}")
    print(f"{key}_exists={path.is_file()}")
PY
