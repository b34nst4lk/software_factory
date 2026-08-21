"""Tests for verdict.py — fenced-YAML verdict extraction, parsing, and routing."""

from __future__ import annotations

import pytest

import verdict

PASS_BLOCK = """\
Some prose about the review.

```yaml
overall: PASS
gates:
  - gate: meets_requirement
    status: PASS
  - gate: contradictions
    status: PASS
  - gate: over_engineering
    status: PASS
  - gate: convention
    status: PASS
  - gate: code_review
    status: PASS
  - gate: behavior_coverage
    status: PASS
```
trailing text.
"""

FAIL_BLOCK = """\
```yaml
overall: FAIL
gates:
  - gate: over_engineering
    status: FAIL
    feedback: "drop the unused helper"
  - gate: convention
    status: PASS
```
"""

BLOCKED_BLOCK = """\
```yaml
overall: BLOCKED
gates:
  - gate: contradictions
    status: BLOCKED
    escalation: "the spec does not say whether greet(None) should raise or coerce"
```
"""

MULTI_BLOCK = """\
```yaml
overall: FAIL
gates:
  - gate: meets_requirement
    status: FAIL
    feedback: "missing the empty-string case"
  - gate: contradictions
    status: BLOCKED
    escalation: "ambiguous on None"
```
"""


# ---- extraction ----


def test_extract_returns_the_fenced_yaml_text():
    text = verdict.extract_verdict_block(PASS_BLOCK)
    assert text is not None
    assert "overall: PASS" in text


def test_extract_returns_none_when_no_fenced_yaml():
    assert verdict.extract_verdict_block("no code fence here") is None


def test_extract_returns_none_for_a_non_yaml_fence():
    assert verdict.extract_verdict_block("```python\nprint(1)\n```") is None


# ---- parse ----


def test_parse_pass_yields_pass_overall_and_no_feedback():
    v = verdict.parse_verdict(PASS_BLOCK)
    assert v.overall is verdict.Overall.PASS
    assert v.feedbacks == []
    assert v.escalations == []


def test_parse_fail_collects_only_failing_gate_feedback():
    v = verdict.parse_verdict(FAIL_BLOCK)
    assert v.overall is verdict.Overall.FAIL
    assert v.feedbacks == ["drop the unused helper"]
    assert v.escalations == []


def test_parse_blocked_collects_escalation_reason():
    v = verdict.parse_verdict(BLOCKED_BLOCK)
    assert v.overall is verdict.Overall.BLOCKED
    assert v.escalations == ["the spec does not say whether greet(None) should raise or coerce"]
    assert v.feedbacks == []


def test_parse_fail_with_a_blocked_gate_routes_to_blocked_overall():
    # Any gate BLOCKED makes overall BLOCKED regardless of a FAIL (06 Q1: any gate may BLOCKED).
    v = verdict.parse_verdict(MULTI_BLOCK)
    assert v.overall is verdict.Overall.BLOCKED
    assert v.feedbacks == ["missing the empty-string case"]
    assert v.escalations == ["ambiguous on None"]


def test_parse_missing_overall_is_unparseable():
    bad = "```yaml\ngates: []\n```"
    v = verdict.parse_verdict(bad)
    assert v.overall is verdict.Overall.UNPARSEABLE


def test_parse_no_fenced_block_is_unparseable():
    v = verdict.parse_verdict("totally free text, no verdict")
    assert v.overall is verdict.Overall.UNPARSEABLE


def test_parse_malformed_yaml_is_unparseable():
    v = verdict.parse_verdict("```yaml\noverall: : :\n```")
    assert v.overall is verdict.Overall.UNPARSEABLE


# ---- routing ----


def test_route_pass_to_done():
    assert verdict.route(verdict.parse_verdict(PASS_BLOCK)) is verdict.Action.DONE


def test_route_fail_to_retry_feedback():
    assert verdict.route(verdict.parse_verdict(FAIL_BLOCK)) is verdict.Action.RETRY


def test_route_blocked_to_escalate():
    assert verdict.route(verdict.parse_verdict(BLOCKED_BLOCK)) is verdict.Action.ESCALATE


def test_route_unparseable_to_human_gate():
    assert verdict.route(verdict.parse_verdict("no fence")) is verdict.Action.HUMAN_GATE


# ---- never-assume: human gate surfaces the raw text ----


def test_unparseable_verdict_carries_raw_text_for_the_human_gate():
    v = verdict.parse_verdict("no fence at all")
    assert v.raw is not None
    assert "no fence" in v.raw


@pytest.mark.parametrize(
    "block,expected",
    [
        (PASS_BLOCK, verdict.Overall.PASS),
        (FAIL_BLOCK, verdict.Overall.FAIL),
        (BLOCKED_BLOCK, verdict.Overall.BLOCKED),
    ],
)
def test_overall_classification(block, expected):
    assert verdict.parse_verdict(block).overall is expected
