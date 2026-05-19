        const configData = window.configData || {};
        const currentUser = window.currentUser || { permissions: [] };
        function ensureInitialVisibleView() {
            const activeView = document.querySelector('.view-section.active');
            if (!activeView) {
                const dashboardView = document.getElementById('view-dashboard');
                if (dashboardView) dashboardView.classList.add('active');
            }
        }
        ensureInitialVisibleView();
        function parseDateTimeText(value) {
            const text = String(value || '').trim();
            if (!text) return null;
            const normalized = text.replace(' ', 'T');
            const dt = new Date(normalized);
            return Number.isNaN(dt.getTime()) ? null : dt;
        }
        function isNowInTimeRange(startText, endText) {
            if (!startText || !endText) return true;
            const parse = text => {
                const [h, m] = String(text || '').split(':');
                return { h: Number(h), m: Number(m) };
            };
            const start = parse(startText);
            const end = parse(endText);
            if (!Number.isFinite(start.h) || !Number.isFinite(start.m) || !Number.isFinite(end.h) || !Number.isFinite(end.m)) return true;
            const now = new Date();
            const nowMinutes = now.getHours() * 60 + now.getMinutes();
            const startMinutes = start.h * 60 + start.m;
            const endMinutes = end.h * 60 + end.m;
            if (startMinutes <= endMinutes) return nowMinutes >= startMinutes && nowMinutes <= endMinutes;
            return nowMinutes >= startMinutes || nowMinutes <= endMinutes;
        }
        function isControlPermissionAllowedBySchedule() {
            if (String(currentUser.role || '').toLowerCase() === 'admin' || String(currentUser.account_category || '').toLowerCase() === 'admin') return true;
            const flags = currentUser.account_flags || {};
            const temp = currentUser.temporary_access || {};
            const schedule = currentUser.control_schedule || {};
            if (flags.frozen || flags.temporarily_disabled) return false;
            const disableUntil = parseDateTimeText(flags.disable_until);
            if (disableUntil && new Date() <= disableUntil) return false;
            if (temp.control_blocked) {
                const blockedUntil = parseDateTimeText(temp.control_blocked_until);
                if (!blockedUntil || new Date() <= blockedUntil) return false;
            }
            if (temp.control_enabled) {
                const allowUntil = parseDateTimeText(temp.control_until);
                if (!allowUntil || new Date() <= allowUntil) return true;
            }
            if (!schedule.enabled) return true;
            const mode = String(schedule.mode || 'always');
            const weekday = (new Date().getDay() + 6) % 7;
            if (mode === 'weekdays' && weekday > 4) return false;
            if (mode === 'weekends' && weekday < 5) return false;
            if (mode === 'custom_days') {
                const weekdays = Array.isArray(schedule.weekdays) ? schedule.weekdays.map(v => Number(v)) : [];
                if (weekdays.length && !weekdays.includes(weekday)) return false;
            }
            return isNowInTimeRange(schedule.start, schedule.end);
        }
        function hasPermission(permission) {
            const allowed = Array.isArray(currentUser.permissions) && currentUser.permissions.includes(permission);
            const compatibilityMap = {
                'control_center.view': 'light.view',
                'control_center.control': 'light.control',
                'control_center.config': 'meter.config'
            };
            const compat = compatibilityMap[String(permission || '').trim()];
            const compatAllowed = compat ? (Array.isArray(currentUser.permissions) && currentUser.permissions.includes(compat)) : false;
            if (!(allowed || compatAllowed)) return false;
            if (String(permission || '').endsWith('.control') || ['meter.config', 'system.config', 'auth.manage', 'automation.edit', 'control_center.config'].includes(String(permission || ''))) {
                return isControlPermissionAllowedBySchedule();
            }
            return true;
        }
        function ensurePermission(permission, actionText = '执行当前操作') {
            if (hasPermission(permission)) return true;
            showToast(`当前账号无权限${actionText}`, true);
            return false;
        }
        function getPermissionDisabledAttrs(permission, titleText) {
            return hasPermission(permission) ? '' : `disabled title="${escapeHtml(titleText || '当前账号无权限执行此操作')}"`;
        }
        function getPermissionDisabledClass(permission) {
            return hasPermission(permission) ? '' : ' is-disabled';
        }
        const myCharts = {};
        const pwrLocks = {};
        const pwrStates = {};
        const pwrPending = {};
        const pwrDesiredStates = {};
        const POWER_CHANNEL_LOCK_MS = 6000;
        const POWER_CHANNEL_VERIFY_HOLD_MS = 45000;
        const powerStatusCache = {};
        const powerHistoryCache = {};
        const powerLogCache = {};
        const powerSupplementFetchAt = {};
        const powerSupplementInFlight = {};
        let powerFetchInFlight = null;
        let powerVisibleSupplementCabIds = [];
        let meterCenterCache = { summary: {}, meters: [], trend: [] };
        let meterTrendTarget = 'total';
        let meterTrendPeriod = 'day';
        let meterCenterRequestSeq = 0;
        let meterTrendOptionSignature = '';
        let meterTrendAxisKey = '';
        let meterTrendYAxisMax = 0;
        let upsStatusCache = {};
        let hyEdgeStatusCache = {};
        let proxyStatusCache = {};
        let snmpStatusCache = {};
        let nvrStatusCache = {};
        let snmpCardFilter = 'all';
        let snmpStatusSignature = '';
        let snmpLastSuccessAt = 0;
        let snmpFetchFailureCount = 0;
        let snmpLastToastAt = 0;
        let snmpFetchInFlight = null;
        let snmpFetchMode = '';
        let snmpStatusMode = '';
        let snmpLastRenderAt = 0;
        let snmpSelectedDeviceId = '';
        let nvrSelectedDeviceId = '';
        let nvrSelectedChannelId = '';
        let nvrPreviewMode = 'smart';
        let nvrPreviewGrid = 16;
        let nvrPreviewPage = 0;
        const NVR_STREAM_CONCURRENCY_LIMIT = 8;
        const NVR_STREAM_STAGGER_MS = 520;
        const NVR_WALL_SNAPSHOT_REFRESH_MS = 10000;
        const nvrWallFrameTimers = [];
        let nvrWallSnapshotRefreshTimer = null;
        let automationStatusCache = { server_time: '', rules: [] };
        let automationStatusLoading = false;
        let automationLogCache = [];
        let automationLogLoading = false;
        let automationGroupSignature = '';
        let activeAutomationCanvasRuleId = '';
        let activeAutomationCanvasNodeId = '';
        let automationCanvasZoom = 1;
        let automationCanvasPanX = 0;
        let automationCanvasPanY = 0;
        let automationCanvasBaseX = 28;
        let automationCanvasBaseY = 0;
        let automationCanvasDragState = null;
        let automationCanvasSuppressClickUntil = 0;
        const snmpOpenDetailsState = {};
        let dashboardLogsCache = [];
        let dashboardSummaryCache = null;
        let dashboardSummaryInFlight = null;

        function getPowerChannelStatus(cabId, chNum) {
            const desired = pwrDesiredStates[cabId]?.[chNum];
            if (desired && Date.now() - desired.ts < POWER_CHANNEL_LOCK_MS) {
                return desired.target;
            }
            const cachedChannels = (powerStatusCache[cabId] || {}).channels_1_4;
            if (Array.isArray(cachedChannels) && cachedChannels[chNum - 1] !== undefined) {
                return cachedChannels[chNum - 1];
            }
            return (pwrStates[cabId] || [])[chNum];
        }
        function setPowerDesiredState(cabId, chNum, targetState) {
            pwrDesiredStates[cabId] = pwrDesiredStates[cabId] || {};
            pwrDesiredStates[cabId][chNum] = {
                target: !!targetState,
                ts: Date.now(),
                confirmed: false,
            };
            pwrStates[cabId] = pwrStates[cabId] || [];
            pwrStates[cabId][chNum] = !!targetState;
        }
        function setPowerCabinetDesiredState(cabId, targetState) {
            const cab = configData.cabinets[cabId] || {};
            const count = Number(cab.channel_count || 8);
            for (let chNum = 1; chNum <= count; chNum += 1) {
                setPowerDesiredState(cabId, chNum, targetState);
            }
        }
        function clearPowerCabinetDesiredState(cabId) {
            if (pwrDesiredStates[cabId]) pwrDesiredStates[cabId] = {};
        }
        function clearPowerDesiredState(cabId, chNum) {
            if (pwrDesiredStates[cabId]) delete pwrDesiredStates[cabId][chNum];
        }
        function shouldAcceptPowerState(cabId, chNum, incomingState) {
            const desired = pwrDesiredStates[cabId]?.[chNum];
            if (!desired) return true;
            const age = Date.now() - desired.ts;
            const matchesTarget = !!incomingState === !!desired.target;
            if (matchesTarget) {
                desired.confirmed = true;
                desired.confirmedAt = Date.now();
                return true;
            }
            if (age < POWER_CHANNEL_VERIFY_HOLD_MS) return false;
            delete pwrDesiredStates[cabId][chNum];
            return true;
        }
        function applyPowerStatusSnapshot(cabId, status) {
            if (!status || !Array.isArray(status.channels_1_4)) return false;
            const previous = powerStatusCache[cabId] || {};
            const safeStatus = Object.assign({}, previous, status || {});
            const nextStates = safeStatus.channels_1_4.map((st, idx) => {
                const chNum = idx + 1;
                if (!shouldAcceptPowerState(cabId, chNum, st)) {
                    const desired = pwrDesiredStates[cabId]?.[chNum];
                    return desired ? desired.target : (pwrStates[cabId] || [])[chNum];
                }
                return st;
            });
            safeStatus.channels_1_4 = nextStates;
            safeStatus.channel_on_count = nextStates.filter(Boolean).length;
            powerStatusCache[cabId] = safeStatus;
            pwrStates[cabId] = pwrStates[cabId] || [];
            nextStates.forEach((st, idx) => {
                const chNum = idx + 1;
                pwrStates[cabId][chNum] = st;
                renderPwrChannel(cabId, chNum);
            });
            return true;
        }
        const lightLocks = {};
        const lightStates = {};
        const lightOnlineStates = {};
        const projectorConfigs = configData.projectors || [];
        const upsConfigs = configData.ups_devices || [];
        const snmpConfigs = configData.snmp_devices || [];
        const nvrConfigs = Array.isArray(configData.nvr_devices) ? configData.nvr_devices : [];
        const sequencerConfigs = Array.isArray(configData.sequencers) ? configData.sequencers : [];
        const dashboardSectionConfig = configData.dashboard_sections || {};
        let doorVideoActive = false;
        let doorVideoNonce = 0;
        let lastDoorStatusFetchAt = 0;
        let doorCameraStatusCache = {};
        let doorViewSlots = ((configData.door_config || {}).view_slots) || { left: 'main', right: 'aux' };
        let doorRegionsCache = ((configData.door_config || {}).regions) || {};
        let appPollingStarted = false;
        const pollingTasks = [];
        const serverCommandPending = {};
        let serverCommandRefreshTimer = null;
        function setDoorSlotVisual(slot, payload) {
            const els = getDoorSlotElements(slot);
            const stateEl = els.state;
            const metaEl = els.meta;
            if (!stateEl || !metaEl) return;
            const enabled = payload ? payload.enabled !== false : true;
            const online = !!(payload && payload.online);
            const configured = !!(payload && payload.configured);
            const transport = String((payload && payload.transport) || '').toUpperCase();
            stateEl.textContent = !enabled ? '停用' : (online ? '在线' : (configured ? '离线' : '未配置'));
            stateEl.className = `tag ${(!enabled) ? '' : (online ? 'green' : (configured ? 'warn' : ''))}`;
            if (!enabled) {
                metaEl.textContent = '监控已停用';
                return;
            }
            if (!configured) {
                metaEl.textContent = '未配置 RTSP';
                return;
            }
            if (online) {
                metaEl.textContent = `${transport || '--'} · ${payload.frame_width || '--'}x${payload.frame_height || '--'}`;
                return;
            }
            metaEl.textContent = payload.last_error_text || payload.last_error || '等待重连';
        }
        function formatDoorCameraDiag(payload) {
            const p = payload && typeof payload === 'object' ? payload : {};
            const name = String(p.name || p.key || '--');
            const host = String(p.host || '--');
            const enabled = p.enabled === false ? '停用' : '启用';
            const configured = p.configured ? '已配置' : '未配置';
            const online = p.online ? '在线' : '离线';
            const transport = p.online ? String((p.transport || '--')).toUpperCase() : '--';
            const errorText = String(p.last_error_text || p.last_error || (p.online ? '正常' : '等待重连'));
            const lastAttempt = String(p.last_attempt_at || '--');
            return `
                <div style="padding:12px 14px; border-radius:12px; background:rgba(15,23,42,0.72); border:1px solid rgba(148,163,184,0.14); min-width:220px; flex:1;">
                    <div style="display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px;">
                        <strong style="color:#e2e8f0; font-size:13px;">${escapeHtml(name)}</strong>
                        <span class="tag ${p.online ? 'green' : 'warn'}">${escapeHtml(online)}</span>
                    </div>
                    <div style="font-size:12px; color:#94a3b8; line-height:1.8;">
                        <div>地址: <span style="color:#e2e8f0;">${escapeHtml(host)}</span></div>
                        <div>状态: <span style="color:#e2e8f0;">${enabled} / ${configured}</span></div>
                        <div>链路: <span style="color:#e2e8f0;">${escapeHtml(transport)}</span></div>
                        <div>错误: <span style="color:#f8fafc;">${escapeHtml(errorText)}</span></div>
                        <div>最近尝试: <span style="color:#e2e8f0;">${escapeHtml(lastAttempt)}</span></div>
                    </div>
                </div>
            `;
        }
        function renderDoorNetworkSummary() {
            const container = document.getElementById('doorNetworkSummary');
            if (!container) return;
            const leftPayload = doorCameraStatusCache[getDoorSlotCameraKey('left')] || {};
            const rightPayload = doorCameraStatusCache[getDoorSlotCameraKey('right')] || {};
            container.innerHTML = `${formatDoorCameraDiag(leftPayload)}${formatDoorCameraDiag(rightPayload)}`;
        }
        function syncDoorVideoSources(forceReload = false) {
            [['left', getDoorSlotElements('left')], ['right', getDoorSlotElements('right')]].forEach(([slot, els]) => {
                if (!els.image) return;
                const cameraKey = getDoorSlotCameraKey(slot);
                const payload = doorCameraStatusCache[cameraKey] || {};
                const targetSrc = `/video_feed/${cameraKey}?_=${doorVideoNonce}`;
                if (!doorVideoActive || payload.enabled === false || payload.configured === false) {
                    els.image.removeAttribute('src');
                    return;
                }
                const currentSrc = String(els.image.getAttribute('src') || '');
                if (forceReload || !currentSrc || !currentSrc.includes(`/video_feed/${cameraKey}`)) {
                    els.image.src = targetSrc;
                }
            });
        }
        function getDoorSlotCameraKey(slot) {
            const key = String((doorViewSlots || {})[slot] || '').trim();
            if (key) return key;
            return slot === 'right' ? 'main' : 'aux';
        }
        function getDoorSlotElements(slot) {
            const isRight = slot === 'right';
            return {
                image: document.getElementById(isRight ? 'videoImgAux' : 'videoImg'),
                canvas: document.getElementById(isRight ? 'drawCanvasAux' : 'drawCanvasMain'),
                label: document.getElementById(isRight ? 'doorCameraAuxLabel' : 'doorCameraMainLabel'),
                state: document.getElementById(isRight ? 'doorCameraAuxState' : 'doorCameraMainState'),
                meta: document.getElementById(isRight ? 'doorCameraAuxMeta' : 'doorCameraMainMeta'),
            };
        }
        function updateDoorSlotLabels() {
            ['left', 'right'].forEach(slot => {
                const cameraKey = getDoorSlotCameraKey(slot);
                const payload = doorCameraStatusCache[cameraKey] || {};
                const els = getDoorSlotElements(slot);
                if (els.label) {
                    const slotText = slot === 'right' ? '右侧画面' : '左侧画面';
                    els.label.textContent = `${slotText} · ${payload.name || cameraKey || '--'}`;
                }
            });
        }
        function startDoorVideoStream() {
            const leftEls = getDoorSlotElements('left');
            const rightEls = getDoorSlotElements('right');
            if (!leftEls.image && !rightEls.image) return;
            doorVideoActive = true;
            doorVideoNonce += 1;
            syncDoorVideoSources(true);
            updateDoorSlotLabels();
        }
        function stopDoorVideoStream() {
            doorVideoActive = false;
            ['left', 'right'].forEach(slot => {
                const els = getDoorSlotElements(slot);
                if (els.image) els.image.removeAttribute('src');
            });
        }
        function isPageVisible() {
            return document.visibilityState !== 'hidden';
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                stopDoorVideoStream();
            } else if (getActiveViewId() === 'door') {
                setTimeout(() => {
                    startDoorVideoStream();
                    updateDoorStatus(true);
                }, 80);
            }
            refreshPollingVisibility();
        });
        function getActiveViewId() {
            const active = document.querySelector('.view-section.active');
            return active ? String(active.id || '').replace(/^view-/, '') : 'dashboard';
        }
        function isDashboardSectionVisible(sectionId) {
            const dashboard = document.getElementById('view-dashboard');
            if (!dashboard || !dashboard.classList.contains('active')) return false;
            const section = dashboard.querySelector(`[data-section-id="${sectionId}"]`);
            if (!section) return false;
            if (section.style.display === 'none') return false;
            const style = window.getComputedStyle ? window.getComputedStyle(section) : null;
            return !style || (style.display !== 'none' && style.visibility !== 'hidden');
        }
        function registerPollingTask(name, intervalMs, run, shouldRun) {
            pollingTasks.push({
                name,
                intervalMs: Math.max(300, Number(intervalMs) || 1000),
                baseIntervalMs: Math.max(300, Number(intervalMs) || 1000),
                run,
                shouldRun: typeof shouldRun === 'function' ? shouldRun : (() => true),
                timer: null,
                running: false,
            });
        }
        function setTextIfExists(id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        }
        function setHtmlIfExists(id, html) {
            const el = document.getElementById(id);
            if (el) el.innerHTML = html;
        }
        function normalizeDashboardSummaryPayload(payload) {
            return payload && typeof payload === 'object' ? payload : { counts: {}, modules: {} };
        }
        function getDashboardSummaryModule(name) {
            return ((dashboardSummaryCache || {}).modules || {})[name] || {};
        }
        function getDashboardSummaryCount(name) {
            return ((dashboardSummaryCache || {}).counts || {})[name] || {};
        }
        function renderDashboardSummaryTopStats(payload) {
            const data = normalizeDashboardSummaryPayload(payload);
            const counts = data.counts || {};
            const modules = data.modules || {};
            const power = counts.power || {};
            const light = counts.light || {};
            const sequencer = counts.sequencer || {};
            const server = counts.server || {};
            const snmp = counts.snmp || {};
            const nvr = counts.nvr || {};
            const networkDevices = [
                ...(((modules.snmp || {}).devices) || []),
                ...(((modules.nvr || {}).devices) || []),
            ];
            const proxy = modules.proxy || {};
            setTextIfExists('dash-power-online', String(power.online ?? 0));
            setTextIfExists('dash-light-online', String(light.online ?? 0));
            setTextIfExists('dash-sequencer-online', String(sequencer.online ?? 0));
            setTextIfExists('dash-sequencer-total', String(sequencer.total ?? 0));
            setTextIfExists('dash-server-online', String(server.online ?? 0));
            setTextIfExists('dash-server-total', String(server.total ?? 0));
            const snmpOnline = Number(snmp.online || 0) + Number(nvr.online || 0);
            const snmpTotal = Number(snmp.total || 0) + Number(nvr.total || 0);
            const snmpCritical = networkDevices.filter(item => {
                const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
                return risk === 'critical' || risk === 'error';
            }).length;
            const snmpWarning = networkDevices.filter(item => {
                const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
                return risk === 'warning' || risk === 'stale';
            }).length;
            setTextIfExists('dash-snmp-online', String(snmpOnline));
            setTextIfExists('dash-snmp-total', String(snmpTotal));
            setTextIfExists('dash-snmp-critical', String(snmpCritical));
            setTextIfExists('dash-snmp-warning', String(snmpWarning));
            setTextIfExists('dash-snmp-alert', String(snmpCritical + snmpWarning));
            renderDashboardProxySummary(proxy);
            renderDashboardEnvSummary(modules.env || {});
            renderDashboardFooterStatus(data, { snmpCritical, snmpWarning, snmpOnline, snmpTotal });
        }
        function renderDashboardFooterStatus(payload = {}, derived = {}) {
            const counts = (payload && payload.counts) || {};
            const autoErrors = Number(document.getElementById('dash-auto-errors')?.textContent || 0);
            const critical = Number(derived.snmpCritical || 0) + autoErrors;
            const warning = Number(derived.snmpWarning || 0);
            const groups = ['power', 'light', 'sequencer', 'server'];
            let online = 0;
            let total = 0;
            groups.forEach(key => {
                const item = counts[key] || {};
                online += Number(item.online || 0);
                total += Number(item.total || 0);
            });
            online += Number(derived.snmpOnline || 0);
            total += Number(derived.snmpTotal || 0);
            const offline = Math.max(0, total - online);
            const stability = total > 0 ? `${Math.max(0, Math.min(99.9, (online / total) * 100)).toFixed(1)}%` : '--';
            setTextIfExists('dashboard-footer-critical', String(critical + warning));
            setTextIfExists('dashboard-footer-warning', String(warning));
            setTextIfExists('dashboard-footer-offline', String(offline));
            setTextIfExists('dashboard-footer-stability', stability);
        }
        function renderDashboardEnvSummary(envModule = {}) {
            const devices = Array.isArray(envModule.devices) ? envModule.devices : [];
            if (!devices.length) return;
            const envMap = {};
            devices.forEach(item => {
                if (item && item.id) envMap[item.id] = item;
            });
            const picked = pickDashboardEnvSensor(envMap);
            const topSummary = document.getElementById('top-env-summary');
            if (picked && picked.st) {
                const st = picked.st || {};
                setTextIfExists('top-env-temp', st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--');
                setTextIfExists('top-env-hum', st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--');
                setTextIfExists('top-env-lux', st.lux !== null && st.lux !== undefined ? `${st.lux}Lux` : '--');
                if (topSummary) topSummary.style.opacity = picked.st.online ? '1' : '0.75';
            }
        }
        function renderDashboardProxySummary(payload = {}) {
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
        }
        function updateDashboardSummary() {
            if (dashboardSummaryInFlight) return dashboardSummaryInFlight;
            dashboardSummaryInFlight = fetchJson('/api/dashboard/summary', {}, '首页汇总状态读取失败')
                .then(data => {
                    dashboardSummaryCache = normalizeDashboardSummaryPayload(data);
                    renderDashboardSummaryTopStats(dashboardSummaryCache);
                    const serverMachines = dashboardSummaryCache.modules?.server?.machines;
                    if (Array.isArray(serverMachines)) {
                        dashboardServerCompactList = serverMachines;
                        renderDashboardServerCompact(dashboardServerCompactList);
                    }
                    if (getActiveViewId() === 'proxy' && dashboardSummaryCache.modules?.proxy) {
                        proxyStatusCache = dashboardSummaryCache.modules.proxy;
                        renderProxyDetail(proxyStatusCache);
                    }
                    return dashboardSummaryCache;
                })
                .catch(err => {
                    console.error('首页汇总状态读取失败', err);
                    throw err;
                })
                .finally(() => {
                    dashboardSummaryInFlight = null;
                });
            return dashboardSummaryInFlight;
        }
        function resolveVisiblePowerSupplementCabIds(activeView = getActiveViewId()) {
            if (activeView === 'power') {
                return Array.isArray(configData.cabinets) ? configData.cabinets.map((_, idx) => idx) : [];
            }
            if (activeView === 'dashboard' && (isDashboardSectionVisible('power_compact') || isDashboardSectionVisible('power_quick'))) {
                return Array.isArray(configData.cabinets)
                    ? configData.cabinets
                        .map((_, idx) => idx)
                        .filter(idx => !!document.getElementById(`dash-power-card-${idx}`))
                    : [];
            }
            return [];
        }
        function applyAdaptivePollingInterval(task) {
            if (!task) return;
            const base = Number(task.baseIntervalMs || task.intervalMs || 1000);
            const activeView = getActiveViewId();
            const isSnmpTask = task.name === 'snmp';
            const isLightTask = task.name === 'light';
            const isPowerTask = task.name === 'power';
            const isDetailView = (isSnmpTask && activeView === 'snmp') || (isLightTask && activeView === 'light') || (isPowerTask && activeView === 'power');
            if (isDetailView) {
                task.intervalMs = base;
                return;
            }
            const dashboardMode = activeView === 'dashboard';
            if (dashboardMode && task.shouldRun()) {
                task.intervalMs = Math.round(base * (isSnmpTask ? 1.35 : (isPowerTask ? 1.2 : 1.2)));
            } else {
                task.intervalMs = Math.round(base * (isSnmpTask ? 2.0 : (isPowerTask ? 1.4 : 1.6)));
            }
        }
        function stopAllPollingTasks() {
            pollingTasks.forEach(task => {
                if (task.timer) {
                    clearTimeout(task.timer);
                    task.timer = null;
                }
            });
        }
        function schedulePollingTask(task, delayMs = null) {
            if (task.timer) clearTimeout(task.timer);
            applyAdaptivePollingInterval(task);
            task.timer = setTimeout(async () => {
                task.timer = null;
                if (!isPageVisible() || !task.shouldRun()) {
                    schedulePollingTask(task, task.intervalMs);
                    return;
                }
                if (task.running) {
                    schedulePollingTask(task, task.intervalMs);
                    return;
                }
                task.running = true;
                try {
                    await task.run();
                } catch (err) {
                    console.error(`Polling task failed: ${task.name}`, err);
                } finally {
                    task.running = false;
                    schedulePollingTask(task, task.intervalMs);
                }
            }, Math.max(50, delayMs ?? task.intervalMs));
        }
        const DASHBOARD_POLLING_INITIAL_DELAYS = {
            dashboard_summary: 80,
            hvac: 360,
            power: 680,
            light: 920,
            sequencer: 1160,
            ups: 1380,
            env: 1580,
            door: 1780,
            hy_edge: 2020,
            snmp: 2350,
            projector: 2700,
            screen: 3000,
            automation: 3300,
            logs: 3650,
            meter: 3900,
        };
        function getPollingInitialDelay(task, index) {
            const activeView = getActiveViewId();
            if (activeView === 'dashboard') {
                return DASHBOARD_POLLING_INITIAL_DELAYS[task.name] ?? (500 + index * 220);
            }
            return 90 + index * 120;
        }
        function startAppPolling() {
            if (appPollingStarted) return;
            appPollingStarted = true;
            pollingTasks.forEach((task, index) => schedulePollingTask(task, getPollingInitialDelay(task, index)));
        }
        function refreshPollingVisibility() {
            if (!isPageVisible()) {
                stopDoorVideoStream();
                stopAllPollingTasks();
                return;
            }
            pollingTasks.forEach((task, index) => {
                if (!task.timer) schedulePollingTask(task, getPollingInitialDelay(task, index));
            });
        }
        let projectorStatusCache = {};
        let sequencerStatusCache = {};
        let currentProjectorRemoteId = null;
        let sequencerFilters = { dashboard: 'all', page: 'all' };
        let globalServerList = [];
        let dashboardServerCompactList = [];
        function canOpenConfigCenter() {
            const role = String(currentUser.role || '').toLowerCase();
            const accountCategory = String(currentUser.account_category || '').toLowerCase();
            if (role === 'admin' || accountCategory === 'admin') return true;
            const hasView = hasPermission('config.view');
            const hasElevatedConfigPermission = hasPermission('system.config')
                || hasPermission('auth.manage')
                || hasPermission('meter.config')
                || hasPermission('control_center.config');
            return hasView && hasElevatedConfigPermission;
        }
        let appleLibrary = [];
        let appleOutputZones = [];
        let appleQueue = [];
        let appleNowPlaying = null;
        let appleIsPlaying = false;
        let appleElapsedSec = 0;
        let appleStateCache = null;
        let appleStateLoading = false;
        let appleLyricsTrackId = '';
        let appleLyricsType = 'none';
        let appleLyricsPlain = '';
        let appleLyricsLines = [];
        let appleLyricsActiveIndex = -1;
        let appleCategorySelected = 'all';
        const serverMonitorConfig = configData.server_monitor || { agent_host: '', agent_port: 6899 };
        let latestAgentVersion = String(serverMonitorConfig.agent_version || '').trim();
        const hvacConfigs = Array.isArray(configData.hvac_devices) ? configData.hvac_devices : [];
        let hvacStatusCache = {};
        if (!Array.isArray(configData.sidebar)) configData.sidebar = [];
        if (hvacConfigs.length && !configData.sidebar.find(item => item.id === 'hvac')) {
            configData.sidebar.push({ id: 'hvac', icon: '❄️', name: '空调控制', sort: 4.6, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'sequencer')) {
            configData.sidebar.push({ id: 'sequencer', icon: '🔌', name: '时序电源', sort: 3, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'snmp')) {
            configData.sidebar.push({ id: 'snmp', icon: '📡', name: 'SNMP监测', sort: 4.2, visible: true });
        }
        if (!configData.sidebar.find(item => item.id === 'apple_audio')) {
            configData.sidebar.push({ id: 'apple_audio', icon: '🎼', name: '音乐播放器', sort: 10.5, visible: true });
        }
        if (hvacConfigs.length && !dashboardSectionConfig.hvac) {
            dashboardSectionConfig.hvac = { title: '空调总览', visible: true, sort: 24 };
        }
        if (!dashboardSectionConfig.sequencer) {
            dashboardSectionConfig.sequencer = { title: '时序电源', visible: true, sort: 25 };
        }
        if (!dashboardSectionConfig.snmp) {
            dashboardSectionConfig.snmp = { title: '网络与录像机', visible: true, sort: 27 };
        }
        const homeDashboardOrder = {
            stats: 10,
            projector: 20,
            hvac: 21,
            hy_edge: 22,
            ups_compact: 23,
            screen: 24,
            sequencer: 25,
            light_compact: 26,
            power_compact: 27,
            snmp: 27.2,
            server_compact: 28,
        };
        Object.entries(homeDashboardOrder).forEach(([key, sort]) => {
            dashboardSectionConfig[key] = Object.assign(
                { title: key, visible: true, sort },
                dashboardSectionConfig[key] || {},
                { sort }
            );
        });
        const dashboardSectionDefaults = {
            power_compact: { title: '强电柜状态', visible: true, sort: homeDashboardOrder.power_compact },
            light_compact: { title: '灯光控制显示', visible: true, sort: homeDashboardOrder.light_compact },
            server_compact: { title: '机器状态', visible: true, sort: homeDashboardOrder.server_compact },
            ups_compact: { title: 'UPS状态', visible: true, sort: homeDashboardOrder.ups_compact },
            screen: { title: '幕布状态', visible: true, sort: homeDashboardOrder.screen },
        };
        Object.entries(dashboardSectionDefaults).forEach(([key, defaults]) => {
            dashboardSectionConfig[key] = Object.assign({}, defaults, dashboardSectionConfig[key] || {}, { sort: defaults.sort });
        });
        if (dashboardSectionConfig.screen) {
            dashboardSectionConfig.screen.sort = homeDashboardOrder.screen;
            dashboardSectionConfig.screen.visible = dashboardSectionConfig.screen.visible !== false;
        }
        function getAgentBaseUrl() {
            const host = (serverMonitorConfig.agent_host || '').trim() || window.location.hostname;
            const port = parseInt(serverMonitorConfig.agent_port || 6899, 10) || 6899;
            return `http://${host}:${port}`;
        }
        function getDeployBatUrl() {
            return `${getAgentBaseUrl()}/deploy_agent.bat`;
        }
        function getDeployCommandText() {
            const batUrl = `${getDeployBatUrl()}?ts=$(Get-Date -Format yyyyMMddHHmmss)`;
            return `$u="${batUrl}"; $p="$env:TEMP\\smart-center-deploy.bat"; iwr -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -Uri $u -OutFile $p; Start-Process -FilePath $p -Verb RunAs`;
        }
        function formatDeployGeneratedAt(date = new Date()) {
            const pad = value => String(value).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
        }
        function updateDeployModalInfo() {
            const versionEl = document.getElementById('deploy-agent-version-text');
            if (versionEl) versionEl.textContent = latestAgentVersion || '读取中...';
            const generatedAtEl = document.getElementById('deploy-generated-at-text');
            if (generatedAtEl) generatedAtEl.textContent = formatDeployGeneratedAt();
            const deployCmdEl = document.getElementById('deploy-cmd-text');
            if (deployCmdEl) deployCmdEl.textContent = getDeployCommandText();
            const deployBatUrlEl = document.getElementById('deploy-bat-url-text');
            if (deployBatUrlEl) deployBatUrlEl.textContent = getDeployBatUrl();
        }
        function openDeployModal() {
            updateDeployModalInfo();
            const modal = document.getElementById('deployModal');
            if (modal) modal.style.display = 'block';
            refreshLatestAgentVersion().finally(() => updateDeployModalInfo());
        }
        function parseAgentVersionBase(version) {
            const text = String(version || '').trim();
            const match = text.match(/\d+(?:\.\d+){3}/);
            if (!match) return null;
            return match[0].split('.').map(part => Number.parseInt(part, 10));
        }
        function compareAgentVersionBase(currentVersion, latestVersion) {
            const currentParts = parseAgentVersionBase(currentVersion);
            const latestParts = parseAgentVersionBase(latestVersion);
            if (!currentParts || !latestParts) {
                const currentText = String(currentVersion || '').trim();
                const latestText = String(latestVersion || '').trim();
                return currentText === latestText ? 0 : -1;
            }
            for (let i = 0; i < Math.max(currentParts.length, latestParts.length); i += 1) {
                const current = currentParts[i] || 0;
                const latest = latestParts[i] || 0;
                if (current < latest) return -1;
                if (current > latest) return 1;
            }
            return 0;
        }
        function refreshLatestAgentVersion() {
            const ts = Date.now();
            const primaryUrl = `/agent/config?probe=1&ts=${ts}`;
            const fallbackUrl = `${getAgentBaseUrl()}/agent/config?probe=1&ts=${ts}`;
            const applyVersion = data => {
                const version = String(data?.version || '').trim();
                if (version) {
                    latestAgentVersion = version;
                    updateDeployModalInfo();
                    if (Array.isArray(globalServerList) && globalServerList.length) {
                        const sContainer = document.getElementById('server-grid-container');
                        if (sContainer) sContainer.innerHTML = renderServerGroupedGrid(globalServerList);
                        renderDashboardServerCompact(globalServerList);
                    }
                }
                return version;
            };
            return fetchJson(primaryUrl, {}, '读取 Agent 最新版本失败')
                .catch(() => fetchJson(fallbackUrl, {}, '读取 Agent 最新版本失败'))
                .then(data => {
                    return applyVersion(data);
                })
                .catch(err => {
                    console.warn('Agent 最新版本读取失败', err);
                    return latestAgentVersion;
                });
        }
        function copyDeployCommand() {
            return copyTextWithToast(getDeployCommandText(), '覆盖安装命令已复制');
        }
        function copyDeployBatUrl() {
            return copyTextWithToast(getDeployBatUrl(), '批处理地址已复制');
        }
        function buildServerDiagnostic(agent = {}, machine = {}) {
            const diagnostic = machine?.diagnostic || {};
            const st = machine?.status || {};
            const isOnline = !!machine?.is_online;
            const hasRuntime = !!diagnostic.has_runtime_metrics;
            const reportOnline = !!(machine?.report_online || diagnostic.report_online);
            if (!isOnline && !reportOnline) {
                return {
                    level: 'offline',
                    code: String(diagnostic.code || 'offline_unreachable').trim(),
                    badgeText: '离线',
                    badgeClass: 'error',
                    summary: '节点离线',
                    detail: '',
                    rootCause: '',
                    recommendation: '',
                    logExcerpt: '',
                    needsRedeploy: false,
                    hasRuntime,
                    isOnline,
                    reportOnline: false,
                    agentHeartbeatOnline: !!(machine?.agent_heartbeat_online || diagnostic.agent_heartbeat_online),
                    runtimeFresh: !!(machine?.runtime_fresh || diagnostic.runtime_fresh),
                    lastReportKind: String(machine?.last_report_kind || diagnostic.last_report_kind || st.last_report_kind || '').trim(),
                    hardwareRefreshedAt: st.hardware_refreshed_at || '',
                };
            }
            const level = String(diagnostic.level || (isOnline && hasRuntime ? 'success' : 'warn'));
            const code = String(diagnostic.code || '').trim();
            const badgeMap = {
                healthy: ['运行正常', 'normal'],
                offline_unreachable: ['离线', 'error'],
                agent_offline_host_reachable: ['Agent离线', 'warn'],
                offline: ['离线', 'error'],
                runtime_stale: ['采集陈旧', 'warn'],
                agent_heartbeat_runtime_stale: ['采集停滞', 'warn'],
                agent_outdated: ['需更新', 'warn'],
                agent_update_failed: ['更新失败', 'error'],
                bootstrap_failed: ['启动失败', 'error'],
                bootstrap_only: ['启动中', 'warn'],
                task_missing: ['任务缺失', 'warn'],
                manual_only: ['未接入', 'warn'],
                partial_metrics: ['采集不全', 'warn'],
            };
            const mappedBadge = badgeMap[code] || null;
            let badgeText = mappedBadge ? mappedBadge[0] : '关注中';
            if (!mappedBadge && level === 'success') badgeText = '运行正常';
            else if (!mappedBadge && level === 'error') badgeText = '需要处理';
            const badgeClass = mappedBadge ? mappedBadge[1] : (level === 'success' ? 'normal' : (level === 'warn' ? 'warn' : 'error'));
            const recommendation = String(diagnostic.suggestion || '').trim();
            const summary = String(diagnostic.summary || '').trim() || '等待节点上报';
            return {
                level,
                code,
                badgeText,
                badgeClass,
                summary,
                detail: String(diagnostic.detail || '').trim(),
                rootCause: String(diagnostic.root_cause || '').trim(),
                recommendation,
                logExcerpt: String(diagnostic.log_excerpt || '').trim(),
                needsRedeploy: !!diagnostic.needs_redeploy,
                hasRuntime,
                isOnline,
                reportOnline,
                agentHeartbeatOnline: !!(machine?.agent_heartbeat_online || diagnostic.agent_heartbeat_online),
                runtimeFresh: !!(machine?.runtime_fresh || diagnostic.runtime_fresh),
                lastReportKind: String(machine?.last_report_kind || diagnostic.last_report_kind || st.last_report_kind || '').trim(),
                hardwareRefreshedAt: st.hardware_refreshed_at || '',
            };
        }

        function showToast(msg, isError=false) { const t = document.getElementById('toast'); t.innerText = msg; t.className = 'toast-msg show' + (isError ? ' toast-error' : ''); setTimeout(() => t.className = 'toast-msg', 2500); }
        function translateApiError(error, fallbackText='请求失败') {
            const text = String(error ?? '').trim();
            if (!text) return fallbackText;
            const map = {
                login_required: '当前会话未登录，请先登录后再操作',
                account_disabled: '当前账号已停用',
                permission_denied: '当前账号没有此功能权限',
                permission_time_restricted: '当前时段不允许执行此操作',
                account_frozen: '当前账号已冻结',
                account_temporarily_disabled: '当前账号已被临时停用',
                account_temporarily_disabled_until: '当前账号处于临时停用时段',
                temporary_control_blocked: '当前账号的控制权限已被临时关闭',
                outside_control_schedule: '当前不在允许控制的时间段内',
                permission_not_granted: '当前账号没有此功能权限'
            };
            if (map[text]) return map[text];
            if (text.startsWith('http_')) {
                const code = text.split('_')[1] || '';
                return `请求失败（HTTP ${code}）`;
            }
            return text;
        }
        async function parseJsonResponse(response, fallbackText='请求失败', options={}) {
            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = {};
            }
            const allowBusinessError = !!options.allowBusinessError;
            if (!response.ok || (!allowBusinessError && data?.ok === false)) {
                const message = data?.msg || data?.message || data?.error || fallbackText;
                throw new Error(translateApiError(message, fallbackText));
            }
            return data;
        }
        const fetchJsonInFlight = new Map();
        function getFetchJsonDedupeKey(url, options={}) {
            const method = String(options?.method || 'GET').toUpperCase();
            if (method !== 'GET') return '';
            const body = options?.body;
            if (body !== undefined && body !== null) return '';
            const headers = options?.headers;
            let headerKey = '';
            if (headers instanceof Headers) {
                headerKey = Array.from(headers.entries()).sort().map(([k, v]) => `${k}:${v}`).join('|');
            } else if (headers && typeof headers === 'object') {
                headerKey = Object.keys(headers).sort().map(k => `${k}:${headers[k]}`).join('|');
            }
            return `${method} ${url} ${headerKey}`;
        }
        async function fetchJson(url, options={}, fallbackText='请求失败', parseOptions={}) {
            const dedupeKey = getFetchJsonDedupeKey(url, options);
            if (dedupeKey && fetchJsonInFlight.has(dedupeKey)) {
                return fetchJsonInFlight.get(dedupeKey);
            }
            const requestPromise = fetch(url, options)
                .then(response => parseJsonResponse(response, fallbackText, parseOptions))
                .finally(() => {
                    if (dedupeKey) fetchJsonInFlight.delete(dedupeKey);
                });
            if (dedupeKey) fetchJsonInFlight.set(dedupeKey, requestPromise);
            return requestPromise;
        }
        async function fetchJsonLoose(url, options={}, fallbackText='请求失败') {
            return fetchJson(url, options, fallbackText, { allowBusinessError: true });
        }
        function toggleUserMenu(forceOpen = null) {
            const menu = document.getElementById('top-user-menu');
            if (!menu) return;
            const shouldOpen = forceOpen === null ? !menu.classList.contains('open') : !!forceOpen;
            menu.classList.toggle('open', shouldOpen);
        }
        function openConfigCenter() {
            if (!canOpenConfigCenter()) {
                showToast('当前账号无配置中心访问权限', true);
                return;
            }
            window.location.href = '/config';
        }
        function goToLoginPage() {
            toggleUserMenu(false);
            window.location.href = '/login';
        }
        function logoutCurrentUser() {
            toggleUserMenu(false);
            fetchJson('/api/auth/logout', { method: 'POST' }, '退出登录失败')
                .then(() => {
                    showToast('已退出当前账号');
                    window.location.href = '/login';
                })
                .catch(err => showToast(err.message || '退出登录失败', true));
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
            (appleLibrary || []).forEach(item => {
                const track = normalizeAppleTrack(item);
                const key = getAppleCategoryLabel(track.category);
                counts.set(key, (counts.get(key) || 0) + 1);
            });
            const options = [{ key: 'all', label: `全部 (${appleLibrary.length})` }];
            Array.from(counts.entries())
                .sort((a, b) => a[0].localeCompare(b[0], 'zh-Hans-CN'))
                .forEach(([key, count]) => {
                    options.push({ key, label: `${key} (${count})` });
                });
            if (appleCategorySelected !== 'all' && !counts.has(appleCategorySelected)) {
                appleCategorySelected = 'all';
            }
            wrap.innerHTML = options.map(opt => `
                <button class="apple-cat-chip ${appleCategorySelected === opt.key ? 'active' : ''}" onclick="setAppleCategoryFilter('${escapeHtml(opt.key)}')">
                    ${escapeHtml(opt.label)}
                </button>
            `).join('');
        }
        function setAppleCategoryFilter(value) {
            appleCategorySelected = String(value || 'all');
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
            noteEl.innerText = scanState.last_scan_at ? `最近扫描：${formatDateTimeText(scanState.last_scan_at)}` : '等待扫描';
            wrap.style.display = '';
        }
        function getAppleCoverHtml(track) {
            const item = track || {};
            const title = escapeHtml(item.title || '曲目封面');
            if (item.coverAvailable && item.coverUrl) {
                return `<img src="${escapeHtml(item.coverUrl)}" alt="${title}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.apple-cover')?.classList.remove('has-image'); this.remove();">`;
            }
            return '<div class="apple-cover-badge">♪</div>';
        }
        function getAppleRowArtHtml(track) {
            const item = track || {};
            if (item.coverAvailable && item.coverUrl) {
                return `<img src="${escapeHtml(item.coverUrl)}" alt="${escapeHtml(item.title || '曲目封面')}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.textContent='${escapeHtml(item.accent || '♪')}';">`;
            }
            return escapeHtml(item.accent || '♪');
        }
        function resetAppleLyricsState() {
            appleLyricsTrackId = '';
            appleLyricsType = 'none';
            appleLyricsPlain = '';
            appleLyricsLines = [];
            appleLyricsActiveIndex = -1;
        }
        function renderAppleLyrics() {
            const boxEl = document.getElementById('appleLyricsBox');
            const typeEl = document.getElementById('appleLyricsType');
            if (!boxEl || !typeEl) return;
            if (!appleNowPlaying) {
                typeEl.innerText = '未加载';
                boxEl.innerHTML = '<div class="apple-lyrics-empty">当前曲目暂无歌词。</div>';
                return;
            }
            const typeMap = {
                synced: '逐行歌词',
                plain: '纯文本歌词',
                none: '暂无歌词'
            };
            typeEl.innerText = typeMap[appleLyricsType] || '暂无歌词';
            if (appleLyricsType === 'synced' && appleLyricsLines.length) {
                boxEl.innerHTML = appleLyricsLines.map((line, idx) => `
                    <div class="apple-lyrics-line ${idx === appleLyricsActiveIndex ? 'active' : ''}" data-lyric-index="${idx}">
                        ${escapeHtml(line.text || '')}
                    </div>
                `).join('');
                if (appleLyricsActiveIndex >= 0) {
                    const activeEl = boxEl.querySelector(`[data-lyric-index="${appleLyricsActiveIndex}"]`);
                    if (activeEl) {
                        const top = Math.max(0, activeEl.offsetTop - Math.floor(boxEl.clientHeight * 0.35));
                        boxEl.scrollTop = top;
                    }
                }
                return;
            }
            if (appleLyricsPlain) {
                boxEl.innerHTML = appleLyricsPlain
                    .split(/\n+/)
                    .map(line => `<div class="apple-lyrics-line">${escapeHtml(line)}</div>`)
                    .join('');
                return;
            }
            boxEl.innerHTML = '<div class="apple-lyrics-empty">当前曲目暂无歌词。</div>';
        }
        function updateAppleLyricsHighlight() {
            if (!appleNowPlaying || appleLyricsType !== 'synced' || !appleLyricsLines.length) {
                appleLyricsActiveIndex = -1;
                renderAppleLyrics();
                return;
            }
            const currentMs = Math.max(0, Math.floor(Number(appleElapsedSec || 0) * 1000));
            let idx = -1;
            for (let i = 0; i < appleLyricsLines.length; i += 1) {
                const ts = Number(appleLyricsLines[i]?.ts_ms || 0);
                if (ts <= currentMs) idx = i;
                else break;
            }
            if (idx !== appleLyricsActiveIndex) {
                appleLyricsActiveIndex = idx;
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
            appleLyricsTrackId = safeTrackId;
            fetchJson(`/api/apple-audio/lyrics/${encodeURIComponent(safeTrackId)}`, {}, '歌词读取失败')
                .then(data => {
                    const payload = data.lyrics || {};
                    if (appleLyricsTrackId !== safeTrackId) return;
                    appleLyricsType = String(payload.lyrics_type || 'none');
                    appleLyricsPlain = String(payload.plain || '');
                    appleLyricsLines = Array.isArray(payload.lines)
                        ? payload.lines
                            .map(item => ({
                                ts_ms: Number(item.ts_ms || 0),
                                text: String(item.text || '')
                            }))
                            .filter(item => item.text)
                            .sort((a, b) => a.ts_ms - b.ts_ms)
                        : [];
                    appleLyricsActiveIndex = -1;
                    updateAppleLyricsHighlight();
                })
                .catch(() => {
                    if (appleLyricsTrackId !== safeTrackId) return;
                    appleLyricsType = 'none';
                    appleLyricsPlain = '';
                    appleLyricsLines = [];
                    appleLyricsActiveIndex = -1;
                    renderAppleLyrics();
                });
        }
        function copyTextWithToast(text, successText = '复制成功') {
            const value = String(text || '').trim();
            if (!value) {
                showToast('没有可复制的内容', true);
                return Promise.resolve(false);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                return navigator.clipboard.writeText(value)
                    .then(() => {
                        showToast(successText);
                        return true;
                    })
                    .catch(() => {
                        const temp = document.createElement('textarea');
                        temp.value = value;
                        temp.style.position = 'fixed';
                        temp.style.opacity = '0';
                        document.body.appendChild(temp);
                        temp.focus();
                        temp.select();
                        let copied = false;
                        try {
                            copied = document.execCommand('copy');
                        } catch (_) {
                            copied = false;
                        }
                        document.body.removeChild(temp);
                        showToast(copied ? successText : '复制失败，请手动复制', !copied);
                        return copied;
                    });
            }
            const temp = document.createElement('textarea');
            temp.value = value;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.focus();
            temp.select();
            let copied = false;
            try {
                copied = document.execCommand('copy');
            } catch (_) {
                copied = false;
            }
            document.body.removeChild(temp);
            showToast(copied ? successText : '复制失败，请手动复制', !copied);
            return Promise.resolve(copied);
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
            if (!appleNowPlaying) {
                titleEl.innerText = '等待选择音源';
                metaEl.innerText = '请选择 NAS 曲目、播放列表，或接入远程播放代理。';
                currentEl.innerText = '00:00';
                totalEl.innerText = '00:00';
                fillEl.style.width = '0%';
                stateTag.innerText = '待连接';
                playBtn.innerText = '▶';
                if (authEl) authEl.innerText = appleStateCache?.auth_state || '未连接';
                if (coverWrap) {
                    coverWrap.classList.remove('has-image');
                    coverWrap.innerHTML = '<div class="apple-cover-badge">♪</div>';
                }
                return;
            }
            titleEl.innerText = appleNowPlaying.title;
            metaEl.innerText = `${appleNowPlaying.artist} · ${appleNowPlaying.album} · ${appleNowPlaying.tag}`;
            currentEl.innerText = formatAppleDuration(appleElapsedSec);
            totalEl.innerText = formatAppleDuration(appleNowPlaying.duration);
            if (appleNowPlaying.duration > 0) {
                fillEl.style.width = `${Math.min(100, (appleElapsedSec / appleNowPlaying.duration) * 100)}%`;
            } else {
                fillEl.style.width = '0%';
            }
            stateTag.innerText = appleIsPlaying ? '播放中' : '已暂停';
            playBtn.innerText = appleIsPlaying ? '❚❚' : '▶';
            if (authEl) authEl.innerText = appleStateCache?.auth_state || '未连接';
            if (coverWrap) {
                coverWrap.classList.toggle('has-image', !!(appleNowPlaying.coverAvailable && appleNowPlaying.coverUrl));
                coverWrap.innerHTML = getAppleCoverHtml(appleNowPlaying);
            }
            updateAppleLyricsHighlight();
        }
        function renderAppleOutputs() {
            const list = document.getElementById('appleOutputList');
            if (!list) return;
            if (!appleOutputZones.length) {
                list.innerHTML = '<div class="apple-empty-note">暂未配置输出区域。可在配置页补充播放主机、输出模式和分区。</div>';
                return;
            }
            list.innerHTML = appleOutputZones.map(zone => `
                <div class="apple-output-card ${zone.active ? 'active' : ''}">
                    <div class="apple-output-title"><span>${zone.name}</span><span>${zone.level}</span></div>
                    <div class="apple-output-meta">${zone.host} · ${zone.mode}</div>
                </div>
            `).join('');
        }
        function formatRelativeSeconds(seconds) {
            const total = Math.max(0, Number(seconds) || 0);
            if (total < 1) return '0秒';
            if (total < 60) return `${Math.round(total)}秒`;
            const minutes = Math.floor(total / 60);
            const remainSeconds = Math.round(total % 60);
            if (minutes < 60) return remainSeconds > 0 ? `${minutes}分${remainSeconds}秒` : `${minutes}分钟`;
            const hours = Math.floor(minutes / 60);
            const remainMinutes = minutes % 60;
            return remainMinutes > 0 ? `${hours}小时${remainMinutes}分钟` : `${hours}小时`;
        }
        function formatDateTimeText(value) {
            if (!value) return '未上报';
            const dt = new Date(String(value).replace(' ', 'T'));
            if (Number.isNaN(dt.getTime())) return String(value);
            return dt.toLocaleString('zh-CN', { hour12: false });
        }
        function formatTimeShort(value) {
            if (!value) return '--';
            const dt = new Date(String(value).replace(' ', 'T'));
            if (Number.isNaN(dt.getTime())) return String(value);
            return dt.toLocaleTimeString('zh-CN', { hour12: false });
        }
        function getDeviceStatusMeta(status = {}, options = {}) {
            const fallbackOfflineText = options.offlineText || '离线';
            const levelRaw = String(status.status_level || '').trim().toLowerCase();
            const stale = !!status.stale;
            const online = !!status.online;
            const hasError = !!(status.last_error || status.error);
            let level = levelRaw;
            if (!['online', 'stale', 'error', 'offline'].includes(level)) {
                if (online && stale) level = 'stale';
                else if (online) level = 'online';
                else if (hasError && (status.last_success_at || status.updated_at)) level = 'error';
                else if (hasError) level = 'error';
                else level = 'offline';
            }
            let chipClass = 'error';
            let text = fallbackOfflineText;
            if (level === 'online') {
                chipClass = 'online';
                text = options.onlineText || '在线';
            } else if (level === 'stale') {
                chipClass = 'warning';
                text = options.staleText || '陈旧';
            } else if (level === 'error') {
                chipClass = 'warning';
                text = options.errorText || '异常';
            }
            const lastSeen = status.last_success_at || status.updated_at || status.last_checked_at;
            const note = status.last_error
                ? `异常: ${String(status.last_error)}`
                : (level === 'stale'
                    ? `最近成功 ${formatTimeShort(lastSeen)}`
                    : (lastSeen ? `更新于 ${formatTimeShort(lastSeen)}` : '等待采集'));
            return {
                level,
                chipClass,
                text,
                note,
                lastSeen,
                lastCheckedAt: status.last_checked_at || null,
                pollFailures: Number(status.poll_failures || 0),
                isOnlineLike: level === 'online' || level === 'stale',
                isOfflineLike: level === 'offline',
            };
        }
        function getCardStateClass(meta) {
            if (!meta || meta.level === 'offline') return 'offline';
            if (meta.level === 'stale' || meta.level === 'error') return 'warning';
            return '';
        }
        function toFiniteNumber(value) {
            const num = Number(value);
            return Number.isFinite(num) ? num : null;
        }
