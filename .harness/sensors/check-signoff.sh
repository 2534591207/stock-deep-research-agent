#!/usr/bin/env bash
# check-signoff.sh — For L3 changes, verifies DCO Signed-off-by line in review-packet.md.
# Usage: check-signoff.sh [change-folder-path]
# Exit codes: 0=signoff found, 1=signoff missing or file not found
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"

# Resolve change folder: use arg if provided, else auto-detect most recent
if [[ -n "${1:-}" ]]; then
  change_dir="$1"
else
  # Auto-detect most recent change folder
  changes_dir="$HARNESS_DIR/changes"
  if [[ ! -d "$changes_dir" ]]; then
    echo "FAIL: No changes directory at $changes_dir"
    exit 1
  fi
  # Find most recently modified change directory
  change_dir=$(find "$changes_dir" -mindepth 1 -maxdepth 1 -type d -print0 \
    | xargs -0 ls -td 2>/dev/null | head -1 || true)
  if [[ -z "$change_dir" ]]; then
    echo "FAIL: No change folders found under $changes_dir"
    exit 1
  fi
fi

review_packet="$change_dir/review-packet.md"

if [[ ! -f "$review_packet" ]]; then
  echo "FAIL: review-packet.md not found at $review_packet"
  exit 1
fi

# DCO format: Signed-off-by: Full Name <email@domain.tld>
if grep -qE '^Signed-off-by: .+ <.+@.+>$' "$review_packet"; then
  echo "PASS: DCO Signed-off-by line found in $(basename "$change_dir")/review-packet.md"
  exit 0
else
  echo "FAIL: No valid DCO Signed-off-by line found in $review_packet"
  echo "      Required format: Signed-off-by: Full Name <email@domain.tld>"
  exit 1
fi
