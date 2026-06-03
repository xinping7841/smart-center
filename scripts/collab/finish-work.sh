#!/usr/bin/env bash
# AI_MODULE: collab_finish_work
# AI_PURPOSE: Run final checks, optionally commit/push, and release a Smart Center module worklock.
# AI_BOUNDARY: Does not deploy production by itself; release locks only after validation or explicit decision.
# AI_DATA_FLOW: task worktree -> git status/diff/compileall -> optional commit/push -> coordination/worklocks unlock.
# AI_RUNTIME: Last step of a Smart Center source-edit task.
# AI_RISK: Medium. Releasing the wrong lock or committing unrelated files can disrupt parallel work.
# AI_COMPAT: Keep --message and --release-lock flags stable for Codex and human runbooks.
# AI_SEARCH_KEYWORDS: finish-work, release lock, compileall, commit, push.
set -euo pipefail

MESSAGE=""
RELEASE_LOCK=""
LOCK_BRANCH="coordination/worklocks"

while [ $# -gt 0 ]; do
  case "$1" in
    --message) MESSAGE="${2:-}"; shift 2 ;;
    --release-lock) RELEASE_LOCK="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

echo "== status =="
git status -sb
echo

echo "== diff stat =="
git diff --stat || true
echo

echo "== compile check =="
if command -v python3 >/dev/null 2>&1; then
  COMPILE_TARGETS=()
  for target in app.py api services runtime modules core config.py background.py power.py snmp_core.py; do
    if [ -e "$target" ]; then
      COMPILE_TARGETS+=("$target")
    fi
  done
  if [ "${#COMPILE_TARGETS[@]}" -eq 0 ]; then
    echo "no python compile targets found"
  else
    python3 -m compileall "${COMPILE_TARGETS[@]}" >/tmp/smart-center-finish-compile.log 2>&1 || {
    echo "compile failed; see /tmp/smart-center-finish-compile.log"
    sed -n '1,160p' /tmp/smart-center-finish-compile.log
    exit 1
    }
  fi
else
  echo "python3 missing, skip compile"
fi
echo

if [ -n "$MESSAGE" ]; then
  if [ -z "$(git status --porcelain)" ]; then
    echo "no changes to commit"
  else
    git add -A
    git commit -m "$MESSAGE"
  fi
  CURRENT_BRANCH="$(git branch --show-current)"
  git push -u origin "$CURRENT_BRANCH"
else
  echo "no --message provided; skip commit and push"
fi

if [ -n "$RELEASE_LOCK" ]; then
  if ! git ls-remote --exit-code --heads origin "$LOCK_BRANCH" >/dev/null 2>&1; then
    echo "worklock branch missing, skip release"
    exit 0
  fi
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/smart-center-locks.XXXXXX")"
  cleanup() {
    git worktree remove --force "$TMP_DIR" >/dev/null 2>&1 || true
    rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  git fetch origin "$LOCK_BRANCH:refs/remotes/origin/$LOCK_BRANCH" >/dev/null 2>&1 || true
  git worktree add --detach "$TMP_DIR" "origin/$LOCK_BRANCH" >/dev/null
  (
    cd "$TMP_DIR"
    git switch -C "$LOCK_BRANCH" "origin/$LOCK_BRANCH" >/dev/null
    LOCK_FILE="locks/${RELEASE_LOCK}.json"
    if [ -f "$LOCK_FILE" ]; then
      rm -f "$LOCK_FILE"
      git add -u "$LOCK_FILE"
      git commit -m "unlock: $RELEASE_LOCK" >/dev/null
      git push origin "$LOCK_BRANCH" >/dev/null
      echo "released lock: $RELEASE_LOCK"
    else
      echo "lock not found: $RELEASE_LOCK"
    fi
  )
  trap - EXIT
  cleanup
fi

echo "finish done"
