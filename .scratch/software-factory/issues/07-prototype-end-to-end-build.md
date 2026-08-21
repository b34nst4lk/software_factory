# 07 — Prototype end-to-end build + smoke test

Type: prototype
Status: open
Blocked by: 01, 02, 03, 04, 05, 06

## Question

Build the prototype end-to-end and smoke-test it on a trivial resolved Wayfinder decision: wire the to-tickets skill, the orchestrator script, the two model providers, and herdr; run one decision through `wayfinder → to-tickets → orchestrator → implementer + verifier` and confirm the script counts cycles, routes implementer↔verifier feedback, surfaces it to the human, and escalates an *injected* ambiguity back to Wayfinder (new ticket, panes block, resolve, resume). This is the destination artifact; may decompose further as fog from 04–06 clears. HITL for the smoke test (human observes the surfaced feedback and the escalation round-trip).

## Answer

<!-- filled on resolve -->