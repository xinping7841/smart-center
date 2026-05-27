from copy import deepcopy
from datetime import datetime
import json
import socket
from typing import Any, Dict, List, Optional

from config import CONFIG, DEVICE_STATUS, ENV_STATUS, LIGHT_ONLINE, LIGHT_STATUS, METER_STATUS
from runtime.state import PROJECTOR_STATUS, SCREEN_STATUS, SNMP_STATUS, UPS_STATUS


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _base_driver(
    driver_id: str,
    group: str,
    name: str,
    protocol: str,
    comm_mode: str,
    cfg: Dict[str, Any],
    enabled: bool = True,
    visible: bool = True,
) -> Dict[str, Any]:
    return {
        "driver_id": str(driver_id),
        "group": str(group),
        "name": str(name or driver_id),
        "protocol": str(protocol or ""),
        "comm_mode": str(comm_mode or ""),
        "enabled": bool(enabled),
        "visible": bool(visible),
        "target": {
            "ip": str(cfg.get("ip") or cfg.get("host") or "").strip(),
            "port": _safe_int(cfg.get("port"), 0),
            "com_port": str(cfg.get("com_port") or "").strip(),
            "slave_id": _safe_int(cfg.get("slave_id", cfg.get("station_id", 1)), 1),
            "address": _safe_int(cfg.get("address", 1), 1),
        },
        "config_ref": cfg,
    }


def list_drivers(include_disabled: bool = True) -> List[Dict[str, Any]]:
    drivers: List[Dict[str, Any]] = []

    for idx, cab in enumerate(CONFIG.get("cabinets", []) or []):
        cfg = dict(cab or {})
        entry = _base_driver(
            driver_id=f"power:{idx}",
            group="power",
            name=str(cfg.get("cabinet_name") or f"Cabinet {idx + 1}"),
            protocol=str(cfg.get("plc_type") or "AV-100"),
            comm_mode="TCP",
            cfg=cfg,
            enabled=True,
            visible=_to_bool(cfg.get("visible"), True),
        )
        entry["cabinet_index"] = idx
        if include_disabled or entry["visible"]:
            drivers.append(entry)

    for meter in CONFIG.get("meters", []) or []:
        cfg = dict(meter or {})
        entry = _base_driver(
            driver_id=f"meter:{cfg.get('id')}",
            group="meter",
            name=str(cfg.get("name") or cfg.get("id") or "meter"),
            protocol=str(cfg.get("protocol") or "Modbus"),
            comm_mode=str(cfg.get("comm_mode") or "TCP"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for light in CONFIG.get("light_devices", []) or []:
        cfg = dict(light or {})
        entry = _base_driver(
            driver_id=f"light:{cfg.get('id')}",
            group="light",
            name=str(cfg.get("name") or cfg.get("id") or "light"),
            protocol=str(cfg.get("brand") or "light"),
            comm_mode="TCP",
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for seq in CONFIG.get("sequencers", []) or []:
        cfg = dict(seq or {})
        entry = _base_driver(
            driver_id=f"sequencer:{cfg.get('id')}",
            group="sequencer",
            name=str(cfg.get("name") or cfg.get("id") or "sequencer"),
            protocol=str(cfg.get("protocol") or "sequencer"),
            comm_mode=str(cfg.get("comm_mode") or "TCP"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for ups in CONFIG.get("ups_devices", []) or []:
        cfg = dict(ups or {})
        entry = _base_driver(
            driver_id=f"ups:{cfg.get('id')}",
            group="ups",
            name=str(cfg.get("name") or cfg.get("id") or "ups"),
            protocol=str(cfg.get("protocol") or "UPS"),
            comm_mode=str(cfg.get("comm_mode") or "TCP"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for snmp in CONFIG.get("snmp_devices", []) or []:
        cfg = dict(snmp or {})
        entry = _base_driver(
            driver_id=f"snmp:{cfg.get('id')}",
            group="snmp",
            name=str(cfg.get("name") or cfg.get("id") or "snmp"),
            protocol=str(cfg.get("protocol") or "SNMP"),
            comm_mode=str(cfg.get("version") or "v2c"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for projector in CONFIG.get("projectors", []) or []:
        cfg = dict(projector or {})
        entry = _base_driver(
            driver_id=f"projector:{cfg.get('id')}",
            group="projector",
            name=str(cfg.get("name") or cfg.get("id") or "projector"),
            protocol=str(cfg.get("control_type") or "pjlink"),
            comm_mode=str(cfg.get("control_type") or "pjlink"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for sensor in CONFIG.get("env_sensors", []) or []:
        cfg = dict(sensor or {})
        entry = _base_driver(
            driver_id=f"env:{cfg.get('id')}",
            group="env",
            name=str(cfg.get("name") or cfg.get("id") or "env"),
            protocol=str(cfg.get("source_type") or "modbus"),
            comm_mode=str(cfg.get("source_type") or "modbus"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for screen in CONFIG.get("screens", []) or []:
        cfg = dict(screen or {})
        entry = _base_driver(
            driver_id=f"screen:{cfg.get('id')}",
            group="screen",
            name=str(cfg.get("name") or cfg.get("id") or "screen"),
            protocol=str(cfg.get("control_type") or "screen_tcp"),
            comm_mode=str(cfg.get("control_type") or "screen_tcp"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    for custom in CONFIG.get("custom_devices", []) or []:
        cfg = dict(custom or {})
        entry = _base_driver(
            driver_id=f"custom:{cfg.get('id')}",
            group="custom",
            name=str(cfg.get("name") or cfg.get("id") or "custom"),
            protocol=str(cfg.get("interface") or "tcp"),
            comm_mode=str(cfg.get("interface") or "tcp"),
            cfg=cfg,
            enabled=_to_bool(cfg.get("enabled"), True),
            visible=_to_bool(cfg.get("visible"), True),
        )
        if include_disabled or (entry["enabled"] and entry["visible"]):
            drivers.append(entry)

    return drivers


def _snapshot_for_driver(driver: Dict[str, Any]) -> Dict[str, Any]:
    group = str(driver.get("group") or "")
    cfg = dict(driver.get("config_ref") or {})
    payload: Dict[str, Any] = {}
    online = False
    error = ""

    try:
        if group == "power":
            idx = _safe_int(driver.get("cabinet_index"), -1)
            payload = dict(DEVICE_STATUS.get(idx) or {})
            online = bool(payload.get("comm_status", False))
        elif group == "meter":
            meter_id = str(cfg.get("id") or "")
            payload = dict(METER_STATUS.get(meter_id) or {})
            online = bool(payload.get("online", False))
        elif group == "light":
            light_id = cfg.get("id")
            payload = {
                "online": bool(LIGHT_ONLINE.get(light_id, False)),
                "channels": deepcopy(LIGHT_STATUS.get(light_id, [])),
            }
            online = bool(payload.get("online", False))
        elif group == "sequencer":
            from api.sequencer import ensure_config_devices, snapshot

            seq_id = str(cfg.get("id") or "")
            target = next((item for item in ensure_config_devices() if str(item.get("id")) == seq_id), None)
            if target:
                payload = snapshot(target)
                online = bool(payload.get("online", False))
            else:
                error = "sequencer_not_found"
        elif group == "ups":
            ups_id = str(cfg.get("id") or "")
            payload = dict(UPS_STATUS.get(ups_id) or {})
            online = bool(payload.get("online", False))
        elif group == "snmp":
            snmp_id = str(cfg.get("id") or "")
            payload = dict(SNMP_STATUS.get(snmp_id) or {})
            online = bool(payload.get("online", False))
        elif group == "projector":
            projector_id = str(cfg.get("id") or "")
            payload = dict(PROJECTOR_STATUS.get(projector_id) or {})
            online = bool(payload.get("online", False))
        elif group == "env":
            env_id = str(cfg.get("id") or "")
            payload = dict(ENV_STATUS.get(env_id) or {})
            online = bool(payload.get("online", False))
        elif group == "screen":
            screen_id = str(cfg.get("id") or "")
            payload = dict(SCREEN_STATUS.get(screen_id) or {})
            online = bool(payload.get("online", False))
        elif group == "custom":
            interface = str(cfg.get("interface") or "tcp").strip().lower()
            ip = str(cfg.get("ip") or "").strip()
            port = _safe_int(cfg.get("port"), 0)
            if interface == "tcp" and ip and port > 0:
                sock = socket.create_connection((ip, port), timeout=1.2)
                sock.close()
                payload = {"connectivity": "ok", "interface": interface}
                online = True
            else:
                error = f"unsupported_custom_interface:{interface}"
        else:
            error = f"unsupported_group:{group}"
    except Exception as exc:
        error = str(exc)

    return {
        "driver_id": driver["driver_id"],
        "group": driver["group"],
        "name": driver["name"],
        "protocol": driver["protocol"],
        "comm_mode": driver["comm_mode"],
        "online": bool(online),
        "error": str(error or ""),
        "updated_at": _now_iso(),
        "data": payload,
    }


def collect_snapshot(
    groups: Optional[str] = None,
    driver_id: Optional[str] = None,
    include_disabled: bool = False,
) -> Dict[str, Any]:
    selected_groups = {
        item.strip().lower()
        for item in str(groups or "").split(",")
        if item.strip()
    }
    selected_driver_id = str(driver_id or "").strip()

    rows = list_drivers(include_disabled=include_disabled)
    selected: List[Dict[str, Any]] = []
    for row in rows:
        if selected_groups and str(row.get("group") or "").lower() not in selected_groups:
            continue
        if selected_driver_id and str(row.get("driver_id") or "") != selected_driver_id:
            continue
        selected.append(row)

    snapshots = [_snapshot_for_driver(row) for row in selected]
    snapshots.sort(key=lambda item: (str(item.get("group")), str(item.get("name"))))
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in snapshots:
        grouped.setdefault(str(row.get("group") or "unknown"), []).append(row)

    summary = {}
    for group, items in grouped.items():
        summary[group] = {
            "total": len(items),
            "online": sum(1 for item in items if bool(item.get("online", False))),
        }

    total = len(snapshots)
    online = sum(1 for item in snapshots if bool(item.get("online", False)))
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "total_drivers": total,
        "online_drivers": online,
        "offline_drivers": total - online,
        "summary_by_group": summary,
        "groups": grouped,
        "drivers": snapshots,
    }


def build_manifest(include_disabled: bool = True) -> Dict[str, Any]:
    rows = list_drivers(include_disabled=include_disabled)
    group_counts: Dict[str, int] = {}
    protocol_counts: Dict[str, int] = {}
    serializable = []
    for row in rows:
        group = str(row.get("group") or "unknown")
        protocol = str(row.get("protocol") or "<empty>")
        group_counts[group] = group_counts.get(group, 0) + 1
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        out = dict(row)
        out.pop("config_ref", None)
        serializable.append(out)

    serializable.sort(key=lambda item: (str(item.get("group")), str(item.get("name"))))
    return {
        "generated_at": _now_iso(),
        "total_drivers": len(serializable),
        "group_counts": group_counts,
        "protocol_counts": protocol_counts,
        "drivers": serializable,
    }


def snapshot_json(groups: Optional[str] = None, driver_id: Optional[str] = None, include_disabled: bool = False) -> str:
    return json.dumps(
        collect_snapshot(groups=groups, driver_id=driver_id, include_disabled=include_disabled),
        ensure_ascii=False,
        indent=2,
    )


def manifest_json(include_disabled: bool = True) -> str:
    return json.dumps(build_manifest(include_disabled=include_disabled), ensure_ascii=False, indent=2)
