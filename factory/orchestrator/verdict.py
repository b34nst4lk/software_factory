"""Verifier verdict — extract a fenced-YAML verdict block, parse it, and route it.

Contract (06 Q1, ticket 09):
  - The verifier ends every response with a fenced YAML verdict block: an ``overall``
    field plus a ``gates`` list where each gate has ``status`` ∈ {PASS, FAIL, BLOCKED}
    and either ``feedback`` (on FAIL) or ``escalation`` (on BLOCKED).
  - Routing:
      overall PASS    → DONE  (all-6-gates-green)
      overall FAIL    → RETRY (collect each FAIL gate's feedback → next implementer cycle)
      overall BLOCKED → ESCALATE (collect each BLOCKED gate's escalation → Wayfinder ticket)
  - Any single gate returning BLOCKED forces ``overall`` to BLOCKED, even if another
    gate FAILED (06 Q1: gate 2 is the dedicated contradictions gate, but ANY gate may
    return BLOCKED).
  - **Never-assume on parse failure**: a missing or unparseable block routes to a
    HUMAN_GATE (the orchestrator does not guess). The raw text is carried along so the
    human gate can surface it.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field

import yaml

# A fenced block whose info string is yaml/YAML (or empty), capturing its body.
_FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
# Also accept a bare ``` (no info string) fence if it parses as YAML.
_BARE_FENCE_RE = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


class Overall(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNPARSEABLE = "UNPARSEABLE"


class Action(enum.Enum):
    DONE = "done"
    RETRY = "retry"
    ESCALATE = "escalate"
    HUMAN_GATE = "human_gate"


@dataclass(frozen=True)
class Verdict:
    overall: Overall
    feedbacks: list[str] = field(default_factory=list)
    escalations: list[str] = field(default_factory=list)
    raw: str | None = None  # the verifier text, surfaced when unparseable


def extract_verdict_block(text: str) -> str | None:
    """Return the inner YAML text of the verdict fence, or None if absent."""
    m = _FENCE_RE.search(text)
    if m is not None:
        return m.group(1)
    m = _BARE_FENCE_RE.search(text)
    if m is not None:
        candidate = m.group(1)
        # Only treat a bare fence as a verdict if it looks like a verdict (has overall/gates).
        if "overall" in candidate:
            return candidate
    return None


def _gate_statuses(gates: list[dict[str, object]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for g in gates:
        if not isinstance(g, dict):
            continue
        gate = str(g.get("gate", "?"))
        status = str(g.get("status", "")).upper()
        out.append((gate, status))
    return out


def _route_data(data: object, raw: str | None) -> Verdict:
    if not isinstance(data, dict):
        return Verdict(Overall.UNPARSEABLE, raw=raw)

    gates = data.get("gates") or []
    statuses = _gate_statuses(gates if isinstance(gates, list) else [])

    feedbacks = [
        str(g.get("feedback", ""))
        for g in (gates if isinstance(gates, list) else [])
        if isinstance(g, dict) and str(g.get("status", "")).upper() == "FAIL"
    ]
    escalations = [
        str(g.get("escalation", ""))
        for g in (gates if isinstance(gates, list) else [])
        if isinstance(g, dict) and str(g.get("status", "")).upper() == "BLOCKED"
    ]

    if any(s == "BLOCKED" for _, s in statuses):
        overall = Overall.BLOCKED
    elif any(s == "FAIL" for _, s in statuses):
        overall = Overall.FAIL
    elif all(s == "PASS" for _, s in statuses) and statuses:
        overall = Overall.PASS
    else:
        declared = str(data.get("overall", "")).upper()
        if declared == "PASS":
            overall = Overall.PASS
        elif declared == "FAIL":
            overall = Overall.FAIL
        elif declared == "BLOCKED":
            overall = Overall.BLOCKED
        else:
            return Verdict(Overall.UNPARSEABLE, raw=raw)

    return Verdict(overall, feedbacks=feedbacks, escalations=escalations, raw=None)


def parse_verdict(text: str) -> Verdict:
    """Parse a verdict from a pane's text (fenced YAML block)."""
    block = extract_verdict_block(text)
    if block is None:
        return Verdict(Overall.UNPARSEABLE, raw=text)
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return Verdict(Overall.UNPARSEABLE, raw=text)
    return _route_data(data, raw=text)


def parse_verdict_yaml(yaml_text: str) -> Verdict:
    """Parse a verdict from a raw YAML file (no fence) the verifier wrote to disk.

    Tolerates a leading `````yaml`` fence if present (strips it) so the same file
    content works whether the verifier fenced it or not.
    """
    block = extract_verdict_block(yaml_text)
    if block is not None:
        yaml_text = block
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return Verdict(Overall.UNPARSEABLE, raw=yaml_text)
    return _route_data(data, raw=yaml_text)


def route(verdict_obj: Verdict) -> Action:
    return {
        Overall.PASS: Action.DONE,
        Overall.FAIL: Action.RETRY,
        Overall.BLOCKED: Action.ESCALATE,
        Overall.UNPARSEABLE: Action.HUMAN_GATE,
    }[verdict_obj.overall]


# A compact one-line routing trailer: `VERDICT overall=PASS|FAIL|BLOCKED`. The overall
# token may be surrounded by spaces around '=' and is case-insensitive. This is a pure
# text scan (decision 15) — it deliberately does NOT reuse the fenced-YAML extraction
# path. It reads only the LAST non-empty line, so a stray mid-text trailer does not count.
_TRAILER_RE = re.compile(r"^VERDICT\s+overall\s*=\s*(\S+)\s*$", re.IGNORECASE)


def parse_trailer(text: str) -> Overall | None:
    """Return the routing Overall from the last non-empty `VERDICT overall=X` line.

    Reads only the last non-empty line of ``text``. Returns the matching ``Overall``
    (PASS/FAIL/BLOCKED) when that line is a valid trailer, else ``None``. The overall
    token is case-insensitive and tolerates surrounding spaces around ``=`` and trailing
    whitespace. Pure text scan — no fenced-YAML extraction.
    """
    last = ""
    for line in text.splitlines():
        if line.strip():
            last = line
    m = _TRAILER_RE.match(last)
    if m is None:
        return None
    token = m.group(1).upper()
    try:
        return Overall[token]
    except KeyError:
        return None
