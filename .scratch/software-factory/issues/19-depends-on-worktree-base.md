# 19 — depends_on doesn't propagate dependency code to a dependent's worktree

Type: task
Status: resolved
Blocked by:
Found by: 15 build (dogfood). Adjacent to 16/17.
Resolved: 2026-08-27 (grilling). No code fix — constraint only (Q2a).

## Question

`gitops.worktree_add` creates every unit's worktree by `git worktree add <path> -b
<branch>` — branching from `main`'s current HEAD, **regardless of `depends_on`**. So a
dependent unit's worktree contains the code as it was on `main` *before* its dependency
was merged. The dependent never sees its dependency's code.

Concretely (decision 15 build): `impl-02` `depends_on` `impl-01`, but `impl-02`'s worktree
branched from `main` (which lacked `impl-01`'s `verdict.parse_trailer`, since `impl-01`
was only on its unmerged `impl-01` branch). So the `impl-02` implementer **duplicated**
`parse_trailer` as a local `_parse_trailer` in `cycle.py` (with an honest comment:
"Mirrors impl-01's verdict.parse_trailer contract, which is not present on this branch")
instead of reusing `verdict.parse_trailer`. The duplication was only reconciled at merge
time (the factory resolved the merge conflict and swapped to `verdict.parse_trailer`).

This is the deeper reason a dependent unit can't be built on its dependency's actual API:
the dependency's code isn't in the dependent's worktree. It also pushes implementers to
duplicate code, which the verifier then has to catch (in the 15 build the verifier
*rationalized* the duplication to PASS instead of BLOCKing — see ticket 14).

## Build (to settle)

Two candidate fixes (pick or combine):

1. **Chain worktrees**: a dependent unit's worktree branches from its *dependency's*
   `impl/NN` branch (not `main`), so it contains the dependency's code. Requires
   resolving the dep chain order (topo) and what happens when a dep gets re-run/rebased.
2. **Merge done deps to `main` before starting dependents**: a unit that PASSes is merged
   to `main` immediately (or its branch is the base for dependents), so dependents branch
   from a `main` that already contains the dep. Simpler ordering but changes the
   pipeline/PR cadence (05/06 currently park-not-halt and merge at the end).

Either way: the `to-tickets` skill's `depends_on` edges must translate into real worktree
base selection, not just topo start-ordering.

## Answer

**No code fix — constraint only (Q2a).** The 15-build framing ("worktrees ignore
`depends_on`") was incomplete. The current code already gates dependents on dep **merge**,
not just verifier-pass:

- `_on_done` (`--pr-stage on`) sets status `AWAITING_PR` (NOT added to `done`).
- `_poll_prs` adds to `done` only **after** the PR merges to `main`.
- `_sweep` starts a dependent only when `all(d in done for d in depends_on)`.

So with `--pr-stage on`, a dependent's `worktree_add` runs only after all its deps are
merged to `main` — the worktree branches from a `main` that already contains the deps'
code. **Bug 19 does not bite with `--pr-stage on`.** It bites only on **throwaway smoke**
(`--pr-stage off`), where `_on_done` adds to `done` on verifier-pass (no merge) and the
dependent branches from `main` before the dep lands — the 15-build `parse_trailer`
duplication path.

**Resolution (Q2a — constraint, no code):**
- Throwaway smoke (`--pr-stage off`) is for **single-unit** smokes (e.g. decision 08).
- **Multi-unit dep chains require `--pr-stage on`** — which already propagates deps via
  merge-to-main before dependents start.
- 25 (a real build, 5 units with a dep chain) runs `--pr-stage on` → no 19.
- Optional later guard: warn/stop if `--pr-stage off` is used with a unit that has
  non-empty `depends_on`. Not built now; the constraint is documented.

**Candidate (b) (local-merge-to-main on `--pr-stage off`) rejected for now** — it would
enable fast dogfood without per-unit GitHub approval, but 23 (auto-merge after Sourcery,
dropping GitHub APPROVED) is the intended path for that; 19 should not pre-empt it. If fast
local dogfood of dep chains is wanted before 23 lands, reopen and take Q2b.

**05 Q4a amendment (already true in code):** a dependent starts only after all its deps
are **merged to `main`** (PR or local squash), not merely verifier-passed. Pipelining
across independent units (no shared deps) is unchanged.

**Known limitation:** `--pr-stage on` needs the human to approve each dep PR on GitHub
(the 06 merge gate = human APPROVED + Sourcery clean; 23, which drops APPROVED, is not
built). For 25 that is several human GitHub approvals in dependency order.