"""Apex Security Configuration Page — Embedded HTML/CSS/JS.

Standalone security admin page served at GET /admin/security-config.
No external dependencies — all CSS and JS are inline.
All event handlers use addEventListener (V2-10 compliant, no inline onclick).
"""

DASHBOARD_SECURITY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0F172A">
<title>Apex — Security Configuration</title>
<style>
:root {
  --bg: #0F172A;
  --surface: #1E293B;
  --border: rgba(148,163,184,0.18);
  --border-light: rgba(148,163,184,0.10);
  --text: #F1F5F9;
  --text-secondary: #CBD5E1;
  --text-dim: #94A3B8;
  --accent: #0EA5E9;
  --accent-hover: #0284C7;
  --accent-light: rgba(14,165,233,0.06);
  --green: #10B981;
  --green-bg: rgba(16,185,129,0.08);
  --green-border: rgba(16,185,129,0.25);
  --yellow: #F59E0B;
  --yellow-bg: rgba(245,158,11,0.08);
  --yellow-border: rgba(245,158,11,0.25);
  --red: #EF4444;
  --red-bg: rgba(239,68,68,0.06);
  --red-border: rgba(239,68,68,0.25);
  --teal: #0D9488;
  --radius: 10px;
  --radius-sm: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,0.28), 0 1px 2px rgba(0,0,0,0.18);
  --shadow-md: 0 8px 24px rgba(0,0,0,0.32), 0 2px 8px rgba(0,0,0,0.18);
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: "SF Mono", Menlo, Consolas, monospace;
}
body.theme-light {
  --bg: #F8FAFC;
  --surface: #FFFFFF;
  --border: #E2E8F0;
  --border-light: #F1F5F9;
  --text: #0F172A;
  --text-secondary: #475569;
  --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.04);
}
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* ── Layout ── */
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 220px; background: var(--surface); border-right: 1px solid var(--border);
  padding: 20px 0; flex-shrink: 0; position: sticky; top: 0; height: 100vh;
  overflow-y: auto; display: flex; flex-direction: column;
}
.sidebar-logo {
  padding: 0 20px 20px; font-size: 18px; font-weight: 700;
  color: var(--text); letter-spacing: -0.02em;
  border-bottom: 1px solid var(--border); margin-bottom: 12px;
}
.sidebar-logo span { color: var(--accent); }
.sidebar-logo a { text-decoration: none; color: inherit; }
.sidebar-nav { list-style: none; flex: 1; }
.sidebar-nav li a {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px; color: var(--text-secondary); text-decoration: none;
  font-size: 13px; font-weight: 500; transition: all 150ms ease;
  border-left: 3px solid transparent;
}
.sidebar-nav li a:hover { background: var(--bg); color: var(--text); }
.sidebar-nav li a.active {
  background: var(--accent-light); color: var(--accent);
  border-left-color: var(--accent); font-weight: 600;
}
.sidebar-nav li a .nav-icon { width: 18px; text-align: center; font-size: 15px; }
.sidebar-nav li a .nav-badge {
  margin-left: auto; background: var(--red); color: white;
  font-size: 10px; font-weight: 700; padding: 1px 6px;
  border-radius: 10px; min-width: 18px; text-align: center;
}
.sidebar-footer { padding: 16px 20px; border-top: 1px solid var(--border); }
.server-status {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  font-size: 12px; color: var(--text-secondary);
}
.server-pulse {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 6px rgba(16,185,129,0.5);
  animation: pulse 2s ease-in-out infinite; flex-shrink: 0;
}
@keyframes pulse {
  0%,100% { opacity:1; box-shadow: 0 0 6px rgba(16,185,129,0.5); }
  50% { opacity:.7; box-shadow: 0 0 12px rgba(16,185,129,0.7); }
}
.server-uptime { font-family: var(--mono); font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }
.btn-restart {
  width: 100%; display: flex; align-items: center; justify-content: center;
  gap: 6px; padding: 8px 12px; border-radius: var(--radius-sm); font-size: 12px;
  font-weight: 600; border: 1px solid var(--border); cursor: pointer;
  transition: all 150ms ease; font-family: var(--font);
  background: var(--surface); color: var(--text-secondary);
}
.btn-restart:hover { background: var(--yellow-bg); border-color: var(--yellow-border); color: #92400E; }
.btn-restart.restarting { background: var(--yellow-bg); border-color: var(--yellow-border); color: #92400E; pointer-events: none; }
.btn-restart .spinner {
  display: none; width: 14px; height: 14px;
  border: 2px solid var(--yellow-border); border-top-color: var(--yellow);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
.btn-restart.restarting .spinner { display: inline-block; }
.btn-restart.restarting .restart-icon { display: none; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Main ── */
.main { flex: 1; padding: 32px 40px; max-width: 960px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 4px; }
.page-header p { color: var(--text-secondary); font-size: 14px; }

/* ── Tabs ── */
.tab-bar {
  display: flex; border-bottom: 2px solid var(--border); margin-bottom: 24px;
  overflow-x: auto; -webkit-overflow-scrolling: touch;
}
.tab-btn {
  position: relative; padding: 12px 20px; font-size: 13px; font-weight: 500;
  color: var(--text-dim); background: none; border: none; cursor: pointer;
  font-family: var(--font); white-space: nowrap; transition: color 150ms ease;
  display: flex; align-items: center; gap: 8px;
}
.tab-btn:hover { color: var(--text-secondary); }
.tab-btn.active { color: var(--accent); font-weight: 600; }
.tab-btn.active::after {
  content: ''; position: absolute; bottom: -2px; left: 0; right: 0;
  height: 2px; background: var(--accent); border-radius: 1px 1px 0 0;
}
.tab-btn .tab-icon { font-size: 15px; }
.tab-badge {
  background: var(--red); color: white; font-size: 10px; font-weight: 700;
  padding: 1px 6px; border-radius: 10px; min-width: 16px; text-align: center; line-height: 1.4;
}
.tab-count {
  background: var(--bg); color: var(--text-dim); font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 10px; border: 1px solid var(--border);
}
.tab-panel { display: none; }
.tab-panel.active { display: block; animation: fadeIn 200ms ease; }
@keyframes fadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }

/* ── Cards ── */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); margin-bottom: 20px; overflow: hidden; }
.card-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border-light); }
.card-header h2 { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.card-body { padding: 20px; }
.card-actions { display: flex; gap: 8px; align-items: center; }

/* ── Posture Grid ── */
.posture-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
.posture-item {
  display: flex; align-items: flex-start; gap: 10px; padding: 14px 16px;
  border-radius: var(--radius-sm); background: var(--bg); border: 1px solid var(--border-light);
  transition: border-color 150ms ease;
}
.posture-item:hover { border-color: var(--border); }
.posture-item.warn { border-color: var(--yellow-border); background: var(--yellow-bg); }
.posture-item.critical { border-color: var(--red-border); background: var(--red-bg); }
.posture-item.ok { border-color: var(--green-border); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }
.status-dot.green { background: var(--green); box-shadow: 0 0 6px rgba(16,185,129,0.4); }
.status-dot.yellow { background: var(--yellow); box-shadow: 0 0 6px rgba(245,158,11,0.4); }
.status-dot.red { background: var(--red); box-shadow: 0 0 6px rgba(239,68,68,0.4); }
.posture-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-secondary); margin-bottom: 2px; }
.posture-detail { font-size: 13px; color: var(--text-dim); }

/* ── Banners ── */
.banner {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px;
  border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; margin-bottom: 16px;
}
.banner-warn { background: var(--yellow-bg); border: 1px solid var(--yellow-border); color: #92400E; }
.banner-critical { background: var(--red-bg); border: 1px solid var(--red-border); color: #991B1B; }
.banner-ok { background: var(--green-bg); border: 1px solid var(--green-border); color: #065F46; }
.banner .btn-sm { margin-left: auto; flex-shrink: 0; }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
  border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; border: none;
  cursor: pointer; transition: all 150ms ease; font-family: var(--font);
}
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--bg); color: var(--text); }
.btn-danger { background: transparent; color: var(--red); border: 1px solid var(--red-border); }
.btn-danger:hover { background: var(--red-bg); }
.btn-warn { background: var(--yellow); color: white; border: none; }
.btn-warn:hover { background: #D97706; }
.btn-sm { padding: 5px 12px; font-size: 12px; }

/* ── Badges ── */
.badge-tag {
  display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
}
.badge-green { background: var(--green-bg); color: #065F46; border: 1px solid var(--green-border); }
.badge-yellow { background: var(--yellow-bg); color: #92400E; border: 1px solid var(--yellow-border); }
.badge-red { background: var(--red-bg); color: #991B1B; border: 1px solid var(--red-border); }
.badge-dim { background: var(--bg); color: var(--text-dim); border: 1px solid var(--border); }
.badge-teal { background: rgba(13,148,136,.08); color: #0D9488; border: 1px solid rgba(13,148,136,.25); }

/* ── Audit Toolbar ── */
.audit-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-group { display: flex; gap: 0; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.filter-btn {
  padding: 6px 14px; font-size: 12px; font-weight: 500; background: var(--surface);
  color: var(--text-secondary); border: none; border-right: 1px solid var(--border);
  cursor: pointer; font-family: var(--font); transition: all 150ms ease;
}
.filter-btn:last-child { border-right: none; }
.filter-btn:hover { background: var(--bg); }
.filter-btn.active { background: var(--accent); color: white; }
.filter-btn .count { font-size: 10px; font-weight: 700; margin-left: 4px; opacity: .7; }
.audit-search {
  flex: 1; min-width: 200px; padding: 7px 12px 7px 32px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 13px; font-family: var(--font); color: var(--text); outline: none;
  background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394A3B8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'/%3E%3C/svg%3E") 10px center / 16px no-repeat;
}
.audit-search:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(14,165,233,0.15); }

/* ── Audit Rows ── */
.audit-row {
  display: flex; flex-direction: column; padding: 14px 16px;
  border-bottom: 1px solid var(--border-light); transition: background 100ms ease;
  cursor: pointer; gap: 8px;
}
.audit-row:hover { background: rgba(14,165,233,.02); }
.audit-row:last-child { border-bottom: none; }
.audit-row-top { display: flex; align-items: center; gap: 10px; }
.audit-row-status { display: flex; align-items: center; gap: 6px; min-width: 86px; }
.audit-row-status .status-dot { width: 8px; height: 8px; margin-top: 0; flex-shrink: 0; }
.audit-row-status .status-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }
.audit-row-persona { display: flex; align-items: center; gap: 6px; min-width: 140px; }
.audit-persona-avatar {
  width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 12px; flex-shrink: 0;
  background: var(--bg); border: 1px solid var(--border);
}
.audit-persona-name { font-size: 12px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.audit-tool-badge {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  font-family: var(--mono); background: var(--bg); color: var(--text-secondary);
  border: 1px solid var(--border); white-space: nowrap;
}
.audit-row-target {
  flex: 1; font-family: var(--mono); font-size: 12px; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.audit-row-time {
  font-family: var(--mono); font-size: 11px; color: var(--text-dim);
  white-space: nowrap; text-align: right; min-width: 60px;
}
.audit-row-bottom { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.audit-meta-pill {
  display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;
  border-radius: 10px; font-size: 10px; font-weight: 500;
  background: var(--bg); color: var(--text-dim); border: 1px solid var(--border-light);
}
.audit-meta-pill .pill-label { font-weight: 600; color: var(--text-secondary); }
.audit-row-reason { font-size: 12px; color: var(--text-dim); font-style: italic; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.audit-row-detail {
  display: none; padding: 10px 14px; margin-top: 4px;
  background: var(--bg); border-radius: var(--radius-sm); font-size: 12px;
  border: 1px solid var(--border-light);
}
.audit-row.expanded .audit-row-detail { display: block; }
.audit-row.expanded { background: rgba(14,165,233,.02); }
.audit-detail-grid { display: grid; grid-template-columns: 100px 1fr; gap: 4px 12px; }
.audit-detail-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-dim); }
.audit-detail-value { font-family: var(--mono); font-size: 11px; color: var(--text-secondary); word-break: break-all; }

/* ── Status text colours ── */
.green-text { color: var(--green); }
.yellow-text { color: var(--yellow); }
.red-text { color: var(--red); }
.teal-text { color: var(--teal); }
.dim { color: var(--text-dim); }
.mono { font-family: var(--mono); font-size: 12px; }

/* ── Pagination ── */
.pagination { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; font-size: 12px; color: var(--text-dim); }
.pagination-btns { display: flex; gap: 4px; }
.page-btn {
  padding: 5px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--text-secondary); font-size: 12px;
  cursor: pointer; font-family: var(--font); transition: all 150ms ease;
}
.page-btn:hover:not(:disabled) { background: var(--bg); }
.page-btn.active { background: var(--accent); color: white; border-color: var(--accent); }
.page-btn:disabled { opacity: .4; cursor: default; }

/* ── Stub card ── */
.stub-card { text-align: center; padding: 60px 40px; color: var(--text-dim); }
.stub-card .stub-icon { font-size: 40px; margin-bottom: 12px; }
.stub-card h3 { font-size: 16px; color: var(--text-secondary); margin-bottom: 6px; font-weight: 600; }
.stub-card p { font-size: 13px; }

/* ── Restart Modal ── */
.modal-overlay {
  display: none; position: fixed; inset: 0; background: rgba(15,23,42,.4);
  backdrop-filter: blur(4px); z-index: 1000; align-items: center; justify-content: center;
}
.modal-overlay.visible { display: flex; }
.modal {
  background: var(--surface); border-radius: var(--radius);
  box-shadow: var(--shadow-md), 0 20px 60px rgba(0,0,0,.12);
  padding: 28px; max-width: 400px; width: 90%; animation: modalIn 200ms ease;
}
@keyframes modalIn { from { opacity:0; transform:scale(0.96) translateY(8px); } to { opacity:1; transform:scale(1) translateY(0); } }
.modal h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.modal p { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; line-height: 1.6; }
.modal-code { background: var(--bg); border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 16px; font-family: var(--mono); font-size: 12px; color: var(--text-secondary); }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }

/* ── Quick Actions grid ── */
.quick-actions-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.quick-action-btn { justify-content: center; padding: 14px !important; }

/* ── Spinner overlay ── */
.loading-overlay { display: flex; align-items: center; justify-content: center; padding: 40px; color: var(--text-dim); gap: 8px; font-size: 13px; }
.load-spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }

/* ── Responsive ── */
@media (max-width: 768px) {
  .sidebar { display: none; }
  .main { padding: 16px; }
  .posture-grid { grid-template-columns: 1fr; }
  .page-header h1 { font-size: 20px; }
  .page-header { flex-direction: column; gap: 12px; }
  .tab-bar { gap: 0; }
  .tab-btn { padding: 10px 14px; font-size: 12px; }
  .audit-row-bottom { flex-wrap: wrap; }
  .audit-row-persona { min-width: auto; }
  .audit-row-target { min-width: 0; }
  .quick-actions-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="layout">

  <!-- ── Sidebar ── -->
  <nav class="sidebar" aria-label="Admin navigation">
    <div class="sidebar-logo"><a href="/admin/"><span>apex</span> admin</a></div>
    <ul class="sidebar-nav">
      <li><a href="/admin/"><span class="nav-icon">📊</span> Overview</a></li>
      <li><a href="#"><span class="nav-icon">⚙️</span> Config</a></li>
      <li><a href="/admin/security-config" class="active"><span class="nav-icon">🛡️</span> Security <span class="nav-badge" id="sidebarWarningBadge" hidden>0</span></a></li>
      <li><a href="#"><span class="nav-icon">🤖</span> Personas</a></li>
      <li><a href="#"><span class="nav-icon">🔑</span> Models &amp; Keys</a></li>
      <li><a href="#"><span class="nav-icon">🔔</span> Notifications</a></li>
      <li><a href="#"><span class="nav-icon">📁</span> Workspace</a></li>
      <li><a href="#"><span class="nav-icon">📋</span> Logs</a></li>
    </ul>
    <div class="sidebar-footer">
      <div class="server-status">
        <div class="server-pulse"></div>
        <span style="font-weight:600;">Server Running</span>
      </div>
      <div class="server-uptime" id="sidebarUptime">Loading…</div>
      <button class="btn-restart" id="restartBtn" type="button" aria-label="Restart server">
        <span class="restart-icon">🔄</span>
        <span class="spinner" aria-hidden="true"></span>
        Restart Server
      </button>
    </div>
  </nav>

  <!-- ── Main Content ── -->
  <main class="main">
    <div class="page-header">
      <div>
        <h1>🛡️ Security Configuration</h1>
        <p>Manage certificates, guardrails, security settings, and audit logging.</p>
      </div>
    </div>

    <!-- Banner (injected by JS) -->
    <div id="postureBanner" hidden></div>

    <!-- ── Tab Bar ── -->
    <div class="tab-bar" role="tablist" id="tabBar">
      <button class="tab-btn active" data-tab="posture" role="tab" aria-selected="true">
        <span class="tab-icon">📊</span> Posture
      </button>
      <button class="tab-btn" data-tab="certificates" role="tab" aria-selected="false">
        <span class="tab-icon">🔒</span> Certificates
      </button>
      <button class="tab-btn" data-tab="guardrails" role="tab" aria-selected="false">
        <span class="tab-icon">🛡️</span> Guardrails
      </button>
      <button class="tab-btn" data-tab="settings" role="tab" aria-selected="false">
        <span class="tab-icon">⚙️</span> Settings
      </button>
      <button class="tab-btn" data-tab="audit" role="tab" aria-selected="false">
        <span class="tab-icon">📋</span> Audit Log
        <span class="tab-count" id="auditTabCount">—</span>
      </button>
    </div>

    <!-- ═══════════════ TAB 1: POSTURE ═══════════════ -->
    <div class="tab-panel active" id="tab-posture">
      <div class="card">
        <div class="card-header">
          <h2>System Health</h2>
          <span class="badge-tag" id="postureStatusBadge">&nbsp;</span>
        </div>
        <div class="card-body" id="postureBody">
          <div class="loading-overlay"><div class="load-spinner"></div> Loading posture…</div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h2>Quick Actions</h2></div>
        <div class="card-body">
          <div class="quick-actions-grid">
            <button class="btn btn-ghost quick-action-btn" data-goto-tab="certificates" type="button">🔒 &nbsp;Certificates</button>
            <button class="btn btn-ghost quick-action-btn" data-goto-tab="guardrails" type="button">🛡️ &nbsp;Guardrails</button>
            <button class="btn btn-ghost quick-action-btn" data-goto-tab="audit" type="button">📋 &nbsp;Audit Log</button>
            <button class="btn btn-ghost quick-action-btn" data-goto-tab="settings" type="button">⚙️ &nbsp;Settings</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ TAB 2: CERTIFICATES (stub) ═══════════════ -->
    <div class="tab-panel" id="tab-certificates">
      <div class="card">
        <div class="stub-card">
          <div class="stub-icon">🔒</div>
          <h3>Certificates</h3>
          <p class="dim">TLS certificate management coming soon.</p>
        </div>
      </div>
    </div>

    <!-- ═══════════════ TAB 3: GUARDRAILS (stub) ═══════════════ -->
    <div class="tab-panel" id="tab-guardrails">
      <div class="card">
        <div class="stub-card">
          <div class="stub-icon">🛡️</div>
          <h3>Guardrails</h3>
          <p class="dim">Protected file rules, sandbox configuration, and secret detection coming soon.</p>
        </div>
      </div>
    </div>

    <!-- ═══════════════ TAB 4: SETTINGS (stub) ═══════════════ -->
    <div class="tab-panel" id="tab-settings">
      <div class="card">
        <div class="stub-card">
          <div class="stub-icon">⚙️</div>
          <h3>Settings</h3>
          <p class="dim">CSRF, rate limiting, and response header configuration coming soon.</p>
        </div>
      </div>
    </div>

    <!-- ═══════════════ TAB 5: AUDIT LOG ═══════════════ -->
    <div class="tab-panel" id="tab-audit">
      <div class="card">
        <div class="card-header">
          <h2>Audit Log</h2>
          <div class="card-actions">
            <span class="dim" style="font-size:12px;" id="auditTotalLabel">—</span>
          </div>
        </div>
        <div class="card-body" style="padding:16px 20px;">
          <div class="audit-toolbar">
            <div class="filter-group" id="auditFilterGroup">
              <button class="filter-btn active" data-filter="all" type="button">All<span class="count" id="countAll">—</span></button>
              <button class="filter-btn" data-filter="blocked" type="button">Blocked<span class="count" id="countBlocked">0</span></button>
              <button class="filter-btn" data-filter="whitelisted" type="button">Whitelisted<span class="count" id="countWhitelisted">0</span></button>
              <button class="filter-btn" data-filter="allowed" type="button">Allowed<span class="count" id="countAllowed">0</span></button>
            </div>
            <input type="search" class="audit-search" id="auditSearch" placeholder="Search actor, tool, target, session…" aria-label="Search audit log">
          </div>
          <div id="auditEntries">
            <div class="loading-overlay"><div class="load-spinner"></div> Loading audit log…</div>
          </div>
          <div class="pagination" id="auditPagination" hidden>
            <span id="paginationLabel">—</span>
            <div class="pagination-btns" id="paginationBtns"></div>
          </div>
        </div>
      </div>
    </div>

  </main>
</div>

<!-- ── Restart Confirmation Modal ── -->
<div class="modal-overlay" id="restartModal" role="dialog" aria-modal="true" aria-labelledby="restartModalTitle">
  <div class="modal">
    <h3 id="restartModalTitle">🔄 Restart Server?</h3>
    <p>
      This will gracefully shut down the Apex server and start it again.
      Active agent streams will complete before shutdown (up to 30s timeout).
      <br><br>
      <strong>Connected clients will briefly disconnect and auto-reconnect.</strong>
    </p>
    <div class="modal-code">
      $ bash server/launch_apex.sh<br>
      <span class="dim">PID <span id="restartPid">—</span> → graceful stop → respawn</span>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="restartCancelBtn" type="button">Cancel</button>
      <button class="btn btn-warn" id="restartConfirmBtn" type="button">Restart Server</button>
    </div>
  </div>
</div>

<script nonce="{{CSP_NONCE}}">
(function () {
'use strict';

// ── State ──────────────────────────────────────────────────────────────
var themeMode = localStorage.getItem('themeMode')
  || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
var systemThemeQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
var auditState = {
  filter: 'all',
  search: '',
  page: 1,
  pageSize: 25,
  total: 0,
  pages: 1,
  debounceTimer: null,
};
var postureData = null;
var serverPid = null;

// ── Helpers ──────────────────────────────────────────────────────────
function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function timeLabel(isoStr) {
  if (!isoStr) return '—';
  var dt = new Date(isoStr);
  if (isNaN(dt)) return esc(isoStr);
  return dt.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false});
}

function showEl(el) { el.removeAttribute('hidden'); el.style.display = ''; }
function hideEl(el) { el.hidden = true; }

function applyTheme() {
  document.body.classList.toggle('theme-light', themeMode === 'light');
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', themeMode === 'light' ? '#F8FAFC' : '#0F172A');
}

function syncThemeFromPreference() {
  var storedTheme = localStorage.getItem('themeMode');
  themeMode = storedTheme || (systemThemeQuery && systemThemeQuery.matches ? 'light' : 'dark');
  applyTheme();
}

// ── Tab Switching ─────────────────────────────────────────────────────
function switchTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(function (b) {
    var active = b.dataset.tab === tabName;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  document.querySelectorAll('.tab-panel').forEach(function (p) {
    p.classList.remove('active');
  });
  var panel = document.getElementById('tab-' + tabName);
  if (panel) panel.classList.add('active');

  if (tabName === 'posture' && !postureData) loadPosture();
  if (tabName === 'audit') loadAudit();

  // Update URL hash for bookmarking
  try { history.replaceState(null, '', '#' + tabName); } catch (e) {}
}

// Wire tab buttons
document.getElementById('tabBar').addEventListener('click', function (e) {
  var btn = e.target.closest('.tab-btn');
  if (!btn) return;
  switchTab(btn.dataset.tab);
});

// Quick-action "goto tab" buttons
document.querySelectorAll('[data-goto-tab]').forEach(function (btn) {
  btn.addEventListener('click', function () { switchTab(btn.dataset.goto_tab || btn.dataset['gotoTab'] || btn.getAttribute('data-goto-tab')); });
});

var ADMIN_TOKEN_STORAGE_KEY = "apexAdminToken";
var ADMIN_TOKEN_COOKIE = "apex_admin_token";

function getAdminToken() {
  var stored = sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
  if (stored) return stored;
  var match = document.cookie.match(/(?:^|;\\s*)apex_admin_token=([^;]+)/);
  if (!match) return '';
  try {
    stored = decodeURIComponent(match[1]);
  } catch (err) {
    stored = match[1];
  }
  if (stored) sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, stored);
  return stored;
}

function setAdminToken(token) {
  token = String(token || '').trim();
  if (!token) return '';
  sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
  document.cookie =
    ADMIN_TOKEN_COOKIE + '=' + encodeURIComponent(token) + '; Path=/admin; SameSite=Strict';
  return token;
}

async function ensureAdminSession() {
  var token = getAdminToken();
  if (token) return token;
  token = window.prompt('Enter admin token');
  return setAdminToken(token);
}

async function authFetch(url, options) {
  options = options || {};
  options.credentials = options.credentials || 'same-origin';
  var headers = new Headers(options.headers || {});
  headers.set('X-Requested-With', 'XMLHttpRequest');
  var token = getAdminToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', 'Bearer ' + token);
  }
  options.headers = headers;
  var resp = await fetch(url, options);
  if (resp.status === 401) {
    var body = await resp.clone().json().catch(function () { return {}; });
    if (body && body.code === 'ADMIN_AUTH_REQUIRED') {
      token = await ensureAdminSession();
      if (token) {
        headers.set('Authorization', 'Bearer ' + token);
        options.headers = headers;
        resp = await fetch(url, options);
      }
    }
  }
  return resp;
}

// ── Posture Tab ───────────────────────────────────────────────────────
function loadPosture() {
  authFetch('/admin/api/security/posture')
    .then(function (r) { return r.json(); })
    .then(renderPosture)
    .catch(function (err) {
      document.getElementById('postureBody').innerHTML =
        '<div class="loading-overlay" style="color:var(--red)">Failed to load posture data.</div>';
    });
}

function statusDotClass(status) {
  if (status === 'ok') return 'green';
  if (status === 'warning') return 'yellow';
  return 'red';
}

function postureItemClass(status) {
  if (status === 'ok') return 'ok';
  if (status === 'warning') return 'warn';
  return 'critical';
}

function renderPosture(data) {
  postureData = data;
  if (data.server && data.server.pid) {
    serverPid = data.server.pid;
    document.getElementById('restartPid').textContent = serverPid;
  }
  if (data.server && data.server.uptime_human) {
    document.getElementById('sidebarUptime').textContent = 'Uptime: ' + esc(data.server.uptime_human);
  }

  // Sidebar warning badge
  var wc = parseInt(data.warning_count || 0, 10);
  var sbb = document.getElementById('sidebarWarningBadge');
  if (wc > 0) { sbb.textContent = wc; showEl(sbb); } else { hideEl(sbb); }

  // Status badge on card header
  var badge = document.getElementById('postureStatusBadge');
  if (wc === 0) {
    badge.textContent = 'All Clear';
    badge.className = 'badge-tag badge-green';
  } else {
    badge.textContent = wc + ' Warning' + (wc !== 1 ? 's' : '');
    badge.className = 'badge-tag badge-yellow';
  }

  // Banner
  var bannerEl = document.getElementById('postureBanner');
  if (data.banner) {
    var b = data.banner;
    var cls = b.level === 'critical' ? 'banner-critical' : 'banner-warn';
    var btnHtml = '';
    if (b.action_tab) {
      btnHtml = '<button class="btn btn-sm btn-primary" data-goto-tab="' + esc(b.action_tab) + '" type="button">' + esc(b.action_label || 'View') + ' →</button>';
    }
    bannerEl.innerHTML = '<div class="banner ' + cls + '">⚠️ &nbsp;' + esc(b.message) + btnHtml + '</div>';
    showEl(bannerEl);
    // Wire any goto-tab buttons inside the banner
    bannerEl.querySelectorAll('[data-goto-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () { switchTab(btn.getAttribute('data-goto-tab')); });
    });
  } else {
    hideEl(bannerEl);
  }

  // Posture grid
  var items = data.items || [];
  var grid = '<div class="posture-grid">';
  items.forEach(function (item) {
    var dc = statusDotClass(item.status);
    var ic = postureItemClass(item.status);
    grid += '<div class="posture-item ' + ic + '">';
    grid += '<div class="status-dot ' + dc + '"></div>';
    grid += '<div><div class="posture-label">' + esc(item.label) + '</div>';
    grid += '<div class="posture-detail">' + esc(item.detail) + '</div></div>';
    grid += '</div>';
  });
  grid += '</div>';
  document.getElementById('postureBody').innerHTML = grid;
}

// ── Audit Log Tab ─────────────────────────────────────────────────────
function loadAudit() {
  var params = new URLSearchParams({
    status: auditState.filter,
    search: auditState.search,
    page: auditState.page,
    page_size: auditState.pageSize,
  });
  var entriesEl = document.getElementById('auditEntries');
  entriesEl.innerHTML = '<div class="loading-overlay"><div class="load-spinner"></div> Loading…</div>';

  authFetch('/admin/api/security/audit?' + params.toString())
    .then(function (r) { return r.json(); })
    .then(renderAudit)
    .catch(function () {
      entriesEl.innerHTML = '<div class="loading-overlay" style="color:var(--red)">Failed to load audit log.</div>';
    });
}

function renderAudit(data) {
  // Update counts in filter buttons
  var sc = data.status_counts || {};
  var totalAll = parseInt(data.total || 0, 10);
  document.getElementById('countAll').textContent = (sc.allowed || 0) + (sc.blocked || 0) + (sc.whitelisted || 0) || totalAll;
  document.getElementById('countBlocked').textContent = sc.blocked || 0;
  document.getElementById('countWhitelisted').textContent = sc.whitelisted || 0;
  document.getElementById('countAllowed').textContent = sc.allowed || 0;

  // Audit tab count badge
  document.getElementById('auditTabCount').textContent = totalAll.toLocaleString();

  // Header label
  auditState.total = totalAll;
  auditState.pages = data.pages || 1;
  document.getElementById('auditTotalLabel').textContent = totalAll.toLocaleString() + ' entries';

  var entries = data.entries || [];
  var html = '';

  if (entries.length === 0) {
    html = '<div class="loading-overlay" style="color:var(--text-dim)">No entries match the current filter.</div>';
  } else {
    entries.forEach(function (e) {
      var statusClass = 'dim';
      var dotClass = 'green';
      var labelClass = 'dim';
      var statusText = esc(e.status || '—');

      if (e.status === 'blocked') {
        dotClass = 'red'; statusClass = 'red-text'; labelClass = 'red-text';
      } else if (e.status === 'allowed') {
        dotClass = 'green'; statusClass = 'green-text'; labelClass = 'green-text';
      } else if (e.status === 'allowed_via_whitelist') {
        dotClass = 'green'; statusClass = 'teal-text'; labelClass = 'teal-text';
        statusText = 'WHITELST';
      } else if (e.status === 'redacted') {
        dotClass = 'yellow'; statusClass = 'yellow-text'; labelClass = 'yellow-text';
      }

      var timeStr = timeLabel(e.timestamp);
      var target = esc(e.target || '—');
      var tool = esc(e.tool_name || '—');
      var actor = esc(e.actor || '—');
      var sessionId = esc(e.session_id || '—');
      var summary = esc(e.summary || '');

      html += '<div class="audit-row" data-expanded="false">';
      html += '<div class="audit-row-top">';
      html += '<div class="audit-row-status"><span class="status-dot ' + dotClass + '"></span><span class="status-label ' + labelClass + '">' + statusText.toUpperCase() + '</span></div>';
      html += '<div class="audit-row-persona"><span class="audit-persona-avatar">💻</span><span class="audit-persona-name">' + actor + '</span></div>';
      html += '<span class="audit-tool-badge">' + tool + '</span>';
      html += '<span class="audit-row-target">' + target + '</span>';
      html += '<span class="audit-row-time">' + timeStr + '</span>';
      html += '</div>';

      if (e.session_id || summary) {
        html += '<div class="audit-row-bottom">';
        if (e.session_id) {
          html += '<span class="audit-meta-pill"><span class="pill-label">Session</span> ' + esc(e.session_id.substring(0, 8)) + '…</span>';
        }
        if (e.original_tool_name && e.original_tool_name !== e.tool_name) {
          html += '<span class="audit-meta-pill"><span class="pill-label">Original</span> ' + esc(e.original_tool_name) + '</span>';
        }
        if (summary) {
          html += '<span class="audit-row-reason">' + summary + '</span>';
        }
        html += '</div>';
      }

      html += '<div class="audit-row-detail">';
      html += '<div class="audit-detail-grid">';
      html += '<span class="audit-detail-label">Timestamp</span><span class="audit-detail-value">' + esc(e.timestamp) + '</span>';
      html += '<span class="audit-detail-label">Session ID</span><span class="audit-detail-value">' + sessionId + '</span>';
      html += '<span class="audit-detail-label">Actor</span><span class="audit-detail-value">' + actor + '</span>';
      html += '<span class="audit-detail-label">Tool</span><span class="audit-detail-value">' + tool + (e.original_tool_name && e.original_tool_name !== e.tool_name ? ' (original: ' + esc(e.original_tool_name) + ')' : '') + '</span>';
      html += '<span class="audit-detail-label">Target</span><span class="audit-detail-value">' + target + '</span>';
      html += '<span class="audit-detail-label">Status</span><span class="audit-detail-value ' + labelClass + '" style="font-weight:600;">' + esc(e.status || '—') + '</span>';
      if (summary) html += '<span class="audit-detail-label">Summary</span><span class="audit-detail-value">' + summary + '</span>';
      html += '</div></div>';
      html += '</div>';
    });
  }

  document.getElementById('auditEntries').innerHTML = html;

  // Wire expand/collapse on rows
  document.querySelectorAll('#auditEntries .audit-row').forEach(function (row) {
    row.addEventListener('click', function () { row.classList.toggle('expanded'); });
  });

  // Pagination
  renderPagination();
}

function renderPagination() {
  var pag = document.getElementById('auditPagination');
  var label = document.getElementById('paginationLabel');
  var btns = document.getElementById('paginationBtns');

  if (auditState.total === 0) { pag.hidden = true; return; }
  pag.removeAttribute('hidden');

  var start = (auditState.page - 1) * auditState.pageSize + 1;
  var end = Math.min(auditState.page * auditState.pageSize, auditState.total);
  label.textContent = 'Showing ' + start + '–' + end + ' of ' + auditState.total.toLocaleString() + ' entries';

  var pages = auditState.pages;
  var cur = auditState.page;
  var html = '';

  // Prev
  html += '<button class="page-btn" data-page="' + (cur - 1) + '" type="button"' + (cur <= 1 ? ' disabled' : '') + '>← Prev</button>';

  // Page numbers — show up to 7 around current
  var pageNums = [];
  if (pages <= 7) {
    for (var i = 1; i <= pages; i++) pageNums.push(i);
  } else {
    pageNums.push(1);
    if (cur > 3) pageNums.push('…');
    for (var j = Math.max(2, cur - 1); j <= Math.min(pages - 1, cur + 1); j++) pageNums.push(j);
    if (cur < pages - 2) pageNums.push('…');
    pageNums.push(pages);
  }

  pageNums.forEach(function (p) {
    if (p === '…') {
      html += '<button class="page-btn" disabled type="button">…</button>';
    } else {
      html += '<button class="page-btn' + (p === cur ? ' active' : '') + '" data-page="' + p + '" type="button">' + p + '</button>';
    }
  });

  // Next
  html += '<button class="page-btn" data-page="' + (cur + 1) + '" type="button"' + (cur >= pages ? ' disabled' : '') + '>Next →</button>';

  btns.innerHTML = html;

  // Wire page buttons
  btns.querySelectorAll('.page-btn[data-page]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var p = parseInt(btn.dataset.page, 10);
      if (isNaN(p) || p < 1 || p > auditState.pages) return;
      auditState.page = p;
      loadAudit();
    });
  });
}

// ── Audit Filters ────────────────────────────────────────────────────
document.getElementById('auditFilterGroup').addEventListener('click', function (e) {
  var btn = e.target.closest('.filter-btn');
  if (!btn) return;
  document.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
  btn.classList.add('active');
  auditState.filter = btn.dataset.filter;
  auditState.page = 1;
  loadAudit();
});

// ── Audit Search ─────────────────────────────────────────────────────
document.getElementById('auditSearch').addEventListener('input', function (e) {
  clearTimeout(auditState.debounceTimer);
  var val = e.target.value;
  auditState.debounceTimer = setTimeout(function () {
    auditState.search = val;
    auditState.page = 1;
    loadAudit();
  }, 350);
});

// ── Restart Modal ─────────────────────────────────────────────────────
function showRestartModal() { document.getElementById('restartModal').classList.add('visible'); }
function hideRestartModal() { document.getElementById('restartModal').classList.remove('visible'); }

document.getElementById('restartBtn').addEventListener('click', showRestartModal);
document.getElementById('restartCancelBtn').addEventListener('click', hideRestartModal);
document.getElementById('restartModal').addEventListener('click', function (e) {
  if (e.target === this) hideRestartModal();
});

document.getElementById('restartConfirmBtn').addEventListener('click', function () {
  hideRestartModal();
  var btn = document.getElementById('restartBtn');
  btn.classList.add('restarting');
  authFetch('/admin/api/restart', { method: 'POST' })
    .then(function () {
      setTimeout(function () { btn.classList.remove('restarting'); }, 5000);
    })
    .catch(function () {
      setTimeout(function () { btn.classList.remove('restarting'); }, 5000);
    });
});

window.addEventListener('storage', function (event) {
  if (event.key === 'themeMode') syncThemeFromPreference();
});

if (systemThemeQuery) {
  var handleSystemThemeChange = function (event) {
    if (!localStorage.getItem('themeMode')) {
      themeMode = event.matches ? 'light' : 'dark';
      applyTheme();
    }
  };
  if (typeof systemThemeQuery.addEventListener === 'function') {
    systemThemeQuery.addEventListener('change', handleSystemThemeChange);
  } else if (typeof systemThemeQuery.addListener === 'function') {
    systemThemeQuery.addListener(handleSystemThemeChange);
  }
}

// ── Initial Load ──────────────────────────────────────────────────────
// Honour URL hash for direct tab link (e.g. /admin/security-config#audit)
applyTheme();
var initialTab = (location.hash || '').replace('#', '').trim();
var validTabs = ['posture', 'certificates', 'guardrails', 'settings', 'audit'];
if (validTabs.indexOf(initialTab) !== -1) {
  switchTab(initialTab);
} else {
  loadPosture();
}

})();
</script>
</body>
</html>
"""
