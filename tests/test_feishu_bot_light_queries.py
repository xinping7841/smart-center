from __future__ import annotations

from typing import Any

from services.device_aliases import build_device_alias_rows
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

    assert "庭院灯状态" in answer
    assert "- 在线：在线" in answer
    assert "- 开关：暗" in answer
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

    assert "庭院灯状态" in answer
    assert "- 在线：在线" in answer
    assert "- 开关：亮" in answer
    assert client.paths == ["/api/node-red/device/courtyard_light/status"]


def test_lighting_status_intent_returns_specific_hall_controller_channels() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/light/status": (
                True,
                {
                    "channels": {"1": [False, True, True, False], "2": [True, True, True, False, False, None, True, True]},
                    "extras": {
                        "1": {"name": "一号厅", "status_label": "在线"},
                        "2": {"name": "二号厅", "status_label": "在线"},
                    },
                },
            )
        }
    )

    answer = client.answer_intent("lighting_status", "1号厅灯光状态")

    assert "一号厅灯光状态：在线" in answer
    assert "- 一号厅 A区：关闭" in answer
    assert "- 一号厅 B区：开启" in answer
    assert "- 一号厅 沉浸厅：开启" in answer
    assert "- 一号厅 前言墙：关闭" in answer
    assert "二号厅" not in answer
    assert client.paths == ["/api/light/status"]


def test_lighting_query_understands_front_wall_short_alias() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/light/status": (
                True,
                {
                    "channels": {"1": [False, True, True, False]},
                    "extras": {"1": {"name": "一号厅", "status_label": "在线"}},
                },
            )
        }
    )

    answer = client.answer_intent("lighting_status", "前言灯状态")

    assert answer == "一号厅 前言墙状态：在线，第4路 关闭"
    assert client.paths == ["/api/light/status"]


def test_courtyard_status_reply_is_readable_chinese_fields() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/node-red/device/courtyard_light/status": (
                True,
                {
                    "device": {
                        "device_name": "庭院灯RF网关",
                        "online": True,
                        "status": "unknown",
                        "display_text": "未知",
                        "updated_at": "2026-06-03T17:31:57.668Z",
                        "health": {"message": "RF serial healthy"},
                    }
                },
            )
        }
    )

    answer = client.answer_intent("lighting_status", "庭院灯状态")

    assert answer == "\n".join(
        [
            "庭院灯RF网关状态",
            "- 在线：在线",
            "- 开关：未知",
            "- 更新：2026-06-04 01:31:57",
            "- 网关：RF 网关正常",
        ]
    )
    assert client.paths == ["/api/node-red/device/courtyard_light/status"]


def test_ups_specific_status_filters_by_alias() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/ups/status": (
                True,
                {
                    "ups_1774600700259": {
                        "online": True,
                        "battery_capacity_percent": 91,
                        "load_percent": 35,
                        "input_voltage": 220.4,
                        "alerts": [],
                        "updated_at": "2026-06-04T01:00:00",
                        "config": {"name": "山特 UPS"},
                    },
                    "other": {
                        "online": False,
                        "battery_capacity_percent": 10,
                        "load_percent": 90,
                        "input_voltage": 0,
                        "alerts": ["异常"],
                        "config": {"name": "备用 UPS"},
                    },
                },
            )
        }
    )

    answer = client.answer_intent("ups_status", "山特UPS状态")

    assert "山特 UPS" in answer
    assert "备用 UPS" not in answer
    assert "电池 91%" in answer
    assert client.paths == ["/api/ups/status"]


def test_projector_screen_sequencer_and_power_query_route_to_specific_status() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/projector/status": (
                True,
                {"proj_infer_hall1": {"online": True, "power": "on", "updated_at": "2026-06-04T01:00:00"}},
            ),
            "/api/screens": (
                True,
                {"screens": [{"id": "screen_1774322049381", "name": "一厅-A区-幕布", "current_position": 92, "status": {"online": True, "status_level": "online", "last_checked_at": "2026-06-04T01:01:00"}}]},
            ),
            "/api/sequencer/status": (
                True,
                {"devices": [{"id": "sequencer_1775236288646", "name": "2 厅-LED", "online": True, "channels": [True, False, True], "updated_at": "2026-06-04T01:02:00"}]},
            ),
            "/api/status?cab=0": (
                True,
                {"online": True, "channels": [True, False, False, True], "updated_at": "2026-06-04T01:03:00"},
            ),
        }
    )

    projector = client.query_text("一号厅投影状态")
    screen = client.query_text("一厅A区幕布状态")
    sequencer = client.query_text("二号厅时序电源状态")
    power = client.query_text("中控室1号厅空调电源状态")

    assert "投影机状态" in projector and "一号厅" in projector
    assert "幕布状态" in screen and "一厅-A区-幕布" in screen
    assert "时序电源状态" in sequencer and "2 厅-LED" in sequencer
    assert "中控室 1号厅空调状态" in power and "第1路 开启" in power


def test_specific_non_light_status_replies_are_filtered_and_readable() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/hvac/status": (
                True,
                {
                    "hvac_ha_shenlan_ac_01": {"name": "机房空调 1.5 挂机", "online": True, "power": True, "mode": "cool", "target_temp": 24, "temp": 26.2, "updated_at": "2026-06-04T01:10:00"},
                    "hvac_ha_office_01_ac_01": {"name": "办公室 01 空调", "online": True, "power": False, "mode": "off", "target_temp": 25, "temp": 27.0},
                },
            ),
            "/api/snmp/status": (
                True,
                {
                    "switch_a": {"online": True, "config": {"name": "核心交换机"}, "summary": {"status_text": "端口正常"}, "updated_at": "2026-06-04T01:11:00"},
                    "nas_a": {"online": True, "config": {"name": "飞牛 NAS"}, "summary": {"status_text": "存储正常"}},
                },
            ),
            "/api/proxy/status": (
                True,
                {
                    "online": True,
                    "healthy_target_count": 1,
                    "check_count": 2,
                    "checks": [
                        {"name": "ChatGPT", "healthy": True, "latency_ms": 88},
                        {"name": "Google", "healthy": False, "latency_ms": None},
                    ],
                    "clients": {"active_client_count": 3},
                },
            ),
            "/api/automation/status": (
                True,
                {
                    "rules": [
                        {"id": "auto_outdoor_light_low_lux_on", "name": "户外灯低照度自动开灯", "enabled": True, "state": {"active": False, "last_triggered_at": "2026-06-04T01:12:00"}},
                        {"id": "other", "name": "其它规则", "enabled": False, "state": {}},
                    ]
                },
            ),
        }
    )

    hvac = client.answer_intent("hvac_status", "机房空调状态")
    snmp = client.query_text("核心交换机SNMP状态")
    proxy = client.query_text("ChatGPT代理状态")
    automation = client.query_text("户外灯低照度自动开灯规则状态")

    assert "机房空调 1.5 挂机" in hvac and "办公室 01 空调" not in hvac
    assert "核心交换机" in snmp and "飞牛 NAS" not in snmp
    assert "ChatGPT" in proxy and "Google" not in proxy
    assert "户外灯低照度自动开灯" in automation and "其它规则" not in automation


def test_environment_specific_status_is_filtered_and_uses_local_time() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/env/status": (
                True,
                {
                    "env_xiaomi_ha_temp_hum_01": {
                        "name": "机房温湿度",
                        "online": True,
                        "temp": 25.6,
                        "hum": 48.2,
                        "updated_at": "2026-06-03T17:31:57.668Z",
                    },
                    "env_1774425123763": {
                        "name": "户外-光照温湿度",
                        "online": True,
                        "temp": 30.1,
                        "hum": 66,
                        "lux": 520,
                    },
                },
            ),
            "/api/dashboard/summary": (True, {"modules": {"env": {"devices": []}}}),
        }
    )

    answer = client.query_text("机房温湿度状态")

    assert "机房温湿度" in answer
    assert "户外-光照温湿度" not in answer
    assert "更新 2026-06-04 01:31:57" in answer


def test_device_alias_index_includes_automation_rules_for_local_model_knowledge() -> None:
    rows = build_device_alias_rows(
        {
            "automation": {
                "rules": [
                    {
                        "id": "auto_outdoor_light_low_lux_on",
                        "name": "户外灯低照度自动开灯",
                        "description": "低照度自动打开庭院灯",
                    }
                ]
            }
        }
    )

    matches = [row for row in rows if row.get("module") == "automation"]

    assert len(matches) == 1
    assert matches[0]["device_id"] == "auto_outdoor_light_low_lux_on"
    assert "户外灯低照度自动开灯" in matches[0]["name"]


def test_prod_aliases_route_core_switch_and_second_hall_sequencer() -> None:
    client = FakeSmartCenterClient(
        {
            "/api/snmp/status": (
                True,
                {
                    "snmp_h3c_192_168_99_1": {
                        "online": True,
                        "config": {"name": "H3C Switch", "host": "192.168.99.1"},
                        "summary": {"status_text": "端口正常"},
                        "updated_at": "2026-06-04T02:20:00",
                    },
                    "snmp_fnnas_192_168_50_254": {
                        "online": True,
                        "config": {"name": "飞牛 NAS"},
                    },
                },
            ),
            "/api/sequencer/status": (
                True,
                {
                    "devices": [
                        {"id": "sequencer_ds608_1", "name": "中控", "online": True},
                        {"id": "sequencer_1775236288646", "name": "2 厅-LED", "online": True, "channels": [True, False, False], "updated_at": "2026-06-04T02:21:00"},
                    ]
                },
            ),
        }
    )

    snmp = client.query_text("核心交换机SNMP状态")
    sequencer = client.query_text("二号厅时序电源状态")

    assert "H3C Switch" in snmp
    assert "飞牛 NAS" not in snmp
    assert "2 厅-LED" in sequencer
    assert "中控" not in sequencer
