#!/bin/bash
# gh_commit.sh — Commit and push files via GitHub API (no .git write needed)
#
# Designed for sandboxed agents (Codex) that can modify working tree files
# but cannot write to .git. Uses the gh CLI to create commits via the
# GitHub REST API.
#
# Usage:
#   gh_commit.sh <branch> <message> <file1> [file2] [file3] ...
#
# Example:
#   gh_commit.sh dev "fix: patch security issue" server/apex.py server/streaming.py
#
# Requirements:
#   - gh CLI authenticated (gh auth status)
#   - Files must exist in the working tree at the paths specified
#   - Paths are relative to the repo root
#
# Exit codes:
#   0 = success
#   1 = usage error
#   2 = gh API error

set -euo pipefail

REPO="use-ash/apex"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Args ──────────────────────────────────────────────────────────────────────
if [ $# -lt 3 ]; then
    echo "Usage: gh_commit.sh <branch> <message> <file1> [file2...]" >&2
    exit 1
fi

BRANCH="$1"; shift
MESSAGE="$1"; shift
FILES=("$@")

echo "gh_commit: branch=$BRANCH files=${#FILES[@]} repo=$REPO"

# ── 1. Get current HEAD SHA ──────────────────────────────────────────────────
HEAD_SHA=$(gh api "repos/$REPO/git/ref/heads/$BRANCH" --jq '.object.sha' 2>/dev/null)
if [ -z "$HEAD_SHA" ]; then
    echo "Error: could not resolve HEAD for branch '$BRANCH'" >&2
    exit 2
fi
echo "  HEAD: $HEAD_SHA"

# ── 2. Get the base tree SHA ────────────────────────────────────────────────
BASE_TREE=$(gh api "repos/$REPO/git/commits/$HEAD_SHA" --jq '.tree.sha')
echo "  base tree: $BASE_TREE"

# ── 3. Create blobs for each file ───────────────────────────────────────────
TREE_ENTRIES="["
FIRST=true
for FILE in "${FILES[@]}"; do
    FULL_PATH="$REPO_ROOT/$FILE"
    if [ ! -f "$FULL_PATH" ]; then
        echo "Error: file not found: $FULL_PATH" >&2
        exit 1
    fi

    # Create blob via API (base64-encoded content)
    CONTENT_B64=$(base64 < "$FULL_PATH")
    BLOB_SHA=$(gh api "repos/$REPO/git/blobs" \
        -f content="$CONTENT_B64" \
        -f encoding=base64 \
        --jq '.sha')

    if [ -z "$BLOB_SHA" ]; then
        echo "Error: failed to create blob for $FILE" >&2
        exit 2
    fi
    echo "  blob: $FILE -> $BLOB_SHA"

    # Build tree entry JSON
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        TREE_ENTRIES+=","
    fi
    TREE_ENTRIES+="{\"path\":\"$FILE\",\"mode\":\"100644\",\"type\":\"blob\",\"sha\":\"$BLOB_SHA\"}"
done
TREE_ENTRIES+="]"

# ── 4. Create new tree ──────────────────────────────────────────────────────
NEW_TREE=$(echo "{\"base_tree\":\"$BASE_TREE\",\"tree\":$TREE_ENTRIES}" \
    | gh api "repos/$REPO/git/trees" --input - --jq '.sha')

if [ -z "$NEW_TREE" ]; then
    echo "Error: failed to create tree" >&2
    exit 2
fi
echo "  new tree: $NEW_TREE"

# ── 5. Create commit ────────────────────────────────────────────────────────
COMMIT_SHA=$(echo "{\"message\":$(echo "$MESSAGE" | jq -Rs .),\"tree\":\"$NEW_TREE\",\"parents\":[\"$HEAD_SHA\"]}" \
    | gh api "repos/$REPO/git/commits" --input - --jq '.sha')

if [ -z "$COMMIT_SHA" ]; then
    echo "Error: failed to create commit" >&2
    exit 2
fi
echo "  commit: $COMMIT_SHA"

# ── 6. Update branch ref ────────────────────────────────────────────────────
gh api "repos/$REPO/git/refs/heads/$BRANCH" \
    -X PATCH \
    -f sha="$COMMIT_SHA" \
    -F force=false \
    --silent

echo "gh_commit: pushed $COMMIT_SHA to $BRANCH (${#FILES[@]} files)"

# For main-branch pushes, remind the operator that the local clone is NOT
# updated by this script. launch_apex.sh now auto-pulls, so this is belt-
# and-suspenders in case the server is restarted via another path.
if [ "$BRANCH" = "main" ]; then
    echo ""
    echo "  NOTE: API push — local clone is NOT updated."
    echo "  launch_apex.sh auto-pulls on restart, but if you restart via"
    echo "  another method first run:  git -C $(printf '%q' "$REPO_ROOT") pull origin main"
fi
