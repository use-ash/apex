#!/opt/homebrew/bin/python3
"""SessionStart hook — loads background memory context for new sessions.

Uses the canonical store to build a unified context envelope, then renders
it via the Claude Code adapter. Falls back to direct guidance.json read
if the canonical store fails.
"""

import datetime
import json
import re
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state


_DATE_LITERAL_RE = re.compile(r"\b(?:TODAY|today)\s*=\s*\d{4}-\d{2}-\d{2}\b")


def _refresh_today(text: str) -> str:
    """Rewrite TODAY=YYYY-MM-DD literals to live date at emission time."""
    if not text:
        return text
    return _DATE_LITERAL_RE.sub(
        f"TODAY={datetime.date.today().isoformat()}", text
    )


def _canonical_render(session_id: str) -> str | None:
    """Try to render via canonical store + Claude Code adapter."""
    try:
        from canonical_store import CanonicalStore
        from adapters.claude_code import render_session_start

        store = CanonicalStore()
        envelope = store.build_envelope(
            backend="claude_code",
            session_id=session_id,
        )
        return render_session_start(envelope)
    except Exception:
        return None


def _legacy_render(session_id: str) -> str:
    """Original rendering — direct guidance.json + digests read."""
    guidance = state.read_guidance()
    items = guidance.get("items", [])

    recent = state.list_recent_sessions(3)
    digests = []
    for s in recent:
        sid = s.get("session_id", "")
        if sid and sid != session_id:
            d = state.load_digest(sid)
            if d:
                digests.append((sid, s.get("started_at", ""), d))

    lines = [
        "<subconscious_context>",
        f"Background memory active. Session: {session_id[:8]}...",
    ]

    if items:
        lines.append("")
        lines.append("## Guidance")
        for item in items:
            lines.append(f"- [{item.get('type', 'note')}] {_refresh_today(item.get('text', ''))}")

    if digests:
        lines.append("")
        lines.append("## Recent Sessions")
        for sid, started_at, d in digests:
            summary = d.get("summary", {})
            summary_text = (summary.get("text", "")
                            if isinstance(summary, dict) else str(summary))
            if summary_text:
                lines.append(f"- {sid[:8]} ({started_at}): {summary_text}")

    lines.append("</subconscious_context>")

    if not items and not digests:
        return (f"<subconscious_context>\n"
                f"Background memory active. Session: {session_id[:8]}...\n"
                f"</subconscious_context>")
    return "\n".join(lines)


def main():
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            return
        raw = sys.stdin.read()
        if not raw.strip():
            return
        payload = json.loads(raw)
        session_id = payload.get("session_id", "")
        cwd = payload.get("cwd", "")

        if not session_id:
            return

        config.ensure_dirs()
        state.register_session(session_id, cwd)

        # Try canonical store first, fall back to legacy
        output = _canonical_render(session_id)
        if not output:
            output = _legacy_render(session_id)

        print(output)

    except Exception:
        pass


if __name__ == "__main__":
    main()
