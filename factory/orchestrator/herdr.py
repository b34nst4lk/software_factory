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
    def pane_split(self, pane_id: str, direction: str, *, cwd: str | None = None) -> str: ...
    def agent_start(
        self, name: str, pane_id: str, model: str, *, approve: bool = False
    ) -> None: ...
    def agent_prompt(
        self, name: str, prompt: str, *, until: str | list[str], timeout_ms: int
    ) -> None: ...
    def agent_read(self, name: str, lines: int) -> str: ...
    def agent_wait(self, name: str, *, until: str, timeout_ms: int) -> None: ...
    def report_metadata(self, pane_id: str, summary: str) -> None: ...


Runner = Callable[[list[str]], tuple[str, int]]


def _extract_pane_id(data: object, *prefix: str) -> str:
    """Pull pane_id from a CLI JSON response, tolerating a `.result` wrapper or not."""
    node: object = data
    for key in prefix:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            node = data  # no wrapper; fall back to the root object
            break
    if isinstance(node, dict):
        if "pane_id" in node:
            return str(node["pane_id"])
        # root_pane / pane nested one more level
        for inner in ("root_pane", "pane"):
            if inner in node and isinstance(node.get(inner), dict):
                return str(node.get(inner, {}).get("pane_id", ""))
    raise RuntimeError(f"could not find pane_id in: {data!r}")


def _default_runner(argv: list[str]) -> tuple[str, int]:
    res = subprocess.run(argv, capture_output=True, text=True)
    return res.stdout, res.returncode


class Herdr:
    """Thin subprocess driver of the herdr CLI (Pattern A)."""

    def __init__(
        self,
        runner: Runner | None = None,
        herdr_bin: str = "herdr",
        session: str = "",
    ) -> None:
        self._run = runner or _default_runner
        self._bin = herdr_bin
        self._session = session

    def _cmd(self, args: list[str]) -> tuple[str, int]:
        prefix = [self._bin, "--session", self._session] if self._session else [self._bin]
        return self._run([*prefix, *args])

    def workspace_create(self, cwd: str, label: str) -> str:
        out, _ = self._cmd(["workspace", "create", "--cwd", cwd, "--label", label, "--no-focus"])
        return _extract_pane_id(json.loads(out), "result", "root_pane")

    def pane_split(self, pane_id: str, direction: str, *, cwd: str | None = None) -> str:
        args = ["pane", "split", pane_id, "--direction", direction, "--no-focus"]
        if cwd:
            args += ["--cwd", cwd]
        out, _ = self._cmd(args)
        return _extract_pane_id(json.loads(out), "result", "pane")

    def agent_start(self, name: str, pane_id: str, model: str, *, approve: bool = False) -> None:
        pi_args = ["--model", model]
        if approve:
            pi_args.append("--approve")
        self._cmd(["agent", "start", name, "--kind", "pi", "--pane", pane_id, "--", *pi_args])

    def agent_prompt(
        self, name: str, prompt: str, *, until: str | list[str], timeout_ms: int
    ) -> None:
        # `--until` matches the EXACT state(s); a finished turn may settle as `idle`
        # (seen) not just `done` (unseen), and a verifier may `blocked`. Match the full
        # terminal set so --wait returns the moment the worker's turn ends.
        states = [until] if isinstance(until, str) else list(until)
        args = ["agent", "prompt", name, prompt, "--wait", "--timeout", str(timeout_ms)]
        for s in states:
            args += ["--until", s]
        self._cmd(args)

    def agent_read(self, name: str, lines: int) -> str:
        out, _ = self._cmd(
            ["agent", "read", name, "--source", "recent-unwrapped", "--lines", str(lines)]
        )
        return out

    def agent_wait(self, name: str, *, until: str, timeout_ms: int) -> None:
        self._cmd(["agent", "wait", name, "--until", until, "--timeout", str(timeout_ms)])

    def report_metadata(self, pane_id: str, summary: str) -> None:
        # --source identifies the metadata writer; --token summary=... renders as $summary.
        self._cmd(
            [
                "pane",
                "report-metadata",
                pane_id,
                "--source",
                "orchestrator",
                "--token",
                f"summary={summary}",
            ]
        )


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

    def pane_split(self, pane_id: str, direction: str, *, cwd: str | None = None) -> str:
        return self._pane()

    def agent_start(self, name: str, pane_id: str, model: str, *, approve: bool = False) -> None:
        self._started[name] = (pane_id, model)

    def agent_prompt(
        self, name: str, prompt: str, *, until: str | list[str], timeout_ms: int
    ) -> None:
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


def make_herdr(*, mock: bool, session: str = "", **_kw: object) -> HerdrPort:
    return MockHerdr() if mock else Herdr(session=session)
