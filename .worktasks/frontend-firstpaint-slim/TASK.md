# 任务记忆

## 基本信息

- 任务名：frontend-firstpaint-slim
- 模块锁：frontend-performance
- 分支：codex/mac-frontend-firstpaint-slim-20260530
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-firstpaint-slim
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-30 23:30:29
- 预计结束：

## 目标

```text
在不改变控制接口和业务行为的前提下，降低首页首屏同步脚本体积；
将服务器监控、HVAC、投影机详情模块从同步链路改为按需加载/空闲预热。
```

## 当前阶段

```text
本地验证完成，待提交、合并、生产发布和生产复测。
```

## 修改范围

```text
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 备份 120 生产代码到 /srv/smart-center/backups/pre-firstpaint-slim-20260530_233102
- 将 server-monitor.js、hvac-view.js、projector.js 从首屏同步脚本链路移入 lazy module
- 增加首页空闲预热 preloadDashboardSupportModules
- 服务器首页摘要改为模块就绪后渲染，避免懒加载窗口期报错

## 已验证

- python3 -m compileall app.py api services runtime config.py background.py power.py snmp_core.py
- 本地 6909 验证 /、dashboard、server、snmp、auto、hvac、projector 均 HTTP 200
- 浏览器验证 dashboard/server/snmp/auto/hvac/projector 均能激活对应 view

## 未验证

- 本轮尚未拆分 707KB 的 smart-center-time-ntp.css，CSS 需下一阶段按视图拆分。

## 风险点

- templates/index.html 仍是高风险文件；本轮只调整加载链路，不改设备控制 payload。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支，合并 main，发布生产，跑生产性能对比。
