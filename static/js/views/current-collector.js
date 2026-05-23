// AI_MODULE: current_collector_view
// AI_PURPOSE: 电流采集独立页面，展示实时通道、组合回路、暂停/恢复和配置状态。
// AI_BOUNDARY: 不直接读 Modbus；所有数据来自 /api/current-collector/*。
// AI_DATA_FLOW: /api/current-collector/status/read -> 原始通道区和组合区 DOM。
// AI_RUNTIME: current-collector 页面轮询。
// AI_RISK: 中，展示结果可能被用于投影/设备开机推断。
// AI_SEARCH_KEYWORDS: current collector, current, channel, group, pause.

(function installSmartCenterCurrentCollector(global) {
  'use strict';

  let lastPayload = null;
  let realtimePaused = false;
  let statusTimer = null;

  function $(id) { return document.getElementById(id); }
  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function formatA(value) {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(3)} A` : '--';
  }
  function hasLiveCurrent(value) {
    const num = Number(value);
    return Number.isFinite(num) && Math.abs(num) > 0.001;
  }
  function setStatus(online, text) {
    const el = $('status');
    el.className = `status ${online ? 'online' : 'offline'}`;
    el.textContent = text || (online ? '在线' : '离线');
  }
  function setPauseUi() {
    const btn = $('pauseBtn');
    const note = $('pauseNote');
    if (btn) {
      btn.textContent = realtimePaused ? '继续实时' : '暂停画面';
      btn.className = realtimePaused ? 'success' : 'warning';
    }
    if (note) note.className = `hold-note ${realtimePaused ? 'active' : ''}`;
  }
  function toggleRealtimePause() {
    realtimePaused = !realtimePaused;
    setPauseUi();
    if (!realtimePaused) fetchStatus().catch(() => {});
  }
  function render(payload) {
    lastPayload = payload || {};
    const cfg = lastPayload.config || {};
    const snap = lastPayload.snapshot || {};
    const channels = Array.isArray(lastPayload.channels) ? lastPayload.channels : [];
    const groups = Array.isArray(lastPayload.groups) ? lastPayload.groups : [];
    const enabled = lastPayload.enabled !== false;
    const online = !!lastPayload.online;
    $('pageTitle').textContent = cfg.name || '电流采集';
    setStatus(online, !enabled ? '已关闭' : (online ? '在线' : '离线'));
    $('toggleBtn').textContent = enabled ? '关闭采集' : '开启采集';
    $('toggleBtn').className = enabled ? 'danger' : 'success';
    $('subtitle').textContent = !enabled
      ? '采集已关闭'
      : online
        ? `${snap.collected_at || lastPayload.updated_at || '--'} / ${snap.transport || cfg.transport || '--'} / 地址 ${snap.slave || cfg.slave || '--'} / 寄存器 ${snap.register_base || '--'}`
        : `离线：${lastPayload.error || '暂无数据'}`;
    const visibleGroups = groups
      .filter(item => item.visible !== false)
      .sort((a, b) => Number(a.sort ?? 9999) - Number(b.sort ?? 9999) || String(a.name || '').localeCompare(String(b.name || '')));
    $('groupSection').style.display = visibleGroups.length ? 'block' : 'none';
    $('groupGrid').innerHTML = visibleGroups.map(item => {
      const live = hasLiveCurrent(item.total_current);
      const channelText = (item.channel_numbers || []).length ? `包含：${(item.channel_numbers || []).join('、')} 路` : '暂无通道';
      const activeText = (item.active_channels || []).length ? `有电流：${(item.active_channels || []).join('、')} 路` : '当前无动态电流';
      return `
      <section class="card group ${live ? 'live' : ''}">
        <div class="card-head">
          <div class="channel-name" title="${escapeHtml(item.name || '组合')}">${escapeHtml(item.name || '组合')}</div>
          <div class="raw">${escapeHtml(activeText)}</div>
        </div>
        <div class="metric"><span>组合总电流</span><strong>${formatA(item.total_current)}</strong></div>
        <div class="group-meta">${escapeHtml(channelText)} · 有效数据 ${item.valid_count ?? 0} 路</div>
      </section>
    `}).join('');
    const visibleChannels = channels
      .filter(item => item.visible !== false)
      .sort((a, b) => Number(a.sort ?? a.channel ?? 9999) - Number(b.sort ?? b.channel ?? 9999) || Number(a.channel || 0) - Number(b.channel || 0));
    $('grid').innerHTML = visibleChannels.map(item => {
      const live = hasLiveCurrent(item.current);
      return `
      <section class="card raw-card ${live ? 'live' : ''}">
        <div class="card-head">
          <div class="channel-name" title="${escapeHtml(item.name || `第${item.channel}路`)}">${escapeHtml(item.name || `第${item.channel}路`)}</div>
          <div class="raw">寄存器 ${item.raw_register ?? '--'}</div>
        </div>
        <div class="metric"><span>采集器电流</span><strong>${formatA(item.current)}</strong></div>
      </section>
    `}).join('');
    const error = lastPayload.error ? `<div class="error">ERROR: ${escapeHtml(lastPayload.error)}</div>` : '';
    $('log').innerHTML = `${error}<div>TX: ${escapeHtml(snap.request_hex || '--')}</div><div>RX: ${escapeHtml(snap.response_hex || '--')}</div>`;
  }
  async function fetchStatus() {
    if (realtimePaused) return;
    const res = await fetch('/api/current-collector/status', { cache: 'no-store' });
    render(await res.json());
  }
  async function readNow() {
    const res = await fetch('/api/current-collector/read', { method: 'POST', cache: 'no-store' });
    render(await res.json());
  }
  async function toggleEnabled() {
    const enabled = !(lastPayload && lastPayload.enabled === false);
    const res = await fetch('/api/current-collector/enabled', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !enabled })
    });
    render(await res.json());
  }
  const api = {
    fetchStatus,
    formatA,
    hasLiveCurrent,
    readNow,
    render,
    setPauseUi,
    setStatus,
    toggleEnabled,
    toggleRealtimePause,
  };

  const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
  SmartCenter.currentCollector = Object.assign({}, SmartCenter.currentCollector || {}, api);
  if (typeof SmartCenter.registerModule === 'function') {
    SmartCenter.registerModule('current_collector', {
      kind: 'view',
      view: 'current_collector',
      exports: Object.keys(api),
      source: 'static/js/views/current-collector.js',
    });
  }

  Object.assign(global, api);

  fetchStatus().catch(err => {
    setStatus(false, '连接失败');
    $('subtitle').textContent = String(err);
  });
  setPauseUi();
  statusTimer = global.setInterval(() => fetchStatus().catch(() => {}), 2000);
})(window);
