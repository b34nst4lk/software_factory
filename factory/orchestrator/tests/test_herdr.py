"""Tests for herdr.py — the herdr subprocess wrapper and its --mock stub."""

from __future__ import annotations

import json

import herdr

# ---- real wrapper: argv construction (no live herdr) ----


def test_workspace_create_builds_correct_argv_and_parses_pane_id():
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        return (json.dumps({"result": {"root_pane": {"pane_id": "w1:p1"}}}), 0)

    h = herdr.Herdr(runner=runner)
    pane = h.workspace_create("/repo", "factory")
    assert pane == "w1:p1"
    assert calls[0][:3] == ["herdr", "workspace", "create"]
    assert "--cwd" in calls[0] and "/repo" in calls[0]
    assert "--label" in calls[0] and "factory" in calls[0]


def test_pane_split_builds_argv_and_returns_new_pane_id():
    def runner(argv: list[str]) -> tuple[str, int]:
        assert argv[:3] == ["herdr", "pane", "split"]
        assert "w1:p1" in argv
        return (json.dumps({"result": {"pane": {"pane_id": "w1:p2"}}}), 0)

    h = herdr.Herdr(runner=runner)
    assert h.pane_split("w1:p1", "right") == "w1:p2"


def test_agent_start_forwards_model_after_double_dash():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("{}", 0)

    h = herdr.Herdr(runner=runner)
    h.agent_start("impl-01", "w1:p1", "deepseek-v4-flash:cloud")
    assert seen[:4] == ["herdr", "agent", "start", "impl-01"]
    assert "--kind" in seen and "pi" in seen
    assert "--pane" in seen and "w1:p1" in seen
    assert "--" in seen and "deepseek-v4-flash:cloud" in seen


def test_agent_prompt_passes_wait_until_and_timeout():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    h = herdr.Herdr(runner=runner)
    h.agent_prompt("impl-01", "do work", until="done", timeout_ms=600000)
    assert seen[:4] == ["herdr", "agent", "prompt", "impl-01"]
    assert "--wait" in seen
    assert "--until" in seen and "done" in seen
    assert "--timeout" in seen and "600000" in seen


def test_agent_read_returns_pane_stdout():
    def runner(argv: list[str]) -> tuple[str, int]:
        assert argv[:4] == ["herdr", "agent", "read", "impl-01"]
        assert "--source" in argv and "recent-unwrapped" in argv
        return ("the implementer output text", 0)

    h = herdr.Herdr(runner=runner)
    assert h.agent_read("impl-01", 200) == "the implementer output text"


def test_report_metadata_builds_token_arg():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    h = herdr.Herdr(runner=runner)
    h.report_metadata("w1:p1", "impl-01 c1 PASS")
    assert seen[:3] == ["herdr", "pane", "report-metadata"]
    assert "w1:p1" in seen
    assert any("summary=impl-01 c1 PASS" in a for a in seen)


# ---- mock: deterministic stubs the cycle loop drives ----


def test_mock_assigns_pane_ids_and_splits():
    m = herdr.MockHerdr()
    root = m.workspace_create("/repo", "factory")
    other = m.pane_split(root, "right")
    assert root != other


def test_mock_records_start_and_reads_pop_fifo():
    m = herdr.MockHerdr()
    m.workspace_create("/repo", "factory")
    m.agent_start("impl-01", "p1", "deepseek-v4-flash:cloud")
    m.feed_read("impl-01", "first output")
    m.feed_read("impl-01", "second output")
    assert m.agent_read("impl-01", 100) == "first output"
    m.agent_prompt("impl-01", "next cycle", until="done", timeout_ms=1000)
    assert m.agent_read("impl-01", 100) == "second output"


def test_mock_records_prompts_and_metadata():
    m = herdr.MockHerdr()
    m.workspace_create("/repo", "factory")
    m.agent_start("impl-01", "p1", "deepseek-v4-flash:cloud")
    m.agent_prompt("impl-01", "a prompt", until="done", timeout_ms=10)
    assert m.prompts["impl-01"][-1] == "a prompt"
    m.report_metadata("p1", "impl-01 c1 PASS")
    assert m.metadata == [("p1", "impl-01 c1 PASS")]


def test_make_herdr_picks_mock_or_real():
    assert isinstance(herdr.make_herdr(mock=True), herdr.MockHerdr)
    assert isinstance(herdr.make_herdr(mock=False), herdr.Herdr)
