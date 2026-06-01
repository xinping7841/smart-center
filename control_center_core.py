import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from xml.etree import ElementTree as ET

try:
    import serial
except Exception:  # pragma: no cover - optional on Linux deployments
    serial = None


DEFAULT_CONTROL_CENTER = {
    "enabled": True,
    "version": 1,
    "transports": [],
    "target_groups": [],
    "command_library": [],
    "devices": [],
    "panels": [
        {
            "id": "main",
            "name": "协议控制面板",
            "visible": True,
            "sort": 1,
            "controls": [],
        }
    ],
}


SUPPORTED_PROTOCOLS = {"tcp", "udp", "com", "osc", "artnet", "midi"}
SUPPORTED_FORMATS = {"str", "hex", "json", "modbus_rtu", "modbus_tcp"}
_SERIAL_LOCKS = {}
_SERIAL_LOCKS_GUARD = threading.Lock()
_TARGET_GROUP_LOCKS = {}
_TARGET_GROUP_LOCKS_GUARD = threading.Lock()
CONTROL_PACKS_DIR = Path(__file__).resolve().parent / "control_packs"


def _is_niren_target(payload):
    if not isinstance(payload, dict):
        return False
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("id", "name", "vendor", "brand", "model", "data_protocol", "protocol_variant")
    ).lower()
    return "niren" in text or "泥人" in text or "poe-kp" in text


def _normalize_niren_mode(value):
    text = str(value or "").strip().lower()
    if "at" in text:
        return "at_over_tcp"
    if "modbus_tcp" in text or text in {"tcp", "standard_tcp", "mbap"}:
        return "modbus_tcp"
    if "rtu" in text:
        return "modbus_rtu_over_tcp"
    return ""


def _apply_niren_target_compat(target):
    if not _is_niren_target(target):
        return target
    current = (
        _normalize_niren_mode(target.get("data_protocol"))
        or _normalize_niren_mode(target.get("protocol_variant"))
        or _normalize_niren_mode(target.get("protocol_mode"))
    )
    target["vendor"] = str(target.get("vendor") or "Niren").strip() or "Niren"
    target["model"] = str(target.get("model") or "POE-KP-I101").strip() or "POE-KP-I101"
    target["data_protocol"] = current or "modbus_rtu_over_tcp"
    target["send_strategy"] = "serial"
    target["wait_ms"] = _safe_int(target.get("wait_ms"), 700, 0, 60000)
    target["timeout_ms"] = _safe_int(target.get("timeout_ms"), 2000, 100, 60000)
    target["max_workers"] = 1
    return target


def _apply_niren_command_compat(command):
    if not isinstance(command, dict):
        return command
    command_id = str(command.get("id") or "").strip().lower()
    category = str(command.get("category") or "").strip().lower()
    payload = str(command.get("payload_template") or command.get("payload") or "").strip().upper()
    is_niren = command_id.startswith("niren_") or "niren" in category or "泥人" in category or payload.startswith("AT+STACH")
    if not is_niren:
        return command
    if command_id.startswith("niren_at_") or payload.startswith("AT"):
        command["format"] = "str"
        command["line_ending"] = "crlf"
    elif command_id.startswith("niren_modbus_rtu_"):
        command["format"] = "modbus_rtu"
        command["line_ending"] = "none"
    elif command_id.startswith("niren_modbus_tcp_"):
        command["format"] = "modbus_tcp"
        command["line_ending"] = "none"
    return command


NIREN_PROTOCOL_COMMAND_MAP = {
    "at_over_tcp": {
        "read_do": "niren_at_do_read",
        "read_di": "niren_at_di_read",
        "do_on": "niren_at_do_on",
        "do_off": "niren_at_do_off",
        "pulse": "niren_at_do_pulse",
        "info": "niren_at_device_info",
        "params": {"channel": 1},
        "pulse_params": {"channel": 1, "seconds": 1},
    },
    "modbus_rtu_over_tcp": {
        "read_do": "niren_modbus_rtu_read_do",
        "read_di": "niren_modbus_rtu_read_di",
        "do_on": "niren_modbus_rtu_do_on",
        "do_off": "niren_modbus_rtu_do_off",
        "pulse": "",
        "info": "",
        "params": {"unit_id": "01"},
        "pulse_params": {"unit_id": "01"},
    },
    "modbus_tcp": {
        "read_do": "niren_modbus_tcp_read_do",
        "read_di": "niren_modbus_tcp_read_di",
        "do_on": "niren_modbus_tcp_do_on",
        "do_off": "niren_modbus_tcp_do_off",
        "pulse": "",
        "info": "",
        "params": {"unit_id": "01"},
        "pulse_params": {"unit_id": "01"},
    },
}


def infer_niren_control_role(control):
    if not isinstance(control, dict):
        return ""
    control_id = str(control.get("id") or "").strip().lower()
    command_id = str(control.get("command_id") or "").strip().lower()
    name = str(control.get("name") or "").strip().lower()
    text = f"{control_id} {command_id} {name}"
    if "read_do" in text or "读do" in text or "读取 do" in text:
        return "read_do"
    if "read_di" in text or "读di" in text or "读取 di" in text:
        return "read_di"
    if "do_on" in text or "do开" in text or "吸合" in text:
        return "do_on"
    if "do_off" in text or "do关" in text or "断开" in text:
        return "do_off"
    if "pulse" in text or "点动" in text:
        return "pulse"
    if "info" in text or "device_info" in text or "信息" in text:
        return "info"
    return ""


def apply_niren_protocol_mode(control_center_config, target_group_id, mode):
    config = normalize_control_center(control_center_config)
    target_id = str(target_group_id or "").strip()
    next_mode = _normalize_niren_mode(mode)
    if next_mode not in NIREN_PROTOCOL_COMMAND_MAP:
        raise ValueError("不支持的泥人协议模式")
    target = _find_by_id(config.get("target_groups"), target_id)
    if not target:
        raise ValueError(f"找不到目标组: {target_group_id}")
    if not _is_niren_target(target):
        raise ValueError("该目标组不是泥人 POE-KP-I101 设备")

    command_map = NIREN_PROTOCOL_COMMAND_MAP[next_mode]
    target["data_protocol"] = next_mode
    target["send_strategy"] = "serial"
    target["max_workers"] = 1

    changed_controls = 0
    for panel in _safe_list(config.get("panels")):
        controls = _safe_list(panel.get("controls"))
        for control in controls:
            if str(control.get("target_group_id") or "").strip() != target_id:
                continue
            role = infer_niren_control_role(control)
            if not role:
                continue
            next_command = command_map.get(role, "")
            control["command_id"] = next_command
            control["params"] = dict(command_map.get("pulse_params" if role == "pulse" else "params") or {})
            if role == "pulse" and not next_command:
                control["visible"] = False
                control["show_on_home"] = False
            elif role == "pulse":
                control["visible"] = True
            changed_controls += 1

    for device in _safe_list(config.get("devices")):
        if str(device.get("target_group_id") or "").strip() != target_id:
            continue
        device["protocol"] = next_mode
        device["port"] = target.get("port")
        device["host"] = target.get("host")

    return {
        "control_center": normalize_control_center(config),
        "target_group_id": target_id,
        "mode": next_mode,
        "changed_controls": changed_controls,
    }


def _stable_id(prefix, *parts):
    raw = "_".join(str(part or "").strip() for part in parts if str(part or "").strip())
    ascii_part = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    if ascii_part:
        return f"{prefix}_{ascii_part[:56]}"
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _safe_list(value):
    return value if isinstance(value, list) else []


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _safe_int(value, default=0, min_value=None, max_value=None):
    try:
        result = int(value)
    except Exception:
        result = int(default)
    if min_value is not None:
        result = max(int(min_value), result)
    if max_value is not None:
        result = min(int(max_value), result)
    return result


def _safe_float(value, default=0.0, min_value=None, max_value=None):
    try:
        result = float(value)
    except Exception:
        result = float(default)
    if min_value is not None:
        result = max(float(min_value), result)
    if max_value is not None:
        result = min(float(max_value), result)
    return result


def _normalize_line_ending(value):
    text = str(value or "").strip().lower()
    if text in {"crlf", "\\r\\n"}:
        return "crlf"
    if text in {"cr", "\\r"}:
        return "cr"
    if text in {"lf", "\\n"}:
        return "lf"
    return "none"


def _line_ending_bytes(value):
    line_ending = _normalize_line_ending(value)
    if line_ending == "crlf":
        return b"\r\n"
    if line_ending == "cr":
        return b"\r"
    if line_ending == "lf":
        return b"\n"
    return b""


def _normalize_param_defs(params):
    normalized = []
    seen = set()
    for item in _safe_list(params):
        if isinstance(item, str):
            param_id = item.strip()
            label = param_id
            default = ""
            param_type = "string"
            options = []
            description = ""
            required = False
            min_value = None
            max_value = None
            step = None
        elif isinstance(item, dict):
            param_id = str(item.get("id") or item.get("name") or "").strip()
            label = str(item.get("label") or param_id).strip() or param_id
            default = item.get("default", "")
            param_type = str(item.get("type") or item.get("value_type") or "string").strip().lower() or "string"
            options = _safe_list(item.get("options"))
            description = str(item.get("description") or item.get("desc") or "").strip()
            required = bool(item.get("required", False))
            min_value = item.get("min")
            max_value = item.get("max")
            step = item.get("step")
        else:
            continue
        if not param_id or param_id in seen:
            continue
        seen.add(param_id)
        normalized.append(
            {
                "id": param_id,
                "label": label,
                "default": default,
                "type": param_type,
                "options": options,
                "description": description,
                "required": required,
                "min": min_value,
                "max": max_value,
                "step": step,
            }
        )
    return normalized


def normalize_control_center(raw_config, custom_devices=None):
    config = deepcopy(DEFAULT_CONTROL_CENTER)
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    config.update({key: deepcopy(value) for key, value in raw_config.items() if key in config})
    config["enabled"] = bool(config.get("enabled", True))
    config["version"] = _safe_int(config.get("version", 1), 1, 1)

    target_groups = []
    seen_targets = set()
    for idx, item in enumerate(_safe_list(raw_config.get("target_groups"))):
        if not isinstance(item, dict):
            continue
        target = deepcopy(item)
        target_id = str(target.get("id") or _stable_id("target", target.get("name"), target.get("host"), idx)).strip()
        if not target_id or target_id in seen_targets:
            target_id = _stable_id("target", target_id, idx)
        seen_targets.add(target_id)
        protocol = str(target.get("protocol") or target.get("interface") or "tcp").strip().lower()
        if protocol not in SUPPORTED_PROTOCOLS:
            protocol = "tcp"
        mode = str(target.get("mode") or target.get("target_mode") or "single").strip().lower()
        if mode not in {"single", "ip_list", "ip_range", "device_group"}:
            mode = "single"
        target.update(
            {
                "id": target_id,
                "name": str(target.get("name") or target_id).strip() or target_id,
                "protocol": protocol,
                "mode": mode,
                "host": str(target.get("host") or target.get("ip") or "").strip(),
                "hosts": _safe_list(target.get("hosts")),
                "range_start": str(target.get("range_start") or "").strip(),
                "range_end": str(target.get("range_end") or "").strip(),
                "port": _safe_int(target.get("port"), 50001 if protocol == "tcp" else (6454 if protocol == "artnet" else 0), 0, 65535),
                "com_port": str(target.get("com_port") or target.get("serial_port") or "COM1").strip() or "COM1",
                "baudrate": _safe_int(target.get("baudrate"), 9600, 300, 10000000),
                "timeout_ms": _safe_int(target.get("timeout_ms"), 2000, 100, 60000),
                "wait_ms": _safe_int(target.get("wait_ms"), 0, 0, 60000),
                "send_strategy": str(target.get("send_strategy") or "parallel").strip().lower(),
                "max_workers": _safe_int(target.get("max_workers"), 8, 1, 64),
                "artnet_universe": _safe_int(target.get("artnet_universe"), 0, 0, 32767),
                "enabled": bool(target.get("enabled", True)),
            }
        )
        if target["send_strategy"] not in {"parallel", "serial"}:
            target["send_strategy"] = "parallel"
        target = _apply_niren_target_compat(target)
        target_groups.append(target)
    config["target_groups"] = target_groups

    commands = []
    seen_commands = set()
    for idx, item in enumerate(_safe_list(raw_config.get("command_library"))):
        if not isinstance(item, dict):
            continue
        command = deepcopy(item)
        command_id = str(command.get("id") or _stable_id("cmd", command.get("name"), command.get("payload_template"), idx)).strip()
        if not command_id or command_id in seen_commands:
            command_id = _stable_id("cmd", command_id, idx)
        seen_commands.add(command_id)
        fmt = str(command.get("format") or command.get("payload_format") or "str").strip().lower()
        if fmt not in SUPPORTED_FORMATS:
            fmt = "str"
        protocol = str(command.get("protocol") or "").strip().lower()
        if protocol and protocol not in SUPPORTED_PROTOCOLS:
            protocol = ""
        command.update(
            {
                "id": command_id,
                "name": str(command.get("name") or command_id).strip() or command_id,
                "category": str(command.get("category") or "").strip(),
                "protocol": protocol,
                "payload_template": str(command.get("payload_template") if command.get("payload_template") is not None else command.get("payload", "") or ""),
                "format": fmt,
                "line_ending": _normalize_line_ending(command.get("line_ending")),
                "wait_ms": _safe_int(command.get("wait_ms"), 0, 0, 60000),
                "params": _normalize_param_defs(command.get("params")),
                "enabled": bool(command.get("enabled", True)),
            }
        )
        command = _apply_niren_command_compat(command)
        commands.append(command)
    config["command_library"] = commands

    config["devices"] = [
        deepcopy(item)
        for item in _safe_list(raw_config.get("devices"))
        if isinstance(item, dict)
    ]

    panels = []
    seen_panels = set()
    for idx, item in enumerate(_safe_list(raw_config.get("panels"))):
        if not isinstance(item, dict):
            continue
        panel = deepcopy(item)
        panel_id = str(panel.get("id") or _stable_id("panel", panel.get("name"), idx)).strip()
        if not panel_id or panel_id in seen_panels:
            panel_id = _stable_id("panel", panel_id, idx)
        seen_panels.add(panel_id)
        controls = []
        seen_controls = set()
        for c_idx, raw_control in enumerate(_safe_list(panel.get("controls"))):
            if not isinstance(raw_control, dict):
                continue
            control = deepcopy(raw_control)
            control_id = str(control.get("id") or _stable_id("control", panel_id, control.get("name"), c_idx)).strip()
            if not control_id or control_id in seen_controls:
                control_id = _stable_id("control", panel_id, control_id, c_idx)
            seen_controls.add(control_id)
            c_type = str(control.get("type") or "button").strip().lower()
            if c_type not in {"button", "toggle", "momentary", "slider", "fader", "knob", "indicator", "value", "button_group"}:
                c_type = "button"
            control.update(
                {
                    "id": control_id,
                    "name": str(control.get("name") or control_id).strip() or control_id,
                    "type": c_type,
                    "command_id": str(control.get("command_id") or "").strip(),
                    "target_group_id": str(control.get("target_group_id") or control.get("target_id") or "").strip(),
                    "show_on_home": bool(control.get("show_on_home", True)),
                    "visible": bool(control.get("visible", True)),
                    "sort": _safe_int(control.get("sort"), c_idx + 1, 0),
                    "feedback_mode": str(control.get("feedback_mode") or "none").strip().lower(),
                    "params": _safe_dict(control.get("params")),
                    "min": _safe_float(control.get("min"), 0),
                    "max": _safe_float(control.get("max"), 100),
                    "step": _safe_float(control.get("step"), 1, 0.0001),
                    "value_param": str(control.get("value_param") or "value").strip() or "value",
                    "value": control.get("value", 0),
                }
            )
            controls.append(control)
        panel.update(
            {
                "id": panel_id,
                "name": str(panel.get("name") or panel_id).strip() or panel_id,
                "visible": bool(panel.get("visible", True)),
                "sort": _safe_int(panel.get("sort"), idx + 1, 0),
                "controls": sorted(controls, key=lambda row: (row.get("sort", 0), row.get("name", ""))),
            }
        )
        panels.append(panel)
    if not panels:
        panels = deepcopy(DEFAULT_CONTROL_CENTER["panels"])
    config["panels"] = sorted(panels, key=lambda row: (row.get("sort", 0), row.get("name", "")))
    return config


def _dedupe_id(base_id, existing_ids, prefix):
    base_id = str(base_id or "").strip()
    if not base_id:
        base_id = _stable_id(prefix, time.time())
    if base_id not in existing_ids:
        return base_id
    for idx in range(2, 10000):
        candidate = f"{base_id}_{idx}"
        if candidate not in existing_ids:
            return candidate
    return _stable_id(prefix, base_id, len(existing_ids), time.time())


def _normalize_command_pack(raw_pack, source=""):
    if not isinstance(raw_pack, dict):
        raise ValueError("指令包必须是 JSON 对象")
    meta = raw_pack.get("meta") if isinstance(raw_pack.get("meta"), dict) else {}
    pack_id = str(meta.get("id") or raw_pack.get("id") or _stable_id("pack", meta.get("name"), source)).strip()
    if not pack_id:
        pack_id = _stable_id("pack", source or "custom")
    pack_name = str(meta.get("name") or raw_pack.get("name") or pack_id).strip() or pack_id
    normalized = {
        "meta": {
            "id": pack_id,
            "name": pack_name,
            "vendor": str(meta.get("vendor") or raw_pack.get("vendor") or "").strip(),
            "description": str(meta.get("description") or raw_pack.get("description") or "").strip(),
            "version": str(meta.get("version") or raw_pack.get("version") or "1.0").strip(),
            "tags": _safe_list(meta.get("tags") or raw_pack.get("tags")),
            "source": str(source or meta.get("source") or "").strip(),
        },
        "target_groups": deepcopy(_safe_list(raw_pack.get("target_groups") or raw_pack.get("targets"))),
        "commands": deepcopy(_safe_list(raw_pack.get("commands") or raw_pack.get("command_library"))),
        "panels": deepcopy(_safe_list(raw_pack.get("panels"))),
        "generator": deepcopy(_safe_dict(raw_pack.get("generator"))),
    }
    generated_config = normalize_control_center(
        {
            "target_groups": normalized["target_groups"],
            "command_library": normalized["commands"],
            "panels": normalized["panels"] or deepcopy(DEFAULT_CONTROL_CENTER["panels"]),
        }
    )
    normalized["target_groups"] = generated_config.get("target_groups", [])
    normalized["commands"] = generated_config.get("command_library", [])
    normalized["panels"] = [] if not raw_pack.get("panels") else generated_config.get("panels", [])
    return normalized


def load_command_pack(path_or_payload):
    if isinstance(path_or_payload, dict):
        return _normalize_command_pack(path_or_payload)
    path = Path(str(path_or_payload or "")).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"找不到指令包: {path}")
    raw_pack = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_command_pack(raw_pack, source=str(path))


def list_builtin_command_packs():
    packs = []
    if not CONTROL_PACKS_DIR.exists():
        return packs
    for path in sorted(CONTROL_PACKS_DIR.glob("*.json")):
        try:
            pack = load_command_pack(path)
            meta = deepcopy(pack.get("meta", {}))
            meta.update(
                {
                    "path": str(path),
                    "target_count": len(pack.get("target_groups", [])),
                    "command_count": len(pack.get("commands", [])),
                    "panel_count": len(pack.get("panels", [])),
                    "generator": pack.get("generator", {}),
                }
            )
            packs.append(meta)
        except Exception as exc:
            packs.append(
                {
                    "id": path.stem,
                    "name": path.stem,
                    "path": str(path),
                    "error": str(exc),
                    "target_count": 0,
                    "command_count": 0,
                    "panel_count": 0,
                }
            )
    return packs


def load_builtin_command_pack(pack_id):
    pack_id = str(pack_id or "").strip()
    if not pack_id:
        raise ValueError("缺少内置指令包 ID")
    for path in sorted(CONTROL_PACKS_DIR.glob("*.json")):
        try:
            pack = load_command_pack(path)
        except Exception:
            continue
        if str(pack.get("meta", {}).get("id") or path.stem) == pack_id or path.stem == pack_id:
            return pack
    raise FileNotFoundError(f"找不到内置指令包: {pack_id}")


def apply_command_pack(control_center_config, command_pack, overwrite=False, include_panels=True):
    config = normalize_control_center(control_center_config)
    pack = _normalize_command_pack(command_pack)
    imported = {"targets": 0, "commands": 0, "panels": 0}

    targets = list(config.get("target_groups", []))
    target_map = {str(item.get("id") or "").strip(): item for item in targets if isinstance(item, dict)}
    for raw_target in pack.get("target_groups", []):
        target = deepcopy(raw_target)
        target_id = str(target.get("id") or "").strip()
        if not target_id:
            target_id = _stable_id("target", target.get("name"), len(target_map))
        if target_id in target_map and not overwrite:
            continue
        target["id"] = target_id
        target_map[target_id] = target
        imported["targets"] += 1
    config["target_groups"] = list(target_map.values())

    commands = list(config.get("command_library", []))
    command_map = {str(item.get("id") or "").strip(): item for item in commands if isinstance(item, dict)}
    for raw_command in pack.get("commands", []):
        command = deepcopy(raw_command)
        command_id = str(command.get("id") or "").strip()
        if not command_id:
            command_id = _stable_id("cmd", command.get("name"), command.get("payload_template"), len(command_map))
        if command_id in command_map and not overwrite:
            continue
        command["id"] = command_id
        command_map[command_id] = command
        imported["commands"] += 1
    config["command_library"] = sorted(command_map.values(), key=lambda row: (str(row.get("category") or ""), str(row.get("name") or "")))

    if include_panels:
        panels = list(config.get("panels", []))
        panel_map = {str(item.get("id") or "").strip(): item for item in panels if isinstance(item, dict)}
        for raw_panel in pack.get("panels", []):
            panel = deepcopy(raw_panel)
            panel_id = str(panel.get("id") or "").strip()
            if not panel_id:
                panel_id = _stable_id("panel", panel.get("name"), len(panel_map))
            if panel_id in panel_map and not overwrite:
                panel_id = _dedupe_id(panel_id, set(panel_map), "panel")
                panel["id"] = panel_id
            panel["id"] = panel_id
            panel_map[panel_id] = panel
            imported["panels"] += 1
        config["panels"] = list(panel_map.values())

    normalized = normalize_control_center(config)
    return {
        "control_center": normalized,
        "imported": imported,
        "pack": pack.get("meta", {}),
    }


def generate_panel_from_commands(control_center_config, category="", target_group_id="", panel_name="", show_on_home=False, command_ids=None):
    config = normalize_control_center(control_center_config)
    category = str(category or "").strip()
    commands = [
        command for command in config.get("command_library", [])
        if isinstance(command, dict) and command.get("enabled", True)
    ]
    wanted_ids = {str(item).strip() for item in _safe_list(command_ids) if str(item).strip()}
    if wanted_ids:
        commands = [command for command in commands if str(command.get("id") or "").strip() in wanted_ids]
    elif category:
        commands = [command for command in commands if str(command.get("category") or "").strip() == str(category).strip()]
    if not commands:
        raise ValueError("没有可生成控件的指令")

    target_group_id = str(target_group_id or "").strip()
    if not target_group_id:
        targets = config.get("target_groups", [])
        if targets:
            target_group_id = str(targets[0].get("id") or "").strip()
    if not target_group_id:
        raise ValueError("请先配置至少一个目标组")

    panel_name = str(panel_name or category or "协议控制面板").strip() or "协议控制面板"
    panel_ids = {str(panel.get("id") or "").strip() for panel in config.get("panels", [])}
    panel_id = _dedupe_id(_stable_id("panel", panel_name), panel_ids, "panel")
    controls = []
    for idx, command in enumerate(commands, 1):
        params = _normalize_param_defs(command.get("params"))
        control_type = "button"
        min_value = 0
        max_value = 100
        step = 1
        value = 0
        value_param = "value"
        if params:
            first_param = params[0]
            value_param = first_param.get("id") or "value"
            param_type = str(first_param.get("type") or "string").lower()
            if param_type in {"int", "float", "number", "range"}:
                control_type = "slider"
                min_value = _safe_float(first_param.get("min"), 0)
                max_value = _safe_float(first_param.get("max"), 100)
                step = _safe_float(first_param.get("step"), 1, 0.0001)
                value = first_param.get("default", min_value)
        controls.append(
            {
                "id": _stable_id("control", panel_id, command.get("id"), idx),
                "name": command.get("name") or command.get("id"),
                "type": control_type,
                "command_id": command.get("id"),
                "target_group_id": target_group_id,
                "show_on_home": bool(show_on_home),
                "visible": True,
                "sort": idx,
                "feedback_mode": "optimistic" if control_type in {"toggle", "slider"} else "none",
                "params": {},
                "min": min_value,
                "max": max_value,
                "step": step,
                "value_param": value_param,
                "value": value,
            }
        )
    config["panels"].append(
        {
            "id": panel_id,
            "name": panel_name,
            "visible": True,
            "sort": len(config.get("panels", [])) + 1,
            "controls": controls,
        }
    )
    return {
        "control_center": normalize_control_center(config),
        "panel_id": panel_id,
        "panel_name": panel_name,
        "control_count": len(controls),
    }


def _find_by_id(items, item_id):
    item_id = str(item_id or "").strip()
    for item in _safe_list(items):
        if isinstance(item, dict) and str(item.get("id") or "").strip() == item_id:
            return item
    return None


def find_control(config, control_id):
    for panel in _safe_list(config.get("panels")):
        control = _find_by_id(panel.get("controls"), control_id)
        if control:
            return panel, control
    return None, None


def _normalize_params(command, control=None, runtime_params=None, value=None):
    params = {}
    for param in _normalize_param_defs(command.get("params")):
        params[param["id"]] = param.get("default", "")
    if isinstance(control, dict):
        params.update(_safe_dict(control.get("params")))
        if value is not None:
            value_param = str(control.get("value_param") or "value").strip() or "value"
            params[value_param] = value
            params.setdefault("value", value)
            params.setdefault("值", value)
    params.update(_safe_dict(runtime_params))
    return params


def render_command_payload(command, params=None):
    params = params if isinstance(params, dict) else {}
    text = str(command.get("payload_template") if command.get("payload_template") is not None else command.get("payload", "") or "")
    for key, value in params.items():
        value_text = str(value)
        for pattern in (f"{{{{{key}}}}}", f"${{{key}}}"):
            text = text.replace(pattern, value_text)
    return text


def payload_to_bytes(command, payload_text):
    fmt = str(command.get("format") or "str").strip().lower()
    if fmt == "json":
        if isinstance(payload_text, (dict, list)):
            text = json.dumps(payload_text, ensure_ascii=False)
        else:
            text = str(payload_text or "")
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                pass
        return text.encode("utf-8") + _line_ending_bytes(command.get("line_ending"))
    if fmt == "hex":
        cleaned = re.sub(r"[^0-9a-fA-F]", "", str(payload_text or ""))
        if len(cleaned) % 2:
            raise ValueError("Hex 指令长度必须是偶数")
        return bytes.fromhex(cleaned)
    if fmt == "modbus_rtu":
        cleaned = re.sub(r"[^0-9a-fA-F]", "", str(payload_text or ""))
        if len(cleaned) % 2:
            raise ValueError("Modbus RTU payload length must be even")
        frame = bytes.fromhex(cleaned)
        return frame + _modbus_crc16(frame)
    if fmt == "modbus_tcp":
        cleaned = re.sub(r"[^0-9a-fA-F]", "", str(payload_text or ""))
        if len(cleaned) % 2:
            raise ValueError("Modbus TCP payload length must be even")
        pdu = bytes.fromhex(cleaned)
        tx_id = int(time.time() * 1000) & 0xFFFF
        return tx_id.to_bytes(2, "big") + b"\x00\x00" + len(pdu).to_bytes(2, "big") + pdu
    text = str(payload_text or "")
    text = (
        text.replace("\\r\\n", "\r\n")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
    )
    return text.encode("utf-8") + _line_ending_bytes(command.get("line_ending"))


def _modbus_crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, "little")


def _parse_host_range(host_text):
    text = str(host_text or "").strip()
    if "-" not in text:
        return []
    start_text, end_text = [part.strip() for part in text.split("-", 1)]
    try:
        start_ip = ipaddress.ip_address(start_text)
    except Exception:
        return []
    if "." in end_text:
        try:
            end_ip = ipaddress.ip_address(end_text)
        except Exception:
            return []
    else:
        try:
            last = int(end_text)
            start_parts = start_text.split(".")
            end_ip = ipaddress.ip_address(".".join(start_parts[:3] + [str(last)]))
        except Exception:
            return []
    if start_ip.version != 4 or end_ip.version != 4 or int(end_ip) < int(start_ip):
        return []
    count = int(end_ip) - int(start_ip) + 1
    if count > 512:
        raise ValueError("IP 批量范围过大，单个目标组最多 512 个地址")
    return [str(ipaddress.ip_address(int(start_ip) + idx)) for idx in range(count)]


def expand_target_group(target):
    target = target if isinstance(target, dict) else {}
    mode = str(target.get("mode") or "single").strip().lower()
    hosts = []
    if mode == "ip_range":
        start = str(target.get("range_start") or "").strip()
        end = str(target.get("range_end") or "").strip()
        hosts = _parse_host_range(f"{start}-{end}") if start and end else _parse_host_range(target.get("host"))
    elif mode in {"ip_list", "device_group"}:
        for item in _safe_list(target.get("hosts")):
            if isinstance(item, dict):
                host = str(item.get("host") or item.get("ip") or "").strip()
            else:
                host = str(item or "").strip()
            if host:
                if "-" in host:
                    hosts.extend(_parse_host_range(host))
                else:
                    hosts.append(host)
    else:
        host = str(target.get("host") or target.get("ip") or "").strip()
        hosts = _parse_host_range(host) if "-" in host else ([host] if host else [])
    return [host for idx, host in enumerate(hosts) if host and host not in hosts[:idx]]


def _bytes_preview(value):
    if isinstance(value, bytes):
        if not value:
            return ""
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return value.hex(" ")
    return str(value or "")


def _bytes_hex(value):
    if isinstance(value, bytes):
        return value.hex(" ")
    return ""


def _send_tcp(host, target, payload, wait_ms):
    port = _safe_int(target.get("port"), 50001, 1, 65535)
    timeout = _safe_int(target.get("timeout_ms"), 2000, 100, 60000) / 1000.0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(payload)
        if wait_ms > 0:
            sock.settimeout(max(0.1, wait_ms / 1000.0))
            try:
                return sock.recv(4096)
            except socket.timeout:
                return b""
    return b"TCP Sent"


def _send_udp(host, target, payload, wait_ms):
    port = _safe_int(target.get("port"), 50001, 1, 65535)
    timeout = _safe_int(target.get("timeout_ms"), 2000, 100, 60000) / 1000.0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (host, port))
        if wait_ms > 0:
            sock.settimeout(max(0.1, wait_ms / 1000.0))
            try:
                return sock.recvfrom(4096)[0]
            except socket.timeout:
                return b""
    return b"UDP Sent"


def _get_serial_lock(com_port):
    key = str(com_port or "").strip().upper()
    with _SERIAL_LOCKS_GUARD:
        if key not in _SERIAL_LOCKS:
            _SERIAL_LOCKS[key] = threading.Lock()
        return _SERIAL_LOCKS[key]


def _get_target_group_lock(target_group_id):
    key = str(target_group_id or "").strip() or "__default__"
    with _TARGET_GROUP_LOCKS_GUARD:
        if key not in _TARGET_GROUP_LOCKS:
            _TARGET_GROUP_LOCKS[key] = threading.Lock()
        return _TARGET_GROUP_LOCKS[key]


def _send_com(target, payload, wait_ms):
    if serial is None:
        raise RuntimeError("当前 Python 环境未安装 pyserial，无法发送串口指令")
    com_port = str(target.get("com_port") or "COM1").strip() or "COM1"
    baudrate = _safe_int(target.get("baudrate"), 9600, 300, 10000000)
    timeout = _safe_int(target.get("timeout_ms"), 2000, 100, 60000) / 1000.0
    with _get_serial_lock(com_port):
        with serial.Serial(com_port, baudrate, timeout=timeout) as ser:
            ser.reset_input_buffer()
            ser.write(payload)
            ser.flush()
            if wait_ms > 0:
                time.sleep(wait_ms / 1000.0)
                return ser.read_all()
    return b"COM Sent"


def _osc_pad(raw):
    raw = raw + b"\0"
    padding = (4 - (len(raw) % 4)) % 4
    return raw + (b"\0" * padding)


def _coerce_osc_arg(value):
    if isinstance(value, bool):
        return "i", 1 if value else 0, struct.pack(">i", 1 if value else 0)
    try:
        if str(value).strip().isdigit() or re.fullmatch(r"[-+]?\d+", str(value).strip()):
            number = int(str(value).strip())
            return "i", number, struct.pack(">i", number)
    except Exception:
        pass
    try:
        number = float(str(value).strip())
        if str(value).strip() and re.search(r"[.eE]", str(value).strip()):
            return "f", number, struct.pack(">f", number)
    except Exception:
        pass
    text = str(value)
    return "s", text, _osc_pad(text.encode("utf-8"))


def _build_osc_payload(command, payload_text, params):
    address = str(command.get("osc_address") or "").strip()
    args = []
    if not address:
        parts = str(payload_text or "").strip().split()
        if parts and parts[0].startswith("/"):
            address = parts[0]
            args = parts[1:]
    configured_args = command.get("osc_args")
    if isinstance(configured_args, list):
        args = []
        for item in configured_args:
            if isinstance(item, str):
                args.append(render_command_payload({"payload_template": item, "format": "str"}, params))
            elif isinstance(item, dict):
                param_id = str(item.get("param") or item.get("id") or "").strip()
                args.append(params.get(param_id, item.get("value", "")))
    if not address:
        raise ValueError("OSC 指令缺少地址，例如 /cue/1/start")
    tags = ","
    body = b""
    for arg in args:
        tag, _coerced, raw = _coerce_osc_arg(arg)
        tags += tag
        body += raw
    return _osc_pad(address.encode("utf-8")) + _osc_pad(tags.encode("ascii")) + body


def _send_osc(host, target, command, payload_text, params, wait_ms):
    payload = _build_osc_payload(command, payload_text, params)
    osc_target = deepcopy(target)
    osc_target["port"] = _safe_int(target.get("port"), 8000, 1, 65535)
    return _send_udp(host, osc_target, payload, wait_ms)


def _build_artnet_payload(target, payload):
    if payload.startswith(b"Art-Net\0"):
        return payload
    dmx = bytes(payload[:512])
    if len(dmx) % 2:
        dmx += b"\0"
    universe = _safe_int(target.get("artnet_universe"), 0, 0, 32767)
    return (
        b"Art-Net\0"
        + struct.pack("<H", 0x5000)
        + struct.pack(">H", 14)
        + b"\0\0"
        + struct.pack("<H", universe)
        + struct.pack(">H", len(dmx))
        + dmx
    )


def _send_artnet(host, target, payload, wait_ms):
    art_target = deepcopy(target)
    art_target["port"] = _safe_int(target.get("port"), 6454, 1, 65535)
    return _send_udp(host, art_target, _build_artnet_payload(target, payload), wait_ms)


def _send_midi(_target, _payload, _wait_ms):
    raise RuntimeError("当前运行环境未安装 MIDI 发送依赖。需要接 MIDI 时，请安装 mido + python-rtmidi 后再启用。")


def _send_one_target(host, target, command, payload, payload_text, params, wait_ms):
    protocol = str(target.get("protocol") or command.get("protocol") or "tcp").strip().lower()
    if protocol == "tcp":
        response = _send_tcp(host, target, payload, wait_ms)
    elif protocol == "udp":
        response = _send_udp(host, target, payload, wait_ms)
    elif protocol == "com":
        response = _send_com(target, payload, wait_ms)
    elif protocol == "osc":
        response = _send_osc(host, target, command, payload_text, params, wait_ms)
    elif protocol == "artnet":
        response = _send_artnet(host, target, payload, wait_ms)
    elif protocol == "midi":
        response = _send_midi(target, payload, wait_ms)
    else:
        raise RuntimeError(f"不支持的协议类型: {protocol}")
    response_text = _bytes_preview(response)
    response_hex = _bytes_hex(response)
    if _command_expects_response(command) and not response_text.strip() and not response_hex.strip():
        return {
            "host": host or target.get("com_port") or protocol,
            "ok": 0,
            "error": "设备未在等待时间内返回数据",
            "response": response_text,
            "response_hex": response_hex,
        }
    return {
        "host": host or target.get("com_port") or protocol,
        "ok": 1,
        "response": response_text,
        "response_hex": response_hex,
    }


def _command_expects_response(command):
    explicit = command.get("expect_response")
    if explicit is not None:
        return bool(explicit)
    command_id = str(command.get("id") or "").strip().lower()
    command_name = str(command.get("name") or "").strip().lower()
    text = f"{command_id} {command_name}"
    # Only read/query/info commands require payload bytes back. Control commands
    # keep the legacy "sent successfully" semantics because many relay modules do
    # not acknowledge every write command consistently.
    return any(token in text for token in ("read", "query", "status", "info", "读取", "读", "查询", "状态", "信息"))


def execute_control_center_command(config, command_id, target_group_id, params=None, value=None, control=None):
    config = normalize_control_center(config)
    if not config.get("enabled", True):
        return {"ok": 0, "success": False, "msg": "协议控制中心已停用", "results": []}
    command = _find_by_id(config.get("command_library"), command_id)
    if not command:
        return {"ok": 0, "success": False, "msg": f"找不到指令: {command_id}", "results": []}
    if command.get("enabled", True) is False:
        return {"ok": 0, "success": False, "msg": f"指令已停用: {command.get('name')}", "results": []}
    target = _find_by_id(config.get("target_groups"), target_group_id)
    if not target:
        return {"ok": 0, "success": False, "msg": f"找不到目标组: {target_group_id}", "results": []}
    if target.get("enabled", True) is False:
        return {"ok": 0, "success": False, "msg": f"目标组已停用: {target.get('name')}", "results": []}

    merged_params = _normalize_params(command, control=control, runtime_params=params, value=value)
    payload_text = render_command_payload(command, merged_params)
    payload = payload_to_bytes(command, payload_text)
    wait_ms = _safe_int(command.get("wait_ms", target.get("wait_ms", 0)), target.get("wait_ms", 0), 0, 60000)
    hosts = expand_target_group(target)
    if str(target.get("protocol") or "").lower() == "com":
        hosts = [str(target.get("com_port") or "COM")]
    if not hosts:
        return {"ok": 0, "success": False, "msg": "目标组没有可用地址或串口", "results": []}

    results = []
    # POE-KP-I101 and similar small TCP/RTU bridges often drop one of two
    # concurrent reads. Serialize per target group across Flask requests while
    # still allowing parallel sends inside a multi-host target group.
    with _get_target_group_lock(target.get("id")):
        if str(target.get("send_strategy") or "parallel").lower() == "serial" or len(hosts) == 1:
            for host in hosts:
                try:
                    results.append(_send_one_target(host, target, command, payload, payload_text, merged_params, wait_ms))
                except Exception as exc:
                    results.append({"host": host, "ok": 0, "error": str(exc)})
        else:
            max_workers = min(_safe_int(target.get("max_workers"), 8, 1, 64), len(hosts))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_map = {
                    pool.submit(_send_one_target, host, target, command, payload, payload_text, merged_params, wait_ms): host
                    for host in hosts
                }
                for future in as_completed(future_map):
                    host = future_map[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append({"host": host, "ok": 0, "error": str(exc)})
    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": 1 if ok_count else 0,
        "success": bool(ok_count),
        "msg": f"已发送 {ok_count}/{len(results)} 个目标",
        "command_id": command.get("id"),
        "command_name": command.get("name"),
        "target_group_id": target.get("id"),
        "target_group_name": target.get("name"),
        "params": merged_params,
        "payload_preview": payload_text,
        "results": results,
    }


def execute_control(config, control_id, params=None, value=None):
    config = normalize_control_center(config)
    panel, control = find_control(config, control_id)
    if not control:
        return {"ok": 0, "success": False, "msg": f"找不到控件: {control_id}", "results": []}
    return execute_control_center_command(
        config,
        control.get("command_id"),
        control.get("target_group_id"),
        params=params,
        value=value,
        control=control,
    )


def _xlsx_shared_strings(zip_file):
    try:
        raw = zip_file.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    strings = []
    for si in root.findall(".//{*}si"):
        chunks = []
        for node in si.iter():
            if node.tag.endswith("}t") or node.tag == "t":
                chunks.append(node.text or "")
        strings.append("".join(chunks))
    return strings


def _xlsx_cell_value(cell, shared_strings):
    value_type = cell.attrib.get("t")
    if value_type == "inlineStr":
        chunks = []
        for node in cell.iter():
            if node.tag.endswith("}t") or node.tag == "t":
                chunks.append(node.text or "")
        return "".join(chunks)
    value = cell.find("{*}v")
    if value is None:
        return ""
    text = value.text or ""
    if value_type == "s":
        try:
            return shared_strings[int(text)]
        except Exception:
            return ""
    return text


def _xlsx_rows(path):
    with zipfile.ZipFile(path) as zf:
        shared_strings = _xlsx_shared_strings(zf)
        sheet_names = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        if not sheet_names:
            return []
        rows = []
        for sheet_name in sorted(sheet_names):
            root = ET.fromstring(zf.read(sheet_name))
            for row in root.findall(".//{*}row"):
                values = []
                for cell in row.findall("{*}c"):
                    values.append(str(_xlsx_cell_value(cell, shared_strings)).strip())
                if any(values):
                    rows.append(values)
        return rows


_HIRENDER_PARAM_TOKENS = [
    "节目页名",
    "节目名",
    "时间线名",
    "显示屏名",
    "连接名",
    "场景名",
    "图层名",
    "素材名",
    "文件名",
    "文件路径",
    "路径",
    "秒数",
    "毫秒",
    "数值",
    "参数",
    "编号",
    "名称",
    "ID",
    "id",
    "值",
]


def _template_hirender_payload(text):
    payload = str(text or "")
    params = []
    for token in sorted(_HIRENDER_PARAM_TOKENS, key=len, reverse=True):
        if token in payload:
            payload = payload.replace(token, f"{{{{{token}}}}}")
            if token not in params:
                params.append(token)
    return payload, [{"id": token, "label": token, "default": ""} for token in params]


def import_hirender_xlsx(path):
    path = os.path.abspath(str(path or ""))
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到 Hirender 指令表: {path}")
    rows = _xlsx_rows(path)
    default_port = 50001
    header_idx = -1
    name_col = 0
    command_col = 1
    note_col = 2
    for idx, row in enumerate(rows):
        joined = " ".join(row)
        match = re.search(r"端口号?\s*[:：]\s*(\d+)", joined)
        if match:
            default_port = _safe_int(match.group(1), 50001, 1, 65535)
        if "指令名" in row and "网络指令" in row:
            header_idx = idx
            name_col = row.index("指令名")
            command_col = row.index("网络指令")
            note_col = row.index("备注") if "备注" in row else 2
            break
    if header_idx < 0:
        raise ValueError("Hirender 指令表中没有找到“指令名 / 网络指令”表头")

    commands = []
    category = "Hirender"
    seen = set()
    for row in rows[header_idx + 1 :]:
        name = row[name_col] if len(row) > name_col else ""
        payload = row[command_col] if len(row) > command_col else ""
        note = row[note_col] if len(row) > note_col else ""
        if name and not payload:
            category = name
            continue
        if not name or not payload:
            continue
        payload_template, params = _template_hirender_payload(payload)
        command_id = _stable_id("hirender", category, name, payload)
        if command_id in seen:
            command_id = _stable_id("hirender", category, name, payload, len(commands))
        seen.add(command_id)
        commands.append(
            {
                "id": command_id,
                "name": name,
                "category": category,
                "vendor": "Hirender",
                "protocol": "tcp",
                "format": "str",
                "line_ending": "none",
                "payload_template": payload_template,
                "params": params,
                "note": note,
                "wait_ms": 0,
                "enabled": True,
            }
        )
    return {
        "source": path,
        "default_port": default_port,
        "commands": commands,
        "count": len(commands),
        "target_group_template": {
            "id": "hirender_s3_main",
            "name": "Hirender S3 主机",
            "protocol": "tcp",
            "mode": "single",
            "host": "",
            "port": default_port,
            "timeout_ms": 2000,
            "wait_ms": 0,
            "enabled": True,
        },
    }
