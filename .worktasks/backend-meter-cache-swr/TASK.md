# 任务记忆

## 基本信息

- 任务名：backend-meter-cache-swr
- 模块锁：backend_api
- 分支：codex/mac-backend-meter-cache-swr-20260531
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/backend-meter-cache-swr
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-05-31 19:15:52
- 预计结束：

## 目标

```text
优化 /api/meters 远程电表读取链路：有本地缓存时优先秒回，远程服务慢或抖动时后台刷新，不再让主页/电表页等待 121/NAS 慢响应。
```

## 当前阶段

```text
本地验证完成，准备提交合并生产
```

## 修改范围

```text
api/power.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 将远程电表缓存改为 stale-while-revalidate：新鲜缓存直接返回，过期可用缓存立即返回并后台刷新，无缓存才阻塞读取远程服务。
- 保持 /api/meters 响应字段兼容：ok/success/summary/meters/trend/dashboard_summary/data_source/cache_hit/stale 继续保留。
- 清理本地测试产生的 config.json 和 runtime/remote_meter_payload_cache.json 副作用，未纳入提交。

## 已验证

- python3 -m compileall api/power.py services/meter_remote.py services/meter_center.py
- git diff --check
- Flask test_client 行为测试：第一次无缓存读取远程；第二次新鲜缓存不再读取远程；过期缓存秒回并后台刷新。
- 慢远程模拟测试：远程 fetch sleep 1s 时，接口 0.001s 返回缓存，并启动后台刷新。

## 未验证

- 待合并 main 后部署 node-120 生产，并通过 https://zhankongceshi.iepose.cn/api/meters 做线上对比。

## 风险点

- 只改读取性能，不改强电/电表真实控制语义。
- stale 缓存最长仍沿用原有 12 小时磁盘兜底上限。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 合并 main，部署生产，复测 /api/meters 和整体 perf baseline。
