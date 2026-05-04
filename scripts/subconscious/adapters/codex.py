"""Codex adapter — translates ContextEnvelope into Codex hook output formats.

Codex context injection points:
  1. SessionStart hook → stdout text (one-shot developer context)
  2. UserPromptSubmit hook → JSON {"systemMessage": "..."} (per-prompt)
  3. Stop hook → stderr/stdout for postmortem (no content injection)

Codex treats exit code 2 + stderr as "block session" — adapters MUST
only write to stdout and ALWAYS exit 0.

Output format differences from Claude Code:
  - SessionStart: plain text (same as Claude Code)
  - UserPromptSubmit: JSON object with "systemMessage" key (Codex-specific)
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
PROMPT_SUBMIT_BUDGET = 6000    # Codex is more tolerant of system messages


_DATE_LITERAL_RE = re.compile(r"\b(?:TODAY|today)\s*=\s*\d{4}-\d{2}-\d{2}\b")


def _refresh_today(text: str) -> str:
    """Rewrite TODAY=YYYY-MM-DD literals to live date at emission time."""
    if not text:
        return text
    return _DATE_LITERAL_RE.sub(
        f"TODAY={datetime.date.today().isoformat()}", text
    )


def render_session_start(envelope: ContextEnvelope) -> str:
    """Render full context for Codex SessionStart hook.

    Returns plain text — Codex injects this as developer context.
    Includes: guidance (invariants + corrections), recent session digests.
    """
    lines = [
        "<subconscious_context>",
        f"Background memory active. Session: {envelope.session.session_id[:8]}...",
    ]

    # Guidance items
    guidance = envelope.guidance
    if guidance:
        lines.append("")
        lines.append("## Guidance")
        char_budget = SESSION_START_BUDGET - 500
        chars_used = 0
        for mem in guidance:
            if mem.type == "invariant":
                ctx = _refresh_today(getattr(mem, "context_when", ""))
                enf = _refresh_today(getattr(mem, "enforce", ""))
                avd = _refresh_today(getattr(mem, "avoid", ""))
                if ctx and enf and avd:
                    display = f"- [invariant] When {ctx}: enforce {enf}; avoid {avd}"
                else:
                    display = f"- [invariant] {_refresh_today(mem.display_text())}"
            else:
                display = f"- [{mem.type}] {_refresh_today(mem.display_text())}"

            if chars_used + len(display) > char_budget:
                remaining = len(guidance) - len(
                    [m for m in guidance if chars_used + m.char_len() <= char_budget]
                )
                lines.append(f"- [note] {remaining} items truncated for budget")
                break
            lines.append(display)
            chars_used += len(display)

    # Recent session summaries
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
    """Render per-prompt whisper for Codex UserPromptSubmit hook.

    Returns JSON string: {"systemMessage": "<subconscious_whisper>..."}
    Returns empty string to skip injection.
    """
    whisper_lines = []

    # Session warnings
    pc = envelope.session.prompt_count
    if pc >= 80:
        whisper_lines.append(
            f"- [warning] Session is {pc} prompts deep. "
            f"Consider starting fresh to avoid token bloat."
        )
    elif pc >= 50:
        whisper_lines.append(
            f"- [note] Session at {pc} prompts. "
            f"Consider starting fresh soon."
        )

    # All guidance items on warmup, high-confidence corrections after
    if pc <= 3:
        # Full dump on first 3 prompts
        for mem in envelope.guidance:
            if mem.type == "invariant":
                ctx = _refresh_today(getattr(mem, "context_when", ""))
                enf = _refresh_today(getattr(mem, "enforce", ""))
                avd = _refresh_today(getattr(mem, "avoid", ""))
                if ctx and enf and avd:
                    whisper_lines.append(
                        f"- [invariant] When {ctx}: enforce {enf}; avoid {avd}"
                    )
                else:
                    whisper_lines.append(f"- [invariant] {_refresh_today(mem.display_text())}")
            else:
                whisper_lines.append(f"- [{mem.type}] {_refresh_today(mem.display_text())}")
    else:
        # After warmup: only high-confidence corrections
        recent_corrections = [
            m for m in envelope.guidance
            if m.type == "correction" and m.confidence >= 0.7
        ]
        for c in recent_corrections[:3]:
            whisper_lines.append(f"- [correction] {_refresh_today(c.text[:200])}")

    if not whisper_lines:
        return ""

    whisper_text = (
        "<subconscious_whisper>\n"
        + "\n".join(whisper_lines)
        + "\n</subconscious_whisper>"
    )
    return json.dumps({"systemMessage": whisper_text})


def render_stop(envelope: ContextEnvelope,
                transcript_path: str = "") -> str:
    """Render context for Codex Stop hook.

    Returns JSON for the postmortem pipeline.
    """
    return json.dumps({
        "session_id": envelope.session.session_id,
        "transcript_path": transcript_path,
        "prompt_count": envelope.session.prompt_count,
    })
