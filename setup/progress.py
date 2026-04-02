"""Setup wizard state persistence.

Saves/loads wizard progress to state/.setup_progress.json for
resumability. Uses atomic writes (temp + rename) to avoid corruption.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROGRESS_FILE = ".setup_progress.json"


def load_progress(state_dir: Path) -> dict:
    """Load progress file, return empty dict if missing or corrupt."""
    path = state_dir / PROGRESS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_progress(state_dir: Path, progress: dict) -> None:
    """Atomic write (temp + rename) to progress file.

    Creates the state directory if it does not exist.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / PROGRESS_FILE

    fd, tmp = tempfile.mkstemp(
        dir=str(state_dir), suffix=".tmp", prefix=".setup_progress_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2)
            f.write("\n")
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def phase_completed(state_dir: Path, phase: str) -> bool:
    """Check if a specific phase was completed."""
    progress = load_progress(state_dir)
    phases = progress.get("phases", {})
    phase_data = phases.get(phase, {})
    return bool(phase_data.get("completed", False))


def mark_phase_completed(state_dir: Path, phase: str, **metadata) -> None:
    """Mark a phase as completed with timestamp and optional metadata.

    Creates the progress structure if it does not exist. Preserves
    existing phases and metadata.
    """
    progress = load_progress(state_dir)

    # Ensure top-level structure
    if "version" not in progress:
        progress["version"] = 1
    if "phases" not in progress:
        progress["phases"] = {}

    # Build phase entry
    entry: dict = {
        "completed": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry.update(metadata)

    progress["phases"][phase] = entry
    save_progress(state_dir, progress)
