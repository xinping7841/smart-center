// AI_MODULE: nvr_preview_runtime
// AI_PURPOSE: 录像机预览墙、单路直播和快照刷新运行时。
// AI_BOUNDARY: 只消费 /api/nvr/status 的前端缓存；不触发录像机控制或采集配置。
// AI_DATA_FLOW: SmartCenter.snmpRuntime.nvrStatusCache -> NVR 预览 DOM。
// AI_RUNTIME: camera_preview 视图按需懒加载，避免 SNMP 摘要页解析预览墙代码。
// AI_RISK: 中，需保持旧 onclick 全局函数由 app-runtime.js 桥接。
// AI_SEARCH_KEYWORDS: nvr preview, camera_preview, stream wall, snapshot refresh.

(function installSmartCenterNvrPreviewRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.nvrPreviewRuntime = Object.assign({
        nvrSelectedDeviceId: '',
        nvrSelectedChannelId: '',
        nvrPreviewMode: 'smart',
        nvrPreviewGrid: 16,
        nvrPreviewPage: 0,
        nvrWallFrameTimers: [],
        nvrWallSnapshotRefreshTimer: null,
    }, SmartCenter.nvrPreviewRuntime || {});

    const NVR_STREAM_CONCURRENCY_LIMIT = 8;
    const NVR_STREAM_STAGGER_MS = 520;
    const NVR_WALL_SNAPSHOT_REFRESH_MS = 10000;

    function getContext(ctx = null) {
        if (ctx && typeof ctx === 'object') return ctx;
        if (typeof global.getSnmpRuntimeContext === 'function') return global.getSnmpRuntimeContext();
        const utils = SmartCenter.utils || {};
        return {
            nvrConfigs: Array.isArray((global.configData || {}).nvr_devices) ? (global.configData || {}).nvr_devices : [],
            escapeHtml: utils.escapeHtml || (value => String(value ?? '')),
            getActiveViewId: () => 'dashboard',
        };
    }

    function getNvrStatusCache() {
        return SmartCenter.snmpRuntime?.nvrStatusCache || {};
    }

    function getNvrPreviewMode(mode = '') {
        const normalized = String(mode || '').trim().toLowerCase();
        if (['stream', 'live', 'single'].includes(normalized)) return 'stream';
        if (['stream4', 'live4'].includes(normalized)) return 'stream4';
        if (['stream8', 'live8'].includes(normalized)) return 'stream8';
        if (['snapshot', 'image'].includes(normalized)) return 'snapshot';
        return 'smart';
    }

    function getNvrPreviewGrid(grid = 16) {
        const value = Number(grid || 16);
        if (value <= 1) return 1;
        if (value <= 4) return 4;
        if (value <= 8) return 8;
        if (value <= 9) return 9;
        return 16;
    }

    function getNvrPreviewChannels(deviceId = '', ctx = null) {
        const runtimeCtx = getContext(ctx);
        const nvrConfigs = Array.isArray(runtimeCtx.nvrConfigs) ? runtimeCtx.nvrConfigs : [];
        const cfg = nvrConfigs.find(item => String(item.id) === String(deviceId))
            || nvrConfigs.find(item => item && item.visible !== false)
            || null;
        if (!cfg) return { cfg: null, status: {}, channels: [] };
        const status = getNvrStatusCache()[cfg.id] || {};
        const channels = Array.isArray(status.channels)
            ? status.channels.slice().sort((a, b) => Number(a?.id || 9999) - Number(b?.id || 9999))
            : [];
        return { cfg, status, channels };
    }

    function applyNvrPreviewUrlParams() {
        const params = new URLSearchParams(global.location.search || '');
        const mode = params.get('nvr_mode') || params.get('preview_mode') || '';
        const grid = params.get('nvr_grid') || params.get('preview_grid') || '';
        const page = params.get('nvr_page') || params.get('preview_page') || '';
        if (mode) state.nvrPreviewMode = getNvrPreviewMode(mode);
        if (grid) state.nvrPreviewGrid = getNvrPreviewGrid(grid);
        if (state.nvrPreviewMode === 'stream4') state.nvrPreviewGrid = 4;
        if (state.nvrPreviewMode === 'stream8') state.nvrPreviewGrid = 8;
        if (state.nvrPreviewMode === 'stream') state.nvrPreviewGrid = 1;
        if (page !== '') state.nvrPreviewPage = Math.max(0, Number(page) || 0);
    }

    function selectNvrPreview(deviceId, channelId, options = {}, ctx = null) {
        state.nvrSelectedDeviceId = String(deviceId || '').trim();
        state.nvrSelectedChannelId = String(channelId || '').trim();
        if (options.mode) state.nvrPreviewMode = getNvrPreviewMode(options.mode);
        if (options.grid) state.nvrPreviewGrid = getNvrPreviewGrid(options.grid);
        if (options.page !== undefined) state.nvrPreviewPage = Math.max(0, Number(options.page || 0));
        if (options.live) {
            state.nvrPreviewGrid = 1;
            state.nvrPreviewMode = 'stream';
            state.nvrPreviewPage = 0;
        }
        renderNvrPreviewPanel({ refresh: !!options.refresh }, ctx);
    }

    function setNvrPreviewMode(mode, ctx = null) {
        state.nvrPreviewMode = getNvrPreviewMode(mode);
        if (state.nvrPreviewMode === 'stream') state.nvrPreviewGrid = 1;
        if (state.nvrPreviewMode === 'stream4') state.nvrPreviewGrid = 4;
        if (state.nvrPreviewMode === 'stream8') state.nvrPreviewGrid = 8;
        state.nvrPreviewPage = 0;
        renderNvrPreviewPanel({ refresh: true }, ctx);
    }

    function setNvrPreviewGrid(grid, ctx = null) {
        state.nvrPreviewGrid = getNvrPreviewGrid(grid);
        if (state.nvrPreviewGrid > 1 && state.nvrPreviewMode === 'stream') {
            state.nvrPreviewMode = state.nvrPreviewGrid > 4 ? 'stream8' : 'stream4';
        }
        if (state.nvrPreviewMode === 'stream4' && state.nvrPreviewGrid !== 4) state.nvrPreviewMode = 'smart';
        if (state.nvrPreviewMode === 'stream8' && state.nvrPreviewGrid !== 8) state.nvrPreviewMode = 'smart';
        state.nvrPreviewPage = 0;
        renderNvrPreviewPanel({ refresh: true }, ctx);
    }

    function setNvrPreviewPage(delta, ctx = null) {
        state.nvrPreviewPage = Math.max(0, Number(state.nvrPreviewPage || 0) + Number(delta || 0));
        renderNvrPreviewPanel({ refresh: true }, ctx);
    }

    function activateNvrWallFrame(frame) {
        if (!frame || !frame.isConnected || frame.dataset.loaded === '1') return;
        const src = frame.dataset.src;
        if (!src) return;
        frame.dataset.loaded = '1';
        const cell = frame.closest('.nvr-wall-cell');
        if (cell) cell.classList.add('loading');
        frame.src = src;
    }

    function scheduleNvrWallFrames() {
        while (state.nvrWallFrameTimers.length) global.clearTimeout(state.nvrWallFrameTimers.pop());
        const frames = Array.from(document.querySelectorAll('#nvr-preview-panel iframe[data-nvr-lazy="1"]'));
        frames.forEach((frame, index) => {
            const timer = global.setTimeout(() => activateNvrWallFrame(frame), index * NVR_STREAM_STAGGER_MS);
            state.nvrWallFrameTimers.push(timer);
        });
    }

    function stopNvrWallSnapshotRefresh() {
        if (state.nvrWallSnapshotRefreshTimer) {
            global.clearTimeout(state.nvrWallSnapshotRefreshTimer);
            state.nvrWallSnapshotRefreshTimer = null;
        }
    }

    function scheduleNvrWallSnapshotRefresh(ctx = null) {
        const runtimeCtx = getContext(ctx);
        stopNvrWallSnapshotRefresh();
        if (runtimeCtx.getActiveViewId() !== 'camera_preview') return;
        if (document.hidden || getNvrPreviewGrid(state.nvrPreviewGrid) <= 1) return;
        const mode = getNvrPreviewMode(state.nvrPreviewMode);
        if (!['smart', 'snapshot'].includes(mode)) return;
        state.nvrWallSnapshotRefreshTimer = global.setTimeout(() => {
            renderNvrPreviewPanel({ refresh: true, autoRefresh: true }, runtimeCtx);
        }, NVR_WALL_SNAPSHOT_REFRESH_MS);
    }

    function stopNvrPreviewStreams() {
        while (state.nvrWallFrameTimers.length) global.clearTimeout(state.nvrWallFrameTimers.pop());
        stopNvrWallSnapshotRefresh();
        const panel = document.getElementById('nvr-preview-panel');
        if (!panel) return;
        panel.querySelectorAll('iframe').forEach(frame => {
            try { frame.src = 'about:blank'; } catch (_) {}
            try { frame.removeAttribute('src'); } catch (_) {}
        });
        panel.querySelectorAll('.nvr-wall-cell.loading, .nvr-preview-frame.loading').forEach(el => el.classList.remove('loading'));
    }

    function getNvrChannelSnapshotUrl(cfg, channel) {
        return channel.snapshot_url || channel.preview_url || channel.image_url || cfg.snapshot_url || cfg.preview_url || '';
    }

    function getNvrChannelStreamUrl(cfg, channel) {
        return channel.stream_url || channel.live_url || channel.iframe_url || cfg.stream_url || cfg.live_url || '';
    }

    function buildNvrPreviewPanelHtml(payload, ctx = null) {
        const runtimeCtx = getContext(ctx);
        const escapeHtml = runtimeCtx.escapeHtml;
        const cfg = payload.cfg || {};
        const channels = Array.isArray(payload.channels) ? payload.channels : [];
        const selected = payload.selected || channels[0] || {};
        const previewMode = getNvrPreviewMode(payload.previewMode);
        const previewGrid = getNvrPreviewGrid(payload.previewGrid);
        const totalPages = Math.max(1, Math.ceil(channels.length / previewGrid));
        const currentPage = Math.min(Math.max(0, Number(payload.previewPage || 0)), totalPages - 1);
        const pageChannels = channels.slice(currentPage * previewGrid, currentPage * previewGrid + previewGrid);
        const liveUrl = getNvrChannelStreamUrl(cfg, selected);
        const snapshotUrl = getNvrChannelSnapshotUrl(cfg, selected);
        const selectedName = selected.name || selected.label || `D${selected.id || '--'}`;
        const channelButton = item => {
            const active = String(item.id) === String(selected.id);
            const online = item.online !== false;
            return `<button type="button" class="nvr-channel-btn ${active ? 'active' : ''} ${online ? '' : 'offline'}" onclick="selectNvrPreview('${escapeHtml(String(cfg.id || ''))}', '${escapeHtml(String(item.id || ''))}', { refresh: true })">
                <span>${escapeHtml(item.name || item.label || `D${item.id || '--'}`)}</span>
                <small>${online ? '在线' : '离线'}</small>
            </button>`;
        };
        const stageHtml = previewGrid <= 1
            ? `<div class="nvr-preview-frame ${liveUrl && previewMode === 'stream' ? 'loading' : ''}">
                ${liveUrl && previewMode === 'stream'
                    ? `<iframe data-nvr-lazy="1" data-src="${escapeHtml(liveUrl)}" title="${escapeHtml(selectedName)}"></iframe>`
                    : (snapshotUrl
                        ? `<img src="${escapeHtml(snapshotUrl)}${snapshotUrl.includes('?') ? '&' : '?'}_=${Date.now()}" alt="${escapeHtml(selectedName)}">`
                        : `<div class="nvr-preview-empty">${escapeHtml(selectedName)} 暂无预览地址</div>`)}
            </div>`
            : `<div class="nvr-wall-grid nvr-wall-grid-${previewGrid}">
                ${pageChannels.map(item => {
                    const streamUrl = getNvrChannelStreamUrl(cfg, item);
                    const imageUrl = getNvrChannelSnapshotUrl(cfg, item);
                    const title = item.name || item.label || `D${item.id || '--'}`;
                    return `<div class="nvr-wall-cell ${item.online === false ? 'offline' : ''}">
                        <div class="nvr-wall-title">${escapeHtml(title)}</div>
                        ${streamUrl && ['stream4', 'stream8'].includes(previewMode)
                            ? `<iframe data-nvr-lazy="1" data-src="${escapeHtml(streamUrl)}" title="${escapeHtml(title)}"></iframe>`
                            : (imageUrl
                                ? `<img src="${escapeHtml(imageUrl)}${imageUrl.includes('?') ? '&' : '?'}_=${Date.now()}" alt="${escapeHtml(title)}">`
                                : `<div class="nvr-preview-empty">暂无预览</div>`)}
                    </div>`;
                }).join('')}
            </div>`;
        return {
            currentPage,
            html: `<div class="nvr-preview-layout">
                <div class="nvr-preview-stage">
                    <div class="nvr-preview-head">
                        <div>
                            <div class="nvr-preview-title">${escapeHtml(cfg.name || '录像机预览')}</div>
                            <div class="nvr-preview-subtitle">${escapeHtml(cfg.host || '--')} · 当前 ${escapeHtml(selectedName)} · 第 ${currentPage + 1}/${totalPages} 页</div>
                        </div>
                        <div class="nvr-preview-tools">
                            <button class="nvr-preview-mode-btn ${previewMode === 'smart' ? 'active' : ''}" type="button" onclick="setNvrPreviewMode('smart')">智能</button>
                            <button class="nvr-preview-mode-btn ${previewMode === 'snapshot' ? 'active' : ''}" type="button" onclick="setNvrPreviewMode('snapshot')">快照</button>
                            <button class="nvr-preview-mode-btn ${previewMode === 'stream' ? 'active' : ''}" type="button" onclick="setNvrPreviewMode('stream')">单路直播</button>
                            <button class="nvr-preview-mode-btn ${previewMode === 'stream4' ? 'active' : ''}" type="button" onclick="setNvrPreviewMode('stream4')">4路</button>
                            <button class="nvr-preview-mode-btn ${previewMode === 'stream8' ? 'active' : ''}" type="button" onclick="setNvrPreviewMode('stream8')">8路</button>
                        </div>
                    </div>
                    ${stageHtml}
                    <div class="nvr-preview-tools">
                        <button class="nvr-preview-btn" type="button" onclick="setNvrPreviewGrid(4)">4宫格</button>
                        <button class="nvr-preview-btn" type="button" onclick="setNvrPreviewGrid(9)">9宫格</button>
                        <button class="nvr-preview-btn" type="button" onclick="setNvrPreviewGrid(16)">16宫格</button>
                        <button class="nvr-preview-btn" type="button" onclick="setNvrPreviewPage(-1)">上一页</button>
                        <button class="nvr-preview-btn" type="button" onclick="setNvrPreviewPage(1)">下一页</button>
                    </div>
                </div>
                <div class="nvr-channel-list">
                    <div class="nvr-preview-badges">
                        <span class="ups-chip">通道 ${channels.length}</span>
                        <span class="ups-chip">并发 ${payload.streamLimit || NVR_STREAM_CONCURRENCY_LIMIT}</span>
                        <span class="ups-chip">刷新 ${Math.round((payload.snapshotRefreshMs || NVR_WALL_SNAPSHOT_REFRESH_MS) / 1000)}s</span>
                    </div>
                    ${channels.map(channelButton).join('')}
                </div>
            </div>`,
        };
    }

    function renderNvrPreviewPanel(options = {}, ctx = null) {
        const runtimeCtx = getContext(ctx);
        const panel = document.getElementById('nvr-preview-panel');
        if (!panel) return;
        stopNvrPreviewStreams();
        const visibleNvrConfigs = (Array.isArray(runtimeCtx.nvrConfigs) ? runtimeCtx.nvrConfigs : []).filter(cfg => cfg && cfg.visible !== false);
        if (!visibleNvrConfigs.length) {
            panel.innerHTML = '<div class="nvr-preview-empty">未配置录像机设备。</div>';
            return;
        }
        const selectedExists = visibleNvrConfigs.some(cfg => String(cfg.id) === String(state.nvrSelectedDeviceId));
        if (!state.nvrSelectedDeviceId || !selectedExists) {
            state.nvrSelectedDeviceId = String(visibleNvrConfigs[0].id || '');
        }
        let { cfg, status, channels } = getNvrPreviewChannels(state.nvrSelectedDeviceId, runtimeCtx);
        if (!cfg) {
            panel.innerHTML = '<div class="nvr-preview-empty">未找到可预览的录像机。</div>';
            return;
        }
        if (!channels.length) {
            const expected = Number(cfg.expected_channel_count || cfg.channel_count || 0);
            channels = Array.from({ length: expected || 32 }, (_, index) => ({
                id: String(index + 1),
                name: `D${index + 1}`,
                online: false,
            }));
        }
        const channelExists = channels.some(item => String(item.id) === String(state.nvrSelectedChannelId));
        if (!state.nvrSelectedChannelId || !channelExists) {
            const firstOnline = channels.find(item => item && item.online);
            state.nvrSelectedChannelId = String((firstOnline || channels[0] || {}).id || '');
        }
        const selected = channels.find(item => String(item.id) === String(state.nvrSelectedChannelId)) || channels[0] || {};
        const preview = buildNvrPreviewPanelHtml({
            cfg,
            status,
            channels,
            selected,
            selectedChannelId: state.nvrSelectedChannelId,
            previewMode: state.nvrPreviewMode,
            previewGrid: state.nvrPreviewGrid,
            previewPage: state.nvrPreviewPage,
            streamLimit: NVR_STREAM_CONCURRENCY_LIMIT,
            snapshotRefreshMs: NVR_WALL_SNAPSHOT_REFRESH_MS,
            options,
        }, runtimeCtx);
        state.nvrPreviewPage = preview.currentPage;
        panel.innerHTML = preview.html;
        scheduleNvrWallFrames();
        scheduleNvrWallSnapshotRefresh(runtimeCtx);
    }

    const api = {
        getNvrStatusCache,
        getNvrPreviewMode,
        getNvrPreviewGrid,
        getNvrPreviewChannels,
        applyNvrPreviewUrlParams,
        selectNvrPreview,
        setNvrPreviewMode,
        setNvrPreviewGrid,
        setNvrPreviewPage,
        stopNvrPreviewStreams,
        buildNvrPreviewPanelHtml,
        renderNvrPreviewPanel,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.nvr_preview_runtime', {
            kind: 'view-runtime',
            exports: Object.keys(api),
            source: 'static/js/views/nvr-preview-runtime.js',
        });
    }
})(window);
