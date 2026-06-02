"""Natural-language process policy and audit helpers.

AI_MODULE: natural_language_orchestrator
AI_PURPOSE: Keep Feishu and local-model natural-language handling observable
and policy controlled without letting model output execute devices directly.
AI_BOUNDARY: This module does not classify, query, or control devices. It only
normalizes policy and records the process trace used by callers.
AI_DATA_FLOW: Feishu/local-model text -> process trace -> runtime JSONL log ->
AI module process view and future learning review.
AI_RISK: Medium. Logs must show enough execution context for debugging while
avoiding secrets and never becoming an execution authority.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import CONFIG_FILE, RUNTIME_DIR, ensure_directory

DEFAULT_NATURAL_LANGUAGE_POLICY = {
    "feishu_control_enabled": True,
    "feishu_control_require_confirmation": False,
    "record_process_enabled": True,
    "process_log_limit": 200,
}

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return default


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except Exception:
        return default


def normalize_natural_language_policy(raw_policy: Any = None) -> dict[str, Any]:
    """Normalize the persisted natural-language policy block."""

    source = raw_policy if isinstance(raw_policy, dict) else {}
    if isinstance(source.get("natural_language"), dict):
        source = source["natural_language"]
    policy = deepcopy(DEFAULT_NATURAL_LANGUAGE_POLICY)
    policy["feishu_control_enabled"] = _as_bool(
        source.get("feishu_control_enabled"),
        DEFAULT_NATURAL_LANGUAGE_POLICY["feishu_control_enabled"],
    )
    policy["feishu_control_require_confirmation"] = _as_bool(
        source.get("feishu_control_require_confirmation"),
        DEFAULT_NATURAL_LANGUAGE_POLICY["feishu_control_require_confirmation"],
    )
    policy["record_process_enabled"] = _as_bool(
        source.get("record_process_enabled"),
        DEFAULT_NATURAL_LANGUAGE_POLICY["record_process_enabled"],
    )
    policy["process_log_limit"] = _as_int(
        source.get("process_log_limit"),
        DEFAULT_NATURAL_LANGUAGE_POLICY["process_log_limit"],
        20,
        2000,
    )
    return policy


def load_runtime_natural_language_policy() -> dict[str, Any]:
    """Read the latest policy from config.json for standalone Feishu workers."""

    try:
        payload = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    local_model = payload.get("local_model") if isinstance(payload, dict) else {}
    policy = normalize_natural_language_policy(local_model if isinstance(local_model, dict) else {})
    env_override = os.environ.get("SMART_CENTER_FEISHU_CONTROL_ENABLED") or os.environ.get("FEISHU_CONTROL_ENABLED")
    if env_override is not None:
        policy["feishu_control_enabled"] = _as_bool(env_override, policy["feishu_control_enabled"])
    return policy


def natural_language_process_log_file() -> Path:
    runtime_dir = Path(os.environ.get("SMART_CENTER_RUNTIME_DIR", "") or RUNTIME_DIR).expanduser()
    if not runtime_dir.is_absolute():
        runtime_dir = Path.cwd() / runtime_dir
    return runtime_dir.resolve() / "natural_language_process.jsonl"


def _safe_value(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "..."
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"pending_token_created"}:
                safe[key_text] = _safe_value(item, depth + 1)
            elif any(part in key_text.lower() for part in _SENSITIVE_KEY_PARTS):
                safe[key_text] = "***REDACTED***" if item not in (None, "") else ""
            else:
                safe[key_text] = _safe_value(item, depth + 1)
        return safe
    if isinstance(value, list):
        return [_safe_value(item, depth + 1) for item in value[:50]]
    if isinstance(value, tuple):
        return [_safe_value(item, depth + 1) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value) if isinstance(value, str) else value
        if isinstance(text, str) and len(text) > 2000:
            return text[:1997] + "..."
        return text
    return str(value)


def summarize_command_for_process(command: dict[str, Any] | None, *, action_text: str = "") -> dict[str, Any]:
    if not isinstance(command, dict):
        return {}
    action = str(command.get("action") or "")
    display_action = action_text or str(command.get("action_text") or "") or {
        "on": "打开",
        "off": "关闭",
        "open": "打开",
        "close": "关闭",
        "stop": "停止",
        "wake": "唤醒",
        "restart": "重启",
        "shutdown": "关机",
    }.get(action, "")
    return {
        "type": command.get("type") or "",
        "risk": command.get("risk") or "",
        "label": command.get("label") or "",
        "action": action,
        "action_text": display_action,
        "method": command.get("method") or "POST",
        "path": command.get("path") or "",
        "payload": _safe_value(command.get("payload") or {}),
        "confidence": command.get("confidence") or "high",
        "inference_reason": command.get("inference_reason") or "",
        "model_rewritten_text": command.get("model_rewritten_text") or "",
        "model_source": command.get("model_source") or "",
        "model_name": command.get("model_name") or "",
        "model_comparison": _safe_value(command.get("model_comparison") or {}),
        "message": command.get("message") or "",
    }


def describe_control_policy(
    command: dict[str, Any] | None,
    *,
    high_risk_types: set[str],
    inferred_confidences: set[str],
    require_confirmation: bool = False,
) -> dict[str, Any]:
    if not isinstance(command, dict) or command.get("type") == "error":
        return {
            "high_risk": False,
            "inferred": False,
            "requires_confirmation": False,
            "reason": "不可执行或未匹配",
        }
    command_type = str(command.get("type") or "")
    confidence = str(command.get("confidence") or "high")
    high_risk = command_type in high_risk_types or str(command.get("risk") or "") == "high"
    inferred = confidence in inferred_confidences
    reasons = []
    if high_risk:
        reasons.append("高风险设备/动作")
    if inferred:
        reasons.append("模型或规则推断结果")
    if require_confirmation and not reasons:
        reasons.append("飞书控制统一确认策略")
    return {
        "high_risk": high_risk,
        "inferred": inferred,
        "requires_confirmation": bool(high_risk or inferred or require_confirmation),
        "reason": "；".join(reasons) or "普通控制",
    }


class NaturalLanguageTrace:
    """Mutable trace for one Feishu/local-model natural-language turn."""

    def __init__(
        self,
        *,
        source: str,
        text: str,
        actor: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> None:
        self.started = time.time()
        self.event: dict[str, Any] = {
            "schema": "smart_center.natural_language_process.v1",
            "id": uuid.uuid4().hex,
            "source": str(source or "unknown"),
            "text": str(text or ""),
            "actor": _safe_value(actor or {}),
            "policy": normalize_natural_language_policy(policy or {}),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [],
        }

    @property
    def id(self) -> str:
        return str(self.event.get("id") or "")

    def add_step(
        self,
        stage: str,
        title: str,
        *,
        detail: str = "",
        data: Any = None,
        ok: bool | None = None,
    ) -> None:
        step = {
            "stage": str(stage or ""),
            "title": str(title or ""),
            "detail": str(detail or ""),
            "at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_ms": int((time.time() - self.started) * 1000),
        }
        if ok is not None:
            step["ok"] = bool(ok)
        if data is not None:
            step["data"] = _safe_value(data)
        self.event.setdefault("steps", []).append(step)

    def finish(
        self,
        *,
        intent: str = "",
        outcome: str = "",
        reply: str = "",
        command: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        record: bool | None = None,
    ) -> dict[str, Any]:
        event = deepcopy(self.event)
        event["intent"] = str(intent or "")
        event["outcome"] = str(outcome or "")
        event["reply"] = str(reply or "")
        event["elapsed_ms"] = int((time.time() - self.started) * 1000)
        event["finished_at"] = datetime.now().isoformat(timespec="seconds")
        if command is not None:
            event["command"] = summarize_command_for_process(command)
        if extra:
            event["extra"] = _safe_value(extra)
        policy = normalize_natural_language_policy(event.get("policy"))
        should_record = bool(policy.get("record_process_enabled", True)) if record is None else bool(record)
        if should_record:
            append_natural_language_event(event, policy=policy)
        return event


def _prune_log_file(path: Path, keep: int) -> None:
    keep = _as_int(keep, DEFAULT_NATURAL_LANGUAGE_POLICY["process_log_limit"], 20, 2000)
    try:
        if not path.is_file() or path.stat().st_size < 512 * 1024:
            return
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(lines) <= keep:
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception:
        return


def append_natural_language_event(event: dict[str, Any], *, policy: dict[str, Any] | None = None) -> None:
    try:
        log_file = natural_language_process_log_file()
        ensure_directory(log_file.parent)
        keep = int((policy or {}).get("process_log_limit") or DEFAULT_NATURAL_LANGUAGE_POLICY["process_log_limit"])
        _prune_log_file(log_file, keep)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_safe_value(event), ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        return


def list_natural_language_events(limit: int = 50, *, source: str = "") -> list[dict[str, Any]]:
    limit = _as_int(limit, 50, 1, 500)
    source = str(source or "").strip()
    try:
        lines = natural_language_process_log_file().read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if source and str(row.get("source") or "") != source:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows
