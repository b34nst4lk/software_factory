# 04 — to-tickets skill design

Type: grilling
Status: open
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

<!-- filled on resolve -->