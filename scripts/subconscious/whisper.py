#!/opt/homebrew/bin/python3
"""UserPromptSubmit hook — whispers guidance on each prompt.

Uses the canonical store when available, falls back to direct guidance.json.

Token optimization: full whisper on first 3 turns, then only when
the guidance state has changed since the last emission.
"""

import datetime
import hashlib
import json
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state

WARMUP_TURNS = 3  # always emit for the first N prompts
MIN_ITEMS_FOR_WHISPER = 5  # don't inject until guidance has enough signal
INTRO_MARKER_FILE = "whisper_introduced"  # tracks whether the user has seen the intro


def _guidance_hash(items: list) -> str:
    raw = json.dumps(items, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _load_guidance_items() -> list[dict]:
    """Load guidance via canonical store, fall back to raw guidance.json."""
    try:
        from canonical_store import CanonicalStore
        store = CanonicalStore()
        memories = store.get_guidance(min_confidence=0.3)
        # Convert Memory objects back to dict form for hash + rendering
        items = []
        for m in memories:
            item = {
                "type": m.type,
                "text": m.display_text(),
                "confidence": m.confidence,
            }
            if m.type == "invariant":
                item["context"] = m.context_when
                item["enforce"] = m.enforce
                item["avoid"] = m.avoid
            items.append(item)
        return items
    except Exception:
        # Fall back to direct guidance.json read
        guidance = state.read_guidance()
        items = guidance.get("items", [])
        return [i for i in items if i.get("confidence", 0) >= 0.3]


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

        if not session_id:
            return

        relevant = _load_guidance_items()

        # Progressive disclosure: stay silent until enough items accumulate
        intro_path = Path(config.STATE_DIR) / INTRO_MARKER_FILE
        has_been_introduced = intro_path.exists()

        if not has_been_introduced and len(relevant) < MIN_ITEMS_FOR_WHISPER:
            # Silent phase: system is learning, don't inject anything yet.
            # Still update session state so prompt_count tracks correctly.
            session = state.get_session(session_id)
            prompt_count = (session.get("prompt_count", 0) + 1) if session else 1
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state.update_session(
                session_id,
                last_prompt_at=now,
                prompt_count=prompt_count,
            )
            return

        # Increment prompt count
        session = state.get_session(session_id)
        prompt_count = (session.get("prompt_count", 0) + 1) if session else 1

        # First time we have enough items: emit intro and mark as introduced
        if not has_been_introduced:
            try:
                intro_path.parent.mkdir(parents=True, exist_ok=True)
                intro_path.write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
            except OSError:
                pass

        # Decide whether to emit
        current_hash = _guidance_hash(relevant)
        last_hash = session.get("last_whisper_hash", "") if session else ""
        should_emit = (
            prompt_count <= WARMUP_TURNS
            or current_hash != last_hash
            or prompt_count >= 50
        )

        if should_emit:
            invariants = [i for i in relevant if i.get("type") == "invariant"]
            others = [i for i in relevant if i.get("type") != "invariant"]
            lines = ["<subconscious_whisper>"]

            for item in invariants:
                ctx = item.get("context", "")
                enf = item.get("enforce", "")
                avd = item.get("avoid", "")
                if ctx and enf and avd:
                    lines.append(f"- [invariant] When {ctx}: enforce {enf}; avoid {avd}")
                else:
                    lines.append(f"- [invariant] {item.get('text', '')}")

            for item in others:
                lines.append(f"- [{item.get('type', 'note')}] {item.get('text', '')}")

            if prompt_count >= 80:
                lines.append(
                    f"- [warning] Session is {prompt_count} prompts deep. "
                    f"Start a fresh session or /compact to save tokens."
                )
            elif prompt_count >= 50:
                lines.append(
                    f"- [note] Session at {prompt_count} prompts. "
                    f"Consider starting fresh soon."
                )

            # Surface pending contradictions (only on first 3 turns to avoid noise)
            if prompt_count <= WARMUP_TURNS:
                try:
                    from contradiction_detector import list_pending
                    pending = list_pending()
                    if pending:
                        lines.append(f"- [attention] {len(pending)} memory contradiction(s) need review:")
                        for c in pending[:3]:
                            a_text = c.get("claim_a", {}).get("text", "?")[:80]
                            b_text = c.get("claim_b", {}).get("text", "?")[:80]
                            lines.append(f"  Claim A: \"{a_text}\"")
                            lines.append(f"  Claim B: \"{b_text}\"")
                            lines.append(f"  (resolve with: python3 contradiction_detector.py --resolve {c.get('id', '?')} --keep a|b)")
                        if len(pending) > 3:
                            lines.append(f"  ...and {len(pending) - 3} more")
                except Exception:
                    pass  # Never block whisper on contradiction detector errors

            if len(lines) > 1:
                lines.append("</subconscious_whisper>")
                print("\n".join(lines))

        # Update session state
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state.update_session(
            session_id,
            last_prompt_at=now,
            prompt_count=prompt_count,
            last_whisper_hash=current_hash,
        )

    except Exception:
        pass


if __name__ == "__main__":
    main()
