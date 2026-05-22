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

    const api = {
        fireUniversalCommand,
        handleLongPressStart,
        handleLongPressEnd,
        fireControlCenterControl,
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
