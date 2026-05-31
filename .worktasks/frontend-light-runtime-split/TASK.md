# 任务记忆

## 基本信息

- 任务名：frontend-light-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-light-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-light-runtime-split
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 17:40:10
- 预计结束：

## 目标

```text
将灯光/继电器运行时从 app-runtime.js 拆出为 static/js/views/light-runtime.js，保持旧 onclick 兼容并降低首页首屏 JS 解析负担。
```

## 当前阶段

```text
本地静态验证完成，准备提交合并生产。
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/light-runtime.js
templates/index.html
.worktasks/frontend-light-runtime-split/TASK.md
```

## 已完成

- 创建任务 worktree
- 获取 frontend_assets 工作锁
- 获取 templates_index_html 高风险锁
- 拆出 light-runtime.js
- app-runtime.js 保留灯光全局桥接函数
- 更新 app-runtime 缓存版本号

## 已验证

- node --check static/js/app-runtime.js static/js/views/light-runtime.js 通过
- node --check static/js/core/*.js static/js/views/*.js 通过
- git diff --check 通过
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py 通过
- scripts/perf_baseline.py 生成本地文件体积基线


## 未验证

- 生产部署后的浏览器资源加载验证待执行


## 风险点

- 灯光控制是真实设备控制链路，本次只迁移前端运行时，不改变 /api/light/control payload


## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并 main、部署 120 生产并验证 dashboard/light 页面

