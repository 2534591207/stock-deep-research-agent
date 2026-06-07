# Risk Assessment — <CHANGE_ID>

> **L3 only.** Written by architect during Phase 2 (design).

## Surface

What code, data, infrastructure, or contracts does this change touch?

- Code paths: ...
- Database tables / columns: ...
- External APIs (consumed): ...
- External APIs (exposed): ...
- Configuration / secrets: ...
- Background jobs / scheduled tasks: ...
- Deployment artifacts: ...

## Blast radius

If this change is wrong / partial / fails mid-deploy, what breaks?

- User-facing impact: <number of users? which flows?>
- Downstream services affected: ...
- Data integrity risk: <can data be corrupted? lost? duplicated?>
- Time-to-detection if broken: <minutes / hours / days / never>
- Time-to-recovery: ...

## Reversibility

- Reversible by code revert alone: yes / no
- Reversible by schema migration rollback: yes / no
- Reversible by data restore from backup: yes / no
- **Irreversible aspects** (data loss, contract change observers cached, etc.): list explicitly

If "no" or "irreversible aspects present", this change is in the "no rollback" class and requires named-human accountability — not just signoff.

## Detection latency

If this change is silently wrong (passes tests, passes review, but breaks production behavior), how do we find out?

- Existing monitoring that would catch it: <Grafana dashboard URL, alerting rule, etc.>
- Detection latency: <minutes / hours / next billing cycle / customer complaint>
- New monitoring added by this change: <yes/no — what?>

## Mitigations

For each row above where the answer is uncomfortable, what mitigation are we applying?

| Risk | Mitigation | Owner |
|---|---|---|
| User-facing impact > 1% during deploy | Feature flag gates new flow | <name> |
| Schema change blocks rollback | Add migration only adds nullable columns; downgrade migration written and tested | <name> |
| Detection latency = customer complaint | Add Grafana panel + p99 alert pre-launch | <name> |

## Pre-launch checklist

- [ ] Feature flag exists and is OFF in production until explicit flip.
- [ ] Rollback plan tested in staging (see `rollback-plan.md`).
- [ ] Stakeholders notified: ...
- [ ] On-call team briefed.
- [ ] Runbook updated (or written if new).
- [ ] DB migration script idempotent (re-runnable on partial failure).

## Stakeholders to notify before/after

- Before: ...
- After (success): ...
- After (rollback): ...

---

This document is read by reviewer at Phase 3 gate. If any "Risk" row's "Mitigation" cell is empty or hand-wavy, gate FAILs.
