# Role: Reviewer

**Topology:** custom
**Active phases:** design (CORE-05), verify (CORE-02), close

---

## Responsibilities

The reviewer is the acceptance gate. They evaluate design documents and
acceptance evidence. In the `custom` topology the reviewer and verifier
roles are merged into one role.

### Design review (Phase 3)

1. Read `changes/<name>/PRD.md` and `changes/<name>/design.md`.
2. Apply the judge prompt at `feedback/judge-core-05.md` (CORE-05 checklist).
3. Write verdict to `feedback/runs/<name>-design.yaml`.
4. If FAIL: return design to Planner with specific gaps listed.
5. If CONDITIONAL: note caveats; Implementer may proceed.
6. If PASS: signal Implementer to begin.

### Acceptance review (Phase 5)

1. Read `changes/<name>/PRD.md` (acceptance criteria) and
   `changes/<name>/acceptance-report.md` (evidence map).
2. Apply the judge prompt at `feedback/judge-core-05.md` (CORE-02 checklist).
3. Verify each criterion is mapped to concrete evidence (test name, log, screenshot).
4. Write verdict to `feedback/runs/<name>-acceptance.yaml`.
5. If FAIL: return to Implementer with specific gaps.
6. If PASS: signal close phase.

### Close review (Phase 6)

1. Confirm `state/phase.yaml` is reset to `idle`.
2. Confirm `changelog.md` has a new entry.
3. Confirm `changes/<name>/review-packet.md` is complete (L2+).

---

## Constraints

- Never self-review. The reviewer must be a different agent or human than
  the implementer (and the planner for design review).
- Verdicts must be YAML, not prose. Use the format in `feedback/judge-core-05.md`.
- CONDITIONAL verdicts require notes explaining the caveats.

---

## Outputs

| Artifact | Location | Required tier |
|---|---|---|
| Design verdict | `feedback/runs/<name>-design.yaml` | L2+ |
| Acceptance verdict | `feedback/runs/<name>-acceptance.yaml` | L2+ |
