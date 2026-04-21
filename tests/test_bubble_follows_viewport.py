"""
Regression test for Bug #5: streaming assistant bubble should NOT follow the
viewport when the user switches chats mid-stream.

Scenario:
  1. Click chat A, send a prompt that produces a streaming reply.
  2. Wait for streaming text to start accumulating in A.
  3. Switch to chat B before the stream ends.
  4. Verify chat B's #messages does NOT contain a [data-stream-id] bubble
     whose content came from A.
  5. Switch back to chat A.
  6. Verify A still owns the bubble and text has accumulated.

Runs against the dev server at https://localhost:8301 with the mTLS client cert.
Uses two pre-existing Claude Opus chats on dev:
  A = b9aa2863  ("testing")
  B = 35bb7925  ("Hello Opus 4.7!")
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

SSL_DIR = Path(os.path.expanduser("~/.openclaw/apex/state/ssl"))
CERT = SSL_DIR / "client_new.crt"
KEY = SSL_DIR / "client_new.key"

BASE_URL = os.environ.get("APEX_TEST_URL", "https://localhost:8301")
CHAT_A = "35bb7925"  # "Hello Opus 4.7!"
CHAT_B = "924b73aa"  # "Use the interceptor MCP tools..."

PROMPT = (
    "Write a detailed 400-word essay about the history of the typewriter, "
    "from the 1714 Mill patent through to the IBM Selectric. Include specific "
    "dates, inventors, and model names. Be thorough."
)

# How long to wait for the stream to first produce visible text before switching
STREAM_WARMUP_SEC = 1.2
# How long to let A continue streaming after switching to B (so B-viewport can't race)
LINGER_ON_B_SEC = 5.0
# Unique marker in the prompt — so we can check B's DOM doesn't contain A's reply
# (The reply will mention typewriter / Mill / Selectric regardless of how Opus phrases it.)
A_REPLY_MARKERS = ("typewriter", "Selectric", "Mill", "1714", "Sholes", "Remington")


def run() -> int:
    from playwright.sync_api import sync_playwright

    if not CERT.exists() or not KEY.exists():
        print(f"FAIL: client cert missing at {CERT} / {KEY}")
        return 2

    failures: list[str] = []
    evidence: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True,
            client_certificates=[
                {
                    "origin": BASE_URL,
                    "certPath": str(CERT),
                    "keyPath": str(KEY),
                }
            ],
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        page.on("console", lambda msg: None)  # quiet; enable if debugging

        print(f"[test] navigate {BASE_URL}/")
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)

        # Wait for chat-item list to populate.
        page.wait_for_selector(f'.chat-item[data-id="{CHAT_A}"]', timeout=15_000)
        page.wait_for_selector(f'.chat-item[data-id="{CHAT_B}"]', timeout=15_000)
        print("[test] chat sidebar populated")

        # --- Step 1: open chat A and send prompt ---
        # currentChat is a module-scope let, not on window. Use the .active
        # sidebar marker + sessionStorage to determine which chat is open.
        page.click(f'.chat-item[data-id="{CHAT_A}"]')
        page.wait_for_selector(
            f'.chat-item.active[data-id="{CHAT_A}"]', timeout=10_000
        )
        print(f"[test] active chat = {CHAT_A}")

        page.fill("#input", PROMPT)
        page.click("#sendBtn")
        print(f"[test] sent prompt to chat {CHAT_A}")

        # --- Step 2: wait for a streaming bubble to appear and accumulate text ---
        stream_info = page.wait_for_function(
            """
            () => {
              const msgs = document.getElementById('messages');
              if (!msgs) return null;
              const nodes = msgs.querySelectorAll('[data-stream-id]');
              for (const n of nodes) {
                const bubble = n.querySelector('.bubble');
                const txt = (bubble?.textContent || '').trim();
                if (txt.length >= 3) {
                  return { sid: n.dataset.streamId, len: txt.length, sample: txt.slice(0, 120) };
                }
              }
              return null;
            }
            """,
            timeout=30_000,
            polling=200,
        ).json_value()
        a_stream_id = stream_info["sid"]
        a_initial_text = stream_info["sample"]
        print(f"[test] stream started in A: sid={a_stream_id} len={stream_info['len']} sample={a_initial_text!r}")
        evidence["a_stream_id"] = a_stream_id
        evidence["a_initial_sample"] = a_initial_text

        # Give it a couple of ticks to accumulate more tokens.
        time.sleep(STREAM_WARMUP_SEC)

        a_mid_len = page.evaluate(
            """
            (sid) => {
              const n = document.querySelector(`[data-stream-id="${sid}"] .bubble`);
              return n ? (n.textContent || '').length : -1;
            }
            """,
            a_stream_id,
        )
        print(f"[test] after warmup, A bubble length = {a_mid_len}")
        evidence["a_mid_len"] = a_mid_len
        if a_mid_len < 3:
            failures.append(f"A bubble never accumulated text (len={a_mid_len})")

        # --- Step 3: switch to chat B mid-stream ---
        page.click(f'.chat-item[data-id="{CHAT_B}"]')
        page.wait_for_selector(
            f'.chat-item.active[data-id="{CHAT_B}"]', timeout=10_000
        )
        print(f"[test] active chat = {CHAT_B}")

        # Let A keep streaming for a bit so any viewport-follow bug has time to manifest.
        time.sleep(LINGER_ON_B_SEC)

        # --- Step 4: assert B's #messages has no bubble carrying A's stream ---
        b_snapshot = page.evaluate(
            """
            ({sid, markers}) => {
              const msgs = document.getElementById('messages');
              if (!msgs) return { found: false, bubbles: [], bodyText: '' };
              const all = msgs.querySelectorAll('[data-stream-id]');
              const info = Array.from(all).map(n => ({
                sid: n.dataset.streamId,
                text: (n.querySelector('.bubble')?.textContent || '').slice(0, 200),
              }));
              const sameSid = info.some(b => b.sid === sid);
              const activeItem = document.querySelector('.chat-item.active');
              const bodyText = (msgs.textContent || '').toLowerCase();
              const hits = markers.filter(m => bodyText.includes(m.toLowerCase()));
              return {
                currentChat: activeItem ? activeItem.dataset.id : null,
                sameSidFound: sameSid,
                bubbles: info,
                msgsChildCount: msgs.children.length,
                markerHits: hits,
              };
            }
            """,
            {"sid": a_stream_id, "markers": list(A_REPLY_MARKERS)},
        )
        print(f"[test] B snapshot: {b_snapshot}")
        evidence["b_snapshot"] = b_snapshot

        if b_snapshot["currentChat"] != CHAT_B:
            failures.append(f"currentChat expected {CHAT_B}, got {b_snapshot['currentChat']}")
        if b_snapshot["sameSidFound"]:
            failures.append(
                f"BUG #5 REGRESSION: chat B's #messages contains bubble with A's stream-id {a_stream_id}"
            )
        # Also check no bubble text matches A's initial text (belt-and-suspenders).
        for bubble in b_snapshot["bubbles"]:
            if a_initial_text and a_initial_text[:20] in bubble["text"]:
                failures.append(
                    f"BUG #5 REGRESSION: chat B has a bubble whose text matches A's stream prefix ({a_initial_text[:40]!r})"
                )
        # Content-level check: A's reply should contain typewriter-related markers.
        # If B's body text contains those markers, A's reply leaked into B's viewport.
        if b_snapshot.get("markerHits"):
            failures.append(
                f"BUG #5 REGRESSION: chat B #messages contains A's reply content. Marker hits: {b_snapshot['markerHits']}"
            )

        # --- Step 5: switch back to A ---
        page.click(f'.chat-item[data-id="{CHAT_A}"]')
        page.wait_for_selector(
            f'.chat-item.active[data-id="{CHAT_A}"]', timeout=10_000
        )
        print(f"[test] back to active chat = {CHAT_A}")
        # selectChat() asynchronously fetches /api/messages — wait for DOM swap.
        # Either the typewriter marker appears OR the streaming bubble reattaches.
        try:
            page.wait_for_function(
                """
                (markers) => {
                  const msgs = document.getElementById('messages');
                  if (!msgs) return false;
                  const txt = (msgs.textContent || '').toLowerCase();
                  if (markers.some(m => txt.includes(m.toLowerCase()))) return true;
                  // or: a streaming bubble has reattached in A
                  if (msgs.querySelector('[data-stream-id] .bubble')) {
                    const t = msgs.querySelector('[data-stream-id] .bubble').textContent || '';
                    if (t.length > 50) return true;
                  }
                  return false;
                }
                """,
                arg=list(A_REPLY_MARKERS),
                timeout=15_000,
                polling=200,
            )
        except Exception as e:
            print(f"[test] WARN waiting for A content reload: {e}")

        # After stream_end the bubble loses its data-stream-id and becomes a
        # regular completed assistant message. So look up by content instead.
        a_recovered = page.evaluate(
            """
            ({sid, markers}) => {
              const msgs = document.getElementById('messages');
              if (!msgs) return { found: false };
              const activeItem = document.querySelector('.chat-item.active');
              const stillStreaming = !!msgs.querySelector(`[data-stream-id="${sid}"]`);
              const bodyText = (msgs.textContent || '').toLowerCase();
              const hits = markers.filter(m => bodyText.includes(m.toLowerCase()));
              return {
                currentChat: activeItem ? activeItem.dataset.id : null,
                stillStreaming,
                msgsChildCount: msgs.children.length,
                markerHits: hits,
                bodySample: (msgs.textContent || '').slice(0, 400),
              };
            }
            """,
            {"sid": a_stream_id, "markers": list(A_REPLY_MARKERS)},
        )
        print(f"[test] A recovered: {a_recovered}")
        evidence["a_recovered"] = a_recovered

        if a_recovered.get("currentChat") != CHAT_A:
            failures.append(
                f"After switching back, active chat is {a_recovered.get('currentChat')}, expected {CHAT_A}"
            )
        if not a_recovered.get("markerHits"):
            failures.append(
                f"After switching back to A, none of the expected markers {A_REPLY_MARKERS!r} were found in #messages. "
                f"Body sample: {a_recovered.get('bodySample', '')[:300]!r}"
            )

        # Best-effort cleanup: try to stop the in-flight stream in chat A.
        try:
            page.evaluate(
                """
                async (cid) => {
                  try { await fetch('/api/chats/' + cid + '/stop', {method:'POST'}); } catch(e) {}
                }
                """,
                CHAT_A,
            )
        except Exception:
            pass

        context.close()
        browser.close()

    print("\n================ RESULT ================")
    for k, v in evidence.items():
        print(f"  {k}: {v}")
    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: Bug #5 fix holds — bubble did not follow the viewport.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
