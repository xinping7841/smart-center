#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import signal
from pathlib import Path


def main() -> int:
    p = Path("/srv/smart-center-data/runtime/day_recording_active.json")
    if not p.exists():
        print('{"status":"ok","msg":"no_active_recording"}')
        return 0
    d = json.loads(p.read_text(encoding="utf-8"))
    pids = (d.get("pids", {}) or {}).values()
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    d["stopped_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "session": d.get("session"), "files": d.get("files", {})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
