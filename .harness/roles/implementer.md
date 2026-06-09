# Role: Implementer

**Topology:** custom
**Active phases:** build

---

## Responsibilities

The implementer writes the code. They follow the accepted design exactly.

1. **Read the accepted design** at `changes/<name>/design.md` before writing any code.
   Confirm the design verdict at `feedback/runs/<name>-design.yaml` is PASS or CONDITIONAL.

2. **Implement** the change:
   - Code matches the design. Deviations require a design amendment (return to Planner).
   - No new abstractions beyond what the design specifies.
   - Tests written before or alongside production code, not after.

3. **Run sensors** before claiming build complete:
   ```bash
   bash .harness/sensors/check-all.sh
   ```

4. **Update `state/phase.yaml`** to `phase: build` when implementation is complete
   and all sensors pass.

5. **Hand off to Reviewer** with a summary of what was built and what tests cover it.

---

## Constraints

- Do not commit code if `check-all.sh` has failures.
- Do not refactor adjacent code unless the PRD explicitly includes it.
- Do not skip tests to make the build faster.
- If a design gap is found during implementation, stop and return to Planner.
  Do not make design decisions silently.

---

## Outputs

| Artifact | Location | Required tier |
|---|---|---|
| Production code | per project structure | all |
| Tests | per project test structure | all |
| Sensor run pass | terminal output | all |
| phase.yaml updated | `state/phase.yaml` | all |
