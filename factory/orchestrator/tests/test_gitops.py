"""Tests for gitops.py — worktree lifecycle + per-cycle commit + push/archive."""

from __future__ import annotations

import gitops

# ---- real wrapper argv construction ----


def test_worktree_add_builds_argv(tmp_path):
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        return ("", 0)

    g = gitops.GitOps(runner=runner, repo="/repo")
    wt = g.worktree_add("impl-01", parent="/repo/..")
    assert wt.endswith("sf-impl-01")
    assert calls[0][:4] == ["git", "worktree", "add", wt]
    assert "-b" in calls[0] and "impl-01" in calls[0]


def test_commit_cycle_adds_all_and_force_adds_runlog_and_commits(tmp_path):
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        return ("", 0)

    g = gitops.GitOps(runner=runner, repo="/repo")
    g.commit_cycle("/wt", "impl-01 c1 PASS")
    # expect: git -C /wt add -A ; git -C /wt add -f run.log ; git -C /wt commit -m ...
    assert calls[0][:3] == ["git", "-C", "/wt"]
    assert "add" in calls[0] and "-A" in calls[0]
    assert calls[1][:3] == ["git", "-C", "/wt"]
    assert "-f" in calls[1] and "run.log" in calls[1]
    assert calls[2][:3] == ["git", "-C", "/wt"]
    assert "commit" in calls[2] and "-m" in calls[2] and "impl-01 c1 PASS" in calls[2]


def test_push_branch_builds_argv():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    gitops.GitOps(runner=runner, repo="/repo").push_branch("impl-01")
    assert seen[:3] == ["git", "push", "-u"]
    assert "impl-01" in seen


def test_tag_archive_builds_argv():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    gitops.GitOps(runner=runner, repo="/repo").tag_archive("impl-01")
    assert seen[:3] == ["git", "tag", "archive/impl-01"]


def test_worktree_remove_builds_argv():
    seen: list[str] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.extend(argv)
        return ("", 0)

    gitops.GitOps(runner=runner, repo="/repo").worktree_remove("/wt/sf-impl-01")
    assert seen[:4] == ["git", "worktree", "remove", "/wt/sf-impl-01"]


# ---- mock gitops: deterministic, no real git ----


def test_mock_worktree_add_creates_dirs_and_returns_path(tmp_path):
    m = gitops.MockGitOps(base=str(tmp_path))
    wt = m.worktree_add("impl-01", parent=str(tmp_path))
    assert wt.startswith(str(tmp_path))
    assert "sf-impl-01" in wt
    import os

    assert os.path.isdir(wt)


def test_mock_commit_cycle_records(tmp_path):
    m = gitops.MockGitOps(base=str(tmp_path))
    wt = m.worktree_add("impl-01", parent=str(tmp_path))
    m.commit_cycle(wt, "impl-01 c1 PASS")
    assert m.commits == [(wt, "impl-01 c1 PASS")]


def test_mock_push_remove_tag_record(tmp_path):
    m = gitops.MockGitOps(base=str(tmp_path))
    m.push_branch("impl-01")
    m.tag_archive("impl-01")
    m.worktree_remove("/wt/sf-impl-01")
    assert m.pushed == ["impl-01"]
    assert m.tagged == ["archive/impl-01"]
    assert m.removed == ["/wt/sf-impl-01"]


def test_make_gitops_picks_mock_or_real():
    assert isinstance(gitops.make_gitops(mock=True, base="/tmp"), gitops.MockGitOps)
    assert isinstance(gitops.make_gitops(mock=False), gitops.GitOps)
