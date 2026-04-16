#!/opt/homebrew/bin/python3
"""chatMine — extract structured knowledge from Apex chat history.

Reads messages from the Apex SQLite DB, chunks them into digestible
windows, runs LLM extraction on each chunk, then consolidates into
per-chat knowledge digests and optionally memory files.

Safety:
- Read-only on the chat DB (never modifies messages)
- All output goes to .subconscious/chatmine/
- Idempotent: re-running overwrites previous extractions

Usage:
    python3 scripts/subconscious/chatmine.py [--chat CHAT_ID] [--dry-run] [--verbose]
    python3 scripts/subconscious/chatmine.py --list          # show available chats
    python3 scripts/subconscious/chatmine.py --chat 933c8242  # mine War Room
    python3 scripts/subconscious/chatmine.py --all            # mine all chats with >20 messages
"""

import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# ── Config ────────────────────────────────────────────────────────────

APEX_DB = Path(os.environ.get(
    "APEX_DB", "/Users/dana/.openclaw/apex/state/apex.db"
))
OUTPUT_DIR = Path(config.STATE_DIR) / "chatmine"
LOG_FILE = Path(config.STATE_DIR) / "chatmine.log"

OLLAMA_MODEL = config.OLLAMA_MODEL
OLLAMA_URL = config.OLLAMA_URL
OLLAMA_TIMEOUT = 300  # overridden to 90 for fast models in set_model()

CHUNK_MAX_MESSAGES = 30
CHUNK_MAX_CHARS = 12000
MIN_CHAT_MESSAGES = 20


def _log(msg: str, verbose: bool = False):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if verbose:
        print(line)


def _get_db() -> sqlite3.Connection:
    if not APEX_DB.exists():
        raise FileNotFoundError(f"Apex DB not found: {APEX_DB}")
    conn = sqlite3.connect(f"file:{APEX_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_chats(min_messages: int = MIN_CHAT_MESSAGES) -> list[dict]:
    conn = _get_db()
    rows = conn.execute("""
        SELECT c.id, c.title, c.type, COUNT(m.id) as msg_count,
            SUM(LENGTH(m.content)) as content_bytes,
            MIN(m.created_at) as oldest, MAX(m.created_at) as newest
        FROM chats c JOIN messages m ON c.id = m.chat_id
        GROUP BY c.id
        HAVING msg_count >= ?
        ORDER BY msg_count DESC
    """, (min_messages,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_messages(chat_id: str) -> list[dict]:
    conn = _get_db()
    rows = conn.execute("""
        SELECT role, speaker_name, content, created_at
        FROM messages WHERE chat_id = ? ORDER BY created_at
    """, (chat_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def chunk_messages(messages: list[dict]) -> list[list[dict]]:
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
    lines = []
    for msg in chunk:
        role = msg["role"]
        speaker = msg.get("speaker_name", "")
        content = msg.get("content", "").strip()
        if len(content) > 2000:
            content = content[:1800] + f"\n... [{len(content)} chars truncated]"
        tag = f"{role}/{speaker}" if speaker else role
        lines.append(f"[{tag}]: {content}")
    return "\n\n".join(lines)


LLM_RETRIES = 3
LLM_RETRY_DELAY = 10  # seconds

def set_model(model: str):
    """Override the Ollama model used for extraction."""
    global OLLAMA_MODEL, OLLAMA_TIMEOUT
    OLLAMA_MODEL = model
    # Fast/small models should fail fast, not wait 5 min per attempt
    if "9b" in model or "8b" in model or "fast" in model:
        OLLAMA_TIMEOUT = 90


def _llm_call(prompt: str, use_json: bool = True, timeout: int | None = None) -> dict | None:
    import time
    payload = {
        "model": OLLAMA_MODEL, "stream": False, "think": False,
        "messages": [
            {"role": "system", "content": "You are a JSON extraction engine. Return ONLY valid JSON, no prose, no markdown fencing, no explanation."},
            {"role": "user", "content": prompt},
        ],
    }
    if use_json:
        payload["format"] = "json"
    payload["options"] = {"num_predict": 1024, "temperature": 0.1, "repeat_penalty": 1.3}
    data = json.dumps(payload).encode()
    effective_timeout = timeout if timeout is not None else OLLAMA_TIMEOUT

    for attempt in range(1, LLM_RETRIES + 1):
        raw = ""
        try:
            req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=effective_timeout)
            body = json.loads(resp.read().decode())
            raw = body.get("message", {}).get("content", "").strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except urllib.error.URLError as e:
            _log(f"    LLM attempt {attempt}/{LLM_RETRIES}: URLError — {e.reason}")
            if attempt < LLM_RETRIES:
                time.sleep(LLM_RETRY_DELAY)
        except json.JSONDecodeError as e:
            _log(f"    LLM attempt {attempt}/{LLM_RETRIES}: bad JSON — {e.msg} (pos {e.pos}), raw[:200]={raw[:200]}")
            if attempt < LLM_RETRIES:
                time.sleep(LLM_RETRY_DELAY)
        except Exception as e:
            _log(f"    LLM attempt {attempt}/{LLM_RETRIES}: {type(e).__name__} — {e}")
            if attempt < LLM_RETRIES:
                time.sleep(LLM_RETRY_DELAY)
    return None


def extract_chunk(transcript: str, chat_title: str, chunk_idx: int) -> dict | None:
    prompt = (
        f"Analyze this conversation segment from '{chat_title}' (chunk {chunk_idx}).\n\n"
        f"Extract the following as JSON:\n"
        f"- \"decisions\": list of architectural/technical decisions made (be specific)\n"
        f"- \"bugs_fixed\": list of bugs found and their fixes (include file names, root causes)\n"
        f"- \"features_built\": list of features implemented (include specifics)\n"
        f"- \"lessons\": list of lessons learned, gotchas, or patterns discovered\n"
        f"- \"topic\": 1-line summary of what this segment covers\n\n"
        f"Rules:\n"
        f"- Be SPECIFIC: include file names, function names, error messages, config keys\n"
        f"- If the segment is mostly tool output or trivial chat, return empty lists\n"
        f"- Capture the FIX, not just the symptom\n"
        f"- Each item should be a concise but complete sentence\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Return valid JSON only."
    )
    result = _llm_call(prompt)
    if not result:
        _log(f"  LLM error on chunk {chunk_idx}")
    return result


def consolidate_day(day_extractions: list[dict], chat_title: str, day: str) -> dict | None:
    merged = {"decisions": [], "bugs_fixed": [], "features_built": [], "lessons": [], "topics": []}
    for ext in day_extractions:
        if not ext:
            continue
        for key in ("decisions", "bugs_fixed", "features_built", "lessons"):
            items = ext.get(key, [])
            if isinstance(items, list):
                merged[key].extend([str(i) for i in items if i])
        topic = ext.get("topic", "")
        if topic:
            merged["topics"].append(str(topic))

    total_items = sum(len(v) for v in merged.values())
    if total_items < 3:
        return merged if total_items > 0 else None
    if total_items <= 15:
        return merged

    prompt = (
        f"Consolidate these extracted items from '{chat_title}' on {day}.\n\n"
        f"Remove exact duplicates and merge similar items. Keep all unique information.\n\n"
        f"Input:\n{json.dumps(merged, indent=2)}\n\n"
        f"Return the same JSON structure with deduplicated lists. Be concise but preserve specifics."
    )
    # Consolidation prompts are large — always allow up to 5 min regardless of model size
    result = _llm_call(prompt, timeout=300)
    return result if result else merged


def write_digest(chat_id, chat_title, daily_digests, dry_run=False, verbose=False):
    chat_dir = OUTPUT_DIR / chat_id
    os.makedirs(chat_dir, exist_ok=True)

    for day, digest in sorted(daily_digests.items()):
        if not digest:
            continue
        day_file = chat_dir / f"{day}.json"
        if not dry_run:
            day_file.write_text(json.dumps(digest, indent=2))
        _log(f"  Wrote {day_file.name}", verbose)

    md_lines = [
        "---",
        f"name: chatmine_{chat_id}",
        f"description: Knowledge extracted from '{chat_title}'",
        "type: reference",
        "source: chatmine",
        f"mined_at: {datetime.datetime.now().isoformat()}",
        "---", "",
        f"# {chat_title} — Extracted Knowledge", "",
    ]

    for day in sorted(daily_digests.keys()):
        digest = daily_digests[day]
        if not digest:
            continue
        md_lines.append(f"## {day}")
        md_lines.append("")
        topics = digest.get("topics", [])
        if topics:
            md_lines.append(f"**Topics:** {'; '.join(topics[:5])}")
            md_lines.append("")
        for section, label in [("decisions", "Decisions"), ("features_built", "Features Built"),
                                ("bugs_fixed", "Bugs Fixed"), ("lessons", "Lessons Learned")]:
            items = digest.get(section, [])
            if items:
                md_lines.append(f"### {label}")
                for item in items:
                    md_lines.append(f"- {item}")
                md_lines.append("")

    summary_path = chat_dir / "summary.md"
    content = "\n".join(md_lines)
    if not dry_run:
        summary_path.write_text(content)
    _log(f"  Summary: {summary_path} ({len(content)} chars)", verbose)

    if verbose:
        preview = content[:3000]
        print(f"\n{'='*60}")
        print(preview)
        if len(content) > 3000:
            print(f"... [{len(content)} chars total]")
        print(f"{'='*60}")

    return summary_path


def mine_chat(chat_id, chat_title, dry_run=False, verbose=False, force=False):
    _log(f"Mining '{chat_title}' ({chat_id})", verbose)
    messages = get_messages(chat_id)
    _log(f"  {len(messages)} messages loaded", verbose)
    chunks = chunk_messages(messages)
    _log(f"  Split into {len(chunks)} chunks", verbose)

    today = datetime.date.today().isoformat()
    chat_dir = OUTPUT_DIR / chat_id

    # Incremental: load cached day files (skip completed days, always re-mine today)
    cached_days = {}
    if not force and not dry_run and chat_dir.exists():
        for day_file in chat_dir.glob("????-??-??.json"):
            day = day_file.stem
            if day != today:
                try:
                    cached_days[day] = json.loads(day_file.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
    if cached_days:
        _log(f"  Incremental: {len(cached_days)} days cached, skipping", verbose)

    day_chunks: dict[str, list] = {}
    chunk_idx = 0
    skipped = 0

    for chunk in chunks:
        first_ts = chunk[0].get("created_at", "")
        day = first_ts[:10] if first_ts else "unknown"
        chunk_idx += 1

        if day in cached_days:
            skipped += 1
            continue

        if day not in day_chunks:
            day_chunks[day] = []
        transcript = format_chunk(chunk)

        if dry_run:
            _log(f"  Chunk {chunk_idx}/{len(chunks)} ({day}): {len(chunk)} msgs, {len(transcript)} chars [dry-run]", verbose)
            day_chunks[day].append({"topic": f"chunk {chunk_idx} ({len(chunk)} msgs)"})
            continue

        _log(f"  Chunk {chunk_idx}/{len(chunks)} ({day}): {len(chunk)} msgs, {len(transcript)} chars", verbose)
        extraction = extract_chunk(transcript, chat_title, chunk_idx)
        if extraction:
            day_chunks[day].append(extraction)
            items = sum(len(extraction.get(k, [])) for k in ("decisions", "bugs_fixed", "features_built", "lessons"))
            topic = extraction.get("topic", "?")
            _log(f"    → {items} items, topic: {topic[:80]}", verbose)
        else:
            _log(f"    → extraction failed", verbose)

    if skipped:
        _log(f"  Skipped {skipped} chunks from {len(cached_days)} cached days", verbose)

    # Merge cached days with newly mined days
    daily_digests = dict(cached_days)
    for day, extractions in sorted(day_chunks.items()):
        if dry_run:
            daily_digests[day] = {"topics": [e.get("topic", "") for e in extractions],
                                   "decisions": [], "bugs_fixed": [], "features_built": [], "lessons": []}
            continue
        _log(f"  Consolidating {day} ({len(extractions)} chunks)...", verbose)
        daily_digests[day] = consolidate_day(extractions, chat_title, day)

    summary_path = write_digest(chat_id, chat_title, daily_digests, dry_run=dry_run, verbose=verbose)
    new_chunks = len(chunks) - skipped
    stats = {"chat_id": chat_id, "title": chat_title, "messages": len(messages),
             "chunks": len(chunks), "new_chunks": new_chunks, "cached_days": len(cached_days),
             "days": len(daily_digests), "summary": str(summary_path)}
    _log(f"  Done: {stats}", verbose)
    return stats


def run(chat_id=None, all_chats=False, dry_run=False, verbose=False, force=False):
    _log(f"chatMine started (dry_run={dry_run}, force={force})", verbose)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if chat_id:
        chats = list_chats(min_messages=1)
        target = next((c for c in chats if c["id"].startswith(chat_id)), None)
        if not target:
            print(f"Chat not found: {chat_id}")
            return
        return mine_chat(target["id"], target["title"], dry_run=dry_run, verbose=verbose, force=force)

    if all_chats:
        chats = list_chats(min_messages=MIN_CHAT_MESSAGES)
        results = []
        for chat in chats:
            results.append(mine_chat(chat["id"], chat["title"], dry_run=dry_run, verbose=verbose, force=force))
        return results

    print("Specify --chat CHAT_ID, --all, or --list")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="chatMine — knowledge extraction from chat history")
    parser.add_argument("--chat", type=str, help="Mine a specific chat (prefix match on ID)")
    parser.add_argument("--all", action="store_true", help=f"Mine all chats with >{MIN_CHAT_MESSAGES} messages")
    parser.add_argument("--list", action="store_true", help="List available chats")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without calling LLM")
    parser.add_argument("--force", action="store_true", help="Re-mine all days (ignore cache)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed output")
    parser.add_argument("--model", type=str, help="Override Ollama model (e.g. qwen3.5:9b-fast)")
    args = parser.parse_args()

    if args.model:
        set_model(args.model)

    if args.list:
        chats = list_chats()
        print(f"\n{'ID':<12} {'Title':<25} {'Type':<8} {'Msgs':>6} {'Content':>10} {'Date Range'}")
        print("-" * 90)
        for c in chats:
            oldest = c["oldest"][:10] if c["oldest"] else "?"
            newest = c["newest"][:10] if c["newest"] else "?"
            kb = f"{c['content_bytes']/1024:.0f}KB"
            print(f"{c['id']:<12} {c['title'][:24]:<25} {c['type']:<8} {c['msg_count']:>6} {kb:>10} {oldest} → {newest}")
        sys.exit(0)

    results = run(chat_id=args.chat, all_chats=args.all, dry_run=args.dry_run, verbose=args.verbose, force=args.force)
    if results:
        print(f"\nResults: {json.dumps(results, indent=2, default=str)}")
