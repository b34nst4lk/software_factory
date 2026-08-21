"""Tests for escalate.py — ticket authoring, file-driven resume, re-injection."""

from __future__ import annotations

import escalate


def test_create_escalation_ticket_writes_grilling_open_ticket(tmp_path):
    issues = tmp_path / "issues"
    issues.mkdir()
    path = escalate.create_escalation_ticket(
        issues_dir=str(issues),
        unit_id="impl-01",
        unit_title="greet",
        cycle=1,
        escalations=["greet(None) behaviour is ambiguous"],
        number=42,
    )
    with open(path) as fh:
        text = fh.read()
    assert "Type: grilling" in text
    assert "Status: open" in text
    assert "impl-01" in text
    assert "greet(None) behaviour is ambiguous" in text
    assert "cycle 1" in text
    assert "## Answer" in text  # empty Answer section present


def test_create_escalation_ticket_slug_and_number_in_path(tmp_path):
    issues = tmp_path / "issues"
    issues.mkdir()
    path = escalate.create_escalation_ticket(
        issues_dir=str(issues),
        unit_id="impl-01",
        unit_title="greet(name)",
        cycle=1,
        escalations=["x"],
        number=7,
    )
    assert "07-" in path
    assert path.endswith(".md")


def test_all_resolved_false_when_any_open(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("# 1\nType: grilling\nStatus: open\n\n## Answer\n\nx\n")
    b = tmp_path / "b.md"
    b.write_text("# 2\nType: grilling\nStatus: resolved\n\n## Answer\n\ny\n")
    assert escalate.all_resolved([str(a), str(b)]) is False


def test_all_resolved_true_when_all_resolved(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("# 1\nType: grilling\nStatus: resolved\n\n## Answer\n\nA1\n")
    b = tmp_path / "b.md"
    b.write_text("# 2\nType: grilling\nStatus: resolved\n\n## Answer\n\nA2\n")
    assert escalate.all_resolved([str(a), str(b)]) is True


def test_resolutions_for_returns_verbatim_answers_only_for_resolved(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("# 1\nType: grilling\nStatus: resolved\n\n## Answer\n\nA1 verbatim.\n")
    b = tmp_path / "b.md"
    b.write_text("# 2\nType: grilling\nStatus: open\n\n## Answer\n\nA2\n")
    res = escalate.resolutions_for([str(a), str(b)])
    assert len(res) == 1
    assert res[0][1] == "A1 verbatim."  # verbatim, not trimmed of content
    assert "42-greet-none" not in res[0][0]  # path returned, just structural


def test_resolutions_for_empty_when_no_paths():
    assert escalate.resolutions_for([]) == []


def test_cancelled_resolution_marks_unit_cancelled():
    # A resolution that cancels the unit (contains 'cancelled') is detectable.
    text = "This unit is cancelled; see impl-99 instead."
    assert escalate.is_cancellation(text) is True


def test_non_cancellation_resolution():
    assert escalate.is_cancellation("greet(None) must raise TypeError") is False


def test_resolution_block_is_verbatim_and_attributed_for_reinjection():
    block = escalate.resolution_block("99-greet-none", "the answer verbatim")
    assert "99-greet-none" in block
    assert "the answer verbatim" in block
