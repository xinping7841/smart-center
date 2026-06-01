#!/usr/bin/env bash
set -euo pipefail

echo "service_active=$(sudo -n systemctl is-active smart-center.service)"
echo "current=$(sudo -n readlink -f /srv/smart-center/current)"
if [ -f /srv/smart-center/current/REVISION ]; then
  echo "revision=$(sudo -n cat /srv/smart-center/current/REVISION)"
fi

python3 - <<'PY'
import gzip
import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:6899"
paths = [
    "/api/env/status",
    "/api/env/status?history=1",
    "/api/hvac/status",
    "/api/machines?detail=compact",
    "/api/machines?detail=full",
]
for path in paths:
    t0 = time.perf_counter()
    with urllib.request.urlopen(BASE + path, timeout=8) as resp:
        body = resp.read()
        status = resp.status
    dt_ms = (time.perf_counter() - t0) * 1000
    print(f"api path={path} status={status} ms={dt_ms:.1f} bytes={len(body)}")
    try:
        payload = json.loads(body.decode("utf-8", "ignore"))
        if path.startswith("/api/machines"):
            print(f"  machines={len(payload) if isinstance(payload, list) else 'n/a'}")
            if isinstance(payload, list) and payload:
                st = payload[0].get("status") or {}
                print(f"  sample_status_keys={','.join(sorted(st.keys())[:12])}")
        elif path.startswith("/api/env/status"):
            print(f"  sensors={len(payload) if isinstance(payload, dict) else 'n/a'}")
            if isinstance(payload, dict) and payload:
                first = next(iter(payload.values()))
                print(f"  has_lux_history={'lux_history' in first}")
        elif path.startswith("/api/hvac/status"):
            print(f"  hvac={len(payload) if isinstance(payload, dict) else 'n/a'}")
    except Exception as exc:
        print(f"  json_error={exc}")

for rel in ("static/css/generated/hvac.css.gz", "static/css/generated/dashboard.css.gz"):
    p = Path("/srv/smart-center/current") / rel
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        text = fh.read()
    print(f"asset {rel} ok bytes={p.stat().st_size} hvac_power_key={'hvac-power-key' in text} dashboard_hvac_power={'dashboard-hvac-power' in text}")
PY
