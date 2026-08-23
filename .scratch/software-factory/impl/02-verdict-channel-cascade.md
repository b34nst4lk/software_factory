---
id: impl-02
decision: 15 — deterministic verdict channel
title: 'verdict channel: file→trailer→(re-prompt once)→HUMAN_GATE + verifier trailer/re-prompt
  prompt'
scope_files:
- factory/orchestrator/cycle.py
- factory/orchestrator/tests/test_cycle.py
- factory/orchestrator/prompts.py
- factory/orchestrator/tests/test_prompts.py
acceptance:
- story: As the orchestrator, I always get a parseable routing verdict or surface
    the never-assume human gate — never a silent guess
  behaviors:
  - behavior: a verifier pane whose only signal is the trailer 'VERDICT overall=PASS'
      (no .verdict.yaml file, no fenced YAML) routes the cycle to DONE
    outcome: success
  - behavior: a verifier pane whose only signal is the trailer 'VERDICT overall=FAIL'
      routes to RETRY (empty feedback is acceptable — the trailer is routing-only)
    outcome: success
  - behavior: a verifier pane whose only signal is the trailer 'VERDICT overall=BLOCKED'
      routes to ESCALATE
    outcome: success
  - behavior: when neither the .verdict.yaml file nor the trailer yields a parseable
      verdict, the orchestrator re-prompts the verifier exactly ONCE
    outcome: success
  - behavior: a re-prompt that yields a parseable verdict (file or trailer) routes
      normally — no human gate
    outcome: success
  - behavior: a re-prompt that is STILL unparseable routes to HUMAN_GATE with the
      raw text surfaced (never-assume; no second re-prompt)
    outcome: failure
  - behavior: verifier_prompt ends by requiring the line 'VERDICT overall=PASS|FAIL|BLOCKED'
      as the verifier's LAST reply line (alongside the existing file contract)
    outcome: success
- story: As the verifier being re-prompted, I receive a strict instruction to write
    exactly the verdict file and trailer
  behaviors:
  - behavior: a new prompt template exists that tells the verifier its previous verdict
      was unparseable and instructs it to write exactly this to .verdict.yaml and
      end with 'VERDICT overall=X'
    outcome: success
verify:
- behaviors captured by tests; tests map 1:1 to acceptance.behaviors
- the re-prompt happens EXACTLY once (assert the verifier pane was prompted exactly
  one extra time after the first unparseable read), never zero, never unbounded
- 'file precedence is preserved: when .verdict.yaml is present and parseable, the
  cycle routes by the file even if the trailer is missing or garbled (existing test_verdict_file_takes_precedence_over_pane_text
  must still pass)'
- the per-cycle commit + value-only frontmatter + run.log cadence is unchanged; only
  the verdict-parse step widens
model: deepseek-v4-flash:cloud
depends_on:
- impl-01
status: done
cycle: 1
last_verdict: PASS
---
Make the verdict **channel** reliable end-to-end in the cycle loop and the verifier
prompt. Touch only `factory/orchestrator/cycle.py`,
`factory/orchestrator/tests/test_cycle.py`, `factory/orchestrator/prompts.py`, and
`factory/orchestrator/tests/test_prompts.py`. Stay strictly within these four files.

Context (decision 15 — deterministic verdict channel): the verifier is instructed
to write a `.verdict.yaml` file (raw YAML: `overall` + `gates`) and reply
`VERDICT_FILE: .verdict.yaml`, but it doesn't always (the smoke's cycle 1 wrote
nothing parseable → human gate). The verdict **content** stays LLM-generated, but
the **channel** must be reliable. This unit adds: (1) a compact one-line routing
trailer `VERDICT overall=PASS|FAIL|BLOCKED` as the verifier's LAST reply line, which
the orchestrator parses for routing even when the file is missing/malformed; (2) a
bounded re-prompt when neither file nor trailer yields a verdict; (3) the
never-assume human gate as the floor. The trailer carries ROUTING only; long
feedback/escalation text still comes from the file (best-effort). `impl-01`
already delivered `verdict.parse_trailer(text) -> Overall | None` — use it here; do
not modify verdict.py.

Behaviours to make pass (each is false at the base commit):
- a verifier pane whose only signal is the trailer 'VERDICT overall=PASS' (no
  .verdict.yaml file, no fenced YAML) routes the cycle to DONE
- a verifier pane whose only signal is the trailer 'VERDICT overall=FAIL' routes
  to RETRY (empty feedback is acceptable — the trailer is routing-only)
- a verifier pane whose only signal is the trailer 'VERDICT overall=BLOCKED' routes
  to ESCALATE
- when neither the .verdict.yaml file nor the trailer yields a parseable verdict,
  the orchestrator re-prompts the verifier exactly ONCE
- a re-prompt that yields a parseable verdict (file or trailer) routes normally —
  no human gate
- a re-prompt that is STILL unparseable routes to HUMAN_GATE with the raw text
  surfaced (never-assume; no second re-prompt)
- verifier_prompt ends by requiring the line
  'VERDICT overall=PASS|FAIL|BLOCKED' as the verifier's LAST reply line (alongside
  the existing file contract)
- a new prompt template exists that tells the verifier its previous verdict was
  unparseable and instructs it to write exactly this to .verdict.yaml and end with
  'VERDICT overall=X'

Implementation notes (you decide exact factoring, but the observable --mock
behaviour is graded):
- `cycle._parse_verdict` (or its caller in `run_cycle`) becomes the cascade
  **file → trailer → (re-prompt once) → file/trailer → HUMAN_GATE**. The re-prompt
  needs the herdr port + the verifier pane, so it is natural to drive it in
  `run_cycle` (which has both) around the existing `_parse_verdict` call: attempt
  file+trailer; if UNPARSEABLE, send the new re-prompt template to the verifier
  pane, read it again, attempt file+trailer once more; if still UNPARSEABLE, route
  to the existing human-gate path (raw text surfaced). Do NOT re-prompt more than
  once.
- When only the trailer is available (no file), build a `Verdict` with the
  `Overall` from `parse_trailer` and empty feedbacks/escalations — routing still
  works (FAIL→RETRY with the existing "verifier FAIL (no concrete feedback)"
  fallback; BLOCKED→ESCALATE with the existing "verifier BLOCKED (no reason given)"
  fallback). Do not invent feedback/escalation text from the trailer.
- Update `prompts.verifier_prompt` so it requires the trailer as the LAST line, in
  addition to (not instead of) the existing file-write + `VERDICT_FILE:` contract.
- Add a new prompt builder in `prompts.py` (e.g. `reprompt_verifier`) carrying the
  strict "your previous verdict was unparseable; write exactly this to
  .verdict.yaml and end with `VERDICT overall=X`" instruction.
- Update the existing `test_unparseable_verdict_routes_to_human_gate` so it
  explicitly feeds the re-prompt read and asserts the re-prompt was sent exactly
  once before the human gate. Add cases for: trailer-only PASS/FAIL/BLOCKED routing;
  re-prompt-then-parseable (no human gate); re-prompt-then-still-unparseable (human
  gate). The mock feeds verifier reads FIFO per pane name, so feed the original
  read then the re-prompt read for the verifier pane.

Build test-first via /skill:tdd. Write one behaviour-driven test per bullet above
and a property/fuzz-style test where it fits (e.g. for any trailer overall in
{PASS,FAIL,BLOCKED} a trailer-only pane routes to the matching outcome). Annotate
each test with the behaviour it covers (e.g.
`# maps to: trailer-only 'VERDICT overall=PASS' routes to DONE`) so coverage is
checkable. Keep the existing cycle tests green (file precedence, cross-model
binding, persistence, resume). Do not edit verdict.py or its tests (that is
impl-01's scope). Stay within scope_files.

When your work is test-green and within scope, stop and summarize what changed and
the test results.