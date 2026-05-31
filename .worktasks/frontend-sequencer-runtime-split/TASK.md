# 任务记忆

## 基本信息

- 任务名：frontend-sequencer-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-sequencer-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-sequencer-runtime-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 15:04:44
- 预计结束：

## 目标

```text
把时序电源首页摘要、详情页卡片、筛选和控制逻辑从 app-runtime.js 拆到 static/js/views/sequencer-runtime.js，并在 dashboard 中改为靠近视口才加载。
```

## 当前阶段

```text
本地校验完成，准备浏览器验证和提交
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/sequencer-runtime.js
static/js/views/README.md
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 手动登记 templates_index_html 第二把锁
- 新增 sequencer-runtime 懒加载模块
- 将时序电源渲染、筛选、状态缓存和控制下发迁出 app-runtime.js
- 将 dashboard 时序电源轮询改为靠近视口才加载
- 更新 app-runtime 缓存版本号

## 已验证

- `node --check static/js/app-runtime.js`
- `node --check static/js/views/sequencer-runtime.js`
- `for f in static/js/app-runtime.js static/js/views/*.js static/js/core/*.js; do node --check "$f"; done`
- `python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py` 通过；仅保留既有 api/server.py Windows 路径转义 SyntaxWarning

## 未验证

- 本地浏览器验证 dashboard 时序电源区和 sequencer 页面
- 生产部署后的公网验证

## 风险点

- 时序电源属于真实设备控制链路，本任务不点击任何控制按钮，只验证渲染、筛选和静态资源加载。
- 必须保留原 `/api/sequencer/control` payload、权限校验和 350/900/1800/3500ms 状态回读节奏。

## 依赖和冲突

```text
已额外登记 templates_index_html 锁；未修改后端 Python 业务逻辑。
```

## 下一步

- 本地浏览器验证
- 提交并 push 任务分支
- 合并 main 并部署生产
- 生产浏览器验证后释放 frontend_assets 和 templates_index_html 锁
