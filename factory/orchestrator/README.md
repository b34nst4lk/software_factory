# sf-orchestrator

The deterministic (no-LLM) spine of the software factory. It reads implementation
tickets produced by `factory-to-tickets`, drives an **implementer**
(`deepseek-v4-flash:cloud`) and a **verifier** (`qwen3.5:cloud`) as pi agents in
herdr panes, owns the cycle counter + git-as-state + verdict routing + escalation /
PR / failover, and surfaces to the human via herdr's sidebar + minimal stdin gates.

The orchestrator is the thin spine precisely because it is the only component that can
**guarantee** the invariants an LLM cannot hold reliably (05 — orchestrator necessity).

## Run

The one-command launcher is `start-factory.sh` at the repo root. The intended
topology is **one herdr session**: your wayfinder pi (glm-5.2) runs there, you split a
pane and run the launcher in it, and the orchestrator creates the implementer/verifier
panes as siblings in the **same** session — all visible in one herdr UI.

```bash
# toolchain (one-time)
python3 -m venv .venv && .venv/bin/pip install ruff black pytest mypy coverage pyyaml hypothesis types-PyYAML

# one-session flow (recommended):
herdr --session factory                          # terminal A: your wayfinder pi (glm-5.2)
#   inside that session, split a pane and run:
./start-factory.sh software-factory --session factory   # orchestrator runs here (stdin gates live)
herdr session attach factory                     # (another terminal) watch the sidebar + impl/ver panes

# the launcher reuses an existing herdr server for the session if one is running;
# otherwise it starts a fresh headless one (and stops it on exit). --mock = dry run.
./start-factory.sh --mock                         # deterministic stubs, no herdr/models
./start-factory.sh --help                         # full runbook

# tests + toolchain gate
.venv/bin/python -m pytest tests/
.venv/bin/ruff check . && .venv/bin/black --check . && .venv/bin/mypy
.venv/bin/coverage run -m pytest tests/ && .venv/bin/coverage report --fail-under=90
```

The launcher is a thin wrapper over the CLI entrypoint (`python -m cli`). CLI flags:
`<effort>` (slug under `.scratch/`), optional `impl-glob`
(default `.scratch/<effort>/impl/*.md`), `--cycle-cap` (default 5), `--no-approve`
(skip pi's interactive trust prompt), `--mock` (herdr/gh/gitops stubs),
`--pr-stage on|off`, `--repo`, `--gh-repo O/R`, `--worktree-parent`, `--herdr-session`,
`--implementer-env-hint`. The launcher passes the common ones; use the CLI directly for
the rest.

**Prereqs**: impl tickets at `.scratch/<effort>/impl/*.md` produced by
`/skill:factory-to-tickets <decision>` (and committed to `main`, since worktrees branch
from `main`); herdr + `herdr integration install pi`; the three cloud models in
`~/.pi/agent/models.json`.

## The invariants the spine guarantees (05, ticket 09)

- **Cycle counting + 5-cycle backstop** — one implementer→verifier round = one cycle;
  after the cap the orchestrator surfaces the per-unit lifecycle and gates the human
  (`c` lifts the ceiling once, `q` cancels, `w` escalates).
- **Cross-model binding every cycle** — implementer `deepseek-*` ≠ verifier `qwen-*`
  (config); the orchestrator binds a model per pane at `agent start`.
- **Verdict routing by tag, never-assume** — fenced-YAML `overall: PASS|FAIL|BLOCKED`;
  any gate `BLOCKED` → escalate; `FAIL` → retry with feedback; missing/unparseable →
  **human gate** (the orchestrator does not guess).
- **Git-as-state integrity** — per cycle one commit on `impl/NN` = code + **value-only**
  frontmatter update (`status`/`cycle`/`last_verdict` only) + **append-only** `run.log`.
  The Husky `pre-commit` guard util enforces both (rejects key-add, body-edit, run.log
  deletion).
- **Queue topo-sort + worktree lifecycle + pipelining** — Kahn topo-sort by
  `depends_on` (cycle → error); one worktree per unit; next unit starts when the current
  reaches `done` (not after merge), so several `impl/NN` branches may await human review
  while the implementer stays busy. No intra-unit parallel.
- **Park-not-halt on escalation; file-driven resume; verbatim re-injection** — on BLOCKED
  the orchestrator authors a grilling Wayfinder ticket, parks the unit (panes idle,
  sidebar-attachable), and continues independent units. Each loop it re-scans parked
  units' tickets; when all resolve (`Status: resolved` + `## Answer`) it resumes,
  prepending a `Resolution (ticket <id>): <answer>` block to **both** prompts verbatim.
- **Every PR push is 6-gate-verifier-green** — request-changes routes back to the
  implementer as a fix cycle; an `addressed` comment commits + re-runs the in-pane
  6-gate verifier before push.
- **Model failover: 3 retries then whole-orchestrator pause** — transient model-call
  failures retry with exponential backoff (5/15/45s); on persistent / quota exhaustion
  (Ollama quota is shared across all models → swapping pointless) the whole
  orchestrator pauses with a stdin gate `(r)etry / (q)uit`.

## The 6 verifier gates (05 verifier, 06 Q6)

1. meets the requirement (the acceptance behaviours)
2. requirement contradictions / callouts — **escalate if ambiguous (never assume)**
3. over-engineering
4. coding convention (non-automatable parts; ruff/black handle the rest)
5. code review via `/skill:code-review` against the diff
6. behavior coverage — behaviors captured via fuzzing/hypothesis; tests map to behaviors

Per-gate verdict `{PASS | FAIL-with-fix | BLOCKED-with-escalation}` + `overall`.

## stdin gates (05 Q5 — herdr is the live UI; stdout/stdin = gates only)

The orchestrator prints a one-line queue print (topo / awaiting-merge) and blocks on
stdin: `c` continue / `s` stop / `w` escalate-to-wayfinder / `m` merge / `q` quit. Per
cycle it pushes `herdr pane report-metadata <pane> --token summary="impl-NN cN <verdict>"`
so the herdr sidebar shows the live state. No custom TUI.

## `--mock` mode

`herdr.py` / `pr.py` / `gitops.py` are thin subprocess wrappers with deterministic stub
counterparts (`MockHerdr`, `MockGh`, `MockGitOps`) selected by `make_herdr/mock=True` etc.
The cycle loop, PR stage, escalation/resume, and stdin gates are exercised in
`tests/test_integration.py` and `tests/test_run.py` entirely in `--mock` — no live herdr
panes, models, git, or GitHub.

## Formalize-when-discovered pre-commit (06 Q7)

The Husky `pre-commit` hook (`.husky/pre-commit`) runs, on every commit, repo-wide and in
worktrees:

1. **guard util** (`guard.py`) — value-only frontmatter + append-only `run.log`;
2. **ruff** + **black** on the orchestrator package;
3. **pytest** under **coverage.py** (threshold `--fail-under=90`);
4. **mypy** strict.

Programmatic checks (type / format / test / coverage) live in the deterministic
pre-commit, not the LLM verifier; the verifier only judges. The orchestrator dogfoods
this hook on its own code.

## Module layout

```
config.py     model ids, timeouts, reviewer logins, paths, cycle cap
guard.py      value-only frontmatter + append-only run.log guard util (+ pre-commit CLI)
verdict.py    fenced-YAML verdict extract/parse/route (never-assume human gate)
tickets.py    impl frontmatter parse, topo-sort, ## Answer parse, value-only writer
herdr.py      herdr subprocess wrapper (Pattern A) + MockHerdr
pr.py         gh wrapper + merge-gate logic + dismissal routing + MockGh
gitops.py     worktree lifecycle + per-cycle commit + push/archive (real + mock) [seam]
prompts.py    implementer / verifier / PR-fix templates (embed /skill:tdd, /skill:code-review)
cycle.py      per-unit implementer↔verifier loop, 5-cycle backstop, guarded commit
escalate.py   templated Wayfinder ticket, file-driven resume, verbatim re-injection
failover.py   3-retry backoff + whole-orchestrator pause gate
run.py        main loop, pipelining, PR stage, stdin gates, sidebar
cli.py        argparse entrypoint
```

The git boundary (`gitops.py`) and the herdr/gh boundaries are isolated seams so the
deterministic state machine can be rewritten (e.g. a future Gleam rewrite per 05 Q1)
without touching the subprocess adapters.

## Deferred (out of scope for 07c — live run is 07d)

- The **live end-to-end smoke** (real herdr panes + real cloud models + the injected
  `greet(None)` escalation round-trip on decision 08) — ticket 07 / 07d.
- **Live GitHub + Sourcery** — `pr.py` is built with a mockable `gh` and exercised in
  `--mock`; the live PR/Sourcery round-trip (GitHub remote, `gh` auth, Sourcery App) is
  07d. The trivial greet smoke may run with `--pr-stage off`.
- **Parameterization** (per-repo tracker path, model bindings, repo path as config) —
  far fog; only after the prototype shape is fixed.