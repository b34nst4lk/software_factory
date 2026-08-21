"""Tests for tickets.py — impl frontmatter parse, topo-sort, and ## Answer parsing."""

from __future__ import annotations

import pytest

import guard
import tickets

IMPL_01 = """\
---
id: impl-01
title: greet
scope_files: [factory/greet.py]
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
---
Body of impl-01.
"""

IMPL_02_DEP_01 = """\
---
id: impl-02
title: caller
scope_files: [factory/caller.py]
model: deepseek-v4-flash:cloud
depends_on: [impl-01]
status: open
cycle: 0
last_verdict: ""
---
Body of impl-02.
"""

IMPL_03_DEP_02 = """\
---
id: impl-03
title: runner
scope_files: [factory/runner.py]
model: deepseek-v4-flash:cloud
depends_on: [impl-02]
status: open
cycle: 0
last_verdict: ""
---
Body of impl-03.
"""

IMPL_04_DEP_NONE = """\
---
id: impl-04
title: standalone
scope_files: [factory/solo.py]
model: deepseek-v4-flash:cloud
depends_on: []
status: open
cycle: 0
last_verdict: ""
---
Body of impl-04.
"""


def make(units: dict[str, str], tmp_path) -> list[tickets.ImplTicket]:
    files = []
    for slug, text in units.items():
        p = tmp_path / slug
        p.write_text(text)
        files.append(str(p))
    return tickets.parse_impl_files(files)


# ---- frontmatter parse ----


def test_parse_reads_frontmatter_values_and_body(tmp_path):
    [t] = make({"01-greet.md": IMPL_01}, tmp_path)
    assert t.id == "impl-01"
    assert t.title == "greet"
    assert t.scope_files == ["factory/greet.py"]
    assert t.model == "deepseek-v4-flash:cloud"
    assert t.depends_on == []
    assert t.status == "open"
    assert t.cycle == 0
    assert t.last_verdict == ""
    assert "Body of impl-01." in t.body


def test_parse_preserves_acceptance_structured_behaviors(tmp_path):
    text = IMPL_01.replace(
        "scope_files: [factory/greet.py]\n",
        "scope_files: [factory/greet.py]\n"
        "acceptance:\n"
        '  - story: "As a caller, I can greet"\n'
        "    behaviors:\n"
        "      - {behavior: \"greet('world')\", outcome: success}\n"
        '      - {behavior: "greet(None) raises", outcome: failure}\n',
    )
    [t] = make({"01-greet.md": text}, tmp_path)
    assert len(t.acceptance) == 1
    assert t.acceptance[0]["story"].startswith("As a caller")
    assert t.acceptance[0]["behaviors"][1]["outcome"] == "failure"


# ---- topo-sort ----


def test_topo_sort_orders_dependencies_before_dependents(tmp_path):
    parsed = make(
        {"03-runner.md": IMPL_03_DEP_02, "01-greet.md": IMPL_01, "02-caller.md": IMPL_02_DEP_01},
        tmp_path,
    )
    order = [t.id for t in tickets.topo_sort(parsed)]
    assert order == ["impl-01", "impl-02", "impl-03"]


def test_topo_sort_orders_independent_units_in_input_order(tmp_path):
    parsed = make({"04-solo.md": IMPL_04_DEP_NONE, "01-greet.md": IMPL_01}, tmp_path)
    order = [t.id for t in tickets.topo_sort(parsed)]
    assert order == ["impl-04", "impl-01"]


def test_topo_sort_detects_a_cycle_as_error(tmp_path):
    # build an actual 2-cycle: impl-01 -> impl-02, impl-02 -> impl-01
    a_text = (
        "---\nid: impl-01\ndepends_on: [impl-02]\n"
        'status: open\ncycle: 0\nlast_verdict: ""\n---\nA\n'
    )
    b_text = (
        "---\nid: impl-02\ndepends_on: [impl-01]\n"
        'status: open\ncycle: 0\nlast_verdict: ""\n---\nB\n'
    )
    parsed = make({"01-a.md": a_text, "02-b.md": b_text}, tmp_path)
    with pytest.raises(tickets.CycleError):
        tickets.topo_sort(parsed)


def test_topo_sort_missing_dependency_is_an_error(tmp_path):
    text = IMPL_02_DEP_01  # depends on impl-01 which we do NOT provide
    parsed = make({"02-caller.md": text}, tmp_path)
    with pytest.raises(tickets.MissingDependencyError):
        tickets.topo_sort(parsed)


# ---- ready units (no unsatisfied deps) ----


def test_ready_units_returns_those_without_unsatisfied_deps(tmp_path):
    parsed = make(
        {"01-greet.md": IMPL_01, "02-caller.md": IMPL_02_DEP_01, "04-solo.md": IMPL_04_DEP_NONE},
        tmp_path,
    )
    ready_ids = {t.id for t in tickets.ready_units(parsed, done_ids=set())}
    assert ready_ids == {"impl-01", "impl-04"}


def test_ready_units_unblocks_dependent_once_dep_done(tmp_path):
    parsed = make({"01-greet.md": IMPL_01, "02-caller.md": IMPL_02_DEP_01}, tmp_path)
    ready = {t.id for t in tickets.ready_units(parsed, done_ids={"impl-01"})}
    assert ready == {"impl-02"}


# ---- ## Answer parse ----

ESCALATION_TICKET = """\
# 99 — greet(None) ambiguity

Type: grilling
Status: resolved
Blocked by: 09

## Question

Should greet(None) raise TypeError or coerce to "hello, None"?

## Answer

`greet(None)` must raise `TypeError`. Do not coerce; do not return a string.
Tests must assert the raise.
"""


def test_parse_answer_returns_the_answer_section_body(tmp_path):
    p = tmp_path / "99-greet-none.md"
    p.write_text(ESCALATION_TICKET)
    answer = tickets.parse_answer(str(p))
    assert "raise `TypeError`" in answer
    assert "Do not coerce" in answer


def test_parse_answer_returns_none_when_no_answer_section(tmp_path):
    p = tmp_path / "open.md"
    p.write_text("# 98\nType: grilling\nStatus: open\n\n## Question\nstuff\n")
    assert tickets.parse_answer(str(p)) is None


def test_ticket_status_resolved_detected(tmp_path):
    p = tmp_path / "99.md"
    p.write_text(ESCALATION_TICKET)
    assert tickets.is_resolved(str(p)) is True


def test_ticket_status_open_not_resolved(tmp_path):
    p = tmp_path / "98.md"
    p.write_text("# 98\nType: grilling\nStatus: open\n\n## Question\nstuff\n")
    assert tickets.is_resolved(str(p)) is False


# ---- write_frontmatter_value stays guard-clean (value-only) ----


def test_write_frontmatter_value_is_value_only_and_guard_passes(tmp_path):
    p = tmp_path / "01-greet.md"
    p.write_text(IMPL_01)
    before = p.read_text()
    tickets.write_frontmatter_value(str(p), status="in_progress", cycle=1, last_verdict="FAIL")
    after = p.read_text()
    # the body is unchanged and no key was added/removed -> guard sees value-only.
    assert guard.check_impl_file(before, after, "01-greet.md", is_new=False) == []
    # and the values actually moved:
    [t] = tickets.parse_impl_files([str(p)])
    assert t.status == "in_progress"
    assert t.cycle == 1
    assert t.last_verdict == "FAIL"


def test_write_frontmatter_value_refuses_non_mutable_key(tmp_path):
    p = tmp_path / "01-greet.md"
    p.write_text(IMPL_01)
    with pytest.raises(ValueError):
        tickets.write_frontmatter_value(str(p), scope_files=["x.py"])
