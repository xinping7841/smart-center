# AI_MODULE: nvr_api
# AI_PURPOSE: 海康 NVR 状态、快照、播放器代理和直播预览接口。
# AI_BOUNDARY: 厂商协议封装在 services/hikvision_nvr.py；这里做缓存、代理和响应。
# AI_DATA_FLOW: NVR/ISAPI/FFmpeg -> /api/nvr/status/snapshot/player/live -> NVR 前端。
# AI_RUNTIME: 监控预览和 NVR 页面调用，部分流媒体接口可能长连接。
# AI_RISK: 中，预览性能会影响浏览器和服务器负载，避免无节制并发。
# AI_COMPAT: snapshot/player/live URL 和通道字段需兼容现有前端。
# AI_SEARCH_KEYWORDS: nvr, hikvision, isapi, snapshot, live, player, camera.

from datetime import datetime
import os
import select
import shutil
import subprocess
import threading
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context
from urllib.parse import urlencode

from auth.decorators import require_permission
from config import CONFIG
from runtime.state import NVR_STATUS


bp = Blueprint("nvr", __name__)

_NVR_API_CACHE_LOCK = threading.Lock()
_NVR_API_CACHE = {}
_NVR_API_CACHE_TTL_SEC = 1.0
_NVR_SNAPSHOT_CACHE_LOCK = threading.Lock()
_NVR_SNAPSHOT_CACHE = {}
_NVR_LIVE_SEMAPHORE = threading.BoundedSemaphore(4)
_NVR_H264_WEBRTC_LIMIT = 8
_NVR_H264_WEBRTC_GUARD_LOCK = threading.Lock()
_NVR_H264_WEBRTC_GUARD = {}


def _nvr_should_cover_player():
    return str(request.args.get("fit") or "").strip().lower() in {"cover", "fill", "full"}


def _nvr_inject_player_fit(body, content_type):
    if not _nvr_should_cover_player():
        return body
    if not str(content_type or "").lower().startswith("text/html"):
        return body
    try:
        html = body.decode("utf-8", errors="ignore")
    except Exception:
        return body
    cover_css = (
        "<style id=\"smart-center-nvr-cover\">"
        "html,body,#root,#app{margin:0!important;width:100%!important;height:100%!important;"
        "overflow:hidden!important;background:#020617!important;}"
        "video,canvas,img{width:100%!important;height:100%!important;object-fit:cover!important;"
        "background:#020617!important;}"
        "video{position:absolute!important;inset:0!important;}"
        "</style>"
    )
    lower = html.lower()
    if "</head>" in lower:
        idx = lower.index("</head>")
        html = html[:idx] + cover_css + html[idx:]
    else:
        html = cover_css + html
    return html.encode("utf-8")


def _terminate_process(proc):
    if not proc:
        return
    try:
        if proc.stdout:
            proc.stdout.close()
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
    except Exception:
        pass




def _nvr_channel_path(channel_id):
    try:
        channel_num = int(str(channel_id).strip())
    except Exception:
        channel_num = 0
    if channel_num <= 0:
        raise ValueError("Invalid NVR channel")
    return f"nvr_ch{channel_num:02d}"


def _nvr_player_path(channel_id, source):
    path_name = _nvr_channel_path(channel_id)
    if str(source or "").strip().lower() in {"h264", "transcode", "preview"}:
        return f"{path_name}_h264"
    return path_name


def _nvr_player_base_url(source):
    return "http://127.0.0.1:8888" if source == "hls" else "http://127.0.0.1:8889"


def _nvr_is_h264_source(source):
    return str(source or "").strip().lower() in {"h264", "transcode", "preview"}


def _nvr_count_active_h264_webrtc_sessions():
    try:
        import json
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9997/v3/webrtcsessions/list", timeout=1.2) as upstream:
            payload = json.loads(upstream.read().decode("utf-8", errors="ignore") or "{}")
        count = 0
        for item in payload.get("items") or []:
            if item.get("peerConnectionEstablished") and str(item.get("path") or "").endswith("_h264"):
                count += 1
        return count
    except Exception:
        return 0


def _nvr_guard_h264_webrtc_request(path_name, source):
    if not _nvr_is_h264_source(source) or not str(path_name or "").endswith("_h264"):
        return True
    current = _nvr_count_active_h264_webrtc_sessions()
    now = time.monotonic()
    with _NVR_H264_WEBRTC_GUARD_LOCK:
        for key, ts in list(_NVR_H264_WEBRTC_GUARD.items()):
            if now - ts > 18:
                _NVR_H264_WEBRTC_GUARD.pop(key, None)
        pending = len(_NVR_H264_WEBRTC_GUARD)
        if current + pending >= _NVR_H264_WEBRTC_LIMIT:
            return False
        _NVR_H264_WEBRTC_GUARD[f"{path_name}:{now:.6f}"] = now
    return True


def _nvr_should_guard_whep_request(asset_path, method):
    # Only the initial WHEP POST creates a new WebRTC session. Follow-up PATCH
    # and DELETE requests belong to that session and must not be rate-limited.
    return str(method or "").upper() == "POST" and str(asset_path or "").strip("/").lower() == "whep"


def _nvr_is_legacy_wall_webrtc_request(asset_path, source):
    if not _nvr_should_guard_whep_request(asset_path, request.method):
        return False
    if not _nvr_is_h264_source(source):
        return False
    if str(request.args.get("wall", "")).strip().lower() in {"1", "true", "yes"}:
        return False
    controls = str(request.args.get("controls", "")).strip().lower()
    return controls in {"", "0", "false", "no"}


def _nvr_legacy_wall_response():
    html = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#020617;color:#dbeafe;font:13px Arial,"Microsoft YaHei",sans-serif;display:grid;place-items:center;text-align:center}
.box{padding:16px 18px;line-height:1.7}.title{font-weight:800;color:#f8fafc;margin-bottom:4px}.hint{color:#94a3b8;font-size:12px}
</style></head><body><div class="box"><div class="title">请刷新监控预览</div><div class="hint">多宫格已切换为智能快照墙，低延迟直播仅用于单路预览。</div></div></body></html>"""
    return Response(html, status=429, mimetype="text/html; charset=utf-8")


def _nvr_webrtc_limit_response():
    html = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#020617;color:#dbeafe;font:13px Arial,"Microsoft YaHei",sans-serif;display:grid;place-items:center;text-align:center}
.box{padding:16px 18px;line-height:1.7}.title{font-weight:800;color:#f8fafc;margin-bottom:4px}.hint{color:#94a3b8;font-size:12px}
</style></head><body><div class="box"><div class="title">低延迟直播会话已满</div><div class="hint">当前最多同时 8 路直播，其余通道请使用抓拍占位或点击切换。</div></div></body></html>"""
    return Response(html, status=429, mimetype="text/html; charset=utf-8")


def _copy_mediamtx_headers(upstream, response, device_id=None, channel_id=None, asset_path=None, source=None):
    passthrough = {"Link", "ETag", "Accept-Patch", "Access-Control-Allow-Origin", "Access-Control-Allow-Credentials"}
    for name in passthrough:
        value = upstream.headers.get(name)
        if value:
            response.headers[name] = value
    location = upstream.headers.get("Location")
    if location and device_id is not None and channel_id is not None and asset_path:
        tail = str(location).rstrip("/").split("/")[-1]
        if tail:
            rewritten = f"/api/nvr/player/{device_id}/{channel_id}/{asset_path.rstrip('/')}/{tail}"
            if source:
                rewritten = f"{rewritten}?{urlencode({'source': source})}"
            response.headers["Location"] = rewritten


def _build_live_commands(ffmpeg_path, rtsp_url, fps, width, quality, hw_mode):
    base_input = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-timeout",
        "5000000",
    ]
    output = [
        "-an",
        "-q:v",
        str(quality),
        "-f",
        "mpjpeg",
        "pipe:1",
    ]
    cpu_command = base_input + [
        "-i",
        rtsp_url,
        "-vf",
        f"fps={fps},scale={width}:-2",
    ] + output
    cuda_command = base_input + [
        "-hwaccel",
        "cuda",
        "-hwaccel_output_format",
        "cuda",
        "-i",
        rtsp_url,
        "-vf",
        f"fps={fps},scale_cuda={width}:-2,hwdownload,format=nv12",
    ] + output
    if hw_mode in {"cuda", "gpu"}:
        return [("cuda", cuda_command)]
    if hw_mode == "cpu":
        return [("cpu", cpu_command)]
    return [("cuda", cuda_command), ("cpu", cpu_command)]


def _truthy_query_arg(name):
    return str(request.args.get(name, "")).strip().lower() in {"1", "true", "yes", "on", "compact", "dashboard"}


def _parse_updated_at(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _default_nvr_status(cfg):
    disabled = cfg.get("enabled", True) is False
    return {
        "online": False,
        "status_level": "offline",
        "status_label": "停用" if disabled else "离线",
        "error": "disabled" if disabled else "等待后台轮询",
        "last_error": "disabled" if disabled else "等待后台轮询",
        "poll_failures": 0,
        "stale": False,
        "updated_at": None,
        "last_checked_at": None,
        "last_success_at": None,
        "summary": {},
        "channels": [],
        "offline_channels": [],
        "hdds": [],
    }


def _apply_status_level(status):
    payload = dict(status or {})
    level = str(payload.get("status_level") or "").strip().lower()
    if level not in {"online", "stale", "error", "offline"}:
        online = bool(payload.get("online"))
        stale = bool(payload.get("stale"))
        has_error = bool(payload.get("last_error") or payload.get("error"))
        if online and stale:
            level = "stale"
        elif online:
            level = "online"
        elif has_error:
            level = "error"
        else:
            level = "offline"
    payload["status_level"] = level
    payload["status_label"] = {
        "online": "正常",
        "stale": "关注",
        "error": "异常",
        "offline": "离线",
    }.get(level, "离线")
    return payload


def _safe_config_payload(cfg):
    return {
        "id": str(cfg.get("id")),
        "name": cfg.get("name") or cfg.get("id"),
        "brand": cfg.get("brand", ""),
        "model": cfg.get("model", ""),
        "protocol": cfg.get("protocol", "Hikvision ISAPI"),
        "host": cfg.get("host", cfg.get("ip", "")),
        "port": cfg.get("port", 80),
        "scheme": cfg.get("scheme", "http"),
        "expected_channel_count": cfg.get("expected_channel_count", 0),
        "poll_interval_ms": cfg.get("poll_interval_ms", 10000),
        "visible": cfg.get("visible", True),
        "enabled": cfg.get("enabled", True),
    }


def _compact_channel(item):
    if not isinstance(item, dict):
        return {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "ip": item.get("ip"),
        "online": bool(item.get("online")),
        "detect_result": item.get("detect_result"),
        "password_status": item.get("password_status"),
    }


def _compact_hdd(item):
    if not isinstance(item, dict):
        return {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "status": item.get("status"),
        "status_text": item.get("status_text"),
        "capacity_text": item.get("capacity_text"),
        "free_text": item.get("free_text"),
        "property": item.get("property"),
    }


def _compact_status(status):
    payload = dict(status or {})
    payload["offline_channels"] = [_compact_channel(item) for item in (payload.get("offline_channels") or [])[:16]]
    payload["channels"] = [_compact_channel(item) for item in (payload.get("channels") or [])[:64]]
    payload["hdds"] = [_compact_hdd(item) for item in (payload.get("hdds") or [])[:4]]
    payload.pop("weak_password_channels", None)
    return payload


def _build_nvr_status_snapshot(cfg):
    device_id = str(cfg.get("id"))
    status = dict(NVR_STATUS.get(device_id, {}) or {})
    if not status:
        status = _default_nvr_status(cfg)
    interval_sec = max(2.0, float(cfg.get("poll_interval_ms", 10000) or 10000) / 1000.0)
    updated_at = _parse_updated_at(status.get("updated_at"))
    last_checked_at = _parse_updated_at(status.get("last_checked_at")) or updated_at
    now = datetime.now()
    cache_age_sec = max(0.0, (now - updated_at).total_seconds()) if updated_at else None
    checked_age_sec = max(0.0, (now - last_checked_at).total_seconds()) if last_checked_at else None
    stale_grace_sec = max(45.0, interval_sec * 4.0)
    if cache_age_sec is not None:
        status["cache_age_sec"] = round(cache_age_sec, 1)
    if checked_age_sec is not None:
        status["last_checked_age_sec"] = round(checked_age_sec, 1)
    status["stale"] = bool(status.get("stale") or (cache_age_sec is not None and cache_age_sec > stale_grace_sec))
    if cfg.get("enabled", True) is False:
        status["online"] = False
        status["status_level"] = "offline"
        status["error"] = "disabled"
        status["last_error"] = "disabled"
    elif status.get("stale") and int(status.get("poll_failures", 0) or 0) >= 3:
        status["online"] = False
        status["status_level"] = "error"
    return _apply_status_level(status)


@bp.route("/api/nvr/status")
@require_permission("snmp.view")
def api_nvr_status():
    compact = _truthy_query_arg("compact") or _truthy_query_arg("summary")
    cache_key = "compact" if compact else "full"
    now = time.monotonic()
    with _NVR_API_CACHE_LOCK:
        cached = _NVR_API_CACHE.get(cache_key)
        if cached and (now - cached["ts"]) <= _NVR_API_CACHE_TTL_SEC:
            return jsonify(cached["data"])

    data = {}
    for cfg in CONFIG.get("nvr_devices", []):
        device_id = str(cfg.get("id"))
        status = _build_nvr_status_snapshot(cfg)
        status["config"] = _safe_config_payload(cfg)
        if compact:
            status = _compact_status(status)
        data[device_id] = status

    with _NVR_API_CACHE_LOCK:
        _NVR_API_CACHE[cache_key] = {"data": data, "ts": time.monotonic()}
    return jsonify(data)


@bp.route("/api/nvr/snapshot/<device_id>/<channel_id>")
@require_permission("snmp.view")
def api_nvr_snapshot(device_id, channel_id):
    cfg = next((item for item in CONFIG.get("nvr_devices", []) if str(item.get("id")) == str(device_id)), None)
    if not cfg or cfg.get("enabled", True) is False:
        return jsonify({"success": False, "message": "未找到可用录像机配置"}), 404
    stream = str(request.args.get("stream") or cfg.get("snapshot_stream") or "2").strip() or "2"
    try:
        ttl_sec = max(0.0, min(float(cfg.get("snapshot_cache_ttl_sec", 1.5) or 1.5), 15.0))
    except Exception:
        ttl_sec = 1.5
    cache_key = (str(device_id), str(channel_id), stream)
    now = time.monotonic()
    if ttl_sec > 0:
        with _NVR_SNAPSHOT_CACHE_LOCK:
            cached = _NVR_SNAPSHOT_CACHE.get(cache_key)
            if cached and (now - cached["ts"]) <= ttl_sec:
                response = Response(cached["body"], mimetype=cached["content_type"])
                response.headers["Cache-Control"] = "no-store, max-age=0"
                return response
    try:
        from services.hikvision_nvr import fetch_hikvision_snapshot

        body, content_type = fetch_hikvision_snapshot(cfg, channel_id, stream=stream)
        if not body:
            raise RuntimeError("empty snapshot")
        if ttl_sec > 0:
            with _NVR_SNAPSHOT_CACHE_LOCK:
                _NVR_SNAPSHOT_CACHE[cache_key] = {"body": body, "content_type": content_type, "ts": time.monotonic()}
        response = Response(body, mimetype=content_type)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    except Exception as exc:
        return jsonify({"success": False, "message": f"抓拍失败: {exc}"}), 502




@bp.route("/api/nvr/player/<device_id>/<channel_id>/")
@bp.route("/api/nvr/player/<device_id>/<channel_id>")
@require_permission("snmp.view")
def api_nvr_player(device_id, channel_id):
    cfg = next((item for item in CONFIG.get("nvr_devices", []) if str(item.get("id")) == str(device_id)), None)
    if not cfg or cfg.get("enabled", True) is False:
        return Response("未找到可用录像机配置", status=404, mimetype="text/plain; charset=utf-8")
    try:
        path_name = _nvr_player_path(channel_id, request.args.get("source") or "h264")
    except Exception:
        return Response("无效通道", status=400, mimetype="text/plain; charset=utf-8")
    source = str(request.args.get("source") or "h264").strip().lower()
    autoplay = "true" if str(request.args.get("autoplay", "1")).lower() not in {"0", "false", "no"} else "false"
    muted = "true" if str(request.args.get("muted", "1")).lower() not in {"0", "false", "no"} else "false"
    controls = "true" if str(request.args.get("controls", "0")).lower() in {"1", "true", "yes"} else "false"
    base_url = _nvr_player_base_url(source)
    upstream_url = f"{base_url}/{path_name}/?autoplay={autoplay}&muted={muted}&controls={controls}&playsinline=1&disablepictureinpicture=1"
    try:
        import urllib.request
        with urllib.request.urlopen(upstream_url, timeout=5) as upstream:
            body = upstream.read()
            content_type = upstream.headers.get("Content-Type") or "text/html; charset=utf-8"
    except Exception as exc:
        html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><style>html,body{{margin:0;height:100%;background:#020617;color:#cbd5e1;font:13px Arial;display:grid;place-items:center;text-align:center}}</style></head><body>视频中继连接失败<br>{exc}</body></html>"""
        return Response(html, status=502, mimetype="text/html; charset=utf-8")
    body = _nvr_inject_player_fit(body, content_type)
    response = Response(body, mimetype=content_type)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/nvr/player/<device_id>/<channel_id>/<path:asset_path>", methods=["GET", "HEAD", "OPTIONS", "POST", "PATCH", "DELETE"])
@require_permission("snmp.view")
def api_nvr_player_asset(device_id, channel_id, asset_path):
    cfg = next((item for item in CONFIG.get("nvr_devices", []) if str(item.get("id")) == str(device_id)), None)
    if not cfg or cfg.get("enabled", True) is False:
        return Response("未找到可用录像机配置", status=404, mimetype="text/plain; charset=utf-8")
    try:
        path_name = _nvr_player_path(channel_id, request.args.get("source") or "h264")
    except Exception:
        return Response("无效通道", status=400, mimetype="text/plain; charset=utf-8")
    source = str(request.args.get("source") or "h264").strip().lower()
    if _nvr_is_legacy_wall_webrtc_request(asset_path, source):
        return _nvr_legacy_wall_response()
    if _nvr_should_guard_whep_request(asset_path, request.method) and not _nvr_guard_h264_webrtc_request(path_name, source):
        return _nvr_webrtc_limit_response()
    base_url = _nvr_player_base_url(source)
    query = request.query_string.decode("utf-8", errors="ignore")
    upstream_url = f"{base_url}/{path_name}/{asset_path}" + (f"?{query}" if query else "")
    try:
        import urllib.error
        import urllib.request
        headers = {}
        for name in ("Content-Type", "If-Match", "Authorization"):
            value = request.headers.get(name)
            if value:
                headers[name] = value
        upstream_request = urllib.request.Request(
            upstream_url,
            data=request.get_data() if request.method in {"POST", "PATCH", "DELETE"} else None,
            headers=headers,
            method=request.method,
        )
        try:
            upstream = urllib.request.urlopen(upstream_request, timeout=15)
        except urllib.error.HTTPError as exc:
            upstream = exc
        with upstream:
            body = b"" if request.method == "HEAD" else upstream.read()
            content_type = upstream.headers.get("Content-Type") or "application/octet-stream"
            status = upstream.status
    except Exception as exc:
        return Response(str(exc), status=502, mimetype="text/plain; charset=utf-8")
    response = Response(body, status=status, mimetype=content_type)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    _copy_mediamtx_headers(upstream, response, device_id=device_id, channel_id=channel_id, asset_path=asset_path, source=source)
    return response

@bp.route("/api/nvr/live/<device_id>/<channel_id>")
@require_permission("snmp.view")
def api_nvr_live(device_id, channel_id):
    cfg = next((item for item in CONFIG.get("nvr_devices", []) if str(item.get("id")) == str(device_id)), None)
    if not cfg or cfg.get("enabled", True) is False:
        return jsonify({"success": False, "message": "未找到可用录像机配置"}), 404
    if not _NVR_LIVE_SEMAPHORE.acquire(blocking=False):
        return jsonify({"success": False, "message": "实时预览连接数已满，请关闭其他预览后重试"}), 429
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        _NVR_LIVE_SEMAPHORE.release()
        return jsonify({"success": False, "message": "服务器未安装 ffmpeg，无法实时预览"}), 500
    stream = str(request.args.get("stream") or cfg.get("live_stream") or cfg.get("snapshot_stream") or "2").strip() or "2"
    try:
        fps = max(1, min(int(float(request.args.get("fps") or cfg.get("live_fps", 8) or 8)), 15))
    except Exception:
        fps = 8
    try:
        width = max(320, min(int(float(request.args.get("width") or cfg.get("live_width", 960) or 960)), 1920))
    except Exception:
        width = 960
    try:
        quality = max(3, min(int(float(request.args.get("quality") or cfg.get("live_quality", 7) or 7)), 18))
    except Exception:
        quality = 7
    hw_mode = str(request.args.get("hw") or cfg.get("live_hwaccel") or "auto").strip().lower()
    if hw_mode not in {"auto", "cuda", "gpu", "cpu"}:
        hw_mode = "auto"
    try:
        from services.hikvision_nvr import build_hikvision_rtsp_url

        rtsp_url = build_hikvision_rtsp_url(cfg, channel_id, stream=stream)
    except Exception as exc:
        _NVR_LIVE_SEMAPHORE.release()
        return jsonify({"success": False, "message": f"实时预览地址生成失败: {exc}"}), 400

    commands = _build_live_commands(ffmpeg_path, rtsp_url, fps, width, quality, hw_mode)

    def generate():
        proc = None
        try:
            for _, command in commands:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
                fd = proc.stdout.fileno() if proc.stdout else None
                # CUDA startup can take a few seconds on the first RTSP session; wait
                # long enough to avoid falling back just before the first frame arrives.
                ready, _, _ = select.select([fd], [], [], 8.0) if fd is not None else ([], [], [])
                if ready:
                    break
                _terminate_process(proc)
                proc = None
            if not proc or not proc.stdout:
                return
            fd = proc.stdout.fileno()
            while True:
                ready, _, _ = select.select([fd], [], [], 1.0)
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            _terminate_process(proc)
            _NVR_LIVE_SEMAPHORE.release()

    response = Response(stream_with_context(generate()), mimetype="multipart/x-mixed-replace; boundary=ffmpeg")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Accel-Buffering"] = "no"
    return response
