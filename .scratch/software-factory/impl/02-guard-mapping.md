---
id: impl-02
decision: 25 — two-loop architecture (inner TDD loop + final 6-gate verifier)
title: guard rule 3 (test↔behavior mapping) + to-tickets behavior-id authoring
scope_files:
- factory/orchestrator/guard.py
- factory/skills/to-tickets/SKILL.md
acceptance:
- story: As the to-tickets skill, I author a stable id per behavior
  behaviors:
  - id: B1
    behavior: the to-tickets SKILL.md output schema gives each behavior an `id` (B1..Bn),
      authored up front
    outcome: success
- story: As the guard, I enforce that tests map to real behaviors and vice-versa
  behaviors:
  - id: B2
    behavior: the guard parses an impl ticket's acceptance.behaviors into the set
      of behavior ids
    outcome: success
  - id: B3
    behavior: 'the guard parses test files under scope_files for `# maps to: <id>`
      comments, one per test function'
    outcome: success
  - id: B4
    behavior: the guard rejects (Violation) when a behavior id has no mapped test,
      a maps-to cites a non-existent id, or a test function has no maps-to
    outcome: success
  - id: B5
    behavior: the guard reports a test that maps to more than one behavior as a non-blocking
      warning, not a Violation
    outcome: success
verify:
- behaviors captured by tests; tests map 1:1 to acceptance.behaviors
- 'guard tests cover: clean mapping passes; orphan test, untested behavior, unmapped
  test each reject; multi-behavior mapping warns but passes'
- 'the SKILL.md schema example shows `id: B1` on a behavior entry'
model: deepseek-v4-flash:cloud
depends_on: []
status: done
cycle: 1
last_verdict: PASS
---
Add the third guard rule (test↔behavior mapping) and teach the to-tickets skill to author
behavior ids. This is evidence (1) from decision 14, folded into 25's build because the inner
loop (a later unit) drives per-behavior micro-cycles by these ids. Stay within
`factory/orchestrator/guard.py` and `factory/skills/to-tickets/SKILL.md` only.

`factory/skills/to-tickets/SKILL.md` — extend the behavior schema so each behavior entry
carries an `id`:
- In the output-schema example and the worked example, change
  `{ behavior: ..., outcome: ... }` to `{ id: B1, behavior: ..., outcome: ... }`.
- Add one line of guidance: ids are stable, authored up front (a value, so the value-only
  guard still holds), referenced by tests via `# maps to: <id>`.
- B1 is a doc behaviour; the verifier checks it by reading the schema. No code test for B1.

`factory/orchestrator/guard.py` — add a third rule alongside the two existing ones:
- Parse the impl ticket's `acceptance.behaviors` → the set of `id` values.
- Parse every test file under the ticket's `scope_files` → collect `# maps to: <id>`
  comments, attributed to the enclosing test function (a `def test_*`).
- Assert (hard Violations that block the commit):
  * every behavior id has ≥1 mapped test (no untested behavior);
  * every `# maps to:` cites a real id (no orphan test);
  * every test function has a `# maps to:` (no unmapped test).
- A test that carries more than one `# maps to:` is a **non-blocking warning** (reported so
  the verifier can judge whether it really probes all of them), NOT a Violation.

Behaviours to make pass:
- B1: the SKILL.md schema shows `id: B1` on a behavior entry (verifier-checked).
- B2: the guard extracts behavior ids from acceptance.
- B3: the guard extracts per-test `# maps to:` from test files.
- B4: the guard emits Violations for orphan/unmapped/untested.
- B5: a multi-behavior mapping warns but does not Violate.

Build test-first via /skill:tdd in the existing `tests/test_guard.py`. Annotate each test
with `# maps to: B<n>`. Implement until green. (The guard's own tests map to these behaviors —
this unit dogfoods the rule it introduces.)

When your work is test-green and within scope, stop and summarize what changed and the test results.