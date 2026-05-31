// AI_MODULE: power_meter_runtime
// AI_PURPOSE: 强电柜状态刷新、首页强电卡片、电表中心和能耗图表运行时。
// AI_BOUNDARY: 真实强电控制确认和 payload 仍由 app-runtime.js 中的 togglePower/doPowerStart/doPowerStop 负责。
// AI_DATA_FLOW: /api/status /api/logs /api/7days_energy /api/meters -> DOM；控制后由 app-runtime 调用本模块回读状态。
// AI_RUNTIME: dashboard 强电区接近视口或进入 power/meter 视图时按需加载，降低 app-runtime 首屏体积。
// AI_RISK: 中高，读取真实强电状态但不直接下发强电控制；必须保持状态回读、权限样式和旧全局函数兼容。
// AI_SEARCH_KEYWORDS: power meter runtime, dashboard power, meter center, energy chart, strong current.

(function installSmartCenterPowerMeterRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const helper = SmartCenter.powerMeter || {};
    const state = SmartCenter.powerMeterRuntime = Object.assign({
        charts: {},
        powerHistoryCache: {},
        powerLogCache: {},
        powerSupplementFetchAt: {},
        powerSupplementInFlight: {},
        powerFetchInFlight: null,
        powerVisibleSupplementCabIds: [],
        meterCenterCache: { summary: {}, meters: [], trend: [] },
        meterTrendTarget: 'total',
        meterTrendPeriod: 'day',
        meterCenterRequestSeq: 0,
        meterTrendOptionSignature: '',
        meterTrendAxisKey: '',
        meterTrendYAxisMax: 0,
        echartsRuntimeLoading: null,
    }, SmartCenter.powerMeterRuntime || {});

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
        const provider = typeof global.getPowerMeterRuntimeContext === 'function'
            ? (global.getPowerMeterRuntimeContext() || {})
            : {};
        return Object.assign({
            configData: global.configData || {},
            fetchJson: utils.fetchJson || global.fetchJson,
            showToast: utils.showToast || global.showToast || (() => {}),
            translateApiError: utils.translateApiError || global.translateApiError || ((err, fallback) => String(err || fallback || '请求失败')),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            formatTimeShort: utils.formatTimeShort || global.formatTimeShort || (value => {
                if (!value) return '--';
                const d = new Date(value);
                return Number.isNaN(d.getTime()) ? String(value).slice(0, 19).replace('T', ' ') : d.toLocaleTimeString('zh-CN', { hour12: false });
            }),
            setTextIfExists: global.setTextIfExists || ((id, text) => {
                const el = document.getElementById(id);
                if (el) el.textContent = text;
            }),
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            getActiveViewId: global.getActiveViewId || (() => 'dashboard'),
            isDashboardSectionVisible: global.isDashboardSectionVisible || (() => false),
            resolveVisiblePowerSupplementCabIds: global.resolveVisiblePowerSupplementCabIds || (() => []),
            getPowerChannelStatus: global.getPowerChannelStatus || (() => null),
            applyPowerStatusSnapshot: global.applyPowerStatusSnapshot || (() => false),
            renderPwrChannel: global.renderPwrChannel || (() => {}),
            powerStatusCache: global.powerStatusCache || {},
            pwrPending: global.pwrPending || {},
            renderPowerDetailLogs: SmartCenter.logs?.renderPowerDetailLogs || global.renderPowerDetailLogs || (() => {}),
            renderPowerLogSourceTag: SmartCenter.logs?.renderPowerLogSourceTag || global.renderPowerLogSourceTag || (() => ''),
            normalizeLogOperationText: SmartCenter.logs?.normalizeLogOperationText || global.normalizeLogOperationText || (log => String(log?.operation || log?.msg || log || '')),
        }, provider || {}, context || {});
    }

    function helperCall(name, fallback, args) {
        const fn = helper && typeof helper[name] === 'function' ? helper[name] : fallback;
        return fn.apply(helper, args);
    }

    function sanitizeReadableText(value, fallback = '--') {
        return helperCall('sanitizeReadableText', val => {
            const text = String(val ?? '').trim();
            return text || fallback;
        }, arguments);
    }

    function formatPowerValue(value, digits = 1, suffix = '') {
        return helperCall('formatPowerValue', val => {
            const num = Number(val);
            return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : '--';
        }, arguments);
    }

    function getCabinetDisplayName(cab, cabId) {
        return helperCall('getCabinetDisplayName', () => `电柜 ${Number(cabId) + 1}`, arguments);
    }

    function getCabinetSubtitle(cab) {
        return helperCall('getCabinetSubtitle', () => {
            const ip = sanitizeReadableText(cab?.ip, '--');
            const port = Number(cab?.port);
            return `${sanitizeReadableText(cab?.plc_type, '强电柜')} / ${ip}${Number.isFinite(port) ? ':' + port : ''}`;
        }, arguments);
    }

    function renderPowerChannelLabelHtml(cab, chNum, options = {}) {
        return helperCall('renderPowerChannelLabelHtml', () => {
            const cfg = (Array.isArray(cab?.channels_config) ? cab.channels_config : []).find(item => Number(item?.channel) === Number(chNum)) || {};
            const name = String(cfg.name || `通道 ${chNum}`);
            const remark = String(cfg.remark || cfg.usage || cfg.description || '').trim();
            const ctx = getContext();
            return `<span class="name" title="${ctx.escapeHtml(remark ? name + ' / ' + remark : name)}">${ctx.escapeHtml(name)}</span>${options.compact || !remark ? '' : `<span class="remark" title="${ctx.escapeHtml(remark)}">${ctx.escapeHtml(remark)}</span>`}`;
        }, arguments);
    }

    function renderDashboardPowerHistory(historyRows, status) {
        return helperCall('renderDashboardPowerHistory', () => '', arguments);
    }

    function formatHomeNumber(value, digits = 0, suffix = '') {
        return helperCall('formatHomeNumber', val => {
            const num = Number(val);
            return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : '--';
        }, arguments);
    }

    function renderMeterTypeChips(typeCounts) {
        return helperCall('renderMeterTypeChips', () => {}, arguments);
    }

    function normalizeMeterCardOrder(meters) {
        return helperCall('normalizeMeterCardOrder', rows => Array.isArray(rows) ? rows : [], arguments);
    }

    function renderMeterCard(meter) {
        return helperCall('renderMeterCard', item => {
            const ctx = getContext();
            return `<div class="meter-card"><div class="meter-card-title">${ctx.escapeHtml(item?.display_name || item?.id || '未命名电表')}</div></div>`;
        }, arguments);
    }

    function formatReferenceMeta(metric, unit = '') {
        return helperCall('formatReferenceMeta', () => '参考总表 <strong>--</strong>', arguments);
    }

    function formatPowerSummaryMeta(summary) {
        return helperCall('formatPowerSummaryMeta', () => '参考总表 <strong>未接入</strong>', arguments);
    }

    function renderMeterTrendSelectors(payload) {
        return helperCall('renderMeterTrendSelectors', () => {}, arguments);
    }

    function resolveMeterSourceMeta(payload) {
        return helperCall('resolveMeterSourceMeta', () => ({ text: '电表服务', color: '#f8fafc', title: '' }), arguments);
    }

    function isChartElementRenderable(dom) {
        if (!dom || !dom.isConnected) return false;
        const rect = typeof dom.getBoundingClientRect === 'function' ? dom.getBoundingClientRect() : null;
        if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
        if (dom.clientWidth <= 0 || dom.clientHeight <= 0) return false;
        const style = window.getComputedStyle ? window.getComputedStyle(dom) : null;
        return !style || (style.display !== 'none' && style.visibility !== 'hidden');
    }

    function ensureEChartsRuntime(contextLabel = '图表', context = {}) {
        const ctx = getContext(context);
        if (global.echarts) return Promise.resolve(global.echarts);
        if (!state.echartsRuntimeLoading) {
            state.echartsRuntimeLoading = SmartCenter.utils.ensureEChartsLoaded()
                .catch(err => {
                    console.error(`${contextLabel}运行库加载失败`, err);
                    ctx.showToast(`${contextLabel}运行库加载失败，请刷新后重试`, true);
                    throw err;
                })
                .finally(() => {
                    state.echartsRuntimeLoading = null;
                });
        }
        return state.echartsRuntimeLoading;
    }

    function ensurePowerChart(cabId) {
        if (typeof global.echarts === 'undefined') return null;
        const chartEl = document.getElementById(`energyChart_${cabId}`);
        if (!isChartElementRenderable(chartEl)) return null;
        if (state.charts[cabId]) return state.charts[cabId];
        try {
            state.charts[cabId] = global.echarts.init(chartEl);
            return state.charts[cabId];
        } catch (err) {
            console.error('强电图表初始化失败', cabId, err);
            return null;
        }
    }

    function resizePowerCharts(context = {}) {
        if (typeof global.echarts === 'undefined') return;
        const ctx = getContext(context);
        const cabinets = Array.isArray(ctx.configData.cabinets) ? ctx.configData.cabinets : [];
        cabinets.forEach((_, cabId) => {
            const chart = ensurePowerChart(cabId);
            if (!chart) return;
            try { chart.resize(); } catch (err) { console.error('强电图表 resize 失败', cabId, err); }
        });
        if (state.charts.meterTrend) {
            try { state.charts.meterTrend.resize(); } catch (err) { console.error('电表趋势图 resize 失败', err); }
        }
        if (state.charts.dashboardEnergyTrend) {
            try { state.charts.dashboardEnergyTrend.resize(); } catch (err) { console.error('首页能耗趋势图 resize 失败', err); }
        }
    }

    function renderPowerEnergyChart(cabId, rawData, context = {}) {
        const chartEl = document.getElementById(`energyChart_${cabId}`);
        if (!isChartElementRenderable(chartEl)) return;
        if (typeof global.echarts === 'undefined') {
            ensureEChartsRuntime('强电图表', context).then(() => renderPowerEnergyChart(cabId, rawData, context)).catch(() => {});
            return;
        }
        const chart = ensurePowerChart(cabId);
        if (!chart) return;
        const data = Array.isArray(rawData) ? rawData : [];
        const nonZeroCount = data.filter(item => Number(item.consume || 0) > 0).length;
        const option = {
            tooltip: { trigger: 'axis' },
            xAxis: {
                type: 'category',
                data: data.map(item => String(item.date || '').slice(5)),
                axisLabel: { color: '#94a3b8', rotate: data.length > 14 ? 35 : 0, interval: data.length > 20 ? 2 : 0 }
            },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#94a3b8' } },
            series: [{
                data: data.map(item => Number(item.consume || 0)),
                type: 'bar',
                barMaxWidth: data.length > 20 ? 14 : 24,
                itemStyle: {
                    color: params => (data[params.dataIndex] && data[params.dataIndex].is_today) ? '#f59e0b' : '#3b82f6',
                    borderRadius: [4, 4, 0, 0]
                },
                label: { show: data.length <= 14, position: 'top', color: '#f8fafc' }
            }],
            graphic: nonZeroCount > 1 ? [] : [{
                type: 'text',
                right: 12,
                top: 10,
                style: { text: '历史数据仍在累计，当前以近 7 天摘要展示', fill: '#94a3b8', fontSize: 11 }
            }]
        };
        try {
            chart.setOption(option, true);
            chart.resize();
        } catch (err) {
            console.error('强电图表渲染失败', cabId, err);
        }
    }

    function renderDashboardPowerCards(context = {}) {
        const ctx = getContext(context);
        const container = document.getElementById('dashboard-power-grid');
        if (!container) return;
        const cabinets = Array.isArray(ctx.configData.cabinets) ? ctx.configData.cabinets : [];
        if (!cabinets.length) {
            container.innerHTML = '<div style="color:var(--text-sub); text-align:center; padding:20px;">未配置强电柜</div>';
            return;
        }
        container.innerHTML = cabinets.map((cab, cabId) => {
            const status = ctx.powerStatusCache[cabId] || {};
            const online = !!status.comm_status;
            const visibleChannels = (Array.isArray(cab.channels_config) ? cab.channels_config : [])
                .filter(item => item && item.visible !== false)
                .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                .slice(0, 6);
            const channelsHtml = visibleChannels.map(ch => {
                const chNum = Number(ch.channel);
                const channelState = ctx.getPowerChannelStatus(cabId, chNum);
                const isPending = !!(ctx.pwrPending[cabId] && ctx.pwrPending[cabId][chNum]);
                const cls = isPending ? 'ch-off' : (channelState === null || channelState === undefined ? 'ch-err' : (channelState ? 'ch-on' : 'ch-off'));
                const stateText = isPending ? '执行中' : (channelState === null || channelState === undefined ? '离线' : (channelState ? '已合闸' : '已断开'));
                return `<button class="power-mini-channel ${cls}${ctx.getPermissionDisabledClass('power.control')}" ${ctx.getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                    ${renderPowerChannelLabelHtml(cab, chNum)}
                    <span class="state">${ctx.escapeHtml(stateText)}</span>
                </button>`;
            }).join('');
            const logs = (state.powerLogCache[cabId] || []).slice(0, 2);
            const logsHtml = logs.length ? logs.map(log => {
                const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
                return `<div class="dashboard-power-log-item"><span class="dashboard-power-log-time">[${timeText}]</span>${ctx.renderPowerLogSourceTag(log, 'dashboard-power-log-source')}<span class="dashboard-power-log-text">${ctx.escapeHtml(ctx.normalizeLogOperationText(log))}</span></div>`;
            }).join('') : '<div class="dashboard-power-log-empty">暂无最近操作</div>';
            const workMode = sanitizeReadableText(status.work_mode, '未知模式');
            const tempValue = Number(status.cabinet_temp);
            const humiValue = Number(status.cabinet_humidity);
            const stopMsg = ctx.escapeHtml(String(cab?.ui_text?.confirm_stop || '确定要停止该电柜所有通道吗？'));
            return `<div class="dashboard-power-card ${online ? '' : 'offline'}" id="dash-power-card-${cabId}">
                <div class="dashboard-power-head">
                    <div>
                        <div class="dashboard-power-title">${ctx.escapeHtml(getCabinetDisplayName(cab, cabId))}</div>
                        <div class="dashboard-power-subtitle">${ctx.escapeHtml(getCabinetSubtitle(cab))}</div>
                    </div>
                    <div class="dashboard-power-chip-row">
                        <span class="ups-chip ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span>
                        <span class="ups-chip">${ctx.escapeHtml(workMode)}</span>
                    </div>
                </div>
                <div class="dashboard-power-kpis">
                    <div class="dashboard-power-kpi"><div class="label">实时功率</div><div class="value warn">${formatPowerValue(status.realtime_power, 2, ' kW')}</div></div>
                    <div class="dashboard-power-kpi"><div class="label">今日用电</div><div class="value ok">${formatPowerValue(status.daily_energy, 1, ' kWh')}</div></div>
                    <div class="dashboard-power-kpi"><div class="label">本月用电</div><div class="value">${formatPowerValue(status.monthly_energy, 1, ' kWh')}</div></div>
                    <div class="dashboard-power-kpi"><div class="label">温湿度</div><div class="value">${Number.isFinite(tempValue) ? tempValue.toFixed(1) + ' C' : '--'} / ${Number.isFinite(humiValue) ? humiValue.toFixed(1) + '%' : '--'}</div></div>
                </div>
                ${renderDashboardPowerHistory(state.powerHistoryCache[cabId], status)}
                <div class="dashboard-power-channels">${channelsHtml || '<div class="dashboard-power-log-empty" style="grid-column:1/-1;">暂无可控通道</div>'}</div>
                <div class="dashboard-power-actions">
                    <button class="dashboard-mini-btn success${ctx.getPermissionDisabledClass('power.control')}" ${ctx.getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStart(${cabId})">一键启动</button>
                    <button class="dashboard-mini-btn danger${ctx.getPermissionDisabledClass('power.control')}" ${ctx.getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStop(${cabId}, '${stopMsg}')">一键停止</button>
                    <button class="dashboard-mini-btn secondary" type="button" onclick="switchTab('power', '强电控制')">详情</button>
                </div>
                <div class="dashboard-power-log">
                    <div class="dashboard-power-log-title">最近操作</div>
                    <div class="dashboard-power-log-list">${logsHtml}</div>
                </div>
            </div>`;
        }).join('');
    }

    function renderDashboardPowerCompact(context = {}) {
        const ctx = getContext(context);
        const container = document.getElementById('dashboard-power-compact-grid');
        if (!container) return;
        const cabinets = Array.isArray(ctx.configData.cabinets) ? ctx.configData.cabinets : [];
        if (!cabinets.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置强电柜</div>';
            return;
        }
        container.classList.add('home-status-list');
        container.innerHTML = cabinets.map((cab, cabId) => {
            const status = ctx.powerStatusCache[cabId] || {};
            const online = !!(status.comm_status || status.online);
            const channels = Array.isArray(status.channels_1_4) ? status.channels_1_4.slice(0, Number(cab.channel_count || 8)) : [];
            const configuredChannels = Array.isArray(cab.channels_config) ? cab.channels_config.filter(ch => ch && ch.visible !== false).length : 0;
            const totalChannels = Number(status.channel_count || cab.channel_count || configuredChannels || channels.length || 0);
            const onCount = Number.isFinite(Number(status.channel_on_count))
                ? Number(status.channel_on_count)
                : channels.filter(item => item === true || item === 1 || item === '1').length;
            const powerValue = status.effective_realtime_power ?? status.stable_realtime_power ?? status.realtime_power;
            const temp = Number(status.cabinet_temp);
            const humi = Number(status.cabinet_humidity);
            const tempText = Number.isFinite(temp) || Number.isFinite(humi)
                ? `${Number.isFinite(temp) ? temp.toFixed(1) + '°C' : '--'} / ${Number.isFinite(humi) ? humi.toFixed(0) + '%' : '--'}`
                : '--';
            const modeText = sanitizeReadableText(status.work_mode, '模式未知');
            const configuredList = Array.isArray(cab.channels_config) ? cab.channels_config : [];
            const visibleChannels = configuredList
                .filter(ch => ch && ch.visible !== false)
                .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999));
            const fallbackChannels = Array.from({ length: Math.min(Number(cab.channel_count || totalChannels || channels.length || 8), 8) }, (_, idx) => ({ channel: idx + 1 }));
            const channelSource = (visibleChannels.length ? visibleChannels : fallbackChannels).slice(0, 8);
            const channelHtml = channelSource.map(ch => {
                const chNum = Number(ch.channel);
                const channelState = ctx.getPowerChannelStatus(cabId, chNum);
                const pending = !!(ctx.pwrPending[cabId] && ctx.pwrPending[cabId][chNum]);
                const unknown = channelState === null || channelState === undefined;
                const isOn = channelState === true || channelState === 1 || channelState === '1';
                const cls = pending ? 'pending' : (unknown ? 'unknown' : (isOn ? 'on' : 'off'));
                const stateText = pending ? '执行中' : (unknown ? '--' : (isOn ? '开' : '关'));
                const disabled = unknown ? 'disabled title="状态未知，暂不可操作"' : '';
                return `<button type="button" class="home-power-channel ${cls}${ctx.getPermissionDisabledClass('power.control')}" ${disabled || ctx.getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                    <span class="led"></span>${renderPowerChannelLabelHtml(cab, chNum, { compact: true })}<span class="state">${ctx.escapeHtml(stateText)}</span>
                </button>`;
            }).join('');
            return `<div class="home-status-row home-power-row ${online ? '' : 'offline'}">
                <div class="home-row-main">
                    <div class="home-row-title-line home-power-title-line"><strong class="home-row-name">${ctx.escapeHtml(getCabinetDisplayName(cab, cabId))}</strong><span class="home-mini-pill ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span></div>
                    <span>${ctx.escapeHtml(modeText)} · ${onCount}/${totalChannels || '--'} 路 · ${ctx.escapeHtml(tempText)}</span>
                </div>
                <div class="home-row-side home-power-side ${online ? 'ok' : 'bad'}">${formatHomeNumber(powerValue, 2, ' kW')}<br>${formatHomeNumber(status.daily_energy, 1, ' kWh')}</div>
                ${channelHtml ? `<div class="home-power-channel-strip">${channelHtml}</div>` : ''}
            </div>`;
        }).join('');
    }

    function renderMeterTrendChart(rows, context = {}) {
        const ctx = getContext(context);
        const dom = document.getElementById('meterTrendChart');
        if (!dom || !isChartElementRenderable(dom)) return;
        if (typeof global.echarts === 'undefined') {
            ensureEChartsRuntime('电表趋势图', ctx).then(() => renderMeterTrendChart(rows, ctx)).catch(() => {});
            return;
        }
        if (!state.charts.meterTrend) state.charts.meterTrend = global.echarts.init(dom);
        const safeRows = Array.isArray(rows) ? rows : [];
        const rowMap = new Map(safeRows.map(item => [String(item.period || item.date || ''), item]));
        let chartRows = safeRows;
        if (state.meterTrendPeriod === 'day') {
            const now = new Date();
            now.setHours(0, 0, 0, 0);
            chartRows = Array.from({ length: 35 }, (_, idx) => {
                const d = new Date(now);
                d.setDate(now.getDate() - 34 + idx);
                const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
                return rowMap.get(key) || { period: key, consume: 0, is_today: idx === 34 };
            });
        }
        const dates = chartRows.map(item => String(item.period || item.date || '')).filter(Boolean);
        const values = chartRows.map(item => {
            const value = Number(item.consume || 0);
            return Number.isFinite(value) ? Number(value.toFixed(2)) : 0;
        });
        const maxValue = Math.max(0, ...values);
        const axisKey = `${state.meterTrendTarget}:${state.meterTrendPeriod}`;
        const nextYMax = Math.max(10, Math.ceil(maxValue * 1.18 / 50) * 50);
        if (axisKey !== state.meterTrendAxisKey) {
            state.meterTrendAxisKey = axisKey;
            state.meterTrendYAxisMax = nextYMax;
        } else {
            state.meterTrendYAxisMax = Math.max(state.meterTrendYAxisMax || 0, nextYMax);
        }
        const yMax = state.meterTrendYAxisMax;
        const todayKey = (() => {
            const d = new Date();
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        })();
        const todayIndex = chartRows.findIndex(item => item && (item.is_today || String(item.period || item.date || '') === todayKey));
        const barData = values.map((value, index) => ({
            value,
            itemStyle: { color: index === todayIndex ? '#f59e0b' : '#3b82f6', borderRadius: [5, 5, 0, 0] },
            label: { color: index === todayIndex ? '#fde68a' : '#bfdbfe' }
        }));
        const optionSignature = JSON.stringify({ dates, values, todayIndex, yMax, target: state.meterTrendTarget, period: state.meterTrendPeriod });
        if (optionSignature === state.meterTrendOptionSignature) {
            state.charts.meterTrend.resize();
            return;
        }
        state.meterTrendOptionSignature = optionSignature;
        state.charts.meterTrend.setOption({
            animation: false,
            animationDuration: 0,
            animationDurationUpdate: 0,
            stateAnimation: { duration: 0 },
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'line', animation: false, lineStyle: { color: 'rgba(226,232,240,0.38)', width: 1 } },
                valueFormatter: value => `${Number(value || 0).toFixed(2)} kWh`
            },
            grid: { left: 18, right: 18, top: 34, bottom: 18, containLabel: true },
            xAxis: {
                type: 'category',
                data: dates,
                boundaryGap: true,
                axisLine: { lineStyle: { color: '#475569' } },
                axisTick: { show: false },
                axisLabel: { color: '#94a3b8', hideOverlap: true }
            },
            yAxis: {
                type: 'value',
                name: 'kWh',
                min: 0,
                max: yMax,
                interval: yMax <= 300 ? 50 : 100,
                nameTextStyle: { color: '#94a3b8' },
                splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } },
                axisLine: { show: false },
                axisTick: { show: false },
                axisLabel: { color: '#94a3b8' }
            },
            series: [
                {
                    name: '电量',
                    type: 'bar',
                    barMaxWidth: 24,
                    data: barData,
                    label: {
                        show: true,
                        position: 'top',
                        distance: 3,
                        formatter: params => Number(params.value || 0).toFixed(0),
                        fontSize: 9,
                        fontWeight: 800
                    },
                    emphasis: { disabled: true }
                },
                {
                    name: '连接线',
                    type: 'line',
                    data: values,
                    symbol: 'circle',
                    symbolSize: 5,
                    smooth: false,
                    z: 3,
                    lineStyle: { color: '#93c5fd', width: 2, opacity: 0.86 },
                    itemStyle: { color: '#e0f2fe', borderColor: '#1d4ed8', borderWidth: 1 },
                    label: { show: false },
                    emphasis: { disabled: true }
                }
            ]
        }, true);
        state.charts.meterTrend.resize();
    }

    function renderDashboardEnergyTrend(rows, summary = {}, context = {}) {
        const ctx = getContext(context);
        const dom = document.getElementById('dashboardEnergyTrendChart');
        const safeRows = Array.isArray(rows) ? rows : [];
        const values = safeRows.map(item => Number(item.consume || 0));
        const total = Number(summary.total_daily_energy ?? (state.meterCenterCache.dashboard_summary || {}).daily_energy ?? 0);
        const last = values.length ? values[values.length - 1] : total;
        const prev = values.length > 1 ? values[values.length - 2] : 0;
        const compare = prev > 0 ? `${(((last - prev) / prev) * 100).toFixed(1)}%` : '--%';
        ctx.setTextIfExists('dashboard-energy-total', `${total.toFixed(1)} kWh`);
        ctx.setTextIfExists('dashboard-energy-compare', compare);
        if (!dom || !isChartElementRenderable(dom)) return;
        if (typeof global.echarts === 'undefined') {
            ensureEChartsRuntime('首页能耗趋势图', ctx).then(() => renderDashboardEnergyTrend(rows, summary, ctx)).catch(() => {});
            return;
        }
        const labels = safeRows.map(item => String(item.period || item.date || '').slice(-5)).filter(Boolean);
        if (!state.charts.dashboardEnergyTrend) state.charts.dashboardEnergyTrend = global.echarts.init(dom);
        state.charts.dashboardEnergyTrend.setOption({
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis',
                formatter: params => {
                    const item = Array.isArray(params) ? params[0] : null;
                    if (!item) return '';
                    return `${ctx.escapeHtml(String(item.axisValue || '--'))}<br/>${Number(item.data || 0).toFixed(2)} kWh`;
                }
            },
            grid: { left: 34, right: 14, top: 18, bottom: 24 },
            xAxis: {
                type: 'category',
                data: labels,
                boundaryGap: false,
                axisLine: { lineStyle: { color: 'rgba(96,165,250,.28)' } },
                axisTick: { show: false },
                axisLabel: { color: '#8fb4de', fontSize: 10 }
            },
            yAxis: {
                type: 'value',
                axisLine: { show: false },
                axisTick: { show: false },
                axisLabel: { color: '#8fb4de', fontSize: 10 },
                splitLine: { lineStyle: { color: 'rgba(96,165,250,.10)' } }
            },
            series: [{
                type: 'line',
                smooth: true,
                symbol: 'none',
                data: values,
                lineStyle: { width: 2, color: '#2f8cff' },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(47,140,255,.42)' },
                            { offset: 1, color: 'rgba(47,140,255,.02)' }
                        ]
                    }
                }
            }]
        }, true);
        state.charts.dashboardEnergyTrend.resize();
    }

    function refreshPowerSupplement(cabId, force = false, context = {}) {
        const ctx = getContext(context);
        const now = Date.now();
        const activeView = ctx.getActiveViewId();
        const minInterval = activeView === 'power' ? 15000 : 45000;
        if (!force && state.powerSupplementFetchAt[cabId] && (now - state.powerSupplementFetchAt[cabId] < minInterval)) return Promise.resolve(null);
        if (state.powerSupplementInFlight[cabId]) return state.powerSupplementInFlight[cabId];
        state.powerSupplementFetchAt[cabId] = now;
        const logsReq = ctx.fetchJson(`/api/logs?cab=${cabId}`, {}, '强电日志读取失败')
            .then(logs => {
                state.powerLogCache[cabId] = Array.isArray(logs) ? logs : [];
                ctx.renderPowerDetailLogs(cabId, state.powerLogCache[cabId]);
            })
            .catch(err => console.error('强电日志更新失败', cabId, err));
        const historyReq = ctx.fetchJson(`/api/7days_energy?cab=${cabId}`, {}, '强电图表读取失败')
            .then(data => {
                state.powerHistoryCache[cabId] = Array.isArray(data) ? data : [];
                renderPowerEnergyChart(cabId, state.powerHistoryCache[cabId], ctx);
            })
            .catch(err => console.error('强电图表更新失败', cabId, err));
        state.powerSupplementInFlight[cabId] = Promise.allSettled([logsReq, historyReq])
            .then(() => renderDashboardPowerCards(ctx))
            .finally(() => {
                delete state.powerSupplementInFlight[cabId];
        });
        return state.powerSupplementInFlight[cabId];
    }

    function renderMeterCenterShell() {
        const container = document.getElementById('view-meter');
        if (!container || document.getElementById('meter-center-grid')) return false;
        container.innerHTML = `
            <div class="card" id="meter-center-shell">
                <div class="card-title">
                    <span>电表中心</span>
                    <span style="font-size:12px; color:var(--text-sub);">先统一接入现有 5 个电柜电表，后续可继续扩展独立电表、互感器电表和不同品牌协议</span>
                </div>
                <div class="meter-summary-grid">
                    <div class="meter-summary-card">
                        <div class="label">在线电表</div>
                        <div class="value"><span id="meter-summary-online">0</span> / <span id="meter-summary-total">0</span></div>
                        <div class="sub">当前纳入统一展示的电表总数</div>
                    </div>
                    <div class="meter-summary-card">
                        <div class="label">总实时功率</div>
                        <div class="value" style="color:var(--warning);" id="meter-summary-power">0.00</div>
                        <div class="sub">单位 kW</div>
                        <div class="meta" id="meter-summary-power-meta">卡片合计计算值</div>
                    </div>
                    <div class="meter-summary-card">
                        <div class="label">今日总用电</div>
                        <div class="value" style="color:var(--success);" id="meter-summary-daily">0.0</div>
                        <div class="sub">单位 kWh，按 0 点口径</div>
                        <div class="meta" id="meter-summary-daily-meta">参考总表 <strong>--</strong></div>
                    </div>
                    <div class="meter-summary-card">
                        <div class="label">本月总用电</div>
                        <div class="value" style="color:#93c5fd;" id="meter-summary-monthly">0.0</div>
                        <div class="sub">统一统计口径下的本月累计，单位 kWh</div>
                        <div class="meta" id="meter-summary-monthly-meta">参考总表 <strong>--</strong></div>
                    </div>
                </div>
                <div class="meter-summary-badgebar">
                    <span class="meter-summary-badge">显示口径 <strong id="meter-summary-badge-display">运行口径</strong></span>
                    <span class="meter-summary-badge">趋势目标 <strong id="meter-summary-badge-target">全部统计电表</strong></span>
                    <span class="meter-summary-badge">统计范围 <strong id="meter-summary-badge-scope">0 / 0 在线</strong></span>
                    <span class="meter-summary-badge">数据来源 <strong id="meter-summary-badge-source">电表服务</strong></span>
                </div>
                <div class="meter-type-chip-row" id="meter-type-chip-row">
                    <span class="meter-type-chip">正在统计电表型号...</span>
                </div>
                <div class="meter-center-grid" id="meter-center-grid" style="margin-top:16px;">
                    <div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">正在加载电表数据...</div>
                </div>
                <div class="meter-trend-layout">
                    <div class="meter-chart-shell">
                        <div class="card-title" style="border:none; padding:0 0 10px 0; margin:0;">
                            <span>电量趋势</span>
                            <span style="font-size:12px; color:var(--text-sub);">支持总表、区域、单表切换，并可按日/周/月查看</span>
                        </div>
                        <div class="meter-chart-toolbar">
                            <select id="meter-trend-target" onchange="changeMeterTrendTarget(this.value)" style="padding:8px 10px; border-radius:8px; background:#0f172a; color:#e2e8f0; border:1px solid rgba(148,163,184,0.24); min-width:240px;"></select>
                            <select id="meter-trend-period" onchange="changeMeterTrendPeriod(this.value)" style="padding:8px 10px; border-radius:8px; background:#0f172a; color:#e2e8f0; border:1px solid rgba(148,163,184,0.24); min-width:140px;">
                                <option value="day">按日</option>
                                <option value="week">按周</option>
                                <option value="month">按月</option>
                            </select>
                        </div>
                        <div class="meter-chart-box" id="meterTrendChart"></div>
                    </div>
                    <div class="meter-side-note">
                        <div class="meter-side-note-title">统计摘要</div>
                        <div class="meter-side-note-list">
                            <div class="meter-side-note-item">
                                <div class="label">当前目标</div>
                                <div class="value" id="meter-trend-target-label">全部统计电表</div>
                            </div>
                            <div class="meter-side-note-item">
                                <div class="label">趋势周期</div>
                                <div class="value" id="meter-trend-period-label">按日</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        return true;
    }

    function updateMeterCenter(context = {}, options = {}) {
        const ctx = getContext(context);
        renderMeterCenterShell();
        const requestSeq = ++state.meterCenterRequestSeq;
        const requestTarget = state.meterTrendTarget;
        const requestPeriod = state.meterTrendPeriod;
        const days = Number(options.days || 35) || 35;
        return ctx.fetchJson(`/api/meters?target=${encodeURIComponent(state.meterTrendTarget)}&period=${encodeURIComponent(state.meterTrendPeriod)}&days=${days}`, {}, '电表中心状态读取失败')
            .then(data => {
                if (requestSeq !== state.meterCenterRequestSeq || requestTarget !== state.meterTrendTarget || requestPeriod !== state.meterTrendPeriod) return null;
                state.meterCenterCache = data || { summary: {}, meters: [], trend: [] };
                const summary = state.meterCenterCache.summary || {};
                const meters = normalizeMeterCardOrder(Array.isArray(state.meterCenterCache.meters) ? state.meterCenterCache.meters : []);
                const grid = document.getElementById('meter-center-grid');
                const totalEl = document.getElementById('meter-summary-total');
                const onlineEl = document.getElementById('meter-summary-online');
                const powerEl = document.getElementById('meter-summary-power');
                const dailyEl = document.getElementById('meter-summary-daily');
                const monthlyEl = document.getElementById('meter-summary-monthly');
                const powerMetaEl = document.getElementById('meter-summary-power-meta');
                const dailyMetaEl = document.getElementById('meter-summary-daily-meta');
                const monthlyMetaEl = document.getElementById('meter-summary-monthly-meta');
                const displayBadge = document.getElementById('meter-summary-badge-display');
                const scopeBadge = document.getElementById('meter-summary-badge-scope');
                const sourceBadge = document.getElementById('meter-summary-badge-source');
                if (totalEl) totalEl.innerText = Number(summary.total || 0);
                if (onlineEl) onlineEl.innerText = Number(summary.online || 0);
                const cardTotalPower = Number(summary.card_total_realtime_power ?? summary.stable_total_realtime_power ?? summary.estimated_total_realtime_power ?? summary.total_realtime_power ?? 0);
                if (powerEl) powerEl.innerText = cardTotalPower.toFixed(2);
                if (dailyEl) dailyEl.innerText = Number(summary.total_daily_energy || 0).toFixed(1);
                if (monthlyEl) monthlyEl.innerText = Number(summary.total_monthly_energy || 0).toFixed(1) + ' kWh';
                if (displayBadge) {
                    const mode = String((ctx.configData.meter_statistics || {}).energy_display_mode || 'display').toLowerCase();
                    displayBadge.innerText = mode === 'raw' ? '原始累计值' : '运行口径';
                }
                if (scopeBadge) scopeBadge.innerText = `${Number(summary.online || 0)} / ${Number(summary.total || 0)} 在线`;
                if (sourceBadge) {
                    const sourceMeta = resolveMeterSourceMeta(state.meterCenterCache);
                    sourceBadge.innerText = sourceMeta.text;
                    sourceBadge.title = sourceMeta.title || '';
                    sourceBadge.style.color = sourceMeta.color || '#f8fafc';
                }
                const dashPower = document.getElementById('dash-total-power');
                const dashDaily = document.getElementById('dash-total-daily-energy');
                const dashPowerMeta = document.getElementById('dash-total-power-meta');
                const dashDailyMeta = document.getElementById('dash-total-daily-meta');
                const dashStablePower = Number((state.meterCenterCache.dashboard_summary || {}).stable_power ?? (state.meterCenterCache.dashboard_summary || {}).estimated_power ?? (state.meterCenterCache.dashboard_summary || {}).power ?? cardTotalPower ?? 0);
                if (dashPower) dashPower.innerText = dashStablePower.toFixed(2);
                if (dashDaily) dashDaily.innerText = Number((state.meterCenterCache.dashboard_summary || {}).daily_energy || summary.total_daily_energy || 0).toFixed(1);
                const compareToReference = (summary.compare_to_reference || {});
                if (powerMetaEl) powerMetaEl.innerHTML = formatPowerSummaryMeta(summary);
                if (dailyMetaEl) dailyMetaEl.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                if (monthlyMetaEl) monthlyMetaEl.innerHTML = formatReferenceMeta(compareToReference.monthly_energy, ' kWh');
                if (dashPowerMeta) dashPowerMeta.innerHTML = `单位 kW · ${formatPowerSummaryMeta(summary)}`;
                if (dashDailyMeta) dashDailyMeta.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                renderMeterTypeChips(summary.type_counts || {});
                renderMeterTrendSelectors(state.meterCenterCache);
                if (grid) {
                    grid.innerHTML = meters.length
                        ? meters.map(renderMeterCard).join('')
                        : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">暂无可展示电表数据</div>';
                }
                const trendRows = (((state.meterCenterCache.trend_breakdown || {})[state.meterTrendPeriod === 'week' ? 'weekly' : (state.meterTrendPeriod === 'month' ? 'monthly' : 'daily')]) || []);
                renderMeterTrendChart(trendRows, ctx);
                renderDashboardEnergyTrend(trendRows, summary, ctx);
                return state.meterCenterCache;
            })
            .catch(err => {
                console.error('电表中心状态更新失败', err);
                return null;
            });
    }

    async function updatePowerData(context = {}) {
        const ctx = getContext(context);
        if (state.powerFetchInFlight) return state.powerFetchInFlight;
        state.powerFetchInFlight = (async () => {
            let onlineCount = 0;
            const activeView = ctx.getActiveViewId();
            const shouldLoadDetails = activeView === 'power';
            const shouldLoadDashboard = activeView === 'dashboard' || ctx.isDashboardSectionVisible('power_compact') || ctx.isDashboardSectionVisible('power_quick');
            const supplementCabIds = ctx.resolveVisiblePowerSupplementCabIds(activeView);
            const supplementCabIdSet = new Set(supplementCabIds);
            const cabinetEntries = Array.isArray(ctx.configData.cabinets) ? Array.from(ctx.configData.cabinets.entries()) : [];
            const responses = [];
            for (const [cabId] of cabinetEntries) {
                try {
                    const data = await ctx.fetchJson(`/api/status?cab=${cabId}`, {}, '强电状态读取失败');
                    responses.push({ cabId, data, error: null });
                } catch (err) {
                    responses.push({ cabId, data: null, error: err });
                }
            }
            for (const [cabId, cab] of cabinetEntries) {
                const result = responses.find(item => item.cabId === cabId) || {};
                const data = result.data;
                if (!data) {
                    console.error('强电状态更新失败', cabId, result.error);
                    continue;
                }
                try {
                    ctx.applyPowerStatusSnapshot(cabId, data);
                    if (data.comm_status) onlineCount++;
                    const statusEl = document.getElementById(`commStatus_${cabId}`);
                    if (statusEl) {
                        statusEl.className = data.comm_status ? 'tag normal' : 'tag error';
                        statusEl.innerText = data.comm_status ? '通讯正常' : '通讯异常';
                    }
                    const wm = document.getElementById(`workMode_${cabId}`);
                    if (wm) wm.innerText = data.work_mode || '未知';
                    const sourceLabelEl = document.getElementById(`sourceLabel_${cabId}`);
                    if (sourceLabelEl) sourceLabelEl.innerText = data.source_label || (data.data_source || '电表服务');
                    const displayAddressEl = document.getElementById(`displayAddress_${cabId}`);
                    if (displayAddressEl) displayAddressEl.innerText = data.display_address || data.gateway_base || `${cab.ip}:${cab.port}`;
                    const deviceAddressEl = document.getElementById(`deviceAddress_${cabId}`);
                    if (deviceAddressEl) deviceAddressEl.innerText = data.device_address || `${cab.ip}:${cab.port}`;
                    ['va', 'vb', 'vc', 'ia', 'ib', 'ic', 'energy', 'dailyEnergy', 'monthEnergy', 'realtimePower', 'temp', 'humi'].forEach(key => {
                        const el = document.getElementById(`${key}_${cabId}`);
                        const val = data[key === 'energy'
                            ? 'electric_energy'
                            : (key === 'dailyEnergy'
                                ? 'daily_energy'
                                : (key === 'monthEnergy'
                                    ? 'monthly_energy'
                                    : (key === 'realtimePower'
                                        ? 'realtime_power'
                                        : (key === 'temp'
                                            ? 'cabinet_temp'
                                            : (key === 'humi'
                                                ? 'cabinet_humidity'
                                                : key.replace('v', 'voltage_').replace('i', 'current_'))))))];
                        if (el && val !== undefined) {
                            el.innerText = parseFloat(val).toFixed(key.includes('i') || key.includes('v') || key === 'temp' || key === 'humi' || key.includes('Energy') ? 1 : 2);
                        }
                    });
                } catch (err) {
                    console.error('强电状态更新失败', cabId, err);
                }
            }
            const supplementChanged = supplementCabIds.length !== state.powerVisibleSupplementCabIds.length
                || supplementCabIds.some((cabId, idx) => cabId !== state.powerVisibleSupplementCabIds[idx]);
            if (shouldLoadDetails || shouldLoadDashboard) {
                for (const cabId of supplementCabIds) refreshPowerSupplement(cabId, supplementChanged, ctx);
            }
            for (const oldCabId of state.powerVisibleSupplementCabIds) {
                if (!supplementCabIdSet.has(oldCabId)) delete state.powerSupplementInFlight[oldCabId];
            }
            state.powerVisibleSupplementCabIds = supplementCabIds.slice();
            renderDashboardPowerCards(ctx);
            renderDashboardPowerCompact(ctx);
            const pOnline = document.getElementById('dash-power-online');
            if (pOnline) pOnline.innerText = onlineCount;
            resizePowerCharts(ctx);
        })();
        try {
            return await state.powerFetchInFlight;
        } finally {
            state.powerFetchInFlight = null;
        }
    }

    function changeMeterTrendTarget(target, context = {}) {
        state.meterTrendTarget = target || 'total';
        return updateMeterCenter(context);
    }

    function changeMeterTrendPeriod(period, context = {}) {
        state.meterTrendPeriod = period || 'day';
        return updateMeterCenter(context);
    }

    const api = {
        isChartElementRenderable,
        ensureEChartsRuntime,
        ensurePowerChart,
        resizePowerCharts,
        renderPowerEnergyChart,
        renderDashboardPowerCards,
        renderDashboardPowerCompact,
        renderMeterTrendChart,
        renderDashboardEnergyTrend,
        renderMeterCenterShell,
        refreshPowerSupplement,
        updateMeterCenter,
        updatePowerData,
        changeMeterTrendTarget,
        changeMeterTrendPeriod,
    };

    Object.assign(state, api);
    Object.assign(global, api);

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('power-meter-runtime', {
            kind: 'runtime',
            exports: Object.keys(api),
            source: 'static/js/views/power-meter-runtime.js',
            risk: 'medium-high',
        });
    }
})(window);
