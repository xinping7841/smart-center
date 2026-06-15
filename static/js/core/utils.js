// AI_MODULE: frontend_utils
// AI_PURPOSE: 前端通用工具，包含 HTML 转义、API 错误翻译、fetch JSON、toast 和格式化函数。
// AI_BOUNDARY: 不写具体模块 DOM 渲染；业务页面应调用这里的工具减少重复。
// AI_DATA_FLOW: view 脚本 -> SmartCenter.utils -> API 请求/格式化/提示。
// AI_RUNTIME: 全站页面加载后常驻，许多 view 模块依赖。
// AI_RISK: 中，错误翻译和 fetch 行为会影响所有页面的操作反馈。
// AI_SEARCH_KEYWORDS: utils, fetchJson, toast, escapeHtml, format.

(function installSmartCenterUtils(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const inFlight = new Map();
    const scriptLoads = new Map();
    const stylesheetLoads = new Map();
    let toastTimer = null;

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

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
        return match ? match[1] : '';
    }

    async function fetchJson(url, options = {}, fallbackText = '请求失败', parseOptions = {}) {
        const dedupeKey = getFetchJsonDedupeKey(url, options);
        if (dedupeKey && inFlight.has(dedupeKey)) {
            return inFlight.get(dedupeKey);
        }
        // CSRF protection: attach token for unsafe methods
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            const csrfToken = getCsrfToken();
            if (csrfToken) {
                options.headers = Object.assign({}, options.headers || {}, { 'X-CSRF-Token': csrfToken });
            }
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

    function loadScriptOnce(src, options = {}) {
        const url = String(src || '').trim();
        if (!url) return Promise.reject(new Error('script_url_empty'));
        const existingGlobal = options.globalName ? global[options.globalName] : null;
        if (existingGlobal) return Promise.resolve(existingGlobal);
        if (scriptLoads.has(url)) return scriptLoads.get(url);
        const resolveScriptResult = () => (options.globalName ? global[options.globalName] : true);
        const promise = new Promise((resolve, reject) => {
            const existingTag = Array.from(document.scripts || []).find(item => item.dataset.smartLazySrc === url || item.getAttribute('src') === url);
            if (existingTag) {
                if (existingTag.dataset.smartLazyLoaded === '1') {
                    resolve(resolveScriptResult());
                    return;
                }
                if (existingTag.dataset.smartLazyError === '1') {
                    reject(new Error(`script_load_failed:${url}`));
                    return;
                }
                existingTag.addEventListener('load', () => {
                    existingTag.dataset.smartLazyLoaded = '1';
                    resolve(resolveScriptResult());
                }, { once: true });
                existingTag.addEventListener('error', () => {
                    existingTag.dataset.smartLazyError = '1';
                    reject(new Error(`script_load_failed:${url}`));
                }, { once: true });
                // If a script tag was already loaded before this listener was attached,
                // no second load event will fire. Resolve on the next tick when the module
                // has registered or the browser reports the script as complete.
                window.setTimeout(() => {
                    if (options.globalName && !global[options.globalName]) return;
                    if (existingTag.dataset.smartLazyError === '1') return;
                    if (existingTag.dataset.smartLazyLoaded === '1' || existingTag.readyState === 'complete' || !options.globalName) {
                        existingTag.dataset.smartLazyLoaded = '1';
                        resolve(resolveScriptResult());
                    }
                }, 0);
                return;
            }
            const script = document.createElement('script');
            script.src = url;
            script.async = true;
            script.defer = true;
            script.dataset.smartLazySrc = url;
            script.onload = () => {
                script.dataset.smartLazyLoaded = '1';
                resolve(resolveScriptResult());
            };
            script.onerror = () => {
                script.dataset.smartLazyError = '1';
                reject(new Error(`script_load_failed:${url}`));
            };
            document.head.appendChild(script);
        }).catch(err => {
            scriptLoads.delete(url);
            throw err;
        });
        scriptLoads.set(url, promise);
        return promise;
    }

    function loadStylesheetOnce(href) {
        const url = String(href || '').trim();
        if (!url) return Promise.reject(new Error('stylesheet_url_empty'));
        if (Array.from(document.styleSheets || []).some(sheet => String(sheet.href || '').endsWith(url) || String(sheet.href || '') === url)) {
            return Promise.resolve(true);
        }
        if (stylesheetLoads.has(url)) return stylesheetLoads.get(url);
        const promise = new Promise((resolve, reject) => {
            const existingTag = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(item => item.dataset.smartLazyHref === url || item.getAttribute('href') === url);
            if (existingTag) {
                if (existingTag.dataset.smartLazyLoaded === '1') {
                    resolve(true);
                    return;
                }
                if (existingTag.dataset.smartLazyError === '1') {
                    reject(new Error(`stylesheet_load_failed:${url}`));
                    return;
                }
                existingTag.addEventListener('load', () => {
                    existingTag.dataset.smartLazyLoaded = '1';
                    resolve(true);
                }, { once: true });
                existingTag.addEventListener('error', () => {
                    existingTag.dataset.smartLazyError = '1';
                    reject(new Error(`stylesheet_load_failed:${url}`));
                }, { once: true });
                window.setTimeout(() => {
                    if (existingTag.dataset.smartLazyError === '1') return;
                    if (existingTag.sheet || existingTag.dataset.smartLazyLoaded === '1') {
                        existingTag.dataset.smartLazyLoaded = '1';
                        resolve(true);
                    }
                }, 0);
                return;
            }
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = url;
            link.dataset.smartLazyHref = url;
            link.onload = () => {
                link.dataset.smartLazyLoaded = '1';
                resolve(true);
            };
            link.onerror = () => {
                link.dataset.smartLazyError = '1';
                reject(new Error(`stylesheet_load_failed:${url}`));
            };
            document.head.appendChild(link);
        }).catch(err => {
            stylesheetLoads.delete(url);
            throw err;
        });
        stylesheetLoads.set(url, promise);
        return promise;
    }

    function ensureEChartsLoaded() {
        if (global.echarts) return Promise.resolve(global.echarts);
        return loadScriptOnce('/static/vendor/echarts.min.js?v=6.0.0', { globalName: 'echarts' });
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

    function showToast(message, isError = false, options = {}) {
        const text = String(message ?? '');
        const doc = global.document;
        const el = options.element || (doc ? doc.getElementById(options.toastId || 'toast') : null);
        if (!el) {
            if (options.fallback === 'alert' && typeof global.alert === 'function') {
                global.alert(text);
            }
            return;
        }
        if ('innerText' in el) el.innerText = text;
        else el.textContent = text;
        const baseClass = options.baseClass || 'toast-msg';
        const showClass = options.showClass || 'show';
        const errorClass = options.errorClass || 'toast-error';
        el.className = `${baseClass} ${showClass}${isError ? ` ${errorClass}` : ''}`;
        const timeoutMs = Number.isFinite(Number(options.timeoutMs)) ? Number(options.timeoutMs) : 2500;
        if (toastTimer) global.clearTimeout(toastTimer);
        toastTimer = global.setTimeout(() => {
            el.className = baseClass;
            toastTimer = null;
        }, timeoutMs);
    }

    function reportFrontendError(scope, err, options = {}) {
        const errorText = err && err.stack ? err.stack : String(err || 'unknown_error');
        if (global.console && typeof global.console.error === 'function') {
            global.console.error(`[frontend:${scope}]`, err);
        }
        const endpoint = options.endpoint || '/api/logs/frontend';
        try {
            if (typeof global.fetch === 'function') {
                global.fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope,
                        message: errorText,
                        url: global.location ? global.location.href : '',
                        ts: new Date().toISOString(),
                    }),
                }).catch(() => {});
            }
        } catch (_) {}
        return errorText;
    }

    function guardFrontendStep(scope, fn, fallbackMessage = '', options = {}) {
        const handleError = err => {
            reportFrontendError(scope, err, options.reportOptions || {});
            if (fallbackMessage) {
                showToast(fallbackMessage, true, options.toastOptions || {});
            }
            return null;
        };
        try {
            const result = fn();
            if (result && typeof result.then === 'function') {
                return result.catch(handleError);
            }
            return result;
        } catch (err) {
            return handleError(err);
        }
    }

    function formatNetworkMbps(kbPerSec) {
        const mbps = (Number(kbPerSec) || 0) * 8 / 1024;
        if (mbps >= 100) return mbps.toFixed(0);
        if (mbps >= 10) return mbps.toFixed(1);
        return mbps.toFixed(2).replace(/\.?0+$/, '');
    }

    function formatBytesGiB(bytes) {
        const num = Number(bytes);
        if (!Number.isFinite(num) || num <= 0) return '--';
        const gib = num / (1024 ** 3);
        if (gib >= 1024) return `${(gib / 1024).toFixed(gib >= 10240 ? 0 : 1)} TB`;
        return `${gib.toFixed(gib >= 100 ? 0 : 1)} GB`;
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

    function ensurePermission(permission, actionText = '执行当前操作', options = {}) {
        const user = options.user || global.currentUser || {};
        if (hasPermission(permission, user)) return true;
        const message = options.message || `当前账号无权限${actionText}`;
        if (typeof options.notifier === 'function') {
            options.notifier(message, true);
        } else if (options.mode === 'alert' && typeof global.alert === 'function') {
            global.alert(message);
        } else {
            showToast(message, true, options.toastOptions || {});
        }
        return false;
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

    function formatAutomationValue(value) {
        if (value === null || value === undefined || value === '') return '--';
        if (typeof value === 'number' && Number.isFinite(value)) {
            return Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) >= 100 ? 1 : 2).replace(/\.?0+$/, '');
        }
        return String(value);
    }

    function formatAutomationRuleTime(value) {
        if (!value) return '--';
        const text = formatDateTimeText(value);
        return text === '未上报' ? '--' : text;
    }

    function getAutomationTodayKey(now = new Date()) {
        const pad = value => String(value).padStart(2, '0');
        return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    }

    function getAutomationDayLabel(schedule = {}) {
        const dayType = String(schedule.day_type || 'everyday');
        if (dayType === 'workday') return '工作日';
        if (dayType === 'weekend') return '周末';
        if (dayType === 'custom') return '自定义日期';
        return '每天';
    }

    function getAutomationSourceLabel(sourceType) {
        const map = { env: '环境', screen: '幕布', power: '强电', sequencer: '时序电源', light: '灯光', meter: '电表', server: '服务器', hvac: '空调' };
        return map[String(sourceType || 'env')] || String(sourceType || '数据源');
    }

    function getAutomationPropLabel(prop) {
        const map = { lux: '光照', illuminance: '光照', temp: '温度', temperature: '温度', hum: '湿度', humidity: '湿度', online: '在线', current: '电流', power: '电源', mode: '模式', hvac_action: '运行状态', all_on: '全部开启', all_off: '全部关闭', on_count: '开启路数', off_count: '关闭路数', channel_state: '通道状态', running: '运行中', locked: '锁定' };
        return map[String(prop || '').toLowerCase()] || String(prop || '属性');
    }

    function getAutomationPropUnit(prop) {
        const key = String(prop || '').toLowerCase();
        if (['lux', 'illuminance'].includes(key)) return ' lux';
        if (['temp', 'temperature'].includes(key)) return '°C';
        if (['hum', 'humidity'].includes(key)) return '%';
        if (key === 'current') return ' A';
        if (key === 'power') return ' W';
        if (['on_count', 'off_count'].includes(key)) return ' 路';
        return '';
    }

    function formatAutomationValueWithUnit(value, prop) {
        if (typeof value === 'boolean') {
            const key = String(prop || '').toLowerCase();
            if (key === 'online') return value ? '在线' : '离线';
            if (key === 'all_on') return value ? '已全开' : '未全开';
            if (key === 'all_off') return value ? '已全关' : '未全关';
            if (key === 'locked') return value ? '已锁定' : '未锁定';
            if (key === 'running') return value ? '运行中' : '待机';
            return value ? '开' : '关';
        }
        const text = formatAutomationValue(value);
        if (text === '--') return text;
        return `${text}${getAutomationPropUnit(prop)}`;
    }

    const api = {
        escapeHtml,
        translateApiError,
        parseJsonResponse,
        getFetchJsonDedupeKey,
        fetchJson,
        fetchJsonLoose,
        postJsonLoose,
        loadScriptOnce,
        loadStylesheetOnce,
        ensureEChartsLoaded,
        parseDateTimeText,
        formatRelativeSeconds,
        formatDateTimeText,
        formatTimeShort,
        toFiniteNumber,
        getTodayTargetDateTime,
        formatCountdownText,
        formatFixedNumber,
        showToast,
        reportFrontendError,
        guardFrontendStep,
        formatNetworkMbps,
        formatBytesGiB,
        isNowInTimeRange,
        isControlPermissionAllowedBySchedule,
        hasPermission,
        ensurePermission,
        getPermissionDisabledAttrs,
        getPermissionDisabledClass,
        getDeviceStatusMeta,
        getCardStateClass,
        formatAutomationValue,
        formatAutomationRuleTime,
        getAutomationTodayKey,
        getAutomationDayLabel,
        getAutomationSourceLabel,
        getAutomationPropLabel,
        getAutomationPropUnit,
        formatAutomationValueWithUnit,
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
