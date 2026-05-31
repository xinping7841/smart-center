// AI_MODULE: sequencer_runtime
// AI_PURPOSE: 时序电源首页摘要、详情页卡片、筛选和控制指令运行时。
// AI_BOUNDARY: 不实现后端通讯协议；只消费 /api/sequencer/status 并向 /api/sequencer/control 发送原有 payload。
// AI_DATA_FLOW: /api/sequencer/status -> sequencerStatusCache -> dashboard/page DOM；用户点击 -> /api/sequencer/control -> 状态回读。
// AI_RUNTIME: dashboard 时序电源区接近视口或进入 sequencer 视图时按需加载。
// AI_RISK: 高，包含真实时序电源控制链路；必须保留权限校验、payload 和状态回读延迟。
// AI_SEARCH_KEYWORDS: sequencer runtime, sequencer control, sequence power, 时序电源.

(function installSmartCenterSequencerRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.sequencerRuntime = Object.assign({
        statusCache: {},
        filters: { dashboard: 'all', page: 'all' },
    }, SmartCenter.sequencerRuntime || {});

    let sequencerStatusCache = state.statusCache || {};
    let sequencerFilters = Object.assign({ dashboard: 'all', page: 'all' }, state.filters || {});

    function fallbackEscapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function fallbackCompactText(value, maxLen = 88) {
        const text = String(value || '').trim();
        if (!text) return '--';
        if (text.length <= maxLen) return text;
        return `${text.slice(0, maxLen)}...`;
    }

    function getContext(context = {}) {
        return Object.assign({
            fetchJson: utils.fetchJson || global.fetchJson,
            postJsonLoose: utils.postJsonLoose || global.postJsonLoose,
            ensurePermission: utils.ensurePermission || global.ensurePermission,
            showToast: utils.showToast || global.showToast || (() => {}),
            translateApiError: utils.translateApiError || global.translateApiError || ((error, fallback) => String(error || fallback || '请求失败')),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            hasPermission: utils.hasPermission || global.hasPermission || (() => false),
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            compactText: SmartCenter.snmp?.compactSnmpText || global.compactSnmpText || fallbackCompactText,
            updateDashboardLogs: SmartCenter.logs?.updateDashboardLogs || global.updateDashboardLogs || (() => {}),
        }, context || {});
    }

    function getSequencerOnlineClass(device) {
        return device && device.online ? 'online' : 'offline';
    }

    function renderSequencerCard(device, context = {}) {
        const ctx = getContext(context);
        const channels = Array.isArray(device.channels) ? device.channels : [];
        const commMode = String(device.comm_mode || 'TCP').toUpperCase();
        const connectionText = commMode === 'COM'
            ? `${device.baudrate || 19200} / ${device.data_bits || 8}${String(device.parity || 'N').slice(0, 1)}${device.stop_bits || 1}`
            : `${device.ip || '--'}:${device.port || '--'}`;
        const sequencerLogs = Array.isArray(device.logs) ? device.logs.slice(0, 6) : [];
        const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
        const lastSuccessText = device.last_success_at ? new Date(device.last_success_at).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
        const currentStatusText = device.online
            ? `${device.mode || '时序模式'} / ${device.startup_mode || '手动'} / ${device.last_action || '待机'}`
            : `${device.last_action || '离线'}${device.error_display ? ' / ' + device.error_display : ''}`;
        const shortErrorText = device.error_display ? String(device.error_display).split(/[，,。]/)[0] : '';
        const channelHtml = channels.filter(ch => ch.visible !== false).map(ch => `
            <button class="sequencer-channel-btn ${ch.state ? 'on' : 'off'}${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                <span class="sequencer-inline-led ${ch.state ? 'on' : ''}"></span>
                <span class="name">${ctx.escapeHtml(ch.name || ('CH' + ch.channel))}</span>
                <span class="state">${ch.state ? '已开启' : '已关闭'}</span>
            </button>
        `).join('');
        const logHtml = sequencerLogs.length ? sequencerLogs.map(log => {
            const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
            const message = ctx.escapeHtml(String(log.operation || '').replace(/\[.*?\]\s*/, '') || '未命名记录');
            return `<div class="sequencer-mini-log-item"><span class="sequencer-mini-log-time">[${timeText}]</span><span class="sequencer-mini-log-text">${message}</span></div>`;
        }).join('') : '<div style="color:var(--text-sub); font-size:12px;">暂无时序电源日志</div>';
        return `<div class="sequencer-card ${getSequencerOnlineClass(device)}">
            <div class="sequencer-head">
                <div>
                    <div class="card-head-kicker">Sequencer Control</div>
                    <div class="sequencer-title">${ctx.escapeHtml(device.name || device.id)}</div>
                    <div class="sequencer-subtitle">地址 ${ctx.escapeHtml(String(device.address ?? 1))} / ${ctx.escapeHtml(device.protocol || 'DGH 8路时序器')} / ${ctx.escapeHtml(device.brand || 'DGH')}</div>
                </div>
                <div class="status-chip-stack">
                    <span class="sequencer-tag ${device.online ? 'online' : ''}">${device.online ? '在线' : '离线'}</span>
                    <span class="sequencer-tag ${device.locked ? 'locked' : ''}">${device.locked ? '已锁定' : '未锁定'}</span>
                    ${(!device.online && shortErrorText) ? `<span class="sequencer-tag error">${ctx.escapeHtml(shortErrorText)}</span>` : ''}
                </div>
            </div>
            <div class="sequencer-summary-text">通道状态摘要: ${ctx.escapeHtml(device.channel_summary || '无通道状态')}</div>
            <div class="sequencer-meta">
                <div class="sequencer-meta-item"><div class="label">接入方式</div><div class="value">${ctx.escapeHtml(commMode)}</div></div>
                <div class="sequencer-meta-item"><div class="label">${commMode === 'COM' ? '串口参数' : '网络地址'}</div><div class="value">${ctx.escapeHtml(String(connectionText))}</div></div>
                <div class="sequencer-meta-item"><div class="label">当前状态</div><div class="value">${ctx.escapeHtml(currentStatusText)}</div></div>
                <div class="sequencer-meta-item log"><div class="label">最近操作</div><div class="sequencer-mini-log-list">${logHtml}</div></div>
            </div>
            <div class="sequencer-toolbar">
                <button class="sequencer-action-btn seq-on${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'sequence_on')">顺序开启</button>
                <button class="sequencer-action-btn seq-off${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'sequence_off')">顺序关闭</button>
                <button class="sequencer-action-btn all-on${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'all_on')">全部开启</button>
                <button class="sequencer-action-btn all-off${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'all_off')">全部关闭</button>
                <button class="sequencer-action-btn lock${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'toggle_lock')">${device.locked ? '解除锁定' : '锁定设备'}</button>
            </div>
            <div class="sequencer-channel-grid">${channelHtml || '<div style="grid-column:1/-1;color:var(--text-sub);">未配置通道</div>'}</div>
            <div class="sequencer-diagnostics">
                <div class="sequencer-diag-item">
                    <div class="label">最后轮询</div>
                    <div class="value">${ctx.escapeHtml(updatedAtText)}</div>
                </div>
                <div class="sequencer-diag-item">
                    <div class="label">最后成功通讯</div>
                    <div class="value">${ctx.escapeHtml(lastSuccessText)}</div>
                </div>
                <div class="sequencer-diag-item">
                    <div class="label">最后指令</div>
                    <div class="value">${ctx.escapeHtml(device.last_command_hex || '--')}</div>
                </div>
                <div class="sequencer-diag-item">
                    <div class="label">最后回包</div>
                    <div class="value">${ctx.escapeHtml(device.last_response_hex || '--')}</div>
                </div>
            </div>
            ${device.error ? `<div class="card-inline-note error">通讯异常：${ctx.escapeHtml(device.error)}</div>` : ''}
        </div>`;
    }

    function renderCompactSequencerCard(device, context = {}) {
        const ctx = getContext(context);
        const visibleChannels = Array.isArray(device?.channels) ? device.channels.filter(ch => ch && ch.visible !== false).slice(0, 8) : [];
        const canControlChannels = ctx.hasPermission('sequencer.control');
        const channelHtml = visibleChannels.map(ch => {
            const title = canControlChannels
                ? `${ch.name || ('CH' + ch.channel)} · 点击切换`
                : '当前账号无时序电源控制权限';
            return `
            <button type="button" class="dashboard-sequencer-channel ${ch.state ? 'on' : 'off'}${canControlChannels ? '' : ' is-disabled'}" ${canControlChannels ? '' : 'disabled'} title="${ctx.escapeHtml(title)}" onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                <span class="dashboard-sequencer-channel-index">${ctx.escapeHtml(String(ch.channel || '--'))}</span>
                <span class="dashboard-sequencer-channel-led"></span>
                <span class="dashboard-sequencer-channel-state">${ch.state ? '开' : '关'}</span>
            </button>`;
        }).join('');
        const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
        const actionText = device.last_action || (device.online ? '待机' : '离线');
        const modeText = device.startup_mode || device.mode || '手动';
        const summaryText = device.channel_summary || `${visibleChannels.filter(ch => ch.state).length}/${visibleChannels.length || 0} 路开启`;
        return `<div class="dashboard-sequencer-panel ${device && device.online ? '' : 'offline'}">
            <div class="dashboard-sequencer-device">
                <div class="dashboard-sequencer-title-row">
                    <div class="dashboard-sequencer-name">${ctx.escapeHtml(device.name || device.id)}</div>
                </div>
                <div class="dashboard-sequencer-meta">
                    <span class="ups-chip ${device && device.online ? 'online' : 'error'}">${device && device.online ? '在线' : '离线'}</span>
                    <span class="ups-chip ${device && device.locked ? 'warning' : ''}">${device && device.locked ? '锁定' : '可控'}</span>
                    <span>${ctx.escapeHtml(modeText)}</span>
                    <span class="dot"></span>
                    <span>${ctx.escapeHtml(actionText)}</span>
                    <span class="dot"></span>
                    <span>${ctx.escapeHtml(ctx.compactText(summaryText, 14))}</span>
                </div>
            </div>
            <div class="dashboard-sequencer-strip">${channelHtml || '<div class="dashboard-sequencer-empty" style="grid-column:1/-1;">未配置通道</div>'}</div>
            <div class="dashboard-sequencer-actions">
                <button class="dashboard-mini-btn success${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'sequence_on')">顺开</button>
                <button class="dashboard-mini-btn danger${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'sequence_off')">顺关</button>
                <button class="dashboard-mini-btn secondary${ctx.getPermissionDisabledClass('sequencer.control')}" ${ctx.getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${ctx.escapeHtml(device.id)}', 'all_off')">全关</button>
                <span class="dashboard-mini-note">更新 ${ctx.escapeHtml(updatedAtText)}</span>
            </div>
        </div>`;
    }

    function getSortedSequencerDevices() {
        const devices = Array.isArray(sequencerStatusCache.devices) ? [...sequencerStatusCache.devices] : [];
        return devices.sort((a, b) => {
            const sortDiff = Number(a.sort_order || 999) - Number(b.sort_order || 999);
            if (sortDiff !== 0) return sortDiff;
            const nameA = String(a.name || a.id || '').toLowerCase();
            const nameB = String(b.name || b.id || '').toLowerCase();
            const nameDiff = nameA.localeCompare(nameB, 'zh-CN');
            if (nameDiff !== 0) return nameDiff;
            return String(a.ip || '').localeCompare(String(b.ip || ''), 'zh-CN');
        });
    }

    function filterSequencerDevices(devices, mode) {
        if (mode === 'online') return devices.filter(item => item.online);
        if (mode === 'offline') return devices.filter(item => !item.online || !!item.error_display);
        return devices;
    }

    function setSequencerFilter(mode, scope = 'dashboard', context = {}) {
        sequencerFilters[scope] = mode;
        state.filters = sequencerFilters;
        const wrapId = scope === 'dashboard' ? 'dashboard-sequencer-filters' : 'page-sequencer-filters';
        const wrap = document.getElementById(wrapId);
        if (wrap) {
            wrap.querySelectorAll('.sequencer-filter-btn').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.includes(mode === 'all' ? '全部' : mode === 'online' ? '在线' : '离线/异常'));
            });
        }
        renderSequencerCards(context);
    }

    function renderSequencerCards(context = {}) {
        const ctx = getContext(context);
        const devices = getSortedSequencerDevices();
        const dashboardGrid = document.getElementById('dashboard-sequencer-grid');
        const pageGrid = document.getElementById('sequencer-page-grid');
        const dashboardDevices = filterSequencerDevices(devices, sequencerFilters.dashboard);
        const pageDevices = filterSequencerDevices(devices, sequencerFilters.page);
        const dashboardHtml = dashboardDevices.length ? dashboardDevices.map(device => renderCompactSequencerCard(device, ctx)).join('') : '<div class="dashboard-sequencer-empty">当前筛选条件下暂无时序电源设备</div>';
        const pageHtml = pageDevices.length ? pageDevices.map(device => renderSequencerCard(device, ctx)).join('') : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">当前筛选条件下暂无时序电源设备</div>';
        if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
        if (pageGrid) pageGrid.innerHTML = pageHtml;
        const totalEl = document.getElementById('dash-sequencer-total');
        const onlineEl = document.getElementById('dash-sequencer-online');
        if (totalEl) totalEl.innerText = devices.length;
        if (onlineEl) onlineEl.innerText = devices.filter(item => item.online).length;
    }

    function updateSequencerStatus(context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.fetchJson !== 'function') {
            console.error('时序电源状态更新失败', new Error('fetchJson_missing'));
            return Promise.resolve(null);
        }
        return ctx.fetchJson('/api/sequencer/status', {}, '时序电源状态读取失败')
            .then(data => {
                sequencerStatusCache = data || {};
                state.statusCache = sequencerStatusCache;
                global.sequencerStatusCache = sequencerStatusCache;
                renderSequencerCards(ctx);
                return sequencerStatusCache;
            })
            .catch(err => {
                console.error('时序电源状态更新失败', err);
                return null;
            });
    }

    function fireSequencerAction(id, action, channel = null, context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.ensurePermission === 'function' && !ctx.ensurePermission('sequencer.control', '操作时序电源')) return Promise.resolve(null);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('时序电源控制运行库缺少请求方法', true);
            return Promise.resolve(null);
        }
        ctx.showToast('时序电源指令下发中...', false);
        return ctx.postJsonLoose('/api/sequencer/control', { id, action, channel }, '时序电源指令下发失败')
            .then(data => {
                if (!data.success) {
                    ctx.showToast(data.message || data.msg || '执行失败', true);
                    return data;
                }
                ctx.showToast(`执行成功${data.command ? ' - ' + data.command : ''}`);
                if (data.device && Array.isArray(data.device.channels)) {
                    sequencerStatusCache = sequencerStatusCache || {};
                    sequencerStatusCache.devices = Array.isArray(sequencerStatusCache.devices) ? sequencerStatusCache.devices : [];
                    const idx = sequencerStatusCache.devices.findIndex(item => item && item.id === data.device.id);
                    if (idx >= 0) sequencerStatusCache.devices[idx] = data.device;
                    else sequencerStatusCache.devices.push(data.device);
                    state.statusCache = sequencerStatusCache;
                    global.sequencerStatusCache = sequencerStatusCache;
                    renderSequencerCards(ctx);
                }
                [350, 900, 1800, 3500].forEach(delay => setTimeout(() => updateSequencerStatus(ctx), delay));
                setTimeout(() => ctx.updateDashboardLogs(), 300);
                return data;
            })
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, '网络请求失败'), true);
                return null;
            });
    }

    const api = {
        getSequencerOnlineClass,
        renderSequencerCard,
        renderCompactSequencerCard,
        getSortedSequencerDevices,
        filterSequencerDevices,
        setSequencerFilter,
        renderSequencerCards,
        updateSequencerStatus,
        fireSequencerAction,
    };

    Object.assign(state, api);
    Object.assign(global, api);
    global.sequencerStatusCache = sequencerStatusCache;

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('sequencer-runtime', {
            kind: 'runtime',
            exports: Object.keys(api),
            source: 'static/js/views/sequencer-runtime.js',
            risk: 'high',
        });
    }
})(window);
