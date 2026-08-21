"""Tests for failover.py — 3-retry backoff + whole-orchestrator pause gate."""

from __future__ import annotations

import failover


def make_attempt(seq: list[bool]):
    it = iter(seq)

    def fn() -> bool:
        return next(it)

    return fn


def test_success_on_first_try_no_sleep():
    sleeps: list[int] = []
    result = failover.retry(
        make_attempt([True]),
        max_retries=3,
        backoff=(5, 15, 45),
        sleep=lambda s: sleeps.append(s),
        on_exhausted=lambda a: "q",
    )
    assert result.outcome is failover.FailoverOutcome.SUCCESS
    assert result.attempts == 1
    assert sleeps == []


def test_success_on_last_retry_uses_full_backoff_sequence():
    sleeps: list[int] = []
    result = failover.retry(
        make_attempt([False, False, False, True]),
        max_retries=3,
        backoff=(5, 15, 45),
        sleep=lambda s: sleeps.append(s),
        on_exhausted=lambda a: "q",
    )
    assert result.outcome is failover.FailoverOutcome.SUCCESS
    assert result.attempts == 4
    assert sleeps == [5, 15, 45]


def test_fail_all_then_quit_pauses():
    sleeps: list[int] = []
    pauses: list[int] = []
    result = failover.retry(
        make_attempt([False, False, False, False]),
        max_retries=3,
        backoff=(5, 15, 45),
        sleep=lambda s: sleeps.append(s),
        on_exhausted=lambda a: pauses.append(a) or "q",
    )
    assert result.outcome is failover.FailoverOutcome.PAUSED_QUIT
    assert result.attempts == 4
    assert pauses == [4]
    assert sleeps == [5, 15, 45]


def test_fail_all_then_probe_r_succeeds():
    # 4 failures (initial+3 retries) -> pause; 'r' probe succeeds on attempt 5.
    sleeps: list[int] = []
    pauses: list[int] = []
    result = failover.retry(
        make_attempt([False, False, False, False, True]),
        max_retries=3,
        backoff=(5, 15, 45),
        sleep=lambda s: sleeps.append(s),
        on_exhausted=lambda a: pauses.append(a) or "r",
    )
    assert result.outcome is failover.FailoverOutcome.SUCCESS
    assert result.attempts == 5
    assert pauses == [4]
    assert sleeps == [5, 15, 45]  # no sleep before the probe


def test_fail_all_probe_fails_then_quit_re_pauses():
    pauses: list[int] = []
    decisions = iter(["r", "q"])
    result = failover.retry(
        make_attempt([False, False, False, False, False]),
        max_retries=3,
        backoff=(5, 15, 45),
        sleep=lambda s: None,
        on_exhausted=lambda a: pauses.append(a) or next(decisions),
    )
    assert result.outcome is failover.FailoverOutcome.PAUSED_QUIT
    assert pauses == [4, 5]
    assert result.attempts == 5
