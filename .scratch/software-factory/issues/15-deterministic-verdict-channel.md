# 15 — deterministic verdict channel

Type: task
Status: resolved
Blocked by:
Graduated from: 07 (live smoke observations). Next frontier after 07.

## Question

The verifier verdict retrieval is flaky: the model is *instructed* to write `.verdict.yaml`
and reply `VERDICT_FILE:`, but it doesn't always (the smoke's cycle 1 didn't → unparseable
→ human gate). The verdict **content** is inherently LLM-generated, but the **channel** must
be reliable: the orchestrator must always either get a parseable verdict or surface the
never-assume human gate — never silently guess. Today `cycle._parse_verdict` reads the file
if `VERDICT_FILE:` is present, else falls back to the pane's fenced YAML (which wraps in
narrow panes).

## Build (design settled: a+b)

1. **File contract** (keep): verifier writes `.verdict.yaml` (raw YAML, `overall` + `gates`)
   and replies `VERDICT_FILE: .verdict.yaml`. The orchestrator reads it.
2. **Compact routing trailer** (new): the verifier's **last line** is
   `VERDICT overall=PASS|FAIL|BLOCKED` — one short line that survives any pane width. The
   orchestrator parses it for **routing** (the spine's deterministic job) even when the file
   is missing/malformed. The long `feedback`/`escalation` text still comes from the file
   (best-effort); if the file is missing on BLOCKED, the re-prompt (below) or the human gate
   surfaces it.
3. **Bounded re-prompt** (new): if neither the file nor the trailer yields a parseable
   verdict, the orchestrator re-prompts the verifier **once** with a strict "write exactly
   this to `.verdict.yaml` and end with `VERDICT overall=X`; you wrote nothing parseable."
   If that still fails → the existing never-assume human gate (no silent guess).
4. **Human gate floor** (exists): unparseable after the re-prompt → HUMAN_GATE.

`verdict.py` gains `parse_trailer(text) -> Overall | None` (parses `VERDICT overall=X`);
`cycle._parse_verdict` becomes: file → trailer → (re-prompt once) → file/trailer →
HUMAN_GATE. Testable in `--mock` (feed a pane with only the trailer, only the file, neither,
a malformed file + good trailer, etc.). Updates `prompts.verifier_prompt` to require the
trailer as the last line.

## Answer

Resolved 2026-08-21 (design settled via the 07 smoke + the verdict/resumability grilling;
no further wayfinder exploration needed — this is a build task). The deterministic verdict
channel is **a + b** (detail in the Build section above):

1. **File contract**: the verifier writes `.verdict.yaml` (raw YAML: `overall` + `gates`)
   and replies `VERDICT_FILE: .verdict.yaml`; the orchestrator reads it.
2. **Compact routing trailer**: the verifier's **last line** is `VERDICT overall=PASS|FAIL|BLOCKED`
   — one short line that survives any pane width; the orchestrator parses it for **routing**
   (PASS→done / FAIL→retry / BLOCKED→escalate) even when the file is missing/malformed. The
   long `feedback`/`escalation` text comes from the file (best-effort).
3. **Bounded re-prompt**: if neither file nor trailer yields a parseable verdict, re-prompt
   the verifier **once** with a strict "write exactly this to `.verdict.yaml` and end with
   `VERDICT overall=X`; your previous verdict was unparseable." If still no parseable
   verdict → the existing never-assume **human gate** (no silent guess).

`verdict.py` gains `parse_trailer(text) -> Overall | None`; `cycle._parse_verdict` becomes
file → trailer → (re-prompt once) → file/trailer → HUMAN_GATE; `prompts.verifier_prompt`
requires the trailer as the last line. Testable in `--mock`. Subsumes the "cycle-1 file
not written" observation from the smoke.

<!-- filled when built -->