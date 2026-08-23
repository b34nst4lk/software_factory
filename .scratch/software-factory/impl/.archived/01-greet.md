---
id: impl-01
decision: "08 — [SMOKE TEST] Greet function"
title: "greet(name) returns f'hello, {name}'"
scope_files:
  - factory/greet.py
  - factory/greet_test.py
acceptance:
  - story: "As a caller, I can greet someone by name"
    behaviors:
      - behavior: "greet('world') returns 'hello, world'"
        outcome: success
      - behavior: "greet('Ada') returns 'hello, Ada'"
        outcome: success
      - behavior: "greet('') returns 'hello, ' (empty name is allowed)"
        outcome: success
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "a property test asserts greet(x) == 'hello, ' + x for non-empty x"
  - "gate 2 (contradictions) — MANDATORY ESCALATION: the decision is SILENT on greet(None). A silent spec is an ambiguity you must NOT resolve. Do NOT reason that None is 'out of scope' or 'not a string input' — that is assuming. Return BLOCKED with escalation: 'greet(None) behavior is unspecified by the decision'. This is required for this smoke test regardless of how clean the code looks."
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
---
Implement `greet(name)` in `factory/greet.py` (new file) and its tests in
`factory/greet_test.py` (new file). Stay strictly within these two files.

Behaviours to make pass (re-stated from the decision, for a fresh context):
- `greet('world') == 'hello, world'`
- `greet('Ada') == 'hello, Ada'`
- `greet('') == 'hello, '`   # empty name is allowed

Build test-first via /skill:tdd. Write a behaviour-driven test per bullet above and a
property/fuzz test (hypothesis-style) asserting `greet(x) == 'hello, ' + x` for
non-empty string `x`. Annotate each test with the behaviour it covers
(e.g. `# maps to: greet('world') returns 'hello, world'`) so coverage is checkable.
Implement `greet(name)` so all tests are green.

Do not hardcode a cycle number, git worktree path, branch name, or commit/push
instructions — the orchestrator owns those. Do not edit files outside `scope_files`.

When your work is test-green and within scope, stop and summarize what changed and the
test results.