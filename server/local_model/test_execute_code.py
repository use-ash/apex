#!/usr/bin/env python3
"""Test execute_code tool — per-chat isolation and stateful persistence."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_model.tools.execute_code import (
    execute,
    _get_or_create_kernel,
    _make_kernel_key,
    _history_path,
    _load_history,
    _clear_history,
    shutdown_all_kernels,
    _kernels,
)

WORKSPACE = "/tmp/apex_test_ws"
CHAT_A = "test-chat-aaa"
CHAT_B = "test-chat-bbb"

PASS = 0
FAIL = 0


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


def main():
    global PASS, FAIL
    print("=" * 60)
    print("execute_code: persistence & isolation tests")
    print("=" * 60)

    # Clean up any prior test state
    for cid in [CHAT_A, CHAT_B, None]:
        _clear_history(_make_kernel_key(WORKSPACE, cid))
    shutdown_all_kernels()

    # ── Test 1: Basic execution ──
    print("\n--- Test 1: Basic execution ---")
    result = execute({"code": "print(1 + 1)"}, WORKSPACE, chat_id=CHAT_A)
    test("basic print", result.strip() == "2", f"got: {result.strip()!r}")

    # ── Test 2: State persists within session ──
    print("\n--- Test 2: State persists within session ---")
    execute({"code": "x = 42"}, WORKSPACE, chat_id=CHAT_A)
    result = execute({"code": "print(x)"}, WORKSPACE, chat_id=CHAT_A)
    test("variable persists", result.strip() == "42", f"got: {result.strip()!r}")

    # ── Test 3: Per-chat isolation ──
    print("\n--- Test 3: Per-chat isolation ---")
    result = execute({"code": "print(x)"}, WORKSPACE, chat_id=CHAT_B)
    test("chat B can't see chat A's x", "Error" in result or "NameError" in result,
         f"got: {result[:100]!r}")

    # Set a different value in chat B
    execute({"code": "x = 999"}, WORKSPACE, chat_id=CHAT_B)
    result = execute({"code": "print(x)"}, WORKSPACE, chat_id=CHAT_B)
    test("chat B has own x=999", result.strip() == "999", f"got: {result.strip()!r}")

    # Chat A still has x=42
    result = execute({"code": "print(x)"}, WORKSPACE, chat_id=CHAT_A)
    test("chat A still has x=42", result.strip() == "42", f"got: {result.strip()!r}")

    # ── Test 4: Cell history saved ──
    print("\n--- Test 4: Cell history persistence ---")
    key_a = _make_kernel_key(WORKSPACE, CHAT_A)
    history = _load_history(key_a)
    test("history file has cells", len(history) >= 2,
         f"got {len(history)} cells")
    test("history contains x=42", any("x = 42" in c for c in history),
         f"cells: {[c[:30] for c in history]}")

    # ── Test 5: State replay after kernel kill ──
    print("\n--- Test 5: State replay after kernel restart ---")
    # Kill chat A's kernel (simulates server restart)
    shutdown_all_kernels()
    test("kernels cleared", len(_kernels) == 0)

    # Now execute — should auto-create kernel and replay history
    result = execute({"code": "print(x)"}, WORKSPACE, chat_id=CHAT_A)
    test("x=42 survives kernel restart", result.strip() == "42",
         f"got: {result.strip()!r}")

    # ── Test 6: Error cells not saved ──
    print("\n--- Test 6: Error cells excluded from history ---")
    history_before = len(_load_history(key_a))
    execute({"code": "raise ValueError('boom')"}, WORKSPACE, chat_id=CHAT_A)
    history_after = len(_load_history(key_a))
    test("error cell not saved", history_after == history_before,
         f"before={history_before} after={history_after}")

    # ── Test 7: Timeout ──
    print("\n--- Test 7: Timeout ---")
    result = execute({"code": "import time; time.sleep(10); print('done')",
                      "timeout": 2}, WORKSPACE, chat_id=CHAT_A)
    test("timeout triggers", "timed out" in result.lower(), f"got: {result[:100]!r}")

    # ── Cleanup ──
    print("\n--- Cleanup ---")
    shutdown_all_kernels()
    for cid in [CHAT_A, CHAT_B]:
        _clear_history(_make_kernel_key(WORKSPACE, cid))
    print("  Kernels shut down, history cleared.")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
