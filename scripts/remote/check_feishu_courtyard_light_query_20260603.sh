#!/usr/bin/env bash
# AI_PURPOSE: Diagnose why Feishu "庭院灯状态" maps to generic light status, using read-only production checks.
# AI_BOUNDARY: Read-only; this script must not call Node-RED or Smart Center control endpoints.
set -euo pipefail

echo "== active release =="
readlink -f /srv/smart-center/current || true
git -C /srv/smart-center/current rev-parse --short HEAD || true

echo
echo "== smart-center services =="
sudo -n systemctl is-active smart-center.service || true
sudo -n systemctl is-active smart-center-feishu-bot.service || true

echo
echo "== recent feishu logs for courtyard query =="
sudo -n journalctl -u smart-center-feishu-bot.service --since "2026-06-03 23:20:00" --no-pager \
  | grep -E "庭院灯状态|\\[nl intent\\]|\\[message\\]" \
  | tail -n 80 || true

echo
echo "== read-only generic light status =="
curl -fsS --max-time 6 http://127.0.0.1:6899/api/light/status \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(json.dumps({"keys": list(data.keys()), "channels": data.get("channels"), "extras": data.get("extras")}, ensure_ascii=False, indent=2)[:2000])' || true

echo
echo "== read-only courtyard Node-RED status =="
curl -fsS --max-time 8 http://127.0.0.1:6899/api/node-red/device/courtyard_light/status \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); dev=data.get("device", data); keep={k:dev.get(k) for k in ["device_id","device_name","device_type","online","status","display_status","display_text","updated_at","health","gateway"]}; print(json.dumps(keep, ensure_ascii=False, indent=2)[:2000])' || true

