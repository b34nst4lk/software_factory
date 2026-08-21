"""The main loop — topo → worktree-per-unit → cycle → pipeline; stdin gates + sidebar.

Owns the per-unit lifecycle (05 Q4): glob impl → topo-sort by depends_on → worktree per
unit → cycle loop → pipelined across units (next starts at `done`, not after merge) → on
`done` raise PR (if pr_stage) → poll reviews → merge gate → route/dismissal. Park-not-halt
on escalation with file-driven resume (06 Q2/Q3). Stdin gates c/s/w/m/q; per-cycle facts
pushed to the herdr sidebar via ``pane report-metadata``.

All system boundaries are injected (herdr, gh, gitops, stdin) so the loop is exercised in
``--mock`` without live panes/models/git/github. ``cycle.py`` owns the per-unit build-time
cycle; this module owns the cross-unit pipeline + PR stage + human gates.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import config as config_mod
import cycle
import escalate
import pr as pr_mod
import prompts
import tickets
import verdict
from gitops import GitOpsPort
from herdr import HerdrPort
from pr import GhPort

PARK_POLL_S = 5  # cadence for re-scanning parked units' escalation tickets


def _next_issue_number(issues_dir: str) -> int:
    """Next free issue number: 1 + the highest NN- prefix already in the tracker.

    Escalations live in the shared ``issues/`` namespace (06 Q2), so they must number
    past existing decisions — not start at 1 and collide with ``01-repo-bootstrap``.
    """
    import os
    import re

    nums: list[int] = []
    try:
        names = os.listdir(issues_dir)
    except OSError:
        return 1
    for name in names:
        m = re.match(r"(\d+)-", name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


StdinFn = Callable[[], str]


class UnitStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PARKED = "parked"
    AWAITING_PR = "awaiting_pr"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class UnitState:
    unit: tickets.ImplTicket
    branch: str
    worktree: str
    panes: cycle.Panes
    status: UnitStatus = UnitStatus.PENDING
    escalation_paths: list[str] = field(default_factory=list)
    pr_number: int | None = None
    last_outcome: str = ""
    cap_override: int | None = None

    @property
    def id(self) -> str:
        return self.unit.id


@dataclass
class Orchestrator:
    config: config_mod.Config
    herdr: HerdrPort
    gh: GhPort
    gitops: GitOpsPort
    units: list[tickets.ImplTicket]
    stdin: StdinFn
    next_esc_number: int = 1
    on_park: Callable[[UnitState], None] | None = None
    park_poll_budget: int = 0
    sleep_fn: Callable[[float], None] = time.sleep
    _root_pane: str = ""
    _log: list[str] = field(default_factory=list)

    # ---- lifecycle ----
    def run(self) -> dict[str, str]:
        self.next_esc_number = _next_issue_number(self.config.issues_dir)
        topo = tickets.topo_sort(self.units)
        states: dict[str, UnitState] = {
            u.id: UnitState(unit=u, branch=u.id, worktree="", panes=_empty_panes(u.id))
            for u in topo
        }
        done: set[str] = set()
        self._root_pane = self.herdr.workspace_create(self.config.repo_path, "factory")
        safety = 0
        park_polls = 0
        while safety < 10000:
            safety += 1
            progressed = self._sweep(states, done)
            if progressed:
                park_polls = 0
                continue
            awaiting = [s for s in states.values() if s.status == UnitStatus.AWAITING_PR]
            parked = [s for s in states.values() if s.status == UnitStatus.PARKED]
            if awaiting:
                # PRs awaiting human review: poll on the configured cadence (no timeout).
                self.sleep_fn(self.config.pr_poll_cadence_s)
                self._poll_prs(states, done)
                continue
            if parked:
                # file-driven resume (06 Q2): re-scan parked units' tickets each loop;
                # the human/wayfinder resolves them out-of-band. Park, don't halt.
                # park_poll_budget bounds this for tests; 0 = wait indefinitely (live).
                park_polls += 1
                if self.park_poll_budget and park_polls >= self.park_poll_budget:
                    break
                self.sleep_fn(PARK_POLL_S)
                continue
            break  # all units terminal
        return {uid: st.status.value for uid, st in states.items()}

    def _sweep(self, states: dict[str, UnitState], done: set[str]) -> bool:
        progressed = False
        # 1. resume parked units whose escalations resolved (file-driven resume)
        for st in states.values():
            if (
                st.status == UnitStatus.PARKED
                and st.escalation_paths
                and escalate.all_resolved(st.escalation_paths)
            ):
                progressed |= self._resume(st, done)
        # 2. start ready units (deps done, pending) — pipelined: next starts at done
        for u in states.values():
            if u.status == UnitStatus.PENDING and all(d in done for d in u.unit.depends_on):
                self._start_unit(u)
                self._run_one(u, done, resolution=None)
                progressed = True
                break  # one new unit per sweep; PRs still polled below
        # 3. poll PRs for awaiting-merge units (pipelined: implementer advances meanwhile)
        progressed |= self._poll_prs(states, done)
        return progressed

    # ---- per-unit ----
    def _start_unit(self, st: UnitState) -> None:
        st.worktree = self.gitops.worktree_add(st.branch, parent=self.config.worktree_parent)
        _link_venv(self.config.repo_path, st.worktree)
        wt_path = self._worktree_unit_path(st)
        if not os.path.exists(wt_path):
            os.makedirs(os.path.dirname(wt_path), exist_ok=True)
            Path(wt_path).write_text(Path(st.unit.path).read_text())
        st.unit = dataclasses.replace(st.unit, path=wt_path)
        impl_name = st.id
        ver_name = "ver-" + st.id.split("-")[-1]
        impl_pane = self.herdr.pane_split(self._root_pane, "right", cwd=st.worktree)
        ver_pane = self.herdr.pane_split(self._root_pane, "right", cwd=st.worktree)
        self.herdr.agent_start(
            impl_name, impl_pane, self.config.implementer_model, approve=self.config.no_approve
        )
        self.herdr.agent_start(
            ver_name, ver_pane, self.config.verifier_model, approve=self.config.no_approve
        )
        st.panes = cycle.Panes(impl_name, ver_name, impl_pane, ver_pane)

    def _worktree_unit_path(self, st: UnitState) -> str:
        rel = os.path.relpath(st.unit.path, self.config.repo_path)
        return os.path.join(st.worktree, rel)

    def _commit_fn(self, st: UnitState) -> cycle.CommitFn:
        def commit(unit_id: str, c: int, overall: str, worktree: str) -> None:
            self.gitops.commit_cycle(worktree, f"{unit_id} c{c} {overall}")

        return commit

    def _run_one(self, st: UnitState, done: set[str], *, resolution: str | None) -> None:
        result = cycle.run_cycle(
            unit=st.unit,
            config=self.config,
            herdr=self.herdr,
            worktree=st.worktree,
            branch=st.branch,
            panes=st.panes,
            commit=self._commit_fn(st),
            issues_dir=self.config.issues_dir,
            next_esc_number=self.next_esc_number,
            resolution=resolution,
            cap_override=st.cap_override,
        )
        st.last_outcome = result.outcome.value
        if result.outcome is cycle.CycleOutcome.DONE:
            self._on_done(st, done)
        elif result.outcome is cycle.CycleOutcome.ESCALATE:
            st.escalation_paths = list(result.escalation_paths)
            st.status = UnitStatus.PARKED
            self.next_esc_number += 1
            msg = f"{st.id} BLOCKED -> escalated to {result.escalation_paths[0]}"
            self._log.append(msg)
            self.herdr.report_metadata(st.panes.impl_pane, msg)
            print(msg)
            if self.on_park is not None:
                self.on_park(st)
        elif result.outcome is cycle.CycleOutcome.HUMAN_GATE:
            self._gate(st, done, raw=result.raw_verdict)
        elif result.outcome is cycle.CycleOutcome.CAP_REACHED:
            self._gate(st, done, raw=None, cap=True)

    def _resume(self, st: UnitState, done: set[str]) -> bool:
        res = escalate.resolutions_for(st.escalation_paths)
        if any(escalate.is_cancellation(a) for _, a in res):
            st.status = UnitStatus.CANCELLED
            self._log.append(f"{st.id} cancelled by resolution")
            return True
        resolution = "".join(escalate.resolution_block(p, a) for p, a in res)
        tickets.append_run_log(st.worktree, f"{st.id} resolution received")
        self._run_one(st, done, resolution=resolution)
        return True

    def _on_done(self, st: UnitState, done: set[str]) -> None:
        if self.config.pr_stage and self.config.gh_repo:
            self.gitops.push_branch(st.branch)
            pr_num = self.gh.pr_create(
                st.branch,
                st.branch,
                "main",
                f"[{st.id}] {st.unit.title}",
                f"Work unit {st.id} verifier-passed (6 gates).",
            )
            st.pr_number = pr_num
            st.status = UnitStatus.AWAITING_PR
            self._log.append(f"{st.id} done -> PR #{pr_num}")
        else:
            st.status = UnitStatus.DONE
            done.add(st.id)
            self._log.append(f"{st.id} done (pr_stage off)")

    # ---- PR stage ----
    def _poll_prs(self, states: dict[str, UnitState], done: set[str]) -> bool:
        progressed = False
        for st in states.values():
            if st.status != UnitStatus.AWAITING_PR or st.pr_number is None:
                continue
            reviews = self.gh.api_reviews(self.config.gh_repo, st.pr_number)
            gate = pr_mod.merge_gate(
                reviews,
                human_login=self.config.human_login,
                sourcery_login=self.config.sourcery_reviewer_login,
            )
            if gate.mergable:
                self.gh.pr_merge(st.pr_number, squash=True)
                self.gitops.worktree_remove(st.worktree)
                self.gitops.tag_archive(st.branch)
                st.status = UnitStatus.DONE
                done.add(st.id)
                self._log.append(f"{st.id} PR #{st.pr_number} merged")
                progressed = True
            elif gate.changes_requested_from:
                self._pr_fix_cycle(st, reviews)
                progressed = True
            # advisory-only or awaiting human: no progression this sweep
        return progressed

    def _pr_fix_cycle(self, st: UnitState, reviews: list[dict[str, str]]) -> None:
        comments = _format_comments(reviews)
        self.herdr.agent_prompt(
            st.panes.impl_name,
            prompts.pr_fix_prompt(pr_number=st.pr_number or 0, comments=comments),
            until="done",
            timeout_ms=self.config.prompt_timeout_ms,
        )
        out = self.herdr.agent_read(st.panes.impl_name, self.config.read_lines)
        routes = pr_mod.parse_dismissals(out)
        any_addressed = False
        for r in routes:
            if r.kind is pr_mod.DismissalKind.ADDRESSED:
                any_addressed = True
            else:
                self.gh.pr_comment(st.pr_number or 0, f"Dismissed ({r.comment_id}): {r.reason}")
        if any_addressed:
            self.gitops.commit_cycle(st.worktree, f"{st.id} pr-fix")
            self.herdr.agent_prompt(
                st.panes.ver_name,
                prompts.verifier_prompt(
                    implementer_output="pr-fix applied",
                    verify=st.unit.verify,
                    cycle=0,
                    resolution=None,
                ),
                until="done",
                timeout_ms=self.config.prompt_timeout_ms,
            )
            vout = self.herdr.agent_read(st.panes.ver_name, self.config.read_lines)
            v = verdict.parse_verdict(vout)
            if verdict.route(v) is verdict.Action.DONE:
                self.gitops.push_branch(st.branch)

    # ---- stdin gates (05 Q5) ----
    def _gate(self, st: UnitState, done: set[str], *, raw: str | None, cap: bool = False) -> None:
        kind = "5-cycle backstop" if cap else "verifier verdict unparseable"
        msg = f"{st.id}: {kind}; (c)ontinue / (s)top / (w)escalate / (q)uit"
        print(msg)
        if raw:
            print("raw verdict:", raw)
        choice = self.stdin().strip().lower() or "c"
        if choice == "q":
            st.status = UnitStatus.CANCELLED
            return
        if choice == "w":
            path = escalate.create_escalation_ticket(
                issues_dir=self.config.issues_dir,
                unit_id=st.id,
                unit_title=st.unit.title,
                cycle=0,
                escalations=["human escalation from gate"],
                number=self.next_esc_number,
            )
            st.escalation_paths = [path]
            st.status = UnitStatus.PARKED
            self.next_esc_number += 1
            return
        # c (continue): re-run the cycle. On the cap backstop the human lifts the
        # ceiling once (overridable per 05 Q3); on an unparseable verdict, just retry.
        if cap:
            st.cap_override = (st.cap_override or self.config.cycle_cap) + 1
        self._run_one(st, done, resolution=None)

    def summary(self) -> dict[str, str]:
        return {}


def _link_venv(repo_path: str, worktree: str) -> None:
    """Symlink the main repo's .venv into the worktree so workers can run tests there.

    The venv is gitignored, so worktrees don't get it; a symlink lets the implementer
    use ``.venv/bin/python -m pytest`` without reinstalling deps. Skipped if absent.
    """
    import os

    src = os.path.join(repo_path, ".venv")
    dst = os.path.join(worktree, ".venv")
    if os.path.isdir(src) and not os.path.exists(dst):
        with contextlib.suppress(OSError):
            os.symlink(src, dst)


def _empty_panes(unit_id: str) -> cycle.Panes:
    ver_name = "ver-" + unit_id.split("-")[-1]
    return cycle.Panes(unit_id, ver_name, "", "")


def _format_comments(reviews: list[dict[str, str]]) -> str:
    return "\n".join(f"- {r.get('user', '?')}: {r.get('state', '')}" for r in reviews)
