#!/opt/homebrew/bin/python3
"""autoDream — background memory consolidation for topic files.

Reads memory/*.md files, prunes stale items, merges duplicates,
removes completed TODOs, and rewrites in place. Runs nightly via cron.

Safety:
- Protected files (behavioral rules, strategy, secure coding) are NEVER touched
- Changes >30% of file content are flagged for human review (written to .autodream_review/)
- All changes logged to .subconscious/autodream.log
- Git diff after run shows exactly what changed

Usage:
    /opt/homebrew/bin/python3 scripts/subconscious/autodream.py [--dry-run] [--file FILE] [--verbose]
"""

import argparse
import datetime
import difflib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# ── Config ────────────────────────────────────────────────────────────

MEMORY_DIR = Path(config.WORKSPACE) / "memory"
REVIEW_DIR = Path(config.STATE_DIR) / "autodream_review"
LOG_FILE = Path(config.STATE_DIR) / "autodream.log"

# Files that must NEVER be auto-pruned (behavioral rules, strategy, security)
PROTECTED_FILES = {
    "behavioral_rules.md",
    "secure_coding.md",
    "MEMORY.md",  # index file — managed separately
}

# Files that are reference-only (don't prune, just check staleness)
REFERENCE_ONLY_PREFIXES = ("reference_", "feedback_", "divorce_")

# Maximum change ratio before flagging for human review
MAX_AUTO_CHANGE_RATIO = 0.30

OLLAMA_MODEL = config.OLLAMA_MODEL
OLLAMA_URL = config.OLLAMA_URL
OLLAMA_TIMEOUT = 120


# ── Logging ───────────────────────────────────────────────────────────

def _log(msg: str, verbose: bool = False):
    """Append to autodream log and optionally print."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    if verbose:
        print(line)


# ── Staleness detection ───────────────────────────────────────────────

def check_staleness(file_path: Path) -> dict:
    """Check a memory file for staleness signals.

    Returns:
        dict with keys: file, age_days, stale_references, staleness_score (0-1)
    """
    mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
    age_days = (datetime.datetime.now() - mtime).days

    content = file_path.read_text()
    stale_refs = []

    # Check for file path references that no longer exist
    path_pattern = re.compile(r'[`"]([/~][\w/._ -]+\.\w+)[`"]')
    for match in path_pattern.finditer(content):
        ref_path = match.group(1)
        expanded = os.path.expanduser(ref_path)
        if ref_path.startswith(("/", "~")) and not os.path.exists(expanded):
            stale_refs.append(ref_path)

    # Check for "done" / "completed" / crossed-out items still in file
    done_pattern = re.compile(r'~~.+~~|✅\s*(Complete|Done|Built|Shipped)', re.IGNORECASE)
    done_count = len(done_pattern.findall(content))

    # Staleness score: 0 = fresh, 1 = very stale
    score = 0.0
    if age_days > 30:
        score += 0.3
    elif age_days > 14:
        score += 0.15
    if stale_refs:
        score += min(len(stale_refs) * 0.15, 0.4)
    if done_count > 3:
        score += 0.2

    return {
        "file": file_path.name,
        "age_days": age_days,
        "stale_references": stale_refs,
        "done_items": done_count,
        "staleness_score": round(min(score, 1.0), 2),
    }


# ── LLM consolidation ────────────────────────────────────────────────

def consolidate_file(content: str, filename: str, staleness: dict) -> str | None:
    """Send file to Ollama for consolidation. Returns rewritten content or None."""

    stale_context = ""
    if staleness["stale_references"]:
        stale_context += f"\nStale file references (no longer exist): {', '.join(staleness['stale_references'])}"
    if staleness["done_items"] > 0:
        stale_context += f"\nCompleted/done items found: {staleness['done_items']}"

    prompt = (
        f"You are a memory file consolidator. Rewrite this memory file to be more concise and current.\n\n"
        f"File: {filename}\n"
        f"Age: {staleness['age_days']} days since last update\n"
        f"{stale_context}\n\n"
        f"Rules:\n"
        f"- PRESERVE the YAML frontmatter (--- block) exactly as-is\n"
        f"- REMOVE completed/done items (crossed out with ~~ or marked with checkmarks)\n"
        f"- REMOVE references to files that no longer exist\n"
        f"- MERGE duplicate entries that say the same thing differently\n"
        f"- CONVERT vague statements to specific, actionable ones where possible\n"
        f"- PRESERVE all dates, version numbers, and specific technical details\n"
        f"- PRESERVE the overall structure (headers, sections)\n"
        f"- DO NOT add new information — only prune and consolidate what exists\n"
        f"- DO NOT change the meaning of any entry\n"
        f"- If the file is already clean and concise, return it unchanged\n\n"
        f"Current content:\n```\n{content}\n```\n\n"
        f"Return ONLY the rewritten file content, no explanation."
    )

    # autodream uses higher num_predict (prose output, not JSON)
    opts = dict(config.OLLAMA_OPTIONS)
    opts["num_predict"] = 2048
    payload = json.dumps({
        "model": OLLAMA_MODEL, "stream": False, "think": False,
        "prompt": prompt,
        "options": opts,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
        body = json.loads(resp.read().decode())
        result = body.get("response", "").strip()

        # Strip markdown fencing if model wrapped it
        result = re.sub(r'^```(?:markdown|md)?\s*\n?', '', result)
        result = re.sub(r'\n?```\s*$', '', result)

        # Sanity check: must still have frontmatter
        if not result.startswith("---"):
            return None

        return result
    except Exception as e:
        _log(f"  LLM error for {filename}: {e}")
        return None


# ── Diff and apply ────────────────────────────────────────────────────

def _change_ratio(old: str, new: str) -> float:
    """Calculate ratio of changed lines."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    if not old_lines:
        return 1.0
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    return round(1.0 - matcher.ratio(), 3)


def _unified_diff(old: str, new: str, filename: str) -> str:
    """Generate unified diff string."""
    return "\n".join(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"a/{filename}", tofile=f"b/{filename}",
        lineterm="",
    ))


# ── Index sync ────────────────────────────────────────────────────────

def sync_memory_index(verbose: bool = False):
    """Regenerate MEMORY.md index descriptions from file frontmatter."""
    index_path = MEMORY_DIR / "MEMORY.md"
    if not index_path.exists():
        return

    index_content = index_path.read_text()
    updated = False

    for md_file in sorted(MEMORY_DIR.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue

        content = md_file.read_text()
        # Extract description from frontmatter
        fm_match = re.search(r'^---\s*\n.*?description:\s*["\']?(.+?)["\']?\s*\n.*?---', content, re.DOTALL)
        if not fm_match:
            continue

        description = fm_match.group(1).strip().rstrip('"\'')
        stem = md_file.stem

        # Check if this file is in the index
        # Pattern: - [Name](memory/filename.md) — description
        idx_pattern = re.compile(
            rf'\- \[([^\]]+)\]\(memory/{re.escape(md_file.name)}\) — .+',
        )
        match = idx_pattern.search(index_content)
        if match:
            old_line = match.group(0)
            name = match.group(1)
            new_line = f"- [{name}](memory/{md_file.name}) — {description}"
            if old_line != new_line:
                index_content = index_content.replace(old_line, new_line)
                updated = True
                if verbose:
                    _log(f"  Index updated: {md_file.name}")

    if updated:
        index_path.write_text(index_content)
        _log("MEMORY.md index synced with file frontmatter")


# ── Main ──────────────────────────────────────────────────────────────

def run(dry_run: bool = False, target_file: str | None = None, verbose: bool = False):
    """Run autoDream consolidation on memory files."""
    _log(f"autoDream started (dry_run={dry_run})", verbose)

    os.makedirs(REVIEW_DIR, exist_ok=True)

    files = sorted(MEMORY_DIR.glob("*.md"))
    stats = {"scanned": 0, "pruned": 0, "flagged": 0, "skipped": 0, "unchanged": 0}

    for md_file in files:
        if md_file.name in PROTECTED_FILES:
            continue
        if md_file.name.startswith(REFERENCE_ONLY_PREFIXES):
            continue
        if target_file and md_file.name != target_file:
            continue

        stats["scanned"] += 1
        content = md_file.read_text()

        # Skip tiny files
        if len(content) < 200:
            stats["skipped"] += 1
            continue

        # Check staleness
        staleness = check_staleness(md_file)
        _log(f"  {md_file.name}: age={staleness['age_days']}d score={staleness['staleness_score']} "
             f"stale_refs={len(staleness['stale_references'])} done={staleness['done_items']}", verbose)

        # Only consolidate files with some staleness signal
        if staleness["staleness_score"] < 0.15:
            stats["unchanged"] += 1
            _log(f"  {md_file.name}: fresh, skipping", verbose)
            continue

        # Consolidate via LLM
        new_content = consolidate_file(content, md_file.name, staleness)
        if new_content is None:
            stats["skipped"] += 1
            _log(f"  {md_file.name}: LLM failed, skipping (check detailed log above)", verbose)
            continue

        # Calculate change ratio
        ratio = _change_ratio(content, new_content)
        diff = _unified_diff(content, new_content, md_file.name)

        if ratio < 0.02:
            stats["unchanged"] += 1
            _log(f"  {md_file.name}: no meaningful changes ({ratio:.1%})", verbose)
            continue

        if ratio > MAX_AUTO_CHANGE_RATIO:
            # Too many changes — flag for human review
            review_path = REVIEW_DIR / md_file.name
            if not dry_run:
                review_path.write_text(new_content)
                (REVIEW_DIR / f"{md_file.stem}.diff").write_text(diff)
            stats["flagged"] += 1
            _log(f"  {md_file.name}: FLAGGED for review ({ratio:.1%} changed) → {review_path}", verbose)
        else:
            # Safe to auto-apply
            if not dry_run:
                md_file.write_text(new_content)
            stats["pruned"] += 1
            _log(f"  {md_file.name}: pruned ({ratio:.1%} changed)", verbose)

        if verbose and diff:
            print(f"\n--- Diff for {md_file.name} ---")
            print(diff[:2000])
            if len(diff) > 2000:
                print(f"... ({len(diff)} chars total)")

    # Sync index after all changes
    if not dry_run and stats["pruned"] > 0:
        sync_memory_index(verbose)

    _log(f"autoDream complete: {stats}", verbose)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="autoDream memory consolidation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--file", type=str, help="Target a specific memory file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed output")
    args = parser.parse_args()

    stats = run(dry_run=args.dry_run, target_file=args.file, verbose=args.verbose)
    print(f"\nResults: {json.dumps(stats, indent=2)}")
