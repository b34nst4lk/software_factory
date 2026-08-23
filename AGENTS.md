# AGENTS.md — software-factory

This repo builds the **software factory**: a pi extension that turns loose ideas into working software via a staged, human-in-the-loop pipeline. Iteration 1 is a **prototype** built here; once it works it becomes the parameterized base for other projects.

## Read this first

The wayfinding **map** for this effort lives at [`.scratch/software-factory/map.md`](.scratch/software-factory/map.md). Load it before any work: it holds the Destination, Notes (model bindings + standing preferences), the Decisions-so-far index, and the fog. Child tickets are in `.scratch/software-factory/issues/`; research findings in `.scratch/software-factory/research/`. This is the local-markdown issue tracker — see `~/.pi/agent/skills/mattpocock-skills/skills/engineering/setup-matt-pocock-skills/issue-tracker-local.md` for operations.

## The pipeline

```
Wayfinder (glm-5.2:cloud)  →  to-tickets skill  →  Orchestrator (script)  →  Implementer (deepseek-v4-flash:cloud) + Verifier (qwen3.5:cloud)  [via herdr]
```

- **Wayfinder** clears fog and produces decisions in the tracker.
- **to-tickets** (a pi skill, this repo: `factory/skills/to-tickets/`) converts resolved decisions into implementation tickets.
- **Orchestrator** (a deterministic script, **no LLM**, this repo: `factory/orchestrator/`) reads implementation tickets and drives the implementer + verifier as pi agents in herdr panes. It owns the cycle counter, routes implementer↔verifier feedback back to itself, and surfaces it to the human.
- On ambiguity, the **Verifier never assumes** — it escalates back to Wayfinder (a new decision ticket); the orchestrator blocks the worker panes until that ticket resolves.

## Model bindings (Ollama-only, all via the single `ollama` pi provider)

| Role | Model | Per-pane binding |
|---|---|---|
| Wayfinder / grilling / to-tickets | `glm-5.2:cloud` | `pi --model glm-5.2:cloud` |
| Implementer | `deepseek-v4-flash:cloud` | `pi --model deepseek-v4-flash:cloud` |
| Verifier | `qwen3.5:cloud` | `pi --model qwen3.5:cloud` |

Cross-model review is enforced: implementer and verifier are different model families. The orchestrator is a script and uses no model.

## Standing rules

- The verifier **never assumes**. Ambiguity → new Wayfinder ticket, not a guess.
- Wayfinder is the **single decision channel**, continuously interleaved (not a one-shot front-end phase).
- Human gates: map→implementation handoff; pre-merge. Verifier-fail → Wayfinder ticket (no auto-retry).
- herdr is the runtime: drive pi workers with Pattern A — `herdr agent start <name> --kind pi --pane X -- --model <m>`, `agent prompt <name> "…" --wait --until done|blocked`, `agent read <name> --source recent-unwrapped --lines N`. See [research/03](.scratch/software-factory/research/03-herdr-pi-driver-pattern.md).

## Working in this repo

- Tickets 04–06 are resolved and 07 is built + smoke-green live; the orchestrator (`factory/orchestrator/`), the `factory-to-tickets` skill, and the `start-factory.sh` launcher all exist. Open frontier: 15 (deterministic verdict channel), 16 (interrupted-run resumability), 17 (git-as-state durability), 14 (test-strength gate, grilling).
- Run the factory: `./start-factory.sh software-factory --session factory` inside a herdr session that's running your wayfinder pi (one session — the orchestrator creates implementer/verifier panes as siblings). See `./start-factory.sh --help` and `factory/orchestrator/README.md`.
- Keep the map's Notes in sync with settled decisions; append closed tickets to Decisions-so-far.