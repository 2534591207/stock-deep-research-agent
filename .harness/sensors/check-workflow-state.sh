#!/usr/bin/env bash
# check-workflow-state.sh — Verifies required artifacts exist for the current change's risk tier.
# Reads .harness/changes/<change-id>/ and validates per playbook artifact requirements.
# Exit codes: 0=all required artifacts present, 1=missing artifacts, 2=no active change found
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"
STATE_FILE="$HARNESS_DIR/state/phase.yaml"

if ! command -v yq &>/dev/null; then
  echo "ERROR: yq is required but not installed." >&2
  exit 1
fi

# Determine current change folder
if [[ ! -f "$STATE_FILE" ]]; then
  echo "NOTE: No state/phase.yaml found. No active change to validate."
  exit 0
fi

current_change=$(yq '.current_change // ""' "$STATE_FILE" 2>/dev/null || echo "")
if [[ -z "$current_change" || "$current_change" == "null" ]]; then
  echo "NOTE: No current_change in state/phase.yaml. Nothing to validate."
  exit 0
fi

change_dir="$HARNESS_DIR/changes/$current_change"
if [[ ! -d "$change_dir" ]]; then
  echo "FAIL: Change directory $change_dir does not exist"
  exit 1
fi

# Read risk tier
tier_file="$change_dir/risk-tier.txt"
if [[ ! -f "$tier_file" ]]; then
  echo "WARN: $tier_file not found; defaulting to L2 artifact check"
  tier="L2"
else
  tier=$(tr -d '[:space:]' < "$tier_file")
fi

echo "Checking artifacts for change '$current_change' at tier $tier"

missing=0

check_artifact() {
  local artifact="$change_dir/$1"
  local label="$1"
  if [[ ! -f "$artifact" ]]; then
    echo "FAIL: Missing artifact: $label"
    missing=$((missing + 1))
  elif [[ ! -s "$artifact" ]]; then
    echo "FAIL: Artifact exists but is empty: $label"
    missing=$((missing + 1))
  else
    echo "PASS: $label"
  fi
}

case "$tier" in
  L0)
    # L0: commit message intent only — no file artifacts required
    echo "PASS: L0 tier requires no file artifacts (commit message only)"
    ;;
  L1)
    check_artifact "bug-reference.txt"
    ;;
  L2)
    check_artifact "PRD.md"
    check_artifact "design.md"
    check_artifact "acceptance-report.md"
    check_artifact "review-packet.md"
    ;;
  L3)
    check_artifact "PRD.md"
    check_artifact "design.md"
    check_artifact "acceptance-report.md"
    check_artifact "review-packet.md"
    check_artifact "risk-assessment.md"
    check_artifact "rollback-plan.md"
    ;;
  *)
    echo "WARN: Unknown tier '$tier', falling back to L2 checks"
    check_artifact "PRD.md"
    check_artifact "design.md"
    check_artifact "acceptance-report.md"
    check_artifact "review-packet.md"
    ;;
esac

if [[ $missing -gt 0 ]]; then
  echo ""
  echo "Workflow state check FAILED: $missing required artifact(s) missing for tier $tier"
  exit 1
fi

echo ""
echo "Workflow state check PASSED for tier $tier"
exit 0
