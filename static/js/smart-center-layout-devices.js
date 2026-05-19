        function renderHyEdgeCards() {
            const summaryEl = document.getElementById('dashboard-hy-edge-summary');
            const grid = document.getElementById('dashboard-hy-edge-grid');
            if (!summaryEl || !grid) return;
            const payload = hyEdgeStatusCache || {};
            const summary = payload.summary || {};
            const cards = Array.isArray(payload.cards) ? payload.cards : [];
            const online = payload.online !== false && payload.enabled !== false && !payload.error;
            const stateChip = online
                ? '<span class="ups-chip online">边缘在线</span>'
                : `<span class="ups-chip error">边缘离线</span>`;
            summaryEl.innerHTML = `
                ${stateChip}
                <span class="ups-chip">在线 <strong>${escapeHtml(String(summary.online_count ?? 0))}</strong> / ${escapeHtml(String(summary.card_total ?? 0))}</span>
                <span class="ups-chip ${Number(summary.alert_count || 0) > 0 ? 'warning' : ''}">告警 <strong>${escapeHtml(String(summary.alert_count ?? 0))}</strong></span>
                <span class="ups-chip">响应 ${escapeHtml(String(summary.response_time_ms ?? '--'))} ms</span>
            `;
            if (payload.enabled === false) {
                grid.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">HY 异地机房监控已停用</div>';
                return;
            }
            if (!online && !cards.length) {
                grid.innerHTML = `<div style="color:var(--danger); grid-column:1/-1; text-align:center; padding:20px;">HY 边缘状态读取失败：${escapeHtml(payload.error || '未知错误')}</div>`;
                return;
            }
            grid.innerHTML = cards.map(card => {
                const hasAlerts = Array.isArray(card.alerts) && card.alerts.length > 0;
                const cardClass = `${card.online ? '' : 'offline'} ${hasAlerts ? 'warning' : ''}`.trim();
                const chips = (card.chips || []).map(chip => `<span class="ups-chip ${escapeHtml(chip.tone || '')}">${escapeHtml(chip.text || '--')}</span>`).join('');
                const metrics = (card.metrics || []).map(metric => `
                    <div class="hy-edge-metric ${escapeHtml(metric.level || '')}">
                        <div class="label">${escapeHtml(metric.label || '--')}</div>
                        <div class="value">${escapeHtml(metric.value || '--')}</div>
                    </div>
                `).join('');
                const alerts = hasAlerts
                    ? `<div class="hy-edge-alerts">${card.alerts.map(item => `<span class="ups-chip warning">${escapeHtml(item)}</span>`).join('')}</div>`
                    : '';
                return `<div class="hy-edge-card ${escapeHtml(cardClass)}">
                    <div class="hy-edge-head">
                        <div>
                            <div class="hy-edge-title">${escapeHtml(card.title || '--')}</div>
                            <div class="hy-edge-subtitle">${escapeHtml(card.subtitle || '--')}</div>
                        </div>
                        <div class="dashboard-mini-chip-row">${chips}</div>
                    </div>
                    <div class="hy-edge-metric-grid">${metrics}</div>
                    ${alerts}
                    <div class="hy-edge-note">${escapeHtml(card.note || '')}</div>
                </div>`;
            }).join('');
        }
        function updateHyEdgeStatus() {
            return fetchJson('/api/hy-edge/status', {}, 'HY 异地状态读取失败')
                .then(data => {
                    hyEdgeStatusCache = data || {};
                    renderHyEdgeCards();
                })
                .catch(err => {
                    console.error('HY 异地状态更新失败', err);
                    hyEdgeStatusCache = {
                        enabled: true,
                        online: false,
                        error: translateApiError(err?.message, 'HY 异地状态读取失败'),
                        summary: { online_count: 0, card_total: 0, alert_count: 0, response_time_ms: null, high_age_text: '--', low_age_text: '--' },
                        cards: []
                    };
                    renderHyEdgeCards();
                });
        }
        function applyAdaptiveDensity() {
            const width = window.innerWidth || document.documentElement.clientWidth || 0;
            const height = window.innerHeight || document.documentElement.clientHeight || 0;
            const params = new URLSearchParams(window.location.search);
            const forceTouchMode = params.get('force_touch') || '';
            const forceLayoutMode = String(params.get('force_layout') || params.get('layout') || '').toLowerCase();
            const useSavedLayout = params.get('use_saved_layout') === '1' || params.get('remember_layout') === '1';
            const coarsePointer = window.matchMedia ? window.matchMedia('(pointer: coarse)').matches : false;
            const touchPoints = Number(navigator.maxTouchPoints || 0);
            const ua = navigator.userAgent || '';
            const uaDataMobile = navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean'
                ? navigator.userAgentData.mobile
                : null;
            const uaLooksTouchOs = /Android|iPhone|iPad|iPod|HarmonyOS|Adr/i.test(ua);
            const uaLooksMobile = /Mobile|iPhone|iPad|iPod|Android|HarmonyOS|Adr/i.test(ua);
            const screenW = Number(window.screen?.width || 0);
            const screenH = Number(window.screen?.height || 0);
            const screenShort = Math.min(screenW, screenH);
            const screenLong = Math.max(screenW, screenH);
            const screenAspect = screenShort ? screenLong / screenShort : 9;
            const visualW = Number(window.visualViewport?.width || 0);
            const visualH = Number(window.visualViewport?.height || 0);
            const viewShort = Math.min(
                ...[width, height, visualW, visualH].filter(value => Number.isFinite(value) && value > 0)
            );
            const viewLong = Math.max(width, height, visualW, visualH, 0);
            const viewAspect = viewShort ? viewLong / viewShort : 9;
            const dpr = Math.max(1, Number(window.devicePixelRatio || 1));
            const physicalShort = Math.max(screenShort * dpr, viewShort * dpr);
            const physicalLong = Math.max(screenLong * dpr, viewLong * dpr);
            const viewportPreset = document.documentElement.dataset.viewportPreset || '';
            let isTouch = coarsePointer || touchPoints > 0;
            const isPortrait = height >= width;
            const aspect = width && height ? Math.max(width, height) / Math.max(1, Math.min(width, height)) : 1;
            let savedLayout = '';
            try { savedLayout = useSavedLayout ? (localStorage.getItem('smartCenterDashboardLayout') || '') : ''; } catch (_) {}
            const explicitDesktop = ['desktop', 'pc', 'wide'].includes(forceLayoutMode) || params.get('desktop') === '1' || savedLayout === 'desktop';
            const explicitTablet = ['tablet', 'pad', 'fold'].includes(forceLayoutMode) || params.get('tablet') === '1' || savedLayout === 'tablet';
            const explicitMobile = ['mobile', 'phone', 'outer'].includes(forceLayoutMode) || params.get('mobile') === '1' || savedLayout === 'mobile';
            const squareTouchScreen = Math.min(screenAspect, viewAspect) <= 1.62;
            const nearSquareViewport = viewShort >= 560 && viewLong >= 620 && viewAspect <= 1.62;
            const highDensityFoldScreen = squareTouchScreen && physicalShort >= 900 && physicalLong >= 1000;
            const autoTabletCandidate = isTouch && !explicitMobile && !explicitDesktop && (
                nearSquareViewport || highDensityFoldScreen || (viewShort >= 600 && viewLong >= 768 && viewAspect <= 1.75)
            );
            const browserDesktopSite = isTouch && !explicitMobile && !explicitTablet && !autoTabletCandidate && (
                viewportPreset === 'desktop-touch'
                || (!uaLooksTouchOs && (uaDataMobile === false || !uaLooksMobile))
                || (uaDataMobile === false && viewLong >= 960)
            );
            const desktopRequested = explicitDesktop || (!explicitTablet && !autoTabletCandidate && browserDesktopSite);
            const foldTabletScreen = isTouch && (nearSquareViewport || highDensityFoldScreen || autoTabletCandidate);
            let isFoldTablet = isTouch && width >= 700 && height >= 760 && (width >= 900 || height >= 1100 || aspect <= 1.45);
            if (foldTabletScreen) isFoldTablet = true;
            let isTablet = isTouch && !desktopRequested && (explicitTablet || autoTabletCandidate || isFoldTablet || (width >= 768 && viewShort >= 600));
            let isMobile = isTouch && !desktopRequested && !isTablet && (width <= 760 || isPortrait || uaLooksMobile || uaDataMobile === true);
            let isTouchWide = isTouch && !desktopRequested && !isMobile && !isTablet && width >= 700 && width <= 1400;
            let isTouchPortrait = isTouch && isPortrait;
            let isFoldDesktop = isTouch && desktopRequested && !isMobile;
            const forcedTouch = String(forceTouchMode || '').toLowerCase();
            if (['wide', 'tablet', 'fold', 'touch-wide'].includes(forcedTouch)) {
                isTouch = true;
                isFoldTablet = true;
                isMobile = false;
                isFoldDesktop = ['desktop', 'pc'].includes(forceLayoutMode);
                isTouchWide = !isFoldDesktop;
                isTouchPortrait = isPortrait;
            } else if (['mobile', 'phone', 'outer', 'portrait'].includes(forcedTouch)) {
                isTouch = true;
                isFoldTablet = false;
                isMobile = true;
                isTouchWide = false;
                isTouchPortrait = true;
                isFoldDesktop = false;
            }
            if (explicitDesktop) {
                isMobile = false;
                isFoldTablet = isTouch;
                isFoldDesktop = isTouch;
                isTouchWide = false;
                isTouchPortrait = false;
            } else if (explicitMobile) {
                isTouch = true;
                isMobile = true;
                isTablet = false;
                isFoldTablet = false;
                isFoldDesktop = false;
                isTouchWide = false;
                isTouchPortrait = true;
            } else if (explicitTablet) {
                isTouch = true;
                isTablet = true;
                isMobile = false;
                isFoldTablet = true;
                isFoldDesktop = false;
                isTouchWide = false;
                isTouchPortrait = false;
            } else if (browserDesktopSite) {
                isMobile = false;
                isTablet = false;
                isFoldTablet = isTouch;
                isFoldDesktop = isTouch;
                isTouchWide = false;
                isTouchPortrait = false;
            }
            if (isFoldDesktop) {
                isMobile = false;
                isTablet = false;
                isTouchWide = false;
                isTouchPortrait = false;
            }
            if (isMobile || isTouchWide || isTablet) closeSidebar();
            const dense = !isMobile && !isTablet && !isTouchWide && !isFoldDesktop && (width <= 980 || height <= 720);
            const compact = !isMobile && !isTablet && !isTouchWide && !isFoldDesktop && !dense && (width <= 1366 || height <= 860);
            document.body.classList.toggle('dense-layout', dense);
            document.body.classList.toggle('compact-layout', dense || compact || isFoldDesktop);
            document.body.classList.toggle('mobile-layout', isMobile);
            document.body.classList.toggle('tablet-layout', isTablet);
            document.body.classList.toggle('touch-layout', isTouch);
            document.body.classList.toggle('touch-wide-layout', isTouchWide);
            document.body.classList.toggle('touch-portrait-layout', isTouchPortrait);
            document.body.classList.toggle('fold-desktop-layout', isFoldDesktop);
            applyDashboardBrowserFit({
                width,
                height,
                visualW,
                visualH,
                isMobile,
                isTablet,
                isTouchWide,
                isTouchPortrait,
                isFoldDesktop,
                forceLayoutMode,
                desktopRequested,
                explicitDesktop,
                explicitTablet,
                browserDesktopSite
            });
            updateLayoutDebugPanel({
                width,
                height,
                visualW,
                visualH,
                screenW,
                screenH,
                dpr,
                physicalShort,
                physicalLong,
                coarsePointer,
                touchPoints,
                uaDataMobile,
                uaLooksTouchOs,
                uaLooksMobile,
                viewportPreset,
                forceLayoutMode,
                forceTouchMode,
                desktopRequested,
                explicitDesktop,
                explicitTablet,
                browserDesktopSite,
                mode: isMobile ? 'mobile' : (isTablet ? 'tablet' : (isFoldDesktop ? 'fold-desktop' : (isTouchWide ? 'touch-wide' : (isTouch ? 'touch' : 'desktop')))),
                classes: document.body.className,
                fixedCanvas: document.documentElement.classList.contains('dashboard-fixed-canvas'),
                fitScale: getComputedStyle(document.documentElement).getPropertyValue('--dashboard-fit-scale').trim() || '-'
            });
        }
        function updateLayoutDebugPanel(info) {
            const params = new URLSearchParams(window.location.search);
            const enabled = ['1', 'true', 'yes'].includes(String(params.get('layout_debug') || params.get('debug_layout') || '').toLowerCase());
            let panel = document.getElementById('layout-debug-panel');
            if (!enabled) {
                if (panel) panel.remove();
                return;
            }
            if (!panel) {
                panel = document.createElement('div');
                panel.id = 'layout-debug-panel';
                panel.className = 'layout-debug-panel';
                document.body.appendChild(panel);
            }
            panel.textContent = [
                `mode=${info.mode}`,
                `inner=${info.width}x${info.height} visual=${Math.round(info.visualW || 0)}x${Math.round(info.visualH || 0)} dpr=${Number(info.dpr).toFixed(2)}`,
                `screen=${info.screenW}x${info.screenH}`,
                `physical=${Math.round(info.physicalShort || 0)}x${Math.round(info.physicalLong || 0)}`,
                `touch=${info.touchPoints} coarse=${info.coarsePointer}`,
                `uaMobile=${info.uaDataMobile} touchOS=${info.uaLooksTouchOs} uaLooksMobile=${info.uaLooksMobile}`,
                `preset=${info.viewportPreset || '-'} force=${info.forceLayoutMode || '-'} touch=${info.forceTouchMode || '-'}`,
                `desktopReq=${info.desktopRequested ? '1' : '0'} explicit=${info.explicitDesktop ? '1' : '0'} tablet=${info.explicitTablet ? '1' : '0'} browserDesktop=${info.browserDesktopSite ? '1' : '0'}`,
                `fixedCanvas=${info.fixedCanvas ? '1' : '0'} scale=${info.fitScale || '-'}`,
                `classes=${info.classes || '-'}`
            ].join('\n');
        }
        function applyDashboardBrowserFit(info = {}) {
            const root = document.documentElement;
            const params = new URLSearchParams(window.location.search);
            const disabled = ['0', 'false', 'off', 'none'].includes(String(params.get('fit_dashboard') || '').toLowerCase());
            const useSavedLayout = params.get('use_saved_layout') === '1' || params.get('remember_layout') === '1';
            const activeView = getActiveViewId();
            const width = Number(info.width || window.innerWidth || document.documentElement.clientWidth || 0);
            const height = Number(info.height || window.innerHeight || document.documentElement.clientHeight || 0);
            const visualW = Number(info.visualW || window.visualViewport?.width || width || 0);
            const visualH = Number(info.visualH || window.visualViewport?.height || height || 0);
            const fitW = Math.max(1, Math.min(width || visualW, visualW || width));
            const fitH = Math.max(1, Math.min(height || visualH, visualH || height));
            const baseW = 1920;
            const baseH = 1080;
            const mobileMode = typeof info.isMobile === 'boolean' ? info.isMobile : document.body.classList.contains('mobile-layout');
            const tabletMode = typeof info.isTablet === 'boolean' ? info.isTablet : document.body.classList.contains('tablet-layout');
            const touchWideMode = typeof info.isTouchWide === 'boolean' ? info.isTouchWide : document.body.classList.contains('touch-wide-layout');
            const touchPortraitMode = typeof info.isTouchPortrait === 'boolean' ? info.isTouchPortrait : document.body.classList.contains('touch-portrait-layout');
            const coarsePointer = window.matchMedia ? window.matchMedia('(pointer: coarse)').matches : false;
            const touchPoints = Number(navigator.maxTouchPoints || 0);
            const isTouch = coarsePointer || touchPoints > 0;
            const ua = navigator.userAgent || '';
            const uaDataMobile = navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean'
                ? navigator.userAgentData.mobile
                : null;
            const uaLooksTouchOs = /Android|iPhone|iPad|iPod|HarmonyOS|Adr/i.test(ua);
            const uaLooksMobile = /Mobile|iPhone|iPad|iPod|Android|HarmonyOS|Adr/i.test(ua);
            const forceMode = String(info.forceLayoutMode || '').toLowerCase();
            let savedLayout = '';
            try { savedLayout = useSavedLayout ? (localStorage.getItem('smartCenterDashboardLayout') || '') : ''; } catch (_) {}
            const forcedMobile = ['mobile', 'phone', 'outer'].includes(forceMode) || params.get('mobile') === '1' || savedLayout === 'mobile' || mobileMode;
            const tabletRequested = ['tablet', 'pad', 'fold'].includes(forceMode) || params.get('tablet') === '1' || info.explicitTablet === true || savedLayout === 'tablet' || tabletMode;
            const forcedDesktop = !forcedMobile && !tabletRequested && (
                ['desktop', 'pc', 'wide'].includes(forceMode) || params.get('desktop') === '1' || info.explicitDesktop === true || savedLayout === 'desktop'
            );
            const browserDesktopSite = !forcedMobile && !tabletRequested && (info.browserDesktopSite === true || (
                isTouch
                && !['mobile', 'phone', 'outer'].includes(forceMode)
                && (
                    document.documentElement.dataset.viewportPreset === 'desktop-touch'
                    || (!uaLooksTouchOs && (uaDataMobile === false || !uaLooksMobile))
                    || (uaDataMobile === false && Math.max(width, height, visualW, visualH) >= 960)
                )
            ));
            const desktopCanvasRequested = forcedDesktop || browserDesktopSite;
            const desktopLike = desktopCanvasRequested || (!mobileMode && !tabletMode && !touchWideMode && !touchPortraitMode && !coarsePointer);
            const directDesktop = desktopLike && !['mobile', 'phone', 'outer'].includes(forceMode)
                && (desktopCanvasRequested || (width >= 1181 && fitW >= 1181));
            const shouldFit = !disabled && activeView === 'dashboard' && directDesktop;
            if (!shouldFit) {
                root.classList.remove('dashboard-browser-fit', 'dashboard-fixed-canvas', 'dashboard-fixed-canvas-locked');
                root.style.removeProperty('--dashboard-fit-scale');
                root.style.removeProperty('--dashboard-fit-base-width');
                root.style.removeProperty('--dashboard-fit-base-height');
                root.style.removeProperty('--dashboard-fit-offset-x');
                root.style.removeProperty('--dashboard-fit-offset-y');
                return;
            }
            const scale = Math.max(0.1, Math.min(fitW / baseW, fitH / baseH));
            const offsetX = Math.max(0, (fitW - baseW * scale) / 2);
            const offsetY = Math.max(0, (fitH - baseH * scale) / 2);
            root.classList.remove('dashboard-browser-fit');
            root.classList.add('dashboard-fixed-canvas', 'dashboard-fixed-canvas-locked');
            root.style.setProperty('--dashboard-fit-scale', scale.toFixed(5));
            root.style.setProperty('--dashboard-fit-base-width', `${baseW}px`);
            root.style.setProperty('--dashboard-fit-base-height', `${baseH}px`);
            root.style.setProperty('--dashboard-fit-offset-x', `${offsetX.toFixed(2)}px`);
            root.style.setProperty('--dashboard-fit-offset-y', `${offsetY.toFixed(2)}px`);
        }
        function syncDashboardCompactMode(viewId = getActiveViewId()) {
            document.body.classList.toggle('dashboard-compact-mode', viewId === 'dashboard');
            applyDashboardBrowserFit();
            scheduleDashboardMasonry();
        }
        function syncCurrentViewToUrl(viewId) {
            const safeView = String(viewId || '').replace(/[^a-zA-Z0-9_-]/g, '');
            if (!safeView) return;
            try {
                const url = new URL(window.location.href);
                if (url.searchParams.get('view') !== safeView) {
                    url.searchParams.set('view', safeView);
                    window.history.replaceState(null, '', url.toString());
                }
                if (window.parent && window.parent !== window) {
                    window.parent.postMessage({
                        source: 'smart-center',
                        type: 'view-change',
                        view: safeView,
                        href: url.toString()
                    }, '*');
                }
            } catch (_) {}
        }
        function toggleSidebar(forceOpen = null) {
            const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !document.body.classList.contains('sidebar-open');
            document.body.classList.toggle('sidebar-open', shouldOpen);
        }
        function closeSidebar() { document.body.classList.remove('sidebar-open'); }
        function switchTab(viewId, title, navEl) {
            const previousView = getActiveViewId();
            if (previousView === 'camera_preview' && viewId !== 'camera_preview') stopNvrPreviewStreams();
            if (viewId !== 'snmp' && snmpSelectedDeviceId) {
                snmpSelectedDeviceId = '';
                syncSnmpSelectedDeviceToUrl('');
            }
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            const targetView = document.getElementById('view-' + viewId);
            if (targetView) targetView.classList.add('active');
            document.querySelectorAll('.nav-menu li').forEach(el => el.classList.remove('active'));
            if (navEl) navEl.classList.add('active');
            document.getElementById('header-title').innerText = title;
            syncDashboardCompactMode(viewId);
            syncCurrentViewToUrl(viewId);
            if (window.innerWidth <= 760) closeSidebar();
            if (viewId !== 'door') stopDoorVideoStream();
            if (viewId === 'power') setTimeout(() => { resizePowerCharts(); updatePowerData(); }, 120);
            if (viewId === 'meter') setTimeout(() => { updateMeterCenter(); }, 80);
            if (viewId === 'ups') setTimeout(() => { updateUpsStatus(); }, 80);
            if (viewId === 'snmp') setTimeout(() => { updateSnmpStatus({ full: true }); }, 80);
            if (viewId === 'proxy') setTimeout(() => { updateProxyStatus(); }, 80);
            if (viewId === 'auto') setTimeout(() => { loadAutomationStatus(true); loadAutomationLogs(); }, 80);
            if (viewId === 'camera_preview') {
                setTimeout(() => {
                    applyNvrPreviewUrlParams();
                    updateSnmpStatus({ full: true }).finally(() => renderNvrPreviewPanel({ refresh: true }));
                }, 80);
            }
            if (viewId === 'hvac') setTimeout(() => { updateHvacStatus(true); updateEnvData(); }, 80);
            if (viewId === 'door') setTimeout(() => { initCanvas(); updateDoorStatus(true).finally(() => startDoorVideoStream()); }, 100);
            if (viewId === 'sequencer') setTimeout(() => { updateSequencerStatus(); }, 80);
            if (viewId === 'apple_audio') setTimeout(() => { initAppleAudioDemo(); }, 60);
            refreshPollingVisibility();
        }
        function formatGlobalTime(now = new Date()) {
            const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
            const pad = value => String(value).padStart(2, '0');
            return {
                clock: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
                date: `${now.getFullYear()}年${pad(now.getMonth() + 1)}月${pad(now.getDate())}日 ${weekdays[now.getDay()]}`
            };
        }
        function updateGlobalClock() {
            const formatted = formatGlobalTime(new Date());
            const clockEl = document.getElementById("global-time-clock");
            const dateEl = document.getElementById("global-time-date");
            const timeEl = document.getElementById("global-time");
            if (clockEl && dateEl) {
                clockEl.innerText = formatted.clock;
                dateEl.innerText = formatted.date;
            } else if (timeEl) {
                timeEl.innerText = `${formatted.date} ${formatted.clock}`;
            }
            updateDeployModalInfo();
        }
        function getSequencerOnlineClass(device) {
            return device && device.online ? 'online' : 'offline';
        }
        function renderSequencerCard(device) {
            const channels = Array.isArray(device.channels) ? device.channels : [];
            const commMode = String(device.comm_mode || 'TCP').toUpperCase();
            const connectionText = commMode === 'COM'
                ? `${device.baudrate || 19200} / ${device.data_bits || 8}${String(device.parity || 'N').slice(0,1)}${device.stop_bits || 1}`
                : `${device.ip || '--'}:${device.port || '--'}`;
            const sequencerLogs = Array.isArray(device.logs) ? device.logs.slice(0, 6) : [];
            const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
            const lastSuccessText = device.last_success_at ? new Date(device.last_success_at).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
            const currentStatusText = device.online
                ? `${device.mode || '时序模式'} / ${device.startup_mode || '手动'} / ${device.last_action || '待机'}`
                : `${device.last_action || '离线'}${device.error_display ? ' / ' + device.error_display : ''}`;
            const shortErrorText = device.error_display ? String(device.error_display).split(/[，,。]/)[0] : '';
            const channelHtml = channels.filter(ch => ch.visible !== false).map(ch => `
                <button class="sequencer-channel-btn ${ch.state ? 'on' : 'off'}${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                    <span class="sequencer-inline-led ${ch.state ? 'on' : ''}"></span>
                    <span class="name">${escapeHtml(ch.name || ('CH' + ch.channel))}</span>
                    <span class="state">${ch.state ? '已开启' : '已关闭'}</span>
                </button>
            `).join('');
            const logHtml = sequencerLogs.length ? sequencerLogs.map(log => {
                const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
                const message = escapeHtml(String(log.operation || '').replace(/\[.*?\]\s*/, '') || '未命名记录');
                return `<div class="sequencer-mini-log-item"><span class="sequencer-mini-log-time">[${timeText}]</span><span class="sequencer-mini-log-text">${message}</span></div>`;
            }).join('') : '<div style="color:var(--text-sub); font-size:12px;">暂无时序电源日志</div>';
            return `<div class="sequencer-card ${getSequencerOnlineClass(device)}">
                <div class="sequencer-head">
                    <div>
                        <div class="card-head-kicker">Sequencer Control</div>
                        <div class="sequencer-title">${escapeHtml(device.name || device.id)}</div>
                        <div class="sequencer-subtitle">地址 ${escapeHtml(String(device.address ?? 1))} / ${escapeHtml(device.protocol || 'DGH 8路时序器')} / ${escapeHtml(device.brand || 'DGH')}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="sequencer-tag ${device.online ? 'online' : ''}">${device.online ? '在线' : '离线'}</span>
                        <span class="sequencer-tag ${device.locked ? 'locked' : ''}">${device.locked ? '已锁定' : '未锁定'}</span>
                        ${(!device.online && shortErrorText) ? `<span class="sequencer-tag error">${escapeHtml(shortErrorText)}</span>` : ''}
                    </div>
                </div>
                <div class="sequencer-summary-text">通道状态摘要: ${escapeHtml(device.channel_summary || '无通道状态')}</div>
                <div class="sequencer-meta">
                    <div class="sequencer-meta-item"><div class="label">接入方式</div><div class="value">${escapeHtml(commMode)}</div></div>
                    <div class="sequencer-meta-item"><div class="label">${commMode === 'COM' ? '串口参数' : '网络地址'}</div><div class="value">${escapeHtml(String(connectionText))}</div></div>
                    <div class="sequencer-meta-item"><div class="label">当前状态</div><div class="value">${escapeHtml(currentStatusText)}</div></div>
                    <div class="sequencer-meta-item log"><div class="label">最近操作</div><div class="sequencer-mini-log-list">${logHtml}</div></div>
                </div>
                <div class="sequencer-toolbar">
                    <button class="sequencer-action-btn seq-on${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_on')">顺序开启</button>
                    <button class="sequencer-action-btn seq-off${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_off')">顺序关闭</button>
                    <button class="sequencer-action-btn all-on${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_on')">全部开启</button>
                    <button class="sequencer-action-btn all-off${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_off')">全部关闭</button>
                    <button class="sequencer-action-btn lock${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_lock')">${device.locked ? '解除锁定' : '锁定设备'}</button>
                </div>
                <div class="sequencer-channel-grid">${channelHtml || '<div style="grid-column:1/-1;color:var(--text-sub);">未配置通道</div>'}</div>
                <div class="sequencer-diagnostics">
                    <div class="sequencer-diag-item">
                        <div class="label">最后轮询</div>
                        <div class="value">${escapeHtml(updatedAtText)}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后成功通讯</div>
                        <div class="value">${escapeHtml(lastSuccessText)}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后指令</div>
                        <div class="value">${escapeHtml(device.last_command_hex || '--')}</div>
                    </div>
                    <div class="sequencer-diag-item">
                        <div class="label">最后回包</div>
                        <div class="value">${escapeHtml(device.last_response_hex || '--')}</div>
                    </div>
                </div>
                ${device.error ? `<div class="card-inline-note error">通讯异常：${escapeHtml(device.error)}</div>` : ''}
            </div>`;
        }
        function renderCompactSequencerCard(device) {
            const visibleChannels = Array.isArray(device?.channels) ? device.channels.filter(ch => ch && ch.visible !== false).slice(0, 8) : [];
            const canControlChannels = hasPermission('sequencer.control');
            const channelHtml = visibleChannels.map(ch => {
                const title = canControlChannels
                    ? `${ch.name || ('CH' + ch.channel)} · 点击切换`
                    : '当前账号无时序电源控制权限';
                return `
                <button type="button" class="dashboard-sequencer-channel ${ch.state ? 'on' : 'off'}${canControlChannels ? '' : ' is-disabled'}" ${canControlChannels ? '' : 'disabled'} title="${escapeHtml(title)}" onclick="fireSequencerAction('${escapeHtml(device.id)}', 'toggle_channel', ${Number(ch.channel)})">
                    <span class="dashboard-sequencer-channel-index">${escapeHtml(String(ch.channel || '--'))}</span>
                    <span class="dashboard-sequencer-channel-led"></span>
                    <span class="dashboard-sequencer-channel-state">${ch.state ? '开' : '关'}</span>
                </button>`;
            }).join('');
            const updatedAtText = device.updated_at ? new Date(device.updated_at).toLocaleTimeString('zh-CN', { hour12:false }) : '--:--:--';
            const actionText = device.last_action || (device.online ? '待机' : '离线');
            const modeText = device.startup_mode || device.mode || '手动';
            const summaryText = device.channel_summary || `${visibleChannels.filter(ch => ch.state).length}/${visibleChannels.length || 0} 路开启`;
            return `<div class="dashboard-sequencer-panel ${device && device.online ? '' : 'offline'}">
                <div class="dashboard-sequencer-device">
                    <div class="dashboard-sequencer-title-row">
                        <div class="dashboard-sequencer-name">${escapeHtml(device.name || device.id)}</div>
                    </div>
                    <div class="dashboard-sequencer-meta">
                        <span class="ups-chip ${device && device.online ? 'online' : 'error'}">${device && device.online ? '在线' : '离线'}</span>
                        <span class="ups-chip ${device && device.locked ? 'warning' : ''}">${device && device.locked ? '锁定' : '可控'}</span>
                        <span>${escapeHtml(modeText)}</span>
                        <span class="dot"></span>
                        <span>${escapeHtml(actionText)}</span>
                        <span class="dot"></span>
                        <span>${escapeHtml(compactSnmpText(summaryText, 14))}</span>
                    </div>
                </div>
                <div class="dashboard-sequencer-strip">${channelHtml || '<div class="dashboard-sequencer-empty" style="grid-column:1/-1;">未配置通道</div>'}</div>
                <div class="dashboard-sequencer-actions">
                    <button class="dashboard-mini-btn success${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_on')">顺开</button>
                    <button class="dashboard-mini-btn danger${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'sequence_off')">顺关</button>
                    <button class="dashboard-mini-btn secondary${getPermissionDisabledClass('sequencer.control')}" ${getPermissionDisabledAttrs('sequencer.control', '当前账号无时序电源控制权限')} onclick="fireSequencerAction('${escapeHtml(device.id)}', 'all_off')">全关</button>
                    <span class="dashboard-mini-note">更新 ${escapeHtml(updatedAtText)}</span>
                </div>
            </div>`;
        }
        function getSortedSequencerDevices() {
            const devices = Array.isArray(sequencerStatusCache.devices) ? [...sequencerStatusCache.devices] : [];
            return devices.sort((a, b) => {
                const sortDiff = (Number(a.sort_order || 999) - Number(b.sort_order || 999));
                if (sortDiff !== 0) return sortDiff;
                const nameA = String(a.name || a.id || '').toLowerCase();
                const nameB = String(b.name || b.id || '').toLowerCase();
                const nameDiff = nameA.localeCompare(nameB, 'zh-CN');
                if (nameDiff !== 0) return nameDiff;
                return String(a.ip || '').localeCompare(String(b.ip || ''), 'zh-CN');
            });
        }
        function filterSequencerDevices(devices, mode) {
            if (mode === 'online') return devices.filter(item => item.online);
            if (mode === 'offline') return devices.filter(item => !item.online || !!item.error_display);
            return devices;
        }
        function setSequencerFilter(mode, scope='dashboard') {
            sequencerFilters[scope] = mode;
            const wrapId = scope === 'dashboard' ? 'dashboard-sequencer-filters' : 'page-sequencer-filters';
            const wrap = document.getElementById(wrapId);
            if (wrap) {
                wrap.querySelectorAll('.sequencer-filter-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.textContent.includes(mode === 'all' ? '全部' : mode === 'online' ? '在线' : '离线/异常'));
                });
            }
            renderSequencerCards();
        }
        function renderSequencerCards() {
            const devices = getSortedSequencerDevices();
            const dashboardGrid = document.getElementById('dashboard-sequencer-grid');
            const pageGrid = document.getElementById('sequencer-page-grid');
            const dashboardDevices = filterSequencerDevices(devices, sequencerFilters.dashboard);
            const pageDevices = filterSequencerDevices(devices, sequencerFilters.page);
            const dashboardHtml = dashboardDevices.length ? dashboardDevices.map(renderCompactSequencerCard).join('') : '<div class="dashboard-sequencer-empty">当前筛选条件下暂无时序电源设备</div>';
            const pageHtml = pageDevices.length ? pageDevices.map(renderSequencerCard).join('') : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">当前筛选条件下暂无时序电源设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid) pageGrid.innerHTML = pageHtml;
            const totalEl = document.getElementById('dash-sequencer-total');
            const onlineEl = document.getElementById('dash-sequencer-online');
            if (totalEl) totalEl.innerText = devices.length;
            if (onlineEl) onlineEl.innerText = devices.filter(item => item.online).length;
        }
        function updateSequencerStatus() {
            fetch('/api/sequencer/status')
                .then(r => r.json())
                .then(data => {
                    sequencerStatusCache = data || {};
                    renderSequencerCards();
                })
                .catch(err => console.error('时序电源状态更新失败', err));
        }
        function fireSequencerAction(id, action, channel = null) {
            if (!ensurePermission('sequencer.control', '操作时序电源')) return;
            showToast('时序电源指令下发中...', false);
            fetch('/api/sequencer/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, action, channel })
            }).then(r => r.json()).then(data => {
                if (!data.success) {
                    showToast(data.message || '执行失败', true);
                    return;
                }
                showToast(`执行成功${data.command ? ' - ' + data.command : ''}`);
                setTimeout(() => { updateSequencerStatus(); updateDashboardLogs(); }, 120);
            }).catch(() => showToast('网络请求失败', true));
        }
        function applyDashboardSectionOrder() {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard) return;
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.sort((a, b) => {
                const sa = dashboardSectionConfig[a.dataset.sectionId] || {};
                const sb = dashboardSectionConfig[b.dataset.sectionId] || {};
                return Number(sa.sort || 999) - Number(sb.sort || 999);
            }).forEach(section => dashboard.appendChild(section));
            sections.forEach(section => {
                const meta = dashboardSectionConfig[section.dataset.sectionId] || {};
                section.style.display = meta.visible === false ? 'none' : '';
            });
        }
        let dashboardMasonryTimer = 0;
        let dashboardMasonryObserver = null;
        let dashboardResizeObserver = null;
        function applyDashboardMasonry() {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard || getActiveViewId() !== 'dashboard') return;
            // Keep the monitoring wall deterministic across browsers: no masonry reflow.
            document.body.classList.remove('dashboard-masonry-mode');
            const sections = Array.from(dashboard.querySelectorAll('[data-section-id]'));
            sections.forEach(section => { section.style.gridRowEnd = ''; });
        }
        function scheduleDashboardMasonry(delay = 80) {
            window.clearTimeout(dashboardMasonryTimer);
            dashboardMasonryTimer = window.setTimeout(() => applyDashboardMasonry(), delay);
        }
        function initDashboardMasonryObservers() {
            applyDashboardMasonry();
        }
        function formatHvacTemperature(value) {
            const num = Number(value);
            return Number.isFinite(num) ? `${num}°C` : '--';
        }
        function formatHvacPower(status) {
            const watt = Number(status?.electric_power_w);
            if (Number.isFinite(watt)) {
                if (Math.abs(watt) >= 1000) return `${(watt / 1000).toFixed(2)} kW`;
                return `${watt.toFixed(watt >= 100 ? 0 : 2)} W`;
            }
            const kw = Number(status?.electric_power_kw);
            if (Number.isFinite(kw)) return `${kw.toFixed(3)} kW`;
            return '--';
        }
        function getHvacModeText(mode) {
            const map = {
                off: '关闭',
                cool: '制冷',
                heat: '制热',
                dry: '除湿',
                fan_only: '送风',
                auto: '自动',
                heat_cool: '自动冷热'
            };
            const key = String(mode || '').trim().toLowerCase();
            return map[key] || (mode ? String(mode) : '--');
        }
        function getHvacActionText(action) {
            const map = {
                cooling: '制冷中',
                heating: '制热中',
                drying: '除湿中',
                fan: '送风中',
                idle: '待机',
                off: '已关闭'
            };
            const key = String(action || '').trim().toLowerCase();
            return map[key] || (action ? String(action) : '--');
        }
        function getHvacModeClass(mode) {
            const key = String(mode || '').trim().toLowerCase();
            if (key === 'cool') return 'cool';
            if (key === 'heat') return 'heat';
            if (key === 'dry') return 'dry';
            if (key === 'fan_only' || key === 'fan') return 'fan';
            if (key === 'auto' || key === 'heat_cool') return 'auto';
            if (key === 'off') return 'off';
            return '';
        }
        function getHvacCardStateClass(status) {
            if (!status?.online) return 'offline';
            return status?.power ? 'running' : 'standby';
        }
        function getHvacActionClass(status) {
            if (!status?.online) return 'idle';
            const action = String(status?.hvac_action || '').trim().toLowerCase();
            if (action === 'cooling') return 'cooling';
            if (action === 'heating') return 'heating';
            if (status?.power) return 'running';
            return 'idle';
        }
        function getHvacPowerButtonClass(status) {
            if (!status?.online) return 'unknown';
            return status?.power ? 'on' : 'off';
        }
        function getHvacModeIcon(kind) {
            const key = String(kind || '').trim().toLowerCase();
            if (key === 'cool') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 2.8v18.4M5.2 6.2l13.6 11.6M18.8 6.2L5.2 17.8" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
                    <path d="M12 2.8l2 3.1M12 2.8l-2 3.1M12 21.2l2-3.1M12 21.2l-2-3.1M5.2 6.2l3.6.7M5.2 6.2l.9 3.4M18.8 6.2l-3.6.7M18.8 6.2l-.9 3.4M5.2 17.8l3.6-.7M5.2 17.8l.9-3.4M18.8 17.8l-3.6-.7M18.8 17.8l-.9-3.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>`;
            }
            if (key === 'heat') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="4.4" stroke="currentColor" stroke-width="1.9"/>
                    <path d="M12 2.7v3.1M12 18.2v3.1M21.3 12h-3.1M5.8 12H2.7M18.6 5.4l-2.2 2.2M7.6 16.4l-2.2 2.2M18.6 18.6l-2.2-2.2M7.6 7.6 5.4 5.4" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
                </svg>`;
            }
            if (key === 'dry') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 3.5c2.9 3.5 4.4 5.9 4.4 8a4.4 4.4 0 1 1-8.8 0c0-2.1 1.5-4.5 4.4-8Z" stroke="currentColor" stroke-width="1.9"/>
                </svg>`;
            }
            if (key === 'fan') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="2.2" stroke="currentColor" stroke-width="1.8"/>
                    <path d="M12.1 4.6c2.1 0 3.6 2.4 2.1 4.3-.9 1.2-2.9 1.1-4 .2-1.4-1.2-.5-4.5 1.9-4.5ZM19 12.1c0 2.1-2.4 3.6-4.3 2.1-1.2-.9-1.1-2.9-.2-4 1.2-1.4 4.5-.5 4.5 1.9ZM11.9 19.4c-2.1 0-3.6-2.4-2.1-4.3.9-1.2 2.9-1.1 4-.2 1.4 1.2.5 4.5-1.9 4.5ZM5 11.9c0-2.1 2.4-3.6 4.3-2.1 1.2.9 1.1 2.9.2 4-1.2 1.4-4.5.5-4.5-1.9Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                </svg>`;
            }
            if (key === 'auto') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M8.4 7.1A5.8 5.8 0 1 1 5.7 12H3.2l2.6-2.8L8.4 12H6.9A4.3 4.3 0 1 0 8.9 8.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>`;
            }
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 4.2v7.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
                <path d="M7.4 6.5A8 8 0 1 0 16.6 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
            </svg>`;
        }
        function getHvacFanLevel(fanSpeed) {
            const text = String(fanSpeed || '').trim().toLowerCase();
            if (!text || text === '--' || text === 'unknown') return 0;
            if (text.includes('低') || text.includes('low')) return 1;
            if (text.includes('中') || text.includes('medium') || text.includes('mid')) return 2;
            if (text.includes('高') || text.includes('high') || text.includes('turbo') || text.includes('strong')) return 4;
            if (text.includes('自动') || text.includes('auto')) return 3;
            return 2;
        }
        function renderHvacFanStatus(fanSpeed) {
            const label = escapeHtml(fanSpeed || '--');
            const level = getHvacFanLevel(fanSpeed);
            const bars = [1, 2, 3, 4].map(idx => `<span class="hvac-fan-bar${idx <= level ? ' active' : ''}"></span>`).join('');
            return `<div class="hvac-fan-wrap">
                <div class="hvac-fan-label">${label}</div>
                <div class="hvac-fan-bars">${bars}</div>
            </div>`;
        }
        function renderHvacFanInline(fanSpeed) {
            const label = escapeHtml(fanSpeed || '--');
            const level = getHvacFanLevel(fanSpeed);
            const bars = [1, 2, 3, 4].map(idx => `<span class="hvac-fan-bar${idx <= level ? ' active' : ''}"></span>`).join('');
            return `<div class="hvac-fan-inline">
                <span class="hvac-fan-inline-label">${label}</span>
                <span class="hvac-fan-inline-bars">${bars}</span>
            </div>`;
        }
        function getHvacControlId(value, scope = '') {
            const prefix = scope ? `${scope}-` : '';
            return `${prefix}${String(value || '').replace(/[^a-zA-Z0-9_-]/g, '_')}`;
        }
        function toHvacNumber(value, fallback = null) {
            const num = Number(value);
            return Number.isFinite(num) ? num : fallback;
        }
        function getHvacSupportedModes(status = {}) {
            const rawModes = Array.isArray(status?.hvac_modes) ? status.hvac_modes : [];
            const normalized = rawModes
                .map(item => String(item || '').trim().toLowerCase())
                .filter(Boolean);
            const fallback = ['off', 'cool', 'heat'];
            const modes = normalized.length ? normalized : fallback;
            return modes
                .filter((mode, index, list) => list.indexOf(mode) === index)
                .filter(mode => ['off', 'cool', 'heat', 'dry', 'fan_only', 'fan', 'auto', 'heat_cool'].includes(mode));
        }
        function renderHvacModeOptions(deviceId, status = {}) {
            const currentMode = String(status?.mode || 'off').trim().toLowerCase();
            const safeDeviceId = escapeHtml(deviceId);
            return getHvacSupportedModes(status).map(mode => {
                const modeClass = getHvacModeClass(mode) || 'off';
                const modeText = escapeHtml(getHvacModeText(mode));
                const isActive = mode === currentMode || getHvacModeClass(mode) === getHvacModeClass(currentMode);
                return `<button type="button" class="hvac-mode-option ${modeClass}${isActive ? ' active' : ''}${getPermissionDisabledClass('hvac.control')}" ${getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限')} onclick="event.stopPropagation(); selectHvacMode('${safeDeviceId}', '${escapeHtml(mode)}')">
                    ${getHvacModeIcon(modeClass)}
                    <span>${modeText}</span>
                </button>`;
            }).join('');
        }
        function getHvacTempBounds(status = {}) {
            return {
                min: toHvacNumber(status?.min_temp, 16),
                max: toHvacNumber(status?.max_temp, 30),
                step: toHvacNumber(status?.target_temp_step, 1) || 1,
            };
        }
        function toggleHvacTempControls(deviceId, scope = '', event = null) {
            if (event) event.stopPropagation();
            closeHvacModeMenus();
            const panel = document.getElementById(`hvac-temp-${getHvacControlId(deviceId, scope)}`);
            if (!panel) return;
            document.querySelectorAll('.hvac-temp-panel.open').forEach(item => {
                if (item !== panel) item.classList.remove('open');
            });
            panel.classList.toggle('open');
        }
        function closeHvacTempControls() {
            document.querySelectorAll('.hvac-temp-panel.open').forEach(item => item.classList.remove('open'));
        }
        function toggleHvacModeMenu(deviceId, scope = '', event = null) {
            if (event) event.stopPropagation();
            closeHvacTempControls();
            const metric = document.getElementById(`hvac-mode-${getHvacControlId(deviceId, scope)}`);
            if (!metric) return;
            document.querySelectorAll('.hvac-mode-block.open').forEach(item => {
                if (item !== metric) item.classList.remove('open');
            });
            metric.classList.toggle('open');
        }
        function closeHvacModeMenus() {
            document.querySelectorAll('.hvac-mode-block.open').forEach(item => item.classList.remove('open'));
        }
        function adjustHvacTemperature(deviceId, delta, event = null) {
            if (event) event.stopPropagation();
            const status = hvacStatusCache[deviceId] || {};
            const bounds = getHvacTempBounds(status);
            const currentTarget = toHvacNumber(status.target_temp, toHvacNumber(status.temp, 24));
            const nextValue = Math.min(bounds.max, Math.max(bounds.min, Math.round((currentTarget + Number(delta || 0)) / bounds.step) * bounds.step));
            hvacStatusCache[deviceId] = Object.assign({}, status, { target_temp: Number(nextValue.toFixed(1)), temp: Number(nextValue.toFixed(1)) });
            renderHvacCards();
            controlHvac(deviceId, 'set_temp', { temperature: Number(nextValue.toFixed(1)) });
        }
        function selectHvacMode(deviceId, mode) {
            closeHvacModeMenus();
            controlHvac(deviceId, String(mode || '').toLowerCase() === 'off' ? 'power_off' : 'set_mode', { mode });
        }
        function getHvacAgeText(status) {
            const ageSec = Number(status?.age_sec);
            if (!Number.isFinite(ageSec)) return '--';
            if (ageSec < 60) return `${Math.round(ageSec)} 秒前`;
            if (ageSec < 3600) return `${Math.round(ageSec / 60)} 分钟前`;
            return `${(ageSec / 3600).toFixed(1)} 小时前`;
        }
        function formatCompactAgeFromSec(ageSec) {
            const value = Number(ageSec);
            if (!Number.isFinite(value)) return '';
            if (value < 60) return `${Math.round(value)}秒前`;
            if (value < 3600) return `${Math.round(value / 60)}分钟前`;
            if (value < 86400) return `${Math.round(value / 3600)}小时前`;
            return `${Math.round(value / 86400)}天前`;
        }
        function getHvacRoomName(cfg) {
            const text = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
            if (text) return text;
            const source = `${cfg?.name || ''} ${cfg?.id || ''}`.toLowerCase();
            if (/一号厅|1号厅|hall1|a1|a2|沉浸|b厅/.test(source)) return '一号厅';
            if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
            if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
            if (/机房|shenlan|machine|server/.test(source)) return '主机房';
            if (/咖啡|cafe/.test(source)) return '咖啡厅';
            if (/办公室|office/.test(source)) return '办公室二楼';
            return '未分区';
        }
        function getHvacSortOrder(cfg) {
            const value = Number(cfg?.sort_order);
            if (Number.isFinite(value)) return value;
            const name = String(cfg?.name || '');
            const match = name.match(/(\d+)/);
            if (match) return Number(match[1]);
            return 999;
        }
        function getHvacRoomSort(roomName) {
            const text = String(roomName || '').trim();
            const priority = {
                '机房': 1,
                '主机房': 1,
                '一号厅': 2,
                '二号厅': 3,
                '办公室': 4,
                '办公室二楼': 4,
                '办公室二楼会议室': 5,
                '咖啡厅': 6,
                '庭院': 7,
            };
            return Number.isFinite(priority[text]) ? priority[text] : 99;
        }
        function getHvacGroupClass(roomName) {
            const text = String(roomName || '').trim();
            if (text === '机房' || text === '主机房') return 'hvac-group-machine';
            if (text.includes('一号厅')) return 'hvac-group-hall1';
            if (text.includes('二号厅')) return 'hvac-group-hall2';
            if (text.includes('咖啡')) return 'hvac-group-cafe';
            if (text.includes('会议室')) return 'hvac-group-meeting';
            if (text.includes('办公室')) return 'hvac-group-office';
            return 'hvac-group-misc';
        }
        function getHvacGroupAccent(roomName) {
            const text = String(roomName || '').trim();
            if (text === '机房' || text === '主机房') return { accent: '#22c55e', border: 'rgba(34,197,94,0.46)', glow: 'rgba(34,197,94,0.14)' };
            if (text.includes('一号厅')) return { accent: '#38bdf8', border: 'rgba(56,189,248,0.48)', glow: 'rgba(56,189,248,0.16)' };
            if (text.includes('二号厅')) return { accent: '#818cf8', border: 'rgba(129,140,248,0.50)', glow: 'rgba(129,140,248,0.16)' };
            if (text.includes('咖啡')) return { accent: '#fb923c', border: 'rgba(251,146,60,0.48)', glow: 'rgba(251,146,60,0.15)' };
            if (text.includes('会议室')) return { accent: '#a855f7', border: 'rgba(168,85,247,0.50)', glow: 'rgba(168,85,247,0.15)' };
            if (text.includes('办公室')) return { accent: '#0ea5e9', border: 'rgba(14,165,233,0.46)', glow: 'rgba(14,165,233,0.15)' };
            return { accent: '#64748b', border: 'rgba(100,116,139,0.42)', glow: 'rgba(100,116,139,0.12)' };
        }
        function normalizeHvacEnvRoomName(value) {
            const text = String(value || '').trim();
            const source = text.toLowerCase();
            if (!text) return '';
            if (/机房|深澜|server|machine/.test(source)) return '主机房';
            if (/一号厅|1号厅|hall1|沉浸/.test(source)) return '一号厅';
            if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
            if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
            if (/二楼办公室|办公室二楼|office|办公室/.test(source)) return '办公室二楼';
            if (/咖啡|cafe/.test(source)) return '咖啡厅';
            return text;
        }
        function getEnvSensorRoomName(cfg) {
            const explicit = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
            if (explicit) return normalizeHvacEnvRoomName(explicit);
            return normalizeHvacEnvRoomName(`${cfg?.name || ''} ${cfg?.id || ''}`);
        }
        function getEnvThermalAgeSec(st) {
            const ages = [Number(st?.temp_age_sec), Number(st?.hum_age_sec), Number(st?.age_sec)]
                .filter(value => Number.isFinite(value));
            return ages.length ? Math.min(...ages) : null;
        }
        function envSensorHasThermalValue(st) {
            return Number.isFinite(Number(st?.temp)) || Number.isFinite(Number(st?.hum));
        }
        function findRoomEnvSensors(roomName, limit = 2) {
            const data = window.__envStatusCache || {};
            const targetRoom = normalizeHvacEnvRoomName(roomName);
            if (!targetRoom) return [];
            const envConfigList = Array.isArray(window.__envConfigsCache) ? window.__envConfigsCache : [];
            return envConfigList
                .map(cfg => {
                    const st = data[cfg.id] || {};
                    const sensorRoom = getEnvSensorRoomName(cfg);
                    const roomMatched = sensorRoom === targetRoom;
                    const text = `${cfg?.id || ''} ${cfg?.name || ''}`.toLowerCase();
                    const isContactOnly = isContactLikeEnvSensor(cfg) && !envSensorHasThermalValue(st);
                    const hasThermal = envSensorHasThermalValue(st);
                    if (!roomMatched || isContactOnly || !hasThermal) return null;
                    const ageSec = getEnvThermalAgeSec(st);
                    const statusLevel = String(st?.status_level || (st?.online ? 'online' : (st?.stale ? 'stale' : 'offline'))).toLowerCase();
                    const score = (st?.online ? 1000 : 0)
                        + (statusLevel === 'stale' ? 120 : 0)
                        + (Number.isFinite(ageSec) ? Math.max(0, 7200 - Math.min(ageSec, 7200)) / 10 : 0)
                        + (text.includes(targetRoom.toLowerCase()) ? 30 : 0);
                    return { cfg, st, ageSec, statusLevel, score };
                })
                .filter(Boolean)
                .sort((left, right) => right.score - left.score)
                .slice(0, limit);
        }
        function renderHvacRoomEnvChips(roomName, options = {}) {
            const sensors = findRoomEnvSensors(roomName, options.limit || 2);
            if (!sensors.length) return '';
            return sensors.map(item => {
                const st = item.st || {};
                const temp = Number(st.temp);
                const hum = Number(st.hum);
                if (!Number.isFinite(temp) && !Number.isFinite(hum)) return '';
                const tempText = Number.isFinite(temp) ? `${temp.toFixed(temp % 1 === 0 ? 0 : 1)}°C` : '--°C';
                const humText = Number.isFinite(hum) ? `${hum.toFixed(hum % 1 === 0 ? 0 : 1)}%` : '--%';
                const level = String(item.statusLevel || '').toLowerCase();
                const chipClass = level === 'stale' ? 'stale' : (st.online ? 'online' : 'offline');
                const ageText = formatCompactAgeFromSec(item.ageSec);
                const title = `${item.cfg?.name || roomName || '空间温湿度'}${ageText ? ` / ${ageText}` : ''}`;
                const label = options.compact ? '室内' : '温湿';
                return `<span class="hvac-room-env-chip ${escapeHtml(chipClass)}" title="${escapeHtml(title)}"><span class="label">${escapeHtml(label)}</span><strong>${escapeHtml(tempText)}</strong><span>/ ${escapeHtml(humText)}</span>${ageText && chipClass !== 'online' ? `<em>${escapeHtml(ageText)}</em>` : ''}</span>`;
            }).filter(Boolean).join('');
        }
        function renderMachineRoomEnvChip() {
            const sensors = findRoomEnvSensors('主机房', 1);
            const st = sensors[0]?.st;
            if (!st) return '';
            const temp = Number(st.temp);
            const hum = Number(st.hum);
            if (!Number.isFinite(temp) && !Number.isFinite(hum)) return '';
            const tempText = Number.isFinite(temp) ? `${temp.toFixed(1)}°C` : '--°C';
            const humText = Number.isFinite(hum) ? `${hum.toFixed(hum % 1 === 0 ? 0 : 1)}%` : '--%';
            return `<span class="hvac-room-env-chip"><span class="label">温湿</span><strong>${escapeHtml(tempText)}</strong><span>/ ${escapeHtml(humText)}</span></span>`;
        }
        function updateHvacRoomEnvSlots() {
            document.querySelectorAll('[data-hvac-room-env]').forEach(slot => {
                const roomName = slot.getAttribute('data-hvac-room-env') || '';
                const html = renderHvacRoomEnvChips(roomName);
                slot.innerHTML = html;
                slot.classList.toggle('is-empty', !html);
            });
            document.querySelectorAll('[data-hvac-card-env]').forEach(slot => {
                const roomName = slot.getAttribute('data-hvac-card-env') || '';
                const html = renderHvacRoomEnvChips(roomName, { compact: true, limit: 1 });
                slot.innerHTML = html;
                slot.classList.toggle('is-empty', !html);
                const row = slot.closest('.hvac-compact-row, .hvac-info-row');
                if (row) {
                    row.classList.toggle('is-empty', !html);
                    if (html) row.style.removeProperty('display');
                    else row.style.setProperty('display', 'none', 'important');
                }
            });
        }
        function buildHvacGroups(configs, statusMap = {}) {
            const groupsMap = new Map();
            (Array.isArray(configs) ? configs : []).forEach(cfg => {
                if (!cfg || cfg.visible === false) return;
                const roomName = getHvacRoomName(cfg);
                if (!groupsMap.has(roomName)) groupsMap.set(roomName, []);
                groupsMap.get(roomName).push(cfg);
            });
            return Array.from(groupsMap.entries())
                .map(([roomName, items]) => {
                    const sortedItems = items.slice().sort((left, right) => {
                        const orderDiff = getHvacSortOrder(left) - getHvacSortOrder(right);
                        if (orderDiff !== 0) return orderDiff;
                        return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN');
                    });
                    const stats = sortedItems.reduce((acc, cfg) => {
                        const st = statusMap[cfg.id] || {};
                        acc.total += 1;
                        if (st.online) acc.online += 1;
                        if (st.power) acc.running += 1;
                        const watt = Number(st.electric_power_w);
                        if (Number.isFinite(watt)) acc.powerW += watt;
                        return acc;
                    }, { total: 0, online: 0, running: 0, powerW: 0 });
                    return { roomName, items: sortedItems, stats };
                })
                .sort((left, right) => {
                    const roomDiff = getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName);
                    if (roomDiff !== 0) return roomDiff;
                    return String(left.roomName || '').localeCompare(String(right.roomName || ''), 'zh-CN');
                });
        }
        function renderHvacGroup(group, scope='page') {
            const roomTitle = escapeHtml(group?.roomName || '未分区');
            const stats = group?.stats || { total: 0, online: 0, running: 0, powerW: 0 };
            const totalText = `${Number(stats.total || 0)} 台`;
            const onlineText = `${Number(stats.online || 0)} 在线`;
            const runningText = `${Number(stats.running || 0)} 运行`;
            const powerText = Number.isFinite(Number(stats.powerW))
                ? (Math.abs(Number(stats.powerW)) >= 1000 ? `${(Number(stats.powerW) / 1000).toFixed(2)} kW` : `${Number(stats.powerW).toFixed(Number(stats.powerW) >= 100 ? 0 : 2)} W`)
                : '--';
            const cardsHtml = (group?.items || []).map(cfg => renderHvacCard(cfg, hvacStatusCache[cfg.id] || {}, scope)).join('');
            const actualGroupItemCount = Math.max(1, (group?.items || []).length);
            const groupItemCount = Math.max(1, Math.min(actualGroupItemCount, 4));
            const rawGroupClass = getHvacGroupClass(group?.roomName);
            const groupClass = escapeHtml(rawGroupClass);
            const accent = getHvacGroupAccent(group?.roomName);
            const groupStyle = [
                `--hvac-room-accent:${accent.accent}`,
                `border:2px solid ${accent.border}`,
                `background:linear-gradient(180deg, ${accent.glow}, rgba(10,20,34,0.98) 34%, rgba(8,16,29,0.98))`,
                `box-shadow:0 12px 30px rgba(2,6,23,0.28), inset 0 1px 0 rgba(255,255,255,0.07)`,
                `border-radius:18px`,
                `padding:10px`,
                `margin:0 0 10px`,
                `position:relative`,
                `overflow:hidden`
            ].join(';');
            const headStyle = [
                `border-bottom:1px solid rgba(148,163,184,0.18)`,
                `padding:0 2px 7px 9px`,
                `margin:0 0 8px`,
                `box-shadow:inset 4px 0 0 ${accent.accent}`,
                `border-radius:10px`
            ].join(';');
            const roomEnvChipHtml = renderHvacRoomEnvChips(group?.roomName);
            const roomEnvSlot = `<span class="hvac-room-env-slot${roomEnvChipHtml ? '' : ' is-empty'}" data-hvac-room-env="${escapeHtml(group?.roomName || '')}">${roomEnvChipHtml}</span>`;
            return `<div class="hvac-group-section ${groupClass} hvac-group-count-${groupItemCount}" data-hvac-count="${groupItemCount}" style="${groupStyle}">
                <div class="hvac-group-head" style="${headStyle}">
                    <div class="hvac-group-title-wrap">
                        <div class="hvac-group-title-row">
                            <div class="hvac-group-title" style="font-size:16px;color:#f8fafc;">${roomTitle}</div>
                            ${roomEnvSlot}
                        </div>
                        <div class="hvac-group-subtitle">按区域汇总空调运行状态与快捷控制</div>
                    </div>
                    <div class="hvac-group-stats">
                        <span class="hvac-group-stat">${escapeHtml(totalText)}</span>
                        <span class="hvac-group-stat online">${escapeHtml(onlineText)}</span>
                        <span class="hvac-group-stat running">${escapeHtml(runningText)}</span>
                        <span class="hvac-group-stat power">${escapeHtml(powerText)}</span>
                    </div>
                </div>
                <div class="hvac-group-grid">${cardsHtml}</div>
            </div>`;
        }
        function isDashboardHvacAttention(status = {}) {
            const errorText = String(status?.error || status?.last_error || '').trim();
            const action = String(status?.hvac_action || '').trim().toLowerCase();
            return !status?.online || !!status?.power || !!errorText || ['cooling', 'heating', 'drying', 'fan'].includes(action);
        }
        function getDashboardHvacAttentionRank(item) {
            const st = item?.status || {};
            if (!st.online) return 0;
            if (st.error || st.last_error) return 1;
            if (st.power) return 2;
            return 9;
        }
        function getDashboardHvacTotals(groups = []) {
            return groups.reduce((acc, group) => {
                const stats = group?.stats || {};
                acc.total += Number(stats.total || 0);
                acc.online += Number(stats.online || 0);
                acc.running += Number(stats.running || 0);
                acc.powerW += Number(stats.powerW || 0);
                (group?.items || []).forEach(cfg => {
                    const st = hvacStatusCache[cfg.id] || {};
                    if (!st.online) acc.offline += 1;
                    if (st.error || st.last_error) acc.error += 1;
                });
                return acc;
            }, { total: 0, online: 0, running: 0, offline: 0, error: 0, powerW: 0 });
        }
        function formatHvacDashboardPower(watt) {
            const value = Number(watt);
            if (!Number.isFinite(value)) return '--';
            if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
            return `${value.toFixed(value >= 100 ? 0 : 1)} W`;
        }
        function renderDashboardHvacMetric(label, value, tone = '') {
            return `<div class="dashboard-hvac-metric ${escapeHtml(tone)}">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
            </div>`;
        }
        function renderDashboardHvacAttentionCard(item) {
            const cfg = item?.cfg || {};
            const status = item?.status || {};
            const merged = Object.assign({}, cfg, status);
            const state = getHvacStateSummary(merged);
            const modeClass = getHvacModeClass(merged.mode) || getHvacActionClass(merged);
            const title = escapeHtml(merged.name || merged.id || '未命名空调');
            const roomName = getHvacRoomName(merged);
            const targetText = formatHvacTemperature(merged.target_temp);
            const actionText = merged.power
                ? (state.actionText !== '--' ? state.actionText : state.modeText)
                : state.powerText;
            const powerText = formatHvacPower(merged);
            const ageText = getHvacAgeText(merged);
            const noteParts = [
                roomName,
                ageText && ageText !== '--' ? ageText : '',
                powerText && powerText !== '--' ? powerText : ''
            ].filter(Boolean);
            const deviceId = String(merged.id || '');
            const safeDeviceId = escapeHtml(deviceId);
            return `<div class="dashboard-hvac-device-mini ${state.stateClass}${modeClass ? ` mode-${modeClass}` : ''}">
                <div class="dashboard-hvac-device-main">
                    <div class="dashboard-hvac-device-title">${title}</div>
                    <div class="dashboard-hvac-device-meta">${escapeHtml(noteParts.join(' · '))}</div>
                </div>
                <div class="dashboard-hvac-device-state">
                    <span class="dashboard-hvac-pill ${merged.online ? 'online' : 'offline'}">${escapeHtml(state.onlineText)}</span>
                    <strong>${escapeHtml(targetText)}</strong>
                    <span>${escapeHtml(actionText)}</span>
                </div>
                <button class="dashboard-hvac-power ${getHvacPowerButtonClass(merged)}${getPermissionDisabledClass('hvac.control')}" ${getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限')} title="${escapeHtml(merged.power ? '当前开机，点击关机' : '当前关机，点击开机')}" onclick="event.stopPropagation(); controlHvac('${safeDeviceId}', '${merged.power ? 'power_off' : 'power_on'}')">${getProjectorIconHtml('power')}</button>
            </div>`;
        }
        function renderDashboardHvacRoomTile(group) {
            const stats = group?.stats || {};
            const roomName = group?.roomName || '未分区';
            const accent = getHvacGroupAccent(roomName);
            const offline = Math.max(0, Number(stats.total || 0) - Number(stats.online || 0));
            const roomEnvChipHtml = renderHvacRoomEnvChips(roomName, { compact: true, limit: 1 });
            const loadText = Number(stats.running || 0) > 0
                ? `${Number(stats.running || 0)} 运行`
                : `${Math.max(0, Number(stats.total || 0) - Number(stats.running || 0))} 已关`;
            return `<div class="dashboard-hvac-room-tile ${escapeHtml(getHvacGroupClass(roomName))}" style="--hvac-room-accent:${accent.accent};">
                <div class="dashboard-hvac-room-head">
                    <strong>${escapeHtml(roomName)}</strong>
                    <span>${escapeHtml(loadText)}</span>
                </div>
                <div class="dashboard-hvac-room-line">
                    <span>${escapeHtml(`${Number(stats.online || 0)}/${Number(stats.total || 0)} 在线`)}</span>
                    <span class="${offline ? 'warn' : ''}">${escapeHtml(offline ? `${offline} 离线` : '正常')}</span>
                    <span>${escapeHtml(formatHvacDashboardPower(stats.powerW))}</span>
                </div>
                <div class="dashboard-hvac-room-env${roomEnvChipHtml ? '' : ' is-empty'}" data-hvac-room-env="${escapeHtml(roomName)}">${roomEnvChipHtml}</div>
            </div>`;
        }
        function renderDashboardHvacOverview(groups = []) {
            if (!groups.length) return '<div class="hvac-empty">未配置空调设备</div>';
            const totals = getDashboardHvacTotals(groups);
            const attentionItems = groups.flatMap(group => (group?.items || []).map(cfg => ({
                cfg,
                status: hvacStatusCache[cfg.id] || {},
                roomName: group.roomName,
            }))).filter(item => isDashboardHvacAttention(item.status))
                .sort((left, right) => getDashboardHvacAttentionRank(left) - getDashboardHvacAttentionRank(right)
                    || getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName)
                    || getHvacSortOrder(left.cfg) - getHvacSortOrder(right.cfg));
            const visibleAttention = attentionItems.slice(0, 6);
            const moreCount = Math.max(0, attentionItems.length - visibleAttention.length);
            const attentionHtml = visibleAttention.length
                ? visibleAttention.map(renderDashboardHvacAttentionCard).join('')
                : '<div class="dashboard-hvac-quiet">全部空调处于正常关闭/待机状态</div>';
            const roomHtml = groups.map(renderDashboardHvacRoomTile).join('');
            return `<div class="dashboard-hvac-overview">
                <div class="dashboard-hvac-summary-strip">
                    ${renderDashboardHvacMetric('运行', String(totals.running), totals.running ? 'running' : '')}
                    ${renderDashboardHvacMetric('离线', String(totals.offline), totals.offline ? 'offline' : '')}
                    ${renderDashboardHvacMetric('在线', `${totals.online}/${totals.total}`, 'online')}
                    ${renderDashboardHvacMetric('当前功率', formatHvacDashboardPower(totals.powerW), 'power')}
                    <button class="dashboard-hvac-entry" type="button" onclick="switchTab('hvac', '空调控制', findNavElementByView('hvac'))">详情</button>
                </div>
                <div class="dashboard-hvac-priority">
                    <div class="dashboard-hvac-block-title">
                        <span>需关注</span>
                        <strong>${escapeHtml(moreCount ? `+${moreCount}` : `${attentionItems.length}`)}</strong>
                    </div>
                    <div class="dashboard-hvac-priority-grid">${attentionHtml}</div>
                </div>
                <div class="dashboard-hvac-room-grid">${roomHtml}</div>
            </div>`;
        }
        function getHvacStateSummary(status) {
            const online = !!status?.online;
            const powerOn = !!status?.power;
            const modeText = getHvacModeText(status?.mode);
            const actionText = getHvacActionText(status?.hvac_action);
            return {
                onlineText: online ? '在线' : '离线',
                powerText: powerOn ? '运行中' : '已关闭',
                stateClass: getHvacCardStateClass(status),
                modeText,
                actionText,
            };
        }
        function renderHvacCard(cfg, status = {}, scope='page') {
            const merged = Object.assign({}, cfg || {}, status || {});
            const isDashboardCard = scope === 'dashboard';
            const state = getHvacStateSummary(merged);
            const cardStateClass = state.stateClass || 'offline';
            const modeClass = getHvacModeClass(merged.mode);
            const actionClass = getHvacActionClass(merged);
            const deviceId = String(merged.id || '');
            const safeDeviceId = escapeHtml(deviceId);
            const controlScope = scope === 'dashboard' ? 'dash' : 'page';
            const controlId = getHvacControlId(deviceId, controlScope);
            const title = escapeHtml(merged.name || merged.id || '未命名空调');
            const subtitle = escapeHtml(`${merged.brand || 'Home Assistant'} / ${merged.model || merged.protocol || 'HVAC'}`);
            const targetText = formatHvacTemperature(merged.target_temp);
            const targetValue = targetText.replace('°C', '');
            const thermalClass = merged.power ? (modeClass || actionClass || 'off') : 'off';
            const dashboardThermalText = !merged.online
                ? '离线'
                : (merged.power
                    ? (state.actionText !== '--' ? state.actionText : (state.modeText === '--' ? state.powerText : state.modeText))
                    : '已关闭');
            const thermalText = isDashboardCard
                ? dashboardThermalText
                : (merged.power ? (state.modeText === '--' ? state.powerText : state.modeText) : '已关闭');
            const fanSpeedHtml = renderHvacFanInline(merged.fan_speed || '--');
            const updatedAt = merged.updated_at ? new Date(merged.updated_at).toLocaleTimeString('zh-CN', { hour12:false }) : '--:--:--';
            const powerText = escapeHtml(formatHvacPower(merged));
            const modeText = escapeHtml(state.modeText);
            const actionText = escapeHtml(state.actionText);
            const modeIcon = getHvacModeIcon(modeClass);
            const actionIcon = getHvacModeIcon(modeClass === 'off' ? 'off' : modeClass || 'fan');
            const powerButtonClass = getHvacPowerButtonClass(merged);
            const powerButtonTitle = merged.power ? '当前开机，点击关机' : '当前关机，点击开机';
            const noteText = `最后更新 ${escapeHtml(updatedAt)} · 数据年龄 ${escapeHtml(getHvacAgeText(merged))}`;
            const cardRoomName = getHvacRoomName(merged);
            const roomEnvCompactHtml = renderHvacRoomEnvChips(cardRoomName, { compact: true, limit: 1 });
            const safeCardRoomName = escapeHtml(cardRoomName);
            const hiddenEnvStyle = roomEnvCompactHtml ? '' : ' style="display:none !important;"';
            const roomEnvRowHtml = `<div class="hvac-compact-row env${roomEnvCompactHtml ? '' : ' is-empty'}"${hiddenEnvStyle}><span class="hvac-compact-label">环境</span><strong data-hvac-card-env="${safeCardRoomName}">${roomEnvCompactHtml}</strong></div>`;
            const roomEnvInfoRowHtml = `<div class="hvac-info-row env${roomEnvCompactHtml ? '' : ' is-empty'}"${hiddenEnvStyle}><div class="label">空间温湿度</div><div class="value env" data-hvac-card-env="${safeCardRoomName}">${roomEnvCompactHtml}</div></div>`;
            const detailButton = scope === 'dashboard'
                ? `<button class="hvac-control-btn" type="button" onclick="switchTab('hvac', '空调控制', findNavElementByView('hvac'))">详情</button>`
                : '';
            const powerBadgeHtml = isDashboardCard
                ? ''
                : `<span class="hvac-state-badge ${cardStateClass}">${state.powerText}</span>`;
            const actionStripHtml = isDashboardCard
                ? ''
                : `<div class="hvac-action-strip ${actionClass}">
                            <span class="hvac-mode-icon">${actionIcon}</span>
                            <span class="hvac-action-copy">
                                <span class="hvac-action-caption">动作</span>
                                <span class="hvac-action-text">${actionText}</span>
                            </span>
                        </div>`;
            const modeCaption = isDashboardCard ? '设定模式' : '模式';
            const dashboardSideHtml = `<div class="hvac-dashboard-compact-info">
                            <div class="hvac-compact-row mode ${modeClass || 'off'}">
                                <span class="hvac-compact-label">${modeCaption}</span>
                                <strong>${modeText}</strong>
                            </div>
                            <div class="hvac-compact-row fan">
                                <span class="hvac-compact-label">风速</span>
                                <strong>${fanSpeedHtml}</strong>
                            </div>
                            ${roomEnvRowHtml}
                        </div>`;
            const detailSideHtml = `<div class="hvac-info-stack">
                            ${roomEnvInfoRowHtml}
                            <div class="hvac-info-row">
                                <div class="label">风速</div>
                                <div class="value fan">${fanSpeedHtml}</div>
                            </div>
                            <div class="hvac-info-row power">
                                <div class="label">实时功率</div>
                                <div class="value">${powerText}</div>
                            </div>
                        </div>`;
            return `<div class="hvac-card ${cardStateClass}${modeClass ? ` mode-${modeClass}` : ''}">
                <div class="hvac-card-head">
                    <div>
                        <div class="hvac-title">${title}</div>
                        <div class="hvac-subtitle">${subtitle}</div>
                    </div>
                    <div class="hvac-top-actions">
                        <div class="hvac-chip-row">
                            <span class="hvac-state-badge ${merged.online ? 'online' : 'offline'}">${state.onlineText}</span>
                            ${powerBadgeHtml}
                        </div>
                        <button class="projector-power-key ${powerButtonClass}${getPermissionDisabledClass('hvac.control')}" ${getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限')} title="${escapeHtml(powerButtonTitle)}" onclick="event.stopPropagation(); controlHvac('${safeDeviceId}', '${merged.power ? 'power_off' : 'power_on'}')">${getProjectorIconHtml('power')}</button>
                    </div>
                </div>
                <div class="hvac-body">
                    <div id="hvac-temp-${controlId}" class="hvac-temp-panel" onclick="toggleHvacTempControls('${safeDeviceId}', '${controlScope}', event)" title="点击调整目标温度">
                        <div class="hvac-temp-label">目标温度</div>
                        <div class="hvac-temp-value">${escapeHtml(targetValue)}<small>°C</small></div>
                        <div class="hvac-temp-target compact">
                            <div class="hvac-temp-hint">+ / - 调温</div>
                        </div>
                        <div class="hvac-thermal-pill ${thermalClass}">
                            ${getHvacModeIcon(thermalClass)}
                            <span>${escapeHtml(thermalText)}</span>
                        </div>
                        <div class="hvac-temp-stepper" onclick="event.stopPropagation()">
                            <button type="button" class="hvac-temp-step-btn${getPermissionDisabledClass('hvac.control')}" ${getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限')} onclick="adjustHvacTemperature('${safeDeviceId}', 1, event)" title="目标温度 +1">+</button>
                            <button type="button" class="hvac-temp-step-btn${getPermissionDisabledClass('hvac.control')}" ${getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限')} onclick="adjustHvacTemperature('${safeDeviceId}', -1, event)" title="目标温度 -1">-</button>
                        </div>
                    </div>
                    <div class="hvac-side-panel">
                        <div id="hvac-mode-${controlId}" class="hvac-mode-block ${modeClass}${isDashboardCard ? ' dashboard-hidden' : ''}">
                            <button type="button" class="hvac-mode-trigger ${modeClass || 'off'}" onclick="toggleHvacModeMenu('${safeDeviceId}', '${controlScope}', event)" title="点击切换模式">
                                <span class="hvac-mode-main">
                                    <span class="hvac-mode-icon">${modeIcon}</span>
                                    <span class="hvac-mode-copy">
                                        <span class="hvac-mode-caption">${modeCaption}</span>
                                        <span class="hvac-mode-name">${modeText}</span>
                                    </span>
                                </span>
                                <span class="hvac-mode-side">切换</span>
                            </button>
                            <div class="hvac-mode-popover" onclick="event.stopPropagation()">${renderHvacModeOptions(deviceId, merged)}</div>
                        </div>
                        ${actionStripHtml}
                        ${isDashboardCard ? dashboardSideHtml : detailSideHtml}
                    </div>
                </div>
                ${isDashboardCard
                    ? `<div class="hvac-dashboard-footer"><div class="dashboard-mini-note">${noteText}</div>${detailButton ? `<div class="hvac-actions">${detailButton}</div>` : ''}</div>`
                    : `${detailButton ? `<div class="hvac-actions">${detailButton}</div>` : ''}<div class="dashboard-mini-note">${noteText}</div>`}
                ${merged.error ? `<div class="hvac-error">${escapeHtml(String(merged.error))}</div>` : ''}
            </div>`;
        }
        function renderHvacCards() {
            const dashboardGrid = document.getElementById('dashboard-hvac-grid');
            const pageGrid = document.getElementById('hvac-grid-container');
            const visibleConfigs = hvacConfigs.filter(cfg => cfg && cfg.visible !== false);
            const groups = buildHvacGroups(visibleConfigs, hvacStatusCache);
            const dashboardHtml = groups.length
                ? renderDashboardHvacOverview(groups)
                : '<div class="hvac-empty">未配置空调设备</div>';
            const pageHtml = groups.length
                ? groups.map(group => renderHvacGroup(group, 'page')).join('')
                : '<div class="hvac-empty">未配置空调设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid) pageGrid.innerHTML = pageHtml;
            const dashHvacOnline = document.getElementById('dash-hvac-online');
            if (dashHvacOnline) dashHvacOnline.innerText = visibleConfigs.filter(cfg => (hvacStatusCache[cfg.id] || {}).online).length;
        }
        function findNavElementByView(viewId) {
            return Array.from(document.querySelectorAll('.nav-menu li')).find(el => String(el.getAttribute('onclick') || '').includes(`switchTab('${viewId}'`)) || null;
        }
        function getInitialViewFromUrl() {
            const params = new URLSearchParams(window.location.search || '');
            const requested = String(params.get('view') || params.get('tab') || '').trim();
            if (!requested) return null;
            const safeView = requested.replace(/[^a-zA-Z0-9_-]/g, '');
            if (!safeView || !document.getElementById('view-' + safeView)) return null;
            return safeView;
        }
        function getViewTitleFromNav(navEl, fallback = '') {
            const onclickText = String(navEl?.getAttribute('onclick') || '');
            const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
            return match ? match[2] : fallback;
        }
        function updateHvacStatus(showError = false) {
            if (!hvacConfigs.length) return Promise.resolve({});
            return fetchJson('/api/hvac/status', {}, '空调状态读取失败')
                .then(data => {
                    hvacStatusCache = data || {};
                    renderHvacCards();
                    return data;
                })
                .catch(err => {
                    console.error('空调状态更新失败', err);
                    if (showError) showToast(translateApiError(err?.message, '空调状态读取失败'), true);
                    throw err;
                });
        }
        function controlHvac(deviceId, action, extra = {}) {
            if (!ensurePermission('hvac.control', '控制空调')) return;
            const payload = Object.assign({ device_id: deviceId, action }, extra || {});
            const loadingTextMap = {
                power_on: '空调开机指令下发中...',
                power_off: '空调关机指令下发中...',
                set_mode: '空调模式切换中...',
                set_temp: '空调温度设置中...'
            };
            showToast(loadingTextMap[action] || '空调控制中...', false);
            fetchJsonLoose('/api/hvac/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }, '空调控制失败')
                .then(data => {
                    if (!data?.success) {
                        showToast(data?.msg || data?.message || '空调控制失败', true);
                        return;
                    }
                    if (data.status && typeof data.status === 'object') {
                        hvacStatusCache[deviceId] = data.status;
                        renderHvacCards();
                    }
                    showToast(data.msg || '空调控制成功');
                    setTimeout(() => { updateHvacStatus(); updateDashboardLogs(); }, 320);
                })
                .catch(err => {
                    showToast(translateApiError(err?.message, '空调控制失败'), true);
                });
        }
        function renderDashboardLogs(logs) {
            const logList = document.getElementById('dashboard-logs');
            if (!logList) return;
            const visibleLogs = sortLogsNewestFirst(filterDashboardTotalLogs(logs));
            if (!visibleLogs.length) {
                logList.innerHTML = '<div style="color:var(--text-sub); text-align:center; padding:24px 0;">暂无操作日志</div>';
                return;
            }
            const html = visibleLogs.slice(0, 40).map(log => {
                const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', {hour12:false}) : '--:--:--';
                const message = escapeHtml(normalizeLogOperationText(log));
                return `<div class="log-item"><span class="time">[${timeText}]</span><span class="msg">${message}</span></div>`;
            }).join('');
            if (logList.innerHTML !== html) {
                logList.innerHTML = html;
                logList.scrollTop = 0;
            }
        }
        function updateDashboardLogs() {
            fetch('/api/logs')
                .then(r => r.json())
                .then(logs => {
                    const nextLogs = Array.isArray(logs) ? logs : [];
                    const changed = buildDashboardLogSignature(nextLogs) !== buildDashboardLogSignature(dashboardLogsCache || []);
                    dashboardLogsCache = nextLogs;
                    if (changed) renderDashboardLogs(dashboardLogsCache);
                })
                .catch(err => console.error('首页系统日志更新失败', err));
        }
        setInterval(updateGlobalClock, 1000);

        // 门禁控制
        let doorDrawState = { slot: '', isDrawing: false, startX: 0, startY: 0 };
        function initDoorCanvas(slot) {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            if (els.image.clientWidth > 0) {
                els.canvas.width = els.image.clientWidth;
                els.canvas.height = els.image.clientHeight;
            }
        }
        ['left', 'right'].forEach(slot => {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            const ctx = els.canvas.getContext('2d');
            els.image.onload = function() { initDoorCanvas(slot); };
            els.canvas.addEventListener('mousedown', function(e) {
                if (doorDrawState.slot !== slot) return;
                doorDrawState.isDrawing = true;
                const rect = els.image.getBoundingClientRect();
                doorDrawState.startX = e.clientX - rect.left;
                doorDrawState.startY = e.clientY - rect.top;
            });
            els.canvas.addEventListener('mousemove', function(e) {
                if (doorDrawState.slot !== slot || !doorDrawState.isDrawing) return;
                const rect = els.image.getBoundingClientRect();
                const currentX = e.clientX - rect.left;
                const currentY = e.clientY - rect.top;
                ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
                ctx.strokeStyle = '#3b82f6';
                ctx.lineWidth = 3;
                ctx.strokeRect(doorDrawState.startX, doorDrawState.startY, currentX - doorDrawState.startX, currentY - doorDrawState.startY);
            });
            els.canvas.addEventListener('mouseup', function(e) {
                if (doorDrawState.slot !== slot || !doorDrawState.isDrawing) return;
                doorDrawState.isDrawing = false;
                const rect = els.image.getBoundingClientRect();
                const endX = e.clientX - rect.left;
                const endY = e.clientY - rect.top;
                const p_x1 = Math.max(0, Math.min(doorDrawState.startX, endX) / rect.width);
                const p_y1 = Math.max(0, Math.min(doorDrawState.startY, endY) / rect.height);
                const p_x2 = Math.min(1, Math.max(doorDrawState.startX, endX) / rect.width);
                const p_y2 = Math.min(1, Math.max(doorDrawState.startY, endY) / rect.height);
                const cameraKey = getDoorSlotCameraKey(slot);
                saveDoorRegionSelection({ camera_key: cameraKey, p_x1, p_y1, p_x2, p_y2 })
                    .then(data => {
                        doorRegionsCache[cameraKey] = (data && data.region) ? data.region : { p_x1, p_y1, p_x2, p_y2 };
                        ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
                        els.canvas.style.display = 'none';
                        doorDrawState.slot = '';
                    })
                    .catch(err => {
                        showToast(`保存失败: ${translateApiError(err?.message, '请稍后重试')}`, true);
                    });
            });
        });
        window.onresize = () => {
            initDoorCanvas('left');
            initDoorCanvas('right');
            resizePowerCharts();
            if (myCharts.meterTrend) myCharts.meterTrend.resize();
            if (myCharts.dashboardEnergyTrend) myCharts.dashboardEnergyTrend.resize();
        };
        function startDrawRegion(slot = 'right') {
            const els = getDoorSlotElements(slot);
            if (!els.canvas || !els.image) return;
            initDoorCanvas(slot);
            doorDrawState = { slot, isDrawing: false, startX: 0, startY: 0 };
            els.canvas.style.display = 'block';
            els.canvas.style.cursor = 'crosshair';
            showToast(`请在${slot === 'right' ? '右侧' : '左侧'}画面拖拽框选检测区域`);
        }
        function updateDoorStatus(force = false) { const now = Date.now(); if (!force && now - lastDoorStatusFetchAt < 1000) return; lastDoorStatusFetchAt = now; fetch('/get_door_status').then(res => res.json()).then(data => { if (data.status === 'success') { const statusEl = document.getElementById('doorStatus'); if (statusEl) { statusEl.textContent = data.msg; statusEl.className = `tag door-status-${data.door_status}`; } const debugTip = document.getElementById('debugTip'); if (debugTip) debugTip.textContent = `双帧差异阈值 | ${data.diff}`; const dashStatus = document.getElementById('dash-door-status'); if (dashStatus) { dashStatus.textContent = data.msg.replace(/[\u2705\uD83D\uDEAA\u23F3\u26A0\uFE0F\u23F8\uFE0F\u23F8]\s*/g, ''); if (data.door_status === 'opening' || data.door_status === 'closing') dashStatus.className = 'value highlight'; else if (data.door_status === 'open') dashStatus.className = 'value danger'; else if (data.door_status === 'closed') dashStatus.className = 'value green'; else dashStatus.className = 'value blue'; } } }).catch(err => { const statusEl = document.getElementById('doorStatus'); if (statusEl) statusEl.textContent = '检测器离线'; }); }
        function openWizard() { document.getElementById('aiWizardModal').style.display = 'block'; document.getElementById('step1-card').style.opacity = '1'; document.getElementById('step1-card').style.pointerEvents = 'auto'; document.getElementById('step2-card').style.opacity = '0.4'; document.getElementById('step2-card').style.pointerEvents = 'none'; }
        function closeWizard() { document.getElementById('aiWizardModal').style.display = 'none'; }
        const wizardBox = document.getElementById('wizardBox'); const wizardHeader = document.getElementById('wizardHeader'); let isWizDragging = false; let wizOffsetX = 0, wizOffsetY = 0; wizardHeader.addEventListener('mousedown', function(e) { if(e.target.tagName.toLowerCase() === 'button') return; isWizDragging = true; wizOffsetX = e.clientX - wizardBox.offsetLeft; wizOffsetY = e.clientY - wizardBox.offsetTop; wizardBox.style.transition = 'none'; wizardBox.style.opacity = '0.9'; }); document.addEventListener('mousemove', function(e) { if (!isWizDragging) return; wizardBox.style.left = (e.clientX - wizOffsetX) + 'px'; wizardBox.style.top = (e.clientY - wizOffsetY) + 'px'; wizardBox.style.right = 'auto'; }); document.addEventListener('mouseup', function() { if (isWizDragging) { isWizDragging = false; wizardBox.style.transition = 'opacity 0.2s'; wizardBox.style.opacity = '1'; } });
        function captureWizard(state, statusId) { const btn = event.target; const oldText = btn.innerHTML; btn.innerHTML = '正在保存...'; btn.disabled = true; fetch(`/api/ai_wizard/capture/${state}`, {method: 'POST'}).then(res => res.json()).then(data => { showToast(data.msg, data.status === 'error'); if (data.status === 'success') { const statusSpan = document.getElementById(statusId); statusSpan.innerHTML = '已保存'; statusSpan.style.color = 'var(--success)'; if (state === 'closed') { document.getElementById('step1-card').style.opacity = '0.4'; document.getElementById('step1-card').style.pointerEvents = 'none'; document.getElementById('step2-card').style.opacity = '1'; document.getElementById('step2-card').style.pointerEvents = 'auto'; } } }).catch(err => { showToast('拍照保存失败', true); }).finally(() => { btn.innerHTML = oldText; btn.disabled = false; }); }
        function applyAiCalibration() { const btn = document.getElementById('btnWizardRecord'); btn.textContent = `正在提取并计算...`; btn.disabled = true; fetch('/api/ai_wizard/apply_model', {method: 'POST'}).then(res => res.json()).then(data => { showToast(data.msg, data.status === 'error'); if(data.status === 'success') { setTimeout(closeWizard, 1500); } }).catch(err => { showToast('生成模型失败', true); }).finally(() => { btn.disabled = false; btn.innerHTML = `一键生成 AI 推演模型`; }); }
        function controlDoor(action) { if (!ensurePermission('door.control', '控制门禁')) return; fetch(`/door_control/${action}`).then(res => res.json()).then(data => { showToast(data.msg, data.status === 'error'); }).catch(err => { showToast('指令下发失败', true); }); }

        // 强电与灯光控制
        configData.cabinets.forEach((cab, idx) => { pwrLocks[idx] = {}; pwrStates[idx] = []; pwrDesiredStates[idx] = {}; });
        function doPowerStart(cabId){ if (!ensurePermission('power.control', '执行强电启动')) return; fetch(`/api/onekey_start?cab=${cabId}`).then(r => r.json()).then(data => { if(!data.ok){ showToast(data.msg || '启动失败', true); return; } showToast("启动指令已发送"); setTimeout(() => updatePowerData(), 600); }).catch(() => showToast('启动请求失败', true)); }
        function doPowerStop(cabId, msg){ if (!ensurePermission('power.control', '执行强电停止')) return; if(confirm(msg)){ fetch(`/api/onekey_stop?cab=${cabId}`).then(r => r.json()).then(data => { if(!data.ok){ showToast(data.msg || '停止失败', true); return; } showToast("停止指令已下发"); setTimeout(() => updatePowerData(), 600); }).catch(() => showToast('停止请求失败', true)); } }
function renderPwrChannel(cabId, chNum) { const cachedChannels = (powerStatusCache[cabId] || {}).channels_1_4; const hasCachedStatus = Array.isArray(cachedChannels) && cachedChannels[chNum - 1] !== undefined; const status = getPowerChannelStatus(cabId, chNum); const chItem = document.getElementById(`pch_${cabId}_${chNum}`); if(!chItem) return; let chCfg = (configData.cabinets[cabId].channels_config || []).find(c => c.channel === chNum); let chName = chCfg ? chCfg.name : (configData.cabinets[cabId].ui_text.label_channel + chNum); let chRemark = chCfg ? (chCfg.remark || '') : ''; const ui = configData.cabinets[cabId].ui_text; const isPending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]); const cls = isPending ? 'ch-off' : (status === null || status === undefined ? 'ch-err' : (status ? 'ch-on' : 'ch-off')); const txt = isPending ? '执行中' : (status === null || status === undefined ? '离线' : (status ? ui.label_on : ui.label_off)); const oldClasses = Array.from(chItem.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn' || c === 'power-channel-btn').join(' '); chItem.className = `${oldClasses || 'ch-btn power-channel-btn'} ${cls}`; chItem.innerHTML = `<span class="name" title="${escapeHtml(chRemark ? chName + ' / ' + chRemark : chName)}">${escapeHtml(chName)}</span>${chRemark ? `<span class="remark" title="${escapeHtml(chRemark)}">${escapeHtml(chRemark)}</span>` : ''}<span class="state">${escapeHtml(txt)}</span>`; chItem.disabled = isPending || chItem.classList.contains('permission-disabled'); chItem.style.pointerEvents = isPending ? 'none' : ''; chItem.style.opacity = isPending ? '0.78' : ''; chItem.dataset.stateSource = hasCachedStatus ? 'api' : 'local'; }
        function togglePower(cabId, chNum) { if (!ensurePermission('power.control', '切换强电通道')) return; pwrPending[cabId] = pwrPending[cabId] || {}; if (pwrPending[cabId][chNum]) { showToast('该回路正在执行中，请等待状态确认'); return; } const status = getPowerChannelStatus(cabId, chNum); if(status === null || status === undefined) return; if(status && !confirm(configData.cabinets[cabId].ui_text.confirm_single_off)) return; const targetState = !status; pwrLocks[cabId][chNum] = Date.now(); pwrPending[cabId][chNum] = true; renderPwrChannel(cabId, chNum); fetch("/api/set", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({cab: cabId, ch: chNum, on: targetState}) }).then(r => r.json()).then(data => { if(!data.ok){ renderPwrChannel(cabId, chNum); showToast(data.msg || '强电控制失败', true); return; } if (data.status && Array.isArray(data.status.channels_1_4)) { powerStatusCache[cabId] = Object.assign({}, powerStatusCache[cabId] || {}, data.status || {}); data.status.channels_1_4.forEach((st, idx) => { const nextCh = idx + 1; pwrStates[cabId][nextCh] = st; renderPwrChannel(cabId, nextCh); }); } setTimeout(() => updatePowerData(), 450); }).catch(() => { renderPwrChannel(cabId, chNum); showToast('强电控制请求失败', true); }).finally(() => { delete pwrPending[cabId][chNum]; renderPwrChannel(cabId, chNum); setTimeout(() => { delete pwrLocks[cabId][chNum]; }, POWER_CHANNEL_LOCK_MS); }); }
        async function updatePowerData() { let onlineCount = 0; const activeView = getActiveViewId(); const shouldLoadDetails = activeView === 'power'; const shouldLoadDashboard = activeView === 'dashboard' || isDashboardSectionVisible('power_quick'); for (const [cabId, cab] of configData.cabinets.entries()) { try { const d = await fetch(`/api/status?cab=${cabId}`).then(r=>r.json()); powerStatusCache[cabId] = d; if(d.comm_status) onlineCount++; const statusEl = document.getElementById(`commStatus_${cabId}`); if(statusEl) { statusEl.className = d.comm_status ? 'tag normal' : 'tag error'; statusEl.innerText = d.comm_status ? '通讯正常' : '通讯异常'; } let wm = document.getElementById(`workMode_${cabId}`); if(wm) wm.innerText = d.work_mode || "未知"; ['va','vb','vc','ia','ib','ic','energy','dailyEnergy','monthEnergy','realtimePower','temp','humi'].forEach(k => { const el = document.getElementById(`${k}_${cabId}`); let val = d[k === 'energy'?'electric_energy': (k==='dailyEnergy'?'daily_energy': (k==='monthEnergy'?'monthly_energy': (k==='realtimePower'?'realtime_power': (k==='temp'?'cabinet_temp': (k==='humi'?'cabinet_humidity': k.replace('v','voltage_').replace('i','current_'))))))]; if(el && val !== undefined) el.innerText = parseFloat(val).toFixed(k.includes('i')||k.includes('v')||k==='temp'||k==='humi'||k.includes('Energy')?1:2); }); const maxCount = cab.channel_count || 8; const allChannels = (d.channels_1_4||[]).slice(0, maxCount); allChannels.forEach((st, idx) => { const chNum = idx + 1; if (pwrLocks[cabId][chNum] && (Date.now() - pwrLocks[cabId][chNum] < 3000)) return; pwrStates[cabId][chNum] = st; renderPwrChannel(cabId, chNum); }); if (shouldLoadDetails || shouldLoadDashboard) refreshPowerSupplement(cabId); } catch(err) { console.error('强电状态更新失败', cabId, err); } } renderDashboardPowerCards(); let pOnline = document.getElementById('dash-power-online'); if(pOnline) pOnline.innerText = onlineCount; resizePowerCharts(); }
        function exportEnergyHistory() {
            window.open('/api/export/energy_30days', '_blank');
        }

        configData.light_devices.forEach(dev => { lightLocks[dev.id] = {}; lightStates[dev.id] = []; lightOnlineStates[dev.id] = false; });
        function normalizeLightChannelState(status) {
            if (status === null || status === undefined) return null;
            if (status === true || status === false) return status;
            if (status === 1 || status === '1') return true;
            if (status === 0 || status === '0') return false;
            if (typeof status === 'string') {
                const text = status.trim().toLowerCase();
                if (['true', 'on', 'open', 'opened', 'enabled', 'yes', 'y', 'online', 'running', '已开', '开启', '打开', '开'].includes(text)) return true;
                if (['false', 'off', 'close', 'closed', 'disabled', 'no', 'n', 'offline', 'stopped', '已关', '关闭', '关'].includes(text)) return false;
            }
            return null;
        }
        function getLightChannelStateFromSources(devId, chNum, channelsMap = {}) {
            const channelNo = Number(chNum);
            const apiSources = [
                (channelsMap || {})[devId],
                (channelsMap || {})[String(devId)],
            ];
            for (const source of apiSources) {
                if (!source) continue;
                if (Array.isArray(source)) {
                    const candidates = [source[channelNo - 1], source[channelNo]];
                    for (const candidate of candidates) {
                        const normalized = normalizeLightChannelState(candidate);
                        if (normalized !== null) return normalized;
                    }
                    continue;
                }
                if (typeof source === 'object') {
                    const candidates = [
                        source[channelNo],
                        source[String(channelNo)],
                        source[`ch${channelNo}`],
                        source[`channel_${channelNo}`],
                    ];
                    for (const candidate of candidates) {
                        const normalized = normalizeLightChannelState(candidate);
                        if (normalized !== null) return normalized;
                    }
                }
            }
            const cacheSources = [
                lightStates[devId],
                lightStates[String(devId)],
            ];
            for (const source of cacheSources) {
                if (!source) continue;
                if (Array.isArray(source)) {
                    const candidates = [source[channelNo]];
                    for (const candidate of candidates) {
                        const normalized = normalizeLightChannelState(candidate);
                        if (normalized !== null) return normalized;
                    }
                    continue;
                }
                if (typeof source === 'object') {
                    const candidates = [
                        source[channelNo],
                        source[String(channelNo)],
                        source[`ch${channelNo}`],
                        source[`channel_${channelNo}`],
                    ];
                    for (const candidate of candidates) {
                        const normalized = normalizeLightChannelState(candidate);
                        if (normalized !== null) return normalized;
                    }
                }
            }
            return null;
        }
        function getLightChannelUiState(devId, chNum) {
            const status = getLightChannelStateFromSources(devId, chNum, {});
            const isOnline = !!lightOnlineStates[devId];
            if (!isOnline) return { cls: 'ch-err', text: '离线', actionable: false };
            if (status === true) return { cls: 'ch-on', text: '已开启', actionable: true };
            if (status === false) return { cls: 'ch-off', text: '已关闭', actionable: true };
            return { cls: 'ch-unknown', text: '待确认', actionable: false };
        }
        function renderLightChannel(devId, chNum) { const btn = document.getElementById(`lch_${devId}_${chNum}`); if(!btn) return; const uiState = getLightChannelUiState(devId, chNum); const oldClasses = Array.from(btn.classList).filter(c => c.startsWith('ch-span-') || c === 'ch-btn').join(' '); btn.className = `${oldClasses} ${uiState.cls}`; btn.querySelector('.state').innerText = uiState.text; btn.title = uiState.actionable ? '' : (lightOnlineStates[devId] ? '设备在线，但该通道状态暂未确认' : '设备离线，无法读取通道状态'); }
        function renderDashboardLightCards(statusData = {}) {
            const container = document.getElementById('dashboard-light-grid');
            if (!container) return;
            const devices = Array.isArray(configData.light_devices) ? configData.light_devices.slice(0, 4) : [];
            const extras = statusData.extras || {};
            if (!devices.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置灯光模块</div>';
                return;
            }
            container.innerHTML = devices.map(device => {
                const extraMeta = extras[String(device.id)] || {};
                const statusMeta = getDeviceStatusMeta({
                    online: !!((statusData.online || {})[device.id]),
                    status_level: extraMeta.status_level,
                    stale: extraMeta.stale,
                    poll_failures: extraMeta.poll_failures,
                    last_success_at: extraMeta.last_success_at,
                    last_checked_at: extraMeta.last_checked_at,
                    last_error: extraMeta.last_error,
                }, { staleText: '陈旧', errorText: '异常' });
                const online = statusMeta.isOnlineLike;
                const channels = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999)).slice(0, 4) : [];
                const currentStates = Array.isArray((statusData.channels || {})[device.id]) ? (statusData.channels || {})[device.id] : [];
                const visibleChannelCount = Array.isArray(device.channels_config) ? device.channels_config.filter(ch => ch && ch.visible !== false).length : currentStates.length;
                const onCount = currentStates.filter(Boolean).length;
                const unknownCount = currentStates.filter(st => st === null || st === undefined).length;
                const actions = channels.map(ch => {
                    const uiState = getLightChannelUiState(device.id, ch.channel);
                    const btnClass = uiState.cls === 'ch-on' ? 'success' : (uiState.cls === 'ch-off' ? 'secondary' : (online ? 'warning' : 'danger'));
                    return `<button class="dashboard-mini-btn ${btnClass}${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${escapeHtml(device.id)}', ${Number(ch.channel)})">${escapeHtml(ch.name || ('CH' + ch.channel))}</button>`;
                }).join('');
                const extraButtons = (((extras[String(device.id)] || {}).dashboard_action_buttons) || []).filter(item => item && item.visible !== false).map(item => {
                    return `<button class="dashboard-mini-btn secondary${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${escapeHtml(device.id)}', '${escapeHtml(item.action || '')}', '${escapeHtml(item.label || item.action || '')}')">${escapeHtml(item.label || item.action || '动作')}</button>`;
                }).join('');
                return `<div class="dashboard-mini-card ${getCardStateClass(statusMeta)}">
                    <div class="dashboard-mini-head">
                        <div>
                            <div class="dashboard-mini-title">${escapeHtml(device.name || device.id)}</div>
                            <div class="dashboard-mini-subtitle">${escapeHtml(device.ip || device.id || '--')}</div>
                        </div>
                        <div class="dashboard-mini-chip-row">
                            <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                        </div>
                    </div>
                    <div class="dashboard-mini-light-summary">
                        <div class="dashboard-mini-light-count">已开 ${escapeHtml(String(onCount))} / ${escapeHtml(String(visibleChannelCount || currentStates.length || 0))}</div>
                        <div class="dashboard-mini-note">${online ? (unknownCount > 0 ? `${unknownCount} 路状态待确认` : statusMeta.note) : statusMeta.note}</div>
                    </div>
                    <div class="dashboard-mini-actions">${actions || '<span class="dashboard-mini-note">暂无可用通道</span>'}${extraButtons}</div>
                </div>`;
            }).join('');
        }
        function renderDashboardLightCompact(statusData = {}) {
            const container = document.getElementById('dashboard-light-compact-grid');
            if (!container) return;
            const devices = Array.isArray(configData.light_devices) ? configData.light_devices : [];
            const onlineMap = statusData.online || {};
            const channelsMap = statusData.channels || {};
            const extras = statusData.extras || {};
            if (!devices.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置灯光模块</div>';
                return;
            }
            container.classList.remove('home-status-list');
            container.innerHTML = devices.map(device => {
                const extraMeta = extras[String(device.id)] || {};
                const statusMeta = getDeviceStatusMeta({
                    online: !!onlineMap[device.id],
                    status_level: extraMeta.status_level,
                    stale: extraMeta.stale,
                    poll_failures: extraMeta.poll_failures,
                    last_success_at: extraMeta.last_success_at,
                    last_checked_at: extraMeta.last_checked_at,
                    last_error: extraMeta.last_error,
                }, { staleText: '陈旧', errorText: '异常' });
                const online = statusMeta.isOnlineLike;
                const rawStates = Array.isArray(channelsMap[device.id]) ? channelsMap[device.id] : (Array.isArray(channelsMap[String(device.id)]) ? channelsMap[String(device.id)] : []);
                const visibleChannels = Array.isArray(device.channels_config)
                    ? device.channels_config.filter(ch => ch && ch.visible !== false).sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                    : [];
                const total = visibleChannels.length || rawStates.length || 0;
                const knownVisibleStates = visibleChannels.length
                    ? visibleChannels.map(ch => getLightChannelStateFromSources(device.id, ch.channel, channelsMap))
                    : rawStates.map(st => normalizeLightChannelState(st));
                const onCount = knownVisibleStates.filter(st => st === true).length;
                const unknownCount = knownVisibleStates.filter(st => st === null).length;
                const actionChannels = visibleChannels.length
                    ? visibleChannels
                    : rawStates.map((_, idx) => ({ channel: idx + 1, name: `CH${idx + 1}` }));
                const actionNameCounts = actionChannels.reduce((acc, ch) => {
                    const chNum = Number(ch.channel);
                    const name = String(ch.name || `CH${chNum}`);
                    acc.set(name, (acc.get(name) || 0) + 1);
                    return acc;
                }, new Map());
                const actions = actionChannels.slice(0, 8).map(ch => {
                    const chNum = Number(ch.channel);
                    const state = getLightChannelStateFromSources(device.id, chNum, channelsMap);
                    const cls = state === true ? 'on' : (state === false ? 'off' : 'warning');
                    const stateText = state === true ? '开' : (state === false ? '关' : '?');
                    const baseName = String(ch.name || `CH${chNum}`);
                    const displayName = actionNameCounts.get(baseName) > 1 ? `${baseName} ${chNum}` : baseName;
                    return `<button class="home-compact-action ${cls}${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="toggleLight('${escapeHtml(device.id)}', ${chNum})"><span class="label">${escapeHtml(displayName)}</span><span class="home-action-state">${escapeHtml(stateText)}</span></button>`;
                }).join('');
                const extraButtons = ((extraMeta.dashboard_action_buttons || [])).filter(item => item && item.visible !== false).slice(0, 2).map(item => {
                    return `<button class="home-compact-action success${getPermissionDisabledClass('light.control')}" ${getPermissionDisabledAttrs('light.control', '当前账号无灯光控制权限')} onclick="triggerLightAction('${escapeHtml(device.id)}', '${escapeHtml(item.action || '')}', '${escapeHtml(item.label || item.action || '')}')">${escapeHtml(item.label || item.action || '动作')}</button>`;
                }).join('');
                return `<div class="home-compact-card ${online ? '' : 'offline'}">
                    <div class="home-compact-head">
                        <div style="min-width:0;">
                            <div class="home-compact-title">${escapeHtml(device.name || device.id)}</div>
                            <div class="home-compact-subtitle">${escapeHtml(device.ip || device.id || '--')}</div>
                        </div>
                        <div class="home-compact-chip-row">
                            <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                        </div>
                    </div>
                    <div class="home-compact-metrics">
                        ${renderHomeCompactMetric('已开路数', `${onCount} / ${total || '--'}`, onCount > 0 ? 'ok' : '')}
                        ${renderHomeCompactMetric('状态待确认', String(unknownCount || 0), unknownCount > 0 ? 'warn' : '')}
                    </div>
                    <div class="home-compact-actions">${actions || '<span class="home-compact-note">暂无可用通道</span>'}${extraButtons}</div>
                    <div class="home-compact-note">${escapeHtml(statusMeta.note || '--')}</div>
                </div>`;
            }).join('');
        }
        function toggleLight(devId, chNum) { if (!ensurePermission('light.control', '切换灯光通道')) return; if(!lightOnlineStates[devId]) { showToast('设备离线，无法控制通道', true); return; } const rawStatus = lightStates[devId][chNum]; const status = normalizeLightChannelState(rawStatus); if(status === null) { showToast('设备在线，但该通道状态待确认，请稍后再试或使用动作按钮', true); return; } const targetState = !status; lightLocks[devId][chNum] = Date.now(); lightStates[devId][chNum] = targetState; renderLightChannel(devId, chNum); fetch("/api/light/control", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({type: 'single', device_id: devId, channel: chNum, is_open: targetState}) }).then(r => r.json()).then(data => { if(!data.success){ lightStates[devId][chNum] = rawStatus; renderLightChannel(devId, chNum); showToast(data.msg || '灯光控制失败', true); return; } if(Array.isArray(data.channels)){ data.channels.forEach((st, idx) => { lightStates[devId][idx + 1] = st; renderLightChannel(devId, idx + 1); }); } showToast(data.verified === false ? '灯光指令已发送，等待状态确认' : '灯光控制成功'); setTimeout(() => updateLightData(), 600); }).catch(() => { lightStates[devId][chNum] = rawStatus; renderLightChannel(devId, chNum); showToast('灯光控制请求失败', true); }).finally(() => { setTimeout(() => { delete lightLocks[devId][chNum]; }, 1200); }); }
        function triggerLightAction(devId, actionName, label) { if (!ensurePermission('light.control', `执行灯光动作 ${label || actionName}`)) return; fetch("/api/light/control", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({type: 'action', device_id: devId, action: actionName}) }).then(r => r.json()).then(data => { if(!data.success){ showToast(data.msg || `${label || actionName} 执行失败`, true); return; } if(Array.isArray(data.channels)){ data.channels.forEach((st, idx) => { lightStates[devId][idx + 1] = st; renderLightChannel(devId, idx + 1); }); } showToast(data.verified === false ? `${label || actionName} 已下发，等待状态确认` : `${label || actionName} 已执行`); setTimeout(() => updateLightData(), 700); }).catch(() => showToast(`${label || actionName} 请求失败`, true)); }
        function executeScene(sceneId, name) { if (!ensurePermission('light.control', '执行场景联动')) return; if(confirm(`确定要触发全局联动场景 [${name}] 吗？`)) { fetch("/api/light/control", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({type: 'scene', scene_id: sceneId}) }).then(r => r.json()).then(data => { if(!data.success){ showToast(data.msg || `场景联动 [${name}] 执行失败`, true); return; } showToast(`场景联动 [${name}] 触发成功`); setTimeout(() => updateLightData(), 800); }).catch(() => showToast(`场景联动 [${name}] 请求失败`, true)); } }
        function updateLightData() { fetch('/api/light/status').then(r=>r.json()).then(d=>{ let onlineCount = 0; for (let devId in d.online) { lightOnlineStates[devId] = !!d.online[devId]; if(d.online[devId]) onlineCount++; const tag = document.getElementById(`light-status-${devId}`); if(tag) { tag.className = d.online[devId] ? 'tag normal' : 'tag error'; tag.innerText = d.online[devId] ? '通讯正常' : '通讯异常'; } (d.channels[devId] || []).forEach((st, idx) => { const chNum = idx + 1; if(lightLocks[devId][chNum] && (Date.now() - lightLocks[devId][chNum] < 2000)) return; lightStates[devId][chNum] = st; renderLightChannel(devId, chNum); }); } let lOnline = document.getElementById('dash-light-online'); if(lOnline) lOnline.innerText = onlineCount; renderDashboardLightCards(d); }); fetch('/api/light/logs').then(r=>r.json()).then(logs=>{ const logBox = document.getElementById('light-global-log'); if(!logBox) return; let html = ""; (logs||[]).forEach(log => { html += `<div class="log-item"><span class="time">[${new Date(log.time).toLocaleTimeString('zh-CN',{hour12:false})}]</span><span class="msg">${log.operation.replace(/\[.*?\]\s*/,'')}</span></div>`; }); if (logBox.innerHTML !== html) logBox.innerHTML = html; }); }

        // 服务器面板控制
        function getColor(p) { return p > 90 ? 'bg-red' : (p > 70 ? 'bg-yellow' : 'bg-green'); }
        function formatServerTime(value) {
            if(!value) return '未记录';
            const d = new Date(value);
            if (Number.isNaN(d.getTime())) return value;
            return d.toLocaleString('zh-CN', { hour12: false });
        }
        function formatServerClockOffset(value) {
            const offset = Number(value);
            if (!Number.isFinite(offset)) return '未获取';
            const abs = Math.abs(offset);
            if (abs < 1) return '正常';
            const prefix = offset > 0 ? '快' : '慢';
            if (abs >= 3600) return `${prefix}${(abs / 3600).toFixed(1)}小时`;
            if (abs >= 60) return `${prefix}${(abs / 60).toFixed(abs >= 600 ? 0 : 1)}分钟`;
            return `${prefix}${abs.toFixed(0)}秒`;
        }
        function getServerClockOffsetClass(value) {
            const offset = Math.abs(Number(value));
            if (!Number.isFinite(offset)) return ' clock-unknown';
            if (offset >= 300) return ' clock-bad';
            if (offset >= 120) return ' clock-warn';
            return ' clock-ok';
        }
        function wakeServer(mac) { if (!ensurePermission('server.control', '唤醒服务器节点')) return; if(mac.startsWith('TEMP')) { showToast('没有真实 MAC 地址，无法发送网络唤醒', true); return; } if(confirm('确定发送网络唤醒魔术包(WOL)吗？')) { fetch(`/api/wake/${mac}`, {method: 'POST'}).then(()=>showToast('唤醒包已发出')); } }
        function sendServerCmd(mac, cmd) { if (!ensurePermission('server.control', '下发服务器指令')) return; const actionMap = { shutdown: '关机', restart: '重启', refresh: '刷新信息' }; let actionName = actionMap[cmd] || cmd; const prompt = cmd === 'refresh' ? `确定要远程刷新此节点的硬件信息吗？` : `危险操作：确定要让此节点立刻【${actionName}】吗？`; if(confirm(prompt)) { fetch(`/api/machines/${mac}/command`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command: cmd}) }).then(() => showToast(`指令 [${actionName}] 已进入下发队列`)); } }
        function moveServer(mac, direction) { if (!ensurePermission('server.control', '调整服务器排序')) return; let idx = globalServerList.findIndex(m => m.mac === mac); if (idx < 0) return; let newIdx = idx + direction; if (newIdx < 0 || newIdx >= globalServerList.length) return; let temp = globalServerList[idx]; globalServerList[idx] = globalServerList[newIdx]; globalServerList[newIdx] = temp; globalServerList.forEach((m, i) => m.sort_order = i + 1); fetch('/api/machines/sort', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({macs: globalServerList.map(m => m.mac)}) }).then(() => updateServerData()); }
        function updateServerData() { fetch('/api/machines').then(r=>r.json()).then(data => { data.sort((a, b) => { if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order; return a.mac.localeCompare(b.mac); }); globalServerList = data; let sTotal = document.getElementById('dash-server-total'); if(sTotal) sTotal.innerText = data.length; let onlineCount = 0; let html = ''; data.forEach(m => { if (m.is_online) onlineCount++; let st = m.status || {}; let agent = m.agent_status || {}; let gpuHtml = ''; if(st.gpu_list && st.gpu_list.length > 0) { gpuHtml = `<div class="gpu-list">`; st.gpu_list.forEach(g => gpuHtml += `<div>GPU ${g.index}: ${g.name} - <span style="color:var(--text-main);">${g.util_percent}% / ${g.temp}°C</span></div>`); gpuHtml += `</div>`; } let agentTaskText = agent.task_exists ? `${agent.task_state || '未知'} / ${agent.task_user || 'SYSTEM'}` : '未安装'; let statusMetaHtml = `<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px;"><div style="background:rgba(0,0,0,0.15); border-radius:6px; padding:10px;"><div style="font-size:12px; color:var(--text-sub); margin-bottom:4px;">最近上报</div><div style="font-size:13px; color:var(--text-main);">${formatServerTime(m.last_online)}</div></div><div style="background:rgba(0,0,0,0.15); border-radius:6px; padding:10px;"><div style="font-size:12px; color:var(--text-sub); margin-bottom:4px;">硬件刷新</div><div style="font-size:13px; color:var(--text-main);">${formatServerTime(st.hardware_refreshed_at)}</div></div><div style="background:rgba(0,0,0,0.15); border-radius:6px; padding:10px;"><div style="font-size:12px; color:var(--text-sub); margin-bottom:4px;">代理状态</div><div style="font-size:13px; color:${agent.task_exists ? 'var(--success)' : 'var(--warning)'};">${agentTaskText}</div></div><div style="background:rgba(0,0,0,0.15); border-radius:6px; padding:10px;"><div style="font-size:12px; color:var(--text-sub); margin-bottom:4px;">当前接入</div><div style="font-size:13px; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${agent.current_server_url || ''}">${agent.current_server_url || '未获取'}</div></div></div>`; let metricsHtml = m.is_online ? `${statusMetaHtml}<div class="hardware-info"><div class="hardware-item" title="${st.cpu_name||'未获取到CPU'}">CPU: <span>${st.cpu_name||'加载中...'}</span></div><div class="hardware-item" title="${st.motherboard||'未获取到主板'}">主板: <span>${st.motherboard||'加载中...'}</span></div><div class="hardware-item">内存频率: <span>${st.mem_speed ? st.mem_speed + ' MHz' : '未获取到'}</span></div><div class="hardware-item">Agent版本: <span>${agent.version || '--'}</span></div></div><div class="metric-row"><div class="metric-label"><span>CPU使用率</span><span>${st.cpu_percent||0}%</span></div><div class="progress-track"><div class="progress-fill ${getColor(st.cpu_percent)}" style="width:${st.cpu_percent||0}%"></div></div></div><div class="metric-row"><div class="metric-label"><span>内存 (${st.mem_used||0}/${st.mem_total||0} GB)</span><span>${st.mem_percent||0}%</span></div><div class="progress-track"><div class="progress-fill bg-blue" style="width:${st.mem_percent||0}%"></div></div></div><div class="metric-row" style="margin-bottom:0;"><div class="metric-label"><span>系统盘 (C:)</span><span>${st.disk_percent||0}%</span></div><div class="progress-track"><div class="progress-fill ${getColor(st.disk_percent)}" style="width:${st.disk_percent||0}%"></div></div></div><div class="metric-row" style="margin-top:12px; margin-bottom:0;"><div class="metric-label"><span>网络流量 (上/下)</span><span><span style="color:var(--brand-blue)">↑ ${st.net_sent_kb_s||0}</span> / <span style="color:var(--success)">↓ ${st.net_recv_kb_s||0}</span> KB/s</span></div></div>${gpuHtml}` : `${statusMetaHtml}<div style="text-align:center; color:var(--text-sub); margin:20px 0;">该节点当前离线，等待自动重连上报。</div>`; let groupHtml = m.asset_group ? `<div style="margin-top:8px; font-size:12px; color:var(--brand-blue);">资产分组: ${m.asset_group}</div>` : ''; let remarkHtml = m.remark ? `<div style="margin-top:12px; font-size:12px; color:var(--text-sub); border-top:1px dashed rgba(255,255,255,0.1); padding-top:8px;">备注: ${m.remark}</div>` : ''; remarkHtml = groupHtml + remarkHtml; html += `<div class="server-card ${m.is_online ? 'online' : 'offline'} size-${m.card_size}"><div class="server-title">${m.custom_name || m.hostname || '未知节点'}<span class="tag ${m.is_online ? 'normal' : 'error'}">${m.is_online ? '运行中' : '已离线'}</span></div><div class="server-ip" title="${escapeHtml(getServerIdentityLine(m).title)}">${escapeHtml(getServerIdentityLine(m).text)}</div>${metricsHtml}${remarkHtml}<div style="margin-top:20px; border-top:1px solid var(--panel-border); padding-top:15px; display:flex; gap:8px; align-items:center;"><button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} title="上移" onclick="moveServer('${m.mac}', -1)">↑</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} title="下移" onclick="moveServer('${m.mac}', 1)">↓</button><div style="flex-grow:1;"></div><button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${m.mac}', 'refresh')">刷新信息</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" style="color:var(--warning); border-color:var(--warning);" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${m.mac}', 'restart')">硬重启</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" style="color:var(--danger); border-color:var(--danger);" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${m.mac}', 'shutdown')">强关机</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" style="color:var(--brand-blue); border-color:var(--brand-blue);" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="wakeServer('${m.mac}')">网络唤醒</button></div></div>`; }); let sOnline = document.getElementById('dash-server-online'); if(sOnline) sOnline.innerText = onlineCount; let sContainer = document.getElementById('server-grid-container'); if(sContainer) sContainer.innerHTML = html; }); }

        // 投影与泛型设备
        function fireUniversalCommand(devId, payload, format, wait_ms) { if (!ensurePermission('system.config', '控制泛型设备')) return; showToast("通用指令下发中...", false); fetch('/api/universal/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: devId, command: { payload: payload, format: format, wait_ms: wait_ms || 0 } }) }).then(r => r.json()).then(data => { if(data.success) { showToast("执行成功"); console.log("设备返回:", data.response); } else { showToast("执行失败: " + (data.response || data.msg || data.message || '未知错误'), true); } }).catch(e => showToast("网络请求错误", true)); }
        function handleLongPressStart(devId, startPayload, format) { fireUniversalCommand(devId, startPayload, format, 0); }
        function handleLongPressEnd(devId, stopPayload, format) { fireUniversalCommand(devId, stopPayload, format, 0); }
        function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])); }
        const projectorCommandNameFallbacks = {
            smile: {
                ek: {
                    power_on: '开机',
                    power_off: '关机',
                    source_pc: '切换到 PC',
                    source_vga: '切换到 VGA',
                    source_dvi: '切换到 DVI',
                    source_hdmi1: '切换到 HDMI1',
                    source_hdmi2: '切换到 HDMI2',
                    source_dp: '切换到 DP',
                    mute_on: '静音黑屏开启',
                    mute_off: '静音黑屏关闭',
                    freeze_on: '冻结画面开启',
                    freeze_off: '冻结画面关闭',
                    volume_up: '音量加',
                    volume_down: '音量减',
                    menu_on: '打开菜单',
                    menu_off: '关闭菜单',
                    key_up: '方向上',
                    key_down: '方向下',
                    key_left: '方向左',
                    key_right: '方向右',
                    key_enter: '确认',
                    key_exit: '返回',
                    auto_adjust: '自动调整',
                    lamp_eco: '灯泡节能模式',
                    lamp_normal: '灯泡标准模式',
                    power_status: '查询开关机状态',
                    source_status: '查询信号源',
                    volume_status: '查询音量',
                    mute_status: '查询静音黑屏状态',
                    temp_status: '查询温度状态',
                    lamp_status: '查询灯泡状态'
                }
            }
        };
        function looksLikeGarbledText(value) {
            const text = String(value ?? '').trim();
            if (!text) return true;
            return ['?', '锛', '馃', '篇胆赤', '狼双', '高桁', '寮€', '闂'].some(token => text.includes(token));
        }
        function normalizeProjectorCommand(proj, cmd) {
            const normalized = { ...(cmd || {}) };
            const brandId = String(proj?.brand_id || '').trim();
            const seriesId = String(proj?.series_id || '').trim();
            const fallbackName = projectorCommandNameFallbacks?.[brandId]?.[seriesId]?.[normalized.id];
            if (fallbackName && looksLikeGarbledText(normalized.name)) normalized.name = fallbackName;
            if (looksLikeGarbledText(normalized.icon)) normalized.icon = '';
            return normalized;
        }
        function getProjectorById(projId) { return projectorConfigs.find(item => String(item.id) === String(projId)); }
        function getProjectorCommands(proj) { return (proj?.commands || []).filter(cmd => cmd && cmd.visible !== false).map(cmd => normalizeProjectorCommand(proj, cmd)).sort((a, b) => (a.sort ?? 999) - (b.sort ?? 999)); }
        function findProjectorCommand(proj, ids, keywords=[]) {
            const commands = getProjectorCommands(proj);
            return commands.find(cmd => ids.includes(cmd.id)) || commands.find(cmd => keywords.some(keyword => String(cmd.name || '').includes(keyword)));
        }
        function getProjectorStatus(projId) {
            return projectorStatusCache[projId] || { online: false, power: 'unknown', temp: null, temp_status: null, lamp_hours: null, lamp_state: null, filter_hours: null, lamp_model: null, filter_model: null, source: null, source_code: null, source_name: null, av_mute: null, freeze_status: null, input_list: [], input_list_labels: [], input_resolution: null, recommended_resolution: null, error: null, error_code: null, error_details: null, device_name: null, manufacturer: null, product_name: null, class_version: null, serial_number: null, software_version: null };
        }
        function formatProjectorSourceText(status) {
            if (status.source_name) return status.source_name;
            if (status.source && status.source !== '查询不支持') return status.source;
            if (status.source === '查询不支持') return '当前源查询不支持';
            if (Array.isArray(status.input_list_labels) && status.input_list_labels.length) return `支持 ${status.input_list_labels.length} 路输入`;
            if (Array.isArray(status.input_list) && status.input_list.length) return `支持 ${status.input_list.length} 路输入`;
            return '未获取';
        }
        function formatProjectorModelText(proj, status) {
            return proj.fixed_model || status.product_name || status.device_name || (status.manufacturer && status.class_version ? `${status.manufacturer} / PJLink Class ${status.class_version}` : null) || status.manufacturer || proj.series_name || proj.model || '未识别型号';
        }
        function formatProjectorMuteText(status) {
            return status.av_mute || '未获取';
        }
        function formatProjectorManufacturerText(proj, status) {
            return proj.fixed_manufacturer || status.manufacturer || '--';
        }
        function formatProjectorSoftwareText(proj, status) {
            return proj.fixed_software_version || status.software_version || '--';
        }
        function formatProjectorErrorText(status) {
            const raw = status.error || '正常';
            if (raw === '正常' || raw === '预警' || raw === '故障') return raw;
            if (String(raw).includes('WinError 10061')) return '连接被拒绝';
            if (String(raw).includes('timed out')) return '连接超时';
            return String(raw).length > 18 ? `${String(raw).slice(0, 18)}...` : raw;
        }
        function formatProjectorClassText(proj, status) {
            if (status.class_version) return `Class ${status.class_version}（设备实测）`;
            if (proj.control_type === 'pjlink' && proj.pjlink_version) return `Class ${proj.pjlink_version}（配置值）`;
            return '--';
        }
        function formatProjectorProtocolText(proj, status) {
            const controlType = String(proj.control_type || '');
            if (controlType === 'pjlink') {
                return status.class_version ? `PJLink Class ${status.class_version}` : (proj.pjlink_version ? `PJLink ${proj.pjlink_version}.0` : 'PJLink');
            }
            if (controlType.startsWith('smile_ek') || controlType === 'rs232') {
                return controlType.includes('_com') || controlType === 'rs232' ? '视美乐专用协议 / RS232' : '视美乐专用协议 / TCP';
            }
            if (controlType.startsWith('appotronics_')) {
                return '厂商专用协议';
            }
            return proj.pjlink_version ? `PJLink ${proj.pjlink_version}.0` : '--';
        }
        function getProjectorPowerText(powerStatus) {
            if (powerStatus === 'on') return '开机';
            if (powerStatus === 'off') return '关机';
            if (powerStatus === 'cooling') return '冷却中';
            if (powerStatus === 'warming') return '启动中';
            if (powerStatus === 'warning') return '告警';
            return '未知';
        }
        function getProjectorPowerColor(powerStatus) {
            if (powerStatus === 'on') return 'var(--success)';
            if (powerStatus === 'off') return 'var(--danger)';
            if (powerStatus === 'cooling' || powerStatus === 'warming' || powerStatus === 'warning') return 'var(--warning)';
            return '#94a3b8';
        }
        function getProjectorPowerButtonClass(isOnline, powerStatus) {
            if (!isOnline || powerStatus === 'unknown') return 'unknown';
            if (powerStatus === 'off') return 'off';
            if (powerStatus === 'cooling' || powerStatus === 'warming' || powerStatus === 'warning') return 'unknown';
            return 'on';
        }
        function getProjectorPowerButtonTitle(isOnline, powerStatus) {
            if (!isOnline) return '设备离线';
            if (powerStatus === 'on' || powerStatus === 'warming') return '当前开机，点击关机';
            if (powerStatus === 'off' || powerStatus === 'cooling') return '当前关机，点击开机';
            return '打开遥控器或刷新状态';
        }
        function getProjectorButtonHint(cmd) {
            const name = String(cmd?.name || '');
            if (name.includes('查询')) return '点击查询设备状态';
            if (name.includes('切换')) return '点击执行切换';
            if (name.includes('开启')) return '点击开启功能';
            if (name.includes('关闭')) return '点击关闭功能';
            if (name.includes('开机')) return '点击下发开机';
            if (name.includes('关机')) return '点击下发关机';
            return '点击执行指令';
        }
        function getProjectorIconHtml(kind) {
            const icon = String(kind || '').trim().toLowerCase();
            if (icon === 'power') {
                return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 4.2v7.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
                    <path d="M7.4 6.5A8 8 0 1 0 16.6 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
                </svg>`;
            }
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect x="4" y="5" width="16" height="14" rx="2.5" stroke="currentColor" stroke-width="1.9"/>
                <path d="M8.5 9h7M8.5 12h7M8.5 15h7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
            </svg>`;
        }
        function groupProjectorCommands(proj) {
            const groups = { power: [], input: [], av: [], info: [], other: [] };
            getProjectorCommands(proj).forEach(cmd => {
                const id = String(cmd.id || '');
                const name = String(cmd.name || '');
                if (id.includes('power') || name.includes('开机') || name.includes('关机') || name.includes('电源')) groups.power.push(cmd);
                else if (id.includes('input') || name.includes('信号源') || name.includes('切换')) groups.input.push(cmd);
                else if (id.includes('mute') || id.includes('freeze') || name.includes('静音') || name.includes('冻结')) groups.av.push(cmd);
                else if (name.includes('查询') || id.includes('status') || id.includes('info') || id.includes('name') || id.includes('manufacturer') || id.includes('product') || id.includes('lamp') || id.includes('error')) groups.info.push(cmd);
                else groups.other.push(cmd);
            });
            return groups;
        }
        function renderProjectorCommandButtons(commands, projId) {
            if (!commands.length) return '<div class="projector-empty-tip">当前分组没有可用指令。</div>';
            return `<div class="projector-remote-grid">${commands.map(cmd => `
                <button class="projector-command-btn${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} onclick="fireProjectorCommand('${escapeHtml(projId)}', '${escapeHtml(cmd.payload || '')}', '${escapeHtml(cmd.format || 'str')}')">
                    <span class="name">${escapeHtml(cmd.name || cmd.id || '未命名指令')}</span>
                    <span class="hint">${escapeHtml(getProjectorButtonHint(cmd))}</span>
                </button>`).join('')}</div>`;
        }
        function isInferredProjector(proj, status) {
            return String(proj?.control_type || '') === 'inferred_rs232' || status?.inferred === true;
        }
        function formatProjectorKw(value) {
            if (value === null || value === undefined || value === '') return '--';
            const n = Number(value);
            if (!Number.isFinite(n)) return '--';
            return `${n.toFixed(2)} kW`;
        }
        function formatProjectorSignedKw(value) {
            if (value === null || value === undefined || value === '') return '--';
            const n = Number(value);
            if (!Number.isFinite(n)) return '--';
            return `${n >= 0 ? '+' : ''}${n.toFixed(2)} kW`;
        }
        function formatInferredFeedText(status) {
            if (status?.power_feed_on === true) return '供电合闸';
            if (status?.power_feed_on === false) return '供电断开';
            return '供电未知';
        }
        function renderInferredTargetSummary(status) {
            const targets = Array.isArray(status?.inferred_targets) ? status.inferred_targets : [];
            if (!targets.length) return '--';
            return targets.map((target, idx) => `控制点${idx + 1}${target.online ? '在线' : '离线'}`).join(' / ');
        }
        function renderInferredProjectorPowerActions(proj, powerOnCmd, powerOffCmd, compact=false) {
            const disabledClass = getPermissionDisabledClass('projector.control');
            const disabledAttrs = getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限');
            const buttonClass = compact ? 'projector-inline-power-btn compact' : 'projector-inline-power-btn';
            if (!powerOnCmd && !powerOffCmd) {
                return `<button class="projector-inline-power-btn muted ${compact ? 'compact' : ''}" type="button" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">遥控器</button>`;
            }
            return `
                <div class="projector-inline-power-actions ${compact ? 'compact' : ''}">
                    ${powerOnCmd ? `<button class="${buttonClass} on${disabledClass}" ${disabledAttrs} type="button" title="通过121投影网关开机" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOnCmd.payload || '')}', '${escapeHtml(powerOnCmd.format || 'str')}', '${escapeHtml(powerOnCmd.name || '开机')}')">开机</button>` : ''}
                    ${powerOffCmd ? `<button class="${buttonClass} off${disabledClass}" ${disabledAttrs} type="button" title="通过121投影网关关机" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOffCmd.payload || '')}', '${escapeHtml(powerOffCmd.format || 'str')}', '${escapeHtml(powerOffCmd.name || '关机')}')">关机</button>` : ''}
                </div>`;
        }
        function renderInferredProjectorCard(proj) {
            const status = getProjectorStatus(proj.id);
            const statusMeta = getDeviceStatusMeta(status, { staleText: '待确认', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const powerStatus = status.power || 'unknown';
            const powerText = getProjectorPowerText(powerStatus);
            const powerColor = getProjectorPowerColor(powerStatus);
            const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
            const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
            const targetTotal = Number(status.target_total_count ?? 0);
            const targetOnline = Number(status.target_online_count ?? 0);
            const targetSummary = targetTotal ? `${targetOnline}/${targetTotal} 在线` : '未配置目标';
            const projectorNote = status.inference_basis || status.status_note || statusMeta.note;
            const lastIntentText = status.last_intent === 'on' ? '最近开机' : (status.last_intent === 'off' ? '最近关机' : '无指令记录');
            const gatewayText = status.last_command_source ? '121网关' : '串口 + 电柜';
            return `
                <div class="projector-card ${isOnline ? 'online' : 'offline'} ${getCardStateClass(statusMeta)}">
                    <div class="projector-card-top">
                        <div>
                            <div class="projector-card-title">${escapeHtml(proj.name || proj.id)}</div>
                            <div class="projector-card-subtitle">三区域组控 · ${escapeHtml(targetSummary)} · ${escapeHtml(formatInferredFeedText(status))}</div>
                        </div>
                        <button class="projector-entry-btn" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    </div>
                    <div class="projector-status-inline">
                        <div class="projector-status-left">
                            <span class="projector-dot ${statusMeta.chipClass === 'online' ? 'online' : ''} ${statusMeta.chipClass === 'warning' ? 'warning' : ''}"></span>
                            <span>${escapeHtml(statusMeta.text)}</span>
                            <span>·</span>
                            <span style="color:${powerColor}; font-weight:700;">推断 ${escapeHtml(powerText)}</span>
                        </div>
                        <div class="projector-status-actions">
                            ${renderInferredProjectorPowerActions(proj, powerOnCmd, powerOffCmd)}
                        </div>
                    </div>
                    <div class="projector-meta-grid">
                        <div class="projector-meta-item"><div class="projector-meta-label">串口服务器</div><div class="projector-meta-value">${escapeHtml(targetSummary)}</div></div>
                        <div class="projector-meta-item"><div class="projector-meta-label">供电状态</div><div class="projector-meta-value">${escapeHtml(formatInferredFeedText(status))}</div></div>
                        <div class="projector-meta-item"><div class="projector-meta-label">电柜总功率</div><div class="projector-meta-value">${escapeHtml(formatProjectorKw(status.meter_power_kw))}</div></div>
                        <div class="projector-meta-item"><div class="projector-meta-label">功率变化</div><div class="projector-meta-value">${escapeHtml(formatProjectorSignedKw(status.power_delta_kw))}</div></div>
                    </div>
                    <div class="projector-extra-row">
                        <div class="projector-extra-chip"><div class="label">控制记录</div><div class="value">${escapeHtml(lastIntentText)}</div></div>
                        <div class="projector-extra-chip"><div class="label">状态来源</div><div class="value">${escapeHtml(gatewayText)}</div></div>
                        <div class="projector-extra-chip"><div class="label">控制点</div><div class="value" title="${escapeHtml(renderInferredTargetSummary(status))}">${escapeHtml(renderInferredTargetSummary(status))}</div></div>
                    </div>
                    <div class="dashboard-mini-note">${escapeHtml(projectorNote)}</div>
                </div>`;
        }
        function renderCompactInferredProjectorCard(proj) {
            const status = getProjectorStatus(proj.id);
            const statusMeta = getDeviceStatusMeta(status, { staleText: '待确认', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const powerStatus = status.power || 'unknown';
            const powerText = getProjectorPowerText(powerStatus);
            const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
            const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
            const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
            const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
            const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
            const targetTotal = Number(status.target_total_count ?? 0);
            const targetOnline = Number(status.target_online_count ?? 0);
            const targetSummary = targetTotal ? `串口 ${targetOnline}/${targetTotal}` : '串口未配置';
            return `<div class="dashboard-mini-card projector-compact-card ${getCardStateClass(statusMeta)}">
                <div class="dashboard-mini-projector-head">
                    <div class="dashboard-mini-projector-title">
                        <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                        <div class="dashboard-mini-subtitle">${escapeHtml(targetSummary)} · ${escapeHtml(formatInferredFeedText(status))}</div>
                    </div>
                    <div class="dashboard-mini-projector-controls">
                        <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                        ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}', '${escapeHtml(powerButtonCmd.name || '')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                    </div>
                </div>
                <div class="dashboard-mini-light-summary">
                    <div class="dashboard-mini-light-count">${escapeHtml(powerText)}</div>
                    <div class="dashboard-mini-chip-row"><span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span></div>
                </div>
                <div class="dashboard-mini-note">${escapeHtml(status.inference_basis || status.status_note || statusMeta.note)}</div>
            </div>`;
        }
        function renderProjectorCard(proj, scope) {
            const status = getProjectorStatus(proj.id);
            if (isInferredProjector(proj, status)) return renderInferredProjectorCard(proj);
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const powerStatus = status.power || 'unknown';
            const powerText = getProjectorPowerText(powerStatus);
            const powerColor = getProjectorPowerColor(powerStatus);
            const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
            const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
            const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
            const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
            const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
            const modelText = formatProjectorModelText(proj, status);
            const manufacturerText = formatProjectorManufacturerText(proj, status);
            const softwareText = formatProjectorSoftwareText(proj, status);
            const sourceText = formatProjectorSourceText(status);
            const lampText = status.lamp_hours !== null && status.lamp_hours !== undefined ? `${status.lamp_hours} h` : '--';
            const errorText = formatProjectorErrorText(status);
            const tempDisplayText = status.temp !== null && status.temp !== undefined ? `${status.temp}°C` : (status.temp_status || '--');
            const tempLabel = status.temp !== null && status.temp !== undefined ? '温度' : '温度状态';
            const tempColor = status.temp !== null && status.temp !== undefined ? (status.temp > 60 ? 'var(--danger)' : 'var(--text-main)') : (status.temp_status === '故障' ? 'var(--danger)' : (status.temp_status === '预警' ? 'var(--warning)' : 'var(--text-main)'));
            const onlineText = statusMeta.text;
            const filterHoursText = status.filter_hours !== null && status.filter_hours !== undefined ? `${status.filter_hours} h` : '--';
            const recommendedResolutionText = status.recommended_resolution && status.recommended_resolution !== 'NA' ? status.recommended_resolution : '不适用';
            const lampStateText = status.lamp_state || '--';
            const supportText = Array.isArray(status.input_list_labels) && status.input_list_labels.length ? status.input_list_labels.join(' / ') : (Array.isArray(status.input_list) && status.input_list.length ? status.input_list.join(' / ') : '--');
            const supportCountText = Array.isArray(status.input_list_labels) && status.input_list_labels.length ? `${status.input_list_labels.length} 路` : (Array.isArray(status.input_list) && status.input_list.length ? `${status.input_list.length} 路` : '--');
            const classText = formatProjectorProtocolText(proj, status);
            const classVersionText = formatProjectorClassText(proj, status);
            const errorDetailLabels = { fan: '风扇', lamp: '灯泡', temperature: '温度', cover: '机盖', filter: '滤网', other: '其他' };
            const alertChips = Object.entries(status.error_details || {}).filter(([, value]) => value === '预警' || value === '故障').map(([key, value]) => {
                const chipClass = value === '故障' ? 'error' : 'warning';
                const label = errorDetailLabels[key] || key;
                return `<span class="projector-alert-chip ${chipClass}">${escapeHtml(label)}${escapeHtml(value)}</span>`;
            }).join('');
            return `
                <div class="projector-card ${isOnline ? 'online' : 'offline'} ${getCardStateClass(statusMeta)}">
                    <div class="projector-card-top">
                        <div>
                            <div class="projector-card-title">${escapeHtml(proj.name || proj.id)}</div>
                            <div class="projector-card-subtitle">${escapeHtml(proj.ip || '--')}:${escapeHtml(proj.port || '--')} · ${escapeHtml(modelText)}</div>
                        </div>
                        <button class="projector-entry-btn" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                    </div>
                    <div class="projector-status-inline">
                        <div class="projector-status-left">
                            <span class="projector-dot ${statusMeta.chipClass === 'online' ? 'online' : ''} ${statusMeta.chipClass === 'warning' ? 'warning' : ''}"></span>
                            <span>${onlineText}</span>
                            <span>·</span>
                            <span style="color:${powerColor}; font-weight:700;">电源 ${powerText}</span>
                        </div>
                        <div class="projector-status-actions">
                            ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}" title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                        </div>
                    </div>
                    <div class="projector-meta-grid">
                        <div class="projector-meta-item">
                            <div class="projector-meta-label">当前信号源</div>
                            <div class="projector-meta-value">${escapeHtml(sourceText)}</div>
                        </div>
                        <div class="projector-meta-item">
                            <div class="projector-meta-label">灯泡时长</div>
                            <div class="projector-meta-value">${escapeHtml(lampText)}</div>
                        </div>
                        <div class="projector-meta-item">
                            <div class="projector-meta-label">${tempLabel}</div>
                            <div class="projector-meta-value" style="color:${tempColor}">${escapeHtml(tempDisplayText)}</div>
                        </div>
                        <div class="projector-meta-item">
                            <div class="projector-meta-label">故障总览</div>
                            <div class="projector-meta-value" style="color:${errorText === '正常' ? 'var(--success)' : 'var(--warning)'}">${escapeHtml(errorText)}</div>
                        </div>
                    </div>
                    <div class="projector-extra-row">
                        <div class="projector-extra-chip">
                            <div class="label">厂家信息</div>
                            <div class="value">${escapeHtml(manufacturerText)}</div>
                        </div>
                        <div class="projector-extra-chip">
                            <div class="label">协议等级</div>
                            <div class="value">${escapeHtml(classVersionText)}</div>
                        </div>
                        <div class="projector-extra-chip">
                            <div class="label">软件版本</div>
                            <div class="value">${escapeHtml(softwareText)}</div>
                        </div>
                    </div>
                    <div class="dashboard-mini-note">${escapeHtml(statusMeta.note)}</div>
                    ${alertChips ? `<div class="projector-alert-list">${alertChips}</div>` : ''}
                    <div class="projector-card-footer">
                        <div class="projector-footer-chip">
                            <div class="label">静音状态</div>
                            <div class="value">${escapeHtml(formatProjectorMuteText(status))}</div>
                        </div>
                        <div class="projector-footer-chip">
                            <div class="label">灯泡状态</div>
                            <div class="value">${escapeHtml(lampStateText)}</div>
                        </div>
                        <div class="projector-footer-chip">
                            <div class="label">支持输入</div>
                            <div class="value" title="${escapeHtml(supportText)}">${escapeHtml(supportCountText)}</div>
                        </div>
                    </div>
                </div>`;
        }
        function renderCompactProjectorCard(proj) {
            const status = getProjectorStatus(proj.id);
            if (isInferredProjector(proj, status)) return renderCompactInferredProjectorCard(proj);
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const powerStatus = status.power || 'unknown';
            const powerText = getProjectorPowerText(powerStatus);
            const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
            const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
            const powerButtonCmd = (powerStatus === 'on' || powerStatus === 'warming') ? powerOffCmd : powerOnCmd;
            const powerButtonClass = getProjectorPowerButtonClass(isOnline, powerStatus);
            const powerButtonTitle = getProjectorPowerButtonTitle(isOnline, powerStatus);
            return `<div class="dashboard-mini-card projector-compact-card ${getCardStateClass(statusMeta)}">
                <div class="dashboard-mini-projector-head">
                    <div class="dashboard-mini-projector-title">
                        <div class="dashboard-mini-title">${escapeHtml(proj.name || proj.id)}</div>
                        <div class="dashboard-mini-subtitle">${escapeHtml(proj.ip || '--')}:${escapeHtml(proj.port || '--')}</div>
                    </div>
                    <div class="dashboard-mini-projector-controls">
                        <button class="dashboard-mini-projector-entry" type="button" title="打开遥控器面板" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('remote')}</button>
                        ${powerButtonCmd ? `<button class="projector-power-key ${powerButtonClass}${getPermissionDisabledClass('projector.control')}" ${getPermissionDisabledAttrs('projector.control', '当前账号无投影机控制权限')} title="${escapeHtml(powerButtonTitle)}" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerButtonCmd.payload || '')}', '${escapeHtml(powerButtonCmd.format || 'str')}')">${getProjectorIconHtml('power')}</button>` : `<button class="projector-power-key ${powerButtonClass}" title="打开遥控器" onclick="openProjectorRemote('${escapeHtml(proj.id)}')">${getProjectorIconHtml('power')}</button>`}
                    </div>
                </div>
                <div class="dashboard-mini-light-summary">
                    <div class="dashboard-mini-light-count">${escapeHtml(powerText)}</div>
                    <div class="dashboard-mini-chip-row"><span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span></div>
                </div>
                <div class="dashboard-mini-note">更新 ${escapeHtml(status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--:--:--')}</div>
            </div>`;
        }
        function renderProjectorCards(targetId, scope) {
            const container = document.getElementById(targetId);
            if (!container) return;
            if (!projectorConfigs.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置投影机，请前往系统配置添加。</div>';
                return;
            }
            container.innerHTML = projectorConfigs.map(proj => scope === 'dashboard' ? renderCompactProjectorCard(proj) : renderProjectorCard(proj, scope)).join('');
        }
        function openProjectorRemote(projId) {
            currentProjectorRemoteId = String(projId);
            document.getElementById('projectorRemoteModal').style.display = 'block';
            renderProjectorRemote(currentProjectorRemoteId);
        }
        function closeProjectorRemote() {
            document.getElementById('projectorRemoteModal').style.display = 'none';
            currentProjectorRemoteId = null;
        }
        function renderProjectorRemote(projId) {
            const proj = getProjectorById(projId);
            const content = document.getElementById('projectorRemoteContent');
            if (!proj || !content) return;
            const status = getProjectorStatus(proj.id);
            const groups = groupProjectorCommands(proj);
            const powerStatus = status.power || 'unknown';
            const manufacturerText = formatProjectorManufacturerText(proj, status);
            const softwareText = formatProjectorSoftwareText(proj, status);
            const powerOnCmd = findProjectorCommand(proj, ['power_on'], ['开机']);
            const powerOffCmd = findProjectorCommand(proj, ['power_off'], ['关机']);
            const errorDetails = status.error_details || {};
            const errorDetailItems = [
                { key: 'fan', label: '风扇' },
                { key: 'lamp', label: '灯泡' },
                { key: 'temperature', label: '温度' },
                { key: 'cover', label: '机盖' },
                { key: 'filter', label: '滤网' },
                { key: 'other', label: '其他' }
            ];
            const errorDetailsHtml = errorDetailItems.map(item => {
                const value = errorDetails[item.key] || '--';
                const color = value === '故障' ? 'var(--danger)' : (value === '预警' ? 'var(--warning)' : 'var(--text-main)');
                return `<div class="projector-remote-tile"><div class="label">${item.label}状态</div><div class="value" style="color:${color}">${escapeHtml(value)}</div></div>`;
            }).join('');
            const class2InfoHtml = [
                { label: '设备名称', value: status.device_name || '--' },
                { label: '厂商名称', value: status.manufacturer || '--' },
                { label: '产品型号', value: status.product_name || '--' },
                { label: '输入名称', value: formatProjectorSourceText(status) },
                { label: '当前分辨率', value: status.input_resolution || '--' },
                { label: '推荐分辨率', value: status.recommended_resolution && status.recommended_resolution !== 'NA' ? status.recommended_resolution : '不适用' },
                { label: '滤网时长', value: status.filter_hours !== null && status.filter_hours !== undefined ? `${status.filter_hours} h` : '--' },
                { label: '灯泡型号', value: status.lamp_model || '--' },
                { label: '滤网型号', value: status.filter_model || '--' },
                { label: '冻结状态', value: status.freeze_status || '--' },
                { label: '序列号', value: status.serial_number || '--' },
                { label: '软件版本', value: status.software_version || '--' }
            ].map(item => `<div class="projector-remote-tile"><div class="label">${item.label}</div><div class="value">${escapeHtml(item.value)}</div></div>`).join('');
            document.getElementById('projectorRemoteTitle').innerText = `${proj.name || proj.id} 遥控器`;
            document.getElementById('projectorRemoteSubtitle').innerText = `${proj.ip || '--'}:${proj.port || '--'} · ${formatProjectorModelText(proj, status)}`;
            content.innerHTML = `
                <div class="projector-remote-side">
                    <div class="projector-remote-overview">
                        <div class="projector-remote-tile"><div class="label">在线状态</div><div class="value" style="color:${status.online ? 'var(--success)' : 'var(--text-sub)'}">${status.online ? '在线' : '离线'}</div></div>
                        <div class="projector-remote-tile"><div class="label">电源状态</div><div class="value" style="color:${getProjectorPowerColor(powerStatus)}">${getProjectorPowerText(powerStatus)}</div></div>
                        <div class="projector-remote-tile"><div class="label">信号源</div><div class="value">${escapeHtml(formatProjectorSourceText(status))}</div></div>
                        <div class="projector-remote-tile"><div class="label">静音/黑屏</div><div class="value">${escapeHtml(formatProjectorMuteText(status))}</div></div>
                        <div class="projector-remote-tile"><div class="label">灯泡时长</div><div class="value">${escapeHtml(status.lamp_hours !== null && status.lamp_hours !== undefined ? status.lamp_hours + ' h' : '--')}</div></div>
                        <div class="projector-remote-tile"><div class="label">灯泡状态</div><div class="value">${escapeHtml(status.lamp_state || '--')}</div></div>
                        <div class="projector-remote-tile"><div class="label">${status.temp !== null && status.temp !== undefined ? '温度' : '温度状态'}</div><div class="value" style="color:${status.temp !== null && status.temp !== undefined ? (status.temp > 60 ? 'var(--danger)' : 'var(--text-main)') : (status.temp_status === '故障' ? 'var(--danger)' : (status.temp_status === '预警' ? 'var(--warning)' : 'var(--text-main)'))}">${escapeHtml(status.temp !== null && status.temp !== undefined ? (status.temp + '°C') : (status.temp_status || '--'))}</div></div>
                        <div class="projector-remote-tile"><div class="label">故障总览</div><div class="value" style="color:${status.error && status.error !== '正常' ? 'var(--warning)' : 'var(--success)'}">${escapeHtml(status.error || '正常')}</div></div>
                        ${status.error_code ? `<div class="projector-remote-tile"><div class="label">ERST 原始码</div><div class="value">${escapeHtml(status.error_code)}</div></div>` : ''}
                        <div class="projector-remote-tile"><div class="label">厂商 / 协议</div><div class="value">${escapeHtml(manufacturerText + ' / ' + formatProjectorProtocolText(proj, status))}</div></div>
                        <div class="projector-remote-tile"><div class="label">PJLink 等级</div><div class="value">${escapeHtml(formatProjectorClassText(proj, status))}</div></div>
                        ${status.other_info ? `<div class="projector-remote-tile"><div class="label">附加信息</div><div class="value">${escapeHtml(status.other_info)}</div></div>` : ''}
                        <div class="projector-remote-tile"><div class="label">支持输入</div><div class="value">${escapeHtml(Array.isArray(status.input_list_labels) && status.input_list_labels.length ? status.input_list_labels.join(' / ') : (Array.isArray(status.input_list) && status.input_list.length ? status.input_list.join(' / ') : '--'))}</div></div>
                        <div class="projector-remote-tile"><div class="label">软件版本</div><div class="value">${escapeHtml(softwareText)}</div></div>
                    </div>
                    <div class="projector-remote-hero-actions">
                        ${powerOnCmd ? `<button class="projector-power-btn on" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOnCmd.payload || '')}', '${escapeHtml(powerOnCmd.format || 'str')}')">开机</button>` : ''}
                        ${powerOffCmd ? `<button class="projector-power-btn off" onclick="fireProjectorCommand('${escapeHtml(proj.id)}', '${escapeHtml(powerOffCmd.payload || '')}', '${escapeHtml(powerOffCmd.format || 'str')}')">关机</button>` : ''}
                    </div>
                </div>
                <div class="projector-remote-main">
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>电源与基础控制</span><span class="projector-remote-section-note">常用开关机、状态查询</span></div>
                        ${renderProjectorCommandButtons(groups.power, proj.id)}
                    </div>
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>信号源切换</span><span class="projector-remote-section-note">HDMI、RGB、VIDEO 等输入选择</span></div>
                        ${renderProjectorCommandButtons(groups.input, proj.id)}
                    </div>
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>画面与音视频控制</span><span class="projector-remote-section-note">静音黑屏、冻结等控制</span></div>
                        ${renderProjectorCommandButtons(groups.av, proj.id)}
                    </div>
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>信息与状态查询</span><span class="projector-remote-section-note">查询设备名称、故障、灯泡、协议信息</span></div>
                        ${renderProjectorCommandButtons(groups.info, proj.id)}
                    </div>
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>故障明细</span><span class="projector-remote-section-note">PJLink ERST 六项状态拆解</span></div>
                        <div class="projector-remote-grid">${errorDetailsHtml}</div>
                    </div>
                    <div class="projector-remote-section">
                        <div class="projector-remote-section-title"><span>PJLink Class 2 信息</span><span class="projector-remote-section-note">分辨率、滤网、型号、版本等扩展信息</span></div>
                        <div class="projector-remote-grid">${class2InfoHtml}</div>
                    </div>
                    <div class="projector-remote-section" style="margin-bottom:0;">
                        <div class="projector-remote-section-title"><span>其它指令</span><span class="projector-remote-section-note">保留扩展控制命令</span></div>
                        ${renderProjectorCommandButtons(groups.other, proj.id)}
                    </div>
                </div>`;
        }
        
        function refreshProjectorStatusAfterCommand() {
            updateProjectorStatus();
            [700, 1800, 4200].forEach(delay => setTimeout(updateProjectorStatus, delay));
        }

        function fireProjectorCommand(devId, payload, format, name='') {
            if (!ensurePermission('projector.control', '操作投影机')) return;
            showToast("投影指令下发中...", false);
            fetch('/api/projector/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: devId, command: { payload: payload, format: format, name: name } }) })
                .then(r => r.json())
                .then(data => {
                    showToast(data.success ? "执行成功" : ("执行失败: " + (data.response || '未知错误')), !data.success);
                    if (data.success) refreshProjectorStatusAfterCommand();
                })
                .catch(() => showToast("网络请求失败", true));
        }
        
        function fireScreenCommand(screenId, payload, format, action) {
            if (!ensurePermission('screen.control', '操作幕布')) return;
            showToast("幕布指令下发中...", false);
            fetch('/api/screen/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    screen_id: screenId,
                    command: { payload: payload, format: format, action: action }
                })
            }).then(r => r.json()).then(data => {
                showToast(data.success ? "执行成功" : ("执行失败: " + (data.response || '未知错误')), !data.success);
                if(data.success) {
                    setTimeout(updateScreenStatus, 120);
                }
            });
        }

        function getScreenCommand(screen, action) {
            return (screen.commands || []).find(cmd => String(cmd.action || '').toLowerCase() === action) || null;
        }
        function getScreenActionText(status) {
            if (!status || status.online === false) return '离线';
            if (status.is_moving) return status.action === 'up' ? '正在上升...' : '正在下降...';
            return '已停止';
        }
        function getScreenActionColor(status) {
            if (!status || status.online === false) return '#94a3b8';
            if (status.is_moving) return 'var(--warning)';
            return 'var(--text-sub)';
        }
        function renderScreenControlButton(screen, action, label, className) {
            const cmd = getScreenCommand(screen, action);
            const iconMap = { up: '↑', stop: '■', down: '↓' };
            const icon = iconMap[action] || '•';
            if (!cmd) {
                return `<button class="screen-control-btn ${className}" disabled title="未配置${label}指令"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
            }
            return `<button class="screen-control-btn ${className}${getPermissionDisabledClass('screen.control')}" ${getPermissionDisabledAttrs('screen.control', '当前账号无幕布控制权限')} title="${label}" onclick="fireScreenCommand('${escapeHtml(screen.id)}', '${escapeHtml(cmd.payload || '')}', '${escapeHtml(cmd.format || 'hex')}', '${escapeHtml(cmd.action || action)}')"><span class="btn-icon">${icon}</span><span class="btn-text">${label}</span></button>`;
        }
        function buildScreenEnvCards() {
            const cards = [];
            if (Array.isArray(envConfigs) && envConfigs.length) {
                const onlineEnv = envConfigs.map(cfg => ({ cfg, st: window.__envStatusCache?.[cfg.id] || {} })).find(item => item.st && item.st.online);
                const fallbackEnv = envConfigs[0] ? { cfg: envConfigs[0], st: window.__envStatusCache?.[envConfigs[0].id] || {} } : null;
                const envItem = onlineEnv || fallbackEnv;
                if (envItem) {
                    const cfg = envItem.cfg;
                    const st = envItem.st || {};
                    const online = !!st.online;
                    const temp = st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--';
                    const hum = st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--';
                    const lux = st.lux !== null && st.lux !== undefined ? `${st.lux} Lux` : '--';
                    const tempIcon = `<span class="screen-companion-metric-icon temp"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0v7.2a4.5 4.5 0 1 1-4 0V5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 14V8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.8" fill="currentColor"/></svg></span>`;
                    const humIcon = `<span class="screen-companion-metric-icon hum"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.8C9.4 7.2 6 10.4 6 14.2A6 6 0 0 0 18 14.2c0-3.8-3.4-7-6-10.4Z" fill="currentColor" fill-opacity="0.92"/><path d="M9.6 15.4c.5 1.4 1.6 2.2 3 2.5" stroke="#dbeafe" stroke-width="1.4" stroke-linecap="round"/></svg></span>`;
                    const luxIcon = `<span class="screen-companion-metric-icon lux"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.8v2.3M12 18.9v2.3M21.2 12h-2.3M5.1 12H2.8M18.6 5.4l-1.6 1.6M7 17l-1.6 1.6M18.6 18.6 17 17M7 7 5.4 5.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></span>`;
                    cards.push(`<div class="screen-companion-card screen-companion-env">
                        <div class="screen-companion-title">
                            <span>${escapeHtml(cfg.name || cfg.id)}</span>
                            <span class="screen-companion-tag" style="${online ? '' : 'color:#cbd5e1;background:rgba(100,116,139,0.16);border-color:rgba(148,163,184,0.18);'}">${online ? '在线' : '离线'}</span>
                        </div>
                        <div class="screen-companion-metrics">
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${tempIcon}<div class="label">温度</div></div>
                                <div class="value">${escapeHtml(temp)}</div>
                            </div>
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${humIcon}<div class="label">湿度</div></div>
                                <div class="value">${escapeHtml(hum)}</div>
                            </div>
                            <div class="screen-companion-metric">
                                <div class="metric-label-wrap">${luxIcon}<div class="label">光照</div></div>
                                <div class="value">${escapeHtml(lux)}</div>
                            </div>
                        </div>
                        <div class="screen-companion-footer">
                            <span>来源 ${escapeHtml(cfg.name || cfg.id)}</span>
                            <span>${online ? '实时采集' : '等待恢复'}</span>
                        </div>
                    </div>`);
                }
            }
            if (!cards.length) {
                cards.push(`<div class="screen-companion-card screen-placeholder-card">
                    <div class="screen-companion-title">
                        <span class="screen-placeholder-icon">+</span>
                        <span>环境摘要</span>
                    </div>
                    <div class="screen-companion-note">这里显示环境传感器的温度、湿度和光照摘要。</div>
                </div>`);
            }
            return cards.join('');
        }
        function buildScreenUpsCards() {
            const cards = [];
            if (Array.isArray(upsConfigs) && upsConfigs.length) {
                upsConfigs
                    .filter(cfg => cfg.visible !== false)
                    .slice(0, 1)
                    .forEach(cfg => {
                        cards.push(renderUpsCompanionCard(cfg, upsStatusCache[cfg.id] || {}));
                    });
            }
            if (!cards.length) {
                cards.push(`<div class="screen-companion-card screen-placeholder-card">
                    <div class="screen-companion-title">
                        <span class="screen-placeholder-icon">+</span>
                        <span>UPS 摘要</span>
                    </div>
                    <div class="screen-companion-note">这里显示 UPS 运行状态、电池和告警摘要。</div>
                </div>`);
            }
            return cards.join('');
        }
        function buildScreenAutomationCards() {
            return `<div class="dash-stat-card outdoor-automation-card" id="dash-outdoor-automation-card">
                <div class="outdoor-auto-head">
                    <div class="outdoor-auto-title">户外灯自动化</div>
                    <span class="outdoor-auto-chip" id="dash-outdoor-auto-chip">等待状态</span>
                </div>
                <div class="outdoor-auto-main">
                    <div class="outdoor-auto-kpi">
                        <div class="value" id="dash-outdoor-lux">--</div>
                        <div class="sub" id="dash-outdoor-status-text">正在等待光照与自动化状态...</div>
                    </div>
                    <div class="outdoor-auto-metrics">
                        <div class="outdoor-auto-metric">
                            <div class="label">开灯窗口</div>
                            <div class="value" id="dash-outdoor-eta">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">关灯计划</div>
                            <div class="value" id="dash-outdoor-off-countdown">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">开灯条件</div>
                            <div class="value" id="dash-outdoor-window">--</div>
                        </div>
                        <div class="outdoor-auto-metric">
                            <div class="label">复位规则</div>
                            <div class="value" id="dash-outdoor-debounce">--</div>
                        </div>
                    </div>
                </div>
                <div class="outdoor-auto-note" id="dash-outdoor-note">低于阈值自动开灯，20:00 自动关灯。</div>
            </div>`;
        }
        function renderScreenStatusCard(screen) {
            const status = screen.status || {};
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const isOnline = statusMeta.isOnlineLike;
            const position = Number.isFinite(Number(status.position)) ? Number(status.position) : 0;
            const height = Number.isFinite(Number(status.height)) ? Number(status.height) : 0;
            const totalHeight = screen.screen_config?.total_height || status.total_height || 3.0;
            const totalTime = screen.screen_config?.total_time || 30;
            const onlineText = statusMeta.text;
            const actionText = getScreenActionText(status);
            const remainingTime = Number.isFinite(Number(status.remaining_time)) ? Number(status.remaining_time).toFixed(1) : '0.0';
            const clampedPosition = Math.max(0, Math.min(100, position));
            const posState = clampedPosition >= 95 ? '全降（到底）' : (clampedPosition <= 5 ? '全升（到顶）' : '中间位置');
            return `<div class="screen-status-card ${isOnline ? '' : 'offline'} ${getCardStateClass(statusMeta)}" id="screen-status-${escapeHtml(screen.id)}">
                <div class="screen-status-header">
                    <div class="screen-status-name">${escapeHtml(screen.name || screen.id)}</div>
                    <div class="screen-status-online ${isOnline ? '' : 'offline'} ${statusMeta.level === 'stale' || statusMeta.level === 'error' ? 'warning' : ''}">${onlineText}</div>
                </div>
                <div class="screen-main-row">
                    <div class="screen-core-meta">
                        <div class="screen-progress-panel">
                            <div class="screen-progress-rail" title="竖版位置进度">
                                <div class="screen-progress-fill-vertical" style="height:${clampedPosition}%; --screen-pos:${clampedPosition}%;"></div>
                            </div>
                            <div class="screen-progress-meta">
                                <div class="screen-progress-head">
                                    <span class="screen-progress-label">当前位置</span>
                                    <span class="screen-position-text">${clampedPosition.toFixed(1)}%</span>
                                </div>
                                <div class="screen-position-note">${posState}</div>
                                <div class="screen-metrics">
                                    <div>
                                        <div class="screen-metric-label">当前高度</div>
                                        <div class="screen-metric-value">${height.toFixed(2)} 米</div>
                                    </div>
                                    <div>
                                        <div class="screen-metric-label">幕布状态</div>
                                        <div class="screen-metric-value" style="color:${getScreenActionColor(status)}">${escapeHtml(actionText)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="screen-control-side">
                        ${renderScreenControlButton(screen, 'up', '上升', 'up')}
                        ${renderScreenControlButton(screen, 'stop', '停止', 'stop')}
                        ${renderScreenControlButton(screen, 'down', '下降', 'down')}
                    </div>
                </div>
                <div class="screen-status-foot">
                    <span>总高度：${escapeHtml(totalHeight)} 米</span>
                    <span>全程时间：${escapeHtml(totalTime)} 秒</span>
                    <span>剩余时间：${escapeHtml(remainingTime)} 秒</span>
                </div>
                <div class="dashboard-mini-note">${escapeHtml(statusMeta.note)}</div>
            </div>`;
        }

        // 投影机状态显示
        function updateProjectorStatus() {
            fetch('/api/projector/status')
                .then(r => r.json())
                .then(data => {
                    projectorStatusCache = data || {};
                    renderProjectorCards('dashboard-projector-grid', 'dashboard');
                    renderProjectorCards('projector-page-grid', 'page');
                    let onlineCount = 0;
                    projectorConfigs.forEach(proj => {
                        if ((projectorStatusCache[proj.id] || {}).online) onlineCount++;
                    });
                    const dashProjectorOnline = document.getElementById('dash-projector-online');
                    if (dashProjectorOnline) dashProjectorOnline.innerText = onlineCount;
                    if (currentProjectorRemoteId) renderProjectorRemote(currentProjectorRemoteId);
                })
                .catch(e => {
                    console.error('投影机状态更新失败', e);
                });
        }
        
        // 幕布状态显示
        function updateScreenStatus() {
            fetch('/api/screens')
                .then(r => r.json())
                .then(data => {
                    const grid = document.getElementById('screen-status-grid');
                    if (!grid) return;
                    const screens = data.screens || [];
                    grid.innerHTML = screens.length
                        ? screens.map(screen => renderScreenStatusCard(screen)).join('')
                        : '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置幕布设备</div>';
                })
                .catch(e => {
                    console.error('幕布状态更新失败', e);
                });
        }

        // 环境与自动化引擎
        const envConfigs = Array.isArray(window.envConfigs) ? window.envConfigs : [];
        window.__envConfigsCache = envConfigs;
        function updateEnvData() {
            fetch('/api/env/status').then(r => r.json()).then(data => {
                window.__envStatusCache = data || {};
                updateHvacRoomEnvSlots();
                const container = document.getElementById('env-grid-container');
                const screenEnvColumn = document.getElementById('screen-env-column');
                const screenUpsColumn = document.getElementById('screen-ups-column');
                const topTemp = document.getElementById('top-env-temp');
                const topHum = document.getElementById('top-env-hum');
                const topLux = document.getElementById('top-env-lux');
                const topSummary = document.getElementById('top-env-summary');
                const onlineSensor = pickDashboardEnvSensor(data);
                if (screenEnvColumn) screenEnvColumn.innerHTML = buildScreenEnvCards();
                if (screenUpsColumn) screenUpsColumn.innerHTML = buildScreenUpsCards();
                if (topTemp && topHum && topLux) {
                    if (onlineSensor) {
                        const st = onlineSensor.st;
                        topTemp.textContent = st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--';
                        topHum.textContent = st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--';
                        topLux.textContent = st.lux !== null && st.lux !== undefined ? `${st.lux}Lux` : '--';
                        if (topSummary) topSummary.style.opacity = '1';
                    } else {
                        topTemp.textContent = '--';
                        topHum.textContent = '--';
                        topLux.textContent = '--';
                        if (topSummary) topSummary.style.opacity = '0.75';
                    }
                }
                if(Object.keys(data).length === 0) {
                    container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1;">暂未配置传感器。</div>';
                    return;
                }
                let html = '';
                envConfigs.forEach(cfg => {
                    const st = data[cfg.id] || {online: false};
                    const features = getEnvFeatures(cfg);
                    const color = st.online ? 'var(--success)' : '#475569';

                    const batteryValue = Number(st.battery);
                    const hasBattery = Number.isFinite(batteryValue);
                    const batteryColor = !hasBattery ? 'var(--text-sub)' : (batteryValue <= 15 ? 'var(--danger)' : (batteryValue <= 35 ? 'var(--warning)' : '#22c55e'));
                    const metricDefs = [
                        { key: 'temperature', label: '温度', value: st.temp, suffix: ' °C', color: 'var(--success)' },
                        { key: 'humidity', label: '湿度', value: st.hum, suffix: ' %', color: 'var(--brand-blue)' },
                        { key: 'noise', label: '噪声', value: st.noise, suffix: ' dB', color: 'var(--warning)' },
                        { key: 'pm25', label: 'PM2.5', value: st.pm25, suffix: '', color: '#f97316' },
                        { key: 'pm10', label: 'PM10', value: st.pm10, suffix: '', color: '#a78bfa' },
                        { key: 'pressure', label: '气压', value: st.pressure, suffix: ' kPa', color: '#22c55e' }
                    ].filter(item => features[item.key]);
                    if (hasBattery && envFeatureEnabled(features, 'battery')) {
                        metricDefs.push({ key: 'battery', label: '电量估算', value: batteryValue, suffix: ' %', color: batteryColor });
                    }

                    const mainMetricLabel = features.illuminance ? '核心指标：实时光照度' : '核心指标：环境监测';
                    const mainMetricValue = features.illuminance && st.online ? (st.lux + ' Lux') : '--';

                    let metricsHtml = '';
                    metricDefs.forEach(item => {
                        const valueText = st.online ? `${item.value}${item.suffix}` : '--';
                        metricsHtml += `<div><div class="label">${item.label}</div><div class="val" style="font-size:24px; margin:5px 0; color:${item.color};">${valueText}</div></div>`;
                    });
                    if(!metricsHtml) {
                        metricsHtml = '<div style="color:var(--text-sub);">未启用扩展指标</div>';
                    }

                    html += `<div class="env-card" style="border-top: 4px solid ${color}; min-height: 220px;">
                        <div class="label" style="font-size:16px; font-weight:bold; color:var(--text-main); margin-bottom:15px;">${cfg.name}</div>
                        <div class="label">${mainMetricLabel}</div>
                        <div class="val" style="color:var(--warning)">${mainMetricValue}</div>
                        <div style="display:flex; justify-content: space-around; flex-wrap: wrap; gap: 20px; margin-top: 20px; padding-top: 15px; border-top: 1px dashed rgba(255,255,255,0.1);">
                            ${metricsHtml}
                        </div>
                    </div>`;
                });
                container.innerHTML = html;
            });
        }
        function toggleAutomation(ruleId, isEnabled) { if (!ensurePermission('automation.edit', '修改自动化规则')) return; fetch('/api/automation/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: ruleId, enabled: isEnabled }) }).then(r => r.json()).then(d => { if(d.success) { showToast(isEnabled ? '自动化规则已启用' : '自动化规则已暂停'); const card = document.getElementById('auto-card-' + ruleId); if(card) { if(isEnabled) card.classList.remove('disabled'); else card.classList.add('disabled'); } } }); }
        function applyPermissionUI() {
            const disabledStyle = 'opacity:.55;cursor:not-allowed;pointer-events:none;filter:grayscale(.18);';
            const configLink = document.querySelector('.system-link');
            const configBtn = document.getElementById('top-user-config-btn');
            if (configLink && !canOpenConfigCenter()) {
                configLink.style.display = 'none';
            }
            if (configBtn && !canOpenConfigCenter()) {
                configBtn.style.display = 'none';
            }
            if (!hasPermission('power.control')) {
                document.querySelectorAll('[onclick*="togglePower("],[onclick*="doPowerStart("],[onclick*="doPowerStop("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无强电控制权限';
                });
            }
            if (!hasPermission('light.control')) {
                document.querySelectorAll('[onclick*="toggleLight("],[onclick*="executeScene("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无灯光控制权限';
                });
            }
            if (!hasPermission('door.control')) {
                document.querySelectorAll('[onclick*="controlDoor("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无门禁控制权限';
                });
            }
            if (!hasPermission('automation.edit')) {
                document.querySelectorAll('.auto-item input[type="checkbox"]').forEach(el => {
                    el.disabled = true;
                    el.title = '当前账号无自动化编辑权限';
                });
                document.querySelectorAll('.auto-edit-btn,.auto-edit-save,.auto-edit-cancel').forEach(el => {
                    el.disabled = true;
                    el.title = '当前账号无自动化编辑权限';
                });
            }
            if (!hasPermission('server.control')) {
                document.querySelectorAll('[onclick*="moveServer("]').forEach(el => {
                    el.disabled = true;
                    el.style.cssText += disabledStyle;
                    el.title = '当前账号无服务器控制权限';
                });
            }
        }

        function reportFrontendError(scope, err) {
            const errorText = err && err.stack ? err.stack : String(err || 'unknown_error');
            console.error(`[frontend:${scope}]`, err);
            try {
                fetch('/api/logs/frontend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope,
                        message: errorText,
                        url: window.location.href,
                        ts: new Date().toISOString()
                    })
                }).catch(() => {});
            } catch (_) {}
        }

        function guardFrontendStep(scope, fn, fallbackMessage = '') {
            try {
                return fn();
            } catch (err) {
                reportFrontendError(scope, err);
                if (fallbackMessage) {
                    showToast(fallbackMessage, true);
                }
                return null;
            }
        }

        window.addEventListener('error', event => {
            if (!event) return;
            const detail = event.error || event.message || 'window_error';
            reportFrontendError('window.error', detail);
        });

        window.addEventListener('unhandledrejection', event => {
            const detail = event && event.reason ? event.reason : 'unhandled_rejection';
            reportFrontendError('window.unhandledrejection', detail);
        });

        function initCanvas() {
            initDoorCanvas('left');
            initDoorCanvas('right');
        }

        document.addEventListener('DOMContentLoaded', () => {
            applyAdaptiveDensity();
            guardFrontendStep('bootstrap.permission_ui', () => applyPermissionUI());
            guardFrontendStep('bootstrap.dashboard_order', () => applyDashboardSectionOrder());
            guardFrontendStep('bootstrap.dashboard_masonry_observer', () => initDashboardMasonryObservers());
            guardFrontendStep('bootstrap.dashboard_masonry', () => scheduleDashboardMasonry(160));
            guardFrontendStep('bootstrap.global_clock', () => updateGlobalClock());
            guardFrontendStep('bootstrap.agent_version', () => refreshLatestAgentVersion());
            guardFrontendStep('bootstrap.apple_audio', () => initAppleAudioDemo());
            guardFrontendStep('bootstrap.server_compact', () => refreshDashboardServerCompactFallback());
            const userBadge = document.getElementById('top-user-badge');
            if (userBadge) {
                userBadge.addEventListener('click', event => {
                    event.stopPropagation();
                    toggleUserMenu();
                });
            }
            const userMenu = document.getElementById('top-user-menu');
            if (userMenu) {
                userMenu.addEventListener('click', event => {
                    event.stopPropagation();
                });
            }
            document.addEventListener('click', event => {
                const menu = document.getElementById('top-user-menu');
                const badge = document.getElementById('top-user-badge');
                if (!menu || !badge) return;
                if (!badge.contains(event.target)) toggleUserMenu(false);
                if (!event.target.closest('.hvac-temp-panel')) closeHvacTempControls();
                if (!event.target.closest('.hvac-metric.mode')) closeHvacModeMenus();
            });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape') {
                    toggleUserMenu(false);
                    closeHvacTempControls();
                    closeHvacModeMenus();
                }
            });
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) stopNvrPreviewStreams();
                refreshPollingVisibility();
            });
            window.addEventListener('focus', () => {
                refreshPollingVisibility();
            });
            window.addEventListener('beforeunload', () => {
                stopNvrPreviewStreams();
                stopDoorVideoStream();
                stopAllPollingTasks();
            });
            const firstNav = document.querySelector('.nav-menu li.active');
            guardFrontendStep('bootstrap.first_nav', () => {
                const navItems = Array.from(document.querySelectorAll('.nav-menu li'));
	                const initialView = getInitialViewFromUrl();
	                if (initialView) {
                        if (initialView === 'snmp') restoreSnmpSelectedDeviceFromUrl();
	                    const targetNav = findNavElementByView(initialView);
	                    switchTab(initialView, getViewTitleFromNav(targetNav, '中控系统'), targetNav);
	                    return;
	                }
                const dashboardNav = navItems.find(el => String(el.getAttribute('onclick') || '').includes("switchTab('dashboard'"));
                const initialNav = dashboardNav || firstNav || null;
                if (initialNav) {
                    const onclickText = String(initialNav.getAttribute('onclick') || '');
                    const match = onclickText.match(/switchTab\('([^']+)',\s*'([^']+)'/);
                    if (match) {
                        switchTab(match[1], match[2], initialNav);
                        return;
                    }
                }
                switchTab('dashboard', '场馆总览', initialNav);
            }, '默认页面初始化异常，已切换为降级启动');
            if (getActiveViewId() === 'door') {
                setTimeout(() => {
                    guardFrontendStep('bootstrap.door_init', () => {
                        initCanvas();
                        updateDoorStatus(true).finally(() => startDoorVideoStream());
                    });
                }, 180);
            }
            window.addEventListener('resize', () => {
                applyAdaptiveDensity();
                scheduleDashboardMasonry(120);
                if (window.innerWidth > 760) closeSidebar();
            });
            guardFrontendStep('bootstrap.start_polling', () => startAppPolling(), '页面轮询启动失败，请查看系统日志');
        });

        registerPollingTask('power', 3500, () => updatePowerData(), () => ['dashboard', 'power'].includes(getActiveViewId()) || isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick'));
        registerPollingTask('meter', 4500, () => updateMeterCenter(), () => ['dashboard', 'meter'].includes(getActiveViewId()) || isDashboardSectionVisible('meter'));
        registerPollingTask('ups', 4500, () => updateUpsStatus(), () => ['dashboard', 'ups'].includes(getActiveViewId()) || isDashboardSectionVisible('ups_compact') || isDashboardSectionVisible('ups'));
        registerPollingTask('hy_edge', 6000, () => updateHyEdgeStatus(), () => ['dashboard'].includes(getActiveViewId()) || isDashboardSectionVisible('hy_edge'));
        registerPollingTask('dashboard_summary', 5000, () => updateDashboardSummary(), () => getActiveViewId() === 'dashboard' || isDashboardSectionVisible('stats'));
        registerPollingTask('proxy', 5000, () => updateProxyStatus(), () => getActiveViewId() === 'proxy');
        registerPollingTask('snmp', 9000, () => updateSnmpStatus(), () => ['dashboard', 'snmp', 'camera_preview'].includes(getActiveViewId()) || isDashboardSectionVisible('snmp'));
        registerPollingTask('hvac', 5000, () => updateHvacStatus(), () => ['dashboard', 'hvac'].includes(getActiveViewId()) || isDashboardSectionVisible('hvac'));
        registerPollingTask('light', 2200, () => updateLightData(), () => ['dashboard', 'light'].includes(getActiveViewId()) || isDashboardSectionVisible('light_compact') || isDashboardSectionVisible('light'));
        registerPollingTask('server', 5000, () => updateServerData(), () => getActiveViewId() === 'server');
        registerPollingTask('door', 1200, () => updateDoorStatus(), () => ['dashboard', 'door'].includes(getActiveViewId()) || isDashboardSectionVisible('door'));
        registerPollingTask('env', 3500, () => updateEnvData(), () => ['dashboard', 'env', 'hvac'].includes(getActiveViewId()) || isDashboardSectionVisible('env') || isDashboardSectionVisible('hvac'));
        registerPollingTask('automation', 4000, () => {
            loadAutomationStatus();
            if (getActiveViewId() === 'auto') loadAutomationLogs();
        }, () => ['dashboard', 'auto'].includes(getActiveViewId()));
        registerPollingTask('projector', 6000, () => updateProjectorStatus(), () => ['dashboard', 'projector'].includes(getActiveViewId()) || isDashboardSectionVisible('projector'));
        registerPollingTask('sequencer', 4500, () => updateSequencerStatus(), () => ['dashboard', 'sequencer'].includes(getActiveViewId()) || isDashboardSectionVisible('sequencer'));
        registerPollingTask('screen', 4500, () => updateScreenStatus(), () => ['dashboard', 'screen'].includes(getActiveViewId()) || isDashboardSectionVisible('screen'));
        registerPollingTask('apple_audio', 3200, () => loadAppleAudioStatus(), () => ['apple_audio'].includes(getActiveViewId()));
        registerPollingTask('logs', 5000, () => updateDashboardLogs(), () => getActiveViewId() === 'dashboard');
        setTimeout(() => { try { updateDashboardSummary(); } catch (_) {} }, 220);
