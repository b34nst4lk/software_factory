"""Tests for run.py stdin gates + PR-stage fix/dismissal routing (--mock)."""

from __future__ import annotations

import os

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
