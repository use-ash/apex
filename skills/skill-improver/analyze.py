#!/usr/bin/env python3
"""Skill Improver — analyze metrics + feedback for a skill and produce a structured report.

Usage:
    python3 analyze.py <skill_name> [--days 30] [--workspace /path/to/workspace]

Output: JSON report to stdout (consumed by Claude for synthesis).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _workspace() -> Path:
    return Path(os.environ.get("APEX_WORKSPACE", os.getcwd()))

def _skill_dir(skill_name: str, workspace: Path | None = None) -> Path:
    ws = workspace or _workspace()
    return ws / "skills" / skill_name


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_metrics(skill_dir: Path, days: int = 30) -> list[dict]:
    """Load metrics.json and filter to recent entries."""
    mf = skill_dir / "metrics.json"
    if not mf.exists():
        return []
    try:
        data = json.loads(mf.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for entry in data:
        ts_raw = entry.get("ts") or entry.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(entry)
        except (ValueError, AttributeError):
            recent.append(entry)  # include entries without valid timestamps
    return recent


def load_feedback(skill_dir: Path, days: int = 30) -> list[str]:
    """Load feedback.log entries from the last N days."""
    ff = skill_dir / "feedback.log"
    if not ff.exists():
        return []
    lines = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for line in ff.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        # Try to parse timestamp from beginning of line (ISO format)
        try:
            ts_str = line[:25]  # typical ISO timestamp length
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts >= cutoff:
                lines.append(line)
        except (ValueError, IndexError):
            lines.append(line)  # include lines without parseable timestamps
    return lines


def load_skill_md(skill_dir: Path) -> str:
    """Load SKILL.md content."""
    sf = skill_dir / "SKILL.md"
    return sf.read_text()[:4000] if sf.exists() else ""


def load_changelog(skill_dir: Path) -> str:
    """Load changelog.md content (last 2000 chars)."""
    cf = skill_dir / "changelog.md"
    if not cf.exists():
        return ""
    text = cf.read_text()
    return text[-2000:] if len(text) > 2000 else text


def load_scripts(skill_dir: Path) -> dict[str, str]:
    """Load run scripts and helper files (first 3000 chars each)."""
    scripts = {}
    for ext in ("*.sh", "*.py"):
        for f in skill_dir.glob(ext):
            if f.name == "analyze.py":
                continue  # skip ourselves
            text = f.read_text()
            scripts[f.name] = text[:3000]
    return scripts


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_metrics(entries: list[dict]) -> dict:
    """Compute metrics summary from invocation entries."""
    if not entries:
        return {
            "total": 0,
            "success_rate": None,
            "avg_duration": None,
            "p50_duration": None,
            "p90_duration": None,
            "error_patterns": [],
            "sources": {},
            "daily_counts": {},
        }

    total = len(entries)
    successes = sum(1 for e in entries if e.get("success"))
    success_rate = round(successes / total * 100, 1) if total else 0

    durations = [e["duration_sec"] for e in entries if isinstance(e.get("duration_sec"), (int, float))]
    avg_dur = round(mean(durations), 2) if durations else None
    p50_dur = round(median(durations), 2) if durations else None
    p90_dur = round(sorted(durations)[int(len(durations) * 0.9)] if durations else 0, 2) if durations else None

    # Error pattern analysis
    errors = [e.get("error", "") for e in entries if not e.get("success") and e.get("error")]
    error_counter = Counter()
    for err in errors:
        # Normalize errors: strip numbers, paths, UUIDs for grouping
        normalized = err[:80]  # truncate for grouping
        error_counter[normalized] += 1
    error_patterns = [
        {"message": msg, "count": count, "pct": round(count / total * 100, 1)}
        for msg, count in error_counter.most_common(10)
    ]

    # Source breakdown
    sources = Counter(e.get("source", "unknown") for e in entries)

    # Daily invocation counts (for trend detection)
    daily: dict[str, int] = {}
    for e in entries:
        ts_raw = e.get("ts") or e.get("timestamp") or ""
        try:
            day = ts_raw[:10]  # YYYY-MM-DD
            if len(day) == 10:
                daily[day] = daily.get(day, 0) + 1
        except (ValueError, IndexError):
            pass

    return {
        "total": total,
        "success_rate": success_rate,
        "successes": successes,
        "failures": total - successes,
        "avg_duration": avg_dur,
        "p50_duration": p50_dur,
        "p90_duration": p90_dur,
        "error_patterns": error_patterns,
        "sources": dict(sources),
        "daily_counts": dict(sorted(daily.items())),
    }


def detect_issues(metrics_summary: dict, feedback: list[str]) -> list[dict]:
    """Auto-detect common issues from metrics and feedback."""
    issues = []

    # Low success rate
    sr = metrics_summary.get("success_rate")
    if sr is not None and sr < 80:
        issues.append({
            "type": "low_success_rate",
            "severity": "high" if sr < 60 else "medium",
            "detail": f"Success rate is {sr}% ({metrics_summary['failures']} failures out of {metrics_summary['total']} invocations)",
        })

    # Timeout pattern
    timeout_errors = [e for e in metrics_summary.get("error_patterns", []) if "timeout" in e["message"].lower()]
    if timeout_errors:
        total_timeouts = sum(e["count"] for e in timeout_errors)
        issues.append({
            "type": "timeout_pattern",
            "severity": "high" if total_timeouts > 5 else "medium",
            "detail": f"{total_timeouts} timeout errors detected",
        })

    # Slow performance
    p90 = metrics_summary.get("p90_duration")
    if p90 is not None and p90 > 5.0:
        issues.append({
            "type": "slow_performance",
            "severity": "medium",
            "detail": f"p90 duration is {p90}s (>5s threshold)",
        })

    # Dominant error pattern (single error >30% of failures)
    for ep in metrics_summary.get("error_patterns", []):
        if ep["count"] >= 3 and ep["pct"] > 15:
            issues.append({
                "type": "recurring_error",
                "severity": "high" if ep["pct"] > 30 else "medium",
                "detail": f"Error '{ep['message'][:60]}' occurs {ep['count']} times ({ep['pct']}% of all invocations)",
            })

    # Feedback volume (many corrections suggest a systemic issue)
    if len(feedback) > 5:
        issues.append({
            "type": "high_feedback_volume",
            "severity": "medium",
            "detail": f"{len(feedback)} feedback entries — indicates user friction",
        })

    # Declining usage (if daily counts show downward trend)
    daily = metrics_summary.get("daily_counts", {})
    if len(daily) >= 7:
        days_sorted = sorted(daily.items())
        first_half = [v for _, v in days_sorted[:len(days_sorted)//2]]
        second_half = [v for _, v in days_sorted[len(days_sorted)//2:]]
        if first_half and second_half:
            first_avg = mean(first_half)
            second_avg = mean(second_half)
            if first_avg > 0 and second_avg / first_avg < 0.5:
                issues.append({
                    "type": "declining_usage",
                    "severity": "low",
                    "detail": f"Usage dropped from avg {first_avg:.1f}/day to {second_avg:.1f}/day",
                })

    return issues


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(skill_name: str, workspace: Path | None = None, days: int = 30) -> dict:
    """Build the full improvement analysis report."""
    ws = workspace or _workspace()
    sd = _skill_dir(skill_name, ws)

    if not sd.exists():
        return {"error": f"Skill '{skill_name}' not found at {sd}"}

    metrics = load_metrics(sd, days)
    feedback = load_feedback(sd, days)
    skill_md = load_skill_md(sd)
    changelog = load_changelog(sd)
    scripts = load_scripts(sd)
    metrics_summary = analyze_metrics(metrics)
    issues = detect_issues(metrics_summary, feedback)

    return {
        "skill": skill_name,
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "skill_dir": str(sd),
        "metrics_summary": metrics_summary,
        "feedback": feedback[-20:],  # last 20 entries
        "feedback_total": len(feedback),
        "detected_issues": issues,
        "current_skill_md": skill_md,
        "changelog": changelog,
        "scripts": scripts,
        "files_present": sorted(f.name for f in sd.iterdir() if f.is_file()),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze skill metrics and propose improvements")
    parser.add_argument("skill", help="Skill name to analyze (e.g., recall, codex, grok)")
    parser.add_argument("--days", type=int, default=30, help="Analysis window in days (default: 30)")
    parser.add_argument("--workspace", type=str, default=None, help="Workspace path override")
    args = parser.parse_args()

    ws = Path(args.workspace) if args.workspace else None
    report = build_report(args.skill, ws, args.days)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
