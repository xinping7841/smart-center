// AI_MODULE: snmp_runtime
// AI_PURPOSE: SNMP/NVR 状态轮询、首页卡片、SNMP 详情页和监控预览运行时编排。
// AI_BOUNDARY: 不解析 SNMP OID、不改设备采集；只消费 /api/snmp/status 与 /api/nvr/status。
// AI_DATA_FLOW: API 状态 -> SmartCenter.snmp 渲染函数 -> DOM；旧全局入口由 app-runtime.js 转发到本模块。
// AI_RUNTIME: 按需懒加载，避免首页首屏解析完整 SNMP/NVR 编排代码。
// AI_RISK: 中，需保持 SNMP 页面、首页摘要、监控预览三个入口兼容。
// AI_SEARCH_KEYWORDS: snmp runtime, nvr preview, dashboard snmp, lazy-load.

(function installSmartCenterSnmpRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.snmpRuntime = Object.assign({
        snmpStatusCache: {},
        nvrStatusCache: {},
        snmpCardFilter: 'all',
        snmpStatusSignature: '',
        snmpLastSuccessAt: 0,
        snmpFetchFailureCount: 0,
        snmpLastToastAt: 0,
        snmpFetchInFlight: null,
        snmpFetchMode: '',
        snmpStatusMode: '',
        snmpLastRenderAt: 0,
        snmpSelectedDeviceId: '',
        nvrSelectedDeviceId: '',
        nvrSelectedChannelId: '',
        nvrPreviewMode: 'smart',
        nvrPreviewGrid: 16,
        nvrPreviewPage: 0,
        nvrWallFrameTimers: [],
        nvrWallSnapshotRefreshTimer: null,
    }, SmartCenter.snmpRuntime || {});

    const NVR_STREAM_CONCURRENCY_LIMIT = 8;
    const NVR_STREAM_STAGGER_MS = 520;
    const NVR_WALL_SNAPSHOT_REFRESH_MS = 10000;

    function getContext(ctx = null) {
        if (ctx && typeof ctx === 'object') return ctx;
        if (typeof global.getSnmpRuntimeContext === 'function') return global.getSnmpRuntimeContext();
        const utils = SmartCenter.utils || {};
        return {
            configData: global.configData || {},
            snmpConfigs: ((global.configData || {}).snmp_devices || []),
            nvrConfigs: Array.isArray((global.configData || {}).nvr_devices) ? (global.configData || {}).nvr_devices : [],
            fetchJson: utils.fetchJson,
            showToast: utils.showToast || (() => {}),
            translateApiError: utils.translateApiError || ((_, fallback) => fallback),
            escapeHtml: utils.escapeHtml || (value => String(value ?? '')),
            getDeviceStatusMeta: utils.getDeviceStatusMeta || (status => ({ level: status?.online ? 'online' : 'offline', text: status?.online ? '在线' : '离线', chipClass: status?.online ? 'online' : 'error', isOnlineLike: !!status?.online })),
            getActiveViewId: () => 'dashboard',
            isDashboardSectionVisible: () => false,
            ensureViewReady: viewId => SmartCenter.ensureViewModules ? SmartCenter.ensureViewModules(viewId) : Promise.resolve([]),
            guardFrontendStep: (_scope, fn) => fn(),
        };
    }

    function snmpApi() {
        return SmartCenter.snmp || {};
    }

    function getNetworkMonitorConfigs(ctx = null) {
        const runtimeCtx = getContext(ctx);
        const snmpConfigs = Array.isArray(runtimeCtx.snmpConfigs) ? runtimeCtx.snmpConfigs : [];
        const nvrConfigs = Array.isArray(runtimeCtx.nvrConfigs) ? runtimeCtx.nvrConfigs : [];
        return [
            ...snmpConfigs.map(cfg => Object.assign({ monitor_kind: 'snmp' }, cfg)),
            ...nvrConfigs.map(cfg => Object.assign({ monitor_kind: 'nvr', device_type: 'nvr' }, cfg)),
        ].filter(cfg => cfg && cfg.visible !== false);
    }

    function getNetworkStatusCache() {
        return Object.assign({}, state.snmpStatusCache || {}, state.nvrStatusCache || {});
    }

    function syncSnmpSelectedDeviceToUrl(deviceId = '') {
        try {
            const url = new URL(global.location.href);
            const safeDeviceId = String(deviceId || '').trim();
            if (safeDeviceId) {
                url.searchParams.set('snmp_device', safeDeviceId);
            } else {
                url.searchParams.delete('snmp_device');
            }
            global.history.replaceState(null, '', url.toString());
        } catch (_) {}
    }

    function restoreSnmpSelectedDeviceFromUrl() {
        try {
            const params = new URLSearchParams(global.location.search || '');
            state.snmpSelectedDeviceId = String(params.get('snmp_device') || params.get('device') || '').trim();
        } catch (_) {
            state.snmpSelectedDeviceId = '';
        }
        return state.snmpSelectedDeviceId;
    }

    function clearSnmpSelectedDevice() {
        if (!state.snmpSelectedDeviceId) return;
        state.snmpSelectedDeviceId = '';
        syncSnmpSelectedDeviceToUrl('');
    }

    function openSnmpDeviceDetail(deviceId, ctx = null) {
        const safeDeviceId = String(deviceId || '').trim();
        if (!safeDeviceId) return;
        state.snmpSelectedDeviceId = safeDeviceId;
        syncSnmpSelectedDeviceToUrl(safeDeviceId);
        const runtimeCtx = getContext(ctx);
        runtimeCtx.ensureViewReady('snmp')
            .then(() => renderSnmpCards({ mode: 'full', renderDetailPage: true }, runtimeCtx))
            .catch(() => {});
    }

    function closeSnmpDeviceDetail(ctx = null) {
        state.snmpSelectedDeviceId = '';
        syncSnmpSelectedDeviceToUrl('');
        const runtimeCtx = getContext(ctx);
        runtimeCtx.ensureViewReady('snmp')
            .then(() => renderSnmpCards({ mode: 'full', renderDetailPage: true }, runtimeCtx))
            .catch(() => {});
    }

    function bindSnmpOverviewCardActions(scopeEl, ctx = null) {
        const root = scopeEl || document;
        root.querySelectorAll('[data-snmp-device-card]').forEach(card => {
            if (card.dataset.snmpOpenBound === '1') return;
            card.dataset.snmpOpenBound = '1';
            const open = () => openSnmpDeviceDetail(card.getAttribute('data-snmp-device-id'), ctx);
            card.addEventListener('click', event => {
                if (event.target && event.target.closest && event.target.closest('button[data-snmp-filter]')) return;
                open();
            });
            card.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    open();
                }
            });
        });
        root.querySelectorAll('[data-snmp-back-overview]').forEach(btn => {
            if (btn.dataset.snmpBackBound === '1') return;
            btn.dataset.snmpBackBound = '1';
            btn.addEventListener('click', () => closeSnmpDeviceDetail(ctx));
        });
    }

    function summarizeSnmpPayload(payload, ctx = null) {
        const runtimeCtx = getContext(ctx);
        return getNetworkMonitorConfigs(runtimeCtx).map(cfg => {
            const status = (payload || {})[cfg.id] || {};
            const statusMeta = runtimeCtx.getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const summary = status.summary || {};
            const interfaceSummary = summary.interface_summary || {};
            return [
                cfg.id,
                statusMeta.level,
                statusMeta.isOnlineLike ? 1 : 0,
                status.updated_at || '',
                status.error || '',
                summary.risk_level || '',
                summary.health_score ?? '',
                (summary.alert_counts || {}).warning ?? 0,
                (summary.alert_counts || {}).critical ?? 0,
                interfaceSummary.physical_up_count ?? '',
                interfaceSummary.physical_down_count ?? '',
                interfaceSummary.aggregate_total_rate_text || '',
                summary.cpu_avg_percent ?? '',
                summary.memory_usage_percent ?? '',
                summary.channel_online ?? '',
                summary.channel_total ?? '',
                summary.hdd_error_count ?? '',
            ].join('|');
        }).join('~');
    }

    function normalizeNvrStatusForSnmp(cfg, status) {
        const api = snmpApi();
        if (api && typeof api.normalizeNvrStatusForSnmp === 'function') {
            return api.normalizeNvrStatusForSnmp(cfg, status);
        }
        const source = status && typeof status === 'object' ? status : {};
        const channels = Array.isArray(source.channels) ? source.channels : [];
        const onlineChannels = channels.filter(item => item && item.online !== false).length;
        const expectedCount = Number(cfg?.expected_channel_count || cfg?.channel_count || channels.length || 0);
        const online = source.online !== undefined ? !!source.online : !source.error;
        return Object.assign({}, source, {
            id: source.id || cfg?.id,
            host: source.host || cfg?.host,
            online,
            summary: Object.assign({
                device_type: 'nvr',
                risk_level: online ? 'normal' : 'warning',
                health_score: online ? 92 : 0,
                channel_online: onlineChannels,
                channel_total: expectedCount || channels.length,
                alert_counts: {
                    critical: online ? 0 : 1,
                    warning: online && expectedCount && onlineChannels < expectedCount ? 1 : 0,
                    info: 0,
                },
            }, source.summary || {}),
        });
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
        const status = state.nvrStatusCache[cfg.id] || {};
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
        if (options.page !== undefined) state.nvrPreviewPage = Math.max(0, Number(options.page) || 0);
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

    function renderSnmpCards(options = {}, ctx = null) {
        const runtimeCtx = getContext(ctx);
        const api = snmpApi();
        const renderMode = String(options.mode || state.snmpStatusMode || '').trim().toLowerCase();
        const renderDetailPage = options.renderDetailPage !== undefined ? !!options.renderDetailPage : renderMode === 'full';
        if (renderDetailPage && !(api && typeof api.renderSnmpCompactCard === 'function')) {
            runtimeCtx.ensureViewReady('snmp').then(() => renderSnmpCards(options, runtimeCtx)).catch(() => {});
            return;
        }
        const dashboardGrid = document.getElementById('dashboard-snmp-grid');
        const pageGrid = document.getElementById('snmp-page-grid');
        const statusCache = getNetworkStatusCache();
        const visibleConfigs = getNetworkMonitorConfigs(runtimeCtx);
        const normalizeName = api.normalizeSnmpDeviceName || ((cfg, status) => String((cfg && (cfg.name || cfg.id)) || status?.sys_name || '--'));
        visibleConfigs.sort((a, b) => {
            const sa = (statusCache[a.id] || {}).summary || {};
            const sb = (statusCache[b.id] || {}).summary || {};
            const riskRank = value => {
                const normalized = String(value || '').trim().toLowerCase();
                if (normalized === 'critical') return 0;
                if (normalized === 'warning') return 1;
                return 2;
            };
            const rankDiff = riskRank(sa.risk_level) - riskRank(sb.risk_level);
            if (rankDiff !== 0) return rankDiff;
            const scoreA = Number(sa.health_score ?? 100);
            const scoreB = Number(sb.health_score ?? 100);
            if (scoreA !== scoreB) return scoreA - scoreB;
            return normalizeName(a, statusCache[a.id] || {}).localeCompare(normalizeName(b, statusCache[b.id] || {}), 'zh-CN');
        });
        const filterConfigs = api.filterSnmpConfigs || ((configs) => configs);
        const filterMetaFn = api.getSnmpFilterMeta || (() => ({ label: '全部设备' }));
        const filteredConfigs = filterConfigs(visibleConfigs, statusCache, state.snmpCardFilter);
        const filterMeta = filterMetaFn(state.snmpCardFilter);
        const onlineCount = visibleConfigs.filter(cfg => runtimeCtx.getDeviceStatusMeta(statusCache[cfg.id] || {}).isOnlineLike).length;
        const criticalCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'critical').length;
        const warningCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'warning').length;
        const renderDashboardCard = api.renderDashboardSnmpCard || (() => '');
        const dashboardCardsHtml = filteredConfigs.length
            ? `<div class="snmp-dashboard-grid">${filteredConfigs.map(cfg => renderDashboardCard(cfg, statusCache[cfg.id] || {})).join('')}</div>`
            : `<div class="snmp-filter-empty"><strong>${runtimeCtx.escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片。</div>`;
        const dashboardHtml = visibleConfigs.length
            ? dashboardCardsHtml
            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
        if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
        if (pageGrid && renderDetailPage) {
            const pageOverviewHtml = api.renderSnmpOverviewBar ? api.renderSnmpOverviewBar(visibleConfigs, statusCache, state.snmpCardFilter) : '';
            const selectedConfig = state.snmpSelectedDeviceId
                ? visibleConfigs.find(cfg => String(cfg.id || '') === state.snmpSelectedDeviceId)
                : null;
            if (state.snmpSelectedDeviceId && !selectedConfig) {
                state.snmpSelectedDeviceId = '';
                syncSnmpSelectedDeviceToUrl('');
            }
            const pageCardsHtml = selectedConfig
                ? api.renderSnmpDeviceDetailPage(selectedConfig, statusCache[selectedConfig.id] || {})
                : (filteredConfigs.length
                    ? `<div class="snmp-device-grid snmp-onepage-grid">${filteredConfigs.map(cfg => {
                        const status = statusCache[cfg.id] || {};
                        const summary = status.summary || {};
                        const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
                        return api.renderSnmpCompactCard(cfg, status, summary, deviceType, summary.interface_summary || {}, { interactive: true });
                    }).join('')}</div>`
                    : `<div class="snmp-filter-empty"><strong>${runtimeCtx.escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片，可切换上方统计卡查看其他设备。</div>`);
            pageGrid.innerHTML = visibleConfigs.length
                ? `${pageOverviewHtml}${pageCardsHtml}`
                : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
        }
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.innerText = String(value);
        };
        setText('dash-snmp-online', onlineCount);
        setText('dash-snmp-total', visibleConfigs.length);
        setText('dash-snmp-critical', criticalCount);
        setText('dash-snmp-warning', warningCount);
        setText('dash-snmp-alert', criticalCount + warningCount);
        [dashboardGrid, renderDetailPage ? pageGrid : null].filter(Boolean).forEach(grid => {
            grid.querySelectorAll('[data-snmp-filter]').forEach(btn => {
                if (btn.dataset.snmpFilterBound === '1') return;
                btn.dataset.snmpFilterBound = '1';
                btn.addEventListener('click', () => {
                    const nextFilter = String(btn.getAttribute('data-snmp-filter') || 'all').trim().toLowerCase() || 'all';
                    state.snmpCardFilter = nextFilter === state.snmpCardFilter ? 'all' : nextFilter;
                    state.snmpSelectedDeviceId = '';
                    syncSnmpSelectedDeviceToUrl('');
                    renderSnmpCards(options, runtimeCtx);
                });
            });
            if (api.bindSnmpDetailToggles) api.bindSnmpDetailToggles(grid);
            bindSnmpOverviewCardActions(grid, runtimeCtx);
        });
    }

    function updateSnmpStatus(options = {}, ctx = null) {
        const runtimeCtx = getContext(ctx);
        const fetchJson = runtimeCtx.fetchJson;
        if (typeof fetchJson !== 'function') return Promise.resolve(null);
        const forceFull = !!options.full || runtimeCtx.getActiveViewId() === 'snmp';
        const mode = forceFull ? 'full' : 'compact';
        if (mode === 'full' && !(snmpApi() && typeof snmpApi().renderSnmpCompactCard === 'function')) {
            return runtimeCtx.ensureViewReady('snmp').then(() => updateSnmpStatus(options, runtimeCtx));
        }
        if (state.snmpFetchInFlight) {
            if (state.snmpFetchMode === mode || (mode === 'compact' && state.snmpFetchMode === 'full')) return state.snmpFetchInFlight;
            if (mode === 'full') return state.snmpFetchInFlight.then(() => updateSnmpStatus({ full: true }, runtimeCtx));
            return state.snmpFetchInFlight;
        }
        const nvrConfigs = Array.isArray(runtimeCtx.nvrConfigs) ? runtimeCtx.nvrConfigs : [];
        const snmpUrl = mode === 'full' ? '/api/snmp/status' : '/api/snmp/status?compact=1';
        const nvrUrl = mode === 'full' ? '/api/nvr/status' : '/api/nvr/status?compact=1';
        const safeRenderSnmpCards = () => runtimeCtx.guardFrontendStep(
            'snmp.render_cards',
            () => renderSnmpCards({ mode, renderDetailPage: mode === 'full' }, runtimeCtx),
            '网络监控卡片渲染异常，请稍后重试'
        );
        state.snmpFetchMode = mode;
        state.snmpFetchInFlight = Promise.allSettled([
            fetchJson(snmpUrl, {}, 'SNMP 状态读取失败'),
            nvrConfigs.length ? fetchJson(nvrUrl, {}, '录像机状态读取失败') : Promise.resolve({}),
        ])
            .then(results => {
                const [snmpResult, nvrResult] = results;
                const snmpFailed = snmpResult.status === 'rejected';
                const nvrFailed = nvrResult.status === 'rejected';
                if (snmpFailed && nvrFailed) {
                    throw snmpResult.reason || nvrResult.reason || new Error('网络监控状态读取失败');
                }
                if (snmpFailed) console.error('SNMP 状态更新失败', snmpResult.reason);
                if (nvrFailed) console.error('录像机状态更新失败', nvrResult.reason);
                const nextSnmpData = snmpResult.status === 'fulfilled' ? (snmpResult.value || {}) : (state.snmpStatusCache || {});
                const rawNvrData = nvrResult.status === 'fulfilled' ? (nvrResult.value || {}) : (state.nvrStatusCache || {});
                const nextNvrData = {};
                nvrConfigs.forEach(cfg => {
                    if (!cfg || !cfg.id) return;
                    nextNvrData[cfg.id] = normalizeNvrStatusForSnmp(cfg, rawNvrData[cfg.id] || {});
                });
                state.snmpStatusCache = nextSnmpData;
                state.nvrStatusCache = nextNvrData;
                const mergedData = getNetworkStatusCache();
                const nextSignature = `${mode}:${summarizeSnmpPayload(mergedData, runtimeCtx)}`;
                const shouldRender = nextSignature !== state.snmpStatusSignature;
                state.snmpLastSuccessAt = Date.now();
                state.snmpFetchFailureCount = 0;
                state.snmpStatusMode = mode;
                if (shouldRender) {
                    state.snmpStatusSignature = nextSignature;
                    const now = Date.now();
                    const elapsed = now - state.snmpLastRenderAt;
                    if (elapsed >= 300) {
                        state.snmpLastRenderAt = now;
                        safeRenderSnmpCards();
                    } else {
                        global.setTimeout(() => {
                            state.snmpLastRenderAt = Date.now();
                            safeRenderSnmpCards();
                        }, 300 - elapsed);
                    }
                }
            })
            .catch(err => {
                console.error('网络监控状态更新失败', err);
                state.snmpFetchFailureCount += 1;
                const now = Date.now();
                const hasCache = Object.keys(getNetworkStatusCache() || {}).length > 0;
                const cacheStillWarm = hasCache && state.snmpLastSuccessAt && (now - state.snmpLastSuccessAt) < 45000;
                const shouldToast = !cacheStillWarm && (!hasCache || state.snmpFetchFailureCount >= 2) && (now - state.snmpLastToastAt) > 15000;
                if (shouldToast) {
                    state.snmpLastToastAt = now;
                    runtimeCtx.showToast(runtimeCtx.translateApiError(err?.message, '网络监控状态读取失败，请稍后重试'), true);
                }
            })
            .finally(() => {
                state.snmpFetchInFlight = null;
                state.snmpFetchMode = '';
            });
        return state.snmpFetchInFlight;
    }

    const api = {
        getNetworkMonitorConfigs,
        getNetworkStatusCache,
        syncSnmpSelectedDeviceToUrl,
        restoreSnmpSelectedDeviceFromUrl,
        clearSnmpSelectedDevice,
        openSnmpDeviceDetail,
        closeSnmpDeviceDetail,
        bindSnmpOverviewCardActions,
        summarizeSnmpPayload,
        normalizeNvrStatusForSnmp,
        getNvrPreviewMode,
        getNvrPreviewGrid,
        getNvrPreviewChannels,
        applyNvrPreviewUrlParams,
        selectNvrPreview,
        setNvrPreviewMode,
        setNvrPreviewGrid,
        setNvrPreviewPage,
        stopNvrPreviewStreams,
        renderNvrPreviewPanel,
        buildNvrPreviewPanelHtml,
        renderSnmpCards,
        updateSnmpStatus,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.snmp_runtime', {
            kind: 'view-runtime',
            exports: Object.keys(api),
            source: 'static/js/views/snmp-runtime.js',
        });
    }
})(window);
