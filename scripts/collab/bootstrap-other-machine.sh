#!/usr/bin/env bash
set -euo pipefail

MACHINE=""
WORKTREE_BASE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --machine) MACHINE="${2:-}"; shift 2 ;;
    --worktree-base) WORKTREE_BASE="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

if [ -z "$MACHINE" ]; then
  MACHINE="$(hostname | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"
fi

if [ -z "$WORKTREE_BASE" ]; then
  WORKTREE_BASE="$(cd "$ROOT/.." && pwd)/smart-center-worktrees"
fi

echo "== Smart Center collaboration bootstrap =="
echo "repo: $ROOT"
echo "machine: $MACHINE"
echo "worktree_base: $WORKTREE_BASE"
echo

git config user.name "codex-$MACHINE"
git config user.email "codex-$MACHINE@smart-center.local"
git config pull.rebase true
git config fetch.prune true
git config rerere.enabled true
git config merge.conflictstyle zdiff3
git config branch.autosetuprebase always

mkdir -p "$WORKTREE_BASE"

SMART_CENTER_WORKTREE_BASE="$WORKTREE_BASE" bash scripts/collab/setup-git-collab.sh

echo
echo "== sync check =="
SMART_CENTER_WORKTREE_BASE="$WORKTREE_BASE" bash scripts/collab/check-sync.sh

echo
echo "== recommended task commands =="
cat <<EOF
export SMART_CENTER_WORKTREE_BASE="$WORKTREE_BASE"

bash scripts/collab/start-work.sh --task server-monitor-refactor --module server_monitor --machine $MACHINE --kind heavy
bash scripts/collab/start-work.sh --task snmp-monitor-refactor --module snmp_monitor --machine $MACHINE --kind heavy
bash scripts/collab/start-work.sh --task frontend-module-split --module templates_index --machine $MACHINE --kind heavy
bash scripts/collab/start-work.sh --task core-config-cleanup --module config_core --machine $MACHINE --kind light
bash scripts/collab/start-work.sh --task validation-docs-report --module docs --machine $MACHINE --kind light
EOF

echo
echo "bootstrap done"
