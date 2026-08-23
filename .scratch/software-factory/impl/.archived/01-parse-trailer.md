---
id: impl-01
decision: 15 — deterministic verdict channel
title: verdict.parse_trailer reads the verifier's last-line `VERDICT overall=X`
scope_files:
- factory/orchestrator/verdict.py
- factory/orchestrator/tests/test_verdict.py
acceptance:
- story: As the orchestrator, I can recover a routing verdict from a pane whose only
    parseable signal is a one-line trailer
  behaviors:
  - behavior: parse_trailer(text ending in 'VERDICT overall=PASS') returns Overall.PASS
    outcome: success
  - behavior: parse_trailer(text ending in 'VERDICT overall=FAIL') returns Overall.FAIL
    outcome: success
  - behavior: parse_trailer(text ending in 'VERDICT overall=BLOCKED') returns Overall.BLOCKED
    outcome: success
  - behavior: parse_trailer(text with no 'VERDICT overall=' line) returns None
    outcome: failure
  - behavior: parse_trailer ignores a 'VERDICT overall=PASS' line that is NOT the
      last non-empty line
    outcome: failure
  - behavior: parse_trailer tolerates trailing whitespace, surrounding spaces around
      '=' (e.g. 'VERDICT overall = PASS'), and is case-insensitive on the overall
      token
    outcome: success
  - behavior: parse_trailer returns None for an unknown overall token (e.g. 'VERDICT
      overall=WAT')
    outcome: failure
verify:
- behaviors captured by tests; tests map 1:1 to acceptance.behaviors
- a property test asserts parse_trailer maps every 'VERDICT overall=X' last line (X
  in {PASS,FAIL,BLOCKED}) to the matching Overall, and any other last line to None
- parse_trailer does not call into file/fenced-YAML parsing; it is a pure text scan
  of the last non-empty line
model: deepseek-v4-flash:cloud
depends_on: []
status: done
cycle: 1
last_verdict: PASS
---
Add `parse_trailer(text: str) -> Overall | None` to `factory/orchestrator/verdict.py`
and its tests in `factory/orchestrator/tests/test_verdict.py`. Stay strictly within
these two files (do not edit cycle.py, prompts.py, or any test file other than
test_verdict.py).

Context (decision 15 — deterministic verdict channel): the verifier's verdict
**content** stays LLM-generated, but the **channel** must be reliable. The verifier
will (in a later unit) end its reply with a compact one-line routing trailer
`VERDICT overall=PASS|FAIL|BLOCKED` that survives any pane width. This unit delivers
ONLY the parser that reads that trailer. It returns a member of the existing
`Overall` enum (PASS/FAIL/BLOCKED) for routing, or `None` when no usable trailer is
present. It does NOT parse gates/feedback/escalation — the trailer carries routing
only; the long feedback/escalation text still comes from the `.verdict.yaml` file
(which a later unit wires). Keep `parse_trailer` a pure text scan: do not reuse the
fenced-YAML extraction path.

Behaviours to make pass (each is false at the base commit — parse_trailer does not
exist yet):
- parse_trailer(text ending in 'VERDICT overall=PASS') returns Overall.PASS
- parse_trailer(text ending in 'VERDICT overall=FAIL') returns Overall.FAIL
- parse_trailer(text ending in 'VERDICT overall=BLOCKED') returns Overall.BLOCKED
- parse_trailer(text with no 'VERDICT overall=' line) returns None
- parse_trailer ignores a 'VERDICT overall=PASS' that is NOT the last non-empty line
  (it reads the LAST non-empty line only — a stray mid-text trailer does not count
  when a different line follows)
- parse_trailer tolerates trailing whitespace, surrounding spaces around '='
  (e.g. 'VERDICT overall = PASS'), and is case-insensitive on the overall token
- parse_trailer returns None for an unknown overall token (e.g. 'VERDICT overall=WAT')

Build test-first via /skill:tdd. Write one behaviour-driven test per bullet above,
annotated with the behaviour it covers (e.g.
`# maps to: parse_trailer(...) returns Overall.PASS`), plus a property/fuzz test
(hypothesis-style) asserting: for every last non-empty line of the form
`VERDICT overall=X` with X in {PASS,FAIL,BLOCKED} (and arbitrary leading prose, and
optional surrounding whitespace / spaces around '='), parse_trailer returns the
matching Overall; for any other last line it returns None. Implement until green.

Do not change the existing `parse_verdict`, `parse_verdict_yaml`, `route`, or
`Overall` enum members — `parse_trailer` is additive and reuses the existing
`Overall` enum. Stay within scope_files.

When your work is test-green and within scope, stop and summarize what changed and
the test results.