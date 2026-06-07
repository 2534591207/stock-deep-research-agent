#!/usr/bin/env bash
# check-marker-blocks.sh — Validates HARNESS marker block integrity in AGENTS.md / CLAUDE.md.
# Exit codes: 0=all blocks valid (warnings printed for hash drift), 1=structural violation found
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"
MANIFEST="$HARNESS_DIR/manifest.yaml"

# Portable SHA-256 helper
sha256_file() {
  if command -v shasum &>/dev/null; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum &>/dev/null; then
    sha256sum "$1" | awk '{print $1}'
  else
    echo "ERROR: neither shasum nor sha256sum found" >&2
    exit 1
  fi
}

# Compute SHA-256 of the managed region between markers in a file
sha256_region() {
  local file="$1"
  awk '/<!-- HARNESS:START/{found=1; next} /<!-- HARNESS:END -->/{found=0} found{print}' "$file" | \
    if command -v shasum &>/dev/null; then
      shasum -a 256 | awk '{print $1}'
    else
      sha256sum | awk '{print $1}'
    fi
}

errors=0
managed_files=("AGENTS.md" "CLAUDE.md")

for managed_file in "${managed_files[@]}"; do
  [[ -f "$managed_file" ]] || continue

  # Count START markers
  start_count=$(grep -c '<!-- HARNESS:START' "$managed_file" || true)
  end_count=$(grep -c '<!-- HARNESS:END -->' "$managed_file" || true)

  if [[ "$start_count" -eq 0 && "$end_count" -eq 0 ]]; then
    # File exists but has no markers — skip (not yet managed)
    continue
  fi

  if [[ "$start_count" -ne 1 ]]; then
    echo "FAIL [$managed_file]: expected exactly 1 HARNESS:START marker, found $start_count"
    errors=$((errors + 1))
    continue
  fi

  if [[ "$end_count" -ne 1 ]]; then
    echo "FAIL [$managed_file]: expected exactly 1 HARNESS:END marker, found $end_count"
    errors=$((errors + 1))
    continue
  fi

  # Check for nested markers (START appearing again before END)
  nested=$(awk '
    /<!-- HARNESS:START/{if(inside){nested++} inside=1; next}
    /<!-- HARNESS:END -->/{inside=0; next}
    END{print nested+0}
  ' "$managed_file")
  if [[ "$nested" -gt 0 ]]; then
    echo "FAIL [$managed_file]: nested HARNESS marker blocks detected"
    errors=$((errors + 1))
    continue
  fi

  # Verify START comes before END
  start_line=$(grep -n '<!-- HARNESS:START' "$managed_file" | head -1 | cut -d: -f1)
  end_line=$(grep -n '<!-- HARNESS:END -->' "$managed_file" | head -1 | cut -d: -f1)
  if [[ "$start_line" -ge "$end_line" ]]; then
    echo "FAIL [$managed_file]: HARNESS:START (line $start_line) must precede HARNESS:END (line $end_line)"
    errors=$((errors + 1))
    continue
  fi

  echo "PASS [$managed_file]: marker block structure valid (lines $start_line-$end_line)"

  # Hash drift check (advisory)
  if [[ -f "$MANIFEST" ]] && command -v yq &>/dev/null; then
    manifest_hash=$(yq ".marker_hashes[\"$managed_file\"]" "$MANIFEST" 2>/dev/null || echo "")
    if [[ -n "$manifest_hash" && "$manifest_hash" != "null" ]]; then
      current_hash=$(sha256_region "$managed_file")
      if [[ "$current_hash" != "$manifest_hash" ]]; then
        echo "WARN [$managed_file]: managed region hash drifted. Expected=$manifest_hash Current=$current_hash. Run init-harness --force to reconcile."
      fi
    fi
  fi
done

if [[ $errors -gt 0 ]]; then
  echo ""
  echo "Marker block check FAILED: $errors structural violation(s)"
  exit 1
fi

echo "Marker block check PASSED"
exit 0
