// AI_MODULE: projector_runtime
// AI_PURPOSE: 投影机状态缓存、轮询刷新、遥控器打开和控制指令胶水层。
// AI_BOUNDARY: 不渲染完整投影机页面细节；摘要由 projector-summary.js 渲染，详情由 projector.js 渲染。
// AI_DATA_FLOW: /api/projector/status -> projectorStatusCache -> dashboard/page/remote render helpers。
// AI_RUNTIME: dashboard 投影区接近视口或进入 projector 视图时按需加载。
// AI_RISK: 高，包含真实投影机控制链路；必须保留权限校验、payload 和状态回读。
// AI_SEARCH_KEYWORDS: projector runtime, projector status cache, projector control, projector remote.

(function installSmartCenterProjectorRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.projectorRuntime = Object.assign({
        statusCache: {},
        currentRemoteId: null,
    }, SmartCenter.projectorRuntime || {});

    let projectorStatusCache = state.statusCache || {};
    let currentProjectorRemoteId = state.currentRemoteId || null;

    function getContext(context = {}) {
        return Object.assign({
            projectorConfigs: Array.isArray(global.configData?.projectors) ? global.configData.projectors : [],
            getActiveViewId: global.getActiveViewId || (() => 'dashboard'),
            ensureModulesReady: (modules, label) => SmartCenter.ensureModules ? SmartCenter.ensureModules(modules) : Promise.resolve([]),
            fetchJson: utils.fetchJson || global.fetchJson,
            postJsonLoose: utils.postJsonLoose || global.postJsonLoose,
            ensurePermission: utils.ensurePermission || global.ensurePermission,
            showToast: utils.showToast || global.showToast || (() => {}),
            escapeHtml: utils.escapeHtml || global.escapeHtml || (value => String(value ?? '')),
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            getDeviceStatusMeta: utils.getDeviceStatusMeta || global.getDeviceStatusMeta,
            getCardStateClass: utils.getCardStateClass || global.getCardStateClass,
        }, context || {});
    }

    function getProjectorViewContext(context = {}) {
        const ctx = getContext(context);
        return {
            projectorConfigs: ctx.projectorConfigs,
            statusCache: projectorStatusCache,
            getStatus: projId => projectorStatusCache[projId] || null,
            escapeHtml: ctx.escapeHtml,
            getPermissionDisabledClass: ctx.getPermissionDisabledClass,
            getPermissionDisabledAttrs: ctx.getPermissionDisabledAttrs,
            getDeviceStatusMeta: ctx.getDeviceStatusMeta,
            getCardStateClass: ctx.getCardStateClass,
        };
    }

    function getSummaryApi() {
        return SmartCenter.projectorSummary || SmartCenter.projector || null;
    }

    function getFullApi() {
        return SmartCenter.projector || null;
    }

    function renderProjectorRemoteById(projId, context = {}) {
        const fullApi = getFullApi();
        const runtimeContext = getProjectorViewContext(context);
        if (fullApi && typeof fullApi.renderProjectorRemote === 'function') {
            fullApi.renderProjectorRemote(projId, runtimeContext);
        } else if (typeof global.renderProjectorRemote === 'function') {
            global.renderProjectorRemote(projId, runtimeContext);
        }
    }

    function renderProjectorCards(context = {}) {
        const ctx = getContext(context);
        const runtimeContext = getProjectorViewContext(ctx);
        const summaryApi = getSummaryApi();
        const fullApi = getFullApi();

        if (summaryApi && typeof summaryApi.renderProjectorCards === 'function') {
            summaryApi.renderProjectorCards('dashboard-projector-grid', 'dashboard', runtimeContext);
        }
        if (ctx.getActiveViewId() === 'projector' && fullApi && typeof fullApi.renderProjectorCards === 'function') {
            fullApi.renderProjectorCards('projector-page-grid', 'page', runtimeContext);
        }

        const projectorApi = summaryApi || fullApi;
        const dashboardProjectors = projectorApi && typeof projectorApi.getDashboardProjectors === 'function'
            ? projectorApi.getDashboardProjectors(runtimeContext)
            : (ctx.projectorConfigs || []).filter(proj => proj.visible !== false && proj.dashboard_visible !== false);
        const onlineCount = dashboardProjectors.filter(proj => (projectorStatusCache[proj.id] || {}).online).length;
        const dashProjectorOnline = document.getElementById('dash-projector-online');
        if (dashProjectorOnline) dashProjectorOnline.innerText = onlineCount;
        const dashProjectorTotal = document.getElementById('dash-projector-total');
        if (dashProjectorTotal) dashProjectorTotal.innerText = dashboardProjectors.length;

        if (currentProjectorRemoteId) {
            const ensureModulesReady = ctx.ensureModulesReady;
            ensureModulesReady(['projector-view'], '投影遥控器模块')
                .then(() => renderProjectorRemoteById(currentProjectorRemoteId, ctx))
                .catch(() => {});
        }
    }

    function updateProjectorStatus(context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.fetchJson !== 'function') {
            console.error('投影机状态更新失败', new Error('fetchJson_missing'));
            return Promise.resolve(null);
        }
        return ctx.fetchJson('/api/projector/status', {}, '投影机状态读取失败')
            .then(data => {
                projectorStatusCache = data || {};
                state.statusCache = projectorStatusCache;
                global.projectorStatusCache = projectorStatusCache;
                renderProjectorCards(ctx);
                return projectorStatusCache;
            })
            .catch(err => {
                console.error('投影机状态更新失败', err);
                return null;
            });
    }

    function openProjectorRemote(projId, context = {}) {
        const ctx = getContext(context);
        currentProjectorRemoteId = String(projId || '');
        state.currentRemoteId = currentProjectorRemoteId;
        const modal = document.getElementById('projectorRemoteModal');
        if (modal) modal.style.display = 'block';
        return ctx.ensureModulesReady(['projector-view'], '投影遥控器模块')
            .then(() => renderProjectorRemoteById(currentProjectorRemoteId, ctx))
            .catch(err => {
                console.error('投影遥控器模块加载失败', err);
                ctx.showToast('投影遥控器模块加载失败，请刷新后重试', true);
            });
    }

    function closeProjectorRemote() {
        const modal = document.getElementById('projectorRemoteModal');
        if (modal) modal.style.display = 'none';
        currentProjectorRemoteId = null;
        state.currentRemoteId = null;
    }

    function refreshProjectorStatusAfterCommand(context = {}) {
        updateProjectorStatus(context);
        [700, 1800, 4200].forEach(delay => setTimeout(() => updateProjectorStatus(context), delay));
    }

    function fireProjectorCommand(devId, payload, format, name = '', context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.ensurePermission === 'function' && !ctx.ensurePermission('projector.control', '操作投影机')) return Promise.resolve(null);
        if (typeof ctx.postJsonLoose !== 'function') {
            ctx.showToast('投影控制运行库缺少请求方法', true);
            return Promise.resolve(null);
        }
        ctx.showToast('投影指令下发中...', false);
        return ctx.postJsonLoose('/api/projector/control', {
            device_id: devId,
            command: { payload, format, name },
        }, '投影指令下发失败')
            .then(data => {
                ctx.showToast(data.success ? '执行成功' : (`执行失败: ${data.response || data.msg || '未知错误'}`), !data.success);
                if (data.success) refreshProjectorStatusAfterCommand(ctx);
                return data;
            })
            .catch(err => {
                console.error('投影指令下发失败', err);
                ctx.showToast('网络请求失败', true);
                return null;
            });
    }

    const api = {
        getProjectorViewContext,
        updateProjectorStatus,
        openProjectorRemote,
        closeProjectorRemote,
        refreshProjectorStatusAfterCommand,
        fireProjectorCommand,
    };

    Object.assign(state, api);
    if (typeof global.getProjectorViewContext !== 'function') {
        global.getProjectorViewContext = () => getProjectorViewContext();
    }
    if (typeof global.openProjectorRemote !== 'function') {
        global.openProjectorRemote = projId => openProjectorRemote(projId);
    }
    if (typeof global.closeProjectorRemote !== 'function') {
        global.closeProjectorRemote = () => closeProjectorRemote();
    }
    if (typeof global.refreshProjectorStatusAfterCommand !== 'function') {
        global.refreshProjectorStatusAfterCommand = () => refreshProjectorStatusAfterCommand();
    }
    if (typeof global.fireProjectorCommand !== 'function') {
        global.fireProjectorCommand = (devId, payload, format, name = '') => fireProjectorCommand(devId, payload, format, name);
    }
    if (typeof global.updateProjectorStatus !== 'function') {
        global.updateProjectorStatus = () => updateProjectorStatus();
    }

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('projector-runtime', {
            kind: 'runtime',
            exports: Object.keys(api),
            source: 'static/js/views/projector-runtime.js',
            risk: 'high',
        });
    }
})(window);
