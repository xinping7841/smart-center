// AI_MODULE: local_model_view
// AI_PURPOSE: 本地模型控制台、健康检查、对话和训练数据导出入口。
// AI_BOUNDARY: 不直接执行设备动作；模型建议必须回到权限 API 和人工确认。
// AI_DATA_FLOW: /api/local-model/* -> 本地模型页面。
// AI_RUNTIME: 主界面本地模型栏目和独立 /local-model 页面共用。
// AI_RISK: 中，提示词和训练数据会影响模型后续建议。
// AI_SEARCH_KEYWORDS: local model, chat, training, export, RAG.

(function installSmartCenterLocalModel(global) {
  'use strict';

  let modelConfig = null;
  let chatMessages = [];
  let initialized = false;

  function $(id) { return document.getElementById(id); }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function hasUi() { return !!($('messages') && $('prompt') && $('sendBtn')); }
  function optionalSet(id, value) { const el = $(id); if (el) el.textContent = value; }
  function optionalValue(id, value) { const el = $(id); if (el) el.value = value; }
  function setBadge(id, text, ok) {
    const el = $(id);
    if (!el) return;
    const baseClass = el.classList.contains('local-model-status')
      ? (el.classList.contains('status') ? 'status local-model-status' : 'local-model-status')
      : 'status';
    el.textContent = text;
    el.className = baseClass + (ok === true ? ' ok' : ok === false ? ' bad' : '');
  }
  function formatNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toLocaleString('zh-CN') : '--';
  }
  function updateMetaFromConfig() {
    const cfg = modelConfig || {};
    optionalSet('modelLine', `${cfg.base_url || '--'} · ${cfg.model || '--'}`);
    optionalSet('localModelNameMeta', cfg.model || '--');
    optionalSet('localModelDocsMeta', '--');
    optionalSet('localModelContextMeta', cfg.max_model_len ? formatNumber(cfg.max_model_len) : '--');
    optionalSet('localModelVllmMeta', cfg.vllm_base_url || '--');
  }
  function addMessage(role, content) {
    chatMessages.push({role, content});
    renderMessages();
  }
  function renderMessages() {
    const box = $('messages');
    if (!box) return;
    if (!chatMessages.length) {
      box.innerHTML = '<div class="local-model-msg msg system">本地模型只负责分析与建议；涉及开关机、断电、联动等动作，请在中控对应页面执行。</div>';
      return;
    }
    box.innerHTML = chatMessages.map(m => `<div class="local-model-msg msg ${esc(m.role)}">${esc(m.content)}</div>`).join('');
    box.scrollTop = box.scrollHeight;
  }
  function clearChat() {
    chatMessages = [];
    renderMessages();
  }
  async function loadConfig() {
    if (!hasUi()) return null;
    const resp = await fetch('/api/local-model/config');
    const data = await resp.json();
    if (!data.ok) throw new Error(data.msg || data.error || '读取失败');
    modelConfig = data.config || {};
    optionalValue('cfgName', modelConfig.name || '');
    optionalValue('cfgBaseUrl', modelConfig.base_url || '');
    optionalValue('cfgVllmBaseUrl', modelConfig.vllm_base_url || '');
    optionalValue('cfgModel', modelConfig.model || '');
    optionalValue('cfgApiKey', '');
    const keyInput = $('cfgApiKey');
    if (keyInput) keyInput.placeholder = modelConfig.api_key_set ? '已配置，留空保留' : '可留空或填 dummy';
    optionalValue('cfgTemperature', modelConfig.temperature ?? 0.2);
    optionalValue('cfgMaxTokens', modelConfig.max_tokens ?? 512);
    optionalValue('cfgMaxModelLen', modelConfig.max_model_len ?? 32768);
    optionalValue('cfgTimeout', modelConfig.timeout_sec ?? 120);
    optionalValue('cfgSystemPrompt', modelConfig.system_prompt || '');
    updateMetaFromConfig();
    setBadge('saveBadge', '已读取', true);
    return modelConfig;
  }
  async function saveConfig() {
    if (!hasUi()) return;
    const payload = {
      enabled: true,
      name: ($('cfgName')?.value || '').trim(),
      provider: 'openai-compatible',
      base_url: ($('cfgBaseUrl')?.value || '').trim(),
      vllm_base_url: ($('cfgVllmBaseUrl')?.value || '').trim(),
      model: ($('cfgModel')?.value || '').trim(),
      api_key: ($('cfgApiKey')?.value || '').trim(),
      temperature: Number($('cfgTemperature')?.value || 0.2),
      max_tokens: Number($('cfgMaxTokens')?.value || 512),
      max_model_len: Number($('cfgMaxModelLen')?.value || 32768),
      timeout_sec: Number($('cfgTimeout')?.value || 120),
      system_prompt: ($('cfgSystemPrompt')?.value || '').trim()
    };
    setBadge('saveBadge', '保存中', null);
    const resp = await fetch('/api/local-model/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await resp.json();
    if (!data.ok) {
      setBadge('saveBadge', data.msg || data.error || '保存失败', false);
      return;
    }
    setBadge('saveBadge', '已保存', true);
    await loadConfig();
    await checkHealth();
  }
  async function checkHealth() {
    if (!hasUi()) return null;
    setBadge('healthBadge', '检测中', null);
    try {
      const resp = await fetch('/api/local-model/health');
      const data = await resp.json();
      if (data.ok) {
        const proxyText = data.proxy_online ? '代理在线' : '代理离线';
        const vllmText = data.vllm_online ? 'vLLM在线' : 'vLLM离线';
        const elapsedText = Number.isFinite(Number(data.elapsed_ms)) ? `${data.elapsed_ms}ms` : '';
        setBadge('healthBadge', `${proxyText}${elapsedText ? ' ' + elapsedText : ''}`, true);
        const docsText = data.docs_count ? `${formatNumber(data.docs_count)} docs` : (data.proxy_online ? '已加载' : '--');
        optionalSet('localModelDocsMeta', docsText);
        optionalSet('localModelContextMeta', data.max_model_len ? formatNumber(data.max_model_len) : (modelConfig?.max_model_len ? formatNumber(modelConfig.max_model_len) : '--'));
        optionalSet('localModelVllmMeta', vllmText);
      } else {
        setBadge('healthBadge', '离线', false);
        optionalSet('localModelVllmMeta', data.vllm_online ? 'vLLM在线' : 'vLLM离线');
      }
      return data;
    } catch (err) {
      setBadge('healthBadge', '离线', false);
      optionalSet('localModelVllmMeta', String(err).slice(0, 80));
      return null;
    }
  }
  async function sendChat() {
    if (!hasUi()) return;
    const prompt = ($('prompt')?.value || '').trim();
    if (!prompt) return;
    $('prompt').value = '';
    addMessage('user', prompt);
    $('sendBtn').disabled = true;
    try {
      const history = chatMessages.filter(m => m.role === 'user' || m.role === 'assistant').slice(-10);
      const resp = await fetch('/api/local-model/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({messages: history})});
      const data = await resp.json();
      if (data.ok) addMessage('assistant', data.answer || '(空回复)');
      else addMessage('system', data.msg || data.error || '调用失败');
    } catch (err) {
      addMessage('system', String(err));
    } finally {
      const btn = $('sendBtn');
      if (btn) btn.disabled = false;
    }
  }
  async function loadFiles() {
    const filesEl = $('files');
    if (!filesEl) return;
    const resp = await fetch('/api/local-model/training-files');
    const data = await resp.json();
    const rows = data.files || [];
    filesEl.innerHTML = rows.length ? rows.map(item => `<div class="local-model-file-row file-row"><div><div class="local-model-file-name file-name" title="${esc(item.path)}">${esc(item.name)}</div><div class="local-model-file-meta file-meta">${Math.ceil((item.size || 0)/1024)} KB · ${esc(item.updated_at || '')}</div></div><a href="/api/local-model/training-files/${encodeURIComponent(item.name)}">下载</a></div>`).join('') : '<div class="local-model-hint hint">暂无导出文件</div>';
  }
  async function exportTraining() {
    const info = $('exportInfo');
    if (info) info.textContent = '生成中...';
    const resp = await fetch('/api/local-model/export-training', {method:'POST'});
    const data = await resp.json();
    if (info) {
      if (data.ok) info.textContent = `已生成：设备 ${data.counts.devices}，服务器 ${data.counts.server_machines || 0}，协议 ${data.counts.protocol_records}，日志 ${data.counts.logs}，知识 ${data.counts.insights || 0}`;
      else info.textContent = data.msg || data.error || '生成失败';
    }
    await loadFiles();
  }
  function init() {
    if (!hasUi()) return;
    if (!initialized) {
      const prompt = $('prompt');
      prompt.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) sendChat();
      });
      initialized = true;
      renderMessages();
    }
    loadConfig().then(checkHealth).catch(err => {
      setBadge('saveBadge', '读取失败', false);
      optionalSet('modelLine', String(err));
    });
    loadFiles().catch(() => {});
  }

  const api = {
    checkHealth,
    clearChat,
    exportTraining,
    init,
    loadConfig,
    loadFiles,
    renderMessages,
    saveConfig,
    sendChat,
  };

  const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
  SmartCenter.localModel = Object.assign({}, SmartCenter.localModel || {}, api);
  if (typeof SmartCenter.registerModule === 'function') {
    SmartCenter.registerModule('local_model', {
      kind: 'view',
      view: 'local_model',
      exports: Object.keys(api),
      source: 'static/js/views/local-model.js',
    });
  }

  Object.assign(global, {
    checkHealth,
    clearChat,
    exportTraining,
    loadConfig,
    saveConfig,
    sendChat,
  });

  const ready = () => init();
  if (typeof SmartCenter.onReady === 'function') SmartCenter.onReady(ready);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true });
  else ready();
})(window);
