---
id: impl-02
decision: "17 — git-as-state durability"
title: "governed per-cycle commit (explicit staging) + discard run.log + ref-advance assert"
scope_files:
  - factory/orchestrator/gitops.py
  - factory/orchestrator/tests/test_gitops.py
  - factory/orchestrator/cycle.py
  - factory/orchestrator/tests/test_cycle.py
  - factory/orchestrator/run.py
  - factory/orchestrator/tests/test_run.py
  - factory/orchestrator/tickets.py
  - factory/orchestrator/tests/test_tickets.py
  - .gitignore
acceptance:
  - story: "As the orchestrator, a per-cycle commit contains exactly the governed set and the impl/NN ref advances"
    behaviors:
      - { behavior: "commit_cycle stages exactly {impl-ticket} ∪ scope_files, each by explicit `git add -- <path>`; it never uses `git add -A` or `git add .`", outcome: success }
      - { behavior: "commit_cycle does NOT stage run.log (no `git add -f run.log`)", outcome: success }
      - { behavior: "a runtime artifact (e.g. .verdict.yaml, a .venv symlink) present in the worktree is NOT staged by commit_cycle", outcome: failure }
      - { behavior: "commit_cycle returns the commit sha (so it can be logged and asserted)", outcome: success }
      - { behavior: "after each cycle, impl/NN points at the just-made commit (ref-advance assert; fails loudly if the ref did not advance)", outcome: success }
  - story: "As the orchestrator, the tracked run.log narrative is discarded (the SQLite DB is the narrative now)"
    behaviors:
      - { behavior: "tickets.append_run_log is deleted; the function no longer exists", outcome: failure }
      - { behavior: "run_cycle and run._resume no longer call append_run_log (the calls are removed)", outcome: success }
      - { behavior: ".gitignore drops the `!run.log` re-include (run.log is no longer tracked); run.log is untracked on this branch (git rm --cached run.log)", outcome: success }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "commit_cycle's staging is explicit per-file: assert the git argv contains `git add -- <governed paths>` and never `git add -A`/`git add .`/`git add -f run.log`"
  - "ref-advance assert: after commit_cycle, `git -C <worktree> rev-parse <branch>` == `git -C <worktree> rev-parse HEAD`; a regression to dangling commits fails the assert"
  - "impl-01's log_cycle is still called once per cycle (impl-01 added it); this unit keeps that call and feeds it the returned sha"
  - "the existing cycle/run/gitops/tickets tests are updated for the removed append_run_log + the new commit_cycle signature and stay green"
model: deepseek-v4-flash:cloud
depends_on:
  - impl-01
status: open
cycle: 0
last_verdict: ""
---
Make the per-cycle **commit** durable and governed, and discard the tracked `run.log`
narrative (the SQLite DB from impl-01 is the narrative now). Touch only the files in
scope_files. Do NOT edit state.py or guard.py (impl-01 owns state.py; impl-03 owns the
guard rule). impl-01 has already added the `state.log_cycle` call in run_cycle and
threaded `db_path`; this unit changes the commit path that feeds it.

Context (decision 17 — git-as-state durability, resolved by grilling): the root cause this
decision fixes — `commit_cycle` did `git add -A` of the worktree root, which swept runtime
artifacts (`.verdict.yaml`, a `.venv` symlink that wasn't effectively gitignored) into
per-cycle commits, causing merge conflicts and (2026-08-23) a broken circular-symlink
venv on main. Gitignore-alone is a fragile gate. The fix: stage **exactly** the governed
set by explicit path, drop the `run.log` narrative (now in the SQLite DB), and assert the
`impl/NN` ref advances each cycle.

Behaviours to make pass (each is false at the base commit — commit_cycle uses `git add
-A` + `git add -f run.log`, append_run_log exists, no ref-advance assert):
- commit_cycle stages exactly `{impl-ticket} ∪ scope_files`, each by explicit
  `git add -- <path>`. It NEVER uses `git add -A`, `git add .`, or `git add -f run.log`.
- commit_cycle does NOT stage run.log (remove the `git add -f run.log` line).
- A runtime artifact (e.g. `.verdict.yaml`, a `.venv` symlink) left in the worktree is
  NOT staged by commit_cycle (it's not in the governed set).
- commit_cycle returns the commit sha (e.g. `git -C <worktree> rev-parse HEAD` after
  the commit), so it can be logged by impl-01's log_cycle and asserted.
- After each cycle, `impl/NN` points at the just-made commit. Add a ref-advance assert
  that fails loudly if the branch ref did not advance (e.g. compare
  `git rev-parse <branch>` to `git rev-parse HEAD` after the commit). This locks the
  guarantee verified during the 15 build (refs advanced correctly) against a future
  regression to dangling commits.
- `tickets.append_run_log` is DELETED; the function no longer exists.
- `run_cycle` and `run._resume` no longer call `append_run_log` (remove the calls).
- `.gitignore` drops the `!run.log` re-include (run.log is no longer tracked). Untrack
  run.log on this branch: `git rm --cached run.log` (so it propagates to main on merge).

Implementation notes (you decide exact factoring, observable --mock behaviour is graded):
- `gitops.commit_cycle(worktree, message, *, impl_ticket, scope_files) -> str` (returns
  sha). Stage explicitly: `git -C <worktree> add -- <impl_ticket> <scope_file1> ...` (one
  `git add --` with all governed paths, or one per path — your call, but never `-A`/`.`).
  Then `git -C <worktree> commit -m <message>`; then `git -C <worktree> rev-parse HEAD`
  for the sha. Keep MockGitOps in step (record the sha).
- The commit callback (`run.py`'s `_commit_fn` closure) must supply `impl_ticket` +
  `scope_files` to commit_cycle and propagate the returned sha (impl-01's log_cycle
  needs it). `cycle.py`'s `CommitFn` signature may stay `(unit_id, cycle, overall,
  worktree)` if the closure captures the unit's `path`/`scope_files`; or widen it — your
  call, but keep the change minimal and the cycle tests green.
- The ref-advance assert: add it where the per-cycle commit is driven (the closure or
  run_cycle), comparing the branch ref to HEAD after commit. Use a real `git rev-parse`
  in the real GitOps and a stubbed/equivalent check in MockGitOps so --mock tests stay
  deterministic.
- Remove `append_run_log` calls from `cycle.run_cycle` and `run._resume`, then delete
  `tickets.append_run_log` (and its test). Update any test that relied on run.log.
- `.gitignore`: remove the `# run.log is tracked state ...` comment + the `!run.log`
  line. Keep `*.log`. Then `git rm --cached run.log` (untrack it on this branch).

Build test-first via /skill:tdd. One behaviour-driven test per bullet, annotated
`# maps to: ...`. For commit_cycle staging, assert the recorded git argv contains
explicit governed paths and never `git add -A`/`.`/`-f run.log` (use a recording fake
runner like the existing gitops tests). For the ref-advance assert, test the success case
and a forced non-advance (e.g. a mock that returns a stale sha) failing loudly. Keep
impl-01's log_cycle call working (feed it the returned sha). Stay within scope_files.

When your work is test-green and within scope, stop and summarize what changed and the
test results.