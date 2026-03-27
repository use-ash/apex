"""Apex Dashboard — Embedded HTML/CSS/JS.

Single-page admin dashboard for the Apex Server.
Served as a string constant from dashboard.py at GET /admin/.
No external dependencies — all CSS, JS, and icons are inline.
"""

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Apex Dashboard</title>
<style>
/* ===================================================================
   CSS Custom Properties
   =================================================================== */

:root {
    --bg: #0F172A;
    --surface: #1E293B;
    --card: #334155;
    --text: #F1F5F9;
    --dim: #94A3B8;
    --accent: #0EA5E9;
    --green: #10B981;
    --red: #EF4444;
    --yellow: #F59E0B;
    --radius: 8px;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    --transition: 150ms ease;
    --sidebar-width: 220px;
}

/* ===================================================================
   Reset & Base
   =================================================================== */

*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

html, body {
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

button {
    cursor: pointer;
    font-family: inherit;
    font-size: inherit;
    border: none;
    border-radius: var(--radius);
    transition: background var(--transition), opacity var(--transition);
}

input, select {
    font-family: inherit;
    font-size: inherit;
    color: var(--text);
    background: var(--bg);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 8px 12px;
    outline: none;
    transition: border-color var(--transition);
}

input:focus, select:focus {
    border-color: var(--accent);
}

select {
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    padding-right: 30px;
}

/* ===================================================================
   Layout: Sidebar + Main
   =================================================================== */

.app-layout {
    display: flex;
    height: 100vh;
    overflow: hidden;
}

/* -- Sidebar -------------------------------------------------------- */

.sidebar {
    width: var(--sidebar-width);
    min-width: var(--sidebar-width);
    background: var(--surface);
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--card);
    z-index: 10;
}

.sidebar-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 20px 16px 16px;
    border-bottom: 1px solid var(--card);
}

.sidebar-header svg {
    flex-shrink: 0;
}

.sidebar-header h1 {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.01em;
}

.sidebar-nav {
    flex: 1;
    padding: 8px;
    overflow-y: auto;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius);
    color: var(--dim);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
    user-select: none;
}

.nav-item:hover:not(.nav-disabled) {
    background: var(--card);
    color: var(--text);
}

.nav-item.nav-active {
    background: var(--accent);
    color: #fff;
}

.nav-item.nav-active svg {
    opacity: 1;
}

.nav-disabled {
    opacity: 0.35;
    cursor: not-allowed;
}

.nav-item svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    opacity: 0.7;
}

.nav-badge {
    margin-left: auto;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 10px;
    background: var(--card);
    color: var(--dim);
}

.sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--card);
    font-size: 11px;
    color: var(--dim);
}

/* -- Main Content --------------------------------------------------- */

.main-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px 28px 40px;
}

.page { display: none; }
.page.page-active { display: block; }

.page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
}

.page-header h2 {
    font-size: 22px;
    font-weight: 600;
}

/* ===================================================================
   Components: Cards
   =================================================================== */

.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.card {
    background: var(--surface);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
}

.card-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim);
    margin-bottom: 16px;
}

.card-title svg {
    width: 16px;
    height: 16px;
}

.stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
}

.stat-row + .stat-row {
    border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.stat-label {
    color: var(--dim);
    font-size: 13px;
}

.stat-value {
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}

/* -- Status Indicators ---------------------------------------------- */

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    flex-shrink: 0;
}

.status-dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-dot.red { background: var(--red); box-shadow: 0 0 6px var(--red); }
.status-dot.yellow { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
.status-dot.dim { background: var(--dim); }

.status-inline {
    display: flex;
    align-items: center;
}

/* -- Progress Bars (cert expiry) ------------------------------------ */

.cert-row {
    margin-bottom: 12px;
}

.cert-row:last-child {
    margin-bottom: 0;
}

.cert-label {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    margin-bottom: 4px;
}

.cert-label-name {
    color: var(--dim);
}

.cert-label-days {
    font-weight: 500;
}

.cert-bar {
    height: 6px;
    border-radius: 3px;
    background: var(--card);
    overflow: hidden;
}

.cert-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}

.cert-bar-fill.green { background: var(--green); }
.cert-bar-fill.yellow { background: var(--yellow); }
.cert-bar-fill.red { background: var(--red); }

/* -- Model Row ------------------------------------------------------ */

.model-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
}

.model-row + .model-row {
    border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.model-name {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 500;
}

.model-latency {
    color: var(--dim);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
}

/* ===================================================================
   Components: Buttons
   =================================================================== */

.btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    border-radius: var(--radius);
}

.btn-primary {
    background: var(--accent);
    color: #fff;
}

.btn-primary:hover {
    background: #0284C7;
}

.btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.btn-ghost {
    background: transparent;
    color: var(--dim);
    border: 1px solid var(--card);
}

.btn-ghost:hover {
    background: var(--card);
    color: var(--text);
}

.btn svg {
    width: 14px;
    height: 14px;
}

/* ===================================================================
   Components: Config Form
   =================================================================== */

.config-section {
    background: var(--surface);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 20px;
}

.config-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}

.config-section-title {
    font-size: 15px;
    font-weight: 600;
    text-transform: capitalize;
}

.restart-badge {
    display: none;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 12px;
    background: rgba(245, 158, 11, 0.15);
    color: var(--yellow);
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.restart-badge.visible {
    display: inline-block;
}

.form-field {
    margin-bottom: 16px;
}

.form-field:last-child {
    margin-bottom: 0;
}

.form-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 4px;
}

.form-help {
    font-size: 12px;
    color: var(--dim);
    margin-bottom: 6px;
}

.form-field input[type="text"],
.form-field input[type="number"],
.form-field select {
    width: 100%;
    max-width: 400px;
}

/* Toggle Switch */

.toggle-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
}

.toggle {
    position: relative;
    width: 40px;
    height: 22px;
    cursor: pointer;
}

.toggle input {
    opacity: 0;
    width: 0;
    height: 0;
    position: absolute;
}

.toggle-track {
    position: absolute;
    inset: 0;
    background: var(--card);
    border-radius: 11px;
    transition: background var(--transition);
}

.toggle input:checked + .toggle-track {
    background: var(--accent);
}

.toggle-knob {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 16px;
    height: 16px;
    background: var(--text);
    border-radius: 50%;
    transition: transform var(--transition);
    pointer-events: none;
}

.toggle input:checked ~ .toggle-knob {
    transform: translateX(18px);
}

.toggle-label {
    font-size: 13px;
    color: var(--dim);
}

/* Readonly alert indicators */

.readonly-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
}

.readonly-indicator + .readonly-indicator {
    border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.config-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--card);
}

/* ===================================================================
   Components: Toast
   =================================================================== */

.toast-container {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 8px;
    pointer-events: none;
}

.toast {
    padding: 12px 20px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    pointer-events: auto;
    animation: toastIn 200ms ease, toastOut 200ms ease forwards;
    animation-delay: 0s, 3s;
}

.toast-success {
    background: var(--green);
    color: #fff;
}

.toast-error {
    background: var(--red);
    color: #fff;
}

.toast-warning {
    background: var(--yellow);
    color: #000;
}

@keyframes toastIn {
    from { opacity: 0; transform: translateX(40px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes toastOut {
    from { opacity: 1; }
    to   { opacity: 0; }
}

/* ===================================================================
   Loading / Spinner
   =================================================================== */

.spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--card);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.loading-overlay {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 60px;
    color: var(--dim);
    gap: 10px;
}

/* ===================================================================
   Mobile: Hamburger + Overlay
   =================================================================== */

.mobile-header {
    display: none;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--card);
}

.mobile-header h1 {
    font-size: 16px;
    font-weight: 600;
}

.hamburger {
    background: transparent;
    color: var(--text);
    padding: 4px;
}

.hamburger svg {
    width: 24px;
    height: 24px;
}

.sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 9;
}

@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        left: 0;
        top: 0;
        bottom: 0;
        transform: translateX(-100%);
        transition: transform 200ms ease;
        z-index: 10;
    }

    .sidebar.sidebar-open {
        transform: translateX(0);
    }

    .sidebar-overlay.sidebar-open {
        display: block;
    }

    .mobile-header {
        display: flex;
    }

    .main-content {
        padding: 16px;
    }

    .card-grid {
        grid-template-columns: 1fr;
    }

    .page-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }
}

/* ===================================================================
   Utility
   =================================================================== */

.text-green { color: var(--green); }
.text-red { color: var(--red); }
.text-yellow { color: var(--yellow); }
.text-dim { color: var(--dim); }
.text-accent { color: var(--accent); }
.mono { font-family: "SF Mono", "Fira Code", "Cascadia Code", Menlo, monospace; font-size: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
</style>
</head>
<body>

<!-- Toast Container -->
<div class="toast-container" id="toast-container"></div>

<!-- Mobile Header -->
<div class="mobile-header">
    <button class="hamburger" onclick="toggleSidebar()" aria-label="Toggle menu">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
    </button>
    <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
        <rect width="32" height="32" rx="8" fill="#0EA5E9"/>
        <path d="M8 22V10l8-4 8 4v12l-8 4-8-4z" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>
        <path d="M16 14v8M12 16l4-2 4 2" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <h1>Apex Dashboard</h1>
</div>

<div class="app-layout">

    <!-- Sidebar Overlay (mobile) -->
    <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="#0EA5E9"/>
                <path d="M8 22V10l8-4 8 4v12l-8 4-8-4z" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>
                <path d="M16 14v8M12 16l4-2 4 2" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <h1>Apex Dashboard</h1>
        </div>

        <nav class="sidebar-nav">
            <!-- Health -->
            <div class="nav-item nav-active" data-page="health" onclick="navigateTo('health')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
                Health
            </div>
            <!-- Config -->
            <div class="nav-item" data-page="config" onclick="navigateTo('config')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
                </svg>
                Config
            </div>
            <!-- Future: TLS -->
            <div class="nav-item nav-disabled" title="Coming in Phase 2">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
                TLS
                <span class="nav-badge">Soon</span>
            </div>
            <!-- Future: Models -->
            <div class="nav-item nav-disabled" title="Coming in Phase 3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                    <polyline points="2 17 12 22 22 17"/>
                    <polyline points="2 12 12 17 22 12"/>
                </svg>
                Models
                <span class="nav-badge">Soon</span>
            </div>
            <!-- Future: Workspace -->
            <div class="nav-item nav-disabled" title="Coming in Phase 4">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Workspace
                <span class="nav-badge">Soon</span>
            </div>
            <!-- Future: Logs -->
            <div class="nav-item nav-disabled" title="Coming in Phase 5">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                </svg>
                Logs
                <span class="nav-badge">Soon</span>
            </div>
        </nav>

        <div class="sidebar-footer">
            Apex Server &middot; <span id="sidebar-version">v1.0</span>
        </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">

        <!-- =========================================================
             HEALTH PAGE
             ========================================================= -->
        <div class="page page-active" id="page-health">
            <div class="page-header">
                <h2>Server Health</h2>
                <div style="display:flex; align-items:center; gap:10px;">
                    <span class="text-dim" id="health-last-updated" style="font-size:12px;"></span>
                    <button class="btn btn-ghost" onclick="loadHealth()" id="btn-refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>

            <div class="card-grid">

                <!-- Server Status Card -->
                <div class="card" id="card-status">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                            <line x1="8" y1="21" x2="16" y2="21"/>
                            <line x1="12" y1="17" x2="12" y2="21"/>
                        </svg>
                        Server Status
                    </div>
                    <div id="status-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <!-- Database Card -->
                <div class="card" id="card-db">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <ellipse cx="12" cy="5" rx="9" ry="3"/>
                            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                        </svg>
                        Database
                    </div>
                    <div id="db-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <!-- TLS Certificates Card -->
                <div class="card" id="card-tls">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                        TLS Certificates
                    </div>
                    <div id="tls-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <!-- Model Health Card -->
                <div class="card" id="card-models">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                            <polyline points="2 17 12 22 22 17"/>
                            <polyline points="2 12 12 17 22 12"/>
                        </svg>
                        Model Health
                    </div>
                    <div id="models-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

            </div>
        </div>

        <!-- =========================================================
             CONFIG PAGE
             ========================================================= -->
        <div class="page" id="page-config">
            <div class="page-header">
                <h2>Configuration</h2>
            </div>
            <div id="config-content">
                <div class="loading-overlay"><div class="spinner"></div> Loading configuration...</div>
            </div>
        </div>

    </main>
</div>

<script>
/* =====================================================================
   Apex Dashboard — Client-Side Application
   ===================================================================== */

(function() {
"use strict";

/* -- Constants ------------------------------------------------------ */

const API = "/admin/api";
const REFRESH_INTERVAL = 30000;  /* 30 seconds */

let refreshTimer = null;
let currentPage = "health";

/* =====================================================================
   Navigation
   ===================================================================== */

function navigateTo(page) {
    if (page === currentPage) return;

    /* Update sidebar active state */
    document.querySelectorAll(".nav-item[data-page]").forEach(el => {
        el.classList.toggle("nav-active", el.dataset.page === page);
    });

    /* Toggle page visibility */
    document.querySelectorAll(".page").forEach(el => {
        el.classList.toggle("page-active", el.id === "page-" + page);
    });

    currentPage = page;
    window.location.hash = page;

    /* Close mobile sidebar */
    closeSidebar();

    /* Load data for the page */
    if (page === "health") {
        loadHealth();
        startAutoRefresh();
    } else {
        stopAutoRefresh();
        if (page === "config") loadConfig();
    }
}
window.navigateTo = navigateTo;

/* -- Mobile Sidebar ------------------------------------------------- */

function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("sidebar-open");
    document.getElementById("sidebar-overlay").classList.toggle("sidebar-open");
}
window.toggleSidebar = toggleSidebar;

function closeSidebar() {
    document.getElementById("sidebar").classList.remove("sidebar-open");
    document.getElementById("sidebar-overlay").classList.remove("sidebar-open");
}

/* =====================================================================
   API Helpers
   ===================================================================== */

async function apiFetch(path, options) {
    try {
        const resp = await fetch(API + path, options);
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.error || `HTTP ${resp.status}`);
        }
        return await resp.json();
    } catch (err) {
        if (err.name === "TypeError" && err.message.includes("fetch")) {
            throw new Error("Server unreachable");
        }
        throw err;
    }
}

/* =====================================================================
   Toast Notifications
   ===================================================================== */

function showToast(message, type) {
    type = type || "success";
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3500);
}

/* =====================================================================
   Health Page
   ===================================================================== */

async function loadHealth() {
    const btnRefresh = document.getElementById("btn-refresh");
    btnRefresh.disabled = true;

    try {
        /* Fetch all health endpoints in parallel */
        const [status, db, tls, models] = await Promise.allSettled([
            apiFetch("/status"),
            apiFetch("/status/db"),
            apiFetch("/status/tls"),
            apiFetch("/status/models"),
        ]);

        renderStatusCard(status);
        renderDbCard(db);
        renderTlsCard(tls);
        renderModelsCard(models);

        /* Update timestamp */
        const now = new Date();
        document.getElementById("health-last-updated").textContent =
            "Updated " + now.toLocaleTimeString();
    } catch (err) {
        showToast("Failed to load health data: " + err.message, "error");
    } finally {
        btnRefresh.disabled = false;
    }
}
window.loadHealth = loadHealth;

/* -- Render: Server Status ------------------------------------------ */

function renderStatusCard(result) {
    const el = document.getElementById("status-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not reach server");
        return;
    }

    const d = result.value;
    const running = d.status === "running" || d.status === "ok";
    const dotClass = running ? "green" : "red";

    el.innerHTML =
        '<div class="stat-row">' +
            '<span class="stat-label">Status</span>' +
            '<span class="stat-value status-inline">' +
                '<span class="status-dot ' + dotClass + '"></span>' +
                esc(running ? "Running" : (d.status || "Unknown")) +
            '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Uptime</span>' +
            '<span class="stat-value">' + formatUptime(d.uptime_seconds) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Model</span>' +
            '<span class="stat-value mono">' + esc(d.model || "—") + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Host</span>' +
            '<span class="stat-value mono">' + esc(d.host || "—") + ':' + esc(d.port || "—") + '</span>' +
        '</div>' +
        (d.active_sessions !== undefined ?
        '<div class="stat-row">' +
            '<span class="stat-label">Active Sessions</span>' +
            '<span class="stat-value">' + esc(d.active_sessions) + '</span>' +
        '</div>' : '') +
        (d.connected_clients !== undefined ?
        '<div class="stat-row">' +
            '<span class="stat-label">Connected Clients</span>' +
            '<span class="stat-value">' + esc(d.connected_clients) + '</span>' +
        '</div>' : '');
}

/* -- Render: Database ----------------------------------------------- */

function renderDbCard(result) {
    const el = document.getElementById("db-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not load DB stats");
        return;
    }

    const d = result.value;

    el.innerHTML =
        '<div class="stat-row">' +
            '<span class="stat-label">Chats</span>' +
            '<span class="stat-value">' + formatNumber(d.chats) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Messages</span>' +
            '<span class="stat-value">' + formatNumber(d.messages) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Alerts</span>' +
            '<span class="stat-value">' + formatNumber(d.alerts) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">DB Size</span>' +
            '<span class="stat-value">' + formatBytes(d.size_bytes) + '</span>' +
        '</div>';
}

/* -- Render: TLS Certificates --------------------------------------- */

function renderTlsCard(result) {
    const el = document.getElementById("tls-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not load TLS info");
        return;
    }

    const d = result.value;
    const certs = d.certificates || d;

    if (!certs || (Array.isArray(certs) && certs.length === 0)) {
        el.innerHTML = '<div class="text-dim" style="padding:8px 0;">No TLS certificates configured</div>';
        return;
    }

    /* Normalize: accept array or object with named keys */
    let certList = [];
    if (Array.isArray(certs)) {
        certList = certs;
    } else {
        for (const key of ["ca", "server", "client"]) {
            if (certs[key]) {
                certList.push(Object.assign({ name: key.charAt(0).toUpperCase() + key.slice(1) }, certs[key]));
            }
        }
    }

    let html = "";
    for (const cert of certList) {
        const days = cert.days_remaining != null ? cert.days_remaining : null;
        const color = days === null ? "dim" : (days > 30 ? "green" : (days > 7 ? "yellow" : "red"));
        const pct = days === null ? 0 : Math.max(0, Math.min(100, (days / 365) * 100));
        const label = days === null ? "Unknown" : days + "d remaining";
        const expiry = cert.expires ? " &middot; " + esc(cert.expires) : "";

        html +=
            '<div class="cert-row">' +
                '<div class="cert-label">' +
                    '<span class="cert-label-name">' + esc(cert.name || cert.type || "Cert") + '</span>' +
                    '<span class="cert-label-days text-' + color + '">' + label + expiry + '</span>' +
                '</div>' +
                '<div class="cert-bar">' +
                    '<div class="cert-bar-fill ' + color + '" style="width:' + pct + '%"></div>' +
                '</div>' +
            '</div>';
    }

    el.innerHTML = html;
}

/* -- Render: Model Health ------------------------------------------- */

function renderModelsCard(result) {
    const el = document.getElementById("models-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not check models");
        return;
    }

    const d = result.value;
    const providers = d.providers || d;

    /* Normalize: accept array or object keyed by provider name */
    let modelList = [];
    if (Array.isArray(providers)) {
        modelList = providers;
    } else {
        for (const key of Object.keys(providers)) {
            modelList.push(Object.assign({ name: key }, providers[key]));
        }
    }

    if (modelList.length === 0) {
        el.innerHTML = '<div class="text-dim" style="padding:8px 0;">No model providers configured</div>';
        return;
    }

    let html = "";
    for (const m of modelList) {
        const ok = m.status === "ok" || m.status === "reachable" || m.reachable === true;
        const dotClass = ok ? "green" : "red";
        const latency = m.latency_ms != null ? m.latency_ms + " ms" : (ok ? "OK" : "Unreachable");

        html +=
            '<div class="model-row">' +
                '<div class="model-name">' +
                    '<span class="status-dot ' + dotClass + '"></span>' +
                    esc(m.name || "Unknown") +
                '</div>' +
                '<span class="model-latency">' + esc(latency) + '</span>' +
            '</div>';
    }

    el.innerHTML = html;
}

/* =====================================================================
   Config Page
   ===================================================================== */

let configSchema = null;
let configValues = null;
let configDirty = {};  /* section -> Set of changed keys */

async function loadConfig() {
    const el = document.getElementById("config-content");
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading configuration...</div>';

    try {
        const [schemaResp, valuesResp] = await Promise.all([
            apiFetch("/config/schema"),
            apiFetch("/config"),
        ]);

        configSchema = schemaResp.schema || schemaResp;
        configValues = valuesResp.config || valuesResp;
        configDirty = {};

        renderConfigPage();
    } catch (err) {
        el.innerHTML = renderError("Failed to load configuration: " + err.message);
    }
}
window.loadConfig = loadConfig;

function renderConfigPage() {
    const el = document.getElementById("config-content");
    let html = "";

    /* Ordered sections */
    const sectionOrder = ["server", "models", "workspace", "alerts"];
    const sections = sectionOrder.filter(s => configSchema[s]);

    for (const section of sections) {
        const schema = configSchema[section];
        const values = (configValues && configValues[section]) || {};
        const isReadonly = Object.values(schema).every(spec => spec.readonly);
        const isRestartSection = (section === "server");

        html += '<div class="config-section" data-section="' + esc(section) + '">';
        html += '<div class="config-section-header">';
        html += '<span class="config-section-title">' + esc(section) + '</span>';
        if (isRestartSection) {
            html += '<span class="restart-badge" id="restart-badge-' + esc(section) + '">Restart required</span>';
        }
        html += '</div>';

        if (isReadonly) {
            /* Alerts section: read-only status indicators */
            for (const [key, spec] of Object.entries(schema)) {
                const val = values[key];
                const ok = val === true;
                const dotClass = ok ? "green" : "red";
                const label = ok ? "Configured" : "Not set";

                html +=
                    '<div class="readonly-indicator">' +
                        '<span class="status-dot ' + dotClass + '"></span>' +
                        '<span class="stat-label">' + esc(spec.description || key) + '</span>' +
                        '<span style="margin-left:auto;" class="stat-value text-' + (ok ? "green" : "dim") + '">' + label + '</span>' +
                    '</div>';
            }
        } else {
            /* Editable fields */
            for (const [key, spec] of Object.entries(schema)) {
                if (spec.readonly) continue;
                const val = values[key] != null ? values[key] : spec.default;
                html += renderFormField(section, key, spec, val);
            }

            /* Save button */
            html +=
                '<div class="config-actions">' +
                    '<button class="btn btn-primary" onclick="saveConfig(\'' + esc(section) + '\')" id="btn-save-' + esc(section) + '">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                            '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>' +
                            '<polyline points="17 21 17 13 7 13 7 21"/>' +
                            '<polyline points="7 3 7 8 15 8"/>' +
                        '</svg>' +
                        'Save ' + capitalize(section) +
                    '</button>' +
                '</div>';
        }

        html += '</div>';
    }

    el.innerHTML = html;
}

function renderFormField(section, key, spec, value) {
    const fieldId = "field-" + section + "-" + key;
    let html = '<div class="form-field">';
    html += '<label class="form-label" for="' + fieldId + '">' + esc(spec.description || key) + '</label>';

    if (spec.min != null || spec.max != null) {
        const parts = [];
        if (spec.min != null) parts.push("min: " + formatNumber(spec.min));
        if (spec.max != null) parts.push("max: " + formatNumber(spec.max));
        html += '<div class="form-help">' + parts.join(", ") + '</div>';
    }

    if (spec.type === "bool") {
        const checked = value ? "checked" : "";
        html +=
            '<div class="toggle-wrap">' +
                '<label class="toggle">' +
                    '<input type="checkbox" id="' + fieldId + '" ' + checked +
                        ' data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                        ' onchange="markDirty(\'' + esc(section) + '\', \'' + esc(key) + '\')">' +
                    '<div class="toggle-track"></div>' +
                    '<div class="toggle-knob"></div>' +
                '</label>' +
                '<span class="toggle-label">' + (value ? "Enabled" : "Disabled") + '</span>' +
            '</div>';
    } else if (spec.choices) {
        html += '<select id="' + fieldId + '" data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                ' onchange="markDirty(\'' + esc(section) + '\', \'' + esc(key) + '\')">';
        for (const choice of spec.choices) {
            const selected = (String(value) === String(choice)) ? " selected" : "";
            html += '<option value="' + esc(choice) + '"' + selected + '>' + esc(choice) + '</option>';
        }
        html += '</select>';
    } else if (spec.type === "int") {
        html += '<input type="number" id="' + fieldId + '" value="' + esc(value) + '"' +
                (spec.min != null ? ' min="' + spec.min + '"' : '') +
                (spec.max != null ? ' max="' + spec.max + '"' : '') +
                ' data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                ' onchange="markDirty(\'' + esc(section) + '\', \'' + esc(key) + '\')">';
    } else {
        html += '<input type="text" id="' + fieldId + '" value="' + esc(value) + '"' +
                ' data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                ' oninput="markDirty(\'' + esc(section) + '\', \'' + esc(key) + '\')">';
    }

    html += '</div>';
    return html;
}

function markDirty(section, key) {
    if (!configDirty[section]) configDirty[section] = new Set();
    configDirty[section].add(key);

    /* Update toggle label in real time */
    const el = document.getElementById("field-" + section + "-" + key);
    if (el && el.type === "checkbox") {
        const label = el.closest(".toggle-wrap").querySelector(".toggle-label");
        if (label) label.textContent = el.checked ? "Enabled" : "Disabled";
    }
}
window.markDirty = markDirty;

async function saveConfig(section) {
    const btn = document.getElementById("btn-save-" + section);
    if (btn) btn.disabled = true;

    /* Gather current values from the form */
    const schema = configSchema[section];
    const payload = {};

    for (const [key, spec] of Object.entries(schema)) {
        if (spec.readonly) continue;
        const el = document.getElementById("field-" + section + "-" + key);
        if (!el) continue;

        if (spec.type === "bool") {
            payload[key] = el.checked;
        } else if (spec.type === "int") {
            payload[key] = parseInt(el.value, 10);
        } else {
            payload[key] = el.value;
        }
    }

    try {
        const result = await apiFetch("/config/" + section, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        /* Update local cache */
        if (configValues) {
            configValues[section] = result.config || result.values || payload;
        }

        configDirty[section] = new Set();
        showToast(capitalize(section) + " configuration saved", "success");

        /* Show restart badge if needed */
        if (result.restart_required) {
            const badge = document.getElementById("restart-badge-" + section);
            if (badge) badge.classList.add("visible");
            showToast("Server restart required for changes to take effect", "warning");
        }
    } catch (err) {
        showToast("Save failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.saveConfig = saveConfig;

/* =====================================================================
   Auto-Refresh Timer
   ===================================================================== */

function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(function() {
        if (currentPage === "health") loadHealth();
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

/* =====================================================================
   Formatting Helpers
   ===================================================================== */

function formatUptime(seconds) {
    if (seconds == null) return "—";
    seconds = Math.floor(seconds);
    if (seconds < 60) return seconds + "s";
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    if (m < 60) return m + "m " + s + "s";
    var h = Math.floor(m / 60);
    m = m % 60;
    if (h < 24) return h + "h " + m + "m";
    var d = Math.floor(h / 24);
    h = h % 24;
    return d + "d " + h + "h " + m + "m";
}

function formatNumber(n) {
    if (n == null) return "—";
    return Number(n).toLocaleString();
}

function formatBytes(bytes) {
    if (bytes == null) return "—";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function esc(val) {
    if (val == null) return "";
    return String(val)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function renderError(message) {
    return '<div style="padding:12px 0; color:var(--red); display:flex; align-items:center; gap:8px;">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<circle cx="12" cy="12" r="10"/>' +
            '<line x1="15" y1="9" x2="9" y2="15"/>' +
            '<line x1="9" y1="9" x2="15" y2="15"/>' +
        '</svg>' +
        esc(message) +
    '</div>';
}

/* =====================================================================
   Initialization
   ===================================================================== */

function init() {
    /* Route from URL hash */
    var hash = window.location.hash.replace("#", "");
    if (hash === "config") {
        navigateTo("config");
    } else {
        /* Default: health page */
        currentPage = "health";
        loadHealth();
        startAutoRefresh();
    }

    /* Listen for hash changes (browser back/forward) */
    window.addEventListener("hashchange", function() {
        var h = window.location.hash.replace("#", "");
        if (h && h !== currentPage) navigateTo(h);
    });
}

/* Kick off */
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}

})();
</script>
</body>
</html>
"""
