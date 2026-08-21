# Map: Software Factory (pi extension)

## Destination

A working *prototype* of a software factory built on pi: **Wayfinder** (glm-5.2, Ollama cloud) clears requirements/decisions → a new **to-tickets** skill converts resolved decisions into implementation tickets → a **deterministic orchestrator script** (no LLM) drives an **implementer** (deepseek-v4-flash) and **verifier** (qwen3.6) as pi agents via **herdr**, owning cycle-counting, feedback routing, and human surfacing, with verifier escalation back to Wayfinder. Once the prototype works end-to-end on this repo, it becomes the parameterized base for other projects.

## Notes

- **Domain**: extending pi into a multi-agent software factory.
- **Skills every session should consult**: wayfinder (this map), grilling, domain-modeling, prototype, research, tdd; plus the **to-tickets** skill once built. herdr agent-automation docs: https://herdr.dev/docs/agent-automation/ ; agents: https://herdr.dev/docs/agents/ .
- **Model bindings** (cross-model review enforced — implementer ≠ verifier):
  - Wayfinder / grilling / to-tickets sessions → **glm-5.2** (Ollama cloud; also the model this charter session runs on).
  - Implementer → **deepseek-v4-flash** (DeepSeek platform; OpenAI-compatible chat completions + Responses API).
  - Verifier → **qwen3.5:cloud** (Ollama cloud; chosen Ollama-only over qwen3.6, which isn't on Ollama cloud — see 02). Older gen than first discussed, but still cross-model vs the implementer.
  - Orchestrator → **deterministic script, no LLM.**
- **Standing preferences**:
  - The verifier **never assumes**. Any ambiguity is escalated back to Wayfinder as a new decision ticket, never guessed. Wayfinder is the single decision channel throughout (continuously interleaved, not a one-shot front-end phase).
  - Cross-model review: implementer and verifier are different models.
  - The orchestrator is a deterministic script that "bounces between" the agents and owns the cycle counter, reporting cadence, feedback routing, and human surfacing.
  - Human gates: map→implementation handoff; pre-merge. Verifier-fail → Wayfinder ticket (not auto-retry).
  - Flow: `wayfinder skill → to-tickets skill → orchestrator script → implementer + verifier (via herdr)`.
- **Reuse, don't rebuild**: the factory is a **thin layer over the existing matt pocock skills** (wayfinder, grilling, domain-modeling, tdd, code-review, prototype, etc.). The only new code is the `to-tickets` skill, the deterministic orchestrator script, herdr setup, and the pi provider config (mostly done — 02). Existing skills are reused where they fit (e.g. `code-review` as the verifier's method, `tdd` for the implementer); how the orchestrator/verifier invokes them is a 05/06 design question.
- **Execution carried into this map**: iteration 1 is the *prototype*, built here; later iterations are dogfooded (the factory builds its own new features). The map clears the fog so the prototype can be built; the build itself (ticket 07) is the destination artifact, not a separate spec handoff.

## Decisions so far

- [03 — herdr + pi driver pattern](issues/03-herdr-pi-driver-pattern.md): drive pi workers via herdr Pattern A (agent start/prompt --wait/read); pi is a supported herdr kind with lifecycle hooks after `herdr integration install pi`; model binding via pi `--model`; herdr gives state, the script owns the cycle counter; pi RPC mode is a fallback. Findings: [research/03](research/03-herdr-pi-driver-pattern.md).
- [02 — Wire the three models as pi custom providers](issues/02-model-provider-wiring.md): glm-5.2:cloud + deepseek-v4-flash:cloud already wired under one `ollama` provider; verifier = qwen3.5:cloud (Ollama-only choice; qwen3.6 not on Ollama cloud). One models.json entry to add at build time. Findings: [research/02](research/02-model-provider-wiring.md).
- [01 — Repo bootstrap](issues/01-repo-bootstrap.md): git init `main` (commit `2f6b540`); AGENTS.md, CONTEXT.md glossary, `factory/` scaffold (orchestrator/ + skills/to-tickets/ placeholders), .gitignore. No decisions; pure setup.
- [04 — to-tickets skill design](issues/04-to-tickets-skill-design.md): one decision per invocation; decomposition = non-overlapping file scopes, independently implementable+verifiable, 1 unit = 1 pane + 1 prompt, cap ≤5; output = `.scratch/<effort>/impl/NN-<slug>.md` with YAML frontmatter (id/decision/title/scope_files/acceptance/verify/model/depends_on/status) + prose prompt body; explicit `/to-tickets <decision>` invocation.

## Not yet specified

- **Parameterization**: once the prototype works, how to generalize it as the base for arbitrary target repos/projects (per-repo tracker path, model bindings, repo path as config). Not ticketable until the prototype shape is fixed by 04–07.
- **"Cycle" definition**: what counts as one cycle for the orchestrator's counter (tool call? turn? pane state transition?). Depends on 05.
- **Model failover / quota exhaustion**: herdr can switch reviewers on quota exhaustion; does our script need its own failover for implementer/verifier? Depends on 05/06.
- **Existing-skills invocation**: which matt pocock skills the implementer/verifier reuse and how the orchestrator invokes them in the herdr/pi context (informs 05/06; not a standalone ticket).
- **Dogfooding first target**: which feature the factory first builds for itself once the prototype exists. Far fog; graduates after 07.

## Out of scope

- Reimplementing Wayfinder/grilling/domain-modeling/tdd/code-review/prototype/etc. — use the existing matt pocock skills (see Notes: thin-layer principle).