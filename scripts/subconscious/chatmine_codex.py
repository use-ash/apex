#!/opt/homebrew/bin/python3
"""chatMine (Codex) — extract knowledge from ~/.codex session transcripts.

Adapts chatmine's extraction pipeline for Codex CLI's JSONL format.
Reads user/assistant messages from session rollout files, chunks them, runs LLM extraction.

Data sources:
- ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl  (session transcripts)
- ~/.codex/history.jsonl  (user prompts with timestamps)
- ~/.codex/session_index.jsonl  (thread names)

Safety:
- Read-only on JSONL files
- Output goes to .subconscious/chatmine/codex/

Usage:
    python3 scripts/subconscious/chatmine_codex.py --list
    python3 scripts/subconscious/chatmine_codex.py --session SESSION_ID [-v]
    python3 scripts/subconscious/chatmine_codex.py --all [-v] [--min-size 10000]
    python3 scripts/subconscious/chatmine_codex.py --top N [-v]
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# Reuse chatmine's core extraction functions
from chatmine import (
    _log as _chatmine_log,
    chunk_messages, extract_chunk, consolidate_day, write_digest,
    OUTPUT_DIR as CHATMINE_OUTPUT,
)

CODEX_DIR = Path.home() / ".codex"
SESSIONS_DIRS = [CODEX_DIR / "sessions", CODEX_DIR / "archived_sessions"]
HISTORY_FILE = CODEX_DIR / "history.jsonl"
INDEX_FILE = CODEX_DIR / "session_index.jsonl"
OUTPUT_DIR = Path(config.STATE_DIR) / "chatmine" / "codex"
LOG_FILE = Path(config.STATE_DIR) / "chatmine_codex.log"


def _log(msg: str, verbose: bool = False):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if verbose:
        print(line)


def _load_session_index() -> dict[str, str]:
    """Load session_id -> thread_name map (last entry wins)."""
    index: dict[str, str] = {}
    if not INDEX_FILE.exists():
        return index
    with open(INDEX_FILE) as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                sid = obj.get("id", "")
                name = obj.get("thread_name", "")
                if sid and name:
                    index[sid] = name
            except (json.JSONDecodeError, KeyError):
                continue
    return index


def _extract_text_content(content) -> str:
    """Extract readable text from Codex message content blocks."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "input_text":
                    text = block.get("text", "")
                    # Skip system/permission/skill preambles
                    if text.startswith("<permissions instructions>"):
                        continue
                    if text.startswith("<skills_instructions>"):
                        continue
                    if text.startswith("<environment_context>"):
                        continue
                    # Strip AGENTS.md wrapper but keep content
                    if "# AGENTS.md instructions" in text[:100]:
                        continue
                    # Strip conversation-history wrapper, keep the content
                    m = re.search(r"<conversation-history>(.*?)</conversation-history>", text, re.DOTALL)
                    if m:
                        text = m.group(1).strip()
                    parts.append(text)
                elif btype == "output_text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content)[:500]


def list_sessions(min_size: int = 10000) -> list[dict]:
    """List Codex sessions by size."""
    index = _load_session_index()
    sessions = []
    # Collect all JSONL files from sessions + archived_sessions
    all_jsonl = []
    for sdir in SESSIONS_DIRS:
        if sdir.exists():
            all_jsonl.extend(sdir.rglob("*.jsonl"))
    for jsonl in all_jsonl:
        size = jsonl.stat().st_size
        if size < min_size:
            continue
        # Extract session ID from filename: rollout-DATE-SESSION_ID.jsonl
        name = jsonl.stem
        # Format: rollout-2026-03-20T21-20-56-019d0e9f-f35b-7ec3-b00a-475cca89edc3
        parts = name.split("-")
        # Session ID is the UUID at the end (5 hyphen-separated groups)
        if len(parts) >= 10:
            session_id = "-".join(parts[-5:])
        else:
            session_id = name
        thread_name = index.get(session_id, "")
        # Get date from path (YYYY/MM/DD)
        try:
            date_parts = jsonl.parent.name  # DD
            month_parts = jsonl.parent.parent.name  # MM
            year_parts = jsonl.parent.parent.parent.name  # YYYY
            date_str = f"{year_parts}-{month_parts}-{date_parts}"
        except Exception:
            date_str = ""
        sessions.append({
            "path": str(jsonl),
            "session_id": session_id,
            "thread_name": thread_name,
            "date": date_str,
            "size": size,
            "modified": datetime.datetime.fromtimestamp(jsonl.stat().st_mtime),
        })
    sessions.sort(key=lambda x: x["size"], reverse=True)
    return sessions


def load_messages(jsonl_path: str) -> list[dict]:
    """Load messages from a Codex session JSONL transcript."""
    messages = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = obj.get("type", "")

            # We care about response_item events with user/assistant messages
            if event_type == "response_item":
                payload = obj.get("payload", {})
                role = payload.get("role", "")
                ptype = payload.get("type", "")

                if role not in ("user", "assistant") or ptype not in ("message",):
                    continue

                content = payload.get("content", [])
                text = _extract_text_content(content)

                if not text or len(text) < 5:
                    continue

                ts = obj.get("timestamp", "")
                messages.append({
                    "role": role,
                    "speaker_name": "",
                    "content": text,
                    "created_at": ts,
                })

    return messages


def format_chunk(chunk: list[dict]) -> str:
    """Format messages as transcript."""
    lines = []
    for msg in chunk:
        role = msg["role"]
        content = msg.get("content", "").strip()
        # Truncate very long messages
        if len(content) > 2000:
            content = content[:1800] + f"\n... [{len(content)} chars truncated]"
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


def mine_session(session: dict, dry_run: bool = False, verbose: bool = False, force: bool = False) -> dict:
    """Mine a single Codex session."""
    sid = session["session_id"][:12]
    thread = session.get("thread_name", "") or session.get("date", "")
    _log(f"Mining {sid} ({thread}, {session['size']//1024}KB)", verbose)

    messages = load_messages(session["path"])
    _log(f"  {len(messages)} messages loaded", verbose)

    if len(messages) < 4:
        _log(f"  Too few messages, skipping", verbose)
        return {"session_id": sid, "skipped": True}

    chunks = chunk_messages(messages)
    _log(f"  Split into {len(chunks)} chunks", verbose)

    today = datetime.date.today().isoformat()
    out_dir = OUTPUT_DIR / session["session_id"]

    # Incremental: load cached day files (skip completed days, always re-mine today)
    cached_days = {}
    if not force and not dry_run and out_dir.exists():
        for day_file in out_dir.glob("????-??-??.json"):
            day = day_file.stem
            if day != today:
                try:
                    cached_days[day] = json.loads(day_file.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
    if cached_days:
        _log(f"  Incremental: {len(cached_days)} days cached, skipping", verbose)

    # Group by day
    day_chunks: dict[str, list] = {}
    chunk_idx = 0
    skipped = 0

    for chunk in chunks:
        first_ts = chunk[0].get("created_at", "")
        # Codex timestamps are ISO: 2026-03-21T04:20:58.479Z
        day = first_ts[:10] if len(first_ts) >= 10 else "unknown"
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
        label = f"Codex ({thread})" if thread else "Codex"
        extraction = extract_chunk(transcript, label, chunk_idx)
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
        label = f"Codex ({thread})" if thread else "Codex"
        _log(f"  Consolidating {day} ({len(extractions)} chunks)...", verbose)
        daily_digests[day] = consolidate_day(extractions, label, day)

    # Write output
    os.makedirs(out_dir, exist_ok=True)

    for day, digest in sorted(daily_digests.items()):
        if digest and not dry_run:
            (out_dir / f"{day}.json").write_text(json.dumps(digest, indent=2))

    # Write markdown summary
    display_name = thread or session["session_id"][:12]
    md_lines = [
        "---",
        f"name: codex_{session['session_id'][:12]}",
        f"description: Knowledge from Codex session ({display_name})",
        "type: reference",
        "source: chatmine_codex",
        f"mined_at: {datetime.datetime.now().isoformat()}",
        "---", "",
        f"# Codex Session — {display_name}", "",
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

    content = "\n".join(md_lines)
    if not dry_run:
        (out_dir / "summary.md").write_text(content)

    new_chunks = len(chunks) - skipped
    _log(f"  Done: {len(messages)} msgs → {new_chunks} new chunks ({skipped} cached), {len(content)} chars summary", verbose)
    return {"session_id": session["session_id"], "messages": len(messages),
            "chunks": len(chunks), "new_chunks": new_chunks, "cached_days": len(cached_days),
            "summary_size": len(content)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="chatMine (Codex)")
    parser.add_argument("--list", action="store_true", help="List sessions")
    parser.add_argument("--session", type=str, help="Mine specific session ID")
    parser.add_argument("--all", action="store_true", help="Mine all sessions")
    parser.add_argument("--top", type=int, help="Mine top N largest sessions")
    parser.add_argument("--min-size", type=int, default=10000, help="Min file size in bytes (default 10KB)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-mine all days (ignore cache)")
    parser.add_argument("--model", type=str, help="Override Ollama model (e.g. qwen3.5:9b-fast)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.model:
        from chatmine import set_model
        set_model(args.model)
        _log(f"Model override: {args.model}", args.verbose)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.list:
        sessions = list_sessions(min_size=args.min_size)
        print(f"\n{'Session ID':<14} {'Size':>8} {'Date':<12} {'Thread Name'}")
        print("-" * 90)
        for s in sessions[:50]:
            kb = f"{s['size']//1024}KB"
            print(f"{s['session_id'][:12]:<14} {kb:>8} {s['date']:<12} {s['thread_name'][:50]}")
        print(f"\nTotal: {len(sessions)} sessions >= {args.min_size//1024}KB")

    elif args.session:
        sessions = list_sessions(min_size=0)
        match = [s for s in sessions if s["session_id"].startswith(args.session)]
        if not match:
            print(f"Session not found: {args.session}")
            sys.exit(1)
        mine_session(match[0], dry_run=args.dry_run, verbose=args.verbose, force=args.force)

    elif args.all or args.top:
        sessions = list_sessions(min_size=args.min_size)
        if args.top:
            sessions = sessions[:args.top]
        _log(f"Mining {len(sessions)} Codex sessions", args.verbose)
        total_msgs = 0
        total_chunks = 0
        errors = 0
        for i, s in enumerate(sessions, 1):
            try:
                result = mine_session(s, dry_run=args.dry_run, verbose=args.verbose, force=args.force)
                if not result.get("skipped"):
                    total_msgs += result.get("messages", 0)
                    total_chunks += result.get("new_chunks", 0)
            except Exception as e:
                _log(f"ERROR mining {s['session_id'][:12]}: {e}", args.verbose)
                errors += 1
            if i % 10 == 0:
                _log(f"Progress: {i}/{len(sessions)} sessions", args.verbose)
        _log(f"Complete: {len(sessions)} sessions, {total_msgs} messages, {total_chunks} new chunks, {errors} errors", args.verbose)

    else:
        parser.print_help()
