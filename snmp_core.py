# AI_MODULE: snmp_core
# AI_PURPOSE: SNMP 轮询、OID 解析、厂商摘要、接口/存储/告警归一化。
# AI_BOUNDARY: 不做页面布局；前端展示由 static/js/views/snmp.js 负责，API 只传结构化结果。
# AI_DATA_FLOW: CONFIG.snmp_devices -> SNMP get/walk -> normalized status -> runtime.state.SNMP_STATUS。
# AI_RUNTIME: background.py 周期轮询，api/snmp.py 也可能做单设备测试。
# AI_RISK: 中，容量/端口/VLAN/告警判断错误会误导网络排障；轮询过重会拖慢页面和设备。
# AI_COMPAT: QNAP、飞牛、爱快、H3C 的 summary/metrics/interface_rows/storage 字段被前端使用。
# AI_SEARCH_KEYWORDS: snmp, oid, qnap, fnos, ikuai, h3c, vlan, interface, storage.

import asyncio
from copy import deepcopy
from datetime import datetime
import re
import subprocess
import time
from typing import Any, Dict, List, Tuple

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    getCmd,
    nextCmd,
    usm3DESEDEPrivProtocol,
    usmAesBlumenthalCfb192Protocol,
    usmAesBlumenthalCfb256Protocol,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC128SHA224AuthProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC256SHA384AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
)

# Module role: SNMP polling, vendor parsing, and normalized status summaries.
# Boundaries: raw OID collection, vendor-specific interpretation, and UI-facing
# summary shaping are still in this file; split them before adding more vendors.
# Performance: API routes should use background SNMP_STATUS snapshots and compact
# payloads instead of running full walks during page refresh.


def _close_snmp_engine(engine: Any) -> None:
    """Release pysnmp UDP transports; older/newer pysnmp expose different names."""
    dispatcher = getattr(engine, "transportDispatcher", None)
    if dispatcher is None:
        dispatcher = getattr(engine, "transport_dispatcher", None)
    if dispatcher is None:
        return
    for method_name in ("closeDispatcher", "close_dispatcher"):
        close_method = getattr(dispatcher, method_name, None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass
            return


DEFAULT_SNMP_OID_MAP = {
    "sys_descr": "1.3.6.1.2.1.1.1.0",
    "sys_object_id": "1.3.6.1.2.1.1.2.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_contact": "1.3.6.1.2.1.1.4.0",
    "sys_name": "1.3.6.1.2.1.1.5.0",
    "sys_location": "1.3.6.1.2.1.1.6.0",
    "if_number": "1.3.6.1.2.1.2.1.0",
}

DEFAULT_SNMP_WALK_ROOTS = [
    "1.3.6.1.2.1.1",
    "1.3.6.1.2.1.2",
    "1.3.6.1.2.1.25",
]

DEFAULT_SWITCH_SNMP_WALK_ROOTS = [
    "1.3.6.1.2.1.1",
    "1.3.6.1.2.1.2.2.1.2",
    "1.3.6.1.2.1.2.2.1.5",
    "1.3.6.1.2.1.2.2.1.7",
    "1.3.6.1.2.1.2.2.1.8",
    "1.3.6.1.2.1.2.2.1.10",
    "1.3.6.1.2.1.2.2.1.13",
    "1.3.6.1.2.1.2.2.1.14",
    "1.3.6.1.2.1.2.2.1.16",
    "1.3.6.1.2.1.2.2.1.19",
    "1.3.6.1.2.1.2.2.1.20",
    "1.3.6.1.2.1.31.1.1.1.1",
    "1.3.6.1.2.1.31.1.1.1.6",
    "1.3.6.1.2.1.31.1.1.1.10",
    "1.3.6.1.2.1.31.1.1.1.15",
    "1.3.6.1.2.1.31.1.1.1.18",
    "1.3.6.1.2.1.17.1.4.1.2",
    "1.3.6.1.2.1.17.4.3.1.2",
    "1.3.6.1.2.1.17.4.3.1.3",
    "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "1.3.6.1.2.1.17.7.1.2.2.1.3",
    "1.3.6.1.2.1.17.7.1.4.3.1.1",
    "1.3.6.1.2.1.17.7.1.4.5.1.1",
]

SWITCH_DIRECT_PORT_OID_ROOTS = {
    "ifName": "1.3.6.1.2.1.31.1.1.1.1",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifInDiscards": "1.3.6.1.2.1.2.2.1.13",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifOutDiscards": "1.3.6.1.2.1.2.2.1.19",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
    "ifHighSpeed": "1.3.6.1.2.1.31.1.1.1.15",
    "ifAlias": "1.3.6.1.2.1.31.1.1.1.18",
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
}

AUTH_PROTOCOL_MAP = {
    "NONE": usmNoAuthProtocol,
    "MD5": usmHMACMD5AuthProtocol,
    "SHA": usmHMACSHAAuthProtocol,
    "SHA1": usmHMACSHAAuthProtocol,
    "SHA224": usmHMAC128SHA224AuthProtocol,
    "SHA256": usmHMAC192SHA256AuthProtocol,
    "SHA384": usmHMAC256SHA384AuthProtocol,
    "SHA512": usmHMAC384SHA512AuthProtocol,
}

PRIV_PROTOCOL_MAP = {
    "NONE": usmNoPrivProtocol,
    "DES": usmDESPrivProtocol,
    "3DES": usm3DESEDEPrivProtocol,
    "AES": usmAesCfb128Protocol,
    "AES128": usmAesCfb128Protocol,
    "AES192": usmAesCfb192Protocol,
    "AES192B": usmAesBlumenthalCfb192Protocol,
    "AES256": usmAesCfb256Protocol,
    "AES256B": usmAesBlumenthalCfb256Protocol,
}


def build_default_snmp_oid_map() -> Dict[str, str]:
    return deepcopy(DEFAULT_SNMP_OID_MAP)


def build_default_snmp_walk_roots() -> List[str]:
    return list(DEFAULT_SNMP_WALK_ROOTS)


def build_default_snmp_walk_roots_for_device(device: Dict[str, Any] | None) -> List[str]:
    current = dict(device or {})
    device_type = str(current.get("device_type") or "").strip().lower()
    if device_type == "switch":
        return list(DEFAULT_SWITCH_SNMP_WALK_ROOTS)
    return build_default_snmp_walk_roots()


def _effective_walk_interval_ms(device: Dict[str, Any] | None) -> int:
    current = dict(device or {})
    device_type = str(current.get("device_type") or "").strip().lower()
    configured = max(1000, _safe_int(current.get("walk_interval_ms"), 20000))
    if device_type == "switch":
        return max(configured, 45000)
    if device_type == "router":
        return max(configured, 30000)
    if device_type == "nas":
        return max(configured, 30000)
    return configured


def _default_walk_roots_per_cycle(device_type: Any) -> int:
    normalized = str(device_type or "").strip().lower()
    if normalized == "switch":
        return 12
    if normalized in {"nas", "router"}:
        return 14
    return 6


def _critical_walk_roots_for_device(device_type: Any) -> List[str]:
    normalized = str(device_type or "").strip().lower()
    if normalized == "nas":
        return [
            "1.3.6.1.2.1.25.2.3.1.3",
            "1.3.6.1.2.1.25.2.3.1.4",
            "1.3.6.1.2.1.25.2.3.1.5",
            "1.3.6.1.2.1.25.2.3.1.6",
            "1.3.6.1.2.1.25.2.2.0",
            "1.3.6.1.2.1.31.1.1.1.1",
            "1.3.6.1.2.1.31.1.1.1.6",
            "1.3.6.1.2.1.31.1.1.1.10",
            "1.3.6.1.4.1.24681.1.2.1",
            "1.3.6.1.4.1.24681.1.2.11",
            "1.3.6.1.4.1.55062.2.10.2.1",
            "1.3.6.1.4.1.55062.2.12.9.1",
        ]
    if normalized == "router":
        return [
            "1.3.6.1.2.1.31.1.1.1.1",
            "1.3.6.1.2.1.2.2.1.2",
            "1.3.6.1.2.1.2.2.1.7",
            "1.3.6.1.2.1.2.2.1.8",
            "1.3.6.1.2.1.31.1.1.1.6",
            "1.3.6.1.2.1.31.1.1.1.10",
            "1.3.6.1.2.1.2.2.1.10",
            "1.3.6.1.2.1.2.2.1.16",
            "1.3.6.1.2.1.25.2.3.1.3",
            "1.3.6.1.2.1.25.2.3.1.4",
            "1.3.6.1.2.1.25.2.3.1.5",
            "1.3.6.1.2.1.25.2.3.1.6",
        ]
    if normalized == "switch":
        return [
            "1.3.6.1.2.1.31.1.1.1.1",
            "1.3.6.1.2.1.2.2.1.2",
            "1.3.6.1.2.1.2.2.1.7",
            "1.3.6.1.2.1.2.2.1.8",
            "1.3.6.1.2.1.31.1.1.1.6",
            "1.3.6.1.2.1.31.1.1.1.10",
            "1.3.6.1.2.1.2.2.1.10",
            "1.3.6.1.2.1.2.2.1.16",
        ]
    return []


def _priority_walk_roots_for_device(device_type: Any) -> List[str]:
    normalized = str(device_type or "").strip().lower()
    system_roots = [
        "1.3.6.1.2.1.1",
        "1.3.6.1.2.1.25.2.2.0",
        "1.3.6.1.2.1.25.1.6.0",
        "1.3.6.1.2.1.25.1.5.0",
        "1.3.6.1.2.1.25.1.4.0",
    ]
    storage_roots = [
        "1.3.6.1.2.1.25.2.3.1.3",
        "1.3.6.1.2.1.25.2.3.1.4",
        "1.3.6.1.2.1.25.2.3.1.5",
        "1.3.6.1.2.1.25.2.3.1.6",
    ]
    ucd_roots = [
        "1.3.6.1.4.1.2021.4",
        "1.3.6.1.4.1.2021.9",
        "1.3.6.1.4.1.2021.10",
        "1.3.6.1.4.1.2021.11",
        "1.3.6.1.4.1.2021.13",
    ]
    qnap_roots = [
        "1.3.6.1.4.1.24681.1.2.1",
        "1.3.6.1.4.1.24681.1.2.2",
        "1.3.6.1.4.1.24681.1.2.3",
        "1.3.6.1.4.1.24681.1.2.11",
        "1.3.6.1.4.1.55062.2.10.2.1",
        "1.3.6.1.4.1.55062.2.12.9.1",
    ]
    interface_roots = [
        "1.3.6.1.2.1.31.1.1.1.1",
        "1.3.6.1.2.1.2.2.1.2",
        "1.3.6.1.2.1.2.2.1.5",
        "1.3.6.1.2.1.2.2.1.7",
        "1.3.6.1.2.1.2.2.1.8",
        "1.3.6.1.2.1.31.1.1.1.15",
        "1.3.6.1.2.1.31.1.1.1.18",
        "1.3.6.1.2.1.31.1.1.1.6",
        "1.3.6.1.2.1.31.1.1.1.10",
        "1.3.6.1.2.1.2.2.1.10",
        "1.3.6.1.2.1.2.2.1.16",
        "1.3.6.1.2.1.2.2.1.13",
        "1.3.6.1.2.1.2.2.1.14",
        "1.3.6.1.2.1.2.2.1.19",
        "1.3.6.1.2.1.2.2.1.20",
    ]
    if normalized == "switch":
        return interface_roots + [
            "1.3.6.1.2.1.17.1.4.1.2",
            "1.3.6.1.2.1.17.4.3.1.2",
            "1.3.6.1.2.1.17.4.3.1.3",
            "1.3.6.1.2.1.17.7.1.2.2.1.2",
            "1.3.6.1.2.1.17.7.1.2.2.1.3",
            "1.3.6.1.2.1.17.7.1.4.3.1.1",
            "1.3.6.1.2.1.17.7.1.4.5.1.1",
        ]
    if normalized == "nas":
        return system_roots + storage_roots + qnap_roots + interface_roots + ucd_roots
    if normalized == "router":
        return system_roots + interface_roots + storage_roots + ucd_roots + [
            "1.3.6.1.4.1.7375.1.2.1",
        ]
    return interface_roots[:10]


def _effective_timeout_sec(config: Dict[str, Any] | None) -> float:
    current = dict(config or {})
    device_type = str(current.get("device_type") or "").strip().lower()
    configured = max(0.5, _safe_float(current.get("timeout_sec"), 2.0))
    minimum = 2.0
    if device_type == "switch":
        minimum = 2.0
    elif device_type == "router":
        minimum = 1.8
    elif device_type == "nas":
        minimum = 1.8
    return max(configured, minimum)


def _effective_retries(config: Dict[str, Any] | None) -> int:
    current = dict(config or {})
    configured = max(0, _safe_int(current.get("retries"), 1))
    return min(2, max(configured, 1))


def _augment_walk_roots_for_device(device: Dict[str, Any] | None, roots: List[str]) -> List[str]:
    current = dict(device or {})
    normalized = [str(root or "").strip() for root in (roots or []) if str(root or "").strip()]
    device_type = str(current.get("device_type") or "").strip().lower()
    preferred = _priority_walk_roots_for_device(device_type)
    remainder = [root for root in normalized if root not in preferred]
    extras = [root for root in preferred if root not in normalized]
    normalized = [root for root in preferred if root in normalized] + extras + remainder
    deduped: List[str] = []
    for root in normalized:
        if root and root not in deduped:
            deduped.append(root)
    return deduped


def _normalize_protocol_name(value: Any) -> str:
    text = str(value or "").upper()
    for token in ["-", "_", " ", "/"]:
        text = text.replace(token, "")
    return text


def _normalize_version(version: Any) -> str:
    text = str(version or "v2c").strip().lower()
    if text in {"1", "v1", "snmpv1"}:
        return "v1"
    if text in {"2", "2c", "v2", "v2c", "snmpv2", "snmpv2c"}:
        return "v2c"
    if text in {"3", "v3", "snmpv3"}:
        return "v3"
    return "v2c"


def _normalize_security_level(level: Any) -> str:
    compact = str(level or "noAuthNoPriv").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return {
        "noauthnopriv": "noAuthNoPriv",
        "authnopriv": "authNoPriv",
        "authpriv": "authPriv",
    }.get(compact, "noAuthNoPriv")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_walk_roots(value: Any) -> List[str]:
    if isinstance(value, str):
        items = value.replace("\r", "\n").split("\n")
    elif isinstance(value, list):
        items = value
    else:
        items = []
    roots: List[str] = []
    for item in items:
        oid = str(item or "").strip()
        if oid and oid not in roots:
            roots.append(oid)
    return roots


def _decode_hex_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text.startswith("0x") or len(text) <= 2:
        return text
    hex_text = text[2:]
    if len(hex_text) % 2 != 0:
        return text
    try:
        raw = bytes.fromhex(hex_text)
    except Exception:
        return text
    for encoding in ("utf-8", "gbk", "utf-16-be"):
        try:
            decoded = raw.decode(encoding).strip("\x00").strip()
            if decoded:
                return decoded
        except Exception:
            continue
    return text


def _format_memory_gb(kb_value: Any) -> Any:
    kb_num = _safe_float(kb_value, 0.0)
    if kb_num <= 0:
        return None
    return round(kb_num / 1024.0 / 1024.0, 2)


def _format_uptime_text(value: Any) -> str:
    ticks = _safe_int(value, 0)
    if ticks <= 0:
        return "--"
    total_seconds = ticks // 100
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _format_speed_text(speed_bps: Any) -> str:
    speed = _safe_int(speed_bps, 0)
    if speed <= 0:
        return "--"
    if speed >= 1000 * 1000 * 1000:
        return f"{round(speed / 1000 / 1000 / 1000, 2)} Gbps"
    if speed >= 1000 * 1000:
        return f"{round(speed / 1000 / 1000, 2)} Mbps"
    if speed >= 1000:
        return f"{round(speed / 1000, 2)} Kbps"
    return f"{speed} bps"


def _infer_interface_speed_bps(name: Any) -> int:
    text = str(name or "").strip().lower()
    if not text:
        return 0
    if text.startswith(("hundredgige", "hundred-gigabitethernet")):
        return 100 * 1000 * 1000 * 1000
    if text.startswith(("fortygige", "forty-gigabitethernet")):
        return 40 * 1000 * 1000 * 1000
    if text.startswith(("ten-gigabitethernet", "xgigabitethernet", "xge")):
        return 10 * 1000 * 1000 * 1000
    if text.startswith(("gigabitethernet", "ge")):
        return 1000 * 1000 * 1000
    if text.startswith(("fastethernet", "fe")):
        return 100 * 1000 * 1000
    return 0


def _format_bytes_text(byte_value: Any) -> str:
    value = _safe_float(byte_value, 0.0)
    if value <= 0:
        return "--"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    precision = 0 if idx == 0 else 2
    return f"{round(value, precision)} {units[idx]}"


def _format_uptime_seconds_text(seconds_value: Any) -> str:
    total_seconds = _safe_int(seconds_value, 0)
    if total_seconds <= 0:
        return "--"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _format_rate_text(bits_per_sec: Any) -> str:
    speed = _safe_float(bits_per_sec, 0.0)
    if speed <= 0:
        return "--"
    units = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"]
    idx = 0
    while speed >= 1000.0 and idx < len(units) - 1:
        speed /= 1000.0
        idx += 1
    return f"{round(speed, 2)} {units[idx]}"


def _rate_is_reasonable_for_interface(rate_bps: Any, speed_bps: Any) -> bool:
    rate = _safe_float(rate_bps, 0.0)
    if rate <= 0:
        return True
    speed = _safe_float(speed_bps, 0.0)
    if speed > 0:
        return rate <= speed * 1.2
    return rate <= 100_000_000_000.0


def _sanitize_interface_rate_row(row: Dict[str, Any]) -> Dict[str, Any]:
    speed_bps = _safe_float(row.get("speed_bps"), 0.0)
    in_rate_bps = _safe_float(row.get("in_rate_bps"), 0.0)
    out_rate_bps = _safe_float(row.get("out_rate_bps"), 0.0)
    changed = False
    if not _rate_is_reasonable_for_interface(in_rate_bps, speed_bps):
        in_rate_bps = 0.0
        changed = True
    if not _rate_is_reasonable_for_interface(out_rate_bps, speed_bps):
        out_rate_bps = 0.0
        changed = True
    if not changed:
        return row
    row["rate_suppressed"] = True
    row["in_rate_bps"] = round(in_rate_bps, 2)
    row["out_rate_bps"] = round(out_rate_bps, 2)
    row["total_rate_bps"] = round(in_rate_bps + out_rate_bps, 2)
    row["in_rate_text"] = _format_rate_text(in_rate_bps)
    row["out_rate_text"] = _format_rate_text(out_rate_bps)
    row["total_rate_text"] = _format_rate_text(in_rate_bps + out_rate_bps)
    row["traffic_text"] = f"{row['in_rate_text']} / {row['out_rate_text']}"
    if speed_bps > 0 and (in_rate_bps + out_rate_bps) > 0:
        utilization_percent = round(min(100.0, ((in_rate_bps + out_rate_bps) / speed_bps) * 100.0), 2)
        row["utilization_percent"] = utilization_percent
        row["utilization_text"] = f"{utilization_percent}%"
    else:
        row["utilization_percent"] = None
        row["utilization_text"] = "--"
    return row


def _safe_usage_percent(used_value: Any, total_value: Any) -> Any:
    used_num = _safe_float(used_value, -1.0)
    total_num = _safe_float(total_value, -1.0)
    if used_num < 0 or total_num <= 0:
        return None
    return round((used_num / total_num) * 100.0, 1)


def _usage_level(percent_value: Any) -> str:
    percent = _safe_float(percent_value, -1.0)
    if percent < 0:
        return "normal"
    if percent >= 90:
        return "critical"
    if percent >= 80:
        return "warning"
    return "normal"


def _parse_iso_datetime(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _elapsed_seconds(current_iso: Any, previous_iso: Any) -> float:
    current_dt = _parse_iso_datetime(current_iso)
    previous_dt = _parse_iso_datetime(previous_iso)
    if not current_dt or not previous_dt:
        return 0.0
    return max(0.0, (current_dt - previous_dt).total_seconds())


def _elapsed_poll_seconds(result: Dict[str, Any]) -> float:
    current_mono = _safe_float(result.get("polled_monotonic"), 0.0)
    previous_mono = _safe_float(result.get("previous_polled_monotonic"), 0.0)
    if current_mono > 0 and previous_mono > 0 and current_mono >= previous_mono:
        return current_mono - previous_mono
    return _elapsed_seconds(result.get("updated_at"), result.get("previous_updated_at"))


def _elapsed_walk_counter_seconds(result: Dict[str, Any]) -> float:
    current_mono = _safe_float(result.get("last_walk_polled_monotonic"), 0.0)
    previous_mono = _safe_float(result.get("previous_last_walk_polled_monotonic"), 0.0)
    if current_mono > 0 and previous_mono > 0 and current_mono >= previous_mono:
        return current_mono - previous_mono
    elapsed = _elapsed_seconds(result.get("last_walk_updated_at"), result.get("previous_last_walk_updated_at"))
    if elapsed > 0:
        return elapsed
    return _elapsed_poll_seconds(result)


def _compute_counter_rate(current_value: Any, previous_value: Any, elapsed_sec: float, counter_bits: int = 64) -> float:
    if elapsed_sec <= 0:
        return 0.0
    current = _safe_int(current_value, -1)
    previous = _safe_int(previous_value, -1)
    if current < 0 or previous < 0:
        return 0.0
    delta = current - previous
    if delta < 0:
        max_counter = (1 << max(1, int(counter_bits))) - 1
        if max_counter > 0:
            delta = current + (max_counter - previous) + 1
    if delta <= 0:
        return 0.0
    return (float(delta) * 8.0) / elapsed_sec


def _parse_cpu_loads(walk_values: Dict[str, str]) -> List[int]:
    prefix = "1.3.6.1.2.1.25.3.3.1.2."
    items = []
    for oid, value in walk_values.items():
        if not oid.startswith(prefix):
            continue
        try:
            index = int(oid.split(".")[-1])
        except Exception:
            index = 999999
        items.append((index, _safe_int(value, 0)))
    items.sort(key=lambda item: item[0])
    return [value for _, value in items]


def _parse_storage_rows(walk_values: Dict[str, str]) -> List[Dict[str, Any]]:
    descr_by_index: Dict[int, str] = {}
    alloc_by_index: Dict[int, int] = {}
    size_by_index: Dict[int, int] = {}
    used_by_index: Dict[int, int] = {}

    def _safe_index(oid: str) -> int | None:
        try:
            return int(str(oid).split(".")[-1])
        except Exception:
            return None

    for oid, value in walk_values.items():
        if oid.startswith("1.3.6.1.2.1.25.2.3.1.3."):
            idx = _safe_index(oid)
            if idx is not None:
                descr_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.25.2.3.1.4."):
            idx = _safe_index(oid)
            if idx is not None:
                alloc_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.25.2.3.1.5."):
            idx = _safe_index(oid)
            if idx is not None:
                size_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.25.2.3.1.6."):
            idx = _safe_index(oid)
            if idx is not None:
                used_by_index[idx] = _safe_int(value, 0)

    rows: List[Dict[str, Any]] = []
    for idx, descr in sorted(descr_by_index.items(), key=lambda item: item[0]):
        alloc_unit = alloc_by_index.get(idx, 0)
        size_units = size_by_index.get(idx, 0)
        used_units = used_by_index.get(idx, 0)
        total_bytes = alloc_unit * size_units if alloc_unit > 0 and size_units > 0 else 0
        used_bytes = alloc_unit * used_units if alloc_unit > 0 and used_units >= 0 else 0
        desc_lower = descr.lower()
        kind = "other"
        if "physical memory" in desc_lower:
            kind = "memory_physical"
        elif "available memory" in desc_lower:
            kind = "memory_available"
        elif "virtual memory" in desc_lower:
            kind = "memory_virtual"
        elif "swap" in desc_lower:
            kind = "swap"
        elif descr.startswith("/"):
            kind = "filesystem"
        rows.append(
            {
                "index": idx,
                "descr": descr,
                "kind": kind,
                "allocation_unit": alloc_unit,
                "size_units": size_units,
                "used_units": used_units,
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "usage_percent": _safe_usage_percent(used_units, size_units),
                "alert_level": _usage_level(_safe_usage_percent(used_units, size_units)),
                "total_text": _format_bytes_text(total_bytes),
                "used_text": _format_bytes_text(used_bytes),
            }
        )
    return rows


def _is_real_storage_row(row: Dict[str, Any]) -> bool:
    if str(row.get("kind") or "") != "filesystem":
        return False
    descr = str(row.get("descr") or "")
    excluded_prefixes = ["/proc", "/sys", "/run", "/dev", "/tmp", "/var/run", "/var/lock"]
    if any(descr.startswith(prefix) for prefix in excluded_prefixes):
        return False
    return _safe_int(row.get("total_bytes"), 0) >= 1024 * 1024 * 1024


def _apply_storage_aliases(rows: List[Dict[str, Any]], aliases: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    alias_map = {
        str(key or "").strip(): str(value or "").strip()
        for key, value in dict(aliases or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    if not alias_map:
        return list(rows or [])
    mapped_rows: List[Dict[str, Any]] = []
    for row in rows or []:
        current = dict(row or {})
        descr = str(current.get("descr") or "").strip()
        alias = alias_map.get(descr)
        if alias:
            current["mountpoint"] = descr
            current["share_name"] = alias
            current["descr"] = alias
            current["source"] = current.get("source") or "snmp"
        mapped_rows.append(current)
    return mapped_rows


def _is_qnap_snmp_result(result: Dict[str, Any]) -> bool:
    vendor_key = " ".join(
        str(result.get(key) or "")
        for key in ("brand", "model", "name", "sys_descr", "sys_name", "host")
    ).lower()
    return (
        str(result.get("device_type") or "").strip().lower() == "nas"
        and (
            "qnap" in vendor_key
            or "ts-" in vendor_key
            or "威联通" in vendor_key
            or str(result.get("host") or "").strip() == "192.168.30.145"
        )
    )


def _qnap_business_storage_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result_rows: List[Dict[str, Any]] = []
    seen_keys = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        descr = str(row.get("descr") or "").strip()
        mountpoint = str(row.get("mountpoint") or "").strip()
        source_path = mountpoint or descr
        source_path_lower = source_path.lower()
        share_name = str(row.get("share_name") or "").strip()
        if not share_name:
            continue
        if source_path_lower.startswith("/zpool") or "/.qpkg/" in source_path_lower:
            continue
        if source_path in {"/share/ZFS1_DATA", "/share/ZFS531_DATA"}:
            continue
        current = dict(row)
        current["quota_view"] = True
        current["capacity_role"] = "lun_quota" if share_name.upper().startswith("LUN") else "share_quota"
        current["capacity_note"] = "QNAP 共享文件夹/LUN 配额视图，不能与物理存储池容量相加"
        current["source"] = current.get("source") or "snmp"
        key = (current.get("capacity_role"), source_path or share_name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        result_rows.append(current)
    return result_rows


def _build_qnap_drive_bays(disk_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [dict(row or {}) for row in (disk_rows or []) if isinstance(row, dict)]
    hdd_rows = [row for row in rows if str(row.get("media_type") or "").lower() != "ssd"]
    ssd_rows = [row for row in rows if str(row.get("media_type") or "").lower() == "ssd"]

    def _bay(row: Dict[str, Any] | None, bay_type: str, slot_number: int) -> Dict[str, Any]:
        if not row:
            return {
                "bay_type": bay_type,
                "slot_number": slot_number,
                "display_slot": f"{bay_type.upper()}{slot_number}",
                "occupied": False,
                "status": "Empty",
                "alert_level": "empty",
            }
        display_prefix = "SSD" if bay_type == "ssd" else "HDD"
        status = str(row.get("status") or "--").strip()
        level = str(row.get("alert_level") or "normal").strip().lower()
        if level not in {"normal", "warning", "critical"}:
            level = "normal"
        current = dict(row)
        current.update(
            {
                "bay_type": bay_type,
                "slot_number": slot_number,
                "display_slot": f"{display_prefix}{slot_number}",
                "occupied": True,
                "status": status or "--",
                "alert_level": level,
            }
        )
        return current

    hdd_bays = [_bay(hdd_rows[idx] if idx < len(hdd_rows) else None, "hdd", idx + 1) for idx in range(max(5, len(hdd_rows)))]
    ssd_bays = [_bay(ssd_rows[idx] if idx < len(ssd_rows) else None, "ssd", idx + 1) for idx in range(max(4, len(ssd_rows)))]
    empty_count = len([bay for bay in hdd_bays + ssd_bays if not bay.get("occupied")])
    warning_count = len([bay for bay in hdd_bays + ssd_bays if bay.get("alert_level") == "warning"])
    critical_count = len([bay for bay in hdd_bays + ssd_bays if bay.get("alert_level") == "critical"])
    return {
        "layout": "qnap_ts_x73a",
        "hdd_bays": hdd_bays,
        "ssd_bays": ssd_bays,
        "hdd_count": len(hdd_rows),
        "ssd_count": len(ssd_rows),
        "empty_count": empty_count,
        "warning_count": warning_count,
        "critical_count": critical_count,
        "summary_text": f"HDD {len(hdd_rows)} / SSD {len(ssd_rows)} / 空槽 {empty_count}",
    }


def _apply_interface_rate_deltas(rows: List[Dict[str, Any]], previous_rows: List[Dict[str, Any]], elapsed_sec: float) -> None:
    previous_by_index = {int(item.get("index")): item for item in previous_rows if item.get("index") is not None}
    for row in rows:
        current_in = _safe_int(row.get("in_octets"), 0)
        current_out = _safe_int(row.get("out_octets"), 0)
        prev = previous_by_index.get(_safe_int(row.get("index"), -1), {})
        prev_in = _safe_int(prev.get("in_octets"), 0)
        prev_out = _safe_int(prev.get("out_octets"), 0)
        in_rate_bps = 0.0
        out_rate_bps = 0.0
        have_prev_in = "in_octets" in prev
        have_prev_out = "out_octets" in prev
        if elapsed_sec > 0 and have_prev_in:
            in_rate_bps = _compute_counter_rate(current_in, prev_in, elapsed_sec, counter_bits=64)
        if elapsed_sec > 0 and have_prev_out:
            out_rate_bps = _compute_counter_rate(current_out, prev_out, elapsed_sec, counter_bits=64)
        speed_bps = _safe_float(row.get("speed_bps"), 0.0)
        oper_status = str(row.get("oper_status") or "").strip()
        if oper_status and oper_status != "1":
            in_rate_bps = 0.0
            out_rate_bps = 0.0
        max_reasonable_rate = speed_bps * 1.2 if speed_bps > 0 else 100_000_000_000.0
        if in_rate_bps > max_reasonable_rate:
            in_rate_bps = 0.0
        if out_rate_bps > max_reasonable_rate:
            out_rate_bps = 0.0
        row["in_rate_bps"] = round(in_rate_bps, 2)
        row["out_rate_bps"] = round(out_rate_bps, 2)
        row["total_rate_bps"] = round(in_rate_bps + out_rate_bps, 2)
        row["in_rate_text"] = _format_rate_text(in_rate_bps)
        row["out_rate_text"] = _format_rate_text(out_rate_bps)
        row["total_rate_text"] = _format_rate_text(in_rate_bps + out_rate_bps)
        row["traffic_text"] = f"{row['in_rate_text']} / {row['out_rate_text']}"
        row["in_bytes_text"] = _format_bytes_text(current_in)
        row["out_bytes_text"] = _format_bytes_text(current_out)
        utilization_percent = None
        if speed_bps > 0 and (in_rate_bps + out_rate_bps) > 0:
            utilization_percent = round(min(100.0, ((in_rate_bps + out_rate_bps) / speed_bps) * 100.0), 2)
        row["utilization_percent"] = utilization_percent
        row["utilization_text"] = f"{utilization_percent}%" if utilization_percent is not None else "--"


def _carry_forward_interface_rates(rows: List[Dict[str, Any]], previous_summary_rows: List[Dict[str, Any]]) -> None:
    if not rows or not previous_summary_rows:
        return
    previous_by_index = {
        _safe_int(item.get("index"), -1): dict(item or {})
        for item in previous_summary_rows
        if _safe_int(item.get("index"), -1) >= 0
    }
    for row in rows:
        if _safe_float(row.get("total_rate_bps"), 0.0) > 0:
            _sanitize_interface_rate_row(row)
            continue
        idx = _safe_int(row.get("index"), -1)
        if idx < 0:
            continue
        prev = previous_by_index.get(idx)
        if not prev:
            continue
        for key in (
            "in_rate_bps",
            "out_rate_bps",
            "total_rate_bps",
            "in_rate_text",
            "out_rate_text",
            "total_rate_text",
            "traffic_text",
            "utilization_percent",
            "utilization_text",
        ):
            if key in prev and prev.get(key) not in (None, ""):
                row[key] = prev.get(key)
        _sanitize_interface_rate_row(row)


def _build_memory_summary(storage_rows: List[Dict[str, Any]], memory_kb: Any) -> Dict[str, Any]:
    physical_rows = [row for row in storage_rows if row.get("kind") == "memory_physical" and _safe_int(row.get("total_bytes"), 0) > 0]
    available_rows = [row for row in storage_rows if row.get("kind") == "memory_available" and _safe_int(row.get("total_bytes"), 0) > 0]
    swap_rows = [row for row in storage_rows if row.get("kind") == "swap" and _safe_int(row.get("total_bytes"), 0) > 0]

    physical = max(physical_rows, key=lambda item: _safe_int(item.get("total_bytes"), 0), default=None)
    available = max(available_rows, key=lambda item: _safe_int(item.get("total_bytes"), 0), default=None)
    swap = max(swap_rows, key=lambda item: _safe_int(item.get("total_bytes"), 0), default=None)

    memory_total_bytes = _safe_int((physical or {}).get("total_bytes"), 0)
    if memory_total_bytes <= 0:
        memory_total_bytes = _safe_int(memory_kb, 0) * 1024
    memory_used_bytes = _safe_int((physical or {}).get("used_bytes"), 0)
    memory_available_bytes = _safe_int((available or {}).get("total_bytes"), 0)
    memory_usage_percent = physical.get("usage_percent") if isinstance(physical, dict) else None
    if memory_usage_percent is None and memory_total_bytes > 0 and memory_used_bytes > 0:
        memory_usage_percent = _safe_usage_percent(memory_used_bytes, memory_total_bytes)
    if memory_usage_percent is None and memory_total_bytes > 0 and memory_available_bytes > 0 and memory_available_bytes <= memory_total_bytes:
        memory_usage_percent = round(100.0 - ((memory_available_bytes / memory_total_bytes) * 100.0), 1)

    if memory_available_bytes <= 0 and memory_total_bytes > 0 and memory_used_bytes >= 0 and memory_used_bytes <= memory_total_bytes:
        memory_available_bytes = max(0, memory_total_bytes - memory_used_bytes)

    swap_total_bytes = _safe_int((swap or {}).get("total_bytes"), 0)
    swap_used_bytes = _safe_int((swap or {}).get("used_bytes"), 0)
    swap_usage_percent = swap.get("usage_percent") if isinstance(swap, dict) else None

    return {
        "memory_total_bytes": memory_total_bytes or None,
        "memory_total_text": _format_bytes_text(memory_total_bytes),
        "memory_used_bytes": memory_used_bytes if memory_used_bytes > 0 else None,
        "memory_used_text": _format_bytes_text(memory_used_bytes),
        "memory_available_bytes": memory_available_bytes if memory_available_bytes > 0 else None,
        "memory_available_text": _format_bytes_text(memory_available_bytes),
        "memory_usage_percent": memory_usage_percent,
        "memory_alert_level": _usage_level(memory_usage_percent),
        "swap_total_bytes": swap_total_bytes or None,
        "swap_total_text": _format_bytes_text(swap_total_bytes),
        "swap_used_bytes": swap_used_bytes if swap_used_bytes > 0 else None,
        "swap_used_text": _format_bytes_text(swap_used_bytes),
        "swap_usage_percent": swap_usage_percent,
        "swap_alert_level": _usage_level(swap_usage_percent),
    }


def _memory_summary_from_bytes(total_bytes: Any, available_bytes: Any, swap_total_bytes: Any = 0, swap_free_bytes: Any = 0) -> Dict[str, Any]:
    total = _safe_int(total_bytes, 0)
    available = _safe_int(available_bytes, 0)
    if total <= 0:
        return {}
    if available < 0:
        available = 0
    if available > total:
        available = total
    used = max(0, total - available)
    usage_percent = _safe_usage_percent(used, total)
    swap_total = _safe_int(swap_total_bytes, 0)
    swap_free = _safe_int(swap_free_bytes, 0)
    swap_used = max(0, swap_total - swap_free) if swap_total > 0 else 0
    swap_usage_percent = _safe_usage_percent(swap_used, swap_total) if swap_total > 0 else None
    return {
        "memory_total_bytes": total,
        "memory_total_text": _format_bytes_text(total),
        "memory_used_bytes": used,
        "memory_used_text": _format_bytes_text(used),
        "memory_available_bytes": available,
        "memory_available_text": _format_bytes_text(available),
        "memory_usage_percent": usage_percent,
        "memory_alert_level": _usage_level(usage_percent),
        "swap_total_bytes": swap_total or None,
        "swap_total_text": _format_bytes_text(swap_total),
        "swap_used_bytes": swap_used if swap_used > 0 else None,
        "swap_used_text": _format_bytes_text(swap_used),
        "swap_usage_percent": swap_usage_percent,
        "swap_alert_level": _usage_level(swap_usage_percent),
    }


def _sort_network_rows(rows: List[Dict[str, Any]], device_type: str = "") -> List[Dict[str, Any]]:
    normalized_type = str(device_type or "").strip().lower()
    if normalized_type == "router":
        rank_map = {"wan": 0, "lan": 1, "physical": 2, "bond": 3, "bridge": 4, "other": 5, "virtual": 6}
    else:
        rank_map = {"physical": 0, "bond": 1, "wan": 2, "lan": 3, "bridge": 4, "other": 5, "virtual": 6}
    return sorted(
        rows,
        key=lambda item: (
            rank_map.get(str(item.get("kind") or "other"), 99),
            -_safe_float(item.get("total_rate_bps"), 0.0),
            -_safe_int(item.get("speed_bps"), 0),
            str(item.get("name") or ""),
        ),
    )


def _build_active_interface_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    active_rows = sorted(
        [
            dict(row or {})
            for row in rows
            if _safe_float((row or {}).get("total_rate_bps"), 0.0) > 0
            and str((row or {}).get("kind") or "other") in {"physical", "wan", "lan", "bond"}
            and _rate_is_reasonable_for_interface(
                _safe_float((row or {}).get("total_rate_bps"), 0.0),
                (row or {}).get("speed_bps"),
            )
        ],
        key=lambda item: _safe_float(item.get("total_rate_bps"), 0.0),
        reverse=True,
    )
    in_rate_bps = sum(_safe_float(row.get("in_rate_bps"), 0.0) for row in active_rows)
    out_rate_bps = sum(_safe_float(row.get("out_rate_bps"), 0.0) for row in active_rows)
    return {
        "active_count": len(active_rows),
        "active_top_rows": active_rows[:8],
        "active_in_rate_bps": round(in_rate_bps, 2),
        "active_out_rate_bps": round(out_rate_bps, 2),
        "active_total_rate_bps": round(in_rate_bps + out_rate_bps, 2),
        "active_in_rate_text": _format_rate_text(in_rate_bps),
        "active_out_rate_text": _format_rate_text(out_rate_bps),
        "active_total_rate_text": _format_rate_text(in_rate_bps + out_rate_bps),
    }


def _ikuai_role_label(name: Any) -> str:
    text = str(name or "").strip().lower()
    return {
        "lan1": "LAN1 管理网 192.168.99.3",
        "lan2": "LAN2 业务网 192.168.29.1",
        "wan1": "WAN1 物理外网",
        "wan1_ad": "WAN1 拨号出口",
        "eth0": "物理口 eth0 -> LAN1",
        "eth1": "物理口 eth1 -> LAN1",
        "eth2": "物理口 eth2 -> WAN1",
        "eth3": "物理口 eth3 -> LAN2",
    }.get(text, str(name or "").strip() or "--")


def _build_ikuai_summary(
    interface_rows: List[Dict[str, Any]],
    custom_metric_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    rows_by_name = {
        str(row.get("name") or "").strip().lower(): dict(row or {})
        for row in interface_rows
        if str(row.get("name") or "").strip()
    }
    role_defs = [
        ("wan1_ad", "WAN", "拨号出口", "wan"),
        ("wan1", "WAN", "物理外网", "wan"),
        ("lan1", "LAN", "管理网", "lan"),
        ("lan2", "LAN", "业务网", "lan"),
        ("eth0", "PHY", "LAN1 物理口", "physical"),
        ("eth1", "PHY", "LAN1 物理口", "physical"),
        ("eth2", "PHY", "WAN1 物理口", "physical"),
        ("eth3", "PHY", "LAN2 物理口", "physical"),
    ]
    status_fallbacks = {
        "wan1_ad": ["wan1", "eth2"],
        "wan1": ["eth2"],
        "lan1": ["eth0", "eth1"],
        "lan2": ["eth3"],
    }
    traffic_fallbacks = {
        "wan1_ad": ["wan1_ad", "wan1", "eth2"],
        "wan1": ["wan1", "eth2"],
        "lan1": ["lan1", "eth0", "eth1"],
        "lan2": ["lan2", "eth3"],
    }

    def _has_oper_status(row: Dict[str, Any] | None) -> bool:
        return bool(str((row or {}).get("oper_status") or "").strip())

    def _is_oper_up(row: Dict[str, Any] | None) -> bool:
        current = row or {}
        return str(current.get("oper_status") or "").strip() == "1" or bool(current.get("oper_up"))

    def _has_traffic_data(row: Dict[str, Any] | None) -> bool:
        current = row or {}
        return (
            _safe_float(current.get("total_rate_bps"), 0.0) > 0
            or _safe_int(current.get("in_octets"), 0) > 0
            or _safe_int(current.get("out_octets"), 0) > 0
        )

    def _best_named_row(names: List[str], predicate) -> Tuple[str, Dict[str, Any]]:
        for candidate_name in names:
            candidate = rows_by_name.get(candidate_name)
            if candidate and predicate(candidate):
                return candidate_name, candidate
        for candidate_name in names:
            candidate = rows_by_name.get(candidate_name)
            if candidate:
                return candidate_name, candidate
        return "", {}

    def _copy_traffic_fields(row: Dict[str, Any], source_name: str, source: Dict[str, Any]) -> None:
        if not source or not source_name:
            return
        if source_name == str(row.get("name") or "").strip().lower() and _has_traffic_data(row):
            return
        for key in (
            "in_octets",
            "out_octets",
            "in_rate_bps",
            "out_rate_bps",
            "total_rate_bps",
            "in_rate_text",
            "out_rate_text",
            "total_rate_text",
            "traffic_text",
            "in_bytes_text",
            "out_bytes_text",
            "utilization_percent",
            "utilization_text",
        ):
            if key in source:
                row[key] = source.get(key)
        if _safe_float(row.get("speed_bps"), 0.0) <= 0 and _safe_float(source.get("speed_bps"), 0.0) > 0:
            row["speed_bps"] = source.get("speed_bps")
            row["speed_text"] = source.get("speed_text") or _format_speed_text(source.get("speed_bps"))
        row["traffic_source_name"] = source_name

    role_rows: List[Dict[str, Any]] = []
    for name, role, note, expected_kind in role_defs:
        source = rows_by_name.get(name)
        candidate_names = [name] + list(status_fallbacks.get(name, []))
        status_source_name, status_source = _best_named_row(candidate_names, _has_oper_status)
        traffic_source_name, traffic_source = _best_named_row(list(traffic_fallbacks.get(name, [name])), _has_traffic_data)
        if not source and not status_source and not traffic_source:
            continue
        row = dict(source or traffic_source or status_source)
        source_name = str(row.get("name") or "").strip().lower()
        if source_name != name:
            row["source_name"] = source_name
            row["name"] = name
        row["role"] = role
        row["role_note"] = note
        row["expected_kind"] = expected_kind
        row["display_name"] = _ikuai_role_label(name)
        row["status_source_name"] = status_source_name or source_name or name
        if _has_oper_status(row):
            row["oper_up"] = _is_oper_up(row)
            row["status_inferred"] = False
        elif status_source:
            row["oper_status"] = str(status_source.get("oper_status") or "").strip()
            row["oper_up"] = _is_oper_up(status_source)
            row["status_inferred"] = bool(status_source_name and status_source_name != name)
        else:
            row["oper_up"] = False
            row["status_inferred"] = False
        if not _has_traffic_data(row) and traffic_source:
            _copy_traffic_fields(row, traffic_source_name, traffic_source)
        if _is_oper_up(row):
            row["status_text"] = "按物理口在线" if row.get("status_inferred") else "在线"
        elif _has_oper_status(row):
            row["status_text"] = "离线"
        else:
            row["status_text"] = "状态未采到"
        role_rows.append(row)

    wan_rows = [row for row in role_rows if row.get("role") == "WAN"]
    lan_rows = [row for row in role_rows if row.get("role") == "LAN"]
    physical_rows = [row for row in role_rows if row.get("role") == "PHY"]
    primary_wan = max(wan_rows, key=lambda row: _safe_float(row.get("total_rate_bps"), 0.0), default=None)
    primary_lan = max(lan_rows, key=lambda row: _safe_float(row.get("total_rate_bps"), 0.0), default=None)
    total_in = sum(_safe_float(row.get("in_rate_bps"), 0.0) for row in role_rows if row.get("role") in {"WAN", "LAN"})
    total_out = sum(_safe_float(row.get("out_rate_bps"), 0.0) for row in role_rows if row.get("role") in {"WAN", "LAN"})

    issue_rows = []
    for row in role_rows:
        errors = _safe_int(row.get("in_errors"), 0) + _safe_int(row.get("out_errors"), 0)
        discards = _safe_int(row.get("in_discards"), 0) + _safe_int(row.get("out_discards"), 0)
        utilization = _safe_float(row.get("utilization_percent"), 0.0)
        if errors > 0 or discards > 0 or utilization >= 70 or not _is_oper_up(row):
            issue_rows.append(
                {
                    "name": row.get("name"),
                    "display_name": row.get("display_name"),
                    "role": row.get("role"),
                    "status_text": row.get("status_text"),
                    "errors": errors,
                    "discards": discards,
                    "utilization_percent": utilization if utilization > 0 else None,
                    "utilization_text": row.get("utilization_text") or "--",
                    "total_rate_text": row.get("total_rate_text") or "--",
                }
            )

    metric_values = {}
    for metric_name in ("network_connections", "session_count", "nat_sessions", "online_clients", "ap_count", "cpu_temperature_c", "temperature_c"):
        item = custom_metric_map.get(metric_name)
        if isinstance(item, dict) and item.get("value") not in (None, "", "--"):
            metric_values[metric_name] = item.get("value")

    return {
        "role_rows": role_rows,
        "wan_rows": wan_rows,
        "lan_rows": lan_rows,
        "physical_rows": physical_rows,
        "issue_rows": sorted(
            issue_rows,
            key=lambda row: (
                -_safe_int(row.get("errors"), 0),
                -_safe_int(row.get("discards"), 0),
                -_safe_float(row.get("utilization_percent"), 0.0),
                str(row.get("name") or ""),
            ),
        ),
        "primary_wan_name": (primary_wan or {}).get("name") or "",
        "primary_wan_text": f"{(primary_wan or {}).get('display_name') or '--'} · {(primary_wan or {}).get('total_rate_text') or '--'}",
        "primary_lan_name": (primary_lan or {}).get("name") or "",
        "primary_lan_text": f"{(primary_lan or {}).get('display_name') or '--'} · {(primary_lan or {}).get('total_rate_text') or '--'}",
        "mapped_total_rate_bps": round(total_in + total_out, 2),
        "mapped_total_rate_text": _format_rate_text(total_in + total_out),
        "mapped_in_rate_bps": round(total_in, 2),
        "mapped_out_rate_bps": round(total_out, 2),
        "mapped_in_rate_text": _format_rate_text(total_in),
        "mapped_out_rate_text": _format_rate_text(total_out),
        "wan_count": len(wan_rows),
        "lan_count": len(lan_rows),
        "physical_count": len(physical_rows),
        "issue_count": len(issue_rows),
        "version_hint": "3.7.22 x64 Build202604141629",
        "interface_map_text": "lan1->eth0/eth1, lan2->eth3, wan1->eth2, wan1_ad->PPPoE",
        "ssh_console": "sshd@192.168.99.3",
        "metric_values": metric_values,
    }


def _extract_gpu_metrics(custom_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    gpu_metrics: List[Dict[str, Any]] = []
    keywords = ("gpu", "graphics", "graphic", "video", "nvidia", "amd")
    for item in custom_metrics:
        name = str(item.get("name") or "").strip().lower()
        if not name or not any(token in name for token in keywords):
            continue
        gpu_metrics.append(
            {
                "name": item.get("name"),
                "value": item.get("value"),
                "unit": item.get("unit", ""),
            }
        )
    return gpu_metrics[:6]


def _qnap_disk_media_type(row: Dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("model", "vendor", "bus", "slot", "capacity_text")
    ).lower()
    ssd_tokens = ("ssd", "nvme", "m.2", "solid state", "ssdpe", "intel")
    return "ssd" if any(token in text for token in ssd_tokens) else "hdd"


def _qnap_disk_temp_level(media_type: str, temp_c: Any) -> str:
    if temp_c is None:
        return "normal"
    temp_num = _safe_float(temp_c, -1.0)
    if temp_num < 0:
        return "normal"
    if str(media_type or "").lower() == "ssd":
        if temp_num >= 70:
            return "critical"
        if temp_num >= 60:
            return "warning"
        return "normal"
    if temp_num >= 55:
        return "critical"
    if temp_num >= 50:
        return "warning"
    return "normal"


def _qnap_disk_temp_label(media_type: str, temp_c: Any) -> str:
    level = _qnap_disk_temp_level(media_type, temp_c)
    if level == "critical":
        return "温度过高"
    if level == "warning":
        return "温度偏高"
    return "温度正常"


def _parse_qnap_disk_rows(walk_values: Dict[str, str]) -> List[Dict[str, Any]]:
    tables = {
        "slot": "1.3.6.1.4.1.24681.1.2.11.1.2.",
        "temp_text": "1.3.6.1.4.1.24681.1.2.11.1.3.",
        "smart_id": "1.3.6.1.4.1.24681.1.2.11.1.4.",
        "model": "1.3.6.1.4.1.24681.1.2.11.1.5.",
        "capacity_text": "1.3.6.1.4.1.24681.1.2.11.1.6.",
        "status": "1.3.6.1.4.1.24681.1.2.11.1.7.",
        "vendor": "1.3.6.1.4.1.55062.2.10.2.1.3.",
        "serial": "1.3.6.1.4.1.55062.2.10.2.1.5.",
        "bus": "1.3.6.1.4.1.55062.2.10.2.1.6.",
        "health": "1.3.6.1.4.1.55062.2.10.2.1.7.",
        "temp_c": "1.3.6.1.4.1.55062.2.10.2.1.8.",
        "capacity_bytes": "1.3.6.1.4.1.55062.2.10.2.1.9.",
    }
    rows_by_index: Dict[int, Dict[str, Any]] = {}

    def _ensure_row(idx: int) -> Dict[str, Any]:
        return rows_by_index.setdefault(idx, {"index": idx})

    for field, prefix in tables.items():
        for oid, value in walk_values.items():
            if not oid.startswith(prefix):
                continue
            try:
                idx = int(oid.split(".")[-1])
            except Exception:
                continue
            row = _ensure_row(idx)
            row[field] = str(value or "").strip()

    rows: List[Dict[str, Any]] = []
    for idx in sorted(rows_by_index.keys()):
        row = rows_by_index[idx]
        capacity_bytes = _safe_int(row.get("capacity_bytes"), 0)
        capacity_text_raw = str(row.get("capacity_text") or "").strip()
        status_raw = str(row.get("health") or row.get("status") or "").strip()
        model_raw = str(row.get("model") or "").strip()
        if capacity_bytes <= 0 and capacity_text_raw in {"", "--"} and status_raw in {"", "--"} and model_raw in {"", "--"}:
            continue
        temp_text = str(row.get("temp_text") or "")
        temp_c_text = str(row.get("temp_c") or "").strip()
        temp_c = None
        if temp_c_text and temp_c_text not in {"--", "-", "0"}:
            temp_c = _safe_int(temp_c_text, 0)
        elif " C" in temp_text:
            parsed_temp = temp_text.split(" C")[0].strip()
            if parsed_temp and parsed_temp not in {"--", "0"}:
                temp_c = _safe_int(parsed_temp, 0)
        status_text = str(row.get("health") or row.get("status") or "--").strip()
        media_type = _qnap_disk_media_type(row)
        level = _qnap_disk_temp_level(media_type, temp_c)
        if status_text and status_text.upper() not in {"GOOD", "ONLINE", "--"}:
            level = "warning" if level == "normal" else level
        rows.append(
            {
                "index": idx,
                "slot": row.get("slot") or f"Disk {idx}",
                "media_type": media_type,
                "model": row.get("model") or "--",
                "vendor": row.get("vendor") or "--",
                "serial": row.get("serial") or "--",
                "bus": row.get("bus") or "--",
                "status": status_text or "--",
                "temp_c": temp_c,
                "temp_text": f"{temp_c} C" if temp_c is not None else (temp_text or "--"),
                "temp_status": _qnap_disk_temp_label(media_type, temp_c),
                "capacity_bytes": capacity_bytes if capacity_bytes > 0 else None,
                "capacity_text": _format_bytes_text(capacity_bytes) if capacity_bytes > 0 else (row.get("capacity_text") or "--"),
                "alert_level": level,
            }
        )
    return rows


def _parse_qnap_fan_rows(walk_values: Dict[str, str]) -> List[Dict[str, Any]]:
    name_prefix = "1.3.6.1.4.1.55062.2.12.9.1.2."
    rpm_prefix = "1.3.6.1.4.1.55062.2.12.9.1.3."
    rows: List[Dict[str, Any]] = []
    names: Dict[int, str] = {}
    rpms: Dict[int, int] = {}
    for oid, value in walk_values.items():
        if oid.startswith(name_prefix):
            try:
                idx = int(oid.split(".")[-1])
            except Exception:
                continue
            names[idx] = str(value or "").strip()
        elif oid.startswith(rpm_prefix):
            try:
                idx = int(oid.split(".")[-1])
            except Exception:
                continue
            rpms[idx] = _safe_int(value, 0)
    for idx in sorted(names.keys()):
        rpm = rpms.get(idx, 0)
        rows.append(
            {
                "index": idx,
                "name": names.get(idx) or f"FAN {idx}",
                "rpm": rpm,
                "rpm_text": f"{rpm} RPM" if rpm > 0 else "--",
                "alert_level": "warning" if 0 < rpm < 500 else "normal",
            }
        )
    return rows


def _parse_human_size_bytes(value: Any) -> int:
    text = str(value or "").strip()
    if not text or text == "--":
        return 0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?i?B?|[KMGTPE])?", text, re.IGNORECASE)
    if not match:
        return 0
    number = _safe_float(match.group(1), 0.0)
    unit = str(match.group(2) or "B").strip().upper().replace("IB", "B")
    multipliers = {
        "B": 1,
        "": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024 ** 2,
        "MB": 1024 ** 2,
        "G": 1024 ** 3,
        "GB": 1024 ** 3,
        "T": 1024 ** 4,
        "TB": 1024 ** 4,
        "P": 1024 ** 5,
        "PB": 1024 ** 5,
        "E": 1024 ** 6,
        "EB": 1024 ** 6,
    }
    return int(number * multipliers.get(unit, 1))


def _qnap_parse_storage_detail(text: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in str(text or "").splitlines():
        current = line.strip()
        if not current or current.lower().startswith("enclosure"):
            continue
        parts = re.split(r"\s{2,}", current)
        if len(parts) < 9:
            continue
        size_text = str(parts[4] or "").strip()
        rows.append(
            {
                "enclosure": parts[0],
                "port": parts[1],
                "sys_name": parts[2],
                "type": parts[3],
                "size_text": size_text,
                "size_bytes": _parse_human_size_bytes(size_text),
                "alias": parts[5] if len(parts) > 5 else "",
                "signature": parts[6] if len(parts) > 6 else "",
                "partitions": parts[7] if len(parts) > 7 else "",
                "model": parts[8] if len(parts) > 8 else "",
            }
        )
    return rows


def _qnap_parse_storage_overview(text: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in str(text or "").splitlines():
        current = line.strip()
        if not current or current.lower().startswith("enclosure"):
            continue
        parts = re.split(r"\s{2,}", current)
        if len(parts) < 10:
            continue
        rows.append(
            {
                "enclosure": parts[0],
                "port": parts[1],
                "sys_name": parts[2],
                "size_text": parts[3],
                "size_bytes": _parse_human_size_bytes(parts[3]),
                "type": parts[4],
                "vdev": parts[5],
                "raid_type": parts[6],
                "group": parts[7],
                "pool": parts[8],
                "shared_folder": parts[9],
            }
        )
    return rows


def _qnap_parse_zpool_status(text: Any) -> List[Dict[str, Any]]:
    pools: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("pool:"):
            if current:
                pools.append(current)
            current = {"name": stripped.split(":", 1)[1].strip(), "vdev_rows": [], "error_text": ""}
            continue
        if not current:
            continue
        if stripped.startswith("state:"):
            current["state"] = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("errors:"):
            current["error_text"] = stripped.split(":", 1)[1].strip()
            continue
        match = re.match(r"^([A-Za-z0-9_./:-]+)\s+(ONLINE|DEGRADED|FAULTED|OFFLINE|UNAVAIL|REMOVED|AVAIL|INUSE)\s+(\d+)\s+(\d+)\s+(\d+)", stripped)
        if match:
            name, state, read, write, cksum = match.groups()
            if name == current.get("name"):
                current["state"] = state
            else:
                current.setdefault("vdev_rows", []).append(
                    {
                        "name": name,
                        "state": state,
                        "read_errors": _safe_int(read, 0),
                        "write_errors": _safe_int(write, 0),
                        "checksum_errors": _safe_int(cksum, 0),
                    }
                )
    if current:
        pools.append(current)
    for pool in pools:
        bad_rows = [
            row for row in pool.get("vdev_rows", [])
            if str(row.get("state") or "").upper() != "ONLINE"
            or _safe_int(row.get("read_errors"), 0) > 0
            or _safe_int(row.get("write_errors"), 0) > 0
            or _safe_int(row.get("checksum_errors"), 0) > 0
        ]
        pool["alert_level"] = "critical" if str(pool.get("state") or "").upper() != "ONLINE" or bad_rows else "normal"
        pool["issue_count"] = len(bad_rows)
        pool["vdev_count"] = len(pool.get("vdev_rows", []) or [])
    return pools


def _qnap_build_share_alias_map(text: Any) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    for line in str(text or "").splitlines():
        current = line.strip()
        if " -> " not in current:
            continue
        left, right = current.rsplit(" -> ", 1)
        alias = left.split()[-1].strip()
        target = right.strip().lstrip("/")
        if not alias or not target or "/" not in target:
            continue
        if alias.startswith(".") or alias in {"homes", "external"}:
            continue
        parts = target.split("/", 1)
        if len(parts) != 2 or not parts[0].startswith("ZFS"):
            continue
        mountpoint = f"/share/{parts[0]}"
        alias_map[mountpoint] = alias
    return alias_map


def _qnap_share_name_from_mountpoint(mountpoint: Any, alias_map: Dict[str, str]) -> str:
    text = str(mountpoint or "").strip()
    if not text.startswith("/share/"):
        return ""
    parts = text.split("/")
    if len(parts) < 3:
        return text.rsplit("/", 1)[-1]
    root = "/".join(parts[:3])
    if root in alias_map:
        return alias_map[root]
    if len(parts) >= 4 and parts[3] and not parts[3].startswith("."):
        return parts[3]
    return parts[2]


def _qnap_parse_meminfo(text: Any) -> Dict[str, Any]:
    values: Dict[str, int] = {}
    for line in str(text or "").splitlines():
        match = re.match(r"^([A-Za-z_()]+):\s+(\d+)\s+kB", line.strip())
        if not match:
            continue
        values[match.group(1)] = _safe_int(match.group(2), 0) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0) or values.get("MemFree", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    summary = _memory_summary_from_bytes(total, available, swap_total, swap_free)
    if summary:
        summary.update(
            {
                "mem_free_text": _format_bytes_text(values.get("MemFree", 0)),
                "mem_cached_text": _format_bytes_text(values.get("Cached", 0)),
                "mem_buffers_text": _format_bytes_text(values.get("Buffers", 0)),
                "mem_slab_text": _format_bytes_text(values.get("Slab", 0)),
            }
        )
    return summary


def _qnap_parse_cpuinfo(text: Any) -> Dict[str, Any]:
    model = ""
    core_count = 0
    for line in str(text or "").splitlines():
        current = line.strip()
        if current.startswith("model name") and ":" in current and not model:
            model = current.split(":", 1)[1].strip()
        elif current.startswith("processor") and ":" in current:
            core_count += 1
    return {"cpu_model": model, "cpu_thread_count": core_count or None}


def _qnap_parse_hwmon(text: Any) -> Dict[str, Any]:
    sensors: List[Dict[str, Any]] = []
    current_name = ""
    labels: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("DIR="):
            current_name = ""
            labels = {}
            continue
        if "=" not in line and not line.startswith("/"):
            current_name = line.strip()
            continue
        if "_label=" in line:
            path, label = line.split("=", 1)
            match = re.search(r"(temp\d+)_label$", path)
            if match:
                labels[match.group(1)] = label.strip()
            continue
        if "_input=" not in line:
            continue
        path, value = line.split("=", 1)
        input_match = re.search(r"(temp\d+|fan\d+)_input$", path)
        if not input_match:
            continue
        key = input_match.group(1)
        raw_value = _safe_float(value, 0.0)
        if key.startswith("temp"):
            temp_c = round(raw_value / 1000.0, 1) if raw_value > 1000 else round(raw_value, 1)
            label = labels.get(key) or key
            sensors.append({"type": "temp", "name": label, "chip": current_name, "value_c": temp_c})
        else:
            sensors.append({"type": "fan", "name": key.upper(), "chip": current_name, "rpm": _safe_int(raw_value, 0)})
    cpu_temp = None
    system_temp = None
    temp_rows = []
    fan_rows = []
    for sensor in sensors:
        if sensor.get("type") == "temp":
            name = str(sensor.get("name") or "").lower()
            chip = str(sensor.get("chip") or "").lower()
            value_c = sensor.get("value_c")
            temp_rows.append(sensor)
            if cpu_temp is None and ("tctl" in name or "k10temp" in chip or "cpu" in name):
                cpu_temp = value_c
            elif system_temp is None and "phy" not in name and "mac" not in name:
                system_temp = value_c
        elif sensor.get("type") == "fan":
            fan_rows.append(sensor)
    return {
        "cpu_temperature_c": cpu_temp,
        "system_temperature_c": system_temp,
        "temperature_rows": temp_rows[:12],
        "hwmon_fan_rows": fan_rows[:8],
    }


def _qnap_parse_uptime(text: Any) -> Dict[str, Any]:
    first = str(text or "").strip().split()
    if not first:
        return {}
    seconds = int(_safe_float(first[0], 0.0))
    return {"uptime_seconds": seconds, "uptime_text": _format_uptime_seconds_text(seconds)}


def _qnap_parse_zfs_list(text: Any, share_alias_map: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    alias_map = dict(share_alias_map or {})
    for line in str(text or "").splitlines():
        current = line.strip()
        if not current or current.startswith("NAME"):
            continue
        parts = re.split(r"\s+", current, maxsplit=4)
        if len(parts) < 5:
            continue
        name, used_text, avail_text, refer_text, mountpoint = parts
        if "@" in name or mountpoint in {"-", "legacy"}:
            continue
        if not mountpoint.startswith("/share/"):
            continue
        if "/@" in mountpoint or "/.qpkg/" in mountpoint or "/.samba/" in mountpoint:
            continue
        path_parts = mountpoint.split("/")
        if len(path_parts) > 4:
            continue
        used_bytes = _parse_human_size_bytes(used_text)
        avail_bytes = _parse_human_size_bytes(avail_text)
        total_bytes = used_bytes + avail_bytes
        usage_percent = round((used_bytes / total_bytes) * 100.0, 1) if total_bytes > 0 else None
        share_name = _qnap_share_name_from_mountpoint(mountpoint, alias_map) or mountpoint.rsplit("/", 1)[-1]
        rows.append(
            {
                "name": name,
                "mountpoint": mountpoint,
                "share_name": share_name,
                "display_name": share_name,
                "used_text": used_text,
                "available_text": avail_text,
                "refer_text": refer_text,
                "total_text": _format_bytes_text(total_bytes),
                "used_bytes": used_bytes,
                "available_bytes": avail_bytes,
                "total_bytes": total_bytes,
                "usage_percent": usage_percent,
                "alert_level": _usage_level(usage_percent),
            }
        )
    rows.sort(
        key=lambda row: (
            {"critical": 0, "warning": 1, "normal": 2}.get(str(row.get("alert_level") or "normal"), 9),
            -_safe_float(row.get("usage_percent"), 0.0),
            -_safe_int(row.get("used_bytes"), 0),
            str(row.get("mountpoint") or ""),
        )
    )
    return rows


def _merge_qnap_disk_rows(snmp_rows: List[Dict[str, Any]], ssh_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not ssh_rows:
        return list(snmp_rows or [])
    snmp_by_port: Dict[int, Dict[str, Any]] = {}
    for row in snmp_rows or []:
        if not isinstance(row, dict):
            continue
        port = _safe_int(row.get("index") or row.get("port") or row.get("slot"), 0)
        if port > 0:
            snmp_by_port[port] = row
    merged_rows: List[Dict[str, Any]] = []
    for row in ssh_rows or []:
        if not isinstance(row, dict):
            continue
        port = _safe_int(row.get("port"), 0)
        snmp_row = snmp_by_port.get(port, {})
        merged = dict(snmp_row)
        merged.update(row)
        if port > 0:
            merged["index"] = port
            merged["port"] = str(port)
            merged.setdefault("slot", f"Disk {port}")
        merged["slot"] = merged.get("slot") or (f"Disk {port}" if port > 0 else merged.get("alias") or "--")
        merged["capacity_text"] = merged.get("capacity_text") or merged.get("size_text") or "--"
        merged["capacity_bytes"] = merged.get("capacity_bytes") or merged.get("size_bytes")
        merged["status"] = merged.get("status") or merged.get("health") or "ONLINE"
        if merged.get("temp_c") is not None and not merged.get("temp_text"):
            merged["temp_text"] = f"{merged.get('temp_c')} C"
        merged["temp_text"] = merged.get("temp_text") or "--"
        merged["alert_level"] = merged.get("alert_level") or "normal"
        merged_rows.append(merged)
    seen_ports = {_safe_int(row.get("port") or row.get("index"), 0) for row in merged_rows}
    for row in snmp_rows or []:
        port = _safe_int((row or {}).get("index") or (row or {}).get("port"), 0)
        if port > 0 and port not in seen_ports:
            merged_rows.append(row)
    return sorted(merged_rows, key=lambda item: _safe_int(item.get("port") or item.get("index"), 9999))


def _qnap_parse_ip_rows(text: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in str(text or "").splitlines():
        current = line.strip()
        if not current:
            continue
        parts = re.split(r"\s+", current)
        if len(parts) < 2:
            continue
        rows.append(
            {
                "name": parts[0],
                "state": parts[1],
                "addr": " ".join(parts[2:]) if len(parts) > 2 else "",
                "oper_up": parts[1].upper() == "UP",
            }
        )
    return rows


def _run_qnap_ssh_snapshot(device: Dict[str, Any], previous_summary: Dict[str, Any]) -> Dict[str, Any]:
    ssh_target = str(device.get("ssh_target") or "qnap-nas").strip()
    ssh_local_user = str(device.get("ssh_local_user") or "xinping").strip()
    timeout_sec = max(4.0, _safe_float(device.get("ssh_timeout_sec"), 12.0))
    cache_ttl_sec = max(30.0, _safe_float(device.get("ssh_cache_ttl_sec"), 60.0))
    previous_snapshot = dict((previous_summary or {}).get("qnap_ssh_summary", {}) or {})
    previous_ts = _safe_float(previous_snapshot.get("collected_monotonic"), 0.0)
    now_mono = time.monotonic()
    if previous_snapshot and previous_ts > 0 and (now_mono - previous_ts) < cache_ttl_sec:
        return previous_snapshot
    remote_cmd = r"""
printf '__QNAP_SYSTEM__\n'
hostname 2>/dev/null
/sbin/getcfg System Model -f /etc/config/uLinux.conf 2>/dev/null
/sbin/getcfg System Version -f /etc/config/uLinux.conf 2>/dev/null
/sbin/getcfg System "Build Number" -f /etc/config/uLinux.conf 2>/dev/null
printf '__PROC_UPTIME__\n'
cat /proc/uptime 2>/dev/null || true
printf '__PROC_MEMINFO__\n'
cat /proc/meminfo 2>/dev/null || true
printf '__PROC_CPUINFO__\n'
cat /proc/cpuinfo 2>/dev/null || true
printf '__HWMON__\n'
for d in /sys/class/hwmon/hwmon*; do
    [ -d "$d" ] || continue
    printf 'DIR=%s\n' "$d"
    cat "$d/name" 2>/dev/null || true
    for f in "$d"/temp*_label "$d"/temp*_input "$d"/fan*_input; do
        [ -e "$f" ] && printf '%s=%s\n' "$f" "$(cat "$f" 2>/dev/null)"
    done
done
printf '__QCLI_STORAGE_P__\n'
/sbin/qcli_storage -p 2>/dev/null || true
printf '__QCLI_STORAGE_D__\n'
/sbin/qcli_storage -d 2>/dev/null || true
printf '__ZPOOL_STATUS__\n'
/sbin/zpool status 2>/dev/null || true
printf '__ZFS_LIST__\n'
/sbin/zfs list -o name,used,avail,refer,mountpoint 2>/dev/null || true
printf '__SHARE_LINKS__\n'
ls -l /share 2>/dev/null || true
printf '__IP_BR_ADDR__\n'
ip -br addr 2>/dev/null || true
"""
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ConnectionAttempts=1",
        ssh_target,
        remote_cmd,
    ]
    if ssh_local_user:
        ssh_cmd = ["sudo", "-n", "-u", ssh_local_user] + ssh_cmd
    try:
        proc = subprocess.run(ssh_cmd, text=True, capture_output=True, timeout=timeout_sec)
    except Exception as exc:
        if previous_snapshot:
            previous_snapshot["stale"] = True
            previous_snapshot["error"] = str(exc)
            return previous_snapshot
        return {"available": False, "stale": True, "error": str(exc)}
    if proc.returncode != 0:
        error_text = (proc.stderr or f"ssh exited {proc.returncode}").strip()
        if previous_snapshot:
            previous_snapshot["stale"] = True
            previous_snapshot["error"] = error_text
            return previous_snapshot
        return {"available": False, "stale": True, "error": error_text}
    sections: Dict[str, List[str]] = {}
    current_section = ""
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__") and line.endswith("__"):
            current_section = line.strip("_")
            sections[current_section] = []
            continue
        if current_section:
            sections.setdefault(current_section, []).append(line)
    system_lines = [line.strip() for line in sections.get("QNAP_SYSTEM", []) if line.strip()]
    hostname = system_lines[0] if len(system_lines) > 0 else ""
    model = system_lines[1] if len(system_lines) > 1 else ""
    version = system_lines[2] if len(system_lines) > 2 else ""
    build = system_lines[3] if len(system_lines) > 3 else ""
    disk_rows = _qnap_parse_storage_detail("\n".join(sections.get("QCLI_STORAGE_D", [])))
    pool_member_rows = _qnap_parse_storage_overview("\n".join(sections.get("QCLI_STORAGE_P", [])))
    zpool_rows = _qnap_parse_zpool_status("\n".join(sections.get("ZPOOL_STATUS", [])))
    share_alias_map = _qnap_build_share_alias_map("\n".join(sections.get("SHARE_LINKS", [])))
    zfs_rows = _qnap_parse_zfs_list("\n".join(sections.get("ZFS_LIST", [])), share_alias_map=share_alias_map)
    ip_rows = _qnap_parse_ip_rows("\n".join(sections.get("IP_BR_ADDR", [])))
    meminfo_summary = _qnap_parse_meminfo("\n".join(sections.get("PROC_MEMINFO", [])))
    cpuinfo_summary = _qnap_parse_cpuinfo("\n".join(sections.get("PROC_CPUINFO", [])))
    hwmon_summary = _qnap_parse_hwmon("\n".join(sections.get("HWMON", [])))
    uptime_summary = _qnap_parse_uptime("\n".join(sections.get("PROC_UPTIME", [])))
    return {
        "available": True,
        "stale": False,
        "error": "",
        "collected_at": datetime.now().isoformat(),
        "collected_monotonic": now_mono,
        "hostname": hostname,
        "model": model,
        "version": version,
        "build": build,
        "firmware_text": f"{version} build {build}".strip(),
        "cpu_model": cpuinfo_summary.get("cpu_model") or "",
        "cpu_thread_count": cpuinfo_summary.get("cpu_thread_count"),
        "cpu_temperature_c": hwmon_summary.get("cpu_temperature_c"),
        "system_temperature_c": hwmon_summary.get("system_temperature_c"),
        "temperature_rows": hwmon_summary.get("temperature_rows", []),
        "memory_summary": meminfo_summary,
        "uptime_seconds": uptime_summary.get("uptime_seconds"),
        "uptime_text": uptime_summary.get("uptime_text"),
        "share_alias_map": share_alias_map,
        "disk_rows": disk_rows[:16],
        "pool_member_rows": pool_member_rows[:16],
        "zpool_rows": zpool_rows[:8],
        "zfs_rows": zfs_rows[:32],
        "ip_rows": ip_rows[:16],
        "disk_count": len(disk_rows),
        "zpool_count": len(zpool_rows),
        "zfs_share_count": len(zfs_rows),
    }


def _build_qnap_ssh_summary(device: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    device_type = str(result.get("device_type") or device.get("device_type") or "").strip().lower()
    vendor_key = f"{device.get('brand') or ''} {device.get('model') or ''} {result.get('sys_descr') or ''} {result.get('sys_name') or ''} {result.get('host') or ''}".lower()
    if device_type != "nas" or ("qnap" not in vendor_key and "ts-x73a" not in vendor_key and str(result.get("host") or "") != "192.168.30.145"):
        return {}
    if device.get("ssh_enrich_enabled", False) is not True:
        return {}
    return _run_qnap_ssh_snapshot(device, dict(result.get("previous_summary", {}) or {}))


def _build_ucd_summary(walk_values: Dict[str, str]) -> Dict[str, Any]:
    load_1 = _safe_float(walk_values.get("1.3.6.1.4.1.2021.10.1.3.1"), 0.0)
    load_5 = _safe_float(walk_values.get("1.3.6.1.4.1.2021.10.1.3.2"), 0.0)
    load_15 = _safe_float(walk_values.get("1.3.6.1.4.1.2021.10.1.3.3"), 0.0)
    mem_total_kb = _safe_int(walk_values.get("1.3.6.1.4.1.2021.4.5.0"), 0)
    mem_avail_kb = _safe_int(walk_values.get("1.3.6.1.4.1.2021.4.6.0"), 0)
    mem_buffer_kb = _safe_int(walk_values.get("1.3.6.1.4.1.2021.4.14.0"), 0)
    mem_cached_kb = _safe_int(walk_values.get("1.3.6.1.4.1.2021.4.15.0"), 0)
    raw_context = {
        "load_1": load_1 if load_1 > 0 else None,
        "load_5": load_5 if load_5 > 0 else None,
        "load_15": load_15 if load_15 > 0 else None,
        "mem_total_text": _format_bytes_text(mem_total_kb * 1024) if mem_total_kb > 0 else "--",
        "mem_available_text": _format_bytes_text(mem_avail_kb * 1024) if mem_avail_kb > 0 else "--",
        "mem_buffer_text": _format_bytes_text(mem_buffer_kb * 1024) if mem_buffer_kb > 0 else "--",
        "mem_cached_text": _format_bytes_text(mem_cached_kb * 1024) if mem_cached_kb > 0 else "--",
    }
    return raw_context


def _is_whole_disk_device(name: str) -> bool:
    text = str(name or "").strip().lower()
    if not text:
        return False
    if re.match(r"^sd[a-z]+$", text):
        return True
    if re.match(r"^hd[a-z]+$", text):
        return True
    if re.match(r"^vd[a-z]+$", text):
        return True
    if re.match(r"^xvd[a-z]+$", text):
        return True
    if re.match(r"^nvme\d+n\d+$", text):
        return True
    if re.match(r"^md\d+$", text):
        return True
    return False


def _parse_ucd_disk_io_rows(walk_values: Dict[str, str]) -> List[Dict[str, Any]]:
    rows_by_index: Dict[int, Dict[str, Any]] = {}
    column_map = {
        2: "device",
        3: "bytes_read_32",
        4: "bytes_written_32",
        5: "reads",
        6: "writes",
        9: "load_1",
        10: "load_5",
        11: "load_15",
        12: "bytes_read_64",
        13: "bytes_written_64",
    }
    prefix = "1.3.6.1.4.1.2021.13.15.1.1."
    for oid, value in walk_values.items():
        if not oid.startswith(prefix):
            continue
        parts = oid.split(".")
        if len(parts) < 2:
            continue
        try:
            column_id = int(parts[-2])
            index = int(parts[-1])
        except Exception:
            continue
        field = column_map.get(column_id)
        if not field:
            continue
        row = rows_by_index.setdefault(index, {"index": index})
        row[field] = str(value or "").strip()

    rows: List[Dict[str, Any]] = []
    for index in sorted(rows_by_index.keys()):
        row = rows_by_index[index]
        device = str(row.get("device") or "").strip()
        if not device:
            continue
        bytes_read = _safe_int(row.get("bytes_read_64"), _safe_int(row.get("bytes_read_32"), 0))
        bytes_written = _safe_int(row.get("bytes_written_64"), _safe_int(row.get("bytes_written_32"), 0))
        reads = _safe_int(row.get("reads"), 0)
        writes = _safe_int(row.get("writes"), 0)
        load_1 = _safe_int(row.get("load_1"), 0)
        load_5 = _safe_int(row.get("load_5"), 0)
        load_15 = _safe_int(row.get("load_15"), 0)
        load_peak = max(load_1, load_5, load_15)
        alert_level = "critical" if load_peak >= 90 else ("warning" if load_peak >= 70 else "normal")
        rows.append(
            {
                "index": index,
                "device": device,
                "is_whole_disk": _is_whole_disk_device(device),
                "bytes_read": bytes_read if bytes_read > 0 else None,
                "bytes_written": bytes_written if bytes_written > 0 else None,
                "bytes_read_text": _format_bytes_text(bytes_read),
                "bytes_written_text": _format_bytes_text(bytes_written),
                "reads": reads if reads > 0 else None,
                "writes": writes if writes > 0 else None,
                "reads_text": f"{reads:,}" if reads > 0 else "--",
                "writes_text": f"{writes:,}" if writes > 0 else "--",
                "load_1": load_1 if load_1 > 0 else None,
                "load_5": load_5 if load_5 > 0 else None,
                "load_15": load_15 if load_15 > 0 else None,
                "load_peak": load_peak if load_peak > 0 else None,
                "load_peak_text": f"{load_peak}%" if load_peak > 0 else "--",
                "alert_level": alert_level,
            }
        )
    return rows


def _summarize_if_names(walk_values: Dict[str, str], limit: int = 4) -> List[str]:
    items = []
    prefix = "1.3.6.1.2.1.2.2.1.2."
    for oid, value in walk_values.items():
        if oid.startswith(prefix):
            try:
                index = int(oid.split(".")[-1])
            except Exception:
                index = 999999
            items.append((index, str(value or "").strip()))
    items.sort(key=lambda item: item[0])
    names = []
    for _, name in items:
        if name and name not in names:
            names.append(name)
        if len(names) >= max(1, int(limit)):
            break
    return names


def _classify_interface_name(name: str) -> str:
    text = str(name or "").strip().lower()
    if not text:
        return "other"
    if text.startswith("wan"):
        return "wan"
    if text.startswith("lan"):
        return "lan"
    if text.startswith("gigabitethernet") or text.startswith("ten-gigabitethernet") or text.startswith("xgigabitethernet") or text.startswith("fortygige") or text.startswith("hundredgige") or text.startswith("bridge-aggregation"):
        return "physical"
    if text.startswith("eth") or text.startswith("en"):
        return "physical"
    if text.startswith("bond"):
        return "bond"
    if text.startswith("br") or "bridge" in text:
        return "bridge"
    if text.startswith("veth") or text.startswith("docker") or text.startswith("lxc") or text.startswith("lxd") or text.startswith("qtap"):
        return "virtual"
    return "other"


def _build_interface_rows(walk_values: Dict[str, str]) -> List[Dict[str, Any]]:
    name_by_index: Dict[int, str] = {}
    alias_by_index: Dict[int, str] = {}
    speed_by_index: Dict[int, int] = {}
    high_speed_by_index: Dict[int, int] = {}
    type_by_index: Dict[int, str] = {}
    admin_by_index: Dict[int, str] = {}
    oper_by_index: Dict[int, str] = {}
    in_octets_by_index: Dict[int, int] = {}
    out_octets_by_index: Dict[int, int] = {}
    in_errors_by_index: Dict[int, int] = {}
    out_errors_by_index: Dict[int, int] = {}
    in_discards_by_index: Dict[int, int] = {}
    out_discards_by_index: Dict[int, int] = {}

    def _safe_index(oid: str) -> int | None:
        try:
            return int(str(oid).split(".")[-1])
        except Exception:
            return None

    for oid, value in walk_values.items():
        if oid.startswith("1.3.6.1.2.1.31.1.1.1.1."):
            idx = _safe_index(oid)
            if idx is not None:
                name_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.31.1.1.1.6."):
            idx = _safe_index(oid)
            if idx is not None:
                in_octets_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.31.1.1.1.10."):
            idx = _safe_index(oid)
            if idx is not None:
                out_octets_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.31.1.1.1.18."):
            idx = _safe_index(oid)
            if idx is not None:
                alias_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.2.2.1.2."):
            idx = _safe_index(oid)
            if idx is not None and idx not in name_by_index:
                name_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.2.2.1.3."):
            idx = _safe_index(oid)
            if idx is not None:
                type_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.2.2.1.5."):
            idx = _safe_index(oid)
            if idx is not None:
                speed_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.31.1.1.1.15."):
            idx = _safe_index(oid)
            if idx is not None:
                high_speed_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.7."):
            idx = _safe_index(oid)
            if idx is not None:
                admin_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.2.2.1.8."):
            idx = _safe_index(oid)
            if idx is not None:
                oper_by_index[idx] = str(value or "").strip()
        elif oid.startswith("1.3.6.1.2.1.2.2.1.10."):
            idx = _safe_index(oid)
            if idx is not None and idx not in in_octets_by_index:
                in_octets_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.16."):
            idx = _safe_index(oid)
            if idx is not None and idx not in out_octets_by_index:
                out_octets_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.13."):
            idx = _safe_index(oid)
            if idx is not None:
                in_discards_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.14."):
            idx = _safe_index(oid)
            if idx is not None:
                in_errors_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.19."):
            idx = _safe_index(oid)
            if idx is not None:
                out_discards_by_index[idx] = _safe_int(value, 0)
        elif oid.startswith("1.3.6.1.2.1.2.2.1.20."):
            idx = _safe_index(oid)
            if idx is not None:
                out_errors_by_index[idx] = _safe_int(value, 0)

    rows = []
    for idx, name in sorted(name_by_index.items(), key=lambda item: item[0]):
        if not name:
            continue
        speed_bps = speed_by_index.get(idx, 0)
        high_speed_mbps = high_speed_by_index.get(idx, 0)
        if high_speed_mbps > 0 and (speed_bps <= 0 or speed_bps >= 4294967295):
            speed_bps = high_speed_mbps * 1000 * 1000
        if speed_bps <= 0 or speed_bps >= 4294967295:
            inferred_speed_bps = _infer_interface_speed_bps(name)
            if inferred_speed_bps > 0:
                speed_bps = inferred_speed_bps
        rows.append(
            {
                "index": idx,
                "name": name,
                "alias": alias_by_index.get(idx, ""),
                "kind": _classify_interface_name(name),
                "if_type": type_by_index.get(idx, ""),
                "speed_bps": speed_bps,
                "speed_text": _format_speed_text(speed_bps),
                "admin_status": admin_by_index.get(idx, ""),
                "oper_status": oper_by_index.get(idx, ""),
                "in_octets": in_octets_by_index.get(idx, 0),
                "out_octets": out_octets_by_index.get(idx, 0),
                "in_errors": in_errors_by_index.get(idx, 0),
                "out_errors": out_errors_by_index.get(idx, 0),
                "in_discards": in_discards_by_index.get(idx, 0),
                "out_discards": out_discards_by_index.get(idx, 0),
            }
        )
    return rows


def _summarize_interfaces(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "interface_total_count": 0,
            "interface_sample_count": 0,
            "top_names": [],
            "physical_names": [],
            "wan_names": [],
            "lan_names": [],
            "bond_names": [],
            "bridge_names": [],
            "virtual_names": [],
            "up_count": 0,
            "down_count": 0,
            "unknown_count": 0,
            "physical_count": 0,
            "wan_count": 0,
            "lan_count": 0,
            "bond_count": 0,
            "bridge_count": 0,
            "virtual_count": 0,
            "physical_up_count": 0,
            "physical_down_count": 0,
            "physical_unknown_count": 0,
            "uplink_count": 0,
            "port_preview_rows": [],
            "switch_port_rows": [],
            "down_rows": [],
            "unknown_rows": [],
            "error_port_count": 0,
            "discard_port_count": 0,
            "busy_port_count": 0,
            "aggregate_in_rate_bps": 0.0,
            "aggregate_out_rate_bps": 0.0,
            "aggregate_total_rate_bps": 0.0,
            "aggregate_in_rate_text": "--",
            "aggregate_out_rate_text": "--",
            "aggregate_total_rate_text": "--",
            "active_count": 0,
            "active_top_rows": [],
            "active_in_rate_bps": 0.0,
            "active_out_rate_bps": 0.0,
            "active_total_rate_bps": 0.0,
            "active_in_rate_text": "--",
            "active_out_rate_text": "--",
            "active_total_rate_text": "--",
            "delta_error_port_count": 0,
            "delta_discard_port_count": 0,
        }
    buckets = {
        "physical": [],
        "wan": [],
        "lan": [],
        "bond": [],
        "bridge": [],
        "virtual": [],
        "other": [],
    }
    up_count = 0
    down_count = 0
    unknown_count = 0
    down_rows = []
    unknown_rows = []
    for row in rows:
        kind = row.get("kind", "other")
        buckets.setdefault(kind, []).append(row.get("name"))
        oper_status = str(row.get("oper_status") or "").strip()
        admin_status = str(row.get("admin_status") or "").strip()
        is_admin_up = admin_status == "1"
        if oper_status == "1":
            up_count += 1
        elif is_admin_up and oper_status:
            down_count += 1
            down_rows.append(
                {
                    "name": row.get("name"),
                    "kind": kind,
                    "speed_text": _format_speed_text(row.get("speed_bps")),
                }
            )
        elif is_admin_up:
            unknown_count += 1
            unknown_rows.append(
                {
                    "name": row.get("name"),
                    "kind": kind,
                    "speed_text": _format_speed_text(row.get("speed_bps")),
                    "reason": "oper_status_missing",
                }
            )
    physical_rows = [row for row in rows if row.get("kind") == "physical"]
    physical_up_count = 0
    physical_down_count = 0
    physical_unknown_count = 0
    uplink_count = 0
    error_port_count = 0
    discard_port_count = 0
    busy_port_count = 0
    aggregate_in_rate_bps = 0.0
    aggregate_out_rate_bps = 0.0
    delta_error_port_count = 0
    delta_discard_port_count = 0
    sorted_physical_rows = sorted(
        physical_rows,
        key=lambda row: (
            0 if (_safe_int(row.get("error_delta_total"), 0) + _safe_int(row.get("discard_delta_total"), 0)) > 0 else 1,
            0 if _safe_float(row.get("utilization_percent"), 0.0) >= 70 else 1,
            0 if str(row.get("oper_status") or "") == "1" else 1,
            0 if _safe_int(row.get("speed_bps"), 0) >= 10_000_000_000 else 1,
            -(_safe_int(row.get("error_delta_total"), 0) + _safe_int(row.get("discard_delta_total"), 0)),
            -_safe_float(row.get("utilization_percent"), 0.0),
            -_safe_float(row.get("total_rate_bps"), 0.0),
            -_safe_int(row.get("speed_bps"), 0),
            str(row.get("name") or ""),
        ),
    )
    port_preview_rows = []
    switch_port_rows = []
    for row in sorted_physical_rows:
        oper_status = str(row.get("oper_status") or "").strip()
        admin_status = str(row.get("admin_status") or "").strip()
        is_oper_up = oper_status == "1"
        is_admin_up = admin_status == "1"
        is_oper_known = bool(oper_status)
        is_definite_down = is_admin_up and is_oper_known and not is_oper_up
        is_unknown = is_admin_up and not is_oper_known
        status_level = "up" if is_oper_up else ("down" if is_definite_down else ("unknown" if is_unknown else "disabled"))
        status_text = "在线" if status_level == "up" else ("离线" if status_level == "down" else ("状态未采到" if status_level == "unknown" else "管理关闭"))
        is_uplink = _safe_int(row.get("speed_bps"), 0) >= 10_000_000_000 or str(row.get("name") or "").lower().startswith(("ten-gigabitethernet", "xgigabitethernet", "fortygige", "hundredgige"))
        if is_oper_up:
            physical_up_count += 1
        elif is_definite_down:
            physical_down_count += 1
        elif is_unknown:
            physical_unknown_count += 1
        if is_uplink:
            uplink_count += 1
        in_errors = _safe_int(row.get("in_errors"), 0)
        out_errors = _safe_int(row.get("out_errors"), 0)
        in_discards = _safe_int(row.get("in_discards"), 0)
        out_discards = _safe_int(row.get("out_discards"), 0)
        total_errors = in_errors + out_errors
        total_discards = in_discards + out_discards
        error_delta_total = _safe_int(row.get("error_delta_total"), 0)
        discard_delta_total = _safe_int(row.get("discard_delta_total"), 0)
        utilization_percent = _safe_float(row.get("utilization_percent"), -1.0)
        if total_errors > 0:
            error_port_count += 1
        if total_discards > 0:
            discard_port_count += 1
        if error_delta_total > 0:
            delta_error_port_count += 1
        if discard_delta_total > 0:
            delta_discard_port_count += 1
        if utilization_percent >= 60:
            busy_port_count += 1
        aggregate_in_rate_bps += _safe_float(row.get("in_rate_bps"), 0.0)
        aggregate_out_rate_bps += _safe_float(row.get("out_rate_bps"), 0.0)
        switch_port_rows.append(
            {
                "index": row.get("index"),
                "name": row.get("name"),
                "alias": row.get("alias", ""),
                "if_type": row.get("if_type", ""),
                "speed_bps": _safe_int(row.get("speed_bps"), 0),
                "speed_text": _format_speed_text(row.get("speed_bps")),
                "admin_status": row.get("admin_status"),
                "oper_status": row.get("oper_status"),
                "admin_up": is_admin_up,
                "oper_up": is_oper_up,
                "oper_status_known": is_oper_known,
                "status_level": status_level,
                "status_text": status_text,
                "in_rate_bps": round(_safe_float(row.get("in_rate_bps"), 0.0), 2),
                "out_rate_bps": round(_safe_float(row.get("out_rate_bps"), 0.0), 2),
                "total_rate_bps": round(_safe_float(row.get("total_rate_bps"), 0.0), 2),
                "in_rate_text": row.get("in_rate_text", "--"),
                "out_rate_text": row.get("out_rate_text", "--"),
                "traffic_text": row.get("traffic_text", "--"),
                "total_rate_text": row.get("total_rate_text", "--"),
                "in_bytes_text": row.get("in_bytes_text", "--"),
                "out_bytes_text": row.get("out_bytes_text", "--"),
                "utilization_percent": utilization_percent if utilization_percent >= 0 else None,
                "utilization_text": row.get("utilization_text", "--"),
                "in_errors": in_errors,
                "out_errors": out_errors,
                "in_discards": in_discards,
                "out_discards": out_discards,
                "error_total": total_errors,
                "discard_total": total_discards,
                "in_errors_delta": _safe_int(row.get("in_errors_delta"), 0),
                "out_errors_delta": _safe_int(row.get("out_errors_delta"), 0),
                "in_discards_delta": _safe_int(row.get("in_discards_delta"), 0),
                "out_discards_delta": _safe_int(row.get("out_discards_delta"), 0),
                "error_delta_total": error_delta_total,
                "discard_delta_total": discard_delta_total,
                "is_uplink": is_uplink,
            }
        )
    for row in sorted_physical_rows[:8]:
        oper_status = str(row.get("oper_status") or "").strip()
        admin_status = str(row.get("admin_status") or "").strip()
        is_oper_up = oper_status == "1"
        is_admin_up = admin_status == "1"
        is_oper_known = bool(oper_status)
        is_definite_down = is_admin_up and is_oper_known and not is_oper_up
        is_unknown = is_admin_up and not is_oper_known
        status_level = "up" if is_oper_up else ("down" if is_definite_down else ("unknown" if is_unknown else "disabled"))
        port_preview_rows.append(
            {
                "name": row.get("name"),
                "alias": row.get("alias", ""),
                "speed_text": _format_speed_text(row.get("speed_bps")),
                "admin_up": is_admin_up,
                "oper_up": is_oper_up,
                "oper_status_known": is_oper_known,
                "status_level": status_level,
                "status_text": "在线" if status_level == "up" else ("离线" if status_level == "down" else ("状态未采到" if status_level == "unknown" else "管理关闭")),
                "is_uplink": _safe_int(row.get("speed_bps"), 0) >= 10_000_000_000 or str(row.get("name") or "").lower().startswith(("ten-gigabitethernet", "xgigabitethernet", "fortygige", "hundredgige")),
            }
        )
    top_names = [row.get("name") for row in rows[:6] if row.get("name")]
    active_summary = _build_active_interface_summary(rows)
    return {
        "interface_total_count": len(rows),
        "interface_sample_count": len(rows),
        "top_names": top_names,
        "physical_names": buckets.get("physical", [])[:6],
        "wan_names": buckets.get("wan", [])[:4],
        "lan_names": buckets.get("lan", [])[:8],
        "bond_names": buckets.get("bond", [])[:4],
        "bridge_names": buckets.get("bridge", [])[:4],
        "virtual_names": buckets.get("virtual", [])[:6],
        "up_count": up_count,
        "down_count": down_count,
        "unknown_count": unknown_count,
        "physical_count": len(physical_rows),
        "wan_count": len(buckets.get("wan", [])),
        "lan_count": len(buckets.get("lan", [])),
        "bond_count": len(buckets.get("bond", [])),
        "bridge_count": len(buckets.get("bridge", [])),
        "virtual_count": len(buckets.get("virtual", [])),
        "physical_up_count": physical_up_count,
        "physical_down_count": physical_down_count,
        "physical_unknown_count": physical_unknown_count,
        "uplink_count": uplink_count,
        "port_preview_rows": port_preview_rows,
        "switch_port_rows": switch_port_rows[:48],
        "down_rows": down_rows[:6],
        "unknown_rows": unknown_rows[:6],
        "error_port_count": error_port_count,
        "discard_port_count": discard_port_count,
        "busy_port_count": busy_port_count,
        "aggregate_in_rate_bps": round(aggregate_in_rate_bps, 2),
        "aggregate_out_rate_bps": round(aggregate_out_rate_bps, 2),
        "aggregate_total_rate_bps": round(aggregate_in_rate_bps + aggregate_out_rate_bps, 2),
        "aggregate_in_rate_text": _format_rate_text(aggregate_in_rate_bps),
        "aggregate_out_rate_text": _format_rate_text(aggregate_out_rate_bps),
        "aggregate_total_rate_text": _format_rate_text(aggregate_in_rate_bps + aggregate_out_rate_bps),
        **active_summary,
        "delta_error_port_count": delta_error_port_count,
        "delta_discard_port_count": delta_discard_port_count,
    }


def _bridge_fdb_status_text(status_value: Any) -> str:
    status = _safe_int(status_value, 0)
    return {
        1: "other",
        2: "invalid",
        3: "learned",
        4: "self",
        5: "mgmt",
    }.get(status, "--")


def _parse_oid_suffix_ints(oid: str, prefix: str) -> List[int]:
    if not str(oid).startswith(prefix):
        return []
    suffix = str(oid)[len(prefix):].strip(".")
    if not suffix:
        return []
    values: List[int] = []
    for item in suffix.split("."):
        try:
            values.append(int(item))
        except Exception:
            return []
    return values


def _format_mac_from_parts(parts: List[int]) -> str:
    if len(parts) != 6:
        return ""
    return ":".join(f"{max(0, min(255, int(part))):02X}" for part in parts)


def _parse_switch_bridge_summary(walk_values: Dict[str, str], interface_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not walk_values:
        return {
            "bridge_port_count": 0,
            "mac_count": 0,
            "learned_mac_count": 0,
            "vlan_count": 0,
            "vlan_rows": [],
            "fdb_rows": [],
            "port_mac_rows": [],
            "port_stats_by_ifindex": {},
        }

    bridge_ifindex_prefix = "1.3.6.1.2.1.17.1.4.1.2."
    dot1d_port_prefix = "1.3.6.1.2.1.17.4.3.1.2."
    dot1d_status_prefix = "1.3.6.1.2.1.17.4.3.1.3."
    dot1q_port_prefix = "1.3.6.1.2.1.17.7.1.2.2.1.2."
    dot1q_status_prefix = "1.3.6.1.2.1.17.7.1.2.2.1.3."
    vlan_name_prefix = "1.3.6.1.2.1.17.7.1.4.3.1.1."
    pvid_prefix = "1.3.6.1.2.1.17.7.1.4.5.1.1."

    ifindex_to_row = {
        _safe_int(row.get("index"), -1): row
        for row in interface_rows
        if _safe_int(row.get("index"), -1) >= 0
    }
    bridge_port_to_ifindex: Dict[int, int] = {}
    vlan_name_map: Dict[int, str] = {}
    pvid_by_bridge_port: Dict[int, int] = {}

    for oid, value in walk_values.items():
        if str(oid).startswith(bridge_ifindex_prefix):
            suffix = _parse_oid_suffix_ints(oid, bridge_ifindex_prefix)
            if len(suffix) == 1:
                bridge_port_to_ifindex[suffix[0]] = _safe_int(value, 0)
        elif str(oid).startswith(vlan_name_prefix):
            suffix = _parse_oid_suffix_ints(oid, vlan_name_prefix)
            if len(suffix) == 1:
                name = _decode_hex_text(value)
                vlan_name_map[suffix[0]] = name if name else f"VLAN {suffix[0]}"
        elif str(oid).startswith(pvid_prefix):
            suffix = _parse_oid_suffix_ints(oid, pvid_prefix)
            if len(suffix) == 1:
                pvid_by_bridge_port[suffix[0]] = _safe_int(value, 0)

    entries: List[Dict[str, Any]] = []
    seen_keys = set()

    def _append_entry(bridge_port: int, mac_text: str, status_text: str, vlan_id: int | None, source: str) -> None:
        if bridge_port <= 0 or not mac_text:
            return
        key = (bridge_port, mac_text, vlan_id or 0, source)
        if key in seen_keys:
            return
        seen_keys.add(key)
        ifindex = bridge_port_to_ifindex.get(bridge_port, 0)
        iface = ifindex_to_row.get(ifindex, {})
        inferred_vlan = vlan_id if vlan_id and vlan_id > 0 else pvid_by_bridge_port.get(bridge_port)
        entries.append(
            {
                "bridge_port": bridge_port,
                "ifindex": ifindex if ifindex > 0 else None,
                "port_name": iface.get("name") or f"BridgePort {bridge_port}",
                "port_alias": iface.get("alias", ""),
                "vlan_id": inferred_vlan if inferred_vlan and inferred_vlan > 0 else None,
                "vlan_name": vlan_name_map.get(inferred_vlan, f"VLAN {inferred_vlan}") if inferred_vlan and inferred_vlan > 0 else "--",
                "mac": mac_text,
                "status": status_text or "--",
                "source": source,
            }
        )

    for oid, value in walk_values.items():
        if str(oid).startswith(dot1q_port_prefix):
            suffix = _parse_oid_suffix_ints(oid, dot1q_port_prefix)
            if len(suffix) >= 7:
                vlan_id = suffix[0]
                mac_text = _format_mac_from_parts(suffix[1:7])
                status_text = _bridge_fdb_status_text(walk_values.get(dot1q_status_prefix + ".".join(str(v) for v in suffix), ""))
                _append_entry(_safe_int(value, 0), mac_text, status_text, vlan_id, "q-bridge")

    if not entries:
        for oid, value in walk_values.items():
            if str(oid).startswith(dot1d_port_prefix):
                suffix = _parse_oid_suffix_ints(oid, dot1d_port_prefix)
                if len(suffix) == 6:
                    mac_text = _format_mac_from_parts(suffix)
                    status_text = _bridge_fdb_status_text(walk_values.get(dot1d_status_prefix + ".".join(str(v) for v in suffix), ""))
                    _append_entry(_safe_int(value, 0), mac_text, status_text, None, "bridge")

    vlan_stats: Dict[int, Dict[str, Any]] = {}
    port_stats_by_ifindex: Dict[int, Dict[str, Any]] = {}
    learned_mac_count = 0

    for entry in entries:
        status_text = str(entry.get("status") or "--")
        if status_text == "invalid":
            continue
        if status_text == "learned":
            learned_mac_count += 1

        vlan_id = _safe_int(entry.get("vlan_id"), 0)
        if vlan_id > 0:
            vlan_row = vlan_stats.setdefault(
                vlan_id,
                {
                    "vlan_id": vlan_id,
                    "vlan_name": vlan_name_map.get(vlan_id, f"VLAN {vlan_id}"),
                    "mac_count": 0,
                    "ports": set(),
                },
            )
            vlan_row["mac_count"] += 1
            vlan_row["ports"].add(entry.get("port_name") or f"BridgePort {entry.get('bridge_port')}")

        ifindex = _safe_int(entry.get("ifindex"), 0)
        if ifindex > 0:
            port_row = port_stats_by_ifindex.setdefault(
                ifindex,
                {
                    "ifindex": ifindex,
                    "port_name": entry.get("port_name") or f"ifIndex {ifindex}",
                    "port_alias": entry.get("port_alias", ""),
                    "mac_count": 0,
                    "vlans": set(),
                    "macs": [],
                    "pvid": None,
                },
            )
            port_row["mac_count"] += 1
            if vlan_id > 0:
                port_row["vlans"].add(vlan_id)
            if len(port_row["macs"]) < 4:
                port_row["macs"].append(entry.get("mac"))

    for bridge_port, ifindex in bridge_port_to_ifindex.items():
        pvid = pvid_by_bridge_port.get(bridge_port)
        if ifindex <= 0 or not pvid:
            continue
        port_row = port_stats_by_ifindex.setdefault(
            ifindex,
            {
                "ifindex": ifindex,
                "port_name": (ifindex_to_row.get(ifindex) or {}).get("name") or f"ifIndex {ifindex}",
                "port_alias": (ifindex_to_row.get(ifindex) or {}).get("alias", ""),
                "mac_count": 0,
                "vlans": set(),
                "macs": [],
                "pvid": None,
            },
        )
        port_row["pvid"] = pvid
        port_row["vlans"].add(pvid)

    # Ensure every physical interface has a bridge stats placeholder.
    # This avoids front-end stats mismatch (e.g. 0/0 port summary while VLAN/MAC exists).
    for iface in interface_rows:
        ifindex = _safe_int(iface.get("index"), 0)
        if ifindex <= 0:
            continue
        if str(iface.get("kind") or "") != "physical":
            continue
        port_stats_by_ifindex.setdefault(
            ifindex,
            {
                "ifindex": ifindex,
                "port_name": iface.get("name") or f"ifIndex {ifindex}",
                "port_alias": iface.get("alias", ""),
                "mac_count": 0,
                "vlans": set(),
                "macs": [],
                "pvid": None,
            },
        )

    vlan_rows = sorted(
        [
            {
                "vlan_id": item["vlan_id"],
                "vlan_name": item["vlan_name"],
                "mac_count": item["mac_count"],
                "port_count": len(item["ports"]),
                "ports_preview": " / ".join(sorted(item["ports"])[:3]) if item["ports"] else "--",
            }
            for item in vlan_stats.values()
        ],
        key=lambda item: (-_safe_int(item.get("mac_count"), 0), _safe_int(item.get("vlan_id"), 0)),
    )

    port_mac_rows = sorted(
        [
            {
                "ifindex": item["ifindex"],
                "port_name": item["port_name"],
                "port_alias": item["port_alias"],
                "mac_count": item["mac_count"],
                "vlan_count": len(item["vlans"]),
                "pvid": item["pvid"],
                "pvid_name": vlan_name_map.get(item["pvid"], f"VLAN {item['pvid']}") if item["pvid"] else "--",
                "mac_preview": " / ".join(item["macs"]) if item["macs"] else "--",
            }
            for item in port_stats_by_ifindex.values()
        ],
        key=lambda item: (-_safe_int(item.get("mac_count"), 0), str(item.get("port_name") or "")),
    )

    fdb_rows = sorted(
        entries,
        key=lambda item: (
            0 if str(item.get("status") or "") == "learned" else 1,
            _safe_int(item.get("vlan_id"), 0) if item.get("vlan_id") is not None else 999999,
            str(item.get("port_name") or ""),
            str(item.get("mac") or ""),
        ),
    )

    return {
        "bridge_port_count": len(bridge_port_to_ifindex),
        "mac_count": len([item for item in entries if str(item.get("status") or "") != "invalid"]),
        "learned_mac_count": learned_mac_count,
        "vlan_count": len(vlan_rows),
        "vlan_rows": vlan_rows[:12],
        "fdb_rows": fdb_rows[:24],
        "port_mac_rows": port_mac_rows[:12],
        "port_stats_by_ifindex": port_stats_by_ifindex,
    }


def _merge_switch_bridge_summary(interface_summary: Dict[str, Any], bridge_summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(interface_summary or {})
    raw_port_stats = dict((bridge_summary or {}).get("port_stats_by_ifindex", {}) or {})
    port_stats: Dict[int, Dict[str, Any]] = {}

    for raw_ifindex, raw_stat in raw_port_stats.items():
        ifindex = _safe_int(raw_ifindex, -1)
        if ifindex < 0:
            continue
        stat = dict(raw_stat or {})
        vlan_values: List[int] = []
        raw_vlans = stat.get("vlans")
        if isinstance(raw_vlans, (set, list, tuple)):
            for vlan_item in raw_vlans:
                vlan_id = _safe_int(vlan_item, 0)
                if vlan_id > 0:
                    vlan_values.append(vlan_id)
        vlan_count = _safe_int(stat.get("vlan_count"), 0)
        if vlan_count <= 0 and vlan_values:
            vlan_count = len(set(vlan_values))
        pvid = _safe_int(stat.get("pvid"), 0)
        pvid_name = str(stat.get("pvid_name") or "").strip()
        if pvid_name in {"", "--"} and pvid > 0:
            pvid_name = f"VLAN {pvid}"
        if not pvid_name:
            pvid_name = "--"
        mac_preview = str(stat.get("mac_preview") or "").strip()
        if mac_preview in {"", "--"}:
            raw_macs = stat.get("macs")
            if isinstance(raw_macs, (set, list, tuple)):
                mac_values = [str(item).strip() for item in raw_macs if str(item).strip()]
                mac_preview = " / ".join(mac_values[:4]) if mac_values else "--"
            else:
                mac_preview = "--"
        port_stats[ifindex] = {
            **stat,
            "mac_count": _safe_int(stat.get("mac_count"), 0),
            "vlan_count": vlan_count,
            "pvid": pvid if pvid > 0 else None,
            "pvid_name": pvid_name,
            "mac_preview": mac_preview,
        }

    def _merge_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged_rows: List[Dict[str, Any]] = []
        for row in rows or []:
            current = dict(row or {})
            ifindex = _safe_int(current.get("index"), 0)
            stat = dict(port_stats.get(ifindex, {}) or {})
            if stat:
                current["learned_mac_count"] = _safe_int(stat.get("mac_count"), 0)
                current["learned_vlan_count"] = _safe_int(stat.get("vlan_count"), 0)
                current["mac_preview"] = stat.get("mac_preview", "--")
                merged_pvid = _safe_int(stat.get("pvid"), _safe_int(current.get("pvid"), 0))
                current["pvid"] = merged_pvid if merged_pvid > 0 else None
                current["pvid_name"] = stat.get("pvid_name") or (f"VLAN {merged_pvid}" if merged_pvid > 0 else "--")
            else:
                fallback_pvid = _safe_int(current.get("pvid"), 0)
                current.setdefault("learned_mac_count", 0)
                current.setdefault("learned_vlan_count", 0)
                current.setdefault("mac_preview", "--")
                current["pvid"] = fallback_pvid if fallback_pvid > 0 else None
                if str(current.get("pvid_name") or "").strip() in {"", "--"}:
                    current["pvid_name"] = f"VLAN {fallback_pvid}" if fallback_pvid > 0 else "--"
            merged_rows.append(current)
        return merged_rows

    summary["switch_port_rows"] = _merge_rows(list(summary.get("switch_port_rows", []) or []))
    summary["port_preview_rows"] = _merge_rows(list(summary.get("port_preview_rows", []) or []))
    summary["bridge_port_count"] = _safe_int((bridge_summary or {}).get("bridge_port_count"), 0)
    summary["bridge_mac_count"] = _safe_int((bridge_summary or {}).get("mac_count"), 0)
    summary["bridge_learned_mac_count"] = _safe_int((bridge_summary or {}).get("learned_mac_count"), 0)
    summary["bridge_vlan_count"] = _safe_int((bridge_summary or {}).get("vlan_count"), 0)
    summary["bridge_vlan_rows"] = list((bridge_summary or {}).get("vlan_rows", []) or [])[:12]
    summary["bridge_fdb_rows"] = list((bridge_summary or {}).get("fdb_rows", []) or [])[:24]
    summary["bridge_port_mac_rows"] = list((bridge_summary or {}).get("port_mac_rows", []) or [])[:12]
    if _safe_int(summary.get("bridge_port_count"), 0) <= 0 and port_stats:
        summary["bridge_port_count"] = len(port_stats)
    if _safe_int(summary.get("bridge_vlan_count"), 0) <= 0 and summary.get("bridge_vlan_rows"):
        summary["bridge_vlan_count"] = len(summary.get("bridge_vlan_rows") or [])
    if not summary.get("bridge_port_mac_rows") and port_stats:
        summary["bridge_port_mac_rows"] = sorted(
            [
                {
                    "ifindex": ifindex,
                    "port_name": stat.get("port_name") or f"ifIndex {ifindex}",
                    "port_alias": stat.get("port_alias", ""),
                    "mac_count": _safe_int(stat.get("mac_count"), 0),
                    "vlan_count": _safe_int(stat.get("vlan_count"), 0),
                    "pvid": stat.get("pvid"),
                    "pvid_name": stat.get("pvid_name") or "--",
                    "mac_preview": stat.get("mac_preview") or "--",
                }
                for ifindex, stat in port_stats.items()
            ],
            key=lambda item: (-_safe_int(item.get("mac_count"), 0), str(item.get("port_name") or "")),
        )[:12]
    if _safe_int(summary.get("physical_count"), 0) <= 0:
        summary["physical_count"] = len(summary.get("switch_port_rows") or [])
    if _safe_int(summary.get("physical_up_count"), 0) <= 0:
        summary["physical_up_count"] = len(
            [
                row
                for row in (summary.get("switch_port_rows") or [])
                if str(row.get("oper_status") or "") == "1" or bool(row.get("oper_up"))
            ]
        )
    summary["physical_unknown_count"] = len(
        [
            row
            for row in (summary.get("switch_port_rows") or [])
            if bool(row.get("admin_up"))
            and not bool(row.get("oper_up"))
            and not str(row.get("oper_status") or "").strip()
        ]
    )
    if _safe_int(summary.get("physical_down_count"), 0) <= 0:
        summary["physical_down_count"] = len(
            [
                row
                for row in (summary.get("switch_port_rows") or [])
                if bool(row.get("admin_up"))
                and not bool(row.get("oper_up"))
                and bool(str(row.get("oper_status") or "").strip())
            ]
        )
    summary["unknown_count"] = _safe_int(summary.get("unknown_count"), 0) or _safe_int(summary.get("physical_unknown_count"), 0)
    summary["down_count"] = _safe_int(summary.get("down_count"), 0) or _safe_int(summary.get("physical_down_count"), 0)
    if _safe_int(summary.get("uplink_count"), 0) <= 0:
        summary["uplink_count"] = len(
            [
                row
                for row in (summary.get("switch_port_rows") or [])
                if bool(row.get("is_uplink")) or _safe_int(row.get("speed_bps"), 0) >= 10_000_000_000
            ]
        )
    return summary


def _normalize_switch_port_key(name: Any) -> str:
    text = str(name or "").strip().lower()
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    suffix_match = re.search(r"(\d+/\d+/\d+)$", compact)
    suffix = suffix_match.group(1) if suffix_match else compact
    if compact.startswith(("ten-gigabitethernet", "tenge", "te")):
        return f"te:{suffix}"
    if compact.startswith(("xgigabitethernet", "xge")):
        return f"xge:{suffix}"
    if compact.startswith(("fortygige", "forty-gigabitethernet")):
        return f"fo:{suffix}"
    if compact.startswith(("hundredgige", "hundred-gigabitethernet")):
        return f"hu:{suffix}"
    if compact.startswith(("gigabitethernet", "ge", "gi")):
        return f"gi:{suffix}"
    return compact


def _short_switch_port_name(name: Any) -> str:
    text = str(name or "").strip()
    replacements = [
        ("Ten-GigabitEthernet", "Te"),
        ("XGigabitEthernet", "XGE"),
        ("GigabitEthernet", "Gi"),
        ("FortyGigE", "Fo"),
        ("HundredGigE", "Hu"),
    ]
    for old, new in replacements:
        if text.startswith(old):
            return new + text[len(old):]
    return text


def _format_switch_vlan_label(vlan_id: Any, vlan_name: Any = "") -> str:
    value = _safe_int(vlan_id, 0)
    if value <= 0:
        return "--"
    name = str(vlan_name or "").strip()
    if not name or name == str(value):
        return str(value)
    return f"{value} {name}"


def _build_static_switch_topology(static_config: Dict[str, Any] | None) -> Dict[str, Any]:
    raw_config = dict(static_config or {})
    topology = raw_config.get("switch_topology") if isinstance(raw_config.get("switch_topology"), dict) else raw_config
    if not isinstance(topology, dict):
        return {}

    vlan_map: Dict[int, str] = {}
    vlan_rows: List[Dict[str, Any]] = []
    for item in topology.get("vlans") or []:
        if not isinstance(item, dict):
            continue
        vlan_id = _safe_int(item.get("id"), 0)
        if vlan_id <= 0:
            continue
        name = str(item.get("name") or "").strip()
        vlan_map[vlan_id] = name
        vlan_rows.append(
            {
                "vlan_id": vlan_id,
                "vlan_name": name or f"VLAN {vlan_id}",
                "label": _format_switch_vlan_label(vlan_id, name),
                "source": "configured",
            }
        )

    gateway_rows: List[Dict[str, Any]] = []
    for item in topology.get("vlan_interfaces") or []:
        if not isinstance(item, dict):
            continue
        vlan_id = _safe_int(item.get("id"), 0)
        if vlan_id <= 0:
            continue
        name = str(item.get("name") or vlan_map.get(vlan_id) or "").strip()
        ip_text = str(item.get("ip") or "").strip()
        mask_text = str(item.get("mask") or "").strip()
        cidr_text = str(item.get("cidr") or "").strip()
        if not cidr_text and ip_text:
            cidr_text = ip_text
        gateway_rows.append(
            {
                "vlan_id": vlan_id,
                "vlan_name": name or f"VLAN {vlan_id}",
                "label": _format_switch_vlan_label(vlan_id, name),
                "ip": ip_text,
                "mask": mask_text,
                "cidr": cidr_text,
                "source": "configured",
            }
        )

    port_rows: List[Dict[str, Any]] = []
    for item in topology.get("ports") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("port") or "").strip()
        if not name:
            continue
        link_type = str(item.get("link_type") or "").strip().lower() or "access"
        access_vlan = _safe_int(item.get("access_vlan"), 0)
        pvid = _safe_int(item.get("pvid"), 0)
        permit_vlans = []
        for raw_vlan in item.get("permit_vlans") or []:
            vlan_id = _safe_int(raw_vlan, 0)
            if vlan_id > 0 and vlan_id not in permit_vlans:
                permit_vlans.append(vlan_id)
        configured_vlans = []
        if link_type == "trunk":
            for vlan_id in [pvid, *permit_vlans]:
                if vlan_id > 0 and vlan_id not in configured_vlans:
                    configured_vlans.append(vlan_id)
        elif access_vlan > 0:
            configured_vlans.append(access_vlan)
            if pvid <= 0:
                pvid = access_vlan
        else:
            for vlan_id in [pvid, *permit_vlans]:
                if vlan_id > 0 and vlan_id not in configured_vlans:
                    configured_vlans.append(vlan_id)

        configured_labels = [_format_switch_vlan_label(vlan_id, vlan_map.get(vlan_id, "")) for vlan_id in configured_vlans]
        access_name = vlan_map.get(access_vlan, "") if access_vlan > 0 else ""
        pvid_name = vlan_map.get(pvid, "") if pvid > 0 else ""
        purpose = str(item.get("purpose") or "").strip()
        if not purpose:
            if link_type == "trunk":
                purpose = f"trunk PVID {_format_switch_vlan_label(pvid, pvid_name)} · permit {'/'.join(str(v) for v in permit_vlans) if permit_vlans else '--'}"
            elif access_vlan > 0:
                purpose = f"access VLAN {_format_switch_vlan_label(access_vlan, access_name)}"
            else:
                purpose = link_type or "--"
        port_rows.append(
            {
                "name": name,
                "short_name": str(item.get("short_name") or _short_switch_port_name(name)).strip(),
                "key": _normalize_switch_port_key(name),
                "link_type": link_type,
                "link_type_text": "Trunk" if link_type == "trunk" else "Access",
                "access_vlan": access_vlan if access_vlan > 0 else None,
                "access_vlan_name": access_name or None,
                "pvid": pvid if pvid > 0 else None,
                "pvid_name": pvid_name or (f"VLAN {pvid}" if pvid > 0 else None),
                "permit_vlans": permit_vlans,
                "permit_vlan_names": [vlan_map.get(vlan_id, f"VLAN {vlan_id}") for vlan_id in permit_vlans],
                "configured_vlan_ids": configured_vlans,
                "configured_vlan_names": [vlan_map.get(vlan_id, f"VLAN {vlan_id}") for vlan_id in configured_vlans],
                "configured_vlan_text": " / ".join(configured_labels) if configured_labels else "--",
                "purpose_text": purpose,
                "source": "configured",
            }
        )

    port_rows.sort(
        key=lambda row: (
            1 if str(row.get("key") or "").startswith("te:") else 0,
            _safe_int(str(row.get("key") or "0/0/999999").split("/")[-1], 999999),
            str(row.get("name") or ""),
        )
    )
    vlan_rows.sort(key=lambda row: _safe_int(row.get("vlan_id"), 0))
    gateway_rows.sort(key=lambda row: _safe_int(row.get("vlan_id"), 0))

    capabilities = dict(topology.get("capabilities") or {}) if isinstance(topology.get("capabilities"), dict) else {}
    return {
        "source": str(topology.get("source") or raw_config.get("source") or "").strip(),
        "sysname": str(topology.get("sysname") or "").strip(),
        "model": str(topology.get("model") or "").strip(),
        "software_version": str(topology.get("software_version") or "").strip(),
        "capabilities": capabilities,
        "configured_vlan_count": len(vlan_rows),
        "configured_port_count": len(port_rows),
        "configured_access_count": len([row for row in port_rows if row.get("link_type") == "access"]),
        "configured_trunk_count": len([row for row in port_rows if row.get("link_type") == "trunk"]),
        "configured_vlan_rows": vlan_rows,
        "vlan_gateway_rows": gateway_rows,
        "configured_port_rows": port_rows,
    }


def _merge_switch_static_topology(interface_summary: Dict[str, Any], static_config: Dict[str, Any] | None) -> Dict[str, Any]:
    topology = _build_static_switch_topology(static_config)
    if not topology:
        return dict(interface_summary or {})
    summary = dict(interface_summary or {})
    configured_ports = list(topology.get("configured_port_rows") or [])
    gateway_by_vlan = {
        _safe_int(row.get("vlan_id"), 0): dict(row)
        for row in list(topology.get("vlan_gateway_rows") or [])
        if _safe_int(row.get("vlan_id"), 0) > 0
    }
    port_by_key = {
        str(row.get("key") or ""): dict(row)
        for row in configured_ports
        if str(row.get("key") or "").strip()
    }

    def _enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(row or {})
        key = _normalize_switch_port_key(current.get("name"))
        configured = dict(port_by_key.get(key, {}) or {})
        if not configured:
            return current
        current["configured"] = True
        current["configured_port_name"] = configured.get("name")
        current["configured_short_name"] = configured.get("short_name")
        current["configured_link_type"] = configured.get("link_type")
        current["configured_link_type_text"] = configured.get("link_type_text")
        current["configured_access_vlan"] = configured.get("access_vlan")
        current["configured_access_vlan_name"] = configured.get("access_vlan_name")
        current["configured_pvid"] = configured.get("pvid")
        current["configured_pvid_name"] = configured.get("pvid_name")
        current["configured_permit_vlans"] = list(configured.get("permit_vlans") or [])
        current["configured_permit_vlan_names"] = list(configured.get("permit_vlan_names") or [])
        current["configured_vlan_ids"] = list(configured.get("configured_vlan_ids") or [])
        current["configured_vlan_names"] = list(configured.get("configured_vlan_names") or [])
        current["configured_vlan_text"] = configured.get("configured_vlan_text") or "--"
        current["purpose_text"] = configured.get("purpose_text") or current.get("purpose_text") or ""
        configured_pvid = _safe_int(configured.get("pvid"), 0)
        configured_access_vlan = _safe_int(configured.get("access_vlan"), 0)
        if _safe_int(current.get("pvid"), 0) <= 0:
            current["pvid"] = configured_pvid if configured_pvid > 0 else (configured_access_vlan if configured_access_vlan > 0 else None)
        if str(current.get("pvid_name") or "").strip() in {"", "--"}:
            current["pvid_name"] = configured.get("pvid_name") or configured.get("access_vlan_name") or (
                f"VLAN {current['pvid']}" if _safe_int(current.get("pvid"), 0) > 0 else "--"
            )
        current["vlan_display_text"] = current.get("configured_vlan_text") or current.get("pvid_name") or "--"
        current["link_type_text"] = current.get("configured_link_type_text") or current.get("link_type_text") or "--"
        current["short_name"] = configured.get("short_name") or _short_switch_port_name(current.get("name"))
        return current

    enriched_switch_rows = [_enrich_row(row) for row in list(summary.get("switch_port_rows", []) or [])]
    enriched_preview_rows = [_enrich_row(row) for row in list(summary.get("port_preview_rows", []) or [])]
    summary["switch_port_rows"] = enriched_switch_rows
    summary["port_preview_rows"] = enriched_preview_rows

    live_by_key = {
        _normalize_switch_port_key(row.get("name")): row
        for row in enriched_switch_rows
        if _normalize_switch_port_key(row.get("name"))
    }
    configured_status_rows = []
    for configured in configured_ports:
        row = dict(configured)
        live = dict(live_by_key.get(str(configured.get("key") or ""), {}) or {})
        if live:
            row.update(
                {
                    "index": live.get("index"),
                    "admin_up": live.get("admin_up"),
                    "oper_up": live.get("oper_up"),
                    "status_level": live.get("status_level"),
                    "status_text": live.get("status_text"),
                    "speed_text": live.get("speed_text"),
                    "speed_bps": live.get("speed_bps"),
                    "in_rate_bps": live.get("in_rate_bps", 0.0),
                    "out_rate_bps": live.get("out_rate_bps", 0.0),
                    "total_rate_bps": live.get("total_rate_bps", 0.0),
                    "in_rate_text": live.get("in_rate_text", "--"),
                    "out_rate_text": live.get("out_rate_text", "--"),
                    "total_rate_text": live.get("total_rate_text"),
                    "traffic_text": live.get("traffic_text", "--"),
                    "utilization_percent": live.get("utilization_percent"),
                    "utilization_text": live.get("utilization_text", "--"),
                    "in_bytes_text": live.get("in_bytes_text", "--"),
                    "out_bytes_text": live.get("out_bytes_text", "--"),
                    "error_total": live.get("error_total", 0),
                    "discard_total": live.get("discard_total", 0),
                    "error_delta_total": live.get("error_delta_total", 0),
                    "discard_delta_total": live.get("discard_delta_total", 0),
                    "is_uplink": live.get("is_uplink", False),
                    "pvid_name": live.get("pvid_name") or configured.get("pvid_name") or configured.get("access_vlan_name") or "--",
                    "learned_mac_count": live.get("learned_mac_count", 0),
                    "learned_vlan_count": live.get("learned_vlan_count", 0),
                }
            )
        else:
            row.setdefault("admin_up", False)
            row.setdefault("oper_up", False)
            row.setdefault("status_level", "down")
            row.setdefault("status_text", "离线")
            row.setdefault("speed_text", "--")
            row.setdefault("total_rate_text", "--")
        configured_status_rows.append(row)

    vlan_stats: Dict[int, Dict[str, Any]] = {}
    for vlan in list(topology.get("configured_vlan_rows") or []):
        vlan_id = _safe_int(vlan.get("vlan_id"), 0)
        if vlan_id <= 0:
            continue
        gateway = gateway_by_vlan.get(vlan_id, {})
        vlan_stats[vlan_id] = {
            "vlan_id": vlan_id,
            "vlan_name": vlan.get("vlan_name") or f"VLAN {vlan_id}",
            "label": vlan.get("label") or _format_switch_vlan_label(vlan_id, vlan.get("vlan_name")),
            "cidr": gateway.get("cidr") or gateway.get("ip") or "",
            "port_count": 0,
            "up_port_count": 0,
            "down_port_count": 0,
            "access_port_count": 0,
            "trunk_port_count": 0,
            "busy_port_count": 0,
            "in_rate_bps": 0.0,
            "out_rate_bps": 0.0,
            "total_rate_bps": 0.0,
            "speed_bps": 0.0,
            "ports": [],
            "top_ports": [],
            "has_trunk_member": False,
        }

    for row in configured_status_rows:
        vlan_ids = []
        for vlan_id in row.get("configured_vlan_ids") or []:
            normalized_vlan_id = _safe_int(vlan_id, 0)
            if normalized_vlan_id > 0 and normalized_vlan_id not in vlan_ids:
                vlan_ids.append(normalized_vlan_id)
        if not vlan_ids:
            for key in ("pvid", "access_vlan", "configured_pvid", "configured_access_vlan"):
                normalized_vlan_id = _safe_int(row.get(key), 0)
                if normalized_vlan_id > 0 and normalized_vlan_id not in vlan_ids:
                    vlan_ids.append(normalized_vlan_id)
        if not vlan_ids:
            continue
        link_type = str(row.get("link_type") or row.get("configured_link_type") or "").strip().lower()
        is_up = bool(row.get("oper_up"))
        is_busy = _safe_float(row.get("utilization_percent"), 0.0) >= 60.0
        for vlan_id in vlan_ids:
            stat = vlan_stats.setdefault(
                vlan_id,
                {
                    "vlan_id": vlan_id,
                    "vlan_name": f"VLAN {vlan_id}",
                    "label": f"VLAN {vlan_id}",
                    "cidr": "",
                    "port_count": 0,
                    "up_port_count": 0,
                    "down_port_count": 0,
                    "access_port_count": 0,
                    "trunk_port_count": 0,
                    "busy_port_count": 0,
                    "in_rate_bps": 0.0,
                    "out_rate_bps": 0.0,
                    "total_rate_bps": 0.0,
                    "speed_bps": 0.0,
                    "ports": [],
                    "top_ports": [],
                    "has_trunk_member": False,
                },
            )
            stat["port_count"] += 1
            stat["up_port_count"] += 1 if is_up else 0
            stat["down_port_count"] += 0 if is_up else 1
            stat["access_port_count"] += 1 if link_type != "trunk" else 0
            stat["trunk_port_count"] += 1 if link_type == "trunk" else 0
            stat["has_trunk_member"] = bool(stat["has_trunk_member"] or link_type == "trunk")
            stat["busy_port_count"] += 1 if is_busy else 0
            stat["in_rate_bps"] += _safe_float(row.get("in_rate_bps"), 0.0)
            stat["out_rate_bps"] += _safe_float(row.get("out_rate_bps"), 0.0)
            stat["total_rate_bps"] += _safe_float(row.get("total_rate_bps"), 0.0)
            stat["speed_bps"] += _safe_float(row.get("speed_bps"), 0.0)
            port_preview = row.get("short_name") or _short_switch_port_name(row.get("name"))
            if port_preview and port_preview not in stat["ports"]:
                stat["ports"].append(port_preview)
            stat["top_ports"].append(
                {
                    "name": row.get("name"),
                    "short_name": port_preview,
                    "status_text": row.get("status_text") or "--",
                    "total_rate_bps": round(_safe_float(row.get("total_rate_bps"), 0.0), 2),
                    "total_rate_text": row.get("total_rate_text") or "--",
                    "utilization_percent": row.get("utilization_percent"),
                    "utilization_text": row.get("utilization_text") or "--",
                }
            )

    configured_vlan_traffic_rows = []
    for stat in vlan_stats.values():
        total_rate = _safe_float(stat.get("total_rate_bps"), 0.0)
        total_speed = _safe_float(stat.get("speed_bps"), 0.0)
        utilization = round(min(100.0, (total_rate / total_speed) * 100.0), 2) if total_speed > 0 and total_rate > 0 else None
        top_ports = sorted(
            stat.get("top_ports") or [],
            key=lambda item: (-_safe_float(item.get("total_rate_bps"), 0.0), str(item.get("short_name") or item.get("name") or "")),
        )[:6]
        configured_vlan_traffic_rows.append(
            {
                "vlan_id": stat.get("vlan_id"),
                "vlan_name": stat.get("vlan_name"),
                "label": stat.get("label"),
                "cidr": stat.get("cidr"),
                "port_count": _safe_int(stat.get("port_count"), 0),
                "up_port_count": _safe_int(stat.get("up_port_count"), 0),
                "down_port_count": _safe_int(stat.get("down_port_count"), 0),
                "access_port_count": _safe_int(stat.get("access_port_count"), 0),
                "trunk_port_count": _safe_int(stat.get("trunk_port_count"), 0),
                "busy_port_count": _safe_int(stat.get("busy_port_count"), 0),
                "in_rate_bps": round(_safe_float(stat.get("in_rate_bps"), 0.0), 2),
                "out_rate_bps": round(_safe_float(stat.get("out_rate_bps"), 0.0), 2),
                "total_rate_bps": round(total_rate, 2),
                "in_rate_text": _format_rate_text(stat.get("in_rate_bps")),
                "out_rate_text": _format_rate_text(stat.get("out_rate_bps")),
                "total_rate_text": _format_rate_text(total_rate),
                "utilization_percent": utilization,
                "utilization_text": f"{utilization}%" if utilization is not None else "--",
                "ports_preview": " / ".join((stat.get("ports") or [])[:8]) if stat.get("ports") else "--",
                "top_ports": top_ports,
                "has_trunk_member": bool(stat.get("has_trunk_member")),
            }
        )
    configured_vlan_traffic_rows.sort(
        key=lambda item: (
            -_safe_float(item.get("total_rate_bps"), 0.0),
            -_safe_int(item.get("busy_port_count"), 0),
            _safe_int(item.get("vlan_id"), 0),
        )
    )

    summary["static_topology"] = topology
    summary["configured_vlan_count"] = topology.get("configured_vlan_count", 0)
    summary["configured_port_count"] = topology.get("configured_port_count", 0)
    summary["configured_access_count"] = topology.get("configured_access_count", 0)
    summary["configured_trunk_count"] = topology.get("configured_trunk_count", 0)
    summary["configured_vlan_rows"] = list(topology.get("configured_vlan_rows") or [])[:24]
    summary["vlan_gateway_rows"] = list(topology.get("vlan_gateway_rows") or [])[:24]
    summary["configured_port_rows"] = configured_status_rows[:48]
    summary["configured_vlan_traffic_rows"] = configured_vlan_traffic_rows[:32]
    summary["vlan_traffic_rows"] = configured_vlan_traffic_rows[:32]
    summary["top_busy_port_rows"] = sorted(
        [row for row in enriched_switch_rows if _safe_float(row.get("total_rate_bps"), 0.0) > 0],
        key=lambda item: (-_safe_float(item.get("total_rate_bps"), 0.0), str(item.get("name") or "")),
    )[:12]
    summary["high_utilization_port_rows"] = sorted(
        [row for row in enriched_switch_rows if _safe_float(row.get("utilization_percent"), 0.0) >= 60.0],
        key=lambda item: (-_safe_float(item.get("utilization_percent"), 0.0), str(item.get("name") or "")),
    )[:12]
    return summary


def _build_snmp_summary_legacy_unused(result: Dict[str, Any]) -> Dict[str, Any]:
    walk_values = dict(result.get("walk_values", {}) or {})
    previous_walk_values = dict(result.get("previous_walk_values", {}) or {})
    metrics = dict(result.get("metrics", {}) or {})
    custom_metrics = list(result.get("custom_metrics", []) or [])
    device_type = str(result.get("device_type") or "").strip().lower()
    location_text = _decode_hex_text(result.get("sys_location") or walk_values.get("1.3.6.1.2.1.1.6.0") or "")
    memory_kb = metrics.get("hr_memory_size_kb") or walk_values.get("1.3.6.1.2.1.25.2.2.0")
    process_count = metrics.get("hr_system_processes")
    if process_count in (None, ""):
        process_count = walk_values.get("1.3.6.1.2.1.25.1.6.0")
    user_count = metrics.get("hr_system_users")
    if user_count in (None, ""):
        user_count = walk_values.get("1.3.6.1.2.1.25.1.5.0")
    boot_params = walk_values.get("1.3.6.1.2.1.25.1.4.0")
    interface_names = _summarize_if_names(walk_values, limit=4)
    interface_rows = _build_interface_rows(walk_values)
    previous_interface_rows = _build_interface_rows(previous_walk_values) if previous_walk_values else []
    current_walk_complete = bool(result.get("walk_counter_cycle_complete"))
    previous_walk_complete = bool(result.get("previous_walk_counter_cycle_complete"))
    elapsed_sec = _elapsed_walk_counter_seconds(result) if current_walk_complete and previous_walk_complete else 0.0
    _apply_interface_rate_deltas(interface_rows, previous_interface_rows, elapsed_sec)
    interface_summary = _summarize_interfaces(interface_rows)
    if_number_value = _safe_int(result.get("if_number"), 0)
    if if_number_value > 0:
        interface_summary["interface_total_count"] = if_number_value
    interface_summary["interface_sample_count"] = len(interface_rows)
    bridge_summary = _parse_switch_bridge_summary(walk_values, interface_rows) if device_type == "switch" else {}
    if bridge_summary:
        interface_summary = _merge_switch_bridge_summary(interface_summary, bridge_summary)
        if if_number_value > 0:
            interface_summary["interface_total_count"] = if_number_value
        interface_summary["interface_sample_count"] = len(interface_rows)
    if device_type == "switch":
        interface_summary = _merge_switch_static_topology(interface_summary, result.get("static_config"))
    cpu_loads = _parse_cpu_loads(walk_values)
    storage_rows = _parse_storage_rows(walk_values)
    memory_summary = _build_memory_summary(storage_rows, memory_kb)
    real_storage_rows = [row for row in storage_rows if _is_real_storage_row(row)]
    sorted_storage_rows = sorted(
        real_storage_rows,
        key=lambda item: (
            {"critical": 0, "warning": 1, "normal": 2}.get(str(item.get("alert_level") or "normal"), 9),
            -_safe_float(item.get("usage_percent"), 0.0),
            -_safe_int(item.get("used_bytes"), 0),
        ),
    )
    top_storage_rows = sorted_storage_rows[:4]
    network_rows = [row for row in interface_rows if row.get("kind") in {"physical", "wan", "lan", "bond"}]
    active_interface_summary = _build_active_interface_summary(interface_rows)
    sorted_network_rows = _sort_network_rows(network_rows, device_type=device_type)
    top_traffic_rows = sorted(
        network_rows,
        key=lambda item: _safe_float(item.get("total_rate_bps"), 0.0),
        reverse=True,
    )[:6]
    if not top_traffic_rows:
        top_traffic_rows = active_interface_summary.get("active_top_rows", [])[:6]
    wan_top_rows = [row for row in sorted_network_rows if row.get("kind") == "wan"][:4]
    lan_top_rows = [row for row in sorted_network_rows if row.get("kind") == "lan"][:4]
    physical_top_rows = [row for row in sorted_network_rows if row.get("kind") in {"physical", "bond"}][:4]
    alert_items: List[Dict[str, Any]] = []
    cpu_avg_percent = round(sum(cpu_loads) / len(cpu_loads), 1) if cpu_loads else None
    cpu_peak_percent = max(cpu_loads) if cpu_loads else None
    memory_usage_percent = memory_summary.get("memory_usage_percent")
    if cpu_peak_percent is not None and cpu_peak_percent >= 90:
        alert_items.append({"level": "critical", "text": f"CPU peak {cpu_peak_percent}% is high"})
    elif cpu_peak_percent is not None and cpu_peak_percent >= 80:
        alert_items.append({"level": "warning", "text": f"CPU peak {cpu_peak_percent}% is elevated"})
    if memory_usage_percent is not None and memory_usage_percent >= 90:
        alert_items.append({"level": "critical", "text": f"Memory usage {memory_usage_percent}% is high"})
    elif memory_usage_percent is not None and memory_usage_percent >= 80:
        alert_items.append({"level": "warning", "text": f"Memory usage {memory_usage_percent}% is elevated"})
    if cpu_peak_percent is not None and cpu_peak_percent >= 85:
        alert_items.append({"level": "warning", "text": f"CPU 峰值 {cpu_peak_percent}% 偏高"})
    for row in top_storage_rows:
        usage_percent = row.get("usage_percent")
        if usage_percent is not None and usage_percent >= 85:
            alert_items.append({"level": "warning", "text": f"{row.get('descr')} 使用率 {usage_percent}%"})
    if not network_rows and device_type == "router":
        alert_items.append({"level": "info", "text": "网关接口分类较少，可继续补充厂商 OID"})
    location_text = location_text if location_text and location_text != '""' else "--"
    contact_text = _decode_hex_text(result.get("sys_contact") or "")
    contact_text = contact_text if contact_text and contact_text != '""' else "--"
    sys_descr_text = _decode_hex_text(result.get("sys_descr") or "")
    alert_items = [
        item for item in alert_items
        if isinstance(item, dict) and str(item.get("text") or "").strip() and "宄板" not in str(item.get("text") or "") and "浣跨敤鐜" not in str(item.get("text") or "")
    ]
    storage_warning_count = len([row for row in real_storage_rows if row.get("alert_level") == "warning"])
    storage_critical_count = len([row for row in real_storage_rows if row.get("alert_level") == "critical"])
    alert_counts = {
        "critical": len([item for item in alert_items if item.get("level") == "critical"]),
        "warning": len([item for item in alert_items if item.get("level") == "warning"]),
        "info": len([item for item in alert_items if item.get("level") == "info"]),
    }
    gpu_metrics = _extract_gpu_metrics(custom_metrics)
    summary = {
        "device_type": device_type or "network",
        "sys_descr_text": sys_descr_text if sys_descr_text else str(result.get("sys_descr") or ""),
        "cpu_model": qnap_ssh_summary.get("cpu_model") or None,
        "cpu_core_count": qnap_ssh_summary.get("cpu_thread_count") or len(cpu_loads),
        "cpu_avg_percent": cpu_avg_percent,
        "cpu_peak_percent": cpu_peak_percent,
        "cpu_loads": cpu_loads[:16],
        "memory_total_kb": _safe_int(memory_kb, 0) if memory_kb not in (None, "") else None,
        "memory_total_gb": _format_memory_gb(memory_kb),
        "memory_total_text": memory_summary.get("memory_total_text"),
        "memory_used_text": memory_summary.get("memory_used_text"),
        "memory_available_text": memory_summary.get("memory_available_text"),
        "memory_usage_percent": memory_summary.get("memory_usage_percent"),
        "memory_alert_level": memory_summary.get("memory_alert_level"),
        "swap_total_text": memory_summary.get("swap_total_text"),
        "swap_used_text": memory_summary.get("swap_used_text"),
        "swap_usage_percent": memory_summary.get("swap_usage_percent"),
        "swap_alert_level": memory_summary.get("swap_alert_level"),
        "process_count": _safe_int(process_count, 0) if str(process_count).strip().isdigit() else None,
        "user_count": _safe_int(user_count, 0) if str(user_count).strip().isdigit() else None,
        "interface_names": interface_names,
        "interface_preview": " / ".join(interface_names) if interface_names else "--",
        "interface_rows": interface_rows[:24],
        "interface_summary": interface_summary,
        "network_top_rows": top_traffic_rows,
        "wan_top_rows": wan_top_rows,
        "lan_top_rows": lan_top_rows,
        "physical_top_rows": physical_top_rows,
        "storage_rows": sorted_storage_rows[:24],
        "storage_top_rows": top_storage_rows,
        "storage_count": len(real_storage_rows),
        "storage_warning_count": storage_warning_count,
        "storage_critical_count": storage_critical_count,
        "alert_items": alert_items[:8],
        "alert_counts": alert_counts,
        "gpu_metrics": gpu_metrics,
        "uptime_text": _format_uptime_text(result.get("sys_uptime")),
        "location_text": location_text,
        "contact_text": contact_text,
        "boot_params_preview": (str(boot_params or "")[:96] + "...") if boot_params and len(str(boot_params)) > 96 else str(boot_params or ""),
        "poll_elapsed_sec": round(elapsed_sec, 2) if elapsed_sec > 0 else 0.0,
    }
    _ = result.pop("previous_summary", None)
    return summary


def _build_snmp_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    walk_values = dict(result.get("walk_values", {}) or {})
    previous_walk_values = dict(result.get("previous_walk_values", {}) or {})
    metrics = dict(result.get("metrics", {}) or {})
    custom_metrics = list(result.get("custom_metrics", []) or [])
    custom_metric_map = {
        str(item.get("name") or "").strip().lower(): item
        for item in custom_metrics
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    def _metric_value(*names: str) -> Any:
        for name in names:
            key = str(name or "").strip().lower()
            if not key:
                continue
            metric_item = custom_metric_map.get(key)
            if metric_item is None:
                continue
            value = metric_item.get("value")
            if value not in (None, "", "--"):
                return value
        return None

    def _metric_raw(*names: str) -> str:
        for name in names:
            key = str(name or "").strip().lower()
            metric_item = custom_metric_map.get(key)
            if not metric_item:
                continue
            raw = str(metric_item.get("raw") or "").strip()
            if raw and not raw.lower().startswith("no such "):
                return raw
        return ""

    device_type = str(result.get("device_type") or "").strip().lower()
    location_text = _decode_hex_text(result.get("sys_location") or walk_values.get("1.3.6.1.2.1.1.6.0") or "")
    memory_kb = metrics.get("hr_memory_size_kb") or walk_values.get("1.3.6.1.2.1.25.2.2.0")
    process_count = metrics.get("hr_system_processes")
    if process_count in (None, ""):
        process_count = walk_values.get("1.3.6.1.2.1.25.1.6.0")
    user_count = metrics.get("hr_system_users")
    if user_count in (None, ""):
        user_count = walk_values.get("1.3.6.1.2.1.25.1.5.0")
    boot_params = walk_values.get("1.3.6.1.2.1.25.1.4.0")
    interface_names = _summarize_if_names(walk_values, limit=4)
    interface_rows = _build_interface_rows(walk_values)
    previous_interface_rows = _build_interface_rows(previous_walk_values) if previous_walk_values else []
    current_walk_complete = bool(result.get("walk_counter_cycle_complete"))
    previous_walk_complete = bool(result.get("previous_walk_counter_cycle_complete"))
    elapsed_sec = _elapsed_walk_counter_seconds(result) if current_walk_complete and previous_walk_complete else 0.0
    _apply_interface_rate_deltas(interface_rows, previous_interface_rows, elapsed_sec)
    _carry_forward_interface_rates(interface_rows, list((result.get("previous_summary") or {}).get("interface_rows", []) or []))
    interface_summary = _summarize_interfaces(interface_rows)
    if_number_value = _safe_int(result.get("if_number"), 0)
    if if_number_value > 0:
        interface_summary["interface_total_count"] = if_number_value
    interface_summary["interface_sample_count"] = len(interface_rows)
    bridge_summary = _parse_switch_bridge_summary(walk_values, interface_rows) if device_type == "switch" else {}
    if bridge_summary:
        interface_summary = _merge_switch_bridge_summary(interface_summary, bridge_summary)
        if if_number_value > 0:
            interface_summary["interface_total_count"] = if_number_value
        interface_summary["interface_sample_count"] = len(interface_rows)
    cpu_loads = _parse_cpu_loads(walk_values)
    storage_rows = _parse_storage_rows(walk_values)
    memory_summary = _build_memory_summary(storage_rows, memory_kb)
    ucd_summary = _build_ucd_summary(walk_values)
    ucd_disk_io_rows = _parse_ucd_disk_io_rows(walk_values)
    vendor_memory_total_text = str(walk_values.get("1.3.6.1.4.1.24681.1.2.2.0") or _metric_raw("vendor_memory_total") or "").strip()
    vendor_memory_free_text = str(walk_values.get("1.3.6.1.4.1.24681.1.2.3.0") or _metric_raw("vendor_memory_free") or "").strip()
    qnap_disk_rows = _parse_qnap_disk_rows(walk_values)
    qnap_fan_rows = _parse_qnap_fan_rows(walk_values)
    qnap_ssh_summary = dict(result.get("qnap_ssh_summary", {}) or {})
    if not qnap_ssh_summary.get("available"):
        qnap_ssh_summary = {}
    qnap_memory_summary = dict(qnap_ssh_summary.get("memory_summary", {}) or {})
    if qnap_memory_summary.get("memory_total_bytes"):
        memory_summary.update(qnap_memory_summary)
    if qnap_ssh_summary.get("disk_rows"):
        qnap_disk_rows = _merge_qnap_disk_rows(qnap_disk_rows, list(qnap_ssh_summary.get("disk_rows") or []))
    for disk_row in qnap_disk_rows:
        if not isinstance(disk_row, dict):
            continue
        if not disk_row.get("slot") and disk_row.get("port"):
            disk_row["slot"] = f"Disk {disk_row.get('port')}"
        if not disk_row.get("capacity_text") and disk_row.get("size_text"):
            disk_row["capacity_text"] = disk_row.get("size_text")
        if not disk_row.get("status"):
            disk_row["status"] = "ONLINE"
        if not disk_row.get("temp_text") and disk_row.get("temp_c") is not None:
            disk_row["temp_text"] = f"{disk_row.get('temp_c')} C"
        disk_row["media_type"] = disk_row.get("media_type") or _qnap_disk_media_type(disk_row)
        disk_row["temp_status"] = _qnap_disk_temp_label(disk_row.get("media_type"), disk_row.get("temp_c"))
        status_text = str(disk_row.get("status") or "--").strip().upper()
        temp_level = _qnap_disk_temp_level(disk_row.get("media_type"), disk_row.get("temp_c"))
        if status_text and status_text not in {"GOOD", "ONLINE", "--"}:
            disk_row["alert_level"] = "warning" if temp_level == "normal" else temp_level
        else:
            disk_row["alert_level"] = temp_level
    is_qnap_device = _is_qnap_snmp_result(result)
    qnap_zfs_rows = list(qnap_ssh_summary.get("zfs_rows") or [])
    real_storage_rows = [row for row in storage_rows if _is_real_storage_row(row)]
    real_storage_rows = _apply_storage_aliases(real_storage_rows, result.get("storage_aliases"))
    if qnap_zfs_rows:
        real_storage_rows = [
            {
                "index": 9000 + idx,
                "descr": row.get("display_name") or row.get("share_name") or row.get("mountpoint") or row.get("name") or f"QNAP Share {idx + 1}",
                "mountpoint": row.get("mountpoint"),
                "share_name": row.get("share_name"),
                "kind": "filesystem",
                "total_bytes": row.get("total_bytes"),
                "used_bytes": row.get("used_bytes"),
                "available_bytes": row.get("available_bytes"),
                "usage_percent": row.get("usage_percent"),
                "alert_level": row.get("alert_level") or _usage_level(row.get("usage_percent")),
                "total_text": row.get("total_text"),
                "used_text": row.get("used_text"),
                "available_text": row.get("available_text"),
                "source": "qnap_ssh",
            }
            for idx, row in enumerate(qnap_zfs_rows)
        ]
    storage_capacity_mode = "standard"
    storage_capacity_note = ""
    if is_qnap_device:
        qnap_business_rows = _qnap_business_storage_rows(real_storage_rows)
        if qnap_business_rows:
            real_storage_rows = qnap_business_rows
            storage_capacity_mode = "qnap_quota"
            storage_capacity_note = "QNAP 通过 SNMP 返回的是共享文件夹/LUN 配额视图，不能把各共享项相加当作物理池总容量。"
    sorted_storage_rows = sorted(
        real_storage_rows,
        key=lambda item: (
            {"critical": 0, "warning": 1, "normal": 2}.get(str(item.get("alert_level") or "normal"), 9),
            -_safe_float(item.get("usage_percent"), 0.0),
            -_safe_int(item.get("used_bytes"), 0),
        ),
    )
    top_storage_rows = sorted_storage_rows[:4]
    network_rows = [row for row in interface_rows if row.get("kind") in {"physical", "wan", "lan", "bond"}]
    active_interface_summary = _build_active_interface_summary(interface_rows)
    sorted_network_rows = _sort_network_rows(network_rows, device_type=device_type)
    top_traffic_rows = sorted(
        network_rows,
        key=lambda item: _safe_float(item.get("total_rate_bps"), 0.0),
        reverse=True,
    )[:6]
    if not top_traffic_rows:
        top_traffic_rows = active_interface_summary.get("active_top_rows", [])[:6]
    wan_top_rows = [row for row in sorted_network_rows if row.get("kind") == "wan"][:4]
    lan_top_rows = [row for row in sorted_network_rows if row.get("kind") == "lan"][:4]
    physical_top_rows = [row for row in sorted_network_rows if row.get("kind") in {"physical", "bond"}][:4]
    drive_bay_summary = _build_qnap_drive_bays(qnap_disk_rows) if is_qnap_device and qnap_disk_rows else {}
    ucd_disk_io_top_rows = sorted(
        ucd_disk_io_rows,
        key=lambda row: (
            0 if row.get("is_whole_disk") else 1,
            {"critical": 0, "warning": 1, "normal": 2}.get(str(row.get("alert_level") or "normal"), 9),
            -_safe_int(row.get("load_peak"), 0),
            -_safe_int(row.get("bytes_written"), 0),
            -_safe_int(row.get("bytes_read"), 0),
            str(row.get("device") or ""),
        ),
    )[:6]
    cpu_avg_percent = round(sum(cpu_loads) / len(cpu_loads), 1) if cpu_loads else None
    cpu_peak_percent = max(cpu_loads) if cpu_loads else None
    qnap_cpu_usage = _metric_value("qnap_cpu_usage_percent")
    if qnap_cpu_usage is not None:
        cpu_avg_percent = qnap_cpu_usage
        cpu_peak_percent = qnap_cpu_usage if cpu_peak_percent is None else cpu_peak_percent
    if cpu_avg_percent is None:
        cpu_avg_percent = _metric_value("cpu_usage_percent", "cpu_user_percent")
    if cpu_peak_percent is None:
        cpu_peak_percent = cpu_avg_percent
    memory_usage_percent = memory_summary.get("memory_usage_percent")
    cpu_temperature_c = _metric_value("cpu_temperature_c", "temperature_c")
    session_count = _metric_value("session_count")
    network_connections = _metric_value("network_connections")
    nat_sessions = _metric_value("nat_sessions")
    ap_count = _metric_value("ap_count")
    online_clients = _metric_value("online_clients")
    if network_connections is None:
        network_connections = session_count if session_count is not None else nat_sessions
    if session_count is None:
        session_count = network_connections if network_connections is not None else nat_sessions
    vendor_key = f"{result.get('brand') or ''} {result.get('sys_descr') or ''} {result.get('sys_name') or ''}".lower()
    is_ikuai_device = device_type == "router" and (
        "ikuai" in vendor_key
        or "爱快" in vendor_key
        or str(result.get("host") or "").strip() == "192.168.99.3"
    )
    ikuai_summary = _build_ikuai_summary(interface_rows, custom_metric_map, result) if is_ikuai_device else {}
    alert_items: List[Dict[str, Any]] = []

    if cpu_peak_percent is not None and cpu_peak_percent >= 90:
        alert_items.append({"level": "critical", "text": f"CPU peak {cpu_peak_percent}% is high"})
    elif cpu_peak_percent is not None and cpu_peak_percent >= 80:
        alert_items.append({"level": "warning", "text": f"CPU peak {cpu_peak_percent}% is elevated"})

    if memory_usage_percent is not None and memory_usage_percent >= 90:
        alert_items.append({"level": "critical", "text": f"Memory usage {memory_usage_percent}% is high"})
    elif memory_usage_percent is not None and memory_usage_percent >= 80:
        alert_items.append({"level": "warning", "text": f"Memory usage {memory_usage_percent}% is elevated"})
    cpu_temp_num = _safe_float(cpu_temperature_c, -1.0)
    if cpu_temp_num >= 80:
        alert_items.append({"level": "critical", "text": f"CPU temperature {round(cpu_temp_num, 1)}C is high"})
    elif cpu_temp_num >= 70:
        alert_items.append({"level": "warning", "text": f"CPU temperature {round(cpu_temp_num, 1)}C is elevated"})
    if device_type == "switch":
        previous_interface_rows_for_delta = {int(item.get("index")): item for item in previous_interface_rows if item.get("index") is not None}
        switch_anomaly_rows: List[Dict[str, Any]] = []
        for row in interface_rows:
            if row.get("kind") != "physical":
                continue
            prev = previous_interface_rows_for_delta.get(_safe_int(row.get("index"), -1), {})
            has_previous_counters = any(
                key in prev
                for key in ("in_errors", "out_errors", "in_discards", "out_discards")
            )
            if has_previous_counters:
                in_errors_delta = max(0, _safe_int(row.get("in_errors"), 0) - _safe_int(prev.get("in_errors"), 0))
                out_errors_delta = max(0, _safe_int(row.get("out_errors"), 0) - _safe_int(prev.get("out_errors"), 0))
                in_discards_delta = max(0, _safe_int(row.get("in_discards"), 0) - _safe_int(prev.get("in_discards"), 0))
                out_discards_delta = max(0, _safe_int(row.get("out_discards"), 0) - _safe_int(prev.get("out_discards"), 0))
            else:
                in_errors_delta = 0
                out_errors_delta = 0
                in_discards_delta = 0
                out_discards_delta = 0
            row["in_errors_delta"] = in_errors_delta
            row["out_errors_delta"] = out_errors_delta
            row["in_discards_delta"] = in_discards_delta
            row["out_discards_delta"] = out_discards_delta
            row["error_delta_total"] = in_errors_delta + out_errors_delta
            row["discard_delta_total"] = in_discards_delta + out_discards_delta
            utilization_percent = _safe_float(row.get("utilization_percent"), -1.0)
            switch_anomaly_rows.append(
                {
                    "name": row.get("name"),
                    "error_delta_total": row["error_delta_total"],
                    "discard_delta_total": row["discard_delta_total"],
                    "utilization_percent": utilization_percent if utilization_percent >= 0 else None,
                }
            )
        interface_summary = _summarize_interfaces(interface_rows)
        if if_number_value > 0:
            interface_summary["interface_total_count"] = if_number_value
        interface_summary["interface_sample_count"] = len(interface_rows)
        if bridge_summary:
            interface_summary = _merge_switch_bridge_summary(interface_summary, bridge_summary)
            if if_number_value > 0:
                interface_summary["interface_total_count"] = if_number_value
            interface_summary["interface_sample_count"] = len(interface_rows)
        interface_summary = _merge_switch_static_topology(interface_summary, result.get("static_config"))
        ranked_switch_anomalies = sorted(
            [row for row in switch_anomaly_rows if _safe_int(row.get("error_delta_total"), 0) > 0 or _safe_int(row.get("discard_delta_total"), 0) > 0 or _safe_float(row.get("utilization_percent"), 0.0) >= 80],
            key=lambda row: (
                -_safe_int(row.get("discard_delta_total"), 0),
                -_safe_int(row.get("error_delta_total"), 0),
                -_safe_float(row.get("utilization_percent"), 0.0),
                str(row.get("name") or ""),
            ),
        )
        if ranked_switch_anomalies:
            top_switch_anomalies = ranked_switch_anomalies[:6]
            for row in top_switch_anomalies:
                if _safe_int(row.get("discard_delta_total"), 0) > 0:
                    alert_items.append({"level": "warning", "text": f"Port {row.get('name')} has {row.get('discard_delta_total')} new discards"})
                elif _safe_int(row.get("error_delta_total"), 0) > 0:
                    alert_items.append({"level": "warning", "text": f"Port {row.get('name')} has {row.get('error_delta_total')} new errors"})
                elif _safe_float(row.get("utilization_percent"), 0.0) >= 80:
                    alert_items.append({"level": "warning", "text": f"Port {row.get('name')} utilization {row.get('utilization_percent')}% is high"})
            if len(ranked_switch_anomalies) > len(top_switch_anomalies):
                extra_count = len(ranked_switch_anomalies) - len(top_switch_anomalies)
                alert_items.append({"level": "info", "text": f"{extra_count} more switch ports have lower-priority anomalies"})

    for row in top_storage_rows:
        usage_percent = row.get("usage_percent")
        if usage_percent is not None and usage_percent >= 92:
            alert_items.append({"level": "critical", "text": f"Storage {row.get('descr')} usage {usage_percent}% is high"})
        elif usage_percent is not None and usage_percent >= 85:
            alert_items.append({"level": "warning", "text": f"Storage {row.get('descr')} usage {usage_percent}% is elevated"})

    if not network_rows and device_type == "router":
        alert_items.append({"level": "info", "text": "Router interface classification is limited; vendor-specific OIDs can improve visibility"})

    if ikuai_summary:
        for row in ikuai_summary.get("issue_rows", [])[:4]:
            errors = _safe_int(row.get("errors"), 0)
            discards = _safe_int(row.get("discards"), 0)
            utilization = _safe_float(row.get("utilization_percent"), 0.0)
            display_name = row.get("display_name") or row.get("name") or "--"
            if errors > 0:
                alert_items.append({"level": "warning", "text": f"iKuai {display_name} has {errors} interface errors"})
            elif discards > 0:
                alert_items.append({"level": "warning", "text": f"iKuai {display_name} has {discards} discards"})
            elif utilization >= 70:
                alert_items.append({"level": "warning", "text": f"iKuai {display_name} utilization {round(utilization, 1)}% is high"})
            elif str(row.get("status_text") or "") != "在线":
                alert_items.append({"level": "warning", "text": f"iKuai {display_name} is {row.get('status_text') or 'offline'}"})

    for row in qnap_disk_rows:
        status_text = str(row.get("status") or "--").strip()
        temp_c = row.get("temp_c")
        if status_text and status_text.upper() not in {"GOOD", "ONLINE", "--"}:
            alert_items.append({"level": "warning", "text": f"{row.get('slot') or '硬盘'} 健康状态异常：{status_text}"})
        temp_level = _qnap_disk_temp_level(row.get("media_type"), temp_c)
        if temp_level == "critical":
            alert_items.append({"level": "critical", "text": f"{row.get('slot') or '硬盘'} 温度过高：{temp_c}°C"})
        elif temp_level == "warning":
            alert_items.append({"level": "warning", "text": f"{row.get('slot') or '硬盘'} 温度偏高：{temp_c}°C"})

    for row in qnap_fan_rows:
        rpm = _safe_int(row.get("rpm"), 0)
        if 0 < rpm < 500:
            alert_items.append({"level": "warning", "text": f"{row.get('name') or 'Fan'} speed {rpm} RPM is low"})
    for row in list(qnap_ssh_summary.get("zpool_rows") or []):
        if str(row.get("alert_level") or "") == "critical":
            alert_items.append({"level": "critical", "text": f"QNAP pool {row.get('name') or '--'} state {row.get('state') or '--'}"})
    for row in ucd_disk_io_top_rows[:4]:
        load_peak = _safe_int(row.get("load_peak"), 0)
        if load_peak >= 90:
            alert_items.append({"level": "critical", "text": f"Disk {row.get('device')} I/O load {load_peak}% is high"})
        elif load_peak >= 70:
            alert_items.append({"level": "warning", "text": f"Disk {row.get('device')} I/O load {load_peak}% is elevated"})

    deduped_alerts: List[Dict[str, Any]] = []
    seen_alert_keys = set()
    for item in alert_items:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or "info").strip().lower() or "info"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        key = (level, text)
        if key in seen_alert_keys:
            continue
        seen_alert_keys.add(key)
        deduped_alerts.append({"level": level, "text": text})

    location_text = location_text if location_text and location_text != '""' else "--"
    contact_text = _decode_hex_text(result.get("sys_contact") or "")
    contact_text = contact_text if contact_text and contact_text != '""' else "--"
    sys_descr_text = _decode_hex_text(result.get("sys_descr") or "")
    storage_warning_count = len([row for row in real_storage_rows if row.get("alert_level") == "warning"])
    storage_critical_count = len([row for row in real_storage_rows if row.get("alert_level") == "critical"])
    alert_counts = {
        "critical": len([item for item in deduped_alerts if item.get("level") == "critical"]),
        "warning": len([item for item in deduped_alerts if item.get("level") == "warning"]),
        "info": len([item for item in deduped_alerts if item.get("level") == "info"]),
    }
    health_score = 100
    health_score -= alert_counts["critical"] * 22
    health_score -= alert_counts["warning"] * 5
    health_score -= storage_critical_count * 10
    health_score -= storage_warning_count * 3
    if device_type == "switch":
        health_score -= min(24, _safe_int(interface_summary.get("delta_error_port_count"), 0) * 4)
        health_score -= min(20, _safe_int(interface_summary.get("delta_discard_port_count"), 0) * 3)
        health_score -= min(10, _safe_int(interface_summary.get("busy_port_count"), 0) * 2)
    elif device_type == "router":
        health_score -= _safe_int(interface_summary.get("error_port_count"), 0) * 4
        health_score -= _safe_int(interface_summary.get("discard_port_count"), 0) * 3
        health_score -= _safe_int(interface_summary.get("busy_port_count"), 0) * 2
    elif device_type == "nas":
        health_score -= len([row for row in qnap_disk_rows if row.get("alert_level") == "critical"]) * 10
        health_score -= len([row for row in qnap_disk_rows if row.get("alert_level") == "warning"]) * 5
        health_score -= len([row for row in ucd_disk_io_top_rows if str(row.get("alert_level")) == "critical"]) * 6
        health_score -= len([row for row in list(qnap_ssh_summary.get("zpool_rows") or []) if str(row.get("alert_level") or "") == "critical"]) * 16
    health_score = max(0, min(100, int(health_score)))
    risk_level = "normal"
    if health_score < 50 or alert_counts["critical"] > 0:
        risk_level = "critical"
    elif health_score < 75 or alert_counts["warning"] > 0:
        risk_level = "warning"
    gpu_metrics = _extract_gpu_metrics(custom_metrics)
    summary = {
        "device_type": device_type or "network",
        "sys_descr_text": sys_descr_text if sys_descr_text else str(result.get("sys_descr") or ""),
        "cpu_core_count": len(cpu_loads),
        "cpu_avg_percent": cpu_avg_percent,
        "cpu_peak_percent": cpu_peak_percent,
        "cpu_loads": cpu_loads[:16],
        "memory_total_kb": _safe_int(memory_kb, 0) if memory_kb not in (None, "") else None,
        "memory_total_gb": _format_memory_gb(memory_kb),
        "memory_total_text": memory_summary.get("memory_total_text"),
        "memory_used_text": memory_summary.get("memory_used_text"),
        "memory_available_text": memory_summary.get("memory_available_text"),
        "memory_usage_percent": memory_summary.get("memory_usage_percent"),
        "memory_alert_level": memory_summary.get("memory_alert_level"),
        "ucd_load_1": ucd_summary.get("load_1"),
        "ucd_load_5": ucd_summary.get("load_5"),
        "ucd_load_15": ucd_summary.get("load_15"),
        "ucd_mem_total_text": ucd_summary.get("mem_total_text"),
        "ucd_mem_available_text": ucd_summary.get("mem_available_text"),
        "ucd_mem_buffer_text": ucd_summary.get("mem_buffer_text"),
        "ucd_mem_cached_text": ucd_summary.get("mem_cached_text"),
        "ucd_disk_io_rows": ucd_disk_io_rows[:16],
        "ucd_disk_io_top_rows": ucd_disk_io_top_rows,
        "cpu_temperature_c": cpu_temperature_c,
        "system_temperature_c": qnap_ssh_summary.get("system_temperature_c"),
        "temperature_rows": list(qnap_ssh_summary.get("temperature_rows") or [])[:12],
        "session_count": session_count,
        "network_connections": network_connections,
        "nat_sessions": nat_sessions,
        "ap_count": ap_count,
        "online_clients": online_clients,
        "swap_total_text": memory_summary.get("swap_total_text"),
        "swap_used_text": memory_summary.get("swap_used_text"),
        "swap_usage_percent": memory_summary.get("swap_usage_percent"),
        "swap_alert_level": memory_summary.get("swap_alert_level"),
        "vendor_memory_total_text": vendor_memory_total_text or None,
        "vendor_memory_free_text": vendor_memory_free_text or None,
        "qnap_ssh_summary": qnap_ssh_summary,
        "process_count": _safe_int(process_count, 0) if str(process_count).strip().isdigit() else None,
        "user_count": _safe_int(user_count, 0) if str(user_count).strip().isdigit() else None,
        "interface_names": interface_names,
        "interface_preview": " / ".join(interface_names) if interface_names else "--",
        "interface_rows": interface_rows[:24],
        "interface_summary": interface_summary,
        "ikuai_summary": ikuai_summary,
        "network_top_rows": top_traffic_rows,
        "wan_top_rows": wan_top_rows,
        "lan_top_rows": lan_top_rows,
        "physical_top_rows": physical_top_rows,
        "storage_rows": sorted_storage_rows[:24],
        "storage_top_rows": top_storage_rows,
        "storage_count": len(real_storage_rows),
        "storage_capacity_mode": storage_capacity_mode,
        "storage_capacity_note": storage_capacity_note,
        "storage_warning_count": storage_warning_count,
        "storage_critical_count": storage_critical_count,
        "disk_rows": qnap_disk_rows[:16],
        "disk_top_rows": qnap_disk_rows[:6],
        "disk_count": len(qnap_disk_rows),
        "drive_bay_summary": drive_bay_summary,
        "fan_rows": qnap_fan_rows[:12],
        "fan_count": len(qnap_fan_rows),
        "alert_items": deduped_alerts[:8],
        "alert_counts": alert_counts,
        "health_score": health_score,
        "risk_level": risk_level,
        "gpu_metrics": gpu_metrics,
        "uptime_text": _format_uptime_text(result.get("sys_uptime")),
        "location_text": location_text,
        "contact_text": contact_text,
        "boot_params_preview": (str(boot_params or "")[:96] + "...") if boot_params and len(str(boot_params)) > 96 else str(boot_params or ""),
        "poll_elapsed_sec": round(elapsed_sec, 2) if elapsed_sec > 0 else 0.0,
        "qnap_cpu_usage_raw": _metric_raw("qnap_cpu_usage_percent"),
    }
    return summary


def _coerce_metric_value(raw_value: str, value_type: str = "auto", scale: Any = 1, precision: Any = None) -> Any:
    mode = str(value_type or "auto").strip().lower()
    scale_num = _safe_float(scale, 1.0)
    precision_num = None if precision in (None, "") else _safe_int(precision, 0)

    def _apply_scale(number: float) -> Any:
        result = number * scale_num
        if precision_num is not None:
            return round(result, precision_num)
        if float(result).is_integer():
            return int(result)
        return round(result, 4)

    def _first_number() -> float | None:
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except Exception:
            return None

    text = str(raw_value or "").strip()
    lowered = text.lower()
    if lowered.startswith("no such ") or lowered.startswith("end of mib") or lowered.startswith("no more variables"):
        return None
    if mode in {"string", "str", "text"}:
        return text
    if mode in {"int", "integer"}:
        number = _first_number()
        return _apply_scale(float(int(number))) if number is not None else None
    if mode in {"float", "number", "numeric", "timeticks"}:
        number = _first_number()
        return _apply_scale(number) if number is not None else None
    if mode == "auto":
        try:
            if "." in text:
                return _apply_scale(float(text))
            return _apply_scale(float(int(text)))
        except Exception:
            number = _first_number()
            return _apply_scale(number) if number is not None else text
    return text


def _build_auth(config: Dict[str, Any]):
    version = _normalize_version(config.get("version"))
    if version in {"v1", "v2c"}:
        community = str(config.get("community") or "public")
        return CommunityData(community, mpModel=0 if version == "v1" else 1)

    security_level = _normalize_security_level(config.get("security_level"))
    auth_protocol = AUTH_PROTOCOL_MAP.get(_normalize_protocol_name(config.get("auth_protocol") or "SHA"), usmHMACSHAAuthProtocol)
    priv_protocol = PRIV_PROTOCOL_MAP.get(_normalize_protocol_name(config.get("priv_protocol") or "AES"), usmAesCfb128Protocol)
    username = str(config.get("username") or "").strip()
    auth_password = str(config.get("auth_password") or "")
    priv_password = str(config.get("priv_password") or "")

    if security_level == "noAuthNoPriv":
        return UsmUserData(username, authProtocol=usmNoAuthProtocol, privProtocol=usmNoPrivProtocol)
    if security_level == "authNoPriv":
        return UsmUserData(username, authKey=auth_password, authProtocol=auth_protocol, privProtocol=usmNoPrivProtocol)
    return UsmUserData(
        username,
        authKey=auth_password,
        privKey=priv_password,
        authProtocol=auth_protocol,
        privProtocol=priv_protocol,
    )


async def _get_values_async(config: Dict[str, Any], oid_pairs: List[Tuple[str, str]]) -> Tuple[Dict[str, str], str]:
    host = str(config.get("host") or config.get("ip") or "").strip()
    port = _safe_int(config.get("port"), 161)
    timeout_sec = _effective_timeout_sec(config)
    retries = _effective_retries(config)
    source_ip = str(config.get("source_ip") or "").strip()
    context_name = str(config.get("context_name") or "")

    target = UdpTransportTarget((host, port), timeout=timeout_sec, retries=retries)
    if source_ip:
        target.setLocalAddress((source_ip, 0))

    engine = SnmpEngine()
    try:
        object_types = [ObjectType(ObjectIdentity(oid)) for _, oid in oid_pairs]
        error_indication, error_status, error_index, var_binds = await getCmd(
            engine,
            _build_auth(config),
            target,
            ContextData(contextName=context_name),
            *object_types,
            lookupMib=False,
        )
        if error_indication:
            return {}, str(error_indication)
        if error_status:
            return {}, error_status.prettyPrint()

        values: Dict[str, str] = {}
        for idx, (key, _) in enumerate(oid_pairs):
            if idx < len(var_binds):
                values[key] = var_binds[idx][1].prettyPrint()
        return values, ""
    except Exception as exc:
        return {}, str(exc)
    finally:
        _close_snmp_engine(engine)


async def _get_values_batched_async(
    config: Dict[str, Any],
    oid_pairs: List[Tuple[str, str]],
    batch_size: int = 28,
) -> Tuple[Dict[str, str], str]:
    pairs = list(oid_pairs or [])
    if not pairs:
        return {}, ""
    values: Dict[str, str] = {}
    errors: List[str] = []
    size = max(1, int(batch_size or 1))
    for offset in range(0, len(pairs), size):
        chunk = pairs[offset : offset + size]
        chunk_values, error_text = await _get_values_async(config, chunk)
        if error_text:
            errors.append(error_text)
            continue
        values.update(chunk_values)
    return values, "; ".join(dict.fromkeys(errors))


def _static_switch_port_indices(static_config: Dict[str, Any] | None) -> List[int]:
    topology = _build_static_switch_topology(static_config)
    indices: List[int] = []
    for row in topology.get("configured_port_rows") or []:
        key = str(row.get("key") or "")
        match = re.search(r":\d+/\d+/(\d+)$", key)
        if not match:
            match = re.search(r"(\d+)$", str(row.get("name") or ""))
        if not match:
            continue
        idx = _safe_int(match.group(1), 0)
        if idx > 0 and idx not in indices:
            indices.append(idx)
    return sorted(indices)


def _direct_interface_indices_for_device(device: Dict[str, Any], result: Dict[str, Any]) -> List[int]:
    device_type = str(device.get("device_type") or "").strip().lower()
    configured_indices = _static_switch_port_indices(device.get("static_config"))
    if configured_indices:
        return [idx for idx in configured_indices if 0 < idx <= 128]
    if device_type == "router":
        walk_values = dict(result.get("walk_values", {}) or {})
        name_prefixes = (
            "1.3.6.1.2.1.31.1.1.1.1.",
            "1.3.6.1.2.1.2.2.1.2.",
        )
        wanted_names = {"eth0", "eth1", "eth2", "eth3", "lan1", "lan2", "wan1", "wan1_ad"}
        indices: List[int] = []
        for oid, value in walk_values.items():
            if not any(str(oid).startswith(prefix) for prefix in name_prefixes):
                continue
            name = str(value or "").strip().lower()
            if name not in wanted_names:
                continue
            try:
                idx = int(str(oid).split(".")[-1])
            except Exception:
                continue
            if 0 < idx <= 128 and idx not in indices:
                indices.append(idx)
        if indices:
            return sorted(indices)
    return list(range(1, max(0, _safe_int(result.get("if_number"), 0)) + 1))[:128]


def _merge_direct_switch_port_values(walk_values: Dict[str, str], direct_values: Dict[str, str]) -> Dict[str, str]:
    merged = dict(walk_values or {})
    for key, raw_value in (direct_values or {}).items():
        text = str(key or "")
        if "." not in text:
            continue
        metric, idx = text.rsplit(".", 1)
        oid_root = SWITCH_DIRECT_PORT_OID_ROOTS.get(metric)
        if not oid_root:
            continue
        merged[f"{oid_root}.{idx}"] = str(raw_value)
    return merged


async def _walk_root_async(config: Dict[str, Any], root_oid: str, max_oids: int, start_oid: str | None = None) -> Tuple[Dict[str, str], bool, str, str]:
    host = str(config.get("host") or config.get("ip") or "").strip()
    port = _safe_int(config.get("port"), 161)
    timeout_sec = _effective_timeout_sec(config)
    retries = _effective_retries(config)
    source_ip = str(config.get("source_ip") or "").strip()
    context_name = str(config.get("context_name") or "")

    target = UdpTransportTarget((host, port), timeout=timeout_sec, retries=retries)
    if source_ip:
        target.setLocalAddress((source_ip, 0))

    result: Dict[str, str] = {}
    truncated = False
    started_at = time.monotonic()
    max_duration_sec = max(1.0, _safe_float(config.get("walk_root_max_sec"), 1.2))
    cursor_oid = str(start_oid or "").strip()
    if cursor_oid and (cursor_oid == root_oid or cursor_oid.startswith(root_oid + ".")):
        current_object = ObjectType(ObjectIdentity(cursor_oid))
    else:
        current_object = ObjectType(ObjectIdentity(root_oid))
    next_oid = ""
    engine = SnmpEngine()
    try:
        while len(result) < max_oids:
            if (time.monotonic() - started_at) >= max_duration_sec:
                truncated = True
                break
            error_indication, error_status, error_index, var_bind_table = await nextCmd(
                engine,
                _build_auth(config),
                target,
                ContextData(contextName=context_name),
                current_object,
                lexicographicMode=False,
                ignoreNonIncreasingOid=True,
                lookupMib=False,
            )
            if error_indication:
                return result, truncated, str(error_indication), next_oid
            if error_status:
                return result, truncated, error_status.prettyPrint(), next_oid
            if not var_bind_table:
                break

            next_oid = ""
            should_stop = False
            for row in var_bind_table:
                for var_bind in row:
                    oid_obj, value_obj = var_bind
                    oid_text = oid_obj.prettyPrint()
                    if oid_text != root_oid and not oid_text.startswith(root_oid + "."):
                        should_stop = True
                        break
                    result[oid_text] = value_obj.prettyPrint()
                    next_oid = oid_text
                    if len(result) >= max_oids:
                        truncated = True
                        should_stop = True
                        break
                if should_stop:
                    break
            if should_stop or not next_oid:
                break
            current_object = ObjectType(ObjectIdentity(next_oid))
        return result, truncated, "", next_oid
    except Exception as exc:
        return result, truncated, str(exc), next_oid
    finally:
        _close_snmp_engine(engine)


def _rotated_walk_roots(roots: List[str], start_index: int) -> List[str]:
    normalized = list(roots or [])
    if not normalized:
        return []
    start = max(0, int(start_index or 0))
    if start >= len(normalized):
        start = 0
    return normalized[start:] + normalized[:start]


async def _walk_roots_async(
    config: Dict[str, Any],
    roots: List[str],
    max_oids: int,
    start_index: int = 0,
    max_roots_per_cycle: int | None = None,
    root_cursors: Dict[str, str] | None = None,
    required_roots: List[str] | None = None,
) -> Tuple[Dict[str, str], List[Dict[str, Any]], bool, str, int, Dict[str, str]]:
    combined: Dict[str, str] = {}
    stats: List[Dict[str, Any]] = []
    any_truncated = False
    per_root_limit = max(1, int(max_oids))
    normalized_roots = list(roots or [])
    if not normalized_roots:
        return combined, stats, any_truncated, "", 0, {}
    cursors = {
        str(root): str(cursor)
        for root, cursor in dict(root_cursors or {}).items()
        if str(root or "").strip() and str(cursor or "").strip()
    }
    start = max(0, int(start_index or 0))
    if start >= len(normalized_roots):
        start = 0
    cycle_limit = max(1, int(max_roots_per_cycle or len(normalized_roots)))
    rotated_roots = _rotated_walk_roots(normalized_roots, start)
    normalized_required = [
        root
        for root in (required_roots or [])
        if root in normalized_roots
    ]
    selected_roots: List[str] = []
    for root in normalized_required:
        if root not in selected_roots:
            selected_roots.append(root)
    for root in rotated_roots:
        if root in cursors and root not in selected_roots:
            selected_roots.append(root)
        if len(selected_roots) >= cycle_limit:
            break
    for root in rotated_roots:
        if root not in selected_roots:
            selected_roots.append(root)
        if len(selected_roots) >= cycle_limit:
            break

    for root in selected_roots:
        force_fresh = root in normalized_required
        start_oid = "" if force_fresh else cursors.get(root)
        walked, truncated, error_text, next_cursor = await _walk_root_async(config, root, per_root_limit, start_oid=start_oid)
        combined.update(walked)
        if force_fresh:
            cursors.pop(root, None)
        elif truncated and next_cursor and next_cursor.startswith(root + "."):
            cursors[root] = next_cursor
        else:
            cursors.pop(root, None)
        stats.append(
            {
                "root": root,
                "count": len(walked),
                "truncated": bool(truncated),
                "continued_from": start_oid or "",
                "next_cursor": cursors.get(root, ""),
                "error": error_text,
            }
        )
        any_truncated = any_truncated or truncated
        if error_text:
            last_root_index = normalized_roots.index(root) if root in normalized_roots else start
            next_index = (last_root_index + 1) % len(normalized_roots)
            return combined, stats, any_truncated, error_text, next_index, cursors
    if selected_roots:
        last_root = selected_roots[-1]
        last_root_index = normalized_roots.index(last_root) if last_root in normalized_roots else start
        next_index = (last_root_index + 1) % len(normalized_roots)
    else:
        next_index = start
    return combined, stats, any_truncated, "", next_index, cursors


def _build_walk_summary(walk_values: Dict[str, str], limit: int = 10) -> List[Dict[str, str]]:
    samples = []
    for oid, value in list(walk_values.items())[: max(1, int(limit))]:
        samples.append({"oid": oid, "value": value})
    return samples


def poll_snmp_device(config: Dict[str, Any], previous_status: Dict[str, Any] | None = None) -> Dict[str, Any]:
    device = deepcopy(config or {})
    previous = dict(previous_status or {})
    first_poll = not bool(previous.get("updated_at"))
    now_monotonic = time.monotonic()
    oid_map = build_default_snmp_oid_map()
    oid_map.update(device.get("oid_map") or {})
    standard_pairs = [(key, oid) for key, oid in oid_map.items() if str(oid or "").strip()]

    custom_metrics = []
    custom_pairs = []
    for item in device.get("custom_oids") or []:
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        metric_name = str(item.get("name") or "").strip()
        oid = str(item.get("oid") or "").strip()
        if not metric_name or not oid:
            continue
        custom_pairs.append((metric_name, oid))
        custom_metrics.append(item)

    result = {
        "online": False,
        "device_type": str(device.get("device_type") or "network").strip().lower() or "network",
        "version": _normalize_version(device.get("version")),
        "updated_at": datetime.now().isoformat(),
        "previous_updated_at": previous.get("updated_at"),
        "polled_monotonic": now_monotonic,
        "previous_polled_monotonic": float(previous.get("last_polled_monotonic", previous.get("polled_monotonic", 0.0)) or 0.0),
        "host": str(device.get("host") or device.get("ip") or "").strip(),
        "port": _safe_int(device.get("port"), 161),
        "error": "",
        "metrics": {},
        "raw_oids": {},
        "custom_metrics": [],
        "walk_enabled": bool(device.get("walk_enabled", False)),
        "walk_roots": _normalize_walk_roots(device.get("walk_roots") or []),
        "walk_total_oids": int(previous.get("walk_total_oids", 0) or 0),
        "previous_walk_values": dict(previous.get("walk_values", {}) or {}),
        "walk_values": dict(previous.get("walk_values", {}) or {}),
        "walk_samples": list(previous.get("walk_samples", []) or []),
        "walk_root_stats": list(previous.get("walk_root_stats", []) or []),
        "walk_root_cursors": dict(previous.get("walk_root_cursors", {}) or {}),
        "walk_error": str(previous.get("walk_error") or ""),
        "walk_truncated": bool(previous.get("walk_truncated", False)),
        "walk_counter_cycle_complete": bool(previous.get("walk_counter_cycle_complete", False)),
        "previous_walk_counter_cycle_complete": bool(previous.get("walk_counter_cycle_complete", False)),
        "previous_summary": dict(previous.get("summary", {}) or {}),
        "previous_last_walk_polled_monotonic": float(previous.get("last_walk_polled_monotonic", 0.0) or 0.0),
        "previous_last_walk_updated_at": previous.get("last_walk_updated_at"),
        "last_walk_polled_monotonic": float(previous.get("last_walk_polled_monotonic", 0.0) or 0.0),
        "last_walk_updated_at": previous.get("last_walk_updated_at"),
        "walk_cycle_index": _safe_int(previous.get("walk_cycle_index"), 0),
        "static_config": dict(device.get("static_config", {}) or {}),
        "storage_aliases": dict(device.get("storage_aliases", {}) or {}),
    }
    if not result["host"]:
        result["error"] = "SNMP host is empty"
        return result

    result["timeout_sec"] = _effective_timeout_sec(device)
    result["retries"] = _effective_retries(device)

    try:
        raw_values, error_text = asyncio.run(_get_values_async(device, standard_pairs + custom_pairs))
        if error_text:
            result["error"] = error_text
            return result
        result["online"] = True
        result["raw_oids"] = raw_values
        for key in DEFAULT_SNMP_OID_MAP.keys():
            if key in raw_values:
                result[key] = raw_values[key]
        if "if_number" in result:
            result["if_number"] = _safe_int(result.get("if_number"), 0)

        custom_metric_map = {item.get("name"): item for item in custom_metrics}
        for metric_name, raw_value in [(key, value) for key, value in raw_values.items() if key not in DEFAULT_SNMP_OID_MAP]:
            metric_cfg = custom_metric_map.get(metric_name, {}) or {}
            parsed_value = _coerce_metric_value(
                raw_value,
                value_type=metric_cfg.get("value_type", "auto"),
                scale=metric_cfg.get("scale", 1),
                precision=metric_cfg.get("precision"),
            )
            result["metrics"][metric_name] = parsed_value
            result["custom_metrics"].append(
                {
                    "name": metric_name,
                    "oid": metric_cfg.get("oid"),
                    "raw": raw_value,
                    "value": parsed_value,
                    "unit": metric_cfg.get("unit", ""),
                    "value_type": metric_cfg.get("value_type", "auto"),
                }
            )

        walk_enabled = bool(device.get("walk_enabled", False))
        walk_roots = _augment_walk_roots_for_device(
            device,
            _normalize_walk_roots(device.get("walk_roots") or build_default_snmp_walk_roots_for_device(device)),
        )
        walk_max_oids = max(10, _safe_int(device.get("walk_max_oids"), 256))
        walk_sample_limit = max(1, _safe_int(device.get("walk_sample_limit"), 12))
        walk_interval_ms = _effective_walk_interval_ms(device)
        device_type_text = str(device.get("device_type") or "").strip().lower()
        critical_walk_roots = [
            root
            for root in _critical_walk_roots_for_device(device_type_text)
            if root in walk_roots
        ]
        configured_roots_per_cycle = _safe_int(device.get("walk_roots_per_cycle"), 0)
        if configured_roots_per_cycle > 0:
            walk_roots_per_cycle = max(1, configured_roots_per_cycle)
        else:
            walk_roots_per_cycle = _default_walk_roots_per_cycle(device_type_text)
        if critical_walk_roots:
            walk_roots_per_cycle = max(walk_roots_per_cycle, len(critical_walk_roots))
        if device_type_text == "switch":
            walk_max_oids = min(max(walk_max_oids, 256), 512)
            device["walk_root_max_sec"] = max(2.0, _safe_float(device.get("walk_root_max_sec"), 1.2))
        elif device_type_text in {"nas", "router"}:
            walk_max_oids = min(max(walk_max_oids, 320), 640)
            device["walk_root_max_sec"] = max(1.8, _safe_float(device.get("walk_root_max_sec"), 1.2))
        result["walk_enabled"] = walk_enabled
        result["walk_roots"] = walk_roots

        if walk_enabled and walk_roots:
            last_walk = float(previous.get("last_walk_polled_monotonic", 0.0) or 0.0)
            root_count = max(1, len(walk_roots))
            cycle_stride = max(1, walk_roots_per_cycle)
            if (now_monotonic - last_walk) * 1000 >= walk_interval_ms or not previous.get("walk_values"):
                previous_walk_values = dict(previous.get("walk_values", {}) or {})
                walk_cycle_index = _safe_int(previous.get("walk_cycle_index"), 0)
                walked_values, walk_stats, walk_truncated, walk_error, next_walk_cycle_index, next_root_cursors = asyncio.run(
                    _walk_roots_async(
                        device,
                        walk_roots,
                        walk_max_oids,
                        start_index=walk_cycle_index,
                        max_roots_per_cycle=walk_roots_per_cycle,
                        root_cursors=dict(previous.get("walk_root_cursors", {}) or {}),
                        required_roots=critical_walk_roots,
                    )
                )
                merged_walk_values = dict(previous_walk_values)
                merged_walk_values.update(walked_values)
                result["walk_values"] = merged_walk_values
                result["walk_total_oids"] = len(merged_walk_values)
                result["walk_root_stats"] = walk_stats
                result["walk_root_cursors"] = next_root_cursors
                result["walk_error"] = walk_error
                result["walk_truncated"] = bool(walk_truncated)
                result["walk_samples"] = _build_walk_summary(merged_walk_values, walk_sample_limit)
                result["last_walk_polled_monotonic"] = now_monotonic
                result["last_walk_updated_at"] = datetime.now().isoformat()
                result["walk_cycle_index"] = next_walk_cycle_index
                result["walk_counter_cycle_complete"] = (
                    next_walk_cycle_index == 0
                    or cycle_stride >= root_count
                    or (walk_cycle_index + cycle_stride) >= root_count
                )
                if configured_roots_per_cycle <= 0:
                    result["walk_counter_cycle_complete"] = True
            else:
                result["walk_values"] = dict(previous.get("walk_values", {}) or {})
                result["walk_total_oids"] = int(previous.get("walk_total_oids", 0) or 0)
                result["walk_root_stats"] = list(previous.get("walk_root_stats", []) or [])
                result["walk_root_cursors"] = dict(previous.get("walk_root_cursors", {}) or {})
                result["walk_error"] = str(previous.get("walk_error") or "")
                result["walk_truncated"] = bool(previous.get("walk_truncated", False))
                result["walk_samples"] = list(previous.get("walk_samples", []) or [])
                result["walk_counter_cycle_complete"] = bool(previous.get("walk_counter_cycle_complete", False))
                result["last_walk_polled_monotonic"] = float(previous.get("last_walk_polled_monotonic", 0.0) or 0.0)
                result["last_walk_updated_at"] = previous.get("last_walk_updated_at")
                result["walk_cycle_index"] = _safe_int(previous.get("walk_cycle_index"), 0)
        else:
            result["walk_values"] = {}
            result["walk_total_oids"] = 0
            result["walk_root_stats"] = []
            result["walk_root_cursors"] = {}
            result["walk_error"] = ""
            result["walk_truncated"] = False
            result["walk_samples"] = []
            result["walk_counter_cycle_complete"] = False
            result["last_walk_polled_monotonic"] = 0.0
            result["last_walk_updated_at"] = None
            result["walk_cycle_index"] = 0
        if walk_enabled and device_type_text in {"switch", "router"}:
            direct_indices = _direct_interface_indices_for_device(device, result)
            if direct_indices:
                direct_pairs = [
                    (f"{metric}.{idx}", f"{oid_root}.{idx}")
                    for metric, oid_root in SWITCH_DIRECT_PORT_OID_ROOTS.items()
                    for idx in direct_indices
                ]
                direct_values, direct_error = asyncio.run(_get_values_batched_async(device, direct_pairs, batch_size=28))
                if direct_values:
                    result["walk_values"] = _merge_direct_switch_port_values(result.get("walk_values", {}), direct_values)
                    result["walk_total_oids"] = len(result["walk_values"])
                    result["direct_interface_poll_count"] = len(direct_values)
                    result["direct_interface_indices"] = direct_indices
                    result["direct_interface_updated_at"] = datetime.now().isoformat()
                    result["direct_port_poll_count"] = len(direct_values)
                    result["direct_port_indices"] = direct_indices
                    result["direct_port_updated_at"] = result["direct_interface_updated_at"]
                    result["last_walk_polled_monotonic"] = now_monotonic
                    result["last_walk_updated_at"] = result["direct_interface_updated_at"]
                    result["walk_counter_cycle_complete"] = True
                if direct_error:
                    existing_error = str(result.get("walk_error") or "")
                    result["walk_error"] = f"{existing_error}; direct_interface: {direct_error}".strip("; ")
        result["qnap_ssh_summary"] = _build_qnap_ssh_summary(device, result) if device.get("ssh_enrich_enabled", False) is True else {}
        result["summary"] = _build_snmp_summary(result)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
