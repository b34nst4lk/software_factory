# factory/

The software factory implementation — built (07a–07c), smoke-tested live (07).

## Layout

- `orchestrator/` — the deterministic orchestrator (no LLM). Reads implementation tickets
  and drives the Implementer (deepseek-v4-flash) + Verifier (qwen3.5) as pi agents via
  herdr. Python3; 13 modules; Husky guard + ruff/black/pytest/mypy/coverage; README with
  the invariants, gates, and run steps. Contract: ticket 05; protocol: ticket 06.
- `skills/to-tickets/` — the `factory-to-tickets` pi skill (glm-5.2) that converts one
  resolved Wayfinder decision into orchestrator-consumable implementation Work Units.
  Contract: ticket 04.

## Running

One herdr session is the intended topology: your wayfinder pi (glm-5.2) does the
wayfinding + `/skill:factory-to-tickets` to produce impl tickets, then the deterministic
orchestrator is kickstarted in a pane of that same session and creates the
implementer/verifier panes as siblings — all visible in one herdr UI.

```bash
herdr --session factory                                  # your wayfinder pi (glm-5.2)
./start-factory.sh software-factory --session factory   # in a split pane: runs the orchestrator
herdr session attach factory                            # watch the sidebar + impl/ver panes
```

`start-factory.sh` (repo root) reuses an existing herdr server for the session if one is
running, else starts a fresh headless one. See `./start-factory.sh --help` and
`orchestrator/README.md` for the full runbook, invariants, and flags.

## Pipeline

```
Wayfinder (glm-5.2)  →  /skill:factory-to-tickets  →  Orchestrator (script)  →
  Implementer (deepseek-v4-flash) + Verifier (qwen3.5)  [via herdr]
```

Decisions/contracts: tickets 04–06; build + live smoke: ticket 07; follow-ups: 10–17.
See the map at `.scratch/software-factory/map.md`.