# Rules Index — topology: custom

schema_version: "2.0"
topology: custom
last_updated: "2026-06-07T13:29:08Z"

## CORE rules (5 total)

These rules apply to all topologies. They encode the fundamental discipline
of the six-phase workflow and design-acceptance practice.

```yaml
rules:
  - id: CORE-01
    file: core/core-01-explicit-intent.md
    title: "Explicit intent — PRD before code"
    mechanization: doc-only
    sensor: null
    judge_prompt: null
    applies_at: []
    severity: MUST
    tags: [workflow, intent]

  - id: CORE-02
    file: core/core-02-given-when-then.md
    title: "Given/When/Then writability"
    mechanization: inferential
    judge_prompt: feedback/judge-core-05.md
    applies_at: [prd, verify]
    severity: MUST
    tags: [acceptance, testability]

  - id: CORE-03
    file: core/core-03-six-phase-workflow.md
    title: "Six-phase workflow discipline"
    mechanization: doc-only
    sensor: null
    judge_prompt: null
    applies_at: []
    severity: MUST
    tags: [workflow, process]

  - id: CORE-04
    file: core/core-04-honest-voice.md
    title: "Honest voice — no AI-slop"
    mechanization: doc-only
    sensor: null
    judge_prompt: null
    applies_at: []
    severity: SHOULD
    tags: [quality, communication]

  - id: CORE-05
    file: core/core-05-design-acceptance.md
    title: "Design must be reviewable before build"
    mechanization: inferential
    judge_prompt: feedback/judge-core-05.md
    applies_at: [design]
    severity: MUST
    tags: [design, review, acceptance]
```

## L1 / L2 / L3 rules

None installed. This is the `custom` topology baseline.
Add project-specific rules here as your harness matures.
See `README.md` for the promotion path.

## Sensor coverage

| Rule | Sensor | Exit code |
|---|---|---|
| CORE-01 | check-placeholders.sh (indirect) | 0=pass, 1=fail |
| CORE-02 | judge-core-05.md (inferential, no sensor) | n/a |
| CORE-03 | check-workflow-state.sh | 0=pass, 1=fail |
| CORE-04 | check-signoff.sh (partial) | 0=pass, 1=warn |
| CORE-05 | judge-core-05.md (inferential, no sensor) | n/a |
