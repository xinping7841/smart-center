import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _probe_rtsp(rtsp_url: str, timeout_sec: float = 2.0):
    rtsp_url = str(rtsp_url or "").strip()
    if not rtsp_url:
        return False, "missing_rtsp"
    try:
        parsed = urlsplit(rtsp_url)
    except Exception as exc:
        return False, f"url_parse_error:{exc}"
    host = parsed.hostname
    port = parsed.port or 554
    if not host:
        return False, "missing_host"
    try:
        sock = socket.create_connection((host, int(port)), timeout=max(float(timeout_sec), 0.2))
        sock.close()
        return True, "ok"
    except Exception as exc:
        return False, f"connect_failed:{exc}"


def main():
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("config.json").resolve()
    cfg = _load_config(config_path)
    door_cfg = cfg.get("door_config", {}) if isinstance(cfg.get("door_config"), dict) else {}
    cameras = door_cfg.get("cameras", []) if isinstance(door_cfg.get("cameras"), list) else []
    if not cameras:
        print("No cameras configured.")
        return 1

    print(f"Config: {config_path}")
    print("=== Door Camera Diagnose ===")
    failed = 0
    for item in cameras:
        key = str(item.get("key") or "").strip()
        name = str(item.get("name") or key).strip()
        enabled = bool(item.get("enabled", True))
        host = str(item.get("host") or "").strip()
        rtsp = str(item.get("rtsp_url") or "").strip()
        ok, detail = _probe_rtsp(rtsp)
        if enabled and not ok:
            failed += 1
        print(
            json.dumps(
                {
                    "camera_key": key,
                    "name": name,
                    "enabled": enabled,
                    "host": host,
                    "rtsp_configured": bool(rtsp),
                    "probe_ok": ok,
                    "probe_detail": detail,
                },
                ensure_ascii=False,
            )
        )
    print(f"Failed enabled cameras: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
