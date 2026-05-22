# Local AI Navigation Guide

Last updated: 2026-05-22

Use this file first when a local AI model needs to understand or modify Smart Center. The goal is to avoid blind search through historical backups or large mixed files.

## Source Of Truth

- Production source: `/srv/git-work/smart-center-main`
- Runtime symlink: `/srv/smart-center/current`
- Main service: `smart-center.service`
- Main app entry: `app.py`
- App assembly: `modules/app/`
- Main UI shell: `templates/index.html`
- Main config: `config.json` loaded through `config.py`

Ignore historical backups, generated scripts, and runtime dumps unless the user explicitly asks to recover history.

## Search Order

1. Read `docs/MODULE_INDEX.yaml` for module ownership and keywords.
2. Read `docs/AI_CODE_MARKERS.md` for the meaning of `AI_*` code comments.
3. Read the module `MODULE.md` if it exists.
4. Inspect the top `AI_MODULE / AI_PURPOSE / AI_BOUNDARY / AI_RISK` comments in the relevant file.
5. Inspect the API route in `api/<module>.py`.
6. Inspect service/core logic in `services/`, `*_core.py`, `drivers/`, or `runtime/`.
7. Inspect UI code in `templates/index.html` or future `static/js/views/<module>.js`.
8. Only then use broad `rg` searches.

## Files To Avoid As Primary Evidence

These can contain stale or generated content and should not be treated as current logic without confirmation:

- `index.html`
- `power.py`
- `api/server_new.py` is deleted in the clean-lab branch; use `api/server.py`.
- `*_agent*.ps1`
- `*.bak*`
- `operation_logs.json`, `audit_logs.json`, `energy_log.json`
- `runtime/door_recordings`, `runtime/door_dataset*`, `runtime/door_retrain_runs`
- `/srv/smart-center/backups/*`
- `/srv/smart-center/releases/*` except the current symlink target

## Safe Change Pattern

For production work:

1. Create a backup or Git tag first.
2. Change the smallest module possible.
3. Run syntax checks for touched Python files.
4. Validate the relevant API with `curl` from node-120.
5. If agent code changed, bump `AGENT_VERSION` and verify `/agent/worker.json`.
6. Deploy by creating a new release instead of editing `/srv/smart-center/current` in place.

For unattended or overnight validation, set `SMART_CENTER_CONTROL_MODE=dry_run` before calling device-control APIs. Use `normal` only when现场确认允许真实控制动作.

## Module Keywords

- Power meter, cabinets, energy, current collector: `power`, `meter`, `cabinet`, `current_collector`, `meter_service`.
- Server monitor, Windows Agent, WOL, CodeMeter: `server`, `machines`, `agent`, `codemeter`, `wake`.
- SNMP/NAS/router/switch: `snmp`, `qnap`, `ikuai`, `h3c`, `interface`, `storage`.
- Automation scenes and rules: `automation`, `scene`, `condition`, `runtime/automation.py`.
- HVAC and sensors: `hvac`, `home_assistant`, `miio`, `env`, `temperature`, `humidity`.
- Projector and screen: `projector`, `pjlink`, `screen`, `inferred`, `rs232`.
- NVR preview: `nvr`, `hikvision`, `live`, `snapshot`, `player`.
- Door/camera vision: `door`, `vision`, `camera`, `recording`, `dataset`.

## Commenting Standard

Add comments only where they help future humans or AI avoid mistakes:

- Module header: what the file owns and what it must not own.
- Boundary comments: where route code calls service/core code.
- Safety comments: physical device control, delayed verification, locks, or cache staleness.
- Compatibility comments: legacy payload fields or routes that must not be removed.

Avoid comments that restate obvious assignments.
