# 05a — Gleam viability for the orchestrator script

Surfaced during 05 grilling Q1 (language). Question: is Gleam a viable language for the deterministic orchestrator?

## Environment (this machine)

- `gleam`: **not installed**
- `erl` / BEAM: **not installed**
- `rebar3`, `elixir`: not installed
- `python3.14` + `pyyaml 6.0.3`: present; `node 22`, `bash 5.3`, `git`, `pi` present; `herdr` not installed (build step)

Choosing Gleam means installing the Gleam compiler **and** Erlang/OTP on this machine and on every target project that runs the factory.

## Library viability (the orchestrator's concrete needs)

### YAML frontmatter (04's Work Unit schema: id/decision/title/scope_files/acceptance/verify/model/depends_on/status)
Multiple Gleam YAML libs exist — all new/niche but functional for our simple flat frontmatter:
- **`taffy` v1.1.2** — YAML 1.2, pure Gleam + optional C NIF, Erlang+JS targets. API: `parse`, `get`, `as_string`, `as_int`, `as_list`. ~121 all-time downloads, last updated Aug 2026. Best fit.
- `yamleam` v1.0.0 — pure Gleam, very new (Apr 2026), ~122 all-time.
- `yum` v1.0.0 — tooling-grade YAML 1.2 + diagnostics + emit, Erlang+JS, very new (Jun 2026), ~5 all-time.

Any of these handles our flat frontmatter trivially.

### Subprocess (drive `herdr agent start/prompt/read/wait`)
- **`child_process` v2.1.2** — cross-platform (Erlang+JS), run shell commands, capture output, inherit stdio, stream lines. Strongest fit (we shell out to herdr and capture stdout; panes themselves are owned by herdr).
- `shellout` v1.8.0 — cross-platform shell ops, exit codes. Mature-ish.
- `gleam_erlexec` — BEAM-only, async exec with pty + stdin pipe + monitor. More powerful (useful if we ever drive panes with interactive stdin), but pulls an Erlang dep.
- `gleamyshell` — **unmaintained**; author abandoned Gleam citing "too many breaking changes within minor version bumps."

### File glob / IO / CLI args
- File read/write: `simplifile` (standard choice).
- Glob: `simplifile` has `read_directory` (recursive); pattern matching `.scratch/<effort>/impl/*.md` is a small recursive walk — fine.
- CLI args: `argv` in stdlib (`gleam_erlang`/`gleam/javascript` argv).

## What Gleam buys us
- **Strong static typing + algebraic data types + Result/option** — genuinely good fit for the state machine: `status` enum (`Pending|Implementing|Verifying|Done|Blocked|Escalated`), verifier verdict enum (`Pass|Fail|Blocked`), pattern match on branches. No null errors.
- **BEAM actor model + lightweight processes** — if the orchestrator ever grows to **parallel work-unit panes** (the Q4 future parameter), BEAM supervisors/actors would model "N implementer+verifier pairs under a supervisor" more cleanly than python asyncio.
- Compiled, fast, no GIL.

## Costs / risks
1. **Toolchain install** — Gleam + Erlang/OTP must be installed here and on every factory target. python3 is universal on Linux/macOS; Erlang is not. Real friction for a "base for other projects."
2. **Ecosystem maturity** — the relevant libs (taffy/yum/child_process) are new/low-download; one prominent shell lib was abandoned citing breaking-change churn. Risk for a tool meant to be a durable base.
3. **"Deterministic script" framing mismatch** — Gleam is a compiled BEAM application (`gleam run` or an escript/release), more ceremony than a ~150-line script.
4. **Modest payoff at current size** — the state machine is small (one enum + counter + topo sort + 3-branch loop). Gleam's safety pays off more on large state surfaces; here it's a small script python handles cleanly.

## Assessment
**Technically viable** — YAML via taffy, subprocess via child_process, clean enums/Result for the state machine, and BEAM is a genuine asset *if* the orchestrator grows into a typed concurrent multi-pane supervisor.

**Not recommended for the prototype** — the costs (toolchain install here + on every target, niche/churning libs, compiled-app ceremony, non-universal runtime) outweigh the modest type-safety benefit for a ~150-line deterministic script, when python3 + pyyaml is already present, universal, and zero-install.

**Nuanced recommendation**: python3 for the prototype, but structure the python so the **state-machine boundary** (the status/verdict enums + the branch logic) is a clean seam — that's the part a future Gleam rewrite would replace if the orchestrator grows into parallel panes and the type-safety/concurrency payoff becomes worth the toolchain cost. Revisit Gleam when/if Q4's parallel-work-units future parameter is actually taken.