#!/usr/bin/env bash
# check-dry-run-purity.sh — Asserts git working tree is clean (zero filesystem changes).
# Used to verify --dry-run produced no side effects.
# Exit codes: 0=clean (or not a git repo — advisory), 1=uncommitted changes found
set -euo pipefail

if ! git rev-parse --git-dir &>/dev/null 2>&1; then
  echo "NOTE: Not inside a git working tree. Dry-run purity check skipped (advisory)."
  exit 0
fi

dirty=$(git status --porcelain 2>/dev/null || true)

if [[ -n "$dirty" ]]; then
  echo "FAIL: Working tree has uncommitted changes after --dry-run:"
  echo "$dirty"
  exit 1
fi

echo "PASS: Working tree is clean — no filesystem changes detected"
exit 0
