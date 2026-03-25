Analyze the skill "$ARGUMENTS" and propose concrete improvements based on its metrics and feedback data.

Run the skill-improver analysis:
```
python3 skills/skill-improver/analyze.py $ARGUMENTS --days 30
```

Then follow the instructions in `skills/skill-improver/SKILL.md` to:

1. Review the analysis report
2. Identify the top issues by impact
3. Propose specific, actionable improvements with diffs where possible
4. Rank by expected impact
5. Present in the structured format defined in SKILL.md

If proposing changes to executable scripts (run.sh, .py files), note that these require gate approval before implementation. SKILL.md-only changes can be applied directly after review.

After presenting the analysis, ask: "Want me to implement any of these improvements?"
