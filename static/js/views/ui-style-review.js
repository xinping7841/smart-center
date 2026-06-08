// AI_MODULE: ui_style_review_switcher
// AI_PURPOSE: Temporary homepage UI style comparison switcher for reviewing Ops, Apple, Meizu, and Smartisan visual directions.
// AI_BOUNDARY: Only sets body[data-ui-review-style] and localStorage preference; no API calls, permissions, navigation, or device-control behavior.
// AI_DATA_FLOW: click on .ui-style-option -> localStorage smartCenterUiReviewStyle -> body dataset -> ui-style-review.css scoped overrides.
// AI_RUNTIME: Loaded from templates/index.html after app-runtime.js while the team compares visual styles; safe to delete with the matching CSS after final selection.
// AI_RISK: Low functional risk, medium visual risk. If removed, the dashboard falls back to ui-dark-ops-palette.css.
// AI_COMPAT: Keep the switcher DOM optional and defensive so production pages still load if the temporary control is removed before this script.
// AI_SEARCH_KEYWORDS: UI style review, style switcher, Apple Meizu Smartisan, temporary A/B compare, removable frontend layer.

(function initUiStyleReview(global) {
    'use strict';

    const STORAGE_KEY = 'smartCenterUiReviewStyle';
    const DEFAULT_STYLE = 'ops';
    const ALLOWED_STYLES = new Set(['ops', 'apple', 'meizu', 'smartisan']);

    function normalizeStyle(value) {
        const key = String(value || '').trim().toLowerCase();
        return ALLOWED_STYLES.has(key) ? key : DEFAULT_STYLE;
    }

    function readSavedStyle() {
        try {
            return normalizeStyle(global.localStorage?.getItem(STORAGE_KEY));
        } catch (_) {
            return DEFAULT_STYLE;
        }
    }

    function writeSavedStyle(styleKey) {
        try {
            global.localStorage?.setItem(STORAGE_KEY, styleKey);
        } catch (_) {}
    }

    function applyStyle(styleKey, options = {}) {
        const nextStyle = normalizeStyle(styleKey);
        document.body.dataset.uiReviewStyle = nextStyle;
        document.querySelectorAll('.ui-style-option').forEach(button => {
            const isActive = normalizeStyle(button.dataset.uiStyle) === nextStyle;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        if (!options.skipSave) writeSavedStyle(nextStyle);
        return nextStyle;
    }

    function bindSwitcher() {
        const switcher = document.querySelector('[data-ui-style-switcher]');
        if (!switcher || switcher.dataset.uiStyleBound === '1') return;
        switcher.dataset.uiStyleBound = '1';
        switcher.addEventListener('click', event => {
            const button = event.target?.closest?.('.ui-style-option');
            if (!button) return;
            applyStyle(button.dataset.uiStyle || DEFAULT_STYLE);
        });
        switcher.addEventListener('keydown', event => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            const buttons = Array.from(switcher.querySelectorAll('.ui-style-option'));
            const currentIndex = buttons.findIndex(button => button.getAttribute('aria-pressed') === 'true');
            const offset = event.key === 'ArrowRight' ? 1 : -1;
            const nextIndex = (Math.max(0, currentIndex) + offset + buttons.length) % buttons.length;
            const nextButton = buttons[nextIndex];
            if (!nextButton) return;
            event.preventDefault();
            nextButton.focus();
            applyStyle(nextButton.dataset.uiStyle || DEFAULT_STYLE);
        });
    }

    function ready() {
        bindSwitcher();
        applyStyle(readSavedStyle(), { skipSave: true });
    }

    global.SmartCenter = global.SmartCenter || {};
    global.SmartCenter.uiStyleReview = {
        applyStyle,
        readSavedStyle,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ready, { once: true });
    } else {
        ready();
    }
})(window);
