// AI_MODULE: frontend_bootstrap
// AI_PURPOSE: 浏览器端 SmartCenter 命名空间、模块注册、ready 队列和全局错误兜底。
// AI_BOUNDARY: 不写具体页面业务；页面逻辑放在 static/js/views/*。
// AI_DATA_FLOW: 各 view 模块 registerModule -> SmartCenter.modules；按需模块 registerLazyModule -> ensureViewModules。
// AI_RUNTIME: 在 templates/index.html 中优先加载，必须在其他 view 脚本之前可用。
// AI_RISK: 中，改坏会导致全站前端模块无法注册或 ready 回调不执行。
// AI_SEARCH_KEYWORDS: SmartCenter, registerModule, onReady, frontend bootstrap, lazy-load.

(function bootstrapSmartCenter(global) {
    'use strict';

    const existing = global.SmartCenter || {};
    const modules = existing.modules || {};
    const readyQueue = existing.readyQueue || [];
    const lazyModules = existing.lazyModules || {};
    const lazyModuleLoads = existing.lazyModuleLoads || {};
    const viewModules = existing.viewModules || {};

    function registerModule(name, definition) {
        const key = String(name || '').trim();
        if (!key) return null;
        modules[key] = Object.assign({ name: key, registeredAt: new Date().toISOString() }, definition || {});
        return modules[key];
    }

    function getModule(name) {
        return modules[String(name || '').trim()] || null;
    }

    function onReady(callback) {
        if (typeof callback !== 'function') return;
        if (document.readyState === 'loading') {
            readyQueue.push(callback);
            return;
        }
        callback(existing);
    }

    function normalizeAssetList(value) {
        if (!value) return [];
        return Array.isArray(value) ? value.filter(Boolean) : [value].filter(Boolean);
    }

    function registerLazyModule(name, definition) {
        const key = String(name || '').trim();
        if (!key) return null;
        const nextDefinition = Object.assign({}, definition || {});
        nextDefinition.scripts = normalizeAssetList(nextDefinition.scripts);
        nextDefinition.styles = normalizeAssetList(nextDefinition.styles);
        lazyModules[key] = nextDefinition;
        return lazyModules[key];
    }

    function registerViewModules(viewId, moduleNames) {
        const key = String(viewId || '').trim();
        if (!key) return [];
        viewModules[key] = normalizeAssetList(moduleNames).map(item => String(item || '').trim()).filter(Boolean);
        return viewModules[key];
    }

    function getLazyUtils() {
        const smartCenter = global.SmartCenter || existing;
        return smartCenter.utils || existing.utils || {};
    }

    function loadScriptAsset(asset) {
        const utils = getLazyUtils();
        if (!utils || typeof utils.loadScriptOnce !== 'function') {
            return Promise.reject(new Error('lazy_loader_utils_unavailable'));
        }
        if (typeof asset === 'string') return utils.loadScriptOnce(asset);
        const src = String((asset || {}).src || '').trim();
        if (!src) return Promise.resolve(true);
        return utils.loadScriptOnce(src, asset || {});
    }

    function loadStyleAsset(asset) {
        const utils = getLazyUtils();
        if (!utils || typeof utils.loadStylesheetOnce !== 'function') {
            return Promise.reject(new Error('lazy_loader_utils_unavailable'));
        }
        const href = typeof asset === 'string' ? asset : String((asset || {}).href || '').trim();
        if (!href) return Promise.resolve(true);
        return utils.loadStylesheetOnce(href);
    }

    function ensureModules(names) {
        const keys = normalizeAssetList(names).map(item => String(item || '').trim()).filter(Boolean);
        if (!keys.length) return Promise.resolve([]);
        return Promise.all(keys.map(key => {
            if (lazyModuleLoads[key]) return lazyModuleLoads[key];
            const definition = lazyModules[key];
            if (!definition) return Promise.reject(new Error(`lazy_module_not_registered:${key}`));
            const loadPromise = Promise.all((definition.styles || []).map(loadStyleAsset))
                .then(() => (definition.scripts || []).reduce(
                    (chain, scriptAsset) => chain.then(() => loadScriptAsset(scriptAsset)),
                    Promise.resolve(true)
                ))
                .then(() => ({ key, loadedAt: new Date().toISOString() }))
                .catch(err => {
                    delete lazyModuleLoads[key];
                    throw err;
                });
            lazyModuleLoads[key] = loadPromise;
            return loadPromise;
        }));
    }

    function ensureViewModules(viewId) {
        const key = String(viewId || '').trim();
        return ensureModules(viewModules[key] || []);
    }

    function flushReadyQueue() {
        while (readyQueue.length) {
            const callback = readyQueue.shift();
            try {
                callback(existing);
            } catch (err) {
                if (typeof global.reportFrontendError === 'function') {
                    global.reportFrontendError('smart_center.ready', err);
                } else {
                    console.error('[smart_center.ready]', err);
                }
            }
        }
    }

    Object.assign(existing, {
        version: '2026.05.22-stage2',
        modules,
        readyQueue,
        lazyModules,
        lazyModuleLoads,
        viewModules,
        registerModule,
        getModule,
        onReady,
        registerLazyModule,
        registerViewModules,
        ensureModules,
        ensureViewModules,
    });

    global.SmartCenter = existing;
    document.addEventListener('DOMContentLoaded', flushReadyQueue, { once: true });
})(window);
