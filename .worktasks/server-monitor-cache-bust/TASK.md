# Task Memory

## Basic Info

- Task: server-monitor-cache-bust
- Module lock: templates_index
- Extra lock: global
- Branch: codex/12700k-server-monitor-cache-bust-20260528
- Worktree: D:\SmartCenter\smart-center-worktrees\server-monitor-cache-bust
- Machine: 12700k
- Kind: light
- Started: 2026-05-28
- Expected finish: 2026-05-28

## Goal

```text
Bump server monitor static asset query versions so production browsers load the merged hardware UI changes.
```

## Current Phase

```text
done
```

## Change Scope

```text
templates/index.html static asset version query strings only.
```

## Done

- Updated smart-center-time-ntp.css version query.
- Updated eager server-monitor.js version query.
- Updated lazy server-monitor.js version query.

## Verified

- `git diff --check`
- Diff only changes three query string values.

## Not Verified

- Live browser after production service reload.

## Risks

- High-risk file touched only for cache busting; templates_index and global locks acquired.

## Dependencies And Conflicts

```text
Requires production service/browser refresh after merge.
```

## Next

- Merge into production integration branch and release locks.
