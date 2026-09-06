from __future__ import annotations

import unittest

import os

from agent_sdk import _is_auth_error, _put_api_key_env
from claude_login import extract_oauth_url, parse_login_output, sanitize_code, strip_ansi
import ws_handler


class ClaudeLoginParseTests(unittest.TestCase):
    def test_extracts_plain_authorize_url(self) -> None:
        url = (
            "https://platform.claude.com/oauth/authorize?code=challenge"
            "&redirect_uri=https://platform.claude.com/oauth/code/callback"
        )
        raw = f"Browser didn't open?\nUse the url below to sign in\n{url}\n"
        self.assertEqual(extract_oauth_url(raw), url)

    def test_extracts_wrapped_url(self) -> None:
        url = "https://platform.claude.com/oauth/authorize?" + ("a" * 200)
        wrapped = url[:80] + "\n" + url[80:160] + "\n" + url[160:]
        self.assertEqual(extract_oauth_url(wrapped), url)

    def test_extracts_osc8_hyperlink(self) -> None:
        url = "https://claude.ai/oauth/authorize?x=1"
        raw = f"\x1b]8;;{url}\x07Open\x1b]8;;\x07"
        self.assertEqual(extract_oauth_url(raw), url)

    def test_ignores_http(self) -> None:
        self.assertIsNone(extract_oauth_url("http://evil.example/oauth/authorize"))

    def test_parse_awaiting_code(self) -> None:
        raw = (
            "https://platform.claude.com/oauth/authorize?code=x\n"
            "Paste code here if prompted > "
        )
        parsed = parse_login_output(raw)
        self.assertTrue(parsed["awaiting_code"])
        self.assertFalse(parsed["ok"])
        self.assertIsNotNone(parsed["url"])

    def test_parse_success(self) -> None:
        parsed = parse_login_output("Logged in as dana@example.com\n")
        self.assertTrue(parsed["ok"])

    def test_strip_ansi(self) -> None:
        self.assertEqual(strip_ansi("\x1b[31mred\x1b[0m"), "red")

    def test_sanitize_code_rejects_control(self) -> None:
        self.assertEqual(sanitize_code("  ABC#def  "), "ABC#def")
        with self.assertRaises(ValueError):
            sanitize_code("abc\ndef")
        with self.assertRaises(ValueError):
            sanitize_code("")


class AuthErrorDetectTests(unittest.TestCase):
    def test_short_cli_error_matches(self) -> None:
        self.assertTrue(_is_auth_error("Not logged in · Please run /login"))

    def test_long_reply_mentioning_login_does_not_match(self) -> None:
        text = (
            "Clean since the restart.\n"
            "Please run /login is what the CLI said earlier, but this turn worked.\n"
            "Invalid API key is the Haiku 401 we saw in compaction recovery.\n"
        ) * 3
        self.assertGreater(len(text), 240)
        self.assertFalse(_is_auth_error(text))


class PutApiKeyEnvTests(unittest.TestCase):
    def test_refuses_to_export_oauth_token(self) -> None:
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-oat01DEADBEEFdead"
        try:
            _put_api_key_env("sk-ant-oat01NEWTOKENdead")
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_exports_real_api_key(self) -> None:
        old = os.environ.get("ANTHROPIC_API_KEY")
        try:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            _put_api_key_env("sk-ant-api03-not-an-oauth-token")
            self.assertEqual(os.environ.get("ANTHROPIC_API_KEY"), "sk-ant-api03-not-an-oauth-token")
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old


class ClaudeAuthErrorCopyTests(unittest.TestCase):
    def test_public_message_points_at_reauth(self) -> None:
        msg = ws_handler._public_backend_error_message(
            "claude",
            "Not logged in · Please run /login",
        )
        self.assertIn("Re-authenticate", msg)
        self.assertIn("/admin#models", msg)
        self.assertNotIn("Open Terminal", msg)


if __name__ == "__main__":
    unittest.main()
