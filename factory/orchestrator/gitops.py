"""Git operations seam — worktree lifecycle, per-cycle commit, push, archive.

Isolated so the deterministic state machine (cycle/run) never calls git directly:
the real :class:`GitOps` shells out to ``git``; :class:`MockGitOps` records without a
repository. run.py owns the worktree lifecycle and the per-cycle commit cadence; the
guard pre-commit hook enforces value-only frontmatter inside the worktree commit
(worktrees share the repo's hooks via the commondir).

Per-cycle commit (05 Q2, decision 17): stage **exactly** the governed set — the impl
ticket plus its ``scope_files`` — by explicit path (``git add -- <path>``), never
``git add -A``/``.`` (which swept runtime artifacts like ``.verdict.yaml`` and a
``.venv`` symlink into per-cycle commits). A mixed ``git reset`` first clears any
pre-staged paths from the index so the commit contains exactly the governed set.
``run.log`` is no longer tracked (the SQLite DB is the narrative now), so there is no
force-add. ``commit_cycle`` checks git's return codes (a failed commit raises instead
of returning a stale sha) and returns the commit sha so the narrative can log it;
``branch_sha`` reads the ``impl/NN`` ref for the ref-advance assert. ``push_branch``
pushes an ``impl/NN`` branch for the PR; ``tag_archive`` tags the merged branch
``archive/impl-NN``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import Protocol

Runner = Callable[[list[str]], tuple[str, int]]


class GitError(Exception):
    """Raised when a git command exits nonzero (e.g. a rejected commit)."""


def _default_runner(argv: list[str]) -> tuple[str, int]:
    res = subprocess.run(argv, capture_output=True, text=True)
    return res.stdout, res.returncode


class GitOpsPort(Protocol):
    def worktree_add(self, branch: str, *, parent: str) -> str: ...
    def commit_cycle(
        self, worktree: str, message: str, *, impl_ticket: str, scope_files: list[str]
    ) -> str: ...
    def branch_sha(self, worktree: str, branch: str) -> str: ...
    def push_branch(self, branch: str) -> None: ...
    def worktree_remove(self, worktree: str) -> None: ...
    def tag_archive(self, branch: str) -> None: ...


class GitOps:
    def __init__(self, *, repo: str, runner: Runner | None = None) -> None:
        self._repo = repo
        self._run = runner or _default_runner

    def _cmd(self, args: list[str]) -> None:
        self._run(["git", *args])

    def _run_checked(self, args: list[str]) -> tuple[str, int]:
        """Run a git command and raise :class:`GitError` on a nonzero exit.

        A failed ``git commit`` (Husky rejection, empty index) or ``git rev-parse``
        must not silently return a stale sha — that would let the ref-advance assert
        pass falsely and record a cycle as committed when no commit was created.
        """
        out, code = self._run(args)
        if code != 0:
            raise GitError(f"git {' '.join(args)} failed with exit code {code}")
        return out, code

    def worktree_add(self, branch: str, *, parent: str) -> str:
        path = os.path.join(parent, f"sf-{branch}")
        self._cmd(["worktree", "add", path, "-b", branch])
        return path

    def commit_cycle(
        self, worktree: str, message: str, *, impl_ticket: str, scope_files: list[str]
    ) -> str:
        """Stage exactly the governed set, commit, and return the HEAD sha.

        A mixed ``git reset`` first clears any pre-staged paths from the index (keeps
        the worktree) so a pre-staged runtime artifact (``.verdict.yaml``, ``.venv``,
        ``run.log``) cannot leak into the commit — the commit contains exactly
        ``{impl-ticket} ∪ scope_files``. Git return codes are checked so a failed
        commit raises instead of returning a stale sha.
        """
        paths = [impl_ticket, *scope_files]
        self._run_checked(["git", "-C", worktree, "reset"])
        self._run_checked(["git", "-C", worktree, "add", "--", *paths])
        self._run_checked(["git", "-C", worktree, "commit", "-m", message])
        out, _ = self._run_checked(["git", "-C", worktree, "rev-parse", "HEAD"])
        return out.strip()

    def branch_sha(self, worktree: str, branch: str) -> str:
        """The sha a branch ref points at."""
        out, _ = self._run(["git", "-C", worktree, "rev-parse", branch])
        return out.strip()

    def push_branch(self, branch: str) -> None:
        self._cmd(["push", "-u", "origin", branch])

    def worktree_remove(self, worktree: str) -> None:
        self._cmd(["worktree", "remove", worktree])

    def tag_archive(self, branch: str) -> None:
        self._cmd(["tag", f"archive/{branch}", branch])


class MockGitOps:
    def __init__(self, *, base: str) -> None:
        self._base = base
        self.commits: list[tuple[str, str, str, list[str], str]] = []
        self.pushed: list[str] = []
        self.removed: list[str] = []
        self.tagged: list[str] = []
        self._seq = 0
        self._head = ""

    def worktree_add(self, branch: str, *, parent: str) -> str:
        path = os.path.join(parent, f"sf-{branch}")
        os.makedirs(path, exist_ok=True)
        return path

    def commit_cycle(
        self, worktree: str, message: str, *, impl_ticket: str, scope_files: list[str]
    ) -> str:
        self._seq += 1
        sha = f"sha-{self._seq}"
        self.commits.append((worktree, message, impl_ticket, list(scope_files), sha))
        self._head = sha
        return sha

    def branch_sha(self, worktree: str, branch: str) -> str:
        # stubbed ref-advance: after a commit the branch ref points at the head sha.
        return self._head

    def push_branch(self, branch: str) -> None:
        self.pushed.append(branch)

    def worktree_remove(self, worktree: str) -> None:
        self.removed.append(worktree)

    def tag_archive(self, branch: str) -> None:
        self.tagged.append(f"archive/{branch}")


def make_gitops(*, mock: bool, repo: str = "", base: str = ".") -> GitOpsPort:
    return MockGitOps(base=base) if mock else GitOps(repo=repo)
