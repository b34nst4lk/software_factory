"""Guard util — the spine's git-as-state integrity backstop.

Three rules (ticket 05 Q2 / ticket 09 Invariants / decision 17; ticket 02 /
decision 14 & 25):
  1. impl-ticket frontmatter changes are **value-only**: the frontmatter key set is
     unchanged and the prose body is unchanged. Only values of `status` / `cycle` /
     `last_verdict` may move. A new key, a removed key, or a body edit is a violation.
  2. staged paths must be a **subset of `{impl-ticket} ∪ scope_files`**: the impl
     ticket's frontmatter `scope_files` (read via `split_frontmatter`) plus the
     ticket itself are the only governed paths. A hard denylist (`.verdict.yaml`,
     `.verdict.yml`, `.venv`, `*.db`, `__pycache__`) rejects runtime-artifact cruft
     regardless of `scope_files`. `run.log` is no longer special-cased.
  3. tests map to behaviors and behaviors map to tests: the impl ticket's
     `acceptance.behaviors` ids must each be cited by a test in `scope_files`, every
     `# maps to: <id>` must cite a real id, and every test function must carry a
     `# maps to:`. A test citing several ids is a non-blocking warning.

The pure checks below are the test seam. :func:`main` is the pre-commit entrypoint:
it reads staged file content via ``git`` and applies the three rules to staged impl
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

# A test file: basename `test_*.py` or `*_test.py` (with an optional directory path).
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py)$")
# Any `def` (optionally `async`, optionally indented) — used to track Python block
# boundaries so `# maps to:` comments are attributed to the enclosing test function.
_DEF_RE = re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)", re.MULTILINE)
# A `# maps to: <id>[, <id>...]` comment.
_MAPS_TO_RE = re.compile(r"#\s*maps to:\s*([^#\n]+)")

# Runtime-artifact cruft that must never be committed, regardless of scope_files.
# Suffix matches (path ends with) and path-component matches (a path segment equals).
_DENY_SUFFIXES = (".verdict.yaml", ".verdict.yml", ".db")
_DENY_COMPONENTS = (".venv", "__pycache__")
# Basename matches: discarded runtime artifacts that must never be committed.
_DENY_BASENAMES = ("run.log",)


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str


@dataclass(frozen=True)
class Warning:
    """Non-blocking guard finding (rule 3 multi-behavior mapping)."""

    func: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class BehaviorMapping:
    """One test function's `# maps to:` citations (possibly empty)."""

    func: str
    ids: tuple[str, ...]


@dataclass
class _Scope:
    """A function scope tracked while parsing a test file (indentation-aware)."""

    indent: int
    name: str
    is_test: bool
    ids: list[str]


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
    if path.rsplit("/", 1)[-1] in _DENY_BASENAMES:
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


# ---- third rule: test↔behavior mapping (ticket 02 / decision 14 & 25) ----


def _is_test_file(path: str) -> bool:
    """True if ``path`` looks like a pytest test file."""
    return bool(_TEST_FILE_RE.search(path))


def behavior_ids(fm: Mapping[str, object]) -> set[str]:
    """The set of `id` values across ``acceptance.behaviors``."""
    ids: set[str] = set()
    acceptance = fm.get("acceptance")
    if not isinstance(acceptance, list):
        return ids
    for entry in acceptance:
        if not isinstance(entry, dict):
            continue
        behaviors = entry.get("behaviors")
        if not isinstance(behaviors, list):
            continue
        for b in behaviors:
            if isinstance(b, dict) and "id" in b:
                ids.add(str(b["id"]))
    return ids


def duplicate_behavior_ids(fm: Mapping[str, object]) -> list[str]:
    """Sorted list of behavior ids that appear more than once in ``acceptance``.

    Duplicate ids are a ticket-authoring error: a single mapped test would otherwise
    satisfy two distinct behaviors. They are reported as a blocking Violation, never
    silently deduped.
    """
    seen: set[str] = set()
    dups: set[str] = set()
    acceptance = fm.get("acceptance")
    if not isinstance(acceptance, list):
        return []
    for entry in acceptance:
        if not isinstance(entry, dict):
            continue
        behaviors = entry.get("behaviors")
        if not isinstance(behaviors, list):
            continue
        for b in behaviors:
            if isinstance(b, dict) and "id" in b:
                i = str(b["id"])
                if i in seen:
                    dups.add(i)
                seen.add(i)
    return sorted(dups)


def extract_test_mappings(source: str) -> list[BehaviorMapping]:
    """Parse a test-file ``source``; one :class:`BehaviorMapping` per ``def test_*``.

    Each `# maps to: <id>` line inside a test function body is attributed to the
    enclosing test function. Indentation-aware block tracking means a comment inside
    a non-test helper (or at module level) is attributed to no test. A test function
    with no such comment gets an empty ``ids`` tuple.
    """
    out: list[BehaviorMapping] = []
    stack: list[_Scope] = []
    for line in source.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        # Pop scopes that no longer enclose this line (indent <= their indent).
        while stack and indent <= stack[-1].indent:
            scope = stack.pop()
            if scope.is_test:
                out.append(BehaviorMapping(scope.name, tuple(scope.ids)))
        m = _DEF_RE.match(line)
        if m:
            name = m.group(1)
            stack.append(_Scope(indent, name, name.startswith("test_"), []))
            continue
        mm = _MAPS_TO_RE.search(line)
        if mm is not None and stack and stack[-1].is_test:
            for part in mm.group(1).split(","):
                part = part.strip()
                if part:
                    stack[-1].ids.append(part)
    for scope in stack:
        if scope.is_test:
            out.append(BehaviorMapping(scope.name, tuple(scope.ids)))
    return out


def check_behavior_mapping(
    fm: Mapping[str, object], test_sources: Mapping[str, str], impl_path: str
) -> tuple[list[Violation], list[Warning]]:
    """Rule 3: enforce the test↔behavior bijection across ``test_sources``.

    When no test file is present in ``scope_files`` there is nothing to map, so no
    violation is raised (a doc-only ticket like B1 passes). Returns
    ``(violations, warnings)``.
    """
    violations: list[Violation] = []
    warnings: list[Warning] = []
    # Duplicate behavior ids are a ticket-authoring error, independent of tests.
    for dup in duplicate_behavior_ids(fm):
        violations.append(
            Violation(
                impl_path,
                "duplicate-behavior",
                f"behavior id '{dup}' appears more than once",
            )
        )
    if not test_sources:
        return violations, warnings
    bid_set = behavior_ids(fm)
    all_cited: set[str] = set()
    for tpath, src in test_sources.items():
        for m in extract_test_mappings(src):
            if not m.ids:
                violations.append(
                    Violation(tpath, "unmapped-test", f"{m.func} has no '# maps to:' comment")
                )
                continue
            distinct = set(m.ids)
            if len(distinct) > 1:
                warnings.append(Warning(m.func, tuple(sorted(distinct))))
            for i in m.ids:
                all_cited.add(i)
                if i not in bid_set:
                    violations.append(
                        Violation(tpath, "orphan-test", f"{m.func} cites unknown behavior id '{i}'")
                    )
    for bid in sorted(bid_set):
        if bid not in all_cited:
            violations.append(
                Violation(impl_path, "untested-behavior", f"behavior id '{bid}' has no mapped test")
            )
    return violations, warnings


def check_staged_paths(
    staged_paths: Iterable[str], staged_contents: Mapping[str, str]
) -> list[Violation]:
    """Enforce staged paths ⊆ {impl-ticket} ∪ scope_files, with a hard denylist.

    ``staged_contents`` maps each staged path to its staged file content (used to
    read the impl ticket's ``scope_files`` frontmatter). Pure over its inputs.
    """
    paths = list(staged_paths)
    violations: list[Violation] = []

    impl_paths = [p for p in paths if _IMPL_RE.search(p)]
    impl_ticket = impl_paths[0] if impl_paths else None
    # Bug #26: the governed-set rule applies to per-cycle commits, which stage exactly
    # one impl ticket (the orchestrator's commit_cycle stages {impl-ticket} ∪ scope_files).
    # A publish (to-tickets authoring multiple new units) stages several impl tickets at
    # once; it is not a per-cycle commit, so the governed-set rule is skipped for it —
    # only the denylist applies. A manual commit (no impl ticket) is also skipped.
    is_per_cycle = len(impl_paths) == 1
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
        elif is_per_cycle and path not in governed:
            # Per-cycle commits may stage only {impl-ticket} ∪ scope_files; anything
            # else is out of scope. Publishes (≥2 impl tickets) and manual commits
            # (0 impl tickets) are not scope-checked (denylist only).
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
    """Run all three guard rules over an explicit list of staged paths (test seam).

    Returns only blocking Violations; rule-3 warnings are exposed via
    :func:`check_staged_full` for the entrypoint to report.
    """
    violations, _warnings = check_staged_full(paths)
    return violations


def _behavior_check(
    impl_path: str, staged_contents: Mapping[str, str]
) -> tuple[list[Violation], list[Warning]]:
    """Run rule 3 for one impl ticket against its own frontmatter + scope_files."""
    fm, _ = split_frontmatter(staged_contents.get(impl_path, ""))
    if fm is None:
        return [], []
    scope = fm.get("scope_files")
    test_sources: dict[str, str] = {}
    if isinstance(scope, list):
        for sp in scope:
            sp = str(sp)
            if _is_test_file(sp) and sp in staged_contents:
                test_sources[sp] = staged_contents[sp]
    return check_behavior_mapping(fm, test_sources, impl_path)


def check_staged_full(paths: Iterable[str]) -> tuple[list[Violation], list[Warning]]:
    """Run all three guard rules; return ``(violations, warnings)``."""
    path_list = list(paths)
    violations: list[Violation] = []
    warnings: list[Warning] = []
    staged_contents: dict[str, str] = {}
    impl_paths: list[str] = []
    for path in path_list:
        if _IMPL_RE.search(path):
            impl_paths.append(path)
            before = _head_text(path)
            after = _index_text(path)
            staged_contents[path] = after
            # A new impl ticket (not in HEAD) is a to-tickets creation — allow it;
            # only modifications of an existing ticket are value-only-constrained.
            violations.extend(check_impl_file(before, after, path, is_new=before == ""))
        else:
            # Non-ticket staged paths (e.g. test files under scope_files) are read
            # from the index so rule 3 can parse their `# maps to:` comments.
            staged_contents[path] = _index_text(path)
    violations.extend(check_staged_paths(path_list, staged_contents))

    # Rule 3 runs independently for EACH staged impl ticket, using that ticket's own
    # frontmatter and scope_files (a publish with several tickets must not let earlier
    # tickets bypass the behavior↔test validation).
    for impl_path in impl_paths:
        v, w = _behavior_check(impl_path, staged_contents)
        violations.extend(v)
        warnings.extend(w)
    return violations, warnings


def main(argv: Sequence[str] | None = None) -> int:
    """Pre-commit entrypoint. Returns 0 if clean, 1 on any violation."""
    if argv is None:
        argv = sys.argv[1:]
    paths = argv if argv else staged_paths()
    violations, warnings = check_staged_full(paths)
    for v in violations:
        print(f"guard: {v.path}: {v.rule}: {v.detail}", file=sys.stderr)
    for w in warnings:
        print(
            f"guard: warn: {w.func}: maps to {len(w.ids)} behaviors: {', '.join(w.ids)}",
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
