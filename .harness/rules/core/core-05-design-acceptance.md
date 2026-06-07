# CORE-05 — Design Acceptance

**ID:** CORE-05
**Severity:** MUST
**Mechanization:** inferential (judge-core-05.md)
**Applies at:** design

---

## Statement

A design document must be reviewed and accepted before implementation begins.
"Accepted" means: a second agent or human has read the design, confirmed it
addresses the PRD, and recorded a verdict in `feedback/runs/`.

---

## Rationale

A design that no one has read is not a design — it is a plan written for
the author's own benefit. Review forces clarity: reviewers who cannot
understand a design identify gaps before they become code. Design review
also catches scope creep, missing non-goals, and over-engineering early.

---

## What "reviewable" means

A design is reviewable if:
1. It is in `changes/<name>/design.md` (not in a chat log or a comment).
2. It is written in plain language (see CORE-04).
3. It explicitly references the PRD acceptance criteria it addresses.
4. It describes the approach, alternatives considered, and why the chosen
   approach was selected.
5. It identifies the risk surface (what can go wrong, how it is mitigated).

---

## Acceptance verdict

Verdicts are recorded at `feedback/runs/<name>-design.yaml`:

```yaml
rule: CORE-05
change: <name>
verdict: PASS | CONDITIONAL | FAIL
reviewer: <agent-id or human name>
date: <ISO-8601>
notes: |
  <free text — required for CONDITIONAL or FAIL>
```

CONDITIONAL means implementation may proceed with noted caveats.
FAIL means the design must be revised before implementation begins.

---

## Mechanization

The judge prompt at `feedback/judge-core-05.md` guides a reviewer agent
through the evaluation. No grep sensor is appropriate for this rule.

---

## Waiver

L0 and L1 tasks may use a one-line design note in the PRD instead of a
separate design document. The waiver must be declared in the PRD itself:
`design_waiver: L1-inline — design embedded in PRD section X`.
