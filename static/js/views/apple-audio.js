// AI_MODULE: apple_audio_view
// AI_PURPOSE: 音乐库、播放队列、歌词和封面的前端展示。
// AI_BOUNDARY: 不直接控制音频设备；所有动作走 /api/apple-audio/*。
// AI_DATA_FLOW: /api/apple-audio/status/queue/transport -> 音乐卡片和控制按钮。
// AI_RUNTIME: 首页或音乐页面加载。
// AI_RISK: 中，音乐扫描和播放控制会影响首页加载与现场播放体验。
// AI_SEARCH_KEYWORDS: apple audio, music, queue, lyrics, cover.

(function installSmartCenterAppleAudio(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.appleAudio = Object.assign({}, SmartCenter.appleAudio || {});

    function html(value) {
        return typeof global.escapeHtml === 'function'
            ? global.escapeHtml(value)
            : String(value ?? '').replace(/[&<>"']/g, ch => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch]));
    }

    function fetchJson(url, options = {}, fallbackText = '请求失败') {
        if (typeof global.fetchJson === 'function') return global.fetchJson(url, options, fallbackText);
        return fetch(url, options).then(response => response.json());
    }

    function postJson(url, payload, fallbackText = '请求失败') {
        if (typeof global.postJsonLoose === 'function') return global.postJsonLoose(url, payload, fallbackText);
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
        }).then(response => response.json());
    }

    function notify(message, isError = false) {
        if (typeof global.showToast === 'function') global.showToast(message, isError);
    }

    function translateError(message, fallbackText = '请求失败') {
        return typeof global.translateApiError === 'function'
            ? global.translateApiError(message, fallbackText)
            : (message || fallbackText);
    }

    function formatDateTime(value) {
        return typeof global.formatDateTimeText === 'function'
            ? global.formatDateTimeText(value)
            : (value ? String(value) : '--');
    }

    function canOpenConfig() {
        return typeof global.canOpenConfigCenter === 'function' ? global.canOpenConfigCenter() : true;
    }

state.library = Array.isArray(state.library) ? state.library : [];
state.outputZones = Array.isArray(state.outputZones) ? state.outputZones : [];
state.queue = Array.isArray(state.queue) ? state.queue : [];
state.nowPlaying = state.nowPlaying || null;
state.isPlaying = !!state.isPlaying;
state.elapsedSec = Number(state.elapsedSec || 0);
state.stateCache = state.stateCache || null;
state.stateLoading = !!state.stateLoading;
state.lyricsTrackId = state.lyricsTrackId || '';
state.lyricsType = state.lyricsType || 'none';
state.lyricsPlain = state.lyricsPlain || '';
state.lyricsLines = Array.isArray(state.lyricsLines) ? state.lyricsLines : [];
state.lyricsActiveIndex = Number.isFinite(Number(state.lyricsActiveIndex)) ? Number(state.lyricsActiveIndex) : -1;
state.categorySelected = state.categorySelected || 'all';
state.remoteResults = Array.isArray(state.remoteResults) ? state.remoteResults : [];
state.searchSeq = Number(state.searchSeq || 0);
state.audioEl = state.audioEl || null;

function renderAppleAudioPage(force = false) {
    const root = document.getElementById('apple-audio-page-root');
    if (!root) return;
    if (state.pageRendered && !force) return;
    root.innerHTML = `                <div class="apple-audio-shell">
                    <div class="apple-audio-main">
                        <div class="apple-audio-panel">
                            <div class="apple-audio-hero">
                                <div class="apple-cover" id="appleNowCoverWrap">
                                    <div class="apple-cover-badge">♪</div>
                                </div>
                                <div class="apple-hero-copy">
                                    <div class="apple-source-chip-row">
                                        <span class="apple-source-chip">NAS 音乐播放控制台</span>
                                        <span class="apple-source-chip">支持本地库 / 远端播放代理</span>
                                    </div>
                                    <div class="apple-hero-title">音乐播放器中控界面</div>
                                    <div class="apple-hero-subtitle">把播放、检索、队列、输出分区和状态都收拢到一个页面。当前由 NAS 音源提供曲目，可继续接入远端播放代理。</div>
                                    <div class="apple-hero-meta">
                                        <div class="apple-hero-stat">
                                            <div class="label">当前模式</div>
                                            <div class="value">预集成</div>
                                        </div>
                                        <div class="apple-hero-stat">
                                            <div class="label">输出分区</div>
                                            <div class="value">3 组</div>
                                        </div>
                                        <div class="apple-hero-stat">
                                            <div class="label">队列长度</div>
                                            <div class="value" id="appleQueueCountHero">0</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="apple-now-grid">
                                <div class="apple-now-card">
                                    <div class="apple-panel-head">
                                        <div>
                                            <div class="apple-panel-title">正在播放</div>
                                            <div class="apple-panel-note">显示当前播放器返回的实时播放状态</div>
                                        </div>
                                        <span class="tag info" id="applePlaybackStateTag">待连接</span>
                                    </div>
                                    <div class="apple-track-title" id="appleNowTitle">等待选择音源</div>
                                    <div class="apple-track-meta" id="appleNowMeta">请选择 NAS 曲目或播放列表，或接入远程播放代理。</div>
                                    <div class="apple-progress-wrap">
                                        <div class="apple-progress-bar"><div class="apple-progress-fill" id="appleProgressFill"></div></div>
                                        <div class="apple-progress-meta">
                                            <span id="appleProgressCurrent">00:00</span>
                                            <span id="appleProgressTotal">00:00</span>
                                        </div>
                                    </div>
                                    <div class="apple-control-row">
                                        <button class="apple-ctl-btn secondary" onclick="appleTransport('prev')">⏮</button>
                                        <button class="apple-ctl-btn primary" id="applePlayToggleBtn" onclick="appleTransport('toggle')">▶</button>
                                        <button class="apple-ctl-btn secondary" onclick="appleTransport('next')">⏭</button>
                                        <button class="apple-ctl-btn text" onclick="appleTransport('favorite')">收藏当前曲目</button>
                                        <button class="apple-ctl-btn text" onclick="openAppleAudioConfig()">输出路由</button>
                                    </div>
                                    <div class="apple-lyrics-card">
                                        <div class="apple-lyrics-head">
                                            <div class="apple-panel-title" style="font-size:13px;">歌词</div>
                                            <div class="apple-lyrics-type" id="appleLyricsType">未加载</div>
                                        </div>
                                        <div class="apple-lyrics-box" id="appleLyricsBox">
                                            <div class="apple-lyrics-empty">当前曲目暂无歌词。</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="apple-now-card">
                                    <div class="apple-panel-head">
                                        <div>
                                            <div class="apple-panel-title">输出区域</div>
                                            <div class="apple-panel-note">可映射到功放分区、网络播放机或远程工作站</div>
                                        </div>
                                    </div>
                                    <div class="apple-output-list" id="appleOutputList"></div>
                                </div>
                            </div>
                        </div>

                        <div class="apple-grid-2">
                            <div class="apple-audio-panel" style="padding:18px 20px;">
                                <div class="apple-panel-head">
                                    <div>
                                        <div class="apple-panel-title">搜索与推荐</div>
                                        <div class="apple-panel-note">搜索结果来自后端音乐服务，可继续接入播放代理或播放主机</div>
                                    </div>
                                </div>
                                <div class="apple-search-wrap">
                                    <span class="apple-search-icon">⌕</span>
                                    <input id="appleSearchInput" class="apple-search-input" placeholder="搜索本地歌曲、歌手、专辑；可补充 Jamendo" oninput="searchAppleSources(this.value)">
                                </div>
                                <div class="apple-scan-progress" id="appleScanProgressWrap">
                                    <div class="apple-scan-head">
                                        <div class="apple-scan-title">刮削进度</div>
                                        <div class="apple-scan-meta" id="appleScanProgressMeta">0%</div>
                                    </div>
                                    <div class="apple-scan-bar"><div class="apple-scan-fill" id="appleScanProgressFill"></div></div>
                                    <div class="apple-scan-note" id="appleScanProgressNote">等待扫描</div>
                                </div>
                                <div class="apple-category-filters" id="appleCategoryFilters"></div>
                                <div class="apple-result-list" id="appleResultList"></div>
                            </div>

                            <div class="apple-audio-panel" style="padding:18px 20px;">
                                <div class="apple-panel-head">
                                    <div>
                                        <div class="apple-panel-title">播放队列</div>
                                        <div class="apple-panel-note">支持插队、下一首、分时节目单</div>
                                    </div>
                                    <button class="apple-ctl-btn text" style="min-width:108px;" onclick="clearAppleQueue()">清空队列</button>
                                </div>
                                <div class="apple-queue-list" id="appleQueueList"></div>
                            </div>
                        </div>
                    </div>

                    <div class="apple-side-stack">
                        <div class="apple-auth-card">
                            <div class="apple-auth-kicker">♪ NAS 音乐接入</div>
                            <div class="apple-auth-title">音乐播放器已切到真实服务接口。</div>
                            <div class="apple-auth-copy">这里会显示后端音乐服务的连接状态、输出区域与当前队列。可以继续接播放代理，或者直接把播放主机音频送入 M32。</div>
                            <div class="apple-auth-actions">
                                <button class="apple-auth-btn primary" onclick="openAppleAudioConfig()">打开配置页</button>
                                <button class="apple-auth-btn secondary" onclick="prepareAppleAudioForM32()">准备 M32 输入</button>
                            </div>
                            <div class="apple-mini-metrics">
                                <div class="apple-mini-stat">
                                    <div class="label">授权状态</div>
                                    <div class="value" id="appleAuthState">未登录</div>
                                </div>
                                <div class="apple-mini-stat">
                                    <div class="label">输出主机</div>
                                    <div class="value">本机 / 远端</div>
                                </div>
                                <div class="apple-mini-stat">
                                    <div class="label">默认音量</div>
                                    <div class="value">72%</div>
                                </div>
                                <div class="apple-mini-stat">
                                    <div class="label">活动场景</div>
                                    <div class="value">展厅背景乐</div>
                                </div>
                            </div>
                        </div>

                        <div class="apple-audio-panel" style="padding:18px 20px;">
                            <div class="apple-panel-head">
                                <div>
                                    <div class="apple-panel-title">建议工作流</div>
                                    <div class="apple-panel-note">适合你当前的中控项目</div>
                                </div>
                            </div>
                            <div class="apple-output-list">
                                <div class="apple-output-card active">
                                    <div class="apple-output-title"><span>方案 A</span><span>推荐</span></div>
                                    <div class="apple-output-meta">浏览器前端直连 NAS 音乐库，播放状态通过接口同步到中控页面，部署简单。</div>
                                </div>
                                <div class="apple-output-card">
                                    <div class="apple-output-title"><span>方案 B</span><span>稳妥</span></div>
                                    <div class="apple-output-meta">独立播放机负责播放，你的中控系统只做检索、排队和输出切换。</div>
                                </div>
                                <div class="apple-output-card">
                                    <div class="apple-output-title"><span>方案 C</span><span>过渡</span></div>
                                    <div class="apple-output-meta">保留这个界面，先用本地歌单或测试音源完成联调，最后再接正式授权。</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
    state.pageRendered = true;
}

function formatAppleDuration(sec) {
    const total = Math.max(0, Number(sec) || 0);
    const m = String(Math.floor(total / 60)).padStart(2, '0');
    const s = String(total % 60).padStart(2, '0');
    return `${m}:${s}`;
}
function normalizeAppleTrack(track, fallbackIndex = 0) {
    const item = track || {};
    return {
        id: String(item.id || `apple_track_${fallbackIndex}`),
        title: String(item.title || '未命名曲目'),
        artist: String(item.artist || '未知艺人'),
        album: String(item.album || '未命名专辑'),
        duration: Number(item.duration || 0),
        tag: String(item.tag || ''),
        accent: String(item.accent || '♪'),
        category: String(item.category || ''),
        source: String(item.source || 'nas'),
        sourceLabel: String(item.source_label || item.source || 'NAS'),
        playable: item.playable !== false,
        streamUrl: String(item.stream_url || (item.id ? `/api/apple-audio/stream/${item.id}` : '')),
        coverUrl: String(item.cover_url || (item.id ? `/api/apple-audio/cover/${item.id}` : '')),
        coverAvailable: !!item.cover_available,
        lyricsAvailable: !!item.lyrics_available,
        lyricsType: String(item.lyrics_type || 'none')
    };
}
function getAppleCategoryLabel(value) {
    const text = String(value || '').trim();
    return text || '未分类';
}
function renderAppleCategoryFilters() {
    const wrap = document.getElementById('appleCategoryFilters');
    if (!wrap) return;
    const counts = new Map();
    (state.library || []).forEach(item => {
        const track = normalizeAppleTrack(item);
        const key = getAppleCategoryLabel(track.category);
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    const options = [{ key: 'all', label: `全部 (${state.library.length})` }];
    Array.from(counts.entries())
        .sort((a, b) => a[0].localeCompare(b[0], 'zh-Hans-CN'))
        .forEach(([key, count]) => {
            options.push({ key, label: `${key} (${count})` });
        });
    if (state.categorySelected !== 'all' && !counts.has(state.categorySelected)) {
        state.categorySelected = 'all';
    }
    wrap.innerHTML = options.map(opt => `
        <button class="apple-cat-chip ${state.categorySelected === opt.key ? 'active' : ''}" onclick="setAppleCategoryFilter('${html(opt.key)}')">
            ${html(opt.label)}
        </button>
    `).join('');
}
function setAppleCategoryFilter(value) {
    state.categorySelected = String(value || 'all');
    renderAppleCategoryFilters();
    const inputEl = document.getElementById('appleSearchInput');
    renderAppleResults(inputEl ? inputEl.value : '');
}
function renderAppleScanProgress(scanState = {}) {
    const wrap = document.getElementById('appleScanProgressWrap');
    const fillEl = document.getElementById('appleScanProgressFill');
    const metaEl = document.getElementById('appleScanProgressMeta');
    const noteEl = document.getElementById('appleScanProgressNote');
    if (!wrap || !fillEl || !metaEl || !noteEl) return;
    const running = !!scanState.running;
    const stage = String(scanState.stage || '');
    const processed = Number(scanState.processed || 0);
    const total = Number(scanState.total || 0);
    const percentRaw = Number(scanState.progress || 0);
    const progress = Math.max(0, Math.min(100, Number.isFinite(percentRaw) ? percentRaw : 0));
    const message = String(scanState.message || '');
    fillEl.style.width = `${progress}%`;
    if (running) {
        metaEl.innerText = `${progress}% · ${processed}/${total || '--'}`;
        noteEl.innerText = message || (stage === 'scrape' ? '正在刮削封面和歌词...' : '正在扫描音频文件...');
        wrap.style.display = '';
        return;
    }
    if (stage === 'done' && total > 0) {
        metaEl.innerText = `100% · ${total} 首`;
        noteEl.innerText = message || '刮削完成';
        wrap.style.display = '';
        return;
    }
    const count = Number(scanState.count || 0);
    metaEl.innerText = count > 0 ? `${count} 首` : '0 首';
    noteEl.innerText = scanState.last_scan_at ? `最近扫描：${formatDateTime(scanState.last_scan_at)}` : '等待扫描';
    wrap.style.display = '';
}
function getAppleCoverHtml(track) {
    const item = track || {};
    const title = html(item.title || '曲目封面');
    if (item.coverAvailable && item.coverUrl) {
        return `<img src="${html(item.coverUrl)}" alt="${title}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.apple-cover')?.classList.remove('has-image'); this.remove();">`;
    }
    return '<div class="apple-cover-badge">♪</div>';
}
function getAppleRowArtHtml(track) {
    const item = track || {};
    if (item.coverAvailable && item.coverUrl) {
        return `<img src="${html(item.coverUrl)}" alt="${html(item.title || '曲目封面')}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.textContent='${html(item.accent || '♪')}';">`;
    }
    return html(item.accent || '♪');
}
function resetAppleLyricsState() {
    state.lyricsTrackId = '';
    state.lyricsType = 'none';
    state.lyricsPlain = '';
    state.lyricsLines = [];
    state.lyricsActiveIndex = -1;
}
function getAppleAudioEl() {
    if (state.audioEl && document.body.contains(state.audioEl)) return state.audioEl;
    const audio = document.getElementById('appleAudioElement') || document.createElement('audio');
    audio.id = 'appleAudioElement';
    audio.preload = 'metadata';
    audio.style.display = 'none';
    if (!audio.parentNode) document.body.appendChild(audio);
    audio.onended = () => appleTransport('next');
    audio.ontimeupdate = () => {
        if (!state.nowPlaying) return;
        state.elapsedSec = Math.floor(audio.currentTime || 0);
        renderAppleNowPlaying();
    };
    audio.onplay = () => {
        state.isPlaying = true;
        renderAppleNowPlaying();
    };
    audio.onpause = () => {
        state.isPlaying = false;
        renderAppleNowPlaying();
    };
    state.audioEl = audio;
    return audio;
}
function playAppleTrackInBrowser(track) {
    const item = normalizeAppleTrack(track || {});
    if (!item.streamUrl || !item.playable) {
        notify('当前曲目没有可播放音频地址', true);
        return;
    }
    const audio = getAppleAudioEl();
    const nextUrl = item.streamUrl;
    if (audio.src !== new URL(nextUrl, window.location.href).href) {
        audio.src = nextUrl;
        audio.currentTime = 0;
    }
    audio.play().catch(err => notify(translateError(err?.message, '浏览器播放失败'), true));
}
function pauseAppleBrowserAudio() {
    const audio = getAppleAudioEl();
    audio.pause();
}
function renderAppleLyrics() {
    const boxEl = document.getElementById('appleLyricsBox');
    const typeEl = document.getElementById('appleLyricsType');
    if (!boxEl || !typeEl) return;
    if (!state.nowPlaying) {
        typeEl.innerText = '未加载';
        boxEl.innerHTML = '<div class="apple-lyrics-empty">当前曲目暂无歌词。</div>';
        return;
    }
    const typeMap = {
        synced: '逐行歌词',
        plain: '纯文本歌词',
        none: '暂无歌词'
    };
    typeEl.innerText = typeMap[state.lyricsType] || '暂无歌词';
    if (state.lyricsType === 'synced' && state.lyricsLines.length) {
        boxEl.innerHTML = state.lyricsLines.map((line, idx) => `
            <div class="apple-lyrics-line ${idx === state.lyricsActiveIndex ? 'active' : ''}" data-lyric-index="${idx}">
                ${html(line.text || '')}
            </div>
        `).join('');
        if (state.lyricsActiveIndex >= 0) {
            const activeEl = boxEl.querySelector(`[data-lyric-index="${state.lyricsActiveIndex}"]`);
            if (activeEl) {
                const top = Math.max(0, activeEl.offsetTop - Math.floor(boxEl.clientHeight * 0.35));
                boxEl.scrollTop = top;
            }
        }
        return;
    }
    if (state.lyricsPlain) {
        boxEl.innerHTML = state.lyricsPlain
            .split(/\n+/)
            .map(line => `<div class="apple-lyrics-line">${html(line)}</div>`)
            .join('');
        return;
    }
    boxEl.innerHTML = '<div class="apple-lyrics-empty">当前曲目暂无歌词。</div>';
}
function updateAppleLyricsHighlight() {
    if (!state.nowPlaying || state.lyricsType !== 'synced' || !state.lyricsLines.length) {
        state.lyricsActiveIndex = -1;
        renderAppleLyrics();
        return;
    }
    const currentMs = Math.max(0, Math.floor(Number(state.elapsedSec || 0) * 1000));
    let idx = -1;
    for (let i = 0; i < state.lyricsLines.length; i += 1) {
        const ts = Number(state.lyricsLines[i]?.ts_ms || 0);
        if (ts <= currentMs) idx = i;
        else break;
    }
    if (idx !== state.lyricsActiveIndex) {
        state.lyricsActiveIndex = idx;
        renderAppleLyrics();
    }
}
function loadAppleLyrics(trackId) {
    const safeTrackId = String(trackId || '').trim();
    if (!safeTrackId) {
        resetAppleLyricsState();
        renderAppleLyrics();
        return;
    }
    state.lyricsTrackId = safeTrackId;
    fetchJson(`/api/apple-audio/lyrics/${encodeURIComponent(safeTrackId)}`, {}, '歌词读取失败')
        .then(data => {
            const payload = data.lyrics || {};
            if (state.lyricsTrackId !== safeTrackId) return;
            state.lyricsType = String(payload.lyrics_type || 'none');
            state.lyricsPlain = String(payload.plain || '');
            state.lyricsLines = Array.isArray(payload.lines)
                ? payload.lines
                    .map(item => ({
                        ts_ms: Number(item.ts_ms || 0),
                        text: String(item.text || '')
                    }))
                    .filter(item => item.text)
                    .sort((a, b) => a.ts_ms - b.ts_ms)
                : [];
            state.lyricsActiveIndex = -1;
            updateAppleLyricsHighlight();
        })
        .catch(() => {
            if (state.lyricsTrackId !== safeTrackId) return;
            state.lyricsType = 'none';
            state.lyricsPlain = '';
            state.lyricsLines = [];
            state.lyricsActiveIndex = -1;
            renderAppleLyrics();
        });
}
function renderAppleNowPlaying() {
    const titleEl = document.getElementById('appleNowTitle');
    const metaEl = document.getElementById('appleNowMeta');
    const currentEl = document.getElementById('appleProgressCurrent');
    const totalEl = document.getElementById('appleProgressTotal');
    const fillEl = document.getElementById('appleProgressFill');
    const stateTag = document.getElementById('applePlaybackStateTag');
    const playBtn = document.getElementById('applePlayToggleBtn');
    const authEl = document.getElementById('appleAuthState');
    const coverWrap = document.getElementById('appleNowCoverWrap');
    if (!titleEl || !metaEl || !currentEl || !totalEl || !fillEl || !stateTag || !playBtn) return;
    if (!state.nowPlaying) {
        titleEl.innerText = '等待选择音源';
        metaEl.innerText = '请选择 NAS 曲目、播放列表，或接入远程播放代理。';
        currentEl.innerText = '00:00';
        totalEl.innerText = '00:00';
        fillEl.style.width = '0%';
        stateTag.innerText = '待连接';
        playBtn.innerText = '▶';
        if (authEl) authEl.innerText = state.stateCache?.auth_state || '未连接';
        if (coverWrap) {
            coverWrap.classList.remove('has-image');
            coverWrap.innerHTML = '<div class="apple-cover-badge">♪</div>';
        }
        return;
    }
    titleEl.innerText = state.nowPlaying.title;
    metaEl.innerText = `${state.nowPlaying.artist} · ${state.nowPlaying.album} · ${state.nowPlaying.tag}`;
    currentEl.innerText = formatAppleDuration(state.elapsedSec);
    totalEl.innerText = formatAppleDuration(state.nowPlaying.duration);
    if (state.nowPlaying.duration > 0) {
        fillEl.style.width = `${Math.min(100, (state.elapsedSec / state.nowPlaying.duration) * 100)}%`;
    } else {
        fillEl.style.width = '0%';
    }
    stateTag.innerText = state.isPlaying ? '播放中' : '已暂停';
    playBtn.innerText = state.isPlaying ? '❚❚' : '▶';
    if (authEl) authEl.innerText = state.stateCache?.auth_state || '未连接';
    if (coverWrap) {
        coverWrap.classList.toggle('has-image', !!(state.nowPlaying.coverAvailable && state.nowPlaying.coverUrl));
        coverWrap.innerHTML = getAppleCoverHtml(state.nowPlaying);
    }
    updateAppleLyricsHighlight();
}
function renderAppleOutputs() {
    const list = document.getElementById('appleOutputList');
    if (!list) return;
    if (!state.outputZones.length) {
        list.innerHTML = '<div class="apple-empty-note">暂未配置输出区域。可在配置页补充播放主机、输出模式和分区。</div>';
        return;
    }
    list.innerHTML = state.outputZones.map(zone => `
        <div class="apple-output-card ${zone.active ? 'active' : ''}">
            <div class="apple-output-title"><span>${zone.name}</span><span>${zone.level}</span></div>
            <div class="apple-output-meta">${zone.host} · ${zone.mode}</div>
        </div>
    `).join('');
}
function renderAppleResults(keyword='') {
    const list = document.getElementById('appleResultList');
    if (!list) return;
    const text = String(keyword || '').trim().toLowerCase();
    const sourceTracks = state.library
        .concat(text ? (state.remoteResults || []) : [])
        .map((item, index) => normalizeAppleTrack(item, index));
    const matched = sourceTracks.filter(item => {
        const categoryOk = state.categorySelected === 'all' || getAppleCategoryLabel(item.category) === state.categorySelected;
        if (!categoryOk) return false;
        if (!text) return true;
        const source = `${item.title} ${item.artist} ${item.album} ${item.tag} ${item.category}`.toLowerCase();
        return source.includes(text);
    });
    list.innerHTML = matched.length ? matched.map(item => `
        <div class="apple-track-row ${state.nowPlaying && state.nowPlaying.id === item.id ? 'playing' : ''}">
            <div class="apple-track-art">${getAppleRowArtHtml(item)}</div>
            <div class="apple-track-copy">
                <div class="title">${html(item.title)}</div>
                <div class="meta">${html(item.artist)} · ${html(item.album)} · ${formatAppleDuration(item.duration)} · ${html(item.sourceLabel)}</div>
            </div>
            <div class="apple-track-actions">
                <button class="apple-track-action primary" onclick="playAppleTrackNow('${html(item.id)}')">播放</button>
                <button class="apple-track-action" onclick="queueAppleTrack('${html(item.id)}')">加入</button>
            </div>
        </div>
    `).join('') : '<div class="apple-empty-note">没有找到匹配曲目。可以换个关键词，或检查后端播放代理配置。</div>';
}
function searchAppleSources(keyword='') {
    const text = String(keyword || '').trim();
    renderAppleResults(text);
    if (state.searchTimer) window.clearTimeout(state.searchTimer);
    if (!text) {
        state.remoteResults = [];
        renderAppleResults('');
        return;
    }
    const seq = ++state.searchSeq;
    state.searchTimer = window.setTimeout(() => {
        fetchJson(`/api/apple-audio/search?q=${encodeURIComponent(text)}&source=all&limit=30`, {}, '音乐搜索失败')
            .then(data => {
                if (seq !== state.searchSeq) return;
                state.remoteResults = Array.isArray(data.jamendo) ? data.jamendo.map((item, index) => normalizeAppleTrack(item, index)) : [];
                renderAppleResults(text);
            })
            .catch(err => {
                console.warn('Jamendo search failed', err);
            });
    }, 360);
}
function renderAppleQueue() {
    const list = document.getElementById('appleQueueList');
    const heroCount = document.getElementById('appleQueueCountHero');
    if (heroCount) heroCount.innerText = state.queue.length;
    if (!list) return;
    list.innerHTML = state.queue.length ? state.queue.map((item, index) => `
        <div class="apple-track-row">
            <div class="apple-track-art">${getAppleRowArtHtml(item)}</div>
            <div class="apple-track-copy">
                <div class="title">${index + 1}. ${html(item.title)}</div>
                <div class="meta">${html(item.artist)} · 下一步可映射到节目单 / 场景联动</div>
            </div>
            <button class="apple-track-action" onclick="promoteAppleTrack(${index})">${index === 0 ? '下一首' : '提前'}</button>
        </div>
    `).join('') : '<div class="apple-empty-note">当前队列为空。你可以从左侧检索结果中添加曲目。</div>';
}
function queueAppleTrack(trackId) {
    postJson('/api/apple-audio/queue', { track_id: trackId }, '加入播放队列失败')
        .then(data => {
            if (!data.success) {
                notify(data.message || data.msg || '加入播放队列失败', true);
                return;
            }
            syncAppleState(data.state);
            notify(`已加入队列：${state.queue[state.queue.length - 1]?.title || trackId}`);
        })
        .catch(err => notify(translateError(err?.message, '加入播放队列失败'), true));
}
function findAppleTrackById(trackId) {
    const safeId = String(trackId || '');
    return (state.library || []).concat(state.remoteResults || [], state.queue || [])
        .map((item, index) => normalizeAppleTrack(item, index))
        .find(item => item.id === safeId);
}
function playAppleTrackNow(trackId) {
    postJson('/api/apple-audio/queue', { track_id: trackId, play_now: true }, '播放曲目失败')
        .then(data => {
            if (!data.success) {
                notify(data.message || data.msg || '播放曲目失败', true);
                return;
            }
            syncAppleState(data.state);
            const track = state.nowPlaying || findAppleTrackById(trackId);
            playAppleTrackInBrowser(track);
        })
        .catch(err => notify(translateError(err?.message, '播放曲目失败'), true));
}
function promoteAppleTrack(index) {
    if (index < 0 || index >= state.queue.length) return;
    postJson('/api/apple-audio/queue/promote', { index }, '调整队列顺序失败')
        .then(data => {
            if (!data.success) {
                notify(data.message || data.msg || '调整队列顺序失败', true);
                return;
            }
            const title = state.queue[index]?.title || '当前曲目';
            syncAppleState(data.state);
            notify(`已调整为优先播放：${title}`);
        })
        .catch(err => notify(translateError(err?.message, '调整队列顺序失败'), true));
}
function clearAppleQueue() {
    postJson('/api/apple-audio/queue/clear', {}, '清空播放队列失败')
        .then(data => {
            if (!data.success) {
                notify(data.message || data.msg || '清空播放队列失败', true);
                return;
            }
            syncAppleState(data.state);
            notify('播放队列已清空');
        })
        .catch(err => notify(translateError(err?.message, '清空播放队列失败'), true));
}
function appleTransport(action) {
    postJson('/api/apple-audio/transport', { action }, '音乐播放器控制失败')
        .then(data => {
            if (!data.success) {
                notify(data.message || data.msg || '音乐播放器控制失败', true);
                return;
            }
            const beforeTrackId = state.nowPlaying ? state.nowPlaying.id : '';
            syncAppleState(data.state);
            const afterTrackId = state.nowPlaying ? state.nowPlaying.id : '';
            if (action === 'toggle') {
                if (state.isPlaying && state.nowPlaying) playAppleTrackInBrowser(state.nowPlaying);
                else pauseAppleBrowserAudio();
            } else if (['next', 'prev'].includes(action) && state.nowPlaying) {
                if (afterTrackId !== beforeTrackId || action === 'prev') playAppleTrackInBrowser(state.nowPlaying);
            }
            const actionMap = {
                toggle: state.isPlaying ? '已开始播放' : '已暂停播放',
                next: '已切到下一首',
                prev: '已回到当前曲目开头',
                favorite: `已收藏：${state.nowPlaying ? state.nowPlaying.title : '当前曲目'}`
            };
            notify(actionMap[action] || '操作已执行');
        })
        .catch(err => notify(translateError(err?.message, '音乐播放器控制失败'), true));
}
function syncAppleState(nextStatePayload) {
    const nextState = nextStatePayload || {};
    const prevTrackId = state.nowPlaying ? state.nowPlaying.id : '';
    state.stateCache = nextState;
    state.library = Array.isArray(nextState.library) ? nextState.library.map((item, index) => normalizeAppleTrack(item, index)) : state.library;
    state.outputZones = Array.isArray(nextState.outputs) ? nextState.outputs.map((item, index) => ({
        id: String(item.id || `zone_${index}`),
        name: String(item.name || `区域 ${index + 1}`),
        host: String(item.host || nextState.player_host || '未指定主机'),
        mode: String(item.mode || nextState.output_mode || '默认输出'),
        level: String(item.level || '--'),
        active: !!item.active
    })) : [];
    state.queue = Array.isArray(nextState.queue) ? nextState.queue.map((item, index) => normalizeAppleTrack(item, index)) : [];
    state.nowPlaying = nextState.current_track ? normalizeAppleTrack(nextState.current_track, 0) : null;
    state.isPlaying = !!nextState.is_playing;
    state.elapsedSec = Number(nextState.elapsed_sec || 0);
    renderAppleScanProgress(nextState.scan || {});
    renderAppleCategoryFilters();
    renderAppleNowPlaying();
    renderAppleOutputs();
    renderAppleQueue();
    renderAppleResults(document.getElementById('appleSearchInput') ? document.getElementById('appleSearchInput').value : '');
    const nextTrackId = state.nowPlaying ? state.nowPlaying.id : '';
    if (!nextTrackId) {
        resetAppleLyricsState();
        renderAppleLyrics();
    } else if (nextTrackId !== prevTrackId) {
        loadAppleLyrics(nextTrackId);
    } else {
        updateAppleLyricsHighlight();
    }
}
function openAppleAudioConfig() {
    if (!canOpenConfig()) {
        notify('当前账号无配置中心访问权限', true);
        return;
    }
    window.location.href = '/config#tab-univ';
}
function loadAppleAudioStatus(force = false) {
    if (state.stateLoading && !force) return;
    state.stateLoading = true;
    fetchJson('/api/apple-audio/status', {}, '音乐播放器状态读取失败')
        .then(data => {
            const nextState = data.state || {};
            state.library = Array.isArray(nextState.library) ? nextState.library : state.library;
            syncAppleState(nextState);
        })
        .catch(err => console.error('音乐播放器状态更新失败', err))
        .finally(() => {
            state.stateLoading = false;
        });
}
function initAppleAudioDemo() {
    renderAppleAudioPage();
    loadAppleAudioStatus(true);
}

    const api = {
        renderAppleAudioPage,
        formatAppleDuration,
        normalizeAppleTrack,
        getAppleCategoryLabel,
        renderAppleCategoryFilters,
        setAppleCategoryFilter,
        renderAppleScanProgress,
        getAppleCoverHtml,
        getAppleRowArtHtml,
        resetAppleLyricsState,
        renderAppleLyrics,
        updateAppleLyricsHighlight,
        loadAppleLyrics,
        renderAppleNowPlaying,
        renderAppleOutputs,
        renderAppleResults,
        searchAppleSources,
        renderAppleQueue,
        queueAppleTrack,
        playAppleTrackNow,
        promoteAppleTrack,
        clearAppleQueue,
        appleTransport,
        syncAppleState,
        openAppleAudioConfig,
        loadAppleAudioStatus,
        initAppleAudioDemo,
    };

    SmartCenter.appleAudio = Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.apple-audio', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/apple-audio.js',
        });
    }

    Object.assign(global, api);
})(window);
