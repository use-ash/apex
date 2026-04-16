# Auto-extracted from dashboard_html.py during modular split.

DASHBOARD_CSS = r"""/* ===================================================================
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
   Components: Usage Page
   =================================================================== */

.usage-month-picker {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border: 1px solid var(--card);
    border-radius: var(--radius);
    background: var(--surface);
}

.usage-month-picker .btn {
    padding: 6px 10px;
}

.usage-month-label {
    min-width: 124px;
    text-align: center;
    font-size: 13px;
    font-weight: 600;
}

.usage-hero-card {
    padding: 0;
    overflow: hidden;
    margin-bottom: 20px;
}

.usage-hero-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

.usage-hero-pane {
    padding: 20px;
}

.usage-hero-pane + .usage-hero-pane {
    border-left: 1px solid var(--soft-border);
}

.usage-hero-kicker {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim);
    margin-bottom: 10px;
}

.usage-hero-value {
    font-size: 30px;
    font-weight: 700;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
}

.usage-hero-sub {
    margin-top: 8px;
    color: var(--dim);
    font-size: 13px;
}

.usage-hero-meta {
    margin-top: 10px;
    color: var(--dim);
    font-size: 12px;
}

.usage-progress {
    margin-top: 14px;
    height: 8px;
    border-radius: 999px;
    background: var(--card);
    overflow: hidden;
}

.usage-progress-fill {
    height: 100%;
    border-radius: 999px;
    background: var(--accent);
    transition: width 0.25s ease;
}

.usage-progress-fill.warning {
    background: var(--yellow);
}

.usage-progress-fill.critical {
    background: var(--red);
}

.usage-insight-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 16px 20px;
    border-top: 1px solid var(--soft-border);
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.08), rgba(14, 165, 233, 0.03));
}

.usage-insight-row svg {
    width: 16px;
    height: 16px;
    color: var(--accent);
    flex-shrink: 0;
    margin-top: 2px;
}

.usage-insight-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
}

.usage-insight-body {
    margin-top: 2px;
    font-size: 13px;
    color: var(--dim);
}

.usage-sparkline {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(24px, 1fr));
    gap: 8px;
    align-items: end;
    min-height: 168px;
}

.usage-spark-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 0;
}

.usage-spark-bar-wrap {
    width: 100%;
    height: 120px;
    display: flex;
    align-items: flex-end;
    justify-content: center;
}

.usage-spark-bar {
    width: 100%;
    min-height: 4px;
    border-radius: 8px 8px 0 0;
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.95), rgba(14, 165, 233, 0.45));
}

.usage-spark-bar.today {
    background: linear-gradient(180deg, rgba(245, 158, 11, 0.95), rgba(245, 158, 11, 0.45));
}

.usage-spark-label {
    font-size: 11px;
    color: var(--dim);
    font-variant-numeric: tabular-nums;
}

.usage-spark-amount {
    font-size: 11px;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}

.usage-provider-list {
    display: grid;
    gap: 12px;
}

.usage-provider-item {
    padding: 14px;
    border: 1px solid var(--soft-border);
    border-radius: var(--radius);
    background: rgba(15, 23, 42, 0.12);
}

.usage-provider-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
}

.usage-provider-name {
    font-size: 14px;
    font-weight: 600;
}

.usage-provider-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
}

.usage-provider-stats {
    display: grid;
    gap: 6px;
}

.usage-provider-stat {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 12px;
}

.usage-provider-stat .label {
    color: var(--dim);
}

.usage-provider-stat .value {
    font-variant-numeric: tabular-nums;
}

.usage-track-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border: 1px solid transparent;
}

.usage-track-badge.api {
    color: #fff;
    background: rgba(14, 165, 233, 0.2);
    border-color: rgba(14, 165, 233, 0.35);
}

.usage-track-badge.subscription {
    color: #FDE68A;
    background: rgba(245, 158, 11, 0.14);
    border-color: rgba(245, 158, 11, 0.3);
}

.usage-track-badge.local {
    color: var(--dim);
    background: rgba(148, 163, 184, 0.12);
    border-color: rgba(148, 163, 184, 0.24);
}

.usage-table-wrap {
    overflow: auto;
    border: 1px solid var(--soft-border);
    border-radius: var(--radius);
}

.usage-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.usage-table th {
    text-align: left;
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim);
    border-bottom: 1px solid var(--card);
    white-space: nowrap;
}

.usage-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--soft-border);
    vertical-align: top;
}

.usage-table tbody tr:last-child td {
    border-bottom: none;
}

.usage-table tbody tr:hover {
    background: var(--hover-subtle);
}

.usage-cell-primary {
    font-weight: 500;
}

.usage-cell-sub {
    margin-top: 4px;
    font-size: 11px;
    color: var(--dim);
}

.usage-secondary-grid,
.usage-breakdown-grid {
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

@media (max-width: 768px) {
    .usage-hero-grid {
        grid-template-columns: 1fr;
    }

    .usage-hero-pane + .usage-hero-pane {
        border-left: none;
        border-top: 1px solid var(--soft-border);
    }

    .usage-month-picker {
        width: 100%;
        justify-content: space-between;
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

/* -- Memory page --------------------------------------------------- */

.memory-type-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.memory-type-badge.invariant { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.memory-type-badge.correction { background: rgba(250, 204, 21, 0.15); color: #facc15; }
.memory-type-badge.decision { background: rgba(74, 222, 128, 0.15); color: #4ade80; }
.memory-type-badge.context { background: rgba(168, 85, 247, 0.15); color: #a855f7; }
.memory-type-badge.pending { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
.memory-type-badge.note { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
.memory-type-badge.unknown { background: rgba(148, 163, 184, 0.10); color: #64748b; }

.memory-pathway-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}
.memory-pathway-badge.type1 { background: rgba(45, 212, 191, 0.15); color: #2dd4bf; }
.memory-pathway-badge.type2 { background: rgba(129, 140, 248, 0.15); color: #818cf8; }

.memory-item-text {
    font-size: 12px;
    color: var(--dim);
    max-width: 500px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: inline-block;
}
.memory-item-expand {
    cursor: default;
    position: relative;
}
.memory-item-expand .memory-item-full {
    display: none;
    position: absolute;
    z-index: 120;
    left: 0;
    top: calc(100% + 4px);
    width: 480px;
    max-height: 220px;
    overflow-y: auto;
    padding: 10px 12px;
    background: var(--surface);
    border: 1px solid var(--soft-border);
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    font-size: 12px;
    line-height: 1.5;
    color: var(--text);
    white-space: normal;
    word-break: break-word;
    pointer-events: auto;
}
.memory-item-expand:hover .memory-item-full {
    display: block;
}

.contradiction-card {
    border: 1px solid var(--soft-border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}
.contradiction-card:last-child { margin-bottom: 0; }

.contradiction-claims {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 12px;
    margin-bottom: 12px;
}
.contradiction-claim {
    padding: 10px;
    background: var(--surface);
    border-radius: 6px;
}
.contradiction-vs {
    display: flex;
    align-items: center;
    font-weight: 700;
    color: var(--dim);
    font-size: 12px;
}
.contradiction-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.memory-score-bar {
    height: 4px;
    border-radius: 2px;
    background: var(--soft-border);
    overflow: hidden;
    margin-top: 4px;
}
.memory-score-fill {
    height: 100%;
    border-radius: 2px;
    background: var(--accent);
    transition: width 0.3s ease;
}
.memory-search-result {
    padding: 12px;
    border: 1px solid var(--soft-border);
    border-radius: 8px;
    margin-top: 8px;
}
.memory-search-result + .memory-search-result { margin-top: 8px; }

/* -- Memory config grid + info tooltips ------------------------------ */

.memory-config-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 32px;
}
.memory-config-grid .form-field {
    margin-bottom: 8px;
}
.memory-config-grid .config-actions {
    grid-column: 1 / -1;
}
.form-label-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}
.form-label-row .form-label {
    margin-bottom: 0;
}
.btn-field-info {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 1px solid var(--dim);
    background: transparent;
    color: var(--dim);
    font-size: 11px;
    font-weight: 700;
    font-style: italic;
    font-family: Georgia, serif;
    line-height: 1;
    padding: 0;
    cursor: pointer;
    flex-shrink: 0;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    position: relative;
}
.btn-field-info:hover {
    border-color: var(--accent);
    color: var(--accent);
}
.btn-field-info.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
}
.field-tooltip {
    display: none;
    position: absolute;
    z-index: 100;
    top: calc(100% + 8px);
    left: 0;
    width: 300px;
    padding: 10px 12px;
    background: var(--surface);
    border: 1px solid var(--soft-border);
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    font-size: 12px;
    font-style: normal;
    font-weight: 400;
    line-height: 1.5;
    color: var(--text);
    white-space: normal;
}
.field-tooltip.visible { display: block; }
.field-tooltip-arrow {
    position: absolute;
    top: -5px;
    left: 12px;
    width: 10px;
    height: 10px;
    background: var(--surface);
    border-top: 1px solid var(--soft-border);
    border-left: 1px solid var(--soft-border);
    transform: rotate(45deg);
}
.field-tooltip strong {
    color: var(--accent);
    font-weight: 600;
}

@media (max-width: 900px) {
    .memory-config-grid {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 800px) {
    .contradiction-claims {
        grid-template-columns: 1fr;
    }
    .contradiction-vs {
        justify-content: center;
        padding: 4px 0;
    }
}"""
