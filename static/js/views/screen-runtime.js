// AI_MODULE: screen_runtime
// AI_PURPOSE: 幕布状态卡片、环境/UPS/自动化伴随卡片和幕布控制指令运行时。
// AI_BOUNDARY: 不负责环境、UPS、自动化的采集决策；只消费它们已经缓存到前端的数据。
// AI_DATA_FLOW: /api/screens -> 幕布卡片；用户点击 -> /api/screen/control；env/ups/automation cache -> 伴随卡片。
// AI_RUNTIME: 首页幕布区接近视口时按需加载，减少 app-runtime 首屏体积。
// AI_RISK: 高，包含真实幕布控制链路；必须保留权限校验、payload 和状态回读。
// AI_SEARCH_KEYWORDS: screen runtime, screen control, screen dashboard, curtain, 幕布.

(function installSmartCenterScreenRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.screenRuntime = Object.assign({}, SmartCenter.screenRuntime || {});

    function fallbackEscapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function getContext(context = {}) {
        return Object.assign({
            envConfigs: Array.isArray(global.__envConfigsCache)
                ? global.__envConfigsCache
                : (Array.isArray(global.configData?.env_sensors) ? global.configData.env_sensors : []),
            fetchJson: utils.fetchJson || global.fetchJson,
            postJsonLoose: utils.postJsonLoose || global.postJsonLoose,
            ensurePermission: utils.ensurePermission || global.ensurePermission,
            showToast: utils.showToast || global.showToast || (() => {}),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            getDeviceStatusMeta: utils.getDeviceStatusMeta || global.getDeviceStatusMeta || (status => ({
                level: status?.online ? 'online' : 'offline',
                text: status?.online ? '在线' : '离线',
                note: '',
                isOnlineLike: !!status?.online,
            })),
            getCardStateClass: utils.getCardStateClass || global.getCardStateClass || (() => ''),
            buildScreenUpsCards: global.buildScreenUpsCards,
            renderOutdoorAutomationDashboardCard: global.renderOutdoorAutomationDashboardCard,
        }, context || {});
    }

    function getScreenCommand(screen, action) {
        return (screen.commands || []).find(cmd => String(cmd.action || '').toLowerCase() === action) || null;
    }

    function getScreenActionText(status) {
        if (!status || status.online === false) return '离线';
        if (status.is_moving) return status.action === 'up' ? '正在上升...' : '正在下降...';
        return '已停止';
    }

    function getScreenActionColor(status) {
        if (!status || status.online === false) return '#94a3b8';
        if (status.is_moving) return 'var(--warning)';
        return 'var(--text-sub)';
    }

    function renderScreenControlButton(screen, action, label, className, context = {}) {
        const ctx = getContext(context);
        const cmd = getScreenCommand(screen, action);
        const iconMap = { up: '↑', stop: '■', down: '↓' };
        const icon = iconMap[action] || '•';
        if (!cmd) {
            return `<button class="screen-control-btn ${className}" disabled title="未配置${label}指令"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
        }
        return `<button class="screen-control-btn ${className}${ctx.getPermissionDisabledClass('screen.control')}" ${ctx.getPermissionDisabledAttrs('screen.control', '当前账号无幕布控制权限')} title="${label}" onclick="fireScreenCommand('${ctx.escapeHtml(screen.id)}', '${ctx.escapeHtml(cmd.payload || '')}', '${ctx.escapeHtml(cmd.format || 'hex')}', '${ctx.escapeHtml(cmd.action || action)}')"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
    }

    function buildScreenEnvCards(context = {}) {
        const ctx = getContext(context);
        const cards = [];
        if (Array.isArray(ctx.envConfigs) && ctx.envConfigs.length) {
            const envCache = global.__envStatusCache || {};
            const onlineEnv = ctx.envConfigs
                .map(cfg => ({ cfg, st: envCache?.[cfg.id] || {} }))
                .find(item => item.st && item.st.online);
            const fallbackEnv = ctx.envConfigs[0] ? { cfg: ctx.envConfigs[0], st: envCache?.[ctx.envConfigs[0].id] || {} } : null;
            const envItem = onlineEnv || fallbackEnv;
            if (envItem) {
                const cfg = envItem.cfg;
                const st = envItem.st || {};
                const online = !!st.online;
                const temp = st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--';
                const hum = st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--';
                const lux = st.lux !== null && st.lux !== undefined ? `${st.lux} Lux` : '--';
                const tempIcon = `<span class="screen-companion-metric-icon temp"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0v7.2a4.5 4.5 0 1 1-4 0V5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 14V8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.8" fill="currentColor"/></svg></span>`;
                const humIcon = `<span class="screen-companion-metric-icon hum"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.8C9.4 7.2 6 10.4 6 14.2A6 6 0 0 0 18 14.2c0-3.8-3.4-7-6-10.4Z" fill="currentColor" fill-opacity="0.92"/><path d="M9.6 15.4c.5 1.4 1.6 2.2 3 2.5" stroke="#dbeafe" stroke-width="1.4" stroke-linecap="round"/></svg></span>`;
                const luxIcon = `<span class="screen-companion-metric-icon lux"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.8v2.3M12 18.9v2.3M21.2 12h-2.3M5.1 12H2.8M18.6 5.4l-1.6 1.6M7 17l-1.6 1.6M18.6 18.6 17 17M7 7 5.4 5.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></span>`;
                cards.push(`<div class="screen-companion-card screen-companion-env">
                    <div class="screen-companion-title">
                        <span>${ctx.escapeHtml(cfg.name || cfg.id)}</span>
                        <span class="screen-companion-tag" style="${online ? '' : 'color:#cbd5e1;background:rgba(100,116,139,0.16);border-color:rgba(148,163,184,0.18);'}">${online ? '在线' : '离线'}</span>
                    </div>
                    <div class="screen-companion-metrics">
                        <div class="screen-companion-metric">
                            <div class="metric-label-wrap">${tempIcon}<div class="label">温度</div></div>
                            <div class="value">${ctx.escapeHtml(temp)}</div>
                        </div>
                        <div class="screen-companion-metric">
                            <div class="metric-label-wrap">${humIcon}<div class="label">湿度</div></div>
                            <div class="value">${ctx.escapeHtml(hum)}</div>
                        </div>
                        <div class="screen-companion-metric">
                            <div class="metric-label-wrap">${luxIcon}<div class="label">光照</div></div>
                            <div class="value">${ctx.escapeHtml(lux)}</div>
                        </div>
                    </div>
                    <div class="screen-companion-footer">
                        <span>来源 ${ctx.escapeHtml(cfg.name || cfg.id)}</span>
                        <span>${online ? '实时采集' : '等待恢复'}</span>
                    </div>
                </div>`);
            }
        }
        if (!cards.length) {
            cards.push(`<div class="screen-companion-card screen-placeholder-card">
                <div class="screen-companion-title">
                    <span class="screen-placeholder-icon">+</span>
                    <span>环境摘要</span>
                </div>
                <div class="screen-companion-note">这里显示环境传感器的温度、湿度和光照摘要。</div>
            </div>`);
        }
        return cards.join('');
    }

    function buildScreenAutomationCards() {
        return `<div class="dash-stat-card outdoor-automation-card" id="dash-outdoor-automation-card">
            <div class="outdoor-auto-head">
                <div class="outdoor-auto-title">户外灯自动化</div>
                <span class="outdoor-auto-chip" id="dash-outdoor-auto-chip">等待状态</span>
            </div>
            <div class="outdoor-auto-main">
                <div class="outdoor-auto-kpi">
                    <div class="value" id="dash-outdoor-lux">--</div>
                    <div class="sub" id="dash-outdoor-status-text">正在等待光照与自动化状态...</div>
                </div>
                <div class="outdoor-auto-metrics">
                    <div class="outdoor-auto-metric">
                        <div class="label">开灯窗口</div>
                        <div class="value" id="dash-outdoor-eta">--</div>
                    </div>
                    <div class="outdoor-auto-metric">
                        <div class="label">关灯计划</div>
                        <div class="value" id="dash-outdoor-off-countdown">--</div>
                    </div>
                    <div class="outdoor-auto-metric">
                        <div class="label">开灯条件</div>
                        <div class="value" id="dash-outdoor-window">--</div>
                    </div>
                    <div class="outdoor-auto-metric">
                        <div class="label">复位规则</div>
                        <div class="value" id="dash-outdoor-debounce">--</div>
                    </div>
                </div>
            </div>
            <div class="outdoor-auto-note" id="dash-outdoor-note">按自动化配置判断开灯和关灯计划。</div>
        </div>`;
    }

    function renderScreenStatusCard(screen, context = {}) {
        const ctx = getContext(context);
        const status = screen.status || {};
        const statusMeta = ctx.getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
        const isOnline = statusMeta.isOnlineLike;
        const position = Number.isFinite(Number(status.position)) ? Number(status.position) : 0;
        const height = Number.isFinite(Number(status.height)) ? Number(status.height) : 0;
        const totalHeight = screen.screen_config?.total_height || status.total_height || 3.0;
        const totalTime = screen.screen_config?.total_time || 30;
        const onlineText = statusMeta.text;
        const actionText = getScreenActionText(status);
        const remainingTime = Number.isFinite(Number(status.remaining_time)) ? Number(status.remaining_time).toFixed(1) : '0.0';
        const clampedPosition = Math.max(0, Math.min(100, position));
        const posState = clampedPosition >= 95 ? '全降（到底）' : (clampedPosition <= 5 ? '全升（到顶）' : '中间位置');
        return `<div class="screen-status-card ${isOnline ? '' : 'offline'} ${ctx.getCardStateClass(statusMeta)}" id="screen-status-${ctx.escapeHtml(screen.id)}">
            <div class="screen-status-header">
                <div class="screen-status-name">${ctx.escapeHtml(screen.name || screen.id)}</div>
                <div class="screen-status-online ${isOnline ? '' : 'offline'} ${statusMeta.level === 'stale' || statusMeta.level === 'error' ? 'warning' : ''}">${onlineText}</div>
            </div>
            <div class="screen-main-row">
                <div class="screen-core-meta">
                    <div class="screen-progress-panel">
                        <div class="screen-progress-rail" title="竖版位置进度">
                            <div class="screen-progress-fill-vertical" style="height:${clampedPosition}%; --screen-pos:${clampedPosition}%;"></div>
                        </div>
                        <div class="screen-progress-meta">
                            <div class="screen-progress-head">
                                <span class="screen-progress-label">当前位置</span>
                                <span class="screen-position-text">${clampedPosition.toFixed(1)}%</span>
                            </div>
                            <div class="screen-position-note">${posState}</div>
                            <div class="screen-metrics">
                                <div>
                                    <div class="screen-metric-label">当前高度</div>
                                    <div class="screen-metric-value">${height.toFixed(2)} 米</div>
                                </div>
                                <div>
                                    <div class="screen-metric-label">幕布状态</div>
                                    <div class="screen-metric-value" style="color:${getScreenActionColor(status)}">${ctx.escapeHtml(actionText)}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="screen-control-side">
                    ${renderScreenControlButton(screen, 'up', '上升', 'up', ctx)}
                    ${renderScreenControlButton(screen, 'stop', '停止', 'stop', ctx)}
                    ${renderScreenControlButton(screen, 'down', '下降', 'down', ctx)}
                </div>
            </div>
            <div class="screen-status-foot">
                <span>总高度：${ctx.escapeHtml(totalHeight)} 米</span>
                <span>全程时间：${ctx.escapeHtml(totalTime)} 秒</span>
                <span>剩余时间：${ctx.escapeHtml(remainingTime)} 秒</span>
            </div>
            <div class="dashboard-mini-note">${ctx.escapeHtml(statusMeta.note)}</div>
        </div>`;
    }

    function updateScreenCompanionPanels(context = {}) {
        const ctx = getContext(context);
        const screenEnvColumn = document.getElementById('screen-env-column');
        const screenUpsColumn = document.getElementById('screen-ups-column');
        const screenAutomationColumn = document.getElementById('screen-automation-column');
        if (screenEnvColumn) screenEnvColumn.innerHTML = buildScreenEnvCards(ctx);
        if (screenUpsColumn) {
            screenUpsColumn.innerHTML = typeof ctx.buildScreenUpsCards === 'function'
                ? ctx.buildScreenUpsCards()
                : `<div class="screen-companion-card screen-placeholder-card">
                    <div class="screen-companion-title">
                        <span class="screen-placeholder-icon">+</span>
                        <span>UPS 摘要</span>
                    </div>
                    <div class="screen-companion-note">这里显示 UPS 运行状态、电池和告警摘要。</div>
                </div>`;
        }
        if (screenAutomationColumn) {
            screenAutomationColumn.innerHTML = buildScreenAutomationCards(ctx);
            if (typeof ctx.renderOutdoorAutomationDashboardCard === 'function') {
                ctx.renderOutdoorAutomationDashboardCard();
            }
        }
    }

    function updateScreenStatus(context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.fetchJson !== 'function') {
            console.error('幕布状态更新失败', new Error('fetchJson_missing'));
            return Promise.resolve(null);
        }
        return ctx.fetchJson('/api/screens', {}, '幕布状态读取失败')
            .then(data => {
                const grid = document.getElementById('screen-status-grid');
                const screens = Array.isArray(data?.screens) ? data.screens : [];
                if (grid) {
                    grid.innerHTML = screens.length
                        ? screens.map(screen => renderScreenStatusCard(screen, ctx)).join('')
                        : '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置幕布设备</div>';
                }
                updateScreenCompanionPanels(ctx);
                return screens;
            })
            .catch(err => {
                console.error('幕布状态更新失败', err);
                return null;
            });
    }

    function fireScreenCommand(screenId, payload, format, action, context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.ensurePermission === 'function' && !ctx.ensurePermission('screen.control', '操作幕布')) return Promise.resolve(null);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('幕布控制运行库缺少请求方法', true);
            return Promise.resolve(null);
        }
        ctx.showToast('幕布指令下发中...', false);
        return ctx.postJsonLoose('/api/screen/control', {
            screen_id: screenId,
            command: { payload, format, action },
        }, '幕布指令下发失败')
            .then(data => {
                ctx.showToast(data.success ? '执行成功' : (`执行失败: ${data.response || data.msg || '未知错误'}`), !data.success);
                if (data.success) setTimeout(() => updateScreenStatus(ctx), 120);
                return data;
            })
            .catch(err => {
                console.error('幕布指令下发失败', err);
                ctx.showToast('幕布指令下发失败', true);
                return null;
            });
    }

    const api = {
        getScreenCommand,
        getScreenActionText,
        getScreenActionColor,
        renderScreenControlButton,
        buildScreenEnvCards,
        buildScreenAutomationCards,
        renderScreenStatusCard,
        updateScreenCompanionPanels,
        updateScreenStatus,
        fireScreenCommand,
    };

    Object.assign(state, api);
    Object.assign(global, api);

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('screen-runtime', {
            kind: 'runtime',
            exports: Object.keys(api),
            source: 'static/js/views/screen-runtime.js',
            risk: 'high',
        });
    }

    updateScreenCompanionPanels();
})(window);
