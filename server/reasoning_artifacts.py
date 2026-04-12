"""
Reasoning Artifact Capture & Recovery

Detects long analytical responses before compaction and saves them to disk.
On recovery, injects them back into the session so reasoning chains survive
compaction boundaries.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Storage directory
ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "reasoning_artifacts")


def detect_reasoning_artifacts(messages: list[dict]) -> list[dict]:
    """
    Scan assistant messages. An artifact is any response where:
    - len(content) > 2000
    - code_ratio (fraction of lines in code blocks) < 0.3
    - Not a tool result dump (tool_events is empty or '[]')

    Parameters:
        messages: list of dicts with 'content', 'tool_events', 'created_at', 'message_id' keys
                  (from db._get_session_analysis_data)

    Returns: list of artifact dicts
    """
    artifacts = []
    for msg in messages:
        content = msg.get("content") or ""
        if len(content) < 2000:
            continue

        # Check code ratio
        lines = content.split("\n")
        in_code_block = False
        code_lines = 0
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or line.startswith("    ") or line.startswith("\t"):
                code_lines += 1
        code_ratio = code_lines / max(len(lines), 1)
        if code_ratio >= 0.3:
            continue

        # Skip tool-heavy messages
        tool_events = msg.get("tool_events") or "[]"
        if isinstance(tool_events, str):
            try:
                te = json.loads(tool_events)
                if isinstance(te, list) and len(te) > 3:
                    continue
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract topics from section headers
        topics = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                topic = stripped.lstrip("#").strip().rstrip(":")
                if topic and len(topic) < 80:
                    topics.append(topic)

        artifacts.append({
            "message_id": msg.get("message_id", ""),
            "created_at": msg.get("created_at", datetime.now().isoformat()),
            "content_length": len(content),
            "content_preview": content[:200],
            "content_full": content,
            "topics": topics[:10],
            "code_ratio": round(code_ratio, 3),
        })

    return artifacts


def save_reasoning_artifacts(chat_id: str, artifacts: list[dict]) -> int:
    """
    Write each artifact to state/reasoning_artifacts/{chat_id}_{timestamp}.json.
    Uses atomic write (write to temp, rename).
    Returns count saved.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    saved = 0
    for art in artifacts:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{chat_id}_{ts}_{saved}.json"
        filepath = os.path.join(ARTIFACTS_DIR, filename)
        tmp_path = filepath + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump({"chat_id": chat_id, **art}, f, indent=2, default=str)
            os.rename(tmp_path, filepath)
            saved += 1
        except Exception as e:
            # Clean up temp file on failure
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            print(f"[reasoning_artifacts] Failed to save artifact: {e}")
    return saved


def load_reasoning_artifacts(chat_id: str, limit: int = 3) -> list[dict]:
    """
    Load most recent artifacts for a chat_id from disk.
    Returns sorted by created_at descending, limited to `limit`.
    """
    if not os.path.isdir(ARTIFACTS_DIR):
        return []

    artifacts = []
    prefix = f"{chat_id}_"
    for filename in os.listdir(ARTIFACTS_DIR):
        if not filename.startswith(prefix) or not filename.endswith(".json"):
            continue
        filepath = os.path.join(ARTIFACTS_DIR, filename)
        try:
            with open(filepath) as f:
                art = json.load(f)
            artifacts.append(art)
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by created_at descending
    artifacts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return artifacts[:limit]


def cleanup_old_artifacts(max_age_days: int = 7, max_per_chat: int = 10) -> int:
    """
    Remove artifact files older than max_age_days.
    Also enforce max_per_chat limit (FIFO eviction).
    Returns count of files removed.
    """
    if not os.path.isdir(ARTIFACTS_DIR):
        return 0

    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed = 0

    # Group by chat_id
    by_chat: dict[str, list[tuple[str, float]]] = {}
    for filename in os.listdir(ARTIFACTS_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(ARTIFACTS_DIR, filename)
        mtime = os.path.getmtime(filepath)

        # Remove old files
        if datetime.fromtimestamp(mtime) < cutoff:
            try:
                os.remove(filepath)
                removed += 1
            except OSError:
                pass
            continue

        # Group remaining by chat_id (first part before second underscore)
        parts = filename.split("_", 1)
        chat_id = parts[0] if parts else "unknown"
        if chat_id not in by_chat:
            by_chat[chat_id] = []
        by_chat[chat_id].append((filepath, mtime))

    # Enforce per-chat limit
    for chat_id, files in by_chat.items():
        if len(files) <= max_per_chat:
            continue
        files.sort(key=lambda x: x[1])  # oldest first
        for filepath, _ in files[:-max_per_chat]:
            try:
                os.remove(filepath)
                removed += 1
            except OSError:
                pass

    return removed
