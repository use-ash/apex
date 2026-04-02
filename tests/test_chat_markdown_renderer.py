from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from chat_html import CHAT_HTML  # noqa: E402


def _extract_js_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start == -1:
        raise AssertionError(f"could not find {name} in chat_html.py")

    brace_start = source.find("{", start)
    if brace_start == -1:
        raise AssertionError(f"could not find opening brace for {name}")

    depth = 0
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]

    raise AssertionError(f"could not find closing brace for {name}")


class ChatMarkdownRendererTests(unittest.TestCase):
    def _run_js(self, script: str) -> str:
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout

    def _render_markdown(self, raw_text: str) -> str:
        source = CHAT_HTML
        esc_html = _extract_js_function(source, "escHtml")
        render_inline = _extract_js_function(source, "renderInlineMarkdown")
        render_markdown = _extract_js_function(source, "renderMarkdown")

        node_script = textwrap.dedent(
            f"""
            global.document = {{
              createElement() {{
                let value = '';
                return {{
                  set textContent(v) {{ value = String(v ?? ''); }},
                  get innerHTML() {{
                    return value
                      .replace(/&/g, '&amp;')
                      .replace(/"/g, '&quot;')
                      .replace(/'/g, '&#x27;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;');
                  }},
                }};
              }},
            }};

            {esc_html}
            {render_inline}
            {render_markdown}

            const el = {{ textContent: {raw_text!r}, innerHTML: '' }};
            renderMarkdown(el);
            process.stdout.write(el.innerHTML);
            """
        )
        return self._run_js(node_script)

    def test_numbered_list_keeps_agent_mentions(self) -> None:
        rendered = self._render_markdown(
            "1. **Server health probe** — @Codex runs a fresh `curl` against `:8301/health`."
        )
        self.assertIn("<ol>", rendered)
        self.assertIn("@Codex", rendered)
        self.assertIn("<strong>Server health probe</strong>", rendered)

    def test_bullet_list_keeps_agent_mentions(self) -> None:
        rendered = self._render_markdown(
            "- @Architect reviews the plan\n- @Designer reviews the handoff copy"
        )
        self.assertIn("<ul>", rendered)
        self.assertIn("@Architect", rendered)
        self.assertIn("@Designer", rendered)

    def test_rebuild_active_stream_ui_restores_queue_state(self) -> None:
        source = CHAT_HTML
        rebuild_stream_ui = _extract_js_function(source, "_rebuildActiveStreamUi")

        output = self._run_js(
            textwrap.dedent(
                f"""
                const calls = [];
                function _teardownThinking() {{ calls.push('teardown'); }}
                function _ensureCtxBubble(ctx) {{
                  calls.push('ensure');
                  ctx.bubble = {{
                    querySelector() {{
                      return {{ innerHTML: '' }};
                    }},
                  }};
                }}
                function _renderQueuedState(ctx, payload) {{
                  calls.push(['queued', payload.position, payload.queued_label]);
                }}
                function _clearQueuedState() {{ calls.push('clear'); }}
                function renderMarkdown(_el, text) {{ calls.push(['render', text]); }}
                function _updateToolPillProgress() {{ calls.push('tools'); }}
                function _thinkingPill(_ctx, options) {{ calls.push(['thinking', Boolean(options.live)]); }}
                {rebuild_stream_ui}
                const ctx = {{
                  queued: true,
                  queuedPosition: 2,
                  speaker: {{name: 'CodeExpert'}},
                  toolCalls: [],
                  thinkingText: '',
                  awaitingAck: false,
                }};
                _rebuildActiveStreamUi(ctx);
                process.stdout.write(JSON.stringify(calls));
                """
            )
        )

        self.assertIn('["queued",2,"Queued for CodeExpert"]', output)
        self.assertNotIn('["render",', output)

    def test_stale_bar_target_prefers_bar_then_watchdog(self) -> None:
        source = CHAT_HTML
        stale_bar_target = _extract_js_function(source, "_staleBarTarget")

        output = self._run_js(
            textwrap.dedent(
                f"""
                let mode = 'bar';
                const staleBar = {{
                  dataset: {{
                    streamId: 'bar-stream',
                    profileId: 'bar-agent',
                  }},
                }};
                global.document = {{
                  getElementById(id) {{
                    if (id !== 'staleBar') return null;
                    if (mode === 'bar') return staleBar;
                    return {{dataset: {{streamId: '', profileId: ''}}}};
                  }},
                }};
                function _pickWatchdogTarget() {{
                  return {{
                    ctx: {{
                      id: 'watchdog-stream',
                      speaker: {{id: 'watchdog-agent'}},
                    }},
                  }};
                }}
                {stale_bar_target}
                const fromBar = _staleBarTarget();
                mode = 'watchdog';
                const fromWatchdog = _staleBarTarget();
                process.stdout.write(JSON.stringify({{fromBar, fromWatchdog}}));
                """
            )
        )

        self.assertIn('"streamId":"bar-stream"', output)
        self.assertIn('"profileId":"bar-agent"', output)
        self.assertIn('"streamId":"watchdog-stream"', output)
        self.assertIn('"profileId":"watchdog-agent"', output)


if __name__ == "__main__":
    unittest.main()
