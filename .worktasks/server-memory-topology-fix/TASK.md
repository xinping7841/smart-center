# Task Memory

## Basic Info

- Task: server-memory-topology-fix
- Module lock: server_monitor
- Branch: codex/mac-server-memory-topology-fix-20260604
- Worktree: /Users/wanghongyu/Documents/New project/smart-center-clean
- Machine: mac
- Started: 2026-06-04

## Goal

Fix server monitor hardware recognition for Linux DIMM locator channel labels, memory speed fallback, and CPU core/thread display.

## Scope

- Linux agent and local Linux monitor hardware parsing.
- Windows agent CPU topology payload.
- Server monitor detail text only; no power/control button execution.

## Notes

- node-123 reports DIMM_A1/B1/C1/D1, which previously stayed `channel_mode: unknown`.
- CPU topology must be included in the final machine status payload, not only the hardware cache.
