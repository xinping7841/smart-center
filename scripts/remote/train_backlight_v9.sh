#!/usr/bin/env bash
set -euo pipefail

REC_DIR="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_180224"
DS_BACKLIGHT="/srv/smart-center-data/runtime/door_recordings/door_day_20260405_180224_dataset_backlight"
DS_V8="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v8_evening"
DS_V9="/srv/smart-center-data/runtime/door_recordings/door_20260405_day_mix_dataset_v9_backlight"
PY="/srv/smart-center/.venv/bin/python"

echo "[1/4] build backlight dataset"
"$PY" /srv/smart-center/current/scripts/build_dataset_from_recording.py \
  --config /srv/smart-center-data/config.json \
  --recording-dir "$REC_DIR" \
  --dataset-root "$DS_BACKLIGHT" \
  --refs-root /srv/smart-center-data/runtime/door_refs \
  --step 3 \
  --max-frames 1800

echo "[2/4] merge dataset"
"$PY" /srv/smart-center/current/scripts/merge_door_datasets.py \
  --output "$DS_V9" \
  --inputs "$DS_V8" "$DS_BACKLIGHT"

RUN="door_cls_daymix_v9_backlight_$(date +%Y%m%d_%H%M)"
RUN_ROOT="/srv/smart-center-data/runtime/door_retrain_runs/$RUN"
OUT_MODEL="$RUN_ROOT/door_state_cls_v9.pt"
mkdir -p "$RUN_ROOT"
echo "$RUN" > /srv/smart-center-data/runtime/door_retrain_runs/current_v9_run.txt

echo "[3/4] train: $RUN"
"$PY" /srv/smart-center/current/scripts/train_door_cls_from_dataset.py \
  --dataset-root "$DS_V9" \
  --output "$OUT_MODEL" \
  --run-name "$RUN" \
  --epochs 16 \
  --imgsz 640 \
  --batch 48 \
  --device 0 | tee "$RUN_ROOT/train_launcher.log"

echo "[4/4] deploy + reload"
cp -f /srv/smart-center/models/door_state_cls.pt "/srv/smart-center/models/door_state_cls.pt.bak_$(date +%Y%m%d_%H%M%S)"
cp -f "$OUT_MODEL" /srv/smart-center/models/door_state_cls.pt

python3 - <<'PY'
import urllib.request
req = urllib.request.Request("http://127.0.0.1:18080/reload_models", method="POST")
print(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore"))
print(urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=10).read().decode("utf-8", "ignore"))
PY

echo "RUN=$RUN"
echo "OUT_MODEL=$OUT_MODEL"

