"""Escalation: author templated Wayfinder tickets, park units, file-driven resume,
verbatim answer re-injection (06 Q2, Q3).

No LLM here — the orchestrator authors the stub. The human + main-pi/wayfinder session
resolves it; the orchestrator re-scans parked units' tickets each loop iteration and
resumes when all open escalations flip to ``Status: resolved`` + ``## Answer``.
"""

from __future__ import annotations

import re

import tickets

_CANCEL_RE = re.compile(r"\bcancel(?:led)?\b", re.IGNORECASE)


def create_escalation_ticket(
    *,
    issues_dir: str,
    unit_id: str,
    unit_title: str,
    cycle: int,
    escalations: list[str],
    number: int,
) -> str:
    """Author a templated grilling ticket for a BLOCKED verdict.

    Returns the path of the written ticket. ``Status: open`` with an empty
    ``## Answer`` — the wayfinder session fills the answer.
    """
    import os

    slug = _slugify(unit_title)
    fname = f"{number:02d}-{slug}.md"
    path = os.path.join(issues_dir, fname)
    body = _template(unit_id, unit_title, cycle, escalations)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _template(unit_id: str, unit_title: str, cycle: int, escalations: list[str]) -> str:
    reasons = "\n".join(f"- {r}" for r in escalations) or "- (none)"
    return (
        f"# (auto) {unit_id} blocked at cycle {cycle}\n"
        "\n"
        f"Type: grilling\n"
        "Status: open\n"
        "\n"
        "## Question\n"
        "\n"
        f"Work unit **{unit_id}** (`{unit_title}`) hit a BLOCKED verdict at "
        f"cycle {cycle}. The verifier flagged ambiguity it will not assume:\n"
        "\n"
        f"{reasons}\n"
        "\n"
        "Resolve the ambiguity; the orchestrator will re-scan this ticket and "
        "re-inject the answer verbatim into the implementer and verifier prompts.\n"
        "\n"
        "## Answer\n"
        "\n"
        "<!-- filled by the wayfinder/human; on `Status: resolved` the orchestrator resumes -->\n"
    )


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "escalation"


def all_resolved(paths: list[str]) -> bool:
    """True when every escalation ticket is resolved (has a Status: resolved)."""
    if not paths:
        return False
    return all(tickets.is_resolved(p) for p in paths)


def resolutions_for(paths: list[str]) -> list[tuple[str, str]]:
    """Return ``(path, answer)`` for each resolved ticket, verbatim (06 Q3).

    Unresolved tickets are skipped. A unit resumes only when ALL its escalations
    resolve; this helper returns the resolved subset so the caller can assemble
    the injection block.
    """
    out: list[tuple[str, str]] = []
    for p in paths:
        if tickets.is_resolved(p):
            answer = tickets.parse_answer(p)
            if answer is not None:
                out.append((p, answer))
    return out


def is_cancellation(answer: str) -> bool:
    """A resolution that cancels the unit (06 Q3: 'this unit is cancelled')."""
    return bool(_CANCEL_RE.search(answer))


def resolution_block(ticket_path: str, answer: str) -> str:
    """Prepend block for re-injection into both prompts (verbatim)."""
    import os

    ticket_id = os.path.splitext(os.path.basename(ticket_path))[0]
    return f"Resolution (ticket {ticket_id}): {answer}\n\n"
