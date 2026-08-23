---
id: impl-03
decision: "17 — git-as-state durability"
title: "guard: reject commits outside {impl-ticket} ∪ scope_files + denylist; drop run.log rule"
scope_files:
  - factory/orchestrator/guard.py
  - factory/orchestrator/tests/test_guard.py
acceptance:
  - story: "As the deterministic pre-commit guard, I reject any per-cycle commit that contains non-governed or runtime-artifact paths"
    behaviors:
      - { behavior: "the guard rejects a commit whose staged paths are not a subset of {impl-ticket} ∪ scope_files", outcome: failure }
      - { behavior: "the guard reads scope_files from the staged impl-ticket's YAML frontmatter (the .scratch/.../impl/NN-*.md file among the staged paths)", outcome: success }
      - { behavior: "the guard hard-denies a staged path matching the denylist (.verdict.yaml, .verdict.yml, .venv, *.db, __pycache__) regardless of scope_files", outcome: failure }
      - { behavior: "the guard accepts a commit whose staged paths are exactly {impl-ticket} ∪ scope_files", outcome: success }
  - story: "As the guard, the old run.log append-only rule is gone (run.log is no longer committed)"
    behaviors:
      - { behavior: "the guard no longer enforces a run.log append-only rule (the rule/check is removed)", outcome: success }
      - { behavior: "a staged run.log is rejected as a non-governed path (it is not in {impl-ticket} ∪ scope_files and not special-cased)", outcome: failure }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "the governed set is {impl-ticket path} ∪ scope_files, where scope_files come from the staged impl ticket's frontmatter"
  - "the denylist is a hard floor: a denied path is rejected even if it were somehow in scope_files"
  - "the guard is a pure function over (staged paths, staged file contents) — it does not shell out beyond reading staged content"
model: deepseek-v4-flash:cloud
depends_on:
  - impl-02
status: open
cycle: 0
last_verdict: ""
---
Make the deterministic pre-commit **guard** the real gate against runtime-artifact cruft
in per-cycle commits (formalize-when-discovered: a programmatically-checkable rule belongs
in the guard, not the LLM verifier). Touch only `factory/orchestrator/guard.py` and
`factory/orchestrator/tests/test_guard.py`. Do NOT edit gitops.py, cycle.py, run.py,
tickets.py, or state.py — those are impl-01/impl-02's scope.

Context (decision 17 — git-as-state durability, resolved by grilling): impl-02 made
`commit_cycle` stage exactly `{impl-ticket} ∪ scope_files` by explicit path. But a future
regression (or a stray `git add -A`) could re-introduce runtime artifacts (`.verdict.yaml`,
a `.venv` symlink, the `*.db` narrative DB, `__pycache__`) into a commit. Gitignore-alone
is a fragile gate (the 15 build proved it: `.venv/` didn't match the symlink). This unit
makes the **guard** enforce "staged paths ⊆ {impl-ticket} ∪ scope_files" with a hard
denylist, and removes the now-obsolete `run.log` append-only rule (run.log is no longer
committed — impl-02 discarded it).

Behaviours to make pass (each is false at the base commit — the guard only checks
frontmatter value-only + run.log append-only; it has no staged-paths-subset rule and no
denylist; it still special-cases run.log):
- The guard rejects a commit whose staged paths are NOT a subset of
  `{impl-ticket} ∪ scope_files`.
- The guard reads `scope_files` from the staged impl-ticket's YAML frontmatter. The
  impl ticket is the staged path matching `.../impl/NN-*.md` (an `impl/` markdown file);
  parse its frontmatter `scope_files` (a list) using the existing `split_frontmatter`
  helper in guard.py.
- The guard hard-denies a staged path matching the denylist — `.verdict.yaml`,
  `.verdict.yml`, `.venv`, any `*.db`, and `__pycache__` (path-suffix/name matches) —
  regardless of scope_files (a denied path is rejected even if it were in scope_files).
- The guard accepts a commit whose staged paths are exactly `{impl-ticket} ∪ scope_files`.
- The guard no longer enforces a `run.log` append-only rule (remove `run_log_has_deletions`
  / `check_run_log_diff` and their use in the guard's check entrypoint).
- A staged `run.log` is rejected as a non-governed path (it is not in
  `{impl-ticket} ∪ scope_files` and is no longer special-cased).

Implementation notes (you decide exact factoring, observable behaviour is graded):
- Add a function like `check_staged_paths(staged_paths, staged_contents) -> list[Violation]`
  that: (a) finds the staged impl ticket (the `impl/*.md` path), parses its frontmatter
  `scope_files`; (b) builds the governed set `{impl_ticket} ∪ set(scope_files)`; (c) any
  staged path not in that set, OR on the denylist, is a Violation. Wire it into the
  guard's main check entrypoint (the one Husky calls) alongside the existing
  frontmatter value-only check.
- The denylist is a hard floor checked first (or independently): if any staged path
  matches a denied name/suffix, emit a Violation even if it's also in scope_files.
- Reuse `split_frontmatter` for parsing the impl ticket frontmatter (it already exists
  in guard.py). Do not duplicate YAML parsing.
- Remove the `run.log` append-only rule entirely (the `run_log_has_deletions`/
  `check_run_log_diff` functions and their call). Keep the frontmatter value-only rule.
- The guard is a pure function over (staged paths, staged file contents); it does not
  shell out beyond reading staged content. Keep it testable in --mock style (feed staged
  paths + contents, assert violations).

Build test-first via /skill:tdd. One behaviour-driven test per bullet, annotated
`# maps to: ...`. Cover: governed-only commit accepted; one extra non-governed file
rejected; each denylist entry (.verdict.yaml, .verdict.yml, .venv, a .db, a __pycache__
path) rejected; scope_files read from a staged impl ticket frontmatter; run.log rejected
as non-governed (and the old run.log append-only test removed/repurposed). Stay within
scope_files.

When your work is test-green and within scope, stop and summarize what changed and the
test results.