# Rollback Plan — <CHANGE_ID>

> **L3 only.** Written by architect during Phase 2.

## Trigger conditions

Under what observed signals should we execute this rollback?

- Error rate on changed endpoint > X% for Y minutes.
- p99 latency on changed flow > Z ms for Y minutes.
- Data integrity check (specify which) detects N inconsistencies.
- Customer complaint volume on the changed feature exceeds baseline by K standard deviations.
- Explicit team call: "<named person> says revert."

If none of the above fire but team has a bad feeling — that's also a valid trigger. Document it.

## Manual rollback steps (in order)

Each step must be runnable by an on-call engineer who has NOT participated in this change. Assume they have shell access and `gh`/`kubectl`/etc. but no project-specific tribal knowledge.

1. **Flag flip**:
   ```bash
   <exact command to flip feature flag to OFF>
   ```
   Expected observation: <what should change>; verification: <how to confirm>.

2. **Code revert**:
   ```bash
   git revert <COMMIT_SHA>
   git push origin <main-branch>
   ```
   Expected build/deploy time: <minutes>.

3. **DB migration rollback (if applicable)**:
   ```bash
   <exact command — flyway:undo, manual SQL, etc.>
   ```
   Idempotency check: <how to verify migration table state>.

4. **Cache invalidation (if applicable)**:
   ```bash
   <exact command>
   ```

5. **Downstream notification**:
   - Who: ...
   - Channel: ...
   - Message template: ...

## Automated rollback

If feature flag flip + code revert is the entire rollback (no data side effects), the rollback can be automated via:

```yaml
# .github/workflows/auto-rollback.yml (example only — not auto-generated)
on:
  workflow_dispatch:
    inputs:
      reason: { required: true }
jobs:
  rollback:
    runs-on: ubuntu-latest
    steps:
      - run: <flag flip>
      - run: <revert + push>
```

If rollback requires data restore or coordinated downstream notification, do NOT automate; keep it manual.

## Verification post-rollback

- [ ] Error rate returned to baseline within X minutes.
- [ ] p99 latency returned to baseline within Y minutes.
- [ ] Affected customers no longer reporting issues (sample N).
- [ ] No data inconsistencies introduced by the rollback itself (run `<verification script>`).
- [ ] On-call signed off in #ops channel.

## Stakeholders to notify

- Engineering: ...
- Product: ...
- Customer support: ...
- (If customer-visible) Customer comms / status page: ...

## Post-mortem trigger

A rollback always triggers a post-mortem within <POSTMORTEM_SLA_DAYS> business days. Owner: ... .

---

Reviewer at Phase 3 must confirm:
- Each manual step has a literal command, not prose.
- Each verification step has a measurable signal, not "looks ok".
- Owner is a named human, not a team alias.
