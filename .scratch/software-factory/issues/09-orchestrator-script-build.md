# 09 — Orchestrator script build (07c)

Type: task
Status: open
Blocked by: 05, 06, 07a (HITL prereqs done), 07b (factory-to-tickets skill built)
Realizes: the 05 (orchestrator contract) + 06 (feedback & escalation protocol) decisions.
Umbrella: ticket 07 (prototype end-to-end build + smoke test). This is its 07c sub-step.

## Goal

Build the **deterministic orchestrator** (python3, no LLM) — the thin spine that drives
implementer (deepseek-v4-flash:cloud) + verifier (qwen3.5:cloud) as pi agents in herdr
panes, owns the cycle counter + git-as-state + verdict routing + escalation/PR/failover,
and surfaces to the human via herdr's sidebar + minimal stdin gates. Source of truth for
every contract decision: [05](05-orchestrator-script-contract.md) and
[06](06-feedback-and-escalation-protocol.md) — read them in full before building; this
ticket is a distillation, they are the spec.

## What to build

Code lives in `factory/orchestrator/` (replace the placeholder README). Proposed module
layout (refine if a cleaner seam appears, but keep the state-machine seam isolated —
05 Q1 notes a possible future Gleam rewrite):

```
factory/orchestrator/
  __init__.py
  cli.py          # entrypoint; args: effort dir / impl glob, --cycle-cap (default 5),
                  #   --no-approve, --mock (herdr/gh stubs for tests), --pr-stage on|off
  config.py       # model ids, timeouts, reviewer logins (sourcery_reviewer_login,
                  #   human login), poll cadences, paths
  herdr.py        # subprocess wrapper: agent start --kind pi --pane -- <args>,
                  #   agent prompt --wait --until done|blocked, agent read
                  #   --source recent-unwrapped --lines N, agent wait, pane split,
                  #   workspace/tab create, pane report-metadata (--token summary=...)
  tickets.py      # parse impl frontmatter (pyyaml); topo-sort by depends_on;
                  #   write/append run.log; parse an escalation ticket's ## Answer
  guard.py        # the value-only + append-only guard util (see Invariants)
  verdict.py      # extract fenced YAML verdict block (regex), parse, route
                  #   PASS/FAIL/BLOCKED; never-assume on unparseable -> human gate
  prompts.py      # implementer + verifier prompt templates (embed /skill:tdd,
                  #   /skill:code-review, 6-gate instructions + fenced-YAML verdict
                  #   instruction; resolution-injection block; cycle/worktree context)
  cycle.py        # the per-unit cycle loop: implementer <-> verifier strictly
                  #   alternating; 5-cycle backstop; commit per cycle
  escalate.py     # write templated Wayfinder ticket; park unit; file-driven resume
                  #   scan; resolved-answer re-injection into both prompts
  pr.py           # gh pr create; poll gh api .../pulls/N/reviews; merge gate
                  #   (human APPROVED + Sourcery clean + no CHANGES_REQUESTED);
                  #   comment routing; dismissal posting (gh pr comment)
  failover.py     # 3-retry exponential backoff (5/15/45s); on persistent/quota
                  #   exhaustion pause the WHOLE orchestrator; stdin (r)etry/(q)uit
  run.py          # main loop: glob impl -> topo -> worktree per unit -> cycle ->
                  #   pipeline across units; stdin gates c/s/w/m/q; sidebar
                  #   report-metadata per cycle
  hooks/pre-commit # Husky hook: guard util + ruff + black + pytest + mypy + coverage.py
  pyproject.toml  # ruff/black/pytest/mypy/coverage config + project metadata
  README.md       # replace placeholder: how to run, the invariants, the gates
```

## The contract (distilled — 05 + 06 are authoritative)

### State & storage (05 Q2) — git-as-state
- Per work unit → its own git worktree on branch `impl/NN` (`git worktree add ../sf-impl-NN -b impl/NN` from main). Isolated checkout eliminates the shared-checkout collision 03 flagged; unlocks pipelining.
- Per cycle → ONE commit on `impl/NN` = implementer code change + impl frontmatter **value-only** updates (`status`, `cycle`, `last_verdict`) + appended `run.log` lines.
- No `run.json` / run-state file. Current state = impl frontmatter; history = `run.log` (narrative) + git log (structural).
- Husky pre-commit hook (repo-wide, active in worktrees) runs: (1) **guard util** — impl frontmatter changes are **value-only** (key set unchanged, prose body unchanged) AND `run.log` is **append-only** (no `-` lines); (2) ruff + black on staged `.py`; (3) pytest; (4) **mypy/pyright** type check; (5) **coverage.py** threshold-enforced. (05 Q2 + 06 Q7 formalize-when-discovered.)
- 04 schema already authors all frontmatter keys up front with defaults (`status: open`, `cycle: 0`, `last_verdict: ""`) so orchestrator mutations stay strictly value-only. The guard util enforces it.

### Main loop & concurrency (05 Q4)
- glob impl files → parse frontmatter → topo-sort by `depends_on` → for each ready unit `git worktree add` → cycle loop → on done leave branch for pre-merge.
- **Pipelined** (Q4a): next unit starts when the current reaches `done` (verifier-passed), not after merge — several `impl/NN` branches may be open awaiting human review; implementer stays busy while the human reviews.
- **Conversation within a unit** (Q4b): one implementer ↔ one verifier strictly alternating, never parallel. Parallelism is only across work-unit pairs, each its own worktree.

### Cycle loop (05 Q3, Q4)
- Implementer pane: `herdr agent start impl-NN --kind pi --pane P -- --model deepseek-v4-flash:cloud`; prompt = wrapper (cycle N, worktree path, resolution injection if resuming) + impl ticket body (which itself embeds `/skill:tdd`); `--wait --until done`; `agent read --source recent-unwrapped`.
- Verifier pane: `herdr agent start ver-NN --kind pi --pane Q -- --model qwen3.5:cloud`; prompt = implementer output + `verify` criteria + the 6-gate instructions + "end with a fenced YAML verdict block"; `--wait --until done|blocked`; `agent read`.
- Verdict routing (06 Q1): parse fenced YAML; `overall: PASS` → `done` → raise PR; any `FAIL` → collect that gate's `feedback` → next implementer cycle; any `BLOCKED` → escalate (below). **Never-assume on parse failure**: missing/unparseable YAML → human gate ("verifier verdict unparseable"), halt. (Not JSON — YAML, for consistency with frontmatter.)
- Every `impl/NN` commit is **unit-green + quality-clean + state-guarded** regardless of verdict (05 Q2-B): implementer lands green before handing to verifier; a verifier-FAIL cycle still commits as long as unit tests are green. Unit-test green ≠ verifier-pass.
- **5-cycle backstop** (05 Q3): after every cycle render the per-unit lifecycle (each cycle's implementer attempt + tests-green + verifier verdict) and gate the human (continue/stop/escalate); a high default ceiling of 5 forces a human surface if unattended, overridable once the human is looking.

### Verifier = 6 gates (05 verifier + 06 Q6)
(1) meets the requirement [the acceptance behaviours]; (2) requirement contradictions/callouts → escalate (the never-assumes trigger); (3) over-engineering; (4) coding convention; (5) `/skill:code-review` against the diff; (6) **behavior coverage** — (a) behaviours captured via fuzzing/hypothesis, (b) tests map back to behaviours. Per-gate verdict {PASS | FAIL-with-fix | BLOCKED-with-escalation} + `overall`. Gate 5 is the existing `code-review` skill invoked in-pane; gate 2 is the dedicated contradictions gate but ANY gate may return BLOCKED.

### Escalation (06 Q2, Q3)
- On any BLOCKED: (1) **create** a templated Wayfinder ticket at `.scratch/<effort>/issues/NN-<slug>.md`, `Type: grilling` (human-gated; wayfinder may reclassify to research), with escalation reason + context (unit id, gate, verdict, ambiguity) — **no LLM**, the orchestrator authors the stub. (2) **park, not halt** — pause that unit's cycle loop, leave its panes idle (preserve context), continue independent units (dependents stall by topo). (3) **file-driven resume** — each loop iteration re-scan parked units' tickets; when one flips to `Status: resolved` + `## Answer`, resume (no keystroke). (4) notify: sidebar `$summary` `impl-NN BLOCKED → escalated to <id>` + one-time stdout. Idle panes stay sidebar-attachable (`herdr agent attach`).
- **Re-injection**: read the ticket's `## Answer` (deterministic markdown parse), prepend a `Resolution (ticket <id>): <answer>` block to BOTH implementer and verifier prompts (verbatim); hold in memory + append a "resolution received" line to `run.log` — **no new frontmatter key** (guard forbids it). Multi/stacked escalations: a unit resumes only when ALL its open escalation tickets resolve, all injected. If a resolution cancels the unit, mark cancelled and move on (don't re-slice — wayfinder + to-tickets' job).

### PR stage (05 Q6, 06 Q4)
- All-6-gates-pass → `done` → push `impl/NN` + `gh pr create` once; only fix commits pushed after.
- Poll `gh api .../pulls/N/reviews` (~60s). Merge gate = human `APPROVED` + Sourcery clean + no `CHANGES_REQUESTED` from either → `gh pr merge --squash` → full-suite smoke on main → `git worktree remove`; branch tagged `archive/impl-NN`.
- Request-changes (Sourcery or human) → route comments to implementer as a fix cycle; implementer fix-cycle output is **structured YAML** per comment `{addressed | dismissed, reason}` (06 Q4-dismissal): `addressed` → commit → **in-pane 6-gate verifier re-runs** (invariant: every PR push is 6-gate-green) → push; `dismissed` → post the reason as a PR reply, no push. `COMMENTED` suggestions are advisory (don't block). Sourcery ~10min timeout → surface to human; no human timeout. PR-stage backstop = the human.

### Model failover (06 Q5)
- Distinguish model-call failure (herdr error / exit 1 / pane not responding) from verifier BLOCKED (model ran, flagged ambiguity). Transient: 3 retries, exponential backoff 5s→15s→45s. Quota exhaustion (Ollama quota is **shared across all models** → swapping pointless) → after 3 retries **pause the WHOLE orchestrator**, panes idle, stdin gate `(r)etry/(q)uit`, human resumes with `r` (probe quota, resume or re-pause). Logged to `run.log`.

### Human-surfacing (05 Q5) — thin layer, no custom TUI
- herdr sidebar = the live view. Orchestrator pushes per-cycle facts via `herdr pane report-metadata <pane> --token summary="impl-NN cN <verdict>"` (renders as `$summary`).
- Orchestrator stdout/stdin = **gates only**: minimal plain-text prompts `c`=continue / `s`=stop / `w`=escalate-to-wayfinder / `m`=merge / `q`=quit, blocking on stdin, + a one-line queue print (topo / awaiting-merge). No textual/rich live panel — herdr is the live panel.

### Skills reuse (05 Q7)
- Prompt templates embed `/skill:name` tokens: implementer `/skill:tdd`, verifier gate-5 `/skill:code-review`. `enableSkillCommands` defaults to true, so worker panes get the commands; the orchestrator stays skill-agnostic and model-agnostic (embeds the tokens, doesn't interpret them). Worker panes are pi sessions in worktrees (which inherit the repo's committed `.pi/settings.json`), so global mattpocock skills (tdd, code-review) are available.

## Invariants the spine must guarantee (the reason it exists — 05 "orchestrator necessity")
- cycle counting + 5-cycle backstop
- cross-model binding every cycle (implementer ≠ verifier)
- verdict routing by tag (PASS/FAIL/BLOCKED), never-assume on parse failure
- git-as-state integrity: per-cycle commit + value-only frontmatter + append-only run.log (guard util)
- queue topo-sort + worktree lifecycle + pipelining (no intra-unit parallel)
- park-not-halt on escalation; file-driven resume; verbatim answer re-injection
- every PR push is 6-gate-verifier-green
- model failover: 3 retries then whole-orchestrator pause

## Acceptance / verify (07c = code + mocked tests; the live run is 07d)
- [ ] Unit tests pass for: frontmatter parse; **guard util** (value-only + append-only, rejects key-add/body-edit/deletion); topo-sort (incl. cycles→error); verdict parse+route (PASS→done / FAIL→feedback / BLOCKED→escalate / unparseable→human-gate); escalation ticket authoring + `## Answer` re-injection parsing; PR merge-gate logic from a fixture of reviews (APPROVED+clean→merge; CHANGES_REQUESTED→route; COMMENTED→advisory); dismissal routing; failover retry/backoff/pause.
- [ ] `herdr.py` and `pr.py` are thin subprocess wrappers with a **`--mock` mode** (deterministic stubs) so the cycle loop + PR loop are exercised in tests without live herdr/panes/gh.
- [ ] An integration test drives one fixture impl unit through the full cycle loop in `--mock` mode: implementer→verifier→PASS→done, and a second fixture through FAIL→retry→PASS, and a third through BLOCKED→escalate→(resolve ticket file)→resume→PASS.
- [ ] The Husky `pre-commit` hook is installed in the repo and runs guard + ruff + black + pytest + mypy + coverage; a commit that adds a frontmatter key OR deletes a run.log line is REJECTED.
- [ ] `pyproject.toml` configures ruff/black/pytest/mypy/coverage; `ruff check`, `black --check`, `pytest`, `mypy`, and coverage threshold all pass on the orchestrator package itself (dogfood the formalize-when-discovered pre-commit on the orchestrator's own code).
- [ ] README.md documents: how to run, the invariants, the 6 gates, the stdin gates, the `--mock` mode, and the deferred live pieces.

## Out of scope for 07c (deferred)
- **The live end-to-end smoke run** = ticket 07 / 07d (real herdr panes + real models + the injected `greet(None)` escalation round-trip on decision 08).
- **Live GitHub + Sourcery wiring** (05 Q6 build prereqs: GitHub remote, `gh` CLI auth, Sourcery GitHub App) — `pr.py` is built with a mockable `gh` and exercised in `--mock`; the live PR/Sourcery round-trip is deferred to 07d or a follow-up. **Open decision for 07d**: the trivial greet smoke test may run with `--pr-stage off` (no real GitHub PR for a throwaway) — confirm at 07d.
- **Parameterization** (per-repo tracker path, model bindings, repo path as config) — far fog; only after the prototype shape is fixed.

## Pointers
- 05 contract: [05-orchestrator-script-contract.md](05-orchestrator-script-contract.md)
- 06 protocol: [06-feedback-and-escalation-protocol.md](06-feedback-and-escalation-protocol.md)
- 04 impl-ticket schema (the frontmatter the orchestrator reads/mutates): [04-to-tickets-skill-design.md](04-to-tickets-skill-design.md)
- herdr driver pattern (Pattern A verbs): [03](03-herdr-pi-driver-pattern.md) + [research/03](../research/03-herdr-pi-driver-pattern.md)
- Gleam-rewrite seam note: [research/05a-gleam-viability.md](../research/05a-gleam-viability.md)
- The skill that produces impl tickets: `factory/skills/to-tickets/SKILL.md` (built 07b)
- Smoke-test input decision: [08-smoke-greet-decision.md](08-smoke-greet-decision.md)

## Answer
<!-- filled when 07c is built and its acceptance checks pass -->