#!/usr/bin/env python3
"""Apply cloud/local parallel NLU runtime policy on production.

AI_MODULE: remote_apply_cloud_parallel_nlu_policy
AI_PURPOSE: Persist Feishu cloud-first parallel NLU and fast execution policy.
AI_BOUNDARY: Edits /srv/smart-center-data/config.json only; does not call device-control APIs.
AI_RUNTIME: Run through scripts/ssh_exec.sh; production paths use sudo -n through reexec.
AI_RISK: Medium, changes Feishu natural-language execution policy and restarts service externally.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))


def reexec_with_sudo_if_needed() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return
    os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])


def main() -> int:
    reexec_with_sudo_if_needed()
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("config root is not an object")
    local_model = payload.setdefault("local_model", {})
    if not isinstance(local_model, dict):
        raise SystemExit("local_model is not an object")
    policy = local_model.setdefault("natural_language", {})
    if not isinstance(policy, dict):
        raise SystemExit("local_model.natural_language is not an object")
    cloud_model = local_model.setdefault("cloud_model", {})
    if not isinstance(cloud_model, dict):
        cloud_model = {}
        local_model["cloud_model"] = cloud_model

    updates = {
        "natural_language.feishu_control_enabled": True,
        "natural_language.feishu_control_require_confirmation": False,
        "natural_language.record_process_enabled": True,
        "cloud_model.priority": "cloud_first",
        "cloud_model.compare_with_local": True,
        "cloud_model.use_for_nlu_fallback": True,
    }
    changed = False
    if policy.get("feishu_control_enabled") is not True:
        policy["feishu_control_enabled"] = True
        changed = True
    if policy.get("feishu_control_require_confirmation") is not False:
        policy["feishu_control_require_confirmation"] = False
        changed = True
    if policy.get("record_process_enabled") is not True:
        policy["record_process_enabled"] = True
        changed = True
    if not isinstance(policy.get("process_log_limit"), int):
        policy["process_log_limit"] = 200
        changed = True
    if cloud_model.get("priority") != "cloud_first":
        cloud_model["priority"] = "cloud_first"
        changed = True
    if cloud_model.get("compare_with_local") is not True:
        cloud_model["compare_with_local"] = True
        changed = True
    if cloud_model.get("use_for_nlu_fallback") is not True:
        cloud_model["use_for_nlu_fallback"] = True
        changed = True

    backup_path = ""
    if changed:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.pre-cloud-parallel-nlu-{stamp}")
        shutil.copy2(CONFIG_PATH, backup)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CONFIG_PATH)
        backup_path = str(backup)

    print(json.dumps(
        {
            "ok": True,
            "changed": changed,
            "config": str(CONFIG_PATH),
            "backup": backup_path,
            "updates": updates,
            "natural_language": {
                "feishu_control_enabled": policy.get("feishu_control_enabled"),
                "feishu_control_require_confirmation": policy.get("feishu_control_require_confirmation"),
                "record_process_enabled": policy.get("record_process_enabled"),
                "process_log_limit": policy.get("process_log_limit"),
            },
            "cloud_model": {
                "enabled": cloud_model.get("enabled"),
                "provider": cloud_model.get("provider"),
                "model": cloud_model.get("model"),
                "api_key_set": bool(cloud_model.get("api_key")),
                "priority": cloud_model.get("priority"),
                "compare_with_local": cloud_model.get("compare_with_local"),
                "use_for_nlu_fallback": cloud_model.get("use_for_nlu_fallback"),
            },
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
