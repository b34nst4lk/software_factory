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
    stepwise migrations).
    """
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
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


def query_cycles(db_path: str, **filters: object) -> list[dict[str, object]]:
    """Return cycle_log rows matching the given column filters (e.g. ``unit_id=...``).

    With no filters, returns every row. Rows are ordered by ``cycle_no``.
    """
    conn = sqlite3.connect(db_path)
    try:
        where = " AND ".join(f"{k} = ?" for k in filters)
        sql = f"SELECT {', '.join(_COLUMNS)} FROM cycle_log"
        if where:
            sql += " WHERE " + where
        sql += " ORDER BY cycle_no"
        rows = conn.execute(sql, tuple(filters.values())).fetchall()
        return [dict(zip(_COLUMNS, r, strict=True)) for r in rows]
    finally:
        conn.close()
