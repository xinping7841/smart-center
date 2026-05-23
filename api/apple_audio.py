# AI_MODULE: apple_audio_api
# AI_PURPOSE: 音乐库、队列、播放控制、歌词封面和 M32R 准备动作接口。
# AI_BOUNDARY: 播放器核心状态在 apple_audio_core.py；页面渲染在 apple-audio.js。
# AI_DATA_FLOW: 本地音乐库/播放器 -> /api/apple-audio/* -> 前端音乐卡片。
# AI_RUNTIME: 首页音乐模块和 Apple Audio 页面调用。
# AI_RISK: 中，M32R 准备动作可能影响音频路由；音乐扫描可能影响加载性能。
# AI_COMPAT: queue/transport/lyrics/cover/m32/prepare 路由需保持。
# AI_SEARCH_KEYWORDS: apple audio, music, queue, lyrics, cover, m32.

import mimetypes
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, stream_with_context

from apple_audio_core import apple_audio_service
from auth.decorators import require_permission
from config import CONFIG, save_config
from data_logger import add_log
from m32r_core import m32r_service

bp = Blueprint("apple_audio", __name__)


def _cfg():
    cfg = CONFIG.get("apple_audio", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    return cfg


def _save_cfg(cfg):
    CONFIG["apple_audio"] = cfg
    save_config(CONFIG)
    apple_audio_service.configure(cfg)


def _error_payload(message, status=400):
    return jsonify({"success": False, "message": str(message or "request failed")}), int(status)


def _auto_prepare_on_play_enabled(cfg):
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("m32_auto_prepare_on_play", True))


def _prepare_m32_channels(cfg=None):
    cfg = cfg if isinstance(cfg, dict) else _cfg()
    left = max(1, min(int(cfg.get("m32_channel_left", 17) or 17), 32))
    right = max(1, min(int(cfg.get("m32_channel_right", 18) or 18), 32))
    level = max(0.0, min(float(cfg.get("m32_prepare_level", 0.68) or 0.68), 1.0))
    label = str(cfg.get("m32_label", "Music Player") or "Music Player").strip() or "Music Player"
    prepare_main = bool(cfg.get("m32_prepare_main", False))

    m32r_service.set_channel_label(left, f"{label} L", "")
    m32r_service.set_channel_label(right, f"{label} R", "")
    m32r_service.set_channel_on(left, True)
    m32r_service.set_channel_on(right, True)
    m32r_service.set_channel_fader(left, level)
    m32r_service.set_channel_fader(right, level)
    m32r_service.set_channel_pan(left, 0.0)
    m32r_service.set_channel_pan(right, 1.0)
    if prepare_main:
        m32r_service.set_main_on(True)

    return {
        "left_channel": left,
        "right_channel": right,
        "label": label,
        "prepare_level": level,
        "prepare_main": prepare_main,
    }


@bp.route("/api/apple-audio/status")
@require_permission("meter.view")
def api_apple_audio_status():
    apple_audio_service.configure()
    return jsonify({"success": True, "state": apple_audio_service.snapshot()})


@bp.route("/api/apple-audio/config", methods=["POST"])
@require_permission("meter.config")
def api_apple_audio_config():
    data = request.json or {}
    cfg = _cfg()
    for key in [
        "provider",
        "player_mode",
        "player_host",
        "output_mode",
        "auth_state",
        "m32_channel_mode",
        "m32_label",
        "nas_music_roots",
        "nas_music_exclude_dirs",
    ]:
        if key in data:
            value = data.get(key)
            if key in {"nas_music_roots", "nas_music_exclude_dirs"}:
                if isinstance(value, list):
                    cfg[key] = [str(item or "").strip() for item in value if str(item or "").strip()]
                elif isinstance(value, str):
                    cfg[key] = [line.strip() for line in value.splitlines() if line.strip()]
            else:
                cfg[key] = str(value or "").strip()
    for key in ["enabled", "m32_prepare_main", "m32_auto_prepare_on_play"]:
        if key in data:
            cfg[key] = bool(data.get(key))
    if "nas_auto_scan_on_start" in data:
        cfg["nas_auto_scan_on_start"] = bool(data.get("nas_auto_scan_on_start"))
    for key in ["m32_channel_left", "m32_channel_right"]:
        if key in data:
            try:
                cfg[key] = max(1, min(int(data.get(key)), 32))
            except Exception:
                pass
    if "m32_prepare_level" in data:
        try:
            cfg["m32_prepare_level"] = max(0.0, min(float(data.get("m32_prepare_level")), 1.0))
        except Exception:
            pass
    _save_cfg(cfg)
    return jsonify({"success": True, "config": cfg, "state": apple_audio_service.snapshot()})


@bp.route("/api/apple-audio/search")
@require_permission("meter.view")
def api_apple_audio_search():
    query = request.args.get("q", "")
    return jsonify({"success": True, "results": apple_audio_service.search(query)})


@bp.route("/api/apple-audio/library")
@require_permission("meter.view")
def api_apple_audio_library():
    query = request.args.get("q", "")
    limit = request.args.get("limit", "")
    try:
        max_items = max(1, min(int(limit or 300), 2000))
    except Exception:
        max_items = 300
    results = apple_audio_service.search(query)[:max_items]
    return jsonify({"success": True, "results": results, "count": len(results)})


@bp.route("/api/apple-audio/rescan", methods=["POST"])
@require_permission("meter.config")
def api_apple_audio_rescan():
    state = apple_audio_service.scan_library()
    add_log(-1, f"[MusicTag] rescan complete, tracks={state.get('library_size', 0)}")
    return jsonify({"success": True, "state": state})


def _iter_file_chunks(path: Path, start: int, stop: int, chunk_size: int = 1024 * 256):
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = max(0, stop - start + 1)
        while remaining > 0:
            chunk = fh.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _guess_audio_mime(path: Path):
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


@bp.route("/api/apple-audio/stream/<track_id>")
@require_permission("meter.view")
def api_apple_audio_stream(track_id):
    file_path = apple_audio_service.get_track_path(track_id)
    if not file_path:
        return jsonify({"success": False, "message": "track not found"}), 404
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return jsonify({"success": False, "message": "audio file missing"}), 404
    file_size = path.stat().st_size
    mime_type = _guess_audio_mime(path)
    range_header = request.headers.get("Range", "")
    if range_header.startswith("bytes="):
        try:
            range_value = range_header.split("=", 1)[1].strip()
            start_text, end_text = range_value.split("-", 1)
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else file_size - 1
            if start < 0:
                start = 0
            if end >= file_size:
                end = file_size - 1
            if end < start:
                end = start
        except Exception:
            return Response(status=416)
        length = end - start + 1
        response = Response(
            stream_with_context(_iter_file_chunks(path, start, end)),
            status=206,
            mimetype=mime_type,
            direct_passthrough=True,
        )
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response.headers["Content-Length"] = str(length)
        return response
    response = Response(
        stream_with_context(_iter_file_chunks(path, 0, file_size - 1)),
        mimetype=mime_type,
        direct_passthrough=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = str(file_size)
    return response


@bp.route("/api/apple-audio/cover/<track_id>")
@require_permission("meter.view")
def api_apple_audio_cover(track_id):
    cover_path, cover_mime = apple_audio_service.get_track_cover(track_id)
    if not cover_path:
        return jsonify({"success": False, "message": "cover not found"}), 404
    path = Path(cover_path)
    if not path.exists() or not path.is_file():
        return jsonify({"success": False, "message": "cover file missing"}), 404
    mime = cover_mime or mimetypes.guess_type(path.name)[0] or "image/jpeg"
    file_size = path.stat().st_size
    response = Response(
        stream_with_context(_iter_file_chunks(path, 0, file_size - 1)),
        mimetype=mime,
        direct_passthrough=True,
    )
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["Content-Length"] = str(file_size)
    return response


@bp.route("/api/apple-audio/lyrics/<track_id>")
@require_permission("meter.view")
def api_apple_audio_lyrics(track_id):
    payload = apple_audio_service.get_track_lyrics(track_id)
    if not payload:
        return jsonify({"success": False, "message": "track not found"}), 404
    return jsonify({"success": True, "lyrics": payload})


@bp.route("/api/apple-audio/queue", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_queue():
    data = request.json or {}
    track_id = data.get("track_id")
    play_now = bool(data.get("play_now"))
    try:
        snapshot = apple_audio_service.queue_track(track_id, play_now=play_now)
        m32_snapshot = None
        cfg = _cfg()
        if play_now and _auto_prepare_on_play_enabled(cfg):
            prepared = _prepare_m32_channels(cfg)
            m32_snapshot = m32r_service.snapshot()
            add_log(
                -1,
                f"[MusicPlayer] auto-prepare M32 CH{prepared['left_channel']:02d}/{prepared['right_channel']:02d}",
            )
        add_log(-1, f"[MusicPlayer] queued track {track_id}")
        payload = {"success": True, "state": snapshot}
        if m32_snapshot is not None:
            payload["m32_state"] = m32_snapshot
        return jsonify(payload)
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/queue/promote", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_queue_promote():
    data = request.json or {}
    try:
        snapshot = apple_audio_service.promote_queue(int(data.get("index", 0)))
        return jsonify({"success": True, "state": snapshot})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/queue/clear", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_queue_clear():
    try:
        snapshot = apple_audio_service.clear_queue()
        return jsonify({"success": True, "state": snapshot})
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/transport", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_transport():
    data = request.json or {}
    action = data.get("action", "")
    try:
        snapshot = apple_audio_service.transport(action)
        cfg = _cfg()
        m32_snapshot = None
        if action in {"toggle", "next", "prev"} and snapshot.get("current_track") and _auto_prepare_on_play_enabled(cfg):
            prepared = _prepare_m32_channels(cfg)
            m32_snapshot = m32r_service.snapshot()
            add_log(
                -1,
                f"[MusicPlayer] auto-prepare M32 CH{prepared['left_channel']:02d}/{prepared['right_channel']:02d}",
            )
        add_log(-1, f"[MusicPlayer] transport {action}")
        payload = {"success": True, "state": snapshot}
        if m32_snapshot is not None:
            payload["m32_state"] = m32_snapshot
        return jsonify(payload)
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/m32/prepare", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_m32_prepare():
    try:
        prepared = _prepare_m32_channels(_cfg())
        add_log(
            -1,
            f"[MusicPlayer] M32 prepare CH{prepared['left_channel']:02d}/{prepared['right_channel']:02d}",
        )
        return jsonify(
            {
                "success": True,
                "apple_state": apple_audio_service.snapshot(),
                "m32_state": m32r_service.snapshot(),
                "prepare": prepared,
            }
        )
    except Exception as ex:
        return _error_payload(ex, 500)
