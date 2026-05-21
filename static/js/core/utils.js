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

    function isNowInTimeRange(startText, endText, now = new Date()) {
        if (!startText || !endText) return true;
        const parse = text => {
            const [h, m] = String(text || '').split(':');
            return { h: Number(h), m: Number(m) };
        };
        const start = parse(startText);
        const end = parse(endText);
        if (!Number.isFinite(start.h) || !Number.isFinite(start.m) || !Number.isFinite(end.h) || !Number.isFinite(end.m)) return true;
        const nowMinutes = now.getHours() * 60 + now.getMinutes();
        const startMinutes = start.h * 60 + start.m;
        const endMinutes = end.h * 60 + end.m;
        if (startMinutes <= endMinutes) return nowMinutes >= startMinutes && nowMinutes <= endMinutes;
        return nowMinutes >= startMinutes || nowMinutes <= endMinutes;
    }

    function isControlPermissionAllowedBySchedule(user = global.currentUser || {}, now = new Date()) {
        if (String(user.role || '').toLowerCase() === 'admin' || String(user.account_category || '').toLowerCase() === 'admin') return true;
        const flags = user.account_flags || {};
        const temp = user.temporary_access || {};
        const schedule = user.control_schedule || {};
        if (flags.frozen || flags.temporarily_disabled) return false;
        const disableUntil = parseDateTimeText(flags.disable_until);
        if (disableUntil && now <= disableUntil) return false;
        if (temp.control_blocked) {
            const blockedUntil = parseDateTimeText(temp.control_blocked_until);
            if (!blockedUntil || now <= blockedUntil) return false;
        }
        if (temp.control_enabled) {
            const allowUntil = parseDateTimeText(temp.control_until);
            if (!allowUntil || now <= allowUntil) return true;
        }
        if (!schedule.enabled) return true;
        const mode = String(schedule.mode || 'always');
        const weekday = (now.getDay() + 6) % 7;
        if (mode === 'weekdays' && weekday > 4) return false;
        if (mode === 'weekends' && weekday < 5) return false;
        if (mode === 'custom_days') {
            const weekdays = Array.isArray(schedule.weekdays) ? schedule.weekdays.map(v => Number(v)) : [];
            if (weekdays.length && !weekdays.includes(weekday)) return false;
        }
        return isNowInTimeRange(schedule.start, schedule.end, now);
    }

    function hasPermission(permission, user = global.currentUser || {}) {
        const permissions = Array.isArray(user.permissions) ? user.permissions : [];
        const allowed = permissions.includes(permission);
        const compatibilityMap = {
            'control_center.view': 'light.view',
            'control_center.control': 'light.control',
            'control_center.config': 'meter.config',
        };
        const compat = compatibilityMap[String(permission || '').trim()];
        const compatAllowed = compat ? permissions.includes(compat) : false;
        if (!(allowed || compatAllowed)) return false;
        if (String(permission || '').endsWith('.control') || ['meter.config', 'system.config', 'auth.manage', 'automation.edit', 'control_center.config'].includes(String(permission || ''))) {
            return isControlPermissionAllowedBySchedule(user);
        }
        return true;
    }

    function getPermissionDisabledAttrs(permission, titleText, user = global.currentUser || {}) {
        return hasPermission(permission, user) ? '' : `disabled title="${escapeHtml(titleText || '当前账号无权限执行此操作')}"`;
    }

    function getPermissionDisabledClass(permission, user = global.currentUser || {}) {
        return hasPermission(permission, user) ? '' : ' is-disabled';
    }

    function getDeviceStatusMeta(status = {}, options = {}) {
        const fallbackOfflineText = options.offlineText || '离线';
        const levelRaw = String(status.status_level || '').trim().toLowerCase();
        const stale = !!status.stale;
        const online = !!status.online;
        const hasError = !!(status.last_error || status.error);
        let level = levelRaw;
        if (!['online', 'stale', 'error', 'offline'].includes(level)) {
            if (online && stale) level = 'stale';
            else if (online) level = 'online';
            else if (hasError && (status.last_success_at || status.updated_at)) level = 'error';
            else if (hasError) level = 'error';
            else level = 'offline';
        }
        let chipClass = 'error';
        let text = fallbackOfflineText;
        if (level === 'online') {
            chipClass = 'online';
            text = options.onlineText || '在线';
        } else if (level === 'stale') {
            chipClass = 'warning';
            text = options.staleText || '陈旧';
        } else if (level === 'error') {
            chipClass = 'warning';
            text = options.errorText || '异常';
        }
        const lastSeen = status.last_success_at || status.updated_at || status.last_checked_at;
        const note = status.last_error
            ? `异常: ${String(status.last_error)}`
            : (level === 'stale'
                ? `最近成功 ${formatTimeShort(lastSeen)}`
                : (lastSeen ? `更新于 ${formatTimeShort(lastSeen)}` : '等待采集'));
        return {
            level,
            chipClass,
            text,
            note,
            lastSeen,
            lastCheckedAt: status.last_checked_at || null,
            pollFailures: Number(status.poll_failures || 0),
            isOnlineLike: level === 'online' || level === 'stale',
            isOfflineLike: level === 'offline',
        };
    }

    function getCardStateClass(meta) {
        if (!meta || meta.level === 'offline') return 'offline';
        if (meta.level === 'stale' || meta.level === 'error') return 'warning';
        return '';
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
        isNowInTimeRange,
        isControlPermissionAllowedBySchedule,
        hasPermission,
        getPermissionDisabledAttrs,
        getPermissionDisabledClass,
        getDeviceStatusMeta,
        getCardStateClass,
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
