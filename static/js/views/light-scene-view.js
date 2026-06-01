// AI_MODULE: light_scene_view
// AI_PURPOSE: 按需生成灯光页设备卡片和场景页按钮，替代 templates/index.html 中的 Jinja 循环。
// AI_BOUNDARY: 只生成 DOM；真实灯光/场景控制继续走 light-runtime 暴露的 toggleLight/executeScene。
// AI_DATA_FLOW: window.configData.light_devices/scenes/automations -> light/scene 页面 DOM -> light-runtime 控制函数。
// AI_RUNTIME: 进入 light 或 scene 视图时懒加载，降低首页初始 HTML 体积。
// AI_RISK: 高，按钮指向真实设备控制函数，渲染时必须保持设备 ID、通道号和场景 ID 原样。
// AI_SEARCH_KEYWORDS: light page render, scene page render, template slim, lighting scene.

(function installSmartCenterLightSceneView(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.lightSceneView = Object.assign({
        lightRendered: false,
        sceneRendered: false,
    }, SmartCenter.lightSceneView || {});

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
        return escapeHtml(JSON.stringify(value ?? ''));
    }

    function config() {
        return global.configData && typeof global.configData === 'object' ? global.configData : {};
    }

    function bySort(a = {}, b = {}) {
        return Number(a.sort ?? 9999) - Number(b.sort ?? 9999);
    }

    function visibleRows(rows) {
        return (Array.isArray(rows) ? rows : [])
            .filter(item => item && item.visible !== false)
            .sort(bySort);
    }

    function renderLightChannelButton(deviceId, channel = {}) {
        const channelNo = Number(channel.channel || 0);
        if (!channelNo) return '';
        const span = Math.max(1, Math.min(4, Number(channel.span || 1)));
        return `<button class="ch-btn ch-err ch-span-${span}" id="lch_${escapeHtml(deviceId)}_${channelNo}" onclick="toggleLight(${jsArg(String(deviceId))}, ${channelNo})">
            <span class="name">${escapeHtml(channel.name || `第${channelNo}路`)}</span>
            <span class="state">离线</span>
        </button>`;
    }

    function renderLightInputChip(deviceId, channel = {}) {
        const channelNo = Number(channel.channel || 0);
        if (!channelNo) return '';
        const span = Math.max(1, Math.min(4, Number(channel.span || 1)));
        return `<div class="relay-input-chip unknown ch-span-${span}" id="lin_${escapeHtml(deviceId)}_${channelNo}">
            <span class="name">${escapeHtml(channel.name || `输入${channelNo}`)}</span>
            <span class="state">待确认</span>
        </div>`;
    }

    function renderLightActionButton(deviceId, action = {}) {
        if (!action || action.visible === false) return '';
        const actionName = String(action.action || '');
        const label = String(action.label || actionName || '动作');
        if (!actionName) return '';
        return `<button class="dashboard-mini-btn secondary" onclick="triggerLightAction(${jsArg(String(deviceId))}, ${jsArg(actionName)}, ${jsArg(label)})">${escapeHtml(label)}</button>`;
    }

    function renderLightDeviceCard(device = {}) {
        const deviceId = String(device.id ?? '');
        if (!deviceId) return '';
        const channels = visibleRows(device.channels_config).map(ch => renderLightChannelButton(deviceId, ch)).join('');
        const inputs = visibleRows(device.input_channels_config);
        const inputPanel = inputs.length ? `
            <div class="relay-input-panel" id="light-input-panel-${escapeHtml(deviceId)}">
                <div class="relay-input-title">输入接口状态</div>
                <div class="relay-input-grid" id="light-inputs-${escapeHtml(deviceId)}">
                    ${inputs.map(ch => renderLightInputChip(deviceId, ch)).join('')}
                </div>
            </div>` : '';
        const actions = (Array.isArray(device.dashboard_action_buttons) ? device.dashboard_action_buttons : [])
            .map(action => renderLightActionButton(deviceId, action))
            .filter(Boolean)
            .join('');
        const actionPanel = actions ? `<div class="dashboard-mini-actions" style="margin-top:-4px;">${actions}</div>` : '';
        const endpoint = `${device.ip || ''}${device.port ? `:${device.port}` : ''}`;
        return `<div class="card">
            <div class="cab-header">
                <h3>${escapeHtml(device.name || `灯光设备 ${deviceId}`)}</h3>
                <span class="tag error" id="light-status-${escapeHtml(deviceId)}">检测中</span>
            </div>
            <div class="info-bar">
                <div>品牌:<span>${escapeHtml(device.brand || '--')}</span></div>
                <div>站号:<span>${escapeHtml(device.slave_id ?? '--')}</span></div>
                <div>地址:<span>${escapeHtml(endpoint || '--')}</span></div>
            </div>
            <div class="light-diagnostic-panel offline" id="light-diagnostic-${escapeHtml(deviceId)}">
                <div class="light-diagnostic-item"><span>状态</span><strong>检测中</strong></div>
                <div class="light-diagnostic-item"><span>连续失败</span><strong>--</strong></div>
                <div class="light-diagnostic-item"><span>最近检查</span><strong>--</strong></div>
                <div class="light-diagnostic-reason">正在读取灯光控制器状态...</div>
            </div>
            <div class="channel-grid" id="light-channels-${escapeHtml(deviceId)}">
                ${channels || '<div style="color:var(--text-sub); grid-column:1/-1;">未配置可见输出通道</div>'}
            </div>
            ${inputPanel}
            ${actionPanel}
        </div>`;
    }

    function renderLightPage(force = false) {
        if (state.lightRendered && !force) return;
        const container = document.getElementById('light-page-grid');
        if (!container) return;
        const devices = Array.isArray(config().light_devices) ? config().light_devices : [];
        container.innerHTML = devices.length
            ? devices.map(renderLightDeviceCard).join('')
            : '<div class="card"><div style="color:var(--text-sub); text-align:center; padding:20px;">未配置灯光设备</div></div>';
        state.lightRendered = true;
    }

    function getSceneRefs(sceneId) {
        const id = String(sceneId ?? '');
        return (Array.isArray(config().automations) ? config().automations : [])
            .filter(rule => String(rule?.action_scene_id ?? '') === id)
            .map(rule => String(rule?.name || rule?.id || '未命名规则'));
    }

    function formatSceneAction(action = {}) {
        const sub = String(action.sub_system || '').trim();
        const type = String(action.action_type || action.action || '').trim();
        if (sub === 'hvac') {
            if (type === 'power_on') return '空调 开机';
            if (type === 'power_off') return '空调 关机';
            if (type === 'set_mode') return `空调 模式 ${action.mode || ''}`.trim();
            if (type === 'set_temp') return `空调 ${action.temperature ?? '--'}°C`;
            if (type === 'set_fan_mode') return `空调 风量 ${action.fan_mode || ''}`.trim();
            return `空调 ${type || '动作'}`;
        }
        if (sub === 'node_red') return `Node-RED ${type || '动作'}`;
        if (sub === 'universal') return '发送指令';
        if (sub === 'screen') return `幕布 ${type || '动作'}`;
        if (sub === 'projector') return `投影 ${type || '动作'}`;
        return `${sub || '设备'} ${type || '动作'}`;
    }

    function renderQuickScene(scene = {}) {
        return `<button class="scene-btn scene-quick-btn" onclick="executeScene(${jsArg(scene.id)}, ${jsArg(scene.name)})">
            <span>场景</span>
            <strong>${escapeHtml(scene.name || scene.id || '未命名场景')}</strong>
        </button>`;
    }

    function renderAutomationScene(scene = {}, refs = []) {
        const actions = Array.isArray(scene.actions) ? scene.actions : [];
        const title = `点击测试触发\nID: ${scene.id || ''}\n引用规则：${refs.join(' / ')}`;
        const actionHtml = actions.map(action => `<span>${escapeHtml(formatSceneAction(action))}</span>`).join('');
        return `<button type="button" class="automation-scene-card" onclick="executeScene(${jsArg(scene.id)}, ${jsArg(scene.name)})" title="${escapeHtml(title)}">
            <div class="automation-scene-main">
                <div class="automation-scene-title-row">
                    <span class="automation-scene-badge">自动化专用</span>
                    <strong>${escapeHtml(scene.name || scene.id || '未命名场景')}</strong>
                </div>
                <div class="automation-scene-meta">
                    <span>${actions.length}步动作</span>
                    <span>${refs.length}条规则</span>
                </div>
                <div class="automation-scene-refs">${escapeHtml(refs.join(' / '))}</div>
                <div class="automation-scene-actions">${actionHtml}</div>
            </div>
            <span class="automation-scene-test-btn">测试</span>
        </button>`;
    }

    function renderScenePage(force = false) {
        if (state.sceneRendered && !force) return;
        const quickGrid = document.getElementById('scene-quick-grid');
        const automationGrid = document.getElementById('automation-scene-grid');
        if (!quickGrid && !automationGrid) return;
        const scenes = (Array.isArray(config().scenes) ? config().scenes : []).slice().sort(bySort);
        if (quickGrid) {
            const quickScenes = scenes.filter(scene => scene && scene.visible);
            quickGrid.innerHTML = quickScenes.length
                ? quickScenes.map(renderQuickScene).join('')
                : '<div class="scene-empty">尚未配置手动快捷场景，可在系统配置中添加并设为可见。</div>';
        }
        if (automationGrid) {
            const autoScenes = scenes
                .map(scene => ({ scene, refs: getSceneRefs(scene?.id) }))
                .filter(item => item.refs.length > 0);
            automationGrid.innerHTML = autoScenes.length
                ? autoScenes.map(item => renderAutomationScene(item.scene, item.refs)).join('')
                : '<div class="scene-empty">当前没有被自动化规则引用的场景。</div>';
        }
        state.sceneRendered = true;
    }

    function renderLightSceneView(viewId = '') {
        const activeView = String(viewId || (typeof global.getActiveViewId === 'function' ? global.getActiveViewId() : '') || '');
        if (!activeView || activeView === 'light') renderLightPage();
        if (!activeView || activeView === 'scene') renderScenePage();
    }

    const api = {
        renderLightPage,
        renderScenePage,
        renderLightSceneView,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('light-scene-view', {
            kind: 'view-renderer',
            exports: Object.keys(api),
            source: 'static/js/views/light-scene-view.js',
        });
    }

    global.renderLightPage = renderLightPage;
    global.renderScenePage = renderScenePage;
    global.renderLightSceneView = renderLightSceneView;
})(window);
