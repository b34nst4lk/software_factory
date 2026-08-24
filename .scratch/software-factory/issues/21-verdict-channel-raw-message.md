# 21 — verdict channel unreliable: reads UI terminal text (chrome) instead of pi's raw message

Type: bug
Status: resolved
Blocked by:
Found by: decision-17 impl-02 rerun (2026-08-24). Defect in decision-15's verdict channel.

## Question / Bug

The orchestrator parses the verifier's verdict from **terminal text** (`herdr agent read
--source recent-unwrapped`), which includes herdr's UI chrome. Decision-15's `parse_trailer`
reads the **last non-empty line** — but herdr appends chrome **after** the trailer (two `────`
separators, the `~/path (branch)` cwd line, and the `↑…↓… <model> • <profile>` status bar), so
the trailer is no longer the last non-empty line → `parse_trailer` reads the status bar → no
match → `UNPARSEABLE` → bounded re-prompt → still `UNPARSEABLE` → **HUMAN_GATE**.

This reproduced on decision-17 impl-02 (a long verifier output: code-review gate + file reads
→ trailing chrome). The verifier also **omitted `VERDICT_FILE:`**, so the file-step did not
fire either. It will block **every** unit with a long verifier output, not just impl-02.

Root cause (seam): the orchestrator reads the agent's **rendered terminal surface** instead of
the agent's **raw message**. Terminal text is the wrong seam for reliable parsing.

## Fix (settled: read pi's raw last message via the session JSONL)

herdr's `agent read` only returns terminal snapshots (no message-level source). But
`herdr agent get <name>` exposes pi's **session JSONL path** (`agent_session.value`), which
contains pi's **raw assistant messages** (no chrome, no wrapping). Verified: the verifier's
last raw assistant message ends **exactly** with `VERDICT overall=PASS`.

Build (manual, test-first, on main — the factory cannot run to fix its own broken verdict
channel):

1. `herdr.agent_last_message(name) -> str`: `agent get <name>` → `agent_session.value` →
   read the JSONL → return the last assistant message's text. Add to `HerdrPort`, the real
   `Herdr`, and `MockHerdr` (a `feed_last_message` + FIFO return, mirroring `feed_read`).
2. `cycle.run_cycle` reads the verifier's verdict from `herdr.agent_last_message(ver_name)`
   (raw) instead of `herdr.agent_read(...)` (terminal). The raw message's trailer IS the last
   line → `parse_trailer` works; `VERDICT_FILE:` + the `.verdict.yaml` file still work when
   emitted. The re-prompt re-reads the raw last message (the JSONL appends the new turn).
3. Regression test: a verifier whose **terminal** output has trailing chrome (would fail the
   old `parse_trailer`) but whose **raw** last message ends with `VERDICT overall=PASS` → the
   cycle routes PASS, not HUMAN_GATE.

## Post-mortem → /improve-codebase-architecture (follow-up, not this ticket)

The deeper seam finding: the orchestrator reads **terminal text** for agent output in more
places — notably `impl_out` (the implementer output passed to the verifier prompt). A
follow-up `/improve-codebase-architecture` pass should surface every `agent_read` call site
and switch each to `agent_last_message` (raw) where the content is meant to be the agent's
message, keeping terminal reads only for genuine pane-surface control. This ticket fixes the
critical path (the verdict); the rest is the follow-up.

## Answer

Fixed 2026-08-24 (manual, test-first, on main — the factory cannot run with a broken
verdict channel). The orchestrator now reads the verifier's verdict from pi's **raw last
assistant message** (session JSONL), not the terminal surface.

- `herdr.agent_last_message(name)`: `agent get <name>` → `agent_session.value` (pi
  session JSONL path) → `_last_assistant_text` returns the last assistant message's text
  (content as string or list of `{text}` blocks). Added to `HerdrPort`, the real `Herdr`,
  and `MockHerdr` (`feed_last_message` + a `feed_read` fallback so existing tests stay green).
- `cycle.run_cycle` reads both verifier turns (initial + after the re-prompt) via
  `agent_last_message`, not `agent_read`. The raw message's trailer IS the last line
  (no chrome) → `parse_trailer` works; `VERDICT_FILE:` + the `.verdict.yaml` file still
  work when emitted. The re-prompt re-reads the raw last message (the JSONL appends the new
  turn).
- Regression test `test_verdict_parsed_from_raw_message_despite_terminal_chrome`: a
  verifier whose terminal surface has trailing chrome (would fail the old `parse_trailer`)
  but whose raw message ends with `VERDICT overall=PASS` → the cycle routes DONE, not
  HUMAN_GATE. Plus `agent_last_message` unit tests (real JSONL parse; mock fallback).

Post-mortem (seam) deferred to a follow-up `/improve-codebase-architecture` pass: the
orchestrator still reads terminal text for `impl_out` (the implementer output passed to
the verifier prompt) and other `agent_read` sites; each should move to the raw message where
the content is the agent's message, keeping terminal reads only for genuine pane-surface
control.