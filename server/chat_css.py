# Auto-extracted from chat_html.py during modular split.

CHAT_CSS = r"""*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0F172A;--surface:#1E293B;--card:#334155;--text:#F1F5F9;--dim:#94A3B8;
--accent:#0EA5E9;--green:#10B981;--red:#EF4444;--yellow:#F59E0B;
--nav-bg:#141C2B;--nav-card:rgba(255,255,255,0.04);--nav-card-active:rgba(14,165,233,0.08);
--nav-card-hover:rgba(255,255,255,0.06);--nav-divider:rgba(255,255,255,0.04);
--nav-accent-glow:0 0 20px rgba(14,165,233,0.15);
--panel-bg:#1A1A2E;--panel-border:#333;--panel-text:#E5E7EB;--panel-muted:#888;
--panel-input-bg:#111827;--debug-bg:#111827;--debug-border:#233047;--debug-state:#93C5FD;--debug-log:#A7F3D0;
--sat:env(safe-area-inset-top);--sab:env(safe-area-inset-bottom);--sidebar-width:min(300px,80vw);
--chat-font-scale:1}
body{background:var(--bg);color:var(--text);font-family:-apple-system,system-ui,sans-serif;
height:100dvh;display:flex;flex-direction:column;overflow:hidden}
body.theme-light{--bg:#F8FAFC;--surface:#FFFFFF;--card:#D8E1EB;--text:#0F172A;--dim:#64748B;
--accent:#0284C7;--green:#059669;--red:#DC2626;--yellow:#D97706;
--nav-bg:#F1F4F9;--nav-card:rgba(0,0,0,0.03);--nav-card-active:rgba(2,132,199,0.07);
--nav-card-hover:rgba(0,0,0,0.05);--nav-divider:rgba(0,0,0,0.04);
--nav-accent-glow:0 0 20px rgba(2,132,199,0.1);
--panel-bg:#FFFFFF;--panel-border:#CBD5E1;--panel-text:#0F172A;--panel-muted:#64748B;
--panel-input-bg:#F8FAFC;--debug-bg:#E2E8F0;--debug-border:#CBD5E1;--debug-state:#1D4ED8;--debug-log:#047857}

/* Top bar */
.topbar{background:var(--surface);padding:12px 16px;padding-top:calc(12px + var(--sat));
display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--card);min-height:52px;flex-shrink:0;
transition:margin-left .2s ease}
.topbar h1{font-size:16px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
cursor:pointer;user-select:none;border-radius:6px;padding:2px 6px;margin:-2px -6px;transition:background .12s}
.topbar h1:hover{background:var(--card)}
.status{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.status.ok{background:var(--green)}
.status.err{background:var(--red)}
.mode-badge{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:600;flex-shrink:0}
.mode-badge.trusted{background:#7F1D1D;color:#FCA5A5}
.mode-badge.guarded{background:#064E3B;color:#6EE7B7}
.mode-badge.mtls{background:#1D4ED8;color:#DBEAFE}
.btn-icon{background:none;border:none;color:var(--dim);font-size:20px;cursor:pointer;padding:4px 8px;min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center}
.banner-ok{background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.25);color:#34D399}
.banner-warn{background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.25);color:#F59E0B}
.banner-critical{background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.25);color:#EF4444}
body.theme-light .banner-ok{color:#047857}
body.theme-light .banner-warn{color:#B45309}
body.theme-light .banner-critical{color:#B91C1C}

/* Messages */
.messages{flex:1;overflow-y:auto;padding:12px 16px;-webkit-overflow-scrolling:touch;transition:margin-left .2s ease}
.msg{margin-bottom:12px;max-width:85%;-webkit-user-select:text;user-select:text}
.msg.user{margin-left:auto;background:var(--accent);color:white;padding:10px 14px;
border-radius:16px 16px 4px 16px;font-size:calc(15px * var(--chat-font-scale));line-height:1.4;word-break:break-word}
.msg.user .msg-text{white-space:pre-wrap}
.msg.user a,.msg.user a:visited{color:white!important;text-decoration-color:rgba(255,255,255,.85)}
.msg.assistant{margin-right:auto}
.msg.assistant .bubble{background:var(--surface);padding:10px 14px;
border-radius:16px 16px 16px 4px;font-size:calc(15px * var(--chat-font-scale));line-height:1.5;word-break:break-word}
.msg.assistant .bubble code{background:var(--card);padding:1px 4px;border-radius:3px;font-size:calc(13px * var(--chat-font-scale))}
.msg.assistant .bubble pre{background:var(--bg);padding:10px;border-radius:6px;overflow-x:auto;
margin:8px 0;font-size:calc(13px * var(--chat-font-scale));line-height:1.4}
.msg.assistant .bubble pre code{background:none;padding:0}
.msg.assistant .bubble h2,.msg.assistant .bubble h3,.msg.assistant .bubble h4{line-height:1.3;margin:10px 0 6px}
.msg.assistant .bubble h2{font-size:calc(1.5em * var(--chat-font-scale))}
.msg.assistant .bubble h3{font-size:calc(1.3em * var(--chat-font-scale))}
.msg.assistant .bubble h4{font-size:calc(1.1em * var(--chat-font-scale))}
.msg.assistant .bubble p + p,.msg.assistant .bubble p + ul,.msg.assistant .bubble p + ol,
.msg.assistant .bubble ul + p,.msg.assistant .bubble ol + p,.msg.assistant .bubble pre + p{margin-top:8px}
.msg.assistant .bubble ul,.msg.assistant .bubble ol{padding-left:20px;margin:8px 0}
.msg.assistant .bubble li + li{margin-top:4px}
.msg-attachments{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.msg-attachments:first-child{margin-top:0}
.msg-attachment{position:relative;display:flex;align-items:center;justify-content:center;
min-width:140px;min-height:120px;max-width:100%;border-radius:8px;overflow:hidden;
background:rgba(148,163,184,0.12);border:1px solid rgba(148,163,184,0.2)}
.msg.user .msg-attachment{background:rgba(255,255,255,0.14);border-color:rgba(255,255,255,0.2)}
.msg-attachment::before{content:'';position:absolute;inset:0;
background:linear-gradient(90deg,transparent,rgba(255,255,255,0.12),transparent);
transform:translateX(-100%);animation:attShimmer 1.5s ease-in-out infinite}
.msg-attachment.is-loaded::before,.msg-attachment.is-file::before{display:none}
.msg-attachment.is-loaded{min-width:0;min-height:0}
.msg-attachment img{display:block;max-width:min(280px,100%);max-height:240px;width:auto;height:auto;
object-fit:cover;aspect-ratio:auto;border-radius:8px;cursor:pointer;opacity:0;transition:opacity .18s ease}
.msg-attachment.is-loaded img{opacity:1}
.msg-attachment.is-file{min-width:0;min-height:0;background:none;border:none;overflow:visible}
.msg-file-pill{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:4px;
border:1px solid var(--card);background:var(--bg);color:var(--text);text-decoration:none;
font-family:'SF Mono','Fira Code',monospace;font-size:11px;line-height:1.4}
.msg.user .msg-file-pill{border-color:rgba(255,255,255,0.22);background:rgba(15,23,42,0.22);color:white}
.msg-file-pill .msg-file-size{opacity:.72}
.image-viewer-overlay{position:fixed;inset:0;z-index:400;background:rgba(2,6,23,.92);
display:flex;align-items:center;justify-content:center;padding:max(16px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) max(16px,env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left))}
.image-viewer-content{position:relative;display:flex;align-items:center;justify-content:center;
width:100%;height:100%;max-width:min(100vw - 32px, 1100px);max-height:100vh}
.image-viewer-image{display:block;max-width:100%;max-height:100%;width:auto;height:auto;
border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.45);cursor:zoom-out}
.image-viewer-close{position:absolute;top:max(12px,env(safe-area-inset-top));right:max(12px,env(safe-area-inset-right));
display:flex;align-items:center;justify-content:center;width:44px;height:44px;border:none;border-radius:999px;
background:rgba(15,23,42,.82);color:white;font-size:28px;line-height:1;cursor:pointer;box-shadow:0 10px 24px rgba(0,0,0,.35)}
@keyframes attShimmer{100%{transform:translateX(100%)}}

/* Thinking blocks */
/* Thinking blocks — standalone or inside work group */
.thinking-block{background:var(--bg);border-left:3px solid var(--yellow);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.thinking-header{padding:8px 12px;font-size:12px;color:var(--yellow);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
.thinking-body{padding:0 12px 8px 12px;font-size:13px;color:var(--dim);
line-height:1.5;display:none;white-space:pre-wrap;-webkit-user-select:text;user-select:text;
max-height:300px;overflow-y:auto}
.thinking-block.open .thinking-body{display:block}
.thinking-header .arrow{transition:transform 0.2s}
.thinking-block.open .thinking-header .arrow{transform:rotate(90deg)}
/* Thinking inside work group: slimmer margins */
.tool-group-body .thinking-block{margin:4px 0;border-left:2px solid var(--yellow)}

/* Work group — collapsible container for thinking + tool calls */
.tool-group{background:var(--bg);border-left:3px solid var(--accent);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.tool-group-header{padding:8px 12px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none;font-weight:600}
.tool-group-header .arrow{transition:transform 0.2s}
.tool-group.open .tool-group-header .arrow{transform:rotate(90deg)}
.tool-group-body{display:none;padding:0 4px 4px}
.tool-group.open .tool-group-body{display:block}
.tool-group-header .tool-group-count{margin-left:auto;font-size:11px;color:var(--dim);font-weight:400}

/* Tool blocks (inside group) */
.tool-block{background:var(--surface);border-left:2px solid rgba(255,255,255,0.06);border-radius:4px;
margin:4px 0;overflow:hidden}
.tool-header{padding:6px 10px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
.tool-summary{font-size:calc(12px * var(--chat-font-scale));color:var(--dim);padding:2px 10px 4px;line-height:1.4}
.tool-summary code{background:var(--bg);padding:1px 4px;border-radius:3px;font-size:calc(11px * var(--chat-font-scale))}
.tool-body{padding:0 10px 6px 10px;font-size:calc(12px * var(--chat-font-scale));color:var(--dim);
line-height:1.4;display:none}
.tool-block.open .tool-body{display:block}
.tool-block.open .tool-header .arrow{transform:rotate(90deg)}
.tool-header .arrow{transition:transform 0.2s}
.tool-status{margin-left:auto;font-size:14px}
.tool-body pre{background:var(--bg);padding:8px;border-radius:4px;overflow-x:auto;
font-size:calc(11px * var(--chat-font-scale));margin:4px 0;max-height:200px;overflow-y:auto}

/* Cost footer */
.cost{font-size:11px;color:var(--dim);margin-top:4px;padding-left:4px}
.canceled-badge{font-size:11px;color:var(--red,#ef4444);margin-top:4px;padding-left:4px;font-style:italic}

/* Streaming indicator */
.streaming .bubble::after{content:'';display:inline-block;width:6px;height:14px;
background:var(--accent);margin-left:2px;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
/* B-34: empty bubble (pre-first-token) needs min-height so cursor is visible */
.streaming .bubble:empty{min-height:18px;display:block}
.queue-state{display:flex;flex-direction:column;gap:4px}
.queue-title{font-size:13px;font-weight:600;color:var(--text)}
.queue-meta{font-size:12px;color:var(--yellow)}
.system-retry-btn{margin-top:10px;padding:6px 12px;border-radius:8px;border:1px solid rgba(14,165,233,0.35);
background:rgba(14,165,233,0.12);color:var(--accent);font-size:12px;font-weight:600;cursor:pointer}
.system-retry-btn:hover{background:rgba(14,165,233,0.18)}

/* Composer */
.composer{background:var(--surface);padding:8px 12px;padding-bottom:calc(8px + var(--sab));
border-top:1px solid var(--card);display:flex;align-items:flex-end;gap:8px;flex-shrink:0;transition:margin-left .2s ease;flex-wrap:wrap}
.stale-bar{display:none;align-items:center;gap:10px;width:100%;padding:8px 10px;border:1px solid transparent;
border-radius:10px;margin-bottom:8px;font-size:12px;font-weight:600;opacity:0;transform:translateY(8px);
pointer-events:none;transition:opacity .2s ease,transform .2s ease,background .3s ease,border-color .3s ease,color .3s ease}
.stale-bar.show{display:flex;opacity:1;transform:translateY(0);pointer-events:auto}
.stale-bar .banner-dot{width:8px;height:8px;border-radius:50%;background:currentColor;animation:stale-dot-pulse 1.2s ease-in-out infinite;flex-shrink:0}
.stale-bar .stale-label{min-width:0;flex:1;line-height:1.35}
.stale-bar .stale-actions{display:flex;gap:8px;flex-shrink:0}
.stale-timer{font-variant-numeric:tabular-nums}
.stale-action{min-width:auto !important;min-height:0 !important;border-radius:6px !important;padding:4px 12px !important;font-size:12px !important;font-weight:600;border:1px solid currentColor !important;background:transparent !important;color:inherit !important}
.stale-action:hover{opacity:.92;filter:brightness(1.05)}
.stale-action.primary{background:currentColor !important;color:var(--surface) !important;border-color:currentColor !important}
body.theme-light .stale-action.primary{color:#fff !important}
@keyframes stale-dot-pulse{0%,100%{opacity:1}50%{opacity:.45}}
.composer textarea{flex:1;background:var(--bg);color:var(--text);border:1px solid var(--card);
border-radius:12px;padding:10px 14px;font-size:16px;resize:none;outline:none;
max-height:120px;line-height:1.4;font-family:inherit}
.composer textarea:focus{border-color:var(--accent)}
.composer button{min-width:44px;min-height:44px;border-radius:50%;border:none;
background:var(--accent);color:white;font-size:18px;cursor:pointer;flex-shrink:0;
display:flex;align-items:center;justify-content:center}
.composer button:disabled{background:var(--card);color:var(--dim)}
.composer button.stop{background:var(--red)}
.composer button.transcribing{background:var(--yellow);color:var(--bg)}
.stop-menu{position:absolute;bottom:100%;right:0;margin-bottom:8px;
background:var(--surface);border:1px solid var(--card);border-radius:14px;
padding:6px;min-width:180px;box-shadow:0 8px 32px rgba(0,0,0,0.45);z-index:100;
opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .15s ease,transform .15s ease}
.stop-menu.show{opacity:1;transform:translateY(0);pointer-events:auto}
.stop-menu button{display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;
background:none;border:none;color:var(--text);font-size:14px;cursor:pointer;border-radius:10px;transition:background .15s ease;text-align:left}
.stop-menu button:hover{background:var(--bg)}
.stop-menu button:active{background:var(--bg)}
.stop-menu button .stop-dot{width:8px;height:8px;border-radius:50%;background:var(--red);
animation:dotPulse 1.2s ease-in-out infinite;flex-shrink:0}
.stop-menu button .stop-icon{width:16px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;font-size:13px}
.stop-menu button .stop-label{min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stop-menu button .agent-time{margin-left:auto;font-size:11px;color:var(--dim);flex-shrink:0}
.stop-menu hr{border:none;border-top:1px solid var(--card);margin:4px 0}
.stop-menu .stop-all{color:var(--red);font-weight:500}
.stop-menu .stop-confirm{background:rgba(239,68,68,0.12)}
.stop-menu .stop-keep{opacity:.6}
@keyframes dotPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.thinking-indicator{display:flex;gap:5px;padding:12px 16px;align-items:center}
.thinking-indicator .dot{width:8px;height:8px;border-radius:50%;background:var(--dim);
animation:dotPulse 1.4s ease-in-out infinite}
.thinking-indicator .dot:nth-child(2){animation-delay:0.2s}
.thinking-indicator .dot:nth-child(3){animation-delay:0.4s}
.thinking-indicator .ti-label{font-size:12px;color:var(--dim);margin-left:4px}
.btn-compose{min-width:44px;min-height:44px;border-radius:50%;border:none;
background:var(--card);color:var(--dim);font-size:18px;cursor:pointer;flex-shrink:0;
display:flex;align-items:center;justify-content:center}
.composer label.btn-compose{position:relative;display:flex;align-items:center;justify-content:center}
.btn-compose:active{background:var(--accent);color:white}
.btn-compose.compose-action{background:var(--accent);color:#fff;box-shadow:0 4px 14px rgba(14,165,233,0.28);
transition:background .2s ease,color .2s ease,box-shadow .2s ease,transform .15s ease}
.btn-compose.compose-action.is-send{background:var(--accent)}
.btn-compose.compose-action.is-stop{background:var(--red);box-shadow:0 0 0 0 rgba(239,68,68,0.4);
animation:stream-pulse 1.5s ease-in-out infinite}
.btn-compose.compose-action:disabled{background:var(--card);color:var(--dim);box-shadow:none;animation:none;cursor:default}
.btn-compose.compose-action:not(:disabled):active{transform:scale(.96)}
@keyframes stream-pulse{
  0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.4)}
  50%{box-shadow:0 0 0 8px rgba(239,68,68,0)}
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.attach-preview{display:flex;gap:6px;padding:0 12px;overflow-x:auto;flex-shrink:0;transition:margin-left .2s ease}
.attach-preview:empty{display:none}
.attach-item{background:var(--card);border-radius:8px;padding:4px 8px;display:flex;align-items:center;
gap:4px;font-size:12px;color:var(--dim);flex-shrink:0;max-width:150px}
.attach-item img{width:32px;height:32px;object-fit:cover;border-radius:4px}
.attach-item .remove{cursor:pointer;color:var(--red);font-size:14px;margin-left:4px}
/* Drag-and-drop overlay */
.drop-overlay{display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);
align-items:center;justify-content:center;pointer-events:none}
.drop-overlay.visible{display:flex}
.drop-overlay-inner{border:3px dashed var(--accent);border-radius:16px;padding:40px 60px;
background:var(--surface);color:var(--accent);font-size:18px;font-weight:600;
text-align:center;pointer-events:none}
.transcribing{color:var(--yellow);font-size:12px;padding:4px 12px;transition:margin-left .2s ease}

/* History sidebar */
.sidebar{position:fixed;top:0;left:0;width:var(--sidebar-width);height:100dvh;background:var(--nav-bg);
z-index:100;transform:translateX(-100%);transition:transform 0.2s ease;padding-top:var(--sat);overflow:hidden;
display:flex;flex-direction:column;border-right:1px solid rgba(255,255,255,0.06)}
.sidebar.open{transform:translateX(0);transition:transform 0.25s cubic-bezier(0.4,0,0.2,1)}
body.theme-light .sidebar{border-right-color:rgba(0,0,0,0.04)}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99;display:none}
.sidebar-overlay.open{display:block}
.sidebar-header{display:flex;align-items:center;justify-content:space-between;padding:18px 16px 14px}
.sidebar h2{font-size:15px;font-weight:700;letter-spacing:0.3px}
.sidebar-body{flex:1;overflow-y:auto;padding:0 8px 12px}
.sidebar-pin{background:transparent;border:none;color:var(--dim);font-size:18px;cursor:pointer;
width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center}
.sidebar-pin:hover,.sidebar-pin.active{background:var(--nav-card-hover);color:var(--accent)}
.sidebar .new-btn{padding:10px 16px;color:var(--accent);cursor:pointer;font-size:13px;font-weight:600;
border:1px dashed rgba(14,165,233,0.35);border-radius:10px;text-align:center;justify-content:center;
background:transparent;min-height:40px;display:flex;align-items:center;margin-bottom:12px;
transition:background 0.15s ease,border-color 0.15s ease,border-style 0.15s ease}
.sidebar .new-btn:hover{border-style:solid;background:var(--nav-card-hover)}
body.theme-light .sidebar .new-btn{border-color:rgba(2,132,199,0.35)}
.sidebar .chat-item{background:var(--nav-card);border-radius:10px;padding:12px 14px;margin-bottom:6px;
border:1px solid transparent;cursor:pointer;font-size:14px;color:var(--text);min-height:44px;display:block;
transition:background 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease,padding 0.15s ease}
.sidebar .chat-item:hover{background:var(--nav-card-hover);border-color:rgba(255,255,255,0.06)}
body.theme-light .sidebar .chat-item:hover{border-color:rgba(0,0,0,0.06)}
.sidebar .chat-item:active{background:var(--nav-card-hover)}
.sidebar .chat-item.active{background:var(--nav-card-active);border-left:3px solid var(--accent);
box-shadow:var(--nav-accent-glow);padding-left:11px}
.chat-item-top{display:flex;align-items:center;gap:8px;min-width:0}
.chat-item .ci-avatar{font-size:22px;width:28px;text-align:center;flex-shrink:0;margin-right:0}
.chat-item-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;
color:var(--text);font-weight:500}
.sidebar .chat-item.active .chat-item-title{color:var(--accent);font-weight:600}
.chat-item-subtitle{font-size:11px;font-weight:500;color:var(--dim);margin-top:3px;padding-left:36px}
.chat-item-subtitle .model{opacity:0.7}
.chat-item-actions{margin-left:auto;display:flex;gap:2px;flex-shrink:0;opacity:0;pointer-events:none;
transition:opacity 0.15s ease}
.chat-item:hover .chat-item-actions,.chat-item:focus-within .chat-item-actions{opacity:1;pointer-events:auto}
.chat-action-btn{background:none;border:none;cursor:pointer;font-size:12px;padding:2px 4px;opacity:0.5;line-height:1}
.chat-action-btn:hover{opacity:1}
.sidebar-section-header{display:flex;align-items:center;justify-content:center;gap:10px;padding:0 4px 8px;
color:var(--dim);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;margin-top:16px}
.thread-section-header::before,.thread-section-header::after{content:'';flex:1;height:1px;background:var(--nav-divider)}
.thread-section-header .section-label{opacity:0.6;white-space:nowrap}
.section-toggle{background:none;border:none;color:var(--dim);cursor:pointer;font-size:11px;padding:0;opacity:0.5;line-height:1}
.section-toggle:hover{opacity:0.8}
.sidebar .chat-item.thread-item{padding:8px 14px;min-height:0;opacity:0.85;font-size:13px}
.sidebar .chat-item.thread-item:hover{opacity:1}
.sidebar .chat-item.thread-item .ci-avatar{font-size:18px;width:24px}
.sidebar .chat-item.thread-item .chat-item-title{font-size:13px}
.speaker-header{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
color:var(--accent);margin-bottom:2px;padding-left:2px;cursor:pointer;border-radius:6px;
padding:2px 6px;margin-left:-6px;transition:background .15s ease}
.speaker-header:hover{background:rgba(14,165,233,0.10)}
.speaker-avatar{font-size:14px}
.speaker-name{opacity:0.9}

/* Persona Info Card — popover (desktop) + bottom sheet (mobile) */
.pic-backdrop{position:fixed;inset:0;z-index:299;background:transparent}
.pic-backdrop.bs-mode{background:rgba(0,0,0,.5);transition:background .2s ease}
.pic-popover{position:fixed;z-index:300;background:var(--surface);border:1px solid var(--card);
border-radius:14px;box-shadow:0 8px 28px rgba(0,0,0,.45);width:280px;overflow:hidden;
animation:picFadeIn .12s ease}
.pic-sheet{position:fixed;bottom:0;left:0;right:0;z-index:300;background:var(--surface);
border-radius:16px 16px 0 0;box-shadow:0 -4px 24px rgba(0,0,0,.45);overflow:hidden;
animation:picSlideUp .2s ease}
@keyframes picFadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
@keyframes picSlideUp{from{transform:translateY(100%)}to{transform:none}}
.pic-drag-handle{display:none;width:36px;height:4px;background:var(--card);border-radius:2px;
margin:10px auto 4px;opacity:.5}
@media(max-width:599px){.pic-drag-handle{display:block}}
.pic-header{display:flex;align-items:center;gap:12px;padding:16px 16px 10px}
.pic-avatar-big{font-size:36px;line-height:1;flex-shrink:0}
.pic-name-block{flex:1;min-width:0}
.pic-name{font-size:15px;font-weight:700;color:var(--text);white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.pic-role{font-size:12px;color:var(--dim);margin-top:2px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pic-model{font-size:11px;color:var(--accent);margin-top:3px;font-weight:600}
.pic-body{padding:0 16px 8px}
.pic-bio{font-size:13px;color:var(--dim);line-height:1.5;margin-bottom:10px;
max-height:80px;overflow-y:auto}
.pic-actions{display:flex;gap:8px;padding:10px 16px 16px}
.pic-btn{flex:1;padding:9px 8px;border-radius:10px;border:none;font-size:13px;
font-weight:600;cursor:pointer;transition:all .15s ease}
.pic-btn-message{background:var(--accent);color:#fff}
.pic-btn-message:hover{filter:brightness(1.1)}
.pic-btn-edit{background:var(--card);color:var(--text)}
.pic-btn-edit:hover{background:var(--surface);border:1px solid var(--accent);color:var(--accent)}

/* @mention autocomplete */
.mention-popup{position:absolute;bottom:100%;left:0;right:0;background:var(--surface);
border:1px solid var(--card);border-radius:8px;margin-bottom:4px;max-height:200px;
overflow-y:auto;display:none;z-index:100;box-shadow:0 -4px 12px rgba(0,0,0,0.3)}
.mention-popup.visible{display:block}
.mention-item{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;
font-size:14px;transition:background 0.1s}
.mention-item:hover,.mention-item.selected{background:var(--card)}
.mention-item .mi-avatar{font-size:18px;width:24px;text-align:center}
.mention-item .mi-name{font-weight:600;color:var(--text)}
.mention-item .mi-role{font-size:12px;color:var(--dim);margin-left:auto}

/* Usage bar */
.usage-bar{background:var(--surface);padding:4px 16px 6px;border-bottom:1px solid var(--card);
display:none;gap:12px;flex-shrink:0;cursor:pointer;
transition:opacity 0.3s ease,max-height 0.3s ease,margin-left .2s ease;overflow:hidden;max-height:60px}
.usage-bar.visible{display:flex}
.usage-bar.fading{opacity:0;max-height:0;padding:0 16px}
.usage-label{font-size:9px;font-weight:700;color:var(--dim);letter-spacing:0.5px;text-transform:uppercase;
writing-mode:vertical-lr;text-orientation:mixed;align-self:center;opacity:0.5}
.usage-bucket{flex:1;min-width:0}
.usage-bucket .label-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px}
.usage-bucket .label{font-size:10px;font-weight:600;color:var(--dim)}
.usage-bucket .pct{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums}
.usage-bucket .reset{font-size:9px;color:var(--dim);opacity:0.6}
.usage-track{height:3px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden}
.usage-fill{height:100%;border-radius:2px;transition:width 0.4s ease,background 0.4s ease}
.usage-toggle{background:none;border:none;color:var(--dim);cursor:pointer;
font-size:11px;padding:2px 6px;opacity:0.4;align-self:center;flex-shrink:0}
.usage-toggle:hover{opacity:0.8}
.usage-fill.green{background:var(--green)}
.usage-fill.orange{background:var(--yellow)}
.usage-fill.red{background:var(--red)}

/* Context bar */
.context-bar{display:none;flex-shrink:0;align-items:center;justify-content:flex-end;
gap:6px;padding:2px 16px 3px;background:var(--bg);transition:margin-left .2s ease}
.context-bar.visible{display:flex}
.context-detail{font-size:9px;font-weight:600;color:var(--dim);font-variant-numeric:tabular-nums;
white-space:nowrap;opacity:0.7}
.context-track{width:60px;height:2px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden}
.context-fill{height:100%;border-radius:2px;transition:width 0.4s ease,background 0.4s ease}
.context-fill.green{background:var(--green)}
.context-fill.orange{background:var(--yellow)}
.context-fill.red{background:var(--red)}

/* Debug bar */
.debugbar{background:var(--debug-bg);border-top:1px solid var(--debug-border);padding:6px 12px;flex-shrink:0}
.debug-state{color:var(--debug-state);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11px;white-space:pre-wrap}
.debug-log{color:var(--debug-log);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
line-height:1.35;max-height:88px;overflow-y:auto;white-space:pre-wrap;margin-top:4px}
.alert-toast{position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px 12px;
transform:translateY(-100%);transition:transform .3s ease;pointer-events:none}
.alert-toast.show{transform:translateY(0);pointer-events:auto}
.alert-toast-inner{max-width:600px;margin:0 auto;padding:10px 14px;border-radius:10px;
display:flex;align-items:flex-start;gap:10px;box-shadow:0 4px 20px rgba(0,0,0,.3);
font-size:13px;line-height:1.4;cursor:pointer}
.alert-toast-inner.critical{background:#1a0000;border:1px solid #dc2626;color:#fca5a5}
.alert-toast-inner.warning{background:#1a1400;border:1px solid #d97706;color:#fcd34d}
.alert-toast-inner.info{background:#001a1a;border:1px solid #0891b2;color:#67e8f9}
.alert-toast .alert-icon{font-size:18px;flex-shrink:0;margin-top:1px}
.alert-toast .alert-body{flex:1;min-width:0}
.alert-toast .alert-source{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;opacity:.7}
.alert-toast .alert-title{font-weight:600;margin-top:2px}
.alert-toast .alert-text{font-size:12px;opacity:.8;margin-top:2px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.alert-toast .alert-preview{display:none;margin-top:6px;font-size:12px;opacity:.85}
.alert-toast .alert-preview.show{display:block}
.alert-toast .alert-preview-line{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.alert-toast .alert-actions{display:flex;gap:6px;flex-shrink:0;align-items:center}
.alert-toast .alert-actions button{font-size:11px;font-weight:600;padding:4px 10px;
border-radius:6px;border:none;cursor:pointer}
.alert-toast .btn-ack{background:#dc2626;color:#fff}
.alert-toast .btn-allow{background:#16a34a;color:#fff}
.alert-toast .btn-dismiss{background:transparent;color:inherit;opacity:.5;font-size:16px;padding:2px 6px}
.alert-badge{position:relative;cursor:pointer;font-size:18px;padding:0 4px;user-select:none}
.alert-badge .count{position:absolute;top:-4px;right:-6px;background:#dc2626;color:#fff;
font-size:9px;font-weight:700;min-width:16px;height:16px;border-radius:8px;
display:flex;align-items:center;justify-content:center;padding:0 4px}
.alert-badge .count:empty{display:none}
.settings-panel{position:fixed;top:40px;right:8px;width:340px;max-height:80vh;
background:var(--panel-bg);border:1px solid var(--panel-border);border-radius:12px;z-index:9997;
overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none}
.settings-panel.show{display:block}
.settings-header{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:13px;font-weight:600;color:var(--panel-text)}
.settings-header button{background:transparent;border:none;color:var(--panel-muted);font-size:18px;cursor:pointer}
.settings-header button:hover{color:var(--panel-text)}
.settings-body{padding:8px 14px}
.settings-section{margin-bottom:14px}
.settings-label{font-size:12px;font-weight:600;color:var(--accent);display:block;margin-bottom:4px}
.settings-hint{font-size:11px;color:var(--panel-muted);margin-bottom:4px}
.settings-value{font-size:12px;color:var(--panel-muted)}
.settings-section select{width:100%;padding:6px 8px;border-radius:6px;border:1px solid var(--panel-border);
background:var(--panel-input-bg);color:var(--panel-text);font-size:13px;outline:none}
.settings-section select:disabled{opacity:0.5}
.settings-section select:focus{border-color:var(--accent)}
.alerts-panel{position:fixed;top:40px;right:8px;width:380px;max-height:70vh;
background:var(--panel-bg);border:1px solid var(--panel-border);border-radius:12px;z-index:9998;
overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none}
.alerts-panel.show{display:block}
.alerts-panel-header{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:13px;font-weight:600;color:var(--panel-text)}
.alerts-panel-header button{background:transparent;border:none;color:var(--panel-muted);
font-size:11px;cursor:pointer}
.alerts-panel-header button:hover{color:var(--panel-text)}
.alert-item{padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:12px;
display:flex;align-items:flex-start;gap:8px}
.alert-item.acked{opacity:.4}
.alert-item .ai-icon{font-size:14px;flex-shrink:0;margin-top:1px}
.alert-item .ai-body{flex:1;min-width:0}
.alert-item .ai-source{font-size:9px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;color:var(--panel-muted)}
.alert-item .ai-title{font-weight:600;color:var(--panel-text);margin-top:1px}
.alert-item .ai-time{font-size:10px;color:var(--panel-muted);margin-top:2px}
.alert-item .ai-actions{display:flex;gap:4px;flex-shrink:0}
.alert-item .ai-actions button{font-size:10px;padding:3px 8px;border-radius:5px;
border:none;cursor:pointer;font-weight:600}
.alert-detail-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);
display:flex;align-items:center;justify-content:center;padding:20px}
.alert-detail-card{background:var(--panel-bg);border-radius:16px;max-width:500px;width:100%;
max-height:80vh;overflow:hidden auto;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.alert-detail-card .ad-header{display:flex;align-items:center;gap:10px;padding:16px 20px;
border-bottom:1px solid var(--panel-border)}
.alert-detail-card .ad-icon{font-size:28px}
.alert-detail-card .ad-source{font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;padding:3px 8px;border-radius:10px;display:inline-block}
.alert-detail-card .ad-time{font-size:11px;color:var(--panel-muted);margin-top:4px}
.alert-detail-card .ad-close{margin-left:auto;background:none;border:none;color:var(--panel-muted);
font-size:20px;cursor:pointer;padding:4px 8px}
.alert-detail-card .ad-close:hover{color:var(--panel-text)}
.alert-detail-card .ad-section{padding:12px 20px;border-bottom:1px solid var(--panel-border);min-width:0}
.alert-detail-card .ad-label{font-size:10px;font-weight:600;color:var(--panel-muted);
text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.alert-detail-card .ad-title{font-size:16px;font-weight:600;color:var(--panel-text)}
.alert-detail-card .ad-body{font-size:13px;color:var(--panel-muted);
overflow-wrap:break-word;word-break:break-word;line-height:1.6}
.alert-detail-card .ad-body a{color:#3b82f6;text-decoration:underline;cursor:pointer;word-break:break-all}
.alert-detail-card .ad-body a:hover{color:#60a5fa}
.alert-detail-card .ad-body ul,.alert-detail-card .ad-body ol{margin:8px 0 0;padding-left:20px}
.alert-detail-card .ad-body li+li{margin-top:4px}
.alert-detail-card .ad-body code{display:block;background:rgba(255,255,255,0.04);
border:1px solid var(--panel-border);border-radius:8px;padding:12px;font-size:13px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
word-break:break-all;margin-top:8px;position:relative;cursor:pointer;color:var(--panel-text)}
.alert-detail-card .ad-body code::after{content:'Tap to copy';display:block;text-align:center;
font-family:inherit;font-size:11px;color:var(--panel-muted);margin-top:8px}
.alert-detail-card .ad-body code[data-copied="true"]::after{content:'Copied';color:var(--green)}
.alert-detail-card .ad-meta-key{font-size:10px;font-weight:600;color:var(--panel-muted);
text-transform:uppercase}
.alert-detail-card .ad-meta-val{font-size:12px;color:var(--panel-text);
font-family:ui-monospace,monospace;word-break:break-all;overflow-wrap:break-word}
.alert-detail-card .ad-actions{display:flex;gap:8px;padding:16px 20px}
.alert-detail-card .ad-actions button{flex:1;padding:8px;border-radius:8px;border:none;
font-weight:600;font-size:13px;cursor:pointer}
body.sidebar-pinned .sidebar{transform:translateX(0);box-shadow:1px 0 0 rgba(255,255,255,0.06),6px 0 16px rgba(0,0,0,0.12)}
body.sidebar-pinned .sidebar-overlay{display:none!important}
body.sidebar-pinned .topbar,
body.sidebar-pinned .usage-bar,
body.sidebar-pinned .context-bar,
body.sidebar-pinned .messages,
body.sidebar-pinned .attach-preview,
body.sidebar-pinned .transcribing,
body.sidebar-pinned .composer{margin-left:var(--sidebar-width)}
body.sidebar-pinned .premium-locked-bar{margin-left:var(--sidebar-width)}

/* Profile picker modal */
.profile-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;
display:flex;align-items:center;justify-content:center;padding:20px}
.profile-modal{background:var(--surface);border-radius:16px;max-width:480px;width:100%;
max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.profile-modal-header{display:flex;align-items:center;justify-content:space-between;
padding:16px 20px;border-bottom:1px solid var(--card);
padding-top:max(16px,calc(env(safe-area-inset-top,0px) + 8px))}
.profile-modal-header h3{font-size:16px;font-weight:600}
.profile-modal-header button{background:none;border:none;color:var(--dim);
font-size:24px;line-height:1;cursor:pointer;padding:0;
min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center;
border-radius:10px;-webkit-tap-highlight-color:rgba(255,255,255,.08);touch-action:manipulation}
.profile-modal-header button:active{background:var(--card)}
.profile-modal-body{padding:12px 16px;overflow-y:auto;flex:1;min-height:0}
.profile-card{display:flex;align-items:center;gap:12px;padding:12px 14px;
border-radius:12px;cursor:pointer;border:2px solid transparent;
transition:all .15s ease;margin-bottom:8px;background:var(--bg)}
.profile-card:hover{border-color:var(--accent);background:var(--card)}
.profile-card.selected{border-color:var(--accent);background:var(--card)}
.profile-card .profile-avatar{font-size:28px;flex-shrink:0;width:40px;text-align:center}
.profile-card .profile-info{flex:1;min-width:0}
.profile-card .profile-name{font-size:14px;font-weight:600;color:var(--text)}
.profile-card .profile-role{font-size:12px;color:var(--dim);
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.profile-card .profile-model{font-size:10px;color:var(--accent);margin-top:2px}
.profile-modal-actions{padding:12px 16px;border-top:1px solid var(--card);
display:flex;gap:8px;justify-content:flex-end}
.profile-modal-actions button{padding:8px 16px;border-radius:8px;border:none;
font-weight:600;font-size:13px;cursor:pointer}
.profile-modal-new-persona{display:block;width:100%;margin-top:4px;padding:12px 14px;
background:transparent;border:none;border-radius:10px;color:var(--accent);font-size:13px;
font-weight:600;text-align:left;cursor:pointer}
.profile-modal-new-persona:hover{text-decoration:underline;background:var(--card)}
.profile-modal-actions .btn-create{background:var(--accent);color:white}
.profile-modal-actions .btn-create:disabled{opacity:.5;cursor:default}
.profile-modal-actions .btn-skip{background:var(--card);color:var(--dim)}

/* Group settings modal */
.gs-tabs{display:flex;gap:8px;padding:12px 16px;border-bottom:1px solid var(--bg);background:var(--surface);position:sticky;top:0;z-index:1}
.gs-tab{flex:1;padding:8px 12px;border:none;border-radius:10px;background:var(--bg);color:var(--dim);font-size:12px;
font-weight:700;cursor:pointer;transition:all .15s ease}
.gs-tab:hover{color:var(--text);background:var(--card)}
.gs-tab.active{background:var(--accent);color:white}
.gs-pane{padding-bottom:8px}
.gs-section{padding:12px 16px;border-bottom:1px solid var(--bg)}
.gs-section-title{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--dim);
margin-bottom:8px;letter-spacing:.5px}
.gs-name-input,.gs-select{width:100%;padding:8px 12px;border:1px solid var(--card);border-radius:8px;
background:var(--bg);color:var(--text);font-size:14px;box-sizing:border-box}
.gs-name-input:focus,.gs-select:focus{outline:none;border-color:var(--accent)}
.gs-member{display:flex;align-items:center;gap:10px;padding:8px 10px;
border-radius:10px;margin-bottom:6px;background:var(--bg);transition:background .15s}
.gs-member:hover{background:var(--card)}
.gs-member-avatar{font-size:22px;flex-shrink:0;width:32px;text-align:center}
.gs-member-info{flex:1;min-width:0}
.gs-member-name{font-size:13px;font-weight:600;color:var(--text)}
.gs-member-model{font-size:11px;color:var(--dim)}
.gs-member-badge{font-size:11px;font-weight:600;padding:3px 8px;border-radius:12px;cursor:pointer;
border:none;transition:all .15s}
.gs-member-badge.primary{background:var(--accent);color:white}
.gs-member-badge.mentioned{background:var(--card);color:var(--dim)}
.gs-member-remove{background:none;border:none;color:var(--dim);cursor:pointer;font-size:16px;
padding:2px 6px;border-radius:6px;opacity:.5;transition:all .15s}
.gs-member-remove:hover{opacity:1;color:var(--red);background:rgba(255,59,48,.1)}
.gs-add-btn{display:flex;align-items:center;gap:8px;padding:8px 12px;width:100%;
border:1px dashed var(--card);border-radius:10px;background:none;color:var(--dim);
cursor:pointer;font-size:13px;transition:all .15s}
.gs-add-btn:hover{border-color:var(--accent);color:var(--accent)}
.gs-toggle-row{display:flex;align-items:center;justify-content:space-between;padding:6px 0}
.gs-toggle-copy{flex:1;min-width:0;padding-right:12px}
.gs-toggle-label{font-size:13px;color:var(--text)}
.gs-toggle-hint{font-size:11px;color:var(--dim);margin-top:4px;line-height:1.4}
.gs-toggle{position:relative;width:44px;height:24px;border-radius:12px;border:none;
cursor:pointer;transition:background .2s;flex-shrink:0}
.gs-toggle.on{background:var(--accent)}
.gs-toggle.off{background:var(--card)}
.gs-toggle::after{content:'';position:absolute;top:2px;left:2px;width:20px;height:20px;
border-radius:50%;background:white;transition:transform .2s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.gs-toggle.on::after{transform:translateX(20px)}
.gs-relay-status{margin-top:8px;padding:12px 14px;border:1px solid var(--card);border-radius:8px;
background:var(--bg);opacity:1;max-height:480px;overflow:hidden;transition:max-height .2s ease,opacity .15s ease}
.gs-relay-ready{display:flex;align-items:flex-start;gap:8px}
.gs-relay-ready-icon{font-size:15px;line-height:1;color:var(--accent)}
.gs-relay-ready-title{font-size:13px;font-weight:600;color:var(--text)}
.gs-relay-ready-copy{font-size:11px;color:var(--dim);line-height:1.4;margin-top:4px}
.gs-relay-header{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.gs-relay-round{font-size:13px;font-weight:600;color:var(--text)}
.gs-relay-round-max{font-size:11px;font-weight:400;color:var(--dim)}
.gs-relay-count{font-size:12px;color:var(--dim);white-space:nowrap}
.gs-relay-progress{height:4px;border-radius:2px;background:var(--card);margin:8px 0}
.gs-relay-progress-fill{height:100%;border-radius:2px;background:var(--accent);transition:width .3s ease}
.gs-relay-agents{display:flex;flex-direction:column;gap:6px}
.gs-relay-agent{display:flex;align-items:center;gap:6px;padding:3px 0}
.gs-relay-agent-emoji{width:22px;flex-shrink:0;font-size:16px;line-height:1;text-align:center}
.gs-relay-agent-icon{width:16px;flex-shrink:0;font-size:12px;line-height:1;text-align:center;color:var(--dim)}
.gs-relay-agent-name{flex:1;min-width:0;font-size:12px;color:var(--text)}
.gs-relay-agent-label{font-size:11px;color:var(--dim);text-align:right;white-space:nowrap}
.gs-relay-agent.is-next .gs-relay-agent-icon,.gs-relay-agent.is-next .gs-relay-agent-name,.gs-relay-agent.is-next .gs-relay-agent-label{color:var(--accent)}
.gs-relay-agent.is-next .gs-relay-agent-name{font-weight:600}
.gs-relay-agent.is-responded .gs-relay-agent-icon{color:#4ade80}
.gs-relay-agent.is-waiting .gs-relay-agent-icon,.gs-relay-agent.is-waiting .gs-relay-agent-name,.gs-relay-agent.is-waiting .gs-relay-agent-label{color:var(--dim)}
.gs-relay-agent.is-abstained .gs-relay-agent-icon{color:color-mix(in srgb, var(--dim) 60%, transparent)}
.gs-relay-agent.is-abstained .gs-relay-agent-name,.gs-relay-agent.is-abstained .gs-relay-agent-label{color:var(--dim)}
.gs-relay-agent.is-abstained .gs-relay-agent-label{font-style:italic}
.gs-relay-agent.is-paused .gs-relay-agent-icon,.gs-relay-agent.is-paused .gs-relay-agent-name,.gs-relay-agent.is-paused .gs-relay-agent-label{color:var(--yellow,#facc15)}
.gs-relay-agent.is-paused .gs-relay-agent-name{font-weight:600}
.gs-relay-paused{padding:6px 8px;margin:6px 0;border-radius:6px;background:color-mix(in srgb, var(--yellow,#facc15) 12%, transparent);color:var(--yellow,#facc15);font-size:11px;text-align:center;font-weight:500}
.gs-add-picker{padding:8px 0}
.gs-add-picker .profile-card{margin-bottom:4px;padding:8px 10px}
.gs-add-picker .profile-card .profile-avatar{font-size:22px;width:32px}
.gs-member-avatar{position:relative}
.gs-member-avatar .gs-crown{position:absolute;bottom:-2px;right:-2px;width:14px;height:14px;
border-radius:7px;background:#EAB308;display:flex;align-items:center;justify-content:center;
font-size:8px;border:2px solid var(--surface);line-height:1}
.gs-pref-card{padding:12px;border-radius:10px;background:var(--bg);margin-bottom:8px}
.gs-pref-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.gs-pref-label{font-size:13px;font-weight:600;color:var(--text)}
.gs-pref-value{font-size:12px;font-weight:600;color:var(--accent);white-space:nowrap}
.gs-pref-hint{font-size:11px;color:var(--dim);margin-top:4px;line-height:1.4}
.gs-range{width:100%;margin-top:12px;accent-color:var(--accent)}
.gs-inline-btn{margin-top:10px;background:none;border:none;color:var(--accent);font-size:12px;
font-weight:600;cursor:pointer;padding:0}
.gs-inline-btn:hover{text-decoration:underline}
.gs-danger{padding:12px 16px}
.gs-danger-btn{display:block;width:100%;padding:10px;text-align:center;font-size:13px;
font-weight:600;color:var(--red,#ef4444);background:rgba(239,68,68,.1);border:none;
border-radius:8px;cursor:pointer;transition:background .15s}
.gs-danger-btn:hover{background:rgba(239,68,68,.2)}
.gs-toast{position:fixed;left:50%;transform:translateX(-50%) translateY(20px);
bottom:max(60px,calc(env(safe-area-inset-bottom,0px) + 20px));
background:var(--card);color:var(--text);padding:10px 20px;border-radius:20px;font-size:13px;
font-weight:500;opacity:0;transition:all .25s ease;pointer-events:none;z-index:9999;
box-shadow:0 4px 16px rgba(0,0,0,.4)}
.gs-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
/* Inline save-status badge for the permissions picker (and any future
   gs-pref-card that reuses this pattern). Lives next to the section label
   so feedback is always visible inside the modal, not just via toast which
   gets covered by the bottom-sheet on phones. */
.gs-pref-label-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.gs-pref-status{font-size:11px;font-weight:600;padding:3px 8px;border-radius:10px;
opacity:0;transition:opacity .2s ease;letter-spacing:.02em}
.gs-pref-status[data-state="saving"]{opacity:1;color:var(--dim);background:var(--card)}
.gs-pref-status[data-state="saved"]{opacity:1;color:#10b981;background:rgba(16,185,129,.12)}
.gs-pref-status[data-state="error"]{opacity:1;color:#ef4444;background:rgba(239,68,68,.12)}

/* Profile indicator in topbar */
.topbar-profile{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--dim);
cursor:pointer;padding:2px 8px;border-radius:6px;margin-right:4px;flex-shrink:0}
.topbar-profile:hover{background:var(--card)}
.topbar-profile .tp-avatar{font-size:16px}
.topbar-profile .tp-name{font-size:11px;max-width:80px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}

/* Profile badge in sidebar chat items */
.chat-item .ci-avatar{font-size:22px;width:28px;text-align:center;flex-shrink:0;margin-right:0}

/* Profile change dropdown */
.profile-dropdown{position:fixed;background:var(--surface);border:1px solid var(--card);
border-radius:12px;z-index:201;box-shadow:0 8px 24px rgba(0,0,0,.4);
max-height:300px;overflow-y:auto;min-width:220px}
.profile-dropdown .pd-item{display:flex;align-items:center;gap:8px;padding:8px 12px;
cursor:pointer;font-size:13px;color:var(--text);border-bottom:1px solid var(--bg)}
.profile-dropdown .pd-item:hover{background:var(--card)}
.profile-dropdown .pd-item:last-child{border-bottom:none}
.profile-dropdown .pd-avatar{font-size:18px;flex-shrink:0}
.profile-dropdown .pd-name{flex:1}
.profile-dropdown .pd-check{color:var(--accent);font-size:14px}

/* ═══════════════════════════════════════════════════
   Inline pills (tool + thinking) — V3 redesign
   ═══════════════════════════════════════════════════ */
.pill{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;
background:var(--surface);border:1px solid var(--card);border-radius:12px;cursor:pointer;
transition:all 0.2s;user-select:none;margin-bottom:4px}
.pill:hover{transform:none}
.pill:active{transform:scale(0.98)}
.pill .pill-icon{font-size:14px;flex-shrink:0}
.pill .pill-label{font-size:13px;color:var(--text);font-weight:500}
.pill .pill-dim{color:var(--dim);font-weight:400;font-size:12px}
.pill .pill-chevron{color:var(--dim);font-size:13px;margin-left:2px}
.pill--tool:hover{border-color:var(--accent);background:rgba(14,165,233,0.06)}
.pill--tool-error{border-color:rgba(239,68,68,0.4)}
.pill--tool-error:hover{border-color:#ef4444;background:rgba(239,68,68,0.06)}
.pill--tool-error .pill-dim{color:#ef4444}
.pill--tool-error .pill-counts{color:#ef4444}
.pill--thinking:hover{border-color:var(--yellow);background:rgba(245,158,11,0.06)}
.pill--tool .pill-counts{font-size:11px;color:var(--dim)}
.pill--tool .spinner{width:14px;height:14px;border:2px solid var(--card);border-top-color:var(--accent);
border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}
.pill--tool.streaming{border-color:rgba(14,165,233,0.3)}
.pill--tool.streaming .pill-bar-wrap{width:80px;height:3px;background:var(--card);border-radius:2px;overflow:hidden}
.pill--tool.streaming .pill-bar{height:100%;background:var(--accent);border-radius:2px;transition:width 0.3s ease}
.pill--tool.active-pill{border-color:var(--accent);background:rgba(14,165,233,0.06)}
.pill--tool.active-pill .pill-chevron{color:var(--accent)}
.pill--thinking.streaming{border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.05)}
.pill--thinking.streaming .pill-label{color:var(--yellow)}
.pill--thinking.streaming .pill-live{width:8px;height:8px;border-radius:50%;background:var(--yellow);
animation:dotPulse 1.4s ease-in-out infinite;flex-shrink:0;margin-left:2px}
.pill--thinking.streaming .pill-chevron{display:none}
.pill--thinking.active-pill{border-color:var(--yellow);background:rgba(245,158,11,0.06)}
.pill--thinking.active-pill .pill-chevron,.pill--thinking.active-pill .pill-label{color:var(--yellow)}

/* ═══════════════════════════════════════════════════
   Side panel — desktop detail pane (tool steps / thinking)
   ═══════════════════════════════════════════════════ */
.side-panel{position:fixed;top:52px;right:0;bottom:0;width:0;overflow:hidden;
background:var(--surface);border-left:1px solid var(--card);z-index:90;
transition:width 0.3s cubic-bezier(0.32,0.72,0,1);display:flex;flex-direction:column}
.side-panel.open{width:380px}
body.panel-open .messages{margin-right:380px}
body.panel-open .composer,body.panel-open .context-bar,
body.panel-open .attach-preview,body.panel-open .transcribing{
transition:margin-right 0.3s cubic-bezier(0.32,0.72,0,1);margin-right:380px}
.sp-header{padding:16px 20px;border-bottom:1px solid var(--card);display:flex;align-items:center;
gap:10px;flex-shrink:0;min-width:380px}
.sp-title{font-size:14px;font-weight:600;flex:1;white-space:nowrap}
.sp-title .sp-dim{color:var(--dim);font-weight:400;font-size:12px}
.sp-close{width:28px;height:28px;border-radius:8px;background:var(--card);border:none;
color:var(--dim);font-size:14px;cursor:pointer;display:flex;align-items:center;
justify-content:center;transition:all 0.15s;flex-shrink:0}
.sp-close:hover{background:var(--bg);color:var(--text)}
.sp-body{flex:1;overflow-y:auto;padding:8px 12px 24px;min-width:380px;
overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
.sp-step{display:flex;align-items:center;gap:10px;padding:10px;border-radius:10px;transition:background 0.15s}
.sp-step:hover{background:var(--bg)}
.sp-step+.sp-step{border-top:1px solid rgba(51,65,85,0.4)}
.sp-step .sps-icon{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;
justify-content:center;font-size:15px;flex-shrink:0}
.sp-step .sps-icon.read{background:rgba(14,165,233,0.1)}
.sp-step .sps-icon.cmd{background:rgba(168,85,247,0.1)}
.sp-step .sps-icon.edit{background:rgba(245,158,11,0.1)}
.sp-step .sps-icon.write{background:rgba(16,185,129,0.1)}
.sp-step .sps-icon.search{background:rgba(99,102,241,0.1)}
.sp-step .sps-info{flex:1;min-width:0}
.sp-step .sps-label{font-size:13px;font-weight:500;color:var(--text);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-step .sps-detail{font-size:11px;color:var(--dim);font-family:'SF Mono','Fira Code',monospace;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-step .sps-meta{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex-shrink:0}
.sp-step .sps-status{font-size:12px}
.sp-step .sps-time{font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
.sp-step.active-step{background:rgba(14,165,233,0.06)}
.sp-step{cursor:pointer}
.sp-step .sps-chevron{color:var(--dim);font-size:11px;transition:transform 0.2s;flex-shrink:0}
.sp-step.expanded .sps-chevron{transform:rotate(90deg);color:var(--accent)}
.sp-detail{display:none;padding:8px 10px;margin:0 10px 8px;background:var(--bg);border-radius:8px;
font-family:'SF Mono','Fira Code',monospace;font-size:12px;line-height:1.5;color:var(--dim);
max-height:300px;overflow-y:auto;border:1px solid rgba(51,65,85,0.3);white-space:pre-wrap;word-break:break-all}
.sp-step.expanded+.sp-detail{display:block}
.sp-detail .spd-section{margin-bottom:8px}
.sp-detail .spd-label{font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--accent);
margin-bottom:4px;font-family:inherit}
.sp-detail .spd-content{color:var(--text)}
.sp-detail .spd-content pre{margin:0;white-space:pre-wrap;word-break:break-all}
.sp-detail .spd-diff-add{color:#4ade80}
.sp-detail .spd-diff-del{color:#f87171;text-decoration:line-through}
.sp-detail .spd-copy{float:right;font-size:10px;padding:2px 8px;background:var(--surface);
border:1px solid rgba(51,65,85,0.4);border-radius:4px;color:var(--dim);cursor:pointer}
.sp-detail .spd-copy:hover{color:var(--text);border-color:var(--accent)}
.sp-thinking{padding:16px 12px;font-size:13px;line-height:1.7;color:var(--dim);min-width:380px;
white-space:pre-wrap;-webkit-user-select:text;user-select:text;overflow-y:auto;flex:1}
.sp-thinking p{margin-bottom:12px}
.sp-thinking strong{color:var(--text)}
.sp-thinking code{background:var(--card);padding:1px 6px;border-radius:4px;font-size:12px;
font-family:'SF Mono','Fira Code',monospace}
/* Drag handle — visible on mobile sheet only */
.sp-drag-handle{display:none;width:36px;height:4px;background:var(--dim);border-radius:2px;
margin:10px auto 4px;flex-shrink:0;opacity:0.4;cursor:ns-resize;touch-action:none}
/* Backdrop — visible on mobile sheet only */
.sp-backdrop{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:189;
opacity:0;transition:opacity 0.3s ease;pointer-events:none}
.sp-backdrop.show{opacity:1;pointer-events:auto}

/* ═══════════════════════════════════════════════════
   Desktop responsive — persistent sidebar, centered chat
   ═══════════════════════════════════════════════════ */
@media (min-width: 600px) {
  :root{--sidebar-width:280px}
  .msg{max-width:75%}
  .composer textarea{font-size:15px}
  .side-panel{top:52px}
}
@media (min-width: 1024px) {
  :root{--sidebar-width:300px}
  .messages{padding:16px 24px}
  .msg{max-width:75%}
  .msg.assistant .bubble{padding:12px 18px}
  .msg.user{padding:12px 18px}
  .composer{padding:12px 20px;padding-bottom:calc(12px + var(--sab))}
  .composer textarea{max-height:200px;font-size:15px;padding:12px 16px}
  .topbar h1{font-size:17px}
}
@media (min-width: 1440px) {
  :root{--sidebar-width:320px}
  .topbar{min-height:60px;padding:14px 20px;padding-top:calc(14px + var(--sat))}
  .topbar h1{font-size:18px}
  .messages{padding:24px 48px}
  .msg{max-width:75%}
  .msg.assistant .bubble{padding:16px 24px;line-height:1.6}
  .msg.user{padding:14px 22px}
  .msg.assistant .bubble h2,.msg.assistant .bubble h3{margin:14px 0 8px}
  .msg+.msg{margin-bottom:16px}
  .mode-badge{font-size:11px;padding:3px 8px}
  .composer{padding:14px 24px;padding-bottom:calc(14px + var(--sab))}
  .composer textarea{max-height:240px;font-size:15px;padding:14px 18px}
}
@media (min-width: 1800px) {
  .topbar{min-height:64px;padding:16px 24px;padding-top:calc(16px + var(--sat));gap:12px}
  .topbar h1{font-size:19px;letter-spacing:-0.01em}
  .messages{padding:28px 56px}
  .msg{max-width:75%}
  .msg.assistant .bubble{padding:18px 28px}
  .msg.user{padding:16px 24px}
  .msg+.msg{margin-bottom:18px}
  .composer{padding:16px 28px;padding-bottom:calc(16px + var(--sab))}
  .composer textarea{padding:14px 20px}
}
/* ═══════════════════════════════════════════════════
   Mobile: side panel becomes a bottom sheet overlay
   ═══════════════════════════════════════════════════ */
@media (max-width: 599px) {
  .side-panel{top:auto!important;right:0;left:0;bottom:0;
  width:100%!important;height:0;border-left:none;border-top:1px solid var(--card);
  border-radius:16px 16px 0 0;box-shadow:0 -4px 24px rgba(0,0,0,0.4);
  transition:height 0.3s cubic-bezier(0.32,0.72,0,1),transform 0.15s ease;z-index:200}
  .side-panel.open{width:100%!important;height:50vh}
  .side-panel.sheet-tall{height:85vh}
  /* Kill the desktop margin-push — sheet floats over chat */
  body.panel-open .messages,
  body.panel-open .composer,
  body.panel-open .context-bar,
  body.panel-open .attach-preview,
  body.panel-open .transcribing{margin-right:0!important;transition:none!important}
  /* Show mobile-only chrome */
  .sp-drag-handle{display:block}
  .sp-backdrop{display:block}
  /* Remove min-width hardcodes set for desktop */
  .sp-header,.sp-body,.sp-thinking{min-width:0}
  /* Settings modal becomes a bottom sheet on mobile — matches the
     /tmp/apex_ui_mockup/index.html reference design. */
  .profile-modal-overlay{padding:0;align-items:stretch}
  .profile-modal{max-width:100%;border-radius:14px 14px 0 0;max-height:95vh;
  min-height:80vh;margin-top:auto}
  .gs-tabs{padding:10px 12px}
  .gs-section{padding:12px 14px}
  .gs-level-picker{grid-template-columns:1fr!important}
  .gs-level-opt{flex-direction:row!important;align-items:center!important;gap:10px!important;
  text-align:left!important}
  .gs-level-opt strong{width:26px;height:26px;border-radius:50%;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;font-size:12px}
  .gs-perm-elev-controls{flex-direction:column;align-items:stretch}
}

/* ═══════════════════════════════════════════════════
   5-level permissions picker (per-chat tool_policy)
   ═══════════════════════════════════════════════════ */
.gs-level-picker{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:8px}
.gs-level-opt{display:flex;flex-direction:column;align-items:flex-start;gap:4px;
padding:10px;border:1px solid var(--card);border-radius:10px;background:var(--bg);
color:var(--text);cursor:pointer;text-align:left;transition:all .15s ease;min-width:0}
.gs-level-opt:hover{border-color:var(--accent);background:var(--card)}
.gs-level-opt.selected{border-color:var(--accent);background:color-mix(in srgb, var(--accent) 14%, var(--bg))}
.gs-level-opt strong{font-size:13px;font-weight:700;color:var(--accent)}
.gs-level-opt .gs-level-name{font-size:12px;font-weight:600;color:var(--text);line-height:1.2}
.gs-level-opt .gs-level-hint{font-size:10px;color:var(--dim);line-height:1.3}
.gs-perm-elev{margin-top:12px;padding-top:12px;border-top:1px solid var(--bg)}
.gs-perm-elev-controls{display:flex;gap:8px;align-items:center;margin-top:6px}
.gs-perm-elev-controls .gs-select{flex:1}
.gs-perm-allowlist{margin-top:12px;padding-top:12px;border-top:1px solid var(--bg)}
.gs-inline-btn{padding:8px 14px;border-radius:8px;border:1px solid var(--card);
background:var(--bg);color:var(--text);font-size:12px;font-weight:600;cursor:pointer;
transition:all .12s ease;white-space:nowrap}
.gs-inline-btn:hover{border-color:var(--accent);color:var(--accent)}"""
