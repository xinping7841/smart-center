// AI_MODULE: logs_view
// AI_PURPOSE: 通用日志窗口和按模块过滤的事件日志展示。
// AI_BOUNDARY: 不写日志；只查询并渲染后端 event logs。
// AI_DATA_FLOW: /api/events/logs -> 日志列表 DOM。
// AI_RUNTIME: 首页日志窗口、灯光日志、自动化日志等场景复用。
// AI_RISK: 低到中，排序/过滤错误会影响排障效率。
// AI_SEARCH_KEYWORDS: logs, event, filter, latest first.

(function installSmartCenterLogs(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.logs = Object.assign({
        eventLogState: { offset: 0, limit: 80, total: 0 },
        automationLogCache: [],
        automationLogLoading: false,
        dashboardLogsCache: [],
    }, SmartCenter.logs || {});

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

    function apiFetchJson(url, options = {}, fallbackText = '请求失败') {
        if (typeof global.fetchJson === 'function') {
            return global.fetchJson(url, options, fallbackText);
        }
        return fetch(url, options).then(response => response.json());
    }

    function translateError(message, fallbackText = '请求失败') {
        return typeof global.translateApiError === 'function'
            ? global.translateApiError(message, fallbackText)
            : (message || fallbackText);
    }

    function notify(message, isError = false) {
        if (typeof global.showToast === 'function') global.showToast(message, isError);
    }

    function formatDateTime(value) {
        return typeof global.formatDateTimeText === 'function'
            ? global.formatDateTimeText(value)
            : (value ? String(value) : '未上报');
    }

    function maybeGarbledText(text) {
        return typeof global.looksLikeGarbledText === 'function'
            ? global.looksLikeGarbledText(text)
            : false;
    }

    function getAutomationLogLevel(log) {
        const op = String(log?.operation || '').toLowerCase();
        const status = String(log?.status || '').toLowerCase();
        if (status === 'error' || op.includes('失败') || op.includes('异常') || op.includes('missing') || op.includes('failed')) return 'error';
        if (op.includes('skip') || op.includes('skipped') || op.includes('timeout') || op.includes('停用') || op.includes('跳过')) return 'warning';
        if (op.includes('completed') || op.includes('triggered') || op.includes('启用') || op.includes('执行')) return 'success';
        return '';
    }

    function normalizeLogOperationText(log) {
        const raw = String(log?.operation || '').replace(/\[.*?\]\s*/g, '').trim();
        if (!raw) return '暂无操作记录';
        if (!maybeGarbledText(raw)) return raw;
        if (raw.includes('config saved') || raw.includes('hot reloaded')) return '配置已保存并热重载';
        const channelMatch = raw.match(/\d+/);
        const channelText = channelMatch ? `通道 ${channelMatch[0]}` : '设备';
        if (raw.includes('鍚堥椄')) return `${channelText} 合闸`;
        if (raw.includes('鏂紑')) return `${channelText} 断开`;
        if (raw.includes('鍏抽棴')) return `${channelText} 关闭`;
        if (raw.includes('寮€鍚')) return `${channelText} 开启`;
        if (raw.includes('鐏厜') || raw.includes('璋冨厜')) return channelMatch ? `灯光 ${channelText} 控制` : '灯光控制';
        if (raw.includes('鏃跺簭') || raw.includes('sequencer')) return '时序电源操作';
        if (raw.includes('system')) return '系统操作';
        if (raw.includes('閫氶亾')) return `${channelText} 操作`;
        return '设备操作记录';
    }

    function normalizeAutomationLogText(log) {
        let text = String(log?.operation || '').trim();
        if (!text) return '暂无自动化记录';
        text = text.replace(/^\[(automation|scene|自动化|场景)\]\s*/i, '');
        text = text.replace(/^triggered:\s*/i, '规则触发：');
        text = text.replace(/^start:\s*/i, '场景开始：');
        text = text.replace(/^completed:\s*/i, '场景完成：');
        text = text.replace(/^missing:\s*/i, '场景缺失：');
        text = text.replace(/^skip duplicate trigger:\s*/i, '跳过重复触发：');
        text = text.replace(/^target scene missing:\s*/i, '目标场景缺失：');
        text = text.replace(/^skipped stale schedule:\s*/i, '定时补执行过期跳过：');
        text = text.replace(/^invalid schedule time:\s*/i, '定时时间无效：');
        text = text.replace(/^rule\s*/i, '规则 ');
        return text || normalizeLogOperationText(log);
    }

    function parseLogTimeMs(log) {
        const raw = log?.time;
        if (!raw) return 0;
        const parsed = new Date(raw).getTime();
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function sortLogsNewestFirst(logs) {
        return (Array.isArray(logs) ? logs : [])
            .slice()
            .sort((a, b) => {
                const delta = parseLogTimeMs(b) - parseLogTimeMs(a);
                if (delta) return delta;
                return String(b?.time || '').localeCompare(String(a?.time || ''));
            });
    }

    function isDashboardTotalLogVisible(log) {
        const op = String(log?.operation || '').trim();
        if (!op) return false;
        if (op.includes('[Agent诊断]')) return false;
        if (/^\[proxy-monitor\]/i.test(op)) return false;
        if (op.includes('runtime_keys=') || op.includes('status_keys=')) return false;
        return (
            op.includes('[状态变化]') ||
            op.includes('[自动化]') ||
            op.includes('[场景]') ||
            op.includes('[服务器]') ||
            op.includes('[强电柜]') ||
            op.includes('[灯光]') ||
            op.includes('[时序电源]') ||
            op.includes('[空调]') ||
            op.includes('[门禁]') ||
            op.includes('[投影机]') ||
            op.includes('[幕布]') ||
            op.includes('控制') ||
            op.includes('指令') ||
            op.includes('开启') ||
            op.includes('关闭') ||
            op.includes('失败') ||
            op.includes('异常') ||
            op.includes('告警')
        );
    }

    function filterDashboardTotalLogs(logs) {
        return (Array.isArray(logs) ? logs : []).filter(isDashboardTotalLogVisible);
    }

    function buildDashboardLogSignature(logs) {
        return sortLogsNewestFirst(filterDashboardTotalLogs(logs))
            .slice(0, 40)
            .map(log => [
                String(log?.time || ''),
                String(log?.cab_idx ?? ''),
                String(log?.category || ''),
                String(log?.status || ''),
                String(log?.operation || ''),
            ].join('|'))
            .join('\n');
    }

    function renderAutomationLogs(logsPayload = null) {
        const list = document.getElementById('automation-runtime-log-list');
        if (!list) return;
        const sourceLogs = logsPayload || state.automationLogCache;
        const logs = sortLogsNewestFirst(sourceLogs).slice(0, 80);
        const summary = document.getElementById('auto-log-summary');
        if (summary) summary.textContent = logs.length ? `最近 ${logs.length} 条自动化和场景联动记录` : '暂无自动化执行记录';
        if (!logs.length) {
            list.innerHTML = '<div class="auto-log-empty">暂无自动化运行记录。规则触发、场景开始/完成、失败会显示在这里。</div>';
            return;
        }
        list.innerHTML = logs.map(log => {
            const cls = getAutomationLogLevel(log);
            const message = html(normalizeAutomationLogText(log));
            const rawMessage = html(String(log?.operation || ''));
            return `<div class="auto-log-item ${cls}" title="${rawMessage}">
                <div class="auto-log-time">${html(formatDateTime(log?.time || ''))}</div>
                <div class="auto-log-message">${message}</div>
            </div>`;
        }).join('');
    }

    async function loadAutomationLogs(showError = false) {
        if (state.automationLogLoading) return;
        state.automationLogLoading = true;
        try {
            const data = await apiFetchJson('/api/automation/logs?limit=80', {}, '自动化日志读取失败');
            state.automationLogCache = Array.isArray(data.items) ? data.items : [];
            renderAutomationLogs();
        } catch (err) {
            if (showError) notify(err.message || '自动化日志读取失败', true);
            console.error('自动化日志读取失败', err);
        } finally {
            state.automationLogLoading = false;
        }
    }

    function getPowerLogSourceMeta(log) {
        const opRaw = String(log?.operation || '').toLowerCase();
        const sourceRaw = String(log?.data_source || '').toLowerCase();
        const detailObj = (log && typeof log.detail === 'object') ? log.detail : {};
        const hasAutoHint = opRaw.includes('自动化') || opRaw.includes('automation') || opRaw.includes('[scene]') || opRaw.includes('[auto]');
        if (hasAutoHint || (log && log.category === 'automation')) {
            return { cls: 'auto', label: '自动化触发' };
        }
        if (sourceRaw.includes('remote') || sourceRaw.includes('gateway') || String(detailObj.gateway || '').toLowerCase() === 'remote') {
            return { cls: 'remote', label: '外部网关' };
        }
        return { cls: 'local', label: '本机操作' };
    }

    function renderPowerLogSourceTag(log, classPrefix = 'source-tag') {
        const meta = getPowerLogSourceMeta(log);
        return `<span class="${classPrefix} ${meta.cls}" title="${html(meta.label)}">${html(meta.label)}</span>`;
    }

    function renderPowerDetailLogs(cabId, logs) {
        const logList = document.getElementById(`logs_${cabId}`);
        if (!logList) return;
        const items = Array.isArray(logs) ? logs : [];
        if (!items.length) {
            logList.innerHTML = '<div style="color:var(--text-sub); padding:10px 0;">暂无操作日志</div>';
            return;
        }
        const rendered = items.map(log => {
            const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
            const message = html(normalizeLogOperationText(log));
            return `<div class="log-item"><span class="time">[${timeText}]</span>${renderPowerLogSourceTag(log)}<span class="msg">${message}</span></div>`;
        }).join('');
        if (logList.innerHTML !== rendered) logList.innerHTML = rendered;
    }

    function getEventFilterValue(id) {
        const el = document.getElementById(id);
        return el ? String(el.value || '').trim() : '';
    }

    function formatEventTime(value) {
        if (!value) return '--';
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return value;
        return d.toLocaleString('zh-CN', { hour12: false });
    }

    function renderEventLogs(payload) {
        const eventLogState = state.eventLogState;
        const tbody = document.getElementById('event-log-tbody');
        const summary = document.getElementById('event-log-summary');
        const pageText = document.getElementById('event-page-text');
        const prevBtn = document.getElementById('event-prev-btn');
        const nextBtn = document.getElementById('event-next-btn');
        if (!tbody) return;
        const items = Array.isArray(payload?.items) ? payload.items : [];
        eventLogState.total = Number(payload?.total || 0);
        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-sub);padding:24px;">暂无事件日志</td></tr>';
        } else {
            tbody.innerHTML = items.map(item => {
                const category = html(item.category || 'system');
                const result = html(item.result || '--');
                const source = html(item.source_label || item.source || '--');
                const device = html(item.device_name || item.device_id || item.entity_id || '--');
                const detailParts = [];
                if (item.action) detailParts.push(`动作 ${html(item.action)}`);
                if (item.channel) detailParts.push(`通道 ${html(item.channel)}`);
                if (item.old_state || item.new_state) detailParts.push(`${html(item.old_state || '--')} -> ${html(item.new_state || '--')}`);
                if (item.correlation_id) detailParts.push(`关联 ${html(item.correlation_id)}`);
                return `<tr>
                    <td>${html(formatEventTime(item.time))}</td>
                    <td><span class="event-chip ${category}">${html(item.category_label || item.category || '--')}</span></td>
                    <td>${html(item.event_type_label || item.event_type || '--')}</td>
                    <td><span class="event-chip ${item.result === 'external_detected' ? 'external' : (item.confidence === 'confirmed' ? 'confirmed' : '')}">${source} / ${result}</span></td>
                    <td>${device}<div class="event-detail">${html(item.entity_id || item.device_id || '')}</div></td>
                    <td><div class="event-message">${html(item.message || '--')}</div><div class="event-detail">${detailParts.join(' / ')}</div></td>
                </tr>`;
            }).join('');
        }
        const pageNo = Math.floor(eventLogState.offset / eventLogState.limit) + 1;
        const pageCount = Math.max(1, Math.ceil(eventLogState.total / eventLogState.limit));
        if (summary) summary.textContent = `共 ${eventLogState.total} 条，当前显示 ${items.length} 条`;
        if (pageText) pageText.textContent = `第 ${pageNo} / ${pageCount} 页`;
        if (prevBtn) prevBtn.disabled = eventLogState.offset <= 0;
        if (nextBtn) nextBtn.disabled = eventLogState.offset + eventLogState.limit >= eventLogState.total;
    }

    function refreshEventLogs(reset = false) {
        const eventLogState = state.eventLogState;
        if (reset) eventLogState.offset = 0;
        const params = new URLSearchParams();
        params.set('limit', String(eventLogState.limit));
        params.set('offset', String(eventLogState.offset));
        const filters = {
            category: getEventFilterValue('event-filter-category'),
            event_type: getEventFilterValue('event-filter-type'),
            result: getEventFilterValue('event-filter-result'),
            hours: getEventFilterValue('event-filter-hours'),
            q: getEventFilterValue('event-filter-q'),
        };
        Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
        return apiFetchJson(`/api/logs/events?${params.toString()}`, {}, '事件日志读取失败')
            .then(renderEventLogs)
            .catch(err => {
                const tbody = document.getElementById('event-log-tbody');
                if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="color:#fca5a5;padding:18px;">${html(translateError(err?.message, '事件日志读取失败'))}</td></tr>`;
            });
    }

    function pageEventLogs(delta) {
        const eventLogState = state.eventLogState;
        eventLogState.offset = Math.max(0, eventLogState.offset + delta * eventLogState.limit);
        refreshEventLogs(false);
    }

    function renderDashboardLogs(logs) {
        const logList = document.getElementById('dashboard-logs');
        if (!logList) return;
        const visibleLogs = sortLogsNewestFirst(filterDashboardTotalLogs(logs));
        if (!visibleLogs.length) {
            logList.innerHTML = '<div style="color:var(--text-sub); text-align:center; padding:24px 0;">暂无操作日志</div>';
            return;
        }
        const rendered = visibleLogs.slice(0, 40).map(log => {
            const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
            const message = html(normalizeLogOperationText(log));
            return `<div class="log-item"><span class="time">[${timeText}]</span><span class="msg">${message}</span></div>`;
        }).join('');
        if (logList.innerHTML !== rendered) {
            logList.innerHTML = rendered;
            logList.scrollTop = 0;
        }
    }

    function updateDashboardLogs() {
        return apiFetchJson('/api/logs', {}, '首页系统日志读取失败')
            .then(logs => {
                const nextLogs = Array.isArray(logs) ? logs : [];
                const changed = buildDashboardLogSignature(nextLogs) !== buildDashboardLogSignature(state.dashboardLogsCache || []);
                state.dashboardLogsCache = nextLogs;
                if (changed) renderDashboardLogs(state.dashboardLogsCache);
            })
            .catch(err => console.error('首页系统日志更新失败', err));
    }

    const api = {
        getAutomationLogLevel,
        normalizeAutomationLogText,
        renderAutomationLogs,
        loadAutomationLogs,
        normalizeLogOperationText,
        isDashboardTotalLogVisible,
        filterDashboardTotalLogs,
        parseLogTimeMs,
        sortLogsNewestFirst,
        buildDashboardLogSignature,
        getPowerLogSourceMeta,
        renderPowerLogSourceTag,
        renderPowerDetailLogs,
        getEventFilterValue,
        formatEventTime,
        renderEventLogs,
        refreshEventLogs,
        pageEventLogs,
        renderDashboardLogs,
        updateDashboardLogs,
    };

    SmartCenter.logs = Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.logs', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/logs.js',
        });
    }

    Object.assign(global, api);
})(window);
