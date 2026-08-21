# 06 — Feedback & escalation protocol

Type: grilling
Status: open
Blocked by: 04, 05

## Question

Decide, with the human (grilling), the feedback routing + escalation protocol the orchestrator script enforces (the human's emphasized mechanism):
1. How implementer↔verifier discussion is captured (herdr `agent read` of both panes? a shared scratch file? a structured exchange log?) and routed back to the script.
2. How the script surfaces that discussion + task state to the human (when, in what form).
3. The verifier-escalation path — when the verifier finds a spec ambiguity (no assumptions), the script creates a **new Wayfinder ticket** (grilling/research) in the tracker, blocks the implementer/verifier panes (herdr `agent wait --until`? a pause flag?) until that ticket resolves, then resumes — define the exact blocking/resume mechanism.
4. How a resolved escalation ticket's answer is fed back into the paused implementer prompt.

Resolve by grilling; decision only.

## Answer

<!-- filled on resolve -->