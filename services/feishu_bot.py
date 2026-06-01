# AI_MODULE: feishu_bot_service
# AI_PURPOSE: Connect the smart center to Feishu by long connection, reply to chat commands, and run scheduled pushes.
# AI_BOUNDARY: Feishu can issue controls through existing Smart Center HTTP APIs only; strong-current cabinets and sequencers require a chat confirmation step.
# AI_DATA_FLOW: Feishu event -> command parser/confirmation -> local smart-center HTTP APIs -> Feishu message API.
# AI_RUNTIME: Run as a standalone process with run_feishu_bot.py or start_feishu_bot.bat.
# AI_RISK: High, chat commands can control real devices; keep target matching conservative and never bypass existing API locks/audit.
# AI_COMPAT: Keep env names FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DEFAULT_CHAT_ID stable.
# AI_SEARCH_KEYWORDS: feishu, lark-oapi, bot, long connection, scheduled push.

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

from services.control_intent_router import ControlIntentRouter
from services.control_learning import ControlLearningStore
from services.control_model_translator import DEFAULT_LOCAL_MODEL_BASE_URL, LocalModelControlTranslator, normalize_openai_base_url, request_local_model_json
from services.device_aliases import build_device_alias_rows, find_alias_rows, normalize_alias_text
from services.natural_language_orchestrator import (
    NaturalLanguageTrace,
    describe_control_policy,
    load_runtime_natural_language_policy,
    summarize_command_for_process,
)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        P2ImMessageReceiveV1,
    )
    from lark_oapi.core.enum import LogLevel
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        CallBackCard,
        CallBackToast,
        P2CardActionTrigger,
        P2CardActionTriggerResponse,
    )
except Exception as exc:  # pragma: no cover - depends on local install
    lark = None
    CreateMessageRequest = None
    CreateMessageRequestBody = None
    P2ImMessageReceiveV1 = Any
    P2CardActionTrigger = Any
    P2CardActionTriggerResponse = Any
    CallBackToast = Any
    CallBackCard = Any
    LogLevel = None
    _LARK_IMPORT_ERROR = exc
else:
    _LARK_IMPORT_ERROR = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path(os.environ.get("SMART_CENTER_RUNTIME_DIR", "/srv/smart-center-data/runtime"))
PENDING_CONTROL_STORE = RUNTIME_ROOT / "feishu_pending_controls.json"
CONTROL_FEEDBACK_STORE = RUNTIME_ROOT / "control_feedback.jsonl"
DEFAULT_BASE_URL = "http://127.0.0.1:5000"
BOT_NAME_HINTS = ("深澜中控AI运维", "中控AI运维", "中控")
MODULE_LABELS = {
    "env": "环境",
    "light": "灯光",
    "power": "电表",
    "proxy": "代理",
    "sequencer": "时序器",
    "server": "服务器",
    "snmp": "网络设备",
    "ups": "UPS",
}
DOOR_WORDS = ("大门", "门磁", "门口", "门状态", "开门", "关门", "门开", "门关")
SERVER_WORDS = ("服务器", "主机", "机器", "电脑", "节点", "显卡", "内存", "磁盘")
SERVER_OFFLINE_WORDS = ("离线", "异常", "不在线", "掉线", "故障")
CONTROL_ACTION_WORDS = (
    "打开",
    "关闭",
    "启动",
    "停止",
    "开机",
    "关机",
    "开门",
    "关门",
    "开灯",
    "关灯",
    "开了",
    "关了",
    "关掉",
    "开启",
    "启用",
    "停用",
    "开一下",
    "关一下",
    "开空调",
    "关空调",
    "控制",
    "重启",
    "执行",
    "下发",
    "唤醒",
    "设置",
    "修改",
    "调整",
    "调温",
    "制冷",
    "制热",
)
CONTROL_STATUS_WORDS = ("状态", "日志", "记录", "历史", "有没有", "是否", "查询", "查看", "显示", "汇总", "吗", "么", "是不是")
CONTROL_CONFIRM_WORDS = ("确认", "确认执行", "执行确认", "执行", "下发", "确认下发", "是的", "确定")
CONTROL_CANCEL_WORDS = ("取消", "别执行", "不要执行", "撤销")
HIGH_RISK_CONTROL_TYPES = {"power", "sequencer"}
PENDING_CONTROL_TTL_SEC = 10 * 60
INFERRED_CONTROL_CONFIDENCE = {"medium", "low"}
SOFTWARE_PLAYBACK_WORDS = (
    "软件播控",
    "播控",
    "素材",
    "播放窗口",
    "显示管理",
    "显示端",
    "传输方式",
    "传输带宽",
    "带宽",
    "缩放",
    "偏移",
    "HVC",
    "H.265",
    "转码",
    "日志提取",
)


@dataclass(frozen=True)
class FeishuBotConfig:
    app_id: str
    app_secret: str
    default_chat_id: str
    smart_center_base_url: str
    push_times: tuple[str, ...]
    request_timeout_sec: float = 4.0
    card_callback_enabled: bool = False
    nl_model_enabled: bool = False
    nl_model_url: str = DEFAULT_LOCAL_MODEL_BASE_URL
    nl_model_name: str = "qwen3:14b"
    nl_model_timeout_sec: float = 8.0
    feishu_control_enabled: bool = False
    feishu_control_require_confirmation: bool = True


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def load_config(env_file: str | Path | None = None) -> FeishuBotConfig:
    if env_file:
        load_dotenv(Path(env_file))
    load_dotenv(PROJECT_ROOT / ".env")
    push_times = tuple(
        item.strip()
        for item in str(os.environ.get("FEISHU_PUSH_TIMES", "") or "").split(",")
        if _valid_hhmm(item.strip())
    )
    try:
        timeout = max(1.0, min(float(os.environ.get("FEISHU_HTTP_TIMEOUT_SEC", "4") or 4), 30.0))
    except Exception:
        timeout = 4.0
    try:
        model_timeout_raw = os.environ.get("FEISHU_NL_MODEL_TIMEOUT_SEC") or os.environ.get("FEISHU_LOCAL_MODEL_TIMEOUT_SEC") or "8"
        model_timeout = max(1.0, min(float(model_timeout_raw or 8), 60.0))
    except Exception:
        model_timeout = 8.0
    nl_model_enabled_raw = os.environ.get("FEISHU_NL_MODEL_ENABLED")
    if nl_model_enabled_raw is None:
        nl_model_enabled_raw = os.environ.get("FEISHU_USE_LOCAL_MODEL", "")
    nl_model_url = (
        os.environ.get("FEISHU_NL_MODEL_URL")
        or os.environ.get("FEISHU_LOCAL_MODEL_BASE_URL")
        or DEFAULT_LOCAL_MODEL_BASE_URL
    )
    nl_model_name = os.environ.get("FEISHU_NL_MODEL_NAME") or os.environ.get("FEISHU_LOCAL_MODEL_NAME") or "qwen3:14b"
    return FeishuBotConfig(
        app_id=str(os.environ.get("FEISHU_APP_ID", "") or "").strip(),
        app_secret=str(os.environ.get("FEISHU_APP_SECRET", "") or "").strip(),
        default_chat_id=str(os.environ.get("FEISHU_DEFAULT_CHAT_ID", "") or "").strip(),
        smart_center_base_url=str(os.environ.get("SMART_CENTER_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/"),
        push_times=push_times,
        request_timeout_sec=timeout,
        card_callback_enabled=str(os.environ.get("FEISHU_CARD_CALLBACK_ENABLED", "") or "").strip().lower() in {"1", "true", "yes", "on"},
        nl_model_enabled=str(nl_model_enabled_raw or "").strip().lower() in {"1", "true", "yes", "on"},
        nl_model_url=normalize_openai_base_url(str(nl_model_url or DEFAULT_LOCAL_MODEL_BASE_URL)),
        nl_model_name=str(nl_model_name or "qwen3:14b").strip(),
        nl_model_timeout_sec=model_timeout,
        feishu_control_enabled=str(os.environ.get("FEISHU_CONTROL_ENABLED", "") or "").strip().lower() in {"1", "true", "yes", "on"},
        feishu_control_require_confirmation=str(os.environ.get("FEISHU_CONTROL_REQUIRE_CONFIRMATION", "1") or "1").strip().lower() in {"1", "true", "yes", "on"},
    )


def _valid_hhmm(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value or ""))


def require_runtime(config: FeishuBotConfig) -> None:
    if _LARK_IMPORT_ERROR is not None:
        raise SystemExit(
            "Missing dependency lark-oapi. Install requirements first, for example: "
            "python -m pip install -r requirements.txt"
        ) from _LARK_IMPORT_ERROR
    if not config.app_id:
        raise SystemExit("Missing FEISHU_APP_ID. Fill .env or process environment before starting.")
    if not config.app_secret:
        raise SystemExit("Missing FEISHU_APP_SECRET. Fill .env or process environment before starting.")


def _json_text(content: str | None) -> str:
    if not content:
        return ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return str(content).strip()
    return str(payload.get("text") or "").strip()


def _strip_mentions(text: str, mentions: list[Any] | None) -> str:
    result = text or ""
    for item in mentions or []:
        key = str(getattr(item, "key", "") or "")
        name = str(getattr(item, "name", "") or "")
        for token in (key, f"@{name}"):
            if token:
                result = result.replace(token, " ")
    for name in BOT_NAME_HINTS:
        result = result.replace(f"@{name}", " ")
    return re.sub(r"\s+", " ", result).strip()


def _aggregate_dashboard_counts(counts: dict[str, Any]) -> dict[str, int]:
    total = 0
    online = 0
    offline = 0
    error = 0
    stale = 0
    for value in (counts or {}).values():
        if not isinstance(value, dict):
            continue
        total += int(value.get("total") or 0)
        online += int(value.get("online") or 0)
        item_offline = int(value.get("offline") or 0)
        item_total = int(value.get("total") or 0)
        item_online = int(value.get("online") or 0)
        offline += max(item_offline, max(0, item_total - item_online))
        error += int(value.get("error") or 0)
        stale += int(value.get("stale") or 0)
    return {
        "total": total,
        "online": online,
        "offline": offline if offline else max(0, total - online),
        "error": error,
        "stale": stale,
    }


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_control_request(text: str) -> bool:
    normalized = str(text or "")
    if not normalized:
        return False
    if _contains_any(normalized, CONTROL_STATUS_WORDS):
        return False
    if _contains_any(normalized, CONTROL_ACTION_WORDS):
        return True
    compact = _normalize_match_text(normalized)
    return bool(re.match(r"^[开关停].{2,}", compact))


def _is_confirmation_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "").strip())
    return normalized in CONTROL_CONFIRM_WORDS


def _is_cancel_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "").strip())
    return normalized in CONTROL_CANCEL_WORDS


def _control_action_from_text(text: str) -> str:
    raw = str(text or "").strip().lower()
    compact = _normalize_match_text(raw)
    if any(word in raw for word in ("升起", "上升", "升幕", "幕布升", "幕布上")):
        return "up"
    if any(word in raw for word in ("降下", "下降", "降幕", "落幕", "幕布降", "幕布下")):
        return "down"
    if any(word in raw for word in ("重启", "restart", "重新启动")):
        return "restart"
    if any(word in raw for word in ("唤醒", "wol", "wake", "开机")) and _contains_any(raw, ("服务器", "主机", "机器", "电脑", "节点", "led", "LED")):
        return "wake"
    if any(word in raw for word in ("关机", "shutdown")) and _contains_any(raw, ("服务器", "主机", "机器", "电脑", "节点", "led", "LED")):
        return "shutdown"
    if any(word in raw for word in ("刷新", "refresh")) and _contains_any(raw, ("服务器", "主机", "机器", "电脑", "节点")):
        return "refresh"
    if any(word in raw for word in ("停止", "停住", "暂停")) and _contains_any(raw, ("幕布", "升降幕", "投影幕")):
        return "stop"
    if any(word in raw for word in ("关机", "关闭", "关灯", "停止", "断开", "熄灭", "off")) or "关" in compact:
        return "off"
    if any(word in raw for word in ("开机", "打开", "开启", "开灯", "启动", "合闸", "制冷", "制热", "on")) or "开" in compact:
        return "on"
    if any(word in raw for word in ("切换", "toggle")):
        return "toggle"
    return ""


def _extract_first_int(text: str) -> int | None:
    raw = str(text or "")
    sanitized = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){1,3}\b", " ", raw)
    sanitized = re.sub(r"\b50\.\d{1,3}\b", " ", sanitized)
    match = re.search(r"(?:第\s*)?(\d+)\s*(?:路|回路|通道|号)", sanitized)
    if not match:
        match = re.search(r"\d+", sanitized)
    if match:
        try:
            return int(match.group(1) if match.lastindex else match.group(0))
        except Exception:
            return None
    zh_map = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    zh_match = re.search(r"第?\s*([一二两三四五六七八九十])\s*(?:路|回路|通道|号)", raw)
    if zh_match:
        return zh_map.get(zh_match.group(1))
    zh_match = re.search(r"第?\s*十([一二三四五六])\s*(?:路|回路|通道|号)", raw)
    if zh_match:
        return 10 + int(zh_map.get(zh_match.group(1), 0))
    try:
        return zh_map.get(raw.strip())
    except Exception:
        return None


def _extract_explicit_channel_int(text: str) -> int | None:
    raw = str(text or "")
    match = re.search(r"(?:第\s*)?(\d+)\s*(?:路|回路|通道)", raw)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    zh_map = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    zh_match = re.search(r"第?\s*([一二两三四五六七八九十])\s*(?:路|回路|通道)", raw)
    if zh_match:
        return zh_map.get(zh_match.group(1))
    zh_match = re.search(r"第?\s*十([一二三四五六])\s*(?:路|回路|通道)", raw)
    if zh_match:
        return 10 + int(zh_map.get(zh_match.group(1), 0))
    return None


def _format_control_action(action: str) -> str:
    return {
        "on": "开启",
        "off": "关闭",
        "toggle": "切换",
        "wake": "唤醒",
        "shutdown": "关机",
        "restart": "重启",
        "refresh": "刷新信息",
        "channel_on": "开启通道",
        "channel_off": "关闭通道",
        "sequence_on": "顺序开启",
        "sequence_off": "顺序关闭",
        "all_on": "全部开启",
        "all_off": "全部关闭",
    }.get(str(action or ""), str(action or "控制"))


def _score_item_by_query(query: str, item: dict[str, Any], fields: tuple[str, ...] = ("name", "id")) -> tuple[int, list[str]]:
    normalized_query = _normalize_match_text(query)
    if not normalized_query or not isinstance(item, dict):
        return 0, []
    best = 0
    reasons: list[str] = []
    for field in fields:
        value = item.get(field)
        if value in (None, ""):
            continue
        normalized_value = _normalize_match_text(value)
        if not normalized_value:
            continue
        if normalized_value == normalized_query:
            best = max(best, 100)
            reasons.append(f"{field}完全匹配")
        elif normalized_value in normalized_query:
            score = 80 + min(len(normalized_value), 19)
            best = max(best, score)
            reasons.append(f"包含{field}:{value}")
        elif len(normalized_query) >= 3 and normalized_query in normalized_value:
            score = 55 + min(len(normalized_query), 19)
            best = max(best, score)
            reasons.append(f"命中{field}:{value}")
    return best, reasons[:3]


def _score_items_by_query(
    query: str,
    items: list[dict[str, Any]],
    fields: tuple[str, ...] = ("name", "id"),
) -> list[tuple[int, dict[str, Any], list[str]]]:
    normalized_query = _normalize_match_text(query)
    if not normalized_query:
        return []
    scored: list[tuple[int, dict[str, Any], list[str]]] = []
    for item in items:
        best, reasons = _score_item_by_query(query, item, fields)
        if best:
            scored.append((best, item, reasons))
    scored.sort(key=lambda row: row[0], reverse=True)
    return scored


def _match_items_by_query(query: str, items: list[dict[str, Any]], fields: tuple[str, ...] = ("name", "id")) -> list[dict[str, Any]]:
    return [item for _score, item, _reasons in _score_items_by_query(query, items, fields)]


def _fmt_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    formatted = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    if "." not in formatted and digits == 0:
        formatted = f"{number:.0f}"
    return formatted or "0"


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _device_name(device: dict[str, Any]) -> str:
    return str(
        device.get("display_name")
        or device.get("custom_name")
        or device.get("name")
        or device.get("hostname")
        or device.get("ip")
        or device.get("id")
        or "未命名设备"
    )


def _normalize_match_text(value: Any) -> str:
    return normalize_alias_text(value)


def _machine_group(machine: dict[str, Any]) -> str:
    return str(machine.get("asset_group") or "").strip() or "未分组"


def _machine_status(machine: dict[str, Any]) -> dict[str, Any]:
    return machine.get("status") if isinstance(machine.get("status"), dict) else {}


def _machine_metric_value(machine: dict[str, Any], metric: str) -> float | None:
    status = _machine_status(machine)
    if metric == "cpu":
        return _to_float(status.get("cpu_percent"))
    if metric == "mem":
        return _to_float(status.get("mem_percent"))
    if metric == "disk":
        return _to_float(status.get("disk_percent"))
    if metric in {"gpu_temp", "gpu_util"}:
        values = []
        for gpu in status.get("gpu_list") or []:
            if not isinstance(gpu, dict):
                continue
            key = "temp" if metric == "gpu_temp" else "util_percent"
            number = _to_float(gpu.get(key))
            if number is not None:
                values.append(number)
        return max(values) if values else None
    return None


def _machine_gpu_text(machine: dict[str, Any], detail: bool = False) -> str:
    gpu_list = _machine_status(machine).get("gpu_list")
    if not isinstance(gpu_list, list) or not gpu_list:
        return ""
    parts = []
    for gpu in gpu_list[:2]:
        if not isinstance(gpu, dict):
            continue
        name = str(gpu.get("name") or "GPU").strip()
        if detail and len(name) > 28:
            name = name[:28] + "..."
        elif not detail:
            name = name.split("[")[0].replace("NVIDIA GeForce", "").replace("VGA compatible controller:", "").strip() or "GPU"
            if len(name) > 18:
                name = name[:18] + "..."
        temp = _fmt_number(gpu.get("temp"), 0)
        util = _fmt_number(gpu.get("util_percent"), 0)
        parts.append(f"{name} {temp}°C/{util}%")
    if len(gpu_list) > 2:
        parts.append(f"+{len(gpu_list) - 2}GPU")
    return "GPU " + "；".join(parts) if parts else ""


def _server_like_query(keyword: str, lowered: str) -> bool:
    if _contains_any(keyword, SERVER_WORDS):
        return True
    if any(token in lowered for token in ("cpu", "gpu", "node-")):
        return True
    return bool(re.search(r"(?:^|[^\d])(?:\d{1,3}\.){3}\d{1,3}(?:$|[^\d])", keyword))


def _query_mentions_machine_field(query: str, normalized_query: str, field: Any, field_name: str = "") -> bool:
    raw = str(field or "").strip()
    if not raw:
        return False
    if field_name == "ip" or re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", raw):
        return bool(re.search(rf"(?<![\d.]){re.escape(raw)}(?![\d.])", query))
    normalized = _normalize_match_text(raw)
    if not normalized:
        return False
    if field_name == "mac" or re.fullmatch(r"[0-9a-fA-F:\-]{11,17}", raw):
        return bool(re.search(rf"(?<![0-9a-f]){re.escape(normalized)}(?![0-9a-f])", normalized_query))
    if len(normalized) < 2:
        return False
    if normalized in normalized_query:
        return True
    if len(normalized_query) >= 3 and normalized_query in normalized:
        return True
    return False


def _normalize_intent(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "status": "overview",
        "system_status": "overview",
        "device_status": "overview",
        "offline": "offline_devices",
        "abnormal": "offline_devices",
        "energy": "energy_overview",
        "meter": "energy_overview",
        "current": "current_collector",
        "current_status": "current_collector",
        "server": "server_status",
        "machine": "server_status",
        "door": "door_status",
        "contact": "door_status",
        "env": "environment_status",
        "environment": "environment_status",
        "hvac": "hvac_status",
        "light": "lighting_status",
        "lighting": "lighting_status",
        "automation": "automation_status",
        "logs": "event_logs",
        "log": "event_logs",
        "event": "event_logs",
        "snmp": "snmp_status",
        "ups": "ups_status",
        "proxy": "proxy_status",
        "model": "local_model_status",
        "local_model": "local_model_status",
        "control": "control_request",
        "forbidden_control": "control_request",
    }
    return aliases.get(text, text)


class LocalModelIntentClassifier:
    INTENTS = (
        "overview",
        "offline_devices",
        "energy_overview",
        "energy_history",
        "current_collector",
        "server_status",
        "door_status",
        "environment_status",
        "hvac_status",
        "lighting_status",
        "lighting_logs",
        "automation_status",
        "automation_logs",
        "event_logs",
        "snmp_status",
        "ups_status",
        "proxy_status",
        "local_model_status",
        "control_request",
        "forbidden_control",
        "unknown",
    )

    def __init__(self, base_url: str, model: str, timeout_sec: float = 8.0) -> None:
        self.base_url = normalize_openai_base_url(base_url)
        self.model = model or "qwen3:14b"
        self.timeout_sec = timeout_sec

    def classify(self, text: str) -> dict[str, Any] | None:
        prompt = (
            "你是中控飞书机器人的意图分类器，只输出 JSON，不要输出解释。\n"
            "当前允许查询，也允许识别控制请求；真实控制由飞书/中控安全链路负责权限、审计和二次确认。\n"
            "可选 intent："
            + ", ".join(self.INTENTS)
            + "\n"
            "如果用户要求开关、控制、重启、关机、唤醒、下发、执行、修改配置、调空调、执行场景，intent 必须是 control_request。\n"
            "如果是查询日志或历史记录，优先选择 event_logs、automation_logs、lighting_logs 或 energy_history。\n"
            "返回格式：{\"intent\":\"...\",\"query\":\"原问题\",\"allowed\":true,\"reason\":\"\"}\n"
            f"用户问题：{text}"
        )
        try:
            parsed = request_local_model_json(self.base_url, self.model, prompt, self.timeout_sec)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        intent = _normalize_intent(parsed.get("intent"))
        if intent not in self.INTENTS:
            return None
        parsed["intent"] = intent
        parsed["query"] = str(parsed.get("query") or text).strip()
        return parsed


class LocalSmartCenterClient:
    def __init__(self, base_url: str, timeout_sec: float = 4.0) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_sec = timeout_sec

    def get_json(self, path: str, timeout_sec: float | None = None) -> tuple[bool, Any]:
        try:
            response = requests.get(
                f"{self.base_url}{path}",
                timeout=timeout_sec if timeout_sec is not None else self.timeout_sec,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return True, response.json()
        except Exception as exc:
            return False, str(exc)

    def post_json(self, path: str, payload: dict[str, Any] | None = None, timeout_sec: float | None = None) -> tuple[bool, Any]:
        try:
            response = requests.post(
                f"{self.base_url}{path}",
                json=payload or {},
                timeout=timeout_sec if timeout_sec is not None else self.timeout_sec,
                headers={"Accept": "application/json"},
            )
            try:
                body = response.json()
            except Exception:
                body = response.text
            if response.status_code >= 400:
                return False, body
            return True, body
        except Exception as exc:
            return False, str(exc)

    def _config_section(self, key: str) -> list[dict[str, Any]]:
        try:
            from config import CONFIG

            rows = CONFIG.get(key, [])
            return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
        except Exception:
            return []

    def _device_alias_rows(self) -> list[dict[str, Any]]:
        try:
            from config import CONFIG

            return build_device_alias_rows(CONFIG)
        except Exception:
            return []

    def _summarize_api_result(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        message = payload.get("msg") or payload.get("message") or payload.get("response") or payload.get("log")
        if message:
            return str(message)
        if payload.get("last_result") and isinstance(payload.get("last_result"), dict):
            result = payload.get("last_result") or {}
            status = result.get("status") or payload.get("status") or ""
            delay = result.get("ack_delay_ms")
            if status:
                return f"网关已确认 {status}{f'，延迟 {delay}ms' if delay is not None else ''}"
        if payload.get("state") and isinstance(payload.get("state"), dict):
            state = payload.get("state") or {}
            status = state.get("status") or state.get("last_response") or ""
            if status:
                return f"状态 {status}"
        if payload.get("success") is not None:
            status = str(payload.get("status") or payload.get("state") or "").strip()
            return f"成功{f'，状态 {status}' if status and len(status) < 32 else ''}" if payload.get("success") else "失败"
        if payload.get("ok") is not None:
            status = str(payload.get("status") or payload.get("state") or "").strip()
            return f"成功{f'，状态 {status}' if status and len(status) < 32 else ''}" if payload.get("ok") else "失败"
        return "已返回结果"

    def _request_target_status(self, command: dict[str, Any]) -> tuple[bool, Any]:
        path = str(command.get("status_path") or "").strip()
        if not path:
            return False, ""
        return self.get_json(path, timeout_sec=float(command.get("status_timeout_sec") or 4.0))

    def _finish_control_result(self, ok: bool, payload: Any, label: str, action: str) -> str:
        status = "成功" if ok else "失败"
        detail = self._summarize_api_result(payload)
        return f"{label} {_format_control_action(action)}{status}：{detail}"

    def control_state_text(self, command: dict[str, Any] | None) -> str:
        if not isinstance(command, dict):
            return ""
        if command.get("type") == "power":
            payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
            cab = payload.get("cab")
            ch = payload.get("ch")
            if cab is None or ch is None:
                return ""
            ok, status = self.get_json(f"/api/status?cab={int(cab)}", timeout_sec=4.0)
            if not ok or not isinstance(status, dict):
                return f"当前状态读取失败：{status}"
            if int(status.get("cab_idx") or status.get("cabinet_idx") or 0) != int(cab):
                return "当前状态读取成功，但返回的不是目标电柜。"
            channels = status.get("channels_1_4") or status.get("channels") or []
            state = "--"
            try:
                state = "开启" if bool(channels[int(ch) - 1]) else "关闭"
            except Exception:
                state = "--"
            updated = status.get("_last_success_at") or status.get("updated_at") or "--"
            return f"当前状态：第{int(ch)}路 {state}，更新时间 {updated}。"
        if command.get("type") in {"light", "light_batch"}:
            payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
            device_id = payload.get("device_id")
            if not device_id and command.get("type") == "light_batch":
                commands = [item for item in payload.get("commands") or [] if isinstance(item, dict)]
                first_payload = commands[0].get("payload") if commands and isinstance(commands[0].get("payload"), dict) else {}
                device_id = first_payload.get("device_id")
            channel = payload.get("channel")
            if not device_id:
                return ""
            ok, status = self.get_json("/api/light/status", timeout_sec=4.0)
            if not ok or not isinstance(status, dict):
                return f"当前灯光状态读取失败：{status}"
            channels = (status.get("channels") or {}).get(str(device_id)) if isinstance(status.get("channels"), dict) else None
            if channel:
                try:
                    state = "开启" if bool(channels[int(channel) - 1]) else "关闭"
                except Exception:
                    state = "--"
                return f"当前状态：{command.get('label') or '灯光'} {state}。"
            if isinstance(channels, list):
                states = "、".join(f"{idx + 1}:{'开' if value else '关'}" for idx, value in enumerate(channels))
                return f"当前状态：{states}。"
        if command.get("type") == "node_red":
            ok, status = self._request_target_status(command)
            if ok and isinstance(status, dict):
                state = status.get("status") or status.get("state") or status.get("power") or status.get("last_response")
                if state is not None:
                    return f"当前状态：{state}。"
        return ""

    def _ambiguous_control_text(self, kind: str, matches: list[dict[str, Any]]) -> str:
        rows = []
        for item in matches[:8]:
            name = _device_name(item)
            item_id = item.get("id") or item.get("mac") or item.get("device_id") or ""
            rows.append(f"- {name}{f'（{item_id}）' if item_id else ''}")
        return "\n".join([f"匹配到多个{kind}，请说得更具体一点：", *rows])

    def _not_found_control_text(self, kind: str, hint: str = "") -> str:
        suffix = f"\n{hint}" if hint else ""
        return f"没有匹配到要控制的{kind}，请带上完整名称、编号或 IP。{suffix}"

    def _mark_inferred(self, command: dict[str, Any] | None, confidence: str, reason: str) -> dict[str, Any] | None:
        if not isinstance(command, dict) or command.get("type") == "error":
            return command
        command = dict(command)
        command["confidence"] = confidence
        command["inference_reason"] = reason
        return command

    def resolve_control_command(self, text: str) -> dict[str, Any] | None:
        return self.resolve_control_command_with_translator(text, translator=None)

    def resolve_control_command_with_translator(self, text: str, translator: LocalModelControlTranslator | None = None) -> dict[str, Any] | None:
        action = _control_action_from_text(text)
        if not action:
            return None
        router = ControlIntentRouter(self._device_alias_rows())
        routed = router.route(
            text,
            action,
            door=self._resolve_door_control,
            sequencer=self._resolve_sequencer_control,
            power=self._resolve_power_control,
            hvac=self._resolve_hvac_control,
            projector=self._resolve_projector_control,
            node_red=self._resolve_node_red_control,
            light=self._resolve_light_control,
            server=self._resolve_server_control,
            screen=self._resolve_screen_control,
            custom=self._resolve_control_center_control,
            infer=self._infer_control_command,
        )
        if routed.command is not None or routed.stop:
            return routed.command
        learning = ControlLearningStore(CONTROL_FEEDBACK_STORE)
        learned = None if learning.rejected_recently(text) else learning.suggest(text)
        if learned:
            return learned
        if translator:
            translated = translator.translate(text, self._device_alias_rows())
            if translated and translated.rewritten_text and normalize_alias_text(translated.rewritten_text) != normalize_alias_text(text):
                translated_action = _control_action_from_text(translated.rewritten_text)
                if translated_action:
                    translated_route = router.route(
                        translated.rewritten_text,
                        translated_action,
                        door=self._resolve_door_control,
                        sequencer=self._resolve_sequencer_control,
                        power=self._resolve_power_control,
                        hvac=self._resolve_hvac_control,
                        projector=self._resolve_projector_control,
                        node_red=self._resolve_node_red_control,
                        light=self._resolve_light_control,
                        server=self._resolve_server_control,
                        screen=self._resolve_screen_control,
                        custom=self._resolve_control_center_control,
                        infer=self._infer_control_command,
                    )
                    if translated_route.command and translated_route.command.get("type") != "error":
                        command = self._mark_inferred(
                            translated_route.command,
                            "medium" if translated.confidence < 0.86 else "high",
                            f"本地模型将“{text}”转译为“{translated.rewritten_text}”。{translated.reason}",
                        )
                        if command:
                            command["model_rewritten_text"] = translated.rewritten_text
                        return command
        normalized = _normalize_match_text(text)
        if normalized in {"开", "关", "打开", "关闭", "开启"}:
            return None
        return None

    def _infer_modules_from_aliases(self, text: str) -> set[str]:
        matches = find_alias_rows(text, self._device_alias_rows())
        modules: set[str] = set()
        for row in matches[:5]:
            module = str(row.get("module") or "")
            if module and row.get("control_capability"):
                modules.add(module)
        return modules

    def _infer_control_command(self, text: str, action: str, normalized: str) -> dict[str, Any] | None:
        if normalized in {"开", "关", "打开", "关闭", "开启"}:
            return None
        channel = _extract_explicit_channel_int(text)
        if channel and action in {"on", "off", "toggle"}:
            if re.search(r"(?:第)?\d+\s*(?:路|回路|通道)", text):
                command = self._resolve_power_control(text, action, allow_single_cabinet_inference=True)
                if command and command.get("type") != "error":
                    reason = f"句子包含“第{channel}路/回路”和“{_format_control_action(action)}”，当前可推断为强电柜回路控制。"
                    return self._mark_inferred(command, "medium", reason)
        if action in {"on", "off", "toggle"} and _contains_any(text, ("户外", "庭院", "院子", "外墙", "室外")):
            node_red = self._resolve_node_red_control(text, action, infer_outdoor_light=True)
            if node_red:
                return self._mark_inferred(node_red, "medium", "句子包含户外/庭院语义，匹配到 Node-RED 网关里的户外灯光设备。")
        if action in {"wake", "shutdown", "restart", "refresh"}:
            server = self._resolve_server_control(text, action, allow_loose=True)
            if server and server.get("type") != "error":
                return self._mark_inferred(server, "medium", "句子像是在控制服务器，我按名称、IP、备注或分组做了近似匹配。")
        return None

    def execute_control_command(self, command: dict[str, Any]) -> str:
        if not isinstance(command, dict):
            return "控制命令格式无效。"
        if command.get("type") == "light_batch":
            return self._execute_batch_control_command(command)
        path = str(command.get("path") or "")
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        method = str(command.get("method") or "POST").upper()
        action = str(command.get("action") or "")
        label = str(command.get("label") or "设备")
        timeout_sec = float(command.get("timeout_sec") or 8.0)
        if method == "GET":
            ok, result = self.get_json(path, timeout_sec=timeout_sec)
        else:
            ok, result = self.post_json(path, payload, timeout_sec=timeout_sec)
        state_text = self.control_state_text(command)
        suffix = f"\n{state_text}" if state_text else ""
        return self._finish_control_result(ok, result, label, action) + suffix

    def _execute_batch_control_command(self, command: dict[str, Any]) -> str:
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        commands = [item for item in payload.get("commands") or [] if isinstance(item, dict)]
        if not commands:
            return "批量控制命令为空。"
        ok_count = 0
        failures: list[str] = []
        for item in commands:
            path = str(item.get("path") or "")
            item_payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            label = str(item.get("label") or path or "子命令")
            ok, result = self.post_json(path, item_payload, timeout_sec=6.0)
            if ok and isinstance(result, dict) and result.get("success", result.get("ok", True)):
                ok_count += 1
            else:
                failures.append(f"{label}: {self._summarize_api_result(result)}")
        state_text = self.control_state_text(command)
        suffix = f"\n{state_text}" if state_text else ""
        if failures:
            return f"{command.get('label') or '批量灯光'} {_format_control_action(command.get('action'))}部分成功：{ok_count}/{len(commands)}。\n" + "\n".join(failures[:4]) + suffix
        return f"{command.get('label') or '批量灯光'} {_format_control_action(command.get('action'))}成功：{ok_count}/{len(commands)}。" + suffix

    def _resolve_door_control(self, text: str, action: str) -> dict[str, Any] | None:
        if not _contains_any(text, ("大门", "门禁", "开门", "关门")):
            return None
        raw = str(text or "")
        door_action = ""
        if _contains_any(raw, ("停止", "停门", "暂停")):
            door_action = "stop"
        elif _contains_any(raw, ("关门", "关闭大门", "关闭门禁")) or action == "off":
            door_action = "close"
        elif _contains_any(raw, ("开门", "打开大门", "开启大门", "打开门禁", "开启门禁")) or action == "on":
            door_action = "open"
        if not door_action:
            return {"type": "error", "message": "门禁控制需要说明动作：打开大门、关闭大门或停止大门。"}
        return {
            "type": "door",
            "risk": "normal",
            "label": "大门门禁",
            "path": f"/door_control/{door_action}",
            "payload": {},
            "action": door_action,
            "method": "GET",
            "timeout_sec": 8.0,
        }

    def _resolve_hvac_control(self, text: str, action: str) -> dict[str, Any] | None:
        if action in {"shutdown", "restart", "wake", "refresh"}:
            return None
        alias_matches = find_alias_rows(text, self._device_alias_rows(), module="hvac")
        hvac_alias = next((row for row in alias_matches if row.get("device_type") == "hvac"), None)
        if not hvac_alias and _contains_any(text, ("中控室空调", "机房空调", "中控空调")):
            for row in self._device_alias_rows():
                if row.get("module") == "hvac" and row.get("device_type") == "hvac" and _contains_any(str(row.get("name") or ""), ("机房", "中控")):
                    hvac_alias = row
                    break
        ok, payload = self.get_json("/api/hvac/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            if hvac_alias:
                api_action = "power_on" if action in {"on", "toggle"} else "power_off"
                return {
                    "type": "hvac",
                    "risk": "normal",
                    "label": str(hvac_alias.get("name") or "空调"),
                    "path": "/api/hvac/control",
                    "payload": {"device_id": hvac_alias.get("device_id"), "action": api_action},
                    "action": "on" if api_action == "power_on" else "off",
                    "confidence": "medium",
                    "inference_reason": f"空调状态接口暂不可用，已按配置别名匹配到 {hvac_alias.get('name')}",
                }
            return {"type": "error", "message": f"空调接口暂时不可用：{payload}"}
        devices = []
        for device_id, item in payload.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("id", device_id)
                devices.append(row)
        matches = _match_items_by_query(text, devices, ("name", "id"))
        if hvac_alias:
            matches = [item for item in devices if str(item.get("id")) == str(hvac_alias.get("device_id"))]
        if not matches and len(devices) == 1:
            matches = devices
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("空调", matches)}
        if not matches:
            return {"type": "error", "message": self._not_found_control_text("空调", "例如：打开机房空调、关闭一号厅空调")}
        item = matches[0]
        api_action = "power_on" if action in {"on", "toggle"} else "power_off"
        return {
            "type": "hvac",
            "risk": "normal",
            "label": _device_name(item),
            "path": "/api/hvac/control",
            "payload": {"device_id": item.get("id"), "action": api_action},
            "action": "on" if api_action == "power_on" else "off",
        }

    def _resolve_node_red_control(self, text: str, action: str, infer_outdoor_light: bool = False) -> dict[str, Any] | None:
        ok, payload = self.get_json("/api/node-red/devices?include_unavailable=1&refresh=0", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return None
        devices = [item for item in payload.get("devices") or [] if isinstance(item, dict)]
        if not devices:
            return None
        matches = _match_items_by_query(text, devices, ("device_name", "device_id", "name", "id"))
        if not matches and infer_outdoor_light:
            outdoor_words = ("庭院", "户外", "室外", "院子", "外墙")
            matches = [
                item
                for item in devices
                if _contains_any(
                    f"{item.get('device_name', '')}{item.get('name', '')}{item.get('device_id', '')}{item.get('id', '')}",
                    outdoor_words,
                )
            ]
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("Node-RED设备", matches)}
        if not matches:
            return None
        item = matches[0]
        normalized_action = "on" if action in {"on", "toggle"} else "off"
        device_id = item.get("device_id") or item.get("id")
        return {
            "type": "node_red",
            "risk": "normal",
            "label": item.get("device_name") or _device_name(item),
            "path": f"/api/node-red/device/{requests.utils.quote(str(device_id), safe='')}/control",
            "status_path": f"/api/node-red/device/{requests.utils.quote(str(device_id), safe='')}/status",
            "payload": {"action": normalized_action},
            "action": normalized_action,
        }

    def _resolve_light_control(self, text: str, action: str) -> dict[str, Any] | None:
        if action not in {"on", "off", "toggle"}:
            return None
        alias_matches = find_alias_rows(text, self._device_alias_rows(), module="light")
        channel_alias = next((row for row in alias_matches if row.get("device_type") == "light_channel"), None)
        controller_alias = next((row for row in alias_matches if row.get("device_type") == "light_controller"), None)
        wants_all = _contains_any(text, ("所有灯", "全部灯", "全灯", "所有灯光", "全部灯光", "全开", "全关"))
        ok, payload = self.get_json("/api/light/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            if wants_all and (controller_alias or channel_alias):
                device_id = (controller_alias or channel_alias).get("device_id")
                cfg = next((item for item in self._config_section("light_devices") if str(item.get("id")) == str(device_id)), None)
                if cfg:
                    channel_count = int(cfg.get("channel_count") or cfg.get("channels") or len(cfg.get("channels_config") or []) or 0)
                    if channel_count > 0:
                        target = action == "on"
                        return self._build_light_batch_command(str(device_id), str(cfg.get("name") or device_id), channel_count, target)
            if channel_alias:
                target = action == "on"
                return {
                    "type": "light",
                    "risk": "normal",
                    "label": str(channel_alias.get("name") or "灯光通道"),
                    "path": "/api/light/control",
                    "payload": {"type": "single", "device_id": channel_alias.get("device_id"), "channel": channel_alias.get("channel"), "is_open": target},
                    "action": "on" if target else "off",
                    "confidence": "medium",
                    "inference_reason": f"灯光状态接口暂不可用，已按配置别名匹配到 {channel_alias.get('name')}",
                }
            return {"type": "error", "message": f"灯光接口暂时不可用：{payload}"}
        extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
        channels = payload.get("channels") if isinstance(payload.get("channels"), dict) else {}
        devices = []
        for device_id, extra in extras.items():
            row = dict(extra if isinstance(extra, dict) else {})
            row["id"] = device_id
            row["name"] = row.get("name") or device_id
            devices.append(row)
        matches = _match_items_by_query(text, devices, ("name", "id"))
        if channel_alias:
            matches = [item for item in devices if str(item.get("id")) == str(channel_alias.get("device_id"))]
        elif controller_alias and not matches:
            matches = [item for item in devices if str(item.get("id")) == str(controller_alias.get("device_id"))]
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("灯光设备", matches)}
        if not matches:
            hint_rows = [row.get("name") for row in self._device_alias_rows() if row.get("module") == "light" and row.get("device_type") == "light_channel"]
            hint = "可尝试：" + "、".join(str(x) for x in hint_rows[:8]) if hint_rows else "如果是庭院灯，请说：打开庭院灯 / 关闭庭院灯"
            return {"type": "error", "message": self._not_found_control_text("灯光设备", hint)}
        item = matches[0]
        states = channels.get(str(item.get("id"))) if isinstance(channels, dict) else None
        if wants_all:
            if not isinstance(states, list) or not states:
                return {"type": "error", "message": f"{_device_name(item)} 暂未读到通道状态，不能安全执行整区灯光控制。"}
            target = action == "on"
            return self._build_light_batch_command(str(item.get("id")), _device_name(item), len(states), target)
        channel = int(channel_alias.get("channel") or 0) if channel_alias else _extract_first_int(text)
        if channel is None and isinstance(states, list) and len(states) == 1:
            channel = 1
        if channel is None:
            channel_hints = [row.get("name") for row in self._device_alias_rows() if row.get("module") == "light" and str(row.get("device_id")) == str(item.get("id")) and row.get("device_type") == "light_channel"]
            suffix = f"可说：{ '、'.join(str(x) for x in channel_hints[:6]) }" if channel_hints else "例如：打开灯光1路。庭院灯可直接说打开庭院灯。"
            return {"type": "error", "message": f"灯光控制需要指定通道。{suffix}"}
        target = not bool(states[channel - 1]) if action == "toggle" and isinstance(states, list) and 0 < channel <= len(states) else action == "on"
        label = str(channel_alias.get("name") or f"{_device_name(item)} {channel}路") if channel_alias else f"{_device_name(item)} {channel}路"
        return {
            "type": "light",
            "risk": "normal",
            "label": label,
            "path": "/api/light/control",
            "payload": {"type": "single", "device_id": item.get("id"), "channel": channel, "is_open": target},
            "action": "on" if target else "off",
        }

    def _build_light_batch_command(self, device_id: str, device_name: str, channel_count: int, target: bool) -> dict[str, Any]:
        channel_count = max(1, min(int(channel_count or 0), 32))
        cfg = next((item for item in self._config_section("light_devices") if str(item.get("id")) == str(device_id)), None)
        if cfg and str(cfg.get("name") or "").strip():
            device_name = str(cfg.get("name") or "").strip()
        return {
            "type": "light_batch",
            "risk": "normal",
            "label": f"{device_name} 全部灯光",
            "path": "/api/feishu/control/batch",
            "payload": {
                "device_id": device_id,
                "commands": [
                    {
                        "path": "/api/light/control",
                        "payload": {"type": "single", "device_id": device_id, "channel": idx + 1, "is_open": target},
                        "label": f"{device_name} 第{idx + 1}路",
                    }
                    for idx in range(channel_count)
                ],
            },
            "action": "on" if target else "off",
            "timeout_sec": max(12.0, channel_count * 5.0),
        }

    def _resolve_screen_control(self, text: str, action: str) -> dict[str, Any] | None:
        if action not in {"up", "down", "stop", "on", "off"}:
            return None
        screens = self._config_section("screens")
        matches = _match_items_by_query(text, screens, ("name", "id", "ip"))
        if not matches and len(screens) == 1:
            matches = screens
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("幕布", matches)}
        if not matches:
            return {"type": "error", "message": self._not_found_control_text("幕布", "例如：升起一厅A区幕布、停止幕布、降下幕布")}
        screen = matches[0]
        screen_action = "up" if action == "on" else ("down" if action == "off" else action)
        wanted_names = {
            "up": ("上升", "升起", "up"),
            "down": ("下降", "降下", "down"),
            "stop": ("停止", "暂停", "stop"),
        }.get(screen_action, ())
        command = None
        for item in screen.get("commands") or []:
            if not isinstance(item, dict):
                continue
            haystack = f"{item.get('action', '')} {item.get('name', '')}".lower()
            if any(str(word).lower() in haystack for word in wanted_names):
                command = {
                    "name": item.get("name") or screen_action,
                    "payload": item.get("payload") or "",
                    "format": item.get("format") or "hex",
                    "action": item.get("action") or screen_action,
                }
                break
        if not command:
            return {"type": "error", "message": f"未找到 {_device_name(screen)} 的幕布{_format_control_action(screen_action)}命令。"}
        return {
            "type": "screen",
            "risk": "normal",
            "label": _device_name(screen),
            "path": "/api/screen/control",
            "payload": {"screen_id": screen.get("id"), "command": command},
            "action": screen_action,
            "timeout_sec": 10.0,
        }

    def _resolve_control_center_control(self, text: str, action: str) -> dict[str, Any] | None:
        if action not in {"on", "off", "toggle"}:
            return None
        try:
            from config import CONFIG
            from control_center_core import normalize_control_center

            config = normalize_control_center(CONFIG.get("control_center"), CONFIG.get("custom_devices"))
        except Exception as exc:
            return {"type": "error", "message": f"协议控制配置暂时不可用：{exc}"}
        targets = [item for item in config.get("target_groups") or [] if isinstance(item, dict)]
        commands = [item for item in config.get("command_library") or [] if isinstance(item, dict)]
        panels = [item for item in config.get("panels") or [] if isinstance(item, dict)]
        target_matches = _match_items_by_query(text, targets, ("name", "id", "host"))
        if not target_matches and re.search(r"50\.\d{1,3}", text):
            suffix = re.search(r"50\.(\d{1,3})", text)
            if suffix:
                needle = f"192.168.50.{suffix.group(1)}"
                short_needle = f"50{suffix.group(1)}"
                target_matches = [
                    item
                    for item in targets
                    if str(item.get("host") or "") == needle
                    or needle in str(item.get("id") or "")
                    or short_needle in _normalize_match_text(item.get("name") or "")
                    or short_needle in _normalize_match_text(item.get("id") or "")
                ]
        if len(target_matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("协议设备", target_matches)}
        if not target_matches:
            return {"type": "error", "message": self._not_found_control_text("协议设备", "例如：打开泥人50.89设备、关闭泥人50.89")}
        target = target_matches[0]
        wants_on = action in {"on", "toggle"}
        command_matches = []
        for command in commands:
            haystack = f"{command.get('id', '')} {command.get('name', '')}".lower()
            if wants_on and any(word in haystack for word in ("do_on", "do开", "吸合", "开启", "开")):
                command_matches.append(command)
            if not wants_on and any(word in haystack for word in ("do_off", "do关", "断开", "关闭", "关")):
                command_matches.append(command)
        target_controls = []
        for panel in panels:
            for control in panel.get("controls") or []:
                if isinstance(control, dict) and str(control.get("target_group_id") or "") == str(target.get("id") or ""):
                    target_controls.append(control)
        control = None
        for item in target_controls:
            control_haystack = f"{item.get('id', '')} {item.get('name', '')} {item.get('command_id', '')}".lower()
            if wants_on and any(word in control_haystack for word in ("do_on", "do开", "吸合", "开启", "开")):
                control = item
                break
            if not wants_on and any(word in control_haystack for word in ("do_off", "do关", "断开", "关闭", "关")):
                control = item
                break
        if control:
            return {
                "type": "control_center",
                "risk": "normal",
                "label": str(control.get("name") or target.get("name") or "协议设备"),
                "path": "/api/control_center/execute",
                "payload": {"control_id": control.get("id"), "params": control.get("params") if isinstance(control.get("params"), dict) else {}},
                "action": "on" if wants_on else "off",
                "timeout_sec": 8.0,
            }
        command = command_matches[0] if command_matches else None
        if not command:
            return {"type": "error", "message": f"未找到 {_device_name(target)} 的DO{'开' if wants_on else '关'}指令。"}
        return {
            "type": "control_center",
            "risk": "normal",
            "label": _device_name(target),
            "path": "/api/control_center/execute",
            "payload": {"command_id": command.get("id"), "target_group_id": target.get("id"), "params": {"channel": 1}},
            "action": "on" if wants_on else "off",
            "timeout_sec": 8.0,
        }

    def _resolve_projector_control(self, text: str, action: str) -> dict[str, Any] | None:
        if action not in {"on", "off", "toggle"}:
            return None
        projectors = self._config_section("projectors")
        matches = _match_items_by_query(text, projectors, ("name", "id", "ip"))
        if not matches and len(projectors) == 1:
            matches = projectors
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("投影机", matches)}
        if not matches:
            return {"type": "error", "message": self._not_found_control_text("投影机")}
        proj = matches[0]
        if action == "toggle":
            action = "on"
        command = self._find_projector_power_command(proj, action)
        if not command:
            return {"type": "error", "message": f"未找到 {_device_name(proj)} 的{_format_control_action(action)}命令。"}
        return {
            "type": "projector",
            "risk": "normal",
            "label": _device_name(proj),
            "path": "/api/projector/control",
            "payload": {"device_id": proj.get("id"), "command": command},
            "action": action,
            "timeout_sec": 10.0,
        }

    def _find_projector_power_command(self, projector: dict[str, Any], action: str) -> dict[str, Any] | None:
        wants_on = action == "on"
        commands = [item for item in projector.get("commands") or [] if isinstance(item, dict)]
        for cmd in commands:
            haystack = f"{cmd.get('id', '')} {cmd.get('name', '')}".lower()
            if wants_on and ("power_on" in haystack or "开机" in haystack):
                return {"name": cmd.get("name") or "开机", "payload": cmd.get("payload") or "", "format": cmd.get("format") or "str"}
            if not wants_on and ("power_off" in haystack or "关机" in haystack):
                return {"name": cmd.get("name") or "关机", "payload": cmd.get("payload") or "", "format": cmd.get("format") or "str"}
        return {"name": "开机" if wants_on else "关机", "payload": "power_on" if wants_on else "power_off", "format": "str"}

    def _resolve_server_control(self, text: str, action: str, allow_loose: bool = False) -> dict[str, Any] | None:
        if action not in {"wake", "shutdown", "restart", "refresh"}:
            return None
        ok, payload = self.get_json("/api/machines", timeout_sec=6.0)
        machines = [item for item in payload if isinstance(item, dict)] if ok and isinstance(payload, list) else []
        if not machines:
            return {"type": "error", "message": f"服务器接口暂时不可用：{payload}"}
        matches = _match_items_by_query(text, machines, ("custom_name", "hostname", "ip", "mac", "remark", "asset_group"))
        if not matches and allow_loose:
            ignored = {"服务器", "主机", "机器", "电脑", "节点", "唤醒", "关机", "重启", "刷新", "打开", "关闭", "开机"}
            raw_tokens = re.split(r"[\s,，。:：的那台]+", str(text or ""))
            query_tokens = [
                _normalize_match_text(token)
                for token in raw_tokens
                if len(_normalize_match_text(token)) >= 2 and _normalize_match_text(token) not in ignored
            ]
            loose_matches: list[dict[str, Any]] = []
            for machine in machines:
                haystack = _normalize_match_text(
                    " ".join(
                        str(machine.get(key) or "")
                        for key in ("custom_name", "hostname", "ip", "mac", "remark", "asset_group")
                    )
                )
                if haystack and any(token in haystack or haystack in token for token in query_tokens):
                    loose_matches.append(machine)
            matches = loose_matches
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("服务器", matches)}
        if not matches:
            return {"type": "error", "message": self._not_found_control_text("服务器", "例如：唤醒门口LED服务器、关闭192.168.80.60")}
        item = matches[0]
        mac = str(item.get("mac") or "").strip()
        if not mac:
            return {"type": "error", "message": f"{_device_name(item)} 没有 MAC，无法下发服务器控制。"}
        if action == "wake":
            return {
                "type": "server",
                "risk": "normal",
                "label": _device_name(item),
                "path": f"/api/wake/{requests.utils.quote(mac, safe='')}",
                "payload": {},
                "action": "wake",
                "timeout_sec": 8.0,
            }
        return {
            "type": "server",
            "risk": "normal",
            "label": _device_name(item),
            "path": f"/api/machines/{requests.utils.quote(mac, safe='')}/command",
            "payload": {"command": action},
            "action": action,
        }

    def _resolve_power_control(self, text: str, action: str, allow_single_cabinet_inference: bool = False) -> dict[str, Any] | None:
        if action not in {"on", "off", "toggle"}:
            return None
        cabinets = self._config_section("cabinets")
        alias_matches = find_alias_rows(text, self._device_alias_rows(), module="power")
        channel_alias = next((row for row in alias_matches if row.get("device_type") == "cabinet_channel"), None)
        cabinet_alias = next((row for row in alias_matches if row.get("device_type") == "cabinet"), None)
        cab_matches = _match_items_by_query(text, cabinets, ("name", "cabinet_name", "meter_display_name", "id"))
        cab_idx = None
        if channel_alias and channel_alias.get("cab_idx") is not None:
            cab_idx = int(channel_alias.get("cab_idx") or 0)
        elif cabinet_alias and cabinet_alias.get("cab_idx") is not None:
            cab_idx = int(cabinet_alias.get("cab_idx") or 0)
        elif cab_matches:
            if len(cab_matches) > 1:
                return {"type": "error", "message": self._ambiguous_control_text("强电柜", cab_matches)}
            cab_idx = cabinets.index(cab_matches[0])
        elif len(cabinets) == 1:
            cab_idx = 0
        elif allow_single_cabinet_inference and len(cabinets) == 1:
            cab_idx = 0
        if cab_idx is None:
            hint_rows = [row.get("name") for row in self._device_alias_rows() if row.get("module") == "power" and row.get("device_type") == "cabinet_channel"]
            hint = "可尝试：" + "、".join(str(x) for x in hint_rows[:8]) if hint_rows else "例如：关闭中控室电柜第8路"
            return {"type": "error", "message": self._not_found_control_text("强电柜", hint)}
        cab = cabinets[cab_idx] if 0 <= cab_idx < len(cabinets) else {}
        cab_label = str(cab.get("cabinet_name") or cab.get("meter_display_name") or cab.get("name") or f"强电柜{cab_idx + 1}")
        channel = int(channel_alias.get("channel") or 0) if channel_alias else _extract_first_int(text)
        channels_cfg = [item for item in cab.get("channels_config") or [] if isinstance(item, dict)]
        channel_matches = _match_items_by_query(text, channels_cfg, ("name", "remark", "channel"))
        if channel_matches:
            channel = int(channel_matches[0].get("channel") or channel or 0)
        if channel is None or channel <= 0:
            if _contains_any(text, ("全部", "一键", "全开", "全关")):
                path = f"/api/onekey_start?cab={cab_idx}" if action == "on" else f"/api/onekey_stop?cab={cab_idx}"
                return {"type": "power", "risk": "high", "label": cab_label, "path": path, "payload": {}, "action": action, "method": "GET"}
            channel_hints = [row.get("name") for row in self._device_alias_rows() if row.get("module") == "power" and row.get("device_type") == "cabinet_channel" and int(row.get("cab_idx") or -1) == cab_idx]
            suffix = f"可说：{ '、'.join(str(x) for x in channel_hints[:6]) }" if channel_hints else "例如：关闭中控室电柜第8路。"
            return {"type": "error", "message": f"强电柜控制需要指定回路。{suffix}"}
        target = action == "on"
        channel_name = str(channel_alias.get("name")).replace(f"{cab_label} ", "", 1) if channel_alias else str((channel_matches[0].get("remark") or channel_matches[0].get("name")) if channel_matches else f"第{channel}路")
        return {
            "type": "power",
            "risk": "high",
            "label": f"{cab_label} {channel_name}",
            "path": "/api/set",
            "payload": {"cab": cab_idx, "ch": channel, "on": target},
            "action": "on" if target else "off",
        }

    def _resolve_sequencer_control(self, text: str, action: str) -> dict[str, Any] | None:
        ok, payload = self.get_json("/api/sequencer/status", timeout_sec=5.0)
        if not ok or not isinstance(payload, dict):
            devices = self._config_section("sequencers")
        else:
            devices = [item for item in payload.get("devices") or [] if isinstance(item, dict)]
        if not devices:
            return {"type": "error", "message": f"时序电源接口暂时不可用：{payload}"}
        matches = _match_items_by_query(text, devices, ("name", "id", "ip"))
        if not matches and _contains_any(text, ("二号厅", "2号厅", "二厅", "2厅")):
            matches = [item for item in devices if _contains_any(str(item.get("name") or ""), ("2 厅", "2厅", "二号厅", "二厅"))]
        if not matches and len(devices) == 1:
            matches = devices
        if len(matches) > 1:
            return {"type": "error", "message": self._ambiguous_control_text("时序电源", matches)}
        if not matches:
            return {"type": "error", "message": self._not_found_control_text("时序电源")}
        device = matches[0]
        channel = _extract_explicit_channel_int(text)
        seq_action = ""
        if _contains_any(text, ("顺序", "顺开", "顺关")):
            seq_action = "sequence_on" if action == "on" else "sequence_off"
        elif _contains_any(text, ("全部", "全开", "全关")):
            seq_action = "all_on" if action == "on" else "all_off"
        elif channel:
            seq_action = "channel_on" if action == "on" else "channel_off"
        else:
            seq_action = "sequence_on" if action == "on" else "sequence_off"
        label = _device_name(device)
        if channel:
            label = f"{label} 第{channel}路"
        return {
            "type": "sequencer",
            "risk": "high",
            "label": label,
            "path": "/api/sequencer/control",
            "payload": {"id": device.get("id"), "action": seq_action, "channel": channel},
            "action": seq_action,
            "timeout_sec": 12.0,
        }

    def status_text(self) -> str:
        lines = [
            "中控总体状态",
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        if ok:
            counts = _aggregate_dashboard_counts((summary or {}).get("counts", {}) or {})
            modules = (summary or {}).get("modules", {}) or {}
            total = int(counts.get("total") or 0)
            online = int(counts.get("online") or 0)
            offline = int(counts.get("offline") or max(0, total - online))
            error = int(counts.get("error") or 0)
            stale = int(counts.get("stale") or 0)
            lines.append(f"总览：设备在线 {online}/{total}，离线 {offline}，异常 {error}，陈旧 {stale}")
            module_parts = []
            for key in ("server", "power", "env", "light", "snmp", "ups", "proxy", "sequencer"):
                item = ((summary or {}).get("counts", {}) or {}).get(key)
                if not isinstance(item, dict):
                    continue
                label = MODULE_LABELS.get(key, key)
                item_total = int(item.get("total") or 0)
                item_online = int(item.get("online") or 0)
                item_offline = max(int(item.get("offline") or 0), max(0, item_total - item_online))
                module_parts.append(f"{label} {item_online}/{item_total}{f' 离线{item_offline}' if item_offline else ''}")
            if module_parts:
                lines.append("模块：" + "；".join(module_parts))
            server = (modules.get("server") or {}) if isinstance(modules, dict) else {}
            if server:
                lines.append(f"服务器：在线 {server.get('online', 0)}/{server.get('total', 0)}")
            env_devices = (((modules.get("env") or {}) if isinstance(modules, dict) else {}).get("devices") or [])
            door = next((item for item in env_devices if isinstance(item, dict) and ("大门" in str(item.get("name") or "") or item.get("contact") is not None)), None)
            if isinstance(door, dict):
                contact = door.get("contact")
                contact_text = "打开" if contact is True else ("关闭" if contact is False else "--")
                lines.append(f"大门：{contact_text}，{'在线' if door.get('online') else '离线'}，更新 {door.get('updated_at') or '--'}")
            offline_preview = []
            module_iter = modules.items() if isinstance(modules, dict) else []
            for module_key, module_payload in module_iter:
                label = MODULE_LABELS.get(module_key, module_key)
                devices = []
                if isinstance(module_payload, dict):
                    if isinstance(module_payload.get("devices"), list):
                        devices = module_payload.get("devices") or []
                    elif module_key == "server" and isinstance(module_payload.get("machines"), list):
                        devices = module_payload.get("machines") or []
                for device in devices:
                    if not isinstance(device, dict):
                        continue
                    online_state = device.get("online", device.get("is_online"))
                    level = str(device.get("status_level") or device.get("diagnostic_level") or "").lower()
                    if online_state is False or level in {"offline", "error", "stale"}:
                        offline_preview.append(f"[{label}] {_device_name(device)}")
            if offline_preview:
                lines.append("重点离线：" + "；".join(offline_preview[:5]) + (f"；... 还有 {len(offline_preview) - 5} 个" if len(offline_preview) > 5 else ""))
        else:
            lines.append(f"概览接口：不可用（{summary}）")
        energy_line = self.energy_brief_text()
        if energy_line:
            lines.append(energy_line)
        collector_line = self.current_collector_text()
        if collector_line:
            lines.append(collector_line)
        proxy_line = self.proxy_brief_text()
        if proxy_line:
            lines.append(proxy_line)
        automation_line = self.automation_brief_text()
        if automation_line:
            lines.append(automation_line)
        return "\n".join(lines)

    def current_collector_text(self) -> str:
        ok, payload = self.get_json("/api/current-collector/status", timeout_sec=3.0)
        if not ok:
            return f"电流采集器：接口不可用（{payload}）"
        online = "在线" if payload.get("online") else "离线"
        updated_at = payload.get("updated_at") or "--"
        groups = payload.get("groups") if isinstance(payload.get("groups"), list) else []
        channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
        if groups:
            details = []
            for item in groups[:6]:
                current = item.get("total_current")
                if current is not None:
                    details.append(f"{item.get('name') or item.get('id')}: {current}A")
            detail_text = "；".join(details) if details else "暂无组合数据"
        else:
            details = []
            for item in channels[:8]:
                current = item.get("current")
                if current is not None:
                    details.append(f"{item.get('name') or item.get('channel')}: {current}A")
            detail_text = "；".join(details) if details else (payload.get("error") or "暂无通道数据")
        return f"电流采集器：{online}，更新时间 {updated_at}，{detail_text}"

    def energy_brief_text(self) -> str:
        ok, payload = self.get_json("/api/meters?target=total&period=day&days=7", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return ""
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        dashboard = payload.get("dashboard_summary") if isinstance(payload.get("dashboard_summary"), dict) else {}
        today = _first_value(summary, ("total_daily_energy", "raw_total_daily_energy"))
        if today is None:
            today = _first_value(dashboard, ("daily_energy", "raw_daily_energy"))
        month = _first_value(summary, ("total_monthly_energy",))
        if month is None:
            month = _first_value(dashboard, ("monthly_energy",))
        power = _first_value(summary, ("total_realtime_power", "stable_total_realtime_power", "estimated_total_realtime_power"))
        if power is None:
            power = _first_value(dashboard, ("power", "stable_power", "estimated_power"))
        return f"电力：今日 {_fmt_number(today)} kWh，本月 {_fmt_number(month)} kWh，当前功率 {_fmt_number(power)} kW"

    def proxy_brief_text(self) -> str:
        ok, payload = self.get_json("/api/proxy/status", timeout_sec=3.0)
        if not ok or not isinstance(payload, dict):
            return ""
        online = "在线" if payload.get("online") else "离线"
        return f"代理：{online}，外网检查 {payload.get('healthy_target_count', 0)}/{payload.get('check_count', 0)}"

    def automation_brief_text(self) -> str:
        ok, payload = self.get_json("/api/automation/status", timeout_sec=3.0)
        if not ok or not isinstance(payload, dict):
            return ""
        rules = [item for item in payload.get("rules") or [] if isinstance(item, dict)]
        enabled = sum(1 for item in rules if item.get("enabled"))
        active = sum(1 for item in rules if isinstance(item.get("state"), dict) and (item["state"].get("active") or item["state"].get("active_since")))
        return f"自动化：启用 {enabled}/{len(rules)}，触发中 {active}"

    def daily_text(self) -> str:
        ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        lines = [
            "中控日报",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if ok:
            counts = _aggregate_dashboard_counts((summary or {}).get("counts", {}) or {})
            total = int(counts.get("total") or 0)
            online = int(counts.get("online") or 0)
            error = int(counts.get("error") or 0)
            stale = int(counts.get("stale") or 0)
            lines.append(f"设备：在线 {online}/{total}，异常 {error}，陈旧 {stale}")
        else:
            lines.append(f"概览接口：不可用（{summary}）")
        lines.append(self.current_collector_text())
        return "\n".join(lines)

    def meter_energy_text(self, query: str = "") -> str:
        query_days = 30 if _contains_any(query, ("近30天", "最近30天", "30天")) else (14 if _contains_any(query, ("上周", "上个星期")) else 7)
        ok, payload = self.get_json(f"/api/meters?target=total&period=day&days={query_days}", timeout_sec=6.0)
        if not ok or not isinstance(payload, dict):
            return f"电表接口暂时不可用：{payload}"

        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        dashboard = payload.get("dashboard_summary") if isinstance(payload.get("dashboard_summary"), dict) else {}
        today_energy = _first_value(summary, ("total_daily_energy", "raw_total_daily_energy"))
        if today_energy is None:
            today_energy = _first_value(dashboard, ("daily_energy", "raw_daily_energy"))
        month_energy = _first_value(summary, ("total_monthly_energy",))
        if month_energy is None:
            month_energy = _first_value(dashboard, ("monthly_energy",))
        power = _first_value(summary, ("total_realtime_power", "stable_total_realtime_power", "estimated_total_realtime_power"))
        if power is None:
            power = _first_value(dashboard, ("power", "stable_power", "estimated_power"))

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        yesterday_energy = None
        for item in payload.get("trend") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("date") or item.get("period") or "") == yesterday:
                yesterday_energy = _first_value(item, ("consume", "value", "daily_energy"))
                break
        if yesterday_energy is None:
            comparison = summary.get("comparison_day") if isinstance(summary.get("comparison_day"), dict) else {}
            yesterday_energy = comparison.get("previous")

        normalized = query.strip()
        computed = self.energy_calculation_text(normalized, payload, today_energy, yesterday_energy, month_energy, power)
        if computed:
            return computed
        lines: list[str]
        if _contains_any(normalized, ("对比", "相比", "比", "差", "多了", "少了")):
            lines = [
                "电量概览",
                f"今日用电：{_fmt_number(today_energy)} kWh",
                f"昨日电量：{_fmt_number(yesterday_energy)} kWh",
                f"本月用电：{_fmt_number(month_energy)} kWh",
                f"当前功率：{_fmt_number(power)} kW",
            ]
        elif _contains_any(normalized, ("昨天", "昨日", "昨日电量")):
            lines = [f"昨日电量：{_fmt_number(yesterday_energy)} kWh"]
        elif _contains_any(normalized, ("今天", "今日", "当天")):
            lines = [f"今日用电：{_fmt_number(today_energy)} kWh"]
        elif _contains_any(normalized, ("本月", "这个月", "月度")):
            lines = [f"本月用电：{_fmt_number(month_energy)} kWh"]
        else:
            lines = [
                "电量概览",
                f"今日用电：{_fmt_number(today_energy)} kWh",
                f"昨日电量：{_fmt_number(yesterday_energy)} kWh",
                f"本月用电：{_fmt_number(month_energy)} kWh",
                f"当前功率：{_fmt_number(power)} kW",
            ]

        if _contains_any(normalized, ("排行", "排名", "最多", "top", "TOP")):
            key = "monthly_energy" if _contains_any(normalized, ("本月", "月")) else "daily_energy"
            title = "本月用电排行" if key == "monthly_energy" else "今日用电排行"
            meters = [item for item in payload.get("meters") or [] if isinstance(item, dict)]
            meters.sort(key=lambda item: float(item.get(key) or 0), reverse=True)
            lines.append(title)
            for index, item in enumerate(meters[:5], 1):
                lines.append(f"{index}. {_device_name(item)}：{_fmt_number(item.get(key))} kWh")

        return "\n".join(lines)

    def energy_calculation_text(
        self,
        query: str,
        payload: dict[str, Any],
        today_energy: Any,
        yesterday_energy: Any,
        month_energy: Any,
        power: Any,
    ) -> str:
        normalized = query.strip()
        wants_calc = _contains_any(
            normalized,
            ("合计", "总计", "总共", "累计", "平均", "最大", "最高", "最小", "最低", "对比", "相比", "环比", "比", "差", "多了", "少了", "本周", "这周", "近7天", "最近7天", "7天", "近30天", "最近30天", "30天"),
        )
        if not wants_calc:
            return ""

        rows = []
        for item in payload.get("trend") or []:
            if not isinstance(item, dict):
                continue
            day = str(item.get("date") or item.get("period") or "")
            value = _to_float(_first_value(item, ("consume", "value", "daily_energy")))
            if day and value is not None:
                rows.append({"date": day, "consume": value})
        rows.sort(key=lambda item: item["date"])

        if _contains_any(normalized, ("近7天", "最近7天", "7天")) and len(rows) < 7:
            ok7, payload7 = self.get_json("/api/7days_energy", timeout_sec=5.0)
            if ok7 and isinstance(payload7, list):
                rows = []
                for item in payload7:
                    if not isinstance(item, dict):
                        continue
                    day = str(item.get("date") or "")
                    value = _to_float(item.get("consume"))
                    if day and value is not None:
                        rows.append({"date": day, "consume": value})
                rows.sort(key=lambda item: item["date"])

        selected = rows
        title = "电量计算"
        today = date.today()
        if _contains_any(normalized, ("本周", "这周")):
            monday = today - timedelta(days=today.weekday())
            selected = [item for item in rows if item["date"] >= monday.isoformat()]
            title = "本周电能消耗"
        elif _contains_any(normalized, ("近30天", "最近30天", "30天")):
            selected = rows[-30:]
            title = "最近30天电能消耗"
        elif _contains_any(normalized, ("近7天", "最近7天", "7天")):
            selected = rows[-7:]
            title = "最近7天电能消耗"
        elif _contains_any(normalized, ("本月", "这个月", "月度")) and not _contains_any(normalized, ("对比", "相比", "比", "差", "多了", "少了")):
            return f"本月用电：{_fmt_number(month_energy)} kWh\n当前功率：{_fmt_number(power)} kW"
        elif _contains_any(normalized, ("昨天", "昨日")) and not _contains_any(normalized, ("对比", "相比", "比", "差", "多了", "少了")):
            return f"昨日电量：{_fmt_number(yesterday_energy)} kWh"
        elif _contains_any(normalized, ("今天", "今日")) and not _contains_any(normalized, ("对比", "相比", "比", "差", "多了", "少了")):
            return f"今日用电：{_fmt_number(today_energy)} kWh"

        if not selected:
            return ""
        values = [float(item["consume"]) for item in selected]
        total = sum(values)
        avg = total / len(values)
        max_item = max(selected, key=lambda item: item["consume"])
        min_item = min(selected, key=lambda item: item["consume"])

        if _contains_any(normalized, ("对比", "相比", "比", "差", "多了", "少了")) and len(selected) >= 2:
            previous = selected[-2]["consume"]
            current = selected[-1]["consume"]
            delta = current - previous
            pct = (delta / previous * 100) if previous else None
            trend = "增加" if delta > 0 else ("减少" if delta < 0 else "持平")
            pct_text = f"，{trend} {_fmt_number(abs(pct))}%" if pct is not None else ""
            return f"{selected[-1]['date']} 比 {selected[-2]['date']} {trend} {_fmt_number(abs(delta))} kWh{pct_text}"
        if _contains_any(normalized, ("平均", "日均", "每天")):
            return f"{title}：日均 {_fmt_number(avg)} kWh（{selected[0]['date']} 至 {selected[-1]['date']}，{len(selected)} 天合计 {_fmt_number(total)} kWh）"
        if _contains_any(normalized, ("最大", "最高", "最多")):
            return f"{title}：最高 {max_item['date']}，{_fmt_number(max_item['consume'])} kWh"
        if _contains_any(normalized, ("最小", "最低", "最少")):
            return f"{title}：最低 {min_item['date']}，{_fmt_number(min_item['consume'])} kWh"
        return "\n".join(
            [
                title,
                f"范围：{selected[0]['date']} 至 {selected[-1]['date']}，{len(selected)} 天",
                f"合计：{_fmt_number(total)} kWh",
                f"平均：{_fmt_number(avg)} kWh/天",
                f"最高：{max_item['date']} {_fmt_number(max_item['consume'])} kWh",
                f"最低：{min_item['date']} {_fmt_number(min_item['consume'])} kWh",
            ]
        )

    def offline_devices_text(self) -> str:
        ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=4.0)
        if not ok or not isinstance(summary, dict):
            return f"设备概览接口暂时不可用：{summary}"

        counts = _aggregate_dashboard_counts(summary.get("counts", {}) or {})
        modules = summary.get("modules", {}) if isinstance(summary.get("modules"), dict) else {}
        offline_items: list[str] = []
        for module_key, module_payload in modules.items():
            label = MODULE_LABELS.get(module_key, module_key)
            devices: list[Any] = []
            if isinstance(module_payload, dict):
                if isinstance(module_payload.get("devices"), list):
                    devices = list(module_payload.get("devices") or [])
                elif module_key == "server" and isinstance(module_payload.get("machines"), list):
                    devices = list(module_payload.get("machines") or [])
                elif module_payload.get("online") is False or module_payload.get("status_level") in {"offline", "error", "stale"}:
                    devices = [module_payload]

            for device in devices:
                if not isinstance(device, dict):
                    continue
                online = device.get("online")
                if online is None and "is_online" in device:
                    online = device.get("is_online")
                level = str(device.get("status_level") or device.get("diagnostic_level") or "").lower()
                if online is not False and level not in {"offline", "error", "stale", "warn"}:
                    continue
                extra = device.get("last_error") or device.get("updated_at") or device.get("last_online") or device.get("ip") or ""
                suffix = f"（{extra}）" if extra else ""
                offline_items.append(f"- [{label}] {_device_name(device)}{suffix}")

        if not offline_items:
            return f"当前未发现离线设备。设备在线 {counts.get('online', 0)}/{counts.get('total', 0)}。"

        header = f"当前离线/异常设备 {len(offline_items)} 个，设备在线 {counts.get('online', 0)}/{counts.get('total', 0)}："
        if len(offline_items) > 12:
            shown = offline_items[:12] + [f"... 还有 {len(offline_items) - 12} 个未显示"]
        else:
            shown = offline_items
        return "\n".join([header, *shown])

    def server_status_text(self, query: str = "") -> str:
        query = str(query or "").strip()
        ok, payload = self.get_json("/api/machines", timeout_sec=6.0)
        source_error = ""
        machines = [item for item in payload if isinstance(item, dict)] if ok and isinstance(payload, list) else []
        if not machines:
            source_error = str(payload)
            summary_ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=4.0)
            if summary_ok and isinstance(summary, dict):
                modules = summary.get("modules", {}) if isinstance(summary.get("modules"), dict) else {}
                server = modules.get("server") if isinstance(modules.get("server"), dict) else {}
                machines = [item for item in server.get("machines", []) if isinstance(item, dict)]
        if not machines:
            return f"服务器接口暂时不可用：{source_error or payload}"

        group_order: list[str] = []
        group_stats: dict[str, dict[str, Any]] = {}
        for item in machines:
            group = _machine_group(item)
            if group not in group_stats:
                group_order.append(group)
                group_stats[group] = {"total": 0, "online": 0, "items": []}
            group_stats[group]["total"] += 1
            group_stats[group]["online"] += 1 if item.get("is_online") else 0
            group_stats[group]["items"].append(item)

        total = len(machines)
        online = sum(1 for item in machines if item.get("is_online"))
        offline_total = max(0, total - online)
        normalized_query = _normalize_match_text(query)
        wants_offline = _contains_any(query, SERVER_OFFLINE_WORDS)
        wants_full_list = _contains_any(query, ("全部", "完整", "列表", "清单", "明细", "每台", "逐台")) or (
            "所有" in query and not _contains_any(query, ("汇总", "概览", "分组", "总览"))
        )
        wants_group_summary = _contains_any(query, ("分组", "汇总", "总览", "概览"))
        wants_diagnostics = _contains_any(query, ("诊断", "建议", "原因", "告警", "异常", "故障"))
        metric_request = ""
        if "gpu" in query.lower() or "显卡" in query:
            metric_request = "gpu_temp" if _contains_any(query, ("温度", "发热", "最高")) else "gpu_util"
        elif "cpu" in query.lower() or "处理器" in query:
            metric_request = "cpu"
        elif "内存" in query:
            metric_request = "mem"
        elif "磁盘" in query or "硬盘" in query:
            metric_request = "disk"

        matched_group = ""
        group_aliases: list[tuple[str, str]] = []
        for group in group_order:
            aliases = {_normalize_match_text(group)}
            if "-" in group or "－" in group:
                parts = [part for part in re.split(r"[-－]+", group) if part]
                aliases.add(_normalize_match_text("".join(parts)))
                aliases.add(_normalize_match_text("".join(reversed(parts))))
            for alias in aliases:
                if alias:
                    group_aliases.append((alias, group))
        for alias, group in sorted(group_aliases, key=lambda item: len(item[0]), reverse=True):
            if alias and alias in normalized_query:
                matched_group = group
                break

        name_matches = []
        for item in machines:
            fields = (
                ("custom_name", item.get("custom_name")),
                ("hostname", item.get("hostname")),
                ("ip", item.get("ip")),
                ("mac", item.get("mac")),
                ("remark", item.get("remark")),
            )
            for field_name, field in fields:
                if _query_mentions_machine_field(query, normalized_query, field, field_name):
                    name_matches.append(item)
                    break

        if name_matches:
            selected = name_matches
            scope_title = f"匹配服务器 {len(selected)} 台"
            include_group = True
        elif matched_group:
            selected = list(group_stats[matched_group]["items"])
            scope_title = f"{matched_group}服务器"
            include_group = False
        else:
            selected = list(machines)
            scope_title = "服务器"
            include_group = True

        selected_before_offline = list(selected)
        if wants_offline:
            selected = [item for item in selected if item.get("is_online") is False]

        if metric_request:
            metric_rows = [(item, _machine_metric_value(item, metric_request)) for item in selected]
            metric_rows = [(item, value) for item, value in metric_rows if value is not None]
            reverse = True
            if _contains_any(query, ("最低", "最少", "最小")):
                reverse = False
            metric_rows.sort(key=lambda row: row[1], reverse=reverse)
            selected = [item for item, _value in metric_rows]

        lines = []
        if name_matches:
            lines.append(f"{scope_title}：总在线 {online}/{total}，离线 {offline_total}")
        elif matched_group:
            stats = group_stats[matched_group]
            group_total = int(stats["total"])
            group_online = int(stats["online"])
            group_offline = max(0, group_total - group_online)
            suffix = f"，当前列出离线 {len(selected)} 台" if wants_offline else ""
            lines.append(f"{scope_title}：在线 {group_online}/{group_total}，离线 {group_offline}{suffix}")
        elif wants_offline:
            lines.append(f"离线服务器：{len(selected)} 台；总在线 {online}/{total}")
        else:
            lines.append(f"服务器：在线 {online}/{total}，离线 {offline_total}，分组 {len(group_order)} 个")

        if not matched_group and not name_matches:
            group_parts = []
            for group in group_order:
                stats = group_stats[group]
                group_total = int(stats["total"])
                group_online = int(stats["online"])
                group_offline = max(0, group_total - group_online)
                offline_text = f"，离线 {group_offline}" if group_offline else ""
                group_parts.append(f"{group} {group_online}/{group_total}{offline_text}")
            if group_parts:
                lines.append("分组：" + "；".join(group_parts))

        if metric_request:
            metric_labels = {
                "cpu": "CPU占用",
                "mem": "内存占用",
                "disk": "磁盘占用",
                "gpu_temp": "GPU温度",
                "gpu_util": "GPU利用率",
            }
            metric_unit = "°C" if metric_request == "gpu_temp" else "%"
            direction = "最低" if _contains_any(query, ("最低", "最少", "最小")) else "最高"
            lines.append(f"{metric_labels.get(metric_request, '指标')}{direction}：")
            for item in selected[:8]:
                value = _machine_metric_value(item, metric_request)
                lines.append(f"- {('[%s] ' % _machine_group(item)) if include_group else ''}{_device_name(item)}（{item.get('ip') or '--'}）：{_fmt_number(value, 1)}{metric_unit}")
            if len(selected) > 8:
                lines.append(f"... 还有 {len(selected) - 8} 台未显示")
            return "\n".join(lines)

        if wants_group_summary and not wants_full_list and not matched_group and not name_matches and not wants_offline:
            return "\n".join(lines)

        def format_machine(item: dict[str, Any]) -> str:
            status = _machine_status(item)
            state = "在线" if item.get("is_online") else "离线"
            prefix = f"[{_machine_group(item)}] " if include_group else ""
            metrics = []
            cpu = _fmt_number(status.get("cpu_percent"), 1)
            mem = _fmt_number(status.get("mem_percent"), 1)
            disk = _fmt_number(status.get("disk_percent"), 1)
            if cpu != "--":
                metrics.append(f"CPU {cpu}%")
            if mem != "--":
                metrics.append(f"内存 {mem}%")
            if disk != "--":
                metrics.append(f"磁盘 {disk}%")
            gpu_text = _machine_gpu_text(item, detail=bool(name_matches))
            if gpu_text:
                metrics.append(gpu_text)
            if not item.get("is_online"):
                metrics.append(f"最后在线 {item.get('last_online') or '--'}")
            diagnostic = item.get("diagnostic") if isinstance(item.get("diagnostic"), dict) else {}
            diagnostic_summary = str(diagnostic.get("summary") or "").strip()
            if diagnostic_summary and (wants_diagnostics or not item.get("is_online")):
                metrics.append(diagnostic_summary)
            detail_text = "，".join(metrics) if metrics else "暂无指标"
            return f"- {prefix}{_device_name(item)}（{item.get('ip') or '--'}）：{state}，{detail_text}"

        if not selected and wants_offline:
            if matched_group:
                return "\n".join(lines + [f"{matched_group}当前没有离线服务器。"])
            return "\n".join(lines + ["当前没有匹配的离线服务器。"])
        if not selected:
            return "\n".join(lines + ["没有匹配到服务器。"])

        if name_matches:
            limit = 8
        elif wants_full_list:
            limit = 20
        elif matched_group or wants_offline:
            limit = 12
        else:
            limit = 10

        list_source = selected
        if not wants_full_list and not matched_group and not name_matches and not wants_offline:
            # Overall status should prove every group is considered, without dumping all 31 rows.
            list_source = []
            for group in group_order:
                group_items = group_stats[group]["items"]
                offline_items = [item for item in group_items if item.get("is_online") is False]
                online_items = [item for item in group_items if item.get("is_online")]
                list_source.extend((offline_items or online_items)[:2])
            lines.append("各分组代表机器：")
        elif len(selected_before_offline) != len(selected):
            lines.append("离线明细：")
        else:
            lines.append("机器明细：")

        for item in list_source[:limit]:
            lines.append(format_machine(item))
        omitted = max(0, len(list_source) - limit)
        if omitted:
            lines.append(f"... 还有 {omitted} 台未显示；可问“全部服务器列表”或指定分组。")
        return "\n".join(lines)

    def environment_status_text(self, query: str = "") -> str:
        ok, payload = self.get_json("/api/env/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"环境接口暂时不可用：{payload}"
        name_map: dict[str, str] = {}
        summary_ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        if summary_ok and isinstance(summary, dict):
            modules = summary.get("modules") if isinstance(summary.get("modules"), dict) else {}
            env_module = modules.get("env") if isinstance(modules.get("env"), dict) else {}
            for device in env_module.get("devices") or []:
                if isinstance(device, dict) and device.get("id"):
                    name_map[str(device.get("id"))] = _device_name(device)
        rows = []
        for sensor_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            name = name_map.get(str(sensor_id)) or str(item.get("name") or sensor_id)
            specific_query = query
            for generic in ("环境", "温度", "湿度", "光照", "传感器", "状态", "多少", "查看", "查询", "帮我看", "现在"):
                specific_query = specific_query.replace(generic, "")
            specific_query = specific_query.strip()
            if specific_query and specific_query not in f"{sensor_id} {name}":
                compact_query = specific_query.replace("的", "").replace(" ", "")
                compact_name = f"{sensor_id}{name}".replace("的", "").replace(" ", "")
                if compact_query and compact_query not in compact_name:
                    continue
            online = "在线" if item.get("online", True) else "离线"
            parts = [f"{name}：{online}"]
            if item.get("temp") is not None:
                parts.append(f"温度 {_fmt_number(item.get('temp'), 1)}°C")
            if item.get("hum") is not None:
                parts.append(f"湿度 {_fmt_number(item.get('hum'), 1)}%")
            if item.get("lux") is not None:
                parts.append(f"光照 {_fmt_number(item.get('lux'), 0)} lux")
            if item.get("updated_at"):
                parts.append(f"更新 {item.get('updated_at')}")
            rows.append("，".join(parts))
        if not rows:
            return "没有匹配到环境传感器。"
        return "\n".join(["环境状态：", *[f"- {row}" for row in rows[:10]], *(["... 还有更多传感器未显示"] if len(rows) > 10 else [])])

    def door_status_text(self, query: str = "") -> str:
        rows: list[str] = []
        vision_ok, vision_payload = self.get_json("/api/door/vision_status", timeout_sec=4.0)
        if vision_ok and isinstance(vision_payload, dict):
            status = str(vision_payload.get("door_status") or "unknown")
            status_text = str(vision_payload.get("door_status_text") or "").strip()
            if not status_text:
                status_text = {
                    "open": "门已完全开启",
                    "closed": "门已完全关闭",
                    "opening": "正在开门中",
                    "closing": "正在关门中",
                    "stopped_midway": "门体静止中",
                    "unknown_calibration": "状态未判定",
                    "unknown": "状态未知",
                }.get(status, "状态未知")
            confidence = vision_payload.get("confidence")
            updated = vision_payload.get("updated_at") or "--"
            rows.append(f"视觉大门：{status_text}，置信度 {_fmt_number(confidence, 2)}，更新 {updated}")

            diagnosis = vision_payload.get("diagnosis") if isinstance(vision_payload.get("diagnosis"), dict) else {}
            if diagnosis and not diagnosis.get("ready"):
                reason = str(diagnosis.get("reason_text") or "").strip()
                if reason:
                    rows.append(f"识别提示：{reason}")
                next_steps = [str(item).strip() for item in diagnosis.get("next_steps") or [] if str(item).strip()]
                if next_steps:
                    rows.append("建议：" + "；".join(next_steps[:2]))
            votes = vision_payload.get("camera_votes") if isinstance(vision_payload.get("camera_votes"), dict) else {}
            if votes:
                brief_votes = []
                for camera_key, vote in list(votes.items())[:2]:
                    if not isinstance(vote, dict):
                        continue
                    brief_votes.append(
                        f"{camera_key}={vote.get('status') or '--'} "
                        f"差异关{_fmt_number(vote.get('diff_c'), 0)}/开{_fmt_number(vote.get('diff_o'), 0)} "
                        f"阈值{_fmt_number(vote.get('threshold'), 0)}"
                    )
                if brief_votes:
                    rows.append("视觉投票：" + "；".join(brief_votes))
        else:
            rows.append(f"视觉大门接口暂时不可用：{vision_payload}")

        ok, payload = self.get_json("/api/env/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            if rows:
                rows.append(f"门磁接口暂时不可用：{payload}")
                return "\n".join(["大门状态：", *[f"- {row}" for row in rows]])
            return f"门磁接口暂时不可用：{payload}"
        summary_ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        name_map: dict[str, str] = {}
        if summary_ok and isinstance(summary, dict):
            modules = summary.get("modules") if isinstance(summary.get("modules"), dict) else {}
            env_module = modules.get("env") if isinstance(modules.get("env"), dict) else {}
            for device in env_module.get("devices") or []:
                if isinstance(device, dict) and device.get("id"):
                    name_map[str(device.get("id"))] = _device_name(device)
        contact_rows = []
        compact_query = query.replace("状态", "").replace("开关", "").replace("门磁", "").replace("门", "").strip()
        for sensor_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            name = name_map.get(str(sensor_id)) or str(item.get("name") or sensor_id)
            has_contact = item.get("contact") is not None or item.get("opening") is not None or item.get("contact_text") is not None
            if not has_contact and not _contains_any(name, ("门", "大门", "门磁")):
                continue
            if compact_query and compact_query not in name:
                continue
            if item.get("contact_text"):
                state = str(item.get("contact_text"))
            elif item.get("opening") is not None:
                state = "打开" if item.get("opening") else "关闭"
            elif item.get("contact") is not None:
                state = "打开" if item.get("contact") else "关闭"
            else:
                state = "--"
            online = "在线" if item.get("online", True) else "离线"
            updated = item.get("contact_updated_at") or item.get("updated_at") or "--"
            contact_rows.append(f"{name}：{state}，{online}，更新 {updated}")
        if contact_rows:
            rows.extend(contact_rows[:8])
            if len(contact_rows) > 8:
                rows.append("... 还有更多门磁未显示")
        elif not rows:
            return "没有匹配到门磁/大门状态。"
        return "\n".join(["大门状态：", *[f"- {row}" for row in rows]])

    def hvac_status_text(self, query: str = "") -> str:
        ok, payload = self.get_json("/api/hvac/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"空调接口暂时不可用：{payload}"
        rows = []
        for device_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            name = _device_name({"name": item.get("name"), "id": device_id})
            if query and not _contains_any(query, ("空调", "制冷", "制热", "温度", "模式")) and query not in name:
                continue
            online = "在线" if item.get("online", True) else "离线"
            power = "开机" if item.get("power") else "关机"
            rows.append(
                f"- {name}：{online}，{power}，模式 {item.get('mode') or '--'}，设定 {_fmt_number(item.get('target_temp'), 1)}°C，室温 {_fmt_number(item.get('temp'), 1)}°C"
            )
        if not rows:
            return "没有匹配到空调设备。"
        return "\n".join(["空调状态：", *rows[:10], *(["... 还有更多空调未显示"] if len(rows) > 10 else [])])

    def lighting_status_text(self) -> str:
        ok, payload = self.get_json("/api/light/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"灯光接口暂时不可用：{payload}"
        extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
        channels = payload.get("channels") if isinstance(payload.get("channels"), dict) else {}
        lines = ["灯光状态："]
        for device_id, states in list(channels.items())[:10]:
            extra = extras.get(str(device_id), {}) if isinstance(extras.get(str(device_id)), dict) else {}
            online = extra.get("status_label") or ("在线" if extra.get("status_level") == "online" else extra.get("status_level") or "--")
            if isinstance(states, list):
                on_count = sum(1 for value in states if value in {1, True})
                known_count = sum(1 for value in states if value is not None)
                state_text = f"{on_count}/{known_count} 路开启"
            else:
                state_text = "通道未知"
            lines.append(f"- {extra.get('name') or device_id}：{online}，{state_text}")
        return "\n".join(lines)

    def automation_status_text(self) -> str:
        ok, payload = self.get_json("/api/automation/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"自动化接口暂时不可用：{payload}"
        rules = [item for item in payload.get("rules") or [] if isinstance(item, dict)]
        enabled = sum(1 for item in rules if item.get("enabled"))
        lines = [f"自动化规则：启用 {enabled}/{len(rules)}"]
        for item in rules[:8]:
            state = item.get("state") if isinstance(item.get("state"), dict) else {}
            active = "触发中" if state.get("active") or state.get("active_since") else "待机"
            lines.append(f"- {item.get('name') or item.get('id')}：{'启用' if item.get('enabled') else '停用'}，{active}")
        if len(rules) > 8:
            lines.append(f"... 还有 {len(rules) - 8} 条规则未显示")
        return "\n".join(lines)

    def log_text(self, query: str = "", category: str = "", event_type: str = "") -> str:
        params = ["limit=8"]
        if category:
            params.append(f"category={category}")
        if event_type:
            params.append(f"event_type={event_type}")
        if _contains_any(query, ("24小时", "一天", "最近一天")):
            params.append("hours=24")
        elif _contains_any(query, ("一周", "7天", "七天")):
            params.append("hours=168")
        if query and not category and not event_type:
            params.append(f"q={requests.utils.quote(query)}")
        ok, payload = self.get_json(f"/api/logs/events?{'&'.join(params)}", timeout_sec=5.0)
        if not ok or not isinstance(payload, dict):
            return f"日志接口暂时不可用：{payload}"
        items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
        if not items:
            return "没有查到匹配日志。"
        lines = [f"最近日志（匹配 {payload.get('total', len(items))} 条，显示 {len(items)} 条）："]
        for item in items:
            when = item.get("time") or "--"
            label = item.get("category_label") or item.get("category") or "日志"
            message = item.get("message") or item.get("action") or item.get("event_type") or ""
            lines.append(f"- {when} [{label}] {message}")
        return "\n".join(lines)

    def snmp_status_text(self) -> str:
        ok, payload = self.get_json("/api/snmp/status", timeout_sec=5.0)
        if not ok or not isinstance(payload, dict):
            return f"网络设备接口暂时不可用：{payload}"
        lines = ["网络设备/SNMP 状态："]
        for device_id, item in list(payload.items())[:8]:
            if not isinstance(item, dict):
                continue
            cfg = item.get("config") if isinstance(item.get("config"), dict) else {}
            name = cfg.get("name") or item.get("name") or device_id
            online = "在线" if item.get("online", True) else "离线"
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            extra = summary.get("status_text") or item.get("error") or ""
            lines.append(f"- {name}：{online}{f'，{extra}' if extra else ''}")
        return "\n".join(lines)

    def ups_status_text(self) -> str:
        ok, payload = self.get_json("/api/ups/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"UPS 接口暂时不可用：{payload}"
        lines = ["UPS 状态："]
        for device_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            cfg = item.get("config") if isinstance(item.get("config"), dict) else {}
            name = cfg.get("name") or item.get("name") or device_id
            online = "在线" if item.get("online", True) else "离线"
            alerts = "；".join(item.get("alerts") or []) or "无告警"
            lines.append(
                f"- {name}：{online}，电池 {_fmt_number(item.get('battery_capacity_percent'), 0)}%，负载 {_fmt_number(item.get('load_percent'), 0)}%，输入 {_fmt_number(item.get('input_voltage'), 1)}V，{alerts}"
            )
        return "\n".join(lines)

    def nvr_status_text(self) -> str:
        return "NVR/海康监控模块已从当前中控主服务归档移除，暂不在飞书机器人里查询。"

    def proxy_status_text(self) -> str:
        ok, payload = self.get_json("/api/proxy/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"代理接口暂时不可用：{payload}"
        online = "在线" if payload.get("online") else "离线"
        lines = [f"代理状态：{online}，目标健康 {payload.get('healthy_target_count', 0)}/{payload.get('check_count', 0)}"]
        for item in payload.get("checks") or []:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}：{'正常' if item.get('healthy') else '异常'}，{item.get('latency_ms') or '--'}ms")
        clients = payload.get("clients") if isinstance(payload.get("clients"), dict) else {}
        if clients:
            lines.append(f"活跃客户端：{clients.get('active_client_count', 0)}")
        return "\n".join(lines)

    def local_model_status_text(self) -> str:
        ok, payload = self.get_json("/api/local-model/config", timeout_sec=3.0)
        if not ok or not isinstance(payload, dict):
            return f"本地模型配置接口暂时不可用：{payload}"
        cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        return (
            f"本地模型：{'启用' if cfg.get('enabled') else '停用'}，模型 {cfg.get('model') or '--'}\n"
            f"入口：{cfg.get('base_url') or '--'}\n"
            f"vLLM：{cfg.get('vllm_base_url') or '--'}"
        )

    def software_playback_text(self) -> str:
        return (
            "软件播控运维要点：\n"
            "- tab 切换不要自动全选内容数据，避免误操作。\n"
            "- 素材在播放窗口内缩放，类似素材布局，支持缩放和偏移。\n"
            "- 素材优化由主备机器调用加快，优先识别 HVC/H.265 以外素材和警告素材。\n"
            "- 复制节目页不带窗口名称；显示管理新增屏幕时可能卡住，先修改一次后再保存。\n"
            "- 警告提示需要能定位到素材位置，锁定屏幕会退出转码优化。\n"
            "- 单独节目传输应避免拖时广播，按选中素材或节目节点右键更新。\n"
            "- 传输带宽限制要按现场网络实测设置，避免占满链路导致卡顿或通讯异常。\n"
            "- 无线跑满但有线空闲时，要规划传输优先级、指定传输、暂停传输等策略。\n"
            "- 日志建议从主控统一提取，记录主控与显示端时间差，显示端运行后尽量无需远程。\n"
            "- 独立机器状态管理应同时关注带宽机器状态和软件状态。"
        )

    def answer_intent(self, intent: str, query: str = "") -> str:
        intent = _normalize_intent(intent)
        if intent == "overview":
            return self.status_text()
        if intent == "offline_devices":
            return self.offline_devices_text()
        if intent == "energy_overview" or intent == "energy_history":
            return self.meter_energy_text(query)
        if intent == "current_collector":
            return self.current_collector_text()
        if intent == "server_status":
            return self.server_status_text(query)
        if intent == "door_status":
            return self.door_status_text(query)
        if intent == "environment_status":
            return self.environment_status_text(query)
        if intent == "hvac_status":
            return self.hvac_status_text(query)
        if intent == "lighting_status":
            return self.lighting_status_text()
        if intent == "lighting_logs":
            return self.log_text(query, category="light")
        if intent == "automation_status":
            return self.automation_status_text()
        if intent == "automation_logs":
            return self.log_text(query, event_type="automation")
        if intent == "event_logs":
            return self.log_text(query)
        if intent == "snmp_status":
            return self.snmp_status_text()
        if intent == "ups_status":
            return self.ups_status_text()
        if intent == "proxy_status":
            return self.proxy_status_text()
        if intent == "local_model_status":
            return self.local_model_status_text()
        if intent in {"control_request", "forbidden_control"}:
            return "飞书机器人已支持控制；请说清楚设备和动作，例如：打开庭院灯、关闭机房空调、唤醒门口LED服务器。强电柜和时序电源会要求二次确认。"
        return self.query_text(query)

    def query_text(self, keyword: str) -> str:
        keyword = re.sub(r"\s+", " ", str(keyword or "").strip())
        if not keyword:
            return "我在。可以问：现在状态、哪些设备离线、昨日电量、近7天用电、当前电流、服务器状态、最近自动化日志、UPS状态。"
        lowered = keyword.lower()
        if _contains_any(keyword, SOFTWARE_PLAYBACK_WORDS):
            return self.software_playback_text()
        if _contains_any(keyword, DOOR_WORDS):
            return self.door_status_text(keyword)
        if _contains_any(keyword, ("日志", "记录", "最近发生", "事件")):
            if _contains_any(keyword, ("自动化", "场景", "联动")):
                return self.answer_intent("automation_logs", keyword)
            if _contains_any(keyword, ("灯", "灯光", "庭院灯")):
                return self.answer_intent("lighting_logs", keyword)
            return self.answer_intent("event_logs", keyword)
        if _contains_any(keyword, ("电流", "采集器")):
            return self.current_collector_text()
        if _contains_any(keyword, ("离线", "异常", "不在线", "掉线", "故障")):
            if _server_like_query(keyword, lowered):
                return self.server_status_text(keyword)
            return self.offline_devices_text()
        asks_energy = (
            _contains_any(keyword, ("电量", "用电", "耗电", "能耗", "功率", "电表", "度电", "多少电", "用了", "耗了"))
            or "kwh" in lowered
            or "kw" in lowered
            or ("电" in keyword and _contains_any(keyword, ("今天", "今日", "昨天", "昨日", "本月", "多少", "消耗")))
            or (_contains_any(keyword, ("本周", "这周", "近7天", "最近7天", "7天", "近30天", "最近30天", "30天")) and _contains_any(keyword, ("电", "能耗", "消耗", "合计", "累计")))
        )
        if asks_energy:
            return self.meter_energy_text(keyword)
        if _server_like_query(keyword, lowered):
            return self.server_status_text(keyword)
        if _contains_any(keyword, ("环境", "温度", "湿度", "光照", "传感器")):
            return self.environment_status_text(keyword)
        if _contains_any(keyword, ("空调", "hvac", "HVAC")):
            return self.hvac_status_text(keyword)
        if _contains_any(keyword, ("灯光", "继电器", "灯状态", "哪些灯")):
            return self.lighting_status_text()
        if _contains_any(keyword, ("自动化", "场景", "联动", "规则")):
            return self.automation_status_text()
        if _contains_any(keyword, ("ups", "UPS", "电池", "旁路", "输入电压", "负载", "续航")):
            return self.ups_status_text()
        if _contains_any(keyword, ("snmp", "SNMP", "nas", "NAS", "交换机", "网关", "网络设备", "存储")):
            return self.snmp_status_text()
        if _contains_any(keyword, ("nvr", "NVR", "录像机", "摄像头")):
            return self.nvr_status_text()
        if _contains_any(keyword, ("代理", "chatgpt", "ChatGPT", "google", "Google", "youtube", "YouTube", "github", "GitHub")):
            return self.proxy_status_text()
        if _contains_any(keyword, ("本地模型", "模型服务", "qwen", "Qwen", "vllm", "vLLM", "知识模型")):
            return self.local_model_status_text()
        if _contains_any(keyword, ("设备", "概览", "状态", "在线", "情况", "现在")):
            return self.status_text()
        return "我还没识别到要查什么。可以问：哪些设备离线、昨日电量、近7天用电、最近日志、当前电流、服务器状态、UPS状态。"


class FeishuBot:
    def __init__(
        self,
        config: FeishuBotConfig,
        local_client: LocalSmartCenterClient | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        require_runtime(config)
        self.config = config
        self.local_client = local_client or LocalSmartCenterClient(
            config.smart_center_base_url,
            config.request_timeout_sec,
        )
        self.intent_classifier = (
            LocalModelIntentClassifier(config.nl_model_url, config.nl_model_name, config.nl_model_timeout_sec)
            if config.nl_model_enabled
            else None
        )
        self.control_translator = (
            LocalModelControlTranslator(config.nl_model_url, config.nl_model_name, config.nl_model_timeout_sec)
            if config.nl_model_enabled
            else None
        )
        self.log = log or (lambda text: print(text, flush=True))
        self.api_client = (
            lark.Client.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .log_level(LogLevel.INFO)
            .build()
        )
        self.ws_client = self._build_ws_client()
        self._stop_scheduler = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._sent_push_keys: set[str] = set()
        self._pending_controls: dict[str, dict[str, Any]] = {}
        self._pending_controls_lock = threading.Lock()
        self._load_pending_controls()

    def _build_ws_client(self):
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.handle_message_event)
            .register_p2_card_action_trigger(self.handle_card_action)
            .build()
        )
        return lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=handler,
            log_level=LogLevel.INFO,
        )

    def start(self) -> None:
        self.start_scheduler()
        self.log("Feishu long-connection bot starting...")
        self.log(f"Smart center base URL: {self.config.smart_center_base_url}")
        if self.config.default_chat_id:
            self.log(f"Default push chat_id: {self.config.default_chat_id}")
        else:
            self.log("Default push chat_id is empty. Send a group message and copy chat_id from logs.")
        if self.config.push_times:
            self.log(f"Scheduled push times: {', '.join(self.config.push_times)}")
        self.log(f"Feishu card callback buttons enabled: {self.config.card_callback_enabled}")
        if self.intent_classifier:
            self.log(f"NL intent model: {self.config.nl_model_name} at {self.config.nl_model_url}")
        policy = self._natural_language_policy()
        self.log(
            "Feishu control policy: "
            f"enabled={policy.get('feishu_control_enabled')} "
            f"require_confirmation={policy.get('feishu_control_require_confirmation')}"
        )
        self.ws_client.start()

    def _natural_language_policy(self) -> dict[str, Any]:
        policy = load_runtime_natural_language_policy()
        env_enabled = self.config.feishu_control_enabled
        if env_enabled:
            policy["feishu_control_enabled"] = True
        policy["feishu_control_require_confirmation"] = bool(
            policy.get("feishu_control_require_confirmation", True) or self.config.feishu_control_require_confirmation
        )
        return policy

    def start_scheduler(self) -> None:
        if not self.config.default_chat_id or not self.config.push_times:
            return
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, name="feishu-push-scheduler", daemon=True)
        self._scheduler_thread.start()

    def _scheduler_loop(self) -> None:
        while not self._stop_scheduler.is_set():
            now = datetime.now()
            hhmm = now.strftime("%H:%M")
            day = date.today().isoformat()
            for push_time in self.config.push_times:
                key = f"{day}:{push_time}"
                if hhmm == push_time and key not in self._sent_push_keys:
                    self._sent_push_keys.add(key)
                    self.send_text(self.config.default_chat_id, self.local_client.daily_text())
                    self.log(f"[scheduled push] chat_id={self.config.default_chat_id} time={push_time}")
            if len(self._sent_push_keys) > 16:
                self._sent_push_keys = {item for item in self._sent_push_keys if item.startswith(day)}
            self._stop_scheduler.wait(20)

    def handle_message_event(self, event: P2ImMessageReceiveV1) -> None:
        message = getattr(getattr(event, "event", None), "message", None)
        if not message:
            return
        chat_id = str(getattr(message, "chat_id", "") or "").strip()
        message_id = str(getattr(message, "message_id", "") or "").strip()
        text = _strip_mentions(_json_text(getattr(message, "content", "")), getattr(message, "mentions", None))
        self.log(f"[message] chat_id={chat_id} message_id={message_id} text={text!r}")
        if not chat_id:
            self.log("[message ignored] missing chat_id")
            return
        result = self.dispatch_command(text, chat_id=chat_id)
        if isinstance(result, dict) and result.get("send_card"):
            if not self.send_card(chat_id, result.get("card") or {}):
                self.send_text(chat_id, str(result.get("fallback_text") or "需要确认，但卡片发送失败。请回复“执行”或“取消”。"))
            return
        self.send_text(chat_id, str(result))

    def handle_card_action(self, event: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        action = getattr(getattr(event, "event", None), "action", None)
        context = getattr(getattr(event, "event", None), "context", None)
        value = getattr(action, "value", None) if action else None
        value = value if isinstance(value, dict) else {}
        chat_id = str(value.get("chat_id") or getattr(context, "open_chat_id", "") or "").strip()
        decision = str(value.get("decision") or "").strip().lower()
        pending_id = str(value.get("pending_id") or "").strip()
        self.log(f"[card action] chat_id={chat_id} decision={decision} pending_id={pending_id}")
        trace = NaturalLanguageTrace(
            source="feishu",
            text=f"card_action:{decision}",
            actor={"chat_id": chat_id, "pending_id": pending_id},
            policy=self._natural_language_policy(),
        )
        trace.add_step("confirm", "收到飞书卡片按钮", data={"decision": decision, "pending_id": pending_id}, ok=True)
        if decision in {"confirm", "execute"}:
            text = self._execute_pending_control(chat_id, expected_pending_id=pending_id, trace=trace)
            trace.finish(intent="control", outcome="executed" if "成功" in text else "control_blocked", reply=text)
            toast_type = "success" if "成功" in text or "已确认" in text else "warning"
            return self._card_action_response(text, toast_type=toast_type, done_text=text)
        if decision == "cancel":
            text = self._cancel_pending_control(chat_id, expected_pending_id=pending_id)
            trace.add_step("confirm", "已取消飞书待确认控制", detail=text, ok=True)
            trace.finish(intent="control", outcome="cancelled", reply=text)
            return self._card_action_response(text, toast_type="success", done_text=text)
        trace.add_step("confirm", "无法识别卡片按钮动作", detail=decision, ok=False)
        trace.finish(intent="control", outcome="unknown_card_action", reply="无法识别按钮动作，请重新下发。")
        return self._card_action_response("无法识别按钮动作，请重新下发。", toast_type="warning")

    def _pending_key(self, chat_id: str) -> str:
        return str(chat_id or "_local").strip() or "_local"

    def _load_pending_controls(self) -> None:
        try:
            payload = json.loads(PENDING_CONTROL_STORE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception as exc:
            self.log(f"[pending load failed] {exc}")
            return
        if not isinstance(payload, dict):
            return
        now = time.time()
        loaded: dict[str, dict[str, Any]] = {}
        for key, pending in payload.items():
            if not isinstance(pending, dict):
                continue
            if now > float(pending.get("expires_at", 0.0) or 0.0):
                continue
            loaded[str(key)] = pending
        self._pending_controls.update(loaded)

    def _save_pending_controls_locked(self) -> None:
        try:
            RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
            tmp = PENDING_CONTROL_STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._pending_controls, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(PENDING_CONTROL_STORE)
        except Exception as exc:
            self.log(f"[pending save failed] {exc}")

    def _pop_pending_control(self, chat_id: str) -> dict[str, Any] | None:
        key = self._pending_key(chat_id)
        with self._pending_controls_lock:
            pending = self._pending_controls.pop(key, None)
        if not pending:
            return None
        if time.time() > float(pending.get("expires_at", 0.0) or 0.0):
            return {"expired": True}
        return pending

    def _pending_control_by_id(self, chat_id: str, expected_pending_id: str = "", *, pop: bool = True) -> dict[str, Any] | None:
        key = self._pending_key(chat_id)
        with self._pending_controls_lock:
            self._load_pending_controls()
            pending = self._pending_controls.get(key)
            if not pending and expected_pending_id:
                for item_key, item in self._pending_controls.items():
                    if isinstance(item, dict) and str(item.get("pending_id") or "") == expected_pending_id:
                        key = item_key
                        pending = item
                        break
            if pending and expected_pending_id and str(pending.get("pending_id") or "") != expected_pending_id:
                return {"mismatch": True}
            if pending and pop:
                self._pending_controls.pop(key, None)
                self._save_pending_controls_locked()
        if not pending:
            return None
        if time.time() > float(pending.get("expires_at", 0.0) or 0.0):
            return {"expired": True}
        return pending

    def _execute_pending_control(self, chat_id: str, expected_pending_id: str = "", trace: NaturalLanguageTrace | None = None) -> str:
        pending = self._pending_control_by_id(chat_id, expected_pending_id=expected_pending_id, pop=True)
        if not pending:
            reply = "未执行：当前没有待确认控制。可能是旧卡片、服务重启前卡片，或测试卡片没有生成真实待确认任务。请重新下发控制命令。"
            if trace:
                trace.add_step("confirm", "没有找到待确认控制", detail=reply, ok=False)
            return reply
        if pending.get("mismatch"):
            reply = "未执行：这张确认卡片已不是最新请求，请使用最新卡片或重新下发。"
            if trace:
                trace.add_step("confirm", "确认卡片不是最新请求", detail=reply, ok=False)
            return reply
        if pending.get("expired"):
            command = pending.get("command") if isinstance(pending.get("command"), dict) else None
            state_text = self.local_client.control_state_text(command)
            reply = f"未执行：待确认控制已过期，请重新下发。{chr(10) + state_text if state_text else ''}"
            if trace:
                trace.add_step("confirm", "待确认控制已过期", detail=reply, data=summarize_command_for_process(command), ok=False)
            return reply
        command = pending.get("command")
        if not isinstance(command, dict):
            reply = "未执行：待确认控制格式无效，请重新下发。"
            if trace:
                trace.add_step("confirm", "待确认控制格式无效", detail=reply, ok=False)
            return reply
        if trace:
            trace.add_step("confirm", "确认通过，准备执行", data=summarize_command_for_process(command), ok=True)
        policy = self._natural_language_policy()
        if not policy.get("feishu_control_enabled", False):
            reply = "未执行：飞书控制中控执行命令已关闭。查询仍可使用；如需控制，请先在中控 AI 模块打开飞书控制开关。"
            if trace:
                trace.add_step("policy", "飞书控制开关关闭", detail=reply, ok=False)
            return reply
        result = self.local_client.execute_control_command(command)
        if trace:
            trace.add_step("execute", "已调用中控执行链路", detail=result, data=summarize_command_for_process(command), ok="成功" in result)
        ControlLearningStore(CONTROL_FEEDBACK_STORE).append(
            str(pending.get("source_text") or ""),
            command,
            "confirmed",
            reason="Feishu confirmation executed",
        )
        return result

    def _cancel_pending_control(self, chat_id: str, expected_pending_id: str = "") -> str:
        pending = self._pending_control_by_id(chat_id, expected_pending_id=expected_pending_id, pop=True)
        if not pending:
            return "当前没有待确认控制。"
        if pending.get("mismatch"):
            return "这张确认卡片已不是最新请求，请使用最新卡片或重新下发。"
        if pending.get("expired"):
            return "待确认控制已过期，已自动放弃。"
        ControlLearningStore(CONTROL_FEEDBACK_STORE).append(
            str(pending.get("source_text") or ""),
            pending.get("command") if isinstance(pending.get("command"), dict) else None,
            "cancelled",
            reason="Feishu user cancelled pending control",
        )
        return "已取消待确认控制。"

    def _store_pending_control(self, chat_id: str, command: dict[str, Any], source_text: str, *, reason_override: str = "") -> str:
        key = self._pending_key(chat_id)
        expires_at = time.time() + PENDING_CONTROL_TTL_SEC
        pending_id = uuid.uuid4().hex
        with self._pending_controls_lock:
            self._pending_controls[key] = {
                "command": deepcopy(command),
                "source_text": source_text,
                "expires_at": expires_at,
                "pending_id": pending_id,
            }
            self._save_pending_controls_locked()
        label = str(command.get("label") or "设备")
        action = _format_control_action(str(command.get("action") or ""))
        confidence = str(command.get("confidence") or "high")
        reason = str(command.get("inference_reason") or "").strip()
        if confidence in INFERRED_CONTROL_CONFIDENCE:
            reason_line = f"\n推断理由：{reason}" if reason else ""
            fallback_text = (
                f"这是我的推断，请你确认后再执行：{label} -> {action}{reason_line}\n"
                "点击卡片按钮，或回复“执行/确认”执行，回复“取消”放弃；如果不对，请补充更完整的设备名称或编号。\n"
                "提示：确认有效期 10 分钟。"
            )
            return self._pending_control_card_payload(
                chat_id,
                pending_id,
                label,
                action,
                fallback_text,
                title="需要确认推断",
                template="blue",
                reason=reason,
                high_risk=False,
            )
        if reason_override:
            fallback_text = (
                f"控制请求已解析，需要确认：{label} -> {action}\n"
                f"原因：{reason_override}\n"
                "点击卡片按钮，或回复“执行/确认”执行，回复“取消”放弃。\n"
                "提示：确认有效期 10 分钟。"
            )
            return self._pending_control_card_payload(
                chat_id,
                pending_id,
                label,
                action,
                fallback_text,
                title="控制执行确认",
                template="yellow",
                reason=reason_override,
                high_risk=False,
            )
        fallback_text = (
            f"高风险操作需要二次确认：{label} -> {action}\n"
            "点击卡片按钮，或回复“执行/确认”执行，回复“取消”放弃。\n"
            "提示：确认有效期 10 分钟。"
        )
        return self._pending_control_card_payload(
            chat_id,
            pending_id,
            label,
            action,
            fallback_text,
            title="高风险操作确认",
            template="red",
            reason="强电柜、时序电源或推断类控制需要人工确认。",
            high_risk=True,
        )

    def _dispatch_control_command(self, normalized: str, chat_id: str = "", trace: NaturalLanguageTrace | None = None) -> str | None:
        if _is_cancel_text(normalized):
            return self._cancel_pending_control(chat_id)
        if _is_confirmation_text(normalized):
            return self._execute_pending_control(chat_id, trace=trace)
        if not _is_control_request(normalized):
            return None
        policy = self._natural_language_policy()
        if trace:
            trace.event["policy"] = policy
            trace.add_step("classify", "识别为飞书控制请求", data={"control_enabled": policy.get("feishu_control_enabled")}, ok=True)
        command = self.local_client.resolve_control_command_with_translator(normalized, translator=self.control_translator)
        if not command:
            if trace:
                trace.add_step("route", "未匹配到可执行设备", ok=False)
            return "我识别到这是控制请求，但没有明确匹配到可执行设备。请带上设备名称、编号或 IP。"
        if command.get("type") == "error":
            if trace:
                trace.add_step("route", "安全路由拒绝控制", detail=command.get("message") or "", data=summarize_command_for_process(command), ok=False)
            return str(command.get("message") or "控制请求无法执行。")
        command_policy = describe_control_policy(
            command,
            high_risk_types=HIGH_RISK_CONTROL_TYPES,
            inferred_confidences=INFERRED_CONTROL_CONFIDENCE,
            require_confirmation=bool(policy.get("feishu_control_require_confirmation", True)),
        )
        if trace:
            trace.add_step("route", "控制目标已解析", data={"command": summarize_command_for_process(command), "control_policy": command_policy}, ok=True)
        if not policy.get("feishu_control_enabled", False):
            reply = (
                "已识别为控制请求，但当前已关闭飞书控制中控执行命令。\n"
                f"目标：{command.get('label') or '设备'}\n"
                f"动作：{_format_control_action(str(command.get('action') or ''))}\n"
                "查询指令仍可正常使用；如需执行，请先在中控 AI 模块打开飞书控制开关。"
            )
            if trace:
                trace.add_step("policy", "飞书控制开关关闭，未进入执行", detail=reply, ok=False)
            return reply
        if command_policy.get("requires_confirmation", False):
            reply = self._store_pending_control(chat_id, command, normalized, reason_override=str(command_policy.get("reason") or "飞书控制需要确认"))
            if trace:
                trace.add_step(
                    "confirm",
                    "已生成飞书待确认控制",
                    detail=str(command_policy.get("reason") or "飞书控制需要确认"),
                    data=summarize_command_for_process(command),
                    ok=True,
                )
            return reply
        result = self.local_client.execute_control_command(command)
        if trace:
            trace.add_step("execute", "已调用中控执行链路", detail=result, data=summarize_command_for_process(command), ok="成功" in result)
        ControlLearningStore(CONTROL_FEEDBACK_STORE).append(
            normalized,
            command,
            "direct_executed",
            reason="Feishu low-risk direct execution",
        )
        return result

    def dispatch_command(self, text: str, chat_id: str = "") -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        trace = NaturalLanguageTrace(
            source="feishu",
            text=normalized,
            actor={"chat_id": chat_id},
            policy=self._natural_language_policy(),
        )
        if not normalized:
            reply = "我在。可以直接问状态，也可以下发控制，例如打开庭院灯、关闭机房空调。强电柜和时序电源会二次确认。"
            trace.add_step("classify", "空消息", ok=True)
            trace.finish(intent="help", outcome="help", reply=reply)
            return reply
        control_reply = self._dispatch_control_command(normalized, chat_id=chat_id, trace=trace)
        if control_reply is not None:
            outcome = "control_reply"
            if isinstance(control_reply, dict) and control_reply.get("send_card"):
                outcome = "pending_confirmation"
            elif "已关闭飞书控制" in str(control_reply) or "未执行" in str(control_reply):
                outcome = "control_blocked"
            trace.finish(intent="control", outcome=outcome, reply=str(control_reply))
            return control_reply
        if normalized in {"状态", "/状态", "status", "/status"}:
            trace.add_step("classify", "内置状态命令", ok=True)
            reply = self.local_client.status_text()
            trace.finish(intent="overview", outcome="answered", reply=reply)
            return reply
        if normalized in {"日报", "/日报", "daily", "/daily"}:
            trace.add_step("classify", "内置日报命令", ok=True)
            reply = self.local_client.daily_text()
            trace.finish(intent="daily", outcome="answered", reply=reply)
            return reply
        if normalized.startswith(("查询 ", "/查询 ")):
            query = normalized.split(" ", 1)[1]
            trace.add_step("classify", "显式查询命令", data={"query": query}, ok=True)
            reply = self.local_client.query_text(query)
            trace.finish(intent="query", outcome="answered", reply=reply)
            return reply
        if normalized in {"帮助", "/帮助", "help", "/help"}:
            reply = (
                "可以直接问：哪些设备离线、昨日电量、近7天用电、最近自动化日志、当前电流、服务器状态、UPS状态。\n"
                "也可以控制：打开庭院灯、关闭机房空调、唤醒门口LED服务器、投影机开机。\n"
                "飞书控制可由中控 AI 模块总开关启停；强电柜、时序电源和所有启用控制都会先要求确认。"
            )
            trace.add_step("classify", "帮助命令", ok=True)
            trace.finish(intent="help", outcome="answered", reply=reply)
            return reply
        if self.intent_classifier:
            classified = self.intent_classifier.classify(normalized)
            if classified:
                intent = str(classified.get("intent") or "unknown")
                query = str(classified.get("query") or normalized)
                self.log(f"[nl intent] text={normalized!r} intent={intent!r}")
                trace.add_step("model", "本地模型完成意图分类", data=classified, ok=True)
                if intent != "unknown":
                    reply = self.local_client.answer_intent(intent, query)
                    trace.finish(intent=intent, outcome="answered", reply=reply)
                    return reply
        trace.add_step("classify", "使用确定性查询兜底", ok=True)
        reply = self.local_client.query_text(normalized)
        trace.finish(intent="query", outcome="answered", reply=reply)
        return reply

    def _pending_control_card_payload(
        self,
        chat_id: str,
        pending_id: str,
        label: str,
        action: str,
        fallback_text: str,
        *,
        title: str,
        template: str,
        reason: str = "",
        high_risk: bool = False,
    ) -> dict[str, Any]:
        risk_text = "高风险操作，请确认现场安全后再执行。" if high_risk else "这是系统推断结果，请确认目标无误。"
        callback_hint = "点击按钮，或回复“执行/确认”执行，回复“取消”放弃。"
        if not self.config.card_callback_enabled:
            callback_hint = "当前飞书应用尚未启用卡片回调，请直接回复“执行/确认”执行，回复“取消”放弃。"
        elements: list[dict[str, Any]] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**目标：** {label}\n**动作：** {action}\n**提示：** {risk_text}\n**确认：** {callback_hint}",
                },
            }
        ]
        if reason:
            elements.append({"tag": "hr"})
            elements.append({"tag": "div", "text": {"tag": "plain_text", "content": f"原因：{reason}"}})
        if self.config.card_callback_enabled:
            elements.extend(
                [
                    {"tag": "hr"},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "确认执行"},
                                "type": "primary",
                                "value": {"decision": "confirm", "pending_id": pending_id, "chat_id": chat_id},
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "取消"},
                                "type": "default",
                                "value": {"decision": "cancel", "pending_id": pending_id, "chat_id": chat_id},
                            },
                        ],
                    },
                ]
            )
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "10 分钟内有效；飞书卡片回调配置完成后可启用按钮确认。"}
                ],
            }
        )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        }
        return {"send_card": True, "card": card, "fallback_text": fallback_text}

    def _done_card(self, text: str, *, template: str = "green") -> dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": "处理结果"}},
            "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": text}}],
        }

    def _card_action_response(self, text: str, *, toast_type: str = "success", done_text: str = ""):
        response = P2CardActionTriggerResponse()
        response.toast = CallBackToast({"type": toast_type, "content": text})
        response.card = CallBackCard({"type": "raw", "data": self._done_card(done_text or text, template="green" if toast_type == "success" else "yellow")})
        return response

    def send_text(self, chat_id: str, text: str) -> bool:
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .uuid(str(uuid.uuid4()))
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        response = self.api_client.im.v1.message.create(request)
        if response.success():
            return True
        self.log(f"[send failed] code={response.code} msg={response.msg} log_id={response.get_log_id()}")
        return False

    def send_card(self, chat_id: str, card: dict[str, Any]) -> bool:
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .uuid(str(uuid.uuid4()))
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        response = self.api_client.im.v1.message.create(request)
        if response.success():
            return True
        self.log(f"[send card failed] code={response.code} msg={response.msg} log_id={response.get_log_id()}")
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the smart center Feishu long-connection bot.")
    parser.add_argument("--env-file", default="", help="Optional env file path. Defaults to .env in project root.")
    parser.add_argument("--send-daily-now", action="store_true", help="Send one daily report to FEISHU_DEFAULT_CHAT_ID and exit.")
    parser.add_argument("--print-status", action="store_true", help="Print local status text and exit without connecting Feishu.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.env_file or None)
    local_client = LocalSmartCenterClient(config.smart_center_base_url, config.request_timeout_sec)
    if args.print_status:
        print(local_client.status_text())
        return 0
    bot = FeishuBot(config, local_client=local_client)
    if args.send_daily_now:
        if not config.default_chat_id:
            raise SystemExit("FEISHU_DEFAULT_CHAT_ID is required for --send-daily-now.")
        return 0 if bot.send_text(config.default_chat_id, local_client.daily_text()) else 1
    bot.start()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nFeishu bot stopped.", flush=True)
