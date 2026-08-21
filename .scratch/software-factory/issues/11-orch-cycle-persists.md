# 11 — orchestrator: cycle counter persists across park/resume

Type: task
Status: resolved
Blocked by:
Found by: 07 (live smoke). Follow-up to 09.

## Question

`cycle.run_cycle` starts `cycle_no = 0` every call and loops `while cycle_no < cap`
(`cycle.py:114`). It writes `cycle` to frontmatter each cycle but never reads it back,
so a park→resume restarts the count. The smoke log showed `c1 BLOCKED`, then resume
`c1 FAIL`, `c2 PASS` — a second `c1`. A unit that escalates repeatedly never approaches
the 5-cycle backstop.

## Fix

Seed `cycle_no = unit.cycle` (the persisted frontmatter value, parsed by
`ImplTicket.cycle`) so resume continues counting. The cap (`cap_override or
config.cycle_cap`) becomes a **total ceiling across the unit's whole life** (05 Q3's
"high default ceiling of 5 cycles"), not per-resume.

## Answer

Fixed 2026-08-21. `cycle.run_cycle` now seeds `cycle_no` from the **persisted**
frontmatter `cycle` (`tickets.parse_impl_file(unit.path).cycle`) instead of `0`, so a
park→resume continues counting — the 5-cycle backstop is now a TOTAL ceiling across the
unit's whole life (05 Q3), not per-resume. The smoke's `c1 BLOCKED → c1 FAIL → c2 PASS`
becomes `c1 BLOCKED → c2 FAIL → c3 PASS`.

This fix also exposed and fixed a latent bug: `run._run_one` never passed
`cap_override=st.cap_override` to `run_cycle`, so the 5-cycle-backstop `c` (continue) gate
that lifts the ceiling was silently broken (the cap-lift test passed only by accident —
the pre-fix restart-at-cycle-1 consumed the next mock read). Now wired through.

Covered by `test_cycle_counter_persists_across_resume` (resume continues at cycle 2) and
the now-correct `test_cap_reached_gate_continue_lifts_cap_then_pass`.

<!-- filled when fixed -->