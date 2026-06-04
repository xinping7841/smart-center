# 任务记忆

## 基本信息

- 任务名：ha-root-cause-check
- 模块锁：ha-hvac-freshness
- 分支：codex/mac-ha-root-cause-check-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees-active/ha-root-cause-check
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 19:50:34
- 预计结束：

## 目标

```text
仔细检查 HA 信息滞后问题，定位是中控拉取、HA 实体、还是 HA/xiaomi_home 集成自身滞后；必要时做最小修复。
```

## 当前阶段

```text
2026-06-04 复查中：node-121 已扩容内存，确认 HA/xiaomi_home 无 Session is closed 复发；正在修正中控 HVAC 更新时间语义。
```

## 修改范围

```text
本轮生产代码修改：
- services/home_assistant_bridge.py
- tests/test_home_assistant_bridge.py

历史一次性远程排查脚本：
新增一次性远程排查脚本：
- scripts/remote/check_ha_node_121_20260603.sh
- scripts/remote/check_ha_node_121_sudo_20260603.sh
- scripts/remote/restart_ha_verify_20260603.sh
- scripts/remote/verify_ha_after_restart_20260603.sh
- scripts/remote/verify_ha_stability_window_20260603.sh
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 生产 /api/hvac/status?refresh_stale=1 显示 Smart Center polled_at 为当前，说明中控每次都有拉 HA。
- 直接 HA /api/states 查询确认 climate.demry、lumi、lemesh 等实体 last_updated 确实滞后，不是前端计算错误。
- HA /api/error_log 与 121 容器日志确认 xiaomi_home 每分钟报 refresh cloud devices failed, Session is closed。
- 使用脚本上传方式在 node-121 检查 HA：Docker 容器 homeassistant，镜像 homeassistant/home-assistant:stable，版本 2026.4.3。
- 用 sudo -n docker restart homeassistant 重启 HA 容器，未调用任何设备控制服务。
- 重启后 HA 实体 last_updated/last_reported 刷新到 2026-06-03 19:54:59 左右，Smart Center 生产 API 同步显示新鲜度约 100 秒。
- 19:56 后日志窗口 Session is closed 计数为 0。
- 2026-06-04 node-121 内存扩容后确认：MemTotal 29686932 kB，Swap 0B 使用，HA 容器正常。
- 2026-06-04 复查最近 45 分钟 HA 日志：Session is closed 计数为 0，未发现 xiaomi_home/miot_client error。
- 2026-06-04 直接 HA REST 探针确认 climate 实体 last_updated/last_reported 会在状态无变化时停留在 HA 重启后的时间；这更像 HA 实体状态时间语义问题，不是中控没有轮询。
- 已将 HA HVAC 的 updated_at 改为 Smart Center 本次成功拉取时间，HA 原始实体时间保留为 last_updated/last_changed/last_reported 与 ha_last_* 字段，避免页面/飞书把“状态未变化”误读成“信息未更新”。

## 已验证

- HA /api/config：state RUNNING，version 2026.4.3。
- 生产 /api/hvac/status?refresh_stale=1：所有空调 ha_state_age_sec 从数小时/一天级降到约 100-200 秒。
- 生产 /api/env/status：原先陈旧的 HA 环境传感器恢复在线，age_sec/max_age_sec 约 100 秒。
- node-121 docker：homeassistant 容器重启后 Up。
- 2026-06-04 3 分钟窗口后生产 /api/hvac/status?refresh_stale=1 仍可成功从 HA 读取 14 台空调，但 HA 原始实体 last_updated/last_reported 超过 300 秒，说明应分离拉取时间和状态变化时间。
- 2026-06-04 xiaomi_home manifest 备份显示版本 v0.4.7；未发现需要立即升级的新版证据。

## 未验证

- 未升级 HA/xiaomi_home；当前没有 Session is closed 复发，且 xiaomi_home 已是 v0.4.7。
- 未执行真实设备控制。
- 未长时间观察 1-2 小时后 climate 实体是否因设备属性实际变化而更新。

## 风险点

- HA 使用 custom_components.xiaomi_home，日志提示自定义集成未被 HA 官方测试，且存在 invalid entity ID 警告；长期看应跟进 xiaomi_home 版本或 HA Core 升级。
- node-121 扩容后资源瓶颈已缓解；如果 Session is closed 再次出现，再优先看 xiaomi_home/HA 升级或定时健康重启策略。
- 本次重启脚本最初用未认证 /api/ 健康探测，产生一串 localhost invalid authentication warning；后续真实验证均使用 token。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 短期：发布本轮 updated_at/ha_* 字段语义修正后，验证生产 /api/hvac/status 的 updated_at 为当前拉取时间，last_updated/ha_last_updated 保留 HA 原始时间。
- 若 Session is closed 复发：优先备份 /opt/home-assistant/config，再评估 HA Core 或 xiaomi_home 升级/重启策略。
- 中控侧后续增强：可以让页面显示“HA拉取时间”和“状态未变化时间”两层信息。
