"""Tests for verdict.py — fenced-YAML verdict extraction, parsing, and routing."""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

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


# ---- parse_verdict_yaml (file path; pane wrapping workaround) ----


def test_parse_verdict_yaml_handles_raw_yaml_file():
    raw = "overall: BLOCKED\ngates:\n  - gate: contradictions\n    status: BLOCKED\n    escalation: greet(None) unspecified\n"
    v = verdict.parse_verdict_yaml(raw)
    assert v.overall is verdict.Overall.BLOCKED
    assert v.escalations == ["greet(None) unspecified"]


def test_parse_verdict_yaml_strips_a_leading_fence():
    raw = "```yaml\noverall: PASS\ngates:\n  - gate: meets_requirement\n    status: PASS\n```\n"
    v = verdict.parse_verdict_yaml(raw)
    assert v.overall is verdict.Overall.PASS


def test_parse_verdict_yaml_malformed_is_unparseable():
    v = verdict.parse_verdict_yaml("overall: : : not yaml")
    assert v.overall is verdict.Overall.UNPARSEABLE


# ---- parse_trailer (decision 15: deterministic routing channel) ----
# The trailer is a compact one-line routing marker `VERDICT overall=PASS|FAIL|BLOCKED`
# that survives any pane width. parse_trailer reads ONLY the last non-empty line and
# returns the matching Overall, or None when no usable trailer is present. It is a
# pure text scan (no fenced-YAML extraction).


def test_parse_trailer_returns_pass_for_pass_trailer():
    # maps to: parse_trailer(text ending in 'VERDICT overall=PASS') returns Overall.PASS
    assert verdict.parse_trailer("review done\nVERDICT overall=PASS") is verdict.Overall.PASS


def test_parse_trailer_returns_fail_for_fail_trailer():
    # maps to: parse_trailer(text ending in 'VERDICT overall=FAIL') returns Overall.FAIL
    assert verdict.parse_trailer("review done\nVERDICT overall=FAIL") is verdict.Overall.FAIL


def test_parse_trailer_returns_blocked_for_blocked_trailer():
    # maps to: parse_trailer(text ending in 'VERDICT overall=BLOCKED') returns Overall.BLOCKED
    assert verdict.parse_trailer("review done\nVERDICT overall=BLOCKED") is verdict.Overall.BLOCKED


def test_parse_trailer_returns_none_when_no_trailer_present():
    # maps to: parse_trailer(text with no 'VERDICT overall=' line) returns None
    assert verdict.parse_trailer("just some prose, no trailer") is None
    assert verdict.parse_trailer("") is None


def test_parse_trailer_ignores_a_stray_mid_text_trailer():
    # maps to: parse_trailer reads the LAST non-empty line only; a stray mid-text
    # trailer does not count when a different line follows.
    text = "VERDICT overall=PASS\nbut then more prose follows"
    assert verdict.parse_trailer(text) is None


def test_parse_trailer_tolerates_whitespace_and_case():
    # maps to: parse_trailer tolerates trailing whitespace, surrounding spaces around
    # '=', and is case-insensitive on the overall token.
    assert verdict.parse_trailer("VERDICT overall = PASS   \n") is verdict.Overall.PASS
    assert verdict.parse_trailer("VERDICT overall=pass") is verdict.Overall.PASS
    assert verdict.parse_trailer("VERDICT overall = fail") is verdict.Overall.FAIL
    assert verdict.parse_trailer("VERDICT overall=Blocked") is verdict.Overall.BLOCKED


def test_parse_trailer_returns_none_for_unknown_overall_token():
    # maps to: parse_trailer returns None for an unknown overall token.
    assert verdict.parse_trailer("VERDICT overall=WAT") is None


def test_parse_trailer_rejects_internal_unparseable_token():
    # Regression: UNPARSEABLE is an internal Overall member, not a routing verdict.
    # The trailer channel carries only PASS/FAIL/BLOCKED; it must not leak UNPARSEABLE.
    # maps to: parse_trailer returns None for an unknown overall token (e.g. 'VERDICT overall=WAT')
    assert verdict.parse_trailer("VERDICT overall=UNPARSEABLE") is None


@given(
    prose=st.text(alphabet=st.characters(blacklist_categories=["Cs"]), max_size=200),
    token=st.sampled_from(["PASS", "FAIL", "BLOCKED"]),
    pad=st.text(alphabet=" \t", max_size=10),
    eq_spaces=st.text(alphabet=" ", max_size=3),
    case=st.sampled_from(["upper", "lower", "mixed"]),
)
def test_parse_trailer_property_valid_trailer(prose, token, pad, eq_spaces, case):
    # maps to: for every last non-empty line of the form `VERDICT overall=X` with X in
    # {PASS,FAIL,BLOCKED} (arbitrary leading prose, optional surrounding whitespace /
    # spaces around '='), parse_trailer returns the matching Overall.
    if case == "upper":
        tok = token
    elif case == "lower":
        tok = token.lower()
    else:
        tok = token[0] + token[1:].lower()
    text = f"{prose}\nVERDICT overall{eq_spaces}={eq_spaces}{tok}{pad}"
    assert verdict.parse_trailer(text) is verdict.Overall[token]


@given(
    prose=st.text(alphabet=st.characters(blacklist_categories=["Cs"]), max_size=200),
    last=st.text(alphabet=st.characters(blacklist_categories=["Cs"]), max_size=200),
)
def test_parse_trailer_property_non_trailer_returns_none(prose, last):
    # maps to: for any other last line it returns None.
    # Constrain the last line so it cannot itself be a valid trailer (which would
    # legitimately return an Overall, not None).
    assume(verdict._TRAILER_RE.match(last) is None)
    text = f"{prose}\n{last}"
    assert verdict.parse_trailer(text) is None
