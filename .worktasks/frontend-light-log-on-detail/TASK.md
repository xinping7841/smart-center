# 任务记忆

## 基本信息

- 任务名：frontend-light-log-on-detail
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-light-log-on-detail-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-light-log-on-detail
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 20:07:22
- 预计结束：

## 目标

```text
首页灯光摘要只读取 /api/light/status，不再随首页轮询反复请求 /api/light/logs；
灯光日志只在进入灯光详情页 view=light 时读取，减少首页后台轮询压力。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/light-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 补充获取 templates_index_html 高风险锁，用于更新 app-runtime 缓存版本号
- 灯光运行时上下文增加 getActiveViewId
- updateLightData 改为仅 light 详情页请求 /api/light/logs
- 更新 app-runtime 与模板 cache bust 版本

## 已验证

- node --check static/js/app-runtime.js
- node --check static/js/views/light-runtime.js
- git diff --check

## 未验证

- 生产浏览器确认 dashboard 灯光摘要不再请求 /api/light/logs，light 详情页仍请求日志

## 风险点

- 

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 本地校验、提交、合并 main、部署生产并观测。
