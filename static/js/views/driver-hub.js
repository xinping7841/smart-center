(function installSmartCenterDriverHub(global) {
    'use strict';

let currentGroups = '';

function esc(text) {
    return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
}

function renderRows(items) {
    const body = document.getElementById('driverBody');
    if (!Array.isArray(items) || !items.length) {
        body.innerHTML = '<tr><td colspan="8">无数据</td></tr>';
        return;
    }
    body.innerHTML = items.map(item => {
        const statusCls = item.online ? 'ok' : 'bad';
        const statusText = item.online ? '在线' : '离线';
        const err = item.error || '';
        const dataText = JSON.stringify(item.data || {}, null, 2);
        return `<tr>
            <td class="mono">${esc(item.driver_id)}</td>
            <td>${esc(item.group)}</td>
            <td>${esc(item.name)}</td>
            <td>${esc(item.protocol)}</td>
            <td>${esc(item.comm_mode)}</td>
            <td><span class="status ${statusCls}">${statusText}</span></td>
            <td>${esc(err)}</td>
            <td><pre class="json-cell mono">${esc(dataText)}</pre></td>
        </tr>`;
    }).join('');
}

async function reloadAll() {
    const url = currentGroups ? `/api/driver_hub/snapshot?groups=${encodeURIComponent(currentGroups)}` : '/api/driver_hub/snapshot';
    const resp = await fetch(url);
    const data = await resp.json();
    document.getElementById('totalDrivers').innerText = data.total_drivers || 0;
    document.getElementById('onlineDrivers').innerText = data.online_drivers || 0;
    document.getElementById('offlineDrivers').innerText = data.offline_drivers || 0;
    document.getElementById('updatedAt').innerText = data.generated_at || '--';
    renderRows(data.drivers || []);
}

function applyFilter() {
    const value = document.getElementById('groupsInput').value.trim();
    currentGroups = value;
    reloadAll();
}

function clearFilter() {
    document.getElementById('groupsInput').value = '';
    currentGroups = '';
    reloadAll();
}

const api = {
    applyFilter,
    clearFilter,
    reloadAll,
    renderRows,
};

const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
SmartCenter.driverHub = Object.assign({}, SmartCenter.driverHub || {}, api);
if (typeof SmartCenter.registerModule === 'function') {
    SmartCenter.registerModule('driver_hub', {
        kind: 'view',
        view: 'driver_hub',
        exports: Object.keys(api),
        source: 'static/js/views/driver-hub.js',
    });
}

Object.assign(global, {
    applyFilter,
    clearFilter,
    reloadAll,
});

reloadAll();
global.setInterval(reloadAll, 4000);
})(window);
