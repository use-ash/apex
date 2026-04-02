# Browser-based setup wizard for Apex.
# HTML/CSS from designer mockup (mockups/setup-wizard.html).
# Wired to: /api/setup/status, /api/setup/models, /api/setup/workspace,
#           /api/setup/knowledge (SSE), /api/setup/complete

SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Apex Setup</title>
<style>
  :root {
    --bg: #080e1a;
    --surface: #0f1829;
    --card: #131e30;
    --border: #1e2d45;
    --text: #e2e8f0;
    --dim: #64748b;
    --accent: #38bdf8;
    --accent-glow: rgba(56, 189, 248, 0.15);
    --accent-dim: rgba(56, 189, 248, 0.08);
    --green: #22c55e;
    --green-glow: rgba(34, 197, 94, 0.12);
    --yellow: #f59e0b;
    --yellow-glow: rgba(245, 158, 11, 0.12);
    --red: #ef4444;
    --red-glow: rgba(239, 68, 68, 0.12);
    --radius: 12px;
    --radius-sm: 8px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Card container ── */
  .wizard-card {
    width: 100%;
    max-width: 580px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 40px;
    position: relative;
  }

  /* ── Logo ── */
  .logo {
    text-align: center;
    margin-bottom: 28px;
  }

  /* ── Progress dots ── */
  .progress {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: var(--border);
    transition: all 0.3s ease;
  }
  .dot.done { background: var(--green); width: 8px; }
  .dot.active { background: var(--accent); width: 24px; }
  .progress-label {
    text-align: center;
    font-size: 12px;
    color: var(--dim);
    margin-bottom: 28px;
    letter-spacing: 0.02em;
  }

  /* ── Step content ── */
  .step { display: none; }
  .step.visible { display: block; }

  .step-title {
    font-size: 24px;
    font-weight: 700;
    text-align: center;
    margin-bottom: 8px;
    letter-spacing: -0.01em;
  }
  .step-subtitle {
    font-size: 14px;
    color: var(--dim);
    text-align: center;
    margin-bottom: 28px;
    line-height: 1.5;
  }

  /* ── Info box ── */
  .info-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 14px 16px;
    margin-bottom: 24px;
  }
  .info-box-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 6px;
  }
  .info-box p { font-size: 13px; color: var(--dim); line-height: 1.5; }

  /* ── Checklist (welcome) ── */
  .checklist { margin: 24px 0 0; }
  .checklist-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    font-size: 14px;
    color: var(--dim);
  }
  .checklist-item .arrow { color: var(--accent); font-size: 12px; flex-shrink: 0; }
  .checklist-item strong { color: var(--text); font-weight: 500; }

  /* ── Status indicator ── */
  .status {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-bottom: 20px;
  }
  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .status-dot.green { background: var(--green); box-shadow: 0 0 8px var(--green-glow); }
  .status-dot.yellow { background: var(--yellow); box-shadow: 0 0 8px var(--yellow-glow); }
  .status-dot.red { background: #ef4444; box-shadow: 0 0 8px rgba(239,68,68,0.4); }
  .status-text { font-size: 13px; color: var(--text); }
  .status-text .dim { color: var(--dim); }

  /* ── Input fields ── */
  .field { margin-bottom: 20px; }
  .field-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--dim);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .field-label .optional { font-size: 11px; font-weight: 400; color: var(--dim); opacity: 0.6; }
  .field input {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 14px;
    font-size: 14px;
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    outline: none;
    transition: border-color 0.2s;
  }
  .field input::placeholder { color: var(--dim); opacity: 0.5; }
  .field input:focus { border-color: var(--accent); }
  .field-hint { font-size: 12px; color: var(--dim); margin-top: 6px; line-height: 1.4; }
  .field-hint a { color: var(--accent); text-decoration: none; }
  .field-hint a:hover { text-decoration: underline; }
  .field-err { font-size: 12px; color: #ef4444; margin-top: 6px; line-height: 1.4; }

  /* ── Model sections (Step 3) ── */
  .model-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 16px;
    margin-bottom: 12px;
  }
  .model-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }
  .model-name {
    font-size: 14px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .model-badge {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
  }
  .model-badge.optional { background: var(--border); color: var(--dim); }
  .model-section .field { margin-bottom: 0; }
  .model-section .field input { font-size: 13px; }
  .model-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--dim);
    margin-top: 8px;
  }
  .dot-sm { width: 6px; height: 6px; border-radius: 50%; }
  .dot-sm.green { background: var(--green); }
  .dot-sm.yellow { background: var(--yellow); }

  /* ── Permission cards (Step 4) ── */
  .perm-cards { margin: 0 0 4px; }
  .perm-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 16px 18px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    position: relative;
  }
  .perm-card:hover { border-color: var(--dim); }
  .perm-card.selected { border-color: var(--accent); background: var(--accent-dim); }
  .perm-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s;
  }
  .perm-card.selected .perm-icon { background: var(--accent-glow); }
  .perm-content { flex: 1; }
  .perm-title {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .perm-desc { font-size: 13px; color: var(--dim); line-height: 1.4; }
  .perm-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    background: var(--accent-glow);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 4px;
  }
  .perm-check {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 2px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }
  .perm-card.selected .perm-check { background: var(--accent); border-color: var(--accent); }

  /* ── AI History (Step 5) ── */
  .history-source {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    margin-bottom: 10px;
    transition: all 0.2s;
  }
  .history-source.found { border-color: rgba(34, 197, 94, 0.3); }
  .history-source .src-icon {
    width: 20px;
    flex-shrink: 0;
    font-size: 16px;
    line-height: 1.2;
    text-align: center;
  }
  .history-source .src-body { flex: 1; min-width: 0; }
  .history-source .src-name { font-weight: 600; font-size: 14px; }
  .history-source .src-detail { font-size: 12px; color: var(--dim); margin-top: 2px; word-break: break-all; }
  .history-source .src-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
  }
  .history-source .src-toggle label { font-size: 12px; color: var(--dim); cursor: pointer; }
  .embed-box {
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 16px;
    margin-top: 16px;
    margin-bottom: 16px;
  }
  .embed-box .embed-title { font-size: 13px; font-weight: 600; margin-bottom: 10px; }
  .embed-option {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    cursor: pointer;
  }
  .embed-option .embed-label { font-size: 13px; }
  .embed-option .embed-hint { font-size: 11px; color: var(--dim); }
  .embed-disabled { opacity: 0.5; }
  .embed-disabled .embed-hint { color: var(--yellow); }

  /* ── Knowledge scan (Step 6) ── */
  .scan-area { text-align: center; }
  .scan-desc { font-size: 14px; color: var(--dim); line-height: 1.5; margin-bottom: 24px; }
  .scan-buttons { display: flex; gap: 12px; justify-content: center; }
  .progress-bar-track {
    width: 100%;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    margin: 16px 0 12px;
  }
  .progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), #7dd3fc);
    border-radius: 3px;
    width: 0%;
    transition: width 0.5s ease;
  }
  .scan-status-text { font-size: 13px; color: var(--dim); }
  .scan-found { font-size: 12px; color: var(--accent); margin-top: 6px; min-height: 18px; }
  .scan-error {
    background: var(--red-glow);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: var(--radius-sm);
    padding: 16px;
    text-align: center;
    margin-bottom: 16px;
  }
  .scan-error-msg { font-size: 13px; color: var(--red); margin-bottom: 4px; }
  .scan-error-hint { font-size: 12px; color: var(--dim); }
  .inline-code {
    background: var(--border);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: var(--accent);
  }

  /* ── Done checklist (Step 7) ── */
  .done-list { margin: 24px 0; }
  .done-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  .done-item:last-child { border-bottom: none; }
  .done-icon {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-size: 12px;
  }
  .done-icon.ok { background: var(--green-glow); color: var(--green); }
  .done-icon.skip { background: var(--border); color: var(--dim); }
  .done-text { flex: 1; }
  .done-text.skipped { color: var(--dim); }
  .done-label { font-size: 11px; color: var(--dim); opacity: 0.7; }

  /* Cert note (collapsible) */
  .cert-note {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    margin-bottom: 24px;
  }
  .cert-note summary {
    padding: 12px 16px;
    font-size: 13px;
    color: var(--dim);
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .cert-note summary::before { content: '▸'; font-size: 10px; transition: transform 0.2s; }
  .cert-note[open] summary::before { transform: rotate(90deg); }
  .cert-note .cert-note-body {
    padding: 0 16px 14px;
    font-size: 13px;
    color: var(--dim);
    line-height: 1.5;
  }
  .cert-note code {
    background: var(--bg);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: var(--accent);
  }

  /* ── Buttons ── */
  .btn-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 28px;
  }
  .btn {
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 24px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: all 0.2s;
    border: none;
    outline: none;
  }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-primary { background: var(--accent); color: #080e1a; }
  .btn-primary:hover:not(:disabled) { background: #7dd3fc; }
  .btn-secondary { background: none; color: var(--dim); border: 1px solid var(--border); }
  .btn-secondary:hover { color: var(--text); border-color: var(--dim); }
  .btn-ghost { background: none; color: var(--dim); border: none; padding: 10px 16px; }
  .btn-ghost:hover { color: var(--text); }
  .btn-cta {
    width: 100%;
    background: var(--accent);
    color: #080e1a;
    font-size: 16px;
    font-weight: 700;
    padding: 14px;
    border-radius: var(--radius-sm);
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
    letter-spacing: 0.01em;
  }
  .btn-cta:hover { background: #7dd3fc; transform: translateY(-1px); box-shadow: 0 4px 20px var(--accent-glow); }
  .btn-cta:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
  .btn-spacer { visibility: hidden; width: 1px; }

  /* ── Error message ── */
  .err-msg { font-size: 13px; color: var(--red); margin-top: 10px; display: none; }
  .err-msg.show { display: block; }
</style>
</head>
<body>

<div class="wizard-card">

  <!-- Logo -->
  <div class="logo">
    <svg width="40" height="40" viewBox="0 0 120 120" fill="none">
      <path d="M60 10 L110 38 L110 82 L60 110 L10 82 L10 38 Z" stroke="#38bdf8" stroke-width="3" fill="none" opacity="0.3"/>
      <path d="M60 25 L98 46 L98 74 L60 95 L22 74 L22 46 Z" stroke="#38bdf8" stroke-width="2" fill="none" opacity="0.15"/>
      <circle cx="40" cy="80" r="4" fill="#38bdf8" opacity="0.8"/>
      <circle cx="80" cy="80" r="4" fill="#38bdf8" opacity="0.8"/>
      <circle cx="60" cy="35" r="4" fill="#38bdf8" opacity="0.8"/>
      <circle cx="60" cy="58" r="5" fill="#38bdf8"/>
      <line x1="40" y1="80" x2="60" y2="58" stroke="#38bdf8" stroke-width="1.5" opacity="0.5"/>
      <line x1="80" y1="80" x2="60" y2="58" stroke="#38bdf8" stroke-width="1.5" opacity="0.5"/>
      <line x1="60" y1="35" x2="60" y2="58" stroke="#38bdf8" stroke-width="1.5" opacity="0.5"/>
    </svg>
  </div>

  <!-- Progress -->
  <div class="progress" id="progress-dots"></div>
  <div class="progress-label" id="progress-label"></div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 1: WELCOME -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-1">
    <h2 class="step-title">Welcome to Apex</h2>
    <p class="step-subtitle">Self-hosted AI agent platform. Setup takes about 2 minutes.</p>

    <div class="checklist">
      <div style="font-size: 12px; font-weight: 600; color: var(--dim); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 12px;">What we'll set up</div>
      <div class="checklist-item"><span class="arrow">→</span> <strong>Claude Code</strong>&nbsp; your main AI agent</div>
      <div class="checklist-item"><span class="arrow">→</span> <strong>Optional models</strong>&nbsp; Grok, Google, Ollama</div>
      <div class="checklist-item"><span class="arrow">→</span> <strong>Workspace</strong>&nbsp; folder + permission level</div>
      <div class="checklist-item"><span class="arrow">→</span> <strong>AI history</strong>&nbsp; index your Claude/Codex conversations</div>
      <div class="checklist-item"><span class="arrow">→</span> <strong>Knowledge scan</strong>&nbsp; teach the AI about your projects</div>
    </div>

    <div class="btn-row">
      <div class="btn-spacer"></div>
      <button class="btn btn-primary" onclick="showStep(2)">Get started →</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 2: CLAUDE -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-2">
    <h2 class="step-title">Connect Claude</h2>
    <p class="step-subtitle">Choose how Apex authenticates with Anthropic.</p>

    <div class="status" id="claude-status-row">
      <div class="status-dot yellow" id="claude-dot"></div>
      <div class="status-text" id="claude-status-text">Checking…</div>
    </div>

    <div class="auth-method-cards" style="display:flex;gap:12px;margin:16px 0;">
      <div class="auth-card" id="auth-oauth" onclick="selectAuth('oauth')" style="flex:1;padding:16px;border:2px solid var(--border);border-radius:12px;cursor:pointer;transition:all 0.2s;">
        <div style="font-weight:600;margin-bottom:4px;">🔑 Claude Subscription</div>
        <div style="font-size:13px;color:var(--text-dim);">Use your Max/Pro subscription — no per-token costs. Requires Claude Code CLI.</div>
      </div>
      <div class="auth-card" id="auth-apikey" onclick="selectAuth('apikey')" style="flex:1;padding:16px;border:2px solid var(--border);border-radius:12px;cursor:pointer;transition:all 0.2s;">
        <div style="font-weight:600;margin-bottom:4px;">🔐 API Key</div>
        <div style="font-size:13px;color:var(--text-dim);">Pay-per-token from console.anthropic.com. Works on all platforms.</div>
      </div>
    </div>

    <!-- OAuth panel -->
    <div id="auth-oauth-panel" style="display:none;">
      <div class="field-hint" style="margin:8px 0 12px;">
        Apex reads your Claude Code session token automatically.<br>
        If Claude Code is installed and you're logged in, you're already set.
      </div>
      <div id="oauth-status" style="padding:12px;border-radius:8px;background:var(--bg-card);font-size:13px;">
        Checking Claude Code session…
      </div>
      <div class="field" style="margin-top:12px;">
        <div class="field-hint">
          <strong>Not working?</strong> Run in your terminal:<br>
          <code style="background:var(--bg-card);padding:2px 6px;border-radius:4px;">claude auth login</code>
          then come back and click Continue.
        </div>
      </div>
    </div>

    <!-- API Key panel -->
    <div id="auth-apikey-panel" style="display:none;">
      <div class="field">
        <label class="field-label">Anthropic API Key</label>
        <input type="password" id="anthropic-key" placeholder="sk-ant-…" autocomplete="off" />
        <div class="field-hint">Get your key from <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:var(--accent);">console.anthropic.com</a>. Saved to ~/.apex/.env.</div>
      </div>
    </div>

    <div class="err-msg" id="err-2"></div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(1)">← Back</button>
      <button class="btn btn-primary" id="btn-2" onclick="saveModels()">Continue →</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 3: OTHER MODELS -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-3">
    <h2 class="step-title">Other Models</h2>
    <p class="step-subtitle">All optional. Skip any you don't need.</p>

    <div class="model-section">
      <div class="model-header">
        <div class="model-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v6m-7-3.5 5.2-3m1.6-1 5.2-3M5 6.5l5.2 3m1.6 1 5.2 3"/></svg>
          Grok
          <span class="model-badge optional">optional</span>
        </div>
      </div>
      <div class="field" style="margin-bottom: 0;">
        <input type="password" id="xai-key" placeholder="xai-…" autocomplete="off" style="font-size: 13px;" />
        <div class="field-hint">Enables live web search + X search. <a href="https://x.ai" target="_blank">x.ai</a></div>
      </div>
    </div>

    <div class="model-section">
      <div class="model-header">
        <div class="model-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>
          Google API
          <span class="model-badge optional">optional</span>
        </div>
      </div>
      <div class="field" style="margin-bottom: 0;">
        <input type="password" id="google-key" placeholder="AIza…" autocomplete="off" style="font-size: 13px;" />
        <div class="field-hint">Required for semantic memory search. <a href="https://aistudio.google.com" target="_blank">aistudio.google.com</a></div>
      </div>
    </div>

    <div class="model-section">
      <div class="model-header">
        <div class="model-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          Codex / OpenAI
          <span class="model-badge optional">optional</span>
        </div>
      </div>
      <div class="model-status" id="codex-status" style="display:none;">
        <div class="dot-sm" id="codex-dot"></div>
        <span id="codex-text"></span>
      </div>
      <div class="field" style="margin-bottom: 0;">
        <input type="password" id="openai-key" placeholder="sk-…" autocomplete="off" style="font-size: 13px;" />
        <div class="field-hint">Powers the /codex skill (gpt-5.4). Or use Codex CLI subscription — <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a></div>
      </div>
    </div>

    <div class="model-section">
      <div class="model-header">
        <div class="model-name">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          Ollama
          <span class="model-badge optional">optional</span>
        </div>
      </div>
      <div class="model-status" id="ollama-status">
        <div class="dot-sm yellow" id="ollama-dot"></div>
        <span id="ollama-text">Checking…</span>
      </div>
    </div>

    <div class="err-msg" id="err-3"></div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(2)">← Back</button>
      <button class="btn btn-primary" id="btn-3" onclick="saveModels()">Continue →</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 4: WORKSPACE -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-4">
    <h2 class="step-title">Workspace</h2>
    <p class="step-subtitle">Where should Apex work? Apex agents can read and write files here.</p>

    <div class="field">
      <label class="field-label">Workspace folder</label>
      <input type="text" id="workspace-path" placeholder="/Users/you/projects" autocomplete="off" />
      <div class="field-hint">Absolute path. Apex agents work only within this folder.</div>
    </div>

    <div style="font-size: 13px; font-weight: 600; color: var(--dim); margin-bottom: 12px;">Permission mode</div>

    <div class="perm-cards">
      <div class="perm-card selected" data-mode="acceptEdits" onclick="selectPerm(this)">
        <div class="perm-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </div>
        <div class="perm-content">
          <div class="perm-title">Edit mode <span class="perm-badge">Recommended</span></div>
          <div class="perm-desc">Apex agents read and edit files. Asks before running commands.</div>
        </div>
        <div class="perm-check">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#080e1a" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
      </div>

      <div class="perm-card" data-mode="plan" onclick="selectPerm(this)">
        <div class="perm-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--dim)" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="perm-content">
          <div class="perm-title">Supervised</div>
          <div class="perm-desc">Asks approval before any file change or command.</div>
        </div>
        <div class="perm-check"></div>
      </div>

      <div class="perm-card" data-mode="bypassPermissions" onclick="selectPerm(this)">
        <div class="perm-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--dim)" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
        </div>
        <div class="perm-content">
          <div class="perm-title">Autonomous</div>
          <div class="perm-desc">Acts without asking. Fastest, use in trusted environments.</div>
        </div>
        <div class="perm-check"></div>
      </div>
    </div>

    <div class="err-msg" id="err-4"></div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(3)">← Back</button>
      <button class="btn btn-primary" id="btn-4" onclick="saveWorkspace()">Continue →</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 5: AI HISTORY -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-5">
    <h2 class="step-title">Your AI History</h2>
    <p class="step-subtitle">Apex can index your existing AI conversations for semantic search.</p>

    <div id="history-scanning" style="text-align:center;padding:20px 0;">
      <div style="color:var(--dim);font-size:13px;">Scanning for conversation history…</div>
    </div>

    <div id="history-sources" style="display:none;"></div>

    <div id="history-embed-box" class="embed-box" style="display:none;">
      <div class="embed-title">Semantic Search</div>
      <div id="embed-options"></div>
    </div>

    <div id="history-none" style="display:none;text-align:center;padding:16px 0;color:var(--dim);font-size:14px;">
      No AI conversation history found.<br>
      <span style="font-size:12px;">You can import history later from the dashboard.</span>
    </div>

    <div id="history-indexing" style="display:none;">
      <div class="progress-bar-track">
        <div class="progress-bar-fill" id="history-bar"></div>
      </div>
      <div class="scan-status-text" id="history-status">Indexing…</div>
    </div>

    <div class="err-msg" id="err-5"></div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(4)">← Back</button>
      <button class="btn btn-primary" id="btn-5" onclick="saveHistory()">Continue →</button>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 6: KNOWLEDGE — Pre-scan -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-6">
    <h2 class="step-title">Workspace Knowledge</h2>
    <p class="step-subtitle">Apex can scan your workspace to build an AI knowledge base — projects, conventions, docs.</p>

    <div class="scan-area">
      <p class="scan-desc">This is optional. The scan is read-only and takes 30–60 seconds.<br>You can run it later with <span class="inline-code">/add-knowledge</span></p>
      <div class="scan-buttons">
        <button class="btn btn-ghost" onclick="skipKnowledge()">Skip for now</button>
        <button class="btn btn-primary" onclick="startScan()">Scan workspace →</button>
      </div>
    </div>

    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(5)">← Back</button>
      <div class="btn-spacer"></div>
    </div>
  </div>

  <!-- STEP 6-1: Scanning in progress -->
  <div class="step" id="step-6-1">
    <h2 class="step-title">Workspace Knowledge</h2>
    <p class="step-subtitle" id="scan-subtitle">Scanning your workspace…</p>

    <div class="scan-area">
      <div class="progress-bar-track">
        <div class="progress-bar-fill" id="scan-bar"></div>
      </div>
      <div class="scan-status-text" id="scan-status">Scanning…</div>
      <div class="scan-found" id="scan-found"></div>
      <div style="margin-top: 20px;">
        <button class="btn btn-ghost" onclick="cancelScan()">Cancel</button>
      </div>
    </div>
  </div>

  <!-- STEP 6-2: Scan error -->
  <div class="step" id="step-6-2">
    <h2 class="step-title">Workspace Knowledge</h2>
    <p class="step-subtitle">Something went wrong during the scan.</p>

    <div class="scan-error">
      <div class="scan-error-msg" id="scan-error-msg">Scan failed</div>
      <div class="scan-error-hint">You can skip and run <span class="inline-code">/add-knowledge</span> later.</div>
    </div>

    <div class="scan-buttons">
      <button class="btn btn-ghost" onclick="skipKnowledge()">Skip for now</button>
      <button class="btn btn-secondary" onclick="retryOrScan()">Retry</button>
    </div>

    <div class="btn-row">
      <button class="btn btn-ghost" onclick="showStep(5)">← Back</button>
      <div class="btn-spacer"></div>
    </div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <!-- STEP 7: DONE -->
  <!-- ══════════════════════════════════════════ -->
  <div class="step" id="step-7">
    <h2 class="step-title">You're all set!</h2>
    <p class="step-subtitle">Apex is configured and ready to use.</p>

    <div class="done-list" id="done-list"></div>

    <details class="cert-note">
      <summary>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--dim)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
        Linux users: manual certificate install required
      </summary>
      <div class="cert-note-body">
        On macOS, the certificate was auto-installed. On Linux, import <code>state/ssl/client.p12</code> into your browser's certificate manager (Settings → Privacy &amp; Security → Certificates).
      </div>
    </details>

    <button class="btn-cta" id="open-btn" onclick="finishSetup()">Open Apex →</button>
  </div>

</div><!-- .wizard-card -->

<script>
// ── Step config (dots + label) ────────────────────────────────────────────────
const STEP_CFG = {
  1:   { dots: [0,0,0,0,0,0,0], active: 0, label: 'Step 1 of 7 · Welcome' },
  2:   { dots: [1,0,0,0,0,0,0], active: 1, label: 'Step 2 of 7 · Claude' },
  3:   { dots: [1,1,0,0,0,0,0], active: 2, label: 'Step 3 of 7 · Other Models' },
  4:   { dots: [1,1,1,0,0,0,0], active: 3, label: 'Step 4 of 7 · Workspace' },
  5:   { dots: [1,1,1,1,0,0,0], active: 4, label: 'Step 5 of 7 · AI History' },
  6:   { dots: [1,1,1,1,1,0,0], active: 5, label: 'Step 6 of 7 · Knowledge Scan' },
  6.1: { dots: [1,1,1,1,1,0,0], active: 5, label: 'Step 6 of 7 · Scanning…' },
  6.2: { dots: [1,1,1,1,1,0,0], active: 5, label: 'Step 6 of 7 · Scan Failed' },
  7:   { dots: [1,1,1,1,1,1,1], active: -1, label: 'Complete' },
};

// ── State ─────────────────────────────────────────────────────────────────────
let _scanResult = { skipped: true, files_written: 0 };
let _scanAbort = null;

// ── Navigation ────────────────────────────────────────────────────────────────
function showStep(n) {
  document.querySelectorAll('.step').forEach(el => el.classList.remove('visible'));
  const id = 'step-' + String(n).replace('.', '-');
  const el = document.getElementById(id);
  if (el) el.classList.add('visible');

  const cfg = STEP_CFG[n];
  if (!cfg) return;

  const dotsEl = document.getElementById('progress-dots');
  dotsEl.innerHTML = cfg.dots.map((d, i) => {
    if (i === cfg.active) return '<div class="dot active"></div>';
    if (d === 1) return '<div class="dot done"></div>';
    return '<div class="dot"></div>';
  }).join('');
  document.getElementById('progress-label').textContent = cfg.label;
}

// ── Permission cards ──────────────────────────────────────────────────────────
function selectPerm(card) {
  const CHECK_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#080e1a" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>';
  document.querySelectorAll('.perm-card').forEach(c => {
    c.classList.remove('selected');
    c.querySelector('.perm-check').innerHTML = '';
    c.querySelector('.perm-icon svg').setAttribute('stroke', 'var(--dim)');
  });
  card.classList.add('selected');
  card.querySelector('.perm-check').innerHTML = CHECK_SVG;
  card.querySelector('.perm-icon svg').setAttribute('stroke', 'var(--accent)');
}

function _selectedMode() {
  const sel = document.querySelector('.perm-card.selected');
  return sel ? sel.dataset.mode : 'acceptEdits';
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || 'HTTP ' + res.status);
  }
  return res.json();
}

function showErr(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('show', !!msg);
}

function setBtn(id, text, disabled) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.disabled = !!disabled;
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async function init() {
  showStep(1);
  try {
    const r = await apiFetch('/api/setup/status');

    // Claude status — detect auth method
    const dot = document.getElementById('claude-dot');
    const txt = document.getElementById('claude-status-text');
    if (r.models && r.models.anthropic) {
      _hasApiKey = true;
      dot.className = 'status-dot green';
      txt.textContent = 'API key configured';
      selectAuth('apikey');
    } else if (r.models && r.models.claude_oauth) {
      dot.className = 'status-dot green';
      txt.textContent = 'Claude subscription connected';
      selectAuth('oauth');
    } else {
      dot.className = 'status-dot yellow';
      txt.textContent = 'Not configured — choose a method below';
      selectAuth('oauth');  // default to subscription
    }

    // Ollama status
    const od = document.getElementById('ollama-dot');
    const ot = document.getElementById('ollama-text');
    if (r.models && r.models.ollama) {
      od.className = 'dot-sm green';
      ot.innerHTML = 'Running — local models available';
    } else {
      od.className = 'dot-sm yellow';
      ot.innerHTML = 'Not detected — <a href="https://ollama.com" target="_blank" style="color:var(--accent);text-decoration:none;">install from ollama.com</a>';
    }

    // Pre-fill workspace
    if (r.workspace && r.workspace.path) {
      document.getElementById('workspace-path').value = r.workspace.path;
    }
    if (r.workspace && r.workspace.permission_mode) {
      const card = document.querySelector('.perm-card[data-mode="' + r.workspace.permission_mode + '"]');
      if (card) selectPerm(card);
    }

    // Resume at first incomplete step
    const step = (r.current_step || 0) + 1;
    if (step > 1 && step <= 7) showStep(step);
  } catch(e) {
    // non-fatal — start at step 1
  }
})();

// ── Auth method selector ──────────────────────────────────────────────────────
let _authMethod = 'oauth';
let _hasApiKey = false;   // set by init if .env has ANTHROPIC_API_KEY

function selectAuth(method) {
  _authMethod = method;
  const oauthCard = document.getElementById('auth-oauth');
  const apikeyCard = document.getElementById('auth-apikey');
  const oauthPanel = document.getElementById('auth-oauth-panel');
  const apikeyPanel = document.getElementById('auth-apikey-panel');
  const dot = document.getElementById('claude-dot');
  const txt = document.getElementById('claude-status-text');

  if (method === 'oauth') {
    oauthCard.style.borderColor = 'var(--accent)';
    oauthCard.style.background = 'rgba(99,102,241,0.08)';
    apikeyCard.style.borderColor = 'var(--border)';
    apikeyCard.style.background = 'transparent';
    oauthPanel.style.display = 'block';
    apikeyPanel.style.display = 'none';
    // Reset status while checking
    dot.className = 'status-dot yellow';
    txt.textContent = 'Checking subscription…';
    checkOAuthStatus();
  } else {
    apikeyCard.style.borderColor = 'var(--accent)';
    apikeyCard.style.background = 'rgba(99,102,241,0.08)';
    oauthCard.style.borderColor = 'var(--border)';
    oauthCard.style.background = 'transparent';
    apikeyPanel.style.display = 'block';
    oauthPanel.style.display = 'none';
    // Restore API key status
    if (_hasApiKey) {
      dot.className = 'status-dot green';
      txt.textContent = 'API key configured';
    } else {
      dot.className = 'status-dot yellow';
      txt.textContent = 'Enter your API key below';
    }
  }
}

async function checkOAuthStatus() {
  const el = document.getElementById('oauth-status');
  const dot = document.getElementById('claude-dot');
  const txt = document.getElementById('claude-status-text');
  try {
    const r = await apiFetch('/api/setup/oauth-status');
    if (r.valid) {
      const detail = r.email ? ' (' + r.email + ')' : '';
      const sub = r.subscription ? ' · ' + r.subscription : '';
      el.innerHTML = '<span style="color:var(--green);">✓</span> Logged in' + detail + sub;
      dot.className = 'status-dot green';
      txt.textContent = 'Claude subscription connected';
    } else {
      const hint = r.error || 'Not logged in';
      el.innerHTML = '<span style="color:var(--text-dim);">—</span> ' + hint + '. Run <code>claude auth login</code> first.';
      dot.className = 'status-dot red';
      txt.textContent = 'Not logged in';
    }
  } catch(e) {
    el.textContent = 'Could not check OAuth status — is Claude Code installed?';
    dot.className = 'status-dot red';
    txt.textContent = 'OAuth unavailable';
  }
}

// ── Steps 2 + 3: Save models ──────────────────────────────────────────────────
async function saveModels() {
  const isStep2 = document.getElementById('step-2').classList.contains('visible');
  const errId = isStep2 ? 'err-2' : 'err-3';
  const btnId = isStep2 ? 'btn-2' : 'btn-3';
  showErr(errId, '');
  // Clear per-field errors on Step 3
  if (!isStep2) {
    document.querySelectorAll('.field-err').forEach(el => el.remove());
  }
  setBtn(btnId, 'Validating…', true);

  try {
    const payload = {
      xai_api_key: (document.getElementById('xai-key') || {value: ''}).value.trim(),
      google_api_key: (document.getElementById('google-key') || {value: ''}).value.trim(),
      openai_api_key: (document.getElementById('openai-key') || {value: ''}).value.trim(),
    };
    // Only send API key if that method was selected
    if (isStep2 && _authMethod === 'apikey') {
      const key = (document.getElementById('anthropic-key') || {value: ''}).value.trim();
      if (!key) { showErr(errId, 'Please enter your API key.'); setBtn(btnId, 'Continue →', false); return; }
      payload.anthropic_api_key = key;
    } else if (isStep2) {
      // OAuth mode — tell server to use subscription auth
      payload.auth_method = 'oauth';
    }
    const result = await apiFetch('/api/setup/models', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    // Step 3: show per-field validation errors, block if any key failed
    if (!isStep2 && result.errors && result.errors.length > 0) {
      const fieldMap = {xai: 'xai-key', grok: 'xai-key', google: 'google-key', openai: 'openai-key'};
      result.errors.forEach(msg => {
        const prefix = (msg.split(':')[0] || '').toLowerCase();
        const inputId = Object.keys(fieldMap).find(k => prefix.includes(k));
        const input = inputId ? document.getElementById(fieldMap[inputId]) : null;
        if (input) {
          const errDiv = document.createElement('div');
          errDiv.className = 'field-err';
          errDiv.textContent = msg;
          input.parentElement.appendChild(errDiv);
          input.style.borderColor = '#ef4444';
          input.addEventListener('input', () => {
            input.style.borderColor = '';
            errDiv.remove();
          }, {once: true});
        }
      });
      setBtn(btnId, 'Continue →', false);
      return;
    }
    showStep(isStep2 ? 3 : 4);
  } catch(e) {
    showErr(errId, e.message);
  } finally {
    setBtn(btnId, 'Continue →', false);
  }
}

// ── Step 4: Save workspace ────────────────────────────────────────────────────
async function saveWorkspace() {
  showErr('err-4', '');
  setBtn('btn-4', 'Saving…', true);
  try {
    await apiFetch('/api/setup/workspace', {
      method: 'POST',
      body: JSON.stringify({
        workspace_path: document.getElementById('workspace-path').value.trim(),
        permission_mode: _selectedMode(),
      }),
    });
    showStep(5);
  } catch(e) {
    showErr('err-4', e.message);
  } finally {
    setBtn('btn-4', 'Continue →', false);
  }
}

// ── Step 5: AI History ────────────────────────────────────────────────────────
let _historySources = [];
let _historyResult = null;
let _historyEmbedOptions = {};

// Scan for AI history on step load
async function scanHistory() {
  document.getElementById('history-scanning').style.display = 'block';
  document.getElementById('history-sources').style.display = 'none';
  document.getElementById('history-embed-box').style.display = 'none';
  document.getElementById('history-none').style.display = 'none';
  document.getElementById('history-indexing').style.display = 'none';

  try {
    const r = await apiFetch('/api/setup/history/scan');
    _historySources = r.sources || [];
    _historyEmbedOptions = r.embedding_options || {};
    document.getElementById('history-scanning').style.display = 'none';

    if (_historySources.length === 0) {
      document.getElementById('history-none').style.display = 'block';
      return;
    }

    // Render source cards
    const container = document.getElementById('history-sources');
    container.innerHTML = _historySources.map((s, i) => {
      return '<div class="history-source found">'
        + '<div class="src-icon">' + (s.source === 'claude' ? '🤖' : s.source === 'codex' ? '🧠' : '💬') + '</div>'
        + '<div class="src-body">'
        + '<div class="src-name">' + (s.name || s.source) + '</div>'
        + '<div class="src-detail">' + s.count + ' transcripts · ' + s.size_mb + ' MB · ' + s.path + '</div>'
        + '<div class="src-toggle">'
        + '<input type="checkbox" id="hist-src-' + i + '" checked />'
        + '<label for="hist-src-' + i + '">Index for search</label>'
        + '</div></div></div>';
    }).join('');
    container.style.display = 'block';

    // Render embedding options
    renderEmbedOptions();
  } catch(e) {
    document.getElementById('history-scanning').style.display = 'none';
    document.getElementById('history-none').style.display = 'block';
  }
}

function renderEmbedOptions() {
  const box = document.getElementById('history-embed-box');
  const optionsEl = document.getElementById('embed-options');
  const hasOllama = _historyEmbedOptions.ollama;
  const hasGemini = _historyEmbedOptions.gemini;

  if (!hasOllama && !hasGemini) {
    optionsEl.innerHTML =
      '<div class="embed-disabled" style="font-size:13px;color:var(--dim);padding:4px 0;">'
      + 'Install <a href="https://ollama.com" target="_blank" style="color:var(--accent)">Ollama</a> '
      + 'or add a Google API key to enable semantic search later.'
      + '</div>';
    box.style.display = 'block';
    return;
  }

  let html = '';
  if (hasOllama && hasGemini) {
    html += '<div class="embed-option" onclick="selectEmbed(\\'ollama\\')">'
      + '<input type="radio" name="embed-backend" value="ollama" id="embed-ollama" checked />'
      + '<div><div class="embed-label">Ollama (local, free)</div>'
      + '<div class="embed-hint">nomic-embed-text — runs locally, no API key needed</div></div></div>';
    html += '<div class="embed-option" onclick="selectEmbed(\\'gemini\\')">'
      + '<input type="radio" name="embed-backend" value="gemini" id="embed-gemini" />'
      + '<div><div class="embed-label">Google Gemini</div>'
      + '<div class="embed-hint">Uses your GOOGLE_API_KEY — higher quality, requires internet</div></div></div>';
  } else if (hasOllama) {
    html += '<div class="embed-option">'
      + '<input type="checkbox" id="embed-ollama" checked />'
      + '<div><div class="embed-label">Ollama (local, free)</div>'
      + '<div class="embed-hint">nomic-embed-text — runs locally, no API key needed</div></div></div>';
  } else {
    html += '<div class="embed-option">'
      + '<input type="checkbox" id="embed-gemini" checked />'
      + '<div><div class="embed-label">Google Gemini</div>'
      + '<div class="embed-hint">Uses your GOOGLE_API_KEY</div></div></div>';
  }

  html += '<div class="embed-option">'
    + '<input type="' + (hasOllama && hasGemini ? 'radio' : 'checkbox') + '" name="embed-backend" value="none" id="embed-none" />'
    + '<div><div class="embed-label">Skip for now</div>'
    + '<div class="embed-hint">You can enable search later from the dashboard</div></div></div>';

  optionsEl.innerHTML = html;
  box.style.display = 'block';
}

function selectEmbed(backend) {
  const el = document.getElementById('embed-' + backend);
  if (el) el.checked = true;
}

function _getSelectedEmbedBackend() {
  const ollama = document.getElementById('embed-ollama');
  const gemini = document.getElementById('embed-gemini');
  const none = document.getElementById('embed-none');
  if (none && none.checked) return null;
  if (ollama && ollama.checked) return 'ollama';
  if (gemini && gemini.checked) return 'gemini';
  return null;
}

function _getSelectedSources() {
  const selected = [];
  _historySources.forEach((s, i) => {
    const cb = document.getElementById('hist-src-' + i);
    if (cb && cb.checked) selected.push(s.source);
  });
  return selected;
}

async function saveHistory() {
  showErr('err-5', '');
  const sources = _getSelectedSources();
  const backend = _getSelectedEmbedBackend();

  // If no sources selected or no embedding, quick save
  if (sources.length === 0 || !backend) {
    setBtn('btn-5', 'Saving…', true);
    try {
      await apiFetch('/api/setup/history', {
        method: 'POST',
        body: JSON.stringify({ sources: sources, embedding_backend: null }),
      });
      _historyResult = { indexed: 0 };
      showStep(6);
    } catch(e) {
      showErr('err-5', e.message);
    } finally {
      setBtn('btn-5', 'Continue →', false);
    }
    return;
  }

  // Embedding requested — SSE stream
  setBtn('btn-5', 'Indexing…', true);
  document.getElementById('history-indexing').style.display = 'block';
  document.getElementById('history-bar').style.width = '5%';
  document.getElementById('history-status').textContent = 'Starting…';

  try {
    const res = await fetch('/api/setup/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ sources: sources, embedding_backend: backend }),
    });

    if (!res.ok) throw new Error('Server error ' + res.status);

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch { continue; }

        if (evt.type === 'progress') {
          document.getElementById('history-bar').style.width = (evt.pct || 50) + '%';
          document.getElementById('history-status').textContent = evt.step || 'Indexing…';
        } else if (evt.type === 'done') {
          document.getElementById('history-bar').style.width = '100%';
          document.getElementById('history-status').textContent = 'Done!';
          _historyResult = evt.result || { indexed: 0 };
          setTimeout(() => showStep(6), 600);
          return;
        } else if (evt.type === 'error') {
          throw new Error(evt.message || 'Indexing failed');
        }
      }
    }
    // Stream ended without explicit done
    _historyResult = { indexed: 0 };
    showStep(6);
  } catch(e) {
    showErr('err-5', e.message);
    document.getElementById('history-indexing').style.display = 'none';
  } finally {
    setBtn('btn-5', 'Continue →', false);
  }
}

// Trigger scan when step 5 becomes visible
const _origShowStep = showStep;
showStep = function(n) {
  _origShowStep(n);
  if (n === 3) checkCodexStatus();
  if (n === 5 && !_historySources.length) scanHistory();
};

async function checkCodexStatus() {
  const wrap = document.getElementById('codex-status');
  const dot = document.getElementById('codex-dot');
  const txt = document.getElementById('codex-text');
  try {
    const r = await apiFetch('/api/setup/codex-status');
    if (r.loggedIn) {
      wrap.style.display = 'flex';
      dot.className = 'dot-sm green';
      const via = r.provider ? ' via ' + r.provider : '';
      txt.textContent = 'Codex CLI logged in' + via + ' — API key optional';
    } else if (r.error !== 'not_installed') {
      wrap.style.display = 'flex';
      dot.className = 'dot-sm yellow';
      txt.textContent = 'Codex CLI not logged in — enter API key or run: codex login';
    }
    // If not installed, hide the status row entirely
  } catch(e) {
    // silent — codex is optional
  }
}

// ── Step 6: Knowledge scan ────────────────────────────────────────────────────
function skipKnowledge() {
  _scanResult = { skipped: true, files_written: 0 };
  fetch('/api/setup/knowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: JSON.stringify({ scan: false }),
  }).catch(() => {});
  goToDone();
}

function cancelScan() {
  if (_scanAbort) { _scanAbort.abort(); _scanAbort = null; }
  showStep(6);
}

function retryOrScan() { startScan(); }

async function startScan() {
  showStep(6.1);
  document.getElementById('scan-bar').style.width = '8%';
  document.getElementById('scan-status').textContent = 'Starting…';
  document.getElementById('scan-found').textContent = '';

  _scanAbort = new AbortController();

  try {
    const res = await fetch('/api/setup/knowledge', {
      method: 'POST',
      signal: _scanAbort.signal,
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ scan: true }),
    });

    if (!res.ok) throw new Error('Server error ' + res.status);

    // SSE stream
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch { continue; }

        if (evt.type === 'progress') {
          document.getElementById('scan-bar').style.width = (evt.pct || 50) + '%';
          document.getElementById('scan-status').textContent = evt.step || 'Scanning…';
          if (evt.found) document.getElementById('scan-found').textContent = evt.found;
        } else if (evt.type === 'done') {
          document.getElementById('scan-bar').style.width = '100%';
          document.getElementById('scan-status').textContent = 'Done!';
          _scanResult = { skipped: false, files_written: (evt.result || {}).files_written || 0 };
          setTimeout(goToDone, 600);
          return;
        } else if (evt.type === 'error') {
          throw new Error(evt.message || 'Scan failed');
        }
      }
    }
    // Stream ended without done event — treat as success
    goToDone();
  } catch(e) {
    if (e.name === 'AbortError') return; // cancelled
    document.getElementById('scan-error-msg').textContent = e.message || 'Scan failed';
    showStep(6.2);
  }
}

// ── Step 7: Done ──────────────────────────────────────────────────────────────
function goToDone() {
  const xaiKey = (document.getElementById('xai-key') || {value: ''}).value.trim();
  const googleKey = (document.getElementById('google-key') || {value: ''}).value.trim();

  const items = [
    { label: 'TLS certificates generated + trusted', ok: true },
    { label: 'Server started on localhost', ok: true },
    { label: 'Claude Code connected', ok: true },
    { label: 'Grok API key', ok: !!xaiKey, skip_label: 'skipped' },
    { label: 'Google API key', ok: !!googleKey, skip_label: 'skipped' },
    {
      label: 'AI history indexed',
      ok: _historyResult && _historyResult.indexed > 0,
      skip_label: 'skipped',
      ok_label: (_historyResult ? _historyResult.indexed : 0) + ' transcripts indexed',
    },
    {
      label: 'Knowledge scan',
      ok: !_scanResult.skipped,
      skip_label: 'skipped — run /add-knowledge later',
      ok_label: _scanResult.files_written + ' files generated',
    },
  ];

  const list = document.getElementById('done-list');
  list.innerHTML = items.map(item => {
    const iconClass = item.ok ? 'ok' : 'skip';
    const icon = item.ok ? '✓' : '–';
    const textClass = item.ok ? '' : 'skipped';
    const extra = item.ok
      ? (item.ok_label ? ' <span class="done-label">' + item.ok_label + '</span>' : '')
      : (item.skip_label ? ' <span class="done-label">' + item.skip_label + '</span>' : '');
    return '<div class="done-item"><div class="done-icon ' + iconClass + '">' + icon + '</div>'
      + '<div class="done-text ' + textClass + '">' + item.label + extra + '</div></div>';
  }).join('');

  showStep(7);
}

async function finishSetup() {
  const btn = document.getElementById('open-btn');
  btn.disabled = true;
  btn.textContent = 'Opening…';
  try {
    await apiFetch('/api/setup/complete', { method: 'POST' });
  } catch(e) { /* non-fatal */ }
  window.location.href = '/';
}
</script>
</body>
</html>"""
