#!/usr/bin/env python3
"""MCP server that exposes guide configuration tools to the Claude SDK.

Wraps the guide_tools module as an MCP stdio server so the Guide persona
can configure the Apex server during Claude Haiku sessions.

Protocol: newline-delimited JSON-RPC over stdin/stdout (MCP stdio transport).

Run standalone:  python3 mcp_guide_tools.py
Registered via:  streaming.py _inject_guide_tools_mcp() (auto-configured for guide sessions)
"""
import json
import sys
import os


def _log(msg: str) -> None:
    print(f"[mcp-guide-tools] {msg}", file=sys.stderr, flush=True)


# Add server dir to path so we can import local_model modules
_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


def _init_tools():
    """Lazy-load the guide tools module."""
    try:
        from local_model.tools.guide_tools import GUIDE_TOOL_DEFS
        executors = {}
        for tool_def in GUIDE_TOOL_DEFS:
            executors[tool_def["name"]] = tool_def["executor"]
        _log(f"loaded {len(executors)} guide tools")
        return GUIDE_TOOL_DEFS, executors
    except Exception as e:
        _log(f"tool load FAILED: {e}")
        raise


def _build_mcp_tool_list(tool_defs: list[dict]) -> list[dict]:
    """Convert guide tool definitions to MCP tools/list format."""
    tools = []
    for td in tool_defs:
        tools.append({
            "name": td["name"],
            "description": td["description"],
            "inputSchema": td["parameters"],
        })
    return tools


def _handle_request(request: dict, tool_defs: list[dict], executors: dict) -> dict | None:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        _log(f"initialize (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "apex-guide-tools",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        _log("notifications/initialized received")
        return None

    if method == "tools/list":
        _log(f"tools/list (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": _build_mcp_tool_list(tool_defs),
            },
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        _log(f"tools/call: {tool_name} (id={req_id})")

        executor = executors.get(tool_name)
        if not executor:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        workspace = os.environ.get("APEX_WORKSPACE")
        try:
            result = executor(args, workspace)
            is_error = result.startswith("Error")
        except Exception as e:
            result = f"Error: {type(e).__name__}: {e}"
            is_error = True

        _log(f"tools/call result: tool={tool_name} error={is_error} len={len(result)}")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result}],
                "isError": is_error,
            },
        }

    # Unknown method
    if req_id is not None:
        _log(f"unknown method: {method} (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    _log(f"unknown notification: {method}")
    return None


def main():
    """Run the MCP server on stdio using newline-delimited JSON."""
    _log(f"starting (pid={os.getpid()}, python={sys.executable})")
    _log(f"env: APEX_ROOT={os.environ.get('APEX_ROOT')}")

    try:
        tool_defs, executors = _init_tools()
    except Exception:
        _log("FATAL: cannot load guide tools, exiting")
        sys.exit(1)

    _log("ready, reading stdin")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"JSON parse error: {e} — line: {line[:200]}")
            continue

        response = _handle_request(request, tool_defs, executors)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    _log("stdin closed, exiting")


if __name__ == "__main__":
    main()
