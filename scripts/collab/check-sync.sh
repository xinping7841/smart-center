#!/usr/bin/env bash
# AI_MODULE: collab_check_sync
# AI_PURPOSE: Show repository sync, dirty state, worktrees, and active Smart Center worklocks before code edits.
# AI_BOUNDARY: Read-only coordination check; it must not create branches, acquire locks, or modify source files.
# AI_DATA_FLOW: git remote/worktree/worklock metadata -> terminal status report for the operator or coding agent.
# AI_RUNTIME: Required first step before Smart Center edits on Mac/120/121/122/123 collaboration machines.
# AI_RISK: Low. Incorrect output can cause branch or lock collisions, but it does not touch real devices.
# AI_COMPAT: Output sections are referenced by collaboration runbooks; keep check names stable.
# AI_SEARCH_KEYWORDS: check-sync, worklock, worktree, collaboration, git status.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

WORKTREE_BASE="${SMART_CENTER_WORKTREE_BASE:-$(cd "$ROOT/.." && pwd)/smart-center-worktrees}"
LOCK_BRANCH="coordination/worklocks"

echo "== repo =="
echo "$ROOT"
echo

echo "== fetch =="
git fetch --all --prune
echo

echo "== branch/status =="
git status -sb
echo

echo "== upstream ahead/behind =="
if git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
  UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}')"
  COUNTS="$(git rev-list --left-right --count HEAD..."$UPSTREAM")"
  echo "upstream: $UPSTREAM"
  echo "ahead/behind: $COUNTS"
else
  echo "no upstream configured"
fi
echo

echo "== recent graph =="
git log --oneline --decorate --graph --all -20
echo

echo "== local dirty high-risk files =="
git status --porcelain -- \
  templates/index.html \
  api/server.py \
  snmp_core.py \
  config.py \
  background.py \
  app.py || true
echo

echo "== active worktrees under base =="
echo "base: $WORKTREE_BASE"
if [ -d "$WORKTREE_BASE" ]; then
  git worktree list --porcelain | awk -v base="$WORKTREE_BASE" '
    /^worktree / { path=substr($0, 10); inbase=(index(path, base)==1); if (inbase) print path }
  '
else
  echo "none"
fi
echo

echo "== worklocks =="
if git ls-remote --exit-code --heads origin "$LOCK_BRANCH" >/dev/null 2>&1; then
  git fetch origin "$LOCK_BRANCH:refs/remotes/origin/$LOCK_BRANCH" >/dev/null 2>&1 || true
  LOCKS="$(git ls-tree -r --name-only "origin/$LOCK_BRANCH" locks 2>/dev/null | grep '\.json$' || true)"
  if [ -z "$LOCKS" ]; then
    echo "no active locks"
  else
    echo "$LOCKS" | while IFS= read -r lock_file; do
      echo "--- $lock_file"
      git show "origin/$LOCK_BRANCH:$lock_file" 2>/dev/null || true
      echo
    done
  fi
else
  echo "worklock branch missing; run scripts/collab/setup-git-collab.sh"
fi
