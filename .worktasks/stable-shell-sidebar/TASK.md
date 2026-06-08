# stable-shell-sidebar

## Goal
Fix the Smart Center main shell so the sidebar, header, and content offset keep the same desktop dimensions while switching between pages. The user-visible target is to remove the "jump" caused by dashboard and detail pages using different shell widths.

## Scope
- Frontend CSS/JS/template cache versioning only.
- No device-control behavior or API payload changes.
- Verification must use page navigation/read-only inspection only.

## Collaboration
- Branch: `codex/12700k-stable-shell-sidebar-20260608`
- Worktree: `D:/SmartCenter/smart-center-worktrees/ui-review-tone-down`
- Locks: `frontend_assets`, `templates_index`

## Verification Notes
- `node --check static/js/app-runtime.js`: passed.
- `git diff --check`: passed with CRLF warnings only.
- Local HTTP browser harness at 3840x2160 loaded the real template CSS chain and toggled dashboard -> light -> dashboard. Measured stable shell metrics on all three samples: sidebar width 224px, main left 224px, top header height 65px, nav item height 36px.
- Verification is read-only page layout inspection; no real device control was triggered.
