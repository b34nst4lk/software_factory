"""Tests for run.py stdin gates + PR-stage fix/dismissal routing (--mock)."""

from __future__ import annotations

import os

import pytest

import config as config_mod
import gitops
import herdr
import pr as pr_mod
import run
import tickets

PASS_VERDICT = """\
```yaml
overall: PASS
gates:
  - {gate: meets_requirement, status: PASS}
  - {gate: contradictions, status: PASS}
  - {gate: over_engineering, status: PASS}
  - {gate: convention, status: PASS}
  - {gate: code_review, status: PASS}
  - {gate: behavior_coverage, status: PASS}
```
"""
UNPARSEABLE_VERDICT = "totally free text, no verdict"
FAIL_VERDICT = """\
```yaml
overall: FAIL
gates:
  - {gate: over_engineering, status: FAIL, feedback: "fix it"}
```
"""
DISMISSAL_YAML = """\
```yaml
items:
  - {comment_id: C1, action: dismissed, reason: "out of scope"}
```
"""

IMPL_BODY = """\
---
id: impl-01
title: greet
scope_files: [factory/greet.py]
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
verify: ["behaviors captured by tests"]
---
Implement greet(name).
"""


def setup(tmp_path, *, pr_stage=False, reviews=None, reviews_queue=None, cap=5):
    repo = str(tmp_path)
    impl_dir = tmp_path / ".scratch" / "sf" / "impl"
    impl_dir.mkdir(parents=True)
    (tmp_path / ".scratch" / "sf" / "issues").mkdir(parents=True)
    impl_file = impl_dir / "01-greet.md"
    impl_file.write_text(IMPL_BODY)
    units = tickets.parse_impl_files([str(impl_file)])
    cfg = config_mod.default(
        repo, "sf", os.path.join(repo, ".scratch", "sf", "impl", "*.md")
    ).with_overrides(
        repo_path=repo,
        worktree_parent=repo,
        pr_stage=pr_stage,
        gh_repo="o/r",
        mock=True,
        cycle_cap=cap,
    )
    m = herdr.MockHerdr()
    gh = pr_mod.MockGh(reviews_fixture=reviews, reviews_queue=reviews_queue)
    gops = gitops.MockGitOps(base=str(tmp_path))
    return units, cfg, m, gh, gops


def test_unparseable_verdict_gate_quit_cancels(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "q",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "cancelled"}


def test_unparseable_verdict_gate_continue_then_pass(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("impl-01", "c2")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}


def test_unparseable_verdict_gate_escalate_parks(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "w",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    result = orch.run()
    assert result["impl-01"] == "parked"
    import os

    esc_files = os.listdir(cfg.issues_dir)
    assert len(esc_files) == 1


def test_cap_reached_gate_quit_cancels(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path, cap=2)
    m.feed_read("impl-01", "c1")
    m.feed_read("impl-01", "c2")
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", FAIL_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "q",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "cancelled"}


def test_cap_reached_gate_continue_lifts_cap_then_pass(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path, cap=2)
    m.feed_read("impl-01", "c1")
    m.feed_read("impl-01", "c2")
    m.feed_read("impl-01", "c3")
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}


def test_pr_changes_requested_dismissed_posts_comment_then_merges(tmp_path):
    # poll 1: human CHANGES_REQUESTED -> route to implementer; dismissed -> pr comment.
    # poll 2: human APPROVED + sourcery APPROVED -> merge.
    poll1 = [
        {"user": "human-reviewer", "state": "CHANGES_REQUESTED"},
        {"user": "sourcery-ai", "state": "APPROVED"},
    ]
    poll2 = [
        {"user": "human-reviewer", "state": "APPROVED"},
        {"user": "sourcery-ai", "state": "APPROVED"},
    ]
    units, cfg, m, gh, gops = setup(tmp_path, pr_stage=True, reviews_queue=[poll1, poll2])
    m.feed_read("impl-01", "impl c1")
    m.feed_read("ver-01", PASS_VERDICT)  # build-time cycle -> done -> PR
    m.feed_read("impl-01", DISMISSAL_YAML)  # pr-fix cycle -> dismissed
    m.feed_read("ver-01", PASS_VERDICT)  # pr-fix verifier re-run (addressed? none here)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}
    assert gh.merged  # eventually merged
    # the dismissed reason was posted as a PR reply
    assert any("out of scope" in body for _num, body in gh.comments)


BLOCKED_VERDICT = """\
```yaml
overall: BLOCKED
gates:
  - {gate: contradictions, status: BLOCKED, escalation: "greet(None) unspecified"}
```
"""


def test_escalation_ticket_numbered_past_existing_issues(tmp_path):
    import os

    units, cfg, m, gh, gops = setup(tmp_path)
    # the tracker already has issues up to 09
    (tmp_path / ".scratch" / "sf" / "issues" / "09-existing.md").write_text(
        "# 9\nType: grilling\nStatus: resolved\n\n## Answer\nx\n"
    )
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=1,
    )
    result = orch.run()
    assert result["impl-01"] == "parked"  # no resolution -> parks and the budget returns
    esc = [f for f in os.listdir(cfg.issues_dir) if f.startswith("10-")]
    assert len(esc) == 1, os.listdir(cfg.issues_dir)


def test_next_issue_number_helper(tmp_path):

    d = tmp_path / "issues"
    d.mkdir()
    assert run._next_issue_number(str(d)) == 1  # empty tracker
    (d / "02-b.md").write_text("x")
    (d / "09-z.md").write_text("x")
    (d / "01-a.md").write_text("x")
    assert run._next_issue_number(str(d)) == 10  # past the highest (09)
    assert run._next_issue_number(str(tmp_path / "nope")) == 1  # missing dir


def test_quit_persists_status_cancelled_to_frontmatter(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)  # -> human gate -> 'q' -> cancelled
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "q",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "cancelled"}
    impl = tmp_path / "sf-impl-01" / ".scratch" / "sf" / "impl" / "01-greet.md"
    assert tickets.parse_impl_file(str(impl)).status == "cancelled"


def test_mock_run_threads_db_path_and_logs_rows(tmp_path):
    # maps to: db_path is threaded from config into run_cycle (not hardcoded); a mock
    # run with a temp db_path produces rows in that DB.
    import state

    units, cfg, m, gh, gops = setup(tmp_path)
    db_path = str(tmp_path / "state.db")
    cfg = cfg.with_overrides(db_path=db_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}
    rows = state.query_cycles(db_path, unit_id="impl-01")
    assert len(rows) == 1
    assert rows[0]["verdict"] == "PASS"
    assert rows[0]["action"] == "DONE"
    assert rows[0]["commit_sha"]  # non-empty sha threaded from the commit closure


def test_ref_advance_assert_passes_when_ref_advances(tmp_path):
    # maps to: after each cycle the impl/NN ref points at the just-made commit; the
    # ref-advance assert passes when the branch ref equals the returned sha.
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}
    # the commit closure staged the governed set (impl ticket + scope_files)
    assert gops.commits[0][2]  # impl_ticket
    assert gops.commits[0][3] == ["factory/greet.py"]  # scope_files


def test_ref_advance_assert_fails_loudly_on_stale_ref(tmp_path):
    # maps to: a regression to dangling commits (branch ref did NOT advance to the
    # just-made commit) fails the ref-advance assert loudly.
    units, cfg, m, gh, gops = setup(tmp_path)

    class StaleGitOps(gitops.MockGitOps):
        def branch_sha(self, worktree, branch):
            return "stale-sha"  # ref did not advance

    gops = StaleGitOps(base=str(tmp_path))
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    with pytest.raises(AssertionError, match="ref-advance failed"):
        orch.run()


# --- impl-03: one herdr space per work unit, 4 panes, output-pane logging ---


def _run_done(tmp_path):
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "done"}
    return m


def test_per_unit_workspace_labeled_by_unit_id(tmp_path):
    # maps to: B1 — workspace_create is called per unit, labeled by the unit id
    # (one space per unit), not a shared "factory" workspace.
    m = _run_done(tmp_path)
    assert len(m.workspaces) == 1
    _cwd, label = m.workspaces[0]
    assert label == "impl-01"
    assert label != "factory"  # not the old shared workspace


def test_four_panes_three_agents_bound_to_config_models(tmp_path):
    # maps to: B2 — 3 agent_start calls (implementer/inner/final models) + 1 output
    # pane that is a shell with no agent.
    m = _run_done(tmp_path)
    # the root space pane + 4 splits = 5 panes created
    assert len(m.pane_splits) == 4
    # exactly 3 agents started, bound to the three config models
    assert len(m._started) == 3
    assert m._started["impl-01"][1] == "deepseek-v4-flash:cloud"
    assert m._started["inner-01"][1] == "deepseek-v4-pro:cloud"
    assert m._started["ver-01"][1] == "glm-5.3-flash:cloud"
    # the 4th split (output pane) is NOT an agent pane
    agent_panes = {pane for pane, _ in m._started.values()}
    split_panes = {new for new, _parent, _dir in m.pane_splits}
    output_panes = split_panes - agent_panes
    assert len(output_panes) == 1  # exactly one shell output pane


def test_actions_logged_to_output_pane(tmp_path):
    # maps to: B3 — orchestrator actions are logged to the output pane via pane_log.
    m = _run_done(tmp_path)
    assert m.pane_logs  # logging happened
    # the output pane is the one split pane with no agent
    agent_panes = {pane for pane, _ in m._started.values()}
    output_pane = next(new for new, _p, _d in m.pane_splits if new not in agent_panes)
    logged_panes = {pane for pane, _ in m.pane_logs}
    assert output_pane in logged_panes  # logs went to the output pane
    lines = " ".join(line for _, line in m.pane_logs)
    assert "starting implementer for impl-01" in lines  # a key seam
    assert "outer cycle for impl-01" in lines


def test_space_disposed_on_teardown_done(tmp_path):
    # maps to: B4 — on unit teardown (done), the unit's space is disposed.
    m = _run_done(tmp_path)
    assert len(m.disposed_workspaces) == 1
    assert m.disposed_workspaces[0] == m.workspace_ids[0]  # the space created at start


def test_space_disposed_on_cancel(tmp_path):
    # maps to: B4 — on unit teardown (cancelled), the unit's space is disposed.
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)  # -> human gate -> 'q' -> cancelled
    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "q",
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    assert orch.run() == {"impl-01": "cancelled"}
    assert len(m.disposed_workspaces) == 1


def test_stdin_gates_stay_on_run_stdout(tmp_path, capsys):
    # maps to: B5 — the stdin gates (c/s/w/m/q) remain on run.py's own stdout/stdin,
    # not in any pane.
    units, cfg, m, gh, gops = setup(tmp_path)
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", UNPARSEABLE_VERDICT)  # -> human gate
    calls: list[str] = []

    def stdin() -> str:
        calls.append("called")
        return "q"

    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=stdin,
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    orch.run()
    # the gate consulted run.py's stdin (not a pane)
    assert calls == ["called"]
    # the gate prompt was written to run.py's stdout (captured), not a pane
    out = capsys.readouterr().out
    assert "(c)ontinue / (s)top / (w)escalate / (q)uit" in out
