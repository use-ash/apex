#!/usr/bin/env python3
"""Phase 2: Model connection — detect, install, and configure AI backends.

All subprocess calls have timeouts. All network calls have timeouts.
Errors are handled gracefully (never crash the wizard).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError


# ---------------------------------------------------------------------------
# Cloud agent checks
# ---------------------------------------------------------------------------

def check_claude() -> dict:
    """Check if Claude Code CLI is installed and authenticated."""
    path = shutil.which("claude")
    if not path:
        return {"installed": False, "authenticated": False, "version": "", "path": ""}
    version = ""
    try:
        out = subprocess.check_output(
            [path, "--version"], timeout=5, text=True, stderr=subprocess.STDOUT
        )
        version = out.strip().splitlines()[0] if out.strip() else ""
    except (subprocess.SubprocessError, OSError):
        pass
    authenticated = Path.home().joinpath(".claude").is_dir()
    return {"installed": True, "authenticated": authenticated, "version": version, "path": path}


def check_codex() -> dict:
    """Check if Codex CLI is installed and authenticated."""
    path = shutil.which("codex")
    if not path:
        return {"installed": False, "authenticated": False, "version": "", "path": ""}
    version = ""
    try:
        out = subprocess.check_output(
            [path, "--version"], timeout=5, text=True, stderr=subprocess.STDOUT
        )
        version = out.strip().splitlines()[0] if out.strip() else ""
    except (subprocess.SubprocessError, OSError):
        pass
    authenticated = Path.home().joinpath(".codex", "auth.json").is_file()
    return {"installed": True, "authenticated": authenticated, "version": version, "path": path}


# ---------------------------------------------------------------------------
# Install helpers
# ---------------------------------------------------------------------------

def install_claude() -> bool:
    """Install Claude Code CLI. Returns True on success."""
    from setup.ui import print_success, print_info, print_error

    npm = shutil.which("npm")
    if npm:
        try:
            subprocess.run(
                [npm, "install", "-g", "@anthropic-ai/claude-code"],
                timeout=120, check=True,
            )
            print_success("Claude Code installed. Run `claude` once to authenticate.")
            return True
        except (subprocess.SubprocessError, OSError):
            pass

    brew = shutil.which("brew")
    if brew:
        try:
            subprocess.run(
                [brew, "install", "claude"], timeout=120, check=True,
            )
            print_success("Claude Code installed via Homebrew. Run `claude` once to authenticate.")
            return True
        except (subprocess.SubprocessError, OSError):
            pass

    print_error("Could not install Claude Code. Install npm or Homebrew and retry.")
    return False


def install_codex() -> bool:
    """Install Codex CLI. Returns True on success."""
    from setup.ui import print_success, print_error

    npm = shutil.which("npm")
    if not npm:
        print_error("npm not found. Install Node.js first, then retry.")
        return False
    try:
        subprocess.run(
            [npm, "install", "-g", "@openai/codex"],
            timeout=120, check=True,
        )
        print_success("Codex installed. Run `codex` once to authenticate.")
        return True
    except (subprocess.SubprocessError, OSError) as e:
        print_error(f"Codex install failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Local model backends
# ---------------------------------------------------------------------------

def check_ollama() -> dict:
    """Check if Ollama is installed and running."""
    path = shutil.which("ollama")
    if not path:
        return {"installed": False, "running": False, "models": []}
    models: list[str] = []
    running = False
    try:
        req = Request("http://localhost:11434/api/tags")
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        running = True
        models = [m["name"] for m in data.get("models", [])]
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        pass
    return {"installed": True, "running": running, "models": models}


def install_ollama() -> bool:
    """Install Ollama. Returns True on success."""
    sys_os = platform.system()
    if sys_os == "Darwin":
        brew = shutil.which("brew")
        if not brew:
            print("Homebrew not found. Install from https://ollama.ai manually.")
            return False
        try:
            subprocess.run([brew, "install", "ollama"], timeout=120, check=True)
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Ollama install failed: {e}")
            return False
    elif sys_os == "Linux":
        curl = shutil.which("curl")
        sh = shutil.which("sh")
        if not curl or not sh:
            print("curl/sh not found. Install from https://ollama.ai manually.")
            return False
        try:
            proc = subprocess.run(
                [curl, "-fsSL", "https://ollama.ai/install.sh"],
                timeout=30, capture_output=True, check=True,
            )
            subprocess.run(
                [sh], input=proc.stdout, timeout=120, check=True,
            )
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Ollama install failed: {e}")
            return False
    else:
        print(f"Automatic Ollama install not supported on {sys_os}.")
        return False

    # Start the service
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("Ollama installed and service started.")
    except OSError:
        print("Ollama installed but could not start service. Run `ollama serve` manually.")
    return True


def pull_ollama_model(model_name: str) -> bool:
    """Pull an Ollama model with real-time progress. Returns True on success."""
    ollama = shutil.which("ollama")
    if not ollama:
        print("Ollama not found.")
        return False
    try:
        proc = subprocess.Popen(
            [ollama, "pull", model_name],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            print(f"  {line.rstrip()}")
        ret = proc.wait(timeout=600)
        return ret == 0
    except (subprocess.SubprocessError, OSError) as e:
        print(f"Failed to pull {model_name}: {e}")
        return False


def check_mlx() -> dict:
    """Check if MLX LM is available and the server is running."""
    installed = False
    try:
        import importlib  # noqa: F811
        importlib.import_module("mlx_lm")
        installed = True
    except ImportError:
        pass

    running = False
    models: list[str] = []
    try:
        req = Request("http://localhost:8400/v1/models")
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        running = True
        models = [m["id"] for m in data.get("data", [])]
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        pass

    return {"installed": installed, "running": running, "models": models}


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

def validate_xai_key(key: str) -> bool:
    """Validate an xAI API key by format and test call."""
    if not key.startswith("xai-") or not (20 <= len(key) <= 200):
        return False
    try:
        req = Request(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (URLError, OSError):
        return False


def validate_google_key(key: str) -> bool:
    """Validate a Google API key by format and test embedding call."""
    if not key.startswith("AIza") or not (20 <= len(key) <= 200):
        return False
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/text-embedding-004:embedContent"
            f"?key={key}"
        )
        body = json.dumps({
            "model": "models/text-embedding-004",
            "content": {"parts": [{"text": "test"}]},
        }).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (URLError, OSError):
        return False


# ---------------------------------------------------------------------------
# .env management
# ---------------------------------------------------------------------------

def save_env_key(env_dir: Path, key_name: str, key_value: str) -> None:
    """Add or update a key in .env with atomic write and 0600 permissions."""
    env_path = env_dir / ".env"
    lines: list[str] = []
    found = False

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{key_name}="):
                lines.append(f"{key_name}={key_value}")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"{key_name}={key_value}")

    # Ensure trailing newline
    content = "\n".join(lines) + "\n"

    # Atomic write: temp file + rename
    env_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(env_dir), prefix=".env_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        from setup.compat import safe_chmod
        safe_chmod(tmp, 0o600)
        os.replace(tmp, str(env_path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_models_setup(apex_root: Path, env_dir: Path) -> dict:
    """Run the full Phase 2 model connection flow.

    Returns a summary dict of what was detected/configured.
    """
    from setup.ui import header, info, success, warn, ask_yes_no, ask_input
    from setup.hardware import detect_hardware, recommend_models

    summary: dict = {
        "claude": {},
        "codex": {},
        "ollama": {},
        "mlx": {},
        "grok_key": False,
        "google_key": False,
        "local_models": [],
    }

    # --- 1. Claude ---
    header("Claude Code")
    claude = check_claude()
    summary["claude"] = claude
    if claude["installed"]:
        auth_str = "authenticated" if claude["authenticated"] else "not authenticated"
        success(f"Claude Code found: {claude['version']} ({auth_str})")
        if not claude["authenticated"]:
            info("Run `claude` in a terminal to authenticate.")
    else:
        info("Claude Code CLI not found.")
        if ask_yes_no("Install Claude Code?"):
            if install_claude():
                summary["claude"] = check_claude()
            else:
                warn("Claude Code installation failed. You can install it later.")

    # --- 2. Codex ---
    header("OpenAI Codex")
    codex = check_codex()
    summary["codex"] = codex
    if codex["installed"]:
        auth_str = "authenticated" if codex["authenticated"] else "not authenticated"
        success(f"Codex found: {codex['version']} ({auth_str})")
        if not codex["authenticated"]:
            info("Run `codex` in a terminal to authenticate.")
    else:
        info("Codex CLI not found.")
        if ask_yes_no("Install Codex?"):
            if install_codex():
                summary["codex"] = check_codex()
            else:
                warn("Codex installation failed. You can install it later.")

    # --- 3. Grok (xAI) key ---
    header("Grok (xAI API)")
    existing_xai = os.environ.get("XAI_API_KEY", "")
    if existing_xai and validate_xai_key(existing_xai):
        success("xAI API key already configured and valid.")
        summary["grok_key"] = True
    else:
        info("Grok provides web research capabilities via xAI.")
        key = ask_input("xAI API key (or Enter to skip)", secret=True)
        if key:
            if validate_xai_key(key):
                save_env_key(env_dir, "XAI_API_KEY", key)
                success("xAI API key saved.")
                summary["grok_key"] = True
            else:
                warn("Key validation failed. Check your key and try again later.")

    # --- 4. Local models ---
    header("Local Models")
    hw = detect_hardware(apex_root)
    info(
        f"Detected: {hw.os} {hw.arch}, {hw.cpu_cores} cores, "
        f"{hw.ram_gb}GB RAM, GPU: {hw.gpu_vendor} ({hw.gpu_vram_gb}GB), "
        f"{hw.disk_available_gb}GB disk free"
    )

    recs = recommend_models(hw)
    if recs:
        top = [m for m in recs if m.get("tier") == "recommended"]
        alts = [m for m in recs if m.get("tier") == "alternative"]
        if top:
            info("Recommended models for your hardware:")
            for m in top:
                tag = " [recommended]" if m["recommended"] else ""
                info(f"  {m['name']} ({m['size_gb']}GB, {m['runtime']}){tag}")
                info(f"    {m['description']}")
        if alts:
            info("Smaller/faster alternatives:")
            for m in alts:
                info(f"  {m['name']} ({m['size_gb']}GB, {m['runtime']})")
                info(f"    {m['description']}")

    # Check/install Ollama (unless pure MLX)
    if not hw.is_apple_silicon or ask_yes_no("Set up Ollama for local models?"):
        ollama = check_ollama()
        summary["ollama"] = ollama
        if ollama["installed"]:
            running_str = "running" if ollama["running"] else "not running"
            success(f"Ollama installed ({running_str}), {len(ollama['models'])} model(s)")
            if ollama["models"]:
                info(f"  Models: {', '.join(ollama['models'])}")
        else:
            if ask_yes_no("Install Ollama?"):
                if install_ollama():
                    summary["ollama"] = check_ollama()

        # Offer to pull recommended model (use ollama_name — works on all platforms)
        if recs and summary["ollama"].get("running"):
            rec = recs[0]
            ollama_name = rec.get("ollama_name", rec["name"])
            if ollama_name not in summary["ollama"].get("models", []):
                if ask_yes_no(f"Pull {ollama_name}?"):
                    if pull_ollama_model(ollama_name):
                        summary["local_models"].append(ollama_name)

    # Check MLX on Apple Silicon
    if hw.is_apple_silicon:
        mlx = check_mlx()
        summary["mlx"] = mlx
        if mlx["installed"]:
            running_str = "running" if mlx["running"] else "not running"
            success(f"MLX LM available ({running_str}), {len(mlx['models'])} model(s)")
        else:
            info("MLX LM not installed. Install with: pip install mlx-lm")

    # --- 5. Google API key ---
    header("Google API (Embeddings)")
    existing_google = os.environ.get("GOOGLE_API_KEY", "")
    if existing_google and validate_google_key(existing_google):
        success("Google API key already configured and valid.")
        summary["google_key"] = True
    else:
        info("Google API key enables semantic search via Gemini embeddings.")
        key = ask_input("Google API key (or Enter to skip)", secret=True)
        if key:
            if validate_google_key(key):
                save_env_key(env_dir, "GOOGLE_API_KEY", key)
                success("Google API key saved.")
                summary["google_key"] = True
            else:
                warn("Key validation failed. Check your key and try again later.")

    # --- 6. Health summary ---
    header("Model Health Summary")
    _print_health_table(summary)

    return summary


def _print_health_table(summary: dict) -> None:
    """Print a compact health summary table."""
    from setup.ui import print_success, print_warning

    rows = [
        ("Claude Code", _status_str(summary["claude"])),
        ("Codex", _status_str(summary["codex"])),
        ("Grok (xAI)", "configured" if summary["grok_key"] else "not configured"),
        ("Ollama", _ollama_status(summary["ollama"])),
        ("MLX", _mlx_status(summary["mlx"])),
        ("Google API", "configured" if summary["google_key"] else "not configured"),
    ]
    max_label = max(len(r[0]) for r in rows)
    for label, status in rows:
        ok = "installed" in status or "configured" in status or "running" in status
        line = f"[{'+'if ok else '-'}] {label:<{max_label}}  {status}"
        if ok:
            print_success(line)
        else:
            print_warning(line)


def _status_str(info: dict) -> str:
    if not info:
        return "not checked"
    if not info.get("installed"):
        return "not installed"
    parts = ["installed"]
    if info.get("authenticated"):
        parts.append("authenticated")
    if info.get("version"):
        parts.append(info["version"])
    return ", ".join(parts)


def _ollama_status(info: dict) -> str:
    if not info:
        return "not checked"
    if not info.get("installed"):
        return "not installed"
    if not info.get("running"):
        return "installed, not running"
    n = len(info.get("models", []))
    return f"running, {n} model(s)"


def _mlx_status(info: dict) -> str:
    if not info:
        return "not checked"
    if not info.get("installed"):
        return "not installed"
    if not info.get("running"):
        return "installed, server not running"
    n = len(info.get("models", []))
    return f"running, {n} model(s)"
