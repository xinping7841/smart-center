# Door Vision Service Protocol

This module documents the HTTP protocol used by `api/door.py` when `door_config.vision.enabled=true` and `provider=http`.

## Endpoint

- `POST /infer/door_state`

## Request JSON

```json
{
  "camera_key": "main",
  "image_b64": "<base64-jpeg>",
  "send_full_frame": false
}
```

## Response JSON

```json
{
  "camera_key": "main",
  "status": "open",
  "confidence": 0.91,
  "diff_c": 123.0,
  "diff_o": 456.0,
  "people_count": 2,
  "zone_counts": {
    "gate_in": 1,
    "gate_out": 1
  }
}
```

Fields consumed by the current system:

- `status`: `open | closed | unknown`
- `confidence`: `0.0 ~ 1.0`
- `people_count`: integer
- `zone_counts`: object of `zone_name -> count`

`diff_c` and `diff_o` are optional compatibility metrics; keep as `0.0` if unavailable.

## Quick Start (Stub)

```bash
python runtime/door_probe/vision_service_stub.py
```

Then set:

- `door_config.vision.enabled = true`
- `door_config.vision.provider = "http"`
- `door_config.vision.http_url = "http://127.0.0.1:18080/infer/door_state"`

The stub returns `unknown` by default. Replace model logic in `vision_service_stub.py`.

## Quick Start (Ultralytics)

1. Install dependencies on Ubuntu runtime:

```bash
pip install ultralytics opencv-python-headless numpy
```

2. Set model paths and launch service:

```bash
export DOOR_MODEL_PATH=/opt/models/door_state_cls.pt
export PERSON_MODEL_PATH=/opt/models/yolo11n.pt
export MODEL_DEVICE=cuda:0
export MODEL_IMGSZ=640
export DOOR_OPEN_LABELS=open,opened,door_open
export DOOR_CLOSED_LABELS=closed,close,door_closed
python runtime/door_probe/vision_service_ultralytics.py
```

3. Enable in main system config:

- `door_config.vision.enabled = true`
- `door_config.vision.provider = "http"`
- `door_config.vision.http_url = "http://127.0.0.1:18080/infer/door_state"`
- `door_config.vision.fusion_enabled = true`

Recommended gray-release order:

1. `enabled=true`, keep provider `legacy` for 30-60 min observation.
2. Switch provider to `http` for one camera window (off-peak).
3. Enable `people_count_enabled` and `zone_count_enabled` after door status is stable.

## Per-camera Calibration (Recommended)

Capture per-camera references:

1. Keep camera at fully closed state, call:
`POST /api/ai_wizard/capture/closed` with JSON `{"camera_key":"main"}`
2. Keep camera at fully open state, call:
`POST /api/ai_wizard/capture/open` with JSON `{"camera_key":"main"}`
3. Apply threshold:
`POST /api/ai_wizard/apply_model` with JSON `{"camera_key":"main"}`
4. Repeat for `aux`.

The system will save:

- `door_ref_closed_main.jpg`, `door_ref_open_main.jpg`
- `door_ref_closed_aux.jpg`, `door_ref_open_aux.jpg`

And maintain camera-specific thresholds in:

- `door_config.match_thresholds.main`
- `door_config.match_thresholds.aux`

## Zone Config API

Update per-camera zones (normalized points in range `0.0~1.0`):

- `POST /api/door/vision_zones`

Request example:

```json
{
  "camera_key": "main",
  "zones": {
    "gate_in": [[0.1, 0.2], [0.4, 0.2], [0.4, 0.8], [0.1, 0.8]],
    "gate_out": [[0.6, 0.2], [0.9, 0.2], [0.9, 0.8], [0.6, 0.8]]
  }
}
```

Automation template API:

- `GET /api/door/automation_templates`

Static template file:

- `runtime/door_probe/automation_rule_templates.json`
