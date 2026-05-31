// AI_MODULE: server_runtime
// AI_PURPOSE: 服务器监控运行时，负责机器列表轮询、WOL/关机/重启/刷新、排序、部署命令和导出。
// AI_BOUNDARY: 详情卡片 HTML 仍由 server-monitor.js 渲染；首页摘要仍由 server-summary.js 渲染。
// AI_DATA_FLOW: /api/machines -> serverRuntime 缓存 -> server page/dashboard summary；用户点击 -> /api/wake 或 /api/machines/*/command。
// AI_RUNTIME: 进入 server 视图或首页服务器摘要接近视口时按需加载，避免主运行时首屏解析服务器详情逻辑。
// AI_RISK: 高，包含真实服务器控制链路；必须保留权限校验、确认弹窗、payload 和状态回读。
// AI_SEARCH_KEYWORDS: server runtime, server monitor polling, wake on lan, agent deploy, codemeter export.

(function installSmartCenterServerRuntime(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const state = SmartCenter.serverRuntime = Object.assign({
        globalServerList: [],
        dashboardServerCompactList: [],
        serverCommandPending: {},
        latestAgentVersion: '',
        serverViewMode: null,
        serverGridRenderToken: 0,
        serverGridSignature: '',
        serverDataRequestInFlight: null,
    }, SmartCenter.serverRuntime || {});

    let serverCommandRefreshTimer = null;

    function fallbackEscapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]));
    }

    function fallbackTranslateApiError(error, fallbackText = '请求失败') {
        return String(error || fallbackText || '请求失败');
    }

    function readServerViewMode() {
        if (state.serverViewMode) return state.serverViewMode;
        try {
            state.serverViewMode = global.localStorage?.getItem('smart-center-server-view-mode') || 'compact';
        } catch (_) {
            state.serverViewMode = 'compact';
        }
        return state.serverViewMode;
    }

    function getContext(context = {}) {
        const configData = context.configData || global.configData || {};
        const serverMonitorConfig = context.serverMonitorConfig || configData.server_monitor || { agent_host: '', agent_port: 6899 };
        if (!state.latestAgentVersion) {
            state.latestAgentVersion = String(serverMonitorConfig.agent_version || '').trim();
        }
        return Object.assign({
            configData,
            serverMonitorConfig,
            fetchJson: utils.fetchJson || global.fetchJson,
            postJsonLoose: utils.postJsonLoose || global.postJsonLoose,
            translateApiError: utils.translateApiError || global.translateApiError || fallbackTranslateApiError,
            ensurePermission: utils.ensurePermission || global.ensurePermission || (() => false),
            showToast: utils.showToast || global.showToast || (() => {}),
            escapeHtml: utils.escapeHtml || global.escapeHtml || fallbackEscapeHtml,
            getActiveViewId: global.getActiveViewId || (() => 'dashboard'),
            ensureModulesReady: global.ensureModulesReady || ((modules) => SmartCenter.ensureModules ? SmartCenter.ensureModules(modules) : Promise.resolve([])),
            isDashboardSectionNearViewport: global.isDashboardSectionNearViewport || (() => true),
            scheduleDashboardDeferredModule: global.scheduleDashboardDeferredModule || (() => {}),
            getPermissionDisabledClass: utils.getPermissionDisabledClass || global.getPermissionDisabledClass || (() => ''),
            getPermissionDisabledAttrs: utils.getPermissionDisabledAttrs || global.getPermissionDisabledAttrs || (() => ''),
            copyTextWithToast: global.copyTextWithToast || ((text) => {
                if (global.navigator?.clipboard?.writeText) return global.navigator.clipboard.writeText(String(text || ''));
                return Promise.resolve(false);
            }),
            compareAgentVersionBase: global.compareAgentVersionBase || (() => 0),
        }, context || {});
    }

    function getServerSummaryApi() {
        return SmartCenter.serverSummary || SmartCenter.serverMonitor || null;
    }

    function getServerMonitorApi() {
        return SmartCenter.serverMonitor || null;
    }

    function monitorCall(name, fallback, args) {
        const api = getServerMonitorApi();
        const fn = api && typeof api[name] === 'function' ? api[name] : fallback;
        return fn.apply(api || null, args);
    }

    function summaryCall(name, fallback, args) {
        const api = getServerSummaryApi();
        const fn = api && typeof api[name] === 'function' ? api[name] : fallback;
        return fn.apply(api || null, args);
    }

    function getServerRenderContext(context = {}) {
        const ctx = getContext(context);
        return {
            serverViewMode: readServerViewMode(),
            latestAgentVersion: state.latestAgentVersion,
            compareAgentVersionBase: ctx.compareAgentVersionBase,
            getPermissionDisabledClass: ctx.getPermissionDisabledClass,
            getPermissionDisabledAttrs: ctx.getPermissionDisabledAttrs,
            getServerCommandPending,
        };
    }

    function buildServerDiagnostic(agent = {}, machine = {}, context = {}) {
        const api = getServerSummaryApi();
        if (!api || typeof api.buildServerDiagnostic !== 'function') {
            return { level: 'warn', badgeText: '摘要加载中', reportOnline: false, summary: '服务器摘要模块加载中' };
        }
        return api.buildServerDiagnostic(agent, machine, getServerRenderContext(context));
    }

    function getAgentBaseUrl(context = {}) {
        const ctx = getContext(context);
        const cfg = ctx.serverMonitorConfig || {};
        const host = String(cfg.agent_host || '').trim() || global.location.hostname;
        const port = Number.parseInt(cfg.agent_port || 6899, 10) || 6899;
        return `http://${host}:${port}`;
    }

    function getDeployBatUrl(context = {}) {
        return `${getAgentBaseUrl(context)}/deploy_agent.bat`;
    }

    function getDeployCommandText(context = {}) {
        const batUrl = `${getDeployBatUrl(context)}?ts=$(Get-Date -Format yyyyMMddHHmmss)`;
        return `$u="${batUrl}"; $p="$env:TEMP\\smart-center-deploy.bat"; iwr -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -Uri $u -OutFile $p; Start-Process -FilePath $p -Verb RunAs`;
    }

    function formatDeployGeneratedAt(date = new Date()) {
        const pad = value => String(value).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    function updateDeployModalInfo(context = {}) {
        const versionEl = document.getElementById('deploy-agent-version-text');
        if (versionEl) versionEl.textContent = state.latestAgentVersion || '读取中...';
        const generatedAtEl = document.getElementById('deploy-generated-at-text');
        if (generatedAtEl) generatedAtEl.textContent = formatDeployGeneratedAt();
        const deployCmdEl = document.getElementById('deploy-cmd-text');
        if (deployCmdEl) deployCmdEl.textContent = getDeployCommandText(context);
        const deployBatUrlEl = document.getElementById('deploy-bat-url-text');
        if (deployBatUrlEl) deployBatUrlEl.textContent = getDeployBatUrl(context);
    }

    function refreshLatestAgentVersion(context = {}) {
        const ctx = getContext(context);
        if (typeof ctx.fetchJson !== 'function') return Promise.resolve(state.latestAgentVersion);
        const ts = Date.now();
        const primaryUrl = `/agent/config?probe=1&ts=${ts}`;
        const fallbackUrl = `${getAgentBaseUrl(ctx)}/agent/config?probe=1&ts=${ts}`;
        const applyVersion = data => {
            const version = String(data?.version || '').trim();
            if (version) {
                state.latestAgentVersion = version;
                updateDeployModalInfo(ctx);
                if (Array.isArray(state.globalServerList) && state.globalServerList.length) {
                    renderServerGridDeferred(state.globalServerList, { force: true }, ctx);
                    renderDashboardServerCompactWhenReady(state.globalServerList, ctx);
                }
            }
            return state.latestAgentVersion;
        };
        return ctx.fetchJson(primaryUrl, {}, '读取 Agent 最新版本失败')
            .catch(() => ctx.fetchJson(fallbackUrl, {}, '读取 Agent 最新版本失败'))
            .then(applyVersion)
            .catch(err => {
                console.warn('Agent 最新版本读取失败', err);
                return state.latestAgentVersion;
            });
    }

    function openDeployModal(context = {}) {
        const ctx = getContext(context);
        updateDeployModalInfo(ctx);
        const modal = document.getElementById('deployModal');
        if (modal) modal.style.display = 'block';
        return refreshLatestAgentVersion(ctx).finally(() => updateDeployModalInfo(ctx));
    }

    function copyDeployCommand(context = {}) {
        const ctx = getContext(context);
        return ctx.copyTextWithToast(getDeployCommandText(ctx), '覆盖安装命令已复制');
    }

    function copyDeployBatUrl(context = {}) {
        const ctx = getContext(context);
        return ctx.copyTextWithToast(getDeployBatUrl(ctx), '批处理地址已复制');
    }

    function wakeServer(mac, context = {}) {
        const ctx = getContext(context);
        if (!ctx.ensurePermission('server.control', '唤醒服务器节点')) return Promise.resolve(false);
        if (String(mac || '').startsWith('TEMP')) {
            ctx.showToast('没有真实 MAC 地址，无法发送网络唤醒', true);
            return Promise.resolve(false);
        }
        if (!global.confirm('确定发送网络唤醒魔术包(WOL)吗？')) return Promise.resolve(false);
        return ctx.fetchJson('/api/wake/' + encodeURIComponent(mac), { method: 'POST' }, '唤醒请求失败')
            .then(result => {
                const targets = Array.isArray(result?.targets) ? result.targets.length : 0;
                markServerCommandPending(mac, 'wake', '唤醒');
                ctx.showToast(targets ? `唤醒包已发出，广播目标 ${targets} 个` : '唤醒包已发出');
                burstRefreshServerData(ctx);
                return result;
            })
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, '唤醒请求失败'), true);
                return false;
            });
    }

    function sendServerCmd(mac, cmd, context = {}) {
        const ctx = getContext(context);
        if (!ctx.ensurePermission('server.control', '下发服务器指令')) return Promise.resolve(false);
        const actionMap = { shutdown: '关机', restart: '重启', refresh: '刷新信息' };
        const actionName = actionMap[cmd] || cmd;
        const prompt = cmd === 'refresh' ? '确定要远程刷新此节点的硬件信息吗？' : `危险操作：确定要让此节点立刻【${actionName}】吗？`;
        if (!global.confirm(prompt)) return Promise.resolve(false);
        return ctx.postJsonLoose(`/api/machines/${mac}/command`, { command: cmd }, `指令 [${actionName}] 下发失败`)
            .then(result => {
                markServerCommandPending(mac, cmd, actionName);
                ctx.showToast(`指令 [${actionName}] 已进入下发队列`);
                burstRefreshServerData(ctx);
                return result;
            })
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, `指令 [${actionName}] 下发失败`), true);
                return false;
            });
    }

    function moveServer(mac, direction, context = {}) {
        const ctx = getContext(context);
        if (!ctx.ensurePermission('server.control', '调整服务器排序')) return Promise.resolve(false);
        const list = Array.isArray(state.globalServerList) ? state.globalServerList : [];
        const idx = list.findIndex(m => m.mac === mac);
        if (idx < 0) return Promise.resolve(false);
        const newIdx = idx + Number(direction || 0);
        if (newIdx < 0 || newIdx >= list.length) return Promise.resolve(false);
        const temp = list[idx];
        list[idx] = list[newIdx];
        list[newIdx] = temp;
        list.forEach((m, i) => { m.sort_order = i + 1; });
        renderServerGridDeferred(list, { force: true }, ctx);
        renderDashboardServerCompactWhenReady(list, ctx);
        return ctx.postJsonLoose('/api/machines/sort', { macs: list.map(m => m.mac) }, '服务器排序保存失败')
            .then(() => updateServerData(ctx))
            .catch(err => {
                ctx.showToast(ctx.translateApiError(err?.message, '服务器排序保存失败'), true);
                return updateServerData(ctx);
            });
    }

    function getServerGridSignature(machines) {
        try {
            return JSON.stringify((Array.isArray(machines) ? machines : []).map(m => [
                m.mac,
                m.is_online,
                m.report_online,
                m.runtime_fresh,
                m.last_online,
                m.server_received_at,
                m.clock_offset_sec,
                m.last_report_kind,
                m.sort_order,
                m.card_size,
                m.remark,
                m.status?.hardware_refreshed_at,
                m.status?.clock_heartbeat_at,
                m.agent_status?.version,
                m.diagnostic?.code,
                m.pending_power_command?.command,
                m.claimed_power_command?.command,
            ]));
        } catch (_) {
            return String(Date.now());
        }
    }

    function renderServerGridDeferred(machines, options = {}, context = {}) {
        const container = document.getElementById('server-grid-container');
        if (!container || !SmartCenter.serverMonitor) return;
        const signature = `${readServerViewMode()}|${getServerGridSignature(machines)}`;
        if (!options.force && signature === state.serverGridSignature) return;
        state.serverGridSignature = signature;
        const token = ++state.serverGridRenderToken;
        const renderNow = () => {
            if (token !== state.serverGridRenderToken) return;
            container.innerHTML = SmartCenter.serverMonitor.renderServerGroupedGrid(machines, getServerRenderContext(context));
        };
        if (typeof global.requestAnimationFrame === 'function') {
            global.requestAnimationFrame(() => global.requestAnimationFrame(renderNow));
        } else {
            global.setTimeout(renderNow, 0);
        }
    }

    function applyServerViewMode(mode) {
        state.serverViewMode = mode === 'detail' ? 'detail' : 'compact';
        document.querySelectorAll('[data-server-view-mode]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.serverViewMode === state.serverViewMode);
            btn.setAttribute('aria-pressed', btn.dataset.serverViewMode === state.serverViewMode ? 'true' : 'false');
        });
        const modeLabel = document.getElementById('server-mode-current');
        if (modeLabel) modeLabel.textContent = state.serverViewMode === 'detail' ? '详细模式' : '简洁模式';
        const container = document.getElementById('server-grid-container');
        if (container) container.classList.toggle('server-detail-mode', state.serverViewMode === 'detail');
    }

    function setServerViewMode(mode, context = {}) {
        applyServerViewMode(mode);
        try { global.localStorage?.setItem('smart-center-server-view-mode', state.serverViewMode); } catch (_) {}
        if (Array.isArray(state.globalServerList) && state.globalServerList.length) {
            renderServerGridDeferred(state.globalServerList, { force: true }, context);
        }
    }

    function csvCell(value) {
        const text = String(value ?? '').replace(/\r?\n/g, ' ').trim();
        return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    }

    function exportListCell(items) {
        return (items || []).map(item => String(item ?? '').trim()).filter(Boolean).join(' | ');
    }

    function normalizeDisplayMac(value) {
        return monitorCall('normalizeDisplayMac', val => String(val || '').trim(), arguments);
    }

    function getCodeMeterSerials(codemeter) {
        return monitorCall('getCodeMeterSerials', () => [], arguments);
    }

    function normalizeCodeMeterLicenses(codemeter, serials = []) {
        return monitorCall('normalizeCodeMeterLicenses', () => [], arguments);
    }

    function getCodeMeterValidityText(codemeter) {
        return monitorCall('getCodeMeterValidityText', () => '', arguments);
    }

    function getCodeMeterLicenseLabel(codemeter) {
        return monitorCall('getCodeMeterLicenseLabel', () => '', arguments);
    }

    function memoryChannelText(topology) {
        return monitorCall('memoryChannelText', () => '', arguments);
    }

    function getServerDisplayName(machine) {
        return summaryCall(
            'getServerDisplayName',
            item => item?.custom_name || item?.remark || item?.hostname || item?.ip || '未知节点',
            arguments
        );
    }

    function getServerDeviceInfoExportRows() {
        const rows = [];
        const list = Array.isArray(state.globalServerList) ? state.globalServerList : [];
        list.forEach(machine => {
            const st = machine.status || {};
            const network = st.network_summary || {};
            const wifi = st.wireless || {};
            const bt = st.bluetooth || {};
            const adapters = Array.isArray(st.network_adapters) ? st.network_adapters.filter(adapter => !adapter?.is_virtual) : [];
            const codemeter = st.codemeter && typeof st.codemeter === 'object' ? st.codemeter : {};
            const codemeterSerials = getCodeMeterSerials(codemeter);
            const codemeterLicenses = normalizeCodeMeterLicenses(codemeter, codemeterSerials);
            const codemeterValidity = getCodeMeterValidityText(codemeter);
            const codemeterLabel = getCodeMeterLicenseLabel(codemeter);
            const codemeterInstalled = codemeter.installed === true ? '已安装' : (codemeter.installed === false ? '未安装' : '');
            const codemeterRunning = codemeter.running === true ? '运行中' : (codemeter.running === false ? '未运行' : '');
            const licenseRows = codemeterLicenses.length ? codemeterLicenses : [];
            const nearestExpiringLicense = licenseRows
                .filter(license => !license.permanent && license.expiryText)
                .slice()
                .sort((a, b) => String(a.expiryText || '').localeCompare(String(b.expiryText || '')))[0];
            const adapterRows = adapters.map((adapter, index) => {
                const ips = Array.isArray(adapter?.ipv4) ? adapter.ipv4 : [adapter?.adapter_ip, adapter?.ip, adapter?.ipv4].filter(Boolean);
                const name = adapter?.description || adapter?.adapter_description || adapter?.name || adapter?.adapter_name || '';
                const mac = normalizeDisplayMac(adapter?.adapter_mac || adapter?.mac || adapter?.physical_mac || adapter?.address);
                const speed = adapter?.speed_mbps || adapter?.link_speed_mbps || adapter?.speed || '';
                const adapterState = adapter?.state || adapter?.status || '';
                const prefix = `${index + 1}.`;
                return {
                    name: name ? `${prefix} ${name}` : '',
                    ip: ips.length ? `${prefix} ${ips.join(' / ')}` : '',
                    mac: mac ? `${prefix} ${mac}` : '',
                    speed: speed ? `${prefix} ${speed}` : '',
                    state: adapterState ? `${prefix} ${adapterState}` : '',
                };
            });
            rows.push({
                name: getServerDisplayName(machine),
                group: machine.asset_group || '',
                ip: machine.ip || '',
                mac: machine.mac || '',
                cpu: st.cpu_name || '',
                motherboard: st.motherboard || '',
                mem_speed_mhz: st.mem_speed || '',
                os: st.os_info?.name || st.os_caption || st.os_version || '',
                memory: st.memory_topology?.installed_count ? `${st.memory_topology.installed_count}条 ${memoryChannelText(st.memory_topology)}` : '',
                disk_count: st.storage_summary?.disk_count ?? (Array.isArray(st.storage_devices) ? st.storage_devices.length : ''),
                network_summary: `${network.active_count ?? 0}/${network.physical_count ?? 0}网卡`,
                wireless: wifi.present ? (wifi.connected ? `Wi-Fi ${wifi.ssid || '已连接'}` : 'Wi-Fi未连') : '',
                bluetooth: bt.present ? (bt.blocked ? '蓝牙阻塞' : '蓝牙') : '',
                adapter_name: exportListCell(adapterRows.map(item => item.name)),
                adapter_ip: exportListCell(adapterRows.map(item => item.ip)),
                adapter_mac: exportListCell(adapterRows.map(item => item.mac)),
                adapter_speed_mbps: exportListCell(adapterRows.map(item => item.speed)),
                adapter_state: exportListCell(adapterRows.map(item => item.state)),
                codemeter_installed: codemeterInstalled,
                codemeter_running: codemeterRunning,
                codemeter_validity: codemeterValidity,
                codemeter_label: codemeterLabel,
                codemeter_all_serials: codemeterSerials.join(' / '),
                codemeter_serial: licenseRows.length ? exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.serial || codemeterSerials.join(' / ')}`)) : codemeterSerials.join(' / '),
                codemeter_product_code: exportListCell(licenseRows.map((license, index) => license.code ? `${index + 1}. ${license.code}` : '')),
                codemeter_expiry: exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.permanent ? '长期' : (license.expiryText || '')}`)),
                codemeter_days_left: nearestExpiringLicense
                    ? `=MAX(0,DATEVALUE("${nearestExpiringLicense.expiryText}")-TODAY())`
                    : (licenseRows.some(license => license.permanent) ? '长期' : ''),
                codemeter_license_status: licenseRows.length
                    ? exportListCell(licenseRows.map((license, index) => `${index + 1}. ${license.expired ? '已过期' : (license.permanent ? '长期' : '有效')}`))
                    : codemeterValidity,
            });
        });
        return rows;
    }

    function exportServerDeviceInfoCsv(context = {}) {
        const ctx = getContext(context);
        const rows = getServerDeviceInfoExportRows();
        if (!rows.length) {
            ctx.showToast('暂无可导出的服务器设备信息', true);
            return;
        }
        const columns = [
            ['name', '设备名'],
            ['group', '分组'],
            ['ip', '管理IP'],
            ['mac', '主MAC'],
            ['cpu', 'CPU'],
            ['motherboard', '主板'],
            ['mem_speed_mhz', '内存频率MHz'],
            ['os', '系统'],
            ['memory', '内存'],
            ['disk_count', '硬盘数量'],
            ['network_summary', '网络汇总'],
            ['wireless', '无线'],
            ['bluetooth', '蓝牙'],
            ['adapter_name', '网卡名称'],
            ['adapter_ip', '网卡IP'],
            ['adapter_mac', '网卡MAC'],
            ['adapter_speed_mbps', '网卡速率Mbps'],
            ['adapter_state', '网卡状态'],
            ['codemeter_installed', '加密锁安装'],
            ['codemeter_running', '加密锁服务'],
            ['codemeter_validity', '加密锁状态'],
            ['codemeter_label', '加密锁授权'],
            ['codemeter_all_serials', '全部加密锁编号'],
            ['codemeter_serial', '加密锁编号'],
            ['codemeter_product_code', '产品码'],
            ['codemeter_expiry', '到期时间'],
            ['codemeter_days_left', '剩余天数'],
            ['codemeter_license_status', '授权状态'],
        ];
        const csv = [columns.map(([, label]) => csvCell(label)).join(',')]
            .concat(rows.map(row => columns.map(([key]) => csvCell(row[key])).join(',')))
            .join('\r\n');
        const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `server-device-info-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        ctx.showToast('服务器设备信息 CSV 已生成');
    }

    function renderDashboardServerCompact(data = [], context = {}) {
        const container = document.getElementById('dashboard-server-compact-grid');
        if (!container) return;
        const machines = Array.isArray(data) && data.length
            ? data
            : (Array.isArray(state.dashboardServerCompactList) && state.dashboardServerCompactList.length
                ? state.dashboardServerCompactList
                : (Array.isArray(state.globalServerList) ? state.globalServerList : []));
        if (SmartCenter.serverSummary && typeof SmartCenter.serverSummary.renderDashboardServerCompact === 'function') {
            SmartCenter.serverSummary.renderDashboardServerCompact(machines, {
                container,
                fallbackList: Array.isArray(state.dashboardServerCompactList) && state.dashboardServerCompactList.length
                    ? state.dashboardServerCompactList
                    : (Array.isArray(state.globalServerList) ? state.globalServerList : []),
            });
            return;
        }
        container.classList.add('home-status-list');
        container.innerHTML = machines.length
            ? '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">服务器摘要模块加载中...</div>'
            : '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">正在加载机器状态...</div>';
    }

    function renderDashboardServerCompactWhenReady(data = [], context = {}) {
        const ctx = getContext(context);
        const container = document.getElementById('dashboard-server-compact-grid');
        if (!container) return Promise.resolve(false);
        if (Array.isArray(data)) state.dashboardServerCompactList = data;
        if (SmartCenter.serverSummary) {
            renderDashboardServerCompact(state.dashboardServerCompactList, ctx);
            return Promise.resolve(true);
        }
        if (!String(container.innerHTML || '').trim()) {
            container.classList.add('home-status-list');
            container.innerHTML = '<div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:10px;">服务器摘要加载中...</div>';
        }
        if (ctx.getActiveViewId() === 'dashboard' && !ctx.isDashboardSectionNearViewport('server_compact')) {
            ctx.scheduleDashboardDeferredModule('server_compact', 0, 'summary');
            return Promise.resolve(false);
        }
        return ctx.ensureModulesReady(['server-summary-view'], '服务器摘要模块')
            .then(() => {
                renderDashboardServerCompact(state.dashboardServerCompactList, ctx);
                return true;
            })
            .catch(() => false);
    }

    function refreshDashboardServerCompactFallback(context = {}) {
        const container = document.getElementById('dashboard-server-compact-grid');
        if (!container) return Promise.resolve(false);
        const data = Array.isArray(state.dashboardServerCompactList) && state.dashboardServerCompactList.length
            ? state.dashboardServerCompactList
            : (Array.isArray(state.globalServerList) ? state.globalServerList : []);
        return renderDashboardServerCompactWhenReady(data, context);
    }

    function markServerCommandPending(mac, cmd, actionName) {
        const key = String(mac || '').trim().toUpperCase();
        if (!key) return;
        state.serverCommandPending[key] = {
            cmd,
            actionName: actionName || cmd,
            queuedAt: Date.now(),
        };
    }

    function getServerCommandPending(mac) {
        const key = String(mac || '').trim().toUpperCase();
        const pending = key ? state.serverCommandPending[key] : null;
        if (!pending) return null;
        const ageMs = Date.now() - Number(pending.queuedAt || 0);
        if (ageMs > 120000) {
            delete state.serverCommandPending[key];
            return null;
        }
        return { ...pending, ageMs };
    }

    function clearSettledServerCommandPending(machines = []) {
        machines.forEach(machine => {
            const key = String(machine?.mac || '').trim().toUpperCase();
            const pending = key ? state.serverCommandPending[key] : null;
            if (!pending) return;
            if ((pending.cmd === 'shutdown' || pending.cmd === 'restart') && machine?.is_online === false) {
                delete state.serverCommandPending[key];
            } else if (pending.cmd === 'refresh') {
                const status = machine?.status || {};
                const refreshedAt = Date.parse(status.hardware_refreshed_at || machine?.last_online || '');
                if (Number.isFinite(refreshedAt) && refreshedAt >= Number(pending.queuedAt || 0) - 5000) {
                    delete state.serverCommandPending[key];
                }
            }
        });
    }

    function burstRefreshServerData(context = {}) {
        updateServerData(context);
        [1500, 5000, 12000, 25000, 45000, 70000].forEach(delay => {
            global.setTimeout(() => updateServerData(context), delay);
        });
        if (serverCommandRefreshTimer) global.clearInterval(serverCommandRefreshTimer);
        const startedAt = Date.now();
        serverCommandRefreshTimer = global.setInterval(() => {
            if (Date.now() - startedAt > 90000) {
                global.clearInterval(serverCommandRefreshTimer);
                serverCommandRefreshTimer = null;
                return;
            }
            updateServerData(context);
        }, 5000);
    }

    function updateServerData(context = {}) {
        const ctx = getContext(context);
        if (state.serverDataRequestInFlight) return state.serverDataRequestInFlight;
        state.serverDataRequestInFlight = ctx.fetchJson('/api/machines', {}, '服务器列表读取失败')
            .then(data => {
                const list = Array.isArray(data) ? data : [];
                applyServerViewMode(readServerViewMode());
                list.sort((a, b) => {
                    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
                    return String(a.mac || '').localeCompare(String(b.mac || ''));
                });
                clearSettledServerCommandPending(list);
                state.globalServerList = list;
                const visibleFn = SmartCenter.serverSummary?.isServerDashboardVisible || SmartCenter.serverMonitor?.isServerDashboardVisible;
                const dashboardMachines = typeof visibleFn === 'function'
                    ? list.filter(machine => visibleFn(machine))
                    : list.filter(machine => String(machine?.asset_group || '').trim().length > 0);
                state.dashboardServerCompactList = dashboardMachines;
                const sTotal = document.getElementById('dash-server-total');
                if (sTotal) sTotal.innerText = dashboardMachines.length;
                const onlineCount = dashboardMachines.filter(m => m.is_online).length;
                const sOnline = document.getElementById('dash-server-online');
                if (sOnline) sOnline.innerText = onlineCount;
                renderServerGridDeferred(list, {}, ctx);
                renderDashboardServerCompactWhenReady(list, ctx);
                return list;
            })
            .catch(err => {
                console.error('服务器数据更新失败', err);
                return [];
            })
            .finally(() => {
                state.serverDataRequestInFlight = null;
            });
        return state.serverDataRequestInFlight;
    }

    function setDashboardServerCompactList(list = []) {
        state.dashboardServerCompactList = Array.isArray(list) ? list : [];
    }

    function setGlobalServerList(list = []) {
        state.globalServerList = Array.isArray(list) ? list : [];
    }

    function getStateSnapshot() {
        return {
            globalServerList: Array.isArray(state.globalServerList) ? state.globalServerList : [],
            dashboardServerCompactList: Array.isArray(state.dashboardServerCompactList) ? state.dashboardServerCompactList : [],
            latestAgentVersion: state.latestAgentVersion,
            serverViewMode: readServerViewMode(),
        };
    }

    const api = {
        state,
        getStateSnapshot,
        setDashboardServerCompactList,
        setGlobalServerList,
        getServerRenderContext,
        buildServerDiagnostic,
        getDeployBatUrl,
        getDeployCommandText,
        updateDeployModalInfo,
        openDeployModal,
        refreshLatestAgentVersion,
        copyDeployCommand,
        copyDeployBatUrl,
        wakeServer,
        sendServerCmd,
        moveServer,
        setServerViewMode,
        getServerDeviceInfoExportRows,
        exportServerDeviceInfoCsv,
        renderDashboardServerCompact,
        renderDashboardServerCompactWhenReady,
        refreshDashboardServerCompactFallback,
        markServerCommandPending,
        getServerCommandPending,
        clearSettledServerCommandPending,
        burstRefreshServerData,
        updateServerData,
    };

    Object.assign(state, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('views.server-runtime', {
            kind: 'runtime',
            exports: Object.keys(api),
            source: 'static/js/views/server-runtime.js',
        });
    }
})(window);
