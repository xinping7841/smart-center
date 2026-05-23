#!/usr/bin/env bash
set -euo pipefail

REC_DIR="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_192701"
DS_NIGHT="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_192701_dataset_night_light"
DS_V9="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v9_backlight"
DS_V10="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v10_night_light"
PY="/srv/smart-center/.venv/bin/python"

echo "[1/6] build night-light dataset"
"$PY" /srv/smart-center/current/scripts/build_dataset_from_recording.py \
  --config /srv/smart-center-data/config.json \
  --recording-dir "$REC_DIR" \
  --dataset-root "$DS_NIGHT" \
  --refs-root /srv/smart-center-data/runtime/door_refs \
  --step 2 \
  --max-frames 2200

echo "[2/6] merge dataset"
"$PY" /srv/smart-center/current/scripts/merge_door_datasets.py \
  --output "$DS_V10" \
  --inputs "$DS_V9" "$DS_NIGHT"

echo "[3/6] clean broken images"
python3 - <<'PY'
from pathlib import Path
import cv2
root=Path("/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v10_night_light")
removed=0
checked=0
for p in root.rglob("*"):
    if not p.is_file():
        continue
    if p.suffix.lower() not in {".jpg",".jpeg",".png",".bmp"}:
        continue
    checked += 1
    img=cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        try:
            p.unlink()
            removed += 1
        except Exception:
            pass
print({"checked":checked,"removed":removed})
PY

RUN="door_cls_daymix_v10_night_$(date +%Y%m%d_%H%M)"
RUN_ROOT="/srv/smart-center-data/runtime/door_retrain_runs/$RUN"
OUT_MODEL="$RUN_ROOT/door_state_cls_v10.pt"
mkdir -p "$RUN_ROOT"
echo "$RUN" > /srv/smart-center-data/runtime/door_retrain_runs/current_v10_run.txt

echo "[4/6] train: $RUN"
"$PY" /srv/smart-center/current/scripts/train_door_cls_from_dataset.py \
  --dataset-root "$DS_V10" \
  --output "$OUT_MODEL" \
  --run-name "$RUN" \
  --epochs 12 \
  --imgsz 640 \
  --batch 48 \
  --device 0 | tee "$RUN_ROOT/train_launcher.log"

echo "[5/6] deploy + reload"
cp -f /srv/smart-center/models/door_state_cls.pt "/srv/smart-center/models/door_state_cls.pt.bak_$(date +%Y%m%d_%H%M%S)"
cp -f "$OUT_MODEL" /srv/smart-center/models/door_state_cls.pt
python3 - <<'PY'
import urllib.request
req = urllib.request.Request("http://127.0.0.1:18080/reload_models", method="POST")
print(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore"))
print(urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=10).read().decode("utf-8", "ignore"))
PY

echo "[6/6] quick static verify 60s"
python3 - <<'PY'
import json,time,urllib.request
u='http://127.0.0.1:6899/api/door/vision_status'
end=time.time()+60
total=0
not_closed=0
while time.time()<end:
    d=json.loads(urllib.request.urlopen(u,timeout=2).read().decode('utf-8','ignore'))
    st=(d.get('vision_runtime',{}) or {}).get('stable_state') or d.get('door_status')
    total += 1
    if st!='closed':
        not_closed += 1
    time.sleep(0.25)
print({"total":total,"not_closed":not_closed,"ratio":round(not_closed/max(total,1),4)})
PY

echo "RUN=$RUN"
echo "OUT_MODEL=$OUT_MODEL"

