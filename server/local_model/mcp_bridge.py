"""MCP bridge — connects MCP servers to the local model tool loop.

Reads state/mcp_servers.json, launches stdio MCP servers, discovers
their tools, and exposes them in registry-compatible format so that
Ollama/xAI/MLX models can call MCP tools the same way they call
built-in tools (bash, read_file, etc.).

Tool names are namespaced as server_name__tool_name to avoid collisions
with built-in tools.

Each MCP server runs as a background task that maintains the stdio_client
context manager — required by the anyio-based MCP SDK.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import env
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger("apex.mcp_bridge")

# Resolve state dir relative to server/
_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "state"


@dataclass
class MCPConnection:
    """Tracks a live MCP server connection."""
    name: str
    session: ClientSession | None = None
    tools: list[dict] = field(default_factory=list)
    _shutdown: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None


# Active connections keyed by server name
_connections: dict[str, MCPConnection] = {}
_lock = asyncio.Lock()
_initialized = False


def _load_mcp_config() -> dict[str, dict]:
    """Load enabled MCP servers from state/mcp_servers.json."""
    mcp_path = _STATE_DIR / "mcp_servers.json"
    if not mcp_path.exists():
        return {}
    try:
        data = json.loads(mcp_path.read_text())
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            return {}
        enabled = {
            name: cfg for name, cfg in servers.items()
            if isinstance(cfg, dict) and cfg.get("enabled", True)
        }
        return env.rewrite_mcp_servers_for_workspace(enabled)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("MCP config load failed: %s", e)
        return {}


def _mcp_tool_to_openai_schema(server_name: str, tool) -> dict:
    """Convert an MCP Tool object to OpenAI function-calling format."""
    prefixed_name = f"{server_name}__{tool.name}"
    return {
        "type": "function",
        "function": {
            "name": prefixed_name,
            "description": tool.description or f"MCP tool: {tool.name} (from {server_name})",
            "parameters": tool.inputSchema if tool.inputSchema else {
                "type": "object",
                "properties": {},
            },
        },
    }


async def _run_server(conn: MCPConnection, config: dict):
    """Background task: keep an MCP server alive within its context manager scope."""
    server_type = config.get("type", "stdio")
    if server_type != "stdio":
        log.warning("MCP bridge: skipping %s (type=%s, only stdio supported)", conn.name, server_type)
        return

    command = config.get("command", "")
    args = config.get("args", [])
    env = config.get("env") or None

    if not command:
        log.warning("MCP bridge: skipping %s (no command)", conn.name)
        return

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )

    try:
        async with stdio_client(server_params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()

                # Discover tools
                tools_result = await session.list_tools()
                tool_schemas = []
                for tool in tools_result.tools:
                    schema = _mcp_tool_to_openai_schema(conn.name, tool)
                    tool_schemas.append(schema)

                conn.session = session
                conn.tools = tool_schemas
                log.info("MCP bridge: connected to %s — %d tool(s)", conn.name, len(tool_schemas))

                # Stay alive until shutdown is signaled
                await conn._shutdown.wait()

    except Exception as e:
        log.error("MCP bridge: %s failed: %s", conn.name, e)
    finally:
        conn.session = None
        conn.tools = []
        log.info("MCP bridge: %s disconnected", conn.name)


async def initialize():
    """Connect to all enabled MCP servers. Call once at startup or on config change."""
    global _initialized
    async with _lock:
        # Shut down existing connections
        await _shutdown_all()

        config = _load_mcp_config()
        if not config:
            log.info("MCP bridge: no servers configured")
            _initialized = True
            return

        # Launch each server as a background task
        for name, cfg in config.items():
            conn = MCPConnection(name=name)
            task = asyncio.create_task(_run_server(conn, cfg))
            conn._task = task
            _connections[name] = conn

        # Wait briefly for servers to connect and discover tools
        await asyncio.sleep(3)

        total_tools = sum(len(c.tools) for c in _connections.values() if c.session)
        connected = sum(1 for c in _connections.values() if c.session)
        log.info("MCP bridge: %d/%d server(s) connected, %d total tool(s)",
                 connected, len(_connections), total_tools)
        _initialized = True


async def _shutdown_all():
    """Signal all servers to stop and wait for tasks to finish."""
    for conn in _connections.values():
        conn._shutdown.set()
    # Wait for tasks to finish (with timeout)
    tasks = [c._task for c in _connections.values() if c._task]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _connections.clear()


async def shutdown():
    """Disconnect all MCP servers. Call on server shutdown."""
    async with _lock:
        await _shutdown_all()


def get_mcp_tool_schemas() -> list[dict]:
    """Return tool schemas from all connected MCP servers.

    Safe to call from sync code — reads from cached connection state.
    """
    schemas = []
    for conn in _connections.values():
        if conn.session and conn.tools:
            schemas.extend(conn.tools)
    return schemas


async def call_mcp_tool(prefixed_name: str, arguments: dict) -> str:
    """Call an MCP tool by its namespaced name (server__tool).

    Returns the tool result as a string.
    """
    if "__" not in prefixed_name:
        return f"Error: invalid MCP tool name '{prefixed_name}' (expected server__tool)"

    server_name, tool_name = prefixed_name.split("__", 1)
    conn = _connections.get(server_name)

    if not conn or not conn.session:
        return f"Error: MCP server '{server_name}' is not connected"

    try:
        result = await conn.session.call_tool(tool_name, arguments)
        # Extract text content from result
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append(f"[binary data: {len(content.data)} bytes]")
            else:
                parts.append(str(content))
        return "\n".join(parts) if parts else "(empty result)"
    except Exception as e:
        return f"Error calling {server_name}/{tool_name}: {type(e).__name__}: {e}"


async def reload():
    """Re-read config and reconnect changed/new servers."""
    await initialize()
