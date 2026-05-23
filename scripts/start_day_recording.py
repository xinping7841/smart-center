#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import subprocess
import time
from pathlib import Path


def main() -> int:
    cfg = json.loads(Path("/srv/smart-center-data/config.json").read_text(encoding="utf-8"))
    cams = []
    for c in (cfg.get("door_config", {}).get("cameras", []) or []):
        if not isinstance(c, dict):
            continue
        rtsp = str(c.get("rtsp_url") or "").strip()
        if bool(c.get("enabled", True)) and rtsp:
            cams.append(c)

    ts = time.strftime("%Y%m%d_%H%M%S")
    session = f"door_day_{ts}"
    out_dir = Path("/srv/smart-center-data/runtime/door_recordings") / session
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "session": session,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": {},
        "pids": {},
    }
    for c in cams:
        key = str(c.get("key") or "").strip() or "cam"
        out = str(out_dir / f"{key}.mp4")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            str(c.get("rtsp_url")),
            "-an",
            "-c:v",
            "copy",
            "-t",
            "1800",
            "-y",
            out,
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        meta["files"][key] = out
        meta["pids"][key] = int(p.pid)

    Path("/srv/smart-center-data/runtime/day_recording_active.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
