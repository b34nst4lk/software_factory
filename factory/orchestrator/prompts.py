"""Prompt templates — the orchestrator stays skill/model-agnostic by embedding
``/skill:name`` tokens (05 Q7) and the fenced-YAML verdict instruction (06 Q1).

These are pure string builders; the orchestrator prepends cycle/worktree/resolution
context around the to-tickets-authored implementer body (which itself embeds
``/skill:tdd``) and around the verifier's 6-gate checklist.
"""

from __future__ import annotations

GATE_NAMES = (
    "meets the requirement (the acceptance behaviours)",
    "requirement contradictions / callouts (escalate if ambiguous — never assume)",
    "over-engineering",
    "coding convention (non-automatable parts; ruff/black handle the rest)",
    "code review via /skill:code-review against the diff",
    "behavior coverage (behaviors captured via fuzzing/hypothesis; tests map to behaviors)",
)


def resolution_block(ticket_id: str, answer: str) -> str:
    return f"Resolution (ticket {ticket_id}): {answer}\n\n"


def implementer_prompt(
    *,
    ticket_body: str,
    cycle: int,
    worktree: str,
    branch: str,
    prior_feedback: str | None,
    resolution: str | None,
    env_hint: str | None = None,
) -> str:
    parts: list[str] = []
    parts.append(f"[orchestrator context] worktree: {worktree} | branch: {branch} | cycle: {cycle}")
    if env_hint:
        parts.append(f"[env] {env_hint}")
    parts.append(
        "Build test-first via /skill:tdd. Stay within scope_files. When test-green "
        "and within scope, stop and summarize what changed and the test results."
    )
    if resolution is not None:
        parts.append(resolution_block("escalation", resolution))
    if prior_feedback:
        parts.append(
            f"Prior verifier feedback (address this in cycle {cycle}):\n{prior_feedback}\n"
        )
    parts.append(ticket_body)
    return "\n".join(parts) + "\n"


def verifier_prompt(
    *,
    implementer_output: str,
    verify: list[str],
    cycle: int,
    resolution: str | None,
) -> str:
    parts: list[str] = []
    if resolution is not None:
        parts.append(resolution_block("escalation", resolution))
    parts.append(f"[verifier context] cycle: {cycle}")
    parts.append("Review the implementer's output below against these 6 gates:")
    for i, name in enumerate(GATE_NAMES, start=1):
        parts.append(f"  Gate {i}: {name}")
    if verify:
        parts.append("Ticket verify criteria:")
        for v in verify:
            parts.append(f"  - {v}")
    parts.append(
        "Run gate 5 via /skill:code-review against the diff. Any gate may return "
        "BLOCKED (gate 2 is the dedicated contradictions gate). End your response "
        "with a fenced YAML verdict block:"
    )
    parts.append("```yaml")
    parts.append("overall: PASS | FAIL | BLOCKED")
    parts.append("gates:")
    parts.append("  - gate: <name>")
    parts.append("    status: PASS | FAIL | BLOCKED")
    parts.append('    feedback: "<concrete fix>"   # on FAIL')
    parts.append('    escalation: "<ambiguity>"    # on BLOCKED')
    parts.append("```")
    parts.append(
        "CRITICAL — write the verdict to a file so the orchestrator reads exact YAML "
        "(pane line-wrapping corrupts inline YAML). Use the `!` bash tool to write "
        "`.verdict.yaml` in the worktree, then end your reply with one line "
        "`VERDICT_FILE: .verdict.yaml`. The file must be valid YAML with `overall:` "
        "and a `gates:` list (no fence, no wrapping)."
    )
    parts.append("--- implementer output ---")
    parts.append(implementer_output)
    return "\n".join(parts) + "\n"


def pr_fix_prompt(*, pr_number: int, comments: str) -> str:
    return (
        f"[orchestrator context] PR #{pr_number} requested changes.\n"
        "Address each reviewer comment. For each comment, decide addressed or "
        "dismissed and reply with a fenced YAML block:\n"
        "```yaml\n"
        "items:\n"
        '  - comment_id: "<id>"\n'
        "    action: addressed | dismissed\n"
        '    reason: "<why>"   # required on dismissed\n'
        "```\n"
        "`addressed` -> commit (pre-commit guard) and the in-pane 6-gate verifier "
        "will re-run before push. `dismissed` -> your reason is posted as a PR reply, "
        "no code change, no push.\n\n"
        "--- requested changes ---\n"
        f"{comments}\n"
    )
