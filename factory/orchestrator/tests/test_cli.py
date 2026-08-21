"""Tests for cli.py — output live-buffering + arg wiring."""

from __future__ import annotations

import cli


class _FakeStream:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def reconfigure(self, **kw: object) -> None:
        self.calls.append(dict(kw))


def test_configure_live_output_sets_line_buffering():
    out, err = _FakeStream(), _FakeStream()
    cli.configure_live_output(stdout=out, stderr=err)
    assert out.calls == [{"line_buffering": True}]
    assert err.calls == [{"line_buffering": True}]


def test_configure_live_output_tolerates_streams_without_reconfigure():
    class NoReconf:  # e.g. a replaced stream
        pass

    # should not raise
    cli.configure_live_output(stdout=NoReconf(), stderr=NoReconf())  # type: ignore[arg-type]


def test_main_runs_mock_end_to_end_and_returns_zero(tmp_path, monkeypatch):
    # a fixture impl ticket the CLI will glob
    impl_dir = tmp_path / ".scratch" / "eff" / "impl"
    impl_dir.mkdir(parents=True)
    (impl_dir / "01-greet.md").write_text(
        "---\n"
        "id: impl-01\n"
        "title: greet\n"
        "scope_files: [factory/greet.py]\n"
        "model: d\n"
        "depends_on: []\n"
        "status: open\n"
        "cycle: 0\n"
        'last_verdict: ""\n'
        "verify: []\n"
        "---\n"
        "body\n"
    )
    # stdin is EOF in the test -> the human gate quits -> unit cancelled -> run returns
    monkeypatch.setattr("sys.stdin", _NoStdin())
    rc = cli.main(
        [
            "eff",
            "--repo",
            str(tmp_path),
            "--mock",
            "--pr-stage",
            "off",
            "--worktree-parent",
            str(tmp_path),
        ]
    )
    assert rc == 0


class _NoStdin:
    """A stdin that always EOFs (so the human gate quits, not hangs)."""

    def readline(self, *a, **k):
        raise EOFError

    def read(self, *a, **k):
        raise EOFError

    def flush(self):
        pass
