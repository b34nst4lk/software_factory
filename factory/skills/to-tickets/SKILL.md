---
name: to-tickets
description: Convert resolved Wayfinder decisions into implementation tickets the orchestrator executes. Placeholder — contract decided by ticket 04.
---

# to-tickets (placeholder skill)

Sits between Wayfinder and the Orchestrator: takes resolved Wayfinder decisions and produces implementation tickets (Work Units) the deterministic orchestrator script consumes.

**This is a stub.** The skill's contract is decided in ticket 04:

- input — one decision vs a batch
- decomposition rules — how a decision becomes implementer-sized Work Units
- output ticket schema — fields the orchestrator reads (id, title, scope/files, acceptance, model binding, dependencies)
- location — where implementation tickets live in the local-markdown tracker
- invocation — explicit command vs a Wayfinder post-resolution hook

Do not implement until 04 resolves. See `.scratch/software-factory/map.md`.