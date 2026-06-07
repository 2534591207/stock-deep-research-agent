# Role: Planner

**Topology:** custom
**Active phases:** design

---

## Responsibilities

The planner owns the design. Their output is `design.md` (and L3 extras).

1. **Read the PRD** at `changes/<name>/PRD.md` in full before starting.

2. **Write the design** at `changes/<name>/design.md`:
   - Approach: the chosen solution and why.
   - Alternatives considered: at least one alternative with a reason for rejection.
   - API/interface contracts: if the change modifies any public or internal interface.
   - Data model changes: if the change modifies any schema or persistent state.
   - Risk surface: what can go wrong, and how each risk is mitigated.
   - Traceability: explicit reference to each PRD acceptance criterion.

3. **For L3 tasks**, also write:
   - `changes/<name>/risk-assessment.md`
   - `changes/<name>/rollback-plan.md`

4. **Request design review** (L2+): hand off to Reviewer and wait for verdict
   at `feedback/runs/<name>-design.yaml` before signalling Implementer to start.

5. **Update `state/phase.yaml`** to `phase: design` when design is complete and accepted.

---

## Constraints

- Do not start design before reading the PRD in full.
- Do not begin implementation (even prototyping) during the design phase.
- If implementation reveals a design gap, return to design phase and amend `design.md`.

---

## Outputs

| Artifact | Location | Required tier |
|---|---|---|
| design.md | `changes/<name>/design.md` | L1+ |
| risk-assessment.md | `changes/<name>/risk-assessment.md` | L3 |
| rollback-plan.md | `changes/<name>/rollback-plan.md` | L3 |
| design verdict | `feedback/runs/<name>-design.yaml` | L2+ |
| phase.yaml updated | `state/phase.yaml` | all |
