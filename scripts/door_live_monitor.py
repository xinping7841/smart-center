#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import json
import sys
import time
import urllib.request


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: door_live_monitor.py <out_csv> [duration_sec]")
        return 2
    out_csv = sys.argv[1]
    duration_sec = int(sys.argv[2]) if len(sys.argv) >= 3 else 1800
    end_ts = time.time() + duration_sec
    url = "http://127.0.0.1:6899/api/door/vision_status"

    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("ts,stable,candidate,door_status,confidence,main,main_conf,aux,aux_conf\n")
        while time.time() < end_ts:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            try:
                with urllib.request.urlopen(url, timeout=1.5) as resp:
                    payload = json.loads(resp.read().decode("utf-8", "ignore"))
                vr = payload.get("vision_runtime", {}) or {}
                votes = payload.get("camera_votes", {}) or {}
                main = votes.get("main", {}) or {}
                aux = votes.get("aux", {}) or {}
                row = [
                    ts,
                    str(vr.get("stable_state")),
                    str(vr.get("last_candidate")),
                    str(payload.get("door_status")),
                    str(payload.get("confidence")),
                    str(main.get("status")),
                    str(main.get("confidence")),
                    str(aux.get("status")),
                    str(aux.get("confidence")),
                ]
                f.write(",".join(row) + "\n")
            except Exception as exc:
                f.write(f"{ts},ERR,{exc}\n")
            f.flush()
            time.sleep(0.25)
    print(out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
