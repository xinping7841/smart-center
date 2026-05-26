// AI_MODULE: universal_control_view
// AI_PURPOSE: 泛型控制/协议控制中心前端按钮和旧设备控制 UI。
// AI_BOUNDARY: 不直接发 TCP/UDP/串口；控制走 /api/control_center/execute 或 /api/universal/control。
// AI_DATA_FLOW: CONFIG custom/control devices -> 按钮 DOM -> 控制 API。
// AI_RUNTIME: 首页/泛型控制页面加载。
// AI_RISK: 高，按钮可能向真实设备发送控制命令。
// AI_SEARCH_KEYWORDS: universal, protocol control, tcp, udp, serial.

(function installSmartCenterUniversal(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const nodeRedPending = {};
    const nodeRedCooldownUntil = {};

    function nowMs() {
        return Date.now();
    }

    function notify(message, isError = false) {
        if (typeof global.showToast === 'function') {
            global.showToast(message, isError);
        }
    }

    function ensureControlPermission(permission, actionText) {
        if (typeof global.ensurePermission === 'function') {
            return global.ensurePermission(permission, actionText);
        }
        return true;
    }

    function postJson(url, payload, fallbackText) {
        if (typeof global.postJsonLoose === 'function') {
            return global.postJsonLoose(url, payload, fallbackText);
        }
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(response => response.json());
    }

    function postJsonAllowHttpError(url, payload) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(response => response.json().catch(() => ({})));
    }

    function fireUniversalCommand(devId, payload, format, waitMs) {
        if (!ensureControlPermission('light.control', '控制泛型设备')) return;
        notify('通用指令下发中...', false);
        postJson('/api/universal/control', {
            device_id: devId,
            command: { payload, format, wait_ms: waitMs || 0 },
        }, '通用指令下发失败')
            .then(data => {
                if (data.success) {
                    notify('执行成功');
                    console.log('设备返回:', data.response);
                    return;
                }
                notify('执行失败: ' + (data.response || data.msg || data.message || '未知错误'), true);
            })
            .catch(() => notify('网络请求错误', true));
    }

    function handleLongPressStart(devId, startPayload, format) {
        fireUniversalCommand(devId, startPayload, format, 0);
    }

    function handleLongPressEnd(devId, stopPayload, format) {
        fireUniversalCommand(devId, stopPayload, format, 0);
    }

    function fireControlCenterControl(controlId, options = {}) {
        if (!ensureControlPermission('control_center.control', '控制协议设备')) return;
        notify('协议指令下发中...', false);
        postJson('/api/control_center/execute', {
            control_id: controlId,
            params: options.params || {},
            value: options.value,
        }, '协议控制下发失败')
            .then(data => {
                if (data.ok) {
                    notify(data.msg || '执行成功', false);
                    if (Array.isArray(data.results)) console.log('协议控制结果:', data.results);
                    return;
                }
                notify('执行失败: ' + (data.msg || '未知错误'), true);
            })
            .catch(() => notify('网络请求错误', true));
    }



    function nodeRedStatusClass(device) {
        const status = String(device?.display_status || device?.status || 'unknown').toLowerCase();
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id] || remaining > 0 || isNodeRedControlPending(device)) return 'is-busy';
        if (status === 'on') return 'is-on';
        if (status === 'off') return 'is-off';
        if (['starting', 'stopping', 'pending_ack', 'partial'].includes(status)) return 'is-busy';
        if (status === 'offline') return 'is-offline';
        return 'is-error';
    }

    function nodeRedActionLabel(device) {
        const status = String(device?.status || '').toLowerCase();
        if (status === 'on' || status === 'starting' || status === 'pending_ack') return '\u5173\u706f';
        return '\u5f00\u706f';
    }

    function nodeRedActionForToggle(device) {
        const status = String(device?.status || '').toLowerCase();
        return status === 'on' || status === 'starting' || status === 'pending_ack' ? 'off' : 'on';
    }

    function nodeRedHealthText(device) {
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id]) return '\u6267\u884c\u4e2d / \u8bf7\u7a0d\u5019';
        if (isNodeRedControlPending(device)) return '\u56de\u8bfb\u4e2d / \u8bf7\u7a0d\u5019';
        if (remaining > 0) return `\u4fdd\u62a4\u51b7\u5374 / ${remaining}\u79d2`;
        const health = device?.health && typeof device.health === 'object' ? device.health : {};
        const message = health.message || health.status || '';
        const onlineText = device?.online === false ? '\u79bb\u7ebf' : '\u5728\u7ebf';
        const state = device?.state && typeof device.state === 'object' ? device.state : {};
        const detail = state.detail || state.power || state.reason || message || onlineText;
        return `${onlineText} / ${detail}`;
    }

    function nodeRedLightStateText(device) {
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id]) return '\u6267\u884c\u4e2d';
        if (isNodeRedControlPending(device)) return '\u56de\u8bfb\u4e2d';
        if (remaining > 0) return `\u4fdd\u62a4 ${remaining}s`;
        const status = String(device?.status || '').toLowerCase();
        if (status === 'on') return '\u4eae';
        if (status === 'off') return '\u6697';
        return device?.display_text || '\u672a\u77e5';
    }

    function syncNodeRedCooldown(device) {
        const id = String(device?.device_id || '');
        if (!id) return;
        const remaining = Number(device?.cooldown_remaining_sec || 0);
        if (remaining > 0) {
            nodeRedCooldownUntil[id] = Math.max(nodeRedCooldownUntil[id] || 0, nowMs() + remaining * 1000);
        }
    }

    function isNodeRedControlPending(device) {
        return !!device?.control_pending || Number(device?.control_pending_remaining_sec || 0) > 0;
    }

    function getNodeRedCooldownRemainingSec(deviceId, device = null) {
        const id = String(deviceId || device?.device_id || '');
        if (!id) return 0;
        syncNodeRedCooldown(device);
        const remainingMs = Math.max(Number(nodeRedCooldownUntil[id] || 0) - nowMs(), 0);
        return remainingMs > 0 ? Math.ceil(remainingMs / 1000) : 0;
    }

    function renderNodeRedDeviceCard(device) {
        const id = String(device?.device_id || '');
        const lightName = id === 'courtyard_light' ? '\u6237\u5916\u706f' : (device?.device_name || id || '\u672a\u547d\u540d\u706f\u5177');
        const name = escapeHtml(lightName);
        const displayText = escapeHtml(nodeRedLightStateText(device));
        const statusClass = nodeRedStatusClass(device);
        const healthText = escapeHtml(nodeRedHealthText(device));
        const updated = escapeHtml(formatTimeShort(device?.updated_at || ''));
        const disabled = id ? '' : 'disabled';
        const safeId = escapeHtml(id);
        const action = nodeRedActionForToggle(device);
        const checked = String(device?.status || '').toLowerCase() === 'on' ? 'checked' : '';
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        const isPending = !!nodeRedPending[id] || isNodeRedControlPending(device);
        const controlDisabled = disabled || isPending || remaining > 0 ? 'disabled' : '';
        const title = isPending
            ? '\u6307\u4ee4\u6267\u884c\u6216\u72b6\u6001\u56de\u8bfb\u4e2d'
            : (remaining > 0 ? `\u5f00\u5173\u4fdd\u62a4\u51b7\u5374\u4e2d\uff0c${remaining}\u79d2\u540e\u53ef\u64cd\u4f5c` : nodeRedActionLabel(device));
        return `<div class="protocol-light-switch-card ${statusClass}" data-node-red-device="${safeId}">
            <div class="protocol-light-switch-head">
                <div style="min-width:0;">
                    <div class="protocol-light-switch-title">${name}</div>
                    <div class="protocol-light-switch-subtitle">\u7f51\u5173\u72b6\u6001\u786e\u8ba4</div>
                </div>
                <span class="protocol-light-switch-state">${displayText}</span>
            </div>
            <div class="protocol-light-switch-row">
                <div class="protocol-light-switch-meta">${healthText}<br>${updated}</div>
                <label class="protocol-light-toggle" title="${escapeHtml(title)}">
                    <input type="checkbox" ${checked} ${controlDisabled} onchange="controlNodeRedDevice('${safeId}', '${action}', this)">
                    <span></span>
                </label>
            </div>
        </div>`;
    }

    function updateNodeRedDevices(force = false) {
        const grid = document.getElementById('node-red-device-grid');
        if (!grid) return Promise.resolve({});
        if (!force && typeof global.getActiveViewId === 'function' && global.getActiveViewId() !== 'universal') {
            return Promise.resolve({});
        }
        return fetchJsonLoose('/api/node-red/devices', {}, 'Node-RED \u8bbe\u5907\u72b6\u6001\u8bfb\u53d6\u5931\u8d25')
            .then(data => {
                const devices = Array.isArray(data.devices) ? data.devices : [];
                devices.forEach(syncNodeRedCooldown);
                grid.innerHTML = devices.length
                    ? devices.map(renderNodeRedDeviceCard).join('')
                    : '<div class="node-red-empty">\u672a\u914d\u7f6e Node-RED \u7edf\u4e00\u8bbe\u5907\u3002</div>';
                return data;
            })
            .catch(error => {
                grid.innerHTML = `<div class="node-red-empty">${escapeHtml(error.message || 'Node-RED \u8bbe\u5907\u72b6\u6001\u8bfb\u53d6\u5931\u8d25')}</div>`;
                return {};
            });
    }

    function controlNodeRedDevice(deviceId, action, inputEl = null) {
        if (!ensureControlPermission('control_center.control', '\u63a7\u5236 Node-RED \u8bbe\u5907')) return;
        const id = String(deviceId || '').trim();
        if (!id) return;
        const remaining = getNodeRedCooldownRemainingSec(id);
        if (remaining > 0) {
            if (inputEl) inputEl.checked = !inputEl.checked;
            notify(`\u5f00\u5173\u4fdd\u62a4\u51b7\u5374\u4e2d\uff0c${remaining}\u79d2\u540e\u518d\u8bd5`, true);
            updateNodeRedDevices(true);
            return Promise.resolve({});
        }
        nodeRedPending[id] = true;
        if (inputEl) inputEl.disabled = true;
        notify('Node-RED \u6307\u4ee4\u4e0b\u53d1\u4e2d...', false);
        return postJsonAllowHttpError('/api/node-red/device/' + encodeURIComponent(id) + '/control', { action })
            .then(data => {
                if (data.success || data.ok) {
                    const device = data.device || {};
                    syncNodeRedCooldown(device);
                    const cooldownSec = Number(device.control_cooldown_sec || 0);
                    if (cooldownSec > 0) nodeRedCooldownUntil[id] = Math.max(nodeRedCooldownUntil[id] || 0, nowMs() + cooldownSec * 1000);
                    notify(data.msg || '\u6267\u884c\u6210\u529f', false);
                    return updateNodeRedDevices(true);
                }
                if (data.error === 'cooldown') {
                    const retrySec = Math.max(1, Number(data.retry_after_sec || 1));
                    nodeRedCooldownUntil[id] = nowMs() + retrySec * 1000;
                }
                notify('\u6267\u884c\u5931\u8d25: ' + (data.msg || data.message || '\u672a\u77e5\u9519\u8bef'), true);
                return updateNodeRedDevices(true);
            })
            .catch(error => {
                notify(error.message || '\u7f51\u7edc\u8bf7\u6c42\u9519\u8bef', true);
                return updateNodeRedDevices(true);
            })
            .finally(() => {
                delete nodeRedPending[id];
                if (inputEl) inputEl.disabled = false;
                setTimeout(() => updateNodeRedDevices(true), 80);
            });
    }

    const api = {
        fireUniversalCommand,
        handleLongPressStart,
        handleLongPressEnd,
        fireControlCenterControl,
        updateNodeRedDevices,
        controlNodeRedDevice,
    };

    SmartCenter.universal = Object.assign({}, SmartCenter.universal || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('universal', {
            kind: 'view',
            view: 'universal',
            exports: Object.keys(api),
            source: 'static/js/views/universal.js',
        });
    }

    Object.assign(global, api);
})(window);
