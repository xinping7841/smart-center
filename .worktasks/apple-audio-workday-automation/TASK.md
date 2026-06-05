# 任务记忆

## 基本信息

- 任务名：apple-audio-workday-automation
- 模块锁：automation
- 分支：codex/mac-apple-audio-workday-automation-20260605
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/apple-audio-workday-automation
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-05 07:52:13
- 预计结束：

## 目标

```text
配置 Smart Center 工作日音乐自动化：09:10 自动播放，18:10 自动停止。
```

## 当前阶段

```text
本地验证完成，准备提交合并发布
```

## 修改范围

```text
runtime/automation.py
tests/test_automation_apple_audio.py
scripts/remote/configure_apple_audio_workday_automation_20260605.py
scripts/remote/verify_apple_audio_workday_automation_20260605.sh
docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl
docs/QUERY_KNOWLEDGE_BASE.md
docs/MODULE_INDEX.yaml
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 确认生产音乐输出为 node120_analog / ffmpeg_aplay / plughw:CARD=PCH,DEV=0
- 确认默认播放列表使用 folder:e38a08cca65f（器乐+轻音乐，2405 首）
- 新增 automation apple_audio 场景动作执行器
- 新增生产配置脚本：写入工作日 09:10 播放、18:10 停止的场景和规则，不立即执行
- 新增只读验证脚本，不调用播放/停止/测试执行接口
- 补充 123 本地模型控制意图和知识库说明

## 已验证

- python3 -m unittest tests.test_automation_apple_audio -v
- python3 -m py_compile runtime/automation.py scripts/remote/configure_apple_audio_workday_automation_20260605.py tests/test_automation_apple_audio.py
- bash -n scripts/remote/verify_apple_audio_workday_automation_20260605.sh
- docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl、docs/LOCAL_MODEL_QUERY_INTENTS.jsonl JSONL 解析通过
- git diff --check

## 未验证

- 远程配置应用
- 发布生产后只读验证

## 风险点

- 自动化到点会触发真实音乐输出；验证时不能调用 /api/automation/test 或即时播放/停止接口。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 本地测试、提交、合并发布、应用生产配置并重启服务、只读验证。
