        function saveDoorRegionSelection(regionPayload) {
            return fetchJsonLoose('/update_door_region', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(regionPayload)
            }, '保存检测区域失败').then(data => {
                showToast(data.msg || '检测区域已更新', data.status === 'error');
                if (data.status === 'error') {
                    throw new Error(data.msg || '保存检测区域失败');
                }
                return data;
            });
        }

        function requestDoorStatus() {
            return fetchJsonLoose('/get_door_status', {}, '读取门禁状态失败');
        }

        function postDoorAction(action) {
            return fetchJsonLoose(`/door_control/${action}`, {}, '门禁指令下发失败');
        }

        function postJsonLoose(url, payload, fallbackText='请求失败') {
            return fetchJsonLoose(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }, fallbackText);
        }

        refreshPowerSupplement = function(cabId, force = false) {
            const now = Date.now();
            const activeView = getActiveViewId();
            const minInterval = activeView === 'power' ? 15000 : 45000;
            if (!force && powerSupplementFetchAt[cabId] && (now - powerSupplementFetchAt[cabId] < minInterval)) return;
            if (powerSupplementInFlight[cabId]) return powerSupplementInFlight[cabId];
            powerSupplementFetchAt[cabId] = now;
            const logsReq = fetchJson(`/api/logs?cab=${cabId}`, {}, '强电日志读取失败')
                .then(logs => {
                    powerLogCache[cabId] = Array.isArray(logs) ? logs : [];
                    renderPowerDetailLogs(cabId, powerLogCache[cabId]);
                })
                .catch(err => console.error('强电日志更新失败', cabId, err));
            const historyReq = fetchJson(`/api/7days_energy?cab=${cabId}`, {}, '强电图表读取失败')
                .then(data => {
                    powerHistoryCache[cabId] = Array.isArray(data) ? data : [];
                    renderPowerEnergyChart(cabId, powerHistoryCache[cabId]);
                })
                .catch(err => console.error('强电图表更新失败', cabId, err));
            powerSupplementInFlight[cabId] = Promise.allSettled([logsReq, historyReq])
                .then(() => {
                    renderDashboardPowerCards();
                })
                .finally(() => {
                    delete powerSupplementInFlight[cabId];
                });
            return powerSupplementInFlight[cabId];
        };

        updateMeterCenter = function() {
            const requestSeq = ++meterCenterRequestSeq;
            const requestTarget = meterTrendTarget;
            const requestPeriod = meterTrendPeriod;
            fetchJson(`/api/meters?target=${encodeURIComponent(meterTrendTarget)}&period=${encodeURIComponent(meterTrendPeriod)}&days=35`, {}, '电表中心状态读取失败')
                .then(data => {
                    if (requestSeq !== meterCenterRequestSeq || requestTarget !== meterTrendTarget || requestPeriod !== meterTrendPeriod) return;
                    meterCenterCache = data || { summary: {}, meters: [], trend: [] };
                    const summary = meterCenterCache.summary || {};
                    const meters = normalizeMeterCardOrder(Array.isArray(meterCenterCache.meters) ? meterCenterCache.meters : []);
                    const grid = document.getElementById('meter-center-grid');
                    const totalEl = document.getElementById('meter-summary-total');
                    const onlineEl = document.getElementById('meter-summary-online');
                    const powerEl = document.getElementById('meter-summary-power');
                    const dailyEl = document.getElementById('meter-summary-daily');
                    const monthlyEl = document.getElementById('meter-summary-monthly');
                    const powerMetaEl = document.getElementById('meter-summary-power-meta');
                    const dailyMetaEl = document.getElementById('meter-summary-daily-meta');
                    const monthlyMetaEl = document.getElementById('meter-summary-monthly-meta');
                    const displayBadge = document.getElementById('meter-summary-badge-display');
                    const scopeBadge = document.getElementById('meter-summary-badge-scope');
                    const sourceBadge = document.getElementById('meter-summary-badge-source');
                    if (totalEl) totalEl.innerText = Number(summary.total || 0);
                    if (onlineEl) onlineEl.innerText = Number(summary.online || 0);
                    const cardTotalPower = Number(
                        summary.card_total_realtime_power
                        ?? summary.stable_total_realtime_power
                        ?? summary.estimated_total_realtime_power
                        ?? summary.total_realtime_power
                        ?? 0
                    );
                    if (powerEl) powerEl.innerText = cardTotalPower.toFixed(2);
                    if (dailyEl) dailyEl.innerText = Number(summary.total_daily_energy || 0).toFixed(1);
                    if (monthlyEl) monthlyEl.innerText = Number(summary.total_monthly_energy || 0).toFixed(1) + ' kWh';
                    if (displayBadge) {
                        const mode = String((configData.meter_statistics || {}).energy_display_mode || 'display').toLowerCase();
                        displayBadge.innerText = mode === 'raw' ? '原始累计值' : '运行口径';
                    }
                    if (scopeBadge) scopeBadge.innerText = `${Number(summary.online || 0)} / ${Number(summary.total || 0)} 在线`;
                    if (sourceBadge) {
                        const sourceMeta = resolveMeterSourceMeta(meterCenterCache);
                        sourceBadge.innerText = sourceMeta.text;
                        sourceBadge.title = sourceMeta.title || '';
                        sourceBadge.style.color = sourceMeta.color || '#f8fafc';
                    }
                    const dashPower = document.getElementById('dash-total-power');
                    const dashDaily = document.getElementById('dash-total-daily-energy');
                    const dashPowerMeta = document.getElementById('dash-total-power-meta');
                    const dashDailyMeta = document.getElementById('dash-total-daily-meta');
                    const dashStablePower = Number(
                        (meterCenterCache.dashboard_summary || {}).stable_power
                        ?? (meterCenterCache.dashboard_summary || {}).estimated_power
                        ?? (meterCenterCache.dashboard_summary || {}).power
                        ?? cardTotalPower
                        ?? 0
                    );
                    if (dashPower) dashPower.innerText = dashStablePower.toFixed(2);
                    if (dashDaily) dashDaily.innerText = Number((meterCenterCache.dashboard_summary || {}).daily_energy || 0).toFixed(1);
                    const compareToReference = (summary.compare_to_reference || {});
                    if (powerMetaEl) powerMetaEl.innerHTML = formatPowerSummaryMeta(summary);
                    if (dailyMetaEl) dailyMetaEl.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                    if (monthlyMetaEl) monthlyMetaEl.innerHTML = formatReferenceMeta(compareToReference.monthly_energy, ' kWh');
                    if (dashPowerMeta) dashPowerMeta.innerHTML = `单位 kW · ${formatPowerSummaryMeta(summary)}`;
                    if (dashDailyMeta) dashDailyMeta.innerHTML = formatReferenceMeta(compareToReference.daily_energy, ' kWh');
                    renderMeterTypeChips(summary.type_counts || {});
                    renderMeterTrendSelectors(meterCenterCache);
                    if (grid) {
                        grid.innerHTML = meters.length
                            ? meters.map(renderMeterCard).join('')
                            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">暂无可展示电表数据</div>';
                    }
                    const trendRows = (((meterCenterCache.trend_breakdown || {})[meterTrendPeriod === 'week' ? 'weekly' : (meterTrendPeriod === 'month' ? 'monthly' : 'daily')]) || []);
                    renderMeterTrendChart(trendRows);
                    renderDashboardEnergyTrend(trendRows, summary);
                })
                .catch(err => console.error('电表中心状态更新失败', err));
        };

        updateUpsStatus = function() {
            fetchJson('/api/ups/status', {}, 'UPS 状态读取失败')
                .then(data => {
                    upsStatusCache = data || {};
                    renderUpsCards();
                })
                .catch(err => console.error('UPS 状态更新失败', err));
        };

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
                    item.required ? '核心判定' : ''
                ].filter(Boolean).join(' · ') || (healthy ? '连通正常' : '暂无返回');
                const err = String(item.error || '').trim();
                return `<div class="proxy-check-card ${healthy ? 'ok' : 'error'}">
                    <div class="proxy-check-name">
                        <span>${escapeHtml(name)}</span>
                        <span class="proxy-pill ${healthy ? 'online' : 'error'}">${healthy ? '正常' : '异常'}</span>
                    </div>
                    <div class="proxy-check-meta">${escapeHtml(meta)}${err ? `<br><strong style="color:#fecaca;">${escapeHtml(err.slice(0, 90))}</strong>` : ''}</div>
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
                body.innerHTML = `<tr><td colspan="8">${escapeHtml(String(clientsPayload.error || '客户端采集暂不可用'))}</td></tr>`;
                return;
            }
            if (!clients.length) {
                body.innerHTML = '<tr><td colspan="8">当前没有检测到正在使用代理的局域网客户端。</td></tr>';
                return;
            }
            body.innerHTML = clients.map(item => {
                const active = !!item.active;
                const lastSeen = item.last_seen_at ? formatServerTime(item.last_seen_at) : '--';
                const rx = item.rx_text || formatProxyRateText(item.rx_bps);
                const tx = item.tx_text || formatProxyRateText(item.tx_bps);
                const recentBytes = item.recent_bytes_text || formatProxyBytesText(item.recent_bytes);
                return `<tr>
                    <td><span class="proxy-client-ip">${escapeHtml(item.ip || '--')}</span></td>
                    <td><span class="proxy-client-active-dot ${active ? 'on' : ''}"></span>${active ? '活跃' : '最近使用'}</td>
                    <td>${escapeHtml(String(item.active_connections ?? 0))}</td>
                    <td>${escapeHtml(rx)}</td>
                    <td>${escapeHtml(tx)}</td>
                    <td>${escapeHtml(String(item.recent_requests ?? 0))}</td>
                    <td>${escapeHtml(recentBytes)}</td>
                    <td>${escapeHtml(lastSeen)}</td>
                </tr>`;
            }).join('');
        }
        function renderProxyDetail(payload = {}) {
            const meta = getDeviceStatusMeta(payload, { onlineText: '在线', staleText: '陈旧', errorText: '异常', offlineText: '离线' });
            const clients = payload.clients || {};
            const traffic = payload.traffic || {};
            const flow = getProxyFlowSummary(payload);
            const healthy = Number(payload.healthy_target_count || 0);
            const total = Number(payload.check_count || 0);
            const endpoint = getProxyEndpoint(payload);
            const setText = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
            const statusEl = document.getElementById('proxy-detail-status');
            if (statusEl) {
                statusEl.textContent = meta.text;
                statusEl.className = `proxy-pill ${meta.chipClass}`;
            }
            setText('proxy-detail-endpoint', endpoint);
            setText('proxy-detail-subtitle', `${endpoint} · 更新 ${formatServerTime(payload.last_checked_at || payload.updated_at)}`);
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
                    ? `来源 ${traffic.host || traffic.device_id || traffic.source || '--'} · 更新时间 ${formatServerTime(traffic.updated_at || payload.updated_at)}`
                    : `SNMP 出口流量暂不可用，当前用客户端连接汇总兜底${err ? '：' + err : ''}`;
            }
            renderProxyChecks(payload.checks || []);
            renderProxyClients(clients);
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
        function updateProxyStatus() {
            fetchJson('/api/proxy/status', {}, '代理状态读取失败')
                .then(data => {
                    const payload = data || {};
                    proxyStatusCache = payload;
                    const statusEl = document.getElementById('dash-proxy-status');
                    const metaEl = document.getElementById('dash-proxy-meta');
                    const meta = getDeviceStatusMeta(payload, { onlineText: '在线', staleText: '陈旧', errorText: '异常', offlineText: '离线' });
                    if (statusEl) {
                        statusEl.textContent = meta.text;
                        statusEl.className = `value ${meta.level === 'online' ? 'green' : (meta.level === 'stale' || meta.level === 'error' ? 'danger' : 'blue')}`;
                    }
                    if (metaEl) {
                        const endpoint = getProxyEndpoint(payload);
                        const healthy = Number(payload.healthy_target_count || 0);
                        const total = Number(payload.check_count || 0);
                        const checkedAt = formatServerTime(payload.last_checked_at || payload.updated_at);
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
                        metaEl.innerHTML = `${escapeHtml(endpoint)} · ${escapeHtml(googleHint)} · ${escapeHtml(checkHint)} · ${escapeHtml(clientHint)} · ${escapeHtml(flowHint)} · ${escapeHtml(checkedAt || '--')}${lastErr ? ` <br><strong>${escapeHtml(lastErr)}</strong>` : ''}`;
                    }
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
                            traffic: { available: false, rx_bps: 0, tx_bps: 0, error: String(err?.message || '代理状态读取失败') }
                        });
                    }
                });
        }

        sendUpsShutdown = function(id, delay) {
            if (!ensurePermission('ups.control', '操作 UPS')) return;
            if (!confirm(`确定向 UPS 下发延时关机命令 S${delay} 吗？`)) return;
            postJsonLoose('/api/ups/control', { id, action: 'shutdown', delay }, 'UPS 指令下发失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || 'UPS 指令执行失败', true);
                        return;
                    }
                    showToast(`UPS 指令已下发: ${data.command || 'S<n>'}`);
                })
                .catch(err => showToast(translateApiError(err?.message, 'UPS 指令下发失败'), true));
        };

        updateSequencerStatus = function() {
            fetchJson('/api/sequencer/status', {}, '时序电源状态读取失败')
                .then(data => {
                    sequencerStatusCache = data || {};
                    renderSequencerCards();
                })
                .catch(err => console.error('时序电源状态更新失败', err));
        };

        fireSequencerAction = function(id, action, channel = null) {
            if (!ensurePermission('sequencer.control', '操作时序电源')) return;
            showToast('时序电源指令下发中...', false);
            postJsonLoose('/api/sequencer/control', { id, action, channel }, '时序电源指令下发失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '执行失败', true);
                        return;
                    }
                    showToast(`执行成功${data.command ? ' - ' + data.command : ''}`);
                    if (data.device && Array.isArray(data.device.channels)) {
                        sequencerStatusCache = sequencerStatusCache || {};
                        sequencerStatusCache.devices = Array.isArray(sequencerStatusCache.devices) ? sequencerStatusCache.devices : [];
                        const idx = sequencerStatusCache.devices.findIndex(item => item && item.id === data.device.id);
                        if (idx >= 0) sequencerStatusCache.devices[idx] = data.device;
                        else sequencerStatusCache.devices.push(data.device);
                        renderSequencerCards();
                    }
                    [350, 900, 1800, 3500].forEach(delay => setTimeout(updateSequencerStatus, delay));
                    setTimeout(updateDashboardLogs, 300);
                })
                .catch(err => showToast(translateApiError(err?.message, '网络请求失败'), true));
        };

        updateDashboardLogs = function() {
            fetchJson('/api/logs', {}, '首页系统日志读取失败')
                .then(logs => {
                    const nextLogs = Array.isArray(logs) ? logs : [];
                    const changed = buildDashboardLogSignature(nextLogs) !== buildDashboardLogSignature(dashboardLogsCache || []);
                    dashboardLogsCache = nextLogs;
                    if (changed) renderDashboardLogs(dashboardLogsCache);
                })
                .catch(err => console.error('首页系统日志更新失败', err));
        };

        updateDoorStatus = function(force = false) {
            const now = Date.now();
            if (!force && now - lastDoorStatusFetchAt < 1000) return Promise.resolve(null);
            lastDoorStatusFetchAt = now;
            return requestDoorStatus()
                .then(data => {
                    if (data.status !== 'success') return null;
                    const cameraMap = {};
                    (Array.isArray(data.cameras) ? data.cameras : []).forEach(item => {
                        const key = String(item?.key || '').trim();
                        if (key) cameraMap[key] = item;
                    });
                    doorCameraStatusCache = cameraMap;
                    if (data.view_slots && typeof data.view_slots === 'object') doorViewSlots = data.view_slots;
                    if (data.regions && typeof data.regions === 'object') doorRegionsCache = data.regions;
                    const leftCameraKey = getDoorSlotCameraKey('left');
                    const rightCameraKey = getDoorSlotCameraKey('right');
                    setDoorSlotVisual('left', cameraMap[leftCameraKey] || {});
                    setDoorSlotVisual('right', cameraMap[rightCameraKey] || {});
                    updateDoorSlotLabels();
                    renderDoorNetworkSummary();
                    syncDoorVideoSources(force);
                    const statusEl = document.getElementById('doorStatus');
                    if (statusEl) {
                        statusEl.textContent = data.msg;
                        statusEl.className = `tag door-status-${data.door_status}`;
                    }
                    const debugTip = document.getElementById('debugTip');
                    if (debugTip) {
                        const offlineCount = Object.values(cameraMap).filter(item => item && item.online === false && item.configured).length;
                        debugTip.textContent = offlineCount > 0 ? `视觉辅助，${offlineCount} 路视频链路异常 | ${data.diff}` : `视觉辅助识别 | ${data.diff}`;
                    }
                    if (!updateDashboardDoorStatusFromEnv()) updateDashboardDoorStatusFromVision(data);
                    return data;
                })
                .catch(() => {
                    const statusEl = document.getElementById('doorStatus');
                    if (statusEl) statusEl.textContent = '检测器离线';
                    setDoorSlotVisual('left', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                    setDoorSlotVisual('right', { configured: true, online: false, last_error: 'status_fetch_failed', last_error_text: '状态读取失败' });
                    renderDoorNetworkSummary();
                    return null;
                });
        };

        captureWizard = function(state, statusId) {
            const btn = event.target;
            const oldText = btn.innerHTML;
            btn.innerHTML = '正在保存...';
            btn.disabled = true;
            fetchJsonLoose(`/api/ai_wizard/capture/${state}`, { method: 'POST' }, '拍照保存失败')
                .then(data => {
                    showToast(data.msg || '拍照完成', data.status === 'error');
                    if (data.status === 'success') {
                        const statusSpan = document.getElementById(statusId);
                        if (statusSpan) {
                            statusSpan.innerHTML = '已保存';
                            statusSpan.style.color = 'var(--success)';
                        }
                        if (state === 'closed') {
                            document.getElementById('step1-card').style.opacity = '0.4';
                            document.getElementById('step1-card').style.pointerEvents = 'none';
                            document.getElementById('step2-card').style.opacity = '1';
                            document.getElementById('step2-card').style.pointerEvents = 'auto';
                        }
                    }
                })
                .catch(() => showToast('拍照保存失败', true))
                .finally(() => {
                    btn.innerHTML = oldText;
                    btn.disabled = false;
                });
        };

        applyAiCalibration = function() {
            const btn = document.getElementById('btnWizardRecord');
            btn.textContent = '正在提取并计算...';
            btn.disabled = true;
            fetchJsonLoose('/api/ai_wizard/apply_model', { method: 'POST' }, '生成模型失败')
                .then(data => {
                    showToast(data.msg || '模型生成完成', data.status === 'error');
                    if (data.status === 'success') setTimeout(closeWizard, 1500);
                })
                .catch(() => showToast('生成模型失败', true))
                .finally(() => {
                    btn.disabled = false;
                    btn.innerHTML = '一键生成 AI 推演模型';
                });
        };

        controlDoor = function(action) {
            if (!ensurePermission('door.control', '控制门禁')) return;
            postDoorAction(action)
                .then(data => showToast(data.msg || '门禁指令已下发', data.status === 'error'))
                .catch(() => showToast('指令下发失败', true));
        };

        doPowerStart = function(cabId) {
            if (!ensurePermission('power.control', '执行强电启动')) return;
            setPowerCabinetDesiredState(cabId, true);
            fetchJsonLoose(`/api/onekey_start?cab=${cabId}`, {}, '启动请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerCabinetDesiredState(cabId);
                        showToast(data.msg || '启动失败', true);
                        return;
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    showToast(data.verified === false ? (data.msg || '启动指令已下发，状态稍后刷新') : '启动指令已发送');
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerCabinetDesiredState(cabId);
                    showToast(translateApiError(err?.message, '启动请求失败'), true);
                });
        };

        doPowerStop = function(cabId, msg) {
            if (!ensurePermission('power.control', '执行强电停止')) return;
            if (!confirm(msg)) return;
            setPowerCabinetDesiredState(cabId, false);
            fetchJsonLoose(`/api/onekey_stop?cab=${cabId}`, {}, '停止请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerCabinetDesiredState(cabId);
                        showToast(data.msg || '停止失败', true);
                        return;
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    showToast(data.verified === false ? (data.msg || '停止指令已下发，状态稍后刷新') : '停止指令已下发');
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerCabinetDesiredState(cabId);
                    showToast(translateApiError(err?.message, '停止请求失败'), true);
                });
        };

        togglePower = function(cabId, chNum) {
            if (!ensurePermission('power.control', '切换强电通道')) return;
            pwrPending[cabId] = pwrPending[cabId] || {};
            if (pwrPending[cabId][chNum]) {
                showToast('该回路正在执行中，请等待状态确认');
                return;
            }
            const status = getPowerChannelStatus(cabId, chNum);
            if (status === null) return;
            if (status && !confirm(configData.cabinets[cabId].ui_text.confirm_single_off)) return;
            const targetState = !status;
            pwrLocks[cabId][chNum] = Date.now();
            pwrPending[cabId][chNum] = true;
            setPowerDesiredState(cabId, chNum, targetState);
            renderPwrChannel(cabId, chNum);
            postJsonLoose('/api/set', { cab: cabId, ch: chNum, on: targetState }, '强电控制请求失败')
                .then(data => {
                    if (!data.ok) {
                        clearPowerDesiredState(cabId, chNum);
                        renderPwrChannel(cabId, chNum);
                        showToast(data.msg || '强电控制失败', true);
                        return;
                    }
                    if (data.verified === false && data.msg) {
                        showToast(data.msg);
                    }
                    applyPowerStatusSnapshot(cabId, data.status);
                    updatePowerData();
                    setTimeout(() => updatePowerData(), 450);
                })
                .catch(err => {
                    clearPowerDesiredState(cabId, chNum);
                    renderPwrChannel(cabId, chNum);
                    showToast(translateApiError(err?.message, '强电控制请求失败'), true);
                })
                .finally(() => {
                    delete pwrPending[cabId][chNum];
                    renderPwrChannel(cabId, chNum);
                    setTimeout(() => { delete pwrLocks[cabId][chNum]; }, POWER_CHANNEL_LOCK_MS);
                });
        };

        updatePowerData = async function() {
            if (powerFetchInFlight) return powerFetchInFlight;
            powerFetchInFlight = (async () => {
            let onlineCount = 0;
            const activeView = getActiveViewId();
            const shouldLoadDetails = activeView === 'power';
            const shouldLoadDashboard = activeView === 'dashboard' || isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick');
            const supplementCabIds = resolveVisiblePowerSupplementCabIds(activeView);
            const supplementCabIdSet = new Set(supplementCabIds);
            const cabinetEntries = Array.isArray(configData.cabinets) ? Array.from(configData.cabinets.entries()) : [];
            const responses = [];
            for (const [cabId] of cabinetEntries) {
                try {
                    const d = await fetchJson(`/api/status?cab=${cabId}`, {}, '强电状态读取失败');
                    responses.push({ cabId, data: d, error: null });
                } catch (err) {
                    responses.push({ cabId, data: null, error: err });
                }
            }
            for (const [cabId, cab] of cabinetEntries) {
                const result = responses.find(item => item.cabId === cabId) || {};
                const d = result.data;
                if (!d) {
                    console.error('强电状态更新失败', cabId, result.error);
                    continue;
                }
                try {
                    applyPowerStatusSnapshot(cabId, d);
                    if (d.comm_status) onlineCount++;
                    const statusEl = document.getElementById(`commStatus_${cabId}`);
                    if (statusEl) {
                        statusEl.className = d.comm_status ? 'tag normal' : 'tag error';
                        statusEl.innerText = d.comm_status ? '通讯正常' : '通讯异常';
                    }
                    const wm = document.getElementById(`workMode_${cabId}`);
                    if (wm) wm.innerText = d.work_mode || '未知';
                    const sourceLabelEl = document.getElementById(`sourceLabel_${cabId}`);
                    if (sourceLabelEl) sourceLabelEl.innerText = d.source_label || (d.data_source || '电表服务');
                    const displayAddressEl = document.getElementById(`displayAddress_${cabId}`);
                    if (displayAddressEl) displayAddressEl.innerText = d.display_address || d.gateway_base || `${cab.ip}:${cab.port}`;
                    const deviceAddressEl = document.getElementById(`deviceAddress_${cabId}`);
                    if (deviceAddressEl) deviceAddressEl.innerText = d.device_address || `${cab.ip}:${cab.port}`;
                    ['va','vb','vc','ia','ib','ic','energy','dailyEnergy','monthEnergy','realtimePower','temp','humi'].forEach(k => {
                        const el = document.getElementById(`${k}_${cabId}`);
                        const val = d[k === 'energy'
                            ? 'electric_energy'
                            : (k === 'dailyEnergy'
                                ? 'daily_energy'
                                : (k === 'monthEnergy'
                                    ? 'monthly_energy'
                                    : (k === 'realtimePower'
                                        ? 'realtime_power'
                                        : (k === 'temp'
                                            ? 'cabinet_temp'
                                            : (k === 'humi'
                                                ? 'cabinet_humidity'
                                                : k.replace('v', 'voltage_').replace('i', 'current_'))))))];
                        if (el && val !== undefined) {
                            el.innerText = parseFloat(val).toFixed(k.includes('i') || k.includes('v') || k === 'temp' || k === 'humi' || k.includes('Energy') ? 1 : 2);
                        }
                    });
                } catch (err) {
                    console.error('强电状态更新失败', cabId, err);
                }
            }
            const supplementChanged =
                supplementCabIds.length !== powerVisibleSupplementCabIds.length
                || supplementCabIds.some((cabId, idx) => cabId !== powerVisibleSupplementCabIds[idx]);
            if (shouldLoadDetails || shouldLoadDashboard) {
                for (const cabId of supplementCabIds) {
                    refreshPowerSupplement(cabId, supplementChanged);
                }
            }
            for (const oldCabId of powerVisibleSupplementCabIds) {
                if (!supplementCabIdSet.has(oldCabId)) {
                    delete powerSupplementInFlight[oldCabId];
                }
            }
            powerVisibleSupplementCabIds = supplementCabIds.slice();
            renderDashboardPowerCards();
            renderDashboardPowerCompact();
            const pOnline = document.getElementById('dash-power-online');
            if (pOnline) pOnline.innerText = onlineCount;
            resizePowerCharts();
            })();
            try {
                return await powerFetchInFlight;
            } finally {
                powerFetchInFlight = null;
            }
        };

        toggleLight = function(devId, chNum) {
            if (!ensurePermission('light.control', '切换灯光通道')) return;
            if (!lightOnlineStates[devId]) {
                showToast('设备离线，无法控制通道', true);
                return;
            }
            const rawStatus = getLightChannelStateFromSources(devId, chNum, {});
            const status = getLightChannelStateFromSources(devId, chNum, {});
            if (status === null || status === undefined) {
                showToast('设备在线，但该通道状态待确认，请稍后再试或使用动作按钮', true);
                return;
            }
            const targetState = !status;
            lightLocks[devId][chNum] = Date.now();
            lightStates[devId][chNum] = targetState;
            renderLightChannel(devId, chNum);
            postJsonLoose('/api/light/control', { type: 'single', device_id: devId, channel: chNum, is_open: targetState }, '灯光控制请求失败')
                .then(data => {
                    if (!data.success) {
                        lightStates[devId][chNum] = rawStatus;
                        renderLightChannel(devId, chNum);
                        showToast(data.msg || '灯光控制失败', true);
                        return;
                    }
                    if (Array.isArray(data.channels)) {
                        data.channels.forEach((st, idx) => {
                            lightStates[devId][idx + 1] = st;
                            renderLightChannel(devId, idx + 1);
                        });
                    }
                    showToast(data.verified === false ? '灯光指令已发送，等待状态确认' : '灯光控制成功');
                    setTimeout(() => updateLightData(), 600);
                })
                .catch(() => {
                    lightStates[devId][chNum] = rawStatus;
                    renderLightChannel(devId, chNum);
                    showToast('灯光控制请求失败', true);
                })
                .finally(() => {
                    setTimeout(() => { delete lightLocks[devId][chNum]; }, 1200);
                });
        };

        triggerLightAction = function(devId, actionName, label) {
            if (!ensurePermission('light.control', `执行灯光动作 ${label || actionName}`)) return;
            postJsonLoose('/api/light/control', { type: 'action', device_id: devId, action: actionName }, `${label || actionName} 请求失败`)
                .then(data => {
                    if (!data.success) {
                        showToast(data.msg || `${label || actionName} 执行失败`, true);
                        return;
                    }
                    if (Array.isArray(data.channels)) {
                        data.channels.forEach((st, idx) => {
                            lightStates[devId][idx + 1] = st;
                            renderLightChannel(devId, idx + 1);
                        });
                    }
                    showToast(data.verified === false ? `${label || actionName} 已下发，等待状态确认` : `${label || actionName} 已执行`);
                    setTimeout(() => updateLightData(), 700);
                })
                .catch(() => showToast(`${label || actionName} 请求失败`, true));
        };

        executeScene = function(sceneId, name) {
            if (!ensurePermission('light.control', '执行场景联动')) return;
            if (!confirm(`确定要触发全局联动场景 [${name}] 吗？`)) return;
            postJsonLoose('/api/light/control', { type: 'scene', scene_id: sceneId }, `场景联动 [${name}] 请求失败`)
                .then(data => {
                    if (!data.success) {
                        showToast(data.msg || `场景联动 [${name}] 执行失败`, true);
                        return;
                    }
                    showToast(`场景联动 [${name}] 触发成功`);
                    setTimeout(() => updateLightData(), 800);
                })
                .catch(() => showToast(`场景联动 [${name}] 请求失败`, true));
        };

        updateLightData = function() {
            fetchJson('/api/light/status', {}, '灯光状态读取失败')
                .then(d => {
                    let onlineCount = 0;
                    for (const devId in (d.online || {})) {
                        const extraMeta = (d.extras || {})[devId] || {};
                        const statusMeta = getDeviceStatusMeta({
                            online: !!d.online[devId],
                            status_level: extraMeta.status_level,
                            stale: extraMeta.stale,
                            poll_failures: extraMeta.poll_failures,
                            last_success_at: extraMeta.last_success_at,
                            last_checked_at: extraMeta.last_checked_at,
                            last_error: extraMeta.last_error,
                        }, { staleText: '陈旧', errorText: '异常' });
                        lightOnlineStates[devId] = statusMeta.isOnlineLike;
                        if (statusMeta.isOnlineLike) onlineCount++;
                        const tag = document.getElementById(`light-status-${devId}`);
                        if (tag) {
                            tag.className = statusMeta.chipClass === 'online' ? 'tag normal' : (statusMeta.chipClass === 'warning' ? 'tag warn' : 'tag error');
                            tag.innerText = statusMeta.text;
                            tag.title = statusMeta.note;
                        }
                        (d.channels?.[devId] || []).forEach((st, idx) => {
                            const chNum = idx + 1;
                            if (lightLocks[devId][chNum] && (Date.now() - lightLocks[devId][chNum] < 2000)) return;
                            lightStates[devId][chNum] = st;
                            renderLightChannel(devId, chNum);
                        });
                    }
                    const lOnline = document.getElementById('dash-light-online');
                    if (lOnline) lOnline.innerText = onlineCount;
                    renderDashboardLightCards(d);
                    renderDashboardLightCompact(d);
                })
                .catch(err => console.error('灯光状态更新失败', err));
            fetchJson('/api/light/logs', {}, '灯光日志读取失败')
                .then(logs => {
                    const logBox = document.getElementById('light-global-log');
                    if (!logBox) return;
                    let html = '';
                    (logs || []).forEach(log => {
                        html += `<div class="log-item"><span class="time">[${new Date(log.time).toLocaleTimeString('zh-CN',{hour12:false})}]</span><span class="msg">${log.operation.replace(/\[.*?\]\s*/,'')}</span></div>`;
                    });
                    if (logBox.innerHTML !== html) logBox.innerHTML = html;
                })
                .catch(err => console.error('灯光日志更新失败', err));
        };

        wakeServer = function(mac) {
            if (!ensurePermission('server.control', '唤醒服务器节点')) return;
            if (mac.startsWith('TEMP')) {
                showToast('没有真实 MAC 地址，无法发送网络唤醒', true);
                return;
            }
            if (!confirm('确定发送网络唤醒魔术包(WOL)吗？')) return;
            fetchJson('/api/wake/' + encodeURIComponent(mac), { method: 'POST' }, '唤醒请求失败')
                .then(result => {
                    const targets = Array.isArray(result?.targets) ? result.targets.length : 0;
                    showToast(targets ? `唤醒包已发出，广播目标 ${targets} 个` : '唤醒包已发出');
                    if (typeof burstRefreshServerData === 'function') burstRefreshServerData();
                })
                .catch(err => showToast(translateApiError(err?.message, '唤醒请求失败'), true));
        };

        sendServerCmd = function(mac, cmd) {
            if (!ensurePermission('server.control', '下发服务器指令')) return;
            const actionMap = { shutdown: '关机', restart: '重启', refresh: '刷新信息' };
            const actionName = actionMap[cmd] || cmd;
            const prompt = cmd === 'refresh' ? '确定要远程刷新此节点的硬件信息吗？' : `危险操作：确定要让此节点立刻【${actionName}】吗？`;
            if (!confirm(prompt)) return;
            postJsonLoose(`/api/machines/${mac}/command`, { command: cmd }, `指令 [${actionName}] 下发失败`)
                .then(() => {
                    markServerCommandPending(mac, cmd, actionName);
                    showToast(`指令 [${actionName}] 已进入下发队列`);
                    burstRefreshServerData();
                })
                .catch(err => showToast(translateApiError(err?.message, `指令 [${actionName}] 下发失败`), true));
        };

        moveServer = function(mac, direction) {
            if (!ensurePermission('server.control', '调整服务器排序')) return;
            const idx = globalServerList.findIndex(m => m.mac === mac);
            if (idx < 0) return;
            const newIdx = idx + direction;
            if (newIdx < 0 || newIdx >= globalServerList.length) return;
            const temp = globalServerList[idx];
            globalServerList[idx] = globalServerList[newIdx];
            globalServerList[newIdx] = temp;
            globalServerList.forEach((m, i) => { m.sort_order = i + 1; });
            postJsonLoose('/api/machines/sort', { macs: globalServerList.map(m => m.mac) }, '服务器排序保存失败')
                .then(() => updateServerData())
                .catch(err => {
                    showToast(translateApiError(err?.message, '服务器排序保存失败'), true);
                    updateServerData();
                });
        };

        function formatServerMetric(value, suffix = '%') {
            const num = Number(value);
            if (!Number.isFinite(num)) return `0${suffix}`;
            return `${num.toFixed(num % 1 ? 1 : 0)}${suffix}`;
        }
        function normalizeServerBytes(value) {
            const num = Number(value);
            return Number.isFinite(num) ? num : 0;
        }
        function formatNetworkMbps(kbPerSec) {
            const mbps = normalizeServerBytes(kbPerSec) * 8 / 1024;
            if (mbps >= 100) return mbps.toFixed(0);
            if (mbps >= 10) return mbps.toFixed(1);
            return mbps.toFixed(2).replace(/\.?0+$/, '');
        }
        function getNetworkPrimaryLabel(st) {
            const nic = st && typeof st.network_primary === 'object' ? st.network_primary : {};
            const rawName = String(nic.adapter_name || nic.name || '').trim();
            const desc = String(nic.adapter_description || nic.description || '').trim();
            const name = rawName && !rawName.includes('?') ? rawName : desc;
            const ip = String(nic.adapter_ip || nic.ip || '').trim();
            return [name, ip].filter(Boolean).join(' · ') || '主网卡';
        }
        function normalizeDisplayMac(value) {
            const compact = String(value || '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
            if (compact.length !== 12 || compact === '000000000000') return '';
            return compact.match(/.{1,2}/g).join('-');
        }
        function getServerPhysicalMac(m) {
            const st = m?.status || {};
            const agent = m?.agent_status || st.agent || {};
            const nic = st && typeof st.network_primary === 'object' ? st.network_primary : {};
            return normalizeDisplayMac(
                st.display_mac
                || st.physical_mac
                || nic.adapter_mac
                || nic.mac
                || agent.physical_mac
            );
        }
        function getServerIdentityLine(m) {
            const st = m?.status || {};
            const displayIp = m?.ip || '--';
            const primaryMac = String(m?.mac || '').trim();
            const physicalMac = getServerPhysicalMac(m);
            const isLocalId = primaryMac.toUpperCase().startsWith('LOCAL-');
            const isTempId = primaryMac.toUpperCase().startsWith('TEMP-');
            const displayMac = physicalMac || (!isTempId ? primaryMac : '');
            const suffix = displayMac ? ` | ${displayMac}` : '';
            const titleParts = [`IP: ${displayIp}`];
            if (physicalMac) titleParts.push(`物理MAC: ${physicalMac}`);
            if (primaryMac && isLocalId) titleParts.push(`节点ID: ${primaryMac}`);
            if (st.network_primary?.adapter_name) titleParts.push(`网卡: ${st.network_primary.adapter_name}`);
            return { text: `${displayIp}${suffix}`, title: titleParts.join(' / ') };
        }
        function isVirtualGpuName(name) {
            const text = String(name || '').toLowerCase();
            return text.includes('gameviewer')
                || text.includes('oray')
                || text.includes('virtual display')
                || text.includes('idddriver')
                || text.includes('remote display');
        }
        function compactGpuName(name) {
            let text = String(name || 'GPU')
                .replace(/^VGA compatible controller:\s*/i, '')
                .replace(/^3D controller:\s*/i, '')
                .replace(/^Display controller:\s*/i, '')
                .replace(/Advanced Micro Devices,\s*Inc\.\s*/i, 'AMD ')
                .replace(/\[AMD\/ATI\]\s*/i, '')
                .replace(/^NVIDIA\s+/i, '')
                .replace(/^Intel\(R\)\s+/i, 'Intel ')
                .replace(/\s+Graphics$/i, ' Graphics')
                .replace(/\s+\(rev\s+[0-9a-f]+\)$/i, '')
                .trim();
            if (/Cezanne/i.test(text) && /Radeon Vega/i.test(text)) return 'AMD Cezanne Radeon Vega';
            return text;
        }
        function normalizeGpuIdentity(name) {
            return compactGpuName(name)
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '');
        }
        function dedupeGpuRows(gpuList) {
            const rows = Array.isArray(gpuList) ? gpuList : [];
            const bestByKey = new Map();
            rows.forEach(item => {
                const key = normalizeGpuIdentity(item?.name || 'GPU');
                const hasTemp = Number.isFinite(Number(item?.temp)) && Number(item.temp) > 0;
                const score = (hasTemp ? 100 : 0) + (String(item?.source || '').toLowerCase().includes('nvidia') ? 10 : 0);
                const previous = bestByKey.get(key);
                if (!previous || score > previous.score) {
                    bestByKey.set(key, { item, score });
                }
            });
            return Array.from(bestByKey.values()).map(entry => entry.item);
        }
        function renderServerGpuList(rawGpuList) {
            const rawList = Array.isArray(rawGpuList) ? rawGpuList : [];
            const realGpus = dedupeGpuRows(rawList.filter(g => !isVirtualGpuName(g?.name)));
            const list = realGpus.length ? realGpus : rawList;
            if (!list.length) {
                return '<div class="gpu-list"><div class="server-gpu-muted">GPU：未采到真实 GPU</div></div>';
            }
            const virtualCount = rawList.filter(g => isVirtualGpuName(g?.name)).length;
            const rows = list.slice(0, 4).map((g, idx) => {
                const label = realGpus.length ? `GPU ${idx}` : `显示 ${idx}`;
                const util = formatServerMetric(g?.util_percent || 0);
                const hasTemp = Number.isFinite(Number(g?.temp)) && Number(g?.temp) > 0;
                const temp = hasTemp ? `${Number(g.temp).toFixed(0)}°C` : '温度未上报';
                const tempColor = hasTemp ? 'var(--text-main)' : 'var(--text-sub)';
                return `<div title="${escapeHtml(g?.name || 'GPU')}">${label}: ${escapeHtml(compactGpuName(g?.name))} <span style="color:var(--text-main);">${util}</span><span style="color:${tempColor};"> · ${temp}</span></div>`;
            }).join('');
            const note = virtualCount > 0 ? `<div class="server-gpu-muted">已隐藏 ${virtualCount} 个远控/虚拟显示适配器</div>` : '';
            return `<div class="gpu-list">${rows}${note}</div>`;
        }
        function getServerCompactGpuText(rawGpuList) {
            const rawList = Array.isArray(rawGpuList) ? rawGpuList : [];
            const realGpus = dedupeGpuRows(rawList.filter(g => !isVirtualGpuName(g?.name)));
            const list = realGpus.length ? realGpus : rawList.filter(g => !isVirtualGpuName(g?.name));
            if (!list.length) return '未采到';
            const first = list[0] || {};
            const name = compactGpuName(first.name || 'GPU');
            const temp = Number(first.temp);
            const tempText = Number.isFinite(temp) && temp > 0 ? `${temp.toFixed(0)}°C` : '温度未上报';
            const more = list.length > 1 ? ` +${list.length - 1}` : '';
            return `${name}${more} · ${tempText}`;
        }
        function getServerCompactMetricClass(value) {
            const num = Number(value) || 0;
            if (num >= 90) return 'bad';
            if (num >= 75) return 'warn';
            return '';
        }
        function getServerCompactGroupName(machine) {
            const raw = String(machine?.asset_group || '').trim();
            return raw || '未分组';
        }
        function getServerDisplayName(machine) {
            const custom = String(machine?.custom_name || '').trim();
            const remark = String(machine?.remark || '').trim();
            const host = String(machine?.hostname || '').trim();
            const ip = String(machine?.ip || '').trim();
            return custom || remark || host || ip || '未知节点';
        }
        function buildServerCompactGroups(machines) {
            const groupMap = new Map();
            machines.forEach(machine => {
                const groupName = getServerCompactGroupName(machine);
                if (!groupMap.has(groupName)) groupMap.set(groupName, []);
                groupMap.get(groupName).push(machine);
            });
            return Array.from(groupMap.entries());
        }
        function isServerDashboardVisible(machine) {
            return String(machine?.asset_group || '').trim().length > 0;
        }
        function getServerCompactAlertText(machine, diagnostic, online) {
            if (!online && !diagnostic.reportOnline) return diagnostic.badgeText || '离线';
            if (diagnostic.level === 'success') return '';
            return diagnostic.summary || diagnostic.badgeText || '异常';
        }
        function getServerCompactTooltip(machine, diagnostic, st, gpuText, alertText) {
            const pingText = machine?.ping_online === true ? '可达' : (machine?.ping_online === false ? '不可达' : '未检测');
            const lines = [
                getServerDisplayName(machine),
                `IP: ${machine?.ip || '--'}`,
                `状态: ${alertText || diagnostic.badgeText || '运行正常'}`,
                `网络: ${pingText}`,
                `CPU: ${formatServerMetric(normalizeServerBytes(st.cpu_percent))}`,
                `内存: ${formatServerMetric(normalizeServerBytes(st.mem_percent))}`,
                `磁盘: ${formatServerMetric(normalizeServerBytes(st.disk_percent))}`,
                `GPU: ${gpuText}`,
            ];
            if (machine?.server_received_at || machine?.last_online) lines.push(`接收时间: ${formatServerTime(machine.server_received_at || machine.last_online)}`);
            if (machine?.last_report_kind || diagnostic.lastReportKind) lines.push(`上报类型: ${machine?.last_report_kind || diagnostic.lastReportKind}`);
            if (machine?.client_reported_at) lines.push(`客户端时间: ${formatServerTime(machine.client_reported_at)}`);
            if (machine?.clock_offset_sec !== undefined && machine?.clock_offset_sec !== null) lines.push(`时间偏差: ${formatServerClockOffset(machine.clock_offset_sec)}`);
            return lines.join('\n');
        }
        function renderDashboardServerCompact(data = []) {
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return;
            const machines = Array.isArray(data) && data.length
                ? data
                : (Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length
                    ? dashboardServerCompactList
                    : (Array.isArray(globalServerList) ? globalServerList : []));
            const visibleMachines = machines.filter(isServerDashboardVisible);
            if (!machines.length) {
                container.classList.remove('server-compact-grouped');
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">正在加载机器状态...</div>';
                return;
            }
            if (!visibleMachines.length) {
                container.classList.remove('server-compact-grouped');
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">暂无已分组机器，未分组机器不参与首页显示。</div>';
                return;
            }
            container.classList.add('home-status-list');
            container.classList.add('server-compact-grouped');
            const renderMachineRow = (m) => {
                const st = m.status || {};
                const agent = m.agent_status || {};
                const diagnostic = buildServerDiagnostic(agent, m);
                const online = !!m.is_online;
                const reportOnline = !!diagnostic.reportOnline;
                const badgeText = diagnostic.badgeText || (online ? '运行正常' : '离线');
                const gpuText = getServerCompactGpuText(st.gpu_list);
                const rowHealthy = online && diagnostic.level === 'success';
                const dotClass = rowHealthy ? 'online' : (reportOnline ? 'warning' : 'error');
                const titleBadge = `<span class="home-status-dot ${dotClass}" title="${escapeHtml(badgeText)}"></span>`;
                const alertText = getServerCompactAlertText(m, diagnostic, online);
                const alertHtml = alertText ? `<span class="home-server-alert" title="${escapeHtml(alertText)}">${escapeHtml(alertText)}</span>` : '';
                const titleText = getServerCompactTooltip(m, diagnostic, st, gpuText, alertText);
                return `<div class="home-status-row home-server-row ${rowHealthy ? '' : (reportOnline ? 'warning' : 'offline')}" title="${escapeHtml(titleText)}">
                    <div class="home-row-main">
                        <div class="home-row-title-line"><strong>${escapeHtml(getServerDisplayName(m))}</strong>${titleBadge}</div>
                        ${alertHtml}
                    </div>
                </div>`;
            };
            container.innerHTML = buildServerCompactGroups(visibleMachines).map(([groupName, rows]) => {
                const onlineCount = rows.filter(item => item.is_online).length;
                const warningCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return diagnostic.level !== 'success' && !!diagnostic.reportOnline;
                }).length;
                const offlineCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return !item.is_online && !diagnostic.reportOnline;
                }).length;
                const groupClass = offlineCount ? 'offline' : (warningCount ? 'warning' : '');
                const warnHtml = warningCount ? `<span class="warn">异 ${warningCount}</span>` : '';
                const offlineHtml = offlineCount ? `<span class="bad">离 ${offlineCount}</span>` : '';
                return `<section class="home-server-group ${groupClass}">
                    <div class="home-server-group-head">
                        <div class="home-server-group-name">${escapeHtml(groupName)}</div>
                        <div class="home-server-group-stats"><span class="ok">${onlineCount}/${rows.length}</span>${warnHtml}${offlineHtml}</div>
                    </div>
                    <div class="home-server-group-list">${rows.map(renderMachineRow).join('')}</div>
                </section>`;
            }).join('');
        }
        function refreshDashboardServerCompactFallback() {
            const container = document.getElementById('dashboard-server-compact-grid');
            if (!container) return;
            if (Array.isArray(dashboardServerCompactList) && dashboardServerCompactList.length) {
                renderDashboardServerCompact(dashboardServerCompactList);
            } else if (Array.isArray(globalServerList) && globalServerList.length) {
                renderDashboardServerCompact(globalServerList);
            }
        }
        function renderServerMetaStrip(m, st, agent, diagnostic) {
            const rawTaskState = String(agent.task_state || '').toLowerCase();
            const taskText = agent.task_exists ? ((rawTaskState === 'running' || rawTaskState.includes('systemd')) ? '在线' : (agent.task_state || '在线')) : '未安装';
            const currentAgentVersion = String(agent.version || '').trim();
            const agentMissing = !currentAgentVersion;
            const agentOutdated = isAgentVersionOutdated(agent);
            const agentChipClass = agentMissing ? ' agent-missing' : (agentOutdated ? ' agent-old' : '');
            const updateHint = getAgentUpdateHint(agent);
            const agentTitle = agentOutdated
                ? `当前版本 ${currentAgentVersion}，最新版 ${latestAgentVersion}${updateHint.title ? `\n${updateHint.title}` : ''}`
                : (currentAgentVersion ? `当前版本 ${currentAgentVersion}` : '未上报 Agent 版本');
            const agentDisplay = currentAgentVersion || '--';
            const latestHint = agentOutdated ? `<em class="server-agent-latest">${escapeHtml(updateHint.label)}</em>` : '';
            const serverReceivedAt = m.server_received_at || st.server_received_at || m.last_online || '';
            const clientReportedAt = m.client_reported_at || st.client_reported_at || '';
            const reportOnline = !!(m.report_online || diagnostic.reportOnline);
            const runtimeFresh = !!(m.runtime_fresh || diagnostic.runtimeFresh);
            const reportKind = String(m.last_report_kind || diagnostic.lastReportKind || st.last_report_kind || '').trim();
            const clockOffset = m.clock_offset_sec ?? st.clock_offset_sec;
            const clockClass = getServerClockOffsetClass(clockOffset);
            const clockTitle = clientReportedAt
                ? `120接收: ${formatServerTime(serverReceivedAt)}\n客户端: ${formatServerTime(clientReportedAt)}\n偏差: ${formatServerClockOffset(clockOffset)}`
                : `120接收: ${formatServerTime(serverReceivedAt)}\n客户端时间暂未上报`;
            const reportKindLabel = reportKind === 'full' ? '完整采集' : (reportKind === 'bootstrap' ? '安装心跳' : (reportKind === 'agent_heartbeat' ? 'Agent心跳' : (reportKind || '')));
            const pingText = m.ping_online === true ? 'Ping可达' : (m.ping_online === false ? 'Ping不通' : (reportOnline ? (reportKindLabel || '心跳在线') : '未检测'));
            const collectText = runtimeFresh ? taskText : (reportOnline ? '采集停滞' : taskText);
            const reachClass = m.ping_online === false ? ' clock-bad' : ((runtimeFresh || m.ping_online === true) ? ' clock-ok' : (reportOnline ? ' clock-warn' : ''));
            return `<div class="server-meta-strip">
                <div class="server-meta-chip"><span>120接收</span><strong>${escapeHtml(formatServerTime(serverReceivedAt))}</strong></div>
                <div class="server-meta-chip${clockClass}" title="${escapeHtml(clockTitle)}"><span>客户端时间</span><strong>${escapeHtml(formatServerTime(clientReportedAt))}</strong><em>${escapeHtml(formatServerClockOffset(clockOffset))}</em></div>
                <div class="server-meta-chip${reachClass}"><span>采集/网络</span><strong>${escapeHtml(collectText)}</strong><em>${escapeHtml(pingText)}</em></div>
                <div class="server-meta-chip${agentChipClass}" title="${escapeHtml(agentTitle)}"><span>Agent版本</span><strong>${escapeHtml(agentDisplay)}${latestHint}</strong></div>
            </div>`;
        }
        function renderServerAttention(diagnostic) {
            if (!diagnostic || diagnostic.level === 'success') return '';
            const text = diagnostic.summary || diagnostic.recommendation || diagnostic.detail || '需要关注';
            return `<div class="server-alert-note">${escapeHtml(text)}</div>`;
        }
        function getCodeMeterSerials(codemeter) {
            const items = [];
            const pushSerial = value => {
                const text = String(value || '').trim();
                if (text && !text.startsWith('130-') && !items.includes(text)) items.push(text);
            };
            if (Array.isArray(codemeter?.serials)) codemeter.serials.forEach(pushSerial);
            if (Array.isArray(codemeter?.containers)) {
                codemeter.containers.forEach(item => pushSerial(item?.serial || item?.serial_number || item?.id));
            }
            return items;
        }
        function getCodeMeterLicenseLabel(codemeter) {
            const code = String(codemeter?.license_code || codemeter?.license_identity?.company_code || '').trim();
            const name = String(codemeter?.license_name || codemeter?.license_identity?.company_name || '').trim();
            if (code && name) return `${code} ${name}`;
            if (code) return `授权 ${code}`;
            return '';
        }
        function parseCodeMeterExpiry(value) {
            const text = String(value || '').trim();
            if (!text) return null;
            let normalized = text.replace(' ', 'T');
            if (/T\d{1,2}:\d{2}/.test(normalized) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) {
                normalized += '+00:00';
            }
            const date = new Date(normalized);
            if (Number.isNaN(date.getTime())) return null;
            return date;
        }
        function formatCodeMeterExpiry(date) {
            if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
            const parts = new Intl.DateTimeFormat('zh-CN', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
            }).formatToParts(date);
            const get = type => parts.find(item => item.type === type)?.value || '';
            return `${get('year')}-${get('month')}-${get('day')}`;
        }
        function hasCompanyCodeMeterLicense(codemeter) {
            return !!(codemeter?.license_code || codemeter?.license_identity?.company_code || codemeter?.license_identity?.has_company_license);
        }
        function getCodeMeterValidityText(codemeter) {
            if (!hasCompanyCodeMeterLicense(codemeter)) return '无授权';
            const licenses = Array.isArray(codemeter?.licenses) ? codemeter.licenses : [];
            const status = getCodeMeterExpiryStatusFromLicenses(licenses);
            const expiring = status.expiring;
            const futureExpiring = status.futureExpiring;
            if (futureExpiring.length) return `到期 ${formatCodeMeterExpiry(futureExpiring[0])}`;
            const expiredAt = formatCodeMeterExpiry(expiring[expiring.length - 1]);
            if (expiredAt) return `已到期 ${expiredAt}`;
            const validity = String(codemeter?.validity || '').toLowerCase();
            const summary = String(codemeter?.summary || '').trim();
            const summaryMap = {
                not_installed: '未安装',
                service_not_running: '服务未运行',
                dongle_not_found: '未发现锁',
                expires: '有期限',
                permanent: '长期有效',
                detected: '已检测到',
            };
            if (validity === 'permanent' || /长期|永久|无限|permanent|unlimited|lifetime/i.test(summary)) return '长期有效';
            if (validity === 'expires') return '有期限';
            if (summaryMap[summary]) return summaryMap[summary];
            return summary || '未检测';
        }
        function getCodeMeterExpiryStatusFromLicenses(licenses) {
            const expiring = (Array.isArray(licenses) ? licenses : [])
                .map(item => parseCodeMeterExpiry(item?.expires_at || item?.valid_until || item?.expire_at))
                .filter(Boolean)
                .sort((a, b) => a.getTime() - b.getTime());
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const todayTime = today.getTime();
            const futureExpiring = expiring.filter(date => date.getTime() >= todayTime);
            if (!expiring.length) return { cls: '', daysLeft: null, expiring, futureExpiring };
            if (!futureExpiring.length) return { cls: 'error', daysLeft: -1, expiring, futureExpiring };
            const daysLeft = Math.floor((futureExpiring[0].getTime() - todayTime) / 86400000);
            return {
                cls: daysLeft < 10 ? 'error' : (daysLeft < 30 ? 'warning' : ''),
                daysLeft,
                expiring,
                futureExpiring
            };
        }
        function renderServerCodeMeterLine(codemeter) {
            const info = codemeter && typeof codemeter === 'object' ? codemeter : {};
            const serials = getCodeMeterSerials(info);
            const installed = !!info.installed;
            const running = !!info.running;
            const level = String(info.level || '').toLowerCase();
            const runtimeOutdated = !!(info.runtime_outdated || info.license_identity?.runtime_outdated);
            const runtimeVersion = String(info.runtime_version || info.license_identity?.runtime_version || '').trim();
            const hasCompanyLicense = hasCompanyCodeMeterLicense(info);
            const expiryStatus = getCodeMeterExpiryStatusFromLicenses(info.licenses);
            const cls = (!installed || level === 'muted') ? 'muted' : (level === 'error' || expiryStatus.cls === 'error' ? 'error' : ((!running || level === 'warning' || runtimeOutdated || !hasCompanyLicense || expiryStatus.cls === 'warning') ? 'warning' : ''));
            const licenseLabel = getCodeMeterLicenseLabel(info);
            const serialText = serials.length ? serials.slice(0, 1).join('') + (serials.length > 1 ? ` +${serials.length - 1}` : '') : (installed ? '未发现锁' : '未安装');
            const displayText = serialText;
            const validityText = getCodeMeterValidityText(info);
            const titleParts = [
                licenseLabel ? `授权代码: ${licenseLabel}` : '',
                `编号: ${serials.length ? serials.join(' / ') : serialText}`,
                `授权: ${validityText}`,
                `服务: ${info.service_state || '--'}`,
            ].filter(Boolean);
            if (Number.isFinite(expiryStatus.daysLeft) && expiryStatus.daysLeft >= 0) titleParts.push(`剩余: ${expiryStatus.daysLeft} 天`);
            if (runtimeVersion) titleParts.push(`Runtime: ${runtimeVersion}${runtimeOutdated ? '，建议升级到 8.0+' : ''}`);
            if (info.checked_at) titleParts.push(`检测: ${formatServerTime(info.checked_at)}`);
            if (info.error) titleParts.push(`错误: ${info.error}`);
            const upgradeHtml = runtimeOutdated ? `<em class="upgrade">升级8.0+</em>` : '';
            return `<div class="server-codemeter-line ${cls}" title="${escapeHtml(titleParts.join('\n'))}"><span>CodeMeter</span><strong><em class="serial">${escapeHtml(displayText)}</em><em class="validity">${escapeHtml(validityText)}</em>${upgradeHtml}</strong></div>`;
        }
        function getServerGroupName(machine) {
            const raw = String(machine?.asset_group || '').trim();
            return raw || '未分组';
        }
        function isAgentVersionOutdated(agent = {}) {
            const currentAgentVersion = String(agent?.version || '').trim();
            return !!(latestAgentVersion && currentAgentVersion && compareAgentVersionBase(currentAgentVersion, latestAgentVersion) < 0);
        }
        function getAgentUpdateHint(agent = {}) {
            const selfUpdate = agent?.self_update || {};
            const action = String(selfUpdate.action || '').trim();
            const ok = selfUpdate.ok;
            if (action === 'failed' || ok === false) {
                const error = String(selfUpdate.error || '').trim();
                return {
                    label: '自更新失败',
                    title: error ? `自更新失败: ${error}` : '自更新失败，建议覆盖安装一次'
                };
            }
            if (!agent || !Object.prototype.hasOwnProperty.call(agent, 'self_update')) {
                return {
                    label: '需覆盖安装',
                    title: '该旧版采集脚本未上报自更新状态，通常需要手动覆盖安装一次；之后可自动滚动更新。'
                };
            }
            if (action === 'updated') {
                return {
                    label: '已拉取新版',
                    title: '新版 worker 已下载，等待下一轮计划任务切换到新版本'
                };
            }
            return {
                label: `需更新到 ${latestAgentVersion}`,
                title: '等待 agent 自更新或手动覆盖安装'
            };
        }
        function markServerCommandPending(mac, cmd, actionName) {
            const key = String(mac || '').trim().toUpperCase();
            if (!key) return;
            serverCommandPending[key] = {
                cmd,
                actionName: actionName || cmd,
                queuedAt: Date.now()
            };
        }
        function getServerCommandPending(mac) {
            const key = String(mac || '').trim().toUpperCase();
            const pending = key ? serverCommandPending[key] : null;
            if (!pending) return null;
            const ageMs = Date.now() - Number(pending.queuedAt || 0);
            if (ageMs > 120000) {
                delete serverCommandPending[key];
                return null;
            }
            return { ...pending, ageMs };
        }
        function clearSettledServerCommandPending(machines = []) {
            machines.forEach(machine => {
                const key = String(machine?.mac || '').trim().toUpperCase();
                const pending = key ? serverCommandPending[key] : null;
                if (!pending) return;
                if ((pending.cmd === 'shutdown' || pending.cmd === 'restart') && machine?.is_online === false) {
                    delete serverCommandPending[key];
                } else if (pending.cmd === 'refresh') {
                    const status = machine?.status || {};
                    const refreshedAt = Date.parse(status.hardware_refreshed_at || machine?.last_online || '');
                    if (Number.isFinite(refreshedAt) && refreshedAt >= Number(pending.queuedAt || 0) - 5000) {
                        delete serverCommandPending[key];
                    }
                }
            });
        }
        function renderServerCommandPending(pending) {
            if (!pending) return '';
            const seconds = Math.max(0, Math.round((Number(pending.ageMs) || 0) / 1000));
            const suffix = pending.cmd === 'shutdown' || pending.cmd === 'restart'
                ? '等待节点执行 / 离线上报'
                : '等待节点刷新上报';
            return `<div class="server-pending-command">${escapeHtml(pending.actionName)}已下发 · ${seconds}s · ${suffix}</div>`;
        }
        function burstRefreshServerData() {
            if (typeof updateServerData === 'function') updateServerData();
            [1500, 5000, 12000, 25000, 45000, 70000].forEach(delay => {
                window.setTimeout(() => {
                    if (typeof updateServerData === 'function') updateServerData();
                }, delay);
            });
            if (serverCommandRefreshTimer) window.clearInterval(serverCommandRefreshTimer);
            const startedAt = Date.now();
            serverCommandRefreshTimer = window.setInterval(() => {
                if (Date.now() - startedAt > 90000) {
                    window.clearInterval(serverCommandRefreshTimer);
                    serverCommandRefreshTimer = null;
                    return;
                }
                if (typeof updateServerData === 'function') updateServerData();
            }, 5000);
        }
        function renderServerCard(m) {
            const st = m.status || {};
            const agent = m.agent_status || {};
            const diagnostic = buildServerDiagnostic(agent, m);
            const pendingCommand = getServerCommandPending(m.mac);
            const identityLine = getServerIdentityLine(m);
            const gpuHtml = renderServerGpuList(st.gpu_list);
            const statusMetaHtml = renderServerMetaStrip(m, st, agent, diagnostic);
            const diagnosticHtml = renderServerAttention(diagnostic);
            const cpuPercent = normalizeServerBytes(st.cpu_percent);
            const memPercent = normalizeServerBytes(st.mem_percent);
            const diskPercent = normalizeServerBytes(st.disk_percent);
            const netSent = normalizeServerBytes(st.net_sent_kb_s);
            const netRecv = normalizeServerBytes(st.net_recv_kb_s);
            const networkPrimaryLabel = getNetworkPrimaryLabel(st);
            const codeMeterHtml = renderServerCodeMeterLine(st.codemeter);
            const showLastMetrics = !!(m.is_online || (diagnostic.reportOnline && diagnostic.hasRuntime));
            const metricsHtml = showLastMetrics
                ? `${statusMetaHtml}${diagnosticHtml}<div class="hardware-info"><div class="hardware-item" title="${escapeHtml(st.cpu_name||'未获取到CPU')}">CPU: <span>${escapeHtml(st.cpu_name||'加载中...')}</span></div><div class="hardware-item" title="${escapeHtml(st.motherboard||'未获取到主板')}">主板: <span>${escapeHtml(st.motherboard||'加载中...')}</span></div>${st.mem_speed ? `<div class="hardware-item">内存频率: <span>${escapeHtml(st.mem_speed)} MHz</span></div>` : ''}</div><div class="metric-row"><div class="metric-label"><span>CPU</span><span>${formatServerMetric(cpuPercent)}</span></div><div class="progress-track"><div class="progress-fill ${getColor(cpuPercent)}" style="width:${Math.max(0, Math.min(100, cpuPercent))}%"></div></div></div><div class="metric-row"><div class="metric-label"><span>内存 (${escapeHtml(st.mem_used||0)}/${escapeHtml(st.mem_total||0)} GB)</span><span>${formatServerMetric(memPercent)}</span></div><div class="progress-track"><div class="progress-fill bg-blue" style="width:${Math.max(0, Math.min(100, memPercent))}%"></div></div></div><div class="metric-row"><div class="metric-label"><span>系统盘</span><span>${formatServerMetric(diskPercent)}</span></div><div class="progress-track"><div class="progress-fill ${getColor(diskPercent)}" style="width:${Math.max(0, Math.min(100, diskPercent))}%"></div></div></div><div class="server-network-line" title="${escapeHtml(networkPrimaryLabel)}"><span>网络 上/下</span><strong><span style="color:var(--brand-blue)">↑ ${formatNetworkMbps(netSent)}</span><span style="color:var(--success)">↓ ${formatNetworkMbps(netRecv)} Mbps</span></strong></div>${codeMeterHtml}${gpuHtml}`
                : `${statusMetaHtml}${diagnosticHtml}<div style="text-align:center; color:var(--text-sub); margin:14px 0;">该节点当前离线，等待自动重连上报。</div>`;
            const groupHtml = m.asset_group ? `<div style="margin-top:8px; font-size:12px; color:var(--brand-blue);">区域/分组: ${escapeHtml(m.asset_group)}</div>` : '';
            let remarkHtml = m.remark ? `<div style="margin-top:12px; font-size:12px; color:var(--text-sub); border-top:1px dashed rgba(255,255,255,0.1); padding-top:8px;">备注: ${escapeHtml(m.remark)}</div>` : '';
            remarkHtml = groupHtml + remarkHtml;
            const cardStateClass = m.is_online ? 'online' : (diagnostic.reportOnline ? 'warning' : 'offline');
            const wakeButton = `<button class="server-action-btn wake${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="wakeServer('${escapeHtml(m.mac)}')">唤醒</button>`;
            const actionHtml = cardStateClass === 'offline'
                ? `<div class="server-compact-actions offline-only"><span class="spacer"></span>${wakeButton}</div>`
                : `<div class="server-compact-actions"><button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} title="上移" onclick="moveServer('${escapeHtml(m.mac)}', -1)">↑</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} title="下移" onclick="moveServer('${escapeHtml(m.mac)}', 1)">↓</button><span class="spacer"></span>${diagnostic.needsRedeploy ? `<button class="server-action-btn" style="color:var(--warning); border-color:var(--warning);" onclick="copyDeployCommand()">重部署</button>` : ''}<button class="server-action-btn${getPermissionDisabledClass('server.control')}" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${escapeHtml(m.mac)}', 'refresh')">刷新</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" style="color:var(--warning); border-color:var(--warning);" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${escapeHtml(m.mac)}', 'restart')">重启</button><button class="server-action-btn${getPermissionDisabledClass('server.control')}" style="color:var(--danger); border-color:var(--danger);" ${getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限')} onclick="sendServerCmd('${escapeHtml(m.mac)}', 'shutdown')">关机</button>${wakeButton}</div>`;
            return `<div class="server-card ${cardStateClass} size-${escapeHtml(m.card_size || 'normal')}"><div class="server-title"><span>${escapeHtml(getServerDisplayName(m))}</span><span class="tag ${diagnostic.badgeClass}">${escapeHtml(diagnostic.badgeText)}</span></div><div class="server-ip" title="${escapeHtml(identityLine.title)}">${escapeHtml(identityLine.text)}</div>${renderServerCommandPending(pendingCommand)}${metricsHtml}${remarkHtml}${actionHtml}</div>`;
        }
        function renderServerGroupedGrid(machines) {
            const groupMap = new Map();
            machines.forEach(machine => {
                const groupName = getServerGroupName(machine);
                if (!groupMap.has(groupName)) groupMap.set(groupName, []);
                groupMap.get(groupName).push(machine);
            });
            return Array.from(groupMap.entries()).map(([groupName, rows]) => {
                const onlineCount = rows.filter(item => item.is_online).length;
                const warningCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return diagnostic.level !== 'success' && !!diagnostic.reportOnline;
                }).length;
                const outdatedCount = rows.filter(item => isAgentVersionOutdated(item.agent_status || {})).length;
                const offlineCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item);
                    return !item.is_online && !diagnostic.reportOnline;
                }).length;
                const warnHtml = warningCount ? `<span class="server-group-pill warn">异常 ${warningCount}</span>` : '';
                const outdatedHtml = outdatedCount ? `<span class="server-group-pill warn">需更新 ${outdatedCount}</span>` : '';
                const offlineHtml = offlineCount ? `<span class="server-group-pill warn">离线 ${offlineCount}</span>` : '';
                return `<section class="server-group-section">
                    <div class="server-group-head">
                        <div class="server-group-title"><span class="server-group-name">${escapeHtml(groupName)}</span></div>
                        <div class="server-group-meta"><span class="server-group-pill ok">在线 ${onlineCount}/${rows.length}</span>${warnHtml}${outdatedHtml}${offlineHtml}</div>
                    </div>
                    <div class="server-group-grid">${rows.map(renderServerCard).join('')}</div>
                </section>`;
            }).join('');
        }

        updateServerData = function() {
            fetchJson('/api/machines', {}, '服务器列表读取失败')
                .then(data => {
                    data.sort((a, b) => {
                        if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
                        return a.mac.localeCompare(b.mac);
                    });
                    clearSettledServerCommandPending(data);
                    globalServerList = data;
                    const dashboardMachines = data.filter(isServerDashboardVisible);
                    dashboardServerCompactList = dashboardMachines;
                    const sTotal = document.getElementById('dash-server-total');
                    if (sTotal) sTotal.innerText = dashboardMachines.length;
                    const onlineCount = dashboardMachines.filter(m => m.is_online).length;
                    const sOnline = document.getElementById('dash-server-online');
                    if (sOnline) sOnline.innerText = onlineCount;
                    const sContainer = document.getElementById('server-grid-container');
                    if (sContainer) sContainer.innerHTML = renderServerGroupedGrid(data);
                    renderDashboardServerCompact(data);
                })
                .catch(err => console.error('服务器数据更新失败', err));
        };

        fireUniversalCommand = function(devId, payload, format, wait_ms) {
            if (!ensurePermission('light.control', '控制泛型设备')) return;
            showToast('通用指令下发中...', false);
            postJsonLoose('/api/universal/control', {
                device_id: devId,
                command: { payload: payload, format: format, wait_ms: wait_ms || 0 }
            }, '通用指令下发失败')
                .then(data => {
                    if (data.success) {
                        showToast('执行成功');
                        console.log('设备返回:', data.response);
                    } else {
                        showToast('执行失败: ' + (data.response || data.msg || data.message || '未知错误'), true);
                    }
                })
                .catch(() => showToast('网络请求错误', true));
        };

        fireControlCenterControl = function(controlId, options = {}) {
            if (!ensurePermission('control_center.control', '控制协议设备')) return;
            showToast('协议指令下发中...', false);
            postJsonLoose('/api/control_center/execute', {
                control_id: controlId,
                params: options.params || {},
                value: options.value
            }, '协议控制下发失败')
                .then(data => {
                    if (data.ok) {
                        const msg = data.msg || '执行成功';
                        showToast(msg, false);
                        if (Array.isArray(data.results)) console.log('协议控制结果:', data.results);
                    } else {
                        showToast('执行失败: ' + (data.msg || '未知错误'), true);
                    }
                })
                .catch(() => showToast('网络请求错误', true));
        };

        fireProjectorCommand = function(devId, payload, format, name='') {
            if (!ensurePermission('projector.control', '操作投影机')) return;
            showToast('投影指令下发中...', false);
            postJsonLoose('/api/projector/control', { device_id: devId, command: { payload: payload, format: format, name: name } }, '投影指令下发失败')
                .then(data => {
                    showToast(data.success ? '执行成功' : ('执行失败: ' + (data.response || data.msg || '未知错误')), !data.success);
                    if (data.success) refreshProjectorStatusAfterCommand();
                })
                .catch(() => showToast('网络请求失败', true));
        };

        fireScreenCommand = function(screenId, payload, format, action) {
            if (!ensurePermission('screen.control', '操作幕布')) return;
            showToast('幕布指令下发中...', false);
            postJsonLoose('/api/screen/control', { screen_id: screenId, command: { payload: payload, format: format, action: action } }, '幕布指令下发失败')
                .then(data => {
                    showToast(data.success ? '执行成功' : ('执行失败: ' + (data.response || data.msg || '未知错误')), !data.success);
                    if (data.success) setTimeout(updateScreenStatus, 120);
                })
                .catch(() => showToast('幕布指令下发失败', true));
        };

        updateProjectorStatus = function() {
            fetchJson('/api/projector/status', {}, '投影机状态读取失败')
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
                .catch(err => console.error('投影机状态更新失败', err));
        };

        updateScreenStatus = function() {
            fetchJson('/api/screens', {}, '幕布状态读取失败')
                .then(data => {
                    const grid = document.getElementById('screen-status-grid');
                    if (!grid) return;
                    const screens = data.screens || [];
                    grid.innerHTML = screens.length
                        ? screens.map(screen => renderScreenStatusCard(screen)).join('')
                        : '<div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">未配置幕布设备</div>';
                })
                .catch(err => console.error('幕布状态更新失败', err));
        };

        function extractMacAddress(value) {
            const text = String(value ?? '').trim();
            if (!text) return '';
            const match = text.match(/\b(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\b/i);
            return match ? match[0].toUpperCase() : '';
        }

        function buildEnvDeviceInfo(cfg, st) {
            const sourceType = String(cfg?.source_type || '').trim().toLowerCase();
            const macAddress = String(
                cfg?.mac_address
                || cfg?.mac
                || cfg?.ble_mac
                || cfg?.address_text
                || extractMacAddress(cfg?.note)
                || ''
            ).trim();
            let accessAddress = '';
            if (cfg?.ip) {
                accessAddress = `${cfg.ip}${cfg?.port ? `:${cfg.port}` : ''}`;
            } else if (sourceType === 'mqtt' && cfg?.mqtt?.host) {
                accessAddress = `${cfg.mqtt.host}${cfg?.mqtt?.port ? `:${cfg.mqtt.port}` : ''}`;
            } else if (['home_assistant', 'homeassistant', 'ha'].includes(sourceType) && cfg?.home_assistant?.base_url) {
                accessAddress = String(cfg.home_assistant.base_url || '').trim();
            } else {
                accessAddress = String(cfg?.bridge_host || cfg?.gateway_host || cfg?.bridge_address || '').trim();
            }
            const updatedAtText = st?.updated_at ? String(st.updated_at).replace('T', ' ').slice(0, 19) : '';
            const polledAtText = st?.polled_at ? String(st.polled_at).replace('T', ' ').slice(0, 19) : '';
            const ageSec = Number(st?.age_sec);
            const rows = [
                String(cfg?.model || '').trim() ? { label: '设备型号', value: String(cfg.model).trim() } : null,
                macAddress ? { label: 'MAC地址', value: macAddress } : null,
                accessAddress ? { label: '接入地址', value: accessAddress } : null,
                updatedAtText
                    ? { label: '数据时间', value: updatedAtText }
                    : (Number.isFinite(ageSec) ? { label: '数据年龄', value: `${Math.round(ageSec)} 秒` } : null),
                Number.isFinite(ageSec) ? { label: '数据年龄', value: formatCompactAgeFromSec(ageSec) } : null,
                polledAtText ? { label: '中控轮询', value: polledAtText } : null,
                Number.isFinite(Number(st?.rssi)) ? { label: '信号强度', value: `${Math.round(Number(st.rssi))} dBm` } : null,
                Number.isFinite(Number(st?.linkquality)) ? { label: '链路质量', value: `${Math.round(Number(st.linkquality))}` } : null,
            ].filter(Boolean);
            return {
                rows,
                note: String(cfg?.note || '').trim(),
            };
        }

        function formatEnvNumericValue(value, precision = null) {
            const num = Number(value);
            if (!Number.isFinite(num)) return null;
            return precision === null ? String(value) : num.toFixed(precision);
        }
        function buildEnvMetricMap(features, st, cfg = null) {
            const batteryValue = Number(st?.battery);
            const batteryAgeText = formatCompactAgeFromSec(st?.battery_age_sec);
            const batteryStale = !!st?.battery_stale;
            const batteryColor = !Number.isFinite(batteryValue)
                ? 'var(--text-sub)'
                : (batteryStale ? 'var(--warning)' : (batteryValue <= 15 ? 'var(--danger)' : (batteryValue <= 35 ? 'var(--warning)' : '#22c55e')));
            const voltageText = formatEnvNumericValue(st?.voltage, 3);
            const map = {
                temperature: {
                    key: 'temperature',
                    label: '温度',
                    mainLabel: '核心指标：温度',
                    value: st?.temp,
                    suffix: ' °C',
                    color: 'var(--success)',
                    available: st?.temp !== null && st?.temp !== undefined && st?.temp !== ''
                },
                humidity: {
                    key: 'humidity',
                    label: '湿度',
                    mainLabel: '核心指标：湿度',
                    value: st?.hum,
                    suffix: ' %',
                    color: 'var(--brand-blue)',
                    available: st?.hum !== null && st?.hum !== undefined && st?.hum !== ''
                },
                illuminance: {
                    key: 'illuminance',
                    label: '光照',
                    mainLabel: '核心指标：实时光照度',
                    value: st?.lux,
                    suffix: ' Lux',
                    color: 'var(--warning)',
                    available: st?.lux !== null && st?.lux !== undefined && st?.lux !== ''
                },
                contact: {
                    key: 'contact',
                    label: '开合状态',
                    mainLabel: '核心指标：开合状态',
                    text: typeof st?.contact === 'boolean'
                        ? (st.contact ? '打开' : '关闭')
                        : (st?.contact_text ? String(st.contact_text) : ''),
                    color: (typeof st?.contact === 'boolean' ? st.contact : String(st?.contact_text || '').includes('开')) ? 'var(--danger)' : 'var(--success)',
                    available: typeof st?.contact === 'boolean' || !!st?.contact_text
                },
                light: {
                    key: 'light',
                    label: '光照状态',
                    mainLabel: '核心指标：光照状态',
                    text: st?.light_text ? String(st.light_text) : (typeof st?.light === 'boolean' ? (st.light ? '亮' : '暗') : ''),
                    color: st?.light ? 'var(--warning)' : 'var(--text-sub)',
                    available: typeof st?.light === 'boolean' || !!st?.light_text
                },
                battery: {
                    key: 'battery',
                    label: batteryStale ? '电量过期' : '电量估算',
                    mainLabel: '核心指标：电量估算',
                    value: Number.isFinite(batteryValue) ? batteryValue : null,
                    suffix: ' %',
                    color: batteryColor,
                    available: Number.isFinite(batteryValue)
                },
                voltage: {
                    key: 'voltage',
                    label: '电池电压',
                    mainLabel: '核心指标：电池电压',
                    value: voltageText,
                    suffix: ' V',
                    color: st?.voltage_stale ? 'var(--warning)' : '#22c55e',
                    available: voltageText !== null
                },
                noise: {
                    key: 'noise',
                    label: '噪声',
                    mainLabel: '核心指标：噪声',
                    value: st?.noise,
                    suffix: ' dB',
                    color: 'var(--warning)',
                    available: st?.noise !== null && st?.noise !== undefined && st?.noise !== ''
                },
                pm25: {
                    key: 'pm25',
                    label: 'PM2.5',
                    mainLabel: '核心指标：PM2.5',
                    value: st?.pm25,
                    suffix: '',
                    color: '#f97316',
                    available: st?.pm25 !== null && st?.pm25 !== undefined && st?.pm25 !== ''
                },
                pm10: {
                    key: 'pm10',
                    label: 'PM10',
                    mainLabel: '核心指标：PM10',
                    value: st?.pm10,
                    suffix: '',
                    color: '#a78bfa',
                    available: st?.pm10 !== null && st?.pm10 !== undefined && st?.pm10 !== ''
                },
                pressure: {
                    key: 'pressure',
                    label: '气压',
                    mainLabel: '核心指标：气压',
                    value: st?.pressure,
                    suffix: ' kPa',
                    color: '#22c55e',
                    available: st?.pressure !== null && st?.pressure !== undefined && st?.pressure !== ''
                },
            };
            Object.keys(map).forEach(key => {
                map[key].enabled = envFeatureEnabled(features, key);
                map[key].displayText = map[key].text !== undefined
                    ? map[key].text
                    : (map[key].available ? `${map[key].value}${map[key].suffix || ''}` : '--');
                const ageSec = Number(st?.[`${key === 'temperature' ? 'temp' : key === 'humidity' ? 'hum' : key}_age_sec`]);
                if (Number.isFinite(ageSec) && Number(st?.stale_after_sec || 7200) > 0 && ageSec > Number(st?.stale_after_sec || 7200)) {
                    map[key].stale = true;
                    map[key].label = `${map[key].label}陈旧`;
                    map[key].color = 'var(--warning)';
                    map[key].displayText = `${map[key].displayText} / ${formatCompactAgeFromSec(ageSec)}`;
                }
            });
            return map;
        }
        function getEnvPrimaryMetricDef(cfg, st, features, metricMap) {
            const configured = String(cfg?.primary_metric || 'auto').trim().toLowerCase();
            const order = configured && configured !== 'auto'
                ? [configured, ...ENV_PRIMARY_METRIC_ORDER.filter(key => key !== configured)]
                : (isContactLikeEnvSensor(cfg)
                    ? ['contact', 'battery', 'voltage', 'temperature', 'humidity', 'illuminance', 'light', 'noise', 'pm25', 'pm10', 'pressure']
                    : ENV_PRIMARY_METRIC_ORDER);
            for (const key of order) {
                const item = metricMap[key];
                if (item && item.enabled && item.available) return item;
            }
            return {
                key: 'auto',
                label: '环境监测',
                mainLabel: '核心指标：环境监测',
                displayText: st?.online ? '在线' : '--',
                color: st?.online ? 'var(--success)' : 'var(--text-sub)',
                available: !!st?.online,
                enabled: true
            };
        }
        function buildEnvStatusMetricDefs(features, st, cfg = null) {
            const metricMap = buildEnvMetricMap(features, st, cfg);
            return ENV_PRIMARY_METRIC_ORDER
                .map(key => metricMap[key])
                .filter(item => item && item.enabled && item.available);
        }

        updateEnvData = function() {
            fetchJson('/api/env/status', {}, '环境状态读取失败')
                .then(data => {
                    window.__envStatusCache = data || {};
                    updateHvacRoomEnvSlots();
                    const container = document.getElementById('env-grid-container');
                    const screenEnvColumn = document.getElementById('screen-env-column');
                    const screenUpsColumn = document.getElementById('screen-ups-column');
                    const screenAutomationColumn = document.getElementById('screen-automation-column');
                    const topTemp = document.getElementById('top-env-temp');
                    const topHum = document.getElementById('top-env-hum');
                    const topLux = document.getElementById('top-env-lux');
                    const topSummary = document.getElementById('top-env-summary');
                    const onlineSensor = pickDashboardEnvSensor(data);
                    if (screenEnvColumn) screenEnvColumn.innerHTML = buildScreenEnvCards();
                    if (screenUpsColumn) screenUpsColumn.innerHTML = buildScreenUpsCards();
                    if (screenAutomationColumn) screenAutomationColumn.innerHTML = buildScreenAutomationCards();
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
                    updateDashboardDoorStatusFromEnv(data);
                    renderOutdoorAutomationDashboardCard();
                    if (Object.keys(data).length === 0) {
                        container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1;">暂未配置传感器。</div>';
                        return;
                    }
                    let html = '';
                    envConfigs.forEach(cfg => {
                        const st = data[cfg.id] || { online: false };
                        const features = getEnvFeatures(cfg);
                        const statusLevel = String(st.status_level || (st.online ? 'online' : (st.stale ? 'stale' : 'offline'))).toLowerCase();
                        const color = statusLevel === 'online' ? 'var(--success)' : (statusLevel === 'stale' ? 'var(--warning)' : '#475569');
                        const metricMap = buildEnvMetricMap(features, st, cfg);
                        const primaryMetric = getEnvPrimaryMetricDef(cfg, st, features, metricMap);
                        const metricDefs = buildEnvStatusMetricDefs(features, st, cfg);
                        const deviceInfo = buildEnvDeviceInfo(cfg, st);
                        let metricsHtml = '';
                        metricDefs.forEach(item => {
                            if (item.key === primaryMetric.key && metricDefs.length > 1) return;
                            const valueText = (st.online || st.stale || statusLevel === 'stale') ? item.displayText : '--';
                            metricsHtml += `<div class="env-card-metric ${item.stale ? 'stale' : ''}"><div class="label">${escapeHtml(item.label)}</div><div class="val" style="color:${item.color};">${escapeHtml(valueText)}</div></div>`;
                        });
                        if (!metricsHtml) metricsHtml = '<div style="color:var(--text-sub);">未启用扩展指标</div>';
                        const deviceInfoHtml = (deviceInfo.rows.length || deviceInfo.note)
                            ? `<div class="env-card-device-info">
                                    ${deviceInfo.rows.length ? `<div class="env-card-device-grid">${deviceInfo.rows.map(item => `<div class="env-card-device-item"><div class="label">${escapeHtml(item.label)}</div><div class="value">${escapeHtml(item.value)}</div></div>`).join('')}</div>` : ''}
                                    ${deviceInfo.note ? `<div class="env-card-note">${escapeHtml(deviceInfo.note)}</div>` : ''}
                                </div>`
                            : '';
                        const onlineText = st.status_label || (st.online ? '在线' : (st.stale ? '陈旧' : '离线'));
                        const primaryText = (st.online || st.stale || statusLevel === 'stale') ? primaryMetric.displayText : '--';
                        html += `<div class="env-card env-card-compact" style="border-top: 4px solid ${color};">
                            <div class="env-card-head">
                                <div class="env-card-name" title="${escapeHtml(cfg.name || cfg.id || '')}">${escapeHtml(cfg.name || cfg.id || '环境传感器')}</div>
                                <span class="env-card-status ${escapeHtml(statusLevel)}">${escapeHtml(onlineText)}</span>
                            </div>
                            <div class="env-card-primary">
                                <div class="label">${escapeHtml(primaryMetric.mainLabel || primaryMetric.label || '核心指标')}</div>
                                <div class="val" style="color:${primaryMetric.color || 'var(--warning)'}">${escapeHtml(primaryText)}</div>
                            </div>
                            <div class="env-card-metrics">${metricsHtml}</div>
                            ${deviceInfoHtml}
                        </div>`;
                    });
                    container.innerHTML = html;
                })
                .catch(err => console.error('环境数据更新失败', err));
        };

        toggleAutomation = function(ruleId, isEnabled) {
            if (!ensurePermission('automation.edit', '修改自动化规则')) return;
            postJsonLoose('/api/automation/toggle', { id: ruleId, enabled: isEnabled }, '自动化规则更新失败')
                .then(d => {
                    if (d.success) {
                        showToast(isEnabled ? '自动化规则已启用' : '自动化规则已暂停');
                        const card = document.getElementById('auto-card-' + ruleId);
                        if (card) {
                            if (isEnabled) card.classList.remove('disabled');
                            else card.classList.add('disabled');
                        }
                        setTimeout(() => { loadAutomationStatus(); loadAutomationLogs(); }, 120);
                    } else {
                        showToast(d.msg || '自动化规则更新失败', true);
                    }
                })
                .catch(err => showToast(translateApiError(err?.message, '自动化规则更新失败'), true));
        };
        function toggleAutomationEditor(ruleId, forceOpen = null) {
            const panel = document.getElementById(`auto-edit-panel-${ruleId}`);
            const btn = document.querySelector(`[data-auto-edit-btn="${ruleId}"]`);
            if (!panel) return;
            const shouldOpen = forceOpen === null ? !panel.classList.contains('open') : !!forceOpen;
            panel.classList.toggle('open', shouldOpen);
            if (btn) btn.textContent = shouldOpen ? '收起编辑' : '编辑条件';
        }
        function applyRuleToAutoCard(rule) {
            if (!rule || !rule.id) return;
            const card = document.getElementById(`auto-card-${rule.id}`);
            if (!card) return;
            const descEl = card.querySelector('.desc');
            if (descEl) {
                let desc = '';
                if (rule.trigger_type === 'schedule') {
                    desc = `定时执行，每日 ${rule.schedule?.time || '08:00'}`;
                } else if (rule.trigger_type === 'condition') {
                    desc = `条件触发，当 ${rule.condition?.source_type || 'env'} / ${rule.condition?.prop || 'lux'} ${rule.condition?.op || '<'} ${rule.condition?.value ?? 0} 时`;
                } else if (rule.trigger_type === 'compound') {
                    desc = `组合触发，${String(rule.trigger_mode || 'any') === 'all' ? '全部条件满足才执行' : '任意一个条件满足即执行'}`;
                } else {
                    desc = `混合模式，在 ${rule.schedule?.time_start || '00:00'} - ${rule.schedule?.time_end || '23:59'} 期间，若 ${rule.condition?.source_type || 'env'} / ${rule.condition?.prop || 'lux'} ${rule.condition?.op || '<'} ${rule.condition?.value ?? 0} 则触发`;
                }
                descEl.innerHTML = `${escapeHtml(desc)}<span style="color:var(--brand-blue); margin-left:10px;">触发动作：调用场景联动 [ID: ${escapeHtml(rule.action_scene_id || '')}]</span>`;
            }
        }
        function readAutoField(ruleId, suffix) {
            const el = document.getElementById(`auto-field-${ruleId}-${suffix}`);
            return el ? el.value : '';
        }
        function saveAutomationRule(ruleId) {
            if (!ensurePermission('automation.edit', '修改自动化规则内部条件')) return;
            const saveBtn = document.getElementById(`auto-save-btn-${ruleId}`);
            if (saveBtn) saveBtn.disabled = true;
            const payload = {
                id: ruleId,
                trigger_type: String(readAutoField(ruleId, 'trigger_type') || 'condition'),
                action_scene_id: String(readAutoField(ruleId, 'action_scene_id') || '').trim(),
                condition: {
                    source_type: String(readAutoField(ruleId, 'source_type') || 'env'),
                    device_id: String(readAutoField(ruleId, 'device_id') || '').trim(),
                    prop: String(readAutoField(ruleId, 'prop') || 'lux').trim(),
                    op: String(readAutoField(ruleId, 'op') || '<'),
                    value: Number(readAutoField(ruleId, 'value') || 0),
                    debounce_sec: Number(readAutoField(ruleId, 'debounce_sec') || 0),
                    hysteresis: Number(readAutoField(ruleId, 'hysteresis') || 0),
                    consecutive_hits: Number(readAutoField(ruleId, 'consecutive_hits') || 1),
                    crossing_mode: String(readAutoField(ruleId, 'crossing_mode') || 'none'),
                    rearm_value: String(readAutoField(ruleId, 'rearm_value') || '').trim(),
                    window_bootstrap_sec: Number(readAutoField(ruleId, 'window_bootstrap_sec') || 0),
                },
                schedule: {
                    day_type: String(readAutoField(ruleId, 'day_type') || 'everyday'),
                    time: String(readAutoField(ruleId, 'time') || '08:00'),
                    time_start: String(readAutoField(ruleId, 'time_start') || '00:00'),
                    time_end: String(readAutoField(ruleId, 'time_end') || '23:59'),
                }
            };
            postJsonLoose('/api/automation/update', payload, '自动化规则保存失败')
                .then(d => {
                    if (d.success) {
                        showToast('自动化规则已保存');
                        if (d.rule) applyRuleToAutoCard(d.rule);
                        toggleAutomationEditor(ruleId, false);
                        setTimeout(() => { loadAutomationStatus(); loadAutomationLogs(); }, 120);
                    } else {
                        showToast(d.msg || '自动化规则保存失败', true);
                    }
                })
                .catch(err => showToast(translateApiError(err?.message, '自动化规则保存失败'), true))
                .finally(() => { if (saveBtn) saveBtn.disabled = false; });
        }
