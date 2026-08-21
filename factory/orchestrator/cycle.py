"""The per-unit cycle loop — implementer ↔ verifier strictly alternating.

This is the build-time heart of the spine (05 Q3, Q4; ticket 09). One unit, one
worktree, two already-started herdr panes (impl-NN, ver-NN). Each cycle: prompt the
implementer (`--wait --until done`), read it, prompt the verifier (`--wait --until
done|blocked`), read it, parse the fenced-YAML verdict, route it, then mutate the
impl frontmatter **value-only** (cycle + last_verdict) and append a run.log line and
commit — so every cycle is a guarded git commit.

Routing (06 Q1):
  DONE       -> return; run.py raises the PR.
  RETRY      -> inject the FAIL gates' feedback into the next implementer cycle.
  ESCALATE   -> author a Wayfinder ticket via escalate, park (run.py owns the park).
  HUMAN_GATE -> unparseable verdict; never-assume; surface raw text to the human.
  CAP_REACHED -> 5-cycle backstop; run.py gates the human.

The per-cycle git commit is injected (``commit``) so the loop is testable without a
live git worktree. The orchestrator guarantees cross-model binding every cycle by
binding the implementer pane to ``config.implementer_model`` and the verifier pane to
``config.verifier_model`` (different families) — run.py does the ``agent_start``.
"""

from __future__ import annotations

import enum
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import escalate
import prompts
import tickets
import verdict
from herdr import HerdrPort

CommitFn = Callable[[str, int, str, str], None]


class CycleOutcome(enum.Enum):
    DONE = "done"
    ESCALATE = "escalate"
    HUMAN_GATE = "human_gate"
    CAP_REACHED = "cap_reached"


@dataclass(frozen=True)
class Panes:
    impl_name: str
    ver_name: str
    impl_pane: str
    ver_pane: str


@dataclass(frozen=True)
class CycleResult:
    outcome: CycleOutcome
    unit_id: str
    final_cycle: int
    escalation_paths: list[str] = field(default_factory=list)
    raw_verdict: str | None = None


class _CfgLike(Protocol):
    @property
    def cycle_cap(self) -> int: ...

    @property
    def prompt_timeout_ms(self) -> int: ...

    @property
    def read_lines(self) -> int: ...


_VERDICT_FILE_RE = re.compile(r"VERDICT_FILE:\s*(\S+)", re.MULTILINE)


def _parse_verdict(ver_out: str, worktree: str) -> verdict.Verdict:
    """Parse the verifier verdict, preferring a file the verifier wrote to disk.

    Pane line-wrapping corrupts inline fenced YAML (the live smoke hit this), so the
    verifier is asked to write `.verdict.yaml` and reply `VERDICT_FILE: <path>`. We
    read that file (resolved against the worktree) as raw YAML; fall back to the pane.
    """
    m = _VERDICT_FILE_RE.search(ver_out)
    if m:
        path = m.group(1)
        full = path if os.path.isabs(path) else os.path.join(worktree, path)
        try:
            return verdict.parse_verdict_yaml(Path(full).read_text())
        except OSError:
            pass  # fall through to pane parsing
    return verdict.parse_verdict(ver_out)


def run_cycle(
    *,
    unit: tickets.ImplTicket,
    config: _CfgLike,
    herdr: HerdrPort,
    worktree: str,
    branch: str,
    panes: Panes,
    commit: CommitFn,
    issues_dir: str,
    next_esc_number: int = 1,
    resolution: str | None = None,
    cap_override: int | None = None,
) -> CycleResult:
    cap = cap_override if cap_override is not None else config.cycle_cap
    prior_feedback: str | None = None
    # Seed from the persisted frontmatter `cycle` (git-as-state: the frontmatter is the
    # source of truth, and the in-memory unit.cycle may be stale across a park/resume).
    # The cap is a TOTAL ceiling across the unit's whole life (05 Q3), not per-resume.
    cycle_no = tickets.parse_impl_file(unit.path).cycle
    while cycle_no < cap:
        cycle_no += 1
        # 1. implementer
        impl_prompt = prompts.implementer_prompt(
            ticket_body=unit.body,
            cycle=cycle_no,
            worktree=worktree,
            branch=branch,
            prior_feedback=prior_feedback,
            resolution=resolution,
            env_hint=getattr(config, "implementer_env_hint", "") or None,
        )
        herdr.agent_prompt(
            panes.impl_name,
            impl_prompt,
            until=["idle", "done", "blocked"],
            timeout_ms=config.prompt_timeout_ms,
        )
        impl_out = herdr.agent_read(panes.impl_name, config.read_lines)

        # 2. verifier
        ver_prompt = prompts.verifier_prompt(
            implementer_output=impl_out,
            verify=unit.verify,
            cycle=cycle_no,
            resolution=resolution,
        )
        herdr.agent_prompt(
            panes.ver_name,
            ver_prompt,
            until=["idle", "done", "blocked"],
            timeout_ms=config.prompt_timeout_ms,
        )
        ver_out = herdr.agent_read(panes.ver_name, config.read_lines)

        # 3. parse + route — prefer the verdict FILE the verifier wrote (pane
        #    wrapping corrupts inline YAML); fall back to the pane's fenced block.
        v = _parse_verdict(ver_out, worktree)
        action = verdict.route(v)
        overall_str = v.overall.value

        # 4. state: value-only frontmatter + append-only run.log + guarded commit.
        #    status persists the lifecycle (04): done/parked at the terminal cycle,
        #    in_progress on a retry cycle (a capped unit is still in_progress).
        if action is verdict.Action.DONE:
            status_str = "done"
        elif action is verdict.Action.ESCALATE:
            status_str = "parked"
        else:  # RETRY
            status_str = "in_progress"
        tickets.write_frontmatter_value(
            unit.path, cycle=cycle_no, last_verdict=overall_str, status=status_str
        )
        tickets.append_run_log(worktree, f"{unit.id} c{cycle_no} {overall_str}")
        commit(unit.id, cycle_no, overall_str, worktree)
        herdr.report_metadata(panes.impl_pane, f"{unit.id} c{cycle_no} {overall_str}")

        if action is verdict.Action.DONE:
            return CycleResult(CycleOutcome.DONE, unit.id, cycle_no)
        if action is verdict.Action.ESCALATE:
            path = escalate.create_escalation_ticket(
                issues_dir=issues_dir,
                unit_id=unit.id,
                unit_title=unit.title,
                cycle=cycle_no,
                escalations=v.escalations or ["verifier BLOCKED (no reason given)"],
                number=next_esc_number,
            )
            return CycleResult(CycleOutcome.ESCALATE, unit.id, cycle_no, escalation_paths=[path])
        if action is verdict.Action.HUMAN_GATE:
            return CycleResult(CycleOutcome.HUMAN_GATE, unit.id, cycle_no, raw_verdict=ver_out)
        # RETRY: collect feedback -> next implementer cycle
        prior_feedback = "\n".join(v.feedbacks) or "verifier FAIL (no concrete feedback)"

    return CycleResult(CycleOutcome.CAP_REACHED, unit.id, cycle_no)
