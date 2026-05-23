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
