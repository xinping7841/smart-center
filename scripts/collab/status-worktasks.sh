#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

WORKTREE_BASE="${SMART_CENTER_WORKTREE_BASE:-$(cd "$ROOT/.." && pwd)/smart-center-worktrees}"

echo "worktree base: $WORKTREE_BASE"
echo

git worktree list --porcelain | awk -v base="$WORKTREE_BASE" '
  /^worktree / {
    path=substr($0, 10)
    if (index(path, base)==1) {
      print path
    }
  }
' | while IFS= read -r wt; do
  echo "== $wt =="
  if [ -d "$wt/.git" ] || [ -f "$wt/.git" ]; then
    (cd "$wt" && git status -sb)
  fi
  find "$wt/.worktasks" -maxdepth 2 -name STATUS.json -print 2>/dev/null | while IFS= read -r status; do
    echo "--- $status"
    cat "$status"
    echo
  done
  echo
done

