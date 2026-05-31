# 任务记忆

## 基本信息

- 任务名：frontend-projector-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-projector-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-projector-runtime-split
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 12:34:08
- 预计结束：

## 目标

```text
继续前端性能拆分：把投影机状态缓存、轮询刷新、遥控器打开和真实控制指令从 app-runtime.js 拆到独立 projector-runtime.js。
```

## 当前阶段

```text
本地验证完成，准备提交合并生产验证
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/projector-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 static/js/views/projector-runtime.js，承接投影机状态缓存、状态刷新、遥控器打开、控制指令和状态回读。
- app-runtime.js 改为薄兼容入口，保留旧的 updateProjectorStatus/fireProjectorCommand/openProjectorRemote/closeProjectorRemote 名称。
- dashboard 投影摘要按需加载 projector-runtime + projector-summary；投影页面加载 projector-runtime + projector.js。
- 更新 app-runtime 缓存版本到 20260531-projector-runtime-split。

## 已验证

- git diff --check
- node --check static/js/app-runtime.js
- node --check static/js/views/projector-runtime.js
- node --check static/js/views/projector-summary.js
- node --check static/js/views/projector.js
- node --check static/js/views/*.js static/js/core/*.js
- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 本地 127.0.0.1:6922 验证：dashboard 初始不加载 projector-runtime/projector-summary/projector.js；projector 页面加载 projector-runtime/projector.js/projector.css。

## 未验证

- 本地临时数据目录没有真实投影机配置，dashboard 投影区域真实摘要渲染需要生产环境验证。
- 生产外网 dashboard/projector 浏览器资源链路待部署后复查。

## 风险点

- 投影机控制是真实设备控制链路；本次只迁移前端胶水层，保持 payload、权限校验和 /api/projector/control 不变。
- 首页投影快捷按钮仍依赖 fireProjectorCommand 和 openProjectorRemote 的全局兼容入口。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支、合并 main、部署到 120，使用 https://zhankongceshi.iepose.cn/ 复查 dashboard/projector 资源加载。
