import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _ensure_vision(cfg: dict) -> dict:
    door = cfg.setdefault("door_config", {})
    vision = door.setdefault("vision", {})
    defaults = {
        "enabled": False,
        "provider": "legacy",
        "http_url": "http://127.0.0.1:18080/infer/door_state",
        "request_timeout_ms": 700,
        "poll_interval_sec": 0.5,
        "fusion_enabled": True,
        "fusion_settle_frames": 3,
        "fusion_history_size": 8,
        "fusion_min_confidence": 0.55,
        "fusion_margin": 0.15,
        "allow_shared_reference": False,
        "camera_weights": {"main": 1.0, "aux": 1.0},
        "people_count_enabled": False,
        "zone_count_enabled": False,
        "http_send_full_frame": False,
    }
    for k, v in defaults.items():
        vision.setdefault(k, v)
    return vision


def main() -> None:
    parser = argparse.ArgumentParser(description="Set door vision mode in config.json")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--mode", choices=["off", "legacy", "http"], required=True)
    parser.add_argument("--http-url", default=None, help="HTTP model endpoint")
    parser.add_argument("--people", choices=["on", "off"], default=None)
    parser.add_argument("--zone", choices=["on", "off"], default=None)
    args = parser.parse_args()

    path = Path(args.config).resolve()
    cfg = _load_json(path)
    vision = _ensure_vision(cfg)

    if args.mode == "off":
        vision["enabled"] = False
    elif args.mode == "legacy":
        vision["enabled"] = True
        vision["provider"] = "legacy"
    elif args.mode == "http":
        vision["enabled"] = True
        vision["provider"] = "http"

    if args.http_url:
        vision["http_url"] = str(args.http_url)
    if args.people is not None:
        vision["people_count_enabled"] = args.people == "on"
    if args.zone is not None:
        vision["zone_count_enabled"] = args.zone == "on"

    _save_json(path, cfg)
    print("Updated:", path)
    print(json.dumps({"vision": vision}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
