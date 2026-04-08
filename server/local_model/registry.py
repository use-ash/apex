"""Tool registry — maps tool names to JSON schemas and executor functions."""
from .tools import bash_tool, read_file, write_file, edit_file, list_files, search_files
from .tools.guide_tools import GUIDE_TOOL_DEFS as _GUIDE_TOOL_DEFS

try:
    from .tools import execute_code as _execute_code_mod
    _HAS_JUPYTER = True
except ImportError:
    _HAS_JUPYTER = False

TOOLS: dict[str, dict] = {}


def _register(name: str, description: str, parameters: dict, executor):
    """Register a tool with its schema and executor."""
    TOOLS[name] = {
        "schema": {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        },
        "executor": executor,
    }


# --- Register built-in tools ---

_register(
    "bash",
    "Execute a bash command and return its output. Use for running scripts, checking system state, git commands, or any shell operation.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute"},
        },
        "required": ["command"],
    },
    bash_tool.execute,
)

_register(
    "read_file",
    "Read the contents of a file. Returns the file content with line numbers.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to read"},
            "offset": {"type": "integer", "description": "Line number to start reading from (1-based). Default: 1"},
            "limit": {"type": "integer", "description": "Maximum number of lines to read. Default: 500"},
        },
        "required": ["file_path"],
    },
    read_file.execute,
)

_register(
    "write_file",
    "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "The content to write to the file"},
        },
        "required": ["file_path", "content"],
    },
    write_file.execute,
)

_register(
    "edit_file",
    "Edit a file by replacing a specific text span. Finds old_text exactly once and replaces it with new_text. More precise than write_file for targeted changes — no need to rewrite the entire file.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to edit"},
            "old_text": {"type": "string", "description": "Exact text to find (must match exactly once in the file)"},
            "new_text": {"type": "string", "description": "Replacement text"},
        },
        "required": ["file_path", "old_text", "new_text"],
    },
    edit_file.execute,
)

_register(
    "list_files",
    "List files matching a glob pattern. Returns matching file paths sorted by modification time.",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern to match (e.g. '**/*.py', 'src/*.ts')"},
            "path": {"type": "string", "description": "Directory to search in. Default: current working directory"},
        },
        "required": ["pattern"],
    },
    list_files.execute,
)

_register(
    "search_files",
    "Search file contents for a regex pattern (like grep). Returns matching lines with file paths and line numbers.",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern (regular expression)"},
            "path": {"type": "string", "description": "File or directory to search in. Default: current working directory"},
            "glob": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
        },
        "required": ["pattern"],
    },
    search_files.execute,
)


# --- Optional: Jupyter code execution (issue #1, set 2) ---

if _HAS_JUPYTER:
    _register(
        "execute_code",
        "Execute Python code in a stateful Jupyter kernel. Variables, imports, and "
        "function definitions persist between calls. ALWAYS use this tool instead of "
        "bash for ANY Python code — including print statements, calculations, scripts, "
        "and multi-step computations. State is preserved across calls.",
        {
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
        _execute_code_mod.execute,
    )


# --- Register guide configuration tools ---

for _gdef in _GUIDE_TOOL_DEFS:
    _register(
        _gdef["name"],
        _gdef["description"],
        _gdef["parameters"],
        _gdef["executor"],
    )


def get_tool_schemas(allowed_names: set[str] | None = None) -> list[dict]:
    """Return list of tool schemas for Ollama API (no executor key).

    Includes built-in tools + any connected MCP server tools.
    """
    if allowed_names is None:
        schemas = [t["schema"] for t in TOOLS.values()]
    else:
        schemas = [TOOLS[name]["schema"] for name in TOOLS if name in allowed_names]
    try:
        from .mcp_bridge import get_mcp_tool_schemas
        mcp_schemas = get_mcp_tool_schemas()
        if allowed_names is None:
            schemas.extend(mcp_schemas)
        else:
            schemas.extend(
                schema
                for schema in mcp_schemas
                if schema.get("function", {}).get("name") in allowed_names
            )
    except Exception:
        pass
    return schemas


def get_executor(name: str):
    """Return executor function for a tool name, or None."""
    tool = TOOLS.get(name)
    return tool["executor"] if tool else None


def is_mcp_tool(name: str) -> bool:
    """Check if a tool name is an MCP tool (server__tool format)."""
    return "__" in name and name not in TOOLS
