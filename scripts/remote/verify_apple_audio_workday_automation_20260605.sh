#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_verify_apple_audio_workday_automation
# AI_PURPOSE: Verify workday music automation config and runtime state without executing scenes.
# AI_BOUNDARY: Read-only checks for config, service status, /api/automation/status, and /api/apple-audio/status.
# AI_RUNTIME: Run via scripts/ssh_exec.sh on node-120 after release/config application.
# AI_RISK: Low. Does not call /api/automation/test or Apple Audio transport/queue endpoints.

echo "smart_center_active=$(sudo -n systemctl is-active smart-center.service)"
python3 - <<'PY'
import json
import urllib.request
from pathlib import Path

cfg = json.loads(Path("/srv/smart-center-data/config.json").read_text(encoding="utf-8"))
scene_ids = {"scene_apple_audio_workday_play", "scene_apple_audio_workday_stop"}
rule_ids = {"auto_apple_audio_workday_0910_play", "auto_apple_audio_workday_1810_stop"}
scenes = [row for row in cfg.get("scenes", []) if isinstance(row, dict) and row.get("id") in scene_ids]
rules = [row for row in cfg.get("automations", []) if isinstance(row, dict) and row.get("id") in rule_ids]

status = json.loads(urllib.request.urlopen("http://127.0.0.1:6899/api/automation/status", timeout=15).read().decode("utf-8"))
runtime_rules = [row for row in status.get("rules", []) if row.get("id") in rule_ids]
audio = json.loads(urllib.request.urlopen("http://127.0.0.1:6899/api/apple-audio/status", timeout=30).read().decode("utf-8"))
state = audio.get("state") or {}
playlist_ids = {row.get("id") for row in state.get("playlists", []) if isinstance(row, dict)}
checks = {
    "config_has_two_scenes": len(scenes) == 2,
    "config_has_two_rules": len(rules) == 2,
    "rules_enabled": all(bool(row.get("enabled")) for row in rules),
    "rules_workday": all((row.get("schedule") or {}).get("day_type") == "workday" for row in rules),
    "runtime_has_two_rules": len(runtime_rules) == 2,
    "playlist_exists": "folder:e38a08cca65f" in playlist_ids,
    "local_player_enabled": bool((state.get("local_player") or {}).get("enabled")),
    "not_playing_now": not bool(state.get("is_playing")),
}
print(json.dumps({
    "ok": all(checks.values()),
    "checks": checks,
    "rules": [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "enabled": row.get("enabled"),
            "scene": row.get("action_scene_id") or row.get("scene_id"),
            "schedule": row.get("schedule"),
            "last_schedule_planned_at": (row.get("state") or {}).get("last_schedule_planned_at"),
            "last_schedule_day": (row.get("state") or {}).get("last_schedule_day"),
        }
        for row in runtime_rules
    ],
    "audio": {
        "player_mode": state.get("player_mode"),
        "local_player": state.get("local_player"),
        "is_playing": state.get("is_playing"),
        "library_size": state.get("library_size"),
    },
}, ensure_ascii=False, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
PY
