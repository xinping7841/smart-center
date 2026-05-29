# AI_MODULE: snmp_agent_poller
# AI_PURPOSE: 121 独立 SNMP 采集服务的多设备并发轮询、失败退避、缓存和健康摘要。
# AI_BOUNDARY: 复用 snmp_core.poll_snmp_device 做协议解析；本模块只调度、缓存和暴露状态。
# AI_DATA_FLOW: SnmpAgentConfig.devices -> poll_snmp_device -> in-memory cache -> /status。
# AI_RUNTIME: FastAPI startup 后后台线程运行；不依赖 Flask，不启动中控其它后台任务。
# AI_RISK: 中高，轮询过密会打满设备或网络；失败判断过激会导致页面误报离线。
# AI_SEARCH_KEYWORDS: snmp-agent, polling, cache, ThreadPoolExecutor, status.

from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any

from snmp_core import poll_snmp_device

from .config import SnmpAgentConfig, load_agent_config


def _now_iso() -> str:
    return datetime.now().isoformat()


def _status_label(level: str) -> str:
    normalized = str(level or "").strip().lower()
    if normalized == "online":
        return "在线"
    if normalized == "stale":
        return "陈旧"
    if normalized == "error":
        return "异常"
    return "离线"


def _apply_status_level(status: dict[str, Any]) -> dict[str, Any]:
    payload = dict(status or {})
    online = bool(payload.get("online"))
    stale = bool(payload.get("stale"))
    has_error = bool(payload.get("last_error") or payload.get("error"))
    has_history = bool(payload.get("last_success_at") or payload.get("updated_at"))
    if online and stale:
        level = "stale"
    elif online:
        level = "online"
    elif has_error and has_history:
        level = "error"
    elif has_error:
        level = "error"
    else:
        level = "offline"
    payload["status_level"] = level
    payload["status_label"] = _status_label(level)
    return payload


def _build_success(previous: dict[str, Any], fresh: dict[str, Any], now_iso: str, now_mono: float) -> dict[str, Any]:
    payload = dict(previous or {})
    payload.update(dict(fresh or {}))
    payload["updated_at"] = now_iso
    payload["last_checked_at"] = now_iso
    payload["last_success_at"] = now_iso
    payload["last_polled_monotonic"] = now_mono
    payload["poll_failures"] = 0
    payload["stale"] = False
    payload["error"] = ""
    payload["last_error"] = ""
    payload["last_error_at"] = None
    return _apply_status_level(payload)


def _build_failure(
    previous: dict[str, Any],
    error: Any,
    now_iso: str,
    now_mono: float,
    interval_sec: float,
    *,
    defaults: dict[str, Any] | None = None,
    max_failures: int = 3,
    grace_factor: float = 3.5,
    min_grace_sec: float = 15.0,
) -> dict[str, Any]:
    payload = dict(defaults or {})
    payload.update(dict(previous or {}))
    next_failures = int(payload.get("poll_failures", 0) or 0) + 1
    last_polled = float(payload.get("last_polled_monotonic", 0.0) or 0.0)
    within_grace = bool(
        payload.get("online")
        and last_polled
        and (now_mono - last_polled) <= max(min_grace_sec, interval_sec * grace_factor)
        and next_failures < max_failures
    )
    err_text = str(error or "SNMP poll failed")
    payload["online"] = within_grace
    had_success = bool(payload.get("updated_at") or payload.get("last_success_at"))
    payload["stale"] = bool(had_success and not within_grace)
    payload["error"] = err_text
    payload["last_error"] = err_text
    payload["last_error_at"] = now_iso
    payload["last_checked_at"] = now_iso
    payload["last_polled_monotonic"] = now_mono
    payload["poll_failures"] = next_failures
    if not payload.get("updated_at"):
        payload["updated_at"] = None
    payload.pop("status_level", None)
    payload.pop("status_label", None)
    return _apply_status_level(payload)


class SnmpAgentPoller:
    def __init__(self, config: SnmpAgentConfig | None = None):
        self._config = config or load_agent_config()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._in_flight: dict[str, Future] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._started_at = _now_iso()
        self._last_config_reload_mono = 0.0
        self._last_loop_error = ""
        self._last_loop_error_at = None

    @property
    def config(self) -> SnmpAgentConfig:
        return self._config

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._executor = ThreadPoolExecutor(
                max_workers=self._config.max_workers,
                thread_name_prefix="smart-snmp-agent",
            )
            self._thread = threading.Thread(target=self._run_loop, name="smart-snmp-agent-loop", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)

    def reload_config(self) -> SnmpAgentConfig:
        next_config = load_agent_config()
        with self._lock:
            old_workers = self._config.max_workers
            self._config = next_config
            active_ids = {str(item.get("id")) for item in next_config.devices}
            for device_id in list(self._status.keys()):
                if device_id not in active_ids:
                    self._status.pop(device_id, None)
                    self._in_flight.pop(device_id, None)
            if next_config.max_workers != old_workers:
                old_executor = self._executor
                self._executor = ThreadPoolExecutor(
                    max_workers=next_config.max_workers,
                    thread_name_prefix="smart-snmp-agent",
                )
                if old_executor:
                    old_executor.shutdown(wait=False, cancel_futures=True)
        return next_config

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            devices = copy.deepcopy(self._status)
            in_flight_ids = sorted(self._in_flight.keys())
            config = self._config
            loop_alive = bool(self._thread and self._thread.is_alive())
        total = len([item for item in config.devices if item.get("enabled", True) is not False])
        online = sum(1 for item in devices.values() if bool(item.get("online")))
        stale = sum(1 for item in devices.values() if bool(item.get("stale")))
        errors = sum(1 for item in devices.values() if item.get("status_level") == "error" or item.get("last_error"))
        return {
            "agent": {
                "name": "smart-snmp-agent",
                "version": "2026.05.28",
                "host_role": "node-121",
                "started_at": self._started_at,
                "generated_at": _now_iso(),
                "source_config_path": config.source_config_path,
                "loop_alive": loop_alive,
                "max_workers": config.max_workers,
                "in_flight": in_flight_ids,
                "last_loop_error": self._last_loop_error,
                "last_loop_error_at": self._last_loop_error_at,
            },
            "summary": {
                "configured": len(config.devices),
                "enabled": total,
                "cached": len(devices),
                "online": online,
                "offline": max(0, total - online),
                "stale": stale,
                "errors": errors,
            },
            "devices": devices,
        }

    def _poll_one(self, cfg: dict[str, Any]) -> None:
        device_id = str(cfg.get("id"))
        interval_sec = max(1.0, float(cfg.get("poll_interval_ms", 5000) or 5000) / 1000.0)
        with self._lock:
            previous = copy.deepcopy(self._status.get(device_id, {}) or {})
        try:
            fresh = dict(poll_snmp_device(cfg, previous_status=previous) or {})
            now_mono = time.monotonic()
            now_iso = _now_iso()
            if bool(fresh.get("online")):
                next_status = _build_success(previous, fresh, now_iso, now_mono)
            else:
                next_status = _build_failure(
                    previous,
                    fresh.get("error") or "SNMP poll returned offline",
                    now_iso,
                    now_mono,
                    interval_sec,
                    defaults={
                        "summary": dict(fresh.get("summary", {}) or previous.get("summary", {}) or {}),
                        "alert_counts": dict(fresh.get("alert_counts", {}) or previous.get("alert_counts", {}) or {}),
                    },
                )
        except Exception as exc:
            now_mono = time.monotonic()
            now_iso = _now_iso()
            next_status = _build_failure(
                previous,
                exc,
                now_iso,
                now_mono,
                interval_sec,
                defaults={"summary": dict(previous.get("summary", {}) or {}), "alert_counts": dict(previous.get("alert_counts", {}) or {})},
            )
        next_status["agent_collected_at"] = next_status.get("last_checked_at") or _now_iso()
        next_status["agent_source"] = "node-121-smart-snmp-agent"
        with self._lock:
            self._status[device_id] = next_status

    def _submit_due_devices(self) -> None:
        with self._lock:
            cfg = self._config
            devices = list(cfg.devices)
            executor = self._executor
            in_flight = dict(self._in_flight)
            status = self._status
        if executor is None:
            return

        for device_id, future in list(in_flight.items()):
            if not future.done():
                continue
            try:
                future.result()
            except Exception as exc:
                self._last_loop_error = str(exc)
                self._last_loop_error_at = _now_iso()
            with self._lock:
                self._in_flight.pop(device_id, None)

        active_ids = {str(item.get("id")) for item in devices}
        with self._lock:
            for device_id in list(self._status.keys()):
                if device_id not in active_ids:
                    self._status.pop(device_id, None)
                    self._in_flight.pop(device_id, None)

        now = time.monotonic()
        due_devices: list[dict[str, Any]] = []
        with self._lock:
            current_in_flight = set(self._in_flight.keys())
            available_slots = max(0, self._config.max_workers - len(current_in_flight))
            for device in devices:
                if available_slots <= 0:
                    break
                if device.get("enabled", True) is False or device.get("visible", True) is False:
                    continue
                device_id = str(device.get("id"))
                if device_id in current_in_flight:
                    continue
                state = status.get(device_id, {}) or {}
                interval_ms = max(1000, int(device.get("poll_interval_ms", 5000) or 5000))
                last_polled = float(state.get("last_polled_monotonic", 0.0) or 0.0)
                if (now - last_polled) * 1000 >= interval_ms:
                    due_devices.append(device)
            due_devices.sort(key=lambda item: float((status.get(str(item.get("id")), {}) or {}).get("last_polled_monotonic", 0.0) or 0.0))
            for device in due_devices[:available_slots]:
                device_id = str(device.get("id"))
                self._in_flight[device_id] = executor.submit(self._poll_one, dict(device))

    def _maybe_reload_config(self) -> None:
        now = time.monotonic()
        if now - self._last_config_reload_mono < self._config.config_reload_sec:
            return
        self._last_config_reload_mono = now
        try:
            self.reload_config()
        except Exception as exc:
            self._last_loop_error = f"config_reload_failed: {exc}"
            self._last_loop_error_at = _now_iso()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._maybe_reload_config()
                self._submit_due_devices()
            except Exception as exc:
                self._last_loop_error = str(exc)
                self._last_loop_error_at = _now_iso()
            self._stop_event.wait(max(0.05, self._config.idle_sleep_sec))

