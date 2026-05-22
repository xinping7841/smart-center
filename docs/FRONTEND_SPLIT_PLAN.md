# Frontend Split Plan

Last updated: 2026-05-22

The dashboard currently works, so frontend splitting must be done as behavior-preserving moves. Do not rewrite view logic while moving it.

## Current State

- `templates/index.html` is the main shell and contains large inline CSS/JS.
- Static CSS files are large and mostly shared.
- Most buttons still call global functions from inline `onclick` attributes.
- The following behavior-preserving modules have been extracted to `static/js/views/`: `logs.js`, `proxy.js`, `ups.js`, `hy-edge.js`, `apple-audio.js`, `universal.js`, `env.js`, `snmp.js`, `server-monitor.js`, `power-meter.js`, `automation-view.js`, `hvac-view.js`, `nvr-view.js`, `current-collector.js`, `m32r.js`, `driver-hub.js`, `local-model.js`, `login.js`, and `lighting.js`.

## Stage 2A: Bootstrap And Boundaries

Completed by adding `static/js/core/bootstrap.js` and this plan. This creates `window.SmartCenter` as a namespace and module registry without changing existing behavior.

## Stage 2B: Extract Shared Utilities

In progress. `static/js/core/utils.js` now provides shared API helpers, time/number formatting, permission helpers, toast display, frontend error reporting, and guarded execution helpers. The dashboard keeps legacy global function names but now delegates several wrappers to `SmartCenter.utils`; the config center now reuses shared API, escape, and time helpers while keeping its stricter local permission checks.

Candidate utilities to move first:

- API wrappers: `fetchJsonLoose`, `postJsonLoose`, error translation.
- Formatting helpers: HTML escaping, time formatting, number/unit formatting.
- Permission helpers: `ensurePermission`, disabled class/attributes.
- Toast/error reporting: `showToast`, `reportFrontendError`.

Keep global aliases during migration:

```js
window.fetchJsonLoose = SmartCenter.api.fetchJsonLoose;
```

## Stage 2C: Extract Low-Risk Views

Recommended order:

1. Logs/event window. Completed: `static/js/views/logs.js`.
2. Proxy monitor. Completed: `static/js/views/proxy.js`.
3. UPS page. Completed: `static/js/views/ups.js`.
4. HY edge room dashboard card. Completed: `static/js/views/hy-edge.js`.
5. Apple Audio music player. Completed: `static/js/views/apple-audio.js`.
6. Protocol/universal command shims. Completed: `static/js/views/universal.js`.
7. Environment sensor page and dashboard summary. Completed: `static/js/views/env.js`.
8. Current collector page. Completed: `static/js/views/current-collector.js`.
9. M32R page. Completed: `static/js/views/m32r.js`.
10. Driver hub page. Completed: `static/js/views/driver-hub.js`.
11. Local model page. Completed: `static/js/views/local-model.js`.
12. Login page. Completed: `static/js/views/login.js`.
13. Legacy lighting page. Completed: `static/js/views/lighting.js`.

## Stage 2D: Extract Heavy Views

Recommended order after utilities are stable:

1. SNMP monitor.
   - Completed: `static/js/views/snmp.js` now holds SNMP formatting, filters, storage/interface/switch helpers, overview/detail render helpers, and NAS/router/switch/NVR card rendering while `templates/index.html` keeps polling, selected-device state, and compatibility wrappers.
2. Server monitor.
   - Completed: `static/js/views/server-monitor.js` now holds server hardware/card render helpers, CodeMeter display helpers, diagnostics, offline snapshot markup, and grouped grid rendering. `templates/index.html` keeps polling, pending command state, WOL/shutdown/restart actions, sorting, and compatibility wrappers.
3. Power/meter dashboard.
   - In progress: `static/js/views/power-meter.js` now holds low-risk display helpers for cabinet names, channel labels, meter cards, reference summaries, meter chips, and source badges. `templates/index.html` still keeps live polling, ECharts instances, one-key start/stop, channel switching, locks, and delayed verification.
4. Automation node canvas.
   - Completed: `static/js/views/automation-view.js` now holds runtime status helpers, condition chips, schedule summaries, action labels, and node-flow data/HTML builders. `templates/index.html` still keeps modal state, drag/zoom, inline panel rendering, API status polling, rule enable/disable, and save actions.
5. HVAC room cards.
   - Completed: `static/js/views/hvac-view.js` now holds status/mode/fan/power display helpers, room grouping/sorting, room environment chips, dashboard overview HTML, and HVAC card/group rendering. `templates/index.html` still keeps polling, status cache, temperature/mode popover state, and `/api/hvac/control` actions.
6. NVR preview.
   - Completed: `static/js/views/nvr-view.js` now holds preview mode/grid helpers, stream/snapshot/MJPEG URL builders, channel buttons, and preview wall/single-frame markup. `templates/index.html` still keeps selection state, stream stop/cleanup, lazy iframe activation, snapshot refresh timers, and SNMP/NVR status polling.

## Stage 2 Safety Notes

- Do not combine view extraction with behavior changes. If a bug is found during extraction, either fix it in a separate commit or explicitly call out the coupled change.
- For physical-control views, preserve current command payloads, lock timing, pending state, delayed verification, and status fallback behavior.
- For modules still using inline `onclick`, exported globals are intentional compatibility shims. Remove them only after templates have been migrated to event binding.
- Static files are cached aggressively by browsers and the public reverse proxy. Bump the query string in `templates/index.html` whenever a view module changes.

## Validation Checklist

For every extraction:

- Main dashboard loads with HTTP 200.
- Browser console has no new frontend errors posted to `/api/logs/frontend`.
- The target view opens from sidebar and direct `?view=<id>` link.
- The 1920x1080 preview still fits the main dashboard.
- Touch/mobile layout still opens the target view.
