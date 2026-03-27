#!/usr/bin/env python3
"""Weekly skill health scan — identify skills that need improvement.

Scans all skills with metrics, flags those with:
  - >10 invocations in the analysis window AND <80% success rate
  - Any skill with >5 timeout errors
  - Any skill with declining usage trend

Usage:
    python3 scan_skills.py [--days 30] [--workspace /path] [--auto-improve]

With --auto-improve, automatically runs analyze.py on flagged skills and
writes reports to skills/skill-improver/reports/<skill>_<date>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import analyze.py from same directory
sys.path.insert(0, str(Path(__file__).parent))
from analyze import build_report, analyze_metrics, load_metrics, detect_issues, load_feedback


def _workspace() -> Path:
    return Path(os.environ.get("LOCALCHAT_WORKSPACE", os.getcwd()))


def scan_all_skills(workspace: Path | None = None, days: int = 30) -> list[dict]:
    """Scan all skills and return health summary for each."""
    ws = workspace or _workspace()
    skills_dir = ws / "skills"
    if not skills_dir.exists():
        return []

    results = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in ("lib", "skill-improver"):
            continue
        if not (skill_dir / "SKILL.md").exists():
            continue

        metrics = load_metrics(skill_dir, days)
        if not metrics:
            results.append({
                "skill": skill_dir.name,
                "total": 0,
                "success_rate": None,
                "flagged": False,
                "reasons": ["no_metrics"],
            })
            continue

        summary = analyze_metrics(metrics)
        feedback = load_feedback(skill_dir, days)
        issues = detect_issues(summary, feedback)

        flagged = False
        flag_reasons = []

        # Flag: >10 invocations AND <80% success rate
        if summary["total"] >= 10 and summary["success_rate"] is not None and summary["success_rate"] < 80:
            flagged = True
            flag_reasons.append(f"low_success_rate:{summary['success_rate']}%")

        # Flag: >5 timeout errors
        timeout_count = sum(
            e["count"] for e in summary.get("error_patterns", [])
            if "timeout" in e["message"].lower()
        )
        if timeout_count > 5:
            flagged = True
            flag_reasons.append(f"timeouts:{timeout_count}")

        # Flag: any high-severity issues detected
        high_issues = [i for i in issues if i.get("severity") == "high"]
        if high_issues:
            flagged = True
            for issue in high_issues:
                flag_reasons.append(f"{issue['type']}")

        results.append({
            "skill": skill_dir.name,
            "total": summary["total"],
            "success_rate": summary["success_rate"],
            "avg_duration": summary["avg_duration"],
            "failures": summary["failures"],
            "issues": len(issues),
            "flagged": flagged,
            "reasons": flag_reasons,
        })

    return results


def run_auto_improve(flagged_skills: list[str], workspace: Path | None = None, days: int = 30) -> list[str]:
    """Run analyze.py on flagged skills and save reports."""
    ws = workspace or _workspace()
    reports_dir = ws / "skills" / "skill-improver" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for skill in flagged_skills:
        report = build_report(skill, ws, days)
        if "error" in report:
            continue

        outfile = reports_dir / f"{skill}_{date_str}.json"
        outfile.write_text(json.dumps(report, indent=2, default=str))
        saved.append(str(outfile))

    return saved


def main():
    parser = argparse.ArgumentParser(description="Weekly skill health scan")
    parser.add_argument("--days", type=int, default=30, help="Analysis window in days")
    parser.add_argument("--workspace", default=None, help="Workspace path override")
    parser.add_argument("--auto-improve", action="store_true", help="Auto-run analysis on flagged skills")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of table")
    args = parser.parse_args()

    ws = Path(args.workspace) if args.workspace else None
    results = scan_all_skills(ws, args.days)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Pretty-print table
    flagged = [r for r in results if r.get("flagged")]
    healthy = [r for r in results if not r.get("flagged") and r.get("total", 0) > 0]
    inactive = [r for r in results if r.get("total", 0) == 0]

    print(f"Skill Health Scan — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Window: {args.days} days | Skills scanned: {len(results)}")
    print()

    if flagged:
        print(f"🔴 FLAGGED ({len(flagged)}):")
        for r in flagged:
            reasons = ", ".join(r.get("reasons", []))
            rate = f"{r['success_rate']}%" if r["success_rate"] is not None else "n/a"
            print(f"   {r['skill']:20s}  {r['total']:4d} invocations  {rate:>6s} success  [{reasons}]")
        print()

    if healthy:
        print(f"🟢 HEALTHY ({len(healthy)}):")
        for r in healthy:
            rate = f"{r['success_rate']}%" if r["success_rate"] is not None else "n/a"
            dur = f"{r['avg_duration']:.1f}s" if r.get("avg_duration") else "n/a"
            print(f"   {r['skill']:20s}  {r['total']:4d} invocations  {rate:>6s} success  {dur:>6s} avg")
        print()

    if inactive:
        print(f"⚪ NO DATA ({len(inactive)}):")
        for r in inactive:
            print(f"   {r['skill']}")
        print()

    if args.auto_improve and flagged:
        print("Running auto-improvement analysis on flagged skills...")
        flagged_names = [r["skill"] for r in flagged]
        saved = run_auto_improve(flagged_names, ws, args.days)
        for path in saved:
            print(f"   📄 {path}")
        print(f"\nDone. {len(saved)} reports generated.")
        print("Review with: /improve <skill_name>")
    elif flagged:
        print("Run with --auto-improve to generate reports, or:")
        for r in flagged:
            print(f"   /improve {r['skill']}")


if __name__ == "__main__":
    main()
