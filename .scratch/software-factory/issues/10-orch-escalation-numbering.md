# 10 — orchestrator: escalation ticket numbering

Type: task
Status: open
Blocked by:
Found by: 07 (live smoke). Follow-up to 09.

## Question

The orchestrator authors escalation Wayfinder tickets at `.scratch/<effort>/issues/NN-<slug>.md`
with `NN = Orchestrator.next_esc_number`, which is hardcoded to `1` (`run.py:75`). The
smoke wrote `01-greet-name-returns-f-hello-name.md` into `issues/`, colliding visually with
`01-repo-bootstrap.md` and ignoring the tracker's existing `01`..`09`.

## Fix

Seed `next_esc_number` from the highest existing `NN-` prefix in `config.issues_dir`
+ 1 (escalations share the `issues/` namespace per 06 Q2), computed once in
`Orchestrator.run()` before the loop.

## Answer

<!-- filled when fixed -->