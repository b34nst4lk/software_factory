# 16 — interrupted-run resumability

Type: task
Status: open
Blocked by:
Graduated from: 07 (live smoke + the verdict/resumability discussion). Next frontier after 07.

## Question

Git-as-state (05 Q2) is designed for interrupt/resume (state = frontmatter + run.log +
git log, no run-state file), and fix #11 (cycle counter seeds from the persisted frontmatter
`cycle`) means a resumed run continues counting from the last committed cycle. But the
current implementation has two gaps an interrupted/killed run hits:

1. **Worktree re-creation assumes a fresh start.** `run._start_unit` does
   `git worktree add ../sf-impl-NN -b impl/NN`; if the orchestrator was killed mid-run, the
   worktree + `impl/NN` branch already exist → `git worktree add` fails → the unit can't
   resume. No "detect existing worktree/branch and resume" path.
2. **Parked-unit escalation links are in-memory only.** `UnitState.escalation_paths` lives
   in the `Orchestrator` object. If the orchestrator dies while a unit is parked, the
   frontmatter says `status: parked` (fix #12) but *which escalation tickets* is lost → on
   restart the orchestrator can't re-scan them to resume. 06 Q3 says the resolution is
   "sourced from the escalation ticket, read at resume" — but the orchestrator needs to know
   *which* tickets.

## Build

1. **Resume an existing worktree/branch**: `run._start_unit` (and `gitops`) detects an
   existing `impl/NN` worktree/branch and reuses it (re-reads the frontmatter, re-attaches
   panes) instead of `git worktree add`. A unit with `status: done`/`cancelled` is skipped.
2. **Persist the escalation-ticket link** so a parked unit is resumable across restarts.
   The guard forbids new frontmatter keys, so the link lives in `run.log` (a structured
   line like `impl-01 parked escalation=<path>`) or a guard-allowed sidecar; on restart the
   orchestrator scans parked units' run.log to recover the paths, then re-scans those
   tickets for `Status: resolved` + `## Answer` (06 Q2/Q3 file-driven resume).

## Open design choice (one, to settle when implementing)

Where to persist the escalation-ticket link — `run.log` structured line vs a sidecar file
the guard allows. `run.log` is append-only and already the narrative home; a structured
`parked escalation=<path>` line is the likely answer. (Not enough fog to warrant a grilling;
decide at the keyboard.)

## Answer

<!-- filled when built -->