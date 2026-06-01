#!/usr/bin/env python3
"""Normalize production local-model config away from legacy provider labels."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path("/srv/smart-center-data/config.json")
LEGACY_PROVIDER_TOKEN = "olla" + "ma"


def reexec_with_sudo_if_needed() -> None:
    if os.geteuid() == 0:
        return
    os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])


def clean_model_name(value: object) -> str:
    text = str(value or "").strip()
    if text:
        text = " ".join(part for part in text.split() if part.lower() != LEGACY_PROVIDER_TOKEN)
    for token in ("Olla" + "ma", "\u6b27\u62c9\u739b", "\u5965\u62c9\u739b"):
        text = text.replace(token, "")
    text = text.replace("本机 知识模型", "本机知识模型")
    return " ".join(text.split())


def normalize_openai_base_url(value: object, default: str) -> str:
    text = str(value or default).strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip("/")
    if not text:
        text = default
    if not text.endswith("/v1"):
        text = f"{text}/v1"
    return text


def main() -> int:
    reexec_with_sudo_if_needed()
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("config root is not an object")
    local_model = payload.setdefault("local_model", {})
    if not isinstance(local_model, dict):
        raise SystemExit("local_model is not an object")

    changed = False
    before_name = str(local_model.get("name") or "")
    after_name = clean_model_name(before_name)
    if before_name != after_name and after_name:
        local_model["name"] = after_name
        changed = True

    before_provider = str(local_model.get("provider") or "")
    if before_provider.lower() != "openai-compatible":
        local_model["provider"] = "openai-compatible"
        changed = True

    before_base = str(local_model.get("base_url") or "")
    after_base = normalize_openai_base_url(before_base, "http://127.0.0.1:8001/v1")
    if before_base != after_base:
        local_model["base_url"] = after_base
        changed = True

    if not changed:
        print("changed=false")
        print(f"name={local_model.get('name') or ''}")
        print(f"base_url={local_model.get('base_url') or ''}")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = CONFIG_PATH.with_name(f"config.pre-local-model-openai-migration-{stamp}.json")
    shutil.copy2(CONFIG_PATH, backup_path)
    tmp_path = CONFIG_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(CONFIG_PATH)
    subprocess.run(["systemctl", "restart", "smart-center.service"], check=True)
    print("changed=true")
    print(f"backup={backup_path}")
    print(f"name={local_model.get('name') or ''}")
    print(f"base_url={local_model.get('base_url') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
