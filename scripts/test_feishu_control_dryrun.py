#!/usr/bin/env python3
"""Dry-run Feishu natural-language control recognition without touching devices.

AI_MODULE: feishu_control_dryrun
AI_PURPOSE: Batch verify natural-language control parsing, risk level, and confirmation policy.
AI_BOUNDARY: Never call execute_control_command; this script only inspects resolved command objects.
AI_USAGE: python scripts/test_feishu_control_dryrun.py --output /tmp/feishu_control_dryrun.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.feishu_bot import (  # noqa: E402
    HIGH_RISK_CONTROL_TYPES,
    INFERRED_CONTROL_CONFIDENCE,
    LocalSmartCenterClient,
    _control_action_from_text,
    _is_control_request,
)


DEFAULT_CASES = [
    "关闭中控室电柜第8路",
    "打开主电柜8回路",
    "打开门口LED电柜第一回路",
    "打开门口LED电柜第1回路",
    "把第8路关了",
    "第4回路打开",
    "关闭黑S时序电源第1路",
    "黑S时序电源顺序开启",
    "打开庭院灯",
    "把户外灯打开",
    "院子里的灯关掉",
    "打开大门",
    "开门",
    "关闭大门",
    "停止大门",
    "打开一号厅A区灯光",
    "打开前言墙灯",
    "打开机房空调",
    "关闭一号厅空调",
    "投影机开机",
    "关闭沉浸厅投影",
    "唤醒门口LED服务器",
    "门口那台服务器开机",
    "把192.168.80.60唤醒",
    "关闭门口LED服务器",
    "重启12700K",
    "打开那个灯",
    "关一下设备",
]


def _load_cases(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_CASES
    rows = []
    for line in Path(path).read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            rows.append(value)
    return rows or DEFAULT_CASES


def _safe_payload(command: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(command, dict):
        return {}
    return {
        "type": command.get("type"),
        "risk": command.get("risk"),
        "label": command.get("label"),
        "action": command.get("action"),
        "method": command.get("method") or "POST",
        "path": command.get("path"),
        "payload": command.get("payload"),
        "confidence": command.get("confidence") or "high",
        "inference_reason": command.get("inference_reason") or "",
        "message": command.get("message") or "",
    }


def _dry_run_case(client: LocalSmartCenterClient, text: str) -> dict[str, Any]:
    normalized = " ".join(str(text or "").split())
    action = _control_action_from_text(normalized)
    is_control = _is_control_request(normalized)
    command = client.resolve_control_command(normalized) if is_control else None
    safe = _safe_payload(command)
    command_type = str(safe.get("type") or "")
    confidence = str(safe.get("confidence") or "high")
    high_risk = command_type in HIGH_RISK_CONTROL_TYPES or str(safe.get("risk") or "") == "high"
    inferred = confidence in INFERRED_CONTROL_CONFIDENCE
    executable = bool(command and command_type != "error" and not high_risk and not inferred)
    return {
        "schema": "smart_center.feishu_control_dryrun.v1",
        "text": normalized,
        "is_control_request": is_control,
        "recognized_action": action,
        "command": safe,
        "requires_confirmation": bool(command and command_type != "error" and (high_risk or inferred)),
        "would_execute_without_confirmation": executable,
        "dry_run": True,
        "note": "未调用真实控制接口；would_execute_without_confirmation 仅表示生产聊天中该命令当前会直接执行。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run Feishu control natural-language recognition.")
    parser.add_argument("--base-url", default=os.environ.get("SMART_CENTER_BASE_URL", "http://127.0.0.1:6899"))
    parser.add_argument("--cases", help="UTF-8 text file, one test sentence per line")
    parser.add_argument("--output", help="Write JSONL result to this path")
    parser.add_argument("--fail-on-unsafe", action="store_true", help="Exit non-zero if a high-risk/inferred command would execute directly")
    args = parser.parse_args()

    client = LocalSmartCenterClient(str(args.base_url).rstrip("/"))
    rows = [_dry_run_case(client, text) for text in _load_cases(args.cases)]
    result = {
        "schema": "smart_center.feishu_control_dryrun_summary.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "count": len(rows),
        "recognized": sum(1 for row in rows if row["is_control_request"] and row["command"].get("type")),
        "needs_confirmation": sum(1 for row in rows if row["requires_confirmation"]),
        "would_execute_without_confirmation": sum(1 for row in rows if row["would_execute_without_confirmation"]),
    }
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"summary": result, "rows": rows}, ensure_ascii=False, indent=2))
    unsafe = [
        row
        for row in rows
        if row["command"].get("type") in HIGH_RISK_CONTROL_TYPES and row["would_execute_without_confirmation"]
    ]
    return 2 if args.fail_on_unsafe and unsafe else 0


if __name__ == "__main__":
    raise SystemExit(main())
