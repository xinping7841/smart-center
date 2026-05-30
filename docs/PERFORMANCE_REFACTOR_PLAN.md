# 性能与结构优化计划

Last updated: 2026-05-30

## 当前边界

这轮先做低风险首屏优化，不改变控制接口、不改变配置结构、不改变物理设备执行逻辑。

- 首页只保留总览直接依赖的前端模块。
- 完整 SNMP 详情、协议控制、音乐播放器、本地模型控制台改为进入对应页面后按需加载。
- ECharts 不再首屏同步加载，强电和电表图表第一次渲染时再加载。
- 已移除首页对不存在的 `static/js/views/nvr-view.js` 引用，NVR 预览仍由 `templates/index.html` 内联逻辑负责。

## 首屏加载策略

保留同步加载：

- `static/js/core/bootstrap.js`
- `static/js/core/utils.js`
- `static/js/views/logs.js`
- `static/js/views/ups.js`
- `static/js/views/hy-edge.js`
- `static/js/views/env.js`
- `static/js/views/snmp-summary.js`
- `static/js/views/server-monitor.js`
- `static/js/views/power-meter.js`
- `static/js/views/automation-view.js`
- `static/js/views/dashboard-summary.js`
- `static/js/views/hvac-view.js`

按需加载：

- `static/vendor/echarts.min.js`
- `static/js/views/snmp.js`
- `static/js/views/proxy.js`
- `static/js/views/universal.js`
- `static/js/views/apple-audio.js`
- `static/js/views/local-model.js`
- `static/css/views/local-model.css`

## 模块加载入口

`static/js/core/bootstrap.js` 现在提供这些前端基础能力：

- `SmartCenter.registerLazyModule(name, definition)`：登记一个可按需加载的 JS/CSS 模块。
- `SmartCenter.registerViewModules(viewId, moduleNames)`：把页面视图和模块绑定。
- `SmartCenter.ensureModules(moduleNames)`：加载一个或多个模块，内部会去重。
- `SmartCenter.ensureViewModules(viewId)`：打开页面前加载该视图所需模块。

`templates/index.html` 仍然保留旧的全局函数名作为兼容层。后续迁移内联 `onclick` 时，可以逐步删除这些兼容包装。

## 性能基线

使用：

```bash
python3 scripts/perf_baseline.py
python3 scripts/perf_baseline.py --base-url http://127.0.0.1:6899
```

输出默认写入 `.baseline_reports/perf-baseline-*.json`，该目录不进入 Git。

报告包含：

- 大文件大小、gzip 后大小、行数。
- 可选 HTTP GET 接口耗时和响应大小。
- 默认接口只读，不触发真实设备控制。

## 后续拆分顺序

1. 把 `templates/index.html` 中的 SNMP 状态轮询和详情页状态迁入 `static/js/views/snmp.js`，首页只保留 `snmp-summary.js`。
2. 把服务器监控轮询、排序、WOL/关机按钮逻辑迁入 `static/js/views/server-monitor.js`，内联只保留权限与页面壳。
3. 把强电/电表图表和轮询迁入独立 `power-meter` 前端模块，控制动作保持原有二次校验。
4. 把自动化节点画布拆成独立模块，保留规则编辑 API 不变。
5. 后端再按侧边栏模块拆 `api/server.py`、`background.py`、`config.py` 的业务逻辑，先加快照测试再迁移。

## 验证重点

- 首页打开不应同步请求完整 `echarts.min.js`、`snmp.js`、`universal.js`、`apple-audio.js`、`local-model.js`。
- 进入 SNMP 页面后，完整 `snmp.js` 应加载并显示详情。
- 进入协议控制页面后，`universal.js` 应加载，并继续注册协议状态轮询。
- 进入本地模型页面后，`local-model.css` 和 `local-model.js` 应加载，控制台按钮可用。
- 强电/电表图表仍能显示，只是图表库按需加载。
