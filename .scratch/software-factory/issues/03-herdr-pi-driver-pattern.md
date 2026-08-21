# 03 — herdr + pi driver pattern

Type: research
Status: resolved
Blocked by:

## Question

Confirm how a deterministic script drives pi agents through herdr, so the orchestrator-script design (05) and the to-tickets handoff (04) can target it. Specifically:
1. pi as a supported herdr `--kind` and how its lifecycle hooks install (`herdr integration install pi`? a pi-side hook? screen-manifest fallback?).
2. The script primitive sequence: `herdr workspace create`, `tab create`, `pane split`, `agent start <name> --kind pi --pane <id> -- <pi args/model>`, `agent prompt <name> "..." --wait --until done|blocked --timeout`, `agent read <name> --source recent-unwrapped --lines N`.
3. How to bind a specific model (deepseek-v4-flash / qwen3.6) to a pi agent in a pane (pi custom-provider via env var or flag).
4. How the script distinguishes `blocked` (approval/escalation) from `done`, and how it reads implementer↔verifier output for feedback routing (06).

Read herdr's agent-automation + agents + socket-api docs and pi's lifecycle-hook docs. Output: a driver-pattern recipe + a minimal working command sequence, as a context pointer here; nothing built.

## Answer

Resolved 2026-08-19. A deterministic script drives pi agents through herdr using **Pattern A (herdr-interactive)**: create workspace/tab/panes → `herdr agent start impl --kind pi --pane X -- --model deepseek-v4-flash` (and `ver`/`qwen3.6`) → `herdr agent prompt <name> "$prompt" --wait --until done|blocked` → `herdr agent read <name> --source recent-unwrapped --lines N` for feedback. pi is a first-class herdr `--kind` with lifecycle hooks once `herdr integration install pi` is run (screen-manifest fallback otherwise). Model binding is pi's `--model provider/id` arg forwarded after `--`; models must be registered in `~/.pi/agent/models.json` (ticket 02). herdr provides lifecycle **state** (working/blocked/done/idle); the **script owns the cycle counter** — one cycle ≈ one implementer→verifier round. pi RPC mode (`--mode rpc`, JSON over stdin/stdout) is a documented fallback for sub-turn granularity but bypasses herdr's persistence/sidebar, so not the default. Feedback capture = `agent read` of both panes each round; escalation = `agent wait --until blocked` + new Wayfinder ticket + leave panes idle until resolved.

Full findings + command recipe: [research/03-herdr-pi-driver-pattern.md](../research/03-herdr-pi-driver-pattern.md)

Unblocks: 04 (to-tickets skill design), 05 (orchestrator script contract). Setup sub-task surfaced for 01/07: `herdr integration install pi`.