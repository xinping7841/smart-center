import os
from io import BytesIO

from flask import Flask, Response, jsonify, request

from .cabinet_gateway import (
    build_gateway_health,
    get_action_logs,
    get_cabinet_energy_history,
    get_cached_or_poll_status,
    onekey_action,
    set_channel_state,
    sync_gateway_config,
)
from .config_store import load_config
from .reporting import (
    build_raw_csv_text,
    build_raw_xlsx_bytes,
    build_report_index,
    build_statistics_csv_text,
    build_statistics_xlsx_bytes,
    build_summary_csv_text,
    build_summary_xlsx_bytes,
    resolve_report_dir,
)
from .service import build_meter_diagnostics_payload, build_meter_payload, export_reports_now, get_runtime_health_snapshot, poll_once, start_background_threads, sync_config
from .storage import init_db

app = Flask(__name__)


DIAGNOSTICS_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NAS 电表诊断页</title>
  <style>
    :root {
      --bg: #081120;
      --panel: rgba(15, 23, 42, 0.88);
      --panel-soft: rgba(15, 23, 42, 0.72);
      --line: rgba(148, 163, 184, 0.22);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --ok: #10b981;
      --warn: #f59e0b;
      --danger: #ef4444;
      --accent: #38bdf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.16), transparent 26%),
        linear-gradient(180deg, #020617, #0f172a 42%, #111827);
      color: var(--text);
      min-height: 100vh;
    }
    .page {
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px 20px 40px;
    }
    .hero {
      display: grid;
      gap: 16px;
      grid-template-columns: 1.5fr 1fr;
      margin-bottom: 18px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 20px 60px rgba(2, 6, 23, 0.32);
      backdrop-filter: blur(16px);
    }
    .hero-main {
      padding: 24px;
    }
    .hero-main h1 {
      margin: 0 0 10px;
      font-size: clamp(28px, 3.8vw, 40px);
      line-height: 1.1;
      letter-spacing: 0.02em;
    }
    .hero-main p {
      margin: 0;
      color: var(--muted);
      line-height: 1.8;
      font-size: 14px;
    }
    .hero-side {
      padding: 20px;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .mini-grid {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .mini {
      border-radius: 16px;
      border: 1px solid rgba(148, 163, 184, 0.16);
      background: rgba(15, 23, 42, 0.66);
      padding: 14px;
    }
    .mini .label {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .mini .value {
      font-size: 24px;
      font-weight: 800;
    }
    .toolbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      margin: 14px 0 18px;
    }
    .toolbar-left, .toolbar-right {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .search, select, button {
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.78);
      color: var(--text);
      padding: 10px 14px;
      font-size: 14px;
    }
    .search { min-width: 240px; }
    button {
      cursor: pointer;
      background: linear-gradient(135deg, #0ea5e9, #2563eb);
      border: none;
      font-weight: 700;
    }
    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.14);
      color: var(--text);
      font-size: 12px;
      border: 1px solid rgba(148, 163, 184, 0.12);
    }
    .table-wrap {
      overflow: auto;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 1380px;
    }
    thead th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: rgba(15, 23, 42, 0.96);
      color: #cbd5e1;
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }
    tbody tr:hover {
      background: rgba(30, 41, 59, 0.5);
    }
    .name-cell {
      display: grid;
      gap: 6px;
    }
    .name-cell strong {
      font-size: 15px;
    }
    .sub {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
    }
    .status-ok { color: #d1fae5; background: rgba(16, 185, 129, 0.16); border-color: rgba(16,185,129,0.26); }
    .status-warn { color: #fde68a; background: rgba(245, 158, 11, 0.14); border-color: rgba(245,158,11,0.26); }
    .status-danger { color: #fecaca; background: rgba(239, 68, 68, 0.14); border-color: rgba(239,68,68,0.28); }
    .diag-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .diag-item {
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      background: rgba(148, 163, 184, 0.12);
      color: #e2e8f0;
    }
    .diag-item.warn { background: rgba(245, 158, 11, 0.14); color: #fde68a; }
    .diag-item.error { background: rgba(239, 68, 68, 0.16); color: #fecaca; }
    .num {
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .muted {
      color: var(--muted);
    }
    .footer-note {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.8;
    }
    @media (max-width: 980px) {
      .hero { grid-template-columns: 1fr; }
      .mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .page { padding: 16px 12px 28px; }
      .hero-main, .hero-side { padding: 16px; }
      .mini-grid { grid-template-columns: 1fr 1fr; }
      .search { min-width: 0; width: 100%; }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="panel hero-main">
        <h1>NAS 电表逐表诊断</h1>
        <p>这个页面只看每块电表的原始实时数据，方便核对 NAS 采集结果是否异常。重点展示电压、电流、实时功率、累计电能、今日电量、本月电量，以及离线、缓存回退、数据延迟等诊断提示。</p>
      </div>
      <div class="panel hero-side">
        <div class="mini-grid" id="summary-cards"></div>
        <div class="badge-row" id="service-badges"></div>
      </div>
    </section>

    <section class="toolbar">
      <div class="toolbar-left">
        <input id="search-input" class="search" type="search" placeholder="搜索电表名称 / ID / 协议 / IP">
        <select id="status-filter">
          <option value="all">全部状态</option>
          <option value="online">只看在线</option>
          <option value="offline">只看离线</option>
          <option value="issues">只看异常</option>
          <option value="fallback">只看缓存回退</option>
        </select>
        <select id="sort-select">
          <option value="sort">按配置排序</option>
          <option value="power_desc">按实时功率从高到低</option>
          <option value="energy_desc">按累计电能从高到低</option>
          <option value="updated_desc">按最新更新时间</option>
        </select>
      </div>
      <div class="toolbar-right">
        <div class="badge" id="updated-at">等待首轮数据...</div>
        <button id="refresh-btn" type="button">立即刷新</button>
      </div>
    </section>

    <div class="table-wrap panel">
      <table>
        <thead>
          <tr>
            <th>电表</th>
            <th>状态</th>
            <th>诊断</th>
            <th>电压</th>
            <th>电流</th>
            <th>实时功率</th>
            <th>累计电能</th>
            <th>今日 / 本月</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody id="meter-table-body">
          <tr><td colspan="9" class="muted">正在读取电表数据...</td></tr>
        </tbody>
      </table>
    </div>

    <div class="footer-note">
      建议先核对电压、电流、实时功率三者是否大体一致，再看累计电能跳变是否正常。若显示“缓存回退”或“数据延迟”，说明当前页面看到的是 NAS 侧保底值，不一定是设备刚刚回来的最新值。
    </div>
  </div>

  <script>
    const state = { payload: null, loading: false };

    function num(value, digits = 2, suffix = '') {
      const n = Number(value);
      if (!Number.isFinite(n)) return '--';
      return `${n.toFixed(digits)}${suffix}`;
    }

    function fmtTime(value) {
      if (!value) return '--';
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value);
      return d.toLocaleString('zh-CN', { hour12: false });
    }

    function ageText(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return '--';
      if (n < 60) return `${n.toFixed(0)} 秒前`;
      if (n < 3600) return `${(n / 60).toFixed(1)} 分钟前`;
      return `${(n / 3600).toFixed(1)} 小时前`;
    }

    function textIncludes(row, keyword) {
      if (!keyword) return true;
      const text = [
        row.display_name, row.name, row.id, row.meter_id, row.source_key, row.display_protocol, row.ip, row.error
      ].join(' ').toLowerCase();
      return text.includes(keyword.toLowerCase());
    }

    function rowHasIssues(row) {
      return Array.isArray(row.diagnostics) && row.diagnostics.length > 0;
    }

    function statusClass(row) {
      if (!row.online) return 'status-danger';
      if (row._using_cached_fallback || row._degraded || rowHasIssues(row)) return 'status-warn';
      return 'status-ok';
    }

    function statusLabel(row) {
      if (!row.online) return '离线';
      if (row._using_cached_fallback) return '缓存回退';
      if (row._degraded) return '降级中';
      return '在线';
    }

    function diagClass(text) {
      const label = String(text || '');
      if (label.includes('离线') || label.includes('负值') || label.includes('连接失败')) return 'diag-item error';
      if (label.includes('缓存') || label.includes('延迟') || label.includes('降级') || label.includes('仍为 0')) return 'diag-item warn';
      return 'diag-item';
    }

    function renderSummary(payload) {
      const summary = payload.summary || {};
      document.getElementById('summary-cards').innerHTML = [
        ['总电表数', summary.total || 0],
        ['在线', summary.online || 0],
        ['离线', summary.offline || 0],
        ['异常提示', summary.with_diagnostics || 0],
      ].map(([label, value]) => `
        <div class="mini">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
        </div>
      `).join('');

      document.getElementById('service-badges').innerHTML = [
        `生成时间 ${fmtTime(payload.generated_at)}`,
        `轮询 ${num(payload.poll_interval_seconds, 1, ' 秒/次')}`,
        `回退 ${summary.fallback || 0}`,
        `降级 ${summary.degraded || 0}`,
      ].map(text => `<span class="badge">${text}</span>`).join('');
      document.getElementById('updated-at').textContent = `最近生成 ${fmtTime(payload.generated_at)}`;
    }

    function getFilteredRows(rows) {
      const keyword = document.getElementById('search-input').value.trim();
      const status = document.getElementById('status-filter').value;
      const sort = document.getElementById('sort-select').value;
      let list = (rows || []).filter(row => textIncludes(row, keyword));
      if (status === 'online') list = list.filter(row => !!row.online);
      if (status === 'offline') list = list.filter(row => !row.online);
      if (status === 'issues') list = list.filter(row => rowHasIssues(row));
      if (status === 'fallback') list = list.filter(row => !!row._using_cached_fallback);

      list = [...list];
      if (sort === 'power_desc') list.sort((a, b) => Number(b.realtime_power || 0) - Number(a.realtime_power || 0));
      else if (sort === 'energy_desc') list.sort((a, b) => Number(b.electric_energy || 0) - Number(a.electric_energy || 0));
      else if (sort === 'updated_desc') list.sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
      else list.sort((a, b) => Number(a.sort_order || 9999) - Number(b.sort_order || 9999));
      return list;
    }

    function renderTable(payload) {
      const rows = getFilteredRows(payload.meters || []);
      const tbody = document.getElementById('meter-table-body');
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="muted">当前筛选条件下没有电表数据。</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(row => `
        <tr>
          <td>
            <div class="name-cell">
              <strong>${row.display_name || row.name || row.id || '--'}</strong>
              <div class="sub">
                ${row.id || '--'}<br>
                ${row.display_protocol || '--'} / ${row.source_type || '--'}<br>
                ${row.ip || '--'}${row.port ? `:${row.port}` : ''}
              </div>
            </div>
          </td>
          <td>
            <span class="status-pill ${statusClass(row)}">${statusLabel(row)}</span>
            <div class="sub" style="margin-top:8px;">
              ${row.visible_in_meter_center === false ? '配置页隐藏' : '配置页显示'}<br>
              ${row.include_in_totals === false ? '不参与统计' : '参与统计'}
            </div>
          </td>
          <td>
            ${rowHasIssues(row) ? `<div class="diag-list">${row.diagnostics.map(item => `<span class="${diagClass(item)}">${item}</span>`).join('')}</div>` : '<span class="status-pill status-ok">无异常提示</span>'}
          </td>
          <td class="num">
            A ${num(row.voltage_a, 1, ' V')}<br>
            B ${num(row.voltage_b, 1, ' V')}<br>
            C ${num(row.voltage_c, 1, ' V')}
          </td>
          <td class="num">
            A ${num(row.current_a, 3, ' A')}<br>
            B ${num(row.current_b, 3, ' A')}<br>
            C ${num(row.current_c, 3, ' A')}
          </td>
          <td class="num">
            <strong>${num(row.realtime_power, 4, ' kW')}</strong>
            <div class="sub">功率因数 ${num(row.power_factor, 3, '')} / 频率 ${num(row.frequency, 2, ' Hz')}</div>
          </td>
          <td class="num">
            <strong>${num(row.electric_energy, 4, ' kWh')}</strong>
            <div class="sub">显示值 ${num(row.display_electric_energy ?? row.electric_energy, 4, ' kWh')}</div>
          </td>
          <td class="num">
            今日 ${num(row.daily_energy, 4, ' kWh')}<br>
            本月 ${num(row.monthly_energy, 4, ' kWh')}
          </td>
          <td>
            ${fmtTime(row.updated_at)}
            <div class="sub">
              数据龄期 ${ageText(row.age_seconds)}<br>
              失败计数 ${Number(row._failure_streak || 0)}
            </div>
          </td>
        </tr>
      `).join('');
    }

    async function loadData() {
      if (state.loading) return;
      state.loading = true;
      try {
        const res = await fetch('/api/diagnostics/meters', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        state.payload = payload;
        renderSummary(payload);
        renderTable(payload);
      } catch (err) {
        document.getElementById('meter-table-body').innerHTML = `<tr><td colspan="9" class="muted">读取失败：${String(err.message || err)}</td></tr>`;
      } finally {
        state.loading = false;
      }
    }

    function rerender() {
      if (state.payload) renderTable(state.payload);
    }

    document.getElementById('refresh-btn').addEventListener('click', loadData);
    document.getElementById('search-input').addEventListener('input', rerender);
    document.getElementById('status-filter').addEventListener('change', rerender);
    document.getElementById('sort-select').addEventListener('change', rerender);

    loadData();
    setInterval(loadData, 5000);
  </script>
</body>
</html>
"""


def _read_build_stamp():
    try:
        stamp_path = "/app/.build_stamp"
        if os.path.exists(stamp_path):
            with open(stamp_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


@app.route("/api/health")
def api_health():
    cfg = load_config()
    meter_statistics = cfg.get("meter_statistics", {}) or {}
    runtime = get_runtime_health_snapshot(window_seconds=600)
    return jsonify({
        "ok": 1,
        "service": "meter_service",
        "meter_count": len(cfg.get("meters", [])),
        "cabinet_meter_count": len(cfg.get("cabinets", [])),
        "auto_export_enabled": bool(meter_statistics.get("auto_export_enabled", True)),
        "report_dir": resolve_report_dir(meter_statistics),
        "build_stamp": _read_build_stamp(),
        "runtime": runtime,
    })


@app.route("/api/meters")
def api_meters():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 7, type=int)
    payload = build_meter_payload(target_source_key=target, period=period, days=days)
    payload["data_source"] = "meter_service"
    return jsonify(payload)


@app.route("/")
def diagnostics_home():
    return Response(DIAGNOSTICS_HTML, mimetype="text/html; charset=utf-8")


@app.route("/diagnostics")
def diagnostics_page():
    return Response(DIAGNOSTICS_HTML, mimetype="text/html; charset=utf-8")


@app.route("/api/diagnostics/meters")
def api_meter_diagnostics():
    payload = build_meter_diagnostics_payload()
    payload["ok"] = 1
    return jsonify(payload)


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/config/sync", methods=["POST"])
def api_config_sync():
    payload = request.get_json(silent=True) or {}
    saved = sync_config(payload)
    poll_once()
    export_result = export_reports_now()
    return jsonify({
        "ok": 1,
        "meter_count": len(saved.get("meters", [])),
        "cabinet_meter_count": len(saved.get("cabinets", [])),
        "export_result": export_result,
    })


@app.route("/api/cabinet/health")
def api_cabinet_health():
    return jsonify(build_gateway_health())


@app.route("/api/cabinet/status")
def api_cabinet_status():
    cab_idx = request.args.get("cab", 0, type=int)
    force = bool(request.args.get("force", "", type=str))
    payload = get_cached_or_poll_status(cab_idx, force=force)
    payload["ok"] = 1
    return jsonify(payload)


@app.route("/api/cabinet/logs")
def api_cabinet_logs():
    cab_idx = request.args.get("cab", None, type=int)
    return jsonify(get_action_logs(cab_idx))


@app.route("/api/cabinet/energy_history")
def api_cabinet_energy_history():
    cab_idx = request.args.get("cab", 0, type=int)
    days = request.args.get("days", 7, type=int)
    return jsonify(get_cabinet_energy_history(cab_idx, days=days))


@app.route("/api/cabinet/set", methods=["POST"])
def api_cabinet_set():
    payload = request.get_json(silent=True) or {}
    result = set_channel_state(payload.get("cab", 0), payload.get("ch", 0), payload.get("on", False))
    status_code = 200 if bool(result.get("ok")) else 500
    return jsonify(result), status_code


@app.route("/api/cabinet/onekey", methods=["POST"])
def api_cabinet_onekey():
    payload = request.get_json(silent=True) or {}
    result = onekey_action(payload.get("cab", 0), payload.get("action", ""))
    status_code = 200 if bool(result.get("ok")) else 500
    return jsonify(result), status_code


@app.route("/api/cabinet/config/sync", methods=["POST"])
def api_cabinet_config_sync():
    payload = request.get_json(silent=True) or {}
    saved = sync_gateway_config(payload)
    poll_once()
    return jsonify({"ok": 1, "cabinet_count": len(saved.get("cabinets", []))})


def _csv_response(csv_text, filename):
    return Response(
        csv_text.encode("utf-8-sig"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(xlsx_bytes, filename):
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/export/meter_statistics")
def api_export_meter_statistics():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period=period, days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_statistics_xlsx_bytes(payload, period), f"meter_statistics_{period}.xlsx")
    return _csv_response(build_statistics_csv_text(payload, period), f"meter_statistics_{period}.csv")


@app.route("/api/export/meter_raw")
def api_export_meter_raw():
    target = request.args.get("target", "total")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period="day", days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_raw_xlsx_bytes(payload.get("meters", [])), "meter_raw.xlsx")
    return _csv_response(build_raw_csv_text(payload.get("meters", [])), "meter_raw.csv")


@app.route("/api/export/meter_summary")
def api_export_meter_summary():
    target = request.args.get("target", "total")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period="day", days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_summary_xlsx_bytes(payload), "meter_summary.xlsx")
    return _csv_response(build_summary_csv_text(payload), "meter_summary.csv")


@app.route("/api/reports")
def api_reports():
    cfg = load_config()
    meter_statistics = cfg.get("meter_statistics", {}) or {}
    payload = build_report_index(meter_statistics)
    payload["ok"] = 1
    return jsonify(payload)


def create_app():
    init_db()
    start_background_threads()
    return app


if __name__ == "__main__":
    init_db()
    start_background_threads()
    app.run(host="0.0.0.0", port=6901, debug=False)
