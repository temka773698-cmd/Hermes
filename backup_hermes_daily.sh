#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/art/hermes-daily-github-backup"
EXPORT_DIR="$REPO_DIR/exports"
STAMP="$(date +%F_%H-%M-%S)"

mkdir -p "$EXPORT_DIR"
cd "$REPO_DIR"

# Export canonical Hermes session DB to JSONL. This is the most useful "what we did" archive.
hermes sessions export "$EXPORT_DIR/hermes-sessions-$STAMP.jsonl"

# Add lightweight metadata for orientation.
{
  echo "# Hermes daily backup"
  echo ""
  echo "Updated: $(date -Is)"
  echo "Host: $(hostname)"
  echo "Export: exports/hermes-sessions-$STAMP.jsonl"
} > README.md

# Keep a rolling pointer to latest export name without duplicating the large JSONL.
printf '%s\n' "exports/hermes-sessions-$STAMP.jsonl" > latest.txt

# Avoid commits with no changes.
git add README.md latest.txt exports/
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

git commit -m "chore: daily Hermes backup $STAMP"

# Push if remote is configured; otherwise leave the commit local.
if git remote get-url origin >/dev/null 2>&1; then
  git push origin main
else
  echo "No git remote 'origin' configured; commit saved locally only."
fi
