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
    const configData = global.configData || {};
    const utils = SmartCenter.utils || {};
    const nodeRedPending = {};
    const nodeRedCooldownUntil = {};
    const nodeRedDesiredStates = {};
    const protocolDesiredStates = {};
    const CONTROL_TARGET_UI_MS = 6000;
    const CONTROL_VERIFY_HOLD_MS = 30000;
    const protocolReadCache = {};
    let universalRendered = false;

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
        if (typeof utils.escapeHtml === 'function') return utils.escapeHtml(value);
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function jsArg(value) {
        return escapeHtml(JSON.stringify(String(value ?? '')));
    }

    function getControlCenterConfig() {
        const cc = configData.control_center;
        return cc && typeof cc === 'object' ? cc : {};
    }

    function getControlCenterDevices() {
        const devices = getControlCenterConfig().devices;
        return Array.isArray(devices) ? devices : [];
    }

    function getControlCenterTargets() {
        const targets = getControlCenterConfig().target_groups;
        return Array.isArray(targets) ? targets : [];
    }

    function getControlCenterPanels() {
        const panels = getControlCenterConfig().panels;
        return Array.isArray(panels) ? panels : [];
    }

    function normalizeProtocolDisplayName(name) {
        return String(name || '协议设备').replace('泥人继电器 ', '泥人 ');
    }

    function getTargetDeviceConfig(targetId) {
        return getControlCenterDevices().find(item => String(item?.target_group_id || '') === String(targetId || '')) || null;
    }

    function getProtocolDisplayName(target = {}, deviceCfg = null) {
        const targetName = String(target?.name || '').trim();
        const deviceName = String(deviceCfg?.display_name || deviceCfg?.alias || deviceCfg?.name || '').trim();
        return normalizeProtocolDisplayName(targetName || deviceName || '协议设备');
    }

    function protocolModeLabel(value) {
        const text = String(value || '').trim().toLowerCase();
        if (text.includes('at')) return 'AT';
        if (text.includes('modbus_tcp')) return 'Modbus TCP';
        if (text.includes('rtu')) return 'RTU透传';
        return text || '';
    }

    function getProtocolReadCache(card, kind) {
        const targetId = String(card?.dataset?.targetId || card?.dataset?.infoEndpoint || 'unknown');
        if (!protocolReadCache[targetId]) protocolReadCache[targetId] = { do: {}, di: {} };
        if (!protocolReadCache[targetId][kind]) protocolReadCache[targetId][kind] = {};
        return protocolReadCache[targetId][kind];
    }

    function getVisibleHomeControlsForTarget(targetId) {
        const rows = [];
        getControlCenterPanels()
            .filter(panel => panel && panel.visible !== false)
            .forEach(panel => {
                const controls = Array.isArray(panel.controls) ? panel.controls : [];
                controls
                    .filter(ctrl => ctrl && ctrl.visible !== false && ctrl.show_on_home && String(ctrl.target_group_id || '') === String(targetId || ''))
                    .sort((a, b) => Number(a?.sort || 0) - Number(b?.sort || 0))
                    .forEach(ctrl => rows.push(ctrl));
            });
        return rows;
    }

    function classifyProtocolControls(controls) {
        const result = { read_do: '', read_di: '', do_on: '', do_off: '', info: '', pulse: '', items: [] };
        controls.forEach(ctrl => {
            const actionName = String(ctrl?.name || '执行');
            if (actionName === '读DO' || actionName.includes('读DO')) result.read_do = ctrl.id || '';
            else if (actionName === '读DI' || actionName.includes('读DI')) result.read_di = ctrl.id || '';
            else if (actionName === 'DO开' || actionName.includes('DO开')) result.do_on = ctrl.id || '';
            else if (actionName === 'DO关' || actionName.includes('DO关')) result.do_off = ctrl.id || '';
            else if (actionName.includes('点动')) {
                if (ctrl.command_id) result.pulse = ctrl.id || '';
            } else if (actionName === '信息' || actionName.includes('信息')) result.info = ctrl.id || '';
            else result.items.push(ctrl);
        });
        return result;
    }

    function renderProtocolDeviceCard(target, targetControls) {
        const deviceCfg = getTargetDeviceConfig(target.id);
        const displayName = getProtocolDisplayName(target, deviceCfg);
        const endpoint = `${target.host || ''}${target.port ? `:${target.port}` : ''}`;
        const protocol = target.data_protocol || deviceCfg?.protocol || target.protocol || '';
        const protocolLabel = protocolModeLabel(protocol);
        const actions = [];
        actions.push(`<button class="protocol-action-btn read" onclick="openProtocolDeviceInfo(this.closest('[data-protocol-card=&quot;1&quot;]'), ${jsArg(targetControls.info)})">信息</button>`);
        if (targetControls.pulse || (targetControls.do_on && targetControls.do_off)) {
            actions.push(`<button class="protocol-action-btn pulse" onclick="pulseProtocolDevice(this.closest('[data-protocol-card=&quot;1&quot;]'))">点动1秒</button>`);
        }
        targetControls.items.forEach(ctrl => {
            actions.push(`<button class="protocol-action-btn" onclick="fireControlCenterControl(${jsArg(ctrl.id || '')})">${escapeHtml(ctrl.name || '执行')}</button>`);
        });
        return `
            <div class="protocol-device-card" data-protocol-card="1" data-target-id="${escapeHtml(target.id || '')}" data-read-do="${escapeHtml(targetControls.read_do)}" data-read-di="${escapeHtml(targetControls.read_di)}" data-do-on="${escapeHtml(targetControls.do_on)}" data-do-off="${escapeHtml(targetControls.do_off)}" data-info="${escapeHtml(targetControls.info)}" data-pulse="${escapeHtml(targetControls.pulse)}" data-info-title="${escapeHtml(displayName)}" data-info-endpoint="${escapeHtml(endpoint)}" data-info-protocol="${escapeHtml(protocolLabel || protocol)}" data-info-model="${escapeHtml(target.model || '')}" data-info-mac="${escapeHtml(target.mac || '')}" data-info-unit="${escapeHtml(target.unit_id || '01')}" data-info-do="${escapeHtml(target.do_channels ?? deviceCfg?.do_channels ?? '')}" data-info-di="${escapeHtml(target.di_channels ?? deviceCfg?.di_channels ?? '')}">
                <div class="protocol-device-head">
                    <div>
                        <div class="protocol-device-title">${escapeHtml(displayName)}</div>
                        <div class="protocol-device-meta">${escapeHtml(endpoint)}${protocolLabel ? ` / ${escapeHtml(protocolLabel)}` : ''}</div>
                    </div>
                    <span class="protocol-device-badge"><span class="protocol-led" data-led="health"></span><span class="protocol-status-value" data-text="health">读取中</span></span>
                </div>
                <div class="protocol-status-row">
                    <div class="protocol-status-pill"><div class="protocol-status-label"><span class="protocol-led" data-led="di"></span>输入</div><div class="protocol-status-value" data-text="di">读取中</div></div>
                    <div class="protocol-status-pill"><div class="protocol-status-label"><span class="protocol-led" data-led="do"></span>输出</div><div class="protocol-status-value" data-text="do">读取中</div></div>
                </div>
                <div class="protocol-switch-row">
                    <div><div class="protocol-switch-title">输出控制</div><div class="protocol-switch-sub" data-text="switch">读取状态后可切换</div></div>
                    <label class="protocol-toggle" title="输出开关"><input type="checkbox" data-role="do-toggle" onchange="toggleProtocolDeviceOutput(this)"><span></span></label>
                </div>
                <div class="protocol-device-note" data-text="note">等待首次读取</div>
                ${actions.length ? `<div class="protocol-device-actions">${actions.join('')}</div>` : ''}
            </div>
        `;
    }

    function renderProtocolDeviceCards() {
        const grid = document.getElementById('control-center-grid');
        if (!grid) return;
        const cards = [];
        getControlCenterTargets().forEach(target => {
            const controls = getVisibleHomeControlsForTarget(target.id);
            const targetControls = classifyProtocolControls(controls);
            const hasCard = targetControls.read_do || targetControls.read_di || targetControls.do_on || targetControls.do_off || targetControls.info || targetControls.pulse || targetControls.items.length;
            if (hasCard) cards.push(renderProtocolDeviceCard(target, targetControls));
        });
        grid.innerHTML = cards.length
            ? cards.join('')
            : '<div style="color:var(--text-sub); grid-column: 1/-1;">协议控制中心还没有设置主页控件，可在系统配置的“协议控制”中添加目标组、指令和控件。</div>';
    }

    function isNodeRedMigratedLegacyCommand(dev = {}, cmd = {}) {
        const text = `${dev.name || ''} ${cmd.name || ''} ${cmd.payload || ''}`;
        return text.includes('99 03 8D 66 34 58 99') || text.includes('99 03 8D 66 32 58 99');
    }

    function renderLegacyUniversalButton(dev, cmd) {
        const devId = escapeHtml(dev.id || '');
        const payload = escapeHtml(cmd.payload || '');
        const format = escapeHtml(cmd.format || 'str');
        const waitMs = Number(cmd.wait_ms || 0);
        const isLongPress = String(cmd.type || '') === 'longpress';
        const eventAttrs = isLongPress
            ? `onmousedown="handleLongPressStart(${jsArg(dev.id || '')}, ${jsArg(cmd.payload || '')}, ${jsArg(cmd.format || 'str')})" onmouseup="handleLongPressEnd(${jsArg(dev.id || '')}, ${jsArg(cmd.stop_payload || '')}, ${jsArg(cmd.format || 'str')})" onmouseleave="handleLongPressEnd(${jsArg(dev.id || '')}, ${jsArg(cmd.stop_payload || '')}, ${jsArg(cmd.format || 'str')})"`
            : `onclick="fireUniversalCommand(${jsArg(dev.id || '')}, ${jsArg(cmd.payload || '')}, ${jsArg(cmd.format || 'str')}, ${waitMs})"`;
        return `<button class="ch-btn ch-off" ${eventAttrs}>
            <span class="name">${escapeHtml(dev.name || '')} - ${escapeHtml(cmd.name || '')}</span>
            <span class="state">${isLongPress ? '长按发送 / 松开停止' : '点击执行'}</span>
        </button>`;
    }

    function renderLegacyUniversalButtons() {
        const grid = document.getElementById('universal-btn-grid');
        if (!grid) return;
        const buttons = [];
        const devices = Array.isArray(configData.custom_devices) ? configData.custom_devices : [];
        devices.forEach(dev => {
            const commands = Array.isArray(dev?.commands) ? dev.commands : [];
            commands.forEach(cmd => {
                if (!cmd?.show_on_home || isNodeRedMigratedLegacyCommand(dev, cmd)) return;
                buttons.push(renderLegacyUniversalButton(dev, cmd));
            });
        });
        grid.innerHTML = buttons.length
            ? buttons.join('')
            : '<div style="color:var(--text-sub); grid-column: 1/-1;">请先前往系统配置定义快捷指令，并勾选主页显示。</div>';
    }

    function renderUniversalPageShell() {
        const root = document.getElementById('view-universal');
        if (!root) return null;
        const shellReady = root.dataset.universalShellReady === '1'
            && document.getElementById('node-red-device-grid')
            && document.getElementById('control-center-grid')
            && document.getElementById('universal-btn-grid');
        if (shellReady) return root;
        root.innerHTML = `
            <div class="card">
                <div class="card-title">
                    <span>协议控制中心</span>
                    <span style="font-size:12px; color:var(--text-sub);">支持 TCP / UDP / 串口 / OSC / Art-Net / MIDI 配置与多目标分发</span>
                </div>
                <div class="card-title" style="margin-top:8px;">
                    <span>灯具开关</span>
                    <span style="font-size:12px; color:var(--text-sub);">单灯控制 / 网关确认亮暗状态</span>
                </div>
                <div class="node-red-device-grid" id="node-red-device-grid">
                    <div class="node-red-empty">正在加载灯具状态...</div>
                </div>
                <div class="card-title" style="margin-top:8px;">
                    <span>协议控件</span>
                    <span style="font-size:12px; color:var(--text-sub);">保留原协议控制中心配置，可继续做多目标分发</span>
                </div>
                <div class="channel-grid protocol-device-grid" id="control-center-grid" style="margin-bottom:18px;">
                    <div style="color:var(--text-sub); grid-column: 1/-1;">正在加载协议控件...</div>
                </div>
                <div class="card-title" style="margin-top:8px;">
                    <span>历史协议设备</span>
                    <span style="font-size:12px; color:var(--text-sub);">保留尚未迁移的历史协议按钮</span>
                </div>
                <div class="channel-grid" id="universal-btn-grid" style="grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));">
                    <div style="color:var(--text-sub); grid-column: 1/-1;">正在加载历史协议按钮...</div>
                </div>
            </div>
        `;
        root.dataset.universalShellReady = '1';
        universalRendered = false;
        return root;
    }

    function renderUniversalControlPage(force = false) {
        renderUniversalPageShell();
        if (universalRendered && !force) return;
        renderProtocolDeviceCards();
        renderLegacyUniversalButtons();
        universalRendered = true;
    }

    function installProtocolCardDensityStyle() {
        if (document.getElementById('protocol-card-density-runtime')) return;
        const style = document.createElement('style');
        style.id = 'protocol-card-density-runtime';
        style.textContent = `
            #control-center-grid.protocol-device-grid { grid-template-columns:repeat(auto-fill, minmax(188px, 204px)) !important; gap:9px !important; }
            #control-center-grid .protocol-device-card { min-height:194px !important; padding:8px !important; gap:7px !important; }
            #control-center-grid .protocol-device-head { gap:6px !important; }
            #control-center-grid .protocol-device-title { font-size:13px !important; }
            #control-center-grid .protocol-device-meta { font-size:10px !important; line-height:1.28 !important; }
            #control-center-grid .protocol-device-badge { min-width:44px !important; min-height:24px !important; padding:3px 6px !important; font-size:10px !important; gap:4px !important; }
            #control-center-grid .protocol-status-row { gap:5px !important; }
            #control-center-grid .protocol-status-pill { min-height:40px !important; padding:5px 6px !important; gap:3px !important; border-radius:8px !important; }
            #control-center-grid .protocol-status-label { font-size:11px !important; gap:5px !important; }
            #control-center-grid .protocol-status-value { font-size:10px !important; }
            #control-center-grid .protocol-switch-row { padding:7px 8px !important; gap:6px !important; border-radius:9px !important; }
            #control-center-grid .protocol-switch-title { font-size:13px !important; }
            #control-center-grid .protocol-switch-sub { font-size:10px !important; }
            #control-center-grid .protocol-toggle { width:46px !important; height:26px !important; }
            #control-center-grid .protocol-toggle span::before { width:20px !important; height:20px !important; left:3px !important; top:2px !important; }
            #control-center-grid .protocol-toggle input:checked + span::before { transform:translateX(20px) !important; }
            #control-center-grid .protocol-device-actions { gap:5px !important; }
            #control-center-grid .protocol-action-btn { min-height:28px !important; padding:4px 6px !important; font-size:11px !important; border-radius:7px !important; }
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
            ['最近读取', card.querySelector('[data-text="note"]')?.textContent?.trim() || '未读取'],
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

    function protocolResultError(result, fallbackText = '读取失败') {
        if (!result) return fallbackText;
        const rows = Array.isArray(result.results) ? result.results : [];
        const failed = rows.find(item => item && !item.ok);
        if (failed?.error) return String(failed.error);
        if (result.msg && result.ok === 0) return String(result.msg);
        if (result.error) return String(result.error);
        return fallbackText;
    }

    function protocolReadState(result, kind) {
        const value = parseProtocolBit(result, kind);
        if (value !== null) {
            return {
                ok: true,
                value,
                text: kind === 'do' ? (value ? '输出开' : '输出关') : (value ? '有输入' : '无输入'),
                error: '',
            };
        }
        return {
            ok: false,
            value: null,
            text: '读取失败',
            error: protocolResultError(result, '未解析到有效状态'),
        };
    }

    function stabilizeProtocolReadState(card, kind, state) {
        const cache = getProtocolReadCache(card, kind);
        const nowIso = new Date().toISOString();
        if (state.ok) {
            cache.value = state.value;
            cache.text = state.text;
            cache.updatedAt = nowIso;
            cache.failures = 0;
            cache.lastError = '';
            return Object.assign({}, state, { stale: false, failures: 0, cachedAt: nowIso });
        }
        cache.failures = Number(cache.failures || 0) + 1;
        cache.lastError = state.error || state.text || '读取失败';
        cache.lastFailedAt = nowIso;
        if (cache.updatedAt && cache.value !== undefined && cache.value !== null) {
            return Object.assign({}, state, {
                value: cache.value,
                text: cache.text || state.text,
                stale: true,
                failures: cache.failures,
                cachedAt: cache.updatedAt,
                error: cache.lastError,
            });
        }
        return Object.assign({}, state, {
            stale: false,
            failures: cache.failures,
            cachedAt: '',
            error: cache.lastError,
        });
    }

    function setProtocolLamp(card, key, state, text) {
        const led = card.querySelector(`[data-led="${key}"]`);
        const label = card.querySelector(`[data-text="${key}"]`);
        if (led) {
            led.classList.remove('on', 'off', 'warn', 'idle');
            if (state === true) led.classList.add('on');
            else if (state === false) led.classList.add(key === 'health' ? 'off' : 'idle');
            else led.classList.add('warn');
        }
        if (label) label.textContent = text || (state === true ? '正常' : (state === false ? '断开' : '异常'));
    }

    function getProtocolCardId(card) {
        return String(card?.dataset?.target || card?.dataset?.readDo || card?.dataset?.doOn || card?.dataset?.doOff || '').trim();
    }

    function setProtocolDesiredState(card, target) {
        const id = getProtocolCardId(card);
        if (!id) return;
        protocolDesiredStates[id] = { target: !!target, ts: nowMs(), confirmed: false };
    }

    function clearProtocolDesiredState(card) {
        const id = getProtocolCardId(card);
        if (id) delete protocolDesiredStates[id];
    }

    function shouldAcceptProtocolOutput(card, value) {
        const id = getProtocolCardId(card);
        const desired = id ? protocolDesiredStates[id] : null;
        if (!desired || value === null || value === undefined) return true;
        const age = nowMs() - desired.ts;
        if (!!value === desired.target) {
            desired.confirmed = true;
            desired.confirmedAt = nowMs();
            return true;
        }
        if (age < CONTROL_VERIFY_HOLD_MS) return false;
        clearProtocolDesiredState(card);
        return true;
    }

    function applyProtocolOutput(card, value) {
        const toggle = card.querySelector('[data-role="do-toggle"]');
        const switchText = card.querySelector('[data-text="switch"]');
        const cardId = getProtocolCardId(card);
        const desired = cardId ? protocolDesiredStates[cardId] : null;
        let displayValue = value;
        if (desired && nowMs() - desired.ts < CONTROL_TARGET_UI_MS) displayValue = desired.target;
        if (toggle) {
            toggle.checked = displayValue === true;
            toggle.disabled = displayValue === null;
        }
        if (switchText) switchText.textContent = displayValue === true ? '当前输出：开' : (displayValue === false ? '当前输出：关' : '状态读取失败');
    }

    function setProtocolNote(card, text, isWarn = false) {
        const note = card.querySelector('[data-text="note"]');
        if (!note) return;
        note.textContent = text || '';
        note.classList.toggle('warn', Boolean(isWarn));
    }

    function updateProtocolDeviceCard(card) {
        if (!card || card.dataset.polling === '1' || card.dataset.pulsing === '1') return Promise.resolve();
        card.dataset.polling = '1';
        const readDo = card.dataset.readDo || '';
        const readDi = card.dataset.readDi || '';
        return executeProtocolControl(readDo)
            .then(doResult => executeProtocolControl(readDi).then(diResult => [doResult, diResult]))
            .then(([doResult, diResult]) => {
                const doState = stabilizeProtocolReadState(card, 'do', protocolReadState(doResult, 'do'));
                const diState = stabilizeProtocolReadState(card, 'di', protocolReadState(diResult, 'di'));
                const okCount = Number(doState.ok) + Number(diState.ok);
                const hasDisplayState = doState.value !== null || diState.value !== null;
                const hasStaleState = Boolean(doState.stale || diState.stale);
                if (okCount === 2) setProtocolLamp(card, 'health', true, '正常');
                else if (hasStaleState) setProtocolLamp(card, 'health', null, '波动');
                else if (okCount === 1 || hasDisplayState) setProtocolLamp(card, 'health', null, '部分异常');
                else setProtocolLamp(card, 'health', false, '异常');
                setProtocolLamp(card, 'di', diState.value, diState.text);
                const acceptedDoValue = shouldAcceptProtocolOutput(card, doState.value)
                    ? doState.value
                    : protocolDesiredStates[getProtocolCardId(card)]?.target;
                setProtocolLamp(card, 'do', acceptedDoValue, doState.text);
                applyProtocolOutput(card, acceptedDoValue);
                const describeIssue = (label, state) => {
                    if (state.ok) return '';
                    if (state.stale) return `${label}本次失败(${state.failures})，保留${formatTimeShort(state.cachedAt)}`;
                    return `${label}:${state.error || '读取失败'}`;
                };
                const errors = [describeIssue('DO', doState), describeIssue('DI', diState)].filter(Boolean);
                const stamp = formatTimeShort(new Date().toISOString());
                setProtocolNote(card, errors.length ? `${errors.join('；')} · ${stamp}` : `读取正常 · ${stamp}`, errors.length > 0);
            })
            .catch(() => {
                setProtocolLamp(card, 'health', false, '异常');
                setProtocolLamp(card, 'di', null, '读取失败');
                setProtocolLamp(card, 'do', null, '读取失败');
                applyProtocolOutput(card, null);
                setProtocolNote(card, `读取请求异常 · ${formatTimeShort(new Date().toISOString())}`, true);
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
        const previousChecked = !input.checked;
        setProtocolDesiredState(card, input.checked);
        applyProtocolOutput(card, input.checked);
        input.disabled = true;
        postJson('/api/control_center/execute', { control_id: controlId, params: {} }, '协议输出控制失败')
            .then(data => {
                if (!data.ok) throw new Error(data.msg || '输出控制失败');
                notify(data.msg || '输出已切换', false);
                setTimeout(() => updateProtocolDeviceCard(card), 260);
            })
            .catch(err => {
                clearProtocolDesiredState(card);
                notify(err.message || '输出控制失败', true);
                input.checked = previousChecked;
            })
            .finally(() => { setTimeout(() => { input.disabled = false; }, 360); });
    }



    function nodeRedStatusClass(device) {
        const status = String(device?.display_status || device?.status || 'unknown').toLowerCase();
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id] || remaining > 0 || isNodeRedControlPending(device)) return 'is-busy';
        const desired = getNodeRedDesiredState(id, device);
        if (desired === true) return 'is-on';
        if (desired === false) return 'is-off';
        if (status === 'on') return 'is-on';
        if (status === 'off') return 'is-off';
        if (['starting', 'stopping', 'pending_ack', 'partial'].includes(status)) return 'is-busy';
        if (status === 'offline') return 'is-offline';
        return 'is-error';
    }

    function nodeRedActionLabel(device) {
        const status = String(device?.status || '').toLowerCase();
        const desired = getNodeRedDesiredState(device?.device_id, device);
        if (desired === true) return '关灯';
        if (desired === false) return '开灯';
        if (status === 'on' || status === 'starting' || status === 'pending_ack') return '\u5173\u706f';
        return '\u5f00\u706f';
    }

    function nodeRedActionForToggle(device) {
        const status = String(device?.status || '').toLowerCase();
        const desired = getNodeRedDesiredState(device?.device_id, device);
        if (desired === true) return 'off';
        if (desired === false) return 'on';
        return status === 'on' || status === 'starting' || status === 'pending_ack' ? 'off' : 'on';
    }

    function normalizeNodeRedDesiredState(value) {
        const text = String(value || '').toLowerCase();
        if (text === 'on') return true;
        if (text === 'off') return false;
        return null;
    }

    function getNodeRedDesiredState(deviceId, device = null) {
        const id = String(deviceId || device?.device_id || '');
        if (!id) return null;
        const desired = nodeRedDesiredStates[id];
        if (!desired) return null;
        const status = String(device?.status || '').toLowerCase();
        const actual = status === 'on' ? true : (status === 'off' ? false : null);
        if (actual === desired.target) {
            desired.confirmed = true;
            desired.confirmedAt = nowMs();
            return actual;
        }
        if (nowMs() - desired.ts < CONTROL_VERIFY_HOLD_MS) return desired.target;
        delete nodeRedDesiredStates[id];
        return actual;
    }

    function setNodeRedDesiredState(deviceId, action) {
        const id = String(deviceId || '');
        const target = normalizeNodeRedDesiredState(action);
        if (!id || target === null) return;
        nodeRedDesiredStates[id] = { target, ts: nowMs(), confirmed: false };
    }

    function clearNodeRedDesiredState(deviceId) {
        const id = String(deviceId || '');
        if (id) delete nodeRedDesiredStates[id];
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

    function nodeRedHealthParts(device) {
        const health = device?.health && typeof device.health === 'object' ? device.health : {};
        const serialOk = health.serial_connected !== false && health.serial_present !== false && String(health.status || 'ok').toLowerCase() === 'ok';
        const gatewayOnline = device?.online !== false && String(device?.display_status || '').toLowerCase() !== 'error';
        const state = device?.state && typeof device.state === 'object' ? device.state : {};
        const ackMs = Number(state.last_ack_delay_ms || device?.raw?.last_result?.ack_delay_ms || 0);
        return {
            gatewayText: gatewayOnline ? '网关在线' : '网关离线',
            gatewayOk: gatewayOnline,
            serialText: serialOk ? '串口正常' : '串口异常',
            serialOk,
            ackText: ackMs > 0 ? `回执 ${ackMs}ms` : '等待回执',
        };
    }

    function nodeRedLightStateText(device) {
        const id = String(device?.device_id || '');
        const remaining = getNodeRedCooldownRemainingSec(id, device);
        if (nodeRedPending[id]) return '\u6267\u884c\u4e2d';
        if (isNodeRedControlPending(device)) return '\u56de\u8bfb\u4e2d';
        if (remaining > 0) return `\u4fdd\u62a4 ${remaining}s`;
        const desired = getNodeRedDesiredState(id, device);
        if (desired === true) return '亮';
        if (desired === false) return '暗';
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
        const healthParts = nodeRedHealthParts(device);
        const updated = escapeHtml(formatTimeShort(device?.updated_at || ''));
        const disabled = id ? '' : 'disabled';
        const safeId = escapeHtml(id);
        const action = nodeRedActionForToggle(device);
        const desired = getNodeRedDesiredState(id, device);
        const checked = (desired === true || (desired === null && String(device?.status || '').toLowerCase() === 'on')) ? 'checked' : '';
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
                    <div class="protocol-light-switch-subtitle">Node-RED / RF 网关状态</div>
                </div>
                <span class="protocol-light-switch-state">${displayText}</span>
            </div>
            <div class="protocol-light-health-row">
                <span class="protocol-light-health-pill ${healthParts.gatewayOk ? 'ok' : 'bad'}">${escapeHtml(healthParts.gatewayText)}</span>
                <span class="protocol-light-health-pill ${healthParts.serialOk ? 'ok' : 'bad'}">${escapeHtml(healthParts.serialText)}</span>
                <span class="protocol-light-health-pill neutral">${escapeHtml(healthParts.ackText)}</span>
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
        if (!force && typeof global.getActiveViewId === 'function' && global.getActiveViewId() !== 'universal') {
            return Promise.resolve({});
        }
        renderUniversalPageShell();
        const grid = document.getElementById('node-red-device-grid');
        if (!grid) return Promise.resolve({});
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
        setNodeRedDesiredState(id, action);
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
                clearNodeRedDesiredState(id);
                return updateNodeRedDevices(true);
            })
            .catch(error => {
                clearNodeRedDesiredState(id);
                notify(error.message || '\u7f51\u7edc\u8bf7\u6c42\u9519\u8bef', true);
                return updateNodeRedDevices(true);
            })
            .finally(() => {
                delete nodeRedPending[id];
                if (inputEl) inputEl.disabled = false;
                setTimeout(() => updateNodeRedDevices(true), 80);
            });
    }

    function isUniversalViewActive() {
        if (typeof global.getActiveViewId === 'function') return global.getActiveViewId() === 'universal';
        return document.getElementById('view-universal')?.classList.contains('active') === true;
    }

    function startUniversalViewIfActive() {
        if (!isUniversalViewActive()) return;
        renderUniversalControlPage(true);
        updateProtocolDeviceCards(true);
        updateNodeRedDevices(true);
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
        renderUniversalPageShell,
        renderUniversalControlPage,
        updateNodeRedDevices,
        controlNodeRedDevice,
    };

    SmartCenter.universal = Object.assign({}, SmartCenter.universal || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        installProtocolCardDensityStyle();
        const isUniversalActive = isUniversalViewActive();
        if (isUniversalActive) renderUniversalControlPage();
        const protocolPollRegister = typeof global.registerPollingTask === 'function' ? global.registerPollingTask : (typeof SmartCenter.registerPollingTask === 'function' ? SmartCenter.registerPollingTask.bind(SmartCenter) : null);
        if (protocolPollRegister) {
            protocolPollRegister('protocol_control', 8000, () => updateProtocolDeviceCards(), () => typeof global.getActiveViewId !== 'function' || global.getActiveViewId() === 'universal');
        }
        if (isUniversalActive) {
            setTimeout(() => updateProtocolDeviceCards(true), 120);
            setTimeout(() => updateProtocolDeviceCards(true), 1100);
        }

        SmartCenter.registerModule('universal', {
            kind: 'view',
            view: 'universal',
            exports: Object.keys(api),
            source: 'static/js/views/universal.js',
        });
    }

    Object.assign(global, api);
    const ready = () => {
        startUniversalViewIfActive();
        setTimeout(startUniversalViewIfActive, 120);
    };
    if (typeof SmartCenter.onReady === 'function') SmartCenter.onReady(ready);
    else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true });
    else ready();
})(window);
