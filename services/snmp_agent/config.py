# AI_MODULE: snmp_agent_config
# AI_PURPOSE: 121 独立 SNMP 采集服务的配置加载、设备归一化和运行参数解析。
# AI_BOUNDARY: 不执行 SNMP 通信；通信由 services.snmp_agent.poller 调用 snmp_core 完成。
# AI_DATA_FLOW: smart-center config.json 或 agent JSON -> SnmpAgentConfig -> FastAPI/poller。
# AI_RUNTIME: smart-snmp-agent 启动时加载，也可通过 SIGHUP/重启刷新。
# AI_RISK: 中，配置路径或默认值错误会导致 121 agent 没有设备或轮询过密。
# AI_SEARCH_KEYWORDS: snmp-agent, config, 121, remote snmp.

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 6916
DEFAULT_MAX_WORKERS = 4
DEFAULT_IDLE_SLEEP_SEC = 0.25
DEFAULT_CONFIG_RELOAD_SEC = 30.0


@dataclass(frozen=True)
class SnmpAgentConfig:
    devices: list[dict[str, Any]]
    listen_host: str = DEFAULT_LISTEN_HOST
    listen_port: int = DEFAULT_LISTEN_PORT
    max_workers: int = DEFAULT_MAX_WORKERS
    idle_sleep_sec: float = DEFAULT_IDLE_SLEEP_SEC
    config_reload_sec: float = DEFAULT_CONFIG_RELOAD_SEC
    source_config_path: str = ""


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _local_ipv4_addresses() -> set[str]:
    addresses = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(str(item[4][0]))
    except Exception:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        addresses.add(str(probe.getsockname()[0]))
        probe.close()
    except Exception:
        pass
    return addresses


def _default_config_path() -> Path:
    raw = str(os.environ.get("SMART_SNMP_AGENT_CONFIG") or os.environ.get("SMART_CENTER_CONFIG_FILE") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path("/srv/smart-center-data/config.json")


def _normalize_device(item: dict[str, Any]) -> dict[str, Any]:
    device = dict(item or {})
    if not str(device.get("id") or "").strip():
        host = str(device.get("host") or device.get("ip") or "unknown").strip().replace(".", "_")
        device["id"] = f"snmp_{host}"
    if "host" not in device:
        device["host"] = device.get("ip", "")
    device["port"] = _as_int(device.get("port"), 161)
    device["poll_interval_ms"] = max(1000, _as_int(device.get("poll_interval_ms"), 5000))
    device["timeout_sec"] = max(0.5, _as_float(device.get("timeout_sec"), 2.0))
    device["retries"] = max(0, _as_int(device.get("retries"), 1))
    forced_source_ip = str(os.environ.get("SMART_SNMP_AGENT_SOURCE_IP") or "").strip()
    if forced_source_ip:
        device["source_ip"] = forced_source_ip
    elif str(device.get("source_ip") or "").strip() and str(device.get("source_ip") or "").strip() not in _local_ipv4_addresses():
        # 生产配置中 H3C 可能固定为 192.168.50.120；迁移到 121 后不能绑定 120 地址。
        device["source_ip"] = ""
    device.setdefault("enabled", True)
    device.setdefault("visible", True)
    device.setdefault("walk_enabled", True)
    return device


def load_agent_config() -> SnmpAgentConfig:
    path = _default_config_path()
    payload = _load_json_file(path) if path.exists() else {}
    agent_cfg = payload.get("snmp_agent", {}) if isinstance(payload.get("snmp_agent", {}), dict) else {}
    devices = payload.get("snmp_devices", [])
    if isinstance(payload.get("devices"), list) and not devices:
        devices = payload.get("devices", [])
    normalized_devices = [
        _normalize_device(item)
        for item in (devices if isinstance(devices, list) else [])
        if isinstance(item, dict)
    ]
    return SnmpAgentConfig(
        devices=normalized_devices,
        listen_host=str(os.environ.get("SMART_SNMP_AGENT_HOST") or agent_cfg.get("host") or DEFAULT_LISTEN_HOST),
        listen_port=max(1, _as_int(os.environ.get("SMART_SNMP_AGENT_PORT") or agent_cfg.get("port"), DEFAULT_LISTEN_PORT)),
        max_workers=max(1, _as_int(os.environ.get("SMART_SNMP_AGENT_MAX_WORKERS") or agent_cfg.get("max_workers"), DEFAULT_MAX_WORKERS)),
        idle_sleep_sec=max(0.05, _as_float(os.environ.get("SMART_SNMP_AGENT_IDLE_SLEEP_SEC") or agent_cfg.get("idle_sleep_sec"), DEFAULT_IDLE_SLEEP_SEC)),
        config_reload_sec=max(5.0, _as_float(os.environ.get("SMART_SNMP_AGENT_CONFIG_RELOAD_SEC") or agent_cfg.get("config_reload_sec"), DEFAULT_CONFIG_RELOAD_SEC)),
        source_config_path=str(path),
    )
