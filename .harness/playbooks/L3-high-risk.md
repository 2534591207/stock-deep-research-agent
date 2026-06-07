# Playbook L3 — High-Risk

## Scope

Irreversible or wide-blast-radius change. Mistakes here are expensive or unrecoverable.

Examples:
- DB schema migration (column rename, table drop, FK addition).
- Authentication / authorization changes (login flow, session, RBAC).
- Payment, billing, financial reconciliation.
- Public customer-facing API contract change (URL, payload shape, semantics).
- Deletion of historical data.
- Changes to security-sensitive code (`preserve_on_force: true` files such as `SecurityConfig.java`).

## Intake heuristic

Classify as L3 if ANY hit:
- Modifies anything under `auth/`, `security/`, `payment/`, `billing/`, `migration/`.
- Touches a file with `preserve_on_force: true` in `rules/_index.md`.
- Adds/modifies/removes a Flyway/Liquibase migration script.
- Changes a public REST API contract (URL, payload, response code semantics).
- Affects a `known-issues/_registry.yaml` entry with `severity: high`.

**Default on ambiguity: L3.** Over-prescribe rather than under.

## Required artifacts

ALL L2 artifacts PLUS:
- `.harness/changes/<change-id>/risk-assessment.md` (architect; surface, blast radius, reversibility, detection latency, mitigations)
- `.harness/changes/<change-id>/rollback-plan.md` (architect; triggers, manual + automated rollback steps, verification post-rollback, stakeholders to notify)
- `Signed-off-by: <name> <email@example.com>` line in `review-packet.md` (mandatory; verified by `sensors/check-signoff.sh`)

## Required sensors

ALL L2 sensors PLUS:
- `bash .harness/sensors/check-signoff.sh <change-id>` — exits non-zero if DCO line missing.
- If `--enable-archunit` was set: `<CMD_TEST> # plus project-specific architecture checks if configured` must compile and run.
- Integration test pass (no mocks for the changed system if integration-testable).
- For schema migrations: `flyway migrate` (or equivalent) must run cleanly on a fresh fixture DB.

## Agents involved

ALL L2 agents PLUS:
- gardener: post-merge audit. Run `roles/gardener.md` flow against the changed harness state. If gardener finds the harness needs an update (e.g., new rule needed for this category of change), file a follow-up.

## Human gate

Two distinct human signals required:
1. **DCO signoff** in `review-packet.md` (`Signed-off-by: Full Name <email@example.com>`) — checked mechanically.
2. **Human-confirmation questions** in `review-packet.md` Section 8 — must be filled by AI AND answered with named human's words, not "approved" boilerplate.

`check-workflow-state.sh` + `check-signoff.sh` together enforce both.

## Definition of done

- L2 DoD criteria, PLUS:
- DCO signoff line present and well-formed.
- Rollback plan present and reviewer has verified it is executable (not just text).
- Gardener post-merge audit report written to `.harness/feedback/gardening/<date>.md`.

## Failure handoff

- Risk assessment surfaces an unmitigated risk → STOP, route back to planner to re-scope.
- Rollback plan cannot be made (e.g., schema change is genuinely irreversible) → STOP, surface to human; do NOT proceed without explicit acknowledgement of "we cannot rollback this."
- Signoff missing at gate time → block; do NOT merge with synthetic signoff.

## Examples of correct signoff line

```
Signed-off-by: Yao <yaohaidong@wanbridge.com>
```

NOT acceptable:
```
Signed-off-by: AI <ai@local>            # not a real human
Signed-off-by: Approved                 # no name/email
```
