# View JS Modules

This directory is the target for gradually extracting logic from `templates/index.html`.

Rules:

- Move one view at a time.
- Preserve existing global function names until all inline callers are migrated.
- Register each module with `window.SmartCenter.registerModule(name, metadata)`.
- Keep API URLs and payload fields stable.
- Validate the affected view in the 16:9 preview after each extraction.
