# 05 — Orchestrator script contract

Type: grilling
Status: open
Blocked by: 03, 04

## Question

Decide, with the human (grilling), the deterministic orchestrator script's contract (no LLM):
1. Language — bash / python / node — and why.
2. State model — per-implementation-ticket state, implementer/verifier pane ids, the **cycle counter** and what counts as a cycle (see Not yet specified).
3. Main loop — read next implementation ticket → spawn implementer (deepseek-v4-flash) + verifier (qwen3.6) panes via herdr → count cycles → on worker settled, read output → route state + implementer↔verifier discussion back to the script → surface to human.
4. Human-surfacing form — CLI log stream? a live state file? a TUI? — and exactly what the human sees (state, discussion, cycle count).
5. The pre-merge gate — what must pass before the script presents merge-ready output to the human.

Resolve by grilling; decision only.

## Answer

<!-- filled on resolve -->