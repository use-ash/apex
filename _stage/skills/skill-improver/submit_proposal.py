#!/usr/bin/env python3
"""Submit an improvement proposal to the Ash gate for risk-tiered approval.

Usage:
    python3 submit_proposal.py <skill_name> <tier> <title> [--reason <reason>] [--workspace /path]

Writes a pending approval record to the gate system. Tier determines routing:
    - Tier 1: SKILL.md-only changes (auto-approved after review)
    - Tier 2: Script/code changes (requires explicit /approve)
    - Tier 3: New dependencies or external calls (requires review + testing)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _workspace() -> Path:
    return Path(os.environ.get("LOCALCHAT_WORKSPACE", os.getcwd()))


def _gate_pending_path(workspace: Path | None = None) -> Path:
    ws = workspace or _workspace()
    return ws / "skills" / "lib" / ".gate_pending.json"


def load_pending(workspace: Path | None = None) -> list[dict]:
    """Load current pending approvals."""
    path = _gate_pending_path(workspace)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def submit(
    skill: str,
    tier: int,
    title: str,
    reasons: list[str] | None = None,
    details: str = "",
    workspace: Path | None = None,
) -> dict:
    """Submit a new improvement proposal to the gate.

    Returns the approval record (with message_id for /approve reference).
    """
    ws = workspace or _workspace()
    pending = load_pending(ws)

    record = {
        "message_id": str(uuid.uuid4())[:8],
        "type": "improvement_proposal",
        "skill": skill,
        "tier": tier,
        "title": title,
        "reasons": reasons or [],
        "details": details[:500],
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }

    # Tier 1: auto-approve (SKILL.md-only changes, low risk)
    if tier <= 1:
        record["status"] = "auto_approved"
        record["resolved_at"] = record["ts"]

    pending.append(record)

    path = _gate_pending_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, indent=2))

    return record


def main():
    parser = argparse.ArgumentParser(description="Submit improvement proposal to gate")
    parser.add_argument("skill", help="Target skill name")
    parser.add_argument("tier", type=int, choices=[1, 2, 3], help="Risk tier (1=low, 2=medium, 3=high)")
    parser.add_argument("title", help="Short description of the proposed change")
    parser.add_argument("--reason", action="append", default=[], help="Risk reason (repeatable)")
    parser.add_argument("--details", default="", help="Detailed description or diff summary")
    parser.add_argument("--workspace", default=None, help="Workspace path override")
    args = parser.parse_args()

    ws = Path(args.workspace) if args.workspace else None
    record = submit(args.skill, args.tier, args.title, args.reason, args.details, ws)

    status = record["status"]
    mid = record["message_id"]
    if status == "auto_approved":
        print(f"✅ Auto-approved (tier {args.tier}): {args.title}")
    else:
        print(f"⏳ Pending approval [{mid}] (tier {args.tier}): {args.title}")
        print(f"   Approve with: /approve {mid}")

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
