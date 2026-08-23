# 17 — git-as-state durability: per-cycle commits must land on the impl/NN branch

Type: task
Status: resolved
Blocked by:
Found by: 07 (live smoke re-run via start-factory.sh). Adjacent to 16.

## Question

Git-as-state (05 Q2) has two halves: the **narrative** (`run.log`) and the **structural
history** (per-cycle commits on `impl/NN`). After the start-factory.sh smoke run, the
per-cycle commits were **dangling**, not on the `impl/01` branch:

```
impl-01 branch → 6a41bb5 (main HEAD; "Created from HEAD", never advanced)
dangling: 71c2d62 impl-01 c1 UNPARSEABLE
dangling: 6ef6684 impl-01 c3 PASS
worktree removed → run.log + mutated frontmatter gone with it
```

So this run's `git -C <worktree> commit` calls created commit objects but the `impl/01`
**branch ref did not advance** — the structural history was orphaned, and with the worktree
gone, the state (frontmatter `cycle`/`status`/`last_verdict`, `run.log`) was lost. The main
repo's `impl/01-greet.md` was still `cycle: 0 / status: open`. (Earlier hand-run smokes
*did* show the per-cycle commits on `impl/01`, so this is intermittent or
environment-dependent — possibly the worktree-aware Husky hook rejecting/aborting the
commit, or a detached-HEAD worktree checkout.)

This defeats the spine's reason for existing: git-as-state integrity.

## Build

1. **Diagnose**: run a live smoke and inspect mid-run — does `git -C <worktree> rev-parse
   HEAD` advance per cycle? Is the worktree on `impl/01` (attached) or detached? Does the
   worktree-aware Husky pre-commit hook pass on the implementer's commit (ruff/black/pytest
   on the worktree's orchestrator copy + the greet files; venv resolution via
   `git-common-dir`)? A hook failure aborts the commit — but here commit objects exist, so
   the likely cause is a detached HEAD or a ref-update failure.
2. **Guarantee the branch ref advances**: ensure `git worktree add -b impl/NN` checks out
   the branch (attached) and `commit_cycle`'s commit advances it; assert after each cycle
   that `impl/NN` points at the new commit.
3. **Survive worktree removal**: the `impl/NN` branch (or `archive/impl-NN`) must retain
   the per-cycle commits after the worktree is removed; the state must not live only in the
   worktree. (Connects to 16: the frontmatter/run.log are in the worktree — on `impl/NN`'s
   commits, so durable iff the branch ref advances.)

## Answer

Resolved 2026-08-23 via grilling (Wayfinder). The original "dangling-commit / ref-not-
advancing" concern is **resolved by current code** — `worktree_add` uses `git worktree add -b
impl/NN` (attached, not detached) and this run's refs advanced correctly (impl-01@280cec8,
impl-02@7d680f3). 17's center therefore shifted (this run's evidence) to **commit content**
+ the **`run.log` narrative**.

The decision (config-fork handling is **deferred** to ticket 20 — Parameterization):

1. **Ref-advance guarantee (lock it)**: add a regression assertion that after each cycle
   `impl/NN` points at the just-made commit, so a future regression to dangling commits
   fails loudly. No further ref-advance work.

2. **`run.log` → SQLite `cycle_log` DB** (replaces the tracked append-only `run.log`):
   - One DB per repo at `<repo>/.factory/state.db`. `.factory/` is **gitignored wholesale**
     (local runtime state, not git-as-state); today it holds only `state.db`.
   - One DB per repo (not per effort), with `effort` as a column, so it tracks across all
     branches/units/cycles in the project.
   - Schema (one table):
     `cycle_log(effort TEXT, unit_id TEXT, branch TEXT, cycle_no INT, verdict TEXT,
     action TEXT, commit_sha TEXT, ts TEXT)` — one row per cycle. `verdict` =
     PASS/FAIL/BLOCKED/UNPARSEABLE (frontmatter `last_verdict` parity); `action` =
     DONE/RETRY/ESCALATE/HUMAN_GATE/CAP_REACHED.
   - Create-on-open via `CREATE TABLE IF NOT EXISTS`; `PRAGMA user_version` for stepwise
     migrate-on-open (no framework yet); `PRAGMA journal_mode=WAL` for concurrent reads.
   - Orchestrator (runs at root, knows `repo_path`) computes `db_path` and **threads it
     into `run_cycle`** (like `worktree`/`issues_dir`); `state.log_cycle(...)` writes one
     row per cycle right after `commit_cycle` (so `commit_sha` is known).

3. **Discard `run.log` entirely**: delete `append_run_log`; `commit_cycle` stops force-adding
   it; the guard's `run.log` append-only rule is **removed**; `.gitignore` drops `!run.log`.
   Sweep existing `run.log` files already on `main`/branches.

4. **Explicit-path staging** (never `git add -A` / `git add .`): `commit_cycle` stages
   **exactly** `{impl-ticket} ∪ scope_files`, each by explicit path. A new file the
   implementer creates must already be named in `scope_files` (the existing `to-tickets`
   contract); a file not in `scope_files` is not committed and is a scope violation the
   verifier flags. (Root cause this run: `git add -A` swept `.verdict.yaml` and a `.venv`
   symlink that weren't effectively gitignored — `.verdict.yaml` not yet ignored, `.venv/`
     dir-pattern didn't match the symlink. Gitignore-alone is a fragile gate.)

5. **Guard rule (formalize-when-discovered)**: the Husky guard **rejects** a commit whose
   staged paths are **not** a subset of `{impl-ticket} ∪ scope_files`. Hard denylist
   regardless: `.verdict.yaml`, `.verdict.yml`, `.venv`, `*.db`, `__pycache__`. The guard
   — not gitignore — is the real gate against runtime-artifact cruft.

6. **Deferred to ticket 20 (Parameterization)**: how root-level **config** (committed vs
   gitignored, worktree inheritance) is handled is explicitly deferred and designed
   holistically for multi-repo use there. 17 introduces only the gitignored `.factory/`
   runtime-state folder + the orchestrator-threading pattern, which does not paint into a
   corner for a future committed root config.

Adjacent findings filed separately: `depends_on` doesn't propagate dependency code →
ticket 19; root-config parameterization → ticket 20.