// AI_MODULE: page_shells_view
// AI_PURPOSE: 生成非首页页面的静态外壳，继续压缩 templates/index.html。
// AI_BOUNDARY: 只创建页面容器、标题、占位 DOM 和原有按钮；不发请求、不执行设备控制。
// AI_DATA_FLOW: switchTab(view) -> renderPageShell(view) -> 原有 view runtime 填充实时数据。
// AI_RUNTIME: app-runtime 切换页面前调用；所有旧容器 id 必须保持兼容。
// AI_RISK: 中，缺少容器会导致对应页面 runtime 渲染失败；新增页面时要同步补充 shell。
// AI_SEARCH_KEYWORDS: page shell, template slim, view root, static page container.

(function installSmartCenterPageShells(global) {
    'use strict';

    const SmartCenter = global.SmartCenter || (global.SmartCenter = {});

    const SHELLS = {
        power: `
                <div class="card power-log-summary-card">
                    <div class="card-title">
                        <span>强电操作日志汇总</span>
                        <span style="font-size:12px; color:var(--text-sub);">最新操作、外部网关、自动化触发统一显示</span>
                    </div>
                    <div class="power-log-summary-grid" id="power-log-summary-grid">
                        <div class="power-log-summary-empty">正在加载强电日志...</div>
                    </div>
                </div>
                <div id="power-page-grid">
                    <div class="card">
                        <div style="color:var(--text-sub); text-align:center; padding:20px;">正在加载强电柜...</div>
                    </div>
                </div>`,
        meter: '<div class="card lazy-view-placeholder">正在加载电表中心...</div>',
        light: `
                <div id="light-page-grid">
                    <div class="card">
                        <div style="color:var(--text-sub); text-align:center; padding:20px;">正在加载灯光设备...</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">场馆灯光日志</div>
                    <div class="log-list" id="light-global-log" style="height:250px;"></div>
                </div>`,
        ups: `
                <div class="card">
                    <div class="card-title">
                        <span>UPS 监测中心</span>
                        <span style="font-size:12px; color:var(--text-sub);">状态查询命令 Q1 / Q6 / WA，关机命令 S&lt;n&gt;</span>
                    </div>
                    <div class="ups-grid" id="ups-page-grid">
                        <div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">正在加载 UPS 设备...</div>
                    </div>
                </div>`,
        snmp: `
                <div class="card snmp-page-card">
                    <div class="card-title">
                        <span>网络与录像机监测中心</span>
                        <span style="font-size:12px; color:var(--text-sub);">SNMP 设备与录像机 ISAPI 状态统一展示，点击卡片查看完整详情</span>
                        <button class="nvr-preview-btn" type="button" onclick="switchTab('camera_preview', '监控预览', findNavElementByView('camera_preview'))">打开监控预览</button>
                    </div>
                    <div class="ups-grid snmp-page-grid" id="snmp-page-grid">
                        <div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">正在加载网络与录像机设备...</div>
                    </div>
                </div>`,
        proxy: '<div class="card lazy-view-placeholder">正在加载代理监控...</div>',
        camera_preview: `
                <div class="card">
                    <div class="card-title">
                        <span>监控画面预览</span>
                        <span style="font-size:12px; color:var(--text-sub);">默认 16 路快照墙，4 路稳定直播分页，点击画面切换单路低延迟</span>
                    </div>
                    <div class="nvr-preview-card standalone">
                        <div id="nvr-preview-panel">
                            <div class="nvr-preview-empty">正在加载录像机通道...</div>
                        </div>
                    </div>
                </div>`,
        sequencer: `
                <div class="card">
                    <div class="card-title">
                        <span>DS-608 时序电源控制台</span>
                        <span style="font-size:12px; color:var(--text-sub);">模拟官方上位机的 8 路控制逻辑，展示产品信息、通讯参数和当前指令码</span>
                    </div>
                    <div class="sequencer-filter-bar" id="page-sequencer-filters">
                        <button class="sequencer-filter-btn active" onclick="setSequencerFilter('all', 'page')">全部</button>
                        <button class="sequencer-filter-btn" onclick="setSequencerFilter('online', 'page')">在线</button>
                        <button class="sequencer-filter-btn" onclick="setSequencerFilter('offline', 'page')">离线/异常</button>
                    </div>
                    <div class="sequencer-grid" id="sequencer-page-grid">
                        <div style="color:var(--text-sub); grid-column:1/-1; text-align:center; padding:20px;">正在加载时序电源设备...</div>
                    </div>
                </div>`,
        door: '<div class="card lazy-view-placeholder">正在加载门禁状态与视觉辅助...</div>',
        scene: `
                <div class="card">
                    <div class="card-title">快捷全局指令</div>
                    <div class="scene-grid scene-quick-grid" id="scene-quick-grid">
                        <div class="scene-empty">正在加载快捷场景...</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>自动化引用场景</span>
                        <span style="font-size:12px; color:var(--text-sub);">这些场景由自动化规则调用，默认不作为手动快捷按钮展示</span>
                    </div>
                    <div class="automation-scene-grid" id="automation-scene-grid">
                        <div class="scene-empty">正在加载自动化场景...</div>
                    </div>
                </div>`,
        server: `
                <div class="card">
                    <div class="card-title" style="margin-bottom: 20px;">
                        <span>物理服务器与工作站节点大屏</span>
                        <div class="server-toolbar" aria-label="服务器看板工具">
                            <div class="server-toolbar-group server-mode-control">
                                <span class="server-mode-current" id="server-mode-current">简洁模式</span>
                                <div class="server-view-toggle" role="group" aria-label="服务器显示模式">
                                    <button class="active" type="button" data-server-view-mode="compact" onclick="setServerViewMode('compact')"><span>简洁</span></button>
                                    <button type="button" data-server-view-mode="detail" onclick="setServerViewMode('detail')"><span>详细</span></button>
                                </div>
                            </div>
                            <div class="server-toolbar-actions">
                                <button class="btn-base server-tool-btn server-export-btn" type="button" onclick="exportServerDeviceInfoCsv()">导出设备信息</button>
                                <button class="btn-base server-tool-btn server-agent-btn" type="button" onclick="openDeployModal()">Agent 部署命令</button>
                            </div>
                        </div>
                    </div>
                    <div class="server-grid" id="server-grid-container"></div>
                </div>`,
        local_model: '<div class="card lazy-view-placeholder">正在加载本地模型页面...</div>',
        projector: `
                <div class="card">
                    <div class="card-title">
                        <span>投影机控制面板</span>
                        <span style="font-size:12px; color:var(--text-sub);">常用功能直接点击，完整指令在遥控器弹窗中操作</span>
                    </div>
                    <div class="projector-card-grid" id="projector-page-grid">
                        <div style="color:var(--text-sub); grid-column: 1/-1; text-align:center; padding:20px;">正在加载投影机卡片...</div>
                    </div>
                </div>`,
        apple_audio: `
                <div id="apple-audio-page-root">
                    <div class="card">
                        <div style="color:var(--text-sub); text-align:center; padding:20px;">正在加载音乐播放器...</div>
                    </div>
                </div>`,
        universal: '<div class="card lazy-view-placeholder">正在加载协议控制中心...</div>',
        logs: '<div class="card lazy-view-placeholder">正在加载日志中心...</div>',
        env: `
                <div class="card">
                    <div class="card-title">环境传感器实时监控大屏</div>
                    <div class="env-stat-grid" id="env-grid-container">
                        <div style="color:var(--text-sub); grid-column:1/-1;">正在连接环境传感器...</div>
                    </div>
                </div>`,
        hvac: `
                <div class="card">
                    <div class="card-title">
                        <span>空调设备监控与控制</span>
                        <span style="font-size:12px; color:var(--text-sub);">当前接入来源：Home Assistant</span>
                    </div>
                    <div class="hvac-grid" id="hvac-grid-container">
                        <div class="hvac-empty">正在加载空调状态...</div>
                    </div>
                </div>`,
        auto: '<div class="card lazy-view-placeholder">正在加载自动化运行页面...</div>',
    };

    function normalizeViewId(viewId) {
        return String(viewId || '').replace(/^view-/, '').trim();
    }

    function renderPageShell(viewId, options = {}) {
        const key = normalizeViewId(viewId);
        const root = global.document ? document.getElementById(`view-${key}`) : null;
        if (!root || !SHELLS[key]) return false;
        if (!options.force && root.dataset.pageShellRendered === '1') return true;
        root.innerHTML = SHELLS[key];
        root.dataset.pageShellRendered = '1';
        root.dataset.pageShell = 'runtime';
        return true;
    }

    function renderAllPageShells(options = {}) {
        Object.keys(SHELLS).forEach(key => renderPageShell(key, options));
        return true;
    }

    const api = {
        renderPageShell,
        renderAllPageShells,
        shells: Object.keys(SHELLS),
    };

    SmartCenter.pageShells = Object.assign({}, SmartCenter.pageShells || {}, api);
    if (typeof SmartCenter.registerModule === 'function') {
        SmartCenter.registerModule('page-shells', {
            kind: 'view-shell',
            exports: ['renderPageShell', 'renderAllPageShells'],
            source: 'static/js/views/page-shells.js',
        });
    }

    global.renderPageShell = renderPageShell;
    global.renderAllPageShells = renderAllPageShells;
})(window);
