#!/opt/homebrew/bin/python3
"""chatMine (Claude Code) — extract knowledge from ~/.claude conversation transcripts.

Adapts chatmine's extraction pipeline for Claude Code's JSONL format.
Reads user/assistant messages, chunks them, runs LLM extraction.

Safety:
- Read-only on JSONL files
- Output goes to .subconscious/chatmine/claude/
- Skips subagent conversations (focus on main sessions)

Usage:
    python3 scripts/subconscious/chatmine_claude.py --list
    python3 scripts/subconscious/chatmine_claude.py --session SESSION_ID [-v]
    python3 scripts/subconscious/chatmine_claude.py --all [-v] [--min-size 50000]
    python3 scripts/subconscious/chatmine_claude.py --top N [-v]  # mine N largest sessions
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

CLAUDE_DIR = Path.home() / ".claude" / "projects"
OUTPUT_DIR = Path(config.STATE_DIR) / "chatmine" / "claude"
LOG_FILE = Path(config.STATE_DIR) / "chatmine_claude.log"


def _log(msg: str, verbose: bool = False):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if verbose:
        print(line)


def _extract_text_content(content) -> str:
    """Extract readable text from Claude Code message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    # Summarize tool calls concisely
                    if name in ("Read", "Glob", "Grep"):
                        parts.append(f"[tool:{name} {inp.get('file_path', inp.get('pattern', ''))}]")
                    elif name == "Edit":
                        parts.append(f"[tool:Edit {inp.get('file_path', '')}]")
                    elif name == "Write":
                        parts.append(f"[tool:Write {inp.get('file_path', '')}]")
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        if len(cmd) > 150:
                            cmd = cmd[:147] + "..."
                        parts.append(f"[tool:Bash {cmd}]")
                    else:
                        parts.append(f"[tool:{name}]")
                elif btype == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str) and len(result_content) > 500:
                        result_content = result_content[:400] + "..."
                    elif isinstance(result_content, list):
                        result_content = "[complex result]"
                    parts.append(f"[result: {result_content}]")
                elif btype == "thinking":
                    # Skip thinking blocks — too noisy
                    pass
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content)[:500]


def list_sessions(min_size: int = 10000) -> list[dict]:
    """List Claude Code sessions by size."""
    sessions = []
    for jsonl in CLAUDE_DIR.rglob("*.jsonl"):
        # Skip subagent files
        if "/subagents/" in str(jsonl):
            continue
        size = jsonl.stat().st_size
        if size < min_size:
            continue
        # Get project from parent dir name
        project = jsonl.parent.name
        session_id = jsonl.stem
        # Quick message count (just count lines with type = user/assistant)
        sessions.append({
            "path": str(jsonl),
            "session_id": session_id,
            "project": project,
            "size": size,
            "modified": datetime.datetime.fromtimestamp(jsonl.stat().st_mtime),
        })
    sessions.sort(key=lambda x: x["size"], reverse=True)
    return sessions


def load_messages(jsonl_path: str) -> list[dict]:
    """Load messages from a Claude Code JSONL transcript."""
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

            msg_type = obj.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            # Extract content
            msg_data = obj.get("message", obj)
            content = msg_data.get("content", "")
            text = _extract_text_content(content)

            if not text or len(text) < 5:
                continue

            ts = obj.get("timestamp", "")
            messages.append({
                "role": msg_type,
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
    """Mine a single Claude Code session."""
    sid = session["session_id"][:12]
    project = session["project"]
    _log(f"Mining {sid} ({project}, {session['size']//1024}KB)", verbose)

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
        extraction = extract_chunk(transcript, f"Claude Code ({project})", chunk_idx)
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
        daily_digests[day] = consolidate_day(extractions, f"Claude Code ({project})", day)

    # Write output — use claude/ subdir
    os.makedirs(out_dir, exist_ok=True)

    for day, digest in sorted(daily_digests.items()):
        if digest and not dry_run:
            (out_dir / f"{day}.json").write_text(json.dumps(digest, indent=2))

    # Write markdown summary
    md_lines = [
        "---",
        f"name: claude_{session['session_id'][:12]}",
        f"description: Knowledge from Claude Code session ({project})",
        "type: reference",
        "source: chatmine_claude",
        f"mined_at: {datetime.datetime.now().isoformat()}",
        "---", "",
        f"# Claude Code Session — {project}", "",
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
    parser = argparse.ArgumentParser(description="chatMine (Claude Code)")
    parser.add_argument("--list", action="store_true", help="List sessions")
    parser.add_argument("--session", type=str, help="Mine specific session ID")
    parser.add_argument("--all", action="store_true", help="Mine all sessions")
    parser.add_argument("--top", type=int, help="Mine top N largest sessions")
    parser.add_argument("--min-size", type=int, default=50000, help="Min file size in bytes (default 50KB)")
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
        print(f"\n{'Session ID':<14} {'Size':>8} {'Project':<50} {'Modified'}")
        print("-" * 100)
        for s in sessions[:50]:
            kb = f"{s['size']//1024}KB"
            proj = s['project'][:49]
            mod = s['modified'].strftime("%Y-%m-%d")
            print(f"{s['session_id'][:12]:<14} {kb:>8} {proj:<50} {mod}")
        print(f"\nTotal: {len(sessions)} sessions >= {args.min_size//1024}KB")
        sys.exit(0)

    sessions = list_sessions(min_size=args.min_size)

    if args.session:
        target = next((s for s in sessions if s["session_id"].startswith(args.session)), None)
        if not target:
            print(f"Session not found: {args.session}")
            sys.exit(1)
        result = mine_session(target, dry_run=args.dry_run, verbose=args.verbose, force=args.force)
        print(json.dumps(result, indent=2, default=str))

    elif args.top:
        results = []
        for s in sessions[:args.top]:
            results.append(mine_session(s, dry_run=args.dry_run, verbose=args.verbose, force=args.force))
        print(f"\nMined {len(results)} sessions")

    elif args.all:
        results = []
        for i, s in enumerate(sessions):
            _log(f"[{i+1}/{len(sessions)}] {s['session_id'][:12]}", args.verbose)
            results.append(mine_session(s, dry_run=args.dry_run, verbose=args.verbose, force=args.force))
        print(f"\nMined {len(results)} sessions")

    else:
        print("Specify --list, --session ID, --top N, or --all")
        sys.exit(0)

    # Bridge chatmine output into guidance.json
    if not args.dry_run:
        try:
            from chatmine_bridge import run_bridge
            bridge_stats = run_bridge(
                session_filter=args.session,
                dry_run=False,
                verbose=args.verbose,
            )
            bridged = bridge_stats.get("bridged", 0)
            if bridged > 0:
                _log(f"Bridge: {bridged} day files → guidance.json "
                     f"({bridge_stats.get('decisions', 0)}d, "
                     f"{bridge_stats.get('corrections', 0)}c)", args.verbose)
        except Exception as e:
            _log(f"Bridge error: {e}", verbose=True)
