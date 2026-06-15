        // AI_MODULE: app_runtime
        // AI_PURPOSE: 中控首页和各视图的旧全局运行时入口，继续兼容内联 onclick 与首页巡屏锁定。
        // AI_BOUNDARY: 模板变量由 templates/index.html 注入；本文件只消费 configData/currentUser。
        // AI_DATA_FLOW: configData + API 响应 -> DOM 渲染；用户点击 -> 首页巡屏守卫或各 /api/* 控制接口。
        // AI_RISK: 高，保留真实设备控制链路，拆分时不得改变 payload 和权限判断；巡屏开启时必须阻断控制与配置入口。
        const lazyModuleVersion = '20260615-control-toggle-page-switch-v1';
        const lazyStyle = name => `/static/css/generated/${name}.css?v=${lazyModuleVersion}`;
        const wideUiStyle = `/static/css/views/ui-wide-1080.css?v=${lazyModuleVersion}`;
        const withWideUiStyle = styles => [...styles, wideUiStyle];
        const viewStyleGroups = {
            dashboard: withWideUiStyle([lazyStyle('dashboard')]),
            server: withWideUiStyle([lazyStyle('server')]),
            hvac: withWideUiStyle([lazyStyle('hvac')]),
            projector: withWideUiStyle([lazyStyle('projector')]),
            snmp: withWideUiStyle([lazyStyle('snmp')]),
            proxy: withWideUiStyle([lazyStyle('proxy')]),
            universal: withWideUiStyle([lazyStyle('universal')]),
            apple_audio: withWideUiStyle([lazyStyle('apple_audio')]),
            local_model: withWideUiStyle([`/static/css/views/local-model.css?v=${lazyModuleVersion}`]),
            power: withWideUiStyle([lazyStyle('power')]),
            meter: withWideUiStyle([lazyStyle('meter')]),
            ups: withWideUiStyle([lazyStyle('ups')]),
            auto: withWideUiStyle([lazyStyle('auto')]),
            sequencer: withWideUiStyle([lazyStyle('sequencer')]),
            env: withWideUiStyle([lazyStyle('env')]),
            logs: withWideUiStyle([lazyStyle('logs')]),
        };
        SmartCenter.registerLazyModule('wide-ui-style', { styles: [wideUiStyle] });
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
        SmartCenter.registerLazyModule('nvr-preview-runtime', {
            scripts: [`/static/js/views/nvr-preview-runtime.js?v=${lazyModuleVersion}`],
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
        SmartCenter.registerLazyModule('dashboard-shell-runtime', {
            scripts: [`/static/js/views/dashboard-shell.js?v=${lazyModuleVersion}`],
        });
        SmartCenter.registerLazyModule('page-shells-runtime', {
            scripts: [`/static/js/views/page-shells.js?v=${lazyModuleVersion}`],
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
        SmartCenter.registerLazyModule('automation-runtime', {
            scripts: [`/static/js/views/automation-runtime.js?v=${lazyModuleVersion}`],
        });
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
        SmartCenter.registerViewModules('dashboard', ['dashboard-view-style', 'dashboard-shell-runtime', 'dashboard-summary-runtime']);
        SmartCenter.registerViewModules('server', ['server-view-style', 'server-runtime', 'server-monitor-view']);
        SmartCenter.registerViewModules('hvac', ['hvac-view-style', 'hvac-view']);
        SmartCenter.registerViewModules('projector', ['projector-view-style', 'projector-runtime', 'projector-view']);
        SmartCenter.registerViewModules('screen', ['screen-runtime']);
        SmartCenter.registerViewModules('snmp', ['snmp-full']);
        SmartCenter.registerViewModules('camera_preview', ['snmp-full', 'nvr-preview-runtime']);
        SmartCenter.registerViewModules('proxy', ['proxy-view']);
        SmartCenter.registerViewModules('universal', ['universal-view']);
        SmartCenter.registerViewModules('apple_audio', ['apple-audio-view']);
        SmartCenter.registerViewModules('local_model', ['local-model-view']);
        SmartCenter.registerViewModules('power', ['power-view-style', 'logs-view-style', 'logs-runtime', 'power-meter-runtime', 'power-page-view']);
        SmartCenter.registerViewModules('light', ['logs-view-style', 'wide-ui-style', 'light-runtime', 'light-scene-view']);
        SmartCenter.registerViewModules('scene', ['light-runtime', 'light-scene-view']);
        SmartCenter.registerViewModules('door', ['door-runtime']);
        SmartCenter.registerViewModules('meter', ['meter-view-style', 'power-meter-runtime']);
        SmartCenter.registerViewModules('ups', ['ups-runtime']);
        SmartCenter.registerViewModules('auto', ['auto-view-style', 'logs-runtime', 'automation-runtime', 'automation-view']);
        SmartCenter.registerViewModules('sequencer', ['sequencer-view-style', 'sequencer-runtime']);
        SmartCenter.registerViewModules('env', ['env-view-style', 'env-runtime']);
        SmartCenter.registerViewModules('logs', ['logs-view-style', 'logs-runtime']);
        const smartUtils = SmartCenter.utils || {};
        const rawFetchJson = smartUtils.fetchJson || window.fetchJson;
        const rawFetchJsonLoose = smartUtils.fetchJsonLoose || window.fetchJsonLoose;
        const rawPostJsonLoose = smartUtils.postJsonLoose || window.postJsonLoose;
        const rawBrowserFetch = typeof window.fetch === 'function' ? window.fetch.bind(window) : null;
        const escapeHtml = smartUtils.escapeHtml || window.escapeHtml || (value => String(value ?? ''));
        const hasPermission = smartUtils.hasPermission || window.hasPermission || (() => false);
        const getPermissionDisabledAttrs = smartUtils.getPermissionDisabledAttrs || window.getPermissionDisabledAttrs || (() => '');
        const getPermissionDisabledClass = smartUtils.getPermissionDisabledClass || window.getPermissionDisabledClass || (() => '');
        function fetchJson() {
            if (isHomeCarouselEnabled() && isHomeCarouselControlUrl(arguments[0])) {
                showHomeCarouselLockout();
                return Promise.resolve({ ok: false, error: 'home_carousel_lockout' });
            }
            return rawFetchJson.apply(window, arguments);
        }
        function fetchJsonLoose() {
            if (isHomeCarouselEnabled() && isHomeCarouselControlUrl(arguments[0])) {
                showHomeCarouselLockout();
                return Promise.resolve({ ok: false, error: 'home_carousel_lockout' });
            }
            return rawFetchJsonLoose.apply(window, arguments);
        }
        function postJsonLoose(url, payload, fallbackText = '请求失败') {
            if (isHomeCarouselEnabled() && isHomeCarouselControlUrl(url)) {
                showHomeCarouselLockout();
                return Promise.resolve({ ok: false, error: 'home_carousel_lockout' });
            }
            return rawPostJsonLoose.call(window, url, payload, fallbackText);
        }
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
        function refreshLogsViewNow(contextLabel = '日志中心模块') {
            return ensureViewReady('logs')
                .then(() => {
                    if (getActiveViewId() !== 'logs') return null;
                    return withLogsRuntime(api => {
                        api.renderEventLogPageShell?.();
                        return api.refreshEventLogs?.(false);
                    }, contextLabel);
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
        function refreshEnvViewNow(contextLabel = '环境数据模块') {
            return ensureViewReady('env')
                .then(() => {
                    if (getActiveViewId() !== 'env') return null;
                    return withEnvRuntime(api => api.updateEnvData?.({ history: true, trend: true }), contextLabel);
                });
        }
        function recoverEnvViewIfStillLoading() {
            if (getActiveViewId() !== 'env') return;
            const container = document.getElementById('env-grid-container');
            const text = String(container?.textContent || '');
            if (!container || !text.includes('正在连接环境传感器')) return;
            refreshEnvViewNow('环境页面恢复刷新').catch(err => console.error('环境页面恢复刷新失败', err));
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
        function ensureDashboardShellRendered() {
            const root = document.getElementById('view-dashboard');
            if (!root) return false;
            if (root.dataset.dashboardShellRendered === '1') return true;
            const api = window.SmartCenter?.dashboardShell || null;
            if (api?.renderDashboardShell) return api.renderDashboardShell(configData);
            if (typeof window.renderDashboardShell === 'function') return window.renderDashboardShell(configData);
            return false;
        }
        function ensurePageShellRendered(viewId) {
            const key = String(viewId || '').replace(/^view-/, '').trim();
            if (!key || key === 'dashboard') return true;
            const root = document.getElementById(`view-${key}`);
            if (!root) return false;
            if (root.dataset.pageShellRendered === '1') return true;
            const api = window.SmartCenter?.pageShells || null;
            if (api?.renderPageShell) return api.renderPageShell(key);
            if (typeof window.renderPageShell === 'function') return window.renderPageShell(key);
            return false;
        }
        function ensureAllPageShellsRendered() {
            if (typeof window.renderAllPageShells === 'function') return window.renderAllPageShells();
            const api = window.SmartCenter?.pageShells || null;
            if (api?.renderAllPageShells) return api.renderAllPageShells();
            return false;
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
        const dashboardDeferredModules = {};
        function isDashboardSectionNearViewport(sectionId, marginPx = 520) {
            if (getActiveViewId() !== 'dashboard') return false;
            ensureDashboardShellRendered();
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
            ensureDashboardShellRendered();
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
            if (typeof window[functionName] === 'function' && !window[functionName].__smartLazyShim) {
                return;
            }
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
            'renderUniversalPageShell',
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
        const HOME_CAROUSEL_STORAGE_KEY = 'smartCenterHomeCarouselEnabled';
        const HOME_CAROUSEL_LOCKOUT_MESSAGE = '滚动播放中，请先关闭巡屏再进行控制或系统配置';
        const HOME_CAROUSEL_CONTROL_PATTERNS = [
            'togglePower(', 'doPowerStart(', 'doPowerStop(', 'toggleLight(', 'executeScene(',
            'controlDoor(', 'fireSequencerAction(', 'fireScreenCommand(', 'fireProjectorCommand(',
            'controlHvac(', 'sendServerCmd(', 'wakeServer(', 'moveServer(', 'fireUniversalCommand(',
            'fireControlCenterControl(', 'toggleProtocolDeviceOutput(', 'pulseProtocolDevice(',
            'controlNodeRedDevice(', 'saveConfig(', 'loadConfig(', 'openAppleAudioConfig(',
        ];
        const HOME_CAROUSEL_CONTROL_URLS = [
            '/api/hvac/control', '/api/sequencer/control', '/api/screen/control', '/api/projector/control',
            '/api/control_center/execute', '/api/control_center/save', '/api/control_center/niren/mode',
            '/api/control_center/import/', '/api/control_center/generate_panel', '/api/universal/control',
            '/api/door/control', '/door_control/', '/api/light/control', '/api/set', '/api/onekey_start',
            '/api/onekey_stop', '/api/ups/control', '/api/wake/', '/api/machines/', '/api/automation/toggle',
            '/api/automation/update', '/api/automation/test', '/api/node-red/device-state', '/api/config/save',
            '/api/hvac/config', '/api/screen/config', '/api/local-model/config', '/api/local-model/control/confirm',
            '/api/apple-audio/transport', '/api/apple-audio/queue', '/api/apple-audio/playlists/queue',
            '/api/apple-audio/playlists/add-track', '/api/apple-audio/bluetooth/connect', '/api/apple-audio/config',
            '/api/apple-audio/rescan',
        ];
        const HOME_CAROUSEL_VIEW_BLOCKLIST = new Set(['auto']);
        let homeCarouselUserEnabled = false;
        let homeCarouselInitialized = false;

        function getStoredHomeCarouselEnabled() {
            try {
                return localStorage.getItem(HOME_CAROUSEL_STORAGE_KEY) === '1';
            } catch (_) {
                return false;
            }
        }

        function setStoredHomeCarouselEnabled(enabled) {
            try {
                localStorage.setItem(HOME_CAROUSEL_STORAGE_KEY, enabled ? '1' : '0');
            } catch (_) {}
        }

        function isHomeCarouselEnabled() {
            return !!homeCarouselUserEnabled;
        }

        function getHomeCarouselRequestUrl(input) {
            if (!input) return '';
            if (typeof input === 'string') return input;
            if (typeof URL !== 'undefined' && input instanceof URL) return input.href;
            if (typeof Request !== 'undefined' && input instanceof Request) return input.url || '';
            if (typeof input === 'object' && input.url) return String(input.url);
            return String(input || '');
        }

        function isHomeCarouselControlUrl(url) {
            const text = getHomeCarouselRequestUrl(url).toLowerCase();
            if (!text) return false;
            if (/\/api\/node-red\/device\/[^/?#]+\/control(?:[/?#]|$)/i.test(text)) return true;
            return HOME_CAROUSEL_CONTROL_URLS.some(pattern => text.includes(pattern.toLowerCase()));
        }

        function buildHomeCarouselLockoutFetchResponse() {
            const payload = JSON.stringify({ ok: false, error: 'home_carousel_lockout', message: HOME_CAROUSEL_LOCKOUT_MESSAGE });
            if (typeof Response === 'function') {
                return new Response(payload, {
                    status: 409,
                    statusText: 'Home Carousel Lockout',
                    headers: { 'Content-Type': 'application/json' },
                });
            }
            return {
                ok: false,
                status: 409,
                json: () => Promise.resolve(JSON.parse(payload)),
                text: () => Promise.resolve(payload),
            };
        }

        function installHomeCarouselRequestGuard() {
            if (window.SmartCenter?.utils) Object.assign(window.SmartCenter.utils, { fetchJson, fetchJsonLoose, postJsonLoose });
            Object.assign(window, { fetchJson, fetchJsonLoose, postJsonLoose });
            if (!rawBrowserFetch || window.fetch?.__smartHomeCarouselGuard) return;
            const guardedFetch = function homeCarouselGuardedFetch(input, options) {
                if (isHomeCarouselEnabled() && isHomeCarouselControlUrl(input)) {
                    showHomeCarouselLockout();
                    return Promise.resolve(buildHomeCarouselLockoutFetchResponse());
                }
                return rawBrowserFetch(input, options);
            };
            guardedFetch.__smartHomeCarouselGuard = true;
            window.fetch = guardedFetch;
        }
        installHomeCarouselRequestGuard();

        function isHomeCarouselControlElement(element) {
            if (!element || element.id === 'home-carousel-toggle' || element.closest?.('.home-carousel-toggle')) return false;
            const configTarget = element.closest?.('.system-link, #top-user-config-btn, a[href^="/config"], [onclick*="/config"], [onclick*="openConfigCenter"]');
            if (configTarget) return true;
            const actionTarget = element.closest?.('button, a, input, select, textarea, label, [role="button"], [onclick]');
            if (!actionTarget) return false;
            const onclickText = String(actionTarget.getAttribute?.('onclick') || '');
            if (HOME_CAROUSEL_CONTROL_PATTERNS.some(pattern => onclickText.includes(pattern))) return true;
            const permission = String(actionTarget.getAttribute?.('data-permission') || actionTarget.dataset?.permission || '');
            if (permission && /\.(control|config|edit|manage)$/i.test(permission)) return true;
            const href = String(actionTarget.getAttribute?.('href') || '');
            return href.startsWith('/config');
        }

        function showHomeCarouselLockout() {
            showToast(HOME_CAROUSEL_LOCKOUT_MESSAGE, true);
        }

        function syncHomeCarouselUi() {
            const enabled = isHomeCarouselEnabled();
            const toggle = document.getElementById('home-carousel-toggle');
            const stateEl = document.getElementById('home-carousel-state');
            const configLink = document.querySelector('.system-link');
            const configBtn = document.getElementById('top-user-config-btn');
            if (toggle) toggle.checked = enabled;
            if (stateEl) stateEl.textContent = enabled ? '播放中' : '关闭';
            document.body.classList.toggle('home-carousel-active', enabled);
            document.documentElement.classList.toggle('home-carousel-active', enabled);
            [configLink, configBtn].forEach(el => {
                if (!el) return;
                el.classList.toggle('home-carousel-disabled', enabled);
                if (enabled) {
                    el.setAttribute('aria-disabled', 'true');
                    el.title = HOME_CAROUSEL_LOCKOUT_MESSAGE;
                } else {
                    el.removeAttribute('aria-disabled');
                    if (el.title === HOME_CAROUSEL_LOCKOUT_MESSAGE) el.removeAttribute('title');
                }
            });
        }

        function setHomeCarouselEnabled(enabled, options = {}) {
            const next = !!enabled;
            homeCarouselUserEnabled = next;
            setStoredHomeCarouselEnabled(next);
            syncHomeCarouselUi();
            if (next) {
                sidebarCarouselIntervalMs = getSidebarCarouselIntervalMs();
                sidebarCarouselActive = true;
                document.body.classList.add('sidebar-carousel-mode');
                syncSidebarCarouselIndex();
                scheduleSidebarCarouselNext(Number(options.delayMs) || 1200);
                if (!options.silent) showToast('已开启巡屏，控制和系统配置已锁定');
            } else {
                stopSidebarCarousel();
                if (!options.silent) showToast('已关闭巡屏，可以进行控制和系统配置');
            }
        }

        function toggleHomeCarousel(forceEnabled = null) {
            const next = forceEnabled === null ? !isHomeCarouselEnabled() : !!forceEnabled;
            setHomeCarouselEnabled(next);
        }

        function installHomeCarouselGuards() {
            if (homeCarouselInitialized) return;
            homeCarouselInitialized = true;
            document.addEventListener('click', event => {
                if (!isHomeCarouselEnabled()) return;
                const target = event.target instanceof Element ? event.target : null;
                if (!isHomeCarouselControlElement(target)) return;
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                showHomeCarouselLockout();
            }, true);
        }

        function initHomeCarouselSwitch() {
            const toggle = document.getElementById('home-carousel-toggle');
            homeCarouselUserEnabled = getStoredHomeCarouselEnabled();
            installHomeCarouselRequestGuard();
            installHomeCarouselGuards();
            if (toggle) {
                toggle.addEventListener('click', event => event.stopPropagation());
                toggle.addEventListener('change', event => {
                    event.stopPropagation();
                    setHomeCarouselEnabled(!!toggle.checked);
                });
            }
            syncHomeCarouselUi();
            if (homeCarouselUserEnabled) {
                sidebarCarouselIntervalMs = getSidebarCarouselIntervalMs();
                sidebarCarouselActive = true;
                document.body.classList.add('sidebar-carousel-mode');
                syncSidebarCarouselIndex();
                scheduleSidebarCarouselNext(1200);
            }
        }
        function ensurePermission(permission, actionText = '执行当前操作') {
            if (isHomeCarouselEnabled() && /\.(control|config|edit|manage)$/i.test(String(permission || ''))) {
                showHomeCarouselLockout();
                return false;
            }
            return SmartCenter.utils.ensurePermission(permission, actionText, {
                notifier: showToast,
            });
        }
        let dashboardSummaryCache = null;
        let dashboardSummaryInFlight = null;
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
            ensureDashboardShellRendered();
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
            return { pickDashboardEnvSensor: window.pickDashboardEnvSensor, renderDashboardProxySummary };
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
            env: 1200,
            projector: 4400,
            screen: 5200,
            automation: 6000,
            door: 7800,
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
        const homeDashboardOrder = {
            hero: 10,
            stats: 20,
            status_matrix: 30,
            device_focus: 40,
            ai_model: 50,
            apple_audio: 55,
            alerts: 60,
            snmp: 70,
            server_compact: 80,
            energy_trend: 90,
        };
        Object.entries(homeDashboardOrder).forEach(([key, sort]) => {
            dashboardSectionConfig[key] = Object.assign(
                { title: key, visible: true, sort },
                dashboardSectionConfig[key] || {},
                { sort }
            );
        });
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
        function ensureDeployModalShell() {
            if (document.getElementById('deployModal')) return;
            document.body.insertAdjacentHTML('beforeend', `
                <div id="deployModal" class="wizard-overlay">
                    <div class="modal-box-center">
                        <h3 style="color:var(--brand-blue); margin-bottom:15px;">Windows 节点覆盖安装 / 升级</h3>
                        <p style="color:var(--text-sub); font-size:14px; margin-bottom:10px;">在目标 Windows 机器上打开 <strong>管理员 PowerShell</strong>，运行下方命令即可覆盖安装最新 Agent。执行一次后，后续 Agent Worker 会自动从中控拉取新版。</p>
                        <div style="display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-bottom:12px;">
                            <div style="background:rgba(59,130,246,0.12); border:1px solid rgba(59,130,246,0.28); border-radius:10px; padding:10px 12px;">
                                <div style="color:#93c5fd; font-size:12px; margin-bottom:4px;">当前发布版本</div>
                                <div id="deploy-agent-version-text" style="color:#fef08a; font-size:18px; font-weight:900;">读取中...</div>
                            </div>
                            <div style="background:rgba(15,23,42,0.70); border:1px solid rgba(148,163,184,0.18); border-radius:10px; padding:10px 12px;">
                                <div style="color:#94a3b8; font-size:12px; margin-bottom:4px;">命令生成时间</div>
                                <div id="deploy-generated-at-text" style="color:#e2e8f0; font-size:18px; font-weight:800;">--</div>
                            </div>
                        </div>
                        <div style="background:#000; color:#0f0; padding:15px; border-radius:6px; font-family:monospace; word-break:break-all; font-size:13px; margin-bottom:20px;" id="deploy-cmd-text"></div>
                        <div style="background:rgba(15,23,42,0.75); color:#cbd5e1; padding:12px 14px; border-radius:10px; border:1px solid rgba(148,163,184,0.16); font-size:12px; line-height:1.7; margin-bottom:16px;">
                            <div>批处理地址：<span id="deploy-bat-url-text" style="color:#93c5fd; word-break:break-all;"></span></div>
                            <div>说明：推荐使用上方 PowerShell 命令；批处理地址保留为备用。远程机器只需覆盖安装一次，后续由计划任务自动运行并支持 Worker 自动更新。</div>
                        </div>
                        <div style="text-align:right;">
                            <button class="btn-base" style="background:var(--brand-blue);" onclick="copyDeployCommand()">复制覆盖安装命令</button>
                            <button class="btn-base" style="background:#0f766e;" onclick="copyDeployBatUrl()">复制批处理地址</button>
                            <button class="btn-base" style="background:#475569;" onclick="closeDeployModal()">关闭</button>
                        </div>
                    </div>
                </div>
            `);
        }
        function closeDeployModal() {
            const modal = document.getElementById('deployModal');
            if (modal) modal.style.display = 'none';
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
            ensureDeployModalShell();
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
        Object.assign(window, { openDeployModal, closeDeployModal, copyDeployCommand, copyDeployBatUrl });
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
            if (isHomeCarouselEnabled()) {
                showHomeCarouselLockout();
                return;
            }
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
        function getAutomationRuntimeApi() {
            return window.SmartCenter?.automationRuntime || null;
        }
        function ensureAutomationRuntimeReady(contextLabel = '自动化运行时模块') {
            const api = getAutomationRuntimeApi();
            if (api?.loadAutomationStatus) return Promise.resolve(api);
            return ensureModulesReady(['automation-runtime'], contextLabel).then(() => getAutomationRuntimeApi());
        }
        function getAutomationStatusMap() {
            const api = getAutomationRuntimeApi();
            if (api?.getAutomationStatusMap) return api.getAutomationStatusMap();
            const cache = getAutomationStatusCache();
            return new Map((Array.isArray(cache.rules) ? cache.rules : []).map(item => [String(item.id), item]));
        }
        function getAutomationStatusCache() {
            const api = getAutomationRuntimeApi();
            return api?.getAutomationStatusCache ? api.getAutomationStatusCache() : { server_time: '', rules: [] };
        }
        function getAutomationViewApi() {
            return window.SmartCenter?.automationView || null;
        }
        function ensureAutomationViewReady(contextLabel = '自动化详情模块') {
            if (getAutomationViewApi()) return Promise.resolve(getAutomationViewApi());
            return ensureModulesReady(['automation-runtime', 'automation-view'], contextLabel).then(() => getAutomationViewApi());
        }
        function getAutomationRuntimeContext() {
            return {
                configData,
                currentUser,
                getActiveViewId,
                ensureModulesReady,
                ensureViewReady,
                getAutomationStatusCache,
                getAutomationStatusMap,
                loadAutomationStatus,
                loadAutomationLogs: window.SmartCenter?.logs?.loadAutomationLogs || window.loadAutomationLogs,
                ensurePermission,
                fetchJson,
                postJsonLoose,
                translateApiError,
                showToast,
                applyPermissionUI,
                scheduleDashboardMasonry,
                formatAutomationRuleTime,
                formatAutomationValue,
                escapeHtml,
                envConfigs,
            };
        }
        function renderAutomationPageStatus() {
            return ensureAutomationRuntimeReady('自动化运行页面模块')
                .then(api => api?.renderAutomationPageStatus?.(getAutomationRuntimeContext()))
                .catch(() => null);
        }
        function renderAutomationLazyPage() {
            return ensureAutomationRuntimeReady('自动化运行页面模块')
                .then(api => api?.renderAutomationLazyPage?.(getAutomationRuntimeContext()))
                .catch(() => null);
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
        function updateDashboardDoorStatusFromEnv(envData = null) {
            const api = getAutomationRuntimeApi();
            if (api?.updateDashboardDoorStatusFromEnv) return api.updateDashboardDoorStatusFromEnv(envData, getAutomationRuntimeContext());
            const dashStatus = document.getElementById('dash-door-status');
            if (!dashStatus) return false;
            const data = envData && typeof envData === 'object' ? envData : (window.__envStatusCache || {});
            const snapshot = envConfigs
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
                .sort((left, right) => right.score - left.score)[0];
            if (!snapshot) return false;
            const st = snapshot.st || {};
            let gateState = { text: '门磁未知', className: 'blue' };
            if (!st || st.online === false) gateState = { text: '离线', className: 'blue' };
            else if (typeof st.contact === 'boolean') gateState = st.contact ? { text: '已打开', className: 'danger' } : { text: '已关闭', className: 'green' };
            else if (typeof st.opening === 'boolean') gateState = st.opening ? { text: '已打开', className: 'danger' } : { text: '已关闭', className: 'green' };
            else {
                const text = String(st.contact_text || st.state || '').trim();
                if (/开|open/i.test(text)) gateState = { text: '已打开', className: 'danger' };
                else if (/关|close|closed/i.test(text)) gateState = { text: '已关闭', className: 'green' };
            }
            dashStatus.textContent = gateState.text;
            dashStatus.className = `value ${gateState.className}`;
            dashStatus.title = `${snapshot.cfg?.name || '户外大门'} · 来源：门磁传感器`;
            return true;
        }
        function updateDashboardDoorStatusFromVision(data = {}) {
            const api = getAutomationRuntimeApi();
            if (api?.updateDashboardDoorStatusFromVision) return api.updateDashboardDoorStatusFromVision(data);
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
        function pickDashboardEnvSensor(envData) {
            const api = getAutomationRuntimeApi();
            if (api?.pickDashboardEnvSensor) return api.pickDashboardEnvSensor(envData, getAutomationRuntimeContext());
            return envConfigs
                .map(cfg => ({ cfg, st: envData[cfg.id] || { online: false } }))
                .sort((left, right) => getEnvDashboardScore(right.cfg, right.st) - getEnvDashboardScore(left.cfg, left.st))
                .find(item => getEnvDashboardScore(item.cfg, item.st) > -999)
                || envConfigs.map(cfg => ({ cfg, st: envData[cfg.id] || { online: false } })).find(item => item.st && item.st.online)
                || null;
        }
        function renderOutdoorAutomationDashboardCard() {
            const api = getAutomationRuntimeApi();
            if (api?.renderOutdoorAutomationDashboardCard) return api.renderOutdoorAutomationDashboardCard(getAutomationRuntimeContext());
            return ensureAutomationRuntimeReady('自动化首页卡片模块')
                .then(runtimeApi => runtimeApi?.renderOutdoorAutomationDashboardCard?.(getAutomationRuntimeContext()))
                .catch(() => null);
        }
        async function loadAutomationStatus(showError=false) {
            return ensureAutomationRuntimeReady('自动化状态模块')
                .then(api => api?.loadAutomationStatus?.(showError, getAutomationRuntimeContext()))
                .catch(err => {
                    if (showError) showToast(err?.message || '自动化状态读取失败', true);
                    console.error('自动化状态读取失败', err);
                    return null;
                });
        }
        Object.assign(window, {
            getAutomationRuntimeContext,
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
                ensurePermission,
                fetchJsonLoose,
                postJsonLoose,
                updateDashboardLogs: window.updateDashboardLogs,
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
        function getPowerChannelStatus(cabId, chNum) {
            const api = window.SmartCenter?.powerMeterRuntime || null;
            return api?.getPowerChannelStatus ? api.getPowerChannelStatus(cabId, chNum, getPowerMeterRuntimeContext()) : null;
        }
        function applyPowerStatusSnapshot(cabId, status) {
            const api = window.SmartCenter?.powerMeterRuntime || null;
            return api?.applyPowerStatusSnapshot ? api.applyPowerStatusSnapshot(cabId, status, getPowerMeterRuntimeContext()) : false;
        }
        function renderPwrChannel(cabId, chNum) {
            const api = window.SmartCenter?.powerMeterRuntime || null;
            return api?.renderPwrChannel ? api.renderPwrChannel(cabId, chNum, getPowerMeterRuntimeContext()) : null;
        }
        function doPowerStart(cabId) {
            return withPowerMeterRuntime((api, ctx) => api.doPowerStart(cabId, ctx), '强电启动模块');
        }
        function doPowerStop(cabId, msg) {
            return withPowerMeterRuntime((api, ctx) => api.doPowerStop(cabId, msg, ctx), '强电停止模块');
        }
        function togglePower(cabId, chNum) {
            return withPowerMeterRuntime((api, ctx) => api.togglePower(cabId, chNum, ctx), '强电控制模块');
        }
        Object.assign(window, {
            getPowerChannelStatus,
            applyPowerStatusSnapshot,
            renderPwrChannel,
            doPowerStart,
            doPowerStop,
            togglePower,
        });
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
        function isDedicatedDashboardDisplayMode() {
            const params = new URLSearchParams(window.location.search || '');
            const displayMode = String(params.get('display_mode') || params.get('mode') || '').toLowerCase();
            const fitDashboard = String(params.get('fit_dashboard') || '').toLowerCase();
            return ['wall', 'kiosk', 'fixed', 'canvas'].includes(displayMode)
                || ['1', 'true', 'on', 'fit', 'fixed', 'canvas', 'kiosk'].includes(fitDashboard);
        }
        function syncDashboardCompactMode(viewId = getActiveViewId()) {
            const dedicatedDisplay = viewId === 'dashboard' && isDedicatedDashboardDisplayMode();
            document.body.classList.toggle('dashboard-wide-mode', viewId === 'dashboard');
            document.body.classList.toggle('dashboard-compact-mode', dedicatedDisplay);
            document.body.classList.toggle('dashboard-masonry-mode', dedicatedDisplay);
            applyDashboardBrowserFit();
            scheduleDashboardMasonry();
        }
        function syncCurrentViewToUrl(viewId) {
            const safeView = String(viewId || '').replace(/[^a-zA-Z0-9_-]/g, '');
            if (!safeView) return;
            try {
                const url = new URL(window.location.href);
                if (/^#view-[a-zA-Z0-9_-]+$/.test(url.hash || '')) url.hash = '';
                if (url.searchParams.get('view') !== safeView) {
                    url.searchParams.set('view', safeView);
                }
                window.history.replaceState(null, '', url.toString());
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
        let sidebarCarouselTimer = 0;
        let sidebarCarouselActive = false;
        let sidebarCarouselIndex = 0;
        let sidebarCarouselIntervalMs = 10000;
        function isTruthyConfig(value) {
            return value === true || ['1', 'true', 'on', 'yes', 'enabled'].includes(String(value || '').toLowerCase());
        }
        function getSidebarCarouselConfig() {
            const primary = configData.sidebar_carousel || configData.carousel || configData.display_carousel || {};
            return primary && typeof primary === 'object' ? primary : {};
        }
        function isSidebarCarouselEnabled() {
            const params = new URLSearchParams(window.location.search || '');
            const mode = String(params.get('display_mode') || params.get('mode') || '').toLowerCase();
            if (['carousel', 'rotation', 'rotate'].includes(mode)) return true;
            if (isTruthyConfig(params.get('carousel')) || isTruthyConfig(params.get('sidebar_carousel')) || isTruthyConfig(params.get('auto_rotate'))) return true;
            return false;
        }
        function coerceSidebarCarouselIntervalMs(value) {
            const numeric = Number(value);
            if (!Number.isFinite(numeric) || numeric <= 0) return null;
            const ms = numeric >= 1000 ? numeric : numeric * 1000;
            return Math.max(1000, Math.min(300000, Math.round(ms)));
        }
        function getSidebarCarouselIntervalMs() {
            const params = new URLSearchParams(window.location.search || '');
            const cfg = getSidebarCarouselConfig();
            return coerceSidebarCarouselIntervalMs(params.get('carousel_interval_ms'))
                || coerceSidebarCarouselIntervalMs(params.get('carousel_interval'))
                || coerceSidebarCarouselIntervalMs(params.get('carousel_interval_sec'))
                || coerceSidebarCarouselIntervalMs(params.get('interval'))
                || coerceSidebarCarouselIntervalMs(cfg.interval_ms)
                || coerceSidebarCarouselIntervalMs(cfg.interval)
                || coerceSidebarCarouselIntervalMs(cfg.interval_sec)
                || 10000;
        }
        function getSidebarCarouselItems() {
            const seen = new Set();
            return Array.from(document.querySelectorAll('.nav-menu li')).map(navEl => {
                const onclickText = String(navEl.getAttribute('onclick') || '');
                const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
                if (!match) return null;
                const viewId = normalizeViewIdCandidate(match[1]);
                if (!viewId || seen.has(viewId)) return null;
                if (isHomeCarouselEnabled() && HOME_CAROUSEL_VIEW_BLOCKLIST.has(viewId)) return null;
                seen.add(viewId);
                return {
                    viewId,
                    title: match[2] || getViewTitleFromNav(navEl, '中控系统'),
                    navEl,
                };
            }).filter(Boolean);
        }
        function syncSidebarCarouselIndex(viewId = getActiveViewId()) {
            const items = getSidebarCarouselItems();
            if (!items.length) return;
            const index = items.findIndex(item => item.viewId === viewId);
            if (index >= 0) sidebarCarouselIndex = index;
        }
        function stopSidebarCarousel() {
            window.clearTimeout(sidebarCarouselTimer);
            sidebarCarouselTimer = 0;
            sidebarCarouselActive = false;
            document.body.classList.remove('sidebar-carousel-mode');
        }
        function scheduleSidebarCarouselNext(delayMs = sidebarCarouselIntervalMs) {
            window.clearTimeout(sidebarCarouselTimer);
            sidebarCarouselTimer = 0;
            if (!sidebarCarouselActive) return;
            const items = getSidebarCarouselItems();
            if (items.length < 2) return;
            sidebarCarouselTimer = window.setTimeout(() => {
                const freshItems = getSidebarCarouselItems();
                if (!sidebarCarouselActive || freshItems.length < 2) return;
                const currentIndex = freshItems.findIndex(item => item.viewId === getActiveViewId());
                sidebarCarouselIndex = currentIndex >= 0 ? currentIndex : sidebarCarouselIndex;
                const nextItem = freshItems[(sidebarCarouselIndex + 1) % freshItems.length];
                if (!nextItem) return scheduleSidebarCarouselNext();
                switchTab(nextItem.viewId, nextItem.title, nextItem.navEl);
            }, Math.max(1000, Number(delayMs) || 10000));
        }
        function startSidebarCarousel() {
            if (!isSidebarCarouselEnabled()) return stopSidebarCarousel();
            sidebarCarouselIntervalMs = getSidebarCarouselIntervalMs();
            sidebarCarouselActive = true;
            document.body.classList.add('sidebar-carousel-mode');
            syncSidebarCarouselIndex();
            scheduleSidebarCarouselNext();
        }
        function switchTab(viewId, title, navEl) {
            const previousView = getActiveViewId();
            if (viewId === 'dashboard') ensureDashboardShellRendered();
            else ensurePageShellRendered(viewId);
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
                            return Promise.resolve(api?.applyNvrPreviewUrlParams?.())
                                .then(() => ensureViewReady('camera_preview'));
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
            if (viewId === 'env') setTimeout(() => {
                refreshEnvViewNow('环境页面加载')
                    .then(() => setTimeout(recoverEnvViewIfStillLoading, 900))
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
            if (viewId === 'logs') setTimeout(() => { refreshLogsViewNow('日志中心页面加载').catch(() => {}); }, 80);
            if (viewId === 'dashboard') preloadDashboardSupportModules();
            window.SmartCenter?.appleAudio?.updateAppleTopLyrics?.();
            refreshPollingVisibility();
            syncSidebarCarouselIndex(viewId);
            if (sidebarCarouselActive) scheduleSidebarCarouselNext();
        }
        Object.assign(window, {
            ensureModulesReady,
            ensureViewReady,
            getActiveViewId,
            registerPollingTask,
            switchTab,
            startSidebarCarousel,
            stopSidebarCarousel,
            toggleHomeCarousel,
            setHomeCarouselEnabled,
            isHomeCarouselEnabled,
            findNavElementByView,
            getViewTitleFromNav,
        });
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
            ensureDashboardShellRendered();
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard) return;
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.sort((a, b) => {
                const defaultSort = {
                    hero: 1,
                    stats: 2,
                    status_matrix: 3,
                    device_focus: 4,
                    ai_model: 5,
                    alerts: 6,
                    snmp: 7,
                    server_compact: 8,
                    energy_trend: 9,
                };
                const sa = dashboardSectionConfig[a.dataset.sectionId] || {};
                const sb = dashboardSectionConfig[b.dataset.sectionId] || {};
                const aSort = Number(sa.sort ?? defaultSort[a.dataset.sectionId] ?? 999);
                const bSort = Number(sb.sort ?? defaultSort[b.dataset.sectionId] ?? 999);
                return aSort - bSort;
            }).forEach(section => dashboard.appendChild(section));
            sections.forEach(section => {
                const meta = dashboardSectionConfig[section.dataset.sectionId] || {};
                const alwaysVisible = ['hero', 'stats', 'status_matrix', 'device_focus', 'ai_model', 'apple_audio', 'alerts', 'snmp', 'server_compact', 'energy_trend'].includes(section.dataset.sectionId);
                section.style.display = !alwaysVisible && meta.visible === false ? 'none' : '';
            });
        }
        let dashboardMasonryTimer = 0;
        let dashboardMasonryObserver = null;
        let dashboardResizeObserver = null;
        function applyDashboardMasonry() {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard || getActiveViewId() !== 'dashboard') return;
            if (!document.body.classList.contains('dashboard-masonry-mode')) {
                Array.from(dashboard.querySelectorAll('[data-section-id]')).forEach(section => {
                    section.style.removeProperty('--smart-dashboard-row-span');
                    section.style.gridRowEnd = '';
                    section.style.gridRowStart = '';
                    section.style.gridColumnStart = '';
                    section.style.gridColumnEnd = '';
                });
                return;
            }
            const style = window.getComputedStyle ? window.getComputedStyle(dashboard) : null;
            const rowHeight = style ? parseFloat(style.gridAutoRows || '0') : 0;
            const rowGap = style ? parseFloat(style.rowGap || style.gap || '0') : 0;
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.forEach(section => {
                section.style.removeProperty('--smart-dashboard-row-span');
                section.style.gridRowEnd = '';
                section.style.gridRowStart = '';
                section.style.gridColumnStart = '';
                section.style.gridColumnEnd = '';
                if (!document.body.classList.contains('dashboard-compact-mode') || !rowHeight) return;
                if (section.style.display === 'none') return;
                const rect = section.getBoundingClientRect();
                if (!rect.height) return;
                const span = Math.max(1, Math.ceil((rect.height + rowGap) / (rowHeight + rowGap)));
                section.style.setProperty('--smart-dashboard-row-span', `span ${span}`);
                section.style.gridRowEnd = `span ${span}`;
            });
        }
        function scheduleDashboardMasonry(delay = 80) {
            window.clearTimeout(dashboardMasonryTimer);
            dashboardMasonryTimer = window.setTimeout(() => applyDashboardMasonry(), delay);
        }
        function initDashboardMasonryObservers() {
            if (!document.body.classList.contains('dashboard-masonry-mode')) {
                applyDashboardMasonry();
                return;
            }
            applyDashboardMasonry();
            if (dashboardResizeObserver || typeof ResizeObserver !== 'function') return;
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard) return;
            dashboardResizeObserver = new ResizeObserver(() => scheduleDashboardMasonry(80));
            Array.from(dashboard.querySelectorAll('[data-section-id]')).forEach(section => dashboardResizeObserver.observe(section));
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
            scheduleDashboardMasonry(80);
        }
        function findNavElementByView(viewId) {
            return Array.from(document.querySelectorAll('.nav-menu li')).find(el => String(el.getAttribute('onclick') || '').includes(`switchTab('${viewId}'`)) || null;
        }
        function normalizeViewIdCandidate(value) {
            const safeView = String(value || '').replace(/^#?view-/, '').replace(/[^a-zA-Z0-9_-]/g, '');
            return safeView && document.getElementById('view-' + safeView) ? safeView : null;
        }
        function getInitialViewFromUrl() {
            const params = new URLSearchParams(window.location.search || '');
            const hashView = normalizeViewIdCandidate(String(window.location.hash || '').trim());
            if (hashView) return hashView;
            return normalizeViewIdCandidate(String(params.get('view') || params.get('tab') || '').trim());
        }
        function getViewTitleFromNav(navEl, fallback = '') {
            const onclickText = String(navEl?.getAttribute('onclick') || '');
            const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
            return match ? match[2] : fallback;
        }
        function updateHvacStatus(showError = false) {
            if (!hvacConfigs.length) return Promise.resolve({});
            return fetchJson('/api/hvac/status?refresh_stale=1', {}, '空调状态读取失败')
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
        let isWizDragging = false;
        let wizOffsetX = 0;
        let wizOffsetY = 0;
        function ensureAiWizardModalShell() {
            if (document.getElementById('aiWizardModal')) return;
            document.body.insertAdjacentHTML('beforeend', `
                <div id="aiWizardModal" class="wizard-overlay">
                    <div class="wizard-box" id="wizardBox">
                        <div id="wizardHeader" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; cursor: move; background: rgba(59, 130, 246, 0.15); padding: 10px 15px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3);">
                            <h3 style="color:var(--brand-blue); margin:0; font-size: 15px; pointer-events: none;">智能标定向导</h3>
                            <button class="btn-base" style="background:transparent; border:1px solid #475569; padding:2px 8px; font-size:12px; cursor: pointer;" onclick="closeWizard()">关闭</button>
                        </div>
                        <div class="wizard-step" id="step1-card">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;"><h4 style="margin:0;">1. 标定“完全关闭”</h4><span id="wiz-status-closed" style="font-size:12px; color:var(--warning);">待操作</span></div>
                            <button class="btn-base btn-success wizard-btn" onclick="captureWizard('closed', 'wiz-status-closed')">拍下“关闭”基准图</button>
                        </div>
                        <div class="wizard-step" id="step2-card" style="opacity:0.4; pointer-events:none;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;"><h4 style="margin:0;">2. 标定“完全打开”</h4><span id="wiz-status-open" style="font-size:12px; color:var(--warning);">待操作</span></div>
                            <button class="btn-base btn-danger wizard-btn" onclick="captureWizard('open', 'wiz-status-open')">拍下“打开”基准图</button>
                        </div>
                        <div class="wizard-step" style="border-color: var(--brand-blue); margin-bottom:0;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;"><h4 style="margin:0; color:var(--brand-blue);">3. 生成特征模型</h4></div>
                            <button id="btnWizardRecord" class="btn-base btn-ai wizard-btn" onclick="applyAiCalibration()">一键生成 AI 推演模型</button>
                        </div>
                    </div>
                </div>
            `);
            const wizardBox = document.getElementById('wizardBox');
            const wizardHeader = document.getElementById('wizardHeader');
            if (!wizardBox || !wizardHeader || wizardHeader.dataset.dragBound === '1') return;
            wizardHeader.dataset.dragBound = '1';
            wizardHeader.addEventListener('mousedown', event => {
                if (event.target.tagName.toLowerCase() === 'button') return;
                isWizDragging = true;
                wizOffsetX = event.clientX - wizardBox.offsetLeft;
                wizOffsetY = event.clientY - wizardBox.offsetTop;
                wizardBox.style.transition = 'none';
                wizardBox.style.opacity = '0.9';
            });
        }
        function openWizard() {
            ensureAiWizardModalShell();
            document.getElementById('aiWizardModal').style.display = 'block';
            document.getElementById('step1-card').style.opacity = '1';
            document.getElementById('step1-card').style.pointerEvents = 'auto';
            document.getElementById('step2-card').style.opacity = '0.4';
            document.getElementById('step2-card').style.pointerEvents = 'none';
        }
        function closeWizard() {
            const modal = document.getElementById('aiWizardModal');
            if (modal) modal.style.display = 'none';
        }
        function setWizardStatus(elementId, text, isError = false) {
            const el = document.getElementById(elementId);
            if (!el) return;
            el.textContent = text;
            el.style.color = isError ? 'var(--danger)' : 'var(--success)';
        }
        function captureWizard(state, statusId) {
            ensureAiWizardModalShell();
            setWizardStatus(statusId, '拍摄中...');
            return fetchJsonLoose(`/api/ai_wizard/capture/${encodeURIComponent(state)}`, { method: 'POST' }, '门禁标定拍摄失败')
                .then(data => {
                    const ok = data.status === 'success' || data.ok === true;
                    setWizardStatus(statusId, ok ? '已完成' : (data.msg || '失败'), !ok);
                    if (ok && state === 'closed') {
                        const next = document.getElementById('step2-card');
                        if (next) {
                            next.style.opacity = '1';
                            next.style.pointerEvents = 'auto';
                        }
                    }
                    showToast(data.msg || (ok ? '标定参考图已保存' : '标定失败'), !ok);
                    return data;
                })
                .catch(err => {
                    setWizardStatus(statusId, '失败', true);
                    showToast(translateApiError(err?.message, '门禁标定拍摄失败'), true);
                    return null;
                });
        }
        function applyAiCalibration() {
            ensureAiWizardModalShell();
            const btn = document.getElementById('btnWizardRecord');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '生成中...';
            }
            return fetchJsonLoose('/api/ai_wizard/apply_model', { method: 'POST' }, '门禁标定模型生成失败')
                .then(data => {
                    const ok = data.status === 'success' || data.ok === true;
                    showToast(data.msg || (ok ? 'AI 标定模型已生成' : 'AI 标定模型生成失败'), !ok);
                    return data;
                })
                .catch(err => {
                    showToast(translateApiError(err?.message, '门禁标定模型生成失败'), true);
                    return null;
                })
                .finally(() => {
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = '一键生成 AI 推演模型';
                    }
                });
        }
        document.addEventListener('mousemove', event => {
            if (!isWizDragging) return;
            const wizardBox = document.getElementById('wizardBox');
            if (!wizardBox) return;
            wizardBox.style.left = (event.clientX - wizOffsetX) + 'px';
            wizardBox.style.top = (event.clientY - wizOffsetY) + 'px';
            wizardBox.style.right = 'auto';
        });
        document.addEventListener('mouseup', () => {
            if (!isWizDragging) return;
            isWizDragging = false;
            const wizardBox = document.getElementById('wizardBox');
            if (wizardBox) {
                wizardBox.style.transition = 'opacity 0.2s';
                wizardBox.style.opacity = '1';
            }
        });
        Object.assign(window, { openWizard, closeWizard, captureWizard, applyAiCalibration });

        // 强电控制、状态回读和通道渲染已迁移到 static/js/views/power-meter-runtime.js。
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
        function ensureProjectorRemoteModalShell() {
            if (document.getElementById('projectorRemoteModal')) return;
            document.body.insertAdjacentHTML('beforeend', `
                <div id="projectorRemoteModal" class="wizard-overlay">
                    <div class="modal-box-center projector-remote-shell">
                        <div class="projector-remote-header">
                            <div>
                                <div class="projector-remote-title" id="projectorRemoteTitle">投影机遥控器</div>
                                <div class="projector-remote-subtitle" id="projectorRemoteSubtitle">正在加载设备信息...</div>
                            </div>
                            <button class="btn-base" style="background:#334155;" onclick="closeProjectorRemote()">关闭</button>
                        </div>
                        <div id="projectorRemoteContent" class="projector-remote-body">
                            <div class="projector-empty-tip" style="grid-column:1/-1; margin:18px;">正在加载遥控器面板...</div>
                        </div>
                    </div>
                </div>
            `);
        }
        window.openProjectorRemote = function(projId) {
            ensureProjectorRemoteModalShell();
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
            syncHomeCarouselUi();
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
            guardFrontendStep('bootstrap.dashboard_shell', () => ensureDashboardShellRendered());
            guardFrontendStep('bootstrap.home_carousel_switch', () => initHomeCarouselSwitch());
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
                if (initialView && initialView !== 'dashboard') refreshDashboardServerCompactFallback();
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
            guardFrontendStep('bootstrap.sidebar_carousel', () => {
                if (!isHomeCarouselEnabled() && isSidebarCarouselEnabled()) startSidebarCarousel();
            }, '页面轮播初始化失败');
            window.addEventListener('hashchange', () => {
                guardFrontendStep('route.hashchange', () => {
                    const nextView = getInitialViewFromUrl();
                    if (!nextView || nextView === getActiveViewId()) return;
                    const targetNav = findNavElementByView(nextView);
                    switchTab(nextView, getViewTitleFromNav(targetNav, '中控系统'), targetNav);
                }, '页面锚点切换异常');
            });
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
        }, () => getActiveViewId() === 'power');
        registerPollingTask('meter', 4500, () => updateMeterCenter(), () => getActiveViewId() === 'meter');
        registerPollingTask('ups', 4500, () => ensureViewReady('ups').then(() => updateUpsStatus()), () => getActiveViewId() === 'ups');
        registerPollingTask('hy_edge', 6000, () => window.updateHyEdgeStatus(), () => false);
        registerPollingTask('dashboard_summary', 5000, () => updateDashboardSummary(), () => getActiveViewId() === 'dashboard');
        registerPollingTask('proxy', 5000, () => ensureViewReady('proxy').then(() => updateProxyStatus()), () => getActiveViewId() === 'proxy');
        registerPollingTask('snmp', 9000, () => updateSnmpStatus(), () => ['snmp', 'camera_preview'].includes(getActiveViewId()));
        registerPollingTask('hvac', 5000, () => {
            const modules = getActiveViewId() === 'hvac' ? ['hvac-view'] : ['hvac-summary-view'];
            return ensureModulesReady(modules, '空调模块').then(() => updateHvacStatus());
        }, () => getActiveViewId() === 'hvac');
        registerPollingTask('light', 2200, () => {
            const modules = getActiveViewId() === 'light' ? ['light-runtime', 'light-scene-view'] : ['light-runtime'];
            return ensureModulesReady(modules, '灯光状态模块')
                .then(() => {
                    if (getActiveViewId() === 'light') renderLightSceneView('light');
                    return updateLightData();
                });
        }, () => getActiveViewId() === 'light');
        registerPollingTask('node_red', 5000, () => ensureViewReady('universal').then(() => updateNodeRedDevices()), () => getActiveViewId() === 'universal');
        registerPollingTask('server', 5000, () => ensureViewReady('server').then(() => updateServerData()), () => getActiveViewId() === 'server');
        registerPollingTask('door', 1200, () => updateDoorStatus(), () => getActiveViewId() === 'door');
        registerPollingTask('env', 2000, () => window.updateEnvData(), () => ['env', 'hvac'].includes(getActiveViewId()));
        registerPollingTask('automation', 4000, () => {
            loadAutomationStatus();
            if (getActiveViewId() === 'auto') window.loadAutomationLogs();
        }, () => getActiveViewId() === 'auto');
        registerPollingTask('projector', 6000, () => {
            const modules = getActiveViewId() === 'projector' ? ['projector-runtime', 'projector-view'] : ['projector-runtime', 'projector-summary-view'];
            return ensureModulesReady(modules, '投影模块').then(() => updateProjectorStatus());
        }, () => getActiveViewId() === 'projector');
        registerPollingTask('sequencer', 4500, () => ensureModulesReady(['sequencer-runtime'], '时序电源运行时模块').then(() => updateSequencerStatus()), () => getActiveViewId() === 'sequencer');
        registerPollingTask('screen', 4500, () => ensureModulesReady(['screen-runtime'], '幕布运行时模块').then(() => updateScreenStatus()), () => getActiveViewId() === 'screen');
        registerPollingTask('apple_audio', 3200, () => ensureViewReady('apple_audio').then(() => loadAppleAudioStatus()), () => ['apple_audio'].includes(getActiveViewId()));
        registerPollingTask('logs', 5000, () => window.updateDashboardLogs(), () => getActiveViewId() === 'logs');
        registerPollingTask('event_logs', 5000, () => window.refreshEventLogs(false), () => getActiveViewId() === 'logs');

        // AI_BRIDGE: door_runtime
        // 门禁状态、视频取流、区域框选和真实开关门控制已迁移到 static/js/views/door-runtime.js。
        // 保留全局函数名是为了兼容模板内联 onclick 与历史轮询入口。

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

        function formatCompactAgeFromSec(ageSec) {
            const value = Number(ageSec);
            if (!Number.isFinite(value)) return '';
            if (value < 60) return `${Math.round(value)}秒前`;
            if (value < 3600) return `${Math.round(value / 60)}分钟前`;
            if (value < 86400) return `${Math.round(value / 3600)}小时前`;
            return `${Math.round(value / 86400)}天前`;
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
            return ensureAutomationRuntimeReady(contextLabel)
                .then(runtimeApi => {
                    if (runtimeApi?.withAutomationView) return runtimeApi.withAutomationView(callback, contextLabel, getAutomationRuntimeContext());
                    return ensureAutomationViewReady(contextLabel).then(api => {
                        if (api && typeof callback === 'function') return callback(api, getAutomationRuntimeContext());
                        return null;
                    });
                })
                .catch(() => null);
        }
        window.toggleAutomation = (ruleId, isEnabled) => withAutomationView(
            (api, ctx) => api.toggleAutomation?.(ruleId, isEnabled, ctx),
            '自动化开关模块'
        );
        window.toggleAutomationEditor = (ruleId, forceOpen = null) => withAutomationView(
            (api, ctx) => api.toggleAutomationEditor?.(ruleId, forceOpen, ctx),
            '自动化编辑模块'
        );
        window.saveAutomationRule = ruleId => withAutomationView(
            (api, ctx) => api.saveAutomationRule?.(ruleId, ctx),
            '自动化保存模块'
        );
        window.openAutomationNodeCanvas = ruleId => withAutomationView(
            (api, ctx) => api.openAutomationNodeCanvas?.(ruleId, ctx),
            '自动化节点画布模块'
        );
        window.closeAutomationNodeCanvas = () => withAutomationView(
            api => api.closeAutomationNodeCanvas?.(),
            '自动化节点画布模块'
        );
        window.toggleAutomationNodeView = (ruleId = null, forceOpen = null) => withAutomationView(
            (api, ctx) => api.toggleAutomationNodeView?.(ruleId, forceOpen, ctx),
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
                return ensureAutomationRuntimeReady('自动化节点画布模块')
                    .then(runtimeApi => {
                        const viewApi = getAutomationViewApi();
                        if (!viewApi?.handleAutomationCanvasNodeClick) {
                            event?.preventDefault?.();
                            return false;
                        }
                        const ctx = runtimeApi?.buildAutomationViewContext
                            ? runtimeApi.buildAutomationViewContext(getAutomationRuntimeContext())
                            : getAutomationRuntimeContext();
                        return viewApi.handleAutomationCanvasNodeClick(event, nodeId, ctx);
                    })
                    .catch(() => {
                        event?.preventDefault?.();
                        return false;
                    });
            }
            return api.handleAutomationCanvasNodeClick(event, nodeId, getAutomationRuntimeContext());
        };
