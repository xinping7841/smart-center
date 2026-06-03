from __future__ import annotations

from typing import Any

from services.feishu_bot import LocalSmartCenterClient


class FakeSmartCenterClient(LocalSmartCenterClient):
    def __init__(self, responses: dict[str, Any]) -> None:
        super().__init__("http://smart-center.local")
        self.responses = responses
        self.paths: list[str] = []

    def get_json(self, path: str, timeout_sec: float | None = None) -> tuple[bool, Any]:
        self.paths.append(path)
        return self.responses[path]


def test_courtyard_light_query_uses_node_red_device_status_before_generic_light_status() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/node-red/device/courtyard_light/status": (
                True,
                {
                    "ok": 1,
                    "device": {
                        "device_id": "courtyard_light",
                        "device_name": "庭院灯",
                        "online": True,
                        "status": "off",
                        "display_text": "暗",
                        "updated_at": "2026-06-03T23:25:00",
                        "health": {"status": "ok", "message": "normal"},
                    },
                },
            ),
            "/api/light/status": (
                True,
                {
                    "channels": {"1": [False, False, False, False]},
                    "extras": {"1": {"name": "1", "status_label": "在线"}},
                },
            ),
        }
    )

    answer = client.query_text("庭院灯状态")

    assert "庭院灯状态：在线，暗" in answer
    assert client.paths == ["/api/node-red/device/courtyard_light/status"]


def test_lighting_status_intent_keeps_specific_courtyard_query() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/node-red/device/courtyard_light/status": (
                True,
                {
                    "ok": 1,
                    "device": {
                        "device_name": "庭院灯",
                        "online": True,
                        "status": "on",
                        "display_text": "亮",
                        "updated_at": "2026-06-03T23:26:00",
                    },
                },
            )
        }
    )

    answer = client.answer_intent("lighting_status", "户外灯状态")

    assert "庭院灯状态：在线，亮" in answer
    assert client.paths == ["/api/node-red/device/courtyard_light/status"]
