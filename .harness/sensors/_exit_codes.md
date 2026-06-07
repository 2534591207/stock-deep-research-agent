# Sensor Exit Codes Reference

## check-all.sh

| Exit Code | Meaning |
|-----------|---------|
| 0 | All grep rules passed; any pending-judge or pending-inferential items noted but non-blocking |
| 1 | At least one grep-mode rule sensor exited non-zero (hard failure) |
| 2 | Index integrity error (e.g., `_index.md` not found or malformed) |
| 3 | Infrastructure error (e.g., `yq` not installed) |

## Per-sensor exit codes

| Script | Exit 0 | Exit 1 | Exit 2 | Exit 3 |
|--------|--------|--------|--------|--------|
| `check-index.sh` | All rules in `_index.md` consistent with disk | Integrity mismatch found (row-level errors printed) | `_index.md` not found | `yq` not installed |
| `check-placeholders.sh` | No double-curly template tokens found in `.harness/` | Unsubstituted placeholders found | — | — |
| `check-marker-blocks.sh` | All managed-file marker blocks structurally valid (hash drift is WARN only, not failure) | Structural violation: wrong count, nested, or inverted markers | — | — |
| `check-dry-run-purity.sh` | Working tree clean, or not a git repo (advisory) | Uncommitted changes found after `--dry-run` | — | — |
| `check-known-issues.sh` | No `touched-must-fix` entries | One or more `touched-must-fix` entries found | `yq` not installed | — |
| `check-workflow-state.sh` | All required artifacts for current tier present and non-empty | One or more required artifacts missing or empty | No active change (exits 0 with note) | — |
| `check-waiver-expiry.sh` | Always 0 — purely advisory; expired waivers printed as WARN | — | — | — |
| `check-signoff.sh` | Valid `Signed-off-by: Name <email>` line found | Signoff missing or `review-packet.md` not found | — | — |

## Notes

- **Advisory** sensors (`check-waiver-expiry.sh`, `check-dry-run-purity.sh` when not in git) always exit 0 and print informational output only.
- `check-all.sh` orchestrates only `grep`-mode sensors directly; `grep+judgment` and `inferential` modes emit `*-PENDING` lines for the reviewer agent to handle.
- Sensors read `HARNESS_DIR` env var (default: `.harness`) so they work from any working directory.
