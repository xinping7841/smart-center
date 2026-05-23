import base64
import json
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover
    YOLO = None


def _env_text(name: str, default: str) -> str:
    return str(os.environ.get(name, default) or default).strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    text = str(os.environ.get(name, str(default))).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _safe_read_gray(path: str) -> Optional[np.ndarray]:
    path = str(path or "").strip()
    if not path or not os.path.exists(path):
        return None
    try:
        return cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


def _resolve_reference_candidates(filename: str) -> List[str]:
    filename = str(filename or "").strip()
    if not filename:
        return []
    candidates: List[str] = []
    data_dir = _env_text("SMART_CENTER_DATA_DIR", "/srv/smart-center-data")
    cwd = Path.cwd()
    for root in [
        Path(data_dir) / "runtime" / "door_refs",
        Path(data_dir),
        Path("/srv/smart-center/current"),
        cwd,
    ]:
        path = (root / filename).resolve()
        path_text = str(path)
        if path_text not in candidates:
            candidates.append(path_text)
    return candidates


def _load_reference_gray(filename: str) -> Optional[np.ndarray]:
    for candidate in _resolve_reference_candidates(filename):
        img = _safe_read_gray(candidate)
        if img is not None:
            return img
    return None


def _calc_region_rect(shape: Tuple[int, int], region_pct: Dict[str, float]) -> Optional[Tuple[int, int, int, int]]:
    vh, vw = shape[:2]
    try:
        x1 = max(0, min(int(float(region_pct.get("p_x1", 0.2)) * vw), vw))
        y1 = max(0, min(int(float(region_pct.get("p_y1", 0.2)) * vh), vh))
        x2 = max(0, min(int(float(region_pct.get("p_x2", 0.8)) * vw), vw))
        y2 = max(0, min(int(float(region_pct.get("p_y2", 0.8)) * vh), vh))
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _compute_diff(img1: np.ndarray, img2: np.ndarray) -> float:
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    return float(np.mean(cv2.absdiff(img1, img2)))


def _load_runtime_door_config() -> Dict:
    # Default to smart-center runtime data dir if present.
    config_path = _env_text("SMART_CENTER_CONFIG_FILE", "/srv/smart-center-data/config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        door_cfg = data.get("door_config", {}) if isinstance(data, dict) else {}
        return door_cfg if isinstance(door_cfg, dict) else {}
    except Exception:
        return {}


def _legacy_ref_fallback(frame: np.ndarray, camera_key: str) -> Optional[Tuple[str, float, float, float]]:
    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    door_cfg = _load_runtime_door_config()
    preferred = str(door_cfg.get("preferred_detection_camera") or "main").strip() or "main"
    regions = door_cfg.get("regions", {}) if isinstance(door_cfg.get("regions"), dict) else {}
    region_pct = regions.get(camera_key) if isinstance(regions.get(camera_key), dict) else door_cfg.get("region_pct", {})
    if not isinstance(region_pct, dict):
        region_pct = {"p_x1": 0.2, "p_y1": 0.2, "p_x2": 0.8, "p_y2": 0.8}
    rect = _calc_region_rect(gray.shape, region_pct)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    crop = gray[y1:y2, x1:x2]

    # Camera-specific refs first, then legacy shared refs.
    ref_closed = _load_reference_gray(f"door_ref_closed_{camera_key}.jpg") or _load_reference_gray("door_ref_closed.jpg")
    ref_open = _load_reference_gray(f"door_ref_open_{camera_key}.jpg") or _load_reference_gray("door_ref_open.jpg")
    if ref_closed is None or ref_open is None:
        return None

    vh, vw = gray.shape
    closed_crop = cv2.resize(ref_closed, (vw, vh))[y1:y2, x1:x2]
    open_crop = cv2.resize(ref_open, (vw, vh))[y1:y2, x1:x2]
    diff_c = _compute_diff(crop, closed_crop)
    diff_o = _compute_diff(crop, open_crop)
    diff_gap = abs(diff_c - diff_o)
    diff_sum = max(diff_c + diff_o, 1.0)
    confidence = max(0.0, min(diff_gap / diff_sum, 1.0))
    status = "closed" if diff_c <= diff_o else "open"
    if confidence < 0.08:
        status = "unknown"
    return status, confidence, float(diff_c), float(diff_o)


def _split_labels(text: str) -> List[str]:
    return [item.strip().lower() for item in str(text or "").split(",") if item.strip()]


def _point_in_polygon(x: float, y: float, polygon: np.ndarray) -> bool:
    try:
        return cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0
    except Exception:
        return False


def _decode_image(image_b64: str) -> Optional[np.ndarray]:
    try:
        raw = base64.b64decode(image_b64.encode("ascii"), validate=False)
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


@dataclass
class ModelConfig:
    door_model_path: str
    person_model_path: str
    device: str
    imgsz: int
    door_conf: float
    person_conf: float
    open_labels: List[str]
    closed_labels: List[str]


class InferenceEngine:
    def __init__(self) -> None:
        self.cfg = ModelConfig(
            door_model_path=_env_text("DOOR_MODEL_PATH", ""),
            person_model_path=_env_text("PERSON_MODEL_PATH", ""),
            device=_env_text("MODEL_DEVICE", "cuda:0"),
            imgsz=max(320, _env_int("MODEL_IMGSZ", 640)),
            door_conf=max(0.01, min(_env_float("DOOR_CONF", 0.2), 0.99)),
            person_conf=max(0.01, min(_env_float("PERSON_CONF", 0.25), 0.99)),
            open_labels=_split_labels(_env_text("DOOR_OPEN_LABELS", "open,opened,door_open")),
            closed_labels=_split_labels(_env_text("DOOR_CLOSED_LABELS", "closed,close,door_closed")),
        )
        self._lock = threading.Lock()
        self._door_model = None
        self._person_model = None
        self._loaded_at = None
        self._load_models()

    def _load_models(self) -> None:
        if YOLO is None:
            print("[vision_ultra] ultralytics is not installed. Service will return unknown.")
            return
        if self.cfg.door_model_path and os.path.exists(self.cfg.door_model_path):
            try:
                self._door_model = YOLO(self.cfg.door_model_path)
                print(f"[vision_ultra] loaded door model: {self.cfg.door_model_path}")
            except Exception as exc:
                print(f"[vision_ultra] failed to load door model: {exc}")
        else:
            if self.cfg.door_model_path:
                print(f"[vision_ultra] door model not found: {self.cfg.door_model_path}")
        if self.cfg.person_model_path and os.path.exists(self.cfg.person_model_path):
            try:
                self._person_model = YOLO(self.cfg.person_model_path)
                print(f"[vision_ultra] loaded person model: {self.cfg.person_model_path}")
            except Exception as exc:
                print(f"[vision_ultra] failed to load person model: {exc}")
        else:
            if self.cfg.person_model_path:
                print(f"[vision_ultra] person model not found: {self.cfg.person_model_path}")
        self._loaded_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def reload_models(self) -> Dict:
        with self._lock:
            self._door_model = None
            self._person_model = None
            self._load_models()
            return self.health()

    def health(self) -> Dict:
        return {
            "status": "ok",
            "engine": "ultralytics",
            "loaded_at": self._loaded_at,
            "device": self.cfg.device,
            "imgsz": self.cfg.imgsz,
            "door_model_path": self.cfg.door_model_path,
            "door_model_exists": bool(self.cfg.door_model_path and os.path.exists(self.cfg.door_model_path)),
            "door_model_loaded": self._door_model is not None,
            "person_model_path": self.cfg.person_model_path,
            "person_model_exists": bool(self.cfg.person_model_path and os.path.exists(self.cfg.person_model_path)),
            "person_model_loaded": self._person_model is not None,
        }

    def infer(self, frame: np.ndarray, camera_key: str, zones_norm: Optional[Dict[str, List[List[float]]]] = None) -> Dict:
        with self._lock:
            status, confidence, diff_c, diff_o = self._infer_door_status(frame, camera_key)
            people_count, zone_counts = self._infer_people(frame, zones_norm or {})
        return {
            "camera_key": camera_key,
            "status": status,
            "confidence": confidence,
            "diff_c": diff_c,
            "diff_o": diff_o,
            "people_count": people_count,
            "zone_counts": zone_counts,
            "engine": "ultralytics",
            "model_loaded_at": self._loaded_at,
        }

    def _infer_door_status(self, frame: np.ndarray, camera_key: str) -> Tuple[str, float, float, float]:
        if self._door_model is None:
            fallback = _legacy_ref_fallback(frame, camera_key)
            if fallback is None:
                return "unknown", 0.0, 0.0, 0.0
            status, conf, diff_c, diff_o = fallback
            return status, conf, diff_c, diff_o
        try:
            result = self._door_model.predict(
                source=frame,
                verbose=False,
                device=self.cfg.device,
                imgsz=self.cfg.imgsz,
                conf=self.cfg.door_conf,
            )[0]
        except Exception as exc:
            print(f"[vision_ultra] door infer failed: {exc}")
            fallback = _legacy_ref_fallback(frame, camera_key)
            if fallback is None:
                return "unknown", 0.0, 0.0, 0.0
            status, conf, diff_c, diff_o = fallback
            return status, conf, diff_c, diff_o

        names = result.names or {}

        # Classify model branch
        probs = getattr(result, "probs", None)
        if probs is not None and getattr(probs, "top1", None) is not None:
            top1 = int(probs.top1)
            label = str(names.get(top1, top1)).strip().lower()
            conf = float(getattr(probs, "top1conf", 0.0) or 0.0)
            if label in self.cfg.open_labels:
                return "open", max(0.0, min(conf, 1.0)), 0.0, 0.0
            if label in self.cfg.closed_labels:
                return "closed", max(0.0, min(conf, 1.0)), 0.0, 0.0
            return "unknown", max(0.0, min(conf * 0.5, 1.0)), 0.0, 0.0

        # Detect model branch (choose highest-confidence class)
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.conf is None or len(boxes.conf) <= 0:
            return "unknown", 0.0, 0.0, 0.0
        best_idx = int(np.argmax(boxes.conf.cpu().numpy()))
        cls_id = int(boxes.cls[best_idx].item())
        conf = float(boxes.conf[best_idx].item())
        label = str(names.get(cls_id, cls_id)).strip().lower()
        if label in self.cfg.open_labels:
            return "open", max(0.0, min(conf, 1.0)), 0.0, 0.0
        if label in self.cfg.closed_labels:
            return "closed", max(0.0, min(conf, 1.0)), 0.0, 0.0
        return "unknown", max(0.0, min(conf * 0.5, 1.0)), 0.0, 0.0

    def _infer_people(self, frame: np.ndarray, zones_norm: Dict[str, List[List[float]]]) -> Tuple[int, Dict[str, int]]:
        if self._person_model is None:
            return 0, {}
        try:
            result = self._person_model.predict(
                source=frame,
                verbose=False,
                device=self.cfg.device,
                imgsz=self.cfg.imgsz,
                conf=self.cfg.person_conf,
            )[0]
        except Exception as exc:
            print(f"[vision_ultra] person infer failed: {exc}")
            return 0, {}

        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.cls is None or boxes.xyxy is None:
            return 0, {}

        names = result.names or {}
        person_ids = {idx for idx, name in names.items() if str(name).strip().lower() == "person"}
        if not person_ids:
            person_ids = {0}

        xyxy = boxes.xyxy.cpu().numpy()
        cls = boxes.cls.cpu().numpy()
        centers = []
        for i in range(len(cls)):
            if int(cls[i]) not in person_ids:
                continue
            x1, y1, x2, y2 = xyxy[i]
            centers.append(((float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0))

        people_count = len(centers)
        zone_counts: Dict[str, int] = {}
        if not zones_norm:
            return people_count, zone_counts

        h, w = frame.shape[:2]
        for zone_name, pts in zones_norm.items():
            if not isinstance(pts, list) or len(pts) < 3:
                continue
            polygon_pts = []
            for pt in pts:
                if not isinstance(pt, list) or len(pt) != 2:
                    continue
                try:
                    px = float(pt[0]) * w
                    py = float(pt[1]) * h
                except Exception:
                    continue
                polygon_pts.append([px, py])
            if len(polygon_pts) < 3:
                continue
            polygon = np.array(polygon_pts, dtype=np.float32)
            zone_count = 0
            for cx, cy in centers:
                if _point_in_polygon(cx, cy, polygon):
                    zone_count += 1
            zone_counts[str(zone_name)] = zone_count
        return people_count, zone_counts


class VisionHandler(BaseHTTPRequestHandler):
    engine = InferenceEngine()

    def _send_json(self, payload: Dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path == "/reload_models":
            info = self.engine.reload_models()
            self._send_json({"status": "success", "message": "models_reloaded", "health": info}, status=200)
            return
        if self.path != "/infer/door_state":
            self._send_json({"error": "not_found"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8", errors="ignore") or "{}")
        except Exception as exc:
            self._send_json({"error": f"bad_request:{exc}"}, status=400)
            return

        camera_key = str(data.get("camera_key") or "main")
        image_b64 = str(data.get("image_b64") or "")
        if not image_b64:
            self._send_json({"error": "missing_image_b64"}, status=400)
            return
        frame = _decode_image(image_b64)
        if frame is None:
            self._send_json({"error": "invalid_image_b64"}, status=400)
            return

        zones_norm = data.get("zones_norm", {})
        if not isinstance(zones_norm, dict):
            zones_norm = {}

        result = self.engine.infer(frame, camera_key=camera_key, zones_norm=zones_norm)
        self._send_json(result, status=200)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(self.engine.health(), status=200)
            return
        self._send_json({"error": "not_found"}, status=404)


def run(host: str = "0.0.0.0", port: int = 18080) -> None:
    server = HTTPServer((host, int(port)), VisionHandler)
    print(f"[vision_ultra] serving on http://{host}:{port}")
    print(f"[vision_ultra] device={VisionHandler.engine.cfg.device} imgsz={VisionHandler.engine.cfg.imgsz}")
    server.serve_forever()


if __name__ == "__main__":
    run(
        host=_env_text("VISION_HOST", "0.0.0.0"),
        port=_env_int("VISION_PORT", 18080),
    )
