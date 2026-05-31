# 任务记忆

## 基本信息

- 任务名：frontend-js-dashboard-defer
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-js-dashboard-defer-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-js-dashboard-defer
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 10:42:51
- 预计结束：

## 目标

```text
继续首页性能优化，把 dashboard 首屏依赖的服务器、空调、投影完整详情模块拆成轻量摘要模块，减少首屏 JS 请求和执行压力。
```

## 当前阶段

```text
本地验证完成，准备提交、部署生产并释放锁。
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/server-summary.js
static/js/views/hvac-summary.js
static/js/views/projector-summary.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 server-summary.js，仅首页服务器摘要使用，不再为 dashboard 加载完整 server-monitor.js。
- 新增 hvac-summary.js，仅首页空调总览使用；空调详情页仍按需加载 hvac-view.js。
- 新增 projector-summary.js，仅首页投影总览使用；遥控器/投影详情仍按需加载 projector.js。
- app-runtime.js 切换首页辅助模块预热为轻量摘要模块，并保留详情页完整模块懒加载入口。
- 清理本地测试服务误写入 config.json / music_tag_library.json 的运行时脏改，未纳入提交。

## 已验证

- `git diff --check`
- `node --check static/js/app-runtime.js`
- `node --check static/js/views/server-summary.js`
- `node --check static/js/views/hvac-summary.js`
- `node --check static/js/views/projector-summary.js`
- `python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py`
- 本地 6921 测试服务验证 dashboard 首屏只请求 `server-summary.js` / `hvac-summary.js` / `projector-summary.js`，不再请求 `server-monitor.js` / `hvac-view.js` / `projector.js`。
- 本地真实配置验证空调/投影首页摘要可渲染；详情页访问会按需拉取完整 `hvac-view.js` / `projector.js`。

## 未验证

- 生产外网部署后资源请求清单和页面截图，待部署后验证。

## 风险点

- 首页空调/投影仍保留快捷控制按钮，摘要模块必须继续调用原全局控制函数，不能绕过权限链路。
- 本地 Mac 无法直连部分展厅设备/HA，设备接口超时属于测试环境限制，生产需用外网页面验证真实状态显示。

## 依赖和冲突

```text
已持有 frontend_assets 和 templates_index_html 锁。未修改配置中心、设备协议或真实控制 API。
```

## 下一步

- 提交分支，合并 main，备份生产并部署，验证 https://zhankongceshi.iepose.cn/ dashboard/hvac/projector。
