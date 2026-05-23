# Vision Deploy Guide (Ubuntu + 3090)

This guide enables door-state + people detection with low rollout risk.

## 1) Install runtime dependencies

```bash
cd /opt/smart_power_monitor
python3 -m pip install -U pip
python3 -m pip install ultralytics opencv-python-headless numpy
```

## 2) Prepare model files

Put your models at:

- `/opt/models/door_state_cls.pt` (door open/closed model)
- `/opt/models/yolo11n.pt` (person model; replace with your stronger person model later)

## 3) Start vision service (systemd)

```bash
sudo cp deploy/linux/vision-door.service /etc/systemd/system/vision-door.service
sudo systemctl daemon-reload
sudo systemctl enable --now vision-door.service
sudo systemctl status vision-door.service --no-pager
```

Health check:

```bash
curl -sS http://127.0.0.1:18080/infer/door_state -X POST \
  -H 'Content-Type: application/json' \
  -d '{"camera_key":"main","image_b64":"aGVsbG8="}'
```

Expect `invalid_image_b64` on fake payload, proving service is reachable.

## 4) Gray release in main app

Inside app workspace:

```bash
python scripts/set_door_vision_mode.py --mode legacy
```

Observe 30-60 minutes first (still local algorithm, no remote model).

Then switch to HTTP model:

```bash
python scripts/set_door_vision_mode.py --mode http --http-url http://127.0.0.1:18080/infer/door_state
```

Enable people + zones only after door status is stable:

```bash
python scripts/set_door_vision_mode.py --mode http --http-url http://127.0.0.1:18080/infer/door_state --people on --zone on
```

## 5) Rollback

Immediate rollback to existing production behavior:

```bash
python scripts/set_door_vision_mode.py --mode off
```

Optional stop vision service:

```bash
sudo systemctl stop vision-door.service
```

## 6) Tomorrow Checklist (camera rewiring day)

Use this order to minimize business impact:

1. Keep production in legacy mode first:

```bash
python scripts/set_door_vision_mode.py --mode legacy
```

2. Run camera connectivity diagnose:

```bash
python scripts/door_camera_diagnose.py config.json
```

3. Verify both camera streams are online in:

- `GET /api/door/cameras`
- `GET /api/door/vision_status`

4. Re-calibrate each camera (closed/open/apply):

- `POST /api/ai_wizard/capture/closed` with `{"camera_key":"main"}`
- `POST /api/ai_wizard/capture/open` with `{"camera_key":"main"}`
- `POST /api/ai_wizard/apply_model` with `{"camera_key":"main"}`
- Repeat above for `camera_key="aux"`

5. Gray switch to HTTP model:

```bash
python scripts/set_door_vision_mode.py --mode http --http-url http://127.0.0.1:18080/infer/door_state
```

6. Check door inference output:

- `GET /get_door_status`
- `GET /api/door/vision_status`

Expected:

- `engine` should become `vision_fusion`
- `camera_votes` should show `main` and `aux`
- `confidence` should be non-zero when model is stable

7. Enable people/zone only after door state is stable:

```bash
python scripts/set_door_vision_mode.py --mode http --http-url http://127.0.0.1:18080/infer/door_state --people on --zone on
```

8. Configure zones and automation:

- `POST /api/door/vision_zones`
- `GET /api/door/automation_templates`

9. If instability appears, immediate rollback:

```bash
python scripts/set_door_vision_mode.py --mode legacy
```
