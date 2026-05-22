(function installSmartCenterPowerMeter(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.powerMeter = Object.assign({}, SmartCenter.powerMeter || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));
    const formatFixedNumber = utils.formatFixedNumber || global.formatFixedNumber || ((value, digits = 0, suffix = '', fallback = '--') => {
        const num = Number(value);
        return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : fallback;
    });
    const formatTimeShort = utils.formatTimeShort || global.formatTimeShort || (value => {
        if (!value) return '--';
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return String(value).slice(0, 19).replace('T', ' ');
        return d.toLocaleTimeString('zh-CN', { hour12: false });
    });

    function looksLikeGarbledText(value) {
        const text = String(value ?? '').trim();
        if (!text) return true;
        return ['?', '锛', '馃', '篇胆赤', '狼双', '高桁', '寮€', '闂'].some(token => text.includes(token));
    }

        function sanitizeReadableText(value, fallback = '--') {
            const text = String(value ?? '').trim();
            if (!text) return fallback;
            return looksLikeGarbledText(text) ? fallback : text;
        }
        function formatPowerValue(value, digits = 1, suffix = '') {
            return formatFixedNumber(value, digits, suffix, '--');
        }
        function getCabinetDisplayName(cab, cabId) {
            const cabinetName = sanitizeReadableText(cab?.cabinet_name, '');
            if (cabinetName && cabinetName !== '--') return cabinetName;
            const meterName = sanitizeReadableText(cab?.meter_display_name, '');
            if (meterName && meterName !== '--') return meterName;
            return `电柜 ${Number(cabId) + 1}`;
        }
        function getCabinetSubtitle(cab) {
            const ip = sanitizeReadableText(cab?.ip, '--');
            const protocol = sanitizeReadableText(cab?.plc_type, '强电柜');
            const port = Number(cab?.port);
            return `${protocol} / ${ip}${Number.isFinite(port) ? ':' + port : ''}`;
        }
        function getPowerChannelDisplayName(cab, chNum) {
            const channels = Array.isArray(cab?.channels_config) ? cab.channels_config : [];
            const match = channels.find(item => Number(item?.channel) === Number(chNum));
            const channelName = sanitizeReadableText(match?.name, '');
            return channelName && channelName !== '--' ? channelName : `通道 ${chNum}`;
        }
        function getPowerChannelConfig(cab, chNum) {
            const channels = Array.isArray(cab?.channels_config) ? cab.channels_config : [];
            return channels.find(item => Number(item?.channel) === Number(chNum)) || {};
        }
        function getPowerChannelRemark(cab, chNum) {
            const match = getPowerChannelConfig(cab, chNum);
            const remark = sanitizeReadableText(match?.remark || match?.usage || match?.description, '');
            return remark && remark !== '--' ? remark : '';
        }
        function renderPowerChannelLabelHtml(cab, chNum, options = {}) {
            const name = getPowerChannelDisplayName(cab, chNum);
            const remark = getPowerChannelRemark(cab, chNum);
            const compact = !!options.compact;
            const remarkHtml = remark
                ? `<span class="remark" title="${escapeHtml(remark)}">${escapeHtml(remark)}</span>`
                : '';
            return `<span class="name" title="${escapeHtml(remark ? name + ' / ' + remark : name)}">${escapeHtml(name)}</span>${compact ? '' : remarkHtml}`;
        }
        function renderDashboardPowerHistory(historyRows, status) {
            const rows = Array.isArray(historyRows) ? historyRows.slice(-7) : [];
            if (!rows.length) {
                const todayText = Number(status?.daily_energy || 0) > 0 ? `今日累计 ${formatPowerValue(status.daily_energy, 1, ' kWh')}` : '历史数据仍在累计';
                return `<div class="dashboard-power-history">
                    <div class="dashboard-power-history-head">
                        <div class="dashboard-power-history-title">近 7 天用电</div>
                        <div class="dashboard-power-history-meta">${todayText}</div>
                    </div>
                    <div class="dashboard-power-history-empty">当前只拿到最近实时累计，后续会随着采集继续补齐历史曲线。</div>
                </div>`;
            }
            const peak = Math.max(...rows.map(item => Number(item.consume || 0)), 0);
            const total = rows.reduce((sum, item) => sum + Number(item.consume || 0), 0);
            const bars = rows.map(item => {
                const value = Number(item.consume || 0);
                const percent = peak > 0 ? Math.max(14, Math.round((value / peak) * 100)) : (item.is_today ? 18 : 10);
                return `<div class="dashboard-power-history-bar-wrap">
                    <div class="dashboard-power-history-bar ${item.is_today ? 'today' : ''}" style="height:${percent}%"></div>
                    <span>${String(item.date || '').slice(8) || '--'}</span>
                </div>`;
            }).join('');
            return `<div class="dashboard-power-history">
                <div class="dashboard-power-history-head">
                    <div class="dashboard-power-history-title">近 7 天用电</div>
                    <div class="dashboard-power-history-meta">累计 ${formatPowerValue(total, 1, ' kWh')} / 峰值 ${formatPowerValue(peak, 1, ' kWh')}</div>
                </div>
                <div class="dashboard-power-history-bars">${bars}</div>
            </div>`;
        }

        function formatHomeNumber(value, digits = 0, suffix = '') {
            return formatFixedNumber(value, digits, suffix, '--');
        }
        function renderHomeCompactMetric(label, value, tone = '') {
            return `<div class="home-compact-metric">
                <div class="label">${escapeHtml(label)}</div>
                <div class="value ${escapeHtml(tone)}">${escapeHtml(value)}</div>
            </div>`;
        }
        function getMeterModeText(mode) {
            const textMap = { type1: '电表类型 1', type4: '电表类型 4' };
            return textMap[String(mode || '').toLowerCase()] || (mode || '未定义');
        }
        function renderMeterTypeChips(typeCounts) {
            const wrap = document.getElementById('meter-type-chip-row');
            if (!wrap) return;
            const entries = Object.entries(typeCounts || {});
            if (!entries.length) {
                wrap.innerHTML = '<span class="meter-type-chip">暂无已接入电表型号</span>';
                return;
            }
            wrap.innerHTML = entries.map(([key, count]) => `<span class="meter-type-chip">${escapeHtml(getMeterModeText(key))} / ${escapeHtml(String(count))} 台</span>`).join('');
        }
        function meterValueOrDash(value, digits = 1, unit = '', zeroAsDash = false) {
            const num = Number(value);
            if (!Number.isFinite(num)) return '--';
            if (zeroAsDash && Math.abs(num) < 0.0001) return '--';
            return `${num.toFixed(digits)}${unit ? ' ' + unit : ''}`;
        }
        function normalizeMeterCardOrder(meters) {
            const list = Array.isArray(meters) ? [...meters] : [];
            return list.sort((left, right) => {
                const leftRef = left && left.is_reference_meter ? 1 : 0;
                const rightRef = right && right.is_reference_meter ? 1 : 0;
                if (leftRef !== rightRef) return rightRef - leftRef;
                const leftSort = Number(left?.sort_order ?? left?.meter_sort_order ?? 999);
                const rightSort = Number(right?.sort_order ?? right?.meter_sort_order ?? 999);
                if (leftSort !== rightSort) return leftSort - rightSort;
                const leftName = String(left?.display_name || left?.cabinet_name || left?.id || '');
                const rightName = String(right?.display_name || right?.cabinet_name || right?.id || '');
                return leftName.localeCompare(rightName, 'zh-CN');
            });
        }
        function renderMeterCard(meter) {
            const online = !!meter.online;
            const degraded = !!meter._degraded || String(meter.error || '').includes('fallback:');
            const isReferenceMeter = !!meter.is_reference_meter;
            const updatedText = meter.updated_at ? String(meter.updated_at).replace('T', ' ').slice(0, 19) : '--';
            const errorText = String(meter.error || '').trim();
            const dataSourceText = meter.source_label || meter.source || (degraded ? '降级采集' : (online ? '远程采集' : '等待连接'));
            const titleText = meter.display_name || meter.cabinet_name || meter.id;
            const subtitleText = isReferenceMeter ? '参考主表 · 不参与统计' : `${meter.area_name || '电表'} · ${dataSourceText}`;
            const statusText = online ? (degraded ? '告警' : '在线') : '离线';
            const detailText = online ? escapeHtml(errorText || '远程采集正常') : escapeHtml(errorText || '设备离线或暂无返回');
            const powerValue = Number((meter.effective_realtime_power ?? meter.stable_realtime_power ?? meter.realtime_power) || 0).toFixed(2);
            const phaseValues = [
                { label: 'A', voltage: Number(meter.voltage_a || 0), current: Number(meter.current_a || 0) },
                { label: 'B', voltage: Number(meter.voltage_b || 0), current: Number(meter.current_b || 0) },
                { label: 'C', voltage: Number(meter.voltage_c || 0), current: Number(meter.current_c || 0) }
            ];
            const voltageAlerts = phaseValues
                .filter(item => Number.isFinite(item.voltage) && item.voltage > 0 && (item.voltage < 180 || item.voltage > 250))
                .map(item => `${item.label} ${item.voltage.toFixed(1)}V`);
            const extraItems = [
                voltageAlerts.length ? { label: 'VOLT', value: voltageAlerts.join(' / ') } : null,
                { label: 'PF', value: meterValueOrDash(meter.power_factor, 3, '', true) },
                { label: 'kVA', value: meterValueOrDash(meter.apparent_power, 2, 'kVA', true) }
            ].filter(item => item && item.value !== '--');
            const extraHtml = extraItems.length
                ? `<div class="meter-extra-grid">${extraItems.map(item => `<div class="meter-extra-card"><div class="label">${escapeHtml(item.label)}</div><div class="value">${escapeHtml(item.value)}</div></div>`).join('')}</div>`
                : '';
            return `<div class="meter-card meter-card-dense ${online ? '' : 'offline'} ${isReferenceMeter ? 'reference-meter' : ''}">
                <div class="meter-card-head">
                    <div class="meter-title-block">
                        <div class="meter-card-title">${escapeHtml(titleText)}</div>
                        <div class="meter-card-subtitle">${escapeHtml(subtitleText)}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="meter-status-chip ${online ? (degraded ? 'degraded' : 'online') : 'offline'}">${statusText}</span>
                        ${isReferenceMeter ? `<span class="meter-status-chip">对照</span>` : ''}
                        ${meter.mode ? `<span class="meter-status-chip">${escapeHtml(getMeterModeText(meter.mode))}</span>` : ''}
                    </div>
                </div>
                <div class="meter-dense-main">
                    <div class="meter-dense-power">
                        <span>实时功率</span>
                        <strong>${powerValue}<em>kW</em></strong>
                    </div>
                    <div class="meter-kpi-grid">
                        <div class="meter-kpi-card"><div class="label">累计</div><div class="value">${Number(meter.effective_electric_energy || 0).toFixed(1)} kWh</div></div>
                        <div class="meter-kpi-card"><div class="label">今日</div><div class="value" style="color:var(--success);">${Number(meter.daily_energy || 0).toFixed(1)} kWh</div></div>
                        <div class="meter-kpi-card"><div class="label">本月</div><div class="value" style="color:var(--brand-blue);">${Number(meter.monthly_energy || 0).toFixed(1)} kWh</div></div>
                    </div>
                </div>
                ${extraHtml}
                <div class="meter-foot">
                    <span>${escapeHtml(updatedText)}</span>
                    <span>${detailText}</span>
                </div>
            </div>`;
        }
        function formatReferenceMeta(metric, unit = '') {
            if (!metric || metric.available === false) {
                const reason = metric?.reason || '';
                if (reason === 'reference_monthly_history_incomplete') {
                    const recordDays = Number(metric?.record_days || 0);
                    const expectedDays = Number(metric?.expected_days || 0);
                    const suffix = expectedDays > 0 ? `（${recordDays}/${expectedDays} 天）` : '';
                    return `参考总表 <strong>月度历史不足，暂不比较${suffix}</strong>`;
                }
                if (reason === 'power_comparison_disabled') return '功率按卡片合计展示，参考总表仅作旁路监看';
                return '参考总表 <strong>未接入</strong>';
            }
            const referenceValue = Number(metric.reference || 0);
            const deltaValue = Number(metric.delta || 0);
            const referenceText = Number.isFinite(referenceValue) ? referenceValue.toFixed(unit === '%' ? 2 : 1) : '--';
            let deltaText = '--';
            if (Number.isFinite(deltaValue)) {
                const deltaAbsText = Math.abs(deltaValue).toFixed(unit === '%' ? 2 : 1);
                if (deltaValue > 0) deltaText = `多 ${deltaAbsText}`;
                else if (deltaValue < 0) deltaText = `少 ${deltaAbsText}`;
                else deltaText = `持平 ${deltaAbsText}`;
            }
            return `参考总表 <strong>${referenceText}${unit}</strong> · 差值 <strong>${deltaText}${unit}</strong>`;
        }
        function formatPowerSummaryMeta(summary) {
            const referencePower = Number(
                summary.reference_total_realtime_power
                ?? summary.reference_meter?.realtime_power
                ?? 0
            );
            const cardTotalPower = Number(
                summary.card_total_realtime_power
                ?? summary.stable_total_realtime_power
                ?? summary.submeter_estimated_total_realtime_power
                ?? summary.estimated_total_realtime_power
                ?? summary.submeter_total_realtime_power
                ?? summary.total_realtime_power
                ?? 0
            );
            if (Number.isFinite(referencePower) && referencePower > 0) {
                if (Number.isFinite(cardTotalPower) && cardTotalPower >= 0) {
                    return `参考总表 <strong>${referencePower.toFixed(2)} kW</strong> · 卡片合计 <strong>${cardTotalPower.toFixed(2)} kW</strong>`;
                }
                return `参考总表 <strong>${referencePower.toFixed(2)} kW</strong>`;
            }
            if (Number.isFinite(cardTotalPower) && cardTotalPower >= 0) {
                return `参考总表 <strong>未接入</strong> · 卡片合计 <strong>${cardTotalPower.toFixed(2)} kW</strong>`;
            }
            return '参考总表 <strong>未接入</strong>';
        }
        function renderMeterTrendSelectors(payload) {
            const targetSelect = document.getElementById('meter-trend-target');
            const periodSelect = document.getElementById('meter-trend-period');
            const targets = Array.isArray(payload.trend_targets) ? payload.trend_targets : [];
            if (targetSelect) {
                targetSelect.innerHTML = targets.map(item => `<option value="${escapeHtml(item.source_key || 'total')}" ${String(payload.trend_target || 'total') === String(item.source_key || 'total') ? 'selected' : ''}>${escapeHtml(item.label || item.source_key || '未命名')}</option>`).join('');
            }
            if (periodSelect) {
                periodSelect.value = payload.trend_period || 'day';
            }
            const targetLabel = document.getElementById('meter-trend-target-label');
            const periodLabel = document.getElementById('meter-trend-period-label');
            const targetBadge = document.getElementById('meter-summary-badge-target');
            if (targetLabel) targetLabel.innerText = payload.trend_target_label || '全部统计电表';
            if (targetBadge) targetBadge.innerText = payload.trend_target_label || '全部统计电表';
            if (periodLabel) periodLabel.innerText = payload.trend_period === 'week' ? '按周' : (payload.trend_period === 'month' ? '按月' : '按日');
        }
        function resolveMeterSourceMeta(payload) {
            const source = String((payload || {}).data_source || '').toLowerCase();
            const remoteUrl = String((payload || {}).remote_service_url || '').trim();
            const remoteError = String((payload || {}).remote_error || '').trim();
            if (source === 'remote_meter_service') {
                return {
                    text: 'NAS 远程',
                    color: '#86efac',
                    title: remoteUrl ? `当前正在读取独立电表服务：${remoteUrl}` : '当前正在读取独立电表服务'
                };
            }
            if (source === 'remote_meter_service_cache') {
                return {
                    text: 'NAS 缓存',
                    color: '#fcd34d',
                    title: remoteError
                        ? `NAS 电表服务短时异常，当前显示最近一次成功缓存：${remoteError}`
                        : 'NAS 电表服务短时异常，当前显示最近一次成功缓存'
                };
            }
            if (source === 'remote_meter_service_error' || source === 'remote_meter_service_required') {
                return {
                    text: 'NAS 异常',
                    color: '#fcd34d',
                    title: remoteError ? `NAS 电表服务异常：${remoteError}` : 'NAS 电表服务不可用'
                };
            }
            if (source === 'meter_service') {
                return {
                    text: '独立服务',
                    color: '#93c5fd',
                    title: '当前页面数据来自独立电表服务'
                };
            }
            return {
                text: 'NAS 远程',
                color: '#86efac',
                title: remoteUrl ? `当前正在读取独立电表服务：${remoteUrl}` : '当前正在读取独立电表服务'
            };
        }


    Object.assign(state, {
        sanitizeReadableText,
        formatPowerValue,
        getCabinetDisplayName,
        getCabinetSubtitle,
        getPowerChannelDisplayName,
        getPowerChannelConfig,
        getPowerChannelRemark,
        renderPowerChannelLabelHtml,
        renderDashboardPowerHistory,
        formatHomeNumber,
        renderHomeCompactMetric,
        getMeterModeText,
        renderMeterTypeChips,
        meterValueOrDash,
        normalizeMeterCardOrder,
        renderMeterCard,
        formatReferenceMeta,
        formatPowerSummaryMeta,
        renderMeterTrendSelectors,
        resolveMeterSourceMeta,
    });

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.power-meter', {
            version: '20260522-stage4-power-meter',
            source: 'static/js/views/power-meter.js',
        });
    }
})(window);
