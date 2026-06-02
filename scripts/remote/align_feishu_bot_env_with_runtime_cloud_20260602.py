#!/usr/bin/env python3
"""Align Feishu bot env with runtime cloud/local NLU policy.

AI_MODULE: remote_align_feishu_bot_env_cloud
AI_PURPOSE: Remove stale Feishu env overrides that prevent the standalone bot
from reading the production cloud model config.
AI_BOUNDARY: Edits /etc/smart-center/feishu-bot.env only; does not execute device controls.
AI_RUNTIME: Run through scripts/ssh_exec.sh; production /etc path uses sudo -n through reexec.
AI_RISK: Medium, affects Feishu natural-language model selection.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


ENV_PATH = Path(os.environ.get("FEISHU_BOT_ENV_FILE", "/etc/smart-center/feishu-bot.env"))
REMOVE_PREFIXES = (
    "FEISHU_NL_CLOUD_ENABLED=",
    "FEISHU_NL_CLOUD_URL=",
    "FEISHU_NL_CLOUD_MODEL=",
    "FEISHU_NL_CLOUD_API_KEY=",
    "FEISHU_NL_CLOUD_TIMEOUT_SEC=",
    "FEISHU_NL_MODEL_PRIORITY=",
)
SETTINGS = {
    "FEISHU_NL_CLOUD_ENABLED": "1",
    "FEISHU_NL_MODEL_PRIORITY": "cloud_first",
    "SMART_CENTER_NLU_PRIMARY_WAIT_SEC": "18",
    "SMART_CENTER_NLU_COMPARE_WAIT_SEC": "2",
}


def reexec_with_sudo_if_needed() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return
    os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])


def main() -> int:
    reexec_with_sudo_if_needed()
    if not ENV_PATH.exists():
        raise SystemExit(f"env file missing: {ENV_PATH}")
    original = ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = []
    removed = []
    for line in original:
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in REMOVE_PREFIXES):
            removed.append(stripped.split("=", 1)[0])
            continue
        if stripped.startswith("SMART_CENTER_NLU_PRIMARY_WAIT_SEC=") or stripped.startswith("SMART_CENTER_NLU_COMPARE_WAIT_SEC="):
            removed.append(stripped.split("=", 1)[0])
            continue
        kept.append(line)
    if kept and kept[-1].strip():
        kept.append("")
    kept.append("# Cloud/local NLU policy managed by Smart Center runtime config.")
    for key, value in SETTINGS.items():
        kept.append(f"{key}={value}")
    new_text = "\n".join(kept).rstrip() + "\n"
    old_text = "\n".join(original).rstrip() + "\n"
    changed = new_text != old_text
    backup = ""
    if changed:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = ENV_PATH.with_name(f"{ENV_PATH.name}.pre-cloud-runtime-align-{stamp}")
        shutil.copy2(ENV_PATH, backup_path)
        tmp = ENV_PATH.with_suffix(".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(ENV_PATH)
        backup = str(backup_path)
    print(f"changed={changed}")
    print(f"backup={backup}")
    print("removed_keys=" + ",".join(sorted(set(removed))))
    for key in SETTINGS:
        print(f"{key}=set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
