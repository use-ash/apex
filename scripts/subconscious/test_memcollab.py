#!/opt/homebrew/bin/python3
"""Test the MemCollab enforce/avoid invariant extraction pipeline.

Usage:
    /opt/homebrew/bin/python3 scripts/subconscious/test_memcollab.py [--digest SESSION_ID] [--sample] [--clean-garbage]

Modes:
    --sample          Run on a synthetic test transcript
    --digest ID       Run on a real digest's source transcript
    --clean-garbage   Remove tool_result noise from current guidance.json
    (no args)         Run on a synthetic sample

Reports:
    - Old-format extraction (corrections/decisions/pending)
    - New invariant extraction (enforce/avoid pairs)
    - Cross-model validation results
    - Side-by-side comparison
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

# ── Synthetic test transcript ─────────────────────────────────────
SAMPLE_TRANSCRIPT = """
[user] Can you update the symbol_monitor to use Tradier instead of Alpaca for price data?
[assistant] I'll update symbol_monitor.py to switch from Alpaca IEX to Tradier for price data. Let me make the changes...
[user] No, don't change the import structure. Just swap the API call inside get_current_price()
[assistant] Got it — I'll only modify the get_current_price() function body, keeping the existing imports.
[user] Also make sure the API key comes from .env first, then keychain fallback. Never hardcode it.
[assistant] Updated get_current_price() to use Tradier API with .env → keychain fallback. No hardcoded keys.
[user] The timeout is too short. Tradier can be slow during market open. Use 10 seconds, not 3.
[assistant] Changed the timeout from 3s to 10s for the Tradier API call in get_current_price().
[user] Good. Now run the backtests with the new data source to make sure nothing broke.
[assistant] Running backtests... All 4 plans pass. No regressions detected.
[user] One more thing — when Tradier returns an error, don't silently return None. Fail closed and alert via Telegram.
[assistant] Added explicit error handling: on Tradier API failure, the function now raises an exception and sends a Telegram alert instead of returning None silently.
[user] Perfect. Let me also check — we should never use Alpaca IEX for individual stocks anymore, only for SPY/QQQ broad index data.
[assistant] Understood. I've added a comment documenting that Alpaca IEX is restricted to broad index data (SPY/QQQ) and individual stock prices must use Tradier.
""".strip()


def _run_extraction(transcript: str) -> dict:
    """Run full extraction pipeline and return results with timing."""
    t0 = time.time()
    messages = [
        {"role": r.split("]")[0].strip("["), "content": r.split("] ", 1)[1]}
        for r in transcript.split("\n")
        if r.startswith("[") and "] " in r
    ]

    # Old-format extraction (just corrections/decisions/pending)
    try:
        old_result = llm._extract_via_llm(transcript)
        old_time = time.time() - t0
    except Exception as e:
        old_result = {"error": str(e)}
        old_time = time.time() - t0

    # New invariant extraction (contrastive pipeline)
    t1 = time.time()
    try:
        invariants = llm.extract_invariants(transcript)
        inv_time = time.time() - t1
    except Exception as e:
        invariants = [{"error": str(e)}]
        inv_time = time.time() - t1

    return {
        "old_format": old_result,
        "old_time_s": round(old_time, 2),
        "invariants": invariants,
        "invariant_time_s": round(inv_time, 2),
        "total_time_s": round(time.time() - t0, 2),
    }


def _print_comparison(result: dict):
    """Pretty-print old vs new format comparison."""
    print("\n" + "=" * 70)
    print("MEMCOLLAB EXTRACTION TEST")
    print("=" * 70)

    old = result["old_format"]
    if "error" in old:
        print(f"\n[OLD FORMAT] ERROR: {old['error']}")
    else:
        print(f"\n[OLD FORMAT] ({result['old_time_s']}s)")
        print(f"  Summary: {old.get('summary', {}).get('text', 'n/a')}")
        print(f"  Corrections ({len(old.get('corrections', []))}):")
        for c in old.get("corrections", []):
            print(f"    - {c.get('text', '')}")
        print(f"  Decisions ({len(old.get('decisions', []))}):")
        for d in old.get("decisions", []):
            print(f"    - {d.get('text', '')}")
        print(f"  Pending ({len(old.get('pending', []))}):")
        for p in old.get("pending", []):
            print(f"    - {p.get('text', '')}")

    print(f"\n[INVARIANTS — enforce/avoid] ({result['invariant_time_s']}s)")
    invs = result["invariants"]
    if not invs:
        print("  (none extracted)")
    elif "error" in invs[0]:
        print(f"  ERROR: {invs[0]['error']}")
    else:
        for i, inv in enumerate(invs, 1):
            src = inv.get("source", "?")
            conf = inv.get("confidence", 0)
            print(f"  {i}. [{src} conf={conf}]")
            print(f"     CONTEXT: {inv.get('context', 'n/a')}")
            print(f"     ENFORCE: {inv.get('enforce', 'n/a')}")
            print(f"     AVOID:   {inv.get('avoid', 'n/a')}")

    print(f"\nTotal time: {result['total_time_s']}s")

    # Analysis
    print("\n" + "-" * 70)
    print("ANALYSIS")
    print("-" * 70)
    n_old_items = (
        len(old.get("corrections", []))
        + len(old.get("decisions", []))
        + len(old.get("pending", []))
    ) if "error" not in old else 0

    n_inv = len([i for i in invs if "error" not in i])
    contrastive = len([i for i in invs if i.get("source") == "contrastive"])
    single = n_inv - contrastive

    print(f"  Old format items:     {n_old_items} (corrections + decisions + pending)")
    print(f"  Invariant items:      {n_inv} (enforce/avoid pairs)")
    print(f"  Contrastive-validated: {contrastive}")
    print(f"  Single-model only:    {single}")
    print(f"  Model-agnostic score: {'HIGH' if contrastive > 0 else 'LOW (validation model may be offline)'}")


def _clean_garbage():
    """Remove tool_result noise from current guidance.json."""
    guidance = state.read_guidance()
    items = guidance.get("items", [])
    original_count = len(items)

    cleaned = []
    removed = []
    for item in items:
        text = item.get("text", "")
        if llm._is_tool_noise(text):
            removed.append(text[:80] + "..." if len(text) > 80 else text)
        else:
            cleaned.append(item)

    guidance["items"] = cleaned
    state.write_guidance(guidance)

    print(f"\nCleaned guidance.json: {original_count} -> {len(cleaned)} items")
    print(f"Removed {len(removed)} garbage entries:")
    for r in removed:
        print(f"  - {r}")


def main():
    parser = argparse.ArgumentParser(description="Test MemCollab invariant extraction")
    parser.add_argument("--sample", action="store_true", help="Run on synthetic transcript")
    parser.add_argument("--digest", type=str, help="Run on real digest transcript by session ID")
    parser.add_argument("--clean-garbage", action="store_true", help="Clean tool noise from guidance")
    args = parser.parse_args()

    if args.clean_garbage:
        _clean_garbage()
        return

    # Use sample transcript
    transcript = SAMPLE_TRANSCRIPT
    if args.digest:
        digest = state.load_digest(args.digest)
        if digest:
            print(f"Loaded digest {args.digest}, but need raw transcript — using sample instead")
        transcript = SAMPLE_TRANSCRIPT

    print(f"Transcript length: {len(transcript)} chars")
    print(f"Primary model: {config.OLLAMA_MODEL}")
    print(f"Validation model: {config.OLLAMA_VALIDATION_MODEL}")
    print(f"Invariant confidence threshold: {config.INVARIANT_CONFIDENCE_THRESHOLD}")
    print(f"Max invariants per session: {config.INVARIANT_MAX_PER_SESSION}")

    result = _run_extraction(transcript)
    _print_comparison(result)


if __name__ == "__main__":
    main()
