# 任务记忆

## 基本信息

- 任务名：clean-collab-entry
- 模块锁：docs
- 分支：codex/mac-clean-collab-entry-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/clean-collab-entry
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-24 01:21:34
- 预计结束：

## 目标

```text
统一干净基线 Git 入口，修复协作脚本，避免新机器继续拉旧仓库或写错任务锁。
```


## 当前阶段

```text
进行中：已修复 start-work.sh Markdown 模板转义，正在补充 clean 基线对接文档。
```


## 修改范围

```text
scripts/collab/start-work.sh
docs/multi-machine-collaboration/*
.worktasks/clean-collab-entry/*
```


## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 修复 start-work.sh 任务模板中的 Markdown 代码块转义问题
- 将协作文档中的旧仓库入口改为 smart-center-clean.git

## 已验证

- bash -n scripts/collab/start-work.sh
- git diff --check

## 未验证

- 12700K SSH 当前被连接重置，暂未能远程执行 bootstrap
- LK402 SSH 当前权限未通过，暂未能远程执行 bootstrap

## 风险点

- 不直接改生产业务代码，仅改协作入口和文档

## 依赖和冲突

```text
远端裸仓库 refs 已修复为 xinping:xinping，否则无法推送 coordination/worklocks。
```


## 下一步

- 提交并推送协作入口修复
- 用新脚本创建测试任务，验证工作锁能被远端看到
