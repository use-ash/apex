"""Ollama tool-calling agent loop."""
import asyncio
import json
import logging
import re
import time
import urllib.request
import uuid
from typing import Callable, Awaitable

from env import ALLOW_LOCAL_TOOLS

from .registry import get_tool_schemas, get_executor, is_mcp_tool
from .guardrails import pre_check, filter_output

_pylog = logging.getLogger("apex.tool_loop")

# Use the Apex custom log function (writes to state/apex.log + stderr)
try:
    from log import log as _apex_log
except ImportError:
    _apex_log = None


class _ToolLoopLogger:
    """Wrapper that sends .info() calls to both Python logging and Apex log file."""
    def info(self, msg, *args):
        formatted = msg % args if args else msg
        _pylog.info(formatted)
        if _apex_log:
            _apex_log(formatted)

    def warning(self, msg, *args):
        formatted = msg % args if args else msg
        _pylog.warning(formatted)
        if _apex_log:
            _apex_log(f"WARN: {formatted}")

log = _ToolLoopLogger()

MAX_TOOL_ITERATIONS = 25
OLLAMA_TIMEOUT = 300  # 5 minutes per Ollama call
DEFAULT_NUM_CTX = 131072  # 128K context window

# ── Text-based tool calling for models without native support ──

# Cache: model_name -> bool (supports native tool calling)
_native_tool_support: dict[str, bool] = {}


def _check_native_tool_support(ollama_url: str, model: str) -> bool:
    """Check if model's Ollama template handles tools natively."""
    if model in _native_tool_support:
        return _native_tool_support[model]
    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/show",
            data=json.dumps({"name": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        template = data.get("template", "")
        supported = ".Tools" in template or "tools" in template.lower() and "tool_call" in template.lower()
        _native_tool_support[model] = supported
        if not supported:
            log.info("Model %s lacks native tool template — using text-based tool calling", model)
        return supported
    except Exception:
        # If we can't check, assume native support (don't break existing models)
        return True


def _build_tool_prompt(tool_schemas: list[dict]) -> str:
    """Build a text description of tools for the system prompt."""
    lines = [
        "\n## Available Tools",
        "You have access to the following tools. To call a tool, output a <tool_call> block with valid JSON:",
        "",
        "```",
        '<tool_call>{"name": "tool_name", "arguments": {"arg1": "value1"}}</tool_call>',
        "```",
        "",
        "You may call multiple tools by outputting multiple <tool_call> blocks.",
        "After each tool call, you will receive the result in a <tool_result> block.",
        "When you have the final answer, respond with plain text (no <tool_call> block).",
        "",
        "### Tool Definitions",
    ]
    for schema in tool_schemas:
        func = schema.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        params = func.get("parameters", {})
        props = params.get("properties", {})
        required = params.get("required", [])

        lines.append(f"\n**{name}**: {desc}")
        if props:
            lines.append("  Parameters:")
            for pname, pinfo in props.items():
                req_marker = " (required)" if pname in required else ""
                pdesc = pinfo.get("description", "")
                ptype = pinfo.get("type", "")
                lines.append(f"  - {pname} ({ptype}){req_marker}: {pdesc}")
    return "\n".join(lines)


def _inject_tool_prompt(messages: list[dict], tool_prompt: str) -> list[dict]:
    """Inject tool descriptions into the system message."""
    messages = [m.copy() for m in messages]
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            messages[i] = {**msg, "content": msg.get("content", "") + "\n" + tool_prompt}
            return messages
    # No system message — prepend one
    messages.insert(0, {"role": "system", "content": tool_prompt})
    return messages


_TOOL_RESULT_TAG_RE = re.compile(r"<tool_result>\s*.*?\s*</tool_result>", re.DOTALL)


def _strip_tool_result_tags(text: str) -> str:
    """Remove <tool_result>...</tool_result> echoes from model output."""
    return _TOOL_RESULT_TAG_RE.sub("", text).strip()


_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*", re.DOTALL)
_TOOL_CALL_END_RE = re.compile(r"\s*</tool_call>")


def _extract_json_object(text: str, start: int) -> tuple[str, int] | tuple[None, int]:
    """Extract a complete JSON object from text starting at `start`.

    Tries json.loads on successively larger substrings ending at each `}`
    to find the complete JSON object. Handles malformed JSON with raw
    control characters by preprocessing before parsing.
    Returns (json_string, end_pos) or (None, start) on failure.
    """
    if start >= len(text) or text[start] != "{":
        return None, start

    # Try parsing at each closing brace from right to left within
    # a reasonable window (scan for `}</tool_call>` pattern first)
    end_tag = "</tool_call>"
    tag_pos = text.find(end_tag, start)
    if tag_pos > start:
        # Try the substring up to the closing tag
        candidate = text[start:tag_pos].rstrip()
        fixed = _fix_json_control_chars(candidate)
        try:
            json.loads(fixed)
            return candidate, tag_pos
        except json.JSONDecodeError:
            pass

    # Fallback: try at each `}` from innermost to outermost
    pos = start
    last_brace = -1
    while True:
        last_brace = text.find("}", last_brace + 1 if last_brace >= 0 else start)
        if last_brace < 0 or last_brace > start + 50000:
            break
        candidate = text[start:last_brace + 1]
        fixed = _fix_json_control_chars(candidate)
        try:
            json.loads(fixed)
            return candidate, last_brace + 1
        except json.JSONDecodeError:
            continue

    return None, start


def _fix_json_control_chars(raw: str) -> str:
    """Escape raw control characters inside JSON string values.

    Models often output literal newlines/tabs inside JSON strings
    which is invalid JSON. This fixes them before parsing.
    """
    # Replace raw newlines/tabs that aren't already escaped
    result = []
    in_string = False
    j = 0
    while j < len(raw):
        c = raw[j]
        if c == '\\' and in_string:
            # Already escaped — keep both chars
            result.append(raw[j:j + 2])
            j += 2
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c == '\n':
            result.append('\\n')
        elif in_string and c == '\r':
            result.append('\\r')
        elif in_string and c == '\t':
            result.append('\\t')
        else:
            result.append(c)
        j += 1
    return "".join(result)


def _parse_text_tool_calls(text: str) -> tuple[str, list[dict]]:
    """Extract <tool_call> blocks from model text output.

    Returns (clean_text, tool_calls) where tool_calls is in
    Ollama-compatible format: [{"function": {"name": ..., "arguments": ...}}]
    """
    tool_calls = []
    clean_parts = []
    pos = 0

    while pos < len(text):
        match = _TOOL_CALL_TAG_RE.search(text, pos)
        if not match:
            clean_parts.append(text[pos:])
            break

        # Add text before the <tool_call> tag
        clean_parts.append(text[pos:match.start()])

        # Extract JSON object after the opening tag
        json_start = match.end()
        raw_json, json_end = _extract_json_object(text, json_start)

        if raw_json is None:
            # Failed to extract — keep the tag text as-is
            clean_parts.append(text[match.start():match.end()])
            pos = match.end()
            continue

        # Skip past the closing </tool_call> tag
        end_match = _TOOL_CALL_END_RE.match(text, json_end)
        pos = end_match.end() if end_match else json_end

        try:
            fixed = _fix_json_control_chars(raw_json)
            parsed = json.loads(fixed)
            tool_calls.append({
                "function": {
                    "name": parsed.get("name", "unknown"),
                    "arguments": parsed.get("arguments", {}),
                },
            })
        except json.JSONDecodeError:
            log.warning("Failed to parse tool call JSON: %s", raw_json[:200])
            continue

    clean = "".join(clean_parts).strip()
    return clean, tool_calls


def _call_ollama(ollama_url: str, model: str, messages: list, tools: list,
                  *, use_native_tools: bool = True) -> dict:
    """Synchronous Ollama API call (runs in thread)."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": DEFAULT_NUM_CTX},
    }
    if tools and use_native_tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    raw = resp.read().decode()
    return json.loads(raw)


def _call_openai_compat(api_url: str, model: str, messages: list, tools: list, api_key: str) -> dict:
    """OpenAI-compatible API call (xAI, OpenAI, etc). Runs in thread."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "tools": tools,
    }
    # GPT-5.x and o-series require max_completion_tokens instead of max_tokens
    if model.startswith("gpt-5") or model.startswith("o3") or model.startswith("o4"):
        payload["max_completion_tokens"] = 16384
    req = urllib.request.Request(
        f"{api_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Apex/1.0",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:500] if hasattr(e, 'read') else ""
        raise RuntimeError(f"API error: {e} body={error_body}") from e
    data = json.loads(resp.read().decode())
    # Normalize to Ollama-like format so the rest of the loop works unchanged
    choice = data.get("choices", [{}])[0]
    return {"message": choice.get("message", {})}


def _call_openai_responses(api_url: str, model: str, messages: list, tools: list, api_key: str) -> dict:
    """OpenAI Responses API — supports reasoning summaries for o-series models."""
    # Convert chat messages to Responses API input format
    input_items = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            input_items.append({"role": "developer", "content": content})
        elif role == "tool":
            # Tool results reference their tool_call_id
            input_items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": content,
            })
        elif role == "assistant" and msg.get("tool_calls"):
            # Re-emit tool calls as function_call items
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", "")
                if not isinstance(args, str):
                    args = json.dumps(args)
                input_items.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": args,
                })
            # Also include any text content
            if content:
                input_items.append({"role": "assistant", "content": content})
        else:
            input_items.append({"role": role, "content": content})

    # Convert tool schemas to Responses API format
    resp_tools = []
    for t in tools:
        func = t.get("function", {})
        resp_tools.append({
            "type": "function",
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {}),
        })

    payload: dict = {
        "model": model,
        "input": input_items,
        "tools": resp_tools,
        "reasoning": {"effort": "medium", "summary": "detailed"},
        "max_output_tokens": 16384,
    }
    req = urllib.request.Request(
        f"{api_url}/responses",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Apex/1.0",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:500] if hasattr(e, 'read') else ""
        raise RuntimeError(f"API error: {e} body={error_body}") from e
    data = json.loads(resp.read().decode())

    # Parse Responses API output into normalized format
    output_items = data.get("output", [])
    content = ""
    tool_calls = []
    reasoning_text = ""

    for item in output_items:
        itype = item.get("type", "")
        if itype == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    content += part.get("text", "")
        elif itype == "reasoning":
            for part in item.get("summary", []):
                if part.get("type") == "summary_text":
                    reasoning_text += part.get("text", "")
        elif itype == "function_call":
            tool_calls.append({
                "id": item.get("call_id", ""),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                },
            })

    # Normalize to same format as _call_openai_compat
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    result = {"message": msg}
    if reasoning_text:
        result["reasoning"] = reasoning_text
    return result


def _load_chatgpt_auth() -> tuple[str, str]:
    """Load OAuth tokens from Codex auth.json. Returns (access_token, account_id)."""
    import os
    auth_path = os.path.expanduser("~/.codex/auth.json")
    with open(auth_path) as f:
        auth = json.loads(f.read())
    tokens = auth.get("tokens", {})
    return tokens.get("access_token", ""), tokens.get("account_id", "")


def _refresh_chatgpt_token() -> str:
    """Refresh the ChatGPT OAuth access token using the refresh token. Returns new access_token."""
    import os
    auth_path = os.path.expanduser("~/.codex/auth.json")
    with open(auth_path) as f:
        auth = json.loads(f.read())
    refresh_token = auth["tokens"]["refresh_token"]
    client_id = "app_EMoamEEZ73f0CkXaXp7hrann"  # Codex desktop OAuth client ID

    payload = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }).encode()
    req = urllib.request.Request(
        "https://auth.openai.com/oauth/token",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=15)
    new_tokens = json.loads(resp.read())

    # Update auth.json with new tokens
    auth["tokens"]["access_token"] = new_tokens["access_token"]
    if "refresh_token" in new_tokens:
        auth["tokens"]["refresh_token"] = new_tokens["refresh_token"]
    if "id_token" in new_tokens:
        auth["tokens"]["id_token"] = new_tokens["id_token"]

    import datetime
    auth["last_refresh"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    import tempfile, shutil
    tmp = tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(auth_path), delete=False, suffix=".tmp")
    tmp.write(json.dumps(auth, indent=2))
    tmp.close()
    shutil.move(tmp.name, auth_path)
    from compat import safe_chmod
    safe_chmod(auth_path, 0o600)

    return new_tokens["access_token"]


def _call_chatgpt_backend(model: str, messages: list, tools: list,
                          _loop=None, _emit_fn=None) -> dict:
    """Call ChatGPT backend via Codex OAuth — uses subscription credits, not API billing.

    Wire protocol: OpenAI Responses API (SSE streaming) at chatgpt.com/backend-api/codex/responses.
    Auth: Bearer token + ChatGPT-Account-ID from ~/.codex/auth.json.
    """
    access_token, account_id = _load_chatgpt_auth()

    # Convert messages to Responses API input format
    input_items = []
    instructions = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            instructions = content  # ChatGPT backend requires 'instructions' field
        elif role == "tool":
            input_items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": content,
            })
        elif role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", "")
                if not isinstance(args, str):
                    args = json.dumps(args)
                input_items.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": args,
                })
            if content:
                input_items.append({"role": "assistant", "content": content})
        else:
            input_items.append({"role": role, "content": content})

    if not instructions:
        instructions = "You are a helpful assistant."

    # Convert tool schemas
    resp_tools = []
    for t in tools:
        func = t.get("function", {})
        resp_tools.append({
            "type": "function",
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {}),
        })

    payload_dict: dict = {
        "model": model,
        "instructions": instructions,
        "input": input_items,
        "stream": True,
        "store": False,
        "reasoning": {"effort": "high", "summary": "auto"},
    }
    if resp_tools:
        payload_dict["tools"] = resp_tools

    def _do_request(token: str) -> dict:
        payload = json.dumps(payload_dict).encode()
        req = urllib.request.Request(
            "https://chatgpt.com/backend-api/codex/responses?client_version=0.117.0",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "ChatGPT-Account-ID": account_id,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "Apex/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)

        # Capture rate limit headers from response
        rate_limits = {}
        for hdr in ("x-codex-primary-used-percent", "x-codex-secondary-used-percent",
                     "x-codex-primary-window-minutes", "x-codex-secondary-window-minutes",
                     "x-codex-primary-reset-at", "x-codex-secondary-reset-at",
                     "x-codex-plan-type", "x-codex-primary-reset-after-seconds",
                     "x-codex-secondary-reset-after-seconds"):
            val = resp.headers.get(hdr)
            if val is not None:
                rate_limits[hdr] = val

        # Write to shared cache file so Apex can serve it
        if rate_limits:
            import os, tempfile, shutil
            cache_path = os.path.expanduser("~/.codex/.usage_cache.json")
            try:
                import time as _t
                cache_data = {**rate_limits, "_ts": _t.time()}
                tmp = tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(cache_path),
                                                   delete=False, suffix=".tmp")
                tmp.write(json.dumps(cache_data))
                tmp.close()
                shutil.move(tmp.name, cache_path)
            except Exception:
                pass

        # Parse SSE stream
        content = ""
        tool_calls = []
        reasoning_text = ""

        for line in resp:
            line = line.decode().strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "response.output_text.delta":
                content += event.get("delta", "")
            elif etype == "response.reasoning_summary_text.delta":
                delta = event.get("delta", "")
                if delta:
                    reasoning_text += delta
                    # Emit delta in real-time via the outer async loop (we're in a thread)
                    if _loop is not None and _emit_fn is not None:
                        asyncio.run_coroutine_threadsafe(
                            _emit_fn({"type": "thinking", "text": delta}), _loop
                        )
            elif etype == "response.reasoning_summary_text.done":
                # Authoritative final text — use if delta events produced nothing
                done_text = event.get("text", "")
                if done_text and not reasoning_text:
                    reasoning_text = done_text
                    if _loop is not None and _emit_fn is not None:
                        asyncio.run_coroutine_threadsafe(
                            _emit_fn({"type": "thinking", "text": done_text}), _loop
                        )
                elif done_text:
                    reasoning_text = done_text  # ensure final value is authoritative
                    if _loop is not None and _emit_fn is not None:
                        asyncio.run_coroutine_threadsafe(
                            _emit_fn({"type": "thinking", "text": done_text}), _loop
                        )
            elif etype == "response.output_item.done":
                item = event.get("item", {})
                if item.get("type") == "reasoning":
                    # Fallback: reasoning content in output_item.done summary
                    for part in item.get("summary", []):
                        if part.get("type") == "summary_text" and not reasoning_text:
                            reasoning_text = part.get("text", "")
                            if _loop is not None and _emit_fn is not None:
                                asyncio.run_coroutine_threadsafe(
                                    _emit_fn({"type": "thinking", "text": reasoning_text}), _loop
                                )
                elif item.get("type") == "function_call":
                    call_id = item.get("call_id", item.get("id", ""))
                    tool_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", "{}"),
                        },
                    })

        # Normalize to same format as _call_openai_compat
        msg: dict = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        result = {"message": msg}
        if reasoning_text:
            result["reasoning"] = reasoning_text
            if _loop is not None and _emit_fn is not None:
                result["reasoning_streamed"] = True  # caller should not re-emit
        return result

    try:
        return _do_request(access_token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired — refresh and retry
            new_token = _refresh_chatgpt_token()
            return _do_request(new_token)
        error_body = e.read().decode()[:500] if hasattr(e, 'read') else ""
        raise RuntimeError(f"ChatGPT backend error: {e} body={error_body}") from e


def _build_result(text: str, tool_events: list, is_error: bool = False, error: str | None = None,
                   thinking: str = "", duration_ms: int = 0) -> dict:
    """Build result dict matching apex.py's expected format."""
    return {
        "text": text,
        "is_error": is_error,
        "error": error,
        "cost_usd": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "session_id": None,
        "thinking": thinking.strip(),
        "tool_events": json.dumps(tool_events),
        "duration_ms": duration_ms,
    }


async def run_tool_loop(
    ollama_url: str,
    model: str,
    messages: list[dict],
    emit_event: Callable[[dict], Awaitable[None]],
    workspace: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    max_iterations: int | None = None,
    permission_level: int = 2,
    allowed_tools: set[str] | None = None,
    allowed_commands: list[str] | None = None,
    audit_context: dict | None = None,
) -> dict:
    """
    Run the tool-calling agent loop (Ollama or OpenAI-compatible API).

    Sends messages + tool schemas to the model. If the model returns tool_calls,
    executes them, emits WebSocket events, and loops. Stops when the model
    returns a text-only response or max iterations are reached.

    Args:
        ollama_url: Ollama base URL (e.g. "http://localhost:11434")
        model: Model name (e.g. "qwen3.5:27b-fast" or "grok-3")
        messages: Conversation history
        emit_event: Async callback to emit WebSocket events
        workspace: Working directory for tool execution
        api_key: If set, use OpenAI-compatible endpoint instead of Ollama
        api_url: Base URL for OpenAI-compatible API (e.g. "https://api.x.ai/v1")

    Returns:
        dict with: text, is_error, error, cost_usd, tokens_in, tokens_out,
                   session_id, thinking, tool_events (JSON string)
    """
    # Remote APIs (xAI, OpenAI, ChatGPT OAuth) bypass the local tools gate —
    # they don't execute local-model tools, they just use the chat completion loop.
    is_remote = bool(
        api_key
        and api_url
        and (api_url.startswith("http") or api_url == "chatgpt")
    )
    if not ALLOW_LOCAL_TOOLS and not is_remote:
        raise RuntimeError("Local model tools are disabled (set APEX_ALLOW_LOCAL_TOOLS=1 to enable)")

    _loop_started_at = time.monotonic()
    tool_schemas = get_tool_schemas(allowed_tools)
    tool_events: list[dict] = []
    result_text = ""
    thinking_text = ""
    iteration_limit = max_iterations or MAX_TOOL_ITERATIONS
    # Use Responses API for OpenAI reasoning models (o3, o4, gpt-5)
    _use_responses_api = (
        api_key and api_url
        and "api.openai.com" in api_url
        and (model.startswith("o3") or model.startswith("o4") or model.startswith("gpt-5"))
    )

    # ChatGPT backend: uses Codex OAuth tokens, subscription billing (not API credits)
    _use_chatgpt_backend = api_url == "chatgpt"

    # Check if local Ollama model supports native tool calling.
    # If not, inject tool schemas as text and parse <tool_call> blocks.
    _use_text_tools = False
    if not is_remote and not _use_chatgpt_backend and tool_schemas:
        _use_text_tools = not await asyncio.to_thread(
            _check_native_tool_support, ollama_url, model
        )

    # For text-based tool calling, inject tool descriptions into messages
    _loop_messages = messages
    if _use_text_tools:
        tool_prompt = _build_tool_prompt(tool_schemas)
        _loop_messages = _inject_tool_prompt(messages, tool_prompt)
    else:
        _loop_messages = messages

    for iteration in range(iteration_limit):
        try:
            if _use_chatgpt_backend:
                response = await asyncio.to_thread(
                    _call_chatgpt_backend, model, _loop_messages, tool_schemas,
                    asyncio.get_event_loop(), emit_event
                )
            elif _use_responses_api:
                response = await asyncio.to_thread(
                    _call_openai_responses, api_url, model, _loop_messages, tool_schemas, api_key
                )
            elif api_key and api_url:
                response = await asyncio.to_thread(
                    _call_openai_compat, api_url, model, _loop_messages, tool_schemas, api_key
                )
            else:
                response = await asyncio.to_thread(
                    _call_ollama, ollama_url, model, _loop_messages, tool_schemas,
                    use_native_tools=not _use_text_tools,
                )
        except Exception as e:
            backend = "API" if (api_key and api_url) else "Ollama"
            err = f"{backend} error: {type(e).__name__}: {e}"
            await emit_event({"type": "error", "message": err})
            return _build_result("", tool_events, is_error=True, error=err, thinking=thinking_text,
                                   duration_ms=int((time.monotonic() - _loop_started_at) * 1000))

        # Emit reasoning/thinking if present
        reasoning = response.get("reasoning")  # OpenAI Responses API / ChatGPT backend
        assistant_msg = response.get("message", {})
        thinking = assistant_msg.get("thinking", "")  # Ollama (Qwen, etc.)
        if reasoning:
            thinking_text += reasoning + "\n"
            # Only emit the full block if deltas weren't already streamed in real-time
            if not response.get("reasoning_streamed"):
                await emit_event({"type": "thinking", "text": reasoning})
        elif thinking:
            thinking_text += thinking + "\n"
            await emit_event({"type": "thinking", "text": thinking})

        # Check for tool calls (native or text-based)
        tool_calls = assistant_msg.get("tool_calls")
        content_text = assistant_msg.get("content", "")

        # Text-based tool calling: parse <tool_call> blocks from content
        if not tool_calls and _use_text_tools and content_text:
            clean_text, parsed_calls = _parse_text_tool_calls(content_text)
            if parsed_calls:
                tool_calls = parsed_calls
                content_text = clean_text

        if not tool_calls:
            # No tool calls — emit final text and return
            if _use_text_tools and content_text:
                content_text = _strip_tool_result_tags(content_text)
            if content_text:
                result_text += content_text
                await emit_event({"type": "text", "text": content_text})
            return _build_result(result_text, tool_events, thinking=thinking_text,
                                   duration_ms=int((time.monotonic() - _loop_started_at) * 1000))

        # Model produced text alongside tool calls — emit it
        if _use_text_tools and content_text:
            content_text = _strip_tool_result_tags(content_text)
        if content_text:
            result_text += content_text
            await emit_event({"type": "text", "text": content_text})

        # Add assistant message to history (preserves tool_calls for context)
        if _use_text_tools:
            # For text-based: add the raw assistant text (with <tool_call> blocks)
            raw_content = assistant_msg.get("content", "")
            _loop_messages.append({"role": "assistant", "content": raw_content})
        else:
            _loop_messages.append(assistant_msg)

        # Execute each tool call
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "unknown")
            tool_args = func.get("arguments", {})
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    tool_args = {"raw": tool_args}

            tool_call_id = tc.get("id", uuid.uuid4().hex[:12])
            tool_id = tool_call_id

            # Emit tool_use event
            await emit_event({
                "type": "tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": tool_args,
            })

            if allowed_tools is not None and tool_name not in allowed_tools:
                if permission_level <= 0:
                    tool_result = "This agent is Restricted and cannot use tools or access files."
                elif permission_level == 1:
                    tool_result = "This action requires Elevated or Admin permissions."
                else:
                    tool_result = f"Error: tool '{tool_name}' is not enabled in the workspace policy. Check Dashboard → Policy → Workspace Tools."
                is_error = True
            else:
                # Guardrail pre-check
                block_reason = pre_check(tool_name, tool_args, model=model)
                if block_reason:
                    tool_result = block_reason
                    is_error = True
                else:
                    from tool_access import tool_access_decision

                    allowed, message = tool_access_decision(
                        tool_name,
                        tool_args if isinstance(tool_args, dict) else {},
                        level=permission_level,
                        allowed_commands=allowed_commands,
                        workspace_paths=workspace or "",
                        audit_context=audit_context,
                    )
                    if not allowed:
                        tool_result = message
                        is_error = True
                    else:
                        # Execute the tool
                        executor = get_executor(tool_name)
                        if executor:
                            try:
                                if tool_name == "bash":
                                    tool_result = await asyncio.to_thread(
                                        executor,
                                        tool_args,
                                        workspace,
                                        permission_level=permission_level,
                                        allowed_commands=allowed_commands,
                                    )
                                elif tool_name == "execute_code":
                                    _chat_id = audit_context.get("chat_id") if audit_context else None
                                    tool_result = await asyncio.to_thread(
                                        executor,
                                        tool_args,
                                        workspace,
                                        permission_level=permission_level,
                                        chat_id=_chat_id,
                                    )
                                else:
                                    tool_result = await asyncio.to_thread(
                                        executor,
                                        tool_args,
                                        workspace,
                                        permission_level=permission_level,
                                    )
                            except Exception as e:
                                tool_result = f"Error executing {tool_name}: {type(e).__name__}: {e}"
                        elif is_mcp_tool(tool_name):
                            try:
                                from .mcp_bridge import call_mcp_tool
                                tool_result = await call_mcp_tool(tool_name, tool_args)
                            except Exception as e:
                                tool_result = f"Error calling MCP tool {tool_name}: {type(e).__name__}: {e}"
                        else:
                            tool_result = f"Error: unknown tool '{tool_name}'"

                    is_error = tool_result.startswith("Error:")

                    # Secret filtering on output
                    tool_result = filter_output(tool_name, tool_result, model=model)

            # Emit tool_result event
            await emit_event({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": tool_result[:2000],
                "is_error": is_error,
            })

            # Track for DB storage
            tool_events.append({
                "id": tool_id,
                "name": tool_name,
                "input": tool_args,
                "result": {
                    "tool_use_id": tool_id,
                    "content": tool_result[:2000],
                    "is_error": is_error,
                },
            })

            # Add tool result to message history
            if _use_text_tools:
                _loop_messages.append({
                    "role": "user",
                    "content": f"<tool_result>\n{tool_result[:2000]}\n</tool_result>",
                })
            else:
                _loop_messages.append({"role": "tool", "content": tool_result, "tool_call_id": tool_call_id})

    # Hit max iterations
    max_msg = "\n\n[Reached maximum tool iterations]"
    result_text += max_msg
    await emit_event({"type": "text", "text": max_msg})
    return _build_result(result_text, tool_events, thinking=thinking_text,
                           duration_ms=int((time.monotonic() - _loop_started_at) * 1000))
