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
    "nvr": "录像机",
    "power": "电表",
    "proxy": "代理",
    "sequencer": "时序器",
    "server": "服务器",
    "snmp": "网络设备",
    "ups": "UPS",
}


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
        offline += int(value.get("offline") or 0)
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


def _fmt_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    formatted = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


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
        "nvr": "nvr_status",
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
        "environment_status",
        "hvac_status",
        "lighting_status",
        "lighting_logs",
        "automation_status",
        "automation_logs",
        "event_logs",
        "snmp_status",
        "ups_status",
        "nvr_status",
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
            "中控在线",
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"本地接口：{self.base_url}",
        ]
        ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=3.0)
        if ok:
            counts = _aggregate_dashboard_counts((summary or {}).get("counts", {}) or {})
            modules = (summary or {}).get("modules", {}) or {}
            total = int(counts.get("total") or 0)
            online = int(counts.get("online") or 0)
            offline = int(counts.get("offline") or max(0, total - online))
            lines.append(f"设备概览：在线 {online}/{total}，离线 {offline}")
            server = (modules.get("server") or {}) if isinstance(modules, dict) else {}
            if server:
                lines.append(f"服务器：在线 {server.get('online', 0)}/{server.get('total', 0)}")
        else:
            lines.append(f"概览接口：不可用（{summary}）")
        lines.append(self.current_collector_text())
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
        ok, payload = self.get_json("/api/meters?target=total&period=day&days=7", timeout_sec=5.0)
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
        lines: list[str]
        if _contains_any(normalized, ("昨天", "昨日", "昨日电量")):
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
        ok, summary = self.get_json("/api/dashboard/summary", timeout_sec=4.0)
        if not ok or not isinstance(summary, dict):
            return f"服务器接口暂时不可用：{summary}"
        modules = summary.get("modules", {}) if isinstance(summary.get("modules"), dict) else {}
        server = modules.get("server") if isinstance(modules.get("server"), dict) else {}
        machines = [item for item in server.get("machines", []) if isinstance(item, dict)]
        total = int(server.get("total") or len(machines) or 0)
        online = int(server.get("online") or sum(1 for item in machines if item.get("is_online")))
        offline = [item for item in machines if item.get("is_online") is False]

        lines = [f"服务器：在线 {online}/{total}，离线 {max(total - online, len(offline))}"]
        if _contains_any(query, ("离线", "异常", "不在线")) and offline:
            for item in offline[:10]:
                last_online = item.get("last_online") or "--"
                lines.append(f"- {_device_name(item)}（{item.get('ip') or '--'}，最后在线 {last_online}）")
            if len(offline) > 10:
                lines.append(f"... 还有 {len(offline) - 10} 台未显示")
            return "\n".join(lines)

        for item in machines[:5]:
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            state = "在线" if item.get("is_online") else "离线"
            cpu = _fmt_number(status.get("cpu_percent"), 1)
            disk = _fmt_number(status.get("disk_percent"), 1)
            lines.append(f"- {_device_name(item)}：{state}，CPU {cpu}%，磁盘 {disk}%")
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
        ok, payload = self.get_json("/api/nvr/status", timeout_sec=4.0)
        if not ok or not isinstance(payload, dict):
            return f"NVR 接口暂时不可用：{payload}"
        lines = ["NVR/摄像头状态："]
        for device_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            name = item.get("name") or device_id
            online = "在线" if item.get("online", True) else "离线"
            channels = item.get("channels") if isinstance(item.get("channels"), list) else []
            lines.append(f"- {name}：{online}，通道 {len(channels)}")
        return "\n".join(lines)

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
        if intent == "nvr_status":
            return self.nvr_status_text()
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
        if _contains_any(keyword, ("开灯", "关灯", "开关", "控制", "重启", "关机", "执行", "下发", "唤醒", "设置", "修改", "调温", "制冷", "制热")) and not _contains_any(keyword, ("状态", "日志", "记录", "历史")):
            return self.answer_intent("forbidden_control", keyword)
        if _contains_any(keyword, ("日志", "记录", "最近发生", "事件")):
            if _contains_any(keyword, ("自动化", "场景", "联动")):
                return self.answer_intent("automation_logs", keyword)
            if _contains_any(keyword, ("灯", "灯光", "庭院灯")):
                return self.answer_intent("lighting_logs", keyword)
            return self.answer_intent("event_logs", keyword)
        if _contains_any(keyword, ("电流", "采集器")):
            return self.current_collector_text()
        if _contains_any(keyword, ("离线", "异常", "不在线", "掉线", "故障")):
            if _contains_any(keyword, ("服务器", "主机", "机器", "电脑", "节点")):
                return self.server_status_text(keyword)
            return self.offline_devices_text()
        asks_energy = (
            _contains_any(keyword, ("电量", "用电", "耗电", "能耗", "功率", "电表", "度电", "多少电", "用了", "耗了"))
            or "kwh" in lowered
            or "kw" in lowered
            or ("电" in keyword and _contains_any(keyword, ("今天", "今日", "昨天", "昨日", "本月", "多少", "消耗")))
        )
        if asks_energy:
            return self.meter_energy_text(keyword)
        if _contains_any(keyword, ("服务器", "主机", "机器", "电脑", "节点")):
            return self.server_status_text(keyword)
        if _contains_any(keyword, ("环境", "温度", "湿度", "光照", "门磁", "传感器")):
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
