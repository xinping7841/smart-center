#!/usr/bin/env bash
set -euo pipefail

echo "== restart services =="
sudo -n systemctl restart smart-center.service
sudo -n systemctl restart smart-center-feishu-bot.service
sleep 4
sudo -n systemctl is-active smart-center.service
sudo -n systemctl is-active smart-center-feishu-bot.service

echo
echo "== context config =="
sudo -n python3 - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("/srv/smart-center-data/config.json").read_text(encoding="utf-8"))
lm = cfg.get("local_model") or {}
ctx = lm.get("knowledge_context") or {}
print(json.dumps({
    "model": lm.get("model"),
    "base_url": lm.get("base_url"),
    "system_prompt_chars": len(str(lm.get("system_prompt") or "")),
    "knowledge_kind": ctx.get("kind"),
    "module_card_count": ctx.get("module_card_count"),
    "marker_required_missing": ctx.get("marker_required_missing"),
    "code_system_map": ctx.get("code_system_map"),
    "ai_marker_coverage": ctx.get("ai_marker_coverage"),
}, ensure_ascii=False, indent=2))
PY

echo
echo "== chat probe =="
python3 - <<'PY'
import json, urllib.request
payload = json.dumps({
    "messages": [
        {"role": "user", "content": "HA/空调信息更新滞后，先列出你建议检查的具体代码文件路径，并说明哪些只能查状态、不能直接控制。"}
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
    "answer": str(data.get("answer") or "")[:1800],
}, ensure_ascii=False, indent=2))
PY
