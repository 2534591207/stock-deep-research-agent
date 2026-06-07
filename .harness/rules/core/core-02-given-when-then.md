# CORE-02 — Given/When/Then Writability

**ID:** CORE-02
**Severity:** MUST
**Mechanization:** inferential (judge-core-05.md)
**Applies at:** prd, verify

---

## Statement

Every acceptance criterion in a PRD must be expressible as a
Given / When / Then scenario. Criteria that cannot be expressed this way
are too vague to verify and must be rewritten before the PRD is approved.

---

## Rationale

"The API should be fast" is not verifiable. "Given a list of 1000 items,
When the client calls GET /items, Then the response arrives in < 200ms at p99"
is verifiable. G/W/T forces precision. It also makes the acceptance-report
(Phase 5) mechanical: each criterion maps to one test or evidence item.

---

## What G/W/T means in practice

- **Given:** the precondition or system state.
- **When:** the action taken (user, client, or system).
- **Then:** the observable, measurable outcome.

G/W/T scenarios do not have to be BDD syntax — prose is fine as long as
all three parts are present.

---

## Mechanization

This rule is **inferential**: the judge prompt at `feedback/judge-core-05.md`
is used by a reviewer agent to evaluate whether PRD criteria meet the G/W/T
standard. No grep sensor is appropriate for this rule.

---

## Waiver

Not waivable. Vague criteria must be rewritten, not waived. If a criterion
is genuinely non-testable (e.g., UX desirability), document it as an
assumption in the PRD and exclude it from the acceptance gate.
