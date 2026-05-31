// AI_MODULE: proxy_view
// AI_PURPOSE: 代理监控页面，展示链路测试、客户端、121 网卡 Mbps 流量和代理状态。
// AI_BOUNDARY: 不配置 squid；只展示 /api/proxy/status。
// AI_DATA_FLOW: /api/proxy/status -> 代理状态卡片。
// AI_RUNTIME: 代理页面轮询。
// AI_RISK: 中，状态错误会影响网络排障。
// AI_SEARCH_KEYWORDS: proxy, squid, traffic, Mbps, node-121.

(function installSmartCenterProxy(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.proxy = Object.assign({ statusCache: {} }, SmartCenter.proxy || {});

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

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function fetchStatus() {
        if (typeof global.fetchJson === 'function') {
            return global.fetchJson('/api/proxy/status', {}, '代理状态读取失败');
        }
        return fetch('/api/proxy/status').then(response => response.json());
    }

    function formatTime(value) {
        return typeof global.formatServerTime === 'function'
            ? global.formatServerTime(value)
            : (value || '--');
    }

    function getStatusMeta(payload) {
        if (typeof global.getDeviceStatusMeta === 'function') {
            return global.getDeviceStatusMeta(payload, { onlineText: '在线', staleText: '陈旧', errorText: '异常', offlineText: '离线' });
        }
        return { level: payload?.online ? 'online' : 'offline', chipClass: payload?.online ? 'online' : 'error', text: payload?.online ? '在线' : '离线' };
    }

    function getActiveViewId() {
        return typeof global.getActiveViewId === 'function' ? global.getActiveViewId() : '';
    }

    function formatProxyRateText(value) {
        const num = Number(value || 0);
        const mbps = Number.isFinite(num) ? num / 1000 / 1000 : 0;
        if (mbps <= 0) return '0.000 Mbps';
        return `${mbps < 1 ? mbps.toFixed(3) : mbps.toFixed(2)} Mbps`;
    }

    function formatProxyBytesText(value) {
        const num = Number(value || 0);
        if (!Number.isFinite(num) || num <= 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let size = num;
        let idx = 0;
        while (size >= 1024 && idx < units.length - 1) {
            size /= 1024;
            idx += 1;
        }
        return idx === 0 ? `${Math.round(size)} ${units[idx]}` : `${size.toFixed(1)} ${units[idx]}`;
    }

    function getProxyEndpoint(payload = {}) {
        const host = String(payload.host || payload?.config?.host || '--');
        const port = Number(payload.port || payload?.config?.port || 0);
        return port > 0 ? `${host}:${port}` : host;
    }

    function getProxyRequiredCheck(payload = {}) {
        if (payload.required_check && typeof payload.required_check === 'object') return payload.required_check;
        const checks = Array.isArray(payload.checks) ? payload.checks : [];
        return checks.find(item => item && item.required) || checks.find(item => /google/i.test(String(item?.name || item?.url || ''))) || null;
    }

    function getProxyFlowSummary(payload = {}) {
        const traffic = payload.traffic || {};
        const clients = payload.clients || {};
        const trafficAvailable = !!traffic.available;
        const rxBps = trafficAvailable ? Number(traffic.rx_bps || 0) : Number(clients.download_bps || 0);
        const txBps = trafficAvailable ? Number(traffic.tx_bps || 0) : Number(clients.upload_bps || 0);
        return {
            rxText: trafficAvailable ? (traffic.rx_text || formatProxyRateText(rxBps)) : (clients.download_text || formatProxyRateText(rxBps)),
            txText: trafficAvailable ? (traffic.tx_text || formatProxyRateText(txBps)) : (clients.upload_text || formatProxyRateText(txBps)),
            source: trafficAvailable ? (traffic.source || '出口') : '客户端汇总',
            available: trafficAvailable || !!clients.available,
        };
    }

    function renderProxyPageShell() {
        const container = document.getElementById('view-proxy');
        if (!container || document.getElementById('proxy-client-table-body')) return false;
        container.innerHTML = `
            <div class="card proxy-hero-card">
                <div class="proxy-hero-head">
                    <div>
                        <div class="proxy-hero-title">公司代理监控</div>
                        <div class="proxy-hero-subtitle" id="proxy-detail-subtitle">正在读取 121 Squid 代理状态...</div>
                    </div>
                    <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;">
                        <span class="proxy-pill" id="proxy-detail-status">检测中</span>
                        <span class="proxy-pill" id="proxy-detail-endpoint">--</span>
                    </div>
                </div>
                <div class="proxy-hero-metrics">
                    <div class="proxy-hero-metric"><div class="label">站点探活</div><div class="value ok" id="proxy-detail-checks">--</div></div>
                    <div class="proxy-hero-metric"><div class="label">活跃 IP / 连接</div><div class="value blue" id="proxy-detail-active">--</div></div>
                    <div class="proxy-hero-metric"><div class="label">实时下行</div><div class="value" id="proxy-detail-rx">--</div></div>
                    <div class="proxy-hero-metric"><div class="label">实时上行</div><div class="value" id="proxy-detail-tx">--</div></div>
                </div>
            </div>
            <div class="proxy-page-grid" style="margin-top:14px;">
                <div class="card">
                    <div class="card-title">
                        <span>站点连通性</span>
                        <span style="font-size:12px; color:var(--text-sub);">Google / YouTube / ChatGPT / GitHub</span>
                    </div>
                    <div class="proxy-check-grid" id="proxy-check-grid">
                        <div class="proxy-card-note">正在加载探活结果...</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>出口流量</span>
                        <span style="font-size:12px; color:var(--text-sub);" id="proxy-traffic-source">--</span>
                    </div>
                    <div class="proxy-hero-metrics" style="grid-template-columns:repeat(2,minmax(0,1fr));">
                        <div class="proxy-hero-metric"><div class="label">下行</div><div class="value blue" id="proxy-traffic-rx">--</div></div>
                        <div class="proxy-hero-metric"><div class="label">上行</div><div class="value warn" id="proxy-traffic-tx">--</div></div>
                    </div>
                    <div class="proxy-card-note" id="proxy-traffic-note">用于判断代理出口是否真的在跑流量。</div>
                </div>
                <div class="card" style="grid-column:1/-1;">
                    <div class="card-title">
                        <span>代理客户端</span>
                        <span style="font-size:12px; color:var(--text-sub);" id="proxy-clients-note">只展示 IP、连接数与流量汇总，不展示访问网址。</span>
                    </div>
                    <div class="proxy-table-wrap">
                        <table class="proxy-client-table">
                            <thead>
                                <tr>
                                    <th>客户端 IP</th>
                                    <th>状态</th>
                                    <th>连接数</th>
                                    <th>实时下行</th>
                                    <th>实时上行</th>
                                    <th>近几分钟请求</th>
                                    <th>累计流量</th>
                                    <th>最后活跃</th>
                                </tr>
                            </thead>
                            <tbody id="proxy-client-table-body">
                                <tr><td colspan="8">正在加载代理客户端...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
        return true;
    }

    function renderDashboardProxySummary(payload = {}) {
        const statusEl = document.getElementById('dash-proxy-status');
        const metaEl = document.getElementById('dash-proxy-meta');
        const meta = getStatusMeta(payload);
        if (statusEl) {
            statusEl.textContent = meta.text;
            statusEl.className = `value ${meta.level === 'online' ? 'green' : (meta.level === 'stale' || meta.level === 'error' ? 'danger' : 'blue')}`;
        }
        if (metaEl) {
            const endpoint = getProxyEndpoint(payload);
            const healthy = Number(payload.healthy_target_count || 0);
            const total = Number(payload.check_count || 0);
            const checkedAt = formatTime(payload.last_checked_at || payload.updated_at);
            const lastErr = String(payload.last_error || payload.error || '').trim();
            const requiredCheck = getProxyRequiredCheck(payload);
            const googleOk = requiredCheck ? !!requiredCheck.healthy : !!payload.google_ok;
            const googleLatency = Number(requiredCheck?.latency_ms ?? payload.google_latency_ms);
            const googleCode = Number(requiredCheck?.status_code ?? payload.google_status_code);
            const clients = payload.clients || {};
            const flow = getProxyFlowSummary(payload);
            const googleHint = `${googleOk ? 'Google正常' : 'Google异常'}${Number.isFinite(googleLatency) && googleLatency > 0 ? ` ${googleLatency}ms` : ''}${Number.isFinite(googleCode) && googleCode > 0 ? `/${googleCode}` : ''}`;
            const clientHint = `IP ${Number(clients.active_client_count || 0)} / 连接 ${Number(clients.total_active_connections || 0)}`;
            const flowHint = `↓${flow.rxText} ↑${flow.txText}`;
            const checkHint = total > 0 ? `${healthy}/${total} 探活` : '无探活数据';
            metaEl.innerHTML = `${html(endpoint)} · ${html(googleHint)} · ${html(checkHint)} · ${html(clientHint)} · ${html(flowHint)} · ${html(checkedAt || '--')}${lastErr ? ` <br><strong>${html(lastErr)}</strong>` : ''}`;
        }
    }

    function renderProxyChecks(checks) {
        const grid = document.getElementById('proxy-check-grid');
        if (!grid) return;
        const items = Array.isArray(checks) ? checks : [];
        if (!items.length) {
            grid.innerHTML = '<div class="proxy-card-note">暂无站点探活数据。</div>';
            return;
        }
        grid.innerHTML = items.map(item => {
            const healthy = !!item.healthy;
            const latency = Number(item.latency_ms);
            const code = Number(item.status_code);
            const name = String(item.name || item.url || '--');
            const meta = [
                Number.isFinite(latency) && latency > 0 ? `${latency}ms` : '',
                Number.isFinite(code) && code > 0 ? `HTTP ${code}` : '',
                item.required ? '核心判定' : '',
            ].filter(Boolean).join(' · ') || (healthy ? '连通正常' : '暂无返回');
            const err = String(item.error || '').trim();
            return `<div class="proxy-check-card ${healthy ? 'ok' : 'error'}">
                <div class="proxy-check-name">
                    <span>${html(name)}</span>
                    <span class="proxy-pill ${healthy ? 'online' : 'error'}">${healthy ? '正常' : '异常'}</span>
                </div>
                <div class="proxy-check-meta">${html(meta)}${err ? `<br><strong style="color:#fecaca;">${html(err.slice(0, 90))}</strong>` : ''}</div>
            </div>`;
        }).join('');
    }

    function renderProxyClients(clientsPayload = {}) {
        const noteEl = document.getElementById('proxy-clients-note');
        const body = document.getElementById('proxy-client-table-body');
        if (!body) return;
        const clients = Array.isArray(clientsPayload.clients) ? clientsPayload.clients : [];
        const recentSeconds = Number(clientsPayload.recent_seconds || 300);
        const recentText = recentSeconds >= 60 ? `${Math.round(recentSeconds / 60)} 分钟` : `${recentSeconds} 秒`;
        if (noteEl) {
            const err = String(clientsPayload.error || '').trim();
            noteEl.textContent = clientsPayload.available === false
                ? `客户端采集暂不可用${err ? '：' + err : ''}`
                : `近 ${recentText} 汇总，只展示 IP、连接数与流量，不展示访问网址。`;
        }
        if (!clientsPayload.enabled) {
            body.innerHTML = '<tr><td colspan="8">客户端监控未启用。</td></tr>';
            return;
        }
        if (!clientsPayload.available) {
            body.innerHTML = `<tr><td colspan="8">${html(String(clientsPayload.error || '客户端采集暂不可用'))}</td></tr>`;
            return;
        }
        if (!clients.length) {
            body.innerHTML = '<tr><td colspan="8">当前没有检测到正在使用代理的局域网客户端。</td></tr>';
            return;
        }
        body.innerHTML = clients.map(item => {
            const active = !!item.active;
            const lastSeen = item.last_seen_at ? formatTime(item.last_seen_at) : '--';
            const rx = item.rx_text || formatProxyRateText(item.rx_bps);
            const tx = item.tx_text || formatProxyRateText(item.tx_bps);
            const recentBytes = item.recent_bytes_text || formatProxyBytesText(item.recent_bytes);
            return `<tr>
                <td><span class="proxy-client-ip">${html(item.ip || '--')}</span></td>
                <td><span class="proxy-client-active-dot ${active ? 'on' : ''}"></span>${active ? '活跃' : '最近使用'}</td>
                <td>${html(String(item.active_connections ?? 0))}</td>
                <td>${html(rx)}</td>
                <td>${html(tx)}</td>
                <td>${html(String(item.recent_requests ?? 0))}</td>
                <td>${html(recentBytes)}</td>
                <td>${html(lastSeen)}</td>
            </tr>`;
        }).join('');
    }

    function renderProxyDetail(payload = {}) {
        renderProxyPageShell();
        const meta = getStatusMeta(payload);
        const clients = payload.clients || {};
        const traffic = payload.traffic || {};
        const flow = getProxyFlowSummary(payload);
        const healthy = Number(payload.healthy_target_count || 0);
        const total = Number(payload.check_count || 0);
        const endpoint = getProxyEndpoint(payload);
        const statusEl = document.getElementById('proxy-detail-status');
        if (statusEl) {
            statusEl.textContent = meta.text;
            statusEl.className = `proxy-pill ${meta.chipClass}`;
        }
        setText('proxy-detail-endpoint', endpoint);
        setText('proxy-detail-subtitle', `${endpoint} · 更新 ${formatTime(payload.last_checked_at || payload.updated_at)}`);
        setText('proxy-detail-checks', total > 0 ? `${healthy}/${total}` : '--');
        setText('proxy-detail-active', `${Number(clients.active_client_count || 0)} / ${Number(clients.total_active_connections || 0)}`);
        setText('proxy-detail-rx', flow.rxText);
        setText('proxy-detail-tx', flow.txText);
        setText('proxy-traffic-rx', flow.rxText);
        setText('proxy-traffic-tx', flow.txText);
        const sourceLabelMap = { nic_ssh: '172出口网卡', snmp: 'SNMP参考', server: '服务器上报', '客户端汇总': '客户端汇总' };
        setText('proxy-traffic-source', `${sourceLabelMap[flow.source] || flow.source}${traffic.ifname ? ' · ' + traffic.ifname : ''}`);
        const trafficNote = document.getElementById('proxy-traffic-note');
        if (trafficNote) {
            const err = String(traffic.error || '').trim();
            trafficNote.textContent = traffic.available
                ? `来源 ${traffic.host || traffic.device_id || traffic.source || '--'} · 更新时间 ${formatTime(traffic.updated_at || payload.updated_at)}`
                : `SNMP 出口流量暂不可用，当前用客户端连接汇总兜底${err ? '：' + err : ''}`;
        }
        renderProxyChecks(payload.checks || []);
        renderProxyClients(clients);
    }

    function updateProxyStatus() {
        return fetchStatus()
            .then(data => {
                const payload = data || {};
                state.statusCache = payload;
                renderDashboardProxySummary(payload);
                if (getActiveViewId() === 'proxy') renderProxyDetail(payload);
            })
            .catch(err => {
                const statusEl = document.getElementById('dash-proxy-status');
                const metaEl = document.getElementById('dash-proxy-meta');
                if (statusEl) {
                    statusEl.textContent = '异常';
                    statusEl.className = 'value danger';
                }
                if (metaEl) {
                    metaEl.textContent = String(err?.message || '代理状态读取失败');
                }
                if (getActiveViewId() === 'proxy') {
                    renderProxyDetail({
                        online: false,
                        status_level: 'error',
                        error: String(err?.message || '代理状态读取失败'),
                        checks: [],
                        clients: { enabled: true, available: false, clients: [], error: String(err?.message || '代理状态读取失败') },
                        traffic: { available: false, rx_bps: 0, tx_bps: 0, error: String(err?.message || '代理状态读取失败') },
                    });
                }
            });
    }

    const api = {
        formatProxyRateText,
        formatProxyBytesText,
        getProxyEndpoint,
        getProxyRequiredCheck,
        getProxyFlowSummary,
        renderProxyPageShell,
        renderDashboardProxySummary,
        renderProxyChecks,
        renderProxyClients,
        renderProxyDetail,
        updateProxyStatus,
    };

    SmartCenter.proxy = Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.proxy', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/proxy.js',
        });
    }

    Object.assign(global, api);
})(window);
