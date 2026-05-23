# Smart Center 干净基线开发入口

本文是 2026-05-24 起的新开发入口。后续多台机器只使用 clean 基线仓库，旧目录只作为历史备份参考，不再作为开发入口。

## 统一远端

```text
node-120-ts:/srv/git/smart-center-clean.git
```

## 推荐目录

Windows：

```text
D:\SmartCenter\smart-center-clean
D:\SmartCenter\smart-center-worktrees
```

macOS：

```text
/Users/wanghongyu/Documents/New project/smart-center-clean
/Users/wanghongyu/Documents/New project/smart-center-worktrees
```

## 首次拉取

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force D:\SmartCenter
Set-Location D:\SmartCenter
git clone node-120-ts:/srv/git/smart-center-clean.git smart-center-clean
Set-Location D:\SmartCenter\smart-center-clean
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/bootstrap-other-machine.ps1 -Machine 12700k -WorktreeBase D:\SmartCenter\smart-center-worktrees
```

Windows Git Bash：

```bash
mkdir -p /d/SmartCenter
cd /d/SmartCenter
git clone node-120-ts:/srv/git/smart-center-clean.git smart-center-clean
cd smart-center-clean
bash scripts/collab/bootstrap-other-machine.sh --machine 12700k --worktree-base /d/SmartCenter/smart-center-worktrees
```

macOS：

```bash
cd "/Users/wanghongyu/Documents/New project/smart-center-clean"
bash scripts/collab/bootstrap-other-machine.sh --machine mac --worktree-base "/Users/wanghongyu/Documents/New project/smart-center-worktrees"
```

## 每次开始前

```bash
bash scripts/collab/check-sync.sh
```

确认以下条件满足再动代码：

- `git status -sb` 没有未处理的脏文件。
- 本地与 `origin/main` 没有 ahead/behind 差异。
- 目标模块没有工作锁。
- 当前机器活动 worktree 少于 5 个。

## 创建任务

每个任务单独 worktree、单独分支、单独任务记忆。

```bash
bash scripts/collab/start-work.sh --task <task-name> --module <module-lock> --machine <machine-name> --kind light
```

示例：

```bash
bash scripts/collab/start-work.sh --task snmp-card-fix --module snmp_monitor --machine mac --kind light
```

## 完成任务

在任务 worktree 内执行：

```bash
bash scripts/collab/finish-work.sh --message "fix: describe change" --release-lock <module-lock>
```

## 固定原则

- 不在 `/srv/smart-center/current` 里直接改代码。
- 不再从旧仓库或旧备份目录开始新任务。
- 不用 `git reset --hard`、`git checkout -- <file>`、`git clean -fd` 清理问题。
- 高风险文件必须先锁模块：`templates/index.html`、`api/server.py`、`snmp_core.py`、`config.py`、`background.py`、`app.py`。
- 生产切换只从 clean Git 生成新 release，运行数据继续使用 `/srv/smart-center-data`。

