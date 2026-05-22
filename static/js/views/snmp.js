(function installSmartCenterSnmp(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const state = SmartCenter.snmp = Object.assign({}, SmartCenter.snmp || {});

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
            nvr: '录像机',
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
            all: { label: '全部设备', hint: '展示当前所有已启用网络与录像机设备', level: '' },
            critical: { label: '高风险设备', hint: '优先关注 critical 级设备', level: 'critical' },
            warning: { label: '中风险设备', hint: '重点跟进 warning 级设备', level: 'warning' },
            nas: { label: 'NAS 设备', hint: '聚焦 CPU / 内存 / 存储 / 网卡', level: '' },
            router: { label: '网关设备', hint: '聚焦 WAN / LAN / 总吞吐', level: '' },
            switch: { label: '交换机设备', hint: '聚焦端口 / 上联 / 异常', level: '' },
            nvr: { label: '录像机设备', hint: '聚焦通道、硬盘、固件与预览', level: '' },
        };
        return map[key] || map.all;
    }

    function getSnmpSummaryCards(summaries) {
        const list = Array.isArray(summaries) ? summaries : [];
        const total = list.length;
        const getStatusMeta = typeof global.getDeviceStatusMeta === 'function'
            ? global.getDeviceStatusMeta
            : status => ({ isOnlineLike: !!status?.online });
        const online = list.filter(item => getStatusMeta(item.status || {}).isOnlineLike).length;
        const critical = list.filter(item => String(item.summary.risk_level || '').toLowerCase() === 'critical').length;
        const warning = list.filter(item => String(item.summary.risk_level || '').toLowerCase() === 'warning').length;
        const nasCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'nas').length;
        const routerCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'router').length;
        const switchCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'switch').length;
        const nvrCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'nvr').length;
        return [
            { key: 'all', label: '设备总数', value: String(total), meta: `在线 ${online} / 离线 ${Math.max(0, total - online)}`, level: '' },
            { key: 'critical', label: '高风险', value: String(critical), meta: '优先处理 critical 设备', level: 'critical' },
            { key: 'warning', label: '中风险', value: String(warning), meta: '建议关注 warning 设备', level: 'warning' },
            { key: 'nas', label: 'NAS', value: String(nasCount), meta: '存储 / 负载 / 磁盘', level: '' },
            { key: 'router', label: '网关', value: String(routerCount), meta: 'WAN / LAN / 总吞吐', level: '' },
            { key: 'switch', label: '交换机', value: String(switchCount), meta: '端口 / 上联 / 异常', level: '' },
            { key: 'nvr', label: '录像机', value: String(nvrCount), meta: '通道 / 硬盘 / 预览', level: '' },
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

    function getSnmpMetricLabel(metricName) {
        const normalized = String(metricName || '').trim().toLowerCase();
        const labelMap = {
            hr_memory_size_kb: '内存总量',
            hr_system_processes: '进程数',
            hr_system_users: '在线用户',
            ucd_load_1: 'Load 1',
            ucd_load_5: 'Load 5',
            ucd_load_15: 'Load 15',
            ucd_mem_total_kb: 'UCD 内存总量',
            ucd_mem_available_kb: 'UCD 可用内存',
            ucd_mem_cached_kb: 'UCD Cache',
            ucd_mem_buffer_kb: 'UCD Buffer',
            vendor_memory_total: '厂商内存总量',
            vendor_memory_free: '厂商空闲内存',
            if_number: '接口数量',
            cpu_usage_percent: 'CPU 使用率',
            cpu_user_percent: 'CPU 用户占比',
            cpu_system_percent: 'CPU 系统占比',
            cpu_idle_percent: 'CPU 空闲占比',
            temperature_c: '温度',
            cpu_temperature_c: 'CPU 温度',
            session_count: '会话数',
            network_connections: '网络连接数',
            ap_count: 'AP 数量',
            online_clients: '在线终端',
            nat_sessions: 'NAT 会话',
        };
        return labelMap[normalized] || (metricName || 'metric');
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
        if (!item.status_text) {
            item.status_text = item.status_level === 'up'
                ? '在线'
                : (item.status_level === 'down' ? '离线' : (item.status_level === 'unknown' ? '状态未采到' : '管理关闭'));
        }
        item.is_uplink = item.is_uplink !== undefined
            ? !!item.is_uplink
            : (speedBps >= 10000000000 || /^(ten-gigabitethernet|xgigabitethernet|fortygige|hundredgige)/.test(nameText));
        item.in_rate_text = item.in_rate_text || '--';
        item.out_rate_text = item.out_rate_text || '--';
        item.total_rate_text = item.total_rate_text || '--';
        item.traffic_text = item.traffic_text || `${item.in_rate_text} / ${item.out_rate_text}`;
        item.utilization_text = item.utilization_text || '--';
        item.in_bytes_text = item.in_bytes_text || '--';
        item.out_bytes_text = item.out_bytes_text || '--';
        item.error_total = Number(item.error_total ?? (Number(item.in_errors || 0) + Number(item.out_errors || 0)));
        item.discard_total = Number(item.discard_total ?? (Number(item.in_discards || 0) + Number(item.out_discards || 0)));
        item.error_delta_total = Number(item.error_delta_total || 0);
        item.discard_delta_total = Number(item.discard_delta_total || 0);
        item.learned_mac_count = Number(item.learned_mac_count || 0);
        item.learned_vlan_count = Number(item.learned_vlan_count || 0);
        const pvidValue = Number(item.pvid || 0);
        const pvidNameRaw = String(item.pvid_name || '').trim();
        item.pvid = Number.isFinite(pvidValue) && pvidValue > 0 ? pvidValue : null;
        item.pvid_name = pvidNameRaw && pvidNameRaw !== '--'
            ? pvidNameRaw
            : (item.pvid ? `VLAN ${item.pvid}` : '--');
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
        if (level === 'up') return { level: 'up', text: '在线', chipClass: 'online', cardClass: 'up', warning: false };
        if (level === 'down') return { level: 'down', text: '离线', chipClass: 'error', cardClass: 'down', warning: true };
        if (level === 'unknown') return { level: 'unknown', text: '状态未采到', chipClass: 'warning', cardClass: 'unknown', warning: false };
        return { level: 'disabled', text: '管理关闭', chipClass: '', cardClass: 'disabled', warning: false };
    }

    function getSnmpSwitchDerivedStats(summary, interfaceSummary) {
        const sourceSummary = summary || {};
        const sourceInterface = interfaceSummary || {};
        const rows = getSnmpSwitchPortRows(sourceSummary, sourceInterface);
        const computedPhysicalCount = rows.length;
        const computedUpCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'up').length;
        const computedDownCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'down').length;
        const computedUnknownCount = rows.filter(row => getSnmpSwitchPortState(row).level === 'unknown').length;
        const computedUplinkCount = rows.filter(row => !!row.is_uplink).length;
        const physicalCount = Number(sourceInterface.physical_count || 0) || computedPhysicalCount;
        const upCount = Number(sourceInterface.physical_up_count || 0) || computedUpCount;
        const downCount = Number(sourceInterface.physical_down_count || 0) || computedDownCount;
        const unknownCount = Number(sourceInterface.physical_unknown_count || 0) || Number(sourceInterface.unknown_count || 0) || computedUnknownCount;
        const uplinkCount = Number(sourceInterface.uplink_count || 0) || computedUplinkCount;
        const bridgeVlanRows = Array.isArray(sourceInterface.bridge_vlan_rows) ? sourceInterface.bridge_vlan_rows : [];
        const bridgePortMacRows = Array.isArray(sourceInterface.bridge_port_mac_rows) ? sourceInterface.bridge_port_mac_rows : [];
        const bridgeVlanCount = Number(sourceInterface.bridge_vlan_count || 0) || bridgeVlanRows.length;
        const bridgeMacCount = Number(sourceInterface.bridge_mac_count || 0)
            || bridgePortMacRows.reduce((acc, row) => acc + Number(row?.mac_count || 0), 0);
        const learnedMacCount = Number(sourceInterface.bridge_learned_mac_count || 0)
            || bridgePortMacRows.reduce((acc, row) => acc + Number(row?.mac_count || 0), 0);
        return {
            rows,
            physicalCount,
            upCount,
            downCount,
            unknownCount,
            uplinkCount,
            bridgeVlanCount,
            bridgeMacCount,
            learnedMacCount,
        };
    }

    function buildSnmpSwitchVlanPortHighlights(summary, interfaceSummary, maxCount = 4) {
        const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
        const rows = switchStats.rows;
        if (!rows.length) return [];
        const normalizedMax = Math.max(1, Number(maxCount || 4));
        const rankedRows = rows
            .filter(row => Number(row.pvid || 0) > 0 || Number(row.learned_vlan_count || 0) > 0 || Number(row.learned_mac_count || 0) > 0)
            .sort((a, b) => {
                const scoreA = Number(a.learned_mac_count || 0) * 100 + Number(a.learned_vlan_count || 0);
                const scoreB = Number(b.learned_mac_count || 0) * 100 + Number(b.learned_vlan_count || 0);
                if (scoreA !== scoreB) return scoreB - scoreA;
                return Number(a.index || 99999) - Number(b.index || 99999);
            })
            .slice(0, normalizedMax);
        return rankedRows.map(row => ({
            label: `${row.name || '--'} (#${row.index ?? '--'})`,
            meta: `PVID ${row.pvid_name || '--'} · VLAN ${row.learned_vlan_count ?? 0}`,
            value: `MAC ${row.learned_mac_count ?? 0}`,
        }));
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
        getSnmpMetricLabel,
        getSnmpMetricValue,
        getSnmpMetricValueWithFallback,
        normalizeSnmpSwitchPortRow,
        getSnmpSwitchPortRows,
        getSnmpSwitchPortState,
        getSnmpSwitchDerivedStats,
        buildSnmpSwitchVlanPortHighlights,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.snmp', {
            kind: 'view',
            exports: Object.keys(api),
            source: 'static/js/views/snmp.js',
        });
    }
})(window);
