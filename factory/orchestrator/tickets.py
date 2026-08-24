"""Impl-ticket parsing, dependency topo-sort, and escalation `## Answer` parsing.

The orchestrator reads its backlog from `.scratch/<effort>/impl/NN-<slug>.md` files
authored by the `factory-to-tickets` skill (04 schema, all keys up front). This module
parses the YAML frontmatter into :class:`ImplTicket`, topo-sorts by `depends_on`,
computes ready units against a set of done ids, and parses an escalation ticket's
`## Answer` section for verbatim re-injection (06 Q3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import guard


class CycleError(Exception):
    """Raised when impl tickets contain a dependency cycle."""


class MissingDependencyError(Exception):
    """Raised when an impl ticket depends on an id that is not in the backlog."""


@dataclass(frozen=True)
class ImplTicket:
    id: str
    title: str
    scope_files: list[str]
    model: str
    depends_on: list[str]
    status: str
    cycle: int
    last_verdict: str
    body: str
    path: str
    decision: str = ""
    acceptance: list[dict[str, object]] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            out.append({str(k): v for k, v in item.items()})
    return out


def parse_impl_file(path: str) -> ImplTicket:
    text = Path(path).read_text()
    fm, body = guard.split_frontmatter(text)
    if fm is None:
        raise ValueError(f"{path}: no frontmatter block")
    return ImplTicket(
        id=str(fm.get("id", "")),
        title=str(fm.get("title", "")),
        scope_files=_as_list(fm.get("scope_files")),
        model=str(fm.get("model", "")),
        depends_on=_as_list(fm.get("depends_on")),
        status=str(fm.get("status", "open")),
        cycle=int(str(fm.get("cycle", 0))),
        last_verdict=str(fm.get("last_verdict", "")),
        body=body,
        path=path,
        decision=str(fm.get("decision", "")),
        acceptance=_as_dict_list(fm.get("acceptance")),
        verify=_as_list(fm.get("verify")),
    )


def parse_impl_files(paths: Iterable[str]) -> list[ImplTicket]:
    return [parse_impl_file(p) for p in paths]


def topo_sort(units: Sequence[ImplTicket]) -> list[ImplTicket]:
    """Kahn topo-sort; preserves input order among equal-priority units.

    Raises :class:`MissingDependencyError` if a `depends_on` id is unknown, and
    :class:`CycleError` if a cycle exists.
    """
    by_id = {u.id: u for u in units}
    for u in units:
        for dep in u.depends_on:
            if dep not in by_id:
                raise MissingDependencyError(f"{u.id} depends on unknown unit {dep!r}")

    # indegree = number of unsatisfied deps; queue in input order (stable).
    order: list[ImplTicket] = []
    remaining: list[ImplTicket] = list(units)
    placed: set[str] = set()
    while remaining:
        ready = [u for u in remaining if all(d in placed for d in u.depends_on)]
        if not ready:
            raise CycleError(
                "dependency cycle among: " + ", ".join(sorted(u.id for u in remaining))
            )
        for u in ready:
            order.append(u)
            placed.add(u.id)
            remaining.remove(u)
    return order


def ready_units(units: Sequence[ImplTicket], done_ids: set[str]) -> list[ImplTicket]:
    """Units whose every dependency is in ``done_ids`` (and not themselves done)."""
    return [u for u in units if u.id not in done_ids and all(d in done_ids for d in u.depends_on)]


# ---- escalation ticket `## Answer` parsing (06 Q3) ----

_ANSWER_RE = re.compile(r"^##\s+Answer\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
_STATUS_RE = re.compile(r"^Status:\s*(\S+)", re.MULTILINE)


def parse_answer(path: str) -> str | None:
    text = Path(path).read_text()
    m = _ANSWER_RE.search(text)
    if m is None:
        return None
    return m.group(1).strip()


def is_resolved(path: str) -> bool:
    text = Path(path).read_text()
    m = _STATUS_RE.search(text)
    if m is None:
        return False
    return m.group(1).strip().lower() == "resolved"


def write_frontmatter_value(path: str, **values: object) -> None:
    """Mutate ONLY values of the mutable keys in an impl ticket's frontmatter.

    Re-serializes the frontmatter with the full key set preserved and the prose body
    unchanged, so the guard util sees a strictly value-only change. Only the keys
    passed in ``values`` change; everything else is carried through verbatim from the
    parsed dict (so key ordering / non-mutable values stay as-authored).
    """
    text = Path(path).read_text()
    fm, body = guard.split_frontmatter(text)
    if fm is None:
        raise ValueError(f"{path}: no frontmatter to mutate")
    mutable = {"status", "cycle", "last_verdict"}
    for k, v in values.items():
        if k not in mutable:
            raise ValueError(f"{path}: refusing to mutate non-mutable key {k!r}")
        fm[k] = v
    head = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True)
    Path(path).write_text(f"---\n{head}---\n{body}")
