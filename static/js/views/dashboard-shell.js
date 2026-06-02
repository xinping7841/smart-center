// AI_MODULE: dashboard_shell_view
// AI_PURPOSE: 生成首页监控大屏骨架，主页只做实时数据展示，不承载真实设备控制按钮。
// AI_BOUNDARY: 只生成首页容器和占位内容；不拉取接口、不执行控制、不改变任何设备状态。
// AI_DATA_FLOW: window.configData -> #view-dashboard shell -> dashboard-summary/app-runtime 填充实时数据。
// AI_RUNTIME: app-runtime 初始化首页排序/轮询前必须可用；保留关键 DOM id 供摘要渲染。
// AI_RISK: 中，首页首屏依赖这些 id；修改时必须同步检查 dashboard-summary 引用。

(function installSmartCenterDashboardShell(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function listLength(value) {
        return Array.isArray(value) ? value.length : 0;
    }

    function loadingText(text, extraStyle = '') {
        return `<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:18px;${extraStyle}">${text}</div>`;
    }

    function buildMonitorHero() {
        return `
                <section class="dashboard-monitor-hero" id="dashboard-section-hero" data-section-id="hero">
                    <div class="monitor-hero-primary">
                        <div class="monitor-kicker">SMART CENTER MONITOR</div>
                        <div class="monitor-title-row">
                            <div>
                                <div class="monitor-title">场馆监控大屏</div>
                                <div class="monitor-subtitle">设备、网络、环境、AI 自然语言、自动化与运行日志统一态势</div>
                            </div>
                            <div class="monitor-health-badge">
                                <span>综合在线率</span>
                                <strong id="dashboard-monitor-rate">--</strong>
                            </div>
                        </div>
                        <div class="monitor-hero-kpis">
                            <div class="monitor-hero-kpi">
                                <span>在线设备</span>
                                <strong id="dashboard-hero-online">--</strong>
                                <em id="dashboard-hero-online-note">等待汇总</em>
                            </div>
                            <div class="monitor-hero-kpi">
                                <span>异常总数</span>
                                <strong id="dashboard-hero-alerts">--</strong>
                                <em id="dashboard-hero-alerts-note">离线 / 异常 / 陈旧</em>
                            </div>
                            <div class="monitor-hero-kpi">
                                <span>环境温度</span>
                                <strong id="dashboard-hero-env">--</strong>
                                <em id="dashboard-hero-env-note">湿度 / 光照</em>
                            </div>
                            <div class="monitor-hero-kpi">
                                <span>更新时间</span>
                                <strong id="dashboard-hero-updated">--</strong>
                                <em id="dashboard-hero-latency">汇总接口 --</em>
                            </div>
                        </div>
                    </div>
                    <div class="monitor-hero-secondary">
                        <div class="monitor-status-grid">
                            <div class="monitor-status-tile">
                                <span>AI 策略</span>
                                <strong id="dashboard-hero-ai-policy">读取中</strong>
                                <em id="dashboard-hero-ai-note">云端/本地并行状态</em>
                            </div>
                            <div class="monitor-status-tile">
                                <span>飞书控制</span>
                                <strong id="dashboard-hero-feishu">读取中</strong>
                                <em id="dashboard-hero-feishu-note">高风险控制需确认</em>
                            </div>
                            <div class="monitor-status-tile">
                                <span>代理出口</span>
                                <strong id="dashboard-hero-proxy">--</strong>
                                <em id="dashboard-hero-proxy-note">等待代理探活</em>
                            </div>
                            <div class="monitor-status-tile">
                                <span>网络告警</span>
                                <strong id="dashboard-hero-snmp">--</strong>
                                <em id="dashboard-hero-snmp-note">严重 / 警告</em>
                            </div>
                        </div>
                        <div class="monitor-chip-strip">
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-power">强电柜 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-light">灯光 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-projector">投影 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-screen">幕布 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-hvac">空调 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-sequencer">时序 --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-ups">UPS --</div>
                            <div class="dashboard-hero-chip" id="dashboard-hero-chip-server">机器 --</div>
                        </div>
                    </div>
                </section>`;
    }

    function buildMonitorKpis(config) {
        const cabinetsTotal = listLength(config.cabinets);
        const lightTotal = listLength(config.light_devices);
        const projectorTotal = listLength(config.projectors);
        const hvacTotal = listLength(config.hvac_devices);
        const screenTotal = listLength(config.screens);
        return `
                <div class="monitor-kpi-strip" id="dashboard-section-stats" data-section-id="stats">
                    <div class="dash-stat-card"><span class="label">强电柜</span><span class="value blue"><span id="dash-power-online">0</span> / ${cabinetsTotal}</span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card"><span class="label">灯光模块</span><span class="value blue"><span id="dash-light-online">0</span> / ${lightTotal}</span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card"><span class="label">投影机</span><span class="value blue"><span id="dash-projector-online">0</span> / <span id="dash-projector-total">${projectorTotal}</span></span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card"><span class="label">幕布</span><span class="value blue"><span id="dash-screen-online">0</span> / <span id="dash-screen-total">${screenTotal}</span></span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card"><span class="label">空调</span><span class="value blue"><span id="dash-hvac-online">0</span> / ${hvacTotal}</span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card"><span class="label">时序电源</span><span class="value blue"><span id="dash-sequencer-online">0</span> / <span id="dash-sequencer-total">0</span></span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card">
                        <span class="label">SNMP 在线 / 报警</span>
                        <span class="value blue"><span id="dash-snmp-online">0</span> / <span id="dash-snmp-alert">0</span></span>
                        <div class="meta">总数 <strong id="dash-snmp-total">0</strong> · 高危 <strong id="dash-snmp-critical">0</strong> · 中危 <strong id="dash-snmp-warning">0</strong></div>
                    </div>
                    <div class="dash-stat-card"><span class="label">服务器</span><span class="value blue"><span id="dash-server-online">0</span> / <span id="dash-server-total">0</span></span><span class="meta">在线 / 总数</span></div>
                    <div class="dash-stat-card">
                        <span class="label">公司代理状态</span>
                        <span class="value blue" id="dash-proxy-status">检测中...</span>
                        <div class="meta" id="dash-proxy-meta">--</div>
                    </div>
                    <div class="dash-stat-card">
                        <span class="label">今日总耗电</span>
                        <span class="value highlight" style="color:var(--success)" id="dash-total-daily-energy">0.0</span>
                        <div class="meta" id="dash-total-daily-meta">单位 kWh · 参考总表 <strong>--</strong></div>
                    </div>
                    <div class="dash-stat-card"><span class="label">大门实时状态</span><span class="value" id="dash-door-status">连接中...</span></div>
                    <div class="dash-stat-card">
                        <span class="label">自动化总览</span>
                        <span class="value blue" id="dash-auto-total">0</span>
                        <div class="meta">已启用 <strong id="dash-auto-enabled">0</strong> · 异常 <strong id="dash-auto-errors">0</strong></div>
                    </div>
                </div>`;
    }

    function buildMonitorDomainMatrix() {
        const domains = [
            ['power', '强电柜', '等待强电柜快照'],
            ['light', '灯光', '等待灯光快照'],
            ['projector', '投影', '等待投影快照'],
            ['screen', '幕布', '等待幕布快照'],
            ['hvac', '空调', '等待空调快照'],
            ['sequencer', '时序电源', '等待时序电源快照'],
            ['ups', 'UPS', '等待 UPS 快照'],
            ['snmp', '网络/SNMP', '等待网络快照'],
            ['server', '服务器', '等待机器快照'],
            ['door', '门禁', '等待门禁快照'],
            ['automation', '自动化', '等待规则快照'],
            ['proxy', '代理出口', '等待代理探活'],
            ['local_model', 'AI 自然语言', '等待 AI 配置'],
            ['logs', '日志流', '等待运行日志'],
        ];
        return `
                <section class="monitor-panel monitor-panel-wide" id="dashboard-section-status_matrix" data-section-id="status_matrix">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">STATUS MATRIX</span><strong>运行状态矩阵</strong></div>
                        <span class="monitor-panel-note" id="dashboard-monitor-matrix-note">等待汇总快照</span>
                    </div>
                    <div class="monitor-domain-grid" id="dashboard-monitor-domains">
                        ${domains.map(([id, label, note]) => `
                            <div class="monitor-domain-tile" id="dashboard-domain-${id}">
                                <div class="monitor-domain-top"><span>${label}</span><em id="dashboard-domain-${id}-badge">读取中</em></div>
                                <div class="monitor-domain-value" id="dashboard-domain-${id}-value">--</div>
                                <div class="monitor-domain-note" id="dashboard-domain-${id}-note">${note}</div>
                                <div class="monitor-domain-bar"><span id="dashboard-domain-${id}-bar"></span></div>
                            </div>
                        `).join('')}
                    </div>
                </section>`;
    }

    function buildMonitorFocusSection() {
        return `
                <section class="monitor-panel monitor-panel-wide" id="dashboard-section-device_focus" data-section-id="device_focus">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">LIVE FEED</span><strong>关键设备态势</strong></div>
                        <span class="monitor-panel-note">实时缓存快照</span>
                    </div>
                    <div class="monitor-focus-grid">
                        <div class="monitor-focus-card">
                            <div class="monitor-focus-title">场馆设备</div>
                            <div class="monitor-feed-list" id="dashboard-monitor-site-feed"></div>
                        </div>
                        <div class="monitor-focus-card">
                            <div class="monitor-focus-title">电力与环境</div>
                            <div class="monitor-feed-list" id="dashboard-monitor-facility-feed"></div>
                        </div>
                        <div class="monitor-focus-card">
                            <div class="monitor-focus-title">网络与算力</div>
                            <div class="monitor-feed-list" id="dashboard-monitor-infra-feed"></div>
                        </div>
                        <div class="monitor-focus-card">
                            <div class="monitor-focus-title">自动化与 AI</div>
                            <div class="monitor-feed-list" id="dashboard-monitor-intelligence-feed"></div>
                        </div>
                    </div>
                </section>`;
    }

    function buildAiModelSection() {
        return `
                <section class="monitor-panel dashboard-ai-card" id="dashboard-section-ai_model" data-section-id="ai_model">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">AI ROUTE</span><strong>AI 自然语言与飞书</strong></div>
                        <span class="monitor-panel-note">云端/本地并行理解</span>
                    </div>
                    <div class="dashboard-ai-grid">
                        <div class="dashboard-ai-tile">
                            <span>当前优先级</span>
                            <strong id="dashboard-ai-priority">--</strong>
                            <em id="dashboard-ai-provider">--</em>
                        </div>
                        <div class="dashboard-ai-tile">
                            <span>云端模型</span>
                            <strong id="dashboard-ai-cloud">--</strong>
                            <em id="dashboard-ai-cloud-note">--</em>
                        </div>
                        <div class="dashboard-ai-tile">
                            <span>本地模型</span>
                            <strong id="dashboard-ai-local">--</strong>
                            <em id="dashboard-ai-local-note">--</em>
                        </div>
                        <div class="dashboard-ai-tile">
                            <span>飞书控制</span>
                            <strong id="dashboard-ai-feishu">--</strong>
                            <em id="dashboard-ai-feishu-note">--</em>
                        </div>
                    </div>
                </section>`;
    }

    function buildMonitorAlertsSection() {
        return `
                <section class="monitor-panel" id="dashboard-section-alerts" data-section-id="alerts">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">ALERTS</span><strong>告警与关注项</strong></div>
                        <span class="monitor-panel-note" id="dashboard-monitor-alert-count">--</span>
                    </div>
                    <div class="monitor-alert-list" id="dashboard-monitor-alert-list">
                        ${loadingText('正在汇总告警...')}
                    </div>
                </section>`;
    }

    function buildMonitorSnmpSection() {
        return `
                <section class="monitor-panel" id="dashboard-section-snmp" data-section-id="snmp">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">NETWORK</span><strong>网络与 SNMP 摘要</strong></div>
                        <span class="monitor-panel-note" id="dashboard-monitor-snmp-note">等待网络快照</span>
                    </div>
                    <div class="monitor-feed-list" id="dashboard-monitor-network-list">
                        ${loadingText('正在加载网络摘要...')}
                    </div>
                </section>`;
    }

    function buildMonitorServerSection() {
        return `
                <section class="monitor-panel" id="dashboard-section-server_compact" data-section-id="server_compact">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">COMPUTE</span><strong>机器状态</strong></div>
                        <span class="monitor-panel-note" id="dashboard-monitor-server-note">等待机器快照</span>
                    </div>
                    <div class="monitor-feed-list" id="dashboard-monitor-server-list">
                        ${loadingText('正在加载机器状态...')}
                    </div>
                    <div id="dashboard-server-compact-grid" hidden></div>
                </section>`;
    }

    function buildMonitorEnergySection() {
        return `
                <section class="monitor-panel home-total-log-card" id="dashboard-section-energy_trend" data-section-id="energy_trend">
                    <div class="monitor-panel-head">
                        <div><span class="monitor-panel-kicker">ENERGY</span><strong>电能消耗态势</strong></div>
                        <span class="monitor-panel-note" id="dashboard-energy-source">等待电表快照</span>
                    </div>
                    <div class="dashboard-energy-board">
                        <div class="dashboard-energy-main">
                            <span>今日总用电</span>
                            <strong id="dashboard-energy-total">-- kWh</strong>
                            <em id="dashboard-energy-compare">较昨日 --</em>
                        </div>
                        <div class="dashboard-energy-side">
                            <div class="dashboard-energy-metric">
                                <span>实时功率</span>
                                <strong id="dashboard-energy-power">-- kW</strong>
                            </div>
                            <div class="dashboard-energy-metric">
                                <span>本月累计</span>
                                <strong id="dashboard-energy-monthly">-- kWh</strong>
                            </div>
                        </div>
                    </div>
                    <div class="dashboard-energy-list" id="dashboard-energy-list">
                        ${loadingText('正在加载电能消耗快照...', 'padding:10px;')}
                    </div>
                </section>`;
    }

    function buildDashboardShell(configInput) {
        const config = configInput && typeof configInput === 'object' ? configInput : {};
        return [
            buildMonitorHero(),
            buildMonitorKpis(config),
            buildMonitorDomainMatrix(),
            buildMonitorFocusSection(),
            buildAiModelSection(),
            buildMonitorAlertsSection(),
            buildMonitorSnmpSection(),
            buildMonitorServerSection(),
            buildMonitorEnergySection(),
        ].join('\n');
    }

    function renderDashboardShell(configInput = global.configData, options = {}) {
        const root = global.document ? document.getElementById('view-dashboard') : null;
        if (!root) return false;
        const force = !!options.force;
        if (!force && root.dataset.dashboardShellRendered === '1') return true;
        root.innerHTML = buildDashboardShell(configInput);
        root.dataset.dashboardShellRendered = '1';
        root.dataset.dashboardShell = 'runtime';
        return true;
    }

    const api = {
        buildDashboardShell,
        renderDashboardShell,
    };

    SmartCenter.dashboardShell = Object.assign({}, SmartCenter.dashboardShell || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('dashboard-shell', {
            kind: 'view-shell',
            view: 'dashboard',
            exports: Object.keys(api),
            source: 'static/js/views/dashboard-shell.js',
        });
    }

    Object.assign(global, api);
})(window);
