"""Git operations seam — worktree lifecycle, per-cycle commit, push, archive.

Isolated so the deterministic state machine (cycle/run) never calls git directly:
the real :class:`GitOps` shells out to ``git``; :class:`MockGitOps` records without a
repository. run.py owns the worktree lifecycle and the per-cycle commit cadence; the
guard pre-commit hook enforces value-only frontmatter + append-only run.log inside the
worktree commit (worktrees share the repo's hooks via the commondir).

Per-cycle commit (05 Q2): stage everything, force-add the tracked ``run.log`` (it is
gitignored by ``*.log`` and re-included by ``!run.log``; force-add is belt-and-braces),
commit with a per-cycle message. ``push_branch`` pushes an ``impl/NN`` branch for the
PR; ``tag_archive`` tags the merged branch ``archive/impl-NN``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import Protocol

Runner = Callable[[list[str]], tuple[str, int]]


def _default_runner(argv: list[str]) -> tuple[str, int]:
    res = subprocess.run(argv, capture_output=True, text=True)
    return res.stdout, res.returncode


class GitOpsPort(Protocol):
    def worktree_add(self, branch: str, *, parent: str) -> str: ...
    def commit_cycle(self, worktree: str, message: str) -> None: ...
    def push_branch(self, branch: str) -> None: ...
    def worktree_remove(self, worktree: str) -> None: ...
    def tag_archive(self, branch: str) -> None: ...


class GitOps:
    def __init__(self, *, repo: str, runner: Runner | None = None) -> None:
        self._repo = repo
        self._run = runner or _default_runner

    def _cmd(self, args: list[str]) -> None:
        self._run(["git", *args])

    def worktree_add(self, branch: str, *, parent: str) -> str:
        path = os.path.join(parent, f"sf-{branch}")
        self._cmd(["worktree", "add", path, "-b", branch])
        return path

    def commit_cycle(self, worktree: str, message: str) -> None:
        self._run(["git", "-C", worktree, "add", "-A"])
        # run.log is gitignored by *.log but re-included by !run.log; force-add anyway.
        self._run(["git", "-C", worktree, "add", "-f", "run.log"])
        self._run(["git", "-C", worktree, "commit", "-m", message])

    def push_branch(self, branch: str) -> None:
        self._cmd(["push", "-u", "origin", branch])

    def worktree_remove(self, worktree: str) -> None:
        self._cmd(["worktree", "remove", worktree])

    def tag_archive(self, branch: str) -> None:
        self._cmd(["tag", f"archive/{branch}", branch])


class MockGitOps:
    def __init__(self, *, base: str) -> None:
        self._base = base
        self.commits: list[tuple[str, str]] = []
        self.pushed: list[str] = []
        self.removed: list[str] = []
        self.tagged: list[str] = []
        self._seq = 0

    def worktree_add(self, branch: str, *, parent: str) -> str:
        path = os.path.join(parent, f"sf-{branch}")
        os.makedirs(path, exist_ok=True)
        return path

    def commit_cycle(self, worktree: str, message: str) -> None:
        self.commits.append((worktree, message))

    def push_branch(self, branch: str) -> None:
        self.pushed.append(branch)

    def worktree_remove(self, worktree: str) -> None:
        self.removed.append(worktree)

    def tag_archive(self, branch: str) -> None:
        self.tagged.append(f"archive/{branch}")


def make_gitops(*, mock: bool, repo: str = "", base: str = ".") -> GitOpsPort:
    return MockGitOps(base=base) if mock else GitOps(repo=repo)
