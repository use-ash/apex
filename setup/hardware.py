#!/opt/homebrew/bin/python3
"""Hardware detection for Apex onboarding wizard.
SECURITY: All data stays in memory. Never written to disk, never transmitted.
"""
from __future__ import annotations
import os, platform, shutil, subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class HardwareInfo:
    os: str              # "Darwin", "Linux", "Windows"
    arch: str            # "arm64", "x86_64"
    cpu_cores: int
    ram_gb: float
    gpu_vendor: str      # "apple", "nvidia", "amd", "none"
    gpu_vram_gb: float   # 0 if no discrete GPU; on Mac, same as ram_gb (unified)
    disk_available_gb: float
    is_apple_silicon: bool

def detect_hardware(workspace_path: Path) -> HardwareInfo:
    """Detect system hardware. All data stays in memory."""
    sys_os, arch = platform.system(), platform.machine()
    cpu_cores = os.cpu_count() or 1
    ram_gb = 0.0
    if sys_os == "Darwin":
        try:
            ram_gb = int(subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], timeout=5, text=True).strip()) / (1024**3)
        except (subprocess.SubprocessError, ValueError):
            pass
    elif sys_os == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_gb = int(line.split()[1]) / (1024**2)
                        break
        except (OSError, ValueError):
            pass
    gpu_vendor, gpu_vram_gb = "none", 0.0
    if sys_os == "Darwin" and arch == "arm64":
        gpu_vendor, gpu_vram_gb = "apple", ram_gb
    elif sys_os == "Linux":
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                timeout=5, text=True, stderr=subprocess.DEVNULL)
            gpu_vendor = "nvidia"
            gpu_vram_gb = max(int(l.strip()) for l in out.strip().splitlines() if l.strip()) / 1024
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            pass
    disk_gb = 0.0
    try:
        disk_gb = shutil.disk_usage(workspace_path).free / (1024**3)
    except OSError:
        pass
    apple_si = arch == "arm64" and sys_os == "Darwin"
    return HardwareInfo(os=sys_os, arch=arch, cpu_cores=cpu_cores,
        ram_gb=round(ram_gb, 1), gpu_vendor=gpu_vendor,
        gpu_vram_gb=round(gpu_vram_gb, 1), disk_available_gb=round(disk_gb, 1),
        is_apple_silicon=apple_si)

# (min_ram, ollama_name, mlx_name, size_gb, description) — checked top-down
_MODEL_TABLE: list[tuple[float, str, str, float, str]] = [
    (64, "qwen3.5:110b-a14b", "Qwen3.5-110B-A14B-4bit", 20, "MoE 110B, excellent reasoning + code"),
    (64, "deepseek-r1:70b",   "deepseek-r1-70b-4bit",   40, "Deep reasoning, strong on complex tasks"),
    (32, "qwen3.5:32b",       "Qwen3.5-32B-4bit",       20, "Dense 32B, strong all-rounder"),
    (32, "llama4:scout",      "llama-4-scout-4bit",      18, "Meta Scout MoE, fast + capable"),
    (16, "qwen3.5:32b-a3b",   "Qwen3.5-32B-A3B-4bit",    5, "Fast MoE, great for code + chat"),
    (16, "gemma3:27b",        "gemma-3-27b-4bit",        16, "Google Gemma 27B, balanced quality"),
    (8,  "gemma3:12b",        "gemma-3-12b-4bit",         7, "Gemma 12B, solid mid-range"),
    (8,  "qwen3.5:8b",        "Qwen3.5-8B-4bit",          5, "Qwen 8B, efficient and fast"),
    (0,  "gemma3:4b",         "gemma-3-4b-4bit",        2.5, "Compact Gemma 4B, fits anywhere"),
    (0,  "phi4-mini",         "phi-4-mini-4bit",         2.2, "Microsoft Phi-4 Mini, tiny + capable"),
]

def recommend_models(hw: HardwareInfo) -> list[dict]:
    """Return recommended local models sorted by priority, filtered by disk."""
    # Find the highest RAM tier that matches
    tier = max((r for r, *_ in _MODEL_TABLE if hw.ram_gb >= r), default=0)
    mlx = hw.is_apple_silicon
    candidates = []
    for min_ram, ollama, mlx_name, size_gb, desc in _MODEL_TABLE:
        if min_ram != tier or size_gb > hw.disk_available_gb:
            continue
        name = f"mlx-community/{mlx_name}" if mlx else ollama
        runtime = "mlx" if mlx else "ollama"
        candidates.append({"name": name, "size_gb": size_gb, "description": desc,
                           "recommended": len(candidates) == 0, "runtime": runtime})
    return candidates
