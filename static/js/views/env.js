// AI_MODULE: environment_view
// AI_PURPOSE: 环境传感器、温湿度、光照、门窗/亮暗和电池状态展示。
// AI_BOUNDARY: 不控制空调；环境数据只作为显示和自动化条件。
// AI_DATA_FLOW: /api/env/status -> 环境卡片、顶部摘要和其他模块上下文。
// AI_RUNTIME: 首页、环境页和 HVAC 卡片会复用。
// AI_RISK: 中，离线/stale 错误会影响自动化判断。
// AI_SEARCH_KEYWORDS: environment, temperature, humidity, lux, contact, battery.

(function installSmartCenterEnv(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function html(value) {
        return typeof global.escapeHtml === 'function'
            ? global.escapeHtml(value)
            : String(value ?? '').replace(/[&<>"']/g, ch => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch]));
    }

    function getEnvConfigs() {
        return Array.isArray(global.__envConfigsCache) ? global.__envConfigsCache : [];
    }

    function fetchEnvStatus(options = {}) {
        const query = options.history || options.trend
            ? `?${new URLSearchParams({
                ...(options.history ? { history: '1' } : {}),
                ...(options.trend ? { trend: '1' } : {}),
            }).toString()}`
            : '';
        const url = `/api/env/status${query}`;
        if (typeof global.fetchJson === 'function') {
            return global.fetchJson(url, {}, '环境状态读取失败');
        }
        return fetch(url).then(response => response.json());
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function updateTopEnvSummary(sensor) {
        const topSummary = document.getElementById('top-env-summary');
        if (sensor && sensor.st) {
            const st = sensor.st;
            setText('top-env-temp', st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--');
            setText('top-env-hum', st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--');
            setText('top-env-lux', st.lux !== null && st.lux !== undefined ? `${st.lux}Lux` : '--');
            if (topSummary) topSummary.style.opacity = st.online ? '1' : '0.75';
            return;
        }
        setText('top-env-temp', '--');
        setText('top-env-hum', '--');
        setText('top-env-lux', '--');
        if (topSummary) topSummary.style.opacity = '0.75';
    }

    function renderEnvSensorCards(data = {}) {
        const configs = getEnvConfigs();
        if (!Object.keys(data || {}).length) {
            return '<div style="color:var(--text-sub); grid-column:1/-1;">暂未配置传感器。</div>';
        }
        return configs.map(cfg => {
            const st = data[cfg.id] || { online: false };
            const features = typeof global.getEnvFeatures === 'function' ? global.getEnvFeatures(cfg) : Object.assign({}, cfg?.features || {});
            const statusLevel = String(st.status_level || (st.online ? 'online' : (st.stale ? 'stale' : 'offline'))).toLowerCase();
            const color = statusLevel === 'online' ? 'var(--success)' : (statusLevel === 'stale' ? 'var(--warning)' : '#475569');
            const metricMap = typeof global.buildEnvMetricMap === 'function' ? global.buildEnvMetricMap(features, st, cfg) : {};
            const primaryMetric = typeof global.getEnvPrimaryMetricDef === 'function'
                ? global.getEnvPrimaryMetricDef(cfg, st, features, metricMap)
                : { key: 'auto', label: '环境监测', mainLabel: '核心指标：环境监测', displayText: st.online ? '在线' : '--', color: st.online ? 'var(--success)' : 'var(--text-sub)' };
            const metricDefs = typeof global.buildEnvStatusMetricDefs === 'function' ? global.buildEnvStatusMetricDefs(features, st, cfg) : [];
            const deviceInfo = typeof global.buildEnvDeviceInfo === 'function' ? global.buildEnvDeviceInfo(cfg, st) : { rows: [], note: '' };
            let metricsHtml = '';
            metricDefs.forEach(item => {
                if (item.key === primaryMetric.key && metricDefs.length > 1) return;
                const valueText = (st.online || st.stale || statusLevel === 'stale') ? item.displayText : '--';
                metricsHtml += `<div class="env-card-metric ${item.stale ? 'stale' : ''}"><div class="label">${html(item.label)}</div><div class="val" style="color:${item.color};">${html(valueText)}</div></div>`;
            });
            if (!metricsHtml) metricsHtml = '<div style="color:var(--text-sub);">未启用扩展指标</div>';
            const deviceInfoHtml = (deviceInfo.rows.length || deviceInfo.note)
                ? `<div class="env-card-device-info">
                        ${deviceInfo.rows.length ? `<div class="env-card-device-grid">${deviceInfo.rows.map(item => `<div class="env-card-device-item"><div class="label">${html(item.label)}</div><div class="value">${html(item.value)}</div></div>`).join('')}</div>` : ''}
                        ${deviceInfo.note ? `<div class="env-card-note">${html(deviceInfo.note)}</div>` : ''}
                    </div>`
                : '';
            const onlineText = st.status_label || (st.online ? '在线' : (st.stale ? '陈旧' : '离线'));
            const primaryText = (st.online || st.stale || statusLevel === 'stale') ? primaryMetric.displayText : '--';
            return `<div class="env-card env-card-compact" style="border-top: 4px solid ${color};">
                <div class="env-card-head">
                    <div class="env-card-name" title="${html(cfg.name || cfg.id || '')}">${html(cfg.name || cfg.id || '环境传感器')}</div>
                    <span class="env-card-status ${html(statusLevel)}">${html(onlineText)}</span>
                </div>
                <div class="env-card-primary">
                    <div class="label">${html(primaryMetric.mainLabel || primaryMetric.label || '核心指标')}</div>
                    <div class="val" style="color:${primaryMetric.color || 'var(--warning)'}">${html(primaryText)}</div>
                </div>
                <div class="env-card-metrics">${metricsHtml}</div>
                ${deviceInfoHtml}
            </div>`;
        }).join('');
    }

    function updateEnvData(options = {}) {
        const activeView = typeof global.getActiveViewId === 'function' ? global.getActiveViewId() : '';
        const requestOptions = Object.assign({
            history: activeView === 'env',
            trend: activeView === 'env',
        }, options || {});
        return fetchEnvStatus(requestOptions)
            .then(data => {
                const payload = data || {};
                global.__envStatusCache = payload;
                if (typeof global.updateHvacRoomEnvSlots === 'function') global.updateHvacRoomEnvSlots();
                const screenEnvColumn = document.getElementById('screen-env-column');
                const screenUpsColumn = document.getElementById('screen-ups-column');
                const screenAutomationColumn = document.getElementById('screen-automation-column');
                if (screenEnvColumn && typeof global.buildScreenEnvCards === 'function') screenEnvColumn.innerHTML = global.buildScreenEnvCards();
                if (screenUpsColumn && typeof global.buildScreenUpsCards === 'function') screenUpsColumn.innerHTML = global.buildScreenUpsCards();
                if (screenAutomationColumn && typeof global.buildScreenAutomationCards === 'function') screenAutomationColumn.innerHTML = global.buildScreenAutomationCards();
                const sensor = typeof global.pickDashboardEnvSensor === 'function' ? global.pickDashboardEnvSensor(payload) : null;
                updateTopEnvSummary(sensor);
                if (typeof global.updateDashboardDoorStatusFromEnv === 'function') global.updateDashboardDoorStatusFromEnv(payload);
                if (typeof global.renderOutdoorAutomationDashboardCard === 'function') global.renderOutdoorAutomationDashboardCard();
                const container = document.getElementById('env-grid-container');
                if (container) container.innerHTML = renderEnvSensorCards(payload);
            })
            .catch(err => console.error('环境数据更新失败', err));
    }

    const api = {
        updateEnvData,
        fetchEnvStatus,
        renderEnvSensorCards,
        updateTopEnvSummary,
    };

    SmartCenter.env = Object.assign({}, SmartCenter.env || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('env', {
            kind: 'view',
            view: 'env',
            exports: Object.keys(api),
            source: 'static/js/views/env.js',
        });
    }

    Object.assign(global, api);
})(window);
