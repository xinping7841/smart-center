# 任务记忆

## 基本信息

- 任务名：frontend-universal-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-universal-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-universal-runtime-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 17:00:42
- 预计结束：

## 目标

```text
继续前端运行时拆分：把仍留在 app-runtime.js 中的服务器监控运行层迁移到 static/js/views/server-runtime.js，降低首页和非服务器页面的 JS 解析成本，同时保持旧 onclick、服务器页、首页服务器摘要、WOL/关机/重启/刷新、排序、Agent 部署命令和 CSV 导出兼容。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/server-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 server-runtime.js 承接服务器列表轮询、控制、排序、部署命令、摘要协调和导出逻辑
- app-runtime.js 改为服务器运行时懒加载桥接，保留旧全局入口
- 更新模板静态资源版本号，确保生产缓存刷新

## 已验证

- node --check static/js/app-runtime.js
- node --check static/js/views/server-runtime.js

## 未验证

- 完整 JS 检查
- 本地浏览器 dashboard/server 页面
- 生产部署和生产浏览器验证

## 风险点

- 服务器监控包含真实设备控制链路，必须确认旧按钮入口仍按需加载 runtime 后执行
- 首页服务器摘要现在通过 runtime 缓存协调，需要验证 dashboard 首屏和滚动懒加载都正常
- Agent 版本启动探测保持轻量逻辑，避免启动时反向加载完整 server-runtime

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 跑完整静态检查、本地浏览器验证、合并部署生产、释放工作锁
