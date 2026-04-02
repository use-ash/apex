---
name: skill-improver
description: Meta-skill that analyzes skill metrics and feedback, then proposes concrete improvements
type: thinking
tier: 2
gate: true
---

# Skill Improver

You are analyzing a skill's performance data to propose concrete improvements.

## Context

You have been given a structured analysis report from `analyze.py` containing:
- **Metrics summary**: invocation count, success rate, error patterns, performance stats
- **Feedback log**: user corrections, complaints, and suggestions
- **Current implementation**: the skill's SKILL.md and changelog
- **Pattern analysis**: automatically detected issues

## Your Task

1. **Diagnose** — Identify the top 1-3 issues hurting this skill's effectiveness. Prioritize by impact (frequency × severity). Look for:
   - Recurring error patterns (same error message appearing >3 times)
   - Low success rate (<80%) or declining trend
   - Slow performance (p90 duration >5s)
   - User corrections that indicate the skill misunderstands intent
   - Gaps between what users ask for and what the skill delivers

2. **Propose** — For each issue, write a concrete improvement proposal:
   - **What to change**: specific file(s) and the nature of the change
   - **Why**: connect it to the data (e.g., "23% of errors are timeout — increasing timeout or adding retry would fix")
   - **Diff**: if the fix is small, show the actual diff. If structural, describe the approach.
   - **Risk**: low/medium/high — will this break existing behavior?

3. **Prioritize** — Rank proposals by expected impact. A fix that addresses 40% of failures beats one that addresses 5%.

## Output Format

Present your analysis as:

```
## Skill Health: {skill_name}

### Metrics Snapshot
- Invocations: {n} (last 30 days)
- Success rate: {rate}%
- Avg duration: {dur}s
- Top errors: {list}

### Issues Found

#### 1. {Issue title} (Priority: HIGH/MEDIUM/LOW)
**Evidence:** {data points from metrics/feedback}
**Proposed fix:** {description}
**Files:** {file list}
**Risk:** {low/medium/high}

{diff or pseudocode if applicable}

### Recommendation
{1-2 sentence summary of what to do first}
```

## Implementation Flow

When the user says "implement" or approves a proposal:

1. **Classify the tier** based on what files are changing:
   - Tier 1: SKILL.md-only changes → implement directly after confirmation
   - Tier 2: Script/code changes (run.sh, .py, .sh) → submit to gate first
   - Tier 3: New dependencies, external API calls, new subprocesses → submit to gate + require testing

2. **For tier 2+**, submit through the gate before making changes:
   ```
   python3 skills/skill-improver/submit_proposal.py <skill> <tier> "<title>" --reason "<reason>" --details "<diff summary>"
   ```
   Then tell the user: "Submitted for approval. Use `/approve <id>` to proceed."

3. **After approval** (or for tier 1), make the changes and update the skill's changelog.md.

4. **Log the improvement** to skills/skill-improver/metrics.json via the standard metrics system.

## Gate Rules

- Proposals that modify `SKILL.md` only → **tier 1** (auto-approved after review)
- Proposals that modify `run.sh`, main scripts, or helper `.py` files → **tier 2** (requires explicit `/approve`)
- Proposals that add new dependencies, external calls, or new subprocesses → **tier 3** (requires review + testing plan)
