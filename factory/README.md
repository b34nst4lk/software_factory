# factory/

The software factory implementation.

## Layout

- `orchestrator/` — the deterministic orchestrator script (no LLM). Reads implementation tickets and drives the Implementer + Verifier as pi agents via herdr. **Language is decided by ticket 05** — this directory is a placeholder until then.
- `skills/to-tickets/` — the `to-tickets` pi skill that converts resolved Wayfinder decisions into implementation tickets. **Contract is decided by ticket 04** — the SKILL.md here is a placeholder stub.

Both pieces are designed in grilling tickets (04, 05, 06) before they are built in ticket 07. See the map at `.scratch/software-factory/map.md`.