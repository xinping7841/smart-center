# Task Memory

## Basic Info

- Task: ui-style-switcher
- Branch: codex/12700k-ui-style-switcher-20260608
- Worktree: D:/SmartCenter/smart-center-worktrees/ui-style-switcher
- Machine: 12700k
- Kind: light
- Started: 2026-06-08 11:52:45

## Goal

Add a temporary homepage UI style switcher so the team can compare Ops, Apple, Meizu, and Smartisan visual directions before fixing the final Smart Center theme.

## Scope

- `templates/index.html`
- `static/css/views/ui-style-review.css`
- `static/js/views/ui-style-review.js`
- `.worktasks/ui-style-switcher/`

## Collaboration Locks

- `frontend_assets`
- `templates_index`

## Design / Cleanup Decision

This is a removable review layer, not a permanent product feature.

Cleanup when final UI style is fixed:

1. Remove `static/css/views/ui-style-review.css`.
2. Remove `static/js/views/ui-style-review.js`.
3. In `templates/index.html`, delete all blocks marked `UI_STYLE_REVIEW_REMOVE_START` to `UI_STYLE_REVIEW_REMOVE_END`.
4. Also search `data-ui-review-remove`, `ui-style-review`, and `ui-style-switcher` to confirm no temporary review hooks remain.

## Implemented

- Added a top-header segmented style switcher with four styles: Ops, Apple, Meizu, Smartisan.
- Scoped all variant overrides to `body[data-ui-review-style]`.
- Kept default style as `ops`, preserving the current production visual direction unless the user chooses another local preference.
- Stored the selected style in `localStorage` key `smartCenterUiReviewStyle`.
- Added keyboard ArrowLeft / ArrowRight switching.
- Added `AI_*` markers to the new CSS and JS files.
- Updated the `templates/index.html` AI header to document the removable review layer.
- Marked all temporary template hooks with `data-ui-review-remove="1"` plus explicit `UI_STYLE_REVIEW_REMOVE_*` comments.

## Verified

- `node --check static/js/views/ui-style-review.js`
- Static Node DOM harness for `ui-style-review.js`: default Ops style, click switching, ArrowLeft / ArrowRight switching, `localStorage`, and no-switcher defensive path.
- `python -m compileall app.py api services runtime config.py background.py power.py snmp_core.py`
- `git diff --check`

## Not Run

- Full Flask runtime preview was not started because importing the main app can start runtime/background pollers. This task is UI-only and real-device control must remain read-only unless explicitly authorized.
- In-app browser `data:` sandbox preview was blocked by browser security policy; no workaround was attempted.

## Risk Notes

- Visual-only CSS uses broad but scoped selectors, so contrast and density should be reviewed on the real homepage before final release.
- No API calls, navigation changes, permission changes, or device-control behavior were added.
