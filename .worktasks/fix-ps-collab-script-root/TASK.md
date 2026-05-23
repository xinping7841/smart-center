# 任务记忆

## 基本信息

- 任务名：fix-ps-collab-script-root
- 模块锁：collab
- 分支：codex/mac-fix-ps-collab-script-root-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/fix-ps-collab-script-root
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-24 01:51:39
- 预计结束：

## 目标

```text
让 Windows 协作脚本支持从任意当前目录用绝对路径执行，自动定位 smart-center-clean 仓库根目录，避免 12700K 远程调用时报 not a git repository。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
scripts/collab/check-sync.ps1
scripts/collab/start-work.ps1
scripts/collab/finish-work.ps1
scripts/collab/setup-git-collab.ps1
scripts/collab/bootstrap-other-machine.ps1
scripts/collab/status-worktasks.ps1
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- PowerShell 脚本改为根据 $PSCommandPath 自动计算仓库根目录

## 已验证

- git diff --check

## 未验证

- 12700K 绝对路径执行 check-sync/start-work/finish-work 实测

## 风险点

- 需要在 Windows PowerShell 5/7 环境验证 $PSCommandPath 行为

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交合并后在 12700K 拉取验证
