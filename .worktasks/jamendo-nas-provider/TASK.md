# Task Memory

## Basic Info

- Task: jamendo-nas-provider
- Module lock: apple_audio
- Branch: codex/lk402-jamendo-nas-provider-20260526
- Worktree: D:\SmartCenter\smart-center-worktrees\jamendo-nas-provider
- Machine: lk402
- Kind: light
- Started: 2026-05-26 14:22:30
- Expected finish:

## Goal

Integrate NAS local music with an optional Jamendo API provider, simplify the music player UI, and improve local metadata, cover, and lyrics matching without merging directly to production first.

## Current Phase

merged

## Change Scope

- `apple_audio_core.py`
- `api/apple_audio.py`
- `config.py`
- `static/js/views/apple-audio.js`
- `static/smart-center.css`
- `static/smart-center-time-ntp.css`
- `static/smart-center-scene-card3.css`
- `templates/index.html`

## Done

- Created task worktree
- Acquired module worklock
- Added optional Jamendo search provider, disabled by default.
- Improved local track metadata fallback from filename and album folder.
- Added same-name sidecar cover matching before folder cover fallback.
- Added browser audio playback actions for NAS stream URLs and Jamendo audio URLs.
- Simplified the music player layout by hiding the right explanatory stack.

## Verified

- `python -m py_compile apple_audio_core.py api\apple_audio.py config.py`
- Apple audio smoke test for Jamendo remote track queueing and local metadata/cover fallback.

## Not Verified

- Full Flask/browser page verification was not run because this local shell Python lacks Flask.

## Risks

- Jamendo requires `jamendo_enabled` plus a configured client id or `JAMENDO_CLIENT_ID`.
- Runtime `config.json` and `music_tag_library.json` can be touched by service initialization and should not be included in this change.

## Dependencies And Conflicts

- Touches `templates/index.html` and `config.py`; no conflicting local changes were present in the worktree during merge prep.

## Next

- Create a post-merge backup.
