(function installSmartCenterUps(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.ups = Object.assign({
        configs: [],
        statusCache: {},
    }, SmartCenter.ups || {});

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

    function getUpsConfigs() {
        if (Array.isArray(state.configs) && state.configs.length) return state.configs;
        return Array.isArray(global.upsConfigs) ? global.upsConfigs : [];
    }

    function setUpsConfigs(configs) {
        state.configs = Array.isArray(configs) ? configs : [];
        global.upsConfigs = state.configs;
        return state.configs;
    }

    function getUpsStatusCache() {
        if (state.statusCache && typeof state.statusCache === 'object') return state.statusCache;
        return (global.upsStatusCache && typeof global.upsStatusCache === 'object') ? global.upsStatusCache : {};
    }

    function setUpsStatusCache(data) {
        state.statusCache = (data && typeof data === 'object') ? data : {};
        global.upsStatusCache = state.statusCache;
        return state.statusCache;
    }

    function getStatusMeta(status, options = {}) {
        if (typeof global.getDeviceStatusMeta === 'function') {
            return global.getDeviceStatusMeta(status, options);
        }
        const online = !!(status && (status.online || status.status === 'online'));
        return {
            level: online ? 'online' : 'offline',
            chipClass: online ? 'online' : 'error',
            text: online ? (options.onlineText || '在线') : (options.offlineText || '离线'),
            note: online ? '状态正常' : '设备离线',
            isOnlineLike: online,
        };
    }

    function getStateClass(statusMeta) {
        return typeof global.getCardStateClass === 'function'
            ? global.getCardStateClass(statusMeta)
            : (statusMeta?.isOnlineLike ? '' : 'offline');
    }

    function fetchUpsStatus() {
        if (typeof global.fetchJson === 'function') {
            return global.fetchJson('/api/ups/status', {}, 'UPS 状态读取失败');
        }
        return fetch('/api/ups/status').then(response => response.json());
    }

    function postUpsControl(payload) {
        if (typeof global.postJsonLoose === 'function') {
            return global.postJsonLoose('/api/ups/control', payload, 'UPS 指令下发失败');
        }
        return fetch('/api/ups/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(response => response.json());
    }

    function notify(message, isError = false) {
        if (typeof global.showToast === 'function') global.showToast(message, isError);
    }

    function ensureControlPermission() {
        if (typeof global.ensurePermission === 'function') {
            return global.ensurePermission('ups.control', '操作 UPS');
        }
        return true;
    }

    function permissionClass() {
        return typeof global.getPermissionDisabledClass === 'function'
            ? global.getPermissionDisabledClass('ups.control')
            : '';
    }

    function permissionAttrs() {
        return typeof global.getPermissionDisabledAttrs === 'function'
            ? global.getPermissionDisabledAttrs('ups.control', '当前账号无 UPS 控制权限')
            : '';
    }

    function translateError(message, fallbackText = 'UPS 指令下发失败') {
        return typeof global.translateApiError === 'function'
            ? global.translateApiError(message, fallbackText)
            : (message || fallbackText);
    }

    function getActiveViewId() {
        return typeof global.getActiveViewId === 'function' ? global.getActiveViewId() : '';
    }

    function getUpsCompactAlarmMeta(status = {}) {
        const faultLabels = Array.isArray(status.fault_labels) ? status.fault_labels.filter(Boolean) : [];
        const warningLabels = Array.isArray(status.warning_labels) ? status.warning_labels.filter(Boolean) : [];
        const rawAlerts = Array.isArray(status.alerts) ? status.alerts.filter(Boolean) : [];
        const benignAlerts = rawAlerts.filter(item => /蜂鸣|buzzer|beeper|beep/i.test(String(item || '')));
        const riskAlerts = rawAlerts.filter(item => !benignAlerts.includes(item));
        const riskItems = [
            ...faultLabels,
            ...warningLabels,
            ...riskAlerts,
            status.is_fault ? 'UPS 故障' : '',
            status.mains_abnormal ? '市电异常' : '',
            status.is_battery_low ? '电池偏低' : '',
            status.is_bypass ? '旁路供电' : '',
            status.last_error || status.error || '',
        ].filter(Boolean);
        if (riskItems.length) {
            return { hasRisk: true, cls: 'warning', label: '告警', title: riskItems.slice(0, 4).join('、') };
        }
        if (benignAlerts.length) {
            return { hasRisk: false, cls: '', label: '提示', title: benignAlerts.slice(0, 4).join('、') };
        }
        return { hasRisk: false, cls: 'online', label: '无告警', title: '当前无故障/告警' };
    }

    function renderDashboardUpsCompact() {
        const container = document.getElementById('dashboard-ups-compact-grid');
        if (!container) return;
        const devices = getUpsConfigs().filter(cfg => cfg.visible !== false);
        if (!devices.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置 UPS</div>';
            return;
        }
        const statusCache = getUpsStatusCache();
        container.classList.add('home-status-list');
        container.innerHTML = devices.map(cfg => {
            const status = statusCache[cfg.id] || {};
            const statusMeta = getStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const alarmMeta = getUpsCompactAlarmMeta(status);
            const inputText = status.input_voltage !== null && status.input_voltage !== undefined ? `${status.input_voltage}V` : '--';
            const outputText = status.output_voltage !== null && status.output_voltage !== undefined ? `${status.output_voltage}V` : '--';
            const modeText = status.supply_state || status.system_mode || (status.is_bypass ? '旁路' : '市电');
            return `<div class="home-status-row home-ups-row ${online ? (alarmMeta.hasRisk ? 'warning' : '') : 'offline'}">
                <div class="home-row-main">
                    <div class="home-row-title-line"><strong>${html(cfg.name || cfg.id)}</strong><span class="home-mini-pill ${statusMeta.chipClass}">${html(statusMeta.text)}</span><span class="home-mini-pill ${alarmMeta.cls}" title="${html(alarmMeta.title)}">${html(alarmMeta.label)}</span></div>
                    <span>${html(modeText)} · ${html(inputText)} / ${html(outputText)}</span>
                </div>
                <div class="home-row-side home-ups-metrics ${alarmMeta.hasRisk ? 'warn' : (online ? 'ok' : 'bad')}">${status.battery_capacity_percent ?? '--'}% 电池<br>${status.load_percent ?? '--'}% 负载</div>
            </div>`;
        }).join('');
    }

    function renderUpsCard(cfg, status) {
        const statusMeta = getStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
        const modeText = status.system_mode || '--';
        const supplyStateText = status.supply_state || (status.is_bypass ? '旁路供电' : (status.mains_abnormal ? '电池供电' : '市电供电'));
        const fmt = (value, digits = 1, suffix = '') => {
            const num = Number(value);
            return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : '--';
        };
        const fmtAuto = (value, suffix = '') => {
            const num = Number(value);
            if (!Number.isFinite(num)) return '--';
            const absVal = Math.abs(num);
            if (absVal >= 1000) return `${num.toFixed(0)}${suffix}`;
            if (absVal >= 100) return `${num.toFixed(1)}${suffix}`;
            return `${num.toFixed(2)}${suffix}`;
        };
        const batteryText = fmt(status.battery_capacity_percent, 1, '%');
        const backupText = Number.isFinite(Number(status.backup_time_seconds)) ? `${Math.max(0, Math.round(Number(status.backup_time_seconds)))}s` : '--';
        const outputFreqText = fmt(status.output_frequency, 1, ' Hz');
        const mainsText = status.mains_abnormal ? '市电异常' : '市电正常';
        const batteryStateText = status.is_battery_low ? '电池偏低' : '电池正常';
        const reportedVoltageKind = status.output_reported_voltage_kind || status.output_voltage_display_mode || '--';
        const inputPhaseText = [status.input_voltage_r, status.input_voltage_s, status.input_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
            ? `${fmt(status.input_voltage_r, 1)} / ${fmt(status.input_voltage_s, 1)} / ${fmt(status.input_voltage_t, 1)} V`
            : '--';
        const outputPhaseText = [status.output_voltage_r, status.output_voltage_s, status.output_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
            ? `${fmt(status.output_voltage_r, 1)} / ${fmt(status.output_voltage_s, 1)} / ${fmt(status.output_voltage_t, 1)} V`
            : '--';
        const derivedPhaseText = [status.output_phase_voltage_r, status.output_phase_voltage_s, status.output_phase_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
            ? `${fmt(status.output_phase_voltage_r, 1)} / ${fmt(status.output_phase_voltage_s, 1)} / ${fmt(status.output_phase_voltage_t, 1)} V`
            : '--';
        const derivedLineText = [status.output_line_voltage_r, status.output_line_voltage_s, status.output_line_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
            ? `${fmt(status.output_line_voltage_r, 1)} / ${fmt(status.output_line_voltage_s, 1)} / ${fmt(status.output_line_voltage_t, 1)} V`
            : '--';
        const outputCurrentText = [status.output_current_r, status.output_current_s, status.output_current_t].filter(v => v !== null && v !== undefined && v !== '').length
            ? `${fmt(status.output_current_r, 1)} / ${fmt(status.output_current_s, 1)} / ${fmt(status.output_current_t, 1)} A`
            : '--';
        const faultCount = Array.isArray(status.fault_labels) ? status.fault_labels.length : 0;
        const warningCount = Array.isArray(status.warning_labels) ? status.warning_labels.length : 0;
        const alerts = Array.isArray(status.alerts) ? status.alerts : [];
        const queryWarnings = Array.isArray(status.query_warnings) ? status.query_warnings : [];
        const protocolSupport = status.protocol_support || {};
        const fieldCounts = status.field_counts || {};
        const rawPreview = status.raw_preview || {};
        const pollDiag = status.poll_diagnostics || {};
        const qualityScore = Number.isFinite(Number(status.data_quality_score))
            ? Number(status.data_quality_score)
            : Number(pollDiag.quality?.score);
        const qualityText = status.data_quality_text || pollDiag.quality?.text || '--';
        const qualityDetails = Array.isArray(status.data_quality_details)
            ? status.data_quality_details
            : (Array.isArray(pollDiag.quality?.details) ? pollDiag.quality.details : []);
        const linkHint = pollDiag.transport_hint || '--';
        const lastSuccessAge = Number.isFinite(Number(pollDiag.last_success_age_sec))
            ? `${Math.round(Number(pollDiag.last_success_age_sec))}s`
            : '--';
        const costMs = Number.isFinite(Number(pollDiag.collected_cost_ms))
            ? `${Math.round(Number(pollDiag.collected_cost_ms))} ms`
            : '--';
        const alertHtml = alerts.length
            ? alerts.slice(0, 6).map(item => `<span class="ups-alert-chip ${String(item).includes('故障') ? 'error' : 'warning'}">${html(item)}</span>`).join('')
            : '<span class="ups-alert-chip warning" style="color:#bbf7d0;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.34);">当前无故障/告警</span>';
        const noteClass = status.last_error || status.error ? 'error' : (queryWarnings.length || statusMeta.level === 'stale' ? 'warn' : '');
        return `<div class="ups-card ${getStateClass(statusMeta)}">
            <div class="ups-head">
                <div>
                    <div class="card-head-kicker">UPS Status</div>
                    <div class="ups-title">${html(cfg.name || cfg.id)}</div>
                    <div class="ups-subtitle">${html(cfg.brand || 'SANTAK')} / ${html(cfg.model || '')} / ${html(cfg.comm_mode || 'TCP')}</div>
                </div>
                <div class="status-chip-stack">
                    <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                    <span class="ups-chip">${html(modeText)}</span>
                    <span class="ups-chip ${status.is_bypass ? 'error' : ''}">${html(supplyStateText)}</span>
                </div>
            </div>
            <div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">输入 / 输出</div><div class="value">${fmt(status.input_voltage, 1)} V / ${fmt(status.output_voltage, 1)} V</div></div>
                <div class="ups-meta-item"><div class="label">输入频率 / 输出频率</div><div class="value">${fmt(status.input_frequency, 1, ' Hz')} / ${outputFreqText}</div></div>
                <div class="ups-meta-item"><div class="label">电池容量 / 续航</div><div class="value">${html(String(batteryText))} / ${html(String(backupText))}</div></div>
                <div class="ups-meta-item"><div class="label">总功率 / 负载</div><div class="value">${fmtAuto(status.total_real_power_kw, ' kW')} / ${fmt(status.load_percent, 1, ' %')}</div></div>
            </div>
            <div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">电池电压</div><div class="value">${fmt(status.battery_voltage, 2, ' V')}</div></div>
                <div class="ups-meta-item"><div class="label">视在功率</div><div class="value">${fmtAuto(status.total_apparent_power_kva, ' kVA')}</div></div>
                <div class="ups-meta-item"><div class="label">电池测试 / 温度</div><div class="value">${html(status.battery_test_text || '--')} / ${fmt(status.temperature, 1, ' °C')}</div></div>
                <div class="ups-meta-item"><div class="label">市电 / 电池状态</div><div class="value">${mainsText} / ${batteryStateText}</div></div>
            </div>
            <div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">三相输入电压</div><div class="value">${inputPhaseText}</div></div>
                <div class="ups-meta-item"><div class="label">协议输出电压 (${html(reportedVoltageKind)})</div><div class="value">${outputPhaseText}</div></div>
                <div class="ups-meta-item"><div class="label">三相输出电流</div><div class="value">${outputCurrentText}</div></div>
                <div class="ups-meta-item"><div class="label">故障 / 告警数量</div><div class="value">${faultCount} / ${warningCount}</div></div>
            </div>
            <div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">换算相电压</div><div class="value">${derivedPhaseText}</div></div>
                <div class="ups-meta-item"><div class="label">换算线电压</div><div class="value">${derivedLineText}</div></div>
                <div class="ups-meta-item"><div class="label">输入变压器</div><div class="value">${html(String(status.transformer_type || '--'))}</div></div>
                <div class="ups-meta-item"><div class="label">故障码 / 告警码</div><div class="value">${html(String(status.fault_code_raw || '--'))} / ${html(String(status.warning_code_raw || '--'))}</div></div>
            </div>
            <div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">数据质量</div><div class="value">${Number.isFinite(qualityScore) ? `${qualityScore} / 100 (${html(String(qualityText))})` : '--'}</div></div>
                <div class="ups-meta-item"><div class="label">链路类型</div><div class="value">${html(String(linkHint))}</div></div>
                <div class="ups-meta-item"><div class="label">最近成功</div><div class="value">${html(String(lastSuccessAge))}</div></div>
                <div class="ups-meta-item"><div class="label">采集耗时</div><div class="value">${html(String(costMs))}</div></div>
            </div>
            <div class="ups-alert-list">${alertHtml}</div>
            <div class="ups-action-row">
                <button class="btn-base btn-stop${permissionClass()}" ${permissionAttrs()} onclick="sendUpsShutdown('${html(cfg.id)}', '${html(cfg.shutdown_delay || '.3')}')">延时关机</button>
            </div>
            <div class="ups-action-row">
                <span class="ups-chip ${protocolSupport.q1 === false ? 'error' : 'online'}">Q1 ${protocolSupport.q1 === false ? '失败' : `正常(${fieldCounts.q1 ?? 0})`}</span>
                <span class="ups-chip ${protocolSupport.q6 ? (protocolSupport.q6_fallback ? 'warning' : 'online') : ''}" style="${protocolSupport.q6 ? (protocolSupport.q6_fallback ? 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);' : '') : 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);'}">Q6 ${protocolSupport.q6 ? (protocolSupport.q6_fallback ? `回退(${fieldCounts.q6 ?? 0})` : `正常(${fieldCounts.q6 ?? 0})`) : `降级(${fieldCounts.q6 ?? 0})`}</span>
                <span class="ups-chip ${protocolSupport.wa ? (protocolSupport.wa_fallback ? 'warning' : 'online') : ''}" style="${protocolSupport.wa ? (protocolSupport.wa_fallback ? 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);' : '') : 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);'}">WA ${protocolSupport.wa ? (protocolSupport.wa_fallback ? `回退(${fieldCounts.wa ?? 0})` : `正常(${fieldCounts.wa ?? 0})`) : `降级(${fieldCounts.wa ?? 0})`}</span>
            </div>
            ${(queryWarnings.length || !protocolSupport.q6 || !protocolSupport.wa || status.last_error || status.error || statusMeta.level === 'stale') ? `<div class="card-inline-note ${noteClass}">
                ${statusMeta.level === 'stale' ? `状态说明: ${html(statusMeta.note)}<br>` : ''}
                ${queryWarnings.length ? `${queryWarnings.map(item => html(item)).join('<br>')}${(!protocolSupport.q6 || !protocolSupport.wa || status.error) ? '<br>' : ''}` : ''}
                ${qualityDetails.length ? `${qualityDetails.map(item => `质量提示: ${html(String(item))}`).join('<br>')}<br>` : ''}
                ${(!protocolSupport.q6 || !protocolSupport.wa) ? `原始回包预览: Q1=${html(rawPreview.q1 || '--')} | Q6=${html(rawPreview.q6 || '--')} | WA=${html(rawPreview.wa || '--')}${status.error ? '<br>' : ''}` : ''}
                ${(status.last_error || status.error) ? `异常: ${html(status.last_error || status.error)}` : ''}
            </div>` : ''}
        </div>`;
    }

    function renderDashboardUpsCard(cfg, status) {
        const statusMeta = getStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
        const batteryText = status.battery_capacity_percent !== null && status.battery_capacity_percent !== undefined ? `${status.battery_capacity_percent}%` : '--';
        const loadText = status.load_percent !== null && status.load_percent !== undefined ? `${status.load_percent}%` : '--';
        const inputText = status.input_voltage !== null && status.input_voltage !== undefined ? `${status.input_voltage}V` : '--';
        const outputText = status.output_voltage !== null && status.output_voltage !== undefined ? `${status.output_voltage}V` : '--';
        const modeText = status.supply_state || status.system_mode || '--';
        return `<div class="dashboard-mini-card ${getStateClass(statusMeta)}">
            <div class="dashboard-mini-head">
                <div>
                    <div class="dashboard-mini-title">${html(cfg.name || cfg.id)}</div>
                    <div class="dashboard-mini-subtitle">${html(cfg.comm_mode || 'UPS')}</div>
                </div>
                <div class="dashboard-mini-chip-row">
                    <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                </div>
            </div>
            <div class="dashboard-mini-metrics">
                <div class="dashboard-mini-metric"><div class="label">电池</div><div class="value">${html(batteryText)}</div></div>
                <div class="dashboard-mini-metric"><div class="label">负载</div><div class="value">${html(loadText)}</div></div>
                <div class="dashboard-mini-metric"><div class="label">输入 / 输出</div><div class="value">${html(inputText)} / ${html(outputText)}</div></div>
                <div class="dashboard-mini-metric"><div class="label">模式</div><div class="value">${html(modeText)}</div></div>
            </div>
            <div class="dashboard-mini-note">${html(statusMeta.note)}</div>
        </div>`;
    }

    function renderUpsCards() {
        const dashboardGrid = document.getElementById('dashboard-ups-grid');
        const pageGrid = document.getElementById('ups-page-grid');
        const upsConfigs = getUpsConfigs();
        const statusCache = getUpsStatusCache();
        const visibleConfigs = upsConfigs.filter(cfg => cfg.visible !== false);
        const dashboardHtml = upsConfigs.length
            ? visibleConfigs.map(cfg => renderDashboardUpsCard(cfg, statusCache[cfg.id] || {})).join('')
            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置 UPS 设备</div>';
        const pageHtml = upsConfigs.length
            ? visibleConfigs.map(cfg => renderUpsCard(cfg, statusCache[cfg.id] || {})).join('')
            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置 UPS 设备</div>';
        if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
        if (pageGrid) pageGrid.innerHTML = pageHtml;
        renderDashboardUpsCompact();
    }

    function renderUpsCompanionCard(cfg, status) {
        const statusMeta = getStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
        const fmt = (value, digits = 1, suffix = '') => {
            const num = Number(value);
            return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : '--';
        };
        const fmtAuto = (value, suffix = '') => {
            const num = Number(value);
            if (!Number.isFinite(num)) return '--';
            const absVal = Math.abs(num);
            if (absVal >= 1000) return `${num.toFixed(0)}${suffix}`;
            if (absVal >= 100) return `${num.toFixed(1)}${suffix}`;
            return `${num.toFixed(2)}${suffix}`;
        };
        const batteryText = fmt(status.battery_capacity_percent, 1, '%');
        const loadText = fmt(status.load_percent, 1, '%');
        const inputText = fmt(status.input_voltage, 1, 'V');
        const outputText = fmt(status.output_voltage, 1, 'V');
        const modeText = status.supply_state || status.system_mode || '--';
        const mainsText = status.mains_abnormal ? '异常' : '正常';
        const batteryStateText = status.is_battery_low ? '偏低' : '正常';
        const faultCount = Array.isArray(status.fault_labels) ? status.fault_labels.length : 0;
        const warningCount = Array.isArray(status.warning_labels) ? status.warning_labels.length : 0;
        const powerText = fmtAuto(status.total_real_power_kw, 'kW');
        const alarmText = faultCount > 0 || warningCount > 0 ? `故障 ${faultCount} / 告警 ${warningCount}` : '无告警';
        const alarmClass = faultCount > 0 ? 'error' : (warningCount > 0 ? 'warn' : 'ok');
        const queryWarnings = Array.isArray(status.query_warnings) ? status.query_warnings : [];
        const protocolSupport = status.protocol_support || {};
        const fallbackChips = [];
        if (protocolSupport.q6_fallback) fallbackChips.push('Q6回退');
        if (protocolSupport.wa_fallback) fallbackChips.push('WA回退');
        const errorText = (status.last_error || status.error) ? `异常：${status.last_error || status.error}` : '';
        const noteText = errorText || (fallbackChips.length ? `协议回退：${fallbackChips.join(' / ')}` : '') || queryWarnings[0] || statusMeta.note || '';
        return `<div class="screen-companion-card screen-companion-ups wide ${getStateClass(statusMeta)}">
            <div class="screen-companion-title">
                <span>${html(cfg.name || cfg.id)}</span>
                <span class="screen-companion-title-actions">
                    <span class="screen-companion-tag" style="${statusMeta.chipClass === 'online' ? 'color:#bbf7d0;background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.30);' : (statusMeta.chipClass === 'warning' ? 'color:#fcd34d;background:rgba(245,158,11,0.16);border-color:rgba(245,158,11,0.24);' : 'color:#cbd5e1;background:rgba(100,116,139,0.16);border-color:rgba(148,163,184,0.18);')}">UPS ${statusMeta.text}</span>
                    <span class="screen-companion-tag ups-alarm-chip ${alarmClass}">${html(alarmText)}</span>
                </span>
            </div>
            <div class="screen-companion-metrics">
                <div class="screen-companion-metric">
                    <div class="label">模式</div>
                    <div class="value">${html(modeText)}</div>
                </div>
                <div class="screen-companion-metric">
                    <div class="label">负载</div>
                    <div class="value">${html(loadText)}</div>
                </div>
                <div class="screen-companion-metric">
                    <div class="label">电压</div>
                    <div class="value">
                        <div class="screen-companion-pair">
                            <div class="screen-companion-pair-row"><span class="mini-label">输入</span><span class="mini-value">${html(inputText)}</span></div>
                            <div class="screen-companion-pair-row"><span class="mini-label">输出</span><span class="mini-value">${html(outputText)}</span></div>
                        </div>
                    </div>
                </div>
                <div class="screen-companion-metric">
                    <div class="label">电池容量</div>
                    <div class="value">${html(batteryText)}</div>
                </div>
                <div class="screen-companion-metric">
                    <div class="label">总功率</div>
                    <div class="value">${html(powerText)}</div>
                </div>
                <div class="screen-companion-metric">
                    <div class="label">供电</div>
                    <div class="value">
                        <div class="screen-companion-pair">
                            <div class="screen-companion-pair-row"><span class="mini-label">市电</span><span class="mini-value">${html(mainsText)}</span></div>
                            <div class="screen-companion-pair-row"><span class="mini-label">电池</span><span class="mini-value">${html(batteryStateText)}</span></div>
                        </div>
                    </div>
                </div>
            </div>
            ${noteText ? `<div class="screen-companion-note ${(errorText || statusMeta.level === 'error') ? 'error' : ''}">${html(noteText)}</div>` : ''}
            <div class="screen-companion-footer">
                <span>${html(cfg.comm_mode || 'TCP')}</span>
                <span>${html(statusMeta.note || '状态正常')}</span>
            </div>
        </div>`;
    }

    function buildScreenUpsCards() {
        const cards = [];
        const statusCache = getUpsStatusCache();
        const upsConfigs = getUpsConfigs();
        if (upsConfigs.length) {
            upsConfigs
                .filter(cfg => cfg.visible !== false)
                .slice(0, 1)
                .forEach(cfg => {
                    cards.push(renderUpsCompanionCard(cfg, statusCache[cfg.id] || {}));
                });
        }
        if (!cards.length) {
            cards.push(`<div class="screen-companion-card screen-placeholder-card">
                <div class="screen-companion-title">
                    <span class="screen-placeholder-icon">+</span>
                    <span>UPS 摘要</span>
                </div>
                <div class="screen-companion-note">这里显示 UPS 运行状态、电池和告警摘要。</div>
            </div>`);
        }
        return cards.join('');
    }

    function updateUpsStatus() {
        return fetchUpsStatus()
            .then(data => {
                setUpsStatusCache(data || {});
                renderUpsCards();
            })
            .catch(err => console.error('UPS 状态更新失败', err));
    }

    function sendUpsShutdown(id, delay) {
        if (!ensureControlPermission()) return;
        if (!global.confirm(`确定向 UPS 下发延时关机命令 S${delay} 吗？`)) return;
        postUpsControl({ id, action: 'shutdown', delay })
            .then(data => {
                if (!data.success) {
                    notify(data.message || data.msg || 'UPS 指令执行失败', true);
                    return;
                }
                notify(`UPS 指令已下发: ${data.command || 'S<n>'}`);
            })
            .catch(err => notify(translateError(err?.message, 'UPS 指令下发失败'), true));
    }

    const api = {
        setUpsConfigs,
        getUpsConfigs,
        getUpsStatusCache,
        setUpsStatusCache,
        getUpsCompactAlarmMeta,
        renderDashboardUpsCompact,
        renderUpsCard,
        renderDashboardUpsCard,
        renderUpsCards,
        renderUpsCompanionCard,
        buildScreenUpsCards,
        updateUpsStatus,
        sendUpsShutdown,
    };

    SmartCenter.ups = Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.ups', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/ups.js',
        });
    }

    global.upsStatusCache = state.statusCache;
    Object.assign(global, api);
})(window);
