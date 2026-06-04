# Smart Center Query Knowledge Base

Last updated: 2026-06-04

This document is the single reference for Feishu natural-language replies and local-model tool routing. Query intents use deterministic read APIs; control intents are enabled but must enter the Smart Center safety chain: permission, audit, target matching, risk classification, and confirmation policy.

The companion seed files are `docs/LOCAL_MODEL_QUERY_INTENTS.jsonl` and `docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl`. Feed them to the local model knowledge pipeline together with this document so natural-language requests map to the right query intent or controlled-action intent before any API call.

## Safety Policy

Allowed:

- Read current device status, online/offline state, health, diagnostics, and configuration inventory.
- Read historical data such as energy trends, meter statistics, state changes, events, and operation logs.
- Summarize and compare existing data, for example "昨天用了多少电" or "最近自动化失败记录".
- Recognize and initiate controlled actions from Feishu or the Smart Center local-model page.

Control boundary:

- Query answers should use the read API allowlist below.
- Real control must go through the existing Smart Center control APIs, permission checks, audit logs, target matching, risk classification, and confirmation policy.
- Strong-current cabinets, sequencers, server shutdown/restart, batch scene actions, and unclear inferred targets must require confirmation.
- The model must not invent a direct device-control path or bypass the Smart Center safety chain.

## Query Routing Rules

Use deterministic routing first. A local model may classify query and control intent, but query tool calls should still be selected from this read allowlist; control tool calls must use the controlled-action chain.

| Intent | Keywords | Primary read API | Notes |
| --- | --- | --- | --- |
| Overview | 状态, 概览, 在线, 现在, 情况 | `GET /api/dashboard/summary` | Fastest whole-system summary. |
| Door/contact status | 大门, 门磁, 门状态, 大门开关状态 | `GET /api/env/status`, `GET /api/dashboard/summary` | Specific object intent; must be routed before generic status/control matching. |
| Offline or abnormal devices | 离线, 不在线, 异常, 掉线, 故障 | `GET /api/dashboard/summary` | Parse `counts` and `modules.*.devices` or `modules.server.machines`. |
| Energy now/today/yesterday/month | 电量, 用电, 耗电, 能耗, 功率, 电表, kWh, 度电 | `GET /api/meters?target=total&period=day&days=7` | Use `summary`, `dashboard_summary`, `trend`, `trend_breakdown`. |
| Energy history | 近7天, 近30天, 历史电量, 趋势 | `GET /api/7days_energy`, `GET /api/30days_energy`, `GET /api/meters?...` | Prefer `/api/meters` when total/reference comparison is needed. |
| Energy calculation | 本周, 最近7天合计, 平均每天, 最高, 最低, 对比, 多了多少 | `GET /api/meters?...`, `GET /api/7days_energy`, `GET /api/30days_energy` | Compute sum/avg/max/min/delta in the bot/service formatter, not in the LLM. |
| Current collector | 电流, 采集器, 回路, 通道 | `GET /api/current-collector/status` | Return group totals first, then visible channels if needed. |
| Server and machine health | 服务器, 主机, 机器, 节点, 电脑, CPU, GPU, 磁盘 | `GET /api/dashboard/summary`, `GET /api/machines` | `/api/dashboard/summary` has a compact server module; `/api/machines` has richer detail. |
| Environment | 温度, 湿度, 光照, 门磁, 环境, 传感器 | `GET /api/env/status`, `GET /api/dashboard/summary` | Use sensor names from config/dashboard. |
| HVAC status | 空调, 制冷, 制热, 模式, 设定温度 | `GET /api/hvac/status`, `GET /api/hvac/devices` | Query-only; do not call `/api/hvac/control`. |
| Lighting status | 灯光状态, 继电器状态, 哪些灯亮着 | `GET /api/light/status` | Query-only; do not call `/api/light/control`. |
| Courtyard/outdoor light status | 庭院灯状态, 户外灯状态, 室外灯现在亮吗, 院子灯开着吗 | `GET /api/node-red/device/courtyard_light/status` | Specific Node-RED device query; route before generic lighting status. Query-only; do not call `/api/node-red/device/courtyard_light/control`. |
| Lighting logs | 灯光日志, 最近开关灯, 庭院灯日志 | `GET /api/light/logs?limit=120`, `GET /api/logs/events?category=light` | Event log is richer; legacy log is useful for operation text. |
| Automation status | 自动化, 规则, 场景, 联动状态 | `GET /api/automation/status` | Query-only; do not call toggle/test/update. |
| Automation logs | 自动化日志, 场景失败, 最近触发 | `GET /api/automation/logs?limit=80`, `GET /api/logs/events?event_type=automation` | Filter by rule name when user mentions a rule. |
| Event logs | 日志, 事件, 最近发生, 失败记录, 操作记录 | `GET /api/logs/events` | Supports `category`, `event_type`, `source`, `result`, `device_id`, `q`, `hours`, `limit`, `offset`. |
| Legacy operation logs | 操作日志, 强电日志, 电柜日志 | `GET /api/logs` | Returns recent operation rows; optional `cab=<index>`. |
| SNMP and network devices | NAS, 网关, 交换机, SNMP, 存储, 端口 | `GET /api/snmp/status` | Query health, storage, interface, traffic where fields exist. |
| UPS | UPS, 电池, 旁路, 输入电压, 负载, 续航 | `GET /api/ups/status` | Query-only; do not call `/api/ups/control`. |
| NVR and cameras | 录像机, 摄像头, NVR, 通道 | `GET /api/nvr/status` | Snapshot/live APIs are read-like media endpoints but should be explicitly requested. |
| Proxy | 代理, 网络代理, ChatGPT, Google, YouTube, GitHub, 流量 | `GET /api/proxy/status` | Report target checks, clients, traffic. |
| Driver health | 驱动, 驱动中心, Node-RED, driver | `GET /api/driver_hub/snapshot`, `GET /api/driver_hub/manifest` | Useful for protocol/driver health summaries. |
| Music player status | 音乐, 播放器, 当前歌曲, 队列, 随机播放, 循环播放, 单曲循环 | `GET /api/dashboard/summary`, `GET /api/apple-audio/status` | Prefer `modules.apple_audio` in dashboard summary for compact status: playing/idle, track, playlist, queue, volume, mode, library size, scan state. Use `/api/apple-audio/status` only when full queue/library detail is needed. Changing modes or transport uses the controlled music route. |
| Local model service | 本地模型, AI, 模型健康, knowledge proxy | `GET /api/local-model/config`, `GET /api/local-model/health` | Health may be slow; config endpoint is cheap and redacts secrets. |

## Response Style

- Give the direct answer first, then key evidence.
- Include timestamps when data is stale, historic, or from logs.
- For lists, cap replies at 10 to 12 items and say how many were omitted.
- For history queries, state the time range and unit, for example `kWh`, `kW`, `A`, `%`, `ms`.
- If an API is unavailable or times out, state the failed source and suggest a manual retry.
- Never expose secrets, tokens, passwords, SNMP community strings, RTSP credentials, or raw authorization headers.

## Information Classes

### 1. System Overview

Use `GET /api/dashboard/summary`.

For "状态 / 总体情况 / 汇总中控情况", do not stop at the top card count. Build a full operational snapshot:

- Base overview from `/api/dashboard/summary`.
- Energy brief from `/api/meters?target=total&period=day&days=7`.
- Current collector from `/api/current-collector/status`.
- Proxy brief from `/api/proxy/status`.
- Automation brief from `/api/automation/status`.
- Include important object states from the dashboard modules, such as `户外大门`.
- Include top offline/abnormal devices so the user sees actionable issues immediately.

Main fields:

- `counts`: per-module `total`, `online`, `offline`, `error`, `stale`.
- `modules`: compact module payloads for `env`, `light`, `nvr`, `power`, `proxy`, `sequencer`, `server`, `snmp`, `ups`.
- `generated_at`, `elapsed_ms`, `read_only`.

Natural-language examples:

- "中控现在状态"
- "当前有多少设备在线"
- "哪些模块异常"
- "现在整体情况"

Suggested reply:

```text
中控在线。设备在线 30/58，离线 28。
服务器在线 5/30；电表在线 5/5；UPS 在线 1/1。
```

### 2. Offline And Abnormal Devices

Use `GET /api/dashboard/summary`.

Parsing:

- For normal device modules, inspect `modules.<module>.devices[]`.
- For servers, inspect `modules.server.machines[]`.
- Treat `online: false`, `is_online: false`, `status_level` in `offline/error/stale`, and important warning diagnostics as reportable.

Natural-language examples:

- "哪些设备离线"
- "帮我看下异常设备"
- "服务器哪些不在线"
- "有掉线的吗"

Suggested reply:

```text
当前离线/异常设备 28 个，设备在线 30/58：
- [环境] 二号厅门口温湿度（2026-05-19T11:47:57）
- [灯光] 泥人测试继电器
- [服务器] node-122（最后在线 ...）
... 还有 16 个未显示
```

### 3. Energy And Meter History

Primary API:

- `GET /api/meters?target=total&period=day&days=7`

Other history APIs:

- `GET /api/7days_energy`
- `GET /api/30days_energy`
- Export endpoints may be expensive and should be used only when explicitly requested and verified.

Main fields:

- `summary.total_daily_energy`, `summary.raw_total_daily_energy`.
- `summary.total_monthly_energy`, `summary.total_realtime_power`, `summary.stable_total_realtime_power`.
- `dashboard_summary.daily_energy`, `dashboard_summary.monthly_energy`, `dashboard_summary.power`.
- `trend[]`: daily `date`, `consume`, `is_today`.
- `trend_breakdown.daily/monthly/weekly`.
- `meters[]`: per-meter `display_name`, `online`, `daily_energy`, `monthly_energy`, `realtime_power`, `data_quality`.

Natural-language examples:

- "昨天用了多少电"
- "今日用电"
- "本月用电排行"
- "近 7 天电量趋势"
- "本周电能消耗"
- "最近 7 天合计用电量"
- "最近 7 天平均每天用电"
- "最近 7 天最高用电是哪天"
- "今天比昨天多用了多少电"
- "哪个电表今天耗电最多"
- "当前总功率"

Suggested reply:

```text
昨日电量：326.48 kWh。
今日当前累计：27.49 kWh；本月累计：7580.0 kWh。
```

Computed reply example:

```text
最近7天电能消耗
范围：2026-05-18 至 2026-05-24，7 天
合计：2507.14 kWh
平均：358.16 kWh/天
最高：2026-05-22 549.09 kWh
最低：2026-05-24 29.6 kWh
```

### 4. Current Collector

Use `GET /api/current-collector/status`.

Main fields:

- `online`, `enabled`, `updated_at`, `source`, `error`, `poll_failures`.
- `groups[]`: configured group totals, including `name` and `total_current`.
- `channels[]`: raw channel `channel`, `name`, `current`, `visible`.

Natural-language examples:

- "当前电流"
- "机柜供电多少 A"
- "各回路电流"
- "电流采集器在线吗"

Suggested reply:

```text
电流采集器在线，更新时间 2026-05-24T05:02:xx。
机柜供电：6.94A；1号厅空调电流：0.0A；AB厅投影：0.0A。
```

### 5. Servers And Machines

Fast source:

- `GET /api/dashboard/summary`

Detailed source:

- `GET /api/machines`

Main fields:

- Dashboard server summary: `modules.server.online`, `total`, `all_total`, `groups`, `machines[]`.
- Full machine records from `/api/machines`: `asset_group`, `custom_name`, `hostname`, `ip`, `mac`, `is_online`, `report_online`, `network_reachable`, `last_online`, `diagnostic.summary/detail/level/suggestion`, `agent_status.version/task_state`, `status.cpu_percent`, `status.mem_percent`, `status.disk_percent`, `status.gpu_list[]`, `status.os_info`, `status.storage_summary`, `status.network_adapters`.
- Current production groups are `机房`, `2号厅`, `机房-马勇`, `1号厅`, and `未分组`. Do not assume only the first group is relevant.

Routing and filtering rules:

- For `服务器状态`, `所有服务器`, `服务器分组汇总`, first read `/api/machines`, group by `asset_group`, and return every group with online/total/offline counts.
- For `机房服务器`, `1号厅服务器`, `2号厅机器`, `机房-马勇主机`, filter by `asset_group` after normalizing `一号/二号` to `1号/2号`.
- For `node-120`, hostname, IP, custom name, or MAC questions, match against `custom_name`, `hostname`, `ip`, `mac`, and `remark`.
- For `离线服务器`, filter `is_online == false`; for `机房离线服务器`, apply group filter first, then offline filter.
- For CPU/GPU/memory/disk questions, sort matching machines by `status.cpu_percent`, `status.gpu_list[].temp/util_percent`, `status.mem_percent`, or `status.disk_percent`, and return the value plus name/IP/group.
- Include `diagnostic.summary` for offline/abnormal/detail questions. Include `last_online` when a machine is offline.

Natural-language examples:

- "服务器状态"
- "所有服务器分组汇总"
- "机房服务器状态"
- "1号厅有哪些服务器"
- "2号厅离线机器"
- "机房-马勇主机列表"
- "node-120 状态"
- "node-120 CPU"
- "GPU 温度最高的是哪台"
- "哪些服务器离线"
- "CPU 占用最高的是谁"

Suggested reply:

```text
服务器：在线 6/31，离线 25，分组 5 个
分组：机房 4/13，离线 9；2号厅 1/9，离线 8；机房-马勇 0/5，离线 5；1号厅 1/3，离线 2；未分组 0/1，离线 1
各分组代表机器：
- [机房] node-120（192.168.50.120）：在线，CPU 4.7%，内存 5.9%，磁盘 19.8%，GPU RTX 3090 45°C/0%
...
```

Controlled related actions:

- `/api/wake/<mac>`
- `/api/machines/<mac>/command`
- shutdown, restart, WOL, command execution.

### 6. Environment Sensors

Use `GET /api/env/status` or the `env` module in `GET /api/dashboard/summary`.

Main fields:

- `online`, `updated_at`, `temp`, `hum`, `lux`, `noise`, `pm25`, `pm10`, `pressure`.
- HA sensors may include `battery`, `age_sec`, `*_updated_at`, `lux_trend`.

Natural-language examples:

- "机房温度"
- "户外光照多少"
- "二号厅门口温湿度在线吗"
- "哪些环境传感器离线"

Door/contact sensors are a specific subtype and should be answered by the door/contact intent first:

- "大门状态"
- "大门开关状态"
- "门磁状态"
- "户外大门开了吗"

For the current production payload, `env_xiaomi_ha_contact_01` / `户外大门` exposes `contact_text`, `opening`, `contact`, `online`, `contact_updated_at`, and `updated_at`.

### 7. HVAC Status

Use:

- `GET /api/hvac/status`
- `GET /api/hvac/devices`

Main fields:

- `name`, `online`, `power`, `mode`, `hvac_action`, `target_temp`, `temp`, `fan_speed`, `electric_power_w`, `updated_at`.

Natural-language examples:

- "空调现在开着吗"
- "咖啡厅空调状态"
- "哪些空调离线"
- "空调当前功率"

Controlled related action:

- `POST /api/hvac/control`

### 8. Lighting Status And Logs

Status API:

- `GET /api/light/status`

Log APIs:

- `GET /api/light/logs?limit=120`
- `GET /api/logs/events?category=light`

Main fields:

- Status: `online`, `channels`, `extras.<device_id>.status_level`, `last_success_at`, `last_error`.
- Logs: `time`, `operation` or event fields `message`, `action`, `result`, `source`.

Natural-language examples:

- "灯光状态"
- "二号厅哪些灯亮着"
- "最近灯光日志"
- "庭院灯最近为什么没开"

Controlled related action:

- `POST /api/light/control`

### 9. Automation And Scene Logs

Status API:

- `GET /api/automation/status`

Log APIs:

- `GET /api/automation/logs?limit=80`
- `GET /api/logs/events?event_type=automation`
- `GET /api/logs/events?q=<rule-name>`

Main fields:

- Status: `rules[]`, `enabled`, `name`, `condition`, `schedule`, `state`.
- Logs: `time`, `operation`, plus structured event fields in `/api/logs/events`.

Natural-language examples:

- "自动化状态"
- "户外灯自动化最近触发了吗"
- "最近自动化失败记录"
- "今天有哪些场景执行"

Controlled related actions:

- `POST /api/automation/toggle`
- `POST /api/automation/test`
- `POST /api/automation/update`
- Any scene execution.

### 10. Unified Event And Operation Logs

Structured event API:

- `GET /api/logs/events`

Supported query parameters:

- `category`: such as `light`, `power`, `automation`, `server`, if present in logs.
- `event_type`: such as `automation`, `state_change`.
- `source`, `result`, `device_id`.
- `q`: keyword search over message, device, action, source detail.
- `hours`: recent time window.
- `limit`: 1 to 500.
- `offset`: pagination.

Legacy operation API:

- `GET /api/logs`
- Optional `cab=<index>` for cabinet-specific logs.

Natural-language examples:

- "最近 24 小时失败日志"
- "查一下庭院灯相关日志"
- "最近谁触发了自动化"
- "强电柜最近操作记录"
- "最近 20 条事件"

Suggested routing:

- Prefer `/api/logs/events` for structured filters.
- Use `/api/automation/logs` when the user specifically asks automation logs.
- Use `/api/light/logs` when the user specifically asks lighting logs.
- Use `/api/logs` for legacy cabinet/operation wording.

### 11. SNMP, UPS, NVR, Proxy, And Driver Health

SNMP:

- `GET /api/snmp/status`
- Ask examples: "NAS 状态", "交换机状态", "网关在线吗", "存储容量".

UPS:

- `GET /api/ups/status`
- Ask examples: "UPS 状态", "电池容量", "输入电压", "续航多久", "有没有旁路/故障".
- Controlled action: `POST /api/ups/control` if later enabled through the safety chain.

NVR:

- `GET /api/nvr/status`
- Ask examples: "NVR 在线吗", "摄像头通道状态".
- Snapshot/live media endpoints may be used only for explicit read requests.

Proxy:

- `GET /api/proxy/status`
- Ask examples: "代理状态", "ChatGPT 能通吗", "代理流量", "有哪些活跃客户端".

Driver hub:

- `GET /api/driver_hub/snapshot`
- `GET /api/driver_hub/manifest`
- Ask examples: "驱动中心状态", "哪些驱动异常", "Node-RED 驱动健康".

### 12. Local Model Service

Use:

- `GET /api/local-model/config`
- `GET /api/local-model/health`
- `POST /api/local-model/export-training` only by explicit admin operation, not normal chat query.
- Optional local-model intent parser for Feishu: `POST <FEISHU_NL_MODEL_URL>/chat/completions`.

Current defaults:

- OpenAI-compatible proxy: `http://192.168.50.122:8001/v1`
- Model service check: same OpenAI-compatible proxy endpoint by default.
- Model: `gemma-4-e4b-awq-int4`
- Feishu NL model endpoint: OpenAI-compatible `/v1` service, for example `http://127.0.0.1:8001/v1` with `qwen3:14b` when `FEISHU_NL_MODEL_ENABLED=true`.

Natural-language examples:

- "本地模型配置"
- "模型服务在线吗"
- "知识库文档数量"

Notes:

- Health checks can be slow. Use short timeouts in Feishu replies and report timeout clearly.
- Config responses redact API keys.
- Training export redacts sensitive fields, but it is still an admin action.
- The local model can classify natural-language control requests and feed the Smart Center/Feishu control chain. It must not bypass API permissions, audit logs, target matching, risk classification, or confirmation policy.
- If the OpenAI-compatible model service only listens on `127.0.0.1` of node-120, run the Feishu bot on node-120 or expose a protected proxy URL.

Suggested OpenAI-compatible classification request:

```json
{
  "model": "qwen3:14b",
  "messages": [
    {"role": "system", "content": "你只输出一个 JSON 对象。"},
    {"role": "user", "content": "将用户问题分类为查询 intent 或 control_request；控制动作需要后续走中控安全链路。"}
  ],
  "stream": false,
  "temperature": 0
}
```

Suggested deployment path:

```text
Feishu message
-> Feishu bot / Smart Center service
-> OpenAI-compatible local model intent classification
-> Smart Center read-only allowlist API
-> deterministic formatter
-> Feishu reply
```

## Tool Call Allowlist For Feishu And Local Model

The first production natural-language integration should only call these GET routes:

```text
/api/dashboard/summary
/api/current-collector/status
/api/machines
/api/meters?target=total&period=day&days=7
/api/7days_energy
/api/30days_energy
/api/env/status
/api/hvac/status
/api/hvac/devices
/api/light/status
/api/node-red/device/courtyard_light/status
/api/light/logs
/api/automation/status
/api/automation/logs
/api/logs/events
/api/logs
/api/snmp/status
/api/ups/status
/api/nvr/status
/api/proxy/status
/api/driver_hub/snapshot
/api/driver_hub/manifest
/api/apple-audio/status
/api/local-model/config
/api/local-model/health
```

Control routes. Call only through the Smart Center safety chain, never directly from a model response:

```text
/api/set
/api/onekey_start
/api/onekey_stop
/api/control_center/execute
/api/universal/control
/api/light/control
/api/hvac/control
/api/sequencer/control
/api/projector/control
/api/screen/control
/api/ups/control
/api/automation/toggle
/api/automation/test
/api/automation/update
/api/apple-audio/transport
/api/wake/<mac>
/api/machines/<mac>/command
/door_control/<action>
/api/door/model_rebuild
/api/door/recording/start
/api/door/recording/stop
/api/m32r/*
/api/apple-audio/transport
/api/apple-audio/queue
/api/apple-audio/m32/prepare
```

## Suggested Intent Schema

Future local-model service can return this JSON before tool execution:

```json
{
  "intent": "energy_history",
  "allowed": true,
  "read_only": true,
  "api": "/api/meters?target=total&period=day&days=7",
  "params": {"range": "yesterday"},
  "answer_style": "short_with_evidence"
}
```

Controlled action example:

```json
{
  "intent": "control_request",
  "allowed": true,
  "read_only": false,
  "requires_confirmation": true,
  "risk": "high",
  "target": "主电柜 回路8",
  "action": "off",
  "reason": "强电柜控制必须二次确认"
}
```

## Local Model Learning Workflow

The local model should not be treated as magically self-learning from chat. Use a controlled knowledge pipeline:

1. Export current knowledge with `POST /api/local-model/export-training` or `python scripts/export_local_model_training.py`.
2. The export writes JSON/JSONL under `DATA_DIR/training/local_model`, including config devices, runtime `server_machines` from `monitor.db`, protocol files, recent logs, instructions, insights, and a `knowledge_*.json` manifest.
3. Feed those files to the local model service as a RAG/knowledge index. This is the recommended path for frequent updates because it can refresh daily or hourly without changing model weights.
4. Optional fine-tuning/LoRA should use curated instruction examples only, not raw secrets or unreviewed logs. It is slower and less suitable for rapidly changing state such as online/offline machines.
5. Query execution must still go through the deterministic read allowlist in this document. Control execution must go through the Smart Center safety chain; the model can classify intent and produce a controlled-action request, but must not directly call device APIs outside that chain.

For server knowledge specifically, every export now includes `server_machines` records with `asset_group`, names, IPs, last report time, Agent version, CPU/memory/disk/GPU summaries, and sanitized raw status. This allows the local model/RAG layer to answer all machine-room and hall-specific server questions instead of learning only the first visible group.

## Initial Feishu Coverage

Implemented in `services/feishu_bot.py`:

- Overview: "状态", "现在情况".
- Offline devices: "哪些设备离线", "异常设备".
- Energy: "昨日电量", "昨天用了多少电", "今日用电", "本月用电", "本月用电排行".
- Current collector: "当前电流", "采集器".
- Servers: "服务器状态", "所有服务器分组汇总", "机房服务器状态", "1号厅服务器", "2号厅离线机器", "node-120 CPU", "GPU温度最高".
- Logs: "最近日志", "最近自动化日志", "最近灯光日志".
- Environment/HVAC/UPS/SNMP/NVR/proxy/local-model status queries.
- Optional local-model intent classifier via `FEISHU_NL_MODEL_ENABLED=true`.
- Controlled actions: "开灯", "关灯", "控制", "重启", "关机", "执行", "下发" route into the same target matching and confirmation policy.

Next useful expansion:

- Add richer formatting for per-device history and filtered log summaries.
- Add a small in-service tool dispatcher endpoint that enforces the allowlist above before any local-model response can trigger an API call.
- Add protected network access to the node-120 local model service if the bot is not running on node-120.
