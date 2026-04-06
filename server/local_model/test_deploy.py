#!/usr/bin/env python3
"""Deployment verification for execute_code + tool_loop.

Runs on any Apex install — no Ollama or local model required.
Tests module imports, registry, kernel lifecycle, and persistence.
Skips kernel tests gracefully if jupyter_client is not installed.

Usage:
    cd server && python3 local_model/test_deploy.py
    # or with venv:
    cd server && ../.venv/bin/python3 local_model/test_deploy.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = 0
FAIL = 0
SKIP = 0


def test(label, condition, detail=""):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    extra = f" — {detail}" if detail else ""
    print(f"  [{status}] {label}{extra}")
    return condition


def skip(label, reason=""):
    global SKIP
    SKIP += 1
    extra = f" — {reason}" if reason else ""
    print(f"  [SKIP] {label}{extra}")


def main():
    global PASS, FAIL, SKIP
    print("=" * 60)
    print("Apex execute_code deployment verification")
    print("=" * 60)

    # ── 1. Core imports ──
    print("\n--- 1. Core imports ---")
    try:
        from local_model.tool_loop import run_tool_loop
        test("tool_loop imports", True)
    except Exception as e:
        test("tool_loop imports", False, str(e))

    try:
        from local_model.registry import get_tool_schemas, get_executor, TOOLS
        test("registry imports", True)
    except Exception as e:
        test("registry imports", False, str(e))

    try:
        from local_model.guardrails import pre_check, filter_output
        test("guardrails imports", True)
    except Exception as e:
        test("guardrails imports", False, str(e))

    try:
        from local_model.safety import truncate_output, _primary_workspace
        test("safety imports", True)
    except Exception as e:
        test("safety imports", False, str(e))

    # ── 2. Tool registry ──
    print("\n--- 2. Tool registry ---")
    schemas = get_tool_schemas()
    base_tools = {"bash", "read_file", "write_file", "edit_file", "list_files", "search_files"}
    registered = set(TOOLS.keys())
    test("base tools registered", base_tools.issubset(registered),
         f"registered: {sorted(registered)}")

    has_jupyter = "execute_code" in registered
    if has_jupyter:
        test("execute_code registered", True)
    else:
        skip("execute_code registered", "jupyter_client not installed")

    for name in base_tools:
        executor = get_executor(name)
        test(f"{name} has executor", executor is not None)

    test("schemas match registrations", len(schemas) >= len(base_tools),
         f"{len(schemas)} schemas")

    # ── 3. ToolLoopLogger ──
    print("\n--- 3. ToolLoopLogger ---")
    from local_model.tool_loop import log as tl_log
    test("log.info exists", hasattr(tl_log, "info"))
    test("log.warning exists", hasattr(tl_log, "warning"))
    try:
        tl_log.info("deploy test: info works")
        test("log.info callable", True)
    except Exception as e:
        test("log.info callable", False, str(e))
    try:
        tl_log.warning("deploy test: warning works")
        test("log.warning callable", True)
    except Exception as e:
        test("log.warning callable", False, str(e))

    # ── 4. Text-based tool calling parser ──
    print("\n--- 4. Text-based tool call parsing ---")
    from local_model.tool_loop import _parse_text_tool_calls, _fix_json_control_chars

    text1 = 'Sure! <tool_call>{"name": "bash", "arguments": {"command": "uname -a"}}</tool_call> Let me check.'
    clean, calls = _parse_text_tool_calls(text1)
    test("single tool_call parsed", len(calls) == 1, f"got {len(calls)}")
    test("tool name correct", calls[0]["function"]["name"] == "bash" if calls else False)
    test("clean text stripped", "<tool_call>" not in clean)

    text2 = 'No tools here, just text.'
    clean2, calls2 = _parse_text_tool_calls(text2)
    test("no false positives", len(calls2) == 0)
    test("text preserved", clean2 == text2)

    text3 = '<tool_call>{"name": "read_file", "arguments": {"file_path": "/tmp/test.py"}}</tool_call><tool_call>{"name": "bash", "arguments": {"command": "ls"}}</tool_call>'
    _, calls3 = _parse_text_tool_calls(text3)
    test("multi tool_call parsed", len(calls3) == 2, f"got {len(calls3)}")

    # JSON with raw newlines (common model output)
    raw = '{"name": "write_file", "arguments": {"file_path": "/tmp/x", "content": "line1\nline2"}}'
    fixed = _fix_json_control_chars(raw)
    import json
    try:
        parsed = json.loads(fixed)
        test("JSON control char fix", parsed["arguments"]["content"] == "line1\nline2")
    except json.JSONDecodeError as e:
        test("JSON control char fix", False, str(e))

    # ── 5. Kernel isolation & persistence (requires jupyter) ──
    if not has_jupyter:
        print("\n--- 5. Kernel tests (SKIPPED — no jupyter_client) ---")
        skip("kernel lifecycle", "jupyter_client not installed")
        skip("per-chat isolation", "jupyter_client not installed")
        skip("cell history persistence", "jupyter_client not installed")
        skip("state replay", "jupyter_client not installed")
    else:
        print("\n--- 5. Kernel isolation & persistence ---")
        from local_model.tools.execute_code import (
            execute, _make_kernel_key, _history_path,
            _load_history, _clear_history, shutdown_all_kernels, _kernels,
        )

        WORKSPACE = "/tmp/apex_deploy_test"
        CHAT_A = "deploy-chat-aaa"
        CHAT_B = "deploy-chat-bbb"

        # Clean slate
        for cid in [CHAT_A, CHAT_B]:
            _clear_history(_make_kernel_key(WORKSPACE, cid))
        shutdown_all_kernels()

        # Basic exec
        r = execute({"code": "print(2+2)"}, WORKSPACE, chat_id=CHAT_A)
        test("basic exec", r.strip() == "4", f"got: {r.strip()!r}")

        # State persists
        execute({"code": "val = 'hello'"}, WORKSPACE, chat_id=CHAT_A)
        r = execute({"code": "print(val)"}, WORKSPACE, chat_id=CHAT_A)
        test("state persists", r.strip() == "hello", f"got: {r.strip()!r}")

        # Isolation
        r = execute({"code": "print(val)"}, WORKSPACE, chat_id=CHAT_B)
        test("chat isolation", "NameError" in r, f"got: {r[:80]!r}")

        # History saved
        key_a = _make_kernel_key(WORKSPACE, CHAT_A)
        history = _load_history(key_a)
        test("history saved", len(history) >= 2, f"{len(history)} cells")

        # Replay after kill
        shutdown_all_kernels()
        r = execute({"code": "print(val)"}, WORKSPACE, chat_id=CHAT_A)
        test("replay after restart", r.strip() == "hello", f"got: {r.strip()!r}")

        # Cleanup
        shutdown_all_kernels()
        for cid in [CHAT_A, CHAT_B]:
            _clear_history(_make_kernel_key(WORKSPACE, cid))

    # ── Summary ──
    print(f"\n{'=' * 60}")
    total = PASS + FAIL + SKIP
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped ({total} total)")
    if FAIL == 0:
        print("STATUS: OK" + (" (kernel tests skipped)" if SKIP > 0 else ""))
    else:
        print("STATUS: FAILED")
    print(f"{'=' * 60}")
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
