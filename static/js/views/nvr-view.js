(function installSmartCenterNvrView(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));
    const getDeviceStatusMeta = utils.getDeviceStatusMeta || global.getDeviceStatusMeta || ((status = {}) => ({
        chipClass: status.online ? 'online' : 'error',
        text: status.online ? '在线' : '离线',
    }));

    function getNvrPreviewMode(mode) {
        const value = String(mode || 'stream').trim().toLowerCase();
        return ['smart', 'stream', 'stream4', 'stream8', 'live', 'snapshot'].includes(value) ? value : 'smart';
    }

    function getNvrPreviewGrid(value) {
        const n = Number(value || 1);
        return [1, 4, 9, 16].includes(n) ? n : 1;
    }

    function buildNvrStreamUrl(cfg, channelId, options = {}) {
        const source = String(options.source || 'h264');
        const controls = options.controls ? '1' : '0';
        const wall = options.wall ? '1' : '0';
        const cacheBust = options.refresh ? `&_=${Date.now()}` : '';
        return `/api/nvr/player/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}/?source=${encodeURIComponent(source)}&autoplay=1&muted=1&controls=${controls}&wall=${wall}&fit=cover${cacheBust}`;
    }

    function buildNvrSnapshotUrl(cfg, channelId, stream, options = {}) {
        const cacheBust = options.refresh ? Date.now() : Math.floor(Date.now() / 10000);
        return `/api/nvr/snapshot/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}?stream=${encodeURIComponent(stream)}&_=${cacheBust}`;
    }

    function buildNvrFallbackUrl(cfg, channelId, stream, options = {}) {
        const cacheBust = options.refresh ? Date.now() : Math.floor(Date.now() / 10000);
        return `/api/nvr/live/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}?stream=${encodeURIComponent(stream)}&fps=${encodeURIComponent(String(options.fps || 5))}&width=${encodeURIComponent(String(options.width || 640))}&hw=auto&_=${cacheBust}`;
    }

    function getNvrPreviewModeLabel(previewMode, gridSize) {
        if (previewMode === 'smart') return gridSize > 1 ? '智能快照墙' : '单路低延迟';
        if (previewMode === 'stream') return '低延迟预览';
        if (previewMode === 'stream4') return '4路稳定直播';
        if (previewMode === 'stream8') return '8路实验直播';
        if (previewMode === 'live') return 'MJPEG备用';
        return '单张抓拍';
    }

    function buildNvrChannelButtons(cfg, channels = [], selectedChannelId = '') {
        return channels.slice(0, 64).map(item => {
            const channelId = String(item?.id || '').trim();
            const active = channelId === String(selectedChannelId);
            const online = !!item?.online;
            const name = item?.name || `D${channelId || '--'}`;
            const meta = [item?.ip, item?.detect_result || (online ? '在线' : '离线')].filter(Boolean).join(' · ') || (online ? '在线' : '离线');
            return `<button type="button" class="nvr-channel-btn ${online ? 'online' : 'offline'} ${active ? 'active' : ''}" onclick="selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(channelId)}', { refresh: true })">
                <span class="nvr-channel-dot"></span>
                <span>
                    <span class="nvr-channel-name">${escapeHtml(name)}</span>
                    <span class="nvr-channel-meta">${escapeHtml(meta)}</span>
                </span>
                <span class="nvr-channel-index">D${escapeHtml(channelId || '--')}</span>
            </button>`;
        }).join('');
    }

    function buildNvrWallFrameHtml(params) {
        const {
            cfg,
            wallChannels,
            stream,
            previewMode,
            effectiveMode,
            wallUsesSnapshots,
            isPagedStream,
            streamLimit,
            options,
        } = params;
        const cellHtml = wallChannels.map((item, index) => {
            const channelId = String(item?.id || '').trim();
            const name = item?.name || `D${channelId || '--'}`;
            const online = !!item?.online;
            const canStream = online && effectiveMode === 'stream' && (isPagedStream || index < streamLimit);
            const isLimited = online && effectiveMode === 'stream' && !isPagedStream && index >= streamLimit;
            const clickAction = `selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(channelId)}', { refresh: true, live: true })`;
            const snapshotUrl = buildNvrSnapshotUrl(cfg, channelId, stream, { refresh: true });
            const media = wallUsesSnapshots
                ? `<img src="${escapeHtml(snapshotUrl)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`
                : (previewMode === 'live'
                    ? `<img src="${escapeHtml(buildNvrFallbackUrl(cfg, channelId, stream, { refresh: options.refresh, fps: 3, width: 480 }))}" alt="${escapeHtml(name)}" loading="lazy" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`
                    : (canStream
                        ? `<iframe data-nvr-lazy="1" data-src="${escapeHtml(buildNvrStreamUrl(cfg, channelId, { refresh: options.refresh, source: 'h264', wall: isPagedStream }))}" title="${escapeHtml(name)}" allow="autoplay; fullscreen; encrypted-media" loading="lazy" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')"></iframe>`
                        : `<img src="${escapeHtml(snapshotUrl)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`));
            const statusText = !online ? '离线' : (wallUsesSnapshots ? '快照' : (effectiveMode === 'stream' ? (canStream ? '直播' : '占位') : (previewMode === 'live' ? 'MJPEG' : '抓拍')));
            return `<div class="nvr-wall-cell ${online ? 'online loading' : 'offline'} ${isLimited ? 'preview-limited' : ''}" onclick="${clickAction}">
                <div class="nvr-wall-label">D${escapeHtml(channelId || '--')} · ${escapeHtml(name)}</div>
                <div class="nvr-wall-status">${escapeHtml(statusText)}</div>
                ${media}
            </div>`;
        }).join('');
        return cellHtml;
    }

    function buildNvrSingleFrameHtml(params) {
        const { cfg, selected, stream, previewMode, effectiveMode, options, title } = params;
        const previewUrl = selected.id
            ? (effectiveMode === 'stream'
                ? buildNvrStreamUrl(cfg, selected.id, { refresh: options.refresh, controls: true, source: 'h264' })
                : (previewMode === 'live'
                    ? buildNvrFallbackUrl(cfg, selected.id, stream, { refresh: options.refresh, fps: 8, width: 960 })
                    : buildNvrSnapshotUrl(cfg, selected.id, stream, { refresh: options.refresh })))
            : '';
        return previewUrl
            ? `<div class="nvr-preview-frame ${effectiveMode === 'stream' ? 'stream' : (previewMode === 'live' ? 'live' : 'snapshot')} ${options.refresh ? 'loading' : ''}">
                ${effectiveMode === 'stream'
                    ? `<iframe src="${escapeHtml(previewUrl)}" title="${escapeHtml(title)}" allow="autoplay; fullscreen; encrypted-media" onload="this.closest('.nvr-preview-frame')?.classList.remove('loading')"></iframe>`
                    : `<img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(title)}" loading="eager" onload="this.closest('.nvr-preview-frame')?.classList.remove('loading')" onerror="this.closest('.nvr-preview-frame').innerHTML='<div class=&quot;nvr-preview-empty&quot;>${previewMode === 'live' ? 'MJPEG 备用连接失败，可切换抓拍备用。' : '抓拍失败，请稍后重试或换一路通道。'}</div>'">`}
            </div>`
            : '<div class="nvr-preview-frame"><div class="nvr-preview-empty">请选择一路通道预览。</div></div>';
    }

    function buildNvrPreviewPanelHtml(context = {}) {
        const cfg = context.cfg || {};
        const status = context.status || {};
        const channels = Array.isArray(context.channels) ? context.channels : [];
        const selected = context.selected || {};
        const options = context.options || {};
        const streamLimitConfig = Number(context.streamLimit || 8);
        const snapshotRefreshMs = Number(context.snapshotRefreshMs || 10000);
        const selectedChannelId = String(context.selectedChannelId || selected.id || '');
        const stream = String(cfg.live_stream || cfg.snapshot_stream || '2');
        const previewMode = getNvrPreviewMode(context.previewMode);
        const gridSize = previewMode === 'stream8' ? 8 : getNvrPreviewGrid(context.previewGrid);
        const onlineChannels = channels.filter(item => item && item.online);
        const selectedIndex = Math.max(0, channels.findIndex(item => String(item.id) === selectedChannelId));
        const wallSource = channels.slice(selectedIndex).concat(channels.slice(0, selectedIndex));
        const pageSource = onlineChannels.length ? wallSource.filter(item => item && item.online) : wallSource;
        const pageCount = Math.max(1, Math.ceil(pageSource.length / Math.max(1, gridSize)));
        const currentPage = Math.min(Math.max(0, Number(context.previewPage || 0)), pageCount - 1);
        const pageStart = currentPage * gridSize;
        const wallChannels = pageSource.slice(pageStart, pageStart + gridSize);
        const effectiveMode = previewMode === 'smart' && gridSize === 1 ? 'stream' : (previewMode === 'stream4' || previewMode === 'stream8' ? 'stream' : previewMode);
        const wallUsesSnapshots = gridSize > 1 && ['smart', 'snapshot'].includes(previewMode);
        const streamLimit = effectiveMode === 'stream' ? Math.min(gridSize, streamLimitConfig) : gridSize;
        const limitedCount = effectiveMode === 'stream' && gridSize > streamLimit ? gridSize - streamLimit : 0;
        const isPagedStream = ['stream4', 'stream8'].includes(previewMode);
        const statusMeta = getDeviceStatusMeta(status, { staleText: '关注', errorText: '异常' });
        const summary = status.summary || {};
        const modeLabel = getNvrPreviewModeLabel(previewMode, gridSize);
        const badges = [
            `<span class="nvr-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>`,
            `<span class="nvr-chip">通道 ${escapeHtml(String(summary.channel_online ?? 0))}/${escapeHtml(String(summary.channel_total ?? channels.length))}</span>`,
            `<span class="nvr-chip ${Number(summary.hdd_error_count || 0) > 0 ? 'error' : 'online'}">硬盘 ${escapeHtml(String(summary.hdd_ok_count ?? 0))}/${escapeHtml(String(summary.hdd_total ?? 0))}</span>`,
            `<span class="nvr-chip">${escapeHtml(modeLabel)}</span>`,
            `<span class="nvr-chip">${gridSize === 1 ? '单路' : `${gridSize}宫格`}</span>`,
            isPagedStream ? `<span class="nvr-chip online">第 ${currentPage + 1}/${pageCount} 页</span>` : '',
            wallUsesSnapshots ? `<span class="nvr-chip online">${snapshotRefreshMs / 1000}s 自动刷新</span>` : (limitedCount ? `<span class="nvr-chip warning">直播 ${streamLimit}/${gridSize} 路，余下抓拍占位</span>` : ''),
        ];
        const channelButtons = buildNvrChannelButtons(cfg, channels, selectedChannelId);
        const title = gridSize > 1
            ? `${cfg.name || cfg.id} · ${gridSize}宫格预览`
            : (selected.id ? `${selected.name || `D${selected.id}`} · D${selected.id}` : '选择一路监控');
        const frameHtml = gridSize > 1
            ? `<div class="nvr-wall-grid wall-${gridSize}">${buildNvrWallFrameHtml({ cfg, wallChannels, stream, previewMode, effectiveMode, wallUsesSnapshots, isPagedStream, streamLimit, options }) || '<div class="nvr-preview-empty">暂无可预览通道</div>'}</div>`
            : buildNvrSingleFrameHtml({ cfg, selected, stream, previewMode, effectiveMode, options, title });
        const html = `<div class="nvr-preview-layout">
            <div class="nvr-preview-stage">
                <div class="nvr-preview-head">
                    <div>
                        <div class="nvr-preview-title">${escapeHtml(title)}</div>
                        <div class="nvr-preview-subtitle">${escapeHtml(cfg.name || cfg.id)} · ${escapeHtml(cfg.host || '--')} · ${escapeHtml(status.device_info?.model || cfg.model || '--')}</div>
                    </div>
                    <div class="nvr-preview-tools">
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'smart' ? 'active' : ''}" onclick="setNvrPreviewMode('smart')" title="默认模式：16 路快照墙，低负载、适合长期打开">16路快照</button>
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream' ? 'active' : ''}" onclick="setNvrPreviewMode('stream')">低延迟</button>
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream4' ? 'active' : ''}" onclick="setNvrPreviewMode('stream4')" title="稳定模式：每页 4 路实时直播，可翻页查看 32 路">4路直播</button>
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream8' ? 'active' : ''}" onclick="setNvrPreviewMode('stream8')" title="实验模式：当前显卡/NVENC环境下可能只能稳定部分通道">8路实验</button>
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'live' ? 'active' : ''}" onclick="setNvrPreviewMode('live')">MJPEG备用</button>
                        <button type="button" class="nvr-preview-mode-btn ${previewMode === 'snapshot' ? 'active' : ''}" onclick="setNvrPreviewMode('snapshot')">抓拍备用</button>
                        ${[1, 4, 9, 16].map(size => `<button type="button" class="nvr-preview-mode-btn ${gridSize === size ? 'active' : ''}" onclick="setNvrPreviewGrid(${size})">${size === 1 ? '单路' : `${size}宫格`}</button>`).join('')}
                        ${isPagedStream ? `<button type="button" class="nvr-preview-btn" onclick="setNvrPreviewPage(-1)" ${currentPage <= 0 ? 'disabled' : ''}>上一页</button><button type="button" class="nvr-preview-btn" onclick="setNvrPreviewPage(1)" ${currentPage >= pageCount - 1 ? 'disabled' : ''}>下一页</button>` : ''}
                        <button type="button" class="nvr-preview-btn" onclick="selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(String(selected.id || ''))}', { refresh: true })">刷新</button>
                    </div>
                </div>
                <div class="nvr-preview-badges">${badges.join('')}</div>
                ${frameHtml}
            </div>
            <div class="nvr-channel-list">${channelButtons || '<div class="nvr-preview-empty">暂无通道清单</div>'}</div>
        </div>`;
        return {
            html,
            currentPage,
            pageCount,
            gridSize,
            previewMode,
            effectiveMode,
            wallUsesSnapshots,
            isPagedStream,
        };
    }

    const api = {
        getNvrPreviewMode,
        getNvrPreviewGrid,
        buildNvrStreamUrl,
        buildNvrSnapshotUrl,
        buildNvrFallbackUrl,
        getNvrPreviewModeLabel,
        buildNvrChannelButtons,
        buildNvrWallFrameHtml,
        buildNvrSingleFrameHtml,
        buildNvrPreviewPanelHtml,
    };

    SmartCenter.nvrView = Object.assign({}, SmartCenter.nvrView || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('nvr-view', {
            kind: 'view',
            view: 'camera_preview',
            exports: Object.keys(api),
            source: 'static/js/views/nvr-view.js',
        });
    }

    Object.assign(global, api);
})(window);
