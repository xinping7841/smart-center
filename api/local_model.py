# AI_MODULE: local_model_api
# AI_PURPOSE: 本地 AI 控制台、OpenAI-compatible 调用、训练/学习数据导出和脱敏知识包生成。
# AI_BOUNDARY: 不直接执行设备控制；模型只能辅助分析，真实动作必须走原有 API 权限和人工确认。
# AI_DATA_FLOW: CONFIG/事件日志/设备清单 -> training/local_model JSONL/JSON -> 本地模型/RAG。
# AI_RUNTIME: /local-model 页面和 /api/local-model/* 调用；导出脚本 scripts/export_local_model_training.py 复用这里的构建函数。
# AI_RISK: 中，导出数据必须脱敏，不能把账号、token、SNMP community、密码喂给模型。
# AI_COMPAT: smart_center.training.v1 schema、/api/local-model/export-training、training-files 需保持兼容。
# AI_SEARCH_KEYWORDS: local model, training export, jsonl, redact, OpenAI compatible, RAG.

import glob
import json
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, jsonify, render_template, request, send_file

from auth.decorators import require_permission
from config import CONFIG, save_config
from event_logger import query_events
from paths import AUDIT_LOG_FILE, DATA_DIR, OPERATION_LOG_FILE, ensure_directory


bp = Blueprint("local_model", __name__)

DEFAULT_LOCAL_MODEL = {
    "enabled": True,
    "name": "122 本地模型",
    "provider": "openai-compatible",
    "base_url": "http://192.168.50.122:8001/v1",
    "vllm_base_url": "http://192.168.50.122:8000/v1",
    "model": "gemma-4-e4b-awq-int4",
    "api_key": "dummy",
    "timeout_sec": 120,
    "temperature": 0.2,
    "max_tokens": 512,
    "max_model_len": 32768,
    "system_prompt": "你是演播中控系统的本地助手，回答要基于中控设备、协议、日志和运行状态。涉及真实控制动作时，先说明风险并等待人工确认。",
    "training_export": {"enabled": True, "include_logs": True, "recent_log_limit": 500},
}

LEGACY_LOCAL_MODEL_BASE_URLS = {"http://192.168.50.122:8000/v1"}
LEGACY_LOCAL_MODEL_MODELS = {"gemma-4-26b-a4b"}

DEVICE_SECTIONS = {
    "cabinets": "强电柜",
    "meters": "电表",
    "ups_devices": "UPS",
    "snmp_devices": "SNMP设备",
    "nvr_devices": "NVR/摄像机",
    "light_devices": "灯光/继电器",
    "projectors": "投影机",
    "screens": "幕布",
    "sequencers": "时序电源",
    "hvac_devices": "空调",
    "env_sensors": "环境传感器",
    "custom_devices": "泛型控制设备",
}

SENSITIVE_KEY_PARTS = (
    "password", "passwd", "token", "secret", "api_key", "apikey", "authorization",
    "credential", "private_key", "access_key", "rtsp_url",
)


def _training_dir():
    return ensure_directory(DATA_DIR / "training" / "local_model")


def _redact_url(value):
    text = str(value or "")
    try:
        parsed = urlsplit(text)
    except Exception:
        return text
    if not parsed.scheme or "@" not in parsed.netloc:
        return text
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, f"***:***@{netloc}", parsed.path, parsed.query, parsed.fragment))


def _redact(value, key=""):
    key_text = str(key or "").lower()
    if any(part in key_text for part in SENSITIVE_KEY_PARTS):
        return "***REDACTED***" if value not in (None, "") else ""
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key_text) for item in value]
    if isinstance(value, str) and "://" in value and "@" in value:
        return _redact_url(value)
    return value


def normalize_local_model_config(raw_config=None, *, keep_secret=True):
    merged = deepcopy(DEFAULT_LOCAL_MODEL)
    source_config = raw_config if isinstance(raw_config, dict) else {}
    if source_config:
        for key, value in source_config.items():
            if key == "training_export" and isinstance(value, dict):
                merged["training_export"].update(value)
            else:
                merged[key] = value
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["name"] = str(merged.get("name") or DEFAULT_LOCAL_MODEL["name"]).strip() or DEFAULT_LOCAL_MODEL["name"]
    merged["provider"] = str(merged.get("provider") or DEFAULT_LOCAL_MODEL["provider"]).strip() or DEFAULT_LOCAL_MODEL["provider"]
    merged["base_url"] = str(merged.get("base_url") or DEFAULT_LOCAL_MODEL["base_url"]).strip().rstrip("/") or DEFAULT_LOCAL_MODEL["base_url"]
    if merged["base_url"] in LEGACY_LOCAL_MODEL_BASE_URLS and not source_config.get("vllm_base_url"):
        merged["base_url"] = DEFAULT_LOCAL_MODEL["base_url"]
    merged["vllm_base_url"] = str(merged.get("vllm_base_url") or DEFAULT_LOCAL_MODEL["vllm_base_url"]).strip().rstrip("/") or DEFAULT_LOCAL_MODEL["vllm_base_url"]
    merged["model"] = str(merged.get("model") or DEFAULT_LOCAL_MODEL["model"]).strip() or DEFAULT_LOCAL_MODEL["model"]
    if merged["model"] in LEGACY_LOCAL_MODEL_MODELS:
        merged["model"] = DEFAULT_LOCAL_MODEL["model"]
    merged["api_key"] = str(merged.get("api_key") or "").strip()
    merged["system_prompt"] = str(merged.get("system_prompt") or DEFAULT_LOCAL_MODEL["system_prompt"]).strip() or DEFAULT_LOCAL_MODEL["system_prompt"]
    for key, default, minimum, maximum in (("timeout_sec", 120, 3, 600), ("temperature", 0.2, 0, 2)):
        try:
            merged[key] = max(minimum, min(float(merged.get(key, default) or default), maximum))
        except Exception:
            merged[key] = default
    try:
        merged["max_tokens"] = max(64, min(int(merged.get("max_tokens", 512) or 512), 4096))
    except Exception:
        merged["max_tokens"] = 512
    try:
        merged["max_model_len"] = max(1024, min(int(merged.get("max_model_len", 32768) or 32768), 262144))
    except Exception:
        merged["max_model_len"] = 32768
    export_cfg = merged.get("training_export") if isinstance(merged.get("training_export"), dict) else {}
    merged_export = deepcopy(DEFAULT_LOCAL_MODEL["training_export"])
    merged_export.update(export_cfg)
    merged_export["enabled"] = bool(merged_export.get("enabled", True))
    merged_export["include_logs"] = bool(merged_export.get("include_logs", True))
    try:
        merged_export["recent_log_limit"] = max(0, min(int(merged_export.get("recent_log_limit", 500) or 0), 5000))
    except Exception:
        merged_export["recent_log_limit"] = 500
    merged["training_export"] = merged_export
    if not keep_secret:
        merged["api_key_set"] = bool(merged.get("api_key"))
        merged["api_key"] = ""
    return merged


def _save_local_model_config(payload):
    current = normalize_local_model_config(CONFIG.get("local_model"))
    incoming = payload if isinstance(payload, dict) else {}
    if "api_key" not in incoming or str(incoming.get("api_key") or "").strip() in {"", "******"}:
        incoming = dict(incoming)
        incoming["api_key"] = current.get("api_key", "")
    next_config = normalize_local_model_config(incoming)
    CONFIG["local_model"] = next_config
    save_config(CONFIG)
    return next_config


def _request_json(url, payload=None, timeout=30, api_key=""):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if payload is not None else "GET")
    started = time.time()
    with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except Exception:
            data = {"raw": text}
        return {"status": resp.status, "elapsed_ms": int((time.time() - started) * 1000), "data": data}


def _parse_openai_model_list(data):
    if not isinstance(data, dict):
        return []
    model_rows = data.get("data")
    if not isinstance(model_rows, list):
        return []
    rows = []
    for item in model_rows:
        if not isinstance(item, dict):
            continue
        docs_count = _extract_docs_count(item)
        rows.append({
            "id": item.get("id") or item.get("model") or "",
            "max_model_len": item.get("max_model_len") or item.get("max_context_len") or item.get("context_length"),
            "owned_by": item.get("owned_by") or "",
            "docs_count": docs_count,
        })
    return [row for row in rows if row["id"]]


def _extract_docs_count(data):
    if not isinstance(data, dict):
        return None
    keys = ("docs_count", "document_count", "knowledge_docs", "loaded_docs", "docs")
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    for value in data.values():
        if isinstance(value, dict):
            nested = _extract_docs_count(value)
            if nested is not None:
                return nested
    return None


def _check_model_endpoint(label, base_url, cfg, timeout):
    url = f"{str(base_url or '').rstrip('/')}/models"
    try:
        result = _request_json(url, timeout=timeout, api_key=cfg.get("api_key", ""))
        data = result.get("data", {})
        models = _parse_openai_model_list(data)
        return {
            "label": label,
            "ok": True,
            "online": True,
            "url": url,
            "elapsed_ms": result.get("elapsed_ms"),
            "models": models,
            "model_ids": [item["id"] for item in models],
            "docs_count": _extract_docs_count(data),
        }
    except Exception as exc:
        return {"label": label, "ok": False, "online": False, "url": url, "error": str(exc)}


def _read_json_file(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _jsonl_write(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _extract_device_records(config):
    rows = []
    for section, label in DEVICE_SECTIONS.items():
        items = config.get(section, [])
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            device_id = str(item.get("id") or item.get("device_id") or item.get("mac") or f"{section}_{index + 1}")
            rows.append({
                "schema": "smart_center.training.v1",
                "kind": "device",
                "source_section": section,
                "device_type": label,
                "device_id": device_id,
                "name": item.get("name") or item.get("cabinet_name") or item.get("display_name") or device_id,
                "protocol": item.get("protocol") or item.get("brand") or item.get("comm_type") or item.get("transport") or "",
                "host": item.get("ip") or item.get("host") or item.get("adapter_ip") or "",
                "port": item.get("port") or item.get("local_port") or "",
                "enabled": item.get("enabled", item.get("visible", True)),
                "raw": _redact(item),
            })
    current_collector = config.get("current_collector")
    if isinstance(current_collector, dict):
        rows.append({
            "schema": "smart_center.training.v1",
            "kind": "device",
            "source_section": "current_collector",
            "device_type": "电流采集器",
            "device_id": "current_collector",
            "name": current_collector.get("name") or "电流采集器",
            "protocol": current_collector.get("transport") or "modbus",
            "host": current_collector.get("host") or "",
            "port": current_collector.get("port") or "",
            "enabled": current_collector.get("enabled", True),
            "raw": _redact(current_collector),
        })
    return rows


def _extract_protocol_records(config):
    rows = []
    for section in ("control_center", "home_assistant", "meter_statistics", "server_monitor", "proxy_monitor"):
        payload = config.get(section)
        if isinstance(payload, (dict, list)):
            rows.append({
                "schema": "smart_center.training.v1",
                "kind": "protocol_config",
                "source_section": section,
                "name": section,
                "raw": _redact(payload),
            })
    for pattern in ("control_packs/*.json", "deploy/driver_hub_bundle/*.json", "deploy/node_red_driver_pack/*.json", "projector_brands.json"):
        for filename in sorted(glob.glob(pattern))[:50]:
            payload = _read_json_file(filename, None)
            if payload is None:
                continue
            rows.append({
                "schema": "smart_center.training.v1",
                "kind": "protocol_file",
                "source_file": filename,
                "name": Path(filename).name,
                "raw": _redact(payload),
            })
    return rows


def _extract_log_records(limit):
    rows = []
    if limit <= 0:
        return rows
    try:
        events = query_events(limit=limit, offset=0).get("items", [])
    except Exception:
        events = []
    for item in events:
        rows.append({
            "schema": "smart_center.training.v1",
            "kind": "event_log",
            "source": "event_logs.db",
            "time": item.get("time"),
            "category": item.get("category"),
            "event_type": item.get("event_type"),
            "device_id": item.get("device_id"),
            "device_name": item.get("device_name"),
            "action": item.get("action"),
            "result": item.get("result"),
            "message": item.get("message"),
            "raw": _redact(item),
        })
    for source_name, path in (("operation_logs.json", OPERATION_LOG_FILE), ("audit_logs.json", AUDIT_LOG_FILE)):
        payload = _read_json_file(path, [])
        if not isinstance(payload, list):
            continue
        for item in payload[-limit:]:
            if isinstance(item, dict):
                rows.append({
                    "schema": "smart_center.training.v1",
                    "kind": "legacy_log",
                    "source": source_name,
                    "time": item.get("time") or item.get("timestamp"),
                    "category": item.get("category") or "system",
                    "message": item.get("operation") or item.get("message") or item.get("action"),
                    "raw": _redact(item),
                })
    return rows



def _count_by(rows, key):
    counts = {}
    for row in rows:
        value = str(row.get(key) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_items(counts, limit=12):
    return [{"name": key, "count": value} for key, value in list(counts.items())[:limit]]


def _compact_value(value, default="未配置"):
    text = str(value or "").strip()
    return text if text else default


def _device_capabilities(row):
    section = str(row.get("source_section") or "")
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    caps = []
    if section == "cabinets":
        caps.extend(["强电回路控制", "回路状态读取", "电能/功率监测"])
    elif section == "meters":
        caps.extend(["电表采集", "用电趋势分析", "能耗统计"])
    elif section == "ups_devices":
        caps.extend(["UPS状态监测", "电池/负载告警"])
    elif section == "snmp_devices":
        caps.extend(["SNMP轮询", "网络设备/服务器/NAS指标监测"])
    elif section == "nvr_devices":
        caps.extend(["NVR/摄像机状态监测", "视频通道可用性检查"])
    elif section == "light_devices":
        caps.extend(["灯光/继电器输出控制", "输出状态读取"])
        if raw.get("input_count"):
            caps.append("输入状态读取")
    elif section == "projectors":
        caps.extend(["投影机开关机", "信号源/状态查询", "异常状态识别"])
    elif section == "screens":
        caps.extend(["幕布升降停止控制", "幕布状态维护"])
    elif section == "sequencers":
        caps.extend(["时序电源分路控制", "顺序上电/断电"])
    elif section == "hvac_devices":
        caps.extend(["空调状态读取", "温度/模式/开关控制"])
    elif section == "env_sensors":
        caps.extend(["温湿度/环境指标采集", "环境异常辅助判断"])
    elif section == "custom_devices":
        caps.extend(["泛型协议控制", "自定义命令发送", "状态解析"])
    elif section == "current_collector":
        caps.extend(["多路电流采集", "组合回路汇总", "设备运行状态推断"])
    command_count = len(raw.get("commands") or raw.get("command_list") or [])
    if command_count:
        caps.append(f"配置了 {command_count} 个命令")
    channel_count = raw.get("channel_count") or raw.get("channels") or raw.get("count")
    if channel_count:
        caps.append(f"约 {channel_count} 个通道/回路")
    return caps


def _device_dependencies(row):
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    section = str(row.get("source_section") or "")
    deps = []
    if row.get("host"):
        deps.append(f"网络地址 {row.get('host')}:{row.get('port') or '默认端口'}")
    protocol = str(row.get("protocol") or "").lower()
    if "ha" in protocol or section == "hvac_devices":
        deps.append("可能依赖 Home Assistant/米家桥接/设备 token")
    if "snmp" in protocol or section == "snmp_devices":
        deps.append("依赖 SNMP community、OID 和网络可达性")
    if "modbus" in protocol or section in {"cabinets", "meters", "current_collector"}:
        deps.append("依赖 Modbus 地址、寄存器、倍率和轮询超时配置")
    if section == "projectors":
        deps.append("状态判断可能依赖供电回路、电流采集或投影机协议回包")
    if raw.get("scene_id") or raw.get("automation_id"):
        deps.append("可能被场景/自动化联动调用")
    return deps


def _build_device_insights(device_rows):
    rows = []
    for row in device_rows:
        name = _compact_value(row.get("name"), row.get("device_id") or "未命名设备")
        protocol = _compact_value(row.get("protocol"))
        host = _compact_value(row.get("host"), "未绑定网络地址")
        port = _compact_value(row.get("port"), "默认端口")
        capabilities = _device_capabilities(row)
        dependencies = _device_dependencies(row)
        summary = (
            f"{name} 属于{row.get('device_type') or row.get('source_section')}，"
            f"协议/品牌为 {protocol}，地址为 {host}:{port}。"
            f"主要能力：{'、'.join(capabilities) if capabilities else '待从配置补充'}。"
        )
        if dependencies:
            summary += f" 关键依赖：{'、'.join(dependencies)}。"
        rows.append({
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "device_profile",
            "title": f"设备画像：{name}",
            "subject_id": row.get("device_id"),
            "source_section": row.get("source_section"),
            "device_type": row.get("device_type"),
            "summary": summary,
            "facts": {
                "name": name,
                "protocol": protocol,
                "host": row.get("host") or "",
                "port": row.get("port") or "",
                "enabled": row.get("enabled"),
                "capabilities": capabilities,
                "dependencies": dependencies,
            },
            "training_hint": "回答设备用途、协议、地址、依赖关系和排障顺序时优先参考该画像。",
        })
    return rows


def _build_protocol_insights(device_rows, protocol_rows):
    grouped = {}
    for row in device_rows:
        protocol = str(row.get("protocol") or row.get("source_section") or "unknown").strip() or "unknown"
        item = grouped.setdefault(protocol, {"devices": [], "sections": set()})
        item["devices"].append(row.get("name") or row.get("device_id"))
        item["sections"].add(str(row.get("source_section") or ""))
    insights = []
    for protocol, payload in sorted(grouped.items(), key=lambda item: (-len(item[1]["devices"]), item[0])):
        proto_l = protocol.lower()
        checks = ["确认设备在线和 IP/端口可达", "核对中控配置是否与现场设备一致", "查看事件日志中的超时、拒绝和状态变化"]
        if "modbus" in proto_l or any(section in payload["sections"] for section in ("cabinets", "meters", "current_collector")):
            checks.extend(["核对站号/slave、寄存器地址、功能码、倍率", "区分 TCP Modbus 与 RTU over TCP 网关"])
        if "snmp" in proto_l:
            checks.extend(["核对 community、SNMP版本、自定义 OID", "检查 NAS/交换机是否允许 120 访问"])
        if "miio" in proto_l or "xiaomi" in proto_l:
            checks.extend(["核对米家 token、局域网可达性", "米家 App 正常但中控异常时优先查桥接层和实体映射"])
        if "pjlink" in proto_l or "projector" in proto_l:
            checks.extend(["区分协议回包状态、供电状态和电流推断状态", "投影关机与断电不能混为一类"])
        insights.append({
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "protocol_capability",
            "title": f"协议能力卡：{protocol}",
            "protocol": protocol,
            "summary": f"{protocol} 当前关联 {len(payload['devices'])} 个设备，覆盖 {', '.join(sorted(x for x in payload['sections'] if x)) or '未知模块'}。",
            "facts": {
                "device_count": len(payload["devices"]),
                "sample_devices": [str(item) for item in payload["devices"][:20]],
                "source_sections": sorted(x for x in payload["sections"] if x),
                "troubleshooting": checks,
            },
            "training_hint": "遇到协议离线、状态不准、控制失败时，先按该能力卡给出排查路径。",
        })
    if protocol_rows:
        insights.append({
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "protocol_inventory",
            "title": "协议与驱动资产总览",
            "summary": f"本次导出包含 {len(protocol_rows)} 条协议/驱动配置记录，覆盖控制中心、驱动包、投影命令库和监控配置。",
            "facts": {"record_count": len(protocol_rows), "sources": _top_items(_count_by(protocol_rows, "kind"), 20)},
            "training_hint": "回答系统支持哪些协议、驱动和命令库时使用该总览。",
        })
    return insights


def _build_rule_insights(config):
    current = config.get("current_collector") if isinstance(config.get("current_collector"), dict) else {}
    groups = current.get("groups") if isinstance(current.get("groups"), list) else []
    projectors = config.get("projectors") if isinstance(config.get("projectors"), list) else []
    hvacs = config.get("hvac_devices") if isinstance(config.get("hvac_devices"), list) else []
    rules = [
        {
            "title": "状态推断：先判断供电，再判断设备开关机",
            "summary": "投影、时序电源和强电相关问题要先区分断电、待机、开机和通信失败。供电状态优先来自电柜/时序电源/电流采集，设备开关机再结合协议回包和电流阈值。",
            "facts": {"projector_count": len(projectors), "current_collector_groups": groups},
        },
        {
            "title": "空调排障：米家正常不代表 HA/中控链路正常",
            "summary": "如果米家 App 能直接控制但中控显示离线，优先检查 Home Assistant 桥接、实体映射、token、局域网可达性、轮询超时和最近日志。",
            "facts": {"hvac_count": len(hvacs), "home_assistant": _redact(config.get("home_assistant") or {})},
        },
        {
            "title": "电流采集：适合做运行状态辅助证据",
            "summary": "电流采集比总功率更适合判断单一设备是否开机，但阈值必须避开同线路小功率设备干扰；结论应同时说明供电状态和电流证据。",
            "facts": {"collector_enabled": current.get("enabled"), "host": current.get("host"), "groups": groups},
        },
        {
            "title": "控制安全：高风险动作必须二次确认",
            "summary": "强电断电、时序电源关闭、投影关机、场景批量联动、自动化规则修改都可能影响现场演出或参观，模型只能给建议，不能替用户直接执行。",
            "facts": {"high_risk_actions": ["power_off", "sequencer_off", "projector_off", "scene_run", "automation_edit"]},
        },
    ]
    return [
        {
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "inference_rule" if "状态推断" in item["title"] or "电流采集" in item["title"] else "operation_policy",
            "title": item["title"],
            "summary": item["summary"],
            "facts": item["facts"],
            "training_hint": "回答状态判断、故障分析或操作建议时，应显式引用该规则并说明证据。",
        }
        for item in rules
    ]


def _build_log_insights(log_rows):
    category_counts = _count_by(log_rows, "category")
    event_type_counts = _count_by(log_rows, "event_type")
    result_counts = _count_by(log_rows, "result")
    source_counts = _count_by(log_rows, "source")
    device_counts = {}
    recent_errors = []
    for row in log_rows:
        device = str(row.get("device_name") or row.get("device_id") or "").strip()
        if device:
            device_counts[device] = device_counts.get(device, 0) + 1
        result_text = str(row.get("result") or "").lower()
        msg = str(row.get("message") or "")
        if len(recent_errors) < 30 and ("error" in result_text or "fail" in result_text or "异常" in msg or "失败" in msg or "离线" in msg):
            recent_errors.append({
                "time": row.get("time"),
                "category": row.get("category"),
                "device": device,
                "action": row.get("action"),
                "result": row.get("result"),
                "message": msg[:240],
            })
    return [{
        "schema": "smart_center.training.v1",
        "kind": "insight",
        "insight_type": "log_pattern",
        "title": "日志模式摘要",
        "summary": f"本次纳入 {len(log_rows)} 条日志。高频模块：{', '.join(f'{x['name']}({x['count']})' for x in _top_items(category_counts, 5)) or '暂无'}。",
        "facts": {
            "category_counts": category_counts,
            "event_type_counts": event_type_counts,
            "result_counts": result_counts,
            "source_counts": source_counts,
            "top_devices": _top_items(dict(sorted(device_counts.items(), key=lambda item: (-item[1], item[0]))), 15),
            "recent_errors": recent_errors,
        },
        "training_hint": "回答最近异常、外部变化、自动化影响和高频故障时优先参考该摘要。",
    }]


def _build_qa_insights(device_rows):
    samples = [
        ("列出所有 TCP/网络协议设备", "按 devices 中 host 非空或 protocol/comm_mode 为 TCP/UDP/HTTP/SNMP/Modbus TCP 的记录筛选，并返回名称、地址、端口、协议。"),
        ("某设备离线应该先查什么", "先查网络可达、协议参数、桥接服务、最近事件日志，再区分设备断电、通信失败和配置错误。"),
        ("投影现在是断电还是关机", "先看供电回路/时序电源/电柜状态，再看电流采集和投影协议回包，不能只凭单一总功率判断。"),
        ("空调米家可控但中控离线", "优先查 Home Assistant/miio 桥接、实体映射、token、局域网连通和轮询日志。"),
        ("哪些操作需要谨慎", "强电、时序电源、投影关机、场景联动和自动化修改都需要人工确认。"),
    ]
    return [
        {
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "qa_pattern",
            "title": f"问答模式：{question}",
            "instruction": question,
            "output": answer,
            "facts": {"device_inventory_count": len(device_rows)},
            "training_hint": "作为模型回答中控常见问题的风格和推理模板。",
        }
        for question, answer in samples
    ]


def build_insights(config, device_rows, protocol_rows, log_rows):
    insight_rows = []
    insight_rows.extend(_build_device_insights(device_rows))
    insight_rows.extend(_build_protocol_insights(device_rows, protocol_rows))
    insight_rows.extend(_build_rule_insights(config))
    insight_rows.extend(_build_log_insights(log_rows))
    insight_rows.extend(_build_qa_insights(device_rows))
    daily_summary = {
        "schema": "smart_center.training.v1",
        "kind": "daily_summary",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "devices": len(device_rows),
            "protocol_records": len(protocol_rows),
            "logs": len(log_rows),
            "insights": len(insight_rows),
        },
        "device_sections": _count_by(device_rows, "source_section"),
        "device_types": _count_by(device_rows, "device_type"),
        "protocols": _count_by(device_rows, "protocol"),
        "log_categories": _count_by(log_rows, "category"),
        "log_results": _count_by(log_rows, "result"),
        "recommended_model_use": [
            "优先用 insights 做中控知识库/RAG 检索",
            "用 devices/protocols/logs 作为证据来源",
            "涉及真实控制动作时只给建议和风险，不直接执行",
            "每天比较 daily_summary 可发现设备、协议和异常趋势变化",
        ],
    }
    return insight_rows, daily_summary


def build_training_export():
    config = deepcopy(CONFIG)
    model_cfg = normalize_local_model_config(config.get("local_model"))
    export_cfg = model_cfg.get("training_export", {})
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _training_dir()
    device_rows = _extract_device_records(config)
    protocol_rows = _extract_protocol_records(config)
    log_rows = _extract_log_records(int(export_cfg.get("recent_log_limit", 500))) if export_cfg.get("include_logs", True) else []
    insight_rows, daily_summary = build_insights(config, device_rows, protocol_rows, log_rows)
    instruction_rows = [
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据中控配置说明指定设备的协议、地址、用途和可用控制能力。",
            "input": {"device_inventory_count": len(device_rows)},
            "output": "已归一化设备清单，可按 source_section、device_type、device_id 检索，并可结合 insights 中的 device_profile 回答。",
        },
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据中控事件日志判断动作来自人工、自动化、设备回报还是外部变化。",
            "input": {"event_log_count": len(log_rows)},
            "output": "event_log 记录包含 category、event_type、source、action、result、message 和脱敏 raw；log_pattern insight 提供聚合结论。",
        },
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "回答中控状态推断和排障问题时，优先引用提炼后的规则、设备画像和协议能力卡。",
            "input": {"insight_count": len(insight_rows)},
            "output": "先给结论，再列证据，最后给排查或操作建议；涉及真实控制动作必须提醒人工确认。",
        },
    ]
    files = {
        "devices": out_dir / f"devices_{stamp}.jsonl",
        "protocols": out_dir / f"protocols_{stamp}.jsonl",
        "logs": out_dir / f"logs_{stamp}.jsonl",
        "instructions": out_dir / f"instructions_{stamp}.jsonl",
        "insights": out_dir / f"insights_{stamp}.jsonl",
        "daily_summary": out_dir / f"daily_summary_{stamp}.json",
        "knowledge": out_dir / f"knowledge_{stamp}.json",
    }
    _jsonl_write(files["devices"], device_rows)
    _jsonl_write(files["protocols"], protocol_rows)
    _jsonl_write(files["logs"], log_rows)
    _jsonl_write(files["instructions"], instruction_rows)
    _jsonl_write(files["insights"], insight_rows)
    files["daily_summary"].write_text(json.dumps(daily_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    knowledge = {
        "schema": "smart_center.training.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_target": {k: v for k, v in model_cfg.items() if k != "api_key"},
        "counts": {
            "devices": len(device_rows),
            "protocol_records": len(protocol_rows),
            "logs": len(log_rows),
            "instructions": len(instruction_rows),
            "insights": len(insight_rows),
        },
        "device_sections": DEVICE_SECTIONS,
        "insight_types": _count_by(insight_rows, "insight_type"),
        "daily_summary": daily_summary,
        "config_snapshot": _redact(config),
        "files": {name: str(path) for name, path in files.items()},
    }
    files["knowledge"].write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "generated_at": knowledge["generated_at"], "counts": knowledge["counts"], "files": {name: str(path) for name, path in files.items()}}


def _list_training_files():
    out_dir = _training_dir()
    rows = []
    for path in sorted(out_dir.glob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if path.is_file():
            rows.append({
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            })
    return rows[:100]


@bp.route("/local-model")
@require_permission("local_model.view")
def local_model_page():
    return render_template("local_model.html", config=CONFIG)


@bp.route("/api/local-model/config", methods=["GET"])
@require_permission("local_model.view")
def api_local_model_config():
    return jsonify({"ok": True, "config": normalize_local_model_config(CONFIG.get("local_model"), keep_secret=False)})


@bp.route("/api/local-model/config", methods=["POST"])
@require_permission("system.config")
def api_local_model_save_config():
    if not request.is_json:
        return jsonify({"ok": False, "error": "json_required", "msg": "需要 JSON 配置"}), 400
    payload = request.get_json(silent=True) or {}
    next_config = _save_local_model_config(payload)
    return jsonify({"ok": True, "config": normalize_local_model_config(next_config, keep_secret=False)})


@bp.route("/api/local-model/health")
@require_permission("local_model.view")
def api_local_model_health():
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    timeout = min(float(cfg.get("timeout_sec", 120)), 10)
    proxy_status = _check_model_endpoint("knowledge_proxy", cfg.get("base_url"), cfg, timeout)
    vllm_status = _check_model_endpoint("vllm_upstream", cfg.get("vllm_base_url"), cfg, timeout)
    online = bool(proxy_status.get("online"))
    model_rows = proxy_status.get("models") or vllm_status.get("models") or []
    docs_count = proxy_status.get("docs_count")
    max_model_len = cfg.get("max_model_len")
    for row in model_rows:
        if row.get("id") != cfg.get("model"):
            continue
        if row.get("max_model_len"):
            max_model_len = row.get("max_model_len")
        if row.get("docs_count") is not None:
            docs_count = row.get("docs_count")
        break
    return jsonify({
        "ok": online,
        "online": online,
        "proxy_online": bool(proxy_status.get("online")),
        "vllm_online": bool(vllm_status.get("online")),
        "url": proxy_status.get("url"),
        "vllm_url": vllm_status.get("url"),
        "model": cfg.get("model"),
        "models": [item.get("id") for item in model_rows if item.get("id")],
        "model_details": model_rows,
        "docs_count": docs_count,
        "max_model_len": max_model_len,
        "elapsed_ms": proxy_status.get("elapsed_ms"),
        "proxy": proxy_status,
        "vllm": vllm_status,
        "error": proxy_status.get("error") if not online else "",
    }), (200 if online else 502)


@bp.route("/api/local-model/chat", methods=["POST"])
@require_permission("local_model.control")
def api_local_model_chat():
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    if not cfg.get("enabled", True):
        return jsonify({"ok": False, "error": "disabled", "msg": "本地模型入口已关闭"}), 400
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    prompt = str(payload.get("prompt") or "").strip()
    normalized_messages = []
    if cfg.get("system_prompt"):
        normalized_messages.append({"role": "system", "content": cfg["system_prompt"]})
    for item in messages[-20:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        if role not in {"user", "assistant", "system"}:
            role = "user"
        content = str(item.get("content") or "").strip()
        if content:
            normalized_messages.append({"role": role, "content": content})
    if prompt:
        normalized_messages.append({"role": "user", "content": prompt})
    if not any(item.get("role") == "user" for item in normalized_messages):
        return jsonify({"ok": False, "error": "empty_prompt", "msg": "请输入问题"}), 400
    req_payload = {
        "model": cfg["model"],
        "messages": normalized_messages,
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "stream": False,
    }
    try:
        result = _request_json(f"{cfg['base_url']}/chat/completions", payload=req_payload, timeout=cfg["timeout_sec"], api_key=cfg.get("api_key", ""))
        data = result.get("data", {})
        answer = ""
        choices = data.get("choices") if isinstance(data, dict) else []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            answer = str(message.get("content") or choices[0].get("text") or "")
        return jsonify({"ok": True, "answer": answer, "elapsed_ms": result.get("elapsed_ms"), "model": cfg["model"], "raw": data})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return jsonify({"ok": False, "error": "http_error", "status": exc.code, "msg": detail}), 502
    except Exception as exc:
        return jsonify({"ok": False, "error": "request_failed", "msg": str(exc)}), 502


@bp.route("/api/local-model/export-training", methods=["POST"])
@require_permission("system.config")
def api_local_model_export_training():
    return jsonify(build_training_export())


@bp.route("/api/local-model/training-files")
@require_permission("local_model.view")
def api_local_model_training_files():
    return jsonify({"ok": True, "files": _list_training_files()})


@bp.route("/api/local-model/training-files/<path:filename>")
@require_permission("local_model.view")
def api_local_model_download_training_file(filename):
    base = _training_dir().resolve()
    target = (base / filename).resolve()
    if base not in target.parents and target != base:
        return jsonify({"ok": False, "error": "invalid_path"}), 400
    if not target.is_file():
        return jsonify({"ok": False, "error": "not_found"}), 404
    return send_file(target, as_attachment=True, download_name=target.name)
