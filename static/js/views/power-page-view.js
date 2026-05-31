// AI_MODULE: power_page_view
// AI_PURPOSE: 按需生成强电控制页电柜卡片，替代 templates/index.html 的 Jinja 电柜循环。
// AI_BOUNDARY: 只生成 DOM 和旧 ID；真实强电控制仍走 app-runtime.js 的 doPowerStart/doPowerStop/togglePower。
// AI_DATA_FLOW: window.configData.cabinets -> power 页面 DOM -> power-meter-runtime 状态回写。
// AI_RUNTIME: 进入 power 视图或强电轮询需要页面节点时懒加载。
// AI_RISK: 高，生成的按钮会触发真实强电控制，必须保持 cabId/channel/payload 兼容。
// AI_SEARCH_KEYWORDS: power page, cabinet card, template slim, strong current.

(function installSmartCenterPowerPageView(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const helper = SmartCenter.powerMeter || {};
    const state = SmartCenter.powerPageView = Object.assign({
        rendered: false,
    }, SmartCenter.powerPageView || {});

    function escapeHtml(value) {
        if (typeof utils.escapeHtml === 'function') return utils.escapeHtml(value);
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function jsArg(value) {
        return escapeHtml(JSON.stringify(String(value ?? '')));
    }

    function config() {
        return global.configData && typeof global.configData === 'object' ? global.configData : {};
    }

    function bySort(a = {}, b = {}) {
        return Number(a.sort ?? 9999) - Number(b.sort ?? 9999);
    }

    function getCabinetName(cab, cabId) {
        if (helper && typeof helper.getCabinetDisplayName === 'function') return helper.getCabinetDisplayName(cab, cabId);
        return cab?.cabinet_name || cab?.meter_display_name || `电柜 ${Number(cabId) + 1}`;
    }

    function renderChannelButton(cabId, cab, channel = {}) {
        const chNum = Number(channel.channel || 0);
        if (!chNum) return '';
        const span = Math.max(1, Math.min(4, Number(channel.span || 1)));
        const name = String(channel.name || cab?.ui_text?.label_channel || '通道') + (channel.name ? '' : chNum);
        const remark = String(channel.remark || '').trim();
        return `<button class="ch-btn power-channel-btn ch-err ch-span-${span}" id="pch_${cabId}_${chNum}" onclick="togglePower(${cabId}, ${chNum})">
            <span class="name" title="${escapeHtml(remark ? `${name} / ${remark}` : name)}">${escapeHtml(name)}</span>
            ${remark ? `<span class="remark" title="${escapeHtml(remark)}">${escapeHtml(remark)}</span>` : ''}
            <span class="state state-pill">离线</span>
        </button>`;
    }

    function renderChannelGrid(cabId, cab) {
        const channels = (Array.isArray(cab?.channels_config) ? cab.channels_config : [])
            .filter(ch => ch && ch.visible !== false)
            .sort(bySort)
            .map(ch => renderChannelButton(cabId, cab, ch))
            .join('');
        return channels || '<div style="color:var(--text-sub); grid-column:1/-1;">未配置可见回路</div>';
    }

    function endpointText(cab) {
        const ip = String(cab?.ip || '').trim();
        const port = cab?.port === undefined || cab?.port === null || cab?.port === '' ? '' : `:${cab.port}`;
        return `${ip}${port}` || '--';
    }

    function renderCabinetCard(cab, cabId) {
        const confirmStop = String(cab?.ui_text?.confirm_stop || '确定要停止该电柜所有通道吗？');
        return `<div class="card">
            <div class="cab-header">
                <h3>${escapeHtml(getCabinetName(cab, cabId))}</h3>
                <span class="tag error" id="commStatus_${cabId}">检测中</span>
            </div>
            <div class="info-bar">
                <div>模式:<span class="tag info" id="workMode_${cabId}" style="margin-left:8px;">未知</span></div>
                <div>协议:<span>${escapeHtml(cab?.plc_type || '--')}</span></div>
                <div>站号:<span>${escapeHtml(cab?.station_id ?? '--')}</span></div>
                <div>来源:<span id="sourceLabel_${cabId}">电表服务</span></div>
                <div>通讯:<span id="displayAddress_${cabId}">${escapeHtml(endpointText(cab))}</span></div>
                <div>设备:<span id="deviceAddress_${cabId}">${escapeHtml(endpointText(cab))}</span></div>
            </div>
            <div class="btn-group">
                <button class="btn-base btn-start" onclick="doPowerStart(${cabId})">一键启动</button>
                <button class="btn-base btn-stop" onclick="doPowerStop(${cabId}, ${jsArg(confirmStop)})">一键停止</button>
                <button class="btn-base" style="background:#2563eb;" onclick="exportEnergyHistory()">导出30天电量</button>
            </div>
            <div class="panel-grid">
                <div class="left-col">
                    <div class="param-box">
                        <div style="color:var(--text-sub); margin-bottom:10px; font-weight:bold;">三相电实时参数</div>
                        <div class="param-row"><span>A 相</span><span class="val"><span id="va_${cabId}">0.0</span> V / <span id="ia_${cabId}">0.0</span> A</span></div>
                        <div class="param-row"><span>B 相</span><span class="val"><span id="vb_${cabId}">0.0</span> V / <span id="ib_${cabId}">0.0</span> A</span></div>
                        <div class="param-row"><span>C 相</span><span class="val"><span id="vc_${cabId}">0.0</span> V / <span id="ic_${cabId}">0.0</span> A</span></div>
                    </div>
                    <div class="param-box">
                        <div style="color:var(--text-sub); margin-bottom:10px; font-weight:bold;">用电统计与环境</div>
                        <div class="param-row"><span>累计电能</span><span class="val"><span id="energy_${cabId}">0.0</span> kWh</span></div>
                        <div class="param-row"><span>今日用电</span><span class="val" style="color:var(--success);"><span id="dailyEnergy_${cabId}">0.0</span> kWh</span></div>
                        <div class="param-row"><span>本月用电</span><span class="val" style="color:var(--brand-blue);"><span id="monthEnergy_${cabId}">0.0</span> kWh</span></div>
                        <div class="param-row" style="margin-top:15px; border-top:1px dashed rgba(255,255,255,0.1); padding-top:10px;">
                            <span>实时功率</span><span class="val highlight"><span id="realtimePower_${cabId}">0.00</span> kW</span>
                        </div>
                        <div class="param-row" style="margin-top:10px;"><span>温度/湿度</span><span class="val"><span id="temp_${cabId}">0.0</span> °C / <span id="humi_${cabId}">0.0</span>%</span></div>
                    </div>
                </div>
                <div class="center-col">
                    <div class="channel-grid" id="channels_${cabId}">
                        ${renderChannelGrid(cabId, cab)}
                    </div>
                    <div class="chart-box" id="energyChart_${cabId}"></div>
                </div>
                <div class="right-col">
                    <div style="color:var(--text-sub); margin-bottom:10px; font-weight:bold;">电柜操作日志</div>
                    <div class="log-list" id="logs_${cabId}"></div>
                </div>
            </div>
        </div>`;
    }

    function renderPowerPage(force = false) {
        if (state.rendered && !force) return;
        const container = document.getElementById('power-page-grid');
        if (!container) return;
        const cabinets = Array.isArray(config().cabinets) ? config().cabinets : [];
        container.innerHTML = cabinets.length
            ? cabinets.map((cab, cabId) => renderCabinetCard(cab, cabId)).join('')
            : '<div class="card"><div style="color:var(--text-sub); text-align:center; padding:20px;">未配置强电柜</div></div>';
        state.rendered = true;
    }

    const api = { renderPowerPage };
    Object.assign(state, api);

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('power-page-view', {
            kind: 'view-renderer',
            exports: Object.keys(api),
            source: 'static/js/views/power-page-view.js',
        });
    }

    global.renderPowerPage = renderPowerPage;
})(window);
