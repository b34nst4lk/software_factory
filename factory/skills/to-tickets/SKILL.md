---
name: factory-to-tickets
description: Convert ONE resolved Wayfinder decision into orchestrator-consumable implementation Work Units — each a non-overlapping, independently implementable+verifiable slice with a strict YAML-frontmatter ticket the deterministic orchestrator reads. A thin specialization of the general to-tickets tracer-bullet process for the software-factory. Invoke explicitly as /skill:factory-to-tickets <decision-ref>.
disable-model-invocation: true
---

# factory-to-tickets

Take **one resolved Wayfinder decision** and break it into **implementation Work Units** the deterministic software-factory orchestrator executes. Each Work Unit is one implementer herdr pane + one prompt.

This is a **thin specialization** of the general `to-tickets` tracer-bullet process. We reuse that skill's process (tracer-bullet vertical slicing, blocking edges, prefactoring-first, quiz-then-publish, one-file-per-ticket) and specialize the **I/O contract** for the factory: one-decision-per-invocation, a strict machine-parseable YAML frontmatter, a separate `impl/` namespace, a ≤5 cap, non-overlapping `scope_files`, structured-behavior `acceptance`, and a per-unit `model` binding. Do **not** rebuild the decomposition philosophy — inherit it.

> **Naming note**: the mattpocock pack ships a global `to-tickets` skill; pi keeps the first-found on a name collision (global before project), so a same-named factory skill would be shadowed. This skill is named `factory-to-tickets` to stay unambiguous. The pipeline stage it fulfils is still "the `to-tickets` step" in the map.

## Prerequisite

A **resolved Wayfinder decision** exists: a ticket file with `Status: resolved` and an `## Answer` section (the wayfinder map and tracker live under `.scratch/<effort>/issues/`). If the decision isn't resolved, stop and tell the human to resolve it via Wayfinder first — this skill consumes decisions, it doesn't make them.

## Invocation

```
/skill:factory-to-tickets <decision-ref>
```

`<decision-ref>` is a path or id resolving to the resolved decision ticket, e.g. `.scratch/software-factory/issues/08-smoke-greet-decision.md` or `08`. Resolve it against the current effort's tracker, read the full ticket (Question + Decision/Answer + any linked context/research), and carry that into the decomposition.

## Process

### 1. Load the decision

Read the resolved decision ticket fully — the Question, the Decision/Answer, and any linked research or ADRs it references. This is the *what/why*. Your job is the *how-sliced*.

### 2. Explore the codebase (optional but usual)

Use the project's domain glossary (`CONTEXT.md`) and ADRs. Understand the current state of the code in the area the decision touches so `scope_files` are real and non-overlapping. Look for prefactoring ("make the change easy, then make the easy change"); order any prefactoring as its own Work Unit(s) first.

### 3. Draft Work Units (tracer-bullet vertical slices)

Break the decision into **Work Units**. Inherit the tracer-bullet rules:

- Each Work Unit cuts a narrow but **complete** path through every layer it needs (code + tests): vertical, not a horizontal slice of one layer.
- A completed Work Unit is **demoable or verifiable on its own**.
- Each Work Unit is sized to fit a **single fresh context window** (the implementer pane has never seen the decision).

Factory-specific constraints (these override the general skill where they differ):

- **Non-overlapping `scope_files`**: every Work Unit names the exact files it will touch. Parallel implementer panes share one checkout — scope isolation prevents write collisions. If two units must touch the same file, sequence them with a `depends_on` edge (one writes, the next reads), or merge them into one unit.
- **Independently implementable AND independently verifiable**: each Work Unit has its own acceptance behaviors and verification criteria. A unit that can only be verified by another unit's work is a horizontal slice — redraw it.
- **1 Work Unit = 1 implementer herdr pane + 1 prompt**. The prose body you write is exactly the prompt the orchestrator sends to that pane.
- **Cap ≤ 5 units per decision.** If you draft more, merge. Over-decomposition is the most common failure mode; the cap is hard.
- **`depends_on` edges** name other `impl-NN` ids that must complete first. A unit with no `depends_on` can start immediately; the orchestrator pipelines independent units and stalls dependents by topo.

**Wide-refactor exception.** A wide refactor (one mechanical change — rename a symbol, retype a shared value — whose blast radius fans across the codebase so no vertical slice lands green) is NOT forced into a tracer bullet. Sequence it expand→migrate→contract: expand (add the new form beside the old), migrate (move call sites in per-package batches, each its own unit blocked by the expand), contract (delete the old form once no caller remains, blocked by every migrate). Green is promised per migrate batch because the old form still exists.

### 4. Quiz the human

Present the proposed breakdown as a numbered list **before publishing anything**. For each Work Unit show:

- **id**: `impl-NN`
- **title**: one line
- **scope_files**: the exact files
- **depends_on**: other `impl-NN` ids, or none
- **what it delivers**: the end-to-end behaviour this unit makes work (a behaviour, not a layer)

Ask:

- Is the granularity right? (too coarse / too fine; the ≤5 cap means merge if >5)
- Are the `scope_files` truly non-overlapping across independent units?
- Are the `depends_on` edges real — does each unit only depend on units that genuinely gate it?
- Should any units merge or split?

Iterate until the human approves. Nothing is written to `impl/` until approval.

### 5. Publish to `.scratch/<effort>/impl/`

Write **one file per Work Unit** at `.scratch/<effort>/impl/NN-<slug>.md`, numbered from `01` in dependency order (blockers first). `<effort>` is the effort slug from the decision's tracker path (e.g. the decision at `.scratch/software-factory/issues/08-...` → effort `software-factory` → `.scratch/software-factory/impl/NN-<slug>.md`). This `impl/` namespace is deliberately separate from `issues/` (decisions = what/why, impl = how-sliced).

Each file is YAML frontmatter + a prose implementer-prompt body.

### Output schema (frontmatter — all keys authored up front, value-only mutation)

```yaml
---
id: impl-NN
decision: <wayfinder ticket id + title, e.g. "08 — [SMOKE TEST] Greet function">
title: <one line>
scope_files: [factory/greet.py, factory/greet_test.py]
acceptance:
  - story: "As a caller, I can <action>"
    behaviors:
      - { behavior: "<normal behavior>",   outcome: success }
      - { behavior: "<edge behavior>",     outcome: failure }
verify:
  - <what the verifier checks: one bullet per gate-relevant fact>
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
model: deepseek-v4-flash:cloud
depends_on: []            # other impl-NN ids, or [] 
status: open             # orchestrator mutates: open → in_progress → parked → done | blocked
cycle: 0                 # orchestrator increments per implementer→verifier round
last_verdict: ""         # orchestrator writes the last overall verdict (PASS|FAIL|BLOCKED)
---
<prose implementer-prompt body — see below>
```

**Value-only-mutation contract (critical).** You author **every key** with its initial value (`status: open`, `cycle: 0`, `last_verdict: ""`, `depends_on: []` when none). The orchestrator later mutates only **values** of `status`, `cycle`, `last_verdict` — it never adds keys. A Husky guard rejects any commit that adds a frontmatter key or mutates a key other than those three. So: get the full key set right now; leave `status/cycle/last_verdict` at their initials.

**`acceptance` is structured behaviours.** Each entry is `{story, behaviors: [{behavior, outcome}]}` capturing the user story and its success/failure states. The implementer writes behaviour-driven + property/fuzz tests mapping to these; the verifier's 6th gate checks behaviours-are-captured and tests-map-to-behaviours. Write behaviours that are **false at the base commit** (else they grade nothing): for each, name the observation that would show it failing, and confirm it fails before the work is done.

### The prose implementer-prompt body

The body is the **single `herdr agent prompt` payload** the orchestrator sends to a fresh implementer pane (model = `model:`). It must be **self-contained**: a pi session that has never seen the decision must understand the task from frontmatter + body alone.

Body rules:

- State the task in domain language (use `CONTEXT.md` vocabulary), the `scope_files` to touch, and **restate the acceptance behaviours** inline (don't just say "see frontmatter" — the pane reads the prompt first).
- Instruct the implementer to build **test-first via `/skill:tdd`**: write behaviour-driven tests + a property/fuzz (hypothesis-style) test, each mapped to an acceptance behaviour, then implement until green.
- Require an explicit **test↔behaviour mapping** (a short table or `# maps to: <behavior>` comments) so the verifier's 6th gate can check coverage.
- Stay strictly within `scope_files`; do not edit files outside scope.
- **Do NOT** hardcode the cycle number, the git worktree path, a branch name, or commit/push instructions — the orchestrator owns the worktree, per-cycle commit cadence, and the Husky pre-commit guard; it prepends that environment/process context around your body at runtime. Your body is the **task**, not the harness.
- **Do NOT** include verifier instructions — the orchestrator sends a separate verifier prompt; this body is implementer-only.
- End with: "When your work is test-green and within scope, stop and summarize what changed and the test results." (The orchestrator decides the next cycle.)

## It's working if

- Every Work Unit answers "what can I demo/verify when this is done?" with a **behaviour**, not a layer.
- `scope_files` across independent units are non-overlapping; shared files are sequenced via `depends_on`.
- ≤ 5 units; the list came back numbered with `depends_on` before anything was written.
- Each file has the full frontmatter key set with `status: open / cycle: 0 / last_verdict: ""` initials.
- `acceptance.behaviors` are false at the base commit (would fail before the work).
- The prose body is readable cold by a fresh session and contains no cycle/worktree/commit/verifier content.
- Prefactoring, where found, is ordered first.

## Worked example (smoke test, decision 08)

Decision: add `greet(name)` to `factory/greet.py` returning `f"hello, {name}"`, with an injected `greet(None)` ambiguity.

One Work Unit (the decision is trivial; the injected ambiguity is an *escalation*, not a second unit):

`.scratch/software-factory/impl/01-greet.md`
```yaml
---
id: impl-01
decision: "08 — [SMOKE TEST] Greet function"
title: "greet(name) returns f'hello, {name}'"
scope_files: [factory/greet.py, factory/greet_test.py]
acceptance:
  - story: "As a caller, I can greet someone by name"
    behaviors:
      - { behavior: "greet('world') returns 'hello, world'", outcome: success }
      - { behavior: "greet('Ada') returns 'hello, Ada'",     outcome: success }
      - { behavior: "greet('')    returns 'hello, '",         outcome: success }
      - { behavior: "greet(None) raises TypeError",          outcome: failure }
verify:
  - "behaviors captured by tests; tests map 1:1 to acceptance.behaviors"
  - "a property test asserts greet(x) == 'hello, ' + x for non-empty x"
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
---
Implement `greet(name)` in `factory/greet.py` (new file) and its tests in
`factory/greet_test.py` (new file). Stay within these two files.

Behaviours to make pass:
- greet('world') == 'hello, world'
- greet('Ada') == 'hello, Ada'
- greet('') == 'hello, '           # empty name is allowed
- greet(None) raises TypeError     # resolution of the injected ambiguity

Build test-first via /skill:tdd. Write a behaviour-driven test per bullet and a
property/fuzz test (hypothesis-style) asserting greet(x) == 'hello, ' + x for
non-empty string x. Annotate each test with the behaviour it covers
(e.g. `# maps to: greet('world') returns 'hello, world'`) so coverage is
checkable. Implement until green.

When test-green and within scope, stop and summarize what changed and the test results.
```