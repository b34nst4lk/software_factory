---
id: impl-03
decision: "25 — two-loop architecture (inner TDD loop + final 6-gate verifier)"
title: "run.py — one herdr space per work unit, 4 panes, orchestrator output-pane logging"
scope_files: [factory/orchestrator/run.py]
acceptance:
  - story: "As a work unit, I run in my own herdr space with four panes"
    behaviors:
      - { id: B1, behavior: "per work unit, run.py calls workspace_create labeled by the unit id (one space per unit), not a shared 'factory' workspace", outcome: success }
      - { id: B2, behavior: "run.py starts 3 agent panes (implementer, inner verifier, final verifier) bound to their config models, plus 1 output pane that is a shell with no agent", outcome: success }
      - { id: B3, behavior: "run.py logs its actions to the output pane via herdr.pane_log (e.g. 'starting implementer for impl-NN', 'outer cycle 1')", outcome: success }
      - { id: B4, behavior: "on unit teardown (done/cancelled), run.py disposes the unit's space", outcome: success }
  - story: "As the human, the orchestrator's gates stay on its own stdout"
    behaviors:
      - { id: B5, behavior: "the stdin gates (c/s/w/m/q) remain on run.py's own stdout/stdin, not in any pane", outcome: success }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "test_run.py asserts workspace_create is called per unit with the unit-id label, 3 agent_start calls (implementer/inner/final models) + 1 output pane, and pane_log calls; gates remain on stdin"
model: deepseek-v4-flash:cloud
depends_on: [impl-01]
status: open
cycle: 0
last_verdict: ""
---
Restructure `run.py` so each work unit gets its own herdr space with four panes and an action
log. Stay within `factory/orchestrator/run.py` only. This unit depends on impl-01 (the
`pane_log` verb + the three config models).

Changes:
- Replace the single shared `workspace_create(repo_path, "factory")` with a per-unit
  `workspace_create(worktree, label=unit_id)` (one space per unit). Track the space so it can
  be torn down with the worktree.
- Per unit, create **four panes**:
  * implementer pane → `agent_start(impl_name, impl_pane, config.implementer_model)`;
  * inner-verifier pane → `agent_start(inner_name, inner_pane, config.inner_verifier_model)`;
  * final-verifier pane → `agent_start(final_name, final_pane, config.final_verifier_model)`;
  * output pane → a shell pane (split, no `agent_start`) for the orchestrator's log.
- Replace the existing `Panes` (impl + ver) with a four-pane struct (impl, inner, final,
  output). Update the cycle-call site to pass the new panes (the inner/final split is wired
  by a later unit; here only the setup + the final verifier is used for the existing
  single-loop cycle so the suite stays green).
- Log orchestrator actions to the output pane via `herdr.pane_log(output_pane, line)` at the
  key seams: unit start, each outer cycle, verifier run, verdict, gate. (The inner-loop
  logging is a later unit; here log the outer-cycle seams.)
- On unit teardown (done/cancelled), dispose the unit's space (and its panes).
- **Do not move the stdin gates** — `c`/`s`/`w`/`m`/`q` stay on run.py's own stdout/stdin
  (05 Q5 unchanged).

Behaviours to make pass:
- B1: workspace_create is called per unit, labeled by the unit id.
- B2: 3 agent_start calls (implementer/inner/final models) + 1 output pane (no agent).
- B3: pane_log is called to the output pane at the outer seams.
- B4: the unit's space is disposed on teardown.
- B5: stdin gates remain on run.py's own stdout/stdin.

Build test-first via /skill:tdd in `tests/test_run.py` (use MockHerdr). Annotate each test
with `# maps to: B<n>`. Implement until green. The existing single-loop cycle must still pass
(the final verifier runs; the inner pane is created but idle until a later unit wires it).

When your work is test-green and within scope, stop and summarize what changed and the test results.