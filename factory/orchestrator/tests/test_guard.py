"""Tests for guard.py — the value-only frontmatter + staged-paths-subset guard util."""

from __future__ import annotations

import pytest

import guard

# ---- split_frontmatter ----


def test_split_frontmatter_parses_keys_and_body():
    text = "---\nid: impl-01\ncycle: 0\n---\nBody line one.\nBody line two.\n"
    fm, body = guard.split_frontmatter(text)
    assert fm == {"id": "impl-01", "cycle": 0}
    assert body == "Body line one.\nBody line two.\n"


def test_split_frontmatter_returns_none_when_absent():
    fm, body = guard.split_frontmatter("just prose, no frontmatter\n")
    assert fm is None
    assert body == "just prose, no frontmatter\n"


# ---- key-set change detection ----

BEFORE = '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n---\n' "Implement greet.\n"
VALUE_ONLY = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: FAIL\n---\n"
    "Implement greet.\n"
)
KEY_ADDED = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: FAIL\n"
    "extra_key: boom\n---\nImplement greet.\n"
)
KEY_REMOVED = "---\nid: impl-01\nstatus: in_progress\ncycle: 1\n---\nImplement greet.\n"
BODY_EDITED = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: FAIL\n---\n"
    "Implement greet DIFFERENTLY.\n"
)


def test_key_set_changed_false_for_value_only_mutation():
    assert guard.key_set_changed(BEFORE, VALUE_ONLY) is False


def test_key_set_changed_true_when_key_added():
    assert guard.key_set_changed(BEFORE, KEY_ADDED) is True


def test_key_set_changed_true_when_key_removed():
    assert guard.key_set_changed(BEFORE, KEY_REMOVED) is True


def test_body_changed_false_for_value_only_mutation():
    assert guard.body_changed(BEFORE, VALUE_ONLY) is False


def test_body_changed_true_when_prose_edited():
    assert guard.body_changed(BEFORE, BODY_EDITED) is True


# ---- check_impl_file ----


def test_check_impl_file_value_only_change_no_violations():
    v = guard.check_impl_file(BEFORE, VALUE_ONLY, "01-greet.md", is_new=False)
    assert v == []


def test_check_impl_file_key_add_rejected():
    v = guard.check_impl_file(BEFORE, KEY_ADDED, "01-greet.md", is_new=False)
    assert len(v) == 1
    assert v[0].rule == "key-set"


def test_check_impl_file_body_edit_rejected():
    v = guard.check_impl_file(BEFORE, BODY_EDITED, "01-greet.md", is_new=False)
    assert len(v) == 1
    assert v[0].rule == "body"


def test_check_impl_file_new_file_allowed():
    v = guard.check_impl_file("", KEY_ADDED, "01-greet.md", is_new=True)
    assert v == []


# ---- check_staged_paths: staged paths ⊆ {impl-ticket} ∪ scope_files ----

IMPL = (
    '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n'
    "scope_files: [factory/greet.py]\n---\nImplement greet.\n"
)
IMPL_PATH = ".scratch/sf/impl/01-greet.md"


def _contents(impl: str = IMPL, **extra: str) -> dict[str, str]:
    c: dict[str, str] = {IMPL_PATH: impl}
    c.update(extra)
    return c


def test_governed_only_commit_accepted():
    # maps to: guard accepts a commit whose staged paths are exactly {impl-ticket} ∪ scope_files
    paths = [IMPL_PATH, "factory/greet.py"]
    contents = _contents(factory_greet_py="def greet():\n    pass\n")
    assert guard.check_staged_paths(paths, contents) == []


def test_manual_commit_without_impl_ticket_is_not_scope_checked():
    # Regression (bug #22): the governed-set rule applies only to per-cycle commits
    # (an impl ticket is staged). A manual commit (e.g. editing the map) has no impl
    # ticket; its paths are allowed, subject only to the denylist.
    paths = [".scratch/software-factory/map.md", "AGENTS.md"]
    contents = {".scratch/software-factory/map.md": "# map\n", "AGENTS.md": "# agents\n"}
    assert guard.check_staged_paths(paths, contents) == []

    # the denylist still applies to manual commits
    paths2 = [".scratch/software-factory/map.md", ".verdict.yaml"]
    contents2 = {".scratch/software-factory/map.md": "# map\n", ".verdict.yaml": "overall: PASS\n"}
    v = guard.check_staged_paths(paths2, contents2)
    assert len(v) == 1 and v[0].path == ".verdict.yaml"


def test_extra_non_governed_file_rejected():
    # maps to: guard rejects a commit whose staged paths are NOT a subset of {impl-ticket} ∪ scope_files
    paths = [IMPL_PATH, "factory/greet.py", "factory/other.py"]
    contents = _contents(factory_greet_py="def greet():\n    pass\n", factory_other_py="x\n")
    v = guard.check_staged_paths(paths, contents)
    assert len(v) == 1
    assert v[0].path == "factory/other.py"
    assert v[0].rule == "scope"


def test_scope_files_read_from_impl_frontmatter():
    # maps to: guard reads scope_files from the staged impl-ticket's YAML frontmatter
    paths = [IMPL_PATH, "factory/greet.py"]
    contents = _contents(factory_greet_py="def greet():\n    pass\n")
    assert guard.check_staged_paths(paths, contents) == []


def test_scope_files_absent_means_only_impl_ticket_governed():
    # maps to: guard reads scope_files from the staged impl-ticket's YAML frontmatter
    no_scope = (
        '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n---\n' "Implement greet.\n"
    )
    paths = [IMPL_PATH, "factory/greet.py"]
    contents = _contents(impl=no_scope, factory_greet_py="x\n")
    v = guard.check_staged_paths(paths, contents)
    assert len(v) == 1
    assert v[0].path == "factory/greet.py"


@pytest.mark.parametrize(
    "denied",
    [
        ".verdict.yaml",
        ".verdict.yml",
        ".venv",
        "data.db",
        "src/__pycache__/x.py",
    ],
)
def test_denylist_entry_rejected(denied):
    # maps to: guard hard-denies a staged path matching the denylist regardless of scope_files
    paths = [IMPL_PATH, "factory/greet.py", denied]
    contents = _contents(factory_greet_py="x\n", **{denied: "x\n"})
    v = guard.check_staged_paths(paths, contents)
    assert any(x.path == denied and x.rule == "denylist" for x in v)


def test_denied_path_rejected_even_if_in_scope_files():
    # maps to: a denied path is rejected even if it were in scope_files
    impl = (
        '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n'
        "scope_files: [.venv]\n---\nImplement greet.\n"
    )
    paths = [IMPL_PATH, ".venv"]
    contents = _contents(impl=impl, **{".venv": "x\n"})
    v = guard.check_staged_paths(paths, contents)
    assert any(x.path == ".venv" and x.rule == "denylist" for x in v)


def test_run_log_rejected_as_non_governed():
    # maps to: a staged run.log is rejected — it is a discarded runtime artifact on
    # the denylist (never committed), not a governed path.
    paths = [IMPL_PATH, "factory/greet.py", "run.log"]
    contents = _contents(factory_greet_py="x\n", **{"run.log": "boot\n"})
    v = guard.check_staged_paths(paths, contents)
    assert any(x.path == "run.log" and x.rule == "denylist" for x in v)
