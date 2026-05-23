import json
import threading
import time
from copy import deepcopy
from datetime import datetime

from data_logger import add_log


DEFAULT_MQTT_ENV = {
    "host": "127.0.0.1",
    "port": 1883,
    "username": "",
    "password": "",
    "topic": "",
    "availability_topic": "",
    "client_id": "",
    "keepalive": 60,
    "qos": 0,
    "stale_after_sec": 7200,
    "tls": False,
    "field_map": {
        "temp": "temperature",
        "hum": "humidity",
        "pressure": "pressure",
        "lux": "illuminance",
        "noise": "noise",
        "pm25": "pm25",
        "pm10": "pm10",
    },
}

_EMPTY_STATE = {
    "online": False,
    "temp": 0,
    "hum": 0,
    "lux": 0,
    "noise": 0,
    "pm25": 0,
    "pm10": 0,
    "pressure": 0,
}

_SENSOR_CLIENTS = {}
_LOCK = threading.Lock()


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _iso_now():
    return datetime.now().isoformat()


def _merge_mqtt_cfg(sensor_cfg):
    merged = deepcopy(DEFAULT_MQTT_ENV)
    extra = sensor_cfg.get("mqtt", {})
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key == "field_map" and isinstance(value, dict):
                merged["field_map"].update(value)
            else:
                merged[key] = value
    for key in ["host", "port", "username", "password", "topic", "availability_topic", "client_id", "keepalive", "qos", "stale_after_sec", "tls"]:
        if key in sensor_cfg and sensor_cfg.get(key) not in [None, ""]:
            merged[key] = sensor_cfg.get(key)
    if isinstance(sensor_cfg.get("field_map"), dict):
        merged["field_map"].update(sensor_cfg["field_map"])
    return merged


class _SensorMqttClient:
    def __init__(self, sensor_cfg):
        self.sensor_id = str(sensor_cfg.get("id"))
        self.name = str(sensor_cfg.get("name") or self.sensor_id)
        self.cfg = _merge_mqtt_cfg(sensor_cfg)
        self.client = None
        self.running = False
        self.connected = False
        self.error = ""
        self.last_payload = None
        self.last_message_at = 0.0
        self.last_availability = ""
        self.state = deepcopy(_EMPTY_STATE)
        self.state["updated_at"] = ""
        self._start_client()

    def _start_client(self):
        try:
            import paho.mqtt.client as mqtt
        except Exception as exc:
            self.error = f"paho-mqtt unavailable: {exc}"
            return

        client_id = str(self.cfg.get("client_id") or f"spm-env-{self.sensor_id}")
        self.client = mqtt.Client(client_id=client_id, clean_session=True)
        username = str(self.cfg.get("username") or "")
        if username:
            self.client.username_pw_set(username, str(self.cfg.get("password") or ""))
        if bool(self.cfg.get("tls")):
            self.client.tls_set()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        try:
            self.client.connect(str(self.cfg.get("host") or "127.0.0.1"), int(self.cfg.get("port") or 1883), int(self.cfg.get("keepalive") or 60))
            self.client.loop_start()
            self.running = True
        except Exception as exc:
            self.error = str(exc)
            self.running = False
            add_log(-1, f"[环境] MQTT 连接失败 [{self.name}]: {exc}")

    def stop(self):
        self.running = False
        self.connected = False
        client = self.client
        self.client = None
        if not client:
            return
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass

    def update_config(self, sensor_cfg):
        new_cfg = _merge_mqtt_cfg(sensor_cfg)
        if new_cfg == self.cfg:
            return
        self.cfg = new_cfg
        self.stop()
        self._start_client()

    def _subscribe_topics(self):
        if not self.client:
            return
        topic = str(self.cfg.get("topic") or "").strip()
        qos = int(self.cfg.get("qos") or 0)
        if topic:
            self.client.subscribe(topic, qos=qos)
        availability_topic = str(self.cfg.get("availability_topic") or "").strip()
        if availability_topic:
            self.client.subscribe(availability_topic, qos=qos)

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)
        self.error = "" if rc == 0 else f"connect rc={rc}"
        if rc == 0:
            self._subscribe_topics()
        else:
            add_log(-1, f"[环境] MQTT 连接异常 [{self.name}]: rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc not in [0, None]:
            self.error = f"disconnect rc={rc}"

    def _handle_availability(self, payload_text):
        lowered = str(payload_text or "").strip().lower()
        self.last_availability = lowered
        self.state["online"] = lowered not in ["offline", "false", "0"]
        self.state["updated_at"] = _iso_now()

    def _handle_json_payload(self, payload):
        field_map = self.cfg.get("field_map", {})
        updated = False
        for state_key, payload_key in field_map.items():
            if payload_key not in payload:
                continue
            value = _safe_float(payload.get(payload_key))
            if value is None:
                continue
            self.state[state_key] = value
            updated = True

        if "battery" in payload:
            battery = _safe_float(payload.get("battery"))
            if battery is not None:
                self.state["battery"] = battery
                updated = True

        if "linkquality" in payload:
            linkquality = _safe_float(payload.get("linkquality"))
            if linkquality is not None:
                self.state["linkquality"] = linkquality
                updated = True

        if updated:
            self.state["updated_at"] = _iso_now()
            self.state["online"] = True

    def _on_message(self, client, userdata, msg):
        try:
            payload_text = msg.payload.decode("utf-8", errors="ignore").strip()
        except Exception:
            payload_text = ""
        self.last_payload = payload_text
        self.last_message_at = time.time()

        availability_topic = str(self.cfg.get("availability_topic") or "").strip()
        if availability_topic and msg.topic == availability_topic:
            self._handle_availability(payload_text)
            return

        try:
            parsed = json.loads(payload_text) if payload_text else {}
        except Exception:
            parsed = {}

        if isinstance(parsed, dict):
            self._handle_json_payload(parsed)

    def get_state(self):
        state = deepcopy(self.state)
        stale_after_sec = max(30, int(self.cfg.get("stale_after_sec") or 7200))
        if self.last_message_at:
            age_sec = max(0, int(time.time() - self.last_message_at))
            state["age_sec"] = age_sec
            if age_sec > stale_after_sec:
                state["online"] = False
        else:
            state["age_sec"] = None
            state["online"] = False

        if self.last_availability in ["offline", "false", "0"]:
            state["online"] = False
        return state

    def get_debug(self):
        return {
            "sensor_id": self.sensor_id,
            "sensor_name": self.name,
            "broker": {
                "host": self.cfg.get("host"),
                "port": self.cfg.get("port"),
                "connected": self.connected,
                "error": self.error,
                "client_id": self.cfg.get("client_id") or f"spm-env-{self.sensor_id}",
            },
            "subscription": {
                "topic": self.cfg.get("topic"),
                "availability_topic": self.cfg.get("availability_topic"),
                "qos": self.cfg.get("qos"),
                "stale_after_sec": self.cfg.get("stale_after_sec"),
            },
            "last_payload": self.last_payload,
            "last_message_at": datetime.fromtimestamp(self.last_message_at).isoformat() if self.last_message_at else "",
            "state": self.get_state(),
        }


def sync_env_sensor_configs(env_sensors):
    mqtt_sensors = {
        str(cfg.get("id")): cfg
        for cfg in (env_sensors or [])
        if str(cfg.get("source_type") or "modbus").strip().lower() == "mqtt"
    }

    with _LOCK:
        for sensor_id in list(_SENSOR_CLIENTS.keys()):
            if sensor_id not in mqtt_sensors:
                _SENSOR_CLIENTS[sensor_id].stop()
                _SENSOR_CLIENTS.pop(sensor_id, None)

        for sensor_id, cfg in mqtt_sensors.items():
            if sensor_id not in _SENSOR_CLIENTS:
                _SENSOR_CLIENTS[sensor_id] = _SensorMqttClient(cfg)
            else:
                _SENSOR_CLIENTS[sensor_id].update_config(cfg)


def get_env_state(sensor_cfg):
    sensor_id = str(sensor_cfg.get("id"))
    with _LOCK:
        client = _SENSOR_CLIENTS.get(sensor_id)
        if not client:
            return None
        return client.get_state()


def get_env_debug(sensor_id):
    with _LOCK:
        client = _SENSOR_CLIENTS.get(str(sensor_id))
        if not client:
            return None
        return client.get_debug()
