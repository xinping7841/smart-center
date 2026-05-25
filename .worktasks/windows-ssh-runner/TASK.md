# 任务记忆

## 基本信息

- 任务名：windows-ssh-runner
- 模块锁：remote_tools
- 分支：codex/mac-windows-ssh-runner-20260526
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/windows-ssh-runner
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-26 03:23:46
- 预计结束：

## 目标

```text
固化 Windows SSH 远程执行方式，避免 PowerShell/SSH 内联命令引号转义反复出错。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
scripts/ssh_exec_windows.ps1
scripts/ssh_exec_windows.sh
scripts/remote/check_windows_smart_center.ps1
scripts/remote/README.md
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 增加 Windows 目标机专用脚本上传执行器
- 增加 macOS/Linux/Git Bash 调用 Windows 目标机的脚本上传执行器
- 增加 Windows Smart Center 环境检查脚本
- 更新远程执行文档，明确 Linux/Windows 分流

## 已验证

- macOS/Linux 入口已在 LK402 上完成验证：可上传、执行、输出环境和仓库状态、执行协作检查、清理远程临时目录。

## 未验证

- PowerShell 调用端入口和 12700K 尚未验证

## 风险点

- 只新增工具和文档，不影响生产运行路径。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
