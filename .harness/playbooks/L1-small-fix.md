# Playbook L1 — Small Fix

## Scope

Single-file bug fix, dependency version bump, configuration tweak. No new behavior; restoring intended behavior.

Examples:
- Fix off-by-one in a method.
- Bump a library version to patch a CVE.
- Update a Spring property to correct a misconfigured endpoint.
- Add a missing null check that was already implied by spec.

## Intake heuristic

Classify as L1 iff:
- ≤1 file of substantive logic change (test files do not count).
- Bug fix in scope of an existing PRD AC or a recorded defect.
- Does NOT modify schema, public API, auth, or `preserve_on_force` files.
- Does NOT introduce new types, modules, or abstractions.

If any condition fails → upgrade to L2.

## Required artifacts

- Commit message + reference to bug source (issue ID, error log excerpt, or stack trace).
- Update or add ≥1 test reproducing the original bug.

## Required sensors (run before commit)

- Full `bash .harness/sensors/check-all.sh` (gathers grep + grep+judgment candidates).
- Reviewer agent runs the `applies_at: [implementation]` slice of `rules/_index.md`.

## Agents involved

- implementer + reviewer (light LLM-as-judge pass — focus on whether the fix matches the bug description, not full architectural review).

## Human gate

None.

## Definition of done

- New test fails on previous commit, passes on this commit.
- `check-all.sh` PASS (or any FAIL is a pre-existing known-issue, not newly introduced).
- Reviewer verdict APPROVE in `feedback/runs/<phase>-<ts>.json`.

## Failure handoff

- If during the fix you discover the bug touches multi-file or design assumptions: STOP. Upgrade to L2 and write a PRD.
