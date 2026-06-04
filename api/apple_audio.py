# AI_MODULE: apple_audio_api
# AI_PURPOSE: 音乐库全量刮削、队列、播放/停止/进度跳转控制、歌词和封面接口。
# AI_BOUNDARY: 播放器核心状态在 apple_audio_core.py；页面渲染在 apple-audio.js。
# AI_DATA_FLOW: 本地音乐库/播放器 -> /api/apple-audio/* -> 前端音乐卡片。
# AI_RUNTIME: 首页音乐模块和 Apple Audio 页面调用。
# AI_RISK: 中，音乐扫描可能影响加载性能。
# AI_COMPAT: queue/transport stop/seek/lyrics/cover 路由需保持。
# AI_SEARCH_KEYWORDS: apple audio, music, full scrape, rescan, queue, stop, seek, lyrics, cover.

import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, Response, jsonify, redirect, request, stream_with_context

from apple_audio_core import apple_audio_service
from auth.decorators import require_permission
from config import CONFIG, save_config
from data_logger import add_log

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


def _normalize_playback_mode(value):
    aliases = {
        "random": "shuffle",
        "loop": "repeat_all",
        "loop_all": "repeat_all",
        "repeat": "repeat_all",
        "single": "repeat_one",
        "single_loop": "repeat_one",
    }
    mode = str(value or "").strip().lower()
    mode = aliases.get(mode, mode)
    if mode not in {"normal", "shuffle", "repeat_all", "repeat_one"}:
        raise ValueError("unsupported playback mode")
    return mode


def _coerce_volume_percent(value):
    try:
        return max(0, min(int(round(float(value))), 100))
    except Exception:
        raise ValueError("unsupported volume")


def _coerce_seek_seconds(value):
    try:
        return max(0, int(round(float(value))))
    except Exception:
        raise ValueError("unsupported seek position")


def _error_payload(message, status=400):
    return jsonify({"success": False, "message": str(message or "request failed")}), int(status)


@bp.route("/api/apple-audio/status")
@require_permission("meter.view")
def api_apple_audio_status():
    apple_audio_service.configure()
    return jsonify({"success": True, "state": apple_audio_service.snapshot()})


@bp.route("/api/apple-audio/local-output/status")
@require_permission("meter.view")
def api_apple_audio_local_output_status():
    return jsonify({"success": True, "status": apple_audio_service.local_output_status()})


@bp.route("/api/apple-audio/bluetooth/connect", methods=["POST"])
@require_permission("meter.config")
def api_apple_audio_bluetooth_connect():
    data = request.json or {}
    try:
        result = apple_audio_service.bluetooth_connect(data.get("mac"), trust=bool(data.get("trust", True)))
        add_log(-1, f"[MusicPlayer] bluetooth connect {result.get('target')} ok={result.get('ok')}")
        return jsonify({"success": bool(result.get("ok")), "result": result})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


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
        "playback_mode",
        "volume_percent",
        "auth_state",
        "nas_music_roots",
        "nas_music_exclude_dirs",
        "local_player_command",
        "local_player_audio_user",
        "local_player_sink",
        "local_player_alsa_device",
        "jamendo_client_id",
        "jamendo_api_base",
    ]:
        if key in data:
            value = data.get(key)
            if key in {"nas_music_roots", "nas_music_exclude_dirs"}:
                if isinstance(value, list):
                    cfg[key] = [str(item or "").strip() for item in value if str(item or "").strip()]
                elif isinstance(value, str):
                    cfg[key] = [line.strip() for line in value.splitlines() if line.strip()]
            else:
                if key == "playback_mode":
                    cfg[key] = _normalize_playback_mode(value)
                elif key == "volume_percent":
                    cfg[key] = _coerce_volume_percent(value)
                else:
                    cfg[key] = str(value or "").strip()
    for key in ["enabled"]:
        if key in data:
            cfg[key] = bool(data.get(key))
    if "nas_auto_scan_on_start" in data:
        cfg["nas_auto_scan_on_start"] = bool(data.get("nas_auto_scan_on_start"))
    if "local_player_enabled" in data:
        cfg["local_player_enabled"] = bool(data.get("local_player_enabled"))
    if "jamendo_enabled" in data:
        cfg["jamendo_enabled"] = bool(data.get("jamendo_enabled"))
    if "jamendo_limit" in data:
        try:
            cfg["jamendo_limit"] = max(1, min(int(data.get("jamendo_limit")), 50))
        except Exception:
            pass
    _save_cfg(cfg)
    return jsonify({"success": True, "config": cfg, "state": apple_audio_service.snapshot()})


@bp.route("/api/apple-audio/search")
@require_permission("meter.view")
def api_apple_audio_search():
    query = request.args.get("q", "")
    source = str(request.args.get("source", "local") or "local").strip().lower()
    include_jamendo = source in {"all", "jamendo"}
    limit = request.args.get("limit", "")
    try:
        max_items = max(1, min(int(limit or 50), 300))
    except Exception:
        max_items = 50
    payload = apple_audio_service.search_sources(query, include_jamendo=include_jamendo, limit=max_items)
    return jsonify({"success": True, **payload})


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
    data = request.json or {}
    full_scrape = bool(data.get("full_scrape", data.get("scrape_all", True)))
    force = bool(data.get("force", data.get("rebuild", False)))
    state = apple_audio_service.start_background_scan("api", full_scrape=full_scrape, force=force)
    add_log(-1, f"[MusicTag] rescan queued full_scrape={full_scrape} force={force}, tracks={state.get('library_size', 0)}")
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
    parsed = urlparse(file_path)
    if parsed.scheme in {"http", "https"}:
        return redirect(file_path, code=302)
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


@bp.route("/api/apple-audio/playlists")
@require_permission("meter.view")
def api_apple_audio_playlists():
    return jsonify({"success": True, **apple_audio_service.playlists_snapshot()})


@bp.route("/api/apple-audio/playlists", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_playlist_create():
    data = request.json or {}
    try:
        payload = apple_audio_service.create_custom_playlist(data.get("name"))
        add_log(-1, f"[MusicPlayer] playlist created {data.get('name')}")
        return jsonify({"success": True, **payload})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/playlists/add-track", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_playlist_add_track():
    data = request.json or {}
    try:
        payload = apple_audio_service.add_track_to_custom_playlist(data.get("playlist_id"), data.get("track_id"))
        add_log(-1, f"[MusicPlayer] playlist add track {data.get('playlist_id')} {data.get('track_id')}")
        return jsonify({"success": True, **payload})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/playlists/queue", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_playlist_queue():
    data = request.json or {}
    try:
        snapshot = apple_audio_service.queue_playlist(
            data.get("playlist_id"),
            play_now=bool(data.get("play_now")),
            mode=data.get("mode"),
        )
        add_log(-1, f"[MusicPlayer] playlist queue {data.get('playlist_id')} play_now={bool(data.get('play_now'))}")
        return jsonify({"success": True, "state": snapshot})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)


@bp.route("/api/apple-audio/queue", methods=["POST"])
@require_permission("meter.view")
def api_apple_audio_queue():
    data = request.json or {}
    track_id = data.get("track_id")
    play_now = bool(data.get("play_now"))
    try:
        snapshot = apple_audio_service.queue_track(track_id, play_now=play_now)
        add_log(-1, f"[MusicPlayer] queued track {track_id}")
        return jsonify({"success": True, "state": snapshot})
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
        action_key = str(action or "").strip().lower()
        if action_key in {"volume", "set_volume"}:
            cfg = _cfg()
            volume = _coerce_volume_percent(data.get("volume_percent", data.get("volume", data.get("mode"))))
            cfg["volume_percent"] = volume
            _save_cfg(cfg)
            snapshot = apple_audio_service.transport(action, mode=volume)
            add_log(-1, f"[MusicPlayer] volume {volume}%")
        elif action_key in {"playback_mode", "set_mode", "mode"}:
            cfg = _cfg()
            mode = _normalize_playback_mode(data.get("mode"))
            cfg["playback_mode"] = mode
            _save_cfg(cfg)
            snapshot = apple_audio_service.transport(action, mode=mode)
            add_log(-1, f"[MusicPlayer] playback mode {mode}")
        elif action_key == "seek":
            seconds = _coerce_seek_seconds(data.get("elapsed_sec", data.get("position", data.get("mode"))))
            snapshot = apple_audio_service.transport(action, mode=seconds)
            add_log(-1, f"[MusicPlayer] seek {seconds}s")
        else:
            snapshot = apple_audio_service.transport(action)
            add_log(-1, f"[MusicPlayer] transport {action}")
        return jsonify({"success": True, "state": snapshot})
    except ValueError as ex:
        return _error_payload(ex, 400)
    except Exception as ex:
        return _error_payload(ex, 500)
