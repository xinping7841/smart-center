(function installSmartCenterUtils(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const inFlight = new Map();

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function translateApiError(error, fallbackText = '请求失败') {
        const text = String(error ?? '').trim();
        if (!text) return fallbackText;
        const map = {
            login_required: '当前会话未登录，请先登录后再操作',
            account_disabled: '当前账号已停用',
            permission_denied: '当前账号没有此功能权限',
            permission_time_restricted: '当前时段不允许执行此操作',
            account_frozen: '当前账号已冻结',
            account_temporarily_disabled: '当前账号已被临时停用',
            account_temporarily_disabled_until: '当前账号处于临时停用时段',
            temporary_control_blocked: '当前账号的控制权限已被临时关闭',
            outside_control_schedule: '当前不在允许控制的时间段内',
            permission_not_granted: '当前账号没有此功能权限',
        };
        if (map[text]) return map[text];
        if (text.startsWith('http_')) {
            const code = text.split('_')[1] || '';
            return `请求失败（HTTP ${code}）`;
        }
        return text;
    }

    async function parseJsonResponse(response, fallbackText = '请求失败', options = {}) {
        let data = {};
        try {
            data = await response.json();
        } catch (_) {
            data = {};
        }
        const allowBusinessError = !!options.allowBusinessError;
        if (!response.ok || (!allowBusinessError && data?.ok === false)) {
            const message = data?.msg || data?.message || data?.error || fallbackText;
            throw new Error(translateApiError(message, fallbackText));
        }
        return data;
    }

    function getFetchJsonDedupeKey(url, options = {}) {
        const method = String(options?.method || 'GET').toUpperCase();
        if (method !== 'GET') return '';
        const body = options?.body;
        if (body !== undefined && body !== null) return '';
        const headers = options?.headers;
        let headerKey = '';
        if (headers instanceof Headers) {
            headerKey = Array.from(headers.entries()).sort().map(([k, v]) => `${k}:${v}`).join('|');
        } else if (headers && typeof headers === 'object') {
            headerKey = Object.keys(headers).sort().map(k => `${k}:${headers[k]}`).join('|');
        }
        return `${method} ${url} ${headerKey}`;
    }

    async function fetchJson(url, options = {}, fallbackText = '请求失败', parseOptions = {}) {
        const dedupeKey = getFetchJsonDedupeKey(url, options);
        if (dedupeKey && inFlight.has(dedupeKey)) {
            return inFlight.get(dedupeKey);
        }
        const requestPromise = fetch(url, options)
            .then(response => parseJsonResponse(response, fallbackText, parseOptions))
            .finally(() => {
                if (dedupeKey) inFlight.delete(dedupeKey);
            });
        if (dedupeKey) inFlight.set(dedupeKey, requestPromise);
        return requestPromise;
    }

    function fetchJsonLoose(url, options = {}, fallbackText = '请求失败') {
        return fetchJson(url, options, fallbackText, { allowBusinessError: true });
    }

    function postJsonLoose(url, payload, fallbackText = '请求失败') {
        return fetchJsonLoose(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }, fallbackText);
    }

    const api = {
        escapeHtml,
        translateApiError,
        parseJsonResponse,
        getFetchJsonDedupeKey,
        fetchJson,
        fetchJsonLoose,
        postJsonLoose,
    };

    SmartCenter.utils = Object.assign({}, SmartCenter.utils || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('core.utils', {
            kind: 'core',
            exports: Object.keys(api),
            source: 'static/js/core/utils.js',
        });
    }

    Object.assign(global, api);
})(window);
