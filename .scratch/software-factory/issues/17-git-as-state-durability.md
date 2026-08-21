# 17 — git-as-state durability: per-cycle commits must land on the impl/NN branch

Type: task
Status: open
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

<!-- filled when fixed -->