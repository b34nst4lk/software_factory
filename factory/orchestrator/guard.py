"""Guard util — the spine's git-as-state integrity backstop.

Three rules (ticket 05 Q2 / ticket 09 Invariants / decision 17 + decision 14):
  1. impl-ticket frontmatter changes are **value-only**: the frontmatter key set is
     unchanged and the prose body is unchanged. Only values of `status` / `cycle` /
     `last_verdict` may move. A new key, a removed key, or a body edit is a violation.
  2. staged paths must be a **subset of `{impl-ticket} ∪ scope_files`**: the impl
     ticket's frontmatter `scope_files` (read via `split_frontmatter`) plus the
     ticket itself are the only governed paths. A hard denylist (`.verdict.yaml`,
     `.verdict.yml`, `.venv`, `*.db`, `__pycache__`) rejects runtime-artifact cruft
     regardless of `scope_files`. `run.log` is no longer special-cased.
  3. **test↔behavior mapping** (decision 14, driven by the inner-loop micro-cycles):
     every `acceptance.behaviors` id must have ≥1 mapped test, every `# maps to:`
     must cite a real id, and every test function must carry a `# maps to:`. Hard
     Violations block the commit. A test mapping to *multiple* behaviors is a
     non-blocking :class:`Warning` (the verifier judges), not a Violation.

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

# Runtime-artifact cruft that must never be committed, regardless of scope_files.
# Suffix matches (path ends with) and path-component matches (a path segment equals).
_DENY_SUFFIXES = (".verdict.yaml", ".verdict.yml", ".db")
_DENY_COMPONENTS = (".venv", "__pycache__")
# Basename matches: discarded runtime artifacts that must never be committed.
_DENY_BASENAMES = ("run.log",)

# A file is a test file if its basename is `test_*.py` or `*_test.py`.
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+\.py|[^/]*_test\.py)$")
# The `# maps to: <id>` comment; captures the id. Matches anywhere on a line so
# both standalone and inline trailing comments are recognised.
_MAP_RE = re.compile(r"#\s*maps to:\s*([A-Za-z0-9_.-]+)")
_DEF_TEST_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(")


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str


@dataclass(frozen=True)
class Warning:
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


def check_staged_paths(
    staged_paths: Iterable[str],
    staged_contents: Mapping[str, str],
    *,
    warnings_out: list[Warning] | None = None,
) -> list[Violation]:
    """Enforce staged paths ⊆ {impl-ticket} ∪ scope_files, with a hard denylist.

    ``staged_contents`` maps each staged path to its staged file content (used to
    read the impl ticket's ``scope_files`` frontmatter and its test files for the
    test↔behavior mapping rule). Pure over its inputs. Non-blocking rule-3
    warnings are appended to ``warnings_out`` (if given) and never returned.
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
        # Rule 3 (test↔behavior mapping) runs only on per-cycle commits: the scope
        # test files are read from the staged contents, and a publish authors new
        # units with no tests yet (would spuriously violate). Behaviours must carry
        # an ``id`` to be trackable; a ticket with none is not behavior-checked.
        if is_per_cycle and fm is not None and acceptance_behavior_ids(fm):
            test_mappings: dict[str, list[str]] = {}
            for scope_path in sorted(governed):
                if _TEST_FILE_RE.search(scope_path):
                    for fn, ids in test_function_mappings(
                        staged_contents.get(scope_path, "")
                    ).items():
                        test_mappings.setdefault(fn, []).extend(ids)
            rule_violations, rule_warnings = check_behavior_mapping(
                acceptance_behavior_ids(fm), test_mappings, path=impl_ticket
            )
            violations.extend(rule_violations)
            if warnings_out is not None:
                warnings_out.extend(rule_warnings)

    for path in paths:
        if _denied(path):
            violations.append(Violation(path, "denylist", "path matches runtime-artifact denylist"))
        elif is_per_cycle and path not in governed:
            # Per-cycle commits may stage only {impl-ticket} ∪ scope_files; anything
            # else is out of scope. Publishes (≥2 impl tickets) and manual commits
            # (0 impl tickets) are not scope-checked (denylist only).
            violations.append(Violation(path, "scope", "path not in {impl-ticket} ∪ scope_files"))
    return violations


# ---- rule 3: test↔behavior mapping (decision 14) ----


def acceptance_behavior_ids(frontmatter: Mapping[str, object]) -> set[str]:
    """Extract the set of behavior ``id`` values from a ticket's ``acceptance``.

    Behaviors without an ``id`` are ignored (only id-carrying behaviors are
    trackable by tests). Returns an empty set when ``acceptance`` is absent or
    malformed.
    """
    ids: set[str] = set()
    acceptance = frontmatter.get("acceptance")
    if not isinstance(acceptance, list):
        return ids
    for entry in acceptance:
        if not isinstance(entry, dict):
            continue
        behaviors = entry.get("behaviors")
        if not isinstance(behaviors, list):
            continue
        for behavior in behaviors:
            if not isinstance(behavior, dict):
                continue
            bid = behavior.get("id")
            if isinstance(bid, str):
                ids.add(bid)
    return ids


def test_function_mappings(content: str) -> dict[str, list[str]]:
    """Map each ``def test_*`` function to the ``# maps to: <id>`` ids inside it.

    A comment before the first test function or inside a non-test helper is
    ignored. A test function with no mapping yields an empty list. Multiple
    mappings on one function are preserved in order.
    """
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.splitlines():
        def_match = _DEF_TEST_RE.match(line)
        if def_match is not None:
            current = def_match.group(1)
            out.setdefault(current, [])
        if current is None:
            continue
        map_match = _MAP_RE.search(line)
        if map_match is not None:
            out[current].append(map_match.group(1))
    return out


def check_behavior_mapping(
    behavior_ids: set[str],
    mappings: Mapping[str, Sequence[str]],
    *,
    path: str,
) -> tuple[list[Violation], list[Warning]]:
    """Enforce the test↔behavior mapping rule (rule 3).

    Hard Violations (block the commit):
      * every behavior id has ≥1 mapped test (no untested behavior);
      * every ``# maps to:`` cites a real id (no orphan test);
      * every test function has a ``# maps to:`` (no unmapped test).

    A test function mapping to more than one behavior is a non-blocking Warning
    (the verifier judges whether it really probes them all), not a Violation.
    """
    violations: list[Violation] = []
    warnings: list[Warning] = []
    for bid in sorted(behavior_ids):
        if not any(bid in ids for ids in mappings.values()):
            violations.append(
                Violation(
                    path, "behavior-mapping", f"behavior {bid} has no mapped test (untested)"
                )
            )
    for fn, ids in mappings.items():
        if not ids:
            violations.append(
                Violation(path, "behavior-mapping", f"test {fn} has no '# maps to:' (unmapped)")
            )
            continue
        if len(ids) > 1:
            warnings.append(
                Warning(path, "behavior-mapping", f"test {fn} maps to multiple behaviors {ids}")
            )
        for mid in ids:
            if mid not in behavior_ids:
                violations.append(
                    Violation(path, "behavior-mapping", f"test {fn} maps to unknown behavior {mid}")
                )
    return violations, warnings


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


def check_staged(paths: Iterable[str]) -> tuple[list[Violation], list[Warning]]:
    """Run the guard rules over an explicit list of staged paths (test seam).

    Returns ``(violations, warnings)``. Warnings are non-blocking rule-3
    diagnostics the verifier should weigh, not commit blockers.
    """
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
    warnings: list[Warning] = []
    violations.extend(check_staged_paths(path_list, staged_contents, warnings_out=warnings))
    return violations, warnings


def main(argv: Sequence[str] | None = None) -> int:
    """Pre-commit entrypoint. Returns 0 if clean, 1 on any violation.

    Warnings are printed (prefixed ``guard-warn``) but do not fail the commit.
    """
    if argv is None:
        argv = sys.argv[1:]
    paths = argv if argv else staged_paths()
    violations, warnings = check_staged(paths)
    for v in violations:
        print(f"guard: {v.path}: {v.rule}: {v.detail}", file=sys.stderr)
    for w in warnings:
        print(f"guard-warn: {w.path}: {w.rule}: {w.detail}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
