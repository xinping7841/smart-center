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
- `snmp.js`: SNMP/network monitor helper utilities, overview/detail render helpers, NAS/router/switch/NVR card rendering, interface summaries, and switch-port normalization.
- `current-collector.js`: standalone current collector page, live polling, pause/resume display, group totals, raw channel cards, and `/api/current-collector/*` actions.
- `m32r.js`: standalone M32R virtual console page, mixer status polling, channel/main controls, templates, and Apple Audio route helpers.
- `driver-hub.js`: standalone driver hub snapshot page, group filtering, health counters, and driver table rendering.
- `local-model.js`: standalone local AI model console, configuration form, health check, chat, and training data export UI.
- `login.js`: login page submit handler, remember-me local storage, and Enter-key shortcut.
- `lighting.js`: standalone legacy stage lighting page polling, log refresh, and unchanged jQuery control event bindings.

Rules:

- Move one view at a time.
- Preserve existing global function names until all inline callers are migrated.
- Register each module with `window.SmartCenter.registerModule(name, metadata)`.
- Keep API URLs and payload fields stable.
- Validate the affected view in the 16:9 preview after each extraction.
- Keep physical-control modules extra conservative: power cabinet, sequencer, projector, screen, door, light, and server shutdown/WOL code must keep existing lock, delay, and verification behavior unless testing on approved hardware.
