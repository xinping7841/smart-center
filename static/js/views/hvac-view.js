(function installSmartCenterHvacView(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
    const utils = SmartCenter.utils || {};
    const escapeHtml = utils.escapeHtml || global.escapeHtml || (value => String(value ?? ''));

    function getContext(context = {}) {
        const provider = typeof global.getHvacViewContext === 'function'
            ? (global.getHvacViewContext() || {})
            : {};
        return Object.assign({}, provider, context || {});
    }

    function formatHvacTemperature(value) {
        const num = Number(value);
        return Number.isFinite(num) ? `${num}°C` : '--';
    }

    function formatHvacPower(status) {
        const watt = Number(status?.electric_power_w);
        if (Number.isFinite(watt)) {
            if (Math.abs(watt) >= 1000) return `${(watt / 1000).toFixed(2)} kW`;
            return `${watt.toFixed(watt >= 100 ? 0 : 2)} W`;
        }
        const kw = Number(status?.electric_power_kw);
        if (Number.isFinite(kw)) return `${kw.toFixed(3)} kW`;
        return '--';
    }

    function getHvacModeText(mode) {
        const map = {
            off: '关闭',
            cool: '制冷',
            heat: '制热',
            dry: '除湿',
            fan_only: '送风',
            auto: '自动',
            heat_cool: '自动冷热',
        };
        const key = String(mode || '').trim().toLowerCase();
        return map[key] || (mode ? String(mode) : '--');
    }

    function getHvacActionText(action) {
        const map = {
            cooling: '制冷中',
            heating: '制热中',
            drying: '除湿中',
            fan: '送风中',
            idle: '待机',
            off: '已关闭',
        };
        const key = String(action || '').trim().toLowerCase();
        return map[key] || (action ? String(action) : '--');
    }

    function getHvacModeClass(mode) {
        const key = String(mode || '').trim().toLowerCase();
        if (key === 'cool') return 'cool';
        if (key === 'heat') return 'heat';
        if (key === 'dry') return 'dry';
        if (key === 'fan_only' || key === 'fan') return 'fan';
        if (key === 'auto' || key === 'heat_cool') return 'auto';
        if (key === 'off') return 'off';
        return '';
    }

    function getHvacCardStateClass(status) {
        if (!status?.online) return 'offline';
        return status?.power ? 'running' : 'standby';
    }

    function getHvacActionClass(status) {
        if (!status?.online) return 'idle';
        const action = String(status?.hvac_action || '').trim().toLowerCase();
        if (action === 'cooling') return 'cooling';
        if (action === 'heating') return 'heating';
        if (status?.power) return 'running';
        return 'idle';
    }

    function getHvacPowerButtonClass(status) {
        if (!status?.online) return 'unknown';
        return status?.power ? 'on' : 'off';
    }

    function getHvacModeIcon(kind) {
        const key = String(kind || '').trim().toLowerCase();
        if (key === 'cool') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 2.8v18.4M5.2 6.2l13.6 11.6M18.8 6.2L5.2 17.8" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
                <path d="M12 2.8l2 3.1M12 2.8l-2 3.1M12 21.2l2-3.1M12 21.2l-2-3.1M5.2 6.2l3.6.7M5.2 6.2l.9 3.4M18.8 6.2l-3.6.7M18.8 6.2l-.9 3.4M5.2 17.8l3.6-.7M5.2 17.8l.9-3.4M18.8 17.8l-3.6-.7M18.8 17.8l-.9-3.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>`;
        }
        if (key === 'heat') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="4.4" stroke="currentColor" stroke-width="1.9"/>
                <path d="M12 2.7v3.1M12 18.2v3.1M21.3 12h-3.1M5.8 12H2.7M18.6 5.4l-2.2 2.2M7.6 16.4l-2.2 2.2M18.6 18.6l-2.2-2.2M7.6 7.6 5.4 5.4" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
            </svg>`;
        }
        if (key === 'dry') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 3.5c2.9 3.5 4.4 5.9 4.4 8a4.4 4.4 0 1 1-8.8 0c0-2.1 1.5-4.5 4.4-8Z" stroke="currentColor" stroke-width="1.9"/>
            </svg>`;
        }
        if (key === 'fan') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="2.2" stroke="currentColor" stroke-width="1.8"/>
                <path d="M12.1 4.6c2.1 0 3.6 2.4 2.1 4.3-.9 1.2-2.9 1.1-4 .2-1.4-1.2-.5-4.5 1.9-4.5ZM19 12.1c0 2.1-2.4 3.6-4.3 2.1-1.2-.9-1.1-2.9-.2-4 1.2-1.4 4.5-.5 4.5 1.9ZM11.9 19.4c-2.1 0-3.6-2.4-2.1-4.3.9-1.2 2.9-1.1 4-.2 1.4 1.2.5 4.5-1.9 4.5ZM5 11.9c0-2.1 2.4-3.6 4.3-2.1 1.2.9 1.1 2.9.2 4-1.2 1.4-4.5.5-4.5-1.9Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>`;
        }
        if (key === 'auto') {
            return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M8.4 7.1A5.8 5.8 0 1 1 5.7 12H3.2l2.6-2.8L8.4 12H6.9A4.3 4.3 0 1 0 8.9 8.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;
        }
        return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 4.2v7.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
            <path d="M7.4 6.5A8 8 0 1 0 16.6 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
        </svg>`;
    }

    function getHvacFanLevel(fanSpeed) {
        const text = String(fanSpeed || '').trim().toLowerCase();
        if (!text || text === '--' || text === 'unknown') return 0;
        if (text.includes('低') || text.includes('low')) return 1;
        if (text.includes('中') || text.includes('medium') || text.includes('mid')) return 2;
        if (text.includes('高') || text.includes('high') || text.includes('turbo') || text.includes('strong')) return 4;
        if (text.includes('自动') || text.includes('auto')) return 3;
        return 2;
    }

    function renderHvacFanStatus(fanSpeed) {
        const label = escapeHtml(fanSpeed || '--');
        const level = getHvacFanLevel(fanSpeed);
        const bars = [1, 2, 3, 4].map(idx => `<span class="hvac-fan-bar${idx <= level ? ' active' : ''}"></span>`).join('');
        return `<div class="hvac-fan-wrap">
            <div class="hvac-fan-label">${label}</div>
            <div class="hvac-fan-bars">${bars}</div>
        </div>`;
    }

    function renderHvacFanInline(fanSpeed) {
        const label = escapeHtml(fanSpeed || '--');
        const level = getHvacFanLevel(fanSpeed);
        const bars = [1, 2, 3, 4].map(idx => `<span class="hvac-fan-bar${idx <= level ? ' active' : ''}"></span>`).join('');
        return `<div class="hvac-fan-inline">
            <span class="hvac-fan-inline-label">${label}</span>
            <span class="hvac-fan-inline-bars">${bars}</span>
        </div>`;
    }

    function getHvacControlId(value, scope = '') {
        const prefix = scope ? `${scope}-` : '';
        return `${prefix}${String(value || '').replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    }

    function toHvacNumber(value, fallback = null) {
        const num = Number(value);
        return Number.isFinite(num) ? num : fallback;
    }

    function getHvacSupportedModes(status = {}) {
        const rawModes = Array.isArray(status?.hvac_modes) ? status.hvac_modes : [];
        const normalized = rawModes.map(item => String(item || '').trim().toLowerCase()).filter(Boolean);
        const modes = normalized.length ? normalized : ['off', 'cool', 'heat'];
        return modes
            .filter((mode, index, list) => list.indexOf(mode) === index)
            .filter(mode => ['off', 'cool', 'heat', 'dry', 'fan_only', 'fan', 'auto', 'heat_cool'].includes(mode));
    }

    function renderHvacModeOptions(deviceId, status = {}) {
        const currentMode = String(status?.mode || 'off').trim().toLowerCase();
        const safeDeviceId = escapeHtml(deviceId);
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('hvac.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限') : '';
        return getHvacSupportedModes(status).map(mode => {
            const modeClass = getHvacModeClass(mode) || 'off';
            const modeText = escapeHtml(getHvacModeText(mode));
            const isActive = mode === currentMode || getHvacModeClass(mode) === getHvacModeClass(currentMode);
            return `<button type="button" class="hvac-mode-option ${modeClass}${isActive ? ' active' : ''}${disabledClass}" ${disabledAttrs} onclick="event.stopPropagation(); selectHvacMode('${safeDeviceId}', '${escapeHtml(mode)}')">
                ${getHvacModeIcon(modeClass)}
                <span>${modeText}</span>
            </button>`;
        }).join('');
    }

    function getHvacTempBounds(status = {}) {
        return {
            min: toHvacNumber(status?.min_temp, 16),
            max: toHvacNumber(status?.max_temp, 30),
            step: toHvacNumber(status?.target_temp_step, 1) || 1,
        };
    }

    function getHvacAgeText(status) {
        const ageSec = Number(status?.age_sec);
        if (!Number.isFinite(ageSec)) return '--';
        if (ageSec < 60) return `${Math.round(ageSec)} 秒前`;
        if (ageSec < 3600) return `${Math.round(ageSec / 60)} 分钟前`;
        return `${(ageSec / 3600).toFixed(1)} 小时前`;
    }

    function formatCompactAgeFromSec(ageSec) {
        const value = Number(ageSec);
        if (!Number.isFinite(value)) return '';
        if (value < 60) return `${Math.round(value)}秒前`;
        if (value < 3600) return `${Math.round(value / 60)}分钟前`;
        if (value < 86400) return `${Math.round(value / 3600)}小时前`;
        return `${Math.round(value / 86400)}天前`;
    }

    function getHvacRoomName(cfg) {
        const text = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
        if (text) return text;
        const source = `${cfg?.name || ''} ${cfg?.id || ''}`.toLowerCase();
        if (/一号厅|1号厅|hall1|a1|a2|沉浸|b厅/.test(source)) return '一号厅';
        if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
        if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
        if (/机房|shenlan|machine|server/.test(source)) return '主机房';
        if (/咖啡|cafe/.test(source)) return '咖啡厅';
        if (/办公室|office/.test(source)) return '办公室二楼';
        return '未分区';
    }

    function getHvacSortOrder(cfg) {
        const value = Number(cfg?.sort_order);
        if (Number.isFinite(value)) return value;
        const match = String(cfg?.name || '').match(/(\d+)/);
        return match ? Number(match[1]) : 999;
    }

    function getHvacRoomSort(roomName) {
        const text = String(roomName || '').trim();
        const priority = {
            '机房': 1,
            '主机房': 1,
            '一号厅': 2,
            '二号厅': 3,
            '办公室': 4,
            '办公室二楼': 4,
            '办公室二楼会议室': 5,
            '咖啡厅': 6,
            '庭院': 7,
        };
        return Number.isFinite(priority[text]) ? priority[text] : 99;
    }

    function getHvacGroupClass(roomName) {
        const text = String(roomName || '').trim();
        if (text === '机房' || text === '主机房') return 'hvac-group-machine';
        if (text.includes('一号厅')) return 'hvac-group-hall1';
        if (text.includes('二号厅')) return 'hvac-group-hall2';
        if (text.includes('咖啡')) return 'hvac-group-cafe';
        if (text.includes('会议室')) return 'hvac-group-meeting';
        if (text.includes('办公室')) return 'hvac-group-office';
        return 'hvac-group-misc';
    }

    function getHvacGroupAccent(roomName) {
        const text = String(roomName || '').trim();
        if (text === '机房' || text === '主机房') return { accent: '#22c55e', border: 'rgba(34,197,94,0.46)', glow: 'rgba(34,197,94,0.14)' };
        if (text.includes('一号厅')) return { accent: '#38bdf8', border: 'rgba(56,189,248,0.48)', glow: 'rgba(56,189,248,0.16)' };
        if (text.includes('二号厅')) return { accent: '#818cf8', border: 'rgba(129,140,248,0.50)', glow: 'rgba(129,140,248,0.16)' };
        if (text.includes('咖啡')) return { accent: '#fb923c', border: 'rgba(251,146,60,0.48)', glow: 'rgba(251,146,60,0.15)' };
        if (text.includes('会议室')) return { accent: '#a855f7', border: 'rgba(168,85,247,0.50)', glow: 'rgba(168,85,247,0.15)' };
        if (text.includes('办公室')) return { accent: '#0ea5e9', border: 'rgba(14,165,233,0.46)', glow: 'rgba(14,165,233,0.15)' };
        return { accent: '#64748b', border: 'rgba(100,116,139,0.42)', glow: 'rgba(100,116,139,0.12)' };
    }

    function normalizeHvacEnvRoomName(value) {
        const text = String(value || '').trim();
        const source = text.toLowerCase();
        if (!text) return '';
        if (/机房|深澜|server|machine/.test(source)) return '主机房';
        if (/一号厅|1号厅|hall1|沉浸/.test(source)) return '一号厅';
        if (/二号厅|2号厅|hall2/.test(source)) return '二号厅';
        if (/会议室|meeting/.test(source)) return '办公室二楼会议室';
        if (/二楼办公室|办公室二楼|office|办公室/.test(source)) return '办公室二楼';
        if (/咖啡|cafe/.test(source)) return '咖啡厅';
        return text;
    }

    function getEnvSensorRoomName(cfg) {
        const explicit = String(cfg?.room_name || cfg?.area_name || cfg?.zone || cfg?.group_name || cfg?.room || cfg?.area || '').trim();
        if (explicit) return normalizeHvacEnvRoomName(explicit);
        return normalizeHvacEnvRoomName(`${cfg?.name || ''} ${cfg?.id || ''}`);
    }

    function getEnvThermalAgeSec(st) {
        const ages = [Number(st?.temp_age_sec), Number(st?.hum_age_sec), Number(st?.age_sec)]
            .filter(value => Number.isFinite(value));
        return ages.length ? Math.min(...ages) : null;
    }

    function envSensorHasThermalValue(st) {
        return Number.isFinite(Number(st?.temp)) || Number.isFinite(Number(st?.hum));
    }

    function findRoomEnvSensors(roomName, limit = 2) {
        const data = global.__envStatusCache || {};
        const targetRoom = normalizeHvacEnvRoomName(roomName);
        if (!targetRoom) return [];
        const envConfigList = Array.isArray(global.__envConfigsCache) ? global.__envConfigsCache : [];
        return envConfigList
            .map(cfg => {
                const st = data[cfg.id] || {};
                const sensorRoom = getEnvSensorRoomName(cfg);
                const roomMatched = sensorRoom === targetRoom;
                const text = `${cfg?.id || ''} ${cfg?.name || ''}`.toLowerCase();
                const isContactOnly = typeof global.isContactLikeEnvSensor === 'function'
                    ? global.isContactLikeEnvSensor(cfg) && !envSensorHasThermalValue(st)
                    : false;
                const hasThermal = envSensorHasThermalValue(st);
                if (!roomMatched || isContactOnly || !hasThermal) return null;
                const ageSec = getEnvThermalAgeSec(st);
                const statusLevel = String(st?.status_level || (st?.online ? 'online' : (st?.stale ? 'stale' : 'offline'))).toLowerCase();
                const score = (st?.online ? 1000 : 0)
                    + (statusLevel === 'stale' ? 120 : 0)
                    + (Number.isFinite(ageSec) ? Math.max(0, 7200 - Math.min(ageSec, 7200)) / 10 : 0)
                    + (text.includes(targetRoom.toLowerCase()) ? 30 : 0);
                return { cfg, st, ageSec, statusLevel, score };
            })
            .filter(Boolean)
            .sort((left, right) => right.score - left.score)
            .slice(0, limit);
    }

    function renderHvacRoomEnvChips(roomName, options = {}) {
        const sensors = findRoomEnvSensors(roomName, options.limit || 2);
        if (!sensors.length) return '';
        return sensors.map(item => {
            const st = item.st || {};
            const temp = Number(st.temp);
            const hum = Number(st.hum);
            if (!Number.isFinite(temp) && !Number.isFinite(hum)) return '';
            const tempText = Number.isFinite(temp) ? `${temp.toFixed(temp % 1 === 0 ? 0 : 1)}°C` : '--°C';
            const humText = Number.isFinite(hum) ? `${hum.toFixed(hum % 1 === 0 ? 0 : 1)}%` : '--%';
            const level = String(item.statusLevel || '').toLowerCase();
            const chipClass = level === 'stale' ? 'stale' : (st.online ? 'online' : 'offline');
            const ageText = formatCompactAgeFromSec(item.ageSec);
            const title = `${item.cfg?.name || roomName || '空间温湿度'}${ageText ? ` / ${ageText}` : ''}`;
            const label = options.compact ? '室内' : '温湿';
            return `<span class="hvac-room-env-chip ${escapeHtml(chipClass)}" title="${escapeHtml(title)}"><span class="label">${escapeHtml(label)}</span><strong>${escapeHtml(tempText)}</strong><span>/ ${escapeHtml(humText)}</span>${ageText && chipClass !== 'online' ? `<em>${escapeHtml(ageText)}</em>` : ''}</span>`;
        }).filter(Boolean).join('');
    }

    function renderMachineRoomEnvChip() {
        const sensors = findRoomEnvSensors('主机房', 1);
        const st = sensors[0]?.st;
        if (!st) return '';
        const temp = Number(st.temp);
        const hum = Number(st.hum);
        if (!Number.isFinite(temp) && !Number.isFinite(hum)) return '';
        const tempText = Number.isFinite(temp) ? `${temp.toFixed(1)}°C` : '--°C';
        const humText = Number.isFinite(hum) ? `${hum.toFixed(hum % 1 === 0 ? 0 : 1)}%` : '--%';
        return `<span class="hvac-room-env-chip"><span class="label">温湿</span><strong>${escapeHtml(tempText)}</strong><span>/ ${escapeHtml(humText)}</span></span>`;
    }

    function buildHvacGroups(configs, statusMap = {}) {
        const groupsMap = new Map();
        (Array.isArray(configs) ? configs : []).forEach(cfg => {
            if (!cfg || cfg.visible === false) return;
            const roomName = getHvacRoomName(cfg);
            if (!groupsMap.has(roomName)) groupsMap.set(roomName, []);
            groupsMap.get(roomName).push(cfg);
        });
        return Array.from(groupsMap.entries())
            .map(([roomName, items]) => {
                const sortedItems = items.slice().sort((left, right) => {
                    const orderDiff = getHvacSortOrder(left) - getHvacSortOrder(right);
                    if (orderDiff !== 0) return orderDiff;
                    return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN');
                });
                const stats = sortedItems.reduce((acc, cfg) => {
                    const st = statusMap[cfg.id] || {};
                    acc.total += 1;
                    if (st.online) acc.online += 1;
                    if (st.power) acc.running += 1;
                    const watt = Number(st.electric_power_w);
                    if (Number.isFinite(watt)) acc.powerW += watt;
                    return acc;
                }, { total: 0, online: 0, running: 0, powerW: 0 });
                return { roomName, items: sortedItems, stats };
            })
            .sort((left, right) => {
                const roomDiff = getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName);
                if (roomDiff !== 0) return roomDiff;
                return String(left.roomName || '').localeCompare(String(right.roomName || ''), 'zh-CN');
            });
    }

    function renderHvacGroup(group, scope = 'page', context = {}) {
        const ctx = getContext(context);
        const statusMap = ctx.statusMap || {};
        const roomTitle = escapeHtml(group?.roomName || '未分区');
        const stats = group?.stats || { total: 0, online: 0, running: 0, powerW: 0 };
        const totalText = `${Number(stats.total || 0)} 台`;
        const onlineText = `${Number(stats.online || 0)} 在线`;
        const runningText = `${Number(stats.running || 0)} 运行`;
        const powerText = Number.isFinite(Number(stats.powerW))
            ? (Math.abs(Number(stats.powerW)) >= 1000 ? `${(Number(stats.powerW) / 1000).toFixed(2)} kW` : `${Number(stats.powerW).toFixed(Number(stats.powerW) >= 100 ? 0 : 2)} W`)
            : '--';
        const cardsHtml = (group?.items || []).map(cfg => renderHvacCard(cfg, statusMap[cfg.id] || {}, scope, ctx)).join('');
        const actualGroupItemCount = Math.max(1, (group?.items || []).length);
        const groupItemCount = Math.max(1, Math.min(actualGroupItemCount, 4));
        const rawGroupClass = getHvacGroupClass(group?.roomName);
        const groupClass = escapeHtml(rawGroupClass);
        const accent = getHvacGroupAccent(group?.roomName);
        const groupStyle = [
            `--hvac-room-accent:${accent.accent}`,
            `border:2px solid ${accent.border}`,
            `background:linear-gradient(180deg, ${accent.glow}, rgba(10,20,34,0.98) 34%, rgba(8,16,29,0.98))`,
            `box-shadow:0 12px 30px rgba(2,6,23,0.28), inset 0 1px 0 rgba(255,255,255,0.07)`,
            `border-radius:18px`,
            `padding:10px`,
            `margin:0 0 10px`,
            `position:relative`,
            `overflow:hidden`,
        ].join(';');
        const headStyle = [
            `border-bottom:1px solid rgba(148,163,184,0.18)`,
            `padding:0 2px 7px 9px`,
            `margin:0 0 8px`,
            `box-shadow:inset 4px 0 0 ${accent.accent}`,
            `border-radius:10px`,
        ].join(';');
        const roomEnvChipHtml = renderHvacRoomEnvChips(group?.roomName);
        const roomEnvSlot = `<span class="hvac-room-env-slot${roomEnvChipHtml ? '' : ' is-empty'}" data-hvac-room-env="${escapeHtml(group?.roomName || '')}">${roomEnvChipHtml}</span>`;
        return `<div class="hvac-group-section ${groupClass} hvac-group-count-${groupItemCount}" data-hvac-count="${groupItemCount}" style="${groupStyle}">
            <div class="hvac-group-head" style="${headStyle}">
                <div class="hvac-group-title-wrap">
                    <div class="hvac-group-title-row">
                        <div class="hvac-group-title" style="font-size:16px;color:#f8fafc;">${roomTitle}</div>
                        ${roomEnvSlot}
                    </div>
                    <div class="hvac-group-subtitle">按区域汇总空调运行状态与快捷控制</div>
                </div>
                <div class="hvac-group-stats">
                    <span class="hvac-group-stat">${escapeHtml(totalText)}</span>
                    <span class="hvac-group-stat online">${escapeHtml(onlineText)}</span>
                    <span class="hvac-group-stat running">${escapeHtml(runningText)}</span>
                    <span class="hvac-group-stat power">${escapeHtml(powerText)}</span>
                </div>
            </div>
            <div class="hvac-group-grid">${cardsHtml}</div>
        </div>`;
    }

    function isDashboardHvacAttention(status = {}) {
        const errorText = String(status?.error || status?.last_error || '').trim();
        const action = String(status?.hvac_action || '').trim().toLowerCase();
        return !status?.online || !!status?.power || !!errorText || ['cooling', 'heating', 'drying', 'fan'].includes(action);
    }

    function getDashboardHvacAttentionRank(item) {
        const st = item?.status || {};
        if (!st.online) return 0;
        if (st.error || st.last_error) return 1;
        if (st.power) return 2;
        return 9;
    }

    function getDashboardHvacTotals(groups = [], context = {}) {
        const statusMap = getContext(context).statusMap || {};
        return groups.reduce((acc, group) => {
            const stats = group?.stats || {};
            acc.total += Number(stats.total || 0);
            acc.online += Number(stats.online || 0);
            acc.running += Number(stats.running || 0);
            acc.powerW += Number(stats.powerW || 0);
            (group?.items || []).forEach(cfg => {
                const st = statusMap[cfg.id] || {};
                if (!st.online) acc.offline += 1;
                if (st.error || st.last_error) acc.error += 1;
            });
            return acc;
        }, { total: 0, online: 0, running: 0, offline: 0, error: 0, powerW: 0 });
    }

    function formatHvacDashboardPower(watt) {
        const value = Number(watt);
        if (!Number.isFinite(value)) return '--';
        if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
        return `${value.toFixed(value >= 100 ? 0 : 1)} W`;
    }

    function renderDashboardHvacMetric(label, value, tone = '') {
        return `<div class="dashboard-hvac-metric ${escapeHtml(tone)}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>`;
    }

    function getHvacStateSummary(status) {
        const online = !!status?.online;
        const powerOn = !!status?.power;
        const modeText = getHvacModeText(status?.mode);
        const actionText = getHvacActionText(status?.hvac_action);
        return {
            onlineText: online ? '在线' : '离线',
            powerText: powerOn ? '运行中' : '已关闭',
            stateClass: getHvacCardStateClass(status),
            modeText,
            actionText,
        };
    }

    function renderDashboardHvacAttentionCard(item) {
        const merged = Object.assign({}, item?.cfg || {}, item?.status || {});
        const state = getHvacStateSummary(merged);
        const modeClass = getHvacModeClass(merged.mode) || getHvacActionClass(merged);
        const title = escapeHtml(merged.name || merged.id || '未命名空调');
        const roomName = getHvacRoomName(merged);
        const targetText = formatHvacTemperature(merged.target_temp);
        const actionText = merged.power
            ? (state.actionText !== '--' ? state.actionText : state.modeText)
            : state.powerText;
        const powerText = formatHvacPower(merged);
        const ageText = getHvacAgeText(merged);
        const noteParts = [
            roomName,
            ageText && ageText !== '--' ? ageText : '',
            powerText && powerText !== '--' ? powerText : '',
        ].filter(Boolean);
        const deviceId = String(merged.id || '');
        const safeDeviceId = escapeHtml(deviceId);
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('hvac.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限') : '';
        const iconHtml = typeof global.getProjectorIconHtml === 'function' ? global.getProjectorIconHtml('power') : '电源';
        return `<div class="dashboard-hvac-device-mini ${state.stateClass}${modeClass ? ` mode-${modeClass}` : ''}">
            <div class="dashboard-hvac-device-main">
                <div class="dashboard-hvac-device-title">${title}</div>
                <div class="dashboard-hvac-device-meta">${escapeHtml(noteParts.join(' · '))}</div>
            </div>
            <div class="dashboard-hvac-device-state">
                <span class="dashboard-hvac-pill ${merged.online ? 'online' : 'offline'}">${escapeHtml(state.onlineText)}</span>
                <strong>${escapeHtml(targetText)}</strong>
                <span>${escapeHtml(actionText)}</span>
            </div>
            <button class="dashboard-hvac-power ${getHvacPowerButtonClass(merged)}${disabledClass}" ${disabledAttrs} title="${escapeHtml(merged.power ? '当前开机，点击关机' : '当前关机，点击开机')}" onclick="event.stopPropagation(); controlHvac('${safeDeviceId}', '${merged.power ? 'power_off' : 'power_on'}')">${iconHtml}</button>
        </div>`;
    }

    function renderDashboardHvacRoomTile(group) {
        const stats = group?.stats || {};
        const roomName = group?.roomName || '未分区';
        const accent = getHvacGroupAccent(roomName);
        const offline = Math.max(0, Number(stats.total || 0) - Number(stats.online || 0));
        const roomEnvChipHtml = renderHvacRoomEnvChips(roomName, { compact: true, limit: 1 });
        const loadText = Number(stats.running || 0) > 0
            ? `${Number(stats.running || 0)} 运行`
            : `${Math.max(0, Number(stats.total || 0) - Number(stats.running || 0))} 已关`;
        return `<div class="dashboard-hvac-room-tile ${escapeHtml(getHvacGroupClass(roomName))}" style="--hvac-room-accent:${accent.accent};">
            <div class="dashboard-hvac-room-head">
                <strong>${escapeHtml(roomName)}</strong>
                <span>${escapeHtml(loadText)}</span>
            </div>
            <div class="dashboard-hvac-room-line">
                <span>${escapeHtml(`${Number(stats.online || 0)}/${Number(stats.total || 0)} 在线`)}</span>
                <span class="${offline ? 'warn' : ''}">${escapeHtml(offline ? `${offline} 离线` : '正常')}</span>
                <span>${escapeHtml(formatHvacDashboardPower(stats.powerW))}</span>
            </div>
            <div class="dashboard-hvac-room-env${roomEnvChipHtml ? '' : ' is-empty'}" data-hvac-room-env="${escapeHtml(roomName)}">${roomEnvChipHtml}</div>
        </div>`;
    }

    function renderDashboardHvacOverview(groups = [], context = {}) {
        const ctx = getContext(context);
        const statusMap = ctx.statusMap || {};
        if (!groups.length) return '<div class="hvac-empty">未配置空调设备</div>';
        const totals = getDashboardHvacTotals(groups, ctx);
        const attentionItems = groups.flatMap(group => (group?.items || []).map(cfg => ({
            cfg,
            status: statusMap[cfg.id] || {},
            roomName: group.roomName,
        }))).filter(item => isDashboardHvacAttention(item.status))
            .sort((left, right) => getDashboardHvacAttentionRank(left) - getDashboardHvacAttentionRank(right)
                || getHvacRoomSort(left.roomName) - getHvacRoomSort(right.roomName)
                || getHvacSortOrder(left.cfg) - getHvacSortOrder(right.cfg));
        const visibleAttention = attentionItems.slice(0, 6);
        const moreCount = Math.max(0, attentionItems.length - visibleAttention.length);
        const attentionHtml = visibleAttention.length
            ? visibleAttention.map(renderDashboardHvacAttentionCard).join('')
            : '<div class="dashboard-hvac-quiet">全部空调处于正常关闭/待机状态</div>';
        const roomHtml = groups.map(renderDashboardHvacRoomTile).join('');
        return `<div class="dashboard-hvac-overview">
            <div class="dashboard-hvac-summary-strip">
                ${renderDashboardHvacMetric('运行', String(totals.running), totals.running ? 'running' : '')}
                ${renderDashboardHvacMetric('离线', String(totals.offline), totals.offline ? 'offline' : '')}
                ${renderDashboardHvacMetric('在线', `${totals.online}/${totals.total}`, 'online')}
                ${renderDashboardHvacMetric('当前功率', formatHvacDashboardPower(totals.powerW), 'power')}
                <button class="dashboard-hvac-entry" type="button" onclick="switchTab('hvac', '空调控制', findNavElementByView('hvac'))">详情</button>
            </div>
            <div class="dashboard-hvac-priority">
                <div class="dashboard-hvac-block-title">
                    <span>需关注</span>
                    <strong>${escapeHtml(moreCount ? `+${moreCount}` : `${attentionItems.length}`)}</strong>
                </div>
                <div class="dashboard-hvac-priority-grid">${attentionHtml}</div>
            </div>
            <div class="dashboard-hvac-room-grid">${roomHtml}</div>
        </div>`;
    }

    function renderHvacCard(cfg, status = {}, scope = 'page') {
        const merged = Object.assign({}, cfg || {}, status || {});
        const isDashboardCard = scope === 'dashboard';
        const state = getHvacStateSummary(merged);
        const cardStateClass = state.stateClass || 'offline';
        const modeClass = getHvacModeClass(merged.mode);
        const actionClass = getHvacActionClass(merged);
        const deviceId = String(merged.id || '');
        const safeDeviceId = escapeHtml(deviceId);
        const controlScope = scope === 'dashboard' ? 'dash' : 'page';
        const controlId = getHvacControlId(deviceId, controlScope);
        const title = escapeHtml(merged.name || merged.id || '未命名空调');
        const subtitle = escapeHtml(`${merged.brand || 'Home Assistant'} / ${merged.model || merged.protocol || 'HVAC'}`);
        const targetText = formatHvacTemperature(merged.target_temp);
        const targetValue = targetText.replace('°C', '');
        const thermalClass = merged.power ? (modeClass || actionClass || 'off') : 'off';
        const dashboardThermalText = !merged.online
            ? '离线'
            : (merged.power
                ? (state.actionText !== '--' ? state.actionText : (state.modeText === '--' ? state.powerText : state.modeText))
                : '已关闭');
        const thermalText = isDashboardCard
            ? dashboardThermalText
            : (merged.power ? (state.modeText === '--' ? state.powerText : state.modeText) : '已关闭');
        const fanSpeedHtml = renderHvacFanInline(merged.fan_speed || '--');
        const updatedAt = merged.updated_at ? new Date(merged.updated_at).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
        const powerText = escapeHtml(formatHvacPower(merged));
        const modeText = escapeHtml(state.modeText);
        const actionText = escapeHtml(state.actionText);
        const modeIcon = getHvacModeIcon(modeClass);
        const actionIcon = getHvacModeIcon(modeClass === 'off' ? 'off' : modeClass || 'fan');
        const powerButtonClass = getHvacPowerButtonClass(merged);
        const powerButtonTitle = merged.power ? '当前开机，点击关机' : '当前关机，点击开机';
        const noteText = `最后更新 ${escapeHtml(updatedAt)} · 数据年龄 ${escapeHtml(getHvacAgeText(merged))}`;
        const cardRoomName = getHvacRoomName(merged);
        const roomEnvCompactHtml = renderHvacRoomEnvChips(cardRoomName, { compact: true, limit: 1 });
        const safeCardRoomName = escapeHtml(cardRoomName);
        const hiddenEnvStyle = roomEnvCompactHtml ? '' : ' style="display:none !important;"';
        const roomEnvRowHtml = `<div class="hvac-compact-row env${roomEnvCompactHtml ? '' : ' is-empty'}"${hiddenEnvStyle}><span class="hvac-compact-label">环境</span><strong data-hvac-card-env="${safeCardRoomName}">${roomEnvCompactHtml}</strong></div>`;
        const roomEnvInfoRowHtml = `<div class="hvac-info-row env${roomEnvCompactHtml ? '' : ' is-empty'}"${hiddenEnvStyle}><div class="label">空间温湿度</div><div class="value env" data-hvac-card-env="${safeCardRoomName}">${roomEnvCompactHtml}</div></div>`;
        const detailButton = scope === 'dashboard'
            ? `<button class="hvac-control-btn" type="button" onclick="switchTab('hvac', '空调控制', findNavElementByView('hvac'))">详情</button>`
            : '';
        const powerBadgeHtml = isDashboardCard
            ? ''
            : `<span class="hvac-state-badge ${cardStateClass}">${state.powerText}</span>`;
        const actionStripHtml = isDashboardCard
            ? ''
            : `<div class="hvac-action-strip ${actionClass}">
                        <span class="hvac-mode-icon">${actionIcon}</span>
                        <span class="hvac-action-copy">
                            <span class="hvac-action-caption">动作</span>
                            <span class="hvac-action-text">${actionText}</span>
                        </span>
                    </div>`;
        const modeCaption = isDashboardCard ? '设定模式' : '模式';
        const dashboardSideHtml = `<div class="hvac-dashboard-compact-info">
                        <div class="hvac-compact-row mode ${modeClass || 'off'}">
                            <span class="hvac-compact-label">${modeCaption}</span>
                            <strong>${modeText}</strong>
                        </div>
                        <div class="hvac-compact-row fan">
                            <span class="hvac-compact-label">风速</span>
                            <strong>${fanSpeedHtml}</strong>
                        </div>
                        ${roomEnvRowHtml}
                    </div>`;
        const detailSideHtml = `<div class="hvac-info-stack">
                        ${roomEnvInfoRowHtml}
                        <div class="hvac-info-row">
                            <div class="label">风速</div>
                            <div class="value fan">${fanSpeedHtml}</div>
                        </div>
                        <div class="hvac-info-row power">
                            <div class="label">实时功率</div>
                            <div class="value">${powerText}</div>
                        </div>
                    </div>`;
        const disabledClass = typeof global.getPermissionDisabledClass === 'function' ? global.getPermissionDisabledClass('hvac.control') : '';
        const disabledAttrs = typeof global.getPermissionDisabledAttrs === 'function' ? global.getPermissionDisabledAttrs('hvac.control', '当前账号无空调控制权限') : '';
        const iconHtml = typeof global.getProjectorIconHtml === 'function' ? global.getProjectorIconHtml('power') : '电源';
        return `<div class="hvac-card ${cardStateClass}${modeClass ? ` mode-${modeClass}` : ''}">
            <div class="hvac-card-head">
                <div>
                    <div class="hvac-title">${title}</div>
                    <div class="hvac-subtitle">${subtitle}</div>
                </div>
                <div class="hvac-top-actions">
                    <div class="hvac-chip-row">
                        <span class="hvac-state-badge ${merged.online ? 'online' : 'offline'}">${state.onlineText}</span>
                        ${powerBadgeHtml}
                    </div>
                    <button class="projector-power-key ${powerButtonClass}${disabledClass}" ${disabledAttrs} title="${escapeHtml(powerButtonTitle)}" onclick="event.stopPropagation(); controlHvac('${safeDeviceId}', '${merged.power ? 'power_off' : 'power_on'}')">${iconHtml}</button>
                </div>
            </div>
            <div class="hvac-body">
                <div id="hvac-temp-${controlId}" class="hvac-temp-panel" onclick="toggleHvacTempControls('${safeDeviceId}', '${controlScope}', event)" title="点击调整目标温度">
                    <div class="hvac-temp-label">目标温度</div>
                    <div class="hvac-temp-value">${escapeHtml(targetValue)}<small>°C</small></div>
                    <div class="hvac-temp-target compact">
                        <div class="hvac-temp-hint">+ / - 调温</div>
                    </div>
                    <div class="hvac-thermal-pill ${thermalClass}">
                        ${getHvacModeIcon(thermalClass)}
                        <span>${escapeHtml(thermalText)}</span>
                    </div>
                    <div class="hvac-temp-stepper" onclick="event.stopPropagation()">
                        <button type="button" class="hvac-temp-step-btn${disabledClass}" ${disabledAttrs} onclick="adjustHvacTemperature('${safeDeviceId}', 1, event)" title="目标温度 +1">+</button>
                        <button type="button" class="hvac-temp-step-btn${disabledClass}" ${disabledAttrs} onclick="adjustHvacTemperature('${safeDeviceId}', -1, event)" title="目标温度 -1">-</button>
                    </div>
                </div>
                <div class="hvac-side-panel">
                    <div id="hvac-mode-${controlId}" class="hvac-mode-block ${modeClass}${isDashboardCard ? ' dashboard-hidden' : ''}">
                        <button type="button" class="hvac-mode-trigger ${modeClass || 'off'}" onclick="toggleHvacModeMenu('${safeDeviceId}', '${controlScope}', event)" title="点击切换模式">
                            <span class="hvac-mode-main">
                                <span class="hvac-mode-icon">${modeIcon}</span>
                                <span class="hvac-mode-copy">
                                    <span class="hvac-mode-caption">${modeCaption}</span>
                                    <span class="hvac-mode-name">${modeText}</span>
                                </span>
                            </span>
                            <span class="hvac-mode-side">切换</span>
                        </button>
                        <div class="hvac-mode-popover" onclick="event.stopPropagation()">${renderHvacModeOptions(deviceId, merged)}</div>
                    </div>
                    ${actionStripHtml}
                    ${isDashboardCard ? dashboardSideHtml : detailSideHtml}
                </div>
            </div>
            ${isDashboardCard
                ? `<div class="hvac-dashboard-footer"><div class="dashboard-mini-note">${noteText}</div>${detailButton ? `<div class="hvac-actions">${detailButton}</div>` : ''}</div>`
                : `${detailButton ? `<div class="hvac-actions">${detailButton}</div>` : ''}<div class="dashboard-mini-note">${noteText}</div>`}
            ${merged.error ? `<div class="hvac-error">${escapeHtml(String(merged.error))}</div>` : ''}
        </div>`;
    }

    const api = {
        formatHvacTemperature,
        formatHvacPower,
        getHvacModeText,
        getHvacActionText,
        getHvacModeClass,
        getHvacCardStateClass,
        getHvacActionClass,
        getHvacPowerButtonClass,
        getHvacModeIcon,
        getHvacFanLevel,
        renderHvacFanStatus,
        renderHvacFanInline,
        getHvacControlId,
        toHvacNumber,
        getHvacSupportedModes,
        renderHvacModeOptions,
        getHvacTempBounds,
        getHvacAgeText,
        formatCompactAgeFromSec,
        getHvacRoomName,
        getHvacSortOrder,
        getHvacRoomSort,
        getHvacGroupClass,
        getHvacGroupAccent,
        normalizeHvacEnvRoomName,
        getEnvSensorRoomName,
        getEnvThermalAgeSec,
        envSensorHasThermalValue,
        findRoomEnvSensors,
        renderHvacRoomEnvChips,
        renderMachineRoomEnvChip,
        buildHvacGroups,
        renderHvacGroup,
        isDashboardHvacAttention,
        getDashboardHvacAttentionRank,
        getDashboardHvacTotals,
        formatHvacDashboardPower,
        renderDashboardHvacMetric,
        renderDashboardHvacAttentionCard,
        renderDashboardHvacRoomTile,
        renderDashboardHvacOverview,
        getHvacStateSummary,
        renderHvacCard,
    };

    SmartCenter.hvacView = Object.assign({}, SmartCenter.hvacView || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('hvac-view', {
            kind: 'view',
            view: 'hvac',
            exports: Object.keys(api),
            source: 'static/js/views/hvac-view.js',
        });
    }

    Object.assign(global, api);
})(window);
