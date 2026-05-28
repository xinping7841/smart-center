# Task Memory

## Basic Info

- Task: niren-relay-integration
- Module lock: relay_controller
- Branch: codex/12700k-niren-relay-integration-20260528
- Worktree: D:\SmartCenter\smart-center-worktrees\niren-relay-integration
- Machine: 12700k
- Kind: light
- Started: 2026-05-28 13:49:49
- Expected finish:

## Goal

Design and implement the Niren POE-KP-I101 RJ45/WIFI relay integration path for Smart Center, including AT and Modbus RTU-over-TCP support, protocol-control command packs, and live validation against 192.168.50.89.

## Current Phase

`	ext
in_progress
`

## Change Scope

- drivers/light_niren_poe_kp.py
- control_center_core.py
- control_packs/niren_poe_kp_i101_at.json
- control_packs/niren_poe_kp_i101_modbus.json
- scripts/probe_niren_poe_kp.py
- scripts/test_niren_modes.py
- docs/niren_poe_kp_i101_integration.md

## Done

- Created task worktree
- Acquired module worklock
- Read vendor AT/Modbus/network-controller manuals and local integration note
- Confirmed 192.168.50.89 AT parameters and DO/DI resources
- Improved Niren AT response parsing and added AT pulse action support
- Added protocol-control packs for AT and Modbus devices
- Added probe and reversible mode-test helper scripts
- Documented integration and migration plan

## Verified

- `python -m py_compile control_center_core.py drivers\light_niren_poe_kp.py scripts\probe_niren_poe_kp.py scripts\test_niren_modes.py`
- Loaded built-in command packs through `control_center_core.list_builtin_command_packs()`
- Verified `modbus_rtu` CRC generation for `01 01 00 00 00 01 -> FD CA`
- 192.168.50.89 AT read: `AT`, `AT+DEVICEINFO=?`, `AT+STACH1=?`, `AT+OCCH1=?`
- 192.168.50.89 AT write test: DO1 on, read back on, DO1 off, read back off
- 192.168.50.89 temporary Modbus mode: RTU-over-TCP DO/DI reads worked; standard Modbus TCP did not respond

## Not Verified

- Batch import into live `control_center` config was not performed
- Config UI/template changes were not made because global/template locks are held by another task

## Risks

- Switching a device from AT to Modbus can make the data port stop accepting AT commands until the protocol is restored; avoid unattended mode-switch tests.
- Existing `custom_devices` contains a `192.168.50.254:1882` generic outdoor-light device, but no current evidence ties it to the Niren POE-KP-I101 devices.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- After global/template locks are free, add any desired config UI shortcut for generating Niren protocol-control targets.
- Import `niren_poe_kp_i101_at` / `niren_poe_kp_i101_modbus` packs into the live config and create target groups for 192.168.50.35/52/89/107/108.
