"""PR1a parity tests for server/tool_surface.py pure extract."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class ToolSurfaceLoadParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="apex-ts-")
        self.root = Path(self._tmp.name)
        (self.root / "state").mkdir()
        self.mcp_path = self.root / "state" / "mcp_servers.json"
        self.mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "filesystem": {
                            "type": "stdio",
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                        },
                        "disabled_one": {
                            "enabled": False,
                            "command": "echo",
                            "args": [],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        # Point APEX_ROOT at temp so loaders read our fixture catalog.
        self._env = mock.patch.dict(
            os.environ,
            {
                "APEX_ROOT": str(self.root),
                "APEX_WORKSPACE": str(self.root),
                "APEX_DB_NAME": "test_apex.db",
            },
        )
        self._env.start()
        # env.APEX_ROOT is bound at import — force reload of env + tool_surface.
        for mod in ("env", "tool_surface", "streaming", "local_model.mcp_bridge"):
            sys.modules.pop(mod, None)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def test_strip_enabled_matches_claude_shim(self) -> None:
        import tool_surface as ts
        import streaming as streaming_mod

        direct = ts.load_enabled_mcp_servers(strip_enabled_key=True)
        via_shim = streaming_mod._load_mcp_servers()
        self.assertEqual(set(direct), {"filesystem"})
        self.assertNotIn("enabled", direct["filesystem"])
        self.assertEqual(direct, via_shim)

    def test_preserve_enabled_matches_bridge_shim(self) -> None:
        import tool_surface as ts
        from local_model import mcp_bridge as mcp_bridge_mod

        direct = ts.load_enabled_mcp_servers(strip_enabled_key=False)
        via_bridge = mcp_bridge_mod._load_mcp_config()
        self.assertEqual(set(direct), {"filesystem"})
        self.assertTrue(direct["filesystem"].get("enabled", True))
        self.assertEqual(direct, via_bridge)

    def test_claim_store_inject_preserves_other_env(self) -> None:
        import tool_surface as ts

        servers = {
            "claim_store": {
                "command": "python",
                "args": ["x.py"],
                "env": {"APEX_DB_NAME": "apex_dev.db", "OTHER": "1"},
            }
        }
        out = ts.inject_claim_store_mcp(servers, chat_id="chat-abc")
        self.assertEqual(out["claim_store"]["env"]["APEX_CHAT_ID"], "chat-abc")
        self.assertEqual(out["claim_store"]["env"]["APEX_DB_NAME"], "apex_dev.db")
        self.assertEqual(out["claim_store"]["env"]["OTHER"], "1")
        # Original not mutated
        self.assertNotIn("APEX_CHAT_ID", servers["claim_store"]["env"])

    def test_guide_inject_idempotent(self) -> None:
        import tool_surface as ts

        out1 = ts.inject_guide_tools_mcp({})
        if "guide_tools" not in out1:
            self.skipTest("mcp_guide_tools.py missing in this checkout")
        out2 = ts.inject_guide_tools_mcp(out1)
        self.assertIs(out2, out1)  # already configured → same object returned

    def test_project_claude_passthrough(self) -> None:
        import tool_surface as ts

        servers = {"fetch": {"command": "npx", "args": []}}
        out = ts.project_claude(servers)
        self.assertEqual(out, servers)
        self.assertIsNot(out, servers)


if __name__ == "__main__":
    unittest.main()
