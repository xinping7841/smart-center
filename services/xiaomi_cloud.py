from typing import Any, Dict, List, Optional


def fetch_xiaomi_cloud_devices(username: str, password: str, locale: Optional[str] = None) -> List[Dict[str, Any]]:
    from miio.cloud import CloudInterface

    ci = CloudInterface(username=username, password=password)
    devices = ci.get_devices(locale=None if locale in [None, "", "all"] else locale)
    rows: List[Dict[str, Any]] = []
    for dev in devices.values():
        rows.append(
            {
                "did": str(getattr(dev, "did", "") or ""),
                "token": str(getattr(dev, "token", "") or ""),
                "name": str(getattr(dev, "name", "") or ""),
                "model": str(getattr(dev, "model", "") or ""),
                "ip": str(getattr(dev, "ip", "") or ""),
                "description": str(getattr(dev, "description", "") or ""),
                "parent_id": str(getattr(dev, "parent_id", "") or ""),
                "ssid": str(getattr(dev, "ssid", "") or ""),
                "mac": str(getattr(dev, "mac", "") or ""),
                "locale": list(getattr(dev, "locale", []) or []),
            }
        )
    return rows


def filter_xiaomi_devices(
    devices: List[Dict[str, Any]],
    ip: str = "",
    model: str = "",
    keyword: str = "",
) -> List[Dict[str, Any]]:
    target_ip = str(ip or "").strip().lower()
    target_model = str(model or "").strip().lower()
    target_keyword = str(keyword or "").strip().lower()

    filtered: List[Dict[str, Any]] = []
    for item in devices:
        item_ip = str(item.get("ip") or "").strip().lower()
        item_model = str(item.get("model") or "").strip().lower()
        item_name = str(item.get("name") or "").strip().lower()
        item_desc = str(item.get("description") or "").strip().lower()

        if target_ip and item_ip != target_ip:
            continue
        if target_model and target_model not in item_model:
            continue
        if target_keyword and target_keyword not in item_name and target_keyword not in item_desc and target_keyword not in item_model:
            continue
        filtered.append(item)
    return filtered
