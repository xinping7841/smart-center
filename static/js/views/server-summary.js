// AI_MODULE: server_summary_view
// AI_PURPOSE: 首页服务器摘要轻量渲染，避免 dashboard 首屏加载完整 server-monitor.js。
// AI_BOUNDARY: 优先只读 /api/dashboard/summary 的紧凑机器摘要；不提供关机、重启、唤醒、加密锁详情等高风险操作。
// AI_DATA_FLOW: /api/dashboard/summary.modules.server.machines -> dashboard-server-compact-grid DOM。
// AI_RUNTIME: 仅首页按需加载；服务器详情页仍由 static/js/views/server-monitor.js 负责。
// AI_RISK: 低，不下发真实控制；但状态判断必须与服务器页保持一致，避免误导值班判断。
// AI_SEARCH_KEYWORDS: server summary, dashboard compact, lightweight server, frontend performance.

(function installSmartCenterServerSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.serverSummary = Object.assign({}, SmartCenter.serverSummary || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));

    function normalizeServerBytes(value) {
        const num = Number(value);
        return Number.isFinite(num) ? num : 0;
    }

    function formatServerMetric(value, suffix = '%') {
        const num = Number(value);
        if (!Number.isFinite(num)) return `0${suffix}`;
        return `${num.toFixed(num % 1 ? 1 : 0)}${suffix}`;
    }

    function formatServerTime(value) {
        if (!value) return '未记录';
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

    function buildServerDiagnostic(agent = {}, machine = {}) {
        const diagnostic = machine?.diagnostic || {};
        const st = machine?.status || {};
        const isOnline = !!machine?.is_online;
        const hasRuntime = !!diagnostic.has_runtime_metrics;
        const reportOnline = !!(machine?.report_online || diagnostic.report_online);
        if (!isOnline && !reportOnline) {
            const offlineCode = String(diagnostic.code || 'agent_offline').trim();
            const unreachable = offlineCode === 'agent_offline_network_unreachable' || machine?.ping_online === false;
            return {
                level: unreachable ? 'warn' : 'offline',
                code: offlineCode,
                badgeText: unreachable ? 'Agent离线' : '离线',
                badgeClass: unreachable ? 'warn' : 'error',
                summary: diagnostic.summary || (unreachable ? 'Agent离线 / 网络不可达' : '节点离线'),
                detail: String(diagnostic.detail || '').trim(),
                rootCause: String(diagnostic.root_cause || '').trim(),
                recommendation: String(diagnostic.suggestion || '').trim(),
                logExcerpt: '',
                needsRedeploy: !!diagnostic.needs_redeploy,
                hasRuntime,
                isOnline,
                reportOnline: false,
                agentHeartbeatOnline: !!(machine?.agent_heartbeat_online || diagnostic.agent_heartbeat_online),
                runtimeFresh: !!(machine?.runtime_fresh || diagnostic.runtime_fresh),
                lastReportKind: String(machine?.last_report_kind || diagnostic.last_report_kind || st.last_report_kind || '').trim(),
                hardwareRefreshedAt: st.hardware_refreshed_at || '',
            };
        }
        const rawLevel = String(diagnostic.level || (isOnline && hasRuntime ? 'success' : 'warn')).toLowerCase();
        const levelAlias = { ok: 'success', online: 'success', normal: 'success', warning: 'warn', stale: 'warn' };
        const level = levelAlias[rawLevel] || rawLevel;
        const code = String(diagnostic.code || '').trim();
        const badgeMap = {
            healthy: ['运行正常', 'normal'],
            offline_unreachable: ['离线', 'error'],
            agent_offline_network_unreachable: ['Agent离线', 'warn'],
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
        const summary = String(diagnostic.summary || '').trim() || '等待节点上报';
        return {
            level,
            code,
            badgeText,
            badgeClass,
            summary,
            detail: String(diagnostic.detail || '').trim(),
            rootCause: String(diagnostic.root_cause || '').trim(),
            recommendation: String(diagnostic.suggestion || '').trim(),
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

    function renderDashboardServerCompact(data = [], options = {}) {
        const container = options.container || (global.document ? document.getElementById('dashboard-server-compact-grid') : null);
        if (!container) return false;
        const fallbackList = Array.isArray(options.fallbackList) ? options.fallbackList : [];
        const machines = Array.isArray(data) && data.length ? data : fallbackList;
        const visibleMachines = machines.filter(isServerDashboardVisible);
        if (!machines.length) {
            container.classList.remove('server-compact-grouped');
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">正在加载机器状态...</div>';
            return true;
        }
        if (!visibleMachines.length) {
            container.classList.remove('server-compact-grouped');
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">暂无已分组机器，未分组机器不参与首页显示。</div>';
            return true;
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
        return true;
    }

    const api = {
        buildServerDiagnostic,
        normalizeServerBytes,
        formatServerMetric,
        formatServerTime,
        formatServerClockOffset,
        isVirtualGpuName,
        compactGpuName,
        normalizeGpuIdentity,
        dedupeGpuRows,
        getServerCompactGpuText,
        getServerCompactMetricClass,
        getServerCompactGroupName,
        getServerDisplayName,
        buildServerCompactGroups,
        isServerDashboardVisible,
        getServerCompactAlertText,
        getServerCompactTooltip,
        renderDashboardServerCompact,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.server-summary', {
            kind: 'dashboard-summary',
            exports: Object.keys(api),
            source: 'static/js/views/server-summary.js',
        });
    }
})(window);
