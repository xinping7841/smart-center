// AI_MODULE: server_monitor_view
// AI_PURPOSE: 服务器看板卡片、硬件指标、GPU/CodeMeter、在线离线、WOL/关机/重启操作展示。
// AI_BOUNDARY: 不生成 Agent 脚本；Agent 分发和命令队列在 api/server.py。
// AI_DATA_FLOW: /api/machines -> 服务器卡片 DOM；用户操作 -> /api/machines/* 或 /api/wake/*。
// AI_RUNTIME: 首页/服务器页面轮询调用，需处理离线设备保留硬件信息。
// AI_RISK: 高，按钮可能触发真实关机、重启、唤醒；必须保留确认和权限提示。
// AI_SEARCH_KEYWORDS: server, machine card, gpu, codemeter, wake, shutdown, offline.

(function installSmartCenterServerMonitor(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.serverMonitor = Object.assign({}, SmartCenter.serverMonitor || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || (value => String(value ?? ''));
    const formatNetworkMbpsValue = utils.formatNetworkMbps || (value => `${Number(value || 0).toFixed(2)} Mbps`);
    const formatBytesGiBValue = utils.formatBytesGiB || (bytes => `${Number(bytes || 0).toFixed(1)} GB`);

    function getContext(maybeContext) {
        return maybeContext && typeof maybeContext === 'object' ? maybeContext : {};
    }

    function getColor(p) { return p > 90 ? 'bg-red' : (p > 70 ? 'bg-yellow' : 'bg-green'); }
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
    function getServerClockOffsetClass(value) {
        const offset = Math.abs(Number(value));
        if (!Number.isFinite(offset)) return ' clock-unknown';
        if (offset >= 300) return ' clock-bad';
        if (offset >= 120) return ' clock-warn';
        return ' clock-ok';
    }

    function buildServerDiagnostic(agent = {}, machine = {}, context = {}) {
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
            return formatNetworkMbpsValue(normalizeServerBytes(kbPerSec));
        }

    function formatBytesGiB(bytes) {
            return formatBytesGiBValue(bytes);
        }

    function compactHardwareName(value, fallback = '--') {
            return String(value || fallback).replace(/\s+/g, ' ').trim();
        }

    function compactCpuName(name) {
            let text = compactHardwareName(name, 'CPU')
                .replace(/\b\d+(?:th|st|nd|rd)\s+Gen\s+/i, '')
                .replace(/\(R\)|\(TM\)/g, '')
                .replace(/\s+CPU\s*/i, ' ')
                .replace(/\s+with\s+Radeon\s+Graphics/i, '')
                .replace(/\s+@.+$/i, '')
                .replace(/\s+/g, ' ')
                .trim();
            if (text.length > 42) text = text.slice(0, 39).trim() + '...';
            return text || 'CPU';
        }

    function memoryChannelText(topology) {
            const mode = String(topology?.channel_mode || '').toLowerCase();
            if (mode === 'dual') return '双通道';
            if (mode === 'single') return '单通道';
            return '通道未知';
        }

    function getAdapterIps(adapter) {
            const rawIps = Array.isArray(adapter?.ipv4)
                ? adapter.ipv4
                : [adapter?.adapter_ip, adapter?.ip, adapter?.ipv4].filter(Boolean);
            return rawIps.map(ip => String(ip || '').trim()).filter(Boolean);
        }

    function getAdapterMac(adapter) {
            return normalizeDisplayMac(adapter?.adapter_mac || adapter?.mac || adapter?.physical_mac || adapter?.address);
        }

    function getAdapterName(adapter, fallback = '网卡') {
            return compactHardwareName(adapter?.description || adapter?.adapter_description || adapter?.name || adapter?.adapter_name, fallback);
        }

    function getAdapterSpeedText(adapter) {
            const speed = Number(adapter?.speed_mbps || adapter?.link_speed_mbps || adapter?.speed);
            if (!Number.isFinite(speed) || speed <= 0 || speed >= 100000) return '';
            if (speed >= 1000) return `${(speed / 1000).toFixed(speed % 1000 ? 1 : 0)}Gbps`;
            return `${speed.toFixed(0)}Mbps`;
        }

    function renderServerNetworkAdapters(st, context = {}) {
            const { serverViewMode = 'compact' } = getContext(context);
            if (serverViewMode !== 'detail') return '';
            const adapters = Array.isArray(st.network_adapters) ? st.network_adapters : [];
            const physical = adapters.filter(adapter => !adapter?.is_virtual);
            const active = physical.filter(adapter => {
                const state = String(adapter?.state || adapter?.status || '').toLowerCase();
                return state === 'up' || state === 'connected' || getAdapterIps(adapter).length;
            });
            const rows = (active.length ? active : physical).slice(0, 6);
            if (!rows.length) return '';
            return `<div class="server-adapter-list">${rows.map((adapter, idx) => {
                const ips = getAdapterIps(adapter);
                const mac = getAdapterMac(adapter);
                const speed = getAdapterSpeedText(adapter);
                const state = String(adapter?.state || adapter?.status || '').trim();
                const name = getAdapterName(adapter, `网卡 ${idx + 1}`);
                const meta = [ips.length ? `IP ${ips.join(' / ')}` : 'IP 未上报', mac ? `MAC ${mac}` : 'MAC 未上报', speed, state].filter(Boolean);
                return `<div class="server-adapter-row" title="${escapeHtml([name, ...meta].join('\n'))}"><span class="server-adapter-index">${escapeHtml(`网卡 ${idx + 1}`)}</span><span class="server-adapter-body"><strong>${escapeHtml(name)}</strong><span class="server-adapter-detail">${meta.map(item => `<em>${escapeHtml(item)}</em>`).join('')}</span></span></div>`;
            }).join('')}</div>`;
        }

    function renderServerHardwareExtra(st, context = {}) {
            const { serverViewMode = 'compact' } = getContext(context);
            if (serverViewMode !== 'detail') return '';
            const os = st.os_info || {};
            const mem = st.memory_topology || {};
            const storage = st.storage_summary || {};
            const network = st.network_summary || {};
            const wifi = st.wireless || {};
            const bt = st.bluetooth || {};
            const osText = os.name || st.os_caption || st.os_version || '';
            const memText = mem.installed_count ? `${mem.installed_count}条 ${memoryChannelText(mem)}` : '';
            const diskCount = storage.disk_count ?? (Array.isArray(st.storage_devices) ? st.storage_devices.length : 0);
            const nicText = `${network.active_count ?? 0}/${network.physical_count ?? 0}网卡`;
            const wirelessText = wifi.present ? (wifi.connected ? `Wi-Fi ${wifi.ssid || '已连接'}` : 'Wi-Fi未连') : '';
            const bluetoothText = bt.present ? (bt.blocked ? '蓝牙阻塞' : '蓝牙') : '';
            const items = [
                ['系统', osText],
                ['内存', memText],
                ['硬盘', diskCount ? `${diskCount}盘` : ''],
                ['网络', [nicText, wirelessText, bluetoothText].filter(Boolean).join(' / ')],
            ].filter(([, value]) => value);
            const itemHtml = items.map(([label, value]) => `<div class="hardware-item server-hardware-extra"><span class="hardware-label">${escapeHtml(label)}</span><span class="hardware-value">${escapeHtml(value)}</span></div>`).join('');
            return `${itemHtml}${renderServerNetworkAdapters(st, context)}`;
        }

    function getStorageVolumeRows(st) {
            const filesystems = Array.isArray(st.storage_filesystems) ? st.storage_filesystems : [];
            const rows = filesystems.map((fs, idx) => {
                const mounts = Array.isArray(fs.mountpoints) ? fs.mountpoints.filter(Boolean) : [];
                const label = mounts[0] || fs.name || fs.disk || `卷${idx + 1}`;
                const percent = Number.isFinite(Number(fs.percent)) ? Number(fs.percent) : (Number.isFinite(Number(st.disk_percent)) ? Number(st.disk_percent) : 0);
                return {
                    label,
                    percent: Math.max(0, Math.min(100, percent)),
                    used: Number(fs.used_bytes) || 0,
                    total: Number(fs.size_bytes) || 0,
                    free: Number(fs.free_bytes) || 0,
                    title: [fs.model, fs.fstype, fs.disk, fs.volume_name].filter(Boolean).join(' · '),
                    tag: fs.is_network ? 'NAS' : (fs.is_removable ? '外接' : (fs.is_system ? '系统' : '')),
                    isSystem: !!fs.is_system,
                    isNetwork: !!fs.is_network,
                };
            }).filter(row => row.total || row.label);
            rows.sort((a, b) => (b.isSystem - a.isSystem) || (b.isNetwork - a.isNetwork) || a.label.localeCompare(b.label));
            if (rows.length) return rows;
            const devices = Array.isArray(st.storage_devices) ? st.storage_devices : [];
            const deviceRows = devices.flatMap((device, idx) => {
                const parts = Array.isArray(device.partitions) ? device.partitions : [];
                return parts.filter(part => part.size_bytes).map((part, pidx) => ({
                    label: part.is_system ? '系统盘' : `${device.name || `Disk ${idx}`}-${pidx + 1}`,
                    percent: Math.max(0, Math.min(100, Number(part.percent) || normalizeServerBytes(st.disk_percent))),
                    used: Number(part.used_bytes) || 0,
                    total: Number(part.size_bytes) || 0,
                    free: Number(part.free_bytes) || 0,
                    title: [device.model, part.fstype, part.type].filter(Boolean).join(' · '),
                    tag: part.is_network ? 'NAS' : (part.is_removable ? '外接' : (part.is_system ? '系统' : '')),
                    isSystem: !!part.is_system,
                    isNetwork: !!part.is_network,
                }));
            });
            if (deviceRows.length) return deviceRows;
            return [{
                label: '系统盘',
                percent: Math.max(0, Math.min(100, normalizeServerBytes(st.disk_percent))),
                used: Number(st.disk_used) ? Number(st.disk_used) * (1024 ** 3) : 0,
                total: Number(st.disk_total) ? Number(st.disk_total) * (1024 ** 3) : 0,
                free: 0,
                title: '',
                tag: '系统',
                isSystem: true,
                isNetwork: false,
            }];
        }

    function renderServerStorageRows(st, context = {}) {
            const { serverViewMode = 'compact' } = getContext(context);
            const rows = getStorageVolumeRows(st);
            const visibleRows = serverViewMode === 'detail' ? rows.slice(0, 6) : rows.filter(row => row.isSystem || row.isNetwork).slice(0, 3);
            const selected = visibleRows.length ? visibleRows : rows.slice(0, 3);
            return `<div class="server-storage-list">${selected.map(row => {
                const sizeText = row.total ? `${formatBytesGiB(row.used)} / ${formatBytesGiB(row.total)}` : '';
                const tagHtml = row.tag ? `<em>${escapeHtml(row.tag)}</em>` : '';
                return `<div class="metric-row server-storage-row" title="${escapeHtml(row.title || row.label)}"><div class="metric-label"><span>${escapeHtml(row.label)}${tagHtml}</span><span>${sizeText ? `${escapeHtml(sizeText)} · ` : ''}${formatServerMetric(row.percent)}</span></div><div class="progress-track"><div class="progress-fill ${getColor(row.percent)}" style="width:${row.percent}%"></div></div></div>`;
            }).join('')}</div>`;
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
                const utilPercent = Math.max(0, Math.min(100, normalizeServerBytes(g?.util_percent)));
                const util = formatServerMetric(utilPercent);
                const memoryUsed = normalizeServerBytes(g?.memory_used_mb);
                const memoryTotal = normalizeServerBytes(g?.memory_total_mb);
                const memoryPercent = Math.max(0, Math.min(100, memoryTotal > 0 ? (memoryUsed / memoryTotal) * 100 : normalizeServerBytes(g?.memory_util_percent)));
                const memoryText = memoryTotal > 0 ? `${(memoryUsed / 1024).toFixed(1).replace(/\.0$/, '')}/${(memoryTotal / 1024).toFixed(1).replace(/\.0$/, '')} GB` : formatServerMetric(memoryPercent);
                const hasTemp = Number.isFinite(Number(g?.temp)) && Number(g?.temp) > 0;
                const temp = hasTemp ? `${Number(g.temp).toFixed(0)}°C` : '温度未上报';
                const tempColor = hasTemp ? 'var(--text-main)' : 'var(--text-sub)';
                const memoryHtml = memoryPercent > 0
                    ? `<div class="metric-label server-gpu-memory-label"><span>显存占用</span><span>${escapeHtml(memoryText)} · ${formatServerMetric(memoryPercent)}</span></div><div class="progress-track server-gpu-memory-track"><div class="progress-fill bg-blue" style="width:${memoryPercent}%"></div></div>`
                    : '';
                return `<div class="metric-row server-gpu-row" title="${escapeHtml(g?.name || 'GPU')}"><div class="server-gpu-head"><span class="server-gpu-index">${escapeHtml(label)}</span><strong>${escapeHtml(compactGpuName(g?.name))}</strong><em style="color:${tempColor};">${temp}</em></div><div class="metric-label"><span>核心占用</span><span>${util}</span></div><div class="progress-track"><div class="progress-fill ${getColor(utilPercent)}" style="width:${utilPercent}%"></div></div>${memoryHtml}</div>`;
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

    function renderServerMetaStrip(m, st, agent, diagnostic, context = {}) {
            const rawTaskState = String(agent.task_state || '').toLowerCase();
            const taskText = agent.task_exists ? ((rawTaskState === 'running' || rawTaskState.includes('systemd')) ? '在线' : (agent.task_state || '在线')) : '未安装';
            const currentAgentVersion = String(agent.version || '').trim();
            const agentMissing = !currentAgentVersion;
            const ctx = getContext(context);
            const agentOutdated = isAgentVersionOutdated(agent, ctx);
            const agentChipClass = agentMissing ? ' agent-missing' : (agentOutdated ? ' agent-old' : '');
            const updateHint = getAgentUpdateHint(agent, ctx);
            const agentTitle = agentOutdated
                ? `当前版本 ${currentAgentVersion}，最新版 ${ctx.latestAgentVersion || ''}${updateHint.title ? `\n${updateHint.title}` : ''}`
                : (currentAgentVersion ? `当前版本 ${currentAgentVersion}` : '未上报 Agent 版本');
            const agentDisplay = currentAgentVersion || '--';
            const latestHint = agentOutdated ? `<em class="server-agent-latest">${escapeHtml(updateHint.label)}</em>` : '';
            const serverReceivedAt = m.server_received_at || st.server_received_at || m.last_online || '';
            const clientReportedAt = m.client_reported_at || st.client_reported_at || '';
            const reportOnline = !!(m.report_online || diagnostic.reportOnline);
            const runtimeFresh = !!((m.report_online || diagnostic.reportOnline) && (m.runtime_fresh || diagnostic.runtimeFresh));
            const reportKind = String(m.last_report_kind || diagnostic.lastReportKind || st.last_report_kind || '').trim();
            const clockOffset = m.clock_offset_sec ?? st.clock_offset_sec;
            const clockClass = getServerClockOffsetClass(clockOffset);
            const clockTitle = clientReportedAt
                ? `120接收: ${formatServerTime(serverReceivedAt)}\n客户端: ${formatServerTime(clientReportedAt)}\n偏差: ${formatServerClockOffset(clockOffset)}`
                : `120接收: ${formatServerTime(serverReceivedAt)}\n客户端时间暂未上报`;
            const reportKindLabel = reportKind === 'full' ? '完整采集' : (reportKind === 'bootstrap' ? '安装心跳' : (reportKind === 'agent_heartbeat' ? 'Agent心跳' : (reportKind || '')));
            const pingText = m.ping_online === true ? 'Ping可达' : (m.ping_online === false ? '网络不可达' : (reportOnline ? (reportKindLabel || '心跳在线') : '未检测'));
            const collectText = runtimeFresh ? taskText : (reportOnline ? '采集停滞' : 'Agent未上报');
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
                if (text && text.startsWith('3-') && !items.includes(text)) items.push(text);
            };
            if (Array.isArray(codemeter?.serials)) codemeter.serials.forEach(pushSerial);
            if (Array.isArray(codemeter?.containers)) {
                codemeter.containers.forEach(item => pushSerial(item?.serial || item?.serial_number || item?.id));
            }
            const physical = codemeter?.license_identity?.physical_serials;
            if (Array.isArray(physical)) physical.forEach(pushSerial);
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

    function getCodeMeterLicenseCode(item) {
            return String(item?.product_code || item?.code || item?.license_code || item?.pc || '').trim();
        }

    function getCodeMeterLicenseExpiryValue(item) {
            return item?.expires_at || item?.valid_until || item?.expire_at || item?.expiry || '';
        }

    function getCodeMeterRemainingDays(item, date) {
            const direct = Number(item?.remaining_days);
            if (Number.isFinite(direct)) return Math.floor(direct);
            if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const expiryDay = new Date(date);
            expiryDay.setHours(0, 0, 0, 0);
            return Math.floor((expiryDay.getTime() - today.getTime()) / 86400000);
        }

    function normalizeCodeMeterLicenses(codemeter, serials = []) {
            const licenses = Array.isArray(codemeter?.licenses) ? codemeter.licenses : [];
            const fallbackSerial = serials[0] || '';
            const rows = [];
            const seen = new Set();
            licenses.forEach((item, index) => {
                if (!item || typeof item !== 'object') return;
                const firmCode = String(item.firm_code || item.company_code || codemeter?.license_code || codemeter?.license_identity?.company_code || '').trim();
                if (firmCode && firmCode !== '102541') return;
                const code = getCodeMeterLicenseCode(item);
                const serial = String(item.serial || item.container_serial || item.container || fallbackSerial || '').trim();
                const expiryDate = parseCodeMeterExpiry(getCodeMeterLicenseExpiryValue(item));
                const expiryText = expiryDate ? formatCodeMeterExpiry(expiryDate) : '';
                const validity = String(item.validity || '').toLowerCase();
                const isPermanent = validity === 'permanent' || /长期|永久|无限|permanent|unlimited|lifetime/i.test(String(item.summary || ''));
                const daysLeft = isPermanent ? null : getCodeMeterRemainingDays(item, expiryDate);
                const expired = !isPermanent && (item.expired === true || (Number.isFinite(daysLeft) && daysLeft < 0));
                if (!code && !expiryText && !isPermanent) return;
                const key = `${serial}|${code}|${expiryText}|${isPermanent ? 'permanent' : ''}`;
                if (seen.has(key)) return;
                seen.add(key);
                rows.push({
                    serial,
                    code,
                    expiryText,
                    daysLeft,
                    expired,
                    permanent: isPermanent,
                    sourceIndex: index,
                });
            });
            rows.sort((a, b) => {
                if (a.expired !== b.expired) return a.expired ? 1 : -1;
                const aCode = Number(a.code);
                const bCode = Number(b.code);
                const aCodeKey = Number.isFinite(aCode) ? aCode : 999999999;
                const bCodeKey = Number.isFinite(bCode) ? bCode : 999999999;
                if (aCodeKey !== bCodeKey) return aCodeKey - bCodeKey;
                return (a.expiryText || '9999-12-31').localeCompare(b.expiryText || '9999-12-31');
            });
            return rows;
        }

    function hasCompanyCodeMeterLicense(codemeter) {
            const code = String(codemeter?.license_code || codemeter?.license_identity?.company_code || '').trim();
            return code === '102541' || !!codemeter?.license_identity?.has_company_license;
        }

    function getCodeMeterValidityText(codemeter) {
            const serials = getCodeMeterSerials(codemeter);
            if (!serials.length) return codemeter?.installed ? '无加密锁' : '未安装';
            const normalizedLicenses = normalizeCodeMeterLicenses(codemeter, serials);
            if (!hasCompanyCodeMeterLicense(codemeter) && !normalizedLicenses.length) return '无授权';
            const activeRows = normalizedLicenses.filter(row => !row.expired);
            if (activeRows.length > 1) return `${activeRows.length}项授权`;
            if (activeRows.length === 1) {
                const row = activeRows[0];
                if (row.permanent) return '长期有效';
                if (Number.isFinite(row.daysLeft)) return `剩余${row.daysLeft}天`;
                if (row.expiryText) return `到期 ${row.expiryText}`;
            }
            if (normalizedLicenses.some(row => row.expired)) return '无有效授权';
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
            const normalizedLicenses = normalizeCodeMeterLicenses(info, serials);
            const activeLicenses = normalizedLicenses.filter(row => !row.expired);
            const displayRows = activeLicenses.slice(0, 3);
            const expiryStatus = getCodeMeterExpiryStatusFromLicenses(info.licenses);
            const minDaysLeft = activeLicenses
                .map(row => row.daysLeft)
                .filter(value => Number.isFinite(value))
                .sort((a, b) => a - b)[0];
            const hasExpiredOnly = normalizedLicenses.length > 0 && activeLicenses.length === 0;
            const noDongle = installed && !serials.length;
            const noAuth = serials.length > 0 && !activeLicenses.length;
            const daysClass = Number.isFinite(minDaysLeft) ? (minDaysLeft < 15 ? 'error' : (minDaysLeft < 30 ? 'warning' : '')) : '';
            const cls = (!installed || level === 'muted') ? 'muted' : (level === 'error' || hasExpiredOnly || daysClass === 'error' ? 'error' : ((!running || level === 'warning' || runtimeOutdated || noDongle || noAuth || !hasCompanyLicense || daysClass === 'warning' || expiryStatus.cls === 'warning') ? 'warning' : ''));
            const serialText = serials.length ? serials.slice(0, 1).join('') + (serials.length > 1 ? ` +${serials.length - 1}` : '') : (installed ? '无加密锁' : '未安装');
            const validityText = getCodeMeterValidityText(info);
            const titleParts = [`CodeMeter ${validityText}`];
            titleParts.push(`加密锁: ${serials.length ? serials.join(' / ') : serialText}`);
            if (info.service_state) titleParts.push(`服务: ${info.service_state}`);
            if (normalizedLicenses.length) {
                titleParts.push('');
                titleParts.push('加密锁编号        产品码   到期时间      剩余天数');
                normalizedLicenses.forEach(row => {
                    const daysText = row.permanent ? '长期' : (Number.isFinite(row.daysLeft) && row.daysLeft >= 0 ? `${row.daysLeft}天` : (row.expired ? '已过期' : '--'));
                    const serialPart = String(row.serial || serialText).padEnd(15, ' ');
                    const codePart = String(row.code || '--').padEnd(6, ' ');
                    const expiryPart = String(row.expiryText || '长期有效').padEnd(11, ' ');
                    titleParts.push(`${serialPart} ${codePart} ${expiryPart} ${daysText}`);
                });
            }
            if (Number.isFinite(minDaysLeft) && minDaysLeft >= 0) titleParts.push(`最近剩余: ${minDaysLeft} 天`);
            if (runtimeVersion) titleParts.push(`Runtime: ${runtimeVersion}${runtimeOutdated ? '，建议升级到 8.0+' : ''}`);
            if (info.checked_at) titleParts.push(`检测: ${formatServerTime(info.checked_at)}`);
            const upgradeHtml = runtimeOutdated ? `<em class="upgrade">升级8.0+</em>` : '';
            let bodyHtml = '';
            if (displayRows.length) {
                const shownSerials = new Set();
                const rowsHtml = displayRows.map(row => {
                    const daysText = row.permanent ? '长期' : (Number.isFinite(row.daysLeft) ? `${row.daysLeft}天` : '--');
                    const rowClass = row.permanent ? 'permanent' : (Number.isFinite(row.daysLeft) && row.daysLeft < 15 ? 'danger' : (Number.isFinite(row.daysLeft) && row.daysLeft < 30 ? 'warn' : ''));
                    const serialValue = row.serial || serialText;
                    const serialDisplay = shownSerials.has(serialValue) ? '' : serialValue;
                    if (serialValue) shownSerials.add(serialValue);
                    return `<div class="codemeter-license-row ${rowClass}"><span class="cm-serial">${escapeHtml(serialDisplay)}</span><span class="cm-code">${escapeHtml(row.code || '--')}</span><span class="cm-expiry">${escapeHtml(row.expiryText || '长期')}</span><span class="cm-days">${escapeHtml(daysText)}</span></div>`;
                }).join('');
                const moreText = activeLicenses.length > displayRows.length ? `<em class="codemeter-more">+${activeLicenses.length - displayRows.length}</em>` : '';
                bodyHtml = `<div class="codemeter-license-table"><div class="codemeter-license-head"><span class="cm-serial">加密锁编号</span><span class="cm-code">产品码</span><span class="cm-expiry">到期时间</span><span class="cm-days">剩余天数</span></div>${rowsHtml}</div>${moreText}`;
            } else {
                bodyHtml = `<strong><em class="serial">${escapeHtml(serialText)}</em><em class="validity">${escapeHtml(validityText)}</em>${upgradeHtml}</strong>`;
            }
            return `<div class="server-codemeter-line ${cls}" title="${escapeHtml(titleParts.join('\n'))}">${bodyHtml}</div>`;
        }

    function getServerGroupName(machine) {
            const raw = String(machine?.asset_group || '').trim();
            return raw || '未分组';
        }

    function isAgentVersionOutdated(agent = {}, context = {}) {
            const { latestAgentVersion = '', compareAgentVersionBase = null } = getContext(context);
            const currentAgentVersion = String(agent?.version || '').trim();
            return !!(latestAgentVersion && currentAgentVersion && typeof compareAgentVersionBase === 'function' && compareAgentVersionBase(currentAgentVersion, latestAgentVersion) < 0);
        }

    function getAgentUpdateHint(agent = {}, context = {}) {
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
                label: `需更新到 ${getContext(context).latestAgentVersion || ''}`,
                title: '等待 agent 自更新或手动覆盖安装'
            };
        }

    function renderServerCommandPending(pending) {
            if (!pending) return '';
            const seconds = Math.max(0, Math.round((Number(pending.ageMs) || 0) / 1000));
            const pendingMeta = {
                shutdown: ['关机指令已下发', '等待节点断开 Agent / 进入离线状态'],
                restart: ['重启指令已下发', '通常 30-90 秒内离线后恢复上报'],
                refresh: ['刷新指令已下发', '等待节点重新采集并上报'],
                wake: ['唤醒包已发送', '等待网卡响应 WOL 并恢复 Agent 上报'],
            };
            const meta = pendingMeta[pending.cmd] || [`${pending.actionName || '指令'}已下发`, '等待节点回报执行状态'];
            return `<div class="server-pending-command" title="${escapeHtml(meta[1])}"><strong>${escapeHtml(meta[0])}</strong><span>${seconds}s</span><em>${escapeHtml(meta[1])}</em></div>`;
        }

    function renderServerCommandResult(result) {
            if (!result || typeof result !== 'object' || !result.action) return '';
            const actionName = { shutdown: '关机', restart: '重启', refresh: '刷新', wake: '唤醒' }[result.action] || result.action;
            const ok = result.ok === true;
            const statusText = ok ? (result.action === 'restart' ? '已接收，等待恢复' : (result.action === 'shutdown' ? '已接收，等待离线' : '已接收')) : '失败';
            const method = result.method ? ` · ${result.method}` : '';
            const exitCode = Number.isFinite(Number(result.exit_code)) ? ` · 退出码 ${result.exit_code}` : '';
            const error = result.error ? ` · ${result.error}` : '';
            const remediation = result.remediation ? ` · ${result.remediation}` : '';
            const cls = ok ? 'ok' : 'error';
            return `<div class="server-command-result ${cls}" title="${escapeHtml(error + remediation)}">${escapeHtml(actionName)}${escapeHtml(statusText)}${escapeHtml(method)}${escapeHtml(exitCode)}${escapeHtml(error || remediation)}</div>`;
        }

    function renderServerCard(m, context = {}) {
            const st = m.status || {};
            const agent = m.agent_status || {};
            const ctx = getContext(context);
            const diagnostic = buildServerDiagnostic(agent, m, ctx);
            const pendingCommand = typeof ctx.getServerCommandPending === 'function' ? ctx.getServerCommandPending(m.mac) : null;
            const commandResultHtml = renderServerCommandResult(st.command_result);
            const identityLine = getServerIdentityLine(m);
            const gpuHtml = renderServerGpuList(st.gpu_list);
            const statusMetaHtml = renderServerMetaStrip(m, st, agent, diagnostic, ctx);
            const diagnosticHtml = renderServerAttention(diagnostic);
            const cpuPercent = normalizeServerBytes(st.cpu_percent);
            const memPercent = normalizeServerBytes(st.mem_percent);
            const diskPercent = normalizeServerBytes(st.disk_percent);
            const netSent = normalizeServerBytes(st.net_sent_kb_s);
            const netRecv = normalizeServerBytes(st.net_recv_kb_s);
            const networkPrimaryLabel = getNetworkPrimaryLabel(st);
            const codeMeterHtml = renderServerCodeMeterLine(st.codemeter);
            const hardwareExtraHtml = renderServerHardwareExtra(st, ctx);
            const storageHtml = renderServerStorageRows(st, ctx);
            const cpuLabel = compactCpuName(st.cpu_name);
            const hasStoredMetrics = !!(
                st.cpu_name ||
                st.motherboard ||
                st.mem_total ||
                st.mem_used ||
                st.disk_total ||
                st.disk_percent ||
                st.hardware_refreshed_at ||
                (Array.isArray(st.gpu_list) && st.gpu_list.length) ||
                (Array.isArray(st.storage_devices) && st.storage_devices.length) ||
                (Array.isArray(st.storage_filesystems) && st.storage_filesystems.length) ||
                st.codemeter
            );
            const offlineSnapshotHtml = (!m.is_online && hasStoredMetrics)
                ? `<div class="server-offline-snapshot">Agent未上报，以下为最后一次采集快照，不代表当前开关机状态</div>`
                : '';
            const showLastMetrics = !!(m.is_online || hasStoredMetrics || (diagnostic.reportOnline && diagnostic.hasRuntime));
            const metricsHtml = showLastMetrics
                ? `${statusMetaHtml}${diagnosticHtml}${offlineSnapshotHtml}<div class="hardware-info"><div class="hardware-item" title="${escapeHtml(st.cpu_name||'未获取到CPU')}"><span class="hardware-label">CPU</span><span class="hardware-value">${escapeHtml(st.cpu_name||'加载中...')}</span></div><div class="hardware-item" title="${escapeHtml(st.motherboard||'未获取到主板')}"><span class="hardware-label">主板</span><span class="hardware-value">${escapeHtml(st.motherboard||'加载中...')}</span></div>${st.mem_speed ? `<div class="hardware-item"><span class="hardware-label">频率</span><span class="hardware-value">${escapeHtml(st.mem_speed)} MHz</span></div>` : ''}${hardwareExtraHtml}</div><div class="metric-row"><div class="metric-label"><span title="${escapeHtml(st.cpu_name || '')}">CPU ${escapeHtml(cpuLabel)}</span><span>${formatServerMetric(cpuPercent)}</span></div><div class="progress-track"><div class="progress-fill ${getColor(cpuPercent)}" style="width:${Math.max(0, Math.min(100, cpuPercent))}%"></div></div></div><div class="metric-row"><div class="metric-label"><span>内存 (${escapeHtml(st.mem_used||0)}/${escapeHtml(st.mem_total||0)} GB)</span><span>${formatServerMetric(memPercent)}</span></div><div class="progress-track"><div class="progress-fill bg-blue" style="width:${Math.max(0, Math.min(100, memPercent))}%"></div></div></div>${gpuHtml}${storageHtml}<div class="server-network-line" title="${escapeHtml(networkPrimaryLabel)}"><span>网络 上/下</span><strong><span style="color:var(--brand-blue)">↑ ${formatNetworkMbps(netSent)}</span><span style="color:var(--success)">↓ ${formatNetworkMbps(netRecv)} Mbps</span></strong></div>${codeMeterHtml}`
                : `${statusMetaHtml}${diagnosticHtml}<div style="text-align:center; color:var(--text-sub); margin:14px 0;">该节点当前离线，等待自动重连上报。</div>`;
            const groupHtml = m.asset_group ? `<div style="margin-top:8px; font-size:12px; color:var(--brand-blue);">区域/分组: ${escapeHtml(m.asset_group)}</div>` : '';
            let remarkHtml = m.remark ? `<div style="margin-top:12px; font-size:12px; color:var(--text-sub); border-top:1px dashed rgba(255,255,255,0.1); padding-top:8px;">备注: ${escapeHtml(m.remark)}</div>` : '';
            remarkHtml = groupHtml + remarkHtml;
            const cardStateClass = m.is_online ? 'online' : (diagnostic.reportOnline ? 'warning' : 'offline');
            const controlClass = typeof ctx.getPermissionDisabledClass === 'function' ? ctx.getPermissionDisabledClass('server.control') : '';
            const controlAttrs = typeof ctx.getPermissionDisabledAttrs === 'function' ? ctx.getPermissionDisabledAttrs('server.control', '当前账号无服务器控制权限') : '';
            const wakeButton = `<button class="server-action-btn wake${controlClass}" ${controlAttrs} title="发送 Wake-on-LAN 唤醒包" onclick="wakeServer('${escapeHtml(m.mac)}')">唤醒</button>`;
            const moveButtons = `<div class="server-action-group order"><button class="server-action-btn icon${controlClass}" ${controlAttrs} title="上移" onclick="moveServer('${escapeHtml(m.mac)}', -1)">↑</button><button class="server-action-btn icon${controlClass}" ${controlAttrs} title="下移" onclick="moveServer('${escapeHtml(m.mac)}', 1)">↓</button></div>`;
            const redeployButton = diagnostic.needsRedeploy ? `<button class="server-action-btn redeploy" title="复制 Agent 重部署命令" onclick="copyDeployCommand()">重部署</button>` : '';
            const refreshButton = `<button class="server-action-btn refresh${controlClass}" ${controlAttrs} title="要求节点立即刷新采集" onclick="sendServerCmd('${escapeHtml(m.mac)}', 'refresh')">刷新</button>`;
            const restartButton = `<button class="server-action-btn restart${controlClass}" ${controlAttrs} title="重启节点，测试机实测约 50 秒恢复 SSH" onclick="sendServerCmd('${escapeHtml(m.mac)}', 'restart')">重启</button>`;
            const shutdownButton = `<button class="server-action-btn shutdown${controlClass}" ${controlAttrs} title="关闭节点；需要 WOL 或现场电源恢复" onclick="sendServerCmd('${escapeHtml(m.mac)}', 'shutdown')">关机</button>`;
            const offlineCommandHint = cardStateClass === 'offline'
                ? `<div class="server-command-disabled-note">节点离线时只保留唤醒入口；关机/重启需要 Agent 在线后才能确认送达。</div>`
                : '';
            const actionHtml = cardStateClass === 'offline'
                ? `${offlineCommandHint}<div class="server-compact-actions offline-only"><span class="spacer"></span>${wakeButton}</div>`
                : `<div class="server-compact-actions">${moveButtons}<span class="spacer"></span>${redeployButton}<div class="server-action-group power">${refreshButton}${restartButton}${shutdownButton}${wakeButton}</div></div>`;
            return `<div class="server-card ${cardStateClass} size-${escapeHtml(m.card_size || 'normal')}"><div class="server-title"><span>${escapeHtml(getServerDisplayName(m))}</span><span class="tag ${diagnostic.badgeClass}">${escapeHtml(diagnostic.badgeText)}</span></div><div class="server-ip" title="${escapeHtml(identityLine.title)}">${escapeHtml(identityLine.text)}</div>${renderServerCommandPending(pendingCommand)}${commandResultHtml}${metricsHtml}${remarkHtml}${actionHtml}</div>`;
        }

    function renderServerGroupedGrid(machines, context = {}) {
            const groupMap = new Map();
            machines.forEach(machine => {
                const groupName = getServerGroupName(machine);
                if (!groupMap.has(groupName)) groupMap.set(groupName, []);
                groupMap.get(groupName).push(machine);
            });
            return Array.from(groupMap.entries()).map(([groupName, rows]) => {
                const onlineCount = rows.filter(item => item.is_online).length;
                const warningCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item, context);
                    return diagnostic.level !== 'success' && !!diagnostic.reportOnline;
                }).length;
                const outdatedCount = rows.filter(item => isAgentVersionOutdated(item.agent_status || {}, context)).length;
                const offlineCount = rows.filter(item => {
                    const diagnostic = buildServerDiagnostic(item.agent_status || {}, item, context);
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
                    <div class="server-group-grid">${rows.map(row => renderServerCard(row, context)).join('')}</div>
                </section>`;
            }).join('');
        }



    const api = {
        buildServerDiagnostic,
        formatServerMetric,
        normalizeServerBytes,
        formatNetworkMbps,
        formatBytesGiB,
        compactHardwareName,
        compactCpuName,
        memoryChannelText,
        renderServerHardwareExtra,
        getStorageVolumeRows,
        renderServerStorageRows,
        getNetworkPrimaryLabel,
        normalizeDisplayMac,
        getServerPhysicalMac,
        getServerIdentityLine,
        isVirtualGpuName,
        compactGpuName,
        normalizeGpuIdentity,
        dedupeGpuRows,
        renderServerGpuList,
        getServerCompactGpuText,
        getServerCompactMetricClass,
        getServerCompactGroupName,
        getServerDisplayName,
        buildServerCompactGroups,
        isServerDashboardVisible,
        getServerCompactAlertText,
        getServerCompactTooltip,
        renderServerMetaStrip,
        renderServerAttention,
        getCodeMeterSerials,
        getCodeMeterLicenseLabel,
        parseCodeMeterExpiry,
        formatCodeMeterExpiry,
        hasCompanyCodeMeterLicense,
        getCodeMeterValidityText,
        getCodeMeterExpiryStatusFromLicenses,
        renderServerCodeMeterLine,
        getServerGroupName,
        isAgentVersionOutdated,
        getAgentUpdateHint,
        renderServerCommandPending,
        renderServerCommandResult,
        renderServerCard,
        renderServerGroupedGrid,
        getColor,
        formatServerTime,
        formatServerClockOffset,
        getServerClockOffsetClass,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.server-monitor', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/server-monitor.js',
        });
    }
})(window);
