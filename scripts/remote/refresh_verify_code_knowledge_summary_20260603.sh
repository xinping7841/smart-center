#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="/srv/smart-center-data"
CURRENT="/srv/smart-center/current"
PYTHON="/srv/smart-center/.venv/bin/python"
MAX_INPUT_CHARS="${SMART_CENTER_SUMMARY_MAX_INPUT_CHARS:-8000}"

echo "== refresh system summary with latest code knowledge =="
sudo -n SMART_CENTER_DATA_DIR="$DATA_DIR" "$PYTHON" "$CURRENT/scripts/refresh_local_model_system_summary.py" --max-input-chars "$MAX_INPUT_CHARS"

echo
echo "== latest knowledge status =="
python3 - <<'PY'
import json, urllib.request
payload = json.loads(urllib.request.urlopen("http://127.0.0.1:6899/api/local-model/knowledge-status", timeout=10).read().decode("utf-8"))
items = []
for item in payload.get("items") or []:
    if item.get("prefix") in {"code_system_map", "module_cards", "code_knowledge", "full_code_context", "system_summary"}:
        items.append({
            "prefix": item.get("prefix"),
            "name": item.get("name"),
            "updated_at": item.get("updated_at"),
            "count": item.get("count"),
            "size": item.get("size"),
        })
print(json.dumps({
    "ok": payload.get("ok"),
    "latest_updated_at": payload.get("latest_updated_at"),
    "model": payload.get("model"),
    "max_model_len": payload.get("max_model_len"),
    "items": items,
    "last_summary": payload.get("last_summary"),
}, ensure_ascii=False, indent=2))
PY

echo
echo "== code knowledge chat probe =="
python3 - <<'PY'
import json, urllib.request
payload = json.dumps({
    "messages": [
        {"role": "user", "content": "根据最新代码知识索引，HA/空调信息更新滞后问题应优先查看哪些模块或文件？同时说明真实设备控制的安全边界。"}
    ]
}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:6899/api/local-model/chat",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
print(json.dumps({
    "ok": data.get("ok"),
    "elapsed_ms": data.get("elapsed_ms"),
    "answer": str(data.get("answer") or data.get("reply") or "")[:1600],
}, ensure_ascii=False, indent=2))
PY
