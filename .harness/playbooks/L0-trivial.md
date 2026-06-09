# Playbook L0 — Trivial

## Scope

Single-file change ≤5 lines of substantive diff. No logic change. No public surface touched.

Examples:
- Typo fix in a comment or log message.
- Renaming a private local variable.
- Tweaking a constant value that does not change behavior contracts (e.g., a log level).
- Updating a README pointer.

## Intake heuristic

Classify as L0 iff ALL true:
- Diff ≤5 substantive lines (excluding whitespace).
- Touches exactly 1 file.
- Does NOT modify public API, schema, auth, or any file marked `preserve_on_force: true` in `rules/_index.md`.

If any condition fails → upgrade to L1.

## Required artifacts

- Commit message (one line, conventional commit format).

## Required sensors (run before commit)

- `bash .harness/sensors/check-placeholders.sh`
- `bash .harness/sensors/check-known-issues.sh`

## Agents involved

- implementer only.

## Human gate

None.

## Definition of done

- Commit landed.
- Sensors above PASS.
- No new entry in `known-issues/_registry.yaml`.
