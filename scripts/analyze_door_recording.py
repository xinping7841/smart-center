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


def _sample_features(video_path: Path, region: dict, step: int = 6):
    cap = cv2.VideoCapture(str(video_path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return []
    idx = 0
    rows = []
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % max(1, step) != 0:
            idx += 1
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x1, y1, x2, y2 = _calc_roi(gray.shape, region)
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            idx += 1
            continue
        feat = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
        rows.append((idx, feat))
        idx += 1
    cap.release()
    return rows


def _analyze(video_path: Path, region: dict, step: int):
    rows = _sample_features(video_path, region=region, step=step)
    if len(rows) < 10:
        return {"ok": False, "reason": "not_enough_frames", "samples": len(rows)}
    arr = np.stack([x[1].reshape(-1) for x in rows], axis=0)
    mean = arr.mean(axis=0, keepdims=True)
    centered = arr - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    pc1 = vt[0]
    score = centered @ pc1
    spread = float(np.percentile(score, 95) - np.percentile(score, 5))
    dynamic = float(np.std(score))
    return {
        "ok": True,
        "samples": len(rows),
        "score_std": round(dynamic, 4),
        "score_p95_p05": round(spread, 4),
        "motion_rich": bool(spread >= 10.0 and dynamic >= 3.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--recording-dir", required=True)
    parser.add_argument("--step", type=int, default=6)
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    door_cfg = cfg.get("door_config", {}) if isinstance(cfg, dict) else {}
    regions = door_cfg.get("regions", {}) if isinstance(door_cfg.get("regions"), dict) else {}
    base_region = door_cfg.get("region_pct", {}) if isinstance(door_cfg.get("region_pct"), dict) else {}

    rec = Path(args.recording_dir)
    out = {"recording_dir": str(rec), "cameras": {}}
    for cam_key in ("main", "aux"):
        p = rec / f"{cam_key}.mp4"
        if not p.exists():
            out["cameras"][cam_key] = {"ok": False, "reason": "missing_video"}
            continue
        region = regions.get(cam_key) if isinstance(regions.get(cam_key), dict) else base_region
        out["cameras"][cam_key] = _analyze(p, region=region or {}, step=args.step)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

