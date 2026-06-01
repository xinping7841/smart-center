#!/usr/bin/env python3
"""Enable persisted Feishu natural-language control on production once.

This migration changes the existing production config from the previous
conservative default to the new operator-requested default: Feishu control is
enabled, but every control still follows confirmation, permissions, and audit.
The AI page switch remains persisted in config.json after this migration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path("/srv/smart-center-data/config.json")


def reexec_with_sudo_if_needed() -> None:
    if os.geteuid() == 0:
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

    changed = False
    if policy.get("feishu_control_enabled") is not True:
        policy["feishu_control_enabled"] = True
        changed = True
    if policy.get("feishu_control_require_confirmation") is not True:
        policy["feishu_control_require_confirmation"] = True
        changed = True
    if policy.get("record_process_enabled") is not True:
        policy["record_process_enabled"] = True
        changed = True
    if not isinstance(policy.get("process_log_limit"), int):
        policy["process_log_limit"] = 200
        changed = True

    if not changed:
        print("changed=false")
        print(f"feishu_control_enabled={policy.get('feishu_control_enabled')}")
        print(f"feishu_control_require_confirmation={policy.get('feishu_control_require_confirmation')}")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = CONFIG_PATH.with_name(f"config.pre-feishu-control-default-{stamp}.json")
    shutil.copy2(CONFIG_PATH, backup_path)
    tmp_path = CONFIG_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(CONFIG_PATH)
    subprocess.run(["systemctl", "restart", "smart-center.service"], check=True)
    print("changed=true")
    print(f"backup={backup_path}")
    print(f"feishu_control_enabled={policy.get('feishu_control_enabled')}")
    print(f"feishu_control_require_confirmation={policy.get('feishu_control_require_confirmation')}")
    print(f"record_process_enabled={policy.get('record_process_enabled')}")
    print(f"process_log_limit={policy.get('process_log_limit')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
