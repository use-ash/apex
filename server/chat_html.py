# Auto-extracted from apex.py during Phase 0 of monolith split.

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ApexChat">
<meta name="theme-color" content="#0F172A">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<title>Apex{{TITLE_SUFFIX}}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
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
.topbar h1{font-size:16px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
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
background:none;border:none;color:var(--text);font-size:14px;cursor:pointer;border-radius:10px;transition:background .15s ease}
.stop-menu button:hover{background:var(--bg)}
.stop-menu button:active{background:var(--bg)}
.stop-menu button .stop-dot{width:8px;height:8px;border-radius:50%;background:var(--red);
animation:dotPulse 1.2s ease-in-out infinite;flex-shrink:0}
.stop-menu button .agent-time{margin-left:auto;font-size:11px;color:var(--dim)}
.stop-menu hr{border:none;border-top:1px solid var(--card);margin:4px 0}
.stop-menu .stop-all{color:var(--red);font-weight:500}
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
padding:16px 20px;border-bottom:1px solid var(--card)}
.profile-modal-header h3{font-size:16px;font-weight:600}
.profile-modal-header button{background:none;border:none;color:var(--dim);
font-size:20px;cursor:pointer;padding:4px 8px}
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
.gs-toggle-label{font-size:13px;color:var(--text)}
.gs-toggle-hint{font-size:11px;color:var(--dim);margin-top:4px;line-height:1.4}
.gs-toggle{position:relative;width:44px;height:24px;border-radius:12px;border:none;
cursor:pointer;transition:background .2s;flex-shrink:0}
.gs-toggle.on{background:var(--accent)}
.gs-toggle.off{background:var(--card)}
.gs-toggle::after{content:'';position:absolute;top:2px;left:2px;width:20px;height:20px;
border-radius:50%;background:white;transition:transform .2s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.gs-toggle.on::after{transform:translateX(20px)}
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
.gs-toast{position:fixed;bottom:60px;left:50%;transform:translateX(-50%) translateY(20px);
background:var(--card);color:var(--text);padding:10px 20px;border-radius:20px;font-size:13px;
font-weight:500;opacity:0;transition:all .25s ease;pointer-events:none;z-index:9999;
box-shadow:0 4px 16px rgba(0,0,0,.4)}
.gs-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

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
}
</style>
</head>
<body>

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

<script nonce="{{CSP_NONCE}}">
window.onerror = (msg, src, line, col, err) => {
  document.title = 'JS ERROR: ' + msg;
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;padding:8px;z-index:9999;font-size:12px';
  d.textContent = `JS Error: ${msg} (line ${line})`;
  document.body.prepend(d);
};
let ws = null;
let currentChat = sessionStorage.getItem('currentChatId') || null;
let streaming = false;
let currentBubble = null;
let currentSpeaker = null; // {name, avatar, id} for group @mention routing
let currentStreamId = '';
let composerHasDraft = false;
let lastSubmittedPrompt = '';
const activeStreams = new Map(); // stream_id -> {name, avatar, profile_id}
// Per-stream context: supports concurrent agent streams without clobbering
const _streamCtx = {};  // stream_id -> {bubble, speaker, toolPill, toolCalls, ...}
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
}

function _elapsedLabel(startedAt) {
  if (!startedAt) return '';
  const sec = Math.round((Date.now() - startedAt) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}

function renderStopMenu() {
  const menu = document.getElementById('stopMenu');
  if (!menu) return;
  menu.innerHTML = '';
  Array.from(activeStreams.values()).forEach(stream => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.innerHTML = `<span class="stop-dot"></span>${escHtml(stream.avatar || '')} Stop ${escHtml(stream.name || 'agent')}<span class="agent-time">${_elapsedLabel(stream.startedAt)}</span>`;
    btn.onclick = () => stopStream(stream.stream_id);
    menu.appendChild(btn);
  });
  if (activeStreams.size > 1) {
    menu.appendChild(document.createElement('hr'));
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'stop-all';
    btn.textContent = 'Stop All';
    btn.onclick = () => stopAllStreams();
    menu.appendChild(btn);
  }
}

function stopStream(streamId) {
  if (!currentChat || !streamId) return;
  cancelStream(streamId).catch(err => reportError('stop stream', err));
  hideStopMenu();
}

function stopAllStreams() {
  if (!currentChat) return;
  cancelStream('').catch(err => reportError('stop all streams', err));
  hideStopMenu();
}

function toggleStopMenu() {
  const menu = document.getElementById('stopMenu');
  if (!menu || activeStreams.size <= 1) return;
  renderStopMenu();
  menu.classList.toggle('show');
}

function dbg(...args) {
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

function clearStreamWatchdog() {
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
    const resp = await fetch(`/api/chats/${currentChat}/cancel`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(streamId ? {stream_id: streamId} : {}),
    });
    if (!resp.ok && resp.status !== 204) throw new Error(`cancel failed: ${resp.status}`);
    const ids = streamId ? [streamId] : Array.from(activeStreams.keys());
    ids.forEach(sid => _finalizeStream(sid, {trackAnswered: false}));
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
    if (ws !== socket || socket.readyState !== WebSocket.OPEN) return;
  }
  dbg('sending attach:', chatId, 'reason=', reason, 'reloadBeforeAttach=', reloadBeforeAttach);
  socket.send(JSON.stringify({action: 'attach', chat_id: chatId}));
}

function resumeConnection(trigger) {
  const streamingChatId = sessionStorage.getItem('streamingChatId');
  const resumeChat = currentChat || sessionStorage.getItem('currentChatId');
  const wasStreaming = Boolean(streamingChatId && resumeChat && streamingChatId === resumeChat);
  const resumeAlertSince = lastAlertCheck;
  dbg(`${trigger}: resume state`, {wasStreaming, streamingChatId, resumeChat});

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
  const waitTimeout = setTimeout(() => {
    if (waitDone) return;
    waitDone = true;
    clearInterval(waitForOpen);
    dbg(`${trigger}: timed out waiting for ws open after 15000ms`);
  }, 15000);
  const waitForOpen = setInterval(() => {
    if (waitDone) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      waitDone = true;
      clearInterval(waitForOpen);
      clearTimeout(waitTimeout);
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
}

// --- WebSocket ---
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
    await ensureInitialized('ws-open').catch(err => reportError('init ws-open', err));
    if (resumeHandledExternally) {
      resumeHandledExternally = false;
      dbg('skipping selectChat in onopen — resume handler owns it');
    } else if (initDone) {
      const restoreChat = currentChat || sessionStorage.getItem('currentChatId');
      const streamingChatId = sessionStorage.getItem('streamingChatId');
      dbg('ws-open: restore state', {currentChat, restoreChat, streamingChatId});
      if (!restoreChat) {
        // No chat to restore
      } else if (streamingChatId && streamingChatId === restoreChat) {
        if (!currentChat) currentChat = restoreChat;
        dbg('ws-open: active stream found in sessionStorage, reattaching:', currentChat);
        await attachToStream(socket, currentChat, {
          reloadBeforeAttach: true,
          reason: 'ws-open',
        });
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
      handleEvent(msg);
    } catch (err) {
      reportError('ws message parse', err);
    }
  };
}

function startHeartbeat(socket) {
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
// Live reasoning now renders as a single pill; detailed steps live only in the side panel.
function _getOrCreateWorkGroup(bubble) {
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

function _ensureCtxBubble(ctx) {
  if (!ctx) return null;
  if (!ctx.bubble || !ctx.bubble.isConnected) {
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
  if (ctx.awaitingAck || ctx.thinkingText) {
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
  if (label) label.textContent = total === 1 ? '1 tool call' : `${total} tool calls`;
  if (dim) dim.textContent = total > 0 ? (completed >= total ? 'Complete' : 'Running') : '';
  if (counts) counts.textContent = total > 0 ? `${completed}/${total}` : '';
  if (bar) {
    const pct = total > 0 ? Math.max(8, Math.round((completed / total) * 100)) : 8;
    bar.style.width = pct + '%';
  }
}

function _finalizeToolPill(ctx, totalTime) {
  if (!ctx || !ctx.toolCalls.length) return null;
  const pill = _getOrCreateToolPill(ctx);
  if (!pill) return null;
  const total = ctx.toolCalls.length;
  const completed = ctx.toolCalls.filter(t => t.status && t.status !== 'running').length;
  pill.className = 'pill pill--tool';
  pill._toolData = ctx.toolCalls.map(t => ({
    ...t,
    result: t.result ? {...t.result} : null,
  }));
  pill._ctx = null;
  pill._totalTime = totalTime || 0;
  pill.innerHTML = `<span class="pill-icon">&#128295;</span><span class="pill-label">${total === 1 ? '1 tool call' : `${total} tool calls`}</span><span class="pill-dim">${_formatDuration(totalTime) || 'Complete'}</span><span class="pill-counts">${completed}/${total}</span><span class="pill-chevron">&#8250;</span>`;
  pill.onclick = () => openToolPanel(pill);
  return pill;
}

function _thinkingPill(ctx, options = {}) {
  if (!ctx) return null;
  const live = Boolean(options.live);
  const durationMs = options.durationMs != null
    ? options.durationMs
    : (ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0);
  if (!live && (!ctx.bubble || !ctx.thinkingText)) return null;
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
  const beforeEl = (ctx.toolPill && ctx.toolPill.isConnected) ? ctx.toolPill : bubbleEl;
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
  if (ctx.thinkingText) {
    _thinkingPill(ctx, {
      durationMs: ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0,
    });
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
  ctx.bubble.querySelectorAll('.bubble').forEach(b => b.parentElement?.classList?.remove('streaming'));
  // Cancel any pending debounced render and do a final authoritative pass
  // using the accumulated raw markdown (ctx.textContent), not el.textContent
  // which would be the text content of already-rendered HTML.
  clearTimeout(ctx._mdTimer);
  ctx._mdTimer = null;
  renderMarkdown(ctx.bubble.querySelector('.bubble'), ctx.textContent);
}

function _captureExpandedState() {
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
      const resultText = tool.result ? (typeof tool.result.content === 'string' ? tool.result.content : JSON.stringify(tool.result.content, null, 2)) : '';
      const summaryHtml = tool.summary || toolSummary(tool.name, tool.input) || '';
      const summaryText = _htmlToText(summaryHtml) || toolLabel(tool.name);
      const status = tool.status === 'error' ? '&#10007;' : (tool.status === 'completed' ? '&#10003;' : '&#9203;');
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
      if (resultText) {
        const resultNote = toolResultSummary(tool.name, resultText);
        detailHtml += `<div class="spd-section"><div class="spd-label">Result${resultNote ? ` · ${escHtml(resultNote)}` : ''}</div><div class="spd-content"><pre>${escHtml(resultText.substring(0, 5000))}</pre></div></div>`;
      }
      detail.innerHTML = detailHtml;
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

function handleEvent(msg) {
  const el = document.getElementById('messages');
  // B-42: drop stream events that belong to a different chat
  const _B42_STREAM = new Set(['stream_start','stream_ack','stream_queued','text','thinking','tool_use','tool_result','stream_end','active_streams']);
  if (_B42_STREAM.has(msg.type) && msg.chat_id && currentChat && msg.chat_id !== currentChat) {
    dbg('B42: drop cross-chat', msg.type, msg.chat_id);
    return;
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
      hideStopMenu();
      updateSendBtn();

      refreshDebugState('stream-queued');
      break;
    }

    case 'text': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      _ensureCtxBubble(ctx);
      _activateStream(ctx);
      if (ctx.awaitingAck && !ctx.thinkingText) {
        _teardownThinking(ctx);
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
      const ctx = _getCtx(msg);
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
      const ctx = _getCtx(msg);
      if (!ctx) break;
      _ensureCtxBubble(ctx);
      _activateStream(ctx);
      if (ctx.awaitingAck && !ctx.thinkingText) {
        _teardownThinking(ctx);
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
      ctx.awaitingAck = false;
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
        selectChat(msg.chat_id).catch(() => {});
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

// --- UI helpers ---
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
  // Escape text, then linkify markdown-style [label](/path) for internal links only
  // Regex literal keeps the pattern readable and avoids string-escape collapse.
  const safe = escHtml(text).replace(
    /\\[([^\\]]+)\\]\\((\\/[^)]+)\\)/g,
    '<a href="$2" target="_blank" style="color:var(--accent);text-decoration:underline">$1</a>'
  );
  bubble.innerHTML = `<div>${safe}</div>`;
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

/* --- Smart scroll: only auto-scroll if user is near bottom --- */
let _userScrolledUp = false;
const _SCROLL_THRESHOLD = 150; // px from bottom to count as "near bottom"

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

// Attach scroll listener once DOM is ready
(function _initScrollWatch() {
  function attach() {
    const el = document.getElementById('messages');
    if (!el) { setTimeout(attach, 100); return; }
    el.addEventListener('scroll', () => {
      if (_programmaticScroll) return;
      _userScrolledUp = !_isNearBottom();
      if (!_userScrolledUp) _hideNewContentPill();
    }, {passive: true});
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
})();

// --- Alerts channel view (renders in main messages area) ---
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
const ALERT_BODY_ALLOWED_TAGS = new Set(['b', 'strong', 'em', 'i', 'code', 'br', 'ul', 'ol', 'li']);
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
    Array.from(child.attributes).forEach((attr) => child.removeAttribute(attr.name));
    sanitizeAlertBodyNode(child);
  });
}
function renderAlertBody(raw) {
  const text = String(raw || '').split('\\\\n').join('\\n');
  const doc = new DOMParser().parseFromString('<div>' + text + '</div>', 'text/html');
  const root = doc.body.firstElementChild || doc.body;
  sanitizeAlertBodyNode(root);
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

// --- Settings Panel ---
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

function escHtml(s) {
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

function renderInlineMarkdown(text) {
  let html = escHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\\*\\*\\*([^*]+)\\*\\*\\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  html = html.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
  return html;
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
  const showStop = (streaming || _isAnyStreamActive()) && !composerHasDraft;
  if (showStop) {
    btn.innerHTML = '&#9632;';
    btn.className = 'btn-compose compose-action is-stop';
    btn.disabled = !canSend;
    btn.title = activeStreams.size > 1 ? 'Choose stream to stop' : 'Stop';
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

// --- Send ---
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

// --- Chats ---
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

async function selectChat(id, title, chatType, category) {
  // Debounce: skip if same chat selected within 500ms
  const now = Date.now();
  if (id === _lastSelectChatId && now - _lastSelectChatTime < 500) {
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
    Object.keys(_streamCtx).forEach(sid => { delete _streamCtx[sid]; });
    clearComposerDraft();
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
  if (ws && ws.readyState === WebSocket.OPEN) {
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
  const el = document.getElementById('messages');
  el.innerHTML = '';
  msgs.forEach(m => {
    if (m.role === 'user') {
      addUserMsg(m.content || '', m.attachments || []);
    } else {
      const div = document.createElement('div');
      div.className = 'msg assistant';
      let inner = '';
      // Speaker identity header for group messages
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
      el.appendChild(div);
      const historyCtx = _newStreamCtx('', m.speaker_name ? {name: m.speaker_name, avatar: m.speaker_avatar || '', id: m.speaker_id || ''} : null);
      historyCtx.bubble = div;
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
      if (m.thinking && m.thinking.trim()) {
        historyCtx.thinkingText = m.thinking;
        _thinkingPill(historyCtx, {durationMs: 0});
      }
      div.querySelectorAll('.bubble').forEach(el => renderMarkdown(el));
    }
  });
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

// --- Sidebar ---
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

// --- Attachments ---
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

// --- PWA service worker ---
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
  if ((streaming || _isAnyStreamActive()) && !composerHasDraft) {
    if (activeStreams.size > 1) {
      toggleStopMenu();
    } else if (activeStreams.size === 1) {
      stopStream(activeStreams.keys().next().value || '');
    } else {
      stopAllStreams();
    }
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

// --- Context bar ---
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

// --- Usage bar (model-aware, toggleable) ---
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

// --- Agent Profiles ---
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
  skipBtn.textContent = 'Plain Chat';
  skipBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newChat().catch(err => reportError('newChat skip', err));
  };
  actions.appendChild(skipBtn);

  const createBtn = document.createElement('button');
  createBtn.className = 'btn-create';
  createBtn.textContent = 'Create Channel';
  createBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newChatWithProfile(selectedProfileId).catch(err => reportError('newChat profile', err));
  };
  actions.appendChild(createBtn);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

async function newChatWithProfile(profileId) {
  dbg(' creating new chat with profile:', profileId || '(none)');
  const body = profileId ? JSON.stringify({profile_id: profileId}) : undefined;
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

// --- Group Settings Modal ---
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

function describeChatToolPolicy(policy) {
  const level = Number((policy && policy.level) || 2);
  if (level <= 0) return 'Restricted';
  if (level === 1) return 'Standard Tools';
  if (level === 2) return 'Workspace Tools';
  return 'Admin Allowlist';
}

async function showDirectChatPermissions() {
  if (!currentChat || currentChatType !== 'chat' || _currentChatProfileId) return;
  document.querySelector('.profile-dropdown')?.remove();
  document.querySelector('.profile-modal-overlay')?.remove();

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
      showToast('Failed to load chat permissions');
      return;
    }
  } catch (e) {
    reportError('showDirectChatPermissions', e);
    showToast('Failed to load chat permissions');
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
        </select>
      </label>
      <label style="display:grid;gap:6px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Allowed Commands</span>
        <textarea id="chat-perm-commands" class="gs-name-input" rows="5" placeholder="One command prefix per line, e.g.&#10;git push&#10;sqlite3"></textarea>
        <span style="font-size:12px;color:var(--dim)">Used only for Admin Allowlist. Bash commands must start with one of these prefixes.</span>
      </label>
      <label style="display:grid;gap:6px">
        <span style="font-size:12px;font-weight:600;color:var(--dim)">Temporary Admin Minutes</span>
        <input id="chat-perm-minutes" class="gs-name-input" type="number" min="1" max="1440" placeholder="15" />
        <span id="chat-perm-expiry" style="font-size:12px;color:var(--dim)"></span>
      </label>
      <div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">
        <button id="chat-perm-revoke" class="gs-inline-btn" type="button">Reset to Default</button>
        <button id="chat-perm-save" class="gs-add-btn" type="button" style="margin:0">Save</button>
      </div>
    </div>`;

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const levelEl = body.querySelector('#chat-perm-level');
  const commandsEl = body.querySelector('#chat-perm-commands');
  const minutesEl = body.querySelector('#chat-perm-minutes');
  const expiryEl = body.querySelector('#chat-perm-expiry');
  const saveBtn = body.querySelector('#chat-perm-save');
  const revokeBtn = body.querySelector('#chat-perm-revoke');
  const defaultLevel = Number(policy.default_level || 2);

  function syncExpiryText() {
    if (policy.elevated_until) {
      expiryEl.textContent = `Current expiry: ${new Date(policy.elevated_until).toLocaleString()}`;
    } else {
      expiryEl.textContent = `Default level: ${describeChatToolPolicy({level: defaultLevel})}`;
    }
  }

  levelEl.value = String(Number(policy.level || defaultLevel));
  commandsEl.value = (policy.allowed_commands || []).join('\\n');
  minutesEl.value = '';
  syncExpiryText();

  revokeBtn.onclick = async () => {
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
      minutesEl.value = '';
      syncExpiryText();
      showToast('Chat permissions reset');
    } catch (e) {
      reportError('revokeChatToolPolicy', e);
      showToast('Failed to reset chat permissions');
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
      syncExpiryText();
      showToast(`Chat permissions saved: ${describeChatToolPolicy(policy)}`);
    } catch (e) {
      reportError('saveChatToolPolicy', e);
      showToast('Failed to save chat permissions');
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

// --- Persona Info Card (F-1) ---
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
    dbg('app resumed from background');
    resumeConnection('visibilitychange');
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
})();
</script>
</body>
</html>"""
