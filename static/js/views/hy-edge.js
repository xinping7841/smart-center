(function installSmartCenterHyEdge(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.hyEdge = Object.assign({
        statusCache: {},
    }, SmartCenter.hyEdge || {});

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

    function getHyEdgeStatusCache() {
        if (state.statusCache && typeof state.statusCache === 'object') return state.statusCache;
        return (global.hyEdgeStatusCache && typeof global.hyEdgeStatusCache === 'object') ? global.hyEdgeStatusCache : {};
    }

    function setHyEdgeStatusCache(data) {
        state.statusCache = (data && typeof data === 'object') ? data : {};
        global.hyEdgeStatusCache = state.statusCache;
        return state.statusCache;
    }

    function fetchStatus() {
        if (typeof global.fetchJson === 'function') {
            return global.fetchJson('/api/hy-edge/status', {}, 'HY 异地状态读取失败');
        }
        return fetch('/api/hy-edge/status').then(response => response.json());
    }

    function translateError(message, fallbackText = 'HY 异地状态读取失败') {
        return typeof global.translateApiError === 'function'
            ? global.translateApiError(message, fallbackText)
            : (message || fallbackText);
    }

    function renderHyEdgeCards() {
        const summaryEl = document.getElementById('dashboard-hy-edge-summary');
        const grid = document.getElementById('dashboard-hy-edge-grid');
        if (!summaryEl || !grid) return;
        const payload = getHyEdgeStatusCache();
        const summary = payload.summary || {};
        const cards = Array.isArray(payload.cards) ? payload.cards : [];
        const online = payload.online !== false && payload.enabled !== false && !payload.error;
        const stateChip = online
            ? '<span class="ups-chip online">边缘在线</span>'
            : '<span class="ups-chip error">边缘离线</span>';
        summaryEl.innerHTML = `
            ${stateChip}
            <span class="ups-chip">在线 <strong>${html(String(summary.online_count ?? 0))}</strong> / ${html(String(summary.card_total ?? 0))}</span>
            <span class="ups-chip ${Number(summary.alert_count || 0) > 0 ? 'warning' : ''}">告警 <strong>${html(String(summary.alert_count ?? 0))}</strong></span>
            <span class="ups-chip">响应 ${html(String(summary.response_time_ms ?? '--'))} ms</span>
        `;
        if (payload.enabled === false) {
            grid.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">HY 异地机房监控已停用</div>';
            return;
        }
        if (!online && !cards.length) {
            grid.innerHTML = `<div style="color:var(--danger); grid-column:1/-1; text-align:center; padding:20px;">HY 边缘状态读取失败：${html(payload.error || '未知错误')}</div>`;
            return;
        }
        grid.innerHTML = cards.map(card => {
            const hasAlerts = Array.isArray(card.alerts) && card.alerts.length > 0;
            const cardClass = `${card.online ? '' : 'offline'} ${hasAlerts ? 'warning' : ''}`.trim();
            const chips = (card.chips || []).map(chip => `<span class="ups-chip ${html(chip.tone || '')}">${html(chip.text || '--')}</span>`).join('');
            const metrics = (card.metrics || []).map(metric => `
                <div class="hy-edge-metric ${html(metric.level || '')}">
                    <div class="label">${html(metric.label || '--')}</div>
                    <div class="value">${html(metric.value || '--')}</div>
                </div>
            `).join('');
            const alerts = hasAlerts
                ? `<div class="hy-edge-alerts">${card.alerts.map(item => `<span class="ups-chip warning">${html(item)}</span>`).join('')}</div>`
                : '';
            return `<div class="hy-edge-card ${html(cardClass)}">
                <div class="hy-edge-head">
                    <div>
                        <div class="hy-edge-title">${html(card.title || '--')}</div>
                        <div class="hy-edge-subtitle">${html(card.subtitle || '--')}</div>
                    </div>
                    <div class="dashboard-mini-chip-row">${chips}</div>
                </div>
                <div class="hy-edge-metric-grid">${metrics}</div>
                ${alerts}
                <div class="hy-edge-note">${html(card.note || '')}</div>
            </div>`;
        }).join('');
    }

    function updateHyEdgeStatus() {
        return fetchStatus()
            .then(data => {
                setHyEdgeStatusCache(data || {});
                renderHyEdgeCards();
            })
            .catch(err => {
                console.error('HY 异地状态更新失败', err);
                setHyEdgeStatusCache({
                    enabled: true,
                    online: false,
                    error: translateError(err?.message, 'HY 异地状态读取失败'),
                    summary: { online_count: 0, card_total: 0, alert_count: 0, response_time_ms: null, high_age_text: '--', low_age_text: '--' },
                    cards: [],
                });
                renderHyEdgeCards();
            });
    }

    const api = {
        getHyEdgeStatusCache,
        setHyEdgeStatusCache,
        renderHyEdgeCards,
        updateHyEdgeStatus,
    };

    SmartCenter.hyEdge = Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.hy-edge', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/hy-edge.js',
        });
    }

    global.hyEdgeStatusCache = state.statusCache;
    Object.assign(global, api);
})(window);
