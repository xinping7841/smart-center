# Smart Center — AI Agent Entry Point

> 本文档是 AI Agent（Codex、本地模型、其他协作者）阅读和修改此代码库的第一入口。
> 先读本文档，再按模块索引导航到具体文件。

## 项目概述

**演播中控调度引擎** — 一套运行在 node-120 上的场馆设备集中控制系统。

- **核心功能**: 强电柜控制、灯光、空调、投影机、时序电源、UPS、门禁监控、服务器看板、环境监测
- **对外接口**: 飞书机器人、本地模型 NL 控制、Agent 上报
- **技术栈**: Python 3.12 + Flask + Jinja2 模板 + 原生 JS/CSS（无框架）
- **生产环境**: node-120 (100.80.138.78)，systemd 管理，`/srv/smart-center/current`

## AI Agent 读取顺序

1. **本文档** (AGENTS.md) — 理解全局结构和安全边界
2. **docs/AI_NAVIGATION.md** — 本地 AI 导航和搜索策略
3. **docs/MODULE_INDEX.yaml** — 模块归属、路由、前端文件映射
4. **docs/AI_CODE_MARKERS.md** — `AI_MODULE:` / `AI_PURPOSE:` 标记规范
5. **目标文件顶部** — 每个文件的 `# AI_MODULE:` 注释块
6. **docs/QUERY_KNOWLEDGE_BASE.md** — NL 查询路由和 API 白名单
7. **docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl** — NL 控制意图种子
8. **docs/COMMENTING_GUIDE.md** — 注释和文档规范

## 安全边界（AI Agent 必须在这些约束内工作）

### 绝对禁止
- **不得**在无人值守时触发真实设备控制（强电、时序电源、投影、空调、UPS、服务器关机重启、WOL）
- **不得**绕过权限检查、操作锁、审计日志
- **不得**静默覆盖用户的本地修改（git reset --hard / git clean -fd）
- **不得**删除或重命名已有 API 路由、前端全局函数、config.json 字段
- **不得**把生成的密码/密钥写入代码

### 控制链路安全
```
飞书/本地模型 NL 输入
  → control_intent_router (意图路由，拒绝歧义)
  → control_model_translator (LLM 翻译为标准化命令)
  → natural_language_orchestrator (策略检查 + 审计)
  → require_permission + acquire_operation_lock
  → api/* 端点
  → background poller / driver
  → 物理设备
```
所有控制链路必须经过：
1. 权限校验 (require_permission)
2. 操作锁 (acquire_operation_lock)
3. 审计日志 (log_audit_event)
4. 二次确认 (高风险操作)

## 项目结构速览

```
smart-center-clean/
├── app.py                    # Flask 应用入口，蓝图注册，CSRF，HTTP 服务
├── config.py                 # 全局配置归一化、迁移、持久化 (2700行)
├── background.py             # 后台设备轮询 (2900行)
├── log_config.py             # 统一日志基础设施
│
├── api/                      # Flask 蓝图路由 (24 个模块)
│   ├── power.py              # 强电控制
│   ├── door.py               # 门禁监控 (2900行)
│   ├── server.py             # 服务器看板 (7900行，最大文件)
│   ├── projector.py          # 投影机集群
│   ├── light.py              # 场馆灯光
│   ├── hvac.py               # 空调
│   ├── sequencer.py          # 时序电源
│   ├── ups.py                # UPS 监测
│   ├── screen.py             # 屏幕控制
│   ├── env.py                # 环境监测
│   ├── automation.py         # 自动化运行
│   ├── apple_audio.py        # Apple Audio 控制
│   ├── local_model.py        # 本地模型接口
│   ├── node_red.py           # Node-RED 桥接
│   ├── hy_edge.py            # 海宴边缘
│   ├── driver_hub.py         # 驱动中心
│   ├── current_collector.py  # 电流采集
│   ├── proxy.py              # 代理监控
│   ├── snmp.py               # SNMP 监测
│   ├── control_center.py     # 控制中心
│   ├── dashboard.py          # 首页总览
│   ├── logs.py               # 日志中心
│   └── auth_api.py           # 认证
│
├── services/                 # 外部服务集成
│   ├── feishu_bot.py         # 飞书机器人 (3700行)
│   ├── natural_language_orchestrator.py  # NL 编排
│   ├── control_intent_router.py          # 意图路由
│   ├── control_model_translator.py       # 指令翻译
│   ├── home_assistant_bridge.py          # HA 桥接
│   ├── mqtt_env_bridge.py               # MQTT 环境
│   ├── miio_hvac.py                      # 米家 HVAC
│   ├── meter_center.py                   # 电表中心
│   ├── meter_remote.py                   # 远程电表
│   └── snmp_agent/                       # SNMP Agent
│
├── drivers/                  # 设备驱动
│   ├── power_adapter.py      # 强电适配
│   ├── light_coxe.py         # COX 灯光
│   ├── light_niren_poe_kp.py # 日能 POE
│   └── light_rf_tcp.py       # RF TCP 灯光
│
├── runtime/                  # 运行时状态
│   ├── state.py              # 全局状态缓存
│   ├── automation.py         # 自动化引擎
│   └── bootstrap.py          # 启动引导
│
├── auth/                     # 认证授权
├── security/                 # CSRF 保护
│
├── static/
│   ├── js/core/              # 前端核心 (bootstrap, utils, viewport)
│   ├── js/views/             # 各页面视图 (39 个模块)
│   ├── css/core/             # 核心样式
│   ├── css/views/            # 视图样式
│   └── css/generated/        # 生成样式
│
├── templates/                # Jinja2 模板
├── docs/                     # 文档和知识库
├── training/                 # 本地模型训练数据
│
├── pyproject.toml            # Python 项目配置 (ruff, mypy)
├── .eslintrc.json            # JS 代码规范
├── .pre-commit-config.yaml   # Git 钩子
└── AGENTS.md                 # 本文档
```

## 设备-协议对照表

| 设备类型 | 模块 ID | 协议 | API 路由 | 控制风险 |
|---------|---------|------|----------|---------|
| 强电柜 | power | Modbus TCP/RTU | /api/status, /api/set | 🔴 高 |
| 电表 | meter | Modbus + HTTP | /api/meters | 🟡 中 |
| 时序电源 | sequencer | 串口/TCP 自定义 | /api/sequencer/* | 🔴 高 |
| UPS | ups | RS232 Q1/Q6 协议 | /api/ups/status | 🔴 高 |
| 灯光 | light | TCP/UDP/POE/RF | /api/light/* | 🟡 中 |
| 门禁 | door | RTSP + 视觉识别 | /api/door/* | 🔴 高 |
| 投影机 | projector | PJLink/TCP/UDP | /api/projector/* | 🟡 中 |
| 空调 | hvac | 米家 miio | /api/hvac/* | 🟡 中 |
| 屏幕 | screen | 串口/网络 | /api/screen/* | 🟢 低 |
| 服务器 | server | Agent HTTP 上报 | /api/server/* | 🔴 高 |
| Apple Audio | apple_audio | AppleScript 桥接 | /api/apple-audio/* | 🟢 低 |
| 环境传感器 | env | MQTT/HA/串口 | /api/env/* | 🟢 低 |
| 电流采集 | current_collector | Modbus | /api/current-collector/* | 🟡 中 |
| 协议控制 | universal | 多种协议 | /api/universal/* | 🟡 中 |
| SNMP | snmp | SNMP v2c/v3 | /api/snmp/* | 🟢 低 |

## AI_MODULE 标记快速参考

每个源文件顶部必须有 AI_MODULE 标记块：

```python
# AI_MODULE: <唯一模块名>
# AI_PURPOSE: <一句话职责>
# AI_BOUNDARY: <不该承担的职责>
# AI_DATA_FLOW: <数据来源→去向>
# AI_RUNTIME: <运行方式>
# AI_RISK: 高/中/低，<原因>
# AI_COMPAT: <不能删除的路由/字段/函数>
# AI_SEARCH_KEYWORDS: <搜索关键词>
```

详见 `docs/AI_CODE_MARKERS.md` 和 `docs/COMMENTING_GUIDE.md`。

## 协作规则摘要

详见本文档底部的完整规则。关键点：
- 每台机器 ≤5 并行任务，独立 worktree + 分支
- 修改前 fetch、检查 worklocks
- 高风险文件 (app.py, config.py, background.py, api/server.py, snmp_core.py, templates/index.html) 同时只允许一个任务修改
- 夜间无人任务禁止触发真实设备控制

---

# Codex 项目协作规则

本项目允许多台机器、多任务并行维护，但必须先保护现场。任何 Codex、本地 AI 或人工协作者在修改代码前，都要遵守本文件。

## 固定规则

- 每台机器最多同时运行 5 个并行任务。
- 每个任务必须使用独立 Git worktree 和独立分支。
- 每个任务必须有自己的 `.worktasks/<task>/TASK.md` 任务记忆。
- 跨任务共识必须写入 `docs/work-session-log/shared-decisions.md`。
- 修改前必须 `git fetch --all --prune`，检查远端更新。
- 修改前必须检查本地脏文件，不能静默覆盖。
- 修改前必须检查 `coordination/worklocks` 工作锁。
- 修改高风险模块前必须获取对应工作锁。
- 修改完成必须提交、推送、释放工作锁，并写清验证结果。

## 高风险文件

这些文件同一时间只能由一个任务修改：

```text
templates/index.html
api/server.py
snmp_core.py
config.py
background.py
app.py
```

如果任务会碰这些文件，必须同时获取对应模块锁和全局锁。

## 禁止操作

- 不得使用 `git reset --hard` 覆盖现场。
- 不得使用 `git checkout -- <file>` 回滚用户改动。
- 不得使用 `git clean -fd` 删除未知文件。
- 不得使用 `rsync --delete` 覆盖 Git 工作区。
- 夜间无人任务不得触发强电、时序电源、投影、空调、UPS、服务器关机重启、WOL 等真实控制动作。
- 不得把复杂远程逻辑直接塞进 `ssh "..."`。只允许简单单条命令；凡是包含管道、awk、JSON、here-doc、PowerShell script block、花括号、嵌套引号或多语句的远程操作，都必须先写成脚本文件，再用 `scripts/ssh_exec.sh`、`scripts/ssh_exec_windows.sh` 或对应 PowerShell runner 上传执行。

## 推荐脚本

协作脚本位于：

```text
scripts/collab/
```

常用命令：

```bash
bash scripts/collab/setup-git-collab.sh
bash scripts/collab/check-sync.sh
bash scripts/collab/start-work.sh --task server-monitor-refactor --module server_monitor --machine 12700k
bash scripts/collab/finish-work.sh --message "refactor: split server monitor module" --release-lock server_monitor
```

Windows PowerShell without Git Bash:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/setup-git-collab.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/check-sync.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task server-monitor-refactor -Module server_monitor -Machine 12700k
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/collab/finish-work.ps1 -Message "refactor: split server monitor module" -ReleaseLock server_monitor
```

远程机器执行复杂操作时使用：

```bash
bash scripts/ssh_exec.sh --host node-120-ts --script scripts/remote/check_status.sh
bash scripts/ssh_exec_windows.sh --host 12700k-ts --script scripts/remote/check_windows_smart_center.ps1
```

详细规则见 `docs/REMOTE_EXECUTION_GUIDE.md`。

## 工作方式

代码隔离依靠 Git worktree；模块占用依靠 worklock；任务记忆依靠 TASK.md；长期共识依靠 shared-decisions.md；最终可追溯依靠 Git commit。
