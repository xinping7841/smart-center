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
            if (sub === 'universal') return `泛型 ${actionText}`;
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
    });

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.automation-view', {
            version: '20260522-stage4-automation-view',
            source: 'static/js/views/automation-view.js',
        });
    }
})(window);
