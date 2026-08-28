---
id: impl-05
decision: "25 — two-loop architecture (inner TDD loop + final 6-gate verifier)"
title: "sf audit — mutation over a unit's scope_files, report to narrative + sidebar, route survivors to the implementer"
scope_files: [factory/orchestrator/audit.py, factory/orchestrator/cli.py]
acceptance:
  - story: "As the human, I call an audit and get a mutation report"
    behaviors:
      - { id: B1, behavior: "`sf audit <unit>` (a cli.py subcommand) runs mutation testing over the unit's scope_files in its worktree", outcome: success }
      - { id: B2, behavior: "the audit writes a report (mutation score + surviving mutants) as a row to the per-repo state.db narrative and as a sidebar summary via herdr.report_metadata", outcome: success }
  - story: "As a surviving mutant, I am routed to the implementer as a fix cycle"
    behaviors:
      - { id: B3, behavior: "each surviving mutant is formatted into a fix prompt and sent to the unit's implementer pane via herdr.agent_prompt", outcome: success }
      - { id: B4, behavior: "the audit does not run in the per-cycle hot path; it is on-demand only", outcome: success }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "test_audit.py / test_cli.py assert: the audit subcommand runs the mutator over scope_files, writes a state.db row + a report_metadata call, and prompts the implementer pane once per survivor; no per-cycle hook invokes it"
model: deepseek-v4-flash:cloud
depends_on: [impl-03]
status: open
cycle: 0
last_verdict: ""
---
Add the on-demand mutation audit (evidence 4 from decision 14). Stay within
`factory/orchestrator/audit.py` (new) and `factory/orchestrator/cli.py` only. Depends on
impl-03 (the per-unit panes the audit routes to).

`audit.py` (new module):
- `run_audit(unit, worktree, scope_files, herdr, db, impl_pane) -> AuditReport`:
  * run a mutator over the unit's `scope_files` in the worktree. Use a small custom mutator
    (per-function statement/return mutation) for the prototype — keep it pluggable so mutmut
    can replace it later. The mutator is an injectable seam (tests stub it).
  * collect surviving mutants (mutant id + file + the mutation).
  * write one row to the narrative `state.db` (verdict='AUDIT', action='mutation', with the
    score) via the existing `state.log_cycle` seam (or a sibling; reuse the db handle).
  * call `herdr.report_metadata` with a summary like `impl-NN AUDIT score=NN% N survivors`.
  * for each survivor, `herdr.agent_prompt(impl_pane, fix_prompt(mutant))` (route to the
    implementer as a fix cycle; do not commit/push — the orchestrator owns that).

`cli.py` — add an `audit` subcommand: `python -m cli audit <effort> <unit-id>` that resolves
the unit, its worktree + scope_files + panes, and calls `run_audit`. It is **on-demand only**
— nothing in the per-cycle loop calls it.

Behaviours to make pass:
- B1: the audit subcommand runs the mutator over the unit's scope_files.
- B2: a state.db row + a report_metadata call are written with the score + survivors.
- B3: each survivor prompts the implementer pane once.
- B4: no per-cycle hook invokes the audit (it is reachable only via the cli subcommand).

Build test-first via /skill:tdd in `tests/test_audit.py` + `tests/test_cli.py` with a stubbed
mutator + MockHerdr + an in-memory db. Annotate each test with `# maps to: B<n>`. Implement
until green.

When your work is test-green and within scope, stop and summarize what changed and the test results.