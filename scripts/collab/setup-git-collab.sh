#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

WORKTREE_BASE="${SMART_CENTER_WORKTREE_BASE:-$(cd "$ROOT/.." && pwd)/smart-center-worktrees}"
LOCK_BRANCH="coordination/worklocks"

echo "[setup] repo: $ROOT"
echo "[setup] worktree base: $WORKTREE_BASE"

git config pull.rebase true
git config fetch.prune true
git config rerere.enabled true
git config merge.conflictstyle zdiff3
git config branch.autosetuprebase always

mkdir -p "$WORKTREE_BASE"

if git remote get-url origin >/dev/null 2>&1; then
  echo "[setup] origin: $(git remote get-url origin)"
else
  echo "[setup] warning: origin remote is missing"
fi

if git ls-remote --exit-code --heads origin "$LOCK_BRANCH" >/dev/null 2>&1; then
  echo "[setup] worklock branch exists: origin/$LOCK_BRANCH"
  git fetch origin "$LOCK_BRANCH:$LOCK_BRANCH" >/dev/null 2>&1 || true
else
  echo "[setup] creating worklock branch: $LOCK_BRANCH"
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/smart-center-locks.XXXXXX")"
  cleanup() {
    git worktree remove --force "$TMP_DIR" >/dev/null 2>&1 || true
    rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  git worktree add --detach "$TMP_DIR" HEAD >/dev/null
  (
    cd "$TMP_DIR"
    git switch --orphan "$LOCK_BRANCH" >/dev/null
    git rm -rf . >/dev/null 2>&1 || true
    mkdir -p locks
    printf "# Smart Center worklocks\n\nThis branch stores module work locks only.\n" > README.md
    printf "" > locks/.gitkeep
    git add README.md locks/.gitkeep
    git commit -m "chore: initialize worklocks" >/dev/null
    git push -u origin "$LOCK_BRANCH" >/dev/null
  )
  trap - EXIT
  cleanup
  echo "[setup] worklock branch created and pushed"
fi

echo "[setup] done"

