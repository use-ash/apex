"""PR2 — Grok / xai projector unit tests.

Design ref: docs/UNIFIED_TOOL_SURFACE_DESIGN.md §PR2, §project_grok hard algorithm.
PR0 wire names: docs/PR0_TOOL_SURFACE_SPIKES.md §3.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class GrokDenyRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts

    def test_L0_denies_bash_edit_write_webfetch(self) -> None:
        rules = self.ts.grok_deny_rules_for_level(0)
        self.assertEqual(set(rules), {"Bash", "Edit", "Write", "WebFetch"})

    def test_L1_denies_bash_edit_write(self) -> None:
        rules = self.ts.grok_deny_rules_for_level(1)
        self.assertEqual(set(rules), {"Bash", "Edit", "Write"})

    def test_L2_denies_edit_write_only(self) -> None:
        """L2 omits Bash from denies to avoid interactive popups
        (--always-approve handles it). Edit/Write still denied."""
        rules = self.ts.grok_deny_rules_for_level(2)
        self.assertEqual(set(rules), {"Edit", "Write"})

    def test_L3_plus_no_builtin_denies(self) -> None:
        self.assertEqual(self.ts.grok_deny_rules_for_level(3), [])
        self.assertEqual(self.ts.grok_deny_rules_for_level(4), [])

    def test_L1_mcp_write_denies_pr0_wire_names(self) -> None:
        rules = self.ts.grok_mcp_deny_rules_for_level(1)
        expected = {
            "MCPTool(filesystem__write_file)",
            "MCPTool(filesystem__edit_file)",
            "MCPTool(filesystem__create_directory)",
            "MCPTool(filesystem__move_file)",
        }
        self.assertEqual(set(rules), expected)

    def test_L2_plus_no_mcp_write_denies(self) -> None:
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(0), [])
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(2), [])
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(3), [])


class ProjectGrokTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts
        self._tmp = tempfile.TemporaryDirectory(prefix="apex-ts-grok-")
        self.root = Path(self._tmp.name)
        self.real_home = self.root / "real_grok"
        self.real_home.mkdir()
        (self.real_home / "auth.json").write_text('{"token":"x"}')
        (self.real_home / "sessions").mkdir()
        (self.real_home / "sessions" / "s1.json").write_text("{}")
        (self.real_home / "config.toml").write_text(
            '[models]\ndefault = "grok-4"\n\n'
            '[mcp_servers."legacy"]\ncommand = "echo"\nargs = ["old"]\n\n'
            "[compat.claude]\nmcps = true\n"
        )
        self.servers = {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            },
            "memory": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            },
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_project_symlinks_auth_and_sessions(self) -> None:
        temp_home, env, args = self.ts.project_grok(
            self.servers, real_grok_home=self.real_home
        )
        try:
            self.assertTrue(temp_home.name.startswith("apex-grok-home-"))
            self.assertEqual(env["GROK_HOME"], str(temp_home))
            self.assertEqual(env["GROK_CLAUDE_MCPS_ENABLED"], "0")
            self.assertEqual(env["GROK_CURSOR_MCPS_ENABLED"], "0")
            auth = temp_home / "auth.json"
            sessions = temp_home / "sessions"
            self.assertTrue(auth.is_symlink())
            self.assertTrue(sessions.is_symlink())
            self.assertEqual(auth.resolve(), (self.real_home / "auth.json").resolve())
            self.assertEqual(sessions.resolve(), (self.real_home / "sessions").resolve())
            # Real home untouched
            self.assertTrue((self.real_home / "auth.json").is_file())
            self.assertFalse((self.real_home / "auth.json").is_symlink())
        finally:
            self.ts.cleanup_projected_home(temp_home)

    def test_config_merge_strips_legacy_mcp_and_adds_apex(self) -> None:
        temp_home, _, _ = self.ts.project_grok(
            self.servers, real_grok_home=self.real_home
        )
        try:
            cfg = (temp_home / "config.toml").read_text()
            self.assertIn('[models]', cfg)
            self.assertIn('default = "grok-4"', cfg)
            self.assertNotIn("legacy", cfg)
            self.assertIn('[mcp_servers."filesystem"]', cfg)
            self.assertIn('[mcp_servers."memory"]', cfg)
            self.assertIn("startup_timeout_sec = 60", cfg)  # npx default
            # compat forced off
            self.assertIn("[compat.claude]", cfg)
            self.assertIn("mcps = false", cfg)
            self.assertIn("[compat.cursor]", cfg)
        finally:
            self.ts.cleanup_projected_home(temp_home)

    def test_cli_deny_tools_become_mcp_tool_argv(self) -> None:
        temp_home, _, args = self.ts.project_grok(
            self.servers,
            real_grok_home=self.real_home,
            cli_deny_tools=("filesystem__write_file",),
        )
        try:
            self.assertEqual(args, ["--deny", "MCPTool(filesystem__write_file)"])
        finally:
            self.ts.cleanup_projected_home(temp_home)

    def test_refuses_temp_real_home_chaining(self) -> None:
        """If caller passes a prior temp home, fall back to ~/.grok."""
        fake_temp = self.root / "apex-grok-home-dead"
        fake_temp.mkdir()
        with mock.patch.object(Path, "home", return_value=self.root):
            # Put a durable home at root/.grok so fallback has something
            durable = self.root / ".grok"
            durable.mkdir()
            (durable / "auth.json").write_text("{}")
            temp_home, env, _ = self.ts.project_grok(
                {}, real_grok_home=fake_temp
            )
        try:
            # Symlink should come from durable ~/.grok under mocked home
            auth = temp_home / "auth.json"
            if auth.exists() or auth.is_symlink():
                self.assertTrue(auth.is_symlink())
                self.assertEqual(auth.resolve(), (durable / "auth.json").resolve())
            self.assertEqual(env["GROK_HOME"], str(temp_home))
        finally:
            self.ts.cleanup_projected_home(temp_home)

    def test_ignores_process_env_grok_home(self) -> None:
        """Env GROK_HOME must not become real_home (chaining bug)."""
        poison = self.root / "apex-grok-home-poison"
        poison.mkdir()
        with mock.patch.dict(os.environ, {"GROK_HOME": str(poison)}):
            temp_home, env, _ = self.ts.project_grok(
                self.servers, real_grok_home=self.real_home
            )
        try:
            self.assertNotEqual(env["GROK_HOME"], str(poison))
            self.assertTrue((temp_home / "auth.json").is_symlink())
        finally:
            self.ts.cleanup_projected_home(temp_home)

    def test_cleanup_removes_temp_only(self) -> None:
        temp_home, _, _ = self.ts.project_grok(
            self.servers, real_grok_home=self.real_home
        )
        self.assertTrue(temp_home.exists())
        self.ts.cleanup_projected_home(temp_home)
        self.assertFalse(temp_home.exists())
        # real home still intact
        self.assertTrue((self.real_home / "auth.json").exists())
        self.assertTrue((self.real_home / "sessions").exists())

    def test_cleanup_refuses_real_home(self) -> None:
        before = list(self.real_home.iterdir())
        self.ts.cleanup_projected_home(self.real_home)
        self.assertEqual(list(self.real_home.iterdir()), before)


class DetectProjectMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts
        self._tmp = tempfile.TemporaryDirectory(prefix="apex-ts-ws-")
        self.ws = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_workspace(self) -> None:
        self.assertEqual(self.ts.detect_project_mcp_sources(self.ws), [])

    def test_detects_mcp_json_and_grok_config(self) -> None:
        (self.ws / ".mcp.json").write_text("{}")
        (self.ws / ".grok").mkdir()
        (self.ws / ".grok" / "config.toml").write_text("[x]\n")
        self.assertEqual(
            self.ts.detect_project_mcp_sources(self.ws),
            [".mcp.json", ".grok/config.toml"],
        )


class ResolveForGrokPackTests(unittest.TestCase):
    """PR2: Grok defaults to core pack (no F-tier / no execute_code at L2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="apex-ts-rfg-")
        self.root = Path(self._tmp.name)
        (self.root / "state").mkdir()
        import json

        (self.root / "state" / "mcp_servers.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "filesystem": {
                            "enabled": True,
                            "command": "npx",
                            "args": ["-y", "fs", str(self.root)],
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

    def test_default_pack_is_core(self) -> None:
        import tool_surface as ts

        # L2 core: filesystem + fetch + memory; no playwright
        servers = ts.resolve_for_grok(
            None, workspace=str(self.root), permission_level=2
        )
        self.assertIn("filesystem", servers)
        self.assertIn("fetch", servers)
        self.assertIn("memory", servers)
        self.assertNotIn("playwright", servers)

    def test_full_pack_admits_f_tier(self) -> None:
        import tool_surface as ts

        servers = ts.resolve_for_grok(
            None, workspace=str(self.root), permission_level=2, pack="full"
        )
        self.assertIn("playwright", servers)


if __name__ == "__main__":
    unittest.main()
