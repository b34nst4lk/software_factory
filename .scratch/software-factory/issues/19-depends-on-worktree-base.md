# 19 — depends_on doesn't propagate dependency code to a dependent's worktree

Type: task
Status: open
Blocked by:
Found by: 15 build (dogfood). Adjacent to 16/17.

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

<!-- filled when resolved -->