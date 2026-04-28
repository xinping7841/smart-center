import argparse
import json
import os
import random
import shutil
import time
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


def _safe_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp_path), str(path))


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _collect_camera_rtsp_urls(cfg: dict) -> List[Tuple[str, str]]:
    door_cfg = cfg.get("door_config", {}) if isinstance(cfg.get("door_config"), dict) else {}
    cameras = door_cfg.get("cameras", []) if isinstance(door_cfg.get("cameras"), list) else []
    result = []
    for item in cameras:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        rtsp = str(item.get("rtsp_url") or "").strip()
        enabled = bool(item.get("enabled", True))
        if key and rtsp and enabled:
            result.append((key, rtsp))
    if not result:
        legacy = str(door_cfg.get("rtsp_url") or "").strip()
        if legacy:
            result.append(("main", legacy))
    return result


def _reference_path(state: str, camera_key: str = "") -> str:
    suffix = str(camera_key or "").strip()
    if suffix:
        return f"door_ref_{state}_{suffix}.jpg"
    return f"door_ref_{state}.jpg"


def _load_gray(path: str) -> Optional[np.ndarray]:
    if not path or not os.path.exists(path):
        return None
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return img


def _resolve_ref_paths(filename: str) -> List[str]:
    roots = [Path("/srv/smart-center-data/runtime/door_refs"), Path.cwd(), Path("/srv/smart-center/current"), Path("/srv/smart-center-data"), Path("/root")]
    result = []
    for root in roots:
        p = (root / filename).resolve()
        if str(p) not in result:
            result.append(str(p))
    return result


def _load_references_for_camera(camera_key: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    closed = None
    open_ = None
    for cand in _resolve_ref_paths(_reference_path("closed", camera_key)):
        closed = _load_gray(cand)
        if closed is not None:
            break
    for cand in _resolve_ref_paths(_reference_path("open", camera_key)):
        open_ = _load_gray(cand)
        if open_ is not None:
            break
    if closed is None:
        for cand in _resolve_ref_paths(_reference_path("closed")):
            closed = _load_gray(cand)
            if closed is not None:
                break
    if open_ is None:
        for cand in _resolve_ref_paths(_reference_path("open")):
            open_ = _load_gray(cand)
            if open_ is not None:
                break
    return closed, open_


def _resize_like(img: np.ndarray, ref: np.ndarray) -> np.ndarray:
    if img.shape[:2] == ref.shape[:2]:
        return img
    return cv2.resize(img, (ref.shape[1], ref.shape[0]))


def _mean_absdiff(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    return float(np.mean(cv2.absdiff(a, b)))


def _augment_gray(img: np.ndarray) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    if random.random() < 0.8:
        alpha = random.uniform(0.85, 1.2)
        beta = random.uniform(-12, 12)
        out = cv2.convertScaleAbs(out, alpha=alpha, beta=beta)
    if random.random() < 0.6:
        k = random.choice([3, 5])
        out = cv2.GaussianBlur(out, (k, k), 0)
    if random.random() < 0.4:
        noise = np.random.normal(0, random.uniform(2.0, 8.0), out.shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if random.random() < 0.5:
        tx = int(random.uniform(-0.02, 0.02) * w)
        ty = int(random.uniform(-0.02, 0.02) * h)
        m = np.float32([[1, 0, tx], [0, 1, ty]])
        out = cv2.warpAffine(out, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    return out


def _write_rgb_image(path: Path, gray: np.ndarray) -> None:
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), rgb)


def _capture_frames(rtsp_url: str, sample_count: int = 24) -> List[np.ndarray]:
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return []
    frames = []
    read_round = max(sample_count * 4, sample_count)
    for i in range(read_round):
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        if i % 3 != 0:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        frames.append(gray)
        if len(frames) >= sample_count:
            break
    cap.release()
    return frames


def _build_dataset(dataset_root: Path, cfg: dict) -> Tuple[int, int]:
    random.seed(42)
    np.random.seed(42)

    train_open = dataset_root / "train" / "open"
    train_closed = dataset_root / "train" / "closed"
    val_open = dataset_root / "val" / "open"
    val_closed = dataset_root / "val" / "closed"
    for p in [train_open, train_closed, val_open, val_closed]:
        p.mkdir(parents=True, exist_ok=True)

    total_open = 0
    total_closed = 0

    camera_urls = _collect_camera_rtsp_urls(cfg)
    for camera_key, rtsp_url in camera_urls:
        ref_closed, ref_open = _load_references_for_camera(camera_key)
        if ref_closed is None or ref_open is None:
            continue
        ref_gap = _mean_absdiff(ref_open, ref_closed)
        if ref_gap < 3.5:
            print(f"skip_camera_invalid_refs camera={camera_key} ref_gap={ref_gap:.3f}")
            continue

        frame_samples = _capture_frames(rtsp_url, sample_count=24)
        if frame_samples:
            base_h, base_w = ref_closed.shape[:2]
            for idx, frame in enumerate(frame_samples):
                frame = _resize_like(frame, ref_closed)
                diff_c = float(np.mean(cv2.absdiff(frame, ref_closed)))
                diff_o = float(np.mean(cv2.absdiff(frame, ref_open)))
                if abs(diff_c - diff_o) < 2.0:
                    continue
                target_label = "closed" if diff_c <= diff_o else "open"
                target_dir = train_closed if target_label == "closed" else train_open
                _write_rgb_image(target_dir / f"{camera_key}_frame_{idx:03d}.jpg", frame)
                if target_label == "closed":
                    total_closed += 1
                else:
                    total_open += 1

                for aug_idx in range(2):
                    aug = _augment_gray(frame)
                    _write_rgb_image(target_dir / f"{camera_key}_frame_{idx:03d}_aug{aug_idx}.jpg", aug)
                    if target_label == "closed":
                        total_closed += 1
                    else:
                        total_open += 1

            # Hold out a few validation samples
            for idx, frame in enumerate(frame_samples[:6]):
                frame = _resize_like(frame, ref_closed)
                diff_c = float(np.mean(cv2.absdiff(frame, ref_closed)))
                diff_o = float(np.mean(cv2.absdiff(frame, ref_open)))
                if abs(diff_c - diff_o) < 2.0:
                    continue
                target_dir = val_closed if diff_c <= diff_o else val_open
                _write_rgb_image(target_dir / f"{camera_key}_val_{idx:03d}.jpg", frame)
        else:
            # If RTSP cannot be sampled, still bootstrap by references.
            for idx in range(18):
                closed_img = _augment_gray(ref_closed)
                open_img = _augment_gray(ref_open)
                _write_rgb_image(train_closed / f"{camera_key}_ref_closed_{idx:03d}.jpg", closed_img)
                _write_rgb_image(train_open / f"{camera_key}_ref_open_{idx:03d}.jpg", open_img)
                total_closed += 1
                total_open += 1
            for idx in range(4):
                _write_rgb_image(val_closed / f"{camera_key}_val_closed_{idx:03d}.jpg", _augment_gray(ref_closed))
                _write_rgb_image(val_open / f"{camera_key}_val_open_{idx:03d}.jpg", _augment_gray(ref_open))

    return total_open, total_closed


def _write_data_yaml(dataset_root: Path) -> Path:
    yaml_path = dataset_root / "door_state_cls.yaml"
    content = "\n".join(
        [
            f"path: {dataset_root.as_posix()}",
            "train: train",
            "val: val",
            "names:",
            "  0: closed",
            "  1: open",
            "",
        ]
    )
    yaml_path.write_text(content, encoding="utf-8")
    return yaml_path


def _write_status(path: Optional[Path], payload: dict) -> None:
    if path is None:
        return
    try:
        _safe_write_json(path, payload)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild door open/close classification model")
    parser.add_argument("--config", required=True, help="Path to smart-center config.json")
    parser.add_argument("--output", required=True, help="Output .pt path")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--status-file", default="", help="Persist rebuild runtime status json")
    args = parser.parse_args()

    from ultralytics import YOLO

    config_path = Path(args.config).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_file = Path(args.status_file).resolve() if str(args.status_file or "").strip() else None

    cfg = _load_config(config_path)
    _write_status(
        status_file,
        {
            "running": True,
            "last_started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_status": "running",
            "last_message": "模型重建中",
            "last_model_path": str(output_path),
        },
    )

    with tempfile.TemporaryDirectory(prefix="door_model_rebuild_") as tmp:
        tmp_root = Path(tmp)
        dataset_root = tmp_root / "dataset"
        dataset_root.mkdir(parents=True, exist_ok=True)
        open_count, closed_count = _build_dataset(dataset_root, cfg)
        if open_count < 10 or closed_count < 10:
            print(f"dataset_too_small open={open_count} closed={closed_count}")
            _write_status(
                status_file,
                {
                    "running": False,
                    "last_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "last_status": "error",
                    "last_message": "样本不足，未生成模型",
                    "last_output": f"dataset_too_small open={open_count} closed={closed_count}",
                    "last_exit_code": 2,
                    "last_model_path": str(output_path),
                },
            )
            return 2

        run_root = tmp_root / "runs"
        run_root.mkdir(parents=True, exist_ok=True)

        base_model = "/srv/smart-center/models/yolo11n-cls.pt" if os.path.exists("/srv/smart-center/models/yolo11n-cls.pt") else "yolo11n-cls.pt"
        model = YOLO(base_model)
        results = model.train(
            data=str(dataset_root),
            epochs=max(1, int(args.epochs)),
            imgsz=max(96, int(args.imgsz)),
            batch=max(4, int(args.batch)),
            device=args.device,
            amp=False,
            project=str(run_root),
            name="door_state_cls",
            exist_ok=True,
            pretrained=True,
            cache=False,
            verbose=False,
        )

        best_path = Path(getattr(results, "save_dir", run_root / "door_state_cls")) / "weights" / "best.pt"
        if not best_path.exists():
            print(f"best_model_not_found: {best_path}")
            _write_status(
                status_file,
                {
                    "running": False,
                    "last_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "last_status": "error",
                    "last_message": "训练完成但未找到 best.pt",
                    "last_output": f"best_model_not_found: {best_path}",
                    "last_exit_code": 3,
                    "last_model_path": str(output_path),
                },
            )
            return 3

        shutil.copy2(best_path, output_path)
        success_msg = json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "open_samples": open_count,
                "closed_samples": closed_count,
            },
            ensure_ascii=False,
        )
        _write_status(
            status_file,
            {
                "running": False,
                "last_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "last_status": "success",
                "last_message": "模型重建完成",
                "last_output": success_msg,
                "last_exit_code": 0,
                "last_model_path": str(output_path),
            },
        )
        try:
            import urllib.request

            req = urllib.request.Request(
                "http://127.0.0.1:18080/reload_models",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                _ = resp.read()
        except Exception:
            pass
        print(json.dumps({
            "status": "ok",
            "output": str(output_path),
            "open_samples": open_count,
            "closed_samples": closed_count,
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        try:
            import argparse as _argparse

            parser = _argparse.ArgumentParser(add_help=False)
            parser.add_argument("--status-file", default="")
            known, _ = parser.parse_known_args()
            status_file = Path(known.status_file).resolve() if str(known.status_file or "").strip() else None
            _write_status(
                status_file,
                {
                    "running": False,
                    "last_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "last_status": "error",
                    "last_message": "模型重建异常",
                    "last_output": str(exc),
                    "last_exit_code": 500,
                },
            )
        except Exception:
            pass
        raise
