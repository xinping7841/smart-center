#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np


CFG_PATH = Path("/srv/smart-center-data/config.json")
REFS_DIR = Path("/srv/smart-center-data/runtime/door_refs")


def _load_gray(path: Path):
    if not path.exists():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    return img


def _calc_rect(shape, region):
    h, w = shape[:2]
    x1 = max(0, min(int(float(region["p_x1"]) * w), w - 1))
    y1 = max(0, min(int(float(region["p_y1"]) * h), h - 1))
    x2 = max(1, min(int(float(region["p_x2"]) * w), w))
    y2 = max(1, min(int(float(region["p_y2"]) * h), h))
    if x2 <= x1 + 8:
        x2 = min(w, x1 + 8)
    if y2 <= y1 + 8:
        y2 = min(h, y1 + 8)
    return x1, y1, x2, y2


def _roi_score(cur_gray, ref_c, ref_o, region) -> Tuple[float, float, float]:
    x1, y1, x2, y2 = _calc_rect(cur_gray.shape, region)
    a = cur_gray[y1:y2, x1:x2]
    b = ref_c[y1:y2, x1:x2]
    c = ref_o[y1:y2, x1:x2]
    if a.size == 0 or b.size == 0 or c.size == 0:
        return -1.0, 0.0, 0.0
    diff_c = float(np.mean(cv2.absdiff(a, b)))
    diff_o = float(np.mean(cv2.absdiff(a, c)))
    sep = float(np.mean(cv2.absdiff(b, c)))
    score = sep - abs(diff_c - diff_o) * 0.35
    return score, diff_c, diff_o


def _capture_main_gray(cfg: dict):
    cams = (cfg.get("door_config", {}) or {}).get("cameras", []) or []
    rtsp = ""
    for c in cams:
        if isinstance(c, dict) and str(c.get("key") or "") == "main":
            rtsp = str(c.get("rtsp_url") or "").strip()
            break
    if not rtsp:
        return None
    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None
    frame = None
    for _ in range(24):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    if frame is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _clip_region(region: Dict[str, float]) -> Dict[str, float]:
    out = dict(region)
    out["p_x1"] = max(0.05, min(float(out["p_x1"]), 0.9))
    out["p_y1"] = max(0.05, min(float(out["p_y1"]), 0.9))
    out["p_x2"] = max(out["p_x1"] + 0.08, min(float(out["p_x2"]), 0.98))
    out["p_y2"] = max(out["p_y1"] + 0.08, min(float(out["p_y2"]), 0.98))
    return out


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    door = cfg.setdefault("door_config", {})
    regions = door.setdefault("regions", {})
    base = regions.get("main") or door.get("region_pct") or {
        "p_x1": 0.33,
        "p_y1": 0.22,
        "p_x2": 0.64,
        "p_y2": 0.48,
    }
    base = _clip_region(base)

    ref_c = _load_gray(REFS_DIR / "door_ref_closed_main.jpg")
    ref_o = _load_gray(REFS_DIR / "door_ref_open_main.jpg")
    cur = _capture_main_gray(cfg)
    if ref_c is None or ref_o is None or cur is None:
        print(json.dumps({"status": "error", "reason": "missing_data"}, ensure_ascii=False))
        return 2

    if ref_c.shape[:2] != cur.shape[:2]:
        ref_c = cv2.resize(ref_c, (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_AREA)
    if ref_o.shape[:2] != cur.shape[:2]:
        ref_o = cv2.resize(ref_o, (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_AREA)

    best = dict(base)
    best_score, best_dc, best_do = _roi_score(cur, ref_c, ref_o, best)
    for dx1 in (-0.04, -0.02, 0.0, 0.02, 0.04):
        for dy1 in (-0.04, -0.02, 0.0, 0.02, 0.04):
            for dx2 in (-0.04, -0.02, 0.0, 0.02, 0.04):
                for dy2 in (-0.04, -0.02, 0.0, 0.02, 0.04):
                    cand = _clip_region(
                        {
                            "p_x1": base["p_x1"] + dx1,
                            "p_y1": base["p_y1"] + dy1,
                            "p_x2": base["p_x2"] + dx2,
                            "p_y2": base["p_y2"] + dy2,
                        }
                    )
                    score, dc, do = _roi_score(cur, ref_c, ref_o, cand)
                    if score > best_score:
                        best_score, best_dc, best_do = score, dc, do
                        best = cand

    regions["main"] = dict(best)
    door["regions"] = regions
    door["region_pct"] = dict(best)
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "best_region": best,
                "best_score": round(best_score, 4),
                "diff_c": round(best_dc, 4),
                "diff_o": round(best_do, 4),
                "base_region": base,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
