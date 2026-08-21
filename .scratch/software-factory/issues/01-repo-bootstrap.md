# 01 — Repo bootstrap

Type: task
Status: resolved
Blocked by:

## Question

Stand up the repo so the prototype can be built: `git init`, write `AGENTS.md` (agent instructions for this repo), seed `CONTEXT.md` with the domain glossary (Software Factory, Orchestrator [script], Implementer, Verifier, Wayfinder [decision engine], to-tickets skill, herdr [runtime], work unit, escalation), and create the factory code directory scaffold (e.g. `factory/` for the orchestrator script + the to-tickets skill). No decision to make — just the setup that unblocks the build.

## Answer

Resolved 2026-08-19. Repo bootstrapped and committed (`2f6b540` on `main`):
- `git init -b main`, first commit.
- `AGENTS.md` — repo guide: pipeline (`wayfinder → to-tickets → orchestrator → implementer+verifier via herdr`), Ollama-only model bindings table, standing rules (verifier never assumes, cross-model review, human gates), pointer to the map + research/03.
- `CONTEXT.md` — domain glossary per the domain-modeling format: pipeline roles (Wayfinder, to-tickets, Orchestrator, Implementer, Verifier), runtime (herdr, Work Unit), process (Cycle, Escalation), each with `_Avoid_` aliases.
- `factory/` scaffold: `factory/orchestrator/` (placeholder, language TBD by 05) and `factory/skills/to-tickets/` (stub `SKILL.md` + `agents/openai.yaml`, contract TBD by 04). Both marked do-not-implement until their grilling tickets resolve.
- `.gitignore` (node_modules, dist, .env, logs, OS). `.scratch/software-factory/` (the wayfinder map + tickets + research) is tracked.

No decisions were made — pure setup. Unblocks 07. The 02 build action (add `qwen3.5:cloud` to `~/.pi/agent/models.json`) is a global-config change, intentionally NOT applied here; do it at build time (07) with user confirmation.