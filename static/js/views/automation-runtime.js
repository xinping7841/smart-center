// AI_MODULE: automation_runtime
// AI_PURPOSE: 自动化状态轮询、首页户外灯自动化卡片和自动化页面桥接。
// AI_BOUNDARY: 不在前端做最终触发决策；真实规则求值和设备执行仍在后端 runtime/automation.py。
// AI_DATA_FLOW: /api/automation/status + 环境缓存 -> 首页 KPI / 户外灯自动化卡 / auto 页面。
// AI_RUNTIME: 首页和自动化页面按需加载，保留旧全局函数兼容内联 onclick。
// AI_RISK: 中，必须保持 /api/automation/status 读取和 automation-view 编辑桥接兼容。
// AI_SEARCH_KEYWORDS: automation runtime, outdoor light, dashboard automation, auto page.

(function installSmartCenterAutomationRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.automationRuntime = Object.assign({
        automationStatusCache: { server_time: '', rules: [] },
        automationStatusLoading: false,
    }, SmartCenter.automationRuntime || {});

    function getContext(ctx = null) {
        if (ctx && typeof ctx === 'object') return ctx;
        if (typeof global.getAutomationRuntimeContext === 'function') return global.getAutomationRuntimeContext();
        return {
            configData: global.configData || {},
            currentUser: global.currentUser || {},
            getActiveViewId: global.getActiveViewId || (() => 'dashboard'),
            ensureModulesReady: SmartCenter.ensureModules || (() => Promise.resolve([])),
            ensureViewReady: SmartCenter.ensureViewModules || (() => Promise.resolve([])),
            fetchJson: global.fetchJson || utils.fetchJson,
            postJsonLoose: global.postJsonLoose || utils.postJsonLoose,
            translateApiError: global.translateApiError || utils.translateApiError || ((_, fallback) => fallback),
            showToast: global.showToast || utils.showToast || (() => {}),
            ensurePermission: global.ensurePermission || utils.ensurePermission || (() => false),
            applyPermissionUI: global.applyPermissionUI || (() => {}),
            scheduleDashboardMasonry: global.scheduleDashboardMasonry || (() => {}),
            escapeHtml: global.escapeHtml || utils.escapeHtml || (value => String(value ?? '')),
            loadAutomationLogs: SmartCenter.logs?.loadAutomationLogs || global.loadAutomationLogs,
            envConfigs: Array.isArray(global.__envConfigsCache) ? global.__envConfigsCache : [],
        };
    }

    function getAutomationStatusMap() {
        return new Map((Array.isArray(state.automationStatusCache.rules) ? state.automationStatusCache.rules : []).map(item => [String(item.id), item]));
    }

    function getAutomationStatusCache() {
        return state.automationStatusCache;
    }

    function getAutomationViewApi() {
        return SmartCenter.automationView || null;
    }

    function ensureAutomationViewReady(contextLabel = '自动化详情模块', ctx = null) {
        const runtimeCtx = getContext(ctx);
        if (getAutomationViewApi()) return Promise.resolve(getAutomationViewApi());
        return runtimeCtx.ensureModulesReady(['automation-view'], contextLabel).then(() => getAutomationViewApi());
    }

    function buildAutomationViewContext(ctx = null) {
        const runtimeCtx = getContext(ctx);
        return Object.assign({}, runtimeCtx, {
            getAutomationStatusCache,
            getAutomationStatusMap,
            loadAutomationStatus: showError => loadAutomationStatus(showError, runtimeCtx),
            loadAutomationLogs: SmartCenter.logs?.loadAutomationLogs || global.loadAutomationLogs || runtimeCtx.loadAutomationLogs,
            formatAutomationRuleTime: utils.formatAutomationRuleTime || global.formatAutomationRuleTime || (value => value || '--'),
            formatAutomationValue: utils.formatAutomationValue || global.formatAutomationValue || (value => (value === undefined || value === null || value === '' ? '--' : String(value))),
        });
    }

    function renderAutomationPageStatus(ctx = null) {
        const runtimeCtx = getContext(ctx);
        const rules = Array.isArray(state.automationStatusCache.rules) ? state.automationStatusCache.rules : [];
        if (runtimeCtx.getActiveViewId() !== 'auto') return;
        if (!document.getElementById('view-auto')) return;
        ensureAutomationViewReady('自动化运行页面模块', runtimeCtx)
            .then(api => {
                api?.renderAutomationPageStatus?.(rules, buildAutomationViewContext(runtimeCtx));
                runtimeCtx.applyPermissionUI();
            })
            .catch(() => {});
    }

    function renderAutomationLazyPage(ctx = null) {
        const runtimeCtx = getContext(ctx);
        return runtimeCtx.ensureViewReady('auto')
            .then(() => {
                const api = getAutomationViewApi();
                if (!api?.renderAutomationViewShell) throw new Error('automation_view_api_unavailable');
                api.renderAutomationViewShell();
                runtimeCtx.applyPermissionUI();
                return loadAutomationStatus(true, runtimeCtx);
            })
            .then(() => {
                const loadLogs = SmartCenter.logs?.loadAutomationLogs || global.loadAutomationLogs || runtimeCtx.loadAutomationLogs;
                return typeof loadLogs === 'function' ? loadLogs() : null;
            })
            .catch(err => {
                console.error('自动化运行页面初始化失败', err);
                const container = document.getElementById('view-auto');
                if (container) {
                    container.innerHTML = `
                        <div class="card lazy-view-placeholder">
                            <div style="font-weight:800;margin-bottom:8px;">自动化运行页面加载失败</div>
                            <div style="color:var(--muted);font-size:13px;">请刷新页面重试；若持续出现，请检查 automation-view 模块加载状态。</div>
                        </div>
                    `;
                }
                runtimeCtx.showToast('自动化运行页面加载失败，请刷新后重试', true);
                return null;
            });
    }

    function getEnvConfigs(ctx = null) {
        const runtimeCtx = getContext(ctx);
        return Array.isArray(runtimeCtx.envConfigs) ? runtimeCtx.envConfigs : [];
    }

    function getEnvConfigById(deviceId, ctx = null) {
        const targetId = String(deviceId || '').trim();
        if (!targetId) return null;
        return getEnvConfigs(ctx).find(cfg => String(cfg.id) === targetId) || null;
    }

    function isContactLikeEnvSensor(cfg) {
        const features = cfg?.features || {};
        const text = `${cfg?.id || ''} ${cfg?.name || ''} ${cfg?.model || ''} ${cfg?.note || ''}`.toLowerCase();
        return features.temperature === false
            && features.humidity === false
            && /大门|门窗|门磁|开关|contact|door|gate|window/.test(text);
    }

    function getOutdoorGateSensorSnapshot(envData = null, ctx = null) {
        const data = envData && typeof envData === 'object' ? envData : (global.__envStatusCache || {});
        const candidates = getEnvConfigs(ctx)
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

    function updateDashboardDoorStatusFromEnv(envData = null, ctx = null) {
        const dashStatus = document.getElementById('dash-door-status');
        if (!dashStatus) return false;
        const snapshot = getOutdoorGateSensorSnapshot(envData, ctx);
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

    function resolveOutdoorAutomationSensor(rule, envData = null, ctx = null) {
        const data = envData && typeof envData === 'object' ? envData : (global.__envStatusCache || {});
        const envConfigs = getEnvConfigs(ctx);
        const configuredId = String(rule?.state?.resolved_device_id || rule?.condition?.device_id || '').trim();
        let sensorCfg = getEnvConfigById(configuredId, ctx);
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

    function pickDashboardEnvSensor(envData = {}, ctx = null) {
        const runtimeMap = getAutomationStatusMap();
        const envConfigs = getEnvConfigs(ctx);
        const outdoorSensor = resolveOutdoorAutomationSensor(runtimeMap.get('auto_outdoor_light_low_lux_on'), envData, ctx);
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

    function formatAutomationWindowText(schedule = {}) {
        const start = schedule.time_start || '00:00';
        const end = schedule.time_end || '23:59';
        return `${start}-${end}`;
    }

    function getAutomationWindowNextText(schedule = {}, inWindow = false) {
        const startText = schedule.time_start || '00:00';
        const endText = schedule.time_end || '23:59';
        if (inWindow) return `${endText}前有效`;
        const startTarget = utils.getTodayTargetDateTime ? utils.getTodayTargetDateTime(startText) : global.getTodayTargetDateTime(startText);
        const endTarget = utils.getTodayTargetDateTime ? utils.getTodayTargetDateTime(endText) : global.getTodayTargetDateTime(endText);
        const now = new Date();
        if (now < startTarget) return `${startText}开始`;
        if (now > endTarget) return `明日${startText}`;
        return `${startText}-${endText}`;
    }

    function getAutomationOffPlanText(rule) {
        const timeText = rule?.schedule?.time || '20:00';
        const target = utils.getTodayTargetDateTime ? utils.getTodayTargetDateTime(timeText) : global.getTodayTargetDateTime(timeText);
        const countdown = utils.formatCountdownText ? utils.formatCountdownText(target) : global.formatCountdownText(target);
        return countdown === '已到时间' ? `${timeText}已到` : `${timeText}关灯`;
    }

    function renderOutdoorAutomationDashboardCard(ctx = null) {
        const runtimeCtx = getContext(ctx);
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

        const toFiniteNumber = utils.toFiniteNumber || global.toFiniteNumber || (value => {
            const num = Number(value);
            return Number.isFinite(num) ? num : null;
        });
        const formatRelativeSeconds = utils.formatRelativeSeconds || global.formatRelativeSeconds || (seconds => `${Math.round(Number(seconds) || 0)}秒`);
        const formatDateTimeText = utils.formatDateTimeText || global.formatDateTimeText || (value => String(value || '未上报'));
        const outdoorSensor = resolveOutdoorAutomationSensor(onRule, null, runtimeCtx);
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
                statusText = currentLux <= threshold ? '光照已低，但未到开灯窗口' : '未到开灯窗口，当前光照充足';
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
            const lastText = formatDateTimeText(onRule?.state?.last_evaluated_at || state.automationStatusCache.server_time || '');
            noteEl.textContent = `${ruleNote}更新 ${lastText}`;
        }
        if (chipEl) {
            chipEl.textContent = chipText;
            chipEl.className = chipClass;
        }
        runtimeCtx.scheduleDashboardMasonry(80);
    }

    async function loadAutomationStatus(showError = false, ctx = null) {
        const runtimeCtx = getContext(ctx);
        if (state.automationStatusLoading) return;
        state.automationStatusLoading = true;
        try {
            const data = await runtimeCtx.fetchJson('/api/automation/status', {}, '自动化状态读取失败');
            state.automationStatusCache = {
                server_time: data.server_time || '',
                rules: Array.isArray(data.rules) ? data.rules : [],
            };
            const rules = state.automationStatusCache.rules || [];
            const dashAutoTotal = document.getElementById('dash-auto-total');
            const dashAutoEnabled = document.getElementById('dash-auto-enabled');
            const dashAutoErrors = document.getElementById('dash-auto-errors');
            const enabledCount = rules.filter(item => item && item.enabled).length;
            const errorCount = rules.filter(item => item && String(item.last_error || '').trim()).length;
            if (dashAutoTotal) dashAutoTotal.innerText = String(rules.length);
            if (dashAutoEnabled) dashAutoEnabled.innerText = String(enabledCount);
            if (dashAutoErrors) dashAutoErrors.innerText = String(errorCount);
            renderOutdoorAutomationDashboardCard(runtimeCtx);
            if (runtimeCtx.getActiveViewId() === 'auto') {
                renderAutomationPageStatus(runtimeCtx);
            }
        } catch (err) {
            if (showError) runtimeCtx.showToast(err.message || '自动化状态读取失败', true);
            console.error('自动化状态读取失败', err);
        } finally {
            state.automationStatusLoading = false;
        }
    }

    function withAutomationView(callback, contextLabel = '自动化运行页面模块', ctx = null) {
        const runtimeCtx = getContext(ctx);
        return ensureAutomationViewReady(contextLabel, runtimeCtx)
            .then(api => {
                if (api && typeof callback === 'function') return callback(api, buildAutomationViewContext(runtimeCtx));
                return null;
            })
            .catch(() => null);
    }

    const api = {
        getAutomationStatusMap,
        getAutomationStatusCache,
        getAutomationViewApi,
        ensureAutomationViewReady,
        buildAutomationViewContext,
        renderAutomationPageStatus,
        renderAutomationLazyPage,
        getEnvConfigById,
        isContactLikeEnvSensor,
        getOutdoorGateSensorSnapshot,
        resolveOutdoorGateState,
        updateDashboardDoorStatusFromEnv,
        updateDashboardDoorStatusFromVision,
        getEnvDashboardScore,
        resolveOutdoorAutomationSensor,
        pickDashboardEnvSensor,
        formatAutomationWindowText,
        getAutomationWindowNextText,
        getAutomationOffPlanText,
        renderOutdoorAutomationDashboardCard,
        loadAutomationStatus,
        withAutomationView,
    };

    Object.assign(state, api);
    Object.assign(global, {
        getAutomationStatusMap,
        getAutomationStatusCache,
        renderAutomationPageStatus,
        renderAutomationLazyPage,
        updateDashboardDoorStatusFromEnv,
        updateDashboardDoorStatusFromVision,
        pickDashboardEnvSensor,
        renderOutdoorAutomationDashboardCard,
        loadAutomationStatus,
    });
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.automation_runtime', {
            kind: 'view-runtime',
            exports: Object.keys(api),
            source: 'static/js/views/automation-runtime.js',
        });
    }
})(window);
