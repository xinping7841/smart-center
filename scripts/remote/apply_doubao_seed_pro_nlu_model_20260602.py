#!/usr/bin/env python3
"""Switch production NLU cloud model to Doubao Seed 2.0 Pro.

AI_MODULE: remote_apply_doubao_seed_pro_nlu_model
AI_PURPOSE: Persist the higher-capability Ark model for Feishu natural-language control.
AI_BOUNDARY: Edits /srv/smart-center-data/config.json only; does not execute device controls.
AI_RUNTIME: Run through scripts/ssh_exec.sh; production paths use sudo -n through reexec.
AI_RISK: Medium, changes cloud model used for natural-language understanding.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))
MODEL_ID = os.environ.get("ARK_NLU_MODEL", "doubao-seed-2-0-pro-260215").strip()
MODEL_NAME = os.environ.get("ARK_NLU_NAME", "Doubao-Seed-2.0-pro").strip()


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
    cloud_model = local_model.setdefault("cloud_model", {})
    if not isinstance(cloud_model, dict):
        cloud_model = {}
        local_model["cloud_model"] = cloud_model

    before = {
        "name": cloud_model.get("name"),
        "model": cloud_model.get("model"),
        "timeout_sec": cloud_model.get("timeout_sec"),
        "priority": cloud_model.get("priority"),
        "compare_with_local": cloud_model.get("compare_with_local"),
    }
    cloud_model.update(
        {
            "enabled": True,
            "name": MODEL_NAME,
            "provider": "ark",
            "base_url": str(cloud_model.get("base_url") or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/"),
            "model": MODEL_ID,
            "timeout_sec": int(os.environ.get("ARK_NLU_TIMEOUT_SEC", "90") or 90),
            "temperature": float(os.environ.get("ARK_NLU_TEMPERATURE", "0") or 0),
            "max_tokens": int(os.environ.get("ARK_NLU_MAX_TOKENS", "2048") or 2048),
            "priority": "cloud_first",
            "compare_with_local": True,
            "use_for_system_summary": True,
            "use_for_nlu_fallback": True,
        }
    )
    policy = local_model.setdefault("natural_language", {})
    if not isinstance(policy, dict):
        policy = {}
        local_model["natural_language"] = policy
    policy.update(
        {
            "feishu_control_enabled": True,
            "feishu_control_require_confirmation": False,
            "record_process_enabled": True,
            "process_log_limit": int(policy.get("process_log_limit") or 200),
        }
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.pre-doubao-seed-pro-nlu-{stamp}")
    shutil.copy2(CONFIG_PATH, backup)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    print(json.dumps(
        {
            "ok": True,
            "config": str(CONFIG_PATH),
            "backup": str(backup),
            "before": before,
            "cloud_model": {
                "enabled": cloud_model.get("enabled"),
                "name": cloud_model.get("name"),
                "provider": cloud_model.get("provider"),
                "base_url": cloud_model.get("base_url"),
                "model": cloud_model.get("model"),
                "api_key_set": bool(cloud_model.get("api_key")),
                "timeout_sec": cloud_model.get("timeout_sec"),
                "temperature": cloud_model.get("temperature"),
                "priority": cloud_model.get("priority"),
                "compare_with_local": cloud_model.get("compare_with_local"),
                "use_for_nlu_fallback": cloud_model.get("use_for_nlu_fallback"),
            },
            "natural_language": {
                "feishu_control_enabled": policy.get("feishu_control_enabled"),
                "feishu_control_require_confirmation": policy.get("feishu_control_require_confirmation"),
                "record_process_enabled": policy.get("record_process_enabled"),
            },
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
