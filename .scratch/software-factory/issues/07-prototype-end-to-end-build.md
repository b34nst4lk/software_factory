# 07 — Prototype end-to-end build + smoke test

Type: prototype
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06

## Question

Build the prototype end-to-end and smoke-test it on a trivial resolved Wayfinder decision: wire the to-tickets skill, the orchestrator script, the two model providers, and herdr; run one decision through `wayfinder → to-tickets → orchestrator → implementer + verifier` and confirm the script counts cycles, routes implementer↔verifier feedback, surfaces it to the human, and escalates an *injected* ambiguity back to Wayfinder (new ticket, panes block, resolve, resume). This is the destination artifact; may decompose further as fog from 04–06 clears. HITL for the smoke test (human observes the surfaced feedback and the escalation round-trip).

## Answer

Resolved 2026-08-21. The prototype is built and **smoke-tested green end-to-end, live**
(decision 08 — `greet(name)` with the injected `greet(None)` escalation).

**Built (07a–07c):** HITL prereqs (herdr v0.8.2 + `herdr integration install pi`, three
cloud models live); the `factory-to-tickets` skill (07b); the deterministic orchestrator
(07c — `factory/orchestrator/`, 13 modules, Husky guard + ruff/black/pytest/mypy/coverage,
131+ unit/integration tests, README).

**Live smoke (real herdr panes + real models, `--pr-stage off`):** `to-tickets` (glm-5.2)
→ orchestrator → implementer (deepseek-v4-flash) wrote `greet.py` test-first (4 tests
green via a symlinked venv) → verifier (qwen3.5) **BLOCKED** on `greet(None)` (gate 2) →
orchestrator parked + authored a grilling Wayfinder ticket → wayfinder resolved it
(`raise TypeError`) → **file-driven resume**, answer injected verbatim into both prompts →
implementer added the `None` guard → verifier **PASS** → `done`. Full escalation
round-trip + the FAIL→retry→PASS path, live. Git-as-state held: per-cycle commits on
`impl/01` (`c1 BLOCKED → c2 FAIL → c3 PASS`), append-only `run.log`, value-only
frontmatter. ~3 min wall-clock per run.

**Bugs the smoke surfaced → fixed (tickets 10–13, all resolved):** escalation ticket
numbering (seed past existing issues); cycle counter persists across park/resume (also
exposed + fixed a latent `cap_override` wiring bug — the 5-cycle `c` gate was silently
broken); `status` persisted to frontmatter (`done`/`parked`/`in_progress`/`cancelled`);
stdout line-buffered for live human-surfacing. Other live fixes: `--until {idle,done,
blocked}` (a finished worker settles as `idle` not `done`), file-based verdict (pane
wrapping corrupts inline YAML), `--cwd <worktree>` panes, `--approve`, herdr `--session`,
worktree `.venv` symlink.

**Next frontier (tickets 15–16, open):** a deterministic verdict channel (file contract +
compact `VERDICT overall=X` routing trailer + bounded re-prompt + human-gate floor) — the
retrieval is still flaky (the model doesn't always write `.verdict.yaml`); and
interrupted-run resumability (resume an existing `impl/NN` worktree; persist parked units'
escalation-ticket links across restarts).

**Observation (ticket 14, open):** test-strength — tests must actually break when the
behavior is wrong (graduated from the ticket-11 accident where a test passed by accident).

**Next iteration:** dogfooding — use the factory to develop the factory itself (the
factory's first self-build). 15 and 16 are the first candidates (both are self-changes to
the orchestrator), and 14 is a grilling that shapes the verifier's behavior-coverage gate.

<!-- filled on resolve -->