# 任务记忆

## 基本信息

- 任务名：apple-audio-dashboard-auto-advance
- 模块锁：apple_audio
- 分支：codex/mac-apple-audio-dashboard-auto-advance-20260605
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/apple-audio-dashboard-auto-advance
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-05 10:40:38
- 预计结束：

## 目标

```text
修复 Apple Audio 本机播放时首页/主界面轻量状态轮询导致自然结束后不续播的问题。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
apple_audio_core.py
tests/test_apple_audio_local_player.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 定位生产现象：/api/dashboard/summary 轻量轮询在本地播放器进程正常退出后调用 _refresh_local_player_locked(auto_advance=False)，把 is_playing 标为 false，导致后续完整 snapshot 无法再触发自动续播。
- 修改 dashboard_snapshot，使其和完整 snapshot 共享本地播放器自然退出自动续播逻辑，但返回 payload 仍保持轻量。
- 增加 dashboard_snapshot_auto_advances_local_player_exit 回归测试。

## 已验证

- python3 -m unittest tests.test_apple_audio_local_player -v

## 未验证

- 待合并发布后在 node-120 生产验证：播放列表自然结束时首页轮询不再导致停播，下一首能继续从后置绿色口播放。

## 风险点

- 这是音乐播放器真实播放链路；验证时仅触发音频播放器，不涉及其它真实设备控制。
- 变更 dashboard_snapshot 的内部刷新行为，需要确认首页音乐状态仍不返回完整 library payload。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并 main、发布生产并做短周期生产验证。
