# Frontend Split Plan

Last updated: 2026-05-22

The dashboard currently works, so frontend splitting must be done as behavior-preserving moves. Do not rewrite view logic while moving it.

## Current State

- `templates/index.html` is the main shell and contains large inline CSS/JS.
- Static CSS files are large and mostly shared.
- Most buttons still call global functions from inline `onclick` attributes.

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

1. Logs/event window.
2. Proxy monitor.
3. UPS page.
4. Current collector page.
5. M32R page if still isolated.

## Stage 2D: Extract Heavy Views

Recommended order after utilities are stable:

1. SNMP monitor.
2. Server monitor.
3. Power/meter dashboard.
4. Automation node canvas.
5. HVAC room cards.
6. NVR preview.

## Validation Checklist

For every extraction:

- Main dashboard loads with HTTP 200.
- Browser console has no new frontend errors posted to `/api/logs/frontend`.
- The target view opens from sidebar and direct `?view=<id>` link.
- The 1920x1080 preview still fits the main dashboard.
- Touch/mobile layout still opens the target view.
