// AI_MODULE: light_runtime
// AI_PURPOSE: 灯光/继电器状态轮询、首页摘要、灯光页控制和日志渲染。
// AI_BOUNDARY: 只负责浏览器运行时和 /api/light/* 调用；不生成底层协议指令。
// AI_DATA_FLOW: /api/light/status/logs -> lightRuntime 缓存 -> dashboard/light DOM；用户点击 -> /api/light/control。
// AI_RUNTIME: 进入 light 视图或首页灯光区接近视口时按需加载，减少 app-runtime 首屏解析体积。
// AI_RISK: 高，包含真实灯光/继电器控制链路；必须保留权限校验、payload 和状态回读。
// AI_SEARCH_KEYWORDS: light runtime, relay channel, dashboard light, lighting control, courtyard light.

(function installSmartCenterLightRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.lightRuntime = Object.assign({
        lightLocks: {},
        lightStates: {},
        lightInputStates: {},
        lightOnlineStates: {},
    }, SmartCenter.lightRuntime || {});

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
        const provider = typeof global.getLightRuntimeContext === 'function'
            ? (global.getLightRuntimeContext() || {})
            : {};
        return Object.assign({
            configData: global.configData || {},
            fetchJson: utils.fetchJson || global.fetchJson,
            postJsonLoose: utils.postJsonLoose || global.postJsonLoose,
            getActiveViewId: global.getActiveViewId || (() => ''),
            ensurePermission: utils.ensurePermission || global.ensurePermission || (() => false),
            showToast: utils.showToast || global.showToast || (() => {}),
            translateApiError: utils.translateApiError || global.translateApiError || ((message, fallback) => String(message || fallback || '请求失败')),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            getDeviceStatusMeta: utils.getDeviceStatusMeta || global.getDeviceStatusMeta || (status => ({
                level: status?.online ? 'online' : 'offline',
                chipClass: status?.online ? 'online' : 'error',
                text: status?.online ? '在线' : '离线',
                note: status?.online ? '在线' : '等待采集',
                isOnlineLike: !!status?.online,
            })),
            getCardStateClass: utils.getCardStateClass || global.getCardStateClass || (meta => (!meta || meta.level === 'offline' ? 'offline' : '')),
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            scheduleDashboardMasonry: global.scheduleDashboardMasonry || (() => {}),
        }, provider || {}, context || {});
    }

    function ensureDeviceState(context = {}) {
        const ctx = getContext(context);
        const devices = Array.isArray(ctx.configData.light_devices) ? ctx.configData.light_devices : [];
        devices.forEach(dev => {
            const devId = String(dev?.id ?? '');
            if (!devId) return;
            state.lightLocks[devId] = state.lightLocks[devId] || {};
            state.lightStates[devId] = state.lightStates[devId] || [];
            state.lightInputStates[devId] = state.lightInputStates[devId] || [];
            if (state.lightOnlineStates[devId] === undefined) state.lightOnlineStates[devId] = false;
        });
        return devices;
    }

    function normalizeLightChannelState(status) {
        if (status === null || status === undefined) return null;
        if (status === true || status === false) return status;
        if (status === 1 || status === '1') return true;
        if (status === 0 || status === '0') return false;
        if (typeof status === 'string') {
            const text = status.trim().toLowerCase();
            if (['true', 'on', 'open', 'opened', 'enabled', 'yes', 'y', 'online', 'running', '已开', '开启', '打开', '开'].includes(text)) return true;
            if (['false', 'off', 'close', 'closed', 'disabled', 'no', 'n', 'offline', 'stopped', '已关', '关闭', '关'].includes(text)) return false;
        }
        return null;
    }

    function getLightChannelStateFromSources(devId, chNum, channelsMap = {}) {
        const devKey = String(devId);
        const channelNo = Number(chNum);
        const apiSources = [
            (channelsMap || {})[devId],
            (channelsMap || {})[devKey],
        ];
        for (const source of apiSources) {
            if (!source) continue;
            if (Array.isArray(source)) {
                const candidates = [source[channelNo - 1], source[channelNo]];
                for (const candidate of candidates) {
                    const normalized = normalizeLightChannelState(candidate);
                    if (normalized !== null) return normalized;
                }
                continue;
            }
            if (typeof source === 'object') {
                const candidates = [
                    source[channelNo],
                    source[String(channelNo)],
                    source[`ch${channelNo}`],
                    source[`channel_${channelNo}`],
                ];
                for (const candidate of candidates) {
                    const normalized = normalizeLightChannelState(candidate);
                    if (normalized !== null) return normalized;
                }
            }
        }
        const cacheSources = [
            state.lightStates[devId],
            state.lightStates[devKey],
        ];
        for (const source of cacheSources) {
            if (!source) continue;
            if (Array.isArray(source)) {
                const normalized = normalizeLightChannelState(source[channelNo]);
                if (normalized !== null) return normalized;
                continue;
            }
            if (typeof source === 'object') {
                const candidates = [
                    source[channelNo],
                    source[String(channelNo)],
                    source[`ch${channelNo}`],
                    source[`channel_${channelNo}`],
                ];
                for (const candidate of candidates) {
                    const normalized = normalizeLightChannelState(candidate);
                    if (normalized !== null) return normalized;
                }
            }
        }
        return null;
    }

    function getLightChannelUiState(devId, chNum) {
        const status = getLightChannelStateFromSources(devId, chNum, {});
        const isOnline = !!state.lightOnlineStates[String(devId)];
        if (!isOnline) return { cls: 'ch-err', text: '离线', actionable: false };
        if (status === true) return { cls: 'ch-on', text: '已开启', actionable: true };
        if (status === false) return { cls: 'ch-off', text: '已关闭', actionable: true };
        return { cls: 'ch-unknown', text: '待确认', actionable: false };
    }

    function renderLightChannel(devId, chNum) {
        const btn = document.getElementById(`lch_${devId}_${chNum}`);
        if (!btn) return;
        const devKey = String(devId);
        const uiState = getLightChannelUiState(devKey, chNum);
        const oldClasses = Array.from(btn.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn').join(' ');
        btn.className = `${oldClasses} ${uiState.cls}`;
        const stateEl = btn.querySelector('.state');
        if (stateEl) stateEl.innerText = uiState.text;
        btn.title = uiState.actionable ? '' : (state.lightOnlineStates[devKey] ? '设备在线，但该通道状态暂未确认' : '设备离线，无法读取通道状态');
    }

    function getLightInputState(devId, inputNum, inputsMap = {}) {
        const devKey = String(devId);
        const list = Array.isArray(inputsMap[devId])
            ? inputsMap[devId]
            : (Array.isArray(inputsMap[devKey]) ? inputsMap[devKey] : state.lightInputStates[devKey]);
        if (!Array.isArray(list)) return null;
        return normalizeLightChannelState(list[Number(inputNum) - 1]);
    }

    function renderLightInput(devId, inputNum) {
        const chip = document.getElementById(`lin_${devId}_${inputNum}`);
        if (!chip) return;
        const devKey = String(devId);
        const inputState = getLightInputState(devKey, inputNum);
        const isOnline = !!state.lightOnlineStates[devKey];
        const cls = !isOnline ? 'offline' : (inputState === true ? 'active' : (inputState === false ? 'idle' : 'unknown'));
        const text = !isOnline ? '离线' : (inputState === true ? '触发' : (inputState === false ? '未触发' : '待确认'));
        const oldClasses = Array.from(chip.classList).filter(c => c.startsWith('ch-span-') || c === 'relay-input-chip').join(' ');
        chip.className = `${oldClasses} ${cls}`;
        const stateEl = chip.querySelector('.state');
        if (stateEl) stateEl.innerText = text;
        chip.title = inputState === true ? '输入接口检测到有效电平' : (inputState === false ? '输入接口未检测到有效电平' : '输入接口状态待确认');
    }

    function formatLightTime(value) {
        if (!value) return '--';
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleString('zh-CN', { hour12: false });
    }

    function renderLightDiagnostics(statusData = {}, context = {}) {
        const ctx = getContext(context);
        const devices = ensureDeviceState(ctx);
        devices.forEach(device => {
            const devKey = String(device?.id ?? '');
            if (!devKey) return;
            const extraMeta = (statusData.extras || {})[devKey] || {};
            const diagEl = document.getElementById(`light-diagnostic-${devKey}`);
            if (!diagEl) return;
            const online = !!((statusData.online || {})[device.id] ?? (statusData.online || {})[devKey]);
            const lastError = String(extraMeta.last_error || '').trim();
            const checkedAt = extraMeta.last_checked_at || extraMeta.last_error_at || '';
            const successAt = extraMeta.last_success_at || '';
            const failures = Number(extraMeta.poll_failures || 0);
            const statusLabel = String(extraMeta.status_label || extraMeta.status_text || (online ? '在线' : '离线')).trim();
            diagEl.className = `light-diagnostic-panel ${online ? 'online' : 'offline'}`;
            diagEl.innerHTML = `
                <div class="light-diagnostic-item"><span>状态</span><strong>${ctx.escapeHtml(statusLabel || '--')}</strong></div>
                <div class="light-diagnostic-item"><span>连续失败</span><strong>${ctx.escapeHtml(String(failures))}</strong></div>
                <div class="light-diagnostic-item"><span>最近检查</span><strong>${ctx.escapeHtml(formatLightTime(checkedAt))}</strong></div>
                <div class="light-diagnostic-item"><span>最近成功</span><strong>${ctx.escapeHtml(formatLightTime(successAt))}</strong></div>
                <div class="light-diagnostic-reason">${ctx.escapeHtml(lastError || (online ? '通讯正常' : '暂无详细错误，等待下一次轮询'))}</div>
            `;
        });
    }

    function getVisibleLightInputs(device) {
        return Array.isArray(device?.input_channels_config)
            ? device.input_channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
            : [];
    }

    function renderHomeCompactMetric(label, value, tone = '', context = {}) {
        const ctx = getContext(context);
        return `<div class="home-compact-metric">
            <div class="label">${ctx.escapeHtml(label)}</div>
            <div class="value ${ctx.escapeHtml(tone)}">${ctx.escapeHtml(value)}</div>
        </div>`;
    }

    function renderDashboardInputSummary(device, extraMeta, compact = false, context = {}) {
        const inputs = Array.isArray(extraMeta?.inputs) ? extraMeta.inputs : [];
        const visibleInputs = getVisibleLightInputs(device);
        const count = visibleInputs.length || inputs.length;
        if (!count) return '';
        const active = inputs.filter(item => normalizeLightChannelState(item) === true).length;
        if (compact) return renderHomeCompactMetric('输入触发', `${active} / ${count}`, active > 0 ? 'warn' : '', context);
        return `<div class="dashboard-mini-note">输入触发 ${getContext(context).escapeHtml(String(active))} / ${getContext(context).escapeHtml(String(count))}</div>`;
    }

    function renderDashboardLightCards(statusData = {}, context = {}) {
        const ctx = getContext(context);
        const container = document.getElementById('dashboard-light-grid');
        if (!container) return;
        const devices = ensureDeviceState(ctx).slice(0, 4);
        const extras = statusData.extras || {};
        if (!devices.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置灯光模块</div>';
            return;
        }
        container.innerHTML = devices.map(device => {
            const devKey = String(device.id);
            const extraMeta = extras[devKey] || {};
            const statusMeta = ctx.getDeviceStatusMeta({
                online: !!((statusData.online || {})[device.id] ?? (statusData.online || {})[devKey]),
                status_level: extraMeta.status_level,
                stale: extraMeta.stale,
                poll_failures: extraMeta.poll_failures,
                last_success_at: extraMeta.last_success_at,
                last_checked_at: extraMeta.last_checked_at,
                last_error: extraMeta.last_error,
            }, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const channels = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999)).slice(0, 4) : [];
            const currentStates = Array.isArray((statusData.channels || {})[device.id]) ? (statusData.channels || {})[device.id] : (Array.isArray((statusData.channels || {})[devKey]) ? (statusData.channels || {})[devKey] : []);
            const visibleChannelCount = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).length : currentStates.length;
            const onCount = currentStates.filter(Boolean).length;
            const unknownCount = currentStates.filter(st => st === null || st === undefined).length;
            const actions = channels.map(ch => {
                const uiState = getLightChannelUiState(devKey, ch.channel);
                const btnClass = uiState.cls === 'ch-on' ? 'success' : (uiState.cls === 'ch-off' ? 'secondary' : (online ? 'warning' : 'danger'));
                return `<button class="dashboard-mini-btn ${btnClass}${ctx.getPermissionDisabledClass('light.control')}" ${ctx.getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${ctx.escapeHtml(devKey)}', ${Number(ch.channel)})">${ctx.escapeHtml(ch.name || ('CH' + ch.channel))}</button>`;
            }).join('');
            const extraButtons = (((extras[devKey] || {}).dashboard_action_buttons) || []).filter(item => item && item.visible !== false).map(item => {
                return `<button class="dashboard-mini-btn secondary${ctx.getPermissionDisabledClass('light.control')}" ${ctx.getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${ctx.escapeHtml(devKey)}', '${ctx.escapeHtml(item.action || '')}', '${ctx.escapeHtml(item.label || item.action || '')}')">${ctx.escapeHtml(item.label || item.action || '动作')}</button>`;
            }).join('');
            return `<div class="dashboard-mini-card ${ctx.getCardStateClass(statusMeta)}">
                <div class="dashboard-mini-head">
                    <div>
                        <div class="dashboard-mini-title">${ctx.escapeHtml(device.name || devKey)}</div>
                        <div class="dashboard-mini-subtitle">${ctx.escapeHtml(device.ip || devKey || '--')}</div>
                    </div>
                    <div class="dashboard-mini-chip-row">
                        <span class="ups-chip ${statusMeta.chipClass}">${ctx.escapeHtml(statusMeta.text)}</span>
                    </div>
                </div>
                <div class="dashboard-mini-light-summary">
                    <div class="dashboard-mini-light-count">已开 ${ctx.escapeHtml(String(onCount))} / ${ctx.escapeHtml(String(visibleChannelCount || currentStates.length || 0))}</div>
                    <div class="dashboard-mini-note">${ctx.escapeHtml(online ? (unknownCount > 0 ? `${unknownCount} 路状态待确认` : statusMeta.note) : statusMeta.note)}</div>
                </div>
                ${renderDashboardInputSummary(device, extraMeta, false, ctx)}
                <div class="dashboard-mini-actions">${actions || '<span class="dashboard-mini-note">暂无可用通道</span>'}${extraButtons}</div>
            </div>`;
        }).join('');
    }

    function renderDashboardLightCompact(statusData = {}, context = {}) {
        const ctx = getContext(context);
        const container = document.getElementById('dashboard-light-compact-grid');
        if (!container) return;
        const devices = ensureDeviceState(ctx);
        const onlineMap = statusData.online || {};
        const channelsMap = statusData.channels || {};
        const extras = statusData.extras || {};
        if (!devices.length) {
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置灯光模块</div>';
            return;
        }
        container.classList.remove('home-status-list');
        container.innerHTML = devices.map(device => {
            const devKey = String(device.id);
            const extraMeta = extras[devKey] || {};
            const statusMeta = ctx.getDeviceStatusMeta({
                online: !!(onlineMap[device.id] ?? onlineMap[devKey]),
                status_level: extraMeta.status_level,
                stale: extraMeta.stale,
                poll_failures: extraMeta.poll_failures,
                last_success_at: extraMeta.last_success_at,
                last_checked_at: extraMeta.last_checked_at,
                last_error: extraMeta.last_error,
            }, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const rawStates = Array.isArray(channelsMap[device.id]) ? channelsMap[device.id] : (Array.isArray(channelsMap[devKey]) ? channelsMap[devKey] : []);
            const visibleChannels = Array.isArray(device.channels_config)
                ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                : [];
            const total = visibleChannels.length || rawStates.length || 0;
            const knownVisibleStates = visibleChannels.length
                ? visibleChannels.map(ch => getLightChannelStateFromSources(devKey, ch.channel, channelsMap))
                : rawStates.map(st => normalizeLightChannelState(st));
            const onCount = knownVisibleStates.filter(st => st === true).length;
            const unknownCount = knownVisibleStates.filter(st => st === null).length;
            const actionChannels = visibleChannels.length
                ? visibleChannels
                : rawStates.map((_, idx) => ({ channel: idx + 1, name: `CH${idx + 1}` }));
            const actionNameCounts = actionChannels.reduce((acc, ch) => {
                const chNum = Number(ch.channel);
                const name = String(ch.name || `CH${chNum}`);
                acc.set(name, (acc.get(name) || 0) + 1);
                return acc;
            }, new Map());
            const actions = actionChannels.slice(0, 8).map(ch => {
                const chNum = Number(ch.channel);
                const channelState = getLightChannelStateFromSources(devKey, chNum, channelsMap);
                const cls = channelState === true ? 'on' : (channelState === false ? 'off' : 'warning');
                const stateText = channelState === true ? '开' : (channelState === false ? '关' : '?');
                const baseName = String(ch.name || `CH${chNum}`);
                const displayName = actionNameCounts.get(baseName) > 1 ? `${baseName} ${chNum}` : baseName;
                return `<button class="home-compact-action ${cls}${ctx.getPermissionDisabledClass('light.control')}" ${ctx.getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${ctx.escapeHtml(devKey)}', ${chNum})"><span class="label">${ctx.escapeHtml(displayName)}</span><span class="home-action-state">${ctx.escapeHtml(stateText)}</span></button>`;
            }).join('');
            const extraButtons = ((extraMeta.dashboard_action_buttons || [])).filter(item => item && item.visible !== false).slice(0, 2).map(item => {
                return `<button class="home-compact-action success${ctx.getPermissionDisabledClass('light.control')}" ${ctx.getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${ctx.escapeHtml(devKey)}', '${ctx.escapeHtml(item.action || '')}', '${ctx.escapeHtml(item.label || item.action || '')}')">${ctx.escapeHtml(item.label || item.action || '动作')}</button>`;
            }).join('');
            return `<div class="home-compact-card ${online ? '' : 'offline'}">
                <div class="home-compact-head">
                    <div style="min-width:0;">
                        <div class="home-compact-title">${ctx.escapeHtml(device.name || devKey)}</div>
                        <div class="home-compact-subtitle">${ctx.escapeHtml(device.ip || devKey || '--')}</div>
                    </div>
                    <div class="home-compact-chip-row">
                        <span class="ups-chip ${statusMeta.chipClass}">${ctx.escapeHtml(statusMeta.text)}</span>
                    </div>
                </div>
                <div class="home-compact-metrics">
                    ${renderHomeCompactMetric('已开路数', `${onCount} / ${total || '--'}`, onCount > 0 ? 'ok' : '', ctx)}
                    ${renderHomeCompactMetric('状态待确认', String(unknownCount || 0), unknownCount > 0 ? 'warn' : '', ctx)}
                    ${renderDashboardInputSummary(device, extraMeta, true, ctx)}
                </div>
                <div class="home-compact-actions">${actions || '<span class="home-compact-note">暂无可用通道</span>'}${extraButtons}</div>
                <div class="home-compact-note">${ctx.escapeHtml(statusMeta.note || '--')}</div>
            </div>`;
        }).join('');
    }

    function applyChannels(devId, channels) {
        const devKey = String(devId);
        if (!Array.isArray(channels)) return;
        state.lightStates[devKey] = state.lightStates[devKey] || [];
        channels.forEach((channelState, idx) => {
            const chNum = idx + 1;
            state.lightStates[devKey][chNum] = channelState;
            renderLightChannel(devKey, chNum);
        });
    }

    function toggleLight(devId, chNum, context = {}) {
        const ctx = getContext(context);
        ensureDeviceState(ctx);
        const devKey = String(devId);
        if (!ctx.ensurePermission('light.control', '切换灯光通道')) return Promise.resolve(false);
        if (!state.lightOnlineStates[devKey]) {
            ctx.showToast('设备离线，无法控制通道', true);
            return Promise.resolve(false);
        }
        const status = getLightChannelStateFromSources(devKey, chNum, {});
        if (status === null || status === undefined) {
            ctx.showToast('设备在线，但该通道状态待确认，请稍后再试或使用动作按钮', true);
            return Promise.resolve(false);
        }
        const targetState = !status;
        state.lightLocks[devKey] = state.lightLocks[devKey] || {};
        state.lightStates[devKey] = state.lightStates[devKey] || [];
        state.lightLocks[devKey][chNum] = Date.now();
        state.lightStates[devKey][chNum] = targetState;
        renderLightChannel(devKey, chNum);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('灯光控制运行库缺少请求方法', true);
            return Promise.resolve(false);
        }
        return ctx.postJsonLoose('/api/light/control', { type: 'single', device_id: devKey, channel: chNum, is_open: targetState }, '灯光控制请求失败')
            .then(data => {
                if (!data.success) {
                    state.lightStates[devKey][chNum] = status;
                    renderLightChannel(devKey, chNum);
                    ctx.showToast(data.msg || '灯光控制失败', true);
                    return data;
                }
                applyChannels(devKey, data.channels);
                ctx.showToast(data.verified === false ? '灯光指令已发送，等待状态确认' : '灯光控制成功');
                setTimeout(() => updateLightData(ctx), 600);
                return data;
            })
            .catch(err => {
                state.lightStates[devKey][chNum] = status;
                renderLightChannel(devKey, chNum);
                ctx.showToast(ctx.translateApiError(err?.message, '灯光控制请求失败'), true);
                return false;
            })
            .finally(() => {
                setTimeout(() => {
                    if (state.lightLocks[devKey]) delete state.lightLocks[devKey][chNum];
                }, 1200);
            });
    }

    function triggerLightAction(devId, actionName, label, context = {}) {
        const ctx = getContext(context);
        const devKey = String(devId);
        const actionText = label || actionName;
        if (!ctx.ensurePermission('light.control', `执行灯光动作 ${actionText}`)) return Promise.resolve(false);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('灯光控制运行库缺少请求方法', true);
            return Promise.resolve(false);
        }
        return ctx.postJsonLoose('/api/light/control', { type: 'action', device_id: devKey, action: actionName }, `${actionText} 请求失败`)
            .then(data => {
                if (!data.success) {
                    ctx.showToast(data.msg || `${actionText} 执行失败`, true);
                    return data;
                }
                applyChannels(devKey, data.channels);
                ctx.showToast(data.verified === false ? `${actionText} 已下发，等待状态确认` : `${actionText} 已执行`);
                setTimeout(() => updateLightData(ctx), 700);
                return data;
            })
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, `${actionText} 请求失败`), true);
                return false;
            });
    }

    function executeScene(sceneId, name, context = {}) {
        const ctx = getContext(context);
        if (!ctx.ensurePermission('light.control', '执行场景联动')) return Promise.resolve(false);
        if (!global.confirm(`确定要触发全局联动场景 [${name}] 吗？`)) return Promise.resolve(false);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('灯光控制运行库缺少请求方法', true);
            return Promise.resolve(false);
        }
        return ctx.postJsonLoose('/api/light/control', { type: 'scene', scene_id: sceneId }, `场景联动 [${name}] 请求失败`)
            .then(data => {
                if (!data.success) {
                    ctx.showToast(data.msg || `场景联动 [${name}] 执行失败`, true);
                    return data;
                }
                ctx.showToast(`场景联动 [${name}] 触发成功`);
                setTimeout(() => updateLightData(ctx), 800);
                return data;
            })
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, `场景联动 [${name}] 请求失败`), true);
                return false;
            });
    }

    function updateLightLogs(context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.fetchJson !== 'function') return Promise.resolve(false);
        return ctx.fetchJson('/api/light/logs', {}, '灯光日志读取失败')
            .then(logs => {
                const logBox = document.getElementById('light-global-log');
                if (!logBox) return logs;
                const html = (logs || []).map(log => {
                    const timeText = new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false });
                    const operation = String(log.operation || '').replace(/\[.*?\]\s*/, '');
                    return `<div class="log-item"><span class="time">[${timeText}]</span><span class="msg">${ctx.escapeHtml(operation)}</span></div>`;
                }).join('') || '<div class="log-item"><span class="time">[--:--:--]</span><span class="msg">暂无灯光操作或诊断日志</span></div>';
                if (logBox.innerHTML !== html) logBox.innerHTML = html;
                return logs;
            })
            .catch(err => {
                console.error('灯光日志更新失败', err);
                return false;
            });
    }

    function updateLightData(context = {}) {
        const ctx = getContext(context);
        ensureDeviceState(ctx);
        if (typeof ctx.fetchJson !== 'function') {
            console.error('灯光状态更新失败', new Error('fetchJson_missing'));
            return Promise.resolve(false);
        }
        const statusPromise = ctx.fetchJson('/api/light/status', {}, '灯光状态读取失败')
            .then(data => {
                let onlineCount = 0;
                Object.keys(data.online || {}).forEach(rawDevId => {
                    const devKey = String(rawDevId);
                    const extraMeta = (data.extras || {})[devKey] || {};
                    const statusMeta = ctx.getDeviceStatusMeta({
                        online: !!data.online[rawDevId],
                        status_level: extraMeta.status_level,
                        stale: extraMeta.stale,
                        poll_failures: extraMeta.poll_failures,
                        last_success_at: extraMeta.last_success_at,
                        last_checked_at: extraMeta.last_checked_at,
                        last_error: extraMeta.last_error,
                    }, { staleText: '陈旧', errorText: '异常' });
                    state.lightOnlineStates[devKey] = statusMeta.isOnlineLike;
                    if (statusMeta.isOnlineLike) onlineCount += 1;
                    const tag = document.getElementById(`light-status-${devKey}`);
                    if (tag) {
                        tag.className = statusMeta.chipClass === 'online' ? 'tag normal' : (statusMeta.chipClass === 'warning' ? 'tag warn' : 'tag error');
                        tag.innerText = statusMeta.text;
                        tag.title = statusMeta.note;
                    }
                    const locks = state.lightLocks[devKey] || {};
                    state.lightStates[devKey] = state.lightStates[devKey] || [];
                    (data.channels?.[rawDevId] || data.channels?.[devKey] || []).forEach((channelState, idx) => {
                        const chNum = idx + 1;
                        if (locks[chNum] && (Date.now() - locks[chNum] < 2000)) return;
                        state.lightStates[devKey][chNum] = channelState;
                        renderLightChannel(devKey, chNum);
                    });
                    const inputStates = Array.isArray(extraMeta.inputs) ? extraMeta.inputs : [];
                    state.lightInputStates[devKey] = inputStates;
                    inputStates.forEach((inputState, idx) => {
                        renderLightInput(devKey, idx + 1);
                    });
                });
                const onlineEl = document.getElementById('dash-light-online');
                if (onlineEl) onlineEl.innerText = String(onlineCount);
                renderDashboardLightCards(data, ctx);
                renderDashboardLightCompact(data, ctx);
                renderLightDiagnostics(data, ctx);
                ctx.scheduleDashboardMasonry(120);
                return data;
            })
            .catch(err => {
                console.error('灯光状态更新失败', err);
                return false;
            });
        const shouldLoadLogs = typeof ctx.getActiveViewId === 'function' && ctx.getActiveViewId() === 'light';
        if (!shouldLoadLogs) return statusPromise;
        return Promise.all([statusPromise, updateLightLogs(ctx)]).then(([status]) => status);
    }

    const api = {
        getStateSnapshot: () => ({
            lightLocks: state.lightLocks,
            lightStates: state.lightStates,
            lightInputStates: state.lightInputStates,
            lightOnlineStates: state.lightOnlineStates,
        }),
        normalizeLightChannelState,
        getLightChannelStateFromSources,
        getLightChannelUiState,
        renderLightChannel,
        renderLightInput,
        renderLightDiagnostics,
        renderDashboardLightCards,
        renderDashboardLightCompact,
        updateLightLogs,
        updateLightData,
        toggleLight,
        triggerLightAction,
        executeScene,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('light-runtime', {
            kind: 'view-runtime',
            exports: Object.keys(api),
            source: 'static/js/views/light-runtime.js',
        });
    }

    Object.assign(global, {
        updateLightData: context => updateLightData(context),
        toggleLight: (devId, chNum, context) => toggleLight(devId, chNum, context),
        triggerLightAction: (devId, actionName, label, context) => triggerLightAction(devId, actionName, label, context),
        executeScene: (sceneId, name, context) => executeScene(sceneId, name, context),
    });
})(window);
