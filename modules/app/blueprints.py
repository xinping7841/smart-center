"""Blueprint registry for the Smart Center Flask application."""

# AI_MODULE: app_blueprint_registry
# AI_PURPOSE: Keep Flask blueprint imports and registration order out of app.py.
# AI_BOUNDARY: This module only owns route registration; route logic stays in api/*.
# AI_DATA_FLOW: create_app() -> register_blueprints(app) -> api route modules.
# AI_RISK: Medium. Route order affects legacy endpoints such as / and /config.
# AI_COMPAT: Preserve all public URLs registered by api/*.py modules.
# AI_SEARCH_KEYWORDS: blueprint, register_blueprint, app factory, routes.

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from flask import Blueprint, Flask

from api.apple_audio import bp as apple_audio_bp
from api.auth_api import bp as auth_api_bp
from api.automation import bp as automation_bp
from api.control_center import bp as control_center_bp
from api.current_collector import bp as current_collector_bp
from api.dashboard import bp as dashboard_bp
from api.door import bp as door_bp
from api.driver_hub import bp as driver_hub_bp
from api.env import bp as env_bp
from api.hvac import bp as hvac_bp
from api.hy_edge import bp as hy_edge_bp
from api.light import bp as light_bp
from api.local_model import bp as local_model_bp
from api.logs import bp as logs_bp
from api.m32r import bp as m32r_bp
from api.node_red import bp as node_red_bp
from api.nvr import bp as nvr_bp
from api.power import bp as power_bp
from api.projector import bp as projector_bp
from api.proxy import bp as proxy_bp
from api.screen import bp as screen_bp
from api.sequencer import bp as sequencer_bp
from api.server import bp as server_bp
from api.snmp import bp as snmp_bp
from api.universal import bp as universal_bp
from api.ups import bp as ups_bp


@dataclass(frozen=True)
class BlueprintSpec:
    name: str
    blueprint: Blueprint
    purpose: str


# Keep this order stable. The power blueprint owns the legacy / and /config pages.
BLUEPRINTS: Sequence[BlueprintSpec] = (
    BlueprintSpec("power", power_bp, "Main dashboard, config page, power and meter APIs."),
    BlueprintSpec("dashboard", dashboard_bp, "Dashboard summary APIs."),
    BlueprintSpec("auth_api", auth_api_bp, "Login and account APIs."),
    BlueprintSpec("apple_audio", apple_audio_bp, "Apple Audio player APIs."),
    BlueprintSpec("light", light_bp, "Lighting and relay APIs."),
    BlueprintSpec("logs", logs_bp, "Event log query APIs."),
    BlueprintSpec("door", door_bp, "Door camera and vision APIs."),
    BlueprintSpec("control_center", control_center_bp, "Protocol control center APIs."),
    BlueprintSpec("local_model", local_model_bp, "Local model console and training export APIs."),
    BlueprintSpec("current_collector", current_collector_bp, "Standalone current collector APIs."),
    BlueprintSpec("driver_hub", driver_hub_bp, "Driver hub manifest and snapshot APIs."),
    BlueprintSpec("server", server_bp, "Server monitor and agent APIs."),
    BlueprintSpec("proxy", proxy_bp, "Proxy monitor APIs."),
    BlueprintSpec("projector", projector_bp, "Projector status and control APIs."),
    BlueprintSpec("screen", screen_bp, "Screen lift status and control APIs."),
    BlueprintSpec("universal", universal_bp, "Legacy universal control API."),
    BlueprintSpec("env", env_bp, "Environment sensor APIs."),
    BlueprintSpec("hy_edge", hy_edge_bp, "HY edge room APIs."),
    BlueprintSpec("snmp", snmp_bp, "SNMP monitor APIs."),
    BlueprintSpec("nvr", nvr_bp, "NVR preview and stream proxy APIs."),
    BlueprintSpec("node_red", node_red_bp, "Node-RED device gateway APIs."),
    BlueprintSpec("automation", automation_bp, "Automation rule APIs."),
    BlueprintSpec("hvac", hvac_bp, "HVAC status and control APIs."),
    BlueprintSpec("sequencer", sequencer_bp, "Power sequencer APIs."),
    BlueprintSpec("ups", ups_bp, "UPS status and control APIs."),
    BlueprintSpec("m32r", m32r_bp, "M32R mixer APIs."),
)


def iter_blueprints() -> Iterable[BlueprintSpec]:
    return BLUEPRINTS


def register_blueprints(app: Flask) -> None:
    for spec in iter_blueprints():
        app.register_blueprint(spec.blueprint)


def build_blueprint_manifest() -> list[dict]:
    return [
        {
            "name": spec.name,
            "blueprint": spec.blueprint.name,
            "purpose": spec.purpose,
        }
        for spec in iter_blueprints()
    ]
