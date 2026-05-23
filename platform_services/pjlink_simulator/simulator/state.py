from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from pathlib import Path

from .profiles import PROFILES, get_profile


class SimulatorState:
    def __init__(self, state_file: str, default_profile_id: str, default_password: str = ""):
        self._state_file = Path(state_file)
        self._lock = threading.RLock()
        self._state = self._build_initial_state(default_profile_id, default_password)
        self._load()

    def _build_initial_state(self, profile_id: str, password: str) -> dict:
        profile = get_profile(profile_id)
        now = time.time()
        return {
            "profile_id": profile["id"],
            "password": password,
            "auth_mode": profile.get("default_auth_mode", "none"),
            "power": {
                "current": "0",
                "target": "0",
                "transition_until": 0.0,
                "updated_at": now,
            },
            "input_code": next(iter(profile["inputs"])),
            "audio_muted": False,
            "video_muted": False,
            "freeze": False,
            "speaker_volume": 50,
            "microphone_volume": 50,
            "error_status": profile["error_status"],
            "lamp_hours": deepcopy(profile["lamp_hours"]),
            "filter_hours": deepcopy(profile["filter_hours"]),
            "serial_number": profile["serial_number"],
            "software_version": profile["software_version"],
            "input_resolution": profile["input_resolution"],
            "recommended_resolution": profile["recommended_resolution"],
            "device_name": profile["device_name"],
            "manufacturer_name": profile["manufacturer_name"],
            "product_name": profile["product_name"],
            "other_info": profile["other_info"],
            "lamp_models": deepcopy(profile["lamp_models"]),
            "filter_models": deepcopy(profile["filter_models"]),
        }

    def _load(self) -> None:
        with self._lock:
            if not self._state_file.exists():
                self._save_locked()
                return
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            profile_id = data.get("profile_id", self._state["profile_id"])
            if profile_id not in PROFILES:
                profile_id = self._state["profile_id"]
            merged = self._build_initial_state(profile_id, data.get("password", ""))
            self._merge_dict(merged, data)
            self._state = merged
            self._save_locked()

    def _merge_dict(self, target: dict, incoming: dict) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge_dict(target[key], value)
            else:
                target[key] = value

    def _save_locked(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _current_profile_locked(self) -> dict:
        return get_profile(self._state["profile_id"])

    def _update_power_transition_locked(self) -> None:
        power = self._state["power"]
        transition_until = float(power.get("transition_until") or 0.0)
        target = power.get("target", power.get("current", "0"))
        now = time.time()
        if transition_until and now >= transition_until:
            power["current"] = target
            power["transition_until"] = 0.0
            power["updated_at"] = now

    def snapshot(self) -> dict:
        with self._lock:
            self._update_power_transition_locked()
            return deepcopy(self._state)

    def get_profile(self) -> dict:
        with self._lock:
            return self._current_profile_locked()

    def reset(self, profile_id: str | None = None) -> dict:
        with self._lock:
            profile_id = profile_id or self._state["profile_id"]
            password = self._state.get("password", "")
            self._state = self._build_initial_state(profile_id, password)
            self._save_locked()
            return self.snapshot()

    def select_profile(self, profile_id: str) -> dict:
        with self._lock:
            password = self._state.get("password", "")
            self._state = self._build_initial_state(profile_id, password)
            self._save_locked()
            return self.snapshot()

    def update(self, patch: dict) -> dict:
        with self._lock:
            if "profile_id" in patch and patch["profile_id"] != self._state["profile_id"]:
                new_password = patch.get("password", self._state.get("password", ""))
                self._state = self._build_initial_state(patch["profile_id"], new_password)
                if "auth_mode" in patch:
                    self._state["auth_mode"] = patch["auth_mode"]
                patch = {key: value for key, value in patch.items() if key != "profile_id"}

            if "power_state" in patch:
                self.set_power(patch.pop("power_state"))

            if "password" in patch:
                self._state["password"] = str(patch.pop("password"))

            if "auth_mode" in patch:
                auth_mode = str(patch.pop("auth_mode"))
                if auth_mode not in {"none", "md5", "auto"}:
                    raise ValueError("auth_mode must be one of: none, md5, auto")
                self._state["auth_mode"] = auth_mode

            if "input_code" in patch:
                self.set_input(str(patch.pop("input_code")))

            for bool_key in ("audio_muted", "video_muted", "freeze"):
                if bool_key in patch:
                    self._state[bool_key] = bool(patch.pop(bool_key))

            for volume_key in ("speaker_volume", "microphone_volume"):
                if volume_key in patch:
                    self._state[volume_key] = self._clamp_int(patch.pop(volume_key), 0, 100)

            for text_key in (
                "error_status",
                "serial_number",
                "software_version",
                "input_resolution",
                "recommended_resolution",
                "device_name",
                "manufacturer_name",
                "product_name",
                "other_info",
            ):
                if text_key in patch:
                    self._state[text_key] = str(patch.pop(text_key))

            for list_key in ("lamp_hours", "filter_hours", "lamp_models", "filter_models"):
                if list_key in patch:
                    self._state[list_key] = list(patch.pop(list_key))

            if patch:
                self._merge_dict(self._state, patch)

            self._save_locked()
            return self.snapshot()

    def _clamp_int(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(value)))

    def set_power(self, requested_state: str) -> None:
        with self._lock:
            self._update_power_transition_locked()
            profile = self._current_profile_locked()
            power = self._state["power"]
            now = time.time()
            if requested_state == "1":
                power["current"] = "3"
                power["target"] = "1"
                power["transition_until"] = now + float(profile.get("power_on_delay", 0.0))
                power["updated_at"] = now
            elif requested_state == "0":
                power["current"] = "2"
                power["target"] = "0"
                power["transition_until"] = now + float(profile.get("power_off_delay", 0.0))
                power["updated_at"] = now
            elif requested_state in {"2", "3"}:
                power["current"] = requested_state
                power["target"] = "1" if requested_state == "3" else "0"
                power["transition_until"] = 0.0
                power["updated_at"] = now
            else:
                raise ValueError("power_state must be one of: 0, 1, 2, 3")
            self._save_locked()

    def get_power_state(self) -> str:
        with self._lock:
            self._update_power_transition_locked()
            return self._state["power"]["current"]

    def set_input(self, code: str) -> None:
        with self._lock:
            profile = self._current_profile_locked()
            if code not in profile["inputs"]:
                raise ValueError(f"Unsupported input code for current profile: {code}")
            self._state["input_code"] = code
            self._save_locked()

    def get_inputs(self) -> dict:
        with self._lock:
            return deepcopy(self._current_profile_locked()["inputs"])
