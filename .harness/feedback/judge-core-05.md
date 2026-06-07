# Judge Prompt — CORE-02 / CORE-05 Design & Acceptance Review

Use this prompt when acting as a reviewer agent evaluating a design document
(CORE-05) or PRD acceptance criteria (CORE-02).

---

## Invocation context

You are a reviewer. You have been given:
- `changes/<name>/PRD.md` — the problem statement and acceptance criteria
- `changes/<name>/design.md` — the proposed approach (for CORE-05 only)

Your task is to produce a verdict YAML and write it to
`feedback/runs/<name>-design.yaml` (for CORE-05) or
`feedback/runs/<name>-acceptance.yaml` (for CORE-02).

---

## CORE-05 — Design review checklist

Answer each question. A single NO is grounds for CONDITIONAL or FAIL.

1. **Traceability:** Does the design explicitly reference the PRD it addresses?
2. **Completeness:** Does the design cover all PRD acceptance criteria?
3. **Reviewability:** Is the design written in plain language (CORE-04)?
4. **Alternatives:** Does the design describe at least one alternative considered?
5. **Risk surface:** Does the design identify what can go wrong and how it is mitigated?
6. **Scope:** Does the design stay within the PRD non-goals?

Verdict rules:
- All YES → PASS
- 1-2 NO (minor gaps) → CONDITIONAL (implementation may proceed; gaps noted)
- 3+ NO or any NO on items 1, 2, or 5 → FAIL (design must be revised)

---

## CORE-02 — Acceptance criteria review checklist

For each acceptance criterion in the PRD:

1. Does it have an explicit **Given** (precondition)?
2. Does it have an explicit **When** (action)?
3. Does it have an explicit **Then** (observable, measurable outcome)?
4. Is the **Then** verifiable by a test, log, or screenshot — not just "looks correct"?

Verdict rules:
- All criteria pass all 4 checks → PASS
- 1-2 criteria with minor vagueness → CONDITIONAL (must be tightened before verify phase)
- Any criterion with no Then, or an unverifiable Then → FAIL (rewrite before approval)

---

## Output format

```yaml
rule: CORE-05   # or CORE-02
change: <name>
verdict: PASS | CONDITIONAL | FAIL
reviewer: <your agent-id or name>
date: <ISO-8601>
checklist:
  - item: "Traceability"
    result: YES | NO
    note: ""
  # ... one entry per checklist item
notes: |
  <Required for CONDITIONAL or FAIL. Be specific: which items failed and why.>
```
