"""Guard util — the spine's git-as-state integrity backstop.

Two rules (ticket 05 Q2 / ticket 09 Invariants):
  1. impl-ticket frontmatter changes are **value-only**: the frontmatter key set is
     unchanged and the prose body is unchanged. Only values of `status` / `cycle` /
     `last_verdict` may move. A new key, a removed key, or a body edit is a violation.
  2. ``run.log`` is **append-only**: a staged diff for ``run.log`` may not contain any
     removed line (no ``-`` lines that are not the ``---`` hunk-header).

The pure checks below are the test seam. :func:`main` is the pre-commit entrypoint:
it reads staged file content via ``git`` and applies the two rules to staged impl
tickets (``.../impl/*.md``) and ``run.log`` files.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import yaml

# `.md` under an `impl/` directory are impl tickets; any path ending in run.log is a
# run log. Both patterns are path-suffix matches so they work inside worktrees.
_IMPL_RE = re.compile(r"(^|/)impl/[^/]+\.md$")
_RUNLOG_RE = re.compile(r"(^|/)run\.log$")
_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str


def split_frontmatter(text: str) -> tuple[dict[str, object] | None, str]:
    """Split a ticket into ``(frontmatter_dict, prose_body)``.

    Returns ``(None, full_text)`` when there is no leading ``---`` frontmatter block.
    """
    m = _FM_RE.match(text)
    if m is None:
        return None, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return {}, m.group(2)
    return data, m.group(2)


def frontmatter_keys(text: str) -> frozenset[str]:
    fm, _ = split_frontmatter(text)
    if fm is None:
        return frozenset()
    return frozenset(fm.keys())


def key_set_changed(before: str, after: str) -> bool:
    return frontmatter_keys(before) != frontmatter_keys(after)


def body_changed(before: str, after: str) -> bool:
    _, body_before = split_frontmatter(before)
    _, body_after = split_frontmatter(after)
    return body_before != body_after


def run_log_has_deletions(diff_text: str) -> bool:
    """True if any unified-diff line is a removal (starts with ``-`` but not ``---``)."""
    for line in diff_text.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            return True
    return False


def check_impl_file(before: str, after: str, path: str, *, is_new: bool) -> list[Violation]:
    """Apply the value-only rule to one impl ticket.

    New files (``is_new``) are allowed to be created (to-tickets authors them once);
    only *modifications* of an existing impl ticket are constrained.
    """
    if is_new:
        return []
    out: list[Violation] = []
    if key_set_changed(before, after):
        out.append(Violation(path, "key-set", "frontmatter key set changed"))
    if body_changed(before, after):
        out.append(Violation(path, "body", "prose body changed"))
    return out


def check_run_log_diff(diff_text: str, path: str) -> list[Violation]:
    if run_log_has_deletions(diff_text):
        return [Violation(path, "append-only", "run.log has a removed/modified line")]
    return []


# ---- git integration for the pre-commit hook ----


def _git(args: Sequence[str]) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def staged_paths() -> list[str]:
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [p for p in out.splitlines() if p]


def _head_text(path: str) -> str:
    res = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else ""


def _index_text(path: str) -> str:
    return _git(["show", f":{path}"])


def _staged_diff(path: str) -> str:
    return _git(["diff", "--cached", "--", path])


def check_staged(paths: Iterable[str]) -> list[Violation]:
    """Run both guard rules over an explicit list of staged paths (test seam)."""
    violations: list[Violation] = []
    for path in paths:
        if _IMPL_RE.search(path):
            before = _head_text(path)
            after = _index_text(path)
            # A new impl ticket (not in HEAD) is a to-tickets creation — allow it;
            # only modifications of an existing ticket are value-only-constrained.
            violations.extend(check_impl_file(before, after, path, is_new=before == ""))
        elif _RUNLOG_RE.search(path):
            diff = _staged_diff(path)
            violations.extend(check_run_log_diff(diff, path))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    """Pre-commit entrypoint. Returns 0 if clean, 1 on any violation."""
    if argv is None:
        argv = sys.argv[1:]
    paths = argv if argv else staged_paths()
    violations = check_staged(paths)
    for v in violations:
        print(f"guard: {v.path}: {v.rule}: {v.detail}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
