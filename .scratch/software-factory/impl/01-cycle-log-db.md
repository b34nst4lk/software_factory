---
id: impl-01
decision: "17 — git-as-state durability"
title: "SQLite cycle_log DB + threading (the cross-branch narrative)"
scope_files:
  - factory/orchestrator/state.py
  - factory/orchestrator/tests/test_state.py
  - factory/orchestrator/config.py
  - factory/orchestrator/tests/test_config.py
  - factory/orchestrator/cycle.py
  - factory/orchestrator/tests/test_cycle.py
  - factory/orchestrator/run.py
  - factory/orchestrator/tests/test_run.py
  - .gitignore
acceptance:
  - story: "As the orchestrator, I can query one per-repo DB for every cycle across all units and branches"
    behaviors:
      - { behavior: "state.open_db(path) creates <repo>/.factory/state.db with a cycle_log table (CREATE TABLE IF NOT EXISTS); idempotent (calling twice does not error or duplicate)", outcome: success }
      - { behavior: "state.open_db sets PRAGMA journal_mode=WAL and PRAGMA user_version (for future stepwise migrations)", outcome: success }
      - { behavior: "state.log_cycle writes one row with columns effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts", outcome: success }
      - { behavior: "rows for multiple efforts/units/cycles coexist in the one DB and are queryable (e.g. all cycles for a unit; every unit across branches)", outcome: success }
      - { behavior: "config.db_path defaults to <repo>/.factory/state.db", outcome: success }
      - { behavior: ".factory/ is gitignored wholesale (the DB is local runtime state, never committed)", outcome: failure }
      - { behavior: "run_cycle writes exactly one log_cycle row per cycle, after the verdict is routed, carrying verdict (PASS/FAIL/BLOCKED/UNPARSEABLE) + action (DONE/RETRY/ESCALATE/HUMAN_GATE/CAP_REACHED) + the cycle's commit_sha", outcome: success }
      - { behavior: "db_path is threaded from config into run_cycle (not hardcoded); a mock run with a temp db_path produces rows in that DB", outcome: success }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "open_db uses CREATE TABLE IF NOT EXISTS (idempotent) and sets PRAGMA user_version + WAL"
  - "log_cycle stores verdict in {PASS,FAIL,BLOCKED,UNPARSEABLE} and action in {DONE,RETRY,ESCALATE,HUMAN_GATE,CAP_REACHED}"
  - "one DB per repo; the effort column distinguishes efforts; nothing in .factory/ is ever staged (it is gitignored)"
  - "run_cycle calls log_cycle exactly once per cycle (assert the row count after a mock run)"
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
---
Add a per-repo SQLite **narrative** DB that logs one row per cycle across every unit and
branch, replacing the per-worktree `run.log` narrative (the `run.log` removal itself is a
sibling unit, impl-02; this unit only adds the DB + threads it). Touch only the files in
scope_files. Do NOT edit gitops.py, guard.py, or tickets.py (other units own those).

Context (decision 17 — git-as-state durability, resolved by grilling): git-as-state has
two halves — the structural history (per-cycle commits on `impl/NN`, owned by impl-02) and
the **narrative**. The narrative moves from a tracked, per-worktree `run.log` (which
conflicts on cross-branch merges and is lost with the worktree) to a single per-repo
SQLite DB at `<repo>/.factory/state.db`, queryable across all efforts/units/branches.

Behaviours to make pass (each is false at the base commit — no state.py exists):
- state.open_db(path) creates <repo>/.factory/state.db with a `cycle_log` table via
  CREATE TABLE IF NOT EXISTS; idempotent (calling twice does not error or duplicate the
  table). It sets PRAGMA journal_mode=WAL and PRAGMA user_version (for future stepwise
  migrations; no migration framework — just set the version).
- state.log_cycle(db_path, effort, unit_id, branch, cycle_no, verdict, action,
  commit_sha, ts) writes one row. Columns: effort TEXT, unit_id TEXT, branch TEXT,
  cycle_no INT, verdict TEXT, action TEXT, commit_sha TEXT, ts TEXT.
- Rows for multiple efforts/units/cycles coexist in the one DB and are queryable
  (e.g. all cycles for a given unit; every unit across branches; a unit's history across
  park/resume).
- config.db_path defaults to <repo>/.factory/state.db (resolve the repo root from the
  existing config; do not hardcode an absolute path).
- `.factory/` is gitignored wholesale (add it to .gitignore). The DB is local runtime
  state, never committed.
- run_cycle writes exactly one log_cycle row per cycle, AFTER the verdict is routed,
  carrying verdict (the Overall: PASS/FAIL/BLOCKED/UNPARSEABLE) and action (the
  CycleOutcome: DONE/RETRY/ESCALATE/HUMAN_GATE/CAP_REACHED) and the cycle's commit_sha.
- db_path is threaded from config into run_cycle (add it as a parameter, like worktree/
  issues_dir); a mock run with a temp db_path produces rows in that DB.

Implementation notes (you decide exact factoring, but the observable --mock behaviour is
graded):
- New module `factory/orchestrator/state.py` using only the stdlib `sqlite3` (no new
  dependency). `open_db(db_path) -> sqlite3.Connection` (CREATE TABLE IF NOT EXISTS
  cycle_log(...); PRAGMA journal_mode=WAL; PRAGMA user_version = 1). `log_cycle(...)`
  inserts one row.
- The cycle's commit_sha: the per-cycle commit is made by the `commit` callback
  (`CommitFn`) passed into run_cycle, which is `run.py`'s `_commit_fn` closure. To get
  the sha for the log row, have that closure return the commit sha (e.g. `git -C <worktree>
  rev-parse HEAD` after the commit) OR have run_cycle read it itself after the commit
  callback returns it. Choose one clean seam and thread the sha to log_cycle.
- Call log_cycle in run_cycle after routing (so the action is known), once per cycle.
  Do NOT log in the closure alone (the action is determined after routing).
- Add `db_path` to config (default `<repo>/.factory/state.db`) and thread it through
  `run_cycle`'s parameters; `run.py` passes `config.db_path`.
- Do not touch the existing `run.log`/`append_run_log` code here — impl-02 removes it.
  This unit only ADDS the DB + threading.

Build test-first via /skill:tdd. Write one behaviour-driven test per bullet (annotated
`# maps to: ...`), plus a property/fuzz-style test where it fits (e.g. for any
verdict ∈ {PASS,FAIL,BLOCKED,UNPARSEABLE} and action ∈ {DONE,RETRY,ESCALATE,HUMAN_GATE,
CAP_REACHED}, a logged row round-trips through a query). For run_cycle threading, use the
existing MockHerdr/MockGitOps patterns in test_cycle.py/test_run.py with a temp db_path
(tmp_path) and assert the row count + columns after a mock run. Keep all existing cycle
and run tests green. Stay within scope_files.

When your work is test-green and within scope, stop and summarize what changed and the
test results.