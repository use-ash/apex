# Auto-extracted from dashboard_html.py during modular split.

DASHBOARD_BODY_HTML = r"""<body>

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
            <!-- Database -->
            <div class="nav-item" data-page="database">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <ellipse cx="12" cy="5" rx="9" ry="3"/>
                    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                </svg>
                Database
            </div>
            <!-- Usage -->
            <div class="nav-item" data-page="usage">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 19h16"/>
                    <path d="M7 16V9"/>
                    <path d="M12 16V5"/>
                    <path d="M17 16v-3"/>
                </svg>
                Usage
            </div>
            <!-- Workspace -->
            <div class="nav-item" data-page="workspace">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Workspace
            </div>
            <!-- Memory -->
            <div class="nav-item" data-page="memory">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2a7 7 0 0 0-7 7c0 2.5 1.5 4.5 3 5.5V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.5c1.5-1 3-3 3-5.5a7 7 0 0 0-7-7z"/>
                    <line x1="10" y1="21" x2="14" y2="21"/>
                    <line x1="9" y1="17" x2="15" y2="17"/>
                </svg>
                Memory
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

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                        DeepSeek
                    </div>
                    <div id="provider-deepseek-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                        Zhipu (GLM)
                    </div>
                    <div id="provider-zhipu-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
                        Gemini
                    </div>
                    <div id="provider-gemini-content">
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

        <div class="page" id="page-database">
            <div class="page-header">
                <h2>Database</h2>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <button class="btn btn-ghost" id="btn-database-refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>

            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 8v4l3 3"/>
                    </svg>
                    Status
                </div>
                <div id="database-status-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading database status...</div>
                </div>
            </div>

            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Tables</span>
                </div>
                <div id="database-tables-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading table inventory...</div>
                </div>
            </div>

            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Retention Policies</span>
                </div>
                <div class="form-help" style="margin-bottom:12px;">Retention settings are not yet backed by a dedicated V2 API. Current cleanup uses the Logs page purge action for old messages only.</div>
                <div id="database-retention-content"></div>
            </div>

            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Actions</span>
                </div>
                <div class="form-help" style="margin-bottom:12px;">Backup and restore operate on the existing tarball backup system. Purge currently deletes messages older than the selected age.</div>
                <div id="database-actions-content"></div>
            </div>
        </div>

        <div class="page" id="page-usage">
            <div class="page-header">
                <h2>Usage</h2>
                <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                    <div class="usage-month-picker" aria-label="Usage month picker">
                        <button class="btn btn-ghost btn-sm" id="btn-usage-prev-month" aria-label="Previous month">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                                <polyline points="15 18 9 12 15 6"/>
                            </svg>
                        </button>
                        <span class="usage-month-label mono" id="usage-month-label">Loading…</span>
                        <button class="btn btn-ghost btn-sm" id="btn-usage-next-month" aria-label="Next month">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                                <polyline points="9 18 15 12 9 6"/>
                            </svg>
                        </button>
                    </div>
                    <button class="btn btn-ghost" id="btn-usage-refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="btn btn-ghost" id="btn-usage-export">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Export CSV
                    </button>
                </div>
            </div>

            <div class="card usage-hero-card" id="usage-hero-content">
                <div class="loading-overlay"><div class="spinner"></div> Loading usage summary...</div>
            </div>

            <div class="card" style="margin-bottom:20px;">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 3v18h18"/>
                        <path d="M7 15l3-3 3 2 4-6"/>
                    </svg>
                    Daily API Spend (last 14 days)
                </div>
                <div id="usage-daily-spend-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading daily spend...</div>
                </div>
            </div>

            <div class="card-grid usage-secondary-grid">
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 6v6l4 2"/>
                        </svg>
                        Providers &amp; Utilization
                    </div>
                    <div id="usage-providers-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading providers...</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="3"/>
                            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
                        </svg>
                        Budget Settings
                    </div>
                    <div id="usage-budget-content">
                        <div class="form-help" id="usage-budget-status" style="margin-bottom:12px;">Tracks actual API spend separately from included subscription usage.</div>
                        <div class="form-field">
                            <label class="form-label" for="usage-budget-input">Monthly API budget (USD)</label>
                            <input id="usage-budget-input" type="number" min="0" max="100000" step="1" inputmode="numeric">
                        </div>
                        <div class="form-field">
                            <label class="form-label" for="usage-alert-input">Alert threshold (%)</label>
                            <input id="usage-alert-input" type="number" min="1" max="100" step="1" inputmode="numeric">
                        </div>
                        <div class="form-field">
                            <label class="form-label" for="usage-reset-input">Reset day of month</label>
                            <input id="usage-reset-input" type="number" min="1" max="28" step="1" inputmode="numeric">
                        </div>
                        <div class="form-field">
                            <label class="form-label" for="usage-primary-user-input">Primary interactive user label</label>
                            <input id="usage-primary-user-input" type="text" maxlength="80" placeholder="Dana">
                        </div>
                        <div class="config-actions" style="margin-top:16px;">
                            <button class="btn btn-primary" id="btn-usage-save-config">Save Usage Settings</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card-grid usage-breakdown-grid">
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                            <circle cx="12" cy="7" r="4"/>
                        </svg>
                        By Speaker
                    </div>
                    <div class="form-help" style="margin-bottom:12px;">Grouped by persona name — does not reconcile 1:1 with model rows.</div>
                    <div id="usage-by-agent-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading speaker breakdown...</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                            <circle cx="9" cy="7" r="4"/>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                        </svg>
                        By User
                    </div>
                    <div id="usage-by-user-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading user breakdown...</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                            <polyline points="2 17 12 22 22 17"/>
                            <polyline points="2 12 12 17 22 12"/>
                        </svg>
                        By Model
                    </div>
                    <div id="usage-by-model-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading model breakdown...</div>
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
             MEMORY PAGE
             ========================================================= -->
        <div class="page" id="page-memory">
            <div class="page-header">
                <h2>Memory</h2>
                <button class="btn btn-ghost" id="btn-memory-refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                    Refresh
                </button>
            </div>

            <!-- Status Banner -->
            <div id="memory-status-banner" class="health-banner banner-ok" style="margin-bottom:20px">
                <div class="banner-left">
                    <span class="banner-dot"></span>
                    <span id="memory-status-text">Loading memory status...</span>
                </div>
                <div class="banner-right" id="memory-status-meta"></div>
            </div>

            <!-- Overview Cards -->
            <div class="card-grid" id="memory-overview-cards">
                <div class="card" id="card-memory-type1">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                        </svg>
                        Type 1 &mdash; Procedural
                    </div>
                    <div id="memory-type1-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>
                <div class="card" id="card-memory-type2">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 16v-4"/>
                            <path d="M12 8h.01"/>
                        </svg>
                        Type 2 &mdash; Declarative
                    </div>
                    <div id="memory-type2-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>
                <div class="card" id="card-memory-metacog">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <circle cx="11" cy="11" r="8"/>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                        Metacognition Index
                    </div>
                    <div id="memory-metacog-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>
                <div class="card" id="card-memory-feedback">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                        </svg>
                        Whisper Feedback
                    </div>
                    <div id="memory-feedback-content">
                        <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                    </div>
                </div>
            </div>

            <!-- Guidance Items -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Guidance Items</span>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <select id="memory-guidance-filter" style="font-size:12px; padding:3px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text);">
                            <option value="all">All Types</option>
                            <option value="invariant">Invariants</option>
                            <option value="correction">Corrections</option>
                            <option value="decision">Decisions</option>
                            <option value="context">Context</option>
                            <option value="pending">Pending</option>
                        </select>
                        <select id="memory-pathway-filter" style="font-size:12px; padding:3px 8px; background:var(--surface); border:1px solid var(--card); border-radius:4px; color:var(--text);">
                            <option value="all">All Pathways</option>
                            <option value="type1">Type 1</option>
                            <option value="type2">Type 2</option>
                        </select>
                    </div>
                </div>
                <div id="memory-guidance-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading guidance...</div>
                </div>
            </div>

            <!-- Contradictions -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Pending Contradictions</span>
                    <span class="text-dim" id="memory-contradiction-count" style="font-size:12px;"></span>
                </div>
                <div id="memory-contradictions-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- Metacognition Search -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Metacognition Search</span>
                </div>
                <div class="form-field">
                    <label class="form-label" for="memory-search-input">Test retrieval query</label>
                    <div class="form-help">Enter a message to test what prior knowledge would be retrieved</div>
                    <div style="display:flex; gap:8px;">
                        <input type="text" id="memory-search-input" placeholder="e.g. How should I handle error recovery?" style="flex:1;">
                        <button class="btn btn-primary" id="btn-memory-search">Search</button>
                    </div>
                </div>
                <div id="memory-search-results"></div>
            </div>

            <!-- Operations -->
            <div class="config-section" style="margin-bottom:20px;">
                <div class="config-section-header">
                    <span class="config-section-title">Operations</span>
                </div>
                <div class="form-help" style="margin-bottom:12px;">
                    Manual triggers for background memory processes. These normally run automatically via cron.
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <button class="btn btn-ghost" id="btn-memory-rebuild-index">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                        </svg>
                        Rebuild Index
                    </button>
                    <button class="btn btn-ghost" id="btn-memory-consolidation">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
                        </svg>
                        Consolidation (dry-run)
                    </button>
                    <button class="btn btn-ghost" id="btn-memory-promotion">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                            <line x1="12" y1="19" x2="12" y2="5"/>
                            <polyline points="5 12 12 5 19 12"/>
                        </svg>
                        Check Promotions
                    </button>
                </div>
                <div id="memory-operations-output"></div>
            </div>

            <!-- Extraction Schedule -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Extraction Schedule</span>
                    <span class="text-dim" style="font-size:11px;">crontab</span>
                </div>
                <div id="memory-schedule-content">
                    <div class="loading-overlay"><div class="spinner"></div> Loading...</div>
                </div>
            </div>

            <!-- Configuration -->
            <div class="config-section">
                <div class="config-section-header">
                    <span class="config-section-title">Memory Configuration</span>
                </div>
                <div id="memory-config-content">
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

"""
