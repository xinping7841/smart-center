// AI_MODULE: dashboard_shell_view
// AI_PURPOSE: 用运行时生成首页静态骨架，减少 templates/index.html 体积并让首页 DOM 可缓存维护。
// AI_BOUNDARY: 只生成首页容器和占位内容；不拉取接口、不执行控制、不改变任何设备状态。
// AI_DATA_FLOW: window.configData -> #view-dashboard shell -> app-runtime 继续排序、轮询和填充实时数据。
// AI_RUNTIME: app-runtime 初始化首页排序/观察器前必须可用；保持所有旧 DOM id 和 data-section-id 稳定。
// AI_RISK: 中，首页首屏依赖这些 id；修改时必须同步检查 app-runtime/dashboard summary 引用。
// AI_SEARCH_KEYWORDS: dashboard shell, homepage skeleton, template slim, dashboard sections.

(function installSmartCenterDashboardShell(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function listLength(value) {
        return Array.isArray(value) ? value.length : 0;
    }

    function hasItems(config, key) {
        return listLength(config && config[key]) > 0;
    }

    function loadingText(text, extraStyle = '') {
        return `<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;${extraStyle}">${text}</div>`;
    }

    function buildDashboardStats(config) {
        const cabinetsTotal = listLength(config.cabinets);
        const lightTotal = listLength(config.light_devices);
        const projectorTotal = listLength(config.projectors);
        const hvacTotal = listLength(config.hvac_devices);
        return `
                <div class="dash-grid" id="dashboard-section-stats" data-section-id="stats">
                    <div class="dash-stat-card"><span class="label">强电柜在线 / 总数</span><span class="value blue"><span id="dash-power-online">0</span> / ${cabinetsTotal}</span><span class="dash-stat-icon">⚡</span></div>
                    <div class="dash-stat-card"><span class="label">灯光模块在线 / 总数</span><span class="value blue"><span id="dash-light-online">0</span> / ${lightTotal}</span><span class="dash-stat-icon">💡</span></div>
                    <div class="dash-stat-card"><span class="label">投影机在线 / 总数</span><span class="value blue"><span id="dash-projector-online">0</span> / <span id="dash-projector-total">${projectorTotal}</span></span><span class="dash-stat-icon">📽</span></div>
                    <div class="dash-stat-card"><span class="label">空调在线 / 总数</span><span class="value blue"><span id="dash-hvac-online">0</span> / ${hvacTotal}</span><span class="dash-stat-icon">❄</span></div>
                    <div class="dash-stat-card"><span class="label">时序电源在线 / 总数</span><span class="value blue"><span id="dash-sequencer-online">0</span> / <span id="dash-sequencer-total">0</span></span><span class="dash-stat-icon">〽</span></div>
                    <div class="dash-stat-card">
                        <span class="label">SNMP 在线 / 报警</span>
                        <span class="value blue"><span id="dash-snmp-online">0</span> / <span id="dash-snmp-alert">0</span></span>
                        <div class="meta">总数 <strong id="dash-snmp-total">0</strong> · 高危 <strong id="dash-snmp-critical">0</strong> · 中危 <strong id="dash-snmp-warning">0</strong></div>
                        <span class="dash-stat-icon">📡</span>
                    </div>
                    <div class="dash-stat-card"><span class="label">服务器在线 / 总数</span><span class="value blue"><span id="dash-server-online">0</span> / <span id="dash-server-total">0</span></span><span class="dash-stat-icon">🖥</span></div>
                    <div class="dash-stat-card">
                        <span class="label">公司代理状态</span>
                        <span class="value blue" id="dash-proxy-status">检测中...</span>
                        <div class="meta" id="dash-proxy-meta">--</div>
                        <span class="dash-stat-icon">🌐</span>
                    </div>
                    <div class="dash-stat-card">
                        <span class="label">场馆今日总耗电</span>
                        <span class="value highlight" style="color:var(--success)" id="dash-total-daily-energy">0.0</span>
                        <div class="meta" id="dash-total-daily-meta">单位 kWh · 参考总表 <strong>--</strong></div>
                        <span class="dash-stat-icon">＋</span>
                    </div>
                    <div class="dash-stat-card"><span class="label">大门实时状态</span><span class="value" id="dash-door-status">连接中...</span><span class="dash-stat-icon">🚪</span></div>
                    <div class="dash-stat-card">
                        <span class="label">自动化总览</span>
                        <span class="value blue" id="dash-auto-total">0</span>
                        <div class="meta">已启用 <strong id="dash-auto-enabled">0</strong> · 异常 <strong id="dash-auto-errors">0</strong></div>
                        <span class="dash-stat-icon">◎</span>
                    </div>
                </div>`;
    }

    function buildDashboardCard(id, sectionId, title, subtitle, bodyClass, bodyId, placeholder, bodyStyle = '') {
        const styleAttr = bodyStyle ? ` style="${bodyStyle}"` : '';
        return `
                <div class="card" style="margin-top: 20px;" id="${id}" data-section-id="${sectionId}">
                    <div class="card-title">
                        <span>${title}</span>
                        <span style="font-size:12px; color:var(--text-sub);">${subtitle}</span>
                    </div>
                    <div class="${bodyClass}" id="${bodyId}"${styleAttr}>
                        ${placeholder}
                    </div>
                </div>`;
    }

    function buildScreenSection() {
        return `
                <div class="card" style="margin-top: 20px;" id="dashboard-section-screen" data-section-id="screen">
                    <div class="card-title">
                        <span>幕布状态与控制</span>
                        <span style="font-size:12px; color:var(--text-sub);">状态按时间模拟线性变化，控制按钮已并入卡片</span>
                    </div>
                    <div class="screen-dashboard-shell">
                        <div class="screen-dashboard-layout">
                            <div class="screen-status-grid" id="screen-status-grid">
                                ${loadingText('正在加载状态...')}
                            </div>
                            <div class="screen-env-column" id="screen-env-column">
                                <div class="screen-column-head"><span>环境</span><span class="accent">温湿度 / 光照</span></div>
                                <div class="screen-companion-card">
                                    <div class="screen-companion-title"><span>环境摘要</span><span class="screen-companion-tag">加载中</span></div>
                                    <div class="screen-companion-note">正在同步环境传感器状态...</div>
                                </div>
                            </div>
                            <div class="screen-ups-column" id="screen-ups-column">
                                <div class="screen-column-head"><span>UPS</span><span class="accent">供电 / 电池 / 告警</span></div>
                                <div class="screen-companion-card">
                                    <div class="screen-companion-title"><span>UPS 摘要</span><span class="screen-companion-tag">加载中</span></div>
                                    <div class="screen-companion-note">正在同步 UPS 状态...</div>
                                </div>
                            </div>
                            <div class="screen-automation-column" id="screen-automation-column">
                                <div class="screen-column-head"><span>自动化</span><span class="accent">户外灯</span></div>
                                <div class="screen-companion-card">
                                    <div class="screen-companion-title"><span>自动化摘要</span><span class="screen-companion-tag">加载中</span></div>
                                    <div class="screen-companion-note">正在同步自动化状态...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
    }

    function buildHyEdgeSection() {
        return `
                <div class="card" style="margin-top: 20px;" id="dashboard-section-hy_edge" data-section-id="hy_edge">
                    <div class="card-title">
                        <span>HY506 异地机房</span>
                        <span style="font-size:12px; color:var(--text-sub);">从 HY506-Node-254 汇总拉取网关、交换机、UPS 与本机状态</span>
                    </div>
                    <div class="hy-edge-summary" id="dashboard-hy-edge-summary">
                        <span class="ups-chip">正在连接 HY506 边缘节点...</span>
                    </div>
                    <div class="hy-edge-grid" id="dashboard-hy-edge-grid">
                        ${loadingText('正在加载 HY506 异地状态...')}
                    </div>
                </div>`;
    }

    function buildDashboardShell(configInput) {
        const config = configInput && typeof configInput === 'object' ? configInput : {};
        const sections = [buildDashboardStats(config)];

        if (hasItems(config, 'projectors')) {
            sections.push(buildDashboardCard(
                'dashboard-section-projector',
                'projector',
                '投影机总览',
                '仅保留名称、IP 与开关状态',
                'projector-card-grid',
                'dashboard-projector-grid',
                loadingText('正在加载投影机控制卡片...')
            ));
        }

        if (hasItems(config, 'hvac_devices')) {
            sections.push(buildDashboardCard(
                'dashboard-section-hvac',
                'hvac',
                '空调总览',
                'Home Assistant 桥接状态与快捷控制',
                'hvac-dashboard-grid',
                'dashboard-hvac-grid',
                '<div class="hvac-empty">正在加载空调状态...</div>'
            ));
        }

        sections.push(buildHyEdgeSection());

        sections.push(`
                <div class="card" style="margin-top: 20px;" id="dashboard-section-sequencer" data-section-id="sequencer">
                    <div class="card-title">
                        <span>时序电源</span>
                        <span style="font-size:12px; color:var(--text-sub);">每路状态与主页快捷开关</span>
                    </div>
                    <div class="sequencer-filter-bar" id="dashboard-sequencer-filters">
                        <button class="sequencer-filter-btn active" onclick="setSequencerFilter('all', 'dashboard')">全部</button>
                        <button class="sequencer-filter-btn" onclick="setSequencerFilter('online', 'dashboard')">在线</button>
                        <button class="sequencer-filter-btn" onclick="setSequencerFilter('offline', 'dashboard')">离线/异常</button>
                    </div>
                    <div class="dashboard-sequencer-grid" id="dashboard-sequencer-grid">
                        ${loadingText('正在加载时序电源状态...')}
                    </div>
                </div>`);

        if (hasItems(config, 'ups_devices') && !hasItems(config, 'screens')) {
            sections.push(buildDashboardCard(
                'dashboard-section-ups',
                'ups',
                'UPS 总览',
                '仅保留电池、负载、输入/输出电压',
                'ups-grid',
                'dashboard-ups-grid',
                loadingText('正在加载 UPS 状态...')
            ));
        }

        if (hasItems(config, 'snmp_devices')) {
            sections.push(`
                <div class="card" style="margin-top: 20px;" id="dashboard-section-snmp" data-section-id="snmp">
                    <div class="dashboard-compact-grid" id="dashboard-snmp-grid">
                        ${loadingText('正在加载 SNMP 状态...')}
                    </div>
                </div>`);
        }

        if (hasItems(config, 'screens')) sections.push(buildScreenSection());

        if (hasItems(config, 'cabinets')) {
            sections.push(buildDashboardCard(
                'dashboard-section-power_compact',
                'power_compact',
                '强电柜状态',
                '状态、功率、能耗与每路开关',
                'dashboard-home-grid',
                'dashboard-power-compact-grid',
                loadingText('正在加载强电柜状态...', 'padding:14px;')
            ));
        }

        if (hasItems(config, 'light_devices')) {
            sections.push(buildDashboardCard(
                'dashboard-section-light_compact',
                'light_compact',
                '灯光控制',
                '在线状态与常用通道开关',
                'dashboard-home-grid',
                'dashboard-light-compact-grid',
                loadingText('正在加载灯光状态...', 'padding:14px;')
            ));
        }

        sections.push(buildDashboardCard(
            'dashboard-section-server_compact',
            'server_compact',
            '机器状态',
            '分组状态灯与异常提示',
            'dashboard-home-grid',
            'dashboard-server-compact-grid',
            loadingText('正在加载机器状态...', 'padding:14px;')
        ));

        sections.push(`
                <div class="card home-total-log-card" style="margin-top: 20px;" id="dashboard-section-energy_trend" data-section-id="energy_trend">
                    <div class="card-title">
                        <span>总日志</span>
                        <span class="home-ui-period-pill">中控触发 / 外部变化</span>
                    </div>
                    <div class="home-total-log-subtitle">只要识别到设备状态变化，都会写入这里。</div>
                    <div class="log-list home-total-log-list" id="dashboard-logs"></div>
                </div>`);

        if (hasItems(config, 'ups_devices')) {
            sections.push(buildDashboardCard(
                'dashboard-section-ups_compact',
                'ups_compact',
                'UPS 状态',
                '在线、电池、负载、输入输出与告警',
                'dashboard-home-grid',
                'dashboard-ups-compact-grid',
                loadingText('正在加载 UPS 状态...', 'padding:14px;')
            ));
        }

        if (hasItems(config, 'cabinets')) {
            sections.push(buildDashboardCard(
                'dashboard-section-power_quick',
                'power_quick',
                '强电柜总览与控制',
                '保留在线、功率、能耗、关键通道与最近操作',
                'dashboard-power-grid',
                'dashboard-power-grid',
                '<div style="color:var(--text-sub); text-align:center; padding:20px; border:1px dashed rgba(148,163,184,0.2); border-radius:12px;">正在加载强电柜状态...</div>'
            ));
        }

        if (hasItems(config, 'light_devices')) {
            sections.push(buildDashboardCard(
                'dashboard-section-light_quick',
                'light_quick',
                '灯光模块',
                '简洁模式显示在线状态与常用通道',
                'dashboard-compact-grid',
                'dashboard-light-grid',
                loadingText('正在加载灯光模块...')
            ));
        }

        sections.push(buildDashboardCard(
            'dashboard-section-system_logs',
            'system_logs',
            '系统操作日志',
            '最近操作记录',
            'log-list',
            'dashboard-logs-legacy',
            '',
            'height: 300px;'
        ));

        return sections.join('\n');
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

    global.renderDashboardShell = renderDashboardShell;
})(window);
