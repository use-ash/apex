"""Skill dispatch — server-side /recall, /codex, /grok, /claude routing.

Parses skill commands, runs direct skills (codex, grok, approve/reject),
context skills (recall, improve), and thinking skills (first-principles).
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path

import env
from db import _save_message
from log import log
from state import _current_stream_id

WORKSPACE = env.WORKSPACE

# ---------------------------------------------------------------------------
# Metrics collection — Phase 1 of gated skill loop
# ---------------------------------------------------------------------------
sys.path.insert(0, str(WORKSPACE))
try:
    from skills.lib.metrics import log_invocation as _log_skill_invocation
    _METRICS_ENABLED = True
except ImportError:
    _METRICS_ENABLED = False
    def _log_skill_invocation(*a, **kw): pass  # noqa: E704

# Gate — Phase 2 of gated skill loop
try:
    from skills.lib.gate import (
        get_pending_approvals as _get_pending_approvals,
        resolve_approval as _resolve_approval,
    )
    _GATE_ENABLED = True
except ImportError:
    _GATE_ENABLED = False
    def _get_pending_approvals(): return []  # noqa: E704
    def _resolve_approval(*a, **kw): return None  # noqa: E704


# ---------------------------------------------------------------------------
# Skill command parsing
# ---------------------------------------------------------------------------

def _parse_skill_command(prompt: str) -> tuple[str, str] | None:
    """Parse /skill-name args from prompt. Returns (skill, args) or None."""
    m = re.match(r"^/([\w-]+)\s*(.*)", prompt.strip(), re.DOTALL)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()


# ---------------------------------------------------------------------------
# Recall search
# ---------------------------------------------------------------------------

_RECALL_STOP_WORDS = frozenset(
    "a about all also am an and any are as at be been being but by can could"
    " did do does don doing done each for from get got had has have having he"
    " her here him his how i if in into is it its just know let like me might"
    " mine more my no not now of on one or our out over own please re really"
    " remember say she so some still tell than that the their them then there"
    " these they this those to up us very want was we were what when where"
    " which who will with would you your gonna gotta wanna".split()
)


def _extract_recall_terms(raw: str) -> str:
    """Strip stop words and punctuation to get meaningful search terms."""
    words = re.findall(r"[a-zA-Z0-9$%]+", raw.lower())
    meaningful = [w for w in words if w not in _RECALL_STOP_WORDS and len(w) > 1]
    return " ".join(meaningful) if meaningful else raw


def _run_recall(args: str) -> str:
    """Run hybrid search: keyword (fast, exact) + semantic (Gemini embeddings)."""
    if not args:
        return "Usage: /recall <search query>"
    t0 = time.monotonic()
    parts: list[str] = []

    query = _extract_recall_terms(args)
    script = WORKSPACE / "skills" / "recall" / "search_transcripts.py"
    keyword_output = ""
    if script.exists():
        log(f"Recall keyword search: {query!r}")
        try:
            result = subprocess.run(
                [sys.executable, str(script), query, "--top", "5", "--context", "800"],
                capture_output=True, text=True, timeout=15, cwd=str(WORKSPACE),
            )
            if result.returncode == 0 and result.stdout.strip() and "No results" not in result.stdout:
                keyword_output = result.stdout.strip()
        except Exception:
            pass

    semantic_output = ""
    try:
        embed_path = str(WORKSPACE / "skills" / "embedding")
        if embed_path not in sys.path:
            sys.path.insert(0, embed_path)
        import importlib
        _ms = importlib.import_module("memory_search")
        log(f"Recall semantic search: {args[:60]!r}")
        results = _ms.search(args, top_k=5)
        if results:
            lines = []
            for i, r in enumerate(results, 1):
                source_tag = r.get("source", "?")
                score = r.get("score", 0)
                fname = Path(r["file"]).name
                preview = r.get("content", "")[:600]
                lines.append(f"[{i}] Score: {score:.3f} | {source_tag} | {fname}\n{'='*60}\n{preview}\n")
            semantic_output = "\n".join(lines)
    except Exception as e:
        log(f"Recall semantic search error: {e}")

    elapsed = time.monotonic() - t0
    if semantic_output:
        parts.append(f"## Semantic Search Results (Gemini Embedding)\n\n{semantic_output}")
    if keyword_output:
        parts.append(f"## Keyword Search Results\n\n{keyword_output}")

    if parts:
        _log_skill_invocation("recall", success=True, duration_sec=elapsed, context=query[:80], source="apex")
        return "\n\n".join(parts)

    _log_skill_invocation("recall", success=False, duration_sec=elapsed, context=query[:80], source="apex")
    return f"No results found for: {args}"


# ---------------------------------------------------------------------------
# Skill-improver
# ---------------------------------------------------------------------------

def _run_improve(args: str) -> str:
    """Run skill-improver analysis. Returns structured JSON report for Claude synthesis."""
    if not args:
        return "Usage: /improve <skill_name> — Analyze a skill's metrics and propose improvements"
    skill_name = args.split()[0].strip().lower()
    skill_dir = WORKSPACE / "skills" / skill_name
    if not skill_dir.exists():
        available = sorted(
            d.name for d in (WORKSPACE / "skills").iterdir()
            if d.is_dir() and (d / "SKILL.md").exists() and d.name != "lib"
        )
        return f"Skill '{skill_name}' not found. Available: {', '.join(available)}"

    analyze_script = WORKSPACE / "skills" / "skill-improver" / "analyze.py"
    if not analyze_script.exists():
        return "Skill-improver not installed. Expected: skills/skill-improver/analyze.py"

    log(f"Skill-improver: analyzing '{skill_name}'")
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(analyze_script), skill_name,
             "--workspace", str(WORKSPACE), "--days", "30"],
            capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE),
        )
        elapsed = time.monotonic() - t0
        output = result.stdout.strip()
        if result.returncode != 0:
            _log_skill_invocation("skill-improver", success=False, duration_sec=elapsed,
                                  error=result.stderr.strip()[:200], context=skill_name, source="apex")
            return f"Analysis error: {result.stderr.strip()}"
        _log_skill_invocation("skill-improver", success=True, duration_sec=elapsed,
                              context=skill_name, source="apex")
        return output
    except subprocess.TimeoutExpired:
        _log_skill_invocation("skill-improver", success=False, duration_sec=30.0,
                              error="timeout", context=skill_name, source="apex")
        return "Skill analysis timed out."
    except Exception as e:
        _log_skill_invocation("skill-improver", success=False,
                              duration_sec=time.monotonic() - t0, error=str(e)[:200],
                              context=skill_name, source="apex")
        return f"Analysis error: {e}"


# ---------------------------------------------------------------------------
# Codex background
# ---------------------------------------------------------------------------

def _run_codex_background(args: str, chat_id: str) -> str:
    """Launch codex as a background task. Returns status message."""
    if not args:
        return "Usage: /codex <prompt for codex>"
    prompt_file = WORKSPACE / f"codex_apex_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"codex_apex_{chat_id[:8]}_response.md"
    prompt_file.write_text(args)
    script = WORKSPACE / "skills" / "codex" / "run_codex.sh"
    if not script.exists():
        return "Codex skill not found."
    try:
        subprocess.Popen(
            ["bash", str(script), str(prompt_file.relative_to(WORKSPACE)),
             str(response_file.relative_to(WORKSPACE)), "", "--network"],
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _log_skill_invocation("codex", success=True, context=args[:80], source="apex")
        return f"Codex task launched in background.\nPrompt: `{prompt_file.name}`\nResponse will be at: `{response_file.name}`\n\nI'll check the response when it's ready. You can also ask me to check with: \"check codex response\""
    except Exception as e:
        _log_skill_invocation("codex", success=False, error=str(e)[:200], context=args[:80], source="apex")
        return f"Codex launch error: {e}"


# ---------------------------------------------------------------------------
# Grok research
# ---------------------------------------------------------------------------

def _run_grok(args: str, chat_id: str) -> str | dict:
    """Launch grok research. Returns status message (or dict with bg process info)."""
    if not args:
        return "Usage: /grok <research question> [--bookmarks [N]] [--search] [--research] [--thinking LEVEL]"

    import shlex
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()

    extra_flags: list[str] = []
    prompt_tokens: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--bookmarks":
            extra_flags.append("--bookmarks")
            if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                i += 1
                extra_flags.append(tokens[i])
        elif tok == "--search":
            extra_flags.append("--search")
        elif tok == "--research":
            extra_flags.append("--research")
        elif tok == "--thinking" and i + 1 < len(tokens):
            extra_flags.append("--thinking")
            i += 1
            extra_flags.append(tokens[i])
        else:
            prompt_tokens.append(tok)
        i += 1

    prompt_text = " ".join(prompt_tokens)
    if not prompt_text:
        return "Usage: /grok <research question> [--bookmarks [N]] [--search] [--research] [--thinking LEVEL]"

    prompt_file = WORKSPACE / f"grok_apex_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"grok_apex_{chat_id[:8]}_response.md"
    if response_file.exists():
        response_file.unlink()
    prompt_file.write_text(prompt_text)
    script = WORKSPACE / "skills" / "grok" / "run_grok.sh"
    if not script.exists():
        return "Grok skill not found."
    try:
        cmd = ["bash", str(script), str(prompt_file.relative_to(WORKSPACE)),
               str(response_file.relative_to(WORKSPACE))] + extra_flags
        proc = subprocess.Popen(
            cmd,
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        flags_str = f" ({' '.join(extra_flags)})" if extra_flags else ""
        _log_skill_invocation("grok", success=True, context=args[:80], source="apex")
        return {
            "status": f"Grok research launched in background{flags_str}...",
            "bg_proc": proc,
            "bg_response_file": str(response_file),
        }
    except Exception as e:
        _log_skill_invocation("grok", success=False, error=str(e)[:200], context=args[:80], source="apex")
        return f"Grok launch error: {e}"


# ---------------------------------------------------------------------------
# Gate approval / rejection
# ---------------------------------------------------------------------------

def _run_approve(args: str, chat_id: str = "") -> str:
    """Approve a pending skill gate."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    approval_id = args.strip() if args.strip() else None
    if not approval_id:
        if len(pending) == 1:
            approval_id = str(pending[0].get("message_id", ""))
        else:
            lines = ["Multiple pending approvals. Specify an ID:\n"]
            for p in pending:
                mid = p.get("message_id", "?")
                skill = p.get("skill", "?")
                ts = p.get("ts", "?")[:16]
                reasons = ", ".join(p.get("reasons", [])[:2])
                lines.append(f"  /approve {mid} — {skill} ({reasons}) [{ts}]")
            return "\n".join(lines)
    result = _resolve_approval(approval_id, "approved")
    if result:
        _log_skill_invocation("gate", success=True, context=f"approved:{result.get('skill','?')}", source="apex")
        return f"✅ Approved: {result.get('skill', '?')}"
    return f"Approval ID '{approval_id}' not found or already resolved."


def _run_reject(args: str, chat_id: str = "") -> str:
    """Reject a pending skill gate."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    approval_id = args.strip() if args.strip() else None
    if not approval_id:
        if len(pending) == 1:
            approval_id = str(pending[0].get("message_id", ""))
        else:
            lines = ["Multiple pending approvals. Specify an ID:\n"]
            for p in pending:
                mid = p.get("message_id", "?")
                skill = p.get("skill", "?")
                lines.append(f"  /reject {mid} — {skill}")
            return "\n".join(lines)
    result = _resolve_approval(approval_id, "rejected")
    if result:
        _log_skill_invocation("gate", success=True, context=f"rejected:{result.get('skill','?')}", source="apex")
        return f"❌ Rejected: {result.get('skill', '?')}"
    return f"Approval ID '{approval_id}' not found or already resolved."


def _run_pending(args: str, chat_id: str = "") -> str:
    """Show pending skill gate approvals."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    lines = [f"Pending approvals ({len(pending)}):\n"]
    for p in pending:
        mid = p.get("message_id", "?")
        skill = p.get("skill", "?")
        tier = p.get("tier", "?")
        ts = p.get("ts", "?")[:16]
        reasons = ", ".join(p.get("reasons", [])[:3])
        lines.append(f"  [{mid}] {skill} (tier {tier}) — {reasons}")
        lines.append(f"         {ts}")
        lines.append(f"         /approve {mid}  |  /reject {mid}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skill registries
# ---------------------------------------------------------------------------

_DIRECT_SKILL_HANDLERS = {
    "codex": _run_codex_background,
    "grok": _run_grok,
    "approve": _run_approve,
    "reject": _run_reject,
    "pending": _run_pending,
}

_CONTEXT_SKILLS = {"recall", "improve"}
_THINKING_SKILLS = {"first-principles", "simplify"}


def _find_skill_md(skill: str) -> Path | None:
    """Return the SKILL.md path for a discovered skill, if present."""
    skill_name = str(skill or "").strip().lower()
    if not skill_name:
        return None
    for skill_md in env.iter_workspace_skill_files(env.get_runtime_workspace_paths_list()):
        if skill_md.parent.name.lower() == skill_name:
            return skill_md
    return None


def _load_thinking_skill_instructions(skill: str) -> str | None:
    """Load SKILL.md instructions for an explicit non-direct skill invocation."""
    skill_name = str(skill or "").strip().lower()
    if not skill_name or skill_name in _CONTEXT_SKILLS or skill_name in _DIRECT_SKILL_HANDLERS:
        return None
    skill_md = _find_skill_md(skill_name)
    if not skill_md or not skill_md.exists():
        return None
    return skill_md.read_text()[:4000]


# ---------------------------------------------------------------------------
# Background skill watcher
# ---------------------------------------------------------------------------

async def _watch_bg_skill(proc, response_file: str, chat_id: str, skill_name: str):
    """Watch a background skill process and push the result into the chat when done."""
    # Lazy imports to avoid circular dependency
    from streaming import (
        _make_stream_id, _send_stream_event,
    )

    try:
        exit_code = await asyncio.to_thread(proc.wait, 300)
        rpath = Path(response_file)
        if rpath.exists():
            content = rpath.read_text().strip()
            if content:
                label = f"**{skill_name.capitalize()} response:**\n\n{content}"
            else:
                label = f"⚠️ {skill_name.capitalize()} returned empty response."
        else:
            label = f"⚠️ {skill_name.capitalize()} response file not found (exit code {exit_code})."
    except subprocess.TimeoutExpired:
        label = f"⚠️ {skill_name.capitalize()} timed out after 5 minutes."
        proc.kill()
    except Exception as e:
        label = f"⚠️ {skill_name.capitalize()} watcher error: {e}"

    stream_token = _current_stream_id.set(_make_stream_id())
    try:
        _save_message(chat_id, "assistant", label, cost_usd=0, tokens_in=0, tokens_out=0)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})
        await _send_stream_event(chat_id, {"type": "text", "text": label})
        await _send_stream_event(chat_id, {
            "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        })
        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})
        log(f"BG skill complete: /{skill_name} chat={chat_id} len={len(label)}")
    finally:
        _current_stream_id.reset(stream_token)


# ---------------------------------------------------------------------------
# Skill handler (called from websocket)
# ---------------------------------------------------------------------------

async def _handle_skill(websocket, chat_id: str, skill: str, args: str, display_prompt: str) -> bool:
    """Handle a skill invocation. Returns True if handled, False to fall through to Claude."""
    from streaming import (
        _make_stream_id, _attach_ws, _reset_stream_buffer,
        _send_stream_event,
    )

    if skill in _CONTEXT_SKILLS:
        if skill == "recall":
            log(f"Skill dispatch: /recall (context mode) args={args[:80]!r} chat={chat_id}")
            recall_results = await asyncio.to_thread(_run_recall, args)
            if not recall_results or "No results" in recall_results:
                return False
            return False, recall_results  # type: ignore[return-value]
        return False

    handler = _DIRECT_SKILL_HANDLERS.get(skill)
    if not handler:
        return False

    log(f"Skill dispatch: /{skill} (direct) args={args[:80]!r} chat={chat_id}")

    stream_token = _current_stream_id.set(_make_stream_id())
    try:
        _save_message(chat_id, "user", display_prompt)
        _attach_ws(websocket, chat_id)
        _reset_stream_buffer(chat_id)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})

        bg_info = None
        try:
            result = await asyncio.to_thread(handler, args, chat_id)
            if isinstance(result, dict) and "bg_proc" in result:
                bg_info = result
                result_text = result["status"]
            else:
                result_text = result
        except Exception as e:
            result_text = f"Skill error: {e}"

        await _send_stream_event(chat_id, {"type": "text", "text": result_text})
        _save_message(chat_id, "assistant", result_text, cost_usd=0, tokens_in=0, tokens_out=0)

        await _send_stream_event(chat_id, {
            "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        })
        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})

        if bg_info and "bg_proc" in bg_info:
            asyncio.create_task(_watch_bg_skill(
                bg_info["bg_proc"], bg_info["bg_response_file"],
                chat_id, skill
            ))

        return True
    finally:
        _current_stream_id.reset(stream_token)
