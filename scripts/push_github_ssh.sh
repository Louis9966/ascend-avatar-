#!/bin/bash
# Push ascend-avatar source to GitHub via SSH key.
# Usage: bash /data/ascend-avatar/scripts/push_github_ssh.sh

set -e

KEY="/data/ascend-avatar/.ssh/ascend_avatar_push"
REPO_URL="git@github.com:Louis9966/ascend-avatar-.git"

cd /data/ascend-avatar

if [ ! -f "$KEY" ]; then
    echo "ERROR: SSH key not found at $KEY"
    echo "Please generate it first: ssh-keygen -t ed25519 -f $KEY -N \"\""
    exit 1
fi

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

# Use the dedicated SSH key for this push
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

# Add remote and push
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
git branch -M main
git push -u origin main

echo "Push complete."
