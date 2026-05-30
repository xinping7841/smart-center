# 任务记忆

## 基本信息

- 任务名：remote-script-runner
- 模块锁：collab_tools
- 分支：codex/mac-remote-script-runner-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/remote-script-runner
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-30 20:38:05
- 预计结束：

## 目标

```text
彻底规避远程 SSH/PowerShell 引号问题：形成长期记忆、项目规则文档，并补齐 Linux/Windows 远端脚本上传执行入口。
```

## 当前阶段

```text
已完成，待提交释放锁
```

## 修改范围

```text
AGENTS.md
docs/REMOTE_EXECUTION_GUIDE.md
scripts/ssh_exec.sh
scripts/ssh_exec.ps1
scripts/ssh_exec_windows.sh
scripts/ssh_exec_windows.ps1
scripts/remote/quote_smoke.sh
scripts/remote/quote_smoke.py
scripts/remote/quote_smoke_windows.ps1
scripts/remote/README.md
.worktasks/remote-script-runner/TASK.md
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 写入长期记忆：复杂远程命令禁止内联 SSH，默认上传脚本再执行。
- 新增并加固 Linux/macOS 远端脚本上传执行器 `scripts/ssh_exec.sh`。
- 加固 PowerShell Linux runner `scripts/ssh_exec.ps1`。
- 加固 Windows 远端 runner `scripts/ssh_exec_windows.sh` 和 `scripts/ssh_exec_windows.ps1`。
- 新增固定引号烟测脚本 `scripts/remote/quote_smoke.sh`、`scripts/remote/quote_smoke.py`。
- 新增 Windows 固定引号烟测脚本 `scripts/remote/quote_smoke_windows.ps1`。
- 更新项目协作规则和远程执行文档。

## 已验证

- `bash -n scripts/ssh_exec.sh`
- `bash -n scripts/ssh_exec_windows.sh`
- `python3 -m py_compile scripts/remote/quote_smoke.py`
- 120 Linux 远端 Bash payload 烟测通过：中文、JSON、管道、awk、单双引号、工作目录均正常。
- 120 Linux 远端 Python payload 烟测通过：中文、JSON、单双引号、工作目录均正常。
- 12700K Windows 远端 PowerShell payload 烟测通过：中文、JSON、管道、单双引号、工作目录均正常。
- 本地长期记忆文件已写入：`/Users/wanghongyu/.codex/memories/extensions/ad_hoc/notes/20260530-remote-script-runner-no-inline-ssh.md`。

## 风险点

- 该任务只修改协作工具和文档，不触碰生产业务代码。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交并释放 `collab_tools` 锁。
- 后续分支审计和 Windows 机器检查必须优先使用这些 runner。
