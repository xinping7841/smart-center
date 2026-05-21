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

    function parseDateTimeText(value) {
        const text = String(value || '').trim();
        if (!text) return null;
        const normalized = text.replace(' ', 'T');
        const dt = new Date(normalized);
        return Number.isNaN(dt.getTime()) ? null : dt;
    }

    function formatRelativeSeconds(seconds) {
        const total = Math.max(0, Number(seconds) || 0);
        if (total < 1) return '0秒';
        if (total < 60) return `${Math.round(total)}秒`;
        const minutes = Math.floor(total / 60);
        const remainSeconds = Math.round(total % 60);
        if (minutes < 60) return remainSeconds > 0 ? `${minutes}分${remainSeconds}秒` : `${minutes}分钟`;
        const hours = Math.floor(minutes / 60);
        const remainMinutes = minutes % 60;
        return remainMinutes > 0 ? `${hours}小时${remainMinutes}分钟` : `${hours}小时`;
    }

    function formatDateTimeText(value) {
        if (!value) return '未上报';
        const dt = new Date(String(value).replace(' ', 'T'));
        if (Number.isNaN(dt.getTime())) return String(value);
        return dt.toLocaleString('zh-CN', { hour12: false });
    }

    function formatTimeShort(value) {
        if (!value) return '--';
        const dt = new Date(String(value).replace(' ', 'T'));
        if (Number.isNaN(dt.getTime())) return String(value);
        return dt.toLocaleTimeString('zh-CN', { hour12: false });
    }

    function toFiniteNumber(value) {
        const num = Number(value);
        return Number.isFinite(num) ? num : null;
    }

    function getTodayTargetDateTime(timeText = '20:00') {
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

    function formatFixedNumber(value, digits = 0, suffix = '', fallback = '--') {
        const num = Number(value);
        if (!Number.isFinite(num)) return suffix ? `${fallback}${suffix}` : fallback;
        return `${num.toFixed(digits)}${suffix}`;
    }

    const api = {
        escapeHtml,
        translateApiError,
        parseJsonResponse,
        getFetchJsonDedupeKey,
        fetchJson,
        fetchJsonLoose,
        postJsonLoose,
        parseDateTimeText,
        formatRelativeSeconds,
        formatDateTimeText,
        formatTimeShort,
        toFiniteNumber,
        getTodayTargetDateTime,
        formatCountdownText,
        formatFixedNumber,
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
