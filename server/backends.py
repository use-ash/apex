"""Non-Claude chat backends — Codex CLI and Ollama/xAI/MLX.

Routes chat messages through the Codex CLI (OpenAI models) or the
local model tool loop (Ollama, xAI, MLX) with streaming support.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import env
from env import (
    MODEL, DEBUG, CODEX_CLI, OPENAI_API_KEY, XAI_API_KEY,
    MAX_TOOL_ITERATIONS, ALLOW_LOCAL_TOOLS,
)

from db import (
    _get_messages,
    _estimate_tokens,
    _get_chat_settings,
    _update_chat_settings,
    _get_chat_tool_policy,
    _get_profile_tool_policy,
)
from log import log
from model_dispatch import (
    _get_model_backend, OLLAMA_BASE_URL, MLX_BASE_URL,
    MODEL_CONTEXT_WINDOWS, MODEL_CONTEXT_DEFAULT,
)
from state import _current_group_profile_id, _codex_threads, _codex_thread_turns
from tool_access import allowed_tool_names_for_level

_CODEX_MAX_THREAD_TURNS = int(os.environ.get("APEX_CODEX_MAX_TURNS", "8"))

# Valid Codex sandbox modes (passed to -s flag)
_VALID_CODEX_SANDBOX = {"read-only", "suggest", "full"}


def _get_codex_scope_key(chat_id: str) -> tuple[str, str]:
    """Return (scope_key, profile_id) for Codex thread state."""
    profile_id = _current_group_profile_id.get("")
    return (f"{chat_id}:{profile_id}", profile_id) if profile_id else (chat_id, "")


def _resolve_codex_profile_overrides(chat_id: str) -> tuple[str, str]:
    """Resolve per-agent workspace and sandbox mode from tool_policy JSON.

    tool_policy format: {"workspace": "/path/to/repo", "sandbox": "suggest"}
    Returns (workspace_path, sandbox_mode) with safe defaults.
    """
    codex_workspace = str(env.get_runtime_workspace_root())
    codex_sandbox = "read-only"
    try:
        from db import _get_db
        from state import _db_lock
        pid = _current_group_profile_id.get("")
        with _db_lock:
            conn = _get_db()
            if pid:
                row = conn.execute(
                    "SELECT tool_policy FROM agent_profiles WHERE id = ?", (pid,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT ap.tool_policy FROM agent_profiles ap "
                    "INNER JOIN chats c ON c.profile_id = ap.id WHERE c.id = ?",
                    (chat_id,)
                ).fetchone()
            conn.close()
        if row and row[0]:
            policy = json.loads(row[0])
            if isinstance(policy, dict):
                ws = policy.get("workspace", "")
                if ws and Path(ws).is_dir():
                    codex_workspace = ws
                sb = policy.get("sandbox", "")
                if sb in _VALID_CODEX_SANDBOX:
                    codex_sandbox = sb
    except Exception as e:
        log(f"codex profile overrides: {e}")
    return codex_workspace, codex_sandbox
from streaming import _send_stream_event, _load_recovery_journal, _cleanup_recovery_journal


def _public_codex_error_message(err_msg: str) -> str:
    text = str(err_msg or "").strip()
    lower = text.lower()
    limit_signatures = (
        "chunk is longer than limit",
        "chunk_size",
        "too large to process",
        "chunk exceed the limit",
        "separator is not found",
    )
    if any(sig in lower for sig in limit_signatures):
        return "Codex hit an internal size limit while preparing the response. Retry the turn or narrow the scope."
    return "Codex encountered an internal error while preparing the response. Retry the turn."


def _persist_codex_thread(chat_id: str, thread_id: str, turns: int) -> None:
    """Write Codex thread state to DB settings for restart survival."""
    try:
        _scope_key, profile_id = _get_codex_scope_key(chat_id)
        if profile_id:
            settings = _get_chat_settings(chat_id)
            thread_map = dict(settings.get("codex_threads_by_profile") or {})
            turns_map = dict(settings.get("codex_thread_turns_by_profile") or {})
            thread_map[profile_id] = thread_id
            turns_map[profile_id] = int(turns)
            _update_chat_settings(
                chat_id,
                {
                    "codex_threads_by_profile": thread_map,
                    "codex_thread_turns_by_profile": turns_map,
                },
            )
        else:
            _update_chat_settings(chat_id, {"codex_thread_id": thread_id, "codex_thread_turns": turns})
    except Exception:
        pass  # fire-and-forget — never fail the stream


def _clear_persisted_codex_thread(chat_id: str) -> None:
    """Clear persisted Codex thread state from DB."""
    try:
        _scope_key, profile_id = _get_codex_scope_key(chat_id)
        if profile_id:
            settings = _get_chat_settings(chat_id)
            thread_map = dict(settings.get("codex_threads_by_profile") or {})
            turns_map = dict(settings.get("codex_thread_turns_by_profile") or {})
            thread_map.pop(profile_id, None)
            turns_map.pop(profile_id, None)
            _update_chat_settings(
                chat_id,
                {
                    "codex_threads_by_profile": thread_map,
                    "codex_thread_turns_by_profile": turns_map,
                },
            )
        else:
            _update_chat_settings(chat_id, {"codex_thread_id": "", "codex_thread_turns": 0})
    except Exception:
        pass


def _get_codex_thread_state(chat_id: str) -> tuple[str, int, str]:
    """Return (thread_id, turns, scope_key) for the current Codex turn."""
    scope_key, profile_id = _get_codex_scope_key(chat_id)
    existing_thread = _codex_threads.get(scope_key, "")
    thread_turns = _codex_thread_turns.get(scope_key, 0)
    if existing_thread:
        return existing_thread, thread_turns, scope_key

    try:
        settings = _get_chat_settings(chat_id)
        if profile_id:
            thread_map = settings.get("codex_threads_by_profile") or {}
            turns_map = settings.get("codex_thread_turns_by_profile") or {}
            existing_thread = str(thread_map.get(profile_id, "") or "")
            thread_turns = int(turns_map.get(profile_id, 0) or 0)
        else:
            existing_thread = str(settings.get("codex_thread_id", "") or "")
            thread_turns = int(settings.get("codex_thread_turns", 0) or 0)
        if existing_thread:
            _codex_threads[scope_key] = existing_thread
            _codex_thread_turns[scope_key] = thread_turns
            log(
                f"codex thread restored from DB: session={scope_key[:24]} "
                f"thread={existing_thread[:8]} turns={thread_turns}"
            )
    except Exception:
        pass
    return existing_thread, thread_turns, scope_key


def _build_journal_recovery_context(chat_id: str) -> str:
    """Extract tool chain from crash recovery journal and return as context block."""
    events = _load_recovery_journal(chat_id)
    if not events:
        return ""
    tool_chain: list[str] = []
    partial_parts: list[str] = []
    for _, evt in events:
        evt_type = evt.get("type", "")
        if evt_type == "tool_use":
            name = evt.get("name", "tool")
            inp = str(evt.get("input", ""))[:200]
            tool_chain.append(f"  - {name}: {inp}")
        elif evt_type == "tool_result":
            content = str(evt.get("content", ""))[:300]
            tool_chain.append(f"    result: {content}")
        elif evt_type == "text":
            partial_parts.append(evt.get("text", ""))
        elif evt_type == "error":
            tool_chain.append(f"  - ERROR: {evt.get('message', '')[:200]}")
    parts: list[str] = []
    if tool_chain:
        parts.append("Tool chain from crashed session:\n" + "\n".join(tool_chain))
    partial = "".join(partial_parts).strip()
    if partial:
        parts.append(f"Partial response:\n{partial[:1000]}")
    if not parts:
        _cleanup_recovery_journal(chat_id)
        return ""
    _cleanup_recovery_journal(chat_id)
    return (
        "\n[System: Your previous session crashed mid-execution. "
        "Here is what was in progress:\n" + "\n\n".join(parts) +
        "\nContinue from where the crash occurred. Do not repeat completed work.]\n\n"
    )


from context import (
    _get_profile_prompt, _get_group_roster_prompt,
    _get_memory_prompt, _get_workspace_context,
)
from agent_sdk import _load_attachment

# Local model tool calling
try:
    from local_model.tool_loop import run_tool_loop
    from local_model.context import build_system_prompt
    _TOOL_LOOP_AVAILABLE = True
except ImportError:
    _TOOL_LOOP_AVAILABLE = False

# Config imported from env.py


_BACKEND_LABELS = {
    "codex": "Codex",
    "ollama": "Ollama",
    "xai": "xAI",
    "mlx": "MLX",
}
_CODEX_RESPONSES_API_MODELS = {"o3", "o4-mini"}
def validate_backend_attachments(backend: str, attachments: list[dict] | None) -> str | None:
    """Return a user-facing error when a backend cannot handle the attachment set."""
    if not attachments:
        return None

    loaded = [_load_attachment(att) for att in attachments]
    if backend == "codex":
        return "Attachments are not supported for Codex chats yet. Switch this chat to Claude to send files."

    if backend in {"ollama", "xai", "mlx"} and any(item["type"] == "text" for item in loaded):
        label = _BACKEND_LABELS.get(backend, backend)
        return f"Text attachments are not supported for {label} chats yet. Image attachments still work."

    return None


# ---------------------------------------------------------------------------
# Codex CLI backend
# ---------------------------------------------------------------------------

async def _run_codex_chat(chat_id: str, prompt: str, model: str | None = None,
                           attachments: list[dict] | None = None) -> dict:
    """Run a chat response via the Codex CLI (gpt-5.4, o3, o4-mini)."""
    effective_model = model or "codex:gpt-5.4"
    cli_model = effective_model.removeprefix("codex:")

    # Models that require OpenAI API key (not available on ChatGPT OAuth)
    _API_KEY_MODELS = {"o3", "o4-mini"}
    use_api_key = cli_model in _API_KEY_MODELS

    # Check for existing Codex thread to resume (in-memory → DB fallback)
    existing_thread, thread_turns, scope_key = _get_codex_thread_state(chat_id)

    # Rotate thread if it's getting long — prevents context overflow
    is_rotation = False
    if existing_thread and thread_turns >= _CODEX_MAX_THREAD_TURNS:
        log(
            f"codex thread rotation: session={scope_key[:24]} "
            f"thread={existing_thread[:8]} turns={thread_turns}/{_CODEX_MAX_THREAD_TURNS}"
        )
        _codex_threads.pop(scope_key, None)
        _codex_thread_turns.pop(scope_key, None)
        _clear_persisted_codex_thread(chat_id)
        is_rotation = True
        existing_thread = ""

    # Per-agent workspace + sandbox from tool_policy
    codex_workspace, codex_sandbox = _resolve_codex_profile_overrides(chat_id)

    if existing_thread:
        # Resume existing session — Codex already has full conversation history.
        # Skip context injection: the thread carries profile/roster/workspace from
        # prior turns. Re-injecting every turn causes ~4K token bloat per turn that
        # compounds as Codex replays the full thread on resume.
        # Exception: inject a minimal identity anchor to prevent character capture.
        # GPT-series models drift into impersonating other agents (writing [Operations]:
        # etc.) on long relay threads where their own name hasn't appeared recently.
        _anchor_pid = _current_group_profile_id.get("")
        _anchor_name = ""
        if _anchor_pid:
            try:
                from db import _get_db
                from state import _db_lock
                with _db_lock:
                    _anchor_conn = _get_db()
                    _anchor_row = _anchor_conn.execute(
                        "SELECT name FROM agent_profiles WHERE id = ?", (_anchor_pid,)
                    ).fetchone()
                    _anchor_conn.close()
                _anchor_name = _anchor_row[0] if _anchor_row else ""
            except Exception:
                pass
        if _anchor_name:
            full_prompt = (
                f"<system-reminder>You are {_anchor_name}. "
                "Respond only as yourself. Do not write as, speak for, or impersonate "
                "any other agent. Never prefix your response with another agent's name."
                f"</system-reminder>\n\n{prompt}"
            )
        else:
            full_prompt = prompt
        log(f"codex resume: session={scope_key[:24]} thread={existing_thread[:8]} (identity anchor={'yes' if _anchor_name else 'no'})")
        cmd = [
            CODEX_CLI, "exec", "resume", existing_thread,
            "--json", "--skip-git-repo-check",
            "-m", cli_model, "-",
        ]
    else:
        # Fresh or rotated session — inject profile + workspace context + build speaker-aware history
        profile_prompt = _get_profile_prompt(chat_id)
        group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=prompt)
        memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=prompt)
        workspace_ctx = _get_workspace_context(chat_id)
        ctx_prefix = f"{profile_prompt}{group_roster_prompt}{memory_prompt}{workspace_ctx}"
        full_prompt = f"{ctx_prefix}{prompt}" if ctx_prefix else prompt

        # Fetch wider window, then classify: crash recovery / stale return / cold call
        recent = _get_messages(chat_id, days=1)["messages"]
        current_pid = _current_group_profile_id.get("")
        fetch_window = max(_CODEX_MAX_THREAD_TURNS + 4, 12)  # extra headroom for filtering
        all_recent = [m for m in recent[-fetch_window:] if "<system-reminder>" not in m["content"]]

        # Identify own messages — in 1:1 chats (no current_pid), all assistant msgs are "self"
        def _is_self(m: dict) -> bool:
            if m["role"] != "assistant":
                return False
            sid = m.get("speaker_id", "")
            if current_pid:
                return sid == current_pid
            return True  # 1:1 chat — sole assistant

        self_msgs = [m for m in all_recent if _is_self(m)]

        # Check if recent self messages include tool use → crash/restart signal
        self_has_tools = any(
            (m.get("tool_events", "[]") or "[]") != "[]"
            for m in self_msgs[-3:]
        )

        if self_msgs and self_has_tools:
            # CRASH RECOVERY — prioritize own tool chain + some group context
            self_window = self_msgs[-6:]
            self_set = set(id(m) for m in self_window)
            other_msgs = [m for m in all_recent if id(m) not in self_set][-3:]
            ordered = sorted(self_window + other_msgs, key=lambda m: m.get("created_at", ""))
            context_mode = "crash_recovery"
        elif self_msgs:
            # STALE RETURN — participated earlier, conversation moved on
            ordered = all_recent[-_CODEX_MAX_THREAD_TURNS:]
            context_mode = "stale_return"
        else:
            # COLD CALL — new to this conversation
            ordered = all_recent[-_CODEX_MAX_THREAD_TURNS:]
            context_mode = "cold_call"

        if DEBUG:
            log(f"codex context: chat={chat_id[:8]} mode={context_mode} self_msgs={len(self_msgs)} ordered={len(ordered)}")

        # Build history lines with "You" tagging for self messages
        history_lines: list[str] = []

        # For stale return, prepend a brief "your last activity" line
        if context_mode == "stale_return" and self_msgs:
            last_self = self_msgs[-1]
            last_tools = last_self.get("tool_events", "[]") or "[]"
            tool_summary = ""
            if last_tools != "[]":
                try:
                    tools = json.loads(last_tools)
                    names = [t.get("name", "tool") for t in tools if t.get("type") == "tool_use"]
                    if names:
                        tool_summary = f" (tools: {', '.join(names)})"
                except (json.JSONDecodeError, TypeError):
                    pass
            history_lines.append(f"[Your last activity{tool_summary}: {last_self['content'][:200]}]")

        for m in ordered:
            role = m["role"]
            content = m["content"]
            speaker_id = m.get("speaker_id", "")

            # Label: "You" for self, speaker name for other agents, "user" for humans
            if _is_self(m):
                label = "You"
            elif role == "assistant" and speaker_id:
                label = m.get("speaker_name", speaker_id)
            else:
                label = role

            line = f"[{label}] {content[:3000]}"

            # Tool event summaries for assistant messages
            tool_json = m.get("tool_events", "[]") or "[]"
            if role == "assistant" and tool_json != "[]":
                try:
                    tools = json.loads(tool_json)
                    tool_names = [t.get("name", "tool") for t in tools if t.get("type") == "tool_use"]
                    if tool_names:
                        line += f"\n  [tools used: {', '.join(tool_names)}]"
                except (json.JSONDecodeError, TypeError):
                    pass
            history_lines.append(line)

        if history_lines:
            history_block = "\n".join(history_lines)
            if is_rotation:
                context_note = (
                    "\n[System: This is a continuation of your previous work. "
                    "Continue from where you left off — do not repeat work already completed.]\n\n"
                )
            elif context_mode == "crash_recovery":
                context_note = (
                    "\n[System: Your previous session ended unexpectedly. "
                    "Your tool chain and recent work are shown above. "
                    "Continue from where you left off — do not repeat completed work.]\n\n"
                )
            elif context_mode == "cold_call":
                context_note = (
                    "\n[System: You are joining an ongoing conversation. "
                    "The recent discussion is shown above for context.]\n\n"
                )
            else:
                context_note = ""
            full_prompt = f"<conversation-history>\n{history_block}\n</conversation-history>\n{context_note}\n{full_prompt}"

        # Check for recovery journal from a previous crash (richer than DB messages)
        journal_ctx = _build_journal_recovery_context(chat_id)
        if journal_ctx:
            full_prompt = f"{journal_ctx}{full_prompt}"
            log(f"codex journal recovery injected: chat={chat_id[:8]}")

        cmd = [
            CODEX_CLI, "exec", "--json",
            "--skip-git-repo-check",
            "-m", cli_model, "-s", codex_sandbox, "-C", codex_workspace, "-",
        ]

    # Spawn codex CLI — API-key models use a separate config dir with API auth
    codex_env = {**os.environ, "OPENAI_API_KEY": OPENAI_API_KEY}
    if use_api_key:
        api_config = Path.home() / ".codex-api"
        if api_config.is_dir():
            codex_env["CODEX_CONFIG_DIR"] = str(api_config)
            log(f"codex: using API key auth for {cli_model}")
        else:
            log(f"codex: WARNING — {cli_model} requires API key but ~/.codex-api not configured")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=codex_env,
    )
    _codex_started_at = time.monotonic()

    if proc.stdin is not None:
        proc.stdin.write(full_prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

    result_text = ""
    thinking_text = ""
    pending_agent_message = ""   # holds last agent_message until we know if it's narration or final answer
    tool_events: list[dict] = []
    tokens_in = 0
    tokens_out = 0
    thread_id = ""

    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line_str = line.decode().strip()
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")

        # Capture thread_id for session resume
        if event_type == "thread.started":
            thread_id = event.get("thread_id", "")
            if thread_id:
                _codex_threads[scope_key] = thread_id
                if not existing_thread:
                    _codex_thread_turns[scope_key] = 0
                _persist_codex_thread(chat_id, thread_id, _codex_thread_turns.get(scope_key, 0))
                if DEBUG:
                    log(f"codex thread: session={scope_key[:24]} thread={thread_id[:8]} fresh={not existing_thread}")
            continue

        if event_type == "item.started":
            item = event.get("item", {})
            if item.get("type") == "command_execution":
                tool_id = str(uuid.uuid4())
                tool_evt = {"type": "tool_use", "id": tool_id, "name": "command", "input": item.get("command", "")}
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

        elif event_type == "item.completed":
            item = event.get("item", {})
            item_type = item.get("type", "")

            if item_type == "agent_message":
                text = item.get("text", "")
                if not text:
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            text += part.get("text", "")
                if text:
                    # Flush the previous agent_message as thinking — it was narration,
                    # not the final answer (a newer message arrived after it).
                    if pending_agent_message:
                        thinking_text += pending_agent_message
                        await _send_stream_event(chat_id, {"type": "thinking", "text": pending_agent_message})
                    # Hold this message; we won't know if it's the final answer until
                    # the next agent_message arrives or turn.completed fires.
                    pending_agent_message = text

            elif item_type == "command_execution":
                tool_id = str(uuid.uuid4())
                output = item.get("output", "")
                tool_evt = {"type": "tool_result", "id": tool_id, "content": output[:2000]}
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

            elif item_type == "reasoning":
                text = item.get("text", "")
                if not text:
                    for part in item.get("content", []):
                        if part.get("type") == "text":
                            text += part.get("text", "")
                if text:
                    thinking_text += text
                    await _send_stream_event(chat_id, {"type": "thinking", "text": text})

            elif item_type == "file_change":
                tool_id = str(uuid.uuid4())
                fname = item.get("filename", "unknown")
                await _send_stream_event(chat_id, {"type": "tool_use", "id": tool_id, "name": "file_change", "input": fname})
                await _send_stream_event(chat_id, {"type": "tool_result", "id": tool_id, "content": f"File changed: {fname}"})

        elif event_type == "turn.completed":
            usage = event.get("usage", {})
            tokens_in = usage.get("input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)
            # The last agent_message is the final answer — route it to result_text.
            if pending_agent_message:
                result_text = pending_agent_message
                await _send_stream_event(chat_id, {"type": "text", "text": pending_agent_message})
                pending_agent_message = ""

    await proc.wait()
    # Fallback: if turn.completed never fired (crash/timeout), treat the last
    # pending agent_message as the final answer rather than losing it.
    if pending_agent_message and not result_text:
        result_text = pending_agent_message
        await _send_stream_event(chat_id, {"type": "text", "text": pending_agent_message})
    stderr_data = await proc.stderr.read() if proc.stderr else b""
    if proc.returncode != 0 and not result_text:
        err_msg = stderr_data.decode()[:500] if stderr_data else f"codex exited with code {proc.returncode}"
        log(f"codex process error: {err_msg}")

        # If resume failed, clear thread and retry as fresh session
        if existing_thread:
            log(f"codex resume failed, retrying fresh: session={scope_key[:24]} thread={existing_thread[:8]}")
            _codex_threads.pop(scope_key, None)
            _codex_thread_turns.pop(scope_key, None)
            _clear_persisted_codex_thread(chat_id)
            return await _run_codex_chat(chat_id, prompt, model=model, attachments=attachments)

        # Chunking error — task too large for Codex's file indexer.
        # Retry once with a decomposition directive that tells Codex to
        # work on files individually instead of indexing the whole codebase.
        _CHUNK_ERRORS = ("chunk is longer than limit", "chunk_size", "too large to process")
        if any(sig in err_msg.lower() for sig in _CHUNK_ERRORS) and not prompt.startswith("[DECOMPOSE]"):
            log(f"codex chunking error detected, retrying with decomposition directive: chat={chat_id[:8]}")
            decompose_prefix = (
                "[DECOMPOSE] IMPORTANT: The previous attempt failed because the codebase is too large "
                "to process at once. You MUST break this task into phases:\n"
                "1. List the specific files you need to examine (do NOT index the entire codebase)\n"
                "2. Read and process ONE file at a time using cat or head\n"
                "3. Summarize findings from each file before moving to the next\n"
                "4. Compile your final analysis from the per-file summaries\n\n"
                "Never try to load all files simultaneously. Work file-by-file.\n\n"
            )
            return await _run_codex_chat(chat_id, decompose_prefix + prompt, model=model, attachments=attachments)

        await _send_stream_event(
            chat_id,
            {
                "type": "error",
                "message": _public_codex_error_message(err_msg),
                "retryable": True,
            },
        )
        return {"text": "", "is_error": True, "error": err_msg,
                "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
                "session_id": None, "thinking": "", "tool_events": json.dumps(tool_events)}

    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    await _send_stream_event(chat_id, {
        "type": "result", "is_error": False,
        "cost_usd": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "session_id": thread_id or None,
        "context_tokens_in": tokens_in,
        "context_window": _cw,
        "thinking": thinking_text,
        "duration_ms": int((time.monotonic() - _codex_started_at) * 1000),
    })
    if thread_id:
        _codex_thread_turns[scope_key] = _codex_thread_turns.get(scope_key, 0) + 1
        turns = _codex_thread_turns[scope_key]
        _persist_codex_thread(chat_id, thread_id, turns)
        log(
            f"codex turn complete: session={scope_key[:24]} thread={thread_id[:8]} "
            f"turn={turns}/{_CODEX_MAX_THREAD_TURNS} tokens={tokens_in}in/{tokens_out}out"
        )
    return {"text": result_text, "is_error": False, "error": None,
            "cost_usd": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "session_id": thread_id or None, "thinking": thinking_text, "tool_events": json.dumps(tool_events)}


# ---------------------------------------------------------------------------
# Ollama / xAI / MLX backend
# ---------------------------------------------------------------------------

async def _run_ollama_chat(chat_id: str, prompt: str, model: str | None = None,
                           attachments: list[dict] | None = None,
                           permission_policy: dict | None = None) -> dict:
    """Run a chat response from Ollama/xAI/MLX with tool-calling support."""
    effective_model = model or MODEL
    recent = _get_messages(chat_id, days=1)["messages"]
    current_pid = _current_group_profile_id.get("")
    tool_policy = permission_policy or (
        _get_profile_tool_policy(current_pid)
        if current_pid
        else _get_chat_tool_policy(chat_id)
    )
    permission_level = int(tool_policy.get("level", 2))
    allowed_commands = list(tool_policy.get("allowed_commands") or [])
    allowed_local_tools = allowed_tool_names_for_level(permission_level)
    if _TOOL_LOOP_AVAILABLE and ALLOW_LOCAL_TOOLS:
        sys_prompt = build_system_prompt(effective_model, permission_level=permission_level, allowed_tool_names=allowed_local_tools)
    else:
        sys_prompt = f"You are {effective_model}, a local AI model running via Ollama. Be helpful and concise."

    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=prompt)
    memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=prompt)
    workspace_ctx = _get_workspace_context(chat_id)
    if profile_prompt or group_roster_prompt or memory_prompt or workspace_ctx:
        sys_prompt = f"{sys_prompt}\n\n{profile_prompt}{group_roster_prompt}{memory_prompt}{workspace_ctx}"

    # In group chats, conversation history prefixes other agents' messages with
    # [AgentName]: for attribution. GPT-series models learn this pattern and can
    # start their own responses with [AgentName]: — impersonating other agents.
    # Append an explicit identity lock after all context so it is the last
    # instruction the model reads before the conversation history.
    if current_pid:
        sys_prompt = (
            f"{sys_prompt}\n\n<system-reminder>"
            "You are responding as yourself. "
            "In the conversation history above, messages from other agents are prefixed "
            "with [AgentName]: to show who said them — this is a display convention only. "
            "Never start your own response with [AgentName]: or any other agent's name. "
            "Do not impersonate, speak for, or write as any other agent."
            "</system-reminder>"
        )

    messages = [{"role": "system", "content": sys_prompt}]
    for m in recent[-50:]:
        content = m["content"]
        if "<system-reminder>" in content:
            continue
        role = m["role"]
        if role not in ("user", "assistant"):
            continue
        speaker_id = m.get("speaker_id", "")
        if role == "assistant" and current_pid and speaker_id and speaker_id != current_pid:
            speaker_name = m.get("speaker_name", speaker_id)
            content = f"[{speaker_name}]: {content}"
        messages.append({"role": role, "content": content})

    user_msg: dict = {"role": "user", "content": prompt}
    if attachments:
        images_b64: list[str] = []
        for att in attachments:
            try:
                item = _load_attachment(att)
                if item["type"] == "image":
                    images_b64.append(base64.b64encode(item["data"]).decode())
            except (ValueError, Exception) as e:
                log(f"ollama image load error: {e}")
        if images_b64:
            user_msg["images"] = images_b64
    messages.append(user_msg)

    if _TOOL_LOOP_AVAILABLE:
        async def emit(event: dict):
            await _send_stream_event(chat_id, event)

        backend = _get_model_backend(effective_model)
        runtime_workspace_paths = env.get_runtime_workspace_paths()
        audit_context = {
            "source": "tool_loop",
            "chat_id": chat_id,
            "backend": backend,
            "model": effective_model,
        }

        # Remote APIs (xai, codex) always use tool loop — they don't depend
        # on ALLOW_LOCAL_TOOLS which gates local Ollama/MLX tool calling.
        if backend == "xai":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                api_key=XAI_API_KEY,
                api_url="https://api.x.ai/v1",
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
            )
        elif backend == "codex":
            codex_model = effective_model[6:]
            if codex_model in _CODEX_RESPONSES_API_MODELS and OPENAI_API_KEY:
                result = await run_tool_loop(
                    ollama_url=OLLAMA_BASE_URL,
                    model=codex_model,
                    messages=messages,
                    emit_event=emit,
                    workspace=runtime_workspace_paths,
                    api_key=OPENAI_API_KEY,
                    api_url="https://api.openai.com/v1",
                    max_iterations=MAX_TOOL_ITERATIONS,
                    permission_level=permission_level,
                    allowed_tools=allowed_local_tools,
                    allowed_commands=allowed_commands,
                    audit_context=audit_context,
                )
            else:
                result = await run_tool_loop(
                    ollama_url=OLLAMA_BASE_URL,
                    model=codex_model,
                    messages=messages,
                    emit_event=emit,
                    workspace=runtime_workspace_paths,
                    api_key="chatgpt-oauth",
                    api_url="chatgpt",
                    max_iterations=MAX_TOOL_ITERATIONS,
                    permission_level=permission_level,
                    allowed_tools=allowed_local_tools,
                    allowed_commands=allowed_commands,
                    audit_context=audit_context,
                )
        elif ALLOW_LOCAL_TOOLS and backend == "mlx":
            mlx_model = effective_model[4:]
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=mlx_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                api_key="local",
                api_url=f"{MLX_BASE_URL}/v1",
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
            )
        elif ALLOW_LOCAL_TOOLS:
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
            )
        else:
            result = None  # fall through to plain streaming below

        if result is not None:
            _est = _estimate_tokens(chat_id)
            _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
            await _send_stream_event(chat_id, {
                "type": "result", "is_error": result.get("is_error", False),
                "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
                "session_id": None,
                "context_tokens_in": _est,
                "context_window": _cw,
                "thinking": result.get("thinking", ""),
                "duration_ms": result.get("duration_ms", 0),
            })
            return result

    # Fallback: plain text streaming (no tool support)
    _stream_started_at = time.monotonic()
    payload = json.dumps({
        "model": effective_model, "messages": messages, "stream": True,
    }).encode()
    chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _stream_ollama():
        try:
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/chat", data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=300)
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode())
                if chunk.get("done"):
                    break
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                content = msg.get("content", "")
                if thinking:
                    chunk_queue.put_nowait(("thinking", thinking))
                if content:
                    chunk_queue.put_nowait(("text", content))
        except Exception as e:
            chunk_queue.put_nowait(("error", str(e)))
        finally:
            chunk_queue.put_nowait(None)

    asyncio.get_event_loop().run_in_executor(None, _stream_ollama)
    result_text, thinking_text, is_error, error_msg = "", "", False, ""
    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        chunk_type, chunk_data = chunk
        if chunk_type == "error":
            error_msg = chunk_data
            is_error = True
            log(f"ollama error: {error_msg}")
            await _send_stream_event(chat_id, {"type": "error", "message": f"Ollama: {error_msg}"})
            break
        elif chunk_type == "thinking":
            thinking_text += chunk_data
            await _send_stream_event(chat_id, {"type": "thinking", "text": chunk_data})
        elif chunk_type == "text":
            result_text += chunk_data
            await _send_stream_event(chat_id, {"type": "text", "text": chunk_data})

    _est = _estimate_tokens(chat_id) + len(result_text) // 4
    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    _stream_duration_ms = int((time.monotonic() - _stream_started_at) * 1000)
    await _send_stream_event(chat_id, {
        "type": "result", "is_error": is_error,
        "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        "context_tokens_in": _est,
        "context_window": _cw,
        "thinking": thinking_text,
        "duration_ms": _stream_duration_ms,
    })
    return {"text": result_text, "is_error": is_error, "error": error_msg or None,
            "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
            "session_id": None, "thinking": thinking_text, "tool_events": "[]",
            "duration_ms": _stream_duration_ms}
