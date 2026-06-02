#!/usr/bin/env bash
set -euo pipefail

echo "== restart services =="
sudo -n systemctl restart smart-center.service
sudo -n systemctl restart smart-center-feishu-bot.service
sleep 3
sudo -n systemctl is-active smart-center.service
sudo -n systemctl is-active smart-center-feishu-bot.service

echo
echo "== service env =="
sudo -n systemctl show smart-center.service -p ExecStart -p WorkingDirectory -p EnvironmentFiles --no-pager
sudo -n systemctl show smart-center-feishu-bot.service -p ExecStart -p WorkingDirectory -p EnvironmentFiles --no-pager

echo
echo "== config summary =="
sudo -n python3 - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("/srv/smart-center-data/config.json").read_text(encoding="utf-8"))
lm = cfg.get("local_model") if isinstance(cfg, dict) else {}
cloud = lm.get("cloud_model") if isinstance(lm, dict) and isinstance(lm.get("cloud_model"), dict) else {}
nl = lm.get("natural_language") if isinstance(lm, dict) and isinstance(lm.get("natural_language"), dict) else {}
print(json.dumps({
    "local_model": lm.get("model") if isinstance(lm, dict) else "",
    "cloud_enabled": cloud.get("enabled"),
    "cloud_name": cloud.get("name"),
    "cloud_model": cloud.get("model"),
    "cloud_priority": cloud.get("priority"),
    "compare_with_local": cloud.get("compare_with_local"),
    "cloud_api_key_set": bool(cloud.get("api_key")),
    "feishu_control_enabled": nl.get("feishu_control_enabled"),
    "feishu_control_require_confirmation": nl.get("feishu_control_require_confirmation"),
    "record_process_enabled": nl.get("record_process_enabled"),
}, ensure_ascii=False, indent=2))
PY

echo
echo "== http checks =="
curl -fsS http://127.0.0.1:6899/api/local-model/config | python3 - <<'PY'
import json, sys
payload = json.load(sys.stdin)
cfg = payload.get("config") or {}
cloud = cfg.get("cloud_model") or {}
nl = cfg.get("natural_language") or {}
print(json.dumps({
    "ok": payload.get("ok"),
    "cloud_model": cloud.get("model"),
    "cloud_name": cloud.get("name"),
    "priority": cloud.get("priority"),
    "compare_with_local": cloud.get("compare_with_local"),
    "api_key_set": cloud.get("api_key_set"),
    "feishu_control_enabled": nl.get("feishu_control_enabled"),
    "feishu_control_require_confirmation": nl.get("feishu_control_require_confirmation"),
}, ensure_ascii=False, indent=2))
PY

curl -fsS http://127.0.0.1:6899/api/local-model/health | python3 - <<'PY'
import json, sys
payload = json.load(sys.stdin)
print(json.dumps({
    "ok": payload.get("ok"),
    "proxy_online": payload.get("proxy_online"),
    "vllm_online": payload.get("vllm_online"),
    "cloud_online": payload.get("cloud_online"),
    "cloud_model": (payload.get("config") or {}).get("cloud_model", {}).get("model"),
}, ensure_ascii=False, indent=2))
PY

echo
echo "== feishu recent journal =="
sudo -n journalctl -u smart-center-feishu-bot.service -n 25 --no-pager
