# Codex 项目协作规则

本项目允许多台机器、多任务并行维护，但必须先保护现场。任何 Codex、本地 AI 或人工协作者在修改代码前，都要遵守本文件。

## 固定规则

- 每台机器最多同时运行 5 个并行任务。
- 每个任务必须使用独立 Git worktree 和独立分支。
- 每个任务必须有自己的 `.worktasks/<task>/TASK.md` 任务记忆。
- 跨任务共识必须写入 `docs/work-session-log/shared-decisions.md`。
- 修改前必须 `git fetch --all --prune`，检查远端更新。
- 修改前必须检查本地脏文件，不能静默覆盖。
- 修改前必须检查 `coordination/worklocks` 工作锁。
- 修改高风险模块前必须获取对应工作锁。
- 修改完成必须提交、推送、释放工作锁，并写清验证结果。

## 高风险文件

这些文件同一时间只能由一个任务修改：

```text
templates/index.html
api/server.py
snmp_core.py
config.py
background.py
app.py
```

如果任务会碰这些文件，必须同时获取对应模块锁和全局锁。

## 禁止操作

- 不得使用 `git reset --hard` 覆盖现场。
- 不得使用 `git checkout -- <file>` 回滚用户改动。
- 不得使用 `git clean -fd` 删除未知文件。
- 不得使用 `rsync --delete` 覆盖 Git 工作区。
- 夜间无人任务不得触发强电、时序电源、投影、空调、UPS、服务器关机重启、WOL 等真实控制动作。

## 推荐脚本

协作脚本位于：

```text
scripts/collab/
```

常用命令：

```bash
bash scripts/collab/setup-git-collab.sh
bash scripts/collab/check-sync.sh
bash scripts/collab/start-work.sh --task server-monitor-refactor --module server_monitor --machine 12700k
bash scripts/collab/finish-work.sh --message "refactor: split server monitor module" --release-lock server_monitor
```

Windows PowerShell without Git Bash:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/setup-git-collab.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/check-sync.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task server-monitor-refactor -Module server_monitor -Machine 12700k
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/finish-work.ps1 -Message "refactor: split server monitor module" -ReleaseLock server_monitor
```

## 工作方式

代码隔离依靠 Git worktree；模块占用依靠 worklock；任务记忆依靠 TASK.md；长期共识依靠 shared-decisions.md；最终可追溯依靠 Git commit。

