# 08 — [SMOKE TEST] Greet function

Type: decision
Status: resolved
Blocked by:
Purpose: trivial resolved Wayfinder decision to smoke-test the full factory pipeline (ticket 07). Disposable.

## Question

What is the smallest behaviour we can build that exercises every stage of the factory
(wayfinder → to-tickets → orchestrator → implementer + verifier), including an injected
escalation round-trip?

## Decision

Add a `greet(name)` function to a new module `factory/greet.py` that returns the string
`f"hello, {name}"` for a non-empty `name`.

- **Scope**: one new file `factory/greet.py` + a behavior test `factory/greet_test.py` (or
  `tests/test_greet.py`). Non-overlapping, independently implementable and verifiable.
- **Behaviour(s)** to capture:
  - Story: "As a caller, I can greet someone by name."
    - `{ behavior: "greet('world') returns 'hello, world'", outcome: success }`
    - `{ behavior: "greet('Ada')   returns 'hello, Ada'",   outcome: success }`
    - `{ behavior: "greet('')      returns 'hello, ' (empty name is allowed)", outcome: success }`
- **Verify**: implementer writes behavior-driven tests mapping to the behaviors above
  (plus a hypothesis/property check that `greet(x) == f"hello, {x}"` for non-empty x).
  Verifier 6-gate checklist runs; gate 6 (behavior-coverage) must pass.
- **Injected ambiguity (for the escalation round-trip)**: the verifier, on the first cycle,
  is instructed to BLOCK on "what should `greet(None)` return?" — orchestrator parks the
  unit, creates a new Wayfinder ticket, the human resolves it (decision: raise `TypeError`),
  the answer is injected verbatim into implementer+verifier prompts, and the unit resumes.

## Answer

Resolved 2026-08-21 (trivial, resolved up front for the smoke test).

- `greet(name)` lives in `factory/greet.py`, returns `f"hello, {name}"`.
- `name` is a non-empty string. Empty string `""` is allowed and yields `"hello, "`.
- `greet(None)` raises `TypeError` (the injected-ambiguity resolution; see above).
- Tests map 1:1 to the behaviors; a property test asserts `greet(x) == "hello, " + x`.

This decision is the input to one `/to-tickets` invocation, expected to produce 1–2 Work
Units under `.scratch/software-factory/impl/` (effort slug: `greet`). It is disposable once
the smoke test passes end-to-end.