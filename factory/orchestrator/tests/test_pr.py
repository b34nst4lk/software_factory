"""Tests for pr.py — gh wrapper, merge-gate logic, and dismissal routing."""

from __future__ import annotations

import json

import pr

# ---- argv construction (no live gh) ----


def test_pr_create_builds_argv_and_returns_number():
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        return ("https://github.com/o/r/pull/12\n", 0)

    g = pr.Gh(runner=runner)
    num = g.pr_create("impl-01", "head-branch", "main", "title", "body")
    assert num == 12
    assert calls[0][:4] == ["gh", "pr", "create", "--head"]
    assert "impl-01" in calls[0] or "head-branch" in calls[0]


def test_api_reviews_builds_argv_and_returns_parsed_reviews():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        assert argv[:4] == ["gh", "api", "repos/o/r/pulls/12/reviews"]
        # GitHub's review `user` is an object with a `login` field, not a string.
        return (
            json.dumps([{"user": {"login": "sourcery-ai[bot]"}, "state": "APPROVED"}]),
            0,
        )

    g = pr.Gh(runner=runner)
    reviews = g.api_reviews("o/r", 12)
    assert reviews == [{"user": "sourcery-ai[bot]", "state": "APPROVED"}]


def test_api_reviews_normalizes_user_object_to_login():
    # Regression (the 25-build crash): the raw GitHub review `user` is a full
    # object; merge_gate used it as a dict key -> TypeError (unhashable). api_reviews
    # must normalize `user` to the login string.
    raw_review = {
        "user": {"login": "sourcery-ai[bot]", "id": 58596630, "type": "Bot"},
        "state": "COMMENTED",
        "body": "some review body",
    }

    def runner(argv: list[str]) -> tuple[str, int]:
        return (json.dumps([raw_review]), 0)

    g = pr.Gh(runner=runner)
    reviews = g.api_reviews("o/r", 1)
    assert reviews == [{"user": "sourcery-ai[bot]", "state": "COMMENTED"}]
    # the normalized user is a hashable string (usable as a dict key by merge_gate)
    assert isinstance(reviews[0]["user"], str)


def test_api_reviews_handles_missing_user():
    def runner(argv: list[str]) -> tuple[str, int]:
        return (json.dumps([{"state": "COMMENTED"}, {"user": None, "state": "APPROVED"}]), 0)

    g = pr.Gh(runner=runner)
    reviews = g.api_reviews("o/r", 1)
    assert reviews == [
        {"user": "", "state": "COMMENTED"},
        {"user": "", "state": "APPROVED"},
    ]


def test_pr_merge_builds_squash_argv():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    g = pr.Gh(runner=runner)
    g.pr_merge(12, squash=True)
    assert seen[:4] == ["gh", "pr", "merge", "12"]
    assert "--squash" in seen


def test_pr_comment_builds_argv():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    g = pr.Gh(runner=runner)
    g.pr_comment(12, "reason text")
    assert seen[:4] == ["gh", "pr", "comment", "12"]
    assert "reason text" in seen


# ---- merge-gate logic ----


def review(state: str, user: str) -> dict[str, str]:
    return {"user": user, "state": state}


def test_merge_gate_approves_when_human_approved_and_sourcery_clean():
    gate = pr.merge_gate(
        reviews=[
            review("APPROVED", "human-login"),
            review("APPROVED", "sourcery-ai"),
        ],
        human_login="human-login",
        sourcery_login="sourcery-ai",
    )
    assert gate.mergable is True
    assert gate.changes_requested_from == []
    assert gate.advisory_comments == []


def test_merge_gate_blocks_on_changes_requested_from_sourcery():
    gate = pr.merge_gate(
        reviews=[
            review("APPROVED", "human-login"),
            review("CHANGES_REQUESTED", "sourcery-ai"),
        ],
        human_login="human-login",
        sourcery_login="sourcery-ai",
    )
    assert gate.mergable is False
    assert "sourcery-ai" in gate.changes_requested_from


def test_merge_gate_blocks_on_changes_requested_from_human():
    gate = pr.merge_gate(
        reviews=[
            review("CHANGES_REQUESTED", "human-login"),
            review("APPROVED", "sourcery-ai"),
        ],
        human_login="human-login",
        sourcery_login="sourcery-ai",
    )
    assert gate.mergable is False
    assert "human-login" in gate.changes_requested_from


def test_merge_gate_blocks_without_human_approval():
    gate = pr.merge_gate(
        reviews=[review("APPROVED", "sourcery-ai")],
        human_login="human-login",
        sourcery_login="sourcery-ai",
    )
    assert gate.mergable is False
    assert gate.human_approved is False


def test_merge_gate_commented_is_advisory_does_not_block():
    gate = pr.merge_gate(
        reviews=[
            review("APPROVED", "human-login"),
            review("APPROVED", "sourcery-ai"),
            review("COMMENTED", "sourcery-ai"),
        ],
        human_login="human-login",
        sourcery_login="sourcery-ai",
    )
    assert gate.mergable is True
    assert gate.advisory_comments == ["sourcery-ai"]


# ---- dismissal routing ----


def test_dismissal_action_addressed_routes_to_commit():
    route = pr.route_dismissal({"action": "addressed", "comment_id": "C1"})
    assert route.kind is pr.DismissalKind.ADDRESSED
    assert route.reason is None


def test_dismissal_action_dismissed_routes_to_pr_reply():
    route = pr.route_dismissal(
        {"action": "dismissed", "comment_id": "C1", "reason": "not applicable"}
    )
    assert route.kind is pr.DismissalKind.DISMISSED
    assert route.reason == "not applicable"


def test_dismissal_unknown_action_is_error():
    import pytest

    with pytest.raises(pr.DismissalParseError):
        pr.route_dismissal({"action": "huh", "comment_id": "C1"})


def test_parse_dismissals_from_fenced_yaml_block():
    block = """\
```yaml
items:
  - {comment_id: C1, action: addressed}
  - {comment_id: C2, action: dismissed, reason: "out of scope"}
```
"""
    routes = pr.parse_dismissals(block)
    assert len(routes) == 2
    assert routes[0].kind is pr.DismissalKind.ADDRESSED
    assert routes[1].kind is pr.DismissalKind.DISMISSED
    assert routes[1].reason == "out of scope"


# ---- mock ----


def test_mock_pr_create_returns_number_and_records():
    m = pr.MockGh()
    assert m.pr_create("impl-01", "impl-01", "main", "t", "b") == 1
    assert m.created == [(1, "impl-01", "impl-01", "main", "t", "b")]


def test_mock_api_reviews_returns_fixture():
    m = pr.MockGh(reviews_fixture=[{"user": "sourcery-ai", "state": "APPROVED"}])
    assert m.api_reviews("o/r", 1) == [{"user": "sourcery-ai", "state": "APPROVED"}]


def test_make_gh_picks_mock_or_real():
    assert isinstance(pr.make_gh(mock=True), pr.MockGh)
    assert isinstance(pr.make_gh(mock=False), pr.Gh)
