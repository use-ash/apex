# Auto-extracted from chat_html.py during modular split.

CHAT_BODY_HTML = r"""
<div class="alert-toast" id="alertToast">
  <div class="alert-toast-inner" id="alertToastInner">
    <span class="alert-icon" id="alertToastIcon"></span>
    <div class="alert-body">
      <div class="alert-source" id="alertToastSource"></div>
      <div class="alert-title" id="alertToastTitle"></div>
      <div class="alert-text" id="alertToastText"></div>
      <div class="alert-preview" id="alertToastPreview"></div>
    </div>
    <div class="alert-actions" id="alertToastActions"></div>
  </div>
</div>

<div class="topbar">
  <button class="btn-icon" id="menuBtn">&#9776;</button>
  <h1 id="chatTitle">ApexChat</h1>
  <span class="topbar-profile" id="topbarProfile">
    <span class="tp-avatar" id="topbarProfileAvatar"></span>
    <span class="tp-name" id="topbarProfileName"></span>
  </span>
  <span class="status ok" id="statusDot"></span>
  <span class="mode-badge {{MODE_CLASS}}" id="modeBadge">{{MODE_LABEL}}</span>
  <span class="alert-badge" id="alertBadge" title="Alerts">&#128276;<span class="count" id="alertCount"></span></span>
  <button class="btn-icon" id="themeBtn" title="Toggle theme">&#9681;</button>
  <button class="btn-icon" id="settingsBtn" title="Settings">&#9881;</button>
  <button class="btn-icon" id="refreshBtn" title="Refresh">&#8635;</button>
</div>
<div class="alerts-panel" id="alertsPanel">
  <div class="alerts-panel-header">
    <span>Alerts</span>
    <button id="clearAlertsBtn">Clear All</button>
  </div>
  <div id="alertsList"></div>
</div>

<div class="settings-panel" id="settingsPanel">
  <div class="settings-header">
    <span>Settings</span>
    <button id="settingsCloseBtn">&times;</button>
  </div>
  <div class="settings-body">
    <div class="settings-section">
      <label class="settings-label">Chat Model</label>
      <div class="settings-hint" id="chatModelHint">Select a chat first</div>
      <select id="chatModelSelect" disabled>
        <option value="">Loading...</option>
      </select>
    </div>
    <div class="settings-section">
      <label class="settings-label">Server Default</label>
      <div class="settings-value" id="serverModelDisplay">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Local Models (Ollama)</label>
      <div class="settings-value" id="ollamaModelsList">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Memory Whisper</label>
      <div class="settings-hint">Injects relevant memories into each turn</div>
      <div class="settings-value" id="whisperStatus">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Embedding Index</label>
      <div class="settings-value" id="embeddingStatus">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Build</label>
      <div class="settings-hint">Version • branch • commit</div>
      <div class="settings-value" id="buildInfoDisplay">--</div>
    </div>
    <div class="settings-section">
      <a href="/admin/" target="_blank" style="display:inline-flex;align-items:center;gap:6px;color:var(--accent);text-decoration:none;font-size:13px;font-weight:600">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        Admin Dashboard
      </a>
    </div>
    <div class="settings-section">
      <label class="settings-label">Usage Meter</label>
      <select id="usageMeterSelect">
        <option value="always">Always visible</option>
        <option value="auto">Auto-hide (5s)</option>
        <option value="off">Off</option>
      </select>
    </div>
    <div class="settings-section">
      <label class="settings-label">Text Size</label>
      <div class="settings-hint">
        <span>Font Scale</span>
        <span id="fontScaleValue">100%</span>
      </div>
      <input type="range" id="fontScaleSlider" min="70" max="200" step="10" value="100">
      <button id="fontScaleResetBtn" type="button" style="display:none;margin-top:8px;background:none;border:none;color:var(--accent);cursor:pointer;font-size:12px;padding:0">
        Reset to Default
      </button>
    </div>
  </div>
</div>

<div class="usage-bar" id="usageBar">
  <span class="usage-label" id="usageLabel">Claude</span>
  <div class="usage-bucket" id="usageSession">
    <div class="label-row">
      <span class="label">Session</span>
      <span><span class="pct" id="usageSessionPct">-</span> <span class="reset" id="usageSessionReset"></span></span>
    </div>
    <div class="usage-track"><div class="usage-fill green" id="usageSessionFill" style="width:0%"></div></div>
  </div>
  <div class="usage-bucket" id="usageWeekly">
    <div class="label-row">
      <span class="label">Weekly</span>
      <span><span class="pct" id="usageWeeklyPct">-</span> <span class="reset" id="usageWeeklyReset"></span></span>
    </div>
    <div class="usage-track"><div class="usage-fill green" id="usageWeeklyFill" style="width:0%"></div></div>
  </div>
  <button class="usage-toggle" id="usageToggle" title="Hide usage meter">&#10005;</button>
</div>

<div class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h2>Channels</h2>
    <button class="sidebar-pin" id="pinSidebarBtn" title="Pin sidebar" aria-pressed="false">&#128204;</button>
  </div>
  <div class="sidebar-body">
    <div class="new-btn" id="newChatBtn">+ New Channel</div>
    <div id="chatList"></div>
    <div class="sidebar-section-header thread-section-header" id="threadSectionHeader" style="display:none">
      <span class="section-label">Threads</span>
      <button class="section-toggle" id="threadToggle" title="Toggle threads">▾</button>
    </div>
    <div id="threadList"></div>
  </div>
</div>
<div class="sidebar-overlay" id="sidebarOverlay"></div>

<div class="messages" id="messages"></div>

<div class="side-panel" id="sidePanel">
  <div class="sp-drag-handle" id="spDragHandle"></div>
  <div class="sp-header">
    <div class="sp-title" id="spTitle"></div>
    <button class="sp-close" id="spCloseBtn">&#10005;</button>
  </div>
  <div class="sp-body" id="spBody"></div>
</div>
<div class="sp-backdrop" id="spBackdrop"></div>

<div class="debugbar" id="debugBar" style="display:none">
  <div class="debug-state" id="debugState">booting</div>
  <div class="debug-log" id="debugLog"></div>
</div>

<div id="attachPreview" class="attach-preview"></div>
<div id="transcribeStatus" class="transcribing" style="display:none"></div>
<div class="context-bar" id="contextBar">
  <span class="context-detail" id="contextDetail">--</span>
  <div class="context-track">
    <div class="context-fill green" id="contextFill" style="width:0%"></div>
  </div>
</div>
<div class="drop-overlay" id="dropOverlay"><div class="drop-overlay-inner">&#128206; Drop files to attach</div></div>
<div class="premium-locked-bar" id="premiumLockedBar" style="display:none;position:fixed;bottom:0;left:0;right:0;z-index:10;background:var(--surface);padding:10px 0;padding-bottom:calc(10px + var(--sab))">
  <div style="padding:14px 16px;background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.2);border-radius:10px;margin:0 12px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="font-size:16px">🔒</span>
      <div style="font-weight:600;font-size:13px;color:var(--yellow,#F59E0B)">Group channels require Apex Pro</div>
      <div style="font-size:11px;color:var(--dim);margin-left:auto">Message history preserved</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <a href="https://buy.stripe.com/dRmcN40Ag8Qucptc2UcQU04" target="_blank" style="flex:1;text-align:center;padding:8px 12px;background:var(--card);border:1px solid var(--card);border-radius:6px;color:var(--text);text-decoration:none;font-size:12px;font-weight:600">$29.99<span style="font-weight:400;color:var(--dim)">/mo</span></a>
      <a href="https://buy.stripe.com/9B6cN46YE3wa6153wocQU05" target="_blank" style="flex:1;text-align:center;padding:8px 12px;background:var(--accent);border:1px solid var(--accent);border-radius:6px;color:#fff;text-decoration:none;font-size:12px;font-weight:600">$249<span style="font-weight:400;opacity:.8">/yr</span> <span style="font-size:10px;opacity:.7">save 30%</span></a>
      <a href="https://buy.stripe.com/6oUeVc96Mc2G7593wocQU06" target="_blank" style="flex:1;text-align:center;padding:8px 12px;background:linear-gradient(135deg,#F59E0B,#D97706);border:none;border-radius:6px;color:#fff;text-decoration:none;font-size:12px;font-weight:600">$499 <span style="font-weight:400;opacity:.8">lifetime</span> <span style="font-size:10px;opacity:.7">limited</span></a>
    </div>
  </div>
</div>
<div class="composer" id="composerBar" style="position:relative">
  <div class="stale-bar banner-warn" id="staleBar" role="status" aria-live="polite">
    <span class="banner-dot"></span>
    <span class="stale-label" id="staleLabel">No response for <span class="stale-timer" id="staleTimer">30s</span></span>
    <div class="stale-actions">
      <button type="button" class="stale-action" id="staleCancelBtn">Cancel</button>
      <button type="button" class="stale-action primary" id="staleRetryBtn" style="display:none">Retry</button>
    </div>
  </div>
  <div class="mention-popup" id="mentionPopup"></div>
  <label class="btn-compose" id="attachBtn" title="Attach file" style="cursor:pointer">
    &#128206;
    <input type="file" id="fileInput" style="position:absolute;width:0;height:0;overflow:hidden;opacity:0" multiple accept="image/*,.txt,.py,.json,.csv,.md,.yaml,.yml,.toml,.sh,.js,.ts,.html,.css">
  </label>
  <textarea id="input" rows="1" placeholder="Message..." autocomplete="off"></textarea>
  <button class="btn-compose" id="sendBtn" title="Send">&#9654;</button>
  <div class="stop-menu" id="stopMenu"></div>
</div>
"""
