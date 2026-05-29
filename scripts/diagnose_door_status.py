#!/usr/bin/env python3
"""Read-only door status diagnosis for Smart Center operators.

AI_MODULE: door_status_diagnosis_script
AI_PURPOSE: Help operators and local AI understand why door visual state is unreliable.
AI_BOUNDARY: Read-only HTTP diagnostics; never sends open/close/stop commands.
AI_USAGE: python scripts/diagnose_door_status.py --base-url http://127.0.0.1:6899
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests


def _fmt(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "--"


def _get_json(base_url: str, path: str, timeout_sec: float) -> dict[str, Any]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}{path}", timeout=timeout_sec, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path} returned non-object JSON")
        return payload
    except Exception as exc:
        raise RuntimeError(f"读取 {base_url.rstrip('/')}{path} 失败：{exc}") from exc


def build_report(payload: dict[str, Any]) -> str:
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    runtime = payload.get("vision_runtime") if isinstance(payload.get("vision_runtime"), dict) else {}
    calibration = payload.get("calibration") if isinstance(payload.get("calibration"), dict) else {}
    votes = payload.get("camera_votes") if isinstance(payload.get("camera_votes"), dict) else {}
    health = payload.get("vision_service_health") if isinstance(payload.get("vision_service_health"), dict) else {}

    lines = [
        "大门状态诊断",
        f"- 状态: {payload.get('door_status')} / {payload.get('door_status_text') or payload.get('msg') or '--'}",
        f"- 引擎: {payload.get('engine') or '--'}，检测摄像头: {payload.get('detection_camera') or '--'}",
        f"- 置信度: {_fmt(payload.get('confidence'))}，更新时间: {payload.get('updated_at') or '--'}",
        f"- 诊断: {diagnosis.get('reason_code') or '--'} / {diagnosis.get('reason_text') or '--'}",
    ]
    next_steps = [str(item).strip() for item in diagnosis.get("next_steps") or [] if str(item).strip()]
    if next_steps:
        lines.append("- 建议: " + "；".join(next_steps))
    lines.extend(
        [
            f"- 视觉服务: {'可达' if health.get('reachable') else '不可达'} / {health.get('status') or health.get('error') or '--'}",
            f"- 运行态: stable={runtime.get('stable_state') or '--'} candidate={runtime.get('last_candidate') or '--'} unknown_hits={runtime.get('unknown_hits') or 0}",
        ]
    )
    cameras = calibration.get("cameras") if isinstance(calibration.get("cameras"), dict) else {}
    if cameras:
        lines.append("- 参考图:")
        for key, item in cameras.items():
            ready = "ready" if (item or {}).get("ready") else "missing"
            closed = "Y" if (((item or {}).get("closed") or {}).get("exists")) else "N"
            open_ = "Y" if (((item or {}).get("open") or {}).get("exists")) else "N"
            lines.append(f"  - {key}: {ready}, closed={closed}, open={open_}, threshold={item.get('match_threshold')}")
    if votes:
        lines.append("- 视觉投票:")
        for key, vote in votes.items():
            if not isinstance(vote, dict):
                continue
            lines.append(
                f"  - {key}: status={vote.get('status') or '--'}, confidence={_fmt(vote.get('confidence'))}, "
                f"diff_closed={_fmt(vote.get('diff_c'), 0)}, diff_open={_fmt(vote.get('diff_o'), 0)}, "
                f"threshold={_fmt(vote.get('threshold'), 0)}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Smart Center door status diagnosis.")
    parser.add_argument("--base-url", default="http://127.0.0.1:6899", help="Smart Center base URL")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    try:
        payload = _get_json(args.base_url, "/api/door/vision_status", args.timeout)
    except Exception as exc:
        print(f"大门状态诊断失败：{exc}", file=sys.stderr)
        print("建议：如果从 Mac 直连 120 偶发 reset，请在 120 本机执行：python3 scripts/diagnose_door_status.py --base-url http://127.0.0.1:6899", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(build_report(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
