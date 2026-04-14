#!/opt/homebrew/bin/python3
"""reDigest — re-extract heuristic session digests via LLM.

Finds digests that fell back to heuristic keyword matching (Ollama timed
out), reads the ORIGINAL .jsonl transcript, and re-runs LLM extraction
with a longer timeout to produce high-quality digests.

Safety:
- Original digests are backed up to .subconscious/digests_backup/
- Only overwrites heuristic digests (LLM digests are untouched)
- Dry-run mode shows what would change without writing

Usage:
    python3 redigest.py [--timeout 180] [--dry-run] [--verbose] [--limit N]
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state
import llm
from batch_digest import parse_transcript, TRANSCRIPTS_DIR

# ── Config ────────────────────────────────────────────────────────────

DIGESTS_DIR = Path(config.DIGESTS_DIR)
BACKUP_DIR = Path(config.STATE_DIR) / "digests_backup"


def find_heuristic_digests() -> list[tuple[str, Path, Path]]:
    """Find digests that used heuristic fallback AND have original transcripts.

    Returns (session_id, digest_path, transcript_path) sorted by transcript size desc.
    """
    results = []
    for digest_path in DIGESTS_DIR.glob("*.json"):
        session_id = digest_path.stem
        try:
            d = json.loads(digest_path.read_text())
            if d.get("summary", {}).get("source") != "heuristic":
                continue
            transcript = TRANSCRIPTS_DIR / f"{session_id}.jsonl"
            if not transcript.exists():
                # Also check the non-workspace project dir
                alt = Path.home() / ".claude/projects/-Users-dana--openclaw" / f"{session_id}.jsonl"
                if alt.exists():
                    transcript = alt
                else:
                    continue
            results.append((session_id, digest_path, transcript))
        except (json.JSONDecodeError, OSError):
            continue
    results.sort(key=lambda x: x[2].stat().st_size, reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(description="reDigest — upgrade heuristic digests via LLM")
    parser.add_argument("--timeout", type=int, default=180,
                        help="LLM timeout in seconds (default: 180)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without modifying digests")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed output")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N digests (0=all)")
    args = parser.parse_args()

    # Override timeouts and token budget for this run
    config.OLLAMA_TIMEOUT = args.timeout
    llm.OLLAMA_TIMEOUT = args.timeout
    # Bump num_predict — 512 is too small for rich sessions, truncates JSON
    # 1024 still truncates on sessions with many corrections/decisions; 2048 needed
    config.OLLAMA_OPTIONS = {**config.OLLAMA_OPTIONS, "num_predict": 2048}
    llm.OLLAMA_OPTIONS = config.OLLAMA_OPTIONS

    os.makedirs(BACKUP_DIR, exist_ok=True)
    config.ensure_dirs()

    sessions = find_heuristic_digests()
    if args.limit > 0:
        sessions = sessions[:args.limit]
    print(f"Found {len(sessions)} heuristic digests with transcripts (timeout={args.timeout}s)")

    processed = 0
    failed = 0
    skipped = 0

    for session_id, digest_path, transcript_path in sessions:
        size_kb = transcript_path.stat().st_size / 1024
        print(f"  RE-DIGEST {session_id[:8]} ({size_kb:.0f}KB)...", end=" ", flush=True)

        if args.dry_run:
            print("would re-extract [dry-run]")
            processed += 1
            continue

        try:
            messages, transcript_text = parse_transcript(transcript_path)
            if not messages or len(transcript_text) < 50:
                print("empty transcript")
                skipped += 1
                continue

            # Call _extract_via_llm directly to get a clear error on timeout
            result = llm._extract_via_llm(transcript_text)
            # Also get invariants
            result["invariants"] = llm.extract_invariants(transcript_text)

            if result.get("summary", {}).get("source") == "heuristic":
                print("still heuristic")
                failed += 1
                continue

            # Backup original before overwriting
            backup_path = BACKUP_DIR / digest_path.name
            if not backup_path.exists():
                shutil.copy2(digest_path, backup_path)

            # Save upgraded digest
            state.save_digest(session_id, result)

            # Merge into guidance
            current_guidance = state.read_guidance()
            from digest import _merge_guidance
            merged = _merge_guidance(current_guidance, result)
            state.write_guidance(merged)

            summary = result.get("summary", {}).get("text", "")[:80]
            n_c = len(result.get("corrections", []))
            n_p = len(result.get("pending", []))
            n_i = len(result.get("invariants", []))
            print(f"OK (llm) c={n_c} p={n_p} i={n_i} | {summary}")
            processed += 1

        except Exception as e:
            print(f"FAIL: {type(e).__name__}: {e}")
            failed += 1

    print(f"\nDone: {processed} upgraded, {failed} failed, {skipped} skipped")
    print(f"Guidance items: {len(state.read_guidance().get('items', []))}")


if __name__ == "__main__":
    main()
