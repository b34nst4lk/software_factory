---
id: impl-04
decision: "25 — two-loop architecture (inner TDD loop + final 6-gate verifier)"
title: "inner loop — per-behavior TDD micro-cycles, deterministic witness, inner-verifier LLM judgment, 5-attempt stall gate, red-witness escalate"
scope_files: [factory/orchestrator/cycle.py, factory/orchestrator/prompts.py]
acceptance:
  - story: "As an outer cycle, the implementer step runs an inner loop over the ticket's behaviors"
    behaviors:
      - { id: B1, behavior: "the inner loop iterates the ticket's acceptance.behaviors by id; for each Bn it prompts the implementer to write only the failing test for Bn, then to implement until Bn's test is green", outcome: success }
      - { id: B2, behavior: "the orchestrator runs pytest in the worktree via subprocess and reads the exit code to witness red (before impl) and green (after impl) per behavior", outcome: success }
      - { id: B3, behavior: "the inner-verifier pane is prompted after the red witness (judge the test honest) and after the green witness (judge the green honest) each micro-cycle", outcome: success }
  - story: "As a behavior that cannot get green, I hit a per-behavior human-gate"
    behaviors:
      - { id: B4, behavior: "a behavior is capped at 5 implementer attempts; on cap, the orchestrator surfaces a per-behavior human-gate (c/s/w) that does not increment the outer cycle counter", outcome: success }
  - story: "As a behavior whose test is green at base, I escalate to Wayfinder"
    behaviors:
      - { id: B5, behavior: "if a behavior's test is green at base (not false-at-base), the orchestrator escalates via the existing escalate path (author ticket, park unit) and does not guess", outcome: success }
  - story: "As the outer cycle, the inner loop is invisible to the cap and commits nothing"
    behaviors:
      - { id: B6, behavior: "the inner loop writes no state.db row and commits nothing; one outer cycle = inner-to-green + final 6-gate, counted by the cap as before", outcome: success }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "test_cycle.py asserts: per-behavior prompt→witness→prompt→witness flow with a stubbed pytest subprocess; inner-verifier prompted twice per behavior; 5-attempt cap → human-gate without incrementing the outer cycle; green-at-base → escalate (no guess); no state.db row from the inner loop"
model: deepseek-v4-flash:cloud
depends_on: [impl-02, impl-03]
status: open
cycle: 0
last_verdict: ""
---
Build the inner loop inside the implementer step of an outer cycle. Stay within
`factory/orchestrator/cycle.py` and `factory/orchestrator/prompts.py` only. Depends on
impl-02 (behavior ids) and impl-03 (the four panes incl. inner-verifier + output).

`prompts.py` — add four templates (no cycle number, no worktree path, no commit instructions;
the orchestrator owns those):
- `inner_write_test_prompt(behavior_id, behavior_text)` — "write ONLY the failing test for
  behavior Bn: <text>; do not implement; stop when the test is written."
- `inner_implement_prompt(behavior_id, behavior_text)` — "implement until behavior Bn's test
  is green; stop when green."
- `inner_judge_red_prompt(behavior_id, test_text)` — to the inner verifier: "judge whether
  this failing test actually probes behavior Bn, or is vacuous; reply with a short verdict."
- `inner_judge_green_prompt(behavior_id)` — "judge whether the green is honest (the test
  actually passed for the right reason)."

`cycle.py` — inside the implementer step of `run_cycle`, run the inner loop:
- Read the ticket's `acceptance.behaviors` (ids B1..Bn).
- For each behavior Bn:
  1. prompt the implementer (`inner_write_test_prompt`) → read.
  2. run `pytest` in the worktree via **subprocess** (injectable runner; read the exit code).
     If green at base → **escalate** (call the existing `escalate` author + return
     `CycleOutcome.ESCALATE`); never assume.
  3. prompt the inner-verifier pane (`inner_judge_red_prompt`) → read.
  4. prompt the implementer (`inner_implement_prompt`) → read.
  5. run pytest again; if not green, retry up to **5 attempts** per behavior; on the 5th
     failure surface a per-behavior human-gate (`c` continue / `s` stop / `w` escalate) that
     does **not** increment the outer `cycle_no`.
  6. prompt the inner-verifier pane (`inner_judge_green_prompt`) → read.
- The inner loop writes **no** `state.db` row and commits nothing; the per-cycle commit +
  `state.db` row happen once per outer cycle as today (after the final verifier).

Behaviours to make pass:
- B1: per-behavior write-test → implement prompt flow.
- B2: subprocess pytest witnesses red then green (exit code).
- B3: inner-verifier prompted twice per behavior (judge red, judge green).
- B4: 5-attempt cap → human-gate, outer cycle counter unchanged.
- B5: green at base → escalate (no guess), via the existing escalate path.
- B6: inner loop writes no state.db row, commits nothing; outer cycle count unchanged by the inner loop.

Build test-first via /skill:tdd in `tests/test_cycle.py` with a stubbed pytest runner +
MockHerdr. Annotate each test with `# maps to: B<n>`. Implement until green.

When your work is test-green and within scope, stop and summarize what changed and the test results.