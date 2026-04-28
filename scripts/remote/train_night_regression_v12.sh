#!/usr/bin/env bash
set -euo pipefail

REC_DIR="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_221017"
DS_NIGHT_REG="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_221017_dataset_night_regression"
DS_V11="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v11_night_test"
DS_V12="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v12_night_regression"
PY="/srv/smart-center/.venv/bin/python"

echo "[1/6] build night regression dataset"
"$PY" /srv/smart-center/current/scripts/build_dataset_from_recording.py \
  --config /srv/smart-center-data/config.json \
  --recording-dir "$REC_DIR" \
  --dataset-root "$DS_NIGHT_REG" \
  --refs-root /srv/smart-center-data/runtime/door_refs \
  --step 2 \
  --max-frames 1800

echo "[2/6] merge into v12 dataset"
"$PY" /srv/smart-center/current/scripts/merge_door_datasets.py \
  --output "$DS_V12" \
  --inputs "$DS_V11" "$DS_NIGHT_REG"

echo "[3/6] sanitize images + count"
python3 - <<'PY'
from pathlib import Path
import cv2
import numpy as np

root = Path("/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v12_night_regression")
checked = 0
removed = 0

for p in root.rglob("*"):
    if not p.is_file():
        continue
    if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
        continue
    checked += 1
    bad = False
    try:
        arr = np.fromfile(str(p), dtype=np.uint8)
        if arr.size == 0:
            bad = True
        else:
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                bad = True
    except Exception:
        bad = True
    if bad:
        try:
            p.unlink()
            removed += 1
        except Exception:
            pass

def count(split, label):
    d = root / split / label
    if not d.exists():
        return 0
    return sum(1 for x in d.glob("*") if x.is_file())

print({
    "checked": checked,
    "removed": removed,
    "train_open": count("train", "open"),
    "train_closed": count("train", "closed"),
    "val_open": count("val", "open"),
    "val_closed": count("val", "closed"),
})
PY

RUN="door_cls_daymix_v12_nightreg_$(date +%Y%m%d_%H%M)"
RUN_ROOT="/srv/smart-center-data/runtime/door_retrain_runs/$RUN"
OUT_MODEL="$RUN_ROOT/door_state_cls_v12.pt"
mkdir -p "$RUN_ROOT"
echo "$RUN" > /srv/smart-center-data/runtime/door_retrain_runs/current_v12_run.txt

echo "[4/6] train: $RUN"
"$PY" - <<'PY' > "$RUN_ROOT/train.log" 2>&1
import json
import shutil
import tempfile
from pathlib import Path
from ultralytics import YOLO

src = Path("/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v12_night_regression").resolve()
run = Path("/srv/smart-center-data/runtime/door_retrain_runs/current_v12_run.txt").read_text().strip()
run_root = Path("/srv/smart-center-data/runtime/door_retrain_runs") / run
out_path = run_root / "door_state_cls_v12.pt"
run_root.mkdir(parents=True, exist_ok=True)

def count_images(root: Path, split: str, label: str) -> int:
    d = root / split / label
    if not d.exists():
        return 0
    return sum(1 for p in d.glob("*") if p.is_file())

with tempfile.TemporaryDirectory(prefix="door_cls_train_v12_") as tmp:
    ds = Path(tmp) / "dataset"
    if ds.exists():
        shutil.rmtree(ds)
    shutil.copytree(src, ds)

    stats = {
        "train_open": count_images(ds, "train", "open"),
        "train_closed": count_images(ds, "train", "closed"),
        "val_open": count_images(ds, "val", "open"),
        "val_closed": count_images(ds, "val", "closed"),
    }
    if min(stats.values()) < 40:
        raise SystemExit(json.dumps({"status": "error", "reason": "dataset_too_small", **stats}, ensure_ascii=False))

    base_model = "/srv/smart-center/models/yolo11n-cls.pt"
    if not Path(base_model).exists():
        base_model = "yolo11n-cls.pt"

    model = YOLO(base_model)
    results = model.train(
        data=str(ds),
        epochs=8,
        imgsz=640,
        batch=48,
        device="0",
        amp=True,
        workers=4,
        project=str(run_root),
        name="door_state_cls",
        exist_ok=True,
        pretrained=True,
        cache=False,
        verbose=False,
    )
    best = Path(getattr(results, "save_dir", run_root / "door_state_cls")) / "weights" / "best.pt"
    if not best.exists():
        raise SystemExit(json.dumps({"status": "error", "reason": "best_not_found", "best": str(best)}, ensure_ascii=False))
    shutil.copy2(best, out_path)
    print(json.dumps({"status": "ok", "output": str(out_path), "run_root": str(run_root), **stats}, ensure_ascii=False))
PY

if [ ! -f "$OUT_MODEL" ]; then
  echo "training failed, tail:"
  tail -n 120 "$RUN_ROOT/train.log" || true
  exit 2
fi

echo "[5/6] deploy + reload"
cp -f /srv/smart-center/models/door_state_cls.pt "/srv/smart-center/models/door_state_cls.pt.bak_$(date +%Y%m%d_%H%M%S)"
cp -f "$OUT_MODEL" /srv/smart-center/models/door_state_cls.pt
python3 - <<'PY'
import time
import urllib.request
last = None
for _ in range(5):
    try:
        req = urllib.request.Request("http://127.0.0.1:18080/reload_models", method="POST")
        print(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore"))
        print(urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=10).read().decode("utf-8", "ignore"))
        break
    except Exception as e:
        last = e
        time.sleep(2)
else:
    raise last
PY

echo "[6/6] static verify 120s"
python3 - <<'PY'
import json
import time
import urllib.request
u = "http://127.0.0.1:6899/api/door/vision_status"
end = time.time() + 120
total = 0
flip = 0
bad = 0
last = None
while time.time() < end:
    d = json.loads(urllib.request.urlopen(u, timeout=2).read().decode("utf-8", "ignore"))
    st = (d.get("vision_runtime", {}) or {}).get("stable_state") or d.get("door_status")
    total += 1
    if st != "closed":
        bad += 1
    if last is not None and st != last:
        flip += 1
    last = st
    time.sleep(0.25)
print({"total": total, "not_closed": bad, "flip_count": flip, "last_state": last})
PY

echo "RUN=$RUN"
echo "OUT_MODEL=$OUT_MODEL"

