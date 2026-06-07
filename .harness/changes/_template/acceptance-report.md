# Acceptance Report — <CHANGE_ID>

> Written by **reviewer** role at Phase 3 (design gate) or Phase 6 (final acceptance).
> Reviewer MUST be a different agent instance from architect/implementer/tester.

## Metadata

- Change ID: <CHANGE_ID>
- Phase: design-gate | final-acceptance
- Reviewer agent: <REVIEWER_AGENT_ID>
- Timestamp: <TIMESTAMP>
- Risk tier: L0 | L1 | L2 | L3

## Inputs read

- `.harness/changes/<CHANGE_ID>/PRD.md`
- `.harness/changes/<CHANGE_ID>/design.md`
- `.harness/changes/<CHANGE_ID>/review-packet.md` (L2+)
- `.harness/rules/_index.md`
- `.harness/feedback/waivers/` (current)
- Source diff (if Phase 6)

## Rule-by-rule verdict

> Reviewer loader output. See `.harness/feedback/runs/<phase>-<timestamp>.json` for the machine-readable companion. This section is the human-readable rendering.

| rule_id | mechanization | verdict | hits | notes |
|---|---|---|---|---|
| CORE-01 | inferential | PASS | — | All ACs are testable. |
| CORE-05 | inferential | PASS | — | G/W/T-writable. |
| DDD-01 | grep | PASS | 0 | — |
| DDD-06 | grep+judgment | PASS | 0 candidates | — |
| SB-07 | grep | FAIL | 1 | adapter/web/security/SecurityConfig.java:37 — Authorization-as-username detected. See SECURITY-STUB-001. |
| ... | ... | ... | ... | ... |

## Inferential rule details

For each `inferential` rule, paste the judge prompt verdict JSON:

```json
{
  "rule_id": "CORE-05",
  "verdict": "PASS",
  "failing_ACs": [],
  "evidence_excerpt": "AC-1: When user POSTs /orders with valid body → Then 201 with Location header"
}
```

## Summary

- Pass: N
- Fail: M
- Waived: K
- Skipped (not applies_at this phase): S
- **Gate result: PASS | FAIL**

## On FAIL — specific actions

For each failed rule, write:
- Rule ID + statement
- Concrete file:line evidence
- Fix path (what would make this pass)
- Estimated rework size

Example:
```
SB-07 (Authorization header as principal) — FAIL
  File: app/src/main/java/com/example/order/adapter/web/security/SecurityConfig.java
  Line: 37 — setPrincipalRequestHeader("Authorization")
  Fix path: Replace with proper JWT/session-cookie principal extraction.
  Estimated rework: 1 hour (single file, well-isolated).
```

## Reviewer notes

Free-form. Use this for context that doesn't fit in the verdict JSON.

---

> This report is **append-only**. If you find an error after writing, append a `## Correction` section; do not rewrite history.
