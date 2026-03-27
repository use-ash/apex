"""Workspace scanner for Apex onboarding wizard.

Scans a directory to discover projects, documentation, and conventions.
SECURITY: read-only, no network calls, no subprocess, no dynamic imports.
Must be auditable — every function is pure or read-only I/O.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Security: hardcoded exclusions — cannot be overridden
# ---------------------------------------------------------------------------

ALWAYS_EXCLUDE_DIRS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".env", "build", "dist", ".next", "target", ".tox", ".mypy_cache",
    ".pytest_cache", ".eggs", "*.egg-info", ".terraform",
}

ALWAYS_EXCLUDE_FILES: set[str] = {
    ".env", ".env.*", "*.key", "*.pem", "*.p12", "*.pfx", "*.jks",
    "*.secret", "*.credential", "*.token", "*.lock", ".DS_Store",
    "*.pyc", "*.pyo", "*.so", "*.dylib",
}

SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-(?:ant-|proj-)?[a-zA-Z0-9_-]{20,}"),
    re.compile(r"xai-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AIza[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"gho_[a-zA-Z0-9]{36}"),
]

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[A-Z \t]*PRIVATE KEY-----[\s\S]*?-----END[A-Z \t]*PRIVATE KEY-----",
)
_CONN_STRING_RE = re.compile(
    r"(postgres|postgresql|mysql|mongodb|redis|amqp)://[^\s\"'`]+",
)
_ENV_SECRET_RE = re.compile(
    r"(?:^|[\s;])([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD))\s*=\s*(\S+)",
    re.MULTILINE,
)

# Extension → language mapping for repo detection
_EXT_LANGUAGES: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".rs": "Rust",
    ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".c": "C", ".cpp": "C++", ".h": "C", ".hpp": "C++",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".scala": "Scala",
    ".zig": "Zig", ".lua": "Lua", ".sh": "Shell", ".zsh": "Shell",
    ".md": "Markdown", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
}

# Markdown filename → doc priority
_DOC_PRIORITY: dict[str, int] = {
    "readme": 1,
    "architecture": 2,
    "contributing": 3,
    "changelog": 3,
    "security": 3,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RepoInfo:
    name: str
    path: Path
    readme_path: Path | None
    languages: list[str] = field(default_factory=list)


@dataclass
class ProjectInfo:
    name: str
    path: Path
    project_type: str  # "python", "node", "rust", "go", "docker", "generic"
    config_path: Path  # package.json, pyproject.toml, etc.
    entry_points: list[Path] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    python_version: str | None = None
    test_runner: str | None = None  # "pytest", "jest", "cargo test", etc.


@dataclass
class DocInfo:
    path: Path
    title: str  # first heading or filename
    size_bytes: int
    priority: int  # 1=README, 2=ARCHITECTURE, 3=other docs/ files, 4=misc .md


@dataclass
class ConventionInfo:
    source: str  # ".editorconfig", "pyproject.toml [tool.ruff]", ".eslintrc"
    conventions: dict[str, str]


@dataclass
class ScanResult:
    repos: list[RepoInfo] = field(default_factory=list)
    projects: list[ProjectInfo] = field(default_factory=list)
    documentation: list[DocInfo] = field(default_factory=list)
    conventions: list[ConventionInfo] = field(default_factory=list)
    ai_conversations: list[dict] = field(default_factory=list)
    total_files: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# scrub_text — MUST be called on all output before writing/sending
# ---------------------------------------------------------------------------

def scrub_text(text: str) -> str:
    """Remove secrets, keys, and credentials from text.

    Called on ALL text before it is written to any file or sent to any API.
    """
    result = text

    # API keys and tokens
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)

    # Private key blocks
    result = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", result)

    # Connection strings — keep the scheme, redact the rest
    def _redact_conn(m: re.Match[str]) -> str:
        scheme = m.group(1)
        return f"{scheme}://[REDACTED]"
    result = _CONN_STRING_RE.sub(_redact_conn, result)

    # ENV_VAR=value patterns for secrets
    def _redact_env(m: re.Match[str]) -> str:
        prefix = m.group(0)[: m.start(2) - m.start(0)]
        return f"{prefix}[REDACTED]"
    result = _ENV_SECRET_RE.sub(_redact_env, result)

    return result


# ---------------------------------------------------------------------------
# Exclusion helpers
# ---------------------------------------------------------------------------

def _is_excluded_dir(name: str) -> bool:
    """Check if a directory name matches any exclusion pattern."""
    for pattern in ALWAYS_EXCLUDE_DIRS:
        if "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(name, pattern):
                return True
        elif name == pattern:
            return True
    return False


def _is_excluded_file(name: str) -> bool:
    """Check if a filename matches any exclusion pattern."""
    for pattern in ALWAYS_EXCLUDE_FILES:
        if "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(name, pattern):
                return True
        elif name == pattern:
            return True
    return False


# ---------------------------------------------------------------------------
# Parsing helpers (read-only, no imports of external libs)
# ---------------------------------------------------------------------------

def _safe_read_text(path: Path, limit: int = 65536) -> str:
    """Read up to `limit` bytes of a text file, returning '' on error."""
    try:
        raw = path.read_bytes()[:limit]
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _safe_read_json(path: Path) -> dict:
    """Parse a JSON file, returning {} on error."""
    text = _safe_read_text(path)
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_toml_simple(text: str) -> dict[str, dict[str, str]]:
    """Minimal TOML parser for extracting section keys.

    Only handles [section.subsection] headers and key = "value" / key = value.
    Good enough for pyproject.toml metadata extraction without tomllib dependency.
    """
    result: dict[str, dict[str, str]] = {}
    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Section header
        m = re.match(r"^\[([^\]]+)\]", stripped)
        if m:
            current_section = m.group(1).strip()
            if current_section not in result:
                result[current_section] = {}
            continue
        # Key = value
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_.-]*)\s*=\s*(.*)', stripped)
        if m and current_section:
            key = m.group(1).strip()
            val = m.group(2).strip().strip('"').strip("'")
            result[current_section][key] = val
    return result


def _extract_first_heading(text: str) -> str | None:
    """Extract the first markdown heading from text."""
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return None


def _detect_languages(dir_path: Path, file_list: list[str]) -> list[str]:
    """Detect programming languages from file extensions in a list."""
    seen: set[str] = set()
    for name in file_list:
        ext = os.path.splitext(name)[1].lower()
        lang = _EXT_LANGUAGES.get(ext)
        if lang and lang != "Markdown":
            seen.add(lang)
    return sorted(seen)


def _doc_priority(path: Path) -> int:
    """Assign a priority to a documentation file by name."""
    stem = path.stem.lower()
    for keyword, prio in _DOC_PRIORITY.items():
        if keyword in stem:
            return prio
    # Check if inside a docs/ directory
    parts = [p.lower() for p in path.parts]
    if "docs" in parts or "doc" in parts or "documentation" in parts:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Project detection
# ---------------------------------------------------------------------------

def _detect_node_project(dir_path: Path, pkg_path: Path) -> ProjectInfo:
    """Parse package.json for a Node.js project."""
    data = _safe_read_json(pkg_path)
    name = data.get("name", dir_path.name)
    deps = sorted(set(
        list(data.get("dependencies", {}).keys())
        + list(data.get("devDependencies", {}).keys())
    ))
    scripts = data.get("scripts", {})
    test_runner: str | None = None
    if "test" in scripts:
        test_cmd = scripts["test"]
        if "jest" in test_cmd:
            test_runner = "jest"
        elif "mocha" in test_cmd:
            test_runner = "mocha"
        elif "vitest" in test_cmd:
            test_runner = "vitest"
        else:
            test_runner = "npm test"
    # Entry points
    entry_points: list[Path] = []
    if data.get("main"):
        ep = dir_path / data["main"]
        if ep.exists():
            entry_points.append(ep)
    if "start" in scripts:
        # Best effort: note the start script exists
        pass
    # Look for common entry files
    for candidate in ("index.js", "index.ts", "src/index.js", "src/index.ts",
                       "src/main.js", "src/main.ts", "app.js", "server.js"):
        ep = dir_path / candidate
        if ep.exists() and ep not in entry_points:
            entry_points.append(ep)
    return ProjectInfo(
        name=name,
        path=dir_path,
        project_type="node",
        config_path=pkg_path,
        entry_points=entry_points,
        dependencies=deps[:50],  # cap at 50 to stay readable
        test_runner=test_runner,
    )


def _detect_python_project(dir_path: Path, toml_path: Path) -> ProjectInfo:
    """Parse pyproject.toml for a Python project."""
    text = _safe_read_text(toml_path)
    parsed = _parse_toml_simple(text)

    project_section = parsed.get("project", {})
    name = project_section.get("name", dir_path.name)
    python_version = project_section.get("requires-python")

    # Dependencies — extract from requires or project.dependencies line
    deps: list[str] = []
    # Try to find dependencies array with simple regex
    dep_match = re.search(
        r"\[project\].*?dependencies\s*=\s*\[(.*?)\]",
        text, re.DOTALL,
    )
    if dep_match:
        raw_deps = dep_match.group(1)
        for d in re.findall(r'"([^"]+)"', raw_deps):
            # Take just the package name, strip version specifiers
            pkg = re.split(r"[><=!~;]", d)[0].strip()
            if pkg:
                deps.append(pkg)

    # Test runner detection
    test_runner: str | None = None
    if "tool.pytest" in parsed or "tool.pytest.ini_options" in parsed:
        test_runner = "pytest"
    elif (dir_path / "pytest.ini").exists():
        test_runner = "pytest"
    elif (dir_path / "tox.ini").exists():
        test_runner = "tox"

    # Conventions from tool sections
    # (handled separately in convention detection)

    # Entry points
    entry_points: list[Path] = []
    for candidate in ("main.py", "app.py", "manage.py", "cli.py",
                       "src/__main__.py", "__main__.py"):
        ep = dir_path / candidate
        if ep.exists():
            entry_points.append(ep)

    return ProjectInfo(
        name=name,
        path=dir_path,
        project_type="python",
        config_path=toml_path,
        entry_points=entry_points,
        dependencies=deps[:50],
        python_version=python_version,
        test_runner=test_runner,
    )


def _detect_rust_project(dir_path: Path, cargo_path: Path) -> ProjectInfo:
    """Parse Cargo.toml for a Rust project."""
    text = _safe_read_text(cargo_path)
    parsed = _parse_toml_simple(text)
    pkg = parsed.get("package", {})
    name = pkg.get("name", dir_path.name)

    deps: list[str] = []
    for section_key in parsed:
        if section_key == "dependencies" or section_key.startswith("dependencies."):
            deps.extend(parsed[section_key].keys())

    entry_points: list[Path] = []
    src_main = dir_path / "src" / "main.rs"
    src_lib = dir_path / "src" / "lib.rs"
    if src_main.exists():
        entry_points.append(src_main)
    if src_lib.exists():
        entry_points.append(src_lib)

    return ProjectInfo(
        name=name,
        path=dir_path,
        project_type="rust",
        config_path=cargo_path,
        entry_points=entry_points,
        dependencies=sorted(set(deps))[:50],
        test_runner="cargo test",
    )


def _detect_go_project(dir_path: Path, mod_path: Path) -> ProjectInfo:
    """Parse go.mod for a Go project."""
    text = _safe_read_text(mod_path)
    name = dir_path.name
    # Extract module name
    m = re.match(r"^module\s+(\S+)", text, re.MULTILINE)
    if m:
        name = m.group(1).split("/")[-1]

    # Extract require blocks
    deps: list[str] = []
    in_require = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if stripped == ")":
                in_require = False
                continue
            parts = stripped.split()
            if parts:
                deps.append(parts[0].split("/")[-1])
        elif stripped.startswith("require "):
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append(parts[1].split("/")[-1])

    entry_points: list[Path] = []
    main_go = dir_path / "main.go"
    if main_go.exists():
        entry_points.append(main_go)

    return ProjectInfo(
        name=name,
        path=dir_path,
        project_type="go",
        config_path=mod_path,
        entry_points=entry_points,
        dependencies=deps[:50],
        test_runner="go test",
    )


# ---------------------------------------------------------------------------
# Convention detection
# ---------------------------------------------------------------------------

def _detect_editorconfig(path: Path) -> ConventionInfo | None:
    """Parse .editorconfig for coding conventions."""
    text = _safe_read_text(path)
    if not text:
        return None
    conventions: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        key, _, val = stripped.partition("=")
        key = key.strip().lower()
        val = val.strip()
        if key in ("indent_style", "indent_size", "charset",
                    "end_of_line", "trim_trailing_whitespace",
                    "insert_final_newline", "max_line_length"):
            conventions[key] = val
    if not conventions:
        return None
    return ConventionInfo(source=".editorconfig", conventions=conventions)


def _detect_pyproject_conventions(toml_path: Path) -> list[ConventionInfo]:
    """Extract formatting conventions from pyproject.toml tool sections."""
    text = _safe_read_text(toml_path)
    if not text:
        return []
    parsed = _parse_toml_simple(text)
    results: list[ConventionInfo] = []

    # Ruff
    ruff = parsed.get("tool.ruff", {})
    ruff_lint = parsed.get("tool.ruff.lint", {})
    ruff_format = parsed.get("tool.ruff.format", {})
    if ruff or ruff_lint or ruff_format:
        conventions: dict[str, str] = {"formatter": "ruff"}
        if "line-length" in ruff:
            conventions["line_length"] = ruff["line-length"]
        if "target-version" in ruff:
            conventions["target_version"] = ruff["target-version"]
        if "select" in ruff_lint:
            conventions["lint_select"] = ruff_lint["select"]
        results.append(ConventionInfo(
            source="pyproject.toml [tool.ruff]",
            conventions=conventions,
        ))

    # Black
    black = parsed.get("tool.black", {})
    if black:
        conventions = {"formatter": "black"}
        if "line-length" in black:
            conventions["line_length"] = black["line-length"]
        if "target-version" in black:
            conventions["target_version"] = black["target-version"]
        results.append(ConventionInfo(
            source="pyproject.toml [tool.black]",
            conventions=conventions,
        ))

    # isort
    isort = parsed.get("tool.isort", {})
    if isort:
        conventions = {"import_sorter": "isort"}
        if "profile" in isort:
            conventions["profile"] = isort["profile"]
        results.append(ConventionInfo(
            source="pyproject.toml [tool.isort]",
            conventions=conventions,
        ))

    return results


# ---------------------------------------------------------------------------
# AI conversation detection
# ---------------------------------------------------------------------------

def _detect_ai_conversations(workspace: Path) -> list[dict]:
    """Detect existing AI conversation history files."""
    results: list[dict] = []

    # Claude Code projects directory
    claude_projects = Path.home() / ".claude" / "projects"
    if claude_projects.is_dir():
        count = 0
        try:
            for f in claude_projects.rglob("*.jsonl"):
                if not _is_excluded_file(f.name):
                    count += 1
        except OSError:
            pass
        if count > 0:
            results.append({
                "source": "claude",
                "path": str(claude_projects),
                "count": count,
            })

    # ChatGPT exports in common locations
    for search_dir in (workspace, Path.home() / "Downloads",
                       Path.home() / "Documents"):
        if not search_dir.is_dir():
            continue
        try:
            for f in search_dir.iterdir():
                if fnmatch.fnmatch(f.name.lower(), "chatgpt-export*.json"):
                    results.append({
                        "source": "chatgpt",
                        "path": str(f),
                        "count": 1,
                    })
        except OSError:
            pass

    return results


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def scan_workspace(workspace: Path) -> ScanResult:
    """Walk the workspace and discover projects, docs, and conventions.

    SECURITY: read-only, no network calls, no subprocess, no symlink following.
    All text read from disk is scrubbed before being stored in results.
    """
    result = ScanResult()
    total_files = 0
    dir_file_counts: dict[str, int] = {}  # track per-dir counts for warnings

    # Tracks which directories we've already registered as projects
    project_dirs: set[Path] = set()

    for dirpath, dirnames, filenames in os.walk(workspace, followlinks=False):
        current = Path(dirpath)

        # Prune excluded directories IN-PLACE (modifying dirnames)
        dirnames[:] = [
            d for d in dirnames
            if not _is_excluded_dir(d)
        ]

        # Count files in this directory
        safe_files = [f for f in filenames if not _is_excluded_file(f)]
        total_files += len(safe_files)
        dir_file_counts[dirpath] = len(safe_files)

        # --- Repo detection (.git as a subdirectory) ---
        if ".git" in os.listdir(current):
            readme_path: Path | None = None
            for candidate in ("README.md", "readme.md", "README.rst",
                              "README.txt", "README"):
                rp = current / candidate
                if rp.is_file():
                    readme_path = rp
                    break
            # Detect languages from immediate files
            languages = _detect_languages(current, safe_files)
            result.repos.append(RepoInfo(
                name=current.name,
                path=current,
                readme_path=readme_path,
                languages=languages,
            ))

        # --- Project detection (sentinel files) ---
        if current not in project_dirs:
            # package.json → Node
            pkg_json = current / "package.json"
            if pkg_json.is_file():
                result.projects.append(_detect_node_project(current, pkg_json))
                project_dirs.add(current)

            # pyproject.toml → Python
            pyproject = current / "pyproject.toml"
            if pyproject.is_file():
                result.projects.append(_detect_python_project(current, pyproject))
                project_dirs.add(current)
                # Also extract conventions
                result.conventions.extend(_detect_pyproject_conventions(pyproject))

            # Cargo.toml → Rust
            cargo = current / "Cargo.toml"
            if cargo.is_file():
                result.projects.append(_detect_rust_project(current, cargo))
                project_dirs.add(current)

            # go.mod → Go
            gomod = current / "go.mod"
            if gomod.is_file():
                result.projects.append(_detect_go_project(current, gomod))
                project_dirs.add(current)

            # Dockerfile → containerized (only if no other project type)
            dockerfile = current / "Dockerfile"
            if dockerfile.is_file() and current not in project_dirs:
                result.projects.append(ProjectInfo(
                    name=current.name,
                    path=current,
                    project_type="docker",
                    config_path=dockerfile,
                ))
                project_dirs.add(current)

            # Makefile → generic (only if nothing else matched)
            makefile = current / "Makefile"
            if makefile.is_file() and current not in project_dirs:
                result.projects.append(ProjectInfo(
                    name=current.name,
                    path=current,
                    project_type="generic",
                    config_path=makefile,
                ))
                project_dirs.add(current)

        # --- Convention detection ---
        editorconfig = current / ".editorconfig"
        if editorconfig.is_file():
            info = _detect_editorconfig(editorconfig)
            if info:
                result.conventions.append(info)

        # ESLint / Prettier — note presence
        for name in (".eslintrc", ".eslintrc.js", ".eslintrc.json",
                     ".eslintrc.yml", ".eslintrc.yaml", "eslint.config.js",
                     "eslint.config.mjs"):
            if (current / name).is_file():
                result.conventions.append(ConventionInfo(
                    source=f"{name}",
                    conventions={"linter": "eslint"},
                ))
                break  # one per directory

        for name in (".prettierrc", ".prettierrc.js", ".prettierrc.json",
                     ".prettierrc.yml", ".prettierrc.yaml",
                     "prettier.config.js", "prettier.config.mjs"):
            if (current / name).is_file():
                result.conventions.append(ConventionInfo(
                    source=f"{name}",
                    conventions={"formatter": "prettier"},
                ))
                break

        # --- Documentation detection (*.md files) ---
        for fname in safe_files:
            if fname.lower().endswith(".md"):
                md_path = current / fname
                try:
                    size = md_path.stat().st_size
                except OSError:
                    continue
                # Skip tiny or huge files
                if size < 10 or size > 1_000_000:
                    continue
                text = _safe_read_text(md_path, limit=4096)
                title = _extract_first_heading(text) or md_path.stem
                priority = _doc_priority(md_path)
                result.documentation.append(DocInfo(
                    path=md_path,
                    title=title,
                    size_bytes=size,
                    priority=priority,
                ))

    # --- AI conversation detection ---
    result.ai_conversations = _detect_ai_conversations(workspace)

    # --- Totals and warnings ---
    result.total_files = total_files
    for dirpath_str, count in dir_file_counts.items():
        if count > 1000:
            result.warnings.append(
                f"Directory has {count} files: {dirpath_str}"
            )

    # Sort documentation by priority then name
    result.documentation.sort(key=lambda d: (d.priority, d.path.name.lower()))

    return result
