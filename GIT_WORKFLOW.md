# Smart Center Git Workflow

- `main` is the production baseline used for node-120 deployment.
- Development machines should create their own branches, for example `codex/mac-*` and `codex/12700k-*`.
- Pull before editing: `git fetch origin && git pull --rebase origin main`.
- Commit small changes frequently.
- Do not copy whole folders over `/srv/smart-center/current`; merge through Git, then deploy.
- Runtime data, backups, caches, logs, and databases are backed up outside Git.

## Frontend Split Map

- `templates/index.html`: Jinja-rendered markup and the three server-injected globals only.
- `static/js/smart-center-bootstrap.js`: early viewport/layout bootstrap that must run in `<head>`.
- `static/css/automation-node-canvas.css`: automation node canvas modal styling.
- `static/js/smart-center-core.js`: global state, permissions, polling, dashboard helpers, shared utilities.
- `static/js/smart-center-automation.js`: automation rules, condition chips, logs, node canvas, automation editor.
- `static/js/smart-center-power-meter-ups.js`: power cabinets, meter center, UPS cards and related charts.
- `static/js/smart-center-snmp-nvr.js`: SNMP/NVR cards, detail panels, camera preview helpers.
- `static/js/smart-center-layout-devices.js`: layout, navigation, sequencers, HVAC, door, lights, servers, projectors, screen controls.
- `static/js/smart-center-management.js`: proxy detail, server management, config-style interactions, late automation save helpers.

When two machines edit in parallel, prefer touching different files from this map. If a change needs moving code between files, do that in a dedicated refactor branch before feature work.
