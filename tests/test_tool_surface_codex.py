"""PR3 — Codex / project_codex unit tests.

Design: docs/UNIFIED_TOOL_SURFACE_DESIGN.md §PR3, §project_codex.
PR0: docs/PR0_TOOL_SURFACE_SPIKES.md §4–6.
"""
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


class CodexTomlValueTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts

    def test_string_bool_list_dict(self) -> None:
        self.assertEqual(self.ts._codex_toml_value("npx"), '"npx"')
        self.assertEqual(self.ts._codex_toml_value(True), "true")
        self.assertEqual(
            self.ts._codex_toml_value(["-y", "pkg"]),
            '["-y", "pkg"]',
        )
        self.assertEqual(
            self.ts._codex_toml_value({"FOO": "bar"}),
            '{ FOO = "bar" }',
        )

    def test_server_key_hyphen(self) -> None:
        self.assertEqual(
            self.ts._codex_server_c_key("code-review-graph"),
            "code_review_graph",
        )


class ProjectCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts
        self.servers = {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/ws"],
            },
            "memory": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {"X": "1"},
            },
        }

    def test_preferred_path_no_temp_home(self) -> None:
        args, env, temp = self.ts.project_codex(self.servers, permission_level=2)
        self.assertIsNone(temp)
        self.assertEqual(env, {})
        # -c pairs only
        self.assertEqual(args[0::2], ["-c"] * (len(args) // 2))
        joined = " ".join(args)
        self.assertIn("mcp_servers.filesystem.command=", joined)
        self.assertIn("mcp_servers.filesystem.args=", joined)
        self.assertIn("mcp_servers.memory.env=", joined)
        # L2: no enabled_tools allowlist
        self.assertNotIn("enabled_tools", joined)

    def test_L1_filesystem_enabled_tools_allowlist(self) -> None:
        args, _, _ = self.ts.project_codex(self.servers, permission_level=1)
        joined = " ".join(args)
        self.assertIn("mcp_servers.filesystem.enabled_tools=", joined)
        self.assertIn("read_file", joined)
        self.assertIn("list_directory", joined)
        # write tools must not appear in allowlist
        self.assertNotIn("write_file", joined)
        self.assertNotIn("edit_file", joined)

    def test_L3_no_enabled_tools(self) -> None:
        args, _, _ = self.ts.project_codex(self.servers, permission_level=3)
        self.assertNotIn("enabled_tools", " ".join(args))

    def test_real_codex_home_env_override(self) -> None:
        home = Path("/tmp/fake-codex-home")
        _, env, temp = self.ts.project_codex(
            {}, permission_level=2, real_codex_home=home
        )
        self.assertIsNone(temp)
        self.assertEqual(env.get("CODEX_HOME"), str(home))

    def test_empty_servers(self) -> None:
        args, env, temp = self.ts.project_codex({}, permission_level=2)
        self.assertEqual(args, [])
        self.assertEqual(env, {})
        self.assertIsNone(temp)

    def test_argv_shape_matches_pr0(self) -> None:
        """Nested -c keys match PR0 spike shape."""
        args, _, _ = self.ts.project_codex(
            {
                "fs_spike": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                }
            },
            permission_level=2,
        )
        # Collect value sides of -c pairs
        values = args[1::2]
        self.assertTrue(
            any(v.startswith('mcp_servers.fs_spike.command="npx"') for v in values)
        )
        self.assertTrue(any(v.startswith("mcp_servers.fs_spike.args=") for v in values))


class ResolveForCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="apex-ts-rfc-")
        self.root = Path(self._tmp.name)
        (self.root / "state").mkdir()
        (self.root / "state" / "mcp_servers.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "filesystem": {
                            "enabled": True,
                            "command": "npx",
                            "args": [
                                "-y",
                                "@modelcontextprotocol/server-filesystem",
                                "/old",
                            ],
                        },
                        "fetch": {
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "fetch"],
                        },
                        "memory": {
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "mem"],
                        },
                        "playwright": {
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "pw"],
                        },
                        "claim_store": {
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "claim"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        self._env = mock.patch.dict(
            os.environ,
            {
                "APEX_ROOT": str(self.root),
                "APEX_WORKSPACE": str(self.root),
                "APEX_DB_NAME": "test_apex.db",
            },
        )
        self._env.start()
        for mod in ("env", "tool_surface"):
            sys.modules.pop(mod, None)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()
        for mod in ("env", "tool_surface"):
            sys.modules.pop(mod, None)

    def test_default_core_pack_no_playwright(self) -> None:
        import tool_surface as ts

        servers = ts.resolve_for_codex(
            None, workspace=str(self.root), permission_level=2
        )
        self.assertIn("filesystem", servers)
        self.assertIn("fetch", servers)
        self.assertIn("memory", servers)
        self.assertNotIn("playwright", servers)
        self.assertNotIn("claim_store", servers)

    def test_extras_admit_claim_store(self) -> None:
        import tool_surface as ts

        servers = ts.resolve_for_codex(
            "chat1",
            workspace=str(self.root),
            permission_level=1,
            extra_allowed_tools=frozenset({"claim_store__claim_assert"}),
            pack="core",
        )
        self.assertIn("claim_store", servers)

    def test_L2_cli_denies_execute_code(self) -> None:
        import tool_surface as ts

        # inject won't add execute_code without jupyter; matrix would deny at L2 anyway
        servers = ts.resolve_for_codex(
            None, workspace=str(self.root), permission_level=2, pack="full"
        )
        self.assertNotIn("execute_code", servers)

    def test_workspace_rewrite_on_filesystem_args(self) -> None:
        import tool_surface as ts

        ws = str(self.root / "ws")
        Path(ws).mkdir()
        servers = ts.resolve_for_codex(None, workspace=ws, permission_level=2)
        args = servers["filesystem"]["args"]
        self.assertIn(ws, args)


class ClaimStoreRequiredTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts

    def test_extras_force(self) -> None:
        self.assertTrue(
            self.ts.claim_store_required(
                extras=frozenset({"claim_store__claim_list"})
            )
        )
        self.assertFalse(self.ts.claim_store_required(extras=None))

    def test_gate_test_profile(self) -> None:
        # b32aac1b is gate-test-codex-weak
        self.assertTrue(
            self.ts.claim_store_required(profile_id="b32aac1b", extras=None)
        )
        self.assertFalse(
            self.ts.claim_store_required(profile_id="not-a-gate", extras=None)
        )


if __name__ == "__main__":
    unittest.main()
