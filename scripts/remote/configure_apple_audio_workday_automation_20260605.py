#!/usr/bin/env python3
"""Configure workday music playback automation on node-120.

AI_MODULE: remote_configure_apple_audio_workday_automation
AI_PURPOSE: Add/update Smart Center scenes and schedule rules for workday Apple Audio playback.
AI_BOUNDARY: Edits /srv/smart-center-data/config.json only; does not call automation test, playback, stop, or device-control APIs.
AI_RUNTIME: Run via scripts/ssh_exec.sh on node-120, then restart smart-center.service for the automation engine to reload config.
AI_RISK: Medium. The saved rules will start/stop real audio at scheduled workday times.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))
PLAYLIST_ID = os.environ.get("SMART_CENTER_WORKDAY_MUSIC_PLAYLIST_ID", "folder:e38a08cca65f")
PLAYLIST_NAME = os.environ.get("SMART_CENTER_WORKDAY_MUSIC_PLAYLIST_NAME", "器乐+轻音乐")
PLAYBACK_MODE = os.environ.get("SMART_CENTER_WORKDAY_MUSIC_MODE", "shuffle")


def run_sudo(args: list[str]) -> None:
    subprocess.run(["sudo", "-n", *args], check=True)


def stat_config() -> tuple[str, str, str]:
    result = subprocess.run(
        ["stat", "-c", "%a %u %g", str(CONFIG_PATH)],
        check=True,
        text=True,
        capture_output=True,
    )
    mode, owner, group = result.stdout.strip().split()
    return mode, owner, group


def upsert_by_id(rows: list[dict], item: dict) -> bool:
    item_id = str(item.get("id") or "").strip()
    for index, row in enumerate(rows):
        if isinstance(row, dict) and str(row.get("id") or "").strip() == item_id:
            if row != item:
                rows[index] = item
                return True
            return False
    rows.append(item)
    return True


def main() -> int:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    scenes = payload.setdefault("scenes", [])
    automations = payload.setdefault("automations", [])
    if not isinstance(scenes, list) or not isinstance(automations, list):
        raise SystemExit("config scenes/automations must be lists")

    play_scene = {
        "id": "scene_apple_audio_workday_play",
        "name": "工作日音乐自动播放",
        "actions": [
            {
                "sub_system": "apple_audio",
                "action_type": "play_playlist",
                "playlist_id": PLAYLIST_ID,
                "playlist_name": PLAYLIST_NAME,
                "mode": PLAYBACK_MODE,
            }
        ],
    }
    stop_scene = {
        "id": "scene_apple_audio_workday_stop",
        "name": "工作日音乐自动停止",
        "actions": [
            {
                "sub_system": "apple_audio",
                "action_type": "stop",
            }
        ],
    }
    play_rule = {
        "id": "auto_apple_audio_workday_0910_play",
        "name": "工作日早上9点10音乐自动播放",
        "enabled": True,
        "trigger_type": "schedule",
        "action_scene_id": play_scene["id"],
        "condition": {
            "source_type": "env",
            "device_id": "",
            "prop": "lux",
            "op": "<",
            "value": 0,
            "debounce_sec": 0,
            "hysteresis": 0,
            "consecutive_hits": 1,
            "crossing_mode": "none",
            "rearm_value": "",
            "window_bootstrap_sec": 0,
        },
        "schedule": {
            "day_type": "workday",
            "days": [],
            "time": "09:10",
            "time_start": "09:10",
            "time_end": "09:40",
            "recovery_grace_sec": 300,
        },
        "preconditions": [],
        "precondition_mode": "all",
        "triggers": [],
        "trigger_mode": "any",
    }
    stop_rule = {
        **play_rule,
        "id": "auto_apple_audio_workday_1810_stop",
        "name": "工作日下午6点10音乐自动停止",
        "action_scene_id": stop_scene["id"],
        "schedule": {
            "day_type": "workday",
            "days": [],
            "time": "18:10",
            "time_start": "18:10",
            "time_end": "18:40",
            "recovery_grace_sec": 300,
        },
    }

    changed = False
    changed = upsert_by_id(scenes, play_scene) or changed
    changed = upsert_by_id(scenes, stop_scene) or changed
    changed = upsert_by_id(automations, play_rule) or changed
    changed = upsert_by_id(automations, stop_rule) or changed

    backup = ""
    if changed:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.pre-apple-audio-workday-automation-{stamp}")
        mode, owner, group = stat_config()
        run_sudo(["cp", "-a", str(CONFIG_PATH), str(backup_path)])
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir="/tmp",
            prefix="smart-center-config.",
            suffix=".json",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        try:
            run_sudo([
                "install",
                "-m",
                mode,
                "-o",
                owner,
                "-g",
                group,
                str(tmp_path),
                str(CONFIG_PATH),
            ])
        finally:
            tmp_path.unlink(missing_ok=True)
        backup = str(backup_path)

    print(json.dumps(
        {
            "ok": True,
            "changed": changed,
            "backup": backup,
            "scenes": [play_scene["id"], stop_scene["id"]],
            "automations": [play_rule["id"], stop_rule["id"]],
            "playlist_id": PLAYLIST_ID,
            "playlist_name": PLAYLIST_NAME,
            "playback_mode": PLAYBACK_MODE,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
