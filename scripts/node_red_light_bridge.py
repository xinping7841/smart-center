import json
import sys
from pathlib import Path

from paths import CONFIG_FILE as CONFIG_FILE_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from drivers.light_coxe import CoxeLightDriver


DEFAULT_CONFIG_PATH = Path(CONFIG_FILE_PATH)


def load_light_devices(config_path: Path):
    data = json.loads(config_path.read_text(encoding="utf-8"))
    devices = data.get("light_devices") or []
    indexed = {str(item.get("id")): item for item in devices if isinstance(item, dict) and item.get("id") is not None}
    return indexed


def build_result(success: bool, **kwargs):
    payload = {"success": success}
    payload.update(kwargs)
    return payload


def main():
    if len(sys.argv) < 3:
        print(json.dumps(build_result(False, error="usage", message="Usage: python node_red_light_bridge.py <read|write> <device_id> [channel] [state]"), ensure_ascii=False))
        return 1

    action = str(sys.argv[1]).strip().lower()
    device_id = str(sys.argv[2]).strip()
    config_path = DEFAULT_CONFIG_PATH

    try:
        devices = load_light_devices(config_path)
    except Exception as exc:
        print(json.dumps(build_result(False, error="config_load_failed", message=str(exc), config_path=str(config_path)), ensure_ascii=False))
        return 2

    if device_id not in devices:
        print(json.dumps(build_result(False, error="device_not_found", message=f"light device {device_id} not found"), ensure_ascii=False))
        return 3

    config = dict(devices[device_id])
    driver = CoxeLightDriver(config)

    try:
        if action == "read":
            result = driver.read_status()
            print(json.dumps(build_result(True, action="read", device_id=config.get("id"), name=config.get("name"), result=result), ensure_ascii=False))
            return 0

        if action == "write":
            if len(sys.argv) < 5:
                print(json.dumps(build_result(False, error="usage", message="write requires channel and state"), ensure_ascii=False))
                return 4
            channel = int(sys.argv[3])
            raw_state = str(sys.argv[4]).strip().lower()
            is_open = raw_state in {"1", "true", "on", "open"}
            success = driver.control_channel(channel, is_open)
            verify = driver.read_status()
            print(json.dumps(build_result(success, action="write", device_id=config.get("id"), name=config.get("name"), channel=channel, is_open=is_open, verify=verify), ensure_ascii=False))
            return 0 if success else 5

        print(json.dumps(build_result(False, error="invalid_action", message=f"unsupported action: {action}"), ensure_ascii=False))
        return 6
    except Exception as exc:
        print(json.dumps(build_result(False, error="driver_failed", message=str(exc), action=action, device_id=config.get("id"), name=config.get("name")), ensure_ascii=False))
        return 7
    finally:
        try:
            driver.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
