# 任务记忆

## 基本信息

- 任务名：fix-ps-collab-native-stderr
- 模块锁：collab
- 分支：codex/mac-fix-ps-collab-native-stderr-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/fix-ps-collab-native-stderr
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-24 01:47:15
- 预计结束：

## 目标

```text
修复 Windows PowerShell 协作脚本把 git fetch 进度输出误判为 NativeCommandError 的问题，保证 12700K/LK402 能稳定执行 check-sync/start-work/finish-work。
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
- 为 Windows 协作脚本增加 Invoke-Git 包装，按 Git 退出码判断失败
- 关闭 PSNativeCommandUseErrorActionPreference 对 Git 进度输出的误报影响

## 已验证

- git diff --check

## 未验证

- 12700K PowerShell 实机执行 check-sync/start-work/finish-work

## 风险点

- 本机 macOS 没有 pwsh，需要推送后在 12700K 上完成 PowerShell 实测

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交并推送脚本修复，12700K 拉取后执行协作流程烟测
