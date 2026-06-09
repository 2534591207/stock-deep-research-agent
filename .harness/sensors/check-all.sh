#!/usr/bin/env bash
# check-all.sh — Orchestrator sensor. Walks rules/_index.md and runs each rule's sensor.
# Exit codes: 0=all pass, 1=at least one grep fail, 2=index integrity error, 3=infrastructure error
set -euo pipefail

STRICT=0
if [[ "${1:-}" == "--strict" ]]; then
  STRICT=1
fi

HARNESS_DIR="${HARNESS_DIR:-.harness}"
INDEX="$HARNESS_DIR/rules/_index.md"

if ! command -v yq &>/dev/null; then
  echo "ERROR: yq is required but not installed." >&2
  exit 3
fi

if [[ ! -f "$INDEX" ]]; then
  echo "ERROR: $INDEX not found." >&2
  exit 2
fi

passed=0
failed=0
judge_pending=0
inferential_pending=0

# Extract YAML from fenced ```yaml block if present; else use whole file.
YAML_TMP=$(mktemp -t harness-checkall-XXXXXX.yaml)
trap 'rm -f "$YAML_TMP"' EXIT
awk '/^```yaml[[:space:]]*$/{flag=1;next} /^```[[:space:]]*$/{flag=0;next} flag' "$INDEX" > "$YAML_TMP"
if [[ ! -s "$YAML_TMP" ]]; then
  cp "$INDEX" "$YAML_TMP"
fi

rules_count=$(yq '.rules | length' "$YAML_TMP" 2>/dev/null || echo 0)

if [[ "$rules_count" -eq 0 || "$rules_count" == "null" ]]; then
  echo "WARN: No rules found in $INDEX"
  exit 0
fi

for i in $(seq 0 $((rules_count - 1))); do
  rule_id=$(yq ".rules[$i].id" "$YAML_TMP")
  mode=$(yq ".rules[$i].mechanization" "$YAML_TMP")
  sensor=$(yq ".rules[$i].sensor // \"\"" "$YAML_TMP")
  judge_prompt=$(yq ".rules[$i].judge_prompt // \"\"" "$YAML_TMP")
  [[ "$sensor" == "null" ]] && sensor=""
  [[ "$judge_prompt" == "null" ]] && judge_prompt=""

  case "$mode" in
    grep)
      if [[ -z "$sensor" ]]; then
        echo "FAIL [$rule_id]: mechanization=grep but sensor is null"
        failed=$((failed + 1))
        continue
      fi
      sensor_path="$HARNESS_DIR/$sensor"
      if [[ ! -x "$sensor_path" ]]; then
        echo "FAIL [$rule_id]: sensor $sensor_path not found or not executable"
        failed=$((failed + 1))
        continue
      fi
      if "$sensor_path" 2>/dev/null; then
        echo "PASS [$rule_id]"
        passed=$((passed + 1))
      else
        echo "FAIL [$rule_id]: sensor exited non-zero"
        failed=$((failed + 1))
      fi
      ;;
    grep+judgment)
      if [[ -z "$sensor" ]]; then
        echo "FAIL [$rule_id]: mechanization=grep+judgment but sensor is null"
        failed=$((failed + 1))
        continue
      fi
      sensor_path="$HARNESS_DIR/$sensor"
      if [[ ! -x "$sensor_path" ]]; then
        echo "FAIL [$rule_id]: sensor $sensor_path not found or not executable"
        failed=$((failed + 1))
        continue
      fi
      hits=$("$sensor_path" 2>/dev/null || true)
      if [[ -z "$hits" ]]; then
        echo "PASS [$rule_id]: no candidate hits"
        passed=$((passed + 1))
      else
        echo "JUDGE-PENDING [$rule_id]: $sensor returned hits — reviewer must invoke judge prompt"
        judge_pending=$((judge_pending + 1))
      fi
      ;;
    inferential)
      echo "INFERENTIAL-PENDING [$rule_id]: reviewer must load judge_prompt and evaluate"
      inferential_pending=$((inferential_pending + 1))
      ;;
    doc-only)
      # skip silently
      ;;
    *)
      echo "WARN [$rule_id]: unknown mechanization '$mode', skipping"
      ;;
  esac
done

total=$((passed + failed + judge_pending + inferential_pending))
echo ""
echo "Summary: $total rules checked, $passed passed, $failed failed, $judge_pending pending-judge, $inferential_pending pending-inferential"

if [[ $failed -gt 0 ]]; then
  exit 1
fi
if [[ $STRICT -eq 1 && $((judge_pending + inferential_pending)) -gt 0 ]]; then
  echo "STRICT mode: pending judge/inferential gates block completion"
  exit 4
fi
exit 0
