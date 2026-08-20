"""Unit tests for server/streaming.py zombie-reload guard helpers.

Covers:
- _record_disconnect_mid_stream (new helper)
- _vacuum_dead_ws records mid-stream disconnect pre-discard
- cancel-save reconstructs Ollama thinking/tool events from the stream buffer

Fabricated from QA artifact (break/fix room chat ad8b6115, round 3).
"""
import asyncio
import contextlib
import json
import sys
import time
from collections import deque
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
    _partial_from_stream_payloads,
    _merge_cancel_partial,
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


def test_partial_from_stream_payloads_pairs_tools_and_thinking():
    payloads = [
        {"type": "stream_start"},
        {"type": "thinking", "text": "try yts then 1337x"},
        {"type": "thinking", "text": " still blocked"},
        {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "curl x"}},
        {"type": "tool_result", "tool_use_id": "t1", "content": "403", "is_error": False},
        {"type": "text", "text": "no listing yet"},
    ]
    partial = _partial_from_stream_payloads(payloads)
    assert partial["thinking"] == "try yts then 1337x still blocked"
    assert partial["text"] == "no listing yet"
    assert len(partial["tool_events"]) == 1
    assert partial["tool_events"][0]["name"] == "bash"
    assert partial["tool_events"][0]["result"]["content"] == "403"
    assert partial["tool_events"][0]["result"]["is_error"] is False


def test_partial_from_stream_payloads_keeps_unpaired_tool_use():
    payloads = [
        {"type": "tool_use", "id": "t9", "name": "execute_code", "input": {"code": "print(1)"}},
    ]
    partial = _partial_from_stream_payloads(payloads)
    assert partial["tool_events"][0]["name"] == "execute_code"
    assert "result" not in partial["tool_events"][0]


def test_partial_from_stream_payloads_filters_other_stream_id():
    payloads = [
        {"type": "thinking", "text": "keep", "stream_id": "sid-a"},
        {"type": "thinking", "text": "drop", "stream_id": "sid-b"},
        {"type": "tool_use", "id": "t1", "name": "bash", "input": {}, "stream_id": "sid-b"},
    ]
    partial = _partial_from_stream_payloads(payloads, stream_id="sid-a")
    assert partial["thinking"] == "keep"
    assert partial["tool_events"] == []


def test_merge_cancel_partial_fills_from_sdk():
    merged = _merge_cancel_partial(
        {"text": "", "thinking": "", "tool_events": []},
        {"text": "hello", "thinking": "why", "tool_events": [{"name": "x"}]},
    )
    assert merged["text"] == "hello"
    assert merged["thinking"] == "why"
    assert merged["tool_events"][0]["name"] == "x"


def test_cancel_saves_ollama_partial_without_sdk_client(monkeypatch):
    saved: dict = {}

    def fake_save(chat_id, role, content, **kwargs):
        saved.update({"chat_id": chat_id, "role": role, "content": content, **kwargs})
        return "mid"

    monkeypatch.setattr(streaming, "_save_message", fake_save)
    monkeypatch.setattr(streaming, "_active_send_tasks", {})
    monkeypatch.setattr(streaming, "_stream_buffers", {})
    monkeypatch.setattr(streaming, "_clients", {})
    monkeypatch.setattr(streaming, "_chat_ws", {})

    async def _run():
        async def sleeper():
            await asyncio.sleep(60)

        task = asyncio.create_task(sleeper())
        streaming._set_active_send_task("e5214086", "sid1", task, started_at=time.monotonic() - 1)
        streaming._stream_buffers["e5214086"] = deque(
            [
                (1, {"type": "thinking", "text": "plan A", "stream_id": "sid1"}),
                (2, {"type": "tool_use", "id": "t1", "name": "bash",
                     "input": {"command": "curl x"}, "stream_id": "sid1"}),
                (3, {"type": "tool_result", "tool_use_id": "t1", "content": "403",
                     "is_error": False, "stream_id": "sid1"}),
            ],
            maxlen=2000,
        )
        try:
            ok = await streaming._cancel_chat_streams("e5214086")
            assert ok is True
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    asyncio.run(_run())

    assert saved.get("canceled") is True
    assert saved.get("role") == "assistant"
    assert "plan A" in saved.get("thinking", "")
    tools = json.loads(saved.get("tool_events") or "[]")
    assert tools[0]["name"] == "bash"
    assert tools[0]["result"]["content"] == "403"
    assert saved.get("content") == "[Response canceled]"
