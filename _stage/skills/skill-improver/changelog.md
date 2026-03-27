# skill-improver changelog

## v1.1 — 2026-03-25
- Added submit_proposal.py: gate integration for risk-tiered approval of improvements
  - Tier 1 (SKILL.md changes) auto-approved
  - Tier 2+ writes pending approval to gate, requires /approve
- Added scan_skills.py: weekly health scan across all skills
  - Flags skills with >10 invocations and <80% success rate
  - Flags skills with >5 timeouts or high-severity issues
  - --auto-improve flag generates reports for flagged skills
  - Pretty-printed table output + --json mode
- Updated SKILL.md with implementation flow (gate submission instructions for Claude)

## v1.0 — 2026-03-25
- Initial implementation
- analyze.py: reads metrics.json + feedback.log, computes success rate, error patterns, duration stats
- Auto-detects: low success rate, timeout patterns, slow performance, recurring errors, high feedback volume, declining usage
- Structured JSON output for Claude synthesis
- Server dispatch as context skill: /improve <skill_name>
- SKILL.md: thinking-skill instructions for Claude to produce actionable proposals
- Gate-aware: proposals tagged by risk tier (SKILL.md changes = tier 1, script changes = tier 2, new deps = tier 3)
