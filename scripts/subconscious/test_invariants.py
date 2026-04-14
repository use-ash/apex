#!/opt/homebrew/bin/python3
"""Test the MemCollab-inspired invariant extraction pipeline.

Usage:
    # Test with a synthetic transcript (no Ollama needed for format check)
    python3 test_invariants.py --dry-run

    # Test with live Ollama extraction on a sample transcript
    python3 test_invariants.py --live

    # Test with an actual session transcript file
    python3 test_invariants.py --transcript /path/to/transcript.jsonl

    # Show current guidance.json with invariants highlighted
    python3 test_invariants.py --guidance
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import llm
import state

# ── Synthetic test transcript ────────────────────────────────────────
SAMPLE_TRANSCRIPT = """
[user] Can you update the server launch script to use nohup?
[assistant] Sure, I'll update the launch script to use nohup for background execution.
[user] No, don't use nohup. Always use launch_dana.sh in tmux. That's the rule.
[assistant] Got it, I'll use launch_dana.sh in tmux instead.
[user] Also the model health dots are showing red
[assistant] The red dots indicate the API key is missing from the environment.
[user] No, red means the API reachability check failed, not just key presence. It actually pings the endpoint.
[assistant] You're right — the health check performs an actual API reachability test, not just checking for key presence.
[user] Can you fix the digest script? It's dumping raw tool_result JSON into the guidance file as corrections.
[assistant] I see the issue — the heuristic fallback in _extract_heuristic is treating tool_result messages as user corrections because they contain the word "no" in the content. I'll add a filter to skip tool_result blobs.
[user] Yes exactly. And while you're at it, make sure the compaction model falls back to Ollama if Grok is down.
[assistant] I'll update the fallback chain: Grok 4 Fast → Ollama gemma3:27b → empty string.
[user] Good. And remember, on this codebase always use /opt/homebrew/bin/python3 for the Python path. Not just python3.
""".strip()


def _print_section(title: str, char: str = "─"):
    width = 70
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def _print_items(items: list, label: str = ""):
    if not items:
        print(f"  (no {label} found)")
        return
    for i, item in enumerate(items, 1):
        if isinstance(item, dict):
            if item.get("type") == "invariant" or "context" in item:
                ctx = item.get("context", "?")
                enf = item.get("enforce", "?")
                avd = item.get("avoid", "?")
                conf = item.get("confidence", 0)
                src = item.get("source", "?")
                print(f"  {i}. [{src} conf={conf:.2f}]")
                print(f"     WHEN: {ctx}")
                print(f"     ENFORCE: {enf}")
                print(f"     AVOID: {avd}")
            else:
                typ = item.get("type", "?")
                text = item.get("text", str(item))
                conf = item.get("confidence", 0)
                print(f"  {i}. [{typ} conf={conf:.2f}] {text}")
        else:
            print(f"  {i}. {item}")


def test_dry_run():
    """Test format validation without calling Ollama."""
    _print_section("DRY RUN — Format Validation")

    # Simulate what a well-formed extraction looks like
    mock_invariants = [
        {
            "context": "launching the Apex server",
            "enforce": "Use launch_dana.sh in a tmux session",
            "avoid": "Using nohup or direct process spawning",
            "confidence": 0.92,
            "source": "contrastive",
        },
        {
            "context": "interpreting model health status indicators",
            "enforce": "Treat red dots as API reachability check failures (actual endpoint ping)",
            "avoid": "Assuming red means only that the API key is missing from environment",
            "confidence": 0.88,
            "source": "contrastive",
        },
        {
            "context": "running Python scripts in this workspace",
            "enforce": "Use /opt/homebrew/bin/python3 (3.14) as the explicit interpreter path",
            "avoid": "Using bare 'python3' which may resolve to a different version",
            "confidence": 0.90,
            "source": "contrastive",
        },
    ]

    print("\n  Simulated invariants from sample transcript:")
    _print_items(mock_invariants, "invariants")

    # Test whisper rendering
    _print_section("Whisper Rendering Preview")
    print("  <subconscious_whisper>")
    for inv in mock_invariants:
        ctx = inv["context"]
        enf = inv["enforce"]
        avd = inv["avoid"]
        print(f"  - [invariant] When {ctx}: enforce {enf}; avoid {avd}")
    print("  - [correction] thats what i did")
    print("  - [decision] Fallback chain: Grok 4 Fast → Ollama → empty")
    print("  </subconscious_whisper>")

    # Test merge logic
    _print_section("Merge Deduplication Test")
    from digest import _similarity, _merge_guidance

    # Simulate merging a duplicate invariant
    existing_guidance = {"items": [
        {
            "type": "invariant",
            "context": "launching the Apex server",
            "enforce": "Use launch_dana.sh in a tmux session",
            "avoid": "Using nohup or direct process spawning",
            "confidence": 0.88,
            "source": "contrastive",
            "created_at": "2026-03-27T00:00:00+00:00",
            "ttl_days": 30,
            "text": "When launching the Apex server: enforce Use launch_dana.sh; avoid nohup",
        }
    ]}
    digest_with_dup = {
        "corrections": [],
        "decisions": [],
        "pending": [],
        "invariants": [
            {
                "context": "launching the Apex server process",
                "enforce": "Always use launch_dana.sh inside tmux",
                "avoid": "Using nohup or spawning the process directly",
                "confidence": 0.90,
                "source": "contrastive",
            }
        ],
    }
    merged = _merge_guidance(existing_guidance, digest_with_dup)
    invariants_after = [i for i in merged["items"] if i.get("type") == "invariant"]
    print(f"  Invariants before merge: 1")
    print(f"  Invariants after merge:  {len(invariants_after)}")
    if invariants_after:
        print(f"  Confidence after reinforcement: {invariants_after[0].get('confidence', '?')}")
    if len(invariants_after) == 1:
        print("  ✓ Dedup worked — duplicate merged, confidence reinforced")
    else:
        print("  ✗ Dedup failed — duplicate was added")

    # Test TTL
    _print_section("TTL Pruning Test")
    import datetime
    old_item = {
        "type": "correction",
        "text": "old correction",
        "confidence": 0.8,
        "created_at": (datetime.datetime.now(datetime.timezone.utc)
                       - datetime.timedelta(days=10)).isoformat(),
    }
    old_invariant = {
        "type": "invariant",
        "context": "old invariant context",
        "enforce": "old enforce",
        "avoid": "old avoid",
        "text": "old invariant",
        "confidence": 0.9,
        "ttl_days": 30,
        "created_at": (datetime.datetime.now(datetime.timezone.utc)
                       - datetime.timedelta(days=10)).isoformat(),
    }
    test_guidance = {"items": [old_item, old_invariant]}

    # Simulate read_guidance pruning (inline version)
    now = datetime.datetime.now(datetime.timezone.utc)
    pruned = []
    for item in test_guidance["items"]:
        ts = item.get("created_at", "")
        if ts:
            item_dt = datetime.datetime.fromisoformat(ts)
            ttl = item.get("ttl_days", config.GUIDANCE_MAX_AGE_DAYS)
            cutoff = now - datetime.timedelta(days=ttl)
            if item_dt < cutoff:
                continue
        pruned.append(item)

    corrs = [i for i in pruned if i["type"] == "correction"]
    invs = [i for i in pruned if i["type"] == "invariant"]
    print(f"  10-day-old correction (7d TTL): {'✗ pruned' if not corrs else '✓ kept (ERROR)'}")
    print(f"  10-day-old invariant (30d TTL): {'✓ kept' if invs else '✗ pruned (ERROR)'}")

    print(f"\n{'═' * 70}")
    print("  DRY RUN COMPLETE — all format/logic tests passed")
    print(f"{'═' * 70}\n")


def test_live():
    """Test live extraction via Ollama with the sample transcript."""
    _print_section("LIVE TEST — Ollama Invariant Extraction")
    print(f"  Primary model:    {config.OLLAMA_MODEL}")
    print(f"  Validation model: {config.OLLAMA_VALIDATION_MODEL}")
    print(f"  Confidence threshold: {config.INVARIANT_CONFIDENCE_THRESHOLD}")
    print(f"  Max per session: {config.INVARIANT_MAX_PER_SESSION}")

    _print_section("Sample Transcript")
    for line in SAMPLE_TRANSCRIPT.split("\n")[:6]:
        print(f"  {line}")
    print("  ...")

    # Run standard extraction first
    _print_section("Standard Extraction (current format)")
    t0 = time.time()
    try:
        standard = llm._extract_via_llm(SAMPLE_TRANSCRIPT)
        t1 = time.time()
        print(f"  Time: {t1 - t0:.1f}s")
        print("\n  Corrections:")
        _print_items(standard.get("corrections", []), "corrections")
        print("\n  Decisions:")
        _print_items(standard.get("decisions", []), "decisions")
        print("\n  Pending:")
        _print_items(standard.get("pending", []), "pending")
        print(f"\n  Summary: {standard.get('summary', {}).get('text', '?')}")
    except Exception as e:
        print(f"  ✗ Standard extraction failed: {e}")
        return

    # Run invariant extraction (pass 1 + pass 2)
    _print_section("Pass 1 — Invariant Extraction (gemma3:27b)")
    t0 = time.time()
    try:
        candidates = llm._extract_invariants_pass1(SAMPLE_TRANSCRIPT)
        t1 = time.time()
        print(f"  Time: {t1 - t0:.1f}s")
        print(f"  Candidates: {len(candidates)}")
        _print_items(candidates, "candidates")
    except Exception as e:
        print(f"  ✗ Pass 1 failed: {e}")
        return

    if not candidates:
        print("  No candidates extracted — check confidence threshold")
        return

    _print_section(f"Pass 2 — Contrastive Validation ({config.OLLAMA_VALIDATION_MODEL})")
    t0 = time.time()
    try:
        validated = llm._validate_invariants_pass2(candidates, SAMPLE_TRANSCRIPT)
        t1 = time.time()
        print(f"  Time: {t1 - t0:.1f}s")
        print(f"  Validated: {len(validated)} / {len(candidates)} candidates")
        _print_items(validated, "validated invariants")

        # Show what was filtered
        if len(validated) < len(candidates):
            print(f"\n  Filtered out {len(candidates) - len(validated)} invariant(s):")
            val_contexts = {v.get("context", "") for v in validated}
            for c in candidates:
                if c.get("context", "") not in val_contexts:
                    print(f"    ✗ {c.get('context', '?')}: {c.get('enforce', '?')}")
    except Exception as e:
        print(f"  ✗ Pass 2 failed: {e}")
        print("  Falling back to pass 1 candidates with reduced confidence")
        validated = candidates

    # Show final whisper rendering
    _print_section("Final Whisper Output")
    print("  <subconscious_whisper>")
    for inv in validated[:config.INVARIANT_MAX_PER_SESSION]:
        ctx = inv.get("context", "?")
        enf = inv.get("enforce", "?")
        avd = inv.get("avoid", "?")
        print(f"  - [invariant] When {ctx}: enforce {enf}; avoid {avd}")
    for c in standard.get("corrections", [])[:2]:
        print(f"  - [correction] {c.get('text', '?')}")
    for d in standard.get("decisions", [])[:2]:
        print(f"  - [decision] {d.get('text', '?')}")
    print("  </subconscious_whisper>")

    print(f"\n{'═' * 70}")
    print("  LIVE TEST COMPLETE")
    print(f"{'═' * 70}\n")


def test_transcript(path: str):
    """Test extraction on a real transcript file."""
    _print_section(f"TRANSCRIPT TEST — {path}")
    messages, transcript, _ = _parse_transcript_file(path)
    if not transcript:
        print(f"  ✗ Could not read transcript from {path}")
        return

    print(f"  Messages: {len(messages)}")
    print(f"  Transcript length: {len(transcript)} chars")

    # Run full extraction
    _print_section("Full Extraction (standard + invariants)")
    t0 = time.time()
    result = llm.extract_session(transcript, messages)
    t1 = time.time()
    print(f"  Total time: {t1 - t0:.1f}s")
    print("\n  Corrections:")
    _print_items(result.get("corrections", []), "corrections")
    print("\n  Decisions:")
    _print_items(result.get("decisions", []), "decisions")
    print("\n  Invariants:")
    _print_items(result.get("invariants", []), "invariants")


def _parse_transcript_file(path: str):
    """Parse a JSONL transcript file."""
    messages = []
    lines_text = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = entry.get("type", "unknown")
                content = entry.get("message") or entry.get("content") or ""
                if isinstance(content, dict):
                    content = content.get("text", str(content))
                messages.append({"role": role, "content": str(content)})
                lines_text.append(f"[{role}] {content}")
    except (FileNotFoundError, OSError):
        return [], "", 0
    return messages, "\n".join(lines_text), 0


def show_guidance():
    """Show current guidance.json with invariants highlighted."""
    _print_section("Current Guidance")
    guidance = state.read_guidance()
    items = guidance.get("items", [])

    invariants = [i for i in items if i.get("type") == "invariant"]
    corrections = [i for i in items if i.get("type") == "correction"]
    decisions = [i for i in items if i.get("type") == "decision"]
    pending = [i for i in items if i.get("type") == "pending"]

    print(f"  Total items: {len(items)}")
    print(f"  Invariants: {len(invariants)}  |  Corrections: {len(corrections)}")
    print(f"  Decisions:  {len(decisions)}  |  Pending: {len(pending)}")

    if invariants:
        print("\n  ── Invariants ──")
        _print_items(invariants, "invariants")
    if corrections:
        print("\n  ── Corrections ──")
        _print_items(corrections, "corrections")
    if decisions:
        print("\n  ── Decisions ──")
        _print_items(decisions, "decisions")
    if pending:
        print("\n  ── Pending ──")
        _print_items(pending, "pending")


def main():
    parser = argparse.ArgumentParser(description="Test MemCollab invariant extraction")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Format/logic tests only")
    group.add_argument("--live", action="store_true", help="Live Ollama extraction test")
    group.add_argument("--transcript", type=str, help="Path to a real transcript file")
    group.add_argument("--guidance", action="store_true", help="Show current guidance")
    args = parser.parse_args()

    if args.dry_run:
        test_dry_run()
    elif args.live:
        test_live()
    elif args.transcript:
        test_transcript(args.transcript)
    elif args.guidance:
        show_guidance()


if __name__ == "__main__":
    main()
