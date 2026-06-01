# 任务记忆

## 基本信息

- 任务名：hvac-env-server-speed
- 模块锁：frontend_assets
- 分支：codex/mac-hvac-env-server-speed-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/hvac-env-server-speed
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 18:04:51
- 预计结束：

## 目标

```text
修复 HVAC 电源图标/按钮问题；优化环境传感器加载和刷新速度；优化服务器监控加载速度。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
api/env.py
api/server.py
services/home_assistant_bridge.py
static/js/app-runtime.js
static/js/views/env.js
static/js/views/hvac-summary.js
static/js/views/hvac-view.js
static/js/views/server-runtime.js
static/css/generated/dashboard.css(.gz)
static/css/generated/hvac.css(.gz)
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 companion locks: server_monitor、backend_api、global
- 环境状态接口默认轻量返回，按需携带 lux trend/history
- Home Assistant 状态读取增加短 TTL 缓存，减少同轮多实体串行请求
- 服务器监控前端默认请求 `/api/machines?detail=compact`，详细模式/导出按需请求 full
- HVAC 详情页使用专用 `.hvac-power-key`，首页 HVAC 摘要电源键改为绿色开/红色关
- 同步刷新 gzip CSS

## 已验证

- `python3 -m py_compile api/env.py api/server.py services/home_assistant_bridge.py` 通过；api/server.py 有旧 PowerShell 字符串 SyntaxWarning
- `node --check` 通过：env.js、server-runtime.js、hvac-view.js、hvac-summary.js、app-runtime.js
- 本机缺少 Flask 依赖，未启动本地 web 服务；待生产部署后做真实接口和页面验证

## 未验证

- 生产 `/api/env/status`、`/api/machines?detail=compact/full` 体积和耗时
- 生产 HVAC 页面按钮视觉和点击区域

## 风险点

- `/api/server.py` 是高风险文件；已补锁 server_monitor/backend_api/global
- `/api/machines` 默认保持 full 兼容旧调用，只有新前端显式请求 compact
- 未触发任何空调、服务器关机/重启/WOL 等真实控制动作

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交推送后部署生产，使用只读接口和浏览器截图验证
