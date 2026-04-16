# Auto-extracted from chat_html.py during modular split.

_JS_ERROR_HANDLER = """window.onerror = (msg, src, line, col, err) => {
  document.title = 'JS ERROR: ' + msg;
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;padding:8px;z-index:9999;font-size:12px';
  d.textContent = `JS Error: ${msg} (line ${line})`;
  document.body.prepend(d);
};"""

_JS_STATE = """let ws = null;
let currentChat = sessionStorage.getItem('currentChatId') || null;
let streaming = false;
let currentBubble = null;
let currentSpeaker = null; // {name, avatar, id} for group @mention routing
let currentStreamId = '';
let composerHasDraft = false;
let lastSubmittedPrompt = '';
const activeStreams = new Map(); // stream_id -> {name, avatar, profile_id}
let queuedMessages = []; // [{msg_id, stream_id, preview, agent}]
let _stopMenuConfirmKey = '';
// Per-stream context: supports concurrent agent streams without clobbering"""

_JS_STREAM_CONTEXT = """const _streamCtx = {};  // stream_id -> {bubble, speaker, toolPill, toolCalls, ...}
// Per-chat last-seen event seq — dedupes events that arrive via both live-send
// and attach-replay paths. Server attaches {seq, epoch} to every stream event.
// Reset on epoch mismatch (server restart) or new ws connection.
const _lastSeenSeq = {};  // chat_id -> {epoch, seq}
function _newStreamCtx(streamId, speaker) {
  return {
    id: streamId,
    bubble: null,
    speaker: speaker,
    toolPill: null,
    thinkingPill: null,
    thinkingBlock: null,
    liveThinkingPill: null,
    liveThinkingTimer: null,
    thinkingCollapsed: false,
    toolCalls: [],
    textContent: '',
    thinkingText: '',
    thinkingStart: null,
    toolsStart: null,
    completedToolCount: 0,
    _mdTimer: null,
    awaitingAck: false,
    queued: false,
    queuedPosition: 0,
    watchdogLastEventAt: 0,
    watchdogMode: 'silent',
    watchdogLastReason: '',
  };
}
function _upsertStreamCtx(streamId, speaker = null) {
  let ctx = _streamCtx[streamId];
  if (!ctx) {
    ctx = _newStreamCtx(streamId, speaker);
    _streamCtx[streamId] = ctx;
    return ctx;
  }
  ctx.id = streamId;
  if (speaker) ctx.speaker = speaker;
  return ctx;
}
function _activeStreamIds() {
  return Object.keys(_streamCtx);
}
function _resolveStreamId(input = null, options = {}) {
  const allowFocusedFallback = Boolean(options.allowFocusedFallback);
  const requested = typeof input === 'string' ? input : ((input && input.stream_id) || '');
  if (requested && _streamCtx[requested]) return requested;
  // B-19v2: if message explicitly names a stream that's already finalized,
  // don't fall through to heuristics — return empty so caller no-ops
  if (requested) return '';
  const ids = _activeStreamIds();
  if (ids.length === 1) return ids[0];
  if (allowFocusedFallback && currentStreamId && _streamCtx[currentStreamId]) return currentStreamId;
  return requested || '';
}
function _getCtx(input = null, options = {}) {
  const sid = _resolveStreamId(input, options);
  return sid ? (_streamCtx[sid] || null) : null;
}
function _isAnyStreamActive() {
  return _activeStreamIds().length > 0;
}
function _syncLegacyStreamGlobals(preferredSid = '', options = {}) {
  const clearSessionWhenIdle = options.clearSessionWhenIdle !== false;
  const ids = _activeStreamIds();
  let sid = '';
  if (preferredSid && _streamCtx[preferredSid]) {
    sid = preferredSid;
  } else if (currentStreamId && _streamCtx[currentStreamId]) {
    sid = currentStreamId;
  } else {
    sid = ids[ids.length - 1] || '';
  }
  currentStreamId = sid;
  const ctx = sid ? (_streamCtx[sid] || null) : null;
  currentBubble = ctx ? (ctx.bubble || null) : null;
  currentSpeaker = ctx ? (ctx.speaker || null) : null;
  streaming = ids.length > 0;
  if (!streaming) {
    currentStreamId = '';
    currentBubble = null;
    currentSpeaker = null;
    if (clearSessionWhenIdle) sessionStorage.removeItem('streamingChatId');
    clearStreamWatchdog();
  }
  return ctx;
}
function _activateStream(ctxOrSid, options = {}) {
  const sid = typeof ctxOrSid === 'string' ? ctxOrSid : ((ctxOrSid && ctxOrSid.id) || '');
  if (!sid) return null;
  const ctx = typeof ctxOrSid === 'string' ? (_streamCtx[sid] || null) : ctxOrSid;
  if (!ctx) return null;
  const chatId = options.chatId || '';
  if (chatId || currentChat) {
    sessionStorage.setItem('streamingChatId', chatId || currentChat || '');
  }
  return _syncLegacyStreamGlobals(sid, {clearSessionWhenIdle: false});
}
function _removeStreamCtx(streamId, options = {}) {
  if (!streamId) return null;
  const ctx = _streamCtx[streamId] || null;
  if (ctx) {
    clearTimeout(ctx._mdTimer);
    ctx._mdTimer = null;
    _teardownThinking(ctx);
    if (options.removeBubble) {
      if (ctx.thinkingPill && ctx.thinkingPill.isConnected) ctx.thinkingPill.remove();
      if (ctx.toolPill && ctx.toolPill.isConnected) ctx.toolPill.remove();
      if (ctx.bubble && ctx.bubble.isConnected) ctx.bubble.remove();
    }
  }
  delete _streamCtx[streamId];
  activeStreams.delete(streamId);
  return ctx;
}
function _finalizeStream(streamId, options = {}) {
  const sid = _resolveStreamId(streamId, {allowFocusedFallback: true});
  if (!sid) return null;
  const finished = activeStreams.get(sid);
  const ctx = _streamCtx[sid] || null;
  if (ctx) {
    _finalizeStreamUi(ctx, options.resultMsg || null);
  } else {
    _clearStreamingBubbleState(sid, null);
  }
  _removeStreamCtx(sid);
  _syncLegacyStreamGlobals(options.preferredSid || '', {clearSessionWhenIdle: options.clearSessionWhenIdle !== false});
  // B-19v2: only sweep all streaming classes when no siblings are still active —
  // sweeping while another stream runs strips its .streaming class and causes
  // double banner / orphaned UI state
  if (!_isAnyStreamActive()) _clearStreamingBubbleState('', null, true);
  return sid;
}
function _resetAllStreamState(options = {}) {
  const removeBubbles = Boolean(options.removeBubbles);
  Object.values(_streamCtx).forEach(ctx => {
    clearTimeout(ctx._mdTimer);
    ctx._mdTimer = null;
    _teardownThinking(ctx);
    _clearStreamingBubbleState(ctx.id || '', ctx.bubble || null);
    if (removeBubbles) {
      if (ctx.thinkingPill && ctx.thinkingPill.isConnected) ctx.thinkingPill.remove();
      if (ctx.toolPill && ctx.toolPill.isConnected) ctx.toolPill.remove();
      if (ctx.bubble && ctx.bubble.isConnected) ctx.bubble.remove();
    }
  });
  Object.keys(_streamCtx).forEach(k => delete _streamCtx[k]);
  activeStreams.clear();
  _clearStreamingBubbleState('', null, true);
  _syncLegacyStreamGlobals('', {clearSessionWhenIdle: options.clearSessionWhenIdle !== false});
}
function _getCurrentBubble() {
  const ctx = currentStreamId ? (_streamCtx[currentStreamId] || null) : null;
  return ctx ? ctx.bubble : null;
}
let currentGroupMembers = []; // [{profile_id, name, avatar, role_description}] for @mention autocomplete
let _premiumFeaturesCache = null; // cached /api/features response
let _premiumCacheTime = 0;
async function _checkPremiumFeatures() {
  const now = Date.now();
  if (_premiumFeaturesCache && now - _premiumCacheTime < 60000) return _premiumFeaturesCache;
  try {
    const r = await fetch('/api/features', {credentials: 'same-origin'});
    if (r.ok) { _premiumFeaturesCache = await r.json(); _premiumCacheTime = now; }
  } catch(e) {}
  return _premiumFeaturesCache || {groups_enabled: true, features: {groups: true}};
}
let mentionSelectedIdx = 0;
let initStarted = false;
let initDone = false;
let initPromise = null;
let initTrigger = 'boot';
let reconnectTimer = null;
let _resumeWaitInterval = null;
let _resumeWaitTimeout = null;
let knownChatCount = 0;
let selectChatSeq = 0;
let staleBarTick = null;
let staleState = 'idle';
let mediaRecorder = null;
let mediaStream = null;
let recording = false;
let recordingChunks = [];
let transcribing = false;

function refreshComposerDraftState() {
  const inputEl = document.getElementById('input');
  composerHasDraft = Boolean((inputEl && inputEl.value.trim()) || pendingAttachments.length);
  updateSendBtn();
}

function clearComposerDraft({keepFocus = false} = {}) {
  const inputEl = document.getElementById('input');
  if (!inputEl) return;
  inputEl.value = '';
  inputEl.style.height = 'auto';
  pendingAttachments = [];
  document.getElementById('attachPreview').innerHTML = '';
  _hideMentionPopup();
  refreshComposerDraftState();
  if (keepFocus) inputEl.focus();
}

function restoreComposerDraft(text, attachments = []) {
  const inputEl = document.getElementById('input');
  pendingAttachments = attachments.map(att => ({...att}));
  renderAttachmentPreview();
  if (!inputEl) {
    refreshComposerDraftState();
    return;
  }
  inputEl.value = text;
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  refreshComposerDraftState();
  inputEl.focus();
}

function hideStopMenu() {
  document.getElementById('stopMenu')?.classList.remove('show');
  _stopMenuConfirmKey = '';
}
"""

_JS_STOP_MENU = """function _elapsedLabel(startedAt) {
  if (!startedAt) return '';
  const sec = Math.round((Date.now() - startedAt) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}

function _queuePreview(preview = '') {
  const text = String(preview || '').trim();
  return text || 'Queued message';
}

function _stopMenuLabel(label, confirmLabel, isConfirm) {
  return isConfirm ? confirmLabel : label;
}

function _appendStopMenuRow(menu, spec) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = spec.className || '';
  if (spec.confirmKey && _stopMenuConfirmKey === spec.confirmKey) btn.classList.add('stop-confirm');
  const label = _stopMenuLabel(spec.label, spec.confirmLabel || spec.label, spec.confirmKey && _stopMenuConfirmKey === spec.confirmKey);
  const time = spec.elapsed ? `<span class="agent-time">${escHtml(spec.elapsed)}</span>` : '';
  btn.innerHTML = `<span class="${spec.dot ? 'stop-dot' : 'stop-icon'}">${spec.dot ? '' : escHtml(spec.icon || '')}</span><span class="stop-label">${escHtml(label)}</span>${time}`;
  btn.onclick = (e) => {
    e.stopPropagation();
    if (!spec.confirmKey) {
      spec.onConfirm();
      return;
    }
    if (_stopMenuConfirmKey === spec.confirmKey) {
      const run = spec.onConfirm;
      hideStopMenu();
      run();
      return;
    }
    _stopMenuConfirmKey = spec.confirmKey;
    renderStopMenu();
  };
  menu.appendChild(btn);
}

function renderStopMenu() {
  const menu = document.getElementById('stopMenu');
  if (!menu) return;
  const activeRows = Array.from(activeStreams.values());
  const queuedRows = Array.isArray(queuedMessages) ? queuedMessages.slice() : [];
  menu.innerHTML = '';
  if (!activeRows.length && !queuedRows.length) {
    hideStopMenu();
    return;
  }
  activeRows.forEach(stream => {
    const isGroupRow = activeRows.length > 1 || currentChatType === 'group';
    const who = isGroupRow ? `${stream.avatar || ''} ${stream.name || 'this response'}`.trim() : 'this response';
    _appendStopMenuRow(menu, {
      label: `Stop ${who}`,
      confirmLabel: `Tap again to stop ${who}`,
      confirmKey: `active:${stream.stream_id}`,
      dot: false,
      icon: '⏹',
      elapsed: _elapsedLabel(stream.startedAt),
      onConfirm: () => stopStream(stream.stream_id),
    });
  });
  queuedRows.forEach(item => {
    const preview = _queuePreview(item.preview || item.msg_id || '');
    _appendStopMenuRow(menu, {
      label: `Cancel "${preview}"`,
      confirmLabel: `Tap again to cancel "${preview}"`,
      confirmKey: `queued:${item.msg_id || item.stream_id || ''}`,
      dot: false,
      icon: '✕',
      onConfirm: () => cancelQueuedMessage(item.msg_id || item.stream_id || ''),
    });
  });
  if (activeRows.length || queuedRows.length) {
    menu.appendChild(document.createElement('hr'));
  }
  if (activeRows.length + queuedRows.length > 1) {
    _appendStopMenuRow(menu, {
      label: 'Stop + cancel all',
      confirmLabel: 'Tap again to stop + cancel all',
      confirmKey: 'all',
      className: 'stop-all',
      dot: false,
      icon: '⏹',
      onConfirm: () => stopAllStreams(),
    });
    menu.appendChild(document.createElement('hr'));
  }
  _appendStopMenuRow(menu, {
    label: '← Keep going',
    className: 'stop-keep',
    dot: false,
    icon: '←',
    onConfirm: () => hideStopMenu(),
  });
}

function stopStream(streamId) {
  if (!currentChat || !streamId) return;
  cancelStream(streamId).catch(err => reportError('stop stream', err));
}

async function cancelQueuedMessage(msgId) {
  if (!currentChat || !msgId || !ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify({action: 'cancel_queued', chat_id: currentChat, msg_id: msgId}));
  } catch (err) {
    reportError('cancel queued', err);
  }
}

function stopAllStreams() {
  if (!currentChat || !ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify({action: 'stop_all', chat_id: currentChat}));
    if (activeStreams.size > 0) {
      Array.from(activeStreams.keys()).forEach(sid => _finalizeStream(sid, {trackAnswered: false}));
    }
  } catch (err) {
    reportError('stop all streams', err);
  }
}

function toggleStopMenu() {
  const menu = document.getElementById('stopMenu');
  const hasStopTargets = activeStreams.size > 0 || queuedMessages.length > 0;
  if (!menu || !hasStopTargets) return;
  if (!menu.classList.contains('show')) {
    _stopMenuConfirmKey = '';
    renderStopMenu();
    menu.classList.add('show');
    return;
  }
  hideStopMenu();
}
"""

_JS_DEBUG = """function dbg(...args) {
  const ts = new Date().toLocaleTimeString();
  const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
  const line = `[${ts}] ${msg}`;
  console.log('[lc]', ...args);
  const logEl = document.getElementById('debugLog');
  if (logEl) {
    logEl.textContent += line + '\\n';
    logEl.scrollTop = logEl.scrollHeight;
  }
}

function wsStateLabel() {
  if (!ws) return 'none';
  switch (ws.readyState) {
    case WebSocket.CONNECTING: return 'connecting';
    case WebSocket.OPEN: return 'open';
    case WebSocket.CLOSING: return 'closing';
    case WebSocket.CLOSED: return 'closed';
    default: return `unknown:${ws.readyState}`;
  }
}

function refreshDebugState(reason = '') {
  const stateEl = document.getElementById('debugState');
  if (!stateEl) return;
  const parts = [
    `ws=${wsStateLabel()}`,
    `init=${initDone ? 'done' : (initStarted ? 'running' : 'idle')}`,
    `chat=${currentChat || 'none'}`,
    `chats=${knownChatCount}`,
    `streaming=${_isAnyStreamActive() ? 'yes' : 'no'}`,
  ];
  if (reason) parts.push(`last=${reason}`);
  stateEl.textContent = parts.join(' | ');
}

function reportError(context, err) {
  const message = err?.message || String(err);
  dbg(`ERROR: ${context}:`, message);
  refreshDebugState(`error:${context}`);
}

function updateConnectionIndicators() {
  const dot = document.getElementById('statusDot');
  const badge = document.getElementById('modeBadge');
  if (!dot || !badge) return;

  let badgeClass = 'mode-badge trusted';
  let badgeTitle = 'mTLS disconnected';
  const state = ws ? ws.readyState : WebSocket.CLOSED;

  if (state === WebSocket.OPEN) {
    dot.className = 'status ok';
    badgeClass = 'mode-badge guarded';
    badgeTitle = 'mTLS connected';
  } else if (state === WebSocket.CONNECTING || state === WebSocket.CLOSING) {
    dot.className = 'status';
    badgeClass = 'mode-badge mtls';
    badgeTitle = state === WebSocket.CONNECTING ? 'mTLS connecting' : 'mTLS closing';
  } else {
    dot.className = 'status err';
  }

  badge.className = badgeClass;
  badge.textContent = 'mTLS';
  badge.title = badgeTitle;
}
"""

_JS_STREAM_WATCHDOG = """function clearStreamWatchdog() {
  if (staleBarTick) {
    clearInterval(staleBarTick);
    staleBarTick = null;
  }
  staleState = 'idle';
  hideStaleBar({immediate: true});
  _renderWatchdogPills();
}

function _formatElapsedForLabel(ms) {
  const totalSec = Math.max(0, Math.round((ms || 0) / 1000));
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}m ${sec}s`;
}

function _ctxWatchdogMode(ctx) {
  if (!ctx) return 'silent';
  return ctx.watchdogMode === 'active' ? 'active' : 'silent';
}

function _ctxWatchdogKind(ctx) {
  if (!ctx) return 'silent';
  if (_ctxHasActiveTool(ctx) || ctx.watchdogLastReason === 'tool-use' || ctx.watchdogLastReason === 'tool-result') {
    return 'tool';
  }
  if (_ctxWatchdogMode(ctx) === 'active') return 'thinking';
  return 'silent';
}

function _watchdogThresholds(mode) {
  return mode === 'active'
    ? {warnMs: 120000, stuckMs: 300000}
    : {warnMs: 30000, stuckMs: 120000};
}

function _ctxWatchdogStateInfo(ctx, now = Date.now()) {
  if (!ctx || !ctx.watchdogLastEventAt) return null;
  const mode = _ctxWatchdogMode(ctx);
  const thresholds = _watchdogThresholds(mode);
  const since = Math.max(0, now - ctx.watchdogLastEventAt);
  let state = 'working';
  if (since >= thresholds.stuckMs) state = 'stuck';
  else if (since >= thresholds.warnMs) state = 'stale';
  return {
    mode,
    kind: _ctxWatchdogKind(ctx),
    state,
    since,
    thresholds,
  };
}

function _pickWatchdogTarget(now = Date.now()) {
  let pickedCtx = null;
  let pickedInfo = null;
  const severityRank = {working: 0, stale: 1, stuck: 2};
  Object.values(_streamCtx).forEach(ctx => {
    const info = _ctxWatchdogStateInfo(ctx, now);
    if (!info || info.state === 'working') return;
    if (!pickedCtx) {
      pickedCtx = ctx;
      pickedInfo = info;
      return;
    }
    const severityDiff = (severityRank[info.state] || 0) - (severityRank[pickedInfo.state] || 0);
    if (severityDiff > 0 || (severityDiff === 0 && info.since > pickedInfo.since)) {
      pickedCtx = ctx;
      pickedInfo = info;
    }
  });
  if (!pickedCtx || !pickedInfo) return null;
  return {ctx: pickedCtx, info: pickedInfo};
}

function _thinkingPillLabel(ctx, info) {
  if (!ctx || !info || info.state === 'working') return 'Thinking...';
  const elapsed = _formatElapsedForLabel(info.since);
  if (info.kind === 'tool') {
    if (info.state === 'stuck') return `Tool may be stuck · ${elapsed}`;
    return `Tool running for ${elapsed}`;
  }
  if (info.state === 'stuck') return `No response · ${elapsed}`;
  return `Waiting for response… ${elapsed}`;
}

function _renderWatchdogPills() {
  const now = Date.now();
  Object.values(_streamCtx).forEach(ctx => {
    const pill = ctx && ctx.liveThinkingPill;
    if (!pill || !pill.isConnected) return;
    const label = pill.querySelector('.pill-label');
    if (!label) return;
    const info = _ctxWatchdogStateInfo(ctx, now);
    label.textContent = _thinkingPillLabel(ctx, info);
    if (!info || info.state === 'working') {
      pill.style.borderColor = '';
      pill.style.background = '';
      pill.style.color = '';
      const live = pill.querySelector('.pill-live');
      if (live) live.style.background = '';
    } else if (info.state === 'stale') {
      pill.style.borderColor = 'rgba(245,158,11,0.35)';
      pill.style.background = 'rgba(245,158,11,0.06)';
      pill.style.color = 'var(--yellow)';
      const live = pill.querySelector('.pill-live');
      if (live) live.style.background = 'var(--yellow)';
    } else {
      pill.style.borderColor = 'rgba(239,68,68,0.35)';
      pill.style.background = 'rgba(239,68,68,0.06)';
      pill.style.color = 'var(--red)';
      const live = pill.querySelector('.pill-live');
      if (live) live.style.background = 'var(--red)';
    }
  });
}

function hideStaleBar(options = {}) {
  const immediate = Boolean(options.immediate);
  const bar = document.getElementById('staleBar');
  if (!bar) return;
  bar.classList.remove('show');
  if (immediate) {
    bar.style.display = 'none';
  } else {
    setTimeout(() => {
      if (!bar.classList.contains('show')) bar.style.display = 'none';
    }, 220);
  }
}

function _watchdogSpeakerPrefix(ctx) {
  if (!ctx || !ctx.speaker || !ctx.speaker.name) return '';
  if (!(activeStreams.size > 1 || currentChatType === 'group')) return '';
  const avatar = ctx.speaker.avatar ? `${ctx.speaker.avatar} ` : '';
  return `${avatar}${ctx.speaker.name} — `;
}

function _barLabel(ctx, info) {
  const elapsed = _formatElapsedForLabel(info.since);
  const prefix = _watchdogSpeakerPrefix(ctx);
  if (info.kind === 'tool') {
    if (info.state === 'stuck') return `${prefix}Tool may be stuck · ${elapsed}`;
    return `${prefix}Tool running for ${elapsed}`;
  }
  if (info.state === 'stuck') return `${prefix}Agent unresponsive · ${elapsed}`;
  if (info.mode === 'active') return `${prefix}Waiting for response… ${elapsed}`;
  return `${prefix}No response for ${elapsed}`;
}

function renderStaleBar() {
  const bar = document.getElementById('staleBar');
  const label = document.getElementById('staleLabel');
  const timer = document.getElementById('staleTimer');
  const retryBtn = document.getElementById('staleRetryBtn');
  if (!bar || !label || !timer || !retryBtn) return;
  if (!_isAnyStreamActive()) {
    hideStaleBar({immediate: true});
    return;
  }
  const selected = _pickWatchdogTarget();
  if (!selected) {
    staleState = 'working';
    hideStaleBar({immediate: false});
    _renderWatchdogPills();
    return;
  }
  const {ctx, info} = selected;
  staleState = info.state;
  bar.dataset.streamId = ctx.id || '';
  bar.dataset.profileId = (ctx.speaker && ctx.speaker.id) ? ctx.speaker.id : ((activeStreams.get(ctx.id) || {}).profile_id || '');
  bar.style.display = 'flex';
  bar.classList.add('show');
  bar.classList.remove('banner-warn', 'banner-critical', 'banner-ok');
  bar.classList.add(info.state === 'stuck' ? 'banner-critical' : 'banner-warn');
  const elapsed = _formatElapsedForLabel(info.since);
  timer.textContent = elapsed;
  const timerMarkup = '<span class="stale-timer" id="staleTimer">' + escHtml(elapsed) + '</span>';
  const labelText = _barLabel(ctx, info).replace(elapsed, '__STALE_TIMER__');
  label.innerHTML = escHtml(labelText).replace('__STALE_TIMER__', timerMarkup);
  retryBtn.style.display = info.state === 'stuck' ? '' : 'none';
  _renderWatchdogPills();
}

async function cancelStream(streamId = '') {
  if (!currentChat) return false;
  try {
    // Capture bubble refs + partial content BEFORE finalization removes ctx
    const ids = streamId ? [streamId] : Array.from(activeStreams.keys());
    const cancelledCtx = ids.map(sid => {
      const ctx = _streamCtx[sid] || null;
      return ctx ? {bubble: ctx.bubble, text: ctx.textContent || '', thinking: ctx.thinkingText || '', tools: ctx.toolCalls.length} : null;
    }).filter(Boolean);

    const resp = await fetch(`/api/chats/${currentChat}/cancel`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(streamId ? {stream_id: streamId} : {}),
    });
    if (!resp.ok && resp.status !== 204) throw new Error(`cancel failed: ${resp.status}`);
    ids.forEach(sid => _finalizeStream(sid, {trackAnswered: false}));

    // Add [Canceled] badge to each cancelled message
    cancelledCtx.forEach(({bubble, text}) => {
      if (!bubble) return;
      // If no text was generated, add a placeholder so the message is visible
      const bubbleEl = bubble.querySelector('.bubble');
      if (bubbleEl && !text.trim()) {
        bubbleEl.innerHTML = '<span style="color:var(--dim);font-style:italic">Response canceled</span>';
      }
      // Add canceled badge
      let badge = bubble.querySelector('.canceled-badge');
      if (!badge) {
        badge = document.createElement('div');
        badge.className = 'canceled-badge';
        badge.textContent = 'Canceled';
        bubble.appendChild(badge);
      }
    });

    hideStopMenu();
    if (_isAnyStreamActive()) {
      renderStaleBar();
    } else {
      hideStaleBar({immediate: true});
    }
    updateSendBtn();
    refreshDebugState('cancel');
    return true;
  } catch (err) {
    reportError('cancel stream', err);
    return false;
  }
}

async function retryLastPrompt(streamId = '', profileId = '') {
  const ok = await cancelStream(streamId || '');
  if (!ok) return;
  hideStaleBar({immediate: true});
  setTimeout(() => {
    send({allowLastPrompt: true, targetAgent: profileId || ''}).catch(err => reportError('stale retry', err));
  }, 50);
}

function _startStaleBarTick() {
  if (staleBarTick) return;
  staleBarTick = setInterval(() => {
    if (!_isAnyStreamActive()) {
      clearStreamWatchdog();
      return;
    }
    renderStaleBar();
  }, 1000);
}

function _registerWatchdogEvent(ctxOrSid, reason = '') {
  const sid = typeof ctxOrSid === 'string' ? ctxOrSid : ((ctxOrSid && ctxOrSid.id) || '');
  const ctx = sid ? (_streamCtx[sid] || null) : ctxOrSid;
  if (!ctx) return;
  const now = Date.now();
  ctx.watchdogLastEventAt = now;
  ctx.watchdogLastReason = reason || 'activity';
  ctx.watchdogMode = ['thinking', 'tool-use', 'tool-result'].includes(ctx.watchdogLastReason) ? 'active' : 'silent';
  _startStaleBarTick();
  hideStaleBar({immediate: false});
  renderStaleBar();
}

function markStreamActivity(ctxOrSid, reason = '') {
  if (!_isAnyStreamActive()) return;
  _registerWatchdogEvent(ctxOrSid, reason);
}

function _ctxHasActiveTool(ctx) {
  const bubble = ctx && ctx.bubble;
  if (!bubble) return false;
  if (bubble.querySelector('.pill--tool.streaming')) return true;
  const tools = bubble.querySelectorAll('.tool-block');
  for (const t of tools) {
    const status = t.querySelector('.tool-status');
    if (status && status.textContent === '⏳') return true;
  }
  return false;
}

function _ctxHasActiveThinking(ctx) {
  const bubble = ctx && ctx.bubble;
  return Boolean(bubble && bubble.querySelector('.thinking-block, .pill--thinking.streaming'));
}

function hasActiveTool() {
  return Object.values(_streamCtx).some(ctx => _ctxHasActiveTool(ctx));
}

async function attachToStream(socket, chatId, options = {}) {
  const reloadBeforeAttach = Boolean(options.reloadBeforeAttach);
  const reason = options.reason || 'attach';
  if (!chatId || !socket || ws !== socket || socket.readyState !== WebSocket.OPEN) return;
  if (reloadBeforeAttach) {
    await selectChat(chatId).catch(err => reportError(`${reason} selectChat`, err));
    // selectChat already sent {action:'attach'} at line ~4656 — do NOT send a
    // second one.  A double-attach causes the server to replay the buffer twice:
    // the second stream_reattached clears accumulated thinkingText and the second
    // el.innerHTML='' wipes rebuilt bubbles, making thinking pills vanish for
    // concurrent agents.
    return;
  }
  dbg('sending attach:', chatId, 'reason=', reason, 'reloadBeforeAttach=', reloadBeforeAttach);
  // WSDIAG
  console.log('WSDIAG attach chat=' + (chatId || '').slice(0,8) + ' reason=' + (reason || '_') + ' site=attachToStream');
  socket.send(JSON.stringify({action: 'attach', chat_id: chatId}));
}

function resumeConnection(trigger) {
  const streamingChatId = sessionStorage.getItem('streamingChatId');
  const resumeChat = currentChat || sessionStorage.getItem('currentChatId');
  const wasStreaming = Boolean(streamingChatId && resumeChat && streamingChatId === resumeChat);
  const resumeAlertSince = lastAlertCheck;
  dbg(`${trigger}: resume state`, {wasStreaming, streamingChatId, resumeChat});

  // Cancel any previous resume polling to prevent double-attach when both
  // visibilitychange and pageshow fire in quick succession on iOS.
  if (_resumeWaitInterval) { clearInterval(_resumeWaitInterval); _resumeWaitInterval = null; }
  if (_resumeWaitTimeout) { clearTimeout(_resumeWaitTimeout); _resumeWaitTimeout = null; }

  clearTimeout(reconnectTimer);
  stopHeartbeat();
  clearStreamWatchdog();
  if (ws) {
    try { ws.close(); } catch (e) {}
  }
  currentBubble = null;
  streaming = wasStreaming || _isAnyStreamActive();
  if (!streaming) {
    currentStreamId = '';
    currentSpeaker = null;
  }
  resumeHandledExternally = true;
  updateSendBtn();

  connect();

  if (!resumeChat) return;
  let waitDone = false;
  _resumeWaitTimeout = setTimeout(() => {
    if (waitDone) return;
    waitDone = true;
    clearInterval(_resumeWaitInterval);
    _resumeWaitInterval = null;
    _resumeWaitTimeout = null;
    dbg(`${trigger}: timed out waiting for ws open after 15000ms`);
  }, 15000);
  _resumeWaitInterval = setInterval(() => {
    if (waitDone) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      waitDone = true;
      clearInterval(_resumeWaitInterval);
      clearTimeout(_resumeWaitTimeout);
      _resumeWaitInterval = null;
      _resumeWaitTimeout = null;
      attachToStream(ws, resumeChat, {
        reloadBeforeAttach: wasStreaming,
        reason: trigger,
      }).then(async () => {
        await fetchMissedAlerts(resumeAlertSince);
        if (!wasStreaming) {
          selectChat(resumeChat).catch(err => reportError(`${trigger} reload`, err));
        }
      }).catch(err => reportError(`${trigger} attach`, err));
    }
  }, 100);
}

function setActiveChatUI() {
  document.querySelectorAll('.chat-item').forEach(item => {
    item.classList.toggle('active', item.dataset.id === currentChat);
  });
}

function setCurrentChat(id, title) {
  currentChat = id || null;
  if (currentChat) {
    sessionStorage.setItem('currentChatId', currentChat);
  } else {
    sessionStorage.removeItem('currentChatId');
  }
  const titleEl = document.getElementById('chatTitle');
  titleEl.textContent = title || 'ApexChat';
  // Make title clickable for group chats → opens group settings
  if (currentChatType === 'group') {
    titleEl.style.cursor = 'pointer';
    titleEl.onclick = () => showGroupSettings();
  } else {
    titleEl.style.cursor = '';
    titleEl.onclick = null;
  }
  setActiveChatUI();
  updateUsageBarVisibility();
  startUsagePolling();
  updateSendBtn();
  refreshDebugState('chat-selected');
  // Computer-use: sync the persistent resume banner with server pause state.
  // If this chat has GUI automation enabled AND the pause flag is set on disk,
  // surface a resume button in the header so the user always has a way out.
  if (typeof cuSyncPauseUI === 'function' && currentChat) {
    try { cuSyncPauseUI(currentChat); } catch (e) { /* non-fatal */ }
  }
}
"""

_JS_STREAM_ATTACH = """// --- WebSocket ---
let heartbeatInterval = null;
let lastPong = 0;
let resumeHandledExternally = false;  // set by visibilitychange to prevent double selectChat

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws_url = `${proto}://${location.host}/ws`;
  const connectStart = Date.now();
  dbg(' connecting via mTLS');
  const socket = new WebSocket(ws_url);
  ws = socket;
  updateConnectionIndicators();
  refreshDebugState('ws-connect');
  socket.onopen = async () => {
    if (ws !== socket) return;
    dbg(` ws opened in ${Date.now() - connectStart}ms`);
    dbg(' ws connected');
    clearTimeout(reconnectTimer);
    lastPong = Date.now();
    startHeartbeat(socket);
    updateConnectionIndicators();
    updateSendBtn();

    refreshDebugState('ws-open');
    // Track whether initApp ran inside ensureInitialized.  If it did, initApp
    // already called selectChat which sent {action:'attach'} — we must not
    // call attachToStream again or we get a second full buffer replay.
    const _initWasAlreadyDone = initDone;
    await ensureInitialized('ws-open').catch(err => reportError('init ws-open', err));
    if (resumeHandledExternally) {
      resumeHandledExternally = false;
      dbg('skipping selectChat in onopen — resume handler owns it');
    } else if (initDone) {
      const restoreChat = currentChat || sessionStorage.getItem('currentChatId');
      const streamingChatId = sessionStorage.getItem('streamingChatId');
      dbg('ws-open: restore state', {currentChat, restoreChat, streamingChatId, _initWasAlreadyDone});
      if (!restoreChat) {
        // No chat to restore
      } else if (streamingChatId && streamingChatId === restoreChat) {
        if (!currentChat) currentChat = restoreChat;
        if (!_initWasAlreadyDone) {
          // initApp just ran — selectChat inside initApp already sent attach.
          // The stream_reattached + buffer replay are already in flight.
          dbg('ws-open: initApp just ran, stream attached via initApp → selectChat — skipping attachToStream');
        } else {
          dbg('ws-open: active stream found in sessionStorage, reattaching:', currentChat);
          await attachToStream(socket, currentChat, {
            reloadBeforeAttach: true,
            reason: 'ws-open',
          });
        }
      } else {
        if (!currentChat) currentChat = restoreChat;
        selectChat(restoreChat).catch(err => reportError('reload current chat', err));
      }
    }
  };
  socket.onclose = (e) => {
    if (ws !== socket) return;
    dbg(' ws closed:', e.code, e.reason);
    stopHeartbeat();
    streaming = false;
    currentBubble = null;
    currentSpeaker = null;
    clearStreamWatchdog();
    _clearStreamingBubbleState('', null, true);
    updateConnectionIndicators();
    updateSendBtn();

    refreshDebugState('ws-close');
    clearTimeout(reconnectTimer);
    if (document.visibilityState === 'visible') {
      reconnectTimer = setTimeout(connect, 3000);
    } else {
      dbg(' ws closed while hidden; waiting for visibilitychange');
    }
  };
  socket.onerror = (e) => {
    if (ws !== socket) return;
    dbg('ERROR: ws error:', e);
    updateConnectionIndicators();
    refreshDebugState('ws-error');
  };
  socket.onmessage = (e) => {
    if (ws !== socket) return;
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'pong') { lastPong = Date.now(); return; }
      dbg(' event:', msg.type, msg);
      // WSDIAG: observability for WS streaming race bug. Text frames sampled
      // (first-per-stream) so we don't flood console on streaming responses.
      if (msg && msg.type && msg.type !== 'text') {
        var _cc = (currentChat || '').slice(0,8);
        var _sid = (msg.stream_id || '').slice(0,8);
        var _mc = (msg.chat_id || '').slice(0,8);
        console.log('WSDIAG recv type=' + msg.type + ' chat=' + _mc + ' sid=' + _sid + ' seq=' + (msg.seq == null ? '_' : msg.seq) + ' curr=' + _cc);
      } else if (msg && msg.type === 'text' && msg.stream_id) {
        window._wsdiagTextSeen = window._wsdiagTextSeen || {};
        var _tk = (msg.chat_id || '') + ':' + msg.stream_id;
        if (!window._wsdiagTextSeen[_tk]) {
          window._wsdiagTextSeen[_tk] = 1;
          console.log('WSDIAG recv type=text chat=' + (msg.chat_id || '').slice(0,8) + ' sid=' + msg.stream_id.slice(0,8) + ' seq=' + (msg.seq == null ? '_' : msg.seq) + ' curr=' + (currentChat || '').slice(0,8) + ' (first)');
        }
      }
      handleEvent(msg);
    } catch (err) {
      reportError('ws message parse', err);
    }
  };
}
"""

_JS_WEBSOCKET = """function startHeartbeat(socket) {
  stopHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) {
      try { socket.send(JSON.stringify({action: 'ping'})); } catch(e) {}
      // If no pong received in 10s, connection is zombie — kill and reconnect
      if (Date.now() - lastPong > 15000) {
        dbg('heartbeat: no pong in 15s, closing zombie socket');
        stopHeartbeat();
        socket.close();
      }
    }
  }, 5000);
}

function stopHeartbeat() {
  if (heartbeatInterval) { clearInterval(heartbeatInterval); heartbeatInterval = null; }
}

// Legacy work-group helpers are kept as no-ops for backward compatibility.
// Live reasoning now renders as a single pill; detailed steps live only in the side panel."""

_JS_TOOL_HELPERS = """function _getOrCreateWorkGroup(bubble) {
  return bubble || null;
}

function _updateWorkGroupHeader(group) {
  return group || null;
}

let _sidePanelRefreshTimer = null;
let _sidePanelAnchor = null;

function _formatDuration(ms) {
  if (!ms || !Number.isFinite(ms) || ms <= 0) return '';
  const totalSec = Math.max(1, Math.round(ms / 1000));
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min <= 0) return `${totalSec}s`;
  return sec ? `${min}m ${sec}s` : `${min}m`;
}

function _htmlToText(html) {
  const d = document.createElement('div');
  d.innerHTML = html || '';
  return d.textContent || '';
}

function _toolTypeClass(name) {
  const key = String(name || '').toLowerCase();
  if (key === 'read') return 'read';
  if (key === 'edit' || key === 'file_change') return 'edit';
  if (key === 'write') return 'write';
  if (key === 'grep' || key === 'glob' || key === 'websearch' || key === 'webfetch') return 'search';
  if (key === 'bash' || key === 'command' || key === 'agent' || key === 'skill') return 'cmd';
  return 'cmd';
}

function _formatToolInput(name, input) {
  if (input == null) return '';
  if (typeof input === 'string') {
    try {
      return JSON.stringify(JSON.parse(input), null, 2);
    } catch (e) {
      return input;
    }
  }
  try {
    return JSON.stringify(input, null, 2);
  } catch (e) {
    return String(input);
  }
}

function _normalizeToolEvents(rawEvents) {
  if (!Array.isArray(rawEvents)) return [];
  const tools = [];
  const pendingById = new Map();
  rawEvents.forEach((evt, idx) => {
    if (!evt) return;
    if (evt.type === 'tool_use') {
      const call = {
        id: evt.id || ('tool-' + idx),
        name: evt.name || 'Tool',
        input: evt.input,
        summary: evt.summary || toolSummary(evt.name, evt.input),
        status: 'running',
        startTime: evt.startTime || null,
        endTime: null,
        result: null,
      };
      tools.push(call);
      if (call.id) pendingById.set(call.id, call);
      return;
    }
    if (evt.type === 'tool_result') {
      const key = evt.tool_use_id || evt.id || '';
      let call = key ? pendingById.get(key) : null;
      if (!call) {
        call = tools.find(t => t.status === 'running') || null;
      }
      if (!call) {
        call = {
          id: key || ('tool-' + idx),
          name: evt.name || 'Tool',
          input: evt.input,
          summary: evt.summary || null,
          status: 'running',
          startTime: null,
          endTime: null,
          result: null,
        };
        tools.push(call);
        if (call.id) pendingById.set(call.id, call);
      }
      call.status = evt.is_error ? 'error' : 'completed';
      call.endTime = evt.endTime || call.endTime || null;
      call.result = evt.result ? {
        content: evt.result.content ?? '',
        is_error: Boolean(evt.result.is_error),
      } : {
        content: evt.content ?? '',
        is_error: Boolean(evt.is_error),
      };
      return;
    }
    if (!evt.name) return;
    tools.push({
      id: evt.id || ('tool-' + idx),
      name: evt.name || 'Tool',
      input: evt.input,
      summary: evt.summary || toolSummary(evt.name, evt.input),
      status: evt.status || (evt.result ? (evt.result.is_error ? 'error' : 'completed') : 'running'),
      startTime: evt.startTime || null,
      endTime: evt.endTime || null,
      result: evt.result ? {
        content: evt.result.content ?? '',
        is_error: Boolean(evt.result.is_error),
      } : (evt.content != null ? {
        content: evt.content,
        is_error: Boolean(evt.is_error),
      } : null),
    });
  });
  return tools;
}
"""

_JS_STREAM_UI = """function _ensureCtxBubble(ctx) {
  if (!ctx) return null;
  // B-4 fix: history contexts have _isHistory=true and a valid but detached
  // bubble (not yet appended to DOM).  Without this guard, isConnected is
  // false for detached elements, causing addAssistantMsg() to create a
  // phantom bubble with .streaming that is never cleaned up.
  if (!ctx.bubble || (!ctx.bubble.isConnected && !ctx._isHistory)) {
    ctx.bubble = addAssistantMsg(ctx.speaker, ctx.id || '');
    ctx.toolPill = null;
    ctx.thinkingPill = null;
  } else if (ctx.id) {
    ctx.bubble.dataset.streamId = ctx.id;
  }
  return ctx.bubble;
}

function _renderQueuedState(ctx, payload = {}) {
  if (!ctx) return;
  ctx.queued = true;
  ctx.queuedPosition = parseInt(payload.position || 0, 10) || 0;
  _ensureCtxBubble(ctx);
  const bubbleEl = ctx.bubble && ctx.bubble.querySelector('.bubble');
  if (!bubbleEl) return;
  const title = payload.queued_label || (ctx.speaker && ctx.speaker.name ? `Queued for ${ctx.speaker.name}` : 'Queued');
  const detail = ctx.queuedPosition > 1 ? `Position ${ctx.queuedPosition} in line` : 'Will run when the current turn finishes';
  bubbleEl.innerHTML = `<div class="queue-state"><div class="queue-title">${escHtml(title)}</div><div class="queue-meta">${escHtml(detail)}</div></div>`;
}

function _clearQueuedState(ctx) {
  if (!ctx || !ctx.queued) return;
  ctx.queued = false;
  ctx.queuedPosition = 0;
  const bubbleEl = ctx.bubble && ctx.bubble.querySelector('.bubble');
  if (bubbleEl && !ctx.textContent) {
    bubbleEl.innerHTML = '';
  }
}

function _syncQueuedUiFromQueueState() {
  const queueItems = Array.isArray(queuedMessages) ? queuedMessages : [];
  const queuedIds = new Set();
  queueItems.forEach(item => {
    const sid = String(item?.msg_id || item?.stream_id || '');
    if (sid) queuedIds.add(sid);
  });

  Object.keys(_streamCtx).forEach(sid => {
    const ctx = _streamCtx[sid] || null;
    if (!ctx) return;
    const queueIndex = queueItems.findIndex(item => String(item?.msg_id || item?.stream_id || '') === sid);
    if (queueIndex >= 0) {
      _renderQueuedState(ctx, {
        position: queueIndex + 1,
        queued_label: ctx.speaker && ctx.speaker.name ? `Queued for ${ctx.speaker.name}` : 'Queued',
      });
      return;
    }
    if (!ctx.queued || activeStreams.has(sid)) return;
    const hasContent = Boolean(ctx.textContent || ctx.thinkingText || (ctx.toolCalls && ctx.toolCalls.length));
    _clearQueuedState(ctx);
    if (!hasContent) {
      _removeStreamCtx(sid, {removeBubble: true});
    }
  });

  _syncLegacyStreamGlobals(currentStreamId, {clearSessionWhenIdle: false});
}

function _rebuildActiveStreamUi(ctx) {
  if (!ctx) return;
  _teardownThinking(ctx, {resetCollapsed: false});
  ctx.bubble = null;
  ctx.toolPill = null;
  ctx.thinkingPill = null;
  ctx.thinkingBlock = null;
  ctx.liveThinkingPill = null;
  _ensureCtxBubble(ctx);
  const bubbleEl = ctx.bubble && ctx.bubble.querySelector('.bubble');
  if (!bubbleEl) return;
  if (ctx.queued) {
    _renderQueuedState(ctx, {
      position: ctx.queuedPosition || 0,
      queued_label: ctx.speaker && ctx.speaker.name ? `Queued for ${ctx.speaker.name}` : 'Queued',
    });
    return;
  }
  _clearQueuedState(ctx);
  if (ctx.textContent) {
    renderMarkdown(bubbleEl, ctx.textContent);
  } else {
    bubbleEl.innerHTML = '';
  }
  if (ctx.toolCalls && ctx.toolCalls.length > 0) {
    _updateToolPillProgress(ctx);
  }
  // Show live thinking pill if: server confirmed stream is active (awaitingAck),
  // OR thinking text has already accumulated, OR no text has arrived yet
  // (meaning the agent is still in the thinking phase — stream_start from buffer
  // replay clears awaitingAck before any thinking events arrive for a second
  // concurrent agent, so !ctx.textContent catches that early-turn window).
  if (ctx.awaitingAck || ctx.thinkingText || !ctx.textContent) {
    if (!ctx.thinkingStart) ctx.thinkingStart = Date.now();
    _thinkingPill(ctx, {live: true});
  }
}

function _clearStreamingBubbleState(streamId = '', bubbleEl = null, sweepAll = false) {
  const seen = new Set();
  const clear = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    el.classList.remove('streaming');
    if (el.classList && el.classList.contains('pill--thinking')) {
      const label = el.querySelector('.pill-label');
      if (label && label.textContent && label.textContent.trim() === 'Thinking...') {
        label.textContent = 'Thinking';
      }
      el.querySelectorAll('.pill-live').forEach(node => node.remove());
      if (!el.querySelector('.pill-chevron')) {
        const chevron = document.createElement('span');
        chevron.className = 'pill-chevron';
        chevron.innerHTML = '&#8250;';
        el.appendChild(chevron);
      }
    }
  };
  clear(bubbleEl);
  if (bubbleEl && bubbleEl.querySelectorAll) {
    bubbleEl.querySelectorAll('.pill--thinking.streaming').forEach(clear);
  }
  if (streamId) {
    document.querySelectorAll('.msg.assistant.streaming, .pill--thinking.streaming').forEach(el => {
      if ((el.dataset.streamId || '') === streamId) clear(el);
    });
  }
  if (sweepAll || (!streamId && !bubbleEl)) {
    document.querySelectorAll('.msg.assistant.streaming, .pill--thinking.streaming').forEach(clear);
  }
}

function _getOrCreateToolPill(ctx) {
  if (!ctx) return null;
  _ensureCtxBubble(ctx);
  let pill = ctx.toolPill;
  if (pill && pill.isConnected) {
    pill._toolData = ctx.toolCalls;
    pill._ctx = ctx;
    return pill;
  }
  pill = document.createElement('div');
  pill.className = 'pill pill--tool streaming';
  pill.innerHTML = `<span class="spinner"></span><span class="pill-label">Tools</span><span class="pill-dim"></span><span class="pill-counts"></span><span class="pill-bar-wrap"><span class="pill-bar"></span></span><span class="pill-chevron">&#8250;</span>`;
  pill._toolData = ctx.toolCalls;
  pill._ctx = ctx;
  pill._totalTime = 0;
  pill.onclick = () => openToolPanel(pill);
  ctx.toolPill = pill;
  const bubbleEl = ctx.bubble.querySelector('.bubble');
  ctx.bubble.insertBefore(pill, bubbleEl);
  return pill;
}

function _updateToolPillProgress(ctx) {
  const pill = _getOrCreateToolPill(ctx);
  if (!pill) return;
  const total = ctx.toolCalls.length;
  const completed = ctx.toolCalls.filter(t => t.status && t.status !== 'running').length;
  ctx.completedToolCount = completed;
  pill._toolData = ctx.toolCalls;
  pill._ctx = ctx;
  const label = pill.querySelector('.pill-label');
  const dim = pill.querySelector('.pill-dim');
  const counts = pill.querySelector('.pill-counts');
  const bar = pill.querySelector('.pill-bar');
  const errors = ctx.toolCalls.filter(t => t.status === 'error').length;
  if (label) label.textContent = total === 1 ? '1 tool call' : `${total} tool calls`;
  if (dim) dim.textContent = total > 0 ? (errors > 0 ? `${errors} failed` : (completed >= total ? 'Complete' : 'Running')) : '';
  if (counts) counts.textContent = total > 0 ? `${completed}/${total}` : '';
  if (bar) {
    const pct = total > 0 ? Math.max(8, Math.round((completed / total) * 100)) : 8;
    bar.style.width = pct + '%';
  }
  // Mount the inline pause button as soon as any computer_use tool lands in
  // this pill — do not wait for the user to expand the side panel. Without
  // this, when the agent starts a new turn after a pause, the new turn's
  // pill has no inline pause control and the stale button clings to the
  // previous turn's bubble.
  if (typeof cuMountPauseButton === 'function' && currentChat) {
    const hasCU = ctx.toolCalls.some(t => t && t.name && t.name.indexOf('mcp__computer_use__') === 0);
    if (hasCU) {
      try { cuMountPauseButton(pill, currentChat); } catch (e) { /* non-fatal */ }
    }
  }
}

function _finalizeToolPill(ctx, totalTime) {
  if (!ctx || !ctx.toolCalls.length) return null;
  const pill = _getOrCreateToolPill(ctx);
  if (!pill) return null;
  const total = ctx.toolCalls.length;
  const completed = ctx.toolCalls.filter(t => t.status && t.status !== 'running').length;
  const errors = ctx.toolCalls.filter(t => t.status === 'error').length;
  pill.className = errors > 0 ? 'pill pill--tool pill--tool-error' : 'pill pill--tool';
  pill._toolData = ctx.toolCalls.map(t => ({
    ...t,
    result: t.result ? {...t.result} : null,
  }));
  pill._ctx = null;
  pill._totalTime = totalTime || 0;
  const dimText = errors > 0 ? `${errors} failed` : (_formatDuration(totalTime) || 'Complete');
  pill.innerHTML = `<span class="pill-icon">${errors > 0 ? '&#9888;' : '&#128295;'}</span><span class="pill-label">${total === 1 ? '1 tool call' : `${total} tool calls`}</span><span class="pill-dim">${dimText}</span><span class="pill-counts">${completed}/${total}</span><span class="pill-chevron">&#8250;</span>`;
  pill.onclick = () => openToolPanel(pill);
  // Re-attach the inline pause button on finalize — innerHTML rewrite above
  // doesn't touch siblings, but in case the button was never mounted (e.g.
  // the progress updater missed the window), guarantee it here for CU tools.
  if (typeof cuMountPauseButton === 'function' && currentChat) {
    const hasCU = ctx.toolCalls.some(t => t && t.name && t.name.indexOf('mcp__computer_use__') === 0);
    if (hasCU) {
      try { cuMountPauseButton(pill, currentChat); } catch (e) { /* non-fatal */ }
    }
  }
  return pill;
}

function _thinkingPill(ctx, options = {}) {
  if (!ctx) return null;
  const live = Boolean(options.live);
  const durationMs = options.durationMs != null
    ? options.durationMs
    : (ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0);
  // Allow static pill when there's an explicit non-zero duration even without
  // thinkingText — GPT-based agents (Developer/Codex) produce no thinking events
  // but still have measurable processing time that should show in the pill.
  if (!live && !ctx.bubble) return null;
  if (!live && !ctx.thinkingText && !durationMs) return null;
  _ensureCtxBubble(ctx);
  const key = live ? 'liveThinkingPill' : 'thinkingPill';
  let pill = ctx[key];
  if (!pill || !pill.isConnected) {
    pill = document.createElement('div');
    pill.className = `pill pill--thinking${live ? ' streaming' : ''}`;
    pill.onclick = () => openThinkingPanel(pill);
    ctx[key] = pill;
  } else {
    pill.className = `pill pill--thinking${live ? ' streaming' : ''}`;
  }
  if (ctx.id) pill.dataset.streamId = ctx.id;
  pill._thinkingText = ctx.thinkingText;
  pill._thinkingDuration = durationMs;
  pill.innerHTML = live
    ? `<span class="pill-icon">&#129504;</span><span class="pill-label">Thinking...</span><span class="pill-dim">${_formatDuration(durationMs) || ''}</span><span class="pill-live"></span>`
    : `<span class="pill-icon">&#129504;</span><span class="pill-label">Thinking</span><span class="pill-dim">${_formatDuration(durationMs) || ''}</span><span class="pill-chevron">&#8250;</span>`;
  const bubbleEl = ctx.bubble.querySelector('.bubble');
  // Use parentElement check instead of isConnected — tool pill may be a child
  // of a detached bubble (history rendering) where isConnected is always false.
  const beforeEl = (ctx.toolPill && ctx.toolPill.parentElement === ctx.bubble) ? ctx.toolPill : bubbleEl;
  if (pill.parentElement !== ctx.bubble || pill.nextSibling !== beforeEl) {
    ctx.bubble.insertBefore(pill, beforeEl);
  }
  if (live && !ctx.liveThinkingTimer) {
    ctx.liveThinkingTimer = setInterval(() => {
      if (!ctx.liveThinkingPill || !ctx.liveThinkingPill.isConnected) {
        _teardownThinking(ctx, {resetCollapsed: false});
        return;
      }
      _thinkingPill(ctx, {live: true});
    }, 1000);
  }
  return pill;
}

function _teardownThinking(ctx, options = {}) {
  if (!ctx) return;
  const resetCollapsed = options.resetCollapsed !== false;
  if (ctx.liveThinkingTimer) {
    clearInterval(ctx.liveThinkingTimer);
    ctx.liveThinkingTimer = null;
  }
  if (ctx.liveThinkingPill && ctx.liveThinkingPill.isConnected) {
    ctx.liveThinkingPill.remove();
  }
  ctx.liveThinkingPill = null;
  if (resetCollapsed) ctx.thinkingCollapsed = false;
}

function _finalizeThinking(ctx) {
  if (!ctx || !ctx.bubble) return;
  _teardownThinking(ctx);
  ctx.bubble.querySelectorAll('.thinking-block').forEach(el => el.remove());
  ctx.thinkingBlock = null;
  const durationMs = ctx.turnDurationMs || (ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0);
  // Create static pill for Claude agents (thinkingText) AND GPT agents (thinkingStart
  // set at stream_ack but no thinking events — durationMs is the full processing time).
  if (ctx.thinkingText || durationMs > 0) {
    _thinkingPill(ctx, { durationMs });
  }
}

function _anchoredMutateWhenScrolled(anchorEl, mutate) {
  const scroller = document.getElementById('messages');
  const shouldAnchor = Boolean(scroller && _userScrolledUp && anchorEl && anchorEl.isConnected);
  const before = shouldAnchor ? anchorEl.getBoundingClientRect().top : null;
  const afterEl = mutate() || anchorEl;
  if (shouldAnchor) {
    const target = afterEl && afterEl.isConnected ? afterEl : (anchorEl && anchorEl.isConnected ? anchorEl : null);
    if (target) {
      _programmaticScroll = true;
      scroller.scrollTop += (target.getBoundingClientRect().top - before);
      _userScrolledUp = true;
      requestAnimationFrame(() => { _programmaticScroll = false; });
    }
  }
  return afterEl;
}

function _setThinkingCollapsed(ctx, collapsed) {
  if (!ctx || !ctx.bubble) return;
  ctx.thinkingCollapsed = collapsed;
  if (ctx.thinkingBlock && ctx.thinkingBlock.isConnected) {
    ctx.thinkingBlock.remove();
  }
  ctx.thinkingBlock = null;
  _teardownThinking(ctx, {resetCollapsed: false});
  if (ctx.thinkingText) {
    if (collapsed) {
      _thinkingPill(ctx, {live: true});
    } else {
      _thinkingPill(ctx, {
        durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
      });
    }
  }
}

function _restoreThinkingFromPill(streamId) {
  const ctx = _streamCtx[streamId];
  if (!ctx) return;
  if (ctx.liveThinkingPill && ctx.liveThinkingPill.isConnected) {
    openThinkingPanel(ctx.liveThinkingPill);
    return;
  }
  _setThinkingCollapsed(ctx, false);
}

function _finalizeStreamUi(ctx, resultMsg = null) {
  if (!ctx || !ctx.bubble) return;
  if (resultMsg?.duration_ms) ctx.turnDurationMs = resultMsg.duration_ms;
  _finalizeThinking(ctx);
  _renderWatchdogPills();
  ctx.awaitingAck = false;
  ctx.bubble.querySelectorAll('.tool-group').forEach(el => el.remove());
  if (ctx.toolCalls.length > 0) {
    const totalTime = ctx.toolsStart ? (Date.now() - ctx.toolsStart) : 0;
    _finalizeToolPill(ctx, totalTime);
  }
  if (resultMsg) {
    let costEl = ctx.bubble.querySelector('.cost');
    if (!costEl) {
      costEl = document.createElement('div');
      costEl.className = 'cost';
      ctx.bubble.appendChild(costEl);
    }
    const cost = resultMsg.cost_usd ? `$${resultMsg.cost_usd.toFixed(4)}` : '';
    const tokens = resultMsg.tokens_in || resultMsg.tokens_out ? ` | ${resultMsg.tokens_in}in/${resultMsg.tokens_out}out` : '';
    costEl.textContent = cost + tokens;
  }
  _clearStreamingBubbleState(ctx.id || '', ctx.bubble);
  // B-4 hardened: direct removal of .streaming from the bubble element itself.
  // _clearStreamingBubbleState uses stream_id matching which can miss during
  // concurrent streams. This direct removal is the last line of defense.
  ctx.bubble.classList.remove('streaming');
  ctx.bubble.querySelectorAll('.bubble').forEach(b => b.parentElement?.classList?.remove('streaming'));
  // Cancel any pending debounced render and do a final authoritative pass
  // using the accumulated raw markdown (ctx.textContent), not el.textContent
  // which would be the text content of already-rendered HTML.
  clearTimeout(ctx._mdTimer);
  ctx._mdTimer = null;
  renderMarkdown(ctx.bubble.querySelector('.bubble'), ctx.textContent);
}
"""

_JS_SIDE_PANEL = """function _captureExpandedState() {
  const panel = document.getElementById('sidePanel');
  const current = new Set();
  panel.querySelectorAll('.sp-step.expanded[data-step-idx]').forEach(step => {
    current.add(step.dataset.stepIdx);
  });
  panel._prevExpanded = current;
  return current;
}

function _anchoredPanelToggle(anchorEl, mutate) {
  const scroller = document.getElementById('messages');
  const before = anchorEl && anchorEl.isConnected ? anchorEl.getBoundingClientRect().top : null;
  mutate();
  if (scroller && before != null && anchorEl && anchorEl.isConnected) {
    const after = anchorEl.getBoundingClientRect().top;
    scroller.scrollTop += (after - before);
  }
}

function closeSidePanel(anchorEl) {
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');
  const target = anchorEl || _sidePanelAnchor || null;
  _anchoredPanelToggle(target, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = null;
    panel.classList.remove('open');
    panel.style.transform = '';
    document.getElementById('spBackdrop').classList.remove('show');
    document.body.classList.remove('panel-open');
    panel._prevExpanded = new Set();
    titleEl.innerHTML = '';
    bodyEl.innerHTML = '';
    document.querySelectorAll('.pill--tool.active-pill,.pill--thinking.active-pill').forEach(el => el.classList.remove('active-pill'));
  });
}

// Mobile bottom-sheet: swipe-down to dismiss
(function() {
  const panel = document.getElementById('sidePanel');
  let _swipeStartY = 0, _swipeActive = false;
  panel.addEventListener('touchstart', function(e) {
    if (window.innerWidth >= 600 || !panel.classList.contains('open')) return;
    _swipeStartY = e.touches[0].clientY;
    _swipeActive = true;
    panel.style.transition = 'none';
  }, {passive: true});
  panel.addEventListener('touchmove', function(e) {
    if (!_swipeActive) return;
    const dy = e.touches[0].clientY - _swipeStartY;
    if (dy > 0) panel.style.transform = 'translateY(' + dy + 'px)';
  }, {passive: true});
  panel.addEventListener('touchend', function(e) {
    if (!_swipeActive) return;
    _swipeActive = false;
    const dy = e.changedTouches[0].clientY - _swipeStartY;
    panel.style.transition = '';
    // Dismiss threshold: 80px or 30% of sheet height, whichever is smaller
    if (dy > Math.min(80, panel.offsetHeight * 0.3)) {
      closeSidePanel();
    } else {
      panel.style.transform = '';
    }
  });
})();

function openToolPanel(pillEl) {
  if (!pillEl) return;
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');

  let _lastToolFingerprint = '';
  function rebuild(force) {
    const prevExpanded = _captureExpandedState();
    const prevScroll = bodyEl.scrollTop;
    const toolData = Array.isArray(pillEl._toolData) ? pillEl._toolData : [];
    const completed = toolData.filter(t => t.status && t.status !== 'running').length;
    // Skip DOM rebuild if nothing changed (prevents scroll yank on 800ms timer)
    const fingerprint = toolData.map(t => `${t.name}:${t.status}:${t.result ? 1 : 0}`).join('|');
    if (!force && fingerprint === _lastToolFingerprint && bodyEl.children.length > 0) {
      // Just update the title counter
      titleEl.innerHTML = `${toolData.length === 1 ? '1 tool call' : `${toolData.length} tool calls`}<span class="sp-dim">${pillEl._totalTime ? ` · ${_formatDuration(pillEl._totalTime)}` : ` · ${completed}/${toolData.length || 0} complete`}</span>`;
      return;
    }
    _lastToolFingerprint = fingerprint;
    titleEl.innerHTML = `${toolData.length === 1 ? '1 tool call' : `${toolData.length} tool calls`}<span class="sp-dim">${pillEl._totalTime ? ` · ${_formatDuration(pillEl._totalTime)}` : ` · ${completed}/${toolData.length || 0} complete`}</span>`;
    bodyEl.innerHTML = '';
    if (!toolData.length) {
      bodyEl.innerHTML = '<div class="sp-thinking">No tool activity yet.</div>';
      return;
    }

    toolData.forEach((tool, idx) => {
      const hasArrayContent = tool.result && Array.isArray(tool.result.content);
      const resultText = tool.result ? (typeof tool.result.content === 'string' ? tool.result.content : (hasArrayContent ? '' : JSON.stringify(tool.result.content, null, 2))) : '';
      const summaryHtml = tool.summary || toolSummary(tool.name, tool.input) || '';
      const summaryText = _htmlToText(summaryHtml) || toolLabel(tool.name);
      const status = tool.status === 'error' ? '<span style="color:#ef4444">&#10007;</span>' : (tool.status === 'completed' ? '&#10003;' : '&#9203;');
      const duration = tool.endTime && tool.startTime ? _formatDuration(tool.endTime - tool.startTime) : '';
      const step = document.createElement('div');
      step.className = 'sp-step';
      step.dataset.stepIdx = String(idx);
      if (prevExpanded.has(String(idx))) step.classList.add('expanded');
      step.innerHTML = `<div class="sps-icon ${_toolTypeClass(tool.name)}">${toolIcon(tool.name)}</div><div class="sps-info"><div class="sps-label">${escHtml(toolLabel(tool.name))}</div><div class="sps-detail">${escHtml(summaryText)}</div></div><div class="sps-meta"><div class="sps-status">${status}</div><div class="sps-time">${escHtml(duration || (tool.status === 'running' ? 'Running' : 'Done'))}</div></div><div class="sps-chevron">&#9656;</div>`;
      const detail = document.createElement('div');
      detail.className = 'sp-detail';
      let detailHtml = `<div class="spd-section"><div class="spd-label">Summary</div><div class="spd-content">${escHtml(summaryText)}</div></div>`;
      const inputText = _formatToolInput(tool.name, tool.input);
      if (inputText) {
        detailHtml += `<div class="spd-section"><div class="spd-label">Input</div><div class="spd-content"><pre>${escHtml(inputText)}</pre></div></div>`;
      }
      if (hasArrayContent) {
        // Rich content blocks (images + text) — used by computer_use screenshots.
        const isErr = tool.result && tool.result.is_error;
        const priorTool = idx > 0 ? toolData[idx - 1] : null;
        const priorClick = (priorTool && priorTool.input && typeof priorTool.input === 'object'
                            && (priorTool.name === 'mcp__computer_use__click' || priorTool.name === 'mcp__computer_use__scroll')
                            && typeof priorTool.input.x === 'number' && typeof priorTool.input.y === 'number')
          ? {x: priorTool.input.x, y: priorTool.input.y}
          : null;
        let blocksHtml = '';
        for (const block of tool.result.content) {
          if (block && block.type === 'image' && block.source && block.source.data) {
            blocksHtml += (typeof cuRenderScreenshot === 'function')
              ? cuRenderScreenshot(block, priorClick)
              : `<img class="cu-screenshot" src="data:${escHtml(block.source.media_type || 'image/png')};base64,${block.source.data}" style="max-width:100%;border-radius:6px;cursor:zoom-in;">`;
          } else if (block && block.type === 'text' && typeof block.text === 'string') {
            const txt = block.text.substring(0, 5000);
            blocksHtml += `<pre${isErr ? ' style="color:#ef4444"' : ''}>${escHtml(txt)}</pre>`;
          }
        }
        if (blocksHtml) {
          const resultNote = toolResultSummary(tool.name, '');
          detailHtml += `<div class="spd-section"><div class="spd-label">${isErr ? 'Error' : 'Result'}${resultNote ? ` · ${escHtml(resultNote)}` : ''}</div><div class="spd-content">${blocksHtml}</div></div>`;
        }
      } else if (resultText) {
        const resultNote = toolResultSummary(tool.name, resultText);
        const isErr = tool.result && tool.result.is_error;
        detailHtml += `<div class="spd-section"><div class="spd-label">${isErr ? 'Error' : 'Result'}${resultNote ? ` · ${escHtml(resultNote)}` : ''}</div><div class="spd-content"><pre${isErr ? ' style="color:#ef4444"' : ''}>${escHtml(resultText.substring(0, 5000))}</pre></div></div>`;
      }
      detail.innerHTML = detailHtml;
      // Wire up click-to-enlarge for screenshot images (delegated to avoid inline handlers).
      detail.querySelectorAll('img.cu-screenshot').forEach((imgEl) => {
        const src = imgEl.getAttribute('src') || '';
        imgEl.addEventListener('click', (ev) => {
          ev.stopPropagation();
          if (typeof openImageViewer === 'function') openImageViewer(src, 'Screenshot');
        });
      });
      // Position red-dot overlays once images have measured.
      if (typeof cuWireOverlays === 'function') cuWireOverlays(detail);
      // Mount pause button on the tool pill for any computer_use activity.
      if (typeof cuMountPauseButton === 'function' && tool.name && tool.name.indexOf('mcp__computer_use__') === 0) {
        try { cuMountPauseButton(pillEl, currentChat); } catch (e) { /* non-fatal */ }
      }
      step.onclick = () => {
        step.classList.toggle('expanded');
        const expanded = _captureExpandedState();
        if (step.classList.contains('expanded')) {
          expanded.add(step.dataset.stepIdx);
        } else {
          expanded.delete(step.dataset.stepIdx);
        }
        panel._prevExpanded = expanded;
      };
      bodyEl.appendChild(step);
      bodyEl.appendChild(detail);
    });
    requestAnimationFrame(() => { bodyEl.scrollTop = prevScroll; });
  }

  _anchoredPanelToggle(pillEl, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = pillEl;
    panel.classList.add('open');
    document.getElementById('spBackdrop').classList.add('show');
    document.body.classList.add('panel-open');
    document.querySelectorAll('.pill--tool.active-pill,.pill--thinking.active-pill').forEach(el => el.classList.remove('active-pill'));
    pillEl.classList.add('active-pill');
    rebuild(true);
    if (pillEl.classList.contains('streaming') || pillEl._ctx) {
      _sidePanelRefreshTimer = setInterval(rebuild, 800);
    }
  });
}

function openThinkingPanel(pillEl) {
  if (!pillEl) return;
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');
  if (panel.classList.contains('open') && _sidePanelAnchor === pillEl) {
    closeSidePanel(pillEl);
    return;
  }
  _anchoredPanelToggle(pillEl, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = pillEl;
    panel.classList.add('open');
    document.getElementById('spBackdrop').classList.add('show');
    document.body.classList.add('panel-open');
    document.querySelectorAll('.pill--tool.active-pill,.pill--thinking.active-pill').forEach(el => el.classList.remove('active-pill'));
    pillEl.classList.add('active-pill');
    titleEl.innerHTML = `Thinking<span class="sp-dim">${pillEl._thinkingDuration ? ` · ${_formatDuration(pillEl._thinkingDuration)}` : ''}</span>`;
    bodyEl.innerHTML = '<div class="sp-thinking"></div>';
    const thinkingEl = bodyEl.querySelector('.sp-thinking');
    thinkingEl.textContent = pillEl._thinkingText || '';
    renderMarkdown(thinkingEl);
    if (pillEl.classList.contains('streaming')) {
      function refreshThinking() {
        const t = pillEl._thinkingText || '';
        if (thinkingEl.textContent !== t) {
          thinkingEl.textContent = t;
          renderMarkdown(thinkingEl);
        }
        titleEl.innerHTML = `Thinking<span class="sp-dim">${pillEl._thinkingDuration ? ` · ${_formatDuration(pillEl._thinkingDuration)}` : ''}</span>`;
      }
      _sidePanelRefreshTimer = setInterval(refreshThinking, 800);
    }
  });
}
"""

_JS_EVENT_HANDLER = """function handleEvent(msg) {
  const el = document.getElementById('messages');
  // B-42: drop stream events that belong to a different chat
  const _B42_STREAM = new Set(['stream_start','stream_ack','stream_queued','text','thinking','tool_use','tool_result','stream_end','active_streams','queue_update']);
  // B-42b: fall back to sessionStorage so a transiently-nulled currentChat
  // (init race, tab refocus, stream teardown sweep) doesn't silently drop
  // our own in-flight stream events.
  const _activeChat = currentChat || sessionStorage.getItem('currentChatId') || '';
  if (_B42_STREAM.has(msg.type) && msg.chat_id && _activeChat && msg.chat_id !== _activeChat) {
    // WSDIAG: always surface cross-chat drops (not just dbg) — this is the
    // symptom of the streaming race bug we're hunting.
    console.log('WSDIAG drop type=' + msg.type + ' chat=' + (msg.chat_id || '').slice(0,8) + ' vs curr=' + (_activeChat || '').slice(0,8) + ' sid=' + (msg.stream_id || '').slice(0,8) + ' reason=cross-chat');
    return;
  }
  // B-42c: self-heal currentChat if it was nulled but the event matches sessionStorage
  if (_B42_STREAM.has(msg.type) && msg.chat_id && !currentChat && msg.chat_id === _activeChat) {
    currentChat = msg.chat_id;
    dbg('B42: restored currentChat', msg.chat_id);
  }
  // B-42d: diagnostic log for stream routing
  if (_B42_STREAM.has(msg.type)) {
    dbg('WS evt', msg.type, 'chat', msg.chat_id, 'curr', currentChat, 'sid', msg.stream_id || '', 'hasCtx', !!(msg.stream_id && _streamCtx[msg.stream_id]));
  }
  // Seq-based dedup: server stamps every stream event with {seq, epoch}.
  // Drop events we've already processed. Reset on epoch mismatch (server restart).
  if (typeof msg.seq === 'number' && msg.chat_id) {
    const epoch = String(msg.epoch || '');
    const prev = _lastSeenSeq[msg.chat_id];
    if (prev && prev.epoch === epoch && msg.seq <= prev.seq) {
      dbg('dedup skip', msg.chat_id, 'seq', msg.seq, 'type', msg.type);
      return;
    }
    _lastSeenSeq[msg.chat_id] = {epoch, seq: msg.seq};
  }
  switch(msg.type) {
    case 'active_streams':
      if (msg.chat_id && currentChat && msg.chat_id !== currentChat) break;
      const prevStreams = new Map(activeStreams);
      activeStreams.clear();
      (msg.streams || []).forEach(stream => {
        if (!stream || !stream.stream_id) return;
        const prev = prevStreams.get(stream.stream_id);
        stream.startedAt = prev ? prev.startedAt : Date.now();
        activeStreams.set(stream.stream_id, stream);
      });
      updateSendBtn();
      break;

    case 'stream_start': {
      const sid = msg.stream_id || ('_s' + Date.now());
      const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
      const ctx = _upsertStreamCtx(sid, speaker);
      ctx.awaitingAck = false;
      _clearQueuedState(ctx);
      _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
      markStreamActivity(ctx, 'stream-start');
      // B-34: create placeholder bubble immediately so agent is visible before first token
      _ensureCtxBubble(ctx);
      activeStreams.set(sid, {
        stream_id: sid,
        name: msg.speaker_name || '',
        avatar: msg.speaker_avatar || '',
        profile_id: msg.speaker_id || '',
        startedAt: (activeStreams.get(sid) || {}).startedAt || Date.now(),
      });
      hideStopMenu();
      updateSendBtn();

      refreshDebugState('stream-start');
      break;
    }

    case 'stream_ack': {
      const sid = msg.stream_id || ('_s' + Date.now());
      const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
      const ctx = _upsertStreamCtx(sid, speaker);
      ctx.awaitingAck = true;
      _clearQueuedState(ctx);
      if (!ctx.thinkingStart) ctx.thinkingStart = Date.now();
      _ensureCtxBubble(ctx);
      _removeThinkingIndicator();
      _thinkingPill(ctx, {live: true});
      _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
      activeStreams.set(sid, {
        stream_id: sid,
        name: msg.speaker_name || '',
        avatar: msg.speaker_avatar || '',
        profile_id: msg.speaker_id || '',
        startedAt: (activeStreams.get(sid) || {}).startedAt || Date.now(),
      });
      hideStopMenu();
      updateSendBtn();
      markStreamActivity(ctx, 'stream-ack');

      refreshDebugState('stream-ack');
      break;
    }

    case 'stream_queued': {
      _removeThinkingIndicator();
      const sid = msg.stream_id || ('_s' + Date.now());
      const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
      const ctx = _upsertStreamCtx(sid, speaker);
      ctx.awaitingAck = false;
      _renderQueuedState(ctx, msg);
      if (document.getElementById('stopMenu')?.classList.contains('show')) renderStopMenu();
      updateSendBtn();

      refreshDebugState('stream-queued');
      break;
    }

    case 'queue_update': {
      if (msg.chat_id && currentChat && msg.chat_id !== currentChat) break;
      queuedMessages = Array.isArray(msg.queued) ? msg.queued.map(item => ({...item})) : [];
      _syncQueuedUiFromQueueState();
      if (document.getElementById('stopMenu')?.classList.contains('show')) {
        renderStopMenu();
      }
      updateSendBtn();
      refreshDebugState('queue-update');
      break;
    }

    case 'text': {
      _removeThinkingIndicator();
      let ctx = _getCtx(msg);
      // B-42e: salvage — if stream_start was dropped but chat_id matches our
      // active chat, synthesize a ctx so tokens aren't silently discarded.
      if (!ctx && msg.stream_id && (!msg.chat_id || msg.chat_id === currentChat)) {
        const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
        ctx = _upsertStreamCtx(msg.stream_id, speaker);
        _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
        dbg('B42e: salvaged text ctx', msg.stream_id);
      }
      if (!ctx) break;
      _ensureCtxBubble(ctx);
      _activateStream(ctx);
      if (ctx.awaitingAck && !ctx.thinkingText) {
        // No thinking events before first text — convert live pill to static with TTFT
        // duration so it persists during streaming. _finalizeThinking will update it
        // with the correct full duration from result.duration_ms.
        _teardownThinking(ctx);
        if (ctx.thinkingStart) _thinkingPill(ctx, { durationMs: Date.now() - ctx.thinkingStart });
      } else if (ctx.thinkingText && !ctx.thinkingPill) {
        // Ensure a static thinking pill exists whenever we have thinking text —
        // handles both live→static conversion and recreation after teardown
        _teardownThinking(ctx);
        _thinkingPill(ctx, {
          durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
        });
      } else if (ctx.liveThinkingPill) {
        // Still have a live pill — convert to static
        _teardownThinking(ctx);
        _thinkingPill(ctx, {
          durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
        });
      }
      ctx.awaitingAck = false;
      if (!ctx.textContent) ctx.textContent = '';
      ctx.textContent += msg.text;
      // Debounced incremental markdown render — replaces raw textContent append.
      // Fires at most every 80ms so the user sees formatted text while streaming,
      // not a raw wall that only formats on stream completion.
      clearTimeout(ctx._mdTimer);
      ctx._mdTimer = setTimeout(() => {
        const bEl = ctx.bubble && ctx.bubble.querySelector('.bubble');
        if (bEl) renderMarkdown(bEl, ctx.textContent);
      }, 80);
      markStreamActivity(ctx, 'text');
      scrollBottom();
      break;
    }

    case 'thinking': {
      _removeThinkingIndicator();
      let ctx = _getCtx(msg);
      if (!ctx && msg.stream_id && (!msg.chat_id || msg.chat_id === currentChat)) {
        const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
        ctx = _upsertStreamCtx(msg.stream_id, speaker);
        _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
        dbg('B42e: salvaged thinking ctx', msg.stream_id);
      }
      if (!ctx) break;
      _ensureCtxBubble(ctx);
      _activateStream(ctx);
      if (!ctx.thinkingStart) ctx.thinkingStart = Date.now();
      ctx.awaitingAck = false;
      ctx.thinkingText += msg.text || '';
      if (ctx.thinkingPill && ctx.thinkingPill.isConnected) {
        ctx.thinkingPill.remove();
      }
      ctx.thinkingPill = null;
      _thinkingPill(ctx, {live: true});
      markStreamActivity(ctx, 'thinking');
      scrollBottom();
      break;
    }

    case 'tool_use': {
      _removeThinkingIndicator();
      let ctx = _getCtx(msg);
      if (!ctx && msg.stream_id && (!msg.chat_id || msg.chat_id === currentChat)) {
        const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
        ctx = _upsertStreamCtx(msg.stream_id, speaker);
        _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
        dbg('B42e: salvaged tool_use ctx', msg.stream_id);
      }
      if (!ctx) break;
      _ensureCtxBubble(ctx);
      _activateStream(ctx);
      if (ctx.awaitingAck && !ctx.thinkingText) {
        _teardownThinking(ctx);
        if (ctx.thinkingStart) _thinkingPill(ctx, { durationMs: Date.now() - ctx.thinkingStart });
      } else if (ctx.thinkingText && !ctx.thinkingPill) {
        // Ensure a static thinking pill exists whenever we have thinking text
        _teardownThinking(ctx);
        _thinkingPill(ctx, {
          durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
        });
      } else if (ctx.liveThinkingPill) {
        // Still have a live pill — convert to static
        _teardownThinking(ctx);
        _thinkingPill(ctx, {
          durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
        });
      }
      ctx.awaitingAck = false;
      if (!ctx.toolsStart) ctx.toolsStart = Date.now();
      ctx.toolCalls.push({
        id: msg.id || ('tool-' + Date.now()),
        name: msg.name || 'Tool',
        input: msg.input,
        summary: toolSummary(msg.name, msg.input),
        status: 'running',
        startTime: Date.now(),
        endTime: null,
        result: null,
      });
      _updateToolPillProgress(ctx);
      markStreamActivity(ctx, 'tool-use');
      scrollBottom();
      break;
    }

    case 'tool_result': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      _activateStream(ctx);
      const toolId = msg.tool_use_id || msg.id || '';
      let toolCall = ctx.toolCalls.find(t => t.id === toolId) || null;
      if (!toolCall) {
        toolCall = ctx.toolCalls.find(t => t.status === 'running') || null;
      }
      if (toolCall) {
        toolCall.status = msg.is_error ? 'error' : 'completed';
        toolCall.endTime = Date.now();
        toolCall.result = {
          content: msg.content,
          is_error: Boolean(msg.is_error),
        };
      }
      _updateToolPillProgress(ctx);
      markStreamActivity(ctx, 'tool-result');
      scrollBottom();
      break;
    }

    case 'result': {
      _removeThinkingIndicator();
      const sid = _resolveStreamId(msg, {allowFocusedFallback: true});
      const ctx = _getCtx(msg, {allowFocusedFallback: true});
      // Backfill thinking text from result payload if real-time events were
      // missed or empty (e.g. single-turn codex responses where pending_agent_message
      // was never flushed as thinking, or non-streaming _call_openai_responses path).
      if (ctx && msg.thinking && !ctx.thinkingText) {
        ctx.thinkingText = msg.thinking;
        if (!ctx.thinkingStart) ctx.thinkingStart = Date.now();
      }
      // B-25: Finalize the stream state immediately on 'result' so the Stop
      // button and busy flag are cleared as soon as the agent's response is
      // complete.  Without this, the Stop button stayed active and a follow-up
      // sent while the server was still doing post-processing (save / compact /
      // agent routing) triggered a false "agent is busy" error.  The subsequent
      // stream_end is still handled and is idempotent once the context is gone.
      _finalizeStream(sid, {resultMsg: ctx ? msg : null});
      hideStaleBar({immediate: false});
      hideStopMenu();
      updateSendBtn();
      // Update context bar from inline data or fallback to API
      if (msg.context_tokens_in != null && msg.context_window) {
        updateContextBar(msg.context_tokens_in, msg.context_window);
      } else {
        fetchContext(currentChat);
      }
      startUsagePolling();
      refreshDebugState('result');
      break;
    }

    case 'stream_end': {
      _removeThinkingIndicator();
      // B-19v3: _resolveStreamId already handles unnamed stream_end (line 983-984
      // falls through to "only 1 active → use it").  The external heuristic below
      // was a duplicate that ONLY activated when the B-19v2 guard deliberately
      // returned '' for a named-but-finalized stream — overriding the protection
      // and grabbing a sibling stream to murder.  Removed.
      const sid = _resolveStreamId(msg, {allowFocusedFallback: true});
      if (sid) {
        _finalizeStream(sid);
      } else {
        _syncLegacyStreamGlobals('', {clearSessionWhenIdle: false});
        // B-19v3: only sweep all streaming CSS when no siblings are active —
        // same guard as _finalizeStream line 1063
        if (!_isAnyStreamActive()) _clearStreamingBubbleState('', null, true);
      }
      hideStaleBar({immediate: false});
      hideStopMenu();
      updateSendBtn();

      refreshDebugState('stream-end');
      break;
    }

    case 'stream_reattached': {
      // Server confirmed we re-attached to an active stream after replaying
      // the buffered events that were missed while the socket was down.
      dbg('stream re-attached for chat:', msg.chat_id);
      const sid = msg.stream_id || ('_s' + Date.now());
      const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
      const ctx = _upsertStreamCtx(sid, speaker);
      // B-24: Reset accumulated text before buffer replay so replayed text
      // chunks are not appended on top of already-rendered content, which
      // would produce duplicated sentences/paragraphs in the live bubble.
      clearTimeout(ctx._mdTimer);
      ctx._mdTimer = null;
      ctx.textContent = '';
      const _reattachBubble = ctx.bubble && ctx.bubble.querySelector && ctx.bubble.querySelector('.bubble');
      if (_reattachBubble) _reattachBubble.innerHTML = '';
      _clearQueuedState(ctx);
      // Set awaitingAck=true to mirror stream_ack state — stream_ack is not
      // buffered so it never replays on reconnect.  Without this, agents that
      // haven't emitted thinking blocks yet have no visible thinking pill after
      // a page reload.  The buffer replay will clear it via stream_start/text.
      ctx.awaitingAck = true;
      if (msg.elapsed_ms) {
        const _correctedStart = Date.now() - msg.elapsed_ms;
        ctx.thinkingStart = _correctedStart;
        // Pre-seed activeStreams so the replayed stream_start at line ~2494
        // picks up the corrected startedAt instead of falling back to Date.now().
        const _prevEntry = activeStreams.get(sid) || {};
        activeStreams.set(sid, {
          ..._prevEntry,
          stream_id: sid,
          name: msg.speaker_name || _prevEntry.name || '',
          avatar: msg.speaker_avatar || _prevEntry.avatar || '',
          profile_id: msg.speaker_id || _prevEntry.profile_id || '',
          startedAt: _correctedStart,
        });
      }
      // Create the thinking pill immediately — don't wait for buffer replay.
      // stream_ack is not buffered so it never replays on reconnect.
      // stream_start (which is buffered) clears awaitingAck, so for models
      // without extended thinking there are no thinking events to re-trigger
      // the pill. Showing it here covers all cases.
      _ensureCtxBubble(ctx);
      _thinkingPill(ctx, {live: true});
      _activateStream(ctx, {chatId: msg.chat_id || currentChat || ''});
      markStreamActivity(ctx, 'stream-reattached');
      updateSendBtn();

      refreshDebugState('stream-reattached');
      break;
    }

    case 'attach_ok':
      _removeThinkingIndicator();
      // Server confirmed no active stream — safe to reload from DB.
      // This fires when the client thought a stream might be running
      // (sessionStorage had streamingChatId) but it already finished.
      dbg('attach ok, no active stream for chat:', msg.chat_id);
      _resetAllStreamState();
      hideStaleBar({immediate: true});
      hideStopMenu();
      updateSendBtn();

      // Skip reload if we already have messages loaded for this chat
      // (prevents request storm on reconnect/refresh)
      if (msg.chat_id && msg.chat_id === currentChat && !document.getElementById('messages').hasChildNodes()) {
        selectChat(msg.chat_id).catch(() => {});
      }
      refreshDebugState('attach-ok');
      break;

    case 'stream_complete_reload':
      _removeThinkingIndicator();
      // Stream finished while we were disconnected. Reload from DB.
      dbg('stream completed while disconnected, reloading chat:', msg.chat_id);
      hideStaleBar({immediate: true});
      hideStopMenu();
      updateSendBtn();

      // B-19: only reload if no other streams are still active — reloading
      // during an active stream kills its context and makes it invisible
      if (msg.chat_id && msg.chat_id === currentChat && !_isAnyStreamActive()) {
        _resetAllStreamState();
        // Reconnect-triggered reloads often arrive immediately after the same
        // chat was selected/attached, so bypass the normal 500ms debounce
        // without triggering another attach/reload cycle.
        selectChat(msg.chat_id, undefined, undefined, undefined, {forceReload: true, skipAttach: true}).catch(() => {});
      }
      refreshDebugState('stream-complete-reload');
      break;

    case 'user_message_added':
      // Another client sent a message on this chat — show it
      if (msg.chat_id === currentChat && (msg.content || normalizeMessageAttachments(msg.attachments).length)) {
        addUserMsg(msg.content || '', msg.attachments || []);
      }
      break;

    case 'chat_updated':
      if (currentChat === msg.chat_id) {
        if (msg.title) document.getElementById('chatTitle').textContent = msg.title;
        // Update profile state if broadcast includes it
        if ('profile_id' in msg) {
          _currentChatProfileId = msg.profile_id || '';
          updateTopbarProfile(msg.profile_name || '', msg.profile_avatar || '');
          updateChatModelSelect();
        }
      }
      loadChats().catch(err => reportError('chat_updated loadChats', err));
      refreshDebugState('chat-updated');
      break;

    case 'chat_deleted':
      loadChats().then(chats => {
        if (currentChat === msg.chat_id && chats.length > 0) {
          selectChat(chats[0].id, chats[0].title).catch(() => {});
        }
      }).catch(err => reportError('chat_deleted loadChats', err));
      break;

    case 'alert':
      showAlertToast(msg);
      break;

    case 'alert_acked':
      hideAlertToast();
      const acked = alertsCache.find(a => a.id === msg.alert_id);
      if (acked) { acked.acked = true; renderAlertsPanel(); }
      break;

    case 'system':
      if (msg.subtype === 'compaction') {
        addSystemMsg('⚡ ' + (msg.message || 'Session compacted.'), {});
      }
      break;

    case 'system_message':
      if (msg.chat_id && currentChat && msg.chat_id !== currentChat) break;
      addSystemMsg(msg.text || msg.message || 'System message');
      break;

    case 'error': {
      _removeThinkingIndicator();
      const errorText = msg.message || 'Unknown error';
      const sid = msg.stream_id ? _resolveStreamId(msg, {allowFocusedFallback: false}) : '';
      if (sid) {
        const ctx = _streamCtx[sid];
        const emptyCtx = ctx && !ctx.textContent && !ctx.thinkingText && (!ctx.toolCalls || ctx.toolCalls.length === 0);
        if (emptyCtx) {
          _removeStreamCtx(sid, {removeBubble: true});
          _syncLegacyStreamGlobals('', {clearSessionWhenIdle: true});
        } else if (ctx) {
          _finalizeStream(sid);
        }
      }
      addSystemMsg(errorText, {
        retryable: Boolean(msg.retryable),
        targetAgent: msg.target_agent || '',
      });
      const isBusyError = _isBusyErrorMessage(errorText);
      if (!isBusyError) {
        if (!sid) {
          _resetAllStreamState();
          hideStaleBar({immediate: true});
          hideStopMenu();
        } else if (_isAnyStreamActive()) {
          renderStaleBar();
        } else {
          hideStaleBar({immediate: true});
          hideStopMenu();
        }
      }
      updateSendBtn();

      refreshDebugState(isBusyError ? 'event-error-busy' : 'event-error');
      break;
    }
  }
}
"""

_JS_UI_HELPERS = """// --- UI helpers ---
function addAssistantMsg(speaker = currentSpeaker, streamId = '') {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant streaming';
  if (streamId) div.dataset.streamId = streamId;
  let inner = '';
  if (speaker && speaker.name) {
    inner += `<div class="speaker-header" data-profile-id="${escHtml(speaker.id || '')}"><span class="speaker-avatar">${escHtml(speaker.avatar || '')}</span> <span class="speaker-name">${escHtml(speaker.name)}</span></div>`;
  }
  inner += '<div class="bubble"></div>';
  div.innerHTML = inner;
  el.appendChild(div);
  scrollBottom();
  return div;
}

function formatAttachmentSize(size) {
  const bytes = Number(size || 0);
  if (!bytes) return '';
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1).replace(/\\.0$/, '') + 'MB';
  if (bytes >= 1024) return Math.round(bytes / 1024) + 'KB';
  return bytes + 'B';
}

function normalizeMessageAttachments(raw) {
  if (Array.isArray(raw)) return raw.filter(att => att && typeof att === 'object');
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter(att => att && typeof att === 'object') : [];
    } catch (_) {
      return [];
    }
  }
  return [];
}

function buildMessageFilePill(att) {
  const link = document.createElement('a');
  link.className = 'msg-file-pill';
  link.href = att.url || '#';
  link.target = '_blank';
  link.rel = 'noopener';
  if (!att.url) link.onclick = (e) => e.preventDefault();

  const icon = document.createElement('span');
  icon.textContent = '📎';
  link.appendChild(icon);

  const name = document.createElement('span');
  name.textContent = att.name || 'attachment';
  link.appendChild(name);

  const sizeLabel = formatAttachmentSize(att.size);
  if (sizeLabel) {
    const size = document.createElement('span');
    size.className = 'msg-file-size';
    size.textContent = '· ' + sizeLabel;
    link.appendChild(size);
  }
  return link;
}

function openImageViewer(imageUrl, altText = 'Attachment') {
  if (!imageUrl) return;
  document.querySelector('.image-viewer-overlay')?.remove();
  const previousOverflow = document.body.style.overflow;
  const overlay = document.createElement('div');
  overlay.className = 'image-viewer-overlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');

  const content = document.createElement('div');
  content.className = 'image-viewer-content';

  const closeBtn = document.createElement('button');
  closeBtn.className = 'image-viewer-close';
  closeBtn.type = 'button';
  closeBtn.setAttribute('aria-label', 'Close image');
  closeBtn.innerHTML = '&times;';

  const img = document.createElement('img');
  img.className = 'image-viewer-image';
  img.src = imageUrl;
  img.alt = altText;

  const closeViewer = () => {
    document.body.style.overflow = previousOverflow;
    document.removeEventListener('keydown', onKeyDown);
    overlay.remove();
  };
  const onKeyDown = (e) => {
    if (e.key === 'Escape') closeViewer();
  };

  img.onclick = (e) => {
    e.stopPropagation();
    closeViewer();
  };
  closeBtn.onclick = (e) => {
    e.stopPropagation();
    closeViewer();
  };
  overlay.onclick = (e) => {
    if (e.target === overlay) closeViewer();
  };

  content.appendChild(closeBtn);
  content.appendChild(img);
  overlay.appendChild(content);
  document.body.style.overflow = 'hidden';
  document.body.appendChild(overlay);
  document.addEventListener('keydown', onKeyDown);
}

function buildMessageAttachment(att) {
  const item = document.createElement('div');
  const imageUrl = att.url || ((att.base64 && att.mimeType) ? `data:${att.mimeType};base64,${att.base64}` : '');
  if (att.type === 'image' && imageUrl) {
    item.className = 'msg-attachment';
    const img = document.createElement('img');
    img.src = imageUrl;
    img.alt = att.name || 'Attachment';
    img.loading = 'lazy';
    img.onclick = () => openImageViewer(imageUrl, att.name || 'Attachment');
    img.onload = () => item.classList.add('is-loaded');
    img.onerror = () => {
      item.className = 'msg-attachment is-file';
      item.innerHTML = '';
      item.appendChild(buildMessageFilePill(att));
    };
    item.appendChild(img);
    if (img.complete) item.classList.add('is-loaded');
    return item;
  }

  item.className = 'msg-attachment is-file';
  item.appendChild(buildMessageFilePill(att));
  return item;
}

function buildMessageAttachments(raw) {
  const attachments = normalizeMessageAttachments(raw);
  if (!attachments.length) return null;
  const wrap = document.createElement('div');
  wrap.className = 'msg-attachments';
  attachments.forEach(att => wrap.appendChild(buildMessageAttachment(att)));
  return wrap;
}

function addUserMsg(text, attachments = []) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg user';
  if (text) {
    const msgText = document.createElement('div');
    msgText.className = 'msg-text';
    msgText.textContent = text;
    div.appendChild(msgText);
  }
  const attachmentWrap = buildMessageAttachments(attachments);
  if (attachmentWrap) div.appendChild(attachmentWrap);
  if (!text && !attachmentWrap) div.textContent = '(attachment)';
  el.appendChild(div);
  scrollBottomForce();
}

function _showThinkingIndicator() {
  _removeThinkingIndicator();
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.id = '_thinkingIndicator';
  div.innerHTML = '<div class="thinking-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div><span class="ti-label">Thinking\u2026</span></div>';
  el.appendChild(div);
  scrollBottomForce();
}
function _removeThinkingIndicator() {
  const existing = document.getElementById('_thinkingIndicator');
  if (existing) existing.remove();
}

function addSystemMsg(text, options = {}) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.style.color = 'var(--red)';
  // Use the normal markdown renderer so system-authored literal @mentions
  // survive display the same way assistant text does.
  const content = document.createElement('div');
  renderMarkdown(content, text || '');
  bubble.appendChild(content);
  if (options.retryable) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'system-retry-btn';
    btn.textContent = 'Retry';
    btn.onclick = () => {
      send({
        allowLastPrompt: true,
        targetAgent: options.targetAgent || '',
      }).catch(err => reportError('system retry', err));
    };
    bubble.appendChild(btn);
  }
  div.appendChild(bubble);
  el.appendChild(div);
  scrollBottom();
}

function _isBusyErrorMessage(text = '') {
  return /still responding|already processing a message/i.test(String(text || ''));
}

/* --- Smart scroll: only auto-scroll if user is near bottom --- */"""

_JS_SCROLL = """let _userScrolledUp = false;
const _SCROLL_THRESHOLD = 150; // px from bottom to count as "near bottom"

// ---- History pagination (infinite scroll) ----
let _historyHasMore = false;
let _historyOldestId = null;
let _historyLoading = false;
const _HISTORY_PAGE_SIZE = 100;
const _SCROLL_TOP_THRESHOLD = 200; // px from top to trigger load-more

function _isNearBottom() {
  const el = document.getElementById('messages');
  if (!el) return true;
  return (el.scrollHeight - el.scrollTop - el.clientHeight) < _SCROLL_THRESHOLD;
}

function scrollBottom() {
  // Smart version: only scroll if user hasn't scrolled up
  if (_userScrolledUp) {
    _showNewContentPill();
    return;
  }
  scrollBottomForce();
}

function scrollBottomForce() {
  const el = document.getElementById('messages');
  if (!el) return;
  el.scrollTop = el.scrollHeight;
  _userScrolledUp = false;
  _hideNewContentPill();
}

function _showNewContentPill() {
  let pill = document.getElementById('newContentPill');
  if (pill) { pill.style.display = 'flex'; return; }
  pill = document.createElement('div');
  pill.id = 'newContentPill';
  pill.textContent = '\u2193 New';
  pill.style.cssText = 'position:absolute;bottom:80px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;z-index:200;display:flex;align-items:center;gap:4px;box-shadow:0 2px 8px rgba(0,0,0,0.3);transition:opacity 0.2s';
  pill.onclick = () => { scrollBottomForce(); };
  const container = document.getElementById('messages').parentElement;
  container.style.position = 'relative';
  container.appendChild(pill);
}

function _hideNewContentPill() {
  const pill = document.getElementById('newContentPill');
  if (pill) pill.style.display = 'none';
}

// Toggle collapsible block with scroll-position anchoring
let _programmaticScroll = false;
function _toggleCollapsible(headerEl) {
  const block = headerEl.parentElement;
  const scroller = document.getElementById('messages');
  const wasScrolledUp = _userScrolledUp;
  const beforeTop = block.getBoundingClientRect().top;
  block.classList.toggle('open');
  if (scroller && wasScrolledUp) {
    _programmaticScroll = true;
    const afterTop = block.getBoundingClientRect().top;
    scroller.scrollTop += (afterTop - beforeTop);
    _userScrolledUp = true;
    requestAnimationFrame(() => { _programmaticScroll = false; });
  }
}
function _toggleThinkingBlock(headerEl) {
  const block = headerEl ? headerEl.parentElement : null;
  const sid = block && block.dataset ? block.dataset.streamId : '';
  const ctx = sid ? _streamCtx[sid] : null;
  if (ctx) {
    _setThinkingCollapsed(ctx, true);
    return;
  }
  _toggleCollapsible(headerEl);
}

// ---- Render a single history message DOM node (user or assistant) ----
function _renderHistoryMsg(m) {
  if (m.role === 'user') {
    const div = document.createElement('div');
    div.className = 'msg user';
    if (m.content) {
      const msgText = document.createElement('div');
      msgText.className = 'msg-text';
      msgText.textContent = m.content;
      div.appendChild(msgText);
    }
    const attachmentWrap = buildMessageAttachments(m.attachments || []);
    if (attachmentWrap) div.appendChild(attachmentWrap);
    if (!m.content && !attachmentWrap) div.textContent = '(attachment)';
    return div;
  }
  // Assistant message
  const div = document.createElement('div');
  div.className = 'msg assistant';
  let inner = '';
  if (m.speaker_name) {
    inner += `<div class="speaker-header" data-profile-id="${escHtml(m.speaker_id || '')}"><span class="speaker-avatar">${escHtml(m.speaker_avatar || '')}</span> <span class="speaker-name">${escHtml(m.speaker_name)}</span></div>`;
  }
  inner += `<div class="bubble"></div>`;
  if (m.cost_usd || m.tokens_in || m.tokens_out) {
    const cost = m.cost_usd ? `$${m.cost_usd.toFixed(4)}` : '';
    const tokens = (m.tokens_in || m.tokens_out) ? `${m.tokens_in}in/${m.tokens_out}out` : '';
    inner += `<div class="cost">${[cost, tokens].filter(Boolean).join(' | ')}</div>`;
  }
  div.innerHTML = inner;
  const bubble = div.querySelector('.bubble');
  bubble.textContent = m.content;
  const historyCtx = _newStreamCtx('', m.speaker_name ? {name: m.speaker_name, avatar: m.speaker_avatar || '', id: m.speaker_id || ''} : null);
  historyCtx.bubble = div;
  historyCtx._isHistory = true;  // prevent _ensureCtxBubble from creating phantom bubbles
  historyCtx.textContent = m.content || '';
  try {
    historyCtx.toolCalls = _normalizeToolEvents(JSON.parse(m.tool_events || '[]'));
  } catch (e) {
    historyCtx.toolCalls = [];
  }
  if (historyCtx.toolCalls.length > 0) {
    const totalTime = historyCtx.toolCalls.reduce((sum, tool) => {
      const duration = tool.startTime && tool.endTime ? (tool.endTime - tool.startTime) : 0;
      return sum + Math.max(0, duration);
    }, 0);
    _finalizeToolPill(historyCtx, totalTime);
  }
  if ((m.thinking && m.thinking.trim()) || m.duration_ms > 0) {
    if (m.thinking && m.thinking.trim()) historyCtx.thinkingText = m.thinking;
    _thinkingPill(historyCtx, {durationMs: m.duration_ms || 0});
  }
  if (m.canceled) {
    let badge = document.createElement('div');
    badge.className = 'canceled-badge';
    badge.textContent = 'Canceled';
    div.appendChild(badge);
  }
  div.querySelectorAll('.bubble').forEach(el => renderMarkdown(el));
  return div;
}

// ---- Load older messages when scrolling to top ----
async function _loadOlderMessages() {
  if (_historyLoading || !_historyHasMore || !currentChat) return;
  _historyLoading = true;
  const el = document.getElementById('messages');
  if (!el) { _historyLoading = false; return; }

  // Show loading spinner at top
  let spinner = document.getElementById('_historySpinner');
  if (!spinner) {
    spinner = document.createElement('div');
    spinner.id = '_historySpinner';
    spinner.style.cssText = 'text-align:center;padding:12px;color:var(--dim);font-size:13px';
    spinner.innerHTML = '<span class="dot-spinner" style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--dim);animation:dotPulse 1.4s ease-in-out infinite;margin:0 2px"></span> Loading older messages\u2026';
  }
  el.prepend(spinner);

  try {
    const url = `/api/chats/${currentChat}/messages?limit=${_HISTORY_PAGE_SIZE}&before_id=${encodeURIComponent(_historyOldestId)}`;
    const r = await fetch(url, {credentials: 'same-origin'});
    if (!r.ok) { dbg('load-more failed:', r.status); return; }
    const data = await r.json();
    const msgs = Array.isArray(data) ? data : (data.messages || []);
    _historyHasMore = data.has_more === true;

    if (msgs.length > 0) {
      _historyOldestId = msgs[0].id;

      // Preserve scroll position: anchor to current first real message
      const scrollAnchor = el.children[1]; // [0] is spinner
      const anchorTop = scrollAnchor ? scrollAnchor.getBoundingClientRect().top : 0;

      // Build fragment of older messages
      const frag = document.createDocumentFragment();
      msgs.forEach(m => frag.appendChild(_renderHistoryMsg(m)));

      // Insert after spinner (which we'll remove)
      spinner.remove();
      el.prepend(frag);

      // Restore scroll position so the view doesn't jump
      if (scrollAnchor && scrollAnchor.isConnected) {
        _programmaticScroll = true;
        const newAnchorTop = scrollAnchor.getBoundingClientRect().top;
        el.scrollTop += (newAnchorTop - anchorTop);
        requestAnimationFrame(() => { _programmaticScroll = false; });
      }
    } else {
      spinner.remove();
    }

    // Show "beginning of conversation" marker when no more history
    if (!_historyHasMore) {
      let marker = document.getElementById('_historyEnd');
      if (!marker) {
        marker = document.createElement('div');
        marker.id = '_historyEnd';
        marker.style.cssText = 'text-align:center;padding:16px 12px 8px;color:var(--dim);font-size:12px;opacity:0.6';
        marker.textContent = '\u2500\u2500 Beginning of conversation \u2500\u2500';
        el.prepend(marker);
      }
    }
  } catch (e) {
    dbg('load-more error:', e);
    if (spinner.isConnected) spinner.remove();
  } finally {
    _historyLoading = false;
  }
}

// Attach scroll listener once DOM is ready
(function _initScrollWatch() {
  function attach() {
    const el = document.getElementById('messages');
    if (!el) { setTimeout(attach, 100); return; }
    el.addEventListener('scroll', () => {
      if (_programmaticScroll) return;
      _userScrolledUp = !_isNearBottom();
      if (!_userScrolledUp) _hideNewContentPill();
      // Infinite scroll: load older messages when near top
      if (_historyHasMore && !_historyLoading && el.scrollTop < _SCROLL_TOP_THRESHOLD) {
        _loadOlderMessages();
      }
    }, {passive: true});
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
})();
"""

_JS_ALERTS = """// --- Alerts channel view (renders in main messages area) ---
function renderAlertsList(alerts) {
  channelAlertsData = alerts;
  const el = document.getElementById('messages');
  el.innerHTML = '';
  if (alerts.length === 0) {
    el.innerHTML = '<div style="padding:40px;text-align:center;color:#666">No alerts</div>';
    return;
  }
  // Event delegation for channel alert action buttons — set up once per render
  if (!el._channelAlertDelegationAttached) {
    el._channelAlertDelegationAttached = true;
    el.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-alert-action]');
      if (btn) {
        e.stopPropagation();
        channelAlertAction(btn.dataset.alertAction, btn.dataset.alertId, btn);
        return;
      }
      const msg = e.target.closest('.msg[data-alert-id]');
      if (msg) showAlertDetail(msg.dataset.alertId);
    });
  }
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  alerts.forEach(a => {
    const sev = a.severity || 'info';
    const icon = sevIcons[sev] || '\u2139\ufe0f';
    const color = sevColors[sev] || '#0891b2';
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.dataset.alertId = a.id;
    div.style.opacity = a.acked ? '0.4' : '1';
    div.style.cursor = 'pointer';
    let actions = '';
    if (!a.acked) {
      if (a.source === 'guardrail') {
        actions += `<button data-alert-action="allow" data-alert-id="${escAttr(a.id)}" style="background:#16a34a;color:#fff;border:none;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;margin-right:4px">Allow</button>`;
      }
      actions += `<button data-alert-action="ack" data-alert-id="${escAttr(a.id)}" style="background:${color};color:#fff;border:none;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Ack</button>`;
    } else {
      actions = '<span style="color:#4ade80;font-size:11px">\u2713 Acked</span>';
    }
    const ago = timeAgo(a.created_at);
    div.innerHTML = `<div class="bubble" style="border-left:3px solid ${color};padding:10px 14px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span style="font-size:16px">${icon}</span>
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;color:${color}">${escHtml(a.source)}</span>
        <span style="font-size:10px;color:#666;margin-left:auto">${ago}</span>
      </div>
      <div style="font-weight:600;margin-bottom:4px">${escHtml(a.title)}</div>
      ${a.body ? `<div style="font-size:12px;color:#aaa;white-space:pre-wrap;overflow-wrap:break-word;word-break:break-word;margin-bottom:6px">${escHtml(a.body)}</div>` : ''}
      <div>${actions}</div>
    </div>`;
    el.appendChild(div);
  });
}
let channelAlertsData = [];
function channelAlertAction(action, alertId, btn) {
  postAlertAction(action, alertId).then(() => {
    markAlertAcknowledged(alertId);
    if (btn) {
      const bubble = btn.closest('.msg');
      if (bubble) bubble.style.opacity = '0.4';
      btn.parentElement.innerHTML = alertActionStatusLabel(action);
    }
  }).catch(err => {
    reportError('channelAlertAction', err);
    flashAlertActionError(btn);
  });
}
function humanizeAlertStatus(status, alert) {
  const normalized = String(status || '').trim().toLowerCase();
  if (!normalized) return '';
  if (normalized === 'ack' || normalized === 'acked' || normalized === 'acknowledged') {
    return alert?.source === 'guardrail' ? 'Approved' : 'Acknowledged';
  }
  if (normalized === 'allow' || normalized === 'allowed' || normalized === 'approved') {
    return alert?.source === 'guardrail' ? 'Approved' : 'Allowed';
  }
  if (normalized === 'allowed_via_whitelist' || normalized === 'whitelisted') {
    return 'Whitelisted';
  }
  if (normalized === 'blocked') return 'Blocked';
  if (normalized === 'error') return 'Error';
  if (normalized === 'pending') return 'Pending';
  return normalized
    .replace(/_/g, ' ')
    .replace(/\\b\\w/g, (ch) => ch.toUpperCase());
}
function getAlertStatusText(alert) {
  const explicitStatus = alert?.status || alert?.metadata?.status || '';
  if (explicitStatus) return humanizeAlertStatus(explicitStatus, alert);
  if (alert?.acked) {
    return alert?.source === 'guardrail' ? 'Approved' : 'Acknowledged';
  }
  return '';
}
function formatAlertMetadataValue(key, value, alert) {
  if (String(key || '').trim().toLowerCase() === 'status') {
    return humanizeAlertStatus(value, alert);
  }
  return String(value ?? '');
}
const ALERT_BODY_ALLOWED_TAGS = new Set(['b', 'strong', 'em', 'i', 'code', 'br', 'ul', 'ol', 'li', 'a']);
function sanitizeAlertBodyNode(node) {
  Array.from(node.childNodes).forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) return;
    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.remove();
      return;
    }
    const tag = child.tagName.toLowerCase();
    if (!ALERT_BODY_ALLOWED_TAGS.has(tag)) {
      if (tag === 'script' || tag === 'style') {
        child.remove();
        return;
      }
      const fragment = document.createDocumentFragment();
      while (child.firstChild) {
        fragment.appendChild(child.firstChild);
      }
      child.replaceWith(fragment);
      sanitizeAlertBodyNode(node);
      return;
    }
    if (tag === 'a') {
      const href = child.getAttribute('href');
      Array.from(child.attributes).forEach((attr) => child.removeAttribute(attr.name));
      if (href && /^https?:\/\//.test(href)) {
        child.setAttribute('href', href);
        child.setAttribute('target', '_blank');
        child.setAttribute('rel', 'noopener noreferrer');
      }
    } else {
      Array.from(child.attributes).forEach((attr) => child.removeAttribute(attr.name));
    }
    sanitizeAlertBodyNode(child);
  });
}
function linkifyTextNodes(node) {
  const urlRe = /https?:\/\/[^\s<>"')\]]+/g;
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  textNodes.forEach((tn) => {
    if (tn.parentNode && tn.parentNode.tagName && tn.parentNode.tagName.toLowerCase() === 'a') return;
    const val = tn.nodeValue;
    if (!urlRe.test(val)) return;
    urlRe.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    let m;
    while ((m = urlRe.exec(val)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(val.slice(last, m.index)));
      const a = document.createElement('a');
      a.href = m[0];
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = m[0];
      frag.appendChild(a);
      last = m.index + m[0].length;
    }
    if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
    tn.parentNode.replaceChild(frag, tn);
  });
}
function renderAlertBody(raw) {
  const text = String(raw || '').split('\\\\n').join('\\n');
  const doc = new DOMParser().parseFromString('<div>' + text + '</div>', 'text/html');
  const root = doc.body.firstElementChild || doc.body;
  sanitizeAlertBodyNode(root);
  linkifyTextNodes(root);
  root.querySelectorAll('code').forEach((codeEl) => {
    codeEl.setAttribute('role', 'button');
    codeEl.setAttribute('tabindex', '0');
  });
  return root.innerHTML.replace(/\\n/g, '<br>');
}
function showAlertDetail(alertId) {
  const a = channelAlertsData.find(x => x.id === alertId) || alertsCache.find(x => x.id === alertId);
  if (!a) return;
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  const color = sevColors[a.severity] || '#0891b2';
  const icon = sevIcons[a.severity] || '\u2139\ufe0f';
  const ago = timeAgo(a.created_at);
  const statusText = getAlertStatusText(a);
  let metaHtml = '';
  if (a.metadata && Object.keys(a.metadata).length > 0) {
    metaHtml = '<div class="ad-section"><div class="ad-label">Metadata</div>' +
      Object.entries(a.metadata).sort((x,y) => x[0].localeCompare(y[0])).map(([k,v]) =>
        `<div style="margin-top:8px"><div class="ad-meta-key">${escHtml(k)}</div><div class="ad-meta-val">${escHtml(formatAlertMetadataValue(k, v, a))}</div></div>`
      ).join('') + '</div>';
  }
  let actions = '';
  if (!a.acked) {
    if (a.source === 'guardrail') {
      actions += `<button data-detail-action="allow" data-alert-id="${escAttr(a.id)}" style="background:#16a34a;color:#fff">Allow</button>`;
    }
    actions += `<button data-detail-action="ack" data-alert-id="${escAttr(a.id)}" style="background:${color};color:#fff">Ack</button>`;
  }
  actions += `<button data-detail-action="copy" data-alert-id="${escAttr(a.id)}" style="background:#333;color:#ccc">Copy</button>`;
  const overlay = document.createElement('div');
  overlay.className = 'alert-detail-overlay';
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeAlertDetail(overlay); });
  overlay.innerHTML = `<div class="alert-detail-card">
    <div class="ad-header">
      <span class="ad-icon">${icon}</span>
      <div>
        <span class="ad-source" style="background:${color}22;color:${color}">${escHtml((a.source||'').toUpperCase())}</span>
        <div class="ad-time">${ago}${statusText ? ' \u2014 \u2713 ' + escHtml(statusText) : ''}</div>
      </div>
      <button class="ad-close" data-detail-action="close">\u2715</button>
    </div>
    <div class="ad-section"><div class="ad-label">Title</div><div class="ad-title">${escHtml(a.title)}</div></div>
    ${a.body ? `<div class="ad-section"><div class="ad-label">Details</div><div class="ad-body">${renderAlertBody(a.body)}</div></div>` : ''}
    ${metaHtml}
    <div class="ad-actions">${actions}</div>
  </div>`;
  // Wire detail card buttons via delegation (avoids onclick+a.id interpolation)
  overlay.addEventListener('click', (e) => {
    const codeBlock = e.target.closest('.ad-body code');
    if (codeBlock) {
      e.stopPropagation();
      copyAlertCodeBlock(codeBlock);
      return;
    }
    const btn = e.target.closest('[data-detail-action]');
    if (!btn) return;
    e.stopPropagation();
    const action = btn.dataset.detailAction;
    const alertId = btn.dataset.alertId;
    if (action === 'close') { closeAlertDetail(btn); }
    else if (action === 'copy') { copyAlertBody(alertId, btn); }
    else if (action === 'allow' || action === 'ack') { detailAlertAction(action, alertId, btn); }
  });
  document.body.appendChild(overlay);
}
function closeAlertDetail(el) {
  const overlay = el.closest('.alert-detail-overlay');
  if (!overlay) return;
  overlay.style.transition = 'opacity .2s ease';
  overlay.style.opacity = '0';
  setTimeout(() => overlay.remove(), 200);
}
function copyAlertBody(alertId, btn) {
  const a = channelAlertsData.find(x => x.id === alertId) || alertsCache.find(x => x.id === alertId);
  if (a) {
    navigator.clipboard.writeText(a.body || a.title || '');
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '\u2713 Copied';
      btn.style.background = '#16a34a';
      btn.style.color = '#fff';
      setTimeout(() => { btn.textContent = orig; btn.style.background = '#333'; btn.style.color = '#ccc'; }, 1500);
    }
  }
}
function copyAlertCodeBlock(codeEl) {
  const text = codeEl.innerText || codeEl.textContent || '';
  navigator.clipboard.writeText(text).then(() => {
    codeEl.dataset.copied = 'true';
    setTimeout(() => { delete codeEl.dataset.copied; }, 1500);
  }).catch(err => {
    reportError('copyAlertCodeBlock', err);
  });
}
function detailAlertAction(action, alertId, btn) {
  postAlertAction(action, alertId).then(() => {
    markAlertAcknowledged(alertId);
    document.querySelector('.alert-detail-overlay')?.remove();
    // Refresh channel view if on alerts channel
    if (currentChatType === 'alerts' && currentChat) {
      selectChat(currentChat).catch(() => {});
    }
  }).catch(err => {
    reportError('detailAlertAction', err);
    flashAlertActionError(btn);
  });
}

// --- Persistent alerts panel ---
let alertsCache = [];
let lastAlertCheck = new Date().toISOString();
let lastAlertFetchSince = '';
function loadAlerts() {
  fetch('/api/alerts?limit=50').then(r => r.json()).then(alerts => {
    alertsCache = alerts;
    lastAlertCheck = new Date().toISOString();
    renderAlertsPanel();
  }).catch(() => {});
}
function updateLastAlertCheck(iso) {
  const ts = Date.parse(iso || '');
  if (Number.isNaN(ts)) {
    lastAlertCheck = new Date().toISOString();
    return;
  }
  const current = Date.parse(lastAlertCheck || '');
  if (Number.isNaN(current) || ts > current) {
    lastAlertCheck = new Date(ts).toISOString();
  }
}
function getKnownAlertIds() {
  const ids = new Set();
  alertsCache.forEach(a => {
    if (a && a.id) ids.add(a.id);
  });
  return ids;
}
function mergeAlertsIntoCache(alerts) {
  if (!Array.isArray(alerts) || alerts.length === 0) return;
  const known = getKnownAlertIds();
  const fresh = [];
  alerts.forEach(alert => {
    if (!alert || !alert.id || known.has(alert.id)) return;
    known.add(alert.id);
    fresh.push(alert);
  });
  if (fresh.length === 0) return;
  alertsCache = fresh.concat(alertsCache);
  alertsCache.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
  alertsCache = alertsCache.slice(0, 100);
  renderAlertsPanel();
}
function truncateAlertTitle(title, maxLen = 60) {
  const text = String(title || '').trim();
  if (text.length <= maxLen) return text;
  return text.slice(0, Math.max(0, maxLen - 1)).trimEnd() + '…';
}
function getAlertSeverity(alerts) {
  const rank = {info: 0, warning: 1, critical: 2};
  return (alerts || []).reduce((worst, alert) => {
    const sev = alert?.severity || 'info';
    return (rank[sev] || 0) > (rank[worst] || 0) ? sev : worst;
  }, 'info');
}
async function fetchMissedAlerts(since) {
  if (!since || since === lastAlertFetchSince) return;
  lastAlertFetchSince = since;
  try {
    const r = await fetch('/api/alerts?since=' + encodeURIComponent(since) + '&unacked=true', {
      credentials: 'same-origin',
    });
    if (!r.ok) {
      lastAlertFetchSince = '';
      return;
    }
    const alerts = await r.json();
    const known = getKnownAlertIds();
    const missed = (Array.isArray(alerts) ? alerts : []).filter(alert => alert && alert.id && !known.has(alert.id));
    if (missed.length) {
      mergeAlertsIntoCache(missed);
      showMissedAlertsSummary(missed);
    }
    lastAlertCheck = new Date().toISOString();
  } catch (e) {
    lastAlertFetchSince = '';
  }
}
function renderAlertsPanel() {
  const list = document.getElementById('alertsList');
  const unacked = alertsCache.filter(a => !a.acked).length;
  document.getElementById('alertCount').textContent = unacked > 0 ? unacked : '';
  list.innerHTML = '';
  if (alertsCache.length === 0) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:#666;font-size:12px">No alerts</div>';
    return;
  }
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  // Event delegation for panel action buttons (allow/ack) — set up once
  if (!list._panelDelegationAttached) {
    list._panelDelegationAttached = true;
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-panel-action]');
      if (btn) {
        e.stopPropagation();
        panelAlertAction(btn.dataset.panelAction, btn.dataset.alertId, btn);
        return;
      }
      const item = e.target.closest('.alert-item');
      if (item && item.dataset.alertId) { toggleAlertsPanel(); showAlertDetail(item.dataset.alertId); }
    });
  }
  for (const a of alertsCache) {
    const div = document.createElement('div');
    div.className = 'alert-item' + (a.acked ? ' acked' : '');
    div.style.cursor = 'pointer';
    div.dataset.alertId = a.id;
    const icon = sevIcons[a.severity] || '\u2139\ufe0f';
    const color = sevColors[a.severity] || '#0891b2';
    let actions = '';
    if (!a.acked) {
      if (a.source === 'guardrail') {
        actions += `<button data-panel-action="allow" data-alert-id="${escAttr(a.id)}" style="background:#16a34a;color:#fff">Allow</button>`;
      }
      actions += `<button data-panel-action="ack" data-alert-id="${escAttr(a.id)}" style="background:${color};color:#fff">Ack</button>`;
    }
    const ago = timeAgo(a.created_at);
    div.innerHTML = `<span class="ai-icon">${icon}</span>
      <div class="ai-body">
        <div class="ai-source">${escHtml(a.source)}</div>
        <div class="ai-title">${escHtml(a.title)}</div>
        <div class="ai-time">${ago}</div>
      </div>
      <div class="ai-actions">${actions}</div>`;
    list.appendChild(div);
  }
}
function toggleAlertsPanel() {
  const panel = document.getElementById('alertsPanel');
  const showing = panel.classList.toggle('show');
  if (showing) loadAlerts();
  // Close settings if open
  document.getElementById('settingsPanel').classList.remove('show');
}

function toggleSettings() {
  // For group chats, redirect to group settings instead of model selector
  if (currentChatType === 'group') {
    document.getElementById('settingsPanel').classList.remove('show');
    showGroupSettings();
    return;
  }
  const panel = document.getElementById('settingsPanel');
  const showing = panel.classList.toggle('show');
  if (showing) {
    loadSettingsData();
    // Close alerts if open
    document.getElementById('alertsPanel').classList.remove('show');
  }
}

// Click outside to dismiss alerts/settings panels
document.addEventListener('click', (e) => {
  const alertsPanel = document.getElementById('alertsPanel');
  const settingsPanel = document.getElementById('settingsPanel');
  const alertBadge = document.getElementById('alertBadge');
  const settingsBtn = document.getElementById('settingsBtn');
  const stopMenu = document.getElementById('stopMenu');
  const sendBtn = document.getElementById('sendBtn');
  // Close alerts panel if click is outside it and outside the bell
  if (alertsPanel.classList.contains('show') &&
      !alertsPanel.contains(e.target) && !alertBadge.contains(e.target)) {
    alertsPanel.classList.remove('show');
  }
  // Close settings panel if click is outside it and outside the settings button
  if (settingsPanel.classList.contains('show') &&
      !settingsPanel.contains(e.target) && !(settingsBtn && settingsBtn.contains(e.target))) {
    settingsPanel.classList.remove('show');
  }
  if (stopMenu && stopMenu.classList.contains('show') &&
      !stopMenu.contains(e.target) && !(sendBtn && sendBtn.contains(e.target))) {
    hideStopMenu();
  }
});
"""

_JS_SETTINGS = """// --- Settings Panel ---
let _settingsModels = [];  // cached model list

async function loadSettingsData() {
  // Server default model
  try {
    const r = await fetch('/api/health', {credentials: 'same-origin'});
    if (r.ok) {
      const d = await r.json();
      document.getElementById('serverModelDisplay').textContent = d.model || '--';
      document.getElementById('whisperStatus').textContent = d.whisper ? 'Enabled' : 'Disabled';
      document.getElementById('buildInfoDisplay').textContent = d.build || '--';
    }
  } catch(e) {}

  // Local Ollama models
  try {
    const r = await fetch('/api/models/local', {credentials: 'same-origin'});
    if (r.ok) {
      const models = await r.json();
      const localNames = models.map(m => m.id + ' (' + m.sizeGb + 'GB)');
      document.getElementById('ollamaModelsList').textContent = localNames.join(', ') || 'None found';
      _settingsModels = models;
    }
  } catch(e) {}

  // Embedding status
  try {
    const r = await fetch('/api/embedding/status', {credentials: 'same-origin'});
    if (r.ok) {
      const d = await r.json();
      const parts = [];
      if (d.memory) parts.push('Memory: ' + d.memory.files + ' files');
      if (d.transcripts) parts.push('Transcripts: ' + d.transcripts.files + ' files');
      document.getElementById('embeddingStatus').textContent = parts.join(' | ') || '--';
    }
  } catch(e) { document.getElementById('embeddingStatus').textContent = 'Not available'; }

  // Chat model selector
  updateChatModelSelect();
  updateUsageBarVisibility();
  applyChatFontScale();
}

function updateChatModelSelect() {
  const sel = document.getElementById('chatModelSelect');
  const hint = document.getElementById('chatModelHint');
  if (!currentChat) {
    sel.disabled = true;
    hint.textContent = 'Select a chat first';
    sel.innerHTML = '<option value="">--</option>';
    return;
  }
  // Get current chat's model from sidebar data
  const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
  const chatTitle = item?.dataset?.title || 'this chat';
  // Lock model selector when a profile is attached (profile is source of truth)
  const hasProfile = _currentChatProfileId && _currentChatProfileId.length > 0;
  if (hasProfile) {
    sel.disabled = true;
    hint.textContent = 'Model locked by profile: ' + (_currentChatProfileName || _currentChatProfileId);
  } else {
    sel.disabled = false;
    hint.textContent = 'Model for: ' + chatTitle;
  }

  // Build option list: cloud models + local models
  const cloudModels = [
    {id: 'claude-opus-4-7', name: 'Claude Opus 4.7'},
    {id: 'claude-opus-4-6', name: 'Claude Opus 4.6'},
    {id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6'},
    {id: 'claude-haiku-4-5-20251001', name: 'Claude Haiku 4.5'},
    {id: 'grok-4', name: 'Grok 4'},
    {id: 'grok-4-fast', name: 'Grok 4 Fast'},
    {id: 'codex:gpt-5.4', name: 'GPT-5.4'},
    {id: 'codex:gpt-5.4-mini', name: 'GPT-5.4 Mini'},
    {id: 'codex:gpt-5.3-codex', name: 'GPT-5.3'},
    {id: 'codex:gpt-5.2', name: 'GPT-5.2'},
    {id: 'codex:gpt-5.1-codex-max', name: 'GPT-5.1 Max'},
  ];
  sel.innerHTML = '';
  cloudModels.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.name;
    sel.appendChild(opt);
  });
  // Add separator + local models
  if (_settingsModels.length) {
    const sep = document.createElement('option');
    sep.disabled = true;
    sep.textContent = '── Local Models ──';
    sel.appendChild(sep);
    _settingsModels.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.displayName || m.id;
      sel.appendChild(opt);
    });
  }

  // Fetch current chat's model from context endpoint
  fetch('/api/chats/' + currentChat + '/context', {credentials: 'same-origin'})
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d && d.model) {
        sel.value = d.model;
        const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
        if (item) item.dataset.model = d.model;
        updateUsageBarVisibility();
        startUsagePolling();
      }
    })
    .catch(() => {});
}

function changeChatModel(model) {
  if (!currentChat || !model) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({action: 'set_chat_model', chat_id: currentChat, model: model}));
    dbg('set_chat_model:', currentChat, model);
    const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
    if (item) item.dataset.model = model;
    updateUsageBarVisibility();
    // Update hint
    document.getElementById('chatModelHint').textContent = 'Switched to: ' + model;
  }
}
function panelAlertAction(action, alertId, btn) {
  postAlertAction(action, alertId).then(() => {
    markAlertAcknowledged(alertId);
    renderAlertsPanel();
  }).catch(err => {
    reportError('panelAlertAction', err);
    flashAlertActionError(btn);
  });
}
function clearAllAlerts() {
  fetch('/api/alerts', {method:'DELETE'}).then(r => {
    if (r.ok) { alertsCache = []; renderAlertsPanel(); }
  }).catch(() => {});
}
function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return new Date(iso).toLocaleDateString();
}
// Load alerts on page init
setTimeout(loadAlerts, 1000);

let alertToastTimer = null;
let alertToastDeadline = 0;
let alertToastRemaining = 0;
let alertToastTouchStart = null;
function startAlertToastTimer(ms = 10000) {
  clearTimeout(alertToastTimer);
  alertToastRemaining = ms;
  alertToastDeadline = Date.now() + ms;
  alertToastTimer = setTimeout(hideAlertToast, ms);
}
function pauseAlertToastTimer() {
  if (!alertToastTimer) return;
  alertToastRemaining = Math.max(0, alertToastDeadline - Date.now());
  clearTimeout(alertToastTimer);
  alertToastTimer = null;
}
function resumeAlertToastTimer() {
  const toast = document.getElementById('alertToast');
  if (!toast.classList.contains('show') || alertToastTimer || alertToastRemaining <= 0) return;
  startAlertToastTimer(alertToastRemaining);
}
function showAlertToast(msg) {
  const toast = document.getElementById('alertToast');
  const inner = document.getElementById('alertToastInner');
  const preview = document.getElementById('alertToastPreview');
  const sev = msg.severity || 'info';
  const isSummary = msg.kind === 'missed-alerts-summary';
  inner.className = 'alert-toast-inner ' + sev;
  const icons = {critical: '\u26a0\ufe0f', warning: '\u26a0', info: '\u2139\ufe0f'};
  document.getElementById('alertToastIcon').textContent = icons[sev] || '\u2139\ufe0f';
  document.getElementById('alertToastSource').textContent = (msg.source || 'system').toUpperCase();
  document.getElementById('alertToastTitle').textContent = msg.title || '';
  document.getElementById('alertToastText').textContent = msg.body || '';
  preview.innerHTML = '';
  preview.classList.remove('show');
  if (Array.isArray(msg.previewLines) && msg.previewLines.length) {
    msg.previewLines.forEach(line => {
      const row = document.createElement('div');
      row.className = 'alert-preview-line';
      row.textContent = line;
      preview.appendChild(row);
    });
    preview.classList.add('show');
  }
  // Actions
  const actions = document.getElementById('alertToastActions');
  actions.innerHTML = '';
  if (!isSummary && msg.source === 'guardrail' && msg.id) {
    const allowBtn = document.createElement('button');
    allowBtn.className = 'btn-allow';
    allowBtn.textContent = 'Allow';
    allowBtn.onclick = (e) => { e.stopPropagation(); alertAction('allow', msg.id, allowBtn); };
    actions.appendChild(allowBtn);
  }
  if (!isSummary && msg.id) {
    const ackBtn = document.createElement('button');
    ackBtn.className = 'btn-ack';
    ackBtn.textContent = 'Ack';
    ackBtn.onclick = (e) => { e.stopPropagation(); alertAction('ack', msg.id, ackBtn); };
    actions.appendChild(ackBtn);
  }
  const dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn-dismiss';
  dismissBtn.textContent = '\u2715';
  dismissBtn.onclick = (e) => { e.stopPropagation(); hideAlertToast(); };
  actions.appendChild(dismissBtn);
  if (!isSummary && msg.id) {
    mergeAlertsIntoCache([{
      id: msg.id,
      source: msg.source,
      severity: sev,
      title: msg.title || '',
      body: msg.body || '',
      acked: false,
      created_at: msg.created_at || new Date().toISOString(),
      metadata: msg.metadata || {},
    }]);
  }
  updateLastAlertCheck(msg.created_at || new Date().toISOString());
  // Click toast body to open detail
  inner.onclick = () => {
    hideAlertToast();
    if (isSummary) {
      const panel = document.getElementById('alertsPanel');
      panel.classList.add('show');
      document.getElementById('settingsPanel').classList.remove('show');
      renderAlertsPanel();
      return;
    }
    showAlertDetail(msg.id);
  };
  // Show toast
  toast.classList.add('show');
  startAlertToastTimer(10000);
}
function hideAlertToast() {
  document.getElementById('alertToast').classList.remove('show');
  document.getElementById('alertToastPreview').classList.remove('show');
  document.getElementById('alertToastPreview').innerHTML = '';
  clearTimeout(alertToastTimer);
  alertToastTimer = null;
  alertToastDeadline = 0;
  alertToastRemaining = 0;
  alertToastTouchStart = null;
}
function alertActionStatusLabel(action) {
  return '<span style="color:#4ade80;font-size:11px">' + (action === 'allow' ? '\u2713 Allowed' : '\u2713 Acked') + '</span>';
}
function markAlertAcknowledged(alertId) {
  for (const alert of alertsCache) {
    if (alert.id === alertId) alert.acked = true;
  }
  for (const alert of channelAlertsData) {
    if (alert.id === alertId) alert.acked = true;
  }
}
async function postAlertAction(action, alertId) {
  const r = await fetch('/api/alerts/' + alertId + '/' + action, {method: 'POST'});
  let data = null;
  try {
    data = await r.json();
  } catch (_) {}
  if (!r.ok) {
    throw new Error(data?.error || ('Alert action failed: ' + r.status));
  }
  return data || {};
}
function flashAlertActionError(btn) {
  if (!btn) return;
  const originalText = btn.textContent;
  btn.textContent = 'Failed';
  btn.disabled = true;
  setTimeout(() => {
    btn.textContent = originalText;
    btn.disabled = false;
  }, 1500);
}
function alertAction(action, alertId, btn) {
  postAlertAction(action, alertId)
    .then(() => {
      markAlertAcknowledged(alertId);
      hideAlertToast();
    })
    .catch(err => {
      reportError('alertAction', err);
      flashAlertActionError(btn);
    });
}
function showMissedAlertsSummary(alerts) {
  if (!Array.isArray(alerts) || alerts.length === 0) return;
  const count = alerts.length;
  const titles = alerts
    .map(alert => truncateAlertTitle(alert?.title || '', 60))
    .filter(Boolean);
  const previewLines = [];
  if (count > 1) {
    previewLines.push(...titles.slice(0, 3));
    if (count > 3) {
      previewLines.push('+' + (count - 3) + ' more');
    }
  }
  showAlertToast({
    kind: 'missed-alerts-summary',
    source: 'alerts',
    severity: getAlertSeverity(alerts),
    title: count + ' alert' + (count === 1 ? '' : 's') + ' while you were away',
    body: count === 1 ? (titles[0] || '') : '',
    previewLines,
    created_at: new Date().toISOString(),
  });
}

const alertToastInner = document.getElementById('alertToastInner');
if (alertToastInner) {
  alertToastInner.addEventListener('mouseenter', pauseAlertToastTimer);
  alertToastInner.addEventListener('mouseleave', resumeAlertToastTimer);
  alertToastInner.addEventListener('touchstart', (e) => {
    pauseAlertToastTimer();
    const touch = e.touches && e.touches[0];
    alertToastTouchStart = touch ? {x: touch.clientX, y: touch.clientY} : null;
  }, {passive: true});
  alertToastInner.addEventListener('touchend', (e) => {
    const touch = e.changedTouches && e.changedTouches[0];
    if (alertToastTouchStart && touch) {
      const dx = touch.clientX - alertToastTouchStart.x;
      const dy = touch.clientY - alertToastTouchStart.y;
      if (Math.abs(dx) > 60 || dy < -50) {
        hideAlertToast();
        return;
      }
    }
    alertToastTouchStart = null;
    resumeAlertToastTimer();
  }, {passive: true});
  alertToastInner.addEventListener('touchcancel', () => {
    alertToastTouchStart = null;
    resumeAlertToastTimer();
  }, {passive: true});
}
"""

_JS_MARKDOWN = """function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}
// Escape a value for use inside an HTML attribute (e.g. data-alert-id)
function escAttr(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const TOOL_META = {
  Read:     {icon: '📄', label: 'Read File'},
  Edit:     {icon: '✏️', label: 'Edit File'},
  Write:    {icon: '📝', label: 'Write File'},
  Bash:     {icon: '💻', label: 'Run Command'},
  Grep:     {icon: '🔍', label: 'Search Code'},
  Glob:     {icon: '📂', label: 'Find Files'},
  WebFetch: {icon: '🌐', label: 'Fetch URL'},
  WebSearch:{icon: '🔎', label: 'Web Search'},
  Agent:    {icon: '🤖', label: 'Sub-Agent'},
  Skill:    {icon: '⚡', label: 'Skill'},
};

function toolIcon(name) { return (TOOL_META[name] || {}).icon || '🔧'; }
function toolLabel(name) { return (TOOL_META[name] || {}).label || name; }

function toolSummary(name, input) {
  const o = typeof input === 'string' ? (() => { try { return JSON.parse(input); } catch(e) { return {}; } })() : (input || {});
  switch (name) {
    case 'Read': {
      const p = o.file_path || '';
      const short = p.split('/').slice(-2).join('/');
      let s = `Reading <code>${escHtml(short)}</code>`;
      if (o.offset) s += ` from line ${o.offset}`;
      if (o.limit) s += ` (${o.limit} lines)`;
      return s;
    }
    case 'Edit': {
      const p = (o.file_path || '').split('/').slice(-2).join('/');
      return `Editing <code>${escHtml(p)}</code>`;
    }
    case 'Write': {
      const p = (o.file_path || '').split('/').slice(-2).join('/');
      return `Writing <code>${escHtml(p)}</code>`;
    }
    case 'Bash': {
      const cmd = o.command || '';
      const short = cmd.length > 80 ? cmd.substring(0, 77) + '...' : cmd;
      const desc = o.description || '';
      if (desc) return `${escHtml(desc)}`;
      return `<code>${escHtml(short)}</code>`;
    }
    case 'Grep': {
      const pat = o.pattern || '';
      const path = o.path ? o.path.split('/').slice(-2).join('/') : '';
      let s = `Searching for <code>${escHtml(pat)}</code>`;
      if (path) s += ` in ${escHtml(path)}`;
      return s;
    }
    case 'Glob': {
      const pat = o.pattern || '';
      return `Finding files matching <code>${escHtml(pat)}</code>`;
    }
    case 'Agent': {
      return escHtml(o.description || o.prompt?.substring(0, 80) || 'Running sub-agent');
    }
    case 'Skill': {
      return `Running skill <code>${escHtml(o.skill || '')}</code>`;
    }
    case 'WebSearch': {
      return `Searching: <code>${escHtml(o.query || '')}</code>`;
    }
    default: return null;
  }
}

function toolResultSummary(name, content) {
  if (!content) return null;
  const s = typeof content === 'string' ? content : JSON.stringify(content);
  if (name === 'Grep' || name === 'Glob') {
    const lines = s.trim().split('\\n').filter(Boolean);
    if (lines.length > 0) return `${lines.length} result${lines.length === 1 ? '' : 's'}`;
  }
  if (name === 'Bash') {
    const lines = s.trim().split('\\n');
    if (lines.length <= 3) return null;
    return `${lines.length} lines of output`;
  }
  return null;
}

function linkifyMarkdownLinks(html) {
  // Markdown links: [text](url) — internal or external
  let out = String(html || '').replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:underline">$1</a>'
  );
  // Bare URLs not already inside an href="..." or >...</a>
  out = out.replace(
    /(?<!href="|">)(https?:\/\/[^\s<)]+)/g,
    '<a href="$1" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:underline">$1</a>'
  );
  return out;
}

function renderInlineMarkdown(text) {
  let html = escHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return linkifyMarkdownLinks(html);
}

function renderMarkdown(el, rawText) {
  const source = (rawText !== undefined && rawText !== null) ? rawText : (el.textContent || '');
  const codeBlocks = [];
  let text = source.replace(/```([\\w-]*)\\n([\\s\\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push(`<pre><code>${escHtml(code.trimEnd())}</code></pre>`);
    return `@@CODEBLOCK_${codeBlocks.length - 1}@@`;
  });
  const lines = text.split('\\n');
  const html = [];
  let listType = null;

  function closeList() {
    if (!listType) return;
    html.push(listType === 'ol' ? '</ol>' : '</ul>');
    listType = null;
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    const codeMatch = trimmed.match(/^@@CODEBLOCK_(\\d+)@@$/);
    if (codeMatch) {
      closeList();
      html.push(codeBlocks[Number(codeMatch[1])] || '');
      continue;
    }

    let match = line.match(/^###\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h4>${renderInlineMarkdown(match[1])}</h4>`);
      continue;
    }

    match = line.match(/^##\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h3>${renderInlineMarkdown(match[1])}</h3>`);
      continue;
    }

    match = line.match(/^#\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h2>${renderInlineMarkdown(match[1])}</h2>`);
      continue;
    }

    match = line.match(/^[-*]\\s+(.+)$/);
    if (match) {
      if (listType !== 'ul') {
        closeList();
        html.push('<ul>');
        listType = 'ul';
      }
      html.push(`<li>${renderInlineMarkdown(match[1])}</li>`);
      continue;
    }

    match = line.match(/^\\d+\\.\\s+(.+)$/);
    if (match) {
      if (listType !== 'ol') {
        closeList();
        html.push('<ol>');
        listType = 'ol';
      }
      html.push(`<li>${renderInlineMarkdown(match[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }

  closeList();
  el.innerHTML = html.join('');
}

function updateSendBtn() {
  const btn = document.getElementById('sendBtn');
  const canSend = Boolean(currentChat && ws && ws.readyState === WebSocket.OPEN);
  const inputEl = document.getElementById('input');
  const composerHasText = Boolean(inputEl && inputEl.value.trim());
  const hasActiveOrQueuedWork = streaming || _isAnyStreamActive() || queuedMessages.length > 0;
  const showStop = hasActiveOrQueuedWork && !composerHasText;
  if (showStop) {
    btn.innerHTML = '&#9632;';
    btn.className = 'btn-compose compose-action is-stop';
    btn.disabled = !canSend;
    btn.title = (activeStreams.size + queuedMessages.length) > 1 ? 'Choose what to stop' : 'Stop';
  } else {
    btn.innerHTML = '&#9654;';
    btn.className = 'btn-compose compose-action is-send';
    btn.disabled = !canSend;
    btn.title = btn.disabled ? 'Waiting for chat initialization' : 'Send';
    hideStopMenu();
  }
}

function setTranscribeStatus(text = '') {
  const el = document.getElementById('transcribeStatus');
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}

function stopVoiceStream() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach(track => track.stop());
  mediaStream = null;
}

function updateVoiceBtn() {
  // Voice button removed — iOS dictation handles this natively
}

function buildAttachmentPreview(att, idx) {
  const item = document.createElement('div');
  item.className = 'attach-item';
  if (att.type === 'image') {
    const img = document.createElement('img');
    img.src = `data:${att.mimeType};base64,${att.base64}`;
    img.alt = '';
    item.appendChild(img);
  } else {
    const icon = document.createElement('span');
    icon.innerHTML = '&#128196;';
    item.appendChild(icon);
  }
  const label = document.createElement('span');
  label.textContent = att.name;
  item.appendChild(label);
  const remove = document.createElement('span');
  remove.className = 'remove';
  remove.innerHTML = '&times;';
  remove.onclick = () => removeAttachment(idx);
  item.appendChild(remove);
  return item;
}

function renderAttachmentPreview() {
  const preview = document.getElementById('attachPreview');
  preview.innerHTML = '';
  pendingAttachments.forEach((att, idx) => {
    preview.appendChild(buildAttachmentPreview(att, idx));
  });
}

async function transcribeVoiceBlob(blob, mimeType) {
  transcribing = true;
  setTranscribeStatus('Transcribing voice note...');

  const ext = mimeType.includes('mp4') ? 'm4a' :
    mimeType.includes('ogg') ? 'ogg' :
    mimeType.includes('mpeg') ? 'mp3' : 'webm';
  const formData = new FormData();
  formData.append('file', blob, `voice.${ext}`);
  try {
    const r = await fetch('/api/transcribe', {method: 'POST', body: formData, credentials: 'same-origin'});
    const data = await r.json();
    if (!r.ok) {
      throw new Error(data.error || `transcribe failed: ${r.status}`);
    }
    const input = document.getElementById('input');
    const prefix = input.value.trim() ? `${input.value.trim()} ` : '';
    input.value = `${prefix}${data.text || ''}`.trim();
    input.dispatchEvent(new Event('input'));
    input.focus();
    setTranscribeStatus('');
  } catch (err) {
    reportError('transcribe voice', err);
    addSystemMsg(`Voice transcription failed: ${err?.message || err}`);
    setTranscribeStatus('');
  } finally {
    transcribing = false;

  }
}

async function toggleVoiceRecording() {
  if (transcribing) return;
  if (recording && mediaRecorder) {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    addSystemMsg('Voice recording is not supported here. Use keyboard dictation instead.');
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({audio: true});
    recordingChunks = [];
    const preferredMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : '';
    mediaRecorder = preferredMime ? new MediaRecorder(mediaStream, {mimeType: preferredMime}) : new MediaRecorder(mediaStream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordingChunks.push(event.data);
      }
    };
    mediaRecorder.onerror = (event) => {
      reportError('voice recorder', event.error || event);
      setTranscribeStatus('');
      recording = false;
      mediaRecorder = null;
      recordingChunks = [];
      stopVoiceStream();
  
    };
    mediaRecorder.onstop = async () => {
      const mimeType = mediaRecorder?.mimeType || 'audio/webm';
      const chunks = recordingChunks.slice();
      mediaRecorder = null;
      recording = false;
      recordingChunks = [];
      stopVoiceStream();
  
      if (!chunks.length) {
        setTranscribeStatus('');
        return;
      }
      await transcribeVoiceBlob(new Blob(chunks, {type: mimeType}), mimeType);
    };
    mediaRecorder.start();
    recording = true;
    setTranscribeStatus('Recording voice note... tap again to stop');

  } catch (err) {
    reportError('toggle voice', err);
    recording = false;
    mediaRecorder = null;
    recordingChunks = [];
    stopVoiceStream();
    setTranscribeStatus('');

    addSystemMsg(`Voice recording failed: ${err?.message || err}`);
  }
}
"""

_JS_COMPOSER = """// --- Send ---
async function send(options = {}) {
  const allowLastPrompt = Boolean(options.allowLastPrompt);
  const input = document.getElementById('input');
  const draftText = input.value;
  const rawText = draftText.trim();
  const text = rawText || (allowLastPrompt ? lastSubmittedPrompt : '');
  const effectiveTargetAgent = options.targetAgent || '';
  dbg(' send:', {text: text?.substring(0,30), currentChat, streaming, wsState: ws?.readyState});
  if (!text && pendingAttachments.length === 0) return;
  if (!currentChat) {
    dbg(' no active chat on send, forcing init');
    try {
      await ensureInitialized('send-no-chat');
    } catch (err) {
      reportError('send init', err);
      addSystemMsg('Chat initialization failed. Check the debug bar.');
      return;
    }
  }
  if (!currentChat) {
    dbg('ERROR: no active chat after init');
    addSystemMsg('Chat initialization failed. Check the debug bar.');
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) { dbg('ERROR: ws not open'); return; }
  _userScrolledUp = false;
  _hideNewContentPill();
  const attachmentSnapshot = pendingAttachments.map(att => ({...att}));
  const msg = {action: 'send', chat_id: currentChat, prompt: text};
  if (effectiveTargetAgent) msg.target_agent = effectiveTargetAgent;
  if (attachmentSnapshot.length > 0) {
    msg.attachments = attachmentSnapshot.map(a => ({id: a.id, type: a.type, name: a.name, url: a.url, ext: a.ext}));
  }
  lastSubmittedPrompt = text;
  hideStopMenu();
  clearComposerDraft({keepFocus: true});
  // WSDIAG: log at send boundary so we can correlate with server recv_attach
  // and the subsequent stream_start frame. ws_chat_attached mismatch here is
  // a smoking gun.
  console.log('WSDIAG send chat=' + (currentChat || '').slice(0,8) + ' len=' + (text || '').length + ' wsState=' + (ws && ws.readyState));
  try {
    ws.send(JSON.stringify(msg));
  } catch (err) {
    if (draftText || attachmentSnapshot.length) {
      restoreComposerDraft(draftText, attachmentSnapshot);
    }
    throw err;
  }
  addUserMsg(text, attachmentSnapshot);
  _showThinkingIndicator();
  refreshDebugState('send');
}
"""

_JS_CHATS = """// --- Chats ---
async function loadChats() {
  const r = await fetch('/api/chats', {credentials: 'same-origin'});
  dbg(' loadChats status:', r.status);
  if (!r.ok) {
    dbg('ERROR: loadChats failed:', r.status);
    throw new Error(`loadChats failed: ${r.status}`);
  }
  const chats = await r.json();
  knownChatCount = chats.length;
  dbg(' chats:', chats.length, chats.map(c => c.id));

  // Partition into channels (chat + alerts) and threads
  const channels = chats.filter(c => (c.type || 'chat') !== 'thread');
  const threads = chats.filter(c => c.type === 'thread').slice(0, 10);

  function buildChatItem(c, isThread) {
    const d = document.createElement('div');
    d.className = 'chat-item' + (c.id === currentChat ? ' active' : '') + (isThread ? ' thread-item' : '');
    const top = document.createElement('div');
    top.className = 'chat-item-top';
    // Icon prefix
    if (isThread) {
      const icon = document.createElement('span');
      icon.className = 'ci-avatar';
      icon.textContent = '\u26A1';
      top.appendChild(icon);
    } else if (c.type === 'group') {
      const icon = document.createElement('span');
      icon.className = 'ci-avatar';
      icon.textContent = c.profile_avatar || '👥';
      top.appendChild(icon);
    } else if (c.profile_avatar) {
      const avatarSpan = document.createElement('span');
      avatarSpan.className = 'ci-avatar';
      avatarSpan.textContent = c.profile_avatar;
      top.appendChild(avatarSpan);
    } else {
      const avatarSpan = document.createElement('span');
      avatarSpan.className = 'ci-avatar';
      avatarSpan.textContent = c.type === 'alerts' ? '🚨' : '💬';
      top.appendChild(avatarSpan);
    }
    const titleSpan = document.createElement('span');
    titleSpan.className = 'chat-item-title';
    let displayTitle = c.title || 'Untitled';
    if (c.type === 'group' && c.member_count) displayTitle += ' (' + c.member_count + ')';
    titleSpan.textContent = displayTitle;
    top.appendChild(titleSpan);
    d.dataset.id = c.id;
    d.dataset.title = c.title || 'Untitled';
    d.dataset.type = c.type || 'chat';
    d.dataset.category = c.category || '';
    d.dataset.model = c.model || '';
    d.dataset.profileId = c.profile_id || '';
    d.dataset.profileName = c.profile_name || '';
    d.dataset.profileAvatar = c.profile_avatar || '';
    d.onclick = () => selectChat(c.id, c.title, c.type, c.category).catch(err => reportError('selectChat click', err));
    d.ondblclick = (e) => { e.stopPropagation(); startRenameChat(d, c.id, c.title || 'Untitled'); };
    d.oncontextmenu = (e) => { e.preventDefault(); e.stopPropagation(); confirmDeleteChat(c.id, c.title || 'Untitled'); };
    const actions = document.createElement('span');
    actions.className = 'chat-item-actions';
    actions.innerHTML =
      '<button class="chat-action-btn" title="Rename" data-action="rename">\u270F\uFE0F</button>' +
      '<button class="chat-action-btn" title="Delete" data-action="delete">🗑️</button>';
    actions.querySelector('[data-action="rename"]').onclick = (e) => {
      e.stopPropagation(); startRenameChat(d, c.id, c.title || 'Untitled');
    };
    actions.querySelector('[data-action="delete"]').onclick = (e) => {
      e.stopPropagation(); confirmDeleteChat(c.id, c.title || 'Untitled');
    };
    top.appendChild(actions);
    d.appendChild(top);
    if (!isThread) {
      const sub = document.createElement('div');
      sub.className = 'chat-item-subtitle';
      const agentName = c.profile_name || '';
      const modelName = c.model || '';
      if (c.type === 'alerts') {
        sub.textContent = 'Alerts · Trading + System';
      } else if (c.type === 'group') {
        sub.textContent = 'Group · ' + (c.member_count || 0) + ' members';
      } else if (agentName && modelName) {
        sub.appendChild(document.createTextNode(agentName + ' · '));
        const model = document.createElement('span');
        model.className = 'model';
        model.textContent = modelName;
        sub.appendChild(model);
      } else if (modelName) {
        sub.textContent = modelName;
      }
      if (sub.textContent || sub.children.length) {
        d.appendChild(sub);
      }
    }
    return d;
  }

  // Render channels
  const list = document.getElementById('chatList');
  list.innerHTML = '';
  channels.forEach(c => list.appendChild(buildChatItem(c, false)));

  // Render threads section
  const threadHeader = document.getElementById('threadSectionHeader');
  const threadList = document.getElementById('threadList');
  threadList.innerHTML = '';
  if (threads.length > 0) {
    threadHeader.style.display = 'flex';
    const collapsed = threadList.dataset.collapsed === 'true';
    threadList.style.display = collapsed ? 'none' : '';
    threads.forEach(c => threadList.appendChild(buildChatItem(c, true)));
  } else {
    threadHeader.style.display = 'none';
  }

  setActiveChatUI();
  updateUsageBarVisibility();
  refreshDebugState('loadChats');
  return chats;
}

function startRenameChat(el, chatId, currentTitle) {
  const titleSpan = el.querySelector('.chat-item-title');
  if (!titleSpan) return;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle;
  input.className = 'rename-input';
  input.style.cssText = 'width:100%;padding:4px 8px;font-size:14px;border:1px solid var(--accent);border-radius:4px;background:var(--bg);color:var(--fg);outline:none;flex:1;min-width:0';
  titleSpan.replaceWith(input);
  input.focus();
  input.select();
  const commit = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await renameChat(chatId, newTitle);
    }
    // loadChats will rebuild the list via WS event or fallback
    const ns = document.createElement('span');
    ns.className = 'chat-item-title';
    ns.textContent = newTitle || currentTitle;
    ns.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0';
    input.replaceWith(ns);
  };
  input.onblur = () => commit();
  input.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
  };
  // Prevent the click from triggering selectChat
  el.onclick = (e) => e.stopPropagation();
}

async function confirmDeleteChat(chatId, title) {
  if (!confirm(`Delete "${title}"? This removes all messages.`)) return;
  const ok = await deleteChat(chatId);
  if (!ok) alert('Failed to delete chat. Please try again.');
}

async function deleteChat(chatId) {
  try {
    const r = await fetch(`/api/chats/${chatId}`, {
      method: 'DELETE', credentials: 'same-origin'
    });
    if (!r.ok) {
      dbg('ERROR: deleteChat failed:', r.status);
      return false;
    }
    const wasCurrent = currentChat === chatId;
    await loadChats();
    if (wasCurrent) {
      const first = document.querySelector('.chat-item');
      if (first) first.click();
    }
    return true;
  } catch (e) {
    dbg('ERROR: deleteChat:', e);
    return false;
  }
}

async function renameChat(chatId, newTitle) {
  try {
    const r = await fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({title: newTitle})
    });
    if (!r.ok) dbg('ERROR: renameChat failed:', r.status);
  } catch (e) {
    dbg('ERROR: renameChat:', e);
  }
  // chat_updated WS event will trigger loadChats
}

let _selectChatDebounce = null;
let _lastSelectChatId = null;
let _lastSelectChatTime = 0;

let currentChatType = 'chat';
let _groupMembers = []; // cached members for current group chat
const _storedPin = localStorage.getItem('sidebarPinned');
let sidebarPinned = _storedPin === null ? window.innerWidth >= 600 : _storedPin === '1';
let themeMode = localStorage.getItem('themeMode')
  || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
let chatFontScale = Number(localStorage.getItem('chatFontScale') || '1');
if (!Number.isFinite(chatFontScale)) chatFontScale = 1;
chatFontScale = Math.min(Math.max(chatFontScale, 0.7), 2.0);

function applyTheme() {
  document.body.classList.toggle('theme-light', themeMode === 'light');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', themeMode === 'light' ? '#F8FAFC' : '#0F172A');
  const btn = document.getElementById('themeBtn');
  if (btn) {
    btn.textContent = themeMode === 'light' ? '☀' : '☾';
    btn.title = themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode';
  }
}

function toggleTheme() {
  themeMode = themeMode === 'light' ? 'dark' : 'light';
  localStorage.setItem('themeMode', themeMode);
  applyTheme();
}

function applyChatFontScale() {
  document.documentElement.style.setProperty('--chat-font-scale', String(chatFontScale));
  const slider = document.getElementById('fontScaleSlider');
  const value = document.getElementById('fontScaleValue');
  const reset = document.getElementById('fontScaleResetBtn');
  const percent = Math.round(chatFontScale * 100);
  if (slider) slider.value = String(percent);
  if (value) value.textContent = `${percent}%`;
  if (reset) reset.style.display = chatFontScale === 1 ? 'none' : 'inline-block';
}

function setChatFontScale(nextScale) {
  chatFontScale = Math.min(Math.max(nextScale, 0.7), 2.0);
  localStorage.setItem('chatFontScale', String(chatFontScale));
  applyChatFontScale();
}

async function selectChat(id, title, chatType, category, options) {
  options = options || {};
  const forceReload = Boolean(options.forceReload);
  const skipAttach = Boolean(options.skipAttach);
  // Debounce: skip if same chat selected within 500ms
  const now = Date.now();
  if (!forceReload && id === _lastSelectChatId && now - _lastSelectChatTime < 500) {
    dbg(' selectChat DEBOUNCED:', id);
    return;
  }
  _lastSelectChatId = id;
  _lastSelectChatTime = now;

  // Resolve chat type from sidebar data if not passed
  const sidebarItem = document.querySelector(`.chat-item[data-id="${id}"]`);
  if (!chatType) {
    chatType = sidebarItem?.dataset?.type || 'chat';
    category = sidebarItem?.dataset?.category || '';
  }
  currentChatType = chatType || 'chat';
  // B-42: purge stream contexts from previous chat to prevent ghost bubbles
  // B-19: only purge when actually switching chats — reloading the same chat
  // must preserve active stream contexts or long-running streams go invisible
  if (id !== currentChat) {
    activeStreams.clear();
    queuedMessages = [];
    _stopMenuConfirmKey = '';
    Object.keys(_streamCtx).forEach(sid => { delete _streamCtx[sid]; });
    clearComposerDraft();
    // Reset history pagination for new chat
    _historyHasMore = false;
    _historyOldestId = null;
    _historyLoading = false;
  }
  hideStopMenu();
  // B-23: close side panel on channel switch so thinking/tool content from
  // the previous channel doesn't bleed into the newly selected one.
  closeSidePanel();

  // Update topbar profile indicator
  const pId = sidebarItem?.dataset?.profileId || '';
  const pName = sidebarItem?.dataset?.profileName || '';
  const pAvatar = sidebarItem?.dataset?.profileAvatar || '';
  _currentChatProfileId = pId;
  updateTopbarProfile(pName, pAvatar);
  dbg(' selectChat:', id, title, 'type:', currentChatType);
  const seq = ++selectChatSeq;
  setCurrentChat(id, title || 'ApexChat');
  closeSidebar();
  // Attach WS to the selected chat so we receive live stream events
  if (!skipAttach && ws && ws.readyState === WebSocket.OPEN) {
    // WSDIAG
    console.log('WSDIAG attach chat=' + (id || '').slice(0,8) + ' site=selectChat');
    ws.send(JSON.stringify({action: 'attach', chat_id: id}));
  }

  // Alerts channel — render alerts list instead of messages
  if (currentChatType === 'alerts') {
    const catParam = category ? `&category=${category}` : '';
    const r = await fetch(`/api/alerts?limit=100${catParam}`, {credentials: 'same-origin'});
    if (!r.ok) return;
    const alerts = await r.json();
    if (seq !== selectChatSeq || currentChat !== id) return;
    renderAlertsList(alerts);
    // Hide input bar, locked bar, and context bar for alerts channels
    document.getElementById('composerBar').style.display = 'none';
    document.getElementById('premiumLockedBar').style.display = 'none';
    document.getElementById('contextBar').classList.remove('visible');
    return;
  }
  // Premium gate: check if group channels are locked
  const lockedBar = document.getElementById('premiumLockedBar');
  let groupLocked = false;
  if (currentChatType === 'group') {
    const features = await _checkPremiumFeatures();
    groupLocked = !features.groups_enabled && !features.features?.groups;
  }
  if (groupLocked) {
    lockedBar.style.display = '';
    document.getElementById('composerBar').style.display = 'none';
  } else {
    lockedBar.style.display = 'none';
    document.getElementById('composerBar').style.display = '';
  }
  // Load group members for @mention autocomplete
  currentGroupMembers = [];
  if (currentChatType === 'group' && !groupLocked) {
    try {
      const mr = await fetch(`/api/chats/${id}/members`, {credentials: 'same-origin'});
      if (mr.ok) {
        const md = await mr.json();
        currentGroupMembers = md.members || [];
        dbg('group members loaded:', currentGroupMembers.length);
      }
    } catch(e) { dbg('group members fetch error:', e); }
  }
  // Update placeholder for groups
  const inp = document.getElementById('input');
  inp.placeholder = currentGroupMembers.length ? 'Message... (type @ to mention)' : 'Message...';
  refreshComposerDraftState();

  // Load messages
  const r = await fetch(`/api/chats/${id}/messages`, {credentials: 'same-origin'});
  if (!r.ok) {
    dbg('ERROR: selectChat messages failed:', id, r.status);
    throw new Error(`selectChat failed: ${r.status}`);
  }
  const data = await r.json();
  const msgs = Array.isArray(data) ? data : (data.messages || []);
  if (seq !== selectChatSeq || currentChat !== id) {
    dbg(' stale selectChat response ignored:', id);
    return;
  }

  // Initialize pagination state
  _historyHasMore = data.has_more === true;
  _historyOldestId = msgs.length > 0 ? msgs[0].id : null;
  _historyLoading = false;

  const el = document.getElementById('messages');
  el.innerHTML = '';

  // Show "beginning of conversation" marker if all messages fit in first page
  if (!_historyHasMore && msgs.length > 0) {
    const marker = document.createElement('div');
    marker.id = '_historyEnd';
    marker.style.cssText = 'text-align:center;padding:16px 12px 8px;color:var(--dim);font-size:12px;opacity:0.6';
    marker.textContent = '\u2500\u2500 Beginning of conversation \u2500\u2500';
    el.appendChild(marker);
  }

  msgs.forEach(m => el.appendChild(_renderHistoryMsg(m)));
  _userScrolledUp = false;
  scrollBottomForce();
  fetchContext(id);

  // After DOM rebuild, restore any active streaming state.
  // Buffer replay events may have created DOM elements that innerHTML=''
  // just wiped. Re-create every active streaming bubble from accumulated context.
  const activeIds = _activeStreamIds();
  if (activeIds.length > 0) {
    activeIds.forEach(sid => {
      const ctx = _streamCtx[sid];
      if (!ctx) return;
      _rebuildActiveStreamUi(ctx);
    });
    const preferredSid = activeIds.includes(currentStreamId) ? currentStreamId : activeIds[activeIds.length - 1];
    _syncLegacyStreamGlobals(preferredSid, {clearSessionWhenIdle: false});
    scrollBottomForce();
    dbg('streaming state restored after message load, streams:', activeIds.join(','));
  }

  refreshDebugState('messages-loaded');
}

async function newChat() {
  dbg(' creating new chat...');
  const r = await fetch('/api/chats', {method: 'POST', credentials: 'same-origin'});
  if (!r.ok) {
    dbg('ERROR: newChat failed:', r.status);
    throw new Error(`newChat failed: ${r.status}`);
  }
  const data = await r.json();
  dbg(' created chat:', data.id);
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'New Channel');
  refreshDebugState('newChat');
  return data.id;
}
"""

_JS_SIDEBAR = """// --- Sidebar ---
function openSidebar() {
  if (sidebarPinned) {
    applySidebarPinnedState();
    return;
  }
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebarOverlay').classList.add('open');
}
function closeSidebar() {
  if (sidebarPinned) return;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

function applySidebarPinnedState() {
  const body = document.body;
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const pinBtn = document.getElementById('pinSidebarBtn');
  if (!body || !sidebar || !overlay || !pinBtn) return;

  body.classList.toggle('sidebar-pinned', sidebarPinned);
  sidebar.classList.toggle('open', sidebarPinned);
  overlay.classList.remove('open');
  pinBtn.classList.toggle('active', sidebarPinned);
  pinBtn.setAttribute('aria-pressed', sidebarPinned ? 'true' : 'false');
  pinBtn.title = sidebarPinned ? 'Unpin sidebar' : 'Pin sidebar';
}

function toggleSidebarPin() {
  sidebarPinned = !sidebarPinned;
  localStorage.setItem('sidebarPinned', sidebarPinned ? '1' : '0');
  applySidebarPinnedState();
}
"""

_JS_ATTACHMENTS = """// --- Attachments ---
let pendingAttachments = [];

function clearAttachments() {
  pendingAttachments = [];
  document.getElementById('attachPreview').innerHTML = '';
  refreshComposerDraftState();
}

async function handleFiles(files) {
  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const r = await fetch('/api/upload', {method: 'POST', body: formData, credentials: 'same-origin'});
      if (!r.ok) {
        const detail = await r.text();
        dbg('ERROR: upload failed:', r.status, detail);
        continue;
      }
      const att = await r.json();
      pendingAttachments.push(att);
      const preview = document.getElementById('attachPreview');
      preview.appendChild(buildAttachmentPreview(att, pendingAttachments.length - 1));
      dbg(' attached:', att.name, att.type);
      refreshComposerDraftState();
    } catch(e) {
      dbg('ERROR: upload:', e);
    }
  }
}

function removeAttachment(idx) {
  pendingAttachments.splice(idx, 1);
  const preview = document.getElementById('attachPreview');
  preview.innerHTML = '';
  pendingAttachments.forEach((att, i) => {
    preview.appendChild(buildAttachmentPreview(att, i));
  });
  refreshComposerDraftState();
}

function audioMimeType() {
  if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') return '';
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || '';
}

async function uploadVoiceNote(blob, ext) {
  transcribing = true;

  setTranscribeStatus('Transcribing voice note...');
  try {
    const formData = new FormData();
    formData.append('file', blob, `voice-note.${ext}`);
    const r = await fetch('/api/transcribe', {method: 'POST', body: formData, credentials: 'same-origin'});
    const data = await r.json();
    if (!r.ok) {
      throw new Error(data.error || `Transcription failed: ${r.status}`);
    }
    const input = document.getElementById('input');
    input.value = [input.value.trim(), data.text].filter(Boolean).join(input.value.trim() ? '\\n' : '');
    input.dispatchEvent(new Event('input'));
    input.focus();
  } finally {
    transcribing = false;
    setTranscribeStatus('');

  }
}

async function toggleVoiceRecording() {
  if (transcribing) return;
  if (recording && mediaRecorder) {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    addSystemMsg('Voice recording is not supported in this browser.');
    return;
  }

  const mimeType = audioMimeType();
  mediaStream = await navigator.mediaDevices.getUserMedia({audio: true});
  recordingChunks = [];
  mediaRecorder = mimeType ? new MediaRecorder(mediaStream, {mimeType}) : new MediaRecorder(mediaStream);
  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) {
      recordingChunks.push(event.data);
    }
  };
  mediaRecorder.onerror = (event) => {
    reportError('mediaRecorder', event.error || event);
    addSystemMsg('Voice recording failed.');
    recording = false;
    mediaRecorder = null;
    stopVoiceStream();

  };
  mediaRecorder.onstop = async () => {
    const blobType = mediaRecorder.mimeType || mimeType || 'audio/webm';
    const ext = blobType.includes('mp4') ? 'mp4' : (blobType.includes('ogg') ? 'ogg' : 'webm');
    const blob = new Blob(recordingChunks, {type: blobType});
    recording = false;
    mediaRecorder = null;
    stopVoiceStream();

    if (blob.size === 0) {
      setTranscribeStatus('');
      return;
    }
    await uploadVoiceNote(blob, ext).catch(err => {
      reportError('uploadVoiceNote', err);
      addSystemMsg(err.message || 'Voice transcription failed.');
    });
  };
  recording = true;

  setTranscribeStatus('Recording voice note... tap again to stop');
  mediaRecorder.start();
}
"""

_JS_INIT = """// --- PWA service worker ---
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// --- Init ---
document.getElementById('menuBtn').onclick = openSidebar;
document.getElementById('sidebarOverlay').onclick = closeSidebar;
document.getElementById('pinSidebarBtn').onclick = toggleSidebarPin;
document.getElementById('themeBtn').onclick = toggleTheme;
document.getElementById('fontScaleSlider').oninput = (e) => setChatFontScale(Number(e.target.value) / 100);
document.getElementById('fontScaleResetBtn').onclick = () => setChatFontScale(1);
document.getElementById('newChatBtn').onclick = () => {
  loadProfiles().then(() => showNewChatProfilePicker()).catch(err => reportError('profile picker', err));
};
document.getElementById('threadToggle').onclick = () => {
  const tl = document.getElementById('threadList');
  const btn = document.getElementById('threadToggle');
  const collapsed = tl.dataset.collapsed !== 'true';
  tl.dataset.collapsed = collapsed;
  tl.style.display = collapsed ? 'none' : '';
  btn.textContent = collapsed ? '\u25B8' : '\u25BE';
};
document.getElementById('sendBtn').onclick = () => {
  const inputEl = document.getElementById('input');
  const composerHasText = Boolean(inputEl && inputEl.value.trim());
  if ((streaming || _isAnyStreamActive() || queuedMessages.length > 0) && !composerHasText) {
    toggleStopMenu();
  } else {
    send().catch(err => reportError('send click', err));
  }
};
document.getElementById('fileInput').onchange = (e) => {
  if (e.target.files.length) handleFiles(e.target.files);
  e.target.value = '';
};
function _staleBarTarget() {
  const bar = document.getElementById('staleBar');
  const selected = _pickWatchdogTarget();
  return {
    streamId: (bar && bar.dataset.streamId) || ((selected && selected.ctx && selected.ctx.id) || ''),
    profileId: (bar && bar.dataset.profileId) || ((selected && selected.ctx && selected.ctx.speaker && selected.ctx.speaker.id) || ''),
  };
}
document.getElementById('staleCancelBtn').onclick = () => {
  const target = _staleBarTarget();
  cancelStream(target.streamId || '').catch(err => reportError('stale cancel', err));
};
document.getElementById('staleRetryBtn').onclick = () => {
  const target = _staleBarTarget();
  retryLastPrompt(target.streamId || '', target.profileId || '').catch(err => reportError('stale retry click', err));
};

// --- Drag-and-drop file attachment ---
let _dragCounter = 0;
const _dropOverlay = document.getElementById('dropOverlay');
document.addEventListener('dragenter', (e) => {
  if (!e.dataTransfer?.types?.includes('Files')) return;
  e.preventDefault();
  _dragCounter++;
  _dropOverlay.classList.add('visible');
});
document.addEventListener('dragleave', (e) => {
  _dragCounter--;
  if (_dragCounter <= 0) { _dragCounter = 0; _dropOverlay.classList.remove('visible'); }
});
document.addEventListener('dragover', (e) => {
  if (!e.dataTransfer?.types?.includes('Files')) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
});
document.addEventListener('drop', (e) => {
  e.preventDefault();
  _dragCounter = 0;
  _dropOverlay.classList.remove('visible');
  if (e.dataTransfer?.files?.length) {
    handleFiles(e.dataTransfer.files);
    document.getElementById('input').focus();
  }
});

const input = document.getElementById('input');
refreshComposerDraftState();
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  // @mention autocomplete
  _checkMentionPopup();
  refreshComposerDraftState();
});
input.addEventListener('keydown', (e) => {
  const popup = document.getElementById('mentionPopup');
  if (popup && popup.classList.contains('visible')) {
    const items = popup.querySelectorAll('.mention-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionSelectedIdx = Math.min(mentionSelectedIdx + 1, items.length - 1); _highlightMentionItem(items); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); mentionSelectedIdx = Math.max(mentionSelectedIdx - 1, 0); _highlightMentionItem(items); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); const sel = items[mentionSelectedIdx]; if (sel) _insertMention(sel.dataset.name); return; }
    if (e.key === 'Escape') { e.preventDefault(); _hideMentionPopup(); return; }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send().catch(err => reportError('send keydown', err));
  }
});

function _checkMentionPopup() {
  if (!currentGroupMembers.length) { _hideMentionPopup(); return; }
  const val = input.value;
  const pos = input.selectionStart;
  // Find the @word being typed: look backwards from cursor for @
  const before = val.substring(0, pos);
  const match = before.match(/@[\\w]*$/);
  if (!match) { _hideMentionPopup(); return; }
  const query = match[0].slice(1).toLowerCase();
  const filtered = currentGroupMembers.filter(m =>
    m.name.toLowerCase().startsWith(query) || m.profile_id.toLowerCase().startsWith(query)
  );
  if (!filtered.length) { _hideMentionPopup(); return; }
  const popup = document.getElementById('mentionPopup');
  popup.innerHTML = '';
  filtered.forEach((m, i) => {
    const item = document.createElement('div');
    item.className = 'mention-item' + (i === 0 ? ' selected' : '');
    item.dataset.name = m.name || '';

    const avatar = document.createElement('span');
    avatar.className = 'mi-avatar';
    avatar.textContent = m.avatar || '';

    const name = document.createElement('span');
    name.className = 'mi-name';
    name.textContent = m.name || '';

    item.appendChild(avatar);
    item.appendChild(name);
    item.addEventListener('click', () => _insertMention(item.dataset.name || ''));
    popup.appendChild(item);
  });
  mentionSelectedIdx = 0;
  popup.classList.add('visible');
}

function _highlightMentionItem(items) {
  items.forEach((it, i) => it.classList.toggle('selected', i === mentionSelectedIdx));
}

function _insertMention(name) {
  const val = input.value;
  const pos = input.selectionStart;
  const before = val.substring(0, pos);
  const after = val.substring(pos);
  const atIdx = before.lastIndexOf('@');
  if (atIdx < 0) return;
  const newVal = before.substring(0, atIdx) + '@' + name + ' ' + after;
  input.value = newVal;
  const newPos = atIdx + name.length + 2;
  input.setSelectionRange(newPos, newPos);
  input.focus();
  _hideMentionPopup();
  refreshComposerDraftState();
}

function _hideMentionPopup() {
  const popup = document.getElementById('mentionPopup');
  if (popup) popup.classList.remove('visible');
}

async function initApp() {
  dbg(' initApp starting via', initTrigger);
  const chats = await loadChats();
  if (currentChat) {
    const current = chats.find(chat => chat.id === currentChat);
    if (current) {
      dbg(' initApp keeping current chat:', currentChat);
      await selectChat(current.id, current.title || 'Untitled');
      dbg(' initApp done, currentChat:', currentChat);
      return;
    }
  }

  if (chats.length > 0) {
    const first = chats[0];
    dbg(' initApp selecting first chat:', first.id);
    await selectChat(first.id, first.title || 'Untitled');
  } else {
    dbg(' initApp no chats, creating one');
    await newChat();
  }
  dbg(' initApp done, currentChat:', currentChat);
}

async function ensureInitialized(trigger) {
  if (initDone) {
    refreshDebugState(`init-skip:${trigger}`);
    return currentChat;
  }
  if (initPromise) {
    dbg(' init already running, trigger:', trigger);
    refreshDebugState(`init-wait:${trigger}`);
    return initPromise;
  }

  initStarted = true;
  initTrigger = trigger;
  refreshDebugState(`init-start:${trigger}`);
  initPromise = (async () => {
    try {
      await initApp();
      initDone = Boolean(currentChat);
      if (!initDone) {
        throw new Error('init completed without selecting a chat');
      }
      return currentChat;
    } catch (err) {
      dbg('ERROR: init failed:', err?.message || err);
      initStarted = false;
      initDone = false;
      throw err;
    } finally {
      initPromise = null;
      refreshDebugState(`init-finish:${trigger}`);
      updateSendBtn();
    }
  })();
  return initPromise;
}

window.addEventListener('error', (e) => {
  dbg('ERROR: window:', e.message);
  refreshDebugState('window-error');
});
window.addEventListener('unhandledrejection', (e) => {
  reportError('unhandledrejection', e.reason);
});
"""

_JS_CONTEXT_BAR = """// --- Context bar ---
function formatTokenCount(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function updateContextBar(tokensIn, threshold) {
  const bar = document.getElementById('contextBar');
  if (!bar) return;
  const pct = threshold > 0 ? Math.min((tokensIn / threshold) * 100, 100) : 0;
  const fill = document.getElementById('contextFill');
  const detail = document.getElementById('contextDetail');
  fill.style.width = pct.toFixed(1) + '%';
  fill.className = 'context-fill ' + (pct >= 80 ? 'red' : pct >= 50 ? 'orange' : 'green');
  detail.textContent = formatTokenCount(tokensIn) + ' / ' + formatTokenCount(threshold) + ' tokens (' + Math.round(pct) + '%)';
  detail.style.color = pct >= 80 ? 'var(--red)' : pct >= 50 ? 'var(--yellow)' : 'var(--dim)';
  bar.classList.add('visible');
}

async function fetchContext(chatId) {
  if (!chatId) return;
  try {
    const r = await fetch('/api/chats/' + chatId + '/context');
    if (r.ok) {
      const d = await r.json();
      updateContextBar(d.tokens_in, d.context_window);
    }
  } catch (e) { dbg('context fetch error:', e.message); }
}
"""

_JS_USAGE_BAR = """// --- Usage bar (model-aware, toggleable) ---
function usageColor(pct) { return pct >= 90 ? 'red' : pct >= 70 ? 'orange' : 'green'; }
let _usageHideTimer = null;
let _lastUsageData = null;
let _usageInterval = null;
let _lastUsageProvider = null;

function selectedChatModel() {
  if (!currentChat) return '';
  const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
  return item?.dataset?.model || document.getElementById('serverModelDisplay')?.textContent || '';
}

function isClaudeModel(model) { return typeof model === 'string' && model.startsWith('claude-'); }
function isCodexModel(model) { return typeof model === 'string' && model.startsWith('codex:'); }
function isGrokModel(model) { return typeof model === 'string' && model.startsWith('grok-'); }

function getUsageProvider() {
  const model = selectedChatModel();
  if (isClaudeModel(model)) return 'claude';
  if (isCodexModel(model)) return 'codex';
  if (isGrokModel(model)) return 'grok';
  return null;
}

// Usage meter mode: 'always' | 'auto' | 'off'
function getUsageMeterMode() {
  // Migrate old toggle key
  if (localStorage.getItem('usageMeterOff') === '1' && !localStorage.getItem('usageMeterMode')) {
    localStorage.setItem('usageMeterMode', 'off');
    localStorage.removeItem('usageMeterOff');
  }
  return localStorage.getItem('usageMeterMode') || 'auto';
}
function setUsageMeterMode(mode) { localStorage.setItem('usageMeterMode', mode); localStorage.removeItem('usageMeterOff'); }

function updateUsageBarVisibility() {
  const bar = document.getElementById('usageBar');
  if (!bar) return false;
  const provider = getUsageProvider();
  const mode = getUsageMeterMode();
  const shouldShow = currentChatType !== 'alerts' && provider !== null && mode !== 'off';
  if (!shouldShow) {
    bar.classList.remove('visible', 'fading');
    bar.style.display = 'none';
    return false;
  }
  const label = document.getElementById('usageLabel');
  if (label) label.textContent = provider === 'codex' ? 'ChatGPT' : provider === 'grok' ? 'Grok' : 'Claude';
  bar.style.display = '';
  if (mode === 'always' || (mode === 'auto' && provider !== 'claude')) {
    // Always-on mode, or auto mode for non-polling providers (Codex/Grok stay visible)
    bar.classList.add('visible');
    bar.classList.remove('fading');
    clearTimeout(_usageHideTimer);
  }
  return true;
}

function showUsageBar() {
  const bar = document.getElementById('usageBar');
  if (!bar || !_lastUsageData || !updateUsageBarVisibility()) return;
  bar.classList.add('visible');
  bar.classList.remove('fading');
  clearTimeout(_usageHideTimer);
  const mode = getUsageMeterMode();
  const provider = getUsageProvider();
  // Auto-hide only for Claude (which polls and re-shows). Codex/Grok are static — keep visible.
  if (mode === 'auto' && provider === 'claude') {
    _usageHideTimer = setTimeout(() => {
      bar.classList.add('fading');
      setTimeout(() => { bar.classList.remove('visible', 'fading'); }, 350);
    }, 5000);
  }
}

function renderUsage(data) {
  const bar = document.getElementById('usageBar');
  if (!bar || !data || !data.session) {
    if (bar) { bar.classList.remove('visible', 'fading'); bar.style.display = 'none'; }
    return;
  }
  _lastUsageData = data;
  const s = data.session, w = data.weekly;

  // Session bar — may be "N/A" for Codex
  const isNA = s.resets_in === 'N/A';
  document.getElementById('usageSessionPct').textContent = isNA ? '' : s.utilization + '%';
  document.getElementById('usageSessionReset').textContent = isNA ? 'Included' : '(' + s.resets_in + ')';
  const sf = document.getElementById('usageSessionFill');
  sf.style.width = isNA ? '0%' : Math.min(s.utilization, 100) + '%';
  sf.className = 'usage-fill ' + (isNA ? 'green' : usageColor(s.utilization));
  document.getElementById('usageSessionPct').style.color =
    isNA ? 'var(--dim)' : s.utilization >= 90 ? 'var(--red)' : s.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';

  // Weekly bar
  const wNA = w.resets_in === 'N/A';
  document.getElementById('usageWeeklyPct').textContent = wNA ? '' : w.utilization + '%';
  document.getElementById('usageWeeklyReset').textContent = wNA ? 'Flat rate' : '(' + w.resets_in + ')';
  const wf = document.getElementById('usageWeeklyFill');
  wf.style.width = wNA ? '0%' : Math.min(w.utilization, 100) + '%';
  wf.className = 'usage-fill ' + (wNA ? 'green' : usageColor(w.utilization));
  document.getElementById('usageWeeklyPct').style.color =
    wNA ? 'var(--dim)' : w.utilization >= 90 ? 'var(--red)' : w.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';

  if (updateUsageBarVisibility()) showUsageBar();
}

document.getElementById('usageBar').addEventListener('click', () => showUsageBar());

// --- Toggle: X button hides, settings control mode ---
function toggleUsageMeter() {
  setUsageMeterMode('off');
  updateUsageBarVisibility();
  const sel = document.getElementById('usageMeterSelect');
  if (sel) sel.value = 'off';
}
function changeUsageMeterMode(mode) {
  setUsageMeterMode(mode);
  updateUsageBarVisibility();
  if (mode !== 'off') startUsagePolling();
}

// --- Smart polling (only active provider) ---
async function fetchClaudeUsage() {
  try {
    const r = await fetch('/api/usage');
    if (r.ok) renderUsage(await r.json());
  } catch (e) { dbg('claude usage fetch error:', e.message); }
}

async function fetchCodexUsage() {
  try {
    const r = await fetch('/api/usage/codex');
    if (r.ok) {
      const data = await r.json();
      // Update label
      const label = document.getElementById('usageLabel');
      if (label) label.textContent = 'ChatGPT ' + (data.plan || '');
      // Render using standard renderUsage (same format as Claude)
      renderUsage(data);
      return;
    }
  } catch (e) { dbg('codex usage fetch error:', e.message); }
  // Fallback: no data yet — show placeholder
  const bar = document.getElementById('usageBar');
  if (!bar) return;
  const label = document.getElementById('usageLabel');
  if (label) label.textContent = 'ChatGPT';
  document.getElementById('usageSessionPct').textContent = '--';
  document.getElementById('usageSessionReset').textContent = 'send a message to load';
  document.querySelector('#usageSession .label').textContent = 'Session';
  document.getElementById('usageSessionFill').style.width = '0%';
  document.getElementById('usageWeeklyPct').textContent = '--';
  document.getElementById('usageWeeklyReset').textContent = '';
  document.querySelector('#usageWeekly .label').textContent = 'Weekly';
  document.getElementById('usageWeeklyFill').style.width = '0%';
  bar.style.display = '';
  bar.classList.add('visible');
  bar.classList.remove('fading');
}

async function fetchGrokUsage() {
  try {
    const r = await fetch('/api/usage/grok');
    if (!r.ok) return;
    const data = await r.json();
    const bal = data.balance_usd || 0;
    const total = data.purchased_usd || 100;
    const spent = data.spent_usd || 0;
    const pct = total > 0 ? Math.round((bal / total) * 100) : 0;

    // Use renderUsage for visibility/show logic, then override labels
    renderUsage({
      session: { utilization: pct, resets_in: '' },
      weekly: { utilization: 0, resets_in: 'N/A' },
    });

    // Override session bar to show credit balance
    const lbl = document.querySelector('#usageSession .label');
    if (lbl) lbl.textContent = 'Credits';
    const pctEl = document.getElementById('usageSessionPct');
    if (pctEl) {
      pctEl.textContent = '$' + bal.toFixed(2);
      pctEl.style.color = bal >= 20 ? 'var(--green)' : bal >= 5 ? 'var(--yellow)' : 'var(--red)';
    }
    document.getElementById('usageSessionReset').textContent = 'of $' + total.toFixed(0) + ' remaining';
    const sf = document.getElementById('usageSessionFill');
    if (sf) {
      sf.style.width = pct + '%';
      sf.className = 'usage-fill ' + (bal >= 20 ? 'green' : bal >= 5 ? 'orange' : 'red');
    }
    // Override weekly to show spent
    const wlbl = document.querySelector('#usageWeekly .label');
    if (wlbl) wlbl.textContent = 'Spent';
    document.getElementById('usageWeeklyPct').textContent = '$' + spent.toFixed(2);
    document.getElementById('usageWeeklyPct').style.color = 'var(--dim)';
    document.getElementById('usageWeeklyReset').textContent = '';
    const wf = document.getElementById('usageWeeklyFill');
    if (wf) { wf.style.width = '0%'; }
  } catch (e) { dbg('grok usage fetch error:', e.message); }
}

function startUsagePolling() {
  const provider = getUsageProvider();
  const mode = getUsageMeterMode();
  // Reset if provider changed or not yet started
  if (provider !== _lastUsageProvider || !_usageInterval) {
    _lastUsageProvider = provider;
    clearInterval(_usageInterval);
    _usageInterval = null;
    _lastUsageData = null;
    // Reset labels when switching providers
    const lbl = document.querySelector('#usageSession .label');
    if (lbl) lbl.textContent = 'Session';
  }

  if (!provider || mode === 'off') {
    updateUsageBarVisibility();
    return;
  }

  const fetchFn = provider === 'grok' ? fetchGrokUsage : provider === 'codex' ? fetchCodexUsage : fetchClaudeUsage;
  fetchFn();
  // Poll Claude and Grok (Codex is static)
  if (provider !== 'codex') {
    _usageInterval = setInterval(fetchFn, 300000);
  }
  updateUsageBarVisibility();
}
"""

_JS_PROFILES = """// --- Agent Profiles ---
let _profilesCache = [];
let _currentChatProfileId = '';
let _currentChatProfileName = '';
let _currentChatProfileAvatar = '';

async function loadProfiles() {
  try {
    const r = await fetch('/api/profiles', {credentials: 'same-origin'});
    if (r.ok) {
      const data = await r.json();
      _profilesCache = data.profiles || [];
    }
  } catch(e) { dbg('loadProfiles error:', e.message); }
  return _profilesCache;
}

async function showNewChatProfilePicker() {
  // Remove any existing modal
  document.querySelector('.profile-modal-overlay')?.remove();

  // Refresh Ollama model list so we have current availability
  try {
    const r = await fetch('/api/models/local', {credentials: 'same-origin'});
    if (r.ok) _settingsModels = await r.json();
  } catch(e) {}

  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  let selectedProfileId = '';
  let selectedModel = '';
  const modal = document.createElement('div');
  modal.className = 'profile-modal';

  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>New Channel</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  // Quick Thread button at top
  const threadBtn = document.createElement('div');
  threadBtn.style.cssText = 'padding:12px 16px;border-bottom:1px solid var(--bg);cursor:pointer;display:flex;align-items:center;gap:10px';
  threadBtn.innerHTML = '<span style="font-size:18px">\u26A1</span><div><div style="font-weight:600;font-size:14px">Quick Thread</div><div style="font-size:12px;color:var(--dim)">Lightweight one-off interaction</div></div>';
  threadBtn.onmouseenter = () => { threadBtn.style.background = 'var(--card)'; };
  threadBtn.onmouseleave = () => { threadBtn.style.background = ''; };
  threadBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newThread().catch(err => reportError('newThread', err));
  };
  modal.appendChild(threadBtn);

  // New Group button (premium-gated)
  fetch('/api/features', {credentials: 'same-origin'}).then(r => r.json()).then(f => {
    if (!f.groups_enabled) return;
    const groupBtn = document.createElement('div');
    groupBtn.style.cssText = 'padding:12px 16px;border-bottom:1px solid var(--bg);cursor:pointer;display:flex;align-items:center;gap:10px';
    groupBtn.innerHTML = '<span style="font-size:18px">👥</span><div><div style="font-weight:600;font-size:14px">New Group</div><div style="font-size:12px;color:var(--dim)">Multi-agent collaboration</div></div>';
    groupBtn.onmouseenter = () => { groupBtn.style.background = 'var(--card)'; };
    groupBtn.onmouseleave = () => { groupBtn.style.background = ''; };
    groupBtn.onclick = () => { overlay.remove(); showNewGroupPicker(); };
    threadBtn.after(groupBtn);
  }).catch(() => {});

  const body = document.createElement('div');
  body.className = 'profile-modal-body';

  function getNewChatModelOptions() {
    const cloudModels = [
      {id: 'claude-opus-4-7', name: 'Claude Opus 4.7'},
      {id: 'claude-opus-4-6', name: 'Claude Opus 4.6'},
      {id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6'},
      {id: 'claude-haiku-4-5-20251001', name: 'Claude Haiku 4.5'},
      {id: 'grok-4', name: 'Grok 4'},
      {id: 'grok-4-fast', name: 'Grok 4 Fast'},
      {id: 'codex:gpt-5.4', name: 'GPT-5.4'},
      {id: 'codex:gpt-5.4-mini', name: 'GPT-5.4 Mini'},
      {id: 'codex:gpt-5.3-codex', name: 'GPT-5.3'},
      {id: 'codex:gpt-5.2', name: 'GPT-5.2'},
      {id: 'codex:gpt-5.1-codex-max', name: 'GPT-5.1 Max'},
    ];
    const localModels = (_settingsModels || []).map(m => ({
      id: m.id,
      name: m.displayName || m.id,
      local: true,
    }));
    return cloudModels.concat(localModels);
  }

  function defaultNewChatModel() {
    const preferred = (document.getElementById('serverModelDisplay')?.textContent || '').trim();
    const options = getNewChatModelOptions();
    return options.some(m => m.id === preferred) ? preferred : (options[0]?.id || 'claude-sonnet-4-6');
  }

  selectedModel = defaultNewChatModel();

  function renderCards() {
    body.innerHTML = '';
    const hasCustomProfiles = _profilesCache.some(p => !p.is_system);
    if (!hasCustomProfiles) {
      const guide = document.createElement('div');
      guide.style.cssText = 'margin:0 0 12px;padding:14px 16px;background:var(--card);border-radius:12px;border-left:3px solid var(--accent)';
      guide.innerHTML = '<div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px">' +
        '\uD83C\uDFAD Personas make Apex yours</div>' +
        '<div style="font-size:12px;color:var(--dim);line-height:1.5;margin-bottom:10px">' +
        'Create custom personas with their own personality, system prompt, and model. ' +
        'Each channel can have a different persona.</div>' +
        '<a href="/admin/#personas" target="_blank" style="font-size:12px;color:var(--accent);' +
        'text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:4px">' +
        'Set up personas \u2192</a>';
      body.appendChild(guide);
    }
    if (_profilesCache.length === 0) {
      body.insertAdjacentHTML('beforeend', '<div style="padding:12px;color:var(--dim);font-size:13px">No agent profiles configured. Creating a plain channel.</div>');
    }
    const noProfileCard = document.createElement('div');
    noProfileCard.className = 'profile-card' + (!selectedProfileId ? ' selected' : '');
    let noProfileHtml = `<div class="profile-avatar">💬</div>
      <div class="profile-info">
        <div class="profile-name">No Profile</div>
        <div class="profile-role">Plain chat with no persona assigned</div>
        <div class="profile-model">Use chat model directly</div>`;
    if (!selectedProfileId) {
      const options = getNewChatModelOptions();
      const localStart = options.findIndex(m => m.local);
      const selectOptions = options.map((m, idx) => {
        const separator = localStart === idx ? '<option disabled>── Local Models ──</option>' : '';
        return separator + `<option value="${escHtml(m.id)}"${m.id === selectedModel ? ' selected' : ''}>${escHtml(m.name)}</option>`;
      }).join('');
      noProfileHtml += `
        <div style="margin-top:10px;">
          <label style="display:block;font-size:12px;font-weight:600;color:var(--dim);margin-bottom:6px;">Model</label>
          <select id="newChatModelSelect" style="width:100%;padding:10px 12px;background:var(--surface);border:1px solid var(--bg);border-radius:10px;color:var(--fg);">
            ${selectOptions}
          </select>
          <div style="margin-top:6px;font-size:12px;color:var(--dim);">Pick the model before creating the chat.</div>
        </div>`;
    }
    noProfileHtml += `</div>`;
    noProfileCard.innerHTML = noProfileHtml;
    noProfileCard.onclick = () => {
      selectedProfileId = '';
      renderCards();
    };
    body.appendChild(noProfileCard);
    if (!selectedProfileId) {
      const sel = noProfileCard.querySelector('#newChatModelSelect');
      if (sel) {
        sel.onclick = (e) => e.stopPropagation();
        sel.onchange = () => { selectedModel = sel.value; };
      }
    }
    const ollamaAvailable = _settingsModels.length > 0;
    _profilesCache.forEach(p => {
      const isLocal = (p.backend === 'ollama' || p.backend === 'mlx');
      const unavailable = isLocal && !ollamaAvailable;
      const card = document.createElement('div');
      card.className = 'profile-card' + (selectedProfileId === p.id ? ' selected' : '') + (unavailable ? ' unavailable' : '');
      card.innerHTML = `<div class="profile-avatar">${escHtml(p.avatar || '💬')}</div>
        <div class="profile-info">
          <div class="profile-name">${escHtml(p.name)}${unavailable ? ' <span style="font-size:11px;color:var(--dim);font-weight:normal">(Ollama not running)</span>' : ''}</div>
          <div class="profile-role">${escHtml(p.role_description || '')}</div>
          <div class="profile-model">${escHtml(p.model || 'default')}</div>
        </div>`;
      if (unavailable) {
        card.style.opacity = '0.4';
        card.style.pointerEvents = 'none';
      } else {
        card.onclick = () => {
          selectedProfileId = selectedProfileId === p.id ? '' : p.id;
          renderCards();
        };
      }
      body.appendChild(card);
    });

    const newPersonaLink = document.createElement('button');
    newPersonaLink.type = 'button';
    newPersonaLink.className = 'profile-modal-new-persona';
    newPersonaLink.textContent = '+ New Persona';
    newPersonaLink.onclick = () => {
      overlay.remove();
      window.open('/admin/#personas', '_blank');
    };
    body.appendChild(newPersonaLink);
  }
  renderCards();
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'profile-modal-actions';
  const skipBtn = document.createElement('button');
  skipBtn.className = 'btn-skip';
  skipBtn.textContent = 'Cancel';
  skipBtn.onclick = () => overlay.remove();
  actions.appendChild(skipBtn);

  const createBtn = document.createElement('button');
  createBtn.className = 'btn-create';
  createBtn.textContent = 'Create Channel';
  createBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newChatWithProfile(selectedProfileId, selectedProfileId ? '' : selectedModel).catch(err => reportError('newChat profile', err));
  };
  actions.appendChild(createBtn);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

async function newChatWithProfile(profileId, model) {
  dbg(' creating new chat with profile:', profileId || '(none)', 'model:', model || '(default)');
  const payload = {};
  if (profileId) payload.profile_id = profileId;
  if (!profileId && model) payload.model = model;
  const body = Object.keys(payload).length ? JSON.stringify(payload) : undefined;
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: body ? {'Content-Type': 'application/json'} : {},
    body: body
  });
  if (!r.ok) {
    dbg('ERROR: newChatWithProfile failed:', r.status);
    throw new Error('newChatWithProfile failed: ' + r.status);
  }
  const data = await r.json();
  dbg(' created chat:', data.id, 'profile:', data.profile_name || '(none)');
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'New Channel');
  refreshDebugState('newChatWithProfile');
  return data.id;
}

async function newThread() {
  dbg(' creating new thread...');
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'thread'})
  });
  if (!r.ok) {
    dbg('ERROR: newThread failed:', r.status);
    throw new Error('newThread failed: ' + r.status);
  }
  const data = await r.json();
  dbg(' created thread:', data.id);
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'Quick thread', 'thread');
  refreshDebugState('newThread');
  return data.id;
}

function showNewGroupPicker() {
  document.querySelector('.profile-modal-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  const modal = document.createElement('div');
  modal.className = 'profile-modal';
  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>New Group</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const titleInput = document.createElement('input');
  titleInput.type = 'text';
  titleInput.placeholder = 'Group name...';
  titleInput.value = '';
  titleInput.style.cssText = 'width:100%;padding:10px 16px;border:none;border-bottom:1px solid var(--bg);background:var(--surface);color:var(--fg);font-size:14px;box-sizing:border-box';
  modal.appendChild(titleInput);

  const body = document.createElement('div');
  body.className = 'profile-modal-body';
  body.style.maxHeight = '300px';
  const selectedMembers = new Map();

  function render() {
    body.innerHTML = '';
    if (_profilesCache.length === 0) {
      body.innerHTML = '<div style="padding:12px;color:var(--dim);font-size:13px">No agent profiles to add.</div>';
      return;
    }
    _profilesCache.forEach(p => {
      const card = document.createElement('div');
      card.className = 'profile-card' + (selectedMembers.has(p.id) ? ' selected' : '');
      const mode = selectedMembers.get(p.id) || '';
      const badge = mode === 'primary' ? ' 👑' : (mode ? ' ✓' : '');
      card.innerHTML = `<div class="profile-avatar">${escHtml(p.avatar || '💬')}</div>
        <div class="profile-info"><div class="profile-name">${escHtml(p.name)}${badge}</div>
        <div class="profile-role">${escHtml(p.role_description || '')}</div></div>`;
      card.onclick = () => {
        if (!selectedMembers.has(p.id)) {
          selectedMembers.set(p.id, 'mentioned');
        } else if (selectedMembers.get(p.id) === 'mentioned') {
          selectedMembers.set(p.id, 'primary');
          // Only one primary
          selectedMembers.forEach((v, k) => { if (k !== p.id && v === 'primary') selectedMembers.set(k, 'mentioned'); });
        } else {
          selectedMembers.delete(p.id);
        }
        render();
      };
      body.appendChild(card);
    });
  }
  const hint = document.createElement('div');
  hint.style.cssText = 'padding:8px 16px;font-size:11px;color:var(--dim);border-bottom:1px solid var(--bg)';
  hint.textContent = 'Click once = member, twice = primary (crown), third = remove';
  modal.appendChild(hint);

  render();
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'profile-modal-actions';
  const createBtn = document.createElement('button');
  createBtn.className = 'btn-create';
  createBtn.textContent = 'Create Group';
  createBtn.onclick = async () => {
    if (selectedMembers.size === 0) return;
    const members = [];
    selectedMembers.forEach((mode, pid) => members.push({profile_id: pid, routing_mode: mode}));
    if (!members.some(m => m.routing_mode === 'primary') && members.length > 0) {
      members[0].routing_mode = 'primary';
    }
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newGroup(titleInput.value.trim() || 'New Group', members).catch(err => reportError('newGroup', err));
  };
  actions.appendChild(createBtn);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

async function newGroup(title, members) {
  dbg(' creating new group:', title, members);
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'group', title: title, members: members})
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    dbg('ERROR: newGroup failed:', r.status, err);
    throw new Error('newGroup failed: ' + r.status + ' ' + (err.error || ''));
  }
  const data = await r.json();
  dbg(' created group:', data.id);
  const chats = await loadChats();
  await selectChat(data.id, title, 'group');
  refreshDebugState('newGroup');
  return data.id;
}
"""

_JS_GROUP_SETTINGS = """// --- Group Settings Modal ---
async function showGroupSettings() {
  if (!currentChat || currentChatType !== 'group') return;
  const chatId = currentChat;
  document.getElementById('settingsPanel')?.classList.remove('show');

  // Remove any existing modal
  document.querySelector('.profile-modal-overlay')?.remove();

  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  const modal = document.createElement('div');
  modal.className = 'profile-modal';
  modal.style.maxWidth = '520px';

  // Header
  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>Group Settings</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const body = document.createElement('div');
  body.className = 'profile-modal-body';
  body.style.padding = '0';

  // State
  let members = [];
  let settings = {};
  let addMode = false;
  let activeTab = 'channel';

  // Fetch data
  async function loadData() {
    try {
      const [mr, sr] = await Promise.all([
        fetch(`/api/chats/${chatId}/members`, {credentials: 'same-origin'}),
        fetch(`/api/chats/${chatId}/settings`, {credentials: 'same-origin'})
      ]);
      if (mr.ok) { const d = await mr.json(); members = d.members || []; }
      if (sr.ok) { const d = await sr.json(); settings = d.settings || {}; }
    } catch(e) { dbg('group settings load error:', e); }
  }

  function gsToast(msg) {
    let t = document.querySelector('.gs-toast');
    if (!t) { t = document.createElement('div'); t.className = 'gs-toast'; document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 2000);
  }

  function renderRelayStatus(relayState) {
    if (!relayState) return null;
    const card = document.createElement('div');
    card.className = 'gs-relay-status';
    if (relayState.active !== true) {
      const stepHint = relayState && relayState.step_mode
        ? 'One agent per message — you speak between each turn.'
        : 'Agents will respond one at a time.';
      card.innerHTML = `<div class="gs-relay-ready"><div class="gs-relay-ready-icon">◎</div><div><div class="gs-relay-ready-title">Ready</div><div class="gs-relay-ready-copy">Relay starts on your next message.<br>${stepHint}</div></div></div>`;
      return card;
    }
    const agents = Array.isArray(relayState.agents) ? relayState.agents : [];
    const completed = agents.filter(a => a.status === 'responded' || a.status === 'abstained').length;
    const total = agents.length;
    const pct = total > 0 ? Math.max(0, Math.min(100, (completed / total) * 100)) : 0;
    const statusMeta = {
      responded: { icon: '✓', label: 'responded', cls: 'is-responded' },
      abstained: { icon: '⊘', label: 'passed', cls: 'is-abstained' },
      next: { icon: '▸', label: 'up next', cls: 'is-next' },
      paused: { icon: '⏸', label: 'your turn', cls: 'is-paused' },
      waiting: { icon: '○', label: 'waiting', cls: 'is-waiting' },
    };
    const rows = agents.map(agent => {
      const meta = statusMeta[agent.status] || statusMeta.waiting;
      return `<div class="gs-relay-agent ${meta.cls}"><div class="gs-relay-agent-emoji">${escHtml(agent.emoji || '🤖')}</div><div class="gs-relay-agent-icon">${meta.icon}</div><div class="gs-relay-agent-name">${escHtml(agent.name || agent.profile_id || 'Agent')}</div><div class="gs-relay-agent-label">${meta.label}</div></div>`;
    }).join('');
    const pausedBanner = relayState.paused
      ? '<div class="gs-relay-paused">Waiting for you — send a message to continue</div>'
      : '';
    card.innerHTML = `<div class="gs-relay-header"><div class="gs-relay-round">Round ${Number(relayState.round_number || 1)} <span class="gs-relay-round-max">· ${Number(relayState.max_rounds || 10)} max</span></div><div class="gs-relay-count">${completed}/${total}</div></div><div class="gs-relay-progress"><div class="gs-relay-progress-fill" style="width:${pct}%"></div></div>${pausedBanner}<div class="gs-relay-agents">${rows}</div>`;
    return card;
  }

  function renderTabs() {
    const tabs = document.createElement('div');
    tabs.className = 'gs-tabs';
    [
      ['channel', 'Channel'],
      ['preferences', 'Preferences'],
    ].forEach(([key, label]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'gs-tab' + (activeTab === key ? ' active' : '');
      btn.textContent = label;
      btn.onclick = () => {
        if (activeTab === key) return;
        activeTab = key;
        render();
      };
      tabs.appendChild(btn);
    });
    return tabs;
  }

  function renderPreferencesTab(content) {
    const appearanceSection = document.createElement('div');
    appearanceSection.className = 'gs-section';
    appearanceSection.innerHTML = `<div class="gs-section-title">Appearance</div>`;

    const textCard = document.createElement('div');
    textCard.className = 'gs-pref-card';
    const textRow = document.createElement('div');
    textRow.className = 'gs-pref-row';
    textRow.innerHTML = `<div>
      <div class="gs-pref-label">Text Size</div>
      <div class="gs-pref-hint">Applies across all chats and groups.</div>
    </div>`;
    const textValue = document.createElement('div');
    textValue.className = 'gs-pref-value';
    textRow.appendChild(textValue);
    textCard.appendChild(textRow);

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'gs-range';
    slider.min = '70';
    slider.max = '200';
    slider.step = '10';
    textCard.appendChild(slider);

    const resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'gs-inline-btn';
    resetBtn.textContent = 'Reset to Default';
    textCard.appendChild(resetBtn);

    function syncTextControls() {
      const percent = Math.round(chatFontScale * 100);
      slider.value = String(percent);
      textValue.textContent = `${percent}%`;
      resetBtn.style.display = chatFontScale === 1 ? 'none' : 'inline-block';
    }

    slider.oninput = () => {
      setChatFontScale(Number(slider.value) / 100);
      syncTextControls();
    };
    resetBtn.onclick = () => {
      setChatFontScale(1);
      syncTextControls();
    };
    syncTextControls();
    appearanceSection.appendChild(textCard);
    content.appendChild(appearanceSection);

    const usageSection = document.createElement('div');
    usageSection.className = 'gs-section';
    usageSection.innerHTML = `<div class="gs-section-title">Usage</div>`;

    const usageCard = document.createElement('div');
    usageCard.className = 'gs-pref-card';
    const usageLabel = document.createElement('div');
    usageLabel.className = 'gs-pref-label';
    usageLabel.textContent = 'Usage Meter';
    usageCard.appendChild(usageLabel);

    const usageHint = document.createElement('div');
    usageHint.className = 'gs-pref-hint';
    usageCard.appendChild(usageHint);

    const usageSelect = document.createElement('select');
    usageSelect.className = 'gs-select';
    usageSelect.innerHTML = `
      <option value="always">Always visible</option>
      <option value="auto">Auto-hide (5s)</option>
      <option value="off">Off</option>`;
    usageCard.appendChild(usageSelect);

    function syncUsageControls() {
      usageSelect.value = getUsageMeterMode();
      const provider = getUsageProvider();
      const providerName = provider === 'codex' ? 'ChatGPT' : provider === 'grok' ? 'Grok' : provider === 'claude' ? 'Claude' : '';
      usageHint.textContent = providerName
        ? `Controls the ${providerName} usage bar above the conversation.`
        : 'Shows the usage bar when the current model supports usage data.';
    }

    usageSelect.onchange = () => {
      changeUsageMeterMode(usageSelect.value);
      syncUsageControls();
    };
    syncUsageControls();
    usageSection.appendChild(usageCard);
    content.appendChild(usageSection);
  }

  function renderChannelTab(content) {
    const sidebarItem = document.querySelector(`.chat-item[data-id="${chatId}"]`);
    const currentTitle = sidebarItem?.dataset?.title || 'Group';

    // --- Channel Name ---
    const nameSection = document.createElement('div');
    nameSection.className = 'gs-section';
    nameSection.innerHTML = `<div class="gs-section-title">Channel Name</div>`;
    const nameInput = document.createElement('input');
    nameInput.className = 'gs-name-input';
    nameInput.type = 'text';
    nameInput.value = currentTitle;
    let nameTimer = null;
    nameInput.oninput = () => {
      clearTimeout(nameTimer);
      nameTimer = setTimeout(async () => {
        const val = nameInput.value.trim();
        if (!val || val === currentTitle) return;
        try {
          await fetch(`/api/chats/${chatId}`, {
            method: 'PATCH', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: val})
          });
          if (sidebarItem) {
            sidebarItem.dataset.title = val;
            const titleEl = sidebarItem.querySelector('.chat-item-title');
            if (titleEl) titleEl.textContent = val;
          }
          document.getElementById('chatTitle').textContent = val;
        } catch(e) { dbg('rename error:', e); }
      }, 600);
    };
    nameSection.appendChild(nameInput);
    content.appendChild(nameSection);

    // --- Members ---
    const memSection = document.createElement('div');
    memSection.className = 'gs-section';
    memSection.innerHTML = `<div class="gs-section-title">Members (${members.length})</div>`;

    members.forEach(m => {
      const row = document.createElement('div');
      row.className = 'gs-member';
      const primary = m.is_primary || m.routing_mode === 'primary';
      const modelName = m.model || 'default';
      row.innerHTML = `
        <div class="gs-member-avatar">${escHtml(m.avatar || '🤖')}${primary ? '<div class="gs-crown">★</div>' : ''}</div>
        <div class="gs-member-info">
          <div class="gs-member-name">${escHtml(m.name)}</div>
          <div class="gs-member-model">${escHtml(modelName)}</div>
        </div>`;

      // Routing mode badge (clickable toggle)
      const badge = document.createElement('button');
      badge.className = 'gs-member-badge ' + (primary ? 'primary' : 'mentioned');
      badge.textContent = primary ? 'Primary' : 'Mentioned';
      badge.onclick = async () => {
        const newMode = primary ? 'mentioned' : 'primary';
        try {
          const resp = await fetch(`/api/chats/${chatId}/members/${m.profile_id || m.id}`, {
            method: 'PATCH', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({routing_mode: newMode})
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            gsToast(err.error || 'Role update failed');
            return;
          }
          gsToast(`${m.name} → ${newMode}`);
          await loadData();
          render();
        } catch(e) { dbg('update member error:', e); }
      };
      row.appendChild(badge);

      // Remove button
      const rmBtn = document.createElement('button');
      rmBtn.className = 'gs-member-remove';
      rmBtn.innerHTML = '&times;';
      rmBtn.title = 'Remove member';
      rmBtn.onclick = async () => {
        if (!confirm(`Remove ${m.name} from this group?`)) return;
        try {
          await fetch(`/api/chats/${chatId}/members/${m.profile_id || m.id}`, {
            method: 'DELETE', credentials: 'same-origin'
          });
          gsToast(`${m.name} removed`);
          await loadData();
          render();
          const sub = sidebarItem?.querySelector('.chat-item-subtitle');
          if (sub) sub.textContent = `Group · ${members.length} members`;
        } catch(e) { dbg('remove member error:', e); }
      };
      row.appendChild(rmBtn);
      memSection.appendChild(row);
    });

    if (addMode) {
      const picker = document.createElement('div');
      picker.className = 'gs-add-picker';
      const existingIds = new Set(members.map(m => m.profile_id || m.id));
      const available = _profilesCache.filter(p => !existingIds.has(p.id));
      if (available.length === 0) {
        picker.innerHTML = '<div style="padding:8px 10px;font-size:12px;color:var(--dim)">All personas are already members.</div>';
      } else {
        available.forEach(p => {
          const card = document.createElement('div');
          card.className = 'profile-card';
          card.innerHTML = `<div class="profile-avatar">${escHtml(p.avatar || '💬')}</div>
            <div class="profile-info"><div class="profile-name">${escHtml(p.name)}</div>
            <div class="profile-role">${escHtml(p.role_description || '')}</div></div>`;
          card.onclick = async () => {
            try {
              await fetch(`/api/chats/${chatId}/members`, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profile_id: p.id, routing_mode: 'mentioned'})
              });
              addMode = false;
              gsToast(`${p.name} added`);
              await loadData();
              render();
              const sub = sidebarItem?.querySelector('.chat-item-subtitle');
              if (sub) sub.textContent = `Group · ${members.length} members`;
            } catch(e) { dbg('add member error:', e); }
          };
          picker.appendChild(card);
        });
      }
      const cancelBtn = document.createElement('button');
      cancelBtn.className = 'gs-add-btn';
      cancelBtn.textContent = 'Cancel';
      cancelBtn.style.justifyContent = 'center';
      cancelBtn.onclick = () => { addMode = false; render(); };
      memSection.appendChild(picker);
      memSection.appendChild(cancelBtn);
    } else {
      const addBtn = document.createElement('button');
      addBtn.className = 'gs-add-btn';
      addBtn.innerHTML = '<span style="font-size:16px">+</span> Add Member';
      addBtn.onclick = () => { addMode = true; render(); };
      memSection.appendChild(addBtn);
    }
    content.appendChild(memSection);

    const setSection = document.createElement('div');
    setSection.className = 'gs-section';
    setSection.innerHTML = `<div class="gs-section-title">Settings</div>`;

    const mentionRow = document.createElement('div');
    mentionRow.className = 'gs-toggle-row';
    const mentionOn = settings.agent_mentions_enabled === true;
    mentionRow.innerHTML = `<span class="gs-toggle-label">Agent @Mentions</span>`;
    const toggle = document.createElement('button');
    toggle.className = 'gs-toggle ' + (mentionOn ? 'on' : 'off');
    toggle.onclick = async () => {
      const newVal = !mentionOn;
      try {
        await fetch(`/api/chats/${chatId}/settings`, {
          method: 'PATCH', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({agent_mentions_enabled: newVal})
        });
        settings.agent_mentions_enabled = newVal;
        gsToast(newVal ? '@Mentions enabled' : '@Mentions disabled');
        render();
      } catch(e) { dbg('setting update error:', e); }
    };
    mentionRow.appendChild(toggle);
    setSection.appendChild(mentionRow);

    const mentionHint = document.createElement('div');
    mentionHint.className = 'gs-toggle-hint';
    mentionHint.textContent = 'When enabled, agents can @mention other members to invoke them automatically.';
    setSection.appendChild(mentionHint);

    const arRow = document.createElement('div');
    arRow.className = 'gs-toggle-row';
    arRow.style.borderTop = '1px solid var(--bg)';
    arRow.style.paddingTop = '10px';
    arRow.style.marginTop = '6px';
    const arOn = settings.auto_reply === true;
    arRow.innerHTML = `<div><span class="gs-toggle-label">Auto-Reply</span>
      <div class="gs-toggle-hint" style="margin-top:2px">Non-primary agents can respond without @mention when relevant</div></div>`;
    const arToggle = document.createElement('button');
    arToggle.className = 'gs-toggle ' + (arOn ? 'on' : 'off');
    arToggle.onclick = async () => {
      const newVal = !arOn;
      try {
        await fetch(`/api/chats/${chatId}/settings`, {
          method: 'PATCH', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({auto_reply: newVal})
        });
        settings.auto_reply = newVal;
        gsToast(newVal ? 'Auto-reply enabled' : 'Auto-reply disabled');
        render();
      } catch(e) { dbg('setting update error:', e); }
    };
    arRow.appendChild(arToggle);
    setSection.appendChild(arRow);

    const smRow = document.createElement('div');
    smRow.className = 'gs-toggle-row';
    smRow.style.borderTop = '1px solid var(--bg)';
    smRow.style.paddingTop = '10px';
    smRow.style.marginTop = '6px';
    const smOn = settings.shared_memory !== false;
    smRow.innerHTML = `<div><span class="gs-toggle-label">Shared Memory</span>
      <div class="gs-toggle-hint" style="margin-top:2px">Agents share decisions across all their groups</div></div>`;
    const smToggle = document.createElement('button');
    smToggle.className = 'gs-toggle ' + (smOn ? 'on' : 'off');
    smToggle.onclick = async () => {
      const newVal = !smOn;
      try {
        await fetch(`/api/chats/${chatId}/settings`, {
          method: 'PATCH', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({shared_memory: newVal})
        });
        settings.shared_memory = newVal;
        gsToast(newVal ? 'Shared memory enabled' : 'Shared memory disabled');
        render();
      } catch(e) { dbg('setting update error:', e); }
    };
    smRow.appendChild(smToggle);
    setSection.appendChild(smRow);

    const seqRow = document.createElement('div');
    seqRow.className = 'gs-toggle-row';
    seqRow.style.borderTop = '1px solid var(--bg)';
    seqRow.style.paddingTop = '10px';
    seqRow.style.marginTop = '6px';
    const seqOn = settings.coordination_protocol === 'sequential';
    const relayState = settings.relay_state || null;
    const seqCopy = document.createElement('div');
    seqCopy.className = 'gs-toggle-copy';
    seqCopy.innerHTML = `<span class="gs-toggle-label">Sequential Relay</span>
      <div class="gs-toggle-hint" style="margin-top:2px">Agents take turns in order. Each one sees all prior responses before adding theirs.</div>`;
    seqRow.appendChild(seqCopy);
    const seqToggle = document.createElement('button');
    seqToggle.className = 'gs-toggle ' + (seqOn ? 'on' : 'off');
    seqToggle.onclick = async () => {
      const newVal = seqOn ? 'freeform' : 'sequential';
      if (seqOn && relayState && relayState.active === true) {
        const confirmed = confirm("End the active relay? Agents who haven't responded will be skipped.");
        if (!confirmed) return;
      }
      try {
        const resp = await fetch(`/api/chats/${chatId}/settings`, {
          method: 'PATCH', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({coordination_protocol: newVal})
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          gsToast(err.error || 'Setting update failed');
          return;
        }
        const payload = await resp.json().catch(() => ({}));
        settings = payload.settings || settings;
        settings.coordination_protocol = newVal;
        gsToast(newVal === 'sequential' ? 'Sequential relay enabled' : 'Freeform routing enabled');
        render();
      } catch(e) { dbg('setting update error:', e); }
    };
    seqRow.appendChild(seqToggle);
    setSection.appendChild(seqRow);

    if (seqOn) {
      const stepRow = document.createElement('div');
      stepRow.className = 'gs-toggle-row';
      stepRow.style.borderTop = '1px solid var(--bg)';
      stepRow.style.paddingTop = '10px';
      stepRow.style.marginTop = '6px';
      const stepOn = !!settings.relay_step_mode;
      const stepCopy = document.createElement('div');
      stepCopy.className = 'gs-toggle-copy';
      stepCopy.innerHTML = `<span class="gs-toggle-label">Human in the Loop</span>
        <div class="gs-toggle-hint" style="margin-top:2px">One agent responds per message. You speak between each agent turn.</div>`;
      stepRow.appendChild(stepCopy);
      const stepToggle = document.createElement('button');
      stepToggle.className = 'gs-toggle ' + (stepOn ? 'on' : 'off');
      stepToggle.onclick = async () => {
        const newStepVal = !stepOn;
        try {
          const resp = await fetch(`/api/chats/${chatId}/settings`, {
            method: 'PATCH', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({relay_step_mode: newStepVal})
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            gsToast(err.error || 'Setting update failed');
            return;
          }
          const payload = await resp.json().catch(() => ({}));
          settings = payload.settings || settings;
          settings.relay_step_mode = newStepVal;
          gsToast(newStepVal ? 'Human-in-the-loop enabled' : 'Auto-relay restored');
          render();
        } catch(e) { dbg('setting update error:', e); }
      };
      stepRow.appendChild(stepToggle);
      setSection.appendChild(stepRow);
    }

    const relayCard = renderRelayStatus(relayState);
    if (relayCard) setSection.appendChild(relayCard);

    content.appendChild(setSection);

    const dangerSection = document.createElement('div');
    dangerSection.className = 'gs-danger';
    const delBtn = document.createElement('button');
    delBtn.className = 'gs-danger-btn';
    delBtn.textContent = 'Delete Channel';
    delBtn.onclick = async () => {
      if (!confirm(`Delete "${currentTitle}"? This will remove all messages and cannot be undone.`)) return;
      overlay.remove();
      const ok = await deleteChat(chatId);
      if (!ok) gsToast('Failed to delete channel');
    };
    dangerSection.appendChild(delBtn);
    content.appendChild(dangerSection);
  }

  function render() {
    body.innerHTML = '';
    body.appendChild(renderTabs());
    const content = document.createElement('div');
    content.className = 'gs-pane';
    if (activeTab === 'preferences') {
      renderPreferencesTab(content);
    } else {
      renderChannelTab(content);
    }
    body.appendChild(content);
  }

  await loadData();
  render();
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const origRemove = overlay.remove.bind(overlay);
  overlay.remove = () => {
    origRemove();
    if (currentChat === chatId && currentChatType === 'group') {
      fetch(`/api/chats/${chatId}/members`, {credentials: 'same-origin'})
        .then(r => r.ok ? r.json() : {members: []})
        .then(d => { currentGroupMembers = d.members || []; })
        .catch(() => {});
    }
  };
}

function updateTopbarProfile(profileName, profileAvatar) {
  const el = document.getElementById('topbarProfile');
  const avatarEl = document.getElementById('topbarProfileAvatar');
  const nameEl = document.getElementById('topbarProfileName');
  if (!el) return;
  _currentChatProfileName = profileName || '';
  _currentChatProfileAvatar = profileAvatar || '';
  if (currentChatType === 'group') {
    avatarEl.textContent = '💬';
    nameEl.textContent = 'Group';
    el.style.display = '';
    el.onclick = null;
  } else if (profileName) {
    avatarEl.textContent = profileAvatar || '💬';
    nameEl.textContent = profileName;
    el.style.display = '';
    el.onclick = (e) => showProfileDropdown(e);
  } else {
    avatarEl.textContent = '💬';
    nameEl.textContent = 'No Profile';
    el.style.display = currentChatType === 'chat' ? '' : 'none';
    el.onclick = (e) => showProfileDropdown(e);
  }
}

const CHAT_PERMISSION_PRESETS = [
  {
    key: 'diagnostics',
    label: 'Diagnostics',
    commands: ['echo', 'date', 'grep', 'rg', 'find', 'ls', 'cat', 'head', 'tail', 'sed', 'awk', 'cut', 'sort', 'uniq', 'tr', 'wc', 'ps', 'lsof', 'curl', 'stat', 'file', 'realpath', 'basename', 'dirname', 'printenv', 'env'],
  },
  {
    key: 'repo',
    label: 'Repo Ops',
    commands: ['git status', 'git diff', 'git log', 'git show', 'git branch', 'git rev-parse', 'git grep', 'git ls-files', 'git remote', 'git describe', 'git blame'],
  },
  {
    key: 'python-db',
    label: 'Python + DB',
    commands: ['python3', 'python3 -m py_compile', 'pytest', 'sqlite3'],
  },
  {
    key: 'system',
    label: 'System',
    commands: ['pgrep', 'kill', 'tmux', 'sleep', 'uname', 'whoami', 'id', 'df', 'du', 'ss', 'netstat'],
  },
];

function describeChatToolPolicy(policy) {
  const level = Number((policy && policy.level) || 2);
  if (level <= 0) return 'Restricted';
  if (level === 1) return 'Standard Tools';
  if (level === 2) return 'Workspace Tools';
  if (level === 3) return 'Admin Allowlist';
  if (level >= 4) return 'Full Admin';
  return 'Admin Allowlist';
}

async function showDirectChatPermissions() {
  if (!currentChat || currentChatType !== 'chat' || _currentChatProfileId) return;
  document.querySelector('.profile-dropdown')?.remove();
  document.querySelector('.profile-modal-overlay')?.remove();

  const toast = (msg) => {
    let t = document.querySelector('.gs-toast');
    if (!t) {
      t = document.createElement('div');
      t.className = 'gs-toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 2000);
  };

  let policy = {
    level: 2,
    default_level: 2,
    elevated_until: null,
    invoke_policy: 'anyone',
    allowed_commands: [],
  };
  try {
    const resp = await fetch(`/api/chats/${currentChat}/tool-policy`, {credentials: 'same-origin'});
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.tool_policy) policy = data.tool_policy;
    } else {
      toast('Failed to load chat permissions');
      return;
    }
  } catch (e) {
    reportError('showDirectChatPermissions', e);
    toast('Failed to load chat permissions');
    return;
  }

  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  const modal = document.createElement('div');
  modal.className = 'profile-modal';
  modal.style.maxWidth = '560px';

  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>Chat Permissions</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const body = document.createElement('div');
  body.className = 'profile-modal-body';
  body.innerHTML = `
    <div style="display:grid;gap:14px">
      <div style="font-size:13px;color:var(--dim);line-height:1.5">
        Applies only to this direct chat while <strong>No Profile</strong> is selected.
      </div>
      <label style="display:grid;gap:6px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Permission Level</span>
        <select id="chat-perm-level" class="gs-select">
          <option value="0">Restricted</option>
          <option value="1">Standard Tools</option>
          <option value="2">Workspace Tools</option>
          <option value="3">Admin Allowlist</option>
          <option value="4">Full Admin</option>
        </select>
      </label>
      <div style="display:grid;gap:8px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Preset Bundles</span>
        <div id="chat-perm-presets" style="display:flex;gap:8px;flex-wrap:wrap"></div>
        <span style="font-size:12px;color:var(--dim)">Built from common debugging commands seen in prior Apex sessions. Presets append to the allowlist.</span>
      </div>
      <label style="display:grid;gap:6px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Allowed Commands</span>
        <textarea id="chat-perm-commands" class="gs-name-input" rows="5" placeholder="One command prefix per line, e.g.&#10;git push&#10;sqlite3"></textarea>
        <span id="chat-perm-help" style="font-size:12px;color:var(--dim)">Used only for Admin Allowlist. Bash commands must start with one of these prefixes.</span>
      </label>
      <label style="display:grid;gap:6px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Temporary Admin Minutes</span>
        <input id="chat-perm-minutes" class="gs-name-input" type="number" min="1" max="1440" placeholder="15" />
        <span id="chat-perm-expiry" style="font-size:12px;color:var(--dim)"></span>
      </label>
      <div id="chat-perm-status" style="font-size:12px;color:var(--dim);min-height:18px"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">
        <button id="chat-perm-revoke" class="gs-inline-btn" type="button">Reset to Default</button>
        <button id="chat-perm-save" class="gs-add-btn" type="button" style="margin:0">Save</button>
      </div>
    </div>`;

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const levelEl = body.querySelector('#chat-perm-level');
  const presetsEl = body.querySelector('#chat-perm-presets');
  const commandsEl = body.querySelector('#chat-perm-commands');
  const helpEl = body.querySelector('#chat-perm-help');
  const minutesEl = body.querySelector('#chat-perm-minutes');
  const expiryEl = body.querySelector('#chat-perm-expiry');
  const statusEl = body.querySelector('#chat-perm-status');
  const saveBtn = body.querySelector('#chat-perm-save');
  const revokeBtn = body.querySelector('#chat-perm-revoke');
  const defaultLevel = Number(policy.default_level || 2);
  const presetButtons = [];

  function setStatus(text, tone = 'dim') {
    statusEl.textContent = text || '';
    if (tone === 'success') statusEl.style.color = '#10b981';
    else if (tone === 'error') statusEl.style.color = '#ef4444';
    else if (tone === 'warning') statusEl.style.color = '#f59e0b';
    else statusEl.style.color = 'var(--dim)';
  }

  function setBusy(busy, label = 'Save') {
    saveBtn.disabled = !!busy;
    revokeBtn.disabled = !!busy;
    levelEl.disabled = !!busy;
    commandsEl.disabled = !!busy;
    minutesEl.disabled = !!busy;
    presetButtons.forEach((btn) => { btn.disabled = !!busy; });
    saveBtn.textContent = busy ? `${label}…` : 'Save';
  }

  function syncExpiryText() {
    if (policy.elevated_until) {
      expiryEl.textContent = `Current expiry: ${new Date(policy.elevated_until).toLocaleString()}`;
    } else {
      expiryEl.textContent = `Default level: ${describeChatToolPolicy({level: defaultLevel})}`;
    }
  }

  function currentCommandList() {
    return commandsEl.value
      .split('\\n')
      .map(v => v.trim())
      .filter(Boolean);
  }

  function setCommandList(items) {
    const deduped = [];
    const seen = new Set();
    items.forEach((item) => {
      const value = String(item || '').trim();
      if (!value || seen.has(value)) return;
      seen.add(value);
      deduped.push(value);
    });
    commandsEl.value = deduped.join('\\n');
  }

  function syncPolicyUi() {
    const level = Number(levelEl.value || defaultLevel);
    const allowlistMode = level === 3;
    const fullAdminMode = level >= 4;
    commandsEl.disabled = fullAdminMode;
    presetsEl.style.opacity = allowlistMode ? '1' : '0.6';
    presetButtons.forEach((btn) => { btn.disabled = fullAdminMode; });
    if (fullAdminMode) {
      helpEl.textContent = 'Full Admin bypasses the command allowlist and file/path restrictions. Use a temporary expiry whenever possible.';
    } else if (allowlistMode) {
      helpEl.textContent = 'Used only for Admin Allowlist. Bash commands must start with one of these prefixes.';
    } else {
      helpEl.textContent = 'Allowed Commands are ignored unless Permission Level is Admin Allowlist.';
    }
  }

  CHAT_PERMISSION_PRESETS.forEach((preset) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'gs-inline-btn';
    btn.style.margin = '0';
    btn.textContent = preset.label;
    btn.onclick = () => {
      const merged = [...currentCommandList(), ...preset.commands];
      setCommandList(merged);
      setStatus(`Added ${preset.label} preset`, 'success');
    };
    presetButtons.push(btn);
    presetsEl.appendChild(btn);
  });

  levelEl.value = String(Number(policy.level || defaultLevel));
  commandsEl.value = (policy.allowed_commands || []).join('\\n');
  minutesEl.value = '';
  syncExpiryText();
  syncPolicyUi();
  setStatus(`Current policy: ${describeChatToolPolicy(policy)}`);

  levelEl.onchange = () => {
    syncPolicyUi();
    setStatus(`Editing ${describeChatToolPolicy({level: Number(levelEl.value || defaultLevel)})}`, 'dim');
  };

  revokeBtn.onclick = async () => {
    setBusy(true, 'Resetting');
    setStatus('Resetting chat permissions…');
    try {
      const resp = await fetch(`/api/chats/${currentChat}/tool-policy/revoke`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      policy = data.tool_policy || policy;
      levelEl.value = String(Number(policy.level || defaultLevel));
      commandsEl.value = (policy.allowed_commands || []).join('\\n');
      minutesEl.value = '';
      syncExpiryText();
      syncPolicyUi();
      setStatus(`Reset to ${describeChatToolPolicy(policy)}`, 'success');
      toast('Chat permissions reset');
    } catch (e) {
      reportError('revokeChatToolPolicy', e);
      setStatus('Failed to reset chat permissions', 'error');
      toast('Failed to reset chat permissions');
    } finally {
      setBusy(false);
      syncPolicyUi();
    }
  };

  saveBtn.onclick = async () => {
    const level = Number(levelEl.value || defaultLevel);
    const minutes = Number(minutesEl.value || 0);
    const allowedCommands = commandsEl.value
      .split('\\n')
      .map(v => v.trim())
      .filter(Boolean);
    let elevatedUntil = null;
    if (level > defaultLevel && minutes > 0) {
      elevatedUntil = new Date(Date.now() + minutes * 60 * 1000).toISOString();
    }
    const payload = {
      level,
      default_level: defaultLevel,
      elevated_until: elevatedUntil,
      invoke_policy: policy.invoke_policy || 'anyone',
      allowed_commands: allowedCommands,
    };
    setBusy(true, 'Saving');
    setStatus('Saving chat permissions…');
    try {
      const resp = await fetch(`/api/chats/${currentChat}/tool-policy`, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      policy = data.tool_policy || payload;
      levelEl.value = String(Number(policy.level || defaultLevel));
      commandsEl.value = (policy.allowed_commands || []).join('\\n');
      syncExpiryText();
      syncPolicyUi();
      setStatus(`Saved. Current policy: ${describeChatToolPolicy(policy)}`, 'success');
      toast(`Chat permissions saved: ${describeChatToolPolicy(policy)}`);
    } catch (e) {
      reportError('saveChatToolPolicy', e);
      setStatus('Failed to save chat permissions', 'error');
      toast('Failed to save chat permissions');
    } finally {
      setBusy(false);
      syncPolicyUi();
    }
  };
}

function showProfileDropdown(event) {
  event.stopPropagation();
  if (currentChatType !== 'chat') return;
  // Remove existing dropdown
  document.querySelector('.profile-dropdown')?.remove();

  if (_profilesCache.length === 0) return;

  const btn = document.getElementById('topbarProfile');
  const rect = btn.getBoundingClientRect();
  const dd = document.createElement('div');
  dd.className = 'profile-dropdown';
  dd.style.top = (rect.bottom + 4) + 'px';
  dd.style.left = Math.max(8, rect.left - 60) + 'px';

  // "None" option
  const noneItem = document.createElement('div');
  noneItem.className = 'pd-item';
  noneItem.innerHTML = '<span class="pd-avatar">💬</span><span class="pd-name">No Profile</span>' +
    (!_currentChatProfileId ? '<span class="pd-check">✓</span>' : '');
  noneItem.onclick = () => { dd.remove(); changeChatProfile(''); };
  dd.appendChild(noneItem);

  if (!_currentChatProfileId) {
    const permissionsItem = document.createElement('div');
    permissionsItem.className = 'pd-item';
    permissionsItem.innerHTML = '<span class="pd-avatar">🛡️</span><span class="pd-name">Chat Permissions…</span>';
    permissionsItem.onclick = () => { dd.remove(); showDirectChatPermissions(); };
    dd.appendChild(permissionsItem);
  }

  _profilesCache.forEach(p => {
    const item = document.createElement('div');
    item.className = 'pd-item';
    item.innerHTML = `<span class="pd-avatar">${escHtml(p.avatar || '💬')}</span><span class="pd-name">${escHtml(p.name)}</span>` +
      (_currentChatProfileId === p.id ? '<span class="pd-check">✓</span>' : '');
    item.onclick = () => { dd.remove(); changeChatProfile(p.id); };
    dd.appendChild(item);
  });

  document.body.appendChild(dd);
  // Close on any click outside
  setTimeout(() => {
    const closer = (e) => {
      if (!dd.contains(e.target)) { dd.remove(); document.removeEventListener('click', closer); }
    };
    document.addEventListener('click', closer);
  }, 0);
}

async function changeChatProfile(profileId) {
  if (!currentChat || currentChatType !== 'chat') return;
  try {
    const r = await fetch('/api/chats/' + currentChat, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({profile_id: profileId})
    });
    if (r.ok) {
      dbg('changed profile for chat:', currentChat, 'to:', profileId || '(none)');
      // Update local state
      _currentChatProfileId = profileId;
      const profile = _profilesCache.find(p => p.id === profileId);
      updateTopbarProfile(profile?.name || '', profile?.avatar || '');
      await loadChats();
    }
  } catch(e) {
    reportError('changeChatProfile', e);
  }
}
"""

_JS_PERSONA_CARD = """// --- Persona Info Card (F-1) ---
// Opens a popover on desktop or a bottom sheet on mobile when a
// speaker header (agent name/avatar in message) is clicked.

function _isMobile() {
  return window.matchMedia('(max-width: 599px)').matches;
}

function _closePic() {
  document.querySelector('.pic-backdrop')?.remove();
  document.querySelector('.pic-popover')?.remove();
  document.querySelector('.pic-sheet')?.remove();
}

function showPersonaInfoCard(profileId, anchorEl) {
  _closePic();
  const profile = _profilesCache.find(p => p.id === profileId);
  // Graceful fallback: use data from the speaker header itself if profile not found
  let name = '', avatar = '', role = '', model = '', bio = '';
  if (profile) {
    name   = profile.name || '';
    avatar = profile.avatar || '';
    role   = profile.role_description || '';
    model  = profile.model || '';
    bio    = profile.role_description || '';
  } else if (anchorEl) {
    // Extract from DOM when profile not in cache (e.g. stale cache)
    name   = anchorEl.querySelector('.speaker-name')?.textContent?.trim() || '';
    avatar = anchorEl.querySelector('.speaker-avatar')?.textContent?.trim() || '';
  }
  if (!name) return; // nothing to show

  const mobile = _isMobile();

  // Backdrop
  const backdrop = document.createElement('div');
  backdrop.className = 'pic-backdrop' + (mobile ? ' bs-mode' : '');
  backdrop.onclick = _closePic;
  document.body.appendChild(backdrop);

  // Card element
  const card = document.createElement('div');
  card.className = mobile ? 'pic-sheet' : 'pic-popover';
  card.onclick = (e) => e.stopPropagation();

  card.innerHTML =
    (mobile ? '<div class="pic-drag-handle"></div>' : '') +
    '<div class="pic-header">' +
      '<div class="pic-avatar-big">' + escHtml(avatar) + '</div>' +
      '<div class="pic-name-block">' +
        '<div class="pic-name">' + escHtml(name) + '</div>' +
        (role ? '<div class="pic-role">' + escHtml(role) + '</div>' : '') +
        (model ? '<div class="pic-model">' + escHtml(model) + '</div>' : '') +
      '</div>' +
    '</div>' +
    (bio
      ? '<div class="pic-body"><div class="pic-bio">' + escHtml(bio) + '</div></div>'
      : '') +
    '<div class="pic-actions">' +
      '<button class="pic-btn pic-btn-message">Message</button>' +
      '<button class="pic-btn pic-btn-edit">Edit</button>' +
    '</div>';

  // Wire buttons
  card.querySelector('.pic-btn-message').onclick = () => {
    _closePic();
    const input = document.getElementById('input');
    if (!input) return;
    if (profile) {
      // In a group chat, prepend @mention; in a solo chat, just focus
      if (currentChatType === 'group' && name) {
        const mention = '@' + name + ' ';
        if (!input.value.startsWith('@' + name)) {
          input.value = mention + input.value;
          input.dispatchEvent(new Event('input'));
        }
      }
    }
    input.focus();
  };

  card.querySelector('.pic-btn-edit').onclick = () => {
    _closePic();
    // Navigate to admin profile editor — open in same tab
    const pid = profile?.id || profileId || '';
    window.open('/admin/#personas' + (pid ? '/' + encodeURIComponent(pid) : ''), '_blank');
  };

  document.body.appendChild(card);

  // Desktop: position as popover anchored to clicked element
  if (!mobile && anchorEl) {
    const rect = anchorEl.getBoundingClientRect();
    const cardW = 280;
    let left = rect.left;
    let top  = rect.bottom + 6;
    // Clamp to viewport
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (left + cardW > vw - 8) left = vw - cardW - 8;
    if (left < 8) left = 8;
    // Rough card height estimate; flip up if not enough room below
    const estH = 200;
    if (top + estH > vh - 8) top = rect.top - estH - 6;
    if (top < 8) top = 8;
    card.style.left = left + 'px';
    card.style.top  = top  + 'px';
  }
}

// Delegate click on messages container — catches both history and streaming bubbles
document.getElementById('messages').addEventListener('click', (e) => {
  const header = e.target.closest('.speaker-header');
  if (!header) return;
  const profileId = header.dataset.profileId || '';
  showPersonaInfoCard(profileId, header);
});

// Load profiles at startup
loadProfiles();

applyTheme();
applyChatFontScale();
applySidebarPinnedState();
// B-41 diagnostic: log viewport info to help debug responsive breakpoint issues
console.log('[B41] viewport:', window.innerWidth, 'x', window.innerHeight, 'DPR:', devicePixelRatio, 'mobile:', _isMobile());
// Init usage meter mode from localStorage
(function() {
  const sel = document.getElementById('usageMeterSelect');
  if (sel) sel.value = getUsageMeterMode();
})();
startUsagePolling();

connect();
setTimeout(() => { ensureInitialized('timer-fallback').catch(() => {}); }, 1500);
refreshDebugState('boot');
updateSendBtn();

// --- PWA resume: reconnect when app comes back from background ---
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    updateLastAlertCheck(new Date().toISOString());
    lastAlertFetchSince = '';
  } else if (document.visibilityState === 'visible') {
    // Only reconnect if the ws is actually dead. Safari keeps ws alive
    // through brief background periods; forcing reconnect every tab switch
    // tears down in-flight streams and loses buffered events.
    const wsDead = !ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED;
    if (wsDead) {
      dbg('app resumed from background, ws dead, reconnecting');
      resumeConnection('visibilitychange');
    } else {
      dbg('app resumed from background, ws alive, keeping it');
    }
  }
});

// iOS pageshow fires on back/forward cache restore
window.addEventListener('pageshow', (e) => {
  const wsDead = !ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED;
  if (e.persisted) {
    dbg(`pageshow: bfcache restore, wsDead=${wsDead}`);
    resumeConnection('pageshow');
  } else if (wsDead) {
    dbg('pageshow: non-bfcache show with dead WS, forcing reconnect');
    resumeConnection('pageshow');
  }
});

// --- Pull to refresh (PWA has no reload button) ---
let pullStartY = 0;
let pulling = false;
const msgEl = document.getElementById('messages');
msgEl.addEventListener('touchstart', (e) => {
  if (msgEl.scrollTop <= 0) {
    pullStartY = e.touches[0].clientY;
    pulling = true;
  }
}, {passive: true});
msgEl.addEventListener('touchmove', (e) => {
  if (!pulling) return;
  const dy = e.touches[0].clientY - pullStartY;
  if (dy > 120 && msgEl.scrollTop <= 0) {
    pulling = false;
    dbg('pull-to-refresh triggered');
    window.location.reload();
  }
}, {passive: true});
msgEl.addEventListener('touchend', () => {
  pulling = false;
}, {passive: true});
msgEl.addEventListener('touchcancel', () => {
  pulling = false;
}, {passive: true});

// P2: Wire static element event handlers (replaces all inline onclick/onchange attributes)
(function _wireStaticHandlers() {
  function wire() {
    const _w = (id, evt, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(evt, fn); };
    _w('topbarProfile',    'click',  (e) => showProfileDropdown(e));
    _w('alertBadge',       'click',  () => toggleAlertsPanel());
    _w('settingsBtn',      'click',  () => toggleSettings());
    _w('refreshBtn',       'click',  () => window.location.reload());
    _w('clearAlertsBtn',   'click',  () => clearAllAlerts());
    _w('settingsCloseBtn', 'click',  () => toggleSettings());
    _w('chatModelSelect',  'change', (e) => changeChatModel(e.target.value));
    _w('usageMeterSelect', 'change', (e) => changeUsageMeterMode(e.target.value));
    _w('usageToggle',      'click',  (e) => { e.stopPropagation(); toggleUsageMeter(); });
    _w('spCloseBtn',       'click',  () => closeSidePanel());
    _w('spBackdrop',       'click',  () => closeSidePanel());
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();"""

# --- Computer-use (GUI automation) frontend module ---
# Inlined into CHAT_JS (no separate static route) to match the existing
# chat_js.py pattern — every frontend module is a Python string constant
# joined into CHAT_JS and served by chat_html.py at page render time.
_JS_COMPUTER_USE = """// --- Computer-use (GUI automation) client module ---
// Renders screenshots inline in the tool panel and provides pause/resume UI
// for the per-chat GUI-control toggle. Exposed globals consumed by
// openToolPanel: cuRenderScreenshot, cuMountPauseButton.

// Tracks last GUI-tool activity per chat for auto-hiding the pause button.
const _cuLastActivity = {};  // chat_id -> ms timestamp
const _cuPauseState = {};    // chat_id -> 'active' | 'paused'
const _cuButtonEls = {};     // chat_id -> button element

function cuRenderScreenshot(block, priorClickCoords) {
  // Builds the <img> (+ optional red-dot overlay) HTML string. The overlay
  // uses percentage coords so it scales correctly with the displayed img,
  // whose natural size is what the agent captured.
  if (!block || !block.source || !block.source.data) return '';
  const mt = (block.source.media_type || 'image/png').replace(/[^a-zA-Z0-9/+.-]/g, '');
  const src = `data:${mt};base64,${block.source.data}`;
  const imgHtml = `<img class="cu-screenshot" src="${src}" alt="screenshot" style="display:block;max-width:100%;width:100%;border-radius:6px;cursor:zoom-in;">`;
  if (!priorClickCoords || typeof priorClickCoords.x !== 'number' || typeof priorClickCoords.y !== 'number') {
    return imgHtml;
  }
  // The red-dot position is computed at render time against the image's
  // natural dimensions, so we need an onload handler. We embed a tiny
  // inline script via data-* attrs and wire up from openToolPanel's
  // delegated handlers — but simpler: compute on the img's load event.
  const cx = priorClickCoords.x;
  const cy = priorClickCoords.y;
  // Return a wrapper with the img + a dot positioned via a load callback.
  // The dot starts hidden; a post-mount hook (see cuWireOverlays) sets
  // its absolute pixel position once the image has measured.
  return `<div class="cu-shot-wrap" style="position:relative;display:inline-block;max-width:100%;" data-cu-click-x="${cx}" data-cu-click-y="${cy}">${imgHtml}<span class="cu-click-dot" style="position:absolute;width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff;box-shadow:0 0 6px rgba(239,68,68,0.9);display:none;pointer-events:none;transform:translate(-50%,-50%);"></span></div>`;
}

// Post-render: position click dots once their image has measured.
function cuWireOverlays(rootEl) {
  if (!rootEl) return;
  rootEl.querySelectorAll('.cu-shot-wrap').forEach((wrap) => {
    const img = wrap.querySelector('img.cu-screenshot');
    const dot = wrap.querySelector('.cu-click-dot');
    if (!img || !dot) return;
    const cx = parseFloat(wrap.getAttribute('data-cu-click-x'));
    const cy = parseFloat(wrap.getAttribute('data-cu-click-y'));
    if (!isFinite(cx) || !isFinite(cy)) return;
    const place = () => {
      const nw = img.naturalWidth || 0;
      const nh = img.naturalHeight || 0;
      if (!nw || !nh) return;
      const dw = img.clientWidth || img.offsetWidth || 0;
      const dh = img.clientHeight || img.offsetHeight || 0;
      if (!dw || !dh) return;
      const scaleX = dw / nw;
      const scaleY = dh / nh;
      dot.style.left = (cx * scaleX) + 'px';
      dot.style.top  = (cy * scaleY) + 'px';
      dot.style.display = 'block';
    };
    if (img.complete) place();
    else img.addEventListener('load', place, {once: true});
    // Reposition on window resize so the dot tracks the responsive img.
    window.addEventListener('resize', place);
  });
}

async function cuEnableForChat(chatId, targetBundleId) {
  if (!chatId) return null;
  const r = await fetch(`/api/chats/${chatId}/computer_use/enable`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({target_bundle_id: targetBundleId}),
  });
  return r.ok ? r.json() : null;
}

async function cuDisableForChat(chatId) {
  if (!chatId) return null;
  const r = await fetch(`/api/chats/${chatId}/computer_use/disable`, {
    method: 'POST', credentials: 'same-origin',
  });
  return r.ok ? r.json() : null;
}

async function cuPause(chatId) {
  if (!chatId) return null;
  const r = await fetch(`/api/chats/${chatId}/computer_use/pause`, {
    method: 'POST', credentials: 'same-origin',
  });
  _cuPauseState[chatId] = 'paused';
  // Surface the persistent header banner immediately — without this, if the
  // current tool pill ages out or a new turn renders without re-mounting the
  // inline button, the user has no way to resume from the UI.
  try { cuEnsurePauseBanner(chatId, true); } catch (e) { /* non-fatal */ }
  return r.ok ? r.json() : null;
}

async function cuResume(chatId) {
  if (!chatId) return null;
  const r = await fetch(`/api/chats/${chatId}/computer_use/resume`, {
    method: 'POST', credentials: 'same-origin',
  });
  _cuPauseState[chatId] = 'active';
  // Remove the header banner now that we're active again.
  try { cuEnsurePauseBanner(chatId, false); } catch (e) { /* non-fatal */ }
  return r.ok ? r.json() : null;
}

async function cuGetStatus(chatId) {
  if (!chatId) return null;
  const r = await fetch(`/api/chats/${chatId}/computer_use/status`, {
    credentials: 'same-origin',
  });
  return r.ok ? r.json() : null;
}

function cuMountPauseButton(toolPillEl, chatId) {
  if (!toolPillEl || !chatId) return;
  // Record activity; used to auto-hide 60s after last GUI tool.
  _cuLastActivity[chatId] = Date.now();
  // If a button is already attached to this pill, just keep it visible.
  const existing = _cuButtonEls[chatId];
  if (existing && existing.isConnected && existing._pillEl === toolPillEl) {
    existing.style.display = '';
    return;
  }
  // A stale button from a previous turn's pill would otherwise linger
  // forever (auto-hide ticker skips paused buttons). Evict it from DOM
  // before we create the replacement on the current turn's pill.
  if (existing && existing.isConnected && existing._pillEl !== toolPillEl) {
    try { existing.remove(); } catch (e) { /* non-fatal */ }
  }
  // Local-const capture of DOM elements — avoid mutable globals in handler.
  const pillEl = toolPillEl;
  const cid = chatId;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'cu-pause-btn';
  btn.style.cssText = 'margin-left:8px;padding:4px 10px;border-radius:999px;background:#ef4444;color:#fff;border:none;font-size:12px;cursor:pointer;font-weight:600;';
  const setLabel = (paused) => {
    btn.textContent = paused ? '\\u25B6 Resume GUI' : '\\u23F8 Pause GUI';
    btn.style.background = paused ? '#22c55e' : '#ef4444';
  };
  setLabel(_cuPauseState[cid] === 'paused');
  // Sync label from server truth — in-memory _cuPauseState is lost on page
  // refresh, but the flag file on disk persists. Without this, after a
  // reload the button shows "Pause" even though the server is still paused,
  // and clicking it would POST /pause (no-op) instead of /resume.
  cuGetStatus(cid).then((st) => {
    if (!st) return;
    _cuPauseState[cid] = st.paused ? 'paused' : 'active';
    setLabel(!!st.paused);
  }).catch(() => {});
  btn.addEventListener('click', async (ev) => {
    ev.stopPropagation();  // don't open/close the tool panel
    const wasPaused = _cuPauseState[cid] === 'paused';
    btn.disabled = true;
    try {
      if (wasPaused) {
        await cuResume(cid);
        setLabel(false);
      } else {
        await cuPause(cid);
        setLabel(true);
      }
    } finally {
      btn.disabled = false;
    }
  });
  btn._pillEl = pillEl;
  _cuButtonEls[cid] = btn;
  // Insert the button right after the pill (sibling, not child — so
  // pill onclick keeps its own hit area).
  if (pillEl.parentNode) {
    pillEl.parentNode.insertBefore(btn, pillEl.nextSibling);
  }
  // Auto-hide 60s after last activity — a single shared ticker, cheap enough.
  // EXCEPTION: never auto-hide while paused; otherwise user loses the only
  // way to resume from the UI once the tool pill ages out.
  if (!cuMountPauseButton._ticker) {
    cuMountPauseButton._ticker = setInterval(() => {
      const now = Date.now();
      for (const k of Object.keys(_cuButtonEls)) {
        const b = _cuButtonEls[k];
        const last = _cuLastActivity[k] || 0;
        const paused = _cuPauseState[k] === 'paused';
        if (b && b.isConnected && !paused && (now - last) > 60000) {
          b.style.display = 'none';
        }
      }
    }, 5000);
  }
}

// Persistent resume banner: when a chat has computer_use enabled AND is
// paused, surface a resume pill in the chat header even when no tool pill
// is visible. Solves the "paused → no new tool calls → button ages out →
// no way to unpause from UI" dead-end.
function cuEnsurePauseBanner(chatId, paused) {
  if (!chatId) return;
  // Anchor: the chat title element (always present while a chat is open).
  const anchor = document.getElementById('chatTitle');
  if (!anchor || !anchor.parentNode) return;
  let banner = document.getElementById('cuPauseBanner');
  if (!paused) {
    if (banner) banner.remove();
    return;
  }
  if (!banner) {
    banner = document.createElement('button');
    banner.id = 'cuPauseBanner';
    banner.type = 'button';
    banner.style.cssText = 'margin-left:10px;padding:4px 12px;border-radius:999px;background:#22c55e;color:#fff;border:none;font-size:12px;cursor:pointer;font-weight:600;vertical-align:middle;';
    banner.textContent = '\\u25B6 Resume GUI';
    banner.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      banner.disabled = true;
      try {
        await cuResume(chatId);
        banner.remove();
        // Also sync the inline tool-pill button label if present.
        const b = _cuButtonEls[chatId];
        if (b && b.isConnected) {
          b.textContent = '\\u23F8 Pause GUI';
          b.style.background = '#ef4444';
        }
      } finally {
        banner.disabled = false;
      }
    });
    anchor.parentNode.insertBefore(banner, anchor.nextSibling);
  }
}

// Called from setCurrentChat — syncs the resume banner with server truth
// whenever the user switches to (or reloads) a chat.
async function cuSyncPauseUI(chatId) {
  if (!chatId) return;
  try {
    const st = await cuGetStatus(chatId);
    if (!st) return;
    _cuPauseState[chatId] = st.paused ? 'paused' : 'active';
    // Only show the banner if computer_use is actually enabled for this chat
    // (no target bundle = no GUI automation, banner would be meaningless).
    cuEnsurePauseBanner(chatId, st.enabled && st.paused);
  } catch (e) { /* non-fatal */ }
}

// Expose as window globals so openToolPanel (rendered from a different
// Python string constant) can reach them.
window.cuRenderScreenshot = cuRenderScreenshot;
window.cuWireOverlays = cuWireOverlays;
window.cuEnableForChat = cuEnableForChat;
window.cuDisableForChat = cuDisableForChat;
window.cuPause = cuPause;
window.cuResume = cuResume;
window.cuGetStatus = cuGetStatus;
window.cuMountPauseButton = cuMountPauseButton;
window.cuEnsurePauseBanner = cuEnsurePauseBanner;
window.cuSyncPauseUI = cuSyncPauseUI;
"""

CHAT_JS = "\n".join([
    _JS_ERROR_HANDLER,
    _JS_STATE,
    _JS_STREAM_CONTEXT,
    _JS_STOP_MENU,
    _JS_DEBUG,
    _JS_STREAM_WATCHDOG,
    _JS_STREAM_ATTACH,
    _JS_WEBSOCKET,
    _JS_TOOL_HELPERS,
    _JS_STREAM_UI,
    _JS_SIDE_PANEL,
    _JS_EVENT_HANDLER,
    _JS_UI_HELPERS,
    _JS_SCROLL,
    _JS_ALERTS,
    _JS_SETTINGS,
    _JS_MARKDOWN,
    _JS_COMPOSER,
    _JS_CHATS,
    _JS_SIDEBAR,
    _JS_ATTACHMENTS,
    _JS_INIT,
    _JS_CONTEXT_BAR,
    _JS_USAGE_BAR,
    _JS_PROFILES,
    _JS_GROUP_SETTINGS,
    _JS_PERSONA_CARD,
    _JS_COMPUTER_USE,
])
