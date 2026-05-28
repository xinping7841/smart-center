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
- config.json

## Done

- Created task worktree
- Acquired module worklock
- Read vendor AT/Modbus/network-controller manuals and local integration note
- Confirmed 192.168.50.89 AT parameters and DO/DI resources
- Improved Niren AT response parsing and added AT pulse action support
- Added protocol-control packs for AT and Modbus devices
- Added probe and reversible mode-test helper scripts
- Documented integration and migration plan
- Imported all five screenshot devices into `control_center` protocol-control config:
  192.168.50.35, 192.168.50.52, 192.168.50.89, 192.168.50.107, 192.168.50.108
- Added protocol-control target groups, device metadata, DO controls, and DI read controls for each Niren relay

## Verified

- `python -m py_compile control_center_core.py drivers\light_niren_poe_kp.py scripts\probe_niren_poe_kp.py scripts\test_niren_modes.py`
- Loaded built-in command packs through `control_center_core.list_builtin_command_packs()`
- Verified `modbus_rtu` CRC generation for `01 01 00 00 00 01 -> FD CA`
- 192.168.50.89 AT read: `AT`, `AT+DEVICEINFO=?`, `AT+STACH1=?`, `AT+OCCH1=?`
- 192.168.50.89 AT write test: DO1 on, read back on, DO1 off, read back off
- 192.168.50.89 temporary Modbus mode: RTU-over-TCP DO/DI reads worked; standard Modbus TCP did not respond
- Parsed `config.json` and normalized `control_center`: 5 target groups, 15 commands, 5 devices, 1 panel, 22 controls, no missing command/target references
- Executed safe protocol-control reads from `config.json` for all five devices, including 50.89 AT device info/DO/DI and Modbus RTU-over-TCP DO/DI read commands
- Confirmed raw Modbus RTU-over-TCP request frames include CRC and receive valid responses from multiple devices, e.g. `01 01 00 00 00 01 FD CA` and `01 02 00 00 00 01 B9 CA`

## Not Verified

- Config UI/template changes were not made because global/template locks are held by another task

## Risks

- Switching a device from AT to Modbus can make the data port stop accepting AT commands until the protocol is restored; avoid unattended mode-switch tests.
- Existing `custom_devices` contains a `192.168.50.254:1882` generic outdoor-light device, but no current evidence ties it to the Niren POE-KP-I101 devices.
- The config page's format dropdown does not yet expose `modbus_rtu` / `modbus_tcp`; avoid manually changing these command formats in the UI until the template lock is free and UI support is added.
- Some Modbus devices can return empty reads during rapid consecutive polling; keep commands serial per device and tune `wait_ms` / polling cadence if automations need frequent DI sampling.

## Dependencies And Conflicts

`	ext
If this task touches templates/index.html, config.py, background.py, app.py, api/server.py, or snmp_core.py, acquire the related high-risk lock too.
`

## Next

- After global/template locks are free, add config UI support for `modbus_rtu` / `modbus_tcp` format selection and any desired Niren device generator shortcut.
