# AI_MODULE: device_aliases
# AI_PURPOSE: Build a reusable natural-language alias index from Smart Center config for Feishu and local-model control routing.
# AI_BOUNDARY: Read-only helper; it only describes devices, channels, aliases, and suggested control metadata.
# AI_DATA_FLOW: CONFIG -> alias rows -> Feishu parser / local-model training export.
# AI_RISK: Medium, alias mistakes can route control to the wrong device; keep aliases explainable and conservative.

from __future__ import annotations

import re
from typing import Any


def normalize_alias_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    replacements = {
        "一号": "1号",
        "第一": "第1",
        "二号": "2号",
        "第二": "第2",
        "两号": "2号",
        "第三": "第3",
        "三号": "3号",
        "第四": "第4",
        "四号": "4号",
        "第五": "第5",
        "五号": "5号",
        "第六": "第6",
        "六号": "6号",
        "第七": "第7",
        "七号": "7号",
        "第八": "第8",
        "八号": "8号",
        "第九": "第9",
        "九号": "9号",
        "第十": "第10",
        "十号": "10号",
        "电源柜": "电柜",
        "配电柜": "电柜",
        "前檐墙": "前言墙",
        "前沿墙": "前言墙",
        "前颜墙": "前言墙",
        "前言灯": "前言墙灯",
        "前言照明": "前言墙照明",
        "二楼": "2楼",
        "二层": "2楼",
        "一楼": "1楼",
        "一层": "1楼",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"(前言墙)+", "前言墙", text)
    return re.sub(r"[\s\-_:：,，.。/\\()（）\[\]【】+]+", "", text)


def _add_alias(aliases: set[str], *values: Any) -> None:
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        normalized = normalize_alias_text(raw)
        if normalized:
            aliases.add(normalized)


def _iter_list(config: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = config.get(key)
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def _item_id(item: dict[str, Any], fallback: str = "") -> str:
    for key in ("id", "device_id", "entity_id", "host", "ip", "mac", "name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return fallback


def _item_name(item: dict[str, Any], fallback: str = "") -> str:
    for key in ("name", "display_name", "custom_name", "hostname", "cabinet_name", "meter_display_name", "device_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return _item_id(item, fallback)


def _network_aliases(item: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    _add_alias(
        aliases,
        item.get("id"),
        item.get("device_id"),
        item.get("entity_id"),
        item.get("host"),
        item.get("ip"),
        item.get("mac"),
        item.get("model"),
        item.get("brand"),
        item.get("protocol"),
        item.get("area_name"),
        item.get("room_name"),
        item.get("asset_group"),
    )
    return aliases


def _name_variants(name: Any) -> set[str]:
    raw = str(name or "").strip()
    aliases: set[str] = set()
    if not raw:
        return aliases
    _add_alias(aliases, raw)
    compact = normalize_alias_text(raw)
    if compact:
        _add_alias(aliases, compact.replace("电柜", ""), compact.replace("灯", ""))
    for suffix in ("电柜", "配电柜", "电箱", "电源柜", "柜", "灯", "灯光", "照明"):
        _add_alias(aliases, f"{raw}{suffix}")
    return aliases


def _channel_aliases(channel: Any, name: Any = "", remark: Any = "") -> set[str]:
    aliases: set[str] = set()
    try:
        ch = int(channel)
    except Exception:
        ch = 0
    if ch > 0:
        _add_alias(aliases, str(ch), f"{ch}路", f"第{ch}路", f"回路{ch}", f"第{ch}回路", f"{ch}回路", f"{ch}通道", f"第{ch}通道")
    aliases.update(_name_variants(name))
    aliases.update(_name_variants(remark))
    return aliases


def _row(module: str, device_type: str, row_id: str, name: str, aliases: set[str], **extra: Any) -> dict[str, Any]:
    control_capability = extra.pop("control_capability", bool(extra.get("action_hint")))
    query_capability = extra.pop("query_capability", True)
    return {
        "schema": "smart_center.device_alias.v1",
        "module": module,
        "device_type": device_type,
        "device_id": str(row_id),
        "name": str(name or row_id),
        "aliases": sorted(alias for alias in aliases if alias),
        "control_capability": bool(control_capability),
        "query_capability": bool(query_capability),
        **extra,
    }


def _generic_device_row(
    module: str,
    device_type: str,
    item: dict[str, Any],
    *,
    row_id: str = "",
    name: str = "",
    extra_aliases: tuple[Any, ...] = (),
    control_capability: bool = False,
    query_capability: bool = True,
    risk: str = "normal",
    **extra: Any,
) -> dict[str, Any]:
    item_id = row_id or _item_id(item, f"{module}:{device_type}")
    item_name = name or _item_name(item, item_id)
    aliases = set()
    aliases.update(_name_variants(item_name))
    aliases.update(_network_aliases(item))
    _add_alias(aliases, *extra_aliases)
    return _row(
        module,
        device_type,
        item_id,
        item_name,
        aliases,
        control_capability=control_capability,
        query_capability=query_capability,
        risk=risk,
        **extra,
    )


def build_device_alias_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    node_red_light_aliases = set()
    _add_alias(
        node_red_light_aliases,
        "庭院灯",
        "庭院灯RF网关",
        "户外灯",
        "室外灯",
        "室外照明",
        "院子灯",
        "院子里的灯",
        "外墙灯",
        "院灯",
        "Node-RED庭院灯",
        "121庭院灯",
    )
    rows.append(
        _row(
            "node_red",
            "gateway_light",
            "courtyard_light",
            "庭院灯RF网关",
            node_red_light_aliases,
            action_hint="on/off",
            risk="normal",
            control_capability=True,
            query_capability=True,
            query_api="/api/node-red/device/courtyard_light/status",
            control_api="/api/node-red/device/courtyard_light/control",
            gateway="121 Node-RED",
        )
    )

    for cab_idx, cab in enumerate(_iter_list(config, "cabinets")):
        if not isinstance(cab, dict):
            continue
        cab_name = str(cab.get("cabinet_name") or cab.get("meter_display_name") or cab.get("name") or f"强电柜{cab_idx + 1}")
        cab_aliases = set()
        cab_aliases.update(_name_variants(cab_name))
        _add_alias(cab_aliases, cab.get("id"), cab.get("name"), cab.get("cabinet_name"), cab.get("meter_display_name"))
        if cab_idx == 0:
            _add_alias(cab_aliases, "主电柜", "主柜", "总电柜", "中控主电柜")
        rows.append(_row("power", "cabinet", str(cab_idx), cab_name, cab_aliases, cab_idx=cab_idx, risk="high", control_capability=True))
        for ch in cab.get("channels_config") or []:
            if not isinstance(ch, dict):
                continue
            channel = ch.get("channel")
            channel_name = str(ch.get("remark") or ch.get("name") or f"第{channel}路")
            aliases = set(cab_aliases)
            aliases.update(_channel_aliases(channel, ch.get("name"), ch.get("remark")))
            for cab_alias in list(cab_aliases):
                for ch_alias in _channel_aliases(channel, ch.get("name"), ch.get("remark")):
                    _add_alias(aliases, f"{cab_alias}{ch_alias}")
            rows.append(
                _row(
                    "power",
                    "cabinet_channel",
                    f"{cab_idx}:{channel}",
                    f"{cab_name} {channel_name}",
                    aliases,
                    cab_idx=cab_idx,
                    channel=channel,
                    action_hint="on/off",
                    risk="high",
                    control_capability=True,
                )
            )

    for device in _iter_list(config, "light_devices"):
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("id") or "")
        light_name = str(device.get("name") or device_id or "灯光设备")
        light_aliases = set()
        light_aliases.update(_name_variants(light_name))
        _add_alias(light_aliases, device_id, device.get("ip"))
        rows.append(_row("light", "light_controller", device_id, light_name, light_aliases, device_id=device_id, risk="normal", control_capability=True))
        for ch in device.get("channels_config") or []:
            if not isinstance(ch, dict):
                continue
            channel = ch.get("channel")
            channel_name = str(ch.get("remark") or ch.get("name") or f"第{channel}路")
            aliases = set(light_aliases)
            aliases.update(_channel_aliases(channel, ch.get("name"), ch.get("remark")))
            aliases.update(_name_variants(channel_name))
            for suffix in ("灯", "灯光", "照明"):
                _add_alias(aliases, f"{channel_name}{suffix}", f"{light_name}{channel_name}{suffix}")
            for dev_alias in list(light_aliases):
                for ch_alias in _channel_aliases(channel, ch.get("name"), ch.get("remark")):
                    _add_alias(aliases, f"{dev_alias}{ch_alias}", f"{dev_alias}{ch_alias}灯")
            rows.append(
                _row(
                    "light",
                    "light_channel",
                    f"{device_id}:{channel}",
                    f"{light_name} {channel_name}",
                    aliases,
                    device_id=device_id,
                    channel=channel,
                    action_hint="on/off/toggle",
                    risk="normal",
                    control_capability=True,
                )
            )

    for section, module, device_type in (
        ("hvac_devices", "hvac", "hvac"),
        ("projectors", "projector", "projector"),
        ("screens", "screen", "screen"),
        ("sequencers", "sequencer", "sequencer"),
        ("custom_devices", "custom", "custom_device"),
    ):
        for item in _iter_list(config, section):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or item.get("device_id") or item.get("ip") or item.get("name") or "")
            name = str(item.get("name") or item.get("display_name") or item_id or device_type)
            aliases = set()
            aliases.update(_name_variants(name))
            _add_alias(aliases, item_id, item.get("ip"), item.get("host"), item.get("entity_id"), item.get("node_red_device_id"))
            rows.append(
                _row(
                    module,
                    device_type,
                    item_id,
                    name,
                    aliases,
                    risk="high" if module == "sequencer" else "normal",
                    control_capability=module in {"hvac", "projector", "screen", "sequencer", "custom"},
                )
            )

    for item in _iter_list(config, "meters"):
        rows.append(
            _generic_device_row(
                "meter",
                "meter",
                item,
                extra_aliases=("电表", "电表监测", item.get("meter_kind"), item.get("meter_type")),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    for item in _iter_list(config, "ups_devices"):
        rows.append(
            _generic_device_row(
                "ups",
                "ups",
                item,
                extra_aliases=("UPS", "ups", "不间断电源", "备用电源"),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    for item in _iter_list(config, "snmp_devices"):
        rows.append(
            _generic_device_row(
                "snmp",
                str(item.get("device_type") or "snmp_device"),
                item,
                extra_aliases=("SNMP", "snmp", "网络设备", "交换机" if item.get("device_type") == "switch" else "", "网关" if item.get("device_type") == "router" else "", "NAS" if item.get("device_type") == "nas" else ""),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    for item in _iter_list(config, "env_sensors"):
        features = item.get("features") if isinstance(item.get("features"), dict) else {}
        feature_aliases = tuple(key for key, enabled in features.items() if enabled)
        rows.append(
            _generic_device_row(
                "env",
                "env_sensor",
                item,
                extra_aliases=("环境", "温湿度", "传感器", item.get("primary_metric"), *feature_aliases),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    automation_rules = []
    for key in ("automation_rules", "automation"):
        value = config.get(key)
        if isinstance(value, list):
            automation_rules.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict) and isinstance(value.get("rules"), list):
            automation_rules.extend(item for item in value.get("rules") or [] if isinstance(item, dict))
    for item in automation_rules:
        rows.append(
            _generic_device_row(
                "automation",
                "automation_rule",
                item,
                extra_aliases=("自动化", "规则", "场景", "联动", item.get("description")),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    current_collector = config.get("current_collector") if isinstance(config.get("current_collector"), dict) else {}
    if current_collector:
        rows.append(
            _generic_device_row(
                "current_collector",
                "collector",
                current_collector,
                row_id=str(current_collector.get("id") or "current_collector"),
                name=str(current_collector.get("name") or "电流采集器"),
                extra_aliases=("电流采集", "16路电流", "电流监测"),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )
        for channel in current_collector.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            ch = channel.get("channel")
            ch_name = str(channel.get("name") or f"第{ch}路")
            aliases = _channel_aliases(ch, ch_name, channel.get("remark"))
            _add_alias(aliases, f"电流采集{ch_name}", f"电流{ch}路", f"{ch_name}电流")
            rows.append(
                _row(
                    "current_collector",
                    "collector_channel",
                    f"current_collector:{ch}",
                    ch_name,
                    aliases,
                    channel=ch,
                    control_capability=False,
                    query_capability=True,
                    risk="normal",
            )
        )

    door_cfg = config.get("door_config") if isinstance(config.get("door_config"), dict) else {}
    if door_cfg:
        aliases = set()
        _add_alias(
            aliases,
            "大门",
            "门禁",
            "开门",
            "关门",
            "门口大门",
            "展厅大门",
            "大门门禁",
            "门禁继电器",
            door_cfg.get("ip"),
        )
        for camera in door_cfg.get("cameras") or []:
            if not isinstance(camera, dict):
                continue
            _add_alias(aliases, camera.get("name"), camera.get("host"), camera.get("key"))
        rows.append(
            _row(
                "door",
                "door_controller",
                "door:main",
                "大门门禁",
                aliases,
                action_hint="open/close/stop",
                control_capability=True,
                query_capability=True,
                risk="normal",
            )
        )

    proxy_monitor = config.get("proxy_monitor") if isinstance(config.get("proxy_monitor"), dict) else {}
    if proxy_monitor:
        rows.append(
            _generic_device_row(
                "proxy",
                "proxy_monitor",
                proxy_monitor,
                row_id="proxy_monitor",
                name="代理监控",
                extra_aliases=("代理", "节点小宝", "异地访问", "代理监控", proxy_monitor.get("host"), proxy_monitor.get("traffic_host")),
                control_capability=False,
                query_capability=True,
                risk="normal",
            )
        )

    return rows


def find_alias_rows(query: str, rows: list[dict[str, Any]], *, module: str = "", device_type: str = "") -> list[dict[str, Any]]:
    normalized = normalize_alias_text(query)
    if not normalized:
        return []
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for row in rows:
        if module and row.get("module") != module:
            continue
        if device_type and row.get("device_type") != device_type:
            continue
        best = 0
        best_len = 0
        for alias in row.get("aliases") or []:
            alias_norm = normalize_alias_text(alias)
            if not alias_norm:
                continue
            if alias_norm == normalized:
                best = max(best, 120)
                best_len = max(best_len, len(alias_norm))
            elif alias_norm in normalized:
                # Very short aliases such as "1路" are useful only as a tie-breaker
                # after a specific device name matched; otherwise they can route a
                # cross-cabinet command to the first cabinet.
                base = 35 if len(alias_norm) < 3 else 80
                best = max(best, base + min(len(alias_norm), 30))
                best_len = max(best_len, len(alias_norm))
            elif len(alias_norm) >= 3 and normalized in alias_norm:
                best = max(best, 50 + min(len(normalized), 25))
                best_len = max(best_len, len(alias_norm))
        if best:
            matches.append((best, best_len, row))
    matches.sort(key=lambda item: (item[0], item[1], len(item[2].get("aliases") or [])), reverse=True)
    return [row for _score, _best_len, row in matches]
