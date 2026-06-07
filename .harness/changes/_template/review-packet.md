# Review Packet — <CHANGE_ID>

> **MANDATORY for L2+ changes.** L3 requires a `Signed-off-by:` line at bottom.
>
> Purpose: route human attention to the questions that matter. Harness cannot certify behavior correctness; this packet certifies that the right evidence is in front of the human.

## 1. Original user request (verbatim)

> <PASTE_USER_REQUEST_HERE>

(Do not paraphrase. Use the user's actual words.)

## 2. AI's interpretation

What the AI understood the user wanted, in 3–5 bullets:

- Bullet 1: ...
- Bullet 2: ...
- Bullet 3: ...

## 3. PRD acceptance criteria summary

- AC-1: ...
- AC-2: ...
- AC-3: ...

→ Full PRD: `.harness/changes/<CHANGE_ID>/PRD.md`

## 4. Design summary (≤10 lines)

- Approach: ...
- Affected packages: ...
- New types: ...
- Schema changes: ... (or "none")

→ Full design: `.harness/changes/<CHANGE_ID>/design.md`

## 5. Test evidence

| AC | Test class | Test method | Status |
|---|---|---|---|
| AC-1 | OrderControllerIT | createOrderHappyPath | PASS |
| AC-2 | OrderControllerIT | createOrderInvalidBody | PASS |
| AC-3 | OrderServiceTest | cancellation_blocked_after_paid | PASS |

- Unit tests added: N (paths)
- Integration tests added: M (paths)
- Manual smoke: <screenshots / curl output / log excerpts>
- Coverage: line X% / branch Y% (changed files only)

## 6. Sensor verdicts

| Sensor | Result | Notes |
|---|---|---|
| check-all.sh | PASS | — |
| check-architecture.sh (grep + judge) | PASS | DDD-06 had 0 candidates |
| ArchUnit | N/A | not enabled |
| check-known-issues.sh | PASS | no `touched-must-fix` entries |

→ Reviewer verdict JSON: `.harness/feedback/runs/final-acceptance-<ts>.json`

## 7. Known risks

What might break? Be explicit, don't write "none" lazily.

- Risk: ... | Likelihood: low/med/high | Blast radius: ... | Mitigation: ...
- Risk: ... | Likelihood: ... | Blast radius: ... | Mitigation: ...

## 8. Human-confirmation questions

Questions the AI cannot answer alone. **Human must answer before merge.**

- Q1: Did we interpret "X" correctly? (AI's guess: ...)
- Q2: Should we also handle Y edge case? (Out of current PRD scope; explicit decision needed.)
- Q3: ...

### Human answers

> (filled by named human before merge)

- A1: ...
- A2: ...
- A3: ...

## 9. Decision

- [ ] Approved (proceed to merge)
- [ ] Approved with conditions: ...
- [ ] Rejected — return for rework: ...

Reviewer: __________________________ (name)
Date: __________

---

<!-- L3 ONLY — uncomment and fill before merge -->
<!-- Signed-off-by: Full Name <email@example.com> -->
