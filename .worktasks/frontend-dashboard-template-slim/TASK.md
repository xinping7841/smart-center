# 任务记忆

## 基本信息

- 任务名：frontend-dashboard-template-slim
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-dashboard-template-slim-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-dashboard-template-slim
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 00:24:12
- 预计结束：

## 目标

```text
将首页 dashboard 静态骨架从 templates/index.html 拆到 static/js/views/dashboard-shell.js，
继续保留所有旧 DOM id、data-section-id、轮询和控制入口，降低首页模板体积。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
templates/index.html
static/js/app-runtime.js
static/js/views/dashboard-shell.js
static/js/views/README.md
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 templates_index_html 伴随锁
- 新增 dashboard-shell.js，用 configData 在运行时生成首页骨架
- templates/index.html 的 dashboard 块缩减为运行时根节点
- app-runtime 加入 dashboard shell 注册、启动前渲染兜底和版本号更新
- README 补充 dashboard-shell 模块说明

## 已验证

- node --check static/js/views/dashboard-shell.js
- node --check static/js/app-runtime.js
- git diff --check
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 本地 http://127.0.0.1:6911/?view=dashboard&probe=dashboard_shell_local_recheck 验证首页 runtime shell 渲染成功，15 个 section、11 个统计卡存在，当前 URL 无 console error

## 未验证

- 生产部署后浏览器验证待执行

## 风险点

- dashboard 是默认首页，若 dashboard-shell.js 加载失败会造成首页空壳；已在模板直接加载脚本并在 app-runtime 增加 ensureDashboardShellRendered 兜底。
- 户外灯自动化卡片由 screen-runtime.js 动态注入，本任务未改变该逻辑。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 合并 main、部署生产、使用 zhankongceshi.iepose.cn 验证首页无空白和无新增前端错误。
