"""Ollama tool-calling agent loop."""
import asyncio
import json
import urllib.request
import uuid
from typing import Callable, Awaitable

from env import ALLOW_LOCAL_TOOLS

from .registry import get_tool_schemas, get_executor
from .guardrails import pre_check, filter_output

MAX_TOOL_ITERATIONS = 25
OLLAMA_TIMEOUT = 300  # 5 minutes per Ollama call
DEFAULT_NUM_CTX = 131072  # 128K context window


def _call_ollama(ollama_url: str, model: str, messages: list, tools: list) -> dict:
    """Synchronous Ollama API call (runs in thread)."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"num_ctx": DEFAULT_NUM_CTX},
    }).encode()
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    return json.loads(resp.read().decode())


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
        "reasoning": {"effort": "medium", "summary": "auto"},
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
    os.chmod(auth_path, 0o600)

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


def _build_result(text: str, tool_events: list, is_error: bool = False, error: str | None = None, thinking: str = "") -> dict:
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
    # Remote APIs (xAI, Codex) bypass the local tools gate — they don't
    # execute tools locally, they just need the chat completion loop.
    is_remote = bool(api_key and api_url and api_url.startswith("http"))
    if not ALLOW_LOCAL_TOOLS and not is_remote:
        raise RuntimeError("Local model tools are disabled (set APEX_ALLOW_LOCAL_TOOLS=1 to enable)")

    tool_schemas = get_tool_schemas()
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

    for iteration in range(iteration_limit):
        try:
            if _use_chatgpt_backend:
                response = await asyncio.to_thread(
                    _call_chatgpt_backend, model, messages, tool_schemas,
                    asyncio.get_event_loop(), emit_event
                )
            elif _use_responses_api:
                response = await asyncio.to_thread(
                    _call_openai_responses, api_url, model, messages, tool_schemas, api_key
                )
            elif api_key and api_url:
                response = await asyncio.to_thread(
                    _call_openai_compat, api_url, model, messages, tool_schemas, api_key
                )
            else:
                response = await asyncio.to_thread(
                    _call_ollama, ollama_url, model, messages, tool_schemas
                )
        except Exception as e:
            backend = "API" if (api_key and api_url) else "Ollama"
            err = f"{backend} error: {type(e).__name__}: {e}"
            await emit_event({"type": "error", "message": err})
            return _build_result("", tool_events, is_error=True, error=err, thinking=thinking_text)

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

        # Check for tool calls
        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            # No tool calls — emit final text and return
            text = assistant_msg.get("content", "")
            if text:
                result_text += text
                await emit_event({"type": "text", "text": text})
            return _build_result(result_text, tool_events, thinking=thinking_text)

        # Model produced text before tool calls — emit it
        if assistant_msg.get("content"):
            result_text += assistant_msg["content"]
            await emit_event({"type": "text", "text": assistant_msg["content"]})

        # Add assistant message to history (preserves tool_calls for context)
        messages.append(assistant_msg)

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

            # Guardrail pre-check
            block_reason = pre_check(tool_name, tool_args, model=model)
            if block_reason:
                tool_result = block_reason
                is_error = True
            else:
                # Execute the tool
                executor = get_executor(tool_name)
                if executor:
                    try:
                        tool_result = await asyncio.to_thread(executor, tool_args, workspace)
                    except Exception as e:
                        tool_result = f"Error executing {tool_name}: {type(e).__name__}: {e}"
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
            messages.append({"role": "tool", "content": tool_result, "tool_call_id": tool_call_id})

    # Hit max iterations
    max_msg = "\n\n[Reached maximum tool iterations]"
    result_text += max_msg
    await emit_event({"type": "text", "text": max_msg})
    return _build_result(result_text, tool_events, thinking=thinking_text)
