(function installSmartCenterLocalModel(global) {
  'use strict';

let modelConfig = null;
let chatMessages = [];
function $(id) { return document.getElementById(id); }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function setBadge(id, text, ok) { const el=$(id); el.textContent=text; el.className='status ' + (ok === true ? 'ok' : ok === false ? 'bad' : ''); }
function addMessage(role, content) { chatMessages.push({role, content}); renderMessages(); }
function renderMessages() {
  const box = $('messages');
  if (!chatMessages.length) {
    box.innerHTML = '<div class="msg system">本地模型只负责分析与建议；涉及开关机、断电、联动等动作，请在中控对应页面执行。</div>';
    return;
  }
  box.innerHTML = chatMessages.map(m => `<div class="msg ${m.role}">${esc(m.content)}</div>`).join('');
  box.scrollTop = box.scrollHeight;
}
function clearChat() { chatMessages = []; renderMessages(); }
async function loadConfig() {
  const resp = await fetch('/api/local-model/config');
  const data = await resp.json();
  if (!data.ok) throw new Error(data.msg || data.error || '读取失败');
  modelConfig = data.config || {};
  $('cfgName').value = modelConfig.name || '';
  $('cfgBaseUrl').value = modelConfig.base_url || '';
  $('cfgModel').value = modelConfig.model || '';
  $('cfgApiKey').value = '';
  $('cfgApiKey').placeholder = modelConfig.api_key_set ? '已配置，留空保留' : '可留空或填 dummy';
  $('cfgTemperature').value = modelConfig.temperature ?? 0.2;
  $('cfgMaxTokens').value = modelConfig.max_tokens ?? 512;
  $('cfgTimeout').value = modelConfig.timeout_sec ?? 120;
  $('cfgSystemPrompt').value = modelConfig.system_prompt || '';
  $('modelLine').textContent = `${modelConfig.base_url || '--'} · ${modelConfig.model || '--'}`;
  setBadge('saveBadge', '已读取', true);
}
async function saveConfig() {
  const payload = {
    enabled: true,
    name: $('cfgName').value.trim(),
    provider: 'openai-compatible',
    base_url: $('cfgBaseUrl').value.trim(),
    model: $('cfgModel').value.trim(),
    api_key: $('cfgApiKey').value.trim(),
    temperature: Number($('cfgTemperature').value || 0.2),
    max_tokens: Number($('cfgMaxTokens').value || 512),
    timeout_sec: Number($('cfgTimeout').value || 120),
    system_prompt: $('cfgSystemPrompt').value.trim()
  };
  const resp = await fetch('/api/local-model/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await resp.json();
  if (!data.ok) { setBadge('saveBadge', data.msg || data.error || '保存失败', false); return; }
  setBadge('saveBadge', '已保存', true);
  await loadConfig();
}
async function checkHealth() {
  setBadge('healthBadge', '检测中', null);
  const resp = await fetch('/api/local-model/health');
  const data = await resp.json();
  if (data.ok) setBadge('healthBadge', `在线 ${data.elapsed_ms || 0}ms`, true);
  else setBadge('healthBadge', '离线', false);
}
async function sendChat() {
  const prompt = $('prompt').value.trim();
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
    $('sendBtn').disabled = false;
  }
}
async function loadFiles() {
  const resp = await fetch('/api/local-model/training-files');
  const data = await resp.json();
  const rows = data.files || [];
  $('files').innerHTML = rows.length ? rows.map(item => `<div class="file-row"><div><div class="file-name" title="${esc(item.path)}">${esc(item.name)}</div><div class="file-meta">${Math.ceil((item.size || 0)/1024)} KB · ${esc(item.updated_at || '')}</div></div><a href="/api/local-model/training-files/${encodeURIComponent(item.name)}">下载</a></div>`).join('') : '<div class="hint">暂无导出文件</div>';
}
async function exportTraining() {
  $('exportInfo').textContent = '生成中...';
  const resp = await fetch('/api/local-model/export-training', {method:'POST'});
  const data = await resp.json();
  if (data.ok) $('exportInfo').textContent = `已生成：设备 ${data.counts.devices}，协议 ${data.counts.protocol_records}，日志 ${data.counts.logs}`;
  else $('exportInfo').textContent = data.msg || data.error || '生成失败';
  await loadFiles();
}
const api = {
  checkHealth,
  clearChat,
  exportTraining,
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

$('prompt').addEventListener('keydown', ev => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) sendChat(); });
renderMessages();
loadConfig().then(checkHealth).catch(err => { setBadge('saveBadge', '读取失败', false); $('modelLine').textContent = String(err); });
loadFiles();
})(window);
