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
import backends  # noqa: E402
import dashboard as dashboard_mod  # noqa: E402
import db as db_mod  # noqa: E402
import env  # noqa: E402
import memory_extract  # noqa: E402
import context as context_mod  # noqa: E402
import streaming as streaming_mod  # noqa: E402
import ws_handler  # noqa: E402
from state import (  # noqa: E402
    _current_group_profile_id,
    _active_send_tasks,
    _queued_turns,
    _chat_ws,
    _stream_buffers,
    _chat_locks,
    _chat_send_locks,
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
        ):
            state.clear()
        context_mod._premium = None
        ws_handler._ws_premium = None

    def _client(self) -> TestClient:
        return TestClient(apex.app)

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
        self.assertIn("Restricted", deny_read.message)

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

        async def fake_run_ollama_chat(chat_id_arg: str, prompt: str, model=None, attachments=None):
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
        self.assertIn("# Agent Load", prompt)
        self.assertIn("Queue CodeExpert [queue-codeexpert] 💻", prompt)
        self.assertIn("queue: 2/2", prompt)
        self.assertIn("Queue Apex Assistant [queue-apex-assistant] ✨ — 🟢 idle", prompt)

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
        with (
            mock.patch.object(ws_handler, "_ws_premium", None),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
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
        with (
            mock.patch.object(ws_handler, "_ws_premium", None),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
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
        with (
            mock.patch.object(ws_handler, "_ws_premium", None),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
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
        with (
            mock.patch.object(ws_handler, "_ws_premium", None),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
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
        with (
            mock.patch.object(ws_handler, "_ws_premium", None),
            mock.patch.object(ws_handler, "_run_codex_chat", side_effect=fake_run_codex_chat),
        ):
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
