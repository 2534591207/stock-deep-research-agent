# Playbook L2 — Feature / Change

## Scope

New behavior. New endpoint, new use case, new business rule. ≥2 files of substantive change. Multi-layer (domain + application + adapter typically).

Examples:
- Add a new REST endpoint for an existing aggregate (e.g., `POST /orders/{id}/cancel`).
- Add a new business rule to a domain method (e.g., reservation can't be made for past dates).
- Add a new adapter for an external system.
- Refactor that touches public-but-internal interfaces (still backed by tests).

## Intake heuristic

Classify as L2 iff:
- ≥2 files of substantive change OR new public API surface.
- Spec-implied behavior change (PRD-driven).
- Does NOT touch auth, schema migration, payment, public-customer API, or any irreversible side effect.

If any of those conditions hit → upgrade to L3.

## Required artifacts

All of:
- `.harness/changes/<change-id>/PRD.md` (planner role)
- `.harness/changes/<change-id>/design.md` (architect role)
- `.harness/changes/<change-id>/acceptance-report.md` (reviewer at Phase 3)
- `.harness/changes/<change-id>/review-packet.md` (implementer fills, reviewer verifies)
- `.harness/changes/<change-id>/completion-report.md` (reviewer at Phase 6)
- Test code under `<TEST_ROOTS>/` mapping ≥1 test per PRD AC

## Required sensors

- `bash .harness/sensors/check-all.sh` (full grep + judgment pipeline)
- `bash .harness/sensors/check-workflow-state.sh` (verifies artifact set above is complete)
- Reviewer's full Phase 6 loader algorithm (see `roles/reviewer.md`)

## Agents involved

Full sequence:
```
analyst → planner → architect → [reviewer: Phase 3 gate] → implementer → tester → [reviewer: Phase 6 gate]
```

Each role MUST be a different agent instance from the next:
- architect ≠ reviewer (verifying their own design = no value).
- implementer ≠ reviewer (verifying their own code = no value).
- Tester MAY be implementer (test is verification of implementation), but reviewer MUST be different.

## Human gate

`review-packet.md` Section 8 ("Human-confirmation questions") must be filled by the AI AND answered by a human before merge. The presence of unanswered questions blocks the gate.

`check-workflow-state.sh` will FAIL if Section 8 is empty or unanswered.

## Definition of done

- Phase 6 `acceptance-report.md` shows `gate_result: PASS`.
- All PRD ACs map to ≥1 test, all green.
- `phase.yaml.current_phase = completed`.
- `review-packet.md` Section 9 ("Decision") has a human checkmark.

## Failure handoff

- Phase 3 design gate FAIL → architect reworks design, re-run Phase 3.
- Phase 6 final acceptance FAIL → implementer fixes, re-run Phase 5+6.
- Discovery mid-flow that scope is L3 (e.g., turns out to need schema migration) → STOP, escalate to L3 playbook.
