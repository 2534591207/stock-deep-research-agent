# CORE-03 — Six-Phase Workflow Discipline

**ID:** CORE-03
**Severity:** MUST
**Mechanization:** doc-only
**Applies at:** classify, prd, design, build, verify, close

---

## Statement

Work proceeds through the six phases in order: classify → prd → design →
build → verify → close. Phases may not be skipped. The current phase is
recorded in `state/phase.yaml` and must reflect actual progress.

---

## Rationale

Skipping phases (e.g., jumping straight from classify to build) is the most
common cause of rework. Design that happens after build is rationalization,
not design. Verification that happens without acceptance criteria is theater.
The six-phase structure ensures each gate is passed in the right sequence.

---

## Allowed shortcuts by tier

| Tier | Allowed shortcuts |
|---|---|
| L0 | Skip PRD and design; create one-line note in commit message |
| L1 | Lightweight PRD (3-5 bullets); lightweight design (1 paragraph) |
| L2 | Full PRD + design required |
| L3 | Full PRD + design + risk assessment + rollback plan required |

See `playbooks/` for per-tier artifact requirements.

---

## Phase state machine

```
idle → classify → prd → design → build → verify → close → idle
```

The `design → build` transition may loop (amendment) if implementation
reveals a gap. Each amendment must update `changes/<name>/design.md`.

---

## Mechanization note

`check-workflow-state.sh` validates that `state/phase.yaml` contains a
recognized phase name. It does not enforce phase ordering — that is a
human/agent responsibility enforced by playbooks.

---

## Waiver

L0 tasks may use a lightweight commit-message-only record. All other
tiers must follow the full phase sequence.
