from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="apex-profile-tests-"))

# CRITICAL: Force-set env vars to the temp directory BEFORE importing apex.
# Using setdefault would let production env vars leak through (e.g., from
# launch_dana.sh), causing tests to read/write the production database.
# This was the root cause of the 2026-03-28 data loss incident.
os.environ["APEX_ROOT"] = str(TEST_ROOT)
os.environ["APEX_WORKSPACE"] = str(TEST_ROOT)
os.environ["APEX_ALERT_TOKEN"] = ""
os.environ["APEX_SSL_CERT"] = ""
os.environ["APEX_SSL_KEY"] = ""
os.environ["APEX_SSL_CA"] = ""
os.environ["APEX_DB_NAME"] = "test_apex.db"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import apex  # noqa: E402
from setup.progress import mark_phase_completed  # noqa: E402


class ProfileSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        apex._init_db()
        mark_phase_completed(TEST_ROOT / "state", "setup_complete")
        with apex._db_lock:
            conn = apex._get_db()
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM chats")
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM agent_profiles")
            conn.commit()
            conn.close()
        apex._seed_default_profiles()

        for state in (
            getattr(apex, "_clients", None),
            getattr(apex, "_active_send_tasks", None),
            getattr(apex, "_chat_ws", None),
            getattr(apex, "_stream_buffers", None),
            getattr(apex, "_chat_locks", None),
            getattr(apex, "_chat_send_locks", None),
            getattr(apex, "_session_context_sent", None),
            getattr(apex, "_compaction_summaries", None),
            getattr(apex, "_last_compacted_at", None),
            getattr(apex, "_recovery_pending", None),
        ):
            if hasattr(state, "clear"):
                state.clear()

    def _client(self) -> TestClient:
        return TestClient(apex.app)

    def _chat_row(self, client: TestClient, chat_id: str) -> dict:
        chats = client.get("/api/chats").json()
        for chat in chats:
            if chat["id"] == chat_id:
                return chat
        self.fail(f"chat {chat_id} not found")

    def _create_profile(self, client: TestClient, **overrides) -> tuple[int, dict]:
        payload = {
            "name": "Custom Profile",
            "slug": "custom-profile",
            "avatar": "🧪",
            "role_description": "Test profile",
            "backend": "fake-backend-should-be-ignored",
            "model": "grok-4",
            "system_prompt": "You are a test profile.",
            "tool_policy": "manual",
        }
        payload.update(overrides)
        resp = client.post("/api/profiles", json=payload)
        return resp.status_code, resp.json()

    def test_create_chat_with_valid_profile_inherits_profile_model(self) -> None:
        with self._client() as client:
            resp = client.post("/api/chats", json={"profile_id": "architect"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["profile_id"], "architect")
            self.assertEqual(data["profile_name"], "Architect")
            self.assertEqual(data["model"], "claude-sonnet-4-6")

            chat = self._chat_row(client, data["id"])
            self.assertEqual(chat["profile_id"], "architect")
            self.assertEqual(chat["model"], "claude-sonnet-4-6")

    def test_create_chat_with_invalid_profile_returns_400(self) -> None:
        with self._client() as client:
            resp = client.post("/api/chats", json={"profile_id": "missing-profile"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("not found", resp.json()["error"])

    def test_assign_and_remove_profile_on_existing_chat(self) -> None:
        with self._client() as client:
            create = client.post("/api/chats", json={})
            self.assertEqual(create.status_code, 200)
            chat_id = create.json()["id"]

            assign = client.patch(f"/api/chats/{chat_id}", json={"profile_id": "architect"})
            self.assertEqual(assign.status_code, 200)
            self.assertTrue(assign.json()["ok"])

            chat = self._chat_row(client, chat_id)
            self.assertEqual(chat["profile_id"], "architect")
            self.assertEqual(chat["model"], "claude-sonnet-4-6")

            remove = client.patch(f"/api/chats/{chat_id}", json={"profile_id": ""})
            self.assertEqual(remove.status_code, 200)
            self.assertTrue(remove.json()["ok"])

            chat = self._chat_row(client, chat_id)
            self.assertEqual(chat["profile_id"], "")

    def test_profiled_chat_rejects_set_chat_model_over_websocket(self) -> None:
        with self._client() as client:
            create = client.post("/api/chats", json={"profile_id": "architect"})
            chat_id = create.json()["id"]

            with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
                ws.send_json({"action": "set_chat_model", "chat_id": chat_id, "model": "grok-4"})
                msg = ws.receive_json()

            self.assertEqual(msg["type"], "error")
            self.assertIn("locked by profile", msg["message"])

            chat = self._chat_row(client, chat_id)
            self.assertEqual(chat["model"], "claude-sonnet-4-6")

    def test_non_chat_channels_reject_profile_assignment(self) -> None:
        with self._client() as client:
            create = client.post(
                "/api/chats",
                json={"type": "alerts", "category": "system", "profile_id": "architect"},
            )
            self.assertEqual(create.status_code, 400)
            self.assertIn("channels and threads", create.json()["error"])

            alerts_chat = client.post("/api/chats", json={"type": "alerts", "category": "system"})
            self.assertEqual(alerts_chat.status_code, 200)
            chat_id = alerts_chat.json()["id"]

            patch = client.patch(f"/api/chats/{chat_id}", json={"profile_id": "architect"})
            self.assertEqual(patch.status_code, 400)
            self.assertIn("regular chats", patch.json()["error"])

    def test_profiles_list_omits_sensitive_fields(self) -> None:
        with self._client() as client:
            resp = client.get("/api/profiles")
            self.assertEqual(resp.status_code, 200)
            profiles = resp.json()["profiles"]
            self.assertGreater(len(profiles), 0)

            first = profiles[0]
            self.assertNotIn("system_prompt", first)
            self.assertNotIn("tool_policy", first)
            self.assertIn("backend", first)
            self.assertIn("model", first)

    def test_profile_detail_returns_full_fields(self) -> None:
        with self._client() as client:
            resp = client.get("/api/profiles/architect")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["id"], "architect")
            self.assertIn("system_prompt", data)
            self.assertIn("tool_policy", data)
            self.assertEqual(data["backend"], "claude")
            self.assertEqual(
                json.loads(data["tool_policy"]),
                {
                    "level": 2,
                    "default_level": 2,
                    "elevated_until": None,
                    "invoke_policy": "anyone",
                    "allowed_commands": [],
                },
            )

    def test_create_profile_defaults_tool_policy_to_level_1(self) -> None:
        with self._client() as client:
            status, body = self._create_profile(client, tool_policy="")
            self.assertEqual(status, 201)

            detail = client.get(f"/api/profiles/{body['id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(
                json.loads(detail.json()["tool_policy"]),
                {
                    "level": 1,
                    "default_level": 1,
                    "elevated_until": None,
                    "invoke_policy": "anyone",
                    "allowed_commands": [],
                },
            )

    def test_create_profile_merges_level_into_existing_tool_policy_json(self) -> None:
        with self._client() as client:
            status, body = self._create_profile(
                client,
                tool_policy=json.dumps({"workspace": "/tmp/project", "sandbox": "suggest"}),
            )
            self.assertEqual(status, 201)

            detail = client.get(f"/api/profiles/{body['id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(
                json.loads(detail.json()["tool_policy"]),
                {
                    "level": 1,
                    "default_level": 1,
                    "elevated_until": None,
                    "invoke_policy": "anyone",
                    "allowed_commands": [],
                    "workspace": "/tmp/project",
                    "sandbox": "suggest",
                },
            )

    def test_update_profile_normalizes_tool_policy_level(self) -> None:
        with self._client() as client:
            status, body = self._create_profile(client, tool_policy="manual")
            self.assertEqual(status, 201)

            update = client.put(
                f"/api/profiles/{body['id']}",
                json={"tool_policy": json.dumps({"workspace": "/tmp/code"})},
            )
            self.assertEqual(update.status_code, 200)

            detail = client.get(f"/api/profiles/{body['id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(
                json.loads(detail.json()["tool_policy"]),
                {
                    "level": 1,
                    "default_level": 1,
                    "elevated_until": None,
                    "invoke_policy": "anyone",
                    "allowed_commands": [],
                    "workspace": "/tmp/code",
                },
            )

    def test_duplicate_slug_on_update_returns_409(self) -> None:
        with self._client() as client:
            status, body = self._create_profile(client, name="Alpha Profile", slug="alpha-profile")
            self.assertEqual(status, 201)
            profile_id = body["id"]

            resp = client.put(f"/api/profiles/{profile_id}", json={"slug": "architect"})
            self.assertEqual(resp.status_code, 409)
            self.assertIn("slug", resp.json()["error"])

    def test_delete_missing_profile_returns_404(self) -> None:
        with self._client() as client:
            resp = client.delete("/api/profiles/missing-profile")
            self.assertEqual(resp.status_code, 404)
            self.assertIn("Persona not found", resp.json()["error"])


if __name__ == "__main__":
    unittest.main()
