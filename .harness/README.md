# custom topology — init-harness v2

**topology: custom** is the polyglot, non-DDD starting point.
Use it when your stack is Python, Go, Node/TypeScript, a polyglot monorepo,
or any other language that is not Java/Spring/DDD-Hexagonal.

## When to use this topology

| Use case | Example |
|---|---|
| Python FastAPI service | REST API + SQLAlchemy + Alembic |
| Go microservice | net/http or chi router |
| Node/TypeScript API | Express, Fastify, NestJS |
| Polyglot monorepo | Go backend + TS frontend + Python scripts |
| Anything non-Java-DDD | Rust CLI, Elixir Phoenix, Ruby on Rails |

Do **not** use this topology for Java/Spring projects — use `java-spring-ddd-hex` instead.

## What ships in this bundle

```
.harness/
├── README.md              ← you are here (the map)
├── workflow.md            ← 6-phase workflow (classify → PRD → design → build → verify → close)
├── project.yaml           ← project metadata (topology: custom)
├── manifest.yaml          ← harness manifest (version, checksums)
├── HARNESS.md             ← human-readable manifest summary
├── gardening.md           ← periodic maintenance checklist
├── changelog.md           ← harness change log
├── state/
│   └── phase.yaml         ← current workflow phase tracker
├── rules/
│   ├── _index.md          ← canonical rule registry (5 CORE rules)
│   └── core/              ← 5 universal rules (no Java/Spring/DDD specifics)
├── sensors/               ← automated checks (no grep/ rules — add yours later)
├── feedback/              ← judge prompts + waivers + reviewer run records
├── roles/                 ← 4 agent role definitions
├── playbooks/             ← L0–L3 task tier guides
└── changes/               ← per-change artifact directories
    └── _template/         ← copy this for each new change
```

## Rules in this topology

This topology ships **5 CORE rules only** — no L1/L2/L3 framework-specific rules.
See `rules/_index.md` for the full registry.

| ID | Rule | Mechanization |
|---|---|---|
| CORE-01 | Explicit intent (PRD before code) | doc-only |
| CORE-02 | Given/When/Then writability | inferential (judge-core-05.md) |
| CORE-03 | Six-phase workflow discipline | doc-only |
| CORE-04 | Honest voice (no AI-slop) | doc-only |
| CORE-05 | Design acceptance | inferential (judge-core-05.md) |

## Sensors

`sensors/grep/` is empty by default. The 9 cross-cutting sensors (`check-*.sh`)
validate harness structure, placeholders, waivers, and workflow state.
Run them all: `bash .harness/sensors/check-all.sh`

## Promotion path

Promote from `custom` to a richer topology by hand:

1. Add L3 rules to `rules/` (copy a `core-NN-*.md` as a template).
2. Add corresponding sensors to `sensors/grep/` (grep-based or script-based).
3. Run `init --bootstrap-manifest` to re-baseline checksums.
4. Update `project.yaml` `topology:` field to a new name if desired.

For Java/Spring/DDD projects, switch to the `java-spring-ddd-hex` topology instead.

## Quick start

```bash
# run all sensors
bash .harness/sensors/check-all.sh

# create a new change directory (L2 feature or higher)
cp -r .harness/changes/_template .harness/changes/my-feature-20260516

# check workflow state
cat .harness/state/phase.yaml
```
