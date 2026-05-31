# 任务记忆

## 基本信息

- 任务名：frontend-snmp-runtime-slim
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-snmp-runtime-slim-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-snmp-runtime-slim
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-31 16:21:12
- 预计结束：

## 目标

```text
将 app-runtime.js 中残留的 SNMP/NVR 状态拉取、详情页编排和监控预览逻辑拆到
static/js/views/snmp-runtime.js，主 runtime 只保留旧全局入口包装，降低首页首屏解析成本。
```

## 当前阶段

```text
本地验证完成，准备合并生产
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/snmp-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 新增 snmp-runtime 懒加载运行时模块
- app-runtime.js 保留 updateSnmpStatus/renderSnmpCards/NVR 预览旧入口并转发到新模块
- SNMP full 页面继续加载 snmp.js 详情渲染，首页/轮询可先只加载 snmp-runtime
- 更新 app-runtime/snmp-summary 缓存版本号为 20260531-snmp-runtime-slim

## 已验证

- node --check app-runtime.js/snmp-runtime.js/snmp.js/snmp-summary.js
- 全量 static/js/core 与 static/js/views 语法检查通过
- Python compileall app.py/api/services/runtime/config.py/background.py/power.py/snmp_core.py 通过
- git diff --check 通过
- 本地 6911 dashboard 页面加载通过，首页不强制加载 snmp.js
- 本地 6911 SNMP 页面加载通过，snmp-runtime.js/snmp.js/SNMP CSS 按需加载
- 本地 6911 camera_preview 页面加载通过，监控预览容器与 NVR 入口兼容

## 未验证

- 生产发布后页面验证

## 风险点

- NVR 预览此前依赖旧全局函数名，拆分后必须保持 selectNvrPreview/setNvrPreviewMode 等入口
- SNMP 首页摘要使用 snmp-summary.js，SNMP 详情页使用 snmp.js，需确认懒加载顺序无回归

## 依赖和冲突

```text
已获取 frontend_assets 锁；另已获取 templates_index_html 锁用于更新缓存版本号。
```

## 下一步

- 跑全量检查、本地页面验证，合并 main 并部署生产
