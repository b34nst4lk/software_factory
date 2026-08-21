# Software Factory

The system this repo builds: a pi extension that turns a loose idea into working software through a staged, human-in-the-loop pipeline. Iteration 1 is a prototype built in this repo; later iterations are dogfooded (the factory builds its own new features).

## Pipeline roles

**Wayfinder**:
The requirements/decision engine. Clears fog and records decisions as tickets in the tracker; stays the single decision channel throughout, continuously interleaved with implementation.
_Avoid_: planner, requirements phase, spec writer

**to-tickets**:
A pi skill that converts a resolved Wayfinder decision into implementation tickets the orchestrator can execute.
_Avoid_: decomposer, task spawner, ticket generator

**Orchestrator**:
A deterministic script (no LLM) that reads implementation tickets and drives the Implementer and Verifier as pi agents via herdr. Owns the cycle counter, routes worker feedback back to itself, and surfaces it to the human.
_Avoid_: coordinator agent, controller, dispatcher

**Implementer**:
A pi agent (deepseek-v4-flash) that implements a single scoped work unit in a herdr pane.
_Avoid_: coder, builder, worker

**Verifier**:
A pi agent (qwen3.5) that adversarially reviews the Implementer's output. Never assumes — escalates ambiguity back to Wayfinder. Different model family from the Implementer (cross-model review).
_Avoid_: reviewer, checker, QA agent

## Runtime

**herdr**:
The terminal runtime the Orchestrator drives workers through. Owns panes and agent lifecycle state (working/blocked/done/idle); the Orchestrator binds a model per pane, prompts, waits on state, and reads output through it.
_Avoid_: terminal multiplexer, session manager

**Work Unit**:
One scoped, implementer-sized slice of a resolved decision: a self-contained prompt with file scope, acceptance criteria, and a model binding, consumable by the Orchestrator as one herdr pane + prompt.
_Avoid_: task, ticket (use "implementation ticket" for the tracker artifact), story

## Process

**Cycle**:
One implementer→verifier round the Orchestrator counts (prompt implementer → wait → read → prompt verifier → wait → read). Definition is finalized in ticket 05.
_Avoid_: turn, step, iteration

**Escalation**:
The path a Verifier takes when it cannot proceed without assumption: the Orchestrator opens a new Wayfinder decision ticket, blocks the worker panes, and resumes only once that ticket resolves.
_Avoid_: handoff, raise, block (use "blocked" for herdr's lifecycle state)