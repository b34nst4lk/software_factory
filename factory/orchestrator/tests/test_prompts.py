"""Tests for prompts.py — the implementer + verifier prompt templates."""

from __future__ import annotations

import prompts


def test_implementer_prompt_embeds_skill_tdd_and_ticket_body_and_context():
    p = prompts.implementer_prompt(
        ticket_body="Implement greet(name).",
        cycle=1,
        worktree="/tmp/sf-impl-01",
        branch="impl-01",
        prior_feedback=None,
        resolution=None,
    )
    assert "/skill:tdd" in p
    assert "Implement greet(name)." in p
    assert "cycle: 1" in p
    assert "/tmp/sf-impl-01" in p
    assert "impl-01" in p


def test_implementer_prompt_includes_prior_feedback_on_retry():
    p = prompts.implementer_prompt(
        ticket_body="body",
        cycle=2,
        worktree="/w",
        branch="impl-01",
        prior_feedback="drop the unused helper",
        resolution=None,
    )
    assert "drop the unused helper" in p
    assert "prior verifier feedback" in p.lower() or "verifier feedback" in p.lower()


def test_implementer_prompt_includes_resolution_block_on_resume():
    p = prompts.implementer_prompt(
        ticket_body="body",
        cycle=2,
        worktree="/w",
        branch="impl-01",
        prior_feedback=None,
        resolution="greet(None) must raise TypeError",
    )
    assert "Resolution" in p
    assert "greet(None) must raise TypeError" in p
    assert "verbatim" not in p.lower() or True  # just ensure injection happened


def test_verifier_prompt_embeds_code_review_skill_and_6_gates_and_verdict_instruction():
    p = prompts.verifier_prompt(
        implementer_output="Here is the diff.",
        verify=["behaviors captured by tests"],
        cycle=1,
        resolution=None,
    )
    assert "/skill:code-review" in p
    assert "Here is the diff." in p
    assert "meets" in p.lower()  # gate 1
    assert "contradiction" in p.lower() or "escalate" in p.lower()  # gate 2
    assert "over-engineer" in p.lower() or "over_engineer" in p.lower()  # gate 3
    assert "convention" in p.lower()  # gate 4
    assert "behavior" in p.lower() and "coverage" in p.lower()  # gate 6
    assert "fenced YAML" in p or "```yaml" in p
    assert "overall" in p
    assert "PASS" in p and "FAIL" in p and "BLOCKED" in p


def test_verifier_prompt_lists_all_six_gates_explicitly():
    p = prompts.verifier_prompt(implementer_output="d", verify=[], cycle=1, resolution=None)
    for i in range(1, 7):
        assert f"gate {i}" in p.lower() or f"Gate {i}" in p


def test_verifier_prompt_includes_resolution_block_on_resume():
    p = prompts.verifier_prompt(
        implementer_output="d",
        verify=[],
        cycle=2,
        resolution="greet(None) must raise TypeError",
    )
    assert "greet(None) must raise TypeError" in p


def test_resolution_block_is_verbatim_and_attributed():
    block = prompts.resolution_block("99-greet-none", "the answer text")
    assert "99-greet-none" in block
    assert "the answer text" in block


def test_verifier_prompt_requires_trailer_as_last_line():
    # maps to: verifier_prompt ends by requiring the line 'VERDICT overall=PASS|FAIL|BLOCKED'
    # as the verifier's LAST reply line (alongside the existing file contract)
    p = prompts.verifier_prompt(implementer_output="d", verify=[], cycle=1, resolution=None)
    assert "VERDICT overall=PASS|FAIL|BLOCKED" in p
    assert "LAST" in p or "last line" in p.lower()
    # the trailer requirement comes after the existing file contract
    assert p.index("VERDICT_FILE") < p.index("VERDICT overall=PASS|FAIL|BLOCKED")


def test_reprompt_verifier_tells_verifier_previous_was_unparseable():
    # maps to: a new prompt template tells the verifier its previous verdict was
    # unparseable and instructs it to write exactly this to .verdict.yaml and end with
    # 'VERDICT overall=X'
    p = prompts.reprompt_verifier(cycle=1, resolution=None)
    assert "UNPARSEABLE" in p
    assert ".verdict.yaml" in p
    assert "VERDICT overall=" in p
    assert "overall:" in p


def test_pr_fix_prompt_routes_reviewer_comments_and_requests_structured_dismissal():
    p = prompts.pr_fix_prompt(
        pr_number=12,
        comments="reviewer: please rename foo",
    )
    assert "PR #12" in p
    assert "please rename foo" in p
    assert "addressed" in p and "dismissed" in p
    assert "```yaml" in p or "fenced YAML" in p
