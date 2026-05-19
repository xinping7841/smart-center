        function renderAppleResults(keyword='') {
            const list = document.getElementById('appleResultList');
            if (!list) return;
            const text = String(keyword || '').trim().toLowerCase();
            const sourceTracks = appleLibrary.map((item, index) => normalizeAppleTrack(item, index));
            const matched = sourceTracks.filter(item => {
                const categoryOk = appleCategorySelected === 'all' || getAppleCategoryLabel(item.category) === appleCategorySelected;
                if (!categoryOk) return false;
                if (!text) return true;
                const source = `${item.title} ${item.artist} ${item.album} ${item.tag} ${item.category}`.toLowerCase();
                return source.includes(text);
            });
            list.innerHTML = matched.length ? matched.map(item => `
                <div class="apple-track-row ${appleNowPlaying && appleNowPlaying.id === item.id ? 'playing' : ''}">
                    <div class="apple-track-art">${getAppleRowArtHtml(item)}</div>
                    <div class="apple-track-copy">
                        <div class="title">${escapeHtml(item.title)}</div>
                        <div class="meta">${escapeHtml(item.artist)} · ${escapeHtml(item.album)} · ${formatAppleDuration(item.duration)} · ${escapeHtml(getAppleCategoryLabel(item.category))}</div>
                    </div>
                    <button class="apple-track-action" onclick="queueAppleTrack('${item.id}')">加入队列</button>
                </div>
            `).join('') : '<div class="apple-empty-note">没有找到匹配曲目。可以换个关键词，或检查后端播放代理配置。</div>';
        }
        function renderAppleQueue() {
            const list = document.getElementById('appleQueueList');
            const heroCount = document.getElementById('appleQueueCountHero');
            if (heroCount) heroCount.innerText = appleQueue.length;
            if (!list) return;
            list.innerHTML = appleQueue.length ? appleQueue.map((item, index) => `
                <div class="apple-track-row">
                    <div class="apple-track-art">${getAppleRowArtHtml(item)}</div>
                    <div class="apple-track-copy">
                        <div class="title">${index + 1}. ${escapeHtml(item.title)}</div>
                        <div class="meta">${escapeHtml(item.artist)} · 下一步可映射到节目单 / 场景联动</div>
                    </div>
                    <button class="apple-track-action" onclick="promoteAppleTrack(${index})">${index === 0 ? '下一首' : '提前'}</button>
                </div>
            `).join('') : '<div class="apple-empty-note">当前队列为空。你可以从左侧检索结果中添加曲目。</div>';
        }
        function queueAppleTrack(trackId) {
            postJsonLoose('/api/apple-audio/queue', { track_id: trackId }, '加入播放队列失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '加入播放队列失败', true);
                        return;
                    }
                    syncAppleState(data.state);
                    showToast(`已加入队列：${appleQueue[appleQueue.length - 1]?.title || trackId}`);
                })
                .catch(err => showToast(translateApiError(err?.message, '加入播放队列失败'), true));
        }
        function promoteAppleTrack(index) {
            if (index < 0 || index >= appleQueue.length) return;
            postJsonLoose('/api/apple-audio/queue/promote', { index }, '调整队列顺序失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '调整队列顺序失败', true);
                        return;
                    }
                    const title = appleQueue[index]?.title || '当前曲目';
                    syncAppleState(data.state);
                    showToast(`已调整为优先播放：${title}`);
                })
                .catch(err => showToast(translateApiError(err?.message, '调整队列顺序失败'), true));
        }
        function clearAppleQueue() {
            postJsonLoose('/api/apple-audio/queue/clear', {}, '清空播放队列失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '清空播放队列失败', true);
                        return;
                    }
                    syncAppleState(data.state);
                    showToast('播放队列已清空');
                })
                .catch(err => showToast(translateApiError(err?.message, '清空播放队列失败'), true));
        }
        function appleTransport(action) {
            postJsonLoose('/api/apple-audio/transport', { action }, '音乐播放器控制失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '音乐播放器控制失败', true);
                        return;
                    }
                    syncAppleState(data.state);
                    const actionMap = {
                        toggle: appleIsPlaying ? '已开始播放' : '已暂停播放',
                        next: '已切到下一首',
                        prev: '已回到当前曲目开头',
                        favorite: `已收藏：${appleNowPlaying ? appleNowPlaying.title : '当前曲目'}`
                    };
                    showToast(actionMap[action] || '操作已执行');
                })
                .catch(err => showToast(translateApiError(err?.message, '音乐播放器控制失败'), true));
        }
        function syncAppleState(state) {
            const nextState = state || {};
            const prevTrackId = appleNowPlaying ? appleNowPlaying.id : '';
            appleStateCache = nextState;
            appleLibrary = Array.isArray(nextState.library) ? nextState.library.map((item, index) => normalizeAppleTrack(item, index)) : appleLibrary;
            appleOutputZones = Array.isArray(nextState.outputs) ? nextState.outputs.map((item, index) => ({
                id: String(item.id || `zone_${index}`),
                name: String(item.name || `区域 ${index + 1}`),
                host: String(item.host || nextState.player_host || '未指定主机'),
                mode: String(item.mode || nextState.output_mode || '默认输出'),
                level: String(item.level || '--'),
                active: !!item.active
            })) : [];
            appleQueue = Array.isArray(nextState.queue) ? nextState.queue.map((item, index) => normalizeAppleTrack(item, index)) : [];
            appleNowPlaying = nextState.current_track ? normalizeAppleTrack(nextState.current_track, 0) : null;
            appleIsPlaying = !!nextState.is_playing;
            appleElapsedSec = Number(nextState.elapsed_sec || 0);
            renderAppleScanProgress(nextState.scan || {});
            renderAppleCategoryFilters();
            renderAppleNowPlaying();
            renderAppleOutputs();
            renderAppleQueue();
            renderAppleResults(document.getElementById('appleSearchInput') ? document.getElementById('appleSearchInput').value : '');
            const nextTrackId = appleNowPlaying ? appleNowPlaying.id : '';
            if (!nextTrackId) {
                resetAppleLyricsState();
                renderAppleLyrics();
            } else if (nextTrackId !== prevTrackId) {
                loadAppleLyrics(nextTrackId);
            } else {
                updateAppleLyricsHighlight();
            }
        }
        function prepareAppleAudioForM32() {
            postJsonLoose('/api/apple-audio/m32/prepare', {}, '配置 M32 通道失败')
                .then(data => {
                    if (!data.success) {
                        showToast(data.message || data.msg || '配置 M32 通道失败', true);
                        return;
                    }
                    if (data.apple_state) syncAppleState(data.apple_state);
                    showToast('M32 音乐播放器输入通道已准备完成');
                })
                .catch(err => showToast(translateApiError(err?.message, '配置 M32 通道失败'), true));
        }
        function openAppleAudioConfig() {
            if (!canOpenConfigCenter()) {
                showToast('当前账号无配置中心访问权限', true);
                return;
            }
            window.location.href = '/config#tab-univ';
        }
        function loadAppleAudioStatus(force = false) {
            if (appleStateLoading && !force) return;
            appleStateLoading = true;
            fetchJson('/api/apple-audio/status', {}, '音乐播放器状态读取失败')
                .then(data => {
                    const state = data.state || {};
                    appleLibrary = Array.isArray(state.library) ? state.library : appleLibrary;
                    syncAppleState(state);
                })
                .catch(err => console.error('音乐播放器状态更新失败', err))
                .finally(() => {
                    appleStateLoading = false;
                });
        }
        function initAppleAudioDemo() {
            loadAppleAudioStatus(true);
        }
        function ensurePowerChart(cabId) {
            if (typeof echarts === 'undefined') return null;
            const chartEl = document.getElementById(`energyChart_${cabId}`);
            if (!chartEl || chartEl.clientWidth <= 0 || chartEl.clientHeight <= 0) return null;
            if (myCharts[cabId]) return myCharts[cabId];
            try {
                myCharts[cabId] = echarts.init(chartEl);
                return myCharts[cabId];
            } catch (e) {
                console.error('强电图表初始化失败', cabId, e);
                return null;
            }
        }
        function resizePowerCharts() {
            configData.cabinets.forEach((_, cabId) => {
                const chart = ensurePowerChart(cabId);
                if (!chart) return;
                try { chart.resize(); } catch (e) { console.error('强电图表 resize 失败', cabId, e); }
            });
        }
        function renderPowerEnergyChart(cabId, rawData) {
            const chart = ensurePowerChart(cabId);
            if (!chart) return;
            const data = Array.isArray(rawData) ? rawData : [];
            const nonZeroCount = data.filter(item => Number(item.consume || 0) > 0).length;
            const option = {
                tooltip: { trigger: 'axis' },
                xAxis: {
                    type: 'category',
                    data: data.map(item => String(item.date || '').slice(5)),
                    axisLabel: {
                        color: '#94a3b8',
                        rotate: data.length > 14 ? 35 : 0,
                        interval: data.length > 20 ? 2 : 0
                    }
                },
                yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#94a3b8' } },
                series: [{
                    data: data.map(item => Number(item.consume || 0)),
                    type: 'bar',
                    barMaxWidth: data.length > 20 ? 14 : 24,
                    itemStyle: {
                        color: params => (data[params.dataIndex] && data[params.dataIndex].is_today) ? '#f59e0b' : '#3b82f6',
                        borderRadius: [4,4,0,0]
                    },
                    label: {
                        show: data.length <= 14,
                        position: 'top',
                        color: '#f8fafc'
                    }
                }],
                graphic: nonZeroCount > 1 ? [] : [{
                    type: 'text',
                    right: 12,
                    top: 10,
                    style: {
                        text: '历史数据仍在累计，当前以近 7 天摘要展示',
                        fill: '#94a3b8',
                        fontSize: 11
                    }
                }]
            };
            try {
                chart.setOption(option, true);
                chart.resize();
            } catch (e) {
                console.error('强电图表渲染失败', cabId, e);
            }
        }
        function sanitizeReadableText(value, fallback = '--') {
            const text = String(value ?? '').trim();
            if (!text) return fallback;
            return looksLikeGarbledText(text) ? fallback : text;
        }
        function formatPowerValue(value, digits = 1, suffix = '') {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return `--${suffix}`;
            return `${numeric.toFixed(digits)}${suffix}`;
        }
        function getCabinetDisplayName(cab, cabId) {
            const cabinetName = sanitizeReadableText(cab?.cabinet_name, '');
            if (cabinetName && cabinetName !== '--') return cabinetName;
            const meterName = sanitizeReadableText(cab?.meter_display_name, '');
            if (meterName && meterName !== '--') return meterName;
            return `电柜 ${Number(cabId) + 1}`;
        }
        function getCabinetSubtitle(cab) {
            const ip = sanitizeReadableText(cab?.ip, '--');
            const protocol = sanitizeReadableText(cab?.plc_type, '强电柜');
            const port = Number(cab?.port);
            return `${protocol} / ${ip}${Number.isFinite(port) ? ':' + port : ''}`;
        }
        function getPowerChannelDisplayName(cab, chNum) {
            const channels = Array.isArray(cab?.channels_config) ? cab.channels_config : [];
            const match = channels.find(item => Number(item?.channel) === Number(chNum));
            const channelName = sanitizeReadableText(match?.name, '');
            return channelName && channelName !== '--' ? channelName : `通道 ${chNum}`;
        }
        function getPowerChannelConfig(cab, chNum) {
            const channels = Array.isArray(cab?.channels_config) ? cab.channels_config : [];
            return channels.find(item => Number(item?.channel) === Number(chNum)) || {};
        }
        function getPowerChannelRemark(cab, chNum) {
            const match = getPowerChannelConfig(cab, chNum);
            const remark = sanitizeReadableText(match?.remark || match?.usage || match?.description, '');
            return remark && remark !== '--' ? remark : '';
        }
        function renderPowerChannelLabelHtml(cab, chNum, options = {}) {
            const name = getPowerChannelDisplayName(cab, chNum);
            const remark = getPowerChannelRemark(cab, chNum);
            const compact = !!options.compact;
            const remarkHtml = remark
                ? `<span class="remark" title="${escapeHtml(remark)}">${escapeHtml(remark)}</span>`
                : '';
            return `<span class="name" title="${escapeHtml(remark ? name + ' / ' + remark : name)}">${escapeHtml(name)}</span>${compact ? '' : remarkHtml}`;
        }
        function normalizeLogOperationText(log) {
            const raw = String(log?.operation || '').replace(/\[.*?\]\s*/g, '').trim();
            if (!raw) return '暂无操作记录';
            if (!looksLikeGarbledText(raw)) return raw;
            if (raw.includes('config saved') || raw.includes('hot reloaded')) return '配置已保存并热重载';
            const channelMatch = raw.match(/\d+/);
            const channelText = channelMatch ? `通道 ${channelMatch[0]}` : '设备';
            if (raw.includes('鍚堥椄')) return `${channelText} 合闸`;
            if (raw.includes('鏂紑')) return `${channelText} 断开`;
            if (raw.includes('鍏抽棴')) return `${channelText} 关闭`;
            if (raw.includes('寮€鍚')) return `${channelText} 开启`;
            if (raw.includes('鐏厜') || raw.includes('璋冨厜')) return channelMatch ? `灯光 ${channelText} 控制` : '灯光控制';
            if (raw.includes('鏃跺簭') || raw.includes('sequencer')) return '时序电源操作';
            if (raw.includes('system')) return '系统操作';
            if (raw.includes('閫氶亾')) return `${channelText} 操作`;
            return '设备操作记录';
        }
        function isDashboardTotalLogVisible(log) {
            const op = String(log?.operation || '').trim();
            if (!op) return false;
            if (op.includes('[Agent诊断]')) return false;
            if (/^\[proxy-monitor\]/i.test(op)) return false;
            if (op.includes('runtime_keys=') || op.includes('status_keys=')) return false;
            return (
                op.includes('[状态变化]') ||
                op.includes('[自动化]') ||
                op.includes('[场景]') ||
                op.includes('[服务器]') ||
                op.includes('[强电柜]') ||
                op.includes('[灯光]') ||
                op.includes('[时序电源]') ||
                op.includes('[空调]') ||
                op.includes('[门禁]') ||
                op.includes('[投影机]') ||
                op.includes('[幕布]') ||
                op.includes('控制') ||
                op.includes('指令') ||
                op.includes('开启') ||
                op.includes('关闭') ||
                op.includes('失败') ||
                op.includes('异常') ||
                op.includes('告警')
            );
        }
        function filterDashboardTotalLogs(logs) {
            return (Array.isArray(logs) ? logs : []).filter(isDashboardTotalLogVisible);
        }
        function parseLogTimeMs(log) {
            const raw = log?.time;
            if (!raw) return 0;
            const parsed = new Date(raw).getTime();
            return Number.isFinite(parsed) ? parsed : 0;
        }
        function sortLogsNewestFirst(logs) {
            return (Array.isArray(logs) ? logs : [])
                .slice()
                .sort((a, b) => {
                    const delta = parseLogTimeMs(b) - parseLogTimeMs(a);
                    if (delta) return delta;
                    return String(b?.time || '').localeCompare(String(a?.time || ''));
                });
        }
        function buildDashboardLogSignature(logs) {
            return sortLogsNewestFirst(filterDashboardTotalLogs(logs))
                .slice(0, 40)
                .map(log => [
                    String(log?.time || ''),
                    String(log?.cab_idx ?? ''),
                    String(log?.category || ''),
                    String(log?.status || ''),
                    String(log?.operation || '')
                ].join('|'))
                .join('\n');
        }
        function getPowerLogSourceMeta(log) {
            const opRaw = String(log?.operation || '').toLowerCase();
            const sourceRaw = String(log?.data_source || '').toLowerCase();
            const detailObj = (log && typeof log.detail === 'object') ? log.detail : {};
            const hasAutoHint = opRaw.includes('自动化') || opRaw.includes('automation') || opRaw.includes('[scene]') || opRaw.includes('[auto]');
            if (hasAutoHint || (log && log.category === 'automation')) {
                return { cls: 'auto', label: '自动化触发' };
            }
            if (sourceRaw.includes('remote') || sourceRaw.includes('gateway') || String(detailObj.gateway || '').toLowerCase() === 'remote') {
                return { cls: 'remote', label: '外部网关' };
            }
            return { cls: 'local', label: '本机操作' };
        }
        function renderPowerLogSourceTag(log, classPrefix = 'source-tag') {
            const meta = getPowerLogSourceMeta(log);
            return `<span class="${classPrefix} ${meta.cls}" title="${escapeHtml(meta.label)}">${escapeHtml(meta.label)}</span>`;
        }
        function renderPowerDetailLogs(cabId, logs) {
            const logList = document.getElementById(`logs_${cabId}`);
            if (!logList) return;
            const items = Array.isArray(logs) ? logs : [];
            if (!items.length) {
                logList.innerHTML = '<div style="color:var(--text-sub); padding:10px 0;">暂无操作日志</div>';
                return;
            }
            const html = items.map(log => {
                const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
                const message = escapeHtml(normalizeLogOperationText(log));
                return `<div class="log-item"><span class="time">[${timeText}]</span>${renderPowerLogSourceTag(log)}<span class="msg">${message}</span></div>`;
            }).join('');
            if (logList.innerHTML !== html) logList.innerHTML = html;
        }
        function renderDashboardPowerHistory(historyRows, status) {
            const rows = Array.isArray(historyRows) ? historyRows.slice(-7) : [];
            if (!rows.length) {
                const todayText = Number(status?.daily_energy || 0) > 0 ? `今日累计 ${formatPowerValue(status.daily_energy, 1, ' kWh')}` : '历史数据仍在累计';
                return `<div class="dashboard-power-history">
                    <div class="dashboard-power-history-head">
                        <div class="dashboard-power-history-title">近 7 天用电</div>
                        <div class="dashboard-power-history-meta">${todayText}</div>
                    </div>
                    <div class="dashboard-power-history-empty">当前只拿到最近实时累计，后续会随着采集继续补齐历史曲线。</div>
                </div>`;
            }
            const peak = Math.max(...rows.map(item => Number(item.consume || 0)), 0);
            const total = rows.reduce((sum, item) => sum + Number(item.consume || 0), 0);
            const bars = rows.map(item => {
                const value = Number(item.consume || 0);
                const percent = peak > 0 ? Math.max(14, Math.round((value / peak) * 100)) : (item.is_today ? 18 : 10);
                return `<div class="dashboard-power-history-bar-wrap">
                    <div class="dashboard-power-history-bar ${item.is_today ? 'today' : ''}" style="height:${percent}%"></div>
                    <span>${String(item.date || '').slice(8) || '--'}</span>
                </div>`;
            }).join('');
            return `<div class="dashboard-power-history">
                <div class="dashboard-power-history-head">
                    <div class="dashboard-power-history-title">近 7 天用电</div>
                    <div class="dashboard-power-history-meta">累计 ${formatPowerValue(total, 1, ' kWh')} / 峰值 ${formatPowerValue(peak, 1, ' kWh')}</div>
                </div>
                <div class="dashboard-power-history-bars">${bars}</div>
            </div>`;
        }
        function renderDashboardPowerCards() {
            const container = document.getElementById('dashboard-power-grid');
            if (!container) return;
            const cabinets = Array.isArray(configData.cabinets) ? configData.cabinets : [];
            if (!cabinets.length) {
                container.innerHTML = '<div style="color:var(--text-sub); text-align:center; padding:20px;">未配置强电柜</div>';
                return;
            }
            container.innerHTML = cabinets.map((cab, cabId) => {
                const status = powerStatusCache[cabId] || {};
                const online = !!status.comm_status;
                const visibleChannels = (Array.isArray(cab.channels_config) ? cab.channels_config : [])
                    .filter(item => item && item.visible !== false)
                    .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999))
                    .slice(0, 6);
                    const channelsHtml = visibleChannels.map(ch => {
                        const chNum = Number(ch.channel);
                        const state = getPowerChannelStatus(cabId, chNum);
                        const isPending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]);
                        const cls = isPending ? 'ch-off' : (state === null || state === undefined ? 'ch-err' : (state ? 'ch-on' : 'ch-off'));
                        const stateText = isPending ? '执行中' : (state === null || state === undefined ? '离线' : (state ? '已合闸' : '已断开'));
                        return `<button class="power-mini-channel ${cls}${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                        ${renderPowerChannelLabelHtml(cab, chNum)}
                        <span class="state">${escapeHtml(stateText)}</span>
                    </button>`;
                }).join('');
                const logs = (powerLogCache[cabId] || []).slice(0, 2);
                const logsHtml = logs.length ? logs.map(log => {
                    const timeText = log.time ? new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
                    return `<div class="dashboard-power-log-item"><span class="dashboard-power-log-time">[${timeText}]</span>${renderPowerLogSourceTag(log, 'dashboard-power-log-source')}<span class="dashboard-power-log-text">${escapeHtml(normalizeLogOperationText(log))}</span></div>`;
                }).join('') : '<div class="dashboard-power-log-empty">暂无最近操作</div>';
                const workMode = sanitizeReadableText(status.work_mode, '未知模式');
                const tempValue = Number(status.cabinet_temp);
                const humiValue = Number(status.cabinet_humidity);
                const stopMsg = escapeHtml(String(cab?.ui_text?.confirm_stop || '确定要停止该电柜所有通道吗？'));
                return `<div class="dashboard-power-card ${online ? '' : 'offline'}" id="dash-power-card-${cabId}">
                    <div class="dashboard-power-head">
                        <div>
                            <div class="dashboard-power-title">${escapeHtml(getCabinetDisplayName(cab, cabId))}</div>
                            <div class="dashboard-power-subtitle">${escapeHtml(getCabinetSubtitle(cab))}</div>
                        </div>
                        <div class="dashboard-power-chip-row">
                            <span class="ups-chip ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span>
                            <span class="ups-chip">${escapeHtml(workMode)}</span>
                        </div>
                    </div>
                    <div class="dashboard-power-kpis">
                        <div class="dashboard-power-kpi">
                            <div class="label">实时功率</div>
                            <div class="value warn">${formatPowerValue(status.realtime_power, 2, ' kW')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">今日用电</div>
                            <div class="value ok">${formatPowerValue(status.daily_energy, 1, ' kWh')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">本月用电</div>
                            <div class="value">${formatPowerValue(status.monthly_energy, 1, ' kWh')}</div>
                        </div>
                        <div class="dashboard-power-kpi">
                            <div class="label">温湿度</div>
                            <div class="value">${Number.isFinite(tempValue) ? tempValue.toFixed(1) + ' C' : '--'} / ${Number.isFinite(humiValue) ? humiValue.toFixed(1) + '%' : '--'}</div>
                        </div>
                    </div>
                    ${renderDashboardPowerHistory(powerHistoryCache[cabId], status)}
                    <div class="dashboard-power-channels">${channelsHtml || '<div class="dashboard-power-log-empty" style="grid-column:1/-1;">暂无可控通道</div>'}</div>
                    <div class="dashboard-power-actions">
                        <button class="dashboard-mini-btn success${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStart(${cabId})">一键启动</button>
                        <button class="dashboard-mini-btn danger${getPermissionDisabledClass('power.control')}" ${getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="doPowerStop(${cabId}, '${stopMsg}')">一键停止</button>
                        <button class="dashboard-mini-btn secondary" type="button" onclick="switchTab('power', '强电控制')">详情</button>
                    </div>
                    <div class="dashboard-power-log">
                        <div class="dashboard-power-log-title">最近操作</div>
                        <div class="dashboard-power-log-list">${logsHtml}</div>
                    </div>
                </div>`;
            }).join('');
        }
        function formatHomeNumber(value, digits = 0, suffix = '') {
            const num = Number(value);
            if (!Number.isFinite(num)) return '--';
            return `${num.toFixed(digits)}${suffix}`;
        }
        function renderHomeCompactMetric(label, value, tone = '') {
            return `<div class="home-compact-metric">
                <div class="label">${escapeHtml(label)}</div>
                <div class="value ${escapeHtml(tone)}">${escapeHtml(value)}</div>
            </div>`;
        }
        function getUpsCompactAlarmMeta(status = {}) {
            const faultLabels = Array.isArray(status.fault_labels) ? status.fault_labels.filter(Boolean) : [];
            const warningLabels = Array.isArray(status.warning_labels) ? status.warning_labels.filter(Boolean) : [];
            const rawAlerts = Array.isArray(status.alerts) ? status.alerts.filter(Boolean) : [];
            const benignAlerts = rawAlerts.filter(item => /蜂鸣|buzzer|beeper|beep/i.test(String(item || '')));
            const riskAlerts = rawAlerts.filter(item => !benignAlerts.includes(item));
            const riskItems = [
                ...faultLabels,
                ...warningLabels,
                ...riskAlerts,
                status.is_fault ? 'UPS 故障' : '',
                status.mains_abnormal ? '市电异常' : '',
                status.is_battery_low ? '电池偏低' : '',
                status.is_bypass ? '旁路供电' : '',
                status.last_error || status.error || '',
            ].filter(Boolean);
            if (riskItems.length) {
                return { hasRisk: true, cls: 'warning', label: '告警', title: riskItems.slice(0, 4).join('、') };
            }
            if (benignAlerts.length) {
                return { hasRisk: false, cls: '', label: '提示', title: benignAlerts.slice(0, 4).join('、') };
            }
            return { hasRisk: false, cls: 'online', label: '无告警', title: '当前无故障/告警' };
        }
        function renderDashboardPowerCompact() {
            const container = document.getElementById('dashboard-power-compact-grid');
            if (!container) return;
            const cabinets = Array.isArray(configData.cabinets) ? configData.cabinets : [];
            if (!cabinets.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置强电柜</div>';
                return;
            }
            container.classList.add('home-status-list');
            container.innerHTML = cabinets.map((cab, cabId) => {
                const status = powerStatusCache[cabId] || {};
                const online = !!(status.comm_status || status.online);
                const channels = Array.isArray(status.channels_1_4) ? status.channels_1_4.slice(0, Number(cab.channel_count || 8)) : [];
                const configuredChannels = Array.isArray(cab.channels_config) ? cab.channels_config.filter(ch => ch && ch.visible !== false).length : 0;
                const totalChannels = Number(status.channel_count || cab.channel_count || configuredChannels || channels.length || 0);
                const onCount = Number.isFinite(Number(status.channel_on_count))
                    ? Number(status.channel_on_count)
                    : channels.filter(st => st === true || st === 1 || st === '1').length;
                const powerValue = status.effective_realtime_power ?? status.stable_realtime_power ?? status.realtime_power;
                const temp = Number(status.cabinet_temp);
                const humi = Number(status.cabinet_humidity);
                const tempText = Number.isFinite(temp) || Number.isFinite(humi)
                    ? `${Number.isFinite(temp) ? temp.toFixed(1) + '°C' : '--'} / ${Number.isFinite(humi) ? humi.toFixed(0) + '%' : '--'}`
                    : '--';
                const modeText = sanitizeReadableText(status.work_mode, '模式未知');
                const updatedText = formatTimeShort(status.updated_at || status._last_success_at || status.last_success_at || status.last_checked_at);
                const configuredList = Array.isArray(cab.channels_config) ? cab.channels_config : [];
                const visibleChannels = configuredList
                    .filter(ch => ch && ch.visible !== false)
                    .sort((a, b) => Number(a.sort || 999) - Number(b.sort || 999));
                const fallbackChannels = Array.from({ length: Math.min(Number(cab.channel_count || totalChannels || channels.length || 8), 8) }, (_, idx) => ({ channel: idx + 1 }));
                const channelSource = (visibleChannels.length ? visibleChannels : fallbackChannels).slice(0, 8);
                const channelHtml = channelSource.map(ch => {
                    const chNum = Number(ch.channel);
                    const state = getPowerChannelStatus(cabId, chNum);
                    const pending = !!(pwrPending[cabId] && pwrPending[cabId][chNum]);
                    const unknown = state === null || state === undefined;
                    const isOn = state === true || state === 1 || state === '1';
                    const cls = pending ? 'pending' : (unknown ? 'unknown' : (isOn ? 'on' : 'off'));
                    const stateText = pending ? '执行中' : (unknown ? '--' : (isOn ? '开' : '关'));
                    const disabled = unknown ? 'disabled title="状态未知，暂不可操作"' : '';
                    return `<button type="button" class="home-power-channel ${cls}${getPermissionDisabledClass('power.control')}" ${disabled || getPermissionDisabledAttrs('power.control', '当前账号无强电控制权限')} onclick="togglePower(${cabId}, ${chNum})">
                        <span class="led"></span>${renderPowerChannelLabelHtml(cab, chNum, { compact: true })}<span class="state">${escapeHtml(stateText)}</span>
                    </button>`;
                }).join('');
                return `<div class="home-status-row home-power-row ${online ? '' : 'offline'}">
                    <div class="home-row-main">
                        <div class="home-row-title-line home-power-title-line"><strong class="home-row-name">${escapeHtml(getCabinetDisplayName(cab, cabId))}</strong><span class="home-mini-pill ${online ? 'online' : 'error'}">${online ? '在线' : '离线'}</span></div>
                        <span>${escapeHtml(modeText)} · ${onCount}/${totalChannels || '--'} 路 · ${escapeHtml(tempText)}</span>
                    </div>
                    <div class="home-row-side home-power-side ${online ? 'ok' : 'bad'}">${formatHomeNumber(powerValue, 2, ' kW')}<br>${formatHomeNumber(status.daily_energy, 1, ' kWh')}</div>
                    ${channelHtml ? `<div class="home-power-channel-strip">${channelHtml}</div>` : ''}
                </div>`;
            }).join('');
        }
        function renderDashboardUpsCompact() {
            const container = document.getElementById('dashboard-ups-compact-grid');
            if (!container) return;
            const devices = Array.isArray(upsConfigs) ? upsConfigs.filter(cfg => cfg.visible !== false) : [];
            if (!devices.length) {
                container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:14px;">未配置 UPS</div>';
                return;
            }
            container.classList.add('home-status-list');
            container.innerHTML = devices.map(cfg => {
                const status = upsStatusCache[cfg.id] || {};
                const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
                const online = statusMeta.isOnlineLike;
                const alarmMeta = getUpsCompactAlarmMeta(status);
                const inputText = status.input_voltage !== null && status.input_voltage !== undefined ? `${status.input_voltage}V` : '--';
                const outputText = status.output_voltage !== null && status.output_voltage !== undefined ? `${status.output_voltage}V` : '--';
                const modeText = status.supply_state || status.system_mode || (status.is_bypass ? '旁路' : '市电');
                return `<div class="home-status-row home-ups-row ${online ? (alarmMeta.hasRisk ? 'warning' : '') : 'offline'}">
                    <div class="home-row-main">
                        <div class="home-row-title-line"><strong>${escapeHtml(cfg.name || cfg.id)}</strong><span class="home-mini-pill ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span><span class="home-mini-pill ${alarmMeta.cls}" title="${escapeHtml(alarmMeta.title)}">${escapeHtml(alarmMeta.label)}</span></div>
                        <span>${escapeHtml(modeText)} · ${escapeHtml(inputText)} / ${escapeHtml(outputText)}</span>
                    </div>
                    <div class="home-row-side home-ups-metrics ${alarmMeta.hasRisk ? 'warn' : (online ? 'ok' : 'bad')}">${status.battery_capacity_percent ?? '--'}% 电池<br>${status.load_percent ?? '--'}% 负载</div>
                </div>`;
            }).join('');
        }
        function refreshPowerSupplement(cabId, force = false) {
            const now = Date.now();
            const activeView = getActiveViewId();
            const minInterval = activeView === 'power' ? 12000 : 30000;
            if (!force && powerSupplementFetchAt[cabId] && (now - powerSupplementFetchAt[cabId] < minInterval)) return;
            powerSupplementFetchAt[cabId] = now;
            fetch(`/api/logs?cab=${cabId}`)
                .then(r => r.json())
                .then(logs => {
                    powerLogCache[cabId] = Array.isArray(logs) ? logs : [];
                    renderPowerDetailLogs(cabId, powerLogCache[cabId]);
                    renderDashboardPowerCards();
                    renderDashboardPowerCompact();
                })
                .catch(err => console.error('强电日志更新失败', cabId, err));
            fetch(`/api/7days_energy?cab=${cabId}`)
                .then(r => r.json())
                .then(data => {
                    powerHistoryCache[cabId] = Array.isArray(data) ? data : [];
                    renderPowerEnergyChart(cabId, powerHistoryCache[cabId]);
                    renderDashboardPowerCards();
                    renderDashboardPowerCompact();
                })
                .catch(err => console.error('强电图表更新失败', cabId, err));
        }
        function getMeterModeText(mode) {
            const textMap = { type1: '电表类型 1', type4: '电表类型 4' };
            return textMap[String(mode || '').toLowerCase()] || (mode || '未定义');
        }
        function renderMeterTypeChips(typeCounts) {
            const wrap = document.getElementById('meter-type-chip-row');
            if (!wrap) return;
            const entries = Object.entries(typeCounts || {});
            if (!entries.length) {
                wrap.innerHTML = '<span class="meter-type-chip">暂无已接入电表型号</span>';
                return;
            }
            wrap.innerHTML = entries.map(([key, count]) => `<span class="meter-type-chip">${escapeHtml(getMeterModeText(key))} / ${escapeHtml(String(count))} 台</span>`).join('');
        }
        function meterValueOrDash(value, digits = 1, unit = '', zeroAsDash = false) {
            const num = Number(value);
            if (!Number.isFinite(num)) return '--';
            if (zeroAsDash && Math.abs(num) < 0.0001) return '--';
            return `${num.toFixed(digits)}${unit ? ' ' + unit : ''}`;
        }
        function normalizeMeterCardOrder(meters) {
            const list = Array.isArray(meters) ? [...meters] : [];
            return list.sort((left, right) => {
                const leftRef = left && left.is_reference_meter ? 1 : 0;
                const rightRef = right && right.is_reference_meter ? 1 : 0;
                if (leftRef !== rightRef) return rightRef - leftRef;
                const leftSort = Number(left?.sort_order ?? left?.meter_sort_order ?? 999);
                const rightSort = Number(right?.sort_order ?? right?.meter_sort_order ?? 999);
                if (leftSort !== rightSort) return leftSort - rightSort;
                const leftName = String(left?.display_name || left?.cabinet_name || left?.id || '');
                const rightName = String(right?.display_name || right?.cabinet_name || right?.id || '');
                return leftName.localeCompare(rightName, 'zh-CN');
            });
        }
        function renderMeterCard(meter) {
            const online = !!meter.online;
            const degraded = !!meter._degraded || String(meter.error || '').includes('fallback:');
            const isReferenceMeter = !!meter.is_reference_meter;
            const updatedText = meter.updated_at ? String(meter.updated_at).replace('T', ' ').slice(0, 19) : '--';
            const errorText = String(meter.error || '').trim();
            const dataSourceText = meter.source_label || meter.source || (degraded ? '降级采集' : (online ? '远程采集' : '等待连接'));
            const titleText = meter.display_name || meter.cabinet_name || meter.id;
            const subtitleText = isReferenceMeter
                ? '参考主表 · 不参与统计'
                : `${meter.area_name || '电表'} · ${dataSourceText}`;
            const extraItems = [
                { label: 'AB 线压', value: meterValueOrDash(meter.voltage_ab, 1, 'V', true) },
                { label: 'BC 线压', value: meterValueOrDash(meter.voltage_bc, 1, 'V', true) },
                { label: 'CA 线压', value: meterValueOrDash(meter.voltage_ca, 1, 'V', true) },
                { label: '功率因数', value: meterValueOrDash(meter.power_factor, 3, '', true) },
                { label: '频率', value: meterValueOrDash(meter.frequency, 2, 'Hz', true) },
                { label: '视在功率', value: meterValueOrDash(meter.apparent_power, 2, 'kVA', true) },
                { label: '无功功率', value: meterValueOrDash(meter.reactive_power, 2, 'kvar', true) }
            ].filter(item => item.value !== '--');
            const extraHtml = extraItems.length
                ? `<div class="meter-extra-grid">${extraItems.map(item => `<div class="meter-extra-card"><div class="label">${item.label}</div><div class="value">${item.value}</div></div>`).join('')}</div>`
                : '';
            const statusText = online ? (degraded ? '告警' : '在线') : '离线';
            const detailText = online ? escapeHtml(errorText || '远程采集正常') : escapeHtml(errorText || '设备离线或暂无返回');
            return `<div class="meter-card ${online ? '' : 'offline'} ${isReferenceMeter ? 'reference-meter' : ''}">
                <div class="meter-card-head">
                    <div>
                        <div class="card-head-kicker">${isReferenceMeter ? 'Reference Meter' : 'Meter Overview'}</div>
                        <div class="meter-card-title">${escapeHtml(titleText)}</div>
                        <div class="meter-card-subtitle">${escapeHtml(subtitleText)}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="meter-status-chip ${online ? (degraded ? 'degraded' : 'online') : 'offline'}">${statusText}</span>
                        ${isReferenceMeter ? `<span class="meter-status-chip">对照专用</span>` : ''}
                        ${meter.mode ? `<span class="meter-status-chip">${escapeHtml(getMeterModeText(meter.mode))}</span>` : ''}
                    </div>
                </div>
                <div class="meter-phase-grid">
                    <div class="meter-phase-card"><div class="phase">A 相</div><div class="main">${Number(meter.voltage_a || 0).toFixed(1)} V</div><div class="sub">${Number(meter.current_a || 0).toFixed(1)} A</div></div>
                    <div class="meter-phase-card"><div class="phase">B 相</div><div class="main">${Number(meter.voltage_b || 0).toFixed(1)} V</div><div class="sub">${Number(meter.current_b || 0).toFixed(1)} A</div></div>
                    <div class="meter-phase-card"><div class="phase">C 相</div><div class="main">${Number(meter.voltage_c || 0).toFixed(1)} V</div><div class="sub">${Number(meter.current_c || 0).toFixed(1)} A</div></div>
                </div>
                <div class="meter-kpi-grid">
                    <div class="meter-kpi-card"><div class="label">实时功率</div><div class="value" style="color:var(--warning);">${Number((meter.effective_realtime_power ?? meter.stable_realtime_power ?? meter.realtime_power) || 0).toFixed(2)} kW</div></div>
                    <div class="meter-kpi-card"><div class="label">累计电能</div><div class="value">${Number(meter.effective_electric_energy || 0).toFixed(1)} kWh</div></div>
                    <div class="meter-kpi-card"><div class="label">今日电量</div><div class="value" style="color:var(--success);">${Number(meter.daily_energy || 0).toFixed(1)} kWh</div></div>
                    <div class="meter-kpi-card"><div class="label">本月电量</div><div class="value" style="color:var(--brand-blue);">${Number(meter.monthly_energy || 0).toFixed(1)} kWh</div></div>
                </div>
                ${extraHtml}
                <div class="meter-foot">
                    <span>更新时间 ${escapeHtml(updatedText)}</span>
                    <span>${detailText}</span>
                </div>
            </div>`;
        }
        function renderMeterCard(meter) {
            const online = !!meter.online;
            const degraded = !!meter._degraded || String(meter.error || '').includes('fallback:');
            const isReferenceMeter = !!meter.is_reference_meter;
            const updatedText = meter.updated_at ? String(meter.updated_at).replace('T', ' ').slice(0, 19) : '--';
            const errorText = String(meter.error || '').trim();
            const dataSourceText = meter.source_label || meter.source || (degraded ? '降级采集' : (online ? '远程采集' : '等待连接'));
            const titleText = meter.display_name || meter.cabinet_name || meter.id;
            const subtitleText = isReferenceMeter ? '参考主表 · 不参与统计' : `${meter.area_name || '电表'} · ${dataSourceText}`;
            const statusText = online ? (degraded ? '告警' : '在线') : '离线';
            const detailText = online ? escapeHtml(errorText || '远程采集正常') : escapeHtml(errorText || '设备离线或暂无返回');
            const powerValue = Number((meter.effective_realtime_power ?? meter.stable_realtime_power ?? meter.realtime_power) || 0).toFixed(2);
            const phaseValues = [
                { label: 'A', voltage: Number(meter.voltage_a || 0), current: Number(meter.current_a || 0) },
                { label: 'B', voltage: Number(meter.voltage_b || 0), current: Number(meter.current_b || 0) },
                { label: 'C', voltage: Number(meter.voltage_c || 0), current: Number(meter.current_c || 0) }
            ];
            const voltageAlerts = phaseValues
                .filter(item => Number.isFinite(item.voltage) && item.voltage > 0 && (item.voltage < 180 || item.voltage > 250))
                .map(item => `${item.label} ${item.voltage.toFixed(1)}V`);
            const extraItems = [
                voltageAlerts.length ? { label: 'VOLT', value: voltageAlerts.join(' / ') } : null,
                { label: 'PF', value: meterValueOrDash(meter.power_factor, 3, '', true) },
                { label: 'kVA', value: meterValueOrDash(meter.apparent_power, 2, 'kVA', true) }
            ].filter(item => item && item.value !== '--');
            const extraHtml = extraItems.length
                ? `<div class="meter-extra-grid">${extraItems.map(item => `<div class="meter-extra-card"><div class="label">${escapeHtml(item.label)}</div><div class="value">${escapeHtml(item.value)}</div></div>`).join('')}</div>`
                : '';
            return `<div class="meter-card meter-card-dense ${online ? '' : 'offline'} ${isReferenceMeter ? 'reference-meter' : ''}">
                <div class="meter-card-head">
                    <div class="meter-title-block">
                        <div class="meter-card-title">${escapeHtml(titleText)}</div>
                        <div class="meter-card-subtitle">${escapeHtml(subtitleText)}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="meter-status-chip ${online ? (degraded ? 'degraded' : 'online') : 'offline'}">${statusText}</span>
                        ${isReferenceMeter ? `<span class="meter-status-chip">对照</span>` : ''}
                        ${meter.mode ? `<span class="meter-status-chip">${escapeHtml(getMeterModeText(meter.mode))}</span>` : ''}
                    </div>
                </div>
                <div class="meter-dense-main">
                    <div class="meter-dense-power">
                        <span>实时功率</span>
                        <strong>${powerValue}<em>kW</em></strong>
                    </div>
                    <div class="meter-kpi-grid">
                        <div class="meter-kpi-card"><div class="label">累计</div><div class="value">${Number(meter.effective_electric_energy || 0).toFixed(1)} kWh</div></div>
                        <div class="meter-kpi-card"><div class="label">今日</div><div class="value" style="color:var(--success);">${Number(meter.daily_energy || 0).toFixed(1)} kWh</div></div>
                        <div class="meter-kpi-card"><div class="label">本月</div><div class="value" style="color:var(--brand-blue);">${Number(meter.monthly_energy || 0).toFixed(1)} kWh</div></div>
                    </div>
                </div>
                ${extraHtml}
                <div class="meter-foot">
                    <span>${escapeHtml(updatedText)}</span>
                    <span>${detailText}</span>
                </div>
            </div>`;
        }
        function formatReferenceMeta(metric, unit = '') {
            if (!metric || metric.available === false) {
                const reason = metric?.reason || '';
                if (reason === 'reference_monthly_history_incomplete') {
                    const recordDays = Number(metric?.record_days || 0);
                    const expectedDays = Number(metric?.expected_days || 0);
                    const suffix = expectedDays > 0 ? `（${recordDays}/${expectedDays} 天）` : '';
                    return `参考总表 <strong>月度历史不足，暂不比较${suffix}</strong>`;
                }
                if (reason === 'power_comparison_disabled') return '功率按卡片合计展示，参考总表仅作旁路监看';
                return '参考总表 <strong>未接入</strong>';
            }
            const referenceValue = Number(metric.reference || 0);
            const deltaValue = Number(metric.delta || 0);
            const referenceText = Number.isFinite(referenceValue) ? referenceValue.toFixed(unit === '%' ? 2 : 1) : '--';
            let deltaText = '--';
            if (Number.isFinite(deltaValue)) {
                const deltaAbsText = Math.abs(deltaValue).toFixed(unit === '%' ? 2 : 1);
                if (deltaValue > 0) deltaText = `多 ${deltaAbsText}`;
                else if (deltaValue < 0) deltaText = `少 ${deltaAbsText}`;
                else deltaText = `持平 ${deltaAbsText}`;
            }
            return `参考总表 <strong>${referenceText}${unit}</strong> · 差值 <strong>${deltaText}${unit}</strong>`;
        }
        function formatPowerSummaryMeta(summary) {
            const referencePower = Number(
                summary.reference_total_realtime_power
                ?? summary.reference_meter?.realtime_power
                ?? 0
            );
            const cardTotalPower = Number(
                summary.card_total_realtime_power
                ?? summary.stable_total_realtime_power
                ?? summary.submeter_estimated_total_realtime_power
                ?? summary.estimated_total_realtime_power
                ?? summary.submeter_total_realtime_power
                ?? summary.total_realtime_power
                ?? 0
            );
            if (Number.isFinite(referencePower) && referencePower > 0) {
                if (Number.isFinite(cardTotalPower) && cardTotalPower >= 0) {
                    return `参考总表 <strong>${referencePower.toFixed(2)} kW</strong> · 卡片合计 <strong>${cardTotalPower.toFixed(2)} kW</strong>`;
                }
                return `参考总表 <strong>${referencePower.toFixed(2)} kW</strong>`;
            }
            if (Number.isFinite(cardTotalPower) && cardTotalPower >= 0) {
                return `参考总表 <strong>未接入</strong> · 卡片合计 <strong>${cardTotalPower.toFixed(2)} kW</strong>`;
            }
            return '参考总表 <strong>未接入</strong>';
        }
        function renderMeterTrendSelectors(payload) {
            const targetSelect = document.getElementById('meter-trend-target');
            const periodSelect = document.getElementById('meter-trend-period');
            const targets = Array.isArray(payload.trend_targets) ? payload.trend_targets : [];
            if (targetSelect) {
                targetSelect.innerHTML = targets.map(item => `<option value="${escapeHtml(item.source_key || 'total')}" ${String(payload.trend_target || 'total') === String(item.source_key || 'total') ? 'selected' : ''}>${escapeHtml(item.label || item.source_key || '未命名')}</option>`).join('');
            }
            if (periodSelect) {
                periodSelect.value = payload.trend_period || 'day';
            }
            const targetLabel = document.getElementById('meter-trend-target-label');
            const periodLabel = document.getElementById('meter-trend-period-label');
            const targetBadge = document.getElementById('meter-summary-badge-target');
            if (targetLabel) targetLabel.innerText = payload.trend_target_label || '全部统计电表';
            if (targetBadge) targetBadge.innerText = payload.trend_target_label || '全部统计电表';
            if (periodLabel) periodLabel.innerText = payload.trend_period === 'week' ? '按周' : (payload.trend_period === 'month' ? '按月' : '按日');
        }
        function resolveMeterSourceMeta(payload) {
            const source = String((payload || {}).data_source || '').toLowerCase();
            const remoteUrl = String((payload || {}).remote_service_url || '').trim();
            const remoteError = String((payload || {}).remote_error || '').trim();
            if (source === 'remote_meter_service') {
                return {
                    text: 'NAS 远程',
                    color: '#86efac',
                    title: remoteUrl ? `当前正在读取独立电表服务：${remoteUrl}` : '当前正在读取独立电表服务'
                };
            }
            if (source === 'remote_meter_service_cache') {
                return {
                    text: 'NAS 缓存',
                    color: '#fcd34d',
                    title: remoteError
                        ? `NAS 电表服务短时异常，当前显示最近一次成功缓存：${remoteError}`
                        : 'NAS 电表服务短时异常，当前显示最近一次成功缓存'
                };
            }
            if (source === 'remote_meter_service_error' || source === 'remote_meter_service_required') {
                return {
                    text: 'NAS 异常',
                    color: '#fcd34d',
                    title: remoteError ? `NAS 电表服务异常：${remoteError}` : 'NAS 电表服务不可用'
                };
            }
            if (source === 'meter_service') {
                return {
                    text: '独立服务',
                    color: '#93c5fd',
                    title: '当前页面数据来自独立电表服务'
                };
            }
            return {
                text: 'NAS 远程',
                color: '#86efac',
                title: remoteUrl ? `当前正在读取独立电表服务：${remoteUrl}` : '当前正在读取独立电表服务'
            };
        }
        function renderMeterTrendChart(rows) {
            const dom = document.getElementById('meterTrendChart');
            if (!dom || typeof echarts === 'undefined') return;
            if (!myCharts.meterTrend) {
                myCharts.meterTrend = echarts.init(dom);
            }
            const safeRows = Array.isArray(rows) ? rows : [];
            const rowMap = new Map(safeRows.map(item => [String(item.period || item.date || ''), item]));
            let chartRows = safeRows;
            if (meterTrendPeriod === 'day') {
                const now = new Date();
                now.setHours(0, 0, 0, 0);
                chartRows = Array.from({ length: 35 }, (_, idx) => {
                    const d = new Date(now);
                    d.setDate(now.getDate() - 34 + idx);
                    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
                    return rowMap.get(key) || { period: key, consume: 0, is_today: idx === 34 };
                });
            }
            const dates = chartRows.map(item => String(item.period || item.date || '')).filter(Boolean);
            const values = chartRows.map(item => {
                const value = Number(item.consume || 0);
                return Number.isFinite(value) ? Number(value.toFixed(2)) : 0;
            });
            const maxValue = Math.max(0, ...values);
            const axisKey = `${meterTrendTarget}:${meterTrendPeriod}`;
            const nextYMax = Math.max(10, Math.ceil(maxValue * 1.18 / 50) * 50);
            if (axisKey !== meterTrendAxisKey) {
                meterTrendAxisKey = axisKey;
                meterTrendYAxisMax = nextYMax;
            } else {
                meterTrendYAxisMax = Math.max(meterTrendYAxisMax || 0, nextYMax);
            }
            const yMax = meterTrendYAxisMax;
            const todayKey = (() => {
                const d = new Date();
                return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
            })();
            const todayIndex = chartRows.findIndex(item => item && (item.is_today || String(item.period || item.date || '') === todayKey));
            const barData = values.map((value, index) => ({
                value,
                itemStyle: {
                    color: index === todayIndex ? '#f59e0b' : '#3b82f6',
                    borderRadius: [5, 5, 0, 0]
                },
                label: { color: index === todayIndex ? '#fde68a' : '#bfdbfe' }
            }));
            const optionSignature = JSON.stringify({ dates, values, todayIndex, yMax, target: meterTrendTarget, period: meterTrendPeriod });
            if (optionSignature === meterTrendOptionSignature) {
                myCharts.meterTrend.resize();
                return;
            }
            meterTrendOptionSignature = optionSignature;
            myCharts.meterTrend.setOption({
                animation: false,
                animationDuration: 0,
                animationDurationUpdate: 0,
                stateAnimation: { duration: 0 },
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'line', animation: false, lineStyle: { color: 'rgba(226,232,240,0.38)', width: 1 } },
                    valueFormatter: value => `${Number(value || 0).toFixed(2)} kWh`
                },
                grid: { left: 18, right: 18, top: 34, bottom: 18, containLabel: true },
                xAxis: {
                    type: 'category',
                    data: dates,
                    boundaryGap: true,
                    axisLine: { lineStyle: { color: '#475569' } },
                    axisTick: { show: false },
                    axisLabel: { color: '#94a3b8', hideOverlap: true }
                },
                yAxis: {
                    type: 'value',
                    name: 'kWh',
                    min: 0,
                    max: yMax,
                    interval: yMax <= 300 ? 50 : 100,
                    nameTextStyle: { color: '#94a3b8' },
                    splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    axisLabel: { color: '#94a3b8' }
                },
                series: [
                    {
                        name: '电量',
                        type: 'bar',
                        barMaxWidth: 24,
                        data: barData,
                        label: {
                            show: true,
                            position: 'top',
                            distance: 3,
                            formatter: params => Number(params.value || 0).toFixed(0),
                            fontSize: 9,
                            fontWeight: 800
                        },
                        emphasis: { disabled: true }
                    },
                    {
                        name: '连接线',
                        type: 'line',
                        data: values,
                        symbol: 'circle',
                        symbolSize: 5,
                        smooth: false,
                        z: 3,
                        lineStyle: { color: '#93c5fd', width: 2, opacity: 0.86 },
                        itemStyle: { color: '#e0f2fe', borderColor: '#1d4ed8', borderWidth: 1 },
                        label: { show: false },
                        emphasis: { disabled: true }
                    }
                ]
            }, true);
            myCharts.meterTrend.resize();
        }
        function renderDashboardEnergyTrend(rows, summary = {}) {
            const dom = document.getElementById('dashboardEnergyTrendChart');
            if (!dom || typeof echarts === 'undefined') return;
            const safeRows = Array.isArray(rows) ? rows : [];
            const labels = safeRows.map(item => String(item.period || item.date || '').slice(-5)).filter(Boolean);
            const values = safeRows.map(item => Number(item.consume || 0));
            const total = Number(summary.total_daily_energy ?? (meterCenterCache.dashboard_summary || {}).daily_energy ?? 0);
            const last = values.length ? values[values.length - 1] : total;
            const prev = values.length > 1 ? values[values.length - 2] : 0;
            const compare = prev > 0 ? `${(((last - prev) / prev) * 100).toFixed(1)}%` : '--%';
            setTextIfExists('dashboard-energy-total', `${total.toFixed(1)} kWh`);
            setTextIfExists('dashboard-energy-compare', compare);
            if (!myCharts.dashboardEnergyTrend) {
                myCharts.dashboardEnergyTrend = echarts.init(dom);
            }
            myCharts.dashboardEnergyTrend.setOption({
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'axis',
                    formatter: params => {
                        const item = Array.isArray(params) ? params[0] : null;
                        if (!item) return '';
                        return `${escapeHtml(String(item.axisValue || '--'))}<br/>${Number(item.data || 0).toFixed(2)} kWh`;
                    }
                },
                grid: { left: 34, right: 14, top: 18, bottom: 24 },
                xAxis: {
                    type: 'category',
                    data: labels,
                    boundaryGap: false,
                    axisLine: { lineStyle: { color: 'rgba(96,165,250,.28)' } },
                    axisTick: { show: false },
                    axisLabel: { color: '#8fb4de', fontSize: 10 }
                },
                yAxis: {
                    type: 'value',
                    axisLine: { show: false },
                    axisTick: { show: false },
                    axisLabel: { color: '#8fb4de', fontSize: 10 },
                    splitLine: { lineStyle: { color: 'rgba(96,165,250,.10)' } }
                },
                series: [{
                    type: 'line',
                    smooth: true,
                    symbol: 'none',
                    data: values,
                    lineStyle: { width: 2, color: '#2f8cff' },
                    areaStyle: {
                        color: {
                            type: 'linear',
                            x: 0, y: 0, x2: 0, y2: 1,
                            colorStops: [
                                { offset: 0, color: 'rgba(47,140,255,.42)' },
                                { offset: 1, color: 'rgba(47,140,255,.02)' }
                            ]
                        }
                    }
                }]
            }, true);
            myCharts.dashboardEnergyTrend.resize();
        }
        function updateMeterCenter() {
            fetch(`/api/meters?target=${encodeURIComponent(meterTrendTarget)}&period=${encodeURIComponent(meterTrendPeriod)}&days=35`)
                .then(r => r.json())
                .then(data => {
                    meterCenterCache = data || { summary: {}, meters: [], trend: [] };
                    const summary = meterCenterCache.summary || {};
                    const meters = Array.isArray(meterCenterCache.meters) ? meterCenterCache.meters : [];
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
        }
        function changeMeterTrendTarget(target) {
            meterTrendTarget = target || 'total';
            updateMeterCenter();
        }
        function changeMeterTrendPeriod(period) {
            meterTrendPeriod = period || 'day';
            updateMeterCenter();
        }
        function renderUpsCard(cfg, status) {
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const modeText = status.system_mode || '--';
            const supplyStateText = status.supply_state || (status.is_bypass ? '旁路供电' : (status.mains_abnormal ? '电池供电' : '市电供电'));
            const fmt = (value, digits = 1, suffix = '') => {
                const num = Number(value);
                return Number.isFinite(num) ? `${num.toFixed(digits)}${suffix}` : '--';
            };
            const fmtAuto = (value, suffix = '') => {
                const num = Number(value);
                if (!Number.isFinite(num)) return '--';
                const absVal = Math.abs(num);
                if (absVal >= 1000) return `${num.toFixed(0)}${suffix}`;
                if (absVal >= 100) return `${num.toFixed(1)}${suffix}`;
                return `${num.toFixed(2)}${suffix}`;
            };
            const batteryText = fmt(status.battery_capacity_percent, 1, '%');
            const backupText = Number.isFinite(Number(status.backup_time_seconds)) ? `${Math.max(0, Math.round(Number(status.backup_time_seconds)))}s` : '--';
            const outputFreqText = fmt(status.output_frequency, 1, ' Hz');
            const mainsText = status.mains_abnormal ? '市电异常' : '市电正常';
            const batteryStateText = status.is_battery_low ? '电池偏低' : '电池正常';
            const reportedVoltageKind = status.output_reported_voltage_kind || status.output_voltage_display_mode || '--';
            const inputPhaseText = [status.input_voltage_r, status.input_voltage_s, status.input_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
                ? `${fmt(status.input_voltage_r, 1)} / ${fmt(status.input_voltage_s, 1)} / ${fmt(status.input_voltage_t, 1)} V`
                : '--';
            const outputPhaseText = [status.output_voltage_r, status.output_voltage_s, status.output_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
                ? `${fmt(status.output_voltage_r, 1)} / ${fmt(status.output_voltage_s, 1)} / ${fmt(status.output_voltage_t, 1)} V`
                : '--';
            const derivedPhaseText = [status.output_phase_voltage_r, status.output_phase_voltage_s, status.output_phase_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
                ? `${fmt(status.output_phase_voltage_r, 1)} / ${fmt(status.output_phase_voltage_s, 1)} / ${fmt(status.output_phase_voltage_t, 1)} V`
                : '--';
            const derivedLineText = [status.output_line_voltage_r, status.output_line_voltage_s, status.output_line_voltage_t].filter(v => v !== null && v !== undefined && v !== '').length
                ? `${fmt(status.output_line_voltage_r, 1)} / ${fmt(status.output_line_voltage_s, 1)} / ${fmt(status.output_line_voltage_t, 1)} V`
                : '--';
            const outputCurrentText = [status.output_current_r, status.output_current_s, status.output_current_t].filter(v => v !== null && v !== undefined && v !== '').length
                ? `${fmt(status.output_current_r, 1)} / ${fmt(status.output_current_s, 1)} / ${fmt(status.output_current_t, 1)} A`
                : '--';
            const faultCount = Array.isArray(status.fault_labels) ? status.fault_labels.length : 0;
            const warningCount = Array.isArray(status.warning_labels) ? status.warning_labels.length : 0;
            const alerts = Array.isArray(status.alerts) ? status.alerts : [];
            const queryWarnings = Array.isArray(status.query_warnings) ? status.query_warnings : [];
            const protocolSupport = status.protocol_support || {};
            const fieldCounts = status.field_counts || {};
            const rawPreview = status.raw_preview || {};
            const pollDiag = status.poll_diagnostics || {};
            const qualityScore = Number.isFinite(Number(status.data_quality_score))
                ? Number(status.data_quality_score)
                : Number(pollDiag.quality?.score);
            const qualityText = status.data_quality_text || pollDiag.quality?.text || '--';
            const qualityDetails = Array.isArray(status.data_quality_details)
                ? status.data_quality_details
                : (Array.isArray(pollDiag.quality?.details) ? pollDiag.quality.details : []);
            const linkHint = pollDiag.transport_hint || '--';
            const lastSuccessAge = Number.isFinite(Number(pollDiag.last_success_age_sec))
                ? `${Math.round(Number(pollDiag.last_success_age_sec))}s`
                : '--';
            const costMs = Number.isFinite(Number(pollDiag.collected_cost_ms))
                ? `${Math.round(Number(pollDiag.collected_cost_ms))} ms`
                : '--';
            const alertHtml = alerts.length
                ? alerts.slice(0, 6).map(item => `<span class="ups-alert-chip ${String(item).includes('故障') ? 'error' : 'warning'}">${escapeHtml(item)}</span>`).join('')
                : '<span class="ups-alert-chip warning" style="color:#bbf7d0;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.34);">当前无故障/告警</span>';
            const noteClass = status.last_error || status.error ? 'error' : (queryWarnings.length || statusMeta.level === 'stale' ? 'warn' : '');
            return `<div class="ups-card ${getCardStateClass(statusMeta)}">
                <div class="ups-head">
                    <div>
                        <div class="card-head-kicker">UPS Status</div>
                        <div class="ups-title">${escapeHtml(cfg.name || cfg.id)}</div>
                        <div class="ups-subtitle">${escapeHtml(cfg.brand || 'SANTAK')} / ${escapeHtml(cfg.model || '')} / ${escapeHtml(cfg.comm_mode || 'TCP')}</div>
                    </div>
                    <div class="status-chip-stack">
                        <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                        <span class="ups-chip">${escapeHtml(modeText)}</span>
                        <span class="ups-chip ${status.is_bypass ? 'error' : ''}">${escapeHtml(supplyStateText)}</span>
                    </div>
                </div>
                <div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">输入 / 输出</div><div class="value">${fmt(status.input_voltage, 1)} V / ${fmt(status.output_voltage, 1)} V</div></div>
                    <div class="ups-meta-item"><div class="label">输入频率 / 输出频率</div><div class="value">${fmt(status.input_frequency, 1, ' Hz')} / ${outputFreqText}</div></div>
                    <div class="ups-meta-item"><div class="label">电池容量 / 续航</div><div class="value">${escapeHtml(String(batteryText))} / ${escapeHtml(String(backupText))}</div></div>
                    <div class="ups-meta-item"><div class="label">总功率 / 负载</div><div class="value">${fmtAuto(status.total_real_power_kw, ' kW')} / ${fmt(status.load_percent, 1, ' %')}</div></div>
                </div>
                <div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">电池电压</div><div class="value">${fmt(status.battery_voltage, 2, ' V')}</div></div>
                    <div class="ups-meta-item"><div class="label">视在功率</div><div class="value">${fmtAuto(status.total_apparent_power_kva, ' kVA')}</div></div>
                    <div class="ups-meta-item"><div class="label">电池测试 / 温度</div><div class="value">${escapeHtml(status.battery_test_text || '--')} / ${fmt(status.temperature, 1, ' °C')}</div></div>
                    <div class="ups-meta-item"><div class="label">市电 / 电池状态</div><div class="value">${mainsText} / ${batteryStateText}</div></div>
                </div>
                <div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">三相输入电压</div><div class="value">${inputPhaseText}</div></div>
                    <div class="ups-meta-item"><div class="label">协议输出电压 (${escapeHtml(reportedVoltageKind)})</div><div class="value">${outputPhaseText}</div></div>
                    <div class="ups-meta-item"><div class="label">三相输出电流</div><div class="value">${outputCurrentText}</div></div>
                    <div class="ups-meta-item"><div class="label">故障 / 告警数量</div><div class="value">${faultCount} / ${warningCount}</div></div>
                </div>
                <div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">换算相电压</div><div class="value">${derivedPhaseText}</div></div>
                    <div class="ups-meta-item"><div class="label">换算线电压</div><div class="value">${derivedLineText}</div></div>
                    <div class="ups-meta-item"><div class="label">输入变压器</div><div class="value">${escapeHtml(String(status.transformer_type || '--'))}</div></div>
                    <div class="ups-meta-item"><div class="label">故障码 / 告警码</div><div class="value">${escapeHtml(String(status.fault_code_raw || '--'))} / ${escapeHtml(String(status.warning_code_raw || '--'))}</div></div>
                </div>
                <div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">数据质量</div><div class="value">${Number.isFinite(qualityScore) ? `${qualityScore} / 100 (${escapeHtml(String(qualityText))})` : '--'}</div></div>
                    <div class="ups-meta-item"><div class="label">链路类型</div><div class="value">${escapeHtml(String(linkHint))}</div></div>
                    <div class="ups-meta-item"><div class="label">最近成功</div><div class="value">${escapeHtml(String(lastSuccessAge))}</div></div>
                    <div class="ups-meta-item"><div class="label">采集耗时</div><div class="value">${escapeHtml(String(costMs))}</div></div>
                </div>
                <div class="ups-alert-list">${alertHtml}</div>
                <div class="ups-action-row">
                    <button class="btn-base btn-stop${getPermissionDisabledClass('ups.control')}" ${getPermissionDisabledAttrs('ups.control', '当前账号无 UPS 控制权限')} onclick="sendUpsShutdown('${escapeHtml(cfg.id)}', '${escapeHtml(cfg.shutdown_delay || '.3')}')">延时关机</button>
                </div>
                <div class="ups-action-row">
                    <span class="ups-chip ${protocolSupport.q1 === false ? 'error' : 'online'}">Q1 ${protocolSupport.q1 === false ? '失败' : `正常(${fieldCounts.q1 ?? 0})`}</span>
                    <span class="ups-chip ${protocolSupport.q6 ? (protocolSupport.q6_fallback ? 'warning' : 'online') : ''}" style="${protocolSupport.q6 ? (protocolSupport.q6_fallback ? 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);' : '') : 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);'}">Q6 ${protocolSupport.q6 ? (protocolSupport.q6_fallback ? `回退(${fieldCounts.q6 ?? 0})` : `正常(${fieldCounts.q6 ?? 0})`) : `降级(${fieldCounts.q6 ?? 0})`}</span>
                    <span class="ups-chip ${protocolSupport.wa ? (protocolSupport.wa_fallback ? 'warning' : 'online') : ''}" style="${protocolSupport.wa ? (protocolSupport.wa_fallback ? 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);' : '') : 'color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.14);'}">WA ${protocolSupport.wa ? (protocolSupport.wa_fallback ? `回退(${fieldCounts.wa ?? 0})` : `正常(${fieldCounts.wa ?? 0})`) : `降级(${fieldCounts.wa ?? 0})`}</span>
                </div>
                ${(queryWarnings.length || !protocolSupport.q6 || !protocolSupport.wa || status.last_error || status.error || statusMeta.level === 'stale') ? `<div class="card-inline-note ${noteClass}">
                    ${statusMeta.level === 'stale' ? `状态说明: ${escapeHtml(statusMeta.note)}<br>` : ''}
                    ${queryWarnings.length ? `${queryWarnings.map(item => escapeHtml(item)).join('<br>')}${(!protocolSupport.q6 || !protocolSupport.wa || status.error) ? '<br>' : ''}` : ''}
                    ${qualityDetails.length ? `${qualityDetails.map(item => `质量提示: ${escapeHtml(String(item))}`).join('<br>')}<br>` : ''}
                    ${(!protocolSupport.q6 || !protocolSupport.wa) ? `原始回包预览: Q1=${escapeHtml(rawPreview.q1 || '--')} | Q6=${escapeHtml(rawPreview.q6 || '--')} | WA=${escapeHtml(rawPreview.wa || '--')}${status.error ? '<br>' : ''}` : ''}
                    ${(status.last_error || status.error) ? `异常: ${escapeHtml(status.last_error || status.error)}` : ''}
                </div>` : ''}
            </div>`;
        }
        function renderDashboardUpsCard(cfg, status) {
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const batteryText = status.battery_capacity_percent !== null && status.battery_capacity_percent !== undefined ? `${status.battery_capacity_percent}%` : '--';
            const loadText = status.load_percent !== null && status.load_percent !== undefined ? `${status.load_percent}%` : '--';
            const inputText = status.input_voltage !== null && status.input_voltage !== undefined ? `${status.input_voltage}V` : '--';
            const outputText = status.output_voltage !== null && status.output_voltage !== undefined ? `${status.output_voltage}V` : '--';
            const modeText = status.supply_state || status.system_mode || '--';
            return `<div class="dashboard-mini-card ${getCardStateClass(statusMeta)}">
                <div class="dashboard-mini-head">
                    <div>
                        <div class="dashboard-mini-title">${escapeHtml(cfg.name || cfg.id)}</div>
                        <div class="dashboard-mini-subtitle">${escapeHtml(cfg.comm_mode || 'UPS')}</div>
                    </div>
                    <div class="dashboard-mini-chip-row">
                        <span class="ups-chip ${statusMeta.chipClass}">${statusMeta.text}</span>
                    </div>
                </div>
                <div class="dashboard-mini-metrics">
                    <div class="dashboard-mini-metric"><div class="label">电池</div><div class="value">${escapeHtml(batteryText)}</div></div>
                    <div class="dashboard-mini-metric"><div class="label">负载</div><div class="value">${escapeHtml(loadText)}</div></div>
                    <div class="dashboard-mini-metric"><div class="label">输入 / 输出</div><div class="value">${escapeHtml(inputText)} / ${escapeHtml(outputText)}</div></div>
                    <div class="dashboard-mini-metric"><div class="label">模式</div><div class="value">${escapeHtml(modeText)}</div></div>
                </div>
                <div class="dashboard-mini-note">${escapeHtml(statusMeta.note)}</div>
            </div>`;
        }
