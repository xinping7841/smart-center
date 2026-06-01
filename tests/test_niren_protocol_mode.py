from control_center_core import apply_niren_protocol_mode


def _sample_control_center():
    target_id = "niren_poe_kp_i101_192_168_50_35_rtu"
    return {
        "enabled": True,
        "version": 1,
        "target_groups": [
            {
                "id": target_id,
                "name": "1 infrared fill light",
                "vendor": "Niren",
                "model": "POE-KP-I101",
                "protocol": "tcp",
                "host": "192.168.50.35",
                "port": 502,
                "data_protocol": "modbus_rtu_over_tcp",
            }
        ],
        "command_library": [],
        "devices": [
            {
                "id": "niren_poe_kp_i101_192_168_50_35",
                "name": "Niren 50.35",
                "target_group_id": target_id,
            }
        ],
        "panels": [
            {
                "id": "niren",
                "name": "Niren",
                "controls": [
                    {"id": "read_do", "name": "Read DO", "command_id": "niren_modbus_rtu_read_do", "target_group_id": target_id},
                    {"id": "read_di", "name": "Read DI", "command_id": "niren_modbus_rtu_read_di", "target_group_id": target_id},
                    {"id": "do_on", "name": "DO on", "command_id": "niren_modbus_rtu_do_on", "target_group_id": target_id},
                    {"id": "do_off", "name": "DO off", "command_id": "niren_modbus_rtu_do_off", "target_group_id": target_id},
                    {"id": "pulse", "name": "Pulse", "command_id": "", "target_group_id": target_id, "visible": False},
                ],
            }
        ],
    }


def test_niren_at_mode_keeps_existing_port_and_syncs_controls():
    target_id = "niren_poe_kp_i101_192_168_50_35_rtu"
    result = apply_niren_protocol_mode(_sample_control_center(), target_id, "at_over_tcp")
    config = result["control_center"]
    target = next(item for item in config["target_groups"] if item["id"] == target_id)
    controls = {
        item["id"]: item
        for panel in config["panels"]
        for item in panel["controls"]
        if item["target_group_id"] == target_id
    }

    assert target["host"] == "192.168.50.35"
    assert target["port"] == 502
    assert target["data_protocol"] == "at_over_tcp"
    assert target["send_strategy"] == "serial"
    assert controls["read_do"]["command_id"] == "niren_at_do_read"
    assert controls["read_di"]["command_id"] == "niren_at_di_read"
    assert controls["do_on"]["command_id"] == "niren_at_do_on"
    assert controls["do_off"]["command_id"] == "niren_at_do_off"
    assert controls["pulse"]["command_id"] == "niren_at_do_pulse"
    assert controls["pulse"]["visible"] is True


def test_niren_rtu_mode_hides_unsupported_pulse_control():
    target_id = "niren_poe_kp_i101_192_168_50_35_rtu"
    result = apply_niren_protocol_mode(_sample_control_center(), target_id, "modbus_rtu_over_tcp")
    config = result["control_center"]
    target = next(item for item in config["target_groups"] if item["id"] == target_id)
    pulse = next(
        item
        for panel in config["panels"]
        for item in panel["controls"]
        if item["id"] == "pulse"
    )

    assert target["port"] == 502
    assert target["data_protocol"] == "modbus_rtu_over_tcp"
    assert pulse["command_id"] == ""
    assert pulse["visible"] is False
    assert pulse["show_on_home"] is False
