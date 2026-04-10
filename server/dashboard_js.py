# Auto-extracted from dashboard_html.py during modular split.

_JS_PREAMBLE = r"""/* =====================================================================
   Apex Dashboard — Client-Side Application
   ===================================================================== */

(function() {
"use strict";

"""

_JS_GLOBALS = r"""/* -- Constants ------------------------------------------------------ */

const API = "/admin/api";
const REFRESH_INTERVAL = 30000;  /* 30 seconds */

let refreshTimer = null;
let currentPage = "health";
let themeMode = localStorage.getItem("themeMode")
    || (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
const systemThemeQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
let personaGuidanceExpanded = true;
let personaGuidanceManual = false;
let usageState = { month: "", payload: null, config: null };

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
    if (hash === "config" || hash === "tls" || hash === "models" || hash === "personas" || hash === "policy" || hash === "database" || hash === "usage" || hash === "workspace" || hash === "logs" || hash === "license") {
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

"""

_JS_NAVIGATION = r"""/* =====================================================================
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
        if (page === "database") loadDatabasePage();
        if (page === "usage") loadUsagePage();
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
            statusText.textContent = `Apex Pro — ${s.tier} license active`;
            const exp = new Date(s.license_expires);
            const daysLeft = Math.max(0, Math.ceil((exp - Date.now()) / 86400000));
            meta.textContent = `${daysLeft} days remaining`;
            details.innerHTML =
                '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px">' +
                '<span style="color:var(--text-dim)">Tier</span><span>' + s.tier + '</span>' +
                '<span style="color:var(--text-dim)">License ID</span><span style="font-family:monospace;font-size:11px">' + (s.license_id || '—') + '</span>' +
                '<span style="color:var(--text-dim)">Expires</span><span>' + (s.license_expires ? new Date(s.license_expires).toLocaleDateString() : '—') + '</span>' +
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
            statusText.textContent = "Free tier — premium features locked";
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

"""

_JS_API_HELPERS = r"""/* =====================================================================
   API Helpers
   ===================================================================== */

var ADMIN_TOKEN_STORAGE_KEY = "apexAdminToken";
var ADMIN_TOKEN_COOKIE = "apex_admin_token";

function getAdminToken() {
    var stored = sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
    if (stored) return stored;
    var match = document.cookie.match(/(?:^|;\s*)apex_admin_token=([^;]+)/);
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

"""

_JS_TOAST = r"""/* =====================================================================
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

"""

_JS_HEALTH = r"""/* =====================================================================
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

"""

_JS_CONFIG = r"""/* =====================================================================
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
        const textValue = String(value || "").split(":").join("\n");
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

"""

_JS_TLS = r"""/* =====================================================================
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

"""

_JS_MODELS = r"""/* =====================================================================
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

"""

_JS_PERSONAS = r"""/* =====================================================================
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
                '<textarea id="policy-never-allowed-commands" rows="8" placeholder="sqlite3&#10;rm -rf&#10;launchctl">' + esc((policyNeverAllowedCommands || []).join('\n')) + '</textarea>' +
            '</div>' +
            '<div class="card policy-mini-card">' +
                '<div class="card-title" style="margin-bottom:8px;">Blocked Path Prefixes</div>' +
                '<div class="form-help" style="margin-bottom:8px;">One absolute path prefix per line. File tools and shell commands touching these locations are denied, even at Full Admin.</div>' +
                '<textarea id="policy-blocked-path-prefixes" rows="8" placeholder="/Users/you/project/state&#10;/Users/you/.ssh">' + esc((policyBlockedPathPrefixes || []).join('\n')) + '</textarea>' +
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

"""

_JS_POLICY = r"""async function loadPolicies() {
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
        .split(/\r?\n/)
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

"""

_JS_WORKSPACE = r"""/* =====================================================================
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
    var pathsText = workspacePaths.join('\n');

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
        var parts = cmdRaw.split(/\s+/);
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
            { label: "uvx", command: "uvx", args: ["mcp-server-fetch"] },
        ]},
        { name: "brave-search", desc: "Web search via Brave Search API", runners: [
            { label: "Docker", command: "docker", args: ["run", "-i", "--rm", "-e", "BRAVE_API_KEY", "mcp/brave-search"] },
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-brave-search"] },
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
            { label: "npx", command: "npx", args: ["-y", "@playwright/mcp"] },
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
            { label: "npx", command: "npx", args: ["-y", "@modelcontextprotocol/server-gdrive"] },
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

"""

_JS_REFRESH_TIMER = r"""/* =====================================================================
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

"""

_JS_FORMATTERS = r"""/* =====================================================================
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

function formatCurrency(amount) {
    var value = Number(amount || 0);
    return value.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function currentMonthKey() {
    var now = new Date();
    return now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0");
}

function shiftMonthKey(monthKey, delta) {
    var raw = String(monthKey || currentMonthKey());
    var parts = raw.split("-");
    var year = parseInt(parts[0], 10);
    var month = parseInt(parts[1], 10);
    if (!Number.isFinite(year) || !Number.isFinite(month)) return currentMonthKey();
    month += delta;
    while (month < 1) {
        year -= 1;
        month += 12;
    }
    while (month > 12) {
        year += 1;
        month -= 12;
    }
    return year + "-" + String(month).padStart(2, "0");
}

function isFutureMonthKey(monthKey) {
    return String(monthKey || "") > currentMonthKey();
}

function providerDisplayName(provider) {
    var key = String(provider || "").toLowerCase();
    if (key === "xai" || key === "grok") return "Grok";
    if (key === "codex") return "Codex";
    if (key === "claude") return "Claude";
    if (key === "gemini") return "Gemini";
    if (key === "openai") return "OpenAI";
    if (key === "local" || key === "ollama" || key === "mlx") return "Local";
    return capitalize(key || "provider");
}

function usageTrackLabel(track) {
    var key = String(track || "local").toLowerCase();
    if (key === "subscription") return "Subscription";
    if (key === "api") return "API";
    return "Local";
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

"""

_JS_LOGS = r"""/* =====================================================================
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
            loadLegacyDbStats(),
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
        html += '<span class="' + cls + '">' + esc(text) + '</span>\n';
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
        viewer.innerHTML += '<span class="' + cls + '">' + esc(text) + '</span>\n';

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

/* -- Usage ----------------------------------------------------------- */

function createNode(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = text;
    return el;
}

function usageLoadingMarkup(message) {
    return '<div class="loading-overlay"><div class="spinner"></div> ' + esc(message || 'Loading...') + '</div>';
}

function updateUsageMonthControls(monthKey, monthLabel) {
    var label = document.getElementById("usage-month-label");
    if (label) label.textContent = monthLabel || monthKey || "—";
    var nextBtn = document.getElementById("btn-usage-next-month");
    if (nextBtn) nextBtn.disabled = isFutureMonthKey(shiftMonthKey(monthKey, 1));
}

function buildUsageProviderRows(payload) {
    var rowsByProvider = {};
    var models = Array.isArray(payload.by_model) ? payload.by_model : [];
    models.forEach(function(model) {
        var providerKey = String(model.provider || "local").toLowerCase();
        if (!rowsByProvider[providerKey]) {
            rowsByProvider[providerKey] = {
                provider: providerKey,
                tracks: {},
                apiCost: 0,
                equivalentCost: 0,
                tokens: 0,
                utilization: null,
            };
        }
        var row = rowsByProvider[providerKey];
        row.tracks[String(model.track || "local").toLowerCase()] = true;
        row.apiCost += Number(model.track === "api" ? (model.cost_usd || 0) : 0);
        row.equivalentCost += Number(model.track === "subscription" ? (model.equivalent_cost_usd || 0) : 0);
        row.tokens += Number(model.tokens_in || 0) + Number(model.tokens_out || 0);
    });

    var tokenProviders = (payload.subscription_track && payload.subscription_track.tokens_by_provider) || {};
    Object.keys(tokenProviders).forEach(function(providerKey) {
        var key = String(providerKey || "local").toLowerCase();
        if (!rowsByProvider[key]) {
            rowsByProvider[key] = {
                provider: key,
                tracks: { subscription: true },
                apiCost: 0,
                equivalentCost: 0,
                tokens: 0,
                utilization: null,
            };
        }
        rowsByProvider[key].tokens = Number(tokenProviders[providerKey] || 0);
    });

    var utilization = payload.provider_utilization || {};
    Object.keys(utilization).forEach(function(providerKey) {
        var key = String(providerKey || "local").toLowerCase();
        if (!rowsByProvider[key]) {
            rowsByProvider[key] = {
                provider: key,
                tracks: { subscription: true },
                apiCost: 0,
                equivalentCost: 0,
                tokens: 0,
                utilization: null,
            };
        }
        rowsByProvider[key].utilization = utilization[providerKey] || null;
    });

    return Object.keys(rowsByProvider).map(function(key) {
        var row = rowsByProvider[key];
        var tracks = Object.keys(row.tracks);
        row.track = tracks.length > 1 ? "mixed" : (tracks[0] || "local");
        row.apiCost = Number(row.apiCost || 0);
        row.equivalentCost = Number(row.equivalentCost || 0);
        row.tokens = Number(row.tokens || 0);
        return row;
    }).sort(function(a, b) {
        var aWeight = a.apiCost + a.equivalentCost;
        var bWeight = b.apiCost + b.equivalentCost;
        if (bWeight !== aWeight) return bWeight - aWeight;
        return b.tokens - a.tokens;
    });
}

function renderUsageHero(payload) {
    var container = document.getElementById("usage-hero-content");
    if (!container) return;
    container.textContent = "";

    var costTrack = payload.cost_track || {};
    var subTrack = payload.subscription_track || {};
    var providerUtil = payload.provider_utilization || {};
    var providerNames = Object.keys(subTrack.tokens_by_provider || {});
    var windowRows = Object.keys(providerUtil).map(function(key) {
        return { provider: key, pct: Number((providerUtil[key] || {}).utilization_pct || 0) };
    }).filter(function(row) { return row.pct > 0; });
    windowRows.sort(function(a, b) { return b.pct - a.pct; });
    var topWindow = windowRows.length ? windowRows[0] : null;

    var heroGrid = createNode("div", "usage-hero-grid");

    var left = createNode("div", "usage-hero-pane");
    left.appendChild(createNode("div", "usage-hero-kicker", "API Spend"));
    left.appendChild(createNode("div", "usage-hero-value", formatCurrency(costTrack.total_usd || 0)));
    left.appendChild(createNode("div", "usage-hero-sub", (payload.month_label || payload.month || "This month") + " actual API spend"));
    var leftMeta = createNode("div", "usage-hero-meta", formatCurrency(costTrack.daily_pace_usd || 0) + "/day · On track for ~" + formatCurrency(costTrack.projected_month_end_usd || 0));
    left.appendChild(leftMeta);
    var leftProgress = createNode("div", "usage-progress");
    var leftFill = createNode("div", "usage-progress-fill");
    var budgetPct = Math.max(0, Math.min(100, Number(costTrack.budget_used_pct || 0)));
    leftFill.style.width = budgetPct + "%";
    if (budgetPct >= 100) leftFill.classList.add("critical");
    else if (budgetPct >= 80) leftFill.classList.add("warning");
    leftProgress.appendChild(leftFill);
    left.appendChild(leftProgress);
    left.appendChild(createNode("div", "usage-hero-meta", formatCurrency(costTrack.budget_usd || 0) + " monthly budget · " + budgetPct + "% used"));

    var right = createNode("div", "usage-hero-pane");
    right.appendChild(createNode("div", "usage-hero-kicker", "Subscription Usage"));
    right.appendChild(createNode("div", "usage-hero-value", formatNumber(subTrack.tokens_total || 0) + " tokens"));
    right.appendChild(createNode("div", "usage-hero-sub", (payload.month_label || payload.month || "This month") + " included-capacity usage"));
    var providerSummary = providerNames.length ? providerNames.map(function(key) {
        return providerDisplayName(key) + ": " + formatNumber((subTrack.tokens_by_provider || {})[key] || 0);
    }).join(" · ") : "No subscription token activity recorded";
    right.appendChild(createNode("div", "usage-hero-meta", providerSummary));
    var rightProgress = createNode("div", "usage-progress");
    var rightFill = createNode("div", "usage-progress-fill");
    var windowPct = topWindow ? Math.max(0, Math.min(100, Number(topWindow.pct || 0))) : 0;
    rightFill.style.width = windowPct + "%";
    if (windowPct >= 90) rightFill.classList.add("critical");
    else if (windowPct >= 70) rightFill.classList.add("warning");
    rightProgress.appendChild(rightFill);
    right.appendChild(rightProgress);
    right.appendChild(createNode("div", "usage-hero-meta", topWindow ? (providerDisplayName(topWindow.provider) + " current window: " + windowPct + "% used") : "Current provider window unavailable"));

    heroGrid.appendChild(left);
    heroGrid.appendChild(right);
    container.appendChild(heroGrid);

    var insightRow = createNode("div", "usage-insight-row");
    insightRow.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    var insightCopy = createNode("div");
    insightCopy.appendChild(createNode("div", "usage-insight-title", (payload.insight && payload.insight.title) || "Usage insight"));
    insightCopy.appendChild(createNode("div", "usage-insight-body", (payload.insight && payload.insight.body) || "No insight available yet."));
    insightRow.appendChild(insightCopy);
    container.appendChild(insightRow);
}

function renderUsageDailySpend(payload) {
    var container = document.getElementById("usage-daily-spend-content");
    if (!container) return;
    container.textContent = "";
    var days = Array.isArray(payload.daily_spend) ? payload.daily_spend.slice(-14) : [];
    if (!days.length) {
        container.innerHTML = '<div class="text-dim" style="padding:8px 0;">No usage rows recorded for this month yet.</div>';
        return;
    }
    var maxAmount = 0;
    days.forEach(function(day) {
        var amount = Number(day.amount || 0);
        if (amount > maxAmount) maxAmount = amount;
    });
    var sparkline = createNode("div", "usage-sparkline");
    var todayKey = new Date().toISOString().slice(0, 10);
    days.forEach(function(day) {
        var col = createNode("div", "usage-spark-col");
        var amount = Number(day.amount || 0);
        var wrap = createNode("div", "usage-spark-bar-wrap");
        var bar = createNode("div", "usage-spark-bar");
        var pct = maxAmount > 0 ? Math.max(4, Math.round((amount / maxAmount) * 100)) : 4;
        bar.style.height = pct + "%";
        if (String(day.date || "") === todayKey) bar.classList.add("today");
        wrap.appendChild(bar);
        col.appendChild(createNode("div", "usage-spark-amount", formatCurrency(amount)));
        col.appendChild(wrap);
        col.appendChild(createNode("div", "usage-spark-label", String(day.date || "").slice(5)));
        sparkline.appendChild(col);
    });
    container.appendChild(sparkline);
}

function createUsageTrackBadge(track) {
    var badge = createNode("span", "usage-track-badge " + String(track || "local").toLowerCase(), usageTrackLabel(track));
    return badge;
}

function renderUsageProviders(payload) {
    var container = document.getElementById("usage-providers-content");
    if (!container) return;
    container.textContent = "";
    var rows = buildUsageProviderRows(payload);
    if (!rows.length) {
        container.innerHTML = '<div class="text-dim" style="padding:8px 0;">No provider usage recorded yet.</div>';
        return;
    }
    var list = createNode("div", "usage-provider-list");
    rows.forEach(function(row) {
        var item = createNode("div", "usage-provider-item");
        var head = createNode("div", "usage-provider-head");
        head.appendChild(createNode("div", "usage-provider-name", providerDisplayName(row.provider)));
        var badgeWrap = createNode("div", "usage-provider-meta");
        if (row.track === "mixed") {
            badgeWrap.appendChild(createUsageTrackBadge("api"));
            badgeWrap.appendChild(createUsageTrackBadge("subscription"));
        } else {
            badgeWrap.appendChild(createUsageTrackBadge(row.track));
        }
        head.appendChild(badgeWrap);
        item.appendChild(head);

        var stats = createNode("div", "usage-provider-stats");
        var stat1 = createNode("div", "usage-provider-stat");
        stat1.appendChild(createNode("span", "label", "API spend"));
        stat1.appendChild(createNode("span", "value", formatCurrency(row.apiCost)));
        stats.appendChild(stat1);

        var stat2 = createNode("div", "usage-provider-stat");
        stat2.appendChild(createNode("span", "label", "Subscription tokens"));
        stat2.appendChild(createNode("span", "value", formatNumber(row.tokens)));
        stats.appendChild(stat2);

        var stat3 = createNode("div", "usage-provider-stat");
        stat3.appendChild(createNode("span", "label", "API-rate equivalent"));
        stat3.appendChild(createNode("span", "value", formatCurrency(row.equivalentCost)));
        stats.appendChild(stat3);

        if (row.utilization) {
            var utilPct = Math.max(0, Math.min(100, Number(row.utilization.utilization_pct || 0)));
            var stat4 = createNode("div", "usage-provider-stat");
            stat4.appendChild(createNode("span", "label", row.utilization.label || "Current window"));
            var utilText = utilPct + "% used";
            if (row.utilization.resets_in) utilText += " · resets in " + row.utilization.resets_in;
            stat4.appendChild(createNode("span", "value", utilText));
            stats.appendChild(stat4);

            var progress = createNode("div", "usage-progress");
            var fill = createNode("div", "usage-progress-fill");
            fill.style.width = utilPct + "%";
            if (utilPct >= 90) fill.classList.add("critical");
            else if (utilPct >= 70) fill.classList.add("warning");
            progress.appendChild(fill);
            item.appendChild(stats);
            item.appendChild(progress);
        } else {
            var stat4b = createNode("div", "usage-provider-stat");
            stat4b.appendChild(createNode("span", "label", "Current window"));
            stat4b.appendChild(createNode("span", "value", "No live utilization data"));
            stats.appendChild(stat4b);
            item.appendChild(stats);
        }

        list.appendChild(item);
    });
    container.appendChild(list);
}

function renderUsageBudget(config, payload) {
    var budget = config || {};
    var fallbackBudget = payload && payload.budget ? payload.budget : {};
    var budgetInput = document.getElementById("usage-budget-input");
    var alertInput = document.getElementById("usage-alert-input");
    var resetInput = document.getElementById("usage-reset-input");
    var primaryUserInput = document.getElementById("usage-primary-user-input");
    var statusEl = document.getElementById("usage-budget-status");
    if (budgetInput) budgetInput.value = budget.budget_usd != null ? budget.budget_usd : (fallbackBudget.budget_usd || 0);
    if (alertInput) alertInput.value = budget.alert_pct != null ? budget.alert_pct : (fallbackBudget.alert_pct || 80);
    if (resetInput) resetInput.value = budget.reset_day != null ? budget.reset_day : (fallbackBudget.reset_day || 1);
    if (primaryUserInput) primaryUserInput.value = budget.primary_user_label != null ? budget.primary_user_label : "Dana";
    if (statusEl) {
        var costSource = payload && payload.cost_source ? String(payload.cost_source) : "mixed";
        statusEl.textContent = "Tracks actual API spend separately from included subscription usage. Current cost basis: " + costSource + ".";
    }
}

function renderUsageEmptyTable(containerId, message) {
    var container = document.getElementById(containerId);
    if (container) container.innerHTML = '<div class="text-dim" style="padding:8px 0;">' + esc(message) + '</div>';
}

function appendUsageTable(containerId, columns, rows) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.textContent = "";
    if (!rows.length) {
        container.innerHTML = '<div class="text-dim" style="padding:8px 0;">No data yet for this month.</div>';
        return;
    }
    var wrap = createNode("div", "usage-table-wrap");
    var table = createNode("table", "usage-table");
    var thead = createNode("thead");
    var headerRow = createNode("tr");
    columns.forEach(function(col) {
        headerRow.appendChild(createNode("th", "", col));
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    var tbody = createNode("tbody");
    rows.forEach(function(row) { tbody.appendChild(row); });
    table.appendChild(tbody);
    wrap.appendChild(table);
    container.appendChild(wrap);
}

function renderUsageBreakdowns(payload) {
    var byAgent = Array.isArray(payload.by_agent) ? payload.by_agent : [];
    var agentRows = byAgent.map(function(item) {
        var tr = createNode("tr");
        var nameCell = createNode("td");
        nameCell.appendChild(createNode("div", "usage-cell-primary", item.name || "—"));
        nameCell.appendChild(createNode("div", "usage-cell-sub", formatNumber((item.tokens_in || 0) + (item.tokens_out || 0)) + " tokens"));
        tr.appendChild(nameCell);
        tr.appendChild(createNode("td", "mono", formatCurrency((item.track_mix && item.track_mix.api_cost_usd) || item.cost_usd || 0)));
        tr.appendChild(createNode("td", "mono", formatCurrency((item.track_mix && item.track_mix.subscription_equivalent_cost_usd) || 0)));
        tr.appendChild(createNode("td", "mono text-dim", (item.pct || 0) + "%"));
        return tr;
    });
    appendUsageTable("usage-by-agent-content", ["Speaker", "API Spend", "Sub Eqv.", "%"], agentRows);

    var byUser = Array.isArray(payload.by_user) ? payload.by_user : [];
    var userRows = byUser.map(function(item) {
        var tr = createNode("tr");
        var nameCell = createNode("td");
        nameCell.appendChild(createNode("div", "usage-cell-primary", item.name || "—"));
        nameCell.appendChild(createNode("div", "usage-cell-sub", formatNumber((item.tokens_in || 0) + (item.tokens_out || 0)) + " tokens"));
        tr.appendChild(nameCell);
        tr.appendChild(createNode("td", "mono", formatCurrency((item.track_mix && item.track_mix.api_cost_usd) || item.cost_usd || 0)));
        tr.appendChild(createNode("td", "mono", formatCurrency((item.track_mix && item.track_mix.subscription_equivalent_cost_usd) || 0)));
        tr.appendChild(createNode("td", "mono text-dim", (item.pct || 0) + "%"));
        return tr;
    });
    appendUsageTable("usage-by-user-content", ["User", "API Spend", "Sub Eqv.", "%"], userRows);

    var byModel = Array.isArray(payload.by_model) ? payload.by_model : [];
    var modelRows = byModel.map(function(item) {
        var tr = createNode("tr");
        var modelCell = createNode("td");
        modelCell.appendChild(createNode("div", "usage-cell-primary", item.display || item.model || "—"));
        var rateText = "In " + formatCurrency((Number(item.price_in || 0) / 1000)) + " · Out " + formatCurrency((Number(item.price_out || 0) / 1000));
        modelCell.appendChild(createNode("div", "usage-cell-sub mono", rateText));
        tr.appendChild(modelCell);
        var trackCell = createNode("td");
        trackCell.appendChild(createUsageTrackBadge(item.track));
        tr.appendChild(trackCell);
        tr.appendChild(createNode("td", "mono", formatCurrency(item.cost_usd || 0)));
        tr.appendChild(createNode("td", "mono", formatCurrency(item.equivalent_cost_usd || 0)));
        tr.appendChild(createNode("td", "mono", formatNumber((item.tokens_in || 0) + (item.tokens_out || 0))));
        return tr;
    });
    appendUsageTable("usage-by-model-content", ["Model", "Track", "Cost", "API-rate", "Tokens"], modelRows);
}

async function loadUsagePage(monthKey) {
    var targetMonth = monthKey || usageState.month || currentMonthKey();
    usageState.month = targetMonth;
    updateUsageMonthControls(targetMonth, targetMonth);

    var refreshBtn = document.getElementById("btn-usage-refresh");
    var prevBtn = document.getElementById("btn-usage-prev-month");
    var nextBtn = document.getElementById("btn-usage-next-month");
    if (refreshBtn) refreshBtn.disabled = true;
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;

    ["usage-hero-content", "usage-daily-spend-content", "usage-providers-content", "usage-by-agent-content", "usage-by-user-content", "usage-by-model-content"].forEach(function(id) {
        var el = document.getElementById(id);
        if (el && !el.textContent.trim()) {
            el.innerHTML = usageLoadingMarkup("Loading...");
        }
    });

    try {
        var results = await Promise.allSettled([
            apiFetch("/admin/usage?month=" + encodeURIComponent(targetMonth)),
            apiFetch("/admin/usage/config"),
        ]);
        var usageResult = results[0];
        var configResult = results[1];

        if (usageResult.status !== "fulfilled") {
            throw usageResult.reason || new Error("Could not load usage report");
        }

        usageState.payload = usageResult.value || {};
        usageState.month = usageState.payload.month || targetMonth;
        updateUsageMonthControls(usageState.month, usageState.payload.month_label || usageState.month);
        renderUsageHero(usageState.payload);
        renderUsageDailySpend(usageState.payload);
        renderUsageProviders(usageState.payload);
        renderUsageBreakdowns(usageState.payload);

        if (configResult.status === "fulfilled") {
            usageState.config = configResult.value || {};
            renderUsageBudget(usageState.config, usageState.payload);
        } else {
            usageState.config = null;
            renderUsageBudget(null, usageState.payload);
            showToast("Usage config unavailable: " + configResult.reason.message, "warning");
        }
    } catch (err) {
        ["usage-hero-content", "usage-daily-spend-content", "usage-providers-content", "usage-by-agent-content", "usage-by-user-content", "usage-by-model-content"].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.innerHTML = renderError("Could not load usage page: " + err.message);
        });
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
        if (prevBtn) prevBtn.disabled = false;
        updateUsageMonthControls(usageState.month, (usageState.payload && usageState.payload.month_label) || usageState.month);
    }
}
window.loadUsagePage = loadUsagePage;

async function saveUsageConfig() {
    var budgetInput = document.getElementById("usage-budget-input");
    var alertInput = document.getElementById("usage-alert-input");
    var resetInput = document.getElementById("usage-reset-input");
    var primaryUserInput = document.getElementById("usage-primary-user-input");
    var button = document.getElementById("btn-usage-save-config");
    var statusEl = document.getElementById("usage-budget-status");
    var payload = {
        budget_usd: parseInt(budgetInput && budgetInput.value, 10),
        alert_pct: parseInt(alertInput && alertInput.value, 10),
        reset_day: parseInt(resetInput && resetInput.value, 10),
        primary_user_label: String(primaryUserInput && primaryUserInput.value || "").trim(),
    };
    if (!Number.isFinite(payload.budget_usd) || payload.budget_usd < 0) {
        showToast("Budget must be 0 or higher", "warning");
        if (budgetInput) budgetInput.focus();
        return;
    }
    if (!Number.isFinite(payload.alert_pct) || payload.alert_pct < 1 || payload.alert_pct > 100) {
        showToast("Alert threshold must be between 1 and 100", "warning");
        if (alertInput) alertInput.focus();
        return;
    }
    if (!Number.isFinite(payload.reset_day) || payload.reset_day < 1 || payload.reset_day > 28) {
        showToast("Reset day must be between 1 and 28", "warning");
        if (resetInput) resetInput.focus();
        return;
    }
    if (!payload.primary_user_label) {
        showToast("Primary user label is required", "warning");
        if (primaryUserInput) primaryUserInput.focus();
        return;
    }
    if (button) button.disabled = true;
    if (statusEl) statusEl.textContent = "Saving usage settings...";
    try {
        var result = await apiFetch("/admin/usage/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        usageState.config = result.config || payload;
        renderUsageBudget(usageState.config, usageState.payload || {});
        if (statusEl) statusEl.textContent = "Usage settings saved.";
        showToast("Usage settings saved", "success");
        await loadUsagePage(usageState.month || currentMonthKey());
    } catch (err) {
        if (statusEl) statusEl.textContent = "Failed to save usage settings.";
        showToast("Usage settings failed: " + err.message, "error");
    } finally {
        if (button) button.disabled = false;
    }
}
window.saveUsageConfig = saveUsageConfig;

async function exportUsageCsv() {
    var month = usageState.month || currentMonthKey();
    window.open(API + "/admin/usage/export?month=" + encodeURIComponent(month), "_blank");
}
window.exportUsageCsv = exportUsageCsv;

/* -- Database -------------------------------------------------------- */

async function loadLegacyDbStats() {
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

function setButtonBusy(ids, busy) {
    (ids || []).forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.disabled = !!busy;
    });
}

async function refreshDatabaseViews() {
    if (currentPage === "database") {
        await loadDatabasePage();
        return;
    }
    await loadLegacyDbStats();
}

async function vacuumDb() {
    setButtonBusy(["btn-vacuum", "btn-database-vacuum"], true);
    try {
        var data = await apiFetch("/db/vacuum", { method: "POST" });
        var before = data.before_size || data.size_before;
        var after = data.after_size || data.size_after;
        if (before && after) {
            showToast("Vacuum complete: " + formatBytes(before) + " -> " + formatBytes(after), "success");
        } else {
            showToast("Vacuum complete", "success");
        }
        await refreshDatabaseViews();
    } catch (err) {
        showToast("Vacuum failed: " + err.message, "error");
    } finally {
        setButtonBusy(["btn-vacuum", "btn-database-vacuum"], false);
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
        await refreshDatabaseViews();
    } catch (err) {
        showToast("Purge failed: " + err.message, "error");
    }
}
window.purgeMessages = purgeMessages;

function buildDatabaseTableRows(tables) {
    var preferred = [
        "messages",
        "chats",
        "alerts",
        "agent_profiles",
        "channel_agent_memberships",
        "persona_memories",
        "persona_model_overrides",
        "device_tokens",
        "permission_audit_log",
        "apex_meta",
    ];
    var rows = [];
    var safeTables = tables || {};
    preferred.forEach(function(name) {
        if (Object.prototype.hasOwnProperty.call(safeTables, name)) {
            rows.push({ name: name, count: safeTables[name] });
        }
    });
    Object.keys(safeTables).sort().forEach(function(name) {
        if (preferred.indexOf(name) === -1) {
            rows.push({ name: name, count: safeTables[name] });
        }
    });
    return rows;
}

function renderDatabaseStatus(data) {
    var container = document.getElementById("database-status-content");
    if (!container) return;
    var dbSize = data.db_size_bytes || data.file_size || 0;
    var walSize = data.wal_size_bytes || data.wal_size || 0;
    var pageCount = Number(data.page_count || 0);
    var freelistCount = Number(data.freelist_count || 0);
    var fragmentationPct = pageCount > 0 ? ((freelistCount / pageCount) * 100) : 0;
    var backupSummary = "See backups below";
    if (data.last_backup_created) {
        try {
            backupSummary = new Date(data.last_backup_created).toLocaleString();
        } catch (err) {
            backupSummary = String(data.last_backup_created);
        }
    }
    var totalRows = 0;
    Object.keys(data.tables || {}).forEach(function(name) {
        var count = Number((data.tables || {})[name]);
        if (Number.isFinite(count) && count > 0) totalRows += count;
    });

    var rows = [
        { label: "Health", value: "Healthy", statusDot: true, statusInline: true },
        { label: "Database Size", value: formatBytes(dbSize) },
        { label: "Total Rows", value: formatNumber(totalRows) },
        { label: "WAL Size", value: formatBytes(walSize) },
        { label: "Fragmentation", value: fragmentationPct.toFixed(1) + "%" },
        { label: "Last Backup", value: backupSummary },
    ];

    container.textContent = "";
    rows.forEach(function(row) {
        var statRow = document.createElement("div");
        statRow.className = "stat-row";

        var label = document.createElement("span");
        label.className = "stat-label";
        label.textContent = row.label;
        statRow.appendChild(label);

        var value = document.createElement("span");
        value.className = row.statusInline ? "stat-value status-inline" : "stat-value";
        if (row.statusDot) {
            var dot = document.createElement("span");
            dot.className = "status-dot green";
            value.appendChild(dot);
        }
        var text = document.createTextNode(row.value);
        value.appendChild(text);
        statRow.appendChild(value);

        container.appendChild(statRow);
    });
}

function renderDatabaseTables(data) {
    var container = document.getElementById("database-tables-content");
    if (!container) return;
    var rows = buildDatabaseTableRows(data.tables || {});
    if (!rows.length) {
        container.innerHTML = '<div style="padding:12px 0; color:var(--text-dim);">No database tables found.</div>';
        return;
    }

    var html = '<table class="backup-list"><thead><tr><th>Table</th><th>Rows</th><th>Size</th></tr></thead><tbody>';
    rows.forEach(function(row) {
        html += '<tr>';
        html += '<td style="font-family:monospace; font-size:12px;">' + esc(row.name) + '</td>';
        html += '<td>' + (row.count >= 0 ? formatNumber(row.count) : '—') + '</td>';
        html += '<td style="color:var(--text-dim); font-size:12px;">—</td>';
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

function renderDatabaseRetention(data) {
    var container = document.getElementById("database-retention-content");
    if (!container) return;
    var rows = [
        { label: "Messages", value: "30 days", note: "Backed by /api/db/messages purge action" },
        { label: "Chats", value: "Keep all", note: "No dedicated retention endpoint yet" },
        { label: "Alerts", value: "Keep all", note: "No dedicated retention endpoint yet" },
        { label: "Persona memories", value: "Keep all", note: "No dedicated retention endpoint yet" },
    ];
    var html = '<table class="backup-list"><thead><tr><th>Data</th><th>Retention</th><th>Notes</th></tr></thead><tbody>';
    rows.forEach(function(row) {
        html += '<tr>';
        html += '<td>' + esc(row.label) + '</td>';
        html += '<td>' + esc(row.value) + '</td>';
        html += '<td style="color:var(--text-dim); font-size:12px;">' + esc(row.note) + '</td>';
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

function renderDatabaseActions() {
    var container = document.getElementById("database-actions-content");
    if (!container) return;
    container.innerHTML =
        '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px;">' +
            '<button class="btn btn-ghost" id="btn-database-vacuum" style="justify-content:flex-start; padding:14px 16px;">Optimize (VACUUM)</button>' +
            '<button class="btn btn-ghost" id="btn-database-export" style="justify-content:flex-start; padding:14px 16px;">Export Database</button>' +
            '<button class="btn btn-ghost" id="btn-database-backup" style="justify-content:flex-start; padding:14px 16px;">Backup Now</button>' +
            '<button class="btn btn-ghost" id="btn-database-restore" style="justify-content:flex-start; padding:14px 16px; color:var(--yellow);">Open Restore Controls</button>' +
        '</div>' +
        '<div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:14px;">' +
            '<span style="color:var(--text-dim); font-size:12px;">Purge messages older than</span>' +
            '<input type="number" id="database-purge-days-input" value="30" min="1" max="365" style="width:88px;">' +
            '<span style="color:var(--text-dim); font-size:12px;">days</span>' +
            '<button class="btn btn-ghost" id="btn-database-purge" style="color:var(--red);">Purge</button>' +
        '</div>' +
        '<div style="margin-top:16px;" id="database-backups-content"><div class="loading-overlay"><div class="spinner"></div> Loading backups...</div></div>';
}

async function loadDatabasePage() {
    var refreshBtn = document.getElementById("btn-database-refresh");
    if (refreshBtn) refreshBtn.disabled = true;
    renderDatabaseActions();
    try {
        var results = await Promise.allSettled([
            apiFetch("/db/stats"),
            apiFetch("/backups"),
        ]);
        var statsResult = results[0];
        var backupsResult = results[1];
        if (statsResult.status !== "fulfilled") {
            throw statsResult.reason || new Error("Could not load database stats");
        }
        var stats = statsResult.value || {};
        if (backupsResult.status === "fulfilled") {
            var backups = backupsResult.value || {};
            if (backups && backups.backups && backups.backups.length > 0) {
                stats.last_backup_created = backups.backups[0].created || backups.backups[0].date || "";
            }
            renderBackupsTable(backups, "database-backups-content");
        } else {
            var backupsEl = document.getElementById("database-backups-content");
            if (backupsEl) backupsEl.innerHTML = renderError("Could not load backups: " + backupsResult.reason.message);
        }
        renderDatabaseStatus(stats);
        renderDatabaseTables(stats);
        renderDatabaseRetention(stats);
    } catch (err) {
        var sections = ["database-status-content", "database-tables-content", "database-retention-content", "database-actions-content"];
        sections.forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.innerHTML = renderError("Could not load database page: " + err.message);
        });
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
    }
}
window.loadDatabasePage = loadDatabasePage;

async function purgeDatabaseMessages() {
    var input = document.getElementById("database-purge-days-input");
    var days = input ? parseInt(input.value, 10) : NaN;
    if (!Number.isFinite(days) || days < 1) {
        showToast("Purge days must be at least 1", "warning");
        return;
    }
    if (!confirm("Purge messages older than " + days + " days? This cannot be undone.")) return;
    setButtonBusy(["btn-database-purge", "btn-purge-messages"], true);
    try {
        var data = await apiFetch("/db/messages?days=" + days, { method: "DELETE" });
        showToast("Purged " + formatNumber(data.deleted || 0) + " messages", "success");
        await refreshDatabaseViews();
    } catch (err) {
        showToast("Purge failed: " + err.message, "error");
    } finally {
        setButtonBusy(["btn-database-purge", "btn-purge-messages"], false);
    }
}
window.purgeDatabaseMessages = purgeDatabaseMessages;

function renderBackupsTable(data, containerId) {
    var container = document.getElementById(containerId || "backups-content");
    if (!container) return;
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
}

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
        renderBackupsTable(data, "backups-content");
    } catch (err) {
        container.innerHTML = renderError("Could not load backups: " + err.message);
    }
}

async function createBackup() {
    setButtonBusy(["btn-create-backup", "btn-database-backup"], true);
    try {
        var data = await apiFetch("/backup", { method: "POST" });
        var name = data.filename || data.name || "backup";
        showToast("Backup created: " + name, "success");
        if (currentPage === "database") {
            await loadDatabasePage();
        } else {
            await loadBackups();
        }
    } catch (err) {
        showToast("Backup failed: " + err.message, "error");
    } finally {
        setButtonBusy(["btn-create-backup", "btn-database-backup"], false);
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
    setButtonBusy(["btn-database-restore"], true);
    try {
        await apiFetch("/backup/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: filename }) });
        showToast("Restore complete. Server may restart.", "success");
        if (currentPage === "database") {
            await loadDatabasePage();
        }
    } catch (err) {
        showToast("Restore failed: " + err.message, "error");
    } finally {
        setButtonBusy(["btn-database-restore"], false);
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
    } else if ((btn = e.target.closest("#btn-database-vacuum"))) {
        vacuumDb();
    } else if ((btn = e.target.closest("#btn-database-export"))) {
        exportDb();
    } else if ((btn = e.target.closest("#btn-database-backup"))) {
        createBackup();
    } else if ((btn = e.target.closest("#btn-database-restore"))) {
        var backupsBlock = document.getElementById("database-backups-content");
        if (backupsBlock) backupsBlock.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if ((btn = e.target.closest("#btn-database-purge"))) {
        purgeDatabaseMessages();
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

"""

_JS_INIT = r"""/* =====================================================================
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
    bindClick("btn-database-refresh", loadDatabasePage);
    bindClick("btn-usage-refresh", function() { loadUsagePage(usageState.month || currentMonthKey()); });
    bindClick("btn-usage-prev-month", function() { loadUsagePage(shiftMonthKey(usageState.month || currentMonthKey(), -1)); });
    bindClick("btn-usage-next-month", function() {
        var nextMonth = shiftMonthKey(usageState.month || currentMonthKey(), 1);
        if (!isFutureMonthKey(nextMonth)) loadUsagePage(nextMonth);
    });
    bindClick("btn-usage-save-config", saveUsageConfig);
    bindClick("btn-usage-export", exportUsageCsv);
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

"""

DASHBOARD_JS = (
    _JS_PREAMBLE
    + _JS_GLOBALS
    + _JS_NAVIGATION
    + _JS_API_HELPERS
    + _JS_TOAST
    + _JS_HEALTH
    + _JS_CONFIG
    + _JS_TLS
    + _JS_MODELS
    + _JS_PERSONAS
    + _JS_POLICY
    + _JS_WORKSPACE
    + _JS_REFRESH_TIMER
    + _JS_FORMATTERS
    + _JS_LOGS
    + _JS_INIT
    + "})();\n"
)
