"""Premium WebSocket handler extensions — group routing + agent relay.

Extracted from ws_handler.py. Loaded by PremiumLoader at startup.
Exports pure-data functions — the host file handles asyncio tasks and WS sends.
"""
from __future__ import annotations

import re

from db import _get_group_members, _get_chat_settings
from model_dispatch import _get_model_backend
from context import _MENTION_RE

# Relay limits (moved from ws_handler.py — only relevant with premium groups)
MAX_MENTION_DEPTH = 25
MAX_PAIR_BACK_AND_FORTH = 4
OPERATIONS_NAMES = {"operations", "ops"}


def _count_pair_volleys(chain: list[str], agent_a: str, agent_b: str) -> int:
    """Count consecutive back-and-forth hops between the same two agents at the tail of the chain."""
    pair = {agent_a.lower(), agent_b.lower()}
    count = 0
    for i in range(len(chain) - 1, 0, -1):
        if {chain[i].lower(), chain[i - 1].lower()} == pair:
            count += 1
        else:
            break
    return count


def _find_operations_agent(members: list[dict]) -> dict | None:
    """Find the Operations agent in the group member list."""
    for m in members:
        if m["name"].lower() in OPERATIONS_NAMES or m["profile_id"].lower() in OPERATIONS_NAMES:
            return m
    return None


def resolve_target_agent(chat_id: str, prompt: str, target_profile_id: str) -> dict | None:
    """Resolve an explicit target_agent (from UI) to a group_agent dict.

    Returns the group_agent dict or None if the target is not a member.
    """
    members = _get_group_members(chat_id)
    for m in members:
        if m["profile_id"] == target_profile_id:
            clean = re.sub(
                rf"@{re.escape(m['name'])}|@{re.escape(m['profile_id'])}",
                "", prompt, count=1, flags=re.IGNORECASE
            ).strip() or prompt
            return {
                "profile_id": m["profile_id"],
                "name": m["name"],
                "avatar": m["avatar"],
                "model": m["model"],
                "backend": _get_model_backend(m["model"]),
                "clean_prompt": clean,
            }
    return None


def get_multi_dispatch_targets(chat_id: str, prompt: str, primary_agent: dict, data: dict) -> list[dict]:
    """For multi-@mention messages, return additional targets beyond the primary.

    Returns list of member dicts (with profile_id, name, avatar, etc.) for each
    additional agent that should receive the message. The caller creates asyncio
    tasks for each target.
    """
    if data.get("_source"):
        return []
    mentions = _MENTION_RE.findall(prompt)
    broadcast_keywords = {"all", "channel", "everyone"}
    members = _get_group_members(chat_id)
    if any(m.lower() in broadcast_keywords for m in mentions):
        mentions = [m["name"] for m in members]
    if len(mentions) <= 1:
        return []
    member_map = {m["name"].lower(): m for m in members}
    member_map.update({m["profile_id"].lower(): m for m in members})
    seen = {primary_agent["profile_id"]}
    targets = []
    for mname in mentions:
        t = member_map.get(mname.lower())
        if not t or t["profile_id"] in seen:
            continue
        seen.add(t["profile_id"])
        targets.append(t)
    return targets


def get_agent_relay_actions(
    chat_id: str,
    response_text: str,
    group_agent: dict,
    mention_chain: list[str],
    mention_depth: int,
) -> dict:
    """Determine relay actions from agent response @mentions.

    Returns a dict with:
        mentioned_names: list[str] — names found in response
        mentions_enabled: bool — whether settings allow relay
        current_chain: list[str] — updated relay chain
        actions: list[dict] — relay decisions for the host to execute

    Each action is one of:
        {"type": "relay", "target": member_dict, "prompt": str, "depth": int}
        {"type": "redirect", "target": member_dict, "prompt": str, "depth": int, "reason": str}
        {"type": "blocked", "reason": str}
        {"type": "pair_blocked", "agent_name": str, "target_name": str, "reason": str}
    """
    current_chain = mention_chain + [group_agent["profile_id"]]

    settings = _get_chat_settings(chat_id)
    mentions_enabled = settings.get("agent_mentions_enabled")
    mentioned_names = _MENTION_RE.findall(response_text) if mentions_enabled else []

    result = {
        "mentioned_names": mentioned_names,
        "mentions_enabled": mentions_enabled,
        "current_chain": current_chain,
        "actions": [],
    }

    if not mentions_enabled or not mentioned_names:
        return result

    members = _get_group_members(chat_id)
    member_map = {m["name"].lower(): m for m in members}
    member_map.update({m["profile_id"].lower(): m for m in members})

    # Depth ceiling: check once, redirect once, skip loop
    if mention_depth >= MAX_MENTION_DEPTH:
        reason = f"Relay depth limit ({MAX_MENTION_DEPTH}) reached"
        ops_agent = _find_operations_agent(members)
        if ops_agent and ops_agent["profile_id"] != group_agent["profile_id"]:
            result["actions"].append({
                "type": "redirect",
                "target": ops_agent,
                "prompt": (
                    f"[RELAY CONTROL] {reason}. "
                    f"The last exchange involved {group_agent['name']}. "
                    f"Review what the team was working on, realign on next steps, "
                    f"and decide who should act next."
                ),
                "depth": mention_depth + 1,
                "reason": reason,
            })
        else:
            result["actions"].append({"type": "blocked", "reason": reason})
        return result

    # Normal relay — dispatch to ALL valid mentioned targets
    seen: set[str] = set()
    for name in mentioned_names:
        target = member_map.get(name.lower())
        if not target or target["profile_id"] == group_agent["profile_id"]:
            continue
        if target["profile_id"] in seen:
            continue
        seen.add(target["profile_id"])

        pair_volleys = _count_pair_volleys(
            current_chain, group_agent["profile_id"], target["profile_id"]
        )
        if pair_volleys >= MAX_PAIR_BACK_AND_FORTH:
            result["actions"].append({
                "type": "pair_blocked",
                "agent_name": group_agent["name"],
                "target_name": target["name"],
                "reason": (
                    f"Back-and-forth limit ({MAX_PAIR_BACK_AND_FORTH}) reached "
                    f"between {group_agent['name']} and {target['name']}"
                ),
            })
            continue

        result["actions"].append({
            "type": "relay",
            "target": target,
            "prompt": response_text,
            "depth": mention_depth + 1,
        })

    return result
