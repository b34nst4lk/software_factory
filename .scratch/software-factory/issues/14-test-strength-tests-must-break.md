# 14 — test-strength: tests must break when the behavior is wrong

Type: grilling
Status: resolved
Blocked by: 06
Resolved: 2026-08-27 (grilling). Splits off: 24 (gate-2 leniency), 25 (two-loop).
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

**In scope, and broader than enforcing 07b.** The factory must produce four pieces of
evidence a human can trust without deep review: (1) tests are *planned*, (2) tests *fail
before implementation*, (3) tests *pass only after validation*, (4) *auditable* —
fuzzing the tests or the code breaks them.

1. **Planned — formalize the test↔behavior mapping in the guard (pre-commit),
   deterministic.** Each acceptance behavior gets a stable id (`B1`, `B2`, …). Each test
   carries a `# maps to: <id>`. A new third guard rule asserts: every behavior has ≥1
   mapped test; every `# maps to:` cites a real id; every test function has a `# maps to:`.
   **One test → one behavior** (a multi-behavior test is flagged for the verifier to
   judge, not auto-rejected). This formalizes gate 6 (a)/(b); the verifier keeps only the
   *honesty* judgment (is the mapping gamed). to-tickets authors the behavior id up front
   (a value, so the value-only guard still holds).

2. **Failing-before-implementation — produced by the two-loop, not a one-shot check.**
   An **inner loop**: implementer + tiny verifier in tight TDD micro-cycles (write a
   failing test → tiny verifier witnesses red → write until green → tiny verifier
   witnesses green). The red-then-green evidence is a byproduct of the loop, recorded by
   the witness — not a separate orchestrator step. The two-loop is its own decision ticket
   (25); 14 records the decision, 25 grills the cycle/role mechanics and drives the build.

3. **Passing-after-validation — already the pre-commit hook** (pytest green + coverage
   ≥90 + mypy). At the strong end it *is* the audit (below).

4. **Auditable — on-demand mutation audit.** An `sf audit` command runs mutation testing
   (mutmut, or a small custom mutator) over a unit's `scope_files`, writes a report to
   the narrative + sidebar, and routes surviving mutants to the implementer as a fix
   cycle. Out of the per-cycle hot path. Promote to the PR gate once proven and fast
   enough.

**Tiny verifier is hybrid.** Deterministic for red/green witness + mapping parse
(always-on, cheap); a light LLM pass only for the one judgment deterministic can't catch
— *is the test vacuous*. ~~The LLM pass is gated behind the audit, not every micro-cycle.~~
**[Superseded by 25 (2026-08-27):** the inner verifier LLM now runs **every micro-cycle**,
in the tight per-behavior loop — see 25. The mutation audit becomes an additional
deterministic backstop on top, not the gate for the LLM.**]

**Inner loop is sub-cycle.** No commit, no count against the 5-cycle cap, no `state.db`
row. It is the implementer's TDD workflow. Recording micro-steps to `state.db` is fog.

**Model topology (amends the standing cross-model rule):**

| Role | Model |
|---|---|
| Wayfinder | glm-5.2:cloud |
| Implementer | deepseek-v4-flash:cloud, low effort |
| Inner verifier | deepseek-v4-pro:cloud |
| Final verifier | glm-5.3-flash:cloud |

**Cross-model rule amended:** it binds the **final (primary adversarial) verifier** to a
different family from the implementer. The **inner teeth-check verifier** may share the
implementer's family, because its judgment is backstopped by the **deterministic
mutation audit** (formalize-when-discovered: an LLM judgment with a deterministic
backstop). The final verifier (glm) and Wayfinder (glm) share a family — accepted; the
Wayfinder is human-in-loop, its model is the interview not solo judgment, and the rule
never bound it.

**Build-time facts (raise at to-tickets, not decisions):** confirm effort control is
settable on Ollama-cloud `deepseek-v4-flash` ("low effort") and `glm-5.3-flash`
(low/high/max); wire both new models (`deepseek-v4-pro:cloud`, `glm-5.3-flash:cloud`)
into `models.json` (decision-02-style). Quota: 06 Q5's shared-quota pause still governs.

**Split off:** the gate-2 never-assume *leniency* finding (verifier rationalizing the
`parse_trailer` duplication to PASS instead of BLOCKing) becomes its own grilling ticket
(24) — it is a verifier-prompt/judgment defect, not a test-strength defect. The 15-build
weak `assume()` in `test_verdict.py:280` is an example of the test-strength gap this
ticket addresses (the audit catches it).