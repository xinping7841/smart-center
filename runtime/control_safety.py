"""Safety guard for physical device control endpoints."""

# AI_MODULE: control_safety
# AI_PURPOSE: Provide a single opt-in read-only/dry-run/disabled guard for real device actions.
# AI_BOUNDARY: This module decides whether an action may execute; endpoints still own auth and payload validation.
# AI_DATA_FLOW: API route -> guard_device_control() -> block/dry-run payload or real driver call.
# AI_RUNTIME: Normal production mode allows control. Validation can set SMART_CENTER_CONTROL_MODE=dry_run.
# AI_RISK: High. Missing a guard can let unattended validation move real hardware.
# AI_COMPAT: Existing APIs keep their normal payloads when SMART_CENTER_CONTROL_MODE=normal.
# AI_SEARCH_KEYWORDS: dry_run, read_only, disable device control, safety guard, physical control.

from __future__ import annotations

import os
from typing import Any, Mapping

try:
    from flask import has_request_context, request
except Exception:  # pragma: no cover - keeps this importable in non-Flask tools.
    has_request_context = None
    request = None

CONTROL_MODES = {"normal", "read_only", "dry_run", "disabled"}
BLOCKING_MODES = {"read_only", "dry_run", "disabled"}


def _normalize_mode(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"0", "false", "off", "allow", "allowed", "enable", "enabled"}:
        return "normal"
    if text in {"1", "true", "on", "block", "blocked", "disable", "disabled"}:
        return "disabled"
    if text in CONTROL_MODES:
        return text
    return "normal"


def _request_forced_mode() -> str:
    if not has_request_context or not has_request_context() or request is None:
        return "normal"
    header_mode = _normalize_mode(request.headers.get("X-Smart-Center-Control-Mode", ""))
    if header_mode != "normal":
        return header_mode
    if str(request.args.get("dry_run", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return "dry_run"
    return "normal"


def get_effective_control_mode() -> str:
    env_mode = _normalize_mode(
        os.environ.get("SMART_CENTER_CONTROL_MODE")
        or os.environ.get("SMART_CENTER_DEVICE_CONTROL_MODE")
        or ""
    )
    legacy_disable = _normalize_mode(os.environ.get("SMART_CENTER_DISABLE_DEVICE_CONTROL", ""))
    request_mode = _request_forced_mode()
    for mode in ("disabled", "read_only", "dry_run"):
        if mode in {env_mode, legacy_disable, request_mode}:
            return mode
    return "normal"


def guard_device_control(
    action: str,
    target: Any,
    *,
    payload: Mapping[str, Any] | None = None,
    category: str = "device_control",
) -> tuple[dict, int] | None:
    mode = get_effective_control_mode()
    if mode not in BLOCKING_MODES:
        return None

    dry_run = mode == "dry_run"
    response = {
        "success": dry_run,
        "ok": dry_run,
        "blocked": True,
        "dry_run": dry_run,
        "control_mode": mode,
        "error": "device_control_blocked",
        "category": category,
        "action": str(action or ""),
        "target": str(target or ""),
        "msg": _mode_message(mode),
    }
    if payload is not None:
        response["request"] = dict(payload)
    return response, 200 if dry_run else 423


def _mode_message(mode: str) -> str:
    if mode == "dry_run":
        return "control request accepted in dry-run mode; no physical command was sent"
    if mode == "read_only":
        return "control request blocked because the service is in read-only mode"
    return "control request blocked because physical device control is disabled"
