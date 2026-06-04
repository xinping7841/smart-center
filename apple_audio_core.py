# AI_MODULE: apple_audio_core
# AI_PURPOSE: Scan local music files, maintain queue/transport metadata, lyrics, covers, and playback state helpers.
# AI_BOUNDARY: Flask routes live in api/apple_audio.py and frontend rendering lives in static/js/views/apple-audio.js.
# AI_DATA_FLOW: CONFIG/apple audio library files -> DATA_DIR runtime caches -> API payloads for music cards and transport.
# AI_RUNTIME: Imported by api/apple_audio.py during page/API requests and background-style scan operations.
# AI_RISK: Medium. Heavy scans or bad metadata parsing can slow the dashboard and disrupt live playback; startup scans must not block Flask binding.
# AI_COMPAT: Preserve queue, transport, lyrics, cover, and library payload shapes used by existing frontend.
# AI_SEARCH_KEYWORDS: apple audio, music library, queue, lyrics, cover, transport.
import base64
import hashlib
import json
import math
import mimetypes
import os
import pwd
import random
import re
import shutil
import signal
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
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
PLAYLISTS_FILE = ensure_parent_dir(DATA_DIR / "music_playlists.json")
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
    "playback_mode": "normal",
    "volume_percent": 70,
    "auth_state": "NAS music tag ready",
    "outputs": DEFAULT_OUTPUTS,
    "nas_music_roots": [],
    "nas_music_exclude_dirs": [],
    "nas_auto_scan_on_start": True,
    "local_player_enabled": False,
    "local_player_command": "ffplay",
    "local_player_audio_user": "",
    "local_player_sink": "",
    "local_player_alsa_device": "",
    "jamendo_enabled": False,
    "jamendo_client_id": "",
    "jamendo_limit": 20,
    "jamendo_api_base": "https://api.jamendo.com/v3.0",
}

JAMENDO_TRACKS_ENDPOINT = "https://api.jamendo.com/v3.0/tracks/"
LOCAL_PLAYER_MODES = {"local_process", "node120_bluetooth", "bluetooth_local", "node120_analog"}
LOCAL_PLAYER_COMMANDS = {"ffplay", "ffmpeg_aplay"}
LOCAL_PLAYER_STATUS_TIMEOUT = 2.5
PLAYBACK_MODES = {"normal", "shuffle", "repeat_all", "repeat_one"}
PLAYBACK_MODE_ALIASES = {
    "random": "shuffle",
    "loop": "repeat_all",
    "loop_all": "repeat_all",
    "repeat": "repeat_all",
    "single": "repeat_one",
    "single_loop": "repeat_one",
}


def _normalize_playback_mode(value):
    mode = str(value or "").strip().lower()
    mode = PLAYBACK_MODE_ALIASES.get(mode, mode)
    return mode if mode in PLAYBACK_MODES else "normal"


def _coerce_volume_percent(value):
    try:
        return max(0, min(int(round(float(value))), 100))
    except Exception:
        return 70


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


def _find_named_cover(audio_path: Path):
    base = audio_path.with_suffix("")
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        for candidate in (base.with_suffix(ext), base.with_suffix(ext.upper())):
            if candidate.exists() and candidate.is_file():
                return str(candidate.resolve()), _guess_mime(candidate, fallback="image/jpeg")
    return None


def _pick_filename_metadata(path: Path):
    name = path.stem.strip()
    if not name:
        return "", ""
    normalized = re.sub(r"\s+", " ", name)
    normalized = re.sub(r"^\s*\d{1,3}\s*[-_. ]+\s*", "", normalized).strip()
    patterns = [
        r"^(?P<artist>.+?)\s+-\s+(?P<title>.+)$",
        r"^(?P<artist>.+?)\s+--\s+(?P<title>.+)$",
        r"^(?P<title>.+?)\s+-\s+(?P<artist>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if not match:
            continue
        artist = _try_decode_text(match.groupdict().get("artist", ""))
        title = _try_decode_text(match.groupdict().get("title", ""))
        if title and artist:
            return title, artist
    return normalized, ""


def _guess_album_from_path(path: Path, root: Path):
    try:
        rel_parent = path.parent.relative_to(root)
        parts = [part for part in rel_parent.parts if part]
    except Exception:
        parts = [path.parent.name]
    if parts:
        return str(parts[-1] or "").strip()
    return str(root.name or "").strip()


def _jamendo_client_id(cfg):
    raw = str(cfg.get("jamendo_client_id") or "").strip()
    env = str(os.environ.get("JAMENDO_CLIENT_ID") or "").strip()
    return raw or env


def _is_remote_track(item):
    source = str((item or {}).get("source") or "").strip().lower()
    return source in {"jamendo", "remote"}


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


def _safe_playlist_id(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64] or hashlib.sha1(str(value or "").encode("utf-8", errors="ignore")).hexdigest()[:12]


class AppleAudioService:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_tick = time.monotonic()
        self.library = []
        self.library_by_id = {}
        self.lyrics_cache = {}
        self.custom_playlists = []
        self.local_player_proc = None
        self.state = {
            "connected": True,
            "provider": "nas_music_tag",
            "player_mode": "nas_http",
            "player_host": "",
            "output_mode": "system_default",
            "playback_mode": "normal",
            "volume_percent": 70,
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
            "local_player": {
                "enabled": False,
                "mode": "nas_http",
                "state": "idle",
                "pid": 0,
                "message": "",
                "updated_at": "",
            },
        }
        self.configure()
        self._load_library_cache()
        self._load_custom_playlists()
        if self._config().get("nas_auto_scan_on_start", True):
            self.start_background_scan("startup")

    def start_background_scan(self, reason="manual"):
        with self.lock:
            if self.state.get("scan_running"):
                return self.snapshot()
            self.state["scan_running"] = True
            self.state["scan_stage"] = "queued"
            self.state["scan_message"] = f"Scan queued: {reason}"
            self.state["updated_at"] = datetime.now().isoformat()

        def run():
            try:
                self.scan_library()
            except Exception as exc:
                with self.lock:
                    self.state["scan_running"] = False
                    self.state["scan_stage"] = "error"
                    self.state["scan_message"] = f"Scan failed: {exc}"
                    self.state["scan_errors"] = [str(exc)]
                    self.state["updated_at"] = datetime.now().isoformat()

        thread = threading.Thread(target=run, name=f"apple-audio-scan-{reason}", daemon=True)
        thread.start()
        return self.snapshot()

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
        merged["jamendo_enabled"] = bool(merged.get("jamendo_enabled", False))
        merged["jamendo_client_id"] = str(merged.get("jamendo_client_id") or "").strip()
        merged["jamendo_api_base"] = str(merged.get("jamendo_api_base") or JAMENDO_TRACKS_ENDPOINT.rsplit("/", 2)[0]).strip()
        merged["playback_mode"] = _normalize_playback_mode(merged.get("playback_mode"))
        merged["volume_percent"] = _coerce_volume_percent(merged.get("volume_percent", 70))
        try:
            merged["jamendo_limit"] = max(1, min(int(merged.get("jamendo_limit", 20) or 20), 50))
        except Exception:
            merged["jamendo_limit"] = 20
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
            self.state["playback_mode"] = _normalize_playback_mode(cfg.get("playback_mode", self.state.get("playback_mode")))
            self.state["volume_percent"] = _coerce_volume_percent(cfg.get("volume_percent", self.state.get("volume_percent", 70)))
            self.state["auth_state"] = str(cfg.get("auth_state", "NAS music tag ready") or "NAS music tag ready")
            self.state["connected"] = bool(cfg.get("enabled", True))
            self.state["outputs"] = deepcopy(cfg.get("outputs", DEFAULT_OUTPUTS))
            local_enabled = self._local_player_enabled(cfg)
            self.state["local_player"] = {
                **(self.state.get("local_player") or {}),
                "enabled": local_enabled,
                "mode": self.state["player_mode"],
                "command": self._local_player_command(cfg),
                "audio_user": str(cfg.get("local_player_audio_user", "") or "").strip(),
                "sink": str(cfg.get("local_player_sink", "") or "").strip(),
                "alsa_device": str(cfg.get("local_player_alsa_device", "") or "").strip(),
            }
            self.state["updated_at"] = datetime.now().isoformat()

    def _local_player_enabled(self, cfg=None):
        cfg = cfg or self._config()
        mode = str(cfg.get("player_mode", "") or "").strip().lower()
        return bool(cfg.get("local_player_enabled", False)) or mode in LOCAL_PLAYER_MODES

    def _local_player_command(self, cfg=None):
        cfg = cfg or self._config()
        command = str(cfg.get("local_player_command", "ffplay") or "ffplay").strip().lower()
        return command if command in LOCAL_PLAYER_COMMANDS else "ffplay"

    def _mark_local_player_locked(self, state, message="", pid=0):
        self.state["local_player"] = {
            **(self.state.get("local_player") or {}),
            "enabled": self._local_player_enabled(),
            "mode": self.state.get("player_mode", "nas_http"),
            "state": state,
            "pid": int(pid or 0),
            "message": str(message or ""),
            "updated_at": datetime.now().isoformat(),
        }

    def _stop_local_player(self, message="Stopped"):
        proc = self.local_player_proc
        self.local_player_proc = None
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        with self.lock:
            self._mark_local_player_locked("idle", message)

    def _build_local_player_command(self, track):
        cfg = self._config()
        command = self._local_player_command(cfg)
        volume = max(0.0, min(_coerce_volume_percent(cfg.get("volume_percent", self.state.get("volume_percent", 70))) / 100.0, 1.0))
        path = str(track.get("path") or "").strip()
        if not path:
            raise RuntimeError("track has no local path")
        if _is_remote_track(track):
            source = str(track.get("stream_url") or "").strip()
        else:
            source = path
            if not Path(source).exists():
                raise RuntimeError(f"audio file missing on node-120: {source}")
        if command == "ffplay":
            binary = shutil.which("ffplay")
            if not binary:
                raise RuntimeError("ffplay is not installed on node-120")
            return [binary, "-nodisp", "-autoexit", "-loglevel", "warning", "-volume", str(int(round(volume * 100))), source]
        if command == "ffmpeg_aplay":
            ffmpeg = shutil.which("ffmpeg")
            aplay = shutil.which("aplay")
            if not ffmpeg:
                raise RuntimeError("ffmpeg is not installed on node-120")
            if not aplay:
                raise RuntimeError("aplay is not installed on node-120")
            device = str(cfg.get("local_player_alsa_device", "") or "").strip() or "plughw:CARD=PCH,DEV=0"
            return [
                "/bin/bash",
                "-c",
                (
                    "set -o pipefail; "
                    '"$1" -hide_banner -loglevel warning -nostdin -i "$2" '
                    '-vn -af "volume=$5" -ar 48000 -ac 2 -f wav - | '
                    '"$3" -D "$4"'
                ),
                "smart-center-ffmpeg-aplay",
                ffmpeg,
                source,
                aplay,
                device,
                f"{volume:.3f}",
            ]
        raise RuntimeError("unsupported local player command")

    def _local_player_env(self):
        cfg = self._config()
        env = os.environ.copy()
        sink = str(cfg.get("local_player_sink", "") or "").strip()
        if sink:
            env["PULSE_SINK"] = sink
        return env

    def _audio_user_command(self, base_cmd):
        cfg = self._config()
        user = str(cfg.get("local_player_audio_user", "") or "").strip()
        if not user:
            return list(base_cmd), self._local_player_env()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user):
            raise RuntimeError("invalid local_player_audio_user")
        try:
            info = pwd.getpwnam(user)
        except KeyError as exc:
            raise RuntimeError(f"audio user not found: {user}") from exc
        env = self._local_player_env()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{info.pw_uid}"
        prefix = ["sudo", "-n", "-u", user, "env", f"XDG_RUNTIME_DIR={env['XDG_RUNTIME_DIR']}"]
        if env.get("PULSE_SINK"):
            prefix.append(f"PULSE_SINK={env['PULSE_SINK']}")
        return prefix + list(base_cmd), env

    def _start_local_player_for_track(self, track_id):
        track = self._find_track(track_id)
        if not track:
            raise RuntimeError("track not found")
        self._stop_local_player("Switching track")
        cmd = self._build_local_player_command(track)
        cmd, env = self._audio_user_command(cmd)
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except Exception as exc:
            with self.lock:
                self.state["is_playing"] = False
                self._mark_local_player_locked("error", str(exc))
            raise
        self.local_player_proc = proc
        with self.lock:
            self._mark_local_player_locked("playing", f"Playing with {self._local_player_command()}: {track.get('title')}", pid=proc.pid)

    def _next_library_track_id_locked(self, current_id):
        ids = [str(item.get("id") or "").strip() for item in self.library if str(item.get("id") or "").strip()]
        ids = [track_id for track_id in ids if track_id in self.library_by_id]
        if not ids:
            return ""
        current_id = str(current_id or "").strip()
        if current_id in ids and len(ids) > 1:
            return ids[(ids.index(current_id) + 1) % len(ids)]
        if current_id in ids:
            return current_id
        return ids[0]

    def _shuffle_track_id_locked(self, current_id):
        ids = [str(item.get("id") or "").strip() for item in self.library if str(item.get("id") or "").strip()]
        ids = [track_id for track_id in ids if track_id in self.library_by_id]
        if not ids:
            return ""
        current_id = str(current_id or "").strip()
        choices = [track_id for track_id in ids if track_id != current_id]
        return random.choice(choices or ids)

    def _select_next_track_locked(self, *, manual=False):
        mode = _normalize_playback_mode(self.state.get("playback_mode"))
        queue = self.state.get("queue_ids", [])
        current_id = str(self.state.get("current_track_id") or "").strip()
        if mode == "repeat_one" and current_id:
            return current_id
        if mode == "shuffle":
            return self._shuffle_track_id_locked(current_id)
        if queue:
            return str(queue.pop(0) or "").strip()
        if mode == "repeat_all":
            return self._next_library_track_id_locked(current_id)
        if manual:
            raise ValueError("queue is empty")
        return ""

    def _apply_selected_track_locked(self, track_id, action_text, *, playing=True):
        track_id = str(track_id or "").strip()
        if not track_id or track_id not in self.library_by_id:
            return ""
        self.state["current_track_id"] = track_id
        self.state["elapsed_sec"] = 0
        self.state["is_playing"] = bool(playing)
        self.state["last_action"] = action_text
        return track_id

    def _refresh_local_player_locked(self, *, auto_advance=False):
        proc = self.local_player_proc
        if not proc:
            return ""
        code = proc.poll()
        if code is None:
            self._mark_local_player_locked("playing", self.state.get("local_player", {}).get("message", ""), pid=proc.pid)
            return ""
        self.local_player_proc = None
        was_playing = bool(self.state.get("is_playing"))
        next_track_id = ""
        if auto_advance and was_playing and code == 0:
            next_track_id = self._select_next_track_locked(manual=False)
        if next_track_id:
            title = self.library_by_id.get(next_track_id, {}).get("title") or next_track_id
            self._apply_selected_track_locked(next_track_id, f"Auto next: {title}", playing=True)
            self.state["updated_at"] = datetime.now().isoformat()
            return next_track_id
        self.state["is_playing"] = False
        self.state["updated_at"] = datetime.now().isoformat()
        self._mark_local_player_locked("idle", f"Local player exited: {code}")
        return ""

    def local_output_status(self):
        cfg = self._config()

        def run(cmd, audio_user=False):
            try:
                env = None
                if audio_user:
                    cmd, env = self._audio_user_command(cmd)
                result = subprocess.run(cmd, text=True, capture_output=True, timeout=LOCAL_PLAYER_STATUS_TIMEOUT, env=env)
                return {
                    "ok": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": (result.stdout or "").strip()[-4000:],
                    "stderr": (result.stderr or "").strip()[-1200:],
                }
            except Exception as exc:
                return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}

        roots = []
        for raw in cfg.get("nas_music_roots", []) or []:
            path = Path(str(raw or "")).expanduser()
            roots.append({
                "path": str(path),
                "exists": path.exists(),
                "is_dir": path.is_dir(),
            })
        bluetooth = {}
        if shutil.which("bluetoothctl"):
            bluetooth = {
                "controllers": run(["bluetoothctl", "list"]),
                "devices": run(["bluetoothctl", "devices"]),
                "connected": run(["bluetoothctl", "devices", "Connected"]),
            }
        audio = {
            "ffplay": shutil.which("ffplay") or "",
            "ffmpeg": shutil.which("ffmpeg") or "",
            "aplay": shutil.which("aplay") or "",
            "pactl": run(["pactl", "list", "short", "sinks"], audio_user=True) if shutil.which("pactl") else {"ok": False, "stderr": "pactl missing"},
            "wpctl": run(["wpctl", "status"], audio_user=True) if shutil.which("wpctl") else {"ok": False, "stderr": "wpctl missing"},
        }
        with self.lock:
            self._refresh_local_player_locked()
            local_player = deepcopy(self.state.get("local_player") or {})
        return {
            "player_mode": str(cfg.get("player_mode", "nas_http") or "nas_http"),
            "local_player_enabled": self._local_player_enabled(cfg),
            "local_player": local_player,
            "roots": roots,
            "bluetooth": bluetooth,
            "audio": audio,
        }

    def bluetooth_connect(self, mac, trust=True):
        target = str(mac or "").strip().upper().replace("-", ":")
        if not re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", target):
            raise ValueError("valid bluetooth mac required")
        if not shutil.which("bluetoothctl"):
            raise RuntimeError("bluetoothctl is not installed")
        commands = [["bluetoothctl", "power", "on"]]
        if trust:
            commands.append(["bluetoothctl", "trust", target])
        commands.append(["bluetoothctl", "connect", target])
        results = []
        for cmd in commands:
            try:
                result = subprocess.run(cmd, text=True, capture_output=True, timeout=12.0)
                results.append({
                    "cmd": cmd[1],
                    "ok": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": (result.stdout or "").strip()[-1600:],
                    "stderr": (result.stderr or "").strip()[-1200:],
                })
            except Exception as exc:
                results.append({"cmd": cmd[1], "ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)})
                break
        return {
            "target": target,
            "ok": bool(results and results[-1].get("ok")),
            "results": results,
            "status": self.local_output_status(),
        }

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

    def _extract_metadata(self, path: Path, root: Path):
        tag_fallback = _read_id3v1_tag(path)
        audio, tags, duration = _load_audio(path)
        filename_title, filename_artist = _pick_filename_metadata(path)

        title = _pick_tag_text(tags, ["title", "TIT2", "\xa9nam"]) or tag_fallback.get("title") or filename_title or path.stem
        artist = _pick_tag_join(tags, ["artist", "TPE1", "\xa9ART"], sep=" / ") or tag_fallback.get("artist") or filename_artist or "Unknown Artist"
        album = _pick_tag_text(tags, ["album", "TALB", "\xa9alb"]) or tag_fallback.get("album") or _guess_album_from_path(path, root) or "Unknown Album"
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
        named_cover = _find_named_cover(path)
        if named_cover:
            cover_path, cover_mime = named_cover
            return True, "sidecar", cover_mime, cover_path
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

        parsed = self._extract_metadata(path, root)
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
            "source": "nas",
            "source_label": "NAS",
            "playable": True,
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
        normalized["source"] = str(normalized.get("source") or "nas")
        normalized["source_label"] = str(normalized.get("source_label") or "NAS")
        normalized["playable"] = bool(normalized.get("playable", True))
        normalized["stream_url"] = str(normalized.get("stream_url") or f"/api/apple-audio/stream/{track_id}")
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

    def _normalize_custom_playlist(self, item):
        if not isinstance(item, dict):
            return None
        name = str(item.get("name") or "").strip()
        raw_id = str(item.get("id") or name or "").strip()
        playlist_id = _safe_playlist_id(raw_id or name)
        if not name:
            name = playlist_id or "未命名歌单"
        seen = set()
        track_ids = []
        for raw in item.get("track_ids", []) or []:
            track_id = str(raw or "").strip()
            if not track_id or track_id in seen:
                continue
            seen.add(track_id)
            track_ids.append(track_id)
        return {
            "id": playlist_id,
            "name": name[:80],
            "track_ids": track_ids,
            "created_at": str(item.get("created_at") or datetime.now().isoformat()),
            "updated_at": str(item.get("updated_at") or datetime.now().isoformat()),
        }

    def _load_custom_playlists(self):
        try:
            if not PLAYLISTS_FILE.exists():
                return
            payload = json.loads(PLAYLISTS_FILE.read_text(encoding="utf-8"))
            rows = payload.get("playlists", []) if isinstance(payload, dict) else []
            playlists = []
            seen = set()
            for item in rows:
                normalized = self._normalize_custom_playlist(item)
                if not normalized or normalized["id"] in seen:
                    continue
                seen.add(normalized["id"])
                playlists.append(normalized)
            with self.lock:
                self.custom_playlists = playlists
        except Exception:
            return

    def _save_custom_playlists_locked(self):
        payload = {
            "schema": "smart_center.apple_audio_playlists.v1",
            "updated_at": datetime.now().isoformat(),
            "playlists": self.custom_playlists,
        }
        PLAYLISTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _folder_playlist_rows_locked(self):
        groups = {}
        for item in self.library:
            label = str(item.get("category") or "").strip() or _derive_category(item.get("relative_path", ""), item.get("root_name", ""))
            playlist_id = f"folder:{_safe_playlist_id(label)}"
            row = groups.setdefault(playlist_id, {
                "id": playlist_id,
                "kind": "folder",
                "name": label or "未分类",
                "track_ids": [],
                "count": 0,
                "duration": 0,
            })
            row["track_ids"].append(item.get("id"))
            row["count"] += 1
            row["duration"] += int(item.get("duration", 0) or 0)
        return sorted(groups.values(), key=lambda row: (-int(row.get("count", 0) or 0), str(row.get("name") or "")))

    def _custom_playlist_rows_locked(self):
        rows = []
        for item in self.custom_playlists:
            track_ids = [tid for tid in item.get("track_ids", []) if tid in self.library_by_id]
            duration = sum(int(self.library_by_id.get(tid, {}).get("duration", 0) or 0) for tid in track_ids)
            rows.append({
                "id": f"custom:{item['id']}",
                "kind": "custom",
                "custom_id": item["id"],
                "name": item["name"],
                "track_ids": track_ids,
                "count": len(track_ids),
                "duration": duration,
                "updated_at": item.get("updated_at", ""),
            })
        return rows

    def _playlist_rows_locked(self):
        return self._folder_playlist_rows_locked() + self._custom_playlist_rows_locked()

    def _resolve_playlist_track_ids_locked(self, playlist_id):
        safe_id = str(playlist_id or "").strip()
        for row in self._playlist_rows_locked():
            if row.get("id") == safe_id:
                return [tid for tid in row.get("track_ids", []) if tid in self.library_by_id]
        return []

    def playlists_snapshot(self):
        with self.lock:
            return {
                "playlists": deepcopy(self._playlist_rows_locked()),
                "updated_at": datetime.now().isoformat(),
            }

    def _playlists_snapshot_payload_locked(self):
        return {
            "playlists": deepcopy(self._playlist_rows_locked()),
            "updated_at": datetime.now().isoformat(),
        }

    def create_custom_playlist(self, name):
        name = str(name or "").strip()
        if not name:
            raise ValueError("playlist name required")
        with self.lock:
            base_id = _safe_playlist_id(name)
            playlist_id = base_id
            suffix = 2
            existing = {item["id"] for item in self.custom_playlists}
            while playlist_id in existing:
                playlist_id = f"{base_id}_{suffix}"
                suffix += 1
            now = datetime.now().isoformat()
            self.custom_playlists.append({
                "id": playlist_id,
                "name": name[:80],
                "track_ids": [],
                "created_at": now,
                "updated_at": now,
            })
            self._save_custom_playlists_locked()
            return self._playlists_snapshot_payload_locked()

    def add_track_to_custom_playlist(self, playlist_id, track_id):
        custom_id = str(playlist_id or "").strip()
        if custom_id.startswith("custom:"):
            custom_id = custom_id.split(":", 1)[1]
        track_id = str(track_id or "").strip()
        if not track_id:
            raise ValueError("track id required")
        with self.lock:
            if track_id not in self.library_by_id:
                raise ValueError("track not found")
            for item in self.custom_playlists:
                if item.get("id") != custom_id:
                    continue
                if track_id not in item["track_ids"]:
                    item["track_ids"].append(track_id)
                    item["updated_at"] = datetime.now().isoformat()
                    self._save_custom_playlists_locked()
                return self._playlists_snapshot_payload_locked()
        raise ValueError("playlist not found")

    def queue_playlist(self, playlist_id, play_now=False):
        with self.lock:
            self._tick_locked()
            track_ids = self._resolve_playlist_track_ids_locked(playlist_id)
            if not track_ids:
                raise ValueError("playlist is empty")
            if play_now:
                current_id = str(self.state.get("current_track_id") or "").strip()
                next_queue = list(track_ids[1:])
                if current_id:
                    next_queue.append(current_id)
                self.state["current_track_id"] = track_ids[0]
                self.state["queue_ids"] = next_queue
                self.state["elapsed_sec"] = 0
                self.state["is_playing"] = True
                self.state["last_action"] = "Play playlist"
                target_track_id = track_ids[0]
            else:
                self.state["queue_ids"].extend(track_ids)
                self.state["last_action"] = "Queued playlist"
                target_track_id = ""
            self.state["updated_at"] = datetime.now().isoformat()
        if play_now and self._local_player_enabled():
            self._start_local_player_for_track(target_track_id)
        return self.snapshot()

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

    def _remember_remote_track(self, track):
        if not isinstance(track, dict):
            return
        track_id = str(track.get("id") or "").strip()
        if not track_id or not _is_remote_track(track):
            return
        normalized = self._normalize_cached_track(track)
        normalized["path"] = ""
        normalized["source"] = str(track.get("source") or "remote")
        normalized["source_label"] = str(track.get("source_label") or normalized["source"]).upper()
        normalized["playable"] = bool(track.get("playable", True))
        with self.lock:
            self.library_by_id[track_id] = normalized
            self.state["updated_at"] = datetime.now().isoformat()

    def get_track_path(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            if not item:
                return ""
            if _is_remote_track(item):
                return str(item.get("stream_url") or "")
            return str(item.get("path") or "")

    def get_track_cover(self, track_id):
        with self.lock:
            item = self.library_by_id.get(str(track_id or "").strip())
            if not item:
                return "", ""
            if _is_remote_track(item):
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
            if _is_remote_track(item_copy):
                return _normalize_lyrics_payload(item_copy, lyrics_type="none", source="remote")
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

    def _snapshot_payload_locked(self):
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
            "playback_mode": _normalize_playback_mode(self.state.get("playback_mode")),
            "volume_percent": _coerce_volume_percent(self.state.get("volume_percent", 70)),
            "auth_state": self.state.get("auth_state", "NAS music tag ready"),
            "is_playing": bool(self.state.get("is_playing")),
            "elapsed_sec": int(self.state.get("elapsed_sec", 0) or 0),
            "current_track": deepcopy(current) if current else None,
            "queue": queue,
            "library": deepcopy(self.library),
            "playlists": deepcopy(self._playlist_rows_locked()),
            "outputs": deepcopy(self.state.get("outputs", [])),
            "local_player": deepcopy(self.state.get("local_player", {})),
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
                "requires_audio_route": self._local_player_enabled(),
                "cover_endpoint": "/api/apple-audio/cover/<track_id>",
                "lyrics_endpoint": "/api/apple-audio/lyrics/<track_id>",
                "category_field": "category",
                "playback_modes": sorted(PLAYBACK_MODES),
                "notes": [
                    "Music source is provided by NAS local library.",
                    "Track stream URL is exposed under /api/apple-audio/stream/<track_id>.",
                    "Local node playback is available when player_mode is node120_bluetooth/node120_analog/local_process.",
                    "Playback mode supports normal, shuffle, repeat_all, and repeat_one.",
                    "Cover art and lyrics scraping is enabled for local files.",
                    "Full-library lyrics scraping runs during rescan.",
                ],
            },
        }

    def snapshot(self):
        auto_start_track_id = ""
        with self.lock:
            self._tick_locked()
            auto_start_track_id = self._refresh_local_player_locked(auto_advance=True)
            if not auto_start_track_id:
                return self._snapshot_payload_locked()
        if self._local_player_enabled():
            try:
                self._start_local_player_for_track(auto_start_track_id)
            except Exception:
                pass
        with self.lock:
            self._tick_locked()
            self._refresh_local_player_locked(auto_advance=False)
            return self._snapshot_payload_locked()

    def search(self, query):
        text = str(query or "").strip().lower()
        with self.lock:
            source = [deepcopy(item) for item in self.library]
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

    def _jamendo_enabled(self, cfg=None):
        cfg = cfg or self._config()
        return bool(cfg.get("jamendo_enabled")) and bool(_jamendo_client_id(cfg))

    def _jamendo_track_to_item(self, raw):
        track_id = str(raw.get("id") or "").strip()
        if not track_id:
            return None
        title = str(raw.get("name") or "Untitled").strip() or "Untitled"
        artist = str(raw.get("artist_name") or "Jamendo Artist").strip() or "Jamendo Artist"
        album = str(raw.get("album_name") or "Jamendo").strip() or "Jamendo"
        duration = 0
        try:
            duration = int(float(raw.get("duration") or 0))
        except Exception:
            duration = 0
        audio_url = str(raw.get("audio") or raw.get("audiodownload") or "").strip()
        cover_url = str(
            raw.get("album_image")
            or raw.get("image")
            or raw.get("artist_image")
            or ""
        ).strip()
        return {
            "id": f"jamendo:{track_id}",
            "remote_id": track_id,
            "title": title,
            "artist": artist,
            "album": album,
            "album_artist": artist,
            "genre": str(raw.get("musicinfo", {}).get("tags", {}).get("genres", [""])[0] if isinstance(raw.get("musicinfo"), dict) and raw.get("musicinfo", {}).get("tags", {}).get("genres") else ""),
            "track_no": 0,
            "duration": duration,
            "tag": "JAMENDO",
            "accent": (artist[:1] or title[:1] or "J").upper(),
            "path": "",
            "size": 0,
            "mtime": 0,
            "year": str(raw.get("releasedate") or "")[:4],
            "relative_path": "",
            "category": "Jamendo",
            "root_name": "Jamendo",
            "root_key": "jamendo",
            "root_label": "Jamendo API",
            "source": "jamendo",
            "source_label": "Jamendo",
            "playable": bool(audio_url),
            "stream_url": audio_url,
            "cover_available": bool(cover_url),
            "cover_type": "remote",
            "cover_mime": "",
            "cover_path": "",
            "cover_url": cover_url,
            "lyrics_available": False,
            "lyrics_type": "none",
            "lyrics_url": f"/api/apple-audio/lyrics/jamendo:{track_id}",
        }

    def search_jamendo(self, query, limit=None):
        cfg = self._config()
        text = str(query or "").strip()
        if not text or not self._jamendo_enabled(cfg):
            return []
        client_id = _jamendo_client_id(cfg)
        try:
            max_items = max(1, min(int(limit or cfg.get("jamendo_limit", 20) or 20), 50))
        except Exception:
            max_items = 20
        base = str(cfg.get("jamendo_api_base") or "https://api.jamendo.com/v3.0").rstrip("/")
        endpoint = f"{base}/tracks/"
        params = {
            "client_id": client_id,
            "format": "json",
            "limit": str(max_items),
            "search": text,
            "include": "musicinfo",
            "audioformat": "mp32",
            "order": "popularity_total",
        }
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "SmartCenter/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
        except (urllib.error.URLError, TimeoutError, ValueError):
            return []
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            return []
        results = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            item = self._jamendo_track_to_item(raw)
            if not item:
                continue
            results.append(item)
            self._remember_remote_track(item)
        return results

    def search_sources(self, query, include_jamendo=False, limit=None):
        local_results = self.search(query)
        if limit:
            try:
                local_results = local_results[: max(1, int(limit))]
            except Exception:
                pass
        jamendo_results = self.search_jamendo(query, limit=limit) if include_jamendo else []
        merged = local_results + jamendo_results
        return {
            "results": merged,
            "local": local_results,
            "jamendo": jamendo_results,
            "sources": {
                "nas": {"enabled": True, "count": len(local_results)},
                "jamendo": {
                    "enabled": self._jamendo_enabled(),
                    "count": len(jamendo_results),
                },
            },
        }

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
        if play_now and self._local_player_enabled():
            self._start_local_player_for_track(track_id)
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

    def transport(self, action, mode=None):
        action = str(action or "").strip().lower()
        with self.lock:
            self._tick_locked()
            queue = self.state.get("queue_ids", [])
            current_id = str(self.state.get("current_track_id") or "").strip()
            if action in {"volume", "set_volume"}:
                volume = _coerce_volume_percent(mode)
                self.state["volume_percent"] = volume
                self.state["last_action"] = f"Volume: {volume}%"
                target_track_id = ""
            elif action in {"playback_mode", "set_mode", "mode"}:
                playback_mode = _normalize_playback_mode(mode)
                self.state["playback_mode"] = playback_mode
                self.state["last_action"] = f"Playback mode: {playback_mode}"
                target_track_id = ""
            elif action == "toggle":
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
                target_track_id = str(self.state.get("current_track_id") or "").strip()
            elif action in {"next", "ended"}:
                is_manual_next = action == "next"
                target_track_id = self._select_next_track_locked(manual=is_manual_next)
                if not target_track_id and action == "ended":
                    self.state["is_playing"] = False
                    self.state["elapsed_sec"] = 0
                    self.state["last_action"] = "Playback ended"
                    target_track_id = ""
                elif not target_track_id:
                    raise ValueError("no playable track available")
                else:
                    self._apply_selected_track_locked(target_track_id, "Next track", playing=True)
                    self.state["last_action"] = "Next track"
            elif action == "prev":
                if not current_id:
                    raise ValueError("no track selected")
                self.state["elapsed_sec"] = 0
                self.state["last_action"] = "Restart track"
                target_track_id = current_id
            elif action == "favorite":
                if not current_id:
                    raise ValueError("no track selected")
                name = self.library_by_id.get(current_id, {}).get("title") or current_id
                self.state["last_action"] = f"Favorite: {name}"
                target_track_id = ""
            else:
                raise ValueError("unsupported transport action")
            self.state["updated_at"] = datetime.now().isoformat()
            should_play = self._local_player_enabled() and bool(self.state.get("is_playing")) and bool(target_track_id)
            should_stop = self._local_player_enabled() and action == "toggle" and not bool(self.state.get("is_playing"))
        if should_stop:
            self._stop_local_player("Paused")
        elif should_play:
            self._start_local_player_for_track(target_track_id)
        return self.snapshot()


apple_audio_service = AppleAudioService()
