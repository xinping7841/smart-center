# 任务记忆

## 基本信息

- 任务名：frontend-4k-energy-hvac-layout
- 模块锁：frontend_assets
- 分支：codex/mac-frontend-4k-energy-hvac-layout-20260602
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/frontend-4k-energy-hvac-layout
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-02 22:39:49
- 预计结束：

## 目标

```text
围绕用户反馈，重点优化 3840x2160 监控大屏适配：
1. 首页补充电能消耗只读信息。
2. 彻底稳定 4K 页面切换时侧边栏尺寸。
3. 诊断空调页面刷新不及时是 HA 还是中控问题。
4. 优化 dashboard/power/light/meter/hvac/server/logs 等页面在 4K 下的一屏布局。
```

## 当前阶段

```text
本地验证完成，准备提交/发布
```

## 修改范围

```text
api/dashboard.py
api/hvac.py
templates/index.html
static/js/app-runtime.js
static/js/views/dashboard-shell.js
static/js/views/dashboard-summary.js
static/js/views/page-shells.js
static/js/views/power-meter-runtime.js
static/css/views/ui-wide-1080.css
static/css/views/ui-4k-final.css
static/css/generated/meter.css
static/css/generated/meter.css.gz
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 首页新增只读“电能消耗态势”，由 dashboard summary 与电表中心快照共同驱动。
- /api/dashboard/summary 增加 modules.energy。
- 空调状态刷新增加中控轮询耗时、轮询时间、刷新来源诊断字段。
- 空调前端轮询改为防重叠请求，并显示 HA 数据年龄诊断。
- 增加 inactive view 隐藏保护，避免页面切换后非活动页面撑开布局。
- 3840x2160 下新增最终 4K 样式 ui-4k-final.css，确保懒加载视图样式后仍保持最终布局。
- 电表页 4K 调整为 4 列紧凑卡片、3 行卡片列表与可见趋势图。
- 空调页 4K 最终提升到 v13，覆盖懒加载 hvac.css 的 320px 固定卡片规则，三个分区横向铺满 3840 宽屏。
- 生产真实数据有 14 台空调，v14 进一步按 12 栏重排 HVAC 分组：1/2/3 台组占 4 栏，4 台组占 8 栏并 4 列展示，减少 3840 下行尾留白。
- 修复 meter.css.gz 未同步导致浏览器拿到旧预压缩 CSS 的问题。
- 日志页、服务页、首页、电表页 4K 布局完成复扫。

## 已验证

- node --check static/js/app-runtime.js static/js/views/page-shells.js static/js/views/dashboard-shell.js static/js/views/dashboard-summary.js static/js/views/power-meter-runtime.js
- python3 -m py_compile api/dashboard.py api/hvac.py
- git diff --check
- CSS brace count: ui-wide-1080.css 767/767, ui-4k-final.css 49/49, meter.css 224/224
- /api/dashboard/summary 返回 modules.energy
- /api/hvac/status 返回 _refresh，当前中控轮询约 0.1-0.3ms
- 3840x2160 全页面扫描：dashboard/power/light/meter/sequencer/universal/snmp/hvac/apple_audio/local_model/server/logs 均 tinyCount=0、rootX=0、bodyX=0、inactiveVisible=0、finalCssV13=true
- 3840x2160 空调页：诊断条可见，HA stale 判断可见，分组最右侧 right=3783，卡片不再固定 320px。
- 3840x2160 生产 HVAC 真实数据：14 台空调、6 个分组；v14 按生产分组补齐 12 栏宽屏布局。
- 3840x2160 切页 dashboard -> power -> light -> server -> logs -> hvac -> meter -> dashboard：侧栏 286px，导航行高 58px，导航字号 18px

## 未验证

- 未点击/执行任何真实设备控制按钮。
- 尚未完成生产发布后的公网回验。

## 风险点

- static/css/generated/meter.css 存在预压缩 .gz，修改后必须同步更新 meter.css.gz，否则浏览器会拿旧样式。
- config.json、music_tag_library.json、runtime/remote_meter_payload_cache.json 是本地预览运行时写脏文件，不提交。
- 空调诊断显示中控轮询很快，但 HA/entity 数据存在陈旧，后续需要从 HA 侧继续排查实体更新时间。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 精确 stage 代码改动，排除本地运行时脏文件。
- commit/push 后合并 main，发布生产并公网回验。
- 完成后释放 frontend_assets、templates_index_html、backend_api worklocks。
