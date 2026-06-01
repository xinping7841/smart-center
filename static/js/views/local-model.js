// AI_MODULE: local_model_view
// AI_PURPOSE: 本地模型控制台、健康检查、对话和训练数据导出入口。
// AI_BOUNDARY: 可作为自然语言控制入口；真实动作必须回到中控权限 API、审计和二次确认链路。
// AI_DATA_FLOW: /api/local-model/* -> 本地模型页面。
// AI_RUNTIME: 主界面本地模型栏目和独立 /local-model 页面共用。
// AI_RISK: 中，提示词和训练数据会影响模型后续建议。
// AI_SEARCH_KEYWORDS: local model, chat, training, export, RAG.

(function installSmartCenterLocalModel(global) {
  'use strict';

  let modelConfig = null;
  let chatMessages = [];
  let initialized = false;
  let pendingControl = null;
  let processLog = [];

  function $(id) { return document.getElementById(id); }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function renderLocalModelPage() {
    const root = $('view-local_model');
    if (!root || $('local-model-shell')) return;
    root.innerHTML = `
      <div class="card">
        <div class="card-title">
          <span>本地模型</span>
          <div class="local-model-actions">
            <span class="local-model-status" id="healthBadge">未检测</span>
            <button class="local-model-btn secondary" type="button" onclick="checkHealth()">检测服务</button>
          </div>
        </div>
        <div class="local-model-shell" id="local-model-shell">
          <section class="local-model-card local-model-chat">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">对话入口</div>
                <div class="local-model-subtitle" id="modelLine">读取配置中...</div>
              </div>
              <div class="local-model-actions">
                <button class="local-model-btn secondary" type="button" onclick="clearChat()">清空</button>
              </div>
            </div>
            <div class="local-model-meta-grid">
              <div class="local-model-meta-item">
                <div class="local-model-meta-label">模型</div>
                <div class="local-model-meta-value" id="localModelNameMeta">--</div>
              </div>
              <div class="local-model-meta-item">
                <div class="local-model-meta-label">知识库</div>
                <div class="local-model-meta-value" id="localModelDocsMeta">--</div>
              </div>
              <div class="local-model-meta-item">
                <div class="local-model-meta-label">上下文</div>
                <div class="local-model-meta-value" id="localModelContextMeta">--</div>
              </div>
              <div class="local-model-meta-item">
                <div class="local-model-meta-label">vLLM</div>
                <div class="local-model-meta-value" id="localModelVllmMeta">--</div>
              </div>
            </div>
            <div class="local-model-messages messages" id="messages"></div>
            <div class="local-model-composer">
              <textarea class="local-model-textarea" id="prompt" placeholder="问本地模型，例如：整理当前投影机、空调、强电柜的协议和状态关注点"></textarea>
              <button class="local-model-btn" id="sendBtn" type="button" onclick="sendChat()">发送</button>
            </div>
          </section>
          <aside class="local-model-side">
            <section class="local-model-card">
              <div class="local-model-head">
                <div class="local-model-title">后台配置</div>
                <span class="local-model-status" id="saveBadge">未保存</span>
              </div>
              <div class="local-model-form">
                <div>
                  <label>名称</label>
                  <input class="local-model-input" id="cfgName">
                </div>
                <div>
                  <label>对话入口 / 知识代理</label>
                  <input class="local-model-input" id="cfgBaseUrl">
                </div>
                <div>
                  <label>vLLM 上游服务</label>
                  <input class="local-model-input" id="cfgVllmBaseUrl">
                </div>
                <div>
                  <label>模型</label>
                  <input class="local-model-input" id="cfgModel">
                </div>
                <div>
                  <label>API Key</label>
                  <input class="local-model-input" id="cfgApiKey" placeholder="留空则保留原值，可填 dummy">
                </div>
                <div class="local-model-row2">
                  <div>
                    <label>温度</label>
                    <input class="local-model-input" id="cfgTemperature" type="number" step="0.1" min="0" max="2">
                  </div>
                  <div>
                    <label>输出上限</label>
                    <input class="local-model-input" id="cfgMaxTokens" type="number" min="64" max="4096">
                  </div>
                </div>
                <div class="local-model-row2">
                  <div>
                    <label>上下文长度</label>
                    <input class="local-model-input" id="cfgMaxModelLen" type="number" min="1024" max="262144">
                  </div>
                  <div>
                    <label>超时秒数</label>
                    <input class="local-model-input" id="cfgTimeout" type="number" min="3" max="600">
                  </div>
                </div>
                <div>
                  <label>系统提示词</label>
                  <textarea class="local-model-textarea" id="cfgSystemPrompt"></textarea>
                </div>
                <label class="local-model-switch-row">
                  <span>
                    <strong>允许飞书执行中控命令</strong>
                    <small>关闭后飞书仍可查询和解析，但不会进入真实控制执行。</small>
                  </span>
                  <input id="cfgFeishuControlEnabled" type="checkbox">
                </label>
                <div class="local-model-actions">
                  <button class="local-model-btn success" type="button" onclick="saveConfig()">保存配置</button>
                  <button class="local-model-btn secondary" type="button" onclick="loadConfig()">重新读取</button>
                </div>
                <div class="local-model-hint">默认使用 122 的知识代理 8001 作为对话入口，vLLM 8000 作为上游状态校验。模型只负责理解；飞书控制开启后仍需人工确认。</div>
              </div>
            </section>
            <section class="local-model-card">
              <div class="local-model-head">
                <div>
                  <div class="local-model-title">自然语言处理记录</div>
                  <div class="local-model-subtitle">模型理解、安全路由与实际执行过程</div>
                </div>
                <button class="local-model-btn secondary" type="button" onclick="loadProcessLog()">刷新</button>
              </div>
              <div class="local-model-process-list" id="processLog"></div>
            </section>
            <section class="local-model-card">
              <div class="local-model-head">
                <div class="local-model-title">训练数据导出</div>
                <button class="local-model-btn warning" type="button" onclick="exportTraining()">生成</button>
              </div>
              <div class="local-model-form">
                <div class="local-model-hint" id="exportInfo">将设备、协议配置、事件日志和操作日志归一化为 JSON/JSONL，并自动脱敏凭据。</div>
              </div>
              <div class="local-model-files" id="files"></div>
            </section>
          </aside>
        </div>
      </div>`;
  }
  function hasUi() { return !!($('messages') && $('prompt') && $('sendBtn')); }
  function optionalSet(id, value) { const el = $(id); if (el) el.textContent = value; }
  function optionalValue(id, value) { const el = $(id); if (el) el.value = value; }
  function optionalChecked(id, value) { const el = $(id); if (el) el.checked = !!value; }
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
  function isConfirmText(text) {
    return ['确认', '确认执行', '执行确认', '是的', '确定', '确认下发'].includes(String(text || '').replace(/\s+/g, ''));
  }
  function isCancelText(text) {
    return ['取消', '别执行', '不要执行', '撤销'].includes(String(text || '').replace(/\s+/g, ''));
  }
  function formatControlDryRun(data) {
    const cmd = data.command || {};
    if (!data.is_control_request) return '';
    if (!data.matched) return data.msg || '识别到控制请求，但没有明确匹配到设备。';
    const lines = [
      `控制解析：${cmd.label || '设备'} -> ${cmd.action_text || cmd.action || '控制'}`,
      `类型：${cmd.type || '--'}，风险：${cmd.risk || '--'}，置信度：${cmd.confidence || '--'}`,
      `权限：${data.permission || cmd.permission || '--'}${data.allowed === false ? '（未通过）' : ''}`,
    ];
    if (cmd.inference_reason) lines.push(`推断理由：${cmd.inference_reason}`);
    if (data.allowed === false) {
      lines.push(`无法执行：${data.deny_reason || '权限不足'}`);
    } else {
      lines.push('已进入待确认状态，未执行真实设备控制。回复“确认”执行，回复“取消”放弃。');
    }
    return lines.join('\n');
  }
  function compactJson(value) {
    try {
      return JSON.stringify(value || {});
    } catch (err) {
      return String(value || '');
    }
  }
  function processOutcomeText(value) {
    const map = {
      answered: '已回答',
      pending_confirmation: '待确认',
      control_blocked: '已拦截',
      route_rejected: '路由拒绝',
      unmatched: '未匹配',
      permission_denied: '权限拒绝',
      executed: '已执行',
      model_failed: '模型失败',
      model_http_error: '模型失败',
      not_control: '普通问答'
    };
    return map[value] || value || '--';
  }
  function processStageText(value) {
    const map = {classify:'理解', model:'模型', route:'路由', permission:'权限', policy:'策略', confirm:'确认', execute:'执行'};
    return map[value] || value || '步骤';
  }
  function renderProcessLog() {
    const box = $('processLog');
    if (!box) return;
    if (!processLog.length) {
      box.innerHTML = '<div class="local-model-hint">暂无自然语言处理记录</div>';
      return;
    }
    box.innerHTML = processLog.map(item => {
      const steps = Array.isArray(item.steps) ? item.steps : [];
      const stepHtml = steps.map(step => `
        <div class="local-model-process-step ${step.ok === false ? 'bad' : ''}">
          <span>${esc(processStageText(step.stage))}</span>
          <div><strong>${esc(step.title || '--')}</strong>${step.detail ? `<small>${esc(step.detail)}</small>` : ''}</div>
        </div>`).join('');
      const command = item.command || {};
      const commandLines = command.label ? [
        `${command.label} -> ${command.action_text || command.action || '--'}`,
        `${command.type || '--'} · ${command.risk || '--'} · ${command.confidence || '--'}`,
        `${command.method || 'POST'} ${command.path || ''}`,
        compactJson(command.payload)
      ] : [];
      const commandHtml = commandLines.length ? `<div class="local-model-process-command">${commandLines.map(line => `<span>${esc(line)}</span>`).join('')}</div>` : '';
      return `
        <details class="local-model-process-row">
          <summary>
            <span class="local-model-process-source">${esc(item.source || '--')}</span>
            <div><strong>${esc(item.text || '(空输入)')}</strong><small>${esc(item.started_at || '')}</small></div>
            <em>${esc(processOutcomeText(item.outcome))}</em>
          </summary>
          <div class="local-model-process-body">
            ${commandHtml}
            ${stepHtml || '<div class="local-model-hint">没有细分步骤</div>'}
          </div>
        </details>`;
    }).join('');
  }
  async function loadProcessLog() {
    const box = $('processLog');
    if (!box) return;
    try {
      const resp = await fetch('/api/local-model/nl-process-log?limit=40');
      const data = await resp.json();
      processLog = data.items || [];
      renderProcessLog();
    } catch (err) {
      box.innerHTML = `<div class="local-model-hint">${esc(String(err))}</div>`;
    }
  }
  async function handlePendingControl(prompt) {
    if (!pendingControl) return false;
    if (isCancelText(prompt)) {
      pendingControl = null;
      addMessage('system', '已取消待确认控制。');
      return true;
    }
    if (!isConfirmText(prompt)) return false;
    const token = pendingControl.pending_token;
    pendingControl = null;
    const resp = await fetch('/api/local-model/control/confirm', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pending_token: token})});
    const data = await resp.json();
    if (data.ok) addMessage('assistant', data.result || '控制已执行。');
    else addMessage('system', data.msg || data.error || '确认执行失败');
    await loadProcessLog();
    return true;
  }
  async function tryControlDryRun(prompt) {
    const resp = await fetch('/api/local-model/control/dry-run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text: prompt})});
    const data = await resp.json();
    if (!data.ok || !data.is_control_request) return false;
    const text = formatControlDryRun(data);
    if (text) addMessage(data.allowed === false ? 'system' : 'assistant', text);
    pendingControl = data.pending_token ? data : null;
    await loadProcessLog();
    return true;
  }
  function renderMessages() {
    const box = $('messages');
    if (!box) return;
    if (!chatMessages.length) {
      box.innerHTML = '<div class="local-model-msg msg system">本地模型可识别状态查询和受控控制意图；强电柜、时序电源、服务器关机/重启等高风险动作必须二次确认，不确定目标会先给出推断让你判断。</div>';
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
    optionalChecked('cfgFeishuControlEnabled', modelConfig.natural_language?.feishu_control_enabled);
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
      system_prompt: ($('cfgSystemPrompt')?.value || '').trim(),
      natural_language: {
        ...(modelConfig?.natural_language || {}),
        feishu_control_enabled: !!$('cfgFeishuControlEnabled')?.checked,
        feishu_control_require_confirmation: true,
        record_process_enabled: true
      }
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
      if (await handlePendingControl(prompt)) return;
      if (await tryControlDryRun(prompt)) return;
      const history = chatMessages.filter(m => m.role === 'user' || m.role === 'assistant').slice(-10);
      const resp = await fetch('/api/local-model/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({messages: history})});
      const data = await resp.json();
      if (data.ok) addMessage('assistant', data.answer || '(空回复)');
      else addMessage('system', data.msg || data.error || '调用失败');
      await loadProcessLog();
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
    renderLocalModelPage();
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
    loadProcessLog().catch(() => {});
  }

  const api = {
    checkHealth,
    clearChat,
    exportTraining,
    init,
    loadConfig,
    loadFiles,
    loadProcessLog,
    renderLocalModelPage,
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
    loadProcessLog,
    saveConfig,
    sendChat,
  });

  const ready = () => init();
  if (typeof SmartCenter.onReady === 'function') SmartCenter.onReady(ready);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true });
  else ready();
})(window);
