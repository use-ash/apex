"""Unit tests for Grok chat_history tool-event extraction (this-turn scope)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class GrokToolHistoryTests(unittest.TestCase):
    def test_slice_history_this_turn(self) -> None:
        import backends as b

        rows = [
            {"type": "user", "content": "first"},
            {"type": "assistant", "tool_calls": [{"id": "a1", "name": "old", "arguments": "{}"}]},
            {"type": "tool_result", "tool_call_id": "a1", "content": "old out"},
            {"type": "user", "content": "second"},
            {"type": "assistant", "tool_calls": [{"id": "b1", "name": "new", "arguments": "{}"}]},
            {"type": "tool_result", "tool_call_id": "b1", "content": "new out"},
        ]
        sliced = b._slice_history_this_turn(rows)
        self.assertEqual([r.get("type") for r in sliced], ["assistant", "tool_result"])
        self.assertEqual(sliced[0]["tool_calls"][0]["id"], "b1")

    def test_extract_this_turn_only(self) -> None:
        import backends as b

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "chat_history.jsonl"
            lines = [
                {"type": "user", "content": "old"},
                {
                    "type": "assistant",
                    "tool_calls": [
                        {"id": "old1", "name": "run_terminal_command", "arguments": "ls"}
                    ],
                },
                {"type": "tool_result", "tool_call_id": "old1", "content": "a"},
                {"type": "user", "content": "new"},
                {
                    "type": "assistant",
                    "tool_calls": [
                        {"id": "new1", "name": "read_file", "arguments": "x"},
                        {"id": "new2", "name": "grep", "arguments": "y"},
                    ],
                },
                {"type": "tool_result", "tool_call_id": "new1", "content": "file"},
                {"type": "tool_result", "tool_call_id": "new2", "content": "hits"},
            ]
            p.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")

            all_ev = b._extract_tool_events_from_history(p, this_turn_only=False)
            turn_ev = b._extract_tool_events_from_history(p, this_turn_only=True)

            self.assertEqual(
                sum(1 for e in all_ev if e["type"] == "tool_use"), 3
            )
            self.assertEqual(
                sum(1 for e in turn_ev if e["type"] == "tool_use"), 2
            )
            names = [e["name"] for e in turn_ev if e["type"] == "tool_use"]
            self.assertEqual(names, ["read_file", "grep"])
            self.assertNotIn("old1", [e["id"] for e in turn_ev])


if __name__ == "__main__":
    unittest.main()
