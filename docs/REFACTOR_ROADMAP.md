# Safe Refactor Roadmap

Last updated: 2026-05-22

The objective is to make Smart Center modular and local-AI friendly without breaking current production behavior.

## Stage 0: Baseline And Guardrails

- Create a Git tag and a lightweight source backup before each stage.
- Record current API response sizes and representative timings.
- Keep production route paths stable.
- Do not include recordings, datasets, model outputs, backup tarballs, or generated agent scripts in code backups.

## Stage 1: Documentation And Source Hygiene

- Add architecture, module index, AI navigation, and per-module notes.
- Expand `.gitignore` for runtime/generated files.
- Move tracked legacy files to `archive/legacy/` only after a separate backup.
- Keep runtime data outside Git.

## Stage 2: Frontend Split Without Behavior Change

- Extract shared JS utilities from `templates/index.html` into `static/js/core/`.
- Extract view modules one at a time into `static/js/views/`.
- Start with low-risk pages, then heavy views: SNMP, server monitor, power, automation.
- Keep `window.*` compatibility wrappers during the transition.

## Stage 3: API And Service Split

- Keep `api/*.py` route signatures stable.
- Move business logic into `modules/<name>/service.py` or existing `services/`.
- Priority: `server_monitor`, `power`, `snmp_monitor`, `automation`.
- Add payload snapshot scripts before changing any response structure.

## Stage 4: Performance

- Make dashboard APIs compact by default and detail APIs explicit.
- Add lazy loading for SNMP details, server hardware details, and power charts.
- Cache remote meter payloads and projector status more consistently.
- Prefer background pollers over route-time device access.

## Stage 5: Independent Module Packaging

Power statistics is the best first candidate for extraction:

- Define a module boundary around meter rows, cabinet status, energy history, exports, and UI payloads.
- Keep cabinet control adapters separate from read-only statistics.
- Produce a minimal API contract so the same module can run inside Smart Center or independently.

## Done Criteria For Each Stage

- `python -m py_compile` passes for touched Python files.
- Relevant APIs return HTTP 200 from node-120 loopback.
- Main page still renders.
- Git status contains only intended changes.
- Backup path and commit hash are recorded in the final note.
