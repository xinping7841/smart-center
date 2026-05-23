# Smart Center Query Knowledge Base

Last updated: 2026-05-24

This document is the single reference for Feishu natural-language replies and future local-model tool routing. The current policy is query-only: status, history, logs, statistics, diagnostics, and inventory are allowed; physical control actions are not allowed.

## Safety Policy

Allowed:

- Read current device status, online/offline state, health, diagnostics, and configuration inventory.
- Read historical data such as energy trends, meter statistics, state changes, events, and operation logs.
- Summarize and compare existing data, for example "昨天用了多少电" or "最近自动化失败记录".
- Explain risk and suggest manual next steps without executing an action.

Forbidden until explicitly enabled by a later design:

- Device control: open, close, switch, start, stop, reboot, shutdown, wake, set mode, set temperature, scene execution, command execution, one-key start/stop, calibration, model rebuild, recording start/stop.
- Any POST/PUT/DELETE route that changes real equipment, config, runtime state, training data, or credentials.
- Any indirect control through "debug", "test", "execute", "control", "save", "update", "toggle", "wake", "command", "onekey", "rebuild", "recording", or "calibrate" routes.

Natural-language assistants must answer forbidden requests with a refusal such as:

```text
当前只支持查询状态、历史数据和日志，不执行开关、重启、下发控制、配置修改等操作。
```

## Query Routing Rules

Use deterministic routing first. A local model may classify intent, but the actual tool call should still be selected from this allowlist.

| Intent | Keywords | Primary read API | Notes |
| --- | --- | --- | --- |
| Overview | 状态, 概览, 在线, 现在, 情况 | `GET /api/dashboard/summary` | Fastest whole-system summary. |
| Offline or abnormal devices | 离线, 不在线, 异常, 掉线, 故障 | `GET /api/dashboard/summary` | Parse `counts` and `modules.*.devices` or `modules.server.machines`. |
| Energy now/today/yesterday/month | 电量, 用电, 耗电, 能耗, 功率, 电表, kWh, 度电 | `GET /api/meters?target=total&period=day&days=7` | Use `summary`, `dashboard_summary`, `trend`, `trend_breakdown`. |
| Energy history | 近7天, 近30天, 历史电量, 趋势 | `GET /api/7days_energy`, `GET /api/30days_energy`, `GET /api/meters?...` | Prefer `/api/meters` when total/reference comparison is needed. |
| Current collector | 电流, 采集器, 回路, 通道 | `GET /api/current-collector/status` | Return group totals first, then visible channels if needed. |
| Server and machine health | 服务器, 主机, 机器, 节点, 电脑, CPU, GPU, 磁盘 | `GET /api/dashboard/summary`, `GET /api/machines` | `/api/dashboard/summary` has a compact server module; `/api/machines` has richer detail. |
| Environment | 温度, 湿度, 光照, 门磁, 环境, 传感器 | `GET /api/env/status`, `GET /api/dashboard/summary` | Use sensor names from config/dashboard. |
| HVAC status | 空调, 制冷, 制热, 模式, 设定温度 | `GET /api/hvac/status`, `GET /api/hvac/devices` | Query-only; do not call `/api/hvac/control`. |
| Lighting status | 灯光状态, 继电器状态, 哪些灯亮着 | `GET /api/light/status` | Query-only; do not call `/api/light/control`. |
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
- "哪个电表今天耗电最多"
- "当前总功率"

Suggested reply:

```text
昨日电量：326.48 kWh。
今日当前累计：27.49 kWh；本月累计：7580.0 kWh。
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
- Machine fields may include `custom_name`, `hostname`, `ip`, `is_online`, `last_online`, `status.cpu_percent`, `status.disk_percent`, `status.gpu_list`.

Natural-language examples:

- "服务器状态"
- "node-120 状态"
- "哪些服务器离线"
- "GPU 温度"
- "CPU 占用最高的是谁"

Forbidden related actions:

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

Forbidden related action:

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

Forbidden related action:

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

Forbidden related actions:

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
- Forbidden: `POST /api/ups/control`.

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
- Optional Ollama intent parser for Feishu: `POST <FEISHU_NL_MODEL_URL>/api/generate`.

Current defaults:

- OpenAI-compatible proxy: `http://192.168.50.122:8001/v1`
- vLLM upstream: `http://192.168.50.122:8000/v1`
- Model: `gemma-4-e4b-awq-int4`
- Ollama on node-120: `qwen3:14b` when `FEISHU_NL_MODEL_ENABLED=true`.

Natural-language examples:

- "本地模型配置"
- "模型服务在线吗"
- "知识库文档数量"

Notes:

- Health checks can be slow. Use short timeouts in Feishu replies and report timeout clearly.
- Config responses redact API keys.
- Training export redacts sensitive fields, but it is still an admin action.
- Qwen3 Ollama requests must include `think: false`; otherwise Feishu may receive thinking text instead of the final JSON/result.
- The Ollama model is an intent classifier only. It must not directly call Smart Center APIs.
- If Ollama only listens on `127.0.0.1` of node-120, run the Feishu bot on node-120 or expose a protected proxy URL.

Suggested Ollama classification request:

```json
{
  "model": "qwen3:14b",
  "prompt": "只输出 JSON。将用户问题分类为只读查询 intent；控制动作返回 forbidden_control。",
  "stream": false,
  "format": "json",
  "think": false,
  "options": {"temperature": 0}
}
```

Suggested deployment path:

```text
Feishu message
-> Feishu bot / Smart Center service
-> Ollama qwen3:14b intent classification with think:false
-> Smart Center read-only allowlist API
-> deterministic formatter
-> Feishu reply
```

## Tool Call Allowlist For Feishu And Local Model

The first production natural-language integration should only call these GET routes:

```text
/api/dashboard/summary
/api/current-collector/status
/api/meters?target=total&period=day&days=7
/api/7days_energy
/api/30days_energy
/api/env/status
/api/hvac/status
/api/hvac/devices
/api/light/status
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
/api/local-model/config
/api/local-model/health
```

Do not call these from chat automation until a separate approval workflow exists:

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

Forbidden action example:

```json
{
  "intent": "device_control",
  "allowed": false,
  "read_only": false,
  "reason": "control_actions_are_disabled_in_chat"
}
```

## Initial Feishu Coverage

Implemented in `services/feishu_bot.py`:

- Overview: "状态", "现在情况".
- Offline devices: "哪些设备离线", "异常设备".
- Energy: "昨日电量", "昨天用了多少电", "今日用电", "本月用电", "本月用电排行".
- Current collector: "当前电流", "采集器".
- Servers: "服务器状态", "哪些服务器离线".
- Logs: "最近日志", "最近自动化日志", "最近灯光日志".
- Environment/HVAC/UPS/SNMP/NVR/proxy/local-model read-only status.
- Optional Ollama intent classifier via `FEISHU_NL_MODEL_ENABLED=true`.
- Control refusal: "开灯", "关灯", "控制", "重启", "关机", "执行", "下发".

Next useful expansion:

- Add richer formatting for per-device history and filtered log summaries.
- Add a small in-service tool dispatcher endpoint that enforces the allowlist above before any local-model response can trigger an API call.
- Add protected network access to node-120 Ollama if the bot is not running on node-120.
