import argparse
import json
import sys


def safe_getattr(obj, name, default=None):
    try:
        value = getattr(obj, name)
        if callable(value):
            return value()
        return value
    except Exception:
        return default


def main():
    parser = argparse.ArgumentParser(description="Probe Xiaomi miio HVAC/AC companion device by IP and token.")
    parser.add_argument("--ip", required=True, help="Device IP address")
    parser.add_argument("--token", required=True, help="32-char miio token")
    args = parser.parse_args()

    try:
        import miio
    except Exception as exc:
        print(json.dumps({"success": False, "stage": "import", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    result = {
        "success": False,
        "ip": args.ip,
        "token_length": len(args.token or ""),
        "miio_version": getattr(miio, "__version__", "unknown"),
        "candidates": [],
    }

    candidates = []
    for name in ["AirConditioningCompanion", "MiotDevice", "Device"]:
        cls = getattr(miio, name, None)
        if cls:
            candidates.append((name, cls))

    for class_name, cls in candidates:
        item = {"class_name": class_name}
        try:
            try:
                device = cls(args.ip, args.token)
            except TypeError:
                device = cls(ip=args.ip, token=args.token)

            info = None
            status = None

            for method_name in ["info"]:
                method = getattr(device, method_name, None)
                if callable(method):
                    try:
                        info = method()
                        break
                    except Exception as exc:
                        item["info_error"] = str(exc)

            for method_name in ["status", "get_status"]:
                method = getattr(device, method_name, None)
                if callable(method):
                    try:
                        status = method()
                        break
                    except Exception as exc:
                        item["status_error"] = str(exc)

            if info is not None:
                item["info"] = {
                    "model": safe_getattr(info, "model"),
                    "mac": safe_getattr(info, "mac_address") or safe_getattr(info, "mac"),
                    "firmware": safe_getattr(info, "firmware_version") or safe_getattr(info, "fw_ver"),
                    "hardware": safe_getattr(info, "hardware_version") or safe_getattr(info, "hw_ver"),
                    "raw": str(info),
                }
            if status is not None:
                item["status"] = str(status)

            item["ok"] = info is not None or status is not None
        except Exception as exc:
            item["ok"] = False
            item["error"] = str(exc)

        result["candidates"].append(item)

    result["success"] = any(item.get("ok") for item in result["candidates"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
