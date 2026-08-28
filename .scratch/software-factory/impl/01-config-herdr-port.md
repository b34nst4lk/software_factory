---
id: impl-01
decision: 25 — two-loop architecture (inner TDD loop + final 6-gate verifier)
title: config (3 models + effort) + herdr port (per-unit workspace label, pane_log
  verb)
scope_files:
- factory/orchestrator/config.py
- factory/orchestrator/herdr.py
acceptance:
- story: As the orchestrator, I bind three agent models per unit
  behaviors:
  - id: B1
    behavior: config.default() exposes implementer_model='deepseek-v4-flash:cloud',
      inner_verifier_model='deepseek-v4-pro:cloud', final_verifier_model='glm-5.3-flash:cloud'
    outcome: success
  - id: B2
    behavior: config carries an effort setting for the implementer ('low') and the
      final verifier ('low'/'high'/'max')
    outcome: success
  - id: B3
    behavior: config.default() no longer exposes a single verifier_model (replaced
      by inner/final)
    outcome: success
- story: As the orchestrator, I log actions to a shell pane
  behaviors:
  - id: B4
    behavior: HerdrPort declares pane_log(pane_id, line) -> None
    outcome: success
  - id: B5
    behavior: the real Herdr.pane_log sends `herdr send-keys` to append the line to
      the pane
    outcome: success
  - id: B6
    behavior: MockHerdr.pane_log records the (pane_id, line) pair for test assertions
    outcome: success
verify:
- behaviors captured by tests; tests map 1:1 to acceptance.behaviors
- config tests assert the three model ids + effort fields; the old verifier_model
  field is gone
- herdr tests assert pane_log argv construction (real) and recording (mock) without
  invoking the binary
model: deepseek-v4-flash:cloud
depends_on: []
status: done
cycle: 1
last_verdict: PASS
---
Extend the two seams the two-loop build rests on. Stay within `factory/orchestrator/config.py`
and `factory/orchestrator/herdr.py` only.

`config.py` — replace the single `verifier_model` with two bindings and add effort:
- `IMPLEMENTER_MODEL = "deepseek-v4-flash:cloud"`, `INNER_VERIFIER_MODEL = "deepseek-v4-pro:cloud"`,
  `FINAL_VERIFIER_MODEL = "glm-5.3-flash:cloud"`.
- `Config` fields: `implementer_model`, `inner_verifier_model`, `final_verifier_model`
  (drop `verifier_model`), plus `implementer_effort: str = "low"` and
  `final_verifier_effort: str = "low"` (accept low/high/max; the runtime honoring of effort
  is a build-time fact, not asserted here — config only carries the values).
- `default(...)` returns the new fields.

`herdr.py` — add a one-way logging verb to the port and both impls:
- `HerdrPort.pane_log(self, pane_id: str, line: str) -> None: ...`
- Real `Herdr.pane_log` sends `herdr send-keys` to append the line to the shell pane (use the
  injectable runner; construct the argv, do not invoke the binary in tests).
- `MockHerdr.pane_log` records `(pane_id, line)` into a list for assertions.
- Do not change `workspace_create`'s signature here; per-unit *usage* of its label is a later
  unit. (This unit only adds the verb the later unit calls.)

Behaviours to make pass:
- B1: config.default() returns the three model ids above.
- B2: config carries implementer_effort='low' and final_verifier_effort='low'.
- B3: config has no verifier_model field.
- B4: HerdrPort declares pane_log.
- B5: real Herdr.pane_log builds a send-keys argv for the pane + line.
- B6: MockHerdr.pane_log records the (pane_id, line) pair.

Build test-first via /skill:tdd. Write a behaviour-driven test per bullet (in the existing
test_config.py / test_herdr.py) and annotate each with `# maps to: B<n>`. Implement until green.

When your work is test-green and within scope, stop and summarize what changed and the test results.