# AI_MODULE: feishu_bot_service
# AI_PURPOSE: Connect the smart center to Feishu by long connection, reply to chat commands, and run scheduled pushes.
# AI_BOUNDARY: This module only reads local HTTP APIs and sends Feishu messages; it must not issue device control commands.
# AI_DATA_FLOW: Feishu event -> command parser -> local smart-center HTTP APIs -> Feishu message API.
# AI_RUNTIME: Run as a standalone process with run_feishu_bot.py or start_feishu_bot.bat.
# AI_RISK: Medium, bad credentials or chat_id stop notifications; command scope is intentionally read-only.
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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        P2ImMessageReceiveV1,
    )
    from lark_oapi.core.enum import LogLevel
except Exception as exc:  # pragma: no cover - depends on local install
    lark = None
    CreateMessageRequest = None
    CreateMessageRequestBody = None
    P2ImMessageReceiveV1 = Any
    LogLevel = None
    _LARK_IMPORT_ERROR = exc
else:
    _LARK_IMPORT_ERROR = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
    "开灯",
    "关灯",
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
CONTROL_STATUS_WORDS = ("状态", "日志", "记录", "历史", "有没有", "是否", "查询", "查看", "显示", "汇总")
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
    nl_model_enabled: bool = False
    nl_model_url: str = "http://127.0.0.1:11434"
    nl_model_name: str = "qwen3:14b"
    nl_model_timeout_sec: float = 8.0


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
        model_timeout = max(1.0, min(float(os.environ.get("FEISHU_NL_MODEL_TIMEOUT_SEC", "8") or 8), 60.0))
    except Exception:
        model_timeout = 8.0
    return FeishuBotConfig(
        app_id=str(os.environ.get("FEISHU_APP_ID", "") or "").strip(),
        app_secret=str(os.environ.get("FEISHU_APP_SECRET", "") or "").strip(),
        default_chat_id=str(os.environ.get("FEISHU_DEFAULT_CHAT_ID", "") or "").strip(),
        smart_center_base_url=str(os.environ.get("SMART_CENTER_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/"),
        push_times=push_times,
        request_timeout_sec=timeout,
        nl_model_enabled=str(os.environ.get("FEISHU_NL_MODEL_ENABLED", "") or "").strip().lower() in {"1", "true", "yes", "on"},
        nl_model_url=str(os.environ.get("FEISHU_NL_MODEL_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434").strip().rstrip("/"),
        nl_model_name=str(os.environ.get("FEISHU_NL_MODEL_NAME", "qwen3:14b") or "qwen3:14b").strip(),
        nl_model_timeout_sec=model_timeout,
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
    if not _contains_any(normalized, CONTROL_ACTION_WORDS):
        return False
    return not _contains_any(normalized, CONTROL_STATUS_WORDS)


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
    text = str(value or "").strip().lower()
    if not text:
        return ""
    replacements = {
        "一号": "1号",
        "二号": "2号",
        "三号": "3号",
        "四号": "4号",
        "五号": "5号",
        "六号": "6号",
        "七号": "7号",
        "八号": "8号",
        "九号": "9号",
        "十号": "10号",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"[\s\-_:：,，.。/\\()（）\[\]【】]+", "", text)


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
        "control": "forbidden_control",
    }
    return aliases.get(text, text)


class OllamaIntentClassifier:
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
        "forbidden_control",
        "unknown",
    )

    def __init__(self, base_url: str, model: str, timeout_sec: float = 8.0) -> None:
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen3:14b"
        self.timeout_sec = timeout_sec

    def classify(self, text: str) -> dict[str, Any] | None:
        prompt = (
            "你是中控飞书机器人的意图分类器，只输出 JSON，不要输出解释。\n"
            "当前只允许查询状态、历史数据、日志、统计和诊断，不允许任何控制动作。\n"
            "可选 intent："
            + ", ".join(self.INTENTS)
            + "\n"
            "如果用户要求开关、控制、重启、关机、唤醒、下发、执行、修改配置、调空调、执行场景，intent 必须是 forbidden_control。\n"
            "如果是查询日志或历史记录，优先选择 event_logs、automation_logs、lighting_logs 或 energy_history。\n"
            "返回格式：{\"intent\":\"...\",\"query\":\"原问题\",\"allowed\":true,\"reason\":\"\"}\n"
            f"用户问题：{text}"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0},
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_sec,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            raw = str(data.get("response") or "").strip()
            parsed = json.loads(raw)
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
        ok, payload = self.get_json("/api/env/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"门磁接口暂时不可用：{payload}"
        summary_ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        name_map: dict[str, str] = {}
        if summary_ok and isinstance(summary, dict):
            modules = summary.get("modules") if isinstance(summary.get("modules"), dict) else {}
            env_module = modules.get("env") if isinstance(modules.get("env"), dict) else {}
            for device in env_module.get("devices") or []:
                if isinstance(device, dict) and device.get("id"):
                    name_map[str(device.get("id"))] = _device_name(device)
        rows = []
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
            rows.append(f"- {name}：{state}，{online}，更新 {updated}")
        if not rows:
            return "没有匹配到门磁/大门状态。"
        return "\n".join(["门磁状态：", *rows[:8], *(["... 还有更多门磁未显示"] if len(rows) > 8 else [])])

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
        if intent == "forbidden_control":
            return "当前只支持查询状态、历史数据和日志，不执行开关、重启、下发控制、配置修改等操作。"
        return self.query_text(query)

    def query_text(self, keyword: str) -> str:
        keyword = re.sub(r"\s+", " ", str(keyword or "").strip())
        if not keyword:
            return "我在。可以问：现在状态、哪些设备离线、昨日电量、近7天用电、当前电流、服务器状态、最近自动化日志、UPS状态。"
        lowered = keyword.lower()
        if _is_control_request(keyword):
            return self.answer_intent("forbidden_control", keyword)
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
        if _contains_any(keyword, ("本地模型", "模型服务", "ollama", "Ollama", "qwen", "Qwen")):
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
            OllamaIntentClassifier(config.nl_model_url, config.nl_model_name, config.nl_model_timeout_sec)
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

    def _build_ws_client(self):
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.handle_message_event)
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
        if self.intent_classifier:
            self.log(f"NL intent model: {self.config.nl_model_name} at {self.config.nl_model_url}")
        self.ws_client.start()

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
        self.send_text(chat_id, self.dispatch_command(text))

    def dispatch_command(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized:
            return "我在。可以直接问：哪些设备离线、昨日电量、今日用电、本月用电、当前电流、服务器状态。"
        if _is_control_request(normalized):
            return self.local_client.answer_intent("forbidden_control", normalized)
        if normalized in {"状态", "/状态", "status", "/status"}:
            return self.local_client.status_text()
        if normalized in {"日报", "/日报", "daily", "/daily"}:
            return self.local_client.daily_text()
        if normalized.startswith(("查询 ", "/查询 ")):
            return self.local_client.query_text(normalized.split(" ", 1)[1])
        if normalized in {"帮助", "/帮助", "help", "/help"}:
            return "可以直接问：哪些设备离线、昨日电量、近7天用电、最近自动化日志、当前电流、服务器状态、UPS状态。当前仅支持只读查询。"
        if self.intent_classifier:
            classified = self.intent_classifier.classify(normalized)
            if classified:
                intent = str(classified.get("intent") or "unknown")
                query = str(classified.get("query") or normalized)
                self.log(f"[nl intent] text={normalized!r} intent={intent!r}")
                if intent != "unknown":
                    return self.local_client.answer_intent(intent, query)
        return self.local_client.query_text(normalized)

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
