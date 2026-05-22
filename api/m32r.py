# AI_MODULE: m32r_api
# AI_PURPOSE: M32R 调音台连接、通道/主输出控制、模板和 Apple Audio 路由辅助接口。
# AI_BOUNDARY: OSC/调音台协议细节在 m32r_core.py。
# AI_DATA_FLOW: M32R 页面 -> /api/m32r/* -> m32r_service -> 调音台。
# AI_RUNTIME: 独立 M32R 页面和音乐路由准备动作调用。
# AI_RISK: 中，控制会影响现场音频输出。
# AI_COMPAT: /m32r、/api/m32r/status/connect/channel/main/templates 需保持。
# AI_SEARCH_KEYWORDS: m32r, mixer, osc, audio, channel, main.

from flask import Blueprint, jsonify, render_template, request

from config import CONFIG, save_config
from data_logger import add_log
from m32r_core import m32r_service

bp = Blueprint("m32r", __name__)


def _m32r_cfg():
    cfg = CONFIG.get("m32r", {}) or {}
    if not isinstance(cfg.get("templates"), list):
        cfg["templates"] = []
    if not isinstance(cfg.get("known_mixers"), list):
        cfg["known_mixers"] = []
    return cfg


def _normalize_bank_start(bank_start, channel_count):
    channel_count = max(1, min(int(channel_count or 8), 32))
    max_start = max(1, 33 - channel_count)
    return max(1, min(int(bank_start or 1), max_start))


@bp.route("/m32r")
def m32r_page():
    return render_template("m32r.html", config=CONFIG)


@bp.route("/api/m32r/status")
def api_m32r_status():
    m32r_service.configure()
    return jsonify(m32r_service.snapshot())


@bp.route("/api/m32r/discover", methods=["POST"])
def api_m32r_discover():
    m32r_service.configure()
    snapshot = m32r_service.discover_mixers()
    return jsonify({"success": True, "state": snapshot, "mixers": snapshot.get("discovered_mixers", [])})


@bp.route("/api/m32r/connect", methods=["POST"])
def api_m32r_connect():
    data = request.json or {}
    cfg = _m32r_cfg()
    changed = False

    for key in ["host", "name", "sync_direction"]:
        if key in data:
            cfg[key] = str(data.get(key, "") or "").strip()
            changed = True

    for key in ["port", "channel_count", "bank_start", "poll_interval_ms", "keepalive_sec"]:
        if key in data:
            try:
                cfg[key] = int(data.get(key))
                changed = True
            except Exception:
                pass

    for key in ["auto_connect", "auto_sync", "enabled"]:
        if key in data:
            cfg[key] = bool(data.get(key))
            changed = True

    cfg["channel_count"] = max(1, min(int(cfg.get("channel_count", 8) or 8), 32))
    cfg["bank_start"] = _normalize_bank_start(cfg.get("bank_start", 1), cfg["channel_count"])
    cfg["port"] = int(cfg.get("port", 10023) or 10023)
    cfg["poll_interval_ms"] = max(300, int(cfg.get("poll_interval_ms", 1200) or 1200))
    cfg["keepalive_sec"] = max(2, min(int(cfg.get("keepalive_sec", 5) or 5), 9))
    cfg["sync_direction"] = str(cfg.get("sync_direction", "mixer_to_pc") or "mixer_to_pc")

    demo_mode = bool(data.get("demo_mode"))
    if changed:
        CONFIG["m32r"] = cfg
        save_config(CONFIG)

    snapshot = m32r_service.connect(demo_mode=demo_mode)
    if demo_mode:
        add_log(-1, "[M32R] demo mode enabled")
    else:
        add_log(-1, f"[M32R] connect requested {snapshot.get('host')}:{snapshot.get('port')}")
    return jsonify({"success": True, "state": snapshot})


@bp.route("/api/m32r/disconnect", methods=["POST"])
def api_m32r_disconnect():
    snapshot = m32r_service.disconnect()
    add_log(-1, "[M32R] disconnected")
    return jsonify({"success": True, "state": snapshot})


@bp.route("/api/m32r/config", methods=["POST"])
def api_m32r_config():
    data = request.json or {}
    cfg = _m32r_cfg()
    for key, value in data.items():
        cfg[key] = value
    cfg["channel_count"] = max(1, min(int(cfg.get("channel_count", 8) or 8), 32))
    cfg["bank_start"] = _normalize_bank_start(cfg.get("bank_start", 1), cfg["channel_count"])
    cfg["poll_interval_ms"] = max(300, int(cfg.get("poll_interval_ms", 1200) or 1200))
    cfg["keepalive_sec"] = max(2, min(int(cfg.get("keepalive_sec", 5) or 5), 9))
    cfg["port"] = int(cfg.get("port", 10023) or 10023)
    cfg["auto_connect"] = bool(cfg.get("auto_connect", False))
    cfg["auto_sync"] = bool(cfg.get("auto_sync", False))
    cfg["sync_direction"] = str(cfg.get("sync_direction", "mixer_to_pc") or "mixer_to_pc")
    if not isinstance(cfg.get("known_mixers"), list):
        cfg["known_mixers"] = []
    CONFIG["m32r"] = cfg
    save_config(CONFIG)
    m32r_service.configure(cfg)
    return jsonify({"success": True, "config": cfg, "state": m32r_service.snapshot()})


@bp.route("/api/m32r/bank", methods=["POST"])
def api_m32r_bank():
    data = request.json or {}
    direction = str(data.get("direction", "next") or "next").strip().lower()
    cfg = _m32r_cfg()
    channel_count = max(1, min(int(cfg.get("channel_count", 8) or 8), 32))
    current_start = _normalize_bank_start(cfg.get("bank_start", 1), channel_count)

    if direction == "prev":
        next_start = max(1, current_start - channel_count)
    elif direction == "next":
        next_start = min(max(1, 33 - channel_count), current_start + channel_count)
    elif direction == "set":
        next_start = _normalize_bank_start(data.get("bank_start", current_start), channel_count)
    else:
        return jsonify({"success": False, "msg": "unknown bank direction"}), 400

    cfg["bank_start"] = next_start
    CONFIG["m32r"] = cfg
    save_config(CONFIG)
    m32r_service.configure(cfg)
    m32r_service.refresh_channels()
    return jsonify({"success": True, "config": cfg, "state": m32r_service.snapshot()})


@bp.route("/api/m32r/channel", methods=["POST"])
def api_m32r_channel():
    data = request.json or {}
    try:
        channel_no = int(data.get("channel", 1))
    except Exception:
        return jsonify({"success": False, "msg": "invalid channel"}), 400
    if channel_no < 1 or channel_no > 32:
        return jsonify({"success": False, "msg": "channel out of range"}), 400
    action = str(data.get("action", "") or "").strip()

    if action == "mute_toggle":
        current = next(
            (item for item in m32r_service.snapshot().get("channels", []) if int(item.get("channel", 0)) == channel_no),
            None,
        )
        target_on = not bool(current.get("on", True)) if current else False
        snapshot = m32r_service.set_channel_on(channel_no, target_on)
        add_log(-1, f"[M32R] channel {channel_no:02d} {'on' if target_on else 'mute'}")
        return jsonify({"success": True, "state": snapshot})

    if action == "set_on":
        target_on = bool(data.get("on"))
        snapshot = m32r_service.set_channel_on(channel_no, target_on)
        add_log(-1, f"[M32R] channel {channel_no:02d} {'on' if target_on else 'mute'}")
        return jsonify({"success": True, "state": snapshot})

    if action == "set_fader":
        snapshot = m32r_service.set_channel_fader(channel_no, float(data.get("value", 0.75)))
        return jsonify({"success": True, "state": snapshot})

    if action == "set_pan":
        snapshot = m32r_service.set_channel_pan(channel_no, float(data.get("value", 0.5)))
        return jsonify({"success": True, "state": snapshot})

    if action == "set_detail":
        snapshot = m32r_service.set_channel_detail(
            channel_no,
            str(data.get("section", "") or "").strip(),
            str(data.get("key", "") or "").strip(),
            data.get("value"),
        )
        return jsonify({"success": True, "state": snapshot})

    if action == "set_label":
        snapshot = m32r_service.set_channel_label(channel_no, data.get("name"), data.get("scribble"))
        add_log(-1, f"[M32R] channel {channel_no:02d} label updated")
        return jsonify({"success": True, "state": snapshot})

    return jsonify({"success": False, "msg": "unknown channel action"}), 400


@bp.route("/api/m32r/main", methods=["POST"])
def api_m32r_main():
    data = request.json or {}
    action = str(data.get("action", "") or "").strip()

    if action == "set_on":
        target_on = bool(data.get("on"))
        snapshot = m32r_service.set_main_on(target_on)
        add_log(-1, f"[M32R] main {'on' if target_on else 'mute'}")
        return jsonify({"success": True, "state": snapshot})

    if action == "set_fader":
        try:
            value = float(data.get("value", 0.75))
        except Exception:
            return jsonify({"success": False, "msg": "invalid main fader value"}), 400
        snapshot = m32r_service.set_main_fader(value)
        return jsonify({"success": True, "state": snapshot})

    return jsonify({"success": False, "msg": "unknown main action"}), 400


@bp.route("/api/m32r/refresh", methods=["POST"])
def api_m32r_refresh():
    m32r_service.refresh_channels()
    return jsonify({"success": True, "state": m32r_service.snapshot()})


@bp.route("/api/m32r/sync", methods=["POST"])
def api_m32r_sync():
    data = request.json or {}
    direction = str(data.get("direction", "mixer_to_pc") or "mixer_to_pc").strip().lower()
    if direction == "pc_to_mixer":
        payload = data.get("state") or m32r_service.snapshot()
        snapshot = m32r_service.apply_template(payload)
        add_log(-1, "[M32R] sync applied PC -> Mixer")
        return jsonify({"success": True, "state": snapshot})
    m32r_service.refresh_channels()
    snapshot = m32r_service.snapshot()
    add_log(-1, "[M32R] sync applied Mixer -> PC")
    return jsonify({"success": True, "state": snapshot})


@bp.route("/api/m32r/scene", methods=["POST"])
def api_m32r_scene():
    data = request.json or {}
    scene_name = str(data.get("scene", "") or "").strip().lower()
    snapshot = m32r_service.apply_scene(scene_name)
    add_log(-1, f"[M32R] scene applied: {scene_name}")
    return jsonify({"success": True, "state": snapshot})


@bp.route("/api/m32r/templates")
def api_m32r_templates():
    cfg = _m32r_cfg()
    return jsonify({"success": True, "templates": list(cfg.get("templates", []) or [])})


@bp.route("/api/m32r/template/save", methods=["POST"])
def api_m32r_template_save():
    data = request.json or {}
    name = str(data.get("name", "") or "").strip() or "unnamed_template"
    cfg = _m32r_cfg()
    templates = list(cfg.get("templates", []) or [])
    template_data = m32r_service.capture_template(name)
    replaced = False

    for idx, item in enumerate(templates):
        if str(item.get("name", "")).strip() == name:
            templates[idx] = template_data
            replaced = True
            break

    if not replaced:
        templates.append(template_data)

    cfg["templates"] = templates
    CONFIG["m32r"] = cfg
    save_config(CONFIG)
    add_log(-1, f"[M32R] template saved: {name}")
    return jsonify({"success": True, "templates": templates, "state": m32r_service.snapshot()})


@bp.route("/api/m32r/template/apply", methods=["POST"])
def api_m32r_template_apply():
    data = request.json or {}
    name = str(data.get("name", "") or "").strip()
    cfg = _m32r_cfg()
    templates = list(cfg.get("templates", []) or [])
    template_data = next((item for item in templates if str(item.get("name", "")).strip() == name), None)
    if not template_data:
        return jsonify({"success": False, "msg": "template not found"}), 404

    snapshot = m32r_service.apply_template(template_data)
    add_log(-1, f"[M32R] template loaded: {name}")
    return jsonify({"success": True, "state": snapshot, "template": template_data})


@bp.route("/api/m32r/template/delete", methods=["POST"])
def api_m32r_template_delete():
    data = request.json or {}
    name = str(data.get("name", "") or "").strip()
    cfg = _m32r_cfg()
    templates = list(cfg.get("templates", []) or [])
    next_templates = [item for item in templates if str(item.get("name", "")).strip() != name]
    if len(next_templates) == len(templates):
        return jsonify({"success": False, "msg": "template not found"}), 404

    cfg["templates"] = next_templates
    CONFIG["m32r"] = cfg
    save_config(CONFIG)
    add_log(-1, f"[M32R] template deleted: {name}")
    return jsonify({"success": True, "templates": next_templates})


@bp.route("/api/m32r/template/rename", methods=["POST"])
def api_m32r_template_rename():
    data = request.json or {}
    old_name = str(data.get("old_name", "") or "").strip()
    new_name = str(data.get("new_name", "") or "").strip()
    if not old_name or not new_name:
        return jsonify({"success": False, "msg": "template name required"}), 400

    cfg = _m32r_cfg()
    templates = list(cfg.get("templates", []) or [])
    target = next((item for item in templates if str(item.get("name", "")).strip() == old_name), None)
    if not target:
        return jsonify({"success": False, "msg": "template not found"}), 404

    if any(str(item.get("name", "")).strip() == new_name for item in templates if item is not target):
        return jsonify({"success": False, "msg": "template already exists"}), 400

    target["name"] = new_name
    cfg["templates"] = templates
    CONFIG["m32r"] = cfg
    save_config(CONFIG)
    add_log(-1, f"[M32R] template renamed: {old_name} -> {new_name}")
    return jsonify({"success": True, "templates": templates})
