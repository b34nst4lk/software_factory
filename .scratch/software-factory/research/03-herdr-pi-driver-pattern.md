# Research 03 — herdr + pi driver pattern

**Ticket:** [03 — herdr + pi driver pattern](../issues/03-herdr-pi-driver-pattern.md)
**Status:** resolved · **Date:** 2026-08-19

Question: how does a deterministic orchestrator script drive pi agents (implementer = deepseek-v4-flash, verifier = qwen3.6) through herdr, and how does it bind a model, detect state, and read worker output for feedback routing?

## Finding 1 — pi is a first-class herdr agent kind with lifecycle hooks

herdr's agent table lists **Pi** with state authority *"lifecycle hooks when installed; otherwise screen manifest"* and integration role *"state and session"*. So herdr can track pi's `working` / `blocked` / `done` / `idle` lifecycle, not just treat it as a terminal process.

- Install the integration from herdr's side: `herdr integration install pi`, then `herdr integration status` to confirm. (pi's own docs do not mention herdr by name; the integration is herdr-shipped and reports state to herdr's socket via `pane.report_agent`.)
- Fallback if hooks aren't installed: herdr's screen-manifest detection still classifies pi's `idle`/`working`/`blocked` from the live bottom-buffer — usable but less reliable.

Source: https://herdr.dev/docs/agents/ (Status authority, Supported agents, Blocked state); https://herdr.dev/docs/socket-api/ (`pane.report_agent`).

## Finding 2 — the script's primitive sequence (recommended Pattern A: herdr-interactive)

herdr's automation model has three surfaces — **layout** (workspace/tab/pane), **pane** (raw terminal), **agent** (recognized agent lifecycle). `agent start` requires an existing shell pane and never creates layout. Creation commands print JSON; capture IDs from the response.

Minimal working sequence for one implementer + one verifier:

```bash
# 1. Layout: one workspace, one tab, split into two panes
ws=$(herdr workspace create --cwd "$REPO" --label factory --no-focus)
impl_pane=$(printf '%s\n' "$ws" | jq -r '.result.root_pane.pane_id')
sp=$(herdr pane split "$impl_pane" --direction right --no-focus)
ver_pane=$(printf '%s\n' "$sp" | jq -r '.result.pane.pane_id')

# 2. Start a pi agent in each pane, bound to a model via pi's --model flag
herdr agent start impl  --kind pi --pane "$impl_pane" -- --model deepseek-v4-flash
herdr agent start ver   --kind pi --pane "$ver_pane"  -- --model qwen3.6

# 3. Submit work and wait on lifecycle state (the script's "report" boundary)
herdr agent prompt impl "$IMPL_PROMPT" --wait --until done --timeout 600000
herdr agent read impl --source recent-unwrapped --lines 200     # feedback capture

# 4. Hand the implementer output to the verifier
herdr agent prompt ver "$REVIEW_PROMPT" --wait --until done --timeout 600000
herdr agent read ver --source recent-unwrapped --lines 200

# 5. Escalation: if a worker hits an approval/ambiguity UI, herdr marks it blocked
herdr agent wait impl --until blocked --timeout 600000
herdr agent read impl --source recent-unwrapped --lines 80      # inspect, then route to human/wayfinder
```

Key rules from herdr docs:
- Wait on **meaning**, not text scraping: `agent wait --until blocked|done` for lifecycle; `pane wait-output --regex` only for non-agent processes (tests, servers).
- `agent prompt --wait` submits + waits in one call (avoids a race). Default `--until` accepts `idle`/`done`/`blocked`.
- Agent **names** (`impl`, `ver`) are stable live aliases; pane IDs (`w1:p2`) are stable handles. Use names in script commands; capture IDs from JSON.
- `done` = finished in background, unseen; `idle` = ready and seen. For "worker finished its turn", `done` or `idle` both satisfy; `blocked` = needs input/approval.

Source: https://herdr.dev/docs/agent-automation/ (Three primitives, Choose the control surface, Recipes); https://herdr.dev/docs/socket-api/ (Agent methods, Event subscriptions).

## Finding 3 — binding a model to a pi agent in a pane

pi selects models with `--model <pattern>` where pattern supports `provider/id` and optional `:thinking` (e.g. `pi --model openai/gpt-4o`, `pi --model sonnet:high`). The model must be registered in `~/.pi/agent/models.json` as a custom provider (that's ticket 02's job). Passing `--model deepseek-v4-flash` after `herdr agent start ... --` forwards it to pi unchanged.

- For Ollama-cloud models (glm-5.2, qwen3.6) and the DeepSeek platform (deepseek-v4-flash): register each as a provider with `api: "openai-completions"` (OpenAI-compatible), `baseUrl`, and `apiKey` (env-interpolated, e.g. `"$DEEPSEEK_API_KEY"`). See ticket 02.
- Per-pane model binding is just the `--model` arg at `agent start`; no env hack needed. (pi also exposes `PI_MODEL` to its bash tool, but that's for in-session commands, not launch-time binding.)
- Trust/autonomy: pi's interactive trust prompt surfaces in the pane and registers as herdr `blocked` — which is exactly the human-gate behaviour we want. For fully autonomous runs, `--approve`/`-a` (or `defaultProjectTrust`) skips it; reserve that for trusted, scoped work.

Source: pi `docs/usage.md` (Non-interactive modes, `-p`/`--print`, `--model`, `--models`, `--approve`); pi `docs/models.md` (Minimal/Full example, Supported APIs, Provider Configuration, Value Resolution); pi `docs/extensions.md` (`PI_MODEL` env).

## Finding 4 — cycle counting is the script's job (matches the user's Q4 answer)

herdr gives **lifecycle state transitions**, not a cycle counter. The user decided the script owns counting. The natural mapping:

- One **cycle** ≈ one implementer→verifier round: `prompt impl --wait` → `read impl` → `prompt ver --wait` → `read ver`. The script increments its counter each round and decides (configurably) when to surface state to the human.
- herdr's `--wait --until done|blocked` is the *wait* primitive inside each step; the script wraps the round in its own loop and counts.
- For finer-grained events (per tool call, per turn) instead of pane-level state, pi's **RPC mode** (`pi --mode rpc`, JSON over stdin/stdout, streaming message/agent/turn/tool lifecycle events) is an alternative control channel — but it bypasses herdr's terminal persistence + human-visible sidebar. Recommend: stay on Pattern A (herdr) for the prototype; only drop to RPC if cycle counting needs sub-turn granularity.

Source: pi `docs/rpc.md` (RPC mode, `--model`); pi `docs/sdk.md` (event lifecycle: message / agent / turn); herdr agent-automation (lifecycle state is the wait primitive).

## Finding 5 — feedback capture for ticket 06

`herdr agent read <name> --source recent-unwrapped --lines N` returns the pane's recent output (ANSI stripped, unwrapped). For full-screen agents, idle reads can pull alternate-screen history via the mouse-scroll interface. The script captures implementer and verifier output this way each round and routes both back to itself for human surfacing (ticket 06). If a full response isn't readable from the pane, herdr's recipe is: ask the agent to write it as Markdown in a temp dir and reply with the file path, then read the file — a robust fallback for long reviews.

Source: https://herdr.dev/docs/agent-automation/ (Alternate-screen history reads, Recipes); https://herdr.dev/docs/socket-api/ (Reading panes).

## Recipe summary for downstream tickets

- **04 (to-tickets)** can assume the orchestrator submits one prompt per implementation ticket via `herdr agent prompt impl "$TICKET_BODY" --wait --until done`; the ticket body is the prompt payload — so the to-tickets ticket schema should produce a self-contained, model-bound work unit readable as a prompt.
- **05 (orchestrator contract)** can target Pattern A above; language choice still open, but the script is a thin herdr-CLI driver + a round counter + a feedback router (read both panes → surface to human). RPC mode is a documented fallback, not the default.
- **06 (feedback & escalation)** uses `agent read` of both panes per round for discussion capture; `agent wait --until blocked` for escalation detection; a new Wayfinder ticket + leaving the panes idle (not re-prompting) is the block; resume = re-prompt with the resolved answer.
- **Setup sub-task (fold into 01 or 07):** `herdr integration install pi` + `herdr integration status` before the first run.

## Open / not covered here

- Exact mechanism of herdr's pi integration hook on the pi side (pi docs don't document it; verify by running `herdr integration install pi` and `herdr agent explain <pane>`). If hooks are unavailable, screen-manifest fallback still works.
- Whether qwen3.6 via Ollama cloud and deepseek-v4-flash expose clean tool-use over `openai-completions` — that's ticket 02.