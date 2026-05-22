// AI_MODULE: lighting_view
// AI_PURPOSE: 灯光/继电器页面，展示通道状态、控制按钮、场景和灯光日志。
// AI_BOUNDARY: 不拼协议指令；控制走 /api/light/control。
// AI_DATA_FLOW: /api/light/status/logs -> 灯光控制器 DOM。
// AI_RUNTIME: 灯光页面和首页灯光模块。
// AI_RISK: 高，按钮会真实改变灯光/继电器输出。
// AI_SEARCH_KEYWORDS: lighting, relay, channel, scene, log.

(function installSmartCenterLighting(global) {
    'use strict';

$(document).ready(function() {
    refreshStatus(); refreshLogs();
    setInterval(refreshStatus, 1000);
    setInterval(refreshLogs, 1500);

    $(document).on('click', '.channel-btn', function() {
        var btn = $(this);
        $.ajax({
            url: '/api/light/control', type: 'POST', contentType: 'application/json',
            data: JSON.stringify({ type: 'single', device_id: btn.data('device-id'), channel: btn.data('channel'), is_open: !btn.hasClass('status-on') })
        });
    });

    $(document).on('click', '.scene-btn', function() {
        $.ajax({
            url: '/api/light/control', type: 'POST', contentType: 'application/json',
            data: JSON.stringify({ type: 'scene', scene_id: $(this).data('scene-id') })
        });
    });
});

function refreshStatus() {
    $.get('/api/light/status', function(data) {
        for (var devId in data.online) {
            var isOnline = data.online[devId];
            var statusTag = $('#device-status-' + devId);
            if (isOnline) { statusTag.removeClass('status-offline').addClass('status-online').html('在线'); }
            else { statusTag.removeClass('status-online').addClass('status-offline').html('离线'); }
        }
        for (var devId in data.channels) {
            var statusList = data.channels[devId];
            statusList.forEach(function(status, index) {
                var btn = $('[data-device-id="' + devId + '"][data-channel="' + (index + 1) + '"]');
                if(btn.length > 0) {
                    btn.removeClass('status-on status-off status-offline');
                    if (status === null) {
                        btn.addClass('status-offline'); btn.find('.channel-state').html('离线');
                    } else if (status) {
                        btn.addClass('status-on'); btn.find('.channel-state').html('已开启');
                    } else {
                        btn.addClass('status-off'); btn.find('.channel-state').html('已关闭');
                    }
                }
            });
        }
    });
}

function refreshLogs() {
    $.get('/api/light/logs', function(data) {
        var html = '';
        data.forEach(function(log) {
            var t = new Date(log.time).toLocaleTimeString('zh-CN', {hour12: false});
            html += '<div class="log-item"><span class="log-time">[' + t + ']</span> <span>' + log.operation + '</span></div>';
        });
        $('#log-window').html(html);
    });
}

const api = {
    refreshLogs,
    refreshStatus,
};

const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
SmartCenter.lighting = Object.assign({}, SmartCenter.lighting || {}, api);
if (typeof SmartCenter.registerModule === 'function') {
    SmartCenter.registerModule('lighting', {
        kind: 'view',
        view: 'lighting',
        exports: Object.keys(api),
        source: 'static/js/views/lighting.js',
    });
}

Object.assign(global, api);
})(window);
