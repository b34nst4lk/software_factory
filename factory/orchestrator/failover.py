"""Model failover / quota-exhaustion handling (06 Q5).

Distinguish a **model-call failure** (herdr error / exit 1 / pane not responding —
model unreachable) from a **verifier BLOCKED** (model ran, flagged ambiguity — that
is the escalate path, not this one). Transient failures retry with exponential
backoff (5s -> 15s -> 45s); on persistent / quota exhaustion (Ollama quota is shared
across all models, so swapping is pointless) the **whole orchestrator pauses** and a
stdin gate ``(r)etry / (q)uit`` decides: ``r`` probes the quota (one attempt, resume
on success, re-pause on failure); ``q`` gives up. The orchestrator logs this to
``run.log``.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_BACKOFF = (5, 15, 45)
DEFAULT_MAX_RETRIES = 3

SleepFn = Callable[[int], None]
AttemptFn = Callable[[], bool]
PauseFn = Callable[[int], str]  # given attempts so far, return 'r' or 'q'


class FailoverOutcome(enum.Enum):
    SUCCESS = "success"
    PAUSED_QUIT = "paused_quit"


@dataclass(frozen=True)
class FailoverResult:
    outcome: FailoverOutcome
    attempts: int


def retry(
    fn: AttemptFn,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff: tuple[int, ...] = DEFAULT_BACKOFF,
    sleep: SleepFn,
    on_exhausted: PauseFn,
) -> FailoverResult:
    """Retry ``fn`` (returns True on success) with exponential backoff.

    ``max_retries`` is the number of retries after the first attempt (initial +
    retries = ``max_retries + 1`` total attempts before the first pause). Backoff
    delays are applied before each retry. On exhaustion, ``on_exhausted`` is the
    whole-orchestrator pause stdin gate returning ``"r"`` (probe & resume) or
    ``"q"`` (quit).
    """
    attempts = 0
    while True:
        attempts += 1
        if fn():
            return FailoverResult(FailoverOutcome.SUCCESS, attempts)
        if attempts <= max_retries:
            sleep(backoff[(attempts - 1) % len(backoff)])
            continue
        # exhausted initial + retries -> pause the whole orchestrator
        decision = on_exhausted(attempts)
        if decision == "q":
            return FailoverResult(FailoverOutcome.PAUSED_QUIT, attempts)
        # "r": probe once (no backoff sleep), then re-pause if it still fails.
        continue
