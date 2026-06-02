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
  let knowledgeStatus = null;

  function $(id) { return document.getElementById(id); }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function renderLocalModelPage() {
    const root = $('view-local_model');
    if (!root || $('local-model-shell')) return;
    root.innerHTML = `
      <div class="local-model-page" id="local-model-shell">
        <section class="local-model-topbar">
          <div class="local-model-heading">
            <span class="local-model-eyebrow">AI 配置与学习状态</span>
            <h2>本地模型运行面板</h2>
            <p id="modelLine">读取配置中...</p>
          </div>
          <div class="local-model-top-actions">
            <span class="local-model-status" id="healthBadge">未检测</span>
            <span class="local-model-status" id="cloudHealthBadge">云端未检测</span>
            <button class="local-model-btn secondary" type="button" onclick="checkHealth()">检测服务</button>
          </div>
        </section>
        <section class="local-model-metric-grid" aria-label="模型运行概览">
          <div class="local-model-metric">
            <span>本地模型</span>
            <strong id="localModelNameMeta">--</strong>
          </div>
          <div class="local-model-metric">
            <span>知识库</span>
            <strong id="localModelDocsMeta">--</strong>
          </div>
          <div class="local-model-metric">
            <span>上下文</span>
            <strong id="localModelContextMeta">--</strong>
          </div>
          <div class="local-model-metric">
            <span>模型服务</span>
            <strong id="localModelVllmMeta">--</strong>
          </div>
          <div class="local-model-metric">
            <span>云端增强</span>
            <strong id="cloudModelNameMeta">--</strong>
          </div>
          <div class="local-model-metric">
            <span>决策模式</span>
            <strong id="localModelDecisionMeta">--</strong>
          </div>
        </section>
        <div class="local-model-workspace">
          <section class="local-model-panel local-model-config-status">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">AI 配置状态</div>
                <div class="local-model-subtitle">当前模型、云端增强、飞书执行权限</div>
              </div>
            </div>
            <div class="local-model-config-summary">
              <div class="local-model-status-line">
                <span>本地模型</span>
                <strong id="parseLocalState">--</strong>
              </div>
              <div class="local-model-status-line">
                <span>云端模型</span>
                <strong id="parseCloudState">--</strong>
              </div>
              <div class="local-model-status-line">
                <span>当前采用</span>
                <strong id="parseDecisionState">--</strong>
              </div>
            </div>
            <div class="local-model-flow local-model-flow-compact">
              <div><span>1</span><strong>飞书输入</strong><small>自然语言请求</small></div>
              <div><span>2</span><strong>云端解析</strong><small>主判断</small></div>
              <div><span>3</span><strong>本地对照</strong><small>学习样本</small></div>
              <div><span>4</span><strong>沉淀优化</strong><small>切回本地</small></div>
            </div>
            <div class="local-model-flow-controls">
              <label class="local-model-switch-row">
                <span><strong>启用云端增强</strong><small id="cloudModelState">未启用，本地模型单独工作</small></span>
                <input id="cfgCloudEnabled" type="checkbox">
              </label>
              <div class="local-model-row2">
                <label class="local-model-switch-row local-model-mini-switch">
                  <span><strong>摘要刷新</strong><small>代码和设备知识摘要</small></span>
                  <input id="cfgCloudUseSummary" type="checkbox">
                </label>
                <label class="local-model-switch-row local-model-mini-switch">
                  <span><strong>飞书并行理解</strong><small>云端结果优先采用</small></span>
                  <input id="cfgCloudUseNlu" type="checkbox">
                </label>
              </div>
            </div>
            <label class="local-model-feishu-control" id="feishuControlSwitchCard">
              <input id="cfgFeishuControlEnabled" type="checkbox">
              <span class="local-model-toggle-visual" aria-hidden="true"><span></span></span>
              <span class="local-model-feishu-copy">
                <span class="local-model-feishu-kicker">飞书控制执行开关</span>
                <strong>允许飞书执行中控命令</strong>
                <small>关闭时仅查询、解析和记录，不下发控制。</small>
              </span>
              <span class="local-model-feishu-state" id="feishuControlState">已关闭，仅允许查询</span>
            </label>
          </section>
          <section class="local-model-panel local-model-process-panel">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">模型解析状态</div>
                <div class="local-model-subtitle">云端/本地理解对比、路由与执行结果</div>
              </div>
              <button class="local-model-btn secondary" type="button" onclick="loadProcessLog()">刷新</button>
            </div>
            <div class="local-model-parse-summary">
              <div><span>最近记录</span><strong id="learningSampleCount">--</strong></div>
              <div><span>云端选择</span><strong id="learningCloudSelected">--</strong></div>
              <div><span>本地可用</span><strong id="learningLocalOk">--</strong></div>
            </div>
            <div class="local-model-process-list" id="processLog"></div>
          </section>
          <section class="local-model-panel local-model-learning-panel">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">学习沉淀与切换准备</div>
                <div class="local-model-subtitle">先云端主用，持续存储样本，成熟后切回本地</div>
              </div>
            </div>
            <div class="local-model-learning-stage">
              <span id="learningStageBadge">观察中</span>
              <strong id="learningStageText">等待配置读取</strong>
            </div>
            <div class="local-model-learning-grid">
              <div><span>样本存储</span><strong id="learningStorageState">--</strong></div>
              <div><span>知识包</span><strong id="learningKnowledgeCount">--</strong></div>
              <div><span>摘要状态</span><strong id="learningSummaryState">--</strong></div>
              <div><span>本地切换</span><strong id="learningSwitchReadiness">--</strong></div>
            </div>
            <div class="local-model-learning-steps">
              <div><span>1</span><strong>云端稳定解析</strong><small>当前用于主判断</small></div>
              <div><span>2</span><strong>本地并行对照</strong><small>记录差异和成功样本</small></div>
              <div><span>3</span><strong>周期汇总学习</strong><small>沉淀知识、意图和别名</small></div>
              <div><span>4</span><strong>切换本地优先</strong><small>准确率达标后执行</small></div>
            </div>
          </section>
        </div>
        <div class="local-model-ops-grid">
          <details class="local-model-panel local-model-chat local-model-chat-compact local-model-chat-drawer">
            <summary class="local-model-chat-summary">
              <span>
                <strong>轻量对话测试</strong>
                <small>默认收起，临时验证自然语言理解时再展开</small>
              </span>
              <span class="local-model-chat-summary-action" aria-hidden="true"></span>
            </summary>
            <div class="local-model-chat-body">
              <div class="local-model-chat-actions">
                <button class="local-model-btn secondary" type="button" onclick="clearChat()">清空</button>
              </div>
              <div class="local-model-messages messages" id="messages"></div>
              <div class="local-model-composer">
                <textarea class="local-model-textarea" id="prompt" placeholder="临时测试一句自然语言，例如：查询一号厅灯光状态"></textarea>
                <button class="local-model-btn" id="sendBtn" type="button" onclick="sendChat()">发送</button>
              </div>
            </div>
          </details>
          <section class="local-model-panel">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">知识库状态</div>
                <div class="local-model-subtitle" id="knowledgeFreshness">等待读取</div>
              </div>
              <button class="local-model-btn secondary" type="button" onclick="loadKnowledgeStatus()">刷新</button>
            </div>
            <div class="local-model-knowledge-grid" id="knowledgeStatusGrid"></div>
            <div class="local-model-form">
              <div class="local-model-hint" id="knowledgeSummaryHint">系统地图、设备清单、控制能力、代码地图和高上下文源码包会一起服务自然语言查询与受控控制。</div>
              <button class="local-model-btn warning" type="button" id="summaryBtn" onclick="refreshSystemSummary()">刷新模型摘要</button>
            </div>
          </section>
          <section class="local-model-panel local-model-config-panel">
            <div class="local-model-head">
              <div>
                <div class="local-model-title">维护参数</div>
                <div class="local-model-subtitle">模型、云端增强和提示词配置</div>
              </div>
              <span class="local-model-status" id="saveBadge">未保存</span>
            </div>
            <div class="local-model-form">
              <details class="local-model-details">
                <summary>本地知识模型</summary>
                <div class="local-model-config-section">
                  <div class="local-model-config-section-title">
                    <strong>本地知识模型</strong>
                    <span>普通对话、状态查询、RAG 知识代理</span>
                  </div>
                  <div>
                    <label>名称</label>
                    <input class="local-model-input" id="cfgName">
                  </div>
                  <div>
                    <label>对话入口 / 知识代理</label>
                    <input class="local-model-input" id="cfgBaseUrl">
                  </div>
                  <div>
                    <label>模型上游 / 兼容服务</label>
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
                </div>
              </details>
              <details class="local-model-details">
                <summary>云端增强模型</summary>
                <div class="local-model-config-section local-model-cloud-section" id="cloudModelConfigSection">
                  <div class="local-model-config-section-title">
                    <strong>云端增强模型</strong>
                    <span>Ark / DeepSeek 复杂理解、飞书并行对比、当前云端为准</span>
                  </div>
                  <div class="local-model-row2">
                    <div>
                      <label>显示名称</label>
                      <input class="local-model-input" id="cfgCloudName">
                    </div>
                    <div>
                      <label>供应商</label>
                      <input class="local-model-input" id="cfgCloudProvider">
                    </div>
                  </div>
                  <div>
                    <label>Ark Base URL</label>
                    <input class="local-model-input" id="cfgCloudBaseUrl">
                  </div>
                  <div>
                    <label>云端模型</label>
                    <input class="local-model-input" id="cfgCloudModel">
                  </div>
                  <div>
                    <label>Ark API Key</label>
                    <input class="local-model-input" id="cfgCloudApiKey" placeholder="留空则保留原值">
                  </div>
                  <div class="local-model-row2">
                    <div>
                      <label>云端超时秒数</label>
                      <input class="local-model-input" id="cfgCloudTimeout" type="number" min="3" max="600">
                    </div>
                    <div>
                      <label>云端输出上限</label>
                      <input class="local-model-input" id="cfgCloudMaxTokens" type="number" min="64" max="8192">
                    </div>
                  </div>
                </div>
              </details>
              <div class="local-model-actions">
                <button class="local-model-btn success" type="button" onclick="saveConfig()">保存配置</button>
                <button class="local-model-btn secondary" type="button" onclick="loadConfig()">重新读取</button>
              </div>
            </div>
          </section>
          <section class="local-model-panel">
            <div class="local-model-head">
              <div class="local-model-title">训练数据导出</div>
              <button class="local-model-btn warning" type="button" onclick="exportTraining()">生成</button>
            </div>
            <div class="local-model-form">
              <div class="local-model-hint" id="exportInfo">将设备、协议配置、事件日志和操作日志归一化为 JSON/JSONL，并自动脱敏凭据。</div>
            </div>
            <div class="local-model-files" id="files"></div>
          </section>
        </div>
      </div>`;
  }
  function hasUi() { return !!($('messages') && $('prompt') && $('sendBtn')); }
  function optionalSet(id, value) { const el = $(id); if (el) el.textContent = value; }
  function optionalValue(id, value) { const el = $(id); if (el) el.value = value; }
  function optionalChecked(id, value) { const el = $(id); if (el) el.checked = !!value; }
  function readValue(id, fallback = '') {
    const el = $(id);
    return el ? String(el.value || '').trim() : String(fallback || '').trim();
  }
  function readNumber(id, fallback) {
    const el = $(id);
    if (!el) return Number(fallback);
    const value = Number(el.value);
    return Number.isFinite(value) ? value : Number(fallback);
  }
  function readChecked(id, fallback = false) {
    const el = $(id);
    return el ? !!el.checked : !!fallback;
  }
  function updateFeishuControlState() {
    const input = $('cfgFeishuControlEnabled');
    const card = $('feishuControlSwitchCard');
    const state = $('feishuControlState');
    const enabled = !!input?.checked;
    if (card) card.classList.toggle('is-enabled', enabled);
    if (state) state.textContent = enabled ? '已开启，可执行控制' : '已关闭，仅允许查询';
  }
  function updateCloudModelState() {
    const input = $('cfgCloudEnabled');
    const section = $('cloudModelConfigSection');
    const state = $('cloudModelState');
    const enabled = !!input?.checked;
    if (section) section.classList.toggle('is-enabled', enabled);
    if (state) state.textContent = enabled ? '已启用，用于复杂理解和摘要' : '未启用，本地模型单独工作';
  }
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
  function formatKb(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) return '--';
    if (num >= 1024 * 1024) return `${(num / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.ceil(num / 1024)} KB`;
  }
  function updateMetaFromConfig() {
    const cfg = modelConfig || {};
    const cloud = cfg.cloud_model || {};
    optionalSet('modelLine', `${cfg.base_url || '--'} · ${cfg.model || '--'}`);
    optionalSet('localModelNameMeta', cfg.model || '--');
    optionalSet('localModelDocsMeta', '--');
    optionalSet('localModelContextMeta', cfg.max_model_len ? formatNumber(cfg.max_model_len) : '--');
    optionalSet('localModelVllmMeta', cfg.vllm_base_url || '--');
    optionalSet('cloudModelNameMeta', cloud.enabled ? (cloud.model || cloud.name || '已启用') : '未启用');
    optionalSet('localModelDecisionMeta', cloud.enabled && cloud.use_for_nlu_fallback !== false ? '云端主用 / 本地学习' : '本地优先');
    optionalSet('parseLocalState', `${cfg.model || '--'} · ${cfg.max_model_len ? formatNumber(cfg.max_model_len) : '--'} 上下文`);
    optionalSet('parseCloudState', cloud.enabled ? `${cloud.model || cloud.name || '--'} · 已启用` : '未启用');
    optionalSet('parseDecisionState', cloud.enabled && cloud.use_for_nlu_fallback !== false ? '云端结果为准，本地并行学习' : '本地模型直接判断');
    updateLearningStatusSummary();
  }
  function updateCloudHealth(data) {
    const cloud = modelConfig?.cloud_model || {};
    if (!cloud.enabled) {
      setBadge('cloudHealthBadge', '未启用', null);
      optionalSet('cloudModelState', '未启用，本地模型单独工作');
      return;
    }
    const online = !!data?.cloud_online;
    const modelCount = Array.isArray(data?.cloud_models) ? data.cloud_models.length : 0;
    const label = online ? `在线${modelCount ? ` · ${modelCount} 模型` : ''}` : '离线';
    setBadge('cloudHealthBadge', label, online);
    optionalSet('cloudModelState', online ? `当前 ${data.cloud_model || cloud.model || '--'}` : '已启用，但健康检查未通过');
    optionalSet('parseCloudState', online ? `${data.cloud_model || cloud.model || '--'} · 在线` : `${cloud.model || '--'} · 离线`);
    updateLearningStatusSummary();
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
  function modelSourceText(value) {
    const map = {cloud: '云端', local: '本地'};
    return map[String(value || '')] || value || '--';
  }
  function findModelComparison(item) {
    const commandComparison = item?.command?.model_comparison;
    if (commandComparison && typeof commandComparison === 'object') return commandComparison;
    const steps = Array.isArray(item?.steps) ? item.steps : [];
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      const data = steps[i]?.data;
      if (data && typeof data === 'object' && data.schema === 'smart_center.model_comparison.v1') return data;
    }
    return null;
  }
  function renderModelComparison(comparison) {
    if (!comparison || typeof comparison !== 'object') return '';
    const results = Array.isArray(comparison.results) ? comparison.results : [];
    if (!results.length) return '';
    const selected = modelSourceText(comparison.selected_source);
    const priority = comparison.priority === 'cloud_first' ? '云端优先' : (comparison.priority === 'local_first' ? '本地优先' : comparison.priority || '--');
    const kind = comparison.kind === 'control_translate' ? '控制转译' : '意图理解';
    const resultHtml = results.map(row => {
      const status = row.ok ? (row.selected ? '采用' : '对照') : '失败';
      const main = row.intent || row.rewritten_text || row.error || '--';
      const meta = [
        row.model || '',
        Number.isFinite(Number(row.elapsed_ms)) ? `${row.elapsed_ms}ms` : '',
        row.confidence !== undefined ? `置信 ${row.confidence}` : '',
      ].filter(Boolean).join(' · ');
      const detail = row.query || row.reason || row.error || '';
      return `<div class="local-model-compare-row ${row.selected ? 'selected' : ''} ${row.ok ? '' : 'bad'}">
        <span>${esc(modelSourceText(row.source))}</span>
        <div><strong>${esc(main)}</strong>${detail ? `<small>${esc(detail)}</small>` : ''}${meta ? `<small>${esc(meta)}</small>` : ''}</div>
        <em>${esc(status)}</em>
      </div>`;
    }).join('');
    return `<div class="local-model-compare">
      <div class="local-model-compare-head"><strong>${esc(kind)}</strong><span>${esc(priority)} · 采用${esc(selected)}</span></div>
      ${resultHtml}
    </div>`;
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
      const comparisonHtml = renderModelComparison(findModelComparison(item));
      return `
        <details class="local-model-process-row">
          <summary>
            <span class="local-model-process-source">${esc(item.source || '--')}</span>
            <div><strong>${esc(item.text || '(空输入)')}</strong><small>${esc(item.started_at || '')}</small></div>
            <em>${esc(processOutcomeText(item.outcome))}</em>
          </summary>
          <div class="local-model-process-body">
            ${comparisonHtml}
            ${commandHtml}
            ${stepHtml || '<div class="local-model-hint">没有细分步骤</div>'}
          </div>
        </details>`;
    }).join('');
    updateLearningStatusSummary();
  }
  function renderKnowledgeStatus() {
    const grid = $('knowledgeStatusGrid');
    if (!grid) return;
    const data = knowledgeStatus || {};
    optionalSet('knowledgeFreshness', data.latest_updated_at ? `最新刷新 ${data.latest_updated_at}` : '暂无知识包');
    const rows = Array.isArray(data.items) ? data.items : [];
    if (!rows.length) {
      grid.innerHTML = '<div class="local-model-hint">暂无知识库状态</div>';
      updateLearningStatusSummary();
      return;
    }
    grid.innerHTML = rows.map(item => `
      <div class="local-model-knowledge-item ${item.exists ? 'is-ready' : 'is-missing'}">
        <div class="local-model-knowledge-title">
          <strong>${esc(item.label || item.prefix || '--')}</strong>
          <span>${item.exists ? '已生成' : '缺失'}</span>
        </div>
        <small>${esc(item.name || '等待生成')}</small>
        <em>${item.count != null ? `${formatNumber(item.count)} 条` : formatKb(item.size)}${item.updated_at ? ` · ${esc(item.updated_at)}` : ''}</em>
      </div>`).join('');
    const hint = $('knowledgeSummaryHint');
    if (hint) {
      const parts = [
        `上下文配置 ${formatNumber(data.max_model_len)}，建议摘要输入 ${formatNumber(data.recommended_context_len)}`,
        data.include_full_code_context ? '已启用高上下文源码包' : '未启用高上下文源码包',
        data.last_summary?.generated_at ? `最近模型摘要 ${data.last_summary.generated_at}` : '尚未生成模型摘要'
      ];
      hint.textContent = parts.join('；');
    }
    updateLearningStatusSummary();
  }
  function collectLearningStats() {
    const rows = Array.isArray(processLog) ? processLog : [];
    let cloudSelected = 0;
    let localOk = 0;
    let comparisons = 0;
    rows.forEach(item => {
      const comparison = findModelComparison(item);
      const results = Array.isArray(comparison?.results) ? comparison.results : [];
      if (results.length) comparisons += 1;
      results.forEach(row => {
        if (row.source === 'cloud' && row.selected) cloudSelected += 1;
        if (row.source === 'local' && row.ok) localOk += 1;
      });
    });
    const knowledgeRows = Array.isArray(knowledgeStatus?.items) ? knowledgeStatus.items : [];
    const readyKnowledge = knowledgeRows.filter(item => item.exists).length;
    return {rows, cloudSelected, localOk, comparisons, knowledgeRows, readyKnowledge};
  }
  function updateLearningStatusSummary() {
    const cfg = modelConfig || {};
    const cloud = cfg.cloud_model || {};
    const stats = collectLearningStats();
    const processCount = stats.rows.length;
    const hasSummary = !!knowledgeStatus?.last_summary?.generated_at;
    const readyRatio = stats.knowledgeRows.length ? stats.readyKnowledge / stats.knowledgeRows.length : 0;
    const localCoverage = stats.comparisons ? Math.round((stats.localOk / stats.comparisons) * 100) : null;
    const switchReady = cloud.enabled
      ? (processCount >= 80 && readyRatio >= 0.8 && hasSummary && localCoverage !== null && localCoverage >= 85)
      : false;
    optionalSet('learningSampleCount', processCount ? `${formatNumber(processCount)} 条` : '暂无');
    optionalSet('learningCloudSelected', stats.cloudSelected ? `${formatNumber(stats.cloudSelected)} 次` : '暂无');
    optionalSet('learningLocalOk', localCoverage === null ? '等待样本' : `${localCoverage}%`);
    optionalSet('learningStorageState', processCount ? `已记录 ${formatNumber(processCount)} 条` : '等待飞书/页面解析记录');
    optionalSet('learningKnowledgeCount', stats.knowledgeRows.length ? `${stats.readyKnowledge}/${stats.knowledgeRows.length} 就绪` : '等待知识包');
    optionalSet('learningSummaryState', hasSummary ? `已生成 ${knowledgeStatus.last_summary.generated_at}` : '等待摘要刷新');
    optionalSet('learningSwitchReadiness', switchReady ? '可评估切换' : '继续云端主用');
    optionalSet('learningStageText', switchReady ? '本地模型已具备切换评估条件' : (cloud.enabled ? '云端主用，本地持续对照学习' : '本地模型单独工作'));
    const badge = $('learningStageBadge');
    if (badge) {
      badge.textContent = switchReady ? '可切换评估' : (cloud.enabled ? '学习中' : '本地直连');
      badge.className = switchReady ? 'is-ready' : (cloud.enabled ? 'is-learning' : 'is-local');
    }
  }
  async function loadKnowledgeStatus() {
    const grid = $('knowledgeStatusGrid');
    if (grid) grid.innerHTML = '<div class="local-model-hint">读取中...</div>';
    try {
      const resp = await fetch('/api/local-model/knowledge-status');
      const data = await resp.json();
      knowledgeStatus = data.ok === false ? null : data;
      renderKnowledgeStatus();
      return data;
    } catch (err) {
      if (grid) grid.innerHTML = `<div class="local-model-hint">${esc(String(err))}</div>`;
      return null;
    }
  }
  async function refreshSystemSummary() {
    const btn = $('summaryBtn');
    const hint = $('knowledgeSummaryHint');
    const cloud = modelConfig?.cloud_model || {};
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = cloud.enabled && cloud.use_for_system_summary ? '正在让云端增强模型读取系统地图和高上下文代码摘要...' : '正在让本地模型读取系统地图和高上下文代码摘要...';
    try {
      const resp = await fetch('/api/local-model/refresh-system-summary', {method:'POST'});
      const data = await resp.json();
      if (hint) hint.textContent = data.ok ? `已生成模型摘要：${data.summary?.file || ''}` : (data.msg || data.error || '生成失败');
      await loadKnowledgeStatus();
    } catch (err) {
      if (hint) hint.textContent = String(err);
    } finally {
      if (btn) btn.disabled = false;
    }
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
      box.innerHTML = '<div class="local-model-msg msg system">本地模型可识别状态查询和受控控制意图；飞书理解会同时跑云端和本地，目前采用云端结果。高风险或不确定目标会先给出推断让你判断。</div>';
      return;
    }
    box.innerHTML = chatMessages.map(m => `<div class="local-model-msg msg ${esc(m.role)}">${esc(m.content)}</div>`).join('');
    box.scrollTop = box.scrollHeight;
  }
  function clearChat() {
    chatMessages = [];
    renderMessages();
  }
  function bindLocalModelEvents() {
    const prompt = $('prompt');
    if (prompt && prompt.dataset.localModelBound !== '1') {
      prompt.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) sendChat();
      });
      prompt.dataset.localModelBound = '1';
    }
    const feishuSwitch = $('cfgFeishuControlEnabled');
    if (feishuSwitch && feishuSwitch.dataset.localModelBound !== '1') {
      feishuSwitch.addEventListener('change', updateFeishuControlState);
      feishuSwitch.dataset.localModelBound = '1';
    }
    const cloudSwitch = $('cfgCloudEnabled');
    if (cloudSwitch && cloudSwitch.dataset.localModelBound !== '1') {
      cloudSwitch.addEventListener('change', updateCloudModelState);
      cloudSwitch.dataset.localModelBound = '1';
    }
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
    const cloud = modelConfig.cloud_model || {};
    optionalChecked('cfgCloudEnabled', cloud.enabled);
    optionalValue('cfgCloudName', cloud.name || 'Ark 云端增强模型');
    optionalValue('cfgCloudProvider', cloud.provider || 'ark');
    optionalValue('cfgCloudBaseUrl', cloud.base_url || 'https://ark.cn-beijing.volces.com/api/v3');
    optionalValue('cfgCloudModel', cloud.model || 'deepseek-v3-2-251201');
    optionalValue('cfgCloudApiKey', '');
    const cloudKeyInput = $('cfgCloudApiKey');
    if (cloudKeyInput) cloudKeyInput.placeholder = cloud.api_key_set ? '已配置，留空保留' : '填写 Ark API Key';
    optionalChecked('cfgCloudUseSummary', cloud.use_for_system_summary !== false);
    optionalChecked('cfgCloudUseNlu', cloud.use_for_nlu_fallback !== false);
    optionalValue('cfgCloudTimeout', cloud.timeout_sec ?? 180);
    optionalValue('cfgCloudMaxTokens', cloud.max_tokens ?? 2048);
    updateFeishuControlState();
    updateCloudModelState();
    updateMetaFromConfig();
    setBadge('saveBadge', '已读取', true);
    return modelConfig;
  }
  async function saveConfig() {
    if (!hasUi()) return;
    const payload = {
      enabled: true,
      name: readValue('cfgName'),
      provider: 'openai-compatible',
      base_url: readValue('cfgBaseUrl'),
      vllm_base_url: readValue('cfgVllmBaseUrl'),
      model: readValue('cfgModel'),
      api_key: readValue('cfgApiKey'),
      temperature: readNumber('cfgTemperature', 0.2),
      max_tokens: readNumber('cfgMaxTokens', 512),
      max_model_len: readNumber('cfgMaxModelLen', 32768),
      timeout_sec: readNumber('cfgTimeout', 120),
      system_prompt: readValue('cfgSystemPrompt'),
      cloud_model: {
        ...(modelConfig?.cloud_model || {}),
        enabled: readChecked('cfgCloudEnabled'),
        name: readValue('cfgCloudName', 'Ark 云端增强模型'),
        provider: readValue('cfgCloudProvider', 'ark'),
        base_url: readValue('cfgCloudBaseUrl', 'https://ark.cn-beijing.volces.com/api/v3'),
        model: readValue('cfgCloudModel', 'deepseek-v3-2-251201'),
        api_key: readValue('cfgCloudApiKey'),
        timeout_sec: readNumber('cfgCloudTimeout', 180),
        max_tokens: readNumber('cfgCloudMaxTokens', 2048),
        priority: 'cloud_first',
        compare_with_local: true,
        use_for_system_summary: readChecked('cfgCloudUseSummary', true),
        use_for_nlu_fallback: readChecked('cfgCloudUseNlu', true)
      },
      natural_language: {
        ...(modelConfig?.natural_language || {}),
        feishu_control_enabled: readChecked('cfgFeishuControlEnabled'),
        feishu_control_require_confirmation: false,
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
        const vllmText = data.vllm_online ? '模型服务在线' : '模型服务离线';
        const elapsedText = Number.isFinite(Number(data.elapsed_ms)) ? `${data.elapsed_ms}ms` : '';
        setBadge('healthBadge', `${proxyText}${elapsedText ? ' ' + elapsedText : ''}`, true);
        const docsText = data.docs_count ? `${formatNumber(data.docs_count)} docs` : (data.proxy_online ? '已加载' : '--');
        optionalSet('localModelDocsMeta', docsText);
        optionalSet('localModelContextMeta', data.max_model_len ? formatNumber(data.max_model_len) : (modelConfig?.max_model_len ? formatNumber(modelConfig.max_model_len) : '--'));
        optionalSet('localModelVllmMeta', vllmText);
      } else {
        setBadge('healthBadge', '离线', false);
        optionalSet('localModelVllmMeta', data.vllm_online ? '模型服务在线' : '模型服务离线');
      }
      updateCloudHealth(data);
      return data;
    } catch (err) {
      setBadge('healthBadge', '离线', false);
      optionalSet('localModelVllmMeta', String(err).slice(0, 80));
      updateCloudHealth(null);
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
      if (data.ok) info.textContent = `已生成：设备 ${data.counts.devices}，控制能力 ${data.counts.control_capabilities || 0}，服务器 ${data.counts.server_machines || 0}，协议 ${data.counts.protocol_records}，日志 ${data.counts.logs}，知识 ${data.counts.insights || 0}`;
      else info.textContent = data.msg || data.error || '生成失败';
    }
    await loadFiles();
    await loadKnowledgeStatus();
  }
  function init() {
    renderLocalModelPage();
    if (!hasUi()) return;
    bindLocalModelEvents();
    if (!initialized) {
      initialized = true;
      renderMessages();
    }
    loadConfig().then(checkHealth).catch(err => {
      setBadge('saveBadge', '读取失败', false);
      optionalSet('modelLine', String(err));
    });
    loadFiles().catch(() => {});
    loadKnowledgeStatus().catch(() => {});
    loadProcessLog().catch(() => {});
  }

  const api = {
    checkHealth,
    clearChat,
    exportTraining,
    init,
    loadConfig,
    loadFiles,
    loadKnowledgeStatus,
    loadProcessLog,
    renderLocalModelPage,
    renderMessages,
    saveConfig,
    sendChat,
    refreshSystemSummary,
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
    loadKnowledgeStatus,
    loadProcessLog,
    refreshSystemSummary,
    saveConfig,
    sendChat,
  });

  const ready = () => init();
  if (typeof SmartCenter.onReady === 'function') SmartCenter.onReady(ready);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true });
  else ready();
})(window);
