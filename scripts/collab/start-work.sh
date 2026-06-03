#!/usr/bin/env bash
# AI_MODULE: collab_start_work
# AI_PURPOSE: Create one task worktree/branch and acquire a module worklock for Smart Center collaboration.
# AI_BOUNDARY: Coordinates Git/worklock state only; it does not deploy, publish, or edit production runtime files.
# AI_DATA_FLOW: origin/main + coordination/worklocks -> task worktree, branch, .worktasks metadata, lock JSON.
# AI_RUNTIME: Run before implementation work when a Smart Center task needs source edits.
# AI_RISK: Medium. Wrong module names or branch reuse can block teammates or mix unrelated tasks.
# AI_COMPAT: Keep --task, --module, --machine, --kind, and --base flags stable for existing workflows.
# AI_SEARCH_KEYWORDS: start-work, worktree, branch, worklock, .worktasks.
set -euo pipefail

TASK=""
MODULE=""
MACHINE=""
KIND="light"
BASE_REF="origin/main"
LOCK_BRANCH="coordination/worklocks"

while [ $# -gt 0 ]; do
  case "$1" in
    --task) TASK="${2:-}"; shift 2 ;;
    --module) MODULE="${2:-}"; shift 2 ;;
    --machine) MACHINE="${2:-}"; shift 2 ;;
    --kind) KIND="${2:-light}"; shift 2 ;;
    --base) BASE_REF="${2:-origin/main}"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

if [ -z "$TASK" ] || [ -z "$MODULE" ] || [ -z "$MACHINE" ]; then
  echo "用法: bash scripts/collab/start-work.sh --task <task> --module <module> --machine <machine> [--kind light|heavy]"
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

WORKTREE_BASE="${SMART_CENTER_WORKTREE_BASE:-$(cd "$ROOT/.." && pwd)/smart-center-worktrees}"
WORKTREE_PATH="$WORKTREE_BASE/$TASK"
DATE_TAG="$(date +%Y%m%d)"
BRANCH="codex/${MACHINE}-${TASK}-${DATE_TAG}"
LOCK_FILE="locks/${MODULE}.json"

git fetch --all --prune
mkdir -p "$WORKTREE_BASE"

ACTIVE_COUNT="$(git worktree list --porcelain | awk -v base="$WORKTREE_BASE" '/^worktree / { path=substr($0, 10); if (index(path, base)==1) count++ } END { print count+0 }')"
if [ "$ACTIVE_COUNT" -ge 5 ] && [ ! -d "$WORKTREE_PATH" ]; then
  echo "当前机器已有 $ACTIVE_COUNT 个并行 worktree，达到上限 5。"
  exit 1
fi

if git ls-remote --exit-code --heads origin "$LOCK_BRANCH" >/dev/null 2>&1; then
  git fetch origin "$LOCK_BRANCH:refs/remotes/origin/$LOCK_BRANCH" >/dev/null 2>&1 || true
  if git cat-file -e "origin/$LOCK_BRANCH:$LOCK_FILE" 2>/dev/null; then
    echo "模块已被锁定: $MODULE"
    git show "origin/$LOCK_BRANCH:$LOCK_FILE" || true
    exit 1
  fi
else
  echo "工作锁分支不存在，请先运行: bash scripts/collab/setup-git-collab.sh"
  exit 1
fi

if [ -e "$WORKTREE_PATH" ]; then
  echo "worktree 已存在: $WORKTREE_PATH"
  exit 1
fi

git worktree add -b "$BRANCH" "$WORKTREE_PATH" "$BASE_REF"

mkdir -p "$WORKTREE_PATH/.worktasks/$TASK"
cat > "$WORKTREE_PATH/.worktasks/$TASK/TASK.md" <<EOF_TASK
# 任务记忆

## 基本信息

- 任务名：$TASK
- 模块锁：$MODULE
- 分支：$BRANCH
- Worktree 路径：$WORKTREE_PATH
- 执行机器：$MACHINE
- 任务类型：$KIND
- 开始时间：$(date '+%Y-%m-%d %H:%M:%S')
- 预计结束：

## 目标

\`\`\`text
填写本任务要完成的目标
\`\`\`

## 当前阶段

\`\`\`text
进行中
\`\`\`

## 修改范围

\`\`\`text
填写预计或实际修改的文件
\`\`\`

## 已完成

- 创建任务 worktree
- 获取模块工作锁

## 已验证

- 

## 未验证

- 

## 风险点

- 

## 依赖和冲突

\`\`\`text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
\`\`\`

## 下一步

- 
EOF_TASK

cat > "$WORKTREE_PATH/.worktasks/$TASK/STATUS.json" <<EOF_STATUS
{
  "task": "$TASK",
  "module": "$MODULE",
  "machine": "$MACHINE",
  "kind": "$KIND",
  "branch": "$BRANCH",
  "worktree": "$WORKTREE_PATH",
  "started_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "status": "in_progress"
}
EOF_STATUS

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/smart-center-locks.XXXXXX")"
cleanup() {
  git worktree remove --force "$TMP_DIR" >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT
git worktree add --detach "$TMP_DIR" "origin/$LOCK_BRANCH" >/dev/null
(
  cd "$TMP_DIR"
  git switch -C "$LOCK_BRANCH" "origin/$LOCK_BRANCH" >/dev/null
  mkdir -p locks
  cat > "$LOCK_FILE" <<EOF_LOCK
{
  "module": "$MODULE",
  "owner_machine": "$MACHINE",
  "owner_branch": "$BRANCH",
  "task": "$TASK",
  "kind": "$KIND",
  "worktree": "$WORKTREE_PATH",
  "started_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "expected_until": "",
  "note": "created by scripts/collab/start-work.sh"
}
EOF_LOCK
  git add "$LOCK_FILE"
  git commit -m "lock: $MODULE by $MACHINE" >/dev/null
  git push origin "$LOCK_BRANCH" >/dev/null
)
trap - EXIT
cleanup

echo "任务已创建:"
echo "  worktree: $WORKTREE_PATH"
echo "  branch:   $BRANCH"
echo "  lock:     $MODULE"
echo
echo "进入任务目录:"
echo "  cd \"$WORKTREE_PATH\""
