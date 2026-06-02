#!/usr/bin/env python3
"""Configure Smart Center Ark cloud model in production config.json.

AI_MODULE: remote_configure_ark_cloud_model
AI_PURPOSE: Safely add cloud_model runtime config without committing API keys.
AI_BOUNDARY: Edits /srv/smart-center-data/config.json only; does not call device-control APIs.
AI_RISK: Medium, this writes model credentials and affects Feishu natural-language understanding.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


CONFIG_FILE = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")
ARK_MODEL = os.environ.get("ARK_MODEL", "deepseek-v3-2-251201").strip()
ARK_NAME = os.environ.get("ARK_NAME", "Ark 云端增强模型").strip()
ARK_PROVIDER = os.environ.get("ARK_PROVIDER", "ark").strip()
ARK_API_KEY = os.environ.get("ARK_API_KEY", "").strip()


def _as_bool(value: str, default: bool = True) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def main() -> None:
    if not ARK_API_KEY:
        raise SystemExit("ARK_API_KEY environment variable is required")
    payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("config root is not an object")
    local_model = payload.setdefault("local_model", {})
    if not isinstance(local_model, dict):
        raise SystemExit("local_model is not an object")
    cloud_model = local_model.setdefault("cloud_model", {})
    if not isinstance(cloud_model, dict):
        cloud_model = {}
        local_model["cloud_model"] = cloud_model
    cloud_model.update(
        {
            "enabled": _as_bool(os.environ.get("ARK_ENABLED", "1"), True),
            "name": ARK_NAME,
            "provider": ARK_PROVIDER,
            "base_url": ARK_BASE_URL,
            "model": ARK_MODEL,
            "api_key": ARK_API_KEY,
            "timeout_sec": int(os.environ.get("ARK_TIMEOUT_SEC", "180") or 180),
            "temperature": float(os.environ.get("ARK_TEMPERATURE", "0.1") or 0.1),
            "max_tokens": int(os.environ.get("ARK_MAX_TOKENS", "2048") or 2048),
            "use_for_system_summary": _as_bool(os.environ.get("ARK_USE_FOR_SYSTEM_SUMMARY", "1"), True),
            "use_for_nlu_fallback": _as_bool(os.environ.get("ARK_USE_FOR_NLU_FALLBACK", "1"), True),
        }
    )
    backup = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.pre-ark-cloud-model-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(CONFIG_FILE, backup)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_FILE)
    print(
        json.dumps(
            {
                "ok": True,
                "config": str(CONFIG_FILE),
                "backup": str(backup),
                "cloud_model": {
                    "enabled": cloud_model.get("enabled"),
                    "name": cloud_model.get("name"),
                    "provider": cloud_model.get("provider"),
                    "base_url": cloud_model.get("base_url"),
                    "model": cloud_model.get("model"),
                    "api_key_set": bool(cloud_model.get("api_key")),
                    "use_for_system_summary": cloud_model.get("use_for_system_summary"),
                    "use_for_nlu_fallback": cloud_model.get("use_for_nlu_fallback"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
