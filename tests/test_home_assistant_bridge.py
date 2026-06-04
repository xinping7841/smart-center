import unittest
from unittest.mock import patch


from services import home_assistant_bridge as bridge


class HomeAssistantBridgeTest(unittest.TestCase):
    def test_hvac_status_separates_poll_time_from_ha_state_time(self):
        def fake_state(entity_id, ha_cfg):
            return {
                "entity_id": entity_id,
                "state": "cool",
                "last_changed": "2026-06-04T02:53:11.741845+00:00",
                "last_updated": "2026-06-04T02:53:11.741845+00:00",
                "last_reported": "2026-06-04T02:53:11.741845+00:00",
                "attributes": {
                    "temperature": 22,
                    "hvac_action": "cooling",
                    "hvac_modes": ["off", "cool"],
                },
            }

        with patch.object(bridge, "_now_iso", return_value="2026-06-04T11:08:00"):
            with patch.object(bridge, "get_cached_state", side_effect=fake_state):
                status = bridge.get_hvac_status(
                    {
                        "id": "hvac_ha_office_01_ac_01",
                        "name": "办公室 01 空调",
                        "protocol": "home_assistant",
                        "home_assistant": {
                            "entity_id": "climate.lumi_cn_827394351_mcn02",
                            "token": "test-token",
                        },
                    },
                    {"home_assistant": {"token": "test-token"}},
                )

        self.assertEqual(status["updated_at"], "2026-06-04T11:08:00")
        self.assertEqual(status["polled_at"], "2026-06-04T11:08:00")
        self.assertEqual(status["last_updated"], "2026-06-04T10:53:11")
        self.assertEqual(status["last_reported"], "2026-06-04T10:53:11")
        self.assertEqual(status["ha_last_updated"], "2026-06-04T10:53:11")
        self.assertEqual(status["ha_last_reported"], "2026-06-04T10:53:11")
        self.assertIs(status["power"], True)
        self.assertEqual(status["mode"], "cool")
        self.assertEqual(status["temp"], 22)


if __name__ == "__main__":
    unittest.main()
