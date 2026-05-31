        // AI_MODULE: app_runtime
        // AI_PURPOSE: 中控首页和各视图的旧全局运行时入口，继续兼容内联 onclick。
        // AI_BOUNDARY: 模板变量由 templates/index.html 注入；本文件只消费 configData/currentUser。
        // AI_DATA_FLOW: configData + API 响应 -> DOM 渲染；用户点击 -> 各 /api/* 控制接口。
        // AI_RISK: 高，保留真实设备控制链路，拆分时不得改变 payload 和权限判断。
        const lazyModuleVersion = '20260531-logs-template-slim-v1';
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
        SmartCenter.registerLazyModule('server-runtime', {
            scripts: [`/static/js/views/server-runtime.js?v=${lazyModuleVersion}`],
        });
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
        SmartCenter.registerLazyModule('projector-runtime', {
            scripts: [`/static/js/views/projector-runtime.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('projector-view', {
            scripts: [`/static/js/views/projector.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('projector-summary-view', {
            scripts: [`/static/js/views/projector-summary.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('screen-runtime', {
            scripts: [`/static/js/views/screen-runtime.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('snmp-runtime', {
            scripts: [
                `/static/js/views/snmp-summary.js?v=${lazyModuleVersion}`,
                `/static/js/views/snmp-runtime.js?v=${lazyModuleVersion}`,
            ],
        });
        SmartCenter.registerLazyModule('snmp-full', {
            styles: viewStyleGroups.snmp,
            scripts: [
                `/static/js/views/snmp-summary.js?v=${lazyModuleVersion}`,
                `/static/js/views/snmp-runtime.js?v=${lazyModuleVersion}`,
                `/static/js/views/snmp.js?v=${lazyModuleVersion}`,
            ],
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
        SmartCenter.registerLazyModule('logs-runtime', {
            scripts: [`/static/js/views/logs.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('env-runtime', {
            scripts: [`/static/js/views/env.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('hy-edge-runtime', {
            scripts: [`/static/js/views/hy-edge.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('dashboard-summary-runtime', {
            scripts: [`/static/js/views/dashboard-summary.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('power-meter-runtime', {
            scripts: [
                `/static/js/views/logs.js?v=${lazyModuleVersion}`,
                `/static/js/views/power-meter.js?v=${lazyModuleVersion}`,
                `/static/js/views/power-meter-runtime.js?v=${lazyModuleVersion}`,
            ],
        });
        SmartCenter.registerLazyModule('power-page-view', {
            scripts: [`/static/js/views/power-page-view.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('light-runtime', {
            scripts: [`/static/js/views/light-runtime.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('light-scene-view', {
            scripts: [`/static/js/views/light-scene-view.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('door-runtime', {
            scripts: [`/static/js/views/door-runtime.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('ups-runtime', {
            styles: viewStyleGroups.ups,
            scripts: [`/static/js/views/ups.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('auto-view-style', { styles: viewStyleGroups.auto });
        SmartCenter.registerLazyModule('automation-view', {
            scripts: [`/static/js/views/automation-view.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('sequencer-view-style', { styles: viewStyleGroups.sequencer });
        SmartCenter.registerLazyModule('sequencer-runtime', {
            scripts: [`/static/js/views/sequencer-runtime.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('env-view-style', { styles: viewStyleGroups.env });
        SmartCenter.registerLazyModule('logs-view-style', { styles: viewStyleGroups.logs });
        SmartCenter.registerLazyModule('dashboard-view-style', { styles: viewStyleGroups.dashboard });
        SmartCenter.registerViewModules('dashboard', ['dashboard-view-style', 'dashboard-summary-runtime']);
        SmartCenter.registerViewModules('server', ['server-view-style', 'server-runtime', 'server-monitor-view']);
        SmartCenter.registerViewModules('hvac', ['hvac-view-style', 'hvac-view']);
        SmartCenter.registerViewModules('projector', ['projector-view-style', 'projector-runtime', 'projector-view']);
        SmartCenter.registerViewModules('screen', ['screen-runtime']);
        SmartCenter.registerViewModules('snmp', ['snmp-full']);
        SmartCenter.registerViewModules('camera_preview', ['snmp-full']);
        SmartCenter.registerViewModules('proxy', ['proxy-view']);
        SmartCenter.registerViewModules('universal', ['universal-view']);
        SmartCenter.registerViewModules('apple_audio', ['apple-audio-view']);
        SmartCenter.registerViewModules('local_model', ['local-model-view']);
        SmartCenter.registerViewModules('power', ['power-view-style', 'power-meter-runtime', 'power-page-view']);
        SmartCenter.registerViewModules('light', ['light-runtime', 'light-scene-view']);
        SmartCenter.registerViewModules('scene', ['light-runtime', 'light-scene-view']);
        SmartCenter.registerViewModules('door', ['door-runtime']);
        SmartCenter.registerViewModules('meter', ['meter-view-style', 'power-meter-runtime']);
        SmartCenter.registerViewModules('ups', ['ups-runtime']);
        SmartCenter.registerViewModules('auto', ['auto-view-style', 'logs-runtime', 'automation-view']);
        SmartCenter.registerViewModules('sequencer', ['sequencer-view-style', 'sequencer-runtime']);
        SmartCenter.registerViewModules('env', ['env-view-style', 'env-runtime']);
        SmartCenter.registerViewModules('logs', ['logs-view-style', 'logs-runtime']);
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
        function ensureLogsReady(contextLabel = '日志模块') {
            const api = window.SmartCenter?.logs || null;
            if (api?.updateDashboardLogs) return Promise.resolve(api);
            return ensureModulesReady(['logs-runtime'], contextLabel).then(() => window.SmartCenter?.logs || null);
        }
        function withLogsRuntime(callback, contextLabel = '日志模块') {
            return ensureLogsReady(contextLabel)
                .then(api => (api && typeof callback === 'function' ? callback(api) : null))
                .catch(err => {
                    console.error(`${contextLabel}调用失败`, err);
                    return null;
                });
        }
        function ensureEnvReady(contextLabel = '环境模块') {
            const api = window.SmartCenter?.env || null;
            if (api?.updateEnvData) return Promise.resolve(api);
            return ensureModulesReady(['env-runtime'], contextLabel).then(() => window.SmartCenter?.env || null);
        }
        function withEnvRuntime(callback, contextLabel = '环境模块') {
            return ensureEnvReady(contextLabel)
                .then(api => (api && typeof callback === 'function' ? callback(api) : null))
                .catch(err => {
                    console.error(`${contextLabel}调用失败`, err);
                    return null;
                });
        }
        function ensureHyEdgeReady(contextLabel = 'HY 异地状态模块') {
            const api = window.SmartCenter?.hyEdge || null;
            if (api?.updateHyEdgeStatus) return Promise.resolve(api);
            return ensureModulesReady(['hy-edge-runtime'], contextLabel).then(() => window.SmartCenter?.hyEdge || null);
        }
        function withHyEdgeRuntime(callback, contextLabel = 'HY 异地状态模块') {
            return ensureHyEdgeReady(contextLabel)
                .then(api => (api && typeof callback === 'function' ? callback(api) : null))
                .catch(err => {
                    console.error(`${contextLabel}调用失败`, err);
                    return null;
                });
        }
        function ensureDashboardSummaryReady(contextLabel = '首页汇总模块') {
            const api = window.SmartCenter?.dashboardSummary || null;
            if (api?.renderDashboardSummaryTopStats) return Promise.resolve(api);
            return ensureModulesReady(['dashboard-summary-runtime'], contextLabel).then(() => window.SmartCenter?.dashboardSummary || null);
        }
        window.loadAutomationLogs = (showError = false) => withLogsRuntime(api => api.loadAutomationLogs?.(showError), '自动化日志模块');
        window.refreshEventLogs = (reset = false) => withLogsRuntime(api => api.refreshEventLogs?.(reset), '事件日志模块');
        window.pageEventLogs = delta => withLogsRuntime(api => api.pageEventLogs?.(delta), '事件日志模块');
        window.updateDashboardLogs = () => withLogsRuntime(api => api.updateDashboardLogs?.(), '首页日志模块');
        window.renderPowerDetailLogs = (cabId, logs) => withLogsRuntime(api => api.renderPowerDetailLogs?.(cabId, logs), '强电日志模块');
        window.renderPowerLogSourceTag = (log, classPrefix = 'source-tag') => {
            const api = window.SmartCenter?.logs || null;
            return api?.renderPowerLogSourceTag ? api.renderPowerLogSourceTag(log, classPrefix) : '';
        };
        window.normalizeLogOperationText = log => {
            const api = window.SmartCenter?.logs || null;
            return api?.normalizeLogOperationText ? api.normalizeLogOperationText(log) : String(log?.operation || log?.msg || log || '');
        };
        window.updateEnvData = () => withEnvRuntime(api => api.updateEnvData?.(), '环境数据模块');
        window.updateHyEdgeStatus = () => withHyEdgeRuntime(api => api.updateHyEdgeStatus?.(), 'HY 异地状态模块');
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
            power_compact: { sectionId: 'power_compact', modules: ['power-meter-runtime'], label: '强电摘要模块' },
            power_quick: { sectionId: 'power_quick', modules: ['power-meter-runtime'], label: '强电总览模块' },
            light_compact: { sectionId: 'light_compact', modules: ['light-runtime'], label: '灯光摘要模块' },
            light_quick: { sectionId: 'light_quick', modules: ['light-runtime'], label: '灯光模块' },
            projector: { sectionId: 'projector', modules: ['projector-runtime', 'projector-summary-view'], label: '投影摘要模块' },
            screen: { sectionId: 'screen', modules: ['screen-runtime'], label: '幕布运行时模块' },
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
                        const summaryMachines = getDashboardSummaryModule('server')?.machines;
                        const runtimeState = window.SmartCenter?.serverRuntime || {};
                        const data = Array.isArray(summaryMachines) && summaryMachines.length
                            ? summaryMachines
                            : (Array.isArray(runtimeState.dashboardServerCompactList) && runtimeState.dashboardServerCompactList.length
                                ? runtimeState.dashboardServerCompactList
                                : []);
                        renderDashboardServerCompactWhenReady(data);
                    } else if (key === 'hvac' && getActiveViewId() === 'dashboard') {
                        updateHvacStatus(false);
                    } else if ((key === 'power_compact' || key === 'power_quick') && getActiveViewId() === 'dashboard') {
                        updatePowerData();
                    } else if ((key === 'light_compact' || key === 'light_quick') && getActiveViewId() === 'dashboard') {
                        updateLightData();
                    } else if (key === 'projector' && getActiveViewId() === 'dashboard') {
                        updateProjectorStatus();
                    } else if (key === 'screen' && getActiveViewId() === 'dashboard') {
                        updateScreenStatus();
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
            'renderUniversalControlPage',
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
        const pwrLocks = {};
        const pwrStates = {};
        const pwrPending = {};
        const pwrDesiredStates = {};
        const POWER_CHANNEL_LOCK_MS = 6000;
        const POWER_CHANNEL_VERIFY_HOLD_MS = 45000;
        const powerStatusCache = {};
        window.powerStatusCache = powerStatusCache;
        window.pwrPending = pwrPending;
        let automationStatusCache = { server_time: '', rules: [] };
        let automationStatusLoading = false;
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
        const projectorConfigs = configData.projectors || [];
        const upsConfigs = configData.ups_devices || [];
        window.upsConfigs = upsConfigs;
        const snmpConfigs = configData.snmp_devices || [];
        const nvrConfigs = Array.isArray(configData.nvr_devices) ? configData.nvr_devices : [];
        const sequencerConfigs = Array.isArray(configData.sequencers) ? configData.sequencers : [];
        const dashboardSectionConfig = configData.dashboard_sections || {};
        let appPollingStarted = false;
        const pollingTasks = [];
        function isPageVisible() {
            return document.visibilityState !== 'hidden';
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                stopDoorVideoStream();
            } else if (getActiveViewId() === 'door') {
                setTimeout(() => {
                    ensureViewReady('door')
                        .then(() => {
                            if (getActiveViewId() !== 'door') return;
                            startDoorVideoStream();
                            updateDoorStatus(true);
                        })
                        .catch(() => {});
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
            const api = SmartCenter.dashboardSummary || {};
            return typeof api.normalizeDashboardSummaryPayload === 'function'
                ? api.normalizeDashboardSummaryPayload.apply(api, arguments)
                : (payload && typeof payload === 'object' ? payload : { counts: {}, modules: {} });
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
            return ensureDashboardSummaryReady()
                .then(api => api?.renderDashboardSummaryTopStats?.(payload, getDashboardSummaryRenderContext()));
        }
        function renderDashboardFooterStatus(payload = {}, derived = {}) {
            const api = SmartCenter.dashboardSummary || {};
            return api?.renderDashboardFooterStatus?.(payload, derived);
        }
        function renderDashboardEnvSummary(envModule = {}) {
            const api = SmartCenter.dashboardSummary || {};
            return api?.renderDashboardEnvSummary?.(envModule, getDashboardSummaryRenderContext());
        }
        function updateDashboardSummary() {
            if (dashboardSummaryInFlight) return dashboardSummaryInFlight;
            dashboardSummaryInFlight = ensureDashboardSummaryReady()
                .then(() => fetchJson('/api/dashboard/summary', {}, '首页汇总状态读取失败'))
                .then(data => {
                    dashboardSummaryCache = normalizeDashboardSummaryPayload(data);
                    return renderDashboardSummaryTopStats(dashboardSummaryCache).then(() => dashboardSummaryCache);
                })
                .then(cache => {
                    dashboardSummaryCache = cache || dashboardSummaryCache;
                    const serverMachines = dashboardSummaryCache.modules?.server?.machines;
                    if (Array.isArray(serverMachines)) {
                        window.SmartCenter?.serverRuntime?.setDashboardServerCompactList?.(serverMachines);
                        renderDashboardServerCompactWhenReady(serverMachines);
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
        window.SmartCenter = window.SmartCenter || {};
        window.SmartCenter.serverRuntime = Object.assign({
            globalServerList: [],
            dashboardServerCompactList: [],
        }, window.SmartCenter.serverRuntime || {});
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
        window.SmartCenter.serverRuntime.latestAgentVersion = String(
            window.SmartCenter.serverRuntime.latestAgentVersion || serverMonitorConfig.agent_version || ''
        ).trim();
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
            const api = window.SmartCenter?.serverRuntime;
            if (api?.getDeployBatUrl) return String(api.getDeployBatUrl(getServerRuntimeContext())).replace(/\/deploy_agent\.bat$/, '');
            const host = (serverMonitorConfig.agent_host || '').trim() || window.location.hostname;
            const port = parseInt(serverMonitorConfig.agent_port || 6899, 10) || 6899;
            return `http://${host}:${port}`;
        }
        function getDeployBatUrl() {
            const api = window.SmartCenter?.serverRuntime;
            return api?.getDeployBatUrl ? api.getDeployBatUrl(getServerRuntimeContext()) : `${getAgentBaseUrl()}/deploy_agent.bat`;
        }
        function getDeployCommandText() {
            const api = window.SmartCenter?.serverRuntime;
            if (api?.getDeployCommandText) return api.getDeployCommandText(getServerRuntimeContext());
            const batUrl = `${getDeployBatUrl()}?ts=$(Get-Date -Format yyyyMMddHHmmss)`;
            return `$u="${batUrl}"; $p="$env:TEMP\\smart-center-deploy.bat"; iwr -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -Uri $u -OutFile $p; Start-Process -FilePath $p -Verb RunAs`;
        }
        function formatDeployGeneratedAt(date = new Date()) {
            const pad = value => String(value).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
        }
        function updateDeployModalInfo() {
            const api = window.SmartCenter?.serverRuntime;
            if (api?.updateDeployModalInfo) return api.updateDeployModalInfo(getServerRuntimeContext());
            const versionEl = document.getElementById('deploy-agent-version-text');
            if (versionEl) versionEl.textContent = window.SmartCenter?.serverRuntime?.latestAgentVersion || '读取中...';
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
            return withServerRuntime((api, ctx) => api.openDeployModal(ctx), 'Agent 部署模块');
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
            const api = window.SmartCenter?.serverRuntime;
            if (api?.refreshLatestAgentVersion) {
                return api.refreshLatestAgentVersion(getServerRuntimeContext());
            }
            const ts = Date.now();
            const primaryUrl = `/agent/config?probe=1&ts=${ts}`;
            const fallbackUrl = `${getAgentBaseUrl()}/agent/config?probe=1&ts=${ts}`;
            const applyVersion = data => {
                const version = String(data?.version || '').trim();
                if (version) {
                    window.SmartCenter.serverRuntime.latestAgentVersion = version;
                    updateDeployModalInfo();
                }
                return window.SmartCenter.serverRuntime.latestAgentVersion || version;
            };
            return fetchJson(primaryUrl, {}, '读取 Agent 最新版本失败')
                .catch(() => fetchJson(fallbackUrl, {}, '读取 Agent 最新版本失败'))
                .then(applyVersion)
                .catch(err => {
                    console.warn('Agent 最新版本读取失败', err);
                    return window.SmartCenter?.serverRuntime?.latestAgentVersion || '';
                });
        }
        function copyDeployCommand() {
            return withServerRuntime((api, ctx) => api.copyDeployCommand(ctx), 'Agent 部署模块');
        }
        function copyDeployBatUrl() {
            return withServerRuntime((api, ctx) => api.copyDeployBatUrl(ctx), 'Agent 部署模块');
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
                .then(api => {
                    api?.renderAutomationPageStatus?.(rules, getAutomationRuntimeContext());
                    applyPermissionUI();
                })
                .catch(() => {});
        }
        function renderAutomationLazyPage() {
            return ensureViewReady('auto')
                .then(() => {
                    const api = getAutomationViewApi();
                    if (!api?.renderAutomationViewShell) throw new Error('automation_view_api_unavailable');
                    api.renderAutomationViewShell();
                    applyPermissionUI();
                    return loadAutomationStatus(true);
                })
                .then(() => window.loadAutomationLogs())
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
                    if (typeof showToast === 'function') showToast('自动化运行页面加载失败，请刷新后重试', true);
                    return null;
                });
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
        function getPowerMeterRuntimeContext() {
            return {
                configData,
                fetchJson,
                showToast,
                translateApiError,
                escapeHtml,
                formatTimeShort,
                setTextIfExists,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getActiveViewId,
                isDashboardSectionVisible,
                resolveVisiblePowerSupplementCabIds,
                getPowerChannelStatus,
                applyPowerStatusSnapshot,
                renderPwrChannel,
                powerStatusCache,
                pwrPending,
                renderPowerDetailLogs: window.SmartCenter?.logs?.renderPowerDetailLogs || window.renderPowerDetailLogs,
                renderPowerLogSourceTag: window.SmartCenter?.logs?.renderPowerLogSourceTag || window.renderPowerLogSourceTag,
                normalizeLogOperationText: window.SmartCenter?.logs?.normalizeLogOperationText || window.normalizeLogOperationText,
            };
        }
        window.getPowerMeterRuntimeContext = getPowerMeterRuntimeContext;
        function withPowerMeterRuntime(callback, contextLabel = '强电电表运行时模块') {
            return ensureModulesReady(['power-meter-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.powerMeterRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getPowerMeterRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        function resizePowerCharts() {
            return withPowerMeterRuntime((api, ctx) => api.resizePowerCharts(ctx));
        }
        function renderPowerEnergyChart(cabId, rawData) {
            return withPowerMeterRuntime((api, ctx) => api.renderPowerEnergyChart(cabId, rawData, ctx));
        }
        function renderDashboardPowerCards() {
            return withPowerMeterRuntime((api, ctx) => api.renderDashboardPowerCards(ctx));
        }
        function renderDashboardPowerCompact() {
            return withPowerMeterRuntime((api, ctx) => api.renderDashboardPowerCompact(ctx));
        }
        function updateMeterCenter() {
            return withPowerMeterRuntime((api, ctx) => api.updateMeterCenter(ctx), '电表中心模块');
        }
        function changeMeterTrendTarget(target) {
            return withPowerMeterRuntime((api, ctx) => api.changeMeterTrendTarget(target, ctx), '电表趋势模块');
        }
        function changeMeterTrendPeriod(period) {
            return withPowerMeterRuntime((api, ctx) => api.changeMeterTrendPeriod(period, ctx), '电表趋势模块');
        }
        function refreshPowerSupplement(cabId, force = false) {
            return withPowerMeterRuntime((api, ctx) => api.refreshPowerSupplement(cabId, force, ctx), '强电补充数据模块');
        }
        function updatePowerData() {
            return withPowerMeterRuntime((api, ctx) => api.updatePowerData(ctx), '强电状态模块');
        }
        function getSnmpRuntimeContext() {
            return {
                configData,
                snmpConfigs,
                nvrConfigs,
                fetchJson,
                showToast,
                translateApiError,
                escapeHtml,
                getDeviceStatusMeta,
                getActiveViewId,
                isDashboardSectionVisible,
                ensureViewReady,
                guardFrontendStep,
            };
        }
        window.getSnmpRuntimeContext = getSnmpRuntimeContext;
        function getSnmpRuntimeApi() {
            return window.SmartCenter?.snmpRuntime || null;
        }
        function ensureSnmpRuntimeReady(contextLabel = '网络监控运行时模块') {
            return ensureModulesReady(['snmp-runtime'], contextLabel)
                .then(() => getSnmpRuntimeApi());
        }
        function withSnmpRuntime(callback, contextLabel = '网络监控运行时模块') {
            return ensureSnmpRuntimeReady(contextLabel)
                .then(api => {
                    if (api && typeof callback === 'function') return callback(api, getSnmpRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        function stopNvrPreviewStreams() {
            const api = getSnmpRuntimeApi();
            if (api?.stopNvrPreviewStreams) return api.stopNvrPreviewStreams();
            const panel = document.getElementById('nvr-preview-panel');
            if (!panel) return null;
            panel.querySelectorAll('iframe').forEach(frame => {
                try { frame.src = 'about:blank'; } catch (_) {}
                try { frame.removeAttribute('src'); } catch (_) {}
            });
            panel.querySelectorAll('.nvr-wall-cell.loading, .nvr-preview-frame.loading').forEach(el => el.classList.remove('loading'));
            return null;
        }
        function clearSnmpSelectedDevice() {
            const api = getSnmpRuntimeApi();
            if (api?.clearSnmpSelectedDevice) return api.clearSnmpSelectedDevice();
            try {
                const url = new URL(window.location.href);
                url.searchParams.delete('snmp_device');
                window.history.replaceState(null, '', url.toString());
            } catch (_) {}
            return null;
        }
        function restoreSnmpSelectedDeviceFromUrl() {
            return withSnmpRuntime((api) => api.restoreSnmpSelectedDeviceFromUrl(), 'SNMP 详情状态模块');
        }
        function renderSnmpCards(options = {}) {
            return withSnmpRuntime((api, ctx) => api.renderSnmpCards(options, ctx), 'SNMP 渲染模块');
        }
        function updateSnmpStatus(options = {}) {
            return withSnmpRuntime((api, ctx) => api.updateSnmpStatus(options, ctx), '网络监控状态模块');
        }
        function applyNvrPreviewUrlParams() {
            return withSnmpRuntime((api) => api.applyNvrPreviewUrlParams(), '监控预览参数模块');
        }
        function renderNvrPreviewPanel(options = {}) {
            return withSnmpRuntime((api, ctx) => api.renderNvrPreviewPanel(options, ctx), '监控预览模块');
        }
        function selectNvrPreview(deviceId, channelId, options = {}) {
            return withSnmpRuntime((api, ctx) => api.selectNvrPreview(deviceId, channelId, options, ctx), '监控预览模块');
        }
        function setNvrPreviewMode(mode) {
            return withSnmpRuntime((api, ctx) => api.setNvrPreviewMode(mode, ctx), '监控预览模块');
        }
        function setNvrPreviewGrid(grid) {
            return withSnmpRuntime((api, ctx) => api.setNvrPreviewGrid(grid, ctx), '监控预览模块');
        }
        function setNvrPreviewPage(delta) {
            return withSnmpRuntime((api, ctx) => api.setNvrPreviewPage(delta, ctx), '监控预览模块');
        }
        window.selectNvrPreview = selectNvrPreview;
        window.setNvrPreviewMode = setNvrPreviewMode;
        window.setNvrPreviewGrid = setNvrPreviewGrid;
        window.setNvrPreviewPage = setNvrPreviewPage;
        window.renderNvrPreviewPanel = renderNvrPreviewPanel;
        window.updateSnmpStatus = updateSnmpStatus;
        window.renderSnmpCards = renderSnmpCards;
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
            if (viewId !== 'snmp') clearSnmpSelectedDevice();
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
            if (viewId !== 'auto') ensureViewReady(viewId).catch(() => {});
            if (viewId === 'power') setTimeout(() => {
                ensureViewReady('power')
                    .then(() => {
                        renderPowerPage();
                        resizePowerCharts();
                        updatePowerData();
                    })
                    .catch(() => {});
            }, 120);
            if (viewId === 'meter') setTimeout(() => { ensureViewReady('meter').then(() => updateMeterCenter()).catch(() => {}); }, 80);
            if (viewId === 'ups') setTimeout(() => { ensureViewReady('ups').then(() => updateUpsStatus()).catch(() => {}); }, 80);
            if (viewId === 'snmp') setTimeout(() => { ensureViewReady('snmp').then(() => updateSnmpStatus({ full: true })).catch(() => {}); }, 80);
            if (viewId === 'proxy') setTimeout(() => { ensureViewReady('proxy').then(() => updateProxyStatus()).catch(() => {}); }, 80);
            if (viewId === 'auto') setTimeout(() => { renderAutomationLazyPage(); }, 80);
            if (viewId === 'camera_preview') {
                setTimeout(() => {
                    ensureSnmpRuntimeReady('监控预览模块')
                        .then(api => {
                            api?.applyNvrPreviewUrlParams?.();
                            return ensureViewReady('camera_preview');
                        })
                        .then(() => updateSnmpStatus({ full: true }))
                        .finally(() => renderNvrPreviewPanel({ refresh: true }));
                }, 80);
            }
            if (viewId === 'hvac') setTimeout(() => {
                ensureViewReady('hvac')
                    .then(() => {
                        updateHvacStatus(true);
                        return window.updateEnvData();
                    })
                    .catch(() => {});
            }, 80);
            if (viewId === 'door') setTimeout(() => {
                ensureViewReady('door')
                    .then(() => {
                        if (getActiveViewId() !== 'door') return null;
                        initCanvas();
                        return updateDoorStatus(true);
                    })
                    .finally(() => {
                        if (getActiveViewId() === 'door') startDoorVideoStream();
                    })
                    .catch(() => {});
            }, 100);
            if (viewId === 'sequencer') setTimeout(() => { ensureViewReady('sequencer').then(() => updateSequencerStatus()).catch(() => {}); }, 80);
            if (viewId === 'light') setTimeout(() => {
                ensureViewReady('light')
                    .then(() => {
                        renderLightSceneView('light');
                        return updateLightData();
                    })
                    .catch(() => {});
            }, 80);
            if (viewId === 'scene') setTimeout(() => {
                ensureViewReady('scene')
                    .then(() => renderLightSceneView('scene'))
                    .catch(() => {});
            }, 80);
            if (viewId === 'universal') setTimeout(() => {
                ensureViewReady('universal')
                    .then(() => {
                        renderUniversalControlPage(true);
                        updateProtocolDeviceCards(true);
                        return updateNodeRedDevices(true);
                    })
                    .catch(() => {});
            }, 80);
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
        function getSequencerRuntimeContext() {
            return {
                fetchJson,
                postJsonLoose,
                ensurePermission,
                showToast,
                translateApiError,
                escapeHtml,
                hasPermission,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                updateDashboardLogs: window.updateDashboardLogs,
            };
        }
        function withSequencerRuntime(callback, contextLabel = '时序电源运行时模块') {
            return ensureModulesReady(['sequencer-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.sequencerRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getSequencerRuntimeContext());
                    return null;
                })
                .catch(() => null);
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
                    setTimeout(() => { updateHvacStatus(); window.updateDashboardLogs(); }, 320);
                })
                .catch(err => {
                    showToast(translateApiError(err?.message, '空调控制失败'), true);
                });
        }

        setInterval(updateGlobalClock, 1000);

        window.addEventListener('resize', () => {
            if (getActiveViewId() === 'door' || window.SmartCenter?.doorRuntime) initCanvas();
            resizePowerCharts();
        });
        function openWizard() { document.getElementById('aiWizardModal').style.display = 'block'; document.getElementById('step1-card').style.opacity = '1'; document.getElementById('step1-card').style.pointerEvents = 'auto'; document.getElementById('step2-card').style.opacity = '0.4'; document.getElementById('step2-card').style.pointerEvents = 'none'; }
        function closeWizard() { document.getElementById('aiWizardModal').style.display = 'none'; }
        const wizardBox = document.getElementById('wizardBox'); const wizardHeader = document.getElementById('wizardHeader'); let isWizDragging = false; let wizOffsetX = 0, wizOffsetY = 0; wizardHeader.addEventListener('mousedown', function(e) { if(e.target.tagName.toLowerCase() === 'button') return; isWizDragging = true; wizOffsetX = e.clientX - wizardBox.offsetLeft; wizOffsetY = e.clientY - wizardBox.offsetTop; wizardBox.style.transition = 'none'; wizardBox.style.opacity = '0.9'; }); document.addEventListener('mousemove', function(e) { if (!isWizDragging) return; wizardBox.style.left = (e.clientX - wizOffsetX) + 'px'; wizardBox.style.top = (e.clientY - wizOffsetY) + 'px'; wizardBox.style.right = 'auto'; }); document.addEventListener('mouseup', function() { if (isWizDragging) { isWizDragging = false; wizardBox.style.transition = 'opacity 0.2s'; wizardBox.style.opacity = '1'; } });

        // 强电与灯光控制
        configData.cabinets.forEach((cab, idx) => { pwrLocks[idx] = {}; pwrStates[idx] = []; pwrDesiredStates[idx] = {}; });
function renderPwrChannel(cabId, chNum) { const cachedChannels = (powerStatusCache[cabId] || {}).channels_1_4; const hasCachedStatus = Array.isArray(cachedChannels) && cachedChannels[chNum - 1] !== undefined; const status = getPowerChannelStatus(cabId, chNum); const chItem = document.getElementById(`pch_${cabId}_${chNum}`); if(!chItem) return; let chCfg = (configData.cabinets[cabId].channels_config || []).find(c => c.channel === chNum); let chName = chCfg ? chCfg.name : (configData.cabinets[cabId].ui_text.label_channel + chNum); let chRemark = chCfg ? (chCfg.remark || '') : ''; const ui = configData.cabinets[cabId].ui_text; const isPending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]); const cls = isPending ? 'ch-off' : (status === null || status === undefined ? 'ch-err' : (status ? 'ch-on' : 'ch-off')); const txt = isPending ? '执行中' : (status === null || status === undefined ? '离线' : (status ? ui.label_on : ui.label_off)); const oldClasses = Array.from(chItem.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn' || c === 'power-channel-btn').join(' '); chItem.className = `${oldClasses || 'ch-btn power-channel-btn'} ${cls}`; chItem.innerHTML = `<span class="name" title="${escapeHtml(chRemark ? chName + ' / ' + chRemark : chName)}">${escapeHtml(chName)}</span>${chRemark ? `<span class="remark" title="${escapeHtml(chRemark)}">${escapeHtml(chRemark)}</span>` : ''}<span class="state">${escapeHtml(txt)}</span>`; chItem.disabled = isPending || chItem.classList.contains('permission-disabled'); chItem.style.pointerEvents = isPending ? 'none' : ''; chItem.style.opacity = isPending ? '0.78' : ''; chItem.dataset.stateSource = hasCachedStatus ? 'api' : 'local'; }
        function exportEnergyHistory() {
            window.open('/api/export/energy_30days', '_blank');
        }


        // AI_BRIDGE: light_runtime
        // 灯光控制、首页摘要和灯光日志已迁移到 static/js/views/light-runtime.js。
        function getLightRuntimeContext() {
            return {
                configData,
                fetchJson,
                postJsonLoose,
                getActiveViewId,
                ensurePermission,
                showToast,
                translateApiError,
                escapeHtml,
                getDeviceStatusMeta,
                getCardStateClass,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                scheduleDashboardMasonry,
            };
        }
        window.getLightRuntimeContext = getLightRuntimeContext;
        function withLightRuntime(callback, contextLabel = '灯光运行时模块') {
            return ensureModulesReady(['light-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.lightRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getLightRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        function updateLightData() {
            return withLightRuntime((api, ctx) => api.updateLightData(ctx), '灯光状态模块');
        }
        function toggleLight(devId, chNum) {
            return withLightRuntime((api, ctx) => api.toggleLight(devId, chNum, ctx), '灯光控制模块');
        }
        function triggerLightAction(devId, actionName, label) {
            return withLightRuntime((api, ctx) => api.triggerLightAction(devId, actionName, label, ctx), '灯光动作模块');
        }
        function executeScene(sceneId, name) {
            return withLightRuntime((api, ctx) => api.executeScene(sceneId, name, ctx), '灯光场景模块');
        }
        window.updateLightData = updateLightData;
        window.toggleLight = toggleLight;
        window.triggerLightAction = triggerLightAction;
        window.executeScene = executeScene;

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

        // AI_BRIDGE: server_runtime
        // 服务器监控的轮询、排序、控制和导出已迁移到 static/js/views/server-runtime.js。
        function getServerRuntimeContext() {
            return {
                configData,
                serverMonitorConfig,
                fetchJson,
                postJsonLoose,
                translateApiError,
                ensurePermission,
                showToast,
                escapeHtml,
                getActiveViewId,
                ensureModulesReady,
                isDashboardSectionNearViewport,
                scheduleDashboardDeferredModule,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                copyTextWithToast,
                compareAgentVersionBase,
            };
        }
        function withServerRuntime(callback, contextLabel = '服务器监控运行时模块', moduleNames = ['server-runtime']) {
            return ensureModulesReady(moduleNames, contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.serverRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getServerRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        function getServerRenderContext() {
            const api = window.SmartCenter?.serverRuntime;
            if (api?.getServerRenderContext) return api.getServerRenderContext(getServerRuntimeContext());
            let serverViewMode = 'compact';
            try { serverViewMode = localStorage.getItem('smart-center-server-view-mode') || 'compact'; } catch (_) {}
            return {
                serverViewMode,
                latestAgentVersion: window.SmartCenter?.serverRuntime?.latestAgentVersion || String(serverMonitorConfig.agent_version || '').trim(),
                compareAgentVersionBase,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getServerCommandPending: mac => window.SmartCenter?.serverRuntime?.getServerCommandPending?.(mac) || null,
            };
        }
        window.getServerRuntimeContext = getServerRuntimeContext;

        // AI_BRIDGE: projector_runtime
        // 投影机状态缓存、渲染协调和控制链路已迁移到 static/js/views/projector-runtime.js。
        function getProjectorRuntimeContext() {
            return {
                projectorConfigs,
                getActiveViewId,
                ensureModulesReady,
                fetchJson,
                postJsonLoose,
                ensurePermission,
                showToast,
                escapeHtml,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getDeviceStatusMeta,
                getCardStateClass,
            };
        }
        function withProjectorRuntime(callback, contextLabel = '投影运行时模块') {
            return ensureModulesReady(['projector-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.projectorRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getProjectorRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        window.getProjectorViewContext = function() {
            const api = window.SmartCenter?.projectorRuntime;
            return api?.getProjectorViewContext
                ? api.getProjectorViewContext(getProjectorRuntimeContext())
                : {
                    projectorConfigs,
                    statusCache: {},
                    getStatus: () => null,
                    escapeHtml,
                    getPermissionDisabledClass,
                    getPermissionDisabledAttrs,
                    getDeviceStatusMeta,
                    getCardStateClass,
                };
        };
        window.openProjectorRemote = function(projId) {
            return withProjectorRuntime((api, ctx) => api.openProjectorRemote(projId, ctx), '投影遥控器模块');
        };
        window.closeProjectorRemote = function() {
            const api = window.SmartCenter?.projectorRuntime;
            if (api?.closeProjectorRemote) return api.closeProjectorRemote();
            const modal = document.getElementById('projectorRemoteModal');
            if (modal) modal.style.display = 'none';
            return null;
        };
        window.refreshProjectorStatusAfterCommand = function() {
            return withProjectorRuntime((api, ctx) => api.refreshProjectorStatusAfterCommand(ctx), '投影运行时模块');
        };

        function getScreenRuntimeContext() {
            return {
                configData,
                fetchJson,
                postJsonLoose,
                ensurePermission,
                showToast,
                escapeHtml,
                getPermissionDisabledClass,
                getPermissionDisabledAttrs,
                getDeviceStatusMeta,
                getCardStateClass,
            };
        }
        function withScreenRuntime(callback, contextLabel = '幕布运行时模块') {
            return ensureModulesReady(['screen-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.screenRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getScreenRuntimeContext());
                    return null;
                })
                .catch(() => null);
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

        function getDoorRuntimeContext() {
            return {
                fetchJsonLoose,
                ensurePermission,
                showToast,
                translateApiError,
                escapeHtml,
                getActiveViewId,
                updateDashboardDoorStatusFromEnv,
                updateDashboardDoorStatusFromVision,
            };
        }
        window.getDoorRuntimeContext = getDoorRuntimeContext;
        function withDoorRuntime(callback, contextLabel = '门禁运行时模块') {
            return ensureModulesReady(['door-runtime'], contextLabel)
                .then(() => {
                    const api = window.SmartCenter?.doorRuntime || null;
                    if (api && typeof callback === 'function') return callback(api, getDoorRuntimeContext());
                    return null;
                })
                .catch(() => null);
        }
        function initCanvas() {
            return withDoorRuntime((api) => api.initCanvas(), '门禁画布模块');
        }
        function startDrawRegion(slot = 'right') {
            return withDoorRuntime((api) => api.startDrawRegion(slot), '门禁框选模块');
        }
        function startDoorVideoStream() {
            return withDoorRuntime((api) => api.startDoorVideoStream(), '门禁视频模块');
        }
        function stopDoorVideoStream() {
            const api = window.SmartCenter?.doorRuntime || null;
            if (api && typeof api.stopDoorVideoStream === 'function') api.stopDoorVideoStream();
            return Promise.resolve(null);
        }
        function updateDoorStatus(force = false) {
            return withDoorRuntime((api, ctx) => api.updateDoorStatus(force, ctx), '门禁状态模块');
        }
        function controlDoor(action) {
            return withDoorRuntime((api, ctx) => api.controlDoor(action, ctx), '门禁控制模块');
        }
        window.initCanvas = initCanvas;
        window.startDrawRegion = startDrawRegion;
        window.startDoorVideoStream = startDoorVideoStream;
        window.stopDoorVideoStream = stopDoorVideoStream;
        window.updateDoorStatus = updateDoorStatus;
        window.controlDoor = controlDoor;

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
            guardFrontendStep('bootstrap.server_compact', () => {
                const initialView = getInitialViewFromUrl();
                if (!initialView || initialView === 'dashboard') refreshDashboardServerCompactFallback();
            });
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
                        if (getActiveViewId() !== 'door') return;
                        initCanvas();
                        updateDoorStatus(true).finally(() => {
                            if (getActiveViewId() === 'door') startDoorVideoStream();
                        });
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

        registerPollingTask('power', 3500, () => {
            if (getActiveViewId() === 'power') {
                return ensureViewReady('power')
                    .then(() => {
                        renderPowerPage();
                        return updatePowerData();
                    });
            }
            return updatePowerData();
        }, () => getActiveViewId() === 'power' || (getActiveViewId() === 'dashboard' && (isDashboardSectionNearViewport('power_compact') || isDashboardSectionNearViewport('power_quick'))));
        registerPollingTask('meter', 4500, () => updateMeterCenter(), () => getActiveViewId() === 'meter');
        registerPollingTask('ups', 4500, () => ensureViewReady('ups').then(() => updateUpsStatus()), () => getActiveViewId() === 'ups' || (getActiveViewId() === 'dashboard' && (isDashboardSectionNearViewport('ups_compact') || isDashboardSectionNearViewport('ups'))));
        registerPollingTask('hy_edge', 6000, () => window.updateHyEdgeStatus(), () => ['dashboard'].includes(getActiveViewId()) || isDashboardSectionVisible('hy_edge'));
        registerPollingTask('dashboard_summary', 5000, () => updateDashboardSummary(), () => getActiveViewId() === 'dashboard' || isDashboardSectionVisible('stats'));
        registerPollingTask('proxy', 5000, () => ensureViewReady('proxy').then(() => updateProxyStatus()), () => getActiveViewId() === 'proxy');
        registerPollingTask('snmp', 9000, () => updateSnmpStatus(), () => ['dashboard', 'snmp', 'camera_preview'].includes(getActiveViewId()) || isDashboardSectionVisible('snmp'));
        registerPollingTask('hvac', 5000, () => {
            const modules = getActiveViewId() === 'hvac' ? ['hvac-view'] : ['hvac-summary-view'];
            return ensureModulesReady(modules, '空调模块').then(() => updateHvacStatus());
        }, () => getActiveViewId() === 'hvac' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('hvac')));
        registerPollingTask('light', 2200, () => {
            const modules = getActiveViewId() === 'light' ? ['light-runtime', 'light-scene-view'] : ['light-runtime'];
            return ensureModulesReady(modules, '灯光状态模块')
                .then(() => {
                    if (getActiveViewId() === 'light') renderLightSceneView('light');
                    return updateLightData();
                });
        }, () => getActiveViewId() === 'light' || (getActiveViewId() === 'dashboard' && (isDashboardSectionNearViewport('light_compact') || isDashboardSectionNearViewport('light_quick'))));
        registerPollingTask('node_red', 5000, () => ensureViewReady('universal').then(() => updateNodeRedDevices()), () => getActiveViewId() === 'universal');
        registerPollingTask('server', 5000, () => ensureViewReady('server').then(() => updateServerData()), () => getActiveViewId() === 'server');
        registerPollingTask('door', 1200, () => updateDoorStatus(), () => ['dashboard', 'door'].includes(getActiveViewId()) || isDashboardSectionVisible('door'));
        registerPollingTask('env', 3500, () => window.updateEnvData(), () => ['dashboard', 'env', 'hvac'].includes(getActiveViewId()) || isDashboardSectionVisible('env') || isDashboardSectionVisible('hvac'));
        registerPollingTask('automation', 4000, () => {
            loadAutomationStatus();
            if (getActiveViewId() === 'auto') window.loadAutomationLogs();
        }, () => ['dashboard', 'auto'].includes(getActiveViewId()));
        registerPollingTask('projector', 6000, () => {
            const modules = getActiveViewId() === 'projector' ? ['projector-runtime', 'projector-view'] : ['projector-runtime', 'projector-summary-view'];
            return ensureModulesReady(modules, '投影模块').then(() => updateProjectorStatus());
        }, () => getActiveViewId() === 'projector' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('projector')));
        registerPollingTask('sequencer', 4500, () => ensureModulesReady(['sequencer-runtime'], '时序电源运行时模块').then(() => updateSequencerStatus()), () => getActiveViewId() === 'sequencer' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('sequencer')));
        registerPollingTask('screen', 4500, () => ensureModulesReady(['screen-runtime'], '幕布运行时模块').then(() => updateScreenStatus()), () => getActiveViewId() === 'screen' || (getActiveViewId() === 'dashboard' && isDashboardSectionNearViewport('screen')));
        registerPollingTask('apple_audio', 3200, () => ensureViewReady('apple_audio').then(() => loadAppleAudioStatus()), () => ['apple_audio'].includes(getActiveViewId()));
        registerPollingTask('logs', 5000, () => window.updateDashboardLogs(), () => getActiveViewId() === 'dashboard');
        registerPollingTask('event_logs', 5000, () => window.refreshEventLogs(false), () => getActiveViewId() === 'logs');

        // AI_BRIDGE: door_runtime
        // 门禁状态、视频取流、区域框选和真实开关门控制已迁移到 static/js/views/door-runtime.js。
        // 保留全局函数名是为了兼容模板内联 onclick 与历史轮询入口。

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

        wakeServer = function(mac) {
            return withServerRuntime(
                (api, ctx) => api.wakeServer(mac, ctx),
                '服务器唤醒模块'
            );
        };

        sendServerCmd = function(mac, cmd) {
            return withServerRuntime(
                (api, ctx) => api.sendServerCmd(mac, cmd, ctx),
                '服务器控制模块'
            );
        };

        moveServer = function(mac, direction) {
            return withServerRuntime(
                (api, ctx) => api.moveServer(mac, direction, ctx),
                '服务器排序模块',
                ['server-runtime', 'server-monitor-view']
            );
        };

        function setServerViewMode(mode) {
            return withServerRuntime(
                (api, ctx) => api.setServerViewMode(mode, ctx),
                '服务器视图模块',
                ['server-runtime', 'server-monitor-view']
            );
        }

        function getServerDeviceInfoExportRows() {
            const api = window.SmartCenter?.serverRuntime;
            return api?.getServerDeviceInfoExportRows ? api.getServerDeviceInfoExportRows() : [];
        }

        function exportServerDeviceInfoCsv() {
            return withServerRuntime(
                (api, ctx) => api.exportServerDeviceInfoCsv(ctx),
                '服务器导出模块',
                ['server-runtime', 'server-monitor-view']
            );
        }
        window.getServerDeviceInfoExportRows = getServerDeviceInfoExportRows;
        window.exportServerDeviceInfoCsv = exportServerDeviceInfoCsv;

        function renderDashboardServerCompactWhenReady(data = []) {
            if (getActiveViewId() !== 'dashboard') return Promise.resolve(false);
            const runtimeState = window.SmartCenter?.serverRuntime;
            if (runtimeState && Array.isArray(data)) runtimeState.dashboardServerCompactList = data;
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return Promise.resolve(false);
            if (window.SmartCenter?.serverSummary?.renderDashboardServerCompact) {
                return Promise.resolve(window.SmartCenter.serverSummary.renderDashboardServerCompact(data, { container }));
            }
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
                    if (!window.SmartCenter?.serverSummary?.renderDashboardServerCompact) return false;
                    return !!window.SmartCenter.serverSummary.renderDashboardServerCompact(data, { container });
                })
                .catch(err => {
                    console.error('服务器摘要模块加载失败', err);
                    return false;
                });
        }

        function refreshDashboardServerCompactFallback() {
            if (getActiveViewId() !== 'dashboard') return Promise.resolve(false);
            const runtimeState = window.SmartCenter?.serverRuntime || {};
            const data = Array.isArray(runtimeState.dashboardServerCompactList) && runtimeState.dashboardServerCompactList.length
                ? runtimeState.dashboardServerCompactList
                : (Array.isArray(runtimeState.globalServerList) ? runtimeState.globalServerList : []);
            return renderDashboardServerCompactWhenReady(data);
        }

        function markServerCommandPending(mac, cmd, actionName) {
            return window.SmartCenter?.serverRuntime?.markServerCommandPending?.(mac, cmd, actionName);
        }

        function getServerCommandPending(mac) {
            return window.SmartCenter?.serverRuntime?.getServerCommandPending?.(mac) || null;
        }

        function burstRefreshServerData() {
            return withServerRuntime(
                (api, ctx) => api.burstRefreshServerData(ctx),
                '服务器刷新模块'
            );
        }

        updateServerData = function() {
            return withServerRuntime(
                (api, ctx) => api.updateServerData(ctx),
                '服务器监控模块',
                ['server-runtime', 'server-monitor-view']
            );
        };

        fireProjectorCommand = function(devId, payload, format, name='') {
            return withProjectorRuntime(
                (api, ctx) => api.fireProjectorCommand(devId, payload, format, name, ctx),
                '投影控制模块'
            );
        };

        fireScreenCommand = function(screenId, payload, format, action) {
            return withScreenRuntime(
                (api, ctx) => api.fireScreenCommand(screenId, payload, format, action, ctx),
                '幕布控制模块'
            );
        };

        updateProjectorStatus = function() {
            return withProjectorRuntime(
                (api, ctx) => api.updateProjectorStatus(ctx),
                '投影状态模块'
            );
        };

        updateScreenStatus = function() {
            return withScreenRuntime(
                (api, ctx) => api.updateScreenStatus(ctx),
                '幕布状态模块'
            );
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
