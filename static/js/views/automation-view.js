// AI_MODULE: automation_view
// AI_PURPOSE: 自动化运行页面、规则卡片、条件气泡、节点画布、执行日志展示。
// AI_BOUNDARY: 不在前端做最终触发决策；真实条件求值和执行在 runtime/automation.py。
// AI_DATA_FLOW: /api/automation/status/logs -> 自动化卡片/节点画布 DOM。
// AI_RUNTIME: 自动化页面轮询；画布支持缩放、居中和拖动。
// AI_RISK: 高，展示错误会让用户误判自动化是否会触发真实设备动作。
// AI_SEARCH_KEYWORDS: automation, node canvas, condition bubble, trigger, scene.

(function installSmartCenterAutomationView(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.automationView = Object.assign({}, SmartCenter.automationView || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));
    const formatRelativeSeconds = utils.formatRelativeSeconds || global.formatRelativeSeconds || (seconds => `${Number(seconds || 0).toFixed(0)}秒`);
    const getAutomationTodayKey = utils.getAutomationTodayKey || global.getAutomationTodayKey || (() => new Date().toISOString().slice(0, 10));
    const getAutomationDayLabel = utils.getAutomationDayLabel || global.getAutomationDayLabel || (() => '每天');
    const getAutomationSourceLabel = utils.getAutomationSourceLabel || global.getAutomationSourceLabel || (value => value || '数据源');
    const getAutomationPropLabel = utils.getAutomationPropLabel || global.getAutomationPropLabel || (value => value || '属性');
    const formatAutomationValue = utils.formatAutomationValue || global.formatAutomationValue || (value => (value === undefined || value === null || value === '' ? '--' : String(value)));
    const formatAutomationValueWithUnit = utils.formatAutomationValueWithUnit || global.formatAutomationValueWithUnit || ((value, _prop) => formatAutomationValue(value));
    const formatAutomationRuleTime = utils.formatAutomationRuleTime || global.formatAutomationRuleTime || (value => value || '未触发');

    let automationGroupSignature = '';
    let activeAutomationCanvasRuleId = '';
    let activeAutomationCanvasNodeId = '';
    let automationCanvasZoom = 1;
    let automationCanvasPanX = 0;
    let automationCanvasPanY = 0;
    let automationCanvasBaseX = 28;
    let automationCanvasBaseY = 0;
    let automationCanvasDragState = null;
    let automationCanvasSuppressClickUntil = 0;

    function getContext(maybeContext) {
        return maybeContext && typeof maybeContext === 'object' ? maybeContext : {};
    }

    function isAutomationScheduleDoneToday(rule) {
        const state = rule?.state || {};
        const today = getAutomationTodayKey();
        return String(state.last_schedule_day || '') === today || String(state.last_schedule_key || '').startsWith(today);
    }
    function isAutomationScheduleStateDoneToday(triggerState = {}) {
        const today = getAutomationTodayKey();
        return String(triggerState.last_schedule_day || '') === today || String(triggerState.last_schedule_key || '').startsWith(today);
    }
    function findAutomationScene(sceneId, context = {}) {
        const { configData = global.configData || {} } = getContext(context);
        const id = String(sceneId || '').trim();
        return (Array.isArray(configData.scenes) ? configData.scenes : []).find(scene => String(scene?.id || '') === id) || null;
    }

    function getAutomationStatusMapFromContext(context = {}) {
        if (typeof context.getAutomationStatusMap === 'function') return context.getAutomationStatusMap();
        const cache = typeof context.getAutomationStatusCache === 'function'
            ? context.getAutomationStatusCache()
            : (global.SmartCenter?.automationStatusCache || {});
        return new Map((Array.isArray(cache.rules) ? cache.rules : []).map(item => [String(item.id), item]));
    }

    function getActiveAutomationCanvasRule(context = {}) {
        if (!activeAutomationCanvasRuleId) return null;
        const { configData = global.configData || {} } = getContext(context);
        return getAutomationStatusMapFromContext(context).get(String(activeAutomationCanvasRuleId))
            || (Array.isArray(configData.automations) ? configData.automations : []).find(item => String(item?.id || '') === String(activeAutomationCanvasRuleId))
            || null;
    }

        function getAutomationRuleRuntimeMeta(rule) {
            const state = rule?.state || {};
            const enabled = !!rule?.enabled;
            const triggerType = String(rule?.trigger_type || 'condition');
            const hasError = !!String(state.last_error || '').trim();
            const sceneRunning = !!state.scene_running;
            const rawMatched = !!state.last_condition_raw;
            if (!enabled) return { cls: 'waiting', cardClass: '', text: '已停用' };
            if (hasError) return { cls: 'error', cardClass: 'runtime-error', text: '异常' };
            if (sceneRunning) return { cls: 'running', cardClass: 'runtime-running', text: '执行中' };
            if (triggerType === 'compound') {
                if (state.last_trigger_matched) return { cls: 'matched', cardClass: 'runtime-matched', text: '触发达成' };
                if (state.preconditions_met === false) return { cls: 'waiting', cardClass: '', text: '前置未满足' };
                const triggers = Array.isArray(rule?.triggers) ? rule.triggers : [];
                if (triggers.some(item => item.last_condition_raw && !item.last_condition_stable)) return { cls: 'waiting', cardClass: '', text: '防抖中' };
                return { cls: 'waiting', cardClass: '', text: '组合监测' };
            }
            if (triggerType === 'schedule') {
                if (isAutomationScheduleDoneToday(rule)) return { cls: 'matched', cardClass: 'runtime-matched', text: '今日已执行' };
                if (state.last_day_match === false) return { cls: 'waiting', cardClass: '', text: '等待日期' };
                return { cls: 'waiting', cardClass: '', text: '等待定时' };
            }
            if (triggerType === 'mixed') {
                if (state.last_trigger_matched) return { cls: 'matched', cardClass: 'runtime-matched', text: '已触发' };
                if (state.last_day_match === false) return { cls: 'waiting', cardClass: '', text: '等待日期' };
                if (state.last_in_window === false) return { cls: rawMatched ? 'waiting' : 'waiting', cardClass: '', text: rawMatched ? '条件满足/窗外' : '窗外等待' };
                if (state.last_condition_stable) return { cls: 'matched', cardClass: 'runtime-matched', text: '条件命中' };
            } else if (state.last_condition_stable) {
                return { cls: 'matched', cardClass: 'runtime-matched', text: '条件命中' };
            }
            if (rawMatched) return { cls: 'waiting', cardClass: '', text: '防抖中' };
            return { cls: 'waiting', cardClass: '', text: '监测中' };
        }

        function buildAutomationConditionStateChips(condition = {}, state = {}, labelPrefix = '') {
            const chips = [];
            const pushChip = (label, text, cls = 'info', title = '') => chips.push({ label, text, cls, title });
            const prop = condition.prop || '';
            const sourceLabel = getAutomationSourceLabel(condition.source_type);
            const propLabel = getAutomationPropLabel(prop);
            const currentText = formatAutomationValueWithUnit(state.current_value, prop);
            const thresholdText = formatAutomationValueWithUnit(condition.value, prop);
            const op = condition.op || '<';
            const label = labelPrefix || '阈值';
            if (state.last_error === 'state_unavailable') {
                pushChip(label, `${sourceLabel}/${propLabel} 无数据`, 'error');
            } else if (state.last_base_match || state.last_condition_stable) {
                pushChip(label, `${propLabel} ${currentText} ${op} ${thresholdText}`, 'pass');
            } else {
                pushChip(label, `${propLabel} ${currentText} 未达到 ${op} ${thresholdText}`, 'wait');
            }

            const crossingMode = String(condition.crossing_mode || state.crossing_mode || 'none');
            if (crossingMode !== 'none') {
                const directionText = crossingMode === 'cross_up' ? '上穿阈值' : '下穿阈值';
                const rearmValue = condition.rearm_value !== '' && condition.rearm_value !== undefined ? condition.rearm_value : state.rearm_value;
                const rearmText = rearmValue !== null && rearmValue !== undefined && rearmValue !== '' ? `，复位 ${formatAutomationValueWithUnit(rearmValue, prop)}` : '';
                if (state.crossing_active) pushChip('穿越', `已${directionText}${rearmText}`, 'pass');
                else if (state.crossing_ready) pushChip('穿越', `等待${directionText}`, 'wait');
                else pushChip('穿越', `等待复位${rearmText}`, 'wait');
            }

            const hitsRequired = Number(state.hits_required || condition.consecutive_hits || 1);
            const debounceSec = Number(state.debounce_sec ?? condition.debounce_sec ?? 0);
            if (hitsRequired > 1 || debounceSec > 0) {
                if (state.last_condition_stable) {
                    const parts = [];
                    if (hitsRequired > 1) parts.push(`${state.hits || 0}/${hitsRequired}`);
                    if (debounceSec > 0) parts.push(`已稳定 ${formatRelativeSeconds(state.stable_for_sec || debounceSec)}`);
                    pushChip('稳定', parts.join(' · ') || '已满足', 'pass');
                } else if (state.last_condition_raw) {
                    const parts = [];
                    if (hitsRequired > 1) parts.push(`${state.hits || 0}/${hitsRequired}`);
                    if (debounceSec > 0) parts.push(`${formatRelativeSeconds(state.stable_for_sec || 0)}/${formatRelativeSeconds(debounceSec)}`);
                    pushChip('稳定', parts.join(' · ') || '确认中', 'wait');
                } else {
                    pushChip('稳定', hitsRequired > 1 || debounceSec > 0 ? '未开始计时' : '无需防抖', 'muted');
                }
            }
            return chips;
        }

        function formatAutomationConditionSummary(condition = {}, state = {}) {
            const prop = condition.prop || '';
            const sourceLabel = getAutomationSourceLabel(condition.source_type);
            const propLabel = getAutomationPropLabel(prop);
            const currentText = formatAutomationValueWithUnit(state.current_value, prop);
            const thresholdText = formatAutomationValueWithUnit(condition.value, prop);
            const op = condition.op || '<';
            const deviceId = condition.device_id || '未指定设备';
            const parts = [
                `${sourceLabel} / ${propLabel}`,
                `${deviceId}`,
                `当前 ${currentText}`,
                `条件 ${op} ${thresholdText}`,
            ];
            return parts.filter(Boolean);
        }
        function getAutomationConditionNodeClass(condition = {}, state = {}) {
            if (state.last_error === 'state_unavailable' || state.last_error) return 'error';
            if (state.last_condition_stable || state.last_base_match || state.matched) return 'pass';
            if (state.last_condition_raw) return 'running';
            return 'wait';
        }
        function formatAutomationScheduleSummary(schedule = {}, state = {}) {
            const dayLabel = getAutomationDayLabel(schedule);
            const timeText = schedule.time || '--';
            const windowText = `${schedule.time_start || '--'}-${schedule.time_end || '--'}`;
            const statusText = state.last_day_match === false
                ? '今天不执行'
                : (isAutomationScheduleStateDoneToday(state) ? '今日已执行' : '等待定时');
            return [`${dayLabel} ${timeText}`, `补执行窗口 ${windowText}`, statusText];
        }
        function getAutomationScheduleNodeClass(state = {}) {
            if (state.last_error === 'schedule_missed_window' || state.last_schedule_missed) return 'wait';
            if (isAutomationScheduleStateDoneToday(state)) return 'pass';
            if (state.last_day_match === false) return 'muted';
            return 'wait';
        }
        function formatAutomationActionLabel(action = {}, index = 0) {
            const sub = String(action.sub_system || '').trim() || '动作';
            const type = String(action.action_type || action.action || '').trim() || (action.is_open === false ? 'off' : 'on');
            const map = {
                power_on: '开机',
                power_off: '关机',
                set_mode: '设置模式',
                set_temp: '设置温度',
                set_fan_mode: '设置风速',
                command: '发送指令',
                on: '开启',
                off: '关闭',
                jog: '点动',
            };
            const actionText = map[type] || type;
            if (sub === 'hvac') return `空调 ${actionText}`;
            if (sub === 'light') return `灯光 ${actionText}`;
            if (sub === 'power') return `强电 ${actionText}`;
            if (sub === 'universal') return `协议 ${actionText}`;
            if (sub === 'wait') return '等待';
            return `${sub} ${actionText}`;
        }
        function formatAutomationActionDetails(action = {}, context = {}) {
            const { getHvacModeText = global.getHvacModeText || (value => value) } = getContext(context);
            const details = [];
            if (action.device_id) details.push(`设备 ${action.device_id}`);
            if (action.mode) details.push(`模式 ${getHvacModeText ? getHvacModeText(action.mode) : action.mode}`);
            if (action.temperature !== undefined && action.temperature !== null) details.push(`温度 ${action.temperature}°C`);
            if (action.fan_mode || action.fan_speed) details.push(`风速 ${action.fan_mode || action.fan_speed}`);
            if (action.channel !== undefined && action.channel !== null) details.push(`通道 ${action.channel}`);
            if (action.payload) details.push(`指令 ${String(action.payload).slice(0, 28)}`);
            return details;
        }
        function makeAutomationNodeId(kind, index, extra = '') {
            return `${kind}-${index}${extra ? `-${extra}` : ''}`.replace(/[^a-zA-Z0-9_-]+/g, '-');
        }
        function formatAutomationNodeDetails(node = {}) {
            const details = Array.isArray(node.details) && node.details.length ? node.details : (node.meta || []);
            return details.filter(Boolean);
        }
        function renderAutomationFlowNode(node) {
            const meta = (node.meta || []).filter(Boolean);
            return `<button class="auto-flow-node ${escapeHtml(node.kind || 'info')} ${escapeHtml(node.status || 'wait')}" type="button" data-auto-node-id="${escapeHtml(node.id || '')}" onclick="handleAutomationCanvasNodeClick(event, '${escapeHtml(node.id || '')}')">
                <div class="auto-flow-port in"></div>
                <div class="auto-flow-port out"></div>
                <div class="auto-flow-node-top">
                    <span class="auto-flow-icon">${escapeHtml(node.icon || '●')}</span>
                    <span class="auto-flow-type">${escapeHtml(node.type || '节点')}</span>
                    <span class="auto-flow-state">${escapeHtml(node.stateText || '')}</span>
                </div>
                <div class="auto-flow-title">${escapeHtml(node.title || '--')}</div>
                ${meta.length ? `<div class="auto-flow-meta">${meta.map(item => `<span>${escapeHtml(item)}</span>`).join('')}</div>` : ''}
            </button>`;
        }

        function getAutomationGroupMeta(rule = {}) {
            const explicitName = String(rule.group_name || rule.group_title || rule.display_group || '').trim();
            const explicitKey = String(rule.group || rule.automation_group || rule.group_id || explicitName || '').trim();
            if (explicitName || explicitKey) {
                return {
                    key: (explicitKey || explicitName).toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '_') || 'custom',
                    title: explicitName || explicitKey,
                    subtitle: '配置分组'
                };
            }
            const text = `${rule.id || ''} ${rule.name || ''} ${rule.scene_id || ''} ${rule.scene_name || ''}`.toLowerCase();
            if (text.includes('outdoor_light') || text.includes('户外灯') || text.includes('庭院灯')) {
                return { key: 'outdoor_light', title: '庭院灯 / 户外灯', subtitle: '低照度开灯、定时关灯、午夜兜底关灯集中显示' };
            }
            if (text.includes('machine_room_hvac') || (text.includes('机房') && text.includes('空调'))) {
                return { key: 'machine_room_hvac', title: '机房空调', subtitle: '工作日开关机和低温保护集中显示' };
            }
            const sceneRoot = String(rule.scene_id || 'other')
                .replace(/^scene_/, '')
                .replace(/_(low_temp|workday|auto|manual)?_?(on|off|open|close|start|stop)$/i, '')
                .replace(/[^a-z0-9]+/gi, '_') || 'other';
            return { key: `scene_${sceneRoot}`, title: rule.scene_name || '其他自动化', subtitle: '按目标场景自动归组' };
        }

        function ensureAutomationRuleGroups(rules) {
            const list = document.getElementById('automation-rule-list');
            if (!list) return;
            const cards = Array.from(list.querySelectorAll('[data-auto-rule-id]'));
            if (!cards.length) return;
            const runtimeRules = Array.isArray(rules) && rules.length
                ? rules
                : cards.map(card => ({
                    id: card.dataset.autoRuleId,
                    name: card.dataset.autoRuleName || '',
                    scene_id: card.dataset.autoSceneId || ''
                }));
            const cardMap = new Map(cards.map(card => [String(card.dataset.autoRuleId || ''), card]));
            const groups = [];
            const groupMap = new Map();
            const signatureParts = [];
            runtimeRules.forEach(rule => {
                const card = cardMap.get(String(rule?.id || ''));
                if (!card) return;
                const meta = getAutomationGroupMeta(rule);
                signatureParts.push(`${meta.key}:${String(rule?.id || '')}`);
                if (!groupMap.has(meta.key)) {
                    const group = { ...meta, rules: [] };
                    groupMap.set(meta.key, group);
                    groups.push(group);
                }
                groupMap.get(meta.key).rules.push(rule);
            });
            if (!groups.length) return;
            const signature = signatureParts.join('|');
            if (automationGroupSignature === signature && list.querySelector('.auto-rule-group')) return;
            automationGroupSignature = signature;
            const fragment = document.createDocumentFragment();
            groups.forEach(group => {
                const section = document.createElement('section');
                section.className = 'auto-rule-group';
                section.dataset.autoGroupKey = group.key;
                section.innerHTML = `
                    <div class="auto-rule-group-head">
                        <div class="auto-rule-group-title-wrap">
                            <div class="auto-rule-group-title">${escapeHtml(group.title)}</div>
                            <div class="auto-rule-group-sub">${escapeHtml(group.subtitle || '')}</div>
                        </div>
                        <span class="auto-rule-group-summary">整理中</span>
                    </div>
                    <div class="auto-rule-group-body"></div>
                `;
                const body = section.querySelector('.auto-rule-group-body');
                group.rules.forEach(rule => {
                    const card = cardMap.get(String(rule?.id || ''));
                    if (card && body) body.appendChild(card);
                });
                fragment.appendChild(section);
            });
            list.replaceChildren(fragment);
        }
        function buildAutomationFlowNodes(rule = {}, context = {}) {
            const { configData = global.configData || {}, getHvacModeText = global.getHvacModeText || (value => value) } = getContext(context);
            const nodes = [];
            const triggerType = String(rule.trigger_type || 'condition');
            const state = rule.state || {};
            nodes.push({
                id: makeAutomationNodeId('start', nodes.length),
                kind: 'start',
                status: rule.enabled ? 'pass' : 'muted',
                icon: rule.enabled ? '▶' : 'Ⅱ',
                type: '规则',
                title: rule.name || rule.id || '自动化规则',
                stateText: rule.enabled ? '启用' : '停用',
                meta: [`模式 ${triggerType}`, rule.group_name || rule.group || ''],
                details: [`规则ID ${rule.id || '--'}`, `执行场景 ${rule.scene_id || rule.action_scene_id || '--'}`, rule.enabled ? '当前规则已启用' : '当前规则已停用'],
                editable: false
            });

            if (triggerType === 'compound') {
                const preconditions = Array.isArray(rule.preconditions) ? rule.preconditions : [];
                preconditions.forEach((item, idx) => {
                    const condition = item.condition || item || {};
                    nodes.push({
                        id: makeAutomationNodeId('precondition', nodes.length, idx),
                        kind: 'precondition',
                        status: item.matched ? 'pass' : 'wait',
                        icon: '◇',
                        type: '前置条件',
                        title: item.label || `前置 ${idx + 1}`,
                        stateText: item.matched ? '满足' : '未满足',
                        meta: formatAutomationConditionSummary(condition, Object.assign({}, item, { current_value: item.current_value })),
                        details: formatAutomationConditionSummary(condition, Object.assign({}, item, { current_value: item.current_value })).concat([
                            `判定结果 ${item.matched ? '满足' : '未满足'}`,
                            '组合规则暂以配置文件结构保存，当前画布先用于阅读和核对。'
                        ]),
                        editable: false
                    });
                });
                const triggerModeText = String(rule.trigger_mode || 'any') === 'all' ? '全部满足' : '任意满足';
                nodes.push({
                    id: makeAutomationNodeId('gate', nodes.length),
                    kind: 'gate',
                    status: state.preconditions_met === false ? 'wait' : 'pass',
                    icon: String(rule.trigger_mode || 'any') === 'all' ? 'AND' : 'OR',
                    type: '组合逻辑',
                    title: `${triggerModeText}触发`,
                    stateText: state.last_trigger_matched ? '达成' : '等待',
                    meta: [`前置 ${state.preconditions_met === false ? '未满足' : '通过'}`],
                    details: [`触发模式 ${triggerModeText}`, `前置条件 ${state.preconditions_met === false ? '未满足' : '通过'}`, `本次触发 ${state.last_trigger_matched ? '达成' : '未达成'}`],
                    editable: false
                });
                (Array.isArray(rule.triggers) ? rule.triggers : []).forEach((trigger, idx) => {
                    const type = String(trigger.type || 'condition');
                    if (type === 'schedule') {
                        nodes.push({
                            id: makeAutomationNodeId('trigger-schedule', nodes.length, idx),
                            kind: 'schedule',
                            status: getAutomationScheduleNodeClass(trigger),
                            icon: '⏱',
                            type: '定时触发',
                            title: trigger.label || `定时 ${idx + 1}`,
                            stateText: isAutomationScheduleStateDoneToday(trigger) ? '已执行' : '等待',
                            meta: formatAutomationScheduleSummary(trigger.schedule || {}, trigger),
                            details: formatAutomationScheduleSummary(trigger.schedule || {}, trigger).concat(['组合触发节点，当前画布先用于查看状态。']),
                            editable: false
                        });
                    } else {
                        nodes.push({
                            id: makeAutomationNodeId('trigger-condition', nodes.length, idx),
                            kind: 'condition',
                            status: getAutomationConditionNodeClass(trigger.condition || {}, trigger),
                            icon: '◆',
                            type: '条件触发',
                            title: trigger.label || `条件 ${idx + 1}`,
                            stateText: trigger.last_condition_stable || trigger.last_base_match ? '满足' : (trigger.last_condition_raw ? '确认中' : '等待'),
                            meta: formatAutomationConditionSummary(trigger.condition || {}, trigger),
                            details: formatAutomationConditionSummary(trigger.condition || {}, trigger).concat([
                                `原始命中 ${trigger.last_condition_raw ? '是' : '否'}`,
                                `稳定命中 ${trigger.last_condition_stable || trigger.last_base_match ? '是' : '否'}`
                            ]),
                            editable: false
                        });
                    }
                });
            } else {
                if (triggerType === 'schedule' || triggerType === 'mixed') {
                    nodes.push({
                        id: makeAutomationNodeId('schedule', nodes.length),
                        kind: 'schedule',
                        status: getAutomationScheduleNodeClass(state),
                        icon: '⏱',
                        type: triggerType === 'mixed' ? '时间窗' : '定时触发',
                        title: triggerType === 'mixed' ? '计划窗口' : '定时计划',
                        stateText: triggerType === 'mixed' ? (state.last_in_window ? '窗内' : '窗外') : (isAutomationScheduleDoneToday(rule) ? '已执行' : '等待'),
                        meta: formatAutomationScheduleSummary(rule.schedule || {}, state),
                        details: formatAutomationScheduleSummary(rule.schedule || {}, state).concat([
                            `日期类型 ${getAutomationDayLabel(rule.schedule || {})}`,
                            '可通过规则编辑修改定时时间和补执行窗口。'
                        ]),
                        editable: true,
                        editTarget: 'schedule'
                    });
                }
                if (triggerType === 'condition' || triggerType === 'mixed') {
                    nodes.push({
                        id: makeAutomationNodeId('condition', nodes.length),
                        kind: 'condition',
                        status: getAutomationConditionNodeClass(rule.condition || {}, state),
                        icon: '◆',
                        type: '条件触发',
                        title: '阈值判断',
                        stateText: state.last_condition_stable ? '满足' : (state.last_condition_raw ? '确认中' : '等待'),
                        meta: formatAutomationConditionSummary(rule.condition || {}, state),
                        details: formatAutomationConditionSummary(rule.condition || {}, state).concat([
                            `原始命中 ${state.last_condition_raw ? '是' : '否'}`,
                            `稳定命中 ${state.last_condition_stable ? '是' : '否'}`,
                            '可通过规则编辑修改数据源、属性、比较符和阈值。'
                        ]),
                        editable: true,
                        editTarget: 'condition'
                    });
                    const debounceSec = Number(state.debounce_sec ?? rule.condition?.debounce_sec ?? 0);
                    const hitsRequired = Number(state.hits_required || rule.condition?.consecutive_hits || 1);
                    if (debounceSec > 0 || hitsRequired > 1 || String(rule.condition?.crossing_mode || 'none') !== 'none') {
                        nodes.push({
                            id: makeAutomationNodeId('debounce', nodes.length),
                            kind: 'debounce',
                            status: state.last_condition_stable ? 'pass' : (state.last_condition_raw ? 'running' : 'wait'),
                            icon: '≈',
                            type: '防抖/复位',
                            title: '稳定确认',
                            stateText: state.last_condition_stable ? '通过' : '等待',
                            meta: [
                                debounceSec > 0 ? `防抖 ${formatRelativeSeconds(debounceSec)}` : '',
                                hitsRequired > 1 ? `连续 ${state.hits || 0}/${hitsRequired}` : '',
                                rule.condition?.crossing_mode && rule.condition.crossing_mode !== 'none' ? `${rule.condition.crossing_mode} / 复位 ${rule.condition.rearm_value || '--'}` : ''
                            ],
                            details: [
                                debounceSec > 0 ? `防抖时间 ${formatRelativeSeconds(debounceSec)}` : '未设置防抖时间',
                                hitsRequired > 1 ? `连续命中 ${state.hits || 0}/${hitsRequired}` : '单次命中即可',
                                rule.condition?.crossing_mode && rule.condition.crossing_mode !== 'none' ? `穿越触发 ${rule.condition.crossing_mode}` : '无穿越触发',
                                rule.condition?.rearm_value ? `复位阈值 ${rule.condition.rearm_value}` : ''
                            ],
                            editable: true,
                            editTarget: 'condition'
                        });
                    }
                }
            }

            const scene = findAutomationScene(rule.scene_id || rule.action_scene_id, { configData });
            nodes.push({
                id: makeAutomationNodeId('scene', nodes.length),
                kind: 'scene',
                status: state.scene_running ? 'running' : (state.last_trigger_matched ? 'pass' : 'wait'),
                icon: '◎',
                type: '场景联动',
                title: scene?.name || rule.scene_name || rule.scene_id || rule.action_scene_id || '未配置场景',
                stateText: state.scene_running ? '执行中' : '待触发',
                meta: [`ID ${rule.scene_id || rule.action_scene_id || '--'}`],
                details: [
                    `场景ID ${rule.scene_id || rule.action_scene_id || '--'}`,
                    `动作数量 ${Array.isArray(scene?.actions) ? scene.actions.length : 0}`,
                    state.scene_running ? '当前正在执行场景动作' : '等待触发后执行场景'
                ],
                editable: false
            });
            (Array.isArray(scene?.actions) ? scene.actions : []).forEach((action, idx) => {
                const delayMs = Number(action.delay_ms || action.wait_ms || 0);
                if (delayMs > 0) {
                    nodes.push({
                        id: makeAutomationNodeId('delay', nodes.length, idx),
                        kind: 'delay',
                        status: 'info',
                        icon: '…',
                        type: '延时',
                        title: `${delayMs} ms`,
                        stateText: '等待',
                        meta: ['动作间隔'],
                        details: [`延时 ${delayMs} ms`, '用于给设备留出响应时间，避免连续指令过快。'],
                        editable: false
                    });
                }
                nodes.push({
                    id: makeAutomationNodeId('action', nodes.length, idx),
                    kind: 'action',
                    status: state.scene_running ? 'running' : 'wait',
                    icon: '→',
                    type: `执行 ${idx + 1}`,
                    title: formatAutomationActionLabel(action, idx),
                    stateText: action.sub_system || '',
                    meta: formatAutomationActionDetails(action, { getHvacModeText }),
                    details: formatAutomationActionDetails(action, { getHvacModeText }).concat([
                        `子系统 ${action.sub_system || '--'}`,
                        `动作类型 ${action.action_type || action.action || '--'}`
                    ]),
                    editable: false
                });
            });
            return nodes;
        }

        function buildAutomationScheduleStateChips(schedule = {}, state = {}, labelPrefix = '定时') {
            const chips = [];
            const pushChip = (label, text, cls = 'info', title = '') => chips.push({ label, text, cls, title });
            const dayLabel = getAutomationDayLabel(schedule);
            if (state.last_day_match === false) pushChip('日期', `${dayLabel}：今天不执行`, 'wait');
            else pushChip('日期', `${dayLabel}：今天可执行`, 'pass');
            const timeText = schedule.time || '--';
            if (state.last_error === 'schedule_missed_window' || state.last_schedule_missed) {
                pushChip(labelPrefix, `${timeText} 已错过补执行窗口`, 'wait');
            } else if (isAutomationScheduleStateDoneToday(state)) {
                pushChip(labelPrefix, `今日 ${timeText} 已执行`, 'pass');
            } else if (state.last_day_match === false) {
                pushChip(labelPrefix, `等待下一个${dayLabel} ${timeText}`, 'wait');
            } else {
                pushChip(labelPrefix, `等待 ${timeText}`, 'wait');
            }
            return chips;
        }
        function buildAutomationConditionChips(rule) {
            const state = rule?.state || {};
            const condition = rule?.condition || {};
            const schedule = rule?.schedule || {};
            const triggerType = String(rule?.trigger_type || 'condition');
            const chips = [];
            const pushChip = (label, text, cls = 'info', title = '') => chips.push({ label, text, cls, title });
            const dayLabel = getAutomationDayLabel(schedule);

            if (triggerType === 'compound') {
                const modeText = String(rule?.trigger_mode || 'any') === 'all' ? '全部触发条件满足' : '任意触发条件满足';
                pushChip('组合', modeText, 'info');
                (Array.isArray(rule?.preconditions) ? rule.preconditions : []).forEach((item, idx) => {
                    const conditionInfo = item.condition || {};
                    const propLabel = getAutomationPropLabel(conditionInfo.prop);
                    const currentText = formatAutomationValueWithUnit(item.current_value, conditionInfo.prop);
                    const label = item.label || `前置${idx + 1}`;
                    pushChip('前置', `${label}：${propLabel} ${currentText}`, item.matched ? 'pass' : 'wait');
                });
                (Array.isArray(rule?.triggers) ? rule.triggers : []).forEach((trigger, idx) => {
                    const label = trigger.label || `触发${idx + 1}`;
                    if (String(trigger.type || 'condition') === 'schedule') {
                        buildAutomationScheduleStateChips(trigger.schedule || {}, trigger, label).forEach(chip => chips.push(chip));
                    } else {
                        buildAutomationConditionStateChips(trigger.condition || {}, trigger, label).forEach(chip => chips.push(chip));
                    }
                });
                if (state.last_skip_reason === 'preconditions_not_met') {
                    pushChip('跳过', '触发条件已满足，但前置条件未满足', 'wait');
                }
                return chips;
            }

            if (triggerType === 'schedule' || triggerType === 'mixed') {
                if (state.last_day_match === false) pushChip('日期', `${dayLabel}：今天不执行`, 'wait');
                else pushChip('日期', `${dayLabel}：今天可执行`, 'pass');
            }

            if (triggerType === 'schedule') {
                const timeText = schedule.time || '--';
                if (state.last_error === 'schedule_missed_window' || state.last_schedule_missed) {
                    pushChip('定时', `${timeText} 已错过补执行窗口`, 'wait');
                } else if (isAutomationScheduleDoneToday(rule)) {
                    pushChip('定时', `今日 ${timeText} 已执行`, 'pass');
                } else if (state.last_day_match === false) {
                    pushChip('定时', `等待下一个${dayLabel} ${timeText}`, 'wait');
                } else {
                    pushChip('定时', `等待 ${timeText}`, 'wait');
                }
                return chips;
            }

            if (triggerType === 'mixed') {
                const windowText = `${schedule.time_start || '--'}-${schedule.time_end || '--'}`;
                if (state.last_in_window === true) pushChip('时间窗', `${windowText} 内`, 'pass');
                else pushChip('时间窗', `${windowText} 外`, 'wait');
                if (Number(condition.window_bootstrap_sec || 0) > 0) {
                    pushChip('补触发', `入窗持续 ${formatRelativeSeconds(condition.window_bootstrap_sec)} 后补执行`, 'info');
                }
            }

            return chips.concat(buildAutomationConditionStateChips(condition, state, '阈值'));
        }

        function renderAutomationCanvasInspector(rule, node, context = {}) {
            const inspector = document.getElementById('automation-node-inspector');
            if (!inspector) return;
            if (!rule || !node) {
                inspector.innerHTML = '<div class="auto-node-inspector-empty">点击任意节点，查看当前值、判断条件、执行目标和可编辑入口。</div>';
                return;
            }
            const details = formatAutomationNodeDetails(node);
            const editableText = node.editable ? '此节点可通过规则编辑安全修改' : '此节点当前为查看模式';
            inspector.innerHTML = `
                <div class="auto-node-inspector-card">
                    <div class="auto-node-inspector-kicker">${escapeHtml(node.type || '节点')}</div>
                    <div class="auto-node-inspector-title">${escapeHtml(node.title || '--')}</div>
                    <div class="auto-node-inspector-state ${escapeHtml(node.status || 'wait')}">${escapeHtml(node.stateText || '等待')}</div>
                    <div class="auto-node-inspector-list">
                        ${details.length ? details.map(item => `<div>${escapeHtml(item)}</div>`).join('') : '<div>暂无详细参数。</div>'}
                    </div>
                    <div class="auto-node-inspector-note">${escapeHtml(editableText)}</div>
                    <div class="auto-node-inspector-actions">
                        ${node.editable && String(rule.trigger_type || '') !== 'compound' ? `<button class="auto-node-modal-btn" type="button" onclick="openAutomationCanvasEditor('${escapeHtml(node.editTarget || '')}')">打开编辑</button>` : ''}
                        <button class="auto-node-modal-btn secondary" type="button" onclick="scrollAutomationRuleIntoView('${escapeHtml(rule.id || '')}')">定位卡片</button>
                    </div>
                </div>
            `;
        }

        function clampAutomationCanvasZoom(value) {
            const next = Number(value);
            if (!Number.isFinite(next)) return 1;
            return Math.max(0.42, Math.min(1.4, next));
        }

        function updateAutomationCanvasZoomLabel() {
            const label = document.getElementById('auto-node-zoom-value');
            if (label) label.textContent = `${Math.round(automationCanvasZoom * 100)}%`;
        }

        function measureAutomationFlowRawWidth(scaleEl) {
            if (!scaleEl) return 0;
            const children = Array.from(scaleEl.children);
            if (!children.length) return 0;
            const left = Math.min(...children.map(el => el.offsetLeft));
            const right = Math.max(...children.map(el => el.offsetLeft + el.offsetWidth));
            return Math.max(0, right - left);
        }

        function measureAutomationFlowRawHeight(scaleEl) {
            if (!scaleEl) return 0;
            const children = Array.from(scaleEl.children);
            if (!children.length) return 0;
            return Math.max(...children.map(el => el.offsetHeight));
        }

        function applyAutomationCanvasZoom({ fit = false } = {}) {
            const canvas = document.getElementById('automation-node-canvas');
            const scaleEl = canvas?.querySelector('.auto-flow-scale');
            if (!canvas || !scaleEl) return;
            automationCanvasZoom = clampAutomationCanvasZoom(automationCanvasZoom);
            const rawWidth = measureAutomationFlowRawWidth(scaleEl);
            const rawHeight = measureAutomationFlowRawHeight(scaleEl);
            const visualWidth = rawWidth * automationCanvasZoom;
            const visualHeight = rawHeight * automationCanvasZoom;
            const x = Math.max(18, fit ? (canvas.clientWidth - visualWidth) / 2 : 28);
            const y = Math.max(0, Math.min(canvas.clientHeight - visualHeight, 0));
            automationCanvasBaseX = x;
            automationCanvasBaseY = y / 2;
            if (fit) {
                automationCanvasPanX = 0;
                automationCanvasPanY = 0;
            }
            scaleEl.style.width = `${Math.max(rawWidth, 1)}px`;
            scaleEl.style.minWidth = `${Math.max(rawWidth, 1)}px`;
            scaleEl.style.marginLeft = '0px';
            scaleEl.style.transform = `translate(${Math.round(automationCanvasBaseX + automationCanvasPanX)}px, calc(-50% + ${Math.round(automationCanvasBaseY + automationCanvasPanY)}px)) scale(${automationCanvasZoom})`;
            updateAutomationCanvasZoomLabel();
        }

        function zoomAutomationNodeCanvas(delta) {
            automationCanvasZoom = clampAutomationCanvasZoom(automationCanvasZoom + Number(delta || 0));
            applyAutomationCanvasZoom({ fit: false });
        }

        function fitAutomationNodeCanvas() {
            const canvas = document.getElementById('automation-node-canvas');
            const scaleEl = canvas?.querySelector('.auto-flow-scale');
            if (!canvas || !scaleEl) return;
            const rawWidth = measureAutomationFlowRawWidth(scaleEl);
            const rawHeight = measureAutomationFlowRawHeight(scaleEl);
            const availableW = Math.max(220, canvas.clientWidth - 72);
            const availableH = Math.max(120, canvas.clientHeight - 80);
            automationCanvasZoom = clampAutomationCanvasZoom(Math.min(1.12, availableW / Math.max(rawWidth, 1), availableH / Math.max(rawHeight, 1)));
            applyAutomationCanvasZoom({ fit: true });
        }

        function getAutomationCanvasClientPoint(event) {
            const touch = event?.touches?.[0] || event?.changedTouches?.[0];
            if (touch) return { x: touch.clientX, y: touch.clientY };
            return { x: event?.clientX || 0, y: event?.clientY || 0 };
        }

        function startAutomationCanvasPan(event) {
            if (!event) return;
            if (event.button !== undefined && event.button !== 0) return;
            const canvas = document.getElementById('automation-node-canvas');
            if (!canvas) return;
            const point = getAutomationCanvasClientPoint(event);
            automationCanvasDragState = {
                startX: point.x,
                startY: point.y,
                lastX: point.x,
                lastY: point.y,
                panX: automationCanvasPanX,
                panY: automationCanvasPanY,
                moved: false,
                pointerId: event.pointerId,
            };
            canvas.classList.add('dragging');
            if (event.pointerId !== undefined) canvas.setPointerCapture?.(event.pointerId);
            event.preventDefault?.();
        }

        function moveAutomationCanvasPan(event) {
            if (!automationCanvasDragState) return;
            const point = getAutomationCanvasClientPoint(event);
            const dx = point.x - automationCanvasDragState.startX;
            const dy = point.y - automationCanvasDragState.startY;
            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) automationCanvasDragState.moved = true;
            automationCanvasPanX = automationCanvasDragState.panX + dx;
            automationCanvasPanY = automationCanvasDragState.panY + dy;
            automationCanvasDragState.lastX = point.x;
            automationCanvasDragState.lastY = point.y;
            applyAutomationCanvasZoom({ fit: false });
            event.preventDefault?.();
        }

        function endAutomationCanvasPan(event) {
            if (!automationCanvasDragState) return;
            const canvas = document.getElementById('automation-node-canvas');
            const moved = !!automationCanvasDragState.moved;
            const pointerId = automationCanvasDragState.pointerId;
            automationCanvasDragState = null;
            canvas?.classList.remove('dragging');
            if (pointerId !== undefined) canvas?.releasePointerCapture?.(pointerId);
            if (moved) automationCanvasSuppressClickUntil = Date.now() + 220;
            event?.preventDefault?.();
        }

        function bindAutomationCanvasPan() {
            const canvas = document.getElementById('automation-node-canvas');
            if (!canvas || canvas.dataset.panBound === '1') return;
            canvas.dataset.panBound = '1';
            canvas.addEventListener('pointerdown', startAutomationCanvasPan);
            canvas.addEventListener('pointermove', moveAutomationCanvasPan);
            canvas.addEventListener('pointerup', endAutomationCanvasPan);
            canvas.addEventListener('pointercancel', endAutomationCanvasPan);
            canvas.addEventListener('pointerleave', endAutomationCanvasPan);
            canvas.addEventListener('mousedown', startAutomationCanvasPan);
            global.addEventListener('mousemove', moveAutomationCanvasPan);
            global.addEventListener('mouseup', endAutomationCanvasPan);
            canvas.addEventListener('touchstart', startAutomationCanvasPan, { passive: false });
            global.addEventListener('touchmove', moveAutomationCanvasPan, { passive: false });
            global.addEventListener('touchend', endAutomationCanvasPan, { passive: false });
            global.addEventListener('touchcancel', endAutomationCanvasPan, { passive: false });
        }

        function handleAutomationCanvasNodeClick(event, nodeId, context = {}) {
            if (Date.now() < automationCanvasSuppressClickUntil) {
                event?.preventDefault?.();
                event?.stopPropagation?.();
                return false;
            }
            selectAutomationCanvasNode(nodeId, context);
            return true;
        }

        function renderAutomationNodeCanvas(rule, context = {}) {
            const canvas = document.getElementById('automation-node-canvas');
            const title = document.getElementById('automationNodeModalTitle');
            const sub = document.getElementById('automationNodeModalSub');
            const editBtn = document.getElementById('auto-node-edit-shortcut');
            if (!canvas || !rule) return;
            bindAutomationCanvasPan();
            const nodes = buildAutomationFlowNodes(rule, context);
            if (!nodes.some(node => node.id === activeAutomationCanvasNodeId)) {
                activeAutomationCanvasNodeId = nodes[0]?.id || '';
            }
            if (title) title.textContent = rule.name || rule.id || '自动化规则';
            if (sub) {
                const scene = findAutomationScene(rule.scene_id || rule.action_scene_id, context);
                sub.textContent = `规则 ${rule.id || '--'} · ${rule.enabled ? '已启用' : '已停用'} · 场景 ${scene?.name || rule.scene_name || rule.scene_id || rule.action_scene_id || '--'}`;
            }
            if (editBtn) {
                const canEdit = String(rule.trigger_type || '') !== 'compound';
                editBtn.disabled = !canEdit;
                editBtn.textContent = canEdit ? '编辑此规则' : '组合规则暂只读';
            }
            canvas.innerHTML = `<div class="auto-flow-scale">${nodes.map((node, idx) => `${idx > 0 ? '<div class="auto-flow-link"></div>' : ''}${renderAutomationFlowNode(node)}`).join('')}</div>`;
            canvas.querySelectorAll('.auto-flow-node').forEach(nodeEl => {
                nodeEl.classList.toggle('selected', String(nodeEl.dataset.autoNodeId || '') === String(activeAutomationCanvasNodeId));
            });
            applyAutomationCanvasZoom({ fit: false });
            const selected = nodes.find(node => node.id === activeAutomationCanvasNodeId) || nodes[0];
            renderAutomationCanvasInspector(rule, selected, context);
        }

        function openAutomationNodeCanvas(ruleId, context = {}) {
            const modal = document.getElementById('automationNodeModal');
            if (!modal) return;
            activeAutomationCanvasRuleId = String(ruleId || '');
            activeAutomationCanvasNodeId = '';
            automationCanvasZoom = 1;
            automationCanvasPanX = 0;
            automationCanvasPanY = 0;
            const rule = getActiveAutomationCanvasRule(context);
            if (!rule) {
                const notify = context.showToast || global.showToast || (() => {});
                notify('未找到自动化规则，稍后自动刷新后再试', true);
                if (typeof context.loadAutomationStatus === 'function') context.loadAutomationStatus(true);
                return;
            }
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
            document.body.classList.add('auto-node-modal-open');
            renderAutomationNodeCanvas(rule, context);
            requestAnimationFrame(() => fitAutomationNodeCanvas());
        }

        function closeAutomationNodeCanvas() {
            const modal = document.getElementById('automationNodeModal');
            if (!modal) return;
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('auto-node-modal-open');
        }

        function selectAutomationCanvasNode(nodeId, context = {}) {
            activeAutomationCanvasNodeId = String(nodeId || '');
            const rule = getActiveAutomationCanvasRule(context);
            if (rule) renderAutomationNodeCanvas(rule, context);
        }

        function scrollAutomationRuleIntoView(ruleId) {
            const card = document.getElementById(`auto-card-${ruleId}`);
            if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        function toggleAutomationEditor(ruleId, forceOpen = null) {
            const panel = document.getElementById(`auto-edit-panel-${ruleId}`);
            const btn = document.querySelector(`[data-auto-edit-btn="${ruleId}"]`);
            if (!panel) return;
            const shouldOpen = forceOpen === null ? !panel.classList.contains('open') : !!forceOpen;
            panel.classList.toggle('open', shouldOpen);
            if (btn) btn.textContent = shouldOpen ? '收起编辑' : '编辑条件';
        }

        function openAutomationCanvasEditor(editTarget = '', context = {}) {
            const rule = getActiveAutomationCanvasRule(context);
            if (!rule || !rule.id) return;
            const notify = context.showToast || global.showToast || (() => {});
            if (String(rule.trigger_type || '') === 'compound') {
                notify('组合规则结构更复杂，当前先支持节点查看，编辑会单独做安全版本。', true);
                return;
            }
            closeAutomationNodeCanvas();
            toggleAutomationEditor(rule.id, true);
            scrollAutomationRuleIntoView(rule.id);
            if (editTarget) {
                const focusMap = { condition: 'prop', schedule: 'time' };
                const suffix = focusMap[String(editTarget)] || '';
                const el = suffix ? document.getElementById(`auto-field-${rule.id}-${suffix}`) : null;
                if (el) setTimeout(() => el.focus(), 80);
            }
        }

        function renderAutomationNodePanel(rule, context = {}) {
            if (!rule || !rule.id) return;
            const panel = document.getElementById(`auto-node-panel-${rule.id}`);
            if (!panel || !panel.classList.contains('open')) return;
            const nodes = buildAutomationFlowNodes(rule, context);
            panel.innerHTML = `
                <div class="auto-node-toolbar">
                    <div>
                        <div class="auto-node-title">节点流程图</div>
                        <div class="auto-node-sub">从左到右：规则触发 -> 条件/时间/前置 -> 场景联动 -> 执行动作</div>
                    </div>
                    <button class="auto-edit-btn" type="button" onclick="toggleAutomationNodeView('${escapeHtml(rule.id)}', false)">收起</button>
                </div>
                <div class="auto-flow-canvas">
                    ${nodes.map((node, idx) => `${idx > 0 ? '<div class="auto-flow-link"></div>' : ''}${renderAutomationFlowNode(node)}`).join('')}
                </div>
            `;
        }

        function toggleAutomationNodeView(ruleId = null, forceOpen = null, context = {}) {
            const targetRuleId = String(ruleId || activeAutomationCanvasRuleId || '');
            if (!targetRuleId) return;
            const panel = document.getElementById(`auto-node-panel-${targetRuleId}`);
            const btn = document.querySelector(`[data-auto-node-btn="${targetRuleId}"]`);
            if (!panel) return;
            const shouldOpen = forceOpen === null ? !panel.classList.contains('open') : !!forceOpen;
            panel.classList.toggle('open', shouldOpen);
            if (btn) btn.textContent = shouldOpen ? '收起节点' : '节点视图';
            if (shouldOpen) {
                const rule = getAutomationStatusMapFromContext(context).get(String(targetRuleId)) || { id: targetRuleId, name: panel.closest('[data-auto-rule-name]')?.dataset?.autoRuleName || '' };
                renderAutomationNodePanel(rule, context);
            }
        }

        function renderAutomationConditionChips(rule) {
            if (!rule || !rule.id) return;
            const row = document.getElementById(`auto-condition-row-${rule.id}`);
            if (!row) return;
            const chips = buildAutomationConditionChips(rule);
            row.innerHTML = chips.length ? chips.map(chip => `
                <span class="auto-condition-chip ${chip.cls || 'info'}" title="${escapeHtml(chip.title || `${chip.label} ${chip.text}`)}">
                    <b>${escapeHtml(chip.label)}</b>${escapeHtml(chip.text)}
                </span>
            `).join('') : '<span class="auto-condition-chip muted">无附加条件</span>';
        }

        function updateAutomationGroupSummaries(rules) {
            const list = document.getElementById('automation-rule-list');
            if (!list || !Array.isArray(rules)) return;
            list.querySelectorAll('.auto-rule-group').forEach(section => {
                const ruleIds = Array.from(section.querySelectorAll('[data-auto-rule-id]')).map(card => String(card.dataset.autoRuleId || ''));
                const groupRules = rules.filter(rule => ruleIds.includes(String(rule?.id || '')));
                const enabled = groupRules.filter(rule => rule?.enabled).length;
                const running = groupRules.filter(rule => rule?.state?.scene_running).length;
                const errors = groupRules.filter(rule => String(rule?.state?.last_error || '').trim()).length;
                const matched = groupRules.filter(rule => ['条件命中', '今日已执行', '执行中'].includes(getAutomationRuleRuntimeMeta(rule).text)).length;
                const waiting = Math.max(groupRules.length - matched - errors - running, 0);
                const summary = section.querySelector('.auto-rule-group-summary');
                section.classList.toggle('has-error', errors > 0);
                section.classList.toggle('has-running', running > 0);
                section.classList.toggle('has-matched', matched > 0);
                if (summary) {
                    summary.textContent = `${groupRules.length} 条 · ${enabled} 启用 · ${matched} 达成 · ${waiting} 等待`;
                }
            });
        }

        function renderAutomationPageStatus(rulesPayload = null, context = {}) {
            const rules = Array.isArray(rulesPayload)
                ? rulesPayload
                : Array.from(getAutomationStatusMapFromContext(context).values());
            const getActiveViewId = context.getActiveViewId || global.getActiveViewId || (() => '');
            if (getActiveViewId() !== 'auto') return;
            if (!document.getElementById('view-auto')) return;
            ensureAutomationRuleGroups(rules);
            const enabledCount = rules.filter(rule => rule && rule.enabled).length;
            const matchedCount = rules.filter(rule => {
                const state = rule?.state || {};
                return !!state.last_trigger_matched || !!state.last_condition_stable || !!state.scene_running;
            }).length;
            const runningCount = rules.filter(rule => !!rule?.state?.scene_running).length;
            const lastRule = rules
                .filter(rule => rule?.state?.last_triggered_at)
                .sort((a, b) => new Date(String(b.state.last_triggered_at).replace(' ', 'T')).getTime() - new Date(String(a.state.last_triggered_at).replace(' ', 'T')).getTime())[0];

            const setText = (id, text) => {
                const el = document.getElementById(id);
                if (el) el.textContent = text;
            };
            setText('auto-kpi-total', String(rules.length || document.querySelectorAll('[data-auto-rule-id]').length));
            setText('auto-kpi-enabled', String(enabledCount));
            setText('auto-kpi-matched', String(matchedCount));
            setText('auto-kpi-running', `执行中 ${runningCount}`);
            setText('auto-kpi-last-rule', lastRule?.name || '暂无');
            setText('auto-kpi-last-time', lastRule?.state?.last_triggered_at ? formatAutomationRuleTime(lastRule.state.last_triggered_at) : '等待运行记录');

            rules.forEach(rule => {
                if (!rule || !rule.id) return;
                const ruleState = rule.state || {};
                const ruleId = String(rule.id);
                const card = document.getElementById(`auto-card-${ruleId}`);
                const stateEl = document.getElementById(`auto-runtime-state-${ruleId}`);
                const valueEl = document.getElementById(`auto-runtime-value-${ruleId}`);
                const lastEl = document.getElementById(`auto-runtime-last-${ruleId}`);
                const sceneEl = document.getElementById(`auto-runtime-scene-${ruleId}`);
                const meta = getAutomationRuleRuntimeMeta(rule);
                if (card) {
                    card.classList.toggle('disabled', !rule.enabled);
                    card.classList.remove('runtime-matched', 'runtime-running', 'runtime-error');
                    if (meta.cardClass) card.classList.add(meta.cardClass);
                }
                if (stateEl) {
                    stateEl.className = `auto-runtime-chip ${meta.cls}`;
                    stateEl.textContent = meta.text;
                    if (ruleState.last_error) stateEl.title = String(ruleState.last_error);
                }
                if (valueEl) {
                    const currentValue = formatAutomationValue(ruleState.current_value);
                    const hitsText = Number(ruleState.hits_required || 0) > 1 ? ` · 命中 ${ruleState.hits || 0}/${ruleState.hits_required}` : '';
                    valueEl.textContent = `当前值 ${currentValue}${hitsText}`;
                }
                if (lastEl) {
                    const lastValue = formatAutomationValue(ruleState.last_trigger_value);
                    const lastTime = formatAutomationRuleTime(ruleState.last_triggered_at);
                    lastEl.textContent = `最近触发 ${lastTime}${lastValue !== '--' ? ` · ${lastValue}` : ''}`;
                }
                if (sceneEl) {
                    sceneEl.textContent = rule.scene_name ? `场景 ${rule.scene_name}` : `场景 ${rule.scene_id || '--'}`;
                    sceneEl.title = rule.scene_id || '';
                }
                renderAutomationConditionChips(rule);
                renderAutomationNodePanel(rule, context);
            });
            updateAutomationGroupSummaries(rules);
        }

        function applyRuleToAutoCard(rule) {
            if (!rule || !rule.id) return;
            const card = document.getElementById(`auto-card-${rule.id}`);
            if (!card) return;
            const descEl = card.querySelector('.desc');
            if (descEl) {
                let desc = '';
                if (rule.trigger_type === 'schedule') {
                    desc = `定时执行，每日 ${rule.schedule?.time || '08:00'}`;
                } else if (rule.trigger_type === 'condition') {
                    desc = `条件触发，当 ${rule.condition?.source_type || 'env'} / ${rule.condition?.prop || 'lux'} ${rule.condition?.op || '<'} ${rule.condition?.value ?? 0} 时`;
                } else if (rule.trigger_type === 'compound') {
                    desc = `组合触发，${String(rule.trigger_mode || 'any') === 'all' ? '全部条件满足才执行' : '任意一个条件满足即执行'}`;
                } else {
                    desc = `混合模式，在 ${rule.schedule?.time_start || '00:00'} - ${rule.schedule?.time_end || '23:59'} 期间，若 ${rule.condition?.source_type || 'env'} / ${rule.condition?.prop || 'lux'} ${rule.condition?.op || '<'} ${rule.condition?.value ?? 0} 则触发`;
                }
                descEl.innerHTML = `${escapeHtml(desc)}<span style="color:var(--brand-blue); margin-left:10px;">触发动作：调用场景联动 [ID: ${escapeHtml(rule.action_scene_id || '')}]</span>`;
            }
        }

        function readAutoField(ruleId, suffix) {
            const el = document.getElementById(`auto-field-${ruleId}-${suffix}`);
            return el ? el.value : '';
        }

        function refreshAutomationAfterWrite(context = {}) {
            const loadStatus = context.loadAutomationStatus || global.loadAutomationStatus;
            const loadLogs = context.loadAutomationLogs || global.loadAutomationLogs;
            setTimeout(() => {
                if (typeof loadStatus === 'function') loadStatus();
                if (typeof loadLogs === 'function') loadLogs();
            }, 120);
        }

        function toggleAutomation(ruleId, isEnabled, context = {}) {
            const ensurePermission = context.ensurePermission || global.ensurePermission || (() => false);
            const postJsonLoose = context.postJsonLoose || global.postJsonLoose;
            const notify = context.showToast || global.showToast || (() => {});
            const translateApiError = context.translateApiError || global.translateApiError || ((msg, fallback) => msg || fallback);
            if (!ensurePermission('automation.edit', '修改自动化规则') || typeof postJsonLoose !== 'function') return;
            postJsonLoose('/api/automation/toggle', { id: ruleId, enabled: isEnabled }, '自动化规则更新失败')
                .then(d => {
                    if (d.success) {
                        notify(isEnabled ? '自动化规则已启用' : '自动化规则已暂停');
                        const card = document.getElementById('auto-card-' + ruleId);
                        if (card) {
                            if (isEnabled) card.classList.remove('disabled');
                            else card.classList.add('disabled');
                        }
                        refreshAutomationAfterWrite(context);
                    } else {
                        notify(d.msg || '自动化规则更新失败', true);
                    }
                })
                .catch(err => notify(translateApiError(err?.message, '自动化规则更新失败'), true));
        }

        function saveAutomationRule(ruleId, context = {}) {
            const ensurePermission = context.ensurePermission || global.ensurePermission || (() => false);
            const postJsonLoose = context.postJsonLoose || global.postJsonLoose;
            const notify = context.showToast || global.showToast || (() => {});
            const translateApiError = context.translateApiError || global.translateApiError || ((msg, fallback) => msg || fallback);
            if (!ensurePermission('automation.edit', '修改自动化规则内部条件') || typeof postJsonLoose !== 'function') return;
            const saveBtn = document.getElementById(`auto-save-btn-${ruleId}`);
            if (saveBtn) saveBtn.disabled = true;
            const payload = {
                id: ruleId,
                trigger_type: String(readAutoField(ruleId, 'trigger_type') || 'condition'),
                action_scene_id: String(readAutoField(ruleId, 'action_scene_id') || '').trim(),
                condition: {
                    source_type: String(readAutoField(ruleId, 'source_type') || 'env'),
                    device_id: String(readAutoField(ruleId, 'device_id') || '').trim(),
                    prop: String(readAutoField(ruleId, 'prop') || 'lux').trim(),
                    op: String(readAutoField(ruleId, 'op') || '<'),
                    value: Number(readAutoField(ruleId, 'value') || 0),
                    debounce_sec: Number(readAutoField(ruleId, 'debounce_sec') || 0),
                    hysteresis: Number(readAutoField(ruleId, 'hysteresis') || 0),
                    consecutive_hits: Number(readAutoField(ruleId, 'consecutive_hits') || 1),
                    crossing_mode: String(readAutoField(ruleId, 'crossing_mode') || 'none'),
                    rearm_value: String(readAutoField(ruleId, 'rearm_value') || '').trim(),
                    window_bootstrap_sec: Number(readAutoField(ruleId, 'window_bootstrap_sec') || 0),
                },
                schedule: {
                    day_type: String(readAutoField(ruleId, 'day_type') || 'everyday'),
                    time: String(readAutoField(ruleId, 'time') || '08:00'),
                    time_start: String(readAutoField(ruleId, 'time_start') || '00:00'),
                    time_end: String(readAutoField(ruleId, 'time_end') || '23:59'),
                }
            };
            postJsonLoose('/api/automation/update', payload, '自动化规则保存失败')
                .then(d => {
                    if (d.success) {
                        notify('自动化规则已保存');
                        if (d.rule) applyRuleToAutoCard(d.rule);
                        toggleAutomationEditor(ruleId, false);
                        refreshAutomationAfterWrite(context);
                    } else {
                        notify(d.msg || '自动化规则保存失败', true);
                    }
                })
                .catch(err => notify(translateApiError(err?.message, '自动化规则保存失败'), true))
                .finally(() => { if (saveBtn) saveBtn.disabled = false; });
        }

        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && document.getElementById('automationNodeModal')?.classList.contains('open')) {
                closeAutomationNodeCanvas();
            }
        });

    Object.assign(state, {
        isAutomationScheduleDoneToday,
        isAutomationScheduleStateDoneToday,
        findAutomationScene,
        getAutomationRuleRuntimeMeta,
        buildAutomationConditionStateChips,
        formatAutomationConditionSummary,
        getAutomationConditionNodeClass,
        formatAutomationScheduleSummary,
        getAutomationScheduleNodeClass,
        formatAutomationActionLabel,
        formatAutomationActionDetails,
        makeAutomationNodeId,
        formatAutomationNodeDetails,
        renderAutomationFlowNode,
        buildAutomationFlowNodes,
        buildAutomationScheduleStateChips,
        buildAutomationConditionChips,
        getAutomationGroupMeta,
        ensureAutomationRuleGroups,
        renderAutomationPageStatus,
        renderAutomationCanvasInspector,
        renderAutomationNodeCanvas,
        openAutomationNodeCanvas,
        closeAutomationNodeCanvas,
        selectAutomationCanvasNode,
        handleAutomationCanvasNodeClick,
        zoomAutomationNodeCanvas,
        fitAutomationNodeCanvas,
        toggleAutomationNodeView,
        toggleAutomationEditor,
        openAutomationCanvasEditor,
        scrollAutomationRuleIntoView,
        toggleAutomation,
        saveAutomationRule,
    });

    Object.assign(global, {
        scrollAutomationRuleIntoView,
        openAutomationCanvasEditor,
    });

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.automation-view', {
            version: '20260522-stage4-automation-view',
            source: 'static/js/views/automation-view.js',
        });
    }
})(window);
