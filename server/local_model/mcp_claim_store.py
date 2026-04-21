#!/usr/bin/env python3
"""MCP server exposing claim_store tools: claim_assert / claim_list / claim_revise.

V3 v1 gate Day 1 — tag-mode claim management. Every factual assertion the
assistant emits should first be registered here with explicit source
provenance. The output gate (not yet built) will later consult this store
to decide whether prose may be emitted.

Storage: SQLite `claims` table in the active Apex DB (apex.db or apex_dev.db,
resolved via APEX_DB_NAME env — same convention as server/db.py).

Protocol: newline-delimited JSON-RPC over stdin/stdout (MCP stdio transport).
Run standalone:  python3 mcp_claim_store.py

Environment variables honored:
  APEX_DB_NAME                   DB file name under APEX_STATE_DIR (default apex.db).
  APEX_STATE_DIR                 State directory (default ~/.openclaw/apex/state).
  APEX_CHAT_ID                   (V3 v2 Step 1a) Authoritative chat_id for this
                                 subprocess; overrides model-supplied args["chat_id"].
                                 Set per-chat by streaming._inject_claim_store_mcp.
  APEX_AUTOPROVENANCE_DISABLE=1  (V3 v2 Step 2 kill switch) Disable server-side
                                 sha256 auto-population. Restores Day 4.5 behavior
                                 (model must supply sha256 explicitly). Ops-level
                                 rollback without a code push.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[mcp-claim-store] {msg}", file=sys.stderr, flush=True)


_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# --- DB resolution ----------------------------------------------------------

def _db_path() -> Path:
    state_dir = Path(os.environ.get(
        "APEX_STATE_DIR",
        str(Path.home() / ".openclaw/apex/state"),
    ))
    db_name = os.environ.get("APEX_DB_NAME", "apex.db")
    return state_dir / db_name


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


_SOURCE_TYPES = ("tool_result", "prior_turn", "speculation", "user")

# V3 v2 Step 3 — Room E §DELTA-E.5 (C14) 16th L1 field.
# Frozen at assert — revise may NOT mutate resource_type (E_RESOURCE_TYPE_MUTATED).
# Back-compat default at assert time: source_type='tool_result' → 'TOOL'.
_RESOURCE_TYPES = ("PROMPT", "AGENT", "TOOL", "ENV", "MEMORY")

# V3 Day 4.5 — compiled once for hot-path sha256 format check.
import re as _re
_SHA256_RE = _re.compile(r"^[0-9a-f]{64}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _validate_sha256(s: str | None) -> None:
    """Raise ValueError if s is not a valid 64-char lowercase hex sha256.
    Callers that permit None should check for that separately before calling.

    V3 v2 Step 2-bis — also reject trivial single-character fills
    (`"0"*64`, `"f"*64`, any repeat of one hex char). These pass the
    format regex but are obvious placeholder fabrications; the
    2026-04-19 matrix run caught Codex gpt-5.4 landing 3 rows with
    source_sha256="0"*64 because it couldn't compute a real hash at
    persona-level-1 and the format-only check let the bypass through.
    The downstream gate classifies these as `E_SHA256_TRIVIAL`.
    """
    if not isinstance(s, str) or not _SHA256_RE.match(s):
        raise ValueError(
            f"source_ref.sha256 must be a 64-char lowercase hex SHA-256 digest; "
            f"got {(s[:16] + '…') if isinstance(s, str) and len(s) > 16 else s!r} "
            f"(len={len(s) if isinstance(s, str) else 'n/a'})"
        )
    # Trivial single-char fill — E_SHA256_TRIVIAL per spec §2 Q2.
    if len(set(s)) == 1:
        raise ValueError(
            f"source_ref.sha256 is a trivial placeholder ({s[:8]}…×{len(s)//8}); "
            f"compute the real digest or omit sha256 so the server can auto-populate "
            f"via the Read-tool whitelist (E_SHA256_TRIVIAL)"
        )


def _validate_chat_id(chat_id: str) -> None:
    """Reject chat_ids not present in the `chats` table. Closes the Codex
    mis-attribution path where the model fabricates 'default' or any other
    non-existent chat_id and the row lands unreachable."""
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError("chat_id must be a non-empty string")
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM chats WHERE id = ? LIMIT 1", (chat_id,)
        ).fetchone()
    if row is None:
        raise ValueError(
            f"unknown chat_id: {chat_id!r} (not present in chats table). "
            f"Populate chat_id from the host audit context; do not invent."
        )


def _uuid7() -> str:
    return str(uuid.uuid7())


def _byte_range(src: dict) -> tuple[int | None, int | None]:
    br = src.get("byte_range")
    if isinstance(br, list) and len(br) == 2:
        return int(br[0]), int(br[1])
    return None, None


# --- V3 v2 Step 2 — server-side sha256 auto-provenance --------------------

# Whitelist (after realpath). Narrower than /Users/dana/ — that would cover
# Keychain, iMessage DB, Downloads, etc. See v2_spec.md §2 Step 2 (c).
_AUTOPROV_ALLOWED_PREFIXES = (
    "/Users/dana/.openclaw/",
    "/private/tmp/",        # realpath of /tmp/
)
# Reject-list substrings checked against realpath. Defense in depth: even a
# whitelisted prefix doesn't let the model hash cert material, .env secrets,
# or the live SQLite DBs (which would leak writer-activity timing).
_AUTOPROV_REJECT_SUBSTRINGS = (
    "/state/ssl/",
    "/apex/state/",
)
_AUTOPROV_MAX_BYTES = 1024 * 1024        # 1 MB hard cap on byte_range size
_AUTOPROV_ALLOWED_TOOLS = ("Read",)      # extend cautiously; each tool adds
                                         # semantics we must vouch for.


def _autoprovenance(tool: str | None, path: str | None,
                    byte_range: tuple[int | None, int | None]) -> str | None:
    """V3 v2 Step 2 — compute sha256 of the bytes at (path, byte_range) when
    the model supplies tool+path+byte_range for a tool_result claim but omits
    sha256. Fail-closed: returns None (caller raises) whenever any precondition
    isn't met. This closes the 'models cannot compute hashes at persona level
    1' constraint surfaced in v1.

    Honest weakening (named in spec §2 Step 2 (b)): bytes are re-read at
    assert time, not captured from the originating tool_use. If the file
    mutated between the tool_use and the claim_assert call, the hash reflects
    current state. Collision window is typically <1s in practice.

    Kill switch: APEX_AUTOPROVENANCE_DISABLE=1 short-circuits to None.
    """
    if os.environ.get("APEX_AUTOPROVENANCE_DISABLE") == "1":
        return None
    t0 = time.monotonic()
    ok = False
    real = ""
    n_bytes = 0
    err: str | None = None
    try:
        if tool not in _AUTOPROV_ALLOWED_TOOLS:
            err = f"tool {tool!r} not in {_AUTOPROV_ALLOWED_TOOLS}"
            return None
        if not isinstance(path, str) or not path:
            err = "path missing"
            return None
        if ".." in path.split(os.sep):
            err = "path contains .. segment (pre-realpath)"
            return None
        lo, hi = byte_range
        if lo is None or hi is None:
            err = "byte_range missing"
            return None
        if hi <= lo:
            err = f"byte_range empty or reversed: [{lo},{hi})"
            return None
        if (hi - lo) > _AUTOPROV_MAX_BYTES:
            err = f"byte_range too large: {hi - lo} > {_AUTOPROV_MAX_BYTES}"
            return None
        real = os.path.realpath(path)
        if not any(real.startswith(p) for p in _AUTOPROV_ALLOWED_PREFIXES):
            err = f"path outside whitelist: {real!r}"
            return None
        if any(sub in real for sub in _AUTOPROV_REJECT_SUBSTRINGS):
            err = f"path matches reject-list: {real!r}"
            return None
        # Also reject trailing .env (secrets file convention)
        if real.endswith(".env") or "/.env/" in real or real.endswith("/.env"):
            err = f"path is .env (secret): {real!r}"
            return None
        if not os.path.exists(real):
            err = f"path does not exist: {real!r}"
            return None
        size = os.path.getsize(real)
        effective_hi = min(hi, size)
        if effective_hi <= lo:
            err = f"byte_range past EOF: lo={lo} size={size}"
            return None
        with open(real, "rb") as f:
            f.seek(lo)
            data = f.read(effective_hi - lo)
        n_bytes = len(data)
        digest = hashlib.sha256(data).hexdigest()
        ok = True
        return digest
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        return None
    finally:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        path_sha = hashlib.sha256((real or path or "").encode("utf-8")).hexdigest()[:8]
        _log(
            f"AUTOPROV tool={tool} path_sha={path_sha} bytes={n_bytes} "
            f"ms={elapsed_ms:.1f} ok={ok}"
            + (f" err={err}" if err else "")
        )


# --- Tool executors ---------------------------------------------------------

def _tool_claim_assert(args: dict) -> dict:
    # V3 v2 Step 1a — APEX_CHAT_ID env var is the authoritative chat_id
    # when present (set per-chat by streaming._inject_claim_store_mcp).
    # Overwrite semantics: a confused or adversarial model cannot cross-
    # chat-spoof by emitting a different chat_id in tool args. Falls
    # through to model-supplied chat_id if env is unset (static-config
    # path, pre-migration dev) so _validate_chat_id still catches fakes.
    _env_chat_id = os.environ.get("APEX_CHAT_ID")
    if _env_chat_id:
        args["chat_id"] = _env_chat_id
    chat_id = args["chat_id"]
    turn_id = int(args["turn_id"])
    text = args["text"]
    confidence = float(args.get("confidence", 0.5))
    source_type = args["source_type"]
    if source_type not in _SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {_SOURCE_TYPES}; got {source_type!r}")
    src = args.get("source_ref") or {}

    # V3 v2 Step 3 — resource_type is the 16th L1 field (Room E §DELTA-E.5, C14).
    # Validated at assert, frozen thereafter (revise may not mutate).
    # Back-compat: when the caller omits resource_type and source_type='tool_result',
    # default to 'TOOL' so pre-Step-3 callers still work. Other source_types MUST
    # supply resource_type explicitly — the server does not guess PROMPT vs ENV vs
    # MEMORY for prior_turn / speculation / user claims.
    resource_type = args.get("resource_type")
    if resource_type is None:
        if source_type == "tool_result":
            resource_type = "TOOL"
        else:
            raise ValueError(
                f"resource_type is required when source_type={source_type!r} "
                f"(only source_type='tool_result' gets the 'TOOL' back-compat default). "
                f"Supply one of {_RESOURCE_TYPES}."
            )
    if resource_type not in _RESOURCE_TYPES:
        raise ValueError(
            f"resource_type must be one of {_RESOURCE_TYPES}; got {resource_type!r}"
        )

    # V3 Day 4.5 — server-side provenance guards.
    # (1) chat_id must resolve to a real chat row. Closes the Codex
    #     mis-attribution path (pre-Day 4 wrote 74 rows under 'default').
    _validate_chat_id(chat_id)

    # (2) source_type='tool_result' requires a validly-formatted sha256.
    #     The old guard was truthy-only (`if not sha256: raise`), which
    #     accepted any non-empty string — Day 2b's 62-char mnemonic digits
    #     passed. Now the format is validated.
    #
    # V3 v2 Step 2 — if sha256 is missing but tool+path+byte_range look
    # auto-hashable, compute the hash server-side. Fail-closed: if the
    # helper returns None (path outside whitelist, byte_range oversized,
    # file missing, kill switch engaged, etc.), we fall through to
    # _validate_sha256 which will reject the still-missing hash. The
    # intent is that the model supplies the provenance tuple and the
    # server supplies the hash; both are server-verified.
    if source_type == "tool_result":
        # V3 v2 Step 2-bis — verify-on-supplied.
        # Autoprovenance always fires when the (tool, path, byte_range)
        # tuple is hashable under the whitelist. If the model ALSO supplied
        # sha256, the two must match; mismatch is E_SHA256_MISMATCH per
        # spec §2 Q2. Closes the "supply plausible hex + never gets
        # checked" bypass.
        auto_sha = _autoprovenance(
            src.get("tool"),
            src.get("path"),
            _byte_range(src),
        )
        supplied = src.get("sha256")
        if auto_sha:
            if supplied and supplied != auto_sha:
                raise ValueError(
                    f"source_ref.sha256 mismatch: supplied={supplied[:16]}… "
                    f"server_computed={auto_sha[:16]}… "
                    f"(tool={src.get('tool')!r}, path={src.get('path')!r}) "
                    f"— omit sha256 to accept server computation, or recompute "
                    f"the real digest (E_SHA256_MISMATCH)"
                )
            src["sha256"] = auto_sha
        _validate_sha256(src.get("sha256"))

    # (3) source_type='prior_turn' had NO provenance guard. A model could
    #     write any claim by claiming "I said this earlier". Require at
    #     minimum source_tool + source_sha256 so the prior-turn assertion
    #     has a verifiable anchor.
    if source_type == "prior_turn":
        if not src.get("source_tool") and not src.get("tool"):
            raise ValueError(
                "source_type='prior_turn' requires source_ref.tool (the tool "
                "that produced the originally-grounding evidence)"
            )
        _validate_sha256(src.get("sha256"))

    claim_id = _uuid7()
    bl, bh = _byte_range(src)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO claims (
                claim_id, chat_id, turn_id, created_at, text, confidence,
                source_type, source_tool, source_path,
                source_byte_lo, source_byte_hi, source_sha256,
                resource_type, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active')""",
            (claim_id, chat_id, turn_id, _now_iso(), text, confidence,
             source_type, src.get("tool"), src.get("path"),
             bl, bh, src.get("sha256"), resource_type),
        )
    return {"claim_id": claim_id, "status": "active", "resource_type": resource_type}


def _tool_claim_list(args: dict) -> dict:
    chat_id = args["chat_id"]
    turn_id = args.get("turn_id")
    include_revised = bool(args.get("include_revised", False))
    q = "SELECT * FROM claims WHERE chat_id=?"
    params: list = [chat_id]
    if turn_id is not None:
        q += " AND turn_id=?"
        params.append(int(turn_id))
    if not include_revised:
        q += " AND status='active'"
    q += " ORDER BY turn_id ASC, claim_id ASC"
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return {"count": len(rows), "claims": rows}


def _tool_claim_revise(args: dict) -> dict:
    old_id = args["claim_id"]
    new_text = args["text"]
    new_conf = float(args.get("confidence", 0.5))
    new_stype = args.get("source_type")
    new_src = args.get("source_ref") or {}
    with _connect() as conn:
        old = conn.execute(
            "SELECT * FROM claims WHERE claim_id=?", (old_id,)
        ).fetchone()
        if not old:
            raise ValueError(f"claim_id not found: {old_id}")
        if old["status"] != "active":
            raise ValueError(f"claim {old_id} is {old['status']}, cannot revise")

        stype = new_stype or old["source_type"]
        if stype not in _SOURCE_TYPES:
            raise ValueError(f"source_type invalid: {stype!r}")

        # V3 v2 Step 3 — resource_type is frozen at assert (E_RESOURCE_TYPE_MUTATED).
        # Allowed: caller omits resource_type (carried forward), or supplies the
        # same value as the old row. If the old row's resource_type is NULL
        # (pre-Step-3 row created before this column was populated), allow the
        # revision to set it once — a one-time backfill path, not a mutation.
        old_rtype = old["resource_type"] if "resource_type" in old.keys() else None
        new_rtype = args.get("resource_type")
        if new_rtype is not None:
            if new_rtype not in _RESOURCE_TYPES:
                raise ValueError(
                    f"resource_type must be one of {_RESOURCE_TYPES}; got {new_rtype!r}"
                )
            if old_rtype is not None and new_rtype != old_rtype:
                raise ValueError(
                    f"resource_type is frozen at assert: old={old_rtype!r} "
                    f"new={new_rtype!r} (E_RESOURCE_TYPE_MUTATED). To correct a "
                    f"mis-typed claim, withdraw it and assert a new one."
                )
            effective_rtype = new_rtype
        else:
            effective_rtype = old_rtype
        # V3 Day 4.5 — same format guards as claim_assert.
        # V3 v2 Step 2 — auto-provenance applies to revise too. If the
        # revision supplies a new (tool, path, byte_range) but no sha256,
        # compute server-side. If the revision omits all provenance, fall
        # through to the old row's sha256 (Day 4.5 behavior).
        if stype == "tool_result":
            effective_sha = new_src.get("sha256") or old["source_sha256"]
            if not effective_sha and new_src.get("path"):
                auto_sha = _autoprovenance(
                    new_src.get("tool") or old["source_tool"],
                    new_src.get("path"),
                    _byte_range(new_src),
                )
                if auto_sha:
                    new_src["sha256"] = auto_sha
                    effective_sha = auto_sha
            _validate_sha256(effective_sha)
        if stype == "prior_turn":
            _validate_sha256(new_src.get("sha256") or old["source_sha256"])

        bl, bh = _byte_range(new_src)
        new_id = _uuid7()
        now = _now_iso()
        conn.execute(
            """INSERT INTO claims (
                claim_id, chat_id, turn_id, created_at, text, confidence,
                source_type, source_tool, source_path,
                source_byte_lo, source_byte_hi, source_sha256,
                resource_type, status, supersedes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?)""",
            (new_id, old["chat_id"], old["turn_id"], now, new_text, new_conf,
             stype,
             new_src.get("tool") or old["source_tool"],
             new_src.get("path") or old["source_path"],
             bl if bl is not None else old["source_byte_lo"],
             bh if bh is not None else old["source_byte_hi"],
             new_src.get("sha256") or old["source_sha256"],
             effective_rtype,
             old_id),
        )
        conn.execute(
            "UPDATE claims SET status='revised', revised_at=?, superseded_by=? WHERE claim_id=?",
            (now, new_id, old_id),
        )
    return {"old_claim_id": old_id, "new_claim_id": new_id, "status": "revised"}


# --- Tool schemas -----------------------------------------------------------

_SRC_REF_SCHEMA = {
    "type": "object",
    "description": (
        "Provenance reference. When source_type='tool_result', sha256 is verified. "
        "If sha256 is OMITTED and you supply tool+path+byte_range for an allowed "
        "tool (currently only 'Read') pointing at a file inside the server's "
        "whitelist, the server will compute sha256 on your behalf — this is the "
        "recommended path (you are NOT expected to compute hashes yourself). "
        "If sha256 is SUPPLIED, it must be a 64-char lowercase hex digest and "
        "will be accepted as-is (not re-verified against path bytes)."
    ),
    "properties": {
        "tool": {"type": "string", "description": "Tool name that produced the source (e.g. 'Read')."},
        "path": {"type": "string", "description": "File path of the source (absolute or relative to an allowed prefix)."},
        "byte_range": {
            "type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
            "description": "[lo, hi) byte range within the source. Required for server-side auto-hash; max range size 1MB.",
        },
        "sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": (
                "64-char lowercase hex SHA-256 of the source content. Optional "
                "when tool+path+byte_range are supplied and path is server-hashable "
                "(the server will compute and fill it in). Required otherwise."
            ),
        },
    },
}

_TOOLS = {
    "claim_assert": {
        "description": (
            "Register a factual claim with source provenance. Call BEFORE emitting prose "
            "that relies on this fact.\n\n"
            "REQUIRED fields: chat_id, turn_id, text, source_type.\n"
            "When source_type='tool_result', source_ref.sha256 is ALSO REQUIRED and "
            "MUST be a real 64-char lowercase hex SHA-256 digest of the tool_result "
            "content (do not invent or mnemonic-pattern it — the server rejects calls "
            "lacking sha256; the row will not persist).\n\n"
            "Example call shape (all fields real, not placeholders):\n"
            "  {\n"
            "    \"chat_id\": \"<the current apex chat_id, populated by the host>\",\n"
            "    \"turn_id\": 1,\n"
            "    \"text\": \"symbol_monitor.py line 240 sets protocolVersion='2024-11-05'\",\n"
            "    \"confidence\": 0.9,\n"
            "    \"source_type\": \"tool_result\",\n"
            "    \"source_ref\": {\n"
            "      \"tool\": \"Read\",\n"
            "      \"path\": \"/abs/path/symbol_monitor.py\",\n"
            "      \"byte_range\": [7620, 7680],\n"
            "      \"sha256\": \"d1ae7b2f1cc343f4d573bdf499c6e9d92844d03bcb5590236d0f4cd446338f57\"\n"
            "    }\n"
            "  }\n"
            "Do not guess sha256. Compute it from the exact bytes returned by the tool "
            "call you are grounding against. If sha256 is unavailable, either use "
            "source_type='speculation' (marks the claim as unverified — honest) or "
            "omit the claim_assert call entirely. Do not fabricate a hash to satisfy "
            "the schema — the server rejects non-64-char-hex strings and the row will "
            "not persist."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["chat_id", "turn_id", "text", "source_type"],
            "properties": {
                "chat_id": {"type": "string"},
                "turn_id": {"type": "integer"},
                "text": {"type": "string", "description": "The claim as a single prose sentence."},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "source_type": {"type": "string", "enum": list(_SOURCE_TYPES)},
                "source_ref": _SRC_REF_SCHEMA,
                "resource_type": {
                    "type": "string",
                    "enum": list(_RESOURCE_TYPES),
                    "description": (
                        "What kind of resource the claim is about, per V3 spec Room E §DELTA-E.5. "
                        "PROMPT = instruction/system-prompt text; AGENT = another agent's output; "
                        "TOOL = tool_result bytes (file, API, shell); ENV = environment observation "
                        "(pid, port, hostname, clock); MEMORY = persistent store (DB row, memory "
                        "blob, chatmine). Frozen at assert — claim_revise will reject any change. "
                        "Default when omitted: 'TOOL' if source_type='tool_result', else REQUIRED."
                    ),
                },
            },
        },
        "executor": _tool_claim_assert,
    },
    "claim_list": {
        "description": "List claims for a chat (and optionally a turn). Returns active claims by default.",
        "inputSchema": {
            "type": "object",
            "required": ["chat_id"],
            "properties": {
                "chat_id": {"type": "string"},
                "turn_id": {"type": "integer"},
                "include_revised": {"type": "boolean"},
            },
        },
        "executor": _tool_claim_list,
    },
    "claim_revise": {
        "description": (
            "Revise an existing active claim. Append-only: creates a new row, marks "
            "old as 'revised', links via supersedes/superseded_by."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["claim_id", "text"],
            "properties": {
                "claim_id": {"type": "string"},
                "text": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "source_type": {"type": "string", "enum": list(_SOURCE_TYPES)},
                "source_ref": _SRC_REF_SCHEMA,
                "resource_type": {
                    "type": "string",
                    "enum": list(_RESOURCE_TYPES),
                    "description": (
                        "Frozen at original assert — pass only if matching the old row "
                        "(or if old row predates Step 3 and has no resource_type set, in "
                        "which case this is a one-time backfill). Any mismatch raises "
                        "E_RESOURCE_TYPE_MUTATED."
                    ),
                },
            },
        },
        "executor": _tool_claim_revise,
    },
}


# --- JSON-RPC stdio loop ----------------------------------------------------

def _handle(req: dict) -> dict | None:
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "apex-claim-store", "version": "0.1.0"},
        }}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [
                {"name": n, "description": t["description"], "inputSchema": t["inputSchema"]}
                for n, t in _TOOLS.items()
            ],
        }}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = _TOOLS.get(name)
        if not tool:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        try:
            result = tool["executor"](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": False,
            }}
        except Exception as e:
            _log(f"{name} failed: {e}")
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                "isError": True,
            }}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main() -> None:
    _log(f"starting, db={_db_path()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"bad json: {e}")
            continue
        resp = _handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
