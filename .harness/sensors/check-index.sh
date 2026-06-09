#!/usr/bin/env bash
# check-index.sh — Schema↔filesystem integrity. Validates _index.md entries against disk.
# Exit codes: 0=all valid, 1=integrity mismatch found, 2=index missing, 3=yq missing
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-.harness}"
INDEX="$HARNESS_DIR/rules/_index.md"

if ! command -v yq &>/dev/null; then
  echo "ERROR: yq is required but not installed." >&2
  echo "  macOS: brew install yq" >&2
  echo "  Linux: see https://github.com/mikefarah/yq" >&2
  exit 3
fi

if [[ ! -f "$INDEX" ]]; then
  echo "ERROR: $INDEX not found." >&2
  exit 2
fi

# Extract YAML from fenced ```yaml block if present; else use whole file.
YAML_TMP=$(mktemp -t harness-index-XXXXXX.yaml)
trap 'rm -f "$YAML_TMP"' EXIT

awk '/^```yaml[[:space:]]*$/{flag=1;next} /^```[[:space:]]*$/{flag=0;next} flag' "$INDEX" > "$YAML_TMP"
if [[ ! -s "$YAML_TMP" ]]; then
  cp "$INDEX" "$YAML_TMP"
fi

errors=0
rules_count=$(yq '.rules | length' "$YAML_TMP" 2>/dev/null || echo 0)

if [[ "$rules_count" -eq 0 || "$rules_count" == "null" ]]; then
  echo "ERROR: $INDEX has no rules[] array or YAML is malformed." >&2
  exit 1
fi

for i in $(seq 0 $((rules_count - 1))); do
  rule_id=$(yq ".rules[$i].id" "$YAML_TMP")
  mode=$(yq ".rules[$i].mechanization" "$YAML_TMP")
  sensor=$(yq ".rules[$i].sensor // \"\"" "$YAML_TMP")
  judge_prompt=$(yq ".rules[$i].judge_prompt // \"\"" "$YAML_TMP")
  applies_at_count=$(yq ".rules[$i].applies_at | length // 0" "$YAML_TMP" 2>/dev/null || echo 0)

  # Normalize "null" string to empty
  [[ "$sensor" == "null" ]] && sensor=""
  [[ "$judge_prompt" == "null" ]] && judge_prompt=""

  case "$mode" in
    grep)
      if [[ -z "$sensor" ]]; then
        echo "ERROR [$rule_id]: mechanization=grep requires sensor path, got null"
        errors=$((errors + 1))
      else
        sensor_path="$HARNESS_DIR/$sensor"
        if [[ ! -f "$sensor_path" ]]; then
          echo "ERROR [$rule_id]: sensor $sensor_path does not exist"
          errors=$((errors + 1))
        elif [[ ! -x "$sensor_path" ]]; then
          echo "ERROR [$rule_id]: sensor $sensor_path exists but is not executable"
          errors=$((errors + 1))
        fi
      fi
      ;;
    grep+judgment)
      if [[ -z "$sensor" ]]; then
        echo "ERROR [$rule_id]: mechanization=grep+judgment requires sensor path, got null"
        errors=$((errors + 1))
      else
        sensor_path="$HARNESS_DIR/$sensor"
        if [[ ! -f "$sensor_path" ]]; then
          echo "ERROR [$rule_id]: sensor $sensor_path does not exist"
          errors=$((errors + 1))
        elif [[ ! -x "$sensor_path" ]]; then
          echo "ERROR [$rule_id]: sensor $sensor_path is not executable"
          errors=$((errors + 1))
        fi
      fi
      if [[ -z "$judge_prompt" ]]; then
        echo "ERROR [$rule_id]: mechanization=grep+judgment requires judge_prompt, got null"
        errors=$((errors + 1))
      else
        judge_path="$HARNESS_DIR/$judge_prompt"
        if [[ ! -f "$judge_path" ]]; then
          echo "ERROR [$rule_id]: judge_prompt $judge_path does not exist"
          errors=$((errors + 1))
        fi
      fi
      ;;
    inferential)
      if [[ -n "$sensor" ]]; then
        echo "ERROR [$rule_id]: mechanization=inferential must have sensor=null, got '$sensor'"
        errors=$((errors + 1))
      fi
      if [[ -z "$judge_prompt" ]]; then
        echo "ERROR [$rule_id]: mechanization=inferential requires judge_prompt, got null"
        errors=$((errors + 1))
      else
        judge_path="$HARNESS_DIR/$judge_prompt"
        if [[ ! -f "$judge_path" ]]; then
          echo "ERROR [$rule_id]: judge_prompt $judge_path does not exist"
          errors=$((errors + 1))
        fi
      fi
      ;;
    doc-only)
      if [[ -n "$sensor" ]]; then
        echo "ERROR [$rule_id]: mechanization=doc-only must have sensor=null, got '$sensor'"
        errors=$((errors + 1))
      fi
      if [[ -n "$judge_prompt" ]]; then
        echo "ERROR [$rule_id]: mechanization=doc-only must have judge_prompt=null, got '$judge_prompt'"
        errors=$((errors + 1))
      fi
      if [[ "$applies_at_count" -gt 0 ]]; then
        echo "ERROR [$rule_id]: mechanization=doc-only must have applies_at empty, got $applies_at_count entries"
        errors=$((errors + 1))
      fi
      ;;
    *)
      echo "ERROR [$rule_id]: unknown mechanization '$mode'"
      errors=$((errors + 1))
      ;;
  esac
done

if [[ $errors -gt 0 ]]; then
  echo ""
  echo "Index integrity check FAILED: $errors error(s) found"
  exit 1
fi

echo "Index integrity check PASSED: all $rules_count rules consistent"
exit 0
