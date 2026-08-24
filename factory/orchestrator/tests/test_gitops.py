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


def test_commit_cycle_stages_explicit_governed_paths_and_returns_sha(tmp_path):
    # maps to: commit_cycle stages exactly {impl-ticket} ∪ scope_files, each by explicit
    # `git add -- <path>`; it never uses `git add -A`/`git add .`/`git add -f run.log`.
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return ("abc123", 0)
        return ("", 0)

    g = gitops.GitOps(runner=runner, repo="/repo")
    sha = g.commit_cycle(
        "/wt",
        "impl-01 c1 PASS",
        impl_ticket=".scratch/sf/impl/01-greet.md",
        scope_files=["factory/greet.py", "factory/greet_test.py"],
    )
    assert sha == "abc123"  # returns the commit sha
    # exactly ONE explicit `git add -- <paths>`; never -A / . / -f run.log
    add_calls = [c for c in calls if "add" in c]
    assert len(add_calls) == 1
    add = add_calls[0]
    assert add[:3] == ["git", "-C", "/wt"]
    assert "--" in add
    assert ".scratch/sf/impl/01-greet.md" in add
    assert "factory/greet.py" in add
    assert "factory/greet_test.py" in add
    assert "-A" not in add
    assert "." not in add  # no bare `git add .`
    assert "-f" not in add and "run.log" not in add
    # then commit, then rev-parse HEAD for the sha
    assert calls[-2][:3] == ["git", "-C", "/wt"] and "commit" in calls[-2]
    assert "impl-01 c1 PASS" in calls[-2]
    assert calls[-1][-2:] == ["rev-parse", "HEAD"]


def test_commit_cycle_does_not_stage_runtime_artifacts(tmp_path):
    # maps to: a runtime artifact (e.g. .verdict.yaml, a .venv symlink) present in the
    # worktree is NOT staged by commit_cycle (it is not in the governed set).
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        calls.append(argv)
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return ("sha1", 0)
        return ("", 0)

    g = gitops.GitOps(runner=runner, repo="/repo")
    g.commit_cycle("/wt", "m", impl_ticket="t.md", scope_files=["a.py"])
    add = [c for c in calls if "add" in c][0]
    assert ".verdict.yaml" not in add
    assert ".venv" not in add
    assert "run.log" not in add


def test_branch_sha_builds_argv():
    # maps to: the ref-advance assert compares the branch ref to HEAD via a real
    # `git rev-parse <branch>` in the real GitOps.
    seen: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[str, int]:
        seen.append(argv)
        return ("deadbeef", 0)

    g = gitops.GitOps(runner=runner, repo="/repo")
    assert g.branch_sha("/wt", "impl-01") == "deadbeef"
    assert seen[0][:3] == ["git", "-C", "/wt"]
    assert seen[0][-2:] == ["rev-parse", "impl-01"]


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


def test_mock_commit_cycle_records_sha_and_governed_paths(tmp_path):
    # maps to: MockGitOps stays in step with the real GitOps — records the governed
    # paths and the returned sha, and its branch_sha equals the head after a commit.
    m = gitops.MockGitOps(base=str(tmp_path))
    wt = m.worktree_add("impl-01", parent=str(tmp_path))
    sha = m.commit_cycle(wt, "impl-01 c1 PASS", impl_ticket="t.md", scope_files=["a.py", "b.py"])
    assert sha  # non-empty sha
    assert m.commits == [(wt, "impl-01 c1 PASS", "t.md", ["a.py", "b.py"], sha)]
    # stubbed ref-advance: after a commit the branch ref points at the head sha
    assert m.branch_sha(wt, "impl-01") == sha


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
