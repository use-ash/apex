#!/usr/bin/env python3
"""MCP server that exposes execute_code to the Claude SDK.

Wraps the Jupyter kernel-backed execute_code tool as an MCP stdio server
so Claude sessions can use stateful Python execution.

Run standalone:  python3 mcp_execute_code.py
Registered via:  state/mcp_servers.json  (auto-configured by setup)
"""
import json
import sys
import os

# Add server dir to path so we can import local_model modules
_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


def _init_executor():
    """Lazy-load the execute_code module."""
    from local_model.tools.execute_code import execute
    return execute


def _handle_request(request: dict, executor) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "apex-execute-code",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "execute_code",
                        "description": (
                            "Execute Python code in a stateful Jupyter kernel. "
                            "Variables, imports, and function definitions persist between calls. "
                            "ALWAYS use this tool instead of Bash for ANY Python code — "
                            "including print statements, calculations, scripts, and multi-step computations."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python code to execute",
                                },
                                "timeout": {
                                    "type": "integer",
                                    "description": "Execution timeout in seconds (default: 30, max: 120)",
                                },
                            },
                            "required": ["code"],
                        },
                    }
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name != "execute_code":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        # Extract chat_id from env (set by Apex when spawning the SDK client)
        chat_id = os.environ.get("APEX_CHAT_ID")
        workspace = os.environ.get("APEX_WORKSPACE")

        try:
            result = executor(args, workspace, chat_id=chat_id)
            is_error = result.startswith("Error")
        except Exception as e:
            result = f"Error: {type(e).__name__}: {e}"
            is_error = True

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result}],
                "isError": is_error,
            },
        }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """Run the MCP server on stdio."""
    executor = _init_executor()

    # Read JSON-RPC messages from stdin, write responses to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = _handle_request(request, executor)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
