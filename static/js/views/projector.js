// AI_MODULE: projector_view_helpers
// AI_PURPOSE: 投影机页面通用格式化、指令归一化和推断状态辅助函数。
// AI_BOUNDARY: 不直接下发投影机控制；真实控制仍由 templates/index.html 的 fireProjectorCommand 走 /api/projector/control。
// AI_DATA_FLOW: config.projectors + /api/projector/status 缓存 -> 投影机卡片/遥控器渲染辅助。
// AI_RUNTIME: 首页和投影机页面同步加载，保持旧全局函数名以兼容内联 onclick。
// AI_RISK: 高，函数被真实投影机控制 UI 使用；修改时必须保持 payload、权限和回读逻辑不变。
// AI_SEARCH_KEYWORDS: projector, pjlink, rs232, inferred, current collector, projector gateway.

(function installSmartCenterProjectorHelpers(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};

    const defaultProjectorStatus = {
        online: false,
        power: 'unknown',
        temp: null,
        temp_status: null,
        lamp_hours: null,
        lamp_state: null,
        filter_hours: null,
        lamp_model: null,
        filter_model: null,
        source: null,
        source_code: null,
        source_name: null,
        av_mute: null,
        freeze_status: null,
        input_list: [],
        input_list_labels: [],
        input_resolution: null,
        recommended_resolution: null,
        error: null,
        error_code: null,
        error_details: null,
        device_name: null,
        manufacturer: null,
        product_name: null,
        class_version: null,
        serial_number: null,
        software_version: null,
    };

    const projectorCommandNameFallbacks = {
        smile: {
            ek: {
                power_on: '开机',
                power_off: '关机',
                source_pc: '切换到 PC',
                source_vga: '切换到 VGA',
                source_dvi: '切换到 DVI',
                source_hdmi1: '切换到 HDMI1',
                source_hdmi2: '切换到 HDMI2',
                source_dp: '切换到 DP',
                mute_on: '静音黑屏开启',
                mute_off: '静音黑屏关闭',
                freeze_on: '冻结画面开启',
                freeze_off: '冻结画面关闭',
                volume_up: '音量加',
                volume_down: '音量减',
                menu_on: '打开菜单',
                menu_off: '关闭菜单',
                key_up: '方向上',
                key_down: '方向下',
                key_left: '方向左',
                key_right: '方向右',
                key_enter: '确认',
                key_exit: '返回',
                auto_adjust: '自动调整',
                lamp_eco: '灯泡节能模式',
                lamp_normal: '灯泡标准模式',
                power_status: '查询开关机状态',
                source_status: '查询信号源',
                volume_status: '查询音量',
                mute_status: '查询静音黑屏状态',
                temp_status: '查询温度状态',
                lamp_status: '查询灯泡状态',
            },
        },
    };

    function getContext(context = {}) {
        const provider = typeof global.getProjectorViewContext === 'function'
            ? (global.getProjectorViewContext() || {})
            : {};
        return Object.assign({
            projectorConfigs: [],
            statusCache: {},
            escapeHtml: utils.escapeHtml || global.escapeHtml || (value => String(value ?? '')),
        }, provider, context || {});
    }

    function looksLikeGarbledText(value) {
        const text = String(value ?? '').trim();
        if (!text) return true;
        return ['?', '锛', '馃', '篇胆赤', '狼双', '高桁', '寮€', '闂'].some(token => text.includes(token));
    }

    function normalizeProjectorCommand(proj, cmd) {
        const normalized = { ...(cmd || {}) };
        const brandId = String(proj?.brand_id || '').trim();
        const seriesId = String(proj?.series_id || '').trim();
        const fallbackName = projectorCommandNameFallbacks?.[brandId]?.[seriesId]?.[normalized.id];
        if (fallbackName && looksLikeGarbledText(normalized.name)) normalized.name = fallbackName;
        if (looksLikeGarbledText(normalized.icon)) normalized.icon = '';
        return normalized;
    }

    function getProjectorById(projId, context = {}) {
        const ctx = getContext(context);
        return (ctx.projectorConfigs || []).find(item => String(item.id) === String(projId));
    }

    function getProjectorCommands(proj) {
        return (proj?.commands || [])
            .filter(cmd => cmd && cmd.visible !== false)
            .map(cmd => normalizeProjectorCommand(proj, cmd))
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

    function formatProjectorMuteText(status = {}) {
        return status.av_mute || '未获取';
    }

    function formatProjectorManufacturerText(proj = {}, status = {}) {
        return proj.fixed_manufacturer || status.manufacturer || '--';
    }

    function formatProjectorSoftwareText(proj = {}, status = {}) {
        return proj.fixed_software_version || status.software_version || '--';
    }

    function formatProjectorErrorText(status = {}) {
        const raw = status.error || '正常';
        if (raw === '正常' || raw === '预警' || raw === '故障') return raw;
        if (String(raw).includes('WinError 10061')) return '连接被拒绝';
        if (String(raw).includes('timed out')) return '连接超时';
        return String(raw).length > 18 ? `${String(raw).slice(0, 18)}...` : raw;
    }

    function formatProjectorClassText(proj = {}, status = {}) {
        if (status.class_version) return `Class ${status.class_version}（设备实测）`;
        if (proj.control_type === 'pjlink' && proj.pjlink_version) return `Class ${proj.pjlink_version}（配置值）`;
        return '--';
    }

    function formatProjectorProtocolText(proj = {}, status = {}) {
        const controlType = String(proj.control_type || '');
        if (controlType === 'pjlink') {
            return status.class_version ? `PJLink Class ${status.class_version}` : (proj.pjlink_version ? `PJLink ${proj.pjlink_version}.0` : 'PJLink');
        }
        if (controlType.startsWith('smile_ek') || controlType === 'rs232') {
            return controlType.includes('_com') || controlType === 'rs232' ? '视美乐专用协议 / RS232' : '视美乐专用协议 / TCP';
        }
        if (controlType.startsWith('appotronics_')) {
            return '厂商专用协议';
        }
        return proj.pjlink_version ? `PJLink ${proj.pjlink_version}.0` : '--';
    }

    function getProjectorPowerText(powerStatus) {
        if (powerStatus === 'on') return '开机';
        if (powerStatus === 'off') return '关机';
        if (powerStatus === 'cooling') return '冷却中';
        if (powerStatus === 'warming') return '启动中';
        if (powerStatus === 'warning') return '告警';
        return '未知';
    }

    function getProjectorPowerColor(powerStatus) {
        if (powerStatus === 'on') return 'var(--success)';
        if (powerStatus === 'off') return 'var(--danger)';
        if (powerStatus === 'cooling' || powerStatus === 'warming' || powerStatus === 'warning') return 'var(--warning)';
        return '#94a3b8';
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

    function getProjectorButtonHint(cmd) {
        const name = String(cmd?.name || '');
        if (name.includes('查询')) return '点击查询设备状态';
        if (name.includes('切换')) return '点击执行切换';
        if (name.includes('开启')) return '点击开启功能';
        if (name.includes('关闭')) return '点击关闭功能';
        if (name.includes('开机')) return '点击下发开机';
        if (name.includes('关机')) return '点击下发关机';
        return '点击执行指令';
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

    function groupProjectorCommands(proj) {
        const groups = { power: [], input: [], av: [], info: [], other: [] };
        getProjectorCommands(proj).forEach(cmd => {
            const id = String(cmd.id || '');
            const name = String(cmd.name || '');
            if (id.includes('power') || name.includes('开机') || name.includes('关机') || name.includes('电源')) groups.power.push(cmd);
            else if (id.includes('input') || name.includes('信号源') || name.includes('切换')) groups.input.push(cmd);
            else if (id.includes('mute') || id.includes('freeze') || name.includes('静音') || name.includes('冻结')) groups.av.push(cmd);
            else if (name.includes('查询') || id.includes('status') || id.includes('info') || id.includes('name') || id.includes('manufacturer') || id.includes('product') || id.includes('lamp') || id.includes('error')) groups.info.push(cmd);
            else groups.other.push(cmd);
        });
        return groups;
    }

    function renderProjectorCommandButtons(commands, projId, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const getPermissionDisabledClass = ctx.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => '');
        const getPermissionDisabledAttrs = ctx.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => '');
        if (!commands.length) return '<div class="projector-empty-tip">当前分组没有可用指令。</div>';
        return `<div class="projector-remote-grid">${commands.map(cmd => `
            <button class="projector-command-btn${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} onclick="fireProjectorCommand('${escapeHtml(projId)}', '${escapeHtml(cmd.payload || '')}', '${escapeHtml(cmd.format || 'str')}')">
                <span class="name">${escapeHtml(cmd.name || cmd.id || '未命名指令')}</span>
                <span class="hint">${escapeHtml(getProjectorButtonHint(cmd))}</span>
            </button>`).join('')}</div>`;
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

    function getDashboardProjectors(context = {}) {
        const ctx = getContext(context);
        return (ctx.projectorConfigs || []).filter(proj => proj.visible !== false && proj.dashboard_visible !== false);
    }

    function formatProjectorKw(value) {
        if (value === null || value === undefined || value === '') return '--';
        const n = Number(value);
        if (!Number.isFinite(n)) return '--';
        return `${n.toFixed(2)} kW`;
    }

    function formatProjectorSignedKw(value) {
        if (value === null || value === undefined || value === '') return '--';
        const n = Number(value);
        if (!Number.isFinite(n)) return '--';
        return `${n >= 0 ? '+' : ''}${n.toFixed(2)} kW`;
    }

    function formatInferredFeedText(status) {
        if (status?.power_feed_on === true) return '供电合闸';
        if (status?.power_feed_on === false) return '供电断开';
        return '供电未知';
    }

    function formatInferredZoneFeedText(zone) {
        if (zone?.power_feed_on === true) return '供电合闸';
        if (zone?.power_feed_on === false) return '供电断开';
        return '供电未知';
    }

    function formatProjectorAmp(value) {
        if (value === null || value === undefined || value === '') return '--';
        const n = Number(value);
        if (!Number.isFinite(n)) return '--';
        return `${n.toFixed(2)} A`;
    }

    function renderInferredTargetSummary(status) {
        const targets = Array.isArray(status?.inferred_targets) ? status.inferred_targets : [];
        if (!targets.length) return '--';
        return targets.map((target) => `${target.name || target.ip || '控制点'}${target.online ? '在线' : '离线'}`).join(' / ');
    }

    function renderInferredEvidenceSummary(status) {
        const rows = Array.isArray(status?.inferred_evidence) ? status.inferred_evidence : (Array.isArray(status?.inferred_zones) ? status.inferred_zones : []);
        if (!rows.length) return formatInferredFeedText(status);
        return rows.map(row => `${row.name || row.id || '证据'} ${formatProjectorAmp(row.current_total_a)}`).join(' / ');
    }

    function renderInferredEvidenceCards(status, compact = false, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const zones = Array.isArray(status?.inferred_evidence) ? status.inferred_evidence : (Array.isArray(status?.inferred_zones) ? status.inferred_zones : []);
        if (!zones.length) return '<div class="projector-zone-empty">未配置投影推断证据</div>';
        return `<div class="projector-zone-grid ${compact ? 'compact' : ''}">${zones.map(zone => {
            const powerStatus = zone.power || 'unknown';
            const currentText = formatProjectorAmp(zone.current_total_a);
            const deltaText = zone.current_delta_a === null || zone.current_delta_a === undefined ? '--' : `${Number(zone.current_delta_a) >= 0 ? '+' : ''}${Number(zone.current_delta_a).toFixed(2)} A`;
            const feedText = formatInferredZoneFeedText(zone);
            const cabinetText = zone.cabinet_channel ? `电柜${zone.cabinet_channel}路` : '电柜未绑定';
            const currentChannels = Array.isArray(zone.current_channels) ? zone.current_channels : [];
            const currentChannelText = currentChannels.length ? currentChannels.map(ch => ch.name || `第${ch.channel}路`).join(' / ') : '电流未绑定';
            const targetText = Number(zone.target_total_count || 0) ? `${zone.target_online_count || 0}/${zone.target_total_count || 0} 在线` : '串口未绑定';
            return `<div class="projector-zone-card ${powerStatus} ${zone.status_level === 'stale' ? 'stale' : ''}">
                <div class="projector-zone-head">
                    <div class="projector-zone-name">${escapeHtml(zone.name || zone.id || '判定证据')}</div>
                    <span class="projector-zone-state">${escapeHtml(deltaText)}</span>
                </div>
                <div class="projector-zone-current">${escapeHtml(currentText)}</div>
                <div class="projector-zone-meta"><span>${escapeHtml(feedText)}</span><span>${escapeHtml(cabinetText)}</span><span>${escapeHtml(targetText)}</span></div>
                <div class="projector-zone-source" title="${escapeHtml(currentChannelText)}">${escapeHtml(currentChannelText)}</div>
            </div>`;
        }).join('')}</div>`;
    }

    function resolveStatusMeta(status, options, context) {
        const ctx = getContext(context);
        const fn = ctx.getDeviceStatusMeta || global.getDeviceStatusMeta;
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
        const fn = ctx.getCardStateClass || global.getCardStateClass;
        return typeof fn === 'function' ? fn(statusMeta) : '';
    }

    function renderInferredProjectorPowerActions(proj, powerOnCmd, powerOffCmd, compact = false, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const getPermissionDisabledClass = ctx.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => '');
        const getPermissionDisabledAttrs = ctx.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => '');
        const disabledClass = getPermissionDisabledClass('projector.control');
        const disabledAttrs = getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限');
        const buttonClass = compact ? 'projector-inline-power-btn compact' : 'projector-inline-power-btn';
        if (!powerOnCmd && !powerOffCmd) {
            return `<button class="projector-inline-power-btn muted ${compact ? 'compact' : ''}" type="button" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">遥控器</button>`;
        }
        return `
            <div class="projector-inline-power-actions ${compact ? 'compact' : ''}">
                ${powerOnCmd ? `<button class="${buttonClass} on${disabledClass}" ${disabledAttrs} type="button" title="通过121投影网关开机" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOnCmd.payload || '')}', '${escapeHtml(powerOnCmd.format || 'str')}', '${escapeHtml(powerOnCmd.name || '开机')}')">开机</button>` : ''}
                ${powerOffCmd ? `<button class="${buttonClass} off${disabledClass}" ${disabledAttrs} type="button" title="通过121投影网关关机" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOffCmd.payload || '')}', '${escapeHtml(powerOffCmd.format || 'str')}', '${escapeHtml(powerOffCmd.name || '关机')}')">关机</button>` : ''}
            </div>`;
    }

    function renderInferredProjectorCard(proj, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const status = getProjectorStatus(proj.id, ctx);
        const statusMeta = resolveStatusMeta(status, { staleText: '待确认', errorText: '异常' }, ctx);
        const isOnline = statusMeta.isOnlineLike;
        const powerStatus = status.power || 'unknown';
        const powerText = getProjectorPowerText(powerStatus);
        const powerColor = getProjectorPowerColor(powerStatus);
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const targetTotal = Number(status.target_total_count ?? 0);
        const targetOnline = Number(status.target_online_count ?? 0);
        const targetSummary = targetTotal ? `${targetOnline}/${targetTotal} 在线` : '未配置目标';
        const projectorNote = status.inference_basis || status.status_note || statusMeta.note;
        const lastIntentText = status.last_intent === 'on' ? '最近开机' : (status.last_intent === 'off' ? '最近关机' : '无指令记录');
        const gatewayText = status.last_command_source ? '121网关' : '串口 + 电流采集';
        const collectorText = status.current_collector_online ? `在线 ${String(status.current_collector_updated_at || '').replace('T', ' ').slice(11, 19)}` : (status.current_collector_error || '离线');
        const zones = Array.isArray(status.inferred_evidence) ? status.inferred_evidence : (Array.isArray(status.inferred_zones) ? status.inferred_zones : []);
        const abZone = zones.find(zone => /AB|A\s*B|一号厅|1号厅/i.test(String(zone.name || zone.id || ''))) || zones[0] || {};
        const immersionZone = zones.find(zone => /沉浸/i.test(String(zone.name || zone.id || ''))) || zones[1] || {};
        const abCurrent = formatProjectorAmp(abZone.current_total_a);
        const immersionCurrent = formatProjectorAmp(immersionZone.current_total_a);
        const feedText = formatInferredFeedText(status);
        return `
            <div class="projector-card inferred-projector-card ${isOnline ? 'online' : 'offline'} ${resolveCardStateClass(statusMeta, ctx)}">
                <div class="projector-card-top">
                    <div>
                        <div class="projector-card-title">${escapeHtml(proj.name || proj.id)}</div>
                        <div class="projector-card-subtitle">整体组控 · ${escapeHtml(targetSummary)}</div>
                    </div>
                    <button class="projector-entry-btn" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                </div>
                <div class="projector-status-inline">
                    <div class="projector-status-left">
                        <span class="projector-dot ${statusMeta.chipClass === 'online' ? 'online' : ''} ${statusMeta.chipClass === 'warning' ? 'warning' : ''}"></span>
                        <span>${escapeHtml(statusMeta.text)}</span>
                        <span>·</span>
                        <span style="color:${powerColor}; font-weight:700;">总体 ${escapeHtml(powerText)}</span>
                    </div>
                    <div class="projector-status-actions">
                        ${renderInferredProjectorPowerActions(proj, powerOnCmd, powerOffCmd, false, ctx)}
                    </div>
                </div>
                <div class="projector-meta-grid inferred-projector-meta">
                    <div class="projector-meta-item"><div class="projector-meta-label">AB厅电流</div><div class="projector-meta-value">${escapeHtml(abCurrent)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">沉浸厅电流</div><div class="projector-meta-value">${escapeHtml(immersionCurrent)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">供电状态</div><div class="projector-meta-value">${escapeHtml(feedText)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">推断状态</div><div class="projector-meta-value" style="color:${powerColor};">${escapeHtml(powerText)}</div></div>
                </div>
                <div class="projector-extra-row">
                    <div class="projector-extra-chip"><div class="label">控制记录</div><div class="value">${escapeHtml(lastIntentText)}</div></div>
                    <div class="projector-extra-chip"><div class="label">状态来源</div><div class="value">${escapeHtml(gatewayText)}</div></div>
                    <div class="projector-extra-chip"><div class="label">电流采集器</div><div class="value">${escapeHtml(collectorText)}</div></div>
                </div>
                <div class="dashboard-mini-note projector-card-note" title="${escapeHtml(renderInferredEvidenceSummary(status))}">${escapeHtml(projectorNote)}</div>
            </div>`;
    }

    function renderCompactInferredProjectorCard(proj, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const getPermissionDisabledClass = ctx.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => '');
        const getPermissionDisabledAttrs = ctx.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => '');
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
        return `<div class="dashboard-mini-card projector-compact-card ${resolveCardStateClass(statusMeta, ctx)}">
            <div class="dashboard-mini-projector-head">
                <div class="dashboard-mini-projector-title" style="min-width:0;">
                    <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                    <div class="dashboard-mini-subtitle">${escapeHtml(targetSummary)} · ${escapeHtml(statusMeta.text)}</div>
                </div>
                <div class="dashboard-mini-projector-controls">
                    <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}', '${escapeHtml(powerButtonCmd.name || '')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                </div>
            </div>
            <div class="dashboard-mini-note" title="${escapeHtml(evidenceSummary)}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(evidenceSummary)}</div>
            <div class="dashboard-mini-note" title="${escapeHtml(noteText)}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(noteText)}</div>
        </div>`;
    }

    function renderProjectorCard(proj, scope, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const status = getProjectorStatus(proj.id, ctx);
        if (isInferredProjector(proj, status)) return renderInferredProjectorCard(proj, ctx);
        const statusMeta = resolveStatusMeta(status, { staleText: '陈旧', errorText: '异常' }, ctx);
        const isOnline = statusMeta.isOnlineLike;
        const powerStatus = status.power || 'unknown';
        const powerText = getProjectorPowerText(powerStatus);
        const powerColor = getProjectorPowerColor(powerStatus);
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
        const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
        const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
        const modelText = formatProjectorModelText(proj, status);
        const manufacturerText = formatProjectorManufacturerText(proj, status);
        const softwareText = formatProjectorSoftwareText(proj, status);
        const sourceText = formatProjectorSourceText(status);
        const lampText = status.lamp_hours !== null && status.lamp_hours !== undefined ? `${status.lamp_hours} h` : '--';
        const errorText = formatProjectorErrorText(status);
        const tempDisplayText = status.temp !== null && status.temp !== undefined ? `${status.temp}°C` : (status.temp_status || '--');
        const tempLabel = status.temp !== null && status.temp !== undefined ? '温度' : '温度状态';
        const tempColor = status.temp !== null && status.temp !== undefined ? (status.temp > 60 ? 'var(--danger)' : 'var(--text-main)') : (status.temp_status === '故障' ? 'var(--danger)' : (status.temp_status === '预警' ? 'var(--warning)' : 'var(--text-main)'));
        const onlineText = statusMeta.text;
        const lampStateText = status.lamp_state || '--';
        const supportText = Array.isArray(status.input_list_labels) && status.input_list_labels.length ? status.input_list_labels.join(' / ') : (Array.isArray(status.input_list) && status.input_list.length ? status.input_list.join(' / ') : '--');
        const supportCountText = Array.isArray(status.input_list_labels) && status.input_list_labels.length ? `${status.input_list_labels.length} 路` : (Array.isArray(status.input_list) && status.input_list.length ? `${status.input_list.length} 路` : '--');
        const classVersionText = formatProjectorClassText(proj, status);
        const errorDetailLabels = { fan: '风扇', lamp: '灯泡', temperature: '温度', cover: '机盖', filter: '滤网', other: '其他' };
        const alertChips = Object.entries(status.error_details || {}).filter(([, value]) => value === '预警' || value === '故障').map(([key, value]) => {
            const chipClass = value === '故障' ? 'error' : 'warning';
            const label = errorDetailLabels[key] || key;
            return `<span class="projector-alert-chip ${chipClass}">${escapeHtml(label)}${escapeHtml(value)}</span>`;
        }).join('');
        return `
            <div class="projector-card ${isOnline ? 'online' : 'offline'} ${resolveCardStateClass(statusMeta, ctx)}">
                <div class="projector-card-top">
                    <div>
                        <div class="projector-card-title">${escapeHtml(proj.name || proj.id)}</div>
                        <div class="projector-card-subtitle">${escapeHtml(proj.ip || '--')}:${escapeHtml(proj.port || '--')} · ${escapeHtml(modelText)}</div>
                    </div>
                    <button class="projector-entry-btn" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                </div>
                <div class="projector-status-inline">
                    <div class="projector-status-left">
                        <span class="projector-dot ${statusMeta.chipClass === 'online' ? 'online' : ''} ${statusMeta.chipClass === 'warning' ? 'warning' : ''}"></span>
                        <span>${onlineText}</span>
                        <span>·</span>
                        <span style="color:${powerColor}; font-weight:700;">电源 ${powerText}</span>
                    </div>
                    <div class="projector-status-actions">
                        ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}" title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                    </div>
                </div>
                <div class="projector-meta-grid">
                    <div class="projector-meta-item"><div class="projector-meta-label">当前信号源</div><div class="projector-meta-value">${escapeHtml(sourceText)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">灯泡时长</div><div class="projector-meta-value">${escapeHtml(lampText)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">${tempLabel}</div><div class="projector-meta-value" style="color:${tempColor}">${escapeHtml(tempDisplayText)}</div></div>
                    <div class="projector-meta-item"><div class="projector-meta-label">故障总览</div><div class="projector-meta-value" style="color:${errorText === '正常' ? 'var(--success)' : 'var(--warning)'}">${escapeHtml(errorText)}</div></div>
                </div>
                <div class="projector-extra-row">
                    <div class="projector-extra-chip"><div class="label">厂家信息</div><div class="value">${escapeHtml(manufacturerText)}</div></div>
                    <div class="projector-extra-chip"><div class="label">协议等级</div><div class="value">${escapeHtml(classVersionText)}</div></div>
                    <div class="projector-extra-chip"><div class="label">软件版本</div><div class="value">${escapeHtml(softwareText)}</div></div>
                </div>
                <div class="dashboard-mini-note">${escapeHtml(statusMeta.note)}</div>
                ${alertChips ? `<div class="projector-alert-list">${alertChips}</div>` : ''}
                <div class="projector-card-footer">
                    <div class="projector-footer-chip"><div class="label">静音状态</div><div class="value">${escapeHtml(formatProjectorMuteText(status))}</div></div>
                    <div class="projector-footer-chip"><div class="label">灯泡状态</div><div class="value">${escapeHtml(lampStateText)}</div></div>
                    <div class="projector-footer-chip"><div class="label">支持输入</div><div class="value" title="${escapeHtml(supportText)}">${escapeHtml(supportCountText)}</div></div>
                </div>
            </div>`;
    }

    function renderCompactProjectorCard(proj, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const getPermissionDisabledClass = ctx.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => '');
        const getPermissionDisabledAttrs = ctx.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => '');
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
        return `<div class="dashboard-mini-card projector-compact-card ${resolveCardStateClass(statusMeta, ctx)}">
            <div class="dashboard-mini-projector-head">
                <div class="dashboard-mini-projector-title">
                    <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                    <div class="dashboard-mini-subtitle">${escapeHtml(proj.ip || '--')}:${escapeHtml(proj.port || '--')}</div>
                </div>
                <div class="dashboard-mini-projector-controls">
                    <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                </div>
            </div>
            <div class="dashboard-mini-light-summary">
                <div class="dashboard-mini-light-count">${escapeHtml(powerText)}</div>
                <div class="dashboard-mini-chip-row"><span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span></div>
            </div>
            <div class="dashboard-mini-note">更新 ${escapeHtml(status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--:--:--')}</div>
        </div>`;
    }

    function renderProjectorMiniCard(proj, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const getPermissionDisabledClass = ctx.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => '');
        const getPermissionDisabledAttrs = ctx.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => '');
        const status = getProjectorStatus(proj.id, ctx);
        const statusMeta = resolveStatusMeta(status, { staleText: '陈旧', errorText: '异常' }, ctx);
        const isOnline = statusMeta.isOnlineLike;
        const powerStatus = status.power || 'unknown';
        const powerText = getProjectorPowerText(powerStatus);
        const powerColor = getProjectorPowerColor(powerStatus);
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
        const powerButtonClass = (powerStatus === 'on' || powerStatus === 'warming') ? 'off' : 'on';
        const powerButtonText = (powerStatus === 'on' || powerStatus === 'warming') ? '关机' : '开机';
        const statusClass = !isOnline ? 'offline' : (statusMeta.chipClass === 'warning' ? 'warning' : 'online');
        let subtitle = '';
        let metrics = [];
        if (isInferredProjector(proj, status)) {
            const zones = Array.isArray(status.inferred_evidence) ? status.inferred_evidence : (Array.isArray(status.inferred_zones) ? status.inferred_zones : []);
            const abZone = zones.find(zone => /AB|A\s*B|一号厅|1号厅/i.test(String(zone.name || zone.id || ''))) || zones[0] || {};
            const immersionZone = zones.find(zone => /沉浸/i.test(String(zone.name || zone.id || ''))) || zones[1] || {};
            subtitle = `整体组控 · ${Number(status.target_online_count || 0)}/${Number(status.target_total_count || 0)} 在线`;
            metrics = [
                ['AB厅电流', formatProjectorAmp(abZone.current_total_a)],
                ['沉浸厅电流', formatProjectorAmp(immersionZone.current_total_a)],
                ['供电', formatInferredFeedText(status)],
                ['来源', status.source === 'node-red' ? 'Node-RED' : (status.last_command_source ? '121网关' : '推断')],
            ];
        } else {
            subtitle = `${proj.ip || '--'}:${proj.port || '--'} · ${formatProjectorModelText(proj, status)}`;
            metrics = [
                ['信号', formatProjectorSourceText(status)],
                ['灯时', status.lamp_hours !== null && status.lamp_hours !== undefined ? `${status.lamp_hours} h` : '--'],
                ['温度', status.temp !== null && status.temp !== undefined ? `${status.temp}°C` : (status.temp_status || '--')],
                ['输入', Array.isArray(status.input_list_labels) && status.input_list_labels.length ? `${status.input_list_labels.length} 路` : '--'],
            ];
        }
        return `<div class="projector-mini-card ${statusClass}">
            <div class="projector-mini-head">
                <div style="min-width:0;">
                    <div class="projector-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                    <div class="projector-mini-subtitle">${escapeHtml(subtitle)}</div>
                </div>
                <span class="projector-mini-status">${escapeHtml(statusMeta.text)}</span>
            </div>
            <div class="projector-mini-primary">
                <div class="label">核心状态</div>
                <div class="value" style="color:${powerColor};">${escapeHtml(powerText)}</div>
            </div>
            <div class="projector-mini-metrics">
                ${metrics.map(([label, value]) => `<div class="projector-mini-metric"><div class="label">${escapeHtml(label)}</div><div class="value" title="${escapeHtml(value)}">${escapeHtml(value)}</div></div>`).join('')}
            </div>
            <div class="projector-mini-actions">
                <button class="projector-mini-btn detail" type="button" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">遥控</button>
                ${powerButtonCmd ? `<button class="projector-mini-btn ${powerButtonClass}${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} type="button" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}', '${escapeHtml(powerButtonCmd.name || powerButtonText)}')">${powerButtonText}</button>` : ''}
            </div>
        </div>`;
    }

    function renderProjectorCards(targetId, scope, context = {}) {
        const ctx = getContext(context);
        const container = global.document ? document.getElementById(targetId) : null;
        if (!container) return;
        const visibleProjectors = scope === 'dashboard' ? getDashboardProjectors(ctx) : (ctx.projectorConfigs || []);
        if (!visibleProjectors.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置投影机，请前往系统配置添加。</div>';
            return;
        }
        container.innerHTML = visibleProjectors.map(proj => scope === 'dashboard' ? renderCompactProjectorCard(proj, ctx) : renderProjectorMiniCard(proj, ctx)).join('');
    }

    function renderProjectorRemote(projId, context = {}) {
        const ctx = getContext(context);
        const escapeHtml = ctx.escapeHtml;
        const proj = getProjectorById(projId, ctx);
        const content = global.document ? document.getElementById('projectorRemoteContent') : null;
        if (!proj || !content) return;
        const status = getProjectorStatus(proj.id, ctx);
        const groups = groupProjectorCommands(proj);
        const powerStatus = status.power || 'unknown';
        const manufacturerText = formatProjectorManufacturerText(proj, status);
        const softwareText = formatProjectorSoftwareText(proj, status);
        const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
        const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
        const errorDetails = status.error_details || {};
        const errorDetailItems = [
            { key: 'fan', label: '风扇' },
            { key: 'lamp', label: '灯泡' },
            { key: 'temperature', label: '温度' },
            { key: 'cover', label: '机盖' },
            { key: 'filter', label: '滤网' },
            { key: 'other', label: '其他' },
        ];
        const errorDetailsHtml = errorDetailItems.map(item => {
            const value = errorDetails[item.key] || '--';
            const color = value === '故障' ? 'var(--danger)' : (value === '预警' ? 'var(--warning)' : 'var(--text-main)');
            return `<div class="projector-remote-tile"><div class="label">${item.label}状态</div><div class="value" style="color:${color}">${escapeHtml(value)}</div></div>`;
        }).join('');
        const class2InfoHtml = [
            { label: '设备名称', value: status.device_name || '--' },
            { label: '厂商名称', value: status.manufacturer || '--' },
            { label: '产品型号', value: status.product_name || '--' },
            { label: '输入名称', value: formatProjectorSourceText(status) },
            { label: '当前分辨率', value: status.input_resolution || '--' },
            { label: '推荐分辨率', value: status.recommended_resolution && status.recommended_resolution !== 'NA' ? status.recommended_resolution : '不适用' },
            { label: '滤网时长', value: status.filter_hours !== null && status.filter_hours !== undefined ? `${status.filter_hours} h` : '--' },
            { label: '灯泡型号', value: status.lamp_model || '--' },
            { label: '滤网型号', value: status.filter_model || '--' },
            { label: '冻结状态', value: status.freeze_status || '--' },
            { label: '序列号', value: status.serial_number || '--' },
            { label: '软件版本', value: status.software_version || '--' },
        ].map(item => `<div class="projector-remote-tile"><div class="label">${item.label}</div><div class="value">${escapeHtml(item.value)}</div></div>`).join('');
        const titleEl = document.getElementById('projectorRemoteTitle');
        const subtitleEl = document.getElementById('projectorRemoteSubtitle');
        if (titleEl) titleEl.innerText = `${proj.name || proj.id} 遥控器`;
        if (subtitleEl) subtitleEl.innerText = `${proj.ip || '--'}:${proj.port || '--'} · ${formatProjectorModelText(proj, status)}`;
        content.innerHTML = `
            <div class="projector-remote-side">
                <div class="projector-remote-overview">
                    <div class="projector-remote-tile"><div class="label">在线状态</div><div class="value" style="color:${status.online ? 'var(--success)' : 'var(--text-sub)'}">${status.online ? '在线' : '离线'}</div></div>
                    <div class="projector-remote-tile"><div class="label">电源状态</div><div class="value" style="color:${getProjectorPowerColor(powerStatus)}">${getProjectorPowerText(powerStatus)}</div></div>
                    <div class="projector-remote-tile"><div class="label">信号源</div><div class="value">${escapeHtml(formatProjectorSourceText(status))}</div></div>
                    <div class="projector-remote-tile"><div class="label">静音/黑屏</div><div class="value">${escapeHtml(formatProjectorMuteText(status))}</div></div>
                    <div class="projector-remote-tile"><div class="label">灯泡时长</div><div class="value">${escapeHtml(status.lamp_hours !== null && status.lamp_hours !== undefined ? status.lamp_hours + ' h' : '--')}</div></div>
                    <div class="projector-remote-tile"><div class="label">灯泡状态</div><div class="value">${escapeHtml(status.lamp_state || '--')}</div></div>
                    <div class="projector-remote-tile"><div class="label">${status.temp !== null && status.temp !== undefined ? '温度' : '温度状态'}</div><div class="value" style="color:${status.temp !== null && status.temp !== undefined ? (status.temp > 60 ? 'var(--danger)' : 'var(--text-main)') : (status.temp_status === '故障' ? 'var(--danger)' : (status.temp_status === '预警' ? 'var(--warning)' : 'var(--text-main)'))}">${escapeHtml(status.temp !== null && status.temp !== undefined ? (status.temp + '°C') : (status.temp_status || '--'))}</div></div>
                    <div class="projector-remote-tile"><div class="label">故障总览</div><div class="value" style="color:${status.error && status.error !== '正常' ? 'var(--warning)' : 'var(--success)'}">${escapeHtml(status.error || '正常')}</div></div>
                    ${status.error_code ? `<div class="projector-remote-tile"><div class="label">ERST 原始码</div><div class="value">${escapeHtml(status.error_code)}</div></div>` : ''}
                    <div class="projector-remote-tile"><div class="label">厂商 / 协议</div><div class="value">${escapeHtml(manufacturerText + ' / ' + formatProjectorProtocolText(proj, status))}</div></div>
                    <div class="projector-remote-tile"><div class="label">PJLink 等级</div><div class="value">${escapeHtml(formatProjectorClassText(proj, status))}</div></div>
                    ${status.other_info ? `<div class="projector-remote-tile"><div class="label">附加信息</div><div class="value">${escapeHtml(status.other_info)}</div></div>` : ''}
                    <div class="projector-remote-tile"><div class="label">支持输入</div><div class="value">${escapeHtml(Array.isArray(status.input_list_labels) && status.input_list_labels.length ? status.input_list_labels.join(' / ') : (Array.isArray(status.input_list) && status.input_list.length ? status.input_list.join(' / ') : '--'))}</div></div>
                    <div class="projector-remote-tile"><div class="label">软件版本</div><div class="value">${escapeHtml(softwareText)}</div></div>
                </div>
                <div class="projector-remote-hero-actions">
                    ${powerOnCmd ? `<button class="projector-power-btn on" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOnCmd.payload || '')}', '${escapeHtml(powerOnCmd.format || 'str')}')">开机</button>` : ''}
                    ${powerOffCmd ? `<button class="projector-power-btn off" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOffCmd.payload || '')}', '${escapeHtml(powerOffCmd.format || 'str')}')">关机</button>` : ''}
                </div>
            </div>
            <div class="projector-remote-main">
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>电源与基础控制</span><span class="projector-remote-section-note">常用开关机、状态查询</span></div>
                    ${renderProjectorCommandButtons(groups.power, proj.id, ctx)}
                </div>
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>信号源切换</span><span class="projector-remote-section-note">HDMI、RGB、VIDEO 等输入选择</span></div>
                    ${renderProjectorCommandButtons(groups.input, proj.id, ctx)}
                </div>
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>画面与音视频控制</span><span class="projector-remote-section-note">静音黑屏、冻结等控制</span></div>
                    ${renderProjectorCommandButtons(groups.av, proj.id, ctx)}
                </div>
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>信息与状态查询</span><span class="projector-remote-section-note">查询设备名称、故障、灯泡、协议信息</span></div>
                    ${renderProjectorCommandButtons(groups.info, proj.id, ctx)}
                </div>
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>故障明细</span><span class="projector-remote-section-note">PJLink ERST 六项状态拆解</span></div>
                    <div class="projector-remote-grid">${errorDetailsHtml}</div>
                </div>
                <div class="projector-remote-section">
                    <div class="projector-remote-section-title"><span>PJLink Class 2 信息</span><span class="projector-remote-section-note">分辨率、滤网、型号、版本等扩展信息</span></div>
                    <div class="projector-remote-grid">${class2InfoHtml}</div>
                </div>
                <div class="projector-remote-section" style="margin-bottom:0;">
                    <div class="projector-remote-section-title"><span>其它指令</span><span class="projector-remote-section-note">保留扩展控制命令</span></div>
                    ${renderProjectorCommandButtons(groups.other, proj.id, ctx)}
                </div>
            </div>`;
    }

    const api = {
        looksLikeGarbledText,
        normalizeProjectorCommand,
        getProjectorById,
        getProjectorCommands,
        findProjectorCommand,
        getProjectorStatus,
        formatProjectorSourceText,
        formatProjectorModelText,
        formatProjectorMuteText,
        formatProjectorManufacturerText,
        formatProjectorSoftwareText,
        formatProjectorErrorText,
        formatProjectorClassText,
        formatProjectorProtocolText,
        getProjectorPowerText,
        getProjectorPowerColor,
        getProjectorPowerButtonClass,
        getProjectorPowerButtonTitle,
        getProjectorButtonHint,
        getProjectorIconHtml,
        groupProjectorCommands,
        renderProjectorCommandButtons,
        isInferredProjector,
        getDashboardProjectors,
        formatProjectorKw,
        formatProjectorSignedKw,
        formatInferredFeedText,
        formatInferredZoneFeedText,
        formatProjectorAmp,
        renderInferredTargetSummary,
        renderInferredEvidenceSummary,
        renderInferredEvidenceCards,
        renderInferredProjectorPowerActions,
        renderInferredProjectorCard,
        renderCompactInferredProjectorCard,
        renderProjectorCard,
        renderCompactProjectorCard,
        renderProjectorMiniCard,
        renderProjectorCards,
        renderProjectorRemote,
    };

    SmartCenter.projector = Object.assign({}, SmartCenter.projector || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('projector-view', {
            version: '20260530-inline-phase2',
            helpers: Object.keys(api),
            risk: 'high',
        });
    }
    Object.assign(global, api);
})(window);
