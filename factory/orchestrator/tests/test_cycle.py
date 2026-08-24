"""Tests for cycle.py — the per-unit implementer↔verifier cycle loop (--mock)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import cycle
import herdr
import state
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
    effort: str = "sf"


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
        return f"{unit_id}-c{c}"

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
        db_path=str(tmp_path / "state.db"),
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
    # run.log narrative is gone (the SQLite DB is the narrative now) — no run.log written
    assert not (Path(worktree) / "run.log").exists()
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
    # maps to: neither the .verdict.yaml file nor the trailer yields a parseable
    # verdict -> the orchestrator re-prompts the verifier exactly ONCE, then a still-
    # unparseable re-prompt routes to HUMAN_GATE with the raw text surfaced (never-assume).
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "totally free text, no verdict")
    m.feed_read("ver-01", "still no verdict after re-prompt")
    result, _commits, _wt = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.HUMAN_GATE
    assert "still no verdict after re-prompt" in (result.raw_verdict or "")
    # the re-prompt was sent exactly once before the human gate
    assert len(m.prompts["ver-01"]) == 2
    assert "UNPARSEABLE" in m.prompts["ver-01"][1]


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
        return f"{uid}-c{c}"

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
        db_path=str(tmp_path / "state.db"),
    )
    assert result.outcome is cycle.CycleOutcome.DONE


def test_cycle_counter_persists_across_resume(tmp_path):
    """On resume the cycle counter continues from the persisted frontmatter `cycle`,
    so the 5-cycle backstop counts across the unit's whole life (not per-resume)."""
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    cfg = FakeConfig(cycle_cap=5)
    commits: list[tuple] = []

    def commit(uid, c, o, wt):
        commits.append((uid, c, o))
        return f"{uid}-c{c}"

    # cycle 1 -> BLOCKED
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    r1 = cycle.run_cycle(
        unit=unit,
        config=cfg,
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=commit,
        issues_dir=str(issues),
        next_esc_number=10,
        db_path=str(tmp_path / "state.db"),
    )
    assert r1.outcome is cycle.CycleOutcome.ESCALATE
    assert tickets.parse_impl_file(unit.path).cycle == 1  # persisted

    # resume: must continue at cycle 2 (seeded from the persisted cycle=1), not restart at 1
    m.feed_read("impl-01", "c2")
    m.feed_read("ver-01", PASS_VERDICT)
    r2 = cycle.run_cycle(
        unit=unit,
        config=cfg,
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=commit,
        issues_dir=str(issues),
        next_esc_number=10,
        resolution="greet(None) raises TypeError",
        db_path=str(tmp_path / "state.db"),
    )
    assert r2.outcome is cycle.CycleOutcome.DONE
    assert r2.final_cycle == 2  # the bug: this was 1 before the fix
    # the narrative is the SQLite DB: one row per cycle, no duplicate c1
    rows = state.query_cycles(str(tmp_path / "state.db"), unit_id="impl-01")
    assert [r["cycle_no"] for r in rows] == [1, 2]
    assert [r["verdict"] for r in rows] == ["BLOCKED", "PASS"]


def test_done_persists_status_done(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    cycle.run_cycle(
        unit=unit,
        config=FakeConfig(),
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=lambda *a: "sha",
        issues_dir=str(issues),
        next_esc_number=10,
        db_path=str(tmp_path / "state.db"),
    )
    assert tickets.parse_impl_file(unit.path).status == "done"


def test_blocked_persists_status_parked(tmp_path):
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    cycle.run_cycle(
        unit=unit,
        config=FakeConfig(),
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=lambda *a: "sha",
        issues_dir=str(issues),
        next_esc_number=10,
        db_path=str(tmp_path / "state.db"),
    )
    assert tickets.parse_impl_file(unit.path).status == "parked"


# ---- decision 15: deterministic verdict channel (trailer + bounded re-prompt) ----


def test_trailer_only_pass_routes_to_done(tmp_path):
    # maps to: trailer-only 'VERDICT overall=PASS' routes to DONE
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "review done\nVERDICT overall=PASS")
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.DONE
    assert result.final_cycle == 1
    assert commits == [("impl-01", 1, "PASS", worktree)]


def test_trailer_only_fail_routes_to_retry_with_fallback_feedback(tmp_path):
    # maps to: trailer-only 'VERDICT overall=FAIL' routes to RETRY (empty feedback is
    # acceptable — the trailer is routing-only, so the fallback feedback is used)
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "review done\nVERDICT overall=FAIL")
    m.feed_read("impl-01", "impl output c2")
    m.feed_read("ver-01", "review done\nVERDICT overall=PASS")
    result, commits, worktree = run(unit, m, tmp_path, cap=3)
    assert result.outcome is cycle.CycleOutcome.DONE
    assert result.final_cycle == 2
    # trailer is routing-only: no feedback, so the existing fallback is injected
    cycle2_prompt = m.prompts["impl-01"][1]
    assert "verifier FAIL (no concrete feedback)" in cycle2_prompt


def test_trailer_only_blocked_routes_to_escalate(tmp_path):
    # maps to: trailer-only 'VERDICT overall=BLOCKED' routes to ESCALATE
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "review done\nVERDICT overall=BLOCKED")
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.ESCALATE
    assert result.final_cycle == 1
    esc = Path(result.escalation_paths[0])
    assert "verifier BLOCKED (no reason given)" in esc.read_text()


@pytest.mark.parametrize("token", ["PASS", "FAIL", "BLOCKED"])
def test_trailer_only_never_human_gates_and_records_overall(tmp_path, token):
    # maps to: for any trailer overall in {PASS,FAIL,BLOCKED} a trailer-only pane routes
    # to the matching outcome (never a human gate) and records that overall.
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", f"review done\nVERDICT overall={token}")
    result, commits, worktree = run(unit, m, tmp_path, cap=1)
    assert result.outcome is not cycle.CycleOutcome.HUMAN_GATE
    assert commits == [("impl-01", 1, token, worktree)]


def test_reprompt_sent_once_then_parseable_routes_normally(tmp_path):
    # maps to: a re-prompt that yields a parseable verdict (file or trailer) routes
    # normally — no human gate
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "garbled, no verdict")  # first read: unparseable
    m.feed_read("ver-01", "review done\nVERDICT overall=PASS")  # re-prompt read: parseable
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.DONE
    assert result.final_cycle == 1
    # exactly one re-prompt was sent to the verifier pane
    assert len(m.prompts["ver-01"]) == 2
    assert "UNPARSEABLE" in m.prompts["ver-01"][1]


def test_reprompt_still_unparseable_routes_to_human_gate(tmp_path):
    # maps to: a re-prompt that is STILL unparseable routes to HUMAN_GATE with the raw
    # text surfaced (never-assume; no second re-prompt)
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "garbled, no verdict")
    m.feed_read("ver-01", "still garbled, no verdict")
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.HUMAN_GATE
    assert "still garbled" in (result.raw_verdict or "")
    # exactly one re-prompt, no second
    assert len(m.prompts["ver-01"]) == 2


def test_human_gate_writes_no_narrative_row(tmp_path):
    # maps to: HUMAN_GATE writes no narrative row (no commit happened; one row per
    # COMMITTED cycle, so a re-run on the gate's "continue" does not duplicate).
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", "garbled, no verdict")
    m.feed_read("ver-01", "still garbled, no verdict")
    result, _commits, _wt = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.HUMAN_GATE
    # No commit happened, so log_cycle never ran and the DB file was never created.
    assert not (tmp_path / "state.db").exists()


def test_verdict_parsed_from_raw_message_despite_terminal_chrome(tmp_path):
    # Regression (decision 21): the terminal surface has herdr chrome AFTER the trailer
    # (separators + the ~/path (branch) + ↑…↓… status bar), so parse_trailer on terminal
    # text reads the status bar -> UNPARSEABLE -> HUMAN_GATE. The verifier's RAW last
    # message (pi session JSONL) ends cleanly with the trailer, so the cycle routes PASS.
    terminal = (
        "review prose\n"
        "VERDICT overall=PASS\n"
        "───────────────────────────────────────────────\n"
        "~/projects/sf-impl-02 (impl-02)\n"
        "↑375k ↓3k 10.6%/262k (auto)  qwen3.5:cloud • medium"
    )
    raw = "review prose\nVERDICT overall=PASS"
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    m.feed_read("impl-01", "impl output c1")
    m.feed_read("ver-01", terminal)  # terminal surface (chrome) — would fail parse_trailer
    m.feed_last_message("ver-01", raw)  # raw last message — clean trailer
    result, _commits, _wt = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.DONE


def test_in_progress_persisted_when_not_terminal(tmp_path):
    # cap=1, FAIL -> CAP_REACHED: status written in_progress at cycle start, no terminal write
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    worktree = str(tmp_path / "wt")
    Path(worktree).mkdir()
    issues = tmp_path / "issues"
    issues.mkdir()
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", FAIL_VERDICT)
    cycle.run_cycle(
        unit=unit,
        config=FakeConfig(cycle_cap=1),
        herdr=m,
        worktree=worktree,
        branch="impl-01",
        panes=make_panes(),
        commit=lambda *a: "sha",
        issues_dir=str(issues),
        next_esc_number=10,
        db_path=str(tmp_path / "state.db"),
    )
    assert tickets.parse_impl_file(unit.path).status == "in_progress"


# ---- decision 17: per-repo narrative DB (state.py) threading ----


def test_run_cycle_logs_one_row_per_cycle_after_routing(tmp_path):
    # maps to: run_cycle writes exactly one log_cycle row per cycle, AFTER the verdict
    # is routed, carrying verdict (PASS) + action (DONE) + the cycle's commit_sha.
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    db_path = str(tmp_path / "state.db")
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", PASS_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.DONE
    rows = state.query_cycles(db_path, unit_id="impl-01")
    assert len(rows) == 1  # exactly one row for the single cycle
    row = rows[0]
    assert row["verdict"] == "PASS"
    assert row["action"] == "DONE"
    assert row["commit_sha"] == "impl-01-c1"  # the commit callback's returned sha
    assert row["cycle_no"] == 1
    assert row["branch"] == "impl-01"
    assert row["effort"] == "sf"


def test_run_cycle_logs_retry_then_cap_reached(tmp_path):
    # maps to: a FAIL-then-FAIL run logs one row per cycle; the final cycle's action is
    # CAP_REACHED (the 5-cycle backstop), earlier cycles are RETRY.
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    db_path = str(tmp_path / "state.db")
    m.feed_read("impl-01", "c1")
    m.feed_read("impl-01", "c2")
    m.feed_read("ver-01", FAIL_VERDICT)
    m.feed_read("ver-01", FAIL_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path, cap=2)
    assert result.outcome is cycle.CycleOutcome.CAP_REACHED
    rows = state.query_cycles(db_path, unit_id="impl-01")
    assert len(rows) == 2  # one row per cycle
    assert [r["action"] for r in rows] == ["RETRY", "CAP_REACHED"]
    assert [r["verdict"] for r in rows] == ["FAIL", "FAIL"]
    assert [r["commit_sha"] for r in rows] == ["impl-01-c1", "impl-01-c2"]


def test_run_cycle_logs_escalate_row(tmp_path):
    # maps to: a BLOCKED verdict routes to ESCALATE and logs one row with that action.
    unit = make_unit(tmp_path)
    m = herdr.MockHerdr()
    db_path = str(tmp_path / "state.db")
    m.feed_read("impl-01", "c1")
    m.feed_read("ver-01", BLOCKED_VERDICT)
    result, commits, worktree = run(unit, m, tmp_path)
    assert result.outcome is cycle.CycleOutcome.ESCALATE
    rows = state.query_cycles(db_path, unit_id="impl-01")
    assert len(rows) == 1
    assert rows[0]["verdict"] == "BLOCKED"
    assert rows[0]["action"] == "ESCALATE"
