# CORE-01 — Explicit Intent (PRD before code)

**ID:** CORE-01
**Severity:** MUST
**Mechanization:** doc-only
**Applies at:** classify, prd

---

## Statement

No implementation begins until a PRD (Problem / Requirements / Definition) exists
and is placed at `changes/<name>/PRD.md`.

---

## Rationale

Code written without a written problem statement solves the wrong problem more
often than it solves the right one. A PRD forces the author to articulate
_what_ breaks or is missing before deciding _how_ to fix it. It also gives
reviewers a stable reference point that is independent of the implementation.

---

## What "explicit intent" means

1. The PRD exists before any production code is committed.
2. The PRD contains at minimum: problem statement, goals, non-goals, and
   acceptance criteria in plain language.
3. The PRD is traceable — the change directory name appears in the commit
   message or PR description.

---

## Mechanization note

This rule is **doc-only**: no automated sensor enforces it.
The six-phase workflow enforces it by convention: sensors check that
`state/phase.yaml` does not advance past `prd` without a PRD file present.
Human reviewers are the primary gate.

---

## Waiver

Waivers are allowed for L0 trivial changes only. Add a waiver file at
`feedback/waivers/<name>.yaml` with `rule: CORE-01` and `reason: L0-trivial`.
