"""herdr subprocess wrapper (Pattern A verbs) + a deterministic `--mock` stub.

Pattern A (research/03): one workspace + split panes; per pane a pi agent bound to a
model via `--model`; `agent prompt --wait --until done|blocked`; `agent read
--source recent-unwrapped --lines N`; `pane report-metadata --token summary=...`
for the sidebar; `agent wait --until blocked` for escalation park.

The real :class:`Herdr` is a thin `subprocess` driver. :class:`MockHerdr` is a
deterministic stand-in so the cycle/PR loops are exercised in tests without live
herdr/panes. Both implement :class:`HerdrPort`.

The real wrapper takes an injectable ``runner`` (DI at the system boundary) so
tests assert argv construction without invoking the binary.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Protocol


class HerdrPort(Protocol):
    def workspace_create(self, cwd: str, label: str) -> str: ...
    def pane_split(self, pane_id: str, direction: str) -> str: ...
    def agent_start(self, name: str, pane_id: str, model: str) -> None: ...
    def agent_prompt(self, name: str, prompt: str, *, until: str, timeout_ms: int) -> None: ...
    def agent_read(self, name: str, lines: int) -> str: ...
    def agent_wait(self, name: str, *, until: str, timeout_ms: int) -> None: ...
    def report_metadata(self, pane_id: str, summary: str) -> None: ...


Runner = Callable[[list[str]], tuple[str, int]]


def _default_runner(argv: list[str]) -> tuple[str, int]:
    res = subprocess.run(argv, capture_output=True, text=True)
    return res.stdout, res.returncode


class Herdr:
    """Thin subprocess driver of the herdr CLI (Pattern A)."""

    def __init__(self, runner: Runner | None = None, herdr_bin: str = "herdr") -> None:
        self._run = runner or _default_runner
        self._bin = herdr_bin

    def _cmd(self, args: list[str]) -> tuple[str, int]:
        return self._run([self._bin, *args])

    def workspace_create(self, cwd: str, label: str) -> str:
        out, _ = self._cmd(["workspace", "create", "--cwd", cwd, "--label", label, "--no-focus"])
        data = json.loads(out)
        return str(data["result"]["root_pane"]["pane_id"])

    def pane_split(self, pane_id: str, direction: str) -> str:
        out, _ = self._cmd(["pane", "split", pane_id, "--direction", direction, "--no-focus"])
        data = json.loads(out)
        return str(data["result"]["pane"]["pane_id"])

    def agent_start(self, name: str, pane_id: str, model: str) -> None:
        self._cmd(
            ["agent", "start", name, "--kind", "pi", "--pane", pane_id, "--", "--model", model]
        )

    def agent_prompt(self, name: str, prompt: str, *, until: str, timeout_ms: int) -> None:
        self._cmd(
            [
                "agent",
                "prompt",
                name,
                prompt,
                "--wait",
                "--until",
                until,
                "--timeout",
                str(timeout_ms),
            ]
        )

    def agent_read(self, name: str, lines: int) -> str:
        out, _ = self._cmd(
            ["agent", "read", name, "--source", "recent-unwrapped", "--lines", str(lines)]
        )
        return out

    def agent_wait(self, name: str, *, until: str, timeout_ms: int) -> None:
        self._cmd(["agent", "wait", name, "--until", until, "--timeout", str(timeout_ms)])

    def report_metadata(self, pane_id: str, summary: str) -> None:
        self._cmd(["pane", "report-metadata", pane_id, "--token", f"summary={summary}"])


class MockHerdr:
    """Deterministic herdr stub. Feed canned reads; prompts/metadata are recorded."""

    def __init__(self) -> None:
        self._next_pane = 0
        self._reads: dict[str, list[str]] = {}
        self._started: dict[str, tuple[str, str]] = {}
        self.prompts: dict[str, list[str]] = {}
        self.metadata: list[tuple[str, str]] = []

    def _pane(self) -> str:
        self._next_pane += 1
        return f"p{self._next_pane}"

    def feed_read(self, name: str, output: str) -> None:
        self._reads.setdefault(name, []).append(output)

    def workspace_create(self, cwd: str, label: str) -> str:
        return self._pane()

    def pane_split(self, pane_id: str, direction: str) -> str:
        return self._pane()

    def agent_start(self, name: str, pane_id: str, model: str) -> None:
        self._started[name] = (pane_id, model)

    def agent_prompt(self, name: str, prompt: str, *, until: str, timeout_ms: int) -> None:
        self.prompts.setdefault(name, []).append(prompt)

    def agent_read(self, name: str, lines: int) -> str:
        queue = self._reads.setdefault(name, [])
        if not queue:
            return ""
        return queue.pop(0)

    def agent_wait(self, name: str, *, until: str, timeout_ms: int) -> None:
        return None

    def report_metadata(self, pane_id: str, summary: str) -> None:
        self.metadata.append((pane_id, summary))

    def pane_for(self, name: str) -> str:
        return self._started[name][0]


def make_herdr(*, mock: bool, **_kw: object) -> HerdrPort:
    return MockHerdr() if mock else Herdr()
