"""Premium context extensions — group roster and agent resolution.

Extracted from context.py. Loaded by PremiumLoader at startup.
Exports get_group_roster_prompt() and resolve_group_agent().
"""
from __future__ import annotations

import re

from db import (
    _get_chat, _get_group_members, _get_messages, _get_chat_settings,
    SYSTEM_PROFILE_ID,
)
from context import _get_memory_prompt, _MENTION_RE
from state import _current_group_profile_id


def get_group_roster_prompt(chat_id: str, user_message: str = "") -> str:
    """Inject group roster context so the active agent knows who else is in the room."""
    chat = _get_chat(chat_id)
    if not chat or chat.get("type") != "group":
        return ""
    members = _get_group_members(chat_id)
    if not members:
        return ""

    active_profile_id = _current_group_profile_id.get("")
    lines = [
        "You are responding inside a multi-agent group channel.",
        "Channel roster:",
    ]
    for member in members:
        tags: list[str] = []
        if member.get("profile_id") == active_profile_id:
            tags.append("you")
        if member.get("is_primary"):
            tags.append("primary")
        tag_text = f" ({', '.join(tags)})" if tags else ""
        avatar = f" {member.get('avatar', '')}" if member.get("avatar") else ""
        lines.append(f"- {member.get('name', member.get('profile_id', 'agent'))} [{member.get('profile_id', '')}]{avatar}{tag_text}")
    lines.append("Only speak as yourself. Other agents may read the shared chat history, but they do not receive your private hidden thinking.")
    lines.append("If the user addresses another agent, do not impersonate them.")

    memory_prompt = _get_memory_prompt(chat_id, active_profile_id=active_profile_id, limit=30, user_message=user_message)
    if memory_prompt:
        memory_body = memory_prompt.strip()
        if memory_body.startswith("<system-reminder>") and memory_body.endswith("</system-reminder>"):
            memory_body = memory_body[len("<system-reminder>"): -len("</system-reminder>")].strip()
        if memory_body:
            lines.append("")
            lines.extend(memory_body.splitlines())

    try:
        recent = _get_messages(chat_id, limit=20)["messages"]
        recent = recent[-20:]
        if recent:
            lines.append("")
            lines.append("## Recent Group History (last {} messages)".format(len(recent)))
            for m in recent:
                speaker = m.get("speaker_name") or m.get("role", "user")
                raw = m.get("content") or ""
                content = raw[:1200] + ("..." if len(raw) > 1200 else "")
                lines.append(f"[{speaker}]: {content}")
    except Exception:
        pass

    return "<system-reminder>\n# Group Channel Roster\n" + "\n".join(lines) + "\n</system-reminder>\n\n"


def resolve_group_agent(chat_id: str, chat: dict, prompt: str) -> dict | None:
    """For group chats, parse @mentions and resolve the target agent."""
    if chat.get("type") != "group":
        return None

    members = _get_group_members(chat_id)
    if not members:
        return None

    mentions = _MENTION_RE.findall(prompt)

    # @all / @channel → expand to all member names so multi-dispatch picks them up
    broadcast_keywords = {"all", "channel", "everyone"}
    if any(m.lower() in broadcast_keywords for m in mentions):
        mentions = [m["name"] for m in members]

    target = None
    if mentions:
        for mention in mentions:
            mention_lower = mention.lower()
            for m in members:
                if m["name"].lower() == mention_lower or m["profile_id"].lower() == mention_lower:
                    target = m
                    break
            if target:
                break

    if not target:
        for m in members:
            if m["is_primary"]:
                target = m
                break
        if not target and members:
            target = members[0]

    if not target:
        return None

    clean_prompt = prompt
    if mentions and target:
        clean_prompt = re.sub(
            rf"@{re.escape(target['name'])}|@{re.escape(target['profile_id'])}",
            "", prompt, count=1, flags=re.IGNORECASE
        ).strip()
        if not clean_prompt:
            clean_prompt = prompt

    return {
        "profile_id": target["profile_id"],
        "name": target["name"],
        "avatar": target["avatar"],
        "model": target["model"],
        "backend": target["backend"],
        "clean_prompt": clean_prompt,
    }
