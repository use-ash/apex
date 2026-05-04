"""Claude Code adapter — translates ContextEnvelope into Claude Code injection formats.

Claude Code context injection points:
  1. SessionStart hook → stdout text (one-shot, injected at session start)
  2. UserPromptSubmit hook → stdout text (per-prompt, wired in settings.json)
  3. CLAUDE.md files → read at session start (static)
  4. settings.json → permissions only (no content injection)

This adapter renders ContextEnvelope for points 1 and 2.
"""

import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_store import ContextEnvelope, Memory


# Token budget estimates (chars, not tokens — conservative 4:1 ratio)
SESSION_START_BUDGET = 16000   # One-shot injection at start
PROMPT_SUBMIT_BUDGET = 4000   # Per-prompt refresh (lightweight)


_DATE_LITERAL_RE = re.compile(r"\b(?:TODAY|today)\s*=\s*\d{4}-\d{2}-\d{2}\b")


def _refresh_today(text: str) -> str:
    """Rewrite TODAY=YYYY-MM-DD literals to live date at emission time."""
    if not text:
        return text
    return _DATE_LITERAL_RE.sub(
        f"TODAY={datetime.date.today().isoformat()}", text
    )


def render_session_start(envelope: ContextEnvelope) -> str:
    """Render full context for SessionStart hook.

    This is the one-shot injection that sets up the session.
    Includes: guidance (invariants + corrections), recent session digests,
    session metadata.
    """
    lines = [
        "<subconscious_context>",
        f"Background memory active. Session: {envelope.session.session_id[:8]}...",
    ]

    # Guidance items (invariants and corrections)
    guidance = envelope.guidance
    if guidance:
        lines.append("")
        lines.append("## Guidance")
        char_budget = SESSION_START_BUDGET - 500  # reserve for header/footer
        chars_used = 0
        for mem in guidance:
            display = f"- [{mem.type}] {_refresh_today(mem.display_text())}"
            if chars_used + len(display) > char_budget:
                lines.append(f"- [note] {len(guidance) - len([m for m in guidance if m.char_len() + chars_used <= char_budget])} items truncated for budget")
                break
            lines.append(display)
            chars_used += len(display)

    # Recent session summaries (from memories with source=digest)
    digest_mems = [m for m in envelope.memories
                   if m.source == "digest" and m.type == "context"]
    if digest_mems:
        lines.append("")
        lines.append("## Recent Sessions")
        for m in digest_mems[:3]:
            lines.append(f"- {m.source_id}: {m.text[:200]}")

    lines.append("</subconscious_context>")
    return "\n".join(lines)


def render_prompt_submit(envelope: ContextEnvelope,
                         current_prompt: str = "") -> str:
    """Render lightweight context for UserPromptSubmit hook.

    This fires on every prompt. Keep it small — only inject when there's
    something new or important to say. Returns empty string to skip injection.

    Injects:
      - Session energy/phase warnings
      - New guidance items since last injection
      - Prompt count warnings
    """
    lines = []

    # Session warnings
    pc = envelope.session.prompt_count
    if pc >= 80:
        lines.append(
            f"- [warning] Session is {pc} prompts deep. "
            f"Consider starting fresh to avoid token bloat."
        )
    elif pc >= 50:
        lines.append(
            f"- [note] Session at {pc} prompts. "
            f"Consider starting fresh soon."
        )

    # High-confidence corrections (only recent ones)
    recent_corrections = [
        m for m in envelope.guidance
        if m.type == "correction" and m.confidence >= 0.7
    ]
    if recent_corrections:
        for c in recent_corrections[:3]:
            lines.append(f"- [correction] {_refresh_today(c.text[:200])}")

    if not lines:
        return ""

    return (
        "<subconscious_whisper>\n"
        + "\n".join(lines)
        + "\n</subconscious_whisper>"
    )


def render_stop(envelope: ContextEnvelope,
                transcript_path: str = "") -> str:
    """Render context for Stop/StopFailure hook.

    Currently just passes through to the existing postmortem pipeline.
    Future: could include session scoring, memory promotion suggestions.
    """
    return json.dumps({
        "session_id": envelope.session.session_id,
        "transcript_path": transcript_path,
        "prompt_count": envelope.session.prompt_count,
    })
