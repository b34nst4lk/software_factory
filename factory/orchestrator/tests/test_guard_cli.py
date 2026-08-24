"""End-to-end guard CLI test against a real (throwaway) git repo.

This is the unit test behind the Husky acceptance: a commit that adds a frontmatter
key OR deletes a run.log line must be REJECTED, value-only changes accepted. The
Husky pre-commit hook shells out to this same ``guard.main``.
"""

from __future__ import annotations

import subprocess

import guard

IMPL = '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n---\n' "Implement greet.\n"


def git(*args: str, cwd: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def init_repo(tmp_path) -> str:
    d = str(tmp_path)
    git("init", "-q", cwd=d)
    git("config", "user.email", "pi@local", cwd=d)
    git("config", "user.name", "pi", cwd=d)
    impl_dir = f"{d}/.scratch/sf/impl"
    import os

    os.makedirs(impl_dir, exist_ok=True)
    with open(f"{impl_dir}/01-greet.md", "w") as fh:
        fh.write(IMPL)
    with open(f"{d}/run.log", "w") as fh:
        fh.write("boot\n")
    git("add", "-A", cwd=d)
    git("add", "-f", "run.log", cwd=d)
    git("commit", "-q", "-m", "init", cwd=d)
    return d


def test_value_only_change_is_accepted(tmp_path, monkeypatch):
    d = init_repo(tmp_path)
    monkeypatch.chdir(d)
    with open(".scratch/sf/impl/01-greet.md", "w") as fh:
        fh.write(
            "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: PASS\n---\n"
            "Implement greet.\n"
        )
    git("add", "-A", cwd=d)
    assert guard.main([]) == 0


def test_key_add_change_is_rejected(tmp_path, monkeypatch):
    d = init_repo(tmp_path)
    monkeypatch.chdir(d)
    with open(".scratch/sf/impl/01-greet.md", "w") as fh:
        fh.write(
            "---\nid: impl-01\nstatus: in_progress\ncycle: 1\nlast_verdict: PASS\n"
            "sneaky: newkey\n---\nImplement greet.\n"
        )
    git("add", "-A", cwd=d)
    assert guard.main([]) == 1


def test_body_edit_is_rejected(tmp_path, monkeypatch):
    d = init_repo(tmp_path)
    monkeypatch.chdir(d)
    with open(".scratch/sf/impl/01-greet.md", "w") as fh:
        fh.write(
            '---\nid: impl-01\nstatus: open\ncycle: 0\nlast_verdict: ""\n---\n'
            "Implement greet DIFFERENTLY.\n"
        )
    git("add", "-A", cwd=d)
    assert guard.main([]) == 1


def test_run_log_is_rejected_as_non_governed(tmp_path, monkeypatch):
    # maps to: a staged run.log is rejected as a non-governed path (no longer special-cased)
    d = init_repo(tmp_path)
    monkeypatch.chdir(d)
    with open("run.log", "a") as fh:
        fh.write("appended line\n")
    git("add", "-f", "run.log", cwd=d)
    assert guard.main([]) == 1
