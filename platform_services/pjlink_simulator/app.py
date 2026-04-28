from __future__ import annotations

import logging
import os
import threading

from flask import Flask, request

from simulator.pjlink_server import PJLinkCommandProcessor, PJLinkServerApp
from simulator.profiles import list_profiles
from simulator.state import SimulatorState


def _enrich_state(state: SimulatorState, snapshot: dict) -> dict:
    snapshot["profile"] = state.get_profile()
    snapshot["inputs"] = state.get_inputs()
    return snapshot


def create_http_app(state: SimulatorState) -> Flask:
    app = Flask(__name__)
    processor = PJLinkCommandProcessor(state)

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok"}, 200

    @app.get("/api/v1/profiles")
    def profiles() -> tuple[dict, int]:
        return {"profiles": list_profiles()}, 200

    @app.get("/api/v1/state")
    def get_state() -> tuple[dict, int]:
        return _enrich_state(state, state.snapshot()), 200

    @app.put("/api/v1/state")
    def update_state() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=False) or {}
        try:
            snapshot = state.update(payload)
        except Exception as exc:
            return {"error": str(exc)}, 400
        return _enrich_state(state, snapshot), 200

    @app.post("/api/v1/profile/select")
    def select_profile() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=False) or {}
        profile_id = payload.get("profile_id")
        if not profile_id:
            return {"error": "profile_id is required"}, 400
        try:
            snapshot = state.select_profile(profile_id)
        except Exception as exc:
            return {"error": str(exc)}, 400
        return _enrich_state(state, snapshot), 200

    @app.post("/api/v1/reset")
    def reset() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        try:
            snapshot = state.reset(payload.get("profile_id"))
        except Exception as exc:
            return {"error": str(exc)}, 400
        return _enrich_state(state, snapshot), 200

    @app.post("/api/v1/command")
    def execute_command() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=False) or {}
        command = str(payload.get("command", "")).strip()
        if not command:
            return {"error": "command is required"}, 400
        response = processor.handle(command)
        return {"command": command, "response": response}, 200

    @app.get("/api/v1/commands")
    def command_catalog() -> tuple[dict, int]:
        profile = state.get_profile()
        supports = profile["supports"]
        commands = [
            {"command": "%1POWR ?", "note": "Query power state"},
            {"command": "%1POWR 1", "note": "Power on"},
            {"command": "%1POWR 0", "note": "Power off"},
            {"command": "%1INPT ?", "note": "Query input"},
            {"command": "%1INST ?", "note": "List supported inputs"},
            {"command": "%1AVMT ?", "note": "Query AV mute"},
            {"command": "%1AVMT 31", "note": "Mute audio/video"},
            {"command": "%1AVMT 30", "note": "Unmute audio/video"},
            {"command": "%1ERST ?", "note": "Query error status"},
            {"command": "%1LAMP ?", "note": "Query lamp hours"},
            {"command": "%1NAME ?", "note": "Query device name"},
            {"command": "%1INF1 ?", "note": "Query manufacturer"},
            {"command": "%1INF2 ?", "note": "Query product"},
            {"command": "%1INFO ?", "note": "Query other info"},
            {"command": "%1CLSS ?", "note": "Query PJLink class"},
        ]
        if profile["pjlink_class"] == 2:
            commands.extend(
                [
                    {"command": "%2SNUM ?", "note": "Query serial number"},
                    {"command": "%2SVER ?", "note": "Query software version"},
                    {"command": "%2INNM ?", "note": "Query all input names"},
                    {"command": "%2IRES ?", "note": "Query current input resolution"},
                    {"command": "%2RRES ?", "note": "Query recommended resolution"},
                ]
            )
            if supports["freeze"]:
                commands.extend(
                    [
                        {"command": "%2FREZ ?", "note": "Query freeze state"},
                        {"command": "%2FREZ 1", "note": "Freeze on"},
                        {"command": "%2FREZ 0", "note": "Freeze off"},
                    ]
                )
            if supports["filter_hours"]:
                commands.append({"command": "%2FILT ?", "note": "Query filter hours"})
            if supports["lamp_model"]:
                commands.append({"command": "%2RLMP ?", "note": "Query lamp model"})
            if supports["filter_model"]:
                commands.append({"command": "%2RFIL ?", "note": "Query filter model"})
            if supports["speaker_volume"]:
                commands.extend(
                    [
                        {"command": "%2SVOL 1", "note": "Speaker volume up"},
                        {"command": "%2SVOL 0", "note": "Speaker volume down"},
                    ]
                )
            if supports["microphone_volume"]:
                commands.extend(
                    [
                        {"command": "%2MVOL 1", "note": "Mic volume up"},
                        {"command": "%2MVOL 0", "note": "Mic volume down"},
                    ]
                )
        return {"commands": commands}, 200

    return app


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    root_dir = os.path.dirname(os.path.abspath(__file__))
    state_file = os.getenv("STATE_FILE", os.path.join(root_dir, "data", "state.json"))
    default_profile_id = os.getenv("DEFAULT_PROFILE", "epson_1_0")
    default_password = os.getenv("PJLINK_PASSWORD", "")
    pjlink_host = os.getenv("PJLINK_HOST", "0.0.0.0")
    pjlink_port = int(os.getenv("PJLINK_PORT", "4352"))
    http_host = os.getenv("HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("HTTP_PORT", "8080"))

    state = SimulatorState(state_file, default_profile_id, default_password)
    tcp_server = PJLinkServerApp(pjlink_host, pjlink_port, state)
    http_app = create_http_app(state)

    tcp_thread = threading.Thread(target=tcp_server.serve_forever, daemon=True)
    tcp_thread.start()

    logging.getLogger("pjlink-simulator").info(
        "Simulator ready: PJLink=%s:%s HTTP=%s:%s profile=%s",
        pjlink_host,
        pjlink_port,
        http_host,
        http_port,
        state.snapshot()["profile_id"],
    )
    http_app.run(host=http_host, port=http_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
