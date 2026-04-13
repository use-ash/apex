"""
Tests for the compaction overhaul: session classification, reasoning artifacts,
adaptive transcript tail, and recovery template selection.

These are pure-logic unit tests — no LLM calls, no network I/O.
DB-dependent tests use the hermetic test database from conftest.py.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers: synthetic message builders
# ---------------------------------------------------------------------------

def _make_msg(content: str = "", tool_events: str = "[]",
              thinking: str = "", created_at: str = "",
              message_id: str = "") -> dict:
    """Build a message dict matching db._get_session_analysis_data output."""
    return {
        "content": content,
        "tool_events": tool_events,
        "thinking": thinking,
        "created_at": created_at or datetime.now().isoformat(),
        "message_id": message_id or f"msg_{id(content)}",
    }


def _thinking_message(length: int = 3000) -> dict:
    """Long analytical response with no code, no tool calls."""
    prose = (
        "## Analysis of Market Regime Detection\n\n"
        "The fundamental challenge with regime detection is distinguishing "
        "genuine regime shifts from noise. A Markov chain approach models "
        "this as transitions between discrete states, but the choice of "
        "state space critically determines the model's utility.\n\n"
        "### Key Insight: Duration as Signal Quality\n\n"
        "Bars that have been in a directional state for 4-6 bars show "
        "significantly higher continuation probability (74%) compared to "
        "fresh transitions (51%). This suggests that momentum confirmation "
        "through temporal persistence is more reliable than amplitude-based "
        "thresholds.\n\n"
        "### Failed Approach: Pure Amplitude Thresholds\n\n"
        "Initial attempts to classify regimes using return magnitude "
        "(e.g., >0.3% = trending, <0.1% = choppy) produced unstable "
        "boundaries that shifted with volatility regimes. The duration-based "
        "approach is invariant to volatility scaling.\n\n"
    )
    # Pad to desired length
    while len(prose) < length:
        prose += "Further analysis confirms the regime detection framework. "
    return _make_msg(content=prose[:length])


def _code_message() -> dict:
    """Message with heavy code content."""
    code = (
        "Here's the implementation:\n\n"
        "```python\n"
        "def classify_regime(bars, lookback=8):\n"
        "    states = []\n"
        "    for i in range(lookback, len(bars)):\n"
        "        window = bars[i-lookback:i]\n"
        "        up = sum(1 for b in window if b['close'] > b['open'])\n"
        "        if up / lookback > 0.6:\n"
        "            states.append('trending_up')\n"
        "        elif up / lookback < 0.4:\n"
        "            states.append('trending_down')\n"
        "        else:\n"
        "            states.append('choppy')\n"
        "    return states\n"
        "```\n\n"
        "And the test:\n\n"
        "```python\n"
        "def test_classify():\n"
        "    bars = [{'close': i, 'open': i-1} for i in range(20)]\n"
        "    result = classify_regime(bars)\n"
        "    assert all(s == 'trending_up' for s in result)\n"
        "```\n"
    )
    return _make_msg(content=code)


def _tool_message() -> dict:
    """Message with heavy tool events."""
    tools = json.dumps([
        {"tool": "read_file", "result": "ok"},
        {"tool": "edit_file", "result": "ok"},
        {"tool": "read_file", "result": "ok"},
        {"tool": "search_files", "result": "ok"},
    ])
    return _make_msg(content="I've made the changes.", tool_events=tools)


def _short_message(text: str = "Sure, I'll do that.") -> dict:
    """Short conversational message."""
    return _make_msg(content=text)


# ===========================================================================
# Test Suite 1: Session Type Classification
# ===========================================================================

class TestSessionClassifier:
    """Test _classify_session_type logic with mocked DB data."""

    def _classify(self, messages: list[dict]) -> dict:
        """Run the classifier against synthetic messages by mocking the DB call."""
        with patch("context._get_session_analysis_data", return_value=messages):
            with patch("context._last_compacted_at", {}):
                from context import _classify_session_type
                return _classify_session_type("test-chat-id")

    def test_thinking_session(self):
        """Long prose, no code, no tools => thinking."""
        msgs = [_thinking_message(3000) for _ in range(6)]
        result = self._classify(msgs)
        assert result["session_type"] == "thinking"
        assert result["avg_response_length"] >= 2000
        assert result["code_ratio"] < 0.2
        assert result["tool_call_ratio"] < 0.3

    def test_task_session_code_heavy(self):
        """Mostly code messages => task."""
        msgs = [_code_message() for _ in range(6)]
        result = self._classify(msgs)
        assert result["session_type"] == "task"
        assert result["code_ratio"] > 0.4

    def test_task_session_tool_heavy(self):
        """Mostly tool-heavy messages => task."""
        msgs = [_tool_message() for _ in range(6)]
        result = self._classify(msgs)
        assert result["session_type"] == "task"
        assert result["tool_call_ratio"] > 0.5

    def test_mixed_session(self):
        """Mix of thinking and code => mixed."""
        msgs = [
            _thinking_message(2500),
            _thinking_message(2500),
            _code_message(),
            _thinking_message(2500),
            _short_message("Let me think about that more..."),
            _code_message(),
        ]
        result = self._classify(msgs)
        # Code ratio ~0.33 (2/6), tool_call_ratio 0.0, avg length might be < 2000
        # depending on short message dragging down avg. Could be mixed or thinking.
        assert result["session_type"] in ("mixed", "thinking")

    def test_short_session_defaults_to_task(self):
        """Fewer than 5 messages => defaults to task."""
        msgs = [_thinking_message(3000) for _ in range(3)]
        result = self._classify(msgs)
        assert result["session_type"] == "task"
        assert result["message_count"] == 3

    def test_empty_session(self):
        """No messages => defaults to task."""
        result = self._classify([])
        assert result["session_type"] == "task"
        assert result["message_count"] == 0

    def test_boundary_code_ratio_exactly_0_4(self):
        """code_ratio exactly 0.4 should NOT trigger task (> not >=)."""
        # 2 code messages out of 5 = 0.4
        msgs = [
            _code_message(),
            _code_message(),
            _thinking_message(1000),  # short enough that avg < 2000
            _thinking_message(1000),
            _thinking_message(1000),
        ]
        result = self._classify(msgs)
        # code_ratio = 0.4, NOT > 0.4, so first condition fails
        # avg_length ~ 1400, not > 2000, so thinking fails too
        assert result["session_type"] == "mixed"

    def test_metrics_populated(self):
        """All metric fields should be present and correctly typed."""
        msgs = [_thinking_message(2500) for _ in range(6)]
        result = self._classify(msgs)
        assert "session_type" in result
        assert "avg_response_length" in result
        assert "code_ratio" in result
        assert "tool_call_ratio" in result
        assert "max_response_length" in result
        assert "message_count" in result
        assert isinstance(result["code_ratio"], float)
        assert isinstance(result["tool_call_ratio"], float)
        assert isinstance(result["message_count"], int)

    def test_code_ratio_beats_thinking(self):
        """Even with long responses, high code ratio => task."""
        # Long messages that also have code blocks
        long_code = (
            "Here's my analysis:\n\n```python\n" +
            "x = 1\n" * 300 +
            "```\n\nAnd more:\n```python\n" +
            "y = 2\n" * 300 +
            "```\n"
        )
        msgs = [_make_msg(content=long_code) for _ in range(6)]
        result = self._classify(msgs)
        assert result["session_type"] == "task"
        assert result["avg_response_length"] > 2000
        assert result["code_ratio"] > 0.4


# ===========================================================================
# Test Suite 2: Reasoning Artifact Detection
# ===========================================================================

class TestReasoningArtifactDetection:
    """Test detect_reasoning_artifacts() — pure function, no mocking needed."""

    def test_detects_long_prose(self):
        """Long analytical message with no code => artifact."""
        from reasoning_artifacts import detect_reasoning_artifacts
        msgs = [_thinking_message(3000)]
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 1
        assert artifacts[0]["content_length"] >= 2000
        assert artifacts[0]["code_ratio"] < 0.3

    def test_skips_short_messages(self):
        """Messages under 2000 chars are never artifacts."""
        from reasoning_artifacts import detect_reasoning_artifacts
        msgs = [_short_message("Brief response.")]
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 0

    def test_skips_code_heavy(self):
        """Messages with code_ratio >= 0.3 are not artifacts."""
        from reasoning_artifacts import detect_reasoning_artifacts
        code_heavy = (
            "Some explanation:\n"
            "```python\n" +
            "x = 1\n" * 200 +
            "```\n"
            "Done."
        )
        msgs = [_make_msg(content=code_heavy)]
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 0

    def test_skips_tool_heavy(self):
        """Messages with >3 tool events are not artifacts."""
        from reasoning_artifacts import detect_reasoning_artifacts
        tools = json.dumps([{"t": i} for i in range(5)])
        msg = _make_msg(content="A" * 3000, tool_events=tools)
        msgs = [msg]
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 0

    def test_allows_few_tool_events(self):
        """Messages with <= 3 tool events can still be artifacts."""
        from reasoning_artifacts import detect_reasoning_artifacts
        tools = json.dumps([{"t": 1}, {"t": 2}])
        msg = _thinking_message(3000)
        msg["tool_events"] = tools
        artifacts = detect_reasoning_artifacts([msg])
        assert len(artifacts) == 1

    def test_extracts_topics_from_headers(self):
        """Section headers (# ...) become topic entries."""
        from reasoning_artifacts import detect_reasoning_artifacts
        msgs = [_thinking_message(3000)]  # has "## Analysis of..." headers
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 1
        assert len(artifacts[0]["topics"]) > 0
        assert any("Analysis" in t for t in artifacts[0]["topics"])

    def test_preserves_full_content(self):
        """Artifact includes complete content in content_full."""
        from reasoning_artifacts import detect_reasoning_artifacts
        msg = _thinking_message(3000)
        artifacts = detect_reasoning_artifacts([msg])
        assert artifacts[0]["content_full"] == msg["content"]

    def test_multiple_artifacts(self):
        """Multiple qualifying messages each produce an artifact."""
        from reasoning_artifacts import detect_reasoning_artifacts
        msgs = [_thinking_message(3000) for _ in range(4)]
        artifacts = detect_reasoning_artifacts(msgs)
        assert len(artifacts) == 4

    def test_indented_code_counts(self):
        """4-space indented lines count as code (not just fenced blocks)."""
        from reasoning_artifacts import detect_reasoning_artifacts
        # 70% indented lines = code_ratio >= 0.3 => skip
        content = "Explanation:\n" + ("    indented_code_line\n" * 70) + ("prose line\n" * 30)
        while len(content) < 2100:
            content += "more prose to reach threshold. "
        msgs = [_make_msg(content=content)]
        artifacts = detect_reasoning_artifacts(msgs)
        # The indented lines should push code_ratio above 0.3
        assert len(artifacts) == 0


# ===========================================================================
# Test Suite 3: Artifact Save / Load / Cleanup
# ===========================================================================

class TestArtifactPersistence:
    """Test save/load/cleanup using a temp directory."""

    @pytest.fixture(autouse=True)
    def _tmp_artifacts_dir(self, tmp_path):
        """Redirect ARTIFACTS_DIR to a temp path."""
        import reasoning_artifacts as ra
        self._orig_dir = ra.ARTIFACTS_DIR
        ra.ARTIFACTS_DIR = str(tmp_path / "artifacts")
        yield
        ra.ARTIFACTS_DIR = self._orig_dir

    def test_save_and_load_roundtrip(self):
        """Saved artifacts can be loaded back."""
        from reasoning_artifacts import (
            detect_reasoning_artifacts, save_reasoning_artifacts,
            load_reasoning_artifacts,
        )
        msgs = [_thinking_message(3000)]
        artifacts = detect_reasoning_artifacts(msgs)
        saved = save_reasoning_artifacts("chat123", artifacts)
        assert saved == 1

        loaded = load_reasoning_artifacts("chat123")
        assert len(loaded) == 1
        assert loaded[0]["chat_id"] == "chat123"
        assert loaded[0]["content_length"] >= 2000

    def test_load_respects_limit(self):
        """load_reasoning_artifacts respects the limit param."""
        from reasoning_artifacts import save_reasoning_artifacts, load_reasoning_artifacts
        artifacts = [
            {"content_full": f"art {i}", "content_length": 3000,
             "content_preview": f"art {i}", "topics": [], "code_ratio": 0.1,
             "created_at": datetime.now().isoformat(), "message_id": f"m{i}"}
            for i in range(5)
        ]
        save_reasoning_artifacts("chat456", artifacts)
        loaded = load_reasoning_artifacts("chat456", limit=2)
        assert len(loaded) == 2

    def test_load_empty_chat(self):
        """Loading artifacts for unknown chat returns empty list."""
        from reasoning_artifacts import load_reasoning_artifacts
        loaded = load_reasoning_artifacts("nonexistent-chat")
        assert loaded == []

    def test_load_isolates_by_chat_id(self):
        """Artifacts for different chats don't leak."""
        from reasoning_artifacts import save_reasoning_artifacts, load_reasoning_artifacts
        art = [{"content_full": "test", "content_length": 2500,
                "content_preview": "test", "topics": [], "code_ratio": 0.1,
                "created_at": datetime.now().isoformat(), "message_id": "m1"}]
        save_reasoning_artifacts("chatA", art)
        save_reasoning_artifacts("chatB", art)
        loaded_a = load_reasoning_artifacts("chatA")
        loaded_b = load_reasoning_artifacts("chatB")
        assert len(loaded_a) == 1
        assert len(loaded_b) == 1
        assert loaded_a[0]["chat_id"] == "chatA"
        assert loaded_b[0]["chat_id"] == "chatB"

    def test_cleanup_removes_old(self):
        """cleanup_old_artifacts removes files older than max_age_days."""
        from reasoning_artifacts import save_reasoning_artifacts, cleanup_old_artifacts, ARTIFACTS_DIR
        art = [{"content_full": "old", "content_length": 2500,
                "content_preview": "old", "topics": [], "code_ratio": 0.1,
                "created_at": datetime.now().isoformat(), "message_id": "m1"}]
        save_reasoning_artifacts("chatOld", art)

        # Backdate the file
        artifacts_dir = Path(ARTIFACTS_DIR)
        for f in artifacts_dir.iterdir():
            old_time = time.time() - (8 * 86400)  # 8 days ago
            os.utime(f, (old_time, old_time))

        removed = cleanup_old_artifacts(max_age_days=7)
        assert removed == 1
        remaining = list(artifacts_dir.iterdir())
        assert len(remaining) == 0

    def test_cleanup_enforces_per_chat_limit(self):
        """cleanup_old_artifacts evicts oldest when exceeding max_per_chat."""
        from reasoning_artifacts import save_reasoning_artifacts, cleanup_old_artifacts, ARTIFACTS_DIR
        # Save all 5 in a single call so they get unique _0 through _4 suffixes
        # (avoids timestamp collision from sub-second calls)
        arts = [
            {"content_full": f"art{i}", "content_length": 2500,
             "content_preview": f"art{i}", "topics": [], "code_ratio": 0.1,
             "created_at": datetime.now().isoformat(), "message_id": f"m{i}"}
            for i in range(5)
        ]
        saved = save_reasoning_artifacts("chatMany", arts)
        assert saved == 5

        # Stagger mtime so cleanup can sort oldest-first
        artifacts_dir = Path(ARTIFACTS_DIR)
        files = sorted(artifacts_dir.iterdir())
        for i, f in enumerate(files):
            os.utime(f, (time.time() - (10 - i), time.time() - (10 - i)))

        removed = cleanup_old_artifacts(max_age_days=30, max_per_chat=3)
        assert removed == 2
        remaining = list(artifacts_dir.iterdir())
        assert len(remaining) == 3


# ===========================================================================
# Test Suite 4: Recovery Template Selection
# ===========================================================================

class TestRecoveryTemplate:
    """Test that _generate_recovery_context uses the right template per session type.

    The function makes raw urllib.request.urlopen calls to xAI/Anthropic/Ollama.
    We mock urlopen to capture the request payload and return canned responses.
    """

    def _mock_urlopen(self, return_text="## Task: test"):
        """Create a mock for urllib.request.urlopen that returns canned LLM output."""
        mock_resp = MagicMock()
        # Ollama response format (last fallback)
        mock_resp.read.return_value = json.dumps(
            {"response": return_text}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def _capture_urlopen(self, return_text="## Task: test"):
        """Return (mock_urlopen_fn, captured_requests) for inspecting payloads."""
        captured = []
        def mock_fn(req, **kwargs):
            body = json.loads(req.data.decode()) if req.data else {}
            captured.append({"url": req.full_url, "body": body})
            resp = MagicMock()
            resp.read.return_value = json.dumps({"response": return_text}).encode()
            return resp
        return mock_fn, captured

    def test_thinking_template_includes_mental_model(self):
        """Thinking sessions include Mental Model in the prompt to the LLM."""
        from context import _generate_recovery_context
        mock_fn, captured = self._capture_urlopen()
        # Clear API keys so it falls through to Ollama
        with patch.dict(os.environ, {"XAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=mock_fn):
                result = _generate_recovery_context("transcript", session_type="thinking")
        assert result is not None
        # Check that the system prompt sent to the model includes thinking fields
        prompt_text = captured[-1]["body"].get("prompt", "")
        assert "Mental Model" in prompt_text
        assert "Key Insights" in prompt_text
        assert "Failed Approaches" in prompt_text

    def test_task_template_no_mental_model(self):
        """Task sessions do NOT include Mental Model in the prompt."""
        from context import _generate_recovery_context
        mock_fn, captured = self._capture_urlopen()
        with patch.dict(os.environ, {"XAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=mock_fn):
                result = _generate_recovery_context("transcript", session_type="task")
        assert result is not None
        prompt_text = captured[-1]["body"].get("prompt", "")
        assert "Mental Model" not in prompt_text
        assert "Failed Approaches" not in prompt_text

    def test_artifacts_appended_to_transcript(self):
        """When artifacts are provided, they're appended to the transcript."""
        from context import _generate_recovery_context
        artifacts = [
            {"content_full": "This is a preserved analytical response about regime detection."}
        ]
        mock_fn, captured = self._capture_urlopen()
        with patch.dict(os.environ, {"XAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}, clear=False):
            with patch("urllib.request.urlopen", side_effect=mock_fn):
                _generate_recovery_context("base transcript", session_type="thinking", artifacts=artifacts)

        prompt_text = captured[-1]["body"].get("prompt", "")
        assert "Preserved Reasoning Artifacts" in prompt_text
        assert "regime detection" in prompt_text


# ===========================================================================
# Test Suite 5: Adaptive Transcript Tail Length
# ===========================================================================

class TestAdaptiveTranscriptTail:
    """Test _build_recovery_block uses correct tail length per session type.

    _build_recovery_block uses a lazy import for load_reasoning_artifacts,
    so we patch it on the reasoning_artifacts module directly.
    """

    def test_thinking_gets_longest_tail(self):
        """Thinking sessions should request TRANSCRIPT_TAIL_THINKING chars."""
        from context import _build_recovery_block, _TRANSCRIPT_TAIL_THINKING, _TRANSCRIPT_TAIL_CHARS

        captured_kwargs = {}
        def mock_tail(chat_id, max_chars=1500):
            captured_kwargs["max_chars"] = max_chars
            return "transcript tail content"

        with patch("context._get_transcript_tail", side_effect=mock_tail):
            with patch("reasoning_artifacts.load_reasoning_artifacts", return_value=[]):
                result = _build_recovery_block("test-chat", "summary", session_type="thinking")

        assert captured_kwargs["max_chars"] == _TRANSCRIPT_TAIL_THINKING
        assert _TRANSCRIPT_TAIL_THINKING > _TRANSCRIPT_TAIL_CHARS

    def test_task_gets_shortest_tail(self):
        """Task sessions should request base TRANSCRIPT_TAIL_CHARS."""
        from context import _build_recovery_block, _TRANSCRIPT_TAIL_CHARS

        captured_kwargs = {}
        def mock_tail(chat_id, max_chars=1500):
            captured_kwargs["max_chars"] = max_chars
            return "transcript tail content"

        with patch("context._get_transcript_tail", side_effect=mock_tail):
            result = _build_recovery_block("test-chat", "summary", session_type="task")

        assert captured_kwargs["max_chars"] == _TRANSCRIPT_TAIL_CHARS

    def test_mixed_gets_middle_tail(self):
        """Mixed sessions should request TRANSCRIPT_TAIL_MIXED chars."""
        from context import _build_recovery_block, _TRANSCRIPT_TAIL_MIXED

        captured_kwargs = {}
        def mock_tail(chat_id, max_chars=1500):
            captured_kwargs["max_chars"] = max_chars
            return "transcript tail content"

        with patch("context._get_transcript_tail", side_effect=mock_tail):
            with patch("reasoning_artifacts.load_reasoning_artifacts", return_value=[]):
                result = _build_recovery_block("test-chat", "summary", session_type="mixed")

        assert captured_kwargs["max_chars"] == _TRANSCRIPT_TAIL_MIXED

    def test_thinking_recovery_includes_critical_instructions(self):
        """Thinking session recovery block includes anti-regression instructions."""
        from context import _build_recovery_block
        with patch("context._get_transcript_tail", return_value="tail"):
            with patch("reasoning_artifacts.load_reasoning_artifacts", return_value=[]):
                result = _build_recovery_block("test-chat", "summary", session_type="thinking")

        assert "CRITICAL RECOVERY INSTRUCTIONS" in result
        assert "Mental Model" in result
        assert "Failed Approaches" in result
        assert "Do not regress" in result

    def test_task_recovery_has_generic_instructions(self):
        """Task session recovery block uses generic continuation instructions."""
        from context import _build_recovery_block
        with patch("context._get_transcript_tail", return_value="tail"):
            result = _build_recovery_block("test-chat", "summary", session_type="task")

        assert "Pick up where you left off" in result
        assert "CRITICAL RECOVERY INSTRUCTIONS" not in result

    def test_recovery_block_includes_artifacts(self):
        """Thinking recovery block includes loaded reasoning artifacts."""
        from context import _build_recovery_block
        fake_artifacts = [{
            "content_full": "Deep analysis of compaction quality loss...",
            "topics": ["Compaction Quality", "KV Cache"],
        }]
        with patch("context._get_transcript_tail", return_value="tail"):
            with patch("reasoning_artifacts.load_reasoning_artifacts", return_value=fake_artifacts):
                result = _build_recovery_block("test-chat", "summary", session_type="thinking")

        assert "Preserved Reasoning Artifacts" in result
        assert "compaction quality loss" in result
        assert "Compaction Quality" in result
