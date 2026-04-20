"""Unit tests for server/streaming.py zombie-reload guard helpers.

Covers:
- _record_disconnect_mid_stream (new helper)
- _vacuum_dead_ws records mid-stream disconnect pre-discard

Fabricated from QA artifact (break/fix room chat ad8b6115, round 3).
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `from server import streaming` resolves
# when pytest is invoked from the apex/ dir.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from server import streaming
from server.streaming import (
    _vacuum_dead_ws,
    _record_disconnect_mid_stream,
)


class _FakeWS:
    """Minimal ws stand-in — identity via object id, hashable by default."""
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<FakeWS {self.name}>"


@pytest.fixture(autouse=True)
def _snapshot_streaming_dicts(monkeypatch):
    """Snapshot+restore all module-level dicts touched by these tests.

    Avoids bleed between tests and between this file and any other test that
    imports streaming.py at collection time.
    """
    monkeypatch.setattr(streaming, "_chat_ws", {}, raising=True)
    monkeypatch.setattr(streaming, "_ws_chat", {}, raising=True)
    monkeypatch.setattr(streaming, "_stream_attached_at_start", {}, raising=True)
    monkeypatch.setattr(streaming, "_stream_disconnected_during", {}, raising=True)
    yield


def test_vacuum_dead_ws_records_mid_stream_disconnect(monkeypatch):
    """Dead ws inside an active stream window must be recorded as mid-stream disconnect."""
    ws_a = _FakeWS("a")
    streaming._chat_ws["chat-x"] = {ws_a}
    streaming._ws_chat[ws_a] = "chat-x"
    streaming._stream_attached_at_start[("chat-x", "sid-1")] = {ws_a}

    # Stub liveness — ws_a is dead.
    monkeypatch.setattr(streaming, "_ws_is_alive", lambda w: False)

    discarded = _vacuum_dead_ws("chat-x")

    assert discarded == 1
    assert streaming._chat_ws.get("chat-x") is None
    assert streaming._ws_chat.get(ws_a) is None
    assert streaming._stream_disconnected_during[("chat-x", "sid-1")] == {ws_a}


def test_record_disconnect_noop_when_no_active_stream():
    """No active stream for chat — recording must not create spurious keys or raise."""
    ws_a = _FakeWS("a")
    # _stream_attached_at_start empty by autouse fixture.

    _record_disconnect_mid_stream(ws_a, "chat-x")  # must not raise

    assert streaming._stream_disconnected_during == {}


def test_record_disconnect_only_affects_matching_chat():
    """Ws in a DIFFERENT chat's active stream must not be recorded for chat-x."""
    ws_a = _FakeWS("a")
    streaming._stream_attached_at_start[("chat-y", "sid-other")] = {ws_a}

    _record_disconnect_mid_stream(ws_a, "chat-x")

    assert streaming._stream_disconnected_during == {}


def test_record_disconnect_ws_not_in_attached_set_is_noop():
    """Active stream exists for chat-x but ws_a was never attached — no record."""
    ws_a = _FakeWS("a")
    ws_b = _FakeWS("b")
    streaming._stream_attached_at_start[("chat-x", "sid-1")] = {ws_b}

    _record_disconnect_mid_stream(ws_a, "chat-x")

    assert streaming._stream_disconnected_during == {}
