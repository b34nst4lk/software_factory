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


# ---- bug #26: publish (multiple new impl tickets) vs per-cycle commit ----

IMPL2_PATH = ".scratch/sf/impl/02-wave.md"
IMPL2 = (
    '---\nid: impl-02\nstatus: open\ncycle: 0\nlast_verdict: ""\n'
    "scope_files: [factory/wave.py]\n---\nImplement wave.\n"
)


def test_publish_multiple_impl_tickets_not_scope_checked():
    # Regression (bug #26): a publish stages several new impl tickets (with their
    # own scope_files) plus the map/issues sync. It is not a per-cycle commit, so the
    # governed-set rule is skipped — only the denylist applies. (A per-cycle commit
    # stages exactly one impl ticket.)
    paths = [IMPL_PATH, IMPL2_PATH, ".scratch/sf/map.md"]
    contents = _contents(impl=IMPL, **{IMPL2_PATH: IMPL2, ".scratch/sf/map.md": "# map\n"})
    assert guard.check_staged_paths(paths, contents) == []


def test_publish_denylist_still_applies():
    # maps to: even on a publish (≥2 impl tickets), the denylist still rejects a
    # runtime-artifact path.
    paths = [IMPL_PATH, IMPL2_PATH, ".verdict.yaml"]
    contents = _contents(impl=IMPL, **{IMPL2_PATH: IMPL2, ".verdict.yaml": "overall: PASS\n"})
    v = guard.check_staged_paths(paths, contents)
    assert len(v) == 1 and v[0].path == ".verdict.yaml" and v[0].rule == "denylist"


def test_single_impl_ticket_still_governed():
    # maps to: a single impl ticket + an out-of-scope file is still rejected — the
    # count signal (≥2 = publish) does not relax the per-cycle rule for one ticket.
    paths = [IMPL_PATH, "factory/greet.py", "factory/other.py"]
    contents = _contents(factory_greet_py="x\n", factory_other_py="x\n")
    v = guard.check_staged_paths(paths, contents)
    assert len(v) == 1 and v[0].path == "factory/other.py" and v[0].rule == "scope"


# ---- third rule: test↔behavior mapping (ticket 02 / decision 14 & 25) ----


def _acceptance_fm(*ids: str) -> dict[str, object]:
    behaviors = [{"id": i, "behavior": "b", "outcome": "success"} for i in ids]
    return {"acceptance": [{"story": "s", "behaviors": behaviors}]}


def test_behavior_ids_parses_acceptance_behaviors():
    # maps to: B2
    fm = _acceptance_fm("B1", "B2", "B3")
    assert guard.behavior_ids(fm) == {"B1", "B2", "B3"}


def test_behavior_ids_returns_empty_when_no_acceptance():
    # maps to: B2
    assert guard.behavior_ids({}) == set()


def test_extract_test_mappings_collects_maps_to_per_function():
    # maps to: B3
    src = (
        "def test_a():\n"
        "    # maps to: B2\n"
        "    assert 1\n"
        "\n"
        "def test_b():\n"
        "    # maps to: B3, B4\n"
        "    assert 2\n"
    )
    ms = guard.extract_test_mappings(src)
    assert [(m.func, m.ids) for m in ms] == [
        ("test_a", ("B2",)),
        ("test_b", ("B3", "B4")),
    ]


def test_extract_test_mappings_tracks_function_without_mapping():
    # maps to: B3
    src = "def test_a():\n    assert 1\n"
    ms = guard.extract_test_mappings(src)
    assert [(m.func, m.ids) for m in ms] == [("test_a", ())]


def test_behavior_mapping_clean_passes():
    # maps to: B2
    # maps to: B3
    # maps to: B4
    fm = _acceptance_fm("B1", "B2")
    tests = {
        "factory/t.py": (
            "def test_x():\n    # maps to: B1\n    pass\n"
            "\n"
            "def test_y():\n    # maps to: B2\n    pass\n"
        )
    }
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert v == [] and w == []


def test_orphan_test_rejected():
    # maps to: B4
    fm = _acceptance_fm("B1")
    tests = {
        "factory/t.py": (
            "def test_x():\n    # maps to: B1\n    pass\n"
            "\n"
            "def test_y():\n    # maps to: B9\n    pass\n"
        )
    }
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert any(x.rule == "orphan-test" for x in v)


def test_unmapped_test_rejected():
    # maps to: B4
    fm = _acceptance_fm("B1")
    tests = {
        "factory/t.py": (
            "def test_x():\n    # maps to: B1\n    pass\n" "\n" "def test_y():\n    assert 1\n"
        )
    }
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert any(x.rule == "unmapped-test" for x in v)


def test_untested_behavior_rejected():
    # maps to: B4
    fm = _acceptance_fm("B1", "B2")
    tests = {"factory/t.py": "def test_x():\n    # maps to: B1\n    pass\n"}
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert any(x.rule == "untested-behavior" for x in v)


def test_no_test_files_means_no_mapping_enforcement():
    # maps to: B4
    fm = _acceptance_fm("B1", "B2")
    assert guard.check_behavior_mapping(fm, {}, "impl") == ([], [])


def test_multi_behavior_mapping_warns_but_not_violates():
    # maps to: B5
    fm = _acceptance_fm("B1", "B2")
    tests = {"factory/t.py": "def test_x():\n    # maps to: B1, B2\n    pass\n"}
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert v == []
    assert len(w) == 1
    assert w[0].func == "test_x"
    assert w[0].ids == ("B1", "B2")


# ---- PR #12 fixes (Sourcery bug-risk comments) ----


def test_extract_test_mappings_handles_async_and_class_scoped():
    # maps to: B3
    src = (
        "class TestGreet:\n"
        "    async def test_async(self):\n"
        "        # maps to: B1\n"
        "        pass\n"
        "\n"
        "    def test_sync(self):\n"
        "        # maps to: B2\n"
        "        pass\n"
    )
    ms = guard.extract_test_mappings(src)
    assert [(m.func, m.ids) for m in ms] == [
        ("test_async", ("B1",)),
        ("test_sync", ("B2",)),
    ]


def test_extract_test_mappings_ignores_comment_in_helper():
    # maps to: B3
    src = (
        "def test_a():\n"
        "    # maps to: B1\n"
        "    pass\n"
        "\n"
        "def helper():\n"
        "    # maps to: B2\n"
        "    return 1\n"
        "\n"
        "def test_b():\n"
        "    # maps to: B3\n"
        "    pass\n"
    )
    ms = guard.extract_test_mappings(src)
    assert [(m.func, m.ids) for m in ms] == [
        ("test_a", ("B1",)),
        ("test_b", ("B3",)),
    ]


def test_duplicate_behavior_ids_rejected():
    # maps to: B4
    fm = {
        "acceptance": [
            {"story": "s", "behaviors": [{"id": "B1", "behavior": "a", "outcome": "success"}]},
            {"story": "s2", "behaviors": [{"id": "B1", "behavior": "b", "outcome": "success"}]},
        ]
    }
    tests = {"factory/t.py": "def test_x():\n    # maps to: B1\n    pass\n"}
    v, w = guard.check_behavior_mapping(fm, tests, "impl")
    assert any(x.rule == "duplicate-behavior" for x in v)


def test_duplicate_behavior_ids_rejected_even_without_tests():
    # maps to: B4
    fm = {"acceptance": [{"behaviors": [{"id": "B1"}, {"id": "B1"}]}]}
    v, w = guard.check_behavior_mapping(fm, {}, "impl")
    assert any(x.rule == "duplicate-behavior" for x in v)


def test_check_staged_full_checks_each_impl_ticket(monkeypatch):
    # maps to: B4
    impl1 = (
        '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n'
        "scope_files: [factory/t_test.py]\n"
        "acceptance:\n  - story: s\n    behaviors:\n      - { id: B1, behavior: b, outcome: success }\n"
        "---\nbody\n"
    )
    impl2 = (
        '---\nid: impl-02\nstatus: open\ncycle: 0\nlast_verdict: ""\n'
        "scope_files: [factory/t_test.py]\n"
        "acceptance:\n  - story: s\n    behaviors:\n      - { id: B2, behavior: b, outcome: success }\n"
        "---\nbody\n"
    )
    test_src = "def test_x():\n    # maps to: B1\n    pass\n"
    contents = {
        ".scratch/sf/impl/01-a.md": impl1,
        ".scratch/sf/impl/02-b.md": impl2,
        "factory/t_test.py": test_src,
    }
    monkeypatch.setattr(guard, "_head_text", lambda p: "")
    monkeypatch.setattr(guard, "_index_text", lambda p: contents[p])
    paths = [".scratch/sf/impl/01-a.md", ".scratch/sf/impl/02-b.md", "factory/t_test.py"]
    v, w = guard.check_staged_full(paths)
    # impl-01's B1 is mapped; impl-02's B2 is NOT -> untested-behavior for impl-02.
    assert any(x.rule == "untested-behavior" and x.path == ".scratch/sf/impl/02-b.md" for x in v)
