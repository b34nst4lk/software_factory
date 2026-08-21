"""Tests for guard.py — the value-only frontmatter + append-only run.log guard util."""
from __future__ import annotations

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

BEFORE = (
    "---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: \"\"\n---\n"
    "Implement greet.\n"
)
VALUE_ONLY = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: FAIL\n---\n"
    "Implement greet.\n"
)
KEY_ADDED = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: FAIL\n"
    "extra_key: boom\n---\nImplement greet.\n"
)
KEY_REMOVED = (
    "---\nid: impl-01\nstatus: in_progress\ncycle: 1\n---\nImplement greet.\n"
)
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


# ---- run.log append-only ----

APPEND_ONLY_DIFF = (
    "@@ -1,1 +1,2 @@\n"
    " line one\n"
    "+line two\n"
)
DELETION_DIFF = (
    "@@ -1,2 +1,1 @@\n"
    " line one\n"
    "-line two\n"
)
ONLY_HUNK_HEADER_MINUS = (
    "@@ -1,1 +1,1 @@\n"
    " line one\n"
)


def test_run_log_has_deletions_false_for_append_only():
    assert guard.run_log_has_deletions(APPEND_ONLY_DIFF) is False


def test_run_log_has_deletions_false_when_only_hunk_header_minus():
    assert guard.run_log_has_deletions(ONLY_HUNK_HEADER_MINUS) is False


def test_run_log_has_deletions_true_for_a_removed_line():
    assert guard.run_log_has_deletions(DELETION_DIFF) is True


# ---- check_impl_file / check_run_log_diff ----

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


def test_check_run_log_diff_append_only_ok():
    v = guard.check_run_log_diff(APPEND_ONLY_DIFF, "run.log")
    assert v == []


def test_check_run_log_diff_deletion_rejected():
    v = guard.check_run_log_diff(DELETION_DIFF, "run.log")
    assert len(v) == 1
    assert v[0].rule == "append-only"