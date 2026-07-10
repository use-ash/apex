"""PR1b — level × server admission matrix (dual-track).

Design ref: docs/UNIFIED_TOOL_SURFACE_DESIGN.md
§"Level × server admission matrix (dual-track — locked for P1+)"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class ServersForLevelTests(unittest.TestCase):
    """Required PR1b cases from design doc §PR1b unit tests."""

    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts
        self.catalog = frozenset({
            "filesystem", "fetch", "memory",
            "playwright", "tradingview", "gdrive", "code-review-graph",
            "claim_store", "execute_code",
            "computer_use", "interceptor", "guide_tools",
        })

    def _admit(self, backend: str, level: int, pack: str = "full", extras=None):
        admitted, _ = self.ts.servers_for_level(
            self.catalog, level=level, backend=backend, pack=pack, extras=extras,
        )
        return admitted

    # --- Required cases -----------------------------------------------------

    def test_claude_L2_admits_execute_code(self) -> None:
        # (1) backend=claude, L2, Jupyter available → surface contains execute_code
        admitted = self._admit("claude", level=2, pack="full")
        self.assertIn("execute_code", admitted)

    def test_xai_L2_core_denies_execute_code(self) -> None:
        # (2) backend=xai, L2, core pack → surface does NOT contain execute_code
        admitted = self._admit("xai", level=2, pack="core")
        self.assertNotIn("execute_code", admitted)

    def test_xai_L2_core_no_extras_denies_claim_store(self) -> None:
        # (3) backend=xai, L2, core pack, no claim extras → no claim_store
        admitted = self._admit("xai", level=2, pack="core", extras=None)
        self.assertNotIn("claim_store", admitted)

    def test_codex_extras_core_admits_claim_store(self) -> None:
        # (4) backend=codex, gate-test extras, core pack → claim_store admitted
        admitted = self._admit(
            "codex", level=1, pack="core",
            extras=frozenset({"claim_store__submit_claim", "claim_store__list"}),
        )
        self.assertIn("claim_store", admitted)

    # --- L0 guide-only -----------------------------------------------------

    def test_L0_no_extras_admits_nothing(self) -> None:
        admitted = self._admit("claude", level=0, pack="full", extras=None)
        self.assertEqual(admitted, frozenset())

    def test_L0_guide_extras_admits_only_guide_tools(self) -> None:
        admitted = self._admit(
            "claude", level=0, pack="full",
            extras=frozenset({"guide__set_config"}),
        )
        self.assertEqual(admitted, frozenset({"guide_tools"}))

    # --- CLI danger denylist -----------------------------------------------

    def test_xai_L2_denies_computer_use_and_interceptor(self) -> None:
        admitted = self._admit("xai", level=2, pack="full")
        self.assertNotIn("computer_use", admitted)
        self.assertNotIn("interceptor", admitted)

    def test_codex_L4_denies_computer_use(self) -> None:
        # CLI danger denylist applies at every level unless allow_cli_dangerous
        admitted = self._admit("codex", level=4, pack="full")
        self.assertNotIn("computer_use", admitted)

    def test_cli_dangerous_override(self) -> None:
        admitted, _ = self.ts.servers_for_level(
            {"computer_use"}, level=2, backend="xai", pack="full",
            allow_cli_dangerous=True,
        )
        self.assertIn("computer_use", admitted)

    # --- CLI execute_code gate --------------------------------------------

    def test_xai_L3_full_admits_execute_code(self) -> None:
        admitted = self._admit("xai", level=3, pack="full")
        self.assertIn("execute_code", admitted)

    def test_xai_L2_full_still_denies_execute_code(self) -> None:
        # Pack alone doesn't unlock execute_code on CLI — needs L3.
        admitted = self._admit("xai", level=2, pack="full")
        self.assertNotIn("execute_code", admitted)

    # --- claim_store L3+ full pack path ------------------------------------

    def test_claude_L4_full_admits_claim_store_without_extras(self) -> None:
        admitted = self._admit("claude", level=4, pack="full", extras=None)
        self.assertIn("claim_store", admitted)

    def test_xai_L3_core_no_extras_denies_claim_store(self) -> None:
        # L3+ path requires pack=full without extras.
        admitted = self._admit("xai", level=3, pack="core", extras=None)
        self.assertNotIn("claim_store", admitted)

    def test_xai_L3_full_no_extras_admits_claim_store(self) -> None:
        admitted = self._admit("xai", level=3, pack="full", extras=None)
        self.assertIn("claim_store", admitted)

    # --- Core pack shape ---------------------------------------------------

    def test_core_pack_L2_shape_cli(self) -> None:
        admitted = self._admit("xai", level=2, pack="core")
        self.assertEqual(admitted, frozenset({"filesystem", "fetch", "memory"}))

    def test_full_pack_L2_shape_cli(self) -> None:
        admitted = self._admit("xai", level=2, pack="full")
        # F-tier + core, minus D-tier (computer_use/interceptor) + execute_code
        # (CLI L3+) + claim_store (needs extras or L3+ full).
        self.assertIn("filesystem", admitted)
        self.assertIn("playwright", admitted)
        self.assertIn("tradingview", admitted)
        self.assertNotIn("execute_code", admitted)
        self.assertNotIn("computer_use", admitted)


class GrokMcpDenyRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts

    def test_L1_denies_filesystem_writes(self) -> None:
        rules = self.ts.grok_mcp_deny_rules_for_level(1)
        self.assertIn("MCPTool(filesystem__write_file)", rules)
        self.assertIn("MCPTool(filesystem__edit_file)", rules)
        self.assertIn("MCPTool(filesystem__create_directory)", rules)
        self.assertIn("MCPTool(filesystem__move_file)", rules)

    def test_L0_empty(self) -> None:
        # filesystem itself denied at admission, no per-tool rule needed
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(0), [])

    def test_L2_empty(self) -> None:
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(2), [])

    def test_L4_empty(self) -> None:
        self.assertEqual(self.ts.grok_mcp_deny_rules_for_level(4), [])


class BackendTrackTests(unittest.TestCase):
    def setUp(self) -> None:
        import tool_surface as ts

        self.ts = ts

    def test_sdk_track(self) -> None:
        self.assertEqual(self.ts.backend_track("claude"), "sdk")
        self.assertEqual(self.ts.backend_track("tool_loop"), "sdk")

    def test_cli_track(self) -> None:
        self.assertEqual(self.ts.backend_track("xai"), "cli")
        self.assertEqual(self.ts.backend_track("grok"), "cli")
        self.assertEqual(self.ts.backend_track("codex"), "cli")

    def test_unknown_defaults_sdk(self) -> None:
        self.assertEqual(self.ts.backend_track("weird"), "sdk")


if __name__ == "__main__":
    unittest.main()
