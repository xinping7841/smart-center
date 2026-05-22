// AI_MODULE: frontend_bootstrap
// AI_PURPOSE: 浏览器端 SmartCenter 命名空间、模块注册、ready 队列和全局错误兜底。
// AI_BOUNDARY: 不写具体页面业务；页面逻辑放在 static/js/views/*。
// AI_DATA_FLOW: 各 view 模块 registerModule -> SmartCenter.modules -> index.html 统一调用。
// AI_RUNTIME: 在 templates/index.html 中优先加载，必须在其他 view 脚本之前可用。
// AI_RISK: 中，改坏会导致全站前端模块无法注册或 ready 回调不执行。
// AI_SEARCH_KEYWORDS: SmartCenter, registerModule, onReady, frontend bootstrap.

(function bootstrapSmartCenter(global) {
    'use strict';

    const existing = global.SmartCenter || {};
    const modules = existing.modules || {};
    const readyQueue = existing.readyQueue || [];

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
        registerModule,
        getModule,
        onReady,
    });

    global.SmartCenter = existing;
    document.addEventListener('DOMContentLoaded', flushReadyQueue, { once: true });
})(window);
