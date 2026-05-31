# 任务记忆

## 基本信息

- 任务名：frontend-runtime-domain-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-runtime-domain-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-runtime-domain-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 11:32:05
- 预计结束：

## 目标

```text
继续拆分首页首屏前端负载，将自动化详情脚本从全站常驻改为自动化页面按需加载，并保持内联 onclick 兼容。
```

## 当前阶段

```text
本地验证完成，准备提交和发布生产
```

## 修改范围

```text
static/js/app-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 追加 templates_index_html 工作锁
- 注册 automation-view 懒加载模块
- 从模板首屏脚本移除 static/js/views/automation-view.js
- 更新 app-runtime 缓存版本为 20260531-runtime-domain-split
- 为自动化详情调用增加按需加载和 fallback 保护

## 已验证

- git diff --check
- node --check static/js/app-runtime.js
- node --check static/js/views/*.js static/js/core/*.js
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 本地临时数据目录启动 127.0.0.1:6917，首页 HTML 不再包含 views/automation-view.js
- 本地静态资源 app-runtime.js 和 automation-view.js 均可读取并通过 node --check

## 未验证

- 生产发布后的浏览器网络请求和自动化页按需加载

## 风险点

- 自动化页的节点画布依赖懒加载，必须确认切换到 auto 页面后才加载 automation-view.js

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交推送分支，发布生产，外网验证 dashboard/auto 页面资源请求
