"""GitHub PR wrapper (gh CLI) + merge-gate logic + dismissal routing, with --mock.

Contract (05 Q6, 06 Q4):
  - PR opened once at first all-6-gates-pass; only fix commits pushed after.
  - Merge gate = human `APPROVED` + Sourcery clean + no `CHANGES_REQUESTED` from either.
    `COMMENTED` suggestions are advisory (don't block).
  - Request-changes (Sourcery or human) routes back to the implementer as a fix cycle;
    the implementer's fix-cycle output is structured YAML per comment
    `{action: addressed | dismissed, reason}`. `addressed` -> commit + in-pane 6-gate
    verifier re-run + push; `dismissed` -> post the reason as a PR reply, no push.
  - Every PR push is 6-gate-verifier-green (enforced in cycle.py, not here).

:class:`Gh` is a thin subprocess wrapper (injectable ``runner`` for argv tests).
:class:`MockGh` is a deterministic stub. Both implement :class:`GhPort`.
"""

from __future__ import annotations

import enum
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import yaml

Runner = Callable[[list[str]], tuple[str, int]]


def _default_runner(argv: list[str]) -> tuple[str, int]:
    res = subprocess.run(argv, capture_output=True, text=True)
    return res.stdout, res.returncode


class GhPort(Protocol):
    def pr_create(self, branch: str, head: str, base: str, title: str, body: str) -> int: ...
    def api_reviews(self, repo: str, pr_num: int) -> list[dict[str, str]]: ...
    def pr_merge(self, pr_num: int, *, squash: bool) -> None: ...
    def pr_comment(self, pr_num: int, body: str) -> None: ...


class Gh:
    def __init__(self, runner: Runner | None = None, gh_bin: str = "gh") -> None:
        self._run = runner or _default_runner
        self._bin = gh_bin

    def _cmd(self, args: list[str]) -> tuple[str, int]:
        return self._run([self._bin, *args])

    def pr_create(self, branch: str, head: str, base: str, title: str, body: str) -> int:
        out, _ = self._cmd(
            ["pr", "create", "--head", head, "--base", base, "--title", title, "--body", body]
        )
        # gh pr create prints a URL like https://github.com/o/r/pull/12
        m = re.search(r"/pull/(\d+)", out)
        if m is None:
            raise RuntimeError(f"could not parse PR number from: {out!r}")
        return int(m.group(1))

    def api_reviews(self, repo: str, pr_num: int) -> list[dict[str, str]]:
        out, _ = self._cmd(["api", f"repos/{repo}/pulls/{pr_num}/reviews"])
        data = json.loads(out)
        return data if isinstance(data, list) else []

    def pr_merge(self, pr_num: int, *, squash: bool) -> None:
        args = ["pr", "merge", str(pr_num)]
        if squash:
            args.append("--squash")
        self._cmd(args)

    def pr_comment(self, pr_num: int, body: str) -> None:
        self._cmd(["pr", "comment", str(pr_num), "--body", body])


@dataclass(frozen=True)
class MergeGate:
    mergable: bool
    human_approved: bool
    sourcery_clean: bool
    changes_requested_from: list[str]
    advisory_comments: list[str]


def merge_gate(
    reviews: list[dict[str, str]], *, human_login: str, sourcery_login: str
) -> MergeGate:
    states_by_user: dict[str, str] = {r.get("user", ""): r.get("state", "") for r in reviews}
    human_approved = states_by_user.get(human_login, "") == "APPROVED"
    # Sourcery "clean" = its latest review is APPROVED (or no CHANGES_REQUESTED).
    sourcery_state = states_by_user.get(sourcery_login, "")
    sourcery_clean = sourcery_state != "CHANGES_REQUESTED"
    changes_requested_from = [u for u, s in states_by_user.items() if s == "CHANGES_REQUESTED"]
    advisory_comments = [u for u, s in states_by_user.items() if s == "COMMENTED"]
    mergable = human_approved and sourcery_clean and not changes_requested_from
    return MergeGate(
        mergable=mergable,
        human_approved=human_approved,
        sourcery_clean=sourcery_clean,
        changes_requested_from=changes_requested_from,
        advisory_comments=advisory_comments,
    )


class DismissalKind(enum.Enum):
    ADDRESSED = "addressed"
    DISMISSED = "dismissed"


class DismissalParseError(Exception):
    pass


@dataclass(frozen=True)
class DismissalRoute:
    comment_id: str
    kind: DismissalKind
    reason: str | None


def route_dismissal(item: dict[str, object]) -> DismissalRoute:
    action = str(item.get("action", "")).lower()
    comment_id = str(item.get("comment_id", ""))
    reason = item.get("reason")
    if action == "addressed":
        return DismissalRoute(comment_id, DismissalKind.ADDRESSED, None)
    if action == "dismissed":
        return DismissalRoute(comment_id, DismissalKind.DISMISSED, str(reason) if reason else None)
    raise DismissalParseError(f"unknown dismissal action: {action!r}")


_DISMISSAL_FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_dismissals(text: str) -> list[DismissalRoute]:
    m = _DISMISSAL_FENCE_RE.search(text)
    if m is None:
        return []
    data = yaml.safe_load(m.group(1)) or {}
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [route_dismissal(it) for it in items if isinstance(it, dict)]


class MockGh:
    def __init__(
        self,
        reviews_fixture: list[dict[str, str]] | None = None,
        reviews_queue: list[list[dict[str, str]]] | None = None,
    ) -> None:
        self._next = 0
        self.reviews_fixture = reviews_fixture or []
        self.reviews_queue = list(reviews_queue) if reviews_queue else []
        self.created: list[tuple[int, str, str, str, str, str]] = []
        self.merged: list[int] = []
        self.comments: list[tuple[int, str]] = []

    def pr_create(self, branch: str, head: str, base: str, title: str, body: str) -> int:
        self._next += 1
        self.created.append((self._next, branch, head, base, title, body))
        return self._next

    def api_reviews(self, repo: str, pr_num: int) -> list[dict[str, str]]:
        if self.reviews_queue:
            return self.reviews_queue.pop(0)
        return list(self.reviews_fixture)

    def pr_merge(self, pr_num: int, *, squash: bool) -> None:
        self.merged.append(pr_num)

    def pr_comment(self, pr_num: int, body: str) -> None:
        self.comments.append((pr_num, body))


def make_gh(*, mock: bool, **_kw: object) -> GhPort:
    return MockGh() if mock else Gh()
