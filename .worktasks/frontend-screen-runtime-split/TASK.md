# 任务记忆

## 基本信息

- 任务名：frontend-screen-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-screen-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-screen-runtime-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 14:40:30
- 预计结束：

## 目标

```text
把首页幕布/屏幕状态和控制逻辑从 app-runtime.js 拆到 static/js/views/screen-runtime.js，并保持 dashboard 接近视口才加载，继续降低首屏基础包体积。
```

## 当前阶段

```text
本地校验完成，准备提交/合并/生产验证
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/screen-runtime.js
static/js/views/README.md
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 手动登记 templates_index_html 第二把锁
- 新增 screen-runtime 懒加载模块
- 将幕布状态卡片、环境/UPS/自动化伴随卡片、幕布控制下发迁出 app-runtime.js
- 将 dashboard 幕布区纳入接近视口延迟加载
- 更新 app-runtime 缓存版本号

## 已验证

- `git diff --check`
- `node --check static/js/app-runtime.js`
- `node --check static/js/views/screen-runtime.js`
- `for f in static/js/app-runtime.js static/js/views/*.js static/js/core/*.js; do node --check "$f"; done`
- `python3 -m compileall app.py api services runtime modules core config.py background.py power.py snmp_core.py` 通过；仅保留既有 api/server.py Windows 路径转义 SyntaxWarning

## 未验证

- 本地浏览器和生产浏览器的 dashboard 幕布区 lazy-load 行为
- 生产部署后的静态资源 200 和页面控制入口

## 风险点

- 幕布属于真实设备控制链路，必须保留 screen.control 权限校验和原 `/api/screen/control` payload。
- env.js / ups.js 会在 screen-runtime 加载前尝试刷新伴随卡片；screen-runtime 加载后会主动补渲染，避免长期停留在加载中。

## 依赖和冲突

```text
已额外登记 templates_index_html 锁；未修改后端 Python 业务逻辑。
```

## 下一步

- 本地浏览器验证
- 提交并 push 任务分支
- 合并 main 并部署生产
- 生产浏览器验证后释放 frontend_assets 和 templates_index_html 锁
