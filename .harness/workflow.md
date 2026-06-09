# Six-Phase Workflow — init-harness v2 (topology: custom)

Every task, regardless of size, passes through these six phases in order.
Playbooks (`playbooks/L0–L3.md`) define which artifacts are required at each tier.

---

## Phase 1 — Classify

**Gate:** task is assigned a tier before any work begins.

| Tier | Description | Example |
|---|---|---|
| L0 | Trivial (typo, rename, 1-line config) | Fix a comment |
| L1 | Small fix (bug, small refactor, <1 day) | Fix a null-pointer in handler |
| L2 | Feature (new endpoint, schema change, multi-file) | Add pagination to list API |
| L3 | High-risk (data migration, auth change, breaking API) | Migrate DB column type |

Exit criteria: `state/phase.yaml` updated with `phase: classify` and `tier: LN`.

---

## Phase 2 — PRD (Problem / Requirements / Definition)

**Gate:** written intent exists before any design or code.

Required artifact: `changes/<name>/PRD.md`
- Problem statement (what breaks or is missing)
- Goals and non-goals
- Acceptance criteria (plain language)

Exit criteria: PRD reviewed (L2+: by a second agent or human).

---

## Phase 3 — Design

**Gate:** design is reviewable before implementation.

Required artifact: `changes/<name>/design.md`
- Approach chosen and alternatives considered
- API/interface contracts (if applicable)
- Data model changes (if applicable)
- Risk surface identified

L3 also requires: `changes/<name>/risk-assessment.md` + `changes/<name>/rollback-plan.md`

Exit criteria: design reviewed; `feedback/runs/<name>-design.yaml` written (L2+).

---

## Phase 4 — Build

**Gate:** implementation follows the accepted design.

Constraints:
- Code matches the design doc; deviations require a design amendment.
- No new abstractions beyond what design specifies.
- Tests written before or alongside production code (not after).

Exit criteria: all tests pass locally; sensors pass (`check-all.sh`).

---

## Phase 5 — Verify

**Gate:** acceptance criteria from PRD are demonstrably met.

Required artifact: `changes/<name>/acceptance-report.md`
- Each PRD acceptance criterion mapped to evidence (test name, log output, screenshot).
- Reviewer verdict: PASS / CONDITIONAL / FAIL.

L2+ also requires: `changes/<name>/review-packet.md` summarizing the change for reviewers.

Exit criteria: acceptance-report signed off; `feedback/runs/<name>-acceptance.yaml` written.

---

## Phase 6 — Close

**Gate:** change is merged, documented, and harness state is reset.

Checklist:
- [ ] `state/phase.yaml` reset to `phase: idle`
- [ ] `changelog.md` entry added
- [ ] `changes/<name>/` archived or deleted per team policy
- [ ] Any new rules or sensors added to `_index.md` and committed

---

## Workflow state machine

```
idle → classify → prd → design → build → verify → close → idle
                                    ↑
                         (amendment loop allowed: design → build)
```

Sensor `check-workflow-state.sh` validates that `state/phase.yaml` contains a valid phase.
