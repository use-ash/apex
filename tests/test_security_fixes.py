from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="apex-security-tests-"))

os.environ["APEX_ROOT"] = str(TEST_ROOT)
os.environ["APEX_WORKSPACE"] = str(TEST_ROOT)
os.environ["APEX_ALERT_TOKEN"] = "initial-alert-token"
os.environ["APEX_ADMIN_TOKEN"] = "admin-secret"
os.environ["APEX_SSL_CERT"] = ""
os.environ["APEX_SSL_KEY"] = ""
os.environ["APEX_SSL_CA"] = ""
os.environ["APEX_DB_NAME"] = "test_apex.db"
os.environ["APEX_LOG_NAME"] = "test_apex.log"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import apex  # noqa: E402
import alert_client  # noqa: E402
import agent_sdk  # noqa: E402
import backends  # noqa: E402
import dashboard as dashboard_mod  # noqa: E402
import dashboard_html as dashboard_html_mod  # noqa: E402
import db as db_mod  # noqa: E402
import env  # noqa: E402
import memory_extract  # noqa: E402
import context as context_mod  # noqa: E402
import premium_loader  # noqa: E402
import routes_chat as routes_chat_mod  # noqa: E402
import streaming as streaming_mod  # noqa: E402
import tool_access  # noqa: E402
import ws_handler  # noqa: E402
from state import (  # noqa: E402
    _current_group_profile_id,
    _active_send_tasks,
    _queued_turns,
    _chat_ws,
    _stream_buffers,
    _chat_locks,
    _chat_send_locks,
    _client_permission_levels,
    _client_permission_policies,
    _clients,
    _session_context_sent,
)
from local_model import safety as local_safety  # noqa: E402
from local_model import tool_loop  # noqa: E402
from local_model.tools import list_files, read_file, search_files, write_file  # noqa: E402
from setup.progress import mark_phase_completed  # noqa: E402


class SecurityFixTests(unittest.TestCase):
    def setUp(self) -> None:
        dashboard_mod._set_live_alert_token("initial-alert-token")
        apex.MODEL = env.MODEL
        apex._init_db()
        mark_phase_completed(TEST_ROOT / "state", "setup_complete")
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM chats")
            conn.commit()
            conn.close()
        apex._seed_default_profiles()
        apex.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        apex.LOG_PATH.write_text("", encoding="utf-8")
        for state in (
            _active_send_tasks,
            _queued_turns,
            _chat_ws,
            _stream_buffers,
            _chat_locks,
            _chat_send_locks,
            _client_permission_levels,
            _client_permission_policies,
            _clients,
            _session_context_sent,
        ):
            state.clear()
        context_mod._premium = None
        ws_handler._ws_premium = None

    def _client(self) -> TestClient:
        return TestClient(apex.app)

    def _fast_relay_context(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(ws_handler, "_has_session_context", return_value=True))
        stack.enter_context(mock.patch.object(ws_handler, "_generate_recovery_context", return_value=""))
        stack.enter_context(mock.patch.object(context_mod, "_get_workspace_context", return_value=""))
        stack.enter_context(mock.patch.object(backends, "_get_workspace_context", return_value=""))
        stack.enter_context(mock.patch.object(agent_sdk, "_get_workspace_context", return_value=""))
        return stack

    def _admin_headers(self) -> dict[str, str]:
        return {
            "Authorization": "Bearer admin-secret",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _create_test_group_chat(self) -> str:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "queue-codeexpert",
                    "Queue CodeExpert",
                    "queue-codeexpert",
                    "💻",
                    "Queue test agent",
                    "codex",
                    "codex:gpt-5.4",
                    "Queue test agent",
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "queue-apex-assistant",
                    "Queue Apex Assistant",
                    "queue-apex-assistant",
                    "✨",
                    "Queue test agent",
                    "codex",
                    "codex:gpt-5.4",
                    "Queue test agent",
                ),
            )
            conn.commit()
            conn.close()
        chat_id = db_mod._create_chat(title="Queue Test", model="codex:gpt-5.4", chat_type="group")
        db_mod._add_group_member(chat_id, "queue-codeexpert", routing_mode="primary", is_primary=True, display_order=0)
        db_mod._add_group_member(chat_id, "queue-apex-assistant", routing_mode="mentioned", display_order=1)
        return chat_id

    def _create_direct_chat(self, model: str = "qwen3:latest") -> str:
        return db_mod._create_chat(title="Security Test", model=model)

    def _create_uploaded_attachment(
        self,
        ext: str,
        data: bytes,
        *,
        name: str | None = None,
        kind: str | None = None,
    ) -> dict[str, str]:
        upload_dir = env.APEX_ROOT / "state" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex[:8]
        (upload_dir / f"{file_id}.{ext}").write_bytes(data)
        return {
            "id": file_id,
            "type": kind or ("image" if ext in {"jpg", "jpeg", "png", "gif", "webp"} else "text"),
            "name": name or f"upload.{ext}",
        }

    def _receive_until(self, ws, predicate):
        for _ in range(12):
            msg = ws.receive_json()
            if predicate(msg):
                return msg
        self.fail("Expected websocket event was not received")

    def _group_agent(self, chat_id: str, profile_id: str) -> dict:
        for member in db_mod._get_group_members(chat_id):
            if member["profile_id"] == profile_id:
                return {**member, "clean_prompt": f"Prompt for {member['name']}"}
        self.fail(f"group agent {profile_id} not found in chat {chat_id}")

    def _upsert_test_profile(
        self,
        profile_id: str,
        name: str,
        *,
        avatar: str = "🧪",
        is_system: bool = False,
    ) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, ?, datetime('now'), datetime('now'))
                """,
                (
                    profile_id,
                    name,
                    profile_id,
                    avatar,
                    "Queue test agent",
                    "codex",
                    "codex:gpt-5.4",
                    "Queue test agent",
                    1 if is_system else 0,
                ),
            )
            conn.commit()
            conn.close()

    def _add_test_group_member(
        self,
        chat_id: str,
        profile_id: str,
        name: str,
        *,
        avatar: str = "🧪",
        display_order: int = 2,
    ) -> None:
        self._upsert_test_profile(profile_id, name, avatar=avatar)
        db_mod._add_group_member(chat_id, profile_id, routing_mode="mentioned", display_order=display_order)

    def test_logs_search_treats_regex_as_literal_text(self) -> None:
        apex.LOG_PATH.write_text(
            "[2026-03-31 12:00:00] info literal a.+b\n"
            "[2026-03-31 12:00:01] info expanded axxxb\n",
            encoding="utf-8",
        )
        with self._client() as client:
            resp = client.get(
                "/admin/api/logs",
                params={"search": "a.+b"},
                headers=self._admin_headers(),
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertIn("literal a.+b", data["lines"][0]["message"])

    def test_alert_token_rotation_takes_effect_immediately(self) -> None:
        old_token = os.environ["APEX_ALERT_TOKEN"]
        with self._client() as client:
            rotate = client.post(
                "/admin/api/credentials/alert-token/rotate",
                headers=self._admin_headers(),
            )
            self.assertEqual(rotate.status_code, 200)
            new_token = rotate.json()["alert_token"]

            old_resp = client.post(
                "/api/alerts",
                json={"source": "test", "severity": "info", "title": "old"},
                headers={"Authorization": f"Bearer {old_token}"},
            )
            self.assertEqual(old_resp.status_code, 401)

            new_resp = client.post(
                "/api/alerts",
                json={"source": "test", "severity": "info", "title": "new"},
                headers={"Authorization": f"Bearer {new_token}"},
            )
            self.assertEqual(new_resp.status_code, 201)

    def test_dashboard_sensitive_get_requires_admin_token(self) -> None:
        with self._client() as client:
            denied = client.get("/admin/api/db/export")
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.json()["code"], "ADMIN_AUTH_REQUIRED")

            allowed = client.get(
                "/admin/api/db/export",
                headers={"Authorization": "Bearer admin-secret"},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                allowed.headers["content-type"],
                "application/octet-stream",
            )

    def test_dashboard_sensitive_get_accepts_admin_cookie(self) -> None:
        with self._client() as client:
            client.cookies.set("apex_admin_token", "admin-secret")
            resp = client.get("/admin/api/backups")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("backups", resp.json())

    def test_dashboard_shell_pages_remain_loadable_without_admin_token(self) -> None:
        with self._client() as client:
            index = client.get("/admin/")
            security = client.get("/admin/security-config")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(security.status_code, 200)

    def test_alert_client_https_without_ca_fails_closed(self) -> None:
        with (
            mock.patch.object(alert_client.env, "ALERT_TOKEN", "alert-token"),
            mock.patch.object(alert_client.env, "SERVER_URL", "https://localhost:8300"),
            mock.patch.object(alert_client.env, "SSL_CA", ""),
            mock.patch("alert_client.urllib.request.urlopen") as urlopen_mock,
        ):
            self.assertFalse(
                alert_client.send_apex_alert("tester", "info", "hello")
            )
            urlopen_mock.assert_not_called()

    def test_alert_client_uses_configured_ca_for_https(self) -> None:
        ca_dir = Path(tempfile.mkdtemp(prefix="apex-alert-client-ca-"))
        ca_path = ca_dir / "ca.crt"
        ca_path.write_text("placeholder", encoding="utf-8")
        ssl_context = object()

        with (
            mock.patch.object(alert_client.env, "ALERT_TOKEN", "alert-token"),
            mock.patch.object(alert_client.env, "SERVER_URL", "https://localhost:8300"),
            mock.patch.object(alert_client.env, "SSL_CA", str(ca_path)),
            mock.patch(
                "alert_client.ssl.create_default_context",
                return_value=ssl_context,
            ) as create_context_mock,
            mock.patch("alert_client.urllib.request.urlopen") as urlopen_mock,
        ):
            self.assertTrue(
                alert_client.send_apex_alert("tester", "info", "hello")
            )
            create_context_mock.assert_called_once_with(cafile=str(ca_path))
            self.assertIs(urlopen_mock.call_args.kwargs["context"], ssl_context)

    def test_server_url_defaults_to_current_port(self) -> None:
        env_copy = os.environ.copy()
        env_copy.pop("APEX_SERVER", None)
        env_copy["APEX_PORT"] = "8301"
        server_url = subprocess.check_output(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, {str(SERVER_DIR)!r}); "
                    "import env; "
                    "print(env.SERVER_URL)"
                ),
            ],
            text=True,
            env=env_copy,
        ).strip()
        self.assertEqual(server_url, "https://localhost:8301")

    def test_local_model_tools_default_off(self) -> None:
        self.assertFalse(env.ALLOW_LOCAL_TOOLS)

    def test_tool_loop_rejects_when_local_tools_disabled(self) -> None:
        async def emit(_event: dict) -> None:
            return None

        with mock.patch.object(tool_loop, "ALLOW_LOCAL_TOOLS", False):
            with self.assertRaisesRegex(
                RuntimeError,
                "Local model tools are disabled",
            ):
                asyncio.run(
                    tool_loop.run_tool_loop(
                        ollama_url="http://localhost:11434",
                        model="qwen3:latest",
                        messages=[{"role": "user", "content": "hi"}],
                        emit_event=emit,
                    )
                )

    def test_backend_falls_back_to_plain_chat_when_local_tools_disabled(self) -> None:
        chat_id = self._create_direct_chat()

        class _FakeResponse:
            def __iter__(self):
                return iter([
                    b'{"message":{"content":"hello "}}\n',
                    b'{"message":{"content":"world"}}\n',
                    b'{"done":true}\n',
                ])

        send_event = mock.AsyncMock()
        run_tool_loop_mock = mock.AsyncMock(side_effect=AssertionError("run_tool_loop should not be called"))

        with (
            mock.patch.object(backends, "ALLOW_LOCAL_TOOLS", False),
            mock.patch.object(backends, "_TOOL_LOOP_AVAILABLE", True),
            mock.patch.object(backends, "run_tool_loop", run_tool_loop_mock),
            mock.patch.object(backends, "_send_stream_event", send_event),
            mock.patch.object(backends, "_estimate_tokens", return_value=0),
            mock.patch.object(backends.urllib.request, "urlopen", return_value=_FakeResponse()),
        ):
            result = asyncio.run(
                backends._run_ollama_chat(chat_id, "Say hello", model="qwen3:latest")
            )

        self.assertEqual(result["text"], "hello world")
        self.assertFalse(result["is_error"])
        self.assertEqual(result["tool_events"], "[]")
        run_tool_loop_mock.assert_not_awaited()

    def test_make_options_standard_profile_uses_plan_and_blocks_write_tools(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "perm-standard",
                    "Perm Standard",
                    "perm-standard",
                    "S",
                    "standard test",
                    "claude",
                    "claude-sonnet-4-6",
                    "standard test",
                    json.dumps({"level": 1}),
                ),
            )
            conn.commit()
            conn.close()
        chat_id = db_mod._create_chat(
            title="Standard Persona",
            model="claude-sonnet-4-6",
            profile_id="perm-standard",
        )

        opts = streaming_mod._make_options(
            model="claude-sonnet-4-6",
            client_key=chat_id,
            chat_id=chat_id,
        )

        self.assertEqual(opts.permission_mode, "plan")
        allow_read = asyncio.run(opts.can_use_tool("Read", {}, SimpleNamespace(suggestions=[])))
        deny_bash = asyncio.run(
            opts.can_use_tool("Bash", {"command": "pwd"}, SimpleNamespace(suggestions=[]))
        )
        self.assertEqual(allow_read.behavior, "allow")
        self.assertEqual(deny_bash.behavior, "deny")
        self.assertTrue(deny_bash.interrupt)
        self.assertIn("Elevated", deny_bash.message)

    def test_make_options_restricted_profile_blocks_all_tools(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "perm-restricted",
                    "Perm Restricted",
                    "perm-restricted",
                    "R",
                    "restricted test",
                    "claude",
                    "claude-sonnet-4-6",
                    "restricted test",
                    json.dumps({"level": 0}),
                ),
            )
            conn.commit()
            conn.close()
        chat_id = db_mod._create_chat(
            title="Restricted Persona",
            model="claude-sonnet-4-6",
            profile_id="perm-restricted",
        )

        opts = streaming_mod._make_options(
            model="claude-sonnet-4-6",
            client_key=chat_id,
            chat_id=chat_id,
        )

        deny_read = asyncio.run(opts.can_use_tool("Read", {}, SimpleNamespace(suggestions=[])))
        self.assertEqual(opts.permission_mode, "plan")
        self.assertEqual(deny_read.behavior, "deny")
        self.assertTrue(deny_read.interrupt)
        self.assertIn("Restricted", deny_read.message)

    def test_agent_sdk_pending_denied_tools_preserve_partial_response(self) -> None:
        fake_client = SimpleNamespace(receive_response=lambda: None)
        sent: list[dict] = []

        async def fake_send_stream_event(_chat_id: str, payload: dict) -> None:
            sent.append(payload)

        async def fake_stream():
            yield agent_sdk.AssistantMessage(
                content=[
                    agent_sdk.TextBlock(text="I found the likely rendering issue and started narrowing it down."),
                    agent_sdk.ThinkingBlock(thinking="Need to inspect the live DOM after refresh.", signature="sig-1"),
                    agent_sdk.ToolUseBlock(id="toolu_1", name="Bash", input={"command": "pwd"}),
                ],
                model="claude-haiku-4-5-20251001",
            )
            yield agent_sdk.ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="sess-1",
                usage={"input_tokens": 1, "output_tokens": 1},
                result="/Users/dana/.openclaw/workspace",
            )

        with (
            mock.patch.object(agent_sdk, "_send_stream_event", side_effect=fake_send_stream_event),
            mock.patch.object(agent_sdk, "_normalize_response_stream", return_value=fake_stream()),
        ):
            result = asyncio.run(agent_sdk._stream_response(fake_client, "deadbeef"))

        self.assertTrue(result["is_error"])
        self.assertIn("I found the likely rendering issue", result["text"])
        self.assertIn("denied by host permissions", result["text"])
        self.assertIn("partial response was preserved", result["text"])
        self.assertEqual(result["thinking"], "Need to inspect the live DOM after refresh.")
        tool_events = json.loads(result["tool_events"])
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["name"], "Bash")
        self.assertTrue(tool_events[0]["result"]["is_error"])
        self.assertIn("denied by host permissions", tool_events[0]["result"]["content"])
        tool_result_event = next(evt for evt in sent if evt.get("type") == "tool_result")
        self.assertTrue(tool_result_event["is_error"])
        self.assertIn("denied by host permissions", tool_result_event["content"])
        result_event = next(evt for evt in sent if evt.get("type") == "result")
        self.assertTrue(result_event["is_error"])

    def test_agent_sdk_level_4_pending_tools_do_not_false_deny(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")
        db_mod._set_chat_tool_policy(
            chat_id,
            {
                "level": 4,
                "default_level": 2,
                "elevated_until": None,
                "allowed_commands": [],
            },
        )
        fake_client = SimpleNamespace(receive_response=lambda: None)
        sent: list[dict] = []

        async def fake_send_stream_event(_chat_id: str, payload: dict) -> None:
            sent.append(payload)

        async def fake_stream():
            yield agent_sdk.AssistantMessage(
                content=[agent_sdk.ToolUseBlock(id="toolu_1", name="Bash", input={"command": "date +%s"})],
                model="claude-haiku-4-5-20251001",
            )
            yield agent_sdk.ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="sess-1",
                usage={"input_tokens": 1, "output_tokens": 1},
                result="1775331480",
            )

        with (
            mock.patch.object(agent_sdk, "_send_stream_event", side_effect=fake_send_stream_event),
            mock.patch.object(agent_sdk, "_normalize_response_stream", return_value=fake_stream()),
        ):
            result = asyncio.run(agent_sdk._stream_response(fake_client, chat_id))

        self.assertFalse(result["is_error"])
        self.assertEqual(result["text"], "1775331480")
        self.assertNotIn("denied by host permissions", result["text"])
        tool_events = json.loads(result["tool_events"])
        self.assertEqual(len(tool_events), 1)
        self.assertFalse(tool_events[0]["result"]["is_error"])
        self.assertIn("omitted explicit result block", tool_events[0]["result"]["content"])
        result_event = next(evt for evt in sent if evt.get("type") == "result")
        self.assertFalse(result_event["is_error"])

    def test_local_full_admin_level_4_allows_shell_and_external_paths(self) -> None:
        outside_root = Path(tempfile.mkdtemp(prefix="apex-admin4-outside-"))
        target = outside_root / "admin4.txt"
        write_result = write_file.execute(
            {"file_path": str(target), "content": "full admin\n"},
            str(TEST_ROOT),
            permission_level=4,
        )
        self.assertIn("Wrote", write_result)

        read_result = read_file.execute(
            {"file_path": str(target)},
            str(TEST_ROOT),
            permission_level=4,
        )
        self.assertIn("full admin", read_result)

        argv, err = local_safety.prepare_command(
            "printf 'admin4\\n' | tr a-z A-Z",
            str(TEST_ROOT),
            permission_level=4,
        )
        self.assertIsNone(err)
        self.assertEqual(argv, ["/bin/sh", "-lc", "printf 'admin4\\n' | tr a-z A-Z"])
        shell_result = subprocess.run(argv, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(shell_result, "ADMIN4")

    def test_ollama_chat_passes_standard_tool_allowlist(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "perm-ollama-standard",
                    "Perm Ollama Standard",
                    "perm-ollama-standard",
                    "O",
                    "ollama standard test",
                    "ollama",
                    "qwen3:latest",
                    "ollama standard test",
                    json.dumps({"level": 1}),
                ),
            )
            conn.commit()
            conn.close()
        chat_id = db_mod._create_chat(
            title="Ollama Standard Persona",
            model="qwen3:latest",
            profile_id="perm-ollama-standard",
        )
        run_tool_loop_mock = mock.AsyncMock(
            return_value={
                "text": "ok",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }
        )

        with (
            mock.patch.object(backends, "_TOOL_LOOP_AVAILABLE", True),
            mock.patch.object(backends, "ALLOW_LOCAL_TOOLS", True),
            mock.patch.object(backends, "build_system_prompt", return_value="system"),
            mock.patch.object(backends, "run_tool_loop", run_tool_loop_mock),
            mock.patch.object(backends, "_send_stream_event", mock.AsyncMock()),
        ):
            result = asyncio.run(
                backends._run_ollama_chat(chat_id, "Inspect the repo", model="qwen3:latest")
            )

        self.assertFalse(result["is_error"])
        self.assertEqual(
            run_tool_loop_mock.await_args.kwargs["allowed_tools"],
            {"read_file", "list_files", "search_files"},
        )
        self.assertEqual(run_tool_loop_mock.await_args.kwargs["permission_level"], 1)

    def test_tool_access_level_2_allows_playwright_fetch_and_readonly_filesystem(self) -> None:
        with mock.patch.object(
            tool_access,
            "_iter_mcp_tool_names",
            return_value=[
                "playwright__browser_navigate",
                "fetch__fetch",
                "filesystem__read_text_file",
                "filesystem__write_file",
                "memory__read_graph",
            ],
        ):
            allowed = tool_access.allowed_tool_names_for_level(2)

        self.assertIn("playwright__browser_navigate", allowed)
        self.assertIn("fetch__fetch", allowed)
        self.assertIn("filesystem__read_text_file", allowed)
        self.assertNotIn("filesystem__write_file", allowed)
        self.assertNotIn("memory__read_graph", allowed)

    def test_tool_access_level_2_denies_memory_and_filesystem_writes(self) -> None:
        allowed, message = tool_access.tool_access_decision(
            "filesystem__write_file",
            {"path": "/tmp/level2.txt", "content": "x"},
            level=2,
            allowed_commands=[],
            workspace_paths=str(TEST_ROOT),
        )
        self.assertFalse(allowed)
        self.assertIn("tool is not allowed", message)

        allowed, message = tool_access.tool_access_decision(
            "memory__read_graph",
            {},
            level=2,
            allowed_commands=[],
            workspace_paths=str(TEST_ROOT),
        )
        self.assertFalse(allowed)
        self.assertIn("tool is not allowed", message)

    def test_tool_access_level_2_allows_playwright(self) -> None:
        allowed, message = tool_access.tool_access_decision(
            "playwright__browser_navigate",
            {"url": "https://example.com"},
            level=2,
            allowed_commands=[],
            workspace_paths=str(TEST_ROOT),
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

    def test_local_model_admin_commands_use_prefix_match_and_protected_paths(self) -> None:
        workspace = str(TEST_ROOT)
        self.assertIsNone(
            local_safety.validate_command(
                "git push origin dev",
                workspace,
                permission_level=3,
                allowed_commands=["git push"],
            )
        )
        self.assertIn(
            "not allowed",
            local_safety.validate_command(
                "git merge origin/dev",
                workspace,
                permission_level=3,
                allowed_commands=["git push"],
            ) or "",
        )
        self.assertIn(
            "protected path",
            local_safety.validate_command(
                f"sqlite3 {env.APEX_ROOT / 'state' / 'apex.db'} .schema",
                workspace,
                permission_level=3,
                allowed_commands=["sqlite3"],
            ) or "",
        )

    def test_sdk_admin_bash_gate_honors_allowlist(self) -> None:
        gate = streaming_mod._make_sdk_tool_gate(3, allowed_commands=["echo"])
        result = asyncio.run(
            gate(
                "Bash",
                {"command": 'echo "bash test"'},
                None,
            )
        )

        self.assertEqual(type(result).__name__, "PermissionResultAllow")
        self.assertIn(
            "protected path",
            local_safety.validate_path(str(env.APEX_ROOT / "state" / "config.json"), allow_write=True) or "",
        )

    def test_validate_backend_attachments_rejects_codex_attachments(self) -> None:
        attachment = self._create_uploaded_attachment("txt", b"notes")
        err = backends.validate_backend_attachments("codex", [attachment])
        self.assertEqual(
            err,
            "Attachments are not supported for Codex chats yet. Switch this chat to Claude to send files.",
        )

    def test_validate_backend_attachments_rejects_text_for_ollama_family(self) -> None:
        attachment = self._create_uploaded_attachment("txt", b"notes")
        err = backends.validate_backend_attachments("ollama", [attachment])
        self.assertEqual(
            err,
            "Text attachments are not supported for Ollama chats yet. Image attachments still work.",
        )

    def test_validate_backend_attachments_allows_images_for_ollama_family(self) -> None:
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00"
            b"\x18\xdd\x8d\xb1"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        attachment = self._create_uploaded_attachment("png", png, kind="image")
        err = backends.validate_backend_attachments("ollama", [attachment])
        self.assertIsNone(err)

    def test_websocket_send_rejects_codex_attachments_before_backend_dispatch(self) -> None:
        chat_id = self._create_direct_chat(model="codex:gpt-5.4")
        attachment = self._create_uploaded_attachment("txt", b"notes")

        with (
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=AssertionError("backend should not run")),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "see attached",
                    "attachments": [attachment],
                })
                msg = ws.receive_json()

        self.assertEqual(msg["type"], "error")
        self.assertIn("not supported for Codex chats yet", msg["message"])

    def test_websocket_send_routes_o3_to_responses_backend_when_api_key_present(self) -> None:
        chat_id = self._create_direct_chat(model="codex:o3")
        routed = {"ollama": 0}

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None, permission_policy=None):
            self.assertEqual(chat_id_arg, chat_id)
            self.assertEqual(prompt, "show reasoning")
            self.assertEqual(model, "codex:o3")
            routed["ollama"] += 1
            return {
                "text": "done",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "step by step",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler.env, "OPENAI_API_KEY", "sk-test"),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=AssertionError("codex CLI path should not run")),
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=fake_run_ollama_chat),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "show reasoning",
                })
                self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(routed["ollama"], 1)

    def test_websocket_send_routes_codex_gpt5_direct_chat_through_permission_aware_backend(self) -> None:
        chat_id = self._create_direct_chat(model="codex:gpt-5.4")
        db_mod._set_chat_tool_policy(
            chat_id,
            {
                "level": 3,
                "default_level": 2,
                "allowed_commands": [],
            },
        )
        routed = {"ollama": 0}

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None, permission_policy=None):
            self.assertEqual(chat_id_arg, chat_id)
            self.assertEqual(prompt, "show reasoning")
            self.assertEqual(model, "codex:gpt-5.4")
            self.assertEqual((permission_policy or {}).get("level"), 3)
            routed["ollama"] += 1
            return {
                "text": "done",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "step by step",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=AssertionError("codex CLI path should not run")),
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=fake_run_ollama_chat),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "show reasoning",
                })
                self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(routed["ollama"], 1)

    def test_websocket_send_rejects_text_attachments_for_ollama_before_dispatch(self) -> None:
        chat_id = self._create_direct_chat(model="qwen3:latest")
        attachment = self._create_uploaded_attachment("txt", b"notes")

        with (
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=AssertionError("backend should not run")),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "see attached",
                    "attachments": [attachment],
                })
                msg = ws.receive_json()

        self.assertEqual(msg["type"], "error")
        self.assertIn("Text attachments are not supported for Ollama chats yet", msg["message"])

    def test_group_multi_dispatch_propagates_image_attachments_to_supported_agents(self) -> None:
        chat_id = self._create_test_group_chat()
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x0cIDAT\x08\x99c```\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        attachment = self._create_uploaded_attachment("png", png, kind="image", name="puppy.png")
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id IN (?, ?)",
                ("ollama", "qwen3:latest", "queue-codeexpert", "queue-apex-assistant"),
            )
            conn.commit()
            conn.close()

        seen_attachments: dict[str, list[dict] | None] = {}

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None, permission_policy=None):
            seen_attachments[_current_group_profile_id.get("")] = attachments
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=fake_run_ollama_chat),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "@Queue CodeExpert @Queue Apex Assistant what do you see?",
                    "attachments": [attachment],
                })
                stream_end_count = 0
                while stream_end_count < 2:
                    msg = ws.receive_json()
                    if msg.get("type") == "stream_end":
                        stream_end_count += 1

        self.assertEqual(set(seen_attachments), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertTrue(all(items and items[0]["id"] == attachment["id"] for items in seen_attachments.values()))

    def test_group_multi_dispatch_falls_back_to_attachment_refs_for_unsupported_agents(self) -> None:
        chat_id = self._create_test_group_chat()
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x0cIDAT\x08\x99c```\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        attachment = self._create_uploaded_attachment("png", png, kind="image", name="puppy.png")
        attachment_url = f"/api/uploads/{attachment['id']}.png"
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id = ?",
                ("ollama", "qwen3:latest", "queue-codeexpert"),
            )
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id = ?",
                ("codex", "codex:gpt-5.4", "queue-apex-assistant"),
            )
            conn.commit()
            conn.close()

        seen_prompts: dict[str, str] = {}
        seen_attachments: dict[str, list[dict] | None] = {}

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None, permission_policy=None):
            seen_prompts[_current_group_profile_id.get("")] = prompt
            seen_attachments[_current_group_profile_id.get("")] = attachments
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_prompts[_current_group_profile_id.get("")] = prompt
            seen_attachments[_current_group_profile_id.get("")] = attachments
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=fake_run_ollama_chat),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "@Queue CodeExpert @Queue Apex Assistant what do you see?",
                    "attachments": [attachment],
                })
                stream_end_count = 0
                while stream_end_count < 2:
                    msg = ws.receive_json()
                    if msg.get("type") == "stream_end":
                        stream_end_count += 1

        self.assertEqual(seen_attachments["queue-codeexpert"][0]["id"], attachment["id"])
        self.assertEqual(seen_attachments["queue-apex-assistant"], [])
        self.assertIn("[Attached: puppy.png", seen_prompts["queue-apex-assistant"])
        self.assertIn(attachment_url, seen_prompts["queue-apex-assistant"])

    def test_group_relay_propagates_image_attachments_to_supported_agents(self) -> None:
        chat_id = self._create_test_group_chat()
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x0cIDAT\x08\x99c```\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        attachment = self._create_uploaded_attachment("png", png, kind="image", name="puppy.png")
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id IN (?, ?)",
                ("ollama", "qwen3:latest", "queue-codeexpert", "queue-apex-assistant"),
            )
            conn.commit()
            conn.close()

        primary = self._group_agent(chat_id, "queue-codeexpert")
        secondary = self._group_agent(chat_id, "queue-apex-assistant")
        seen_attachments: dict[str, list[dict] | None] = {}
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(
                primary if target_profile_id == primary["profile_id"] else secondary
            ),
            get_agent_relay_actions=lambda _chat_id, _response_text, group_agent, _chain, mention_depth: {
                "mentions_enabled": True,
                "mentioned_names": [secondary["name"]] if mention_depth == 0 else [],
                "current_chain": [group_agent["profile_id"]],
                "actions": (
                    [{
                        "type": "relay",
                        "target": dict(secondary),
                        "prompt": "Please inspect the same photo",
                        "depth": mention_depth + 1,
                    }]
                    if mention_depth == 0
                    else []
                ),
            },
        )

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None, permission_policy=None):
            seen_attachments[_current_group_profile_id.get("")] = attachments
            return {
                "text": "Handing off to @Queue Apex Assistant",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_run_ollama_chat", side_effect=fake_run_ollama_chat),
            self._client() as client,
        ):
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "send",
                    "chat_id": chat_id,
                    "prompt": "Inspect this image",
                    "target_agent": primary["profile_id"],
                    "attachments": [attachment],
                })
                stream_end_count = 0
                while stream_end_count < 2:
                    msg = ws.receive_json()
                    if msg.get("type") == "stream_end":
                        stream_end_count += 1

        self.assertEqual(set(seen_attachments), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertTrue(all(items and items[0]["id"] == attachment["id"] for items in seen_attachments.values()))

    def test_mcp_stdio_rejects_shell_interpreters(self) -> None:
        with mock.patch.object(dashboard_mod.shutil, "which", return_value="/bin/sh"):
            err = dashboard_mod._validate_mcp_server({
                "type": "stdio",
                "command": "/bin/sh",
                "args": ["-c", "echo hi"],
            })
        self.assertIn("Shell interpreters are not allowed", err or "")

    def test_mcp_stdio_rejects_shell_metacharacters_in_args(self) -> None:
        with mock.patch.object(dashboard_mod.shutil, "which", return_value="/opt/homebrew/bin/npx"):
            err = dashboard_mod._validate_mcp_server({
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp;curl attacker"],
            })
        self.assertIn("Shell metacharacters are not allowed", err or "")

    def test_mcp_stdio_rejects_blocked_env_keys(self) -> None:
        with mock.patch.object(dashboard_mod.shutil, "which", return_value="/opt/homebrew/bin/npx"):
            err = dashboard_mod._validate_mcp_server({
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"LD_PRELOAD": "/tmp/evil.so"},
            })
        self.assertIn("Blocked environment variables are not allowed", err or "")

    def test_mcp_stdio_accepts_allowed_launcher(self) -> None:
        with mock.patch.object(dashboard_mod.shutil, "which", return_value="/opt/homebrew/bin/npx"):
            err = dashboard_mod._validate_mcp_server({
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"MCP_LOG_LEVEL": "debug"},
            })
        self.assertIsNone(err)

    def test_websocket_set_model_requires_admin_token_and_whitelist(self) -> None:
        with self._client() as client:
            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({"action": "set_model", "model": "grok-4"})
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "error")
                self.assertIn("authorization required", msg["message"].lower())

            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "set_model",
                    "model": "definitely-not-a-model",
                    "admin_token": "admin-secret",
                })
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "error")
                self.assertIn("unsupported model", msg["message"].lower())

            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({
                    "action": "set_model",
                    "model": "grok-4",
                    "admin_token": "admin-secret",
                })
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "system")
                self.assertEqual(msg["subtype"], "model_changed")
                self.assertEqual(msg["model"], "grok-4")

    def test_group_relay_depth_cap_is_twenty_five(self) -> None:
        self.assertEqual(ws_handler.MAX_MENTION_DEPTH, 25)

    def test_group_members_use_effective_override_model(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._set_persona_model_override("queue-apex-assistant", "grok-4")

        members = db_mod._get_group_members(chat_id)
        assistant = next(m for m in members if m["profile_id"] == "queue-apex-assistant")

        self.assertEqual(assistant["model"], "grok-4")
        self.assertEqual(assistant["backend"], "xai")

    def test_group_target_agent_routes_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@Queue Apex Assistant take this one",
                        "target_agent": "queue-apex-assistant",
                    })
                    start = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-apex-assistant",
                    )
                    self.assertEqual(start["speaker_name"], "Queue Apex Assistant")
                    self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(seen_profiles, ["queue-apex-assistant"])

    def test_group_typed_mentions_route_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@Queue Apex Assistant take this one",
                    })
                    start = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-apex-assistant",
                    )
                    self.assertEqual(start["speaker_name"], "Queue Apex Assistant")
                    self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(seen_profiles, ["queue-apex-assistant"])

    def test_group_at_all_multi_dispatches_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@all weigh in",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_multi_mentions_dispatch_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@Queue CodeExpert @Queue Apex Assistant weigh in",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_multi_mentions_dispatch_without_premium_module_when_not_leading(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "testing @Queue CodeExpert @Queue Apex Assistant",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_at_all_multi_dispatches_even_with_target_agent(self) -> None:
        chat_id = self._create_test_group_chat()
        seen_profiles: list[str] = []
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(self._group_agent(chat_id, target_profile_id)),
            get_multi_dispatch_targets=lambda _chat_id, _prompt, _group_agent, _data: [],
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@all weigh in",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_owner_only_group_dispatch_blocks_agent_source(self) -> None:
        chat_id = self._create_test_group_chat()
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET tool_policy = ? WHERE id = ?",
                (
                    json.dumps({
                        "level": 1,
                        "default_level": 1,
                        "elevated_until": None,
                        "invoke_policy": "owner_only",
                        "allowed_commands": [],
                    }),
                    "queue-apex-assistant",
                ),
            )
            conn.commit()
            conn.close()

        class _FakeWS:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_json(self, payload: dict) -> None:
                self.sent.append(payload)

        fake_ws = _FakeWS()

        async def fake_run_codex_chat(*_args, **_kwargs):
            raise AssertionError("owner-only agent dispatch should not reach backend")

        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            asyncio.run(
                ws_handler._handle_send_action(
                    fake_ws,
                    {
                        "chat_id": chat_id,
                        "prompt": "take this one",
                        "target_agent": "queue-apex-assistant",
                        "_source": "agent",
                    },
                )
            )

        self.assertEqual(fake_ws.sent, [])

    def test_expired_elevation_reverts_to_default_level_inline(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "expired-admin",
                    "Expired Admin",
                    "expired-admin",
                    "E",
                    "expired admin test",
                    "ollama",
                    "qwen3:latest",
                    "expired admin test",
                    json.dumps({
                        "level": 3,
                        "default_level": 1,
                        "elevated_until": "2020-01-01T00:00:00+00:00",
                        "invoke_policy": "anyone",
                        "allowed_commands": ["git push"],
                    }),
                ),
            )
            conn.commit()
            conn.close()
        chat_id = db_mod._create_chat(
            title="Expired Admin Chat",
            model="qwen3:latest",
            profile_id="expired-admin",
        )

        chat = db_mod._get_chat(chat_id)
        policy = ws_handler._resolve_effective_tool_policy(chat_id, chat, None)

        self.assertEqual(policy["level"], 1)
        self.assertIsNone(policy["elevated_until"])
        self.assertEqual(db_mod._get_profile_tool_policy("expired-admin")["level"], 1)

    def test_dashboard_persona_elevate_and_revoke_round_trip(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "persona-admin-test",
                    "Persona Admin Test",
                    "persona-admin-test",
                    "P",
                    "persona admin test",
                    "ollama",
                    "qwen3:latest",
                    "persona admin test",
                    json.dumps({
                        "level": 1,
                        "default_level": 1,
                        "elevated_until": None,
                        "invoke_policy": "owner_only",
                        "allowed_commands": ["git push"],
                    }),
                ),
            )
            conn.commit()
            conn.close()

        with self._client() as client:
            elevate = client.post(
                "/admin/api/personas/persona-admin-test/elevate",
                json={"minutes": 5},
                headers=self._admin_headers(),
            )
            self.assertEqual(elevate.status_code, 200, elevate.text)
            elevated = elevate.json()
            self.assertTrue(elevated["ok"])
            self.assertEqual(elevated["tool_policy"]["level"], 3)
            self.assertEqual(elevated["tool_policy"]["default_level"], 1)
            self.assertEqual(elevated["tool_policy"]["allowed_commands"], ["git push"])
            self.assertTrue(elevated["expires_at"])

            revoke = client.post(
                "/admin/api/personas/persona-admin-test/revoke",
                headers=self._admin_headers(),
            )
            self.assertEqual(revoke.status_code, 200, revoke.text)
            revoked = revoke.json()
            self.assertEqual(revoked["tool_policy"]["level"], 1)
            self.assertIsNone(revoked["tool_policy"]["elevated_until"])

    def test_dashboard_persona_elevate_accepts_level_4(self) -> None:
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "persona-admin-4",
                    "Persona Admin 4",
                    "persona-admin-4",
                    "P",
                    "persona admin test",
                    "ollama",
                    "qwen3:latest",
                    "persona admin test",
                    json.dumps({
                        "level": 2,
                        "default_level": 2,
                        "elevated_until": None,
                        "invoke_policy": "anyone",
                        "allowed_commands": [],
                    }),
                ),
            )
            conn.commit()
            conn.close()

        with self._client() as client:
            elevate = client.post(
                "/admin/api/personas/persona-admin-4/elevate",
                json={"minutes": 10, "level": 4},
                headers=self._admin_headers(),
            )
            self.assertEqual(elevate.status_code, 200, elevate.text)
            elevated = elevate.json()
            self.assertEqual(elevated["tool_policy"]["level"], 4)
            self.assertEqual(elevated["tool_policy"]["default_level"], 2)
            self.assertTrue(elevated["expires_at"])

    def test_unassigned_direct_chat_uses_chat_level_tool_policy(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")
        policy = db_mod._set_chat_tool_policy(
            chat_id,
            {
                "level": 3,
                "default_level": 2,
                "elevated_until": None,
                "allowed_commands": ["git push"],
            },
        )

        self.assertEqual(policy["level"], 3)
        self.assertEqual(db_mod._get_chat_tool_policy(chat_id)["level"], 3)
        self.assertEqual(db_mod._get_chat_tool_policy(chat_id)["allowed_commands"], ["git push"])

    def test_expired_chat_level_elevation_reverts_to_default_level_inline(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")
        db_mod._set_chat_tool_policy(
            chat_id,
            {
                "level": 3,
                "default_level": 2,
                "elevated_until": "2020-01-01T00:00:00+00:00",
                "allowed_commands": ["git push"],
            },
        )

        chat = db_mod._get_chat(chat_id)
        policy = ws_handler._resolve_effective_tool_policy(chat_id, chat, None)

        self.assertEqual(policy["level"], 2)
        self.assertIsNone(policy["elevated_until"])
        self.assertEqual(db_mod._get_chat_tool_policy(chat_id)["level"], 2)

    def test_direct_chat_tool_policy_api_round_trip(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")

        with self._client() as client:
            update = client.put(
                f"/api/chats/{chat_id}/tool-policy",
                json={
                    "level": 3,
                    "default_level": 2,
                    "allowed_commands": ["git push", "sqlite3"],
                    "elevated_until": "2030-01-01T00:00:00+00:00",
                },
            )
            self.assertEqual(update.status_code, 200, update.text)
            updated = update.json()
            self.assertTrue(updated["ok"])
            self.assertEqual(updated["tool_policy"]["level"], 3)
            self.assertEqual(updated["tool_policy"]["default_level"], 2)
            self.assertEqual(updated["tool_policy"]["allowed_commands"], ["git push", "sqlite3"])

            fetched = client.get(f"/api/chats/{chat_id}/tool-policy")
            self.assertEqual(fetched.status_code, 200, fetched.text)
            self.assertEqual(fetched.json()["tool_policy"]["level"], 3)

            revoke = client.post(f"/api/chats/{chat_id}/tool-policy/revoke")
            self.assertEqual(revoke.status_code, 200, revoke.text)
            revoked = revoke.json()
            self.assertEqual(revoked["tool_policy"]["level"], 2)
            self.assertIsNone(revoked["tool_policy"]["elevated_until"])

    def test_direct_chat_tool_policy_api_accepts_level_4(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")

        with self._client() as client:
            update = client.put(
                f"/api/chats/{chat_id}/tool-policy",
                json={
                    "level": 4,
                    "default_level": 2,
                    "allowed_commands": ["echo"],
                    "elevated_until": "2030-01-01T00:00:00+00:00",
                },
            )
            self.assertEqual(update.status_code, 200, update.text)
            updated = update.json()
            self.assertEqual(updated["tool_policy"]["level"], 4)
            self.assertEqual(updated["tool_policy"]["default_level"], 2)
            self.assertEqual(updated["tool_policy"]["allowed_commands"], ["echo"])

            elevate = client.post(
                f"/api/chats/{chat_id}/tool-policy/elevate",
                json={"minutes": 10, "level": 4},
            )
            self.assertEqual(elevate.status_code, 200, elevate.text)
            elevated = elevate.json()
            self.assertEqual(elevated["tool_policy"]["level"], 4)
            self.assertTrue(elevated["expires_at"])

    def test_direct_chat_tool_policy_update_clears_stale_session(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")
        db_mod._update_chat(chat_id, claude_session_id="sess-stale")
        _session_context_sent.add(chat_id)

        async_disconnect = mock.AsyncMock()
        with self._client() as client, \
            mock.patch.object(routes_chat_mod, "_has_client", return_value=True), \
            mock.patch.object(routes_chat_mod, "_disconnect_client", async_disconnect):
            update = client.put(
                f"/api/chats/{chat_id}/tool-policy",
                json={
                    "level": 4,
                    "default_level": 2,
                    "allowed_commands": [],
                    "elevated_until": None,
                },
            )
            self.assertEqual(update.status_code, 200, update.text)

        async_disconnect.assert_awaited_once_with(chat_id)
        self.assertIsNone(db_mod._get_chat(chat_id)["claude_session_id"])
        self.assertNotIn(chat_id, _session_context_sent)

    def test_sdk_client_reconnects_when_allowed_commands_change_at_same_level(self) -> None:
        chat_id = self._create_direct_chat(model="claude-opus-4.6")

        class _FakeClient:
            def __init__(self, label: str) -> None:
                self.label = label
                self.connected = False
                self.disconnected = False

            async def connect(self) -> None:
                self.connected = True

            async def disconnect(self) -> None:
                self.disconnected = True

        existing = _FakeClient("existing")
        _clients[chat_id] = existing
        _client_permission_levels[chat_id] = 3
        _client_permission_policies[chat_id] = streaming_mod._permission_policy_signature(3, ["git push"])

        created: list[_FakeClient] = []

        def _make_fake_client(_options):
            client = _FakeClient("new")
            created.append(client)
            return client

        async def _noop():
            return None

        with mock.patch.object(streaming_mod, "_client_is_alive", return_value=True), \
            mock.patch.object(streaming_mod, "_evict_lru_client", side_effect=_noop), \
            mock.patch.object(agent_sdk, "ensure_fresh_token", return_value=None), \
            mock.patch.object(streaming_mod, "_make_options", return_value=object()), \
            mock.patch.object(streaming_mod, "ClaudeSDKClient", side_effect=_make_fake_client):
            client = asyncio.run(
                streaming_mod._get_or_create_client(
                    chat_id,
                    model="claude-opus-4.6",
                    permission_level=3,
                    allowed_commands=["sqlite3"],
                )
            )

        self.assertIsNot(client, existing)
        self.assertTrue(existing.disconnected)
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].connected)
        self.assertEqual(_client_permission_levels[chat_id], 3)
        self.assertEqual(
            _client_permission_policies[chat_id],
            streaming_mod._permission_policy_signature(3, ["sqlite3"]),
        )

    def test_sdk_level_4_uses_bypass_permissions(self) -> None:
        opts = streaming_mod._make_options(
            model="claude-sonnet-4-6",
            client_key="chat-1",
            chat_id="chat-1",
            permission_level=4,
        )
        self.assertEqual(opts.permission_mode, "bypassPermissions")

    def test_dashboard_workspace_path_normalizes_multiline_roots(self) -> None:
        normalized = dashboard_mod._normalize_workspace_path_value(
            "/Users/dana/project-a\n/Users/dana/project-b\n\n/Users/dana/project-a"
        )
        self.assertEqual(
            normalized,
            "/Users/dana/project-a:/Users/dana/project-b",
        )

    def test_config_schema_marks_workspace_path_multiline(self) -> None:
        spec = dashboard_mod.SCHEMA["workspace"]["path"]
        self.assertTrue(spec["multiline"])
        self.assertIn("project-a", spec["placeholder"])

    def test_dashboard_html_keeps_multiline_workspace_js_escaped(self) -> None:
        self.assertIn(
            'split(":").join("\\n")',
            dashboard_html_mod.DASHBOARD_HTML,
        )
        self.assertIn('data-page="policy"', dashboard_html_mod.DASHBOARD_HTML)
        self.assertIn('id="persona-tool-policy"></select>', dashboard_html_mod.DASHBOARD_HTML)

    def test_sdk_pre_tool_hook_blocks_level_3_non_allowlisted_date(self) -> None:
        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Bash",
            {"command": "date +%s"},
            level=3,
            allowed_commands=["echo", "grep"],
        )
        self.assertFalse(allowed)
        self.assertIn("command is not allowed", message)

    def test_sdk_pre_tool_hook_level_3_allows_allowlisted_date_and_tmp_write(self) -> None:
        diagnostics = [
            "echo", "date", "grep", "rg", "find", "ls", "cat", "head", "tail",
            "sed", "awk", "cut", "sort", "uniq", "tr", "wc", "ps", "lsof",
            "curl", "stat", "file", "realpath", "basename", "dirname",
            "printenv", "env",
        ]
        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Bash",
            {"command": "date +%s"},
            level=3,
            allowed_commands=diagnostics,
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Write",
            {"file_path": "/tmp/apex_level4_check2.txt", "content": "1775331902"},
            level=3,
            allowed_commands=diagnostics,
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Read",
            {"file_path": "/tmp/apex_level4_check2.txt"},
            level=3,
            allowed_commands=diagnostics,
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

    def test_sdk_pre_tool_hook_level_3_allows_allowlisted_shell_pipelines(self) -> None:
        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Bash",
            {"command": "ps aux | grep apex"},
            level=3,
            allowed_commands=["ps", "grep"],
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

    def test_sdk_pre_tool_hook_level_3_still_blocks_write_outside_workspace_and_tmp(self) -> None:
        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Write",
            {"file_path": "/var/root/apex_level4_check2.txt", "content": "1775331902"},
            level=3,
            allowed_commands=["echo"],
        )
        self.assertFalse(allowed)
        self.assertIn("outside allowed admin paths", message)

    def test_sdk_pre_tool_hook_allows_level_4_any_path_and_command(self) -> None:
        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Bash",
            {"command": "date +%s"},
            level=4,
            allowed_commands=[],
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

        allowed, message = streaming_mod._sdk_pre_tool_use_decision(
            "Write",
            {"file_path": "/tmp/apex_level4_check2.txt", "content": "1775331902"},
            level=4,
            allowed_commands=[],
        )
        self.assertTrue(allowed)
        self.assertEqual(message, "")

    def test_group_multi_mentions_supplement_partial_premium_targets(self) -> None:
        chat_id = self._create_test_group_chat()
        primary = self._group_agent(chat_id, "queue-codeexpert")
        secondary = self._group_agent(chat_id, "queue-apex-assistant")
        seen_profiles: list[str] = []
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(
                primary if target_profile_id == primary["profile_id"] else secondary
            ),
            get_multi_dispatch_targets=lambda _chat_id, _prompt, _group_agent, _data: [dict(primary)],
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_resolve_group_agent", return_value=dict(primary)),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@Queue CodeExpert @Queue Apex Assistant weigh in",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_multi_mentions_supplement_partial_premium_targets_when_not_leading(self) -> None:
        chat_id = self._create_test_group_chat()
        primary = self._group_agent(chat_id, "queue-codeexpert")
        secondary = self._group_agent(chat_id, "queue-apex-assistant")
        seen_profiles: list[str] = []
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(
                primary if target_profile_id == primary["profile_id"] else secondary
            ),
            get_multi_dispatch_targets=lambda _chat_id, _prompt, _group_agent, _data: [dict(primary)],
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_resolve_group_agent", return_value=dict(primary)),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "testing @Queue CodeExpert @Queue Apex Assistant",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_primary_fallback_uses_effective_model_instead_of_stale_chat_model(self) -> None:
        chat_id = self._create_test_group_chat()
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id = ?",
                ("claude", "claude-sonnet-4-6", "queue-codeexpert"),
            )
            conn.commit()
            conn.close()
        db_mod._set_persona_model_override("queue-codeexpert", "codex:gpt-5.4")
        db_mod._update_chat(chat_id, model="claude-sonnet-4-6")

        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            seen_profiles.append(_current_group_profile_id.get(""))
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Primary should answer with the override model",
                    })
                    start = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-codeexpert",
                    )
                    self.assertEqual(start["speaker_name"], "Queue CodeExpert")
                    self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(seen_profiles, ["queue-codeexpert"])

    def test_busy_group_agent_turn_is_queued_while_other_agent_can_run(self) -> None:
        chat_id = self._create_test_group_chat()
        release_codeexpert = asyncio.Event()
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: self._group_agent(chat_id, target_profile_id),
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            active_profile = _current_group_profile_id.get("")
            if active_profile == "queue-codeexpert":
                await release_codeexpert.wait()
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "First for CodeExpert",
                        "target_agent": "queue-codeexpert",
                    })
                    self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-codeexpert",
                    )

                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Second for CodeExpert",
                        "target_agent": "queue-codeexpert",
                    })
                    queued = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_queued" and msg.get("speaker_id") == "queue-codeexpert",
                    )
                    self.assertEqual(queued["position"], 1)

                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Immediate for Apex Assistant",
                        "target_agent": "queue-apex-assistant",
                    })
                    other_agent = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-apex-assistant",
                    )
                    self.assertEqual(other_agent["speaker_name"], "Queue Apex Assistant")

                    release_codeexpert.set()
                    dequeued = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-codeexpert",
                    )
                    self.assertEqual(dequeued["speaker_name"], "Queue CodeExpert")

    def test_busy_group_agent_blocks_third_queued_turn_after_two(self) -> None:
        chat_id = self._create_test_group_chat()
        release_codeexpert = asyncio.Event()
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: self._group_agent(chat_id, target_profile_id),
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            if _current_group_profile_id.get("") == "queue-codeexpert":
                await release_codeexpert.wait()
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "First for CodeExpert",
                        "target_agent": "queue-codeexpert",
                    })
                    self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "stream_start" and msg.get("speaker_id") == "queue-codeexpert",
                    )

                    for expected_position, prompt in ((1, "Second"), (2, "Third")):
                        ws.send_json({
                            "action": "send",
                            "chat_id": chat_id,
                            "prompt": f"{prompt} for CodeExpert",
                            "target_agent": "queue-codeexpert",
                        })
                        queued = self._receive_until(
                            ws,
                            lambda msg: msg.get("type") == "stream_queued" and msg.get("speaker_id") == "queue-codeexpert",
                        )
                        self.assertEqual(queued["position"], expected_position)

                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Fourth for CodeExpert",
                        "target_agent": "queue-codeexpert",
                    })
                    overflow = self._receive_until(
                        ws,
                        lambda msg: msg.get("type") == "error" and msg.get("stream_id"),
                    )
                    self.assertIn("already has 2 queued turns", overflow["message"])

        release_codeexpert.set()

    def test_group_roster_prompt_includes_cross_chat_agent_load(self) -> None:
        chat_id_one = self._create_test_group_chat()
        chat_id_two = self._create_test_group_chat()
        premium = SimpleNamespace(
            get_group_roster_prompt=lambda _chat_id, _user_message="": "<system-reminder>\n# Group Roster\n- base\n</system-reminder>\n\n",
        )
        loop = asyncio.new_event_loop()
        blocker = asyncio.Event()
        task = loop.create_task(blocker.wait())
        started_at = time.monotonic() - 45
        streaming_mod._set_active_send_task(
            chat_id_one,
            "stream-one",
            task,
            name="Queue CodeExpert",
            avatar="💻",
            profile_id="queue-codeexpert",
        )
        streaming_mod._update_active_send_task(
            chat_id_one,
            "stream-one",
            started_at=started_at,
        )
        _queued_turns["other-chat:queue-codeexpert"] = deque([
            {"profile_id": "queue-codeexpert"},
            {"profile_id": "queue-codeexpert"},
        ])

        try:
            with mock.patch.object(context_mod, "_premium", premium):
                prompt = context_mod._get_group_roster_prompt(chat_id_two, user_message="@queue-codeexpert help")
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(task)
            loop.close()

        self.assertIn("# Group Roster", prompt)
        self.assertIn("The channel roster above is authoritative.", prompt)
        self.assertIn("ignore SDK client counts", prompt)
        self.assertIn("# Agent Load", prompt)
        self.assertIn("Queue CodeExpert [queue-codeexpert] 💻", prompt)
        self.assertIn("queue: 2/2", prompt)
        self.assertIn("Queue Apex Assistant [queue-apex-assistant] ✨ — 🟢 idle", prompt)

    def test_group_roster_prompt_includes_strict_relay_state(self) -> None:
        chat_id = self._create_test_group_chat()
        premium = SimpleNamespace(
            get_group_roster_prompt=lambda _chat_id, _user_message="": "<system-reminder>\n# Group Roster\n- base\n</system-reminder>\n\n",
        )
        self.assertTrue(ws_handler._strict_relay_requested(
            "Start a relay test. Each agent should respond exactly once and pass it off until all agents have spoken."
        ))
        ws_handler._start_strict_group_relay(chat_id, first_profile_id="queue-codeexpert")
        with mock.patch.object(context_mod, "_premium", premium):
            prompt = context_mod._get_group_roster_prompt(chat_id, user_message="Start relay")

        self.assertIn("# Strict Relay", prompt)
        self.assertIn("Agents already responded this round: none yet", prompt)
        self.assertIn("The next valid handoff target is @Queue CodeExpert.", prompt)

    def test_group_workspace_context_is_scoped_per_agent_in_group_chats(self) -> None:
        chat_id = self._create_test_group_chat()
        (TEST_ROOT / "APEX.md").write_text("Project instructions here", encoding="utf-8")
        memory_dir = TEST_ROOT / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "MEMORY.md").write_text("Persistent memory here", encoding="utf-8")

        with (
            mock.patch.object(context_mod, "_get_live_state_snapshot", return_value=""),
            mock.patch.object(context_mod, "_get_recent_exchange_context", return_value=""),
        ):
            token = _current_group_profile_id.set("queue-codeexpert")
            try:
                first_agent_ctx = context_mod._get_workspace_context(chat_id)
                repeated_first_agent_ctx = context_mod._get_workspace_context(chat_id)
            finally:
                _current_group_profile_id.reset(token)

            token = _current_group_profile_id.set("queue-apex-assistant")
            try:
                second_agent_ctx = context_mod._get_workspace_context(chat_id)
            finally:
                _current_group_profile_id.reset(token)

        self.assertIn("Project instructions here", first_agent_ctx)
        self.assertIn("Persistent memory here", first_agent_ctx)
        self.assertEqual(repeated_first_agent_ctx, "")
        self.assertIn("Project instructions here", second_agent_ctx)
        self.assertIn("Persistent memory here", second_agent_ctx)
        self.assertIn(f"{chat_id}:queue-codeexpert", _session_context_sent)
        self.assertIn(f"{chat_id}:queue-apex-assistant", _session_context_sent)

        context_mod._clear_session_context(chat_id)

        self.assertNotIn(f"{chat_id}:queue-codeexpert", _session_context_sent)
        self.assertNotIn(f"{chat_id}:queue-apex-assistant", _session_context_sent)

    def test_premium_loader_dev_mode_falls_back_to_encrypted_modules_when_plaintext_missing(self) -> None:
        loader = premium_loader.PremiumLoader(REPO_ROOT / "server", TEST_ROOT / "state")
        sentinel = object()

        with (
            mock.patch.object(premium_loader.env, "DEV_MODE", True),
            mock.patch.object(loader, "_load_plaintext", return_value=None) as load_plaintext,
            mock.patch.object(loader, "load_feature_key", return_value="feature-key") as load_feature_key,
            mock.patch.object(loader, "_load_encrypted", return_value=sentinel) as load_encrypted,
        ):
            loaded = loader.load_premium_module("context_premium")

        self.assertIs(loaded, sentinel)
        load_plaintext.assert_called_once_with("context_premium")
        load_feature_key.assert_called_once_with()
        load_encrypted.assert_called_once_with("context_premium", "feature-key")

    def test_group_relay_self_mention_is_suppressed(self) -> None:
        chat_id = self._create_test_group_chat()
        agent = self._group_agent(chat_id, "queue-codeexpert")
        relay_agent = dict(agent)
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(self._group_agent(chat_id, target_profile_id)),
            get_agent_relay_actions=lambda _chat_id, _response_text, group_agent, _chain, mention_depth: {
                "mentions_enabled": True,
                "mentioned_names": [group_agent["name"]] if mention_depth == 0 else [],
                "current_chain": [group_agent["profile_id"]],
                "actions": (
                    [{
                        "type": "relay",
                        "target": relay_agent,
                        "prompt": "Self relay",
                        "depth": mention_depth + 1,
                    }]
                    if mention_depth == 0
                    else []
                ),
            },
        )
        created_send_tasks = 0
        real_create_task = ws_handler.asyncio.create_task

        def counting_create_task(coro, *args, **kwargs):
            nonlocal created_send_tasks
            code = getattr(coro, "cr_code", None)
            if getattr(code, "co_name", "") == "_handle_send_action":
                created_send_tasks += 1
            return real_create_task(coro, *args, **kwargs)

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            return {
                "text": "Reply with @Queue CodeExpert",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
            mock.patch.object(ws_handler.asyncio, "create_task", side_effect=counting_create_task),
            mock.patch.object(ws_handler, "log") as log_mock,
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(created_send_tasks, 1)
        self.assertTrue(
            any("relay blocked (self-mention)" in str(call.args[0]) for call in log_mock.call_args_list)
        )

    def test_group_relay_specific_mentions_work_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_profiles.append(profile_id)
            text = (
                "Please take this one, @Queue Apex Assistant."
                if profile_id == "queue-codeexpert"
                else "Handled."
            )
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_relay_multiple_markdown_mentions_dispatch_without_premium_module(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, is_system, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, datetime('now'), datetime('now'))
                """,
                (
                    "queue-debugger",
                    "Queue Debugger",
                    "queue-debugger",
                    "🪲",
                    "Queue test agent",
                    "codex",
                    "codex:gpt-5.4",
                    "Queue test agent",
                ),
            )
            conn.commit()
            conn.close()
        db_mod._add_group_member(chat_id, "queue-debugger", routing_mode="mentioned", display_order=2)

        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_profiles.append(profile_id)
            text = (
                "Passing to **@Queue Apex Assistant** and **@Queue Debugger**."
                if profile_id == "queue-codeexpert"
                else "Handled."
            )
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 3:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(
            started_speakers,
            {"queue-codeexpert", "queue-apex-assistant", "queue-debugger"},
        )
        self.assertEqual(
            set(seen_profiles),
            {"queue-codeexpert", "queue-apex-assistant", "queue-debugger"},
        )
        self.assertEqual(len(seen_profiles), 3)

    def test_group_relay_specific_mentions_survive_incidental_agent_at_all_text(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_profiles: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_profiles.append(profile_id)
            text = (
                "Please take this one, @Queue Apex Assistant.\n\n"
                "Current dev commits:\n"
                "- Restrict agent @all relay\n"
                "- Fix non-leading multi-mention dispatch"
                if profile_id == "queue-codeexpert"
                else "Handled."
            )
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: set[str] = set()
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.add(msg.get("speaker_id"))
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(started_speakers, {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(set(seen_profiles), {"queue-codeexpert", "queue-apex-assistant"})
        self.assertEqual(len(seen_profiles), 2)

    def test_group_relay_missing_single_target_warns_and_self_corrects(self) -> None:
        chat_id = self._create_test_group_chat()
        self._upsert_test_profile("queue-debugger", "Queue Debugger", avatar="🛠️")
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[tuple[str, str]] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append((profile_id, prompt))
            if profile_id == "queue-codeexpert":
                if sum(1 for pid, _ in seen_calls if pid == "queue-codeexpert") == 1:
                    text = "Passing to @Queue Debugger."
                else:
                    text = "Passing to @Queue Apex Assistant."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        system_messages: list[str] = []
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 3:
                        msg = ws.receive_json()
                        if msg.get("type") == "system_message":
                            system_messages.append(msg.get("text") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertTrue(
            any("@Queue Debugger isn't in this room." in text for text in system_messages)
        )
        self.assertTrue(
            any("@Queue Apex Assistant" in text for text in system_messages)
        )
        self.assertEqual(
            [profile_id for profile_id, _prompt in seen_calls],
            ["queue-codeexpert", "queue-codeexpert", "queue-apex-assistant"],
        )
        self.assertIn("@Queue Debugger isn't in this room.", seen_calls[1][1])
        self.assertIn("@Queue Apex Assistant", seen_calls[1][1])

    def test_group_relay_missing_target_warns_without_self_correction_when_valid_target_exists(self) -> None:
        chat_id = self._create_test_group_chat()
        self._upsert_test_profile("queue-debugger", "Queue Debugger", avatar="🛠️")
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append(profile_id)
            text = (
                "Passing to @Queue Apex Assistant and @Queue Debugger."
                if profile_id == "queue-codeexpert"
                else "Handled."
            )
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        system_messages: list[str] = []
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "system_message":
                            system_messages.append(msg.get("text") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(seen_calls, ["queue-codeexpert", "queue-apex-assistant"])
        self.assertTrue(
            any("@Queue Debugger isn't in this room." in text for text in system_messages)
        )
        self.assertTrue(
            any("@Queue Apex Assistant" in text for text in system_messages)
        )

    def test_group_relay_roster_uncertainty_self_corrects_with_authoritative_roster(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[tuple[str, str]] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append((profile_id, prompt))
            if profile_id == "queue-codeexpert":
                if sum(1 for pid, _ in seen_calls if pid == "queue-codeexpert") == 1:
                    text = "I am unsure who is present in this room. I cannot see a live room roster."
                else:
                    text = "Passing to @Queue Apex Assistant."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        started_speakers: list[str] = []
        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 3:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.append(msg.get("speaker_id") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(
            [profile_id for profile_id, _prompt in seen_calls],
            ["queue-codeexpert", "queue-codeexpert", "queue-apex-assistant"],
        )
        self.assertEqual(
            started_speakers.count("queue-codeexpert"),
            2,
        )
        self.assertIn(
            "The agents currently in this room are: @Queue Apex Assistant.",
            seen_calls[1][1],
        )
        self.assertIn(
            "Do not use tools, files, SDK client counts, or inferred presence signals",
            seen_calls[1][1],
        )

    def test_group_relay_roster_feedback_disables_tools(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id IN (?, ?)",
                ("claude", "claude-sonnet-4-6", "queue-codeexpert", "queue-apex-assistant"),
            )
            conn.commit()
            conn.close()

        permission_levels: list[tuple[str, int]] = []
        seen_profiles: list[str] = []

        async def fake_get_or_create_client(
            client_key: str,
            model=None,
            permission_level=None,
            allowed_commands=None,
        ):
            permission_levels.append((client_key, int(permission_level)))
            return object()

        async def fake_run_query_turn(client, make_query_input, chat_id_arg: str):
            profile_id = _current_group_profile_id.get("")
            seen_profiles.append(profile_id)
            if profile_id == "queue-codeexpert":
                if seen_profiles.count("queue-codeexpert") == 1:
                    text = "I am unsure who is present in this room. I cannot see a live room roster."
                else:
                    text = "Passing to @Queue Apex Assistant."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_get_or_create_client", side_effect=fake_get_or_create_client), \
            mock.patch.object(ws_handler, "_run_query_turn", side_effect=fake_run_query_turn):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 3:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        codeexpert_levels = [
            level for client_key, level in permission_levels
            if client_key == f"{chat_id}:queue-codeexpert"
        ]
        self.assertEqual(codeexpert_levels[:2], [2, 0])
        self.assertIn((f"{chat_id}:queue-apex-assistant", 2), permission_levels)

    def test_group_codex_threads_are_scoped_per_agent(self) -> None:
        chat_id = self._create_test_group_chat()

        token = _current_group_profile_id.set("queue-codeexpert")
        try:
            backends._persist_codex_thread(chat_id, "thread-codeexpert", 1)
            codeexpert_state = backends._get_codex_thread_state(chat_id)
        finally:
            _current_group_profile_id.reset(token)

        token = _current_group_profile_id.set("queue-apex-assistant")
        try:
            assistant_initial_state = backends._get_codex_thread_state(chat_id)
            backends._persist_codex_thread(chat_id, "thread-assistant", 2)
            assistant_state = backends._get_codex_thread_state(chat_id)
        finally:
            _current_group_profile_id.reset(token)

        self.assertEqual(codeexpert_state[:2], ("thread-codeexpert", 1))
        self.assertEqual(assistant_initial_state[:2], ("", 0))
        self.assertEqual(assistant_state[:2], ("thread-assistant", 2))
        self.assertEqual(backends._codex_threads[f"{chat_id}:queue-codeexpert"], "thread-codeexpert")
        self.assertEqual(backends._codex_threads[f"{chat_id}:queue-apex-assistant"], "thread-assistant")

        settings = db_mod._get_chat_settings(chat_id)
        self.assertEqual(
            settings.get("codex_threads_by_profile"),
            {
                "queue-codeexpert": "thread-codeexpert",
                "queue-apex-assistant": "thread-assistant",
            },
        )
        self.assertEqual(
            settings.get("codex_thread_turns_by_profile"),
            {
                "queue-codeexpert": 1,
                "queue-apex-assistant": 2,
            },
        )

    def test_group_strict_relay_disables_tools_from_initial_turn(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute(
                "UPDATE agent_profiles SET backend = ?, model = ? WHERE id IN (?, ?)",
                ("claude", "claude-sonnet-4-6", "queue-codeexpert", "queue-apex-assistant"),
            )
            conn.commit()
            conn.close()

        permission_levels: list[tuple[str, int]] = []
        seen_profiles: list[str] = []

        async def fake_get_or_create_client(
            client_key: str,
            model=None,
            permission_level=None,
            allowed_commands=None,
        ):
            permission_levels.append((client_key, int(permission_level)))
            return object()

        async def fake_run_query_turn(client, make_query_input, chat_id_arg: str):
            profile_id = _current_group_profile_id.get("")
            seen_profiles.append(profile_id)
            text = "Passing to @Queue Apex Assistant." if profile_id == "queue-codeexpert" else "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_get_or_create_client", side_effect=fake_get_or_create_client), \
            mock.patch.object(ws_handler, "_run_query_turn", side_effect=fake_run_query_turn):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": (
                            "Start a relay test. Each agent should respond exactly once, in order, "
                            "by @ mentioning the next agent who has not spoken yet. Stop after every "
                            "agent currently in the room has responded once."
                        ),
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(seen_profiles, ["queue-codeexpert", "queue-apex-assistant"])
        self.assertEqual(
            permission_levels,
            [
                (f"{chat_id}:queue-codeexpert", 0),
                (f"{chat_id}:queue-apex-assistant", 0),
            ],
        )

    def test_group_strict_relay_excludes_system_personas_from_ordering(self) -> None:
        chat_id = self._create_test_group_chat()
        self._upsert_test_profile("sys-guide", "Guide", avatar="🧭", is_system=True)
        db_mod._add_group_member(chat_id, "sys-guide", routing_mode="mentioned", display_order=0)
        state = ws_handler._start_strict_group_relay(chat_id, first_profile_id="queue-codeexpert")

        self.assertEqual(
            state.ordered_profile_ids,
            ["queue-codeexpert", "queue-apex-assistant"],
        )
        self.assertEqual(state.next_profile_id, "queue-codeexpert")

    def test_group_strict_relay_uncertainty_feedback_names_exact_next_agent(self) -> None:
        chat_id = self._create_test_group_chat()
        self._add_test_group_member(chat_id, "queue-planner", "Queue Planner", avatar="📊", display_order=2)
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[tuple[str, str]] = []
        system_messages: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append((profile_id, prompt))
            if profile_id == "queue-codeexpert":
                if sum(1 for pid, _ in seen_calls if pid == "queue-codeexpert") == 1:
                    text = "I am unsure who is present in this room."
                else:
                    text = "Passing to @Queue Apex Assistant."
            elif profile_id == "queue-apex-assistant":
                text = "Passing to @Queue Planner."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": (
                            "Start a relay test. Each agent should respond exactly once, in order, "
                            "by @ mentioning the next agent who has not spoken yet. Stop after every "
                            "agent currently in the room has responded once."
                        ),
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 4:
                        msg = ws.receive_json()
                        if msg.get("type") == "system_message":
                            system_messages.append(msg.get("text") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(
            [profile_id for profile_id, _prompt in seen_calls],
            [
                "queue-codeexpert",
                "queue-codeexpert",
                "queue-apex-assistant",
                "queue-planner",
            ],
        )
        self.assertTrue(
            any("Strict relay is active. The next agent is @Queue Apex Assistant." in text for text in system_messages)
        )
        self.assertIn("Next agent to hand off to is @Queue Apex Assistant.", seen_calls[1][1])
        self.assertIn("Agents already responded: @Queue CodeExpert.", seen_calls[1][1])

    def test_group_strict_relay_wrong_present_target_self_corrects(self) -> None:
        chat_id = self._create_test_group_chat()
        self._add_test_group_member(chat_id, "queue-planner", "Queue Planner", avatar="📊", display_order=2)
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[tuple[str, str]] = []
        started_speakers: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append((profile_id, prompt))
            if profile_id == "queue-codeexpert":
                if sum(1 for pid, _ in seen_calls if pid == "queue-codeexpert") == 1:
                    text = "Passing to @Queue Planner."
                else:
                    text = "Passing to @Queue Apex Assistant."
            elif profile_id == "queue-apex-assistant":
                text = "Passing to @Queue Planner."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": (
                            "Start a relay test. Each agent should respond exactly once, in order, "
                            "by @ mentioning the next agent who has not spoken yet."
                        ),
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 4:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_start":
                            started_speakers.append(msg.get("speaker_id") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(
            started_speakers,
            [
                "queue-codeexpert",
                "queue-codeexpert",
                "queue-apex-assistant",
                "queue-planner",
            ],
        )
        self.assertIn("Next agent to hand off to is @Queue Apex Assistant.", seen_calls[1][1])
        self.assertNotIn("queue-planner", seen_calls[1][1].casefold().split("next agent to hand off to is", 1)[-1])

    def test_group_relay_plain_english_at_mention_does_not_trigger_missing_target_warning(self) -> None:
        chat_id = self._create_test_group_chat()
        db_mod._update_chat_settings(chat_id, {"agent_mentions_enabled": True})
        seen_calls: list[tuple[str, str]] = []
        system_messages: list[str] = []

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            profile_id = _current_group_profile_id.get("")
            seen_calls.append((profile_id, prompt))
            if profile_id == "queue-codeexpert":
                if sum(1 for pid, _ in seen_calls if pid == "queue-codeexpert") == 1:
                    text = "I can't @mention the next agent without guessing. I am unsure who is present."
                else:
                    text = "Passing to @Queue Apex Assistant."
            else:
                text = "Handled."
            return {
                "text": text,
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", None), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": "queue-codeexpert",
                    })
                    stream_end_count = 0
                    while stream_end_count < 3:
                        msg = ws.receive_json()
                        if msg.get("type") == "system_message":
                            system_messages.append(msg.get("text") or "")
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertFalse(any("@mention" in text for text in system_messages))
        self.assertIn(
            "The agents currently in this room are: @Queue Apex Assistant.",
            seen_calls[1][1],
        )

    def test_group_relay_agent_at_all_is_suppressed(self) -> None:
        chat_id = self._create_test_group_chat()
        primary = self._group_agent(chat_id, "queue-codeexpert")
        secondary = self._group_agent(chat_id, "queue-apex-assistant")
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(self._group_agent(chat_id, target_profile_id)),
            get_agent_relay_actions=lambda _chat_id, _response_text, group_agent, _chain, mention_depth: {
                "mentions_enabled": True,
                "mentioned_names": ["all"] if mention_depth == 0 else [],
                "current_chain": [group_agent["profile_id"]],
                "actions": (
                    [{
                        "type": "relay",
                        "target": dict(secondary),
                        "prompt": "Broadcast relay",
                        "depth": mention_depth + 1,
                    }]
                    if mention_depth == 0
                    else []
                ),
            },
        )
        created_send_tasks = 0
        real_create_task = ws_handler.asyncio.create_task

        def counting_create_task(coro, *args, **kwargs):
            nonlocal created_send_tasks
            code = getattr(coro, "cr_code", None)
            if getattr(code, "co_name", "") == "_handle_send_action":
                created_send_tasks += 1
            return real_create_task(coro, *args, **kwargs)

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            return {
                "text": "Reply with @all",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with self._fast_relay_context(), \
            mock.patch.object(ws_handler, "_ws_premium", premium), \
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat), \
            mock.patch.object(ws_handler.asyncio, "create_task", side_effect=counting_create_task), \
            mock.patch.object(ws_handler, "log") as log_mock:
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "Start relay",
                        "target_agent": primary["profile_id"],
                    })
                    self._receive_until(ws, lambda msg: msg.get("type") == "stream_end")

        self.assertEqual(created_send_tasks, 1)
        self.assertTrue(
            any("relay blocked (@all reserved for user)" in str(call.args[0]) for call in log_mock.call_args_list)
        )

    def test_user_multi_dispatch_skips_primary_agent(self) -> None:
        chat_id = self._create_test_group_chat()
        primary = self._group_agent(chat_id, "queue-codeexpert")
        secondary = self._group_agent(chat_id, "queue-apex-assistant")
        premium = SimpleNamespace(
            resolve_target_agent=lambda _chat_id, _prompt, target_profile_id: dict(
                primary if target_profile_id == primary["profile_id"] else secondary
            ),
            get_multi_dispatch_targets=lambda _chat_id, _prompt, _group_agent, _data: [primary, secondary],
            get_agent_relay_actions=lambda *_args, **_kwargs: {
                "mentions_enabled": True,
                "mentioned_names": [],
                "current_chain": [],
                "actions": [],
            },
        )
        created_send_tasks = 0
        real_create_task = ws_handler.asyncio.create_task

        def counting_create_task(coro, *args, **kwargs):
            nonlocal created_send_tasks
            code = getattr(coro, "cr_code", None)
            if getattr(code, "co_name", "") == "_handle_send_action":
                created_send_tasks += 1
            return real_create_task(coro, *args, **kwargs)

        async def fake_run_codex_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
            return {
                "text": f"reply:{prompt}",
                "is_error": False,
                "error": None,
                "cost_usd": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "session_id": None,
                "thinking": "",
                "tool_events": "[]",
            }

        with (
            mock.patch.object(ws_handler, "_ws_premium", premium),
            mock.patch.object(ws_handler, "_resolve_group_agent", return_value=dict(primary)),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
            mock.patch.object(ws_handler.asyncio, "create_task", side_effect=counting_create_task),
            mock.patch.object(ws_handler, "log") as log_mock,
        ):
            with self._client() as client:
                with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                    ws.send_json({
                        "action": "send",
                        "chat_id": chat_id,
                        "prompt": "@all weigh in",
                    })
                    stream_end_count = 0
                    while stream_end_count < 2:
                        msg = ws.receive_json()
                        if msg.get("type") == "stream_end":
                            stream_end_count += 1

        self.assertEqual(created_send_tasks, 2)
        self.assertTrue(
            any("user multi-dispatch blocked (self-target)" in str(call.args[0]) for call in log_mock.call_args_list)
        )

    def test_codex_public_error_message_hides_internal_chunk_details(self) -> None:
        msg = ws_handler._public_backend_error_message(
            "codex",
            "Separator is not found, and chunk exceed the limit",
        )
        self.assertIn("internal size limit", msg.lower())
        self.assertNotIn("separator is not found", msg.lower())

    def test_local_model_file_tools_are_contained_to_workspace(self) -> None:
        workspace = Path(tempfile.mkdtemp(prefix="apex-tool-workspace-"))
        outside_dir = Path(tempfile.mkdtemp(prefix="apex-tool-outside-"))
        inside_file = workspace / "inside.txt"
        outside_file = outside_dir / "outside.txt"
        inside_file.write_text("hello\n", encoding="utf-8")
        outside_file.write_text("secret\n", encoding="utf-8")

        self.assertIn(
            "outside workspace",
            read_file.execute({"file_path": str(outside_file)}, workspace=str(workspace)),
        )
        self.assertIn(
            "outside workspace",
            write_file.execute(
                {"file_path": str(outside_dir / "new.txt"), "content": "x"},
                workspace=str(workspace),
            ),
        )
        self.assertIn(
            "outside workspace",
            list_files.execute({"path": str(outside_dir), "pattern": "*.txt"}, workspace=str(workspace)),
        )
        self.assertIn(
            "outside workspace",
            search_files.execute({"path": str(outside_dir), "pattern": "secret"}, workspace=str(workspace)),
        )
        self.assertIn(
            "inside.txt",
            list_files.execute({"path": str(workspace), "pattern": "*.txt"}, workspace=str(workspace)),
        )

    def test_guardrail_summary_loader_does_not_execute_workspace_code(self) -> None:
        workspace = Path(tempfile.mkdtemp(prefix="apex-guardrail-summary-"))
        guardrails_dir = workspace / "scripts" / "guardrails"
        guardrails_dir.mkdir(parents=True, exist_ok=True)
        side_effect = workspace / "executed.txt"

        (guardrails_dir / "guardrail_core.py").write_text(
            f"""
import os
WORKSPACE = "{workspace}"
APEX_ROOT = "/tmp/apex"
PROTECTED_EXACT = {{"a", "b"}}
PROTECTED_ABSOLUTE = {{os.path.expanduser("~/.apex/.env")}}
PROTECTED_SUFFIXES = (".env",)
PROTECTED_SUBSTRINGS = ("/secrets/",)
SANDBOX_ALLOW = [APEX_ROOT + "/", "/tmp/"]
SANDBOX_BLOCK = ["/etc/"]
open({str(side_effect)!r}, "w").write("should not happen")
""".strip(),
            encoding="utf-8",
        )
        (guardrails_dir / "secret_patterns.py").write_text(
            """
import re
SECRET_PATTERNS = [
    ("A", re.compile("a")),
    ("B", re.compile("b")),
]
raise RuntimeError("should not execute")
""".strip(),
            encoding="utf-8",
        )

        original_workspace_root = dashboard_mod._workspace_root
        dashboard_mod._workspace_root = lambda: workspace
        try:
            summary = dashboard_mod._load_guardrail_summary()
        finally:
            dashboard_mod._workspace_root = original_workspace_root

        self.assertFalse(side_effect.exists())
        self.assertEqual(summary["protected_count"], 5)
        self.assertEqual(summary["sandbox_rule_count"], 3)
        self.assertEqual(summary["secret_pattern_count"], 2)


    def test_allow_alert_creates_whitelist_entry(self) -> None:
        """POST /api/alerts/{id}/allow must succeed end-to-end.

        Regression for B-51: memory_extract._add_whitelist_entry() called
        os.chmod() without `import os`, causing a NameError → 500 on every
        Allow action.  This test drives the full route so the import error
        surfaces immediately if it regresses.
        """
        with self._client() as client:
            # Create an alert that looks like a guardrail block
            create = client.post(
                "/api/alerts",
                json={
                    "source": "guardrail",
                    "severity": "warn",
                    "title": "Bash blocked",
                    "body": "echo test > /etc/test",
                    "metadata": {
                        "tool": "Bash",
                        "target": "echo test > /etc/test",
                    },
                },
                headers={"Authorization": "Bearer initial-alert-token"},
            )
            self.assertEqual(create.status_code, 201, create.text)
            alert_id = create.json()["id"]

            # Allow it — this exercises the full route + _add_whitelist_entry
            allow = client.post(
                f"/api/alerts/{alert_id}/allow",
                headers={"Authorization": "Bearer initial-alert-token"},
            )
            self.assertEqual(allow.status_code, 200, allow.text)
            data = allow.json()
            self.assertTrue(data.get("ok"), f"expected ok=True, got: {data}")
            self.assertIn("expires_at", data, f"missing expires_at in: {data}")

            # Whitelist file must now exist and contain the entry
            wl_path = env.APEX_ROOT / "state" / "guardrail_whitelist.json"
            self.assertTrue(wl_path.exists(), "whitelist file not created")
            entries = json.loads(wl_path.read_text())
            self.assertTrue(
                any(e.get("alert_id") == alert_id for e in entries),
                f"alert_id {alert_id} not found in whitelist: {entries}",
            )

    def test_allow_alert_whitelist_entry_has_restricted_permissions(self) -> None:
        """Whitelist file and parent dir must be owner-only (0o600 / 0o700)."""
        with self._client() as client:
            create = client.post(
                "/api/alerts",
                json={
                    "source": "guardrail",
                    "severity": "warn",
                    "title": "Perm test",
                    "body": "cat /etc/passwd",
                    "metadata": {
                        "tool": "Bash",
                        "target": "cat /etc/passwd",
                    },
                },
                headers={"Authorization": "Bearer initial-alert-token"},
            )
            self.assertEqual(create.status_code, 201)
            alert_id = create.json()["id"]
            client.post(
                f"/api/alerts/{alert_id}/allow",
                headers={"Authorization": "Bearer initial-alert-token"},
            )

        wl_path = env.APEX_ROOT / "state" / "guardrail_whitelist.json"
        dir_mode = oct(os.stat(wl_path.parent).st_mode & 0o777)
        file_mode = oct(os.stat(wl_path).st_mode & 0o777)
        self.assertEqual(dir_mode, oct(0o700), f"state/ dir perms wrong: {dir_mode}")
        self.assertEqual(file_mode, oct(0o600), f"whitelist file perms wrong: {file_mode}")


if __name__ == "__main__":
    unittest.main()
