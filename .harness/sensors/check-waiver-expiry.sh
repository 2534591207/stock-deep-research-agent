#!/usr/bin/env bash
# check-waiver-expiry.sh — Advisory check for expired waivers in feedback/waivers/*.yaml.
# Emits WARN lines for expired entries; never exits non-zero (purely advisory).
# Exit codes: 0 always
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"
WAIVERS_DIR="$HARNESS_DIR/feedback/waivers"

if ! command -v yq &>/dev/null; then
  echo "NOTE: yq not available, skipping waiver expiry check" >&2
  exit 0
fi

if [[ ! -d "$WAIVERS_DIR" ]]; then
  echo "NOTE: No waivers directory at $WAIVERS_DIR. Nothing to check."
  exit 0
fi

today=$(date +%Y-%m-%d)
expired_count=0
checked_count=0

for waiver_file in "$WAIVERS_DIR"/*.yaml; do
  [[ -f "$waiver_file" ]] || continue

  entries_count=$(yq '. | length' "$waiver_file" 2>/dev/null || echo 0)
  # Support both list-at-root and map-with-waivers-key
  if yq '.waivers' "$waiver_file" &>/dev/null 2>&1; then
    entries_count=$(yq '.waivers | length' "$waiver_file" 2>/dev/null || echo 0)
    key_prefix=".waivers"
  else
    entries_count=$(yq '. | length' "$waiver_file" 2>/dev/null || echo 0)
    key_prefix="."
  fi

  for i in $(seq 0 $((entries_count - 1))); do
    rule_id=$(yq "${key_prefix}[$i].rule_id // \"(unknown)\"" "$waiver_file")
    hit_sig=$(yq "${key_prefix}[$i].hit_signature // \"(unknown)\"" "$waiver_file")
    expires_at=$(yq "${key_prefix}[$i].expires_at // \"\"" "$waiver_file")

    [[ -z "$expires_at" || "$expires_at" == "null" ]] && continue
    checked_count=$((checked_count + 1))

    if [[ "$expires_at" < "$today" ]]; then
      echo "WARN: waiver expired $rule_id $hit_sig on $expires_at (today is $today) — file: $(basename "$waiver_file")"
      expired_count=$((expired_count + 1))
    fi
  done
done

echo ""
echo "Waiver expiry check complete: $checked_count waivers checked, $expired_count expired"
exit 0
