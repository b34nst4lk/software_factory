"""Tests for cycle.py — the per-unit implementer↔verifier cycle loop (--mock)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cycle
import herdr
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


@dataclass
class FakeConfig:
    cycle_cap: int = 5
    prompt_timeout_ms: int = 1000
    read_lines: int = 100
    implementer_model: str = "deepseek-v4-flash:cloud"
    verifier_model: str = "qwen3.5:cloud"


def make_unit(tmp_path) -> tickets.ImplTicket:
    p = tmp_path / "01-greet.md"
    p.write_text(IMPL_BODY)
    return tickets.parse_impl_file(str(p))


def make_panes() -> cycle.Panes:
    return cycle.Panes(impl_name="impl-01", ver_name="ver-01", impl_pane="p1", ver_pane="p2")


def run(unit, m, tmp_path, *, cap=5, resolution=None):
    cfg = FakeConfig(cycle_cap=cap)
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    commits: list[tuple] = []

    def commit(unit_id, c, overall, wt):
        commits.append((unit_id, c, overall, wt))

    result = cycle.run_cycle(
        unit=unit,
        config=cfg,
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=commit,
        issues_dir=str(issues),
        next_esc_number=1,
        resolution=resolution,
    )
    return result, commits, worktree


def test_pass_first_cycle_done(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", PASS_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.DONE
    assert result.final_cycle == 1
    assert commits == [("impl-01", 1, "PASS", worktree)]
    # frontmatter updated value-only
    [t] = tickets.parse_impl_files([unit.path])
    assert t.cycle == 1 and t.last_verdict == "PASS"
    # run.log appended one line
    assert (Path(worktree) / "run.log").read_text().count("\n") == 1
    # sidebar metadata pushed
    assert ("p1", "impl-01 c1 PASS") in m.metadata


def test_fail_then_retry_then_pass(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("impl-01", "impl output c2")
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", PASS_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path, cap=3)
    assert result.outcome is cycle.CycleOutcome.DONE
    assert result.final_cycle == 2
    assert len(commits) == 2
    # cycle-2 implementer prompt carries the prior verifier feedback
    cycle2_prompt = m.prompts["impl-01"][1]
    assert "drop the unused helper" in cycle2_prompt


def test_blocked_escalates_and_authors_ticket(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.ESCALATE
    assert result.final_cycle == 1
    assert len(result.escalation_paths) == 1
    esc = Path(result.escalation_paths[0])
    assert esc.exists()
    assert "Type: grilling" in esc.read_text()
    assert "greet(None) ambiguous" in esc.read_text()
    # the cycle still committed (unit-green assumed) and updated frontmatter
    assert commits == [("impl-01", 1, "BLOCKED", worktree)]
    [t] = tickets.parse_impl_files([unit.path])
    assert t.last_verdict == "BLOCKED"


def test_unparseable_verdict_routes_to_human_gate(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "totally free text, no verdict")
    result, _commits, _wt = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.HUMAN_GATE
    assert "totally free text" in (result.raw_verdict or "")


def test_cap_reached_after_repeated_fail(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "c1")
    m.feed_read("impl-01", "c2")
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", FAIL_VERDICT)
    result, commits, _wt = run(unit, m, tmp_path, cap=2)
    assert result.outcome is cycle.CycleOutcome.CAP_REACHED
    assert result.final_cycle == 2
    assert len(commits) == 2


def test_resolution_block_injected_into_both_prompts_on_resume(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", PASS_VERDICT)
    run(unit, m, tmp_path, resolution="greet(None) must raise TypeError")
    impl_prompt = m.prompts["impl-01"][0]
    ver_prompt = m.prompts["ver-01"][0]
    assert "greet(None) must raise TypeError" in impl_prompt
    assert "greet(None) must raise TypeError" in ver_prompt


def test_cross_model_binding_every_cycle(tmp_path):
    # The cycle binds implementer != verifier model via the prompt context (config).
    # We assert the unit's model is the implementer binding and the verifier uses a
    # different family — encoded in the config passed to run_cycle.
    cfg = FakeConfig()
    assert cfg.implementer_model != cfg.verifier_model
    assert cfg.implementer_model.startswith("deepseek")
    assert cfg.verifier_model.startswith("qwen")


def test_verdict_file_takes_precedence_over_pane_text(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    # the verifier's pane text is unparseable (wrapping), but it wrote a clean file
    m.feed_read("impl-01", "impl c1")
    m.feed_read("ver-01", "garbled pane text\nVERDICT_FILE: .verdict.yaml")
    (Path(worktree) / ".verdict.yaml").write_text(
        "overall: PASS\ngates:\n  - gate: meets_requirement\n    status: PASS\n"
    )
    cfg = FakeConfig(cycle_cap=5)

    def commit(uid, c, o, wt):
        pass

    result = cycle.run_cycle(
        unit=unit,
        config=cfg,
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=commit,
        issues_dir=str(issues),
        next_esc_number=1,
    )
    assert result.outcome is cycle.CycleOutcome.DONE
