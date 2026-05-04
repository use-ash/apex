#!/opt/homebrew/bin/python3
"""Batch-run digests on unprocessed session transcripts.

Usage: /opt/homebrew/bin/python3 scripts/subconscious/batch_digest.py [--days 2] [--force]

Finds all .jsonl transcripts from the last N days, skips ones that already
have digests, and runs the extraction pipeline on the rest.

Large transcripts are chunked (~12KB per chunk, max 30 messages) to avoid
hanging the LLM on 80KB single-shot prompts. Results are merged across chunks.
"""

import argparse
import datetime
import json
import os
import re
import signal
import sys
import time
import traceback
import urllib.request
import urllib.error
from pathlib import Path


def _crash_handler(signum, frame):
    """Log the signal that killed us."""
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    msg = f"\n!!! KILLED by signal {sig_name} ({signum}) at {datetime.datetime.now()}\n"
    sys.stderr.write(msg)
    sys.stderr.flush()
    print(msg, flush=True)
    sys.exit(128 + signum)

signal.signal(signal.SIGTERM, _crash_handler)
signal.signal(signal.SIGHUP, _crash_handler)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state
import llm


TRANSCRIPTS_DIRS = [
    Path.home() / ".claude/projects/-Users-dana--openclaw-apex",
    Path.home() / ".claude/projects/-Users-dana--openclaw",
    Path.home() / ".claude/projects/-Users-dana--openclaw-apex-server",
    Path.home() / ".claude/projects/-Users-dana--openclaw-workspace",
]

# Chunking params (aligned with chatmine.py)
CHUNK_MAX_MESSAGES = 30
CHUNK_MAX_CHARS = 12_000
# Single-shot threshold: transcripts under this use the old single-call path
SINGLE_SHOT_CHARS = 15_000
# Max chunks to process per transcript (sample beginning + end for huge sessions)
MAX_CHUNKS_PER_TRANSCRIPT = 20
# LLM call timeout per chunk (generous but not infinite)
CHUNK_TIMEOUT = 120
LLM_RETRIES = 2
LLM_RETRY_DELAY = 5
# Tool output noise patterns
_TOOL_NOISE = re.compile(
    r"^\s*\{['\"](?:role|tool_use_id|type|tool_result)['\"]"
)


def _repair_json_strings(raw: str) -> str:
    """Fix literal control chars inside JSON string values.

    Qwen sometimes outputs actual newlines/tabs inside JSON strings when the
    chunk contains code snippets. This escapes them so json.loads() succeeds.
    Works character-by-character inside quoted regions only.
    """
    out = []
    in_string = False
    i = 0
    while i < len(raw):
        c = raw[i]
        # Count preceding backslashes to handle \\\" correctly
        if c == '"':
            n_bs = 0
            j = i - 1
            while j >= 0 and raw[j] == '\\':
                n_bs += 1
                j -= 1
            if n_bs % 2 == 0:  # even backslashes = quote is real
                in_string = not in_string
            out.append(c)
        elif in_string:
            if c == '\n':
                out.append('\\n')
            elif c == '\r':
                out.append('\\r')
            elif c == '\t':
                out.append('\\t')
            else:
                out.append(c)
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def _log_repair(chunk_idx: int, raw: str, repaired: str):
    """Log when JSON repair was needed so we can track LLM output quality."""
    n_fixes = sum(1 for a, b in zip(raw, repaired) if a != b)
    print(f"[chunk {chunk_idx}: repaired {n_fixes} control chars in JSON]", end=" ", flush=True)


def find_transcripts(days: int, extra_dirs: list[str] | None = None) -> list[tuple[str, Path]]:
    """Find .jsonl transcripts modified in the last N days, return (session_id, path).

    Scans all TRANSCRIPTS_DIRS plus any --dir overrides. Skips subagent dirs.
    """
    cutoff = datetime.datetime.now().timestamp() - (days * 86400)
    seen: dict[str, Path] = {}  # dedupe by session_id (keep largest)
    dirs = list(TRANSCRIPTS_DIRS)
    if extra_dirs:
        dirs.extend(Path(d) for d in extra_dirs)
    for d in dirs:
        if not d.exists():
            continue
        for p in d.glob("*.jsonl"):  # non-recursive: skip subagents/
            if p.stat().st_mtime >= cutoff:
                session_id = p.stem
                if session_id not in seen or p.stat().st_size > seen[session_id].stat().st_size:
                    seen[session_id] = p
    results = [(sid, path) for sid, path in seen.items()]
    results.sort(key=lambda x: x[1].stat().st_mtime)
    return results


def has_digest(session_id: str) -> bool:
    """Check if a digest already exists for this session."""
    return Path(config.DIGESTS_DIR, f"{session_id}.json").exists()


def _session_date_from_transcript(path: Path) -> datetime.date | None:
    """Read the first JSONL line and return its timestamp's date.

    Used to anchor relative-date phrases ('yesterday', 'last week') to
    the session's actual date rather than today, so historical re-digests
    don't drift as the calendar advances.
    """
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp")
                if not ts:
                    continue
                try:
                    # Handle 'Z' suffix and offsets
                    iso = ts.replace("Z", "+00:00")
                    return datetime.datetime.fromisoformat(iso).date()
                except (ValueError, TypeError):
                    continue
    except (FileNotFoundError, OSError):
        pass
    # Fall back to file mtime
    try:
        return datetime.date.fromtimestamp(path.stat().st_mtime)
    except (OSError, ValueError):
        return None


def parse_transcript(path: Path) -> list[dict]:
    """Parse JSONL transcript into a list of {role, content} dicts.

    Filters out tool_result noise and messages with no meaningful content,
    keeping only human/assistant turns that might contain corrections or decisions.
    """
    messages = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = entry.get("type", "unknown")
            # Skip non-conversation entries entirely
            if role in ("tool_result", "tool_use", "progress",
                        "file-history-snapshot", "queue-operation",
                        "custom-title", "agent-name", "last-prompt"):
                continue
            content = entry.get("message") or entry.get("content") or ""
            # Unwrap message dict (Claude Code format: {role, content})
            if isinstance(content, dict):
                content = content.get("content", content.get("text", str(content)))
            # Filter content blocks: skip tool_result blocks wrapped in user entries
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        # Skip tool_result and tool_use blocks inside user messages
                        if block.get("type") in ("tool_result", "tool_use"):
                            continue
                        t = block.get("text", block.get("content", ""))
                        if t:
                            parts.append(str(t))
                    elif isinstance(block, str):
                        parts.append(block)
                content = " ".join(parts)
            content = str(content).strip()
            # Skip empty or tool-noise content
            if not content or len(content) < 5:
                continue
            if _TOOL_NOISE.match(content):
                continue
            messages.append({"role": role, "content": content})
    return messages


def chunk_messages(messages: list[dict]) -> list[list[dict]]:
    """Split messages into chunks of ~CHUNK_MAX_CHARS / CHUNK_MAX_MESSAGES."""
    chunks, current, current_chars = [], [], 0
    for msg in messages:
        clen = len(msg.get("content", ""))
        if current and (len(current) >= CHUNK_MAX_MESSAGES or current_chars + clen > CHUNK_MAX_CHARS):
            chunks.append(current)
            current, current_chars = [], 0
        current.append(msg)
        current_chars += clen
    if current:
        chunks.append(current)
    return chunks


def format_chunk(chunk: list[dict]) -> str:
    """Format a chunk of messages into a readable transcript string."""
    lines = []
    for msg in chunk:
        role = msg["role"]
        content = msg.get("content", "").strip()
        # Truncate individual huge messages (tool output, etc.)
        if len(content) > 2000:
            content = content[:1800] + f"\n... [{len(content)} chars truncated]"
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def format_all(messages: list[dict]) -> str:
    """Format all messages as a single transcript string."""
    lines = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "").strip()
        if len(content) > 2000:
            content = content[:1800] + f"\n... [{len(content)} chars truncated]"
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _llm_extract_chunk(transcript: str, chunk_idx: int, total_chunks: int) -> dict | None:
    """Call Ollama to extract corrections/decisions/pending from one chunk."""
    clean = config.redact_secrets(transcript)
    prompt = (
        f"Analyze this conversation segment (chunk {chunk_idx}/{total_chunks}) and extract:\n"
        "- corrections: things the user corrected or said no/wrong/stop about\n"
        "- decisions: architectural or technical decisions made\n"
        "- pending: unresolved items, things left incomplete\n"
        "- summary: 1-2 sentence summary of this segment\n\n"
        "Rules:\n"
        "- Be SPECIFIC: include file names, function names, config keys\n"
        "- If the segment is mostly tool output or trivial chat, return empty lists\n"
        "- Capture corrections and decisions, not just activity descriptions\n\n"
        "Return valid JSON with keys: corrections (list), decisions (list), "
        "pending (list), summary (string).\n\n"
        f"Transcript:\n{clean}"
    )
    payload = json.dumps({
        "model": config.OLLAMA_MODEL, "stream": False, "think": False,
        "messages": [
            {"role": "system", "content": "You are a JSON extraction engine. Return ONLY valid JSON, no prose, no markdown fencing, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "options": config.OLLAMA_OPTIONS,
    }).encode()

    # First chunk gets extra time (model may be cold-loading into GPU)
    effective_timeout = CHUNK_TIMEOUT * 2 if chunk_idx == 1 else CHUNK_TIMEOUT

    for attempt in range(1, LLM_RETRIES + 1):
        try:
            req = urllib.request.Request(
                config.OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=effective_timeout)
            body = json.loads(resp.read().decode())
            raw = body.get("message", {}).get("content", "").strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            # Fix unterminated strings: Qwen outputs literal newlines/tabs
            # inside JSON string values when chunks contain code snippets.
            # Escape them before parsing.
            repaired = _repair_json_strings(raw)
            if repaired != raw:
                _log_repair(chunk_idx, raw, repaired)
            return json.loads(repaired)
        except Exception as e:
            if attempt < LLM_RETRIES:
                time.sleep(LLM_RETRY_DELAY)
            else:
                print(f"[chunk {chunk_idx} failed: {e}]", end=" ", flush=True)
    return None


def _normalize(text: str, max_len: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _tag(items: list, source: str = "llm") -> list[dict]:
    return [
        {"text": _normalize(str(i)), "confidence": 0.8, "source": source}
        for i in (items if isinstance(items, list) else [])
        if str(i).strip()
    ]


def merge_chunk_results(chunk_results: list[dict]) -> dict:
    """Merge extraction results from multiple chunks into one digest."""
    all_corrections = []
    all_decisions = []
    all_pending = []
    summaries = []

    for r in chunk_results:
        if not r:
            continue
        all_corrections.extend(r.get("corrections", []))
        all_decisions.extend(r.get("decisions", []))
        # Only take pending from the LAST chunk (earlier pending may be resolved)
        all_pending = r.get("pending", []) or all_pending
        s = r.get("summary", "")
        if s:
            summaries.append(str(s))

    # Deduplicate by normalized text
    def _dedup(items):
        seen = set()
        out = []
        for item in items:
            key = _normalize(str(item)).lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    all_corrections = _dedup(all_corrections)
    all_decisions = _dedup(all_decisions)
    all_pending = _dedup(all_pending)

    # Build final summary from chunk summaries
    summary_text = "; ".join(summaries[-3:]) if summaries else ""

    return {
        "corrections": _tag(all_corrections),
        "decisions": _tag(all_decisions),
        "pending": _tag(all_pending),
        "summary": {
            "text": _normalize(summary_text, 300),
            "confidence": 0.8, "source": "llm",
        },
    }


def _sample_chunks(chunks: list[list[dict]], max_chunks: int) -> list[list[dict]]:
    """Sample chunks from a huge transcript: first 5 + last 5 + evenly spaced middle.

    The beginning has session setup context. The end has corrections/decisions.
    The middle catches things that happened along the way.
    """
    if len(chunks) <= max_chunks:
        return chunks

    head_n = min(5, max_chunks // 4)
    tail_n = min(10, max_chunks // 2)  # bias toward end (corrections live here)
    middle_budget = max_chunks - head_n - tail_n

    head = chunks[:head_n]
    tail = chunks[-tail_n:]

    middle_pool = chunks[head_n:-tail_n] if tail_n else chunks[head_n:]
    if middle_budget > 0 and middle_pool:
        step = max(1, len(middle_pool) // middle_budget)
        middle = middle_pool[::step][:middle_budget]
    else:
        middle = []

    return head + middle + tail


def run_digest(session_id: str, path: Path, max_chunks: int = 0,
               session_date: datetime.date | None = None) -> dict:
    """Run extraction on a single transcript, chunking large ones.

    `session_date` anchors relative-date phrases to the session's actual
    date. Defaults to deriving from the transcript's first timestamp so
    historical re-digests don't bind 'yesterday' to today's date.
    """
    if session_date is None:
        session_date = _session_date_from_transcript(path)
    messages = parse_transcript(path)
    if not messages:
        return {}

    total_text = format_all(messages)
    if len(total_text) < 50:
        return {}

    # Small transcripts: single-shot (old path, fast)
    if len(total_text) <= SINGLE_SHOT_CHARS:
        digest = llm.extract_session(total_text, messages, session_date=session_date)
        return digest

    # Large transcripts: chunk and extract each piece
    all_chunks = chunk_messages(messages)
    effective_max = max_chunks if max_chunks > 0 else MAX_CHUNKS_PER_TRANSCRIPT
    chunks = _sample_chunks(all_chunks, effective_max)
    sampled = len(chunks) < len(all_chunks)
    label = f"{len(chunks)}/{len(all_chunks)} chunks" if sampled else f"{len(chunks)} chunks"
    print(f"[{len(messages)} msgs, {label}]", end=" ", flush=True)

    chunk_results = []
    failed_chunks = 0
    for i, chunk in enumerate(chunks, 1):
        transcript = format_chunk(chunk)
        t0 = time.time()
        result = _llm_extract_chunk(transcript, i, len(chunks))
        elapsed = time.time() - t0
        if result:
            chunk_results.append(result)
            if elapsed > 60:
                print(f"[chunk {i} slow: {elapsed:.0f}s]", end=" ", flush=True)
        else:
            failed_chunks += 1
            print(f"[chunk {i} FAILED after {elapsed:.0f}s]", end=" ", flush=True)

    if not chunk_results:
        # All chunks failed — fall back to heuristic on full message set
        return llm.extract_session(total_text[-SINGLE_SHOT_CHARS:], messages,
                                   session_date=session_date)

    digest = merge_chunk_results(chunk_results)
    if failed_chunks:
        print(f"[{failed_chunks} chunk failures]", end=" ", flush=True)

    # Invariants still run on the tail of the transcript (they only use last 6KB anyway)
    digest["invariants"] = llm.extract_invariants(total_text[-6000:],
                                                  session_date=session_date)

    # Anchor relative dates (chunked path bypasses extract_session, so apply here)
    digest = llm._anchor_extraction(digest, anchor=session_date)

    return digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2, help="Look back N days (default: 2)")
    parser.add_argument("--force", action="store_true", help="Re-digest even if digest exists")
    parser.add_argument("--session", type=str, default=None,
                        help="Process a specific session ID (prefix match)")
    parser.add_argument("--min-size", type=int, default=0,
                        help="Only process transcripts >= this many KB")
    parser.add_argument("--max-count", type=int, default=0,
                        help="Stop after processing this many transcripts (0=unlimited)")
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="Max chunks per transcript (0=use default, 99999=all)")
    parser.add_argument("--dir", type=str, action="append", default=None,
                        help="Additional transcript directory to scan (repeatable)")
    parser.add_argument("--min-msgs", type=int, default=0,
                        help="Skip transcripts with fewer conversation messages after filtering")
    args = parser.parse_args()

    config.ensure_dirs()

    transcripts = find_transcripts(args.days, extra_dirs=args.dir)
    print(f"Found {len(transcripts)} transcripts from last {args.days} day(s)")

    skipped = 0
    processed = 0
    failed = 0

    for session_id, path in transcripts:
        size_kb = path.stat().st_size / 1024
        if args.session and not session_id.startswith(args.session):
            continue
        if args.min_size and size_kb < args.min_size:
            continue
        if not args.force and has_digest(session_id):
            skipped += 1
            continue

        # Quick pre-check: count conversation messages to skip tiny sessions
        if args.min_msgs:
            conv_msgs = parse_transcript(path)
            if len(conv_msgs) < args.min_msgs:
                skipped += 1
                continue

        print(f"  DIGEST {session_id[:8]} ({size_kb:.0f}KB)...", end=" ", flush=True)
        try:
            digest = run_digest(session_id, path, max_chunks=args.max_chunks)
            if not digest:
                print("empty transcript")
                skipped += 1
                continue

            state.save_digest(session_id, digest)

            # Merge into guidance
            current_guidance = state.read_guidance()
            from digest import _merge_guidance
            merged = _merge_guidance(current_guidance, digest)
            state.write_guidance(merged)

            # Register session if not already registered
            if not state.get_session(session_id):
                state.register_session(session_id, str(config.WORKSPACE))

            source = digest.get("summary", {}).get("source", "?")
            summary = digest.get("summary", {}).get("text", "")[:80]
            n_corrections = len(digest.get("corrections", []))
            n_decisions = len(digest.get("decisions", []))
            n_pending = len(digest.get("pending", []))
            print(f"OK ({source}) c={n_corrections} d={n_decisions} p={n_pending} | {summary}")
            processed += 1

            if args.max_count and processed >= args.max_count:
                print(f"\n  Stopping after {args.max_count} transcripts (--max-count)")
                break

        except Exception as e:
            import traceback
            print(f"FAIL: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nDone: {processed} processed, {skipped} skipped, {failed} failed")
    print(f"Guidance items: {len(state.read_guidance().get('items', []))}")


if __name__ == "__main__":
    main()
