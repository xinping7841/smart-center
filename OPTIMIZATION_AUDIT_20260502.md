# Smart Center Optimization Audit - 2026-05-02

## Current Safe Point

Production path: `/srv/smart-center/current` -> `/srv/smart-center/releases/smart-center-release-20260405_230118`

Service: `smart-center.service`

## Completed Stages

- Stage 0 baseline backup: `/srv/smart-center/backups/staged/stage0-baseline-20260502_140921/`
- Stage 1 low-risk runtime cleanup: `/srv/smart-center/backups/staged/stage1-low-risk-20260502_141744/`
- Stage 2 static cache and precompressed vendor JS: `/srv/smart-center/backups/staged/stage2-static-cache-20260502_142925/`
- Stage 3 frontend GET fetch de-duplication: `/srv/smart-center/backups/staged/stage3-frontend-fetch-dedupe-20260502_143427/`
- Stage 4 CSS extraction to static asset: `/srv/smart-center/backups/staged/stage4-css-extract-20260502_143831/`

Each completed stage has a NAS copy under `/mnt/ubuntu01/smart-center-backups/staged/` and a `SHA256SUMS.txt` file.

## Measured Improvements

- `static/vendor/echarts.min.js` is now served as precompressed gzip when supported: about 1.1 MB -> about 362 KB.
- `static/smart-center.css` is now extracted from the main template and served as precompressed gzip: about 456 KB -> about 49 KB.
- Dashboard HTML gzip payload is reduced from about 214 KB to about 161 KB after CSS extraction.
- Static assets are served with `Cache-Control: public, max-age=31536000, immutable` and do not set the auth session cookie.
- Frontend `fetchJson()` now de-duplicates simultaneous GET requests by URL/options so multiple widgets can share the same in-flight response.

## Guardrails

- Do not modify strong-power, UPS, HVAC, sequencer, or light control protocol logic without a fresh backup and a focused test plan.
- The 32/40/50/70/77/9 network device polling is operationally sensitive; prefer cached status fan-out over adding new direct polling loops.
- NVR/HEVC messages still write to stderr from the video stack. Logrotate contains growth, but a future video phase should address decoder stderr suppression or capture options separately.
- Avoid broad UI rewrites in `templates/index.html`; it still contains repeated legacy function blocks, and later definitions override earlier ones.

## Known Structure Risks

- `templates/index.html` remains very large and mixes Jinja, HTML, UI state, polling, device control, and rendering logic.
- Some functions are defined once as old-style functions and later overridden by assignment-based implementations. This should be cleaned module by module, not by mass deletion.
- Direct `fetch()` calls still exist outside `fetchJson()`, especially in old control/render sections. Convert read-only GET calls gradually; leave POST/control paths conservative.
- Dashboard still fans out to many endpoints. A future `/api/dashboard/summary` endpoint can reduce first-load request count, but should be introduced read-only and side-by-side first.

## Suggested Next Stages

1. Extract non-control dashboard JavaScript into `/static/smart-center-dashboard.js` with a compatibility wrapper, after a fresh backup.
2. Add a read-only `/api/dashboard/summary` endpoint that aggregates existing cached statuses without extra PLC/device connections.
3. Convert dashboard-only widgets to consume the summary endpoint while keeping detail pages on existing endpoints.
4. Add a small developer audit script that lists duplicate function definitions and direct fetch endpoints before each UI change.
5. Move old root-level backup/debug files out of the release tree periodically, but never delete without an archive backup.
