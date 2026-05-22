# 另一台机器首次对接和目录建设

这份文档给 12700K、其他本地 Windows 机器或笔记本使用。目标是让另一台机器加入协作后，能看到工作锁、创建最多 5 个并行 worktree，并把任务记忆落到文件里。

## 1. 前提

另一台机器需要：

- 安装 Git。
- 能通过 SSH 访问 `node-120-ts:/srv/git/smart-center.git`。
- 推荐使用 Git Bash、PowerShell 或 VS Code 终端执行命令。
- 不要直接在生产目录里改代码。

如果是 Windows，推荐目录：

```text
D:\SmartCenter\
  smart-center-git\
  smart-center-worktrees\
```

如果是 macOS 或 Linux，推荐目录：

```text
~/SmartCenter/
  smart-center-git/
  smart-center-worktrees/
```

## 2. 克隆代码

Windows Git Bash 示例：

```bash
mkdir -p /d/SmartCenter
cd /d/SmartCenter
git clone node-120-ts:/srv/git/smart-center.git smart-center-git
cd smart-center-git
```

Windows PowerShell 示例：

```powershell
New-Item -ItemType Directory -Force D:\SmartCenter
Set-Location D:\SmartCenter
git clone node-120-ts:/srv/git/smart-center.git smart-center-git
Set-Location D:\SmartCenter\smart-center-git
```

macOS/Linux 示例：

```bash
mkdir -p ~/SmartCenter
cd ~/SmartCenter
git clone node-120-ts:/srv/git/smart-center.git smart-center-git
cd smart-center-git
```

如果另一台机器已经有代码，不要直接覆盖，先检查：

```bash
cd /path/to/smart-center-git
git status -sb
git remote -v
```

## 3. 配置 Git 身份

把机器名写清楚，方便看提交来源。

12700K 示例：

```bash
git config user.name "codex-12700k"
git config user.email "codex-12700k@smart-center.local"
```

笔记本示例：

```bash
git config user.name "codex-laptop"
git config user.email "codex-laptop@smart-center.local"
```

## 4. 一键初始化协作目录

在 `smart-center-git` 里执行：

```bash
bash scripts/collab/bootstrap-other-machine.sh --machine 12700k
```

如果当前机器没有 Git Bash，使用 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/bootstrap-other-machine.ps1 -Machine 12700k
```

如果想指定 worktree 目录：

```bash
bash scripts/collab/bootstrap-other-machine.sh \
  --machine 12700k \
  --worktree-base /d/SmartCenter/smart-center-worktrees
```

PowerShell 指定 worktree 目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/bootstrap-other-machine.ps1 `
  -Machine 12700k `
  -WorktreeBase D:\SmartCenter\smart-center-worktrees
```

这个脚本会做：

- 配置 Git 协作参数。
- 创建 worktree 基地目录。
- 确认远端工作锁分支 `coordination/worklocks`。
- 检查同步状态。
- 打印 5 个推荐任务启动命令。

## 5. 开始任务

示例：启动服务器监控拆分任务：

```bash
bash scripts/collab/start-work.sh \
  --task server-monitor-refactor \
  --module server_monitor \
  --machine 12700k \
  --kind heavy
```

PowerShell 示例：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 `
  -Task server-monitor-refactor `
  -Module server_monitor `
  -Machine 12700k `
  -Kind heavy
```

启动后会生成：

```text
../smart-center-worktrees/server-monitor-refactor/
  .worktasks/server-monitor-refactor/TASK.md
  .worktasks/server-monitor-refactor/STATUS.json
```

同时会在远端 `coordination/worklocks` 分支创建：

```text
locks/server_monitor.json
```

其他机器就能看到这个模块正在被占用。

## 6. 查看当前状态

```bash
bash scripts/collab/check-sync.sh
bash scripts/collab/status-worktasks.sh
```

PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/check-sync.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/status-worktasks.ps1
```

## 7. 结束任务

进入任务 worktree，例如：

```bash
cd ../smart-center-worktrees/server-monitor-refactor
```

结束并释放锁：

```bash
bash scripts/collab/finish-work.sh \
  --message "refactor: split server monitor module" \
  --release-lock server_monitor
```

PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/finish-work.ps1 `
  -Message "refactor: split server monitor module" `
  -ReleaseLock server_monitor
```

## 8. 重要提醒

- 一台机器最多 5 个并行 worktree。
- 同时最多 2 个重任务。
- `templates/index.html` 同一时间只能一个任务改。
- `api/server.py` 同一时间只能一个任务改。
- `snmp_core.py` 同一时间只能一个任务改。
- `config.py`、`app.py`、`background.py` 同一时间只能一个任务改。
- 不要使用 `git reset --hard`、`git checkout -- <file>`、`git clean -fd`。

