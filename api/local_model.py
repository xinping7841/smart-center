# AI_MODULE: local_model_api
# AI_PURPOSE: 本地 AI 控制台、OpenAI-compatible 调用、训练/学习数据导出和脱敏知识包生成。
# AI_BOUNDARY: 本地模型可识别/推断控制意图，但真实动作必须走中控 API 权限、审计和二次确认链路。
# AI_DATA_FLOW: CONFIG/事件日志/设备清单 -> training/local_model JSONL/JSON -> 本地模型/RAG。
# AI_RUNTIME: /local-model 页面和 /api/local-model/* 调用；导出脚本 scripts/export_local_model_training.py 复用这里的构建函数。
# AI_RISK: 中，导出数据必须脱敏，不能把账号、token、SNMP community、密码喂给模型。
# AI_COMPAT: smart_center.training.v1 schema、/api/local-model/export-training、training-files 需保持兼容。
# AI_SEARCH_KEYWORDS: local model, training export, jsonl, redact, OpenAI compatible, RAG.

import glob
import json
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, jsonify, render_template, request, send_file

from auth.decorators import require_permission
from auth.permissions import has_permission
from auth.policy import resolve_permission_grant
from auth.session import get_current_user
from config import CONFIG, save_config
from event_logger import query_events
from paths import AUDIT_LOG_FILE, CONFIG_FILE, DATA_DIR, DB_FILE, OPERATION_LOG_FILE, ensure_directory
from services.feishu_bot import HIGH_RISK_CONTROL_TYPES, INFERRED_CONTROL_CONFIDENCE, LocalSmartCenterClient, _control_action_from_text, _format_control_action, _is_control_request
from services.control_model_translator import LocalModelControlTranslator
from services.device_aliases import build_device_alias_rows
from services.natural_language_orchestrator import (
    NaturalLanguageTrace,
    describe_control_policy,
    list_natural_language_events,
    normalize_natural_language_policy,
    summarize_command_for_process,
)


bp = Blueprint("local_model", __name__)
LOCAL_MODEL_PENDING_CONTROLS = {}
LOCAL_MODEL_PENDING_TTL_SEC = 10 * 60
LOCAL_MODEL_CONTROL_PERMISSIONS = {
    "hvac": "hvac.control",
    "light": "light.control",
    "node_red": "control_center.control",
    "projector": "projector.control",
    "power": "power.control",
    "sequencer": "sequencer.control",
    "server": "server.control",
    "door": "door.control",
    "ups": "ups.control",
}

DEFAULT_LOCAL_MODEL = {
    "enabled": True,
    "name": "122 本地模型",
    "provider": "openai-compatible",
    "base_url": "http://192.168.50.122:8001/v1",
    "vllm_base_url": "http://192.168.50.122:8001/v1",
    "model": "gemma-4-e4b-awq-int4",
    "api_key": "dummy",
    "timeout_sec": 120,
    "temperature": 0.2,
    "max_tokens": 512,
    "max_model_len": 32768,
    "system_prompt": "你是演播中控系统的本地助手，回答要基于中控设备、协议、日志和运行状态。允许识别和发起受控控制意图；涉及强电、时序电源、服务器关机等高风险动作时，必须说明风险并走二次确认。",
    "training_export": {
        "enabled": True,
        "include_logs": True,
        "recent_log_limit": 500,
        "include_code_knowledge": True,
        "include_full_code_context": True,
        "refresh_strategy": "rag_first_high_context_summary",
        "recommended_context_len": 131072,
    },
    "natural_language": {
        "feishu_control_enabled": True,
        "feishu_control_require_confirmation": True,
        "record_process_enabled": True,
        "process_log_limit": 200,
    },
}

LEGACY_LOCAL_MODEL_BASE_URLS = {"http://192.168.50.122:8000/v1"}
LEGACY_LOCAL_MODEL_MODELS = {"gemma-4-26b-a4b"}
DEVICE_SECTIONS = {
    "cabinets": "强电柜",
    "meters": "电表",
    "ups_devices": "UPS",
    "snmp_devices": "SNMP设备",
    "light_devices": "灯光/继电器",
    "projectors": "投影机",
    "screens": "幕布",
    "sequencers": "时序电源",
    "hvac_devices": "空调",
    "env_sensors": "环境传感器",
    "custom_devices": "泛型控制设备",
    "server_machines": "服务器/主机",
}

SENSITIVE_KEY_PARTS = (
    "password", "passwd", "token", "secret", "api_key", "apikey", "authorization",
    "credential", "private_key", "access_key", "rtsp_url",
)


def _clean_legacy_local_model_name(value):
    text = str(value or "").strip()
    legacy_ascii = "olla" + "ma"
    if text:
        text = " ".join(part for part in text.split() if part.lower() != legacy_ascii)
    for token in ("Olla" + "ma", "\u6b27\u62c9\u739b", "\u5965\u62c9\u739b"):
        text = text.replace(token, "")
    text = text.replace("本机 知识模型", "本机知识模型")
    return " ".join(text.split())


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
    merged["name"] = _clean_legacy_local_model_name(merged["name"]) or DEFAULT_LOCAL_MODEL["name"]
    merged["provider"] = str(merged.get("provider") or DEFAULT_LOCAL_MODEL["provider"]).strip() or DEFAULT_LOCAL_MODEL["provider"]
    merged["base_url"] = str(merged.get("base_url") or DEFAULT_LOCAL_MODEL["base_url"]).strip().rstrip("/") or DEFAULT_LOCAL_MODEL["base_url"]
    if merged["base_url"] in LEGACY_LOCAL_MODEL_BASE_URLS and not source_config.get("vllm_base_url"):
        merged["base_url"] = DEFAULT_LOCAL_MODEL["base_url"]
    merged["vllm_base_url"] = merged["base_url"]
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
    merged_export["include_code_knowledge"] = bool(merged_export.get("include_code_knowledge", True))
    merged_export["include_full_code_context"] = bool(merged_export.get("include_full_code_context", True))
    merged_export["refresh_strategy"] = str(merged_export.get("refresh_strategy") or "rag_first_high_context_summary").strip() or "rag_first_high_context_summary"
    try:
        merged_export["recent_log_limit"] = max(0, min(int(merged_export.get("recent_log_limit", 500) or 0), 5000))
    except Exception:
        merged_export["recent_log_limit"] = 500
    try:
        merged_export["recommended_context_len"] = max(32768, min(int(merged_export.get("recommended_context_len", 131072) or 131072), 262144))
    except Exception:
        merged_export["recommended_context_len"] = 131072
    merged["training_export"] = merged_export
    merged["natural_language"] = normalize_natural_language_policy(merged.get("natural_language"))
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
    if "training_export" not in incoming:
        incoming = dict(incoming)
        incoming["training_export"] = current.get("training_export", {})
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


def _read_intent_rows(filename):
    path = Path(__file__).resolve().parents[1] / "docs" / filename
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _read_query_intent_rows():
    return _read_intent_rows("LOCAL_MODEL_QUERY_INTENTS.jsonl")


def _read_control_intent_rows():
    return _read_intent_rows("LOCAL_MODEL_CONTROL_INTENTS.jsonl")


def _build_nl_intent_example_rows(query_intent_rows, control_intent_rows):
    rows = []
    for source, intent_type, read_only in (
        (query_intent_rows, "query", True),
        (control_intent_rows, "control", False),
    ):
        for row in source:
            if not isinstance(row, dict):
                continue
            examples = row.get("examples") if isinstance(row.get("examples"), list) else []
            rows.append({
                "schema": "smart_center.nl_intent_example.v1",
                "kind": "nl_intent_example",
                "intent_type": intent_type,
                "source_schema": row.get("schema") or "",
                "intent": row.get("intent") or "",
                "allowed": bool(row.get("allowed", True)),
                "read_only": bool(row.get("read_only", read_only)),
                "risk": row.get("risk") or ("low" if read_only else "normal"),
                "requires_confirmation": bool(row.get("requires_confirmation", not read_only)),
                "examples": examples,
                "api": row.get("api") if isinstance(row.get("api"), list) else [],
                "expected": row.get("expected") if isinstance(row.get("expected"), dict) else {},
                "answer": row.get("answer") or "",
                "guidance": row.get("guidance") or "",
                "routing_contract": (
                    "查询类进入只读 API/RAG，不受飞书控制开关限制。"
                    if read_only
                    else "控制类先生成受控提案，再走飞书控制开关、权限、确认、审计和中控 API 执行链路。"
                ),
            })
    return rows


def _local_model_control_permission(command):
    command_type = str((command or {}).get("type") or "").strip()
    return LOCAL_MODEL_CONTROL_PERMISSIONS.get(command_type, "local_model.control")


def _user_can_execute_local_model_control(command):
    user = get_current_user()
    permission = _local_model_control_permission(command)
    if not has_permission(user.role, permission, user.permissions):
        return False, permission, "当前账号没有对应设备控制权限"
    state = resolve_permission_grant(user, permission)
    if not state.get("allowed", False):
        return False, permission, "当前时段不允许执行该控制"
    return True, permission, ""


def _summarize_control_command(command):
    if not isinstance(command, dict):
        return {}
    command_type = str(command.get("type") or "")
    confidence = str(command.get("confidence") or "high")
    inferred = confidence in INFERRED_CONTROL_CONFIDENCE
    high_risk = command_type in HIGH_RISK_CONTROL_TYPES or str(command.get("risk") or "") == "high"
    return {
        "type": command_type,
        "risk": command.get("risk") or ("high" if high_risk else "normal"),
        "label": command.get("label") or "设备",
        "action": command.get("action") or "",
        "action_text": _format_control_action(str(command.get("action") or "")),
        "path": command.get("path") or "",
        "method": command.get("method") or "POST",
        "payload": command.get("payload") or {},
        "confidence": confidence,
        "inference_reason": command.get("inference_reason") or "",
        "requires_confirmation": bool(high_risk or inferred),
        "permission": _local_model_control_permission(command),
    }


def _store_local_model_pending_control(command, source_text):
    token = uuid.uuid4().hex
    now = time.time()
    LOCAL_MODEL_PENDING_CONTROLS[token] = {
        "command": command,
        "source_text": source_text,
        "created_at": now,
        "expires_at": now + LOCAL_MODEL_PENDING_TTL_SEC,
        "user": get_current_user().username,
    }
    if len(LOCAL_MODEL_PENDING_CONTROLS) > 100:
        expired = [key for key, row in LOCAL_MODEL_PENDING_CONTROLS.items() if now > float(row.get("expires_at") or 0)]
        for key in expired:
            LOCAL_MODEL_PENDING_CONTROLS.pop(key, None)
    return token


def _smart_center_self_base_url():
    configured = str(CONFIG.get("smart_center_base_url") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.host_url or "http://127.0.0.1:6899").strip().rstrip("/")


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


def _extract_server_machine_records():
    rows = []
    machines = []
    try:
        from api.server import get_cached_machine_payload  # local import avoids coupling normal page load to server monitor
        machines = [item for item in (get_cached_machine_payload(force=True) or []) if isinstance(item, dict)]
    except Exception:
        machines = []
    if machines:
        return [_machine_payload_to_training_record(machine, index) for index, machine in enumerate(machines)]
    return _extract_server_machine_records_from_db()


def _machine_payload_to_training_record(machine, index=0):
    status = _redact(machine.get("status") if isinstance(machine.get("status"), dict) else {})
    agent = machine.get("agent_status") if isinstance(machine.get("agent_status"), dict) else {}
    if not agent and isinstance(status.get("agent"), dict):
        agent = status.get("agent")
    diagnostic = _redact(machine.get("diagnostic") if isinstance(machine.get("diagnostic"), dict) else {})
    gpu_list = status.get("gpu_list") if isinstance(status.get("gpu_list"), list) else []
    storage_summary = status.get("storage_summary") if isinstance(status.get("storage_summary"), dict) else {}
    os_info = status.get("os_info") if isinstance(status.get("os_info"), dict) else {}
    network_primary = status.get("network_primary") if isinstance(status.get("network_primary"), dict) else {}
    name = machine.get("custom_name") or machine.get("hostname") or machine.get("ip") or machine.get("mac") or f"server_{index + 1}"
    return {
        "schema": "smart_center.training.v1",
        "kind": "device",
        "source_section": "server_machines",
        "device_type": "服务器/主机",
        "device_id": machine.get("mac") or f"server_{index + 1}",
        "name": name,
        "hostname": machine.get("hostname") or "",
        "custom_name": machine.get("custom_name") or "",
        "asset_group": machine.get("asset_group") or "未分组",
        "protocol": "Smart Center Agent",
        "host": machine.get("ip") or network_primary.get("adapter_ip") or "",
        "port": "",
        "enabled": True,
        "is_online": bool(machine.get("is_online")),
        "last_online": machine.get("last_online") or "",
        "agent_version": agent.get("version") or "",
        "diagnostic_level": diagnostic.get("level") or "",
        "diagnostic_summary": diagnostic.get("summary") or "",
        "os": os_info.get("name") or os_info.get("id") or "",
        "metrics": {
            "cpu_percent": status.get("cpu_percent"),
            "mem_percent": status.get("mem_percent"),
            "disk_percent": status.get("disk_percent"),
            "gpu_count": len(gpu_list),
            "gpu_names": [str(item.get("name") or "") for item in gpu_list if isinstance(item, dict)][:8],
            "storage_disk_count": storage_summary.get("disk_count"),
        },
        "raw": _redact(machine),
    }


def _extract_server_machine_records_from_db():
    rows = []
    if not Path(DB_FILE).exists():
        return rows
    try:
        conn = sqlite3.connect(str(DB_FILE))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT mac, hostname, ip, last_online, data, is_manual, custom_name,
                   sort_order, remark, card_size, asset_group
            FROM machines
            ORDER BY sort_order ASC, mac ASC
            """
        )
        db_rows = cursor.fetchall()
    except Exception:
        return rows
    finally:
        try:
            conn.close()
        except Exception:
            pass

    for index, row in enumerate(db_rows):
        raw_status = {}
        try:
            raw_status = json.loads(row["data"] or "{}")
        except Exception:
            raw_status = {}
        if not isinstance(raw_status, dict):
            raw_status = {}
        machine = {
            "mac": row["mac"],
            "hostname": row["hostname"],
            "ip": row["ip"],
            "last_online": row["last_online"],
            "custom_name": row["custom_name"],
            "sort_order": row["sort_order"],
            "remark": row["remark"],
            "card_size": row["card_size"],
            "asset_group": row["asset_group"] or "未分组",
            "status": raw_status,
        }
        rows.append(_machine_payload_to_training_record(machine, index))
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
    elif section == "server_machines":
        caps.extend(["服务器在线状态查询", "CPU/内存/磁盘/GPU指标读取", "Agent版本与运行诊断", "按机房/厅/资产组检索"])
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
    if section == "server_machines":
        deps.append("依赖 Smart Center Agent 上报、节点网络可达性和 monitor.db 运行快照")
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
            "summary": "本地模型已经允许识别和发起控制意图，但真实控制必须走中控现有 API、权限、审计和确认链路。强电断电、时序电源关闭、服务器关机/重启、场景批量联动、自动化规则修改都必须二次确认；不确定目标时只给推断并等待人工判断。",
            "facts": {
                "control_enabled": True,
                "execution_boundary": "Smart Center API / Feishu confirmation flow",
                "high_risk_actions": ["power_off", "sequencer_off", "server_shutdown", "server_restart", "scene_run", "automation_edit"],
            },
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
    top_categories_text = ", ".join(f"{x['name']}({x['count']})" for x in _top_items(category_counts, 5)) or "暂无"
    return [{
        "schema": "smart_center.training.v1",
        "kind": "insight",
        "insight_type": "log_pattern",
        "title": "日志模式摘要",
        "summary": f"本次纳入 {len(log_rows)} 条日志。高频模块：{top_categories_text}。",
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


def _build_server_machine_insights(device_rows):
    server_rows = [row for row in device_rows if row.get("source_section") == "server_machines"]
    if not server_rows:
        return []
    groups = {}
    gpu_inventory = {}
    for row in server_rows:
        group = str(row.get("asset_group") or "未分组").strip() or "未分组"
        groups.setdefault(group, []).append(row)
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        for gpu_name in metrics.get("gpu_names") or []:
            name = str(gpu_name or "").strip()
            if name:
                gpu_inventory[name] = gpu_inventory.get(name, 0) + 1
    group_summary = {
        group: {
            "total": len(items),
            "sample_machines": [
                {
                    "name": item.get("name"),
                    "host": item.get("host"),
                    "hostname": item.get("hostname"),
                    "last_online": item.get("last_online"),
                }
                for item in items[:20]
            ],
        }
        for group, items in sorted(groups.items(), key=lambda item: item[0])
    }
    rows = [{
        "schema": "smart_center.training.v1",
        "kind": "insight",
        "insight_type": "server_inventory",
        "title": "服务器资产分组总览",
        "summary": (
            f"本次导出包含 {len(server_rows)} 台服务器/主机，分布在 "
            + "、".join(f"{group}{len(items)}台" for group, items in sorted(groups.items(), key=lambda item: item[0]))
            + "。自然语言查询服务器时必须先检索全部分组，不应只返回第一个机房。"
        ),
        "facts": {
            "total": len(server_rows),
            "groups": group_summary,
            "gpu_inventory": _top_items(dict(sorted(gpu_inventory.items(), key=lambda item: (-item[1], item[0]))), 20),
        },
        "training_hint": "回答“服务器状态、机房服务器、1号厅服务器、2号厅离线机器、node-120 CPU、GPU温度”等问题时，按 asset_group、custom_name、hostname、IP 检索，先给分组统计，再给匹配机器明细。",
    }]
    for group, items in sorted(groups.items(), key=lambda item: item[0]):
        rows.append({
            "schema": "smart_center.training.v1",
            "kind": "insight",
            "insight_type": "server_group_inventory",
            "title": f"服务器分组：{group}",
            "summary": f"{group} 当前登记 {len(items)} 台服务器/主机。可按中文分组名、主机名、自定义名或 IP 查询。",
            "facts": {
                "group": group,
                "total": len(items),
                "machines": [
                    {
                        "name": item.get("name"),
                        "host": item.get("host"),
                        "hostname": item.get("hostname"),
                        "custom_name": item.get("custom_name"),
                        "last_online": item.get("last_online"),
                        "metrics": item.get("metrics"),
                    }
                    for item in items[:30]
                ],
            },
            "training_hint": f"用户问“{group}服务器/主机/机器”时，只过滤 asset_group={group} 的记录；用户问总体服务器时需要同时覆盖其他分组。",
        })
    return rows


def _build_qa_insights(device_rows):
    samples = [
        ("列出所有 TCP/网络协议设备", "按 devices 中 host 非空或 protocol/comm_mode 为 TCP/UDP/HTTP/SNMP/Modbus TCP 的记录筛选，并返回名称、地址、端口、协议。"),
        ("某设备离线应该先查什么", "先查网络可达、协议参数、桥接服务、最近事件日志，再区分设备断电、通信失败和配置错误。"),
        ("服务器状态为什么不能只看第一个机房", "服务器资产按 asset_group 分布在多个分组，应先汇总全部分组，再按用户提到的机房、1号厅、2号厅、机房-马勇、主机名或 IP 过滤。"),
        ("node-120 CPU 和 GPU 怎么查", "在 server_machines 里按 custom_name/hostname/IP 匹配 node-120，再读取 metrics.cpu_percent 和 gpu_names/GPU 指标。"),
        ("投影现在是断电还是关机", "先看供电回路/时序电源/电柜状态，再看电流采集和投影协议回包，不能只凭单一总功率判断。"),
        ("空调米家可控但中控离线", "优先查 Home Assistant/miio 桥接、实体映射、token、局域网连通和轮询日志。"),
        ("哪些操作需要谨慎", "强电、时序电源、投影关机、场景联动和自动化修改都需要人工确认。"),
        ("软件播控素材传输如何排障", "先确认 tab 切换不会自动全选内容数据；素材在播放窗口内缩放并支持偏移；HVC/H.265 以外素材和警告素材优先转码优化；警告提示需要能定位素材位置；锁定屏幕会退出转码优化。"),
        ("软件播控带宽如何限制", "按现场网络实测设置传输带宽限制，避免带宽占满导致卡顿或通讯异常；无线跑满且有线空闲时，要设置传输优先级、指定传输和暂停传输，尽量让主控统一调度。"),
        ("软件播控日志如何采集", "日志应从主控统一提取或由配套工具采集，自动记录主控与显示端时间差；显示端运行后尽量无需远程，独立机器状态管理要同时监控带宽机器状态和软件状态。"),
        ("显示管理新增屏幕卡住怎么办", "新增屏幕后如果显示管理卡住不能修改，先做一次小修改再保存；复制节目页不带窗口名称，节目传输建议按选中素材或节目节点右键更新，避免拖动触发大范围传输。"),
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


def _infer_control_actions(alias_row):
    hint = str(alias_row.get("action_hint") or "").strip().lower()
    module = str(alias_row.get("module") or "").strip()
    device_type = str(alias_row.get("device_type") or "").strip()
    if hint:
        return [part for part in hint.replace(",", "/").split("/") if part]
    if module in {"power", "light", "sequencer", "hvac", "projector"}:
        return ["on", "off"]
    if module == "screen":
        return ["up", "down", "stop"]
    if module == "door":
        return ["open", "close", "stop"]
    if module == "server":
        return ["wake", "shutdown", "restart"]
    if device_type == "custom_device" or module == "custom":
        return ["execute_configured_command"]
    return []


def _control_risk(alias_row):
    risk = str(alias_row.get("risk") or "normal").strip().lower()
    module = str(alias_row.get("module") or "").strip()
    device_type = str(alias_row.get("device_type") or "").strip()
    if risk in {"high", "高"} or module in {"power", "sequencer"} or device_type in {"cabinet", "cabinet_channel"}:
        return "high"
    if module in {"server", "ups"}:
        return "high"
    if module in {"projector", "screen", "hvac", "door", "custom"}:
        return "medium"
    return "normal"


def _build_device_inventory_rows(device_rows, alias_rows):
    aliases_by_id = {}
    for row in alias_rows:
        row_id = str(row.get("device_id") or "")
        if not row_id:
            continue
        aliases_by_id.setdefault(row_id, set()).update(str(item) for item in (row.get("aliases") or []) if item)
    inventory = []
    for row in device_rows:
        row_id = str(row.get("device_id") or "")
        inventory.append({
            "schema": "smart_center.device_inventory.v1",
            "kind": "device_inventory",
            "device_id": row_id,
            "name": row.get("name") or row_id,
            "source_section": row.get("source_section") or "",
            "device_type": row.get("device_type") or "",
            "protocol": row.get("protocol") or "",
            "host": row.get("host") or "",
            "port": row.get("port") or "",
            "enabled": row.get("enabled"),
            "is_online": row.get("is_online"),
            "aliases": sorted(aliases_by_id.get(row_id, set()))[:80],
            "capabilities": _device_capabilities(row),
            "dependencies": _device_dependencies(row),
            "model_use": "自然语言查询先按 aliases/name/source_section/device_type 匹配，再读取实时 API 或运行快照；不要仅凭名称执行控制。",
        })
    return inventory


def _build_control_capability_rows(alias_rows):
    rows = []
    for alias in alias_rows:
        if not alias.get("control_capability"):
            continue
        module = str(alias.get("module") or "").strip()
        device_type = str(alias.get("device_type") or "").strip()
        risk = _control_risk(alias)
        rows.append({
            "schema": "smart_center.control_capability.v1",
            "kind": "control_capability",
            "module": module,
            "device_type": device_type,
            "device_id": alias.get("device_id") or "",
            "name": alias.get("name") or alias.get("device_id") or "",
            "aliases": alias.get("aliases") or [],
            "actions": _infer_control_actions(alias),
            "risk": risk,
            "requires_confirmation": True,
            "query_allowed_when_feishu_control_disabled": True,
            "control_blocked_when_feishu_control_disabled": True,
            "safety_chain": [
                "natural_language_parse",
                "alias_match",
                "deterministic_router",
                "permission_check",
                "audit_trace",
                "confirmation",
                "smart_center_api_execute",
                "state_readback_when_available",
            ],
            "model_use": "模型只能输出控制提案 JSON；后端必须重新按该能力记录和确定性路由校验后才可进入确认/执行。",
        })
    return rows


def _build_runtime_system_map(config, device_rows, alias_rows, protocol_rows, log_rows, insight_rows, control_capability_rows, files, code_knowledge=None):
    sections = _count_by(device_rows, "source_section")
    control_by_module = _count_by(control_capability_rows, "module")
    query_only_modules = sorted(
        {
            str(row.get("module") or "")
            for row in alias_rows
            if row.get("query_capability") and not row.get("control_capability")
        }
    )
    code_counts = {}
    code_files = {}
    if isinstance(code_knowledge, dict):
        code_counts = code_knowledge.get("counts") if isinstance(code_knowledge.get("counts"), dict) else {}
        code_files = code_knowledge.get("files") if isinstance(code_knowledge.get("files"), dict) else {}
    return {
        "schema": "smart_center.system_map.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": "Smart Center 演播中控",
        "purpose": "给本地模型和飞书自然语言提供稳定的系统目录：模块、设备、查询能力、控制能力、风险边界和知识文件入口。",
        "counts": {
            "devices": len(device_rows),
            "aliases": len(alias_rows),
            "protocol_records": len(protocol_rows),
            "logs": len(log_rows),
            "insights": len(insight_rows),
            "control_capabilities": len(control_capability_rows),
            **{f"code_{key}": value for key, value in code_counts.items()},
        },
        "device_sections": sections,
        "control_modules": control_by_module,
        "query_only_modules": query_only_modules,
        "natural_language_contract": {
            "query": "查询类指令始终允许进入只读 API 或 RAG 检索，不受飞书控制开关限制。",
            "control": "控制类指令必须受飞书控制开关、权限、确认策略和审计链路约束；关闭时只解析不执行。",
            "model_output": {
                "intent": "query | control_request | clarify",
                "module": "power/light/hvac/projector/screen/sequencer/server/custom/door/ups/env/snmp/...",
                "target": "用户提到或别名匹配出的设备/通道",
                "action": "只允许后端白名单动作",
                "confidence": "0-1",
                "evidence": "引用 device_inventory/control_capabilities/nl_intent_examples/insights/code_system_map",
            },
        },
        "recommended_learning_order": [
            "system_map_*.json",
            "device_inventory_*.jsonl",
            "control_capabilities_*.jsonl",
            "nl_intent_examples_*.jsonl",
            "device_aliases_*.jsonl",
            "insights_*.jsonl",
            "code_system_map_*.json",
            "module_cards_*.jsonl",
            "code_knowledge_*.jsonl",
            "full_code_context_*.jsonl",
        ],
        "high_context_policy": {
            "enabled": True,
            "target_machine": "3090 本地模型机器",
            "recommended_context_len": 131072,
            "max_supported_config": 262144,
            "refresh_mode": "定期读取脱敏 full_code_context，生成系统摘要/索引；不直接记忆密钥、不直接执行控制。",
        },
        "files": {name: str(path) for name, path in files.items()},
        "code_files": code_files,
        "config_source": str(CONFIG_FILE),
        "safety_boundary": "模型理解和检索不是执行权限。所有真实设备动作必须回到 Smart Center 后端执行链路。",
        "config_modules": sorted(str(key) for key in config.keys() if isinstance(key, str))[:300],
    }


def build_insights(config, device_rows, protocol_rows, log_rows):
    insight_rows = []
    insight_rows.extend(_build_device_insights(device_rows))
    insight_rows.extend(_build_protocol_insights(device_rows, protocol_rows))
    insight_rows.extend(_build_rule_insights(config))
    insight_rows.extend(_build_log_insights(log_rows))
    insight_rows.extend(_build_server_machine_insights(device_rows))
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
            "可识别和发起受控控制意图；真实动作必须走中控权限、审计和二次确认链路",
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
    server_machine_rows = _extract_server_machine_records()
    device_rows.extend(server_machine_rows)
    device_alias_rows = build_device_alias_rows(config)
    protocol_rows = _extract_protocol_records(config)
    log_rows = _extract_log_records(int(export_cfg.get("recent_log_limit", 500))) if export_cfg.get("include_logs", True) else []
    insight_rows, daily_summary = build_insights(config, device_rows, protocol_rows, log_rows)
    query_intent_rows = _read_query_intent_rows()
    control_intent_rows = _read_control_intent_rows()
    nl_intent_example_rows = _build_nl_intent_example_rows(query_intent_rows, control_intent_rows)
    device_inventory_rows = _build_device_inventory_rows(device_rows, device_alias_rows)
    control_capability_rows = _build_control_capability_rows(device_alias_rows)
    instruction_rows = [
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据中控配置说明指定设备的协议、地址、用途和可用控制能力。",
            "input": {"device_inventory_count": len(device_rows), "server_machine_count": len(server_machine_rows)},
            "output": "已归一化设备清单，可按 source_section、device_type、device_id 检索，并可结合 insights 中的 device_profile 回答。",
        },
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据运行时服务器资产快照回答服务器状态、分组、离线、CPU、内存、磁盘和 GPU 查询。",
            "input": {"server_machine_count": len(server_machine_rows)},
            "output": "server_machines 记录来自 monitor.db，可按 asset_group、custom_name、hostname、IP、mac 检索；回答总体服务器时先汇总全部分组，回答指定分组时只返回匹配分组。",
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
            "output": "先给结论，再列证据，最后给排查或操作建议；涉及真实控制动作时允许生成受控控制意图，但必须标注风险、目标、动作和确认策略。",
        },
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据自然语言控制请求识别设备、动作、风险和确认策略。",
            "input": {"control_enabled": True},
            "output": "普通低风险设备可进入受控执行链路；强电柜、时序电源、服务器关机/重启等高风险动作必须二次确认；目标不明确时只返回推断和候选项，等待人工判断。",
        },
    ]
    files = {
        "devices": out_dir / f"devices_{stamp}.jsonl",
        "device_inventory": out_dir / f"device_inventory_{stamp}.jsonl",
        "device_aliases": out_dir / f"device_aliases_{stamp}.jsonl",
        "control_capabilities": out_dir / f"control_capabilities_{stamp}.jsonl",
        "protocols": out_dir / f"protocols_{stamp}.jsonl",
        "logs": out_dir / f"logs_{stamp}.jsonl",
        "instructions": out_dir / f"instructions_{stamp}.jsonl",
        "query_intents": out_dir / f"query_intents_{stamp}.jsonl",
        "control_intents": out_dir / f"control_intents_{stamp}.jsonl",
        "nl_intent_examples": out_dir / f"nl_intent_examples_{stamp}.jsonl",
        "insights": out_dir / f"insights_{stamp}.jsonl",
        "daily_summary": out_dir / f"daily_summary_{stamp}.json",
        "system_map": out_dir / f"system_map_{stamp}.json",
        "knowledge": out_dir / f"knowledge_{stamp}.json",
    }
    _jsonl_write(files["devices"], device_rows)
    _jsonl_write(files["device_inventory"], device_inventory_rows)
    _jsonl_write(files["device_aliases"], device_alias_rows)
    _jsonl_write(files["control_capabilities"], control_capability_rows)
    _jsonl_write(files["protocols"], protocol_rows)
    _jsonl_write(files["logs"], log_rows)
    _jsonl_write(files["instructions"], instruction_rows)
    _jsonl_write(files["query_intents"], query_intent_rows)
    _jsonl_write(files["control_intents"], control_intent_rows)
    _jsonl_write(files["nl_intent_examples"], nl_intent_example_rows)
    _jsonl_write(files["insights"], insight_rows)
    files["daily_summary"].write_text(json.dumps(daily_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    system_map = _build_runtime_system_map(
        config,
        device_rows,
        device_alias_rows,
        protocol_rows,
        log_rows,
        insight_rows,
        control_capability_rows,
        files,
    )
    files["system_map"].write_text(json.dumps(system_map, ensure_ascii=False, indent=2), encoding="utf-8")
    knowledge = {
        "schema": "smart_center.training.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config_source": str(CONFIG_FILE),
        "model_target": {k: v for k, v in model_cfg.items() if k != "api_key"},
        "counts": {
            "devices": len(device_rows),
            "device_inventory": len(device_inventory_rows),
            "device_aliases": len(device_alias_rows),
            "server_machines": len(server_machine_rows),
            "control_capabilities": len(control_capability_rows),
            "protocol_records": len(protocol_rows),
            "logs": len(log_rows),
            "instructions": len(instruction_rows),
            "query_intents": len(query_intent_rows),
            "control_intents": len(control_intent_rows),
            "nl_intent_examples": len(nl_intent_example_rows),
            "insights": len(insight_rows),
        },
        "device_sections": DEVICE_SECTIONS,
        "server_machine_groups": _count_by(server_machine_rows, "asset_group"),
        "alias_modules": _count_by(device_alias_rows, "module"),
        "alias_device_types": _count_by(device_alias_rows, "device_type"),
        "control_modules": _count_by(control_capability_rows, "module"),
        "insight_types": _count_by(insight_rows, "insight_type"),
        "daily_summary": daily_summary,
        "system_map": system_map,
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


def _latest_training_file(prefix, suffix=""):
    matches = [
        path for path in _training_dir().glob(f"{prefix}_*{suffix}")
        if path.is_file()
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _count_jsonl_rows(path):
    if not path or not path.is_file():
        return 0
    count = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.strip():
                    count += 1
    except Exception:
        return 0
    return count


def _file_status_payload(prefix, label, suffix="", *, count_jsonl=False):
    path = _latest_training_file(prefix, suffix)
    if not path:
        return {"label": label, "prefix": prefix, "exists": False, "name": "", "updated_at": "", "size": 0, "count": None}
    count = _count_jsonl_rows(path) if count_jsonl else None
    return {
        "label": label,
        "prefix": prefix,
        "exists": True,
        "name": path.name,
        "path": str(path),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "size": path.stat().st_size,
        "count": count,
    }


def _read_latest_json(prefix):
    path = _latest_training_file(prefix, ".json")
    if not path:
        return {}
    payload = _read_json_file(path, {})
    return payload if isinstance(payload, dict) else {}


def build_knowledge_status():
    cfg = normalize_local_model_config(CONFIG.get("local_model"), keep_secret=False)
    system_map = _read_latest_json("system_map")
    code_map = _read_latest_json("code_system_map")
    summary = _read_latest_json("system_summary")
    items = [
        _file_status_payload("system_map", "系统地图", ".json"),
        _file_status_payload("device_inventory", "设备清单", ".jsonl", count_jsonl=True),
        _file_status_payload("control_capabilities", "控制能力", ".jsonl", count_jsonl=True),
        _file_status_payload("nl_intent_examples", "自然语言意图样例", ".jsonl", count_jsonl=True),
        _file_status_payload("device_aliases", "自然语言别名", ".jsonl", count_jsonl=True),
        _file_status_payload("insights", "运行洞察", ".jsonl", count_jsonl=True),
        _file_status_payload("code_system_map", "代码系统地图", ".json"),
        _file_status_payload("module_cards", "模块卡片", ".jsonl", count_jsonl=True),
        _file_status_payload("code_knowledge", "代码知识", ".jsonl", count_jsonl=True),
        _file_status_payload("full_code_context", "高上下文源码", ".jsonl", count_jsonl=True),
        _file_status_payload("system_summary", "模型系统摘要", ".json"),
    ]
    latest_times = [item["updated_at"] for item in items if item.get("updated_at")]
    export_cfg = cfg.get("training_export") if isinstance(cfg.get("training_export"), dict) else {}
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "latest_updated_at": max(latest_times) if latest_times else "",
        "model": cfg.get("model"),
        "max_model_len": cfg.get("max_model_len"),
        "recommended_context_len": export_cfg.get("recommended_context_len"),
        "refresh_strategy": export_cfg.get("refresh_strategy"),
        "include_full_code_context": export_cfg.get("include_full_code_context", True),
        "items": items,
        "system_counts": system_map.get("counts") if isinstance(system_map.get("counts"), dict) else {},
        "code_counts": code_map.get("counts") if isinstance(code_map.get("counts"), dict) else {},
        "last_summary": {
            "generated_at": summary.get("generated_at") or "",
            "model": summary.get("model") or "",
            "prompt_chars": summary.get("prompt_chars") or 0,
            "elapsed_ms": summary.get("elapsed_ms") or 0,
        },
        "learning_order": system_map.get("recommended_learning_order") if isinstance(system_map.get("recommended_learning_order"), list) else [],
        "safety_boundary": "知识刷新和高上下文阅读只生成摘要/索引；飞书或本地模型控制仍受开关、权限、确认和审计链路约束。",
    }


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
    trace = NaturalLanguageTrace(
        source="local_model",
        text=prompt or (normalized_messages[-1].get("content") if normalized_messages else ""),
        actor={"user": get_current_user().username, "role": get_current_user().role},
        policy=cfg.get("natural_language"),
    )
    trace.add_step(
        "classify",
        "进入普通问答",
        detail="未命中本地控制 dry-run，转交本地模型/知识代理回答。",
        data={"message_count": len(normalized_messages), "model": cfg["model"]},
    )
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
        trace.add_step("model", "模型完成回答", data={"elapsed_ms": result.get("elapsed_ms")}, ok=True)
        process = trace.finish(intent="query", outcome="answered", reply=answer)
        return jsonify({"ok": True, "answer": answer, "elapsed_ms": result.get("elapsed_ms"), "model": cfg["model"], "raw": data, "process": process})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        trace.add_step("model", "模型 HTTP 调用失败", detail=detail, ok=False)
        process = trace.finish(intent="query", outcome="model_http_error", reply=detail)
        return jsonify({"ok": False, "error": "http_error", "status": exc.code, "msg": detail, "process": process}), 502
    except Exception as exc:
        trace.add_step("model", "模型调用失败", detail=str(exc), ok=False)
        process = trace.finish(intent="query", outcome="model_failed", reply=str(exc))
        return jsonify({"ok": False, "error": "request_failed", "msg": str(exc), "process": process}), 502


@bp.route("/api/local-model/control/dry-run", methods=["POST"])
@require_permission("local_model.control")
def api_local_model_control_dry_run():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or payload.get("prompt") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty_text", "msg": "请输入控制内容"}), 400
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    trace = NaturalLanguageTrace(
        source="local_model",
        text=text,
        actor={"user": get_current_user().username, "role": get_current_user().role},
        policy=cfg.get("natural_language"),
    )
    action = _control_action_from_text(text)
    if not _is_control_request(text):
        trace.add_step("classify", "判断为普通查询/对话", data={"recognized_action": action}, ok=True)
        process = trace.finish(intent="query", outcome="not_control", reply="这句话不像明确控制请求。", record=False)
        return jsonify({
            "ok": True,
            "dry_run": True,
            "is_control_request": False,
            "recognized_action": action,
            "msg": "这句话不像明确控制请求，可以继续补充设备和动作。",
            "process": process,
        })
    client = LocalSmartCenterClient(_smart_center_self_base_url())
    translator = LocalModelControlTranslator(cfg["base_url"], cfg["model"], cfg["timeout_sec"]) if cfg.get("enabled") else None
    trace.add_step(
        "classify",
        "识别为控制请求",
        data={"recognized_action": action, "model_translator_enabled": bool(translator)},
        ok=True,
    )
    command = client.resolve_control_command_with_translator(text, translator=translator)
    if not command:
        trace.add_step("route", "未匹配到可执行设备", ok=False)
        process = trace.finish(intent="control", outcome="unmatched", reply="识别到控制请求，但没有明确匹配到设备。")
        return jsonify({
            "ok": True,
            "dry_run": True,
            "is_control_request": True,
            "recognized_action": action,
            "matched": False,
            "msg": "识别到控制请求，但没有明确匹配到设备。",
            "process": process,
        })
    if command.get("type") == "error":
        trace.add_step("route", "安全路由拒绝控制", detail=command.get("message") or "", data=summarize_command_for_process(command), ok=False)
        process = trace.finish(intent="control", outcome="route_rejected", reply=command.get("message") or "控制请求无法执行。", command=command)
        return jsonify({
            "ok": True,
            "dry_run": True,
            "is_control_request": True,
            "matched": False,
            "recognized_action": action,
            "command": _summarize_control_command(command),
            "msg": command.get("message") or "控制请求无法执行。",
            "process": process,
        })
    allowed, permission, reason = _user_can_execute_local_model_control(command)
    summary = _summarize_control_command(command)
    policy = describe_control_policy(
        command,
        high_risk_types=HIGH_RISK_CONTROL_TYPES,
        inferred_confidences=INFERRED_CONTROL_CONFIDENCE,
        require_confirmation=True,
    )
    trace.add_step("route", "控制目标已解析", data={"command": summary, "control_policy": policy}, ok=True)
    trace.add_step(
        "permission",
        "本地账号权限校验",
        detail=reason or "允许进入待确认",
        data={"permission": permission},
        ok=allowed,
    )
    token = ""
    if allowed:
        token = _store_local_model_pending_control(command, text)
    outcome = "pending_confirmation" if token else "permission_denied"
    reply = "已解析控制意图，未执行真实设备控制。" if token else (reason or "当前账号没有对应设备控制权限")
    process = trace.finish(intent="control", outcome=outcome, reply=reply, command=command, extra={"pending_token_created": bool(token)})
    return jsonify({
        "ok": True,
        "dry_run": True,
        "is_control_request": True,
        "matched": True,
        "recognized_action": action,
        "allowed": allowed,
        "permission": permission,
        "deny_reason": reason,
        "pending_token": token,
        "command": summary,
        "msg": "已解析控制意图，未执行真实设备控制。",
        "process": process,
    })


@bp.route("/api/local-model/control/confirm", methods=["POST"])
@require_permission("local_model.control")
def api_local_model_control_confirm():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("pending_token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "missing_token", "msg": "缺少待确认控制 token"}), 400
    pending = LOCAL_MODEL_PENDING_CONTROLS.pop(token, None)
    if not pending:
        return jsonify({"ok": False, "error": "not_found", "msg": "待确认控制不存在或已被处理"}), 404
    if time.time() > float(pending.get("expires_at") or 0):
        return jsonify({"ok": False, "error": "expired", "msg": "待确认控制已过期，请重新解析"}), 409
    command = pending.get("command")
    if not isinstance(command, dict):
        return jsonify({"ok": False, "error": "invalid_command", "msg": "待确认控制格式无效"}), 400
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    trace = NaturalLanguageTrace(
        source="local_model",
        text=str(pending.get("source_text") or ""),
        actor={"user": get_current_user().username, "role": get_current_user().role},
        policy=cfg.get("natural_language"),
    )
    trace.add_step("confirm", "收到本地页面确认", data={"pending_token": token, "command": _summarize_control_command(command)}, ok=True)
    allowed, permission, reason = _user_can_execute_local_model_control(command)
    if not allowed:
        trace.add_step("permission", "确认时权限拒绝", detail=reason, data={"permission": permission}, ok=False)
        process = trace.finish(intent="control", outcome="permission_denied", reply=reason, command=command)
        return jsonify({"ok": False, "error": "permission_denied", "permission": permission, "msg": reason, "process": process}), 403
    client = LocalSmartCenterClient(_smart_center_self_base_url())
    result_text = client.execute_control_command(command)
    trace.add_step("execute", "已调用中控执行链路", detail=result_text, data={"permission": permission}, ok="成功" in result_text)
    process = trace.finish(intent="control", outcome="executed", reply=result_text, command=command)
    return jsonify({"ok": True, "executed": True, "permission": permission, "result": result_text, "command": _summarize_control_command(command), "process": process})


@bp.route("/api/local-model/nl-process-log")
@require_permission("local_model.view")
def api_local_model_nl_process_log():
    try:
        limit = int(request.args.get("limit", "50") or 50)
    except Exception:
        limit = 50
    source = str(request.args.get("source") or "").strip()
    return jsonify({"ok": True, "items": list_natural_language_events(limit, source=source)})


@bp.route("/api/local-model/export-training", methods=["POST"])
@require_permission("system.config")
def api_local_model_export_training():
    payload = build_training_export()
    cfg = normalize_local_model_config(CONFIG.get("local_model"))
    export_cfg = cfg.get("training_export") if isinstance(cfg.get("training_export"), dict) else {}
    if not export_cfg.get("include_code_knowledge", True):
        return jsonify(payload)
    try:
        from scripts.export_code_knowledge import build_code_knowledge_export_with_options

        payload["code_knowledge"] = build_code_knowledge_export_with_options(include_full_context=export_cfg.get("include_full_code_context", True))
    except Exception as exc:
        payload["code_knowledge"] = {"ok": False, "error": str(exc)}
    return jsonify(payload)


@bp.route("/api/local-model/training-files")
@require_permission("local_model.view")
def api_local_model_training_files():
    return jsonify({"ok": True, "files": _list_training_files()})


@bp.route("/api/local-model/knowledge-status")
@require_permission("local_model.view")
def api_local_model_knowledge_status():
    return jsonify(build_knowledge_status())


@bp.route("/api/local-model/refresh-system-summary", methods=["POST"])
@require_permission("system.config")
def api_local_model_refresh_system_summary():
    try:
        payload = request.get_json(silent=True) if request.is_json else {}
        max_input_chars = int((payload or {}).get("max_input_chars") or 8000)
    except Exception:
        max_input_chars = 8000
    try:
        from scripts.refresh_local_model_system_summary import build_system_summary

        summary = build_system_summary(max_input_chars=max(8000, min(max_input_chars, 240000)))
        return jsonify({"ok": True, "summary": summary})
    except Exception as exc:
        return jsonify({"ok": False, "error": "summary_failed", "msg": str(exc)}), 502


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
