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
    return FeishuBotConfig(
        app_id=str(os.environ.get("FEISHU_APP_ID", "") or "").strip(),
        app_secret=str(os.environ.get("FEISHU_APP_SECRET", "") or "").strip(),
        default_chat_id=str(os.environ.get("FEISHU_DEFAULT_CHAT_ID", "") or "").strip(),
        smart_center_base_url=str(os.environ.get("SMART_CENTER_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/"),
        push_times=push_times,
        request_timeout_sec=timeout,
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

    def query_text(self, keyword: str) -> str:
        keyword = re.sub(r"\s+", " ", str(keyword or "").strip())
        if not keyword:
            return "我在。可以问：现在状态、哪些设备离线、昨日电量、今日用电、本月用电、当前电流、服务器状态。"
        lowered = keyword.lower()
        if _contains_any(keyword, ("开灯", "关灯", "开关", "控制", "重启", "关机", "执行", "下发")):
            return "当前飞书机器人只支持只读查询，不执行开关、重启、下发控制等操作。"
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
        if _contains_any(keyword, ("设备", "概览", "状态", "在线", "情况", "现在")):
            return self.status_text()
        return "我还没识别到要查什么。可以问：哪些设备离线、昨日电量、今日用电、本月用电、当前电流、服务器状态。"


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
            return "可以直接问：哪些设备离线、昨日电量、今日用电、本月用电、当前电流、服务器状态。当前仅支持只读查询。"
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
