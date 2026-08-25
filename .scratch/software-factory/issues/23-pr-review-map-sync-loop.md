# 23 — PR-review + map-sync loop driven by the human through the main pi session

Type: task
Status: resolved
Blocked by:
Resolved by grilling 2026-08-24. Amends 05/06's PR stage (dogfooding showed GitHub
APPROVED is unusable: all pushes are under one user, so you cannot approve your own PRs).

## Question

How does the PR-review loop + the post-merge map sync run, and who drives it?

## Answer (settled by grilling)

The orchestrator owns the **PR-review loop** as part of the run (it extends the 05/06 PR
stage). The **human drives it through the main pi session** (the wayfinder pane) via stdin
gates sent with `herdr --session factory pane send-keys <orch-pane> <key>` (then `Enter`).

**The loop (after build done + the PR is open):**
1. The orchestrator polls **Sourcery** review comments on a cadence (60s) AND on the
   human's **`r` poke** (an immediate re-check). It does **not** use GitHub APPROVED —
   dogfooding showed self-approval is impossible (one user pushes everything).
2. If there are comments (Sourcery or human), the orchestrator **routes them to the impl
   pane** (`pr_fix_prompt`) to address. The impl addresses, commits (the guard runs), and
   the **orchestrator re-runs the verifier** (the 6 gates) before the push (cross-model
   review on the fix). Repeat until no open comments.
3. The human signals **`m`** (review complete / merge-ready) through the main pi session.
4. The orchestrator checks **Sourcery clean** (never-assume — it will not merge if Sourcery
   has open issues, even after the human's `m`), then **squash-merges** (`gh pr merge
   --squash`) and signals **merged / complete** back to the wayfinder.
5. The **wayfinder (this session) writes the map sync** (Decisions-so-far, frontier, fog)
   and commits it. The map sync is **judgment**, not a deterministic action, so the
   orchestrator does not write it — it only signals that review is complete. (The bug-22
   guard fix allows this non-impl commit: the map has no impl ticket, so the governed-set
   rule does not apply; only the denylist does.)

**Stdin gates:** `r` = re-check reviews now; `m` = review complete / merge-ready; `q` =
quit / park the unit. Sent from the main pi session via `herdr send-keys`.

**What this amends in 05/06:** drops GitHub APPROVED from the merge gate (replaced by the
human's `m` signal); keeps Sourcery clean as the never-assume floor; the orchestrator
merges (not the human on GitHub); adds the map-sync-by-wayfinder step triggered by the
orchestrator's complete signal.

## Build (to-tickets, then the factory)

The orchestrator gains the PR-review loop (cadence + `r`/`m`/`q` stdin gates), the
comment-routing + verifier re-run (the 06 pr_fix flow, made real), the `gh pr merge` on
`m` + Sourcery-clean, and the "merged → signal wayfinder" step. The wayfinder side
(this session) is a skill/habit, not orchestrator code. Depends on bug 22 (guard allows
non-impl commits for the map sync) and the 06 pr_fix design.

## Answer

<!-- filled when built -->