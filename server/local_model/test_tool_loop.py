#!/usr/bin/env python3
"""Standalone test for local model tool calling loop."""
import asyncio
import sys
import json

# Allow running from project root
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from local_model.tool_loop import run_tool_loop

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3.5:27b-fast"


async def test_emit(event: dict):
    """Print events to stdout for verification."""
    etype = event.get("type", "?")
    if etype == "text":
        print(f"  [text] {event['text'][:200]}")
    elif etype == "tool_use":
        print(f"  [tool_use] {event['name']}({json.dumps(event['input'])[:100]})")
    elif etype == "tool_result":
        preview = event['content'][:150].replace('\n', '\\n')
        err = " ERROR" if event.get('is_error') else ""
        print(f"  [tool_result]{err} {preview}")
    elif etype == "error":
        print(f"  [ERROR] {event['message']}")
    else:
        print(f"  [{etype}] {event}")


async def run_test(prompt: str, label: str):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"PROMPT: {prompt}")
    print(f"{'='*60}")

    messages = [
        {"role": "system", "content": f"You are {MODEL}, a local AI model with tool access. Use tools when needed. Be concise."},
        {"role": "user", "content": prompt},
    ]

    result = await run_tool_loop(
        ollama_url=OLLAMA_URL,
        model=MODEL,
        messages=messages,
        emit_event=test_emit,
    )

    print(f"\n--- Result ---")
    print(f"  text: {result['text'][:200]}")
    print(f"  is_error: {result['is_error']}")
    tool_events = json.loads(result['tool_events'])
    print(f"  tool_events: {len(tool_events)} tool call(s)")
    for te in tool_events:
        print(f"    - {te['name']}: {'ERROR' if te['result']['is_error'] else 'OK'}")
    return result


async def main():
    print("Local Model Tool Loop Test")
    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_URL}")

    # Test 1: bash
    await run_test("Run the command 'uname -a' and tell me what OS I'm running", "bash tool")

    # Test 2: read_file
    await run_test("Read the first 5 lines of /etc/hosts", "read_file tool")

    # Test 3: list_files
    await run_test(f"List all Python files in {__import__('pathlib').Path(__file__).resolve().parent}/", "list_files tool")

    # Test 4: search_files
    await run_test(f"Search for 'def execute' in {__import__('pathlib').Path(__file__).resolve().parent}/tools/", "search_files tool")

    # Test 5: safety - should be blocked
    await run_test("Run the command 'rm -rf /'", "safety block")

    # Test 6: multi-tool
    await run_test("What Python version is installed? Run 'python3 --version'. Also list the files in /tmp/.", "multi-tool")

    print(f"\n{'='*60}")
    print("All tests complete.")


if __name__ == "__main__":
    asyncio.run(main())
