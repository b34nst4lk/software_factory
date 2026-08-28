# 25 — two-loop architecture (inner TDD loop + final 6-gate verifier)

Type: grilling
Status: resolved
Blocked by: 14
Resolved: 2026-08-27 (grilling). Amends 05 (Q3/Q4/Q5), 06 (Q2/Q3), and 14 (Q5 supersession). Build ready (to-tickets → factory).
Found by: 14's grilling (2026-08-27). Reopens 05 (cycle/role contract).

## Question

Ticket 14 resolved *what* test-strength evidence the factory must produce and *where*
each piece lives. The mechanism for evidence (2) — "tests fail before implementation" —
is a **two-loop architecture**, recorded in 14's answer but built under this ticket
because it reopens the 05 orchestrator contract (cycle definition, agent roles, model
bindings, the 5-cycle cap relationship).

Proposed shape (from 14):

- **Inner loop** — implementer + tiny verifier in tight TDD micro-cycles: write a
  failing test → tiny verifier witnesses red (deterministic: run pytest, assert non-zero
  + parse the `# maps to:` mapping) → implementer writes until green → tiny verifier
  witnesses green (deterministic) + a light LLM vacuous-test pass (gated behind the
  audit, not every micro-cycle). The red-then-green evidence is a byproduct of the loop,
  recorded by the witness.
- **Outer loop** — the existing final 6-gate verifier reviews the inner loop's product,
  once per outer cycle, cross-model vs the implementer (see model topology below).

Settled in 14 (do not re-grill): the two-loop is the mechanism; the tiny verifier is
hybrid (deterministic red/green/mapping + gated LLM vacuous-test pass); the inner loop
is sub-cycle (no commit, no cap count, no `state.db` row); the on-demand mutation audit
is the deterministic backstop for the inner LLM's vacuous-test judgment.

Grill to settle here (the 05 amendments):

1. **Cycle definition.** 05 defines one cycle = one implementer→verifier round, counted
   against the 5-cycle cap. With the two-loop, does one *outer* cycle still = the unit
   the cap counts, and the inner loop is invisible to the cap? (14 says yes — confirm
   and write the amendment to 05.)
2. **Agent roles + panes.** The inner loop needs an implementer pane and a tiny-verifier
   pane (or the tiny verifier is orchestrator logic, not a pane, since red/green/mapping
   are deterministic and the LLM pass is gated). Decide: is the tiny verifier a herdr
   agent (pane) or orchestrator-internal? The LLM vacuous-test pass (when invoked) needs
   a model call — does it reuse the final-verifier pane, a dedicated pane, or an
   ad-hoc `pi` call?
3. **Model topology + cross-model rule** (settled in 14, recorded here for the build):
   Wayfinder `glm-5.2:cloud`; Implementer `deepseek-v4-flash:cloud` (low effort); Inner
   verifier `deepseek-v4-pro:cloud`; Final verifier `glm-5.3-flash:cloud`. Cross-model
   binds the **final** verifier (glm ≠ deepseek); the inner verifier may share the
   implementer's family (deepseek) because its vacuous-test judgment is backstopped by
   the deterministic mutation audit (14 Q5). Wire `deepseek-v4-pro:cloud` and
   `glm-5.3-flash:cloud` into `models.json` (decision-02-style); confirm effort control
   on `deepseek-v4-flash` (low) and `glm-5.3-flash` (low/high/max).
4. **The red-witness escalation path.** If the tiny verifier's red-witness finds the test
   is *green* at base (the behavior is not false at base = to-tickets wrote a bad ticket),
   that is a never-assume escalation to Wayfinder (14's resolution), not a code fix. Wire
   the escalation through 06's BLOCK→park→resume (the orchestrator already owns this).
5. **Inner-loop failure modes.** What does the inner loop do when the implementer can't
   get a test green within the micro-cycle (it loops)? Cap the inner micro-cycles; on
   cap, surface to the human (don't silently spin). Does an inner-loop stall escalate
   to Wayfinder or count against the outer cap?

Keep it a thin layer: the inner loop is TDD (reuse the `tdd` skill) + deterministic
witnessing (orchestrator/guard), not new philosophy.

## Answer

**Cycle definition (amends 05 Q3/Q4).** One **outer** cycle = (inner loop runs to
all-green across the ticket's behaviors) + (final 6-gate verifier round). The 5-cycle
backstop counts **outer** cycles only; the inner loop is invisible to the cap. One
per-cycle git commit + one `state.db` row per **outer** cycle, as today; the inner loop
commits nothing.

**Inner loop = per-behavior micro-cycles.** For each behavior `Bn` in the ticket's
`acceptance.behaviors` (the ids from 14): orchestrator prompts the implementer "write the
failing test for Bn only, stop" → orchestrator runs pytest in the worktree (subprocess)
→ witnesses red (records) → inner-verifier pane (LLM) judges the test honest → orchestrator
prompts "implement until Bn green, stop" → witnesses green → inner-verifier pane judges the
green real → next behavior.

**The deterministic witness is orchestrator subprocess** (run pytest in the worktree, read
the exit code — guaranteed). The **inner-verifier pane runs only the LLM judgment** (test
honesty / green honesty) every micro-cycle. Tests never run in a pane.

**Inner-loop stall.** **5 attempts per behavior.** On cap, a per-behavior human-gate
(`c` continue / `s` stop / `w` escalate to Wayfinder) — does **not** burn the outer 5-cycle
cap. Mirrors 05 Q3's human-gated lifecycle, scoped to the inner loop.

**Red-witness escalation (reuses 06).** A behavior's test **green at base** (not
false-at-base = to-tickets wrote a bad ticket) → never-assume escalation: author a
Wayfinder ticket, park the unit, continue independent units, resume on resolution — via
the existing `escalate.py` + park/resume. No new escalation path; a new BLOCK trigger only.

**Topology: one herdr space per work unit, 4 panes.** `workspace_create` per unit (labeled
by unit id), torn down with the worktree (today: one shared `"factory"` workspace). Four
panes:

| Pane | Model | Job |
|---|---|---|
| implementer | `deepseek-v4-flash:cloud`, low effort | writes tests + impl per micro-cycle |
| inner verifier | `deepseek-v4-pro:cloud` | LLM judgment every micro-cycle (test/green honesty) |
| final verifier | `glm-5.3-flash:cloud` | the 6-gate adversarial review, once per outer cycle |
| orchestrator output | — (shell pane, no agent) | the orchestrator logs actions via `herdr send-keys` (one-way; human reads) |

The output pane is **not** a test runner and **not** a human shell. Tests run via subprocess
(clean exit code, guaranteed); the orchestrator logs the action + result to the output pane
for the human's live view. The orchestrator's stdin gates stay on its own stdout (05 Q5
unchanged — `c`/`s`/`w`/`m`/`q`), separate from the per-unit space.

**Amends 14 (Q5 supersession).** The inner verifier LLM runs **every micro-cycle**, in the
tight loop — superseding 14's "gated behind the audit, not every micro-cycle." The
mutation audit (14 Q5) becomes an **additional deterministic backstop on top**, not the
gate for the LLM. Cost: a `deepseek-v4-pro` call per behavior per outer cycle (quota: 06
Q5's shared pool).

**Cross-model + model wiring (from 14, built here).** Cross-model binds the **final**
verifier (glm ≠ deepseek); the inner verifier may share the implementer's family (deepseek)
because its judgment is backstopped by the deterministic mutation audit. Wire
`deepseek-v4-pro:cloud` + `glm-5.3-flash:cloud` into `~/.pi/agent/models.json`
(decision-02-style). `qwen3.5:cloud` is superseded as the verifier.

**Surfacing.** Per-behavior red/green progress via `report_metadata` on the implementer +
inner-verifier panes (`$summary` = `impl-NN B2/5 red✓ implementing`). Inner loop writes no
`state.db` row. The orchestrator output pane is the detailed action log.

**Build under 25 (to-tickets units):**
- herdr port: `workspace_create` per unit; new `pane_log` verb (send-keys echo to the
  output pane); `agent_start` for 3 agent panes with the new models.
- `config.py`: `implementer_model` (deepseek-flash, low effort), `inner_verifier_model`
  (deepseek-pro), `final_verifier_model` (glm-5.3-flash); effort control.
- `prompts.py`: per-behavior write-test / implement / inner-verifier judge-red /
  judge-green templates.
- `cycle.py`: the inner loop inside the implementer step; per-behavior attempt cap (5) +
  human-gate; red-witness → escalate.
- `run.py`: space-per-unit setup, 4 panes, output-pane logging.
- `sf audit` (from 14): mutation command plumbing — built here (carries 14's test-strength
  build).
- `models.json`: add `deepseek-v4-pro:cloud` + `glm-5.3-flash:cloud`.

**Build-time facts to confirm (not decisions):** `herdr send-keys` appends lines to a raw
shell pane reliably; effort control settable on Ollama-cloud `deepseek-v4-flash` (low) and
`glm-5.3-flash` (low/high/max); herdr pane-exec not needed (tests via subprocess).

**05/06/14 amendments recorded:** 05 Q3/Q4 (cycle definition + inner loop), 05 Q5 (output
pane adds an in-space log; gates unchanged), 06 Q2/Q3 (inner-loop stall human-gate mirrors
Q3; red-witness escalation reuses Q2), 14 (inner-verifier LLM every micro-cycle,
superseding the gating).