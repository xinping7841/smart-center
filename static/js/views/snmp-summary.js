// AI_MODULE: snmp_summary
// AI_PURPOSE: 首页 SNMP 摘要轻量渲染，避免首屏强制加载完整 SNMP 详情模块。
// AI_BOUNDARY: 只负责首页卡片和基础统计；端口详情、NAS 盘位、VLAN 明细仍在 snmp.js 中懒加载。
// AI_DATA_FLOW: /api/snmp/status?compact=1 -> 首页网络与录像机摘要卡片。
// AI_RUNTIME: 首页默认加载；保持小体积和无设备副作用。
// AI_SEARCH_KEYWORDS: snmp, summary, dashboard, lazy-load, compact.

(function installSmartCenterSnmpSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.snmp = Object.assign({}, SmartCenter.snmp || {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || (value => String(value ?? ''));
    const getDeviceStatusMeta = utils.getDeviceStatusMeta || (status => ({
        level: status?.online ? 'online' : 'offline',
        chipClass: status?.online ? 'online' : 'error',
        text: status?.online ? '在线' : '离线',
        isOnlineLike: !!status?.online,
    }));
    const getCardStateClass = utils.getCardStateClass || (meta => (
        !meta || meta.level === 'offline' ? 'offline' : (meta.level === 'stale' || meta.level === 'error' ? 'warning' : '')
    ));

    function formatSnmpMetricValue(metric) {
        if (!metric || metric.value === undefined || metric.value === null || metric.value === '') return '--';
        const unit = metric.unit ? ` ${metric.unit}` : '';
        return `${metric.value}${unit}`;
    }

    function formatSnmpSummaryValue(value, suffix = '') {
        if (value === undefined || value === null || value === '' || value === '--') return '--';
        return `${value}${suffix}`;
    }

    function snmpProvidedText(value, fallback = '设备未提供') {
        if (value === undefined || value === null || value === '' || value === '--') return fallback;
        return String(value);
    }

    function compactSnmpText(value, maxLen = 88) {
        const text = String(value || '').trim();
        if (!text) return '--';
        if (text.length <= maxLen) return text;
        return `${text.slice(0, maxLen)}...`;
    }

    function getSnmpInterfaceKindText(kind) {
        const normalized = String(kind || '').trim().toLowerCase();
        const map = {
            wan: 'WAN',
            lan: 'LAN',
            physical: '物理口',
            bond: '聚合口',
            bridge: '桥接口',
            virtual: '虚拟口',
            other: '其他口',
        };
        return map[normalized] || '接口';
    }

    function hasSnmpUsableRate(row) {
        if (!row) return false;
        if (Number(row.total_rate_bps || 0) > 0) return true;
        const text = String(row.total_rate_text || row.traffic_text || '').trim();
        return !!text && text !== '--' && text !== '-- / --';
    }

    function getSnmpUsefulTrafficRows(summary, interfaceSummary, options = {}) {
        const sourceSummary = summary || {};
        const sourceInterface = interfaceSummary || sourceSummary.interface_summary || {};
        const includeZero = !!options.includeZero;
        const candidates = [
            ...(Array.isArray(sourceSummary.wan_top_rows) ? sourceSummary.wan_top_rows : []),
            ...(Array.isArray(sourceSummary.lan_top_rows) ? sourceSummary.lan_top_rows : []),
            ...(Array.isArray(sourceSummary.network_top_rows) ? sourceSummary.network_top_rows : []),
            ...(Array.isArray(sourceSummary.physical_top_rows) ? sourceSummary.physical_top_rows : []),
            ...(Array.isArray(sourceInterface.active_top_rows) ? sourceInterface.active_top_rows : []),
            ...(Array.isArray(sourceInterface.switch_port_rows) ? sourceInterface.switch_port_rows : []),
            ...(Array.isArray(sourceSummary.interface_rows) ? sourceSummary.interface_rows : []),
        ];
        const seen = new Set();
        return candidates
            .filter(row => {
                if (!row) return false;
                const key = `${row.index ?? ''}:${row.name || ''}`;
                if (seen.has(key)) return false;
                seen.add(key);
                return includeZero || hasSnmpUsableRate(row);
            })
            .sort((a, b) => Number(b.total_rate_bps || 0) - Number(a.total_rate_bps || 0));
    }

    function getSnmpInterfaceCountText(interfaceSummary, status = {}) {
        const summary = interfaceSummary || {};
        const total = summary.interface_total_count ?? status.if_number ?? summary.interface_sample_count ?? summary.up_count ?? '--';
        const sample = summary.interface_sample_count ?? (Array.isArray(summary.top_names) ? summary.top_names.length : null);
        if (total !== '--' && sample !== null && sample !== undefined && String(total) !== String(sample)) {
            return `${total} / 已采 ${sample}`;
        }
        return String(total);
    }

    function getSnmpInterfaceRoleText(interfaceSummary) {
        const summary = interfaceSummary || {};
        const parts = [
            `物理 ${summary.physical_count ?? 0}`,
            `聚合 ${summary.bond_count ?? 0}`,
            `桥接 ${summary.bridge_count ?? 0}`,
            `虚拟 ${summary.virtual_count ?? 0}`,
        ];
        const wanCount = Number(summary.wan_count || 0);
        const lanCount = Number(summary.lan_count || 0);
        if (wanCount || lanCount) parts.unshift(`WAN/LAN ${wanCount}/${lanCount}`);
        return parts.join(' · ');
    }

    function getSnmpBestThroughputText(interfaceSummary) {
        const summary = interfaceSummary || {};
        return summary.aggregate_total_rate_text && summary.aggregate_total_rate_text !== '--'
            ? summary.aggregate_total_rate_text
            : (summary.active_total_rate_text || '--');
    }

    function getSnmpBestThroughputDisplay(interfaceSummary) {
        const value = getSnmpBestThroughputText(interfaceSummary);
        return value && value !== '--' ? value : '采集中';
    }

    function getSnmpBestThroughputPair(interfaceSummary) {
        const summary = interfaceSummary || {};
        const inText = summary.aggregate_in_rate_text && summary.aggregate_in_rate_text !== '--'
            ? summary.aggregate_in_rate_text
            : (summary.active_in_rate_text || '--');
        const outText = summary.aggregate_out_rate_text && summary.aggregate_out_rate_text !== '--'
            ? summary.aggregate_out_rate_text
            : (summary.active_out_rate_text || '--');
        return `${inText} / ${outText}`;
    }

    function getSnmpDeviceTypeLabel(deviceType) {
        const normalized = String(deviceType || '').trim().toLowerCase();
        const labelMap = {
            nas: 'NAS 存储',
            router: '路由网关',
            switch: '交换机',
            firewall: '防火墙',
            server: '服务器',
            network: '网络设备',
        };
        return labelMap[normalized] || (normalized ? normalized.toUpperCase() : '网络设备');
    }

    function normalizeSnmpDeviceName(cfg, status) {
        const raw = String((cfg && (cfg.name || cfg.id)) || '').trim();
        const host = String((cfg && cfg.host) || '').trim();
        if (host === '192.168.50.254') return '飞牛 NAS';
        if (host === '192.168.30.145') return '威联通 NAS';
        if (host === '192.168.99.3') return '爱快网关';
        if (host === '192.168.99.1') return 'H3C Switch';
        if (/[�]|椋炵墰|濞佽仈|鐖卞揩/.test(raw)) {
            return status && status.sys_name ? String(status.sys_name) : raw;
        }
        return raw || '--';
    }

    function getSnmpFilterMeta(filterKey) {
        const key = String(filterKey || 'all').trim().toLowerCase() || 'all';
        const map = {
            all: { label: '全部设备', hint: '展示当前所有已启用网络设备', level: '' },
            critical: { label: '高风险设备', hint: '优先关注 critical 级设备', level: 'critical' },
            warning: { label: '中风险设备', hint: '重点跟进 warning 级设备', level: 'warning' },
            nas: { label: 'NAS 设备', hint: '聚焦 CPU / 内存 / 存储 / 网卡', level: '' },
            router: { label: '网关设备', hint: '聚焦 WAN / LAN / 总吞吐', level: '' },
            switch: { label: '交换机设备', hint: '聚焦端口 / 上联 / 异常', level: '' },
        };
        return map[key] || map.all;
    }

    function getSnmpSummaryCards(summaries) {
        const list = Array.isArray(summaries) ? summaries : [];
        const total = list.length;
        const online = list.filter(item => getDeviceStatusMeta(item.status || {}).isOnlineLike).length;
        const critical = list.filter(item => String(item.summary.risk_level || '').toLowerCase() === 'critical').length;
        const warning = list.filter(item => String(item.summary.risk_level || '').toLowerCase() === 'warning').length;
        const nasCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'nas').length;
        const routerCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'router').length;
        const switchCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'switch').length;
        return [
            { key: 'all', label: '设备总数', value: String(total), meta: `在线 ${online} / 离线 ${Math.max(0, total - online)}`, level: '' },
            { key: 'critical', label: '高风险', value: String(critical), meta: '优先处理 critical 设备', level: 'critical' },
            { key: 'warning', label: '中风险', value: String(warning), meta: '建议关注 warning 设备', level: 'warning' },
            { key: 'nas', label: 'NAS', value: String(nasCount), meta: '存储 / 负载 / 磁盘', level: '' },
            { key: 'router', label: '网关', value: String(routerCount), meta: 'WAN / LAN / 总吞吐', level: '' },
            { key: 'switch', label: '交换机', value: String(switchCount), meta: '端口 / 上联 / 异常', level: '' },
        ];
    }

    function filterSnmpConfigs(configs, cache, filterKey) {
        const key = String(filterKey || 'all').trim().toLowerCase() || 'all';
        const items = Array.isArray(configs) ? configs : [];
        if (key === 'all') return items;
        return items.filter(cfg => {
            const status = cache[cfg.id] || {};
            const summary = status.summary || {};
            const deviceType = String(summary.device_type || cfg.device_type || '').toLowerCase();
            const riskLevel = String(summary.risk_level || '').toLowerCase();
            if (key === 'critical' || key === 'warning') return riskLevel === key;
            return deviceType === key;
        });
    }

    function getSnmpMetricValue(customMetrics, metricName) {
        const target = String(metricName || '').trim().toLowerCase();
        const item = (Array.isArray(customMetrics) ? customMetrics : []).find(metric => String(metric?.name || '').trim().toLowerCase() === target);
        return item ? formatSnmpMetricValue(item) : '--';
    }

    function getSnmpMetricValueWithFallback(customMetrics, metricNames = [], summary = null) {
        const names = Array.isArray(metricNames) ? metricNames : [metricNames];
        for (let i = 0; i < names.length; i += 1) {
            const name = String(names[i] || '').trim();
            if (!name) continue;
            const fromCustom = getSnmpMetricValue(customMetrics, name);
            if (fromCustom !== '--') return fromCustom;
            if (summary && summary[name] !== undefined && summary[name] !== null && summary[name] !== '') {
                return formatSnmpSummaryValue(summary[name]);
            }
        }
        return '--';
    }

    function normalizeSnmpSwitchPortRow(row) {
        const item = Object.assign({}, row || {});
        const adminStatus = String(item.admin_status || '').trim();
        const operStatus = String(item.oper_status || '').trim();
        const speedBps = Number(item.speed_bps || 0);
        const nameText = String(item.name || '').toLowerCase();
        item.admin_up = item.admin_up !== undefined ? !!item.admin_up : adminStatus === '1';
        item.oper_up = item.oper_up !== undefined ? !!item.oper_up : operStatus === '1';
        item.oper_status_known = item.oper_status_known !== undefined ? !!item.oper_status_known : !!operStatus;
        if (!item.status_level) {
            item.status_level = item.oper_up
                ? 'up'
                : (item.admin_up && item.oper_status_known ? 'down' : (item.admin_up ? 'unknown' : 'disabled'));
        }
        item.is_uplink = item.is_uplink !== undefined
            ? !!item.is_uplink
            : (speedBps >= 10000000000 || /^(ten-gigabitethernet|xgigabitethernet|fortygige|hundredgige)/.test(nameText));
        item.error_total = Number(item.error_total ?? (Number(item.in_errors || 0) + Number(item.out_errors || 0)));
        item.discard_total = Number(item.discard_total ?? (Number(item.in_discards || 0) + Number(item.out_discards || 0)));
        item.error_delta_total = Number(item.error_delta_total || 0);
        item.discard_delta_total = Number(item.discard_delta_total || 0);
        item.learned_mac_count = Number(item.learned_mac_count || 0);
        item.learned_vlan_count = Number(item.learned_vlan_count || 0);
        return item;
    }

    function getSnmpSwitchPortRows(summary, interfaceSummary) {
        const sourceSummary = summary || {};
        const sourceInterface = interfaceSummary || {};
        const switchRows = Array.isArray(sourceInterface.switch_port_rows) ? sourceInterface.switch_port_rows.filter(Boolean) : [];
        if (switchRows.length) return switchRows.map(normalizeSnmpSwitchPortRow);
        const interfaceRows = Array.isArray(sourceSummary.interface_rows) ? sourceSummary.interface_rows.filter(Boolean) : [];
        const physicalRows = interfaceRows.filter(row => row && row.kind === 'physical');
        const fallbackRows = physicalRows.length ? physicalRows : interfaceRows;
        return fallbackRows.map(normalizeSnmpSwitchPortRow);
    }

    function getSnmpSwitchPortState(row) {
        const item = normalizeSnmpSwitchPortRow(row);
        const level = String(item.status_level || '').trim().toLowerCase();
        if (level === 'up') return { level: 'up' };
        if (level === 'down') return { level: 'down' };
        if (level === 'unknown') return { level: 'unknown' };
        return { level: 'disabled' };
    }

    function getSnmpSwitchDerivedStats(summary, interfaceSummary) {
        const sourceInterface = interfaceSummary || {};
        const rows = getSnmpSwitchPortRows(summary || {}, sourceInterface);
        const computedPhysicalCount = rows.length;
        const computedUpCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'up').length;
        const computedDownCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'down').length;
        const computedUnknownCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'unknown').length;
        const computedUplinkCount = rows.filter(row => !!row.is_uplink).length;
        const bridgePortMacRows = Array.isArray(sourceInterface.bridge_port_mac_rows) ? sourceInterface.bridge_port_mac_rows : [];
        return {
            rows,
            physicalCount: Number(sourceInterface.physical_count || 0) || computedPhysicalCount,
            upCount: Number(sourceInterface.physical_up_count || 0) || computedUpCount,
            downCount: Number(sourceInterface.physical_down_count || 0) || computedDownCount,
            unknownCount: Number(sourceInterface.physical_unknown_count || 0) || Number(sourceInterface.unknown_count || 0) || computedUnknownCount,
            uplinkCount: Number(sourceInterface.uplink_count || 0) || computedUplinkCount,
            bridgeVlanCount: Number(sourceInterface.bridge_vlan_count || 0) || (Array.isArray(sourceInterface.bridge_vlan_rows) ? sourceInterface.bridge_vlan_rows.length : 0),
            bridgeMacCount: Number(sourceInterface.bridge_mac_count || 0) || bridgePortMacRows.reduce((acc, row) => acc + Number(row?.mac_count || 0), 0),
            learnedMacCount: Number(sourceInterface.bridge_learned_mac_count || 0) || bridgePortMacRows.reduce((acc, row) => acc + Number(row?.mac_count || 0), 0),
        };
    }

    function formatSnmpBytesText(bytes) {
        const value = Number(bytes || 0);
        if (!Number.isFinite(value) || value <= 0) return '--';
        const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
        let num = value;
        let unitIndex = 0;
        while (num >= 1024 && unitIndex < units.length - 1) {
            num /= 1024;
            unitIndex += 1;
        }
        const precision = num >= 100 || unitIndex === 0 ? 0 : (num >= 10 ? 1 : 2);
        return `${num.toFixed(precision)} ${units[unitIndex]}`;
    }

    function getSnmpStorageRows(summary) {
        const primary = Array.isArray(summary?.storage_rows) && summary.storage_rows.length
            ? summary.storage_rows
            : (Array.isArray(summary?.storage_top_rows) ? summary.storage_top_rows : []);
        return primary.filter(row => row && row.descr);
    }

    function getSnmpStorageDisplayRows(summary, limit = 8) {
        const rows = getSnmpStorageRows(summary);
        const order = { critical: 0, warning: 1, normal: 2 };
        return rows.slice().sort((a, b) => {
            const levelDiff = (order[String(a?.alert_level || 'normal')] ?? 9) - (order[String(b?.alert_level || 'normal')] ?? 9);
            if (levelDiff !== 0) return levelDiff;
            const usedDiff = Number(b?.used_bytes || 0) - Number(a?.used_bytes || 0);
            if (usedDiff !== 0) return usedDiff;
            const pctDiff = Number(b?.usage_percent || 0) - Number(a?.usage_percent || 0);
            if (pctDiff !== 0) return pctDiff;
            return String(a?.descr || '').localeCompare(String(b?.descr || ''), 'zh-CN');
        }).slice(0, Math.max(1, Number(limit) || 8));
    }

    function getSnmpPrimaryStorageRow(summary) {
        return getSnmpStorageDisplayRows(summary, 1)[0] || null;
    }

    function summarizeSnmpStorageCapacity(summary) {
        const rows = getSnmpStorageRows(summary);
        const totals = rows.reduce((acc, row) => {
            acc.total += Number(row?.total_bytes || 0);
            acc.used += Number(row?.used_bytes || 0);
            return acc;
        }, { total: 0, used: 0 });
        const mode = String(summary?.storage_capacity_mode || '').trim().toLowerCase();
        const quotaMode = mode === 'qnap_quota' || rows.some(row => row?.quota_view);
        if (quotaMode) {
            return {
                mode: 'qnap_quota',
                rows,
                totalBytes: 0,
                quotaTotalBytes: totals.total,
                usedBytes: totals.used,
                percent: null,
                usedText: totals.used > 0 ? formatSnmpBytesText(totals.used) : '--',
                totalText: '配额不合计',
                quotaTotalText: totals.total > 0 ? formatSnmpBytesText(totals.total) : '--',
            };
        }
        const percent = totals.total > 0 ? Math.round((totals.used / totals.total) * 10000) / 100 : null;
        return {
            mode: 'standard',
            rows,
            totalBytes: totals.total,
            usedBytes: totals.used,
            percent,
            usedText: totals.used > 0 ? formatSnmpBytesText(totals.used) : '--',
            totalText: totals.total > 0 ? formatSnmpBytesText(totals.total) : '--',
        };
    }

    function getSnmpAlertLevel(level) {
        const normalized = String(level || '').trim().toLowerCase();
        if (normalized === 'critical') return 'critical';
        if (normalized === 'warning') return 'warning';
        return 'normal';
    }

    function getSnmpCapacityDisplay(summary) {
        const capacity = summarizeSnmpStorageCapacity(summary);
        if (capacity.mode === 'qnap_quota') {
            return {
                value: '配额视图',
                meta: `共享已用 ${capacity.usedText} · ${capacity.rows.length} 项 · 配额不合计`,
                level: '',
                capacity,
            };
        }
        const hasCapacity = capacity.percent !== null && capacity.totalBytes > 0;
        return {
            value: hasCapacity ? `${capacity.percent}%` : '采集中',
            meta: hasCapacity ? `${capacity.usedText} / ${capacity.totalText}` : `卷 ${summary?.storage_count ?? 0} · 等待容量字段`,
            level: Number(capacity.percent || 0) >= 92 ? 'critical' : (Number(capacity.percent || 0) >= 85 ? 'warning' : ''),
            capacity,
        };
    }

    function getSnmpPrimaryStorageDisplay(summary) {
        const row = getSnmpPrimaryStorageRow(summary);
        if (!row) return { value: '采集中', meta: `卷 ${summary?.storage_count ?? 0} · 等待容量字段`, level: '' };
        return {
            value: `${row.descr || '--'} ${row.usage_percent ?? '--'}%`,
            meta: `${row.used_text || '--'} / ${row.total_text || '--'}`,
            level: getSnmpAlertLevel(row.alert_level),
        };
    }

    function renderSnmpOverviewBar(configs, cache, filterKey = 'all', viewMode = 'page') {
        const items = Array.isArray(configs) ? configs.filter(cfg => cfg.visible !== false) : [];
        if (!items.length) return '';
        if (String(viewMode || 'page').trim().toLowerCase() === 'dashboard') return '';
        const summaries = items.map(cfg => ({ cfg, status: cache[cfg.id] || {}, summary: (cache[cfg.id] || {}).summary || {} }));
        const cards = getSnmpSummaryCards(summaries);
        return `<div class="snmp-summary-wrap">
            <div class="snmp-summary-head">
                <div class="snmp-summary-filter-tip">当前视图: <strong>${escapeHtml(getSnmpFilterMeta(filterKey).label)}</strong> · ${escapeHtml(getSnmpFilterMeta(filterKey).hint)}</div>
                <div class="snmp-summary-filter-tip">点击下方统计卡可切换筛选</div>
            </div>
            <div class="snmp-summary-bar">${cards.map(card => `
                <button type="button" class="snmp-summary-card ${card.key === filterKey ? `active ${card.level}` : ''}" data-snmp-filter="${escapeHtml(card.key)}">
                    <div class="label">${escapeHtml(card.label)}</div>
                    <div class="value">${escapeHtml(card.value)}</div>
                    <div class="meta">${escapeHtml(card.meta)}</div>
                </button>
            `).join('')}</div>
        </div>`;
    }

    function getSnmpDeviceIcon(deviceType) {
        const normalized = String(deviceType || '').trim().toLowerCase();
        if (normalized === 'nas') return '🗄';
        if (normalized === 'router') return '🌐';
        if (normalized === 'switch') return '🔀';
        if (normalized === 'server') return '🖥';
        return '📡';
    }

    function buildDashboardSnmpMetricItems(deviceType, summary, status, interfaceSummary, customMetrics = []) {
        const items = [];
        if (deviceType === 'router') {
            const routerCpuTemp = getSnmpMetricValueWithFallback(customMetrics, ['cpu_temperature_c', 'temperature_c'], summary);
            const routerConnections = getSnmpMetricValueWithFallback(customMetrics, ['network_connections', 'session_count', 'nat_sessions'], summary);
            const trafficRows = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true });
            const primaryLink = trafficRows[0];
            items.push(
                { label: '总吞吐', value: getSnmpBestThroughputDisplay(interfaceSummary), meta: `${getSnmpBestThroughputPair(interfaceSummary)}` },
                { label: '主链路', value: primaryLink ? (primaryLink.name || '--') : '--', meta: primaryLink ? compactSnmpText(`${getSnmpInterfaceKindText(primaryLink.kind)} · ${primaryLink.total_rate_text || primaryLink.traffic_text || '--'}`, 26) : compactSnmpText(getSnmpInterfaceRoleText(interfaceSummary), 26) },
                { label: 'CPU / 内存', value: `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%`, meta: `温度 ${snmpProvidedText(routerCpuTemp)}`, level: Number(summary.cpu_peak_percent || 0) >= 80 ? 'warning' : getSnmpAlertLevel(summary.memory_alert_level) },
                { label: '连接 / 告警', value: `${snmpProvidedText(routerConnections)} / ${(summary.alert_counts || {}).warning ?? 0}`, meta: `异常口 ${(interfaceSummary.error_port_count ?? 0) + (interfaceSummary.discard_port_count ?? 0)}`, level: Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0 ? 'warning' : '' }
            );
            return items;
        }
        if (deviceType === 'switch') {
            const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
            items.push(
                { label: '接口总数', value: getSnmpInterfaceCountText(interfaceSummary, status), meta: `在线 / 离线 / 未采到 ${switchStats.upCount} / ${switchStats.downCount} / ${switchStats.unknownCount}`, level: Number(switchStats.downCount || 0) > 0 ? 'warning' : '' },
                { label: '上联 / 忙碌', value: `${switchStats.uplinkCount} / ${interfaceSummary.busy_port_count ?? 0}`, meta: `总吞吐 ${getSnmpBestThroughputDisplay(interfaceSummary)}` },
                { label: '新增异常', value: `${interfaceSummary.delta_error_port_count ?? 0} / ${interfaceSummary.delta_discard_port_count ?? 0}`, meta: `累计 ${(interfaceSummary.error_port_count ?? 0) + (interfaceSummary.discard_port_count ?? 0)}`, level: Number(interfaceSummary.delta_discard_port_count || 0) > 0 ? 'critical' : (Number(interfaceSummary.delta_error_port_count || 0) > 0 ? 'warning' : '') },
                { label: 'MAC / VLAN', value: `${switchStats.bridgeMacCount} / ${switchStats.bridgeVlanCount}`, meta: `学习 ${switchStats.learnedMacCount}` }
            );
            return items;
        }
        const capacityDisplay = getSnmpCapacityDisplay(summary);
        const primaryStorageDisplay = getSnmpPrimaryStorageDisplay(summary);
        const capacity = summarizeSnmpStorageCapacity(summary);
        items.push(
            { label: capacity.mode === 'qnap_quota' ? '共享/LUN 配额' : '容量合计', value: capacityDisplay.value, meta: capacityDisplay.meta, level: capacityDisplay.level },
            { label: capacity.mode === 'qnap_quota' ? '最大占用项' : '最大卷', value: primaryStorageDisplay.value, meta: primaryStorageDisplay.meta, level: primaryStorageDisplay.level },
            { label: 'CPU / 内存', value: `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%`, meta: `负载 ${summary.ucd_load_1 ?? '--'} / ${summary.ucd_load_5 ?? '--'}`, level: Number(summary.cpu_peak_percent || 0) >= 80 ? 'warning' : getSnmpAlertLevel(summary.memory_alert_level) },
            { label: '网络吞吐', value: getSnmpBestThroughputDisplay(interfaceSummary), meta: `${getSnmpBestThroughputPair(interfaceSummary)}` },
            { label: '磁盘 / 硬件', value: `${summary.disk_count ?? 0} / ${(Array.isArray(summary.gpu_metrics) ? summary.gpu_metrics.length : 0)}`, meta: `风扇 ${summary.fan_count ?? 0} · 进程 ${summary.process_count ?? '--'}` }
        );
        return items;
    }

    function renderDashboardSnmpCard(cfg, status) {
        const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
        const online = statusMeta.isOnlineLike;
        const version = String((status.version || cfg.version || 'v2c')).toUpperCase();
        const summary = status.summary || {};
        const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
        const interfaceSummary = summary.interface_summary || {};
        const customMetrics = Array.isArray(status.custom_metrics) ? status.custom_metrics : [];
        const displayName = normalizeSnmpDeviceName(cfg, status);
        const deviceTypeLabel = getSnmpDeviceTypeLabel(deviceType);
        const deviceIcon = getSnmpDeviceIcon(deviceType);
        const updatedAt = status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--';
        const riskLevel = String(summary.risk_level || (online ? 'normal' : 'warning')).trim().toLowerCase();
        const riskText = riskLevel === 'critical' ? '高风险' : (riskLevel === 'warning' ? '关注中' : '稳定');
        const healthScore = summary.health_score !== undefined && summary.health_score !== null ? String(summary.health_score) : '--';
        const alertCounts = summary.alert_counts || {};
        const cardClass = getCardStateClass(statusMeta) || (online ? riskLevel : 'offline');
        const metrics = buildDashboardSnmpMetricItems(deviceType, summary, status, interfaceSummary, customMetrics);
        const note = status.error
            ? `异常: ${String(status.error)}`
            : statusMeta.note || (online ? `最近采集 ${updatedAt}` : '设备离线或暂未采到完整指标');
        return `<div class="snmp-dashboard-card ${escapeHtml(cardClass)} ${online ? '' : 'offline'}">
            <div class="snmp-dashboard-head">
                <div class="snmp-dashboard-main">
                    <div class="snmp-device-icon ${escapeHtml(deviceType)}">${deviceIcon}</div>
                    <div class="snmp-dashboard-body">
                        <div class="snmp-dashboard-kicker">
                            <span class="ups-chip">${escapeHtml(deviceTypeLabel)}</span>
                            <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                            <span class="ups-chip">${escapeHtml(version)}</span>
                        </div>
                        <div class="snmp-dashboard-title">${escapeHtml(displayName)}</div>
                        <div class="snmp-dashboard-subtitle">${escapeHtml(cfg.host || '--')} · ${escapeHtml(compactSnmpText(`${cfg.brand || '--'} / ${cfg.model || '--'}`, 22))}</div>
                    </div>
                </div>
                <div class="snmp-dashboard-status">
                    <span class="ups-chip ${riskLevel === 'critical' ? 'error' : (riskLevel === 'warning' ? 'warning' : '')}">${escapeHtml(riskText)}</span>
                    <span class="ups-chip">${escapeHtml(updatedAt)}</span>
                </div>
            </div>
            <div class="snmp-dashboard-score">
                <div>
                    <div class="snmp-dashboard-score-label">健康评分</div>
                    <div class="snmp-dashboard-score-value">${escapeHtml(healthScore)}</div>
                </div>
                <div class="snmp-dashboard-score-meta">严重 ${escapeHtml(String(alertCounts.critical ?? 0))} · 告警 ${escapeHtml(String(alertCounts.warning ?? 0))} · 提示 ${escapeHtml(String(alertCounts.info ?? 0))}</div>
            </div>
            <div class="snmp-dashboard-metric-grid">${metrics.map(item => `
                <div class="snmp-dashboard-metric ${escapeHtml(item.level || '')}">
                    <div class="label">${escapeHtml(item.label || '--')}</div>
                    <div class="value">${escapeHtml(String(item.value ?? '--'))}</div>
                    ${item.meta ? `<div class="meta">${escapeHtml(String(item.meta))}</div>` : ''}
                </div>
            `).join('')}</div>
            <div class="snmp-dashboard-note">${escapeHtml(note)}</div>
        </div>`;
    }

    function bindSnmpDetailToggles() {
        // 首页不会展开 SNMP 详情；完整详情页加载 snmp.js 后会覆盖该函数。
    }

    const api = {
        formatSnmpMetricValue,
        formatSnmpSummaryValue,
        snmpProvidedText,
        compactSnmpText,
        getSnmpInterfaceKindText,
        hasSnmpUsableRate,
        getSnmpUsefulTrafficRows,
        getSnmpInterfaceCountText,
        getSnmpInterfaceRoleText,
        getSnmpBestThroughputText,
        getSnmpBestThroughputDisplay,
        getSnmpBestThroughputPair,
        getSnmpDeviceTypeLabel,
        normalizeSnmpDeviceName,
        getSnmpFilterMeta,
        getSnmpSummaryCards,
        filterSnmpConfigs,
        getSnmpMetricValue,
        getSnmpMetricValueWithFallback,
        normalizeSnmpSwitchPortRow,
        getSnmpSwitchPortRows,
        getSnmpSwitchPortState,
        getSnmpSwitchDerivedStats,
        getSnmpCapacityDisplay,
        getSnmpPrimaryStorageDisplay,
        renderSnmpOverviewBar,
        bindSnmpDetailToggles,
        getSnmpStorageRows,
        getSnmpStorageDisplayRows,
        getSnmpPrimaryStorageRow,
        summarizeSnmpStorageCapacity,
        formatSnmpBytesText,
        getSnmpAlertLevel,
        getSnmpDeviceIcon,
        buildDashboardSnmpMetricItems,
        renderDashboardSnmpCard,
    };

    Object.assign(state, api, { summaryModuleLoaded: true });
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.snmp_summary', {
            kind: 'view-summary',
            exports: Object.keys(api),
            source: 'static/js/views/snmp-summary.js',
        });
    }
})(window);
