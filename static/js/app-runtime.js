        // AI_MODULE: app_runtime
        // AI_PURPOSE: 中控首页和各视图的旧全局运行时入口，继续兼容内联 onclick。
        // AI_BOUNDARY: 模板变量由 templates/index.html 注入；本文件只消费 configData/currentUser。
        // AI_DATA_FLOW: configData + API 响应 -> DOM 渲染；用户点击 -> 各 /api/* 控制接口。
        // AI_RISK: 高，保留真实设备控制链路，拆分时不得改变 payload 和权限判断。
        const lazyModuleVersion = '20260531-automation-ui-split';
        const lazyStyle = name => `/static/css/generated/${name}.css?v=${lazyModuleVersion}`;
        const viewStyleGroups = {
            dashboard: [lazyStyle('dashboard')],
            server: [lazyStyle('server')],
            hvac: [lazyStyle('hvac')],
            projector: [lazyStyle('projector')],
            snmp: [lazyStyle('snmp')],
            proxy: [lazyStyle('proxy')],
            universal: [lazyStyle('universal')],
            apple_audio: [lazyStyle('apple_audio')],
            local_model: [`/static/css/views/local-model.css?v=${lazyModuleVersion}`],
            power: [lazyStyle('power')],
            meter: [lazyStyle('meter')],
            ups: [lazyStyle('ups')],
            auto: [lazyStyle('auto')],
            sequencer: [lazyStyle('sequencer')],
            env: [lazyStyle('env')],
            logs: [lazyStyle('logs')],
        };
        SmartCenter.registerLazyModule('server-view-style', { styles: viewStyleGroups.server });
        SmartCenter.registerLazyModule('server-monitor-view', {
            scripts: [`/static/js/views/server-monitor.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('server-summary-view', {
            scripts: [`/static/js/views/server-summary.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('hvac-view-style', { styles: viewStyleGroups.hvac });
        SmartCenter.registerLazyModule('hvac-view', {
            scripts: [`/static/js/views/hvac-view.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('hvac-summary-view', {
            scripts: [`/static/js/views/hvac-summary.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('projector-view-style', { styles: viewStyleGroups.projector });
        SmartCenter.registerLazyModule('projector-view', {
            scripts: [`/static/js/views/projector.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('projector-summary-view', {
            scripts: [`/static/js/views/projector-summary.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('snmp-full', {
            styles: viewStyleGroups.snmp,
            scripts: [`/static/js/views/snmp.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('proxy-view', {
            styles: viewStyleGroups.proxy,
            scripts: [`/static/js/views/proxy.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('universal-view', {
            styles: viewStyleGroups.universal,
            scripts: [`/static/js/views/universal.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('apple-audio-view', {
            styles: viewStyleGroups.apple_audio,
            scripts: [`/static/js/views/apple-audio.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('local-model-view', {
            styles: viewStyleGroups.local_model,
            scripts: [`/static/js/views/local-model.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('power-view-style', { styles: viewStyleGroups.power });
        SmartCenter.registerLazyModule('meter-view-style', { styles: viewStyleGroups.meter });
        SmartCenter.registerLazyModule('ups-view-style', { styles: viewStyleGroups.ups });
        SmartCenter.registerLazyModule('auto-view-style', { styles: viewStyleGroups.auto });
        SmartCenter.registerLazyModule('automation-view', {
            scripts: [`/static/js/views/automation-view.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('sequencer-view-style', { styles: viewStyleGroups.sequencer });
        SmartCenter.registerLazyModule('env-view-style', { styles: viewStyleGroups.env });
        SmartCenter.registerLazyModule('logs-view-style', { styles: viewStyleGroups.logs });
        SmartCenter.registerLazyModule('dashboard-view-style', { styles: viewStyleGroups.dashboard });
        SmartCenter.registerViewModules('dashboard', ['dashboard-view-style']);
        SmartCenter.registerViewModules('server', ['server-view-style', 'server-monitor-view']);
        SmartCenter.registerViewModules('hvac', ['hvac-view-style', 'hvac-view']);
        SmartCenter.registerViewModules('projector', ['projector-view-style', 'projector-view']);
        SmartCenter.registerViewModules('snmp', ['snmp-full']);
        SmartCenter.registerViewModules('camera_preview', ['snmp-full']);
        SmartCenter.registerViewModules('proxy', ['proxy-view']);
        SmartCenter.registerViewModules('universal', ['universal-view']);
        SmartCenter.registerViewModules('apple_audio', ['apple-audio-view']);
        SmartCenter.registerViewModules('local_model', ['local-model-view']);
        SmartCenter.registerViewModules('power', ['power-view-style']);
        SmartCenter.registerViewModules('meter', ['meter-view-style']);
        SmartCenter.registerViewModules('ups', ['ups-view-style']);
        SmartCenter.registerViewModules('auto', ['auto-view-style', 'automation-view']);
        SmartCenter.registerViewModules('sequencer', ['sequencer-view-style']);
        SmartCenter.registerViewModules('env', ['env-view-style']);
        SmartCenter.registerViewModules('logs', ['logs-view-style']);
        function ensureModulesReady(moduleNames, contextLabel = '功能模块') {
            if (!window.SmartCenter || typeof SmartCenter.ensureModules !== 'function') return Promise.resolve([]);
            return SmartCenter.ensureModules(moduleNames).catch(err => {
                console.error(`${contextLabel}加载失败`, err);
                if (typeof showToast === 'function') showToast(`${contextLabel}加载失败，请刷新后重试`, true);
                throw err;
            });
        }
        function ensureViewReady(viewId) {
            if (!window.SmartCenter || typeof SmartCenter.ensureViewModules !== 'function') return Promise.resolve([]);
            return SmartCenter.ensureViewModules(viewId).catch(err => {
                console.error(`视图 ${viewId} 模块加载失败`, err);
                if (typeof showToast === 'function') showToast('页面模块加载失败，请刷新后重试', true);
                throw err;
            });
        }
        function scheduleIdleTask(callback, timeout = 1800) {
            if (typeof callback !== 'function') return;
            if (typeof window.requestIdleCallback === 'function') {
                window.requestIdleCallback(callback, { timeout });
                return;
            }
            window.setTimeout(callback, Math.min(Math.max(Number(timeout) || 300, 120), 1200));
        }
        const dashboardDeferredModuleState = {
            timers: {},
            started: {},
            observer: null,
            scrollBound: false,
        };
        const dashboardDeferredModules = {
            server_compact: { sectionId: 'server_compact', modules: ['server-summary-view'], label: '服务器摘要模块' },
            hvac: { sectionId: 'hvac', modules: ['hvac-summary-view'], label: '空调摘要模块' },
            projector: { sectionId: 'projector', modules: ['projector-summary-view'], label: '投影摘要模块' },
        };
        function isDashboardSectionNearViewport(sectionId, marginPx = 520) {
            if (getActiveViewId() !== 'dashboard') return false;
            const section = document.querySelector(`#view-dashboard [data-section-id="${sectionId}"]`);
            if (!section || section.style.display === 'none') return false;
            const style = window.getComputedStyle ? window.getComputedStyle(section) : null;
            if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
            const rect = section.getBoundingClientRect();
            const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 1080;
            return rect.bottom >= -marginPx && rect.top <= viewportHeight + marginPx;
        }
        function loadDashboardDeferredModule(key, reason = 'viewport') {
            const item = dashboardDeferredModules[key];
            if (!item || dashboardDeferredModuleState.started[key]) return Promise.resolve(false);
            if (!isDashboardSectionVisible(item.sectionId)) return Promise.resolve(false);
            if (reason !== 'force' && !isDashboardSectionNearViewport(item.sectionId)) return Promise.resolve(false);
            dashboardDeferredModuleState.started[key] = true;
            return ensureModulesReady(item.modules, item.label)
                .then(result => {
                    if (key === 'server_compact') {
                        const data = Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length
                            ? dashboardServerCompactList
                            : globalServerList;
                        if (Array.isArray(data) && data.length) renderDashboardServerCompactWhenReady(data);
                    } else if (key === 'hvac' && getActiveViewId() === 'dashboard') {
                        updateHvacStatus(false);
                    } else if (key === 'projector' && getActiveViewId() === 'dashboard') {
                        updateProjectorStatus();
                    }
                    return result;
                })
                .catch(err => {
                    dashboardDeferredModuleState.started[key] = false;
                    throw err;
                });
        }
        function scheduleDashboardDeferredModule(key, delayMs = 0, reason = 'viewport') {
            const item = dashboardDeferredModules[key];
            if (!item || dashboardDeferredModuleState.started[key]) return;
            window.clearTimeout(dashboardDeferredModuleState.timers[key]);
            dashboardDeferredModuleState.timers[key] = window.setTimeout(() => {
                scheduleIdleTask(() => loadDashboardDeferredModule(key, reason).catch(() => {}), 900);
            }, Math.max(0, Number(delayMs) || 0));
        }
        function preloadDashboardSupportModules(reason = 'viewport') {
            if (getActiveViewId() !== 'dashboard') return;
            Object.keys(dashboardDeferredModules).forEach((key, index) => {
                scheduleDashboardDeferredModule(key, index * 180, reason);
            });
        }
        function initDashboardDeferredModuleObserver() {
            if (dashboardDeferredModuleState.observer || typeof IntersectionObserver !== 'function') return;
            dashboardDeferredModuleState.observer = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if (!entry.isIntersecting) return;
                    const sectionId = entry.target && entry.target.dataset ? entry.target.dataset.sectionId : '';
                    const foundKey = Object.keys(dashboardDeferredModules).find(key => dashboardDeferredModules[key].sectionId === sectionId);
                    if (foundKey) scheduleDashboardDeferredModule(foundKey, 0, 'intersection');
                });
            }, { root: null, rootMargin: '520px 0px', threshold: 0.01 });
            Object.values(dashboardDeferredModules).forEach(item => {
                const section = document.querySelector(`#view-dashboard [data-section-id="${item.sectionId}"]`);
                if (section) dashboardDeferredModuleState.observer.observe(section);
            });
        }
        function bindDashboardDeferredModuleFallback() {
            if (dashboardDeferredModuleState.scrollBound) return;
            dashboardDeferredModuleState.scrollBound = true;
            const handler = () => {
                if (getActiveViewId() === 'dashboard') preloadDashboardSupportModules('scroll');
            };
            window.addEventListener('scroll', handler, { passive: true });
            window.addEventListener('resize', handler);
        }
        function callLazyGlobal(moduleNames, functionName, args = [], fallbackValue = undefined) {
            if (typeof window[functionName] === 'function' && !window[functionName].__smartLazyShim) {
                return window[functionName].apply(window, args);
            }
            return ensureModulesReady(moduleNames, functionName)
                .then(() => {
                    const fn = window[functionName];
                    if (typeof fn !== 'function' || fn.__smartLazyShim) throw new Error(`lazy_function_missing:${functionName}`);
                    return fn.apply(window, args);
                })
                .catch(err => {
                    console.error(`延迟函数调用失败: ${functionName}`, err);
                    return fallbackValue;
                });
        }
        function installLazyGlobal(functionName, moduleNames, fallbackValue = undefined) {
            const shim = function smartLazyGlobalShim(...args) {
                return callLazyGlobal(moduleNames, functionName, args, fallbackValue);
            };
            shim.__smartLazyShim = true;
            window[functionName] = shim;
        }
        ['renderProxyDetail', 'updateProxyStatus'].forEach(name => installLazyGlobal(name, ['proxy-view']));
        [
            'fireUniversalCommand',
            'handleLongPressStart',
            'handleLongPressEnd',
            'fireControlCenterControl',
            'updateProtocolDeviceCards',
            'toggleProtocolDeviceOutput',
            'pulseProtocolDevice',
            'openProtocolDeviceInfo',
            'updateNodeRedDevices',
            'controlNodeRedDevice',
        ].forEach(name => installLazyGlobal(name, ['universal-view']));
        [
            'appleTransport',
            'clearAppleQueue',
            'initAppleAudioDemo',
            'loadAppleAudioStatus',
            'openAppleAudioConfig',
            'playAppleTrackNow',
            'promoteAppleTrack',
            'queueAppleTrack',
            'searchAppleSources',
            'setAppleCategoryFilter',
        ].forEach(name => installLazyGlobal(name, ['apple-audio-view']));
        [
            'checkHealth',
            'clearChat',
            'exportTraining',
            'loadConfig',
            'saveConfig',
            'sendChat',
        ].forEach(name => installLazyGlobal(name, ['local-model-view']));
        function prepareAppleAudioForM32() {
            showToast('可在配置页将音乐播放器输出路由到 M32 输入；当前页面会按需加载播放器控制模块。');
            return callLazyGlobal(['apple-audio-view'], 'openAppleAudioConfig', [], null);
        }
        function getProxyFlowSummaryLite(payload = {}) {
            const traffic = payload.traffic || {};
            const clients = payload.clients || {};
            const trafficAvailable = !!traffic.available;
            const formatRate = value => {
                const bps = Number(value || 0);
                if (!Number.isFinite(bps) || bps <= 0) return '0 bps';
                if (bps >= 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} Mbps`;
                if (bps >= 1024) return `${(bps / 1024).toFixed(1)} Kbps`;
                return `${bps.toFixed(0)} bps`;
            };
            const rxBps = trafficAvailable ? Number(traffic.rx_bps || 0) : Number(clients.download_bps || 0);
            const txBps = trafficAvailable ? Number(traffic.tx_bps || 0) : Number(clients.upload_bps || 0);
            return {
                rxText: trafficAvailable ? (traffic.rx_text || formatRate(rxBps)) : (clients.download_text || formatRate(rxBps)),
                txText: trafficAvailable ? (traffic.tx_text || formatRate(txBps)) : (clients.upload_text || formatRate(txBps)),
            };
        }
        function renderDashboardProxySummary(payload = {}) {
            const statusEl = document.getElementById('dash-proxy-status');
            const metaEl = document.getElementById('dash-proxy-meta');
            const statusMeta = typeof getDeviceStatusMeta === 'function'
                ? getDeviceStatusMeta(payload, { staleText: '陈旧', errorText: '异常' })
                : { text: payload.online ? '在线' : '离线', level: payload.online ? 'online' : 'error' };
            if (statusEl) {
                statusEl.textContent = statusMeta.text;
                statusEl.className = `value ${statusMeta.level === 'online' ? 'green' : (statusMeta.level === 'stale' || statusMeta.level === 'error' ? 'danger' : 'blue')}`;
            }
            if (metaEl) {
                const endpoint = String(payload.endpoint || payload.base_url || payload.host || '121 代理').trim();
                const healthy = Number(payload.healthy_target_count || 0);
                const total = Number(payload.check_count || 0);
                const requiredCheck = payload.required_check || payload.google_check || null;
                const googleOk = requiredCheck ? !!requiredCheck.healthy : !!payload.google_ok;
                const googleLatency = Number(requiredCheck?.latency_ms ?? payload.google_latency_ms);
                const googleCode = Number(requiredCheck?.status_code ?? payload.google_status_code);
                const clients = payload.clients || {};
                const flow = getProxyFlowSummaryLite(payload);
                const checkedAt = formatTimeShort(payload.last_checked_at || payload.updated_at || '');
                const lastErr = String(payload.last_error || payload.error || '').trim();
                const googleHint = `${googleOk ? 'Google正常' : 'Google异常'}${Number.isFinite(googleLatency) && googleLatency > 0 ? ` ${googleLatency}ms` : ''}${Number.isFinite(googleCode) && googleCode > 0 ? `/${googleCode}` : ''}`;
                const checkHint = total > 0 ? `${healthy}/${total} 探活` : '无探活数据';
                const clientHint = `IP ${Number(clients.active_client_count || 0)} / 连接 ${Number(clients.total_active_connections || 0)}`;
                metaEl.innerHTML = `${escapeHtml(endpoint)} · ${escapeHtml(googleHint)} · ${escapeHtml(checkHint)} · ${escapeHtml(clientHint)} · ${escapeHtml(`↓${flow.rxText} ↑${flow.txText}`)} · ${escapeHtml(checkedAt || '--')}${lastErr ? ` <br><strong>${escapeHtml(lastErr)}</strong>` : ''}`;
            }
        }
        function ensureInitialVisibleView() {
            const activeView = document.querySelector('.view-section.active');
            if (!activeView) {
                const dashboardView = document.getElementById('view-dashboard');
                if (dashboardView) dashboardView.classList.add('active');
            }
        }
        ensureInitialVisibleView();
        function ensurePermission(permission, actionText = '执行当前操作') {
            return SmartCenter.utils.ensurePermission(permission, actionText, {
                notifier: showToast,
            });
        }
        const myCharts = {};
        const pwrLocks = {};
        const pwrStates = {};
        const pwrPending = {};
        const pwrDesiredStates = {};
        const POWER_CHANNEL_LOCK_MS = 6000;
        const POWER_CHANNEL_VERIFY_HOLD_MS = 45000;
        const powerStatusCache = {};
        const powerHistoryCache = {};
        const powerLogCache = {};
        const powerSupplementFetchAt = {};
        const powerSupplementInFlight = {};
        let powerFetchInFlight = null;
        let powerVisibleSupplementCabIds = [];
        let meterCenterCache = { summary: {}, meters: [], trend: [] };
        let meterTrendTarget = 'total';
        let meterTrendPeriod = 'day';
        let meterCenterRequestSeq = 0;
        let meterTrendOptionSignature = '';
        let meterTrendAxisKey = '';
        let meterTrendYAxisMax = 0;
        let snmpStatusCache = {};
        let nvrStatusCache = {};
        let snmpCardFilter = 'all';
        let snmpStatusSignature = '';
        let snmpLastSuccessAt = 0;
        let snmpFetchFailureCount = 0;
        let snmpLastToastAt = 0;
        let snmpFetchInFlight = null;
        let snmpFetchMode = '';
        let snmpStatusMode = '';
        let snmpLastRenderAt = 0;
        let snmpSelectedDeviceId = '';
        let nvrSelectedDeviceId = '';
        let nvrSelectedChannelId = '';
        let nvrPreviewMode = 'smart';
        let nvrPreviewGrid = 16;
        let nvrPreviewPage = 0;
        const NVR_STREAM_CONCURRENCY_LIMIT = 8;
        const NVR_STREAM_STAGGER_MS = 520;
        const NVR_WALL_SNAPSHOT_REFRESH_MS = 10000;
        const nvrWallFrameTimers = [];
        let nvrWallSnapshotRefreshTimer = null;
        let automationStatusCache = { server_time: '', rules: [] };
        let automationStatusLoading = false;
        const snmpOpenDetailsState = {};
        let dashboardSummaryCache = null;
        let dashboardSummaryInFlight = null;

        function getPowerChannelStatus(cabId, chNum) {
            const desired = pwrDesiredStates[cabId]?.[chNum];
            if (desired && Date.now() - desired.ts < POWER_CHANNEL_LOCK_MS) {
                return desired.target;
            }
            const cachedChannels = (powerStatusCache[cabId] || {}).channels_1_4;
            if (Array.isArray(cachedChannels) && cachedChannels[chNum - 1] !== undefined) {
                return cachedChannels[chNum - 1];
            }
            return (pwrStates[cabId] || [])[chNum];
        }
        function setPowerDesiredState(cabId, chNum, targetState) {
            pwrDesiredStates[cabId] = pwrDesiredStates[cabId] || {};
            pwrDesiredStates[cabId][chNum] = {
                target: !!targetState,
                ts: Date.now(),
                confirmed: false,
            };
            pwrStates[cabId] = pwrStates[cabId] || [];
            pwrStates[cabId][chNum] = !!targetState;
        }
        function setPowerCabinetDesiredState(cabId, targetState) {
            const cab = configData.cabinets[cabId] || {};
            const count = Number(cab.channel_count || 8);
            for (let chNum = 1; chNum <= count; chNum += 1) {
                setPowerDesiredState(cabId, chNum, targetState);
            }
        }
        function clearPowerCabinetDesiredState(cabId) {
            if (pwrDesiredStates[cabId]) pwrDesiredStates[cabId] = {};
        }
        function clearPowerDesiredState(cabId, chNum) {
            if (pwrDesiredStates[cabId]) delete pwrDesiredStates[cabId][chNum];
        }
        function shouldAcceptPowerState(cabId, chNum, incomingState) {
            const desired = pwrDesiredStates[cabId]?.[chNum];
            if (!desired) return true;
            const age = Date.now() - desired.ts;
            const matchesTarget = !!incomingState === !!desired.target;
            if (matchesTarget) {
                desired.confirmed = true;
                desired.confirmedAt = Date.now();
                return true;
            }
            if (age < POWER_CHANNEL_VERIFY_HOLD_MS) return false;
            delete pwrDesiredStates[cabId][chNum];
            return true;
        }
        function applyPowerStatusSnapshot(cabId, status) {
            if (!status || !Array.isArray(status.channels_1_4)) return false;
            const previous = powerStatusCache[cabId] || {};
            const safeStatus = Object.assign({}, previous, status || {});
            const nextStates = safeStatus.channels_1_4.map((st, idx) => {
                const chNum = idx + 1;
                if (!shouldAcceptPowerState(cabId, chNum, st)) {
                    const desired = pwrDesiredStates[cabId]?.[chNum];
                    return desired ? desired.target : (pwrStates[cabId] || [])[chNum];
                }
                return st;
            });
            safeStatus.channels_1_4 = nextStates;
            safeStatus.channel_on_count = nextStates.filter(Boolean).length;
            powerStatusCache[cabId] = safeStatus;
            pwrStates[cabId] = pwrStates[cabId] || [];
            nextStates.forEach((st, idx) => {
                const chNum = idx + 1;
                pwrStates[cabId][chNum] = st;
                renderPwrChannel(cabId, chNum);
            });
            return true;
        }
        const lightLocks = {};
        const lightStates = {};
        const lightInputStates = {};
        const lightOnlineStates = {};
        const projectorConfigs = configData.projectors || [];
        const upsConfigs = configData.ups_devices || [];
        window.upsConfigs = upsConfigs;
        if (window.SmartCenter?.ups?.setUpsConfigs) window.SmartCenter.ups.setUpsConfigs(upsConfigs);
        const snmpConfigs = configData.snmp_devices || [];
        const nvrConfigs = Array.isArray(configData.nvr_devices) ? configData.nvr_devices : [];
        const sequencerConfigs = Array.isArray(configData.sequencers) ? configData.sequencers : [];
        const dashboardSectionConfig = configData.dashboard_sections || {};
        let doorVideoActive = false;
        let doorVideoNonce = 0;
        let lastDoorStatusFetchAt = 0;
        let doorCameraStatusCache = {};
        let doorViewSlots = ((configData.door_config || {}).view_slots) || { left: 'main', right: 'aux' };
        let doorRegionsCache = ((configData.door_config || {}).regions) || {};
        let appPollingStarted = false;
        const pollingTasks = [];
        const serverCommandPending = {};
        let serverCommandRefreshTimer = null;
        function setDoorSlotVisual(slot, payload) {
            const els = getDoorSlotElements(slot);
            const stateEl = els.state;
            const metaEl = els.meta;
            if (!stateEl || !metaEl) return;
            const enabled = payload ? payload.enabled !== false : true;
            const online = !!(payload && payload.online);
            const configured = !!(payload && payload.configured);
            const transport = String((payload && payload.transport) || '').toUpperCase();
            stateEl.textContent = !enabled ? '停用' : (online ? '在线' : (configured ? '离线' : '未配置'));
            stateEl.className = `tag ${(!enabled) ? '' : (online ? 'green' : (configured ? 'warn' : ''))}`;
            if (!enabled) {
                metaEl.textContent = '监控已停用';
                return;
            }
            if (!configured) {
                metaEl.textContent = '未配置 RTSP';
                return;
            }
            if (online) {
                metaEl.textContent = `${transport || '--'} · ${payload.frame_width || '--'}x${payload.frame_height || '--'}`;
                return;
            }
            metaEl.textContent = payload.last_error_text || payload.last_error || '等待重连';
        }
        function formatDoorCameraDiag(payload) {
            const p = payload && typeof payload === 'object' ? payload : {};
            const name = String(p.name || p.key || '--');
            const host = String(p.host || '--');
            const enabled = p.enabled === false ? '停用' : '启用';
            const configured = p.configured ? '已配置' : '未配置';
            const online = p.online ? '在线' : '离线';
            const transport = p.online ? String((p.transport || '--')).toUpperCase() : '--';
            const errorText = String(p.last_error_text || p.last_error || (p.online ? '正常' : '等待重连'));
            const lastAttempt = String(p.last_attempt_at || '--');
            return `
                <div style="padding:12px 14px; border-radius:12px; background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.14); min-width:220px; flex:1;">
                    <div style="display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px;">
                        <strong style="color:#e2e8f0; font-size:13px;">${escapeHtml(name)}</strong>
                        <span class="tag ${p.online ? 'green' : 'warn'}">${escapeHtml(online)}</span>
                    </div>
                    <div style="font-size:12px; color:#94a3b8; line-height:1.8;">
                        <div>地址: <span style="color:#e2e8f0;">${escapeHtml(host)}</span></div>
                        <div>状态: <span style="color:#e2e8f0;">${enabled} / ${configured}</span></div>
                        <div>链路: <span style="color:#e2e8f0;">${escapeHtml(transport)}</span></div>
                        <div>错误: <span style="color:#f8fafc;">${escapeHtml(errorText)}</span></div>
                        <div>最近尝试: <span style="color:#e2e8f0;">${escapeHtml(lastAttempt)}</span></div>
                    </div>
                </div>
            `;
        }
        function renderDoorNetworkSummary() {
            const container = document.getElementById('doorNetworkSummary');
            if (!container) return;
            const leftPayload = doorCameraStatusCache[getDoorSlotCameraKey('left')] || {};
            const rightPayload = doorCameraStatusCache[getDoorSlotCameraKey('right')] || {};
            container.innerHTML = `${formatDoorCameraDiag(leftPayload)}${formatDoorCameraDiag(rightPayload)}`;
        }
        function syncDoorVideoSources(forceReload = false) {
            [['left', getDoorSlotElements('left')], ['right', getDoorSlotElements('right')]].forEach(([slot, els]) => {
                if (!els.image) return;
                const cameraKey = getDoorSlotCameraKey(slot);
                const payload = doorCameraStatusCache[cameraKey] || {};
                const targetSrc = `/video_feed/${cameraKey}?_=${doorVideoNonce}`;
                if (!doorVideoActive || payload.enabled === false || payload.configured === false) {
                    els.image.removeAttribute('src');
                    return;
                }
                const currentSrc = String(els.image.getAttribute('src') || '');
                if (forceReload || !currentSrc || !currentSrc.includes(`/video_feed/${cameraKey}`)) {
                    els.image.src = targetSrc;
                }
            });
        }
        function getDoorSlotCameraKey(slot) {
            const key = String((doorViewSlots || {})[slot] || '').trim();
            if (key) return key;
            return slot === 'right' ? 'main' : 'aux';
        }
        function getDoorSlotElements(slot) {
            const isRight = slot === 'right';
            return {
                image: document.getElementById(isRight ? 'videoImgAux' : 'videoImg'),
                canvas: document.getElementById(isRight ? 'drawCanvasAux' : 'drawCanvasMain'),
                label: document.getElementById(isRight ? 'doorCameraAuxLabel' : 'doorCameraMainLabel'),
                state: document.getElementById(isRight ? 'doorCameraAuxState' : 'doorCameraMainState'),
                meta: document.getElementById(isRight ? 'doorCameraAuxMeta' : 'doorCameraMainMeta'),
            };
        }
        function updateDoorSlotLabels() {
            ['left', 'right'].forEach(slot => {
                const cameraKey = getDoorSlotCameraKey(slot);
                const payload = doorCameraStatusCache[cameraKey] || {};
                const els = getDoorSlotElements(slot);
                if (els.label) {
                    const slotText = slot === 'right' ? '右侧画面' : '左侧画面';
                    els.label.textContent = `${slotText} · ${payload.name || cameraKey || '--'}`;
                }
            });
        }
        function startDoorVideoStream() {
            const leftEls = getDoorSlotElements('left');
            const rightEls = getDoorSlotElements('right');
            if (!leftEls.image && !rightEls.image) return;
            doorVideoActive = true;
            doorVideoNonce += 1;
            syncDoorVideoSources(true);
            updateDoorSlotLabels();
        }
        function stopDoorVideoStream() {
            doorVideoActive = false;
            ['left', 'right'].forEach(slot => {
                const els = getDoorSlotElements(slot);
                if (els.image) els.image.removeAttribute('src');
            });
        }
        function isPageVisible() {
            return document.visibilityState !== 'hidden';
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                stopDoorVideoStream();
            } else if (getActiveViewId() === 'door') {
                setTimeout(() => {
                    startDoorVideoStream();
                    updateDoorStatus(true);
                }, 80);
            }
            refreshPollingVisibility();
        });
        function getActiveViewId() {
            const active = document.querySelector('.view-section.active');
            return active ? String(active.id || '').replace(/^view-/, '') : 'dashboard';
        }
        function isDashboardSectionVisible(sectionId) {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard || !dashboard.classList.contains('active')) return false;
            const section = dashboard.querySelector(`[data-section-id="${sectionId}"]`);
            if (!section) return false;
            if (section.style.display === 'none') return false;
            const style = window.getComputedStyle ? window.getComputedStyle(section) : null;
            return !style || (style.display !== 'none' && style.visibility !== 'hidden');
        }
        function registerPollingTask(name, intervalMs, run, shouldRun) {
            const task = {
                name,
                intervalMs: Math.max(300, Number(intervalMs) || 1000),
                baseIntervalMs: Math.max(300, Number(intervalMs) || 1000),
                run,
                shouldRun: typeof shouldRun === 'function' ? shouldRun : (() => true),
                timer: null,
                running: false,
            };
            pollingTasks.push(task);
            if (appPollingStarted && isPageVisible()) {
                schedulePollingTask(task, getPollingInitialDelay(task, pollingTasks.length - 1));
            }
            return task;
        }
        function setTextIfExists(id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        }
        function setHtmlIfExists(id, html) {
            const el = document.getElementById(id);
            if (el) el.innerHTML = html;
        }
        function normalizeDashboardSummaryPayload(payload) {
            return SmartCenter.dashboardSummary.normalizeDashboardSummaryPayload.apply(SmartCenter.dashboardSummary, arguments);
        }
        function getDashboardSummaryModule(name) {
            return ((dashboardSummaryCache || {}).modules || {})[name] || {};
        }
        function getDashboardSummaryCount(name) {
            return ((dashboardSummaryCache || {}).counts || {})[name] || {};
        }
        function getDashboardSummaryRenderContext() {
            return { pickDashboardEnvSensor, renderDashboardProxySummary };
        }
        function renderDashboardSummaryTopStats(payload) {
            return SmartCenter.dashboardSummary.renderDashboardSummaryTopStats(payload, getDashboardSummaryRenderContext());
        }
        function renderDashboardFooterStatus(payload = {}, derived = {}) {
            return SmartCenter.dashboardSummary.renderDashboardFooterStatus(payload, derived);
        }
        function renderDashboardEnvSummary(envModule = {}) {
            return SmartCenter.dashboardSummary.renderDashboardEnvSummary(envModule, getDashboardSummaryRenderContext());
        }
        function updateDashboardSummary() {
            if (dashboardSummaryInFlight) return dashboardSummaryInFlight;
            dashboardSummaryInFlight = fetchJson('/api/dashboard/summary', {}, '首页汇总状态读取失败')
                .then(data => {
                    dashboardSummaryCache = normalizeDashboardSummaryPayload(data);
                    renderDashboardSummaryTopStats(dashboardSummaryCache);
                    const serverMachines = dashboardSummaryCache.modules?.server?.machines;
                    if (Array.isArray(serverMachines)) {
                        dashboardServerCompactList = serverMachines;
                        renderDashboardServerCompactWhenReady(dashboardServerCompactList);
                    }
                    if (getActiveViewId() === 'proxy' && dashboardSummaryCache.modules?.proxy) {
                        renderProxyDetail(dashboardSummaryCache.modules.proxy);
                    }
                    return dashboardSummaryCache;
                })
                .catch(err => {
                    console.error('首页汇总状态读取失败', err);
                    throw err;
                })
                .finally(() => {
                    dashboardSummaryInFlight = null;
                });
            return dashboardSummaryInFlight;
        }
        function resolveVisiblePowerSupplementCabIds(activeView = getActiveViewId()) {
            if (activeView === 'power') {
                return Array.isArray(configData.cabinets) ? configData.cabinets.map((_, idx) => idx) : [];
            }
            if (activeView === 'dashboard' && (isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick'))) {
                return Array.isArray(configData.cabinets)
                    ? configData.cabinets
                        .map((_, idx) => idx)
                        .filter(idx => !!document.getElementById(`dash-power-card-${idx}`))
                    : [];
            }
            return [];
        }
        function applyAdaptivePollingInterval(task) {
            if (!task) return;
            const base = Number(task.baseIntervalMs || task.intervalMs || 1000);
            const activeView = getActiveViewId();
            const isSnmpTask = task.name === 'snmp';
            const isLightTask = task.name === 'light';
            const isPowerTask = task.name === 'power';
            const isDetailView = (isSnmpTask && activeView === 'snmp') || (isLightTask && activeView === 'light') || (isPowerTask && activeView === 'power');
            if (isDetailView) {
                task.intervalMs = base;
                return;
            }
            const dashboardMode = activeView === 'dashboard';
            if (dashboardMode && task.shouldRun()) {
                task.intervalMs = Math.round(base * (isSnmpTask ? 1.35 : (isPowerTask ? 1.2 : 1.2)));
            } else {
                task.intervalMs = Math.round(base * (isSnmpTask ? 2.0 : (isPowerTask ? 1.4 : 1.6)));
            }
        }
        function stopAllPollingTasks() {
            pollingTasks.forEach(task => {
                if (task.timer) {
                    clearTimeout(task.timer);
                    task.timer = null;
                }
            });
        }
        function schedulePollingTask(task, delayMs = null) {
            if (task.timer) clearTimeout(task.timer);
            applyAdaptivePollingInterval(task);
            task.timer = setTimeout(async () => {
                task.timer = null;
                if (!isPageVisible() || !task.shouldRun()) {
                    schedulePollingTask(task, task.intervalMs);
                    return;
                }
                if (task.running) {
                    schedulePollingTask(task, task.intervalMs);
                    return;
                }
                task.running = true;
                try {
                    await task.run();
                } catch (err) {
                    console.error(`Polling task failed: ${task.name}`, err);
                } finally {
                    task.running = false;
                    schedulePollingTask(task, task.intervalMs);
                }
            }, Math.max(50, delayMs ?? task.intervalMs));
        }
        const DASHBOARD_POLLING_INITIAL_DELAYS = {
            dashboard_summary: 80,
            hvac: 900,
            light: 1400,
            power: 1800,
            sequencer: 2400,
            ups: 3000,
            env: 3600,
            projector: 4400,
            screen: 5200,
            automation: 6000,
            hy_edge: 7000,
            door: 7800,
            logs: 8600,
            snmp: 9800,
            meter: 12500,
        };
        function getPollingInitialDelay(task, index) {
            const activeView = getActiveViewId();
            if (activeView === 'dashboard') {
                return DASHBOARD_POLLING_INITIAL_DELAYS[task.name] ?? (500 + index * 220);
            }
            return 90 + index * 120;
        }
        function startAppPolling() {
            if (appPollingStarted) return;
            appPollingStarted = true;
            pollingTasks.forEach((task, index) => schedulePollingTask(task, getPollingInitialDelay(task, index)));
        }
        function refreshPollingVisibility() {
            if (!isPageVisible()) {
                stopDoorVideoStream();
                stopAllPollingTasks();
                return;
            }
            pollingTasks.forEach((task, index) => {
                if (!task.timer) schedulePollingTask(task, getPollingInitialDelay(task, index));
            });
        }
        let projectorStatusCache = {};
        let sequencerStatusCache = {};
        let currentProjectorRemoteId = null;
        let sequencerFilters = { dashboard: 'all', page: 'all' };
        let globalServerList = [];
        let dashboardServerCompactList = [];
        function canOpenConfigCenter() {
            const role = String(currentUser.role || '').toLowerCase();
            const accountCategory = String(currentUser.account_category || '').toLowerCase();
            if (role === 'admin' || accountCategory === 'admin') return true;
            const hasView = hasPermission('config.view');
            const hasElevatedConfigPermission = hasPermission('system.config')
                || hasPermission('auth.manage')
                || hasPermission('meter.config')
                || hasPermission('control_center.config');
            return hasView && hasElevatedConfigPermission;
        }
        const serverMonitorConfig = configData.server_monitor || { agent_host: '', agent_port: 6899 };
        let latestAgentVersion = String(serverMonitorConfig.agent_version || '').trim();
        const hvacConfigs = Array.isArray(configData.hvac_devices) ? configData.hvac_devices : [];
        let hvacStatusCache = {};
        if (!Array.isArray(configData.sidebar)) configData.sidebar = [];
        if (hvacConfigs.length && !configData.sidebar.find(item => item.id === 'hvac')) {
            configData.sidebar.push({ id: 'hvac', icon: '❄️', name: '空调控制', sort: 4.6, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'sequencer')) {
            configData.sidebar.push({ id: 'sequencer', icon: '🔌', name: '时序电源', sort: 3, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'snmp')) {
            configData.sidebar.push({ id: 'snmp', icon: '📡', name: 'SNMP监测', sort: 4.2, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'apple_audio')) {
            configData.sidebar.push({ id: 'apple_audio', icon: '🎼', name: '音乐播放器', sort: 10.5, visible: true });
        }
        if (hvacConfigs.length && !dashboardSectionConfig.hvac) {
            dashboardSectionConfig.hvac = { title: '空调总览', visible: true, sort: 24 };
        }
        if (!dashboardSectionConfig.sequencer) {
            dashboardSectionConfig.sequencer = { title: '时序电源', visible: true, sort: 25 };
        }
        if (!dashboardSectionConfig.snmp) {
            dashboardSectionConfig.snmp = { title: '网络与录像机', visible: true, sort: 27 };
        }
        const homeDashboardOrder = {
            stats: 10,
            projector: 20,
            hvac: 21,
            hy_edge: 22,
            ups_compact: 23,
            screen: 24,
            sequencer: 25,
            light_compact: 26,
            power_compact: 27,
            snmp: 27.2,
            server_compact: 28,
        };
        Object.entries(homeDashboardOrder).forEach(([key, sort]) => {
            dashboardSectionConfig[key] = Object.assign(
                { title: key, visible: true, sort },
                dashboardSectionConfig[key] || {},
                { sort }
            );
        });
        const dashboardSectionDefaults = {
            power_compact: { title: '强电柜状态', visible: true, sort: homeDashboardOrder.power_compact },
            light_compact: { title: '灯光控制显示', visible: true, sort: homeDashboardOrder.light_compact },
            server_compact: { title: '机器状态', visible: true, sort: homeDashboardOrder.server_compact },
            ups_compact: { title: 'UPS状态', visible: true, sort: homeDashboardOrder.ups_compact },
            screen: { title: '幕布状态', visible: true, sort: homeDashboardOrder.screen },
        };
        Object.entries(dashboardSectionDefaults).forEach(([key, defaults]) => {
            dashboardSectionConfig[key] = Object.assign({}, defaults, dashboardSectionConfig[key] || {}, { sort: defaults.sort });
        });
        if (dashboardSectionConfig.screen) {
            dashboardSectionConfig.screen.sort = homeDashboardOrder.screen;
            dashboardSectionConfig.screen.visible = dashboardSectionConfig.screen.visible !== false;
        }
        function getAgentBaseUrl() {
            const host = (serverMonitorConfig.agent_host || '').trim() || window.location.hostname;
            const port = parseInt(serverMonitorConfig.agent_port || 6899, 10) || 6899;
            return `http://${host}:${port}`;
        }
        function getDeployBatUrl() {
            return `${getAgentBaseUrl()}/deploy_agent.bat`;
        }
        function getDeployCommandText() {
            const batUrl = `${getDeployBatUrl()}?ts=$(Get-Date -Format yyyyMMddHHmmss)`;
            return `$u="${batUrl}"; $p="$env:TEMP\\smart-center-deploy.bat"; iwr -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -Uri $u -OutFile $p; Start-Process -FilePath $p -Verb RunAs`;
        }
        function formatDeployGeneratedAt(date = new Date()) {
            const pad = value => String(value).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
        }
        function updateDeployModalInfo() {
            const versionEl = document.getElementById('deploy-agent-version-text');
            if (versionEl) versionEl.textContent = latestAgentVersion || '读取中...';
            const generatedAtEl = document.getElementById('deploy-generated-at-text');
            if (generatedAtEl) generatedAtEl.textContent = formatDeployGeneratedAt();
            const deployCmdEl = document.getElementById('deploy-cmd-text');
            if (deployCmdEl) deployCmdEl.textContent = getDeployCommandText();
            const deployBatUrlEl = document.getElementById('deploy-bat-url-text');
            if (deployBatUrlEl) deployBatUrlEl.textContent = getDeployBatUrl();
        }
        function openDeployModal() {
            updateDeployModalInfo();
            const modal = document.getElementById('deployModal');
            if (modal) modal.style.display = 'block';
            refreshLatestAgentVersion().finally(() => updateDeployModalInfo());
        }
        function parseAgentVersionBase(version) {
            const text = String(version || '').trim();
            const match = text.match(/\d+(?:\.\d+){3}/);
            if (!match) return null;
            return match[0].split('.').map(part => Number.parseInt(part, 10));
        }
        function compareAgentVersionBase(currentVersion, latestVersion) {
            const currentParts = parseAgentVersionBase(currentVersion);
            const latestParts = parseAgentVersionBase(latestVersion);
            if (!currentParts || !latestParts) {
                const currentText = String(currentVersion || '').trim();
                const latestText = String(latestVersion || '').trim();
                return currentText === latestText ? 0 : -1;
            }
            for (let i = 0; i < Math.max(currentParts.length, latestParts.length); i += 1) {
                const current = currentParts[i] || 0;
                const latest = latestParts[i] || 0;
                if (current < latest) return -1;
                if (current > latest) return 1;
            }
            return 0;
        }
        function refreshLatestAgentVersion() {
            const ts = Date.now();
            const primaryUrl = `/agent/config?probe=1&ts=${ts}`;
            const fallbackUrl = `${getAgentBaseUrl()}/agent/config?probe=1&ts=${ts}`;
            const applyVersion = data => {
                const version = String(data?.version || '').trim();
                    if (version) {
                        latestAgentVersion = version;
                        updateDeployModalInfo();
                        if (Array.isArray(globalServerList) && globalServerList.length) {
                        renderServerGridDeferred(globalServerList, { force: true });
                        renderDashboardServerCompactWhenReady(globalServerList);
                    }
                }
                return version;
            };
            return fetchJson(primaryUrl, {}, '读取 Agent 最新版本失败')
                .catch(() => fetchJson(fallbackUrl, {}, '读取 Agent 最新版本失败'))
                .then(data => {
                    return applyVersion(data);
                })
                .catch(err => {
                    console.warn('Agent 最新版本读取失败', err);
                    return latestAgentVersion;
                });
        }
        function copyDeployCommand() {
            return copyTextWithToast(getDeployCommandText(), '覆盖安装命令已复制');
        }
        function copyDeployBatUrl() {
            return copyTextWithToast(getDeployBatUrl(), '批处理地址已复制');
        }
        function getServerSummaryApi() {
            return window.SmartCenter?.serverSummary || window.SmartCenter?.serverMonitor || null;
        }
        function buildServerDiagnostic(agent = {}, machine = {}) {
            const api = getServerSummaryApi();
            if (!api || typeof api.buildServerDiagnostic !== 'function') {
                return { level: 'warn', badgeText: '摘要加载中', reportOnline: false, summary: '服务器摘要模块加载中' };
            }
            return api.buildServerDiagnostic.apply(api, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function showToast(msg, isError=false) {
            return SmartCenter.utils.showToast(msg, isError);
        }
        function toggleUserMenu(forceOpen = null) {
            const menu = document.getElementById('top-user-menu');
            if (!menu) return;
            const shouldOpen = forceOpen === null ? !menu.classList.contains('open') : !!forceOpen;
            menu.classList.toggle('open', shouldOpen);
        }
        function openConfigCenter() {
            if (!canOpenConfigCenter()) {
                showToast('当前账号无配置中心访问权限', true);
                return;
            }
            window.location.href = '/config';
        }
        function goToLoginPage() {
            toggleUserMenu(false);
            window.location.href = '/login';
        }
        function logoutCurrentUser() {
            toggleUserMenu(false);
            fetchJson('/api/auth/logout', { method: 'POST' }, '退出登录失败')
                .then(() => {
                    showToast('已退出当前账号');
                    window.location.href = '/login';
                })
                .catch(err => showToast(err.message || '退出登录失败', true));
        }
        function copyTextWithToast(text, successText = '复制成功') {
            const value = String(text || '').trim();
            if (!value) {
                showToast('没有可复制的内容', true);
                return Promise.resolve(false);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                return navigator.clipboard.writeText(value)
                    .then(() => {
                        showToast(successText);
                        return true;
                    })
                    .catch(() => {
                        const temp = document.createElement('textarea');
                        temp.value = value;
                        temp.style.position = 'fixed';
                        temp.style.opacity = '0';
                        document.body.appendChild(temp);
                        temp.focus();
                        temp.select();
                        let copied = false;
                        try {
                            copied = document.execCommand('copy');
                        } catch (_) {
                            copied = false;
                        }
                        document.body.removeChild(temp);
                        showToast(copied ? successText : '复制失败，请手动复制', !copied);
                        return copied;
                    });
            }
            const temp = document.createElement('textarea');
            temp.value = value;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.focus();
            temp.select();
            let copied = false;
            try {
                copied = document.execCommand('copy');
            } catch (_) {
                copied = false;
            }
            document.body.removeChild(temp);
            showToast(copied ? successText : '复制失败，请手动复制', !copied);
            return Promise.resolve(copied);
        }
        function getAutomationStatusMap() {
            return new Map((Array.isArray(automationStatusCache.rules) ? automationStatusCache.rules : []).map(item => [String(item.id), item]));
        }
        function getAutomationStatusCache() {
            return automationStatusCache;
        }
        function getAutomationViewApi() {
            return window.SmartCenter?.automationView || null;
        }
        function ensureAutomationViewReady(contextLabel = '自动化详情模块') {
            if (getAutomationViewApi()) return Promise.resolve(getAutomationViewApi());
            return ensureModulesReady(['automation-view'], contextLabel).then(() => getAutomationViewApi());
        }
        function getAutomationRuntimeContext() {
            return {
                configData,
                currentUser,
                getActiveViewId,
                getAutomationStatusCache,
                getAutomationStatusMap,
                loadAutomationStatus,
                loadAutomationLogs: window.SmartCenter?.logs?.loadAutomationLogs || window.loadAutomationLogs,
                ensurePermission,
                postJsonLoose,
                translateApiError,
                showToast,
                formatAutomationRuleTime,
                formatAutomationValue,
                escapeHtml,
            };
        }
        function renderAutomationPageStatus() {
            const rules = Array.isArray(automationStatusCache.rules) ? automationStatusCache.rules : [];
            if (getActiveViewId() !== 'auto') return;
            if (!document.getElementById('view-auto')) return;
            ensureAutomationViewReady('自动化运行页面模块')
                .then(api => api?.renderAutomationPageStatus?.(rules, getAutomationRuntimeContext()))
                .catch(() => {});
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
                if (getActiveViewId() === 'auto') {
                    renderAutomationPageStatus();
                }
            } catch (err) {
                if (showError) showToast(err.message || '自动化状态读取失败', true);
                console.error('自动化状态读取失败', err);
            } finally {
                automationStatusLoading = false;
            }
        }
        let echartsRuntimeLoading = null;
        function isChartElementRenderable(dom) {
            if (!dom || !dom.isConnected) return false;
            const rect = typeof dom.getBoundingClientRect === 'function' ? dom.getBoundingClientRect() : null;
            if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
            if (dom.clientWidth <= 0 || dom.clientHeight <= 0) return false;
            const style = window.getComputedStyle ? window.getComputedStyle(dom) : null;
            return !style || (style.display !== 'none' && style.visibility !== 'hidden');
        }
        function ensureEChartsRuntime(contextLabel = '图表') {
            if (window.echarts) return Promise.resolve(window.echarts);
            if (!echartsRuntimeLoading) {
                echartsRuntimeLoading = SmartCenter.utils.ensureEChartsLoaded()
                    .catch(err => {
                        console.error(`${contextLabel}运行库加载失败`, err);
                        showToast(`${contextLabel}运行库加载失败，请刷新后重试`, true);
                        throw err;
                    })
                    .finally(() => {
                        echartsRuntimeLoading = null;
                    });
            }
            return echartsRuntimeLoading;
        }
        function ensurePowerChart(cabId) {
            if (typeof echarts === 'undefined') return null;
            const chartEl = document.getElementById(`energyChart_${cabId}`);
            if (!isChartElementRenderable(chartEl)) return null;
            if (myCharts[cabId]) return myCharts[cabId];
            try {
                myCharts[cabId] = echarts.init(chartEl);
                return myCharts[cabId];
            } catch (e) {
                console.error('强电图表初始化失败', cabId, e);
                return null;
            }
        }
        function resizePowerCharts() {
            if (typeof echarts === 'undefined') return;
            configData.cabinets.forEach((_, cabId) => {
                const chart = ensurePowerChart(cabId);
                if (!chart) return;
                try { chart.resize(); } catch (e) { console.error('强电图表 resize 失败', cabId, e); }
            });
        }
        function renderPowerEnergyChart(cabId, rawData) {
            const chartEl = document.getElementById(`energyChart_${cabId}`);
            if (!isChartElementRenderable(chartEl)) return;
            if (typeof echarts === 'undefined') {
                ensureEChartsRuntime('强电图表').then(() => renderPowerEnergyChart(cabId, rawData)).catch(() => {});
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
                    axisLabel: {
                        color: '#94a3b8',
                        rotate: data.length > 14 ? 35 : 0,
                        interval: data.length > 20 ? 2 : 0
                    }
                },
                yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#94a3b8' } },
                series: [{
                    data: data.map(item => Number(item.consume || 0)),
                    type: 'bar',
                    barMaxWidth: data.length > 20 ? 14 : 24,
                    itemStyle: {
                        color: params => (data[params.dataIndex] && data[params.dataIndex].is_today) ? '#f59e0b' : '#3b82f6',
                        borderRadius: [4,4,0,0]
                    },
                    label: {
                        show: data.length <= 14,
                        position: 'top',
                        color: '#f8fafc'
                    }
                }],
                graphic: nonZeroCount > 1 ? [] : [{
                    type: 'text',
                    right: 12,
                    top: 10,
                    style: {
                        text: '历史数据仍在累计，当前以近 7 天摘要展示',
                        fill: '#94a3b8',
                        fontSize: 11
                    }
                }]
            };
            try {
                chart.setOption(option, true);
                chart.resize();
            } catch (e) {
                console.error('强电图表渲染失败', cabId, e);
            }
        }
        function sanitizeReadableText(value, fallback = '--') {
            return SmartCenter.powerMeter.sanitizeReadableText.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function formatPowerValue(value, digits = 1, suffix = '') {
            return SmartCenter.powerMeter.formatPowerValue.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function getCabinetDisplayName(cab, cabId) {
            return SmartCenter.powerMeter.getCabinetDisplayName.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function getCabinetSubtitle(cab) {
            return SmartCenter.powerMeter.getCabinetSubtitle.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function getPowerChannelDisplayName(cab, chNum) {
            return SmartCenter.powerMeter.getPowerChannelDisplayName.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function getPowerChannelConfig(cab, chNum) {
            return SmartCenter.powerMeter.getPowerChannelConfig.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function getPowerChannelRemark(cab, chNum) {
            return SmartCenter.powerMeter.getPowerChannelRemark.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderPowerChannelLabelHtml(cab, chNum, options = {}) {
            return SmartCenter.powerMeter.renderPowerChannelLabelHtml.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderDashboardPowerHistory(historyRows, status) {
            return SmartCenter.powerMeter.renderDashboardPowerHistory.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderDashboardPowerCards() {
            const container = document.getElementById('dashboard-power-grid');
            if (!container) return;
            const cabinets = Array.isArray(configData.cabinets) ? configData.cabinets : [];
            if (!cabinets.length) {
                container.innerHTML = '<div style="color:var(--text-sub); text-align:center; padding:20px;">未配置强电柜</div>';
                return;
            }
            container.innerHTML = cabinets.map((cab, cabId) => {
                const status = powerStatusCache[cabId] || {};
                const online = !!status.comm_status;
                const visibleChannels = (Array.isArray(cab.channels_config) ? cab.channels_config : [])
                    .filter(item => item && item.visible !== false)
                    .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                    .slice(0, 6);
                    const channelsHtml = visibleChannels.map(ch => {
                        const chNum = Number(ch.channel);
                        const state = getPowerChannelStatus(cabId, chNum);
                        const isPending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]);
                        const cls = isPending ? 'ch-off' : (state === null || state === undefined ? 'ch-err' : (state ? 'ch-on' : 'ch-off'));
                        const stateText = isPending ? '执行中' : (state === null || state === undefined ? '离线' : (state ? '已合闸' : '已断开'));
                        return `<button class="power-mini-channel ${cls}${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                        ${renderPowerChannelLabelHtml(cab, chNum)}
                        <span class="state">${escapeHtml(stateText)}</span>
                    </button>`;
                }).join('');
                const logs = (powerLogCache[cabId] || []).slice(0, 2);
                const logsHtml = logs.length ? logs.map(log => {
                    const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
                    return `<div class="dashboard-power-log-item"><span class="dashboard-power-log-time">[${timeText}]</span>${renderPowerLogSourceTag(log, 'dashboard-power-log-source')}<span class="dashboard-power-log-text">${escapeHtml(normalizeLogOperationText(log))}</span></div>`;
                }).join('') : '<div class="dashboard-power-log-empty">暂无最近操作</div>';
                const workMode = sanitizeReadableText(status.work_mode, '未知模式');
                const tempValue = Number(status.cabinet_temp);
                const humiValue = Number(status.cabinet_humidity);
                const stopMsg = escapeHtml(String(cab?.ui_text?.confirm_stop || '确定要停止该电柜所有通道吗？'));
                return `<div class="dashboard-power-card ${online ? '' : 'offline'}" id="dash-power-card-${cabId}">
                    <div class="dashboard-power-head">
                        <div>
                            <div class="dashboard-power-title">${escapeHtml(getCabinetDisplayName(cab, cabId))}</div>
                            <div class="dashboard-power-subtitle">${escapeHtml(getCabinetSubtitle(cab))}</div>
                        </div>
                        <div class="dashboard-power-chip-row">
                            <span class="ups-chip ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span>
                            <span class="ups-chip">${escapeHtml(workMode)}</span>
                        </div>
                    </div>
                    <div class="dashboard-power-kpis">
                        <div class="dashboard-power-kpi">
                            <div class="label">实时功率</div>
                            <div class="value warn">${formatPowerValue(status.realtime_power, 2, ' kW')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">今日用电</div>
                            <div class="value ok">${formatPowerValue(status.daily_energy, 1, ' kWh')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">本月用电</div>
                            <div class="value">${formatPowerValue(status.monthly_energy, 1, ' kWh')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">温湿度</div>
                            <div class="value">${Number.isFinite(tempValue) ? tempValue.toFixed(1) + ' C' : '--'} / ${Number.isFinite(humiValue) ? humiValue.toFixed(1) + '%' : '--'}</div>
                        </div>
                    </div>
                    ${renderDashboardPowerHistory(powerHistoryCache[cabId], status)}
                    <div class="dashboard-power-channels">${channelsHtml || '<div class="dashboard-power-log-empty" style="grid-column:1/-1;">暂无可控通道</div>'}</div>
                    <div class="dashboard-power-actions">
                        <button class="dashboard-mini-btn success${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStart(${cabId})">一键启动</button>
                        <button class="dashboard-mini-btn danger${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStop(${cabId}, '${stopMsg}')">一键停止</button>
                        <button class="dashboard-mini-btn secondary" type="button" onclick="switchTab('power', '强电控制')">详情</button>
                    </div>
                    <div class="dashboard-power-log">
                        <div class="dashboard-power-log-title">最近操作</div>
                        <div class="dashboard-power-log-list">${logsHtml}</div>
                    </div>
                </div>`;
            }).join('');
        }
        function formatHomeNumber(value, digits = 0, suffix = '') {
            return SmartCenter.powerMeter.formatHomeNumber.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderHomeCompactMetric(label, value, tone = '') {
            return SmartCenter.powerMeter.renderHomeCompactMetric.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderDashboardPowerCompact() {
            const container = document.getElementById('dashboard-power-compact-grid');
            if (!container) return;
            const cabinets = Array.isArray(configData.cabinets) ? configData.cabinets : [];
            if (!cabinets.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置强电柜</div>';
                return;
            }
            container.classList.add('home-status-list');
            container.innerHTML = cabinets.map((cab, cabId) => {
                const status = powerStatusCache[cabId] || {};
                const online = !!(status.comm_status || status.online);
                const channels = Array.isArray(status.channels_1_4) ? status.channels_1_4.slice(0, Number(cab.channel_count || 8)) : [];
                const configuredChannels = Array.isArray(cab.channels_config) ? cab.channels_config.filter(ch => ch && ch.visible !== false).length : 0;
                const totalChannels = Number(status.channel_count || cab.channel_count || configuredChannels || channels.length || 0);
                const onCount = Number.isFinite(Number(status.channel_on_count))
                    ? Number(status.channel_on_count)
                    : channels.filter(st => st === true || st === 1 || st === '1').length;
                const powerValue = status.effective_realtime_power ?? status.stable_realtime_power ?? status.realtime_power;
                const temp = Number(status.cabinet_temp);
                const humi = Number(status.cabinet_humidity);
                const tempText = Number.isFinite(temp) || Number.isFinite(humi)
                    ? `${Number.isFinite(temp) ? temp.toFixed(1) + '°C' : '--'} / ${Number.isFinite(humi) ? humi.toFixed(0) + '%' : '--'}`
                    : '--';
                const modeText = sanitizeReadableText(status.work_mode, '模式未知');
                const updatedText = formatTimeShort(status.updated_at || status._last_success_at || status.last_success_at || status.last_checked_at);
                const configuredList = Array.isArray(cab.channels_config) ? cab.channels_config : [];
                const visibleChannels = configuredList
                    .filter(ch => ch && ch.visible !== false)
                    .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999));
                const fallbackChannels = Array.from({ length: Math.min(Number(cab.channel_count || totalChannels || channels.length || 8), 8) }, (_, idx) => ({ channel: idx + 1 }));
                const channelSource = (visibleChannels.length ? visibleChannels : fallbackChannels).slice(0, 8);
                const channelHtml = channelSource.map(ch => {
                    const chNum = Number(ch.channel);
                    const state = getPowerChannelStatus(cabId, chNum);
                    const pending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]);
                    const unknown = state === null || state === undefined;
                    const isOn = state === true || state === 1 || state === '1';
                    const cls = pending ? 'pending' : (unknown ? 'unknown' : (isOn ? 'on' : 'off'));
                    const stateText = pending ? '执行中' : (unknown ? '--' : (isOn ? '开' : '关'));
                    const disabled = unknown ? 'disabled title="状态未知，暂不可操作"' : '';
                    return `<button type="button" class="home-power-channel ${cls}${getPermissionDisabledClass('power.control')}" ${disabled || getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                        <span class="led"></span>${renderPowerChannelLabelHtml(cab, chNum, { compact: true })}<span class="state">${escapeHtml(stateText)}</span>
                    </button>`;
                }).join('');
                return `<div class="home-status-row home-power-row ${online ? '' : 'offline'}">
                    <div class="home-row-main">
                        <div class="home-row-title-line home-power-title-line"><strong class="home-row-name">${escapeHtml(getCabinetDisplayName(cab, cabId))}</strong><span class="home-mini-pill ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span></div>
                        <span>${escapeHtml(modeText)} · ${onCount}/${totalChannels || '--'} 路 · ${escapeHtml(tempText)}</span>
                    </div>
                    <div class="home-row-side home-power-side ${online ? 'ok' : 'bad'}">${formatHomeNumber(powerValue, 2, ' kW')}<br>${formatHomeNumber(status.daily_energy, 1, ' kWh')}</div>
                    ${channelHtml ? `<div class="home-power-channel-strip">${channelHtml}</div>` : ''}
                </div>`;
            }).join('');
        }
        function getMeterModeText(mode) {
            return SmartCenter.powerMeter.getMeterModeText.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderMeterTypeChips(typeCounts) {
            return SmartCenter.powerMeter.renderMeterTypeChips.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function meterValueOrDash(value, digits = 1, unit = '', zeroAsDash = false) {
            return SmartCenter.powerMeter.meterValueOrDash.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function normalizeMeterCardOrder(meters) {
            return SmartCenter.powerMeter.normalizeMeterCardOrder.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderMeterCard(meter) {
            return SmartCenter.powerMeter.renderMeterCard.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function formatReferenceMeta(metric, unit = '') {
            return SmartCenter.powerMeter.formatReferenceMeta.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function formatPowerSummaryMeta(summary) {
            return SmartCenter.powerMeter.formatPowerSummaryMeta.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderMeterTrendSelectors(payload) {
            return SmartCenter.powerMeter.renderMeterTrendSelectors.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function resolveMeterSourceMeta(payload) {
            return SmartCenter.powerMeter.resolveMeterSourceMeta.apply(SmartCenter.powerMeter, Array.from(arguments));
        }
        function renderMeterTrendChart(rows) {
            const dom = document.getElementById('meterTrendChart');
            if (!dom) return;
            if (!isChartElementRenderable(dom)) return;
            if (typeof echarts === 'undefined') {
                ensureEChartsRuntime('电表趋势图').then(() => renderMeterTrendChart(rows)).catch(() => {});
                return;
            }
            if (!myCharts.meterTrend) {
                myCharts.meterTrend = echarts.init(dom);
            }
            const safeRows = Array.isArray(rows) ? rows : [];
            const rowMap = new Map(safeRows.map(item => [String(item.period || item.date || ''), item]));
            let chartRows = safeRows;
            if (meterTrendPeriod === 'day') {
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
            const axisKey = `${meterTrendTarget}:${meterTrendPeriod}`;
            const nextYMax = Math.max(10, Math.ceil(maxValue * 1.18 / 50) * 50);
            if (axisKey !== meterTrendAxisKey) {
                meterTrendAxisKey = axisKey;
                meterTrendYAxisMax = nextYMax;
            } else {
                meterTrendYAxisMax = Math.max(meterTrendYAxisMax || 0, nextYMax);
            }
            const yMax = meterTrendYAxisMax;
            const todayKey = (() => {
                const d = new Date();
                return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
            })();
            const todayIndex = chartRows.findIndex(item => item && (item.is_today || String(item.period || item.date || '') === todayKey));
            const barData = values.map((value, index) => ({
                value,
                itemStyle: {
                    color: index === todayIndex ? '#f59e0b' : '#3b82f6',
                    borderRadius: [5, 5, 0, 0]
                },
                label: { color: index === todayIndex ? '#fde68a' : '#bfdbfe' }
            }));
            const optionSignature = JSON.stringify({ dates, values, todayIndex, yMax, target: meterTrendTarget, period: meterTrendPeriod });
            if (optionSignature === meterTrendOptionSignature) {
                myCharts.meterTrend.resize();
                return;
            }
            meterTrendOptionSignature = optionSignature;
            myCharts.meterTrend.setOption({
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
            myCharts.meterTrend.resize();
        }
        function renderDashboardEnergyTrend(rows, summary = {}) {
            const dom = document.getElementById('dashboardEnergyTrendChart');
            if (!dom) return;
            const safeRows = Array.isArray(rows) ? rows : [];
            const values = safeRows.map(item => Number(item.consume || 0));
            const total = Number(summary.total_daily_energy ?? (meterCenterCache.dashboard_summary || {}).daily_energy ?? 0);
            const last = values.length ? values[values.length - 1] : total;
            const prev = values.length > 1 ? values[values.length - 2] : 0;
            const compare = prev > 0 ? `${(((last - prev) / prev) * 100).toFixed(1)}%` : '--%';
            setTextIfExists('dashboard-energy-total', `${total.toFixed(1)} kWh`);
            setTextIfExists('dashboard-energy-compare', compare);
            if (!isChartElementRenderable(dom)) return;
            if (typeof echarts === 'undefined') {
                ensureEChartsRuntime('首页能耗趋势图').then(() => renderDashboardEnergyTrend(rows, summary)).catch(() => {});
                return;
            }
            const labels = safeRows.map(item => String(item.period || item.date || '').slice(-5)).filter(Boolean);
            if (!myCharts.dashboardEnergyTrend) {
                myCharts.dashboardEnergyTrend = echarts.init(dom);
            }
            myCharts.dashboardEnergyTrend.setOption({
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'axis',
                    formatter: params => {
                        const item = Array.isArray(params) ? params[0] : null;
                        if (!item) return '';
                        return `${escapeHtml(String(item.axisValue || '--'))}<br/>${Number(item.data || 0).toFixed(2)} kWh`;
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
            myCharts.dashboardEnergyTrend.resize();
        }
        function changeMeterTrendTarget(target) {
            meterTrendTarget = target || 'total';
            updateMeterCenter();
        }
        function changeMeterTrendPeriod(period) {
            meterTrendPeriod = period || 'day';
            updateMeterCenter();
        }
        function formatSnmpMetricValue(metric) {
            return SmartCenter.snmp.formatSnmpMetricValue(metric);
        }
        function formatSnmpSummaryValue(value, suffix = '') {
            return SmartCenter.snmp.formatSnmpSummaryValue(value, suffix);
        }
        function snmpProvidedText(value, fallback = '设备未提供') {
            return SmartCenter.snmp.snmpProvidedText(value, fallback);
        }
        function compactSnmpText(value, maxLen = 88) {
            return SmartCenter.snmp.compactSnmpText(value, maxLen);
        }
        function getSnmpInterfaceKindText(kind) {
            return SmartCenter.snmp.getSnmpInterfaceKindText(kind);
        }
        function hasSnmpUsableRate(row) {
            return SmartCenter.snmp.hasSnmpUsableRate(row);
        }
        function getSnmpUsefulTrafficRows(summary, interfaceSummary, options = {}) {
            return SmartCenter.snmp.getSnmpUsefulTrafficRows(summary, interfaceSummary, options);
        }
        function getSnmpInterfaceCountText(interfaceSummary, status = {}) {
            return SmartCenter.snmp.getSnmpInterfaceCountText(interfaceSummary, status);
        }
        function getSnmpInterfaceRoleText(interfaceSummary) {
            return SmartCenter.snmp.getSnmpInterfaceRoleText(interfaceSummary);
        }
        function getSnmpBestThroughputText(interfaceSummary) {
            return SmartCenter.snmp.getSnmpBestThroughputText(interfaceSummary);
        }
        function getSnmpBestThroughputDisplay(interfaceSummary) {
            return SmartCenter.snmp.getSnmpBestThroughputDisplay(interfaceSummary);
        }
        function getSnmpBestThroughputPair(interfaceSummary) {
            return SmartCenter.snmp.getSnmpBestThroughputPair(interfaceSummary);
        }
        function getSnmpCapacityDisplay(summary) {
            return SmartCenter.snmp.getSnmpCapacityDisplay.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpPrimaryStorageDisplay(summary) {
            return SmartCenter.snmp.getSnmpPrimaryStorageDisplay.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpDeviceTypeLabel(deviceType) {
            return SmartCenter.snmp.getSnmpDeviceTypeLabel(deviceType);
        }
        function normalizeSnmpDeviceName(cfg, status) {
            return SmartCenter.snmp.normalizeSnmpDeviceName(cfg, status);
        }
        function getSnmpFilterMeta(filterKey) {
            return SmartCenter.snmp.getSnmpFilterMeta(filterKey);
        }
        function getSnmpSummaryCards(summaries) {
            return SmartCenter.snmp.getSnmpSummaryCards(summaries);
        }
        function filterSnmpConfigs(configs, cache, filterKey) {
            return SmartCenter.snmp.filterSnmpConfigs(configs, cache, filterKey);
        }
        function renderSnmpOverviewBar(configs, cache, filterKey = 'all', viewMode = 'page') {
            return SmartCenter.snmp.renderSnmpOverviewBar.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpMetricLabel(metricName) {
            return SmartCenter.snmp.getSnmpMetricLabel(metricName);
        }
        function getSnmpMetricValue(customMetrics, metricName) {
            return SmartCenter.snmp.getSnmpMetricValue(customMetrics, metricName);
        }
        function getSnmpMetricValueWithFallback(customMetrics, metricNames = [], summary = null) {
            return SmartCenter.snmp.getSnmpMetricValueWithFallback(customMetrics, metricNames, summary);
        }
        function normalizeSnmpSwitchPortRow(row) {
            return SmartCenter.snmp.normalizeSnmpSwitchPortRow(row);
        }
        function getSnmpSwitchPortRows(summary, interfaceSummary) {
            return SmartCenter.snmp.getSnmpSwitchPortRows(summary, interfaceSummary);
        }
        function getSnmpSwitchPortState(row) {
            return SmartCenter.snmp.getSnmpSwitchPortState(row);
        }
        function getSnmpSwitchDerivedStats(summary, interfaceSummary) {
            return SmartCenter.snmp.getSnmpSwitchDerivedStats(summary, interfaceSummary);
        }
        function buildSnmpSwitchVlanPortHighlights(summary, interfaceSummary, maxCount = 4) {
            return SmartCenter.snmp.buildSnmpSwitchVlanPortHighlights(summary, interfaceSummary, maxCount);
        }
        function renderSnmpMetricChips(customMetrics, summary) {
            return SmartCenter.snmp.renderSnmpMetricChips.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpInlineMetrics(items, emptyText = '当前无可展示指标') {
            return SmartCenter.snmp.renderSnmpInlineMetrics.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpMiniList(items, options = {}) {
            return SmartCenter.snmp.renderSnmpMiniList.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpFocusPanel(title, note, bodyHtml, options = {}) {
            return SmartCenter.snmp.renderSnmpFocusPanel.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpInlineDetails(title, meta, bodyHtml, open = false) {
            return SmartCenter.snmp.renderSnmpInlineDetails.apply(SmartCenter.snmp, arguments);
        }
        function buildSnmpDetailStateKey(deviceId, sectionKey) {
            return SmartCenter.snmp.buildSnmpDetailStateKey.apply(SmartCenter.snmp, arguments);
        }
        function renderPersistedSnmpDetails(deviceId, sectionKey, title, meta, bodyHtml, open = false, className = 'snmp-inline-details') {
            return SmartCenter.snmp.renderPersistedSnmpDetails.apply(SmartCenter.snmp, arguments);
        }
        function bindSnmpDetailToggles(scopeEl) {
            return SmartCenter.snmp.bindSnmpDetailToggles.apply(SmartCenter.snmp, arguments);
        }
        function syncSnmpSelectedDeviceToUrl(deviceId = '') {
            try {
                const url = new URL(window.location.href);
                const safeDeviceId = String(deviceId || '').trim();
                if (safeDeviceId) {
                    url.searchParams.set('snmp_device', safeDeviceId);
                } else {
                    url.searchParams.delete('snmp_device');
                }
                window.history.replaceState(null, '', url.toString());
            } catch (_) {}
        }
        function restoreSnmpSelectedDeviceFromUrl() {
            try {
                const params = new URLSearchParams(window.location.search || '');
                snmpSelectedDeviceId = String(params.get('snmp_device') || params.get('device') || '').trim();
            } catch (_) {
                snmpSelectedDeviceId = '';
            }
        }
        function openSnmpDeviceDetail(deviceId) {
            const safeDeviceId = String(deviceId || '').trim();
            if (!safeDeviceId) return;
            snmpSelectedDeviceId = safeDeviceId;
            syncSnmpSelectedDeviceToUrl(safeDeviceId);
            ensureViewReady('snmp').then(() => renderSnmpCards({ mode: 'full', renderDetailPage: true })).catch(() => {});
        }
        function closeSnmpDeviceDetail() {
            snmpSelectedDeviceId = '';
            syncSnmpSelectedDeviceToUrl('');
            ensureViewReady('snmp').then(() => renderSnmpCards({ mode: 'full', renderDetailPage: true })).catch(() => {});
        }
        function bindSnmpOverviewCardActions(scopeEl) {
            const root = scopeEl || document;
            root.querySelectorAll('[data-snmp-device-card]').forEach(card => {
                if (card.dataset.snmpOpenBound === '1') return;
                card.dataset.snmpOpenBound = '1';
                const open = () => openSnmpDeviceDetail(card.getAttribute('data-snmp-device-id'));
                card.addEventListener('click', event => {
                    if (event.target && event.target.closest && event.target.closest('button[data-snmp-filter]')) return;
                    open();
                });
                card.addEventListener('keydown', event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        open();
                    }
                });
            });
            root.querySelectorAll('[data-snmp-back-overview]').forEach(btn => {
                if (btn.dataset.snmpBackBound === '1') return;
                btn.dataset.snmpBackBound = '1';
                btn.addEventListener('click', closeSnmpDeviceDetail);
            });
        }
        function summarizeSnmpPayload(payload) {
            const configs = getNetworkMonitorConfigs();
            return configs.map(cfg => {
                const status = (payload || {})[cfg.id] || {};
                const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
                const summary = status.summary || {};
                const interfaceSummary = summary.interface_summary || {};
                return [
                    cfg.id,
                    statusMeta.level,
                    statusMeta.isOnlineLike ? 1 : 0,
                    status.updated_at || '',
                    status.error || '',
                    summary.risk_level || '',
                    summary.health_score ?? '',
                    (summary.alert_counts || {}).warning ?? 0,
                    (summary.alert_counts || {}).critical ?? 0,
                    interfaceSummary.physical_up_count ?? '',
                    interfaceSummary.physical_down_count ?? '',
                    interfaceSummary.aggregate_total_rate_text || '',
                    summary.cpu_avg_percent ?? '',
                    summary.memory_usage_percent ?? '',
                    summary.channel_online ?? '',
                    summary.channel_total ?? '',
                    summary.hdd_error_count ?? ''
                ].join('|');
            }).join('~');
        }
        function getNetworkMonitorConfigs() {
            return [
                ...(Array.isArray(snmpConfigs) ? snmpConfigs : []).map(cfg => Object.assign({ monitor_kind: 'snmp' }, cfg)),
                ...(Array.isArray(nvrConfigs) ? nvrConfigs : []).map(cfg => Object.assign({ monitor_kind: 'nvr', device_type: 'nvr' }, cfg))
            ].filter(cfg => cfg && cfg.visible !== false);
        }
        function getNetworkStatusCache() {
            return Object.assign({}, snmpStatusCache || {}, nvrStatusCache || {});
        }
        function getNvrPreviewChannels(deviceId = '') {
            const cfg = nvrConfigs.find(item => String(item.id) === String(deviceId)) || nvrConfigs.find(item => item && item.visible !== false) || null;
            if (!cfg) return { cfg: null, status: {}, channels: [] };
            const status = nvrStatusCache[cfg.id] || {};
            const channels = Array.isArray(status.channels)
                ? status.channels.slice().sort((a, b) => Number(a?.id || 9999) - Number(b?.id || 9999))
                : [];
            return { cfg, status, channels };
        }
        function applyNvrPreviewUrlParams() {
            const params = new URLSearchParams(window.location.search || '');
            const mode = params.get('nvr_mode') || params.get('preview_mode') || '';
            const grid = params.get('nvr_grid') || params.get('preview_grid') || '';
            const page = params.get('nvr_page') || params.get('preview_page') || '';
            if (mode) nvrPreviewMode = getNvrPreviewMode(mode);
            if (grid) nvrPreviewGrid = getNvrPreviewGrid(grid);
            if (nvrPreviewMode === 'stream4') nvrPreviewGrid = 4;
            if (nvrPreviewMode === 'stream8') nvrPreviewGrid = 8;
            if (nvrPreviewMode === 'stream') nvrPreviewGrid = 1;
            if (page !== '') nvrPreviewPage = Math.max(0, Number(page) || 0);
        }
        function selectNvrPreview(deviceId, channelId, options = {}) {
            nvrSelectedDeviceId = String(deviceId || '').trim();
            nvrSelectedChannelId = String(channelId || '').trim();
            if (options.mode) nvrPreviewMode = getNvrPreviewMode(options.mode);
            if (options.grid) nvrPreviewGrid = getNvrPreviewGrid(options.grid);
            if (options.page !== undefined) nvrPreviewPage = Math.max(0, Number(options.page) || 0);
            if (options.live) {
                nvrPreviewGrid = 1;
                nvrPreviewMode = 'stream';
                nvrPreviewPage = 0;
            }
            renderNvrPreviewPanel({ refresh: !!options.refresh });
        }
        function setNvrPreviewMode(mode) {
            nvrPreviewMode = getNvrPreviewMode(mode);
            if (nvrPreviewMode === 'stream') nvrPreviewGrid = 1;
            if (nvrPreviewMode === 'stream4') nvrPreviewGrid = 4;
            if (nvrPreviewMode === 'stream8') nvrPreviewGrid = 8;
            nvrPreviewPage = 0;
            renderNvrPreviewPanel({ refresh: true });
        }
        function setNvrPreviewGrid(grid) {
            nvrPreviewGrid = getNvrPreviewGrid(grid);
            if (nvrPreviewGrid > 1 && nvrPreviewMode === 'stream') nvrPreviewMode = nvrPreviewGrid > 4 ? 'stream8' : 'stream4';
            if (nvrPreviewMode === 'stream4' && nvrPreviewGrid !== 4) nvrPreviewMode = 'smart';
            if (nvrPreviewMode === 'stream8' && nvrPreviewGrid !== 8) nvrPreviewMode = 'smart';
            nvrPreviewPage = 0;
            renderNvrPreviewPanel({ refresh: true });
        }
        function setNvrPreviewPage(delta) {
            nvrPreviewPage = Math.max(0, Number(nvrPreviewPage || 0) + Number(delta || 0));
            renderNvrPreviewPanel({ refresh: true });
        }
        function activateNvrWallFrame(frame) {
            if (!frame || !frame.isConnected || frame.dataset.loaded === '1') return;
            const src = frame.dataset.src;
            if (!src) return;
            frame.dataset.loaded = '1';
            const cell = frame.closest('.nvr-wall-cell');
            if (cell) cell.classList.add('loading');
            frame.src = src;
        }
        function scheduleNvrWallFrames() {
            while (nvrWallFrameTimers.length) window.clearTimeout(nvrWallFrameTimers.pop());
            const frames = Array.from(document.querySelectorAll('#nvr-preview-panel iframe[data-nvr-lazy="1"]'));
            frames.forEach((frame, index) => {
                const timer = window.setTimeout(() => activateNvrWallFrame(frame), index * NVR_STREAM_STAGGER_MS);
                nvrWallFrameTimers.push(timer);
            });
        }
        function stopNvrWallSnapshotRefresh() {
            if (nvrWallSnapshotRefreshTimer) {
                window.clearTimeout(nvrWallSnapshotRefreshTimer);
                nvrWallSnapshotRefreshTimer = null;
            }
        }
        function scheduleNvrWallSnapshotRefresh() {
            stopNvrWallSnapshotRefresh();
            if (getActiveViewId() !== 'camera_preview') return;
            if (document.hidden || getNvrPreviewGrid(nvrPreviewGrid) <= 1) return;
            const mode = getNvrPreviewMode(nvrPreviewMode);
            if (!['smart', 'snapshot'].includes(mode)) return;
            nvrWallSnapshotRefreshTimer = window.setTimeout(() => {
                renderNvrPreviewPanel({ refresh: true, autoRefresh: true });
            }, NVR_WALL_SNAPSHOT_REFRESH_MS);
        }
        function stopNvrPreviewStreams() {
            while (nvrWallFrameTimers.length) window.clearTimeout(nvrWallFrameTimers.pop());
            stopNvrWallSnapshotRefresh();
            const panel = document.getElementById('nvr-preview-panel');
            if (!panel) return;
            panel.querySelectorAll('iframe').forEach(frame => {
                try { frame.src = 'about:blank'; } catch (err) {}
                try { frame.removeAttribute('src'); } catch (err) {}
            });
            panel.querySelectorAll('.nvr-wall-cell.loading, .nvr-preview-frame.loading').forEach(el => el.classList.remove('loading'));
        }
        function renderNvrPreviewPanel(options = {}) {
            const panel = document.getElementById('nvr-preview-panel');
            if (!panel) return;
            stopNvrPreviewStreams();
            const visibleNvrConfigs = (Array.isArray(nvrConfigs) ? nvrConfigs : []).filter(cfg => cfg && cfg.visible !== false);
            if (!visibleNvrConfigs.length) {
                panel.innerHTML = '<div class="nvr-preview-empty">未配置录像机设备。</div>';
                return;
            }
            const selectedExists = visibleNvrConfigs.some(cfg => String(cfg.id) === String(nvrSelectedDeviceId));
            if (!nvrSelectedDeviceId || !selectedExists) {
                nvrSelectedDeviceId = String(visibleNvrConfigs[0].id || '');
            }
            let { cfg, status, channels } = getNvrPreviewChannels(nvrSelectedDeviceId);
            if (!cfg) {
                panel.innerHTML = '<div class="nvr-preview-empty">未找到可预览的录像机。</div>';
                return;
            }
            if (!channels.length) {
                const expected = Number(cfg.expected_channel_count || 0);
                channels = Array.from({ length: expected || 32 }, (_, index) => ({
                    id: String(index + 1),
                    name: `D${index + 1}`,
                    online: false
                }));
            }
            const channelExists = channels.some(item => String(item.id) === String(nvrSelectedChannelId));
            if (!nvrSelectedChannelId || !channelExists) {
                const firstOnline = channels.find(item => item && item.online);
                nvrSelectedChannelId = String((firstOnline || channels[0] || {}).id || '');
            }
            const selected = channels.find(item => String(item.id) === String(nvrSelectedChannelId)) || channels[0] || {};
            const preview = buildNvrPreviewPanelHtml({
                cfg,
                status,
                channels,
                selected,
                selectedChannelId: nvrSelectedChannelId,
                previewMode: nvrPreviewMode,
                previewGrid: nvrPreviewGrid,
                previewPage: nvrPreviewPage,
                streamLimit: NVR_STREAM_CONCURRENCY_LIMIT,
                snapshotRefreshMs: NVR_WALL_SNAPSHOT_REFRESH_MS,
                options,
            });
            nvrPreviewPage = preview.currentPage;
            panel.innerHTML = preview.html;
            scheduleNvrWallFrames();
            scheduleNvrWallSnapshotRefresh();
        }
        function normalizeNvrStatusForSnmp(cfg, status) {
            const source = status && typeof status === 'object' ? status : {};
            if (SmartCenter.snmp && typeof SmartCenter.snmp.normalizeNvrStatusForSnmp === 'function') {
                return SmartCenter.snmp.normalizeNvrStatusForSnmp.apply(SmartCenter.snmp, arguments);
            }
            const channels = Array.isArray(source.channels) ? source.channels : [];
            const onlineChannels = channels.filter(item => item && item.online !== false).length;
            const expectedCount = Number(cfg?.expected_channel_count || cfg?.channel_count || channels.length || 0);
            const online = source.online !== undefined ? !!source.online : !source.error;
            return Object.assign({}, source, {
                id: source.id || cfg?.id,
                host: source.host || cfg?.host,
                online,
                summary: Object.assign({
                    device_type: 'nvr',
                    risk_level: online ? 'normal' : 'warning',
                    health_score: online ? 92 : 0,
                    channel_online: onlineChannels,
                    channel_total: expectedCount || channels.length,
                    alert_counts: {
                        critical: online ? 0 : 1,
                        warning: online && expectedCount && onlineChannels < expectedCount ? 1 : 0,
                        info: 0,
                    },
                }, source.summary || {}),
            });
        }
        function getSnmpStorageRows(summary) {
            return SmartCenter.snmp.getSnmpStorageRows.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpStorageDisplayRows(summary, limit = 8) {
            return SmartCenter.snmp.getSnmpStorageDisplayRows.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpPrimaryStorageRow(summary) {
            return SmartCenter.snmp.getSnmpPrimaryStorageRow.apply(SmartCenter.snmp, arguments);
        }
        function summarizeSnmpStorageCapacity(summary) {
            return SmartCenter.snmp.summarizeSnmpStorageCapacity.apply(SmartCenter.snmp, arguments);
        }
        function formatSnmpBytesText(bytes) {
            return SmartCenter.snmp.formatSnmpBytesText.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpDiskSummary(summary) {
            return SmartCenter.snmp.getSnmpDiskSummary.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpProtocolProfile(cfg, status, summary) {
            return SmartCenter.snmp.getSnmpProtocolProfile.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpHealthPill(summary) {
            return SmartCenter.snmp.renderSnmpHealthPill.apply(SmartCenter.snmp, arguments);
        }
        function buildSnmpDeviceFactItems(deviceType, summary, status) {
            return SmartCenter.snmp.buildSnmpDeviceFactItems.apply(SmartCenter.snmp, arguments);
        }
        function buildSnmpPrimaryMetricItems(deviceType, summary, status, customMetrics = []) {
            return SmartCenter.snmp.buildSnmpPrimaryMetricItems.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpDevicePrimaryPanels(deviceId, deviceType, summary, status, customMetrics = []) {
            return SmartCenter.snmp.renderSnmpDevicePrimaryPanels.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpAdvancedDetails(deviceId, deviceType, summary, status, customMetrics = []) {
            return SmartCenter.snmp.renderSnmpAdvancedDetails.apply(SmartCenter.snmp, arguments);
        }
        function buildSnmpMetricRows(customMetrics, excludeNames = [], maxCount = 8) {
            return SmartCenter.snmp.buildSnmpMetricRows.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpInterfaceChips(interfaceSummary, deviceType) {
            return SmartCenter.snmp.renderSnmpInterfaceChips.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpPortPreview(interfaceSummary, deviceType) {
            return SmartCenter.snmp.renderSnmpPortPreview.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpAlertLevel(level) {
            return SmartCenter.snmp.getSnmpAlertLevel.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpFlowList(rows, emptyText = '当前无流量数据') {
            return SmartCenter.snmp.renderSnmpFlowList.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpStorageList(rows) {
            return SmartCenter.snmp.renderSnmpStorageList.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpCapacityHero(summary, options = {}) {
            return SmartCenter.snmp.renderSnmpCapacityHero.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpDiskHealthList(rows) {
            return SmartCenter.snmp.renderSnmpDiskHealthList.apply(SmartCenter.snmp, arguments);
        }
        function renderQnapDriveBayPanel(summary) {
            return SmartCenter.snmp.renderQnapDriveBayPanel.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpFanList(rows) {
            return SmartCenter.snmp.renderSnmpFanList.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpDiskIoList(rows) {
            return SmartCenter.snmp.renderSnmpDiskIoList.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpHighlightPanel(title, note, chips, level = '') {
            return SmartCenter.snmp.renderSnmpHighlightPanel.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpSpotlightCards(items) {
            return SmartCenter.snmp.renderSnmpSpotlightCards.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpSwitchSegments(summary, portRows) {
            return SmartCenter.snmp.renderSnmpSwitchSegments.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpVendorCards(items) {
            return SmartCenter.snmp.renderSnmpVendorCards.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpPortPanelSortValue(row, mode) {
            return SmartCenter.snmp.getSnmpPortPanelSortValue.apply(SmartCenter.snmp, arguments);
        }
        function sortSnmpPortRows(rows, mode = 'index') {
            return SmartCenter.snmp.sortSnmpPortRows.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpSwitchPortPanels(deviceId, portRows) {
            return SmartCenter.snmp.renderSnmpSwitchPortPanels.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpHealthBanner(summary) {
            return SmartCenter.snmp.renderSnmpHealthBanner.apply(SmartCenter.snmp, arguments);
        }
        function getSnmpDeviceIcon(deviceType) {
            return SmartCenter.snmp.getSnmpDeviceIcon.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpSwitchSection(summary) {
            return SmartCenter.snmp.renderSnmpSwitchSection.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpKpiCards(deviceType, summary, status) {
            return SmartCenter.snmp.renderSnmpKpiCards.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpNasSection(summary, customMetrics = []) {
            return SmartCenter.snmp.renderSnmpNasSection.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpRouterSection(summary, customMetrics = []) {
            return SmartCenter.snmp.renderSnmpRouterSection.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpRoleSection(deviceType, summary, status) {
            return SmartCenter.snmp.renderSnmpRoleSection.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpCompactCard(cfg, status, summary, deviceType, interfaceSummary, options = {}) {
            return SmartCenter.snmp.renderSnmpCompactCard.apply(SmartCenter.snmp, arguments);
        }
        function buildDashboardSnmpMetricItems(deviceType, summary, status, interfaceSummary, customMetrics = []) {
            return SmartCenter.snmp.buildDashboardSnmpMetricItems.apply(SmartCenter.snmp, arguments);
        }
        function renderDashboardSnmpCard(cfg, status) {
            return SmartCenter.snmp.renderDashboardSnmpCard.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpCard(cfg, status) {
            return SmartCenter.snmp.renderSnmpCard.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpDeviceDetailPage(cfg, status) {
            return SmartCenter.snmp.renderSnmpDeviceDetailPage.apply(SmartCenter.snmp, arguments);
        }
        function renderSnmpCards(options = {}) {
            const renderMode = String(options.mode || snmpStatusMode || '').trim().toLowerCase();
            const renderDetailPage = options.renderDetailPage !== undefined
                ? !!options.renderDetailPage
                : renderMode === 'full';
            if (renderDetailPage && !(SmartCenter.snmp && typeof SmartCenter.snmp.renderSnmpCompactCard === 'function')) {
                ensureViewReady('snmp').then(() => renderSnmpCards(options)).catch(() => {});
                return;
            }
            const dashboardGrid = document.getElementById('dashboard-snmp-grid');
            const pageGrid = document.getElementById('snmp-page-grid');
            const statusCache = getNetworkStatusCache();
            const visibleConfigs = getNetworkMonitorConfigs();
            visibleConfigs.sort((a, b) => {
                const sa = (statusCache[a.id] || {}).summary || {};
                const sb = (statusCache[b.id] || {}).summary || {};
                const riskRank = value => {
                    const normalized = String(value || '').trim().toLowerCase();
                    if (normalized === 'critical') return 0;
                    if (normalized === 'warning') return 1;
                    return 2;
                };
                const rankDiff = riskRank(sa.risk_level) - riskRank(sb.risk_level);
                if (rankDiff !== 0) return rankDiff;
                const scoreA = Number(sa.health_score ?? 100);
                const scoreB = Number(sb.health_score ?? 100);
                if (scoreA !== scoreB) return scoreA - scoreB;
                return normalizeSnmpDeviceName(a, statusCache[a.id] || {}).localeCompare(normalizeSnmpDeviceName(b, statusCache[b.id] || {}), 'zh-CN');
            });
            const filteredConfigs = filterSnmpConfigs(visibleConfigs, statusCache, snmpCardFilter);
            const filterMeta = getSnmpFilterMeta(snmpCardFilter);
            const onlineCount = visibleConfigs.filter(cfg => getDeviceStatusMeta(statusCache[cfg.id] || {}).isOnlineLike).length;
            const criticalCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'critical').length;
            const warningCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'warning').length;
            const dashboardCardsHtml = filteredConfigs.length
                ? `<div class="snmp-dashboard-grid">${filteredConfigs.map(cfg => renderDashboardSnmpCard(cfg, statusCache[cfg.id] || {})).join('')}</div>`
                : `<div class="snmp-filter-empty"><strong>${escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片。</div>`;
            const dashboardHtml = visibleConfigs.length
                ? `${dashboardCardsHtml}`
                : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid && renderDetailPage) {
                const pageOverviewHtml = renderSnmpOverviewBar(visibleConfigs, statusCache, snmpCardFilter);
                const selectedConfig = snmpSelectedDeviceId
                    ? visibleConfigs.find(cfg => String(cfg.id || '') === snmpSelectedDeviceId)
                    : null;
                if (snmpSelectedDeviceId && !selectedConfig) {
                    snmpSelectedDeviceId = '';
                    syncSnmpSelectedDeviceToUrl('');
                }
                const pageCardsHtml = selectedConfig
                    ? renderSnmpDeviceDetailPage(selectedConfig, statusCache[selectedConfig.id] || {})
                    : (filteredConfigs.length
                        ? `<div class="snmp-device-grid snmp-onepage-grid">${filteredConfigs.map(cfg => {
                            const status = statusCache[cfg.id] || {};
                            const summary = status.summary || {};
                            const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
                            return renderSnmpCompactCard(cfg, status, summary, deviceType, summary.interface_summary || {}, { interactive: true });
                        }).join('')}</div>`
                        : `<div class="snmp-filter-empty"><strong>${escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片，可切换上方统计卡查看其他设备。</div>`);
                const pageHtml = visibleConfigs.length
                    ? `${pageOverviewHtml}${pageCardsHtml}`
                    : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
                pageGrid.innerHTML = pageHtml;
            }
            const dashSnmpOnline = document.getElementById('dash-snmp-online');
            const dashSnmpTotal = document.getElementById('dash-snmp-total');
            const dashSnmpCritical = document.getElementById('dash-snmp-critical');
            const dashSnmpWarning = document.getElementById('dash-snmp-warning');
            const dashSnmpAlert = document.getElementById('dash-snmp-alert');
            if (dashSnmpOnline) dashSnmpOnline.innerText = String(onlineCount);
            if (dashSnmpTotal) dashSnmpTotal.innerText = String(visibleConfigs.length);
            if (dashSnmpCritical) dashSnmpCritical.innerText = String(criticalCount);
            if (dashSnmpWarning) dashSnmpWarning.innerText = String(warningCount);
            if (dashSnmpAlert) dashSnmpAlert.innerText = String(criticalCount + warningCount);
            [dashboardGrid, renderDetailPage ? pageGrid : null].filter(Boolean).forEach(grid => {
	            grid.querySelectorAll('[data-snmp-filter]').forEach(btn => {
	                btn.addEventListener('click', () => {
	                    const nextFilter = String(btn.getAttribute('data-snmp-filter') || 'all').trim().toLowerCase() || 'all';
	                    snmpCardFilter = nextFilter === snmpCardFilter ? 'all' : nextFilter;
                        snmpSelectedDeviceId = '';
                        syncSnmpSelectedDeviceToUrl('');
	                    renderSnmpCards();
	                });
	            });
                bindSnmpDetailToggles(grid);
                bindSnmpOverviewCardActions(grid);
            });
        }
        function updateSnmpStatus(options = {}) {
            const forceFull = !!options.full || getActiveViewId() === 'snmp';
            const mode = forceFull ? 'full' : 'compact';
            if (mode === 'full' && !(SmartCenter.snmp && typeof SmartCenter.snmp.renderSnmpCompactCard === 'function')) {
                return ensureViewReady('snmp').then(() => updateSnmpStatus(options));
            }
            if (snmpFetchInFlight) {
                if (snmpFetchMode === mode || (mode === 'compact' && snmpFetchMode === 'full')) return snmpFetchInFlight;
                if (mode === 'full') return snmpFetchInFlight.then(() => updateSnmpStatus({ full: true }));
                return snmpFetchInFlight;
            }
            const snmpUrl = mode === 'full' ? '/api/snmp/status' : '/api/snmp/status?compact=1';
            const nvrUrl = mode === 'full' ? '/api/nvr/status' : '/api/nvr/status?compact=1';
            const safeRenderSnmpCards = () => guardFrontendStep('snmp.render_cards', () => renderSnmpCards({
                mode,
                renderDetailPage: mode === 'full'
            }), '网络监控卡片渲染异常，请稍后重试');
            snmpFetchMode = mode;
            snmpFetchInFlight = Promise.allSettled([
                fetchJson(snmpUrl, {}, 'SNMP 状态读取失败'),
                nvrConfigs.length ? fetchJson(nvrUrl, {}, '录像机状态读取失败') : Promise.resolve({})
            ])
                .then(results => {
                    const [snmpResult, nvrResult] = results;
                    const snmpFailed = snmpResult.status === 'rejected';
                    const nvrFailed = nvrResult.status === 'rejected';
                    if (snmpFailed && nvrFailed) {
                        throw snmpResult.reason || nvrResult.reason || new Error('网络监控状态读取失败');
                    }
                    if (snmpFailed) console.error('SNMP 状态更新失败', snmpResult.reason);
                    if (nvrFailed) console.error('录像机状态更新失败', nvrResult.reason);
                    const nextSnmpData = snmpResult.status === 'fulfilled' ? (snmpResult.value || {}) : (snmpStatusCache || {});
                    const rawNvrData = nvrResult.status === 'fulfilled' ? (nvrResult.value || {}) : (nvrStatusCache || {});
                    const nextNvrData = {};
                    (Array.isArray(nvrConfigs) ? nvrConfigs : []).forEach(cfg => {
                        if (!cfg || !cfg.id) return;
                        nextNvrData[cfg.id] = normalizeNvrStatusForSnmp(cfg, rawNvrData[cfg.id] || {});
                    });
                    snmpStatusCache = nextSnmpData;
                    nvrStatusCache = nextNvrData;
                    const mergedData = getNetworkStatusCache();
                    const nextSignature = `${mode}:${summarizeSnmpPayload(mergedData)}`;
                    const shouldRender = nextSignature !== snmpStatusSignature;
                    snmpLastSuccessAt = Date.now();
                    snmpFetchFailureCount = 0;
                    snmpStatusMode = mode;
                    if (shouldRender) {
                        snmpStatusSignature = nextSignature;
                        const now = Date.now();
                        const elapsed = now - snmpLastRenderAt;
                        if (elapsed >= 300) {
                            snmpLastRenderAt = now;
                            safeRenderSnmpCards();
                        } else {
                            setTimeout(() => {
                                snmpLastRenderAt = Date.now();
                                safeRenderSnmpCards();
                            }, 300 - elapsed);
                        }
                    }
                })
                .catch(err => {
                    console.error('网络监控状态更新失败', err);
                    snmpFetchFailureCount += 1;
                    const now = Date.now();
                    const hasCache = Object.keys(getNetworkStatusCache() || {}).length > 0;
                    const cacheStillWarm = hasCache && snmpLastSuccessAt && (now - snmpLastSuccessAt) < 45000;
                    const shouldToast = !cacheStillWarm && (
                        !hasCache
                        || snmpFetchFailureCount >= 2
                    ) && (now - snmpLastToastAt) > 15000;
                    if (shouldToast) {
                        snmpLastToastAt = now;
                        showToast(translateApiError(err?.message, '网络监控状态读取失败，请稍后重试'), true);
                    }
                })
                .finally(() => {
                    snmpFetchInFlight = null;
                    snmpFetchMode = '';
                });
            return snmpFetchInFlight;
        }
        // Runtime viewport helpers now live in static/js/core/viewport-layout.js.
        // Keep these names available for older inline callers and future modules.
        const applyAdaptiveDensity = window.applyAdaptiveDensity || (() => {});
        const applyDashboardBrowserFit = window.applyDashboardBrowserFit || (() => {});
        const updateLayoutDebugPanel = window.updateLayoutDebugPanel || (() => {});
        function syncDashboardCompactMode(viewId = getActiveViewId()) {
            document.body.classList.toggle('dashboard-compact-mode', viewId === 'dashboard');
            applyDashboardBrowserFit();
            scheduleDashboardMasonry();
        }
        function syncCurrentViewToUrl(viewId) {
            const safeView = String(viewId || '').replace(/[^a-zA-Z0-9_-]/g, '');
            if (!safeView) return;
            try {
                const url = new URL(window.location.href);
                if (url.searchParams.get('view') !== safeView) {
                    url.searchParams.set('view', safeView);
                    window.history.replaceState(null, '', url.toString());
                }
                if (window.parent && window.parent !== window) {
                    window.parent.postMessage({
                        source: 'smart-center',
                        type: 'view-change',
                        view: safeView,
                        href: url.toString()
                    }, '*');
                }
            } catch (_) {}
        }
        function toggleSidebar(forceOpen = null) {
            const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !document.body.classList.contains('sidebar-open');
            document.body.classList.toggle('sidebar-open', shouldOpen);
        }
        function closeSidebar() { document.body.classList.remove('sidebar-open'); }
        function switchTab(viewId, title, navEl) {
            const previousView = getActiveViewId();
            if (previousView === 'camera_preview' && viewId !== 'camera_preview') stopNvrPreviewStreams();
            if (viewId !== 'snmp' && snmpSelectedDeviceId) {
                snmpSelectedDeviceId = '';
                syncSnmpSelectedDeviceToUrl('');
            }
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            const targetView = document.getElementById('view-' + viewId);
            if (targetView) targetView.classList.add('active');
            document.querySelectorAll('.nav-menu li').forEach(el => el.classList.remove('active'));
            if (navEl) navEl.classList.add('active');
            document.getElementById('header-title').innerText = title;
            syncDashboardCompactMode(viewId);
            syncCurrentViewToUrl(viewId);
            if (window.innerWidth <= 760) closeSidebar();
            if (viewId !== 'door') stopDoorVideoStream();
            ensureViewReady(viewId).catch(() => {});
            if (viewId === 'power') setTimeout(() => {
                Object.entries(powerHistoryCache || {}).forEach(([cabId, rows]) => renderPowerEnergyChart(cabId, rows));
                resizePowerCharts();
                updatePowerData();
            }, 120);
            if (viewId === 'meter') setTimeout(() => { updateMeterCenter(); }, 80);
            if (viewId === 'ups') setTimeout(() => { updateUpsStatus(); }, 80);
            if (viewId === 'snmp') setTimeout(() => { ensureViewReady('snmp').then(() => updateSnmpStatus({ full: true })).catch(() => {}); }, 80);
            if (viewId === 'proxy') setTimeout(() => { ensureViewReady('proxy').then(() => updateProxyStatus()).catch(() => {}); }, 80);
            if (viewId === 'auto') setTimeout(() => { loadAutomationStatus(true); loadAutomationLogs(); }, 80);
            if (viewId === 'camera_preview') {
                setTimeout(() => {
                    applyNvrPreviewUrlParams();
                    ensureViewReady('camera_preview')
                        .then(() => updateSnmpStatus({ full: true }))
                        .finally(() => renderNvrPreviewPanel({ refresh: true }));
                }, 80);
            }
            if (viewId === 'hvac') setTimeout(() => { ensureViewReady('hvac').then(() => { updateHvacStatus(true); updateEnvData(); }).catch(() => {}); }, 80);
            if (viewId === 'door') setTimeout(() => { initCanvas(); updateDoorStatus(true).finally(() => startDoorVideoStream()); }, 100);
            if (viewId === 'sequencer') setTimeout(() => { updateSequencerStatus(); }, 80);
            if (viewId === 'universal') setTimeout(() => { ensureViewReady('universal').then(() => updateNodeRedDevices(true)).catch(() => {}); }, 80);
            if (viewId === 'apple_audio') setTimeout(() => { ensureViewReady('apple_audio').then(() => initAppleAudioDemo()).catch(() => {}); }, 60);
            if (viewId === 'local_model') setTimeout(() => { ensureViewReady('local_model').then(() => window.SmartCenter?.localModel?.init?.()).catch(() => {}); }, 60);
            if (viewId === 'projector') setTimeout(() => { ensureViewReady('projector').then(() => updateProjectorStatus()).catch(() => {}); }, 80);
            if (viewId === 'dashboard') preloadDashboardSupportModules();
            refreshPollingVisibility();
        }
        function formatGlobalTime(now = new Date()) {
            const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
            const pad = value => String(value).padStart(2, '0');
            return {
                clock: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
                date: `${now.getFullYear()}年${pad(now.getMonth() + 1)}月${pad(now.getDate())}日 ${weekdays[now.getDay()]}`
            };
        }
        function updateGlobalClock() {
            const formatted = formatGlobalTime(new Date());
            const clockEl = document.getElementById("global-time-clock");
            const dateEl = document.getElementById("global-time-date");
            const timeEl = document.getElementById("global-time");
            if (clockEl && dateEl) {
                clockEl.innerText = formatted.clock;
                dateEl.innerText = formatted.date;
            } else if (timeEl) {
                timeEl.innerText = `${formatted.date} ${formatted.clock}`;
            }
            updateDeployModalInfo();
        }
        function getSequencerOnlineClass(device) {
            return device && device.online ? 'online' : 'offline';
        }
        function renderSequencerCard(device) {
            const channels = Array.isArray(device.channels) ? device.channels : [];
            const commMode = String(device.comm_mode || 'TCP').toUpperCase();
            const connectionText = commMode === 'COM'
                ? `${device.baudrate || 19200} / ${device.data_bits || 8}${String(device.parity || 'N').slice(0,1)}${device.stop_bits || 1}`
                : `${device.ip || '--'}:${device.port || '--'}`;
            const sequencerLogs = Array.isArray(device.logs) ? device.logs.slice(0, 6) : [];
            const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
            const lastSuccessText = device.last_success_at ? new Date(device.last_success_at).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
            const currentStatusText = device.online
                ? `${device.mode || '时序模式'} / ${device.startup_mode || '手动'} / ${device.last_action || '待机'}`
                : `${device.last_action || '离线'}${device.error_display ? ' / ' + device.error_display : ''}`;
            const shortErrorText = device.error_display ? String(device.error_display).split(/[，,。]/)[0] : '';
            const channelHtml = channels.filter(ch => ch.visible !== false).map(ch => `
                <button class="sequencer-channel-btn ${ch.state ? 'on' : 'off'}${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                    <span class="sequencer-inline-led ${ch.state ? 'on' : ''}"></span>
                    <span class="name">${escapeHtml(ch.name || ('CH' + ch.channel))}</span>
                    <span class="state">${ch.state ? '已开启' : '已关闭'}</span>
                </button>
            `).join('');
            const logHtml = sequencerLogs.length ? sequencerLogs.map(log => {
                const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
                const message = escapeHtml(String(log.operation || '').replace(/\[.*?\]\s*/, '') || '未命名记录');
                return `<div class="sequencer-mini-log-item"><span class="sequencer-mini-log-time">[${timeText}]</span><span class="sequencer-mini-log-text">${message}</span></div>`;
            }).join('') : '<div style="color:var(--text-sub); font-size:12px;">暂无时序电源日志</div>';
            return `<div class="sequencer-card ${getSequencerOnlineClass(device)}">
                <div class="sequencer-head">
                    <div>
                        <div class="card-head-kicker">Sequencer Control</div>
                        <div class="sequencer-title">${escapeHtml(device.name || device.id)}</div>
                        <div class="sequencer-subtitle">地址 ${escapeHtml(String(device.address ?? 1))} / ${escapeHtml(device.protocol || 'DGH 8路时序器')} / ${escapeHtml(device.brand || 'DGH')}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="sequencer-tag ${device.online ? 'online' : ''}">${device.online ? '在线' : '离线'}</span>
                        <span class="sequencer-tag ${device.locked ? 'locked' : ''}">${device.locked ? '已锁定' : '未锁定'}</span>
                        ${(!device.online && shortErrorText) ? `<span class="sequencer-tag error">${escapeHtml(shortErrorText)}</span>` : ''}
                    </div>
                </div>
                <div class="sequencer-summary-text">通道状态摘要: ${escapeHtml(device.channel_summary || '无通道状态')}</div>
                <div class="sequencer-meta">
                    <div class="sequencer-meta-item"><div class="label">接入方式</div><div class="value">${escapeHtml(commMode)}</div></div>
                    <div class="sequencer-meta-item"><div class="label">${commMode === 'COM' ? '串口参数' : '网络地址'}</div><div class="value">${escapeHtml(String(connectionText))}</div></div>
                    <div class="sequencer-meta-item"><div class="label">当前状态</div><div class="value">${escapeHtml(currentStatusText)}</div></div>
                    <div class="sequencer-meta-item log"><div class="label">最近操作</div><div class="sequencer-mini-log-list">${logHtml}</div></div>
                </div>
                <div class="sequencer-toolbar">
                    <button class="sequencer-action-btn seq-on${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_on')">顺序开启</button>
                    <button class="sequencer-action-btn seq-off${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_off')">顺序关闭</button>
                    <button class="sequencer-action-btn all-on${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_on')">全部开启</button>
                    <button class="sequencer-action-btn all-off${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_off')">全部关闭</button>
                    <button class="sequencer-action-btn lock${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_lock')">${device.locked ? '解除锁定' : '锁定设备'}</button>
                </div>
                <div class="sequencer-channel-grid">${channelHtml || '<div style="grid-column:1/-1;color:var(--text-sub);">未配置通道</div>'}</div>
                <div class="sequencer-diagnostics">
                    <div class="sequencer-diag-item">
                        <div class="label">最后轮询</div>
                        <div class="value">${escapeHtml(updatedAtText)}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后成功通讯</div>
                        <div class="value">${escapeHtml(lastSuccessText)}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后指令</div>
                        <div class="value">${escapeHtml(device.last_command_hex || '--')}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后回包</div>
                        <div class="value">${escapeHtml(device.last_response_hex || '--')}</div>
                    </div>
                </div>
                ${device.error ? `<div class="card-inline-note error">通讯异常：${escapeHtml(device.error)}</div>` : ''}
            </div>`;
        }
        function renderCompactSequencerCard(device) {
            const visibleChannels = Array.isArray(device?.channels) ? device.channels.filter(ch => ch && ch.visible !== false).slice(0, 8) : [];
            const canControlChannels = hasPermission('sequencer.control');
            const channelHtml = visibleChannels.map(ch => {
                const title = canControlChannels
                    ? `${ch.name || ('CH' + ch.channel)} · 点击切换`
                    : '当前账号无时序电源控制权限';
                return `
                <button type="button" class="dashboard-sequencer-channel ${ch.state ? 'on' : 'off'}${canControlChannels ? '' : ' is-disabled'}" ${canControlChannels ? '' : 'disabled'} title="${escapeHtml(title)}" onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                    <span class="dashboard-sequencer-channel-index">${escapeHtml(String(ch.channel || '--'))}</span>
                    <span class="dashboard-sequencer-channel-led"></span>
                    <span class="dashboard-sequencer-channel-state">${ch.state ? '开' : '关'}</span>
                </button>`;
            }).join('');
            const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', { hour12:false }) : '--:--:--';
            const actionText = device.last_action || (device.online ? '待机' : '离线');
            const modeText = device.startup_mode || device.mode || '手动';
            const summaryText = device.channel_summary || `${visibleChannels.filter(ch => ch.state).length}/${visibleChannels.length || 0} 路开启`;
            return `<div class="dashboard-sequencer-panel ${device && device.online ? '' : 'offline'}">
                <div class="dashboard-sequencer-device">
                    <div class="dashboard-sequencer-title-row">
                        <div class="dashboard-sequencer-name">${escapeHtml(device.name || device.id)}</div>
                    </div>
                    <div class="dashboard-sequencer-meta">
                        <span class="ups-chip ${device && device.online ? 'online' : 'error'}">${device && device.online ? '在线' : '离线'}</span>
                        <span class="ups-chip ${device && device.locked ? 'warning' : ''}">${device && device.locked ? '锁定' : '可控'}</span>
                        <span>${escapeHtml(modeText)}</span>
                        <span class="dot"></span>
                        <span>${escapeHtml(actionText)}</span>
                        <span class="dot"></span>
                        <span>${escapeHtml(compactSnmpText(summaryText, 14))}</span>
                    </div>
                </div>
                <div class="dashboard-sequencer-strip">${channelHtml || '<div class="dashboard-sequencer-empty" style="grid-column:1/-1;">未配置通道</div>'}</div>
                <div class="dashboard-sequencer-actions">
                    <button class="dashboard-mini-btn success${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_on')">顺开</button>
                    <button class="dashboard-mini-btn danger${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_off')">顺关</button>
                    <button class="dashboard-mini-btn secondary${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_off')">全关</button>
                    <span class="dashboard-mini-note">更新 ${escapeHtml(updatedAtText)}</span>
                </div>
            </div>`;
        }
        function getSortedSequencerDevices() {
            const devices = Array.isArray(sequencerStatusCache.devices) ? [...sequencerStatusCache.devices] : [];
            return devices.sort((a, b) => {
                const sortDiff = (Number(a.sort_order || 999) - Number(b.sort_order || 999));
                if (sortDiff !== 0) return sortDiff;
                const nameA = String(a.name || a.id || '').toLowerCase();
                const nameB = String(b.name || b.id || '').toLowerCase();
                const nameDiff = nameA.localeCompare(nameB, 'zh-CN');
                if (nameDiff !== 0) return nameDiff;
                return String(a.ip || '').localeCompare(String(b.ip || ''), 'zh-CN');
            });
        }
        function filterSequencerDevices(devices, mode) {
            if (mode === 'online') return devices.filter(item => item.online);
            if (mode === 'offline') return devices.filter(item => !item.online || !!item.error_display);
            return devices;
        }
        function setSequencerFilter(mode, scope='dashboard') {
            sequencerFilters[scope] = mode;
            const wrapId = scope === 'dashboard' ? 'dashboard-sequencer-filters' : 'page-sequencer-filters';
            const wrap = document.getElementById(wrapId);
            if (wrap) {
                wrap.querySelectorAll('.sequencer-filter-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.textContent.includes(mode === 'all' ? '全部' : mode === 'online' ? '在线' : '离线/异常'));
                });
            }
            renderSequencerCards();
        }
        function renderSequencerCards() {
            const devices = getSortedSequencerDevices();
            const dashboardGrid = document.getElementById('dashboard-sequencer-grid');
            const pageGrid = document.getElementById('sequencer-page-grid');
            const dashboardDevices = filterSequencerDevices(devices, sequencerFilters.dashboard);
            const pageDevices = filterSequencerDevices(devices, sequencerFilters.page);
            const dashboardHtml = dashboardDevices.length ? dashboardDevices.map(renderCompactSequencerCard).join('') : '<div class="dashboard-sequencer-empty">当前筛选条件下暂无时序电源设备</div>';
            const pageHtml = pageDevices.length ? pageDevices.map(renderSequencerCard).join('') : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">当前筛选条件下暂无时序电源设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid) pageGrid.innerHTML = pageHtml;
            const totalEl = document.getElementById('dash-sequencer-total');
            const onlineEl = document.getElementById('dash-sequencer-online');
            if (totalEl) totalEl.innerText = devices.length;
            if (onlineEl) onlineEl.innerText = devices.filter(item => item.online).length;
        }
        function applyDashboardSectionOrder() {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard) return;
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.sort((a, b) => {
                const sa = dashboardSectionConfig[a.dataset.sectionId] || {};
                const sb = dashboardSectionConfig[b.dataset.sectionId] || {};
                return Number(sa.sort || 999) - Number(sb.sort || 999);
            }).forEach(section => dashboard.appendChild(section));
            sections.forEach(section => {
                const meta = dashboardSectionConfig[section.dataset.sectionId] || {};
                section.style.display = meta.visible === false ? 'none' : '';
            });
        }
        let dashboardMasonryTimer = 0;
        let dashboardMasonryObserver = null;
        let dashboardResizeObserver = null;
        function applyDashboardMasonry() {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard || getActiveViewId() !== 'dashboard') return;
            // Keep the monitoring wall deterministic across browsers: no masonry reflow.
            document.body.classList.remove('dashboard-masonry-mode');
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.forEach(section => { section.style.gridRowEnd = ''; });
        }
        function scheduleDashboardMasonry(delay = 80) {
            window.clearTimeout(dashboardMasonryTimer);
            dashboardMasonryTimer = window.setTimeout(() => applyDashboardMasonry(), delay);
        }
        function initDashboardMasonryObservers() {
            applyDashboardMasonry();
        }
        function getHvacViewContext() {
            return { statusMap: hvacStatusCache };
        }
        function getHvacSummaryApi() {
            return window.SmartCenter?.hvacView || window.SmartCenter?.hvacSummary || null;
        }
        function updateHvacRoomEnvSlots() {
            const api = getHvacSummaryApi();
            if (!api || typeof api.renderHvacRoomEnvChips !== 'function') return;
            document.querySelectorAll('[data-hvac-room-env]').forEach(slot => {
                const roomName = slot.getAttribute('data-hvac-room-env') || '';
                const html = api.renderHvacRoomEnvChips(roomName);
                slot.innerHTML = html;
                slot.classList.toggle('is-empty', !html);
            });
            document.querySelectorAll('[data-hvac-card-env]').forEach(slot => {
                const roomName = slot.getAttribute('data-hvac-card-env') || '';
                const html = api.renderHvacRoomEnvChips(roomName, { compact: true, limit: 1 });
                slot.innerHTML = html;
                slot.classList.toggle('is-empty', !html);
                const row = slot.closest('.hvac-compact-row, .hvac-info-row');
                if (row) {
                    row.classList.toggle('is-empty', !html);
                    if (html) row.style.removeProperty('display');
                    else row.style.setProperty('display', 'none', 'important');
                }
            });
        }
        function toggleHvacTempControls(deviceId, scope = '', event = null) {
            if (event) event.stopPropagation();
            closeHvacModeMenus();
            const panel = document.getElementById(`hvac-temp-${getHvacControlId(deviceId, scope)}`);
            if (!panel) return;
            document.querySelectorAll('.hvac-temp-panel.open').forEach(item => {
                if (item !== panel) item.classList.remove('open');
            });
            panel.classList.toggle('open');
        }
        function closeHvacTempControls() {
            document.querySelectorAll('.hvac-temp-panel.open').forEach(item => item.classList.remove('open'));
        }
        function toggleHvacModeMenu(deviceId, scope = '', event = null) {
            if (event) event.stopPropagation();
            closeHvacTempControls();
            const metric = document.getElementById(`hvac-mode-${getHvacControlId(deviceId, scope)}`);
            if (!metric) return;
            document.querySelectorAll('.hvac-mode-block.open').forEach(item => {
                if (item !== metric) item.classList.remove('open');
            });
            metric.classList.toggle('open');
        }
        function closeHvacModeMenus() {
            document.querySelectorAll('.hvac-mode-block.open').forEach(item => item.classList.remove('open'));
        }
        function adjustHvacTemperature(deviceId, delta, event = null) {
            if (event) event.stopPropagation();
            const status = hvacStatusCache[deviceId] || {};
            const bounds = getHvacTempBounds(status);
            const currentTarget = toHvacNumber(status.target_temp, toHvacNumber(status.temp, 24));
            const nextValue = Math.min(bounds.max, Math.max(bounds.min, Math.round((currentTarget + Number(delta || 0)) / bounds.step) * bounds.step));
            hvacStatusCache[deviceId] = Object.assign({}, status, { target_temp: Number(nextValue.toFixed(1)), temp: Number(nextValue.toFixed(1)) });
            renderHvacCards();
            controlHvac(deviceId, 'set_temp', { temperature: Number(nextValue.toFixed(1)) });
        }
        function selectHvacMode(deviceId, mode) {
            closeHvacModeMenus();
            controlHvac(deviceId, String(mode || '').toLowerCase() === 'off' ? 'power_off' : 'set_mode', { mode });
        }
        function renderHvacCards() {
            const dashboardGrid = document.getElementById('dashboard-hvac-grid');
            const pageGrid = document.getElementById('hvac-grid-container');
            const summaryApi = getHvacSummaryApi();
            const fullApi = window.SmartCenter?.hvacView || null;
            if (!summaryApi || typeof summaryApi.buildHvacGroups !== 'function') {
                if (dashboardGrid) dashboardGrid.innerHTML = '<div class="hvac-empty">空调摘要模块加载中...</div>';
                return;
            }
            const visibleConfigs = hvacConfigs.filter(cfg => cfg && cfg.visible !== false);
            const groups = summaryApi.buildHvacGroups(visibleConfigs, hvacStatusCache);
            const context = getHvacViewContext();
            const dashboardHtml = groups.length
                ? summaryApi.renderDashboardHvacOverview(groups, context)
                : '<div class="hvac-empty">未配置空调设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid && getActiveViewId() === 'hvac') {
                const pageHtml = groups.length && fullApi && typeof fullApi.renderHvacGroup === 'function'
                    ? groups.map(group => fullApi.renderHvacGroup(group, 'page', context)).join('')
                    : '<div class="hvac-empty">空调详情模块加载中...</div>';
                pageGrid.innerHTML = pageHtml || '<div class="hvac-empty">未配置空调设备</div>';
            }
            const dashHvacOnline = document.getElementById('dash-hvac-online');
            if (dashHvacOnline) dashHvacOnline.innerText = visibleConfigs.filter(cfg => (hvacStatusCache[cfg.id] || {}).online).length;
        }
        function findNavElementByView(viewId) {
            return Array.from(document.querySelectorAll('.nav-menu li')).find(el => String(el.getAttribute('onclick') || '').includes(`switchTab('${viewId}'`)) || null;
        }
        function getInitialViewFromUrl() {
            const params = new URLSearchParams(window.location.search || '');
            const requested = String(params.get('view') || params.get('tab') || '').trim();
            if (!requested) return null;
            const safeView = requested.replace(/[^a-zA-Z0-9_-]/g, '');
            if (!safeView || !document.getElementById('view-' + safeView)) return null;
            return safeView;
        }
        function getViewTitleFromNav(navEl, fallback = '') {
            const onclickText = String(navEl?.getAttribute('onclick') || '');
            const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
            return match ? match[2] : fallback;
        }
        function updateHvacStatus(showError = false) {
            if (!hvacConfigs.length) return Promise.resolve({});
            return fetchJson('/api/hvac/status', {}, '空调状态读取失败')
                .then(data => {
                    hvacStatusCache = data || {};
                    renderHvacCards();
                    return data;
                })
                .catch(err => {
                    console.error('空调状态更新失败', err);
                    if (showError) showToast(translateApiError(err?.message, '空调状态读取失败'), true);
                    throw err;
                });
        }
        function controlHvac(deviceId, action, extra = {}) {
            if (!ensurePermission('hvac.control', '控制空调')) return;
            const payload = Object.assign({ device_id: deviceId, action }, extra || {});
            const loadingTextMap = {
                power_on: '空调开机指令下发中...',
                power_off: '空调关机指令下发中...',
                set_mode: '空调模式切换中...',
                set_temp: '空调温度设置中...'
            };
            showToast(loadingTextMap[action] || '空调控制中...', false);
            fetchJsonLoose('/api/hvac/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }, '空调控制失败')
                .then(data => {
                    if (!data?.success) {
                        showToast(data?.msg || data?.message || '空调控制失败', true);
                        return;
                    }
                    if (data.status && typeof data.status === 'object') {
                        hvacStatusCache[deviceId] = data.status;
                        renderHvacCards();
                    }
                    showToast(data.msg || '空调控制成功');
                    setTimeout(() => { updateHvacStatus(); updateDashboardLogs(); }, 320);
                })
                .catch(err => {
                    showToast(translateApiError(err?.message, '空调控制失败'), true);
                });
        }

        setInterval(updateGlobalClock, 1000);

        // 门禁控制
        let doorDrawState = { slot: '', isDrawing: false, startX: 0, startY: 0 };
        function initDoorCanvas(slot) {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            if (els.image.clientWidth > 0) {
                els.canvas.width = els.image.clientWidth;
                els.canvas.height = els.image.clientHeight;
            }
        }
        ['left', 'right'].forEach(slot => {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            const ctx = els.canvas.getContext('2d');
            els.image.onload = function() { initDoorCanvas(slot); };
            els.canvas.addEventListener('mousedown', function(e) {
                if (doorDrawState.slot !== slot) return;
                doorDrawState.isDrawing = true;
                const rect = els.image.getBoundingClientRect();
                doorDrawState.startX = e.clientX - rect.left;
                doorDrawState.startY = e.clientY - rect.top;
            });
            els.canvas.addEventListener('mousemove', function(e) {
                if (doorDrawState.slot !== slot || !doorDrawState.isDrawing) return;
                const rect = els.image.getBoundingClientRect();
                const currentX = e.clientX - rect.left;
                const currentY = e.clientY - rect.top;
                ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
                ctx.strokeStyle = '#3b82f6';
                ctx.lineWidth = 3;
                ctx.strokeRect(doorDrawState.startX, doorDrawState.startY, currentX - doorDrawState.startX, currentY - doorDrawState.startY);
            });
            els.canvas.addEventListener('mouseup', function(e) {
                if (doorDrawState.slot !== slot || !doorDrawState.isDrawing) return;
                doorDrawState.isDrawing = false;
                const rect = els.image.getBoundingClientRect();
                const endX = e.clientX - rect.left;
                const endY = e.clientY - rect.top;
                const p_x1 = Math.max(0, Math.min(doorDrawState.startX, endX) / rect.width);
                const p_y1 = Math.max(0, Math.min(doorDrawState.startY, endY) / rect.height);
                const p_x2 = Math.min(1, Math.max(doorDrawState.startX, endX) / rect.width);
                const p_y2 = Math.min(1, Math.max(doorDrawState.startY, endY) / rect.height);
                const cameraKey = getDoorSlotCameraKey(slot);
                saveDoorRegionSelection({ camera_key: cameraKey, p_x1, p_y1, p_x2, p_y2 })
                    .then(data => {
                        doorRegionsCache[cameraKey] = (data && data.region) ? data.region : { p_x1, p_y1, p_x2, p_y2 };
                        ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
                        els.canvas.style.display = 'none';
                        doorDrawState.slot = '';
                    })
                    .catch(err => {
                        showToast(`保存失败: ${translateApiError(err?.message, '请稍后重试')}`, true);
                    });
            });
        });
        window.onresize = () => {
            initDoorCanvas('left');
            initDoorCanvas('right');
            resizePowerCharts();
            if (myCharts.meterTrend) myCharts.meterTrend.resize();
            if (myCharts.dashboardEnergyTrend) myCharts.dashboardEnergyTrend.resize();
        };
        function startDrawRegion(slot = 'right') {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            initDoorCanvas(slot);
            doorDrawState = { slot, isDrawing: false, startX: 0, startY: 0 };
            els.canvas.style.display = 'block';
            els.canvas.style.cursor = 'crosshair';
            showToast(`请在${slot === 'right' ? '右侧' : '左侧'}画面拖拽框选检测区域`);
        }
        function openWizard() { document.getElementById('aiWizardModal').style.display = 'block'; document.getElementById('step1-card').style.opacity = '1'; document.getElementById('step1-card').style.pointerEvents = 'auto'; document.getElementById('step2-card').style.opacity = '0.4'; document.getElementById('step2-card').style.pointerEvents = 'none'; }
        function closeWizard() { document.getElementById('aiWizardModal').style.display = 'none'; }
        const wizardBox = document.getElementById('wizardBox'); const wizardHeader = document.getElementById('wizardHeader'); let isWizDragging = false; let wizOffsetX = 0, wizOffsetY = 0; wizardHeader.addEventListener('mousedown', function(e) { if(e.target.tagName.toLowerCase() === 'button') return; isWizDragging = true; wizOffsetX = e.clientX - wizardBox.offsetLeft; wizOffsetY = e.clientY - wizardBox.offsetTop; wizardBox.style.transition = 'none'; wizardBox.style.opacity = '0.9'; }); document.addEventListener('mousemove', function(e) { if (!isWizDragging) return; wizardBox.style.left = (e.clientX - wizOffsetX) + 'px'; wizardBox.style.top = (e.clientY - wizOffsetY) + 'px'; wizardBox.style.right = 'auto'; }); document.addEventListener('mouseup', function() { if (isWizDragging) { isWizDragging = false; wizardBox.style.transition = 'opacity 0.2s'; wizardBox.style.opacity = '1'; } });

        // 强电与灯光控制
        configData.cabinets.forEach((cab, idx) => { pwrLocks[idx] = {}; pwrStates[idx] = []; pwrDesiredStates[idx] = {}; });
function renderPwrChannel(cabId, chNum) { const cachedChannels = (powerStatusCache[cabId] || {}).channels_1_4; const hasCachedStatus = Array.isArray(cachedChannels) && cachedChannels[chNum - 1] !== undefined; const status = getPowerChannelStatus(cabId, chNum); const chItem = document.getElementById(`pch_${cabId}_${chNum}`); if(!chItem) return; let chCfg = (configData.cabinets[cabId].channels_config || []).find(c => c.channel === chNum); let chName = chCfg ? chCfg.name : (configData.cabinets[cabId].ui_text.label_channel + chNum); let chRemark = chCfg ? (chCfg.remark || '') : ''; const ui = configData.cabinets[cabId].ui_text; const isPending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]); const cls = isPending ? 'ch-off' : (status === null || status === undefined ? 'ch-err' : (status ? 'ch-on' : 'ch-off')); const txt = isPending ? '执行中' : (status === null || status === undefined ? '离线' : (status ? ui.label_on : ui.label_off)); const oldClasses = Array.from(chItem.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn' || c === 'power-channel-btn').join(' '); chItem.className = `${oldClasses || 'ch-btn power-channel-btn'} ${cls}`; chItem.innerHTML = `<span class="name" title="${escapeHtml(chRemark ? chName + ' / ' + chRemark : chName)}">${escapeHtml(chName)}</span>${chRemark ? `<span class="remark" title="${escapeHtml(chRemark)}">${escapeHtml(chRemark)}</span>` : ''}<span class="state">${escapeHtml(txt)}</span>`; chItem.disabled = isPending || chItem.classList.contains('permission-disabled'); chItem.style.pointerEvents = isPending ? 'none' : ''; chItem.style.opacity = isPending ? '0.78' : ''; chItem.dataset.stateSource = hasCachedStatus ? 'api' : 'local'; }
        function exportEnergyHistory() {
            window.open('/api/export/energy_30days', '_blank');
        }

        configData.light_devices.forEach(dev => { lightLocks[dev.id] = {}; lightStates[dev.id] = []; lightInputStates[dev.id] = []; lightOnlineStates[dev.id] = false; });
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
            const channelNo = Number(chNum);
            const apiSources = [
                (channelsMap || {})[devId],
                (channelsMap || {})[String(devId)],
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
                lightStates[devId],
                lightStates[String(devId)],
            ];
            for (const source of cacheSources) {
                if (!source) continue;
                if (Array.isArray(source)) {
                    const candidates = [source[channelNo]];
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
            return null;
        }
        function getLightChannelUiState(devId, chNum) {
            const status = getLightChannelStateFromSources(devId, chNum, {});
            const isOnline = !!lightOnlineStates[devId];
            if (!isOnline) return { cls: 'ch-err', text: '离线', actionable: false };
            if (status === true) return { cls: 'ch-on', text: '已开启', actionable: true };
            if (status === false) return { cls: 'ch-off', text: '已关闭', actionable: true };
            return { cls: 'ch-unknown', text: '待确认', actionable: false };
        }
        function renderLightChannel(devId, chNum) { const btn = document.getElementById(`lch_${devId}_${chNum}`); if(!btn) return; const uiState = getLightChannelUiState(devId, chNum); const oldClasses = Array.from(btn.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn').join(' '); btn.className = `${oldClasses} ${uiState.cls}`; btn.querySelector('.state').innerText = uiState.text; btn.title = uiState.actionable ? '' : (lightOnlineStates[devId] ? '设备在线，但该通道状态暂未确认' : '设备离线，无法读取通道状态'); }
        function getLightInputState(devId, inputNum, inputsMap = {}) {
            const list = Array.isArray(inputsMap[devId]) ? inputsMap[devId] : (Array.isArray(inputsMap[String(devId)]) ? inputsMap[String(devId)] : lightInputStates[devId]);
            if (!Array.isArray(list)) return null;
            return normalizeLightChannelState(list[Number(inputNum) - 1]);
        }
        function renderLightInput(devId, inputNum) {
            const chip = document.getElementById(`lin_${devId}_${inputNum}`);
            if (!chip) return;
            const state = getLightInputState(devId, inputNum);
            const isOnline = !!lightOnlineStates[devId];
            const cls = !isOnline ? 'offline' : (state === true ? 'active' : (state === false ? 'idle' : 'unknown'));
            const text = !isOnline ? '离线' : (state === true ? '触发' : (state === false ? '未触发' : '待确认'));
            const oldClasses = Array.from(chip.classList).filter(c => c.startsWith('ch-span-') || c === 'relay-input-chip').join(' ');
            chip.className = `${oldClasses} ${cls}`;
            const stateEl = chip.querySelector('.state');
            if (stateEl) stateEl.innerText = text;
            chip.title = state === true ? '输入接口检测到有效电平' : (state === false ? '输入接口未检测到有效电平' : '输入接口状态待确认');
        }
        function getVisibleLightInputs(device) {
            return Array.isArray(device.input_channels_config)
                ? device.input_channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                : [];
        }
        function renderDashboardInputSummary(device, extraMeta, compact=false) {
            const inputs = Array.isArray(extraMeta.inputs) ? extraMeta.inputs : [];
            const visibleInputs = getVisibleLightInputs(device);
            const count = visibleInputs.length || inputs.length;
            if (!count) return '';
            const active = inputs.filter(item => normalizeLightChannelState(item) === true).length;
            if (compact) return renderHomeCompactMetric('输入触发', `${active} / ${count}`, active > 0 ? 'warn' : '');
            return `<div class="dashboard-mini-note">输入触发 ${escapeHtml(String(active))} / ${escapeHtml(String(count))}</div>`;
        }
        function renderDashboardLightCards(statusData = {}) {
            const container = document.getElementById('dashboard-light-grid');
            if (!container) return;
            const devices = Array.isArray(configData.light_devices) ? configData.light_devices.slice(0, 4) : [];
            const extras = statusData.extras || {};
            if (!devices.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置灯光模块</div>';
                return;
            }
            container.innerHTML = devices.map(device => {
                const extraMeta = extras[String(device.id)] || {};
                const statusMeta = getDeviceStatusMeta({
                    online: !!((statusData.online || {})[device.id]),
                    status_level: extraMeta.status_level,
                    stale: extraMeta.stale,
                    poll_failures: extraMeta.poll_failures,
                    last_success_at: extraMeta.last_success_at,
                    last_checked_at: extraMeta.last_checked_at,
                    last_error: extraMeta.last_error,
                }, { staleText: '陈旧', errorText: '异常' });
                const online = statusMeta.isOnlineLike;
                const channels = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999)).slice(0, 4) : [];
                const currentStates = Array.isArray((statusData.channels || {})[device.id]) ? (statusData.channels || {})[device.id] : [];
                const visibleChannelCount = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).length : currentStates.length;
                const onCount = currentStates.filter(Boolean).length;
                const unknownCount = currentStates.filter(st => st === null || st === undefined).length;
                const actions = channels.map(ch => {
                    const uiState = getLightChannelUiState(device.id, ch.channel);
                    const btnClass = uiState.cls === 'ch-on' ? 'success' : (uiState.cls === 'ch-off' ? 'secondary' : (online ? 'warning' : 'danger'));
                    return `<button class="dashboard-mini-btn ${btnClass}${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${escapeHtml(device.id)}', ${Number(ch.channel)})">${escapeHtml(ch.name || ('CH' + ch.channel))}</button>`;
                }).join('');
                const extraButtons = (((extras[String(device.id)] || {}).dashboard_action_buttons) || []).filter(item => item && item.visible !== false).map(item => {
                    return `<button class="dashboard-mini-btn secondary${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${escapeHtml(device.id)}', '${escapeHtml(item.action || '')}', '${escapeHtml(item.label || item.action || '')}')">${escapeHtml(item.label || item.action || '动作')}</button>`;
                }).join('');
                return `<div class="dashboard-mini-card ${getCardStateClass(statusMeta)}">
                    <div class="dashboard-mini-head">
                        <div>
                            <div class="dashboard-mini-title">${escapeHtml(device.name || device.id)}</div>
                            <div class="dashboard-mini-subtitle">${escapeHtml(device.ip || device.id || '--')}</div>
                        </div>
                        <div class="dashboard-mini-chip-row">
                            <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                        </div>
                    </div>
                    <div class="dashboard-mini-light-summary">
                        <div class="dashboard-mini-light-count">已开 ${escapeHtml(String(onCount))} / ${escapeHtml(String(visibleChannelCount || currentStates.length || 0))}</div>
                        <div class="dashboard-mini-note">${online ? (unknownCount > 0 ? `${unknownCount} 路状态待确认` : statusMeta.note) : statusMeta.note}</div>
                    </div>
                    ${renderDashboardInputSummary(device, extraMeta)}
                    <div class="dashboard-mini-actions">${actions || '<span class="dashboard-mini-note">暂无可用通道</span>'}${extraButtons}</div>
                </div>`;
            }).join('');
        }
        function renderDashboardLightCompact(statusData = {}) {
            const container = document.getElementById('dashboard-light-compact-grid');
            if (!container) return;
            const devices = Array.isArray(configData.light_devices) ? configData.light_devices : [];
            const onlineMap = statusData.online || {};
            const channelsMap = statusData.channels || {};
            const extras = statusData.extras || {};
            if (!devices.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置灯光模块</div>';
                return;
            }
            container.classList.remove('home-status-list');
            container.innerHTML = devices.map(device => {
                const extraMeta = extras[String(device.id)] || {};
                const statusMeta = getDeviceStatusMeta({
                    online: !!onlineMap[device.id],
                    status_level: extraMeta.status_level,
                    stale: extraMeta.stale,
                    poll_failures: extraMeta.poll_failures,
                    last_success_at: extraMeta.last_success_at,
                    last_checked_at: extraMeta.last_checked_at,
                    last_error: extraMeta.last_error,
                }, { staleText: '陈旧', errorText: '异常' });
                const online = statusMeta.isOnlineLike;
                const rawStates = Array.isArray(channelsMap[device.id]) ? channelsMap[device.id] : (Array.isArray(channelsMap[String(device.id)]) ? channelsMap[String(device.id)] : []);
                const visibleChannels = Array.isArray(device.channels_config)
                    ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                    : [];
                const total = visibleChannels.length || rawStates.length || 0;
                const knownVisibleStates = visibleChannels.length
                    ? visibleChannels.map(ch => getLightChannelStateFromSources(device.id, ch.channel, channelsMap))
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
                    const state = getLightChannelStateFromSources(device.id, chNum, channelsMap);
                    const cls = state === true ? 'on' : (state === false ? 'off' : 'warning');
                    const stateText = state === true ? '开' : (state === false ? '关' : '?');
                    const baseName = String(ch.name || `CH${chNum}`);
                    const displayName = actionNameCounts.get(baseName) > 1 ? `${baseName} ${chNum}` : baseName;
                    return `<button class="home-compact-action ${cls}${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${escapeHtml(device.id)}', ${chNum})"><span class="label">${escapeHtml(displayName)}</span><span class="home-action-state">${escapeHtml(stateText)}</span></button>`;
                }).join('');
                const extraButtons = ((extraMeta.dashboard_action_buttons || [])).filter(item => item && item.visible !== false).slice(0, 2).map(item => {
                    return `<button class="home-compact-action success${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${escapeHtml(device.id)}', '${escapeHtml(item.action || '')}', '${escapeHtml(item.label || item.action || '')}')">${escapeHtml(item.label || item.action || '动作')}</button>`;
                }).join('');
                return `<div class="home-compact-card ${online ? '' : 'offline'}">
                    <div class="home-compact-head">
                        <div style="min-width:0;">
                            <div class="home-compact-title">${escapeHtml(device.name || device.id)}</div>
                            <div class="home-compact-subtitle">${escapeHtml(device.ip || device.id || '--')}</div>
                        </div>
                        <div class="home-compact-chip-row">
                            <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                        </div>
                    </div>
                    <div class="home-compact-metrics">
                        ${renderHomeCompactMetric('已开路数', `${onCount} / ${total || '--'}`, onCount > 0 ? 'ok' : '')}
                        ${renderHomeCompactMetric('状态待确认', String(unknownCount || 0), unknownCount > 0 ? 'warn' : '')}
                        ${renderDashboardInputSummary(device, extraMeta, true)}
                    </div>
                    <div class="home-compact-actions">${actions || '<span class="home-compact-note">暂无可用通道</span>'}${extraButtons}</div>
                    <div class="home-compact-note">${escapeHtml(statusMeta.note || '--')}</div>
                </div>`;
            }).join('');
        }

        // 服务器面板控制
        function getColor(p) { return p > 90 ? 'bg-red' : (p > 70 ? 'bg-yellow' : 'bg-green'); }
        function formatServerTime(value) {
            if(!value) return '未记录';
            const d = new Date(value);
            if (Number.isNaN(d.getTime())) return value;
            return d.toLocaleString('zh-CN', { hour12: false });
        }
        function formatServerClockOffset(value) {
            const offset = Number(value);
            if (!Number.isFinite(offset)) return '未获取';
            const abs = Math.abs(offset);
            if (abs < 1) return '正常';
            const prefix = offset > 0 ? '快' : '慢';
            if (abs >= 3600) return `${prefix}${(abs / 3600).toFixed(1)}小时`;
            if (abs >= 60) return `${prefix}${(abs / 60).toFixed(abs >= 600 ? 0 : 1)}分钟`;
            return `${prefix}${abs.toFixed(0)}秒`;
        }
        function getServerClockOffsetClass(value) {
            const offset = Math.abs(Number(value));
            if (!Number.isFinite(offset)) return ' clock-unknown';
            if (offset >= 300) return ' clock-bad';
            if (offset >= 120) return ' clock-warn';
            return ' clock-ok';
        }

        function getServerRenderContext() {
            return {
                serverViewMode,
                latestAgentVersion,
                compareAgentVersionBase,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getServerCommandPending,
            };
        }

        // AI_BRIDGE: projector_view_helpers
        // 投影机渲染/格式化逻辑已迁移到 static/js/views/projector.js；这里仅保留运行时状态上下文和真实控制链路。
        function getProjectorViewContext() {
            return {
                projectorConfigs,
                statusCache: projectorStatusCache,
                getStatus: (projId) => projectorStatusCache[projId] || null,
                escapeHtml,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getDeviceStatusMeta,
                getCardStateClass,
            };
        }
        window.getProjectorViewContext = getProjectorViewContext;

        function openProjectorRemote(projId) {
            currentProjectorRemoteId = String(projId);
            const modal = document.getElementById('projectorRemoteModal');
            if (modal) modal.style.display = 'block';
            ensureModulesReady(['projector-view'], '投影遥控器模块')
                .then(() => {
                    if (typeof renderProjectorRemote === 'function') renderProjectorRemote(currentProjectorRemoteId);
                })
                .catch(() => showToast('投影遥控器模块加载失败，请刷新后重试', true));
        }
        function closeProjectorRemote() {
            const modal = document.getElementById('projectorRemoteModal');
            if (modal) modal.style.display = 'none';
            currentProjectorRemoteId = null;
        }

        function refreshProjectorStatusAfterCommand() {
            updateProjectorStatus();
            [700, 1800, 4200].forEach(delay => setTimeout(updateProjectorStatus, delay));
        }

        function getScreenCommand(screen, action) {
            return (screen.commands || []).find(cmd => String(cmd.action || '').toLowerCase() === action) || null;
        }
        function getScreenActionText(status) {
            if (!status || status.online === false) return '离线';
            if (status.is_moving) return status.action === 'up' ? '正在上升...' : '正在下降...';
            return '已停止';
        }
        function getScreenActionColor(status) {
            if (!status || status.online === false) return '#94a3b8';
            if (status.is_moving) return 'var(--warning)';
            return 'var(--text-sub)';
        }
        function renderScreenControlButton(screen, action, label, className) {
            const cmd = getScreenCommand(screen, action);
            const iconMap = { up: '↑', stop: '■', down: '↓' };
            const icon = iconMap[action] || '•';
            if (!cmd) {
                return `<button class="screen-control-btn ${className}" disabled title="未配置${label}指令"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
            }
            return `<button class="screen-control-btn ${className}${getPermissionDisabledClass('screen.control')}" ${getPermissionDisabledAttrs('screen.control', '当前账号无幕布控制权限')} title="${label}" onclick="fireScreenCommand('${escapeHtml(screen.id)}', '${escapeHtml(cmd.payload || '')}', '${escapeHtml(cmd.format || 'hex')}', '${escapeHtml(cmd.action || action)}')"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
        }
        function buildScreenEnvCards() {
            const cards = [];
            if (Array.isArray(envConfigs) && envConfigs.length) {
                const onlineEnv = envConfigs.map(cfg => ({ cfg, st: window.__envStatusCache?.[cfg.id] || {} })).find(item => item.st && item.st.online);
                const fallbackEnv = envConfigs[0] ? { cfg: envConfigs[0], st: window.__envStatusCache?.[envConfigs[0].id] || {} } : null;
                const envItem = onlineEnv || fallbackEnv;
                if (envItem) {
                    const cfg = envItem.cfg;
                    const st = envItem.st || {};
                    const online = !!st.online;
                    const temp = st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--';
                    const hum = st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--';
                    const lux = st.lux !== null && st.lux !== undefined ? `${st.lux} Lux` : '--';
                    const tempIcon = `<span class="screen-companion-metric-icon temp"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0v7.2a4.5 4.5 0 1 1-4 0V5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 14V8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.8" fill="currentColor"/></svg></span>`;
                    const humIcon = `<span class="screen-companion-metric-icon hum"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.8C9.4 7.2 6 10.4 6 14.2A6 6 0 0 0 18 14.2c0-3.8-3.4-7-6-10.4Z" fill="currentColor" fill-opacity="0.92"/><path d="M9.6 15.4c.5 1.4 1.6 2.2 3 2.5" stroke="#dbeafe" stroke-width="1.4" stroke-linecap="round"/></svg></span>`;
                    const luxIcon = `<span class="screen-companion-metric-icon lux"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.8v2.3M12 18.9v2.3M21.2 12h-2.3M5.1 12H2.8M18.6 5.4l-1.6 1.6M7 17l-1.6 1.6M18.6 18.6 17 17M7 7 5.4 5.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></span>`;
                    cards.push(`<div class="screen-companion-card screen-companion-env">
                        <div class="screen-companion-title">
                            <span>${escapeHtml(cfg.name || cfg.id)}</span>
                            <span class="screen-companion-tag" style="${online ? '' : 'color:#cbd5e1;background:rgba(100,116,139,0.16);border-color:rgba(148,163,184,0.18);'}">${online ? '在线' : '离线'}</span>
                        </div>
                        <div class="screen-companion-metrics">
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${tempIcon}<div class="label">温度</div></div>
                                <div class="value">${escapeHtml(temp)}</div>
                            </div>
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${humIcon}<div class="label">湿度</div></div>
                                <div class="value">${escapeHtml(hum)}</div>
                            </div>
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${luxIcon}<div class="label">光照</div></div>
                                <div class="value">${escapeHtml(lux)}</div>
                            </div>
                        </div>
                        <div class="screen-companion-footer">
                            <span>来源 ${escapeHtml(cfg.name || cfg.id)}</span>
                            <span>${online ? '实时采集' : '等待恢复'}</span>
                        </div>
                    </div>`);
                }
            }
            if (!cards.length) {
                cards.push(`<div class="screen-companion-card screen-placeholder-card">
                    <div class="screen-companion-title">
                        <span class="screen-placeholder-icon">+</span>
                        <span>环境摘要</span>
                    </div>
                    <div class="screen-companion-note">这里显示环境传感器的温度、湿度和光照摘要。</div>
                </div>`);
            }
            return cards.join('');
        }
        function buildScreenAutomationCards() {
            return `<div class="dash-stat-card outdoor-automation-card" id="dash-outdoor-automation-card">
                <div class="outdoor-auto-head">
                    <div class="outdoor-auto-title">户外灯自动化</div>
                    <span class="outdoor-auto-chip" id="dash-outdoor-auto-chip">等待状态</span>
                </div>
                <div class="outdoor-auto-main">
                    <div class="outdoor-auto-kpi">
                        <div class="value" id="dash-outdoor-lux">--</div>
                        <div class="sub" id="dash-outdoor-status-text">正在等待光照与自动化状态...</div>
                    </div>
                    <div class="outdoor-auto-metrics">
                        <div class="outdoor-auto-metric">
                            <div class="label">开灯窗口</div>
                            <div class="value" id="dash-outdoor-eta">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">关灯计划</div>
                            <div class="value" id="dash-outdoor-off-countdown">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">开灯条件</div>
                            <div class="value" id="dash-outdoor-window">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">复位规则</div>
                            <div class="value" id="dash-outdoor-debounce">--</div>
                        </div>
                    </div>
                </div>
                <div class="outdoor-auto-note" id="dash-outdoor-note">低于阈值自动开灯，20:00 自动关灯。</div>
            </div>`;
        }
        function renderScreenStatusCard(screen) {
            const status = screen.status || {};
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const position = Number.isFinite(Number(status.position)) ? Number(status.position) : 0;
            const height = Number.isFinite(Number(status.height)) ? Number(status.height) : 0;
            const totalHeight = screen.screen_config?.total_height || status.total_height || 3.0;
            const totalTime = screen.screen_config?.total_time || 30;
            const onlineText = statusMeta.text;
            const actionText = getScreenActionText(status);
            const remainingTime = Number.isFinite(Number(status.remaining_time)) ? Number(status.remaining_time).toFixed(1) : '0.0';
            const clampedPosition = Math.max(0, Math.min(100, position));
            const posState = clampedPosition >= 95 ? '全降（到底）' : (clampedPosition <= 5 ? '全升（到顶）' : '中间位置');
            return `<div class="screen-status-card ${isOnline ? '' : 'offline'} ${getCardStateClass(statusMeta)}" id="screen-status-${escapeHtml(screen.id)}">
                <div class="screen-status-header">
                    <div class="screen-status-name">${escapeHtml(screen.name || screen.id)}</div>
                    <div class="screen-status-online ${isOnline ? '' : 'offline'} ${statusMeta.level === 'stale' || statusMeta.level === 'error' ? 'warning' : ''}">${onlineText}</div>
                </div>
                <div class="screen-main-row">
                    <div class="screen-core-meta">
                        <div class="screen-progress-panel">
                            <div class="screen-progress-rail" title="竖版位置进度">
                                <div class="screen-progress-fill-vertical" style="height:${clampedPosition}%; --screen-pos:${clampedPosition}%;"></div>
                            </div>
                            <div class="screen-progress-meta">
                                <div class="screen-progress-head">
                                    <span class="screen-progress-label">当前位置</span>
                                    <span class="screen-position-text">${clampedPosition.toFixed(1)}%</span>
                                </div>
                                <div class="screen-position-note">${posState}</div>
                                <div class="screen-metrics">
                                    <div>
                                        <div class="screen-metric-label">当前高度</div>
                                        <div class="screen-metric-value">${height.toFixed(2)} 米</div>
                                    </div>
                                    <div>
                                        <div class="screen-metric-label">幕布状态</div>
                                        <div class="screen-metric-value" style="color:${getScreenActionColor(status)}">${escapeHtml(actionText)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="screen-control-side">
                        ${renderScreenControlButton(screen, 'up', '上升', 'up')}
                        ${renderScreenControlButton(screen, 'stop', '停止', 'stop')}
                        ${renderScreenControlButton(screen, 'down', '下降', 'down')}
                    </div>
                </div>
                <div class="screen-status-foot">
                    <span>总高度：${escapeHtml(totalHeight)} 米</span>
                    <span>全程时间：${escapeHtml(totalTime)} 秒</span>
                    <span>剩余时间：${escapeHtml(remainingTime)} 秒</span>
                </div>
                <div class="dashboard-mini-note">${escapeHtml(statusMeta.note)}</div>
            </div>`;
        }

        // 环境与自动化引擎
        const envConfigs = Array.isArray(configData.env_sensors) ? configData.env_sensors : [];
        window.__envConfigsCache = envConfigs;
        // 环境传感器页面和首页摘要已迁移到 static/js/views/env.js。
        function applyPermissionUI() {
            const disabledStyle = 'opacity:.55;cursor:not-allowed;pointer-events:none;filter:grayscale(.18);';
            const configLink = document.querySelector('.system-link');
            const configBtn = document.getElementById('top-user-config-btn');
            if (configLink && !canOpenConfigCenter()) {
                configLink.style.display = 'none';
            }
            if (configBtn && !canOpenConfigCenter()) {
                configBtn.style.display = 'none';
            }
            if (!hasPermission('power.control')) {
                document.querySelectorAll('[onclick*="togglePower("],[onclick*="doPowerStart("],[onclick*="doPowerStop("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无强电控制权限';
                });
            }
            if (!hasPermission('light.control')) {
                document.querySelectorAll('[onclick*="toggleLight("],[onclick*="executeScene("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无灯光控制权限';
                });
            }
            if (!hasPermission('door.control')) {
                document.querySelectorAll('[onclick*="controlDoor("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无门禁控制权限';
                });
            }
            if (!hasPermission('automation.edit')) {
                document.querySelectorAll('.auto-item input[type="checkbox"]').forEach(el => {
                    el.disabled = true;
                    el.title = '当前账号无自动化编辑权限';
                });
                document.querySelectorAll('.auto-edit-btn,.auto-edit-save,.auto-edit-cancel').forEach(el => {
                    el.disabled = true;
                    el.title = '当前账号无自动化编辑权限';
                });
            }
            if (!hasPermission('server.control')) {
                document.querySelectorAll('[onclick*="moveServer("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无服务器控制权限';
                });
            }
        }

        function reportFrontendError(scope, err) {
            return SmartCenter.utils.reportFrontendError(scope, err);
        }

        function guardFrontendStep(scope, fn, fallbackMessage = '') {
            return SmartCenter.utils.guardFrontendStep(scope, fn, fallbackMessage);
        }

        window.addEventListener('error', event => {
            if (!event) return;
            const detail = event.error || event.message || 'window_error';
            reportFrontendError('window.error', detail);
        });

        window.addEventListener('unhandledrejection', event => {
            const detail = event && event.reason ? event.reason : 'unhandled_rejection';
            reportFrontendError('window.unhandledrejection', detail);
        });

        function initCanvas() {
            initDoorCanvas('left');
            initDoorCanvas('right');
        }

        document.addEventListener('DOMContentLoaded', () => {
            applyAdaptiveDensity();
            guardFrontendStep('bootstrap.permission_ui', () => applyPermissionUI());
            guardFrontendStep('bootstrap.dashboard_order', () => applyDashboardSectionOrder());
            guardFrontendStep('bootstrap.dashboard_masonry_observer', () => initDashboardMasonryObservers());
            guardFrontendStep('bootstrap.dashboard_deferred_modules', () => {
                initDashboardDeferredModuleObserver();
                bindDashboardDeferredModuleFallback();
            });
            guardFrontendStep('bootstrap.dashboard_masonry', () => scheduleDashboardMasonry(160));
            guardFrontendStep('bootstrap.global_clock', () => updateGlobalClock());
            guardFrontendStep('bootstrap.agent_version', () => refreshLatestAgentVersion());
            guardFrontendStep('bootstrap.server_compact', () => refreshDashboardServerCompactFallback());
            const userBadge = document.getElementById('top-user-badge');
            if (userBadge) {
                userBadge.addEventListener('click', event => {
                    event.stopPropagation();
                    toggleUserMenu();
                });
            }
            const userMenu = document.getElementById('top-user-menu');
            if (userMenu) {
                userMenu.addEventListener('click', event => {
                    event.stopPropagation();
                });
            }
            document.addEventListener('click', event => {
                const menu = document.getElementById('top-user-menu');
                const badge = document.getElementById('top-user-badge');
                if (!menu || !badge) return;
                if (!badge.contains(event.target)) toggleUserMenu(false);
                if (!event.target.closest('.hvac-temp-panel')) closeHvacTempControls();
                if (!event.target.closest('.hvac-metric.mode')) closeHvacModeMenus();
            });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape') {
                    toggleUserMenu(false);
                    closeHvacTempControls();
                    closeHvacModeMenus();
                }
            });
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) stopNvrPreviewStreams();
                refreshPollingVisibility();
            });
            window.addEventListener('focus', () => {
                refreshPollingVisibility();
            });
            window.addEventListener('beforeunload', () => {
                stopNvrPreviewStreams();
                stopDoorVideoStream();
                stopAllPollingTasks();
            });
            const firstNav = document.querySelector('.nav-menu li.active');
            guardFrontendStep('bootstrap.first_nav', () => {
                const navItems = Array.from(document.querySelectorAll('.nav-menu li'));
	                const initialView = getInitialViewFromUrl();
	                if (initialView) {
                        if (initialView === 'snmp') restoreSnmpSelectedDeviceFromUrl();
	                    const targetNav = findNavElementByView(initialView);
	                    switchTab(initialView, getViewTitleFromNav(targetNav, '中控系统'), targetNav);
	                    return;
	                }
                const dashboardNav = navItems.find(el => String(el.getAttribute('onclick') || '').includes("switchTab('dashboard'"));
                const initialNav = dashboardNav || firstNav || null;
                if (initialNav) {
                    const onclickText = String(initialNav.getAttribute('onclick') || '');
                    const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
                    if (match) {
                        switchTab(match[1], match[2], initialNav);
                        return;
                    }
                }
                switchTab('dashboard', '场馆总览', initialNav);
            }, '默认页面初始化异常，已切换为降级启动');
            if (getActiveViewId() === 'door') {
                setTimeout(() => {
                    guardFrontendStep('bootstrap.door_init', () => {
                        initCanvas();
                        updateDoorStatus(true).finally(() => startDoorVideoStream());
                    });
                }, 180);
            }
            window.addEventListener('resize', () => {
                applyAdaptiveDensity();
                scheduleDashboardMasonry(120);
                if (window.innerWidth > 760) closeSidebar();
            });
            guardFrontendStep('bootstrap.start_polling', () => startAppPolling(), '页面轮询启动失败，请查看系统日志');
        });

        registerPollingTask('power', 3500, () => updatePowerData(), () => ['dashboard', 'power'].includes(getActiveViewId()) || isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick'));
        registerPollingTask('meter', 4500, () => updateMeterCenter(), () => ['dashboard', 'meter'].includes(getActiveViewId()) || isDashboardSectionVisible('meter'));
        registerPollingTask('ups', 4500, () => updateUpsStatus(), () => ['dashboard', 'ups'].includes(getActiveViewId()) || isDashboardSectionVisible('ups_compact') || isDashboardSectionVisible('ups'));
        registerPollingTask('hy_edge', 6000, () => updateHyEdgeStatus(), () => ['dashboard'].includes(getActiveViewId()) || isDashboardSectionVisible('hy_edge'));
        registerPollingTask('dashboard_summary', 5000, () => updateDashboardSummary(), () => getActiveViewId() === 'dashboard' || isDashboardSectionVisible('stats'));
        registerPollingTask('proxy', 5000, () => ensureViewReady('proxy').then(() => updateProxyStatus()), () => getActiveViewId() === 'proxy');
        registerPollingTask('snmp', 9000, () => updateSnmpStatus(), () => ['dashboard', 'snmp', 'camera_preview'].includes(getActiveViewId()) || isDashboardSectionVisible('snmp'));
        registerPollingTask('hvac', 5000, () => {
            const modules = getActiveViewId() === 'hvac' ? ['hvac-view'] : ['hvac-summary-view'];
            return ensureModulesReady(modules, '空调模块').then(() => updateHvacStatus());
        }, () => getActiveViewId() === 'hvac' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('hvac')));
        registerPollingTask('light', 2200, () => updateLightData(), () => ['dashboard', 'light'].includes(getActiveViewId()) || isDashboardSectionVisible('light_compact') || isDashboardSectionVisible('light'));
        registerPollingTask('node_red', 5000, () => ensureViewReady('universal').then(() => updateNodeRedDevices()), () => getActiveViewId() === 'universal');
        registerPollingTask('server', 5000, () => ensureViewReady('server').then(() => updateServerData()), () => getActiveViewId() === 'server');
        registerPollingTask('door', 1200, () => updateDoorStatus(), () => ['dashboard', 'door'].includes(getActiveViewId()) || isDashboardSectionVisible('door'));
        registerPollingTask('env', 3500, () => updateEnvData(), () => ['dashboard', 'env', 'hvac'].includes(getActiveViewId()) || isDashboardSectionVisible('env') || isDashboardSectionVisible('hvac'));
        registerPollingTask('automation', 4000, () => {
            loadAutomationStatus();
            if (getActiveViewId() === 'auto') loadAutomationLogs();
        }, () => ['dashboard', 'auto'].includes(getActiveViewId()));
        registerPollingTask('projector', 6000, () => {
            const modules = getActiveViewId() === 'projector' ? ['projector-view'] : ['projector-summary-view'];
            return ensureModulesReady(modules, '投影模块').then(() => updateProjectorStatus());
        }, () => getActiveViewId() === 'projector' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('projector')));
        registerPollingTask('sequencer', 4500, () => updateSequencerStatus(), () => ['dashboard', 'sequencer'].includes(getActiveViewId()) || isDashboardSectionVisible('sequencer'));
        registerPollingTask('screen', 4500, () => updateScreenStatus(), () => ['dashboard', 'screen'].includes(getActiveViewId()) || isDashboardSectionVisible('screen'));
        registerPollingTask('apple_audio', 3200, () => ensureViewReady('apple_audio').then(() => loadAppleAudioStatus()), () => ['apple_audio'].includes(getActiveViewId()));
        registerPollingTask('logs', 5000, () => updateDashboardLogs(), () => getActiveViewId() === 'dashboard');
        registerPollingTask('event_logs', 5000, () => refreshEventLogs(false), () => getActiveViewId() === 'logs');

        function saveDoorRegionSelection(regionPayload) {
            return fetchJsonLoose('/update_door_region', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(regionPayload)
            }, '保存检测区域失败').then(data => {
                showToast(data.msg || '检测区域已更新', data.status === 'error');
                if (data.status === 'error') {
                    throw new Error(data.msg || '保存检测区域失败');
                }
                return data;
            });
        }

        function requestDoorStatus() {
            return fetchJsonLoose('/get_door_status', {}, '读取门禁状态失败');
        }

        function postDoorAction(action) {
            return fetchJsonLoose(`/door_control/${action}`, {}, '门禁指令下发失败');
        }

        refreshPowerSupplement = function(cabId, force = false) {
            const now = Date.now();
            const activeView = getActiveViewId();
            const minInterval = activeView === 'power' ? 15000 : 45000;
            if (!force && powerSupplementFetchAt[cabId] && (now - powerSupplementFetchAt[cabId] < minInterval)) return;
            if (powerSupplementInFlight[cabId]) return powerSupplementInFlight[cabId];
            powerSupplementFetchAt[cabId] = now;
            const logsReq = fetchJson(`/api/logs?cab=${cabId}`, {}, '强电日志读取失败')
                .then(logs => {
                    powerLogCache[cabId] = Array.isArray(logs) ? logs : [];
                    renderPowerDetailLogs(cabId, powerLogCache[cabId]);
                })
                .catch(err => console.error('强电日志更新失败', cabId, err));
            const historyReq = fetchJson(`/api/7days_energy?cab=${cabId}`, {}, '强电图表读取失败')
                .then(data => {
                    powerHistoryCache[cabId] = Array.isArray(data) ? data : [];
                    renderPowerEnergyChart(cabId, powerHistoryCache[cabId]);
                })
                .catch(err => console.error('强电图表更新失败', cabId, err));
            powerSupplementInFlight[cabId] = Promise.allSettled([logsReq, historyReq])
                .then(() => {
                    renderDashboardPowerCards();
                })
                .finally(() => {
                    delete powerSupplementInFlight[cabId];
                });
            return powerSupplementInFlight[cabId];
        };

        updateMeterCenter = function() {
            const requestSeq = ++meterCenterRequestSeq;
            const requestTarget = meterTrendTarget;
            const requestPeriod = meterTrendPeriod;
            fetchJson(`/api/meters?target=${encodeURIComponent(meterTrendTarget)}&period=${encodeURIComponent(meterTrendPeriod)}&days=35`, {}, '电表中心状态读取失败')
                .then(data => {
                    if (requestSeq !== meterCenterRequestSeq || requestTarget !== meterTrendTarget || requestPeriod !== meterTrendPeriod) return;
                    meterCenterCache = data || { summary: {}, meters: [], trend: [] };
                    const summary = meterCenterCache.summary || {};
                    const meters = normalizeMeterCardOrder(Array.isArray(meterCenterCache.meters) ? meterCenterCache.meters : []);
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
                    const cardTotalPower = Number(
                        summary.card_total_realtime_power
                        ?? summary.stable_total_realtime_power
                        ?? summary.estimated_total_realtime_power
                        ?? summary.total_realtime_power
                        ?? 0
                    );
                    if (powerEl) powerEl.innerText = cardTotalPower.toFixed(2);
                    if (dailyEl) dailyEl.innerText = Number(summary.total_daily_energy || 0).toFixed(1);
                    if (monthlyEl) monthlyEl.innerText = Number(summary.total_monthly_energy || 0).toFixed(1) + ' kWh';
                    if (displayBadge) {
                        const mode = String((configData.meter_statistics || {}).energy_display_mode || 'display').toLowerCase();
                        displayBadge.innerText = mode === 'raw' ? '原始累计值' : '运行口径';
                    }
                    if (scopeBadge) scopeBadge.innerText = `${Number(summary.online || 0)} / ${Number(summary.total || 0)} 在线`;
                    if (sourceBadge) {
                        const sourceMeta = resolveMeterSourceMeta(meterCenterCache);
                        sourceBadge.innerText = sourceMeta.text;
                        sourceBadge.title = sourceMeta.title || '';
                        sourceBadge.style.color = sourceMeta.color || '#f8fafc';
                    }
                    const dashPower = document.getElementById('dash-total-power');
                    const dashDaily = document.getElementById('dash-total-daily-energy');
                    const dashPowerMeta = document.getElementById('dash-total-power-meta');
                    const dashDailyMeta = document.getElementById('dash-total-daily-meta');
                    const dashStablePower = Number(
                        (meterCenterCache.dashboard_summary || {}).stable_power
                        ?? (meterCenterCache.dashboard_summary || {}).estimated_power
                        ?? (meterCenterCache.dashboard_summary || {}).power
                        ?? cardTotalPower
                        ?? 0
                    );
                    if (dashPower) dashPower.innerText = dashStablePower.toFixed(2);
                    if (dashDaily) dashDaily.innerText = Number((meterCenterCache.dashboard_summary || {}).daily_energy || 0).toFixed(1);
                    const compareToReference = (summary.compare_to_reference || {});
                    if (powerMetaEl) powerMetaEl.innerHTML = formatPowerSummaryMeta(summary);
                    if (dailyMetaEl) dailyMetaEl.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                    if (monthlyMetaEl) monthlyMetaEl.innerHTML = formatReferenceMeta(compareToReference.monthly_energy, ' kWh');
                    if (dashPowerMeta) dashPowerMeta.innerHTML = `单位 kW · ${formatPowerSummaryMeta(summary)}`;
                    if (dashDailyMeta) dashDailyMeta.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                    renderMeterTypeChips(summary.type_counts || {});
                    renderMeterTrendSelectors(meterCenterCache);
                    if (grid) {
                        grid.innerHTML = meters.length
                            ? meters.map(renderMeterCard).join('')
                            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">暂无可展示电表数据</div>';
                    }
                    const trendRows = (((meterCenterCache.trend_breakdown || {})[meterTrendPeriod === 'week' ? 'weekly' : (meterTrendPeriod === 'month' ? 'monthly' : 'daily')]) || []);
                    renderMeterTrendChart(trendRows);
                    renderDashboardEnergyTrend(trendRows, summary);
                })
                .catch(err => console.error('电表中心状态更新失败', err));
        };

        updateSequencerStatus = function() {
            fetchJson('/api/sequencer/status', {}, '时序电源状态读取失败')
                .then(data => {
                    sequencerStatusCache = data || {};
                    renderSequencerCards();
                })
                .catch(err => console.error('时序电源状态更新失败', err));
        };

        fireSequencerAction = function(id, action, channel = null) {
            if (!ensurePermission('sequencer.control', '操作时序电源')) return;
            showToast('时序电源指令下发中...', false);
            postJsonLoose('/api/sequencer/control', { id, action, channel }, '时序电源指令下发失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '执行失败', true);
                        return;
                    }
                    showToast(`执行成功${data.command ? ' - ' + data.command : ''}`);
                    if (data.device && Array.isArray(data.device.channels)) {
                        sequencerStatusCache = sequencerStatusCache || {};
                        sequencerStatusCache.devices = Array.isArray(sequencerStatusCache.devices) ? sequencerStatusCache.devices : [];
                        const idx = sequencerStatusCache.devices.findIndex(item => item && item.id === data.device.id);
                        if (idx >= 0) sequencerStatusCache.devices[idx] = data.device;
                        else sequencerStatusCache.devices.push(data.device);
                        renderSequencerCards();
                    }
                    [350, 900, 1800, 3500].forEach(delay => setTimeout(updateSequencerStatus, delay));
                    setTimeout(updateDashboardLogs, 300);
                })
                .catch(err => showToast(translateApiError(err?.message, '网络请求失败'), true));
        };

        updateDoorStatus = function(force = false) {
            const now = Date.now();
            if (!force && now - lastDoorStatusFetchAt < 1000) return Promise.resolve(null);
            lastDoorStatusFetchAt = now;
            return requestDoorStatus()
                .then(data => {
                    if (data.status !== 'success') return null;
                    const cameraMap = {};
                    (Array.isArray(data.cameras) ? data.cameras : []).forEach(item => {
                        const key = String(item?.key || '').trim();
                        if (key) cameraMap[key] = item;
                    });
                    doorCameraStatusCache = cameraMap;
                    if (data.view_slots && typeof data.view_slots === 'object') doorViewSlots = data.view_slots;
                    if (data.regions && typeof data.regions === 'object') doorRegionsCache = data.regions;
                    const leftCameraKey = getDoorSlotCameraKey('left');
                    const rightCameraKey = getDoorSlotCameraKey('right');
                    setDoorSlotVisual('left', cameraMap[leftCameraKey] || {});
                    setDoorSlotVisual('right', cameraMap[rightCameraKey] || {});
                    updateDoorSlotLabels();
                    renderDoorNetworkSummary();
                    syncDoorVideoSources(force);
                    const statusEl = document.getElementById('doorStatus');
                    if (statusEl) {
                        statusEl.textContent = data.msg;
                        statusEl.className = `tag door-status-${data.door_status}`;
                    }
                    const debugTip = document.getElementById('debugTip');
                    if (debugTip) {
                        const offlineCount = Object.values(cameraMap).filter(item => item && item.online === false && item.configured).length;
                        debugTip.textContent = offlineCount > 0 ? `视觉辅助，${offlineCount} 路视频链路异常 | ${data.diff}` : `视觉辅助识别 | ${data.diff}`;
                    }
                    if (!updateDashboardDoorStatusFromEnv()) updateDashboardDoorStatusFromVision(data);
                    return data;
                })
                .catch(() => {
                    const statusEl = document.getElementById('doorStatus');
                    if (statusEl) statusEl.textContent = '检测器离线';
                    setDoorSlotVisual('left', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                    setDoorSlotVisual('right', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                    renderDoorNetworkSummary();
                    return null;
                });
        };

        captureWizard = function(state, statusId) {
            const btn = event.target;
            const oldText = btn.innerHTML;
            btn.innerHTML = '正在保存...';
            btn.disabled = true;
            fetchJsonLoose(`/api/ai_wizard/capture/${state}`, { method: 'POST' }, '拍照保存失败')
                .then(data => {
                    showToast(data.msg || '拍照完成', data.status === 'error');
                    if (data.status === 'success') {
                        const statusSpan = document.getElementById(statusId);
                        if (statusSpan) {
                            statusSpan.innerHTML = '已保存';
                            statusSpan.style.color = 'var(--success)';
                        }
                        if (state === 'closed') {
                            document.getElementById('step1-card').style.opacity = '0.4';
                            document.getElementById('step1-card').style.pointerEvents = 'none';
                            document.getElementById('step2-card').style.opacity = '1';
                            document.getElementById('step2-card').style.pointerEvents = 'auto';
                        }
                    }
                })
                .catch(() => showToast('拍照保存失败', true))
                .finally(() => {
                    btn.innerHTML = oldText;
                    btn.disabled = false;
                });
        };

        applyAiCalibration = function() {
            const btn = document.getElementById('btnWizardRecord');
            btn.textContent = '正在提取并计算...';
            btn.disabled = true;
            fetchJsonLoose('/api/ai_wizard/apply_model', { method: 'POST' }, '生成模型失败')
                .then(data => {
                    showToast(data.msg || '模型生成完成', data.status === 'error');
                    if (data.status === 'success') setTimeout(closeWizard, 1500);
                })
                .catch(() => showToast('生成模型失败', true))
                .finally(() => {
                    btn.disabled = false;
                    btn.innerHTML = '一键生成 AI 推演模型';
                });
        };

        controlDoor = function(action) {
            if (!ensurePermission('door.control', '控制门禁')) return;
            postDoorAction(action)
                .then(data => showToast(data.msg || '门禁指令已下发', data.status === 'error'))
                .catch(() => showToast('指令下发失败', true));
        };

        doPowerStart = function(cabId) {
            if (!ensurePermission('power.control', '执行强电启动')) return;
            setPowerCabinetDesiredState(cabId, true);
            fetchJsonLoose(`/api/onekey_start?cab=${cabId}`, {}, '启动请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerCabinetDesiredState(cabId);
                        showToast(data.msg || '启动失败', true);
                        return;
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    showToast(data.verified === false ? (data.msg || '启动指令已下发，状态稍后刷新') : '启动指令已发送');
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerCabinetDesiredState(cabId);
                    showToast(translateApiError(err?.message, '启动请求失败'), true);
                });
        };

        doPowerStop = function(cabId, msg) {
            if (!ensurePermission('power.control', '执行强电停止')) return;
            if (!confirm(msg)) return;
            setPowerCabinetDesiredState(cabId, false);
            fetchJsonLoose(`/api/onekey_stop?cab=${cabId}`, {}, '停止请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerCabinetDesiredState(cabId);
                        showToast(data.msg || '停止失败', true);
                        return;
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    showToast(data.verified === false ? (data.msg || '停止指令已下发，状态稍后刷新') : '停止指令已下发');
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerCabinetDesiredState(cabId);
                    showToast(translateApiError(err?.message, '停止请求失败'), true);
                });
        };

        togglePower = function(cabId, chNum) {
            if (!ensurePermission('power.control', '切换强电通道')) return;
            pwrPending[cabId] = pwrPending[cabId] || {};
            if (pwrPending[cabId][chNum]) {
                showToast('该回路正在执行中，请等待状态确认');
                return;
            }
            const status = getPowerChannelStatus(cabId, chNum);
            if (status === null) return;
            if (status && !confirm(configData.cabinets[cabId].ui_text.confirm_single_off)) return;
            const targetState = !status;
            pwrLocks[cabId][chNum] = Date.now();
            pwrPending[cabId][chNum] = true;
            setPowerDesiredState(cabId, chNum, targetState);
            renderPwrChannel(cabId, chNum);
            postJsonLoose('/api/set', { cab: cabId, ch: chNum, on: targetState }, '强电控制请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerDesiredState(cabId, chNum);
                        renderPwrChannel(cabId, chNum);
                        showToast(data.msg || '强电控制失败', true);
                        return;
                    }
                    if (data.verified === false && data.msg) {
                        showToast(data.msg);
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerDesiredState(cabId, chNum);
                    renderPwrChannel(cabId, chNum);
                    showToast(translateApiError(err?.message, '强电控制请求失败'), true);
                })
                .finally(() => {
                    delete pwrPending[cabId][chNum];
                    renderPwrChannel(cabId, chNum);
                    setTimeout(() => { delete pwrLocks[cabId][chNum]; }, POWER_CHANNEL_LOCK_MS);
                });
        };

        updatePowerData = async function() {
            if (powerFetchInFlight) return powerFetchInFlight;
            powerFetchInFlight = (async () => {
            let onlineCount = 0;
            const activeView = getActiveViewId();
            const shouldLoadDetails = activeView === 'power';
            const shouldLoadDashboard = activeView === 'dashboard' || isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick');
            const supplementCabIds = resolveVisiblePowerSupplementCabIds(activeView);
            const supplementCabIdSet = new Set(supplementCabIds);
            const cabinetEntries = Array.isArray(configData.cabinets) ? Array.from(configData.cabinets.entries()) : [];
            const responses = [];
            for (const [cabId] of cabinetEntries) {
                try {
                    const d = await fetchJson(`/api/status?cab=${cabId}`, {}, '强电状态读取失败');
                    responses.push({ cabId, data: d, error: null });
                } catch (err) {
                    responses.push({ cabId, data: null, error: err });
                }
            }
            for (const [cabId, cab] of cabinetEntries) {
                const result = responses.find(item => item.cabId === cabId) || {};
                const d = result.data;
                if (!d) {
                    console.error('强电状态更新失败', cabId, result.error);
                    continue;
                }
                try {
                    applyPowerStatusSnapshot(cabId, d);
                    if (d.comm_status) onlineCount++;
                    const statusEl = document.getElementById(`commStatus_${cabId}`);
                    if (statusEl) {
                        statusEl.className = d.comm_status ? 'tag normal' : 'tag error';
                        statusEl.innerText = d.comm_status ? '通讯正常' : '通讯异常';
                    }
                    const wm = document.getElementById(`workMode_${cabId}`);
                    if (wm) wm.innerText = d.work_mode || '未知';
                    const sourceLabelEl = document.getElementById(`sourceLabel_${cabId}`);
                    if (sourceLabelEl) sourceLabelEl.innerText = d.source_label || (d.data_source || '电表服务');
                    const displayAddressEl = document.getElementById(`displayAddress_${cabId}`);
                    if (displayAddressEl) displayAddressEl.innerText = d.display_address || d.gateway_base || `${cab.ip}:${cab.port}`;
                    const deviceAddressEl = document.getElementById(`deviceAddress_${cabId}`);
                    if (deviceAddressEl) deviceAddressEl.innerText = d.device_address || `${cab.ip}:${cab.port}`;
                    ['va','vb','vc','ia','ib','ic','energy','dailyEnergy','monthEnergy','realtimePower','temp','humi'].forEach(k => {
                        const el = document.getElementById(`${k}_${cabId}`);
                        const val = d[k === 'energy'
                            ? 'electric_energy'
                            : (k === 'dailyEnergy'
                                ? 'daily_energy'
                                : (k === 'monthEnergy'
                                    ? 'monthly_energy'
                                    : (k === 'realtimePower'
                                        ? 'realtime_power'
                                        : (k === 'temp'
                                            ? 'cabinet_temp'
                                            : (k === 'humi'
                                                ? 'cabinet_humidity'
                                                : k.replace('v', 'voltage_').replace('i', 'current_'))))))];
                        if (el && val !== undefined) {
                            el.innerText = parseFloat(val).toFixed(k.includes('i') || k.includes('v') || k === 'temp' || k === 'humi' || k.includes('Energy') ? 1 : 2);
                        }
                    });
                } catch (err) {
                    console.error('强电状态更新失败', cabId, err);
                }
            }
            const supplementChanged =
                supplementCabIds.length !== powerVisibleSupplementCabIds.length
                || supplementCabIds.some((cabId, idx) => cabId !== powerVisibleSupplementCabIds[idx]);
            if (shouldLoadDetails || shouldLoadDashboard) {
                for (const cabId of supplementCabIds) {
                    refreshPowerSupplement(cabId, supplementChanged);
                }
            }
            for (const oldCabId of powerVisibleSupplementCabIds) {
                if (!supplementCabIdSet.has(oldCabId)) {
                    delete powerSupplementInFlight[oldCabId];
                }
            }
            powerVisibleSupplementCabIds = supplementCabIds.slice();
            renderDashboardPowerCards();
            renderDashboardPowerCompact();
            const pOnline = document.getElementById('dash-power-online');
            if (pOnline) pOnline.innerText = onlineCount;
            resizePowerCharts();
            })();
            try {
                return await powerFetchInFlight;
            } finally {
                powerFetchInFlight = null;
            }
        };

        toggleLight = function(devId, chNum) {
            if (!ensurePermission('light.control', '切换灯光通道')) return;
            if (!lightOnlineStates[devId]) {
                showToast('设备离线，无法控制通道', true);
                return;
            }
            const rawStatus = getLightChannelStateFromSources(devId, chNum, {});
            const status = getLightChannelStateFromSources(devId, chNum, {});
            if (status === null || status === undefined) {
                showToast('设备在线，但该通道状态待确认，请稍后再试或使用动作按钮', true);
                return;
            }
            const targetState = !status;
            lightLocks[devId][chNum] = Date.now();
            lightStates[devId][chNum] = targetState;
            renderLightChannel(devId, chNum);
            postJsonLoose('/api/light/control', { type: 'single', device_id: devId, channel: chNum, is_open: targetState }, '灯光控制请求失败')
                .then(data => {
                    if (!data.success) {
                        lightStates[devId][chNum] = rawStatus;
                        renderLightChannel(devId, chNum);
                        showToast(data.msg || '灯光控制失败', true);
                        return;
                    }
                    if (Array.isArray(data.channels)) {
                        data.channels.forEach((st, idx) => {
                            lightStates[devId][idx + 1] = st;
                            renderLightChannel(devId, idx + 1);
                        });
                    }
                    showToast(data.verified === false ? '灯光指令已发送，等待状态确认' : '灯光控制成功');
                    setTimeout(() => updateLightData(), 600);
                })
                .catch(() => {
                    lightStates[devId][chNum] = rawStatus;
                    renderLightChannel(devId, chNum);
                    showToast('灯光控制请求失败', true);
                })
                .finally(() => {
                    setTimeout(() => { delete lightLocks[devId][chNum]; }, 1200);
                });
        };

        triggerLightAction = function(devId, actionName, label) {
            if (!ensurePermission('light.control', `执行灯光动作 ${label || actionName}`)) return;
            postJsonLoose('/api/light/control', { type: 'action', device_id: devId, action: actionName }, `${label || actionName} 请求失败`)
                .then(data => {
                    if (!data.success) {
                        showToast(data.msg || `${label || actionName} 执行失败`, true);
                        return;
                    }
                    if (Array.isArray(data.channels)) {
                        data.channels.forEach((st, idx) => {
                            lightStates[devId][idx + 1] = st;
                            renderLightChannel(devId, idx + 1);
                        });
                    }
                    showToast(data.verified === false ? `${label || actionName} 已下发，等待状态确认` : `${label || actionName} 已执行`);
                    setTimeout(() => updateLightData(), 700);
                })
                .catch(() => showToast(`${label || actionName} 请求失败`, true));
        };

        executeScene = function(sceneId, name) {
            if (!ensurePermission('light.control', '执行场景联动')) return;
            if (!confirm(`确定要触发全局联动场景 [${name}] 吗？`)) return;
            postJsonLoose('/api/light/control', { type: 'scene', scene_id: sceneId }, `场景联动 [${name}] 请求失败`)
                .then(data => {
                    if (!data.success) {
                        showToast(data.msg || `场景联动 [${name}] 执行失败`, true);
                        return;
                    }
                    showToast(`场景联动 [${name}] 触发成功`);
                    setTimeout(() => updateLightData(), 800);
                })
                .catch(() => showToast(`场景联动 [${name}] 请求失败`, true));
        };

        updateLightData = function() {
            fetchJson('/api/light/status', {}, '灯光状态读取失败')
                .then(d => {
                    let onlineCount = 0;
                    for (const devId in (d.online || {})) {
                        const extraMeta = (d.extras || {})[devId] || {};
                        const statusMeta = getDeviceStatusMeta({
                            online: !!d.online[devId],
                            status_level: extraMeta.status_level,
                            stale: extraMeta.stale,
                            poll_failures: extraMeta.poll_failures,
                            last_success_at: extraMeta.last_success_at,
                            last_checked_at: extraMeta.last_checked_at,
                            last_error: extraMeta.last_error,
                        }, { staleText: '陈旧', errorText: '异常' });
                        lightOnlineStates[devId] = statusMeta.isOnlineLike;
                        if (statusMeta.isOnlineLike) onlineCount++;
                        const tag = document.getElementById(`light-status-${devId}`);
                        if (tag) {
                            tag.className = statusMeta.chipClass === 'online' ? 'tag normal' : (statusMeta.chipClass === 'warning' ? 'tag warn' : 'tag error');
                            tag.innerText = statusMeta.text;
                            tag.title = statusMeta.note;
                        }
                        (d.channels?.[devId] || []).forEach((st, idx) => {
                            const chNum = idx + 1;
                            if (lightLocks[devId][chNum] && (Date.now() - lightLocks[devId][chNum] < 2000)) return;
                            lightStates[devId][chNum] = st;
                            renderLightChannel(devId, chNum);
                        });
                        const inputStates = Array.isArray(extraMeta.inputs) ? extraMeta.inputs : [];
                        lightInputStates[devId] = inputStates;
                        inputStates.forEach((st, idx) => {
                            renderLightInput(devId, idx + 1);
                        });
                    }
                    const lOnline = document.getElementById('dash-light-online');
                    if (lOnline) lOnline.innerText = onlineCount;
                    renderDashboardLightCards(d);
                    renderDashboardLightCompact(d);
                })
                .catch(err => console.error('灯光状态更新失败', err));
            fetchJson('/api/light/logs', {}, '灯光日志读取失败')
                .then(logs => {
                    const logBox = document.getElementById('light-global-log');
                    if (!logBox) return;
                    let html = '';
                    (logs || []).forEach(log => {
                        html += `<div class="log-item"><span class="time">[${new Date(log.time).toLocaleTimeString('zh-CN',{hour12:false})}]</span><span class="msg">${log.operation.replace(/\[.*?\]\s*/,'')}</span></div>`;
                    });
                    if (logBox.innerHTML !== html) logBox.innerHTML = html;
                })
                .catch(err => console.error('灯光日志更新失败', err));
        };

        wakeServer = function(mac) {
            if (!ensurePermission('server.control', '唤醒服务器节点')) return;
            if (mac.startsWith('TEMP')) {
                showToast('没有真实 MAC 地址，无法发送网络唤醒', true);
                return;
            }
            if (!confirm('确定发送网络唤醒魔术包(WOL)吗？')) return;
            fetchJson('/api/wake/' + encodeURIComponent(mac), { method: 'POST' }, '唤醒请求失败')
                .then(result => {
                    const targets = Array.isArray(result?.targets) ? result.targets.length : 0;
                    showToast(targets ? `唤醒包已发出，广播目标 ${targets} 个` : '唤醒包已发出');
                    if (typeof burstRefreshServerData === 'function') burstRefreshServerData();
                })
                .catch(err => showToast(translateApiError(err?.message, '唤醒请求失败'), true));
        };

        sendServerCmd = function(mac, cmd) {
            if (!ensurePermission('server.control', '下发服务器指令')) return;
            const actionMap = { shutdown: '关机', restart: '重启', refresh: '刷新信息' };
            const actionName = actionMap[cmd] || cmd;
            const prompt = cmd === 'refresh' ? '确定要远程刷新此节点的硬件信息吗？' : `危险操作：确定要让此节点立刻【${actionName}】吗？`;
            if (!confirm(prompt)) return;
            postJsonLoose(`/api/machines/${mac}/command`, { command: cmd }, `指令 [${actionName}] 下发失败`)
                .then(() => {
                    markServerCommandPending(mac, cmd, actionName);
                    showToast(`指令 [${actionName}] 已进入下发队列`);
                    burstRefreshServerData();
                })
                .catch(err => showToast(translateApiError(err?.message, `指令 [${actionName}] 下发失败`), true));
        };

        moveServer = function(mac, direction) {
            if (!ensurePermission('server.control', '调整服务器排序')) return;
            const idx = globalServerList.findIndex(m => m.mac === mac);
            if (idx < 0) return;
            const newIdx = idx + direction;
            if (newIdx < 0 || newIdx >= globalServerList.length) return;
            const temp = globalServerList[idx];
            globalServerList[idx] = globalServerList[newIdx];
            globalServerList[newIdx] = temp;
            globalServerList.forEach((m, i) => { m.sort_order = i + 1; });
            renderServerGridDeferred(globalServerList, { force: true });
            renderDashboardServerCompactWhenReady(globalServerList);
            postJsonLoose('/api/machines/sort', { macs: globalServerList.map(m => m.mac) }, '服务器排序保存失败')
                .then(() => updateServerData())
                .catch(err => {
                    showToast(translateApiError(err?.message, '服务器排序保存失败'), true);
                    updateServerData();
                });
        };

        function formatServerMetric(value, suffix = '%') {
            const api = getServerSummaryApi();
            if (api && typeof api.formatServerMetric === 'function') {
                return api.formatServerMetric.apply(api, Array.from(arguments));
            }
            const num = Number(value);
            if (!Number.isFinite(num)) return `0${suffix}`;
            return `${num.toFixed(num % 1 ? 1 : 0)}${suffix}`;
        }
        function normalizeServerBytes(value) {
            const api = getServerSummaryApi();
            if (api && typeof api.normalizeServerBytes === 'function') {
                return api.normalizeServerBytes.apply(api, Array.from(arguments));
            }
            const num = Number(value);
            return Number.isFinite(num) ? num : 0;
        }
        function formatNetworkMbps(kbPerSec) {
            return SmartCenter.serverMonitor.formatNetworkMbps.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        let serverViewMode = (() => {
            try { return localStorage.getItem('smart-center-server-view-mode') || 'compact'; } catch (_) { return 'compact'; }
        })();
        let serverGridRenderToken = 0;
        let serverGridSignature = '';
        let serverDataRequestInFlight = null;
        function getServerGridSignature(machines) {
            try {
                return JSON.stringify((Array.isArray(machines) ? machines : []).map(m => [
                    m.mac,
                    m.is_online,
                    m.report_online,
                    m.runtime_fresh,
                    m.last_online,
                    m.server_received_at,
                    m.clock_offset_sec,
                    m.last_report_kind,
                    m.sort_order,
                    m.card_size,
                    m.remark,
                    m.status?.hardware_refreshed_at,
                    m.status?.clock_heartbeat_at,
                    m.agent_status?.version,
                    m.diagnostic?.code,
                    m.pending_power_command?.command,
                    m.claimed_power_command?.command
                ]));
            } catch (_) {
                return String(Date.now());
            }
        }
        function renderServerGridDeferred(machines, options = {}) {
            const container = document.getElementById('server-grid-container');
            if (!container || !window.SmartCenter?.serverMonitor) return;
            const signature = serverViewMode + '|' + getServerGridSignature(machines);
            if (!options.force && signature === serverGridSignature) return;
            serverGridSignature = signature;
            const token = ++serverGridRenderToken;
            const renderNow = () => {
                if (token !== serverGridRenderToken) return;
                container.innerHTML = renderServerGroupedGrid(machines);
            };
            if (typeof window.requestAnimationFrame === 'function') {
                window.requestAnimationFrame(() => window.requestAnimationFrame(renderNow));
            } else {
                window.setTimeout(renderNow, 0);
            }
        }
        function applyServerViewMode(mode) {
            serverViewMode = mode === 'detail' ? 'detail' : 'compact';
            document.querySelectorAll('[data-server-view-mode]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.serverViewMode === serverViewMode);
                btn.setAttribute('aria-pressed', btn.dataset.serverViewMode === serverViewMode ? 'true' : 'false');
            });
            const modeLabel = document.getElementById('server-mode-current');
            if (modeLabel) modeLabel.textContent = serverViewMode === 'detail' ? '详细模式' : '简洁模式';
            const container = document.getElementById('server-grid-container');
            if (container) container.classList.toggle('server-detail-mode', serverViewMode === 'detail');
        }
        function setServerViewMode(mode) {
            applyServerViewMode(mode);
            try { localStorage.setItem('smart-center-server-view-mode', serverViewMode); } catch (_) {}
            if (Array.isArray(globalServerList) && globalServerList.length) {
                renderServerGridDeferred(globalServerList, { force: true });
            }
        }
        function csvCell(value) {
            const text = String(value ?? '').replace(/\r?\n/g, ' ').trim();
            return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
        }
        function exportListCell(items) {
            return (items || []).map(item => String(item ?? '').trim()).filter(Boolean).join(' | ');
        }
        function getServerDeviceInfoExportRows() {
            const rows = [];
            const list = Array.isArray(globalServerList) ? globalServerList : [];
            list.forEach(machine => {
                const st = machine.status || {};
                const network = st.network_summary || {};
                const wifi = st.wireless || {};
                const bt = st.bluetooth || {};
                const adapters = Array.isArray(st.network_adapters) ? st.network_adapters.filter(adapter => !adapter?.is_virtual) : [];
                const codemeter = st.codemeter && typeof st.codemeter === 'object' ? st.codemeter : {};
                const codemeterSerials = getCodeMeterSerials(codemeter);
                const codemeterLicenses = normalizeCodeMeterLicenses(codemeter, codemeterSerials);
                const codemeterValidity = getCodeMeterValidityText(codemeter);
                const codemeterLabel = getCodeMeterLicenseLabel(codemeter);
                const codemeterInstalled = codemeter.installed === true ? '已安装' : (codemeter.installed === false ? '未安装' : '');
                const codemeterRunning = codemeter.running === true ? '运行中' : (codemeter.running === false ? '未运行' : '');
                const licenseRows = codemeterLicenses.length ? codemeterLicenses : [];
                const nearestExpiringLicense = licenseRows
                    .filter(license => !license.permanent && license.expiryText)
                    .slice()
                    .sort((a, b) => String(a.expiryText || '').localeCompare(String(b.expiryText || '')))[0];
                const adapterRows = adapters.map((adapter, index) => {
                    const ips = Array.isArray(adapter?.ipv4) ? adapter.ipv4 : [adapter?.adapter_ip, adapter?.ip, adapter?.ipv4].filter(Boolean);
                    const name = adapter?.description || adapter?.adapter_description || adapter?.name || adapter?.adapter_name || '';
                    const mac = normalizeDisplayMac(adapter?.adapter_mac || adapter?.mac || adapter?.physical_mac || adapter?.address);
                    const speed = adapter?.speed_mbps || adapter?.link_speed_mbps || adapter?.speed || '';
                    const state = adapter?.state || adapter?.status || '';
                    const prefix = `${index + 1}.`;
                    return {
                        name: name ? `${prefix} ${name}` : '',
                        ip: ips.length ? `${prefix} ${ips.join(' / ')}` : '',
                        mac: mac ? `${prefix} ${mac}` : '',
                        speed: speed ? `${prefix} ${speed}` : '',
                        state: state ? `${prefix} ${state}` : '',
                    };
                });
                rows.push({
                    name: getServerDisplayName(machine),
                    group: machine.asset_group || '',
                    ip: machine.ip || '',
                    mac: machine.mac || '',
                    cpu: st.cpu_name || '',
                    motherboard: st.motherboard || '',
                    mem_speed_mhz: st.mem_speed || '',
                    os: st.os_info?.name || st.os_caption || st.os_version || '',
                    memory: st.memory_topology?.installed_count ? `${st.memory_topology.installed_count}条 ${memoryChannelText(st.memory_topology)}` : '',
                    disk_count: st.storage_summary?.disk_count ?? (Array.isArray(st.storage_devices) ? st.storage_devices.length : ''),
                    network_summary: `${network.active_count ?? 0}/${network.physical_count ?? 0}网卡`,
                    wireless: wifi.present ? (wifi.connected ? `Wi-Fi ${wifi.ssid || '已连接'}` : 'Wi-Fi未连') : '',
                    bluetooth: bt.present ? (bt.blocked ? '蓝牙阻塞' : '蓝牙') : '',
                    adapter_name: exportListCell(adapterRows.map(item => item.name)),
                    adapter_ip: exportListCell(adapterRows.map(item => item.ip)),
                    adapter_mac: exportListCell(adapterRows.map(item => item.mac)),
                    adapter_speed_mbps: exportListCell(adapterRows.map(item => item.speed)),
                    adapter_state: exportListCell(adapterRows.map(item => item.state)),
                    codemeter_installed: codemeterInstalled,
                    codemeter_running: codemeterRunning,
                    codemeter_validity: codemeterValidity,
                    codemeter_label: codemeterLabel,
                    codemeter_all_serials: codemeterSerials.join(' / '),
                    codemeter_serial: licenseRows.length ? exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.serial || codemeterSerials.join(' / ')}`)) : codemeterSerials.join(' / '),
                    codemeter_product_code: exportListCell(licenseRows.map((license, index) => license.code ? `${index + 1}. ${license.code}` : '')),
                    codemeter_expiry: exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.permanent ? '长期' : (license.expiryText || '')}`)),
                    codemeter_days_left: nearestExpiringLicense
                        ? `=MAX(0,DATEVALUE("${nearestExpiringLicense.expiryText}")-TODAY())`
                        : (licenseRows.some(license => license.permanent) ? '长期' : ''),
                    codemeter_license_status: licenseRows.length
                        ? exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.expired ? '已过期' : (license.permanent ? '长期' : '有效')}`))
                        : codemeterValidity,
                });
            });
            return rows;
        }
        function exportServerDeviceInfoCsv() {
            const rows = getServerDeviceInfoExportRows();
            if (!rows.length) {
                showToast('暂无可导出的服务器设备信息', true);
                return;
            }
            const columns = [
                ['name', '设备名'],
                ['group', '分组'],
                ['ip', '管理IP'],
                ['mac', '主MAC'],
                ['cpu', 'CPU'],
                ['motherboard', '主板'],
                ['mem_speed_mhz', '内存频率MHz'],
                ['os', '系统'],
                ['memory', '内存'],
                ['disk_count', '硬盘数量'],
                ['network_summary', '网络汇总'],
                ['wireless', '无线'],
                ['bluetooth', '蓝牙'],
                ['adapter_name', '网卡名称'],
                ['adapter_ip', '网卡IP'],
                ['adapter_mac', '网卡MAC'],
                ['adapter_speed_mbps', '网卡速率Mbps'],
                ['adapter_state', '网卡状态'],
                ['codemeter_installed', '加密锁安装'],
                ['codemeter_running', '加密锁服务'],
                ['codemeter_validity', '加密锁状态'],
                ['codemeter_label', '加密锁授权'],
                ['codemeter_all_serials', '全部加密锁编号'],
                ['codemeter_serial', '加密锁编号'],
                ['codemeter_product_code', '产品码'],
                ['codemeter_expiry', '到期时间'],
                ['codemeter_days_left', '剩余天数'],
                ['codemeter_license_status', '授权状态'],
            ];
            const csv = [columns.map(([, label]) => csvCell(label)).join(',')]
                .concat(rows.map(row => columns.map(([key]) => csvCell(row[key])).join(',')))
                .join('\r\n');
            const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `server-device-info-${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            showToast('服务器设备信息 CSV 已生成');
        }
        window.getServerDeviceInfoExportRows = getServerDeviceInfoExportRows;
        window.exportServerDeviceInfoCsv = exportServerDeviceInfoCsv;
        function formatBytesGiB(bytes) {
            return SmartCenter.serverMonitor.formatBytesGiB.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function compactHardwareName(value, fallback = '--') {
            return SmartCenter.serverMonitor.compactHardwareName.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function compactCpuName(name) {
            return SmartCenter.serverMonitor.compactCpuName.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function memoryChannelText(topology) {
            return SmartCenter.serverMonitor.memoryChannelText.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function renderServerHardwareExtra(st) {
            return SmartCenter.serverMonitor.renderServerHardwareExtra.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function getStorageVolumeRows(st) {
            return SmartCenter.serverMonitor.getStorageVolumeRows.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function renderServerStorageRows(st) {
            return SmartCenter.serverMonitor.renderServerStorageRows.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function getNetworkPrimaryLabel(st) {
            return SmartCenter.serverMonitor.getNetworkPrimaryLabel.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function normalizeDisplayMac(value) {
            return SmartCenter.serverMonitor.normalizeDisplayMac.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getServerPhysicalMac(m) {
            return SmartCenter.serverMonitor.getServerPhysicalMac.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getServerIdentityLine(m) {
            return SmartCenter.serverMonitor.getServerIdentityLine.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function isVirtualGpuName(name) {
            return SmartCenter.serverMonitor.isVirtualGpuName.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function compactGpuName(name) {
            return SmartCenter.serverMonitor.compactGpuName.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function normalizeGpuIdentity(name) {
            return SmartCenter.serverMonitor.normalizeGpuIdentity.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function dedupeGpuRows(gpuList) {
            return SmartCenter.serverMonitor.dedupeGpuRows.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function renderServerGpuList(rawGpuList) {
            return SmartCenter.serverMonitor.renderServerGpuList.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getServerCompactGpuText(rawGpuList) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerCompactGpuText === 'function' ? api.getServerCompactGpuText.apply(api, Array.from(arguments)) : '未采到';
        }
        function getServerCompactMetricClass(value) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerCompactMetricClass === 'function' ? api.getServerCompactMetricClass.apply(api, Array.from(arguments)) : '';
        }
        function getServerCompactGroupName(machine) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerCompactGroupName === 'function' ? api.getServerCompactGroupName.apply(api, Array.from(arguments)) : '未分组';
        }
        function getServerDisplayName(machine) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerDisplayName === 'function' ? api.getServerDisplayName.apply(api, Array.from(arguments)) : (machine?.custom_name || machine?.remark || machine?.hostname || machine?.ip || '未知节点');
        }
        function buildServerCompactGroups(machines) {
            const api = getServerSummaryApi();
            return api && typeof api.buildServerCompactGroups === 'function' ? api.buildServerCompactGroups.apply(api, Array.from(arguments)) : [];
        }
        function isServerDashboardVisible(machine) {
            const api = getServerSummaryApi();
            return api && typeof api.isServerDashboardVisible === 'function'
                ? api.isServerDashboardVisible.apply(api, Array.from(arguments))
                : String(machine?.asset_group || '').trim().length > 0;
        }
        function getServerCompactAlertText(machine, diagnostic, online) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerCompactAlertText === 'function' ? api.getServerCompactAlertText.apply(api, Array.from(arguments)) : '';
        }
        function getServerCompactTooltip(machine, diagnostic, st, gpuText, alertText) {
            const api = getServerSummaryApi();
            return api && typeof api.getServerCompactTooltip === 'function' ? api.getServerCompactTooltip.apply(api, Array.from(arguments)) : getServerDisplayName(machine);
        }
        function renderDashboardServerCompact(data = []) {
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return;
            if (window.SmartCenter?.serverSummary?.renderDashboardServerCompact) {
                SmartCenter.serverSummary.renderDashboardServerCompact(data, {
                    container,
                    fallbackList: Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length
                        ? dashboardServerCompactList
                        : (Array.isArray(globalServerList) ? globalServerList : []),
                });
                return;
            }
            const machines = Array.isArray(data) && data.length
                ? data
                : (Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length
                    ? dashboardServerCompactList
                    : (Array.isArray(globalServerList) ? globalServerList : []));
            const visibleMachines = machines.filter(isServerDashboardVisible);
            if (!machines.length) {
                container.classList.remove('server-compact-grouped');
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">正在加载机器状态...</div>';
                return;
            }
            if (!visibleMachines.length) {
                container.classList.remove('server-compact-grouped');
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">暂无已分组机器，未分组机器不参与首页显示。</div>';
                return;
            }
            container.classList.add('home-status-list');
            container.classList.add('server-compact-grouped');
            const renderMachineRow = (m) => {
                const st = m.status || {};
                const agent = m.agent_status || {};
                const diagnostic = buildServerDiagnostic(agent, m);
                const online = !!m.is_online;
                const reportOnline = !!diagnostic.reportOnline;
                const badgeText = diagnostic.badgeText || (online ? '运行正常' : '离线');
                const gpuText = getServerCompactGpuText(st.gpu_list);
                const rowHealthy = online && diagnostic.level === 'success';
                const dotClass = rowHealthy ? 'online' : (reportOnline ? 'warning' : 'error');
                const titleBadge = `<span class="home-status-dot ${dotClass}" title="${escapeHtml(badgeText)}"></span>`;
                const alertText = getServerCompactAlertText(m, diagnostic, online);
                const alertHtml = alertText ? `<span class="home-server-alert" title="${escapeHtml(alertText)}">${escapeHtml(alertText)}</span>` : '';
                const titleText = getServerCompactTooltip(m, diagnostic, st, gpuText, alertText);
                return `<div class="home-status-row home-server-row ${rowHealthy ? '' : (reportOnline ? 'warning' : 'offline')}" title="${escapeHtml(titleText)}">
                    <div class="home-row-main">
                        <div class="home-row-title-line"><strong>${escapeHtml(getServerDisplayName(m))}</strong>${titleBadge}</div>
                        ${alertHtml}
                    </div>
                </div>`;
            };
            container.innerHTML = buildServerCompactGroups(visibleMachines).map(([groupName, rows]) => {
                const onlineCount = rows.filter(item => item.is_online).length;
                const warningCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return diagnostic.level !== 'success' && !!diagnostic.reportOnline;
                }).length;
                const offlineCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return !item.is_online && !diagnostic.reportOnline;
                }).length;
                const groupClass = offlineCount ? 'offline' : (warningCount ? 'warning' : '');
                const warnHtml = warningCount ? `<span class="warn">异 ${warningCount}</span>` : '';
                const offlineHtml = offlineCount ? `<span class="bad">离 ${offlineCount}</span>` : '';
                return `<section class="home-server-group ${groupClass}">
                    <div class="home-server-group-head">
                        <div class="home-server-group-name">${escapeHtml(groupName)}</div>
                        <div class="home-server-group-stats"><span class="ok">${onlineCount}/${rows.length}</span>${warnHtml}${offlineHtml}</div>
                    </div>
                    <div class="home-server-group-list">${rows.map(renderMachineRow).join('')}</div>
                </section>`;
            }).join('');
        }
        function renderDashboardServerCompactWhenReady(data = []) {
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return Promise.resolve(false);
            if (window.SmartCenter?.serverSummary) {
                renderDashboardServerCompact(data);
                return Promise.resolve(true);
            }
            dashboardServerCompactList = Array.isArray(data) ? data : dashboardServerCompactList;
            if (!String(container.innerHTML || '').trim()) {
                container.classList.add('home-status-list');
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">服务器摘要加载中...</div>';
            }
            if (getActiveViewId() === 'dashboard' && !isDashboardSectionNearViewport('server_compact')) {
                scheduleDashboardDeferredModule('server_compact', 0, 'summary');
                return Promise.resolve(false);
            }
            return ensureModulesReady(['server-summary-view'], '服务器摘要模块')
                .then(() => {
                    renderDashboardServerCompact(dashboardServerCompactList);
                    return true;
                })
                .catch(() => false);
        }
        function refreshDashboardServerCompactFallback() {
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return;
            if (Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length) {
                renderDashboardServerCompactWhenReady(dashboardServerCompactList);
            } else if (Array.isArray(globalServerList) && globalServerList.length) {
                renderDashboardServerCompactWhenReady(globalServerList);
            }
        }
        function renderServerMetaStrip(m, st, agent, diagnostic) {
            return SmartCenter.serverMonitor.renderServerMetaStrip.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function renderServerAttention(diagnostic) {
            return SmartCenter.serverMonitor.renderServerAttention.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getCodeMeterSerials(codemeter) {
            return SmartCenter.serverMonitor.getCodeMeterSerials.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getCodeMeterLicenseLabel(codemeter) {
            return SmartCenter.serverMonitor.getCodeMeterLicenseLabel.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function parseCodeMeterExpiry(value) {
            return SmartCenter.serverMonitor.parseCodeMeterExpiry.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function formatCodeMeterExpiry(date) {
            return SmartCenter.serverMonitor.formatCodeMeterExpiry.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function hasCompanyCodeMeterLicense(codemeter) {
            return SmartCenter.serverMonitor.hasCompanyCodeMeterLicense.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getCodeMeterValidityText(codemeter) {
            return SmartCenter.serverMonitor.getCodeMeterValidityText.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function normalizeCodeMeterLicenses(codemeter, serials = []) {
            return SmartCenter.serverMonitor.normalizeCodeMeterLicenses.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getCodeMeterExpiryStatusFromLicenses(licenses) {
            return SmartCenter.serverMonitor.getCodeMeterExpiryStatusFromLicenses.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function renderServerCodeMeterLine(codemeter) {
            return SmartCenter.serverMonitor.renderServerCodeMeterLine.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function getServerGroupName(machine) {
            return SmartCenter.serverMonitor.getServerGroupName.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function isAgentVersionOutdated(agent = {}) {
            return SmartCenter.serverMonitor.isAgentVersionOutdated.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function getAgentUpdateHint(agent = {}) {
            return SmartCenter.serverMonitor.getAgentUpdateHint.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function markServerCommandPending(mac, cmd, actionName) {
            const key = String(mac || '').trim().toUpperCase();
            if (!key) return;
            serverCommandPending[key] = {
                cmd,
                actionName: actionName || cmd,
                queuedAt: Date.now()
            };
        }
        function getServerCommandPending(mac) {
            const key = String(mac || '').trim().toUpperCase();
            const pending = key ? serverCommandPending[key] : null;
            if (!pending) return null;
            const ageMs = Date.now() - Number(pending.queuedAt || 0);
            if (ageMs > 120000) {
                delete serverCommandPending[key];
                return null;
            }
            return { ...pending, ageMs };
        }
        function clearSettledServerCommandPending(machines = []) {
            machines.forEach(machine => {
                const key = String(machine?.mac || '').trim().toUpperCase();
                const pending = key ? serverCommandPending[key] : null;
                if (!pending) return;
                if ((pending.cmd === 'shutdown' || pending.cmd === 'restart') && machine?.is_online === false) {
                    delete serverCommandPending[key];
                } else if (pending.cmd === 'refresh') {
                    const status = machine?.status || {};
                    const refreshedAt = Date.parse(status.hardware_refreshed_at || machine?.last_online || '');
                    if (Number.isFinite(refreshedAt) && refreshedAt >= Number(pending.queuedAt || 0) - 5000) {
                        delete serverCommandPending[key];
                    }
                }
            });
        }
        function renderServerCommandPending(pending) {
            return SmartCenter.serverMonitor.renderServerCommandPending.apply(SmartCenter.serverMonitor, Array.from(arguments));
        }
        function burstRefreshServerData() {
            if (typeof updateServerData === 'function') updateServerData();
            [1500, 5000, 12000, 25000, 45000, 70000].forEach(delay => {
                window.setTimeout(() => {
                    if (typeof updateServerData === 'function') updateServerData();
                }, delay);
            });
            if (serverCommandRefreshTimer) window.clearInterval(serverCommandRefreshTimer);
            const startedAt = Date.now();
            serverCommandRefreshTimer = window.setInterval(() => {
                if (Date.now() - startedAt > 90000) {
                    window.clearInterval(serverCommandRefreshTimer);
                    serverCommandRefreshTimer = null;
                    return;
                }
                if (typeof updateServerData === 'function') updateServerData();
            }, 5000);
        }
        function renderServerCard(m) {
            return SmartCenter.serverMonitor.renderServerCard.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        function renderServerGroupedGrid(machines) {
            return SmartCenter.serverMonitor.renderServerGroupedGrid.apply(SmartCenter.serverMonitor, Array.from(arguments).concat([getServerRenderContext()]));
        }
        updateServerData = function() {
            if (serverDataRequestInFlight) return serverDataRequestInFlight;
            serverDataRequestInFlight = fetchJson('/api/machines', {}, '服务器列表读取失败')
                .then(data => {
                    applyServerViewMode(serverViewMode);
                    data.sort((a, b) => {
                        if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
                        return a.mac.localeCompare(b.mac);
                    });
                    clearSettledServerCommandPending(data);
                    globalServerList = data;
                    const dashboardMachines = data.filter(isServerDashboardVisible);
                    dashboardServerCompactList = dashboardMachines;
                    const sTotal = document.getElementById('dash-server-total');
                    if (sTotal) sTotal.innerText = dashboardMachines.length;
                    const onlineCount = dashboardMachines.filter(m => m.is_online).length;
                    const sOnline = document.getElementById('dash-server-online');
                    if (sOnline) sOnline.innerText = onlineCount;
                    renderServerGridDeferred(data);
                    renderDashboardServerCompactWhenReady(data);
                    return data;
                })
                .catch(err => console.error('服务器数据更新失败', err))
                .finally(() => {
                    serverDataRequestInFlight = null;
                });
            return serverDataRequestInFlight;
        };

        fireProjectorCommand = function(devId, payload, format, name='') {
            if (!ensurePermission('projector.control', '操作投影机')) return;
            showToast('投影指令下发中...', false);
            postJsonLoose('/api/projector/control', { device_id: devId, command: { payload: payload, format: format, name: name } }, '投影指令下发失败')
                .then(data => {
                    showToast(data.success ? '执行成功' : ('执行失败: ' + (data.response || data.msg || '未知错误')), !data.success);
                    if (data.success) refreshProjectorStatusAfterCommand();
                })
                .catch(() => showToast('网络请求失败', true));
        };

        fireScreenCommand = function(screenId, payload, format, action) {
            if (!ensurePermission('screen.control', '操作幕布')) return;
            showToast('幕布指令下发中...', false);
            postJsonLoose('/api/screen/control', { screen_id: screenId, command: { payload: payload, format: format, action: action } }, '幕布指令下发失败')
                .then(data => {
                    showToast(data.success ? '执行成功' : ('执行失败: ' + (data.response || data.msg || '未知错误')), !data.success);
                    if (data.success) setTimeout(updateScreenStatus, 120);
                })
                .catch(() => showToast('幕布指令下发失败', true));
        };

        updateProjectorStatus = function() {
            fetchJson('/api/projector/status', {}, '投影机状态读取失败')
                .then(data => {
                    projectorStatusCache = data || {};
                    const summaryApi = window.SmartCenter?.projectorSummary || window.SmartCenter?.projector || null;
                    const fullApi = window.SmartCenter?.projector || null;
                    if (summaryApi && typeof summaryApi.renderProjectorCards === 'function') {
                        summaryApi.renderProjectorCards('dashboard-projector-grid', 'dashboard', getProjectorViewContext());
                    }
                    if (getActiveViewId() === 'projector' && fullApi && typeof fullApi.renderProjectorCards === 'function') {
                        fullApi.renderProjectorCards('projector-page-grid', 'page', getProjectorViewContext());
                    }
                    let onlineCount = 0;
                    const projectorApi = summaryApi || fullApi;
                    const dashboardProjectors = projectorApi && typeof projectorApi.getDashboardProjectors === 'function'
                        ? projectorApi.getDashboardProjectors(getProjectorViewContext())
                        : projectorConfigs.filter(proj => proj.visible !== false && proj.dashboard_visible !== false);
                    dashboardProjectors.forEach(proj => {
                        if ((projectorStatusCache[proj.id] || {}).online) onlineCount++;
                    });
                    const dashProjectorOnline = document.getElementById('dash-projector-online');
                    if (dashProjectorOnline) dashProjectorOnline.innerText = onlineCount;
                    const dashProjectorTotal = document.getElementById('dash-projector-total');
                    if (dashProjectorTotal) dashProjectorTotal.innerText = dashboardProjectors.length;
                    if (currentProjectorRemoteId) {
                        ensureModulesReady(['projector-view'], '投影遥控器模块')
                            .then(() => { if (typeof renderProjectorRemote === 'function') renderProjectorRemote(currentProjectorRemoteId); })
                            .catch(() => {});
                    }
                })
                .catch(err => console.error('投影机状态更新失败', err));
        };

        updateScreenStatus = function() {
            fetchJson('/api/screens', {}, '幕布状态读取失败')
                .then(data => {
                    const grid = document.getElementById('screen-status-grid');
                    if (!grid) return;
                    const screens = data.screens || [];
                    grid.innerHTML = screens.length
                        ? screens.map(screen => renderScreenStatusCard(screen)).join('')
                        : '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置幕布设备</div>';
                })
                .catch(err => console.error('幕布状态更新失败', err));
        };

        function extractMacAddress(value) {
            const text = String(value ?? '').trim();
            if (!text) return '';
            const match = text.match(/\b(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\b/i);
            return match ? match[0].toUpperCase() : '';
        }

        function buildEnvDeviceInfo(cfg, st) {
            const sourceType = String(cfg?.source_type || '').trim().toLowerCase();
            const macAddress = String(
                cfg?.mac_address
                || cfg?.mac
                || cfg?.ble_mac
                || cfg?.address_text
                || extractMacAddress(cfg?.note)
                || ''
            ).trim();
            let accessAddress = '';
            if (cfg?.ip) {
                accessAddress = `${cfg.ip}${cfg?.port ? `:${cfg.port}` : ''}`;
            } else if (sourceType === 'mqtt' && cfg?.mqtt?.host) {
                accessAddress = `${cfg.mqtt.host}${cfg?.mqtt?.port ? `:${cfg.mqtt.port}` : ''}`;
            } else if (['home_assistant', 'homeassistant', 'ha'].includes(sourceType) && cfg?.home_assistant?.base_url) {
                accessAddress = String(cfg.home_assistant.base_url || '').trim();
            } else {
                accessAddress = String(cfg?.bridge_host || cfg?.gateway_host || cfg?.bridge_address || '').trim();
            }
            const updatedAtText = st?.updated_at ? String(st.updated_at).replace('T', ' ').slice(0, 19) : '';
            const polledAtText = st?.polled_at ? String(st.polled_at).replace('T', ' ').slice(0, 19) : '';
            const ageSec = Number(st?.age_sec);
            const rows = [
                String(cfg?.model || '').trim() ? { label: '设备型号', value: String(cfg.model).trim() } : null,
                macAddress ? { label: 'MAC地址', value: macAddress } : null,
                accessAddress ? { label: '接入地址', value: accessAddress } : null,
                updatedAtText
                    ? { label: '数据时间', value: updatedAtText }
                    : (Number.isFinite(ageSec) ? { label: '数据年龄', value: `${Math.round(ageSec)} 秒` } : null),
                Number.isFinite(ageSec) ? { label: '数据年龄', value: formatCompactAgeFromSec(ageSec) } : null,
                polledAtText ? { label: '中控轮询', value: polledAtText } : null,
                Number.isFinite(Number(st?.rssi)) ? { label: '信号强度', value: `${Math.round(Number(st.rssi))} dBm` } : null,
                Number.isFinite(Number(st?.linkquality)) ? { label: '链路质量', value: `${Math.round(Number(st.linkquality))}` } : null,
            ].filter(Boolean);
            return {
                rows,
                note: String(cfg?.note || '').trim(),
            };
        }

        function formatEnvNumericValue(value, precision = null) {
            const num = Number(value);
            if (!Number.isFinite(num)) return null;
            return precision === null ? String(value) : num.toFixed(precision);
        }
        function buildEnvMetricMap(features, st, cfg = null) {
            const batteryValue = Number(st?.battery);
            const batteryAgeText = formatCompactAgeFromSec(st?.battery_age_sec);
            const batteryStale = !!st?.battery_stale;
            const batteryColor = !Number.isFinite(batteryValue)
                ? 'var(--text-sub)'
                : (batteryStale ? 'var(--warning)' : (batteryValue <= 15 ? 'var(--danger)' : (batteryValue <= 35 ? 'var(--warning)' : '#22c55e')));
            const voltageText = formatEnvNumericValue(st?.voltage, 3);
            const map = {
                temperature: {
                    key: 'temperature',
                    label: '温度',
                    mainLabel: '核心指标：温度',
                    value: st?.temp,
                    suffix: ' °C',
                    color: 'var(--success)',
                    available: st?.temp !== null && st?.temp !== undefined && st?.temp !== ''
                },
                humidity: {
                    key: 'humidity',
                    label: '湿度',
                    mainLabel: '核心指标：湿度',
                    value: st?.hum,
                    suffix: ' %',
                    color: 'var(--brand-blue)',
                    available: st?.hum !== null && st?.hum !== undefined && st?.hum !== ''
                },
                illuminance: {
                    key: 'illuminance',
                    label: '光照',
                    mainLabel: '核心指标：实时光照度',
                    value: st?.lux,
                    suffix: ' Lux',
                    color: 'var(--warning)',
                    available: st?.lux !== null && st?.lux !== undefined && st?.lux !== ''
                },
                contact: {
                    key: 'contact',
                    label: '开合状态',
                    mainLabel: '核心指标：开合状态',
                    text: typeof st?.contact === 'boolean'
                        ? (st.contact ? '打开' : '关闭')
                        : (st?.contact_text ? String(st.contact_text) : ''),
                    color: (typeof st?.contact === 'boolean' ? st.contact : String(st?.contact_text || '').includes('开')) ? 'var(--danger)' : 'var(--success)',
                    available: typeof st?.contact === 'boolean' || !!st?.contact_text
                },
                light: {
                    key: 'light',
                    label: '光照状态',
                    mainLabel: '核心指标：光照状态',
                    text: st?.light_text ? String(st.light_text) : (typeof st?.light === 'boolean' ? (st.light ? '亮' : '暗') : ''),
                    color: st?.light ? 'var(--warning)' : 'var(--text-sub)',
                    available: typeof st?.light === 'boolean' || !!st?.light_text
                },
                battery: {
                    key: 'battery',
                    label: batteryStale ? '电量过期' : '电量估算',
                    mainLabel: '核心指标：电量估算',
                    value: Number.isFinite(batteryValue) ? batteryValue : null,
                    suffix: ' %',
                    color: batteryColor,
                    available: Number.isFinite(batteryValue)
                },
                voltage: {
                    key: 'voltage',
                    label: '电池电压',
                    mainLabel: '核心指标：电池电压',
                    value: voltageText,
                    suffix: ' V',
                    color: st?.voltage_stale ? 'var(--warning)' : '#22c55e',
                    available: voltageText !== null
                },
                noise: {
                    key: 'noise',
                    label: '噪声',
                    mainLabel: '核心指标：噪声',
                    value: st?.noise,
                    suffix: ' dB',
                    color: 'var(--warning)',
                    available: st?.noise !== null && st?.noise !== undefined && st?.noise !== ''
                },
                pm25: {
                    key: 'pm25',
                    label: 'PM2.5',
                    mainLabel: '核心指标：PM2.5',
                    value: st?.pm25,
                    suffix: '',
                    color: '#f97316',
                    available: st?.pm25 !== null && st?.pm25 !== undefined && st?.pm25 !== ''
                },
                pm10: {
                    key: 'pm10',
                    label: 'PM10',
                    mainLabel: '核心指标：PM10',
                    value: st?.pm10,
                    suffix: '',
                    color: '#a78bfa',
                    available: st?.pm10 !== null && st?.pm10 !== undefined && st?.pm10 !== ''
                },
                pressure: {
                    key: 'pressure',
                    label: '气压',
                    mainLabel: '核心指标：气压',
                    value: st?.pressure,
                    suffix: ' kPa',
                    color: '#22c55e',
                    available: st?.pressure !== null && st?.pressure !== undefined && st?.pressure !== ''
                },
            };
            Object.keys(map).forEach(key => {
                map[key].enabled = envFeatureEnabled(features, key);
                map[key].displayText = map[key].text !== undefined
                    ? map[key].text
                    : (map[key].available ? `${map[key].value}${map[key].suffix || ''}` : '--');
                const ageSec = Number(st?.[`${key === 'temperature' ? 'temp' : key === 'humidity' ? 'hum' : key}_age_sec`]);
                if (Number.isFinite(ageSec) && Number(st?.stale_after_sec || 7200) > 0 && ageSec > Number(st?.stale_after_sec || 7200)) {
                    map[key].stale = true;
                    map[key].label = `${map[key].label}陈旧`;
                    map[key].color = 'var(--warning)';
                    map[key].displayText = `${map[key].displayText} / ${formatCompactAgeFromSec(ageSec)}`;
                }
            });
            return map;
        }
        function getEnvPrimaryMetricDef(cfg, st, features, metricMap) {
            const configured = String(cfg?.primary_metric || 'auto').trim().toLowerCase();
            const order = configured && configured !== 'auto'
                ? [configured, ...ENV_PRIMARY_METRIC_ORDER.filter(key => key !== configured)]
                : (isContactLikeEnvSensor(cfg)
                    ? ['contact', 'battery', 'voltage', 'temperature', 'humidity', 'illuminance', 'light', 'noise', 'pm25', 'pm10', 'pressure']
                    : ENV_PRIMARY_METRIC_ORDER);
            for (const key of order) {
                const item = metricMap[key];
                if (item && item.enabled && item.available) return item;
            }
            return {
                key: 'auto',
                label: '环境监测',
                mainLabel: '核心指标：环境监测',
                displayText: st?.online ? '在线' : '--',
                color: st?.online ? 'var(--success)' : 'var(--text-sub)',
                available: !!st?.online,
                enabled: true
            };
        }
        function buildEnvStatusMetricDefs(features, st, cfg = null) {
            const metricMap = buildEnvMetricMap(features, st, cfg);
            return ENV_PRIMARY_METRIC_ORDER
                .map(key => metricMap[key])
                .filter(item => item && item.enabled && item.available);
        }

        function withAutomationView(callback, contextLabel = '自动化运行页面模块') {
            return ensureAutomationViewReady(contextLabel)
                .then(api => {
                    if (api && typeof callback === 'function') return callback(api);
                    return null;
                })
                .catch(() => null);
        }
        window.toggleAutomation = (ruleId, isEnabled) => withAutomationView(
            api => api.toggleAutomation?.(ruleId, isEnabled, getAutomationRuntimeContext()),
            '自动化开关模块'
        );
        window.toggleAutomationEditor = (ruleId, forceOpen = null) => withAutomationView(
            api => api.toggleAutomationEditor?.(ruleId, forceOpen, getAutomationRuntimeContext()),
            '自动化编辑模块'
        );
        window.saveAutomationRule = ruleId => withAutomationView(
            api => api.saveAutomationRule?.(ruleId, getAutomationRuntimeContext()),
            '自动化保存模块'
        );
        window.openAutomationNodeCanvas = ruleId => withAutomationView(
            api => api.openAutomationNodeCanvas?.(ruleId, getAutomationRuntimeContext()),
            '自动化节点画布模块'
        );
        window.closeAutomationNodeCanvas = () => withAutomationView(
            api => api.closeAutomationNodeCanvas?.(),
            '自动化节点画布模块'
        );
        window.toggleAutomationNodeView = (ruleId = null, forceOpen = null) => withAutomationView(
            api => api.toggleAutomationNodeView?.(ruleId, forceOpen, getAutomationRuntimeContext()),
            '自动化节点视图模块'
        );
        window.zoomAutomationNodeCanvas = delta => withAutomationView(
            api => api.zoomAutomationNodeCanvas?.(delta),
            '自动化节点缩放模块'
        );
        window.fitAutomationNodeCanvas = () => withAutomationView(
            api => api.fitAutomationNodeCanvas?.(),
            '自动化节点缩放模块'
        );
        window.handleAutomationCanvasNodeClick = (event, nodeId) => {
            const api = getAutomationViewApi();
            if (!api?.handleAutomationCanvasNodeClick) {
                event?.preventDefault?.();
                return false;
            }
            return api.handleAutomationCanvasNodeClick(event, nodeId, getAutomationRuntimeContext());
        };
