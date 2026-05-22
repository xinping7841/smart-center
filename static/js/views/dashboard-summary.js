(function installSmartCenterDashboardSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function normalizeDashboardSummaryPayload(payload) {
        return payload && typeof payload === 'object' ? payload : { counts: {}, modules: {} };
    }

    function renderDashboardFooterStatus(payload = {}, derived = {}) {
        const counts = (payload && payload.counts) || {};
        const autoErrors = Number(document.getElementById('dash-auto-errors')?.textContent || 0);
        const critical = Number(derived.snmpCritical || 0) + autoErrors;
        const warning = Number(derived.snmpWarning || 0);
        const groups = ['power', 'light', 'sequencer', 'server'];
        let online = 0;
        let total = 0;
        groups.forEach(key => {
            const item = counts[key] || {};
            online += Number(item.online || 0);
            total += Number(item.total || 0);
        });
        online += Number(derived.snmpOnline || 0);
        total += Number(derived.snmpTotal || 0);
        const offline = Math.max(0, total - online);
        const stability = total > 0 ? `${Math.max(0, Math.min(99.9, (online / total) * 100)).toFixed(1)}%` : '--';
        setText('dashboard-footer-critical', String(critical + warning));
        setText('dashboard-footer-warning', String(warning));
        setText('dashboard-footer-offline', String(offline));
        setText('dashboard-footer-stability', stability);
    }

    function renderDashboardEnvSummary(envModule = {}, context = {}) {
        const devices = Array.isArray(envModule.devices) ? envModule.devices : [];
        if (!devices.length) return;
        const envMap = {};
        devices.forEach(item => {
            if (item && item.id) envMap[item.id] = item;
        });
        const picker = typeof context.pickDashboardEnvSensor === 'function'
            ? context.pickDashboardEnvSensor
            : global.pickDashboardEnvSensor;
        if (typeof picker !== 'function') return;
        const picked = picker(envMap);
        const topSummary = document.getElementById('top-env-summary');
        if (picked && picked.st) {
            const st = picked.st || {};
            setText('top-env-temp', st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--');
            setText('top-env-hum', st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--');
            setText('top-env-lux', st.lux !== null && st.lux !== undefined ? `${st.lux}Lux` : '--');
            if (topSummary) topSummary.style.opacity = picked.st.online ? '1' : '0.75';
        }
    }

    function renderDashboardSummaryTopStats(payload, context = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const power = counts.power || {};
        const light = counts.light || {};
        const sequencer = counts.sequencer || {};
        const server = counts.server || {};
        const snmp = counts.snmp || {};
        const nvr = counts.nvr || {};
        const networkDevices = [
            ...(((modules.snmp || {}).devices) || []),
            ...(((modules.nvr || {}).devices) || []),
        ];
        const proxy = modules.proxy || {};
        setText('dash-power-online', String(power.online ?? 0));
        setText('dash-light-online', String(light.online ?? 0));
        setText('dash-sequencer-online', String(sequencer.online ?? 0));
        setText('dash-sequencer-total', String(sequencer.total ?? 0));
        setText('dash-server-online', String(server.online ?? 0));
        setText('dash-server-total', String(server.total ?? 0));
        const snmpOnline = Number(snmp.online || 0) + Number(nvr.online || 0);
        const snmpTotal = Number(snmp.total || 0) + Number(nvr.total || 0);
        const snmpCritical = networkDevices.filter(item => {
            const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
            return risk === 'critical' || risk === 'error';
        }).length;
        const snmpWarning = networkDevices.filter(item => {
            const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
            return risk === 'warning' || risk === 'stale';
        }).length;
        setText('dash-snmp-online', String(snmpOnline));
        setText('dash-snmp-total', String(snmpTotal));
        setText('dash-snmp-critical', String(snmpCritical));
        setText('dash-snmp-warning', String(snmpWarning));
        setText('dash-snmp-alert', String(snmpCritical + snmpWarning));

        const renderProxy = typeof context.renderDashboardProxySummary === 'function'
            ? context.renderDashboardProxySummary
            : global.renderDashboardProxySummary;
        if (typeof renderProxy === 'function') renderProxy(proxy);

        renderDashboardEnvSummary(modules.env || {}, context);
        renderDashboardFooterStatus(data, { snmpCritical, snmpWarning, snmpOnline, snmpTotal });
    }

    const api = {
        normalizeDashboardSummaryPayload,
        renderDashboardSummaryTopStats,
        renderDashboardFooterStatus,
        renderDashboardEnvSummary,
    };

    SmartCenter.dashboardSummary = Object.assign({}, SmartCenter.dashboardSummary || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('dashboard-summary', {
            kind: 'view-helper',
            view: 'dashboard',
            exports: Object.keys(api),
            source: 'static/js/views/dashboard-summary.js',
        });
    }

    Object.assign(global, api);
})(window);
