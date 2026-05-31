// AI_MODULE: door_runtime
// AI_PURPOSE: 门禁状态、视频取流、识别区框选和门禁控制运行时。
// AI_BOUNDARY: 只调用现有 /get_door_status、/video_feed、/door_control、/update_door_region，不改变后端协议。
// AI_DATA_FLOW: /get_door_status -> doorRuntime 缓存 -> door/dashboard DOM；用户点击 -> /door_control/{action}。
// AI_RUNTIME: 进入 door 视图或门禁轮询触发时按需加载，减少 app-runtime 首屏解析体积。
// AI_RISK: 高，包含真实大门控制链路；必须保留权限校验、payload 和状态回读。
// AI_SEARCH_KEYWORDS: door runtime, gate control, video feed, detection region, 门禁.

(function installSmartCenterDoorRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const initialDoorConfig = (global.configData || {}).door_config || {};
    const state = SmartCenter.doorRuntime = Object.assign({
        doorVideoActive: false,
        doorVideoNonce: 0,
        lastDoorStatusFetchAt: 0,
        doorCameraStatusCache: {},
        doorViewSlots: initialDoorConfig.view_slots || { left: 'main', right: 'aux' },
        doorRegionsCache: initialDoorConfig.regions || {},
        doorDrawState: { slot: '', isDrawing: false, startX: 0, startY: 0 },
        boundCanvasSlots: {},
    }, SmartCenter.doorRuntime || {});

    function fallbackEscapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function getContext(context = {}) {
        const provider = typeof global.getDoorRuntimeContext === 'function'
            ? (global.getDoorRuntimeContext() || {})
            : {};
        return Object.assign({
            fetchJsonLoose: utils.fetchJsonLoose || global.fetchJsonLoose,
            ensurePermission: utils.ensurePermission || global.ensurePermission || (() => false),
            showToast: utils.showToast || global.showToast || (() => {}),
            translateApiError: utils.translateApiError || global.translateApiError || ((message, fallback) => String(message || fallback || '请求失败')),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            updateDashboardDoorStatusFromEnv: global.updateDashboardDoorStatusFromEnv || (() => false),
            updateDashboardDoorStatusFromVision: global.updateDashboardDoorStatusFromVision || (() => {}),
        }, provider || {}, context || {});
    }

    function getDoorSlotCameraKey(slot) {
        const key = String((state.doorViewSlots || {})[slot] || '').trim();
        if (key) return key;
        return slot === 'right' ? 'main' : 'aux';
    }

    function getDoorSlotElements(slot) {
        const isRight = slot === 'right';
        return {
            image: document.getElementById(isRight ? 'videoImgAux' : 'videoImg'),
            canvas: document.getElementById(isRight ? 'drawCanvasAux' : 'drawCanvasMain'),
            label: document.getElementById(isRight ? 'doorCameraAuxLabel' : 'doorCameraMainLabel'),
            state: document.getElementById(isRight ? 'doorCameraAuxState' : 'doorCameraMainState'),
            meta: document.getElementById(isRight ? 'doorCameraAuxMeta' : 'doorCameraMainMeta'),
        };
    }

    function setDoorSlotVisual(slot, payload) {
        const els = getDoorSlotElements(slot);
        const stateEl = els.state;
        const metaEl = els.meta;
        if (!stateEl || !metaEl) return;
        const enabled = payload ? payload.enabled !== false : true;
        const online = !!(payload && payload.online);
        const configured = !!(payload && payload.configured);
        const transport = String((payload && payload.transport) || '').toUpperCase();
        stateEl.textContent = !enabled ? '停用' : (online ? '在线' : (configured ? '离线' : '未配置'));
        stateEl.className = `tag ${(!enabled) ? '' : (online ? 'green' : (configured ? 'warn' : ''))}`;
        if (!enabled) {
            metaEl.textContent = '监控已停用';
            return;
        }
        if (!configured) {
            metaEl.textContent = '未配置 RTSP';
            return;
        }
        if (online) {
            metaEl.textContent = `${transport || '--'} · ${payload.frame_width || '--'}x${payload.frame_height || '--'}`;
            return;
        }
        metaEl.textContent = payload.last_error_text || payload.last_error || '等待重连';
    }

    function renderDoorPageShell() {
        const container = document.getElementById('view-door');
        if (!container || document.getElementById('doorStatus')) return false;
        container.innerHTML = `
            <div class="card">
                <div class="card-title">
                    <span>门禁状态与视觉辅助</span>
                    <div style="display:flex; gap:10px; align-items: center;">
                        <span id="debugTip" style="font-size:12px; color:var(--text-sub);">加载中...</span>
                        <span id="doorStatus" class="tag door-status-unknown">检测中...</span>
                    </div>
                </div>
                <div class="video-wrapper" style="position: relative; border-radius: 12px; overflow: hidden; margin-bottom: 20px; background: linear-gradient(180deg, #020617, #0f172a); min-height: 420px; padding: 14px;">
                    <div id="doorNetworkSummary" style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px;">
                        <div style="padding:12px 14px; border-radius:12px; background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.14); color:#94a3b8; font-size:12px;">正在读取门禁视频链路诊断...</div>
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; width:100%;">
                        <div style="position:relative; border-radius:12px; overflow:hidden; min-height:220px; background:#000; border:1px solid rgba(148,163,184,0.18);">
                            <img id="videoImg" alt="大门内画面加载中..." style="width:100%; height:100%; object-fit:contain; display:block;" crossorigin="anonymous">
                            <canvas id="drawCanvasMain" style="position:absolute; inset:0; width:100%; height:100%; cursor:crosshair; display:none;"></canvas>
                            <div style="position:absolute; left:10px; top:10px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                                <span class="tag info" id="doorCameraMainLabel">左侧画面</span>
                                <span class="tag" id="doorCameraMainState">待连接</span>
                            </div>
                            <div id="doorCameraMainMeta" style="position:absolute; right:10px; bottom:10px; font-size:12px; color:#cbd5e1; background:rgba(2,6,23,0.58); border:1px solid rgba(148,163,184,0.18); padding:6px 9px; border-radius:999px;">等待取流</div>
                        </div>
                        <div style="position:relative; border-radius:12px; overflow:hidden; min-height:220px; background:#000; border:1px solid rgba(148,163,184,0.18);">
                            <img id="videoImgAux" alt="大门外画面加载中..." style="width:100%; height:100%; object-fit:contain; display:block;" crossorigin="anonymous">
                            <canvas id="drawCanvasAux" style="position:absolute; inset:0; width:100%; height:100%; cursor:crosshair; display:none;"></canvas>
                            <div style="position:absolute; left:10px; top:10px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                                <span class="tag info" id="doorCameraAuxLabel">右侧画面</span>
                                <span class="tag" id="doorCameraAuxState">待连接</span>
                            </div>
                            <div id="doorCameraAuxMeta" style="position:absolute; right:10px; bottom:10px; font-size:12px; color:#cbd5e1; background:rgba(2,6,23,0.58); border:1px solid rgba(148,163,184,0.18); padding:6px 9px; border-radius:999px;">等待取流</div>
                        </div>
                    </div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:14px;">
                        <button class="btn-base" style="background:var(--brand-blue);" onclick="startDoorVideoStream()">加载监控画面</button>
                        <button class="btn-base" style="background:#475569;" onclick="stopDoorVideoStream()">停止监控画面</button>
                    </div>
                </div>
                <div class="btn-group" style="justify-content: center; flex-wrap: wrap;">
                    <button class="btn-base" style="background:#475569;" onclick="startDrawRegion('left')">框选左侧识别区</button>
                    <button class="btn-base" style="background:#334155;" onclick="startDrawRegion('right')">框选右侧识别区</button>
                    <button class="btn-base btn-ai" onclick="openWizard()">AI 智能标定向导</button>
                    <div style="width: 20px;"></div>
                    <button class="btn-base btn-start" onclick="controlDoor('open')">开启大门</button>
                    <button class="btn-base" style="background:#64748b;" onclick="controlDoor('stop')">停止电机</button>
                    <button class="btn-base btn-stop" onclick="controlDoor('close')">关闭大门</button>
                </div>
            </div>
        `;
        return true;
    }

    function formatDoorCameraDiag(payload, context = {}) {
        const ctx = getContext(context);
        const p = payload && typeof payload === 'object' ? payload : {};
        const name = String(p.name || p.key || '--');
        const host = String(p.host || '--');
        const enabled = p.enabled === false ? '停用' : '启用';
        const configured = p.configured ? '已配置' : '未配置';
        const online = p.online ? '在线' : '离线';
        const transport = p.online ? String((p.transport || '--')).toUpperCase() : '--';
        const errorText = String(p.last_error_text || p.last_error || (p.online ? '正常' : '等待重连'));
        const lastAttempt = String(p.last_attempt_at || '--');
        return `
            <div style="padding:12px 14px; border-radius:12px; background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.14); min-width:220px; flex:1;">
                <div style="display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px;">
                    <strong style="color:#e2e8f0; font-size:13px;">${ctx.escapeHtml(name)}</strong>
                    <span class="tag ${p.online ? 'green' : 'warn'}">${ctx.escapeHtml(online)}</span>
                </div>
                <div style="font-size:12px; color:#94a3b8; line-height:1.8;">
                    <div>地址: <span style="color:#e2e8f0;">${ctx.escapeHtml(host)}</span></div>
                    <div>状态: <span style="color:#e2e8f0;">${enabled} / ${configured}</span></div>
                    <div>链路: <span style="color:#e2e8f0;">${ctx.escapeHtml(transport)}</span></div>
                    <div>错误: <span style="color:#f8fafc;">${ctx.escapeHtml(errorText)}</span></div>
                    <div>最近尝试: <span style="color:#e2e8f0;">${ctx.escapeHtml(lastAttempt)}</span></div>
                </div>
            </div>
        `;
    }

    function renderDoorNetworkSummary(context = {}) {
        const container = document.getElementById('doorNetworkSummary');
        if (!container) return;
        const leftPayload = state.doorCameraStatusCache[getDoorSlotCameraKey('left')] || {};
        const rightPayload = state.doorCameraStatusCache[getDoorSlotCameraKey('right')] || {};
        container.innerHTML = `${formatDoorCameraDiag(leftPayload, context)}${formatDoorCameraDiag(rightPayload, context)}`;
    }

    function syncDoorVideoSources(forceReload = false) {
        [['left', getDoorSlotElements('left')], ['right', getDoorSlotElements('right')]].forEach(([slot, els]) => {
            if (!els.image) return;
            const cameraKey = getDoorSlotCameraKey(slot);
            const payload = state.doorCameraStatusCache[cameraKey] || {};
            const targetSrc = `/video_feed/${cameraKey}?_=${state.doorVideoNonce}`;
            if (!state.doorVideoActive || payload.enabled === false || payload.configured === false) {
                els.image.removeAttribute('src');
                return;
            }
            const currentSrc = String(els.image.getAttribute('src') || '');
            if (forceReload || !currentSrc || !currentSrc.includes(`/video_feed/${cameraKey}`)) {
                els.image.src = targetSrc;
            }
        });
    }

    function updateDoorSlotLabels() {
        ['left', 'right'].forEach(slot => {
            const cameraKey = getDoorSlotCameraKey(slot);
            const payload = state.doorCameraStatusCache[cameraKey] || {};
            const els = getDoorSlotElements(slot);
            if (els.label) {
                const slotText = slot === 'right' ? '右侧画面' : '左侧画面';
                els.label.textContent = `${slotText} · ${payload.name || cameraKey || '--'}`;
            }
        });
    }

    function initDoorCanvas(slot) {
        const els = getDoorSlotElements(slot);
        if (!els.canvas || !els.image) return;
        bindDoorCanvas(slot);
        if (els.image.clientWidth > 0) {
            els.canvas.width = els.image.clientWidth;
            els.canvas.height = els.image.clientHeight;
        }
    }

    function bindDoorCanvas(slot) {
        if (state.boundCanvasSlots[slot]) return;
        const els = getDoorSlotElements(slot);
        if (!els.canvas || !els.image) return;
        const ctx = els.canvas.getContext('2d');
        els.image.addEventListener('load', () => initDoorCanvas(slot));
        els.canvas.addEventListener('mousedown', event => {
            if (state.doorDrawState.slot !== slot) return;
            state.doorDrawState.isDrawing = true;
            const rect = els.image.getBoundingClientRect();
            state.doorDrawState.startX = event.clientX - rect.left;
            state.doorDrawState.startY = event.clientY - rect.top;
        });
        els.canvas.addEventListener('mousemove', event => {
            if (state.doorDrawState.slot !== slot || !state.doorDrawState.isDrawing) return;
            const rect = els.image.getBoundingClientRect();
            const currentX = event.clientX - rect.left;
            const currentY = event.clientY - rect.top;
            ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
            ctx.strokeStyle = '#3b82f6';
            ctx.lineWidth = 3;
            ctx.strokeRect(
                state.doorDrawState.startX,
                state.doorDrawState.startY,
                currentX - state.doorDrawState.startX,
                currentY - state.doorDrawState.startY
            );
        });
        els.canvas.addEventListener('mouseup', event => {
            if (state.doorDrawState.slot !== slot || !state.doorDrawState.isDrawing) return;
            state.doorDrawState.isDrawing = false;
            const rect = els.image.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const endX = event.clientX - rect.left;
            const endY = event.clientY - rect.top;
            const p_x1 = Math.max(0, Math.min(state.doorDrawState.startX, endX) / rect.width);
            const p_y1 = Math.max(0, Math.min(state.doorDrawState.startY, endY) / rect.height);
            const p_x2 = Math.min(1, Math.max(state.doorDrawState.startX, endX) / rect.width);
            const p_y2 = Math.min(1, Math.max(state.doorDrawState.startY, endY) / rect.height);
            const cameraKey = getDoorSlotCameraKey(slot);
            saveDoorRegionSelection({ camera_key: cameraKey, p_x1, p_y1, p_x2, p_y2 })
                .then(data => {
                    state.doorRegionsCache[cameraKey] = (data && data.region) ? data.region : { p_x1, p_y1, p_x2, p_y2 };
                    ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
                    els.canvas.style.display = 'none';
                    state.doorDrawState.slot = '';
                })
                .catch(err => {
                    const ctxRuntime = getContext();
                    ctxRuntime.showToast(`保存失败: ${ctxRuntime.translateApiError(err?.message, '请稍后重试')}`, true);
                });
        });
        state.boundCanvasSlots[slot] = true;
    }

    function initCanvas() {
        renderDoorPageShell();
        initDoorCanvas('left');
        initDoorCanvas('right');
    }

    function startDrawRegion(slot = 'right') {
        const ctx = getContext();
        renderDoorPageShell();
        const els = getDoorSlotElements(slot);
        if (!els.canvas || !els.image) return;
        initDoorCanvas(slot);
        state.doorDrawState = { slot, isDrawing: false, startX: 0, startY: 0 };
        els.canvas.style.display = 'block';
        els.canvas.style.cursor = 'crosshair';
        ctx.showToast(`请在${slot === 'right' ? '右侧' : '左侧'}画面拖拽框选检测区域`);
    }

    function startDoorVideoStream() {
        renderDoorPageShell();
        const leftEls = getDoorSlotElements('left');
        const rightEls = getDoorSlotElements('right');
        if (!leftEls.image && !rightEls.image) return;
        state.doorVideoActive = true;
        state.doorVideoNonce += 1;
        syncDoorVideoSources(true);
        updateDoorSlotLabels();
    }

    function stopDoorVideoStream() {
        state.doorVideoActive = false;
        ['left', 'right'].forEach(slot => {
            const els = getDoorSlotElements(slot);
            if (els.image) els.image.removeAttribute('src');
        });
    }

    function saveDoorRegionSelection(regionPayload) {
        const ctx = getContext();
        if (typeof ctx.fetchJsonLoose !== 'function') return Promise.reject(new Error('fetchJsonLoose_unavailable'));
        return ctx.fetchJsonLoose('/update_door_region', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(regionPayload)
        }, '保存检测区域失败').then(data => {
            ctx.showToast(data.msg || '检测区域已更新', data.status === 'error');
            if (data.status === 'error') {
                throw new Error(data.msg || '保存检测区域失败');
            }
            return data;
        });
    }

    function requestDoorStatus() {
        const ctx = getContext();
        if (typeof ctx.fetchJsonLoose !== 'function') return Promise.reject(new Error('fetchJsonLoose_unavailable'));
        return ctx.fetchJsonLoose('/get_door_status', {}, '读取门禁状态失败');
    }

    function postDoorAction(action) {
        const ctx = getContext();
        if (typeof ctx.fetchJsonLoose !== 'function') return Promise.reject(new Error('fetchJsonLoose_unavailable'));
        return ctx.fetchJsonLoose(`/door_control/${action}`, {}, '门禁指令下发失败');
    }

    function updateDoorStatus(force = false, context = {}) {
        const ctx = getContext(context);
        if (ctx.getActiveViewId?.() === 'door') renderDoorPageShell();
        const now = Date.now();
        if (!force && now - state.lastDoorStatusFetchAt < 1000) return Promise.resolve(null);
        state.lastDoorStatusFetchAt = now;
        return requestDoorStatus()
            .then(data => {
                if (data.status !== 'success') return null;
                const cameraMap = {};
                (Array.isArray(data.cameras) ? data.cameras : []).forEach(item => {
                    const key = String(item?.key || '').trim();
                    if (key) cameraMap[key] = item;
                });
                state.doorCameraStatusCache = cameraMap;
                if (data.view_slots && typeof data.view_slots === 'object') state.doorViewSlots = data.view_slots;
                if (data.regions && typeof data.regions === 'object') state.doorRegionsCache = data.regions;
                const leftCameraKey = getDoorSlotCameraKey('left');
                const rightCameraKey = getDoorSlotCameraKey('right');
                setDoorSlotVisual('left', cameraMap[leftCameraKey] || {});
                setDoorSlotVisual('right', cameraMap[rightCameraKey] || {});
                updateDoorSlotLabels();
                renderDoorNetworkSummary(ctx);
                syncDoorVideoSources(force);
                const statusEl = document.getElementById('doorStatus');
                if (statusEl) {
                    statusEl.textContent = data.msg;
                    statusEl.className = `tag door-status-${data.door_status}`;
                }
                const debugTip = document.getElementById('debugTip');
                if (debugTip) {
                    const offlineCount = Object.values(cameraMap).filter(item => item && item.online === false && item.configured).length;
                    debugTip.textContent = offlineCount > 0 ? `视觉辅助，${offlineCount} 路视频链路异常 | ${data.diff}` : `视觉辅助识别 | ${data.diff}`;
                }
                if (!ctx.updateDashboardDoorStatusFromEnv()) ctx.updateDashboardDoorStatusFromVision(data);
                return data;
            })
            .catch(() => {
                const statusEl = document.getElementById('doorStatus');
                if (statusEl) statusEl.textContent = '检测器离线';
                setDoorSlotVisual('left', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                setDoorSlotVisual('right', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                renderDoorNetworkSummary(ctx);
                return null;
            });
    }

    function controlDoor(action, context = {}) {
        const ctx = getContext(context);
        if (!ctx.ensurePermission('door.control', '控制门禁')) return Promise.resolve(null);
        return postDoorAction(action)
            .then(data => {
                ctx.showToast(data.msg || '门禁指令已下发', data.status === 'error');
                return data;
            })
            .catch(() => {
                ctx.showToast('指令下发失败', true);
                return null;
            });
    }

    const api = {
        getStateSnapshot: () => Object.assign({}, state, {
            doorCameraStatusCache: Object.assign({}, state.doorCameraStatusCache),
            doorViewSlots: Object.assign({}, state.doorViewSlots),
            doorRegionsCache: Object.assign({}, state.doorRegionsCache),
        }),
        renderDoorPageShell,
        initCanvas,
        startDrawRegion,
        startDoorVideoStream,
        stopDoorVideoStream,
        updateDoorStatus,
        controlDoor,
    };

    Object.assign(state, api);
    global.renderDoorPageShell = renderDoorPageShell;
    global.initCanvas = initCanvas;
    global.startDrawRegion = startDrawRegion;
    global.startDoorVideoStream = startDoorVideoStream;
    global.stopDoorVideoStream = stopDoorVideoStream;
    global.updateDoorStatus = updateDoorStatus;
    global.controlDoor = controlDoor;

    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('door-runtime', {
            api,
            source: 'static/js/views/door-runtime.js',
            loadedAt: new Date().toISOString(),
        });
    }
})(window);
