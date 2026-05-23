import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context


APP = Flask(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".wav",
    ".ogg",
    ".wma",
    ".aiff",
    ".ape",
}

CACHE_FILE = Path(os.environ.get("MUSIC_TAG_CACHE_FILE", "/data/library_cache.json")).resolve()
ALLOWED_ROOTS = [
    Path(item.strip()).resolve()
    for item in str(os.environ.get("MUSIC_TAG_ALLOWED_ROOTS", "/music")).split(",")
    if item.strip()
]
DEFAULT_ROOTS = [
    Path(item.strip()).resolve()
    for item in str(os.environ.get("MUSIC_TAG_DEFAULT_ROOTS", "/music")).split(",")
    if item.strip()
]
EXCLUDE_DIRS = [item.strip().lower() for item in str(os.environ.get("MUSIC_TAG_EXCLUDE_DIRS", "@eaDir,tmp,cache")).split(",") if item.strip()]
AUTO_SCAN_ON_START = str(os.environ.get("MUSIC_TAG_AUTO_SCAN_ON_START", "1")).strip() not in {"0", "false", "False"}
MAX_SCAN_FILES = max(1000, min(int(os.environ.get("MUSIC_TAG_MAX_SCAN_FILES", "60000")), 250000))

LIBRARY = []
LIBRARY_BY_ID = {}
STATE = {
    "scan_running": False,
    "scan_count": 0,
    "last_scan_at": "",
    "scan_ms": 0,
    "scan_errors": [],
}


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _ensure_cache_parent():
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _is_under_allowed_roots(path: Path):
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in ALLOWED_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except Exception:
            continue
    return False


def _safe_relative(path: Path, root: Path):
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return path.name


def _try_decode_text(raw):
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            text = raw.decode(enc, errors="ignore").strip("\x00 ").strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def _read_id3v1_tag(path: Path):
    try:
        with path.open("rb") as fh:
            fh.seek(-128, os.SEEK_END)
            chunk = fh.read(128)
    except Exception:
        return {}
    if len(chunk) != 128 or chunk[:3] != b"TAG":
        return {}
    return {
        "title": _try_decode_text(chunk[3:33]),
        "artist": _try_decode_text(chunk[33:63]),
        "album": _try_decode_text(chunk[63:93]),
        "year": _try_decode_text(chunk[93:97]),
    }


def _track_from_file(path: Path, root: Path):
    stat = path.stat()
    tag = _read_id3v1_tag(path)
    title = tag.get("title") or path.stem
    artist = tag.get("artist") or "Unknown Artist"
    album = tag.get("album") or "Unknown Album"
    ext = path.suffix.lower().replace(".", "")
    track_id_source = f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
    track_id = hashlib.sha1(track_id_source.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "album": album,
        "duration": 0,
        "tag": ext.upper(),
        "accent": (artist[:1] or title[:1] or "M").upper(),
        "path": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime": int(stat.st_mtime),
        "year": tag.get("year") or "",
        "relative_path": _safe_relative(path, root),
        "stream_url": f"/api/music-tag/stream/{track_id}",
    }


def _is_excluded(candidate: Path):
    text = str(candidate).lower().replace("\\", "/")
    for name in EXCLUDE_DIRS:
        if text.endswith("/" + name) or ("/" + name + "/") in text:
            return True
    return False


def _load_cache():
    global LIBRARY, LIBRARY_BY_ID
    try:
        if not CACHE_FILE.exists():
            return
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        tracks = payload.get("tracks", [])
        if not isinstance(tracks, list):
            return
        parsed = []
        by_id = {}
        for item in tracks:
            if not isinstance(item, dict):
                continue
            track_id = str(item.get("id") or "").strip()
            path = str(item.get("path") or "").strip()
            if not track_id or not path:
                continue
            parsed.append(item)
            by_id[track_id] = item
        LIBRARY = parsed
        LIBRARY_BY_ID = by_id
        STATE["scan_count"] = len(parsed)
        STATE["last_scan_at"] = str(payload.get("last_scan_at") or "")
    except Exception:
        return


def _save_cache():
    _ensure_cache_parent()
    payload = {
        "last_scan_at": STATE.get("last_scan_at", ""),
        "scan_count": len(LIBRARY),
        "tracks": LIBRARY,
    }
    CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _scan_roots(roots):
    tracks = []
    errors = []
    count = 0
    for raw_root in roots:
        root = Path(str(raw_root).strip()).expanduser()
        if not root.is_absolute():
            root = root.resolve()
        if not _is_under_allowed_roots(root):
            errors.append(f"root not allowed: {root}")
            continue
        if not root.exists():
            errors.append(f"root not found: {root}")
            continue
        if not root.is_dir():
            errors.append(f"root is not directory: {root}")
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dir_path = Path(dirpath)
            dirnames[:] = [name for name in dirnames if not _is_excluded(dir_path / name)]
            for file_name in filenames:
                if count >= MAX_SCAN_FILES:
                    errors.append(f"scan limit reached ({MAX_SCAN_FILES})")
                    return tracks, errors, count
                path = dir_path / file_name
                if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                    continue
                try:
                    tracks.append(_track_from_file(path, root))
                    count += 1
                except Exception as ex:
                    errors.append(f"{path}: {ex}")
    return tracks, errors, count


def scan_library(roots=None):
    global LIBRARY, LIBRARY_BY_ID
    roots = roots or DEFAULT_ROOTS
    started = time.monotonic()
    STATE["scan_running"] = True
    tracks, errors, _ = _scan_roots(roots)
    tracks.sort(key=lambda item: (
        str(item.get("artist") or "").lower(),
        str(item.get("album") or "").lower(),
        str(item.get("title") or "").lower(),
    ))
    LIBRARY = tracks
    LIBRARY_BY_ID = {item["id"]: item for item in tracks}
    STATE["scan_running"] = False
    STATE["scan_count"] = len(tracks)
    STATE["last_scan_at"] = _now_iso()
    STATE["scan_ms"] = int((time.monotonic() - started) * 1000)
    STATE["scan_errors"] = errors[:50]
    _save_cache()
    return STATE.copy()


def _search(query, limit=300):
    text = str(query or "").strip().lower()
    if not text:
        return LIBRARY[:limit]
    results = []
    for item in LIBRARY:
        haystack = " ".join([
            str(item.get("title") or ""),
            str(item.get("artist") or ""),
            str(item.get("album") or ""),
            str(item.get("tag") or ""),
            str(item.get("relative_path") or ""),
        ]).lower()
        if text in haystack:
            results.append(item)
            if len(results) >= limit:
                break
    return results


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


@APP.get("/")
def index():
    return (
        "<html><head><meta charset='utf-8'><title>Music Tag Web</title></head>"
        "<body style='font-family:Segoe UI,Arial;padding:24px;'>"
        "<h2>Music Tag Web</h2>"
        f"<p>Tracks: <b>{len(LIBRARY)}</b></p>"
        f"<p>Last Scan: <b>{STATE.get('last_scan_at') or '--'}</b></p>"
        "<p>API: /api/music-tag/health /api/music-tag/library /api/music-tag/rescan</p>"
        "</body></html>"
    )


@APP.get("/api/music-tag/health")
def api_health():
    return jsonify(
        {
            "ok": True,
            "service": "music_tag_web",
            "tracks": len(LIBRARY),
            "scan": STATE,
        }
    )


@APP.get("/api/music-tag/library")
def api_library():
    query = request.args.get("q", "")
    try:
        limit = max(1, min(int(request.args.get("limit", 300)), 2000))
    except Exception:
        limit = 300
    results = _search(query, limit=limit)
    return jsonify({"ok": True, "count": len(results), "results": results})


@APP.post("/api/music-tag/rescan")
def api_rescan():
    payload = request.get_json(silent=True) or {}
    raw_roots = payload.get("roots")
    if isinstance(raw_roots, list) and raw_roots:
        roots = [Path(str(item).strip()) for item in raw_roots if str(item).strip()]
    else:
        roots = DEFAULT_ROOTS
    scan_state = scan_library(roots=roots)
    return jsonify({"ok": True, "scan": scan_state, "tracks": len(LIBRARY)})


@APP.get("/api/music-tag/stream/<track_id>")
def api_stream(track_id):
    track = LIBRARY_BY_ID.get(str(track_id or "").strip())
    if not track:
        return jsonify({"ok": False, "message": "track not found"}), 404
    path = Path(str(track.get("path") or ""))
    if not path.exists() or not path.is_file():
        return jsonify({"ok": False, "message": "audio file missing"}), 404
    if not _is_under_allowed_roots(path):
        return jsonify({"ok": False, "message": "file path not allowed"}), 403
    file_size = path.stat().st_size
    range_header = request.headers.get("Range", "")
    guessed_type, _ = mimetypes.guess_type(path.name)
    mime_type = guessed_type or "application/octet-stream"
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


if __name__ == "__main__":
    _load_cache()
    if AUTO_SCAN_ON_START and not LIBRARY:
        scan_library()
    host = os.environ.get("MUSIC_TAG_HOST", "0.0.0.0")
    port = int(os.environ.get("MUSIC_TAG_PORT", "6902"))
    APP.run(host=host, port=port, debug=False)
