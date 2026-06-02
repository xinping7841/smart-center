# 任务记忆

## 基本信息

- 任务名：feishu-cloud-parallel-nlu
- 模块锁：backend_api
- 分支：codex/mac-feishu-cloud-parallel-nlu-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-active-worktrees/feishu-cloud-parallel-nlu
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-02 11:53:01
- 预计结束：

## 目标

```text
飞书自然语言改为云端和本地模型并行理解，当前采用云端结果；AI 模块显示两边理解、路由和执行过程；飞书控制执行开关默认开启且可手动关闭，关闭后查询不受影响。
```

## 当前阶段

```text
本地验证中
```

## 修改范围

```text
services/control_model_translator.py
services/feishu_bot.py
services/natural_language_orchestrator.py
api/local_model.py
static/js/views/local-model.js
static/css/views/local-model.css
templates/local_model.html
templates/index.html
static/js/app-runtime.js
scripts/remote/*
docs/*
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 增加云端/本地并行意图分类和控制转译
- 飞书当前采用云端理解结果，本地结果进入对比记录
- AI 模块自然语言处理记录显示模型对比
- 飞书控制执行开关默认开启，配置持久化；全局确认默认关闭

## 已验证

- python py_compile
- node --check
- git diff --check
- mock 验证 cloud_first 并行理解采用云端结果
- Feishu 控制 dry-run 未调用真实控制接口

## 未验证

- 生产部署后接口和页面缓存版本

## 风险点

- 飞书控制效率提升后，普通控制会更快进入执行链；AI 页面执行开关是手动关闭入口。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 本地页面验证，提交合并，部署生产，释放 worklock。
