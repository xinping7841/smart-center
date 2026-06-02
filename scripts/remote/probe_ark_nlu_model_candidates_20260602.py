#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


CONFIG_PATH = Path(os.environ.get("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json"))


def reexec_with_sudo_if_needed() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return
    os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])


def read_cloud_config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    local_model = payload.get("local_model") if isinstance(payload, dict) else {}
    cloud = local_model.get("cloud_model") if isinstance(local_model, dict) else {}
    return cloud if isinstance(cloud, dict) else {}


def normalize_base_url(value: str) -> str:
    base = str(value or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
    return base


def request_models(base_url: str, api_key: str) -> list[str]:
    try:
        response = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=20,
        )
        if response.status_code >= 400:
            return []
        data = response.json()
    except Exception:
        return []
    rows = data.get("data") if isinstance(data, dict) else []
    ids = []
    for item in rows or []:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return sorted(set(ids))


def test_model(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    started = time.time()
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "只输出 JSON。"},
                    {
                        "role": "user",
                        "content": "把“打开一号厅前言灯”分类为 JSON：{\"intent\":\"control_request\",\"target\":\"一号厅前言灯\",\"action\":\"on\"}",
                    },
                ],
                "temperature": 0,
                "max_tokens": 128,
                "stream": False,
            },
            timeout=35,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        body = response.text[:500]
        if response.status_code >= 400:
            return {"model": model, "ok": False, "status": response.status_code, "elapsed_ms": elapsed_ms, "error": body}
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else []
        content = ""
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message")
            if isinstance(msg, dict):
                content = str(msg.get("content") or "")
        return {"model": model, "ok": True, "status": response.status_code, "elapsed_ms": elapsed_ms, "content": content[:220]}
    except Exception as exc:
        return {"model": model, "ok": False, "status": 0, "elapsed_ms": int((time.time() - started) * 1000), "error": str(exc)[:500]}


def main() -> int:
    reexec_with_sudo_if_needed()
    cloud = read_cloud_config()
    api_key = str(cloud.get("api_key") or "").strip()
    base_url = normalize_base_url(str(cloud.get("base_url") or ""))
    current_model = str(cloud.get("model") or "").strip()
    if not api_key:
        raise SystemExit("cloud_model.api_key is empty")

    listed = request_models(base_url, api_key)
    listed_interesting = [
        item for item in listed if any(part in item.lower() for part in ("doubao", "seed", "deepseek", "kimi", "glm"))
    ][:80]

    candidates = [
        "Doubao-Seed-2.0-pro",
        "doubao-seed-2.0-pro",
        "doubao-seed-2-0-pro",
        "doubao-seed-2-0-pro-260215",
        "DeepSeek-V4-Pro",
        "deepseek-v4-pro",
        "deepseek-v4-pro-260424",
        "DeepSeek-V4-Flash",
        "deepseek-v4-flash",
        current_model,
    ]
    for item in listed_interesting:
        lower = item.lower()
        if "seed" in lower or "v4-pro" in lower or "v4" in lower:
            candidates.append(item)
    unique_candidates = []
    seen = set()
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            unique_candidates.append(item)

    tests = [test_model(base_url, api_key, model) for model in unique_candidates[:18]]
    chosen = next((row["model"] for row in tests if row.get("ok")), "")
    print(json.dumps(
        {
            "ok": bool(chosen),
            "base_url": base_url,
            "current_model": current_model,
            "listed_count": len(listed),
            "listed_interesting": listed_interesting,
            "tests": tests,
            "chosen": chosen,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if chosen else 1


if __name__ == "__main__":
    raise SystemExit(main())
