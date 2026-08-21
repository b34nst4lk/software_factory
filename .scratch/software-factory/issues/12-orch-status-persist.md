# 12 — orchestrator: persist status to frontmatter on done/parked/cancelled

Type: task
Status: open
Blocked by:
Found by: 07 (live smoke). Follow-up to 09.

## Question

`cycle.run_cycle` writes only `cycle` and `last_verdict` (`cycle.py:157`). `run` sets the
in-memory `st.status` on done/parked/cancelled but never writes `status:` to the
frontmatter, so the worktree's `01-greet.md` still said `status: open` after the unit was
done. Git-as-state is incomplete: reading the frontmatter alone doesn't tell you the
unit's state.

## Fix

Persist `status` at each lifecycle transition (a guard-allowed mutable key, per 04):
- `in_progress` at the start of each cycle (in `cycle.run_cycle`, alongside `cycle`/`last_verdict`)
- `done` in `run._on_done` (pr_stage off)
- `parked` in the `run._run_one` ESCALATE branch
- `cancelled` in `run._gate` quit

Vocabulary: `open → in_progress → parked → done | cancelled` (04 + 06 Q3's "mark
cancelled"; "blocked" is the herdr lifecycle state, frontmatter uses "parked").

## Answer

<!-- filled when fixed -->