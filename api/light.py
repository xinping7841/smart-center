# AI_MODULE: lighting_api
# AI_PURPOSE: 灯光/继电器控制、状态、日志和调试工具接口。
# AI_BOUNDARY: 不在这里写具体驱动协议；协议驱动放在 drivers/light_*.py。
# AI_DATA_FLOW: 前端灯光页面 -> /api/light/status/control/logs -> LIGHT_STATUS/LIGHT_DRIVERS。
# AI_RUNTIME: 灯光页面、首页卡片、自动化规则会调用。
# AI_RISK: 高，控制会真实改变灯光/继电器输出。
# AI_COMPAT: light device id、channel、action、logs 字段需保持兼容。
# AI_SEARCH_KEYWORDS: light, relay, channel, niren, coxe, scene, log.

import time

from flask import Blueprint, jsonify, render_template_string, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from background import LIGHT_DRIVERS, LIGHT_META
from config import CONFIG, LIGHT_ONLINE, LIGHT_STATUS
from data_logger import add_log, load_logs
from event_logger import record_event, record_state_change
from runtime.automation import execute_scene
from log_config import get_logger
_log = get_logger(__name__)

bp = Blueprint("light", __name__)
LIGHT_LOGS_CACHE = {"expires_at": 0.0, "payload": []}
LIGHT_LOGS_TTL_SEC = 2.0
LIGHT_LOG_KEYWORDS = (
    "[灯光]",
    "[状态变化][灯光]",
    "灯光",
    "户外灯",
    "庭院灯",
    "开灯",
    "关灯",
)


def _channel_display_name(channel_cfg, fallback):
    row = channel_cfg if isinstance(channel_cfg, dict) else {}
    name = str(row.get("name") or "").strip()
    remark = str(row.get("remark") or row.get("usage") or row.get("description") or "").strip()
    if name and remark and remark not in name:
        return f"{name}({remark})"
    return name or remark or fallback


def _json_keyed_status_map(status_map):
    return {str(key): value for key, value in dict(status_map or {}).items()}


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "on", "open", "opened", "enable", "enabled", "yes", "y", "开", "开启", "打开"}:
            return True
        if text in {"0", "false", "off", "close", "closed", "disable", "disabled", "no", "n", "关", "关闭"}:
            return False
    return bool(value)


def _is_light_log_entry(item):
    operation = str((item or {}).get("operation") or "")
    if not operation:
        return False
    lowered = operation.lower()
    if "skipped stale schedule" in lowered:
        return False
    if any(keyword in operation for keyword in LIGHT_LOG_KEYWORDS):
        return True
    return "[light]" in lowered or "light." in lowered or "light_" in lowered


def _filter_light_logs(rows, limit=120):
    filtered = [item for item in (rows or []) if _is_light_log_entry(item)]
    try:
        limit = max(1, min(int(limit), 300))
    except Exception:
        limit = 120
    return filtered[:limit]


def _build_light_diagnostic_logs(limit=120):
    rows = []
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for cfg in CONFIG.get("light_devices", []) or []:
        dev_id = cfg.get("id")
        meta = dict((LIGHT_META.get(dev_id) or LIGHT_META.get(str(dev_id)) or {}))
        last_error = str(meta.get("last_error") or meta.get("error") or "").strip()
        online = bool(LIGHT_ONLINE.get(dev_id) or LIGHT_ONLINE.get(str(dev_id)))
        if online and not last_error:
            continue
        device_name = str(cfg.get("name") or dev_id or "灯光设备")
        checked_at = meta.get("last_checked_at") or meta.get("last_error_at") or now_iso
        failures = int(meta.get("poll_failures", 0) or 0)
        status_label = str(meta.get("status_label") or meta.get("status_text") or "离线")
        rows.append(
            {
                "time": checked_at,
                "operation": f"[灯光诊断] {device_name} {status_label}，连续失败 {failures} 次，原因：{last_error or '暂无详细错误'}",
                "status": "error" if not online else "warning",
                "device_id": str(dev_id),
                "data_source": "light_poller",
            }
        )
    return rows[:limit]

LIGHT_DEBUG_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>灯光调试面板</title>
    <style>
        body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }
        h1 { margin:0 0 20px 0; font-size:28px; }
        .toolbar { margin-bottom:20px; display:flex; gap:12px; align-items:center; }
        button { background:#2563eb; color:#fff; border:none; border-radius:8px; padding:10px 16px; cursor:pointer; font-size:14px; }
        .hint { color:#94a3b8; font-size:14px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:16px; }
        .card { background:#111827; border:1px solid #334155; border-radius:12px; padding:16px; }
        .title { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .tag { padding:4px 10px; border-radius:999px; font-size:12px; font-weight:bold; }
        .ok { background:rgba(16,185,129,.15); color:#10b981; }
        .bad { background:rgba(239,68,68,.15); color:#ef4444; }
        .meta { font-size:13px; color:#94a3b8; line-height:1.8; margin-bottom:12px; }
        .channels { display:grid; grid-template-columns:repeat(auto-fit, minmax(82px, 1fr)); gap:8px; }
        .ch { border:1px solid #334155; border-radius:8px; padding:8px; text-align:center; }
        .on { background:rgba(16,185,129,.15); color:#10b981; }
        .off { background:rgba(30,41,59,.6); color:#94a3b8; }
        .null { background:rgba(245,158,11,.12); color:#fbbf24; }
        .probe-box { margin-top:14px; border-top:1px dashed #334155; padding-top:14px; }
        .probe-grid { display:grid; grid-template-columns:1.2fr 1fr 1fr auto; gap:8px; margin-bottom:12px; }
        .probe-grid input, .probe-grid select { width:100%; border:1px solid #334155; border-radius:8px; padding:8px 10px; background:#020617; color:#e2e8f0; }
        .scan-list { display:grid; gap:8px; margin-top:10px; }
        .scan-item { border:1px solid #334155; border-radius:8px; padding:10px; background:#020617; }
        pre { white-space:pre-wrap; word-break:break-all; background:#020617; padding:12px; border-radius:8px; font-size:12px; color:#cbd5e1; }
    </style>
</head>
<body>
    <h1>灯光调试面板</h1>
    <div class="toolbar">
        <button onclick="loadData()">立即刷新</button>
        <div class="hint">用于排查设备实际状态与页面显示状态是否一致。</div>
    </div>
    <div id="container">加载中...</div>

    <script>
        const probeOutputs = {};

        function renderChannels(label, channels, online = null) {
            if (!Array.isArray(channels) || channels.length === 0) return `<div class="meta">${label}: 无数据</div>`;
            let html = `<div class="meta">${label}</div><div class="channels">`;
            channels.forEach((st, idx) => {
                const unknown = st === null || st === undefined;
                let cls = unknown ? 'null' : (st ? 'on' : 'off');
                let text = unknown ? (online === false ? '离线' : '未知') : (st ? '开启' : '关闭');
                html += `<div class="ch ${cls}">CH${idx + 1}<br>${text}</div>`;
            });
            html += `</div>`;
            return html;
        }

        function runProbe(deviceId) {
            const modeEl = document.getElementById(`probe_mode_${deviceId}`);
            const startEl = document.getElementById(`probe_start_${deviceId}`);
            const countEl = document.getElementById(`probe_count_${deviceId}`);
            const resultEl = document.getElementById(`probe_result_${deviceId}`);
            const params = new URLSearchParams({
                device_id: deviceId,
                mode: modeEl.value,
                start: startEl.value,
                count: countEl.value
            });
            resultEl.innerHTML = '<div class="hint">试读中...</div>';
            fetch(`/api/light/debug_probe?${params.toString()}`)
                .then(r => r.json())
                .then(data => {
                    let html = '';
                    html += `<div class="meta">试读模式: ${data.probe ? data.probe.mode : '--'} | 起始地址: ${data.probe ? data.probe.start_addr : '--'} | 数量: ${data.probe ? data.probe.count : '--'}</div>`;
                    html += renderChannels('试读结果', data.channels || [], data.online);
                    html += `<pre>${JSON.stringify(data, null, 2)}</pre>`;
                    probeOutputs[deviceId] = html;
                    resultEl.innerHTML = html;
                })
                .catch(err => {
                    probeOutputs[deviceId] = `<pre>${String(err)}</pre>`;
                    resultEl.innerHTML = probeOutputs[deviceId];
                });
        }

        function runScan(deviceId) {
            const resultEl = document.getElementById(`probe_result_${deviceId}`);
            resultEl.innerHTML = '<div class="hint">扫描中，请稍候...</div>';
            fetch(`/api/light/debug_scan?device_id=${deviceId}`)
                .then(r => r.json())
                .then(data => {
                    const results = data.results || [];
                    if (!results.length) {
                        probeOutputs[deviceId] = '<div class="hint">没有扫描结果</div>';
                        resultEl.innerHTML = probeOutputs[deviceId];
                        return;
                    }
                    let html = '<div class="meta">自动扫描结果，优先关注有开启通道的项。</div><div class="scan-list">';
                    results.forEach(item => {
                        const activeCount = (item.channels || []).filter(Boolean).length;
                        const titleColor = activeCount > 0 ? '#10b981' : '#94a3b8';
                        html += `<div class="scan-item">
                            <div style="color:${titleColor}; font-weight:bold; margin-bottom:8px;">模式: ${item.mode} | 起始地址: ${item.start_addr} | 在线: ${item.online ? '是' : '否'} | 开启通道数: ${activeCount}</div>
                            ${renderChannels('扫描读回', item.channels || [], item.online)}
                        </div>`;
                    });
                    html += `</div><pre>${JSON.stringify(data, null, 2)}</pre>`;
                    probeOutputs[deviceId] = html;
                    resultEl.innerHTML = html;
                })
                .catch(err => {
                    probeOutputs[deviceId] = `<pre>${String(err)}</pre>`;
                    resultEl.innerHTML = probeOutputs[deviceId];
                });
        }

        function loadData() {
            fetch('/api/light/debug_all')
                .then(r => r.json())
                .then(data => {
                    const list = data.devices || [];
                    if (!list.length) {
                        document.getElementById('container').innerHTML = '<div class="hint">未配置灯光设备</div>';
                        return;
                    }
                    let html = '<div class="grid">';
                    list.forEach(dev => {
                        const online = dev.online === true;
                        const tag = online ? '<span class="tag ok">实时在线</span>' : '<span class="tag bad">实时离线</span>';
                        html += `<div class="card">
                            <div class="title">
                                <div><strong>${dev.name || dev.device_id}</strong></div>
                                ${tag}
                            </div>
                            <div class="meta">
                                设备ID: ${dev.device_id}<br>
                                地址: ${dev.ip}:${dev.port}<br>
                                从站号: ${dev.slave_id}<br>
                                品牌: ${dev.brand || '--'}<br>
                                配置通道数: ${dev.channel_count}<br>
                                状态读取模式: ${dev.status_read_mode || 'coil'}<br>
                                状态起始地址: ${dev.status_start_address ?? 0}<br>
                                写入起始地址: ${dev.write_start_address ?? 0}
                            </div>
                            ${renderChannels('实时读回通道状态', dev.channels, dev.online)}
                            <div style="height:10px"></div>
                            ${renderChannels('缓存通道状态', dev.cached_channels, dev.online)}
                            <div class="probe-box">
                                <div class="meta">临时试读参数，不保存正式配置。</div>
                                <div class="probe-grid">
                                    <select id="probe_mode_${dev.device_id}">
                                        <option value="coil" ${dev.status_read_mode === 'coil' ? 'selected' : ''}>读线圈</option>
                                        <option value="discrete" ${dev.status_read_mode === 'discrete' ? 'selected' : ''}>读离散输入</option>
                                        <option value="holding" ${dev.status_read_mode === 'holding' ? 'selected' : ''}>读保持寄存器</option>
                                        <option value="input" ${dev.status_read_mode === 'input' ? 'selected' : ''}>读输入寄存器</option>
                                    </select>
                                    <input id="probe_start_${dev.device_id}" type="number" value="${dev.status_start_address ?? 0}" placeholder="起始地址">
                                    <input id="probe_count_${dev.device_id}" type="number" value="${dev.channel_count || 0}" placeholder="读取数量">
                                    <button onclick="runProbe(${dev.device_id})">试读</button>
                                </div>
                                <div style="display:flex; gap:8px; margin-bottom:12px;">
                                    <button onclick="runScan(${dev.device_id})">自动扫描</button>
                                </div>
                                <div id="probe_result_${dev.device_id}" class="hint">${probeOutputs[dev.device_id] || '可直接测试不同读取模式和起始地址，不影响正式配置。'}</div>
                            </div>
                            <div style="height:12px"></div>
                            <pre>${JSON.stringify(dev, null, 2)}</pre>
                        </div>`;
                    });
                    html += '</div>';
                    document.getElementById('container').innerHTML = html;
                })
                .catch(err => {
                    document.getElementById('container').innerHTML = `<pre>${String(err)}</pre>`;
                });
        }

        loadData();
        setInterval(loadData, 2000);
    </script>
</body>
</html>
"""


@bp.route("/api/light/status")
@require_permission("light.view")
def api_light_status():
    extras = {}
    for cfg in CONFIG.get("light_devices", []):
        dev_id = cfg.get("id")
        meta = dict((LIGHT_META.get(dev_id) or LIGHT_META.get(str(dev_id)) or {}))
        channel_config = list(cfg.get("channels_config", []) or [])
        channel_labels = {
            str(item.get("channel")): _channel_display_name(item, f"第{item.get('channel')}路")
            for item in channel_config
            if isinstance(item, dict) and item.get("channel") is not None
        }
        protocol_mode = str(cfg.get("relay_protocol") or cfg.get("protocol_variant") or cfg.get("data_protocol") or cfg.get("status_read_mode") or "").strip()
        extras[str(dev_id)] = {
            "brand": cfg.get("brand"),
            "protocol_mode": protocol_mode,
            "relay_protocol": cfg.get("relay_protocol"),
            "channel_labels": channel_labels,
            "dashboard_action_buttons": list(cfg.get("dashboard_action_buttons", []) or []),
            "inputs": list(meta.get("inputs", []) or []),
            "input_count": int(cfg.get("input_count", 0) or 0),
            "input_channels_config": list(cfg.get("input_channels_config", []) or []),
            "input_active_level": cfg.get("input_active_level", "high"),
            "input_state_known": bool(meta.get("input_state_known", False)),
            "status_text": (meta.get("device_status_text") or meta.get("status_text") or "unknown"),
            "status_level": meta.get("status_level", "offline"),
            "status_label": meta.get("status_label", "离线"),
            "stale": bool(meta.get("stale", False)),
            "channel_state_known": bool(meta.get("channel_state_known", False)),
            "poll_failures": int(meta.get("poll_failures", 0) or 0),
            "last_success_at": meta.get("last_success_at"),
            "last_checked_at": meta.get("last_checked_at"),
            "last_error": meta.get("last_error") or meta.get("error") or "",
            "last_error_at": meta.get("last_error_at"),
        }
    return jsonify(
        {
            "channels": _json_keyed_status_map(LIGHT_STATUS),
            "online": _json_keyed_status_map(LIGHT_ONLINE),
            "extras": extras,
        }
    )


@bp.route("/api/light/control", methods=["POST"])
@require_permission("light.control")
def api_light_control():
    d = request.json or {}
    current_user = get_current_user()
    device_id = d.get("device_id")
    drv = LIGHT_DRIVERS.get(device_id)
    if drv is None:
        try:
            drv = LIGHT_DRIVERS.get(int(device_id))
        except Exception:
            drv = None
    if d.get("type") == "single":
        if drv:
            dev_id = device_id
            channel = d.get("channel")
            requested_state = _parse_bool(d.get("is_open"), default=False)
            lock_key = f"light:{dev_id}:channel:{channel}"
            locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "light_single", timeout_sec=2.5)
            if not locked:
                return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
            try:
                success = drv.control_channel(d.get("channel"), requested_state)
                if success:
                    fresh = drv.read_status()
                    LIGHT_ONLINE[dev_id] = bool(fresh.get("online", False))
                    if fresh.get("online"):
                        LIGHT_STATUS[dev_id] = list(fresh.get("channels", []) or [])
                    add_log(-1, f"[灯光] 调光控制: 通道{d.get('channel')} {'开启' if requested_state else '关闭'}")
                    try:
                        device_name = str((next((item.get("name") for item in CONFIG.get("light_devices", []) if str(item.get("id")) == str(dev_id)), "") or dev_id))
                        record_event(
                            category="light",
                            event_type="command",
                            source="api",
                            source_detail=current_user.username,
                            device_id=str(dev_id),
                            device_name=device_name,
                            channel=str(channel),
                            action="power_on" if requested_state else "power_off",
                            message=f"[灯光] 控制命令 {device_name} 通道{channel} {'开启' if requested_state else '关闭'}",
                            result="success",
                            confidence="confirmed" if fresh.get("online") else "unknown",
                            raw={"request": d, "fresh": fresh},
                        )
                    except Exception:
                        _log.debug("non-critical error suppressed", exc_info=True)
                        pass
                    log_audit_event(
                        "light.channel.set",
                        target=f"light:{dev_id}:channel:{channel}",
                        detail={"device_id": dev_id, "channel": channel, "is_open": requested_state},
                    )
                    if not fresh.get("online"):
                        return jsonify({"success": False, "msg": "指令已发送，但设备状态复核失败，请检查通讯或读写地址配置", "verify_failed": True})
                    verified_channels = list(fresh.get("channels", []) or [])
                    idx = int(channel) - 1 if channel not in (None, "") else -1
                    if idx < 0 or idx >= len(verified_channels):
                        return jsonify({"success": True, "verified": False, "msg": "指令已发送，但未读到通道复核值", "channels": verified_channels})
                    verified_state = bool(verified_channels[idx])
                    if verified_state != requested_state:
                        return jsonify({
                            "success": False,
                            "msg": f"设备返回状态与目标不一致，目标={requested_state}，实际={verified_state}",
                            "verify_failed": True,
                            "channels": verified_channels,
                        })
                    return jsonify({"success": True, "verified": True, "channels": verified_channels})
                return jsonify({"success": False, "msg": "灯光控制下发失败"})
            finally:
                release_operation_lock(lock_key, current_user.username)
    elif d.get("type") == "action":
        if drv and hasattr(drv, "execute_action"):
            dev_id = device_id
            action_name = str(d.get("action") or "").strip().lower()
            lock_key = f"light:{dev_id}:action:{action_name}"
            locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "light_action", timeout_sec=2.5)
            if not locked:
                return jsonify({"success": False, "msg": f"设备正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
            try:
                result = drv.execute_action(action_name)
                fresh = drv.read_status()
                LIGHT_ONLINE[dev_id] = bool(fresh.get("online", False))
                if fresh.get("online"):
                    LIGHT_STATUS[dev_id] = list(fresh.get("channels", []) or [])
                if result.get("success"):
                    add_log(-1, f"[灯光] 特殊动作: {action_name}")
                    try:
                        device_name = str((next((item.get("name") for item in CONFIG.get("light_devices", []) if str(item.get("id")) == str(dev_id)), "") or dev_id))
                        record_event(
                            category="light",
                            event_type="command",
                            source="api",
                            source_detail=current_user.username,
                            device_id=str(dev_id),
                            device_name=device_name,
                            action=action_name,
                            message=f"[灯光] 特殊动作 {device_name} {action_name}",
                            result="success",
                            confidence="confirmed" if result.get("verified") else "unknown",
                            raw={"result": result, "fresh": fresh},
                        )
                    except Exception:
                        _log.debug("non-critical error suppressed", exc_info=True)
                        pass
                    log_audit_event(
                        "light.action.execute",
                        target=f"light:{dev_id}:action:{action_name}",
                        detail={"device_id": dev_id, "action": action_name},
                    )
                    payload = {
                        "success": True,
                        "verified": bool(result.get("verified", False)),
                        "queued": bool(result.get("queued", False)),
                        "channels": list(fresh.get("channels", []) or []),
                        "status_text": result.get("status_text") or fresh.get("status_text"),
                    }
                    if result.get("ack") is not None:
                        payload["ack"] = result.get("ack")
                    return jsonify(payload)
                return jsonify({"success": False, "msg": result.get("msg") or "特殊动作下发失败"})
            finally:
                release_operation_lock(lock_key, current_user.username)
    elif d.get("type") == "scene":
        scene_id = d.get("scene_id")
        lock_key = f"light_scene:{scene_id}"
        locked, lock_info = acquire_operation_lock(lock_key, current_user.username, "light_scene", timeout_sec=4.0)
        if not locked:
            return jsonify({"success": False, "msg": f"场景正由 {lock_info.get('owner')} 执行，请稍后再试", "error": "device_busy"}), 409
        try:
            execute_scene(scene_id)
            log_audit_event("light.scene.execute", target=str(scene_id or ""), detail={"scene_id": scene_id})
            return jsonify({"success": True})
        finally:
            release_operation_lock(lock_key, current_user.username)
    return jsonify({"success": False, "msg": "无效控制类型"})


@bp.route("/api/light/logs")
@require_permission("light.view")
def api_light_logs():
    now_ts = time.time()
    if now_ts < float(LIGHT_LOGS_CACHE.get("expires_at", 0.0) or 0.0):
        return jsonify(LIGHT_LOGS_CACHE.get("payload", []))
    limit = request.args.get("limit", default=120, type=int)
    diagnostics = _build_light_diagnostic_logs(limit=limit)
    payload = diagnostics + _filter_light_logs(load_logs(-1), limit=limit)
    payload = payload[:limit]
    LIGHT_LOGS_CACHE["payload"] = payload
    LIGHT_LOGS_CACHE["expires_at"] = now_ts + LIGHT_LOGS_TTL_SEC
    return jsonify(payload)


@bp.route("/api/light/debug")
@require_permission("light.view")
def api_light_debug():
    device_id = request.args.get("device_id", type=int)
    drv = LIGHT_DRIVERS.get(device_id)
    if not drv:
        return jsonify({"success": False, "msg": "找不到灯光设备"}), 404

    try:
        status = drv.read_status()
        return jsonify(
            {
                "success": True,
                "device_id": device_id,
                "online": status.get("online", False),
                "channels": status.get("channels", []),
                "cached_online": LIGHT_ONLINE.get(device_id),
                "cached_channels": LIGHT_STATUS.get(device_id, []),
            }
        )
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "device_id": device_id,
                "msg": str(exc),
                "cached_online": LIGHT_ONLINE.get(device_id),
                "cached_channels": LIGHT_STATUS.get(device_id, []),
            }
        ), 500


@bp.route("/api/light/debug_probe")
@require_permission("light.view")
def api_light_debug_probe():
    device_id = request.args.get("device_id", type=int)
    if device_id is None:
        return jsonify({"success": False, "msg": "缺少 device_id 参数"}), 400

    cfg = next((d for d in CONFIG.get("light_devices", []) if int(d.get("id")) == device_id), None)
    if not cfg:
        return jsonify({"success": False, "msg": "找不到灯光设备配置"}), 404

    drv = LIGHT_DRIVERS.get(device_id)
    if not drv:
        return jsonify({"success": False, "msg": "驱动未加载"}), 404

    mode = request.args.get("mode", cfg.get("status_read_mode", "coil"))
    start_addr = request.args.get("start", type=int)
    if start_addr is None:
        start_addr = int(cfg.get("status_start_address", 0))
    count = request.args.get("count", type=int)
    if count is None:
        count = int(cfg.get("channels", 0))

    original_mode = drv.config.get("status_read_mode", "coil")
    original_start = int(drv.config.get("status_start_address", 0))
    original_channels = int(drv.config.get("channels", 0))

    try:
        drv.config["status_read_mode"] = mode
        drv.config["status_start_address"] = start_addr
        drv.config["channels"] = count
        status = drv.read_status()
        return jsonify(
            {
                "success": True,
                "device_id": device_id,
                "probe": {"mode": mode, "start_addr": start_addr, "count": count},
                "online": status.get("online", False),
                "channels": status.get("channels", []),
            }
        )
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "device_id": device_id,
                "probe": {"mode": mode, "start_addr": start_addr, "count": count},
                "msg": str(exc),
            }
        ), 500
    finally:
        drv.config["status_read_mode"] = original_mode
        drv.config["status_start_address"] = original_start
        drv.config["channels"] = original_channels


@bp.route("/api/light/debug_scan")
@require_permission("light.view")
def api_light_debug_scan():
    device_id = request.args.get("device_id", type=int)
    if device_id is None:
        return jsonify({"success": False, "msg": "缺少 device_id 参数"}), 400

    cfg = next((d for d in CONFIG.get("light_devices", []) if int(d.get("id")) == device_id), None)
    if not cfg:
        return jsonify({"success": False, "msg": "找不到灯光设备配置"}), 404

    drv = LIGHT_DRIVERS.get(device_id)
    if not drv:
        return jsonify({"success": False, "msg": "驱动未加载"}), 404

    original_mode = drv.config.get("status_read_mode", "coil")
    original_start = int(drv.config.get("status_start_address", 0))
    original_channels = int(drv.config.get("channels", 0))
    channel_count = int(cfg.get("channels", 0))

    modes = ["coil", "discrete", "holding", "input"]
    starts = [0, 1, 2, 3, 4, 8]
    results = []

    try:
        for mode in modes:
            for start_addr in starts:
                try:
                    drv.config["status_read_mode"] = mode
                    drv.config["status_start_address"] = start_addr
                    drv.config["channels"] = channel_count
                    status = drv.read_status()
                    results.append(
                        {
                            "mode": mode,
                            "start_addr": start_addr,
                            "online": status.get("online", False),
                            "channels": status.get("channels", []),
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "mode": mode,
                            "start_addr": start_addr,
                            "online": False,
                            "channels": [],
                            "msg": str(exc),
                        }
                    )
        return jsonify({"success": True, "device_id": device_id, "results": results})
    finally:
        drv.config["status_read_mode"] = original_mode
        drv.config["status_start_address"] = original_start
        drv.config["channels"] = original_channels


@bp.route("/api/light/debug_all")
@require_permission("light.view")
def api_light_debug_all():
    devices = []
    for cfg in CONFIG.get("light_devices", []):
        dev_id = cfg.get("id")
        item = {
            "device_id": dev_id,
            "name": cfg.get("name"),
            "ip": cfg.get("ip"),
            "port": cfg.get("port"),
            "slave_id": cfg.get("slave_id", 1),
            "brand": cfg.get("brand"),
            "channel_count": cfg.get("channels", 0),
            "input_count": cfg.get("input_count", 0),
            "input_channels_config": cfg.get("input_channels_config", []),
            "input_active_level": cfg.get("input_active_level", "high"),
            "status_read_mode": cfg.get("status_read_mode", "coil"),
            "status_start_address": cfg.get("status_start_address", 0),
            "input_start_address": cfg.get("input_start_address", 0),
            "write_start_address": cfg.get("write_start_address", 0),
            "cached_online": LIGHT_ONLINE.get(dev_id),
            "cached_channels": LIGHT_STATUS.get(dev_id, []),
        }
        drv = LIGHT_DRIVERS.get(dev_id)
        if not drv:
            item.update({"success": False, "msg": "驱动未加载"})
            devices.append(item)
            continue

        try:
            status = drv.read_status()
            item.update(
                {
                    "success": True,
                    "online": status.get("online", False),
                    "channels": status.get("channels", []),
                    "inputs": status.get("inputs", []),
                }
            )
        except Exception as exc:
            item.update({"success": False, "msg": str(exc)})
        devices.append(item)

    return jsonify({"success": True, "devices": devices})


@bp.route("/light_debug")
@require_permission("light.view")
def light_debug_page():
    return render_template_string(LIGHT_DEBUG_HTML)
