"""Host-side group coordination helpers.

Keeps room-member parsing and relay/recovery planning out of ws_handler so
group orchestration can evolve into a first-class coordinator.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from db import (
    _get_chat_settings,
    _get_group_members,
    _is_known_profile_alias,
    _update_chat_settings,
)


_MAX_RELAY_ROUNDS = 10

_PASS_PATTERNS = (
    "[pass]",
    "[abstain]",
    "i have nothing to add",
    "nothing to add",
    "i'll pass",
    "i pass",
    "pass on this round",
)


@dataclass(frozen=True)
class GroupStrictRelayState:
    active: bool
    ordered_profile_ids: list[str]
    completed_profile_ids: list[str]
    next_profile_id: str
    next_target: dict | None
    round_number: int = 1
    round_abstentions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupRelayPlan:
    relay_members: list[dict]
    relay: dict
    broadcast_mention_present: bool
    missing_relay_mentions: list[str]
    explicit_relay_target_ids: set[str]
    explicit_relay_target_names: set[str]
    sender_profile_id: str
    actionable_relay_actions: list[dict]
    strict_relay: GroupStrictRelayState
    strict_relay_feedback_prompt: str
    strict_relay_feedback_message: str


_STRICT_RELAY_KEY = "strict_relay"


def _detect_agent_abstention(response_text: str) -> bool:
    """Check if an agent's response signals abstention (PASS)."""
    if not response_text:
        return False
    lowered = " ".join(response_text.casefold().split())
    # Short responses with pass patterns — don't match long substantive responses
    # that happen to contain "nothing to add" in a sentence
    if len(lowered) > 300:
        return False
    return any(pattern in lowered for pattern in _PASS_PATTERNS)


def _group_member_aliases(member: dict) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    candidates = [
        str(member.get("name") or "").strip(),
        str(member.get("profile_id") or "").strip(),
    ]
    profile_id = str(member.get("profile_id") or "").strip()
    if profile_id:
        candidates.append(re.sub(r"[-_]+", " ", profile_id).strip())
    for candidate in candidates:
        alias = " ".join(candidate.split())
        if not alias:
            continue
        folded = alias.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        aliases.append(alias)
    aliases.sort(key=len, reverse=True)
    return aliases


def _match_group_mention_prefix(text: str, alias: str) -> int:
    if not text or not alias:
        return 0
    prefix = f"@{alias}"
    if text[: len(prefix)].casefold() != prefix.casefold():
        return 0
    next_char = text[len(prefix): len(prefix) + 1]
    if next_char and not re.match(r"[\s:,.!?\-)\]}>*_`~\"]", next_char):
        return 0
    return len(prefix)


def _find_group_mention_matches(prompt: str, members: list[dict]) -> list[tuple[int, int, dict | None]]:
    matches: list[tuple[int, int, dict | None]] = []
    idx = 0
    while idx < len(prompt):
        at_pos = prompt.find("@", idx)
        if at_pos < 0:
            break
        prev_char = prompt[at_pos - 1: at_pos] if at_pos > 0 else ""
        if prev_char and re.match(r"[\w]", prev_char):
            idx = at_pos + 1
            continue
        text = prompt[at_pos:]
        matched_member: dict | None = None
        matched_len = _match_group_mention_prefix(text, "all")
        for member in members:
            for alias in _group_member_aliases(member):
                prefix_len = _match_group_mention_prefix(text, alias)
                if prefix_len > matched_len:
                    matched_member = member
                    matched_len = prefix_len
        if not matched_len:
            idx = at_pos + 1
            continue
        matches.append((at_pos, at_pos + matched_len, matched_member))
        idx = at_pos + matched_len
    return matches


def _find_invalid_group_mentions(prompt: str, members: list[dict]) -> list[str]:
    valid_matches = {
        start: end
        for start, end, _matched_member in _find_group_mention_matches(prompt, members)
    }
    invalid: list[str] = []
    seen: set[str] = set()
    idx = 0
    while idx < len(prompt):
        at_pos = prompt.find("@", idx)
        if at_pos < 0:
            break
        prev_char = prompt[at_pos - 1: at_pos] if at_pos > 0 else ""
        if prev_char and re.match(r"[\w]", prev_char):
            idx = at_pos + 1
            continue
        valid_end = valid_matches.get(at_pos)
        if valid_end:
            idx = valid_end
            continue
        text = prompt[at_pos + 1:]
        match = re.match(
            r"([A-Za-z0-9][A-Za-z0-9_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9_-]*){0,4})",
            text,
        )
        if not match:
            idx = at_pos + 1
            continue
        candidate = " ".join(match.group(1).split()).strip()
        folded = candidate.casefold()
        if (
            candidate
            and folded != "all"
            and folded not in seen
            and _is_known_profile_alias(candidate)
        ):
            seen.add(folded)
            invalid.append(candidate)
        idx = at_pos + 1 + len(match.group(1))
    return invalid


def _strip_group_leading_mentions(prompt: str, members: list[dict] | None = None) -> str:
    if not members:
        return prompt.strip()
    matches = _find_group_mention_matches(prompt, members)
    if not matches:
        return prompt.strip()
    parts: list[str] = []
    cursor = 0
    for start, end, _member in matches:
        parts.append(prompt[cursor:start])
        cursor = end
        while cursor < len(prompt) and prompt[cursor] in " \t:,.!?-":
            cursor += 1
    parts.append(prompt[cursor:])
    stripped = "".join(parts)
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return stripped.strip()


def _find_group_mentioned_members(prompt: str, members: list[dict]) -> list[dict]:
    mentioned: list[dict] = []
    seen_profile_ids: set[str] = set()
    for _start, _end, matched_member in _find_group_mention_matches(prompt, members):
        if matched_member is None:
            for member in members:
                profile_id = str(member.get("profile_id") or "")
                if not profile_id or profile_id in seen_profile_ids:
                    continue
                seen_profile_ids.add(profile_id)
                mentioned.append(member)
            continue
        profile_id = str(matched_member.get("profile_id") or "")
        if profile_id and profile_id not in seen_profile_ids:
            seen_profile_ids.add(profile_id)
            mentioned.append(matched_member)
    return mentioned


def _find_specific_group_mentioned_members(prompt: str, members: list[dict]) -> list[dict]:
    mentioned: list[dict] = []
    seen_profile_ids: set[str] = set()
    for _start, _end, matched_member in _find_group_mention_matches(prompt, members):
        if matched_member is None:
            continue
        profile_id = str(matched_member.get("profile_id") or "")
        if profile_id and profile_id not in seen_profile_ids:
            seen_profile_ids.add(profile_id)
            mentioned.append(matched_member)
    return mentioned


def _has_group_broadcast_mention(prompt: str, members: list[dict]) -> bool:
    return any(
        matched_member is None
        for _start, _end, matched_member in _find_group_mention_matches(prompt, members)
    )


def _format_group_member_mentions(members: list[dict], *, exclude_profile_id: str = "") -> str:
    handles: list[str] = []
    seen: set[str] = set()
    for member in members:
        profile_id = str(member.get("profile_id") or "")
        if exclude_profile_id and profile_id == exclude_profile_id:
            continue
        name = str(member.get("name") or "").strip()
        if not name:
            continue
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        handles.append(f"@{name}")
    return ", ".join(handles)


def _member_profile_id_list(members: list[dict]) -> list[str]:
    return [
        str(member.get("profile_id") or "")
        for member in members
        if str(member.get("profile_id") or "")
    ]


def _strict_relay_member_eligible(member: dict) -> bool:
    profile_id = str(member.get("profile_id") or "")
    return bool(profile_id) and not profile_id.startswith("sys-")


def _member_map(members: list[dict]) -> dict[str, dict]:
    return {
        str(member.get("profile_id") or ""): member
        for member in members
        if str(member.get("profile_id") or "")
    }


def _normalize_profile_id_sequence(profile_ids: list[str], members: list[dict]) -> list[str]:
    eligible_members = [member for member in members if _strict_relay_member_eligible(member)]
    member_map = _member_map(eligible_members)
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_profile_id in profile_ids:
        profile_id = str(raw_profile_id or "")
        if not profile_id or profile_id not in member_map or profile_id in seen:
            continue
        seen.add(profile_id)
        ordered.append(profile_id)
    for profile_id in _member_profile_id_list(eligible_members):
        if profile_id in seen:
            continue
        seen.add(profile_id)
        ordered.append(profile_id)
    return ordered


def _rotate_profile_ids(profile_ids: list[str], first_profile_id: str) -> list[str]:
    if not first_profile_id or first_profile_id not in profile_ids:
        return list(profile_ids)
    start = profile_ids.index(first_profile_id)
    return list(profile_ids[start:]) + list(profile_ids[:start])


def _strict_relay_requested(prompt: str) -> bool:
    lowered = " ".join(str(prompt or "").casefold().split())
    if not lowered:
        return False
    has_once = (
        "exactly once" in lowered
        or "respond once each" in lowered
        or "all agents have spoken" in lowered
        or "until all agents have spoken" in lowered
    )
    has_handoff = (
        "relay" in lowered
        or "pass it off" in lowered
        or "pass the baton" in lowered
        or "hand off" in lowered
        or "handoff" in lowered
        or "@ mentioning the next agent" in lowered
        or "@mentioning the next agent" in lowered
    )
    return has_once and has_handoff


def _get_strict_relay_payload(chat_id: str) -> dict:
    payload = _get_chat_settings(chat_id).get(_STRICT_RELAY_KEY) or {}
    return payload if isinstance(payload, dict) else {}


def _set_strict_relay_payload(chat_id: str, payload: dict | None) -> None:
    _update_chat_settings(chat_id, {_STRICT_RELAY_KEY: payload or None})


def _start_strict_group_relay(chat_id: str, *, first_profile_id: str = "") -> GroupStrictRelayState:
    members = _get_group_members(chat_id)
    ordered_profile_ids = _normalize_profile_id_sequence([], members)
    ordered_profile_ids = _rotate_profile_ids(ordered_profile_ids, first_profile_id)
    payload = {
        "active": bool(len(ordered_profile_ids) > 1),
        "ordered_profile_ids": ordered_profile_ids,
        "completed_profile_ids": [],
        "round_number": 1,
        "round_abstentions": [],
    }
    _set_strict_relay_payload(chat_id, payload if payload["active"] else None)
    return _get_strict_group_relay_state(chat_id, members)


def _clear_strict_group_relay(chat_id: str) -> None:
    _set_strict_relay_payload(chat_id, None)


def _get_strict_group_relay_state(
    chat_id: str,
    members: list[dict] | None = None,
) -> GroupStrictRelayState:
    relay_members = list(members or _get_group_members(chat_id))
    member_map = _member_map(relay_members)
    payload = _get_strict_relay_payload(chat_id)
    if not payload.get("active"):
        return GroupStrictRelayState(False, [], [], "", None)
    ordered_profile_ids = _normalize_profile_id_sequence(
        list(payload.get("ordered_profile_ids") or []),
        relay_members,
    )
    completed_profile_ids = [
        profile_id
        for profile_id in list(payload.get("completed_profile_ids") or [])
        if profile_id in ordered_profile_ids
    ]
    round_number = int(payload.get("round_number") or 1)
    round_abstentions = tuple(
        pid for pid in list(payload.get("round_abstentions") or [])
        if pid in ordered_profile_ids
    )
    next_profile_id = next(
        (profile_id for profile_id in ordered_profile_ids if profile_id not in completed_profile_ids),
        "",
    )
    active = bool(next_profile_id)
    return GroupStrictRelayState(
        active=active,
        ordered_profile_ids=ordered_profile_ids,
        completed_profile_ids=completed_profile_ids,
        next_profile_id=next_profile_id,
        next_target=member_map.get(next_profile_id),
        round_number=round_number,
        round_abstentions=round_abstentions,
    )


def _advance_strict_group_relay(
    chat_id: str,
    sender_profile_id: str,
    members: list[dict] | None = None,
    *,
    abstained: bool = False,
) -> GroupStrictRelayState:
    state = _get_strict_group_relay_state(chat_id, members)
    if not state.active:
        return state
    completed_profile_ids = list(state.completed_profile_ids)
    round_abstentions = list(state.round_abstentions)
    if (
        sender_profile_id
        and sender_profile_id in state.ordered_profile_ids
        and sender_profile_id not in completed_profile_ids
    ):
        completed_profile_ids.append(sender_profile_id)
    if abstained and sender_profile_id and sender_profile_id not in round_abstentions:
        round_abstentions.append(sender_profile_id)
    next_profile_id = next(
        (profile_id for profile_id in state.ordered_profile_ids if profile_id not in completed_profile_ids),
        "",
    )
    if next_profile_id:
        # Round still in progress
        _set_strict_relay_payload(
            chat_id,
            {
                "active": True,
                "ordered_profile_ids": state.ordered_profile_ids,
                "completed_profile_ids": completed_profile_ids,
                "round_number": state.round_number,
                "round_abstentions": round_abstentions,
            },
        )
    else:
        # Round complete — check if we should wrap around
        coord_protocol = _get_chat_settings(chat_id).get("coordination_protocol", "freeform")
        all_abstained = set(round_abstentions) >= set(state.ordered_profile_ids)
        at_max_rounds = state.round_number >= _MAX_RELAY_ROUNDS
        if coord_protocol == "sequential" and not all_abstained and not at_max_rounds:
            # Start new round
            _set_strict_relay_payload(
                chat_id,
                {
                    "active": True,
                    "ordered_profile_ids": state.ordered_profile_ids,
                    "completed_profile_ids": [],
                    "round_number": state.round_number + 1,
                    "round_abstentions": [],
                },
            )
        else:
            _clear_strict_group_relay(chat_id)
    return _get_strict_group_relay_state(chat_id, members)


def _format_group_member_mentions_for_ids(members: list[dict], profile_ids: list[str]) -> str:
    member_map = _member_map(members)
    handles: list[str] = []
    for profile_id in profile_ids:
        member = member_map.get(profile_id)
        if not member:
            continue
        name = str(member.get("name") or "").strip()
        if name:
            handles.append(f"@{name}")
    return ", ".join(handles)


def _build_strict_group_relay_feedback_prompt(
    state: GroupStrictRelayState,
    members: list[dict],
    *,
    sender_name: str,
) -> str:
    next_target = state.next_target
    if not next_target:
        return (
            f"System feedback for @{sender_name}: The strict relay round is complete. "
            "Do not hand off to another agent."
        )
    completed = _format_group_member_mentions_for_ids(members, state.completed_profile_ids) or "none yet"
    remaining_profile_ids = [
        profile_id
        for profile_id in state.ordered_profile_ids
        if profile_id not in state.completed_profile_ids
    ]
    remaining = _format_group_member_mentions_for_ids(members, remaining_profile_ids) or "none"
    return (
        f"System feedback for @{sender_name}: Strict relay is active. "
        f"Agents already responded: {completed}. "
        f"Agents still pending: {remaining}. "
        f"Next agent to hand off to is @{next_target.get('name')}. "
        f"@mention exactly @{next_target.get('name')} and do not mention anyone else."
    )


def _build_strict_group_relay_feedback_message(state: GroupStrictRelayState) -> str:
    next_target = state.next_target
    if not next_target:
        return "Strict relay is complete. No further agents should be auto-invoked."
    return f"Strict relay is active. The next agent is @{next_target.get('name')}."


def _build_group_relay_state_prompt(chat_id: str) -> str:
    members = _get_group_members(chat_id)
    state = _get_strict_group_relay_state(chat_id, members)
    if not state.active:
        return ""
    completed = _format_group_member_mentions_for_ids(members, state.completed_profile_ids) or "none yet"
    remaining_profile_ids = [
        profile_id
        for profile_id in state.ordered_profile_ids
        if profile_id not in state.completed_profile_ids
    ]
    remaining = _format_group_member_mentions_for_ids(members, remaining_profile_ids) or "none"
    next_target = state.next_target
    next_line = (
        f"The next valid handoff target is @{next_target.get('name')}."
        if next_target
        else "The strict relay round is complete. Do not hand off again."
    )
    round_line = f"Round: {state.round_number}" if state.round_number > 1 else ""
    return (
        "<system-reminder>\n"
        "# Strict Relay\n"
        "A strict relay is active for this room.\n"
        + (f"{round_line}\n" if round_line else "")
        + f"Agents already responded this round: {completed}\n"
        f"Agents still pending: {remaining}\n"
        f"{next_line}\n"
        "Use this relay state as authoritative. If you hand off, @mention exactly one pending agent and do not use "
        "tools, files, SDK client counts, or inferred presence signals to determine room membership.\n"
        "If you have nothing meaningful to add this round, respond with just [PASS] to skip your turn.\n"
        "</system-reminder>\n\n"
    )


def _strict_group_relay_active(chat_id: str) -> bool:
    return _get_strict_group_relay_state(chat_id).active


def _resolve_group_agent_fallback(chat_id: str, prompt: str) -> dict | None:
    members = _get_group_members(chat_id)
    if not members:
        return None
    mentioned = _find_group_mentioned_members(prompt, members)
    if not mentioned:
        return None
    return {
        **mentioned[0],
        "clean_prompt": _strip_group_leading_mentions(prompt, members),
    }


def _get_multi_dispatch_targets_fallback(chat_id: str, prompt: str, group_agent: dict | None) -> list[dict]:
    if not group_agent:
        return []
    members = _get_group_members(chat_id)
    if not members:
        return []
    return _find_group_mentioned_members(prompt, members)


def _merge_group_dispatch_targets(*target_lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_profile_ids: set[str] = set()
    for target_list in target_lists:
        for target in target_list:
            profile_id = str(target.get("profile_id") or "")
            if not profile_id or profile_id in seen_profile_ids:
                continue
            seen_profile_ids.add(profile_id)
            merged.append(target)
    return merged


def _build_missing_group_mentions_message(
    missing_mentions: list[str],
    members: list[dict],
    *,
    sender_profile_id: str = "",
) -> str:
    available = _format_group_member_mentions(members, exclude_profile_id=sender_profile_id)
    if len(missing_mentions) == 1:
        message = f"@{missing_mentions[0]} isn't in this room."
    else:
        missing_list = ", ".join(f"@{name}" for name in missing_mentions)
        message = f"These agents aren't in this room: {missing_list}."
    if available:
        message = f"{message} Available agents: {available}."
    return message


def _build_missing_group_mentions_feedback_prompt(
    missing_mentions: list[str],
    members: list[dict],
    *,
    sender_name: str,
    sender_profile_id: str,
) -> str:
    base = _build_missing_group_mentions_message(
        missing_mentions,
        members,
        sender_profile_id=sender_profile_id,
    )
    return (
        f"System feedback for @{sender_name}: {base} "
        "Continue yourself or hand off to an agent who is present."
    )


def _response_indicates_group_roster_uncertainty(response_text: str) -> bool:
    lowered = " ".join(str(response_text or "").casefold().split())
    if not lowered:
        return False
    uncertainty_markers = (
        "unsure who is present",
        "don't know who is present",
        "do not know who is present",
        "don't know which other agents are present",
        "do not know which other agents are present",
        "room roster is not visible",
        "roster is not visible",
        "cannot see a live room roster",
        "can't see a live room roster",
        "cannot see the room roster",
        "can't see the room roster",
        "not able to see a room roster",
        "cannot identify who to @mention next",
        "cannot identify who to mention next",
    )
    return any(marker in lowered for marker in uncertainty_markers)


def _build_group_roster_feedback_prompt(
    members: list[dict],
    *,
    sender_name: str,
    sender_profile_id: str,
) -> str:
    available = _format_group_member_mentions(members, exclude_profile_id=sender_profile_id)
    if available:
        roster_line = f"The agents currently in this room are: {available}."
    else:
        roster_line = "You are the only agent currently in this room."
    return (
        f"System feedback for @{sender_name}: {roster_line} "
        "This roster is authoritative. Do not use tools, files, SDK client counts, or inferred presence signals "
        "to determine room membership. If you intend to hand off, @mention exactly one present agent from this "
        "roster. If no handoff is needed, continue yourself."
    )


def _strip_group_target_prefix(prompt: str, member: dict) -> str:
    text = prompt.lstrip()
    leading_ws = prompt[: len(prompt) - len(text)]
    for alias in _group_member_aliases(member):
        matched_len = _match_group_mention_prefix(text, alias)
        if not matched_len:
            continue
        stripped = text[matched_len:].lstrip(" \t:,.!?-")
        return f"{leading_ws}{stripped}".strip()
    return prompt


def _resolve_direct_group_agent(chat_id: str, prompt: str, target_profile_id: str) -> dict | None:
    for member in _get_group_members(chat_id):
        if str(member.get("profile_id") or "") != target_profile_id:
            continue
        return {**member, "clean_prompt": _strip_group_target_prefix(prompt, member)}
    return None


def _resolve_primary_group_agent(chat_id: str, prompt: str) -> dict | None:
    members = _get_group_members(chat_id)
    if not members:
        return None
    primary = next((m for m in members if m.get("is_primary")), members[0])
    return {**primary, "clean_prompt": prompt}


def _merge_relay_actions(*action_lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for action_list in action_lists:
        for action in action_list:
            action_type = str(action.get("type") or "")
            target = action.get("target") or {}
            target_profile_id = str(target.get("profile_id") or "")
            if action_type in {"relay", "redirect"}:
                key = (action_type, target_profile_id)
            elif action_type == "pair_blocked":
                key = (action_type, str(action.get("target_name") or ""))
            else:
                key = (action_type, str(action.get("reason") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(action)
    return merged


def _get_agent_relay_fallback(
    chat_id: str,
    response_text: str,
    group_agent: dict,
    mention_chain: list[str],
    mention_depth: int,
    *,
    max_mention_depth: int,
) -> dict:
    current_chain = list(mention_chain) + [str(group_agent.get("profile_id") or "")]
    mentions_enabled = bool(_get_chat_settings(chat_id).get("agent_mentions_enabled"))
    members = _get_group_members(chat_id)
    explicit_targets = _find_specific_group_mentioned_members(response_text, members)
    return {
        "mentioned_names": [str(member.get("name") or "") for member in explicit_targets],
        "mentions_enabled": mentions_enabled,
        "current_chain": current_chain,
        "actions": (
            [
                {
                    "type": "relay",
                    "target": member,
                    "prompt": response_text,
                    "depth": mention_depth + 1,
                }
                for member in explicit_targets
            ]
            if mentions_enabled and mention_depth < max_mention_depth
            else []
        ),
    }


def _build_group_relay_plan(
    chat_id: str,
    response_text: str,
    group_agent: dict,
    mention_chain: list[str],
    mention_depth: int,
    *,
    max_mention_depth: int,
    premium_relay: dict | None = None,
) -> GroupRelayPlan:
    relay_members = _get_group_members(chat_id)
    agent_abstained = _detect_agent_abstention(response_text)
    strict_relay = _advance_strict_group_relay(
        chat_id,
        str(group_agent.get("profile_id") or ""),
        relay_members,
        abstained=agent_abstained,
    )
    broadcast_mention_present = _has_group_broadcast_mention(response_text, relay_members)
    explicit_relay_targets = _find_specific_group_mentioned_members(response_text, relay_members)
    missing_relay_mentions = _find_invalid_group_mentions(response_text, relay_members)
    explicit_relay_target_ids = {
        str(member.get("profile_id") or "")
        for member in explicit_relay_targets
        if str(member.get("profile_id") or "")
    }
    explicit_relay_target_names = {
        str(member.get("name") or "")
        for member in explicit_relay_targets
        if str(member.get("name") or "")
    }
    fallback_relay = _get_agent_relay_fallback(
        chat_id,
        response_text,
        group_agent,
        mention_chain,
        mention_depth,
        max_mention_depth=max_mention_depth,
    )
    relay = fallback_relay
    if premium_relay:
        relay = {
            "mentioned_names": list(dict.fromkeys(
                list(premium_relay.get("mentioned_names") or [])
                + list(fallback_relay.get("mentioned_names") or [])
            )),
            "mentions_enabled": bool(
                premium_relay.get("mentions_enabled")
                or fallback_relay.get("mentions_enabled")
            ),
            "current_chain": list(
                premium_relay.get("current_chain")
                or fallback_relay.get("current_chain")
                or []
            ),
            "actions": _merge_relay_actions(
                list(premium_relay.get("actions") or []),
                list(fallback_relay.get("actions") or []),
            ),
        }
    if broadcast_mention_present:
        filtered_actions: list[dict] = []
        for action in relay.get("actions") or []:
            action_type = str(action.get("type") or "")
            if action_type in {"relay", "redirect"}:
                target = action.get("target") or {}
                target_profile_id = str(target.get("profile_id") or "")
                if target_profile_id and target_profile_id in explicit_relay_target_ids:
                    filtered_actions.append(action)
            elif action_type == "pair_blocked":
                target_name = str(action.get("target_name") or "")
                if target_name and target_name in explicit_relay_target_names:
                    filtered_actions.append(action)
        relay = {**relay, "actions": filtered_actions}
    strict_relay_feedback_prompt = ""
    strict_relay_feedback_message = ""
    if strict_relay.active and relay.get("mentions_enabled"):
        strict_target_profile_id = str(strict_relay.next_profile_id or "")
        strict_actions: list[dict] = []
        for action in relay.get("actions") or []:
            action_type = str(action.get("type") or "")
            if action_type not in {"relay", "redirect"}:
                continue
            target = action.get("target") or {}
            target_profile_id = str(target.get("profile_id") or "")
            if strict_target_profile_id and target_profile_id == strict_target_profile_id:
                strict_actions.append(action)
        relay = {**relay, "actions": strict_actions}
        if not strict_actions:
            strict_relay_feedback_prompt = _build_strict_group_relay_feedback_prompt(
                strict_relay,
                relay_members,
                sender_name=str(group_agent.get("name") or group_agent.get("profile_id") or "agent"),
            )
            strict_relay_feedback_message = _build_strict_group_relay_feedback_message(strict_relay)
    sender_profile_id = str(group_agent.get("profile_id") or "")
    actionable_relay_actions = [
        action
        for action in relay.get("actions") or []
        if action.get("type") in {"relay", "redirect"}
    ]
    return GroupRelayPlan(
        relay_members=relay_members,
        relay=relay,
        broadcast_mention_present=broadcast_mention_present,
        missing_relay_mentions=missing_relay_mentions,
        explicit_relay_target_ids=explicit_relay_target_ids,
        explicit_relay_target_names=explicit_relay_target_names,
        sender_profile_id=sender_profile_id,
        actionable_relay_actions=actionable_relay_actions,
        strict_relay=strict_relay,
        strict_relay_feedback_prompt=strict_relay_feedback_prompt,
        strict_relay_feedback_message=strict_relay_feedback_message,
    )
