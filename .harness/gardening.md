# Gardening Checklist — 股票 Deep Research Agent

Run this checklist periodically (suggested: each sprint or monthly).

## Waiver hygiene
- [ ] Run `bash .harness/sensors/check-waiver-expiry.sh` — expire or renew stale waivers
- [ ] Review `feedback/waivers/` — remove any waivers for rules that no longer exist

## Rule drift
- [ ] Review `rules/_index.md` — are all listed rules still relevant?
- [ ] Check `sensors/grep/` — do sensor scripts match rules in `_index.md`?
- [ ] If new L3 rules were added manually, re-run `init --bootstrap-manifest`

## Change artifact hygiene
- [ ] Review `changes/` — archive or delete closed change directories
- [ ] Check `feedback/runs/` — keep last 10 runs, archive older ones

## Workflow state
- [ ] Run `bash .harness/sensors/check-workflow-state.sh` — confirm `state/phase.yaml` is `idle`
- [ ] If a change is in-flight, confirm `state/phase.yaml` matches actual progress

## Known issues
- [ ] Run `bash .harness/sensors/check-known-issues.sh` — confirm no `touched-must-fix` entries past due

## Harness version
- [ ] Check if a newer `init-harness` version is available (`init-harness --version`)
- [ ] If major version bump, review migration guide before upgrading

---
*Last gardening run: <!-- fill in date -->*
