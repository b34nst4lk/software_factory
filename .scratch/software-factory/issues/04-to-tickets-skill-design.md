# 04 — to-tickets skill design

Type: grilling
Status: resolved
Blocked by: 03

## Question

Design the new **to-tickets** pi skill that sits between Wayfinder and the orchestrator. Decide, with the human (grilling):
1. Input — one resolved Wayfinder decision at a time, or a batch?
2. Decomposition rules — how a decision is sliced into implementer-sized work units (scoped file changes, acceptance criteria per unit).
3. Output ticket schema — the fields the orchestrator script consumes (id, title, scope/files, acceptance criteria, model binding, dependencies).
4. Location — where implementation tickets live in the local-markdown tracker (e.g. `.scratch/<effort>/impl/NN-<slug>.md`) and how that extends the existing `.scratch/` convention.
5. Invocation — how the skill fires after Wayfinder resolves (explicit `/to-tickets` vs a Wayfinder post-resolution hook; see Not yet specified).

Resolve by grilling the human; this is a decision, not a build.

## Answer

Resolved 2026-08-19. The `to-tickets` pi skill (runs on glm-5.2) contract:

1. **Input — one resolved Wayfinder decision per invocation** (not a batch). Matches Wayfinder's one-decision-per-ticket granularity; the orchestrator's backlog is a flat queue of Work Units from many single-decision runs.
2. **Decomposition rules** (LLM on glm-5.2 does the slicing; rules constrain it):
   - Slice on file/module boundaries; each Work Unit names a **non-overlapping file scope** (parallel implementer panes share one checkout — scope isolation prevents collisions).
   - Each Work Unit is **independently implementable and independently verifiable** (own acceptance + verification criteria).
   - One Work Unit = one implementer herdr pane + one prompt.
   - Cap ≤5 units per decision (no unmanageable fan-out).
3. **Output schema — one file per Work Unit, YAML frontmatter + prose prompt body** (machine-parseable by the deterministic orchestrator, no LLM needed to read it):
   ```yaml
   ---
   id: impl-NN
   decision: <wayfinder ticket id/title>
   title: <one line>
   scope_files: [src/foo.ts, src/bar.ts]
   acceptance: [criterion 1, criterion 2]
   verify: [what the verifier checks]
   model: deepseek-v4-flash:cloud      # implementer binding
   depends_on: [impl-NN, impl-NN]
   status: open
   cycle: 0
   last_verdict: ""
   ---
   <self-contained implementer prompt — the single `herdr agent prompt` payload>
   ```
4. **Location — `.scratch/<effort>/impl/NN-<slug>.md`** (parallel to `issues/`, separate namespace; decisions = what/why, impl = how-sliced).
5. **Invocation — explicit `/to-tickets <decision>`**, run by the human or the Wayfinder session as its last step after closing a decision. Matches the stated flow `wayfinder → to-tickets → orchestrator` as a deliberate handoff. (Graduates the map's "to-tickets invocation trigger" fog.)

**Schema amendment (from 05 grilling Q2-A, confirmed)**: to-tickets authors **all keys up front with default empty values** so the orchestrator's per-cycle mutations stay strictly value-only (no new keys added at runtime). The full frontmatter key set is therefore: `id, decision, title, scope_files, acceptance, verify, model, depends_on, status, cycle, last_verdict` — with `status: open`, `cycle: 0`, `last_verdict: ""` as the to-tickets-authored initials the orchestrator later mutates.

**Scope clarification (human)**: the factory is a **thin layer over the existing matt pocock skills** — do not rebuild Wayfinder/grilling/domain-modeling/tdd/code-review/prototype/etc. The only new parts are: the `to-tickets` skill, the deterministic orchestrator script, herdr setup, and the pi provider config (already mostly wired — 02). Existing skills are reused where they fit (e.g. `code-review` as the verifier's method, `tdd` for the implementer, `prototype` for cheap artifacts); how they're invoked by the orchestrator/verifier is a 05/06 design question.

Unblocks: 05 (orchestrator script contract), then 06.