# Clean Architecture Lab 2026-05-22

This branch is a local clean-lab refactor. Production code and runtime data are not changed by this document or branch until it is explicitly merged and deployed.

## Goals

- Keep the production branch stable while cleaning the local code shape.
- Move only confirmed runtime code into clearer ownership boundaries.
- Remove root-level historical/generated files that are not source of truth.
- Add a shared safety guard so validation can run in dry-run/read-only mode without moving real devices.

## Structural Changes

- `app.py` is now a thin service entrypoint.
- Flask assembly moved to `modules/app/`:
  - `factory.py`: Flask object, template/static paths, config.
  - `blueprints.py`: single blueprint registry and stable registration order.
  - `request_hooks.py`: auth context, static cache policy, gzip handling.
  - `server.py`: bounded thread-pool WSGI server.
- `runtime/control_safety.py` adds `SMART_CENTER_CONTROL_MODE` support:
  - `normal`: current production behavior.
  - `dry_run`: return success-like dry-run payload, send no physical command.
  - `read_only`: block control requests.
  - `disabled`: block control requests.

## Physical-Control Guard Coverage

The guard is now checked before hardware or command-queue actions in:

- Strong-current cabinet channel and one-key actions.
- Lighting relay actions.
- Projector commands.
- Screen movement and calibration.
- Sequencer controls.
- UPS shutdown command.
- HVAC commands.
- Protocol control center and legacy universal control.
- Server WOL and shutdown/restart/refresh command queue.
- Automation scene actions before they reach device drivers.

## Removed From Source

These files were deleted from the clean-lab branch because current code and docs already identify them as historical, generated, or runtime artifacts:

- Root duplicate page/API leftovers: `index.html`, `power.py`, `api/server_new.py`.
- Generated or downloaded agent scratch files: `_agent_from_server.ps1`, `_agent_test.ps1`, `_downloaded_agent_*.ps1`, `_generated_agent_*.ps1`, `_remote_agent_worker_20260403.ps1`.
- Door reference images that belong under runtime data, not source: `door_ref_closed.jpg`, `door_ref_open.jpg`.
- Temporary dataset merge script: `tmp_merge_door_datasets.py`.

## Compatibility Notes

- Public route paths are preserved.
- `templates/` and `static/` are explicitly resolved from `paths.PROJECT_ROOT`, so moving app creation into `modules/app/` does not change asset lookup.
- Normal production control behavior is unchanged unless a control-mode environment variable or request header is set.

## Validation Plan

- Python compile checks for `app.py`, `api/`, `services/`, `runtime/`, `modules/`, `config.py`, `background.py`, and `snmp_core.py`.
- Flask URL map import smoke test with background startup disabled by using the app factory directly where possible.
- Dry-run API smoke checks for representative control endpoints.
- Before production merge, deploy to a test port with `SMART_CENTER_CONTROL_MODE=dry_run` and confirm pages/API load without sending real device commands.
