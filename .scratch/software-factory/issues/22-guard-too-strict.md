# 22 — guard too strict: governed-set rule applied to every commit, blocking normal edits

Type: bug
Status: resolved
Found by: 2026-08-24, the map-sync commit after decision-17 merge. Defect in impl-03 (PR #8).

## Bug

impl-03's guard applied the "staged paths ⊆ {impl-ticket} ∪ scope_files" rule to **every**
commit. With no impl ticket staged (a normal edit — the map, AGENTS.md, a source fix), the
governed set was empty → every staged path was "non-governed" → **rejected**. This blocked
all non-per-cycle commits.

## Fix (manual, on main, 2026-08-24)

The governed-set rule now applies **only when an impl ticket is staged** (a per-cycle
commit). Commits with no impl ticket (normal edits) are allowed, subject only to the
denylist. `run.log` was added to the denylist (`_DENY_BASENAMES`) so it is still never
committed (decision 17 discards it) and impl-03's `run.log`-rejection tests still pass.

Regression test: a manual commit (no impl ticket) with a non-governed path is accepted; a
denylisted path (`.verdict.yaml`, `run.log`) is still rejected.

## Answer

Fixed 2026-08-24 (manual, on main). The guard now scopes the governed-set rule to per-cycle
commits; the denylist is the universal floor (now including `run.log`).