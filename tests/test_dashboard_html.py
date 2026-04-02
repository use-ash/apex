from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from dashboard_html import DASHBOARD_HTML  # noqa: E402


def _extract_dashboard_script() -> str:
    start_marker = '<script nonce="{{CSP_NONCE}}">'
    start = DASHBOARD_HTML.find(start_marker)
    if start == -1:
        raise AssertionError("dashboard script tag not found")
    start += len(start_marker)
    end = DASHBOARD_HTML.find("</script>", start)
    if end == -1:
        raise AssertionError("dashboard closing script tag not found")
    return DASHBOARD_HTML[start:end]


class DashboardHtmlTests(unittest.TestCase):
    def test_dashboard_script_parses(self) -> None:
        script = _extract_dashboard_script()
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(script)
            temp_path = Path(handle.name)
        try:
            subprocess.run(
                ["node", "--check", str(temp_path)],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_sidebar_version_uses_runtime_placeholder(self) -> None:
        self.assertIn('{{APP_VERSION}}', DASHBOARD_HTML)
        self.assertNotIn('id="sidebar-version">v1.0<', DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
