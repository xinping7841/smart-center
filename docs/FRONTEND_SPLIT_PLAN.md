# Frontend Split Plan

Last updated: 2026-05-22

The dashboard currently works, so frontend splitting must be done as behavior-preserving moves. Do not rewrite view logic while moving it.

## Current State

- `templates/index.html` is the main shell and contains large inline CSS/JS.
- Static CSS files are large and mostly shared.
- Most buttons still call global functions from inline `onclick` attributes.
- The following behavior-preserving modules have been extracted to `static/js/views/`: `logs.js`, `proxy.js`, `ups.js`, `hy-edge.js`, `apple-audio.js`, `universal.js`, and `env.js`.

## Stage 2A: Bootstrap And Boundaries

Completed by adding `static/js/core/bootstrap.js` and this plan. This creates `window.SmartCenter` as a namespace and module registry without changing existing behavior.

## Stage 2B: Extract Shared Utilities

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
9. M32R page if still isolated.

## Stage 2D: Extract Heavy Views

Recommended order after utilities are stable:

1. SNMP monitor.
2. Server monitor.
3. Power/meter dashboard.
4. Automation node canvas.
5. HVAC room cards.
6. NVR preview.

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
