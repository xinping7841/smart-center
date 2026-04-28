import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError


DEFAULT_BASE_URL = "http://192.168.50.121:8123"
UNAVAILABLE_STATES = {"", "unknown", "unavailable", "none", "null"}


def _now_iso():
    return datetime.now().isoformat()


def _safe_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _bool_state(value):
    return str(value or "").strip().lower() in {"on", "true", "1", "heat", "cool", "auto", "dry", "fan_only"}


def _parse_ha_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _entity_domain(entity_id):
    return str(entity_id or "").split(".", 1)[0].strip().lower()


def _global_ha_cfg(config):
    if not isinstance(config, dict):
        return {}
    raw = config.get("home_assistant", {})
    return raw if isinstance(raw, dict) else {}


def merge_ha_cfg(device_cfg, config=None):
    merged = {
        "enabled": True,
        "base_url": DEFAULT_BASE_URL,
        "token": "",
        "timeout_sec": 5,
        "verify_ssl": True,
        "entity_id": "",
        "entities": {},
        "attribute_map": {},
        "stale_after_sec": 7200,
    }
    for source in (_global_ha_cfg(config), device_cfg.get("home_assistant", {}) if isinstance(device_cfg, dict) else {}):
        if isinstance(source, dict):
            for key, value in source.items():
                if key in {"entities", "attribute_map"} and isinstance(value, dict):
                    merged[key].update(value)
                elif key in {"token", "base_url", "entity_id"} and str(value or "").strip() == "":
                    continue
                else:
                    merged[key] = value
    if isinstance(device_cfg, dict):
        for key in ("base_url", "token", "entity_id"):
            if str(device_cfg.get(key) or "").strip():
                merged[key] = device_cfg.get(key)
    merged["base_url"] = str(merged.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    merged["token"] = str(merged.get("token") or "").strip()
    try:
        merged["timeout_sec"] = max(1, min(int(merged.get("timeout_sec") or 5), 30))
    except Exception:
        merged["timeout_sec"] = 5
    try:
        merged["stale_after_sec"] = max(30, int(merged.get("stale_after_sec") or 7200))
    except Exception:
        merged["stale_after_sec"] = 7200
    merged["verify_ssl"] = bool(merged.get("verify_ssl", True))
    merged["enabled"] = bool(merged.get("enabled", True))
    return merged


def _request_json(ha_cfg, path, method="GET", payload=None):
    if not ha_cfg.get("enabled", True):
        raise RuntimeError("home assistant bridge disabled")
    token = str(ha_cfg.get("token") or "").strip()
    if not token:
        raise RuntimeError("missing Home Assistant long-lived access token")
    base_url = str(ha_cfg.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    url = f"{base_url}{path}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    context = None
    if not bool(ha_cfg.get("verify_ssl", True)):
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=int(ha_cfg.get("timeout_sec") or 5), context=context) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else None


def fetch_state(entity_id, ha_cfg):
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        raise ValueError("missing Home Assistant entity_id")
    quoted = urllib.parse.quote(entity_id, safe=".")
    return _request_json(ha_cfg, f"/api/states/{quoted}")


def fetch_states(ha_cfg):
    return _request_json(ha_cfg, "/api/states")


def call_service(ha_cfg, domain, service, service_data):
    domain = str(domain or "").strip().lower()
    service = str(service or "").strip().lower()
    if not domain or not service:
        raise ValueError("missing Home Assistant service domain or service")
    return _request_json(ha_cfg, f"/api/services/{domain}/{service}", method="POST", payload=service_data or {})


def _state_is_online(state):
    value = str((state or {}).get("state") or "").strip().lower()
    return value not in UNAVAILABLE_STATES


def _state_age_sec(state):
    updated = _parse_ha_timestamp((state or {}).get("last_updated") or (state or {}).get("last_changed"))
    if not updated:
        return None
    return max(0, int((datetime.now() - updated).total_seconds()))


def _state_should_ignore_staleness(entity_id):
    return _entity_domain(entity_id) in {"binary_sensor", "event", "lock"}


def _read_numeric_from_state(state, attr_name=""):
    attrs = (state or {}).get("attributes") or {}
    attr_name = str(attr_name or "").strip()
    if attr_name and attr_name in attrs:
        return _safe_float(attrs.get(attr_name))
    return _safe_float((state or {}).get("state"))


def _read_text_from_state(state, attr_name=""):
    attrs = (state or {}).get("attributes") or {}
    attr_name = str(attr_name or "").strip()
    if attr_name and attr_name in attrs:
        value = attrs.get(attr_name)
    else:
        value = (state or {}).get("state")
    if value in (None, ""):
        return None
    return str(value)


def _read_bool_like_from_state(state, attr_name=""):
    text = str(_read_text_from_state(state, attr_name) or "").strip().lower()
    if text in {"on", "open", "opening", "true", "1", "打开", "强", "亮"}:
        return True
    if text in {"off", "closed", "close", "false", "0", "关闭", "弱", "暗"}:
        return False
    return None


def _format_contact_text(value, bool_value=None):
    text = str(value or "").strip()
    lower = text.lower()
    if lower in {"on", "open", "opening", "true", "1"}:
        return "打开"
    if lower in {"off", "closed", "close", "false", "0"}:
        return "关闭"
    if text:
        return text
    if bool_value is None:
        return None
    return "打开" if bool_value else "关闭"


def _format_light_text(value, bool_value=None):
    text = str(value or "").strip()
    lower = text.lower()
    if lower in {"on", "strong", "high", "bright", "true", "1"}:
        return "强"
    if lower in {"off", "weak", "low", "dark", "false", "0"}:
        return "弱"
    if text:
        return text
    if bool_value is None:
        return None
    return "强" if bool_value else "弱"


def get_env_state(sensor_cfg, config=None):
    ha_cfg = merge_ha_cfg(sensor_cfg or {}, config)
    state = {
        "online": False,
        "temp": 0,
        "hum": 0,
        "lux": 0,
        "noise": 0,
        "pm25": 0,
        "pm10": 0,
        "pressure": 0,
        "updated_at": _now_iso(),
    }
    try:
        entities = ha_cfg.get("entities") if isinstance(ha_cfg.get("entities"), dict) else {}
        attribute_map = ha_cfg.get("attribute_map") if isinstance(ha_cfg.get("attribute_map"), dict) else {}
        any_online = False
        max_age = None
        ignore_staleness = False

        if entities:
            for status_key, entity_id in entities.items():
                status_key = str(status_key or "").strip()
                if not status_key:
                    continue
                ha_state = fetch_state(entity_id, ha_cfg)
                online = _state_is_online(ha_state)
                any_online = any_online or online
                if _state_should_ignore_staleness(entity_id):
                    ignore_staleness = True
                age = _state_age_sec(ha_state)
                if age is not None:
                    max_age = age if max_age is None else max(max_age, age)
                if status_key in {"contact", "light"}:
                    bool_value = _read_bool_like_from_state(ha_state, attribute_map.get(status_key, ""))
                    raw_text = _read_text_from_state(ha_state, attribute_map.get(status_key, ""))
                    text_value = _format_contact_text(raw_text, bool_value) if status_key == "contact" else _format_light_text(raw_text, bool_value)
                    if bool_value is not None:
                        state[status_key] = bool_value
                        if status_key == "contact":
                            state["opening"] = bool_value
                    if text_value is not None:
                        state[f"{status_key}_text"] = text_value
                    continue
                value = _read_numeric_from_state(ha_state, attribute_map.get(status_key, ""))
                if value is not None:
                    state[status_key] = value
        else:
            ha_state = fetch_state(ha_cfg.get("entity_id"), ha_cfg)
            any_online = _state_is_online(ha_state)
            max_age = _state_age_sec(ha_state)
            attrs = (ha_state or {}).get("attributes") or {}
            default_map = {
                "temp": "temperature",
                "hum": "humidity",
                "lux": "illuminance",
                "noise": "noise",
                "pm25": "pm25",
                "pm10": "pm10",
                "pressure": "pressure",
                "battery": "battery",
                "linkquality": "linkquality",
            }
            default_map.update(attribute_map)
            for status_key, attr_name in default_map.items():
                value = _safe_float(attrs.get(attr_name))
                if value is not None:
                    state[status_key] = value
            if _entity_domain((ha_state or {}).get("entity_id")) == "sensor":
                value = _safe_float((ha_state or {}).get("state"))
                if value is not None and not any(key in state and state.get(key) for key in ("temp", "hum", "lux")):
                    state["temp"] = value

        if "contact" not in state and "opening" in state:
            state["contact"] = bool(state.get("opening"))
        if "contact" in state and "contact_text" not in state:
            state["contact_text"] = "打开" if state.get("contact") else "关闭"
        if "light" in state and "light_text" not in state:
            state["light_text"] = "强" if state.get("light") else "弱"
        state["age_sec"] = max_age
        state["online"] = bool(any_online) and (ignore_staleness or max_age is None or max_age <= int(ha_cfg.get("stale_after_sec") or 7200))
    except Exception as exc:
        state["online"] = False
        state["error"] = str(exc)
    return state


def get_env_debug(sensor_cfg, config=None):
    ha_cfg = merge_ha_cfg(sensor_cfg or {}, config)
    masked = dict(ha_cfg)
    if masked.get("token"):
        masked["token"] = "***"
    payload = {"bridge": masked, "state": None}
    try:
        payload["state"] = get_env_state(sensor_cfg or {}, config)
        payload["success"] = True
    except Exception as exc:
        payload["success"] = False
        payload["error"] = str(exc)
    return payload


def get_hvac_status(device_cfg, config=None):
    ha_cfg = merge_ha_cfg(device_cfg or {}, config)
    entity_id = str(ha_cfg.get("entity_id") or "").strip()
    payload = {
        "id": str((device_cfg or {}).get("id") or ""),
        "name": str((device_cfg or {}).get("name") or entity_id or "Home Assistant HVAC"),
        "protocol": "home_assistant",
        "entity_id": entity_id,
        "online": False,
        "power": False,
        "temp": None,
        "target_temp": None,
        "mode": "off",
        "updated_at": _now_iso(),
    }
    try:
        ha_state = fetch_state(entity_id, ha_cfg)
        attrs = (ha_state or {}).get("attributes") or {}
        state_value = str((ha_state or {}).get("state") or "").strip().lower()
        hvac_modes = attrs.get("hvac_modes")
        fan_modes = attrs.get("fan_modes")
        payload.update(
            {
                "online": _state_is_online(ha_state),
                "power": _bool_state(state_value),
                "mode": state_value or "unknown",
                "fan_speed": attrs.get("fan_mode") or attrs.get("fan_speed") or "unknown",
                "hvac_modes": [str(item) for item in hvac_modes] if isinstance(hvac_modes, (list, tuple, set)) else [],
                "fan_modes": [str(item) for item in fan_modes] if isinstance(fan_modes, (list, tuple, set)) else [],
                "min_temp": _safe_float(attrs.get("min_temp")),
                "max_temp": _safe_float(attrs.get("max_temp")),
                "target_temp_step": _safe_float(attrs.get("target_temp_step") or attrs.get("temperature_step")),
                "temperature_unit": attrs.get("temperature_unit"),
                "target_temp": attrs.get("temperature") or attrs.get("target_temperature"),
                "temp": attrs.get("current_temperature") or attrs.get("temperature"),
                "hvac_action": attrs.get("hvac_action"),
                "updated_at": (ha_state or {}).get("last_updated") or _now_iso(),
                "age_sec": _state_age_sec(ha_state),
            }
        )
        power_entity = str((device_cfg or {}).get("power_sensor_entity_id") or "").strip()
        if power_entity:
            power_state = fetch_state(power_entity, ha_cfg)
            power_w = _safe_float((power_state or {}).get("state"))
            if power_w is not None:
                payload["electric_power_w"] = power_w
                payload["electric_power_kw"] = round(power_w / 1000.0, 4)
                payload["power_sensor_entity_id"] = power_entity
    except Exception as exc:
        payload["online"] = False
        payload["error"] = str(exc)
    return payload


def control_hvac(device_cfg, action, config=None, **kwargs):
    ha_cfg = merge_ha_cfg(device_cfg or {}, config)
    entity_id = str(ha_cfg.get("entity_id") or "").strip()
    domain = _entity_domain(entity_id) or "homeassistant"
    action = str(action or "").strip().lower()
    service_data = {"entity_id": entity_id}

    if action == "power_on":
        service = "turn_on"
    elif action == "power_off":
        service = "turn_off"
    elif action == "set_temp":
        service = "set_temperature"
        domain = "climate"
        service_data["temperature"] = kwargs.get("temperature")
    elif action == "set_mode":
        service = "set_hvac_mode"
        domain = "climate"
        service_data["hvac_mode"] = kwargs.get("mode")
    else:
        raise RuntimeError(f"unsupported action: {action}")

    result = call_service(ha_cfg, domain, service, service_data)
    return True, result, "home_assistant"
