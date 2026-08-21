"""Integration test — drives fixture impl units through the run loop in --mock mode.

Covers the three required scenarios (ticket 09 acceptance):
  1. PASS -> done
  2. FAIL -> retry -> PASS -> done
  3. BLOCKED -> escalate -> (resolve ticket file) -> resume -> PASS -> done
Plus the green PR-stage merge path (pr_stage on).
"""

from __future__ import annotations

import os
from pathlib import Path

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
FAIL_VERDICT = """\
```yaml
overall: FAIL
gates:
  - {gate: over_engineering, status: FAIL, feedback: "drop the unused helper"}
```
"""
BLOCKED_VERDICT = """\
```yaml
overall: BLOCKED
gates:
  - {gate: contradictions, status: BLOCKED, escalation: "greet(None) ambiguous"}
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


def setup_env(tmp_path, *, pr_stage=False, reviews=None):
    repo = str(tmp_path)
    impl_dir = tmp_path / ".scratch" / "sf" / "impl"
    impl_dir.mkdir(parents=True)
    issues_dir = tmp_path / ".scratch" / "sf" / "issues"
    issues_dir.mkdir(parents=True)
    impl_file = impl_dir / "01-greet.md"
    impl_file.write_text(IMPL_BODY)
    units = tickets.parse_impl_files([str(impl_file)])
    cfg = config_mod.default(repo, "sf", os.path.join(repo, ".scratch", "sf", "impl", "*.md"))
    cfg = cfg.with_overrides(
        repo_path=repo,
        worktree_parent=repo,
        pr_stage=pr_stage,
        gh_repo="o/r",
        mock=True,
    )
    m = herdr.MockHerdr()
    gh = pr_mod.MockGh(reviews_fixture=reviews or [])
    gops = gitops.MockGitOps(base=str(tmp_path))
    return units, cfg, m, gh, gops, str(impl_file), str(issues_dir)


def read_unit(impl_file):
    return Path(impl_file).read_text()


def read_worktree_unit(tmp_path, branch="impl-01"):
    # the orchestrator mutates the worktree-local copy (state lives on impl/NN).
    wt = tmp_path / f"sf-{branch}" / ".scratch" / "sf" / "impl" / "01-greet.md"
    return wt.read_text()


# ---- scenario 1: PASS -> done ----


def test_pass_first_cycle_done(tmp_path):
    units, cfg, m, gh, gops, impl_file, _ = setup_env(tmp_path, pr_stage=False)
    m.feed_read("impl-01", "impl output c1")
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
    result = orch.run()
    assert result == {"impl-01": "done"}
    # one worktree, one per-cycle commit, run.log line, frontmatter value-only updated
    assert len(gops.commits) == 1
    assert "impl-01 c1 PASS" in gops.commits[0][1]
    final = read_worktree_unit(tmp_path)
    assert "cycle: 1" in final and "last_verdict: PASS" in final
    # the cycle-2/escalation never happened
    assert "BLOCKED" not in final


# ---- scenario 2: FAIL -> retry -> PASS -> done ----


def test_fail_then_retry_then_pass(tmp_path):
    units, cfg, m, gh, gops, impl_file, _ = setup_env(tmp_path, pr_stage=False)
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("impl-01", "impl output c2")
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
    result = orch.run()
    assert result == {"impl-01": "done"}
    assert len(gops.commits) == 2  # one per cycle
    # cycle-2 implementer prompt carries the prior verifier feedback
    assert "drop the unused helper" in m.prompts["impl-01"][1]


# ---- scenario 3: BLOCKED -> escalate -> resolve -> resume -> PASS -> done ----


def test_blocked_escalate_resolve_resume_pass(tmp_path):
    units, cfg, m, gh, gops, impl_file, issues_dir = setup_env(tmp_path, pr_stage=False)
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("impl-01", "impl output c2 (resume)")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    m.feed_read("ver-01", PASS_VERDICT)

    def on_park(st):
        # the human/wayfinder resolves the escalation ticket out-of-band
        esc_path = st.escalation_paths[0]
        text = Path(esc_path).read_text()
        text = text.replace("Status: open", "Status: resolved")
        text = text.replace(
            "<!-- filled by the wayfinder/human; on `Status: resolved` the orchestrator resumes -->",
            "greet(None) must raise TypeError.",
        )
        Path(esc_path).write_text(text)

    orch = run.Orchestrator(
        config=cfg,
        herdr=m,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=lambda: "c",
        on_park=on_park,
        sleep_fn=lambda s: None,
        park_poll_budget=3,
    )
    result = orch.run()
    assert result == {"impl-01": "done"}
    # escalation ticket was authored and is now resolved with an answer
    esc_files = list(Path(issues_dir).glob("*.md"))
    assert len(esc_files) == 1
    assert "Status: resolved" in esc_files[0].read_text()
    # the resume-cycle implementer prompt injected the resolution verbatim
    assert "greet(None) must raise TypeError." in m.prompts["impl-01"][1]
    # two build cycles committed; the BLOCKED cycle + the resumed PASS cycle
    assert len(gops.commits) == 2


# ---- PR stage: green merge ----


def test_pr_stage_green_merge(tmp_path):
    reviews = [
        {"user": "human-reviewer", "state": "APPROVED"},
        {"user": "sourcery-ai", "state": "APPROVED"},
    ]
    units, cfg, m, gh, gops, impl_file, _ = setup_env(tmp_path, pr_stage=True, reviews=reviews)
    m.feed_read("impl-01", "impl output c1")
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
    result = orch.run()
    assert result == {"impl-01": "done"}
    assert gh.created  # PR created
    assert gh.merged == [gh.created[0][0]]  # merged by number
    assert gops.pushed == ["impl-01"]
    assert gops.tagged == ["archive/impl-01"]
    assert gops.removed  # worktree removed post-merge


# ---- pipelining: two independent units both done ----

IMPL_02 = IMPL_BODY.replace("id: impl-01", "id: impl-02").replace("title: greet", "title: caller")


def test_two_independent_units_pipeline_both_done(tmp_path):
    repo = str(tmp_path)
    impl_dir = tmp_path / ".scratch" / "sf" / "impl"
    impl_dir.mkdir(parents=True)
    tmp_path / ".scratch" / "sf" / "issues" / "".strip()  # noop
    (tmp_path / ".scratch" / "sf" / "issues").mkdir(parents=True)
    (impl_dir / "01-greet.md").write_text(IMPL_BODY)
    (impl_dir / "02-caller.md").write_text(IMPL_02)
    units = tickets.parse_impl_files(
        [str(impl_dir / "01-greet.md"), str(impl_dir / "02-caller.md")]
    )
    cfg = config_mod.default(
        repo, "sf", os.path.join(repo, ".scratch", "sf", "impl", "*.md")
    ).with_overrides(
        repo_path=repo,
        worktree_parent=repo,
        pr_stage=False,
        gh_repo="o/r",
        mock=True,
    )
    m = herdr.MockHerdr()
    for name in ("impl-01", "impl-02"):
        m.feed_read(name, "out c1")
    for name in ("ver-01", "ver-02"):
        m.feed_read(name, PASS_VERDICT)
    gops = gitops.MockGitOps(base=str(tmp_path))
    gh = pr_mod.MockGh()
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
    result = orch.run()
    assert result == {"impl-01": "done", "impl-02": "done"}
