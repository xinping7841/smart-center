(function installSmartCenterViewportLayout(global) {
    'use strict';

    // AI map: core.viewport_layout. Runs early in <head> before CSS layout is applied.
    const params = new URLSearchParams(global.location.search);
    const forceLayout = String(params.get('force_layout') || params.get('layout') || '').toLowerCase();
    const rememberLayout = params.get('remember_layout') === '1';
    const useSavedLayout = params.get('use_saved_layout') === '1' || rememberLayout;

    try {
        if (params.get('layout_reset') === '1') {
            localStorage.removeItem('smartCenterDashboardLayout');
        } else if (rememberLayout && (['desktop', 'pc', 'wide'].includes(forceLayout) || params.get('desktop') === '1')) {
            localStorage.setItem('smartCenterDashboardLayout', 'desktop');
        } else if (rememberLayout && (['tablet', 'pad', 'fold'].includes(forceLayout) || params.get('tablet') === '1')) {
            localStorage.setItem('smartCenterDashboardLayout', 'tablet');
        } else if (rememberLayout && (['mobile', 'phone', 'outer'].includes(forceLayout) || params.get('mobile') === '1')) {
            localStorage.setItem('smartCenterDashboardLayout', 'mobile');
        }
    } catch (_) {}

    let savedLayout = '';
    try {
        savedLayout = useSavedLayout ? (localStorage.getItem('smartCenterDashboardLayout') || '') : '';
    } catch (_) {}

    const explicitMobile = ['mobile', 'phone', 'outer'].includes(forceLayout) || params.get('mobile') === '1' || savedLayout === 'mobile';
    if (explicitMobile) {
        document.documentElement.dataset.viewportPreset = 'mobile';
        return;
    }

    const viewportMeta = document.querySelector('meta[name="viewport"]');
    if (!viewportMeta) return;

    const screenW = Number(global.screen?.width || 0);
    const screenH = Number(global.screen?.height || 0);
    const viewW = Math.max(
        Number(global.innerWidth || 0),
        Number(document.documentElement?.clientWidth || 0),
        Number(global.visualViewport?.width || 0)
    );
    const viewH = Math.max(
        Number(global.innerHeight || 0),
        Number(document.documentElement?.clientHeight || 0),
        Number(global.visualViewport?.height || 0)
    );
    const dpr = Math.max(1, Number(global.devicePixelRatio || 1));
    const shortSide = Math.min(screenW, screenH);
    const longSide = Math.max(screenW, screenH);
    const screenAspect = shortSide ? longSide / shortSide : 9;
    const viewShort = Math.min(viewW, viewH);
    const viewLong = Math.max(viewW, viewH);
    const viewAspect = viewShort ? viewLong / viewShort : 9;
    const physicalShort = Math.max(shortSide * dpr, viewShort * dpr);
    const physicalLong = Math.max(longSide * dpr, viewLong * dpr);
    const coarsePointer = global.matchMedia ? global.matchMedia('(pointer: coarse)').matches : false;
    const touchPoints = Number(navigator.maxTouchPoints || 0);
    const isTouch = coarsePointer || touchPoints > 0;
    const ua = navigator.userAgent || '';
    const uaDataMobile = navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean'
        ? navigator.userAgentData.mobile
        : null;
    const uaLooksTouchOs = /Android|iPhone|iPad|iPod|HarmonyOS|Adr/i.test(ua);
    const uaLooksMobile = /Mobile|iPhone|iPad|iPod|Android|HarmonyOS|Adr/i.test(ua);
    const explicitTablet = ['tablet', 'pad', 'fold'].includes(forceLayout) || params.get('tablet') === '1' || savedLayout === 'tablet';
    const explicitDesktop = ['desktop', 'pc', 'wide'].includes(forceLayout) || params.get('desktop') === '1' || savedLayout === 'desktop';
    const squareTouchScreen = Math.min(screenAspect, viewAspect) <= 1.62;
    const nearSquareViewport = viewShort >= 560 && viewLong >= 620 && viewAspect <= 1.62;
    const highDensityFoldScreen = squareTouchScreen && physicalShort >= 900 && physicalLong >= 1000;
    const autoTabletCandidate = isTouch && !explicitMobile && !explicitDesktop && (
        nearSquareViewport || highDensityFoldScreen || (viewShort >= 600 && viewLong >= 768 && viewAspect <= 1.75)
    );
    const browserDesktopSite = isTouch && !explicitMobile && !explicitTablet && !autoTabletCandidate && (
        (!uaLooksTouchOs && (uaDataMobile === false || !uaLooksMobile))
        || (uaDataMobile === false && viewLong >= 960)
    );
    const desktopRequested = explicitDesktop || (!explicitTablet && !autoTabletCandidate && browserDesktopSite);

    if (desktopRequested) {
        document.documentElement.dataset.viewportPreset = explicitDesktop ? 'desktop-forced' : 'desktop-touch';
        viewportMeta.setAttribute('content', 'width=1920, initial-scale=1.0, viewport-fit=cover');
    } else if (explicitTablet || autoTabletCandidate) {
        document.documentElement.dataset.viewportPreset = explicitTablet ? 'tablet-forced' : 'tablet-auto';
    } else if (isTouch) {
        document.documentElement.dataset.viewportPreset = 'touch-mobile';
    }
})(window);

(function installSmartCenterAdaptiveLayout(global) {
    'use strict';

    // AI map: core.adaptive_layout. Runtime density classes and dashboard fit state.
    // Keep this independent from page business modules: it only toggles layout classes.
    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function getCurrentViewId() {
        if (typeof global.getActiveViewId === 'function') return global.getActiveViewId();
        const active = document.querySelector('.view-section.active');
        return active ? String(active.id || '').replace(/^view-/, '') : 'dashboard';
    }

    function maybeCloseSidebar() {
        if (typeof global.closeSidebar === 'function') global.closeSidebar();
        else document.body.classList.remove('sidebar-open');
    }

    function updateLayoutDebugPanel(info) {
        const params = new URLSearchParams(global.location.search);
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
        const clearFit = () => {
            root.classList.remove('dashboard-browser-fit', 'dashboard-fixed-canvas', 'dashboard-fixed-canvas-locked');
            root.style.removeProperty('--dashboard-fit-scale');
            root.style.removeProperty('--dashboard-fit-base-width');
            root.style.removeProperty('--dashboard-fit-base-height');
            root.style.removeProperty('--dashboard-fit-offset-x');
            root.style.removeProperty('--dashboard-fit-offset-y');
        };
        const params = new URLSearchParams(global.location.search);
        const fitMode = String(params.get('fit_dashboard') || params.get('display_mode') || '').toLowerCase();
        const enabled = ['1', 'true', 'on', 'fit', 'fixed', 'canvas', 'kiosk', 'carousel'].includes(fitMode);
        const activeView = getCurrentViewId();
        const mobileMode = typeof info.isMobile === 'boolean' ? info.isMobile : document.body.classList.contains('mobile-layout');
        const tabletMode = typeof info.isTablet === 'boolean' ? info.isTablet : document.body.classList.contains('tablet-layout');
        const touchWideMode = typeof info.isTouchWide === 'boolean' ? info.isTouchWide : document.body.classList.contains('touch-wide-layout');
        const touchPortraitMode = typeof info.isTouchPortrait === 'boolean' ? info.isTouchPortrait : document.body.classList.contains('touch-portrait-layout');
        const desktopDashboard = activeView === 'dashboard' && !mobileMode && !tabletMode && !touchWideMode && !touchPortraitMode;
        if (!enabled || !desktopDashboard) {
            clearFit();
            return;
        }
        const width = Number(info.width || global.innerWidth || document.documentElement.clientWidth || 0);
        const height = Number(info.height || global.innerHeight || document.documentElement.clientHeight || 0);
        const visualW = Number(info.visualW || global.visualViewport?.width || width || 0);
        const visualH = Number(info.visualH || global.visualViewport?.height || height || 0);
        const fitW = Math.max(1, Math.min(width || visualW, visualW || width));
        const fitH = Math.max(1, Math.min(height || visualH, visualH || height));
        root.classList.remove('dashboard-browser-fit');
        root.classList.add('dashboard-fixed-canvas', 'dashboard-fixed-canvas-locked');
        root.style.setProperty('--dashboard-fit-scale', '1');
        root.style.setProperty('--dashboard-fit-base-width', `${fitW}px`);
        root.style.setProperty('--dashboard-fit-base-height', `${fitH}px`);
        root.style.setProperty('--dashboard-fit-offset-x', '0px');
        root.style.setProperty('--dashboard-fit-offset-y', '0px');
    }

    function applyAdaptiveDensity() {
        const width = global.innerWidth || document.documentElement.clientWidth || 0;
        const height = global.innerHeight || document.documentElement.clientHeight || 0;
        const params = new URLSearchParams(global.location.search);
        const forceTouchMode = params.get('force_touch') || '';
        const forceLayoutMode = String(params.get('force_layout') || params.get('layout') || '').toLowerCase();
        const useSavedLayout = params.get('use_saved_layout') === '1' || params.get('remember_layout') === '1';
        const coarsePointer = global.matchMedia ? global.matchMedia('(pointer: coarse)').matches : false;
        const touchPoints = Number(navigator.maxTouchPoints || 0);
        const ua = navigator.userAgent || '';
        const uaDataMobile = navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean'
            ? navigator.userAgentData.mobile
            : null;
        const uaLooksTouchOs = /Android|iPhone|iPad|iPod|HarmonyOS|Adr/i.test(ua);
        const uaLooksMobile = /Mobile|iPhone|iPad|iPod|Android|HarmonyOS|Adr/i.test(ua);
        const screenW = Number(global.screen?.width || 0);
        const screenH = Number(global.screen?.height || 0);
        const screenShort = Math.min(screenW, screenH);
        const screenLong = Math.max(screenW, screenH);
        const screenAspect = screenShort ? screenLong / screenShort : 9;
        const visualW = Number(global.visualViewport?.width || 0);
        const visualH = Number(global.visualViewport?.height || 0);
        const viewShort = Math.min(
            ...[width, height, visualW, visualH].filter(value => Number.isFinite(value) && value > 0)
        );
        const viewLong = Math.max(width, height, visualW, visualH, 0);
        const viewAspect = viewShort ? viewLong / viewShort : 9;
        const dpr = Math.max(1, Number(global.devicePixelRatio || 1));
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
        if (isMobile || isTouchWide || isTablet) maybeCloseSidebar();
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

    const api = {
        applyAdaptiveDensity,
        applyDashboardBrowserFit,
        updateLayoutDebugPanel,
    };
    SmartCenter.viewportLayout = Object.assign({}, SmartCenter.viewportLayout || {}, api);
    global.applyAdaptiveDensity = applyAdaptiveDensity;
    global.applyDashboardBrowserFit = applyDashboardBrowserFit;
    global.updateLayoutDebugPanel = updateLayoutDebugPanel;
})(window);
