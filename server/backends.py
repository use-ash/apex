"""Non-Claude chat backends — Codex CLI and Ollama/xAI/MLX.

Routes chat messages through the Codex CLI (OpenAI models) or the
local model tool loop (Ollama, xAI, MLX) with streaming support.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import env
from env import (
    MODEL, DEBUG, CODEX_CLI, GROK_CLI, OPENAI_API_KEY, XAI_API_KEY,
    DEEPSEEK_API_KEY, ZHIPU_API_KEY, GOOGLE_API_KEY,
    MAX_TOOL_ITERATIONS, ALLOW_LOCAL_TOOLS,
)

from db import (
    _get_messages,
    _estimate_tokens,
    _get_chat_settings,
    _update_chat_settings,
    _get_chat_tool_policy,
    _get_profile_tool_policy,
    _get_chat,
)
from log import log
from model_dispatch import (
    _get_model_backend, OLLAMA_BASE_URL, MLX_BASE_URL,
    MODEL_CONTEXT_WINDOWS, MODEL_CONTEXT_DEFAULT,
)
from state import _current_group_profile_id, _codex_threads, _codex_thread_turns, _grok_sessions, _grok_session_turns
from tool_access import allowed_tool_names_for_level, resolve_profile_extra_tools
import tool_surface

_CODEX_MAX_THREAD_TURNS = int(os.environ.get("APEX_CODEX_MAX_TURNS", "8"))
_GROK_MAX_SESSION_TURNS = int(os.environ.get("APEX_GROK_MAX_TURNS", "12"))

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
    _get_context_energy_prompt,
    _get_temporal_context,
    _get_calibration_primer,
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
    "deepseek": "DeepSeek",
    "zhipu": "Zhipu",
    "google": "Gemini",
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

    if backend == "xai":
        return "Attachments are not supported for Grok CLI chats yet. Switch this chat to Claude to send files."

    if backend in {"ollama", "deepseek", "zhipu", "google", "mlx"} and any(item["type"] == "text" for item in loaded):
        label = _BACKEND_LABELS.get(backend, backend)
        return f"Text attachments are not supported for {label} chats yet. Image attachments still work."

    return None


# ---------------------------------------------------------------------------
# Codex CLI backend
# ---------------------------------------------------------------------------

async def _run_codex_chat(chat_id: str, prompt: str, model: str | None = None,
                           attachments: list[dict] | None = None) -> dict:
    """Run a chat response via the Codex CLI (gpt-5.6*, gpt-5.5, gpt-5.4, o3, o4-mini)."""
    effective_model = model or "codex:gpt-5.5"
    cli_model = effective_model.removeprefix("codex:")
    # ChatGPT OAuth does not accept bare `gpt-5.6` — map to Sol (CLI slug).
    _CODEX_CLI_MODEL_ALIASES = {
        "gpt-5.6": "gpt-5.6-sol",
    }
    cli_model = _CODEX_CLI_MODEL_ALIASES.get(cli_model, cli_model)

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

    # PR3 — resolve Apex MCP (Track B / core pack) and project nested -c args.
    # Prefer real CODEX_HOME; never CODEX_CONFIG_DIR / ~/.codex-api (PR0 §6 dead).
    _cu_target_cx: str | None = None
    _int_enabled_cx = False
    _profile_id_cx = ""
    _perm_level_cx = 2
    try:
        _chat_row_cx = _get_chat(chat_id) if chat_id else None
        if _chat_row_cx:
            _cu_target_cx = _chat_row_cx.get("computer_use_target") or None
            _int_enabled_cx = bool(_chat_row_cx.get("interceptor_enabled"))
            _profile_id_cx = str(_chat_row_cx.get("profile_id") or "")
    except Exception as _e_cx:
        log(f"codex pr3 chat lookup: {_e_cx}")
    _group_pid_cx = _current_group_profile_id.get("")
    if _group_pid_cx:
        _profile_id_cx = _group_pid_cx
    try:
        if _profile_id_cx:
            _policy_cx = _get_profile_tool_policy(_profile_id_cx) or {}
        else:
            _policy_cx = _get_chat_tool_policy(chat_id) if chat_id else {}
        _perm_level_cx = int(_policy_cx.get("level", 2))
    except Exception as _e_pol_cx:
        log(f"codex policy lookup: {_e_pol_cx}")
    _codex_extras = (
        resolve_profile_extra_tools(_profile_id_cx or None) if _profile_id_cx else None
    )
    _codex_pack = "core"
    _resolved_mcp_cx: dict = {}
    _codex_c_args: list[str] = []
    _codex_env_ovr: dict[str, str] = {}
    try:
        _resolved_mcp_cx = tool_surface.resolve_for_codex(
            chat_id,
            workspace=codex_workspace,
            permission_level=_perm_level_cx,
            computer_use_target=_cu_target_cx,
            interceptor_enabled=_int_enabled_cx,
            extra_allowed_tools=_codex_extras,
            pack=_codex_pack,
        )
        # Fail-closed when gate-test / extras require claim_store but it is absent.
        if tool_surface.claim_store_required(
            extras=_codex_extras, profile_id=_profile_id_cx or None
        ) and "claim_store" not in _resolved_mcp_cx:
            err = (
                "CLAIM_STORE_REQUIRED: claim_store MCP not admitted for this Codex "
                "turn (gate-test / extras fail-closed). Check catalog + level."
            )
            log(f"codex {err}")
            await _send_stream_event(
                chat_id, {"type": "error", "message": err, "retryable": False}
            )
            return {
                "text": "",
                "is_error": True,
                "error": err,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }
        if _resolved_mcp_cx:
            _codex_c_args, _env_ovr_cx, _ = tool_surface.project_codex(
                _resolved_mcp_cx, permission_level=_perm_level_cx
            )
            # env overrides applied later into codex_env
            _codex_env_ovr = _env_ovr_cx
        else:
            _codex_env_ovr = {}
    except Exception as _e_proj_cx:
        log(f"codex project_codex failed, fail-open without Apex MCP: {_e_proj_cx}")
        _resolved_mcp_cx = {}
        _codex_c_args = []
        _codex_env_ovr = {}

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
        # Re-pass -c MCP overlays on resume (PR0 §4) so MCP stays attached.
        cmd = [
            CODEX_CLI, "exec",
            *_codex_c_args,
            "resume", existing_thread,
            "--json", "--skip-git-repo-check",
            "-m", cli_model, "-",
        ]
    else:
        # Fresh or rotated session — inject profile + workspace context + build speaker-aware history
        profile_prompt = _get_profile_prompt(chat_id)
        group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=prompt)
        memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=prompt)
        workspace_ctx = _get_workspace_context(chat_id)
        temporal_ctx = _get_temporal_context(chat_id)
        context_energy = _get_context_energy_prompt(chat_id)
        calibration = _get_calibration_primer(chat_id)
        ctx_prefix = f"{profile_prompt}{group_roster_prompt}{memory_prompt}{workspace_ctx}{temporal_ctx}{context_energy}{calibration}"
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
            CODEX_CLI, "exec",
            *_codex_c_args,
            "--json",
            "--skip-git-repo-check",
            "-m", cli_model, "-s", codex_sandbox, "-C", codex_workspace, "-",
        ]

    # Spawn codex CLI — always real CODEX_HOME (~/.codex). API-key models
    # (o3/o4-mini) authenticate via OPENAI_API_KEY / CODEX_API_KEY env or
    # auth.json under CODEX_HOME (PR0 §6). Do NOT set CODEX_CONFIG_DIR or
    # point at empty ~/.codex-api (dead path; not in modern CLI).
    codex_env = {**os.environ}
    if OPENAI_API_KEY:
        codex_env["OPENAI_API_KEY"] = OPENAI_API_KEY
    if use_api_key:
        if not (OPENAI_API_KEY or codex_env.get("CODEX_API_KEY") or codex_env.get("OPENAI_API_KEY")):
            log(
                f"codex: WARNING — {cli_model} typically needs OPENAI_API_KEY/"
                "CODEX_API_KEY; using real CODEX_HOME auth.json only"
            )
        else:
            log(f"codex: API-key model {cli_model} via env + real CODEX_HOME")
    if _codex_env_ovr:
        codex_env.update(_codex_env_ovr)
    log(
        f"codex spawn: model={cli_model} resume={bool(existing_thread)} "
        f"level={_perm_level_cx} pack={_codex_pack} mcp={len(_resolved_mcp_cx)} "
        f"c_args={len(_codex_c_args)//2} home=real cwd={codex_workspace}"
    )
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

    def _codex_item_id(item: dict) -> str:
        return str(item.get("id") or uuid.uuid4())

    def _codex_item_text(item: dict) -> str:
        text = item.get("text") or item.get("content") or ""
        if isinstance(text, str) and text:
            return text
        if isinstance(text, list):
            parts: list[str] = []
            for part in text:
                if isinstance(part, dict):
                    parts.append(str(part.get("text") or part.get("output_text") or ""))
                else:
                    parts.append(str(part))
            return "".join(parts)
        # Nested content array (SDK-style)
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                parts.append(str(part.get("text") or part.get("output_text") or ""))
            return "".join(parts)
        return str(text or "")

    def _codex_cmd_output(item: dict) -> str:
        # Live CLI (0.142+) uses aggregated_output; older builds used output.
        out = item.get("aggregated_output")
        if out is None or out == "":
            out = item.get("output") or item.get("stdout") or ""
        return str(out)

    def _codex_tool_name(item: dict) -> str:
        """Map Codex item types → UI tool name."""
        itype = item.get("type") or "tool"
        if itype == "command_execution":
            return "command"
        if itype == "file_change":
            return "file_change"
        if itype in {"mcp_tool_call", "function_call", "tool_call", "custom_tool_call"}:
            return (
                item.get("name")
                or item.get("tool")
                or item.get("server")
                or item.get("tool_name")
                or itype
            )
        if itype == "web_search":
            return "web_search"
        return str(itype)

    def _codex_tool_input(item: dict) -> str:
        itype = item.get("type") or ""
        if itype == "command_execution":
            return str(item.get("command") or "")
        if itype == "file_change":
            return str(item.get("filename") or item.get("path") or "unknown")
        raw = (
            item.get("arguments")
            or item.get("input")
            or item.get("params")
            or item.get("query")
            or ""
        )
        if not isinstance(raw, str):
            try:
                return json.dumps(raw)[:2000]
            except Exception:
                return str(raw)[:2000]
        return raw[:2000]

    # Item types that count as tool uses (not agent_message / reasoning).
    _CODEX_TOOL_ITEM_TYPES = frozenset({
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "function_call",
        "tool_call",
        "custom_tool_call",
        "web_search",
        "image_view",
        "collab_agent_tool_call",
    })

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
            item = event.get("item") or {}
            item_type = item.get("type") or ""
            if item_type in _CODEX_TOOL_ITEM_TYPES:
                tool_id = _codex_item_id(item)
                tool_evt = {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": _codex_tool_name(item),
                    "input": _codex_tool_input(item),
                }
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

        elif event_type == "item.completed":
            item = event.get("item") or {}
            item_type = item.get("type") or ""

            if item_type == "agent_message":
                text = _codex_item_text(item)
                if text:
                    # Flush the previous agent_message as thinking — it was narration,
                    # not the final answer (a newer message arrived after it).
                    if pending_agent_message:
                        thinking_text += pending_agent_message
                        await _send_stream_event(
                            chat_id, {"type": "thinking", "text": pending_agent_message}
                        )
                    # Hold this message; we won't know if it's the final answer until
                    # the next agent_message arrives or turn.completed fires.
                    pending_agent_message = text

            elif item_type in {"reasoning", "thought", "reasoning_summary"}:
                text = _codex_item_text(item)
                if text:
                    thinking_text += text
                    await _send_stream_event(chat_id, {"type": "thinking", "text": text})

            elif item_type in _CODEX_TOOL_ITEM_TYPES:
                tool_id = _codex_item_id(item)
                # If we never saw item.started (some builds only emit completed),
                # synthesize a tool_use so the UI still gets a pill.
                if not any(
                    t.get("id") == tool_id and t.get("type") == "tool_use"
                    for t in tool_events
                ):
                    use_evt = {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": _codex_tool_name(item),
                        "input": _codex_tool_input(item),
                    }
                    tool_events.append(use_evt)
                    await _send_stream_event(chat_id, use_evt)
                if item_type == "command_execution":
                    content = _codex_cmd_output(item)[:2000]
                elif item_type == "file_change":
                    content = f"File changed: {_codex_tool_input(item)}"
                else:
                    content = _codex_item_text(item) or _codex_cmd_output(item)
                    if not content:
                        content = str(
                            item.get("result")
                            or item.get("output")
                            or item.get("status")
                            or "ok"
                        )[:2000]
                # iOS / Claude convention: pair results via tool_use_id (not only id).
                # Missing tool_use_id leaves the tool_use row isComplete=false forever
                # ("Running command" spinner + 1/2 in Tools sheet).
                tool_evt = {
                    "type": "tool_result",
                    "id": tool_id,
                    "tool_use_id": tool_id,
                    "content": content,
                }
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

            elif item_type == "error":
                # Deprecation noise etc. — log, don't surface as hard error.
                msg = str(item.get("message") or "")[:300]
                if msg:
                    log(f"codex item error: {msg}")

        elif event_type == "turn.completed":
            usage = event.get("usage", {}) or {}
            tokens_in = int(usage.get("input_tokens", 0) or 0)
            tokens_out = int(usage.get("output_tokens", 0) or 0)
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
        return {
            "text": "",
            "is_error": True,
            "error": err_msg,
            "cost_usd": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "session_id": None,
            "thinking": thinking_text,
            "tool_events": json.dumps(tool_events),
            "duration_ms": int((time.monotonic() - _codex_started_at) * 1000),
        }

    _duration_ms = int((time.monotonic() - _codex_started_at) * 1000)
    _tool_events_json = json.dumps(tool_events)
    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    await _send_stream_event(chat_id, {
        "type": "result", "is_error": False,
        "cost_usd": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "session_id": thread_id or None,
        "context_tokens_in": tokens_in,
        "context_window": _cw,
        "thinking": thinking_text,
        "tool_events": _tool_events_json,
        "duration_ms": _duration_ms,
    })
    if thread_id:
        _codex_thread_turns[scope_key] = _codex_thread_turns.get(scope_key, 0) + 1
        turns = _codex_thread_turns[scope_key]
        _persist_codex_thread(chat_id, thread_id, turns)
        log(
            f"codex turn complete: session={scope_key[:24]} thread={thread_id[:8]} "
            f"turn={turns}/{_CODEX_MAX_THREAD_TURNS} tokens={tokens_in}in/{tokens_out}out "
            f"tools={len([t for t in tool_events if t.get('type')=='tool_use'])} "
            f"think_len={len(thinking_text)} dur={_duration_ms}"
        )
    return {
        "text": result_text,
        "is_error": False,
        "error": None,
        "cost_usd": 0,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "session_id": thread_id or None,
        "thinking": thinking_text,
        "tool_events": _tool_events_json,
        "duration_ms": _duration_ms,
    }


# ---------------------------------------------------------------------------
# Grok Build CLI backend (official xAI CLI — subscription / API key auth)
# ---------------------------------------------------------------------------

def _resolve_grok_cli() -> str:
    """Return path to grok binary (env override, PATH, then common install locs)."""
    import shutil
    candidates = [
        GROK_CLI,
        shutil.which("grok") or "",
        str(Path.home() / ".local" / "bin" / "grok"),
        str(Path.home() / ".grok" / "bin" / "grok"),
    ]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return GROK_CLI or "grok"


def _get_grok_scope_key(chat_id: str) -> tuple[str, str]:
    profile_id = _current_group_profile_id.get("")
    return (f"{chat_id}:{profile_id}", profile_id) if profile_id else (chat_id, "")


def _persist_grok_session(chat_id: str, session_id: str, turns: int) -> None:
    try:
        _scope_key, profile_id = _get_grok_scope_key(chat_id)
        if profile_id:
            settings = _get_chat_settings(chat_id)
            sess_map = dict(settings.get("grok_sessions_by_profile") or {})
            turns_map = dict(settings.get("grok_session_turns_by_profile") or {})
            sess_map[profile_id] = session_id
            turns_map[profile_id] = int(turns)
            _update_chat_settings(
                chat_id,
                {
                    "grok_sessions_by_profile": sess_map,
                    "grok_session_turns_by_profile": turns_map,
                },
            )
        else:
            _update_chat_settings(
                chat_id, {"grok_session_id": session_id, "grok_session_turns": turns}
            )
    except Exception:
        pass


def _clear_persisted_grok_session(chat_id: str) -> None:
    try:
        _scope_key, profile_id = _get_grok_scope_key(chat_id)
        if profile_id:
            settings = _get_chat_settings(chat_id)
            sess_map = dict(settings.get("grok_sessions_by_profile") or {})
            turns_map = dict(settings.get("grok_session_turns_by_profile") or {})
            sess_map.pop(profile_id, None)
            turns_map.pop(profile_id, None)
            _update_chat_settings(
                chat_id,
                {
                    "grok_sessions_by_profile": sess_map,
                    "grok_session_turns_by_profile": turns_map,
                },
            )
        else:
            _update_chat_settings(chat_id, {"grok_session_id": "", "grok_session_turns": 0})
    except Exception:
        pass


def _get_grok_session_state(chat_id: str) -> tuple[str, int, str]:
    scope_key, profile_id = _get_grok_scope_key(chat_id)
    existing = _grok_sessions.get(scope_key, "")
    turns = _grok_session_turns.get(scope_key, 0)
    if existing:
        return existing, turns, scope_key
    try:
        settings = _get_chat_settings(chat_id)
        if profile_id:
            sess_map = settings.get("grok_sessions_by_profile") or {}
            turns_map = settings.get("grok_session_turns_by_profile") or {}
            existing = str(sess_map.get(profile_id, "") or "")
            turns = int(turns_map.get(profile_id, 0) or 0)
        else:
            existing = str(settings.get("grok_session_id", "") or "")
            turns = int(settings.get("grok_session_turns", 0) or 0)
        if existing:
            _grok_sessions[scope_key] = existing
            _grok_session_turns[scope_key] = turns
            log(
                f"grok session restored from DB: session={scope_key[:24]} "
                f"sid={existing[:8]} turns={turns}"
            )
    except Exception:
        pass
    return existing, turns, scope_key


def _refresh_grok_token_if_needed() -> None:
    """Pre-flight token refresh for grok CLI OAuth.

    The grok CLI stores an OIDC access_token in ~/.grok/auth.json with a
    6-hour TTL. When it expires, the CLI falls back to the device-code flow
    — which opens a browser authorization prompt. The CLI does NOT
    auto-refresh using the stored refresh_token.

    This function checks the token's expiry and, if it's expired or about
    to expire (< 10 min TTL), refreshes it via the OAuth2 token endpoint
    and rewrites auth.json in place. Called before every grok spawn.
    """
    auth_path = Path.home() / ".grok" / "auth.json"
    if not auth_path.exists():
        return  # never logged in; CLI will prompt on first use
    try:
        auth = json.loads(auth_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    updated = False
    for key, entry in auth.items():
        if not isinstance(entry, dict) or "refresh_token" not in entry:
            continue
        expires_at = entry.get("expires_at", "")
        if expires_at:
            try:
                from datetime import datetime, timezone
                exp_dt = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )
                now_dt = datetime.now(timezone.utc)
                ttl = (exp_dt - now_dt).total_seconds()
                if ttl > 600:  # >10 min remaining, skip
                    continue
            except (ValueError, TypeError):
                pass  # can't parse — try refresh anyway

        issuer = entry.get("oidc_issuer", "https://auth.x.ai")
        client_id = entry.get("oidc_client_id", "")
        refresh_token = entry.get("refresh_token", "")
        if not client_id or not refresh_token:
            continue

        try:
            import urllib.parse
            data = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }).encode()
            req = urllib.request.Request(
                f"{issuer}/oauth2/token",
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_resp = json.loads(resp.read())
        except Exception as e:
            log(f"grok token refresh failed for {key[:40]}: {e}")
            continue

        new_access = token_resp.get("access_token", "")
        new_refresh = token_resp.get("refresh_token", "")
        new_expires_in = token_resp.get("expires_in", 21600)
        if not new_access:
            continue

        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)
        entry["key"] = new_access
        entry["expires_at"] = (
            now_dt + timedelta(seconds=new_expires_in)
        ).isoformat().replace("+00:00", "Z")
        if new_refresh:
            entry["refresh_token"] = new_refresh
        updated = True
        log(f"grok token refreshed for {key[:40]}: ttl={new_expires_in}s")

    if updated:
        try:
            tmp = auth_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(auth, indent=2))
            tmp.replace(auth_path)
        except OSError as e:
            log(f"grok token refresh write failed: {e}")


def _resolve_grok_workspace(chat_id: str) -> str:
    """Per-agent workspace from tool_policy, else runtime workspace root."""
    workspace = str(env.get_runtime_workspace_root())
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
                    (chat_id,),
                ).fetchone()
            conn.close()
        if row and row[0]:
            policy = json.loads(row[0])
            if isinstance(policy, dict):
                ws = policy.get("workspace", "")
                if ws and Path(ws).is_dir():
                    workspace = ws
    except Exception as e:
        log(f"grok workspace resolve: {e}")
    return workspace


def _public_grok_error_message(err_msg: str) -> str:
    text = str(err_msg or "").strip()
    lower = text.lower()
    if any(s in lower for s in ("not logged in", "unauthoriz", "invalid api key", "auth", "login")):
        return (
            "Grok CLI is not authenticated. Run `grok login` in a terminal, "
            "or set XAI_API_KEY in Credentials / .env, then retry."
        )
    if "not found" in lower or "no such file" in lower:
        return (
            "Grok CLI not found. Install with: curl -fsSL https://x.ai/cli/install.sh | bash"
        )
    return "Grok CLI hit an internal error while preparing the response. Retry the turn."


from urllib.parse import quote as _urlquote


def _grok_session_history_path(
    session_id: str,
    cwd: str,
    *,
    temp_grok_home: Path | None = None,
) -> Path | None:
    """Locate chat_history.jsonl for a Grok session.

    Prefer the turn's temp GROK_HOME (if Grok replaced the sessions symlink
    with a real dir under the temp home), then the durable ~/.grok/sessions
    tree. Call this *before* cleanup_projected_home.
    """
    if not session_id:
        return None
    encoded_cwd = _urlquote(cwd, safe="")
    candidates: list[Path] = []
    if temp_grok_home is not None:
        th = Path(temp_grok_home)
        candidates.append(th / "sessions" / encoded_cwd / session_id / "chat_history.jsonl")
        # Some CLI builds nest sessions flat under sessions/<id>/
        candidates.append(th / "sessions" / session_id / "chat_history.jsonl")
    real_home = Path(os.environ.get("GROK_HOME") or (Path.home() / ".grok"))
    # When Apex sets GROK_HOME to a temp dir, still probe the durable user home.
    candidates.append(Path.home() / ".grok" / "sessions" / encoded_cwd / session_id / "chat_history.jsonl")
    candidates.append(Path.home() / ".grok" / "sessions" / session_id / "chat_history.jsonl")
    if real_home.resolve() != (Path.home() / ".grok").resolve():
        candidates.append(real_home / "sessions" / encoded_cwd / session_id / "chat_history.jsonl")
    for p in candidates:
        try:
            if p.exists():
                return p
        except OSError:
            continue
    return None


def _load_grok_history_rows(hist_path: Path) -> list[dict]:
    """Parse chat_history.jsonl into a list of row dicts (skip bad lines)."""
    rows: list[dict] = []
    try:
        with hist_path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError as e:
        log(f"grok history parse error: {e}")
    return rows


def _slice_history_this_turn(rows: list[dict]) -> list[dict]:
    """Keep only rows after the last user message (current turn).

    Prevents stuffing every prior turn's tool_calls into the latest assistant
    message (was dumping 100+ events per Grok turn).
    """
    if not rows:
        return rows
    last_user = -1
    for i, row in enumerate(rows):
        if row.get("type") == "user":
            last_user = i
    if last_user < 0:
        return rows
    return rows[last_user + 1 :]


def _rows_to_tool_events(rows: list[dict]) -> list[dict]:
    """Convert history rows to interleaved tool_use / tool_result events."""
    events: list[dict] = []
    for row in rows:
        if row.get("type") == "assistant" and isinstance(row.get("tool_calls"), list):
            for call in row["tool_calls"]:
                if not isinstance(call, dict):
                    continue
                events.append({
                    "type": "tool_use",
                    "id": str(call.get("id") or uuid.uuid4()),
                    "name": call.get("name") or "tool",
                    "input": call.get("arguments") or "",
                })
        elif row.get("type") == "tool_result":
            content = row.get("content")
            if not isinstance(content, str):
                content = json.dumps(content) if content is not None else ""
            tid = str(row.get("tool_call_id") or uuid.uuid4())
            events.append({
                "type": "tool_result",
                "id": tid,
                "tool_use_id": tid,
                "content": content[:4000],
            })
    return events


def _extract_tool_events_from_events_jsonl(
    events_path: Path,
    *,
    this_turn_only: bool = True,
) -> list[dict]:
    """Fallback: build tool_use/result pairs from session events.jsonl.

    Grok emits tool_started / tool_completed with tool_name (no full args).
    Better than empty when chat_history is missing or incomplete.
    """
    if not events_path.exists():
        return []
    started: list[dict] = []
    completed: list[dict] = []
    try:
        with events_path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                t = row.get("type")
                if t == "turn_started" and this_turn_only:
                    # Reset — only keep tools from the latest turn.
                    started.clear()
                    completed.clear()
                elif t == "tool_started":
                    tid = str(row.get("tool_call_id") or row.get("id") or uuid.uuid4())
                    started.append({
                        "type": "tool_use",
                        "id": tid,
                        "name": row.get("tool_name") or "tool",
                        "input": row.get("input") or row.get("args") or "",
                    })
                elif t == "tool_completed":
                    tid = str(row.get("tool_call_id") or row.get("id") or "")
                    content = row.get("result") or row.get("output") or row.get("content") or ""
                    if not isinstance(content, str):
                        content = json.dumps(content)[:4000]
                    rid = tid or str(uuid.uuid4())
                    completed.append({
                        "type": "tool_result",
                        "id": rid,
                        "tool_use_id": rid,
                        "content": content[:4000],
                    })
    except OSError as e:
        log(f"grok events.jsonl parse error: {e}")
        return []
    # Interleave started then matching completed by id when possible
    by_id = {e["id"]: e for e in completed if e.get("id")}
    out: list[dict] = []
    for s in started:
        out.append(s)
        c = by_id.pop(s["id"], None)
        if c:
            out.append(c)
    for c in by_id.values():
        out.append(c)
    return out


def _extract_tool_events_from_history(
    hist_path: Path,
    *,
    this_turn_only: bool = True,
) -> list[dict]:
    """Read grok's chat_history.jsonl and reconstruct tool_use / tool_result
    events matching apex's stream event shape.

    Returns interleaved tool_use / tool_result events in chronological order.
    Each `assistant` row with `tool_calls` becomes N tool_use events. Each
    `tool_result` row becomes a tool_result event carrying the actual output.

    When ``this_turn_only`` (default), only rows after the last user message
    are included so multi-turn sessions don't re-attach prior tools.
    """
    rows = _load_grok_history_rows(hist_path)
    if this_turn_only:
        rows = _slice_history_this_turn(rows)
    events = _rows_to_tool_events(rows)
    if events:
        return events
    # Fallback: events.jsonl next to chat_history.jsonl
    events_path = hist_path.parent / "events.jsonl"
    return _extract_tool_events_from_events_jsonl(
        events_path, this_turn_only=this_turn_only
    )


def _collect_tool_events_from_history(
    session_id: str,
    cwd: str,
    already_recorded: list[dict],
    *,
    this_turn_only: bool = True,
    temp_grok_home: Path | None = None,
) -> int:
    """Read grok's session chat_history.jsonl and APPEND tool events into
    ``already_recorded`` so they persist in the message DB row and can be
    attached to the ``result`` WS payload for live UI hydration.

    Returns the number of new tool events added.

    Grok CLI 0.2.93 does not emit tool events on streaming-json stdout (bug
    filed with xAI 2026-07-09). We collect post-hoc from history, scope to
    this turn by default, and deliver via the ``result`` event (not mid-stream
    tool_use frames) so the thinking pill is finalized once with the correct
    duration before tools appear.
    """
    hist_path = _grok_session_history_path(
        session_id, cwd, temp_grok_home=temp_grok_home
    )
    all_events: list[dict] = []
    if hist_path is not None:
        all_events = _extract_tool_events_from_history(
            hist_path, this_turn_only=this_turn_only
        )
    else:
        # Last-ditch: rglob session id under durable sessions + temp home
        search_roots: list[Path] = [Path.home() / ".grok" / "sessions"]
        if temp_grok_home is not None:
            search_roots.insert(0, Path(temp_grok_home) / "sessions")
        found: Path | None = None
        for root in search_roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("chat_history.jsonl"):
                    if session_id in str(p):
                        found = p
                        break
            except OSError:
                continue
            if found:
                break
        if found:
            log(f"grok history rglob hit: {found}")
            all_events = _extract_tool_events_from_history(
                found, this_turn_only=this_turn_only
            )
        else:
            log(
                f"grok history missing: sid={session_id[:8]} cwd={cwd!r} "
                f"temp_home={temp_grok_home}"
            )
            return 0
    if not all_events:
        return 0
    seen_ids = {e.get("id") for e in already_recorded if e.get("type") == "tool_use"}
    added = 0
    for evt in all_events:
        if evt.get("type") == "tool_use" and evt.get("id") in seen_ids:
            continue
        already_recorded.append(evt)
        added += 1
    return added


async def _run_grok_chat(
    chat_id: str,
    prompt: str,
    model: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Run a chat response via the official Grok Build CLI (headless streaming-json).

    Mirrors Codex: session resume, context injection on fresh turns, tool events
    emitted when present. Grok CLI owns its own tools/sandbox/MCP.
    """
    effective_model = model or "grok-4.5"
    cli_model = effective_model  # ids already match CLI (grok-4.5, grok-4.3, …)
    grok_bin = _resolve_grok_cli()

    existing_session, session_turns, scope_key = _get_grok_session_state(chat_id)

    is_rotation = False
    if existing_session and session_turns >= _GROK_MAX_SESSION_TURNS:
        log(
            f"grok session rotation: session={scope_key[:24]} "
            f"sid={existing_session[:8]} turns={session_turns}/{_GROK_MAX_SESSION_TURNS}"
        )
        _grok_sessions.pop(scope_key, None)
        _grok_session_turns.pop(scope_key, None)
        _clear_persisted_grok_session(chat_id)
        is_rotation = True
        existing_session = ""

    workspace = _resolve_grok_workspace(chat_id)

    if existing_session:
        # Resume — CLI holds history; inject only identity anchor for group chats.
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
        log(
            f"grok resume: session={scope_key[:24]} sid={existing_session[:8]} "
            f"(identity anchor={'yes' if _anchor_name else 'no'})"
        )
        cmd = [
            grok_bin,
            "-r", existing_session,
            "-p", full_prompt,
            "--output-format", "streaming-json",
            "--always-approve",
            "--permission-mode", "bypassPermissions",
            "--no-plan",
            "-m", cli_model,
            "--cwd", workspace,
            "--max-turns", "30",
        ]
    else:
        profile_prompt = _get_profile_prompt(chat_id)
        group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=prompt)
        memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=prompt)
        workspace_ctx = _get_workspace_context(chat_id)
        temporal_ctx = _get_temporal_context(chat_id)
        context_energy = _get_context_energy_prompt(chat_id)
        calibration = _get_calibration_primer(chat_id)
        ctx_prefix = (
            f"{profile_prompt}{group_roster_prompt}{memory_prompt}"
            f"{workspace_ctx}{temporal_ctx}{context_energy}{calibration}"
        )
        full_prompt = f"{ctx_prefix}{prompt}" if ctx_prefix else prompt

        # Speaker-aware recent history for fresh/rotated sessions
        recent = _get_messages(chat_id, days=1)["messages"]
        current_pid = _current_group_profile_id.get("")
        fetch_window = max(_GROK_MAX_SESSION_TURNS + 4, 12)
        all_recent = [m for m in recent[-fetch_window:] if "<system-reminder>" not in m["content"]]

        def _is_self(m: dict) -> bool:
            if m["role"] != "assistant":
                return False
            sid = m.get("speaker_id", "")
            if current_pid:
                return sid == current_pid
            return True

        history_lines: list[str] = []
        ordered = all_recent[-_GROK_MAX_SESSION_TURNS:]
        for m in ordered:
            role = m["role"]
            content = m["content"]
            speaker_id = m.get("speaker_id", "")
            if _is_self(m):
                label = "You"
            elif role == "assistant" and speaker_id:
                label = m.get("speaker_name", speaker_id)
            else:
                label = role
            line = f"[{label}] {content[:3000]}"
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
            else:
                context_note = ""
            full_prompt = (
                f"<conversation-history>\n{history_block}\n</conversation-history>\n"
                f"{context_note}\n{full_prompt}"
            )

        journal_ctx = _build_journal_recovery_context(chat_id)
        if journal_ctx:
            full_prompt = f"{journal_ctx}{full_prompt}"
            log(f"grok journal recovery injected: chat={chat_id[:8]}")

        cmd = [
            grok_bin,
            "-p", full_prompt,
            "--output-format", "streaming-json",
            "--always-approve",
            "--permission-mode", "bypassPermissions",
            "--no-plan",
            "-m", cli_model,
            "--cwd", workspace,
            "--max-turns", "30",
            "--no-memory",  # Apex owns memory injection
        ]

    grok_env = {**os.environ}
    # Prefer SuperGrok / OIDC subscription via ~/.grok/auth.json — do NOT inject
    # XAI_API_KEY into the CLI env. Pay-per-token API keys bill differently and
    # confuse operators who want subscription-only usage. Pre-flight refresh is
    # `_refresh_grok_token_if_needed()` below; keep tokens warm with
    # apex-private/scripts/refresh_grok_oauth.py (cron every 4h).
    grok_env.pop("XAI_API_KEY", None)
    # Ensure CLI bin dirs are on PATH for child tool processes
    extra_path = f"{Path.home() / '.local' / 'bin'}:{Path.home() / '.grok' / 'bin'}"
    grok_env["PATH"] = f"{extra_path}:{grok_env.get('PATH', '')}"

    # PR1c — resolve Apex MCP for this turn and project a temp GROK_HOME
    # so Grok gets Apex's fetch/playwright/memory/tradingview/claim_store etc.
    # Also adds --deny MCPTool(filesystem__write_file) etc. per PR0 wire names.
    # Cleanup is in the finally block below; safe against exceptions and the
    # resume-failure retry (retry gets a fresh temp_home on its own call).
    _cu_target: str | None = None
    _int_enabled = False
    _profile_id_pr1c = ""
    _perm_level = 2  # default level if lookup fails
    try:
        from db import _get_chat as _chat_lookup
        _chat_row_pr1c = _chat_lookup(chat_id) if chat_id else None
        if _chat_row_pr1c:
            _cu_target = _chat_row_pr1c.get("computer_use_target") or None
            _int_enabled = bool(_chat_row_pr1c.get("interceptor_enabled"))
            _profile_id_pr1c = str(_chat_row_pr1c.get("profile_id") or "")
    except Exception as _e_pr1c:
        log(f"grok pr1c chat lookup: {_e_pr1c}")
    # Prefer active group speaker over chat's default profile — matches Claude
    # SDK path's client_key resolution.
    _group_pid = _current_group_profile_id.get("")
    if _group_pid:
        _profile_id_pr1c = _group_pid
    # Resolve permission level via the same path Claude uses
    # (_resolve_effective_tool_policy pattern) — chat's tool_policy is
    # authoritative; profile overrides for group speakers.
    try:
        if _profile_id_pr1c:
            _policy = _get_profile_tool_policy(_profile_id_pr1c) or {}
        else:
            _policy = _get_chat_tool_policy(chat_id) if chat_id else {}
        _perm_level = int(_policy.get("level", 2))
    except Exception as _e_pol:
        log(f"grok policy lookup: {_e_pol}")
    _grok_extras = resolve_profile_extra_tools(_profile_id_pr1c or None) if _profile_id_pr1c else None
    # PR2: CLI default pack is core (filesystem/fetch/memory). Full pack
    # is Claude/tool_loop; do not silently attach F-tier MCPs on Grok.
    _grok_pack = "core"
    _resolved_mcp = tool_surface.resolve_for_grok(
        chat_id,
        workspace=workspace,
        permission_level=_perm_level,
        computer_use_target=_cu_target,
        interceptor_enabled=_int_enabled,
        extra_allowed_tools=_grok_extras,
        pack=_grok_pack,
    )

    # Hard-deny grok CLI built-in categories per level (Bash/Edit/Write at
    # L0-L2, WebFetch at L0). Matches Claude L2 semantics so switching a chat
    # between backends gives the same effective capability. Uses --deny with
    # rule syntax (Bash, Edit, Write) — verified 2026-07-09 that
    # --disallowed-tools does NOT gate builtins in headless mode.
    _grok_builtin_denies = tool_surface.grok_deny_rules_for_level(_perm_level)
    for _rule in _grok_builtin_denies:
        cmd.extend(["--deny", _rule])
    if _grok_builtin_denies:
        log(f"grok builtin denies at level={_perm_level}: {_grok_builtin_denies}")

    # PR1b: fine-deny filesystem MCP write tools at L1 (server admitted, writes
    # blocked). At L2+ writes are allowed; at L0 filesystem itself isn't admitted.
    _grok_mcp_denies = tool_surface.grok_mcp_deny_rules_for_level(_perm_level)
    for _rule in _grok_mcp_denies:
        cmd.extend(["--deny", _rule])
    if _grok_mcp_denies:
        log(f"grok MCP denies at level={_perm_level}: {_grok_mcp_denies}")
    _temp_grok_home: Path | None = None
    _deny_count = len(_grok_builtin_denies) + len(_grok_mcp_denies)
    if _resolved_mcp:
        try:
            _temp_grok_home, _env_ovr, _deny_args = tool_surface.project_grok(_resolved_mcp)
            grok_env.update(_env_ovr)
            cmd.extend(_deny_args)
            _deny_count += len(_deny_args) // 2
            log(
                f"grok MCP: mcp={len(_resolved_mcp)} pack={_grok_pack} "
                f"home=tmp/{_temp_grok_home.name} denies={_deny_count}"
            )
            # Log residual project-scoped MCP sources — Grok CLI still merges
            # project .mcp.json / .grok/config.toml even with our compat kill
            # switches (per PR0 §2). Operators need visibility.
            try:
                _residual = tool_surface.detect_project_mcp_sources(workspace)
                if _residual:
                    log(f"grok residual project MCP sources under cwd: {_residual}")
            except Exception:
                pass
        except Exception as _e_proj:
            log(f"grok project_grok failed, falling back to native CLI tools: {_e_proj}")
            _temp_grok_home = None

    log(
        f"grok spawn: bin={grok_bin} model={cli_model} resume={bool(existing_session)} "
        f"cwd={workspace} level={_perm_level} pack={_grok_pack} "
        f"mcp={len(_resolved_mcp)} denies={_deny_count} "
        f"home={'tmp' if _temp_grok_home else 'real'}"
    )

    # Pre-flight: refresh OAuth token if expired to avoid device-code popup.
    _refresh_grok_token_if_needed()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=grok_env,
        cwd=workspace,
    )
    _started = time.monotonic()

    result_text = ""
    thinking_text = ""
    tool_events: list[dict] = []
    session_id = existing_session or ""
    tokens_in = 0
    tokens_out = 0
    error_msg = ""

    # Idempotent cleanup closure invoked at every exit path AND from bare
    # except guards below, so we always release temp GROK_HOME even when the
    # parse loop or proc.wait raises (WS disconnect, cancel).
    _cleanup_done = False

    def _do_cleanup() -> None:
        nonlocal _cleanup_done
        if _cleanup_done:
            return
        _cleanup_done = True
        tool_surface.cleanup_projected_home(_temp_grok_home)

    assert proc.stdout is not None
    _parse_interrupted: BaseException | None = None
    while True:
        try:
            line = await proc.stdout.readline()
        except BaseException as _e_read:
            _parse_interrupted = _e_read
            log(f"grok parse loop interrupted: {type(_e_read).__name__}")
            break
        if not line:
            break
        line_str = line.decode(errors="replace").strip()
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            # Non-JSON noise — ignore
            continue

        et = event.get("type", "")

        if et == "thought":
            chunk = event.get("data", "") or event.get("text", "") or ""
            if chunk:
                thinking_text += chunk
                await _send_stream_event(chat_id, {"type": "thinking", "text": chunk})

        elif et == "text":
            chunk = event.get("data", "") or event.get("text", "") or ""
            if chunk:
                result_text += chunk
                await _send_stream_event(chat_id, {"type": "text", "text": chunk})

        elif et in {"tool_use", "tool_call", "tool"}:
            tool_id = str(event.get("id") or event.get("tool_use_id") or uuid.uuid4())
            name = event.get("name") or event.get("tool") or "tool"
            inp = event.get("input") or event.get("arguments") or event.get("data") or ""
            if not isinstance(inp, str):
                try:
                    inp = json.dumps(inp)[:2000]
                except Exception:
                    inp = str(inp)[:2000]
            tool_evt = {"type": "tool_use", "id": tool_id, "name": name, "input": inp}
            tool_events.append(tool_evt)
            await _send_stream_event(chat_id, tool_evt)

        elif et in {"tool_result", "tool_response"}:
            tool_id = str(event.get("id") or event.get("tool_use_id") or uuid.uuid4())
            content = event.get("content") or event.get("data") or event.get("output") or ""
            if not isinstance(content, str):
                try:
                    content = json.dumps(content)[:2000]
                except Exception:
                    content = str(content)[:2000]
            tool_evt = {
                "type": "tool_result",
                "id": tool_id,
                "tool_use_id": tool_id,
                "content": content[:2000],
            }
            tool_events.append(tool_evt)
            await _send_stream_event(chat_id, tool_evt)

        elif et == "error":
            error_msg = str(event.get("message") or event.get("data") or "grok error")
            await _send_stream_event(
                chat_id,
                {"type": "error", "message": _public_grok_error_message(error_msg), "retryable": True},
            )

        elif et == "end":
            sid = event.get("sessionId") or event.get("session_id") or ""
            if sid:
                session_id = sid
            usage = event.get("usage") or {}
            tokens_in = int(usage.get("input_tokens") or usage.get("prompt_tokens") or tokens_in or 0)
            tokens_out = int(usage.get("output_tokens") or usage.get("completion_tokens") or tokens_out or 0)

        elif et == "usage":
            tokens_in = int(event.get("input_tokens") or event.get("prompt_tokens") or tokens_in or 0)
            tokens_out = int(event.get("output_tokens") or event.get("completion_tokens") or tokens_out or 0)

        elif et == "start":
            sid = event.get("sessionId") or event.get("session_id") or ""
            if sid:
                session_id = sid

    try:
        await proc.wait()
    except BaseException as _e_wait:
        # await proc.wait() got cancelled (WS disconnect / task cancel).
        # Guarantee cleanup then re-raise so callers see the original exception.
        log(f"grok wait interrupted, running cleanup: {type(_e_wait).__name__}")
        with contextlib.suppress(BaseException):
            proc.kill()
        _do_cleanup()
        raise
    # If the parse loop was interrupted mid-stream (WS closed / task cancel),
    # kill the subprocess so it doesn't linger, run cleanup, and re-raise the
    # original interrupt for the caller.
    if _parse_interrupted is not None:
        with contextlib.suppress(BaseException):
            proc.kill()
        _do_cleanup()
        raise _parse_interrupted
    stderr_data = await proc.stderr.read() if proc.stderr else b""
    if proc.returncode not in (0, None) and not result_text:
        err_msg = error_msg or (
            stderr_data.decode(errors="replace")[:500]
            if stderr_data
            else f"grok exited with code {proc.returncode}"
        )
        log(f"grok process error: {err_msg}")

        # Resume failure → clear session and retry fresh once
        if existing_session:
            log(
                f"grok resume failed, retrying fresh: session={scope_key[:24]} "
                f"sid={existing_session[:8]}"
            )
            _grok_sessions.pop(scope_key, None)
            _grok_session_turns.pop(scope_key, None)
            _clear_persisted_grok_session(chat_id)
            # PR1c — clean up THIS attempt's temp home before recursing.
            # The recursive call will project its own fresh temp home.
            _do_cleanup()
            _temp_grok_home = None
            return await _run_grok_chat(chat_id, prompt, model=model, attachments=attachments)

        await _send_stream_event(
            chat_id,
            {
                "type": "error",
                "message": _public_grok_error_message(err_msg),
                "retryable": True,
            },
        )
        _do_cleanup()
        return {
            "text": "",
            "is_error": True,
            "error": err_msg,
            "cost_usd": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "session_id": None,
            "thinking": thinking_text,
            "tool_events": json.dumps(tool_events),
            "duration_ms": int((time.monotonic() - _started) * 1000),
        }

    if session_id:
        _grok_sessions[scope_key] = session_id
        _grok_session_turns[scope_key] = _grok_session_turns.get(scope_key, 0) + 1
        turns = _grok_session_turns[scope_key]
        _persist_grok_session(chat_id, session_id, turns)
        log(
            f"grok turn complete: session={scope_key[:24]} sid={session_id[:8]} "
            f"turn={turns}/{_GROK_MAX_SESSION_TURNS} chars={len(result_text)}"
        )

    # Collect this-turn tool events from chat_history.jsonl (CLI omits them on
    # streaming-json stdout). Attach to result payload for live UI hydrate +
    # DB persistence — do NOT emit mid-stream tool_use frames (that broke
    # thinking-pill duration). Frontend hydrates on the single `result` event.
    if session_id:
        try:
            _added = _collect_tool_events_from_history(
                session_id,
                workspace,
                tool_events,
                this_turn_only=True,
                temp_grok_home=_temp_grok_home,
            )
            if _added:
                log(f"grok tool_events collected from history: {_added} events")
        except Exception as _e:
            log(f"grok history-collect failed: {_e}")

    _duration_ms = int((time.monotonic() - _started) * 1000)
    _tool_events_json = json.dumps(tool_events)
    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    _est = tokens_in or _estimate_tokens(chat_id)
    await _send_stream_event(
        chat_id,
        {
            "type": "result",
            "is_error": False,
            "cost_usd": 0,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "session_id": session_id or None,
            "context_tokens_in": _est,
            "context_window": _cw,
            "thinking": thinking_text,
            "duration_ms": _duration_ms,
            # Live hydrate: chat_js result handler applies these before
            # finalizing the thinking pill so tools appear without refresh.
            "tool_events": _tool_events_json,
        },
    )
    _do_cleanup()
    return {
        "text": result_text,
        "is_error": False,
        "error": None,
        "cost_usd": 0,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "session_id": session_id or None,
        "thinking": thinking_text,
        "tool_events": _tool_events_json,
        "duration_ms": _duration_ms,
    }


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
    # Persona-scoped extras (guide config tools, v3-gate claim-store tools).
    # Must be resolved BEFORE allowed_tool_names_for_level so Level 1 personas
    # keyed on a gate-test profile can actually see claim_store__* in the
    # filtered schema set. In group chats, current_pid is the speaking persona;
    # in 1:1 chats current_pid is empty, so fall back to chat.profile_id.
    _extras_pid = current_pid or ""
    if not _extras_pid:
        try:
            _chat_row = _get_chat(chat_id)
            if _chat_row:
                _extras_pid = str(_chat_row.get("profile_id", "") or "")
        except Exception:
            _extras_pid = ""
    extra_allowed_tools = resolve_profile_extra_tools(_extras_pid or None)
    allowed_local_tools = allowed_tool_names_for_level(
        permission_level,
        extra_allowed_tools=extra_allowed_tools,
    )
    if _TOOL_LOOP_AVAILABLE:
        sys_prompt = build_system_prompt(effective_model, permission_level=permission_level, allowed_tool_names=allowed_local_tools)
    else:
        sys_prompt = f"You are {effective_model}, a local AI model running via Ollama. Be helpful and concise."

    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=prompt)
    memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=prompt)
    workspace_ctx = _get_workspace_context(chat_id)
    temporal_ctx = _get_temporal_context(chat_id)
    context_energy = _get_context_energy_prompt(chat_id)
    calibration = _get_calibration_primer(chat_id)
    if profile_prompt or group_roster_prompt or memory_prompt or workspace_ctx or temporal_ctx or context_energy or calibration:
        sys_prompt = f"{sys_prompt}\n\n{profile_prompt}{group_roster_prompt}{memory_prompt}{workspace_ctx}{temporal_ctx}{context_energy}{calibration}"

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
                extra_allowed_tools=extra_allowed_tools,
            )
        elif backend == "deepseek":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                api_key=DEEPSEEK_API_KEY,
                api_url="https://api.deepseek.com",
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
                extra_allowed_tools=extra_allowed_tools,
            )
        elif backend == "zhipu":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                api_key=ZHIPU_API_KEY,
                api_url="https://api.z.ai/api/paas/v4",
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
                extra_allowed_tools=extra_allowed_tools,
            )
        elif backend == "google":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=runtime_workspace_paths,
                api_key=GOOGLE_API_KEY,
                api_url="https://generativelanguage.googleapis.com/v1beta/openai",
                max_iterations=MAX_TOOL_ITERATIONS,
                permission_level=permission_level,
                allowed_tools=allowed_local_tools,
                allowed_commands=allowed_commands,
                audit_context=audit_context,
                extra_allowed_tools=extra_allowed_tools,
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
                    extra_allowed_tools=extra_allowed_tools,
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
                    extra_allowed_tools=extra_allowed_tools,
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
                extra_allowed_tools=extra_allowed_tools,
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
                extra_allowed_tools=extra_allowed_tools,
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
