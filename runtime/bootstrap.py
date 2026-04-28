import threading
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence

from api.door import camera_capture_loop, update_door_status
from api.server import clean_old_history, init_db, local_server_monitor_loop
from background import (
    env_update_loop,
    hvac_update_loop,
    init_light_drivers,
    light_update_loop,
    m32r_update_loop,
    meter_statistics_maintenance_loop,
    meter_update_loop,
    proxy_update_loop,
    projector_update_loop,
    screen_update_loop,
    sequencer_update_loop,
    snmp_update_loop,
    update_loop,
    ups_update_loop,
)
from runtime.automation import automation_engine_loop


@dataclass(frozen=True)
class BackgroundService:
    name: str
    target: Callable
    category: str = "core"
    description: str = ""


BACKGROUND_SERVICES: Sequence[BackgroundService] = (
    BackgroundService("history-cleaner", clean_old_history, "server", "Clean expired machine history."),
    BackgroundService("local-server-monitor", local_server_monitor_loop, "server", "Collect Ubuntu host metrics without installing a second agent."),
    BackgroundService("cabinet-poller", update_loop, "power", "Poll cabinet PLC and linked telemetry."),
    BackgroundService("meter-poller", meter_update_loop, "meter", "Poll standalone and calculated meters."),
    BackgroundService("light-poller", light_update_loop, "light", "Poll lighting devices."),
    BackgroundService("projector-poller", projector_update_loop, "projector", "Poll projectors."),
    BackgroundService("sequencer-poller", sequencer_update_loop, "sequencer", "Poll sequencer devices."),
    BackgroundService("ups-poller", ups_update_loop, "ups", "Poll UPS devices."),
    BackgroundService("snmp-poller", snmp_update_loop, "snmp", "Poll SNMP devices."),
    BackgroundService("proxy-monitor", proxy_update_loop, "network", "Monitor upstream proxy health."),
    BackgroundService("screen-poller", screen_update_loop, "screen", "Poll screen devices."),
    BackgroundService("door-camera", camera_capture_loop, "door", "Capture door camera frames."),
    BackgroundService("door-status", update_door_status, "door", "Update door status."),
    BackgroundService("env-poller", env_update_loop, "env", "Poll environment sensors."),
    BackgroundService("hvac-poller", hvac_update_loop, "hvac", "Poll HVAC devices."),
    BackgroundService("automation-engine", automation_engine_loop, "automation", "Evaluate automation rules."),
    BackgroundService("meter-statistics", meter_statistics_maintenance_loop, "meter", "Export meter reports and maintain display reset snapshots."),
    BackgroundService("m32r-poller", m32r_update_loop, "audio", "Poll M32R mixer state."),
)

_runtime_lock = threading.Lock()
_runtime_initialized = False
_background_started = False
_background_threads: List[threading.Thread] = []


def init_runtime() -> None:
    global _runtime_initialized
    with _runtime_lock:
        if _runtime_initialized:
            return
        init_db()
        init_light_drivers()
        _runtime_initialized = True


def iter_background_services() -> Iterable[BackgroundService]:
    return BACKGROUND_SERVICES


def iter_background_targets() -> Iterable[Callable]:
    for service in iter_background_services():
        yield service.target


def start_background_services() -> List[threading.Thread]:
    global _background_started, _background_threads
    with _runtime_lock:
        if _background_started:
            alive_threads = [thread for thread in _background_threads if thread.is_alive()]
            if alive_threads:
                _background_threads = alive_threads
                return list(_background_threads)
            _background_started = False
            _background_threads = []

        threads: List[threading.Thread] = []
        for service in iter_background_services():
            thread = threading.Thread(target=service.target, name=f"spm-{service.name}", daemon=True)
            thread.start()
            threads.append(thread)
        _background_threads = threads
        _background_started = True
        return list(_background_threads)


def ensure_runtime_started() -> List[threading.Thread]:
    init_runtime()
    return start_background_services()


def get_background_service_manifest() -> List[dict]:
    return [
        {
            "name": service.name,
            "category": service.category,
            "description": service.description,
            "thread_name": f"spm-{service.name}",
        }
        for service in iter_background_services()
    ]
