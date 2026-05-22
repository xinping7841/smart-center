// AI_MODULE: m32r_view
// AI_PURPOSE: M32R 虚拟控台页面，展示连接、通道、主输出和模板控制。
// AI_BOUNDARY: 不直接发 OSC；控制走 /api/m32r/*。
// AI_DATA_FLOW: /api/m32r/status/templates -> 虚拟控台 DOM。
// AI_RUNTIME: 独立 M32R 页面加载。
// AI_RISK: 中，控制会影响现场音频输出。
// AI_SEARCH_KEYWORDS: m32r, mixer, osc, channel, main, template.

(function installSmartCenterM32R(global) {
    "use strict";

const I18N = {
    zh: {
        title: "M32R 虚拟控台",
        subtitle: "官方风格 Setup + Mixer + 回读状态 + 音乐播放器联动。",
        back: "返回主页",
        refresh: "刷新",
        conn: "连接状态",
        mode: "模式",
        mixerHost: "目标地址",
        lastRx: "最后回读",
        tabMixer: "调音台",
        tabSetup: "设置",
        tabRouting: "路由",
        tabMeter: "电平",
        tabApple: "音乐播放器",
        prev: "上一组",
        next: "下一组",
        mainBus: "主输出",
        mainFader: "主推子",
        mainState: "主状态",
        detailHint: "点击通道条后可编辑名称、推子、Pan 及 Tone 参数。",
        channelDetail: "通道详情",
        name: "名称",
        scribble: "标记",
        chFader: "通道推子",
        chPan: "通道 Pan",
        channelOn: "通道开启",
        saveLabel: "保存名称",
        applyBasic: "应用基础参数",
        gateEnabled: "门限启用",
        gateThreshold: "门限阈值 dB",
        eqEnabled: "均衡启用",
        eqMidFreq: "均衡中频 Hz",
        dynEnabled: "压缩启用",
        dynThreshold: "压缩阈值 dB",
        send1: "发送 Bus1",
        send2: "发送 Bus2",
        applyTone: "应用 Tone 参数",
        connectCfg: "连接配置",
        mixerName: "控台名称",
        udpPort: "UDP 端口",
        visibleChannels: "显示通道数",
        bankStart: "起始通道",
        pollMs: "轮询间隔 ms",
        keepaliveSec: "保活秒",
        syncDirection: "同步方向",
        autoConnect: "自动连接",
        autoSync: "自动同步",
        connect: "连接",
        demo: "演示模式",
        disconnect: "断开",
        saveCfg: "保存配置",
        discover: "发现设备",
        syncNow: "立即同步",
        refreshChannels: "刷新通道",
        setupNote: "回读来源标记: live(真机), estimated(估算), local(本地模板)。",
        localIps: "本机 IP",
        feedbackSource: "反馈来源",
        templateOps: "模板操作",
        templateName: "模板名",
        templateList: "模板列表",
        saveTemplate: "保存",
        loadTemplate: "加载",
        renameTemplate: "重命名",
        deleteTemplate: "删除",
        discoveredMixers: "已发现/已记录控台",
        model: "型号",
        firmware: "固件",
        online: "在线",
        action: "操作",
        routeAppleToM32: "音乐播放器到 M32 映射",
        provider: "Provider",
        playerMode: "Player 模式",
        playerHost: "Player 主机",
        outputMode: "输出模式",
        routeLeftCh: "左声道 CH",
        routeRightCh: "右声道 CH",
        routeLabel: "标签",
        prepareLevel: "预设电平",
        prepareMainOn: "同时打开 Main",
        saveAppleCfg: "保存映射",
        prepareM32: "准备 M32 通道",
        syncAndReadback: "同步与回读",
        routeNote: "OSC 只负责参数控制与状态回读，不承载音频流。音频需通过 USB / Dante / 线路输入到 M32。",
        meterOverview: "电平总览",
        appleStatus: "音乐播放器状态",
        playPause: "播放/暂停",
        prevTrack: "上一首",
        nextTrack: "下一首",
        favorite: "收藏",
        outputs: "输出设备",
        queue: "播放队列",
        clearQueue: "清空队列",
        searchLibrary: "搜索曲库",
        search: "搜索",
        quickCount: "显示推子数",
        using: "使用中",
        offline: "离线",
        onlineText: "在线",
        connected: "已连接",
        disconnected: "未连接",
        modeLive: "真机",
        modeDemo: "演示",
        modeOffline: "离线"
    },
    en: {
        title: "M32R Virtual Console",
        subtitle: "Official-style Setup + Mixer + readback status + music player integration.",
        back: "Back",
        refresh: "Refresh",
        conn: "Connection",
        mode: "Mode",
        mixerHost: "Host",
        lastRx: "Last RX",
        tabMixer: "Mixer",
        tabSetup: "Setup",
        tabRouting: "Routing",
        tabMeter: "Meter",
        tabApple: "Music Player",
        prev: "Prev",
        next: "Next",
        mainBus: "Main Bus",
        mainFader: "Main Fader",
        mainState: "Main State",
        detailHint: "Select a strip to edit name, fader, pan, and tone parameters.",
        channelDetail: "Channel Detail",
        name: "Name",
        scribble: "Scribble",
        chFader: "Channel Fader",
        chPan: "Channel Pan",
        channelOn: "Channel On",
        saveLabel: "Save Label",
        applyBasic: "Apply Basic",
        gateEnabled: "Gate Enabled",
        gateThreshold: "Gate Threshold dB",
        eqEnabled: "EQ Enabled",
        eqMidFreq: "EQ Mid Freq Hz",
        dynEnabled: "Dyn Enabled",
        dynThreshold: "Dyn Threshold dB",
        send1: "Send Bus1",
        send2: "Send Bus2",
        applyTone: "Apply Tone",
        connectCfg: "Connection Config",
        mixerName: "Mixer Name",
        udpPort: "UDP Port",
        visibleChannels: "Visible Channels",
        bankStart: "Bank Start",
        pollMs: "Poll Interval ms",
        keepaliveSec: "Keepalive sec",
        syncDirection: "Sync Direction",
        autoConnect: "Auto Connect",
        autoSync: "Auto Sync",
        connect: "Connect",
        demo: "Demo",
        disconnect: "Disconnect",
        saveCfg: "Save Config",
        discover: "Discover",
        syncNow: "Sync Now",
        refreshChannels: "Refresh Channels",
        setupNote: "Feedback source labels: live, estimated, local.",
        localIps: "Local IPs",
        feedbackSource: "Feedback Sources",
        templateOps: "Template Ops",
        templateName: "Template Name",
        templateList: "Template List",
        saveTemplate: "Save",
        loadTemplate: "Load",
        renameTemplate: "Rename",
        deleteTemplate: "Delete",
        discoveredMixers: "Discovered / Known Mixers",
        model: "Model",
        firmware: "Firmware",
        online: "Online",
        action: "Action",
        routeAppleToM32: "Music Player -> M32 Mapping",
        provider: "Provider",
        playerMode: "Player Mode",
        playerHost: "Player Host",
        outputMode: "Output Mode",
        routeLeftCh: "Left CH",
        routeRightCh: "Right CH",
        routeLabel: "Label",
        prepareLevel: "Prepare Level",
        prepareMainOn: "Prepare Main ON",
        saveAppleCfg: "Save Mapping",
        prepareM32: "Prepare M32",
        syncAndReadback: "Sync And Readback",
        routeNote: "OSC controls and reads parameters only. Audio must still route via USB / Dante / line input.",
        meterOverview: "Meter Overview",
        appleStatus: "Music Player Status",
        playPause: "Play/Pause",
        prevTrack: "Prev",
        nextTrack: "Next",
        favorite: "Favorite",
        outputs: "Outputs",
        queue: "Queue",
        clearQueue: "Clear Queue",
        searchLibrary: "Search Library",
        search: "Search",
        quickCount: "Visible Faders",
        using: "Using",
        offline: "Offline",
        onlineText: "Online",
        connected: "Connected",
        disconnected: "Disconnected",
        modeLive: "Live",
        modeDemo: "Demo",
        modeOffline: "Offline"
    }
};

let currentLang = localStorage.getItem("m32r_lang") || "zh";
let m32State = null;
let appleState = null;
let selectedCh = null;
let templateCache = [];

const el = (id) => document.getElementById(id);

function t(key) {
    const bag = I18N[currentLang] || I18N.en;
    return bag[key] || (I18N.en[key] || key);
}

function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((node) => {
        const key = node.getAttribute("data-i18n");
        node.textContent = t(key);
    });
    document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";
    el("langZh").classList.toggle("active", currentLang === "zh");
    el("langEn").classList.toggle("active", currentLang === "en");
}

function setLang(lang) {
    currentLang = (lang === "en") ? "en" : "zh";
    localStorage.setItem("m32r_lang", currentLang);
    applyI18n();
    if (m32State) renderM32(m32State);
    if (appleState) renderApple(appleState);
    renderTemplateMeta();
}

function showToast(msg, isError = false) {
    const toast = el("toast");
    toast.textContent = msg;
    toast.className = "toast show" + (isError ? " error" : "");
    setTimeout(() => {
        toast.className = "toast" + (isError ? " error" : "");
    }, 2200);
}

async function postJson(url, payload) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
    });
    const data = await res.json();
    if (!res.ok || data.success === false) {
        throw new Error(data.msg || data.message || "request failed");
    }
    return data;
}

function fmtTs(v) {
    if (!v) return "-";
    if (v === "demo") return "demo";
    return String(v).replace("T", " ").slice(0, 19);
}

function dbToPct(db) {
    const safe = Math.max(-90, Math.min(10, Number(db || -90)));
    return ((safe + 90) / 100) * 100;
}

function modeText(mode) {
    if (mode === "live") return t("modeLive");
    if (mode === "demo") return t("modeDemo");
    return t("modeOffline");
}

function secToClock(sec) {
    const s = Math.max(0, Number(sec || 0));
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${String(r).padStart(2, "0")}`;
}

function ensureSelectedChannel(state) {
    const channels = state.channels || [];
    if (!channels.length) {
        selectedCh = null;
        return;
    }
    if (!channels.find((c) => Number(c.channel) === Number(selectedCh))) {
        selectedCh = channels[0].channel;
    }
}

function renderTemplateMeta() {
    const select = el("tplSelect");
    const name = select ? String(select.value || "") : "";
    const item = templateCache.find((x) => String(x.name || "") === name);
    if (!item) {
        el("templateMeta").textContent = "-";
        return;
    }
    const start = Number(item.bank_start || 1);
    const count = Number(item.channel_count || 0);
    const end = count > 0 ? start + count - 1 : start;
    el("templateMeta").textContent = `${fmtTs(item.captured_at)} | CH ${String(start).padStart(2, "0")}-${String(end).padStart(2, "0")} | ${count}`;
}

function updateQuickCountButtons() {
    const current = Number(el("setupChannelCount").value || 16);
    const pairs = [
        ["count8Btn", 8],
        ["count16Btn", 16],
        ["count24Btn", 24],
        ["count32Btn", 32]
    ];
    pairs.forEach(([id, value]) => {
        const btn = el(id);
        if (!btn) return;
        btn.classList.toggle("active", current === value);
    });
}

function renderLocalIps(state) {
    const wrap = el("localIps");
    wrap.innerHTML = "";
    const ips = state.local_ips || [];
    if (!ips.length) {
        wrap.innerHTML = `<span class="chip">${t("offline")}</span>`;
        return;
    }
    ips.forEach((ip) => {
        const s = document.createElement("span");
        s.className = "chip";
        s.textContent = ip;
        wrap.appendChild(s);
    });
}

function renderFeedbackSources(state) {
    const wrap = el("feedbackSources");
    wrap.innerHTML = "";
    const src = state.feedback_sources || {};
    const keys = Object.keys(src);
    if (!keys.length) {
        wrap.innerHTML = `<span class="chip">${t("offline")}</span>`;
        return;
    }
    keys.forEach((k) => {
        const v = String(src[k] || "");
        const s = document.createElement("span");
        s.className = "chip" + (v === "live" ? " ok" : (v === "estimated" ? " warn" : ""));
        s.textContent = `${k}:${v}`;
        wrap.appendChild(s);
    });
}

function renderMixerRows(state) {
    const rows = el("mixerRows");
    rows.innerHTML = "";
    const list = state.discovered_mixers || [];
    if (!list.length) {
        rows.innerHTML = `<tr><td colspan="7">-</td></tr>`;
        return;
    }
    list.forEach((item, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td>${item.name || "-"}</td>
            <td>${item.host || "-"}</td>
            <td>${item.model || "M32R"}</td>
            <td>${item.firmware || "-"}</td>
            <td>${item.online ? t("onlineText") : t("offline")}</td>
            <td><button class="btn btn-dark" type="button" data-host="${item.host || ""}" data-name="${item.name || ""}">${t("using")}</button></td>
        `;
        const btn = tr.querySelector("button");
        btn.addEventListener("click", async () => {
            const host = btn.getAttribute("data-host");
            const name = btn.getAttribute("data-name");
            if (!host) return;
            el("setupHost").value = host;
            if (name) el("setupName").value = name;
            try {
                const payload = readSetupForm();
                const data = await postJson("/api/m32r/connect", payload);
                renderM32(data.state || data);
                showToast("OK");
            } catch (err) {
                showToast(err.message || "connect failed", true);
            }
        });
        rows.appendChild(tr);
    });
}

function renderMain(state) {
    const main = state.main || {};
    el("mainFader").value = Number(main.fader || 0.75);
    el("mainDb").textContent = `${Number(main.level_db || 0).toFixed(1)} dB`;
    el("mainMeterDb").textContent = `${Number(main.meter_db || -90).toFixed(1)} dB`;
    el("mainMeterFill").style.height = `${dbToPct(main.meter_db)}%`;
    const btn = el("mainToggleBtn");
    const on = !!main.on;
    btn.textContent = on ? "ON" : "MUTE";
    btn.className = `btn ${on ? "btn-green" : "btn-red"}`;
}

function renderDetail(channel) {
    if (!channel) return;
    el("detailCh").textContent = `CH ${String(channel.channel).padStart(2, "0")} | ${channel.name || ""}`;
    el("detailName").value = channel.name || "";
    el("detailScribble").value = channel.scribble || "";
    el("detailFader").value = Number(channel.fader || 0.75);
    el("detailPan").value = Number(channel.pan || 0.5);
    el("detailOn").checked = !!channel.on;

    const gate = channel.gate || {};
    el("gateEnabled").value = String(gate.enabled !== false);
    el("gateThreshold").value = Number(gate.threshold_db || -42);

    const eq = channel.eq || {};
    el("eqEnabled").value = String(eq.enabled !== false);
    el("eqMidFreq").value = Number(eq.mid_freq_hz || 3200);

    const dyn = channel.dyn || {};
    el("dynEnabled").value = String(dyn.enabled !== false);
    el("dynThreshold").value = Number(dyn.threshold_db || -18);

    const sends = channel.sends || {};
    el("send1").value = Number(sends.bus_1 || 0.55);
    el("send2").value = Number(sends.bus_2 || 0.45);
}

function renderChannels(state) {
    const wrap = el("channelGrid");
    wrap.innerHTML = "";
    const channels = state.channels || [];
    if (!channels.length) {
        wrap.innerHTML = `<div class="chip">${t("offline")}</div>`;
        return;
    }
    const start = channels[0].channel;
    const end = channels[channels.length - 1].channel;
    el("bankRange").textContent = `CH ${String(start).padStart(2, "0")}-${String(end).padStart(2, "0")}`;
    channels.forEach((ch) => {
        const div = document.createElement("div");
        div.className = "strip" + (Number(selectedCh) === Number(ch.channel) ? " active" : "");
        const isOn = !!ch.on;
        div.innerHTML = `
            <div class="strip-name">${ch.name || ("CH " + String(ch.channel).padStart(2, "0"))}</div>
            <div class="strip-scribble">${ch.scribble || "&nbsp;"}</div>
            <div class="chip">CH ${String(ch.channel).padStart(2, "0")}</div>
            <div class="meter"><div class="meter-fill" style="height:${dbToPct(ch.meter_db)}%"></div></div>
            <div class="mini-meter">${Number(ch.meter_db || -90).toFixed(1)} dB</div>
            <input class="fader" type="range" min="0" max="1" step="0.01" value="${Number(ch.fader || 0.75)}">
            <div class="mini-meter">${Number(ch.level_db || 0).toFixed(1)} dB</div>
            <button class="btn ${isOn ? "btn-green" : "btn-red"}" type="button">${isOn ? "ON" : "MUTE"}</button>
        `;

        div.addEventListener("click", (ev) => {
            if (ev.target.classList.contains("fader") || ev.target.tagName === "BUTTON") return;
            selectedCh = ch.channel;
            renderM32(m32State);
        });

        const fader = div.querySelector(".fader");
        fader.addEventListener("change", async (ev) => {
            try {
                const data = await postJson("/api/m32r/channel", {
                    channel: ch.channel,
                    action: "set_fader",
                    value: Number(ev.target.value)
                });
                renderM32(data.state || data);
            } catch (err) {
                showToast(err.message || "fader failed", true);
            }
        });

        const btn = div.querySelector("button");
        btn.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try {
                const data = await postJson("/api/m32r/channel", {
                    channel: ch.channel,
                    action: "mute_toggle"
                });
                renderM32(data.state || data);
            } catch (err) {
                showToast(err.message || "toggle failed", true);
            }
        });

        wrap.appendChild(div);
    });
    const current = channels.find((x) => Number(x.channel) === Number(selectedCh)) || channels[0];
    renderDetail(current);
}

function renderMeterView(state) {
    const wrap = el("meterGrid");
    wrap.innerHTML = "";
    const channels = state.channels || [];
    if (!channels.length) {
        wrap.innerHTML = `<span class="chip">${t("offline")}</span>`;
        return;
    }
    channels.forEach((ch) => {
        const div = document.createElement("div");
        div.className = "meter-card";
        div.innerHTML = `
            <div class="name">${ch.name || ("CH " + String(ch.channel).padStart(2, "0"))}</div>
            <div class="chip">CH ${String(ch.channel).padStart(2, "0")}</div>
            <div class="bar"><div style="height:${dbToPct(ch.meter_db)}%"></div></div>
            <div class="mini-meter">${Number(ch.meter_db || -90).toFixed(1)} dB</div>
        `;
        wrap.appendChild(div);
    });
}

function renderM32(state) {
    if (!state) return;
    m32State = state;
    ensureSelectedChannel(state);

    const conn = state.connected ? t("connected") : t("disconnected");
    const online = state.online ? t("onlineText") : t("offline");
    el("statusConn").textContent = `${conn} / ${online}`;
    el("statusMode").textContent = modeText(state.mode);
    el("statusHost").textContent = `${state.host || "-"}:${state.port || "-"}`;
    el("statusRx").textContent = fmtTs(state.last_rx_at);

    el("setupName").value = state.name || "";
    el("setupHost").value = state.host || "";
    el("setupPort").value = Number(state.port || 10023);
    el("setupChannelCount").value = Number((state.channels || []).length || Number(el("setupChannelCount").value || 8));
    const chs = state.channels || [];
    if (chs.length) {
        el("setupBankStart").value = Number(chs[0].channel || 1);
    }
    el("setupSyncDirection").value = state.sync_direction || "mixer_to_pc";
    el("routeSyncDirection").value = state.sync_direction || "mixer_to_pc";
    el("setupAutoConnect").checked = !!state.auto_connect;
    el("setupAutoSync").checked = !!state.auto_sync;
    updateQuickCountButtons();

    renderLocalIps(state);
    renderFeedbackSources(state);
    renderMixerRows(state);
    renderMain(state);
    renderChannels(state);
    renderMeterView(state);
}

function renderAppleOutputs(state) {
    const wrap = el("appleOutputs");
    wrap.innerHTML = "";
    const outputs = state.outputs || [];
    if (!outputs.length) {
        wrap.innerHTML = `<span class="chip">${t("offline")}</span>`;
        return;
    }
    outputs.forEach((o) => {
        const span = document.createElement("span");
        span.className = "chip" + (o.active ? " ok" : "");
        span.textContent = `${o.name || o.id || "-"} | ${o.level || "-"}`;
        wrap.appendChild(span);
    });
}

function renderAppleQueue(state) {
    const wrap = el("appleQueue");
    wrap.innerHTML = "";
    const queue = state.queue || [];
    if (!queue.length) {
        wrap.innerHTML = `<div class="chip">-</div>`;
        return;
    }
    queue.forEach((item, idx) => {
        const div = document.createElement("div");
        div.className = "music-item";
        div.innerHTML = `
            <div class="name">${item.title || "-"}</div>
            <div class="meta">${item.artist || "-"} | ${item.album || "-"}</div>
            <div class="row">
                <button class="btn btn-dark" type="button" data-promote="${idx}">Top</button>
            </div>
        `;
        const btn = div.querySelector("button");
        btn.addEventListener("click", async () => {
            try {
                const data = await postJson("/api/apple-audio/queue/promote", { index: idx });
                renderApple(data.state || data);
            } catch (err) {
                showToast(err.message || "queue promote failed", true);
            }
        });
        wrap.appendChild(div);
    });
}

function renderAppleSearch(results) {
    const wrap = el("appleSearchResults");
    wrap.innerHTML = "";
    const list = results || [];
    if (!list.length) {
        wrap.innerHTML = `<div class="chip">-</div>`;
        return;
    }
    list.forEach((item) => {
        const div = document.createElement("div");
        div.className = "music-item";
        div.innerHTML = `
            <div class="name">${item.title || "-"}</div>
            <div class="meta">${item.artist || "-"} | ${item.album || "-"}</div>
            <div class="row">
                <button class="btn btn-blue" type="button" data-q="${item.id || ""}">Queue</button>
                <button class="btn btn-green" type="button" data-play="${item.id || ""}">Play Now</button>
            </div>
        `;
        const qBtn = div.querySelector("[data-q]");
        const pBtn = div.querySelector("[data-play]");
        qBtn.addEventListener("click", async () => {
            try {
                const data = await postJson("/api/apple-audio/queue", { track_id: item.id, play_now: false });
                renderApple(data.state || data);
            } catch (err) {
                showToast(err.message || "queue failed", true);
            }
        });
        pBtn.addEventListener("click", async () => {
            try {
                const data = await postJson("/api/apple-audio/queue", { track_id: item.id, play_now: true });
                renderApple(data.state || data);
            } catch (err) {
                showToast(err.message || "play failed", true);
            }
        });
        wrap.appendChild(div);
    });
}

function renderApple(state) {
    if (!state) return;
    appleState = state;
    const cur = state.current_track || {};
    el("appleNow").textContent = `${cur.title || "-"} | ${cur.artist || "-"}`;
    el("appleElapsed").textContent = secToClock(state.elapsed_sec || 0);
    el("appleAuth").textContent = state.auth_state || "-";
    renderAppleOutputs(state);
    renderAppleQueue(state);
}

async function loadTemplates() {
    try {
        const res = await fetch("/api/m32r/templates");
        const data = await res.json();
        templateCache = data.templates || [];
        const sel = el("tplSelect");
        sel.innerHTML = "";
        if (!templateCache.length) {
            const op = document.createElement("option");
            op.value = "";
            op.textContent = "-";
            sel.appendChild(op);
        } else {
            templateCache.forEach((item) => {
                const op = document.createElement("option");
                op.value = item.name || "";
                op.textContent = item.name || "-";
                sel.appendChild(op);
            });
        }
        renderTemplateMeta();
    } catch (_) {
    }
}

async function loadM32() {
    try {
        const res = await fetch("/api/m32r/status");
        const data = await res.json();
        if (data && data.success === false) {
            throw new Error(data.msg || data.message || "status failed");
        }
        renderM32(data.state || data);
    } catch (err) {
        showToast(err.message || "status failed", true);
    }
}

async function loadApple() {
    try {
        const res = await fetch("/api/apple-audio/status");
        const data = await res.json();
        renderApple(data.state || data);
    } catch (_) {
    }
}

function readSetupForm() {
    return {
        name: String(el("setupName").value || "").trim(),
        host: String(el("setupHost").value || "").trim(),
        port: Number(el("setupPort").value || 10023),
        channel_count: Number(el("setupChannelCount").value || 8),
        bank_start: Number(el("setupBankStart").value || 1),
        poll_interval_ms: Number(el("setupPollMs").value || 1200),
        keepalive_sec: Number(el("setupKeepaliveSec").value || 5),
        auto_connect: !!el("setupAutoConnect").checked,
        auto_sync: !!el("setupAutoSync").checked,
        sync_direction: String(el("setupSyncDirection").value || "mixer_to_pc")
    };
}

async function connectMixer(demo = false) {
    const payload = readSetupForm();
    if (demo) payload.demo_mode = true;
    const data = await postJson("/api/m32r/connect", payload);
    renderM32(data.state || data);
}

function bindEvents() {
    el("langZh").addEventListener("click", () => setLang("zh"));
    el("langEn").addEventListener("click", () => setLang("en"));
    el("backBtn").addEventListener("click", () => { window.location.href = "/"; });
    el("refreshBtn").addEventListener("click", async () => {
        await loadM32();
        await loadApple();
        showToast("OK");
    });

    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const view = btn.getAttribute("data-view");
            document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
            const target = document.getElementById(`view-${view}`);
            if (target) target.classList.add("active");
        });
    });

    el("bankPrevBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/bank", { direction: "prev" });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "bank prev failed", true);
        }
    });
    el("bankNextBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/bank", { direction: "next" });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "bank next failed", true);
        }
    });
    el("jump1Btn").addEventListener("click", () => jumpBank(1));
    el("jump2Btn").addEventListener("click", () => jumpBank(9));
    el("jump3Btn").addEventListener("click", () => jumpBank(17));
    el("jump4Btn").addEventListener("click", () => jumpBank(25));
    el("count8Btn").addEventListener("click", () => setQuickChannelCount(8));
    el("count16Btn").addEventListener("click", () => setQuickChannelCount(16));
    el("count24Btn").addEventListener("click", () => setQuickChannelCount(24));
    el("count32Btn").addEventListener("click", () => setQuickChannelCount(32));

    el("mainFader").addEventListener("change", async (ev) => {
        try {
            const data = await postJson("/api/m32r/main", { action: "set_fader", value: Number(ev.target.value) });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "main fader failed", true);
        }
    });
    el("mainToggleBtn").addEventListener("click", async () => {
        try {
            const on = !(m32State && m32State.main && m32State.main.on);
            const data = await postJson("/api/m32r/main", { action: "set_on", on });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "main toggle failed", true);
        }
    });

    el("saveLabelBtn").addEventListener("click", async () => {
        if (!selectedCh) return;
        try {
            const data = await postJson("/api/m32r/channel", {
                channel: selectedCh,
                action: "set_label",
                name: String(el("detailName").value || "").trim(),
                scribble: String(el("detailScribble").value || "").trim()
            });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "label save failed", true);
        }
    });

    el("applyBasicBtn").addEventListener("click", async () => {
        if (!selectedCh) return;
        try {
            const onData = await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_on", on: !!el("detailOn").checked });
            renderM32(onData.state || onData);
            const fData = await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_fader", value: Number(el("detailFader").value || 0.75) });
            renderM32(fData.state || fData);
            const pData = await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_pan", value: Number(el("detailPan").value || 0.5) });
            renderM32(pData.state || pData);
        } catch (err) {
            showToast(err.message || "basic apply failed", true);
        }
    });

    el("applyToneBtn").addEventListener("click", async () => {
        if (!selectedCh) return;
        try {
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "gate", key: "enabled", value: el("gateEnabled").value === "true" });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "gate", key: "threshold_db", value: Number(el("gateThreshold").value || -42) });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "eq", key: "enabled", value: el("eqEnabled").value === "true" });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "eq", key: "mid_freq_hz", value: Number(el("eqMidFreq").value || 3200) });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "dyn", key: "enabled", value: el("dynEnabled").value === "true" });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "dyn", key: "threshold_db", value: Number(el("dynThreshold").value || -18) });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "sends", key: "bus_1", value: Number(el("send1").value || 0.55) });
            await postJson("/api/m32r/channel", { channel: selectedCh, action: "set_detail", section: "sends", key: "bus_2", value: Number(el("send2").value || 0.45) });
            await loadM32();
        } catch (err) {
            showToast(err.message || "tone apply failed", true);
        }
    });

    el("connectBtn").addEventListener("click", async () => {
        try {
            await connectMixer(false);
            showToast("OK");
        } catch (err) {
            showToast(err.message || "connect failed", true);
        }
    });
    el("demoBtn").addEventListener("click", async () => {
        try {
            await connectMixer(true);
            showToast("OK");
        } catch (err) {
            showToast(err.message || "demo failed", true);
        }
    });
    el("disconnectBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/disconnect", {});
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "disconnect failed", true);
        }
    });
    el("saveCfgBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/config", readSetupForm());
            renderM32(data.state || data);
            showToast("OK");
        } catch (err) {
            showToast(err.message || "save config failed", true);
        }
    });
    el("discoverBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/discover", {});
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "discover failed", true);
        }
    });
    el("syncBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/sync", { direction: String(el("setupSyncDirection").value || "mixer_to_pc") });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "sync failed", true);
        }
    });
    el("refreshChBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/refresh", {});
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "refresh failed", true);
        }
    });

    el("tplSelect").addEventListener("change", renderTemplateMeta);
    el("tplSaveBtn").addEventListener("click", async () => {
        const name = String(el("tplName").value || "").trim() || "unnamed_template";
        try {
            const data = await postJson("/api/m32r/template/save", { name });
            templateCache = data.templates || [];
            await loadTemplates();
            el("tplSelect").value = name;
            renderTemplateMeta();
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "template save failed", true);
        }
    });
    el("tplApplyBtn").addEventListener("click", async () => {
        const name = String(el("tplSelect").value || "").trim();
        if (!name) return;
        try {
            const data = await postJson("/api/m32r/template/apply", { name });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "template load failed", true);
        }
    });
    el("tplRenameBtn").addEventListener("click", async () => {
        const oldName = String(el("tplSelect").value || "").trim();
        const newName = String(el("tplName").value || "").trim();
        if (!oldName || !newName) return;
        try {
            const data = await postJson("/api/m32r/template/rename", { old_name: oldName, new_name: newName });
            templateCache = data.templates || [];
            await loadTemplates();
            el("tplSelect").value = newName;
            renderTemplateMeta();
        } catch (err) {
            showToast(err.message || "template rename failed", true);
        }
    });
    el("tplDeleteBtn").addEventListener("click", async () => {
        const name = String(el("tplSelect").value || "").trim();
        if (!name) return;
        try {
            const data = await postJson("/api/m32r/template/delete", { name });
            templateCache = data.templates || [];
            await loadTemplates();
        } catch (err) {
            showToast(err.message || "template delete failed", true);
        }
    });

    el("routeSyncBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/m32r/sync", { direction: String(el("routeSyncDirection").value || "mixer_to_pc") });
            renderM32(data.state || data);
        } catch (err) {
            showToast(err.message || "sync failed", true);
        }
    });

    el("routeSaveBtn").addEventListener("click", async () => {
        try {
            await postJson("/api/apple-audio/config", {
                provider: String(el("routeProvider").value || "").trim(),
                player_mode: String(el("routePlayerMode").value || "").trim(),
                player_host: String(el("routePlayerHost").value || "").trim(),
                output_mode: String(el("routeOutputMode").value || "").trim(),
                m32_channel_left: Number(el("routeLeft").value || 17),
                m32_channel_right: Number(el("routeRight").value || 18),
                m32_label: String(el("routeLabel").value || "").trim(),
                m32_prepare_level: Number(el("routePrepareLevel").value || 0.68),
                m32_prepare_main: !!el("routePrepareMain").checked
            });
            await loadApple();
            showToast("OK");
        } catch (err) {
            showToast(err.message || "apple config failed", true);
        }
    });

    el("routePrepareBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/apple-audio/m32/prepare", {});
            renderApple(data.apple_state || appleState);
            renderM32(data.m32_state || m32State);
        } catch (err) {
            showToast(err.message || "prepare failed", true);
        }
    });

    el("routeSyncDirection").addEventListener("change", () => {
        el("setupSyncDirection").value = el("routeSyncDirection").value;
    });
    el("setupSyncDirection").addEventListener("change", () => {
        el("routeSyncDirection").value = el("setupSyncDirection").value;
    });

    el("appleToggleBtn").addEventListener("click", () => appleTransport("toggle"));
    el("applePrevBtn").addEventListener("click", () => appleTransport("prev"));
    el("appleNextBtn").addEventListener("click", () => appleTransport("next"));
    el("appleFavBtn").addEventListener("click", () => appleTransport("favorite"));
    el("appleClearQueueBtn").addEventListener("click", async () => {
        try {
            const data = await postJson("/api/apple-audio/queue/clear", {});
            renderApple(data.state || data);
        } catch (err) {
            showToast(err.message || "clear queue failed", true);
        }
    });
    el("appleSearchBtn").addEventListener("click", doAppleSearch);
    el("appleSearchInput").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") doAppleSearch();
    });
}

async function doAppleSearch() {
    const q = String(el("appleSearchInput").value || "").trim();
    try {
        const res = await fetch(`/api/apple-audio/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        renderAppleSearch(data.results || []);
    } catch (err) {
        showToast(err.message || "search failed", true);
    }
}

async function appleTransport(action) {
    try {
        const data = await postJson("/api/apple-audio/transport", { action });
        renderApple(data.state || data);
    } catch (err) {
        showToast(err.message || "transport failed", true);
    }
}

async function jumpBank(start) {
    try {
        const data = await postJson("/api/m32r/bank", { direction: "set", bank_start: Number(start) });
        renderM32(data.state || data);
    } catch (err) {
        showToast(err.message || "bank jump failed", true);
    }
}

async function setQuickChannelCount(count) {
    try {
        const safe = Math.max(1, Math.min(32, Number(count || 16)));
        const currentBank = Number(el("setupBankStart").value || 1);
        const maxStart = Math.max(1, 33 - safe);
        el("setupChannelCount").value = safe;
        el("setupBankStart").value = Math.max(1, Math.min(currentBank, maxStart));
        updateQuickCountButtons();
        const data = await postJson("/api/m32r/config", readSetupForm());
        renderM32(data.state || data);
        showToast("OK");
    } catch (err) {
        showToast(err.message || "set channel count failed", true);
    }
}

async function bootstrap() {
    bindEvents();
    setLang(currentLang);
    updateQuickCountButtons();
    await Promise.all([loadM32(), loadApple(), loadTemplates()]);
    global.setInterval(loadM32, 1400);
    global.setInterval(loadApple, 2200);
}

const api = {
    appleTransport,
    connectMixer,
    doAppleSearch,
    jumpBank,
    loadApple,
    loadM32,
    loadTemplates,
    renderApple,
    renderM32,
    setLang,
    setQuickChannelCount,
};

const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
SmartCenter.m32r = Object.assign({}, SmartCenter.m32r || {}, api);
if (typeof SmartCenter.registerModule === "function") {
    SmartCenter.registerModule("m32r", {
        kind: "view",
        view: "m32r",
        exports: Object.keys(api),
        source: "static/js/views/m32r.js",
    });
}

bootstrap();
})(window);
