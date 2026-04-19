"""Claude Agent SDK helpers — auth, attachments, turn execution, streaming.

Handles OAuth token refresh, attachment loading, turn payload construction,
query execution with retry/auth recovery, and response stream processing.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import env
from db import _get_chat, _get_chat_tool_policy, _get_messages, _estimate_tokens
from log import log
from model_dispatch import MODEL_CONTEXT_WINDOWS, MODEL_CONTEXT_DEFAULT, MODEL_INPUT_PRICE, MODEL_OUTPUT_PRICE
from state import _clients, _session_context_sent
from tool_access import tool_access_decision, resolve_profile_extra_tools
from streaming import (
    _send_stream_event, _disconnect_client,
    _normalize_response_stream,
)
from context import (
    _get_profile_prompt, _get_group_roster_prompt,
    _get_memory_prompt, _get_workspace_context, _get_whisper_text,
    _get_context_energy_prompt, _compute_context_used,
)

try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config (from env)
# ---------------------------------------------------------------------------
APEX_ROOT = env.APEX_ROOT
WORKSPACE = env.WORKSPACE
MODEL = env.MODEL
DEBUG = env.DEBUG
SSL_CA = env.SSL_CA
SDK_QUERY_TIMEOUT = env.SDK_QUERY_TIMEOUT
SDK_STREAM_TIMEOUT = env.SDK_STREAM_TIMEOUT
ENABLE_SUBCONSCIOUS_WHISPER = env.ENABLE_SUBCONSCIOUS_WHISPER
ENABLE_METACOGNITION = env.ENABLE_METACOGNITION
ENABLE_UNIFIED_MEMORY = env.ENABLE_UNIFIED_MEMORY

UPLOAD_DIR = APEX_ROOT / "state" / "uploads"

# Partial results for cancelled turns — updated during streaming so cancel
# handler can save whatever accumulated before interruption.
_partial_results: dict[str, dict] = {}
IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp"}
TEXT_TYPES = {"txt", "py", "json", "csv", "md", "yaml", "yml", "toml", "cfg", "ini", "log", "html", "css", "js", "ts", "sh"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_SIZE = 1 * 1024 * 1024    # 1MB


# ---------------------------------------------------------------------------
# OAuth / auth recovery
# ---------------------------------------------------------------------------

_AUTH_ERROR_PATTERNS = (
    "Not logged in",
    "Invalid API key",
    "Fix external API key",
    "Please run /login",
)

_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_OAUTH_REFRESH_BUFFER_S = 5 * 60  # 5 minutes — match Claude Code's internal buffer
_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TOKEN_CACHE = Path.home() / ".apex" / ".oauth_token"
_OAUTH_CACHE = Path.home() / ".apex" / ".oauth_data.json"  # full OAuth blob

# Shared token file — persistent token that survives server restarts.
# Set APEX_SHARED_TOKEN_PATH to override. Generated via `scripts/setup_auth.sh`
# or `claude setup-token`.
_SHARED_TOKEN_PATH = Path(
    os.environ.get("APEX_SHARED_TOKEN_PATH", str(Path.home() / ".apex" / ".anthropic_token"))
)


def _read_shared_token() -> str:
    """Read token from shared token file. Returns '' if unavailable."""
    try:
        if _SHARED_TOKEN_PATH.exists():
            token = _SHARED_TOKEN_PATH.read_text().strip()
            if token:
                return token
    except Exception:
        pass
    return ""


def _validate_token(token: str) -> bool:
    """Quick validation that the API accepts this token. Returns True if valid.

    OAuth tokens (sk-ant-oat*) can't be validated via direct API call — the
    Anthropic REST API doesn't support them. Only the Claude SDK uses them
    internally. For OAuth tokens, we just check the token is non-empty (expiry
    is checked separately via _validate_oauth_expiry).
    API keys (sk-ant-api*) are validated with a real API call.
    """
    if not token:
        return False
    # OAuth access tokens can't be validated via API — SDK handles them
    if _is_oauth_token(token):
        return True
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }).encode(),
        headers={
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False
        # 4xx other than auth = token is valid, request was wrong (that's fine)
        return e.code != 403
    except Exception:
        # Network error — can't tell, assume valid
        return True


def _is_oauth_token(token: str) -> bool:
    """Check if a token is an OAuth access token (vs API key)."""
    return "oat" in token[:15]


def _validate_oauth_expiry(oauth_data: dict) -> bool:
    """Check if an OAuth token has not expired. Returns True if still valid."""
    expires_at = oauth_data.get("expiresAt", 0)
    if not expires_at:
        return False
    import time
    # expiresAt is in milliseconds
    now_ms = int(time.time() * 1000)
    return expires_at > now_ms


def _is_auth_error(text: str) -> bool:
    """Check if SDK response text indicates an authentication failure."""
    return any(p in text for p in _AUTH_ERROR_PATTERNS)


def _read_keychain_oauth() -> dict:
    """Read full OAuth data from macOS Keychain. Returns {} on failure."""
    try:
        import subprocess as _sp
        result = _sp.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            creds = json.loads(result.stdout.strip())
            return creds.get("claudeAiOauth", {})
    except Exception:
        pass
    # Fallback: cached OAuth data
    try:
        if _OAUTH_CACHE.exists():
            return json.loads(_OAUTH_CACHE.read_text())
    except Exception:
        pass
    return {}


def _write_keychain_oauth(oauth_data: dict) -> bool:
    """Write updated OAuth data back to macOS Keychain."""
    try:
        import subprocess as _sp
        # Read full credentials blob, update claudeAiOauth section
        result = _sp.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False
        creds = json.loads(result.stdout.strip())
        creds["claudeAiOauth"] = oauth_data
        blob = json.dumps(creds, separators=(",", ":"))
        # Delete + add (Keychain doesn't have an atomic update)
        _sp.run(
            ["security", "delete-generic-password", "-s", _KEYCHAIN_SERVICE],
            capture_output=True, timeout=5,
        )
        _sp.run(
            ["security", "add-generic-password", "-s", _KEYCHAIN_SERVICE,
             "-a", "", "-w", blob, "-U"],
            capture_output=True, timeout=5, check=True,
        )
        return True
    except Exception as e:
        log(f"Keychain write failed: {e}")
        return False


def _cache_oauth_data(oauth_data: dict, access_token: str) -> None:
    """Cache OAuth data and access token to disk."""
    try:
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(access_token)
        from compat import safe_chmod
        safe_chmod(_TOKEN_CACHE, 0o600)
        _OAUTH_CACHE.write_text(json.dumps(oauth_data, separators=(",", ":")))
        safe_chmod(_OAUTH_CACHE, 0o600)
    except Exception:
        pass


def _do_token_refresh(refresh_token: str, scopes: list[str] | None = None) -> dict | None:
    """Exchange a refresh token for a new access token via Anthropic's OAuth endpoint.

    Returns the raw response dict on success, None on failure.
    """
    # Match Claude Code's internal refresh request format
    default_scopes = [
        "user:profile", "user:inference", "user:sessions:claude_code",
        "user:mcp_servers", "user:file_upload",
    ]
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _OAUTH_CLIENT_ID,
        "scope": " ".join(scopes or default_scopes),
    }).encode()
    req = urllib.request.Request(
        _OAUTH_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "claude-code/1.0",  # required — Cloudflare blocks default urllib UA
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log(f"OAuth token refresh HTTP failed: {e}")
        return None


def _refresh_oauth_token() -> bool:
    """Proactive OAuth refresh — check expiry, refresh if needed, update everywhere.

    Token resolution priority:
    1. Shared token file (persistent across restarts)
    2. Keychain OAuth (macOS, auto-refresh)
    3. Plain cache file (fallback)
    """
    # --- Priority 1: shared token file ---
    shared = _read_shared_token()
    if shared:
        current_env = os.environ.get("ANTHROPIC_API_KEY", "")
        if current_env != shared:
            os.environ["ANTHROPIC_API_KEY"] = shared
            log(f"OAuth: loaded from shared token file ({_SHARED_TOKEN_PATH.name}, {len(shared)} chars)")
            return True
        return False  # already in sync

    # --- Priority 2: Keychain OAuth ---
    oauth = _read_keychain_oauth()
    access_token = oauth.get("accessToken", "")
    refresh_token = oauth.get("refreshToken", "")
    expires_at = oauth.get("expiresAt", 0)

    if not access_token:
        # Last resort: plain cache file
        try:
            if _TOKEN_CACHE.exists():
                token = _TOKEN_CACHE.read_text().strip()
                if token:
                    os.environ["ANTHROPIC_API_KEY"] = token
                    log("OAuth: re-synced from token cache (no Keychain access)")
                    return True
        except Exception:
            pass
        log("OAuth refresh failed: no token from Keychain, shared file, or cache")
        return False

    now_ms = int(time.time() * 1000)
    buffer_ms = _OAUTH_REFRESH_BUFFER_S * 1000
    token_expiring = expires_at > 0 and (now_ms + buffer_ms) >= expires_at

    if token_expiring and refresh_token:
        remaining_s = max(0, (expires_at - now_ms) / 1000)
        log(f"OAuth: token expires in {remaining_s:.0f}s (buffer={_OAUTH_REFRESH_BUFFER_S}s), refreshing...")
        resp = _do_token_refresh(refresh_token, scopes=oauth.get("scopes"))
        if resp and resp.get("access_token"):
            new_access = resp["access_token"]
            new_refresh = resp.get("refresh_token", refresh_token)
            new_expires_in = resp.get("expires_in", 3600)
            new_expires_at = int(time.time() * 1000) + (new_expires_in * 1000)

            # Update OAuth blob
            oauth["accessToken"] = new_access
            oauth["refreshToken"] = new_refresh
            oauth["expiresAt"] = new_expires_at
            if resp.get("scope"):
                oauth["scopes"] = resp["scope"].split() if isinstance(resp["scope"], str) else resp["scope"]

            # Persist everywhere
            os.environ["ANTHROPIC_API_KEY"] = new_access
            _cache_oauth_data(oauth, new_access)
            _write_keychain_oauth(oauth)
            log(f"OAuth: token refreshed OK, new expiry in {new_expires_in}s")
            return True
        else:
            log("OAuth: refresh endpoint failed, falling back to current token")
            # Still update env with current (possibly stale) token
            os.environ["ANTHROPIC_API_KEY"] = access_token
            _cache_oauth_data(oauth, access_token)
            return True

    # Token is still valid — just ensure env var is in sync
    current_env = os.environ.get("ANTHROPIC_API_KEY", "")
    if current_env != access_token:
        os.environ["ANTHROPIC_API_KEY"] = access_token
        _cache_oauth_data(oauth, access_token)
        remaining_s = max(0, (expires_at - now_ms) / 1000) if expires_at else 0
        log(f"OAuth: env var re-synced from Keychain (expires in {remaining_s:.0f}s)")
        return True

    return False


def _is_env_file_key() -> bool:
    """Check if ANTHROPIC_API_KEY was set via .env file (user-provided, not OAuth)."""
    try:
        env_path = Path(os.environ.get(
            "APEX_ENV_FILE",
            str(Path.home() / ".apex" / ".env"),
        ))
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == "ANTHROPIC_API_KEY" and val.strip().strip('"').strip("'"):
                    return True
    except Exception:
        pass
    return False


def ensure_fresh_token() -> None:
    """Proactive token check — call before creating SDK clients.

    Priority:
    1. Explicit ANTHROPIC_API_KEY in .env file — never overwritten by OAuth
    2. Shared token file (persistent across restarts)
    3. Keychain OAuth — NOT set as env var (CLI handles its own auth)

    Evicts stale SDK clients when the token changes.
    """
    current_env = os.environ.get("ANTHROPIC_API_KEY", "")

    # If ANTHROPIC_API_KEY is set to an OAuth token (sk-ant-oat*), clear it.
    # OAuth tokens can't be used as API keys — the CLI must handle OAuth
    # via its own Keychain auth. Setting them as env vars breaks the SDK.
    if current_env and _is_oauth_token(current_env):
        del os.environ["ANTHROPIC_API_KEY"]
        log("OAuth: cleared OAuth token from ANTHROPIC_API_KEY (CLI uses Keychain)")
        _evict_all_clients()
        current_env = ""

    # If the user explicitly set ANTHROPIC_API_KEY in their .env file,
    # respect it — don't let OAuth/Keychain overwrite a working API key.
    if current_env and _is_env_file_key():
        return

    # Shared token file takes priority — no expiry tracking needed
    shared = _read_shared_token()
    if shared and not _is_oauth_token(shared):
        if current_env != shared:
            os.environ["ANTHROPIC_API_KEY"] = shared
            log(f"OAuth: synced from shared token file")
            _evict_all_clients()
        return

    # For Keychain OAuth: don't set ANTHROPIC_API_KEY.
    # The Claude CLI subprocess reads Keychain directly.
    # Just verify the token exists and refresh if near expiry.
    oauth = _read_keychain_oauth()
    expires_at = oauth.get("expiresAt", 0)
    access_token = oauth.get("accessToken", "")

    if not access_token:
        return

    now_ms = int(time.time() * 1000)
    buffer_ms = _OAUTH_REFRESH_BUFFER_S * 1000
    if expires_at > 0 and (now_ms + buffer_ms) >= expires_at:
        refreshed = _refresh_oauth_token()
        if refreshed:
            _evict_all_clients()


def _evict_all_clients() -> None:
    """Evict all SDK clients so they get recreated with fresh token."""
    stale_keys = list(_clients.keys())
    if stale_keys:
        for k in stale_keys:
            _clients.pop(k, None)
        log(f"OAuth: evicted {len(stale_keys)} stale SDK client(s)")


def validate_token_on_startup() -> None:
    """Call once at server boot to verify the token is accepted by the API.

    If the initial token is invalid, attempts an OAuth refresh before giving up.
    Does NOT block startup — logs a clear warning with recovery instructions.
    """
    # If .env has an explicit API key, use it and skip OAuth entirely
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key and _is_env_file_key():
        log(f"OAuth startup: using explicit API key from .env ({env_key[:12]}..., {len(env_key)} chars)")
        if _validate_token(env_key):
            log("OAuth startup: .env API key validated OK")
        else:
            log("WARNING: OAuth startup: .env ANTHROPIC_API_KEY is INVALID (rejected by API). "
                "Check the key in your .env file.")
        return

    # Resolve token: shared file > Keychain > cache
    token = _read_shared_token()
    source = "shared file"
    if not token:
        oauth = _read_keychain_oauth()
        token = oauth.get("accessToken", "")
        source = "Keychain"
    if not token:
        try:
            token = _TOKEN_CACHE.read_text().strip() if _TOKEN_CACHE.exists() else ""
            source = "cache file"
        except Exception:
            token = ""

    if not token:
        log("OAuth startup: no Anthropic token found (shared file, Keychain, cache all empty). "
            "Set ANTHROPIC_API_KEY in .env or run: bash scripts/setup_auth.sh")
        return

    # OAuth tokens (sk-ant-oat*) must NOT be set as ANTHROPIC_API_KEY.
    # The CLI handles OAuth via Keychain — setting it as env var breaks auth.
    if _is_oauth_token(token):
        log(f"OAuth startup: Keychain OAuth token found ({token[:12]}..., {len(token)} chars). "
            "CLI will authenticate via Keychain.")
        # Clear env var if it was set to an OAuth token previously
        if os.environ.get("ANTHROPIC_API_KEY", "") and _is_oauth_token(os.environ["ANTHROPIC_API_KEY"]):
            del os.environ["ANTHROPIC_API_KEY"]
        return

    # API key — set as env var and validate
    os.environ["ANTHROPIC_API_KEY"] = token
    log(f"OAuth startup: token loaded from {source} ({token[:12]}...{token[-4:]}, {len(token)} chars)")

    if _validate_token(token):
        log("OAuth startup: token validated OK")
        return

    # Token is invalid — try OAuth refresh before giving up
    log(f"OAuth startup: token from {source} is INVALID, attempting refresh...")
    refreshed = _refresh_oauth_token()
    if refreshed:
        new_token = os.environ.get("ANTHROPIC_API_KEY", "")
        if new_token and _validate_token(new_token):
            log("OAuth startup: token refreshed and validated OK")
            _evict_all_clients()
            return
        log("OAuth startup: refresh produced a new token but it also failed validation")

    log("WARNING: OAuth startup: could not obtain a valid token. Options:\n"
        "  1. Set ANTHROPIC_API_KEY in .env (recommended for servers)\n"
        "  2. Run: bash scripts/setup_auth.sh\n"
        "  3. Run: claude auth login (then restart server)")


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _stringify_block_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, indent=2)
    except TypeError:
        return str(content)


def _attachment_label(name: str, kind: str) -> str:
    prefix = "Image" if kind == "image" else "File"
    return f"{prefix}: {name}"


def _summarize_attachments(items: list[dict]) -> str:
    labels = [_attachment_label(item["name"], item["type"]) for item in items]
    return "Attachments: " + ", ".join(labels)


def _normalize_filename(filename: str | None, fallback: str = "upload") -> str:
    """Sanitize uploaded filename."""
    import re as _re
    if not filename:
        return fallback
    safe = _re.sub(r"[^\w.\-]", "_", filename.strip())[:100]
    return safe or fallback


def _guess_mime_type(ext: str) -> str:
    """Map extension to MIME type for images."""
    _MIME_MAP = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif",
        "webp": "image/webp",
    }
    import mimetypes
    mime = _MIME_MAP.get(ext.lower())
    if mime:
        return mime
    mime = mimetypes.guess_type(f"file.{ext}")[0]
    return mime or ("image/jpeg" if ext in {"jpg", "jpeg"} else "application/octet-stream")


def _load_attachment(att: dict) -> dict:
    att_id = str(att.get("id", "")).strip().lower()
    if len(att_id) != 8 or any(ch not in "0123456789abcdef" for ch in att_id):
        raise ValueError("Invalid attachment id")

    matches = list(UPLOAD_DIR.glob(f"{att_id}.*"))
    if len(matches) != 1:
        raise ValueError("Attachment not found")

    path = matches[0].resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path.parent != upload_root:
        raise ValueError("Invalid attachment path")

    ext = path.suffix.lstrip(".").lower()
    if ext in IMAGE_TYPES:
        kind = "image"
        limit = MAX_IMAGE_SIZE
    elif ext in TEXT_TYPES:
        kind = "text"
        limit = MAX_TEXT_SIZE
    else:
        raise ValueError(f"Unsupported attachment type: .{ext}")

    requested_type = str(att.get("type", "")).strip()
    if requested_type and requested_type != kind:
        raise ValueError("Attachment type mismatch")

    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("Attachment exceeds size limit")

    return {
        "id": att_id,
        "name": _normalize_filename(att.get("name"), path.name),
        "type": kind,
        "ext": ext,
        "path": str(path),
        "data": data,
        "mimeType": _guess_mime_type(ext) if kind == "image" else None,
    }


# ---------------------------------------------------------------------------
# Turn payload builder
# ---------------------------------------------------------------------------

def _build_turn_payload(chat_id: str, prompt: str, attachments: list[dict]) -> tuple[str, callable]:
    loaded = [_load_attachment(att) for att in attachments]

    prompt_lines: list[str] = []
    if prompt:
        prompt_lines.append(prompt)
    for item in loaded:
        if item["type"] == "text":
            prompt_lines.append(f"[Attached file: {item['name']} at {item['path']}]")
    query_prompt = "\n\n".join(prompt_lines).strip()

    display_parts: list[str] = []
    if prompt:
        display_parts.append(prompt)
    if loaded:
        display_parts.append(_summarize_attachments(loaded))
    display_prompt = "\n".join(display_parts).strip() or "(attachment)"

    image_blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": item["mimeType"],
                "data": base64.b64encode(item["data"]).decode(),
            },
        }
        for item in loaded
        if item["type"] == "image"
    ]
    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id, user_message=query_prompt)
    memory_prompt = "" if group_roster_prompt else _get_memory_prompt(chat_id, user_message=query_prompt)
    workspace_ctx = _get_workspace_context(chat_id)
    whisper = _get_whisper_text(chat_id, current_prompt=query_prompt,
                               model_hint="claude-sdk") if ENABLE_SUBCONSCIOUS_WHISPER else ""
    context_energy = _get_context_energy_prompt(chat_id)
    # Metacognition: when unified memory is active, metacognition results
    # are already merged into the whisper Type 2 path (context.py).
    # Only call the separate metacognition system when unified memory is off.
    metacog = ""
    if ENABLE_METACOGNITION and not ENABLE_UNIFIED_MEMORY:
        try:
            from metacognition import retrieve_prior_context
            metacog = retrieve_prior_context(query_prompt)
        except Exception as e:
            log.warning("metacognition import/call failed: %s", e)
    prefix = f"{profile_prompt}{group_roster_prompt}{memory_prompt}{workspace_ctx}{context_energy}{whisper}{metacog}".strip()
    final_prompt = query_prompt or ("What do you see?" if image_blocks else "")
    if prefix:
        final_prompt = f"{prefix}\n\n{final_prompt}".strip() if final_prompt else prefix

    if image_blocks:
        saved_blocks = list(image_blocks) + [{"type": "text", "text": final_prompt}]

        def make_query_input():
            async def _make_stream():
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": list(saved_blocks)},
                    "parent_tool_use_id": None,
                }
            return _make_stream()

        return display_prompt, make_query_input

    def make_query_input():
        return final_prompt

    return display_prompt, make_query_input


# ---------------------------------------------------------------------------
# WebSocket origin check
# ---------------------------------------------------------------------------

def _websocket_origin_allowed(websocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return bool(SSL_CA)
    host = (websocket.headers.get("host") or "").lower()
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


# ---------------------------------------------------------------------------
# Query turn execution with retry + auth recovery
# ---------------------------------------------------------------------------

async def _run_query_turn(
    client: ClaudeSDKClient,
    make_query_input,
    chat_id: str,
    *,
    permission_level: int | None = None,
    allowed_commands: list[str] | None = None,
    client_key: str | None = None,
) -> dict:
    if DEBUG: log(f"DBG query_turn: chat={chat_id} sending query...")
    await asyncio.wait_for(client.query(make_query_input()), timeout=SDK_QUERY_TIMEOUT)
    if DEBUG: log(f"DBG query_turn: chat={chat_id} query sent, streaming response...")
    result = await asyncio.wait_for(
        _stream_response(
            client,
            chat_id,
            permission_level=permission_level,
            allowed_commands=allowed_commands,
            client_key=client_key,
        ),
        timeout=SDK_STREAM_TIMEOUT,
    )
    if result.get("stream_failed"):
        if DEBUG: log(f"DBG query_turn: chat={chat_id} STREAM FAILED: {result.get('error')}")
        raise RuntimeError(result.get("error") or "SDK stream failed")
    # SDK auth recovery — trigger on auth error text regardless of token count.
    # The SDK can consume tokens (thinking, tool calls) and still return auth
    # error text if the OAuth token expires mid-turn or between client creation
    # and query execution.
    resp_text = result.get("text", "")
    if _is_auth_error(resp_text):
        log(f"SDK auth error: chat={chat_id} got '{resp_text.strip()[:60]}' (tokens_in={result.get('tokens_in',0)}), attempting recovery...")
        refreshed = await asyncio.to_thread(_refresh_oauth_token)
        if refreshed:
            for k in list(_clients.keys()):
                if k == chat_id or k.startswith(chat_id + ":"):
                    _clients.pop(k, None)
            log(f"SDK auth recovery: token refreshed, stale clients evicted for chat={chat_id}")
        # Raise so _handle_send_action creates a fresh client with the new token
        raise RuntimeError(f"SDK auth error (recovered token={'yes' if refreshed else 'no'}): {resp_text.strip()[:60]}")
    if DEBUG: log(f"DBG query_turn: chat={chat_id} done. text={len(result.get('text',''))}chars tools={result.get('tool_events','[]').count('tool_use_id')} session={result.get('session_id','?')[:8] if result.get('session_id') else 'none'}")
    return result


# ---------------------------------------------------------------------------
# Response stream processor
# ---------------------------------------------------------------------------

async def _stream_response(
    client: ClaudeSDKClient,
    chat_id: str,
    *,
    permission_level: int | None = None,
    allowed_commands: list[str] | None = None,
    client_key: str | None = None,
) -> dict:
    """Stream SDK response events to WebSocket. Returns turn result."""
    result_text = ""
    thinking_text = ""
    tool_events: list[dict] = []
    pending_tools: dict[str, dict] = {}
    result_info: dict = {
        "session_id": None, "text": "", "thinking": "",
        "tool_events": "[]", "cost_usd": 0,
        "tokens_in": 0, "tokens_out": 0, "error": None,
        "stream_failed": False, "is_error": False,
    }

    async def _send(payload: dict) -> None:
        await _send_stream_event(chat_id, payload)

    def _full_admin_mode() -> bool:
        effective_level = permission_level
        if effective_level is None:
            try:
                effective_level = int(_get_chat_tool_policy(chat_id).get("level", 2))
            except Exception:
                effective_level = 2
        return int(effective_level) >= 4

    def _host_denied_pending_tools(items: list[dict]) -> list[dict]:
        effective_level = int(permission_level if permission_level is not None else _get_chat_tool_policy(chat_id).get("level", 2))
        effective_allowed_commands = list(allowed_commands or [])
        # Resolve per-profile extras (guide tools, gate-test claim_store, etc.)
        # from client_key — same semantics as streaming._resolve_guide_extra_tools.
        _profile_id = ""
        if client_key:
            if ":" in client_key:
                _profile_id = client_key.split(":", 1)[1]
            else:
                try:
                    _chat = _get_chat(client_key)
                    if _chat:
                        _profile_id = str(_chat.get("profile_id", "") or "")
                except Exception:
                    _profile_id = ""
        effective_extras = resolve_profile_extra_tools(_profile_id) or None
        denied: list[dict] = []
        for item in items:
            allowed, _message = tool_access_decision(
                str(item.get("name") or ""),
                item.get("input") if isinstance(item.get("input"), dict) else {},
                level=effective_level,
                allowed_commands=effective_allowed_commands,
                workspace_paths=env.get_runtime_workspace_paths(),
                extra_allowed_tools=effective_extras,
                audit_context={
                    "source": "sdk_pending",
                    "client_key": client_key or "",
                    "chat_id": chat_id,
                },
            )
            if not allowed:
                denied.append(item)
        return denied

    def _pending_tool_denial_message(items: list[dict]) -> str:
        names = [str(item.get("name") or "").strip() for item in items]
        names = [name for name in names if name]
        if not names:
            return "Tool execution was denied by host permissions."
        if len(names) == 1:
            return f"Tool execution was denied by host permissions: {names[0]}."
        return (
            "Tool execution was denied by host permissions: "
            + ", ".join(names[:5])
            + ("." if len(names) <= 5 else ", ...")
        )

    def _single_tool_denial_message(item: dict) -> str:
        name = str(item.get("name") or "").strip()
        if not name:
            return "Tool execution was denied by host permissions."
        return f"Tool execution was denied by host permissions: {name}."

    def _merge_blocked_tool_result(partial_text: str, blocked_tool_message: str) -> str:
        denial_note = (
            f"{blocked_tool_message}\n"
            "The assistant's partial response was preserved, but any blocked tool work "
            "did not run. Update permissions and continue the same task to resume."
        ).strip()
        partial = partial_text.strip()
        if not partial:
            return denial_note
        if denial_note in partial:
            return partial
        return f"{partial}\n\n---\n{denial_note}"

    async def _flush_pending_tools(
        default_content: str = "",
        default_is_error: bool = False,
        *,
        per_tool_results: dict[str, tuple[str, bool]] | None = None,
    ) -> None:
        if not pending_tools:
            return
        pending_items = list(pending_tools.items())
        pending_tools.clear()
        if DEBUG:
            log(f"DBG flush pending Claude tools: chat={chat_id} count={len(pending_items)} error={default_is_error}")
        for tool_use_id, current_tool in pending_items:
            content = default_content
            is_error = default_is_error
            if per_tool_results and tool_use_id in per_tool_results:
                content, is_error = per_tool_results[tool_use_id]
            tool_events.append({
                **current_tool,
                "result": {
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                },
            })
            await _send({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content[:2000],
                "is_error": is_error,
            })

    _stream_event_count = 0
    _stream_start = time.monotonic()
    # Track partial results for cancel-save
    _partial_results[chat_id] = {"text": "", "thinking": "", "tool_events": [], "start": _stream_start}
    try:
        response = _normalize_response_stream(client.receive_response())
        async for msg in response:
            _stream_event_count += 1
            elapsed = time.monotonic() - _stream_start
            if _stream_event_count <= 3 or _stream_event_count % 20 == 0:
                if DEBUG: log(f"DBG stream event #{_stream_event_count} ({elapsed:.0f}s): chat={chat_id} type={type(msg).__name__}")
            if isinstance(msg, SystemMessage):
                if msg.subtype == "init":
                    data = msg.data if isinstance(msg.data, dict) else {}
                    model_name = data.get("model", MODEL)
                    await _send({"type": "system", "subtype": "init", "model": model_name})

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
                        _partial_results[chat_id]["text"] = result_text
                        # Don't stream raw auth errors to user — they'll get
                        # a helpful message via the error handler instead
                        if _is_auth_error(block.text):
                            continue
                        await _send({"type": "text", "text": block.text})

                    elif isinstance(block, ThinkingBlock):
                        _tk = block.thinking or ""
                        thinking_text += _tk
                        _partial_results[chat_id]["thinking"] = thinking_text
                        await _send({"type": "thinking", "text": _tk})

                    elif isinstance(block, ToolUseBlock):
                        tool_event = {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                        pending_tools[block.id] = tool_event
                        await _send({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                    elif isinstance(block, ToolResultBlock):
                        content = _stringify_block_content(block.content)
                        is_error = block.is_error or False
                        tool_use_id = block.tool_use_id or ""
                        MAX_TOOL_RESULT_CHARS = 5000
                        if len(content) > MAX_TOOL_RESULT_CHARS:
                            tool_name = pending_tools.get(tool_use_id, {}).get("name", "?")
                            if DEBUG: log(f"DBG tool result TRUNCATED: {tool_name} {len(content)} -> {MAX_TOOL_RESULT_CHARS} chars")
                            content = content[:MAX_TOOL_RESULT_CHARS] + f"\n\n[... truncated from {len(content)} chars]"
                        current_tool = pending_tools.pop(tool_use_id, None)
                        if current_tool:
                            tool_events.append({
                                **current_tool,
                                "result": {"tool_use_id": tool_use_id,
                                           "content": content, "is_error": is_error},
                            })
                            _partial_results[chat_id]["tool_events"] = tool_events
                        await _send({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content[:2000],
                            "is_error": is_error,
                        })

            elif isinstance(msg, ResultMessage):
                log(f"ResultMessage usage dict: {msg.usage}")
                full_admin_mode = _full_admin_mode()
                pending_at_result = list(pending_tools.values())
                blocked_tools = [] if full_admin_mode else _host_denied_pending_tools(pending_at_result)
                blocked_ids = {
                    str(item.get("id") or "")
                    for item in blocked_tools
                    if str(item.get("id") or "")
                }
                # V3 v2 Step 1b — scope-limited flip. For claim_store__* tools,
                # a pending tool_use at ResultMessage time means the model emitted
                # the tool call but Anthropic's SDK never received an explicit
                # tool_result block back — which happens when our stdio subprocess
                # raised (e.g. _validate_sha256 rejection). Synthesizing
                # is_error=False would mask the server-side failure and the model
                # would never learn. Flip to is_error=True for claim_store only;
                # all other MCP tools keep the current implicit-success default
                # (Finding-1-general fix is out of v2 scope — filesystem,
                # playwright, computer_use all depend on the existing behavior).
                _CLAIM_STORE_NAMES = (
                    "mcp__claim_store__claim_assert",
                    "mcp__claim_store__claim_revise",
                    "mcp__claim_store__claim_list",
                )
                implicit_success_tools = [
                    item for item in pending_at_result
                    if str(item.get("id") or "") not in blocked_ids
                    and str(item.get("name") or "") not in _CLAIM_STORE_NAMES
                ]
                claim_store_no_result_tools = [
                    item for item in pending_at_result
                    if str(item.get("id") or "") not in blocked_ids
                    and str(item.get("name") or "") in _CLAIM_STORE_NAMES
                ]
                blocked_tool_message = _pending_tool_denial_message(blocked_tools) if blocked_tools else ""
                per_tool_results: dict[str, tuple[str, bool]] = {}
                for item in blocked_tools:
                    tool_id = str(item.get("id") or "")
                    if tool_id:
                        per_tool_results[tool_id] = (_single_tool_denial_message(item), True)
                for item in implicit_success_tools:
                    tool_id = str(item.get("id") or "")
                    if tool_id:
                        per_tool_results[tool_id] = ("[tool completed; SDK omitted explicit result block]", False)
                for item in claim_store_no_result_tools:
                    tool_id = str(item.get("id") or "")
                    if tool_id:
                        per_tool_results[tool_id] = (
                            "[claim_store tool did not return an explicit result; "
                            "the server likely rejected the call — treat as failure "
                            "and review the args (sha256 format, chat_id, source_type).]",
                            True,
                        )
                await _flush_pending_tools(
                    default_content=blocked_tool_message if blocked_tools else "[tool completed; SDK omitted explicit result block]",
                    default_is_error=bool(blocked_tools),
                    per_tool_results=per_tool_results,
                )
                final_text = msg.result or result_text
                if blocked_tools:
                    log(
                        f"SDK pending tool flush forced deny: chat={chat_id} "
                        f"tools={[item.get('name') for item in blocked_tools]}"
                    )
                    final_text = result_text or msg.result or ""
                    final_text = _merge_blocked_tool_result(final_text, blocked_tool_message)
                elif implicit_success_tools:
                    log(
                        f"SDK result completed with implicit tool success: chat={chat_id} "
                        f"tools={[item.get('name') for item in implicit_success_tools]}"
                    )
                if claim_store_no_result_tools:
                    # V3 v2 Step 1b — claim_store pending at ResultMessage means
                    # the stdio subprocess raised. Surface loudly so post-deploy
                    # log grep can count these.
                    log(
                        f"SDK claim_store tool had no explicit result (treated as error): "
                        f"chat={chat_id} "
                        f"tools={[item.get('name') for item in claim_store_no_result_tools]}"
                    )
                elapsed = time.monotonic() - _stream_start
                result_info = {
                    "session_id": msg.session_id,
                    "text": final_text,
                    "thinking": thinking_text,
                    "tool_events": json.dumps(tool_events),
                    "cost_usd": msg.total_cost_usd or 0,
                    "tokens_in": (msg.usage or {}).get("input_tokens", 0),
                    "tokens_out": (msg.usage or {}).get("output_tokens", 0),
                    "duration_ms": int(elapsed * 1000),
                    "error": None,
                    "stream_failed": False,
                    "is_error": bool(msg.is_error or blocked_tools),
                }
                result_is_error = bool(result_info["is_error"])
                _chat = _get_chat(chat_id)
                _ctx_model = (_chat.get("model") or MODEL) if _chat else MODEL
                _ctx_window = MODEL_CONTEXT_WINDOWS.get(_ctx_model, MODEL_CONTEXT_DEFAULT)
                # Three-signal fuel gauge — shared helper, same logic every site.
                _, _, _, _ctx_in = _compute_context_used(
                    chat_id, _ctx_window, _ctx_model
                )
                await _send({
                    "type": "result",
                    "is_error": result_is_error,
                    "cost_usd": result_info["cost_usd"],
                    "tokens_in": result_info["tokens_in"],
                    "tokens_out": result_info["tokens_out"],
                    "duration_ms": result_info["duration_ms"],
                    "session_id": msg.session_id,
                    "context_tokens_in": _ctx_in,
                    "context_window": _ctx_window,
                    "thinking": thinking_text,
                })
                if DEBUG: log(f"DBG stream COMPLETE: chat={chat_id} events={_stream_event_count} time={elapsed:.0f}s session={msg.session_id[:8] if msg.session_id else '?'} cost=${result_info['cost_usd']:.4f}")
                # Normal completion — clear partial results (ws_handler saves the full result)
                _partial_results.pop(chat_id, None)

    except asyncio.TimeoutError:
        if DEBUG: log(f"DBG stream TIMEOUT: chat={chat_id} after {SDK_STREAM_TIMEOUT}s. text={len(result_text)}chars thinking={len(thinking_text)}chars tools={len(tool_events)}")
        result_info["text"] = result_text
        result_info["thinking"] = thinking_text
        result_info["tool_events"] = json.dumps(tool_events)
        result_info["error"] = f"Stream timeout after {SDK_STREAM_TIMEOUT}s"
        result_info["stream_failed"] = True
        await _disconnect_client(chat_id)
    except Exception as e:
        if DEBUG: log(f"DBG stream ERROR: chat={chat_id} {type(e).__name__}: {e}. text={len(result_text)}chars thinking={len(thinking_text)}chars tools={len(tool_events)}")
        result_info["text"] = result_text
        result_info["thinking"] = thinking_text
        result_info["tool_events"] = json.dumps(tool_events)
        result_info["error"] = str(e)
        result_info["stream_failed"] = True
        await _disconnect_client(chat_id)

    if pending_tools:
        await _flush_pending_tools(
            default_content=result_info.get("error") or "",
            default_is_error=bool(result_info.get("stream_failed")),
        )
    if not result_info.get("text"):
        result_info["text"] = result_text
    if not result_info.get("thinking"):
        result_info["thinking"] = thinking_text
    if result_info.get("tool_events") == "[]" and tool_events:
        result_info["tool_events"] = json.dumps(tool_events)

    return result_info
