#!/usr/bin/env bash
# check-placeholders.sh — Detects unsubstituted double-curly template placeholders in .harness/.
# Exit codes: 0=no placeholders found (clean), 1=placeholders found (skill failed to substitute)
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"

if [[ ! -d "$HARNESS_DIR" ]]; then
  echo "ERROR: $HARNESS_DIR directory not found" >&2
  exit 1
fi

# grep returns 1 when no match (which is success for us), 0 when match found (failure)
PATTERN='{''{'
if grep -rn --exclude='check-placeholders.sh' "$PATTERN" "$HARNESS_DIR/" 2>/dev/null; then
  echo ""
  echo "FAIL: Unsubstituted placeholders found in $HARNESS_DIR. The init-harness skill must substitute all double-curly template tokens."
  exit 1
fi

echo "PASS: No unsubstituted placeholders found in $HARNESS_DIR"
exit 0
