import base64
import hashlib
import json
import math
import mimetypes
import os
import re
import struct
import threading
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from config import CONFIG
from paths import DATA_DIR, ensure_directory, ensure_parent_dir

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

try:
    from mutagen.mp4 import MP4Cover
except Exception:
    MP4Cover = None


MUSIC_CACHE_FILE = ensure_parent_dir(DATA_DIR / "music_tag_library.json")
COVER_CACHE_DIR = ensure_directory(DATA_DIR / "music_tag_covers")

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

COVER_FILE_CANDIDATES = [
    "cover.jpg",
    "cover.jpeg",
    "folder.jpg",
    "folder.jpeg",
    "front.jpg",
    "front.jpeg",
    "album.jpg",
    "album.jpeg",
    "cover.png",
    "folder.png",
    "front.png",
    "album.png",
    "cover.webp",
    "folder.webp",
]

LRC_TIME_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")

DEFAULT_OUTPUTS = [
    {
        "id": "nas_player_main",
        "name": "NAS 主播放",
        "host": "本机服务",
        "mode": "HTTP Stream",
        "level": "70%",
        "active": True,
    },
    {
        "id": "nas_zone_2",
        "name": "分区输出 2",
        "host": "待配置",
        "mode": "Zone Feed",
        "level": "--",
        "active": False,
    },
]

DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "nas_music_tag",
    "player_mode": "nas_http",
    "player_host": "",
    "output_mode": "system_default",
    "auth_state": "NAS music tag ready",
    "outputs": DEFAULT_OUTPUTS,
    "nas_music_roots": [],
    "nas_music_exclude_dirs": [],
    "nas_auto_scan_on_start": True,
}


def _try_decode_text(raw):
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip("\x00 ").strip()
    if isinstance(raw, bytes):
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                text = raw.decode(enc, errors="ignore").strip("\x00 ").strip()
                if text:
                    return text
            except Exception:
                continue
        return ""
    text = str(raw).strip("\x00 ").strip()
    return text


def _flatten_text_values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_flatten_text_values(item))
        return out
    if isinstance(value, bytes):
        text = _try_decode_text(value)
        return [text] if text else []
    if hasattr(value, "text"):
        return _flatten_text_values(getattr(value, "text", None))
    if hasattr(value, "value"):
        return _flatten_text_values(getattr(value, "value", None))
    text = _try_decode_text(value)
    return [text] if text else []


def _first_non_empty_text(values):
    for item in values:
        text = _try_decode_text(item)
        if text:
            return text
    return ""


def _join_non_empty_text(values, sep=" / "):
    out = []
    for item in values:
        text = _try_decode_text(item)
        if text and text not in out:
            out.append(text)
    return sep.join(out)


def _parse_year(text):
    value = _try_decode_text(text)
    if not value:
        return ""
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else ""


def _parse_track_no(value):
    text = _try_decode_text(value)
    if not text:
        return 0
    match = re.search(r"\d+", text)
    if not match:
        return 0
    try:
        return int(match.group(0))
    except Exception:
        return 0


def _guess_image_ext(mime):
    mime_text = str(mime or "").strip().lower()
    if "png" in mime_text:
        return ".png"
    if "webp" in mime_text:
        return ".webp"
    if "gif" in mime_text:
        return ".gif"
    return ".jpg"


def _guess_mime(path: Path, fallback="application/octet-stream"):
    mime, _ = mimetypes.guess_type(path.name)
    return mime or fallback


def _safe_relative(path: Path, root: Path):
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return path.name


def _read_id3v1_tag(path: Path):
    try:
        with path.open("rb") as fh:
            fh.seek(-128, os.SEEK_END)
            chunk = fh.read(128)
    except Exception:
        return {}
    if len(chunk) != 128 or chunk[:3] != b"TAG":
        return {}
    title = _try_decode_text(chunk[3:33])
    artist = _try_decode_text(chunk[33:63])
    album = _try_decode_text(chunk[63:93])
    year = _try_decode_text(chunk[93:97])
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "year": year,
    }


def _load_audio(path: Path):
    if MutagenFile is None:
        return None, None, 0.0
    try:
        audio = MutagenFile(path)
    except Exception:
        return None, None, 0.0
    if audio is None:
        return None, None, 0.0
    tags = getattr(audio, "tags", None)
    duration = 0.0
    info = getattr(audio, "info", None)
    if info is not None:
        try:
            duration = float(getattr(info, "length", 0.0) or 0.0)
            if not math.isfinite(duration):
                duration = 0.0
        except Exception:
            duration = 0.0
    return audio, tags, duration


def _pick_tag_text(tags, keys):
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        texts = _flatten_text_values(value)
        text = _first_non_empty_text(texts)
        if text:
            return text
    return ""


def _pick_tag_join(tags, keys, sep=" / "):
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        texts = _flatten_text_values(value)
        text = _join_non_empty_text(texts, sep=sep)
        if text:
            return text
    return ""


def _decode_flac_picture_block(raw):
    try:
        data = base64.b64decode(raw)
    except Exception:
        return b"", ""
    try:
        offset = 0
        if len(data) < 8:
            return b"", ""
        _pic_type = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        mime_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        mime_raw = data[offset : offset + mime_len]
        offset += mime_len
        desc_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        offset += desc_len
        offset += 4 * 4
        data_len = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        image_data = data[offset : offset + data_len]
        mime = _try_decode_text(mime_raw) or "image/jpeg"
        if image_data:
            return image_data, mime
    except Exception:
        return b"", ""
    return b"", ""


def _parse_lrc_text(text):
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return []
    lines = []
    for source_line in raw.split("\n"):
        source_line = source_line.strip()
        if not source_line:
            continue
        time_matches = list(LRC_TIME_RE.finditer(source_line))
        if not time_matches:
            continue
        lyric_text = LRC_TIME_RE.sub("", source_line).strip()
        for match in time_matches:
            mm = int(match.group(1))
            ss = int(match.group(2))
            fraction = match.group(3) or ""
            if len(fraction) == 1:
                ms = int(fraction) * 100
            elif len(fraction) == 2:
                ms = int(fraction) * 10
            elif len(fraction) >= 3:
                ms = int(fraction[:3])
            else:
                ms = 0
            ts_ms = mm * 60 * 1000 + ss * 1000 + ms
            lines.append(
                {
                    "ts_ms": int(ts_ms),
                    "text": lyric_text,
                }
            )
    lines.sort(key=lambda item: (int(item.get("ts_ms", 0)), str(item.get("text") or "")))
    return lines


def _normalize_lyrics_payload(track, lyrics_type="none", plain_text="", lines=None, source="", lang=""):
    clean_lines = []
    for item in lines or []:
        text = _try_decode_text(item.get("text", ""))
        if not text:
            continue
        try:
            ts_ms = int(item.get("ts_ms", 0))
        except Exception:
            ts_ms = 0
        clean_lines.append({"ts_ms": max(0, ts_ms), "text": text})
    clean_lines.sort(key=lambda row: (row["ts_ms"], row["text"]))
    plain = _try_decode_text(plain_text)
    if not plain and clean_lines:
        plain = "\n".join(row["text"] for row in clean_lines)
    safe_type = lyrics_type if lyrics_type in {"synced", "plain", "none"} else "none"
    if not plain and not clean_lines:
        safe_type = "none"
    return {
        "track_id": str(track.get("id") or ""),
        "title": str(track.get("title") or ""),
        "artist": str(track.get("artist") or ""),
        "album": str(track.get("album") or ""),
        "lyrics_available": safe_type != "none",
        "lyrics_type": safe_type,
        "plain": plain,
        "lines": clean_lines,
        "source": str(source or ""),
        "lang": str(lang or ""),
        "updated_at": datetime.now().isoformat(),
    }


def _find_lyrics_sidecar(audio_path: Path):
    base = audio_path.with_suffix("")
    candidates = [
        base.with_suffix(".lrc"),
        base.with_suffix(".LRC"),
        base.with_suffix(".txt"),
        base.with_suffix(".TXT"),
    ]
    for item in candidates:
        if item.exists() and item.is_file():
            return item
    return None


def _derive_category(relative_path: str, root_name: str):
    rel = str(relative_path or "").replace("\\", "/").strip("/")
    if not rel:
        return "未分类"
    if "/" in rel:
        first = rel.split("/", 1)[0].strip()
        return first or "未分类"
    if "." in rel:
        return "未分类"
    return rel or (root_name or "未分类")


class AppleAudioService:
    def __init__(self, *, auto_scan=None):
        self.lock = threading.Lock()
        self.last_tick = time.monotonic()
        self.library = []
        self.library_by_id = {}
        self.lyrics_cache = {}
        self.state = {
            "connected": True,
            "provider": "nas_music_tag",
            "player_mode": "nas_http",
            "player_host": "",
            "output_mode": "system_default",
            "auth_state": "NAS music tag ready",
            "is_playing": False,
            "elapsed_sec": 0,
            "current_track_id": "",
            "queue_ids": [],
            "outputs": deepcopy(DEFAULT_OUTPUTS),
            "last_action": "",
            "updated_at": datetime.now().isoformat(),
            "last_scan_at": "",
            "scan_running": False,
            "scan_count": 0,
            "scan_stage": "idle",
            "scan_processed": 0,
            "scan_total": 0,
            "scan_progress": 0,
            "scan_message": "",
            "scan_errors": [],
            "scan_ms": 0,
        }
        self.configure()
        self._load_library_cache()
        should_scan = self._config().get("nas_auto_scan_on_start", True) if auto_scan is None else bool(auto_scan)
        if should_scan:
            self.scan_library()

    def _config(self):
        cfg = CONFIG.get("apple_audio", {}) or {}
        merged = deepcopy(DEFAULT_CONFIG)
        if isinstance(cfg, dict):
            for key, value in cfg.items():
                merged[key] = value
        roots = merged.get("nas_music_roots", [])
        if not isinstance(roots, list):
            roots = []
        merged["nas_music_roots"] = [str(item or "").strip() for item in roots if str(item or "").strip()]
        excludes = merged.get("nas_music_exclude_dirs", [])
        if not isinstance(excludes, list):
            excludes = []
        merged["nas_music_exclude_dirs"] = [str(item or "").strip() for item in excludes if str(item or "").strip()]
        if not isinstance(merged.get("outputs"), list) or not merged.get("outputs"):
            merged["outputs"] = deepcopy(DEFAULT_OUTPUTS)
        return merged

    def configure(self, cfg=None):
        cfg = cfg or self._config()
        with self.lock:
            self.state["provider"] = str(cfg.get("provider", "nas_music_tag") or "nas_music_tag")
            self.state["player_mode"] = str(cfg.get("player_mode", "nas_http") or "nas_http")
            self.state["player_host"] = str(cfg.get("player_host", "") or "").strip()
            self.state["output_mode"] = str(cfg.get("output_mode", "system_default") or "system_default")
            self.state["auth_state"] = str(cfg.get("auth_state", "NAS music tag ready") or "NAS music tag ready")
            self.state["connected"] = bool(cfg.get("enabled", True))
            self.state["outputs"] = deepcopy(cfg.get("outputs", DEFAULT_OUTPUTS))
            self.state["updated_at"] = datetime.now().isoformat()

    def _detect_lyrics_flags(self, path: Path, tags):
        has_plain = False
        has_synced = False

        if tags:
            if hasattr(tags, "getall"):
                try:
                    if tags.getall("SYLT"):
                        has_synced = True
                except Exception:
                    pass
                try:
                    if tags.getall("USLT"):
                        has_plain = True
                except Exception:
                    pass

            tag_plain = _pick_tag_text(
                tags,
                [
                    "lyrics",
                    "LYRICS",
                    "unsyncedlyrics",
                    "USLT",
                    "\xa9lyr",
                    "----:com.apple.iTunes:LYRICS",
                    "----:com.apple.iTunes:lyrics",
                ],
            )
            if tag_plain:
                has_plain = True

        sidecar = _find_lyrics_sidecar(path)
        if sidecar:
            if sidecar.suffix.lower() == ".lrc":
                try:
                    text = sidecar.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = sidecar.read_text(encoding="gbk", errors="ignore")
                except Exception:
                    text = ""
                parsed_lines = _parse_lrc_text(text)
                if parsed_lines:
                    has_synced = True
                elif text.strip():
                    has_plain = True
            else:
                has_plain = True

        if has_synced:
            return True, "synced"
        if has_plain:
            return True, "plain"
        return False, "none"

    def _extract_cover_from_tags(self, audio, tags):
        if tags and hasattr(tags, "getall"):
            try:
                apics = tags.getall("APIC")
            except Exception:
                apics = []
            for frame in apics or []:
                try:
                    data = bytes(getattr(frame, "data", b"") or b"")
                except Exception:
                    data = b""
                if data:
                    mime = _try_decode_text(getattr(frame, "mime", "")) or "image/jpeg"
                    return data, mime

        pictures = getattr(audio, "pictures", None) if audio is not None else None
        if pictures:
            for pic in pictures:
                try:
                    data = bytes(getattr(pic, "data", b"") or b"")
                except Exception:
                    data = b""
                if data:
                    mime = _try_decode_text(getattr(pic, "mime", "")) or "image/jpeg"
                    return data, mime

        if tags:
            try:
                covr = tags.get("covr")
            except Exception:
                covr = None
            if covr:
                try:
                    first = covr[0]
                except Exception:
                    first = None
                if first is not None:
                    try:
                        data = bytes(first)
                    except Exception:
                        data = b""
                    if data:
                        mime = "image/jpeg"
                        if MP4Cover is not None and hasattr(first, "imageformat"):
                            if getattr(first, "imageformat", None) == MP4Cover.FORMAT_PNG:
                                mime = "image/png"
                        return data, mime

            try:
                block_list = tags.get("metadata_block_picture") or []
            except Exception:
                block_list = []
            for raw in block_list:
                data, mime = _decode_flac_picture_block(raw)
                if data:
                    return data, mime or "image/jpeg"

        return b"", ""

    def _find_folder_cover(self, directory: Path, folder_cover_cache):
        key = str(directory.resolve())
        if key in folder_cover_cache:
            return folder_cover_cache[key]
        result = None
        try:
            entries = {}
            with os.scandir(directory) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    entries[entry.name.lower()] = entry.path
            for candidate in COVER_FILE_CANDIDATES:
                found = entries.get(candidate)
                if found:
                    cover_path = Path(found).resolve()
                    result = (str(cover_path), _guess_mime(cover_path, fallback="image/jpeg"))
                    break
        except Exception:
            result = None
        folder_cover_cache[key] = result
        return result

    def _purge_track_cover_cache(self, track_id):
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bin"):
            candidate = COVER_CACHE_DIR / f"{track_id}{ext}"
            if candidate.exists():
                try:
                    candidate.unlink()
                except Exception:
                    pass

    def _store_embedded_cover(self, track_id, image_bytes, mime):
        if not image_bytes:
            return ""
        ext = _guess_image_ext(mime)
        target = (COVER_CACHE_DIR / f"{track_id}{ext}").resolve()
        self._purge_track_cover_cache(track_id)
        try:
            target.write_bytes(image_bytes)
        except Exception:
            return ""
        return str(target)

    def _extract_metadata(self, path: Path):
        tag_fallback = _read_id3v1_tag(path)
        audio, tags, duration = _load_audio(path)

        title = _pick_tag_text(tags, ["title", "TIT2", "\xa9nam"]) or tag_fallback.get("title") or path.stem
        artist = _pick_tag_join(tags, ["artist", "TPE1", "\xa9ART"], sep=" / ") or tag_fallback.get("artist") or "Unknown Artist"
        album = _pick_tag_text(tags, ["album", "TALB", "\xa9alb"]) or tag_fallback.get("album") or "Unknown Album"
        album_artist = _pick_tag_join(tags, ["albumartist", "TPE2", "aART"], sep=" / ")
        genre = _pick_tag_join(tags, ["genre", "TCON", "\xa9gen"], sep=" / ")
        year = _parse_year(
            _pick_tag_text(tags, ["date", "TDRC", "\xa9day", "TYER"]) or tag_fallback.get("year") or ""
        )
        track_no = _parse_track_no(_pick_tag_text(tags, ["tracknumber", "TRCK", "trkn"]))

        return {
            "audio": audio,
            "tags": tags,
            "duration": int(max(0, round(duration))),
            "title": title,
            "artist": artist,
            "album": album,
            "album_artist": album_artist,
            "genre": genre,
            "year": year,
            "track_no": track_no,
        }

    def _extract_lyrics_from_tags(self, tags):
        if not tags:
            return None

        synced_lines = []
        if hasattr(tags, "getall"):
            try:
                sylt_frames = tags.getall("SYLT")
            except Exception:
                sylt_frames = []
            for frame in sylt_frames or []:
                for entry in getattr(frame, "text", []) or []:
                    text = ""
                    ts_raw = 0
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        text = _try_decode_text(entry[0])
                        ts_raw = entry[1]
                    elif isinstance(entry, str):
                        text = _try_decode_text(entry)
                        ts_raw = 0
                    else:
                        text = _try_decode_text(entry)
                        ts_raw = 0
                    if not text:
                        continue
                    try:
                        ts_ms = int(ts_raw)
                    except Exception:
                        ts_ms = 0
                    synced_lines.append({"ts_ms": max(0, ts_ms), "text": text})
                if synced_lines:
                    return _normalize_lyrics_payload({}, lyrics_type="synced", lines=synced_lines, source="tag_sylt")

            try:
                uslt_frames = tags.getall("USLT")
            except Exception:
                uslt_frames = []
            for frame in uslt_frames or []:
                text = _try_decode_text(getattr(frame, "text", ""))
                if text:
                    lang = _try_decode_text(getattr(frame, "lang", ""))
                    return _normalize_lyrics_payload({}, lyrics_type="plain", plain_text=text, source="tag_uslt", lang=lang)

        plain = _pick_tag_text(
            tags,
            [
                "lyrics",
                "LYRICS",
                "unsyncedlyrics",
                "\xa9lyr",
                "----:com.apple.iTunes:LYRICS",
                "----:com.apple.iTunes:lyrics",
            ],
        )
        if plain:
            return _normalize_lyrics_payload({}, lyrics_type="plain", plain_text=plain, source="tag_plain")

        return None

    def _extract_lyrics_from_sidecar(self, path: Path):
        sidecar = _find_lyrics_sidecar(path)
        if not sidecar:
            return None
        try:
            try:
                text = sidecar.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = sidecar.read_text(encoding="gbk", errors="ignore")
        except Exception:
            return None
        if not text.strip():
            return None
        if sidecar.suffix.lower() == ".lrc":
            lines = _parse_lrc_text(text)
            if lines:
                return _normalize_lyrics_payload({}, lyrics_type="synced", lines=lines, source="sidecar_lrc")
        return _normalize_lyrics_payload({}, lyrics_type="plain", plain_text=text, source="sidecar_text")

    def _resolve_track_cover(self, path: Path, track_id: str, audio, tags, folder_cover_cache):
        embedded_bytes, embedded_mime = self._extract_cover_from_tags(audio, tags)
        if embedded_bytes:
            cached_path = self._store_embedded_cover(track_id, embedded_bytes, embedded_mime)
            if cached_path:
                return True, "embedded", embedded_mime, cached_path
        folder_cover = self._find_folder_cover(path.parent, folder_cover_cache)
        if folder_cover:
            cover_path, cover_mime = folder_cover
            return True, "folder", cover_mime, cover_path
        return False, "none", "", ""

    def _to_track(self, path: Path, root: Path, folder_cover_cache):
        stat = path.stat()
        ext = path.suffix.lower().replace(".", "")
        track_id_source = f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
        track_id = hashlib.sha1(track_id_source.encode("utf-8", errors="ignore")).hexdigest()[:16]

        parsed = self._extract_metadata(path)
        title = parsed["title"]
        artist = parsed["artist"]
        album = parsed["album"]
        accent = (artist[:1] or title[:1] or "M").upper()

        cover_available, cover_type, cover_mime, cover_path = self._resolve_track_cover(
            path, track_id, parsed["audio"], parsed["tags"], folder_cover_cache
        )
        lyrics_available, lyrics_type = self._detect_lyrics_flags(path, parsed["tags"])
        relative_path = _safe_relative(path, root)
        root_name = root.name.strip() or "音乐库"
        category = _derive_category(relative_path, root_name)
        root_key = str(root.resolve())
        root_label = str(root)

        return {
            "id": track_id,
            "title": title,
            "artist": artist,
            "album": album,
            "album_artist": parsed.get("album_artist", ""),
            "genre": parsed.get("genre", ""),
            "track_no": int(parsed.get("track_no", 0) or 0),
            "duration": int(parsed.get("duration", 0) or 0),
            "tag": ext.upper(),
            "accent": accent,
            "path": str(path),
            "size": int(stat.st_size),
            "mtime": int(stat.st_mtime),
            "year": parsed.get("year") or "",
            "relative_path": relative_path,
            "category": category,
            "root_name": root_name,
            "root_key": root_key,
            "root_label": root_label,
            "stream_url": f"/api/apple-audio/stream/{track_id}",
            "cover_available": bool(cover_available),
            "cover_type": cover_type,
            "cover_mime": cover_mime,
            "cover_path": cover_path,
            "cover_url": f"/api/apple-audio/cover/{track_id}",
            "lyrics_available": bool(lyrics_available),
            "lyrics_type": lyrics_type,
            "lyrics_url": f"/api/apple-audio/lyrics/{track_id}",
        }

    def _is_excluded_dir(self, candidate: Path, excludes):
        text = str(candidate).lower().replace("\\", "/")
        for rule in excludes:
            rule_text = str(rule).strip().lower().replace("\\", "/")
            if not rule_text:
                continue
            if text.endswith("/" + rule_text) or ("/" + rule_text + "/") in text:
                return True
        return False

    def _scan_root(self, root: Path, excludes, max_files, folder_cover_cache):
        tracks = []
        errors = []
        count = 0
        if not root.exists():
            return tracks, [f"root not found: {root}"], count
        if not root.is_dir():
            return tracks, [f"root is not directory: {root}"], count
        for dirpath, dirnames, filenames in os.walk(root):
            dir_path = Path(dirpath)
            dirnames[:] = [name for name in dirnames if not self._is_excluded_dir(dir_path / name, excludes)]
            for name in filenames:
                if count >= max_files:
                    errors.append(f"scan limit reached ({max_files})")
                    return tracks, errors, count
                path = dir_path / name
                if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                    continue
                try:
                    track = self._to_track(path, root, folder_cover_cache)
                    tracks.append(track)
                    count += 1
                except Exception as ex:
                    errors.append(f"{path}: {ex}")
        return tracks, errors, count

    def _normalize_cached_track(self, item):
        normalized = dict(item)
        track_id = str(normalized.get("id") or "").strip()
        normalized["id"] = track_id
        normalized["title"] = str(normalized.get("title") or "未命名曲目")
        normalized["artist"] = str(normalized.get("artist") or "Unknown Artist")
        normalized["album"] = str(normalized.get("album") or "Unknown Album")
        normalized["duration"] = int(normalized.get("duration", 0) or 0)
        normalized["tag"] = str(normalized.get("tag") or "")
        normalized["accent"] = str(normalized.get("accent") or "♪")
        normalized["cover_available"] = bool(normalized.get("cover_available", False))
        normalized["cover_type"] = str(normalized.get("cover_type") or "none")
        normalized["cover_mime"] = str(normalized.get("cover_mime") or "")
        normalized["cover_path"] = str(normalized.get("cover_path") or "")
        normalized["cover_url"] = str(normalized.get("cover_url") or f"/api/apple-audio/cover/{track_id}")
        normalized["lyrics_available"] = bool(normalized.get("lyrics_available", False))
        normalized["lyrics_type"] = str(normalized.get("lyrics_type") or "none")
        normalized["lyrics_url"] = str(normalized.get("lyrics_url") or f"/api/apple-audio/lyrics/{track_id}")
        normalized["album_artist"] = str(normalized.get("album_artist") or "")
        normalized["genre"] = str(normalized.get("genre") or "")
        normalized["track_no"] = int(normalized.get("track_no", 0) or 0)
        normalized["relative_path"] = str(normalized.get("relative_path") or "")
        normalized["root_name"] = str(normalized.get("root_name") or "")
        normalized["root_key"] = str(normalized.get("root_key") or "")
        normalized["root_label"] = str(normalized.get("root_label") or "")
        normalized["category"] = str(
            normalized.get("category")
            or _derive_category(normalized.get("relative_path", ""), normalized.get("root_name", ""))
        )
        return normalized

    def _load_library_cache(self):
        try:
            if not MUSIC_CACHE_FILE.exists():
                return
            payload = json.loads(MUSIC_CACHE_FILE.read_text(encoding="utf-8"))
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
                normalized = self._normalize_cached_track(item)
                parsed.append(normalized)
                by_id[track_id] = normalized
            with self.lock:
                self.library = parsed
                self.library_by_id = by_id
                self.state["last_scan_at"] = str(payload.get("last_scan_at") or "")
                self.state["scan_count"] = len(parsed)
        except Exception:
            return

    def _save_library_cache(self):
        payload = {
            "last_scan_at": self.state.get("last_scan_at", ""),
            "scan_count": len(self.library),
            "tracks": self.library,
        }
        MUSIC_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cleanup_stale_cover_cache(self, valid_track_ids):
        valid = {str(item) for item in valid_track_ids}
        try:
            for entry in COVER_CACHE_DIR.iterdir():
                if not entry.is_file():
                    continue
                if entry.stem not in valid:
                    try:
                        entry.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def _scrape_track_lyrics_payload(self, track):
        if not isinstance(track, dict):
            return
        track_id = str(track.get("id") or "").strip()
        if not track_id:
            return
        payload = self.get_track_lyrics(track_id)
        if not payload:
            return
        with self.lock:
            fresh = self.library_by_id.get(track_id)
            if fresh is not None:
                fresh["lyrics_available"] = bool(payload.get("lyrics_available"))
                fresh["lyrics_type"] = str(payload.get("lyrics_type") or "none")
                fresh["lyrics_url"] = f"/api/apple-audio/lyrics/{track_id}"

    def scan_library(self):
        cfg = self._config()
        roots = cfg.get("nas_music_roots", [])
        excludes = cfg.get("nas_music_exclude_dirs", [])
        max_files = 30000
        started = time.monotonic()
        folder_cover_cache = {}
        with self.lock:
            self.state["scan_running"] = True
            self.state["scan_stage"] = "scan"
            self.state["scan_processed"] = 0
            self.state["scan_total"] = 0
            self.state["scan_progress"] = 0
            self.state["scan_message"] = "Scanning files..."
            self.state["scan_errors"] = []
            self.state["updated_at"] = datetime.now().isoformat()

        all_tracks = []
        all_errors = []
        total_count = 0
        for raw_root in roots:
            root = Path(raw_root).expanduser()
            if not root.is_absolute():
                root = (Path.cwd() / root).resolve()
            tracks, errors, count = self._scan_root(
                root,
                excludes,
                max_files=max_files - total_count,
                folder_cover_cache=folder_cover_cache,
            )
            all_tracks.extend(tracks)
            all_errors.extend(errors)
            total_count += count
            if total_count >= max_files:
                break

        all_tracks.sort(
            key=lambda item: (
                str(item.get("artist") or "").lower(),
                str(item.get("album") or "").lower(),
                int(item.get("track_no", 0) or 0),
                str(item.get("title") or "").lower(),
            )
        )
        by_id = {item["id"]: item for item in all_tracks}
        scan_ms = int((time.monotonic() - started) * 1000)
        with self.lock:
            self.library = all_tracks
            self.library_by_id = by_id
            self.lyrics_cache = {k: v for k, v in self.lyrics_cache.items() if k in by_id}
            if self.state.get("current_track_id") and self.state["current_track_id"] not in by_id:
                self.state["current_track_id"] = ""
                self.state["is_playing"] = False
                self.state["elapsed_sec"] = 0
            self.state["queue_ids"] = [tid for tid in self.state.get("queue_ids", []) if tid in by_id]
            self.state["last_scan_at"] = datetime.now().isoformat()
            self.state["scan_count"] = len(all_tracks)
            self.state["scan_stage"] = "scrape"
            self.state["scan_processed"] = 0
            self.state["scan_total"] = len(all_tracks)
            self.state["scan_progress"] = 0
            self.state["scan_message"] = "Scraping cover and lyrics..."
            self.state["scan_errors"] = all_errors[:50]
            self.state["scan_ms"] = scan_ms
            self.state["last_action"] = "Library scanned"
            self.state["updated_at"] = datetime.now().isoformat()
            self._save_library_cache()
        # Full scraping: eagerly parse lyrics for every track during rescan.
        scrape_started = time.monotonic()
        scrape_errors = []
        total_tracks = len(all_tracks)
        for idx, item in enumerate(all_tracks, start=1):
            try:
                self._scrape_track_lyrics_payload(item)
            except Exception as ex:
                scrape_errors.append(str(ex))
                if len(scrape_errors) >= 20:
                    break
            if idx == total_tracks or idx % 20 == 0:
                progress = 100 if total_tracks <= 0 else int((idx / total_tracks) * 100)
                with self.lock:
                    self.state["scan_processed"] = idx
                    self.state["scan_total"] = total_tracks
                    self.state["scan_progress"] = max(0, min(progress, 100))
                    self.state["scan_message"] = f"Scraping metadata {idx}/{total_tracks}"
        scrape_ms = int((time.monotonic() - scrape_started) * 1000)
        with self.lock:
            self.state["scan_ms"] = int(self.state.get("scan_ms", 0) or 0) + scrape_ms
            if scrape_errors:
                self.state["scan_errors"] = (self.state.get("scan_errors") or []) + [
                    f"lyrics scrape: {msg}" for msg in scrape_errors
                ]
                self.state["scan_errors"] = self.state["scan_errors"][:50]
            self.state["scan_processed"] = total_tracks
            self.state["scan_total"] = total_tracks
            self.state["scan_progress"] = 100
            self.state["scan_stage"] = "done"
            self.state["scan_message"] = "Scan complete"
            self.state["scan_running"] = False
            self.state["last_action"] = "Library scanned + metadata scraped"
            self.state["updated_at"] = datetime.now().isoformat()
            self._save_library_cache()
        self._cleanup_stale_cover_cache(by_id.keys())
        return self.snapshot()

    def _find_track(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            return deepcopy(item) if item else None

    def get_track_path(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            if not item:
                return ""
            return str(item.get("path") or "")

    def get_track_cover(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            if not item:
                return "", ""
            cover_path = Path(str(item.get("cover_path") or ""))
            cover_mime = str(item.get("cover_mime") or "")
            cover_available = bool(item.get("cover_available"))
            audio_path = Path(str(item.get("path") or ""))
            item_id = str(item.get("id") or "")
        if cover_available and cover_path and cover_path.exists() and cover_path.is_file():
            return str(cover_path), cover_mime or _guess_mime(cover_path, fallback="image/jpeg")

        if not audio_path.exists() or not audio_path.is_file():
            return "", ""

        folder_cover_cache = {}
        audio, tags, _duration = _load_audio(audio_path)
        cover_available, cover_type, mime, new_cover_path = self._resolve_track_cover(
            audio_path, item_id, audio, tags, folder_cover_cache
        )
        with self.lock:
            fresh = self.library_by_id.get(item_id)
            if fresh is not None:
                fresh["cover_available"] = bool(cover_available)
                fresh["cover_type"] = cover_type
                fresh["cover_mime"] = mime
                fresh["cover_path"] = new_cover_path
                fresh["cover_url"] = f"/api/apple-audio/cover/{item_id}"
                self.state["updated_at"] = datetime.now().isoformat()
                self._save_library_cache()
        if cover_available and new_cover_path:
            candidate = Path(new_cover_path)
            if candidate.exists() and candidate.is_file():
                return str(candidate), mime or _guess_mime(candidate, fallback="image/jpeg")
        return "", ""

    def get_track_lyrics(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            if not item:
                return None
            item_copy = deepcopy(item)
            cache_item = self.lyrics_cache.get(item_copy["id"])
            if cache_item and int(cache_item.get("mtime", -1)) == int(item_copy.get("mtime", -2)):
                return deepcopy(cache_item.get("payload"))

        audio_path = Path(str(item_copy.get("path") or ""))
        if not audio_path.exists() or not audio_path.is_file():
            payload = _normalize_lyrics_payload(item_copy, lyrics_type="none", source="missing_file")
            with self.lock:
                self.lyrics_cache[item_copy["id"]] = {
                    "mtime": int(item_copy.get("mtime", 0) or 0),
                    "payload": payload,
                }
            return payload

        _audio, tags, _duration = _load_audio(audio_path)
        tag_payload = self._extract_lyrics_from_tags(tags)
        sidecar_payload = self._extract_lyrics_from_sidecar(audio_path)

        final_payload = None
        if sidecar_payload and sidecar_payload.get("lyrics_type") == "synced":
            final_payload = sidecar_payload
        elif tag_payload and tag_payload.get("lyrics_type") == "synced":
            final_payload = tag_payload
        elif tag_payload and tag_payload.get("lyrics_type") == "plain":
            final_payload = tag_payload
        elif sidecar_payload and sidecar_payload.get("lyrics_type") == "plain":
            final_payload = sidecar_payload
        else:
            final_payload = _normalize_lyrics_payload(item_copy, lyrics_type="none")

        normalized = _normalize_lyrics_payload(
            item_copy,
            lyrics_type=final_payload.get("lyrics_type", "none"),
            plain_text=final_payload.get("plain", ""),
            lines=final_payload.get("lines", []),
            source=final_payload.get("source", ""),
            lang=final_payload.get("lang", ""),
        )

        with self.lock:
            self.lyrics_cache[item_copy["id"]] = {
                "mtime": int(item_copy.get("mtime", 0) or 0),
                "payload": normalized,
            }
            fresh = self.library_by_id.get(item_copy["id"])
            if fresh is not None:
                fresh["lyrics_available"] = bool(normalized.get("lyrics_available"))
                fresh["lyrics_type"] = str(normalized.get("lyrics_type") or "none")
                fresh["lyrics_url"] = f"/api/apple-audio/lyrics/{item_copy['id']}"
                self.state["updated_at"] = datetime.now().isoformat()
        return deepcopy(normalized)

    def _tick_locked(self):
        now = time.monotonic()
        delta = max(0.0, now - self.last_tick)
        self.last_tick = now
        if not self.state.get("is_playing"):
            return
        current_id = str(self.state.get("current_track_id") or "").strip()
        if not current_id:
            self.state["is_playing"] = False
            return
        self.state["elapsed_sec"] = int(float(self.state.get("elapsed_sec", 0)) + delta)
        if self.state["elapsed_sec"] > 24 * 3600:
            self.state["elapsed_sec"] = 0

    def snapshot(self):
        with self.lock:
            self._tick_locked()
            current = self.library_by_id.get(str(self.state.get("current_track_id") or "").strip())
            queue = []
            for track_id in self.state.get("queue_ids", []):
                item = self.library_by_id.get(str(track_id or "").strip())
                if item:
                    queue.append(deepcopy(item))
            scan_errors = list(self.state.get("scan_errors", []))
            return {
                "connected": bool(self.state.get("connected")),
                "provider": self.state.get("provider", "nas_music_tag"),
                "player_mode": self.state.get("player_mode", "nas_http"),
                "player_host": self.state.get("player_host", ""),
                "output_mode": self.state.get("output_mode", "system_default"),
                "auth_state": self.state.get("auth_state", "NAS music tag ready"),
                "is_playing": bool(self.state.get("is_playing")),
                "elapsed_sec": int(self.state.get("elapsed_sec", 0) or 0),
                "current_track": deepcopy(current) if current else None,
                "queue": queue,
                "library": deepcopy(self.library),
                "outputs": deepcopy(self.state.get("outputs", [])),
                "library_size": len(self.library),
                "last_action": self.state.get("last_action", ""),
                "updated_at": self.state.get("updated_at", ""),
                "scan": {
                    "running": bool(self.state.get("scan_running")),
                    "count": int(self.state.get("scan_count", 0) or 0),
                    "stage": str(self.state.get("scan_stage") or "idle"),
                    "processed": int(self.state.get("scan_processed", 0) or 0),
                    "total": int(self.state.get("scan_total", 0) or 0),
                    "progress": int(self.state.get("scan_progress", 0) or 0),
                    "message": str(self.state.get("scan_message") or ""),
                    "last_scan_at": self.state.get("last_scan_at", ""),
                    "scan_ms": int(self.state.get("scan_ms", 0) or 0),
                    "errors": scan_errors,
                },
                "capabilities": {
                    "control_only": False,
                    "requires_audio_route": False,
                    "cover_endpoint": "/api/apple-audio/cover/<track_id>",
                    "lyrics_endpoint": "/api/apple-audio/lyrics/<track_id>",
                    "category_field": "category",
                    "notes": [
                        "Music source is provided by NAS local library.",
                        "Track stream URL is exposed under /api/apple-audio/stream/<track_id>.",
                        "Cover art and lyrics scraping is enabled for local files.",
                        "Full-library lyrics scraping runs during rescan.",
                    ],
                },
            }

    def search(self, query):
        text = str(query or "").strip().lower()
        with self.lock:
            source = list(self.library)
        if not text:
            return source[:200]
        results = []
        for item in source:
            haystack = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("artist") or ""),
                    str(item.get("album") or ""),
                    str(item.get("album_artist") or ""),
                    str(item.get("genre") or ""),
                    str(item.get("tag") or ""),
                    str(item.get("relative_path") or ""),
                ]
            ).lower()
            if text in haystack:
                results.append(item)
                if len(results) >= 300:
                    break
        return results

    def queue_track(self, track_id, play_now=False):
        track_id = str(track_id or "").strip()
        if not track_id:
            raise ValueError("track id required")
        with self.lock:
            if track_id not in self.library_by_id:
                raise ValueError("track not found")
            self._tick_locked()
            if play_now:
                current_id = str(self.state.get("current_track_id") or "").strip()
                if current_id:
                    self.state["queue_ids"].insert(0, current_id)
                self.state["current_track_id"] = track_id
                self.state["elapsed_sec"] = 0
                self.state["is_playing"] = True
                self.state["last_action"] = f"Play now: {self.library_by_id[track_id].get('title')}"
            else:
                self.state["queue_ids"].append(track_id)
                self.state["last_action"] = f"Queued: {self.library_by_id[track_id].get('title')}"
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def promote_queue(self, index):
        with self.lock:
            self._tick_locked()
            queue = self.state.get("queue_ids", [])
            idx = int(index)
            if idx < 0 or idx >= len(queue):
                raise ValueError("queue index out of range")
            track_id = queue.pop(idx)
            queue.insert(0, track_id)
            name = self.library_by_id.get(track_id, {}).get("title") or track_id
            self.state["last_action"] = f"Promoted: {name}"
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def clear_queue(self):
        with self.lock:
            self.state["queue_ids"] = []
            self.state["last_action"] = "Queue cleared"
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()

    def transport(self, action):
        action = str(action or "").strip().lower()
        with self.lock:
            self._tick_locked()
            queue = self.state.get("queue_ids", [])
            current_id = str(self.state.get("current_track_id") or "").strip()
            if action == "toggle":
                if not current_id and queue:
                    self.state["current_track_id"] = queue.pop(0)
                    self.state["elapsed_sec"] = 0
                    self.state["is_playing"] = True
                    self.state["last_action"] = "Start playback"
                elif not current_id:
                    raise ValueError("no track selected")
                else:
                    self.state["is_playing"] = not bool(self.state.get("is_playing"))
                    self.state["last_action"] = "Play" if self.state["is_playing"] else "Pause"
            elif action == "next":
                if not queue:
                    raise ValueError("queue is empty")
                self.state["current_track_id"] = queue.pop(0)
                self.state["elapsed_sec"] = 0
                self.state["is_playing"] = True
                self.state["last_action"] = "Next track"
            elif action == "prev":
                if not current_id:
                    raise ValueError("no track selected")
                self.state["elapsed_sec"] = 0
                self.state["last_action"] = "Restart track"
            elif action == "favorite":
                if not current_id:
                    raise ValueError("no track selected")
                name = self.library_by_id.get(current_id, {}).get("title") or current_id
                self.state["last_action"] = f"Favorite: {name}"
            else:
                raise ValueError("unsupported transport action")
            self.state["updated_at"] = datetime.now().isoformat()
        return self.snapshot()


class LazyAppleAudioService:
    # Importing the API should never scan NAS folders. The real service is built
    # only when an Apple Audio endpoint is used.
    def __init__(self):
        self._lock = threading.Lock()
        self._service = None

    def _get_service(self):
        if self._service is None:
            with self._lock:
                if self._service is None:
                    self._service = AppleAudioService()
        return self._service

    def __getattr__(self, name):
        return getattr(self._get_service(), name)


apple_audio_service = LazyAppleAudioService()
