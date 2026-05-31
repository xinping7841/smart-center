// AI_MODULE: projector_summary_view
// AI_PURPOSE: 首页投影机摘要轻量渲染，避免 dashboard 首屏加载完整 projector.js。
// AI_BOUNDARY: 只渲染首页紧凑卡片和开关快捷按钮；遥控器/详情页由 projector.js 负责。
// AI_DATA_FLOW: /api/projector/status + configData.projectors -> dashboard-projector-grid DOM。
// AI_RUNTIME: 首页按需加载；打开遥控器或进入投影机页面时再加载完整模块。
// AI_RISK: 中，首页仍保留投影开关按钮，必须继续走 fireProjectorCommand 权限链路。
// AI_SEARCH_KEYWORDS: projector summary, dashboard projector, lightweight projector.

(function installSmartCenterProjectorSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.projectorSummary = Object.assign({}, SmartCenter.projectorSummary || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));

    const defaultProjectorStatus = {
        online: false,
        power: 'unknown',
        source: '',
        source_name: '',
        lamp_hours: null,
        temp: null,
        temp_status: '',
        updated_at: '',
    };

    function getContext(context = {}) {
        const provider = typeof global.getProjectorViewContext === 'function'
            ? (global.getProjectorViewContext() || {})
            : {};
        return Object.assign({
            projectorConfigs: [],
            statusCache: {},
            escapeHtml,
        }, provider, context || {});
    }

    function getProjectorCommands(proj) {
        return (proj?.commands || [])
            .filter(cmd => cmd && cmd.visible !== false)
            .sort((a, b) => (a.sort ?? 999) - (b.sort ?? 999));
    }

    function findProjectorCommand(proj, ids, keywords = []) {
        const commands = getProjectorCommands(proj);
        return commands.find(cmd => ids.includes(cmd.id))
            || commands.find(cmd => keywords.some(keyword => String(cmd.name || '').includes(keyword)));
    }

    function getProjectorStatus(projId, context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.getStatus === 'function') return ctx.getStatus(projId) || { ...defaultProjectorStatus };
        return (ctx.statusCache || {})[projId] || { ...defaultProjectorStatus };
    }

    function getDashboardProjectors(context = {}) {
        const ctx = getContext(context);
        return (ctx.projectorConfigs || []).filter(proj => proj.visible !== false && proj.dashboard_visible !== false);
    }

    function resolveStatusMeta(status, options, context) {
        const ctx = getContext(context);
        const fn = ctx.getDeviceStatusMeta || global.getDeviceStatusMeta || utils.getDeviceStatusMeta;
        if (typeof fn === 'function') return fn(status, options || {});
        const online = !!status?.online;
        return {
            text: online ? '在线' : '离线',
            chipClass: online ? 'online' : 'offline',
            level: online ? 'online' : 'error',
            isOnlineLike: online,
            note: '',
        };
    }

    function resolveCardStateClass(statusMeta, context) {
        const ctx = getContext(context);
        const fn = ctx.getCardStateClass || global.getCardStateClass || utils.getCardStateClass;
        return typeof fn === 'function' ? fn(statusMeta) : '';
    }

    function formatProjectorSourceText(status = {}) {
        if (status.source_name) return status.source_name;
        if (status.source && status.source !== '查询不支持') return status.source;
        if (status.source === '查询不支持') return '当前源查询不支持';
        if (Array.isArray(status.input_list_labels) && status.input_list_labels.length) return `支持 ${status.input_list_labels.length} 路输入`;
        if (Array.isArray(status.input_list) && status.input_list.length) return `支持 ${status.input_list.length} 路输入`;
        return '未获取';
    }

    function formatProjectorModelText(proj = {}, status = {}) {
        return proj.fixed_model
            || status.product_name
            || status.device_name
            || (status.manufacturer && status.class_version ? `${status.manufacturer} / PJLink Class ${status.class_version}` : null)
            || status.manufacturer
            || proj.series_name
            || proj.model
            || '未识别型号';
    }

    function getProjectorPowerText(powerStatus) {
        if (powerStatus === 'on') return '开机';
        if (powerStatus === 'off') return '关机';
        if (powerStatus === 'cooling') return '冷却中';
        if (powerStatus === 'warming') return '启动中';
        if (powerStatus === 'warning') return '告警';
        return '未知';
    }

    function getProjectorPowerButtonClass(isOnline, powerStatus) {
        if (!isOnline || powerStatus === 'unknown') return 'unknown';
        if (powerStatus === 'off') return 'off';
        if (powerStatus === 'cooling' || powerStatus === 'warming' || powerStatus === 'warning') return 'unknown';
        return 'on';
    }

    function getProjectorPowerButtonTitle(isOnline, powerStatus) {
        if (!isOnline) return '设备离线';
        if (powerStatus === 'on' || powerStatus === 'warming') return '当前开机，点击关机';
        if (powerStatus === 'off' || powerStatus === 'cooling') return '当前关机，点击开机';
        return '打开遥控器或刷新状态';
    }

    function getProjectorIconHtml(kind) {
        const icon = String(kind || '').trim().toLowerCase();
        if (icon === 'power') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 4.2v7.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
                <path d="M7.4 6.5A8 8 0 1 0 16.6 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
            </svg>`;
        }
        return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="4" y="5" width="16" height="14" rx="2.5" stroke="currentColor" stroke-width="1.9"/>
            <path d="M8.5 9h7M8.5 12h7M8.5 15h7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
        </svg>`;
    }

    function isInferredProjector(proj, status) {
        const id = String(proj?.id || '').toLowerCase();
        const controlType = String(proj?.control_type || '').toLowerCase();
        const type = String(proj?.type || proj?.kind || proj?.status_type || '').toLowerCase();
        const classVersion = String(status?.class_version || '').toLowerCase();
        return controlType === 'inferred_rs232'
            || id.includes('infer')
            || type.includes('infer')
            || status?.inferred === true
            || classVersion.includes('状态推断')
            || status?.current_collector_online !== undefined
            || Array.isArray(status?.inferred_evidence)
            || Array.isArray(status?.inferred_zones);
    }

    function formatProjectorAmp(value) {
        if (value === null || value === undefined || value === '') return '--';
        const n = Number(value);
        if (!Number.isFinite(n)) return '--';
        return `${n.toFixed(2)} A`;
    }

    function formatInferredFeedText(status) {
        if (status?.power_feed_on === true) return '供电合闸';
        if (status?.power_feed_on === false) return '供电断开';
        return '供电未知';
    }

    function renderInferredEvidenceSummary(status) {
        const rows = Array.isArray(status?.inferred_evidence) ? status.inferred_evidence : (Array.isArray(status?.inferred_zones) ? status.inferred_zones : []);
        if (!rows.length) return formatInferredFeedText(status);
        return rows.map(row => `${row.name || row.id || '证据'} ${formatProjectorAmp(row.current_total_a)}`).join(' / ');
    }

    function renderCompactInferredProjectorCard(proj, context = {}) {
        const ctx = getContext(context);
        const status = getProjectorStatus(proj.id, ctx);
        const statusMeta = resolveStatusMeta(status, { staleText: '待确认', errorText: '异常' }, ctx);
        const isOnline = statusMeta.isOnlineLike;
        const powerStatus = status.power || 'unknown';
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
        const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
        const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
        const targetTotal = Number(status.target_total_count ?? 0);
        const targetOnline = Number(status.target_online_count ?? 0);
        const targetSummary = targetTotal ? `串口 ${targetOnline}/${targetTotal}` : '串口未配置';
        const evidenceSummary = renderInferredEvidenceSummary(status);
        const noteText = status.inference_basis || status.status_note || statusMeta.note;
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('projector.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限') : '';
        return `<div class="dashboard-mini-card projector-compact-card ${resolveCardStateClass(statusMeta, ctx)}">
            <div class="dashboard-mini-projector-head">
                <div class="dashboard-mini-projector-title" style="min-width:0;">
                    <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                    <div class="dashboard-mini-subtitle">${escapeHtml(targetSummary)} · ${escapeHtml(statusMeta.text)}</div>
                </div>
                <div class="dashboard-mini-projector-controls">
                    <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${disabledClass}" ${disabledAttrs} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}', '${escapeHtml(powerButtonCmd.name || '')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                </div>
            </div>
            <div class="dashboard-mini-note" title="${escapeHtml(evidenceSummary)}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(evidenceSummary)}</div>
            <div class="dashboard-mini-note" title="${escapeHtml(noteText)}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(noteText)}</div>
        </div>`;
    }

    function renderCompactProjectorCard(proj, context = {}) {
        const ctx = getContext(context);
        const status = getProjectorStatus(proj.id, ctx);
        if (isInferredProjector(proj, status)) return renderCompactInferredProjectorCard(proj, ctx);
        const statusMeta = resolveStatusMeta(status, { staleText: '陈旧', errorText: '异常' }, ctx);
        const isOnline = statusMeta.isOnlineLike;
        const powerStatus = status.power || 'unknown';
        const powerText = getProjectorPowerText(powerStatus);
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
        const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
        const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('projector.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限') : '';
        return `<div class="dashboard-mini-card projector-compact-card ${resolveCardStateClass(statusMeta, ctx)}">
            <div class="dashboard-mini-projector-head">
                <div class="dashboard-mini-projector-title">
                    <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                    <div class="dashboard-mini-subtitle">${escapeHtml(proj.ip || '--')}:${escapeHtml(proj.port || '--')} · ${escapeHtml(formatProjectorModelText(proj, status))}</div>
                </div>
                <div class="dashboard-mini-projector-controls">
                    <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${disabledClass}" ${disabledAttrs} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                </div>
            </div>
            <div class="dashboard-mini-light-summary">
                <div class="dashboard-mini-light-count">${escapeHtml(powerText)}</div>
                <div class="dashboard-mini-chip-row"><span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span></div>
            </div>
            <div class="dashboard-mini-note">${escapeHtml(formatProjectorSourceText(status))} · 更新 ${escapeHtml(status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--:--:--')}</div>
        </div>`;
    }

    function renderProjectorCards(targetId, scope, context = {}) {
        const ctx = getContext(context);
        const container = global.document ? document.getElementById(targetId) : null;
        if (!container) return;
        if (scope !== 'dashboard') {
            if (SmartCenter.projector?.renderProjectorCards && SmartCenter.projector !== state) {
                SmartCenter.projector.renderProjectorCards(targetId, scope, ctx);
            }
            return;
        }
        const visibleProjectors = getDashboardProjectors(ctx);
        if (!visibleProjectors.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置投影机，请前往系统配置添加。</div>';
            return;
        }
        container.innerHTML = visibleProjectors.map(proj => renderCompactProjectorCard(proj, ctx)).join('');
    }

    const api = {
        getProjectorCommands,
        findProjectorCommand,
        getProjectorStatus,
        getDashboardProjectors,
        formatProjectorSourceText,
        formatProjectorModelText,
        getProjectorPowerText,
        getProjectorPowerButtonClass,
        getProjectorPowerButtonTitle,
        getProjectorIconHtml,
        isInferredProjector,
        formatProjectorAmp,
        formatInferredFeedText,
        renderInferredEvidenceSummary,
        renderCompactInferredProjectorCard,
        renderCompactProjectorCard,
        renderProjectorCards,
    };

    Object.assign(state, api);
    Object.assign(global, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.projector-summary', {
            kind: 'dashboard-summary',
            exports: Object.keys(api),
            source: 'static/js/views/projector-summary.js',
        });
    }
})(window);
