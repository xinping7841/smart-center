# 任务记忆

## 基本信息

- 任务名：node123-music-route-context
- 模块锁：local_model
- 分支：codex/mac-node123-music-route-context-20260604
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/node123-music-route-context
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-04 16:56:04
- 预计结束：

## 目标

```text
修正 123 本地模型对主界面音乐播放器状态问题的只读路由，避免误答 /api/apple-audio/library。
```

## 当前阶段

```text
已完成验证，准备提交合并发布
```

## 修改范围

```text
scripts/remote/apply_node123_device_code_context_20260603.py
scripts/remote/verify_node123_music_route_context_20260605.sh
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 发现模型会把主界面音乐状态误路由到 /api/apple-audio/library
- 在 123 知识上下文 prompt 中补充只读查询路由索引，明确音乐状态优先读取 /api/dashboard/summary.modules.apple_audio

## 已验证

- python3 -m py_compile scripts/remote/apply_node123_device_code_context_20260603.py
- git diff --check
- bash -n scripts/remote/verify_node123_music_route_context_20260605.sh
- 已在 node-120 应用新 123 知识上下文，配置备份：/srv/smart-center-data/config.json.pre-node123-device-code-context-20260605_070634
- smart-center.service active，smart-center-feishu-bot.service active
- 123 音乐路由专项探针通过：回答包含 /api/dashboard/summary 与 modules.apple_audio，不再提 /api/apple-audio/library
- 公网 /api/dashboard/summary 仍返回轻量 modules.apple_audio，has_library_payload=false

## 未验证

- 合并 main 后生产 release 元数据

## 风险点

- 只改模型知识上下文生成脚本，不改播放器 API/UI；验证不得调用播放、停止、音量、队列或真实设备控制接口。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、推送、合并 main，发布生产并释放 local_model 锁。
