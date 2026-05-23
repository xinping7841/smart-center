import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def _calc_roi(shape, region):
    h, w = shape[:2]
    x1 = max(0, min(int(float(region.get("p_x1", 0.2)) * w), w))
    y1 = max(0, min(int(float(region.get("p_y1", 0.2)) * h), h))
    x2 = max(0, min(int(float(region.get("p_x2", 0.8)) * w), w))
    y2 = max(0, min(int(float(region.get("p_y2", 0.8)) * h), h))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, w, h
    return x1, y1, x2, y2


def _iter_frames(video_path: Path, step: int):
    cap = cv2.VideoCapture(str(video_path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % max(1, step) == 0:
            yield idx, frame
        idx += 1
    cap.release()


def _extract_feature(gray, region):
    x1, y1, x2, y2 = _calc_roi(gray.shape, region)
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    feat = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    return feat.reshape(-1)


def _write_rgb(path: Path, gray: np.ndarray):
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), rgb)


def _load_reference_gray(path: Path):
    if not path.exists():
        return None
    ref = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if ref is None or ref.size == 0:
        return None
    return ref


def _load_reference_feature(refs_root: Path, state: str, cam_key: str, frame_shape, region):
    candidates = [
        refs_root / f"door_ref_{state}_{cam_key}.jpg",
        refs_root / f"door_ref_{state}.jpg",
    ]
    for p in candidates:
        gray = _load_reference_gray(p)
        if gray is None:
            continue
        h, w = frame_shape[:2]
        resized = cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA)
        feat = _extract_feature(resized, region)
        if feat is not None:
            return feat, str(p)
    return None, ""


def _build_for_camera(
    cam_key: str,
    video_path: Path,
    region: dict,
    out_root: Path,
    step: int,
    max_frames: int,
    refs_root: Path,
):
    rows = []
    cache = []
    frame_shape = None
    for idx, frame in _iter_frames(video_path, step=step):
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        feat = _extract_feature(gray, region)
        if feat is None:
            continue
        if frame_shape is None:
            frame_shape = gray.shape
        rows.append((idx, feat))
        cache.append((idx, gray))
        if len(rows) >= max_frames:
            break
    if len(rows) < 20:
        return {"ok": False, "reason": "too_few_samples", "count": len(rows)}

    arr = np.stack([r[1] for r in rows], axis=0)
    mean = arr.mean(axis=0, keepdims=True)
    centered = arr - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    pc1 = vt[0]
    score = centered @ pc1

    low_label = "closed"
    high_label = "open"
    orientation_method = "default"
    ref_closed_path = ""
    ref_open_path = ""
    if frame_shape is not None:
        ref_closed_feat, ref_closed_path = _load_reference_feature(
            refs_root=refs_root, state="closed", cam_key=cam_key, frame_shape=frame_shape, region=region
        )
        ref_open_feat, ref_open_path = _load_reference_feature(
            refs_root=refs_root, state="open", cam_key=cam_key, frame_shape=frame_shape, region=region
        )
        if ref_closed_feat is not None and ref_open_feat is not None:
            c_proj = float((ref_closed_feat - mean.reshape(-1)) @ pc1)
            o_proj = float((ref_open_feat - mean.reshape(-1)) @ pc1)
            if abs(c_proj - o_proj) > 1e-6:
                if c_proj <= o_proj:
                    low_label, high_label = "closed", "open"
                else:
                    low_label, high_label = "open", "closed"
                orientation_method = "reference_projection"

    low = float(np.percentile(score, 20))
    high = float(np.percentile(score, 80))
    labeled = []
    for (idx, _), (_, gray), s in zip(rows, cache, score):
        if s <= low:
            labeled.append((idx, gray, low_label))
        elif s >= high:
            labeled.append((idx, gray, high_label))

    if len(labeled) < 30:
        return {"ok": False, "reason": "too_few_labeled", "count": len(labeled)}

    train_open = out_root / "train" / "open"
    train_closed = out_root / "train" / "closed"
    val_open = out_root / "val" / "open"
    val_closed = out_root / "val" / "closed"
    for p in (train_open, train_closed, val_open, val_closed):
        p.mkdir(parents=True, exist_ok=True)

    open_count = 0
    closed_count = 0
    for i, (_, gray, label) in enumerate(labeled):
        is_val = (i % 7 == 0)
        target = (val_open if is_val else train_open) if label == "open" else (val_closed if is_val else train_closed)
        _write_rgb(target / f"{cam_key}_{label}_{i:04d}.jpg", gray)
        if label == "open":
            open_count += 1
        else:
            closed_count += 1

    return {
        "ok": True,
        "open": open_count,
        "closed": closed_count,
        "labeled": len(labeled),
        "label_orientation": {
            "method": orientation_method,
            "low_score_label": low_label,
            "high_score_label": high_label,
            "ref_closed_path": ref_closed_path,
            "ref_open_path": ref_open_path,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--recording-dir", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--refs-root", default="")
    parser.add_argument("--step", type=int, default=4)
    parser.add_argument("--max-frames", type=int, default=800)
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    door_cfg = cfg.get("door_config", {}) if isinstance(cfg, dict) else {}
    regions = door_cfg.get("regions", {}) if isinstance(door_cfg.get("regions"), dict) else {}
    base_region = door_cfg.get("region_pct", {}) if isinstance(door_cfg.get("region_pct"), dict) else {}
    refs_root = Path(args.refs_root) if str(args.refs_root).strip() else (config_path.parent / "runtime" / "door_refs")

    rec = Path(args.recording_dir)
    out_root = Path(args.dataset_root)
    if out_root.exists():
        for p in out_root.glob("*"):
            if p.is_dir():
                for sp in p.rglob("*"):
                    if sp.is_file():
                        sp.unlink()
            elif p.is_file():
                p.unlink()
    out_root.mkdir(parents=True, exist_ok=True)

    summary = {"recording_dir": str(rec), "dataset_root": str(out_root), "refs_root": str(refs_root), "cameras": {}}
    total_open = 0
    total_closed = 0
    for cam_key in ("main", "aux"):
        video = rec / f"{cam_key}.mp4"
        if not video.exists():
            summary["cameras"][cam_key] = {"ok": False, "reason": "missing_video"}
            continue
        region = regions.get(cam_key) if isinstance(regions.get(cam_key), dict) else base_region
        r = _build_for_camera(
            cam_key=cam_key,
            video_path=video,
            region=region or {},
            out_root=out_root,
            step=args.step,
            max_frames=args.max_frames,
            refs_root=refs_root,
        )
        summary["cameras"][cam_key] = r
        if r.get("ok"):
            total_open += int(r.get("open", 0))
            total_closed += int(r.get("closed", 0))
    summary["total_open"] = total_open
    summary["total_closed"] = total_closed

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
