# Smart Center Architecture

Last updated: 2026-05-22

This document is the human and local-AI map for the Smart Center codebase. Keep it current before adding large features.

## Runtime Shape

Smart Center is a Flask application running on node-120. The service entry is `app.py`; application assembly lives in `modules/app/`; registered blueprints live under `api/`; long-running pollers live in `background.py` and `runtime/`; and device/protocol helpers live in `*_core.py`, `drivers/`, and `services/`.

The current production source of truth is `/srv/git-work/smart-center-main`. Runtime releases are copied to `/srv/smart-center/releases/*` and exposed through `/srv/smart-center/current`.

## Layers

- UI layer: `templates/` and `static/`. `templates/index.html` is still the main dashboard shell and currently contains a lot of inline JavaScript. Future UI work should move view-specific logic into `static/js/views/` and style into `static/css/views/` while keeping URLs stable.
- API layer: `api/*.py`. Routes should be thin: validate request, call a service/core function, return a stable payload.
- Service/core layer: `services/`, `*_core.py`, and `drivers/`. This is where device protocols, parsing, inference, and payload shaping should live.
- Runtime state layer: `runtime/state.py`, `background.py`, and JSON/SQLite files under runtime paths. API routes should prefer cached runtime state for fast page loads.
- Configuration layer: `config.py` and `config.json`. Large compatibility migrations should be documented because they strongly affect old deployments.
- Data/log layer: `data_logger.py`, `event_logger.py`, SQLite DBs, CSV reports, and remote meter service data.

## High-Risk Files

- `templates/index.html`: main UI shell, about 14k lines. Avoid parallel edits. Split by view before doing large UI work.
- `api/server.py`: server monitoring and Windows/Linux Agent distribution, about 7k lines. Agent version must be bumped whenever generated agent code changes.
- `snmp_core.py`: SNMP polling and vendor summary logic. Keep raw polling, vendor parsing, and UI summary shaping separated during future refactors.
- `background.py`: background polling loops for many devices. Avoid adding blocking work here without interval/concurrency limits.
- `config.py`: config defaults and migrations. Any change can alter many modules at startup.

## Stable URLs To Preserve

The current UI and external tools expect these URLs to remain compatible:

- `/` main dashboard
- `/config` configuration center
- `/api/status`, `/api/meters`, `/api/logs` power and meter data
- `/api/snmp/status` SNMP status
- `/api/machines`, `/report`, `/agent/config`, `/agent/worker.json`, `/deploy_agent.bat` server monitor and agents
- `/api/automation/status`, `/api/automation/logs` automation
- `/api/hvac/status`, `/api/sequencer/status`, `/api/ups/status`, `/api/projector/status`, `/api/light/status`

## Performance Baseline From 2026-05-22

Measured from node-120 loopback. These numbers are a baseline, not a pass/fail test.

- `/`: about 1.2 MB response, fast server-side but heavy client parse/render.
- `/api/snmp/status`: about 619 KB full response.
- `/api/machines`: about 358 KB full response.
- `/api/meters`: about 1.08 s in one sample, likely remote meter service or payload shaping.
- `/api/projector/status`: about 0.33 s in one sample.

Primary optimization direction: keep current routes but add compact/default payloads, lazy-load detail views, and move expensive collection to background caches.

## Refactor Rules

- Preserve existing route paths and response fields during module extraction.
- Before moving logic, add tests or snapshot scripts for the current payload shape.
- Prefer adapters around legacy functions over rewriting protocol code in one step.
- Do not keep backups, generated files, local recordings, datasets, or runtime DBs in Git.
- If a module controls physical devices, keep locks, delays, and verification behavior unchanged unless explicitly testing on safe hardware.
- For unattended validation, set `SMART_CENTER_CONTROL_MODE=dry_run` or `read_only` so physical device routes return controlled responses without sending commands.

## Recommended Target Structure

```text
api/                    thin Flask route modules
modules/                future feature packages with API-independent logic
  power/
  server_monitor/
  snmp_monitor/
  automation/
  hvac/
services/               shared external service adapters
runtime/                runtime state, background helpers, volatile data
static/js/core/         shared browser utilities
static/js/views/        one file per UI view
static/css/core/        variables, layout, shared components
static/css/views/       one file per UI view
docs/                   architecture and AI navigation docs
archive/legacy/         old implementations kept only for historical reference
```
