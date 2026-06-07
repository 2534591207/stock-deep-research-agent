# 股票 Deep Research Agent — AGENTS

<!-- HARNESS:START v2 topology=custom -->
> This file is partially managed by `init-harness`. The block between
> HARNESS:START and HARNESS:END is generated; everything outside is yours.
> Do not edit inside the markers; re-run `init` to update.

## You are working in: 股票 Deep Research Agent

- Stack: unknown + unknown
- Topology: **custom**
- Workflow: risk-tier dispatcher (see `.harness/workflow.md` and `.harness/playbooks/`)

## Before starting any task — read in this order

1. `.harness/README.md` (60 lines, the map)
2. Classify task tier: **L0 trivial / L1 small fix / L2 feature / L3 high-risk**
3. Read `.harness/playbooks/L<N>-*.md` for required artifacts and gates
4. For L2+: create `.harness/changes/<short-name-YYYYMMDD>/` from `_template/`

## Key constraints (top 5)

- **L2+ requires `review-packet.md`** with answered human-confirmation questions. No exceptions.
- **L3 requires `Signed-off-by:` line** in review-packet. Mechanically enforced by `sensors/check-signoff.sh`.
- **Reviewer is always a separate agent instance** from architect / implementer / tester.
- **Sensors run on every change** regardless of tier: `bash .harness/sensors/check-all.sh` before commit.
- **Don't touch files marked `preserve_on_force: true`** in `rules/_index.md` without escalating to L3.

## Files of interest

- `.harness/rules/_index.md` — canonical rule list with mechanization spectrum
- `.harness/sensors/check-all.sh` — orchestrated sensor run
- `.harness/feedback/runs/` — past reviewer verdicts (newest first)
- `.harness/HARNESS.md` — manifest summary (version, model assumptions, last validation)
- `.harness/changelog.md` — every harness self-mutation logged
- `.harness/known-issues/_registry.yaml` — historic-debt registry (touch a `open` entry → it becomes `touched-must-fix`)

## Honest boundary

The phase-gate workflow is a **prompt-level convention**, not a process-level enforcement. Reviewer separation is a social contract. Sensors are the only mechanical floor. See `.harness/README.md` § "约束力边界" for full disclosure.

<!-- HARNESS:END -->
