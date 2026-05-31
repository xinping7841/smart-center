# 任务记忆

## 基本信息

- 任务名：backend-summary-cache
- 模块锁：backend_api
- 分支：codex/mac-backend-summary-cache-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/backend-summary-cache
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 19:34:54
- 预计结束：

## 目标

```text
降低首页总览和 SNMP 紧凑状态接口的重复聚合/序列化开销：为 /api/dashboard/summary 增加 2 秒短缓存，为 /api/snmp/status?compact=1 增加 3 秒短缓存。
```

## 当前阶段

```text
本地验证完成，准备提交合并生产
```

## 修改范围

```text
api/dashboard.py
api/snmp.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- /api/dashboard/summary 增加短 TTL 缓存，返回 cache_hit/cache_age_sec 方便观察。
- /api/snmp/status?compact=1 缓存 TTL 从 1 秒提高到 3 秒，full 模式仍保持 1 秒。

## 已验证

- python3 -m compileall api/dashboard.py api/snmp.py
- git diff --check
- Flask test_client 验证 /api/dashboard/summary 第二次请求 cache_hit=True 且主体字段正常。

## 未验证

- 待合并 main 后部署 node-120 生产，通过线上 perf baseline 对比 /api/dashboard/summary 与 /api/snmp/status?compact=1。

## 风险点

- 只缓存只读摘要接口，不改变设备控制和后台采集频率。
- TTL 很短，最多会让首页摘要延迟 2 秒、SNMP 紧凑摘要延迟 3 秒。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、合并、部署生产，复测性能和浏览器页面。
