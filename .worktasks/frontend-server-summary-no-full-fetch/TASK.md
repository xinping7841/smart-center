# 任务记忆

## 基本信息

- 任务名：frontend-server-summary-no-full-fetch
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-server-summary-no-full-fetch-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-server-summary-no-full-fetch
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 19:52:08
- 预计结束：

## 目标

```text
首页机器状态摘要不再为了渲染 compact 卡片而加载 server-runtime 或触发 /api/machines；
只消费 /api/dashboard/summary.modules.server.machines，进入服务器详情页时再加载完整服务器模块。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/server-summary.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 补充获取 templates_index_html 高风险锁，用于更新 app-runtime 缓存版本号
- 首页 server_compact 延迟模块改为只加载 server-summary-view
- 首页服务器摘要渲染兜底改为直接调用 server-summary-view，不再 withServerRuntime
- 更新 app-runtime 与模板 cache bust 版本

## 已验证

- node --check static/js/app-runtime.js static/js/views/server-summary.js static/js/views/server-runtime.js
- git diff --check

## 未验证

- 浏览器首页网络观测确认 dashboard 初始加载不请求 /api/machines

## 风险点

- 

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支，合并 main，部署生产后做浏览器和性能观测。
