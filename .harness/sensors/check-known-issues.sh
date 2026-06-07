#!/usr/bin/env bash
# check-known-issues.sh — Parses .harness/known-issues/_registry.yaml for blocking entries.
# Entries with status=touched-must-fix block; open/waived/closed are summarized.
# Exit codes: 0=no blocking issues, 1=touched-must-fix entries found, 2=yq missing
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"
REGISTRY="$HARNESS_DIR/known-issues/_registry.yaml"

if ! command -v yq &>/dev/null; then
  echo "ERROR: yq is required but not installed." >&2
  exit 2
fi

if [[ ! -f "$REGISTRY" ]]; then
  echo "NOTE: No known-issues registry found at $REGISTRY. Skipping."
  exit 0
fi

blocking=0
open_count=0
waived_count=0
closed_count=0

entries_count=$(yq '.issues | length' "$REGISTRY" 2>/dev/null || echo 0)

for i in $(seq 0 $((entries_count - 1))); do
  issue_id=$(yq ".issues[$i].id" "$REGISTRY")
  status=$(yq ".issues[$i].status" "$REGISTRY")
  file_path=$(yq ".issues[$i].file // \"(unknown)\"" "$REGISTRY")
  severity=$(yq ".issues[$i].severity // \"(unknown)\"" "$REGISTRY")
  description=$(yq ".issues[$i].description // \"\"" "$REGISTRY")

  case "$status" in
    touched-must-fix)
      echo "FAIL [$issue_id]: status=touched-must-fix | severity=$severity | file=$file_path"
      echo "     Description: $description"
      echo "     This file was touched and must be fixed before merge."
      blocking=$((blocking + 1))
      ;;
    open)
      open_count=$((open_count + 1))
      ;;
    waived)
      waived_count=$((waived_count + 1))
      ;;
    closed)
      closed_count=$((closed_count + 1))
      ;;
    *)
      echo "WARN [$issue_id]: unknown status '$status'"
      ;;
  esac
done

echo ""
echo "Known-issues summary: $blocking blocking (touched-must-fix), $open_count open, $waived_count waived, $closed_count closed"

if [[ $blocking -gt 0 ]]; then
  echo "FAIL: $blocking blocking known issue(s) must be resolved before proceeding"
  exit 1
fi

echo "PASS: No blocking known issues"
exit 0
