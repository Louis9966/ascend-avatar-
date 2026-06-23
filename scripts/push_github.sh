#!/bin/bash
# Push ascend-avatar source to GitHub.
# Usage: GH_TOKEN=ghp_xxxx bash /data/ascend-avatar/scripts/push_github.sh

set -e

if [ -z "$GH_TOKEN" ]; then
    echo "ERROR: set GH_TOKEN environment variable with your GitHub personal access token."
    exit 1
fi

REPO_URL="https://github.com/Louis9966/ascend-avatar-.git"
CREDS_FILE="/tmp/.ascend-avatar-git-creds"

cd /data/ascend-avatar

# Initialize repository if needed
if [ ! -d .git ]; then
    git init
fi

git config user.email "noreply@example.com" || true
git config user.name "ascend-avatar" || true

# Stage code, docs, config, loop, frontend, etc. (respects .gitignore)
git add .

# Commit (allow empty message guard)
if git diff --cached --quiet; then
    echo "Nothing to commit."
else
    git commit -m "Initial commit: ascend-avatar Phase 8 (PaddleSpeech TTS + video gen)" || true
fi

# Store credentials temporarily
echo "https://Louis9966:${GH_TOKEN}@github.com" > "$CREDS_FILE"
chmod 600 "$CREDS_FILE"
git config credential.helper "store --file=${CREDS_FILE}"

# Add remote and push
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
git branch -M main
git push -u origin main

# Clean up credentials
rm -f "$CREDS_FILE"
git config --unset credential.helper 2>/dev/null || true

echo "Push complete."
