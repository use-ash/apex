#!/bin/bash
# Phase 3 Deploy — skill-improver + usage banner + inline approval
# Run from: ~/.openclaw/apex/
set -e

echo "=== Phase 3 Deploy ==="

# 1. Deploy skill-improver to workspace
echo "→ Deploying skill-improver to workspace..."
mkdir -p ~/.openclaw/workspace/skills/skill-improver
cp _stage/skills/skill-improver/SKILL.md ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/analyze.py ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/submit_proposal.py ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/scan_skills.py ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/changelog.md ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/metrics.json ~/.openclaw/workspace/skills/skill-improver/
cp _stage/skills/skill-improver/feedback.log ~/.openclaw/workspace/skills/skill-improver/
echo "  ✓ 7 files → workspace/skills/skill-improver/"

# 2. Deploy /improve command to workspace
echo "→ Deploying /improve command..."
mkdir -p ~/.openclaw/workspace/.claude/commands
cp _stage/claude-commands/improve.md ~/.openclaw/workspace/.claude/commands/
echo "  ✓ improve.md → workspace/.claude/commands/"

# 3. Git add + commit in apex repo
echo "→ Staging files in apex repo..."
git add \
  server/apex.py \
  ios/ApexChat/ApexChat/Network/APIClient.swift \
  ios/ApexChat/ApexChat/ViewModels/AppState.swift \
  ios/ApexChat/ApexChat/Views/ChatView.swift \
  ios/ApexChat/ApexChat/Views/ContentView.swift \
  ios/ApexChat/ApexChat/Views/MessageBubble.swift \
  ios/ApexChat/ApexChat/Views/UsageBannerView.swift \
  skills/skill-improver/ \
  claude-commands/improve.md

echo "→ Committing..."
git commit -m "$(cat <<'EOF'
feat: Phase 3 — skill-improver meta-skill + usage banner + inline approval

- skill-improver: analyze.py reads metrics.json + feedback.log, detects
  failure patterns, proposes concrete improvements with diffs
- submit_proposal.py: gate integration (tier 1 auto-approve, tier 2+ pending)
- scan_skills.py: weekly health scan, flags >10 invocations + <80% success
- /improve <skill> slash command for manual trigger
- Server: _run_improve() dispatch, usage API, auto-compaction, tool display
- iOS: usage banner, tool call rendering, streaming improvements

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"

# 4. Push
echo "→ Pushing..."
git push

echo ""
echo "=== Deploy complete ==="
echo "Workspace: skill-improver + /improve command deployed"
echo "Apex: committed + pushed"
echo ""
echo "Test with: /improve recall"
