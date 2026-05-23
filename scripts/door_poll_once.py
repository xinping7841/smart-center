#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import time
import urllib.request


def main() -> int:
    url = "http://127.0.0.1:6899/api/door/vision_status"
    for i in range(12):
        with urllib.request.urlopen(url, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        vr = payload.get("vision_runtime", {}) or {}
        print(
            i,
            "stable=", vr.get("stable_state"),
            "cand=", vr.get("last_candidate"),
            "door=", payload.get("door_status"),
            "conf=", payload.get("confidence"),
        )
        time.sleep(0.4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
