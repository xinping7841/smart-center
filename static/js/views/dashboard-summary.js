// AI_MODULE: dashboard_summary_view
// AI_PURPOSE: 首页监控大屏摘要渲染，使用 /api/dashboard/summary 的只读轻量快照。
// AI_BOUNDARY: 不直接请求控制接口，不触发真实设备动作。
// AI_DATA_FLOW: /api/dashboard/summary -> 首页 DOM。
// AI_RUNTIME: 首页加载后执行，要求首屏快、布局稳定。

(function installSmartCenterDashboardSummary(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    function html(value) {
        const text = String(value ?? '');
        return text.replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function setClass(id, className) {
        const el = document.getElementById(id);
        if (el && className) el.className = className;
    }

    function setHtml(id, markup) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = markup;
    }

    function normalizeDashboardSummaryPayload(payload) {
        return payload && typeof payload === 'object' ? payload : { counts: {}, modules: {} };
    }

    function getCount(counts, key) {
        return (counts || {})[key] || {};
    }

    function countTotal(count = {}) {
        return Number(count.total || 0);
    }

    function countOnline(count = {}) {
        return Number(count.online || 0);
    }

    function countOffline(count = {}) {
        const total = countTotal(count);
        return Number(count.offline ?? Math.max(0, total - countOnline(count)));
    }

    function countProblem(count = {}) {
        return Number(count.error || 0) + Number(count.stale || 0) + countOffline(count);
    }

    function ratioText(count = {}) {
        const total = countTotal(count);
        if (!total) return '--';
        return `${Math.max(0, Math.min(100, countOnline(count) / total * 100)).toFixed(0)}%`;
    }

    function formatCount(count = {}) {
        const total = countTotal(count);
        return total > 0 ? `${countOnline(count)}/${total}` : '--';
    }

    function aggregateCounts(counts = {}) {
        const keys = ['power', 'light', 'projector', 'screen', 'hvac', 'sequencer', 'ups', 'snmp', 'server', 'door'];
        return keys.reduce((acc, key) => {
            const item = getCount(counts, key);
            acc.total += countTotal(item);
            acc.online += countOnline(item);
            acc.offline += countOffline(item);
            acc.error += Number(item.error || 0);
            acc.stale += Number(item.stale || 0);
            return acc;
        }, { total: 0, online: 0, offline: 0, error: 0, stale: 0 });
    }

    function toneFromCount(count = {}) {
        if (Number(count.error || 0) > 0 || countOffline(count) > 0) return 'danger';
        if (Number(count.stale || 0) > 0) return 'warn';
        return 'ok';
    }

    function pickEnvDevice(envModule = {}, context = {}) {
        const devices = Array.isArray(envModule.devices) ? envModule.devices : [];
        if (!devices.length) return null;
        const envMap = {};
        devices.forEach(item => {
            if (item && item.id) envMap[item.id] = item;
        });
        const picker = typeof context.pickDashboardEnvSensor === 'function'
            ? context.pickDashboardEnvSensor
            : global.pickDashboardEnvSensor;
        if (typeof picker === 'function') {
            const picked = picker(envMap);
            if (picked && picked.st) return picked.st;
        }
        return devices.find(item => item && item.online && item.temp !== null && item.temp !== undefined)
            || devices.find(item => item && item.online)
            || devices[0]
            || null;
    }

    function formatTimeShort(value) {
        if (!value) return '--';
        const dt = new Date(String(value).replace(' ', 'T'));
        if (Number.isNaN(dt.getTime())) return String(value).slice(0, 19);
        return dt.toLocaleTimeString('zh-CN', { hour12: false });
    }

    function formatMetric(value, suffix = '') {
        if (value === null || value === undefined || value === '') return '--';
        const n = Number(value);
        if (!Number.isFinite(n)) return String(value);
        return `${Math.round(n * 10) / 10}${suffix}`;
    }

    function setHeroChip(id, label, count = {}) {
        const el = document.getElementById(id);
        if (!el) return;
        const problem = countProblem(count);
        el.textContent = `${label} ${formatCount(count)}${problem ? ` · 异常 ${problem}` : ''}`;
        el.classList.toggle('danger', problem > 0 && toneFromCount(count) === 'danger');
        el.classList.toggle('warn', problem > 0 && toneFromCount(count) === 'warn');
    }

    function setDomainTile(key, label, count = {}, note = '') {
        const total = countTotal(count);
        const online = countOnline(count);
        const problems = countProblem(count);
        const tone = toneFromCount(count);
        const tile = document.getElementById(`dashboard-domain-${key}`);
        const bar = document.getElementById(`dashboard-domain-${key}-bar`);
        if (tile) {
            tile.classList.remove('ok', 'warn', 'danger', 'empty');
            tile.classList.add(total ? tone : 'empty');
        }
        setText(`dashboard-domain-${key}-badge`, total ? (tone === 'ok' ? '稳定' : (tone === 'warn' ? '关注' : '异常')) : '未配置');
        setText(`dashboard-domain-${key}-value`, total ? `${online}/${total}` : '--');
        setText(`dashboard-domain-${key}-note`, note || (total ? `异常 ${problems} · 在线率 ${ratioText(count)}` : `${label} 未配置或无快照`));
        if (bar) bar.style.width = total ? `${Math.max(4, Math.min(100, online / total * 100))}%` : '0%';
    }

    function renderDashboardEnvSummary(envModule = {}, context = {}) {
        const st = pickEnvDevice(envModule, context);
        const topSummary = document.getElementById('top-env-summary');
        if (st) {
            setText('top-env-temp', st.temp !== null && st.temp !== undefined ? `${st.temp}°C` : '--');
            setText('top-env-hum', st.hum !== null && st.hum !== undefined ? `${st.hum}%` : '--');
            setText('top-env-lux', st.lux !== null && st.lux !== undefined ? `${st.lux}Lux` : '--');
            if (topSummary) topSummary.style.opacity = st.online ? '1' : '0.75';
        }
    }

    function renderDashboardHero(payload, derived = {}, context = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const aggregate = aggregateCounts(counts);
        const total = aggregate.total;
        const online = aggregate.online;
        const offline = Math.max(0, aggregate.offline);
        const error = Math.max(0, aggregate.error);
        const stale = Math.max(0, aggregate.stale);
        const ratio = total > 0 ? `${Math.max(0, Math.min(100, online / total * 100)).toFixed(1)}%` : '--';

        setText('dashboard-monitor-rate', ratio);
        setText('dashboard-hero-online', total > 0 ? `${online}/${total}` : '--');
        setText('dashboard-hero-online-note', total > 0 ? `在线率 ${ratio}` : '暂无设备汇总');
        setText('dashboard-hero-alerts', String(error + offline + stale));
        setText('dashboard-hero-alerts-note', `离线 ${offline} · 异常 ${error} · 陈旧 ${stale}`);

        const env = pickEnvDevice(modules.env || {}, context);
        if (env) {
            const temp = env.temp !== null && env.temp !== undefined ? `${env.temp}°C` : '--';
            const hum = env.hum !== null && env.hum !== undefined ? `${env.hum}%` : '--';
            const lux = env.lux !== null && env.lux !== undefined ? `${env.lux}Lux` : '--';
            setText('dashboard-hero-env', temp);
            setText('dashboard-hero-env-note', `${hum} · ${lux} · ${env.name || env.id || '环境'}`);
        }

        const proxy = modules.proxy || {};
        const proxyOnline = !!proxy.online;
        const checks = Number(proxy.healthy_target_count || 0);
        const checkTotal = Number(proxy.check_count || 0);
        const latency = Number(proxy.google_latency_ms || proxy.required_check?.latency_ms);
        setText('dashboard-hero-proxy', proxyOnline ? '在线' : '异常');
        setText('dashboard-hero-proxy-note', checkTotal > 0 ? `${checks}/${checkTotal} 探活${Number.isFinite(latency) && latency > 0 ? ` · ${latency}ms` : ''}` : '等待代理探活');

        const localModel = modules.local_model || {};
        const priority = String(localModel.cloud_priority || '').toLowerCase();
        const policyText = priority === 'cloud_first' ? '云端优先' : (priority === 'local_first' ? '本地优先' : (priority || '--'));
        setText('dashboard-hero-ai-policy', policyText);
        setText('dashboard-hero-ai-note', `${localModel.cloud_enabled ? '云端启用' : '云端关闭'} · ${localModel.compare_with_local ? '本地对照' : '单路理解'}`);
        setText('dashboard-hero-feishu', localModel.feishu_control_enabled ? '已开启' : '查询模式');
        setText('dashboard-hero-feishu-note', localModel.feishu_require_confirmation ? '所有控制需确认' : '高风险控制需确认');
        setText('dashboard-hero-snmp', `${derived.snmpCritical || 0}/${derived.snmpWarning || 0}`);
        setText('dashboard-hero-snmp-note', `严重 ${derived.snmpCritical || 0} · 警告 ${derived.snmpWarning || 0}`);
        setText('dashboard-hero-updated', formatTimeShort(data.generated_at));
        setText('dashboard-hero-latency', `汇总接口 ${data.elapsed_ms ?? '--'}ms`);

        setHeroChip('dashboard-hero-chip-power', '强电柜', getCount(counts, 'power'));
        setHeroChip('dashboard-hero-chip-light', '灯光', getCount(counts, 'light'));
        setHeroChip('dashboard-hero-chip-projector', '投影', getCount(counts, 'projector'));
        setHeroChip('dashboard-hero-chip-screen', '幕布', getCount(counts, 'screen'));
        setHeroChip('dashboard-hero-chip-hvac', '空调', getCount(counts, 'hvac'));
        setHeroChip('dashboard-hero-chip-sequencer', '时序', getCount(counts, 'sequencer'));
        setHeroChip('dashboard-hero-chip-ups', 'UPS', getCount(counts, 'ups'));
        setHeroChip('dashboard-hero-chip-server', '机器', getCount(counts, 'server'));

        setText('dashboard-ai-priority', policyText);
        setText('dashboard-ai-provider', `${localModel.cloud_provider || '--'} · ${localModel.compare_with_local ? 'compare on' : 'compare off'}`);
        setText('dashboard-ai-cloud', localModel.cloud_model || '--');
        setText('dashboard-ai-cloud-note', localModel.cloud_enabled ? '云端模型在线策略启用' : '云端未启用');
        setText('dashboard-ai-local', localModel.model || '--');
        setText('dashboard-ai-local-note', `${localModel.name || '本地模型'} · ctx ${localModel.max_model_len || '--'}`);
        setText('dashboard-ai-feishu', localModel.feishu_control_enabled ? '可执行控制' : '只查询记录');
        setText('dashboard-ai-feishu-note', localModel.record_process_enabled ? '处理过程记录已开启' : '处理记录关闭');

        setClass('dashboard-hero-alerts', (error + offline) > 0 ? 'danger' : (stale > 0 ? 'warn' : ''));
        setClass('dashboard-hero-proxy', proxyOnline ? 'ok' : 'danger');
    }

    function renderDomainMatrix(payload, derived = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const domainLabels = {
            power: '强电柜',
            light: '灯光',
            projector: '投影',
            screen: '幕布',
            hvac: '空调',
            sequencer: '时序电源',
            ups: 'UPS',
            snmp: '网络/SNMP',
            server: '服务器',
            door: '门禁',
            automation: '自动化',
        };
        Object.entries(domainLabels).forEach(([key, label]) => {
            const count = getCount(counts, key);
            let note = '';
            if (key === 'automation') note = `启用 ${count.enabled ?? count.online ?? 0} · 异常 ${count.error ?? 0}`;
            else note = countTotal(count) ? `异常 ${countProblem(count)} · 在线率 ${ratioText(count)}` : `${label} 未配置或无快照`;
            setDomainTile(key, label, count, note);
        });
        const proxyCount = getCount(counts, 'proxy');
        setDomainTile('proxy', '代理出口', proxyCount, modules.proxy?.online ? '外网探活在线' : '代理探活异常或未初始化');
        const door = modules.door || {};
        setDomainTile('door', '门禁', getCount(counts, 'door'), `${door.text || '状态未知'} · 摄像头 ${door.camera_online ?? 0}/${door.camera_total ?? 0}`);
        const aiCount = { total: 2, online: (modules.local_model?.enabled ? 1 : 0) + (modules.local_model?.cloud_enabled ? 1 : 0), offline: 0, error: 0, stale: 0 };
        setDomainTile('local_model', 'AI 自然语言', aiCount, `${modules.local_model?.cloud_priority || '--'} · ${modules.local_model?.compare_with_local ? '本地对照开启' : '本地对照关闭'}`);
        const logItems = Array.isArray(modules.logs?.items) ? modules.logs.items.filter(shouldShowDashboardLog) : [];
        const logTotal = Number(modules.logs?.total ?? logItems.length);
        const logsCount = { total: Math.max(1, logTotal || logItems.length), online: logItems.length ? 1 : 0, offline: 0, error: 0, stale: 0 };
        setDomainTile('logs', '日志流', logsCount, logItems.length ? `最近 ${logItems.length} 条 · ${data.cache_hit ? '缓存命中' : '实时刷新'}` : '暂无可展示事件');
        setText('dashboard-monitor-matrix-note', `严重 ${derived.snmpCritical || 0} · 警告 ${derived.snmpWarning || 0} · 缓存 ${data.cache_hit ? '命中' : '刷新'}`);
    }

    function feedRow(title, value, note = '', tone = '') {
        return `<div class="monitor-feed-row ${html(tone)}">
            <div class="monitor-feed-main"><strong>${html(title)}</strong>${note ? `<span>${html(note)}</span>` : ''}</div>
            <em>${html(value)}</em>
        </div>`;
    }

    function deviceTone(item = {}) {
        if (!item.online) return 'danger';
        const level = String(item.status_level || '').toLowerCase();
        if (level === 'error' || level === 'critical') return 'danger';
        if (level === 'warning' || level === 'warn' || level === 'stale') return 'warn';
        return 'ok';
    }

    function appendDeviceRows(rows, devices, limit, formatter) {
        (Array.isArray(devices) ? devices : []).slice(0, limit).forEach(item => {
            const row = formatter(item || {});
            if (row) rows.push(row);
        });
    }

    function renderFeedLists(payload) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const env = pickEnvDevice(modules.env || {});
        const powerDevices = Array.isArray(modules.power?.devices) ? modules.power.devices : [];
        const siteRows = [
            feedRow('投影机', formatCount(getCount(counts, 'projector')), `异常 ${countProblem(getCount(counts, 'projector'))}`, toneFromCount(getCount(counts, 'projector'))),
            feedRow('幕布', formatCount(getCount(counts, 'screen')), `运动中 ${(modules.screen?.devices || []).filter(item => item.is_moving).length}`, toneFromCount(getCount(counts, 'screen'))),
            feedRow('灯光模块', formatCount(getCount(counts, 'light')), `亮灯通道 ${(modules.light?.devices || []).reduce((sum, item) => sum + Number(item.channel_on_count || 0), 0)}`, toneFromCount(getCount(counts, 'light'))),
            feedRow('空调设备', formatCount(getCount(counts, 'hvac')), `在线率 ${ratioText(getCount(counts, 'hvac'))}`, toneFromCount(getCount(counts, 'hvac'))),
        ];
        appendDeviceRows(siteRows, modules.projector?.devices, 3, item => feedRow(item.name || item.id || '投影机', item.online ? '在线' : '离线', `电源 ${item.power || '--'} · 信号 ${item.source || '--'}`, deviceTone(item)));
        appendDeviceRows(siteRows, modules.screen?.devices, 2, item => feedRow(item.name || item.id || '幕布', item.is_moving ? '运动中' : (item.online ? '在线' : '离线'), `位置 ${item.position ?? '--'} · 高度 ${item.height ?? '--'}`, deviceTone(item)));
        const facilityRows = [
            feedRow('强电柜', formatCount(getCount(counts, 'power')), `实时 ${formatMetric(powerDevices.reduce((sum, item) => sum + Number(item.realtime_power || 0), 0), ' kW')}`, toneFromCount(getCount(counts, 'power'))),
            feedRow('今日电能', `${formatMetric(powerDevices.reduce((sum, item) => sum + Number(item.daily_energy || 0), 0), ' kWh')}`, '来自强电柜轻量快照', ''),
            feedRow('环境传感器', formatCount(getCount(counts, 'env')), env ? `${env.name || env.id} · ${formatMetric(env.temp, '°C')} · ${formatMetric(env.hum, '%')}` : '等待环境数据', toneFromCount(getCount(counts, 'env'))),
            feedRow('UPS', formatCount(getCount(counts, 'ups')), `异常 ${countProblem(getCount(counts, 'ups'))}`, toneFromCount(getCount(counts, 'ups'))),
        ];
        appendDeviceRows(facilityRows, powerDevices, 4, item => feedRow(item.name || item.id || '强电柜', item.online ? '在线' : '离线', `功率 ${formatMetric(item.realtime_power, ' kW')} · 今日 ${formatMetric(item.daily_energy, ' kWh')}`, deviceTone(item)));
        appendDeviceRows(facilityRows, modules.env?.devices, 3, item => feedRow(item.name || item.id || '环境', item.online ? '在线' : '离线', `${formatMetric(item.temp, '°C')} · ${formatMetric(item.hum, '%')} · ${formatMetric(item.lux, 'Lux')}`, deviceTone(item)));
        const infraRows = [
            feedRow('SNMP 设备', formatCount(getCount(counts, 'snmp')), `告警 ${countProblem(getCount(counts, 'snmp'))}`, toneFromCount(getCount(counts, 'snmp'))),
            feedRow('服务器', formatCount(getCount(counts, 'server')), `分组 ${(modules.server?.groups || []).length}`, toneFromCount(getCount(counts, 'server'))),
            feedRow('代理出口', modules.proxy?.online ? '在线' : '异常', `${modules.proxy?.healthy_target_count || 0}/${modules.proxy?.check_count || 0} 探活`, modules.proxy?.online ? 'ok' : 'danger'),
            feedRow('时序电源', formatCount(getCount(counts, 'sequencer')), `开启通道 ${(modules.sequencer?.devices || []).reduce((sum, item) => sum + Number(item.channel_on_count || 0), 0)}`, toneFromCount(getCount(counts, 'sequencer'))),
        ];
        appendDeviceRows(infraRows, modules.snmp?.devices, 5, item => feedRow(item.name || item.id || 'SNMP', item.online ? '在线' : '离线', `评分 ${item.summary?.health_score ?? '--'} · ${item.device_type || '--'}`, deviceTone(item)));
        appendDeviceRows(infraRows, modules.sequencer?.devices, 3, item => feedRow(item.name || item.id || '时序电源', item.online ? '在线' : '离线', `通道 ${item.channel_on_count || 0}/${item.channel_count || 0}`, deviceTone(item)));
        const localModel = modules.local_model || {};
        const auto = modules.automation || {};
        const door = modules.door || {};
        const intelRows = [
            feedRow('AI 策略', localModel.cloud_priority || '--', `${localModel.cloud_enabled ? '云端启用' : '云端关闭'} · ${localModel.compare_with_local ? '本地对照' : '单路理解'}`, localModel.cloud_enabled ? 'ok' : 'warn'),
            feedRow('飞书控制', localModel.feishu_control_enabled ? '已开启' : '查询模式', localModel.feishu_require_confirmation ? '所有控制需确认' : '高风险控制需确认', localModel.feishu_control_enabled ? 'ok' : 'warn'),
            feedRow('自动化规则', `${auto.enabled || 0}/${auto.total || 0}`, `异常 ${auto.error || 0}`, Number(auto.error || 0) ? 'danger' : 'ok'),
            feedRow('门禁状态', door.text || '--', `摄像头 ${door.camera_online ?? 0}/${door.camera_total ?? 0} · ${door.engine || '--'}`, door.status_level === 'error' ? 'danger' : (door.online ? 'ok' : 'warn')),
            feedRow('本地模型', localModel.model || '--', localModel.training_export_enabled ? '训练导出开启' : '训练导出关闭', localModel.enabled ? 'ok' : 'warn'),
        ];
        appendDeviceRows(intelRows, auto.rules, 5, item => feedRow(item.name || item.id || '自动化规则', item.enabled ? '启用' : '停用', item.error || item.last_result || item.last_evaluated_at || '等待触发', item.error ? 'danger' : (item.enabled ? 'ok' : 'warn')));
        setHtml('dashboard-monitor-site-feed', siteRows.join(''));
        setHtml('dashboard-monitor-facility-feed', facilityRows.join(''));
        setHtml('dashboard-monitor-infra-feed', infraRows.join(''));
        setHtml('dashboard-monitor-intelligence-feed', intelRows.join(''));
    }

    function renderAlertList(payload, derived = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const alerts = [];
        Object.entries(counts).forEach(([key, count]) => {
            const problems = countProblem(count);
            if (!problems) return;
            const label = {
                power: '强电柜',
                light: '灯光',
                projector: '投影',
                screen: '幕布',
                hvac: '空调',
                sequencer: '时序电源',
                ups: 'UPS',
                snmp: '网络/SNMP',
                server: '服务器',
                automation: '自动化',
                proxy: '代理出口',
            }[key] || key;
            alerts.push({ label, value: problems, note: `离线 ${countOffline(count)} · 异常 ${count.error || 0} · 陈旧 ${count.stale || 0}`, tone: toneFromCount(count) });
        });
        const snmpDevices = Array.isArray(modules.snmp?.devices) ? modules.snmp.devices : [];
        snmpDevices.filter(item => {
            const risk = String(item?.summary?.risk_level || item?.status_level || '').toLowerCase();
            return risk === 'critical' || risk === 'warning' || risk === 'error';
        }).slice(0, 6).forEach(item => {
            alerts.push({
                label: item.name || item.id || 'SNMP 设备',
                value: String(item.summary?.risk_level || item.status_level || '关注'),
                note: item.last_error || `健康评分 ${item.summary?.health_score ?? '--'}`,
                tone: String(item.summary?.risk_level || '').toLowerCase() === 'critical' ? 'danger' : 'warn',
            });
        });
        setText('dashboard-monitor-alert-count', alerts.length ? `${alerts.length} 项` : '无告警');
        if (!alerts.length) {
            setHtml('dashboard-monitor-alert-list', '<div class="monitor-empty">当前未发现需要关注的异常。</div>');
            return;
        }
        setHtml('dashboard-monitor-alert-list', alerts.slice(0, 12).map(item => `<div class="monitor-alert-item ${html(item.tone)}">
            <span>${html(item.label)}</span>
            <strong>${html(item.value)}</strong>
            <em>${html(item.note)}</em>
        </div>`).join(''));
    }

    function renderNetworkAndServerLists(payload) {
        const data = normalizeDashboardSummaryPayload(payload);
        const snmpDevices = Array.isArray(data.modules?.snmp?.devices) ? data.modules.snmp.devices : [];
        const serverMachines = Array.isArray(data.modules?.server?.machines) ? data.modules.server.machines : [];
        setText('dashboard-monitor-snmp-note', snmpDevices.length ? `${snmpDevices.length} 台设备` : '无网络快照');
        setText('dashboard-monitor-server-note', serverMachines.length ? `${serverMachines.length} 台机器` : '无机器快照');
        const networkRows = snmpDevices.slice(0, 10).map(item => {
            const tone = item.online ? (String(item.summary?.risk_level || '').toLowerCase() === 'critical' ? 'danger' : (String(item.summary?.risk_level || '').toLowerCase() === 'warning' ? 'warn' : 'ok')) : 'danger';
            return feedRow(item.name || item.id || 'SNMP', item.online ? '在线' : '离线', `评分 ${item.summary?.health_score ?? '--'} · ${item.device_type || '--'}`, tone);
        });
        const serverRows = serverMachines.slice(0, 12).map(item => {
            const status = item.status || {};
            const name = item.custom_name || item.hostname || item.ip || item.mac || '机器';
            const note = `CPU ${formatMetric(status.cpu_percent, '%')} · 内存 ${formatMetric(status.mem_percent, '%')} · 磁盘 ${formatMetric(status.disk_percent, '%')}`;
            return feedRow(name, item.is_online ? '在线' : '离线', note, item.is_online ? 'ok' : 'danger');
        });
        setHtml('dashboard-monitor-network-list', networkRows.length ? networkRows.join('') : '<div class="monitor-empty">暂无网络设备快照。</div>');
        setHtml('dashboard-monitor-server-list', serverRows.length ? serverRows.join('') : '<div class="monitor-empty">暂无机器快照。</div>');
    }

    function normalizeLogOperationText(log) {
        if (typeof global.normalizeLogOperationText === 'function') {
            return global.normalizeLogOperationText(log);
        }
        const raw = String(log?.operation || log?.message || '').replace(/\[.*?\]\s*/g, '').trim();
        return raw || '暂无操作记录';
    }

    function shouldShowDashboardLog(log) {
        const op = String(log?.operation || log?.message || '').trim();
        if (!op) return false;
        if (op.includes('[Agent诊断]')) return false;
        if (/^\[proxy-monitor\]/i.test(op)) return false;
        if (op.includes('runtime_keys=') || op.includes('status_keys=')) return false;
        return true;
    }

    function renderDashboardLogsFromSummary(payload) {
        const data = normalizeDashboardSummaryPayload(payload);
        const logList = document.getElementById('dashboard-logs');
        if (!logList) return;
        const logs = Array.isArray(data.modules?.logs?.items) ? data.modules.logs.items : [];
        const visibleLogs = logs.filter(shouldShowDashboardLog).slice(0, 28);
        if (!visibleLogs.length) {
            logList.innerHTML = '<div class="monitor-empty">暂无运行日志。</div>';
            return;
        }
        logList.innerHTML = visibleLogs.map(log => {
            const timeText = formatTimeShort(log.time);
            const message = html(normalizeLogOperationText(log));
            return `<div class="log-item"><span class="time">[${html(timeText)}]</span><span class="msg">${message}</span></div>`;
        }).join('');
        logList.scrollTop = 0;
    }

    function renderDashboardEnergySummary(payload) {
        const data = normalizeDashboardSummaryPayload(payload);
        const modules = data.modules || {};
        const energy = modules.energy || {};
        const powerDevices = Array.isArray(modules.power?.devices) ? modules.power.devices : [];
        const rows = Array.isArray(energy.top_consumers) && energy.top_consumers.length
            ? energy.top_consumers
            : powerDevices.slice().sort((left, right) => Number(right.daily_energy || 0) - Number(left.daily_energy || 0)).slice(0, 6);
        const totalPower = Number(energy.realtime_power ?? powerDevices.reduce((sum, item) => sum + Number(item.realtime_power || 0), 0));
        const totalDaily = Number(energy.daily_energy ?? powerDevices.reduce((sum, item) => sum + Number(item.daily_energy || 0), 0));
        const totalMonthly = Number(energy.monthly_energy ?? powerDevices.reduce((sum, item) => sum + Number(item.monthly_energy || 0), 0));
        const online = Number(energy.online ?? powerDevices.filter(item => item && item.online).length);
        const total = Number(energy.total ?? powerDevices.length);
        setText('dashboard-energy-total', `${Number.isFinite(totalDaily) ? totalDaily.toFixed(1) : '--'} kWh`);
        setText('dashboard-energy-power', `${Number.isFinite(totalPower) ? totalPower.toFixed(2) : '--'} kW`);
        setText('dashboard-energy-monthly', `${Number.isFinite(totalMonthly) ? totalMonthly.toFixed(1) : '--'} kWh`);
        setText('dashboard-energy-compare', total ? `在线 ${online}/${total} · 只读快照` : '暂无电力快照');
        setText('dashboard-energy-source', energy.source === 'meter_center' ? '电表中心完整口径' : '强电柜轻量快照');
        if (!rows.length) {
            setHtml('dashboard-energy-list', '<div class="monitor-empty">暂无电能消耗数据。</div>');
            return;
        }
        setHtml('dashboard-energy-list', rows.map(item => {
            const daily = Number(item.daily_energy || 0);
            const power = Number(item.realtime_power || 0);
            const tone = item.online ? 'ok' : 'danger';
            return `<div class="dashboard-energy-row ${tone}">
                <div class="dashboard-energy-row-main">
                    <strong>${html(item.name || item.id || '电力回路')}</strong>
                    <span>${item.online ? '在线' : '离线'} · 今日 ${Number.isFinite(daily) ? daily.toFixed(1) : '--'} kWh</span>
                </div>
                <em>${Number.isFinite(power) ? power.toFixed(2) : '--'} kW</em>
            </div>`;
        }).join(''));
    }

    function renderDashboardFooterStatus(payload = {}, derived = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const aggregate = aggregateCounts(data.counts || {});
        const critical = Number(derived.snmpCritical || 0) + Number(data.counts?.automation?.error || 0);
        const warning = Number(derived.snmpWarning || 0);
        const offline = Math.max(0, aggregate.offline);
        const stability = aggregate.total > 0 ? `${Math.max(0, Math.min(99.9, (aggregate.online / aggregate.total) * 100)).toFixed(1)}%` : '--';
        setText('dashboard-footer-critical', String(critical + warning));
        setText('dashboard-footer-warning', String(warning));
        setText('dashboard-footer-offline', String(offline));
        setText('dashboard-footer-stability', stability);
    }

    function renderDashboardSummaryTopStats(payload, context = {}) {
        const data = normalizeDashboardSummaryPayload(payload);
        const counts = data.counts || {};
        const modules = data.modules || {};
        const power = getCount(counts, 'power');
        const light = getCount(counts, 'light');
        const sequencer = getCount(counts, 'sequencer');
        const server = getCount(counts, 'server');
        const snmp = getCount(counts, 'snmp');
        const projector = getCount(counts, 'projector');
        const screen = getCount(counts, 'screen');
        const networkDevices = Array.isArray(modules.snmp?.devices) ? modules.snmp.devices : [];
        const powerDevices = Array.isArray(modules.power?.devices) ? modules.power.devices : [];

        setText('dash-power-online', String(power.online ?? 0));
        setText('dash-light-online', String(light.online ?? 0));
        setText('dash-projector-online', String(projector.online ?? 0));
        setText('dash-projector-total', String(projector.total ?? 0));
        setText('dash-screen-online', String(screen.online ?? 0));
        setText('dash-screen-total', String(screen.total ?? 0));
        setText('dash-hvac-online', String(counts.hvac?.online ?? 0));
        setText('dash-sequencer-online', String(sequencer.online ?? 0));
        setText('dash-sequencer-total', String(sequencer.total ?? 0));
        setText('dash-server-online', String(server.online ?? 0));
        setText('dash-server-total', String(server.total ?? 0));

        const dashboardDailyEnergy = powerDevices.reduce((sum, item) => {
            const value = Number(item && item.daily_energy);
            return sum + (Number.isFinite(value) ? value : 0);
        }, 0);
        if (dashboardDailyEnergy > 0) {
            setText('dash-total-daily-energy', dashboardDailyEnergy.toFixed(1));
            const dailyMeta = document.getElementById('dash-total-daily-meta');
            if (dailyMeta && !window.SmartCenter?.powerMeterRuntime?.meterCenterCache) {
                dailyMeta.innerHTML = '单位 kWh · 首页轻量快照，电表模块加载后刷新完整口径';
            }
        }

        const snmpCritical = networkDevices.filter(item => {
            const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
            return risk === 'critical' || risk === 'error';
        }).length;
        const snmpWarning = networkDevices.filter(item => {
            const risk = String((item?.summary || {}).risk_level || item?.status_level || '').toLowerCase();
            return risk === 'warning' || risk === 'stale';
        }).length;
        setText('dash-snmp-online', String(snmp.online || 0));
        setText('dash-snmp-total', String(snmp.total || 0));
        setText('dash-snmp-critical', String(snmpCritical));
        setText('dash-snmp-warning', String(snmpWarning));
        setText('dash-snmp-alert', String(snmpCritical + snmpWarning));
        setText('dash-auto-total', String(counts.automation?.total || 0));
        setText('dash-auto-enabled', String(counts.automation?.enabled ?? counts.automation?.online ?? 0));
        setText('dash-auto-errors', String(counts.automation?.error || 0));
        const door = modules.door || {};
        setText('dash-door-status', door.text || '--');
        const doorStatusEl = document.getElementById('dash-door-status');
        if (doorStatusEl) {
            const status = String(door.status || '').toLowerCase();
            const className = status === 'open' ? 'danger' : (status === 'closed' ? 'green' : (door.online ? 'blue' : 'danger'));
            doorStatusEl.className = `value ${className}`;
            doorStatusEl.title = `${door.engine || '--'} · 摄像头 ${door.camera_online ?? 0}/${door.camera_total ?? 0}`;
        }

        const renderProxy = typeof context.renderDashboardProxySummary === 'function'
            ? context.renderDashboardProxySummary
            : global.renderDashboardProxySummary;
        if (typeof renderProxy === 'function') renderProxy(modules.proxy || {});

        const derived = { snmpCritical, snmpWarning, snmpOnline: snmp.online || 0, snmpTotal: snmp.total || 0 };
        renderDashboardEnvSummary(modules.env || {}, context);
        renderDashboardHero(data, derived, context);
        renderDomainMatrix(data, derived);
        renderFeedLists(data);
        renderAlertList(data, derived);
        renderNetworkAndServerLists(data);
        renderDashboardLogsFromSummary(data);
        renderDashboardEnergySummary(data);
        renderDashboardFooterStatus(data, derived);
    }

    const api = {
        normalizeDashboardSummaryPayload,
        renderDashboardSummaryTopStats,
        renderDashboardFooterStatus,
        renderDashboardEnvSummary,
        renderDashboardHero,
        renderDomainMatrix,
        renderFeedLists,
        renderAlertList,
        renderNetworkAndServerLists,
        renderDashboardLogsFromSummary,
        renderDashboardEnergySummary,
    };

    SmartCenter.dashboardSummary = Object.assign({}, SmartCenter.dashboardSummary || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('dashboard-summary', {
            kind: 'view-helper',
            view: 'dashboard',
            exports: Object.keys(api),
            source: 'static/js/views/dashboard-summary.js',
        });
    }

    Object.assign(global, api);
})(window);
