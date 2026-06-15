# Smart Center 12700K 接手文档

> 日期: 2026-06-15  
> 基准 commit: `d3315ab`  
> 由: 本机 (Mac) 整理

---

## 1. 获取代码

```bash
git clone node-120-ts:/srv/git/smart-center-clean.git
cd smart-center-clean
git log --oneline -3   # 最新: d3315ab
```

remote `origin` 指向 node-120 的 bare repo (`/srv/git/smart-center-clean.git`)，post-receive 已配自动推 GitHub (`xinping7841/smart-center`)。push origin 即可双向同步。

## 2. 项目身份

**演播中控调度引擎** — 运行在 node-120 (100.80.138.78) 上的场馆设备集中控制系统。

- **技术栈**: Python 3.12 + Flask + 原生 JS/CSS（无前端框架）
- **端口**: 6899（默认，环境变量 `SMART_POWER_HTTP_PORT`）
- **生产路径**: `/srv/smart-center/current` → systemd `smart-center.service`
- **控制对象**: 强电柜(Modbus PLC)、灯光(RF/TCP/Coxe/PoE)、空调(米家/HA)、投影机(PJLink/串口)、时序电源(DS-608)、UPS、门禁摄像头、服务器看板、环境传感器、SNMP 网络设备
- **对外接口**: 飞书机器人、本地模型 NL 控制、Agent 上报

## 3. 架构

```
浏览器 / 飞书 / Agent / 本地模型
        ↓
   app.py（Flask，6899，ThreadPoolWSGIServer）
        ↓
┌── api/（25 个蓝图）─────────────────────────┐
│ power light hvac door projector              │
│ sequencer ups server snmp screen             │
│ node_red universal env automation ...        │
└──────────────┬───────────────────────────────┘
               ↓
┌── services/（外部桥接）──────────────────────┐
│ home_assistant_bridge  miio_hvac             │
│ control_intent_router   feishu_bot           │
│ snmp_remote  meter_remote  mqtt_env          │
│ natural_language_orchestrator                │
└──────────────┬───────────────────────────────┘
               ↓
┌── *_core.py + drivers/（设备协议层）─────────┐
│ modbus hvac projector ups screen             │
│ control_center apple_audio snmp              │
│ drivers: base / rf_tcp / coxe / niren_poe    │
└──────────────┬───────────────────────────────┘
               ↓
       物理设备（PLC/串口/TCP/HA/Node-RED）
```

**NL 控制安全链**:
```
NL 输入 → control_intent_router → control_model_translator
→ natural_language_orchestrator → require_permission
→ acquire_operation_lock → api → driver → 物理设备
```

## 4. 关键文件速查

| 文件 | 行数 | 角色 |
|------|------|------|
| `app.py` | 337 | Flask 入口、gzip、线程池、CSRF 注入、蓝图注册 |
| `config.py` | 2714 | 全局 CONFIG、默认值、迁移、持久化 |
| `background.py` | 2957 | 后台轮询循环（电柜/灯光/投影/SNMP/UPS...） |
| `api/server.py` | 8007 | 服务器监控、Agent 上报（**最大单文件**）|
| `control_center_core.py` | 1345 | 通用协议控制、驱动包管理 |
| `snmp_core.py` | ~5000 | SNMP 采集核心 |
| `projector_core.py` | ~2300 | 投影机协议（PJLink/串口/多品牌） |
| `apple_audio_core.py` | ~2500 | 音乐播放器控制 |
| `templates/index.html` | ~800 | 主页面 shell，侧边栏 + Jinja2 模板 |
| `static/js/core/utils.js` | ~300 | fetchJson、toast、CSRF、去重、错误翻译 |
| `docs/QUERY_KNOWLEDGE_BASE.md` | - | NL 查询 API 白名单 + 路由规则 |
| `docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl` | - | 18 条控制意图种子数据 |
| `AGENTS.md` | - | AI Agent 第一入口，含设备协议表 + 协作规则 |

## 5. d3315ab 包含的改动（60 文件，+2873/-1811）

| 改动 | 文件 |
|------|------|
| 统一日志基础设施 | `log_config.py`（新建），`get_logger(__name__)` |
| CSRF 保护 | `security/csrf.py`（新建），Double Submit Cookie + meta 标签 |
| 包规范化 | `api/__init__.py` `services/__init__.py`（新建） |
| AI_MODULE 注释补齐 | 18 个模块加了 `# AI_MODULE:` 头 |
| 模板 CSS 提取 | 5 个 `<style>` 块 → `static/css/views/*.css` |
| 工程配置 | `pyproject.toml` `.eslintrc.json` `.pre-commit-config.yaml` |
| NL 知识库扩展 | 意图 11→18 条，`QUERY_KNOWLEDGE_BASE.md` 新增设备对照表 |
| 注释规范重写 | `docs/COMMENTING_GUIDE.md` |
| modbus 去重 | 根 `modbus_core.py` 为唯一源，deploy 副本标记过期 |
| 异常吞噬修复 | 裸 `except:` 清零，静默 `pass` 清零，加 `exc_info=True` |
| 生产验证 | 时序电源、灯光、户外灯(Node-RED) 控制测试通过 |

## 6. 当前问题清单

### 🔴 P0 — 必须修

**1. urllib → requests 迁移（13 个项目文件仍用 urllib）**

之前批量脚本只替换了 import 没替换函数调用，全部回滚。**必须逐文件手动改，禁止再用脚本。**

仍用 urllib 的文件：
```
api/node_red.py          api/door.py           api/power.py
api/hy_edge.py           api/local_model.py    power.py
background.py            services/snmp_remote.py
services/home_assistant_bridge.py               services/cabinet_gateway.py
services/meter_remote.py  apple_audio_core.py   projector_core.py
```
另 5 个脚本也需改：`scripts/door_live_monitor.py` `scripts/rebuild_door_model.py` `scripts/perf_baseline.py` `scripts/refresh_local_model_system_summary.py` `scripts/door_poll_once.py`

已正确迁移到 requests 的 5 个文件可作为参考：
```
services/control_intent_router.py
services/control_model_translator.py
services/feishu_bot.py
scripts/diagnose_door_status.py
scripts/remote/probe_ark_nlu_model_candidates_20260602.py
```

改法：
```
urllib.request.Request(url, data=body, headers=h)  →  requests.get/post(url, data=..., headers=..., timeout=...)
urllib.request.urlopen(req)                         →  requests.get/post(...)
resp.read()                                         →  resp.content / resp.json()
urllib.error.URLError / HTTPError                   →  requests.RequestException / requests.Timeout
```

**2. 巨型文件拆分（6 个，拆 import 可能引入循环引用）**

| 文件 | 行数 |
|------|------|
| `api/server.py` | 8007 |
| `background.py` | 2957 |
| `config.py` | 2714 |
| `snmp_core.py` | ~5000 |
| `projector_core.py` | ~2300 |
| `apple_audio_core.py` | ~2500 |

### 🟡 P1 — 高风险，需浏览器验证

**3. `style=` 属性 → class**
- config.html 有 440+ 处 inline style
- 改完必须在浏览器里逐页目视确认

**4. CSS `!important` 治理**
- 全站约 4007 处 `!important`
- 删错一个页面塌陷，必须逐页目视

### 🟢 P2 — 可持续

**5. 测试覆盖** — `tests/` 21 个文件但不系统，可持续补充

## 7. 踩过的坑

| 坑 | 教训 |
|----|------|
| **批量 urllib→requests** | 只替换 import 没换函数调用，9 文件回滚。**不要批量脚本**，逐文件手动改 |
| **CSRF 两次修 bug** | 第一次 cookie 不下发（`init_csrf` 没同步到 app.py），第二次首次 POST 被误拦（`not cookie_token` 太严）。最终 meta 标签优先 + cookie 兜底方案解决 |
| **浏览器缓存** | JS 文件 max-age=1年。改了 JS/CSS 必须更新 `?v=...` 版本号破缓存 |
| **夜间无人任务** | 禁止触发强电、时序电源、投影、空调、UPS、服务器关机等真实控制动作 |
| **远程执行复杂命令** | 不要往 `ssh "..."` 里塞管道/JSON/here-doc。写成脚本用 `scripts/ssh_exec.sh` 上传执行 |

## 8. 协作规则（来自 AGENTS.md）

- **高风险文件同时只能一人改**: `app.py` `config.py` `background.py` `api/server.py` `snmp_core.py` `templates/index.html`
- 修改前 `git fetch --all --prune`，检查远端
- 每个任务用独立 `git worktree` + 独立分支 + `.worktasks/<task>/TASK.md`
- 跨任务共识写入 `docs/work-session-log/shared-decisions.md`
- 不得 `git reset --hard` / `git clean -fd` / `rsync --delete` 覆盖现场
- 完整规则见 `AGENTS.md`

## 9. 设备对照（控制测试用）

| 用户叫法 | 系统 ID | 控制 API |
|---------|---------|---------|
| 庭院灯/户外灯 | `courtyard_light` | `/api/node-red/device/courtyard_light/control` |
| 一号厅前言灯 | light group 1, ch4 | `/api/light/control`, `device_id:"1"` |
| 门口LED第2路 | cabinet 门口LED, ch2 | `/api/set`, `cab:4,ch:2` |
| 中控室回路5 | cabinet 中控室, ch5 | `/api/set`, `cab:0,ch:5` |
| 机房空调 | `hvac_ha_shenlan_ac_01` | `/api/hvac/control` |
| 2厅LED时序电源 | `sequencer_1775236288646` | `/api/sequencer/control` |
| 泥人50.89 | niren PoE 192.168.50.89:44489 | 协议控制页（当前网络不通） |

## 10. 12700K 开发环境搭建

```bash
# 1. 克隆
git clone node-120-ts:/srv/git/smart-center-clean.git
cd smart-center-clean

# 2. 创建 venv
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt

# 3. pre-commit（可选）
pip install pre-commit && pre-commit install

# 4. 创建任务 worktree
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/collab/start-work.ps1 -Task urllib-migration -Module api -Machine 12700k

# 5. 改完提交
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/collab/finish-work.ps1 -Message "migrate: urllib→requests for api/*" -ReleaseLock api
```

## 11. AI Agent 阅读顺序（建议 12700K 的 AI 先读这些）

1. `AGENTS.md` — 项目全貌和安全边界
2. `docs/AI_NAVIGATION.md` — 搜索策略
3. `docs/MODULE_INDEX.yaml` — 模块归属和路由映射
4. 目标文件顶部的 `# AI_MODULE:` 注释块
5. `docs/QUERY_KNOWLEDGE_BASE.md` — NL 查询路由
6. `docs/COMMENTING_GUIDE.md` — 注释规范

## 12. 生产部署

```bash
# node-120 上进入代码目录
cd /srv/smart-center/releases

# 创建新 release
cp -r ../current smart-center-release-$(date +%Y%m%d_%H%M%S)-main-$(git rev-parse --short HEAD)

# 更新 symlink
sudo ln -sfn /srv/smart-center/releases/smart-center-release-... /srv/smart-center/current
sudo systemctl restart smart-center.service
```

## 13. 备份位置

- 修改前: `smart-center-workspace-backups/before_codex_audit_20260612_010502/`
- 修改后: `smart-center-workspace-backups/after_codex_audit_20260612_022343/`
- 服务器: `/srv/smart-center/backups/backup-before-codex-*`
