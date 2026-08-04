#!/usr/bin/env python3
"""Reusable mTLS WebSocket driver for Apex dev/prod.

Sending a turn is WebSocket-only, so any end-to-end test has to speak /ws.
Importable as ApexWS for scripted scenarios, or usable from the CLI.

    ./.venv/bin/python testing/ws_client.py --new-chat send "hello"
    ./.venv/bin/python testing/ws_client.py --chat abc123 scenario cancel-requeue
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import ssl
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from websockets.asyncio.client import connect as ws_connect

DEV_PORT = 8301
PROD_PORT = 8300

# Frontend heartbeats every 5s; the server evicts on ping staleness
# (streaming.py _PING_STALE_SEC), so a silent client gets force-closed
# mid-stream and the failure looks like a server bug.
PING_INTERVAL = 5.0

_CERT_DIRS = {
    PROD_PORT: Path.home() / ".apex-prod" / "state" / "ssl",
    DEV_PORT: Path.home() / ".openclaw" / "apex" / "state" / "ssl",
}
_FALLBACK_CERT_DIR = Path.home() / ".openclaw" / "apex" / "state" / "ssl"

TERMINAL_EVENTS = {"stream_end", "error"}


def resolve_cert_dir(port: int, override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    d = _CERT_DIRS.get(port, _FALLBACK_CERT_DIR)
    if not (d / "client.crt").exists():
        d = _FALLBACK_CERT_DIR
    return d


def make_ssl_context(cert_dir: Path) -> ssl.SSLContext:
    crt, key = cert_dir / "client.crt", cert_dir / "client.key"
    if not crt.exists() or not key.exists():
        raise SystemExit(f"client cert not found in {cert_dir}")
    ctx = ssl.create_default_context()
    # Server cert is self-signed, same as curl -k.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.load_cert_chain(certfile=str(crt), keyfile=str(key))
    return ctx


class ApexWS:
    def __init__(
        self,
        chat_id: str = "",
        port: int = DEV_PORT,
        host: str = "127.0.0.1",
        cert_dir: str | None = None,
        verbose: bool = True,
    ) -> None:
        self.chat_id = chat_id
        self.port = port
        self.host = host
        self.cert_dir = resolve_cert_dir(port, cert_dir)
        self.verbose = verbose
        self.events: list[dict[str, Any]] = []
        self._ws: Any = None
        self._ping_task: asyncio.Task | None = None
        self._t0 = 0.0

    # ---- plumbing ---------------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{time.time() - self._t0:7.2f}s] {msg}", flush=True)

    async def __aenter__(self) -> "ApexWS":
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def open(self) -> "ApexWS":
        self._t0 = time.time()
        url = f"wss://{self.host}:{self.port}/ws"
        # No Origin header: agent_sdk._websocket_origin_allowed accepts a
        # missing Origin when mTLS is configured.
        self._ws = await ws_connect(url, ssl=make_ssl_context(self.cert_dir))
        self._log(f"connected {url} (certs={self.cert_dir})")
        self._ping_task = asyncio.create_task(self._ping_loop())
        return self

    async def _ping_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                await self._ws.send(json.dumps({"action": "ping"}))
        except (asyncio.CancelledError, Exception):
            return

    async def close(self) -> None:
        if self._ping_task:
            self._ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ping_task
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._log("closed")

    async def drop(self) -> None:
        """Abort the TCP connection with no close handshake.

        Simulates a real client disconnect (backgrounded tab, dead wifi)
        rather than a graceful close.
        """
        if self._ping_task:
            self._ping_task.cancel()
        if self._ws is not None:
            with contextlib.suppress(Exception):
                self._ws.transport.abort()
        self._log("DROPPED (transport aborted)")

    # ---- actions ----------------------------------------------------------
    async def _send_action(self, payload: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(payload))

    async def attach(self) -> None:
        await self._send_action({"action": "attach", "chat_id": self.chat_id})
        self._log(f"-> attach {self.chat_id}")

    async def send(
        self,
        prompt: str,
        client_msg_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> str:
        stream_id = uuid.uuid4().hex[:12]
        cmid = client_msg_id or uuid.uuid4().hex[:12]
        await self._send_action(
            {
                "action": "send",
                "chat_id": self.chat_id,
                "prompt": prompt,
                "stream_id": stream_id,
                "client_msg_id": cmid,
                "attachments": attachments or [],
            }
        )
        self._log(f"-> send stream_id={stream_id} cmid={cmid} {prompt[:60]!r}")
        return stream_id

    async def stop(self, stream_id: str = "") -> None:
        await self._send_action(
            {"action": "stop", "chat_id": self.chat_id, "stream_id": stream_id}
        )
        self._log(f"-> stop stream_id={stream_id or '*'}")

    async def stop_all(self) -> None:
        await self._send_action({"action": "stop_all", "chat_id": self.chat_id})
        self._log("-> stop_all")

    async def cancel_queued(self, msg_id: str) -> None:
        await self._send_action(
            {"action": "cancel_queued", "chat_id": self.chat_id, "msg_id": msg_id}
        )
        self._log(f"-> cancel_queued {msg_id}")

    # ---- receiving --------------------------------------------------------
    async def stream(self, timeout: float = 120.0) -> AsyncIterator[dict[str, Any]]:
        """Yield events until `timeout` elapses or the socket dies.

        Timeout is a wall-clock budget for the whole stream, not per-message,
        so a server that goes quiet mid-turn still ends the iteration.
        """
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self._log(f"TIMEOUT after {timeout}s")
                return
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                self._log(f"TIMEOUT after {timeout}s")
                return
            except Exception as e:
                self._log(f"socket closed: {type(e).__name__}: {e}")
                return
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type", "?")
            if etype == "pong":
                continue
            self.events.append(evt)
            self._log(f"<- {self._fmt(evt)}")
            yield evt

    @staticmethod
    def _fmt(evt: dict[str, Any]) -> str:
        etype = evt.get("type", "?")
        bits = [etype]
        for k in ("stream_id", "client_msg_id", "msg_id", "position", "message"):
            if evt.get(k):
                bits.append(f"{k}={str(evt[k])[:60]}")
        if etype in {"token", "delta", "text"}:
            bits.append(repr(str(evt.get("text") or evt.get("content") or "")[:40]))
        if etype == "queue_update":
            bits.append(f"queued={len(evt.get('queued') or [])}")
        return " ".join(bits)

    async def collect_until(
        self,
        types: Iterable[str] = TERMINAL_EVENTS,
        timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Consume events until one of `types` arrives. Returns it, or None."""
        wanted = set(types)
        async for evt in self.stream(timeout=timeout):
            if evt.get("type") in wanted:
                return evt
        return None

    def seen(self, etype: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == etype]


# ---- REST helper ---------------------------------------------------------
def new_chat(port: int = DEV_PORT, cert_dir: str | None = None, model: str = "") -> str:
    """Create a scratch chat via REST so tests never touch a real one."""
    import urllib.request

    d = resolve_cert_dir(port, cert_dir)
    ctx = make_ssl_context(d)
    body = json.dumps({"model": model} if model else {}).encode()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/chats",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        payload = json.loads(resp.read())
    cid = str(payload.get("chat_id") or payload.get("id") or "")
    if not cid:
        raise SystemExit(f"could not parse chat_id from {payload}")
    return cid


def fetch_messages(
    chat_id: str, port: int = DEV_PORT, cert_dir: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    import urllib.request

    ctx = make_ssl_context(resolve_cert_dir(port, cert_dir))
    url = f"https://127.0.0.1:{port}/api/chats/{chat_id}/messages?limit={limit}"
    with urllib.request.urlopen(url, context=ctx, timeout=15) as resp:
        payload = json.loads(resp.read())
    if isinstance(payload, dict):
        return list(payload.get("messages") or [])
    return list(payload or [])


# ---- scenarios -----------------------------------------------------------
async def scenario_cancel_requeue(chat_id: str, port: int, timeout: float) -> int:
    """Repro: cancel a turn, resend, double-send, then drop the socket.

    Asserts the queued turn's text survives the disconnect. Before the
    _purge_queued_turns_for_ws fix it was silently discarded.
    """
    marker = f"QUEUED-SURVIVES-{uuid.uuid4().hex[:6]}"
    async with ApexWS(chat_id, port=port) as c:
        await c.attach()
        await c.send("Count slowly from 1 to 40, one number per line.")
        await c.collect_until({"stream_ack"}, timeout=30)
        await asyncio.sleep(2)

        await c.stop()
        await asyncio.sleep(1)

        await c.send("First message after cancel.")
        await c.send(marker)  # should be queued: lock still held

        queued = await c.collect_until({"stream_queued"}, timeout=30)
        if not queued:
            print("FAIL: never saw stream_queued — cannot exercise the purge path")
            return 1
        await c.drop()

    await asyncio.sleep(3)
    print(f"\nmarker={marker}")
    msgs = fetch_messages(chat_id, port=port)
    if any(marker in str(m.get("content") or "") for m in msgs):
        print("PASS: queued turn survived the socket drop")
        return 0
    print("FAIL: queued turn was purged without persisting")
    return 1


async def scenario_compaction(chat_id: str, port: int, timeout: float) -> int:
    """Repro: compaction must announce itself before it blocks the chat lock.

    Compaction runs the summary model while holding the lock; without a
    start event the client sees only dead air and reads it as a hang.
    """
    def force_compact() -> None:
        import urllib.request

        ctx = make_ssl_context(resolve_cert_dir(port, None))
        # /admin is bearer-token + CSRF gated; launch_dev.sh defaults the token.
        token = os.environ.get("APEX_ADMIN_TOKEN", "apex-dev-token")
        req = urllib.request.Request(
            f"https://127.0.0.1:{port}/admin/api/sessions/{chat_id}/compact",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
            print(f"compact endpoint: {json.loads(resp.read())}")

    async with ApexWS(chat_id, port=port) as c:
        await c.attach()
        await c.send("Say only: ready.")
        if await c.collect_until(timeout=90) is None:
            print("FAIL: seed turn never terminated")
            return 1

        task = asyncio.create_task(asyncio.to_thread(force_compact))
        t0 = time.time()
        start_at = end_at = 0.0
        async for evt in c.stream(timeout=180):
            if evt.get("type") != "system":
                continue
            if evt.get("subtype") == "compaction_start":
                start_at = time.time()
            elif evt.get("subtype") == "compaction":
                end_at = time.time()
                break
        await task

    if not start_at:
        print("FAIL: no compaction_start — the blocked window is still silent")
        return 1
    print(f"\ncompaction_start after {start_at - t0:.2f}s, "
          f"complete after {end_at - t0:.2f}s "
          f"(silent window covered: {end_at - start_at:.2f}s)")
    if start_at - t0 > 5.0:
        print("FAIL: start event lagged the trigger by >5s")
        return 1
    if not end_at:
        print("FAIL: never saw the compaction-complete event")
        return 1
    print("PASS: client is told before and after the lock-held window")
    return 0


TEXT_EVENTS = {"token", "delta", "text", "assistant_delta", "content"}


async def scenario_stop(chat_id: str, port: int, timeout: float) -> int:
    """Repro: stop mid-generation and assert the tokens actually stop.

    Uses a long enough prompt that the turn cannot finish on its own before
    the stop lands — the 1-to-40 count in cancel-requeue completes in ~2s,
    which is why that scenario could not tell a working stop from a no-op.
    """
    async with ApexWS(chat_id, port=port) as c:
        await c.attach()
        sid = await c.send(
            "Count from 1 to 400, one number per line. No other text."
        )

        # Apex streams whole SDK blocks, not tokens (agent_sdk.py `_send`
        # fires once per TextBlock), so once text arrives the turn is already
        # over. The only interruptible window is thinking / tool use.
        started = False
        async for evt in c.stream(timeout=60):
            if evt.get("type") == "thinking":
                started = True
                break
            if evt.get("type") in TEXT_EVENTS:
                print("FAIL: text arrived before any thinking — no window to stop in")
                return 1
        if not started:
            print("FAIL: never reached the thinking phase")
            return 1

        await asyncio.sleep(1.0)
        stop_at = time.time()
        await c.stop(sid)

        last_text_at = stop_at
        text_after_stop = 0
        async for evt in c.stream(timeout=60):
            if evt.get("type") in TEXT_EVENTS:
                text_after_stop += 1
                last_text_at = time.time()
            if evt.get("type") in TERMINAL_EVENTS:
                break

        lag = last_text_at - stop_at
        print(f"\nstop lag: {lag:.2f}s, {text_after_stop} text events after stop")

    await asyncio.sleep(2)
    msgs = fetch_messages(chat_id, port=port)
    assistant = [m for m in msgs if m.get("role") == "assistant"]
    tail = str(assistant[-1].get("content") or "") if assistant else ""
    reached_400 = "\n400" in tail or tail.rstrip().endswith("400")
    print(f"assistant rows={len(assistant)} reached_400={reached_400} len={len(tail)}")

    if reached_400:
        print("FAIL: generation ran to completion — stop did not interrupt")
        return 1
    if lag > 3.0:
        print(f"FAIL: tokens kept arriving {lag:.1f}s after stop")
        return 1
    print("PASS: stop interrupted the turn")
    return 0


async def cmd_send(args: argparse.Namespace) -> int:
    async with ApexWS(args.chat, port=args.port, cert_dir=args.cert_dir) as c:
        await c.attach()
        await c.send(
            args.prompt,
            attachments=[{"id": a} for a in getattr(args, "attach", [])],
        )
        end = await c.collect_until(timeout=args.timeout)
        if end is None:
            print("no terminal event (timeout)")
            return 1
        return 1 if end.get("type") == "error" else 0


async def cmd_listen(args: argparse.Namespace) -> int:
    async with ApexWS(args.chat, port=args.port, cert_dir=args.cert_dir) as c:
        await c.attach()
        async for _ in c.stream(timeout=args.timeout):
            pass
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=DEV_PORT, help="8301 dev, 8300 prod")
    p.add_argument("--chat", default="", help="chat_id to drive")
    p.add_argument("--new-chat", action="store_true", help="create a scratch chat first")
    p.add_argument("--cert-dir", default=None)
    p.add_argument("--timeout", type=float, default=120.0)

    sub = p.add_subparsers(dest="cmd", required=True)
    s_send = sub.add_parser("send", help="send one prompt, stream to stream_end")
    s_send.add_argument("prompt")
    s_send.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="UPLOAD_ID",
        help="attach an existing state/uploads id (repeatable)",
    )
    sub.add_parser("listen", help="attach and print events")
    s_scn = sub.add_parser("scenario", help="run a named repro")
    s_scn.add_argument("name", choices=["cancel-requeue", "stop", "compaction"])

    args = p.parse_args()

    if args.port == PROD_PORT and not os.environ.get("APEX_WS_ALLOW_PROD"):
        print("refusing to drive prod :8300 (set APEX_WS_ALLOW_PROD=1 to override)")
        return 2

    if args.new_chat:
        args.chat = new_chat(args.port, args.cert_dir)
        print(f"created chat {args.chat}")
    if not args.chat:
        print("need --chat <id> or --new-chat")
        return 2

    if args.cmd == "send":
        return asyncio.run(cmd_send(args))
    if args.cmd == "listen":
        return asyncio.run(cmd_listen(args))
    if args.cmd == "scenario":
        if args.name == "stop":
            return asyncio.run(scenario_stop(args.chat, args.port, args.timeout))
        if args.name == "compaction":
            return asyncio.run(scenario_compaction(args.chat, args.port, args.timeout))
        return asyncio.run(scenario_cancel_requeue(args.chat, args.port, args.timeout))
    return 2


if __name__ == "__main__":
    sys.exit(main())
