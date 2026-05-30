# 任务记忆

## 基本信息

- 任务名：frontend-inline-phase2
- 模块锁：template
- 分支：codex/mac-frontend-inline-phase2-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-inline-phase2
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-30 16:39:21
- 预计结束：

## 目标

```text
继续第二阶段前端结构拆分，减少 templates/index.html 内联 JS 体积，
把可独立理解的首页/投影机辅助逻辑迁移到 static/js 模块，
同时保持生产控制行为、API payload、权限校验和延迟回读逻辑不变。
```

## 当前阶段

```text
收尾验证完成，准备提交
```

## 修改范围

```text
templates/index.html
static/js/core/viewport-layout.js
static/js/views/projector.js
static/js/views/README.md
docs/FRONTEND_SPLIT_PLAN.md
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 抽离移动端/折叠屏/桌面站点自适应布局逻辑到 `static/js/core/viewport-layout.js`
- 新增 `static/js/views/projector.js`，承载投影机格式化、命令归一化、卡片渲染和遥控器面板渲染辅助
- `templates/index.html` 保留投影机状态缓存、轮询、真实控制下发和延迟回读；通过 `getProjectorViewContext()` 给模块提供运行时上下文
- 保持 `renderProjectorCards`、`renderProjectorRemote`、`getProjectorIconHtml` 等旧全局函数名兼容内联调用和其它模块调用
- `templates/index.html` 从约 7984 行降至约 7127 行

## 已验证

- `node --check static/js/core/viewport-layout.js`
- `node --check static/js/views/projector.js`
- `git diff --check`
- `python3 -m py_compile app.py`
- 本地临时 Flask 服务 `http://127.0.0.1:6909`
- 浏览器验证 `?view=projector`：投影机页面可渲染 3 张卡片
- 浏览器验证 `?view=dashboard&layout_debug=1`：首页可渲染，投影机摘要卡片延迟加载正常
- 浏览器验证 `?view=local_model`：本地模型页面可进入并触发懒加载

## 未验证

- 本机无法直连部分现场设备，电柜/电表/本地模型健康检查的 503/502 属于验证环境网络限制，不纳入本次前端拆分问题

## 风险点

- 投影机属于真实物理控制 UI，本次仅迁移渲染/格式化辅助，未改 `/api/projector/control` payload 和 `fireProjectorCommand`
- 静态资源有长缓存，生产合并后需要保留 `projector.js?v=20260530-inline-phase2` 版本戳或继续提升版本戳
- 本地验证时只打开页面和弹层，不点击开关机按钮

## 依赖和冲突

```text
已获取 template 锁。未修改 config.py、background.py、api/server.py 等其它高风险文件。
```

## 下一步

- 完成本地页面验证：dashboard、projector、local_model
- 更新拆分计划和视图模块索引
- 提交并按协作流程释放锁，确认后合并生产
