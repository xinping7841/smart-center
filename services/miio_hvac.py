# AI_MODULE: miio_hvac_adapter
# AI_PURPOSE: Normalize Xiaomi/MIIO HVAC device attributes and command results into Smart Center HVAC status fields.
# AI_BOUNDARY: Home Assistant and API routing live elsewhere; this adapter should not own dashboard rendering or permission checks.
# AI_DATA_FLOW: python-miio device objects/results -> normalized power/mode/temp/fan/swing status dictionaries.
# AI_RUNTIME: Used by HVAC polling/control helpers when MIIO-backed air conditioners are configured.
# AI_RISK: Medium. Bad normalization causes stale/offline or wrong HVAC state, but execution must still pass backend controls.
# AI_COMPAT: Preserve status keys consumed by api/hvac.py and static/js/views/hvac-view.js.
# AI_SEARCH_KEYWORDS: miio, xiaomi, hvac, air conditioner, normalize, HA freshness.
from datetime import datetime
from log_config import get_logger

_log = get_logger(__name__)



def _now_iso():
    return datetime.now().isoformat()


def _bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    lowered = str(value or "").strip().lower()
    return lowered in {"on", "true", "1", "open", "enabled"}


def _pick_attr(obj, names, default=None):
    for name in names:
        if hasattr(obj, name):
            try:
                value = getattr(obj, name)
                if callable(value):
                    value = value()
                if value is not None:
                    return value
            except Exception:
                _log.debug("non-critical error suppressed", exc_info=True)
                pass
        if isinstance(obj, dict) and name in obj and obj.get(name) is not None:
            return obj.get(name)
    return default


class MiioHVACService:
    def __init__(self):
        self._miio = None
        self._load_error = ""
        self._load_library()

    def _load_library(self):
        try:
            import miio  # type: ignore
            self._miio = miio
            self._load_error = ""
        except Exception as exc:
            self._miio = None
            self._load_error = str(exc)

    def is_available(self):
        if self._miio is None:
            self._load_library()
        return self._miio is not None

    def _device_candidates(self):
        if not self.is_available():
            return []
        miio = self._miio
        candidates = []
        for name in [
            "AirConditioningCompanion",
            "AirConditionerCompanion",
            "AirConditioningCompanionV3",
            "MiotDevice",
            "Device",
        ]:
            cls = getattr(miio, name, None)
            if cls:
                candidates.append((name, cls))
        return candidates

    def _build_device(self, cfg):
        if not self.is_available():
            raise RuntimeError(f"python-miio unavailable: {self._load_error}")

        ip = str(cfg.get("ip") or "").strip()
        token = str(cfg.get("token") or cfg.get("miio_token") or "").strip()
        if not ip or not token:
            raise ValueError("missing ip or token")

        last_error = None
        for class_name, cls in self._device_candidates():
            try:
                return class_name, cls(ip, token)
            except TypeError:
                try:
                    return class_name, cls(ip=ip, token=token)
                except Exception as exc:
                    last_error = exc
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"unable to create miio device: {last_error}")

    def _normalize_status(self, cfg, raw):
        target_temp = _pick_attr(raw, ["target_temperature", "target_temp", "temperature", "temp"])
        room_temp = _pick_attr(raw, ["temperature", "current_temperature", "indoor_temperature", "temp"])
        mode = _pick_attr(raw, ["mode", "operation_mode", "ac_mode"], "unknown")
        fan_speed = _pick_attr(raw, ["fan_speed", "speed", "fan_level"], "unknown")
        power = _pick_attr(raw, ["power", "is_on", "on"], False)
        load_power = _pick_attr(raw, ["load_power", "power_consumption", "power_w"], None)

        return {
            "id": str(cfg.get("id")),
            "name": str(cfg.get("name") or cfg.get("id") or "Miio HVAC"),
            "protocol": "miio",
            "class_name": _pick_attr(raw, ["__class__"], ""),
            "online": True,
            "power": _bool_value(power),
            "mode": str(mode or "unknown"),
            "fan_speed": str(fan_speed or "unknown"),
            "target_temp": target_temp,
            "temp": room_temp,
            "load_power": load_power,
            "updated_at": _now_iso(),
        }

    def get_status(self, cfg):
        class_name, device = self._build_device(cfg)
        try:
            status = None
            for method_name in ["status", "get_status"]:
                method = getattr(device, method_name, None)
                if callable(method):
                    status = method()
                    break
            if status is None:
                raise RuntimeError("device does not expose status/get_status")

            normalized = self._normalize_status(cfg, status)
            normalized["driver_class"] = class_name
            return normalized
        except Exception as exc:
            return {
                "id": str(cfg.get("id")),
                "name": str(cfg.get("name") or cfg.get("id") or "Miio HVAC"),
                "protocol": "miio",
                "online": False,
                "error": str(exc),
                "updated_at": _now_iso(),
            }

    def control(self, cfg, action, **kwargs):
        class_name, device = self._build_device(cfg)
        try:
            if action == "power_on":
                for method_name in ["on", "power_on"]:
                    method = getattr(device, method_name, None)
                    if callable(method):
                        result = method()
                        return True, result, class_name
                raise RuntimeError("device does not support power_on")

            if action == "power_off":
                for method_name in ["off", "power_off"]:
                    method = getattr(device, method_name, None)
                    if callable(method):
                        result = method()
                        return True, result, class_name
                raise RuntimeError("device does not support power_off")

            if action == "set_temp":
                target = kwargs.get("temperature")
                for method_name in ["set_target_temperature", "set_temperature"]:
                    method = getattr(device, method_name, None)
                    if callable(method):
                        result = method(int(float(target)))
                        return True, result, class_name
                raise RuntimeError("device does not support set temperature")

            if action == "set_mode":
                mode = kwargs.get("mode")
                for method_name in ["set_mode"]:
                    method = getattr(device, method_name, None)
                    if callable(method):
                        result = method(str(mode))
                        return True, result, class_name
                raise RuntimeError("device does not support set mode")

            raise RuntimeError(f"unsupported action: {action}")
        except Exception as exc:
            return False, str(exc), class_name


miio_hvac_service = MiioHVACService()
