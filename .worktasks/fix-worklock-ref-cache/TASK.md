# 任务记忆

## 基本信息

- 任务名：fix-worklock-ref-cache
- 模块锁：collab
- 分支：codex/mac-fix-worklock-ref-cache-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/fix-worklock-ref-cache
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-24 01:54:26
- 预计结束：

## 目标

```text
修复 Windows 仓库中 origin/coordination/worklocks 远端跟踪引用不存在时，协作脚本读取工作锁失败的问题。
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
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 改为把远端工作锁分支显式同步到本地 coordination/worklocks 缓存分支
- 读取锁、创建临时 worktree 均使用本地稳定锁引用

## 已验证

- git diff --check

## 未验证

- 12700K Windows PowerShell 实机执行 check-sync/start-work/finish-work

## 风险点

- 锁分支同步使用强制 refspec，仅针对 coordination/worklocks 本地缓存分支，不影响 main 或任务分支

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交合并后让 12700K 拉取并执行完整烟测
