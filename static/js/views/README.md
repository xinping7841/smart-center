# View JS Modules

This directory is the target for gradually extracting logic from `templates/index.html`.

## Current Modules

- `logs.js`: event log, automation log, dashboard total log, and power detail log render helpers.
- `proxy.js`: node-121 proxy health page, dashboard proxy summary, link checks, client table, and traffic cards.
- `ups.js`: UPS dashboard/page/screen companion cards, `/api/ups/status` polling, and UPS shutdown command UI.
- `hy-edge.js`: HY506 edge room dashboard card, `/api/hy-edge/status` polling, and offline fallback rendering.
- `apple-audio.js`: music player page state, queue, lyrics, output list, and `/api/apple-audio/*` actions.
- `universal.js`: protocol control center and legacy universal command button shims for `/api/control_center/execute` and `/api/universal/control`.
- `env.js`: environment sensor polling, top/dashboard summaries, env page cards, and door/contact status bridge.
- `snmp.js`: SNMP/network monitor helper utilities, overview/detail render helpers, NAS/router/switch card rendering, interface summaries, and switch-port normalization.
- `server-monitor.js`: server monitor render helpers, hardware metric cards, CodeMeter display, diagnostic badges, and grouped server grid rendering.
- `power-meter.js`: shared power cabinet and meter display helpers, cabinet/channel labels, meter cards, reference summaries, and source badges.
- `automation-view.js`: automation runtime/status helpers, condition chips, schedule summaries, node data builders, and node HTML rendering.
- `dashboard-summary.js`: dashboard top counters, proxy/env summary bridge, and footer health summary render helpers.
- `hvac-view.js`: HVAC room grouping, status text, mode/fan/power display helpers, dashboard overview cards, and room temperature/humidity chips.
- `screen-runtime.js`: dashboard screen/curtain status cards, companion env/UPS/automation panels, and `/api/screen/control` command glue.
- `projector.js`: projector command normalization, PJLink/RS232 display formatting, inferred current evidence cards, dashboard/page projector cards, and remote-panel rendering helpers.
- `current-collector.js`: standalone current collector page, live polling, pause/resume display, group totals, raw channel cards, and `/api/current-collector/*` actions.
- `driver-hub.js`: standalone driver hub snapshot page, group filtering, health counters, and driver table rendering.
- `local-model.js`: local AI model console for the main sidebar view and standalone page, configuration form, health check, chat, and training data export UI.
- `login.js`: login page submit handler, remember-me local storage, and Enter-key shortcut.
- `lighting.js`: standalone legacy stage lighting page polling, log refresh, and unchanged jQuery control event bindings.

Rules:

- Move one view at a time.
- Preserve existing global function names until all inline callers are migrated.
- Register each module with `window.SmartCenter.registerModule(name, metadata)`.
- Keep API URLs and payload fields stable.
- Validate the affected view in the 16:9 preview after each extraction.
- Keep physical-control modules extra conservative: power cabinet, sequencer, projector, screen, door, light, and server shutdown/WOL code must keep existing lock, delay, and verification behavior unless testing on approved hardware.

Core-only note:

- `../core/viewport-layout.js`: early viewport preset detection for mobile, foldable/tablet, and desktop-site rendering. It must stay before CSS and view scripts in `templates/index.html`.
