import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from copy import deepcopy
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit, urlunsplit
import queue

import cv2
import numpy as np
from flask import Blueprint, Response, jsonify, request

from audit import log_audit_event
from auth.decorators import require_permission
from auth.operation_lock import acquire_operation_lock, release_operation_lock
from auth.session import get_current_user
from config import CONFIG, save_config
from data_logger import add_log
from paths import DATA_DIR

bp = Blueprint("door", __name__)


DOOR_COMMANDS = {
    "open": bytes.fromhex("CC DD 33 01 00 01 00 01 36 6C"),
    "stop": bytes.fromhex("CC DD 33 01 00 02 00 02 38 70"),
    "close": bytes.fromhex("CC DD 33 01 00 04 00 04 3C 78"),
}

DEFAULT_REGION = {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8}
DEFAULT_CAMERA_KEYS = ("main", "aux")
DOOR_CAMERA_ERROR_TEXT = {
    "camera_disabled": "监控已停用",
    "waiting_for_stream": "等待视频流",
    "camera_removed": "监控配置已移除",
    "rtsp_missing": "未配置 RTSP",
    "rtsp_host_missing": "RTSP 地址缺少主机",
    "rtsp_port_timeout": "摄像头端口连接超时",
    "rtsp_port_refused": "摄像头端口拒绝连接",
    "rtsp_no_route": "到摄像头网络不通",
    "rtsp_host_unreachable": "摄像头主机不可达",
    "rtsp_network_unreachable": "目标网段不可达",
    "rtsp_connect_error": "RTSP 网络连接失败",
    "transport_tcp_failed": "TCP 取流失败",
    "transport_udp_failed": "UDP 取流失败",
    "capture_open_failed": "取流打开失败",
    "capture_read_failed": "视频读取失败",
    "config_changed": "配置已变更，等待重连",
}

door_status_info = {
    "current_status": "unknown_calibration",
    "transition_status": None,
    "last_move_time": 0,
    "score_history": [],
    "diff_c": 0,
    "diff_o": 0,
    "detection_camera": "main",
    "engine": "legacy",
    "confidence": 0.0,
    "camera_votes": {},
    "people_count": 0,
    "zone_counts": {},
    "updated_at": None,
}
_LAST_LOGGED_DOOR_STABLE_STATE = None
status_lock = threading.Lock()
frame_lock = threading.Lock()
camera_state_lock = threading.Lock()
camera_worker_lock = threading.Lock()

latest_frame = None
camera_frames = {}
camera_states = {}
camera_worker_threads = {}
camera_worker_stop_events = {}
camera_preview_queues = {}

record_lock = threading.Lock()
record_state = {
    "running": False,
    "started_at": None,
    "session_id": "",
    "files": {},
    "pids": {},
}

vision_runtime_info = {
    "stable_state": "unknown_calibration",
    "pending_state": None,
    "pending_hits": 0,
    "unknown_hits": 0,
    "last_candidate": "unknown",
    "last_fusion": {},
    "per_camera_history": {},
    "last_stable_change_at": 0.0,
    "last_transition_mark_at": 0.0,
}

model_rebuild_state = {
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_status": "idle",
    "last_message": "",
    "last_output": "",
    "last_exit_code": None,
    "last_model_path": "",
}
model_rebuild_lock = threading.Lock()
MODEL_REBUILD_STATUS_FILE = os.path.join(str(DATA_DIR), "runtime", "door_model_rebuild_status.json")
INFER_TRACE_FILE = os.path.join(str(DATA_DIR), "runtime", "door_infer_trace.jsonl")

DEFAULT_VISION_CONFIG = {
    "enabled": False,
    "provider": "legacy",
    "http_url": "http://127.0.0.1:18080/infer/door_state",
    "request_timeout_ms": 700,
    "poll_interval_sec": 0.5,
    "fusion_enabled": True,
    "fusion_settle_frames": 3,
    "fusion_history_size": 8,
    "fusion_min_confidence": 0.55,
    "fusion_margin": 0.15,
    "allow_shared_reference": False,
    "camera_weights": {"main": 1.0, "aux": 1.0},
    "people_count_enabled": False,
    "zone_count_enabled": False,
    "zones": {"main": {}, "aux": {}},
    "http_send_full_frame": False,
    "http_reference_assist": True,
    "http_reference_min_confidence": 0.08,
    "http_reference_weight": 0.75,
    "http_model_weight": 0.45,
    "http_reference_min_mean_absdiff_gap": 1.5,
    "reference_valid_min_gap": 3.5,
    # Stability guards for single-camera or weak-fusion situations.
    "single_camera_min_confidence": 0.58,
    "switch_cooldown_sec": 1.2,
    "closed_switch_extra_confidence": 0.12,
    "closed_switch_extra_settle_frames": 1,
    "open_switch_extra_confidence": 0.0,
    "open_switch_extra_settle_frames": 0,
    "trace_enabled": True,
    "trace_max_mb": 20,
    "degrade_unready_camera_weight": True,
    "unready_camera_weight_factor": 0.35,
    # Multi-camera disagreement handling.
    "require_dual_votes_for_switch": False,
    "disagreement_winner_min_score": 0.68,
    "disagreement_winner_min_gap": 0.08,
    "disagreement_winner_min_ratio": 1.22,
    "disagreement_winner_min_confidence": 0.6,
}

DEFAULT_PREVIEW_CONFIG = {
    "fps": 10.0,
    "jpeg_quality": 62,
    "max_width": 960,
    "use_substream": True,
    "substream_channel": "102",
}


def _offline_placeholder_frame(camera_key):
    payload = _camera_payload(camera_key, include_rtsp=False)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (18, 24, 39)
    cv2.rectangle(frame, (40, 40), (1240, 680), (71, 85, 105), 2)
    title = _camera_placeholder_title(camera_key, payload)
    detail = payload.get("last_error_text") or _translate_camera_error(
        payload.get("last_error") or ("camera_disabled" if payload.get("enabled") is False else "waiting_for_stream")
    )
    host = payload.get("host") or "--"
    configured = "yes" if payload.get("configured") else "no"
    enabled = "yes" if payload.get("enabled") else "no"
    lines = [
        title,
        f"host: {host}",
        f"enabled: {enabled} | configured: {configured}",
        f"error: {detail}",
    ]
    y = 220
    for idx, line in enumerate(lines):
        scale = 1.1 if idx == 0 else 0.8
        thickness = 2 if idx == 0 else 1
        cv2.putText(frame, line, (90, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (226, 232, 240), thickness, cv2.LINE_AA)
        y += 70 if idx == 0 else 52
    cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (90, 610), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (148, 163, 184), 1, cv2.LINE_AA)
    return frame


def _camera_placeholder_title(camera_key, payload):
    key = str(camera_key or "").strip().lower()
    label_map = {
        "main": "Main camera",
        "aux": "Aux camera",
    }
    label = label_map.get(key) or f"Camera {key or '--'}"
    host = str((payload or {}).get("host") or "").strip()
    return f"{label}{f' / {host}' if host else ''} - offline"


def _translate_camera_error(error_code):
    text = str(error_code or "").strip()
    if not text:
        return ""
    if text.startswith("rtsp_connect_error:"):
        return DOOR_CAMERA_ERROR_TEXT.get("rtsp_connect_error", "RTSP 网络连接失败")
    return DOOR_CAMERA_ERROR_TEXT.get(text, text)


def _default_camera_state(camera_key, name=None):
    return {
        "key": camera_key,
        "name": name or camera_key,
        "enabled": True,
        "configured": False,
        "online": False,
        "transport": "",
        "transport_attempts": [],
        "last_error": "",
        "last_ok_at": None,
        "last_attempt_at": None,
        "updated_at": None,
        "frame_width": 0,
        "frame_height": 0,
        "rtsp_url": "",
        "host": "",
        "note": "",
    }


def _get_door_config():
    return CONFIG.get("door_config", {}) if isinstance(CONFIG, dict) else {}


def _get_vision_config():
    cfg = _get_door_config().get("vision", {})
    merged = deepcopy(DEFAULT_VISION_CONFIG)
    if isinstance(cfg, dict):
        for key, value in cfg.items():
            if key == "camera_weights" and isinstance(value, dict):
                merged["camera_weights"] = {
                    str(cam_key): max(float(cam_weight), 0.0)
                    for cam_key, cam_weight in value.items()
                    if str(cam_key).strip()
                } or deepcopy(DEFAULT_VISION_CONFIG["camera_weights"])
                continue
            if key == "zones" and isinstance(value, dict):
                merged["zones"] = deepcopy(value)
                continue
            merged[key] = value

    try:
        merged["poll_interval_sec"] = max(0.1, min(float(merged.get("poll_interval_sec", 0.5) or 0.5), 5.0))
    except Exception:
        merged["poll_interval_sec"] = 0.5
    try:
        merged["fusion_settle_frames"] = max(1, min(int(merged.get("fusion_settle_frames", 3) or 3), 30))
    except Exception:
        merged["fusion_settle_frames"] = 3
    try:
        merged["fusion_history_size"] = max(2, min(int(merged.get("fusion_history_size", 8) or 8), 50))
    except Exception:
        merged["fusion_history_size"] = 8
    try:
        merged["fusion_min_confidence"] = max(0.0, min(float(merged.get("fusion_min_confidence", 0.55) or 0.55), 1.0))
    except Exception:
        merged["fusion_min_confidence"] = 0.55
    try:
        merged["fusion_margin"] = max(0.0, min(float(merged.get("fusion_margin", 0.15) or 0.15), 1.0))
    except Exception:
        merged["fusion_margin"] = 0.15
    try:
        merged["request_timeout_ms"] = max(100, min(int(merged.get("request_timeout_ms", 700) or 700), 5000))
    except Exception:
        merged["request_timeout_ms"] = 700
    merged["enabled"] = bool(merged.get("enabled", False))
    merged["fusion_enabled"] = bool(merged.get("fusion_enabled", True))
    merged["allow_shared_reference"] = bool(merged.get("allow_shared_reference", False))
    merged["people_count_enabled"] = bool(merged.get("people_count_enabled", False))
    merged["zone_count_enabled"] = bool(merged.get("zone_count_enabled", False))
    merged["http_send_full_frame"] = bool(merged.get("http_send_full_frame", False))
    merged["http_reference_assist"] = bool(merged.get("http_reference_assist", True))
    merged["degrade_unready_camera_weight"] = bool(merged.get("degrade_unready_camera_weight", True))
    merged["require_dual_votes_for_switch"] = bool(merged.get("require_dual_votes_for_switch", False))
    merged["provider"] = str(merged.get("provider") or "legacy").strip().lower()
    merged["http_url"] = str(merged.get("http_url") or DEFAULT_VISION_CONFIG["http_url"]).strip() or DEFAULT_VISION_CONFIG["http_url"]
    try:
        merged["http_reference_min_confidence"] = max(
            0.0, min(float(merged.get("http_reference_min_confidence", 0.08) or 0.08), 1.0)
        )
    except Exception:
        merged["http_reference_min_confidence"] = 0.08
    try:
        merged["http_reference_weight"] = max(0.0, min(float(merged.get("http_reference_weight", 0.75) or 0.75), 3.0))
    except Exception:
        merged["http_reference_weight"] = 0.75
    try:
        merged["http_model_weight"] = max(0.0, min(float(merged.get("http_model_weight", 0.45) or 0.45), 3.0))
    except Exception:
        merged["http_model_weight"] = 0.45
    try:
        merged["http_reference_min_mean_absdiff_gap"] = max(
            0.0, min(float(merged.get("http_reference_min_mean_absdiff_gap", 1.5) or 1.5), 50.0)
        )
    except Exception:
        merged["http_reference_min_mean_absdiff_gap"] = 1.5
    try:
        merged["single_camera_min_confidence"] = max(
            0.0, min(float(merged.get("single_camera_min_confidence", 0.58) or 0.58), 1.0)
        )
    except Exception:
        merged["single_camera_min_confidence"] = 0.58
    try:
        merged["switch_cooldown_sec"] = max(0.0, min(float(merged.get("switch_cooldown_sec", 1.2) or 1.2), 15.0))
    except Exception:
        merged["switch_cooldown_sec"] = 1.2
    try:
        merged["closed_switch_extra_confidence"] = max(
            0.0, min(float(merged.get("closed_switch_extra_confidence", 0.12) or 0.12), 1.0)
        )
    except Exception:
        merged["closed_switch_extra_confidence"] = 0.12
    try:
        merged["closed_switch_extra_settle_frames"] = max(
            0, min(int(merged.get("closed_switch_extra_settle_frames", 1) or 1), 8)
        )
    except Exception:
        merged["closed_switch_extra_settle_frames"] = 1
    try:
        merged["open_switch_extra_confidence"] = max(
            0.0, min(float(merged.get("open_switch_extra_confidence", 0.0) or 0.0), 1.0)
        )
    except Exception:
        merged["open_switch_extra_confidence"] = 0.0
    try:
        merged["open_switch_extra_settle_frames"] = max(
            0, min(int(merged.get("open_switch_extra_settle_frames", 0) or 0), 8)
        )
    except Exception:
        merged["open_switch_extra_settle_frames"] = 0
    merged["trace_enabled"] = bool(merged.get("trace_enabled", True))
    try:
        merged["trace_max_mb"] = max(2, min(int(merged.get("trace_max_mb", 20) or 20), 200))
    except Exception:
        merged["trace_max_mb"] = 20
    try:
        merged["unready_camera_weight_factor"] = max(
            0.0, min(float(merged.get("unready_camera_weight_factor", 0.35) or 0.35), 1.0)
        )
    except Exception:
        merged["unready_camera_weight_factor"] = 0.35
    try:
        merged["disagreement_winner_min_score"] = max(
            0.0, min(float(merged.get("disagreement_winner_min_score", 0.68) or 0.68), 5.0)
        )
    except Exception:
        merged["disagreement_winner_min_score"] = 0.68
    try:
        merged["disagreement_winner_min_gap"] = max(
            0.0, min(float(merged.get("disagreement_winner_min_gap", 0.08) or 0.08), 5.0)
        )
    except Exception:
        merged["disagreement_winner_min_gap"] = 0.08
    try:
        merged["disagreement_winner_min_ratio"] = max(
            1.0, min(float(merged.get("disagreement_winner_min_ratio", 1.22) or 1.22), 20.0)
        )
    except Exception:
        merged["disagreement_winner_min_ratio"] = 1.22
    try:
        merged["disagreement_winner_min_confidence"] = max(
            0.0, min(float(merged.get("disagreement_winner_min_confidence", 0.6) or 0.6), 1.0)
        )
    except Exception:
        merged["disagreement_winner_min_confidence"] = 0.6
    if not isinstance(merged.get("camera_weights"), dict):
        merged["camera_weights"] = deepcopy(DEFAULT_VISION_CONFIG["camera_weights"])
    zones_cfg = merged.get("zones", {}) if isinstance(merged.get("zones"), dict) else {}
    normalized_zones = {}
    for item in _get_camera_configs():
        cam_key = str(item.get("key") or "").strip()
        if not cam_key:
            continue
        zone_defs = zones_cfg.get(cam_key, {}) if isinstance(zones_cfg.get(cam_key), dict) else {}
        zone_map = {}
        for zone_name, points in zone_defs.items():
            zone_key = str(zone_name or "").strip()
            if not zone_key or not isinstance(points, list):
                continue
            clean_points = []
            for pt in points:
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    continue
                try:
                    px = max(0.0, min(float(pt[0]), 1.0))
                    py = max(0.0, min(float(pt[1]), 1.0))
                except Exception:
                    continue
                clean_points.append([px, py])
            if len(clean_points) >= 3:
                zone_map[zone_key] = clean_points
        normalized_zones[cam_key] = zone_map
    merged["zones"] = normalized_zones
    return merged


def _get_preview_config():
    cfg = _get_door_config().get("preview", {})
    merged = deepcopy(DEFAULT_PREVIEW_CONFIG)
    if isinstance(cfg, dict):
        merged.update(cfg)
    try:
        merged["fps"] = max(2.0, min(float(merged.get("fps", 12.0) or 12.0), 25.0))
    except Exception:
        merged["fps"] = 12.0
    try:
        merged["jpeg_quality"] = max(45, min(int(merged.get("jpeg_quality", 68) or 68), 95))
    except Exception:
        merged["jpeg_quality"] = 68
    try:
        merged["max_width"] = max(640, min(int(merged.get("max_width", 1280) or 1280), 2560))
    except Exception:
        merged["max_width"] = 1280
    merged["use_substream"] = bool(merged.get("use_substream", True))
    channel_raw = str(merged.get("substream_channel", "102") or "102").strip()
    merged["substream_channel"] = channel_raw if channel_raw.isdigit() else "102"
    return merged


def _get_camera_match_threshold(camera_key):
    door_cfg = _get_door_config()
    base_threshold = door_cfg.get("match_threshold", 1500)
    threshold_map = door_cfg.get("match_thresholds", {}) if isinstance(door_cfg.get("match_thresholds"), dict) else {}
    raw_value = threshold_map.get(str(camera_key).strip(), base_threshold)
    try:
        value = int(raw_value or base_threshold)
    except Exception:
        value = int(base_threshold or 1500)
    return max(100, min(value, 500000))


def _set_camera_match_threshold(camera_key, threshold):
    CONFIG.setdefault("door_config", {})
    threshold_map = CONFIG["door_config"].get("match_thresholds", {}) if isinstance(CONFIG["door_config"].get("match_thresholds"), dict) else {}
    threshold_map[str(camera_key).strip() or _preferred_detection_camera()] = int(max(100, min(int(threshold), 500000)))
    CONFIG["door_config"]["match_thresholds"] = threshold_map
    if str(camera_key).strip() == _preferred_detection_camera():
        CONFIG["door_config"]["match_threshold"] = int(threshold_map.get(str(camera_key).strip(), threshold))


def _clone_rtsp_url_with_host(rtsp_url, host_value):
    base_url = str(rtsp_url or "").strip()
    host_value = str(host_value or "").strip()
    if not base_url or not host_value:
        return ""
    try:
        parsed = urlsplit(base_url)
    except Exception:
        return base_url
    if not parsed.scheme:
        return base_url

    port = parsed.port
    host_part = host_value
    if not host_value.startswith("[") and host_value.count(":") == 1:
        maybe_host, maybe_port = host_value.rsplit(":", 1)
        if maybe_port.isdigit():
            host_part = maybe_host
            port = int(maybe_port)

    if ":" in host_part and not host_part.startswith("["):
        host_part = f"[{host_part}]"

    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password is not None:
            auth += f":{parsed.password}"
        auth += "@"

    netloc = auth + host_part
    if port:
        netloc += f":{port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path or "", parsed.query or "", parsed.fragment or ""))


def _rtsp_url_replace_channel(rtsp_url, channel="102"):
    url = str(rtsp_url or "").strip()
    channel = str(channel or "").strip()
    if not url or not channel:
        return url
    marker = "/Streaming/Channels/"
    pos = url.find(marker)
    if pos < 0:
        return url
    start = pos + len(marker)
    end = start
    while end < len(url) and url[end].isdigit():
        end += 1
    if end == start:
        return url
    return f"{url[:start]}{channel}{url[end:]}"


def _preview_rtsp_url(camera_cfg):
    if not isinstance(camera_cfg, dict):
        return ""
    preview_cfg = _get_preview_config()
    use_substream = bool(preview_cfg.get("use_substream", True))
    substream_channel = str(preview_cfg.get("substream_channel", "102") or "102").strip() or "102"
    rtsp = str(camera_cfg.get("rtsp_url") or "").strip()
    if not rtsp:
        return ""
    if not use_substream:
        return rtsp
    return _rtsp_url_replace_channel(rtsp, substream_channel)


def _probe_rtsp_endpoint(rtsp_url, timeout_sec=2):
    base_url = str(rtsp_url or "").strip()
    if not base_url:
        return False, "rtsp_missing"
    try:
        parsed = urlsplit(base_url)
    except Exception:
        return False, "rtsp_connect_error"
    host = parsed.hostname
    port = parsed.port or 554
    if not host:
        return False, "rtsp_host_missing"
    try:
        conn = socket.create_connection((host, int(port)), timeout=max(1, float(timeout_sec)))
        conn.close()
        return True, ""
    except TimeoutError:
        return False, "rtsp_port_timeout"
    except ConnectionRefusedError:
        return False, "rtsp_port_refused"
    except OSError as exc:
        err = getattr(exc, "errno", None)
        if err in (113, 65):
            return False, "rtsp_no_route"
        if err in (118, 64):
            return False, "rtsp_host_unreachable"
        if err in (101,):
            return False, "rtsp_network_unreachable"
        if err in (111,):
            return False, "rtsp_port_refused"
        if err in (110,):
            return False, "rtsp_port_timeout"
        return False, f"rtsp_connect_error:{exc}"


def _get_camera_configs():
    door_cfg = _get_door_config()
    legacy_rtsp = str(door_cfg.get("rtsp_url") or "").strip()
    cameras = door_cfg.get("cameras")
    normalized = []
    if isinstance(cameras, list):
        for idx, item in enumerate(cameras):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or f"camera_{idx + 1}").strip() or f"camera_{idx + 1}"
            normalized.append(
                {
                    "key": key,
                    "name": str(item.get("name") or key).strip() or key,
                    "rtsp_url": str(item.get("rtsp_url") or "").strip(),
                    "enabled": bool(item.get("enabled", True)),
                    "host": str(item.get("host") or "").strip(),
                    "note": str(item.get("note") or "").strip(),
                }
            )
    if not normalized:
        normalized.append(
            {
                "key": "main",
                "name": "大门内",
                "rtsp_url": legacy_rtsp,
                "enabled": True,
                "host": "192.168.40.11",
                "note": "",
            }
        )
    key_set = {item["key"] for item in normalized}
    if "main" not in key_set:
        normalized.insert(
            0,
            {
                "key": "main",
                "name": "大门内",
                "rtsp_url": legacy_rtsp,
                "enabled": True,
                "host": "192.168.40.11",
                "note": "",
            },
        )
    if "aux" not in key_set:
        normalized.append(
            {
                "key": "aux",
                "name": "大门外",
                "rtsp_url": _clone_rtsp_url_with_host(legacy_rtsp, "192.168.40.41"),
                "enabled": True,
                "host": "192.168.40.41",
                "note": "门外监控补盲",
            }
        )
    for item in normalized:
        if item.get("key") == "aux" and not str(item.get("rtsp_url") or "").strip():
            item["rtsp_url"] = _clone_rtsp_url_with_host(legacy_rtsp, item.get("host") or "192.168.40.41")
        if item.get("key") == "main":
            item["name"] = str(item.get("name") or "大门内").strip() or "大门内"
            if not str(item.get("host") or "").strip():
                item["host"] = "192.168.40.11"
        if item.get("key") == "aux":
            item["name"] = str(item.get("name") or "大门外").strip() or "大门外"
            if not str(item.get("host") or "").strip():
                item["host"] = "192.168.40.41"
    return normalized


def _preferred_detection_camera():
    preferred = str(_get_door_config().get("preferred_detection_camera") or "main").strip() or "main"
    available_keys = [item["key"] for item in _get_camera_configs()]
    return preferred if preferred in available_keys else (available_keys[0] if available_keys else "main")


def _get_camera_config(camera_key):
    camera_key = str(camera_key or "").strip()
    for item in _get_camera_configs():
        if item.get("key") == camera_key:
            return item
    return None


def _get_view_slots():
    door_cfg = _get_door_config()
    raw_slots = door_cfg.get("view_slots", {}) if isinstance(door_cfg.get("view_slots"), dict) else {}
    available_keys = [item["key"] for item in _get_camera_configs()]
    if not available_keys:
        return {"left": "main", "right": "main"}
    left = str(raw_slots.get("left") or ("aux" if "aux" in available_keys else available_keys[0])).strip()
    right = str(raw_slots.get("right") or ("main" if "main" in available_keys else available_keys[0])).strip()
    if left not in available_keys:
        left = "aux" if "aux" in available_keys else available_keys[0]
    if right not in available_keys:
        right = "main" if "main" in available_keys else available_keys[0]
    if left == right and len(available_keys) > 1:
        left = next((key for key in available_keys if key != right), left)
    return {"left": left, "right": right}


def _get_region_pct(camera_key=None):
    door_cfg = _get_door_config()
    if camera_key:
        regions = door_cfg.get("regions", {}) if isinstance(door_cfg.get("regions"), dict) else {}
        region = regions.get(str(camera_key).strip())
        if isinstance(region, dict):
            return region
    region = door_cfg.get("region_pct", DEFAULT_REGION)
    return region if isinstance(region, dict) else DEFAULT_REGION


def _sync_camera_state_defaults():
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    with camera_state_lock:
        known_keys = {item["key"] for item in _get_camera_configs()}
        for cfg in _get_camera_configs():
            current = dict(camera_states.get(cfg["key"], _default_camera_state(cfg["key"], cfg.get("name"))))
            current["name"] = cfg["name"]
            current["enabled"] = bool(cfg.get("enabled", True))
            current["configured"] = bool(cfg.get("rtsp_url"))
            current["rtsp_url"] = cfg.get("rtsp_url", "")
            current["host"] = cfg.get("host", "")
            current["note"] = cfg.get("note", "")
            current.setdefault("updated_at", now_iso)
            camera_states[cfg["key"]] = current
            camera_frames.setdefault(cfg["key"], None)
            camera_preview_queues.setdefault(cfg["key"], queue.Queue(maxsize=2))
        for key in list(camera_states.keys()):
            if key not in known_keys and key not in DEFAULT_CAMERA_KEYS:
                camera_states.pop(key, None)
                camera_frames.pop(key, None)
                camera_preview_queues.pop(key, None)


def _set_camera_state(camera_key, **kwargs):
    with camera_state_lock:
        base = dict(camera_states.get(camera_key, _default_camera_state(camera_key)))
        base.update(kwargs)
        base["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        camera_states[camera_key] = base


def _set_camera_frame(camera_key, frame):
    global latest_frame
    with frame_lock:
        camera_frames[camera_key] = frame
        preferred = _preferred_detection_camera()
        preferred_frame = camera_frames.get(preferred)
        if preferred_frame is not None:
            latest_frame = preferred_frame
        elif frame is not None:
            latest_frame = frame
        if frame is not None:
            q = camera_preview_queues.get(str(camera_key))
            if q is not None:
                try:
                    while q.qsize() >= 2:
                        q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(frame.copy())
                except Exception:
                    pass


def _capture_frame(camera_key, allow_fallback=True):
    with frame_lock:
        frame = camera_frames.get(camera_key)
        if frame is not None:
            return frame.copy()
        if allow_fallback and camera_key == _preferred_detection_camera() and latest_frame is not None:
            return latest_frame.copy()
    return None


def _capture_latest_preview_frame(camera_key, allow_fallback=True):
    key = str(camera_key or "").strip()
    q = camera_preview_queues.get(key)
    if q is not None:
        latest = None
        while True:
            try:
                latest = q.get_nowait()
            except Exception:
                break
        if latest is not None:
            return latest
    return _capture_frame(key, allow_fallback=allow_fallback)


def _open_rtsp_capture(rtsp_url, transport, timeout_sec=4):
    previous_opt = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
    try:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}|fflags;nobuffer|flags;low_delay|max_delay;500000|stimeout;3000000"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap, frame
            time.sleep(0.08)
        cap.release()
        return None
    finally:
        if previous_opt is None:
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_opt


def _camera_capture_worker(camera_key, stop_event):
    while not stop_event.is_set():
        cfg = _get_camera_config(camera_key)
        reconnect_delay = max(1, int(_get_door_config().get("camera_reconnect_delay_sec", 2) or 2))
        timeout_sec = max(1, int(_get_door_config().get("camera_probe_timeout_sec", 4) or 4))
        if not cfg:
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_key,
                enabled=False,
                configured=False,
                online=False,
                transport="",
                last_error="camera_removed",
                transport_attempts=[],
                rtsp_url="",
                host="",
                note="",
            )
            _set_camera_frame(camera_key, None)
            stop_event.wait(0.5)
            continue

        camera_name = cfg["name"]
        infer_rtsp = cfg.get("rtsp_url", "")
        preview_rtsp = _preview_rtsp_url(cfg)
        rtsp = preview_rtsp or infer_rtsp
        enabled = bool(cfg.get("enabled", True))
        host = cfg.get("host", "")
        note = cfg.get("note", "")

        if not enabled:
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=False,
                configured=bool(rtsp),
                online=False,
                transport="",
                last_error="camera_disabled",
                transport_attempts=[],
                rtsp_url=rtsp,
                host=host,
                note=note,
            )
            _set_camera_frame(camera_key, None)
            stop_event.wait(0.5)
            continue

        if not rtsp:
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=True,
                configured=False,
                online=False,
                transport="",
                last_error="rtsp_missing",
                transport_attempts=[],
                rtsp_url="",
                host=host,
                note=note,
            )
            _set_camera_frame(camera_key, None)
            stop_event.wait(0.5)
            continue

        probe_ok, probe_error = _probe_rtsp_endpoint(rtsp, timeout_sec=min(timeout_sec, 3))
        if not probe_ok:
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=True,
                configured=True,
                online=False,
                transport="",
                transport_attempts=[],
                last_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                last_error=probe_error,
                rtsp_url=rtsp,
                host=host,
                note=note,
            )
            _set_camera_frame(camera_key, None)
            stop_event.wait(reconnect_delay)
            continue

        attempts = []
        cap = None
        first_frame = None
        selected_transport = ""
        last_error = ""
        for transport in ("tcp", "udp"):
            if stop_event.is_set():
                break
            attempts.append(transport)
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=True,
                configured=True,
                online=False,
                transport=transport,
                transport_attempts=list(attempts),
                last_attempt_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                rtsp_url=rtsp,
                host=host,
                note=note,
            )
            opened = _open_rtsp_capture(rtsp, transport, timeout_sec=timeout_sec)
            if opened:
                cap, first_frame = opened
                selected_transport = transport
                last_error = ""
                break
            last_error = f"transport_{transport}_failed"

        if stop_event.is_set():
            if cap is not None:
                cap.release()
            break

        if cap is None or first_frame is None:
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=True,
                configured=True,
                online=False,
                transport="",
                transport_attempts=attempts,
                last_error=last_error or "capture_open_failed",
                rtsp_url=rtsp,
                host=host,
                note=note,
            )
            _set_camera_frame(camera_key, None)
            stop_event.wait(reconnect_delay)
            continue

        frame = first_frame
        config_changed = False
        while not stop_event.is_set():
            current_cfg = _get_camera_config(camera_key) or {}
            current_infer_rtsp = str(current_cfg.get("rtsp_url") or "").strip()
            current_preview_rtsp = _preview_rtsp_url(current_cfg)
            current_effective_rtsp = current_preview_rtsp or current_infer_rtsp
            if (
                not current_cfg
                or current_effective_rtsp != rtsp
                or bool(current_cfg.get("enabled", True)) != enabled
            ):
                config_changed = True
                last_error = "config_changed"
                break
            if frame is None:
                ok, frame = cap.read()
                if not ok or frame is None:
                    last_error = "capture_read_failed"
                    break
            _set_camera_frame(camera_key, frame)
            _set_camera_state(
                camera_key,
                key=camera_key,
                name=camera_name,
                enabled=True,
                configured=True,
                online=True,
                transport=selected_transport,
                transport_attempts=attempts,
                last_error="",
                last_ok_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                frame_width=int(frame.shape[1]) if getattr(frame, "shape", None) is not None else 0,
                frame_height=int(frame.shape[0]) if getattr(frame, "shape", None) is not None else 0,
                rtsp_url=rtsp,
                host=host,
                note=note,
            )
            if stop_event.wait(0.03):
                break
            ok, next_frame = cap.read()
            if not ok or next_frame is None:
                last_error = "capture_read_failed"
                break
            # Drop stale buffered frames aggressively for lower latency.
            try:
                cap.grab()
            except Exception:
                pass
            frame = next_frame

        cap.release()
        _set_camera_state(
            camera_key,
            key=camera_key,
            name=camera_name,
            enabled=True,
            configured=True,
            online=False,
            transport=selected_transport,
            transport_attempts=attempts,
            last_error=last_error,
            rtsp_url=rtsp,
            host=host,
            note=note,
        )
        if stop_event.is_set():
            break
        if config_changed:
            stop_event.wait(0.1)
            continue
        stop_event.wait(reconnect_delay)


def camera_capture_loop():
    _sync_camera_state_defaults()
    while True:
        camera_cfgs = _get_camera_configs()
        active_keys = {cfg["key"] for cfg in camera_cfgs}
        with camera_worker_lock:
            for cfg in camera_cfgs:
                camera_key = cfg["key"]
                thread = camera_worker_threads.get(camera_key)
                stop_event = camera_worker_stop_events.get(camera_key)
                if thread is not None and thread.is_alive():
                    continue
                if stop_event is not None:
                    stop_event.set()
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=_camera_capture_worker,
                    args=(camera_key, stop_event),
                    name=f"door-cam-{camera_key}",
                    daemon=True,
                )
                camera_worker_stop_events[camera_key] = stop_event
                camera_worker_threads[camera_key] = thread
                thread.start()
            for camera_key in list(camera_worker_threads.keys()):
                if camera_key in active_keys:
                    continue
                stop_event = camera_worker_stop_events.pop(camera_key, None)
                if stop_event is not None:
                    stop_event.set()
                camera_worker_threads.pop(camera_key, None)
                _set_camera_frame(camera_key, None)
        time.sleep(1.0)


def _hist_match(source, template):
    oldshape = source.shape
    source = source.ravel()
    template = template.ravel()
    s_values, bin_idx, s_counts = np.unique(source, return_inverse=True, return_counts=True)
    t_values, t_counts = np.unique(template, return_counts=True)
    s_quantiles = np.cumsum(s_counts).astype(np.float64)
    s_quantiles /= s_quantiles[-1]
    t_quantiles = np.cumsum(t_counts).astype(np.float64)
    t_quantiles /= t_quantiles[-1]
    return np.interp(s_quantiles, t_quantiles, t_values)[bin_idx].reshape(oldshape)


def _compute_diff(img1, img2):
    try:
        img1 = _hist_match(img1, img2).astype(np.uint8)
    except Exception:
        pass
    delta = cv2.absdiff(img1, img2)
    thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return sum(cv2.contourArea(c) for c in contours)


def _runtime_refs_dir() -> Path:
    refs_dir = Path(DATA_DIR) / "runtime" / "door_refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    return refs_dir


def _safe_write_json(path: str, payload: dict) -> None:
    target = Path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp_path), str(target))


def _safe_write_gray_image(path: str, gray_frame) -> None:
    target = Path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", gray_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("jpeg_encode_failed")
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("wb") as f:
        f.write(encoded.tobytes())
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_path), str(target))


def _calc_region_rect(shape, camera_key):
    vh, vw = shape[:2]
    reg_pct = _get_region_pct(camera_key)
    x1 = max(0, min(int(float(reg_pct["p_x1"]) * vw), vw))
    y1 = max(0, min(int(float(reg_pct["p_y1"]) * vh), vh))
    x2 = max(0, min(int(float(reg_pct["p_x2"]) * vw), vw))
    y2 = max(0, min(int(float(reg_pct["p_y2"]) * vh), vh))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _load_reference_images():
    closed_path = _reference_path("closed", "")
    open_path = _reference_path("open", "")
    if not os.path.exists(closed_path) or not os.path.exists(open_path):
        return None, None
    ref_closed = cv2.imread(closed_path, cv2.IMREAD_GRAYSCALE)
    ref_open = cv2.imread(open_path, cv2.IMREAD_GRAYSCALE)
    if ref_closed is None or ref_open is None:
        return None, None
    return ref_closed, ref_open


def _reference_path(state, camera_key=None):
    suffix = str(camera_key or "").strip()
    filename = f"door_ref_{state}.jpg" if not suffix else f"door_ref_{state}_{suffix}.jpg"
    runtime_path = _runtime_refs_dir() / filename
    if runtime_path.exists():
        return str(runtime_path)
    # Backward compatibility: old deployments stored references in working directory.
    legacy_path = Path(filename)
    if legacy_path.exists():
        return str(legacy_path)
    return str(runtime_path)


def _reference_write_path(state, camera_key=None):
    suffix = str(camera_key or "").strip()
    filename = f"door_ref_{state}.jpg" if not suffix else f"door_ref_{state}_{suffix}.jpg"
    return str(_runtime_refs_dir() / filename)


def _load_reference_for_camera(state, camera_key):
    # Prefer camera-specific reference first, then fallback to legacy shared reference.
    path_specific = _reference_path(state, camera_key)
    if os.path.exists(path_specific):
        img = cv2.imread(path_specific, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            return img, path_specific
    path_legacy = _reference_path(state, "")
    if os.path.exists(path_legacy):
        img = cv2.imread(path_legacy, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            return img, path_legacy
    return None, ""


def _reference_pair_gap(frame_shape, camera_key):
    ref_closed, _ = _load_reference_for_camera("closed", camera_key)
    ref_open, _ = _load_reference_for_camera("open", camera_key)
    if ref_closed is None or ref_open is None:
        return None
    try:
        vh, vw = frame_shape[:2]
        rect = _calc_region_rect((vh, vw), camera_key)
        if rect is None:
            return None
        x1, y1, x2, y2 = rect
        closed_rs = cv2.resize(ref_closed, (vw, vh))[y1:y2, x1:x2]
        open_rs = cv2.resize(ref_open, (vw, vh))[y1:y2, x1:x2]
        if closed_rs.size == 0 or open_rs.size == 0:
            return None
        return float(np.mean(cv2.absdiff(closed_rs, open_rs)))
    except Exception:
        return None


def _legacy_detect_camera_state(frame, camera_key, ref_closed, ref_open):
    if frame is None:
        return {"camera_key": camera_key, "status": "unknown", "confidence": 0.0, "diff_c": 0.0, "diff_o": 0.0, "reason": "no_frame"}

    rect = _calc_region_rect(frame.shape, camera_key)
    if rect is None:
        return {"camera_key": camera_key, "status": "unknown", "confidence": 0.0, "diff_c": 0.0, "diff_o": 0.0, "reason": "invalid_region"}

    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    x1, y1, x2, y2 = rect
    door_region = gray[y1:y2, x1:x2]
    vh, vw = gray.shape
    crop_closed = cv2.resize(ref_closed, (vw, vh))[y1:y2, x1:x2]
    crop_open = cv2.resize(ref_open, (vw, vh))[y1:y2, x1:x2]

    diff_c = float(_compute_diff(door_region, crop_closed))
    diff_o = float(_compute_diff(door_region, crop_open))
    diff_gap = abs(diff_c - diff_o)
    diff_sum = max(diff_c + diff_o, 1.0)
    base_conf = max(0.0, min(diff_gap / diff_sum, 1.0))
    status = "closed" if diff_c <= diff_o else "open"
    if base_conf < 0.08:
        status = "unknown"
    return {
        "camera_key": camera_key,
        "status": status,
        "confidence": base_conf,
        "diff_c": diff_c,
        "diff_o": diff_o,
        "reason": "",
    }


def _legacy_detect_camera_state_auto_ref(frame, camera_key):
    ref_closed, ref_closed_path = _load_reference_for_camera("closed", camera_key)
    ref_open, ref_open_path = _load_reference_for_camera("open", camera_key)
    if ref_closed is None or ref_open is None:
        missing_parts = []
        if ref_closed is None:
            missing_parts.append("closed")
        if ref_open is None:
            missing_parts.append("open")
        return {
            "camera_key": camera_key,
            "status": "unknown",
            "confidence": 0.0,
            "diff_c": 0.0,
            "diff_o": 0.0,
            "reason": f"missing_reference:{','.join(missing_parts)}",
            "ref_closed_path": ref_closed_path,
            "ref_open_path": ref_open_path,
        }
    result = _legacy_detect_camera_state(frame, camera_key, ref_closed, ref_open)
    result["ref_closed_path"] = ref_closed_path
    result["ref_open_path"] = ref_open_path
    return result


def _status_score(status):
    if status == "open":
        return 1
    if status == "closed":
        return -1
    return 0


def _vision_http_infer(frame, camera_key, vision_cfg):
    url = str(vision_cfg.get("http_url") or "").strip()
    if not url:
        return {"camera_key": camera_key, "status": "unknown", "confidence": 0.0, "reason": "http_url_missing"}
    try:
        _, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    except Exception as exc:
        return {"camera_key": camera_key, "status": "unknown", "confidence": 0.0, "reason": f"encode_failed:{exc}"}

    payload = {
        "camera_key": camera_key,
        "image_b64": base64.b64encode(encoded.tobytes()).decode("ascii"),
        "send_full_frame": bool(vision_cfg.get("http_send_full_frame", False)),
        "zones_norm": (vision_cfg.get("zones", {}) if isinstance(vision_cfg.get("zones"), dict) else {}).get(camera_key, {}),
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    timeout_sec = max(float(vision_cfg.get("request_timeout_ms", 700) or 700) / 1000.0, 0.1)
    try:
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(text or "{}")
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"camera_key": camera_key, "status": "unknown", "confidence": 0.0, "reason": f"http_infer_failed:{exc}"}

    status = str(data.get("status") or "unknown").strip().lower()
    if status not in {"open", "closed", "unknown"}:
        status = "unknown"
    try:
        confidence = max(0.0, min(float(data.get("confidence", 0.0) or 0.0), 1.0))
    except Exception:
        confidence = 0.0
    return {
        "camera_key": camera_key,
        "status": status,
        "confidence": confidence,
        "diff_c": float(data.get("diff_c", 0.0) or 0.0),
        "diff_o": float(data.get("diff_o", 0.0) or 0.0),
        "people_count": int(data.get("people_count", 0) or 0),
        "zone_counts": data.get("zone_counts", {}) if isinstance(data.get("zone_counts"), dict) else {},
        "reason": "",
    }


def _detect_camera_state(frame, camera_key, ref_closed, ref_open, vision_cfg):
    provider = str(vision_cfg.get("provider") or "legacy").strip().lower()
    if vision_cfg.get("enabled") and provider in {"http", "remote_http"}:
        res = _vision_http_infer(frame, camera_key, vision_cfg)
        # Assist HTTP model with calibrated references, to suppress "open judged as closed".
        if frame is not None and bool(vision_cfg.get("http_reference_assist", True)):
            ref_pair_gap = _reference_pair_gap(frame.shape, camera_key)
            min_pair_gap = float(vision_cfg.get("reference_valid_min_gap", 3.5) or 3.5)
            if ref_pair_gap is not None and ref_pair_gap < min_pair_gap:
                res["reason"] = (
                    str(res.get("reason") or "")
                    + (f"|reference_pair_gap_too_small:{ref_pair_gap:.4f}" if str(res.get("reason") or "") else f"reference_pair_gap_too_small:{ref_pair_gap:.4f}")
                )
                res["ref_pair_gap"] = round(float(ref_pair_gap), 4)
                return res
            legacy = _legacy_detect_camera_state_auto_ref(frame, camera_key)
            legacy_conf = float(legacy.get("confidence", 0.0) or 0.0)
            min_ref_conf = float(vision_cfg.get("http_reference_min_confidence", 0.08) or 0.08)
            diff_c = float(legacy.get("diff_c", 0.0) or 0.0)
            diff_o = float(legacy.get("diff_o", 0.0) or 0.0)
            min_absdiff_gap = float(vision_cfg.get("http_reference_min_mean_absdiff_gap", 1.5) or 1.5)
            ref_gap = abs(diff_c - diff_o)
            if legacy.get("status") in {"open", "closed"} and legacy_conf >= min_ref_conf and ref_gap >= min_absdiff_gap:
                model_status = str(res.get("status") or "unknown")
                model_conf = float(res.get("confidence", 0.0) or 0.0)
                model_weight = float(vision_cfg.get("http_model_weight", 0.45) or 0.45)
                ref_weight = float(vision_cfg.get("http_reference_weight", 0.75) or 0.75)
                open_score = 0.0
                closed_score = 0.0
                if model_status == "open":
                    open_score += model_conf * model_weight
                elif model_status == "closed":
                    closed_score += model_conf * model_weight
                if legacy.get("status") == "open":
                    open_score += legacy_conf * ref_weight
                elif legacy.get("status") == "closed":
                    closed_score += legacy_conf * ref_weight

                if open_score > 0.0 or closed_score > 0.0:
                    merged_status = "open" if open_score > closed_score else "closed"
                    merged_conf = max(0.0, min(abs(open_score - closed_score) / max(open_score + closed_score, 1e-6), 1.0))
                    res["status"] = merged_status
                    res["confidence"] = merged_conf
                    res["diff_c"] = float(legacy.get("diff_c", res.get("diff_c", 0.0)) or 0.0)
                    res["diff_o"] = float(legacy.get("diff_o", res.get("diff_o", 0.0)) or 0.0)
                    res["ref_closed_path"] = str(legacy.get("ref_closed_path") or "")
                    res["ref_open_path"] = str(legacy.get("ref_open_path") or "")
                    res["reason"] = str(res.get("reason") or "") + ("|ref_assist" if str(res.get("reason") or "") else "ref_assist")

        if res.get("status") != "unknown" or not str(res.get("reason") or "").startswith("http_infer_failed"):
            return res
        # In HTTP mode, if remote inference is unreachable, do not force local reference dependency.
        return {
            "camera_key": camera_key,
            "status": "unknown",
            "confidence": 0.0,
            "diff_c": 0.0,
            "diff_o": 0.0,
            "people_count": 0,
            "zone_counts": {},
            "reason": str(res.get("reason") or "http_infer_failed"),
            "ref_closed_path": "",
            "ref_open_path": "",
        }
    # Use camera-specific references first for better robustness.
    return _legacy_detect_camera_state_auto_ref(frame, camera_key)


def _camera_weight(camera_key, vision_cfg):
    weights = vision_cfg.get("camera_weights", {}) if isinstance(vision_cfg.get("camera_weights"), dict) else {}
    try:
        value = float(weights.get(camera_key, 1.0))
    except Exception:
        value = 1.0
    value = max(0.0, value)
    if bool(vision_cfg.get("degrade_unready_camera_weight", True)):
        calibration = _calibration_status_payload()
        ready_map = calibration.get("cameras", {}) if isinstance(calibration.get("cameras"), dict) else {}
        ready = bool((ready_map.get(str(camera_key), {}) or {}).get("ready"))
        if not ready:
            factor = float(vision_cfg.get("unready_camera_weight_factor", 0.35) or 0.35)
            value *= max(0.0, min(factor, 1.0))
    return value


def _resolve_disagreement_winner(vote_map, vision_cfg):
    if not isinstance(vote_map, dict) or not vote_map:
        return None
    agg = {
        "open": {"score": 0.0, "max_confidence": 0.0, "count": 0},
        "closed": {"score": 0.0, "max_confidence": 0.0, "count": 0},
    }
    for vote in vote_map.values():
        status = str(vote.get("status") or "").strip().lower()
        if status not in {"open", "closed"}:
            continue
        try:
            score = max(0.0, float(vote.get("score", 0.0) or 0.0))
        except Exception:
            score = 0.0
        try:
            confidence = max(0.0, min(float(vote.get("confidence", 0.0) or 0.0), 1.0))
        except Exception:
            confidence = 0.0
        agg[status]["score"] += score
        agg[status]["count"] += 1
        if confidence > agg[status]["max_confidence"]:
            agg[status]["max_confidence"] = confidence

    open_count = int(agg["open"]["count"])
    closed_count = int(agg["closed"]["count"])
    if open_count <= 0 or closed_count <= 0:
        return None

    winner = "open" if agg["open"]["score"] >= agg["closed"]["score"] else "closed"
    loser = "closed" if winner == "open" else "open"
    winner_score = float(agg[winner]["score"])
    loser_score = float(agg[loser]["score"])
    winner_conf = float(agg[winner]["max_confidence"])
    score_gap = winner_score - loser_score
    score_ratio = winner_score / max(loser_score, 1e-6)

    min_score = float(vision_cfg.get("disagreement_winner_min_score", 0.68) or 0.68)
    min_gap = float(vision_cfg.get("disagreement_winner_min_gap", 0.08) or 0.08)
    min_ratio = float(vision_cfg.get("disagreement_winner_min_ratio", 1.22) or 1.22)
    min_conf = float(vision_cfg.get("disagreement_winner_min_confidence", 0.6) or 0.6)

    if winner_score < min_score or score_gap < min_gap or score_ratio < min_ratio or winner_conf < min_conf:
        return None

    return {
        "status": winner,
        "confidence": winner_conf,
        "winner_score": winner_score,
        "loser_score": loser_score,
        "score_gap": score_gap,
        "score_ratio": score_ratio,
    }


def _fuse_camera_results(results, vision_cfg):
    if not results:
        return {"status": "unknown", "confidence": 0.0, "weighted_open": 0.0, "weighted_closed": 0.0, "camera_votes": {}}

    weighted_open = 0.0
    weighted_closed = 0.0
    vote_map = {}
    for item in results:
        status = item.get("status")
        confidence = max(0.0, min(float(item.get("confidence", 0.0) or 0.0), 1.0))
        camera_key = str(item.get("camera_key") or "")
        weight = _camera_weight(camera_key, vision_cfg)
        score = confidence * weight
        vote_map[camera_key] = {
            "status": status,
            "confidence": round(confidence, 4),
            "weight": round(weight, 3),
            "score": round(score, 4),
            "diff_c": round(float(item.get("diff_c", 0.0) or 0.0), 2),
            "diff_o": round(float(item.get("diff_o", 0.0) or 0.0), 2),
            "reason": str(item.get("reason") or ""),
            "threshold": _get_camera_match_threshold(camera_key),
            "ref_closed_path": str(item.get("ref_closed_path") or ""),
            "ref_open_path": str(item.get("ref_open_path") or ""),
        }
        if status == "open":
            weighted_open += score
        elif status == "closed":
            weighted_closed += score

    margin = abs(weighted_open - weighted_closed)
    score_sum = max(weighted_open + weighted_closed, 1e-6)
    confidence = max(0.0, min(margin / score_sum, 1.0))
    min_conf = float(vision_cfg.get("fusion_min_confidence", 0.55) or 0.55)
    min_margin = float(vision_cfg.get("fusion_margin", 0.15) or 0.15)
    status = "unknown"
    if margin >= min_margin and confidence >= min_conf:
        status = "open" if weighted_open > weighted_closed else "closed"
    disagreement_override = None
    if status == "unknown":
        disagreement_override = _resolve_disagreement_winner(vote_map, vision_cfg)
        if isinstance(disagreement_override, dict):
            status = str(disagreement_override.get("status") or "unknown")
            confidence = max(confidence, float(disagreement_override.get("confidence", 0.0) or 0.0))

    return {
        "status": status,
        "confidence": confidence,
        "weighted_open": weighted_open,
        "weighted_closed": weighted_closed,
        "camera_votes": vote_map,
        "disagreement_override": disagreement_override or {},
    }


def _update_transition_state(stable_state, candidate_state, match_thresh):
    now = time.time()
    with status_lock:
        history = door_status_info.get("score_history")
        if not isinstance(history, list):
            history = []
            door_status_info["score_history"] = history

        prev_score = _status_score(stable_state)
        next_score = _status_score(candidate_state)
        score_delta = next_score - prev_score
        history.append(score_delta * max(float(match_thresh or 0), 1.0))
        if len(history) > 6:
            history.pop(0)

        if stable_state in {"open", "closed"} and candidate_state in {"open", "closed"} and stable_state != candidate_state:
            door_status_info["transition_status"] = "opening" if candidate_state == "open" else "closing"
            door_status_info["last_move_time"] = now
            vision_runtime_info["last_transition_mark_at"] = now
        elif now - float(door_status_info.get("last_move_time", 0.0) or 0.0) > float(_get_door_config().get("stop_threshold", 3.0) or 3.0):
            if stable_state in {"open", "closed"}:
                door_status_info["transition_status"] = None
            else:
                door_status_info["transition_status"] = "stopped_midway"


def _update_runtime_stability(fusion_result, vision_cfg):
    now = time.time()
    base_settle_frames = int(vision_cfg.get("fusion_settle_frames", 3) or 3)
    settle_frames = base_settle_frames
    history_size = int(vision_cfg.get("fusion_history_size", 8) or 8)

    last_fusion = vision_runtime_info.get("last_fusion", {})
    if not isinstance(last_fusion, dict):
        last_fusion = {}
    last_fusion["status"] = fusion_result.get("status")
    last_fusion["confidence"] = round(float(fusion_result.get("confidence", 0.0) or 0.0), 4)
    last_fusion["weighted_open"] = round(float(fusion_result.get("weighted_open", 0.0) or 0.0), 4)
    last_fusion["weighted_closed"] = round(float(fusion_result.get("weighted_closed", 0.0) or 0.0), 4)
    last_fusion["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    vision_runtime_info["last_fusion"] = last_fusion
    vision_runtime_info["last_candidate"] = fusion_result.get("status", "unknown")

    vote_map = fusion_result.get("camera_votes", {})
    if isinstance(vote_map, dict):
        for camera_key, vote in vote_map.items():
            history = vision_runtime_info["per_camera_history"].setdefault(camera_key, [])
            history.append(
                {
                    "status": str(vote.get("status") or "unknown"),
                    "confidence": float(vote.get("confidence", 0.0) or 0.0),
                    "ts": now,
                }
            )
            if len(history) > history_size:
                del history[:-history_size]

    stable_state = str(vision_runtime_info.get("stable_state") or "unknown_calibration")
    candidate_state = str(fusion_result.get("status") or "unknown")
    if candidate_state not in {"open", "closed"}:
        vision_runtime_info["pending_state"] = None
        vision_runtime_info["pending_hits"] = 0
        vision_runtime_info["unknown_hits"] = int(vision_runtime_info.get("unknown_hits", 0) or 0) + 1
        return stable_state

    # Guard low-confidence single-camera results from directly flipping state.
    camera_votes = fusion_result.get("camera_votes", {})
    camera_count = len(camera_votes) if isinstance(camera_votes, dict) else 0
    valid_vote_states = []
    if isinstance(camera_votes, dict):
        for vote in camera_votes.values():
            s = str((vote or {}).get("status") or "").strip().lower()
            if s in {"open", "closed"}:
                valid_vote_states.append(s)
    fusion_conf = float(fusion_result.get("confidence", 0.0) or 0.0)
    if camera_count <= 1:
        min_single_conf = float(vision_cfg.get("single_camera_min_confidence", 0.58) or 0.58)
        if fusion_conf < min_single_conf:
            candidate_state = "unknown"
            vision_runtime_info["last_candidate"] = "unknown"
            fusion_result["status"] = "unknown"
            if stable_state in {"open", "closed"}:
                return stable_state
            vision_runtime_info["pending_state"] = None
            vision_runtime_info["pending_hits"] = 0
            vision_runtime_info["unknown_hits"] = int(vision_runtime_info.get("unknown_hits", 0) or 0) + 1
            return stable_state

    if candidate_state == stable_state:
        vision_runtime_info["pending_state"] = None
        vision_runtime_info["pending_hits"] = 0
        vision_runtime_info["unknown_hits"] = 0
        return stable_state

    # Anti-jitter: direction-sensitive switch guards.
    if stable_state in {"open", "closed"} and candidate_state in {"open", "closed"} and stable_state != candidate_state:
        if bool(vision_cfg.get("require_dual_votes_for_switch", False)):
            candidate_votes = sum(1 for s in valid_vote_states if s == candidate_state)
            multi_vote_available = len(valid_vote_states) >= 2
            has_disagreement_override = bool(fusion_result.get("disagreement_override"))
            if multi_vote_available and candidate_votes < 2 and not has_disagreement_override:
                return stable_state
        cooldown = float(vision_cfg.get("switch_cooldown_sec", 1.2) or 1.2)
        last_change = float(vision_runtime_info.get("last_stable_change_at", 0.0) or 0.0)
        if cooldown > 0 and (now - last_change) < cooldown:
            return stable_state
        required_conf = float(vision_cfg.get("fusion_min_confidence", 0.55) or 0.55)
        if candidate_state == "closed":
            required_conf += float(vision_cfg.get("closed_switch_extra_confidence", 0.12) or 0.12)
            settle_frames = max(
                settle_frames,
                base_settle_frames + int(vision_cfg.get("closed_switch_extra_settle_frames", 1) or 1),
            )
        else:
            required_conf += float(vision_cfg.get("open_switch_extra_confidence", 0.0) or 0.0)
            settle_frames = max(
                settle_frames,
                base_settle_frames + int(vision_cfg.get("open_switch_extra_settle_frames", 0) or 0),
            )
        if fusion_conf < max(0.0, min(required_conf, 1.0)):
            return stable_state

    if vision_runtime_info.get("pending_state") != candidate_state:
        vision_runtime_info["pending_state"] = candidate_state
        vision_runtime_info["pending_hits"] = 1
    else:
        vision_runtime_info["pending_hits"] = int(vision_runtime_info.get("pending_hits", 0) or 0) + 1

    if int(vision_runtime_info.get("pending_hits", 0) or 0) >= settle_frames:
        old_stable = stable_state
        vision_runtime_info["stable_state"] = candidate_state
        vision_runtime_info["pending_state"] = None
        vision_runtime_info["pending_hits"] = 0
        vision_runtime_info["unknown_hits"] = 0
        vision_runtime_info["last_stable_change_at"] = now
        _update_transition_state(old_stable, candidate_state, _get_door_config().get("match_threshold", 1500))
        return candidate_state
    return stable_state


def _update_status_info(merged_state, fusion_result, primary_result, detection_camera, vision_cfg):
    global _LAST_LOGGED_DOOR_STABLE_STATE
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    now_ts = time.time()
    stop_thresh_time = float(_get_door_config().get("stop_threshold", 3.0) or 3.0)
    log_message = ""
    with status_lock:
        previous_status = door_status_info.get("current_status")
        door_status_info["detection_camera"] = detection_camera
        door_status_info["current_status"] = merged_state
        if (
            merged_state in {"open", "closed"}
            and previous_status in {"open", "closed"}
            and merged_state != previous_status
            and _LAST_LOGGED_DOOR_STABLE_STATE != merged_state
        ):
            state_text = "打开" if merged_state == "open" else "关闭"
            log_message = f"[状态变化][门禁] 户外大门识别为{state_text}（视觉/传感器识别）"
            _LAST_LOGGED_DOOR_STABLE_STATE = merged_state
        if merged_state == "unknown_calibration":
            door_status_info["transition_status"] = None
        if merged_state in {"open", "closed"} and door_status_info.get("transition_status") == "stopped_midway":
            door_status_info["transition_status"] = None
        if merged_state in {"open", "closed"} and door_status_info.get("transition_status") in {"opening", "closing"}:
            last_move = float(door_status_info.get("last_move_time", 0.0) or 0.0)
            if (last_move <= 0.0) or ((now_ts - last_move) >= stop_thresh_time):
                # Gate transition text by idle time, avoid lingering "opening/closing" after state is stable.
                door_status_info["transition_status"] = None
        door_status_info["diff_c"] = float(primary_result.get("diff_c", 0.0) or 0.0)
        door_status_info["diff_o"] = float(primary_result.get("diff_o", 0.0) or 0.0)
        door_status_info["confidence"] = round(float(fusion_result.get("confidence", 0.0) or 0.0), 4)
        door_status_info["camera_votes"] = fusion_result.get("camera_votes", {})
        door_status_info["engine"] = "vision_fusion" if vision_cfg.get("enabled") else "legacy_fusion"
        # Suppress misleading transition text when confidence is low.
        if (
            door_status_info.get("transition_status") == "closing"
            and float(door_status_info.get("confidence", 0.0) or 0.0)
            < float(vision_cfg.get("single_camera_min_confidence", 0.58) or 0.58)
        ):
            door_status_info["transition_status"] = None
        door_status_info["updated_at"] = now_iso
    if log_message:
        add_log(-1, log_message)


def _apply_analytics_to_status(results, vision_cfg):
    if not bool(vision_cfg.get("people_count_enabled", False)):
        return
    people_count = 0
    zone_counts = {}
    for item in results:
        try:
            people_count = max(people_count, int(item.get("people_count", 0) or 0))
        except Exception:
            pass
        zones = item.get("zone_counts")
        if isinstance(zones, dict):
            for zone_name, zone_value in zones.items():
                try:
                    value = int(zone_value or 0)
                except Exception:
                    continue
                zone_counts[str(zone_name)] = max(zone_counts.get(str(zone_name), 0), value)
    with status_lock:
        door_status_info["people_count"] = people_count
        if bool(vision_cfg.get("zone_count_enabled", False)):
            door_status_info["zone_counts"] = zone_counts


def _flatten_zone_counts(zone_counts):
    flat = {}
    if not isinstance(zone_counts, dict):
        return flat
    for zone_name, zone_value in zone_counts.items():
        key = str(zone_name or "").strip()
        if not key:
            continue
        try:
            value = int(zone_value or 0)
        except Exception:
            value = 0
        flat[f"zone_{key}_count"] = value
    return flat


def _apply_vision_automation_fields():
    with status_lock:
        status_value = str(door_status_info.get("transition_status") or door_status_info.get("current_status") or "unknown")
        confidence = float(door_status_info.get("confidence", 0.0) or 0.0)
        people_count = int(door_status_info.get("people_count", 0) or 0)
        zone_counts = dict(door_status_info.get("zone_counts", {}) or {})
        door_status_info["automation_fields"] = {
            "door_status": status_value,
            "door_confidence": confidence,
            "people_count": people_count,
            **_flatten_zone_counts(zone_counts),
        }


def _legacy_update_single_camera_status():
    camera_key = _preferred_detection_camera()
    frame = _capture_frame(camera_key, allow_fallback=False)
    if frame is None:
        with status_lock:
            door_status_info["detection_camera"] = camera_key
            door_status_info["engine"] = "legacy"
            door_status_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return

    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    rect = _calc_region_rect(gray.shape, camera_key)
    if rect is None:
        return
    x1, y1, x2, y2 = rect
    door_region = gray[y1:y2, x1:x2]

    ref_closed, ref_closed_path = _load_reference_for_camera("closed", camera_key)
    ref_open, ref_open_path = _load_reference_for_camera("open", camera_key)
    if ref_closed is None or ref_open is None:
        with status_lock:
            door_status_info["current_status"] = "unknown_calibration"
            door_status_info["detection_camera"] = camera_key
            door_status_info["engine"] = "legacy"
            door_status_info["camera_votes"] = {
                camera_key: {
                    "status": "unknown",
                    "confidence": 0.0,
                    "score": 0.0,
                    "reason": "missing_reference",
                    "ref_closed_path": ref_closed_path,
                    "ref_open_path": ref_open_path,
                }
            }
            door_status_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        vision_runtime_info["stable_state"] = "unknown_calibration"
        return

    vh, vw = gray.shape
    crop_closed = cv2.resize(ref_closed, (vw, vh))[y1:y2, x1:x2]
    crop_open = cv2.resize(ref_open, (vw, vh))[y1:y2, x1:x2]
    diff_c = float(_compute_diff(door_region, crop_closed))
    diff_o = float(_compute_diff(door_region, crop_open))
    match_thresh = _get_camera_match_threshold(camera_key)
    stop_thresh_time = float(_get_door_config().get("stop_threshold", 3.0))
    now = time.time()
    confidence = max(0.0, min(abs(diff_c - diff_o) / max(diff_c + diff_o, 1.0), 1.0))

    with status_lock:
        door_status_info["diff_c"] = diff_c
        door_status_info["diff_o"] = diff_o
        door_status_info["detection_camera"] = camera_key
        door_status_info["engine"] = "legacy"
        door_status_info["confidence"] = round(confidence, 4)
        door_status_info["camera_votes"] = {
            camera_key: {
                "status": "closed" if diff_c <= diff_o else "open",
                "confidence": round(confidence, 4),
                "weight": 1.0,
                "score": round(confidence, 4),
                "diff_c": round(diff_c, 2),
                "diff_o": round(diff_o, 2),
                "reason": "",
                "threshold": match_thresh,
                "ref_closed_path": ref_closed_path,
                "ref_open_path": ref_open_path,
            }
        }
        door_status_info["people_count"] = 0
        door_status_info["zone_counts"] = {}
        door_status_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if diff_c < match_thresh and diff_o > match_thresh:
            door_status_info["current_status"] = "closed"
            door_status_info["transition_status"] = None
        elif diff_o < match_thresh and diff_c > match_thresh:
            door_status_info["current_status"] = "open"
            door_status_info["transition_status"] = None
        else:
            history = door_status_info["score_history"]
            history.append(diff_c - diff_o)
            if len(history) > 6:
                history.pop(0)

            is_moving = False
            if len(history) >= 4:
                slope = history[-1] - history[0]
                if slope > match_thresh * 0.15:
                    door_status_info["transition_status"] = "opening"
                    door_status_info["last_move_time"] = now
                    is_moving = True
                elif slope < -match_thresh * 0.15:
                    door_status_info["transition_status"] = "closing"
                    door_status_info["last_move_time"] = now
                    is_moving = True

            if not is_moving and (now - float(door_status_info.get("last_move_time", 0.0) or 0.0) > stop_thresh_time):
                door_status_info["transition_status"] = "stopped_midway"

    current_state = door_status_info.get("current_status")
    if current_state in {"open", "closed", "unknown_calibration"}:
        vision_runtime_info["stable_state"] = current_state
    _apply_vision_automation_fields()


def _send_tcp_command(command):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(
            (
                _get_door_config().get("ip", "192.168.50.51"),
                int(_get_door_config().get("port", 50000)),
            )
        )
        sock.sendall(command)
        sock.close()
        return True, "指令发送成功"
    except Exception as exc:
        return False, f"发送失败: {exc}"


def _build_overlay_frame(frame, camera_key=None):
    reg_pct = _get_region_pct(camera_key)
    vh, vw = frame.shape[:2]
    x1 = int(reg_pct["p_x1"] * vw)
    y1 = int(reg_pct["p_y1"] * vh)
    x2 = int(reg_pct["p_x2"] * vw)
    y2 = int(reg_pct["p_y2"] * vh)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 2)
    return overlay


def _gen_frames(camera_key):
    preview_cfg = _get_preview_config()
    frame_interval = 1.0 / max(float(preview_cfg.get("fps", 12.0) or 12.0), 0.1)
    jpeg_quality = int(preview_cfg.get("jpeg_quality", 68) or 68)
    max_width = int(preview_cfg.get("max_width", 1280) or 1280)
    while True:
        frame = _capture_latest_preview_frame(camera_key)
        if frame is None:
            frame = _offline_placeholder_frame(camera_key)
        elif frame.shape[1] > max_width:
            ratio = max_width / max(float(frame.shape[1]), 1.0)
            frame = cv2.resize(frame, (max_width, max(1, int(frame.shape[0] * ratio))), interpolation=cv2.INTER_AREA)
        overlay = _build_overlay_frame(frame, camera_key)
        ret, buffer = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        if ret:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        time.sleep(frame_interval)


def update_door_status():
    while True:
        vision_cfg = _get_vision_config()
        interval_sec = float(vision_cfg.get("poll_interval_sec", 0.5) or 0.5)
        time.sleep(interval_sec)

        if not bool(vision_cfg.get("enabled", False)):
            _legacy_update_single_camera_status()
            continue

        provider = str(vision_cfg.get("provider") or "legacy").strip().lower()
        use_http_provider = bool(vision_cfg.get("enabled")) and provider in {"http", "remote_http"}
        ref_closed = None
        ref_open = None
        if not use_http_provider:
            ref_closed, ref_open = _load_reference_images()
        camera_cfgs = _get_camera_configs()
        available_camera_keys = [item.get("key") for item in camera_cfgs if str(item.get("key") or "").strip()]
        preferred_camera = _preferred_detection_camera()
        target_keys = [preferred_camera]
        if bool(vision_cfg.get("fusion_enabled", True)):
            target_keys = [key for key in available_camera_keys if key]
        if not target_keys:
            target_keys = [preferred_camera]

        if not use_http_provider and (ref_closed is None or ref_open is None):
            with status_lock:
                door_status_info["current_status"] = "unknown_calibration"
                door_status_info["detection_camera"] = preferred_camera
                door_status_info["engine"] = "legacy"
                door_status_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            vision_runtime_info["stable_state"] = "unknown_calibration"
            continue

        per_camera_results = []
        for camera_key in target_keys:
            frame = _capture_frame(camera_key, allow_fallback=False)
            if frame is None and camera_key == preferred_camera and bool(vision_cfg.get("allow_shared_reference", False)):
                frame = _capture_frame(camera_key, allow_fallback=True)
            result = _detect_camera_state(frame, camera_key, ref_closed, ref_open, vision_cfg)
            per_camera_results.append(result)

        if not per_camera_results:
            with status_lock:
                door_status_info["detection_camera"] = preferred_camera
                door_status_info["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            continue

        primary_result = next((item for item in per_camera_results if item.get("camera_key") == preferred_camera), per_camera_results[0])
        if bool(vision_cfg.get("fusion_enabled", True)) and len(per_camera_results) > 1:
            fusion_result = _fuse_camera_results(per_camera_results, vision_cfg)
        else:
            fusion_result = {
                "status": str(primary_result.get("status") or "unknown"),
                "confidence": float(primary_result.get("confidence", 0.0) or 0.0),
                "weighted_open": float(primary_result.get("confidence", 0.0) or 0.0) if primary_result.get("status") == "open" else 0.0,
                "weighted_closed": float(primary_result.get("confidence", 0.0) or 0.0) if primary_result.get("status") == "closed" else 0.0,
                "camera_votes": {
                    str(primary_result.get("camera_key") or preferred_camera): {
                        "status": str(primary_result.get("status") or "unknown"),
                        "confidence": round(float(primary_result.get("confidence", 0.0) or 0.0), 4),
                        "weight": 1.0,
                        "score": round(float(primary_result.get("confidence", 0.0) or 0.0), 4),
                        "diff_c": round(float(primary_result.get("diff_c", 0.0) or 0.0), 2),
                        "diff_o": round(float(primary_result.get("diff_o", 0.0) or 0.0), 2),
                        "reason": str(primary_result.get("reason") or ""),
                    }
                },
            }

        if str(fusion_result.get("status") or "unknown") in {"open", "closed"}:
            merged_state = _update_runtime_stability(fusion_result, vision_cfg)
        else:
            merged_state = str(vision_runtime_info.get("stable_state") or "unknown")
            if merged_state not in {"open", "closed"}:
                merged_state = "unknown"
            if merged_state == "unknown":
                with status_lock:
                    if (time.time() - float(door_status_info.get("last_move_time", 0.0) or 0.0)) > float(_get_door_config().get("stop_threshold", 3.0) or 3.0):
                        door_status_info["transition_status"] = "stopped_midway"

        if (
            str(fusion_result.get("status") or "unknown") == "unknown"
            and str(primary_result.get("status") or "unknown") in {"open", "closed"}
        ):
            camera_votes = fusion_result.get("camera_votes", {}) if isinstance(fusion_result.get("camera_votes"), dict) else {}
            valid_vote_states = []
            for vote in camera_votes.values():
                vote_state = str((vote or {}).get("status") or "").strip().lower()
                if vote_state in {"open", "closed"}:
                    valid_vote_states.append(vote_state)
            # Only allow preferred-camera fallback when no real multi-camera disagreement exists.
            allow_primary_fallback = len(valid_vote_states) <= 1 or len(set(valid_vote_states)) <= 1
            if allow_primary_fallback:
                primary_conf = float(primary_result.get("confidence", 0.0) or 0.0)
                min_single_conf = float(vision_cfg.get("single_camera_min_confidence", 0.58) or 0.58)
                if primary_conf >= min_single_conf:
                    preferred_state = str(primary_result.get("status"))
                    merged_state = preferred_state
                    vision_runtime_info["stable_state"] = preferred_state
                    vision_runtime_info["pending_state"] = None
                    vision_runtime_info["pending_hits"] = 0
                    vision_runtime_info["unknown_hits"] = 0
                    fusion_result["status"] = preferred_state
                    fusion_result["confidence"] = max(
                        float(fusion_result.get("confidence", 0.0) or 0.0),
                        primary_conf,
                    )

        _update_status_info(merged_state, fusion_result, primary_result, preferred_camera, vision_cfg)
        _apply_analytics_to_status(per_camera_results, vision_cfg)
        _apply_vision_automation_fields()
        _append_infer_trace(
            {
                "merged_state": merged_state,
                "fusion_status": str(fusion_result.get("status") or "unknown"),
                "fusion_confidence": round(float(fusion_result.get("confidence", 0.0) or 0.0), 4),
                "detection_camera": preferred_camera,
                "camera_votes": fusion_result.get("camera_votes", {}),
            },
            vision_cfg,
        )


def _camera_payload(camera_key, include_rtsp=False):
    with camera_state_lock:
        state = dict(camera_states.get(camera_key, _default_camera_state(camera_key)))
    payload = {
        "key": camera_key,
        "name": state.get("name") or camera_key,
        "enabled": bool(state.get("enabled", True)),
        "configured": bool(state.get("configured")),
        "online": bool(state.get("online")),
        "transport": state.get("transport") or "",
        "transport_attempts": list(state.get("transport_attempts") or []),
        "last_error": state.get("last_error") or "",
        "last_error_text": _translate_camera_error(state.get("last_error") or ""),
        "last_ok_at": state.get("last_ok_at"),
        "last_attempt_at": state.get("last_attempt_at"),
        "updated_at": state.get("updated_at"),
        "frame_width": int(state.get("frame_width") or 0),
        "frame_height": int(state.get("frame_height") or 0),
        "host": state.get("host") or "",
        "note": state.get("note") or "",
    }
    if include_rtsp:
        payload["rtsp_url"] = state.get("rtsp_url") or ""
    return payload


def _vision_runtime_payload():
    payload = {
        "stable_state": str(vision_runtime_info.get("stable_state") or "unknown"),
        "pending_state": vision_runtime_info.get("pending_state"),
        "pending_hits": int(vision_runtime_info.get("pending_hits", 0) or 0),
        "unknown_hits": int(vision_runtime_info.get("unknown_hits", 0) or 0),
        "last_candidate": str(vision_runtime_info.get("last_candidate") or "unknown"),
        "last_stable_change_at": float(vision_runtime_info.get("last_stable_change_at", 0.0) or 0.0),
        "last_transition_mark_at": float(vision_runtime_info.get("last_transition_mark_at", 0.0) or 0.0),
    }
    fusion = vision_runtime_info.get("last_fusion", {})
    payload["last_fusion"] = dict(fusion) if isinstance(fusion, dict) else {}
    history = vision_runtime_info.get("per_camera_history", {})
    if isinstance(history, dict):
        payload["per_camera_history"] = {
            str(key): list(values or [])[-8:]
            for key, values in history.items()
            if str(key).strip()
        }
    else:
        payload["per_camera_history"] = {}
    return payload


def _vision_model_path():
    vision_cfg = _get_vision_config()
    url = str(vision_cfg.get("http_url") or "").strip()
    parsed = urlsplit(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 18080
    return f"http://{host}:{port}"


def _door_model_path():
    # Keep consistent with vision-door.service default.
    return "/srv/smart-center/models/door_state_cls.pt"


def _person_model_path():
    return "/srv/smart-center/models/yolo11n.pt"


def _vision_service_health():
    base = _vision_model_path()
    req = urllib_request.Request(url=f"{base}/health", method="GET")
    try:
        with urllib_request.urlopen(req, timeout=1.5) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        payload = json.loads(text or "{}")
        if isinstance(payload, dict):
            payload["reachable"] = True
            return payload
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}
    return {"reachable": False, "error": "invalid_response"}


def _notify_vision_reload():
    base = _vision_model_path()
    req = urllib_request.Request(url=f"{base}/reload_models", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=2.0) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        return json.loads(text or "{}")
    except Exception as exc:
        return {"status": "error", "msg": f"reload_failed:{exc}"}


def _model_rebuild_snapshot():
    snapshot = None
    with model_rebuild_lock:
        snapshot = dict(model_rebuild_state)
    try:
        if os.path.exists(MODEL_REBUILD_STATUS_FILE):
            with open(MODEL_REBUILD_STATUS_FILE, "r", encoding="utf-8") as f:
                persisted = json.load(f)
            if isinstance(persisted, dict):
                snapshot.update(persisted)
    except Exception:
        pass
    return snapshot


def _recordings_dir() -> Path:
    p = Path(DATA_DIR) / "runtime" / "door_recordings"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _recording_snapshot():
    with record_lock:
        payload = dict(record_state)
        payload["files"] = dict(record_state.get("files") or {})
        payload["pids"] = dict(record_state.get("pids") or {})
    return payload


def _start_recording_session(duration_sec=180):
    cams = _get_camera_configs()
    duration_sec = max(10, min(int(duration_sec or 180), 3600))
    ts = time.strftime("%Y%m%d_%H%M%S")
    session_id = f"door_{ts}"
    out_dir = _recordings_dir() / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    proc_map = {}
    file_map = {}
    for cam in cams:
        key = str(cam.get("key") or "").strip()
        rtsp = str(cam.get("rtsp_url") or "").strip()
        enabled = bool(cam.get("enabled", True))
        if not key or not rtsp or not enabled:
            continue
        out_file = out_dir / f"{key}.mp4"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            rtsp,
            "-an",
            "-c:v",
            "copy",
            "-t",
            str(duration_sec),
            "-y",
            str(out_file),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc_map[key] = proc
        file_map[key] = str(out_file)
    if not proc_map:
        return False, {"status": "error", "msg": "no_camera_available_for_recording"}
    with record_lock:
        record_state["running"] = True
        record_state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record_state["session_id"] = session_id
        record_state["files"] = file_map
        record_state["pids"] = {k: int(v.pid) for k, v in proc_map.items()}

    def _wait_and_close():
        for _, p in proc_map.items():
            try:
                p.wait(timeout=duration_sec + 20)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        with record_lock:
            record_state["running"] = False
            record_state["pids"] = {}

    threading.Thread(target=_wait_and_close, name=f"door-record-{session_id}", daemon=True).start()
    return True, {"status": "success", "session_id": session_id, "files": file_map, "duration_sec": duration_sec}


def _stop_recording_session():
    with record_lock:
        pid_map = dict(record_state.get("pids") or {})
    for _, pid in pid_map.items():
        try:
            os.kill(int(pid), 15)
        except Exception:
            pass
    time.sleep(0.2)
    with record_lock:
        record_state["running"] = False
        record_state["pids"] = {}
    return {"status": "success", "recording": _recording_snapshot()}


def _set_model_rebuild_state(**kwargs):
    with model_rebuild_lock:
        for key, value in kwargs.items():
            model_rebuild_state[key] = value
        data = dict(model_rebuild_state)
    try:
        _safe_write_json(MODEL_REBUILD_STATUS_FILE, data)
    except Exception:
        pass


def _append_infer_trace(payload, vision_cfg):
    if not bool(vision_cfg.get("trace_enabled", True)):
        return
    trace_path = Path(INFER_TRACE_FILE)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(float(vision_cfg.get("trace_max_mb", 20) or 20) * 1024 * 1024)
    try:
        if trace_path.exists() and trace_path.stat().st_size > max_bytes:
            rotated = trace_path.with_suffix(".jsonl.bak")
            try:
                if rotated.exists():
                    rotated.unlink()
            except Exception:
                pass
            os.replace(str(trace_path), str(rotated))
    except Exception:
        pass
    row = dict(payload or {})
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run_door_model_rebuild_async():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rebuild_door_model.py"))
    config_path = os.environ.get("SMART_CENTER_CONFIG_FILE", "")
    if not config_path:
        from paths import CONFIG_FILE as _CFG_PATH

        config_path = str(_CFG_PATH)
    model_path = _door_model_path()
    status_path = MODEL_REBUILD_STATUS_FILE
    cmd = [
        sys.executable,
        script_path,
        "--config",
        config_path,
        "--output",
        model_path,
        "--status-file",
        status_path,
    ]
    _set_model_rebuild_state(
        running=True,
        last_started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        last_status="running",
        last_message="模型重建中",
        last_output="",
        last_exit_code=None,
    )
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as exc:
        _set_model_rebuild_state(
            running=False,
            last_finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            last_status="error",
            last_message=f"模型重建启动失败: {exc}",
            last_output="",
            last_exit_code=500,
            last_model_path=model_path,
        )
        return False


def _calibration_status_payload():
    payload = {"preferred": _preferred_detection_camera(), "cameras": {}, "legacy": {}}
    payload["legacy"] = {
        "closed": {"path": _reference_path("closed", ""), "exists": os.path.exists(_reference_path("closed", ""))},
        "open": {"path": _reference_path("open", ""), "exists": os.path.exists(_reference_path("open", ""))},
    }
    for item in _get_camera_configs():
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        closed_path = _reference_path("closed", key)
        open_path = _reference_path("open", key)
        payload["cameras"][key] = {
            "closed": {"path": closed_path, "exists": os.path.exists(closed_path)},
            "open": {"path": open_path, "exists": os.path.exists(open_path)},
            "match_threshold": _get_camera_match_threshold(key),
            "ready": bool(os.path.exists(closed_path) and os.path.exists(open_path)),
        }
    return payload


@bp.route("/video_feed")
@require_permission("door.view")
def video_feed():
    return Response(_gen_frames(_preferred_detection_camera()), mimetype="multipart/x-mixed-replace; boundary=frame")


@bp.route("/video_feed/<camera_key>")
@require_permission("door.view")
def video_feed_by_key(camera_key):
    camera_key = str(camera_key or "").strip() or _preferred_detection_camera()
    return Response(_gen_frames(camera_key), mimetype="multipart/x-mixed-replace; boundary=frame")


@bp.route("/api/door/cameras")
@require_permission("door.view")
def api_door_cameras():
    _sync_camera_state_defaults()
    keys = [item["key"] for item in _get_camera_configs()]
    return jsonify(
        {
            "status": "success",
            "preferred_detection_camera": _preferred_detection_camera(),
            "view_slots": _get_view_slots(),
            "regions": {key: _get_region_pct(key) for key in keys},
            "cameras": [_camera_payload(key) for key in keys],
            "vision_config": _get_vision_config(),
            "vision_runtime": _vision_runtime_payload(),
        }
    )


@bp.route("/api/door/vision_status")
@require_permission("door.view")
def api_door_vision_status():
    detection_camera = _preferred_detection_camera()
    with status_lock:
        current_snapshot = dict(door_status_info)
    return jsonify(
        {
            "status": "success",
            "door_status": current_snapshot.get("transition_status") or current_snapshot.get("current_status"),
            "detection_camera": current_snapshot.get("detection_camera") or detection_camera,
            "engine": current_snapshot.get("engine") or "legacy",
            "confidence": current_snapshot.get("confidence", 0.0),
            "diff_c": current_snapshot.get("diff_c", 0.0),
            "diff_o": current_snapshot.get("diff_o", 0.0),
            "camera_votes": current_snapshot.get("camera_votes", {}),
            "people_count": current_snapshot.get("people_count", 0),
            "zone_counts": current_snapshot.get("zone_counts", {}),
            "updated_at": current_snapshot.get("updated_at"),
            "vision_config": _get_vision_config(),
            "vision_runtime": _vision_runtime_payload(),
            "vision_service_health": _vision_service_health(),
            "calibration": _calibration_status_payload(),
            "automation_fields": current_snapshot.get("automation_fields", {}),
            "model": {
                "door_model_path": _door_model_path(),
                "door_model_exists": os.path.exists(_door_model_path()),
                "person_model_path": _person_model_path(),
                "person_model_exists": os.path.exists(_person_model_path()),
                "rebuild": _model_rebuild_snapshot(),
            },
        }
    )


@bp.route("/update_door_region", methods=["POST"])
@require_permission("door.control")
def update_door_region():
    data = request.get_json(silent=True) or {}
    CONFIG.setdefault("door_config", {})
    camera_key = str(data.get("camera_key") or _preferred_detection_camera()).strip() or _preferred_detection_camera()
    region_payload = {key: data[key] for key in ("p_x1", "p_y1", "p_x2", "p_y2")}
    regions = CONFIG["door_config"].get("regions", {}) if isinstance(CONFIG["door_config"].get("regions"), dict) else {}
    regions[camera_key] = region_payload
    CONFIG["door_config"]["regions"] = regions
    if camera_key == _preferred_detection_camera():
        CONFIG["door_config"]["region_pct"] = dict(region_payload)
    save_config(CONFIG)
    saved_region = _get_region_pct(camera_key)
    add_log(-1, f"[门禁] 成功更新 {camera_key} 检测区域并已保存")
    log_audit_event("door.region.update", target="door_config", detail={"camera_key": camera_key, "region": saved_region})
    return jsonify({"status": "success", "msg": "检测区域已更新", "camera_key": camera_key, "region": saved_region})


@bp.route("/api/door/vision_zones", methods=["POST"])
@require_permission("door.control")
def api_update_vision_zones():
    data = request.get_json(silent=True) or {}
    camera_key = str(data.get("camera_key") or _preferred_detection_camera()).strip() or _preferred_detection_camera()
    zones_payload = data.get("zones", {})
    if not isinstance(zones_payload, dict):
        return jsonify({"status": "error", "msg": "zones 参数必须是对象"}), 400

    normalized_zone_map = {}
    for zone_name, points in zones_payload.items():
        zone_key = str(zone_name or "").strip()
        if not zone_key or not isinstance(points, list):
            continue
        clean_points = []
        for pt in points:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                continue
            try:
                px = max(0.0, min(float(pt[0]), 1.0))
                py = max(0.0, min(float(pt[1]), 1.0))
            except Exception:
                continue
            clean_points.append([px, py])
        if len(clean_points) >= 3:
            normalized_zone_map[zone_key] = clean_points

    CONFIG.setdefault("door_config", {})
    vision_cfg = CONFIG["door_config"].get("vision", {}) if isinstance(CONFIG["door_config"].get("vision"), dict) else {}
    zones_cfg = vision_cfg.get("zones", {}) if isinstance(vision_cfg.get("zones"), dict) else {}
    zones_cfg[camera_key] = normalized_zone_map
    vision_cfg["zones"] = zones_cfg
    CONFIG["door_config"]["vision"] = vision_cfg
    save_config(CONFIG)

    log_audit_event(
        "door.vision_zones.update",
        target="door_config",
        detail={"camera_key": camera_key, "zone_count": len(normalized_zone_map)},
    )
    add_log(-1, f"[门禁] 已更新视觉区域配置: {camera_key} ({len(normalized_zone_map)} 个区域)")
    return jsonify(
        {
            "status": "success",
            "camera_key": camera_key,
            "zones": normalized_zone_map,
            "vision_config": _get_vision_config(),
        }
    )


@bp.route("/api/door/automation_templates")
@require_permission("door.view")
def api_door_automation_templates():
    detection_camera = _preferred_detection_camera()
    with status_lock:
        current_snapshot = dict(door_status_info)
    zones = current_snapshot.get("zone_counts", {})
    if not isinstance(zones, dict):
        zones = {}

    templates = [
        {
            "name": "门已打开且高置信度",
            "condition": {
                "source_type": "vision",
                "device_id": "door",
                "prop": "door_status",
                "op": "==",
                "value": "open",
                "debounce_sec": 1.0,
                "consecutive_hits": 2,
            },
            "extra_condition": {
                "source_type": "vision",
                "device_id": "door",
                "prop": "door_confidence",
                "op": ">=",
                "value": 0.65,
                "debounce_sec": 0.5,
                "consecutive_hits": 2,
            },
        },
        {
            "name": "门已关闭且高置信度",
            "condition": {
                "source_type": "vision",
                "device_id": "door",
                "prop": "door_status",
                "op": "==",
                "value": "closed",
                "debounce_sec": 1.0,
                "consecutive_hits": 2,
            },
            "extra_condition": {
                "source_type": "vision",
                "device_id": "door",
                "prop": "door_confidence",
                "op": ">=",
                "value": 0.65,
                "debounce_sec": 0.5,
                "consecutive_hits": 2,
            },
        },
        {
            "name": "有人经过门区",
            "condition": {
                "source_type": "vision",
                "device_id": "door",
                "prop": "people_count",
                "op": ">=",
                "value": 1,
                "debounce_sec": 0.5,
                "consecutive_hits": 2,
            },
        },
    ]
    for zone_name in sorted(zones.keys()):
        zone_key = str(zone_name or "").strip()
        if not zone_key:
            continue
        templates.append(
            {
                "name": f"区域[{zone_key}]有人",
                "condition": {
                    "source_type": "vision",
                    "device_id": "door",
                    "prop": f"zone_{zone_key}_count",
                    "op": ">=",
                    "value": 1,
                    "debounce_sec": 0.5,
                    "consecutive_hits": 2,
                },
            }
        )

    return jsonify(
        {
            "status": "success",
            "detection_camera": detection_camera,
            "engine": current_snapshot.get("engine") or "legacy",
            "templates": templates,
        }
    )


@bp.route("/api/door/model_status")
@require_permission("door.view")
def api_door_model_status():
    return jsonify(
        {
            "status": "success",
            "door_model_path": _door_model_path(),
            "door_model_exists": os.path.exists(_door_model_path()),
            "person_model_path": _person_model_path(),
            "person_model_exists": os.path.exists(_person_model_path()),
            "vision_service_health": _vision_service_health(),
            "rebuild": _model_rebuild_snapshot(),
            "recording": _recording_snapshot(),
        }
    )


@bp.route("/api/door/model_rebuild", methods=["POST"])
@require_permission("door.control")
def api_door_model_rebuild():
    snap = _model_rebuild_snapshot()
    if snap.get("running"):
        return jsonify({"status": "error", "msg": "模型重建正在进行中"}), 409
    try:
        proc = subprocess.run(["ps", "-ef"], capture_output=True, text=True, timeout=2.0)
        for line in (proc.stdout or "").splitlines():
            if "rebuild_door_model.py" in line and "python" in line:
                return jsonify({"status": "error", "msg": "已有模型重建进程在运行中"}), 409
    except Exception:
        pass

    started = _run_door_model_rebuild_async()
    if not started:
        return jsonify({"status": "error", "msg": "模型重建任务启动失败"}), 500
    log_audit_event("door.model.rebuild", target="door_model", detail={"message": "triggered"})
    add_log(-1, "[门禁] 已触发开关门专用模型重建任务")
    return jsonify({"status": "success", "msg": "模型重建任务已启动"})


@bp.route("/api/door/recording/start", methods=["POST"])
@require_permission("door.control")
def api_door_recording_start():
    data = request.get_json(silent=True) or {}
    duration_sec = data.get("duration_sec", 180)
    snap = _recording_snapshot()
    if snap.get("running"):
        return jsonify({"status": "error", "msg": "recording_already_running", "recording": snap}), 409
    ok, payload = _start_recording_session(duration_sec=duration_sec)
    if not ok:
        return jsonify(payload), 400
    add_log(-1, f"[门禁] 已启动识别过程录制，会话 {payload.get('session_id')}，时长 {payload.get('duration_sec')} 秒")
    log_audit_event("door.recording.start", target="door_recording", detail=payload)
    return jsonify(payload)


@bp.route("/api/door/recording/stop", methods=["POST"])
@require_permission("door.control")
def api_door_recording_stop():
    payload = _stop_recording_session()
    add_log(-1, "[门禁] 已停止识别过程录制")
    log_audit_event("door.recording.stop", target="door_recording", detail=payload)
    return jsonify(payload)


@bp.route("/api/door/recording/status")
@require_permission("door.view")
def api_door_recording_status():
    return jsonify({"status": "success", "recording": _recording_snapshot()})


@bp.route("/api/door/trace/status")
@require_permission("door.view")
def api_door_trace_status():
    p = Path(INFER_TRACE_FILE)
    size = p.stat().st_size if p.exists() else 0
    return jsonify({"status": "success", "path": str(p), "exists": p.exists(), "size_bytes": int(size)})


@bp.route("/get_door_status")
@require_permission("door.view")
def get_door_status():
    detection_camera = _preferred_detection_camera()
    with status_lock:
        current_snapshot = dict(door_status_info)
    if current_snapshot["current_status"] == "unknown_calibration":
        return jsonify(
            {
                "status": "success",
                "door_status": "unknown",
                "msg": "等待完成标定向导",
                "diff": "请先完成下方标定向导",
                "detection_camera": detection_camera,
                "view_slots": _get_view_slots(),
                "regions": {item["key"]: _get_region_pct(item["key"]) for item in _get_camera_configs()},
                "camera_status": _camera_payload(detection_camera),
                "cameras": [_camera_payload(item["key"]) for item in _get_camera_configs()],
                "engine": current_snapshot.get("engine") or "legacy",
                "confidence": current_snapshot.get("confidence", 0.0),
                "camera_votes": current_snapshot.get("camera_votes", {}),
                "people_count": current_snapshot.get("people_count", 0),
                "zone_counts": current_snapshot.get("zone_counts", {}),
                "vision_runtime": _vision_runtime_payload(),
                "calibration": _calibration_status_payload(),
                "automation_fields": current_snapshot.get("automation_fields", {}),
            }
        )

    show = current_snapshot["transition_status"] or current_snapshot["current_status"]
    text_map = {
        "opening": "正在开门中",
        "closing": "正在关门中",
        "stopped_midway": "门体静止中",
        "closed": "门已完全关闭",
        "open": "门已完全开启",
    }
    return jsonify(
        {
            "status": "success",
            "door_status": show,
            "msg": text_map.get(show, "状态未知"),
            "diff": f"关门差异:{current_snapshot['diff_c']} | 开门差异:{current_snapshot['diff_o']}",
            "detection_camera": current_snapshot.get("detection_camera") or detection_camera,
            "view_slots": _get_view_slots(),
            "regions": {item["key"]: _get_region_pct(item["key"]) for item in _get_camera_configs()},
            "camera_status": _camera_payload(detection_camera),
            "cameras": [_camera_payload(item["key"]) for item in _get_camera_configs()],
            "engine": current_snapshot.get("engine") or "legacy",
            "confidence": current_snapshot.get("confidence", 0.0),
            "camera_votes": current_snapshot.get("camera_votes", {}),
            "people_count": current_snapshot.get("people_count", 0),
            "zone_counts": current_snapshot.get("zone_counts", {}),
            "vision_runtime": _vision_runtime_payload(),
            "calibration": _calibration_status_payload(),
            "automation_fields": current_snapshot.get("automation_fields", {}),
        }
    )


@bp.route("/api/ai_wizard/capture/<state>", methods=["POST"])
@require_permission("door.control")
def wizard_capture(state):
    if state not in ["closed", "open"]:
        return jsonify({"status": "error", "msg": "状态参数无效"})

    data = request.get_json(silent=True) or {}
    camera_key = str(data.get("camera_key") or _preferred_detection_camera()).strip() or _preferred_detection_camera()
    frame = _capture_frame(camera_key)
    if frame is None:
        return jsonify({"status": "error", "msg": "未获取到当前画面"})

    blurred = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    path_specific = _reference_write_path(state, camera_key)
    path_legacy = _reference_write_path(state, "")
    try:
        _safe_write_gray_image(path_specific, blurred)
        if camera_key == _preferred_detection_camera():
            _safe_write_gray_image(path_legacy, blurred)
    except Exception as exc:
        add_log(-1, f"[闂ㄧ] 鎷嶆憚淇濆瓨澶辫触 ({camera_key}/{state}): {exc}")
        log_audit_event(
            "door.calibration.capture",
            target=state,
            detail={"state": state, "camera_key": camera_key, "path": path_specific, "error": str(exc)},
            status="error",
        )
        return jsonify(
            {
                "status": "error",
                "msg": "鎷嶆憚淇濆瓨澶辫触锛岃绋嶅悗閲嶈瘯",
                "camera_key": camera_key,
                "path": path_specific,
                "legacy_path": path_legacy if camera_key == _preferred_detection_camera() else "",
                "error": str(exc),
            }
        )

    name = "【绝对关门】" if state == "closed" else "【绝对开门】"
    add_log(-1, f"[门禁] 已成功拍摄 {name} 基准画面 ({camera_key})")
    log_audit_event(
        "door.calibration.capture",
        target=state,
        detail={"state": state, "camera_key": camera_key, "path": path_specific},
    )
    return jsonify(
        {
            "status": "success",
            "msg": f"已保存 {name} 参考图",
            "camera_key": camera_key,
            "path": path_specific,
            "legacy_path": path_legacy if camera_key == _preferred_detection_camera() else "",
        }
    )


@bp.route("/api/ai_wizard/apply_model", methods=["POST"])
@require_permission("door.control")
def wizard_apply_model():
    data = request.get_json(silent=True) or {}
    camera_key = str(data.get("camera_key") or _preferred_detection_camera()).strip() or _preferred_detection_camera()
    ref_closed, ref_closed_path = _load_reference_for_camera("closed", camera_key)
    ref_open, ref_open_path = _load_reference_for_camera("open", camera_key)
    if ref_closed is None or ref_open is None:
        return jsonify(
            {
                "status": "error",
                "msg": "缺少参考图",
                "camera_key": camera_key,
                "ref_closed_path": ref_closed_path,
                "ref_open_path": ref_open_path,
            }
        )

    vh, vw = ref_closed.shape
    rect = _calc_region_rect((vh, vw), camera_key)
    if rect is None:
        return jsonify({"status": "error", "msg": "检测区域无效", "camera_key": camera_key})
    x1, y1, x2, y2 = rect
    max_diff = _compute_diff(ref_open[y1:y2, x1:x2], ref_closed[y1:y2, x1:x2])

    if max_diff > 500:
        threshold = int(max_diff * 0.4)
        _set_camera_match_threshold(camera_key, threshold)
        save_config(CONFIG)
        msg = f"[门禁] 标定分析完成，动作落差 {max_diff}，{camera_key} 识别阈值已更新为 {threshold}"
        add_log(-1, msg)
        with status_lock:
            door_status_info["current_status"] = "unknown_calibration"
        log_audit_event(
            "door.calibration.apply",
            target="door_config",
            detail={"camera_key": camera_key, "max_diff": max_diff, "match_threshold": threshold},
        )
        return jsonify(
            {
                "status": "success",
                "msg": msg,
                "camera_key": camera_key,
                "match_threshold": threshold,
                "ref_closed_path": ref_closed_path,
                "ref_open_path": ref_open_path,
            }
        )

    msg = f"[门禁] 标定分析失败，{camera_key} 画面差异过小({max_diff})"
    add_log(-1, msg)
    log_audit_event(
        "door.calibration.apply",
        target="door_config",
        detail={"camera_key": camera_key, "max_diff": max_diff, "error": "difference_too_small"},
        status="error",
    )
    return jsonify(
        {
            "status": "error",
            "msg": msg,
            "camera_key": camera_key,
            "ref_closed_path": ref_closed_path,
            "ref_open_path": ref_open_path,
        }
    )


@bp.route("/door_control/<action>")
@require_permission("door.control")
def api_door_control(action):
    if action not in DOOR_COMMANDS:
        return jsonify({"status": "error", "msg": "控制指令无效"})

    current_user = get_current_user()
    lock_key = "door:main"
    locked, lock_info = acquire_operation_lock(lock_key, current_user.username, action, timeout_sec=3.0)
    if not locked:
        return jsonify({"status": "error", "msg": f"门禁正由 {lock_info.get('owner')} 操作，请稍后再试", "error": "device_busy"}), 409
    try:
        success, msg = _send_tcp_command(DOOR_COMMANDS[action])
        action_name = {"open": "打开", "stop": "停止", "close": "关闭"}[action]
        add_log(-1, f"[门禁] 大门控制: [{action_name}] - {'成功' if success else '失败'} ({msg})")
        log_audit_event(
            "door.command.execute",
            target=action,
            detail={"action": action, "message": msg},
            status="ok" if success else "error",
        )
        return jsonify({"status": "success" if success else "error", "msg": f"{action_name}指令下发{'成功' if success else '失败'}"})
    finally:
        release_operation_lock(lock_key, current_user.username)
