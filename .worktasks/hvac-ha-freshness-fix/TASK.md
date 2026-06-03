# 任务记忆

## 基本信息

- 任务名：hvac-ha-freshness-fix
- 模块锁：hvac
- 分支：codex/mac-hvac-ha-freshness-fix-20260603
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees-active/hvac-ha-freshness-fix
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-03 18:21:11
- 预计结束：

## 目标

```text
解决 HVAC 页面底部白色更新时间提示过大、不协调，以及 HA 信息“看起来滞后”的问题。
优先小步区分 Smart Center 拉取时间和 HA 实体状态变化时间，避免误把状态未变化显示成数据没刷新。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
api/hvac.py
services/home_assistant_bridge.py
static/js/app-runtime.js
static/js/views/hvac-view.js
static/js/views/hvac-summary.js
static/css/generated/hvac.css
static/css/generated/hvac.css.gz
templates/index.html
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 获取额外 worklock：frontend_assets、templates_index_html
- HVAC HA 状态返回新增 polled_at、last_updated、last_changed、ha_state_age_sec 等字段
- HVAC 状态 GET 增加 refresh_stale=1 可选只读 HA update_entity 刷新，单次最多 3 个陈旧实体且 5 分钟限频
- HVAC 卡片底部提示改为“HA拉取 HH:MM:SS · 状态未变化 X”，并降低字号/颜色权重
- 资源版本更新为 20260603-hvac-ha-freshness-v1

## 已验证

- python3 -m py_compile api/hvac.py services/home_assistant_bridge.py
- node --check static/js/app-runtime.js && node --check static/js/views/hvac-view.js && node --check static/js/views/hvac-summary.js
- Node 渲染函数验证：HVAC 卡片出现“HA拉取/状态未变化”，不再出现“最后更新/数据年龄”
- 后端函数模拟验证：get_hvac_status 返回 polled_at、last_updated、last_changed、ha_state_age_sec
- gzip -dc static/css/generated/hvac.css.gz 验证包含新的 #view-hvac .dashboard-mini-note 9px 弱提示样式
- 生产只读直连 HA /api/config：当前 HA 版本 2026.4.3，接口可响应
- 生产只读 HA entity/history 验证：部分 climate 实体确实长期未变化，当前问题不是 Smart Center 页面不轮询

## 未验证

- 本地完整 Flask 浏览器验证未完成：当前 worktree 无 .venv，临时 venv 启动到 app.py 时缺 cv2；未继续安装大型依赖
- 生产部署后浏览器实测待执行

## 风险点

- refresh_stale=1 会调用 HA homeassistant.update_entity，只读刷新实体，不调用空调控制服务；已加单次上限和限频
- templates/index.html 只做资源版本号 cache bust

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 运行 finish-work 验证、提交并释放 hvac/frontend_assets/templates_index_html 锁
- 如需上线，发布后用公网/局域网页面验证 HVAC 底部提示和 /api/hvac/status?refresh_stale=1 返回字段
