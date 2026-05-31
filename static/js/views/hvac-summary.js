// AI_MODULE: hvac_summary_view
// AI_PURPOSE: 首页空调总览轻量渲染，避免 dashboard 首屏加载完整 hvac-view.js。
// AI_BOUNDARY: 只渲染首页摘要与开关快捷按钮；完整空调页、模式/温度弹层由 hvac-view.js 负责。
// AI_DATA_FLOW: /api/hvac/status + /api/env/status 缓存 -> dashboard-hvac-grid DOM。
// AI_RUNTIME: 首页按需加载；点击“详情”进入空调页时再加载完整模块。
// AI_RISK: 中，首页仍保留空调开关按钮，必须继续走全局 controlHvac 权限链路。
// AI_SEARCH_KEYWORDS: hvac summary, dashboard hvac, lightweight hvac, air conditioner.

(function installSmartCenterHvacSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.hvacSummary = Object.assign({}, SmartCenter.hvacSummary || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));

    function getContext(context = {}) {
        const provider = typeof global.getHvacViewContext === 'function'
            ? (global.getHvacViewContext() || {})
            : {};
        return Object.assign({}, provider, context || {});
    }

    function formatHvacTemperature(value) {
        const num = Number(value);
        return Number.isFinite(num) ? `${num}°C` : '--';
    }

    function formatHvacPower(status) {
        const watt = Number(status?.electric_power_w);
        if (Number.isFinite(watt)) {
            if (Math.abs(watt) >= 1000) return `${(watt / 1000).toFixed(2)} kW`;
            return `${watt.toFixed(watt >= 100 ? 0 : 2)} W`;
        }
        const kw = Number(status?.electric_power_kw);
        if (Number.isFinite(kw)) return `${kw.toFixed(3)} kW`;
        return '--';
    }

    function getHvacModeText(mode) {
        const map = {
            off: '关闭',
            cool: '制冷',
            heat: '制热',
            dry: '除湿',
            fan_only: '送风',
            auto: '自动',
            heat_cool: '自动冷热',
        };
        const key = String(mode || '').trim().toLowerCase();
        return map[key] || (mode ? String(mode) : '--');
    }

    function getHvacActionText(action) {
        const map = {
            cooling: '制冷中',
            heating: '制热中',
            drying: '除湿中',
            fan: '送风中',
            idle: '待机',
            off: '已关闭',
        };
        const key = String(action || '').trim().toLowerCase();
        return map[key] || (action ? String(action) : '--');
    }

    function getHvacModeClass(mode) {
        const key = String(mode || '').trim().toLowerCase();
        if (key === 'cool') return 'cool';
        if (key === 'heat') return 'heat';
        if (key === 'dry') return 'dry';
        if (key === 'fan_only' || key === 'fan') return 'fan';
        if (key === 'auto' || key === 'heat_cool') return 'auto';
        if (key === 'off') return 'off';
        return '';
    }

    function getHvacCardStateClass(status) {
        if (!status?.online) return 'offline';
        return status?.power ? 'running' : 'standby';
    }

    function getHvacActionClass(status) {
        if (!status?.online) return 'idle';
        const action = String(status?.hvac_action || '').trim().toLowerCase();
        if (action === 'cooling') return 'cooling';
        if (action === 'heating') return 'heating';
        if (status?.power) return 'running';
        return 'idle';
    }

    function getHvacPowerButtonClass(status) {
        if (!status?.online) return 'unknown';
        return status?.power ? 'on' : 'off';
    }

    function getPowerIconHtml() {
        if (typeof global.getProjectorIconHtml === 'function') return global.getProjectorIconHtml('power');
        return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 4.2v7.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
            <path d="M7.4 6.5A8 8 0 1 0 16.6 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
        </svg>`;
    }

    function getHvacAgeText(status) {
        const ageSec = Number(status?.age_sec);
        if (!Number.isFinite(ageSec)) return '--';
        if (ageSec < 60) return `${Math.round(ageSec)} 秒前`;
        if (ageSec < 3600) return `${Math.round(ageSec / 60)} 分钟前`;
        return `${(ageSec / 3600).toFixed(1)} 小时前`;
    }

    function formatCompactAgeFromSec(ageSec) {
        const value = Number(ageSec);
        if (!Number.isFinite(value)) return '';
        if (value < 60) return `${Math.round(value)}秒前`;
        if (value < 3600) return `${Math.round(value / 60)}分钟前`;
        if (value < 86400) return `${Math.round(value / 3600)}小时前`;
        return `${Math.round(value / 86400)}天前`;
    }

    function getHvacRoomName(cfg) {
        const text = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
        if (text) return text;
        const source = `${cfg?.name || ''} ${cfg?.id || ''}`.toLowerCase();
        if (/一号厅|1号厅|hall1|a1|a2|沉浸|b厅/.test(source)) return '一号厅';
        if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
        if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
        if (/机房|shenlan|machine|server/.test(source)) return '主机房';
        if (/咖啡|cafe/.test(source)) return '咖啡厅';
        if (/办公室|office/.test(source)) return '办公室二楼';
        return '未分区';
    }

    function getHvacSortOrder(cfg) {
        const value = Number(cfg?.sort_order);
        if (Number.isFinite(value)) return value;
        const match = String(cfg?.name || '').match(/(\d+)/);
        return match ? Number(match[1]) : 999;
    }

    function getHvacRoomSort(roomName) {
        const text = String(roomName || '').trim();
        const priority = {
            '机房': 1,
            '主机房': 1,
            '一号厅': 2,
            '二号厅': 3,
            '办公室': 4,
            '办公室二楼': 4,
            '办公室二楼会议室': 5,
            '咖啡厅': 6,
            '庭院': 7,
        };
        return Number.isFinite(priority[text]) ? priority[text] : 99;
    }

    function getHvacGroupClass(roomName) {
        const text = String(roomName || '').trim();
        if (text === '机房' || text === '主机房') return 'hvac-group-machine';
        if (text.includes('一号厅')) return 'hvac-group-hall1';
        if (text.includes('二号厅')) return 'hvac-group-hall2';
        if (text.includes('咖啡')) return 'hvac-group-cafe';
        if (text.includes('会议室')) return 'hvac-group-meeting';
        if (text.includes('办公室')) return 'hvac-group-office';
        return 'hvac-group-misc';
    }

    function getHvacGroupAccent(roomName) {
        const text = String(roomName || '').trim();
        if (text === '机房' || text === '主机房') return { accent: '#22c55e' };
        if (text.includes('一号厅')) return { accent: '#38bdf8' };
        if (text.includes('二号厅')) return { accent: '#818cf8' };
        if (text.includes('咖啡')) return { accent: '#fb923c' };
        if (text.includes('会议室')) return { accent: '#a855f7' };
        if (text.includes('办公室')) return { accent: '#0ea5e9' };
        return { accent: '#64748b' };
    }

    function normalizeHvacEnvRoomName(value) {
        const text = String(value || '').trim();
        const source = text.toLowerCase();
        if (!text) return '';
        if (/机房|深澜|server|machine/.test(source)) return '主机房';
        if (/一号厅|1号厅|hall1|沉浸/.test(source)) return '一号厅';
        if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
        if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
        if (/二楼办公室|办公室二楼|office|办公室/.test(source)) return '办公室二楼';
        if (/咖啡|cafe/.test(source)) return '咖啡厅';
        return text;
    }

    function getEnvSensorRoomName(cfg) {
        const explicit = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
        if (explicit) return normalizeHvacEnvRoomName(explicit);
        return normalizeHvacEnvRoomName(`${cfg?.name || ''} ${cfg?.id || ''}`);
    }

    function getEnvThermalAgeSec(st) {
        const ages = [Number(st?.temp_age_sec), Number(st?.hum_age_sec), Number(st?.age_sec)]
            .filter(value => Number.isFinite(value));
        return ages.length ? Math.min(...ages) : null;
    }

    function envSensorHasThermalValue(st) {
        return Number.isFinite(Number(st?.temp)) || Number.isFinite(Number(st?.hum));
    }

    function findRoomEnvSensors(roomName, limit = 2) {
        const data = global.__envStatusCache || {};
        const targetRoom = normalizeHvacEnvRoomName(roomName);
        if (!targetRoom) return [];
        const envConfigList = Array.isArray(global.__envConfigsCache) ? global.__envConfigsCache : [];
        return envConfigList
            .map(cfg => {
                const st = data[cfg.id] || {};
                const sensorRoom = getEnvSensorRoomName(cfg);
                const roomMatched = sensorRoom === targetRoom;
                const text = `${cfg?.id || ''} ${cfg?.name || ''}`.toLowerCase();
                const isContactOnly = typeof global.isContactLikeEnvSensor === 'function'
                    ? global.isContactLikeEnvSensor(cfg) && !envSensorHasThermalValue(st)
                    : false;
                const hasThermal = envSensorHasThermalValue(st);
                if (!roomMatched || isContactOnly || !hasThermal) return null;
                const ageSec = getEnvThermalAgeSec(st);
                const statusLevel = String(st?.status_level || (st?.online ? 'online' : (st?.stale ? 'stale' : 'offline'))).toLowerCase();
                const score = (st?.online ? 1000 : 0)
                    + (statusLevel === 'stale' ? 120 : 0)
                    + (Number.isFinite(ageSec) ? Math.max(0, 7200 - Math.min(ageSec, 7200)) / 10 : 0)
                    + (text.includes(targetRoom.toLowerCase()) ? 30 : 0);
                return { cfg, st, ageSec, statusLevel, score };
            })
            .filter(Boolean)
            .sort((left, right) => right.score - left.score)
            .slice(0, limit);
    }

    function renderHvacRoomEnvChips(roomName, options = {}) {
        const sensors = findRoomEnvSensors(roomName, options.limit || 2);
        if (!sensors.length) return '';
        return sensors.map(item => {
            const st = item.st || {};
            const temp = Number(st.temp);
            const hum = Number(st.hum);
            if (!Number.isFinite(temp) && !Number.isFinite(hum)) return '';
            const tempText = Number.isFinite(temp) ? `${temp.toFixed(temp % 1 === 0 ? 0 : 1)}°C` : '--°C';
            const humText = Number.isFinite(hum) ? `${hum.toFixed(hum % 1 === 0 ? 0 : 1)}%` : '--%';
            const level = String(item.statusLevel || '').toLowerCase();
            const chipClass = level === 'stale' ? 'stale' : (st.online ? 'online' : 'offline');
            const ageText = formatCompactAgeFromSec(item.ageSec);
            const title = `${item.cfg?.name || roomName || '空间温湿度'}${ageText ? ` / ${ageText}` : ''}`;
            const label = options.compact ? '室内' : '温湿';
            return `<span class="hvac-room-env-chip ${escapeHtml(chipClass)}" title="${escapeHtml(title)}"><span class="label">${escapeHtml(label)}</span><strong>${escapeHtml(tempText)}</strong><span>/ ${escapeHtml(humText)}</span>${ageText && chipClass !== 'online' ? `<em>${escapeHtml(ageText)}</em>` : ''}</span>`;
        }).filter(Boolean).join('');
    }

    function buildHvacGroups(configs, statusMap = {}) {
        const groupsMap = new Map();
        (Array.isArray(configs) ? configs : []).forEach(cfg => {
            if (!cfg || cfg.visible === false) return;
            const roomName = getHvacRoomName(cfg);
            if (!groupsMap.has(roomName)) groupsMap.set(roomName, []);
            groupsMap.get(roomName).push(cfg);
        });
        return Array.from(groupsMap.entries())
            .map(([roomName, items]) => {
                const sortedItems = items.slice().sort((left, right) => {
                    const orderDiff = getHvacSortOrder(left) - getHvacSortOrder(right);
                    if (orderDiff !== 0) return orderDiff;
                    return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN');
                });
                const stats = sortedItems.reduce((acc, cfg) => {
                    const st = statusMap[cfg.id] || {};
                    acc.total += 1;
                    if (st.online) acc.online += 1;
                    if (st.power) acc.running += 1;
                    const watt = Number(st.electric_power_w);
                    if (Number.isFinite(watt)) acc.powerW += watt;
                    return acc;
                }, { total: 0, online: 0, running: 0, powerW: 0 });
                return { roomName, items: sortedItems, stats };
            })
            .sort((left, right) => {
                const roomDiff = getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName);
                if (roomDiff !== 0) return roomDiff;
                return String(left.roomName || '').localeCompare(String(right.roomName || ''), 'zh-CN');
            });
    }

    function isDashboardHvacAttention(status = {}) {
        const errorText = String(status?.error || status?.last_error || '').trim();
        const action = String(status?.hvac_action || '').trim().toLowerCase();
        return !status?.online || !!status?.power || !!errorText || ['cooling', 'heating', 'drying', 'fan'].includes(action);
    }

    function getDashboardHvacAttentionRank(item) {
        const st = item?.status || {};
        if (!st.online) return 0;
        if (st.error || st.last_error) return 1;
        if (st.power) return 2;
        return 9;
    }

    function getDashboardHvacTotals(groups = [], context = {}) {
        const statusMap = getContext(context).statusMap || {};
        return groups.reduce((acc, group) => {
            const stats = group?.stats || {};
            acc.total += Number(stats.total || 0);
            acc.online += Number(stats.online || 0);
            acc.running += Number(stats.running || 0);
            acc.powerW += Number(stats.powerW || 0);
            (group?.items || []).forEach(cfg => {
                const st = statusMap[cfg.id] || {};
                if (!st.online) acc.offline += 1;
                if (st.error || st.last_error) acc.error += 1;
            });
            return acc;
        }, { total: 0, online: 0, running: 0, offline: 0, error: 0, powerW: 0 });
    }

    function formatHvacDashboardPower(watt) {
        const value = Number(watt);
        if (!Number.isFinite(value)) return '--';
        if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
        return `${value.toFixed(value >= 100 ? 0 : 1)} W`;
    }

    function renderDashboardHvacMetric(label, value, tone = '') {
        return `<div class="dashboard-hvac-metric ${escapeHtml(tone)}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>`;
    }

    function getHvacStateSummary(status) {
        const online = !!status?.online;
        const powerOn = !!status?.power;
        const modeText = getHvacModeText(status?.mode);
        const actionText = getHvacActionText(status?.hvac_action);
        return {
            onlineText: online ? '在线' : '离线',
            powerText: powerOn ? '运行中' : '已关闭',
            stateClass: getHvacCardStateClass(status),
            modeText,
            actionText,
        };
    }

    function renderDashboardHvacAttentionCard(item) {
        const merged = Object.assign({}, item?.cfg || {}, item?.status || {});
        const state = getHvacStateSummary(merged);
        const modeClass = getHvacModeClass(merged.mode) || getHvacActionClass(merged);
        const title = escapeHtml(merged.name || merged.id || '未命名空调');
        const roomName = getHvacRoomName(merged);
        const targetText = formatHvacTemperature(merged.target_temp);
        const actionText = merged.power
            ? (state.actionText !== '--' ? state.actionText : state.modeText)
            : state.powerText;
        const powerText = formatHvacPower(merged);
        const ageText = getHvacAgeText(merged);
        const noteParts = [
            roomName,
            ageText && ageText !== '--' ? ageText : '',
            powerText && powerText !== '--' ? powerText : '',
        ].filter(Boolean);
        const deviceId = String(merged.id || '');
        const safeDeviceId = escapeHtml(deviceId);
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('hvac.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限') : '';
        return `<div class="dashboard-hvac-device-mini ${state.stateClass}${modeClass ? ` mode-${modeClass}` : ''}">
            <div class="dashboard-hvac-device-main">
                <div class="dashboard-hvac-device-title">${title}</div>
                <div class="dashboard-hvac-device-meta">${escapeHtml(noteParts.join(' · '))}</div>
            </div>
            <div class="dashboard-hvac-device-state">
                <span class="dashboard-hvac-pill ${merged.online ? 'online' : 'offline'}">${escapeHtml(state.onlineText)}</span>
                <strong>${escapeHtml(targetText)}</strong>
                <span>${escapeHtml(actionText)}</span>
            </div>
            <button class="dashboard-hvac-power ${getHvacPowerButtonClass(merged)}${disabledClass}" ${disabledAttrs} title="${escapeHtml(merged.power ? '当前开机，点击关机' : '当前关机，点击开机')}" onclick="event.stopPropagation(); controlHvac('${safeDeviceId}', '${merged.power ? 'power_off' : 'power_on'}')">${getPowerIconHtml()}</button>
        </div>`;
    }

    function renderDashboardHvacRoomTile(group) {
        const stats = group?.stats || {};
        const roomName = group?.roomName || '未分区';
        const accent = getHvacGroupAccent(roomName);
        const offline = Math.max(0, Number(stats.total || 0) - Number(stats.online || 0));
        const roomEnvChipHtml = renderHvacRoomEnvChips(roomName, { compact: true, limit: 1 });
        const loadText = Number(stats.running || 0) > 0
            ? `${Number(stats.running || 0)} 运行`
            : `${Math.max(0, Number(stats.total || 0) - Number(stats.running || 0))} 已关`;
        return `<div class="dashboard-hvac-room-tile ${escapeHtml(getHvacGroupClass(roomName))}" style="--hvac-room-accent:${accent.accent};">
            <div class="dashboard-hvac-room-head">
                <strong>${escapeHtml(roomName)}</strong>
                <span>${escapeHtml(loadText)}</span>
            </div>
            <div class="dashboard-hvac-room-line">
                <span>${escapeHtml(`${Number(stats.online || 0)}/${Number(stats.total || 0)} 在线`)}</span>
                <span class="${offline ? 'warn' : ''}">${escapeHtml(offline ? `${offline} 离线` : '正常')}</span>
                <span>${escapeHtml(formatHvacDashboardPower(stats.powerW))}</span>
            </div>
            <div class="dashboard-hvac-room-env${roomEnvChipHtml ? '' : ' is-empty'}" data-hvac-room-env="${escapeHtml(roomName)}">${roomEnvChipHtml}</div>
        </div>`;
    }

    function renderDashboardHvacOverview(groups = [], context = {}) {
        const ctx = getContext(context);
        const statusMap = ctx.statusMap || {};
        if (!groups.length) return '<div class="hvac-empty">未配置空调设备</div>';
        const totals = getDashboardHvacTotals(groups, ctx);
        const attentionItems = groups.flatMap(group => (group?.items || []).map(cfg => ({
            cfg,
            status: statusMap[cfg.id] || {},
            roomName: group.roomName,
        }))).filter(item => isDashboardHvacAttention(item.status))
            .sort((left, right) => getDashboardHvacAttentionRank(left) - getDashboardHvacAttentionRank(right)
                || getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName)
                || getHvacSortOrder(left.cfg) - getHvacSortOrder(right.cfg));
        const visibleAttention = attentionItems.slice(0, 6);
        const moreCount = Math.max(0, attentionItems.length - visibleAttention.length);
        const attentionHtml = visibleAttention.length
            ? visibleAttention.map(renderDashboardHvacAttentionCard).join('')
            : '<div class="dashboard-hvac-quiet">全部空调处于正常关闭/待机状态</div>';
        const roomHtml = groups.map(renderDashboardHvacRoomTile).join('');
        return `<div class="dashboard-hvac-overview">
            <div class="dashboard-hvac-summary-strip">
                ${renderDashboardHvacMetric('运行', String(totals.running), totals.running ? 'running' : '')}
                ${renderDashboardHvacMetric('离线', String(totals.offline), totals.offline ? 'offline' : '')}
                ${renderDashboardHvacMetric('在线', `${totals.online}/${totals.total}`, 'online')}
                ${renderDashboardHvacMetric('当前功率', formatHvacDashboardPower(totals.powerW), 'power')}
                <button class="dashboard-hvac-entry" type="button" onclick="switchTab('hvac', '空调控制', findNavElementByView('hvac'))">详情</button>
            </div>
            <div class="dashboard-hvac-priority">
                <div class="dashboard-hvac-block-title">
                    <span>需关注</span>
                    <strong>${escapeHtml(moreCount ? `+${moreCount}` : `${attentionItems.length}`)}</strong>
                </div>
                <div class="dashboard-hvac-priority-grid">${attentionHtml}</div>
            </div>
            <div class="dashboard-hvac-room-grid">${roomHtml}</div>
        </div>`;
    }

    const api = {
        formatHvacTemperature,
        formatHvacPower,
        getHvacModeText,
        getHvacActionText,
        getHvacModeClass,
        getHvacCardStateClass,
        getHvacActionClass,
        getHvacPowerButtonClass,
        getHvacAgeText,
        getHvacRoomName,
        getHvacSortOrder,
        getHvacRoomSort,
        getHvacGroupClass,
        getHvacGroupAccent,
        normalizeHvacEnvRoomName,
        findRoomEnvSensors,
        renderHvacRoomEnvChips,
        buildHvacGroups,
        renderDashboardHvacOverview,
    };

    Object.assign(state, api);
    Object.assign(global, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.hvac-summary', {
            kind: 'dashboard-summary',
            exports: Object.keys(api),
            source: 'static/js/views/hvac-summary.js',
        });
    }
})(window);
