# View CSS Modules

This directory is the target for gradually extracting view-specific CSS from `templates/index.html` and the large shared CSS files.

Rules:

- Start with isolated panels or modals.
- Keep selector names stable during the first move.
- Do not change layout behavior in the same commit as a move.
- Add a cache-busting query string in `templates/index.html` when a file is linked.

## Current Modules

- `dashboard-inline.css`: dashboard shell leftovers moved from the main template, including the automation node canvas modal and event-log table styles.
