# 任务记忆

## 基本信息

- 任务名：frontend-door-runtime-split
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-door-runtime-split-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-door-runtime-split
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 17:59:56
- 预计结束：

## 目标

```text
继续前端性能拆分：将门禁/大门视频、状态、框选和控制运行时从 app-runtime.js 抽到 static/js/views/door-runtime.js，保持接口和真实控制逻辑不变。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
static/js/app-runtime.js
static/js/views/door-runtime.js
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取 templates_index_html 额外锁
- 新增 door-runtime 懒加载模块
- app-runtime 保留门禁全局桥接函数，避免破坏模板 onclick

## 已验证

- 

## 未验证

- 

## 风险点

- 门禁控制是真实设备控制链路，本任务只验证页面状态和模块加载，不主动触发开门/关门。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
