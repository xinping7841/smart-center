#!/usr/bin/env bash
set -euo pipefail

echo "HOST=$(hostname)"
echo "TIME=$(date '+%F %T %z')"
python3 - <<'PY'
import json, urllib.request
u = "http://127.0.0.1:6899/api/door/vision_status"
d = json.loads(urllib.request.urlopen(u, timeout=3).read().decode("utf-8", "ignore"))
vr = d.get("vision_runtime", {}) or {}
print({
    "door_status": d.get("door_status"),
    "stable": vr.get("stable_state"),
    "candidate": vr.get("last_candidate"),
    "confidence": d.get("confidence"),
})
PY

