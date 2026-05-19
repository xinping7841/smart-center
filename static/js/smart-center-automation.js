        function getAutomationStatusMap() {
            return new Map((Array.isArray(automationStatusCache.rules) ? automationStatusCache.rules : []).map(item => [String(item.id), item]));
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
        function formatAutomationValue(value) {
            if (value === null || value === undefined || value === '') return '--';
            if (typeof value === 'number' && Number.isFinite(value)) return Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) >= 100 ? 1 : 2).replace(/\.?0+$/, '');
            return String(value);
        }
        function formatAutomationRuleTime(value) {
            if (!value) return '--';
            const text = formatDateTimeText(value);
            return text === '未上报' ? '--' : text;
        }
        function getAutomationTodayKey() {
            const now = new Date();
            const pad = value => String(value).padStart(2, '0');
            return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
        }
        function getAutomationDayLabel(schedule = {}) {
            const dayType = String(schedule.day_type || 'everyday');
            if (dayType === 'workday') return '工作日';
            if (dayType === 'weekend') return '周末';
            if (dayType === 'custom') return '自定义日期';
            return '每天';
        }
        function getAutomationSourceLabel(sourceType) {
            const map = { env: '环境', screen: '幕布', power: '强电', sequencer: '时序电源', light: '灯光', meter: '电表', server: '服务器', hvac: '空调' };
            return map[String(sourceType || 'env')] || String(sourceType || '数据源');
        }
        function getAutomationPropLabel(prop) {
            const map = { lux: '光照', illuminance: '光照', temp: '温度', temperature: '温度', hum: '湿度', humidity: '湿度', online: '在线', current: '电流', power: '电源', mode: '模式', hvac_action: '运行状态', all_on: '全部开启', all_off: '全部关闭', on_count: '开启路数', off_count: '关闭路数', channel_state: '通道状态', running: '运行中', locked: '锁定' };
            return map[String(prop || '').toLowerCase()] || String(prop || '属性');
        }
        function getAutomationPropUnit(prop) {
            const key = String(prop || '').toLowerCase();
            if (['lux', 'illuminance'].includes(key)) return ' lux';
            if (['temp', 'temperature'].includes(key)) return '°C';
            if (['hum', 'humidity'].includes(key)) return '%';
            if (key === 'current') return ' A';
            if (key === 'power') return ' W';
            if (['on_count', 'off_count'].includes(key)) return ' 路';
            return '';
        }
        function formatAutomationValueWithUnit(value, prop) {
            if (typeof value === 'boolean') {
                const key = String(prop || '').toLowerCase();
                if (key === 'online') return value ? '在线' : '离线';
                if (key === 'all_on') return value ? '已全开' : '未全开';
                if (key === 'all_off') return value ? '已全关' : '未全关';
                if (key === 'locked') return value ? '已锁定' : '未锁定';
                if (key === 'running') return value ? '运行中' : '待机';
                return value ? '开' : '关';
            }
            const text = formatAutomationValue(value);
            if (text === '--') return text;
            return `${text}${getAutomationPropUnit(prop)}`;
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
        function isAutomationScheduleDoneToday(rule) {
            const state = rule?.state || {};
            const today = getAutomationTodayKey();
            return String(state.last_schedule_day || '') === today || String(state.last_schedule_key || '').startsWith(today);
        }
        function isAutomationScheduleStateDoneToday(triggerState = {}) {
            const today = getAutomationTodayKey();
            return String(triggerState.last_schedule_day || '') === today || String(triggerState.last_schedule_key || '').startsWith(today);
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
        function findAutomationScene(sceneId) {
            const id = String(sceneId || '').trim();
            return (Array.isArray(configData.scenes) ? configData.scenes : []).find(scene => String(scene?.id || '') === id) || null;
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
        function formatAutomationActionDetails(action = {}) {
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
        function buildAutomationFlowNodes(rule = {}) {
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

            const scene = findAutomationScene(rule.scene_id || rule.action_scene_id);
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
                    meta: formatAutomationActionDetails(action),
                    details: formatAutomationActionDetails(action).concat([
                        `子系统 ${action.sub_system || '--'}`,
                        `动作类型 ${action.action_type || action.action || '--'}`
                    ]),
                    editable: false
                });
            });
            return nodes;
        }
        function getActiveAutomationCanvasRule() {
            if (!activeAutomationCanvasRuleId) return null;
            return getAutomationStatusMap().get(String(activeAutomationCanvasRuleId))
                || (Array.isArray(configData.automations) ? configData.automations : []).find(item => String(item?.id || '') === String(activeAutomationCanvasRuleId))
                || null;
        }
        function renderAutomationCanvasInspector(rule, node) {
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
        window.zoomAutomationNodeCanvas = zoomAutomationNodeCanvas;
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
        window.fitAutomationNodeCanvas = fitAutomationNodeCanvas;
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
            window.addEventListener('mousemove', moveAutomationCanvasPan);
            window.addEventListener('mouseup', endAutomationCanvasPan);
            canvas.addEventListener('touchstart', startAutomationCanvasPan, { passive: false });
            window.addEventListener('touchmove', moveAutomationCanvasPan, { passive: false });
            window.addEventListener('touchend', endAutomationCanvasPan, { passive: false });
            window.addEventListener('touchcancel', endAutomationCanvasPan, { passive: false });
        }
        function handleAutomationCanvasNodeClick(event, nodeId) {
            if (Date.now() < automationCanvasSuppressClickUntil) {
                event?.preventDefault?.();
                event?.stopPropagation?.();
                return false;
            }
            selectAutomationCanvasNode(nodeId);
            return true;
        }
        window.handleAutomationCanvasNodeClick = handleAutomationCanvasNodeClick;
        function renderAutomationNodeCanvas(rule) {
            const canvas = document.getElementById('automation-node-canvas');
            const title = document.getElementById('automationNodeModalTitle');
            const sub = document.getElementById('automationNodeModalSub');
            const editBtn = document.getElementById('auto-node-edit-shortcut');
            if (!canvas || !rule) return;
            bindAutomationCanvasPan();
            const nodes = buildAutomationFlowNodes(rule);
            if (!nodes.some(node => node.id === activeAutomationCanvasNodeId)) {
                activeAutomationCanvasNodeId = nodes[0]?.id || '';
            }
            if (title) title.textContent = rule.name || rule.id || '自动化规则';
            if (sub) {
                const scene = findAutomationScene(rule.scene_id || rule.action_scene_id);
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
            renderAutomationCanvasInspector(rule, selected);
        }
        function openAutomationNodeCanvas(ruleId) {
            const modal = document.getElementById('automationNodeModal');
            if (!modal) return;
            activeAutomationCanvasRuleId = String(ruleId || '');
            activeAutomationCanvasNodeId = '';
            automationCanvasZoom = 1;
            automationCanvasPanX = 0;
            automationCanvasPanY = 0;
            const rule = getActiveAutomationCanvasRule();
            if (!rule) {
                showToast('未找到自动化规则，稍后自动刷新后再试', true);
                loadAutomationStatus(true);
                return;
            }
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
            document.body.classList.add('auto-node-modal-open');
            renderAutomationNodeCanvas(rule);
            requestAnimationFrame(() => fitAutomationNodeCanvas());
        }
        window.openAutomationNodeCanvas = openAutomationNodeCanvas;
        function closeAutomationNodeCanvas() {
            const modal = document.getElementById('automationNodeModal');
            if (!modal) return;
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('auto-node-modal-open');
        }
        window.closeAutomationNodeCanvas = closeAutomationNodeCanvas;
        function selectAutomationCanvasNode(nodeId) {
            activeAutomationCanvasNodeId = String(nodeId || '');
            const rule = getActiveAutomationCanvasRule();
            if (rule) renderAutomationNodeCanvas(rule);
        }
        window.selectAutomationCanvasNode = selectAutomationCanvasNode;
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && document.getElementById('automationNodeModal')?.classList.contains('open')) {
                closeAutomationNodeCanvas();
            }
        });
        function openAutomationCanvasEditor(editTarget = '') {
            const rule = getActiveAutomationCanvasRule();
            if (!rule || !rule.id) return;
            if (String(rule.trigger_type || '') === 'compound') {
                showToast('组合规则结构更复杂，当前先支持节点查看，编辑会单独做安全版本。', true);
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
        function scrollAutomationRuleIntoView(ruleId) {
            const card = document.getElementById(`auto-card-${ruleId}`);
            if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        function renderAutomationNodePanel(rule) {
            if (!rule || !rule.id) return;
            const panel = document.getElementById(`auto-node-panel-${rule.id}`);
            if (!panel || !panel.classList.contains('open')) return;
            const nodes = buildAutomationFlowNodes(rule);
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
        function toggleAutomationNodeView(ruleId, forceOpen = null) {
            const panel = document.getElementById(`auto-node-panel-${ruleId}`);
            const btn = document.querySelector(`[data-auto-node-btn="${ruleId}"]`);
            if (!panel) return;
            const shouldOpen = forceOpen === null ? !panel.classList.contains('open') : !!forceOpen;
            panel.classList.toggle('open', shouldOpen);
            if (btn) btn.textContent = shouldOpen ? '收起节点' : '节点视图';
            if (shouldOpen) {
                const rule = getAutomationStatusMap().get(String(ruleId)) || { id: ruleId, name: panel.closest('[data-auto-rule-name]')?.dataset?.autoRuleName || '' };
                renderAutomationNodePanel(rule);
            }
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
        function renderAutomationPageStatus() {
            const rules = Array.isArray(automationStatusCache.rules) ? automationStatusCache.rules : [];
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
                const state = rule.state || {};
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
                    if (state.last_error) stateEl.title = String(state.last_error);
                }
                if (valueEl) {
                    const currentValue = formatAutomationValue(state.current_value);
                    const hitsText = Number(state.hits_required || 0) > 1 ? ` · 命中 ${state.hits || 0}/${state.hits_required}` : '';
                    valueEl.textContent = `当前值 ${currentValue}${hitsText}`;
                }
                if (lastEl) {
                    const lastValue = formatAutomationValue(state.last_trigger_value);
                    const lastTime = formatAutomationRuleTime(state.last_triggered_at);
                    lastEl.textContent = `最近触发 ${lastTime}${lastValue !== '--' ? ` · ${lastValue}` : ''}`;
                }
                if (sceneEl) {
                    sceneEl.textContent = rule.scene_name ? `场景 ${rule.scene_name}` : `场景 ${rule.scene_id || '--'}`;
                    sceneEl.title = rule.scene_id || '';
                }
                renderAutomationConditionChips(rule);
                renderAutomationNodePanel(rule);
            });
            updateAutomationGroupSummaries(rules);
        }
        function getAutomationLogLevel(log) {
            const op = String(log?.operation || '').toLowerCase();
            const status = String(log?.status || '').toLowerCase();
            if (status === 'error' || op.includes('失败') || op.includes('异常') || op.includes('missing') || op.includes('failed')) return 'error';
            if (op.includes('skip') || op.includes('skipped') || op.includes('timeout') || op.includes('停用') || op.includes('跳过')) return 'warning';
            if (op.includes('completed') || op.includes('triggered') || op.includes('启用') || op.includes('执行')) return 'success';
            return '';
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
        function renderAutomationLogs() {
            const list = document.getElementById('automation-runtime-log-list');
            if (!list) return;
            const logs = sortLogsNewestFirst(automationLogCache).slice(0, 80);
            const summary = document.getElementById('auto-log-summary');
            if (summary) summary.textContent = logs.length ? `最近 ${logs.length} 条自动化和场景联动记录` : '暂无自动化执行记录';
            if (!logs.length) {
                list.innerHTML = '<div class="auto-log-empty">暂无自动化运行记录。规则触发、场景开始/完成、失败会显示在这里。</div>';
                return;
            }
            list.innerHTML = logs.map(log => {
                const cls = getAutomationLogLevel(log);
                const message = escapeHtml(normalizeAutomationLogText(log));
                const rawMessage = escapeHtml(String(log?.operation || ''));
                return `<div class="auto-log-item ${cls}" title="${rawMessage}">
                    <div class="auto-log-time">${escapeHtml(formatDateTimeText(log?.time || ''))}</div>
                    <div class="auto-log-message">${message}</div>
                </div>`;
            }).join('');
        }
        function getEnvConfigById(deviceId) {
            const targetId = String(deviceId || '').trim();
            if (!targetId) return null;
            return envConfigs.find(cfg => String(cfg.id) === targetId) || null;
        }
        function isContactLikeEnvSensor(cfg) {
            const features = cfg?.features || {};
            const text = `${cfg?.id || ''} ${cfg?.name || ''} ${cfg?.model || ''} ${cfg?.note || ''}`.toLowerCase();
            return features.temperature === false
                && features.humidity === false
                && /大门|门窗|门磁|开关|contact|door|gate|window/.test(text);
        }
        const ENV_FEATURE_DEFAULTS = {
            temperature: true,
            humidity: true,
            illuminance: true,
            contact: true,
            light: true,
            battery: true,
            voltage: true,
            noise: false,
            pm25: false,
            pm10: false,
            pressure: false
        };
        const ENV_PRIMARY_METRIC_ORDER = ['contact', 'illuminance', 'temperature', 'humidity', 'light', 'battery', 'voltage', 'noise', 'pm25', 'pm10', 'pressure'];
        function getEnvFeatures(cfg) {
            return Object.assign({}, ENV_FEATURE_DEFAULTS, cfg?.features || {});
        }
        function envFeatureEnabled(features, key) {
            return (features || {})[key] !== false;
        }
        function getOutdoorGateSensorSnapshot(envData = null) {
            const data = envData && typeof envData === 'object' ? envData : (window.__envStatusCache || {});
            const candidates = envConfigs
                .map(cfg => {
                    const text = `${cfg?.id || ''} ${cfg?.name || ''} ${cfg?.model || ''} ${cfg?.note || ''}`.toLowerCase();
                    const st = data[cfg.id] || {};
                    let score = -100;
                    if (isContactLikeEnvSensor(cfg)) score += 80;
                    if (/户外大门|大门|gate/.test(text)) score += 35;
                    if (/contact|door|门窗|门磁|开关/.test(text)) score += 20;
                    if (typeof st.contact === 'boolean' || typeof st.opening === 'boolean' || st.contact_text) score += 30;
                    if (st.online) score += 10;
                    return { cfg, st, score };
                })
                .filter(item => item.score > 0)
                .sort((left, right) => right.score - left.score);
            return candidates[0] || null;
        }
        function resolveOutdoorGateState(st = {}) {
            if (!st || st.online === false) {
                return { status: 'offline', text: '离线', className: 'blue' };
            }
            if (typeof st.contact === 'boolean') {
                return st.contact
                    ? { status: 'open', text: '已打开', className: 'danger' }
                    : { status: 'closed', text: '已关闭', className: 'green' };
            }
            if (typeof st.opening === 'boolean') {
                return st.opening
                    ? { status: 'open', text: '已打开', className: 'danger' }
                    : { status: 'closed', text: '已关闭', className: 'green' };
            }
            const text = String(st.contact_text || st.state || '').trim();
            if (/开|open/i.test(text)) return { status: 'open', text: '已打开', className: 'danger' };
            if (/关|close|closed/i.test(text)) return { status: 'closed', text: '已关闭', className: 'green' };
            return { status: 'unknown', text: '门磁未知', className: 'blue' };
        }
        function updateDashboardDoorStatusFromEnv(envData = null) {
            const dashStatus = document.getElementById('dash-door-status');
            if (!dashStatus) return false;
            const snapshot = getOutdoorGateSensorSnapshot(envData);
            if (!snapshot) return false;
            const gateState = resolveOutdoorGateState(snapshot.st);
            dashStatus.textContent = gateState.text;
            dashStatus.className = `value ${gateState.className}`;
            dashStatus.title = `${snapshot.cfg?.name || '户外大门'} · 来源：门磁传感器`;
            return true;
        }
        function updateDashboardDoorStatusFromVision(data = {}) {
            const dashStatus = document.getElementById('dash-door-status');
            if (!dashStatus) return;
            dashStatus.textContent = String(data.msg || '').replace(/[\u2705\uD83D\uDEAA\u23F3\u26A0\uFE0F\u23F8\uFE0F\u23F8]\s*/g, '');
            dashStatus.title = '来源：视觉识别辅助';
            if (data.door_status === 'opening' || data.door_status === 'closing') dashStatus.className = 'value highlight';
            else if (data.door_status === 'open') dashStatus.className = 'value danger';
            else if (data.door_status === 'closed') dashStatus.className = 'value green';
            else dashStatus.className = 'value blue';
        }
        function getEnvDashboardScore(cfg, st) {
            if (!cfg || !st || !st.online) return -999;
            const features = cfg.features || {};
            let score = 0;
            if (features.illuminance !== false) score += 10;
            if (features.temperature !== false) score += 8;
            if (features.humidity !== false) score += 8;
            if (features.temperature !== false && features.humidity !== false) score += 8;
            const text = `${cfg.id || ''} ${cfg.name || ''} ${cfg.model || ''} ${cfg.note || ''}`.toLowerCase();
            if (/光照温湿度|温湿度变送器|温湿度|环境/.test(text)) score += 12;
            if (isContactLikeEnvSensor(cfg)) score -= 30;
            return score;
        }
        function resolveOutdoorAutomationSensor(rule, envData) {
            const data = envData && typeof envData === 'object' ? envData : (window.__envStatusCache || {});
            const configuredId = String(rule?.state?.resolved_device_id || rule?.condition?.device_id || '').trim();
            let sensorCfg = getEnvConfigById(configuredId);
            if (!sensorCfg || isContactLikeEnvSensor(sensorCfg)) {
                sensorCfg = envConfigs
                    .map(cfg => ({ cfg, st: data[cfg.id] || {} }))
                    .sort((left, right) => getEnvDashboardScore(right.cfg, right.st) - getEnvDashboardScore(left.cfg, left.st))
                    .find(item => getEnvDashboardScore(item.cfg, item.st) > -999)?.cfg
                    || envConfigs.find(cfg => ((cfg.features || {}).illuminance !== false) && !isContactLikeEnvSensor(cfg))
                    || envConfigs[0]
                    || null;
            }
            const sensorState = sensorCfg ? (data[sensorCfg.id] || null) : null;
            return {
                sensorId: sensorCfg ? String(sensorCfg.id) : configuredId,
                sensorCfg,
                sensorState,
            };
        }
        function pickDashboardEnvSensor(envData) {
            const runtimeMap = getAutomationStatusMap();
            const outdoorSensor = resolveOutdoorAutomationSensor(runtimeMap.get('auto_outdoor_light_low_lux_on'), envData);
            if (outdoorSensor.sensorCfg && outdoorSensor.sensorState && outdoorSensor.sensorState.online) {
                return { cfg: outdoorSensor.sensorCfg, st: outdoorSensor.sensorState };
            }
            return envConfigs
                .map(cfg => ({ cfg, st: envData[cfg.id] || { online: false } }))
                .sort((left, right) => getEnvDashboardScore(right.cfg, right.st) - getEnvDashboardScore(left.cfg, left.st))
                .find(item => getEnvDashboardScore(item.cfg, item.st) > -999)
                || envConfigs.map(cfg => ({ cfg, st: envData[cfg.id] || { online: false } })).find(item => item.st && item.st.online)
                || null;
        }
        function getTodayTargetDateTime(timeText='20:00') {
            const now = new Date();
            const [h, m] = String(timeText || '20:00').split(':').map(v => parseInt(v, 10) || 0);
            const dt = new Date(now);
            dt.setHours(h, m, 0, 0);
            return dt;
        }
        function formatCountdownText(target) {
            if (!(target instanceof Date) || Number.isNaN(target.getTime())) return '未知';
            const now = new Date();
            let diff = Math.floor((target.getTime() - now.getTime()) / 1000);
            if (diff <= 0) return '已到时间';
            const hours = Math.floor(diff / 3600);
            diff -= hours * 3600;
            const minutes = Math.floor(diff / 60);
            const seconds = diff - minutes * 60;
            if (hours > 0) return `${hours}小时 ${minutes}分钟`;
            if (minutes > 0) return `${minutes}分钟 ${seconds}秒`;
            return `${seconds}秒`;
        }
        function formatLuxTrendSummary(trend, threshold, currentLux) {
            if (!trend || typeof trend !== 'object') {
                return { eta: '--', note: '趋势数据尚未建立' };
            }
            const current = Number(currentLux);
            const thresholdNum = Number(threshold);
            const etaSec = Number(trend.estimate_to_threshold_sec);
            const direction = String(trend.direction || 'unknown');
            const slope = Number(trend.slope_lux_per_min);
            if (Number.isFinite(etaSec)) {
                if (etaSec <= 0) {
                    if (Number.isFinite(current) && Number.isFinite(thresholdNum) && current > thresholdNum) {
                        return {
                            eta: '高于阈值',
                            note: `当前 ${current.toFixed(0)} lux，高于阈值 ${thresholdNum.toFixed(0)} lux`
                        };
                    }
                    return {
                        eta: '低于阈值',
                        note: Number.isFinite(current) && Number.isFinite(thresholdNum)
                            ? `当前 ${current.toFixed(0)} lux，已低于阈值 ${thresholdNum.toFixed(0)} lux`
                            : '当前已低于触发阈值'
                    };
                }
                const directionText = direction === 'falling' ? '正在变暗' : (direction === 'rising' ? '正在变亮' : '趋势变化中');
                return {
                    eta: formatRelativeSeconds(etaSec),
                    note: `${directionText}，约 ${formatRelativeSeconds(etaSec)} 后接近阈值`
                };
            }
            if (direction === 'falling' && Number.isFinite(slope)) {
                return { eta: '趋势建立中', note: `光照下降约 ${Math.abs(slope).toFixed(1)} lux/分钟，继续观察是否靠近阈值` };
            }
            if (direction === 'rising' && Number.isFinite(slope)) {
                return { eta: '暂无风险', note: `光照回升约 ${Math.abs(slope).toFixed(1)} lux/分钟` };
            }
            if (direction === 'stable') {
                return { eta: '基本稳定', note: '光照波动较小，暂未接近自动开灯条件' };
            }
            return { eta: '--', note: '趋势数据尚未建立' };
        }
        function formatAutomationWindowText(schedule = {}) {
            const start = schedule.time_start || '00:00';
            const end = schedule.time_end || '23:59';
            return `${start}-${end}`;
        }
        function getAutomationWindowNextText(schedule = {}, inWindow = false) {
            const startText = schedule.time_start || '00:00';
            const endText = schedule.time_end || '23:59';
            if (inWindow) return `${endText}前有效`;
            const startTarget = getTodayTargetDateTime(startText);
            const endTarget = getTodayTargetDateTime(endText);
            const now = new Date();
            if (now < startTarget) return `${startText}开始`;
            if (now > endTarget) return `明日${startText}`;
            return `${startText}-${endText}`;
        }
        function getAutomationOffPlanText(rule) {
            const timeText = rule?.schedule?.time || '20:00';
            const target = getTodayTargetDateTime(timeText);
            const countdown = formatCountdownText(target);
            return countdown === '已到时间' ? `${timeText}已到` : `${timeText}关灯`;
        }
        function renderOutdoorAutomationDashboardCard() {
            const runtimeMap = getAutomationStatusMap();
            const onRule = runtimeMap.get('auto_outdoor_light_low_lux_on');
            const offRule = runtimeMap.get('auto_outdoor_light_20_off');
            const card = document.getElementById('dash-outdoor-automation-card');
            if (!card) return;
            const luxEl = document.getElementById('dash-outdoor-lux');
            const statusEl = document.getElementById('dash-outdoor-status-text');
            const etaEl = document.getElementById('dash-outdoor-eta');
            const offEl = document.getElementById('dash-outdoor-off-countdown');
            const windowEl = document.getElementById('dash-outdoor-window');
            const debounceEl = document.getElementById('dash-outdoor-debounce');
            const noteEl = document.getElementById('dash-outdoor-note');
            const chipEl = document.getElementById('dash-outdoor-auto-chip');
            if (!onRule && !offRule) {
                card.style.opacity = '0.72';
                if (luxEl) luxEl.textContent = '--';
                if (statusEl) statusEl.textContent = '未找到户外灯自动化规则';
                if (etaEl) etaEl.textContent = '--';
                if (offEl) offEl.textContent = '--';
                if (windowEl) windowEl.textContent = '--';
                if (debounceEl) debounceEl.textContent = '--';
                if (noteEl) noteEl.textContent = '请先配置 auto_outdoor_light_low_lux_on 与 auto_outdoor_light_20_off。';
                if (chipEl) {
                    chipEl.textContent = '未配置';
                    chipEl.className = 'outdoor-auto-chip';
                }
                return;
            }

            const outdoorSensor = resolveOutdoorAutomationSensor(onRule);
            const runtimeLux = toFiniteNumber(onRule?.state?.current_value);
            const liveLux = toFiniteNumber(outdoorSensor.sensorState?.lux);
            const currentLux = runtimeLux !== null ? runtimeLux : liveLux;
            const threshold = toFiniteNumber(onRule?.condition?.value) ?? 300;
            const inWindow = !!onRule?.state?.last_in_window;
            const debounceSec = Number(onRule?.state?.debounce_sec || 0);
            const ready = !!onRule?.state?.last_trigger_matched;
            const crossingMode = String(onRule?.state?.crossing_mode || onRule?.condition?.crossing_mode || 'none');
            const crossingReady = onRule?.state?.crossing_ready !== false;
            const rearmValue = Number(onRule?.state?.rearm_value ?? onRule?.condition?.rearm_value);
            const lastBaseMatch = !!onRule?.state?.last_base_match;
            const lastSkipReason = String(onRule?.state?.last_skip_reason || '');
            const windowBootstrapSec = Number(onRule?.condition?.window_bootstrap_sec || 0);
            const sensorName = outdoorSensor.sensorCfg?.name || '户外传感器';
            const usingLiveSensorFallback = runtimeLux === null && liveLux !== null;
            const windowText = formatAutomationWindowText(onRule?.schedule || {});
            const windowStateText = getAutomationWindowNextText(onRule?.schedule || {}, inWindow);
            const rearmText = Number.isFinite(rearmValue) ? `${rearmValue.toFixed(0)} lux` : '回升';
            const triggerText = crossingMode === 'cross_down'
                ? `跌破${threshold.toFixed(0)} lux`
                : `低于${threshold.toFixed(0)} lux`;
            const debounceText = debounceSec > 0 ? ` ${formatRelativeSeconds(debounceSec)}` : '';
            const conditionText = `${triggerText}${debounceText}`;
            const resetText = crossingMode === 'cross_down' ? `${rearmText}复位` : '自动复位';
            const offPlanText = getAutomationOffPlanText(offRule);

            let chipText = '观察中';
            let chipClass = 'outdoor-auto-chip';
            let statusText = '正在等待光照与自动化状态...';
            if (ready) {
                chipText = '满足触发';
                chipClass += ' good';
                statusText = '已满足开灯条件，自动化可执行';
            } else if (currentLux !== null) {
                if (!inWindow) {
                    chipText = '时间窗外';
                    statusText = currentLux <= threshold
                        ? '光照已低，但未到开灯窗口'
                        : '未到开灯窗口，当前光照充足';
                } else if (currentLux <= threshold) {
                    if (crossingMode === 'cross_down' && !crossingReady) {
                        chipText = '已触发待复位';
                        statusText = Number.isFinite(rearmValue)
                            ? `已开过灯，需回升到 ${rearmValue.toFixed(0)} lux 后复位`
                            : '已开过灯，需明显回升后复位';
                    } else if (lastSkipReason.startsWith('window_bootstrap_after_')) {
                        chipText = '补触发就绪';
                        chipClass += ' warn';
                        statusText = '窗口内持续低照度，补触发可执行';
                    } else if (crossingMode === 'cross_down' && !lastBaseMatch) {
                        chipText = '等待变暗';
                        chipClass += ' warn';
                        statusText = '等待光照从亮转暗跌破阈值';
                    } else {
                        chipText = '确认中';
                        chipClass += ' warn';
                        statusText = '光照已低，正在确认是否稳定';
                    }
                } else {
                    chipText = '监测中';
                    statusText = '窗口内监测中，光照高于开灯阈值';
                }
            } else if (outdoorSensor.sensorCfg) {
                chipText = '等待数据';
                chipClass += ' warn';
                statusText = `正在等待 ${sensorName} 上报实时光照`;
            }

            card.style.opacity = '1';
            if (luxEl) luxEl.textContent = currentLux !== null ? `${currentLux.toFixed(0)} lux` : '--';
            if (statusEl) statusEl.textContent = statusText;
            if (etaEl) etaEl.textContent = windowStateText;
            if (offEl) offEl.textContent = offPlanText;
            if (windowEl) windowEl.textContent = conditionText;
            if (debounceEl) debounceEl.textContent = resetText;
            if (noteEl) {
                let ruleNote = `规则：${windowText}，${conditionText} 开灯，${offPlanText}。`;
                if (windowBootstrapSec > 0) {
                    ruleNote += ` 低照度入窗 ${formatRelativeSeconds(windowBootstrapSec)} 后补开。`;
                }
                if (usingLiveSensorFallback) {
                    ruleNote += ` 使用 ${sensorName} 实时值。`;
                } else if (outdoorSensor.sensorCfg) {
                    ruleNote += ` 来源：${sensorName}。`;
                }
                const lastText = formatDateTimeText(onRule?.state?.last_evaluated_at || automationStatusCache.server_time || '');
                noteEl.textContent = `${ruleNote}更新 ${lastText}`;
            }
            if (chipEl) {
                chipEl.textContent = chipText;
                chipEl.className = chipClass;
            }
        }
        async function loadAutomationStatus(showError=false) {
            if (automationStatusLoading) return;
            automationStatusLoading = true;
            try {
                const data = await fetchJson('/api/automation/status', {}, '自动化状态读取失败');
                automationStatusCache = {
                    server_time: data.server_time || '',
                    rules: Array.isArray(data.rules) ? data.rules : []
                };
                const rules = automationStatusCache.rules || [];
                const dashAutoTotal = document.getElementById('dash-auto-total');
                const dashAutoEnabled = document.getElementById('dash-auto-enabled');
                const dashAutoErrors = document.getElementById('dash-auto-errors');
                const enabledCount = rules.filter(item => item && item.enabled).length;
                const errorCount = rules.filter(item => item && String(item.last_error || '').trim()).length;
                if (dashAutoTotal) dashAutoTotal.innerText = String(rules.length);
                if (dashAutoEnabled) dashAutoEnabled.innerText = String(enabledCount);
                if (dashAutoErrors) dashAutoErrors.innerText = String(errorCount);
                renderOutdoorAutomationDashboardCard();
                renderAutomationPageStatus();
            } catch (err) {
                if (showError) showToast(err.message || '自动化状态读取失败', true);
                console.error('自动化状态读取失败', err);
            } finally {
                automationStatusLoading = false;
            }
        }
        async function loadAutomationLogs(showError=false) {
            if (automationLogLoading) return;
            automationLogLoading = true;
            try {
                const data = await fetchJson('/api/automation/logs?limit=80', {}, '自动化日志读取失败');
                automationLogCache = Array.isArray(data.items) ? data.items : [];
                renderAutomationLogs();
            } catch (err) {
                if (showError) showToast(err.message || '自动化日志读取失败', true);
                console.error('自动化日志读取失败', err);
            } finally {
                automationLogLoading = false;
            }
        }
