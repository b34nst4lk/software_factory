"""Per-repo SQLite narrative DB — one row per cycle across all units/branches.

Decision 17 (git-as-state durability): the narrative moves from a tracked, per-worktree
``run.log`` (which conflicts on cross-branch merges and is lost with the worktree) to a
single per-repo SQLite DB at ``<repo>/.factory/state.db``, queryable across all
efforts/units/branches. This module owns the DB: :func:`open_db` (idempotent, WAL,
user_version) and :func:`log_cycle` (one row per cycle). No migration framework — just a
``user_version`` for future stepwise migrations.

Stdlib ``sqlite3`` only — no new dependency.
"""

from __future__ import annotations

import os
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cycle_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    effort TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    cycle_no INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    action TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    ts TEXT NOT NULL
)
"""

_COLUMNS = [
    "effort",
    "unit_id",
    "branch",
    "cycle_no",
    "verdict",
    "action",
    "commit_sha",
    "ts",
]


def open_db(db_path: str) -> sqlite3.Connection:
    """Open (creating if needed) the per-repo narrative DB.

    Idempotent: ``CREATE TABLE IF NOT EXISTS`` — calling twice does not error or
    duplicate the table. Sets ``journal_mode=WAL`` and ``user_version`` (for future
    stepwise migrations). Safe under concurrent access: a busy timeout lets a reader
    wait on a writer instead of raising ``database is locked``.
    """
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_SCHEMA)
    # Only switch to WAL if it is not already WAL (re-setting it re-acquires a lock).
    mode = conn.execute("PRAGMA journal_mode").fetchone()
    if not mode or str(mode[0]).lower() != "wal":
        conn.execute("PRAGMA journal_mode=WAL")
    # Never downgrade user_version: a future migration that raised it must stay raised.
    ver = conn.execute("PRAGMA user_version").fetchone()
    if not ver or ver[0] < 1:
        conn.execute("PRAGMA user_version = 1")
    conn.commit()
    return conn


def log_cycle(
    db_path: str,
    effort: str,
    unit_id: str,
    branch: str,
    cycle_no: int,
    verdict: str,
    action: str,
    commit_sha: str,
    ts: str,
) -> None:
    """Write one narrative row for a cycle."""
    conn = open_db(db_path)
    try:
        conn.execute(
            "INSERT INTO cycle_log (effort, unit_id, branch, cycle_no, verdict, action,"
            " commit_sha, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts),
        )
        conn.commit()
    finally:
        conn.close()


_SQL_ALL = (
    "SELECT effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts "
    "FROM cycle_log ORDER BY cycle_no"
)
_SQL_BY_EFFORT = (
    "SELECT effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts "
    "FROM cycle_log WHERE effort = ? ORDER BY cycle_no"
)
_SQL_BY_UNIT = (
    "SELECT effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts "
    "FROM cycle_log WHERE unit_id = ? ORDER BY cycle_no"
)
_SQL_BY_EFFORT_UNIT = (
    "SELECT effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts "
    "FROM cycle_log WHERE effort = ? AND unit_id = ? ORDER BY cycle_no"
)


def query_cycles(
    db_path: str, *, effort: str | None = None, unit_id: str | None = None
) -> list[dict[str, object]]:
    """Return cycle_log rows, optionally filtered by effort and/or unit_id.

    No dynamic SQL and no string concatenation: each query is one complete hardcoded
    literal selected by which filters are given; filter values are parameterized with
    ``?``. Injection is impossible by construction — no caller string ever reaches the
    SQL text, so there is no guard to remove. Rows are ordered by ``cycle_no``.
    """
    sql: str
    params: tuple[object, ...]
    if effort is not None and unit_id is not None:
        sql, params = _SQL_BY_EFFORT_UNIT, (effort, unit_id)
    elif effort is not None:
        sql, params = _SQL_BY_EFFORT, (effort,)
    elif unit_id is not None:
        sql, params = _SQL_BY_UNIT, (unit_id,)
    else:
        sql, params = _SQL_ALL, ()
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(zip(_COLUMNS, r, strict=True)) for r in rows]
    finally:
        conn.close()
