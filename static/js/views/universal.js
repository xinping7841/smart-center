// AI_MODULE: universal_control_view
// AI_PURPOSE: 协议控制中心前端按钮和历史设备控制 UI。
// AI_BOUNDARY: 不直接发 TCP/UDP/串口；控制走 /api/control_center/execute 或 /api/universal/control。
// AI_DATA_FLOW: CONFIG custom/control devices -> 按钮 DOM -> 控制 API。
// AI_RUNTIME: 首页/协议控制页面加载。
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

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function installProtocolCardDensityStyle() {
        if (document.getElementById('protocol-card-density-runtime')) return;
        const style = document.createElement('style');
        style.id = 'protocol-card-density-runtime';
        style.textContent = `
            #control-center-grid.protocol-device-grid { grid-template-columns:repeat(auto-fill, minmax(220px, 236px)) !important; gap:10px !important; }
            #control-center-grid .protocol-device-card { min-height:202px !important; padding:10px !important; gap:8px !important; }
            #control-center-grid .protocol-device-head { gap:8px !important; }
            #control-center-grid .protocol-device-title { font-size:14px !important; }
            #control-center-grid .protocol-device-meta { font-size:10px !important; line-height:1.28 !important; }
            #control-center-grid .protocol-device-badge { min-width:50px !important; min-height:26px !important; padding:3px 7px !important; font-size:10px !important; }
            #control-center-grid .protocol-status-row { gap:6px !important; }
            #control-center-grid .protocol-status-pill { min-height:44px !important; padding:6px 7px !important; gap:4px !important; }
            #control-center-grid .protocol-status-label { font-size:11px !important; gap:5px !important; }
            #control-center-grid .protocol-status-value { font-size:10px !important; }
            #control-center-grid .protocol-switch-row { padding:8px 9px !important; gap:8px !important; }
            #control-center-grid .protocol-switch-title { font-size:13px !important; }
            #control-center-grid .protocol-switch-sub { font-size:10px !important; }
            #control-center-grid .protocol-toggle { width:50px !important; height:28px !important; }
            #control-center-grid .protocol-toggle span::before { width:21px !important; height:21px !important; left:3px !important; top:3px !important; }
            #control-center-grid .protocol-toggle input:checked + span::before { transform:translateX(21px) !important; }
            #control-center-grid .protocol-device-actions { gap:6px !important; }
            #control-center-grid .protocol-action-btn { min-height:30px !important; padding:5px 7px !important; font-size:11px !important; }
        `;
        document.head.appendChild(style);
    }

    function fireUniversalCommand(devId, payload, format, waitMs) {
        if (!ensureControlPermission('light.control', '控制协议设备')) return;
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
        const title = options.title || '';
        const showInfo = options.showInfo === true;
        notify('协议指令下发中...', false);
        return postJson('/api/control_center/execute', {
            control_id: controlId,
            params: options.params || {},
            value: options.value,
        }, '协议控制下发失败')
            .then(data => {
                if (data.ok) {
                    notify(data.msg || '执行成功', false);
                    if (Array.isArray(data.results)) console.log('协议控制结果:', data.results);
                    if (showInfo) showProtocolInfoDialog(title || data.target_group_name || '设备信息', data);
                    setTimeout(() => updateProtocolDeviceCards(true), 220);
                    return;
                }
                notify('执行失败: ' + (data.msg || '未知错误'), true);
            })
            .catch(() => notify('网络请求错误', true));
    }

    function executeProtocolControl(controlId) {
        const id = String(controlId || '').trim();
        if (!id) return Promise.resolve(null);
        return postJson('/api/control_center/execute', {
            control_id: id,
            params: {},
        }, '协议状态读取失败');
    }

    function firstProtocolResponse(result) {
        if (!result) return '';
        const direct = String(result.response || '').trim();
        if (direct) return direct;
        const row = Array.isArray(result.results) ? result.results.find(item => String(item?.response || '').trim()) : null;
        return row ? String(row.response || '').trim() : '';
    }

    function parseDeviceInfoResponse(response) {
        const info = {};
        const match = String(response || '').match(/\+DEVICEINFO:([^\r\n]+)/i);
        const body = match ? match[1] : '';
        body.split(',').forEach(part => {
            const idx = part.indexOf(':');
            if (idx > 0) info[part.slice(0, idx).trim().toUpperCase()] = part.slice(idx + 1).trim();
        });
        return info;
    }

    function showProtocolInfoDialog(title, result, fallbackRows = []) {
        const response = firstProtocolResponse(result);
        const info = parseDeviceInfoResponse(response);
        const parsedRows = [
            ['型号', info.UT || '未返回'],
            ['固件', info.FV || '未返回'],
            ['网络类型', info.NT || '未返回'],
            ['输出通道', info.DO || '未返回'],
            ['输入通道', info.DI || '未返回'],
        ];
        const rows = response ? parsedRows : fallbackRows;
        const old = document.getElementById('protocol-info-dialog');
        if (old) old.remove();
        const overlay = document.createElement('div');
        overlay.id = 'protocol-info-dialog';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:10080;background:rgba(2,6,23,.72);display:flex;align-items:center;justify-content:center;padding:18px;';
        overlay.innerHTML = `<div style="width:min(520px,100%);border:1px solid rgba(148,163,184,.28);border-radius:12px;background:#0f172a;color:#e5eefb;box-shadow:0 24px 70px rgba(0,0,0,.48);overflow:hidden;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid rgba(148,163,184,.18);">
                <div style="font-size:16px;font-weight:950;">${escapeHtml(title || '设备信息')}</div>
                <button type="button" data-close="1" style="width:32px;height:32px;border:1px solid rgba(148,163,184,.24);border-radius:8px;background:rgba(15,23,42,.78);color:#e5eefb;font-size:20px;line-height:1;cursor:pointer;">×</button>
            </div>
            <div style="padding:14px 16px;">
                <div style="display:grid;grid-template-columns:92px minmax(0,1fr);gap:8px 12px;font-size:13px;">
                    ${rows.map(([k, v]) => `<div style="color:#93a4bd;font-weight:800;">${escapeHtml(k)}</div><div style="font-weight:900;word-break:break-word;">${escapeHtml(v)}</div>`).join('')}
                </div>
                <div style="margin-top:14px;color:#93a4bd;font-size:12px;font-weight:800;">${response ? '原始返回' : '说明'}</div>
                <pre style="margin:8px 0 0;max-height:180px;overflow:auto;white-space:pre-wrap;word-break:break-word;border:1px solid rgba(148,163,184,.18);border-radius:8px;background:rgba(2,6,23,.55);padding:10px;color:#bfdbfe;font-size:12px;line-height:1.45;">${escapeHtml(response || '这台设备没有配置厂家设备信息查询命令，显示的是中控系统当前配置和轮询状态。')}</pre>
            </div>
        </div>`;
        overlay.addEventListener('click', event => {
            if (event.target === overlay || event.target?.dataset?.close) overlay.remove();
        });
        document.body.appendChild(overlay);
    }

    function showProtocolCardInfo(card) {
        if (!card) return;
        const title = card.dataset.infoTitle || card.querySelector('.protocol-device-title')?.textContent?.trim() || '设备信息';
        const rows = [
            ['名称', title],
            ['地址', card.dataset.infoEndpoint || '未配置'],
            ['协议', card.dataset.infoProtocol || '未配置'],
            ['型号', card.dataset.infoModel || '未配置'],
            ['MAC', card.dataset.infoMac || '未配置'],
            ['站号', card.dataset.infoUnit || '未配置'],
            ['输出通道', card.dataset.infoDo || '未配置'],
            ['输入通道', card.dataset.infoDi || '未配置'],
            ['设备状态', card.querySelector('[data-text="health"]')?.textContent?.trim() || '未读取'],
            ['输出状态', card.querySelector('[data-text="do"]')?.textContent?.trim() || '未读取'],
            ['输入状态', card.querySelector('[data-text="di"]')?.textContent?.trim() || '未读取'],
        ];
        showProtocolInfoDialog(`${title} 设备信息`, null, rows);
    }

    function openProtocolDeviceInfo(card, controlId = '') {
        if (!card) return;
        if (controlId) {
            fireControlCenterControl(controlId, {
                showInfo: true,
                title: `${card.dataset.infoTitle || '协议设备'} 设备信息`,
            });
            return;
        }
        showProtocolCardInfo(card);
    }

    function parseProtocolBit(result, kind) {
        if (!result || !result.ok) return null;
        const parts = [];
        if (result.response) parts.push(String(result.response));
        if (result.response_hex) parts.push(String(result.response_hex));
        if (Array.isArray(result.results)) {
            result.results.forEach(item => {
                if (item && item.response) parts.push(String(item.response));
                if (item && item.response_hex) parts.push(String(item.response_hex));
            });
        }
        const payload = parts.join('\n');
        const atName = kind === 'do' ? 'STACH' : 'OCCH';
        const atMatch = payload.match(new RegExp(`\\+${atName}\\d*\\s*:\\s*([01])`, 'i'));
        if (atMatch) return atMatch[1] === '1';
        const hex = (payload.match(/[0-9A-Fa-f]{2}/g) || []).map(x => parseInt(x, 16));
        const fn = kind === 'do' ? 0x01 : 0x02;
        for (let i = 0; i + 3 < hex.length; i += 1) {
            if (hex[i + 1] === fn && hex[i + 2] >= 1) return (hex[i + 3] & 0x01) === 1;
        }
        return null;
    }

    function setProtocolLamp(card, key, state, text) {
        const led = card.querySelector(`[data-led="${key}"]`);
        const label = card.querySelector(`[data-text="${key}"]`);
        if (led) {
            led.classList.remove('on', 'off', 'warn');
            if (state === true) led.classList.add('on');
            else if (state === false) led.classList.add('off');
            else led.classList.add('warn');
        }
        if (label) label.textContent = text || (state === true ? '正常' : (state === false ? '断开' : '异常'));
    }

    function applyProtocolOutput(card, value) {
        const toggle = card.querySelector('[data-role="do-toggle"]');
        const switchText = card.querySelector('[data-text="switch"]');
        if (toggle) {
            toggle.checked = value === true;
            toggle.disabled = value === null;
        }
        if (switchText) switchText.textContent = value === true ? '当前输出：开' : (value === false ? '当前输出：关' : '状态读取失败');
    }

    function updateProtocolDeviceCard(card) {
        if (!card || card.dataset.polling === '1' || card.dataset.pulsing === '1') return Promise.resolve();
        card.dataset.polling = '1';
        const readDo = card.dataset.readDo || '';
        const readDi = card.dataset.readDi || '';
        return Promise.all([executeProtocolControl(readDo), executeProtocolControl(readDi)])
            .then(([doResult, diResult]) => {
                const doValue = doResult ? parseProtocolBit(doResult, 'do') : null;
                const diValue = diResult ? parseProtocolBit(diResult, 'di') : null;
                const healthy = Boolean((doResult && doResult.ok && doValue !== null) || (diResult && diResult.ok && diValue !== null));
                setProtocolLamp(card, 'health', healthy, healthy ? '正常' : '异常');
                setProtocolLamp(card, 'di', diValue, diValue === true ? '有输入' : (diValue === false ? '无输入' : '读取失败'));
                setProtocolLamp(card, 'do', doValue, doValue === true ? '输出开' : (doValue === false ? '输出关' : '读取失败'));
                applyProtocolOutput(card, doValue);
            })
            .catch(() => {
                setProtocolLamp(card, 'health', false, '异常');
                setProtocolLamp(card, 'di', null, '读取失败');
                setProtocolLamp(card, 'do', null, '读取失败');
                applyProtocolOutput(card, null);
            })
            .finally(() => { card.dataset.polling = '0'; });
    }

    function updateProtocolDeviceCards(force = false) {
        if (!force && typeof global.getActiveViewId === 'function' && global.getActiveViewId() !== 'universal') return;
        document.querySelectorAll('[data-protocol-card="1"]').forEach(card => updateProtocolDeviceCard(card));
    }

    function pulseProtocolDevice(card) {
        if (!card) return;
        if (!ensureControlPermission('control_center.control', '点动协议设备输出')) return;
        if (card.dataset.pulsing === '1') return;
        const pulseId = card.dataset.pulse || '';
        const onId = card.dataset.doOn || '';
        const offId = card.dataset.doOff || '';
        const pulseButton = card.querySelector('.protocol-action-btn.pulse');
        const toggle = card.querySelector('[data-role="do-toggle"]');
        const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
        const assertOk = (result, message) => {
            if (result && result.ok === 0) throw new Error(result.msg || message);
            return result;
        };
        const run = onId && offId
            ? executeProtocolControl(onId)
                .then(result => assertOk(result, '点动开启失败'))
                .then(() => delay(1000))
                .then(() => executeProtocolControl(offId))
                .then(result => assertOk(result, '点动关断失败'))
            : executeProtocolControl(pulseId).then(result => assertOk(result, '点动失败'));
        card.dataset.pulsing = '1';
        if (pulseButton) {
            pulseButton.disabled = true;
            pulseButton.textContent = '点动中...';
        }
        if (toggle) toggle.disabled = true;
        setProtocolLamp(card, 'do', null, '点动中');
        const switchText = card.querySelector('[data-text="switch"]');
        if (switchText) switchText.textContent = '点动中，1秒后自动关闭';
        notify('点动执行中...', false);
        run.then(result => {
            notify('点动完成', false);
            setProtocolLamp(card, 'do', false, '输出关');
            applyProtocolOutput(card, false);
            setTimeout(() => updateProtocolDeviceCard(card), 180);
            setTimeout(() => updateProtocolDeviceCard(card), 900);
        }).catch(err => {
            notify(err.message || '点动失败', true);
            setTimeout(() => updateProtocolDeviceCard(card), 180);
        }).finally(() => {
            card.dataset.pulsing = '0';
            if (pulseButton) {
                pulseButton.disabled = false;
                pulseButton.textContent = '点动1秒';
            }
            if (toggle) toggle.disabled = false;
        });
    }

    function toggleProtocolDeviceOutput(input) {
        const card = input.closest('[data-protocol-card="1"]');
        if (!card) return;
        if (!ensureControlPermission('control_center.control', '控制协议设备输出')) {
            input.checked = !input.checked;
            return;
        }
        const controlId = input.checked ? card.dataset.doOn : card.dataset.doOff;
        if (!controlId) {
            notify('这个设备缺少输出控制指令', true);
            input.checked = !input.checked;
            return;
        }
        input.disabled = true;
        postJson('/api/control_center/execute', { control_id: controlId, params: {} }, '协议输出控制失败')
            .then(data => {
                if (!data.ok) throw new Error(data.msg || '输出控制失败');
                notify(data.msg || '输出已切换', false);
                setTimeout(() => updateProtocolDeviceCard(card), 260);
            })
            .catch(err => {
                notify(err.message || '输出控制失败', true);
                input.checked = !input.checked;
            })
            .finally(() => { setTimeout(() => { input.disabled = false; }, 360); });
    }



    function nodeRedStatusClass(device) {
        const status = String(device?.display_status || device?.status || 'unknown').toLowerCase();
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id] || remaining > 0) return 'is-busy';
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
        const isPending = !!nodeRedPending[id];
        const controlDisabled = disabled || isPending || remaining > 0 ? 'disabled' : '';
        const title = isPending
            ? '\u6307\u4ee4\u6267\u884c\u4e2d'
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
                if (data.error === 'cooldown' || Number(data.retry_after_sec || 0) > 0) {
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
        updateProtocolDeviceCards,
        toggleProtocolDeviceOutput,
        pulseProtocolDevice,
        openProtocolDeviceInfo,
        updateNodeRedDevices,
        controlNodeRedDevice,
    };

    SmartCenter.universal = Object.assign({}, SmartCenter.universal || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        installProtocolCardDensityStyle();
        const protocolPollRegister = typeof global.registerPollingTask === 'function' ? global.registerPollingTask : (typeof SmartCenter.registerPollingTask === 'function' ? SmartCenter.registerPollingTask.bind(SmartCenter) : null);
        if (protocolPollRegister) {
            protocolPollRegister('protocol_control', 2500, () => updateProtocolDeviceCards(), () => typeof global.getActiveViewId !== 'function' || global.getActiveViewId() === 'universal');
        }
        setTimeout(() => updateProtocolDeviceCards(true), 120);
        setTimeout(() => updateProtocolDeviceCards(true), 1100);

        SmartCenter.registerModule('universal', {
            kind: 'view',
            view: 'universal',
            exports: Object.keys(api),
            source: 'static/js/views/universal.js',
        });
    }

    Object.assign(global, api);
})(window);
