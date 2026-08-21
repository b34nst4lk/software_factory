# 14 — test-strength: tests must break when the behavior is wrong

Type: grilling
Status: open
Blocked by: 06
Found by: 07 (live smoke), via ticket 11.

## Question

Ticket 11 exposed a latent bug where the 5-cycle-backstop cap-lift **test passed by
accident** — the code was wrong (`_run_one` never passed `cap_override`) but the test
went green because the pre-fix "restart the cycle counter at 1" behavior happened to
consume the next mock read and surface DONE. The test did not break when the code was
wrong. That is the test-strength question, stated as a factory feature:

**Should the software factory enforce that a test actually fails when the behavior it
claims to cover is broken — and how?**

Candidate homes (to grill):
- **A behavior-coverage extension (06 gate 6)**: gate 6 already checks "tests map to
  behaviors; no orphans, no untested behaviors." Add a "test strength" sub-check: for
  each behavior, mutate/break the implementation and assert the mapped test fails
  (mutation testing, or a property-style "the test is false at a broken base").
- **A pre-commit check (06 Q7 formalize-when-discovered)**: a deterministic
  mutation/property-strength gate in the Husky hook, not the LLM verifier — "run the
  tests against a deliberately broken variant; they must fail." Migrate verifier→pre-
  commit as it becomes formalizable.
- **The to-tickets `acceptance.behaviors` "false at the base commit" rule (07b)**: that
  rule already says behaviors must be false before the work is done — but "the test
  fails when the behavior is broken" is stronger and checkable.

Decide: is test-strength a gate (which number?), a pre-commit check, or out of scope for
the prototype (far fog)? And what's the minimal tooling (mutmut / hypothesis + a broken
variant / a "tests fail on a reverted diff" smoke) for the Python-first dogfood?

## Answer

<!-- filled on resolve -->