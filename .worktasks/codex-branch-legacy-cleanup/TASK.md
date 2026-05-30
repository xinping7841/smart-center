# 任务记忆

## 基本信息

- 任务名：codex-branch-legacy-cleanup
- 模块锁：collab_tools
- 分支：codex/mac-codex-branch-legacy-cleanup-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/codex-branch-legacy-cleanup
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-30 21:46:03
- 预计结束：

## 目标

```text
彻底清理 120 裸仓库历史 codex/* 活跃分支：先审计、备份，再把安全分支和需复核分支归档到 refs/archive，确保 refs/heads/codex/* 清零且可恢复。
```

## 当前阶段

```text
已完成，待提交释放锁
```

## 修改范围

```text
.worktasks/codex-branch-legacy-cleanup/TASK.md
120 裸仓库 refs/heads/codex/*
120 裸仓库 refs/archive/codex-final-safe-20260530_215022/*
120 裸仓库 refs/archive/codex-review-20260530_215022/*
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 使用远程脚本 runner 在 120 裸仓库完成剩余 31 个 codex/* 分支二级审计。
- 将 22 个安全分支归档到 `refs/archive/codex-final-safe-20260530_215022/*`。
- 将 9 个仍有代码/配置差异、需要历史保留复核的分支归档到 `refs/archive/codex-review-20260530_215022/*`。
- 删除活跃 `refs/heads/codex/*` 分支，保留 archive refs 和 bundle 可恢复。
- 生成最终报告：`/srv/smart-center/backups/branch-final-archive-20260530_215022/FINAL_CODEX_BRANCH_ARCHIVE.md`。
- 生成最终 CSV：`/srv/smart-center/backups/branch-final-archive-20260530_215022/final-codex-branch-archive.csv`。
- 生成完整 refs bundle：`/srv/smart-center/backups/branch-final-archive-20260530_215022/pre-final-archive-all-refs.bundle`。

## 已验证

- 120 裸仓库 `refs/heads/codex/*` 数量为 0。
- 120 裸仓库 `refs/archive/codex-final-safe-20260530_215022/*` 数量为 22。
- 120 裸仓库 `refs/archive/codex-review-20260530_215022/*` 数量为 9。
- bundle、最终报告、最终 CSV 均存在且非空。
- 本机 `git fetch --all --prune` 后 `origin/codex/*` 数量为 0。

## 未验证

- 未逐个恢复 archive refs；已通过 `git update-ref` 后 SHA 校验确认每个 archive ref 写入成功。

## 风险点

- 活跃历史分支已从 `refs/heads/codex/*` 移除，但未丢失：可从 archive refs 或 bundle 恢复。
- 9 个 review archive 分支存在旧代码/配置差异，后续如需追溯应从 `refs/archive/codex-review-20260530_215022/*` 查看，不再从活跃分支列表查看。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交任务记录并释放 `collab_tools` 锁。
