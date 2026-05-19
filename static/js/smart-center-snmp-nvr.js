        function renderUpsCards() {
            const dashboardGrid = document.getElementById('dashboard-ups-grid');
            const pageGrid = document.getElementById('ups-page-grid');
            const dashboardHtml = upsConfigs.length
                ? upsConfigs.filter(cfg => cfg.visible !== false).map(cfg => renderDashboardUpsCard(cfg, upsStatusCache[cfg.id] || {})).join('')
                : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置 UPS 设备</div>';
            const pageHtml = upsConfigs.length
                ? upsConfigs.filter(cfg => cfg.visible !== false).map(cfg => renderUpsCard(cfg, upsStatusCache[cfg.id] || {})).join('')
                : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置 UPS 设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid) pageGrid.innerHTML = pageHtml;
            renderDashboardUpsCompact();
        }
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
                other: '其他口'
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
                ...(Array.isArray(sourceSummary.interface_rows) ? sourceSummary.interface_rows : [])
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
                `虚拟 ${summary.virtual_count ?? 0}`
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
            if (!row) {
                return { value: '采集中', meta: `卷 ${summary?.storage_count ?? 0} · 等待容量字段`, level: '' };
            }
            return {
                value: `${row.descr || '--'} ${row.usage_percent ?? '--'}%`,
                meta: `${row.used_text || '--'} / ${row.total_text || '--'}`,
                level: getSnmpAlertLevel(row.alert_level),
            };
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
                network: '网络设备'
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
                nvr: { label: '录像机设备', hint: '聚焦通道、硬盘、固件与预览', level: '' }
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
            const nvrCount = list.filter(item => String(item.summary.device_type || item.cfg.device_type || '').toLowerCase() === 'nvr').length;
            return [
                { key: 'all', label: '设备总数', value: String(total), meta: `在线 ${online} / 离线 ${Math.max(0, total - online)}`, level: '' },
                { key: 'critical', label: '高风险', value: String(critical), meta: '优先处理 critical 设备', level: 'critical' },
                { key: 'warning', label: '中风险', value: String(warning), meta: '建议关注 warning 设备', level: 'warning' },
                { key: 'nas', label: 'NAS', value: String(nasCount), meta: '存储 / 负载 / 磁盘', level: '' },
                { key: 'router', label: '网关', value: String(routerCount), meta: 'WAN / LAN / 总吞吐', level: '' },
                { key: 'switch', label: '交换机', value: String(switchCount), meta: '端口 / 上联 / 异常', level: '' },
                { key: 'nvr', label: '录像机', value: String(nvrCount), meta: '通道 / 硬盘 / 预览', level: '' }
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
                if (key === 'critical' || key === 'warning') {
                    return riskLevel === key;
                }
                return deviceType === key;
            });
        }
        function renderSnmpOverviewBar(configs, cache, filterKey = 'all', viewMode = 'page') {
            const items = Array.isArray(configs) ? configs.filter(cfg => cfg.visible !== false) : [];
            if (!items.length) {
                return '';
            }
            const summaries = items.map(cfg => ({ cfg, status: cache[cfg.id] || {}, summary: (cache[cfg.id] || {}).summary || {} }));
            const cards = getSnmpSummaryCards(summaries);
            const modeClass = String(viewMode || 'page').trim().toLowerCase() === 'dashboard' ? ' dashboard' : '';
            if (modeClass.includes('dashboard')) {
                return '';
            }
            return `<div class="snmp-summary-wrap${modeClass}">
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
                nat_sessions: 'NAT 会话'
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
            if (switchRows.length) {
                return switchRows.map(normalizeSnmpSwitchPortRow);
            }
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
                learnedMacCount
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
                value: `MAC ${row.learned_mac_count ?? 0}`
            }));
        }
        function renderSnmpMetricChips(customMetrics, summary) {
            const builtInNames = new Set(['hr_memory_size_kb', 'hr_system_processes', 'hr_system_users']);
            const filtered = (Array.isArray(customMetrics) ? customMetrics : []).filter(metric => {
                const name = String(metric?.name || '').trim().toLowerCase();
                if (!name) return false;
                if (builtInNames.has(name)) return false;
                const value = metric?.value;
                return value !== undefined && value !== null && value !== '';
            });
            if (!filtered.length) {
                return '<span class="ups-alert-chip warning" style="color:#bbf7d0;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.34);">当前无额外自定义指标</span>';
            }
            return filtered.slice(0, 6).map(metric => `<span class="ups-alert-chip warning" style="color:#bfdbfe;background:rgba(59,130,246,0.14);border:1px solid rgba(59,130,246,0.28);">${escapeHtml(getSnmpMetricLabel(metric.name))}: ${escapeHtml(String(formatSnmpMetricValue(metric)))}</span>`).join('');
        }
        function renderSnmpInlineMetrics(items, emptyText = '当前无可展示指标') {
            const list = Array.isArray(items) ? items.filter(item => item && (item.label || item.value || item.meta)) : [];
            if (!list.length) {
                return `<div class="snmp-mini-empty">${escapeHtml(emptyText)}</div>`;
            }
            return `<div class="snmp-main-metric-grid">${list.map(item => `
                <div class="snmp-main-metric ${escapeHtml(item.level || '')}">
                    <div class="snmp-main-metric-label">${escapeHtml(item.label || '--')}</div>
                    <div class="snmp-main-metric-value">${escapeHtml(String(item.value ?? '--'))}</div>
                    ${item.meta ? `<div class="snmp-main-metric-meta">${escapeHtml(String(item.meta))}</div>` : ''}
                </div>
            `).join('')}</div>`;
        }
        function renderSnmpMiniList(items, options = {}) {
            const list = Array.isArray(items) ? items.filter(item => item && (item.label || item.value || item.meta)) : [];
            const emptyText = options.emptyText || '当前暂无摘要';
            const maxCount = Number(options.maxCount || 0) > 0 ? Number(options.maxCount) : list.length;
            if (!list.length) {
                return `<div class="snmp-mini-empty">${escapeHtml(emptyText)}</div>`;
            }
            return `<div class="snmp-mini-list">${list.slice(0, maxCount).map(item => `
                <div class="snmp-mini-item ${escapeHtml(item.level || '')}">
                    <div class="snmp-mini-label-wrap">
                        <div class="snmp-mini-label">${escapeHtml(item.label || '--')}</div>
                        ${item.meta ? `<div class="snmp-mini-meta">${escapeHtml(String(item.meta))}</div>` : ''}
                    </div>
                    <div class="snmp-mini-value">${escapeHtml(String(item.value ?? '--'))}</div>
                </div>
            `).join('')}</div>`;
        }
        function renderSnmpFocusPanel(title, note, bodyHtml, options = {}) {
            if (!bodyHtml) return '';
            return `<div class="snmp-focus-panel ${options.wide ? 'wide' : ''}">
                <div class="snmp-focus-head">
                    <div class="snmp-focus-title">${escapeHtml(title || '--')}</div>
                    ${note ? `<div class="snmp-focus-note">${escapeHtml(note)}</div>` : ''}
                </div>
                ${bodyHtml}
            </div>`;
        }
        function renderSnmpInlineDetails(title, meta, bodyHtml, open = false) {
            if (!bodyHtml) return '';
            return `<details class="snmp-inline-details" ${open ? 'open' : ''}>
                <summary>
                    <div class="snmp-inline-details-title">${escapeHtml(title || '--')}</div>
                    ${meta ? `<div class="snmp-inline-details-meta">${escapeHtml(meta)}</div>` : ''}
                </summary>
                <div class="snmp-inline-details-body">${bodyHtml}</div>
            </details>`;
        }
        function buildSnmpDetailStateKey(deviceId, sectionKey) {
            return `${String(deviceId || '--')}::${String(sectionKey || 'default')}`;
        }
        function renderPersistedSnmpDetails(deviceId, sectionKey, title, meta, bodyHtml, open = false, className = 'snmp-inline-details') {
            if (!bodyHtml) return '';
            const stateKey = buildSnmpDetailStateKey(deviceId, sectionKey);
            const isOpen = Object.prototype.hasOwnProperty.call(snmpOpenDetailsState, stateKey) ? !!snmpOpenDetailsState[stateKey] : !!open;
            return `<details class="${escapeHtml(className)}" data-snmp-detail-key="${escapeHtml(stateKey)}" ${isOpen ? 'open' : ''}>
                <summary>
                    <div class="snmp-inline-details-title">${escapeHtml(title || '--')}</div>
                    ${meta ? `<div class="snmp-inline-details-meta">${escapeHtml(meta)}</div>` : ''}
                </summary>
                <div class="snmp-inline-details-body">${bodyHtml}</div>
            </details>`;
        }
        function bindSnmpDetailToggles(scopeEl) {
            const root = scopeEl || document;
            root.querySelectorAll('details[data-snmp-detail-key]').forEach(detail => {
                if (detail.dataset.snmpToggleBound === '1') return;
                detail.dataset.snmpToggleBound = '1';
                detail.addEventListener('toggle', () => {
                    const key = String(detail.getAttribute('data-snmp-detail-key') || '').trim();
                    if (key) snmpOpenDetailsState[key] = detail.open;
                });
            });
        }
        function syncSnmpSelectedDeviceToUrl(deviceId = '') {
            try {
                const url = new URL(window.location.href);
                const safeDeviceId = String(deviceId || '').trim();
                if (safeDeviceId) {
                    url.searchParams.set('snmp_device', safeDeviceId);
                } else {
                    url.searchParams.delete('snmp_device');
                }
                window.history.replaceState(null, '', url.toString());
            } catch (_) {}
        }
        function restoreSnmpSelectedDeviceFromUrl() {
            try {
                const params = new URLSearchParams(window.location.search || '');
                snmpSelectedDeviceId = String(params.get('snmp_device') || params.get('device') || '').trim();
            } catch (_) {
                snmpSelectedDeviceId = '';
            }
        }
        function openSnmpDeviceDetail(deviceId) {
            const safeDeviceId = String(deviceId || '').trim();
            if (!safeDeviceId) return;
            snmpSelectedDeviceId = safeDeviceId;
            syncSnmpSelectedDeviceToUrl(safeDeviceId);
            renderSnmpCards({ mode: 'full', renderDetailPage: true });
        }
        function closeSnmpDeviceDetail() {
            snmpSelectedDeviceId = '';
            syncSnmpSelectedDeviceToUrl('');
            renderSnmpCards({ mode: 'full', renderDetailPage: true });
        }
        function bindSnmpOverviewCardActions(scopeEl) {
            const root = scopeEl || document;
            root.querySelectorAll('[data-snmp-device-card]').forEach(card => {
                if (card.dataset.snmpOpenBound === '1') return;
                card.dataset.snmpOpenBound = '1';
                const open = () => openSnmpDeviceDetail(card.getAttribute('data-snmp-device-id'));
                card.addEventListener('click', event => {
                    if (event.target && event.target.closest && event.target.closest('button[data-snmp-filter]')) return;
                    open();
                });
                card.addEventListener('keydown', event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        open();
                    }
                });
            });
            root.querySelectorAll('[data-snmp-back-overview]').forEach(btn => {
                if (btn.dataset.snmpBackBound === '1') return;
                btn.dataset.snmpBackBound = '1';
                btn.addEventListener('click', closeSnmpDeviceDetail);
            });
        }
        function summarizeSnmpPayload(payload) {
            const configs = getNetworkMonitorConfigs();
            return configs.map(cfg => {
                const status = (payload || {})[cfg.id] || {};
                const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
                const summary = status.summary || {};
                const interfaceSummary = summary.interface_summary || {};
                return [
                    cfg.id,
                    statusMeta.level,
                    statusMeta.isOnlineLike ? 1 : 0,
                    status.updated_at || '',
                    status.error || '',
                    summary.risk_level || '',
                    summary.health_score ?? '',
                    (summary.alert_counts || {}).warning ?? 0,
                    (summary.alert_counts || {}).critical ?? 0,
                    interfaceSummary.physical_up_count ?? '',
                    interfaceSummary.physical_down_count ?? '',
                    interfaceSummary.aggregate_total_rate_text || '',
                    summary.cpu_avg_percent ?? '',
                    summary.memory_usage_percent ?? '',
                    summary.channel_online ?? '',
                    summary.channel_total ?? '',
                    summary.hdd_error_count ?? ''
                ].join('|');
            }).join('~');
        }
        function getNetworkMonitorConfigs() {
            return [
                ...(Array.isArray(snmpConfigs) ? snmpConfigs : []).map(cfg => Object.assign({ monitor_kind: 'snmp' }, cfg)),
                ...(Array.isArray(nvrConfigs) ? nvrConfigs : []).map(cfg => Object.assign({ monitor_kind: 'nvr', device_type: 'nvr' }, cfg))
            ].filter(cfg => cfg && cfg.visible !== false);
        }
        function getNetworkStatusCache() {
            return Object.assign({}, snmpStatusCache || {}, nvrStatusCache || {});
        }
        function getNvrPreviewChannels(deviceId = '') {
            const cfg = nvrConfigs.find(item => String(item.id) === String(deviceId)) || nvrConfigs.find(item => item && item.visible !== false) || null;
            if (!cfg) return { cfg: null, status: {}, channels: [] };
            const status = nvrStatusCache[cfg.id] || {};
            const channels = Array.isArray(status.channels)
                ? status.channels.slice().sort((a, b) => Number(a?.id || 9999) - Number(b?.id || 9999))
                : [];
            return { cfg, status, channels };
        }
        function getNvrPreviewMode(mode) {
            const value = String(mode || 'stream').trim().toLowerCase();
            return ['smart', 'stream', 'stream4', 'stream8', 'live', 'snapshot'].includes(value) ? value : 'smart';
        }
        function getNvrPreviewGrid(value) {
            const n = Number(value || 1);
            return [1, 4, 9, 16].includes(n) ? n : 1;
        }
        function applyNvrPreviewUrlParams() {
            const params = new URLSearchParams(window.location.search || '');
            const mode = params.get('nvr_mode') || params.get('preview_mode') || '';
            const grid = params.get('nvr_grid') || params.get('preview_grid') || '';
            const page = params.get('nvr_page') || params.get('preview_page') || '';
            if (mode) nvrPreviewMode = getNvrPreviewMode(mode);
            if (grid) nvrPreviewGrid = getNvrPreviewGrid(grid);
            if (nvrPreviewMode === 'stream4') nvrPreviewGrid = 4;
            if (nvrPreviewMode === 'stream8') nvrPreviewGrid = 8;
            if (nvrPreviewMode === 'stream') nvrPreviewGrid = 1;
            if (page !== '') nvrPreviewPage = Math.max(0, Number(page) || 0);
        }
        function selectNvrPreview(deviceId, channelId, options = {}) {
            nvrSelectedDeviceId = String(deviceId || '').trim();
            nvrSelectedChannelId = String(channelId || '').trim();
            if (options.mode) nvrPreviewMode = getNvrPreviewMode(options.mode);
            if (options.grid) nvrPreviewGrid = getNvrPreviewGrid(options.grid);
            if (options.page !== undefined) nvrPreviewPage = Math.max(0, Number(options.page) || 0);
            if (options.live) {
                nvrPreviewGrid = 1;
                nvrPreviewMode = 'stream';
                nvrPreviewPage = 0;
            }
            renderNvrPreviewPanel({ refresh: !!options.refresh });
        }
        function setNvrPreviewMode(mode) {
            nvrPreviewMode = getNvrPreviewMode(mode);
            if (nvrPreviewMode === 'stream') nvrPreviewGrid = 1;
            if (nvrPreviewMode === 'stream4') nvrPreviewGrid = 4;
            if (nvrPreviewMode === 'stream8') nvrPreviewGrid = 8;
            nvrPreviewPage = 0;
            renderNvrPreviewPanel({ refresh: true });
        }
        function setNvrPreviewGrid(grid) {
            nvrPreviewGrid = getNvrPreviewGrid(grid);
            if (nvrPreviewGrid > 1 && nvrPreviewMode === 'stream') nvrPreviewMode = nvrPreviewGrid > 4 ? 'stream8' : 'stream4';
            if (nvrPreviewMode === 'stream4' && nvrPreviewGrid !== 4) nvrPreviewMode = 'smart';
            if (nvrPreviewMode === 'stream8' && nvrPreviewGrid !== 8) nvrPreviewMode = 'smart';
            nvrPreviewPage = 0;
            renderNvrPreviewPanel({ refresh: true });
        }
        function setNvrPreviewPage(delta) {
            nvrPreviewPage = Math.max(0, Number(nvrPreviewPage || 0) + Number(delta || 0));
            renderNvrPreviewPanel({ refresh: true });
        }
        function buildNvrStreamUrl(cfg, channelId, options = {}) {
            const source = String(options.source || 'h264');
            const controls = options.controls ? '1' : '0';
            const wall = options.wall ? '1' : '0';
            const cacheBust = options.refresh ? `&_=${Date.now()}` : '';
            return `/api/nvr/player/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}/?source=${encodeURIComponent(source)}&autoplay=1&muted=1&controls=${controls}&wall=${wall}&fit=cover${cacheBust}`;
        }
        function buildNvrSnapshotUrl(cfg, channelId, stream, options = {}) {
            const cacheBust = options.refresh ? Date.now() : Math.floor(Date.now() / 10000);
            return `/api/nvr/snapshot/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}?stream=${encodeURIComponent(stream)}&_=${cacheBust}`;
        }
        function buildNvrFallbackUrl(cfg, channelId, stream, options = {}) {
            const cacheBust = options.refresh ? Date.now() : Math.floor(Date.now() / 10000);
            return `/api/nvr/live/${encodeURIComponent(String(cfg.id))}/${encodeURIComponent(String(channelId))}?stream=${encodeURIComponent(stream)}&fps=${encodeURIComponent(String(options.fps || 5))}&width=${encodeURIComponent(String(options.width || 640))}&hw=auto&_=${cacheBust}`;
        }
        function activateNvrWallFrame(frame) {
            if (!frame || !frame.isConnected || frame.dataset.loaded === '1') return;
            const src = frame.dataset.src;
            if (!src) return;
            frame.dataset.loaded = '1';
            const cell = frame.closest('.nvr-wall-cell');
            if (cell) cell.classList.add('loading');
            frame.src = src;
        }
        function scheduleNvrWallFrames() {
            while (nvrWallFrameTimers.length) window.clearTimeout(nvrWallFrameTimers.pop());
            const frames = Array.from(document.querySelectorAll('#nvr-preview-panel iframe[data-nvr-lazy="1"]'));
            frames.forEach((frame, index) => {
                const timer = window.setTimeout(() => activateNvrWallFrame(frame), index * NVR_STREAM_STAGGER_MS);
                nvrWallFrameTimers.push(timer);
            });
        }
        function stopNvrWallSnapshotRefresh() {
            if (nvrWallSnapshotRefreshTimer) {
                window.clearTimeout(nvrWallSnapshotRefreshTimer);
                nvrWallSnapshotRefreshTimer = null;
            }
        }
        function scheduleNvrWallSnapshotRefresh() {
            stopNvrWallSnapshotRefresh();
            if (getActiveViewId() !== 'camera_preview') return;
            if (document.hidden || getNvrPreviewGrid(nvrPreviewGrid) <= 1) return;
            const mode = getNvrPreviewMode(nvrPreviewMode);
            if (!['smart', 'snapshot'].includes(mode)) return;
            nvrWallSnapshotRefreshTimer = window.setTimeout(() => {
                renderNvrPreviewPanel({ refresh: true, autoRefresh: true });
            }, NVR_WALL_SNAPSHOT_REFRESH_MS);
        }
        function stopNvrPreviewStreams() {
            while (nvrWallFrameTimers.length) window.clearTimeout(nvrWallFrameTimers.pop());
            stopNvrWallSnapshotRefresh();
            const panel = document.getElementById('nvr-preview-panel');
            if (!panel) return;
            panel.querySelectorAll('iframe').forEach(frame => {
                try { frame.src = 'about:blank'; } catch (err) {}
                try { frame.removeAttribute('src'); } catch (err) {}
            });
            panel.querySelectorAll('.nvr-wall-cell.loading, .nvr-preview-frame.loading').forEach(el => el.classList.remove('loading'));
        }
        function renderNvrPreviewPanel(options = {}) {
            const panel = document.getElementById('nvr-preview-panel');
            if (!panel) return;
            stopNvrPreviewStreams();
            const visibleNvrConfigs = (Array.isArray(nvrConfigs) ? nvrConfigs : []).filter(cfg => cfg && cfg.visible !== false);
            if (!visibleNvrConfigs.length) {
                panel.innerHTML = '<div class="nvr-preview-empty">未配置录像机设备。</div>';
                return;
            }
            const selectedExists = visibleNvrConfigs.some(cfg => String(cfg.id) === String(nvrSelectedDeviceId));
            if (!nvrSelectedDeviceId || !selectedExists) {
                nvrSelectedDeviceId = String(visibleNvrConfigs[0].id || '');
            }
            let { cfg, status, channels } = getNvrPreviewChannels(nvrSelectedDeviceId);
            if (!cfg) {
                panel.innerHTML = '<div class="nvr-preview-empty">未找到可预览的录像机。</div>';
                return;
            }
            if (!channels.length) {
                const expected = Number(cfg.expected_channel_count || 0);
                channels = Array.from({ length: expected || 32 }, (_, index) => ({
                    id: String(index + 1),
                    name: `D${index + 1}`,
                    online: false
                }));
            }
            const channelExists = channels.some(item => String(item.id) === String(nvrSelectedChannelId));
            if (!nvrSelectedChannelId || !channelExists) {
                const firstOnline = channels.find(item => item && item.online);
                nvrSelectedChannelId = String((firstOnline || channels[0] || {}).id || '');
            }
            const selected = channels.find(item => String(item.id) === String(nvrSelectedChannelId)) || channels[0] || {};
            const statusMeta = getDeviceStatusMeta(status, { staleText: '关注', errorText: '异常' });
            const summary = status.summary || {};
            const stream = String(cfg.live_stream || cfg.snapshot_stream || '2');
            const previewMode = getNvrPreviewMode(nvrPreviewMode);
            const gridSize = previewMode === 'stream8' ? 8 : getNvrPreviewGrid(nvrPreviewGrid);
            const onlineChannels = channels.filter(item => item && item.online);
            const selectedIndex = Math.max(0, channels.findIndex(item => String(item.id) === String(nvrSelectedChannelId)));
            const wallSource = channels.slice(selectedIndex).concat(channels.slice(0, selectedIndex));
            const pageSource = onlineChannels.length ? wallSource.filter(item => item && item.online) : wallSource;
            const pageCount = Math.max(1, Math.ceil(pageSource.length / Math.max(1, gridSize)));
            const currentPage = Math.min(Math.max(0, Number(nvrPreviewPage || 0)), pageCount - 1);
            nvrPreviewPage = currentPage;
            const pageStart = currentPage * gridSize;
            const wallChannels = pageSource.slice(pageStart, pageStart + gridSize);
            const effectiveMode = previewMode === 'smart' && gridSize === 1 ? 'stream' : (previewMode === 'stream4' || previewMode === 'stream8' ? 'stream' : previewMode);
            const wallUsesSnapshots = gridSize > 1 && ['smart', 'snapshot'].includes(previewMode);
            const streamLimit = effectiveMode === 'stream' ? Math.min(gridSize, NVR_STREAM_CONCURRENCY_LIMIT) : gridSize;
            const limitedCount = effectiveMode === 'stream' && gridSize > streamLimit ? gridSize - streamLimit : 0;
            const isPagedStream = ['stream4', 'stream8'].includes(previewMode);
            const modeLabel = previewMode === 'smart'
                ? (gridSize > 1 ? '智能快照墙' : '单路低延迟')
                : (previewMode === 'stream' ? '低延迟预览' : (previewMode === 'stream4' ? '4路稳定直播' : (previewMode === 'stream8' ? '8路实验直播' : (previewMode === 'live' ? 'MJPEG备用' : '单张抓拍'))));
            const badges = [
                `<span class="nvr-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>`,
                `<span class="nvr-chip">通道 ${escapeHtml(String(summary.channel_online ?? 0))}/${escapeHtml(String(summary.channel_total ?? channels.length))}</span>`,
                `<span class="nvr-chip ${Number(summary.hdd_error_count || 0) > 0 ? 'error' : 'online'}">硬盘 ${escapeHtml(String(summary.hdd_ok_count ?? 0))}/${escapeHtml(String(summary.hdd_total ?? 0))}</span>`,
                `<span class="nvr-chip">${escapeHtml(modeLabel)}</span>`,
                `<span class="nvr-chip">${gridSize === 1 ? '单路' : `${gridSize}宫格`}</span>`,
                isPagedStream ? `<span class="nvr-chip online">第 ${currentPage + 1}/${pageCount} 页</span>` : '',
                wallUsesSnapshots ? `<span class="nvr-chip online">${NVR_WALL_SNAPSHOT_REFRESH_MS / 1000}s 自动刷新</span>` : (limitedCount ? `<span class="nvr-chip warning">直播 ${streamLimit}/${gridSize} 路，余下抓拍占位</span>` : '')
            ];
            const channelButtons = channels.slice(0, 64).map(item => {
                const channelId = String(item?.id || '').trim();
                const active = channelId === String(nvrSelectedChannelId);
                const online = !!item?.online;
                const name = item?.name || `D${channelId || '--'}`;
                const meta = [item?.ip, item?.detect_result || (online ? '在线' : '离线')].filter(Boolean).join(' · ') || (online ? '在线' : '离线');
                return `<button type="button" class="nvr-channel-btn ${online ? 'online' : 'offline'} ${active ? 'active' : ''}" onclick="selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(channelId)}', { refresh: true })">
                    <span class="nvr-channel-dot"></span>
                    <span>
                        <span class="nvr-channel-name">${escapeHtml(name)}</span>
                        <span class="nvr-channel-meta">${escapeHtml(meta)}</span>
                    </span>
                    <span class="nvr-channel-index">D${escapeHtml(channelId || '--')}</span>
                </button>`;
            }).join('');
            const title = gridSize > 1
                ? `${cfg.name || cfg.id} · ${gridSize}宫格预览`
                : (selected.id ? `${selected.name || `D${selected.id}`} · D${selected.id}` : '选择一路监控');
            let frameHtml = '';
            if (gridSize > 1) {
                const cellHtml = wallChannels.map((item, index) => {
                    const channelId = String(item?.id || '').trim();
                    const name = item?.name || `D${channelId || '--'}`;
                    const online = !!item?.online;
                    const canStream = online && effectiveMode === 'stream' && (isPagedStream || index < streamLimit);
                    const isLimited = online && effectiveMode === 'stream' && !isPagedStream && index >= streamLimit;
                    const clickAction = `selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(channelId)}', { refresh: true, live: true })`;
                    const snapshotUrl = buildNvrSnapshotUrl(cfg, channelId, stream, { refresh: true });
                    const media = wallUsesSnapshots
                        ? `<img src="${escapeHtml(snapshotUrl)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`
                        : (previewMode === 'live'
                            ? `<img src="${escapeHtml(buildNvrFallbackUrl(cfg, channelId, stream, { refresh: options.refresh, fps: 3, width: 480 }))}" alt="${escapeHtml(name)}" loading="lazy" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`
                            : (canStream
                                ? `<iframe data-nvr-lazy="1" data-src="${escapeHtml(buildNvrStreamUrl(cfg, channelId, { refresh: options.refresh, source: 'h264', wall: isPagedStream }))}" title="${escapeHtml(name)}" allow="autoplay; fullscreen; encrypted-media" loading="lazy" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')"></iframe>`
                                : `<img src="${escapeHtml(snapshotUrl)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async" onload="this.closest('.nvr-wall-cell')?.classList.remove('loading')" onerror="this.closest('.nvr-wall-cell')?.classList.add('offline')">`));
                    const statusText = !online ? '离线' : (wallUsesSnapshots ? '快照' : (effectiveMode === 'stream' ? (canStream ? '直播' : '占位') : (previewMode === 'live' ? 'MJPEG' : '抓拍')));
                    return `<div class="nvr-wall-cell ${online ? 'online loading' : 'offline'} ${isLimited ? 'preview-limited' : ''}" onclick="${clickAction}">
                        <div class="nvr-wall-label">D${escapeHtml(channelId || '--')} · ${escapeHtml(name)}</div>
                        <div class="nvr-wall-status">${escapeHtml(statusText)}</div>
                        ${media}
                    </div>`;
                }).join('');
                frameHtml = `<div class="nvr-wall-grid wall-${gridSize}">${cellHtml || '<div class="nvr-preview-empty">暂无可预览通道</div>'}</div>`;
            } else {
                const previewUrl = selected.id
                    ? (effectiveMode === 'stream'
                        ? buildNvrStreamUrl(cfg, selected.id, { refresh: options.refresh, controls: true, source: 'h264' })
                        : (previewMode === 'live'
                            ? buildNvrFallbackUrl(cfg, selected.id, stream, { refresh: options.refresh, fps: 8, width: 960 })
                            : buildNvrSnapshotUrl(cfg, selected.id, stream, { refresh: options.refresh })))
                    : '';
                frameHtml = previewUrl
                    ? `<div class="nvr-preview-frame ${effectiveMode === 'stream' ? 'stream' : (previewMode === 'live' ? 'live' : 'snapshot')} ${options.refresh ? 'loading' : ''}">
                        ${effectiveMode === 'stream'
                            ? `<iframe src="${escapeHtml(previewUrl)}" title="${escapeHtml(title)}" allow="autoplay; fullscreen; encrypted-media" onload="this.closest('.nvr-preview-frame')?.classList.remove('loading')"></iframe>`
                            : `<img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(title)}" loading="eager" onload="this.closest('.nvr-preview-frame')?.classList.remove('loading')" onerror="this.closest('.nvr-preview-frame').innerHTML='<div class=&quot;nvr-preview-empty&quot;>${previewMode === 'live' ? 'MJPEG 备用连接失败，可切换抓拍备用。' : '抓拍失败，请稍后重试或换一路通道。'}</div>'">`}
                    </div>`
                    : '<div class="nvr-preview-frame"><div class="nvr-preview-empty">请选择一路通道预览。</div></div>';
            }
            panel.innerHTML = `<div class="nvr-preview-layout">
                <div class="nvr-preview-stage">
                    <div class="nvr-preview-head">
                        <div>
                            <div class="nvr-preview-title">${escapeHtml(title)}</div>
                            <div class="nvr-preview-subtitle">${escapeHtml(cfg.name || cfg.id)} · ${escapeHtml(cfg.host || '--')} · ${escapeHtml(status.device_info?.model || cfg.model || '--')}</div>
                        </div>
                        <div class="nvr-preview-tools">
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'smart' ? 'active' : ''}" onclick="setNvrPreviewMode('smart')" title="默认模式：16 路快照墙，低负载、适合长期打开">16路快照</button>
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream' ? 'active' : ''}" onclick="setNvrPreviewMode('stream')">低延迟</button>
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream4' ? 'active' : ''}" onclick="setNvrPreviewMode('stream4')" title="稳定模式：每页 4 路实时直播，可翻页查看 32 路">4路直播</button>
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'stream8' ? 'active' : ''}" onclick="setNvrPreviewMode('stream8')" title="实验模式：当前显卡/NVENC环境下可能只能稳定部分通道">8路实验</button>
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'live' ? 'active' : ''}" onclick="setNvrPreviewMode('live')">MJPEG备用</button>
                            <button type="button" class="nvr-preview-mode-btn ${previewMode === 'snapshot' ? 'active' : ''}" onclick="setNvrPreviewMode('snapshot')">抓拍备用</button>
                            ${[1,4,9,16].map(size => `<button type="button" class="nvr-preview-mode-btn ${gridSize === size ? 'active' : ''}" onclick="setNvrPreviewGrid(${size})">${size === 1 ? '单路' : `${size}宫格`}</button>`).join('')}
                            ${isPagedStream ? `<button type="button" class="nvr-preview-btn" onclick="setNvrPreviewPage(-1)" ${currentPage <= 0 ? 'disabled' : ''}>上一页</button><button type="button" class="nvr-preview-btn" onclick="setNvrPreviewPage(1)" ${currentPage >= pageCount - 1 ? 'disabled' : ''}>下一页</button>` : ''}
                            <button type="button" class="nvr-preview-btn" onclick="selectNvrPreview('${escapeHtml(String(cfg.id))}', '${escapeHtml(String(selected.id || ''))}', { refresh: true })">刷新</button>
                        </div>
                    </div>
                    <div class="nvr-preview-badges">${badges.join('')}</div>
                    ${frameHtml}
                </div>
                <div class="nvr-channel-list">${channelButtons || '<div class="nvr-preview-empty">暂无通道清单</div>'}</div>
            </div>`;
            scheduleNvrWallFrames();
            scheduleNvrWallSnapshotRefresh();
        }
        function normalizeNvrStatusForSnmp(cfg, status) {
            const payload = Object.assign({}, status || {});
            const summary = Object.assign({}, payload.summary || {});
            payload.online = payload.online !== undefined ? !!payload.online : false;
            payload.status_level = payload.status_level || (payload.online ? 'online' : 'offline');
            payload.status_label = payload.status_label || (payload.online ? '正常' : '离线');
            summary.device_type = 'nvr';
            summary.risk_level = summary.risk_level || (payload.status_level === 'error' ? 'critical' : (payload.status_level === 'stale' ? 'warning' : 'normal'));
            summary.health_score = summary.health_score ?? (payload.online ? 100 : 0);
            summary.channel_total = summary.channel_total ?? payload.channel_total ?? 0;
            summary.channel_online = summary.channel_online ?? payload.channel_online ?? 0;
            summary.channel_offline = summary.channel_offline ?? payload.channel_offline ?? 0;
            summary.hdd_total = summary.hdd_total ?? payload.hdd_total ?? 0;
            summary.hdd_ok_count = summary.hdd_ok_count ?? payload.hdd_ok_count ?? 0;
            summary.hdd_error_count = summary.hdd_error_count ?? payload.hdd_error_count ?? 0;
            summary.weak_password_count = summary.weak_password_count ?? payload.weak_password_count ?? 0;
            summary.uptime_text = summary.uptime_text || payload.uptime_text || '--';
            summary.alert_counts = summary.alert_counts || {
                critical: Number(summary.hdd_error_count || 0) > 0 ? 1 : 0,
                warning: Number(summary.channel_offline || 0) + Number(summary.weak_password_count || 0),
                info: 0
            };
            payload.summary = summary;
            payload.version = payload.version || 'ISAPI';
            payload.sys_name = payload.sys_name || payload.device_info?.device_name || cfg?.name || 'NVR';
            return payload;
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
            const rows = getSnmpStorageDisplayRows(summary, 1);
            return rows[0] || null;
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
                    note: summary?.storage_capacity_note || 'QNAP 共享文件夹/LUN 为配额视图，不能相加为物理总容量。',
                };
            }
            const percent = totals.total > 0 ? Math.round((totals.used / totals.total) * 10_000) / 100 : null;
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
        function getSnmpDiskSummary(summary) {
            const diskRows = Array.isArray(summary?.disk_rows) && summary.disk_rows.length
                ? summary.disk_rows
                : (Array.isArray(summary?.disk_top_rows) ? summary.disk_top_rows : []);
            const warningCount = diskRows.filter(row => ['warning', 'critical'].includes(String(row?.alert_level || '').toLowerCase())).length;
            const criticalCount = diskRows.filter(row => String(row?.alert_level || '').toLowerCase() === 'critical').length;
            const hottest = diskRows.slice().sort((a, b) => Number(b?.temp_c || -1) - Number(a?.temp_c || -1))[0] || null;
            const tempMeta = hottest
                ? `最高 ${hottest.slot || '--'} ${hottest.temp_text || '--'} · ${warningCount > 0 ? `温度告警 ${warningCount}` : '温度正常'}`
                : `盘位未采到 · 风扇 ${summary?.fan_count ?? 0}`;
            return { rows: diskRows, warningCount, criticalCount, hottest, tempMeta };
        }
        function getSnmpProtocolProfile(cfg, status, summary) {
            const deviceType = String(summary?.device_type || cfg?.device_type || '').trim().toLowerCase();
            const brand = String(cfg?.brand || status?.config?.brand || '').trim().toLowerCase();
            if (deviceType === 'nvr') {
                return { label: '海康 ISAPI', note: '厂商接口：通道、硬盘、固件、抓拍/预览', level: 'online' };
            }
            if (brand.includes('qnap') || String(cfg?.model || '').toLowerCase().includes('ts-')) {
                return { label: 'QNAP MIB', note: '私有 MIB + HOST-RESOURCES：卷、盘位、温度、风扇', level: 'online' };
            }
            if (brand.includes('h3c') || deviceType === 'switch') {
                return { label: 'IF-MIB / Bridge-MIB', note: '标准 MIB：端口、速率、MAC、VLAN 学习', level: 'online' };
            }
            if (brand.includes('ikuai') || brand.includes('爱快') || deviceType === 'router') {
                return { label: 'RFC1213 / IF-MIB', note: '标准 SNMP：接口、吞吐、系统资源；私有指标按设备返回显示', level: 'warning' };
            }
            return { label: '标准 SNMP', note: '系统、接口、存储、资源按设备实际返回展示', level: '' };
        }
        function renderSnmpHealthPill(summary) {
            const level = String(summary?.risk_level || 'normal').trim().toLowerCase();
            const counts = summary?.alert_counts || {};
            const levelText = level === 'critical' ? '高风险' : (level === 'warning' ? '关注中' : '运行稳定');
            const score = summary?.health_score !== undefined && summary?.health_score !== null ? String(summary.health_score) : '--';
            return `<div class="snmp-health-pill ${escapeHtml(level)}">
                <div>
                    <div class="snmp-health-pill-label">健康评分</div>
                    <div class="snmp-health-pill-value">${escapeHtml(score)}</div>
                </div>
                <div class="snmp-health-pill-meta">${escapeHtml(levelText)} · 严重 ${escapeHtml(String(counts.critical ?? 0))} · 告警 ${escapeHtml(String(counts.warning ?? 0))}</div>
            </div>`;
        }
        function buildSnmpDeviceFactItems(deviceType, summary, status) {
            const interfaceSummary = summary.interface_summary || {};
            const updatedAt = status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--';
            if (deviceType === 'nvr') {
                const info = status.device_info || {};
                return [
                    { label: '通道在线', value: `${summary.channel_online ?? 0} / ${summary.channel_total ?? 0}`, meta: `离线 ${summary.channel_offline ?? 0}` },
                    { label: '硬盘状态', value: `${summary.hdd_ok_count ?? 0} / ${summary.hdd_total ?? 0}`, meta: `异常 ${summary.hdd_error_count ?? 0}` },
                    { label: '固件版本', value: info.firmware_version || '--', meta: info.firmware_build || info.model || '--' },
                    { label: '采集时间', value: updatedAt, meta: summary.uptime_text || status.uptime_text || '--' }
                ];
            }
            if (deviceType === 'nas') {
                return [
                    { label: '在线接口', value: `${interfaceSummary.up_count ?? '--'}`, meta: `物理 ${(interfaceSummary.physical_count ?? 0)} · 聚合 ${(interfaceSummary.bond_count ?? 0)}` },
                    { label: '存储 / 槽位', value: `${summary.storage_count ?? 0} / ${summary.disk_count ?? 0}`, meta: `风扇 ${summary.fan_count ?? 0} · 进程 ${summary.process_count ?? '--'}` },
                    { label: '采集时间', value: updatedAt, meta: summary.uptime_text || '--' }
                ];
            }
            if (deviceType === 'router') {
                const trafficRows = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true });
                const primaryLink = trafficRows[0];
                return [
                    { label: '接口结构', value: getSnmpInterfaceCountText(interfaceSummary, status), meta: getSnmpInterfaceRoleText(interfaceSummary) },
                    { label: '主链路', value: primaryLink ? `${primaryLink.name || '--'}` : '--', meta: primaryLink ? `${getSnmpInterfaceKindText(primaryLink.kind)} · ${primaryLink.total_rate_text || primaryLink.traffic_text || '--'}` : '暂无实时链路流量' },
                    { label: '采集时间', value: updatedAt, meta: summary.uptime_text || '--' }
                ];
            }
            if (deviceType === 'switch') {
                const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
                return [
                    { label: '接口总数', value: getSnmpInterfaceCountText(interfaceSummary, status), meta: `物理 ${switchStats.physicalCount} · 在线 ${switchStats.upCount}` },
                    { label: '桥接摘要', value: `${switchStats.bridgeMacCount}`, meta: `MAC · VLAN ${switchStats.bridgeVlanCount}` },
                    { label: '采集时间', value: updatedAt, meta: summary.uptime_text || '--' }
                ];
            }
            return [
                { label: '在线接口', value: `${interfaceSummary.up_count ?? '--'}`, meta: `总接口 ${status.if_number ?? '--'}` },
                { label: '采集时间', value: updatedAt, meta: summary.uptime_text || '--' }
            ];
        }
        function buildSnmpPrimaryMetricItems(deviceType, summary, status, customMetrics = []) {
            const interfaceSummary = summary.interface_summary || {};
            if (deviceType === 'nvr') {
                const offlineNames = (Array.isArray(status.offline_channels) ? status.offline_channels : [])
                    .slice(0, 3)
                    .map(item => item?.name || `D${item?.id || ''}`)
                    .filter(Boolean)
                    .join(' / ');
                const hddErrorText = Number(summary.hdd_error_count || 0) > 0 ? `异常 ${summary.hdd_error_count}` : '正常';
                return [
                    {
                        label: '通道在线',
                        value: `${summary.channel_online ?? 0} / ${summary.channel_total ?? 0}`,
                        meta: offlineNames ? `离线 ${offlineNames}` : '全部在线',
                        level: Number(summary.channel_offline || 0) > 0 ? 'warning' : ''
                    },
                    {
                        label: '硬盘',
                        value: `${summary.hdd_ok_count ?? 0} / ${summary.hdd_total ?? 0}`,
                        meta: `${hddErrorText} · 剩余 ${status.hdd_free_text || '--'}`,
                        level: Number(summary.hdd_error_count || 0) > 0 ? 'critical' : ''
                    },
                    {
                        label: '内存 / 运行',
                        value: `${status.memory_usage_percent ?? '--'}%`,
                        meta: status.uptime_text || '--',
                        level: Number(status.memory_usage_percent || 0) >= 85 ? 'warning' : ''
                    },
                    {
                        label: '安全',
                        value: `${summary.weak_password_count ?? 0}`,
                        meta: '弱密码通道',
                        level: Number(summary.weak_password_count || 0) > 0 ? 'warning' : ''
                    }
                ];
            }
            if (deviceType === 'nas') {
                const capacity = summarizeSnmpStorageCapacity(summary);
                const primaryStorageDisplay = getSnmpPrimaryStorageDisplay(summary);
                const diskSummary = getSnmpDiskSummary(summary);
                return [
                    {
                        label: '主容量',
                        value: primaryStorageDisplay.value,
                        meta: `${primaryStorageDisplay.meta} · 卷 ${capacity.rows.length}`,
                        level: primaryStorageDisplay.level
                    },
                    {
                        label: '内存 / CPU',
                        value: `${summary.memory_usage_percent ?? '--'}% / ${summary.cpu_avg_percent ?? '--'}%`,
                        meta: `Load ${summary.ucd_load_1 ?? '--'} · 可用 ${summary.memory_available_text || '--'}`,
                        level: getSnmpAlertLevel(summary.memory_alert_level) || (Number(summary.cpu_peak_percent || 0) >= 80 ? 'warning' : '')
                    },
                    {
                        label: '磁盘 / 温度',
                        value: `${diskSummary.rows.length || summary.disk_count || 0} 盘`,
                        meta: diskSummary.tempMeta,
                        level: diskSummary.criticalCount > 0 ? 'critical' : (diskSummary.warningCount > 0 ? 'warning' : '')
                    },
                    {
                        label: '网络 / 硬件',
                        value: getSnmpBestThroughputDisplay(interfaceSummary),
                        meta: `网卡 ${(interfaceSummary.physical_count ?? 0)} · 风扇 ${summary.fan_count ?? 0} · GPU ${(Array.isArray(summary.gpu_metrics) ? summary.gpu_metrics.length : 0)}`,
                        level: ''
                    }
                ];
            }
            if (deviceType === 'router') {
                const routerCpuTemp = getSnmpMetricValueWithFallback(customMetrics, ['cpu_temperature_c', 'temperature_c'], summary);
                const routerConnections = getSnmpMetricValueWithFallback(customMetrics, ['network_connections', 'session_count', 'nat_sessions'], summary);
                const routerApCount = getSnmpMetricValueWithFallback(customMetrics, ['ap_count', 'online_clients'], summary);
                const trafficRows = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true });
                const primaryLink = trafficRows[0];
                return [
                    {
                        label: '接口总流量',
                        value: getSnmpBestThroughputDisplay(interfaceSummary),
                        meta: `上 / 下 ${getSnmpBestThroughputPair(interfaceSummary)}`
                    },
                    {
                        label: '主链路',
                        value: primaryLink ? `${primaryLink.name || '--'}` : '--',
                        meta: primaryLink ? `${getSnmpInterfaceKindText(primaryLink.kind)} · ${primaryLink.total_rate_text || primaryLink.traffic_text || '--'}` : getSnmpInterfaceRoleText(interfaceSummary)
                    },
                    {
                        label: 'CPU / 内存',
                        value: `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%`,
                        meta: `峰值 ${summary.cpu_peak_percent ?? '--'}% · 温度 ${snmpProvidedText(routerCpuTemp)}`,
                        level: Number(summary.cpu_peak_percent || 0) >= 80 ? 'warning' : getSnmpAlertLevel(summary.memory_alert_level)
                    },
                    {
                        label: '连接 / AP',
                        value: `${snmpProvidedText(routerConnections)} / ${snmpProvidedText(routerApCount)}`,
                        meta: `设备未提供时显示为未提供 · 异常口 ${(interfaceSummary.error_port_count ?? 0) + (interfaceSummary.discard_port_count ?? 0)}`,
                        level: Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0 ? 'warning' : ''
                    }
                ];
            }
            if (deviceType === 'switch') {
                const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
                return [
                    {
                        label: '接口总数',
                        value: getSnmpInterfaceCountText(interfaceSummary, status),
                        meta: `在线 / 离线 / 未采到 ${switchStats.upCount} / ${switchStats.downCount} / ${switchStats.unknownCount}`,
                        level: Number(switchStats.downCount || 0) > 0 ? 'warning' : ''
                    },
                    {
                        label: '端口状态',
                        value: `${switchStats.upCount} / ${switchStats.downCount} / ${switchStats.unknownCount}`,
                        meta: `在线 / 离线 / 未采到 · 物理 ${switchStats.physicalCount} · 上联 ${switchStats.uplinkCount}`,
                        level: Number(switchStats.downCount || 0) > 0 ? 'warning' : ''
                    },
                    {
                        label: '交换总吞吐',
                        value: getSnmpBestThroughputDisplay(interfaceSummary),
                        meta: `${interfaceSummary.aggregate_in_rate_text || '--'} / ${interfaceSummary.aggregate_out_rate_text || '--'}`
                    },
                    {
                        label: '新增异常',
                        value: `${interfaceSummary.delta_error_port_count ?? 0} / ${interfaceSummary.delta_discard_port_count ?? 0}`,
                        meta: `错包口 / 丢弃口 · 忙碌 ${(interfaceSummary.busy_port_count ?? 0)}`,
                        level: Number(interfaceSummary.delta_discard_port_count || 0) > 0 ? 'critical' : (Number(interfaceSummary.delta_error_port_count || 0) > 0 ? 'warning' : '')
                    },
                    {
                        label: 'MAC / VLAN',
                        value: `${switchStats.bridgeMacCount} / ${switchStats.bridgeVlanCount}`,
                        meta: `桥端口 ${interfaceSummary.bridge_port_count ?? 0} · 学习 ${switchStats.learnedMacCount}`
                    }
                ];
            }
            return [
                { label: '接口数', value: `${status.if_number ?? '--'}`, meta: summary.interface_preview || '--' },
                { label: '状态', value: getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' }).text, meta: summary.uptime_text || '--' }
            ];
        }
        function renderSnmpDevicePrimaryPanels(deviceId, deviceType, summary, status, customMetrics = []) {
            const interfaceSummary = summary.interface_summary || {};
            if (deviceType === 'nvr') {
                const channels = Array.isArray(status.channels) ? status.channels : [];
                const hdds = Array.isArray(status.hdds) ? status.hdds : [];
                const offlineChannels = Array.isArray(status.offline_channels) ? status.offline_channels : channels.filter(item => !item.online);
                const weakChannels = Array.isArray(status.weak_password_channels) ? status.weak_password_channels : channels.filter(item => {
                    const text = String(item?.password_status || '').trim().toLowerCase();
                    return text && !['strong', 'safe', 'normal', 'ok'].includes(text);
                });
                const channelBody = renderSnmpMiniList([
                    {
                        label: '在线通道',
                        meta: `总通道 ${summary.channel_total ?? channels.length ?? 0}`,
                        value: `${summary.channel_online ?? 0} / ${summary.channel_total ?? 0}`,
                        level: Number(summary.channel_offline || 0) > 0 ? 'warning' : ''
                    },
                    ...offlineChannels.slice(0, 5).map(item => ({
                        label: item?.name || `D${item?.id || '--'}`,
                        meta: item?.ip || item?.detect_result || '离线通道',
                        value: '离线',
                        level: 'warning'
                    }))
                ], { maxCount: 6, emptyText: '通道状态正常' });
                const hddBody = renderSnmpMiniList(hdds.map(item => {
                    const statusText = item?.status_text || item?.status || '--';
                    const level = ['ok', 'normal', '正常'].includes(String(statusText).toLowerCase()) || statusText === '正常' ? '' : 'critical';
                    return {
                        label: item?.name || `HDD${item?.id || ''}`,
                        meta: `${item?.capacity_text || '--'} / 剩余 ${item?.free_text || '--'}`,
                        value: statusText,
                        level
                    };
                }), { maxCount: 6, emptyText: '未采到硬盘信息' });
                const runtimeBody = renderSnmpMiniList([
                    { label: '设备型号', meta: status.device_info?.manufacturer || 'Hikvision ISAPI', value: status.device_info?.model || status.config?.model || '--' },
                    { label: '固件版本', meta: status.device_info?.firmware_build || '--', value: status.device_info?.firmware_version || '--' },
                    { label: '内存占用', meta: status.uptime_text || summary.uptime_text || '--', value: status.memory_usage_percent !== undefined && status.memory_usage_percent !== null ? `${status.memory_usage_percent}%` : '--', level: Number(status.memory_usage_percent || 0) >= 85 ? 'warning' : '' },
                    { label: '弱密码通道', meta: weakChannels.slice(0, 3).map(item => item?.name || `D${item?.id || ''}`).filter(Boolean).join(' / ') || '未发现', value: String(summary.weak_password_count ?? weakChannels.length ?? 0), level: Number(summary.weak_password_count || weakChannels.length || 0) > 0 ? 'warning' : '' }
                ], { maxCount: 4, emptyText: '暂无录像机运行信息' });
                return `<div class="snmp-focus-grid">
                    ${renderSnmpFocusPanel('通道状态', '在线、离线与缺失通道快速定位', channelBody)}
                    ${renderSnmpFocusPanel('硬盘状态', '录像盘容量与健康状态', hddBody)}
                    ${renderSnmpFocusPanel('录像机信息', '固件、运行时长与安全提示', runtimeBody)}
                </div>`;
            }
            if (deviceType === 'nas') {
                const networkRows = Array.isArray(summary.physical_top_rows) && summary.physical_top_rows.length ? summary.physical_top_rows : (Array.isArray(summary.network_top_rows) ? summary.network_top_rows : []);
                const storageRows = getSnmpStorageDisplayRows(summary, 8);
                const diskSummary = getSnmpDiskSummary(summary);
                const diskRows = diskSummary.rows;
                const gpuMetrics = Array.isArray(summary.gpu_metrics) ? summary.gpu_metrics : [];
                const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
                const capacity = summarizeSnmpStorageCapacity(summary);
                const protocol = getSnmpProtocolProfile({}, status, summary);
                const networkBody = renderSnmpMiniList(networkRows.map(row => ({
                    label: row.name || '--',
                    meta: `${row.speed_text || '--'} · ${row.utilization_text || '--'}`,
                    value: row.total_rate_text || row.traffic_text || '--',
                    level: getSnmpSwitchPortState(row).level === 'down' ? 'warning' : ''
                })), { maxCount: 4, emptyText: '暂无关键网卡流量' });
                const capacityHero = renderSnmpCapacityHero(summary, { limit: 8, title: '容量总览', compact: false });
                const diskBody = renderSnmpMiniList(diskRows.slice(0, 8).map(row => ({
                    label: row.slot || row.model || '--',
                    meta: `${row.model || '--'} · ${row.capacity_text || '--'} · ${row.serial || '--'}`,
                    value: `${row.status || '--'} / ${row.temp_text || '--'}`,
                    level: getSnmpAlertLevel(row.alert_level)
                })), { maxCount: 8, emptyText: '当前未采到盘位健康信息' });
                const signalItems = [
                    { label: '采集能力', meta: protocol.note, value: protocol.label, level: protocol.level === 'warning' ? 'warning' : '' },
                    { label: capacity.mode === 'qnap_quota' ? '共享/LUN 配额' : '卷容量合计', meta: `共 ${capacity.rows.length} 项`, value: capacity.mode === 'qnap_quota' ? `已用 ${capacity.usedText}` : `${capacity.usedText} / ${capacity.totalText}` },
                    ...alertItems.slice(0, 3).map(item => ({
                        label: item.text || '--',
                        meta: '系统告警',
                        value: item.level === 'critical' ? '严重' : '提醒',
                        level: item.level === 'critical' ? 'critical' : 'warning'
                    })),
                    ...gpuMetrics.slice(0, 2).map(item => ({
                        label: item.name || 'GPU',
                        meta: '图形硬件指标',
                        value: `${item.value ?? '--'}${item.unit ? ` ${item.unit}` : ''}`
                    }))
                ];
                const signalBody = renderSnmpMiniList(signalItems, { maxCount: 5, emptyText: '当前无额外告警，硬件运行稳定' });
                const chassisBody = renderQnapDriveBayPanel(summary);
                return `<div class="snmp-focus-grid">
                    ${renderSnmpFocusPanel('容量与配额', capacity.mode === 'qnap_quota' ? 'QNAP 共享/LUN 配额视图，不合并为物理池容量' : 'NAS 卷用量、已用/总量、风险容量', capacityHero)}
                    ${chassisBody ? renderSnmpFocusPanel('机箱盘位', '模拟 QNAP 盘位布局，快速看 HDD/SSD/空槽', chassisBody, { wide: true }) : ''}
                    ${renderSnmpFocusPanel('盘位健康', 'QNAP 私有 MIB 采集盘位、温度、容量和序列号', diskBody)}
                    ${renderSnmpFocusPanel('网络流量', '主网卡实时吞吐与利用率', networkBody)}
                    ${renderSnmpFocusPanel('采集能力与告警', '专用 MIB、系统告警、GPU 与额外硬件指标', signalBody)}
                </div>`;
            }
            if (deviceType === 'router') {
                const topTraffic = Array.isArray(summary.network_top_rows) ? summary.network_top_rows : [];
                const wanTraffic = Array.isArray(summary.wan_top_rows) ? summary.wan_top_rows : [];
                const lanTraffic = Array.isArray(summary.lan_top_rows) ? summary.lan_top_rows : [];
                const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
                const routerConnections = getSnmpMetricValueWithFallback(customMetrics, ['network_connections', 'session_count', 'nat_sessions'], summary);
                const routerApCount = getSnmpMetricValueWithFallback(customMetrics, ['ap_count', 'online_clients'], summary);
                const routerCpuTemp = getSnmpMetricValueWithFallback(customMetrics, ['cpu_temperature_c', 'temperature_c'], summary);
                const linkRows = [wanTraffic[0], lanTraffic[0], ...getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true }).slice(0, 4), ...topTraffic.slice(0, 3)]
                    .filter((row, index, rows) => row && rows.findIndex(item => (item?.name || '') === (row?.name || '')) === index);
                const linkBody = renderSnmpMiniList(linkRows.map(row => ({
                    label: row.name || '--',
                    meta: `${getSnmpInterfaceKindText(row.kind)} · ${row.speed_text || '--'}`,
                    value: row.total_rate_text || row.traffic_text || '--',
                    level: getSnmpSwitchPortState(row).level === 'down' ? 'warning' : ''
                })), { maxCount: 5, emptyText: '暂无关键链路摘要' });
                const runtimeBody = renderSnmpMiniList([
                    { label: '网络连接', meta: '会话规模', value: snmpProvidedText(routerConnections) },
                    { label: 'AP / 终端', meta: '厂商未开放时显示未提供', value: snmpProvidedText(routerApCount) },
                    { label: 'CPU 温度', meta: '厂商扩展 OID', value: snmpProvidedText(routerCpuTemp) },
                    { label: 'Load 1 / 5 / 15', meta: '系统负载', value: `${summary.ucd_load_1 ?? '--'} / ${summary.ucd_load_5 ?? '--'} / ${summary.ucd_load_15 ?? '--'}` }
                ], { maxCount: 4, emptyText: '暂无扩展网关指标' });
                const alertBody = renderSnmpMiniList(alertItems.map(item => ({
                    label: item.text || '--',
                    meta: '网关告警',
                    value: item.level === 'critical' ? '严重' : '提醒',
                    level: item.level === 'critical' ? 'critical' : 'warning'
                })), { maxCount: 5, emptyText: '当前无网关告警' });
                return `<div class="snmp-focus-grid">
                    ${renderSnmpFocusPanel('关键链路', 'WAN、LAN 与高流量接口', linkBody)}
                    ${renderSnmpFocusPanel('运行状态', '连接数、AP、温度与负载', runtimeBody)}
                    ${renderSnmpFocusPanel('告警摘要', '优先展示当前需要关注的网关事件', alertBody)}
                </div>`;
            }
            if (deviceType === 'switch') {
                const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
                const portRows = switchStats.rows;
                const anomalyRows = sortSnmpPortRows(portRows, 'anomaly').filter(row => Number(row.discard_delta_total || 0) > 0 || Number(row.error_delta_total || 0) > 0 || Number(row.utilization_percent || 0) >= 80).slice(0, 6);
                const bridgePortMacRows = Array.isArray(interfaceSummary.bridge_port_mac_rows) ? interfaceSummary.bridge_port_mac_rows : [];
                const bridgeVlanRows = Array.isArray(interfaceSummary.bridge_vlan_rows) ? interfaceSummary.bridge_vlan_rows : [];
                const vlanPortRows = buildSnmpSwitchVlanPortHighlights(summary, interfaceSummary, 4);
                const onlineOverviewBody = renderSnmpMiniList([
                    {
                        label: '端口在线 / 离线 / 未采到',
                        meta: `物理口 ${switchStats.physicalCount} · 上联 ${switchStats.uplinkCount}`,
                        value: `${switchStats.upCount} / ${switchStats.downCount} / ${switchStats.unknownCount}`,
                        level: switchStats.downCount > 0 ? 'warning' : ''
                    },
                    {
                        label: 'MAC / VLAN',
                        meta: `学习 MAC ${switchStats.learnedMacCount}`,
                        value: `${switchStats.bridgeMacCount} / ${switchStats.bridgeVlanCount}`,
                        level: switchStats.bridgeVlanCount > 0 ? '' : 'warning'
                    },
                    ...vlanPortRows
                ], { maxCount: 6, emptyText: '暂无端口在线状态摘要' });
                const anomalyBody = renderSnmpMiniList(anomalyRows.map(row => ({
                    label: `${row.name || '--'} (#${row.index ?? '--'})`,
                    meta: `${row.speed_text || '--'} · ${row.utilization_text || '--'}`,
                    value: row.total_rate_text || '--',
                    level: Number(row.discard_delta_total || 0) > 0 ? 'critical' : 'warning'
                })), { maxCount: 6, emptyText: '当前没有异常端口' });
                const bridgeBody = renderSnmpMiniList(
                    bridgePortMacRows.length
                        ? bridgePortMacRows.map(row => ({
                            label: `${row.port_name || '--'} (#${row.ifindex ?? '--'})`,
                            meta: `VLAN ${row.vlan_count ?? 0} · PVID ${row.pvid_name || '--'}`,
                            value: `MAC ${row.mac_count ?? 0}`
                        }))
                        : bridgeVlanRows.map(row => ({
                            label: row.vlan_name || `VLAN ${row.vlan_id ?? '--'}`,
                            meta: row.ports_preview || '--',
                            value: `MAC ${row.mac_count ?? 0}`
                        })),
                    { maxCount: 6, emptyText: '暂无 VLAN / MAC 学习摘要' }
                );
                return `<div class="snmp-focus-grid">
                    ${renderSnmpFocusPanel('端口在线状态', '交换机物理口实时在线与 VLAN 学习摘要', onlineOverviewBody)}
                    ${renderSnmpFocusPanel('端口异常', '优先看错包、丢弃与高利用率端口', anomalyBody)}
                    ${renderSnmpFocusPanel('VLAN / MAC', '桥接学习与接入口活跃情况', bridgeBody)}
                    ${renderPersistedSnmpDetails(deviceId, 'ports', '端口面板', '异常、上联、在线、离线与状态未采到端口', renderSnmpSwitchPortPanels(deviceId, portRows) || '<div class="snmp-mini-empty">暂无端口明细</div>', false, 'snmp-inline-details snmp-ports-detail')}
                </div>`;
            }
            return renderSnmpFocusPanel('设备摘要', '当前设备主信息', renderSnmpMiniList(buildSnmpDeviceFactItems(deviceType, summary, status), { maxCount: 4, emptyText: '暂无设备摘要' }), { wide: true });
        }
        function renderSnmpAdvancedDetails(deviceId, deviceType, summary, status, customMetrics = []) {
            const interfaceSummary = summary.interface_summary || {};
            const interfaceChipsHtml = renderSnmpInterfaceChips(interfaceSummary, deviceType);
            const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
            const extraMetricRows = buildSnmpMetricRows(customMetrics, ['hr_memory_size_kb', 'hr_system_processes', 'hr_system_users'], 8);
            const sections = [];
            if (interfaceChipsHtml) {
                sections.push(`<div class="ups-alert-list">${interfaceChipsHtml}</div>`);
            }
            if (alertItems.length) {
                sections.push(renderSnmpFocusPanel('告警详情', '保留详细告警文案，便于排查', renderSnmpMiniList(alertItems.map(item => ({
                    label: item.text || '--',
                    meta: item.level === 'critical' ? '严重告警' : '普通告警',
                    value: item.level === 'critical' ? '严重' : '提醒',
                    level: item.level === 'critical' ? 'critical' : 'warning'
                })), { maxCount: 8, emptyText: '当前无告警' }), { wide: true }));
            }
            if (deviceType !== 'switch' && extraMetricRows.length) {
                sections.push(renderSnmpFocusPanel('扩展指标', '自定义 OID 和厂商侧补充指标', renderSnmpMiniList(extraMetricRows.map(item => ({
                    label: item.label || '--',
                    meta: '扩展采集',
                    value: item.value || '--'
                })), { maxCount: 8, emptyText: '暂无扩展指标' }), { wide: true }));
            }
            if (deviceType === 'nvr') {
                const channels = Array.isArray(status.channels) ? status.channels : [];
                const hdds = Array.isArray(status.hdds) ? status.hdds : [];
                const offlineChannels = Array.isArray(status.offline_channels) ? status.offline_channels : [];
                if (channels.length) {
                    sections.push(renderSnmpFocusPanel('通道清单', '最多展示 64 路通道，预览栏按需抓拍单路画面', renderSnmpMiniList(channels.map(item => ({
                        label: `${item.name || `D${item.id || '--'}`}`,
                        meta: `${item.ip || '--'} · ${item.detect_result || item.protocol || '--'}`,
                        value: item.online ? '在线' : '离线',
                        level: item.online ? '' : 'warning'
                    })), { maxCount: 64, emptyText: '暂无通道清单' }), { wide: true }));
                }
                if (hdds.length) {
                    sections.push(renderSnmpFocusPanel('硬盘明细', '录像机存储盘健康与剩余空间', renderSnmpMiniList(hdds.map(item => ({
                        label: item.name || `HDD${item.id || ''}`,
                        meta: `${item.capacity_text || '--'} / 剩余 ${item.free_text || '--'} · ${item.property || '--'}`,
                        value: item.status_text || item.status || '--',
                        level: ['ok', 'normal', '正常'].includes(String(item.status || item.status_text || '').toLowerCase()) || item.status_text === '正常' ? '' : 'critical'
                    })), { maxCount: 8, emptyText: '暂无硬盘明细' }), { wide: true }));
                }
                if (offlineChannels.length) {
                    sections.push(renderSnmpFocusPanel('离线通道', '需要优先核对的摄像头通道', renderSnmpMiniList(offlineChannels.map(item => ({
                        label: item.name || `D${item.id || '--'}`,
                        meta: item.ip || item.detect_result || '--',
                        value: '离线',
                        level: 'warning'
                    })), { maxCount: 32, emptyText: '暂无离线通道' }), { wide: true }));
                }
            } else if (deviceType === 'nas') {
                const storageRows = Array.isArray(summary.storage_top_rows) ? summary.storage_top_rows : [];
                const diskRows = Array.isArray(summary.disk_top_rows) ? summary.disk_top_rows : [];
                const diskIoRows = Array.isArray(summary.ucd_disk_io_top_rows) ? summary.ucd_disk_io_top_rows : [];
                const gpuMetrics = Array.isArray(summary.gpu_metrics) ? summary.gpu_metrics : [];
                if (storageRows.length) sections.push(renderSnmpFocusPanel('卷与容量明细', '保留卷级别用量与容量信息', renderSnmpStorageList(storageRows), { wide: true }));
                if (diskRows.length) sections.push(renderSnmpFocusPanel('磁盘槽位', '盘位健康、温度与状态', renderSnmpDiskHealthList(diskRows), { wide: true }));
                if (diskIoRows.length) sections.push(renderSnmpFocusPanel('磁盘 I/O 热点', '高负载磁盘明细', renderSnmpDiskIoList(diskIoRows), { wide: true }));
                if (gpuMetrics.length) {
                    sections.push(renderSnmpFocusPanel('GPU 指标', '显卡与图形硬件采样', renderSnmpMiniList(gpuMetrics.map(item => ({
                        label: item.name || 'GPU',
                        meta: '图形硬件',
                        value: `${item.value ?? '--'}${item.unit ? ` ${item.unit}` : ''}`
                    })), { maxCount: 8, emptyText: '暂无 GPU 指标' }), { wide: true }));
                }
            } else if (deviceType === 'router') {
                const wanTraffic = Array.isArray(summary.wan_top_rows) ? summary.wan_top_rows : [];
                const lanTraffic = Array.isArray(summary.lan_top_rows) ? summary.lan_top_rows : [];
                const physicalTraffic = Array.isArray(summary.physical_top_rows) ? summary.physical_top_rows : [];
                sections.push(renderSnmpFocusPanel('链路流量明细', '保留 WAN、LAN 与其他链路实时流量', `
                    <div class="snmp-flow-grid">
                        <div class="snmp-flow-card wan"><div class="snmp-flow-title">WAN</div><div class="snmp-flow-list">${renderSnmpFlowList(wanTraffic, '暂无 WAN 流量')}</div></div>
                        <div class="snmp-flow-card lan"><div class="snmp-flow-title">LAN</div><div class="snmp-flow-list">${renderSnmpFlowList(lanTraffic, '暂无 LAN 流量')}</div></div>
                        <div class="snmp-flow-card physical"><div class="snmp-flow-title">其他链路</div><div class="snmp-flow-list">${renderSnmpFlowList(physicalTraffic, '暂无其他链路')}</div></div>
                    </div>
                `, { wide: true }));
            } else if (deviceType === 'switch') {
                const bridgePortMacRows = Array.isArray(interfaceSummary.bridge_port_mac_rows) ? interfaceSummary.bridge_port_mac_rows : [];
                const bridgeFdbRows = Array.isArray(interfaceSummary.bridge_fdb_rows) ? interfaceSummary.bridge_fdb_rows : [];
                const vendorRows = [
                    { label: '接口预览', value: summary.interface_preview || '--' },
                    { label: '位置 / 联系人', value: `${summary.location_text || '--'} / ${summary.contact_text || '--'}` },
                    { label: '轮询差值', value: `${summary.poll_elapsed_sec ?? '--'} s` }
                ];
                sections.push(renderSnmpFocusPanel('系统上下文', '设备级补充信息与桥接样本', `
                    ${renderSnmpMiniList(vendorRows.map(item => ({ label: item.label, value: item.value, meta: '设备信息' })), { maxCount: 3, emptyText: '暂无系统上下文' })}
                    ${renderSnmpMiniList(bridgePortMacRows.slice(0, 6).map(row => ({
                        label: `${row.port_name || '--'} (#${row.ifindex ?? '--'})`,
                        meta: `PVID ${row.pvid_name || '--'} · ${row.mac_preview || '--'}`,
                        value: `MAC ${row.mac_count ?? 0}`
                    })), { maxCount: 6, emptyText: '暂无接入口 MAC 学习数据' })}
                    ${renderSnmpMiniList(bridgeFdbRows.slice(0, 6).map(row => ({
                        label: `${row.port_name || '--'} · ${row.vlan_name || '--'}`,
                        meta: row.status || '--',
                        value: row.mac || '--'
                    })), { maxCount: 6, emptyText: '暂无桥表样本' })}
                `, { wide: true }));
            }
            return renderPersistedSnmpDetails(
                deviceId,
                'advanced',
                '更多监控信息',
                deviceType === 'switch' ? '桥接、系统上下文与补充异常' : (deviceType === 'router' ? '链路流量、扩展指标与告警' : '存储、硬件与扩展采样'),
                sections.join('') || '<div class="snmp-mini-empty">暂无更多信息</div>',
                false
            );
        }
        function buildSnmpMetricRows(customMetrics, excludeNames = [], maxCount = 8) {
            const excludes = new Set((Array.isArray(excludeNames) ? excludeNames : []).map(name => String(name || '').trim().toLowerCase()));
            return (Array.isArray(customMetrics) ? customMetrics : [])
                .filter(metric => {
                    const name = String(metric?.name || '').trim().toLowerCase();
                    if (!name || excludes.has(name)) return false;
                    const value = metric?.value;
                    return value !== undefined && value !== null && value !== '';
                })
                .slice(0, maxCount)
                .map(metric => ({
                    label: getSnmpMetricLabel(metric.name),
                    value: formatSnmpMetricValue(metric)
                }));
        }
        function renderSnmpInterfaceChips(interfaceSummary, deviceType) {
            const summary = interfaceSummary || {};
            const chips = [];
            const pushChip = (label, values, maxCount = 4) => {
                const list = Array.isArray(values) ? values.filter(Boolean).slice(0, maxCount) : [];
                if (!list.length) return;
                chips.push(`<span class="ups-alert-chip warning" style="color:#e2e8f0;background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.18);">${escapeHtml(label)}: ${escapeHtml(list.join(' / '))}</span>`);
            };
            const normalizedType = String(deviceType || '').trim().toLowerCase();
            if (normalizedType === 'router') {
                pushChip('WAN', summary.wan_names, 3);
                pushChip('LAN', summary.lan_names, 5);
                pushChip('物理口', summary.physical_names, 4);
                pushChip('聚合', summary.bond_names, 3);
                pushChip('活跃口', (Array.isArray(summary.active_top_rows) ? summary.active_top_rows : []).map(row => row?.name), 4);
            } else if (normalizedType === 'switch') {
                pushChip('物理口', summary.physical_names, 6);
                pushChip('桥接', summary.bridge_names, 3);
            } else {
                pushChip('物理口', summary.physical_names, 4);
                pushChip('聚合', summary.bond_names, 3);
                pushChip('桥接', summary.bridge_names, 3);
            }
            if (!chips.length) {
                pushChip('接口', summary.top_names, 6);
            }
            return chips.length
                ? chips.join('')
                : '<span class="ups-alert-chip warning" style="color:#cbd5e1;background:rgba(100,116,139,0.16);border:1px solid rgba(148,163,184,0.18);">当前无接口摘要</span>';
        }
        function renderSnmpPortPreview(interfaceSummary, deviceType) {
            const summary = interfaceSummary || {};
            const rows = Array.isArray(summary.port_preview_rows) ? summary.port_preview_rows : [];
            if (String(deviceType || '').trim().toLowerCase() !== 'switch' || !rows.length) return '';
            const rowHtml = rows.slice(0, 8).map(row => {
                const state = getSnmpSwitchPortState(row);
                const stateStyle = state.level === 'up'
                    ? 'color:#bbf7d0;background:rgba(16,185,129,0.14);border-color:rgba(16,185,129,0.28);'
                    : (state.level === 'down'
                        ? 'color:#fecaca;background:rgba(239,68,68,0.14);border-color:rgba(239,68,68,0.28);'
                        : 'color:#fde68a;background:rgba(245,158,11,0.14);border-color:rgba(245,158,11,0.28);');
                const aliasText = row.alias && row.alias !== row.name ? escapeHtml(row.alias) : '标准端口';
                return `<div class="snmp-port-card ${escapeHtml(state.cardClass)}">
                    <div class="snmp-port-name">${escapeHtml(row.name || '--')}</div>
                    <div class="snmp-port-meta">${escapeHtml(row.speed_text || '--')} · ${aliasText}</div>
                    <div class="snmp-port-status-row">
                        <span class="ups-chip" style="${stateStyle}">${escapeHtml(state.text)}</span>
                        <span class="ups-chip">${row.admin_up ? '管理开' : '管理关'}</span>
                    </div>
                </div>`;
            }).join('');
            return `<div class="snmp-port-grid">${rowHtml}</div>`;
        }
        function getSnmpAlertLevel(level) {
            const normalized = String(level || '').trim().toLowerCase();
            if (normalized === 'critical') return 'critical';
            if (normalized === 'warning') return 'warning';
            return 'normal';
        }
        function renderSnmpFlowList(rows, emptyText = '当前无流量数据') {
            const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
            if (!list.length) {
                return `<div class="snmp-flow-item"><div class="snmp-flow-item-name">${escapeHtml(emptyText)}</div></div>`;
            }
            return list.slice(0, 4).map(row => `<div class="snmp-flow-item">
                <div class="snmp-flow-item-name">${escapeHtml(row.name || '--')}</div>
                <div class="snmp-flow-item-meta">实时 ${escapeHtml(row.traffic_text || '--')}</div>
                <div class="snmp-flow-item-meta">累计 ${escapeHtml(row.in_bytes_text || '--')} / ${escapeHtml(row.out_bytes_text || '--')}</div>
                <div class="snmp-flow-item-meta">速率 ${escapeHtml(row.total_rate_text || '--')} · ${escapeHtml(row.speed_text || '--')}</div>
            </div>`).join('');
        }
        function renderSnmpStorageList(rows) {
            const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
            if (!list.length) {
                return '<div class="snmp-storage-item"><div class="snmp-storage-name">当前无存储卷摘要</div></div>';
            }
            return `<div class="snmp-storage-list">${list.slice(0, 10).map(row => {
                const level = getSnmpAlertLevel(row.alert_level);
                const percent = Number.isFinite(Number(row.usage_percent)) ? Math.max(0, Math.min(100, Number(row.usage_percent))) : 0;
                const capacityLabel = row.quota_view ? '配额' : '总量';
                const roleText = row.capacity_role === 'lun_quota' ? 'LUN' : (row.quota_view ? '共享' : '卷');
                return `<div class="snmp-storage-item ${level}">
                    <div class="snmp-storage-top">
                        <div class="snmp-storage-name">${escapeHtml(row.descr || '--')}</div>
                        <div class="snmp-storage-usage">${escapeHtml(String(row.usage_percent ?? '--'))}%</div>
                    </div>
                    <div class="snmp-storage-bar"><div class="snmp-storage-fill" style="width:${percent}%;"></div></div>
                    <div class="snmp-storage-meta">${escapeHtml(roleText)} · 已用 ${escapeHtml(row.used_text || '--')} / ${escapeHtml(capacityLabel)} ${escapeHtml(row.total_text || '--')}</div>
                </div>`;
            }).join('')}</div>`;
        }
        function renderSnmpCapacityHero(summary, options = {}) {
            const capacity = summarizeSnmpStorageCapacity(summary);
            const rows = getSnmpStorageDisplayRows(summary, options.limit || 8);
            if (!rows.length) {
                return '<div class="snmp-mini-empty">当前未采到容量信息</div>';
            }
            const totalPercent = capacity.percent !== null ? Math.max(0, Math.min(100, Number(capacity.percent))) : 0;
            const mainLevel = totalPercent >= 92 ? 'critical' : (totalPercent >= 85 ? 'warning' : 'normal');
            const topRows = rows.slice(0, Math.max(1, Number(options.limit) || 8));
            const isQuotaMode = capacity.mode === 'qnap_quota';
            const titleText = options.title || (isQuotaMode ? '共享文件夹 / LUN 配额' : '容量总览');
            const noteText = isQuotaMode
                ? `共享已用合计 ${capacity.usedText} · ${capacity.rows.length} 项 · ${capacity.note}`
                : `合计已用 ${capacity.usedText} / 总量 ${capacity.totalText} · 卷 ${capacity.rows.length}`;
            return `<div class="snmp-capacity-block ${escapeHtml(mainLevel)}">
                <div class="snmp-capacity-head">
                    <div>
                        <div class="snmp-capacity-title">${escapeHtml(titleText)}</div>
                        <div class="snmp-capacity-note">${escapeHtml(noteText)}</div>
                    </div>
                    <div class="snmp-capacity-percent">${escapeHtml(isQuotaMode ? '配额视图' : (capacity.percent !== null ? `${capacity.percent}%` : '--'))}</div>
                </div>
                ${isQuotaMode ? '<div class="snmp-capacity-quota-note">SNMP 返回的是共享文件夹和 LUN 的配额用量，不与物理存储池容量相加。</div>' : `<div class="snmp-storage-bar capacity"><div class="snmp-storage-fill" style="width:${totalPercent}%;"></div></div>`}
                <div class="snmp-capacity-grid">${topRows.map(row => {
                    const level = getSnmpAlertLevel(row.alert_level);
                    const percent = Number.isFinite(Number(row.usage_percent)) ? Math.max(0, Math.min(100, Number(row.usage_percent))) : 0;
                    const roleText = row.capacity_role === 'lun_quota' ? 'LUN' : (row.quota_view ? '共享' : '卷');
                    return `<div class="snmp-capacity-volume ${escapeHtml(level)}">
                        <div class="snmp-capacity-volume-top">
                            <span>${escapeHtml(row.descr || '--')}</span>
                            <strong>${escapeHtml(String(row.usage_percent ?? '--'))}%</strong>
                        </div>
                        <div class="snmp-storage-bar"><div class="snmp-storage-fill" style="width:${percent}%;"></div></div>
                        <div class="snmp-capacity-volume-meta">${escapeHtml(roleText)} · ${escapeHtml(row.used_text || '--')} / ${escapeHtml(row.total_text || '--')}</div>
                    </div>`;
                }).join('')}</div>
            </div>`;
        }
        function renderSnmpDiskHealthList(rows) {
            const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
            if (!list.length) {
                return '<div class="snmp-storage-item"><div class="snmp-storage-name">当前未采到盘位健康信息</div></div>';
            }
            return `<div class="snmp-storage-list">${list.slice(0, 6).map(row => {
                const level = getSnmpAlertLevel(row.alert_level);
                const statusText = row.status || '--';
                const tempText = row.temp_text || '--';
                const capacityText = row.capacity_text || '--';
                const metaParts = [row.vendor, row.bus, row.model].filter(item => item && item !== '--');
                return `<div class="snmp-storage-item ${level}">
                    <div class="snmp-storage-top">
                        <div class="snmp-storage-name">${escapeHtml(row.slot || '--')}</div>
                        <div class="snmp-storage-usage">${escapeHtml(statusText)}</div>
                    </div>
                    <div class="snmp-storage-meta">温度 ${escapeHtml(tempText)} · 容量 ${escapeHtml(capacityText)}</div>
                    <div class="snmp-storage-meta">${escapeHtml(metaParts.join(' / ') || '磁盘信息已采集')}</div>
                </div>`;
            }).join('')}</div>`;
        }
        function renderQnapDriveBayPanel(summary) {
            const baySummary = summary?.drive_bay_summary || {};
            const hddBays = Array.isArray(baySummary.hdd_bays) ? baySummary.hdd_bays : [];
            const ssdBays = Array.isArray(baySummary.ssd_bays) ? baySummary.ssd_bays : [];
            if (!hddBays.length && !ssdBays.length) {
                return '';
            }
            const installedHdd = baySummary.hdd_count ?? hddBays.filter(item => item?.occupied !== false).length;
            const installedSsd = baySummary.ssd_count ?? ssdBays.filter(item => item?.occupied !== false).length;
            const emptyCount = baySummary.empty_count ?? [...hddBays, ...ssdBays].filter(item => item?.occupied === false).length;
            const criticalCount = Number(baySummary.critical_count || 0);
            const warningCount = Number(baySummary.warning_count || 0);
            const healthText = criticalCount > 0 ? `严重 ${criticalCount}` : (warningCount > 0 ? `告警 ${warningCount}` : '良好');
            const healthLevel = criticalCount > 0 ? 'critical' : (warningCount > 0 ? 'warning' : 'normal');
            const renderBay = (bay) => {
                const occupied = bay?.occupied !== false;
                const level = occupied ? getSnmpAlertLevel(bay?.alert_level) : 'empty';
                const statusText = occupied ? (bay?.status || '--') : '空槽';
                const modelText = occupied ? (bay?.model || bay?.capacity_text || '已安装') : '空槽';
                const tempText = occupied ? (bay?.temp_text || '--') : '--';
                return `<div class="qnap-drive-bay ${escapeHtml(level)} ${occupied ? 'occupied' : 'empty'}" title="${escapeHtml(`${bay?.display_slot || '--'} · ${statusText} · ${tempText} · ${modelText}`)}">
                    <div class="qnap-drive-led"></div>
                    <div class="qnap-drive-face"></div>
                    <span class="qnap-drive-slot">${escapeHtml(bay?.display_slot || '--')}</span>
                </div>`;
            };
            return `<div class="qnap-chassis-panel">
                <div class="qnap-chassis-head">
                    <div>
                        <div class="qnap-chassis-title">NAS 主机 ${escapeHtml(summary?.host || '192.168.30.145')}</div>
                        <div class="qnap-chassis-note">图示按 QNAP 正面盘位模拟，颜色来自 SNMP 健康状态。</div>
                    </div>
                    <div class="qnap-chassis-summary ${escapeHtml(healthLevel)}">${escapeHtml(healthText)}</div>
                </div>
                <div class="qnap-chassis-body">
                    <div class="qnap-device-illustration" aria-label="QNAP NAS 盘位图示">
                        <div class="qnap-device-left">
                            <div class="qnap-logo-dot">QNAP</div>
                            <div class="qnap-status-lights"><span></span><span></span><span></span><span></span></div>
                            <div class="qnap-button"></div>
                            <div class="qnap-usb"></div>
                        </div>
                        <div class="qnap-drive-stack hdd">${hddBays.map(renderBay).join('')}</div>
                        <div class="qnap-drive-stack ssd">${ssdBays.map(renderBay).join('')}</div>
                    </div>
                    <div class="qnap-device-caption">
                        <div class="qnap-device-name">NAS-shenlan</div>
                        <div class="qnap-device-ratio">1 / 1</div>
                        <div class="qnap-device-health ${escapeHtml(healthLevel)}"><span></span>${escapeHtml(healthText)}</div>
                        <div class="qnap-device-meta">HDD ${escapeHtml(String(installedHdd))} · SSD ${escapeHtml(String(installedSsd))} · 空槽 ${escapeHtml(String(emptyCount))}</div>
                    </div>
                </div>
            </div>`;
        }
        function renderSnmpFanList(rows) {
            const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
            if (!list.length) {
                return '';
            }
            return `<div class="ups-alert-list">${list.slice(0, 6).map(row => {
                const className = row.alert_level === 'warning' ? 'warning' : '';
                return `<span class="ups-alert-chip ${className}">${escapeHtml(row.name || '--')} · ${escapeHtml(row.rpm_text || '--')}</span>`;
            }).join('')}</div>`;
        }
        function renderSnmpDiskIoList(rows) {
            const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
            if (!list.length) {
                return '';
            }
            const groups = [
                { title: '系统盘', icon: 'SYS', rows: list.filter(row => String(row.device || '').startsWith('nvme') || String(row.device || '').startsWith('md')) },
                { title: '数据盘', icon: 'DATA', rows: list.filter(row => /^sd[a-z]+$/i.test(String(row.device || ''))) },
                { title: '其他磁盘', icon: 'I/O', rows: list.filter(row => !String(row.device || '').startsWith('nvme') && !String(row.device || '').startsWith('md') && !/^sd[a-z]+$/i.test(String(row.device || ''))) }
            ].filter(group => group.rows.length);
            return groups.map(group => `<div class="snmp-highlight-panel">
                <div class="snmp-highlight-title">${escapeHtml(group.icon)} · ${escapeHtml(group.title)}</div>
                <div class="snmp-highlight-note">按飞牛当前磁盘 I/O 热点排序展示，优先看读写最活跃的设备。</div>
                <div class="snmp-storage-list">${group.rows.slice(0, 4).map(row => {
                const level = getSnmpAlertLevel(row.alert_level);
                return `<div class="snmp-storage-item ${level}">
                    <div class="snmp-storage-top">
                        <div class="snmp-storage-name">${escapeHtml(row.device || '--')}</div>
                        <div class="snmp-storage-usage">${escapeHtml(row.load_peak_text || '--')}</div>
                    </div>
                    <div class="snmp-storage-meta">读取 ${escapeHtml(row.bytes_read_text || '--')} · 写入 ${escapeHtml(row.bytes_written_text || '--')}</div>
                    <div class="snmp-storage-meta">读次数 ${escapeHtml(row.reads_text || '--')} · 写次数 ${escapeHtml(row.writes_text || '--')}</div>
                </div>`;
            }).join('')}</div></div>`).join('');
        }
        function renderSnmpHighlightPanel(title, note, chips, level = '') {
            const list = Array.isArray(chips) ? chips.filter(Boolean) : [];
            if (!list.length) {
                return '';
            }
            return `<div class="snmp-highlight-panel ${escapeHtml(level)}">
                <div class="snmp-highlight-title">${escapeHtml(title || '--')}</div>
                ${note ? `<div class="snmp-highlight-note">${escapeHtml(note)}</div>` : ''}
                <div class="ups-alert-list">${list.join('')}</div>
            </div>`;
        }
        function renderSnmpSpotlightCards(items) {
            const list = Array.isArray(items) ? items.filter(item => item && (item.label || item.value || item.meta)) : [];
            if (!list.length) {
                return '';
            }
            return `<div class="snmp-spotlight-grid">${list.map(item => `
                <div class="snmp-spotlight-card ${escapeHtml(item.level || '')}">
                    <div class="snmp-spotlight-label">${escapeHtml(item.label || '--')}</div>
                    <div class="snmp-spotlight-value">${escapeHtml(String(item.value ?? '--'))}</div>
                    ${item.meta ? `<div class="snmp-spotlight-meta">${escapeHtml(String(item.meta))}</div>` : ''}
                </div>
            `).join('')}</div>`;
        }
        function renderSnmpSwitchSegments(summary, portRows) {
            const rows = Array.isArray(portRows) ? portRows : [];
            if (!rows.length) {
                return '';
            }
            const anomalyRows = rows.filter(row => Number(row.discard_delta_total || 0) > 0 || Number(row.error_delta_total || 0) > 0 || Number(row.utilization_percent || 0) >= 80).slice(0, 4);
            const uplinkRows = rows.filter(row => !!row.is_uplink).slice(0, 4);
            const offlineRows = rows.filter(row => getSnmpSwitchPortState(row).level === 'down').slice(0, 4);
            const unknownRows = rows.filter(row => getSnmpSwitchPortState(row).level === 'unknown').slice(0, 4);
            const segments = [
                {
                    title: '异常端口',
                    note: '新增错包、丢弃和高利用率优先展示',
                    level: anomalyRows.some(row => Number(row.discard_delta_total || 0) > 0) ? 'critical' : (anomalyRows.length ? 'warning' : ''),
                    rows: anomalyRows,
                    empty: '当前没有新增异常口'
                },
                {
                    title: '上联端口',
                    note: '核心链路与高速上行口',
                    level: '',
                    rows: uplinkRows,
                    empty: '当前未识别到上联口'
                },
                {
                    title: '离线端口',
                    note: '明确返回链路 down 的端口',
                    level: offlineRows.length ? 'warning' : '',
                    rows: offlineRows,
                    empty: '当前没有离线物理口'
                },
                {
                    title: '状态未采到',
                    note: '管理开启但本轮缺少 operStatus，不计入离线告警',
                    level: unknownRows.length ? 'warning' : '',
                    rows: unknownRows,
                    empty: '当前没有未采到状态的物理口'
                }
            ];
            return `<div class="snmp-switch-segment-grid">${segments.map(segment => `
                <div class="snmp-switch-segment ${escapeHtml(segment.level || '')}">
                    <div class="snmp-switch-segment-title">${escapeHtml(segment.title)}</div>
                    <div class="snmp-switch-segment-note">${escapeHtml(segment.note)}</div>
                    <div class="snmp-switch-segment-list">${segment.rows.length ? segment.rows.map(row => {
                        const chips = [];
                        if (Number(row.discard_delta_total || 0) > 0) chips.push(`新增丢弃 ${row.discard_delta_total}`);
                        if (Number(row.error_delta_total || 0) > 0) chips.push(`新增错包 ${row.error_delta_total}`);
                        if (Number(row.utilization_percent || 0) >= 80) chips.push(`利用率 ${row.utilization_text || '--'}`);
                        if (!chips.length) chips.push(row.total_rate_text || row.speed_text || '--');
                        return `<div class="snmp-switch-segment-item">
                            <div class="snmp-switch-segment-item-top">
                                <div class="snmp-switch-segment-name">${escapeHtml(row.name || '--')}</div>
                                ${(() => {
                                    const state = getSnmpSwitchPortState(row);
                                    return `<span class="snmp-mini-chip ${escapeHtml(state.chipClass)}">${escapeHtml(state.text)}</span>`;
                                })()}
                            </div>
                            <div class="snmp-switch-segment-meta">${escapeHtml(row.speed_text || '--')} · ${escapeHtml(chips.join(' / '))}</div>
                        </div>`;
                    }).join('') : `<div class="snmp-switch-segment-item"><div class="snmp-switch-segment-name">${escapeHtml(segment.empty)}</div></div>`}</div>
                </div>
            `).join('')}</div>`;
        }
        function renderSnmpVendorCards(items) {
            const list = Array.isArray(items) ? items.filter(item => item && (item.title || item.note || item.rows)) : [];
            if (!list.length) return '';
            return `<div class="snmp-vendor-grid">${list.map(item => {
                const level = getSnmpAlertLevel(item.level);
                const rows = Array.isArray(item.rows) ? item.rows.filter(row => row && (row.label || row.value)) : [];
                const body = rows.length
                    ? `<div class="snmp-dense-list">${rows.map(row => `<div class="snmp-dense-row"><div class="snmp-dense-key">${escapeHtml(row.label || '--')}</div><div class="snmp-dense-value">${escapeHtml(String(row.value ?? '--'))}</div></div>`).join('')}</div>`
                    : `<div class="snmp-dense-list"><div class="snmp-dense-row"><div class="snmp-dense-key">当前状态</div><div class="snmp-dense-value">暂无扩展指标</div></div></div>`;
                return `<div class="snmp-vendor-card ${escapeHtml(level)}">
                    <div class="snmp-vendor-card-title">${escapeHtml(item.title || '扩展信息')}</div>
                    ${item.note ? `<div class="snmp-vendor-card-note">${escapeHtml(item.note)}</div>` : ''}
                    ${body}
                </div>`;
            }).join('')}</div>`;
        }
        function getSnmpPortPanelSortValue(row, mode) {
            const current = row || {};
            const normalizedMode = String(mode || 'index').trim().toLowerCase();
            if (normalizedMode === 'traffic') {
                return -(Number(current.total_rate_bps || 0) || 0);
            }
            if (normalizedMode === 'anomaly') {
                return -(
                    (Number(current.discard_delta_total || 0) * 1000000) +
                    (Number(current.error_delta_total || 0) * 10000) +
                    (Number(current.discard_total || 0) * 100) +
                    Number(current.utilization_percent || 0)
                );
            }
            return Number(current.index || 999999);
        }
        function sortSnmpPortRows(rows, mode = 'index') {
            const list = Array.isArray(rows) ? rows.slice() : [];
            const normalizedMode = String(mode || 'index').trim().toLowerCase();
            return list.sort((a, b) => {
                const diff = getSnmpPortPanelSortValue(a, normalizedMode) - getSnmpPortPanelSortValue(b, normalizedMode);
                if (diff !== 0) return diff;
                return String(a?.name || '').localeCompare(String(b?.name || ''), 'zh-CN');
            });
        }
        function renderSnmpSwitchPortPanels(deviceId, portRows) {
            const rows = Array.isArray(portRows) ? portRows.filter(Boolean) : [];
            if (!rows.length) return '';
            const sections = [
                {
                    key: 'anomaly',
                    title: '异常端口面板',
                    note: '按异常优先级排序，先看新增丢弃、错包和高利用率端口。',
                    open: true,
                    sort: 'anomaly',
                    rows: rows.filter(row => Number(row.discard_delta_total || 0) > 0 || Number(row.error_delta_total || 0) > 0 || Number(row.utilization_percent || 0) >= 80)
                },
                {
                    key: 'uplink',
                    title: '上联与高速链路',
                    note: '按实时吞吐排序，聚焦核心上联、级联和高速链路。',
                    open: false,
                    sort: 'traffic',
                    rows: rows.filter(row => !!row.is_uplink || Number(row.speed_bps || 0) >= 10000000000)
                },
                {
                    key: 'online',
                    title: '在线端口明细',
                    note: '按端口号排序，展示当前链路 up 的物理口和实时带宽。',
                    open: false,
                    sort: 'index',
                    rows: rows.filter(row => !!row.oper_up)
                },
                {
                    key: 'offline',
                    title: '离线端口明细',
                    note: '按端口号排序，只展示明确返回链路 down 的物理口。',
                    open: false,
                    sort: 'index',
                    rows: rows.filter(row => getSnmpSwitchPortState(row).level === 'down')
                },
                {
                    key: 'unknown',
                    title: '状态未采到端口',
                    note: '管理开启但本轮未拿到 operStatus，先不作为离线告警。',
                    open: false,
                    sort: 'index',
                    rows: rows.filter(row => getSnmpSwitchPortState(row).level === 'unknown')
                }
            ];
            return sections.map(section => {
                const sortedRows = sortSnmpPortRows(section.rows, section.sort || 'index');
                const contentRows = sortedRows.slice(0, 24);
                const gridClass = contentRows.length <= 1 ? 'single' : '';
                const detailStateKey = buildSnmpDetailStateKey(deviceId || 'switch-panel', section.key);
                const isOpen = Object.prototype.hasOwnProperty.call(snmpOpenDetailsState, detailStateKey)
                    ? !!snmpOpenDetailsState[detailStateKey]
                    : !!(section.open && contentRows.length);
                return `<details class="snmp-switch-port-panel" data-snmp-detail-key="${escapeHtml(detailStateKey)}" ${isOpen ? 'open' : ''}>
                    <summary>
                        <div>
                            <div class="snmp-switch-port-panel-title">${escapeHtml(section.title)}</div>
                            <div class="snmp-switch-port-panel-meta">${escapeHtml(section.note)}</div>
                        </div>
                        <div class="snmp-switch-port-panel-count">${escapeHtml(String(section.rows.length))} 个端口</div>
                    </summary>
                    <div class="snmp-switch-port-panel-body">
                        ${contentRows.length ? `<div class="snmp-switch-port-panel-grid ${gridClass}">${contentRows.map(row => {
                            const state = getSnmpSwitchPortState(row);
                            const isUp = state.level === 'up';
                            const isUplink = !!row.is_uplink;
                            const discardDelta = Number(row.discard_delta_total || 0);
                            const errorDelta = Number(row.error_delta_total || 0);
                            const utilization = Number(row.utilization_percent || 0);
                            const anomalyLevel = discardDelta > 0 ? 'critical' : ((errorDelta > 0 || utilization >= 80) ? 'warning' : '');
                            const alias = row.alias && row.alias !== row.name ? row.alias : '标准端口';
                            const chips = [];
                            chips.push(`<span class="ups-chip ${escapeHtml(state.chipClass)}">${escapeHtml(state.text)}</span>`);
                            chips.push(`<span class="ups-chip">${row.admin_up ? '管理开' : '管理关'}</span>`);
                            if (isUplink) chips.push('<span class="ups-chip" style="color:#bfdbfe;background:rgba(59,130,246,0.14);border-color:rgba(59,130,246,0.28);">上联</span>');
                            const anomalyChips = [];
                            if (discardDelta > 0) anomalyChips.push(`<span class="snmp-mini-chip error">新增丢弃 ${escapeHtml(String(discardDelta))}</span>`);
                            if (errorDelta > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">新增错包 ${escapeHtml(String(errorDelta))}</span>`);
                            if (Number(row.in_discards_delta || 0) > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">入丢弃 ${escapeHtml(String(row.in_discards_delta || 0))}</span>`);
                            if (Number(row.out_discards_delta || 0) > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">出丢弃 ${escapeHtml(String(row.out_discards_delta || 0))}</span>`);
                            if (Number(row.in_errors_delta || 0) > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">入错包 ${escapeHtml(String(row.in_errors_delta || 0))}</span>`);
                            if (Number(row.out_errors_delta || 0) > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">出错包 ${escapeHtml(String(row.out_errors_delta || 0))}</span>`);
                            if (utilization >= 80) anomalyChips.push(`<span class="snmp-mini-chip info">利用率 ${escapeHtml(row.utilization_text || '--')}</span>`);
                            return `<div class="snmp-switch-port ${escapeHtml(state.cardClass)} ${isUplink ? 'uplink' : ''} ${anomalyLevel}">
                                <div class="snmp-switch-port-head">
                                    <div class="snmp-switch-port-name">${escapeHtml(row.name || '--')}</div>
                                    <div class="snmp-switch-port-index">#${escapeHtml(String(row.index ?? '--'))}</div>
                                </div>
                                <div class="snmp-switch-port-meta">${escapeHtml(row.speed_text || '--')} · ${escapeHtml(alias)}</div>
                                <div class="snmp-switch-port-meta">PVID ${escapeHtml(row.pvid_name || '--')} · VLAN ${escapeHtml(String(row.learned_vlan_count ?? 0))} · MAC ${escapeHtml(String(row.learned_mac_count ?? 0))}</div>
                                <div class="snmp-switch-port-meta">入 / 出 ${escapeHtml(row.in_rate_text || '--')} / ${escapeHtml(row.out_rate_text || '--')}</div>
                                <div class="snmp-switch-port-meta">总速率 ${escapeHtml(row.total_rate_text || '--')} · 利用率 ${escapeHtml(row.utilization_text || '--')}</div>
                                <div class="snmp-switch-port-meta">累计 ${escapeHtml(row.in_bytes_text || '--')} / ${escapeHtml(row.out_bytes_text || '--')}</div>
                                <div class="snmp-switch-port-meta">错包 ${escapeHtml(String(row.error_total ?? 0))} · 丢弃 ${escapeHtml(String(row.discard_total ?? 0))}</div>
                                <div class="snmp-switch-port-status">${chips.join('')}</div>
                                ${anomalyChips.length ? `<div class="snmp-switch-port-badges">${anomalyChips.join('')}</div>` : ''}
                            </div>`;
                        }).join('')}</div>` : `<div class="snmp-dense-list"><div class="snmp-dense-row"><div class="snmp-dense-key">当前状态</div><div class="snmp-dense-value">这一组暂无端口</div></div></div>`}
                    </div>
                </details>`;
            }).join('');
        }
        function renderSnmpHealthBanner(summary) {
            const level = String(summary.risk_level || 'normal').trim().toLowerCase();
            const score = summary.health_score !== undefined && summary.health_score !== null ? String(summary.health_score) : '--';
            const counts = summary.alert_counts || {};
            const chips = [
                `<span class="ups-alert-chip ${level === 'critical' ? 'error' : (level === 'warning' ? 'warning' : '')}">风险等级 ${escapeHtml(level === 'critical' ? '高' : (level === 'warning' ? '中' : '低'))}</span>`,
                `<span class="ups-alert-chip">严重 ${escapeHtml(String(counts.critical ?? 0))}</span>`,
                `<span class="ups-alert-chip">告警 ${escapeHtml(String(counts.warning ?? 0))}</span>`,
                `<span class="ups-alert-chip">提示 ${escapeHtml(String(counts.info ?? 0))}</span>`
            ];
            return `<div class="snmp-health-banner ${escapeHtml(level)}">
                <div class="snmp-health-head">
                    <div class="snmp-health-title">设备健康状态</div>
                    <div class="snmp-health-score">${escapeHtml(score)}</div>
                </div>
                <div class="ups-alert-list">${chips.join('')}</div>
            </div>`;
        }
        function getSnmpDeviceIcon(deviceType) {
            const normalized = String(deviceType || '').trim().toLowerCase();
            if (normalized === 'nas') return '🗄';
            if (normalized === 'router') return '🌐';
            if (normalized === 'switch') return '🔀';
            if (normalized === 'server') return '🖥';
            if (normalized === 'nvr') return '🎥';
            return '📡';
        }
        function renderSnmpSwitchSection(summary) {
            const interfaceSummary = summary.interface_summary || {};
            const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
            const portRows = switchStats.rows;
            const upCount = switchStats.upCount;
            const physicalCount = switchStats.physicalCount;
            const downCount = switchStats.downCount;
            const unknownCount = switchStats.unknownCount;
            const uplinkCount = switchStats.uplinkCount;
            const criticalClass = downCount >= Math.max(4, Math.floor(physicalCount * 0.25)) ? 'critical' : (downCount > 0 ? 'warning' : '');
            const topPortRows = sortSnmpPortRows(portRows, 'anomaly').slice(0, 12);
            const topBusyRows = sortSnmpPortRows(portRows.filter(row => Number(row.total_rate_bps || 0) > 0), 'traffic').slice(0, 4);
            const bridgeVlanRows = Array.isArray(interfaceSummary.bridge_vlan_rows) ? interfaceSummary.bridge_vlan_rows : [];
            const bridgePortMacRows = Array.isArray(interfaceSummary.bridge_port_mac_rows) ? interfaceSummary.bridge_port_mac_rows : [];
            const bridgeFdbRows = Array.isArray(interfaceSummary.bridge_fdb_rows) ? interfaceSummary.bridge_fdb_rows : [];
            const spotlightHtml = renderSnmpSpotlightCards([
                { label: '交换总吞吐', value: getSnmpBestThroughputDisplay(interfaceSummary), meta: `${getSnmpBestThroughputPair(interfaceSummary)}` },
                { label: '异常端口', value: `${interfaceSummary.delta_error_port_count ?? 0} / ${interfaceSummary.delta_discard_port_count ?? 0}`, meta: '新增错包口 / 新增丢弃口', level: Number(interfaceSummary.delta_discard_port_count || 0) > 0 ? 'critical' : (Number(interfaceSummary.delta_error_port_count || 0) > 0 ? 'warning' : '') },
                { label: '在线 / 离线', value: `${upCount} / ${downCount}`, meta: `未采到 ${unknownCount} · 物理 ${physicalCount} · 上联 ${uplinkCount}`, level: downCount > 0 ? 'warning' : '' },
                { label: '忙碌端口', value: String(interfaceSummary.busy_port_count ?? 0), meta: '利用率较高的物理端口', level: Number(interfaceSummary.busy_port_count || 0) >= 4 ? 'warning' : '' },
                { label: '学习 MAC', value: `${switchStats.learnedMacCount ?? 0}`, meta: `总 MAC ${switchStats.bridgeMacCount ?? 0} · VLAN ${switchStats.bridgeVlanCount ?? 0}` },
                { label: '桥端口', value: `${interfaceSummary.bridge_port_count ?? 0}`, meta: 'Bridge-MIB / Q-BRIDGE-MIB', level: Number(interfaceSummary.bridge_port_count || 0) > 0 ? '' : 'warning' }
            ]);
            const portHtml = topPortRows.length
                ? `<div class="snmp-switch-port-grid">${topPortRows.map(row => {
                    const state = getSnmpSwitchPortState(row);
                    const isUp = state.level === 'up';
                    const isUplink = !!row.is_uplink;
                    const alias = row.alias && row.alias !== row.name ? row.alias : '标准端口';
                    const discardDelta = Number(row.discard_delta_total || 0);
                    const errorDelta = Number(row.error_delta_total || 0);
                    const utilization = Number(row.utilization_percent || 0);
                    const anomalyLevel = discardDelta > 0 ? 'critical' : ((errorDelta > 0 || utilization >= 80) ? 'warning' : '');
                    const statusChips = [];
                    if (isUplink) statusChips.push('<span class="ups-chip" style="color:#bfdbfe;background:rgba(59,130,246,0.14);border-color:rgba(59,130,246,0.28);">上联</span>');
                    statusChips.push(`<span class="ups-chip ${escapeHtml(state.chipClass)}">${escapeHtml(state.text)}</span>`);
                    statusChips.push(`<span class="ups-chip">${row.admin_up ? '管理开' : '管理关'}</span>`);
                    const anomalyChips = [];
                    if (discardDelta > 0) anomalyChips.push(`<span class="snmp-mini-chip error">新增丢弃 ${escapeHtml(String(discardDelta))}</span>`);
                    if (errorDelta > 0) anomalyChips.push(`<span class="snmp-mini-chip warning">新增错包 ${escapeHtml(String(errorDelta))}</span>`);
                            if (utilization >= 80) anomalyChips.push(`<span class="snmp-mini-chip info">利用率 ${escapeHtml(row.utilization_text || '--')}</span>`);
                            if (isUplink && !anomalyChips.length) anomalyChips.push('<span class="snmp-mini-chip online">核心链路</span>');
                            if (Number(row.learned_mac_count || 0) > 0) anomalyChips.push(`<span class="snmp-mini-chip online">MAC ${escapeHtml(String(row.learned_mac_count || 0))}</span>`);
                            if (row.pvid) anomalyChips.push(`<span class="snmp-mini-chip info">PVID ${escapeHtml(String(row.pvid))}</span>`);
                            return `<div class="snmp-switch-port ${escapeHtml(state.cardClass)} ${isUplink ? 'uplink' : ''} ${anomalyLevel}">
                                <div class="snmp-switch-port-head">
                                    <div class="snmp-switch-port-name">${escapeHtml(row.name || '--')}</div>
                                    <div class="snmp-switch-port-index">#${escapeHtml(String(row.index ?? '--'))}</div>
                                </div>
                                <div class="snmp-switch-port-meta">${escapeHtml(row.speed_text || '--')} · ${escapeHtml(alias)}</div>
                                <div class="snmp-switch-port-meta">实时 ${escapeHtml(row.traffic_text || '--')} · ${escapeHtml(row.total_rate_text || '--')}</div>
                                <div class="snmp-switch-port-meta">利用率 ${escapeHtml(row.utilization_text || '--')} · 错包 ${escapeHtml(String(row.error_total ?? 0))} · 丢弃 ${escapeHtml(String(row.discard_total ?? 0))}</div>
                                <div class="snmp-switch-port-meta">累计 ${escapeHtml(row.in_bytes_text || '--')} / ${escapeHtml(row.out_bytes_text || '--')}</div>
                                <div class="snmp-switch-port-meta">PVID ${escapeHtml(row.pvid_name || '--')} · 学习 MAC ${escapeHtml(String(row.learned_mac_count ?? 0))}</div>
                                <div class="snmp-switch-port-status">${statusChips.join('')}</div>
                                ${anomalyChips.length ? `<div class="snmp-switch-port-badges">${anomalyChips.join('')}</div>` : ''}
                            </div>`;
                        }).join('')}</div>`
                : '<div class="snmp-switch-port">当前无端口摘要</div>';
            const switchVendorHtml = renderSnmpVendorCards([
                {
                    title: '交换机系统信息',
                    note: '补充交换机本体运行上下文，方便区分设备级问题和端口级问题。',
                    rows: [
                        { label: '系统描述', value: compactSnmpText(summary.sys_descr_text || '--', 72) },
                        { label: '运行时长', value: summary.uptime_text || '--' },
                        { label: '接口预览', value: summary.interface_preview || '--' },
                        { label: '位置 / 联系人', value: `${summary.location_text || '--'} / ${summary.contact_text || '--'}` },
                        { label: '健康分', value: `${summary.health_score ?? '--'} / ${summary.risk_level || '--'}` },
                        { label: '轮询差值', value: `${summary.poll_elapsed_sec ?? '--'} s` }
                    ]
                },
                {
                    title: '当前热点端口',
                    note: '按总吞吐排序，优先看当前最忙的几个口。',
                    rows: topBusyRows.map(row => ({
                        label: `${row.name || '--'} (#${row.index ?? '--'})`,
                        value: `${row.total_rate_text || '--'} · ${row.utilization_text || '--'}`
                    }))
                },
                {
                    title: 'VLAN 学习摘要',
                    note: '按学习到的 MAC 数排序，快速看当前最活跃的 VLAN。',
                    rows: bridgeVlanRows.map(row => ({
                        label: `${row.vlan_name || `VLAN ${row.vlan_id ?? '--'}`}`,
                        value: `MAC ${row.mac_count ?? 0} · 端口 ${row.port_count ?? 0} · ${row.ports_preview || '--'}`
                    }))
                },
                {
                    title: '接入口学习概况',
                    note: '按端口学习到的 MAC 数排序，便于识别接入密集口和级联口。',
                    rows: bridgePortMacRows.map(row => ({
                        label: `${row.port_name || '--'} (#${row.ifindex ?? '--'})`,
                        value: `MAC ${row.mac_count ?? 0} · VLAN ${row.vlan_count ?? 0} · PVID ${row.pvid_name || '--'}`
                    }))
                }
            ]);
            const bridgeHtml = (bridgePortMacRows.length || bridgeFdbRows.length)
                ? `<div class="snmp-insight-grid">
                    <div class="snmp-insight-panel">
                        <div class="snmp-insight-head"><div class="snmp-insight-title">接入口学习明细</div><div class="snmp-insight-note">每口已学习 MAC / PVID / 预览</div></div>
                        <div class="snmp-dense-list">${bridgePortMacRows.length ? bridgePortMacRows.slice(0, 8).map(row => `<div class="snmp-dense-row"><div class="snmp-dense-key">${escapeHtml(row.port_name || '--')} (#${escapeHtml(String(row.ifindex ?? '--'))})</div><div class="snmp-dense-value">MAC ${escapeHtml(String(row.mac_count ?? 0))} · PVID ${escapeHtml(row.pvid_name || '--')} · ${escapeHtml(row.mac_preview || '--')}</div></div>`).join('') : `<div class="snmp-dense-row"><div class="snmp-dense-key">当前状态</div><div class="snmp-dense-value">暂无端口 MAC 学习数据</div></div>`}</div>
                    </div>
                    <div class="snmp-insight-panel">
                        <div class="snmp-insight-head"><div class="snmp-insight-title">MAC / VLAN 近期样本</div><div class="snmp-insight-note">从桥表中抽样展示最近解析到的条目</div></div>
                        <div class="snmp-dense-list">${bridgeFdbRows.length ? bridgeFdbRows.slice(0, 8).map(row => `<div class="snmp-dense-row"><div class="snmp-dense-key">${escapeHtml(row.port_name || '--')} · ${escapeHtml(row.vlan_name || '--')}</div><div class="snmp-dense-value">${escapeHtml(row.mac || '--')} · ${escapeHtml(row.status || '--')}</div></div>`).join('') : `<div class="snmp-dense-row"><div class="snmp-dense-key">当前状态</div><div class="snmp-dense-value">暂无 MAC / VLAN 样本</div></div>`}</div>
                    </div>
                </div>`
                : '';
            const downRows = Array.isArray(interfaceSummary.down_rows) ? interfaceSummary.down_rows : [];
            const unknownRows = Array.isArray(interfaceSummary.unknown_rows) ? interfaceSummary.unknown_rows : [];
            const downHtml = downRows.length
                ? `<div class="ups-alert-list">${downRows.slice(0, 6).map(row => `<span class="ups-alert-chip warning">${escapeHtml(row.name || '--')} · ${escapeHtml(row.speed_text || '--')} · 离线</span>`).join('')}</div>`
                : (unknownRows.length
                    ? `<div class="ups-alert-list">${unknownRows.slice(0, 6).map(row => `<span class="ups-alert-chip warning" style="color:#fde68a;background:rgba(245,158,11,0.14);border:1px solid rgba(245,158,11,0.28);">${escapeHtml(row.name || '--')} · ${escapeHtml(row.speed_text || '--')} · 状态未采到</span>`).join('')}</div>`
                    : '<div class="ups-alert-list"><span class="ups-alert-chip" style="color:#bbf7d0;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.34);">当前端口状态稳定</span></div>');
            const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
            const anomalyChips = alertItems.slice(0, 8).map(item => {
                const cls = item.level === 'critical' ? 'error' : 'warning';
                return `<span class="ups-alert-chip ${cls}">${escapeHtml(item.text || '--')}</span>`;
            });
            const anomalyHtml = renderSnmpHighlightPanel('新增端口异常', '基于本轮轮询与上一轮对比，优先展示新增错包、丢弃与高负载端口。', anomalyChips, alertItems.some(item => item.level === 'critical') ? 'critical' : 'warning');
            const segmentHtml = renderSnmpSwitchSegments(summary, portRows);
            const panelHtml = renderSnmpSwitchPortPanels(summary.id || summary.host || 'switch', portRows);
            return `${switchVendorHtml}${bridgeHtml}<div class="snmp-switch-grid">
                <div class="snmp-switch-panel ${criticalClass}">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">交换端口概况</div><div class="snmp-insight-note">在线 / 离线 / 未采到 / 物理口</div></div>
                    ${spotlightHtml}
                    <div class="snmp-stat-row">
                        <div class="snmp-stat-card"><div class="label">物理端口</div><div class="value">${escapeHtml(String(physicalCount))}</div></div>
                        <div class="snmp-stat-card"><div class="label">在线端口</div><div class="value">${escapeHtml(String(upCount))}</div></div>
                        <div class="snmp-stat-card"><div class="label">离线端口</div><div class="value">${escapeHtml(String(downCount))}</div></div>
                        <div class="snmp-stat-card"><div class="label">状态未采到</div><div class="value">${escapeHtml(String(unknownCount))}</div></div>
                        <div class="snmp-stat-card"><div class="label">上联端口</div><div class="value">${escapeHtml(String(uplinkCount))}</div></div>
                        <div class="snmp-stat-card"><div class="label">忙碌端口</div><div class="value">${escapeHtml(String(interfaceSummary.busy_port_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">异常端口</div><div class="value">${escapeHtml(String(interfaceSummary.error_port_count ?? 0))} / ${escapeHtml(String(interfaceSummary.discard_port_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">新增错包口</div><div class="value">${escapeHtml(String(interfaceSummary.delta_error_port_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">新增丢弃口</div><div class="value">${escapeHtml(String(interfaceSummary.delta_discard_port_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">聚合吞吐</div><div class="value">${escapeHtml(getSnmpBestThroughputDisplay(interfaceSummary))}</div></div>
                        <div class="snmp-stat-card"><div class="label">上 / 下行</div><div class="value">${escapeHtml(interfaceSummary.aggregate_in_rate_text || '--')} / ${escapeHtml(interfaceSummary.aggregate_out_rate_text || '--')}</div></div>
                        <div class="snmp-stat-card"><div class="label">学习 MAC</div><div class="value">${escapeHtml(String(switchStats.learnedMacCount ?? 0))} / ${escapeHtml(String(switchStats.bridgeMacCount ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">VLAN / 桥端口</div><div class="value">${escapeHtml(String(switchStats.bridgeVlanCount ?? 0))} / ${escapeHtml(String(interfaceSummary.bridge_port_count ?? 0))}</div></div>
                    </div>
                    ${downHtml}
                </div>
                <div class="snmp-switch-panel">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">端口状态看板</div><div class="snmp-insight-note">优先展示活跃口与上联口，最多 12 个</div></div>
                    ${anomalyHtml}
                    ${segmentHtml}
                    ${portHtml}
                    ${panelHtml}
                </div>
            </div>`;
        }
        function renderSnmpKpiCards(deviceType, summary, status) {
            const normalized = String(deviceType || '').trim().toLowerCase();
            const items = [];
            const pushItem = (label, value, meta = '') => items.push({ label, value: value || '--', meta });
            if (normalized === 'nas') {
                const capacity = summarizeSnmpStorageCapacity(summary);
                const primaryStorage = getSnmpPrimaryStorageRow(summary);
                const diskSummary = getSnmpDiskSummary(summary);
                const capacityDisplay = getSnmpCapacityDisplay(summary);
                const primaryStorageDisplay = getSnmpPrimaryStorageDisplay(summary);
                pushItem(capacity.mode === 'qnap_quota' ? '共享/LUN 配额' : '容量合计', capacityDisplay.value, `${capacityDisplay.meta} · 项 ${capacity.rows.length}`);
                pushItem(capacity.mode === 'qnap_quota' ? '最大占用项' : '最大占用卷', primaryStorageDisplay.value, primaryStorageDisplay.meta);
                pushItem('内存 / 可用', summary.memory_usage_percent !== undefined && summary.memory_usage_percent !== null ? `${summary.memory_usage_percent}%` : '--', `${summary.memory_available_text || '--'} 可用 / ${summary.memory_total_text || '--'}`);
                pushItem('磁盘 / 网络', `${diskSummary.rows.length || summary.disk_count || 0} / ${(summary.interface_summary || {}).physical_count ?? 0}`, `${diskSummary.hottest ? `最高 ${diskSummary.hottest.temp_text || '--'} · ` : ''}${summary.interface_preview || '--'}`);
            } else if (normalized === 'router') {
                const customMetrics = Array.isArray(status.custom_metrics) ? status.custom_metrics : [];
                const routerConnections = getSnmpMetricValueWithFallback(customMetrics, ['network_connections', 'session_count', 'nat_sessions'], summary);
                const routerCpuTemp = getSnmpMetricValueWithFallback(customMetrics, ['cpu_temperature_c', 'temperature_c'], summary);
                const routerApCount = getSnmpMetricValueWithFallback(customMetrics, ['ap_count', 'online_clients'], summary);
                const interfaceSummary = summary.interface_summary || {};
                const primaryLink = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true })[0];
                pushItem('接口总流量', getSnmpBestThroughputDisplay(interfaceSummary), `上 / 下 ${getSnmpBestThroughputPair(interfaceSummary)}`);
                pushItem('主链路', primaryLink ? `${primaryLink.name || '--'}` : '--', primaryLink ? `${getSnmpInterfaceKindText(primaryLink.kind)} · ${primaryLink.total_rate_text || primaryLink.traffic_text || '--'}` : getSnmpInterfaceRoleText(interfaceSummary));
                pushItem('CPU / 内存', `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%`, `峰值 ${summary.cpu_peak_percent ?? '--'}% · 温度 ${snmpProvidedText(routerCpuTemp)}`);
                pushItem('连接 / AP', `${snmpProvidedText(routerConnections)} / ${snmpProvidedText(routerApCount)}`, '设备未提供时显示为未提供');
            } else if (normalized === 'switch') {
                const interfaceSummary = summary.interface_summary || {};
                const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
                pushItem('接口总数', getSnmpInterfaceCountText(interfaceSummary, status), `物理 ${(summary.interface_summary || {}).physical_count ?? 0}`);
                pushItem('在线 / 离线 / 未采到', `${switchStats.upCount ?? 0} / ${switchStats.downCount ?? 0} / ${switchStats.unknownCount ?? 0}`, `上联 ${switchStats.uplinkCount ?? 0}`);
                pushItem('交换总吞吐', getSnmpBestThroughputDisplay(interfaceSummary), `${getSnmpBestThroughputPair(interfaceSummary)}`);
                pushItem('新增异常', `${(summary.interface_summary || {}).delta_error_port_count ?? 0} / ${(summary.interface_summary || {}).delta_discard_port_count ?? 0}`, `忙碌 ${(summary.interface_summary || {}).busy_port_count ?? 0} · 面板 ${Math.min(Number((summary.interface_summary || {}).physical_count ?? 0), 48)} 个`);
            } else {
                pushItem('接口总数', `${status.if_number ?? '--'}`, summary.interface_preview || '--');
                pushItem('在线状态', getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' }).text, summary.uptime_text || '--');
                pushItem('内存', summary.memory_total_text || '--', summary.memory_used_text || '--');
                pushItem('轮询', summary.poll_elapsed_sec !== undefined ? `${summary.poll_elapsed_sec}s` : '--', status.updated_at ? String(status.updated_at).replace('T', ' ').slice(0, 19) : '--');
            }
            return `<div class="snmp-kpi-grid">${items.slice(0, 4).map(item => `<div class="snmp-kpi-card ${escapeHtml(normalized || 'network')}">
                <div class="snmp-kpi-label">${escapeHtml(item.label)}</div>
                <div class="snmp-kpi-value">${escapeHtml(String(item.value || '--'))}</div>
                ${item.meta ? `<div class="snmp-kpi-meta">${escapeHtml(String(item.meta))}</div>` : ''}
            </div>`).join('')}</div>`;
        }
        function renderSnmpNasSection(summary, customMetrics = []) {
            const cpuAvg = summary.cpu_avg_percent !== undefined && summary.cpu_avg_percent !== null ? `${summary.cpu_avg_percent}%` : '--';
            const cpuPeak = summary.cpu_peak_percent !== undefined && summary.cpu_peak_percent !== null ? `${summary.cpu_peak_percent}%` : '--';
            const cpuCore = summary.cpu_core_count !== undefined && summary.cpu_core_count !== null ? String(summary.cpu_core_count) : '--';
            const load1 = summary.ucd_load_1 !== undefined && summary.ucd_load_1 !== null ? String(summary.ucd_load_1) : '--';
            const load5 = summary.ucd_load_5 !== undefined && summary.ucd_load_5 !== null ? String(summary.ucd_load_5) : '--';
            const load15 = summary.ucd_load_15 !== undefined && summary.ucd_load_15 !== null ? String(summary.ucd_load_15) : '--';
            const cacheText = summary.ucd_mem_cached_text || '--';
            const availText = summary.ucd_mem_available_text || summary.memory_available_text || '--';
            const ucdMemoryText = summary.ucd_mem_total_text || '--';
            const ucdDiskIoRows = Array.isArray(summary.ucd_disk_io_top_rows) ? summary.ucd_disk_io_top_rows : [];
            const portRows = Array.isArray((summary.interface_summary || {}).port_preview_rows) ? (summary.interface_summary || {}).port_preview_rows : [];
            const networkRows = Array.isArray(summary.physical_top_rows) && summary.physical_top_rows.length ? summary.physical_top_rows : (Array.isArray(summary.network_top_rows) ? summary.network_top_rows : []);
            const storageRows = getSnmpStorageDisplayRows(summary, 10);
            const diskSummary = getSnmpDiskSummary(summary);
            const diskRows = diskSummary.rows;
            const fanRows = Array.isArray(summary.fan_rows) ? summary.fan_rows : [];
            const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
            const gpuMetrics = Array.isArray(summary.gpu_metrics) ? summary.gpu_metrics : [];
            const capacity = summarizeSnmpStorageCapacity(summary);
            const primaryStorage = getSnmpPrimaryStorageRow(summary);
            const memoryUsage = summary.memory_usage_percent !== undefined && summary.memory_usage_percent !== null ? `${summary.memory_usage_percent}%` : '--';
            const vendorMemoryText = summary.vendor_memory_total_text
                ? `${summary.vendor_memory_free_text || '--'} free / ${summary.vendor_memory_total_text}`
                : '';
            const memoryText = vendorMemoryText || (summary.memory_total_text && summary.memory_total_text !== '--'
                ? `${summary.memory_used_text || '--'} / ${summary.memory_total_text}`
                : (summary.memory_total_gb ? `${summary.memory_total_gb} GB` : '--'));
            const swapText = summary.swap_total_text && summary.swap_total_text !== '--'
                ? `${summary.swap_used_text || '--'} / ${summary.swap_total_text}`
                : '--';
            const nasSpotlightHtml = renderSnmpSpotlightCards([
                { label: capacity.mode === 'qnap_quota' ? '共享/LUN 配额' : '容量合计', value: getSnmpCapacityDisplay(summary).value, meta: `${getSnmpCapacityDisplay(summary).meta} · 项 ${capacity.rows.length}`, level: getSnmpCapacityDisplay(summary).level },
                { label: '最大占用卷', value: getSnmpPrimaryStorageDisplay(summary).value, meta: getSnmpPrimaryStorageDisplay(summary).meta, level: getSnmpPrimaryStorageDisplay(summary).level },
                { label: '内存 / Swap', value: memoryUsage, meta: `${memoryText} · Swap ${swapText}`, level: getSnmpAlertLevel(summary.memory_alert_level) },
                { label: '磁盘 / 温度', value: `${diskRows.length || summary.disk_count || 0} 盘`, meta: diskSummary.tempMeta, level: diskSummary.criticalCount > 0 ? 'critical' : (diskSummary.warningCount > 0 ? 'warning' : '') }
            ]);
            const resourceDenseHtml = `<div class="snmp-dense-list">
                <div class="snmp-dense-row"><div class="snmp-dense-key">CPU 平均 / 峰值 / 核心</div><div class="snmp-dense-value">${escapeHtml(cpuAvg)} / ${escapeHtml(cpuPeak)} / ${escapeHtml(cpuCore)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">内存占用 / 总量</div><div class="snmp-dense-value">${escapeHtml(memoryUsage)} / ${escapeHtml(memoryText)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">Swap / 可用内存</div><div class="snmp-dense-value">${escapeHtml(swapText)} / ${escapeHtml(availText)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">进程 / 用户 / 风扇</div><div class="snmp-dense-value">${escapeHtml(String(summary.process_count ?? '--'))} / ${escapeHtml(String(summary.user_count ?? '--'))} / ${escapeHtml(String(summary.fan_count ?? 0))}</div></div>
            </div>`;
            const loadDenseHtml = `<div class="snmp-dense-list">
                <div class="snmp-dense-row"><div class="snmp-dense-key">Load 1 / 5 / 15</div><div class="snmp-dense-value">${escapeHtml(load1)} / ${escapeHtml(load5)} / ${escapeHtml(load15)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">UCD 内存总量</div><div class="snmp-dense-value">${escapeHtml(ucdMemoryText)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">Cache / Available</div><div class="snmp-dense-value">${escapeHtml(cacheText)} / ${escapeHtml(availText)}</div></div>
                <div class="snmp-dense-row"><div class="snmp-dense-key">存储卷 / 槽位 / 网卡</div><div class="snmp-dense-value">${escapeHtml(String(summary.storage_count ?? storageRows.length ?? 0))} / ${escapeHtml(String(summary.disk_count ?? diskRows.length ?? 0))} / ${escapeHtml(String((summary.interface_summary || {}).physical_count ?? 0))}</div></div>
            </div>`;
            const nicHtml = portRows.length
                ? `<div class="snmp-port-grid">${portRows.slice(0, 4).map(row => {
                    const state = getSnmpSwitchPortState(row);
                    const stateStyle = state.level === 'up'
                        ? ''
                        : (state.level === 'down'
                            ? 'color:#fecaca;background:rgba(239,68,68,0.14);border-color:rgba(239,68,68,0.28);'
                            : 'color:#fde68a;background:rgba(245,158,11,0.14);border-color:rgba(245,158,11,0.28);');
                    return `<div class="snmp-port-card ${escapeHtml(state.cardClass)}"><div class="snmp-port-name">${escapeHtml(row.name || '--')}</div><div class="snmp-port-meta">${escapeHtml(row.speed_text || '--')}</div><div class="snmp-port-status-row"><span class="ups-chip ${escapeHtml(state.level === 'up' ? 'online' : state.chipClass)}" style="${stateStyle}">${escapeHtml(state.text)}</span></div></div>`;
                }).join('')}</div>`
                : '';
            const capacityHeroHtml = renderSnmpCapacityHero(summary, { limit: 10, title: capacity.mode === 'qnap_quota' ? '共享文件夹 / LUN 配额' : '容量与卷明细' });
            const storageHtml = renderSnmpStorageList(storageRows);
            const diskHtml = renderSnmpDiskHealthList(diskRows);
            const chassisHtml = renderQnapDriveBayPanel(summary);
            const diskIoHtml = renderSnmpDiskIoList(ucdDiskIoRows);
            const fanHtml = renderSnmpFanList(fanRows);
            const nicPanelHtml = networkRows.length
                ? `<div class="snmp-port-grid">${networkRows.slice(0, 4).map(row => {
                    const state = getSnmpSwitchPortState(row);
                    const stateStyle = state.level === 'up'
                        ? ''
                        : (state.level === 'down'
                            ? 'color:#fecaca;background:rgba(239,68,68,0.14);border-color:rgba(239,68,68,0.28);'
                            : 'color:#fde68a;background:rgba(245,158,11,0.14);border-color:rgba(245,158,11,0.28);');
                    return `<div class="snmp-port-card ${escapeHtml(state.cardClass)}">
                        <div class="snmp-port-name">${escapeHtml(row.name || '--')}</div>
                        <div class="snmp-port-meta">${escapeHtml(row.speed_text || '--')} · ${escapeHtml(row.alias || '主链路')}</div>
                        <div class="snmp-port-meta">实时 ${escapeHtml(row.traffic_text || '--')}</div>
                        <div class="snmp-port-meta">累计 ${escapeHtml(row.in_bytes_text || '--')} / ${escapeHtml(row.out_bytes_text || '--')}</div>
                        <div class="snmp-port-status-row">
                            <span class="ups-chip ${escapeHtml(state.level === 'up' ? 'online' : state.chipClass)}" style="${stateStyle}">${escapeHtml(state.text)}</span>
                            <span class="ups-chip">${escapeHtml(row.utilization_text || '--')}</span>
                        </div>
                    </div>`;
                }).join('')}</div>`
                : '';
            const trafficHtml = `<div class="snmp-flow-grid">
                <div class="snmp-flow-card physical">
                    <div class="snmp-flow-title">重点网卡流量</div>
                    <div class="snmp-flow-list">${renderSnmpFlowList(networkRows, '当前无关键网卡流量')}</div>
                </div>
            </div>`;
            const alertHtml = alertItems.length
                ? `<div class="ups-alert-list">${alertItems.map(item => `<span class="ups-alert-chip ${item.level === 'critical' ? 'error' : 'warning'}">${escapeHtml(item.text || '--')}</span>`).join('')}</div>`
                : '';
            const gpuHtml = gpuMetrics.length
                ? `<div class="ups-alert-list">${gpuMetrics.map(item => `<span class="ups-alert-chip warning" style="color:#bfdbfe;background:rgba(59,130,246,0.14);border:1px solid rgba(59,130,246,0.28);">${escapeHtml(String(item.name || 'GPU'))}: ${escapeHtml(String(item.value ?? '--'))}${item.unit ? ` ${escapeHtml(String(item.unit))}` : ''}</span>`).join('')}</div>`
                : '<div class="ups-alert-list"><span class="ups-alert-chip" style="color:#cbd5e1;background:rgba(100,116,139,0.16);border:1px solid rgba(148,163,184,0.18);">当前未采到 GPU 指标，可后续补厂商 OID</span></div>';
            const vendorHtml = renderSnmpVendorCards([
                {
                    title: '厂商扩展资源',
                    note: '优先展示飞牛 / QNAP 厂商扩展内存、缓存和系统负载信息。',
                    level: getSnmpAlertLevel(summary.memory_alert_level),
                    rows: [
                        { label: capacity.mode === 'qnap_quota' ? '共享/LUN 配额' : '容量合计', value: capacity.mode === 'qnap_quota' ? `${getSnmpCapacityDisplay(summary).meta}` : `${getSnmpCapacityDisplay(summary).meta}${capacity.percent !== null ? ` · ${capacity.percent}%` : ''}` },
                        { label: '厂商内存总量', value: summary.vendor_memory_total_text || '--' },
                        { label: '厂商空闲内存', value: summary.vendor_memory_free_text || '--' },
                        { label: 'Load 1 / 5 / 15', value: `${summary.ucd_load_1 ?? '--'} / ${summary.ucd_load_5 ?? '--'} / ${summary.ucd_load_15 ?? '--'}` },
                        { label: 'UCD Buffer', value: summary.ucd_mem_buffer_text || '--' },
                        { label: 'UCD Cache', value: summary.ucd_mem_cached_text || '--' },
                        { label: 'UCD Available', value: summary.ucd_mem_available_text || summary.memory_available_text || '--' }
                    ]
                },
                {
                    title: '图形与硬件侧',
                    note: '优先挂出 GPU、风扇、磁盘 I/O 等偏硬件运行指标。',
                    rows: [
                        { label: 'GPU 指标数', value: String(gpuMetrics.length || 0) },
                        { label: '风扇数量', value: String(summary.fan_count ?? 0) },
                        { label: '磁盘 I/O 热点', value: ucdDiskIoRows[0] ? `${ucdDiskIoRows[0].device || '--'} · ${ucdDiskIoRows[0].load_peak_text || '--'}` : '--' },
                        { label: '健康分', value: `${summary.health_score ?? '--'} / ${summary.risk_level || '--'}` },
                        { label: '运行时长', value: summary.uptime_text || '--' }
                    ]
                },
                {
                    title: '系统运行上下文',
                    note: '把当前采到但没放在主卡里的系统类信息独立展示，方便排查。',
                    rows: [
                        { label: 'Boot 参数', value: summary.boot_params_preview || '--' },
                        { label: '联系人', value: summary.contact_text || '--' },
                        { label: '位置', value: summary.location_text || '--' },
                        { label: '轮询间隔差值', value: `${summary.poll_elapsed_sec ?? '--'} s` }
                    ]
                },
                {
                    title: '扩展 OID 返回',
                    note: '自定义 OID 采到的即时结果，后续可继续按厂商类型补更多字段。',
                    rows: buildSnmpMetricRows(customMetrics, ['hr_memory_size_kb', 'hr_system_processes', 'hr_system_users'], 8)
                }
            ]);
            return `<div class="snmp-insight-grid">
                <div class="snmp-insight-panel ${Number(capacity.percent || 0) >= 92 ? 'critical' : (Number(capacity.percent || 0) >= 85 ? 'warning' : '')} wide">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">${capacity.mode === 'qnap_quota' ? '共享/LUN 配额核心' : '容量核心'}</div><div class="snmp-insight-note">${capacity.mode === 'qnap_quota' ? '配额视图，不合并为物理池容量' : 'NAS 最重要信息放在第一屏'}</div></div>
                    ${capacityHeroHtml}
                </div>
                ${chassisHtml ? `<div class="snmp-insight-panel wide"><div class="snmp-insight-head"><div class="snmp-insight-title">NAS 机箱盘位</div><div class="snmp-insight-note">HDD / SSD / 空槽布局模拟</div></div>${chassisHtml}</div>` : ''}
                <div class="snmp-insight-panel ${getSnmpAlertLevel(summary.memory_alert_level)}">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">资源概况</div><div class="snmp-insight-note">容量 / 内存 / CPU / 盘位</div></div>
                    ${nasSpotlightHtml}
                    ${resourceDenseHtml}
                </div>
                <div class="snmp-insight-panel">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">系统负载</div><div class="snmp-insight-note">UCD / Cache / Available</div></div>
                    ${loadDenseHtml}
                </div>
                <div class="snmp-insight-panel ${summary.storage_critical_count > 0 ? 'critical' : (summary.storage_warning_count > 0 ? 'warning' : '')}">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">存储与链路</div><div class="snmp-insight-note">卷 / 网卡 / 告警</div></div>
                    <div class="snmp-stat-row">
                        <div class="snmp-stat-card"><div class="label">存储卷</div><div class="value">${escapeHtml(String(summary.storage_count ?? storageRows.length ?? 0))} 项</div></div>
                        <div class="snmp-stat-card"><div class="label">磁盘槽位</div><div class="value">${escapeHtml(String(summary.disk_count ?? diskRows.length ?? 0))} 个</div></div>
                        <div class="snmp-stat-card"><div class="label">物理网卡</div><div class="value">${escapeHtml(String((summary.interface_summary || {}).physical_count ?? 0))} 个</div></div>
                        <div class="snmp-stat-card"><div class="label">风险卷</div><div class="value">${escapeHtml(String(summary.storage_warning_count ?? 0))} / ${escapeHtml(String(summary.storage_critical_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">风扇 / 进程</div><div class="value">${escapeHtml(String(summary.fan_count ?? 0))} / ${escapeHtml(String(summary.process_count ?? '--'))}</div></div>
                    </div>
                </div>
            </div>${diskHtml}${diskIoHtml}${trafficHtml}${nicPanelHtml}${nicHtml}${fanHtml}${gpuHtml}${alertHtml}${vendorHtml}`;
        }
        function renderSnmpRouterSection(summary, customMetrics = []) {
            const wanNames = Array.isArray((summary.interface_summary || {}).wan_names) ? (summary.interface_summary || {}).wan_names : [];
            const lanNames = Array.isArray((summary.interface_summary || {}).lan_names) ? (summary.interface_summary || {}).lan_names : [];
            const topTraffic = Array.isArray(summary.network_top_rows) ? summary.network_top_rows : [];
            const wanTraffic = Array.isArray(summary.wan_top_rows) ? summary.wan_top_rows : [];
            const lanTraffic = Array.isArray(summary.lan_top_rows) ? summary.lan_top_rows : [];
            const physicalTraffic = Array.isArray(summary.physical_top_rows) ? summary.physical_top_rows : [];
            const interfaceSummary = summary.interface_summary || {};
            const alertItems = Array.isArray(summary.alert_items) ? summary.alert_items : [];
            const cpuAvg = summary.cpu_avg_percent !== undefined && summary.cpu_avg_percent !== null ? `${summary.cpu_avg_percent}%` : '--';
            const cpuPeak = summary.cpu_peak_percent !== undefined && summary.cpu_peak_percent !== null ? `${summary.cpu_peak_percent}%` : '--';
            const aggregateTotal = getSnmpBestThroughputDisplay(interfaceSummary);
            const aggregatePair = getSnmpBestThroughputPair(interfaceSummary);
            const cpuTemp = getSnmpMetricValueWithFallback(customMetrics, ['cpu_temperature_c', 'temperature_c'], summary);
            const networkConnections = getSnmpMetricValueWithFallback(customMetrics, ['network_connections', 'session_count', 'nat_sessions'], summary);
            const apCount = getSnmpMetricValueWithFallback(customMetrics, ['ap_count', 'online_clients'], summary);
            const cpuUser = getSnmpMetricValueWithFallback(customMetrics, ['cpu_user_percent'], summary);
            const cpuSystem = getSnmpMetricValueWithFallback(customMetrics, ['cpu_system_percent'], summary);
            const cpuIdle = getSnmpMetricValueWithFallback(customMetrics, ['cpu_idle_percent'], summary);
            const usefulTraffic = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true });
            const primaryWan = wanTraffic.length ? wanTraffic[0] : (usefulTraffic.length ? usefulTraffic[0] : null);
            const primaryLan = lanTraffic.length ? lanTraffic[0] : (physicalTraffic.length ? physicalTraffic[0] : usefulTraffic[1] || null);
            const routerLinkRows = [primaryWan, primaryLan, ...usefulTraffic.slice(0, 4), ...topTraffic.slice(0, 2)]
                .filter((row, index, arr) => row && arr.findIndex(item => (item?.name || '') === (row?.name || '')) === index);
            const routerLinkPanelHtml = routerLinkRows
                .filter((row, index, arr) => row && arr.findIndex(item => (item?.name || '') === (row?.name || '')) === index)
                .length
                ? `<div class="snmp-port-grid">${routerLinkRows
                    .slice(0, 4)
                    .map(row => {
                        const state = getSnmpSwitchPortState(row);
                        const stateStyle = state.level === 'up'
                            ? ''
                            : (state.level === 'down'
                                ? 'color:#fecaca;background:rgba(239,68,68,0.14);border-color:rgba(239,68,68,0.28);'
                                : 'color:#fde68a;background:rgba(245,158,11,0.14);border-color:rgba(245,158,11,0.28);');
                        const kindText = getSnmpInterfaceKindText(row.kind);
                        return `<div class="snmp-port-card ${escapeHtml(state.cardClass)}">
                            <div class="snmp-port-name">${escapeHtml(row.name || '--')}</div>
                            <div class="snmp-port-meta">${escapeHtml(kindText)} · ${escapeHtml(row.speed_text || '--')}</div>
                            <div class="snmp-port-meta">实时 ${escapeHtml(row.traffic_text || '--')}</div>
                            <div class="snmp-port-meta">总速率 ${escapeHtml(row.total_rate_text || '--')} · 利用率 ${escapeHtml(row.utilization_text || '--')}</div>
                            <div class="snmp-port-status-row">
                                <span class="ups-chip ${escapeHtml(state.level === 'up' ? 'online' : state.chipClass)}" style="${stateStyle}">${escapeHtml(state.text)}</span>
                                <span class="ups-chip">累计 ${escapeHtml(row.in_bytes_text || '--')} / ${escapeHtml(row.out_bytes_text || '--')}</span>
                            </div>
                        </div>`;
                    }).join('')}</div>`
                : '';
            const routerSpotlightHtml = renderSnmpSpotlightCards([
                { label: '网关总吞吐', value: aggregateTotal, meta: `上 / 下行 ${aggregatePair}` },
                { label: '接口结构', value: getSnmpInterfaceCountText(interfaceSummary), meta: getSnmpInterfaceRoleText(interfaceSummary) },
                { label: 'CPU / 内存', value: `${cpuAvg} / ${summary.memory_usage_percent !== undefined && summary.memory_usage_percent !== null ? `${summary.memory_usage_percent}%` : '--'}`, meta: `峰值 ${cpuPeak} · CPU温度 ${snmpProvidedText(cpuTemp)}`, level: Number(interfaceSummary.busy_port_count || 0) > 0 ? 'warning' : '' },
                { label: '连接 / AP', value: `${snmpProvidedText(networkConnections)} / ${snmpProvidedText(apCount)}`, meta: `设备未提供则显示未提供`, level: Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0 ? 'warning' : '' }
            ]);
            const wanBadgeHtml = renderSnmpHighlightPanel('网关总吞吐', '优先展示当前总吞吐、上下行与异常接口。', [
                `<span class="ups-alert-chip" style="color:#bfdbfe;background:rgba(59,130,246,0.14);border:1px solid rgba(59,130,246,0.28);">总吞吐 ${escapeHtml(aggregateTotal)}</span>`,
                `<span class="ups-alert-chip" style="color:#86efac;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.34);">上 / 下行 ${escapeHtml(aggregatePair)}</span>`,
                `<span class="ups-alert-chip warning">忙碌口 ${escapeHtml(String(interfaceSummary.busy_port_count ?? 0))}</span>`,
                `<span class="ups-alert-chip ${Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0 ? 'warning' : ''}">异常口 ${escapeHtml(String(interfaceSummary.error_port_count ?? 0))} / ${escapeHtml(String(interfaceSummary.discard_port_count ?? 0))}</span>`
            ], (Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0) ? 'warning' : '');
            const trafficHtml = `<div class="snmp-flow-grid">
                <div class="snmp-flow-card wan">
                    <div class="snmp-flow-title">高流量接口</div>
                    <div class="snmp-flow-list">${renderSnmpFlowList(usefulTraffic.length ? usefulTraffic : topTraffic, '当前无实时流量')}</div>
                </div>
                <div class="snmp-flow-card lan">
                    <div class="snmp-flow-title">WAN / LAN 识别</div>
                    <div class="snmp-flow-list">${renderSnmpFlowList([...wanTraffic, ...lanTraffic], '设备未按 WAN/LAN 命名')}</div>
                </div>
                <div class="snmp-flow-card physical">
                    <div class="snmp-flow-title">物理 / 聚合链路</div>
                    <div class="snmp-flow-list">${renderSnmpFlowList(physicalTraffic, '当前无物理链路流量')}</div>
                </div>
            </div>`;
            const alertHtml = alertItems.length
                ? `<div class="ups-alert-list">${alertItems.map(item => `<span class="ups-alert-chip ${item.level === 'critical' ? 'error' : 'warning'}">${escapeHtml(item.text || '--')}</span>`).join('')}</div>`
                : '';
            const routerVendorHtml = renderSnmpVendorCards([
                {
                    title: '网关系统资源',
                    note: '补充当前已采到但未放进主摘要的系统级资源数据。',
                    level: getSnmpAlertLevel(summary.memory_alert_level),
                    rows: [
                        { label: 'Load 1 / 5 / 15', value: `${summary.ucd_load_1 ?? '--'} / ${summary.ucd_load_5 ?? '--'} / ${summary.ucd_load_15 ?? '--'}` },
                        { label: '内存可用', value: summary.memory_available_text || '--' },
                        { label: 'UCD Cache / Buffer', value: `${summary.ucd_mem_cached_text || '--'} / ${summary.ucd_mem_buffer_text || '--'}` },
                        { label: 'Swap 使用', value: summary.swap_total_text && summary.swap_total_text !== '--' ? `${summary.swap_used_text || '--'} / ${summary.swap_total_text}` : '--' },
                        { label: '进程 / 用户', value: `${summary.process_count ?? '--'} / ${summary.user_count ?? '--'}` },
                        { label: '运行时长', value: summary.uptime_text || '--' },
                        { label: 'CPU 温度', value: snmpProvidedText(cpuTemp) },
                        { label: '网络连接数', value: snmpProvidedText(networkConnections) },
                        { label: 'AP / 终端', value: snmpProvidedText(apCount) }
                    ]
                },
                {
                    title: '网关侧上下文',
                    note: '便于后续继续补爱快厂商 OID 时对照现有系统信息。',
                    rows: [
                        { label: '接口预览', value: summary.interface_preview || '--' },
                        { label: '系统描述', value: compactSnmpText(summary.sys_descr_text || '--', 72) },
                        { label: '联系人', value: summary.contact_text || '--' },
                        { label: '位置', value: summary.location_text || '--' },
                        { label: 'CPU 用户 / 系统 / 空闲', value: `${snmpProvidedText(cpuUser)} / ${snmpProvidedText(cpuSystem)} / ${snmpProvidedText(cpuIdle)}` }
                    ]
                }
            ]);
            const customMetricHtml = renderSnmpVendorCards([
                {
                    title: '网关扩展 OID',
                    note: '这里汇总自定义 OID 的实际返回值，后续补爱快专有指标时会优先显示在这里。',
                    rows: buildSnmpMetricRows(customMetrics, ['hr_memory_size_kb', 'hr_system_processes', 'hr_system_users'], 8)
                }
            ]);
            return `${routerSpotlightHtml}${routerVendorHtml}${customMetricHtml}<div class="snmp-insight-grid">
                <div class="snmp-insight-panel">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">网关接口摘要</div><div class="snmp-insight-note">WAN / LAN / 在线</div></div>
                    <div class="snmp-stat-row">
                        <div class="snmp-stat-card"><div class="label">接口总数</div><div class="value">${escapeHtml(getSnmpInterfaceCountText(interfaceSummary))}</div></div>
                        <div class="snmp-stat-card"><div class="label">接口结构</div><div class="value">${escapeHtml(getSnmpInterfaceRoleText(interfaceSummary))}</div></div>
                        <div class="snmp-stat-card"><div class="label">CPU 平均 / 峰值</div><div class="value">${escapeHtml(cpuAvg)} / ${escapeHtml(cpuPeak)}</div></div>
                        <div class="snmp-stat-card"><div class="label">在线接口</div><div class="value">${escapeHtml(String((summary.interface_summary || {}).up_count ?? '--'))}</div></div>
                        <div class="snmp-stat-card"><div class="label">主链路 1</div><div class="value">${escapeHtml(primaryWan ? `${primaryWan.name || '--'} · ${primaryWan.total_rate_text || primaryWan.traffic_text || '--'}` : '--')}</div></div>
                        <div class="snmp-stat-card"><div class="label">主链路 2</div><div class="value">${escapeHtml(primaryLan ? `${primaryLan.name || '--'} · ${primaryLan.total_rate_text || primaryLan.traffic_text || '--'}` : '--')}</div></div>
                    </div>
                    ${routerLinkPanelHtml}
                </div>
                <div class="snmp-insight-panel">
                    <div class="snmp-insight-head"><div class="snmp-insight-title">网关容量摘要</div><div class="snmp-insight-note">内存 / 进程 / 采样</div></div>
                    <div class="snmp-stat-row">
                        <div class="snmp-stat-card"><div class="label">内存占用</div><div class="value">${escapeHtml(summary.memory_usage_percent !== undefined && summary.memory_usage_percent !== null ? `${summary.memory_usage_percent}%` : '--')}</div></div>
                        <div class="snmp-stat-card"><div class="label">内存摘要</div><div class="value">${escapeHtml(summary.memory_used_text || '--')} / ${escapeHtml(summary.memory_total_text || '--')}</div></div>
                        <div class="snmp-stat-card"><div class="label">进程 / 用户</div><div class="value">${escapeHtml(String(summary.process_count ?? '--'))} / ${escapeHtml(String(summary.user_count ?? '--'))}</div></div>
                        <div class="snmp-stat-card"><div class="label">轮询差值</div><div class="value">${escapeHtml(String(summary.poll_elapsed_sec ?? '--'))} s</div></div>
                        <div class="snmp-stat-card"><div class="label">总吞吐</div><div class="value">${escapeHtml(aggregateTotal)}</div></div>
                        <div class="snmp-stat-card"><div class="label">上 / 下行</div><div class="value">${escapeHtml(interfaceSummary.aggregate_in_rate_text || '--')} / ${escapeHtml(interfaceSummary.aggregate_out_rate_text || '--')}</div></div>
                        <div class="snmp-stat-card"><div class="label">忙碌口</div><div class="value">${escapeHtml(String(interfaceSummary.busy_port_count ?? 0))}</div></div>
                        <div class="snmp-stat-card"><div class="label">异常口</div><div class="value">${escapeHtml(String(interfaceSummary.error_port_count ?? 0))} / ${escapeHtml(String(interfaceSummary.discard_port_count ?? 0))}</div></div>
                    </div>
                </div>
            </div>${wanBadgeHtml}${trafficHtml}${alertHtml}`;
        }
        function renderSnmpRoleSection(deviceType, summary, status) {
            const interfaceSummary = summary.interface_summary || {};
            const physicalCount = Array.isArray(interfaceSummary.physical_names) ? interfaceSummary.physical_names.length : 0;
            const wanCount = Array.isArray(interfaceSummary.wan_names) ? interfaceSummary.wan_names.length : 0;
            const lanCount = Array.isArray(interfaceSummary.lan_names) ? interfaceSummary.lan_names.length : 0;
            const bondCount = Array.isArray(interfaceSummary.bond_names) ? interfaceSummary.bond_names.length : 0;
            const bridgeCount = Array.isArray(interfaceSummary.bridge_names) ? interfaceSummary.bridge_names.length : 0;
            const upCount = interfaceSummary.up_count ?? '--';
            const switchStats = deviceType === 'switch' ? getSnmpSwitchDerivedStats(summary, interfaceSummary) : null;
            if (deviceType === 'nvr') {
                return `<div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">录像角色</div><div class="value">NVR / 摄像头汇聚</div></div>
                    <div class="ups-meta-item"><div class="label">通道在线</div><div class="value">${escapeHtml(String(summary.channel_online ?? 0))} / ${escapeHtml(String(summary.channel_total ?? 0))}</div></div>
                    <div class="ups-meta-item"><div class="label">硬盘正常</div><div class="value">${escapeHtml(String(summary.hdd_ok_count ?? 0))} / ${escapeHtml(String(summary.hdd_total ?? 0))}</div></div>
                    <div class="ups-meta-item"><div class="label">运行时长</div><div class="value">${escapeHtml(String(summary.uptime_text || status.uptime_text || '--'))}</div></div>
                    <div class="ups-meta-item"><div class="label">采集协议</div><div class="value">${escapeHtml(String(status.checked_source || 'Hikvision ISAPI'))}</div></div>
                </div>`;
            }
            if (deviceType === 'nas') {
                return `<div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">存储角色</div><div class="value">NAS / 统一资源采集</div></div>
                    <div class="ups-meta-item"><div class="label">物理网口</div><div class="value">${escapeHtml(String(physicalCount || 0))} 个</div></div>
                    <div class="ups-meta-item"><div class="label">聚合 / 桥接</div><div class="value">${escapeHtml(String(bondCount || 0))} / ${escapeHtml(String(bridgeCount || 0))}</div></div>
                    <div class="ups-meta-item"><div class="label">在线接口</div><div class="value">${escapeHtml(String(upCount))}</div></div>
                    <div class="ups-meta-item"><div class="label">存储 / 槽位</div><div class="value">${escapeHtml(String(summary.storage_count ?? 0))} / ${escapeHtml(String(summary.disk_count ?? 0))}</div></div>
                </div>`;
            }
            if (deviceType === 'router') {
                return `<div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">网关角色</div><div class="value">路由 / 出入口监控</div></div>
                    <div class="ups-meta-item"><div class="label">接口总数</div><div class="value">${escapeHtml(getSnmpInterfaceCountText(interfaceSummary, status))}</div></div>
                    <div class="ups-meta-item"><div class="label">接口结构</div><div class="value">${escapeHtml(getSnmpInterfaceRoleText(interfaceSummary))}</div></div>
                    <div class="ups-meta-item"><div class="label">在线接口</div><div class="value">${escapeHtml(String(upCount))}</div></div>
                    <div class="ups-meta-item"><div class="label">总吞吐</div><div class="value">${escapeHtml(String(getSnmpBestThroughputDisplay(interfaceSummary)))}</div></div>
                </div>`;
            }
            if (deviceType === 'switch') {
                return `<div class="ups-meta-grid">
                    <div class="ups-meta-item"><div class="label">交换角色</div><div class="value">交换机 / 端口聚合监控</div></div>
                    <div class="ups-meta-item"><div class="label">接口总数</div><div class="value">${escapeHtml(getSnmpInterfaceCountText(interfaceSummary, status))}</div></div>
                    <div class="ups-meta-item"><div class="label">在线端口</div><div class="value">${escapeHtml(String(switchStats.upCount))}</div></div>
                    <div class="ups-meta-item"><div class="label">总吞吐 / 上联</div><div class="value">${escapeHtml(String(getSnmpBestThroughputDisplay(interfaceSummary)))} / ${escapeHtml(String(switchStats.uplinkCount || 0))}</div></div>
                    <div class="ups-meta-item"><div class="label">MAC / VLAN</div><div class="value">${escapeHtml(String(switchStats.bridgeMacCount || 0))} / ${escapeHtml(String(switchStats.bridgeVlanCount || 0))}</div></div>
                </div>`;
            }
            return `<div class="ups-meta-grid">
                <div class="ups-meta-item"><div class="label">设备角色</div><div class="value">${escapeHtml(getSnmpDeviceTypeLabel(deviceType))}</div></div>
                <div class="ups-meta-item"><div class="label">物理接口</div><div class="value">${escapeHtml(String(physicalCount || 0))} 个</div></div>
                <div class="ups-meta-item"><div class="label">在线接口</div><div class="value">${escapeHtml(String(upCount))}</div></div>
                <div class="ups-meta-item"><div class="label">采集状态</div><div class="value">${status.walk_enabled === false ? '标准 OID' : '标准 + Walk'}</div></div>
            </div>`;
        }
        function renderSnmpCompactCard(cfg, status, summary, deviceType, interfaceSummary, options = {}) {
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const updatedAt = status.updated_at ? String(status.updated_at).replace('T', ' ').slice(11, 19) : '--';
            const displayName = normalizeSnmpDeviceName(cfg, status);
            const deviceTypeLabel = getSnmpDeviceTypeLabel(deviceType);
            const deviceIcon = getSnmpDeviceIcon(deviceType);
            const riskLevel = String(summary.risk_level || 'normal').trim().toLowerCase();
            const riskText = riskLevel === 'critical' ? '高风险' : (riskLevel === 'warning' ? '中风险' : '低风险');
            const tiles = [];
            if (deviceType === 'router') {
                const trafficRows = getSnmpUsefulTrafficRows(summary, interfaceSummary, { includeZero: true });
                const primaryLink = trafficRows[0];
                tiles.push({ label: 'WAN / LAN', value: `${interfaceSummary.wan_count ?? 0} / ${interfaceSummary.lan_count ?? 0}` });
                tiles.push({ label: '总吞吐', value: getSnmpBestThroughputDisplay(interfaceSummary) });
                tiles.push({ label: '主链路', value: primaryLink ? `${primaryLink.name || '--'} ${primaryLink.total_rate_text || primaryLink.traffic_text || '--'}` : '--' });
                tiles.push({ label: '异常口', value: `${interfaceSummary.error_port_count ?? 0} / ${interfaceSummary.discard_port_count ?? 0}` });
                tiles.push({ label: '采集时间', value: updatedAt });
            } else if (deviceType === 'switch') {
                const switchStats = getSnmpSwitchDerivedStats(summary, interfaceSummary);
                tiles.push({ label: '接口总数', value: getSnmpInterfaceCountText(interfaceSummary, status) });
                tiles.push({ label: '在线 / 离线 / 未采到', value: `${switchStats.upCount ?? 0} / ${switchStats.downCount ?? 0} / ${switchStats.unknownCount ?? 0}` });
                tiles.push({ label: '上联 / 忙碌', value: `${switchStats.uplinkCount ?? 0} / ${interfaceSummary.busy_port_count ?? 0}` });
                tiles.push({ label: 'MAC / VLAN', value: `${switchStats.bridgeMacCount ?? 0} / ${switchStats.bridgeVlanCount ?? 0}` });
                tiles.push({ label: '新增异常', value: `${interfaceSummary.delta_error_port_count ?? 0} / ${interfaceSummary.delta_discard_port_count ?? 0}` });
                tiles.push({ label: '采集时间', value: updatedAt });
            } else if (deviceType === 'nvr') {
                tiles.push({ label: '通道在线', value: `${summary.channel_online ?? 0} / ${summary.channel_total ?? 0}` });
                tiles.push({ label: '硬盘正常', value: `${summary.hdd_ok_count ?? 0} / ${summary.hdd_total ?? 0}` });
                tiles.push({ label: '内存 / 运行', value: `${status.memory_usage_percent ?? '--'}% / ${status.uptime_text || '--'}` });
                tiles.push({ label: '采集时间', value: updatedAt });
            } else {
                tiles.push({ label: 'CPU / 内存', value: `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%` });
                tiles.push({ label: '存储 / 磁盘', value: `${summary.storage_count ?? 0} / ${summary.disk_count ?? 0}` });
                tiles.push({ label: '网卡 / 风扇', value: `${interfaceSummary.physical_count ?? 0} / ${summary.fan_count ?? 0}` });
                tiles.push({ label: '采集时间', value: updatedAt });
            }
            const errorNote = status.error ? `<div class="snmp-compact-note">异常: ${escapeHtml(String(status.error))}</div>` : '';
            const interactive = !!options.interactive;
            const interactiveAttrs = interactive
                ? ` role="button" tabindex="0" data-snmp-device-card="1" data-snmp-device-id="${escapeHtml(String(cfg.id || ''))}" aria-label="查看 ${escapeHtml(displayName)} 详情"`
                : '';
            return `<div class="ups-card snmp-device-card compact ${interactive ? 'snmp-overview-card' : ''} ${getCardStateClass(statusMeta)} ${online ? '' : 'offline'}"${interactiveAttrs}>
                <div class="snmp-hero">
                    <div class="snmp-hero-main">
                        <div class="snmp-device-icon ${escapeHtml(deviceType)}">${deviceIcon}</div>
                        <div class="snmp-hero-text">
                            <div class="snmp-hero-kicker">
                                <span class="ups-chip">${escapeHtml(deviceTypeLabel)}</span>
                                <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                            </div>
                            <div class="snmp-hero-title">${escapeHtml(displayName)}</div>
                            <div class="snmp-hero-subtitle">${escapeHtml(cfg.host || '--')} · ${escapeHtml(String((cfg.version || status.version || 'v2c')).toUpperCase())}</div>
                        </div>
                    </div>
                </div>
                <div class="snmp-compact-stack">
                    <div class="snmp-compact-note">${escapeHtml(statusMeta.note || `当前为精简视图，设备${online ? '在线但暂无完整指标' : '离线或暂未采集'}。`)} 风险 ${escapeHtml(riskText)}，健康 ${escapeHtml(String(summary.health_score ?? '--'))}。</div>
                    <div class="snmp-compact-grid">${tiles.map(tile => `<div class="snmp-compact-tile"><div class="label">${escapeHtml(tile.label)}</div><div class="value">${escapeHtml(String(tile.value ?? '--'))}</div></div>`).join('')}</div>
                    ${errorNote}
                    ${interactive ? '<div class="snmp-compact-action">查看完整详情</div>' : ''}
                </div>
            </div>`;
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
                    { label: 'CPU / 内存', value: `${summary.cpu_avg_percent ?? '--'}% / ${summary.memory_usage_percent ?? '--'}%`, meta: `温度 ${snmpProvidedText(routerCpuTemp)}` , level: Number(summary.cpu_peak_percent || 0) >= 80 ? 'warning' : getSnmpAlertLevel(summary.memory_alert_level)},
                    { label: '连接 / 告警', value: `${snmpProvidedText(routerConnections)} / ${(summary.alert_counts || {}).warning ?? 0}`, meta: `异常口 ${(interfaceSummary.error_port_count ?? 0) + (interfaceSummary.discard_port_count ?? 0)}` , level: Number(interfaceSummary.error_port_count || 0) > 0 || Number(interfaceSummary.discard_port_count || 0) > 0 ? 'warning' : '' }
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
            if (deviceType === 'nvr') {
                const offlineNames = (Array.isArray(status.offline_channels) ? status.offline_channels : [])
                    .slice(0, 2)
                    .map(item => item?.name || `D${item?.id || ''}`)
                    .filter(Boolean)
                    .join(' / ');
                items.push(
                    { label: '通道在线', value: `${summary.channel_online ?? 0} / ${summary.channel_total ?? 0}`, meta: offlineNames ? `离线 ${offlineNames}` : '通道正常', level: Number(summary.channel_offline || 0) > 0 ? 'warning' : '' },
                    { label: '硬盘', value: `${summary.hdd_ok_count ?? 0} / ${summary.hdd_total ?? 0}`, meta: `剩余 ${status.hdd_free_text || '--'}`, level: Number(summary.hdd_error_count || 0) > 0 ? 'critical' : '' },
                    { label: '内存 / 运行', value: `${status.memory_usage_percent ?? '--'}%`, meta: status.uptime_text || '--', level: Number(status.memory_usage_percent || 0) >= 85 ? 'warning' : '' },
                    { label: '弱密码', value: `${summary.weak_password_count ?? 0}`, meta: '通道安全', level: Number(summary.weak_password_count || 0) > 0 ? 'warning' : '' }
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
        function renderSnmpCard(cfg, status) {
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
            const online = statusMeta.isOnlineLike;
            const version = String((status.version || cfg.version || 'v2c')).toUpperCase();
            const sysName = status.sys_name || '--';
            const updatedAt = status.updated_at ? String(status.updated_at).replace('T', ' ').slice(0, 19) : '--';
            const hasFreshData = !!(status.updated_at || status.raw_oids || (Array.isArray(status.walk_samples) && status.walk_samples.length));
            const pollStateText = cfg.enabled === false ? '已停用' : (hasFreshData ? '已采集' : '等待采集');
            const customMetrics = Array.isArray(status.custom_metrics) ? status.custom_metrics : [];
            const summary = status.summary || {};
            const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
            const interfaceSummary = summary.interface_summary || {};
            const protocolProfile = getSnmpProtocolProfile(cfg, status, summary);
            const deviceTypeLabel = getSnmpDeviceTypeLabel(deviceType);
            const deviceIcon = getSnmpDeviceIcon(deviceType);
            const displayName = normalizeSnmpDeviceName(cfg, status);
            const heroPort = deviceType === 'nvr' ? (cfg.port || 80) : (cfg.port || 161);
            const heroSubtitle = `${escapeHtml(cfg.brand || '--')} / ${escapeHtml(cfg.model || '--')} / ${escapeHtml(cfg.host || '--')}:${escapeHtml(String(heroPort))}`;
            const shouldCompact = !online || (!hasFreshData && deviceType !== 'nvr');
            if (shouldCompact) {
                return renderSnmpCompactCard(cfg, status, summary, deviceType, interfaceSummary);
            }
            const primaryMetricsHtml = renderSnmpInlineMetrics(buildSnmpPrimaryMetricItems(deviceType, summary, status, customMetrics), '当前无核心指标');
            const deviceFactsHtml = renderSnmpMiniList(buildSnmpDeviceFactItems(deviceType, summary, status), { maxCount: 4, emptyText: '暂无设备摘要' });
            const primaryPanelsHtml = renderSnmpDevicePrimaryPanels(cfg.id, deviceType, summary, status, customMetrics);
            const advancedHtml = renderSnmpAdvancedDetails(cfg.id, deviceType, summary, status, customMetrics);
            return `<div class="ups-card snmp-device-card ${getCardStateClass(statusMeta)} ${online ? '' : 'offline'}">
                <div class="snmp-device-shell">
                    <div class="snmp-device-summary">
                        <div class="snmp-hero">
                            <div class="snmp-hero-main">
                                <div class="snmp-device-icon ${escapeHtml(deviceType)}">${deviceIcon}</div>
                                <div class="snmp-hero-text">
                                    <div class="snmp-hero-kicker">
                                        <span class="ups-chip">${escapeHtml(deviceTypeLabel)}</span>
                                        <span class="ups-chip">${escapeHtml(String(sysName))}</span>
                                    </div>
                                    <div class="snmp-hero-title">${escapeHtml(displayName)}</div>
                                    <div class="snmp-hero-subtitle">${heroSubtitle}</div>
                                </div>
                            </div>
                            <div class="ups-chip-row">
                                <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                                <span class="ups-chip">${escapeHtml(version)}</span>
                                <span class="ups-chip ${protocolProfile.level === 'warning' ? 'warning' : ''}">${escapeHtml(protocolProfile.label)}</span>
                                <span class="ups-chip">${escapeHtml(pollStateText)}</span>
                                <span class="ups-chip">${escapeHtml(updatedAt)}</span>
                            </div>
                        </div>
                        ${renderSnmpHealthPill(summary)}
                        ${deviceFactsHtml}
                    </div>
                    <div class="snmp-device-content">
                        ${primaryMetricsHtml}
                        ${primaryPanelsHtml}
                        ${advancedHtml}
                    </div>
                </div>
                ${status.error ? `<div style="margin-top:10px; color:#fca5a5; font-size:12px; line-height:1.7;">异常: ${escapeHtml(String(status.error))}</div>` : ''}
            </div>`;
        }
        function renderSnmpDeviceDetailPage(cfg, status) {
            const displayName = normalizeSnmpDeviceName(cfg, status || {});
            const summary = (status || {}).summary || {};
            const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
            const statusMeta = getDeviceStatusMeta(status || {}, { staleText: '陈旧', errorText: '异常' });
            const updatedAt = (status || {}).updated_at ? String((status || {}).updated_at).replace('T', ' ').slice(0, 19) : '--';
            const statusLine = `${getSnmpDeviceTypeLabel(deviceType)} · ${statusMeta.text} · 更新时间 ${updatedAt}`;
            return `<div class="snmp-detail-page">
                <div class="snmp-detail-toolbar">
                    <button type="button" class="snmp-detail-back" data-snmp-back-overview="1">返回总览</button>
                    <div class="snmp-detail-heading">
                        <div class="snmp-detail-title">${escapeHtml(displayName)}</div>
                        <div class="snmp-detail-subtitle">${escapeHtml(statusLine)} · ${escapeHtml(cfg.host || '--')}</div>
                    </div>
                    <div class="snmp-detail-toolbar-actions">
                        <span class="ups-chip ${statusMeta.chipClass}">${escapeHtml(statusMeta.text)}</span>
                        <span class="ups-chip">${escapeHtml(String((status || {}).version || cfg.version || 'v2c').toUpperCase())}</span>
                    </div>
                </div>
                <div class="snmp-detail-card-wrap">${renderSnmpCard(cfg, status || {})}</div>
            </div>`;
        }
        function renderSnmpCards(options = {}) {
            const renderMode = String(options.mode || snmpStatusMode || '').trim().toLowerCase();
            const renderDetailPage = options.renderDetailPage !== undefined
                ? !!options.renderDetailPage
                : renderMode === 'full';
            const dashboardGrid = document.getElementById('dashboard-snmp-grid');
            const pageGrid = document.getElementById('snmp-page-grid');
            const statusCache = getNetworkStatusCache();
            const visibleConfigs = getNetworkMonitorConfigs();
            visibleConfigs.sort((a, b) => {
                const sa = (statusCache[a.id] || {}).summary || {};
                const sb = (statusCache[b.id] || {}).summary || {};
                const riskRank = value => {
                    const normalized = String(value || '').trim().toLowerCase();
                    if (normalized === 'critical') return 0;
                    if (normalized === 'warning') return 1;
                    return 2;
                };
                const rankDiff = riskRank(sa.risk_level) - riskRank(sb.risk_level);
                if (rankDiff !== 0) return rankDiff;
                const scoreA = Number(sa.health_score ?? 100);
                const scoreB = Number(sb.health_score ?? 100);
                if (scoreA !== scoreB) return scoreA - scoreB;
                return normalizeSnmpDeviceName(a, statusCache[a.id] || {}).localeCompare(normalizeSnmpDeviceName(b, statusCache[b.id] || {}), 'zh-CN');
            });
            const filteredConfigs = filterSnmpConfigs(visibleConfigs, statusCache, snmpCardFilter);
            const filterMeta = getSnmpFilterMeta(snmpCardFilter);
            const onlineCount = visibleConfigs.filter(cfg => getDeviceStatusMeta(statusCache[cfg.id] || {}).isOnlineLike).length;
            const criticalCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'critical').length;
            const warningCount = visibleConfigs.filter(cfg => String(((statusCache[cfg.id] || {}).summary || {}).risk_level || '').toLowerCase() === 'warning').length;
            const dashboardCardsHtml = filteredConfigs.length
                ? `<div class="snmp-dashboard-grid">${filteredConfigs.map(cfg => renderDashboardSnmpCard(cfg, statusCache[cfg.id] || {})).join('')}</div>`
                : `<div class="snmp-filter-empty"><strong>${escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片。</div>`;
            const dashboardHtml = visibleConfigs.length
                ? `${dashboardCardsHtml}`
                : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
            if (dashboardGrid) dashboardGrid.innerHTML = dashboardHtml;
            if (pageGrid && renderDetailPage) {
                const pageOverviewHtml = renderSnmpOverviewBar(visibleConfigs, statusCache, snmpCardFilter);
                const selectedConfig = snmpSelectedDeviceId
                    ? visibleConfigs.find(cfg => String(cfg.id || '') === snmpSelectedDeviceId)
                    : null;
                if (snmpSelectedDeviceId && !selectedConfig) {
                    snmpSelectedDeviceId = '';
                    syncSnmpSelectedDeviceToUrl('');
                }
                const pageCardsHtml = selectedConfig
                    ? renderSnmpDeviceDetailPage(selectedConfig, statusCache[selectedConfig.id] || {})
                    : (filteredConfigs.length
                        ? `<div class="snmp-device-grid snmp-onepage-grid">${filteredConfigs.map(cfg => {
                            const status = statusCache[cfg.id] || {};
                            const summary = status.summary || {};
                            const deviceType = String(summary.device_type || cfg.device_type || 'network').trim().toLowerCase() || 'network';
                            return renderSnmpCompactCard(cfg, status, summary, deviceType, summary.interface_summary || {}, { interactive: true });
                        }).join('')}</div>`
                        : `<div class="snmp-filter-empty"><strong>${escapeHtml(filterMeta.label)} 暂无设备</strong>当前没有匹配该筛选条件的网络监控卡片，可切换上方统计卡查看其他设备。</div>`);
                const pageHtml = visibleConfigs.length
                    ? `${pageOverviewHtml}${pageCardsHtml}`
                    : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">未配置网络监控设备</div>';
                pageGrid.innerHTML = pageHtml;
            }
            const dashSnmpOnline = document.getElementById('dash-snmp-online');
            const dashSnmpTotal = document.getElementById('dash-snmp-total');
            const dashSnmpCritical = document.getElementById('dash-snmp-critical');
            const dashSnmpWarning = document.getElementById('dash-snmp-warning');
            const dashSnmpAlert = document.getElementById('dash-snmp-alert');
            if (dashSnmpOnline) dashSnmpOnline.innerText = String(onlineCount);
            if (dashSnmpTotal) dashSnmpTotal.innerText = String(visibleConfigs.length);
            if (dashSnmpCritical) dashSnmpCritical.innerText = String(criticalCount);
            if (dashSnmpWarning) dashSnmpWarning.innerText = String(warningCount);
            if (dashSnmpAlert) dashSnmpAlert.innerText = String(criticalCount + warningCount);
            [dashboardGrid, renderDetailPage ? pageGrid : null].filter(Boolean).forEach(grid => {
	            grid.querySelectorAll('[data-snmp-filter]').forEach(btn => {
	                btn.addEventListener('click', () => {
	                    const nextFilter = String(btn.getAttribute('data-snmp-filter') || 'all').trim().toLowerCase() || 'all';
	                    snmpCardFilter = nextFilter === snmpCardFilter ? 'all' : nextFilter;
                        snmpSelectedDeviceId = '';
                        syncSnmpSelectedDeviceToUrl('');
	                    renderSnmpCards();
	                });
	            });
                bindSnmpDetailToggles(grid);
                bindSnmpOverviewCardActions(grid);
            });
        }
        function renderUpsCompanionCard(cfg, status) {
            const statusMeta = getDeviceStatusMeta(status, { staleText: '陈旧', errorText: '异常' });
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
            const loadText = fmt(status.load_percent, 1, '%');
            const inputText = fmt(status.input_voltage, 1, 'V');
            const outputText = fmt(status.output_voltage, 1, 'V');
            const modeText = status.supply_state || status.system_mode || '--';
            const mainsText = status.mains_abnormal ? '异常' : '正常';
            const batteryStateText = status.is_battery_low ? '偏低' : '正常';
            const faultCount = Array.isArray(status.fault_labels) ? status.fault_labels.length : 0;
            const warningCount = Array.isArray(status.warning_labels) ? status.warning_labels.length : 0;
            const powerText = fmtAuto(status.total_real_power_kw, 'kW');
            const alarmText = faultCount > 0 || warningCount > 0 ? `故障 ${faultCount} / 告警 ${warningCount}` : '无告警';
            const alarmClass = faultCount > 0 ? 'error' : (warningCount > 0 ? 'warn' : 'ok');
            const queryWarnings = Array.isArray(status.query_warnings) ? status.query_warnings : [];
            const protocolSupport = status.protocol_support || {};
            const fallbackChips = [];
            if (protocolSupport.q6_fallback) fallbackChips.push('Q6回退');
            if (protocolSupport.wa_fallback) fallbackChips.push('WA回退');
            const errorText = (status.last_error || status.error) ? `异常：${status.last_error || status.error}` : '';
            const noteText = errorText || (fallbackChips.length ? `协议回退：${fallbackChips.join(' / ')}` : '') || queryWarnings[0] || statusMeta.note || '';
            return `<div class="screen-companion-card screen-companion-ups wide ${getCardStateClass(statusMeta)}">
                <div class="screen-companion-title">
                    <span>${escapeHtml(cfg.name || cfg.id)}</span>
                    <span class="screen-companion-title-actions">
                        <span class="screen-companion-tag" style="${statusMeta.chipClass === 'online' ? 'color:#bbf7d0;background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.30);' : (statusMeta.chipClass === 'warning' ? 'color:#fcd34d;background:rgba(245,158,11,0.16);border-color:rgba(245,158,11,0.24);' : 'color:#cbd5e1;background:rgba(100,116,139,0.16);border-color:rgba(148,163,184,0.18);')}">UPS ${statusMeta.text}</span>
                        <span class="screen-companion-tag ups-alarm-chip ${alarmClass}">${escapeHtml(alarmText)}</span>
                    </span>
                </div>
                <div class="screen-companion-metrics">
                    <div class="screen-companion-metric">
                        <div class="label">模式</div>
                        <div class="value">${escapeHtml(modeText)}</div>
                    </div>
                    <div class="screen-companion-metric">
                        <div class="label">负载</div>
                        <div class="value">${escapeHtml(loadText)}</div>
                    </div>
                    <div class="screen-companion-metric">
                        <div class="label">电压</div>
                        <div class="value">
                            <div class="screen-companion-pair">
                                <div class="screen-companion-pair-row"><span class="mini-label">输入</span><span class="mini-value">${escapeHtml(inputText)}</span></div>
                                <div class="screen-companion-pair-row"><span class="mini-label">输出</span><span class="mini-value">${escapeHtml(outputText)}</span></div>
                            </div>
                        </div>
                    </div>
                    <div class="screen-companion-metric">
                        <div class="label">电池容量</div>
                        <div class="value">${escapeHtml(batteryText)}</div>
                    </div>
                    <div class="screen-companion-metric">
                        <div class="label">总功率</div>
                        <div class="value">${escapeHtml(powerText)}</div>
                    </div>
                    <div class="screen-companion-metric">
                        <div class="label">供电</div>
                        <div class="value">
                            <div class="screen-companion-pair">
                                <div class="screen-companion-pair-row"><span class="mini-label">市电</span><span class="mini-value">${escapeHtml(mainsText)}</span></div>
                                <div class="screen-companion-pair-row"><span class="mini-label">电池</span><span class="mini-value">${escapeHtml(batteryStateText)}</span></div>
                            </div>
                        </div>
                    </div>
                </div>
                ${noteText ? `<div class="screen-companion-note ${(errorText || statusMeta.level === 'error') ? 'error' : ''}">${escapeHtml(noteText)}</div>` : ''}
                <div class="screen-companion-footer">
                    <span>${escapeHtml(cfg.comm_mode || 'TCP')}</span>
                    <span>${escapeHtml(statusMeta.note || '状态正常')}</span>
                </div>
            </div>`;
        }
        function updateUpsStatus() {
            fetch('/api/ups/status')
                .then(r => r.json())
                .then(data => {
                    upsStatusCache = data || {};
                    renderUpsCards();
                    renderDashboardUpsCompact();
                })
                .catch(err => console.error('UPS 状态更新失败', err));
        }
        function updateSnmpStatus(options = {}) {
            const forceFull = !!options.full || getActiveViewId() === 'snmp';
            const mode = forceFull ? 'full' : 'compact';
            if (snmpFetchInFlight) {
                if (snmpFetchMode === mode || (mode === 'compact' && snmpFetchMode === 'full')) return snmpFetchInFlight;
                if (mode === 'full') return snmpFetchInFlight.then(() => updateSnmpStatus({ full: true }));
                return snmpFetchInFlight;
            }
            const snmpUrl = mode === 'full' ? '/api/snmp/status' : '/api/snmp/status?compact=1';
            const nvrUrl = mode === 'full' ? '/api/nvr/status' : '/api/nvr/status?compact=1';
            const safeRenderSnmpCards = () => guardFrontendStep('snmp.render_cards', () => renderSnmpCards({
                mode,
                renderDetailPage: mode === 'full'
            }), '网络监控卡片渲染异常，请稍后重试');
            snmpFetchMode = mode;
            snmpFetchInFlight = Promise.allSettled([
                fetchJson(snmpUrl, {}, 'SNMP 状态读取失败'),
                nvrConfigs.length ? fetchJson(nvrUrl, {}, '录像机状态读取失败') : Promise.resolve({})
            ])
                .then(results => {
                    const [snmpResult, nvrResult] = results;
                    const snmpFailed = snmpResult.status === 'rejected';
                    const nvrFailed = nvrResult.status === 'rejected';
                    if (snmpFailed && nvrFailed) {
                        throw snmpResult.reason || nvrResult.reason || new Error('网络监控状态读取失败');
                    }
                    if (snmpFailed) console.error('SNMP 状态更新失败', snmpResult.reason);
                    if (nvrFailed) console.error('录像机状态更新失败', nvrResult.reason);
                    const nextSnmpData = snmpResult.status === 'fulfilled' ? (snmpResult.value || {}) : (snmpStatusCache || {});
                    const rawNvrData = nvrResult.status === 'fulfilled' ? (nvrResult.value || {}) : (nvrStatusCache || {});
                    const nextNvrData = {};
                    (Array.isArray(nvrConfigs) ? nvrConfigs : []).forEach(cfg => {
                        if (!cfg || !cfg.id) return;
                        nextNvrData[cfg.id] = normalizeNvrStatusForSnmp(cfg, rawNvrData[cfg.id] || {});
                    });
                    snmpStatusCache = nextSnmpData;
                    nvrStatusCache = nextNvrData;
                    const mergedData = getNetworkStatusCache();
                    const nextSignature = `${mode}:${summarizeSnmpPayload(mergedData)}`;
                    const shouldRender = nextSignature !== snmpStatusSignature;
                    snmpLastSuccessAt = Date.now();
                    snmpFetchFailureCount = 0;
                    snmpStatusMode = mode;
                    if (shouldRender) {
                        snmpStatusSignature = nextSignature;
                        const now = Date.now();
                        const elapsed = now - snmpLastRenderAt;
                        if (elapsed >= 300) {
                            snmpLastRenderAt = now;
                            safeRenderSnmpCards();
                        } else {
                            setTimeout(() => {
                                snmpLastRenderAt = Date.now();
                                safeRenderSnmpCards();
                            }, 300 - elapsed);
                        }
                    }
                })
                .catch(err => {
                    console.error('网络监控状态更新失败', err);
                    snmpFetchFailureCount += 1;
                    const now = Date.now();
                    const hasCache = Object.keys(getNetworkStatusCache() || {}).length > 0;
                    const cacheStillWarm = hasCache && snmpLastSuccessAt && (now - snmpLastSuccessAt) < 45000;
                    const shouldToast = !cacheStillWarm && (
                        !hasCache
                        || snmpFetchFailureCount >= 2
                    ) && (now - snmpLastToastAt) > 15000;
                    if (shouldToast) {
                        snmpLastToastAt = now;
                        showToast(translateApiError(err?.message, '网络监控状态读取失败，请稍后重试'), true);
                    }
                })
                .finally(() => {
                    snmpFetchInFlight = null;
                    snmpFetchMode = '';
                });
            return snmpFetchInFlight;
        }
        function sendUpsShutdown(id, delay) {
            if (!ensurePermission('ups.control', '操作 UPS')) return;
            if (!confirm(`确定向 UPS 下发延时关机命令 S${delay} 吗？`)) return;
            fetch('/api/ups/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, action: 'shutdown', delay })
            }).then(r => r.json()).then(data => {
                if (!data.success) {
                    showToast(data.message || 'UPS 指令执行失败', true);
                    return;
                }
                showToast(`UPS 指令已下发: ${data.command || 'S<n>'}`);
            }).catch(() => showToast('UPS 指令下发失败', true));
        }
