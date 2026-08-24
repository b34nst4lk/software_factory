"""Guard util — the spine's git-as-state integrity backstop.

Two rules (ticket 05 Q2 / ticket 09 Invariants / decision 17):
  1. impl-ticket frontmatter changes are **value-only**: the frontmatter key set is
     unchanged and the prose body is unchanged. Only values of `status` / `cycle` /
     `last_verdict` may move. A new key, a removed key, or a body edit is a violation.
  2. staged paths must be a **subset of `{impl-ticket} ∪ scope_files`**: the impl
     ticket's frontmatter `scope_files` (read via `split_frontmatter`) plus the
     ticket itself are the only governed paths. A hard denylist (`.verdict.yaml`,
     `.verdict.yml`, `.venv`, `*.db`, `__pycache__`) rejects runtime-artifact cruft
     regardless of `scope_files`. `run.log` is no longer special-cased.

The pure checks below are the test seam. :func:`main` is the pre-commit entrypoint:
it reads staged file content via ``git`` and applies the two rules to staged impl
files (``.../impl/*.md``) and the staged path set.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import yaml

# `.md` under an `impl/` directory are impl tickets. Path-suffix match so it works
# inside worktrees.
_IMPL_RE = re.compile(r"(^|/)impl/[^/]+\.md$")
_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)

# Runtime-artifact cruft that must never be committed, regardless of scope_files.
# Suffix matches (path ends with) and path-component matches (a path segment equals).
_DENY_SUFFIXES = (".verdict.yaml", ".verdict.yml", ".db")
_DENY_COMPONENTS = (".venv", "__pycache__")


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


def _denied(path: str) -> bool:
    """True if a staged path matches the runtime-artifact denylist."""
    if path.endswith(_DENY_SUFFIXES):
        return True
    return any(part in _DENY_COMPONENTS for part in path.split("/"))


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


def check_staged_paths(
    staged_paths: Iterable[str], staged_contents: Mapping[str, str]
) -> list[Violation]:
    """Enforce staged paths ⊆ {impl-ticket} ∪ scope_files, with a hard denylist.

    ``staged_contents`` maps each staged path to its staged file content (used to
    read the impl ticket's ``scope_files`` frontmatter). Pure over its inputs.
    """
    paths = list(staged_paths)
    violations: list[Violation] = []

    impl_ticket = next((p for p in paths if _IMPL_RE.search(p)), None)
    governed: set[str] = set()
    if impl_ticket is not None:
        governed.add(impl_ticket)
        fm, _ = split_frontmatter(staged_contents.get(impl_ticket, ""))
        if fm is not None:
            scope = fm.get("scope_files")
            if isinstance(scope, list):
                governed.update(str(s) for s in scope)

    for path in paths:
        if _denied(path):
            violations.append(Violation(path, "denylist", "path matches runtime-artifact denylist"))
        elif path not in governed:
            violations.append(Violation(path, "scope", "path not in {impl-ticket} ∪ scope_files"))
    return violations


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


def check_staged(paths: Iterable[str]) -> list[Violation]:
    """Run both guard rules over an explicit list of staged paths (test seam)."""
    path_list = list(paths)
    violations: list[Violation] = []
    staged_contents: dict[str, str] = {}
    for path in path_list:
        if _IMPL_RE.search(path):
            before = _head_text(path)
            after = _index_text(path)
            staged_contents[path] = after
            # A new impl ticket (not in HEAD) is a to-tickets creation — allow it;
            # only modifications of an existing ticket are value-only-constrained.
            violations.extend(check_impl_file(before, after, path, is_new=before == ""))
    violations.extend(check_staged_paths(path_list, staged_contents))
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
