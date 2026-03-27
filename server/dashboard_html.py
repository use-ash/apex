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
   Components: Workspace Page
   =================================================================== */

.ws-textarea {
    width: 100%;
    min-height: 400px;
    padding: 16px;
    font-family: "SF Mono", "Fira Code", "Cascadia Code", Menlo, monospace;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text);
    background: var(--bg);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    resize: vertical;
    outline: none;
    tab-size: 4;
    transition: border-color var(--transition);
}

.ws-textarea:focus {
    border-color: var(--accent);
}

.ws-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 8px;
    font-size: 12px;
    color: var(--dim);
}

.ws-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
}

.ws-summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
}

.ws-summary-item {
    text-align: center;
    padding: 12px;
    background: var(--bg);
    border-radius: var(--radius);
}

.ws-summary-value {
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
}

.ws-summary-label {
    font-size: 12px;
    color: var(--dim);
    margin-top: 4px;
}

.ws-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.ws-table th {
    text-align: left;
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim);
    border-bottom: 1px solid var(--card);
}

.ws-table td {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.ws-table tbody tr:hover {
    background: rgba(148, 163, 184, 0.05);
}

/* ===================================================================
   Components: Logs Page
   =================================================================== */

.log-viewer {
    background: #0F172A;
    border: 1px solid var(--card);
    border-radius: var(--radius);
    max-height: 500px;
    overflow-y: auto;
    padding: 12px 16px;
    font-family: "SF Mono", "Fira Code", "Cascadia Code", Menlo, monospace;
    font-size: 12px;
    line-height: 1.7;
    color: #B0BEC5;
    scroll-behavior: smooth;
}

.log-viewer code {
    white-space: pre-wrap;
    word-break: break-all;
}

.log-line { display: block; }
.log-line-error { color: var(--red); font-weight: 500; }
.log-line-warn { color: var(--yellow); }
.log-line-info { color: var(--green); }

.log-toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
}

.log-toolbar select,
.log-toolbar input {
    padding: 6px 10px;
    font-size: 12px;
}

.log-toolbar input[type="text"] {
    flex: 1;
    min-width: 160px;
    max-width: 300px;
}

.btn-livetail {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    border-radius: var(--radius);
    background: transparent;
    color: var(--dim);
    border: 1px solid var(--card);
    cursor: pointer;
    transition: background var(--transition), color var(--transition), border-color var(--transition);
}

.btn-livetail:hover {
    background: var(--card);
    color: var(--text);
}

.btn-livetail.active {
    background: rgba(16, 185, 129, 0.15);
    color: var(--green);
    border-color: var(--green);
}

.livetail-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--dim);
    transition: background var(--transition);
}

.btn-livetail.active .livetail-dot {
    background: var(--green);
    box-shadow: 0 0 6px var(--green);
    animation: livetailPulse 1.5s ease-in-out infinite;
}

@keyframes livetailPulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--green); }
    50% { opacity: 0.4; box-shadow: 0 0 2px var(--green); }
}

.logs-action-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.logs-action-row input[type="number"] {
    width: 70px;
    padding: 6px 10px;
    font-size: 12px;
}

.backup-list {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.backup-list th {
    text-align: left;
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim);
    border-bottom: 1px solid var(--card);
}

.backup-list td {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.backup-list tbody tr:hover {
    background: rgba(148, 163, 184, 0.05);
}

.upload-file-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 13px;
}

.upload-file-item + .upload-file-item {
    border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.skill-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
}

.skill-card {
    background: var(--bg);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.skill-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.skill-card-name {
    font-weight: 600;
    font-size: 14px;
}

.skill-card-desc {
    font-size: 12px;
    color: var(--dim);
    line-height: 1.4;
}

.btn-danger {
    background: var(--red);
    color: #fff;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 500;
}

.btn-danger:hover {
    opacity: 0.85;
}

.btn-sm {
    padding: 5px 10px;
    font-size: 12px;
}

.ws-empty {
    padding: 24px;
    text-align: center;
    color: var(--dim);
    font-size: 13px;
}

.ws-countdown {
    font-variant-numeric: tabular-nums;
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

/* ===================================================================
   Components: Modal
   =================================================================== */

.modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 100;
    align-items: center;
    justify-content: center;
}

.modal-overlay.modal-open {
    display: flex;
}

.modal-card {
    background: var(--surface);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    min-width: 400px;
    max-width: 560px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
}

.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}

.modal-header h3 {
    font-size: 16px;
    font-weight: 600;
}

.modal-close {
    background: transparent;
    color: var(--dim);
    padding: 4px;
    line-height: 1;
    font-size: 20px;
}

.modal-close:hover {
    color: var(--text);
}

/* ===================================================================
   Components: TLS Page
   =================================================================== */

.san-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: var(--card);
    border-radius: 12px;
    font-size: 12px;
    font-family: "SF Mono", "Fira Code", Menlo, monospace;
    margin: 3px;
}

.san-chip .san-remove {
    background: transparent;
    color: var(--dim);
    font-size: 14px;
    padding: 0;
    line-height: 1;
    cursor: pointer;
}

.san-chip .san-remove:hover {
    color: var(--red);
}

.tls-detail-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 16px;
    font-size: 13px;
    margin-bottom: 16px;
}

.tls-detail-grid dt {
    color: var(--dim);
    white-space: nowrap;
}

.tls-detail-grid dd {
    font-weight: 500;
    word-break: break-all;
}

.tls-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.tls-table thead th {
    text-align: left;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim);
    border-bottom: 1px solid var(--card);
}

.tls-table tbody td {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
    vertical-align: middle;
}

.tls-table tbody tr:last-child td {
    border-bottom: none;
}

.btn-danger {
    background: var(--red);
    color: #fff;
}

.btn-danger:hover {
    background: #DC2626;
}

.btn-sm {
    padding: 5px 10px;
    font-size: 12px;
}

.btn-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.san-input-row {
    display: flex;
    gap: 8px;
    margin-top: 12px;
}

.san-input-row input {
    flex: 1;
}

.san-input-row select {
    width: 100px;
}

.san-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
    min-height: 32px;
}

.modal-note {
    margin-top: 12px;
    padding: 10px 12px;
    background: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.25);
    border-radius: var(--radius);
    font-size: 12px;
    color: var(--yellow);
}

.qr-container {
    display: flex;
    justify-content: center;
    padding: 16px 0;
}

.qr-container img {
    max-width: 200px;
    border-radius: var(--radius);
    background: #fff;
    padding: 8px;
}
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
            <!-- TLS -->
            <div class="nav-item" data-page="tls" onclick="navigateTo('tls')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
                TLS
            </div>
            <!-- Models -->
            <div class="nav-item" data-page="models" onclick="navigateTo('models')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                    <polyline points="2 17 12 22 22 17"/>
                    <polyline points="2 12 12 17 22 12"/>
                </svg>
                Models
            </div>
            <!-- Workspace -->
            <div class="nav-item" data-page="workspace" onclick="navigateTo('workspace')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Workspace
            </div>
            <!-- Logs -->
            <div class="nav-item" data-page="logs" onclick="navigateTo('logs')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                </svg>
                Logs
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

        <!-- =========================================================
             TLS PAGE
             ========================================================= -->
        <div class="page" id="page-tls">
            <div class="page-header">
                <h2>TLS Certificates</h2>
                <button class="btn btn-ghost" onclick="loadTLS()" id="btn-tls-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <div class="card-grid">

                <!-- CA Certificate Card -->
                <div class="card" id="card-tls-ca">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                        CA Certificate
                    </div>
                    <div id="tls-ca-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <!-- Server Certificate Card -->
                <div class="card" id="card-tls-server">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                            <line x1="8" y1="21" x2="16" y2="21"/>
                            <line x1="12" y1="17" x2="12" y2="21"/>
                        </svg>
                        Server Certificate
                    </div>
                    <div id="tls-server-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

            </div>

            <!-- Client Certificates Table -->
            <div class="config-section" id="tls-clients-section">
                <div class="config-section-header">
                    <span class="config-section-title">Client Certificates</span>
                    <button class="btn btn-primary" onclick="openNewClientDialog()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        New Client
                    </button>
                </div>
                <div id="tls-clients-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>
        </div>

        <!-- =========================================================
             MODELS PAGE
             ========================================================= -->
        <div class="page" id="page-models">
            <div class="page-header">
                <h2>Models &amp; Credentials</h2>
                <button class="btn btn-ghost" onclick="loadModels()" id="btn-models-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <!-- Provider Status Cards -->
            <div class="card-grid" id="models-provider-cards">
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                            <polyline points="2 17 12 22 22 17"/>
                            <polyline points="2 12 12 17 22 12"/>
                        </svg>
                        Claude
                    </div>
                    <div id="provider-claude-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M8 12l2 2 4-4"/>
                        </svg>
                        Ollama
                    </div>
                    <div id="provider-ollama-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/>
                        </svg>
                        Grok
                    </div>
                    <div id="provider-grok-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6v6H9z"/></svg>
                        CODEX
                    </div>
                    <div id="provider-codex-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>
            </div>

            <!-- Default Model Selector -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Default Model</span>
                </div>
                <div class="form-field">
                    <label class="form-label" for="default-model-select">Active model for new conversations</label>
                    <div class="form-help">Select a model from any available provider</div>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <select id="default-model-select" style="width:100%; max-width:400px;">
                            <option value="">Loading models...</option>
                        </select>
                        <button class="btn btn-primary" onclick="setDefaultModel()" id="btn-set-default-model">Save</button>
                    </div>
                </div>
            </div>

            <!-- Credentials Section -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Credentials</span>
                </div>
                <table class="tls-table" id="credentials-table">
                    <thead><tr>
                        <th>Provider</th><th>Status</th><th>Action</th>
                    </tr></thead>
                    <tbody id="credentials-tbody">
                        <tr><td colspan="3"><div class="loading-overlay"><div class="spinner"></div> Loading...</div></td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Alert Configuration Section -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Alert Configuration</span>
                </div>
                <div id="alert-config-content">
                    <div class="stat-row">
                        <span class="stat-label">Telegram</span>
                        <span class="stat-value" id="alert-telegram-status">
                            <span class="status-dot dim"></span> Checking...
                        </span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Alert Token</span>
                        <span class="stat-value mono" id="alert-token-display">****</span>
                    </div>
                    <div style="margin-top:16px; display:flex; gap:8px; flex-wrap:wrap;">
                        <button class="btn btn-primary btn-sm" onclick="testAlerts()" id="btn-test-alerts">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                                <path d="M22 2L11 13"/>
                                <path d="M22 2L15 22 11 13 2 9l20-7z"/>
                            </svg>
                            Test Alerts
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="rotateAlertToken()" id="btn-rotate-token">Rotate Alert Token</button>
                    </div>
                    <div id="alert-test-result" style="display:none; margin-top:12px;"></div>
                </div>
            </div>
        </div>

        <!-- =========================================================
             WORKSPACE PAGE
             ========================================================= -->
        <div class="page" id="page-workspace">
            <div class="page-header">
                <h2>Workspace</h2>
                <button class="btn btn-ghost" onclick="loadWorkspace()" id="btn-workspace-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <!-- Workspace Summary -->
            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="16" x2="12" y2="12"/>
                        <line x1="12" y1="8" x2="12.01" y2="8"/>
                    </svg>
                    Workspace Summary
                </div>
                <div id="ws-summary-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- CLAUDE.md Editor -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">CLAUDE.md</span>
                </div>
                <textarea class="ws-textarea" id="ws-claudemd-editor" placeholder="Loading CLAUDE.md..." spellcheck="false"></textarea>
                <div class="ws-meta">
                    <span id="ws-claudemd-modified"></span>
                    <span id="ws-claudemd-status"></span>
                </div>
                <div class="ws-actions">
                    <button class="btn btn-ghost" onclick="loadClaudeMd()" id="btn-claudemd-load">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Reload
                    </button>
                    <button class="btn btn-primary" onclick="saveClaudeMd()" id="btn-claudemd-save">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
                            <polyline points="17 21 17 13 7 13 7 21"/>
                            <polyline points="7 3 7 8 15 8"/>
                        </svg>
                        Save
                    </button>
                </div>
            </div>

            <!-- Memory Files -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Memory Files</span>
                </div>
                <div id="ws-memory-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- Skills Catalog -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Skills</span>
                </div>
                <div id="ws-skills-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- Guardrail Whitelist -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Guardrail Whitelist</span>
                </div>
                <div id="ws-whitelist-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- Active Sessions -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Active Sessions</span>
                </div>
                <div id="ws-sessions-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>
        </div>

        <!-- =========================================================
             LOGS PAGE
             ========================================================= -->
        <div class="page" id="page-logs">
            <div class="page-header">
                <h2>Logs &amp; Maintenance</h2>
                <button class="btn btn-ghost" onclick="loadLogsPage()" id="btn-logs-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <!-- Log Viewer Card -->
            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    Log Viewer
                </div>
                <div class="log-toolbar">
                    <select id="log-lines-select" title="Lines to display">
                        <option value="50">50 lines</option>
                        <option value="100" selected>100 lines</option>
                        <option value="500">500 lines</option>
                        <option value="1000">1000 lines</option>
                    </select>
                    <input type="text" id="log-search-input" placeholder="Search logs...">
                    <select id="log-level-select" title="Filter by level">
                        <option value="">All Levels</option>
                        <option value="ERROR">ERROR</option>
                        <option value="WARN">WARN</option>
                        <option value="INFO">INFO</option>
                    </select>
                    <button class="btn btn-ghost" onclick="loadLogs()" style="padding:6px 12px; font-size:12px;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="btn-livetail" id="btn-livetail" onclick="toggleLiveTail()">
                        <span class="livetail-dot"></span>
                        Live Tail
                    </button>
                </div>
                <div class="log-viewer" id="log-viewer">
                    <code id="log-viewer-content">Loading logs...</code>
                </div>
                <div style="margin-top:10px; display:flex; justify-content:flex-end;">
                    <button class="btn btn-ghost" onclick="clearLogs()" style="padding:6px 12px; font-size:12px; color:var(--red);">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
                            <path d="M10 11v6"/>
                            <path d="M14 11v6"/>
                            <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
                        </svg>
                        Clear Logs
                    </button>
                </div>
            </div>

            <!-- Database Card -->
            <div class="card-grid">
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <ellipse cx="12" cy="5" rx="9" ry="3"/>
                            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                        </svg>
                        Database
                    </div>
                    <div id="db-stats-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                    <div class="logs-action-row" style="margin-top:16px; padding-top:12px; border-top:1px solid var(--card);">
                        <button class="btn btn-ghost" onclick="vacuumDb()" id="btn-vacuum" style="font-size:12px; padding:6px 12px;">Vacuum</button>
                        <button class="btn btn-ghost" onclick="exportDb()" style="font-size:12px; padding:6px 12px;">Export</button>
                        <span style="color:var(--dim); font-size:12px;">Purge older than</span>
                        <input type="number" id="purge-days-input" value="30" min="1" max="365">
                        <span style="color:var(--dim); font-size:12px;">days</span>
                        <button class="btn btn-ghost" onclick="purgeMessages()" style="font-size:12px; padding:6px 12px; color:var(--red);">Purge</button>
                    </div>
                </div>

                <!-- Uploads Card -->
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                            <polyline points="17 8 12 3 7 8"/>
                            <line x1="12" y1="3" x2="12" y2="15"/>
                        </svg>
                        Uploads
                    </div>
                    <div id="uploads-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                    <div class="logs-action-row" style="margin-top:16px; padding-top:12px; border-top:1px solid var(--card);">
                        <span style="color:var(--dim); font-size:12px;">Cleanup older than</span>
                        <input type="number" id="uploads-days-input" value="7" min="1" max="365">
                        <span style="color:var(--dim); font-size:12px;">days</span>
                        <button class="btn btn-ghost" onclick="cleanupUploads()" style="font-size:12px; padding:6px 12px; color:var(--yellow);">Cleanup</button>
                    </div>
                </div>
            </div>

            <!-- Backups Card -->
            <div class="card" style="margin-top:4px;">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
                        <polyline points="17 21 17 13 7 13 7 21"/>
                        <polyline points="7 3 7 8 15 8"/>
                    </svg>
                    Backups
                </div>
                <div style="margin-bottom:12px;">
                    <button class="btn btn-primary" onclick="createBackup()" id="btn-create-backup" style="font-size:12px; padding:6px 14px;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        Create Backup
                    </button>
                </div>
                <div id="backups-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>
        </div>

    </main>
</div>

<!-- SAN Editor Modal -->
<div class="modal-overlay" id="modal-san-editor">
    <div class="modal-card">
        <div class="modal-header">
            <h3>Edit Subject Alternative Names</h3>
            <button class="modal-close" onclick="closeModal('modal-san-editor')">&times;</button>
        </div>
        <div>
            <label class="form-label">Current SANs</label>
            <div class="san-list" id="san-list"></div>
        </div>
        <div class="san-input-row">
            <select id="san-type">
                <option value="IP">IP</option>
                <option value="DNS">DNS</option>
            </select>
            <input type="text" id="san-input" placeholder="e.g. 10.0.0.1 or myhost.local">
            <button class="btn btn-ghost" onclick="addSAN()">Add</button>
        </div>
        <div class="modal-note" id="san-note" style="display:none;">
            Server certificate renewal required for SAN changes to take effect.
        </div>
        <div class="config-actions">
            <button class="btn btn-primary" onclick="saveSANs()" id="btn-save-sans">Save SANs</button>
            <button class="btn btn-ghost" onclick="closeModal('modal-san-editor')">Cancel</button>
        </div>
    </div>
</div>

<!-- New Client Modal -->
<div class="modal-overlay" id="modal-new-client">
    <div class="modal-card">
        <div class="modal-header">
            <h3>Generate Client Certificate</h3>
            <button class="modal-close" onclick="closeModal('modal-new-client')">&times;</button>
        </div>
        <div class="form-field">
            <label class="form-label" for="new-client-cn">Device Name (CN)</label>
            <div class="form-help">Common name for the client certificate, e.g. "iphone" or "macbook"</div>
            <input type="text" id="new-client-cn" placeholder="e.g. iphone-dana" style="width:100%;">
        </div>
        <div id="new-client-result" style="display:none; margin-top:16px;"></div>
        <div class="config-actions">
            <button class="btn btn-primary" onclick="generateClient()" id="btn-generate-client">Generate</button>
            <button class="btn btn-ghost" onclick="closeModal('modal-new-client')">Cancel</button>
        </div>
    </div>
</div>

<!-- QR Code Modal -->
<div class="modal-overlay" id="modal-qr">
    <div class="modal-card">
        <div class="modal-header">
            <h3 id="qr-title">QR Code</h3>
            <button class="modal-close" onclick="closeModal('modal-qr')">&times;</button>
        </div>
        <div class="qr-container" id="qr-content">
            <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
        </div>
    </div>
</div>

<!-- Credential Update Modal -->
<div class="modal-overlay" id="modal-credential">
    <div class="modal-card">
        <div class="modal-header">
            <h3 id="credential-modal-title">Update Credential</h3>
            <button class="modal-close" onclick="closeModal('modal-credential')">&times;</button>
        </div>
        <div class="form-field">
            <label class="form-label" for="credential-input" id="credential-input-label">API Key</label>
            <div class="form-help" id="credential-input-help">Enter the new API key or secret</div>
            <input type="password" id="credential-input" placeholder="Paste new credential..." style="width:100%;">
        </div>
        <div class="config-actions">
            <button class="btn btn-primary" onclick="saveCredential()" id="btn-save-credential">Save</button>
            <button class="btn btn-ghost" onclick="closeModal('modal-credential')">Cancel</button>
        </div>
    </div>
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
        if (page === "tls") loadTLS();
        if (page === "models") loadModels();
        if (page === "workspace") loadWorkspace();
        if (page === "logs") loadLogsPage();
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
        options = options || {};
        if (!options.headers) options.headers = {};
        options.headers['X-Requested-With'] = 'XMLHttpRequest';
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
            '<span class="stat-value">' + formatNumber(d.chat_count) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Messages</span>' +
            '<span class="stat-value">' + formatNumber(d.message_count) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">Alerts</span>' +
            '<span class="stat-value">' + formatNumber(d.alert_count) + '</span>' +
        '</div>' +
        '<div class="stat-row">' +
            '<span class="stat-label">DB Size</span>' +
            '<span class="stat-value">' + formatBytes(d.file_size_bytes) + '</span>' +
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
                    '<button class="btn btn-primary" data-save-config="' + esc(section) + '" id="btn-save-' + esc(section) + '">' +
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
                        ' onchange="markDirty(this.dataset.section, this.dataset.key)">' +
                    '<div class="toggle-track"></div>' +
                    '<div class="toggle-knob"></div>' +
                '</label>' +
                '<span class="toggle-label">' + (value ? "Enabled" : "Disabled") + '</span>' +
            '</div>';
    } else if (spec.choices) {
        html += '<select id="' + fieldId + '" data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                ' onchange="markDirty(this.dataset.section, this.dataset.key)">';
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
                ' onchange="markDirty(this.dataset.section, this.dataset.key)">';
    } else {
        html += '<input type="text" id="' + fieldId + '" value="' + esc(value) + '"' +
                ' data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                ' oninput="markDirty(this.dataset.section, this.dataset.key)">';
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
   TLS Page
   ===================================================================== */

let tlsSANs = [];  /* Local SAN array for editor */

async function loadTLS() {
    const btnRefresh = document.getElementById("btn-tls-refresh");
    if (btnRefresh) btnRefresh.disabled = true;

    try {
        const [ca, server, clients, sans] = await Promise.allSettled([
            apiFetch("/tls/ca"),
            apiFetch("/tls/server"),
            apiFetch("/tls/clients"),
            apiFetch("/tls/sans"),
        ]);

        renderTlsCaCard(ca);
        renderTlsServerCard(server);
        renderTlsClientsTable(clients);

        /* Cache SANs for editor */
        if (sans.status === "fulfilled") {
            tlsSANs = (sans.value.sans || sans.value || []).slice();
        }
    } catch (err) {
        showToast("Failed to load TLS data: " + err.message, "error");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadTLS = loadTLS;

/* -- Render: CA Certificate ----------------------------------------- */

function renderCertDetails(cert) {
    let html = '<dl class="tls-detail-grid">';
    if (cert.subject) html += '<dt>Subject</dt><dd class="mono">' + esc(cert.subject) + '</dd>';
    if (cert.issuer) html += '<dt>Issuer</dt><dd class="mono">' + esc(cert.issuer) + '</dd>';
    if (cert.serial) html += '<dt>Serial</dt><dd class="mono">' + esc(cert.serial) + '</dd>';
    if (cert.fingerprint) html += '<dt>Fingerprint</dt><dd class="mono">' + esc(cert.fingerprint) + '</dd>';
    if (cert.not_before) html += '<dt>Not Before</dt><dd>' + esc(cert.not_before) + '</dd>';
    if (cert.not_after) html += '<dt>Not After</dt><dd>' + esc(cert.not_after) + '</dd>';
    html += '</dl>';
    return html;
}

function renderCertExpiryBar(cert) {
    const days = cert.days_remaining != null ? cert.days_remaining : null;
    const color = days === null ? "dim" : (days > 365 ? "green" : (days > 90 ? "yellow" : "red"));
    const maxDays = cert.total_days || 3650;  /* default 10yr for CA */
    const pct = days === null ? 0 : Math.max(0, Math.min(100, (days / maxDays) * 100));
    const label = days === null ? "Unknown" : days + " days remaining";

    return '<div class="cert-row">' +
        '<div class="cert-label">' +
            '<span class="cert-label-name">Expiry</span>' +
            '<span class="cert-label-days text-' + color + '">' + label + '</span>' +
        '</div>' +
        '<div class="cert-bar">' +
            '<div class="cert-bar-fill ' + color + '" style="width:' + pct + '%"></div>' +
        '</div>' +
    '</div>';
}

function renderTlsCaCard(result) {
    const el = document.getElementById("tls-ca-content");

    if (result.status === "rejected") {
        /* CA not found — offer to generate one */
        el.innerHTML =
            '<div class="text-dim" style="padding:8px 0;">No CA certificate found.</div>' +
            '<button class="btn btn-primary btn-sm" onclick="generateCA()" id="btn-generate-ca">Generate CA</button>';
        return;
    }

    const d = result.value;
    let html = renderCertDetails(d);
    html += renderCertExpiryBar(d);
    html += '<div style="margin-top:12px;">' +
        '<button class="btn btn-ghost btn-sm" onclick="generateCA(true)">Re-key CA</button>' +
    '</div>';
    el.innerHTML = html;
}

async function generateCA(rekey) {
    if (rekey) {
        if (!confirm("Re-keying the CA invalidates ALL existing client and server certs. Continue?")) return;
    }

    var btn = document.getElementById("btn-generate-ca");
    if (btn) btn.disabled = true;

    try {
        var body = { cn: "Apex CA", days: 3650 };
        if (rekey) body.force = true;
        await apiFetch("/tls/ca/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        showToast(rekey ? "CA re-keyed. Regenerate all certs and restart." : "CA generated. Generate server + client certs next.", "success");
        loadTLS();
    } catch (err) {
        showToast("CA generation failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.generateCA = generateCA;

/* -- Render: Server Certificate ------------------------------------- */

function renderTlsServerCard(result) {
    const el = document.getElementById("tls-server-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not load server certificate");
        return;
    }

    const d = result.value;
    let html = renderCertDetails(d);

    /* SAN chips */
    if (d.sans && d.sans.length > 0) {
        html += '<div style="margin-bottom:12px;">' +
            '<span class="stat-label" style="display:block; margin-bottom:6px;">Subject Alternative Names</span>' +
            '<div class="san-list">';
        for (const san of d.sans) {
            html += '<span class="san-chip">' + esc(san) + '</span>';
        }
        html += '</div></div>';
    }

    html += renderCertExpiryBar(d);

    /* Action buttons */
    html += '<div style="margin-top:16px; display:flex; gap:8px;">' +
        '<button class="btn btn-primary btn-sm" onclick="renewServer()">Renew</button>' +
        '<button class="btn btn-ghost btn-sm" onclick="openSANEditor()">Edit SANs</button>' +
    '</div>';

    el.innerHTML = html;
}

/* -- Render: Client Certificates Table ------------------------------ */

function renderTlsClientsTable(result) {
    const el = document.getElementById("tls-clients-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not load client certificates");
        return;
    }

    const clients = result.value.clients || result.value || [];

    if (clients.length === 0) {
        el.innerHTML = '<div class="text-dim" style="padding:8px 0;">No client certificates issued yet.</div>';
        return;
    }

    let html = '<table class="tls-table"><thead><tr>' +
        '<th>Name (CN)</th><th>Expires</th><th>Days Left</th><th>Status</th><th>Actions</th>' +
    '</tr></thead><tbody>';

    for (const c of clients) {
        const days = c.days_remaining != null ? c.days_remaining : null;
        const expired = days !== null && days <= 0;
        const warning = days !== null && days > 0 && days <= 90;
        const dotClass = expired ? "red" : (warning ? "yellow" : "green");
        const statusText = expired ? "Expired" : (warning ? "Expiring" : "Valid");

        html += '<tr>' +
            '<td class="mono">' + esc(c.cn || c.name || "—") + '</td>' +
            '<td>' + esc(c.not_after || c.expires || "—") + '</td>' +
            '<td class="text-' + dotClass + '">' + (days != null ? days : "—") + '</td>' +
            '<td><span class="status-inline"><span class="status-dot ' + dotClass + '"></span>' + statusText + '</span></td>' +
            '<td><div class="btn-row">' +
                '<button class="btn btn-ghost btn-sm" data-download-p12="' + esc(c.cn || c.name) + '" title="Download .p12">' +
                    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                        '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>' +
                        '<polyline points="7 10 12 15 17 10"/>' +
                        '<line x1="12" y1="15" x2="12" y2="3"/>' +
                    '</svg>' +
                '</button>' +
                '<button class="btn btn-ghost btn-sm" data-show-qr="' + esc(c.cn || c.name) + '" title="Show QR code">' +
                    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                        '<rect x="3" y="3" width="7" height="7"/>' +
                        '<rect x="14" y="3" width="7" height="7"/>' +
                        '<rect x="3" y="14" width="7" height="7"/>' +
                        '<rect x="14" y="14" width="3" height="3"/>' +
                        '<rect x="20" y="14" width="1" height="3"/>' +
                        '<rect x="14" y="20" width="3" height="1"/>' +
                    '</svg>' +
                '</button>' +
                '<button class="btn btn-danger btn-sm" data-revoke-client="' + esc(c.cn || c.name) + '" title="Revoke">Revoke</button>' +
            '</div></td>' +
        '</tr>';
    }

    html += '</tbody></table>';
    el.innerHTML = html;
}

/* -- TLS Actions ---------------------------------------------------- */

async function renewServer() {
    if (!confirm("Renew the server certificate? Active connections may need to reconnect.")) return;

    try {
        await apiFetch("/tls/server/renew", { method: "POST" });
        showToast("Server certificate renewed", "success");
        loadTLS();
    } catch (err) {
        showToast("Renew failed: " + err.message, "error");
    }
}
window.renewServer = renewServer;

function downloadP12(cn) {
    window.open(API + "/tls/clients/" + encodeURIComponent(cn) + "/p12", "_blank");
}
window.downloadP12 = downloadP12;

async function showQR(cn) {
    document.getElementById("qr-title").textContent = "QR Code — " + cn;
    document.getElementById("qr-content").innerHTML =
        '<div class="loading-overlay"><div class="spinner"></div> Loading...</div>';
    openModal("modal-qr");

    try {
        const resp = await fetch(API + "/tls/clients/" + encodeURIComponent(cn) + "/qr");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById("qr-content").innerHTML =
            '<img src="' + url + '" alt="QR code for ' + esc(cn) + '">';
    } catch (err) {
        document.getElementById("qr-content").innerHTML = renderError("Failed to load QR: " + err.message);
    }
}
window.showQR = showQR;

async function revokeClient(cn) {
    if (!confirm("Revoke client certificate for '" + cn + "'? This cannot be undone.")) return;

    try {
        await apiFetch("/tls/clients/" + encodeURIComponent(cn), { method: "DELETE" });
        showToast("Client '" + cn + "' revoked", "success");
        loadTLS();
    } catch (err) {
        showToast("Revoke failed: " + err.message, "error");
    }
}
window.revokeClient = revokeClient;

/* -- New Client Dialog ---------------------------------------------- */

function openNewClientDialog() {
    document.getElementById("new-client-cn").value = "";
    document.getElementById("new-client-result").style.display = "none";
    document.getElementById("new-client-result").innerHTML = "";
    document.getElementById("btn-generate-client").disabled = false;
    openModal("modal-new-client");
}
window.openNewClientDialog = openNewClientDialog;

async function generateClient() {
    const cn = document.getElementById("new-client-cn").value.trim();
    if (!cn) {
        showToast("Please enter a device name", "warning");
        return;
    }

    const btn = document.getElementById("btn-generate-client");
    btn.disabled = true;

    try {
        const result = await apiFetch("/tls/clients", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cn: cn }),
        });

        showToast("Client certificate generated for '" + cn + "'", "success");

        /* Show download + QR area */
        const resultEl = document.getElementById("new-client-result");
        let html = '<div style="padding:12px; background:var(--bg); border-radius:var(--radius);">' +
            '<div style="margin-bottom:10px; color:var(--green); font-weight:500;">Certificate generated successfully.</div>' +
            '<div class="btn-row">' +
                '<button class="btn btn-primary btn-sm" data-download-p12="' + esc(cn) + '">Download .p12</button>' +
                '<button class="btn btn-ghost btn-sm" data-show-qr="' + esc(cn) + '">Show QR Code</button>' +
            '</div>' +
        '</div>';
        resultEl.innerHTML = html;
        resultEl.style.display = "block";

        /* Refresh client list behind the modal */
        loadTLS();
    } catch (err) {
        showToast("Generate failed: " + err.message, "error");
        btn.disabled = false;
    }
}
window.generateClient = generateClient;

/* -- SAN Editor ----------------------------------------------------- */

function openSANEditor() {
    renderSANList();
    document.getElementById("san-note").style.display = "none";
    document.getElementById("san-input").value = "";
    openModal("modal-san-editor");
}
window.openSANEditor = openSANEditor;

function renderSANList() {
    const el = document.getElementById("san-list");
    if (tlsSANs.length === 0) {
        el.innerHTML = '<span class="text-dim">No SANs configured</span>';
        return;
    }
    let html = "";
    for (let i = 0; i < tlsSANs.length; i++) {
        const san = tlsSANs[i];
        const display = (typeof san === "object") ? (san.type || "IP") + ":" + san.value : san;
        html += '<span class="san-chip">' +
            esc(display) +
            '<button class="san-remove" onclick="removeSAN(' + i + ')" title="Remove">&times;</button>' +
        '</span>';
    }
    el.innerHTML = html;
}

function addSAN() {
    const typeEl = document.getElementById("san-type");
    const inputEl = document.getElementById("san-input");
    const value = inputEl.value.trim();
    if (!value) return;

    tlsSANs.push({ type: typeEl.value, value: value });
    inputEl.value = "";
    renderSANList();
}
window.addSAN = addSAN;

function removeSAN(index) {
    tlsSANs.splice(index, 1);
    renderSANList();
}
window.removeSAN = removeSAN;

async function loadSANs() {
    try {
        const result = await apiFetch("/tls/sans");
        tlsSANs = (result.sans || result || []).slice();
        renderSANList();
    } catch (err) {
        showToast("Failed to load SANs: " + err.message, "error");
    }
}
window.loadSANs = loadSANs;

async function saveSANs() {
    const btn = document.getElementById("btn-save-sans");
    btn.disabled = true;

    try {
        await apiFetch("/tls/sans", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sans: tlsSANs }),
        });
        showToast("SANs updated", "success");
        document.getElementById("san-note").style.display = "block";
        loadTLS();
    } catch (err) {
        showToast("Save SANs failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.saveSANs = saveSANs;

/* =====================================================================
   Models Page
   ===================================================================== */

let modelsData = {};     /* Cached provider data */
let credentialsData = {};  /* Cached credentials status */
let currentCredentialProvider = null;

async function loadModels() {
    const btnRefresh = document.getElementById("btn-models-refresh");
    if (btnRefresh) btnRefresh.disabled = true;

    try {
        const [claude, ollama, grok, codex, creds] = await Promise.allSettled([
            apiFetch("/models/claude"),
            apiFetch("/models/ollama"),
            apiFetch("/models/grok"),
            apiFetch("/models/codex"),
            apiFetch("/credentials"),
        ]);

        modelsData = { claude: claude, ollama: ollama, grok: grok, codex: codex };
        if (creds.status === "fulfilled") {
            credentialsData = creds.value.credentials || creds.value || {};
        }

        renderProviderCards(claude, ollama, grok, codex);
        renderDefaultModelSelector(claude, ollama, grok, codex);
        renderCredentialsTable();
        renderAlertConfig();
    } catch (err) {
        showToast("Failed to load models: " + err.message, "error");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadModels = loadModels;

/* -- Render: Provider Status Cards ---------------------------------- */

function renderProviderCards(claude, ollama, grok, codex) {
    /* Claude */
    const claudeEl = document.getElementById("provider-claude-content");
    if (claude.status === "rejected") {
        claudeEl.innerHTML = renderError("Could not reach Claude API");
    } else {
        const d = claude.value;
        const ok = d.status === "ok" || d.status === "reachable" || d.status === "configured" || d.reachable === true;
        const dotClass = ok ? "green" : "red";
        const apiKey = d.api_key_configured !== undefined ? d.api_key_configured : (credentialsData.claude || false);
        const keychain = d.keychain_fallback !== undefined ? d.keychain_fallback : null;

        claudeEl.innerHTML =
            '<div class="stat-row">' +
                '<span class="stat-label">Status</span>' +
                '<span class="stat-value status-inline">' +
                    '<span class="status-dot ' + dotClass + '"></span>' +
                    (ok ? "Reachable" : "Unreachable") +
                '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">Model</span>' +
                '<span class="stat-value mono">' + esc(d.model || d.default_model || "—") + '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">API Key</span>' +
                '<span class="stat-value text-' + (apiKey ? "green" : "red") + '">' +
                    (apiKey ? "Configured" : "Not set") +
                '</span>' +
            '</div>' +
            (keychain !== null ?
            '<div class="stat-row">' +
                '<span class="stat-label">Keychain Fallback</span>' +
                '<span class="stat-value text-' + (keychain ? "green" : "dim") + '">' +
                    (keychain ? "Available" : "Not available") +
                '</span>' +
            '</div>' : '') +
            (d.latency_ms != null ?
            '<div class="stat-row">' +
                '<span class="stat-label">Latency</span>' +
                '<span class="stat-value">' + d.latency_ms + ' ms</span>' +
            '</div>' : '');
    }

    /* Ollama */
    const ollamaEl = document.getElementById("provider-ollama-content");
    if (ollama.status === "rejected") {
        ollamaEl.innerHTML = renderError("Could not reach Ollama");
    } else {
        const d = ollama.value;
        const ok = d.status === "ok" || d.status === "reachable" || d.status === "configured" || d.reachable === true;
        const dotClass = ok ? "green" : "red";
        const modelCount = d.model_count != null ? d.model_count : (d.models ? d.models.length : null);
        const loaded = d.loaded_models || d.running || [];

        ollamaEl.innerHTML =
            '<div class="stat-row">' +
                '<span class="stat-label">Status</span>' +
                '<span class="stat-value status-inline">' +
                    '<span class="status-dot ' + dotClass + '"></span>' +
                    (ok ? "Reachable" : "Unreachable") +
                '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">URL</span>' +
                '<span class="stat-value mono">' + esc(d.url || d.base_url || "—") + '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">Models Available</span>' +
                '<span class="stat-value">' + (modelCount != null ? modelCount : "—") + '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">Currently Loaded</span>' +
                '<span class="stat-value">' +
                    (loaded.length > 0 ? loaded.map(function(m) { return '<span class="mono">' + esc(typeof m === "string" ? m : m.name || m.model) + '</span>'; }).join(", ") : '<span class="text-dim">None</span>') +
                '</span>' +
            '</div>' +
            (d.latency_ms != null ?
            '<div class="stat-row">' +
                '<span class="stat-label">Latency</span>' +
                '<span class="stat-value">' + d.latency_ms + ' ms</span>' +
            '</div>' : '');
    }

    /* Grok */
    const grokEl = document.getElementById("provider-grok-content");
    if (grok.status === "rejected") {
        grokEl.innerHTML = renderError("Could not reach Grok API");
    } else {
        const d = grok.value;
        const ok = d.status === "ok" || d.status === "reachable" || d.status === "configured" || d.reachable === true;
        const dotClass = ok ? "green" : "red";
        const apiKey = d.api_key_configured !== undefined ? d.api_key_configured : (credentialsData.grok || false);

        grokEl.innerHTML =
            '<div class="stat-row">' +
                '<span class="stat-label">Status</span>' +
                '<span class="stat-value status-inline">' +
                    '<span class="status-dot ' + dotClass + '"></span>' +
                    (ok ? "Reachable" : "Unreachable") +
                '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">Model</span>' +
                '<span class="stat-value mono">' + esc(d.model || d.default_model || "—") + '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">API Key</span>' +
                '<span class="stat-value text-' + (apiKey ? "green" : "red") + '">' +
                    (apiKey ? "Configured" : "Not set") +
                '</span>' +
            '</div>' +
            (d.latency_ms != null ?
            '<div class="stat-row">' +
                '<span class="stat-label">Latency</span>' +
                '<span class="stat-value">' + d.latency_ms + ' ms</span>' +
            '</div>' : '');
    }

    /* Codex */
    const codexEl = document.getElementById("provider-codex-content");
    if (codex.status === "rejected") {
        codexEl.innerHTML = renderError("Could not reach Codex API");
    } else {
        const d = codex.value;
        const ok = d.status === "ok" || d.status === "reachable" || d.status === "configured" || d.reachable === true;
        const dotClass = ok ? "green" : "red";
        const apiKey = d.api_key_configured !== undefined ? d.api_key_configured : (credentialsData.openai || false);
        const cliAvail = d.cli_available || false;
        const cliVer = d.cli_version || null;

        codexEl.innerHTML =
            '<div class="stat-row">' +
                '<span class="stat-label">Status</span>' +
                '<span class="stat-value status-inline">' +
                    '<span class="status-dot ' + dotClass + '"></span>' +
                    (ok ? "Configured" : "Not configured") +
                '</span>' +
            '</div>' +
            '<div class="stat-row">' +
                '<span class="stat-label">CLI</span>' +
                '<span class="stat-value text-' + (cliAvail ? "green" : "red") + '">' +
                    (cliAvail ? "Available" : "Not found") +
                '</span>' +
            '</div>' +
            (cliVer ?
            '<div class="stat-row">' +
                '<span class="stat-label">CLI Version</span>' +
                '<span class="stat-value mono">' + esc(cliVer) + '</span>' +
            '</div>' : '') +
            '<div class="stat-row">' +
                '<span class="stat-label">API Key</span>' +
                '<span class="stat-value text-' + (apiKey ? "green" : "red") + '">' +
                    (apiKey ? "Configured" : "Not set") +
                '</span>' +
            '</div>';
    }
}

/* -- Render: Default Model Selector --------------------------------- */

function renderDefaultModelSelector(claude, ollama, grok, codex) {
    const sel = document.getElementById("default-model-select");
    var options = '<option value="" disabled>Select a model...</option>';

    /* Claude models */
    if (claude.status === "fulfilled") {
        var d = claude.value;
        var models = d.models || (d.model ? [d.model] : [d.default_model].filter(Boolean));
        if (models.length > 0) {
            options += '<optgroup label="Claude">';
            for (var i = 0; i < models.length; i++) {
                var name = typeof models[i] === "string" ? models[i] : models[i].name || models[i].id;
                options += '<option value="claude:' + esc(name) + '">' + esc(name) + '</option>';
            }
            options += '</optgroup>';
        }
    }

    /* Ollama models */
    if (ollama.status === "fulfilled") {
        var od = ollama.value;
        var oModels = od.models || [];
        if (oModels.length > 0) {
            options += '<optgroup label="Ollama">';
            for (var j = 0; j < oModels.length; j++) {
                var oName = typeof oModels[j] === "string" ? oModels[j] : oModels[j].name || oModels[j].model;
                options += '<option value="ollama:' + esc(oName) + '">' + esc(oName) + '</option>';
            }
            options += '</optgroup>';
        }
    }

    /* Grok models */
    if (grok.status === "fulfilled") {
        var gd = grok.value;
        var gModels = gd.models || (gd.model ? [gd.model] : [gd.default_model].filter(Boolean));
        if (gModels.length > 0) {
            options += '<optgroup label="Grok">';
            for (var k = 0; k < gModels.length; k++) {
                var gName = typeof gModels[k] === "string" ? gModels[k] : gModels[k].name || gModels[k].id;
                options += '<option value="grok:' + esc(gName) + '">' + esc(gName) + '</option>';
            }
            options += '</optgroup>';
        }
    }

    /* Codex models */
    if (codex.status === "fulfilled") {
        var cd = codex.value;
        var cModels = cd.models || (cd.model ? [cd.model] : [cd.default_model].filter(Boolean));
        if (cModels.length > 0) {
            options += '<optgroup label="Codex">';
            for (var m = 0; m < cModels.length; m++) {
                var cName = typeof cModels[m] === "string" ? cModels[m] : cModels[m].name || cModels[m].id;
                options += '<option value="codex:' + esc(cName) + '">' + esc(cName) + '</option>';
            }
            options += '</optgroup>';
        }
    }

    sel.innerHTML = options;

    /* Highlight current default */
    var current = credentialsData.default_model || "";
    if (current) {
        sel.value = current;
    }
}

async function setDefaultModel() {
    var sel = document.getElementById("default-model-select");
    var model = sel.value;
    if (!model) {
        showToast("Please select a model", "warning");
        return;
    }

    var btn = document.getElementById("btn-set-default-model");
    btn.disabled = true;

    try {
        await apiFetch("/config/models/default", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: model }),
        });
        showToast("Default model updated to " + model, "success");
    } catch (err) {
        showToast("Failed to set default model: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.setDefaultModel = setDefaultModel;

/* -- Render: Credentials Table -------------------------------------- */

function renderCredentialsTable() {
    var tbody = document.getElementById("credentials-tbody");
    var providers = [
        { key: "anthropic", name: "Claude (Anthropic)" },
        { key: "xai", name: "Grok (xAI)" },
        { key: "openai", name: "Codex (OpenAI)" },
        { key: "telegram_bot", name: "Telegram Bot Token" },
        { key: "telegram_chat", name: "Telegram Chat ID" },
    ];

    var html = "";
    for (var i = 0; i < providers.length; i++) {
        var p = providers[i];
        var configured = credentialsData[p.key] === true || (credentialsData[p.key] && credentialsData[p.key].configured);
        var dotClass = configured ? "green" : "red";
        var statusText = configured ? "Configured" : "Not set";

        html += '<tr>' +
            '<td style="font-weight:500;">' + esc(p.name) + '</td>' +
            '<td><span class="status-inline"><span class="status-dot ' + dotClass + '"></span>' +
                '<span class="text-' + (configured ? "green" : "red") + '">' + statusText + '</span>' +
            '</span></td>' +
            '<td><button class="btn btn-ghost btn-sm" data-update-credential="' + esc(p.key) + '">Update</button></td>' +
        '</tr>';
    }

    tbody.innerHTML = html;
}

/* -- Credential Update ---------------------------------------------- */

function updateCredential(provider) {
    currentCredentialProvider = provider;
    var names = { anthropic: "Claude API Key", xai: "Grok API Key", openai: "OpenAI API Key", telegram_bot: "Telegram Bot Token", telegram_chat: "Telegram Chat ID" };
    var hints = {
        anthropic: "Starts with sk-ant-... (paste from console.anthropic.com)",
        xai: "Starts with xai-... (paste from console.x.ai)",
        openai: "Starts with sk-... (paste from platform.openai.com/api-keys)",
        telegram_bot: "Format: 123456789:ABCdef... (from @BotFather)",
        telegram_chat: "Numeric chat ID (e.g. 5072593158)"
    };
    document.getElementById("credential-modal-title").textContent = "Update " + (names[provider] || capitalize(provider));
    document.getElementById("credential-input-label").textContent = names[provider] || "Credential";
    document.getElementById("credential-input-help").textContent = hints[provider] || "Enter the new " + (names[provider] || "credential").toLowerCase();
    var input = document.getElementById("credential-input");
    input.value = "";
    input.type = provider === "telegram_chat" ? "text" : "password";
    input.autocomplete = "off";
    document.getElementById("btn-save-credential").disabled = false;
    openModal("modal-credential");
}
window.updateCredential = updateCredential;

async function saveCredential() {
    var input = document.getElementById("credential-input");
    var value = input.value.trim();
    if (!value) {
        showToast("Please enter a credential value", "warning");
        return;
    }

    var btn = document.getElementById("btn-save-credential");
    btn.disabled = true;

    try {
        await apiFetch("/credentials/" + encodeURIComponent(currentCredentialProvider), {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: value }),
        });
        showToast(capitalize(currentCredentialProvider) + " credential updated", "success");
        closeModal("modal-credential");
        loadModels();
    } catch (err) {
        showToast("Update failed: " + err.message, "error");
        btn.disabled = false;
    }
}
window.saveCredential = saveCredential;

/* -- Alert Configuration -------------------------------------------- */

function renderAlertConfig() {
    /* Telegram status */
    var telegramEl = document.getElementById("alert-telegram-status");
    var tgConfigured = credentialsData.telegram === true || (credentialsData.telegram && credentialsData.telegram.configured);
    var dotClass = tgConfigured ? "green" : "red";
    telegramEl.innerHTML =
        '<span class="status-dot ' + dotClass + '"></span>' +
        '<span class="text-' + (tgConfigured ? "green" : "red") + '">' +
            (tgConfigured ? "Configured" : "Not configured") +
        '</span>';

    /* Alert token display */
    var tokenEl = document.getElementById("alert-token-display");
    var token = credentialsData.alert_token || credentialsData.alertToken || "";
    if (token && token.length > 4) {
        tokenEl.textContent = token.substring(0, 4) + "****";
    } else if (token) {
        tokenEl.textContent = "****";
    } else {
        tokenEl.innerHTML = '<span class="text-dim">Not set</span>';
    }
}

async function rotateAlertToken() {
    if (!confirm("Rotate the alert token? All existing alert integrations will need the new token.")) return;

    var btn = document.getElementById("btn-rotate-token");
    btn.disabled = true;

    try {
        var result = await apiFetch("/credentials/alert_token/rotate", { method: "POST" });
        var newToken = result.token || result.alert_token || "";
        if (newToken) {
            var tokenEl = document.getElementById("alert-token-display");
            tokenEl.textContent = newToken;
            tokenEl.classList.add("text-accent");
            showToast("Alert token rotated. Copy the new token now — it won't be shown again.", "warning");
            setTimeout(function() {
                tokenEl.textContent = newToken.substring(0, 4) + "****";
                tokenEl.classList.remove("text-accent");
            }, 15000);
        } else {
            showToast("Alert token rotated", "success");
        }
        loadModels();
    } catch (err) {
        showToast("Rotate failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.rotateAlertToken = rotateAlertToken;

async function testAlerts() {
    var btn = document.getElementById("btn-test-alerts");
    btn.disabled = true;
    var resultEl = document.getElementById("alert-test-result");
    resultEl.style.display = "block";
    resultEl.innerHTML = '<div class="loading-overlay" style="padding:12px;"><div class="spinner"></div> Sending test alert...</div>';

    try {
        var result = await apiFetch("/alerts/test", { method: "POST" });
        var channels = result.results || result.channels || result;
        var html = '';

        if (Array.isArray(channels)) {
            for (var i = 0; i < channels.length; i++) {
                var ch = channels[i];
                var ok = ch.success || ch.status === "ok";
                var dotClass = ok ? "green" : "red";
                html +=
                    '<div class="stat-row">' +
                        '<span class="stat-label">' + esc(ch.channel || ch.name || "Channel " + (i + 1)) + '</span>' +
                        '<span class="stat-value status-inline">' +
                            '<span class="status-dot ' + dotClass + '"></span>' +
                            (ok ? "Success" : esc(ch.error || "Failed")) +
                        '</span>' +
                    '</div>';
            }
        } else if (typeof channels === "object") {
            for (var key in channels) {
                if (!channels.hasOwnProperty(key)) continue;
                var val = channels[key];
                var chOk = val === true || val.success || val.status === "ok";
                html +=
                    '<div class="stat-row">' +
                        '<span class="stat-label">' + esc(key) + '</span>' +
                        '<span class="stat-value status-inline">' +
                            '<span class="status-dot ' + (chOk ? "green" : "red") + '"></span>' +
                            (chOk ? "Success" : esc(val.error || "Failed")) +
                        '</span>' +
                    '</div>';
            }
        } else {
            html = '<div class="text-green" style="padding:4px 0;">Test alert sent successfully</div>';
        }

        resultEl.innerHTML = '<div style="background:var(--bg); border-radius:var(--radius); padding:12px;">' + html + '</div>';
        showToast("Test alert sent", "success");
    } catch (err) {
        resultEl.innerHTML = '<div style="background:var(--bg); border-radius:var(--radius); padding:12px; color:var(--red);">' +
            'Test failed: ' + esc(err.message) + '</div>';
        showToast("Test alert failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.testAlerts = testAlerts;

/* =====================================================================
   Workspace Page
   ===================================================================== */

var wsSkillsData = [];
var wsWhitelistData = [];
var wsSessionsData = [];

async function loadWorkspace() {
    var btnRefresh = document.getElementById("btn-workspace-refresh");
    if (btnRefresh) btnRefresh.disabled = true;

    try {
        var [workspace, skills, whitelist, sessions] = await Promise.allSettled([
            apiFetch("/workspace"),
            apiFetch("/skills"),
            apiFetch("/guardrails/whitelist"),
            apiFetch("/sessions"),
        ]);

        /* Summary */
        renderWsSummary(workspace);

        /* Skills */
        if (skills.status === "fulfilled") {
            wsSkillsData = skills.value.skills || skills.value || [];
            renderSkills();
        } else {
            document.getElementById("ws-skills-content").innerHTML =
                renderError("Could not load skills");
        }

        /* Whitelist */
        if (whitelist.status === "fulfilled") {
            wsWhitelistData = whitelist.value.entries || whitelist.value || [];
            renderWhitelist();
        } else {
            document.getElementById("ws-whitelist-content").innerHTML =
                renderError("Could not load whitelist");
        }

        /* Sessions */
        if (sessions.status === "fulfilled") {
            wsSessionsData = sessions.value.sessions || sessions.value || [];
            renderSessions();
        } else {
            document.getElementById("ws-sessions-content").innerHTML =
                renderError("Could not load sessions");
        }

        /* Load CLAUDE.md and memory separately */
        loadClaudeMd();
        loadMemoryFiles();
    } catch (err) {
        showToast("Failed to load workspace: " + err.message, "error");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadWorkspace = loadWorkspace;

/* -- Workspace Summary --------------------------------------------- */

function renderWsSummary(result) {
    var el = document.getElementById("ws-summary-content");

    if (result.status === "rejected") {
        el.innerHTML = renderError("Could not load workspace info");
        return;
    }

    var d = result.value;
    var path = d.workspace || d.path || d.workspace_path || "Unknown";
    var claudeMdExists = d.claude_md_exists !== false;
    var memoryCount = d.memory_file_count != null ? d.memory_file_count : "—";
    var skillsCount = d.skills_count != null ? d.skills_count : "—";

    el.innerHTML =
        '<div class="ws-summary-grid">' +
            '<div class="ws-summary-item">' +
                '<div class="ws-summary-value mono" style="font-size:13px; word-break:break-all;">' + esc(path) + '</div>' +
                '<div class="ws-summary-label">Workspace Path</div>' +
            '</div>' +
            '<div class="ws-summary-item">' +
                '<div class="ws-summary-value">' +
                    '<span class="status-dot ' + (claudeMdExists ? "green" : "red") + '"></span>' +
                    (claudeMdExists ? "Present" : "Missing") +
                '</div>' +
                '<div class="ws-summary-label">CLAUDE.md</div>' +
            '</div>' +
            '<div class="ws-summary-item">' +
                '<div class="ws-summary-value">' + esc(memoryCount) + '</div>' +
                '<div class="ws-summary-label">Memory Files</div>' +
            '</div>' +
            '<div class="ws-summary-item">' +
                '<div class="ws-summary-value">' + esc(skillsCount) + '</div>' +
                '<div class="ws-summary-label">Skills</div>' +
            '</div>' +
        '</div>';
}

/* -- CLAUDE.md Editor ---------------------------------------------- */

async function loadClaudeMd() {
    var editor = document.getElementById("ws-claudemd-editor");
    var statusEl = document.getElementById("ws-claudemd-status");
    var modifiedEl = document.getElementById("ws-claudemd-modified");

    statusEl.textContent = "Loading...";
    editor.disabled = true;

    try {
        var result = await apiFetch("/workspace/claude-md");
        editor.value = result.content || result.text || "";
        var modified = result.modified || result.last_modified || null;
        if (modified) {
            modifiedEl.textContent = "Last modified: " + new Date(modified).toLocaleString();
        } else {
            modifiedEl.textContent = "";
        }
        statusEl.textContent = "";
    } catch (err) {
        editor.value = "";
        statusEl.textContent = "Error: " + err.message;
        statusEl.style.color = "var(--red)";
    } finally {
        editor.disabled = false;
    }
}
window.loadClaudeMd = loadClaudeMd;

async function saveClaudeMd() {
    if (!confirm("This will backup and overwrite CLAUDE.md. Continue?")) return;

    var editor = document.getElementById("ws-claudemd-editor");
    var btn = document.getElementById("btn-claudemd-save");
    var statusEl = document.getElementById("ws-claudemd-status");
    btn.disabled = true;

    try {
        await apiFetch("/workspace/claude-md", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: editor.value }),
        });
        showToast("CLAUDE.md saved with backup", "success");
        statusEl.textContent = "Saved";
        statusEl.style.color = "var(--green)";
        setTimeout(function() { statusEl.textContent = ""; }, 3000);
        /* Refresh modified timestamp */
        var modifiedEl = document.getElementById("ws-claudemd-modified");
        modifiedEl.textContent = "Last modified: " + new Date().toLocaleString();
    } catch (err) {
        showToast("Save failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.saveClaudeMd = saveClaudeMd;

/* -- Memory Files -------------------------------------------------- */

async function loadMemoryFiles() {
    var el = document.getElementById("ws-memory-content");
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading...</div>';

    try {
        var result = await apiFetch("/workspace/memory");
        var files = result.files || result || [];

        if (files.length === 0) {
            el.innerHTML = '<div class="ws-empty">No memory files found.</div>';
            return;
        }

        var html = '<table class="ws-table"><thead><tr>' +
            '<th>Name</th><th>Size</th><th>Modified</th>' +
        '</tr></thead><tbody>';

        for (var i = 0; i < files.length; i++) {
            var f = files[i];
            var modified = f.modified || f.last_modified || "";
            if (modified) {
                modified = new Date(modified).toLocaleString();
            }
            html += '<tr>' +
                '<td class="mono">' + esc(f.name || f.filename || "—") + '</td>' +
                '<td>' + formatBytes(f.size || f.size_bytes || 0) + '</td>' +
                '<td class="text-dim">' + esc(modified || "—") + '</td>' +
            '</tr>';
        }

        html += '</tbody></table>';
        el.innerHTML = html;
    } catch (err) {
        el.innerHTML = renderError("Could not load memory files: " + err.message);
    }
}
window.loadMemoryFiles = loadMemoryFiles;

/* -- Skills Catalog ------------------------------------------------ */

function renderSkills() {
    var el = document.getElementById("ws-skills-content");

    if (wsSkillsData.length === 0) {
        el.innerHTML = '<div class="ws-empty">No skills registered.</div>';
        return;
    }

    var html = '<div class="skill-card-grid">';

    for (var i = 0; i < wsSkillsData.length; i++) {
        var s = wsSkillsData[i];
        var enabled = s.enabled !== false;
        var name = s.name || s.id || "Skill " + (i + 1);
        var desc = s.description || s.desc || "";

        html += '<div class="skill-card">' +
            '<div class="skill-card-header">' +
                '<span class="skill-card-name">' + esc(name) + '</span>' +
                '<label class="toggle">' +
                    '<input type="checkbox" ' + (enabled ? "checked" : "") +
                        ' data-skill-dir="' + esc(s.dir || name) + '">' +
                    '<div class="toggle-track"></div>' +
                    '<div class="toggle-knob"></div>' +
                '</label>' +
            '</div>' +
            (desc ? '<div class="skill-card-desc">' + esc(desc) + '</div>' : '') +
        '</div>';
    }

    html += '</div>';
    el.innerHTML = html;
}

async function toggleSkill(dir, enabled) {
    try {
        await apiFetch("/skills/" + encodeURIComponent(dir) + "/enabled", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: enabled }),
        });
        showToast("Skill '" + dir + "' " + (enabled ? "enabled" : "disabled"), "success");
    } catch (err) {
        showToast("Toggle failed: " + err.message, "error");
        /* Reload to reset toggle state */
        loadWorkspace();
    }
}
window.toggleSkill = toggleSkill;

/* -- Guardrail Whitelist ------------------------------------------- */

function renderWhitelist() {
    var el = document.getElementById("ws-whitelist-content");

    if (wsWhitelistData.length === 0) {
        el.innerHTML = '<div class="ws-empty">No whitelist entries.</div>';
        return;
    }

    var html = '<table class="ws-table"><thead><tr>' +
        '<th>Pattern</th><th>Expires</th><th>Actions</th>' +
    '</tr></thead><tbody>';

    var now = Date.now();
    for (var i = 0; i < wsWhitelistData.length; i++) {
        var e = wsWhitelistData[i];
        var pattern = e.pattern || e.command || e.path || "—";
        var expiresRaw = e.expires || e.expires_at || null;
        var expiresStr = "—";
        var countdown = "";

        if (expiresRaw) {
            var expiresMs = new Date(expiresRaw).getTime();
            var remaining = expiresMs - now;
            if (remaining > 0) {
                var mins = Math.floor(remaining / 60000);
                var secs = Math.floor((remaining % 60000) / 1000);
                countdown = mins + "m " + secs + "s";
                expiresStr = new Date(expiresRaw).toLocaleString();
            } else {
                expiresStr = "Expired";
                countdown = "0m 0s";
            }
        }

        var entryId = e.id || e._id || i;

        html += '<tr>' +
            '<td class="mono">' + esc(pattern) + '</td>' +
            '<td>' + esc(expiresStr) +
                (countdown ? ' <span class="ws-countdown text-dim">(' + countdown + ')</span>' : '') +
            '</td>' +
            '<td><button class="btn btn-danger btn-sm" data-delete-whitelist="' + esc(entryId) + '">Delete</button></td>' +
        '</tr>';
    }

    html += '</tbody></table>';
    el.innerHTML = html;
}

async function deleteWhitelistEntry(id) {
    if (!confirm("Delete this whitelist entry?")) return;

    try {
        await apiFetch("/guardrails/whitelist/" + encodeURIComponent(id), { method: "DELETE" });
        showToast("Whitelist entry deleted", "success");
        loadWorkspace();
    } catch (err) {
        showToast("Delete failed: " + err.message, "error");
    }
}
window.deleteWhitelistEntry = deleteWhitelistEntry;

/* -- Active Sessions ----------------------------------------------- */

function renderSessions() {
    var el = document.getElementById("ws-sessions-content");

    if (wsSessionsData.length === 0) {
        el.innerHTML = '<div class="ws-empty">No active sessions.</div>';
        return;
    }

    var html = '<table class="ws-table"><thead><tr>' +
        '<th>Chat</th><th>Session ID</th><th>Model</th><th>Actions</th>' +
    '</tr></thead><tbody>';

    for (var i = 0; i < wsSessionsData.length; i++) {
        var s = wsSessionsData[i];
        var chatName = s.chat || s.chat_title || s.chat_id || "—";
        var sessionId = s.session_id || s.id || "—";
        var truncId = String(sessionId).length > 12 ? String(sessionId).substring(0, 12) + "..." : String(sessionId);
        var model = s.model || "—";

        html += '<tr>' +
            '<td>' + esc(chatName) + '</td>' +
            '<td class="mono" title="' + esc(sessionId) + '">' + esc(truncId) + '</td>' +
            '<td class="mono">' + esc(model) + '</td>' +
            '<td><div style="display:flex; gap:6px;">' +
                '<button class="btn btn-ghost btn-sm" data-compact-session="' + esc(s.chat_id || s.id || "") + '">Compact</button>' +
                '<button class="btn btn-danger btn-sm" data-kill-session="' + esc(s.chat_id || s.id || "") + '">Kill</button>' +
            '</div></td>' +
        '</tr>';
    }

    html += '</tbody></table>';
    el.innerHTML = html;
}

async function compactSession(chatId) {
    if (!confirm("Compact session for chat '" + chatId + "'? This will summarize the conversation history.")) return;

    try {
        await apiFetch("/sessions/" + encodeURIComponent(chatId) + "/compact", { method: "POST" });
        showToast("Session compacted", "success");
        loadWorkspace();
    } catch (err) {
        showToast("Compact failed: " + err.message, "error");
    }
}
window.compactSession = compactSession;

async function killSession(chatId) {
    if (!confirm("Kill session for chat '" + chatId + "'? This will terminate the active session.")) return;

    try {
        await apiFetch("/sessions/" + encodeURIComponent(chatId), { method: "DELETE" });
        showToast("Session killed", "success");
        loadWorkspace();
    } catch (err) {
        showToast("Kill failed: " + err.message, "error");
    }
}
window.killSession = killSession;

/* -- Modal Helpers -------------------------------------------------- */

function openModal(id) {
    document.getElementById(id).classList.add("modal-open");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("modal-open");
}
window.closeModal = closeModal;

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
   Logs Page
   ===================================================================== */

var liveTailSource = null;
var liveTailActive = false;

async function loadLogsPage() {
    var btnRefresh = document.getElementById("btn-logs-refresh");
    if (btnRefresh) btnRefresh.disabled = true;

    try {
        await Promise.allSettled([
            loadLogs(),
            loadDbStats(),
            loadUploads(),
            loadBackups(),
        ]);
    } catch (err) {
        showToast("Failed to load logs page: " + err.message, "error");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadLogsPage = loadLogsPage;

async function loadLogs() {
    var lines = document.getElementById("log-lines-select").value || "100";
    var search = document.getElementById("log-search-input").value || "";
    var level = document.getElementById("log-level-select").value || "";

    var params = new URLSearchParams();
    params.set("lines", lines);
    if (search) params.set("search", search);
    if (level) params.set("level", level);

    try {
        var data = await apiFetch("/logs?" + params.toString());
        var logLines = data.lines || data.logs || [];
        renderLogLines(logLines);
    } catch (err) {
        var viewer = document.getElementById("log-viewer-content");
        viewer.innerHTML = '<span class="log-line log-line-error">Error loading logs: ' + esc(err.message) + '</span>';
    }
}
window.loadLogs = loadLogs;

function renderLogLines(lines) {
    var viewer = document.getElementById("log-viewer-content");
    if (!lines || lines.length === 0) {
        viewer.innerHTML = '<span class="log-line" style="color:var(--dim);">No log entries found.</span>';
        return;
    }
    var html = "";
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var text = typeof line === "string" ? line : (line.message || line.line || JSON.stringify(line));
        var cls = "log-line";
        var upper = text.toUpperCase();
        if (upper.indexOf("ERROR") !== -1 || upper.indexOf("CRITICAL") !== -1) {
            cls = "log-line log-line-error";
        } else if (upper.indexOf("WARN") !== -1) {
            cls = "log-line log-line-warn";
        } else {
            cls = "log-line log-line-info";
        }
        html += '<span class="' + cls + '">' + esc(text) + '</span>\\n';
    }
    viewer.innerHTML = html;
    /* Scroll to bottom */
    var container = document.getElementById("log-viewer");
    container.scrollTop = container.scrollHeight;
}

function toggleLiveTail() {
    var btn = document.getElementById("btn-livetail");
    if (liveTailActive) {
        /* Disconnect */
        if (liveTailSource) {
            liveTailSource.close();
            liveTailSource = null;
        }
        liveTailActive = false;
        btn.classList.remove("active");
        showToast("Live tail disconnected", "warning");
        return;
    }

    /* Connect SSE */
    liveTailActive = true;
    btn.classList.add("active");

    var url = API.replace("/api", "") + "/api/logs/stream";
    liveTailSource = new EventSource(url);

    liveTailSource.onmessage = function(event) {
        var viewer = document.getElementById("log-viewer-content");
        var container = document.getElementById("log-viewer");
        var text = event.data;
        var cls = "log-line";
        var upper = text.toUpperCase();
        if (upper.indexOf("ERROR") !== -1 || upper.indexOf("CRITICAL") !== -1) {
            cls = "log-line log-line-error";
        } else if (upper.indexOf("WARN") !== -1) {
            cls = "log-line log-line-warn";
        } else {
            cls = "log-line log-line-info";
        }
        viewer.innerHTML += '<span class="' + cls + '">' + esc(text) + '</span>\\n';

        /* Keep buffer trimmed to ~2000 lines */
        var spans = viewer.querySelectorAll(".log-line");
        if (spans.length > 2000) {
            for (var i = 0; i < spans.length - 2000; i++) {
                spans[i].remove();
            }
        }

        /* Auto-scroll */
        container.scrollTop = container.scrollHeight;
    };

    liveTailSource.onerror = function() {
        liveTailActive = false;
        btn.classList.remove("active");
        if (liveTailSource) {
            liveTailSource.close();
            liveTailSource = null;
        }
        showToast("Live tail connection lost", "error");
    };

    showToast("Live tail connected", "success");
}
window.toggleLiveTail = toggleLiveTail;

async function clearLogs() {
    if (!confirm("Clear all server logs? This cannot be undone.")) return;
    try {
        await apiFetch("/logs/clear", { method: "POST" });
        showToast("Logs cleared", "success");
        await loadLogs();
    } catch (err) {
        showToast("Failed to clear logs: " + err.message, "error");
    }
}
window.clearLogs = clearLogs;

/* -- Database -------------------------------------------------------- */

async function loadDbStats() {
    var container = document.getElementById("db-stats-content");
    try {
        var data = await apiFetch("/db/stats");
        var html = "";
        html += '<div class="stat-row"><span class="stat-label">File Size</span><span class="stat-value">' + formatBytes(data.db_size_bytes || data.file_size) + '</span></div>';
        if (data.page_count != null) {
            html += '<div class="stat-row"><span class="stat-label">Page Count</span><span class="stat-value">' + formatNumber(data.page_count) + '</span></div>';
        }
        html += '<div class="stat-row"><span class="stat-label">WAL Size</span><span class="stat-value">' + formatBytes(data.wal_size_bytes || data.wal_size) + '</span></div>';

        var tables = data.tables || data.row_counts || {};
        var keys = Object.keys(tables);
        for (var i = 0; i < keys.length; i++) {
            html += '<div class="stat-row"><span class="stat-label">' + esc(keys[i]) + '</span><span class="stat-value">' + formatNumber(tables[keys[i]]) + ' rows</span></div>';
        }
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = renderError("Could not load DB stats: " + err.message);
    }
}

async function vacuumDb() {
    var btn = document.getElementById("btn-vacuum");
    if (btn) btn.disabled = true;
    try {
        var data = await apiFetch("/db/vacuum", { method: "POST" });
        var before = data.before_size || data.size_before;
        var after = data.after_size || data.size_after;
        if (before && after) {
            showToast("Vacuum complete: " + formatBytes(before) + " -> " + formatBytes(after), "success");
        } else {
            showToast("Vacuum complete", "success");
        }
        await loadDbStats();
    } catch (err) {
        showToast("Vacuum failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.vacuumDb = vacuumDb;

function exportDb() {
    window.open(API + "/db/export", "_blank");
}
window.exportDb = exportDb;

async function purgeMessages() {
    var days = parseInt(document.getElementById("purge-days-input").value) || 30;
    if (!confirm("Purge messages older than " + days + " days? This cannot be undone.")) return;
    try {
        var data = await apiFetch("/db/messages?days=" + days, { method: "DELETE" });
        var count = data.deleted || data.count || 0;
        showToast("Purged " + formatNumber(count) + " messages", "success");
        await loadDbStats();
    } catch (err) {
        showToast("Purge failed: " + err.message, "error");
    }
}
window.purgeMessages = purgeMessages;

/* -- Uploads --------------------------------------------------------- */

async function loadUploads() {
    var container = document.getElementById("uploads-content");
    try {
        var data = await apiFetch("/uploads");
        var files = data.files || [];
        var totalSize = files.reduce(function(s, f) { return s + (f.size_bytes || f.size || 0); }, 0);
        var count = data.total || files.length;

        var html = '';
        html += '<div class="stat-row"><span class="stat-label">File Count</span><span class="stat-value">' + formatNumber(count) + '</span></div>';
        html += '<div class="stat-row"><span class="stat-label">Total Size</span><span class="stat-value">' + formatBytes(totalSize) + '</span></div>';

        if (files.length > 0) {
            html += '<div style="margin-top:12px; max-height:200px; overflow-y:auto;">';
            for (var i = 0; i < files.length; i++) {
                var f = files[i];
                var fname = typeof f === "string" ? f : (f.name || f.filename || "");
                var fsize = typeof f === "object" ? (f.size_bytes || f.size || 0) : 0;
                html += '<div class="upload-file-item">';
                html += '<span style="color:var(--dim); font-size:12px; font-family:monospace;">' + esc(fname) + '</span>';
                if (fsize) html += '<span style="font-size:12px; color:var(--dim);">' + formatBytes(fsize) + '</span>';
                html += '</div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = renderError("Could not load uploads: " + err.message);
    }
}

async function cleanupUploads() {
    var days = parseInt(document.getElementById("uploads-days-input").value) || 7;
    if (!confirm("Remove uploaded files older than " + days + " days?")) return;
    try {
        var data = await apiFetch("/uploads/cleanup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ days: days }),
        });
        var count = data.deleted || data.removed || 0;
        showToast("Cleaned up " + formatNumber(count) + " files", "success");
        await loadUploads();
    } catch (err) {
        showToast("Cleanup failed: " + err.message, "error");
    }
}
window.cleanupUploads = cleanupUploads;

/* -- Backups --------------------------------------------------------- */

async function loadBackups() {
    var container = document.getElementById("backups-content");
    try {
        var data = await apiFetch("/backups");
        var backups = data.backups || data.files || [];

        if (!backups || backups.length === 0) {
            container.innerHTML =
                '<div style="padding:16px 0; text-align:center; color:var(--dim); font-size:13px;">' +
                '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block; margin:0 auto 8px;">' +
                    '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>' +
                    '<polyline points="17 21 17 13 7 13 7 21"/>' +
                    '<polyline points="7 3 7 8 15 8"/>' +
                '</svg>' +
                'No backups yet. Create one above.' +
                '</div>';
            return;
        }

        var html = '<table class="backup-list"><thead><tr>' +
            '<th>Filename</th><th>Size</th><th>Date</th><th style="text-align:right;">Actions</th>' +
            '</tr></thead><tbody>';

        for (var i = 0; i < backups.length; i++) {
            var b = backups[i];
            var name = b.filename || b.name || "";
            var size = b.size_bytes || b.size || 0;
            var date = b.date || b.created || b.modified || "";

            html += '<tr>';
            html += '<td style="font-family:monospace; font-size:12px;">' + esc(name) + '</td>';
            html += '<td>' + formatBytes(size) + '</td>';
            html += '<td style="color:var(--dim); font-size:12px;">' + esc(date) + '</td>';
            html += '<td style="text-align:right;">';
            html += '<button class="btn btn-ghost" data-download-backup="' + esc(name) + '" style="font-size:11px; padding:4px 10px; margin-right:4px;">Download</button>';
            html += '<button class="btn btn-ghost" data-restore-backup="' + esc(name) + '" style="font-size:11px; padding:4px 10px; color:var(--yellow);">Restore</button>';
            html += '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = renderError("Could not load backups: " + err.message);
    }
}

async function createBackup() {
    var btn = document.getElementById("btn-create-backup");
    if (btn) btn.disabled = true;
    try {
        var data = await apiFetch("/backup", { method: "POST" });
        var name = data.filename || data.name || "backup";
        showToast("Backup created: " + name, "success");
        await loadBackups();
    } catch (err) {
        showToast("Backup failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.createBackup = createBackup;

function downloadBackup(filename) {
    window.open(API + "/backups/" + encodeURIComponent(filename), "_blank");
}
window.downloadBackup = downloadBackup;

async function restoreBackup(filename) {
    if (!confirm("This will overwrite your database, config, and SSL certs. Are you sure?")) return;
    if (!confirm("FINAL WARNING: Restoring '" + filename + "' is irreversible. Type OK to proceed.")) return;
    try {
        await apiFetch("/backup/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: filename }) });
        showToast("Restore complete. Server may restart.", "success");
    } catch (err) {
        showToast("Restore failed: " + err.message, "error");
    }
}
window.restoreBackup = restoreBackup;

/* --- Delegated event handlers (XSS-safe: no dynamic data in onclick) --- */
document.addEventListener("change", function(e) {
    if (e.target.matches("[data-skill-dir]")) {
        toggleSkill(e.target.dataset.skillDir, e.target.checked);
    }
});
document.addEventListener("click", function(e) {
    var btn;
    if ((btn = e.target.closest("[data-delete-whitelist]"))) {
        deleteWhitelistEntry(btn.dataset.deleteWhitelist);
    } else if ((btn = e.target.closest("[data-compact-session]"))) {
        compactSession(btn.dataset.compactSession);
    } else if ((btn = e.target.closest("[data-kill-session]"))) {
        killSession(btn.dataset.killSession);
    } else if ((btn = e.target.closest("[data-download-backup]"))) {
        downloadBackup(btn.dataset.downloadBackup);
    } else if ((btn = e.target.closest("[data-restore-backup]"))) {
        restoreBackup(btn.dataset.restoreBackup);
    } else if ((btn = e.target.closest("[data-download-p12]"))) {
        downloadP12(btn.dataset.downloadP12);
    } else if ((btn = e.target.closest("[data-show-qr]"))) {
        showQR(btn.dataset.showQr);
    } else if ((btn = e.target.closest("[data-revoke-client]"))) {
        revokeClient(btn.dataset.revokeClient);
    } else if ((btn = e.target.closest("[data-update-credential]"))) {
        updateCredential(btn.dataset.updateCredential);
    } else if ((btn = e.target.closest("[data-save-config]"))) {
        saveConfig(btn.dataset.saveConfig);
    }
});

/* =====================================================================
   Initialization
   ===================================================================== */

function init() {
    /* Route from URL hash */
    var hash = window.location.hash.replace("#", "");
    if (hash === "config" || hash === "tls" || hash === "models" || hash === "workspace" || hash === "logs") {
        navigateTo(hash);
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
