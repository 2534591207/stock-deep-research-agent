# CORE-04 — Honest Voice (No AI-Slop)

**ID:** CORE-04
**Severity:** SHOULD
**Mechanization:** doc-only
**Applies at:** prd, design, verify

---

## Statement

Harness documents (PRD, design, acceptance-report, review-packet) must be
written in plain, direct language. AI-generated filler, hedge phrases, and
corporate boilerplate are not acceptable.

---

## Rationale

Documents written by AI without human editing tend to be long, vague, and
full of phrases that sound authoritative but carry no information:
"leveraging best practices", "ensuring a robust solution", "in order to
facilitate a seamless experience". These phrases obscure meaning, slow
review, and make it impossible to tell whether the author understood the
problem.

A PRD that takes 10 minutes to read and leaves the reader uncertain what
is being built is worse than no PRD.

---

## Prohibited patterns

Avoid these in harness documents:

- "leveraging" (say "using")
- "ensure a seamless experience" (say what the experience actually is)
- "in order to facilitate" (say "to")
- "robust and scalable" without defining the numbers
- "best practices" without citing which ones
- Passive voice that hides who does what ("it will be implemented")
- Sentences that hedge every claim ("may", "might", "could potentially")

---

## What honest voice looks like

- Short sentences. One idea per sentence.
- Active voice: "The API returns 404 if the user does not exist."
- Concrete numbers: "Response time < 200ms at p99 under 1000 RPS."
- Named actors: "The implementer writes the migration. The reviewer approves it."

---

## Mechanization note

This rule is **doc-only**. No sensor enforces it. The `check-signoff.sh`
sensor checks for a human sign-off on design documents, which partially
gates against fully unreviewed AI output.

---

## Waiver

Not applicable. This is a quality standard, not a gate. SHOULD severity
means reviewers flag violations but do not block on them.
