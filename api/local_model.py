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
    "base_url": "http://192.168.50.122:8000/v1",
    "model": "gemma-4-26b-a4b",
    "api_key": "dummy",
    "timeout_sec": 120,
    "temperature": 0.2,
    "max_tokens": 512,
    "system_prompt": "你是演播中控系统的本地助手，回答要基于中控设备、协议、日志和运行状态。涉及真实控制动作时，先说明风险并等待人工确认。",
    "training_export": {"enabled": True, "include_logs": True, "recent_log_limit": 500},
}

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
    if isinstance(raw_config, dict):
        for key, value in raw_config.items():
            if key == "training_export" and isinstance(value, dict):
                merged["training_export"].update(value)
            else:
                merged[key] = value
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["name"] = str(merged.get("name") or DEFAULT_LOCAL_MODEL["name"]).strip() or DEFAULT_LOCAL_MODEL["name"]
    merged["provider"] = str(merged.get("provider") or DEFAULT_LOCAL_MODEL["provider"]).strip() or DEFAULT_LOCAL_MODEL["provider"]
    merged["base_url"] = str(merged.get("base_url") or DEFAULT_LOCAL_MODEL["base_url"]).strip().rstrip("/") or DEFAULT_LOCAL_MODEL["base_url"]
    merged["model"] = str(merged.get("model") or DEFAULT_LOCAL_MODEL["model"]).strip() or DEFAULT_LOCAL_MODEL["model"]
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


def build_training_export():
    config = deepcopy(CONFIG)
    model_cfg = normalize_local_model_config(config.get("local_model"))
    export_cfg = model_cfg.get("training_export", {})
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _training_dir()
    device_rows = _extract_device_records(config)
    protocol_rows = _extract_protocol_records(config)
    log_rows = _extract_log_records(int(export_cfg.get("recent_log_limit", 500))) if export_cfg.get("include_logs", True) else []
    instruction_rows = [
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据中控配置说明指定设备的协议、地址、用途和可用控制能力。",
            "input": {"device_inventory_count": len(device_rows)},
            "output": "已归一化设备清单，可按 source_section、device_type、device_id 检索。",
        },
        {
            "schema": "smart_center.training.v1",
            "kind": "instruction",
            "instruction": "根据中控事件日志判断动作来自人工、自动化、设备回报还是外部变化。",
            "input": {"event_log_count": len(log_rows)},
            "output": "event_log 记录包含 category、event_type、source、action、result、message 和脱敏 raw。",
        },
    ]
    files = {
        "devices": out_dir / f"devices_{stamp}.jsonl",
        "protocols": out_dir / f"protocols_{stamp}.jsonl",
        "logs": out_dir / f"logs_{stamp}.jsonl",
        "instructions": out_dir / f"instructions_{stamp}.jsonl",
        "knowledge": out_dir / f"knowledge_{stamp}.json",
    }
    _jsonl_write(files["devices"], device_rows)
    _jsonl_write(files["protocols"], protocol_rows)
    _jsonl_write(files["logs"], log_rows)
    _jsonl_write(files["instructions"], instruction_rows)
    knowledge = {
        "schema": "smart_center.training.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_target": {k: v for k, v in model_cfg.items() if k != "api_key"},
        "counts": {
            "devices": len(device_rows),
            "protocol_records": len(protocol_rows),
            "logs": len(log_rows),
            "instructions": len(instruction_rows),
        },
        "device_sections": DEVICE_SECTIONS,
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
    url = f"{cfg['base_url']}/models"
    try:
        result = _request_json(url, timeout=min(float(cfg.get("timeout_sec", 120)), 10), api_key=cfg.get("api_key", ""))
        models = [item.get("id") for item in result.get("data", {}).get("data", []) if isinstance(item, dict)]
        return jsonify({"ok": True, "online": True, "url": url, "model": cfg.get("model"), "models": models, "elapsed_ms": result.get("elapsed_ms")})
    except Exception as exc:
        return jsonify({"ok": False, "online": False, "url": url, "error": str(exc)})


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
