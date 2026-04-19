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
"""
import json
import os
import sqlite3
import sys
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

# V3 Day 4.5 — compiled once for hot-path sha256 format check.
import re as _re
_SHA256_RE = _re.compile(r"^[0-9a-f]{64}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _validate_sha256(s: str | None) -> None:
    """Raise ValueError if s is not a valid 64-char lowercase hex sha256.
    Callers that permit None should check for that separately before calling.
    """
    if not isinstance(s, str) or not _SHA256_RE.match(s):
        raise ValueError(
            f"source_ref.sha256 must be a 64-char lowercase hex SHA-256 digest; "
            f"got {(s[:16] + '…') if isinstance(s, str) and len(s) > 16 else s!r} "
            f"(len={len(s) if isinstance(s, str) else 'n/a'})"
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


# --- Tool executors ---------------------------------------------------------

def _tool_claim_assert(args: dict) -> dict:
    chat_id = args["chat_id"]
    turn_id = int(args["turn_id"])
    text = args["text"]
    confidence = float(args.get("confidence", 0.5))
    source_type = args["source_type"]
    if source_type not in _SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {_SOURCE_TYPES}; got {source_type!r}")
    src = args.get("source_ref") or {}

    # V3 Day 4.5 — server-side provenance guards.
    # (1) chat_id must resolve to a real chat row. Closes the Codex
    #     mis-attribution path (pre-Day 4 wrote 74 rows under 'default').
    _validate_chat_id(chat_id)

    # (2) source_type='tool_result' requires a validly-formatted sha256.
    #     The old guard was truthy-only (`if not sha256: raise`), which
    #     accepted any non-empty string — Day 2b's 62-char mnemonic digits
    #     passed. Now the format is validated.
    if source_type == "tool_result":
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
                source_byte_lo, source_byte_hi, source_sha256, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'active')""",
            (claim_id, chat_id, turn_id, _now_iso(), text, confidence,
             source_type, src.get("tool"), src.get("path"),
             bl, bh, src.get("sha256")),
        )
    return {"claim_id": claim_id, "status": "active"}


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
        # V3 Day 4.5 — same format guards as claim_assert.
        if stype == "tool_result":
            _validate_sha256(new_src.get("sha256") or old["source_sha256"])
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
                status, supersedes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?)""",
            (new_id, old["chat_id"], old["turn_id"], now, new_text, new_conf,
             stype,
             new_src.get("tool") or old["source_tool"],
             new_src.get("path") or old["source_path"],
             bl if bl is not None else old["source_byte_lo"],
             bh if bh is not None else old["source_byte_hi"],
             new_src.get("sha256") or old["source_sha256"],
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
        "Provenance reference. When source_type='tool_result', sha256 is REQUIRED "
        "and MUST be a 64-char lowercase hex SHA-256 digest of the tool_result "
        "content the claim is grounded in. tool, path, byte_range are recommended."
    ),
    "properties": {
        "tool": {"type": "string", "description": "Tool name that produced the source (e.g. 'Read', 'Grep')."},
        "path": {"type": "string", "description": "File path or URI of the source."},
        "byte_range": {
            "type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
            "description": "[lo, hi) byte range within the source.",
        },
        "sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": "64-char lowercase hex SHA-256 of the source content. REQUIRED when source_type='tool_result'.",
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
