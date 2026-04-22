"""Regression tests for group_coordinator strict-relay self-pass bug.

Symptom (witnessed chat 9cdffa31 on 2026-04-22):
    Each persona in a strict-sequential room fired 2–3 consecutive
    messages — substantive, then one-or-more "[PASS] @Next" — before
    the rotation finally advanced to the next speaker. Root cause:
    when `_build_group_relay_plan` saw no valid @next-speaker mention
    in the sender's response, it populated
    `strict_relay_feedback_prompt` which coerced the SAME sender to
    re-emit. Each re-emission persisted as a top-level assistant
    message, re-entering the code path with feedback-depth reset to
    zero → unbounded coercion loop until the LLM happened to emit a
    clean @mention.

Fix (applied 2026-04-22):
    In sequential mode, when `strict_actions` is empty AND the
    rotation pointer (`strict_relay.next_profile_id`) is already
    advanced past the sender, synthesize a single relay action
    targeting `next_profile_id` instead of coercing the sender to
    re-speak. Hub-spoke mode retains feedback coercion (its state
    machine depends on hub @-mention parsing).
"""
from __future__ import annotations

import pytest


def _install_fakes(monkeypatch, *, chat_settings: dict, members: list[dict]) -> None:
    """Monkeypatch db dependencies inside group_coordinator."""
    import group_coordinator as gc

    store: dict[str, dict] = {"chat": dict(chat_settings)}

    def fake_get_chat_settings(_chat_id):
        return dict(store["chat"])

    def fake_update_chat_settings(_chat_id, patch):
        store["chat"].update(patch)

    def fake_get_group_members(_chat_id):
        return [dict(m) for m in members]

    monkeypatch.setattr(gc, "_get_chat_settings", fake_get_chat_settings)
    monkeypatch.setattr(gc, "_update_chat_settings", fake_update_chat_settings)
    monkeypatch.setattr(gc, "_get_group_members", fake_get_group_members)


def _three_member_chat(monkeypatch, *, coord_protocol: str = "sequential") -> list[dict]:
    """Seed a strict-relay-active chat with Interviewer→Mira→Cass rotation.

    After the fixture runs, a subsequent call to _advance_strict_group_relay
    with sender=Interviewer should advance completed_profile_ids=['int'] and
    next_profile_id='mira'.
    """
    members = [
        {"profile_id": "int",  "name": "Interviewer", "avatar": "I", "is_primary": True,  "display_order": 0},
        {"profile_id": "mira", "name": "Mira",        "avatar": "M", "is_primary": False, "display_order": 1},
        {"profile_id": "cass", "name": "Cass",        "avatar": "C", "is_primary": False, "display_order": 2},
    ]
    chat_settings = {
        "coordination_protocol": coord_protocol,
        "agent_mentions_enabled": True,
        "max_relay_rounds": 6,
        "strict_relay": {
            "active": True,
            "ordered_profile_ids": ["int", "mira", "cass"],
            "completed_profile_ids": [],
            "round_number": 1,
            "round_abstentions": [],
        },
    }
    _install_fakes(monkeypatch, chat_settings=chat_settings, members=members)
    return members


def test_strict_sequential_synthesizes_relay_to_next_when_sender_omits_mention(monkeypatch):
    """The self-pass bug: sender emits substantive content with no @mention.

    Expected new behavior — a single synthesized relay action targets
    the next member in rotation (Mira), and NO strict feedback prompt
    is produced that would coerce the sender (Interviewer) to re-emit.
    """
    import group_coordinator as gc

    members = _three_member_chat(monkeypatch)
    interviewer = members[0]

    plan = gc._build_group_relay_plan(
        chat_id="test-chat",
        response_text="Substantive turn content with no at-mention at all.",
        group_agent=interviewer,
        mention_chain=[],
        mention_depth=0,
        max_mention_depth=5,
        premium_relay=None,
    )

    # Rotation advanced: Interviewer completed, Mira is next.
    assert plan.strict_relay.active is True
    assert plan.strict_relay.next_profile_id == "mira"
    assert "int" in plan.strict_relay.completed_profile_ids

    # Synthesis: exactly one relay action targeting Mira.
    actions = plan.relay.get("actions") or []
    assert len(actions) == 1, f"expected 1 synthesized relay action, got {actions!r}"
    action = actions[0]
    assert action["type"] == "relay"
    assert str(action["target"]["profile_id"]) == "mira"

    # No sender-coercion feedback.
    assert plan.strict_relay_feedback_prompt == ""
    assert plan.actionable_relay_actions == actions


def test_strict_sequential_preserves_valid_sender_mention(monkeypatch):
    """Regression guard: when sender DOES mention next speaker cleanly,
    the existing relay action is kept (not replaced by synthesis) so the
    sender's handoff prompt content flows through to the target."""
    import group_coordinator as gc

    members = _three_member_chat(monkeypatch)
    interviewer = members[0]

    plan = gc._build_group_relay_plan(
        chat_id="test-chat",
        response_text="Question for you. @Mira pick (a) or (b).",
        group_agent=interviewer,
        mention_chain=[],
        mention_depth=0,
        max_mention_depth=5,
        premium_relay=None,
    )

    actions = plan.relay.get("actions") or []
    assert len(actions) == 1
    assert str(actions[0]["target"]["profile_id"]) == "mira"
    # Fallback built from explicit @-mention parse, not synthesis.
    assert "@Mira" in str(actions[0].get("prompt") or "")
    assert plan.strict_relay_feedback_prompt == ""


def test_hub_spoke_still_uses_feedback_coercion(monkeypatch):
    """Hub-spoke mode must NOT get the sequential synthesis — its state
    machine depends on the hub's explicit @-mention to choose next spoke.
    Dropping feedback coercion here would break the hub-spoke dispatch."""
    import group_coordinator as gc

    members = [
        {"profile_id": "hub",  "name": "Coord", "avatar": "H", "is_primary": True,  "display_order": 0},
        {"profile_id": "dev",  "name": "Dev",   "avatar": "D", "is_primary": False, "display_order": 1},
        {"profile_id": "qa",   "name": "QA",    "avatar": "Q", "is_primary": False, "display_order": 2},
    ]
    chat_settings = {
        "coordination_protocol": "hub_spoke",
        "hub_profile_id": "hub",
        "agent_mentions_enabled": True,
        "max_relay_rounds": 6,
        "strict_relay": {
            "active": True,
            "mode": "hub_spoke",
            "ordered_profile_ids": ["hub"],
            "completed_profile_ids": [],
            "round_number": 1,
            "round_abstentions": [],
        },
    }
    _install_fakes(monkeypatch, chat_settings=chat_settings, members=members)

    hub = members[0]
    plan = gc._build_group_relay_plan(
        chat_id="test-chat-hub",
        response_text="Hub turn with no at-mention.",
        group_agent=hub,
        mention_chain=[],
        mention_depth=0,
        max_mention_depth=5,
        premium_relay=None,
    )

    # Hub-spoke: no synthesis, feedback path still lives (even if empty
    # text here; the important invariant is that we DIDN'T create a
    # sequential-style synthesized relay action).
    actions = plan.relay.get("actions") or []
    assert actions == [], f"hub-spoke should not synthesize sequential relay: {actions!r}"


def test_round_complete_does_not_synthesize(monkeypatch):
    """When the round completes (no next speaker), the synthesis branch
    must not fabricate a relay — `_advance_strict_group_relay` will have
    either started a new round OR cleared state, and either way the plan
    should reflect that honestly without a bogus synthesized action."""
    import group_coordinator as gc

    members = [
        {"profile_id": "int",  "name": "Interviewer", "avatar": "I", "is_primary": True,  "display_order": 0},
        {"profile_id": "mira", "name": "Mira",        "avatar": "M", "is_primary": False, "display_order": 1},
    ]
    # Seed state so this sender (Mira) is the LAST in rotation and both
    # are already completed by the time we advance.
    chat_settings = {
        "coordination_protocol": "sequential",
        "agent_mentions_enabled": True,
        "max_relay_rounds": 1,  # cap at 1 round so no new round auto-starts
        "strict_relay": {
            "active": True,
            "ordered_profile_ids": ["int", "mira"],
            "completed_profile_ids": ["int"],  # only Mira left
            "round_number": 1,
            "round_abstentions": [],
        },
    }
    _install_fakes(monkeypatch, chat_settings=chat_settings, members=members)

    mira = members[1]
    plan = gc._build_group_relay_plan(
        chat_id="test-chat-end",
        response_text="Final turn with no at-mention.",
        group_agent=mira,
        mention_chain=[],
        mention_depth=0,
        max_mention_depth=5,
        premium_relay=None,
    )

    # Round should have closed; rotation cleared.
    assert plan.strict_relay.active is False
    # No synthesized relay action — nothing to dispatch.
    actions = plan.relay.get("actions") or []
    assert actions == [], f"round close should not synthesize: {actions!r}"
