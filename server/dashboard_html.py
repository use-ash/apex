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
<meta name="theme-color" content="#0F172A">
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
    --soft-border: rgba(148, 163, 184, 0.1);
    --hover-subtle: rgba(148, 163, 184, 0.05);
    --log-bg: #0F172A;
    --log-text: #B0BEC5;
    --modal-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    --toast-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    --transition: 150ms ease;
    --sidebar-width: 220px;
}

body.theme-light {
    --bg: #F8FAFC;
    --surface: #FFFFFF;
    --card: #D8E1EB;
    --text: #0F172A;
    --dim: #64748B;
    --accent: #0284C7;
    --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
    --soft-border: rgba(15, 23, 42, 0.08);
    --hover-subtle: rgba(2, 132, 199, 0.08);
    --log-bg: #E2E8F0;
    --log-text: #334155;
    --modal-shadow: 0 8px 32px rgba(15, 23, 42, 0.16);
    --toast-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
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
    color: inherit;
    background: transparent;
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

.health-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 18px;
    border-radius: var(--radius);
    margin-bottom: 16px;
    font-size: 13px;
    font-weight: 500;
}

.health-banner .banner-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}

.health-banner .banner-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}

.health-banner .banner-right {
    font-size: 12px;
    color: var(--dim);
    white-space: nowrap;
}

.health-banner.banner-ok {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: var(--green);
}

.health-banner.banner-ok .banner-dot {
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
}

.health-banner.banner-warn {
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.25);
    color: var(--yellow);
}

.health-banner.banner-warn .banner-dot {
    background: var(--yellow);
    box-shadow: 0 0 8px var(--yellow);
}

.health-banner.banner-critical {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.25);
    color: var(--red);
}

.health-banner.banner-critical .banner-dot {
    background: var(--red);
    box-shadow: 0 0 8px var(--red);
}

.quick-actions {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}

.quick-action-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    background: var(--surface);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    color: var(--dim);
    font-size: 12px;
    font-weight: 500;
}

.quick-action-btn:hover {
    border-color: var(--accent);
    color: var(--text);
    background: var(--hover-subtle);
}

.quick-action-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.quick-action-btn svg {
    width: 14px;
    height: 14px;
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

.policy-secondary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-top: 16px;
}

.policy-shell {
    display: grid;
    grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
    gap: 16px;
    align-items: start;
}

.policy-stack {
    display: grid;
    gap: 16px;
}

.card {
    background: var(--surface);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
}

.card--ok { border-left: 3px solid var(--green); }
.card--warn { border-left: 3px solid var(--yellow); }
.card--critical { border-left: 3px solid var(--red); }

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

.policy-panel {
    margin: 0;
}

.policy-sidebar {
    position: sticky;
    top: 24px;
}

.policy-section-label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim);
}

.policy-level-card {
    width: 100%;
    margin: 0;
    padding: 11px 12px;
    text-align: left;
    border: 1px solid var(--card);
    background: linear-gradient(180deg, rgba(148, 163, 184, 0.04), rgba(148, 163, 184, 0.02));
    color: var(--text);
    box-shadow: none;
}

.policy-level-card:hover {
    border-color: rgba(14, 165, 233, 0.45);
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.12), rgba(14, 165, 233, 0.06));
}

.policy-level-card.active {
    border-color: var(--accent);
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.24), rgba(14, 165, 233, 0.12));
    box-shadow: 0 0 0 1px rgba(14,165,233,0.25) inset;
}

.policy-level-card strong {
    display: block;
    color: var(--text);
}

.policy-level-card .form-help {
    margin-top: 4px;
    color: var(--dim);
}

.policy-editor-shell {
    display: grid;
    gap: 12px;
}

.policy-editor-actions {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
}

.policy-mini-card {
    margin: 0;
    padding: 14px;
}

.policy-mini-card textarea {
    min-height: 160px;
}

.policy-table-wrap {
    overflow: auto;
    border: 1px solid var(--soft-border);
    border-radius: var(--radius);
    background: rgba(15, 23, 42, 0.14);
}

.policy-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.policy-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: rgba(15, 23, 42, 0.98);
    backdrop-filter: blur(4px);
}

.policy-table tbody tr:hover {
    background: rgba(148, 163, 184, 0.04);
}

.stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
}

.stat-row + .stat-row {
    border-top: 1px solid var(--soft-border);
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

.persona-guidance-card {
    margin-bottom: 16px;
    padding: 14px 16px;
    background: var(--card);
    border-left: 3px solid var(--accent);
    border-radius: 10px;
}

.persona-guidance-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
}

.persona-guidance-card[data-collapsed="true"] .persona-guidance-header {
    margin-bottom: 0;
}

.persona-guidance-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
}

.persona-guidance-toggle {
    padding: 0;
    background: transparent;
    color: var(--dim);
    border: none;
    border-radius: 0;
    font-size: 14px;
    line-height: 1;
}

.persona-guidance-summary,
.persona-guidance-copy {
    font-size: 13px;
    color: var(--dim);
    line-height: 1.55;
}

.persona-guidance-card[data-collapsed="true"] .persona-guidance-copy {
    display: none;
}

.persona-guidance-card[data-collapsed="false"] .persona-guidance-summary {
    display: none;
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
    border-top: 1px solid var(--soft-border);
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
    box-shadow: var(--toast-shadow);
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

    .policy-shell {
        grid-template-columns: 1fr;
    }

    .policy-sidebar {
        position: static;
    }

    .policy-secondary-grid {
        grid-template-columns: 1fr;
    }

    .page-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }

    .health-banner {
        flex-direction: column;
        align-items: flex-start;
    }

    .health-banner .banner-right {
        white-space: normal;
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
    border-bottom: 1px solid var(--soft-border);
}

.ws-table tbody tr:hover {
    background: var(--hover-subtle);
}

/* ===================================================================
   Components: Logs Page
   =================================================================== */

.log-viewer {
    background: var(--log-bg);
    border: 1px solid var(--card);
    border-radius: var(--radius);
    max-height: 500px;
    overflow-y: auto;
    padding: 12px 16px;
    font-family: "SF Mono", "Fira Code", "Cascadia Code", Menlo, monospace;
    font-size: 12px;
    line-height: 1.7;
    color: var(--log-text);
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
    border-bottom: 1px solid var(--soft-border);
}

.backup-list tbody tr:hover {
    background: var(--hover-subtle);
}

.upload-file-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 13px;
}

.upload-file-item + .upload-file-item {
    border-top: 1px solid var(--soft-border);
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
    box-shadow: var(--modal-shadow);
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
    border-bottom: 1px solid var(--soft-border);
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
.mcp-preset-card {
    padding: 10px 12px;
    border: 1px solid var(--card);
    border-radius: 8px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: border-color .15s;
}
.mcp-preset-card:hover {
    border-color: var(--accent);
}
</style>
</head>
<body>

<!-- Toast Container -->
<div class="toast-container" id="toast-container"></div>

<!-- Mobile Header -->
<div class="mobile-header">
    <button class="hamburger" id="btn-menu-hamburger" aria-label="Toggle menu">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
    </button>
    <svg width="22" height="22" viewBox="0 0 140 140" fill="none">
        <path d="M70 14 L118 38 L118 86 L70 126 L22 86 L22 38 Z" stroke="#38bdf8" stroke-width="2.5" opacity="0.45"/>
        <line x1="34" y1="92" x2="70" y2="42" stroke="#2dd4bf" stroke-width="2" opacity="0.6"/>
        <line x1="70" y1="110" x2="70" y2="42" stroke="#38bdf8" stroke-width="2" opacity="0.6"/>
        <line x1="106" y1="92" x2="70" y2="42" stroke="#818cf8" stroke-width="2" opacity="0.6"/>
        <circle cx="70" cy="42" r="10" fill="#38bdf8"/>
        <circle cx="70" cy="42" r="4" fill="#0a0e17"/>
        <circle cx="34" cy="92" r="4" fill="#2dd4bf" opacity="0.85"/>
        <circle cx="106" cy="92" r="4" fill="#818cf8" opacity="0.85"/>
    </svg>
    <h1>Apex Dashboard</h1>
</div>

<div class="app-layout">

    <!-- Sidebar Overlay (mobile) -->
    <div class="sidebar-overlay" id="sidebar-overlay"></div>

    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <svg width="28" height="28" viewBox="0 0 140 140" fill="none">
                <path d="M70 14 L118 38 L118 86 L70 126 L22 86 L22 38 Z" stroke="#38bdf8" stroke-width="2.5" opacity="0.45"/>
                <line x1="34" y1="92" x2="70" y2="42" stroke="#2dd4bf" stroke-width="2" opacity="0.6"/>
                <line x1="70" y1="110" x2="70" y2="42" stroke="#38bdf8" stroke-width="2" opacity="0.6"/>
                <line x1="106" y1="92" x2="70" y2="42" stroke="#818cf8" stroke-width="2" opacity="0.6"/>
                <circle cx="70" cy="42" r="10" fill="#38bdf8"/>
                <circle cx="70" cy="42" r="4" fill="#0a0e17"/>
                <circle cx="34" cy="92" r="4" fill="#2dd4bf" opacity="0.85"/>
                <circle cx="106" cy="92" r="4" fill="#818cf8" opacity="0.85"/>
            </svg>
            <h1>Apex Dashboard</h1>
        </div>

        <nav class="sidebar-nav">
            <!-- Health -->
            <div class="nav-item nav-active" data-page="health">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
                Health
            </div>
            <!-- Config -->
            <div class="nav-item" data-page="config">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
                </svg>
                Config
            </div>
            <!-- TLS -->
            <div class="nav-item" data-page="tls">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
                TLS
            </div>
            <!-- Models -->
            <div class="nav-item" data-page="models">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                    <polyline points="2 17 12 22 22 17"/>
                    <polyline points="2 12 12 17 22 12"/>
                </svg>
                Models
            </div>
            <!-- Personas -->
            <div class="nav-item" data-page="personas">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
                Personas
            </div>
            <!-- Policy -->
            <div class="nav-item" data-page="policy">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 12l2 2 4-4"/>
                    <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z"/>
                </svg>
                Policy
            </div>
            <!-- Workspace -->
            <div class="nav-item" data-page="workspace">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Workspace
            </div>
            <!-- Logs -->
            <div class="nav-item" data-page="logs">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                </svg>
                Logs
            </div>
            <!-- License -->
            <div class="nav-item" data-page="license">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                License
            </div>
        </nav>

        <div class="sidebar-footer">
            Apex Server &middot; <span id="sidebar-version">{{APP_VERSION}}</span>
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
                    <button class="btn btn-ghost" id="btn-refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>

            <div class="health-banner banner-ok" id="health-banner">
                <div class="banner-left">
                    <span class="banner-dot"></span>
                    <span id="health-banner-text">Loading health summary...</span>
                </div>
                <div class="banner-right" id="health-banner-meta">Auto-refresh every 30s</div>
            </div>

            <div class="quick-actions" aria-label="Quick actions">
                <button class="quick-action-btn" id="btn-quick-test-alerts">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 2L11 13"/>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                    Test Alerts
                </button>
                <button class="quick-action-btn" id="btn-quick-backup">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="17 8 12 3 7 8"/>
                        <line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                    Backup Now
                </button>
                <button class="quick-action-btn" id="btn-quick-logs">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                    View Logs
                </button>
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
                <button class="btn btn-ghost" id="btn-tls-refresh">
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
                    <button class="btn btn-primary" id="btn-new-client">
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
                <button class="btn btn-ghost" id="btn-models-refresh">
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
                        <button class="btn btn-primary" id="btn-set-default-model">Save</button>
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
                    <div class="form-field" style="margin-top:16px;">
                        <label class="form-label" for="alert-telegram-bot-input">Telegram Bot Token</label>
                        <div class="form-help">Paste the bot token from @BotFather</div>
                        <input type="password" id="alert-telegram-bot-input" placeholder="123456789:ABCdef..." autocomplete="off">
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="alert-telegram-chat-input">Telegram Chat ID</label>
                        <div class="form-help">Numeric chat ID for alert delivery</div>
                        <input type="text" id="alert-telegram-chat-input" placeholder="5072593158" autocomplete="off">
                    </div>
                    <div style="margin-top:16px; display:flex; gap:8px; flex-wrap:wrap;">
                        <button class="btn btn-primary btn-sm" id="btn-save-telegram-config">Save Telegram Config</button>
                        <button class="btn btn-primary btn-sm" id="btn-test-alerts">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                                <path d="M22 2L11 13"/>
                                <path d="M22 2L15 22 11 13 2 9l20-7z"/>
                            </svg>
                            Test Alerts
                        </button>
                        <button class="btn btn-ghost btn-sm" id="btn-rotate-token">Rotate Alert Token</button>
                    </div>
                    <div id="alert-test-result" style="display:none; margin-top:12px;"></div>
                </div>
            </div>
        </div>

        <!-- =========================================================
             WORKSPACE PAGE
             ========================================================= -->
        <!-- =========================================================
             PERSONAS PAGE
             ========================================================= -->
        <div class="page" id="page-personas">
            <div class="page-header">
                <h2>Personas &amp; Overrides</h2>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-ghost" id="btn-personas-refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="btn btn-primary" id="btn-personas-new">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        New Persona
                    </button>
                </div>
            </div>

            <div class="card-grid" style="grid-template-columns:minmax(280px, 360px) minmax(0, 1fr); align-items:start;">
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                            <circle cx="12" cy="7" r="4"/>
                        </svg>
                        Installed Personas
                    </div>
                    <div class="form-help" style="margin-bottom:12px;">Profiles are served from the main chat app API. Effective model reflects any active override.</div>
                    <div id="personas-list-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading personas...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 20h9"/>
                            <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/>
                        </svg>
                        Persona Editor
                    </div>
                    <div id="persona-editor-meta" class="form-help" style="margin-bottom:12px;">Select a persona to edit, or create a new one.</div>

                    <div class="form-field">
                        <label class="form-label" for="persona-name">Name</label>
                        <input id="persona-name" type="text" placeholder="Research Assistant">
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="persona-slug">Slug</label>
                        <input id="persona-slug" type="text" placeholder="research-assistant">
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="persona-avatar">Avatar</label>
                        <input id="persona-avatar" type="text" placeholder="🧠">
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="persona-role">Role Description</label>
                        <input id="persona-role" type="text" placeholder="Deep research and synthesis">
                    </div>

                    <div class="persona-guidance-card" id="persona-guidance-card" data-collapsed="false">
                        <div class="persona-guidance-header">
                            <div class="persona-guidance-title">What makes a good persona?</div>
                            <button class="persona-guidance-toggle" id="btn-persona-guidance-toggle" type="button" aria-expanded="true" aria-label="Collapse persona guidance">▾</button>
                        </div>
                        <div class="persona-guidance-summary">A clear role, defined tone, and boundaries matter most. The system prompt below is where the personality lives.</div>
                        <div class="persona-guidance-copy">A strong persona has three things: a clear role ("You are a..."), a defined tone (formal, casual, terse), and boundaries (what to do, what to avoid). The system prompt below is where the personality lives - everything else on this form is metadata.</div>
                    </div>

                    <div class="card-grid" style="grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 8px;">
                        <div class="form-field" style="margin-bottom:0;">
                            <label class="form-label" for="persona-model">Base Model</label>
                            <select id="persona-model"></select>
                            <div class="form-help">Used by default when no override is set.</div>
                        </div>
                        <div class="form-field" style="margin-bottom:0;">
                            <label class="form-label" for="persona-override-model">Override Model</label>
                            <select id="persona-override-model"></select>
                            <div class="form-help">Optional admin override layered on top of the base model.</div>
                        </div>
                    </div>

                    <div class="form-field">
                        <label class="form-label" for="persona-tool-policy">Default Tool Policy</label>
                        <select id="persona-tool-policy"></select>
                        <div class="form-help">Default permission level for this persona. Temporary elevations belong on the Policy page.</div>
                    </div>
                    <div class="form-field">
                        <label class="form-label" for="persona-system-prompt">System Prompt</label>
                        <textarea id="persona-system-prompt" placeholder="You are a [role/title] who specializes in [domain or skill].&#10;&#10;Your tone is [e.g. direct, warm, technical, casual]. When responding:&#10;- Always [key behavior, e.g. &quot;cite sources&quot;, &quot;think step-by-step&quot;, &quot;ask clarifying questions&quot;]&#10;- Always [second behavior]&#10;- Never [anti-behavior, e.g. &quot;make assumptions&quot;, &quot;use jargon without explaining it&quot;]&#10;&#10;When you don't know something, [what to do - e.g. &quot;say so directly&quot;, &quot;suggest where to look&quot;]." style="width:100%; min-height:220px; resize:vertical; font-family:inherit; font-size:13px; color:var(--text); background:var(--bg); border:1px solid var(--card); border-radius:var(--radius); padding:10px 12px; outline:none;"></textarea>
                        <div class="form-help" id="persona-prompt-help">Prompt used for this persona.</div>
                    </div>
                    <div class="form-field">
                        <label class="form-label" style="display:flex; align-items:center; gap:8px;">
                            <input id="persona-is-default" type="checkbox" style="width:auto; padding:0;">
                            Mark as default persona
                        </label>
                    </div>

                    <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:16px;">
                        <button class="btn btn-primary" id="btn-persona-save">Save Persona</button>
                        <button class="btn btn-ghost" id="btn-persona-reset-form">Reset</button>
                        <button class="btn btn-ghost" id="btn-persona-reset-prompt" style="display:none;">Reset Prompt to Default</button>
                        <button class="btn btn-ghost" id="btn-persona-delete" style="color:var(--red); margin-left:auto;" disabled>Delete</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="page" id="page-policy">
            <div class="page-header">
                <h2>Policy</h2>
                <button class="btn btn-ghost" id="btn-policy-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <div class="policy-shell">
                <div class="card policy-sidebar">
                    <div class="policy-section-label">Levels</div>
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 12l2 2 4-4"/>
                            <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z"/>
                        </svg>
                        Permission Levels
                    </div>
                    <div class="form-help" style="margin-bottom:12px;">Default persona levels and temporary elevation live here. Direct-chat overrides still belong in the chat UI.</div>
                    <div id="policy-level-guide" style="display:grid; gap:8px;">
                        <div class="loading-overlay"><div class="spinner"></div> Loading policy levels...</div>
                    </div>
                    <div id="policy-level-detail" class="card" style="margin-top:12px; padding:14px;"></div>
                </div>

                <div class="policy-stack">
                    <div class="card policy-panel">
                        <div class="policy-section-label">Persona Defaults</div>
                        <div class="card-title">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                                <circle cx="12" cy="7" r="4"/>
                            </svg>
                            Persona Policies
                        </div>
                        <div class="form-help" style="margin-bottom:12px;">Set default permission levels per persona and issue temporary elevations when needed.</div>
                        <div id="policy-page-status" class="form-help" style="margin-bottom:12px;"></div>
                        <div id="policy-page-content">
                            <div class="loading-overlay"><div class="spinner"></div> Loading persona policies...</div>
                        </div>
                    </div>

                    <div class="policy-secondary-grid">
                        <div class="card policy-panel">
                            <div class="policy-section-label">System Floor</div>
                            <div class="card-title" style="margin-bottom:8px;">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-4z"/>
                                    <path d="M9 12l2 2 4-4"/>
                                </svg>
                                System Guardrails
                            </div>
                            <div class="form-help" style="margin-bottom:10px;">These rules sit above persona and chat permissions. Use them for commands or directories the system should never touch.</div>
                            <div id="policy-guardrails-status" class="form-help" style="margin-bottom:10px;"></div>
                            <div id="policy-guardrails-content">
                                <div class="loading-overlay"><div class="spinner"></div> Loading guardrails...</div>
                            </div>
                        </div>

                        <div class="card policy-panel">
                            <div class="policy-section-label">Level 2 Set</div>
                            <div class="card-title" style="margin-bottom:8px;">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <rect x="3" y="5" width="18" height="14" rx="2"/>
                                    <path d="M7 9h10"/>
                                    <path d="M7 13h6"/>
                                </svg>
                                Workspace + Browser Tool Set
                            </div>
                            <div class="form-help" style="margin-bottom:10px;">Level 2 uses this normalized tool list. Groups are collapsible so read, write, browser, network, memory, and shell controls are easier to scan.</div>
                            <div id="policy-workspace-tools-status" class="form-help" style="margin-bottom:10px;"></div>
                            <div id="policy-workspace-tools-content">
                                <div class="loading-overlay"><div class="spinner"></div> Loading workspace tool set...</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="page" id="page-workspace">
            <div class="page-header">
                <h2>Workspace</h2>
                <button class="btn btn-ghost" id="btn-workspace-refresh">
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

            <!-- Project Instructions (APEX.md) Editor -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Project Instructions (APEX.md)</span>
                </div>
                <textarea class="ws-textarea" id="ws-projectmd-editor" placeholder="Loading project instructions..." spellcheck="false"></textarea>
                <div class="ws-meta">
                    <span id="ws-projectmd-modified"></span>
                    <span id="ws-projectmd-status"></span>
                </div>
                <div class="ws-actions">
                    <button class="btn btn-ghost" id="btn-projectmd-load">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Reload
                    </button>
                    <button class="btn btn-primary" id="btn-projectmd-save">
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

            <!-- MCP Servers -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">MCP Servers</span>
                    <button class="btn btn-ghost" id="btn-mcp-add" style="padding:4px 10px; font-size:12px;">+ Add Server</button>
                </div>
                <div id="ws-mcp-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
                <!-- MCP Catalog Modal (hidden) -->
                <div id="mcp-catalog-overlay" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.55); z-index:1000; align-items:center; justify-content:center;">
                <div style="background:var(--bg); border:1px solid var(--card); border-radius:12px; width:580px; max-height:80vh; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 20px 60px rgba(0,0,0,.4);">
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:16px 20px; border-bottom:1px solid var(--card);">
                        <div>
                            <div style="font-size:15px; font-weight:600; color:var(--text);">Add MCP Server</div>
                            <div style="font-size:12px; color:var(--dim); margin-top:2px;">Choose a server to extend your agents with new tools</div>
                        </div>
                        <button id="mcp-catalog-close" style="background:none; border:none; color:var(--dim); font-size:20px; cursor:pointer; padding:4px 8px;">&times;</button>
                    </div>
                    <div style="padding:12px 20px 8px;">
                        <input id="mcp-catalog-search" type="text" placeholder="Search servers..." style="width:100%; padding:6px 10px; background:var(--surface); border:1px solid var(--card); border-radius:6px; color:var(--text); font-size:13px; outline:none;">
                    </div>
                    <div id="mcp-catalog-body" style="overflow-y:auto; padding:4px 20px 16px; flex:1;"></div>
                    <div style="border-top:1px solid var(--card); padding:12px 20px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:12px; color:var(--dim);">Need something else?</span>
                        <button id="mcp-catalog-custom" class="btn btn-ghost" style="padding:4px 12px; font-size:12px;">Custom Server...</button>
                    </div>
                </div>
                </div>
                <!-- MCP Add/Edit Form (hidden by default) -->
                <div id="mcp-add-form" style="display:none; padding:12px; border-top:1px solid var(--card);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-size:12px; font-weight:600; color:var(--text);" id="mcp-form-title">Custom Server</span>
                        <button class="btn btn-ghost" id="btn-mcp-back-catalog" style="padding:2px 8px; font-size:11px; display:none;">&#8592; Back to Catalog</button>
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
                        <div>
                            <label style="font-size:11px; color:var(--dim);">Name</label>
                            <input id="mcp-name" type="text" placeholder="my-server" style="width:100%; padding:4px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text); font-size:13px;">
                        </div>
                        <div>
                            <label style="font-size:11px; color:var(--dim);">Type</label>
                            <select id="mcp-type" style="width:100%; padding:4px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text); font-size:13px;">
                                <option value="stdio">stdio</option>
                                <option value="sse">sse</option>
                                <option value="http">http</option>
                            </select>
                        </div>
                    </div>
                    <div id="mcp-stdio-fields">
                        <div style="margin-bottom:8px;">
                            <label style="font-size:11px; color:var(--dim);">Command</label>
                            <input id="mcp-command" type="text" placeholder="npx -y @modelcontextprotocol/server-filesystem /tmp" style="width:100%; padding:4px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text); font-size:13px;">
                        </div>
                    </div>
                    <div id="mcp-url-fields" style="display:none;">
                        <div style="margin-bottom:8px;">
                            <label style="font-size:11px; color:var(--dim);">URL</label>
                            <input id="mcp-url" type="text" placeholder="http://localhost:3000/sse" style="width:100%; padding:4px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text); font-size:13px;">
                        </div>
                    </div>
                    <div id="mcp-env-fields" style="display:none; margin-bottom:8px;">
                        <label style="font-size:11px; color:var(--dim);">Environment Variables</label>
                        <div id="mcp-env-list"></div>
                    </div>
                    <div style="display:flex; gap:8px; justify-content:flex-end;">
                        <button class="btn btn-ghost" id="btn-mcp-cancel" style="padding:4px 12px; font-size:12px;">Cancel</button>
                        <button class="btn" id="btn-mcp-save" style="padding:4px 12px; font-size:12px; background:var(--accent); color:#fff;">Save</button>
                    </div>
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
                <button class="btn btn-ghost" id="btn-logs-refresh">
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
                    <button class="btn btn-ghost" id="btn-logs-load" style="padding:6px 12px; font-size:12px;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="btn-livetail" id="btn-livetail">
                        <span class="livetail-dot"></span>
                        Live Tail
                    </button>
                </div>
                <div class="log-viewer" id="log-viewer">
                    <code id="log-viewer-content">Loading logs...</code>
                </div>
                <div style="margin-top:10px; display:flex; justify-content:flex-end;">
                    <button class="btn btn-ghost" id="btn-clear-logs" style="padding:6px 12px; font-size:12px; color:var(--red);">
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
                        <button class="btn btn-ghost" id="btn-vacuum" style="font-size:12px; padding:6px 12px;">Vacuum</button>
                        <button class="btn btn-ghost" id="btn-export-db" style="font-size:12px; padding:6px 12px;">Export</button>
                        <span style="color:var(--dim); font-size:12px;">Purge older than</span>
                        <input type="number" id="purge-days-input" value="30" min="1" max="365">
                        <span style="color:var(--dim); font-size:12px;">days</span>
                        <button class="btn btn-ghost" id="btn-purge-messages" style="font-size:12px; padding:6px 12px; color:var(--red);">Purge</button>
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
                        <button class="btn btn-ghost" id="btn-cleanup-uploads" style="font-size:12px; padding:6px 12px; color:var(--yellow);">Cleanup</button>
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
                    <button class="btn btn-primary" id="btn-create-backup" style="font-size:12px; padding:6px 14px;">
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

        <!-- =========================================================
             LICENSE PAGE
             ========================================================= -->
        <div class="page" id="page-license">
            <div class="page-header">
                <h2>License</h2>
            </div>

            <div id="license-status-banner" class="health-banner banner-ok" style="margin-bottom:20px">
                <div class="banner-left">
                    <span class="banner-dot"></span>
                    <span id="license-status-text">Loading...</span>
                </div>
                <div class="banner-right" id="license-status-meta"></div>
            </div>

            <div class="config-section" id="license-details-section">
                <div class="config-section-header">
                    <span class="config-section-title">License Details</span>
                </div>
                <div id="license-details" style="padding:16px">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <div class="config-section" id="license-activate-section">
                <div class="config-section-header">
                    <span class="config-section-title">Activate License</span>
                </div>
                <div style="padding:16px">
                    <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
                        Paste your license key below. You receive this after purchasing at
                        <a href="https://use-ash.com" target="_blank" style="color:var(--accent)">use-ash.com</a>.
                    </p>
                    <textarea id="license-key-input" rows="6"
                        style="width:100%;background:var(--surface);color:var(--text);border:1px solid var(--card);border-radius:8px;padding:12px;font-family:'SF Mono','JetBrains Mono',monospace;font-size:11px;resize:vertical"
                        placeholder='Paste your license JSON here...'></textarea>
                    <div style="display:flex;gap:8px;margin-top:10px">
                        <button class="btn btn-primary" id="btn-activate-license">Activate</button>
                    </div>
                    <div id="license-activate-result" style="margin-top:10px;font-size:13px"></div>
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
            <button class="modal-close" data-close-modal="modal-san-editor">&times;</button>
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
            <button class="btn btn-ghost" id="btn-add-san">Add</button>
        </div>
        <div class="modal-note" id="san-note" style="display:none;">
            Server certificate renewal required for SAN changes to take effect.
        </div>
        <div class="config-actions">
            <button class="btn btn-primary" id="btn-save-sans">Save SANs</button>
            <button class="btn btn-ghost" data-close-modal="modal-san-editor">Cancel</button>
        </div>
    </div>
</div>

<!-- New Client Modal -->
<div class="modal-overlay" id="modal-new-client">
    <div class="modal-card">
        <div class="modal-header">
            <h3>Generate Client Certificate</h3>
            <button class="modal-close" data-close-modal="modal-new-client">&times;</button>
        </div>
        <div class="form-field">
            <label class="form-label" for="new-client-cn">Device Name (CN)</label>
            <div class="form-help">Common name for the client certificate, e.g. "iphone" or "macbook"</div>
            <input type="text" id="new-client-cn" placeholder="e.g. my-iphone" style="width:100%;">
        </div>
        <div id="new-client-result" style="display:none; margin-top:16px;"></div>
        <div class="config-actions">
            <button class="btn btn-primary" id="btn-generate-client">Generate</button>
            <button class="btn btn-ghost" data-close-modal="modal-new-client">Cancel</button>
        </div>
    </div>
</div>

<!-- QR Code Modal -->
<div class="modal-overlay" id="modal-qr">
    <div class="modal-card">
        <div class="modal-header">
            <h3 id="qr-title">QR Code</h3>
            <button class="modal-close" data-close-modal="modal-qr">&times;</button>
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
            <button class="modal-close" data-close-modal="modal-credential">&times;</button>
        </div>
        <div class="form-field">
            <label class="form-label" for="credential-input" id="credential-input-label">API Key</label>
            <div class="form-help" id="credential-input-help">Enter the new API key or secret</div>
            <input type="password" id="credential-input" placeholder="Paste new credential..." style="width:100%;">
        </div>
        <div class="config-actions">
            <button class="btn btn-primary" id="btn-save-credential">Save</button>
            <button class="btn btn-ghost" data-close-modal="modal-credential">Cancel</button>
        </div>
    </div>
</div>

<script nonce="{{CSP_NONCE}}">
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
let themeMode = localStorage.getItem("themeMode")
    || (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
const systemThemeQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
let personaGuidanceExpanded = true;
let personaGuidanceManual = false;

function applyTheme() {
    document.body.classList.toggle("theme-light", themeMode === "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", themeMode === "light" ? "#F8FAFC" : "#0F172A");
}

function syncThemeFromPreference() {
    var storedTheme = localStorage.getItem("themeMode");
    themeMode = storedTheme || (systemThemeQuery && systemThemeQuery.matches ? "light" : "dark");
    applyTheme();
}

function parseDashboardHash(rawHash) {
    var hash = (rawHash || "").replace(/^#/, "");
    var personaMatch = hash.match(new RegExp("^(?:personas|profiles)/(.+)$"));
    if (personaMatch) {
        return { page: "personas", personaId: personaMatch[1] };
    }
    if (hash === "config" || hash === "tls" || hash === "models" || hash === "personas" || hash === "policy" || hash === "workspace" || hash === "logs") {
        return { page: hash, personaId: "" };
    }
    return { page: "", personaId: "" };
}

function applyPersonaGuidanceState(expanded, manualOverride) {
    var card = document.getElementById("persona-guidance-card");
    var toggle = document.getElementById("btn-persona-guidance-toggle");
    if (!card || !toggle) return;
    personaGuidanceExpanded = expanded;
    if (typeof manualOverride === "boolean") personaGuidanceManual = manualOverride;
    card.dataset.collapsed = expanded ? "false" : "true";
    toggle.textContent = expanded ? "▾" : "▸";
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggle.setAttribute("aria-label", expanded ? "Collapse persona guidance" : "Expand persona guidance");
}

function syncPersonaGuidance(resetManualOverride) {
    var promptInput = document.getElementById("persona-system-prompt");
    if (resetManualOverride) personaGuidanceManual = false;
    var expanded = personaGuidanceManual
        ? personaGuidanceExpanded
        : !(promptInput && promptInput.value.trim());
    applyPersonaGuidanceState(expanded);
}

function togglePersonaGuidance() {
    applyPersonaGuidanceState(!personaGuidanceExpanded, true);
}

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
        if (page === "personas") loadPersonas();
        if (page === "policy") loadPolicies();
        if (page === "workspace") loadWorkspace();
        if (page === "logs") loadLogsPage();
        if (page === "license") loadLicense();
    }
}
window.navigateTo = navigateTo;

/* -- License -------------------------------------------------------- */

async function loadLicense() {
    try {
        const r = await fetch("/api/license/status");
        const s = await r.json();
        const banner = document.getElementById("license-status-banner");
        const statusText = document.getElementById("license-status-text");
        const meta = document.getElementById("license-status-meta");
        const details = document.getElementById("license-details");
        const activateSection = document.getElementById("license-activate-section");

        if (s.license_valid) {
            banner.className = "health-banner banner-ok";
            statusText.textContent = `Apex Pro \u2014 ${s.tier} license active`;
            const exp = new Date(s.license_expires);
            const daysLeft = Math.max(0, Math.ceil((exp - Date.now()) / 86400000));
            meta.textContent = `${daysLeft} days remaining`;
            details.innerHTML =
                '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px">' +
                '<span style="color:var(--text-dim)">Tier</span><span>' + s.tier + '</span>' +
                '<span style="color:var(--text-dim)">License ID</span><span style="font-family:monospace;font-size:11px">' + (s.license_id || '\u2014') + '</span>' +
                '<span style="color:var(--text-dim)">Expires</span><span>' + (s.license_expires ? new Date(s.license_expires).toLocaleDateString() : '\u2014') + '</span>' +
                '<span style="color:var(--text-dim)">Premium</span><span>' + [['groups','Group Channels'],['orchestration','Multi-Agent Orchestration'],['agent_profiles','Custom Personas']].filter(([k]) => s.features[k]).map(([,v]) => v).join(', ') + '</span>' +
                '</div>';
            activateSection.querySelector('[id=license-key-input]').style.display = 'none';
            document.getElementById("btn-activate-license").style.display = 'none';
        } else if (s.trial_active) {
            banner.className = "health-banner banner-warn";
            statusText.textContent = "Trial active";
            meta.textContent = s.trial_days_remaining + " days remaining";
            details.innerHTML =
                '<div style="font-size:13px;color:var(--text-dim);padding:4px 0">' +
                'All premium features are unlocked during the trial. ' +
                'When it ends, group channels become read-only and your data is preserved.</div>';
            activateSection.querySelector('[id=license-key-input]').style.display = '';
            document.getElementById("btn-activate-license").style.display = '';
        } else {
            banner.className = "health-banner banner-critical";
            statusText.textContent = "Free tier \u2014 premium features locked";
            meta.textContent = "";
            details.innerHTML =
                '<div style="font-size:13px;color:var(--text-dim);padding:4px 0">' +
                'Upgrade to Apex Pro for group channels, multi-agent orchestration, and custom personas. ' +
                '<a href="https://buy.stripe.com/dRmcN40Ag8Qucptc2UcQU04" target="_blank" style="color:var(--accent)">View plans</a></div>';
            activateSection.querySelector('[id=license-key-input]').style.display = '';
            document.getElementById("btn-activate-license").style.display = '';
        }
    } catch(e) {
        document.getElementById("license-details").innerHTML = '<div style="color:var(--text-dim)">Failed to load license status</div>';
    }
}

async function activateLicense() {
    const input = document.getElementById("license-key-input");
    const result = document.getElementById("license-activate-result");
    const raw = input.value.trim();
    if (!raw) { result.innerHTML = '<span style="color:#f87171">Paste your license key first</span>'; return; }

    result.innerHTML = '<span style="color:var(--accent)">Activating...</span>';
    try {
        const r = await fetch("/api/license/activate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: raw,
        });
        const data = await r.json();
        if (data.success) {
            result.innerHTML = '<span style="color:#4ade80">License activated! Tier: ' + data.tier + '</span>';
            input.value = '';
            setTimeout(() => loadLicense(), 500);
        } else {
            result.innerHTML = '<span style="color:#f87171">Failed: ' + (data.error || 'Unknown error') + '</span>';
        }
    } catch(e) {
        result.innerHTML = '<span style="color:#f87171">Error: ' + e.message + '</span>';
    }
}

async function deactivateLicense() {
    if (!confirm("Deactivate your license? Premium features will be locked until you re-activate.")) return;
    try {
        const r = await fetch("/api/license/deactivate", {method: "POST"});
        const data = await r.json();
        if (data.success) {
            loadLicense();
        }
    } catch(e) { /* ignore */ }
}

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

var ADMIN_TOKEN_STORAGE_KEY = "apexAdminToken";
var ADMIN_TOKEN_COOKIE = "apex_admin_token";

function getAdminToken() {
    var stored = sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
    if (stored) return stored;
    var match = document.cookie.match(/(?:^|;\\s*)apex_admin_token=([^;]+)/);
    if (!match) return "";
    try {
        stored = decodeURIComponent(match[1]);
    } catch (err) {
        stored = match[1];
    }
    if (stored) sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, stored);
    return stored;
}

function setAdminToken(token) {
    token = String(token || "").trim();
    if (!token) return "";
    sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    document.cookie =
        ADMIN_TOKEN_COOKIE + "=" + encodeURIComponent(token) + "; Path=/admin; SameSite=Strict";
    return token;
}

async function ensureAdminSession() {
    var token = getAdminToken();
    if (token) return token;
    token = window.prompt("Enter admin token");
    return setAdminToken(token);
}

async function authFetch(url, options) {
    options = options || {};
    options.credentials = options.credentials || "same-origin";
    var headers = new Headers(options.headers || {});
    headers.set("X-Requested-With", "XMLHttpRequest");
    var token = getAdminToken();
    if (token && !headers.has("Authorization")) {
        headers.set("Authorization", "Bearer " + token);
    }
    options.headers = headers;
    var resp = await fetch(url, options);
    if (resp.status === 401) {
        var body = await resp.clone().json().catch(function () { return {}; });
        if (body && body.code === "ADMIN_AUTH_REQUIRED") {
            token = await ensureAdminSession();
            if (token) {
                headers.set("Authorization", "Bearer " + token);
                options.headers = headers;
                resp = await fetch(url, options);
            }
        }
    }
    return resp;
}

async function apiFetch(path, options) {
    try {
        options = options || {};
        const resp = await authFetch(API + path, options);
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || body.error || `HTTP ${resp.status}`);
        }
        return await resp.json();
    } catch (err) {
        if (err.name === "TypeError" && err.message.includes("fetch")) {
            throw new Error("Server unreachable");
        }
        throw err;
    }
}

async function rootApiFetch(path, options) {
    try {
        options = options || {};
        const resp = await authFetch(path, options);
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || body.error || `HTTP ${resp.status}`);
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

        var statusEval = analyzeStatusResult(status);
        var dbEval = analyzeDbResult(db);
        var tlsEval = analyzeTlsResult(tls);
        var modelsEval = analyzeModelsResult(models);

        setCardStatus("card-status", statusEval.level);
        setCardStatus("card-db", dbEval.level);
        setCardStatus("card-tls", tlsEval.level);
        setCardStatus("card-models", modelsEval.level);
        updateHealthBanner(statusEval, dbEval, tlsEval, modelsEval);

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

function setCardStatus(cardId, level) {
    var card = document.getElementById(cardId);
    if (!card) return;
    card.classList.remove("card--ok", "card--warn", "card--critical");
    if (level === "ok" || level === "warn" || level === "critical") {
        card.classList.add("card--" + level);
    }
}

function normalizeTlsCerts(payload) {
    var certs = payload && payload.certificates ? payload.certificates : payload;
    if (!certs) return [];
    if (Array.isArray(certs)) return certs;
    var list = [];
    ["ca", "server", "client"].forEach(function(key) {
        if (certs[key]) {
            list.push(Object.assign({ name: key.charAt(0).toUpperCase() + key.slice(1) }, certs[key]));
        }
    });
    return list;
}

function normalizeProviders(payload) {
    var providers = payload && payload.providers ? payload.providers : payload;
    if (!providers) return [];
    if (Array.isArray(providers)) return providers;
    return Object.keys(providers).map(function(key) {
        return Object.assign({ name: key }, providers[key]);
    });
}

function analyzeStatusResult(result) {
    if (!result || result.status === "rejected") {
        return { level: "critical", issue: "Server status unavailable" };
    }
    var d = result.value || {};
    var running = d.status === "running" || d.status === "ok";
    return running ? { level: "ok", issue: "" } : { level: "critical", issue: "Server is not running" };
}

function analyzeDbResult(result) {
    if (!result || result.status === "rejected") {
        return { level: "warn", issue: "Database stats unavailable" };
    }
    return { level: "ok", issue: "" };
}

function analyzeTlsResult(result) {
    if (!result || result.status === "rejected") {
        return { level: "warn", issue: "TLS status unavailable" };
    }
    var certList = normalizeTlsCerts(result.value || {});
    if (!certList.length) {
        return { level: "warn", issue: "No TLS certificates configured" };
    }
    var mostUrgent = null;
    certList.forEach(function(cert) {
        if (cert.days_remaining == null) return;
        if (!mostUrgent || cert.days_remaining < mostUrgent.days_remaining) {
            mostUrgent = cert;
        }
    });
    if (!mostUrgent) {
        return { level: "warn", issue: "TLS expiry unknown" };
    }
    var name = mostUrgent.name || mostUrgent.type || "TLS";
    if (mostUrgent.days_remaining <= 7) {
        return { level: "critical", issue: name + " certificate expires in " + mostUrgent.days_remaining + "d" };
    }
    if (mostUrgent.days_remaining <= 30) {
        return { level: "warn", issue: name + " certificate expires in " + mostUrgent.days_remaining + "d" };
    }
    return { level: "ok", issue: "" };
}

function analyzeModelsResult(result) {
    if (!result || result.status === "rejected") {
        return { level: "warn", issue: "Model health unavailable" };
    }
    var modelList = normalizeProviders(result.value || {});
    if (!modelList.length) {
        return { level: "warn", issue: "No model providers configured" };
    }
    var failing = modelList.filter(function(model) {
        return !(model.status === "ok" || model.status === "reachable" || model.reachable === true);
    });
    if (!failing.length) {
        return { level: "ok", issue: "" };
    }
    if (failing.length === 1) {
        return { level: "warn", issue: (failing[0].name || "Model provider") + " unreachable" };
    }
    return { level: "warn", issue: failing.length + " model providers unreachable" };
}

function updateHealthBanner(statusEval, dbEval, tlsEval, modelsEval) {
    var banner = document.getElementById("health-banner");
    var textEl = document.getElementById("health-banner-text");
    var metaEl = document.getElementById("health-banner-meta");
    if (!banner || !textEl || !metaEl) return;

    var evaluations = [statusEval, dbEval, tlsEval, modelsEval];
    var issues = evaluations.map(function(item) { return item && item.issue ? item.issue : ""; }).filter(Boolean);
    var level = "ok";
    evaluations.forEach(function(item) {
        if (!item) return;
        if (item.level === "critical") {
            level = "critical";
        } else if (item.level === "warn" && level !== "critical") {
            level = "warn";
        }
    });

    banner.classList.remove("banner-ok", "banner-warn", "banner-critical");
    banner.classList.add("banner-" + level);

    if (!issues.length) {
        textEl.textContent = "All systems operational";
        metaEl.textContent = "Auto-refresh every " + Math.round(REFRESH_INTERVAL / 1000) + "s";
    } else if (issues.length === 1) {
        textEl.textContent = issues[0];
        metaEl.textContent = "1 issue detected";
    } else {
        textEl.textContent = issues[0];
        metaEl.textContent = issues.length + " issues detected";
    }
}

async function quickActionTestAlerts(btn) {
    if (btn) btn.disabled = true;
    try {
        await testAlerts();
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.quickActionTestAlerts = quickActionTestAlerts;

async function quickActionCreateBackup(btn) {
    if (btn) btn.disabled = true;
    try {
        await createBackup();
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.quickActionCreateBackup = quickActionCreateBackup;

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
                        ' data-config-field="1" data-section="' + esc(section) + '" data-key="' + esc(key) + '">' +
                    '<div class="toggle-track"></div>' +
                    '<div class="toggle-knob"></div>' +
                '</label>' +
                '<span class="toggle-label">' + (value ? "Enabled" : "Disabled") + '</span>' +
            '</div>';
    } else if (spec.choices) {
        html += '<select id="' + fieldId + '" data-config-field="1" data-section="' + esc(section) + '" data-key="' + esc(key) + '">';
        for (const choice of spec.choices) {
            const selected = (String(value) === String(choice)) ? " selected" : "";
            html += '<option value="' + esc(choice) + '"' + selected + '>' + esc(choice) + '</option>';
        }
        html += '</select>';
    } else if (spec.type === "int") {
        html += '<input type="number" id="' + fieldId + '" value="' + esc(value) + '"' +
                (spec.min != null ? ' min="' + spec.min + '"' : '') +
                (spec.max != null ? ' max="' + spec.max + '"' : '') +
                ' data-config-field="1" data-section="' + esc(section) + '" data-key="' + esc(key) + '">';
    } else if (spec.multiline) {
        const textValue = String(value || "").split(":").join("\\n");
        html += '<textarea id="' + fieldId + '" rows="4" ' +
                'data-config-field="1" data-section="' + esc(section) + '" data-key="' + esc(key) + '"' +
                (spec.placeholder ? ' placeholder="' + esc(spec.placeholder) + '"' : '') +
                '>' + esc(textValue) + '</textarea>';
    } else {
        html += '<input type="text" id="' + fieldId + '" value="' + esc(value) + '"' +
                (spec.placeholder ? ' placeholder="' + esc(spec.placeholder) + '"' : '') +
                ' data-config-field="1" data-section="' + esc(section) + '" data-key="' + esc(key) + '">';
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
            '<button class="btn btn-primary btn-sm" data-generate-ca="false" id="btn-generate-ca">Generate CA</button>';
        return;
    }

    const d = result.value;
    let html = renderCertDetails(d);
    html += renderCertExpiryBar(d);
    html += '<div style="margin-top:12px;">' +
        '<button class="btn btn-ghost btn-sm" data-generate-ca="true">Re-key CA</button>' +
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
        '<button class="btn btn-primary btn-sm" data-renew-server="true">Renew</button>' +
        '<button class="btn btn-ghost btn-sm" data-open-san-editor="true">Edit SANs</button>' +
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

async function downloadP12(cn) {
    if (!await ensureAdminSession()) return;
    window.open(API + "/tls/clients/" + encodeURIComponent(cn) + "/p12", "_blank");
}
window.downloadP12 = downloadP12;

async function showQR(cn) {
    document.getElementById("qr-title").textContent = "QR Code — " + cn;
    document.getElementById("qr-content").innerHTML =
        '<div class="loading-overlay"><div class="spinner"></div> Loading...</div>';
    openModal("modal-qr");

    try {
        const resp = await authFetch(API + "/tls/clients/" + encodeURIComponent(cn) + "/qr");
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
            '<button class="san-remove" data-remove-san="' + i + '" title="Remove">&times;</button>' +
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

/* =====================================================================
   Personas Page
   ===================================================================== */

let personasData = [];
let personaModelsData = [];
let currentPersonaId = "";
let currentPersonaToolPolicy = null;
let policyProfilesData = [];
let policyToolCatalogData = [];
let policyWorkspaceTools = [];
let policyNeverAllowedCommands = [];
let policyBlockedPathPrefixes = [];
let selectedPolicyLevel = 2;

const TOOL_POLICY_LABELS = {
    0: "Chat Only",
    1: "Read Only",
    2: "Workspace + Browser",
    3: "Admin Allowlist",
    4: "Full Admin",
};

const TOOL_POLICY_DETAILS = {
    0: {
        summary: "Conversation only. No tools or MCP access.",
        allowed: [
            "Plain chat responses only",
            "No shell commands",
            "No file reads or writes",
            "No MCP tools",
        ],
        denied: [
            "Bash / command execution",
            "Filesystem access",
            "Playwright browser automation",
            "Memory MCP",
        ],
    },
    1: {
        summary: "Minimal inspection tools for low-risk reading.",
        allowed: [
            "Built-in read tools",
            "Repo/file discovery",
            "Search and list operations",
        ],
        denied: [
            "Writes or edits",
            "Shell commands",
            "Playwright",
            "Memory MCP",
        ],
    },
    2: {
        summary: "Workspace-safe tools, code execution, and browser testing.",
        allowed: [
            "Configured Workspace + Browser tool set",
            "Python code execution (stateful Jupyter kernel)",
            "Playwright MCP when enabled",
            "Fetch MCP when enabled",
            "Selected filesystem read tools",
        ],
        denied: [
            "Filesystem MCP writes/edits unless promoted to a higher level",
            "Memory MCP unless promoted to a higher level",
            "Admin shell allowlist mode",
            "Full unrestricted access",
        ],
    },
    3: {
        summary: "Trusted diagnostics with explicit command and MCP policy controls.",
        allowed: [
            "Allowlisted shell commands",
            "Writable filesystem MCP",
            "Memory MCP",
            "Workspace plus /tmp writes",
        ],
        denied: [
            "Unrestricted shell by default",
            "Automatic access to every command",
            "Unsafe escalation without configuration",
        ],
    },
    4: {
        summary: "Timeboxed unrestricted admin for trusted sessions.",
        allowed: [
            "All shell commands",
            "All filesystem access",
            "All MCP tools",
            "Bypass command/path restrictions",
        ],
        denied: [
            "Nothing by policy; rely on expiry and operator judgment",
        ],
    },
};

function toolPolicyLabel(level) {
    var n = Number(level);
    return TOOL_POLICY_LABELS.hasOwnProperty(n) ? TOOL_POLICY_LABELS[n] : ("Level " + n);
}

function toolPolicyLevelOptions(selectedValue) {
    var selected = Number(selectedValue);
    var html = "";
    [0, 1, 2, 3, 4].forEach(function(level) {
        html += '<option value="' + level + '"' + (level === selected ? ' selected' : '') + '>' +
            level + ' · ' + esc(toolPolicyLabel(level)) +
            '</option>';
    });
    return html;
}

function parseToolPolicy(raw, defaultLevel) {
    var fallback = Number(defaultLevel != null ? defaultLevel : 2);
    var parsed = null;
    if (raw && typeof raw === "object") {
        parsed = raw;
    } else if (typeof raw === "string" && raw.trim()) {
        try {
            parsed = JSON.parse(raw);
        } catch (err) {
            parsed = { level: fallback, default_level: fallback };
        }
    } else {
        parsed = {};
    }
    var defaultVal = Number(parsed.default_level != null ? parsed.default_level : (parsed.level != null ? parsed.level : fallback));
    var levelVal = Number(parsed.level != null ? parsed.level : defaultVal);
    return {
        level: Math.max(0, Math.min(4, Number.isFinite(levelVal) ? levelVal : fallback)),
        default_level: Math.max(0, Math.min(4, Number.isFinite(defaultVal) ? defaultVal : fallback)),
        elevated_until: parsed.elevated_until || null,
        invoke_policy: parsed.invoke_policy || "anyone",
        allowed_commands: Array.isArray(parsed.allowed_commands) ? parsed.allowed_commands : [],
    };
}

function serializeToolPolicyLevel(existingPolicy, level) {
    var base = parseToolPolicy(existingPolicy, level);
    var nextLevel = Math.max(0, Math.min(4, Number(level)));
    base.default_level = nextLevel;
    if (!base.elevated_until) base.level = nextLevel;
    return JSON.stringify(base);
}

function renderPolicyLevelGuide() {
    var el = document.getElementById("policy-level-guide");
    var detailEl = document.getElementById("policy-level-detail");
    if (!el || !detailEl) return;
    var cards = [0, 1, 2, 3, 4].map(function(level) {
        var active = level === selectedPolicyLevel;
        var detail = TOOL_POLICY_DETAILS[level];
        return '<button type="button" class="policy-level-card' + (active ? ' active' : '') + '" data-policy-level-card="' + level + '">' +
            '<strong>' + level + ' · ' + esc(toolPolicyLabel(level)) + '</strong>' +
            '<div class="form-help">' + esc(detail.summary) + '</div>' +
            '</button>';
    }).join('');
    el.innerHTML = cards;

    var selected = TOOL_POLICY_DETAILS[selectedPolicyLevel];
    function list(items) {
        return '<ul style="margin:8px 0 0 18px; display:grid; gap:4px;">' +
            items.map(function(item) { return '<li>' + esc(item) + '</li>'; }).join('') +
            '</ul>';
    }
    detailEl.innerHTML =
        '<div class="card-title" style="margin-bottom:8px;">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>' +
            '</svg>' +
            (selectedPolicyLevel + ' · ' + esc(toolPolicyLabel(selectedPolicyLevel))) +
        '</div>' +
        '<div class="form-help" style="margin-bottom:10px;">' + esc(selected.summary) + '</div>' +
        (selectedPolicyLevel === 2 ? '<div class="form-help" style="margin-bottom:10px;">The exact Workspace + Browser tool set is defined in the editor below.</div>' : '') +
        '<div class="card-grid" style="grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); margin:0;">' +
            '<div class="card policy-mini-card">' +
                '<strong>Allowed</strong>' + list(selected.allowed) +
            '</div>' +
            '<div class="card policy-mini-card">' +
                '<strong>Blocked / Not Included</strong>' + list(selected.denied) +
            '</div>' +
        '</div>';
}
window.renderPolicyLevelGuide = renderPolicyLevelGuide;

function setWorkspaceToolsStatus(message, type) {
    var el = document.getElementById("policy-workspace-tools-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = type === "error" ? "var(--red)" : (type === "success" ? "var(--green)" : "var(--dim)");
}

function setPolicyGuardrailsStatus(message, type) {
    var el = document.getElementById("policy-guardrails-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = type === "error" ? "var(--red)" : (type === "success" ? "var(--green)" : "var(--dim)");
}

function renderPolicyGuardrailsEditor() {
    var el = document.getElementById("policy-guardrails-content");
    if (!el) return;
    el.innerHTML =
        '<div class="policy-editor-shell">' +
        '<div class="card-grid" style="grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); margin:0;">' +
            '<div class="card policy-mini-card">' +
                '<div class="card-title" style="margin-bottom:8px;">Never Allowed Commands</div>' +
                '<div class="form-help" style="margin-bottom:8px;">One command prefix per line. Each shell segment is checked, so entries like <code>sqlite3</code> or <code>rm -rf</code> are blocked everywhere.</div>' +
                '<textarea id="policy-never-allowed-commands" rows="8" placeholder="sqlite3&#10;rm -rf&#10;launchctl">' + esc((policyNeverAllowedCommands || []).join('\\n')) + '</textarea>' +
            '</div>' +
            '<div class="card policy-mini-card">' +
                '<div class="card-title" style="margin-bottom:8px;">Blocked Path Prefixes</div>' +
                '<div class="form-help" style="margin-bottom:8px;">One absolute path prefix per line. File tools and shell commands touching these locations are denied, even at Full Admin.</div>' +
                '<textarea id="policy-blocked-path-prefixes" rows="8" placeholder="/Users/you/project/state&#10;/Users/you/.ssh">' + esc((policyBlockedPathPrefixes || []).join('\\n')) + '</textarea>' +
            '</div>' +
        '</div>' +
        '<div class="policy-editor-actions">' +
            '<button class="btn btn-ghost" data-policy-guardrails-reset>Reset</button>' +
            '<button class="btn btn-primary" data-policy-guardrails-save>Save Guardrails</button>' +
        '</div>' +
        '</div>';
}
window.renderPolicyGuardrailsEditor = renderPolicyGuardrailsEditor;

function renderWorkspaceToolsEditor() {
    var el = document.getElementById("policy-workspace-tools-content");
    if (!el) return;
    if (!policyToolCatalogData.length) {
        el.innerHTML = '<div class="text-dim" style="padding:12px 0;">No tool catalog available.</div>';
        return;
    }
    var enabledSet = new Set((policyWorkspaceTools || []).map(function(item) { return String(item); }));
    var defaultSet = new Set(policyToolCatalogData.filter(function(tool) { return !!tool.workspace_default; }).map(function(tool) { return tool.id; }));
    var enabledCount = enabledSet.size;
    var defaultCount = defaultSet.size;
    var matchesDefault = enabledCount === defaultCount && Array.from(enabledSet).every(function(id) { return defaultSet.has(id); });
    var groupOrder = ["execute", "read", "write", "browser", "network", "memory", "shell"];
    var groupLabels = {
        execute: "Code Execution",
        read: "Read Tools",
        write: "Write Tools",
        browser: "Browser",
        network: "Network",
        memory: "Memory",
        shell: "Shell",
    };
    var grouped = {};
    policyToolCatalogData.forEach(function(tool) {
        var group = String(tool.group || tool.category || "other");
        if (!grouped[group]) grouped[group] = [];
        grouped[group].push(tool);
    });
    var rowsByGroup = groupOrder
        .filter(function(group) { return Array.isArray(grouped[group]) && grouped[group].length; })
        .map(function(group) {
            var tools = grouped[group].slice().sort(function(a, b) {
                var aEnabled = enabledSet.has(a.id) ? 1 : 0;
                var bEnabled = enabledSet.has(b.id) ? 1 : 0;
                if (aEnabled !== bEnabled) return bEnabled - aEnabled;
                return String(a.name).localeCompare(String(b.name));
            });
            var selectedCount = tools.filter(function(tool) { return enabledSet.has(tool.id); }).length;
            var rows = tools.map(function(tool) {
                return '<label class="card" style="display:block; margin:0; padding:10px 12px;">' +
            '<div style="display:flex; gap:10px; align-items:flex-start;">' +
                '<input type="checkbox" data-workspace-tool-id="' + esc(tool.id) + '"' + (enabledSet.has(tool.id) ? ' checked' : '') + ' style="margin-top:2px;">' +
                '<div style="min-width:0;">' +
                    '<div style="font-weight:600;">' + esc(tool.name) + '</div>' +
                    '<div class="form-help"><code>' + esc(tool.id) + '</code> · ' + esc(tool.category) + '</div>' +
                    '<div class="form-help" style="margin-top:4px;">' + esc(tool.description) + '</div>' +
                '</div>' +
            '</div>' +
        '</label>';
            }).join('');
            var isOpen = selectedCount > 0 || group === "read" || group === "browser";
            return '<details class="card" style="margin:0; padding:0; overflow:hidden;"' + (isOpen ? ' open' : '') + '>' +
                '<summary style="list-style:none; cursor:pointer; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 14px; font-weight:600;">' +
                    '<span>' + esc(groupLabels[group] || group) + '</span>' +
                    '<span class="form-help">' + selectedCount + ' of ' + tools.length + ' enabled</span>' +
                '</summary>' +
                '<div style="display:grid; gap:8px; padding:0 12px 12px;">' + rows + '</div>' +
            '</details>';
        }).join('');
    el.innerHTML =
        '<div class="policy-editor-shell">' +
        '<div style="display:flex; gap:8px; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap;">' +
            '<div class="form-help">' +
                'Selected tools apply immediately to level 2 across SDK and tool-loop backends. ' +
                '<strong style="color:var(--text);">' + enabledCount + ' enabled</strong> · ' +
                (matchesDefault ? 'Using system default set' : 'Using custom tool set') +
            '</div>' +
            '<div class="policy-editor-actions">' +
                '<button class="btn btn-ghost" data-policy-workspace-reset>Reset to Default</button>' +
                '<button class="btn btn-primary" data-policy-workspace-save>Save Workspace Tool Set</button>' +
            '</div>' +
        '</div>' +
        '<div style="display:grid; gap:10px;">' + rowsByGroup + '</div>' +
        '</div>';
}
window.renderWorkspaceToolsEditor = renderWorkspaceToolsEditor;

function personaModelOptions(selectedValue, includeBlank, blankLabel) {
    var options = includeBlank ? '<option value="">' + esc(blankLabel || 'None') + '</option>' : '';
    var groups = {};
    for (var i = 0; i < personaModelsData.length; i++) {
        var model = personaModelsData[i] || {};
        var provider = model.provider || (model.local ? 'local' : 'other');
        if (!groups[provider]) groups[provider] = [];
        groups[provider].push(model);
    }
    Object.keys(groups).sort().forEach(function(provider) {
        options += '<optgroup label="' + esc(capitalize(provider)) + '">';
        groups[provider].forEach(function(model) {
            var id = model.id || '';
            var label = model.displayName || model.name || id;
            var selected = id === selectedValue ? ' selected' : '';
            options += '<option value="' + esc(id) + '"' + selected + '>' + esc(label) + '</option>';
        });
        options += '</optgroup>';
    });
    return options;
}

function fillPersonaModelSelects(baseValue, overrideValue) {
    var baseSel = document.getElementById('persona-model');
    var overrideSel = document.getElementById('persona-override-model');
    if (baseSel) baseSel.innerHTML = personaModelOptions(baseValue || '', true, 'Use server default');
    if (overrideSel) overrideSel.innerHTML = personaModelOptions(overrideValue || '', true, 'Use base persona model');
    if (baseSel && baseValue) baseSel.value = baseValue;
    if (overrideSel && overrideValue) overrideSel.value = overrideValue;
}

function renderPersonasList() {
    var container = document.getElementById('personas-list-content');
    if (!container) return;
    if (!personasData.length) {
        container.innerHTML = '<div class="text-dim" style="padding:12px 0;">No personas installed yet.</div>';
        return;
    }
    var html = '';
    personasData.forEach(function(persona) {
        var active = persona.id === currentPersonaId ? ' border-color:var(--accent); box-shadow:0 0 0 1px rgba(14,165,233,0.25) inset;' : '';
        var source = persona.model_source === 'override' ? 'Override' : 'Base';
        var badges = '';
        if (persona.is_system) badges += '<span class="nav-badge" style="margin-left:0; background:rgba(99,102,241,0.15); color:#818cf8;">System</span>';
        if (persona.is_default) badges += '<span class="nav-badge" style="margin-left:0;">Default</span>';
        html += '<button class="btn btn-ghost" data-persona-id="' + esc(encodeURIComponent(persona.id)) + '" style="width:100%; text-align:left; padding:12px; margin-bottom:8px; border:1px solid var(--card); background:var(--bg);' + active + '">' +
            '<div style="display:flex; align-items:flex-start; gap:10px;">' +
                '<div style="font-size:20px; line-height:1;">' + esc(persona.avatar || '💬') + '</div>' +
                '<div style="flex:1; min-width:0;">' +
                    '<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">' +
                        '<strong style="font-size:13px;">' + esc(persona.name || persona.slug || persona.id) + '</strong>' +
                        badges +
                    '</div>' +
                    '<div class="text-dim" style="font-size:12px; margin-top:2px;">' + esc(persona.role_description || 'No description') + '</div>' +
                    '<div style="font-size:11px; color:var(--dim); margin-top:6px;">' +
                        '<span class="mono">' + esc(persona.model || 'server default') + '</span>' +
                        ' · ' + esc(source) +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</button>';
    });
    container.innerHTML = html;
}

function newPersonaForm() {
    currentPersonaId = '';
    currentPersonaToolPolicy = parseToolPolicy(null, 2);
    document.getElementById('persona-editor-meta').textContent = 'Create a new persona profile.';
    document.getElementById('persona-name').value = '';
    document.getElementById('persona-slug').value = '';
    document.getElementById('persona-avatar').value = '';
    document.getElementById('persona-role').value = '';
    document.getElementById('persona-tool-policy').innerHTML = toolPolicyLevelOptions(currentPersonaToolPolicy.default_level);
    document.getElementById('persona-tool-policy').value = String(currentPersonaToolPolicy.default_level);
    document.getElementById('persona-system-prompt').value = '';
    document.getElementById('persona-is-default').checked = false;
    var promptHelp = document.getElementById('persona-prompt-help');
    if (promptHelp) promptHelp.textContent = 'Prompt used for this persona.';
    fillPersonaModelSelects('', '');
    var delBtn = document.getElementById('btn-persona-delete');
    if (delBtn) { delBtn.disabled = true; delBtn.style.display = 'none'; }
    var resetPromptBtn = document.getElementById('btn-persona-reset-prompt');
    if (resetPromptBtn) { resetPromptBtn.disabled = true; resetPromptBtn.style.display = 'none'; }
    var slugInput = document.getElementById('persona-slug');
    if (slugInput) slugInput.disabled = false;
    syncPersonaGuidance(true);
    renderPersonasList();
}
window.newPersonaForm = newPersonaForm;

async function selectPersona(personaId) {
    currentPersonaId = decodeURIComponent(personaId);
    renderPersonasList();
    var detail = await rootApiFetch('/api/profiles/' + encodeURIComponent(currentPersonaId));
    currentPersonaToolPolicy = parseToolPolicy(detail.tool_policy, 2);
    document.getElementById('persona-editor-meta').textContent = 'Editing ' + (detail.name || detail.slug || currentPersonaId) + ' · effective model: ' + (detail.model || 'server default');
    document.getElementById('persona-name').value = detail.name || '';
    document.getElementById('persona-slug').value = detail.slug || '';
    document.getElementById('persona-avatar').value = detail.avatar || '';
    document.getElementById('persona-role').value = detail.role_description || '';
    document.getElementById('persona-tool-policy').innerHTML = toolPolicyLevelOptions(currentPersonaToolPolicy.default_level);
    document.getElementById('persona-tool-policy').value = String(currentPersonaToolPolicy.default_level);
    document.getElementById('persona-system-prompt').value = detail.system_prompt || '';
    document.getElementById('persona-is-default').checked = !!detail.is_default;
    fillPersonaModelSelects(detail.base_model || detail.model || '', detail.override_model || '');
    var promptHelp = document.getElementById('persona-prompt-help');
    if (promptHelp) {
        if (detail.is_system) {
            promptHelp.textContent = detail.has_prompt_override
                ? 'You are editing a custom override for this built-in persona. Reset to go back to the shipped default.'
                : 'This is the built-in system prompt. Any changes you save here become your local override.';
        } else {
            promptHelp.textContent = 'Prompt used for this persona.';
        }
    }
    var slugInput = document.getElementById('persona-slug');
    if (slugInput) slugInput.disabled = !!detail.is_system;
    var delBtn = document.getElementById('btn-persona-delete');
    if (delBtn) {
        if (detail.is_system) {
            delBtn.style.display = 'none';
        } else {
            delBtn.style.display = '';
            delBtn.disabled = false;
        }
    }
    var resetPromptBtn = document.getElementById('btn-persona-reset-prompt');
    if (resetPromptBtn) {
        if (detail.is_system) {
            resetPromptBtn.style.display = '';
            resetPromptBtn.disabled = !detail.has_prompt_override;
        } else {
            resetPromptBtn.style.display = 'none';
            resetPromptBtn.disabled = true;
        }
    }
    syncPersonaGuidance(true);
}
window.selectPersona = selectPersona;

async function loadPersonas() {
    var btnRefresh = document.getElementById('btn-personas-refresh');
    if (btnRefresh) btnRefresh.disabled = true;
    try {
        var results = await Promise.all([
            rootApiFetch('/api/profiles'),
            rootApiFetch('/api/available-models'),
        ]);
        personasData = results[0].profiles || [];
        personaModelsData = results[1].models || [];
        renderPersonasList();
        if (currentPersonaId && personasData.some(function(p) { return p.id === currentPersonaId; })) {
            await selectPersona(currentPersonaId);
        } else {
            newPersonaForm();
        }
    } catch (err) {
        showToast('Failed to load personas: ' + err.message, 'error');
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadPersonas = loadPersonas;

async function savePersona() {
    var name = document.getElementById('persona-name').value.trim();
    if (!name) {
        showToast('Persona name is required', 'warning');
        document.getElementById('persona-name').focus();
        return;
    }
    var payload = {
        name: name,
        slug: document.getElementById('persona-slug').value.trim(),
        avatar: document.getElementById('persona-avatar').value.trim(),
        role_description: document.getElementById('persona-role').value.trim(),
        model: document.getElementById('persona-model').value,
        tool_policy: serializeToolPolicyLevel(currentPersonaToolPolicy, document.getElementById('persona-tool-policy').value),
        system_prompt: document.getElementById('persona-system-prompt').value,
        is_default: document.getElementById('persona-is-default').checked,
    };
    var overrideModel = document.getElementById('persona-override-model').value;
    var btnSave = document.getElementById('btn-persona-save');
    var isEditing = !!currentPersonaId;
    btnSave.disabled = true;
    try {
        var result;
        if (currentPersonaId) {
            await rootApiFetch('/api/profiles/' + encodeURIComponent(currentPersonaId), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            result = { id: currentPersonaId };
        } else {
            result = await rootApiFetch('/api/profiles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            currentPersonaId = result.id;
        }

        if (overrideModel) {
            await rootApiFetch('/api/profiles/' + encodeURIComponent(result.id) + '/model-override', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: overrideModel }),
            });
        } else if (currentPersonaId) {
            await rootApiFetch('/api/profiles/' + encodeURIComponent(result.id) + '/model-override', { method: 'DELETE' }).catch(function() {});
        }

        showToast(isEditing ? 'Persona saved' : 'Persona created', 'success');
        await loadPersonas();
        if (result.id) await selectPersona(result.id);
    } catch (err) {
        showToast('Failed to save persona: ' + err.message, 'error');
    } finally {
        btnSave.disabled = false;
    }
}
window.savePersona = savePersona;

async function resetPersonaPrompt() {
    if (!currentPersonaId) return;
    var btn = document.getElementById('btn-persona-reset-prompt');
    if (btn) btn.disabled = true;
    try {
        var result = await rootApiFetch('/api/profiles/' + encodeURIComponent(currentPersonaId) + '/reset', { method: 'POST' });
        document.getElementById('persona-system-prompt').value = result.system_prompt || '';
        showToast(result.message || 'Persona prompt reset to default', 'success');
        await loadPersonas();
        await selectPersona(currentPersonaId);
    } catch (err) {
        showToast('Failed to reset prompt: ' + err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.resetPersonaPrompt = resetPersonaPrompt;

async function deletePersona() {
    if (!currentPersonaId) return;
    if (!confirm('Delete this persona? Existing chats will be unlinked but preserved.')) return;
    var btnDelete = document.getElementById('btn-persona-delete');
    btnDelete.disabled = true;
    try {
        await rootApiFetch('/api/profiles/' + encodeURIComponent(currentPersonaId), { method: 'DELETE' });
        showToast('Persona deleted', 'success');
        currentPersonaId = '';
        await loadPersonas();
    } catch (err) {
        showToast('Failed to delete persona: ' + err.message, 'error');
        btnDelete.disabled = false;
    }
}
window.deletePersona = deletePersona;

/* =====================================================================
   Policy Page
   ===================================================================== */

function setPolicyPageStatus(message, type) {
    var el = document.getElementById("policy-page-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = type === "error" ? "var(--red)" : (type === "success" ? "var(--green)" : "var(--dim)");
}

function renderPolicyTable() {
    var el = document.getElementById("policy-page-content");
    if (!el) return;
    if (!policyProfilesData.length) {
        el.innerHTML = '<div class="text-dim" style="padding:12px 0;">No personas available.</div>';
        return;
    }
    var rows = policyProfilesData.map(function(profile) {
        var policy = parseToolPolicy(profile.tool_policy, 2);
        var exp = policy.elevated_until ? new Date(policy.elevated_until).toLocaleString() : "—";
        return '<tr style="border-bottom:1px solid var(--card);">' +
            '<td style="padding:10px 8px;">' +
                '<div style="display:flex; align-items:center; gap:8px;">' +
                    '<span style="font-size:18px; line-height:1;">' + esc(profile.avatar || "💬") + '</span>' +
                    '<div><div style="font-weight:600;">' + esc(profile.name || profile.slug || profile.id) + '</div>' +
                    '<div class="form-help">' + esc(profile.id) + (profile.is_system ? " · system" : "") + '</div></div>' +
                '</div>' +
            '</td>' +
            '<td style="padding:10px 8px;">' + esc(toolPolicyLabel(policy.level)) + '</td>' +
            '<td style="padding:10px 8px; min-width:180px;">' +
                '<select data-policy-default-level="' + esc(profile.id) + '" style="width:100%;">' +
                    toolPolicyLevelOptions(policy.default_level) +
                '</select>' +
            '</td>' +
            '<td style="padding:10px 8px;">' + esc(exp) + '</td>' +
            '<td style="padding:10px 8px; min-width:260px;">' +
                '<div style="display:flex; gap:8px; align-items:center; justify-content:flex-end; flex-wrap:wrap;">' +
                    '<select data-policy-elevate-level="' + esc(profile.id) + '">' +
                        '<option value="3">3 · Admin Allowlist</option>' +
                        '<option value="4">4 · Full Admin</option>' +
                    '</select>' +
                    '<input type="number" min="1" max="1440" value="15" data-policy-elevate-minutes="' + esc(profile.id) + '" style="width:84px;">' +
                    '<button class="btn btn-ghost" data-policy-save="' + esc(profile.id) + '">Save Default</button>' +
                    '<button class="btn btn-ghost" data-policy-elevate="' + esc(profile.id) + '">Elevate</button>' +
                    '<button class="btn btn-ghost" data-policy-revoke="' + esc(profile.id) + '" style="color:var(--red);">Revoke</button>' +
                '</div>' +
            '</td>' +
        '</tr>';
    }).join('');
    el.innerHTML =
        '<div class="policy-table-wrap">' +
            '<table class="policy-table">' +
                '<thead><tr style="border-bottom:1px solid var(--card); color:var(--dim); font-size:11px; text-transform:uppercase;">' +
                    '<th style="text-align:left; padding:8px;">Persona</th>' +
                    '<th style="text-align:left; padding:8px;">Effective</th>' +
                    '<th style="text-align:left; padding:8px;">Default Level</th>' +
                    '<th style="text-align:left; padding:8px;">Elevation Expires</th>' +
                    '<th style="text-align:right; padding:8px;">Actions</th>' +
                '</tr></thead>' +
                '<tbody>' + rows + '</tbody>' +
            '</table>' +
        '</div>';
}

async function loadPolicies() {
    var btnRefresh = document.getElementById("btn-policy-refresh");
    if (btnRefresh) btnRefresh.disabled = true;
    renderPolicyLevelGuide();
    setPolicyPageStatus("Loading policies...");
    setPolicyGuardrailsStatus("Loading guardrails...");
    setWorkspaceToolsStatus("Loading workspace tool set...");
    try {
        var toolsResp = await apiFetch('/policy/tools');
        policyToolCatalogData = toolsResp.catalog || [];
        policyWorkspaceTools = toolsResp.workspace_tools || [];
        policyNeverAllowedCommands = toolsResp.never_allowed_commands || [];
        policyBlockedPathPrefixes = toolsResp.blocked_path_prefixes || [];
        renderPolicyGuardrailsEditor();
        setPolicyGuardrailsStatus("Guardrails loaded.");
        renderWorkspaceToolsEditor();
        setWorkspaceToolsStatus("Workspace tool set loaded.");
        var profilesResp = await rootApiFetch('/api/profiles');
        var profiles = profilesResp.profiles || [];
        var details = await Promise.all(profiles.map(function(profile) {
            return rootApiFetch('/api/profiles/' + encodeURIComponent(profile.id));
        }));
        policyProfilesData = details.sort(function(a, b) {
            if (!!a.is_system !== !!b.is_system) return a.is_system ? -1 : 1;
            return String(a.name || a.id).localeCompare(String(b.name || b.id));
        });
        renderPolicyTable();
        setPolicyPageStatus("Policies loaded.");
    } catch (err) {
        setPolicyPageStatus("Failed to load policies: " + err.message, "error");
        setPolicyGuardrailsStatus("Failed to load guardrails: " + err.message, "error");
        setWorkspaceToolsStatus("Failed to load workspace tool set: " + err.message, "error");
        var el = document.getElementById("policy-page-content");
        if (el) el.innerHTML = renderError("Could not load policy data");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadPolicies = loadPolicies;

function _collectWorkspaceToolSelection() {
    return Array.from(document.querySelectorAll('[data-workspace-tool-id]'))
        .filter(function(el) { return el.checked; })
        .map(function(el) { return el.dataset.workspaceToolId; });
}

async function saveWorkspaceToolPolicy() {
    var selected = _collectWorkspaceToolSelection();
    setWorkspaceToolsStatus("Saving workspace tool set...");
    try {
        var resp = await apiFetch('/policy/tools', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_tools: selected }),
        });
        policyToolCatalogData = resp.catalog || [];
        policyWorkspaceTools = resp.workspace_tools || [];
        renderWorkspaceToolsEditor();
        renderPolicyLevelGuide();
        setWorkspaceToolsStatus("Workspace tool set saved.", "success");
    } catch (err) {
        setWorkspaceToolsStatus("Failed to save workspace tool set: " + err.message, "error");
    }
}
window.saveWorkspaceToolPolicy = saveWorkspaceToolPolicy;

function _collectMultilineValues(elementId) {
    var el = document.getElementById(elementId);
    if (!el) return [];
    return String(el.value || '')
        .split(/\\r?\\n/)
        .map(function(line) { return line.trim(); })
        .filter(Boolean);
}

async function savePolicyGuardrails() {
    setPolicyGuardrailsStatus("Saving guardrails...");
    try {
        var resp = await apiFetch('/policy/tools', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                never_allowed_commands: _collectMultilineValues('policy-never-allowed-commands'),
                blocked_path_prefixes: _collectMultilineValues('policy-blocked-path-prefixes'),
            }),
        });
        policyNeverAllowedCommands = resp.never_allowed_commands || [];
        policyBlockedPathPrefixes = resp.blocked_path_prefixes || [];
        renderPolicyGuardrailsEditor();
        setPolicyGuardrailsStatus("Guardrails saved.", "success");
    } catch (err) {
        setPolicyGuardrailsStatus("Failed to save guardrails: " + err.message, "error");
    }
}
window.savePolicyGuardrails = savePolicyGuardrails;

function resetPolicyGuardrails() {
    policyNeverAllowedCommands = [];
    policyBlockedPathPrefixes = [];
    renderPolicyGuardrailsEditor();
    setPolicyGuardrailsStatus("Reset guardrails in the editor. Save to apply.", "success");
}
window.resetPolicyGuardrails = resetPolicyGuardrails;

function resetWorkspaceToolPolicyDefaults() {
    policyWorkspaceTools = policyToolCatalogData
        .filter(function(tool) { return !!tool.workspace_default; })
        .map(function(tool) { return tool.id; });
    renderWorkspaceToolsEditor();
    setWorkspaceToolsStatus("Reset to default workspace tool set. Save to apply.", "success");
}
window.resetWorkspaceToolPolicyDefaults = resetWorkspaceToolPolicyDefaults;

async function savePersonaPolicyLevel(profileId) {
    var levelEl = document.querySelector('[data-policy-default-level="' + profileId + '"]');
    if (!levelEl) return;
    var profile = policyProfilesData.find(function(p) { return p.id === profileId; });
    var serialized = serializeToolPolicyLevel(profile && profile.tool_policy, levelEl.value);
    setPolicyPageStatus("Saving default level for " + profileId + "...");
    try {
        await rootApiFetch('/api/profiles/' + encodeURIComponent(profileId), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool_policy: serialized }),
        });
        setPolicyPageStatus("Saved default level for " + profileId + ".", "success");
        await loadPolicies();
        if (currentPage === "personas") await loadPersonas();
    } catch (err) {
        setPolicyPageStatus("Failed to save " + profileId + ": " + err.message, "error");
    }
}
window.savePersonaPolicyLevel = savePersonaPolicyLevel;

async function elevatePersonaPolicy(profileId) {
    var levelEl = document.querySelector('[data-policy-elevate-level="' + profileId + '"]');
    var minsEl = document.querySelector('[data-policy-elevate-minutes="' + profileId + '"]');
    if (!levelEl || !minsEl) return;
    setPolicyPageStatus("Elevating " + profileId + "...");
    try {
        await apiFetch('/personas/' + encodeURIComponent(profileId) + '/elevate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level: Number(levelEl.value), minutes: Number(minsEl.value || 15) }),
        });
        setPolicyPageStatus("Elevation applied to " + profileId + ".", "success");
        await loadPolicies();
        if (currentPage === "personas") await loadPersonas();
    } catch (err) {
        setPolicyPageStatus("Failed to elevate " + profileId + ": " + err.message, "error");
    }
}
window.elevatePersonaPolicy = elevatePersonaPolicy;

async function revokePersonaPolicy(profileId) {
    setPolicyPageStatus("Revoking elevation for " + profileId + "...");
    try {
        await apiFetch('/personas/' + encodeURIComponent(profileId) + '/revoke', {
            method: 'POST',
        });
        setPolicyPageStatus("Elevation revoked for " + profileId + ".", "success");
        await loadPolicies();
        if (currentPage === "personas") await loadPersonas();
    } catch (err) {
        setPolicyPageStatus("Failed to revoke " + profileId + ": " + err.message, "error");
    }
}
window.revokePersonaPolicy = revokePersonaPolicy;

/* -- Render: Credentials Table -------------------------------------- */

function renderCredentialsTable() {
    var tbody = document.getElementById("credentials-tbody");
    var providers = [
        { key: "anthropic", name: "Claude (Anthropic)" },
        { key: "xai", name: "Grok API Key" },
        { key: "xai_management", name: "Grok Management Key" },
        { key: "xai_team_id", name: "Grok Team ID" },
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
    var names = { anthropic: "Claude API Key", xai: "Grok API Key", xai_management: "Grok Management Key", xai_team_id: "Grok Team ID", openai: "OpenAI API Key", telegram_bot: "Telegram Bot Token", telegram_chat: "Telegram Chat ID" };
    var hints = {
        anthropic: "Starts with sk-ant-... (paste from console.anthropic.com)",
        xai: "Starts with xai-... (paste from console.x.ai)",
        xai_management: "Starts with xai-token-... (from console.x.ai > Settings > Management Keys)",
        xai_team_id: "UUID from console.x.ai/team/default/settings/team",
        openai: "Starts with sk-... (paste from platform.openai.com/api-keys)",
        telegram_bot: "Format: 123456789:ABCdef... (from @BotFather)",
        telegram_chat: "Numeric chat ID (e.g. 5072593158)"
    };
    document.getElementById("credential-modal-title").textContent = "Update " + (names[provider] || capitalize(provider));
    document.getElementById("credential-input-label").textContent = names[provider] || "Credential";
    document.getElementById("credential-input-help").textContent = hints[provider] || "Enter the new " + (names[provider] || "credential").toLowerCase();
    var input = document.getElementById("credential-input");
    input.value = "";
    input.type = (provider === "telegram_chat" || provider === "xai_team_id") ? "text" : "password";
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
    var tgConfigured = !!(credentialsData.telegram_bot && credentialsData.telegram_chat);
    var dotClass = tgConfigured ? "green" : "red";
    telegramEl.innerHTML =
        '<span class="status-dot ' + dotClass + '"></span>' +
        '<span class="text-' + (tgConfigured ? "green" : "red") + '">' +
            (tgConfigured ? "Configured" : "Not configured") +
        '</span>';

    var botInput = document.getElementById("alert-telegram-bot-input");
    var chatInput = document.getElementById("alert-telegram-chat-input");
    if (botInput) {
        botInput.value = "";
    }
    if (chatInput) {
        chatInput.value = "";
    }

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

async function saveTelegramConfig() {
    var botInput = document.getElementById("alert-telegram-bot-input");
    var chatInput = document.getElementById("alert-telegram-chat-input");
    var botToken = botInput ? botInput.value.trim() : "";
    var chatId = chatInput ? chatInput.value.trim() : "";
    if (!botToken) {
        showToast("Please enter a Telegram bot token", "warning");
        if (botInput) botInput.focus();
        return;
    }
    if (!chatId) {
        showToast("Please enter a Telegram chat ID", "warning");
        if (chatInput) chatInput.focus();
        return;
    }

    var btn = document.getElementById("btn-save-telegram-config");
    if (btn) btn.disabled = true;
    try {
        await apiFetch("/alerts/config/telegram", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
        });
        showToast("Telegram configuration updated", "success");
        loadModels();
    } catch (err) {
        showToast("Telegram update failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.saveTelegramConfig = saveTelegramConfig;

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
        var [workspace, skills, mcpResult, whitelist, sessions] = await Promise.allSettled([
            apiFetch("/workspace"),
            apiFetch("/skills"),
            apiFetch("/mcp/servers"),
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

        /* MCP Servers */
        if (mcpResult.status === "fulfilled") {
            renderMcpServers(mcpResult.value);
        } else {
            document.getElementById("ws-mcp-content").innerHTML =
                renderError("Could not load MCP servers");
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

        /* Load project instructions and memory separately */
        loadProjectMd();
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
    var workspacePaths = Array.isArray(d.workspace_paths) && d.workspace_paths.length ? d.workspace_paths : [path];
    var projectMdExists = d.project_md_exists !== false;
    var memoryCount = d.memory_file_count != null ? d.memory_file_count : "—";
    var skillsCount = d.skills_count != null ? d.skills_count : "—";
    var pathsText = workspacePaths.join('\\n');

    el.innerHTML =
        '<div class="ws-summary-grid">' +
            '<div class="ws-summary-item" style="grid-column:span 2; text-align:left;">' +
                '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:8px;">' +
                    '<div class="ws-summary-label" style="margin:0;">Workspace Paths</div>' +
                    '<button class="btn btn-ghost" id="btn-ws-paths-save">Save Paths</button>' +
                '</div>' +
                '<textarea id="ws-paths-editor" rows="3" class="ws-textarea" style="min-height:96px; margin-bottom:8px;" placeholder="/path/to/workspace&#10;/path/to/project-b">' + esc(pathsText) + '</textarea>' +
                '<div id="ws-paths-status" class="form-help">One workspace directory per line.</div>' +
            '</div>' +
            '<div class="ws-summary-item">' +
                '<div class="ws-summary-value">' +
                    '<span class="status-dot ' + (projectMdExists ? "green" : "red") + '"></span>' +
                    (projectMdExists ? "Present" : "Missing") +
                '</div>' +
                '<div class="ws-summary-label">APEX.md</div>' +
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

    var saveBtn = document.getElementById("btn-ws-paths-save");
    if (saveBtn) saveBtn.onclick = saveWorkspacePaths;
}

async function saveWorkspacePaths() {
    var editor = document.getElementById("ws-paths-editor");
    var btn = document.getElementById("btn-ws-paths-save");
    var statusEl = document.getElementById("ws-paths-status");
    if (!editor || !btn || !statusEl) return;
    btn.disabled = true;
    statusEl.textContent = "Saving workspace paths...";
    statusEl.style.color = "var(--dim)";
    try {
        await apiFetch("/config/workspace", {
            method: "PUT",
            headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            body: JSON.stringify({ path: editor.value }),
        });
        statusEl.textContent = "Workspace paths saved.";
        statusEl.style.color = "var(--green)";
        showToast("Workspace paths updated", "success");
        await loadWorkspace();
    } catch (err) {
        statusEl.textContent = "Failed to save: " + err.message;
        statusEl.style.color = "var(--red)";
    } finally {
        btn.disabled = false;
    }
}
window.saveWorkspacePaths = saveWorkspacePaths;

/* -- Project Instructions (APEX.md) Editor ------------------------- */

async function loadProjectMd() {
    var editor = document.getElementById("ws-projectmd-editor");
    var statusEl = document.getElementById("ws-projectmd-status");
    var modifiedEl = document.getElementById("ws-projectmd-modified");

    statusEl.textContent = "Loading...";
    editor.disabled = true;

    try {
        var result = await apiFetch("/workspace/project-md");
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
window.loadProjectMd = loadProjectMd;

async function saveProjectMd() {
    if (!confirm("This will backup and overwrite APEX.md. Continue?")) return;

    var editor = document.getElementById("ws-projectmd-editor");
    var btn = document.getElementById("btn-projectmd-save");
    var statusEl = document.getElementById("ws-projectmd-status");
    btn.disabled = true;

    try {
        await apiFetch("/workspace/project-md", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: editor.value }),
        });
        showToast("APEX.md saved with backup", "success");
        statusEl.textContent = "Saved";
        statusEl.style.color = "var(--green)";
        setTimeout(function() { statusEl.textContent = ""; }, 3000);
        /* Refresh modified timestamp */
        var modifiedEl = document.getElementById("ws-projectmd-modified");
        modifiedEl.textContent = "Last modified: " + new Date().toLocaleString();
    } catch (err) {
        showToast("Save failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
    }
}
window.saveProjectMd = saveProjectMd;

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

/* -- MCP Servers --------------------------------------------------- */

function renderMcpServers(data) {
    var el = document.getElementById("ws-mcp-content");
    var servers = data.mcpServers || {};
    var names = Object.keys(servers);

    if (names.length === 0) {
        el.innerHTML = '<div style="padding:12px; color:var(--dim); font-size:13px;">No MCP servers configured. Click + Add Server to get started.</div>';
        return;
    }

    var html = '<table style="width:100%; font-size:13px; border-collapse:collapse;">' +
        '<tr style="border-bottom:1px solid var(--card); color:var(--dim); font-size:11px; text-transform:uppercase;">' +
        '<th style="text-align:left; padding:6px 8px;">Name</th>' +
        '<th style="text-align:left; padding:6px 8px;">Type</th>' +
        '<th style="text-align:left; padding:6px 8px;">Target</th>' +
        '<th style="text-align:center; padding:6px 8px;">Enabled</th>' +
        '<th style="text-align:right; padding:6px 8px;"></th></tr>';

    for (var i = 0; i < names.length; i++) {
        var name = names[i];
        var cfg = servers[name];
        var target = cfg.command ? esc(cfg.command + (cfg.args ? " " + cfg.args.join(" ") : "")) : esc(cfg.url || "");
        var checked = cfg.enabled !== false ? "checked" : "";
        html += '<tr style="border-bottom:1px solid var(--card);">' +
            '<td style="padding:6px 8px; font-family:monospace;">' + esc(name) + '</td>' +
            '<td style="padding:6px 8px;">' + esc(cfg.type || "stdio") + '</td>' +
            '<td style="padding:6px 8px; max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="' + target + '">' + target + '</td>' +
            '<td style="padding:6px 8px; text-align:center;"><input type="checkbox" ' + checked + ' data-toggle-mcp="' + esc(name) + '"></td>' +
            '<td style="padding:6px 8px; text-align:right;"><button class="btn btn-ghost" data-delete-mcp="' + esc(name) + '" style="padding:2px 8px; font-size:11px; color:var(--red);">Remove</button></td>' +
            '</tr>';
    }
    html += '</table>';
    el.innerHTML = html;
}

async function toggleMcpServer(name, enabled) {
    try {
        await apiFetch("/mcp/servers/" + encodeURIComponent(name), {
            method: "PUT",
            headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            body: JSON.stringify({enabled: enabled}),
        });
        showToast("MCP server " + name + " " + (enabled ? "enabled" : "disabled"), "success");
    } catch (err) {
        showToast("Failed to update: " + err.message, "error");
        loadWorkspace();
    }
}
window.toggleMcpServer = toggleMcpServer;

async function deleteMcpServer(name) {
    if (!confirm("Remove MCP server '" + name + "'?")) return;
    try {
        await apiFetch("/mcp/servers/" + encodeURIComponent(name), {
            method: "DELETE",
            headers: {"X-Requested-With": "XMLHttpRequest"},
        });
        showToast("MCP server removed: " + name, "success");
        loadWorkspace();
    } catch (err) {
        showToast("Failed to remove: " + err.message, "error");
    }
}
window.deleteMcpServer = deleteMcpServer;

async function addMcpServer() {
    var name = document.getElementById("mcp-name").value.trim();
    var type = document.getElementById("mcp-type").value;
    if (!name) { showToast("Name is required", "error"); return; }
    var body = {name: name, type: type, enabled: true};
    if (type === "stdio") {
        var cmdRaw = document.getElementById("mcp-command").value.trim();
        if (!cmdRaw) { showToast("Command is required", "error"); return; }
        var parts = cmdRaw.split(/\\s+/);
        body.command = parts[0];
        if (parts.length > 1) body.args = parts.slice(1);
    } else {
        var url = document.getElementById("mcp-url").value.trim();
        if (!url) { showToast("URL is required", "error"); return; }
        body.url = url;
    }
    var envInputs = document.querySelectorAll(".mcp-env-input");
    if (envInputs.length > 0) {
        var envObj = {}, missing = [];
        envInputs.forEach(function(inp) {
            var k = inp.getAttribute("data-env-key"), v = inp.value.trim();
            if (v) envObj[k] = v; else missing.push(k);
        });
        if (missing.length) { showToast("Required: " + missing.join(", "), "error"); return; }
        if (Object.keys(envObj).length) body.env = envObj;
    }
    try {
        await apiFetch("/mcp/servers", {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            body: JSON.stringify(body),
        });
        showToast("MCP server added: " + name, "success");
        document.getElementById("mcp-add-form").style.display = "none";
        document.getElementById("mcp-name").value = "";
        document.getElementById("mcp-command").value = "";
        document.getElementById("mcp-url").value = "";
        document.getElementById("mcp-env-fields").style.display = "none";
        document.getElementById("mcp-env-list").innerHTML = "";
        var cl = document.querySelector("#mcp-stdio-fields label");
        if (cl) cl.textContent = "Command";
        loadWorkspace();
    } catch (err) {
        showToast("Failed to add: " + err.message, "error");
    }
}

/* -- MCP Catalog --------------------------------------------------- */
var MCP_CATALOG = [
    { category: "Web & Data", items: [
        { name: "fetch", desc: "Fetch web pages and extract content as markdown", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "mcp/fetch"] },
            { label: "npx", command: "npx", args: ["-y", "@anthropic-ai/mcp-server-fetch"] },
            { label: "uvx", command: "uvx", args: ["mcp-server-fetch"] },
        ]},
        { name: "brave-search", desc: "Web search via Brave Search API", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-e", "BRAVE_API_KEY", "mcp/brave-search"] },
            { label: "npx", command: "npx", args: ["-y", "@anthropic-ai/mcp-server-brave-search"] },
        ], env: [{ key: "BRAVE_API_KEY", hint: "From search.brave.com/api" }]},
    ]},
    { category: "Developer Tools", items: [
        { name: "github", desc: "GitHub repos, issues, PRs, code search", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "mcp/github"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-github"] },
        ], env: [{ key: "GITHUB_PERSONAL_ACCESS_TOKEN", hint: "GitHub PAT with repo scope" }]},
        { name: "git", desc: "Git operations: log, diff, blame, branch management", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "mcp/git"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-git"] },
            { label: "uvx", command: "uvx", args: ["mcp-server-git"] },
        ]},
        { name: "playwright", desc: "Browser automation: navigate, click, screenshot, scrape", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "mcp/playwright"] },
            { label: "npx", command: "npx", args: ["-y", "@anthropic-ai/mcp-server-playwright"] },
        ]},
        { name: "filesystem", desc: "Read, write, and manage files in a directory", runners: [
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"] },
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-v", "/tmp:/tmp", "mcp/filesystem", "/tmp"] },
        ]},
    ]},
    { category: "Productivity", items: [
        { name: "slack", desc: "Read/send Slack messages, manage channels", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-e", "SLACK_BOT_TOKEN", "-e", "SLACK_TEAM_ID", "mcp/slack"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-slack"] },
        ], env: [
            { key: "SLACK_BOT_TOKEN", hint: "xoxb-... from Slack app config" },
            { key: "SLACK_TEAM_ID", hint: "Workspace ID (starts with T)" },
        ]},
        { name: "google-drive", desc: "Search and read Google Drive documents", runners: [
            { label: "npx", command: "npx", args: ["-y", "@anthropic-ai/mcp-server-gdrive"] },
        ], env: [{ key: "GDRIVE_CREDENTIALS_PATH", hint: "Path to OAuth credentials JSON" }]},
        { name: "memory", desc: "Persistent key-value memory for agents", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "mcp/memory"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-memory"] },
        ]},
    ]},
    { category: "Databases", items: [
        { name: "postgres", desc: "Query PostgreSQL databases (read-only by default)", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-e", "POSTGRES_CONNECTION_STRING", "mcp/postgres"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-postgres"] },
        ], env: [{ key: "POSTGRES_CONNECTION_STRING", hint: "postgresql://user:pass@host/db" }]},
        { name: "sqlite", desc: "Query and manage SQLite databases", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "mcp/sqlite"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-sqlite"] },
            { label: "uvx", command: "uvx", args: ["mcp-server-sqlite"] },
        ]},
    ]},
];
function openMcpCatalog() {
    document.getElementById("mcp-catalog-overlay").style.display = "flex";
    document.getElementById("mcp-catalog-search").value = "";
    renderCatalog("");
}
function closeMcpCatalog() { document.getElementById("mcp-catalog-overlay").style.display = "none"; }
function renderCatalog(filter) {
    var el = document.getElementById("mcp-catalog-body"), html = "", lf = filter.toLowerCase();
    for (var c = 0; c < MCP_CATALOG.length; c++) {
        var cat = MCP_CATALOG[c];
        var items = cat.items.filter(function(it) { return !lf || it.name.indexOf(lf)>=0 || it.desc.toLowerCase().indexOf(lf)>=0; });
        if (!items.length) continue;
        html += '<div style="margin-top:12px;margin-bottom:6px;font-size:11px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;">' + esc(cat.category) + '</div>';
        for (var i = 0; i < items.length; i++) {
            var it = items[i], badges = "";
            for (var r = 0; r < it.runners.length; r++) {
                var bg = it.runners[r].label==="Docker"?"#0db7ed":it.runners[r].label==="npx"?"#cb3837":"#7c3aed";
                badges += '<span style="display:inline-block;padding:1px 6px;font-size:10px;border-radius:3px;background:'+bg+';color:#fff;margin-left:4px;">'+esc(it.runners[r].label)+'</span>';
            }
            var envHint = (it.env&&it.env.length) ? '<div style="font-size:10px;color:var(--yellow);margin-top:2px;">Requires: '+it.env.map(function(e){return esc(e.key);}).join(", ")+'</div>' : "";
            html += '<div data-mcp-preset="'+esc(it.name)+'" class="mcp-preset-card">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;"><div style="font-size:13px;font-weight:500;color:var(--text);font-family:monospace;">'+esc(it.name)+'</div><div>'+badges+'</div></div>' +
                '<div style="font-size:12px;color:var(--dim);margin-top:2px;">'+esc(it.desc)+'</div>'+envHint+'</div>';
        }
    }
    if (!html) html = '<div style="padding:20px;text-align:center;color:var(--dim);font-size:13px;">No servers match your search.</div>';
    el.innerHTML = html;
}
function selectMcpPreset(name) {
    var preset = null;
    for (var c = 0; c < MCP_CATALOG.length && !preset; c++)
        for (var i = 0; i < MCP_CATALOG[c].items.length; i++)
            if (MCP_CATALOG[c].items[i].name === name) { preset = MCP_CATALOG[c].items[i]; break; }
    if (!preset) return;
    closeMcpCatalog();
    var runner = preset.runners[0];
    document.getElementById("mcp-add-form").style.display = "block";
    document.getElementById("mcp-form-title").textContent = preset.name;
    document.getElementById("btn-mcp-back-catalog").style.display = "inline-block";
    document.getElementById("mcp-name").value = preset.name;
    document.getElementById("mcp-type").value = "stdio";
    document.getElementById("mcp-stdio-fields").style.display = "block";
    document.getElementById("mcp-url-fields").style.display = "none";
    document.getElementById("mcp-command").value = runner.command + " " + runner.args.join(" ");
    var cmdLabel = document.querySelector("#mcp-stdio-fields label");
    if (preset.runners.length > 1) {
        var picker = '<span style="float:right;">';
        for (var r = 0; r < preset.runners.length; r++) {
            var rn = preset.runners[r], sel = r===0?"background:var(--accent);color:#fff;":"background:var(--surface);color:var(--dim);";
            picker += '<button type="button" class="mcp-runner-btn" data-runner-idx="'+r+'" style="padding:1px 8px;font-size:10px;border:1px solid var(--card);border-radius:3px;margin-left:3px;cursor:pointer;'+sel+'">'+esc(rn.label)+'</button>';
        }
        cmdLabel.innerHTML = "Command " + picker + "</span>";
        setTimeout(function() {
            document.querySelectorAll(".mcp-runner-btn").forEach(function(btn) {
                btn.addEventListener("click", function() {
                    var idx = parseInt(this.getAttribute("data-runner-idx")), rn = preset.runners[idx];
                    document.getElementById("mcp-command").value = rn.command + " " + rn.args.join(" ");
                    document.querySelectorAll(".mcp-runner-btn").forEach(function(b){b.style.background="var(--surface)";b.style.color="var(--dim)";});
                    this.style.background="var(--accent)"; this.style.color="#fff";
                    updateEnvFields(preset);
                });
            });
        }, 0);
    } else { cmdLabel.textContent = "Command"; }
    updateEnvFields(preset);
}
function updateEnvFields(preset) {
    var envDiv = document.getElementById("mcp-env-fields"), envList = document.getElementById("mcp-env-list");
    var envVars = preset.env || [];
    if (!envVars.length) { envDiv.style.display = "none"; envList.innerHTML = ""; return; }
    envDiv.style.display = "block";
    var html = "";
    for (var i = 0; i < envVars.length; i++) {
        var ev = envVars[i];
        html += '<div style="display:flex;gap:6px;align-items:center;margin-top:4px;"><code style="font-size:11px;color:var(--dim);min-width:180px;white-space:nowrap;">'+esc(ev.key)+'</code>' +
            '<input type="text" class="mcp-env-input" data-env-key="'+esc(ev.key)+'" placeholder="'+esc(ev.hint||"")+'" style="flex:1;padding:4px 8px;background:var(--surface);border:1px solid var(--card);border-radius:4px;color:var(--text);font-size:12px;"></div>';
    }
    envList.innerHTML = html;
}
/* MCP form + catalog wiring */
(function() {
    document.addEventListener("DOMContentLoaded", function() {
        document.getElementById("btn-mcp-add").addEventListener("click", openMcpCatalog);
        var ov = document.getElementById("mcp-catalog-overlay");
        ov.addEventListener("click", function(e){if(e.target===ov)closeMcpCatalog();});
        document.getElementById("mcp-catalog-close").addEventListener("click", closeMcpCatalog);
        document.getElementById("mcp-catalog-search").addEventListener("input", function(){renderCatalog(this.value);});
        document.getElementById("mcp-catalog-body").addEventListener("click", function(e){
            var card = e.target.closest("[data-mcp-preset]");
            if (card) selectMcpPreset(card.getAttribute("data-mcp-preset"));
        });
        document.getElementById("mcp-catalog-custom").addEventListener("click", function(){
            closeMcpCatalog();
            document.getElementById("mcp-add-form").style.display = "block";
            document.getElementById("mcp-form-title").textContent = "Custom Server";
            document.getElementById("btn-mcp-back-catalog").style.display = "inline-block";
            document.getElementById("mcp-name").value = "";
            document.getElementById("mcp-command").value = "";
            document.getElementById("mcp-url").value = "";
            document.getElementById("mcp-env-fields").style.display = "none";
            document.querySelector("#mcp-stdio-fields label").textContent = "Command";
        });
        document.getElementById("btn-mcp-back-catalog").addEventListener("click", function(){
            document.getElementById("mcp-add-form").style.display = "none"; openMcpCatalog();
        });
        document.getElementById("btn-mcp-cancel").addEventListener("click", function(){
            document.getElementById("mcp-add-form").style.display = "none";
        });
        document.getElementById("btn-mcp-save").addEventListener("click", addMcpServer);
        document.getElementById("mcp-type").addEventListener("change", function(){
            var s = this.value==="stdio";
            document.getElementById("mcp-stdio-fields").style.display = s?"block":"none";
            document.getElementById("mcp-url-fields").style.display = s?"none":"block";
        });
    });
})();
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

async function toggleLiveTail() {
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

    var token = await ensureAdminSession();
    if (!token) {
        liveTailActive = false;
        btn.classList.remove("active");
        showToast("Admin token required for live tail", "warning");
        return;
    }

    var url = API.replace("/api", "") + "/api/logs/stream";
    liveTailSource = new EventSource(url);

    liveTailSource.onmessage = function(event) {
        var viewer = document.getElementById("log-viewer-content");
        var container = document.getElementById("log-viewer");
        var text = event.data;
        try {
            var parsed = JSON.parse(event.data);
            if (parsed && typeof parsed === "object") {
                text = parsed.line || parsed.message || parsed.text || JSON.stringify(parsed);
            }
        } catch (err) {
            text = event.data;
        }
        text = String(text || "");
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

async function exportDb() {
    if (!await ensureAdminSession()) return;
    window.open(API + "/db/export", "_blank");
}
window.exportDb = exportDb;

async function purgeMessages() {
    var days = parseInt(document.getElementById("purge-days-input").value, 10);
    if (!Number.isFinite(days) || days < 1) {
        showToast("Purge days must be at least 1", "warning");
        return;
    }
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

async function downloadBackup(filename) {
    if (!await ensureAdminSession()) return;
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
    } else if (e.target.matches("[data-toggle-mcp]")) {
        toggleMcpServer(e.target.dataset.toggleMcp, e.target.checked);
    } else if (e.target.matches("[data-config-field]")) {
        markDirty(e.target.dataset.section, e.target.dataset.key);
    }
});
document.addEventListener("input", function(e) {
    if (e.target.matches("[data-config-field]")) {
        markDirty(e.target.dataset.section, e.target.dataset.key);
    } else if (e.target.id === "persona-system-prompt") {
        syncPersonaGuidance(false);
    }
});
document.addEventListener("click", function(e) {
    var btn;
    if ((btn = e.target.closest(".nav-item[data-page]"))) {
        if (!btn.classList.contains("nav-disabled")) navigateTo(btn.dataset.page);
    } else if ((btn = e.target.closest("[data-policy-level-card]"))) {
        selectedPolicyLevel = Number(btn.dataset.policyLevelCard);
        renderPolicyLevelGuide();
    } else if ((btn = e.target.closest("#btn-menu-hamburger"))) {
        toggleSidebar();
    } else if ((btn = e.target.closest("#sidebar-overlay"))) {
        closeSidebar();
    } else if ((btn = e.target.closest("[data-close-modal]"))) {
        closeModal(btn.dataset.closeModal);
    } else if ((btn = e.target.closest("[data-persona-id]"))) {
        selectPersona(decodeURIComponent(btn.dataset.personaId));
    } else if ((btn = e.target.closest("[data-delete-whitelist]"))) {
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
    } else if ((btn = e.target.closest("[data-remove-san]"))) {
        removeSAN(parseInt(btn.dataset.removeSan, 10));
    } else if ((btn = e.target.closest("[data-generate-ca]"))) {
        generateCA(btn.dataset.generateCa === "true");
    } else if ((btn = e.target.closest("[data-renew-server]"))) {
        renewServer();
    } else if ((btn = e.target.closest("[data-open-san-editor]"))) {
        openSANEditor();
    } else if ((btn = e.target.closest("[data-delete-mcp]"))) {
        deleteMcpServer(btn.dataset.deleteMcp);
    } else if ((btn = e.target.closest("[data-policy-save]"))) {
        savePersonaPolicyLevel(btn.dataset.policySave);
    } else if ((btn = e.target.closest("[data-policy-elevate]"))) {
        elevatePersonaPolicy(btn.dataset.policyElevate);
    } else if ((btn = e.target.closest("[data-policy-revoke]"))) {
        revokePersonaPolicy(btn.dataset.policyRevoke);
    } else if ((btn = e.target.closest("[data-policy-guardrails-save]"))) {
        savePolicyGuardrails();
    } else if ((btn = e.target.closest("[data-policy-guardrails-reset]"))) {
        resetPolicyGuardrails();
    } else if ((btn = e.target.closest("[data-policy-workspace-save]"))) {
        saveWorkspaceToolPolicy();
    } else if ((btn = e.target.closest("[data-policy-workspace-reset]"))) {
        resetWorkspaceToolPolicyDefaults();
    }
});

/* =====================================================================
   Initialization
   ===================================================================== */

function bindClick(id, handler) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", handler);
}

function init() {
    applyTheme();
    syncPersonaGuidance(true);
    bindClick("btn-refresh", loadHealth);
    bindClick("btn-quick-test-alerts", quickActionTestAlerts);
    bindClick("btn-quick-backup", quickActionCreateBackup);
    bindClick("btn-quick-logs", function() { navigateTo("logs"); });
    bindClick("btn-tls-refresh", loadTLS);
    bindClick("btn-new-client", openNewClientDialog);
    bindClick("btn-models-refresh", loadModels);
    bindClick("btn-set-default-model", setDefaultModel);
    bindClick("btn-save-telegram-config", saveTelegramConfig);
    bindClick("btn-test-alerts", testAlerts);
    bindClick("btn-rotate-token", rotateAlertToken);
    bindClick("btn-personas-refresh", loadPersonas);
    bindClick("btn-personas-new", newPersonaForm);
    bindClick("btn-persona-guidance-toggle", togglePersonaGuidance);
    bindClick("btn-persona-save", savePersona);
    bindClick("btn-persona-reset-form", newPersonaForm);
    bindClick("btn-persona-reset-prompt", resetPersonaPrompt);
    bindClick("btn-persona-delete", deletePersona);
    bindClick("btn-policy-refresh", loadPolicies);
    bindClick("btn-workspace-refresh", loadWorkspace);
    bindClick("btn-projectmd-load", loadProjectMd);
    bindClick("btn-projectmd-save", saveProjectMd);
    bindClick("btn-mcp-cancel", function() {
        document.getElementById("mcp-add-form").style.display = "none";
    });
    bindClick("btn-add-san", addSAN);
    bindClick("btn-generate-client", generateClient);
    bindClick("btn-save-credential", saveCredential);
    bindClick("btn-logs-refresh", loadLogsPage);
    bindClick("btn-logs-load", loadLogs);
    bindClick("btn-livetail", toggleLiveTail);
    bindClick("btn-clear-logs", clearLogs);
    bindClick("btn-vacuum", vacuumDb);
    bindClick("btn-export-db", exportDb);
    bindClick("btn-purge-messages", purgeMessages);
    bindClick("btn-cleanup-uploads", cleanupUploads);
    bindClick("btn-create-backup", createBackup);
    bindClick("btn-save-sans", saveSANs);
    bindClick("btn-activate-license", activateLicense);

    /* Route from URL hash */
    var route = parseDashboardHash(window.location.hash);
    currentPersonaId = route.personaId ? decodeURIComponent(route.personaId) : "";
    if (route.page) {
        navigateTo(route.page);
    } else {
        /* Default: health page */
        currentPage = "health";
        loadHealth();
        startAutoRefresh();
    }

    /* Listen for hash changes (browser back/forward) */
    window.addEventListener("hashchange", function() {
        var nextRoute = parseDashboardHash(window.location.hash);
        if (!nextRoute.page) return;
        currentPersonaId = nextRoute.personaId ? decodeURIComponent(nextRoute.personaId) : "";
        if (nextRoute.page !== currentPage) {
            navigateTo(nextRoute.page);
        } else if (nextRoute.page === "personas") {
            loadPersonas();
        } else if (nextRoute.page === "policy") {
            loadPolicies();
        }
    });

    window.addEventListener("storage", function(event) {
        if (event.key === "themeMode") syncThemeFromPreference();
    });

    if (systemThemeQuery) {
        var handleSystemThemeChange = function(event) {
            if (!localStorage.getItem("themeMode")) {
                themeMode = event.matches ? "light" : "dark";
                applyTheme();
            }
        };
        if (typeof systemThemeQuery.addEventListener === "function") {
            systemThemeQuery.addEventListener("change", handleSystemThemeChange);
        } else if (typeof systemThemeQuery.addListener === "function") {
            systemThemeQuery.addListener(handleSystemThemeChange);
        }
    }
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
