"""Tests for state.py — the per-repo SQLite narrative DB (decision 17).

One behaviour-driven test per acceptance bullet (annotated `# maps to: ...`), plus a
property/fuzz test that any (verdict, action) row round-trips through a query.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import state

VERDICTS = ["PASS", "FAIL", "BLOCKED", "UNPARSEABLE"]
ACTIONS = ["DONE", "RETRY", "ESCALATE", "HUMAN_GATE", "CAP_REACHED"]

# tmp_path is function-scoped and NOT reset between @given inputs, so give each
# generated input its own DB file to keep the round-trip assertion isolated.
_db_counter = iter(range(1_000_000))


def test_open_db_creates_table_idempotent(tmp_path):
    # maps to: state.open_db(path) creates <repo>/.factory/state.db with a cycle_log
    # table (CREATE TABLE IF NOT EXISTS); idempotent (calling twice does not error or
    # duplicate the table).
    db_path = str(tmp_path / ".factory" / "state.db")
    conn1 = state.open_db(db_path)
    conn1.close()
    assert Path(db_path).exists()
    # second open: no error, no duplicate table
    conn2 = state.open_db(db_path)
    tables = conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cycle_log'"
    ).fetchall()
    conn2.close()
    assert len(tables) == 1


def test_open_db_sets_wal_and_user_version(tmp_path):
    # maps to: state.open_db sets PRAGMA journal_mode=WAL and PRAGMA user_version
    # (for future stepwise migrations).
    db_path = str(tmp_path / "state.db")
    conn = state.open_db(db_path)
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert journal == "wal"
    assert version == 1


def test_log_cycle_writes_one_row_with_columns(tmp_path):
    # maps to: state.log_cycle writes one row with columns effort, unit_id, branch,
    # cycle_no, verdict, action, commit_sha, ts.
    db_path = str(tmp_path / "state.db")
    state.log_cycle(
        db_path,
        effort="software-factory",
        unit_id="impl-01",
        branch="impl-01",
        cycle_no=1,
        verdict="PASS",
        action="DONE",
        commit_sha="abc123",
        ts="2026-08-23T00:00:00",
    )
    rows = state.query_cycles(db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["effort"] == "software-factory"
    assert row["unit_id"] == "impl-01"
    assert row["branch"] == "impl-01"
    assert row["cycle_no"] == 1
    assert row["verdict"] == "PASS"
    assert row["action"] == "DONE"
    assert row["commit_sha"] == "abc123"
    assert row["ts"] == "2026-08-23T00:00:00"


def test_rows_for_multiple_efforts_units_cycles_coexist(tmp_path):
    # maps to: rows for multiple efforts/units/cycles coexist in the one DB and are
    # queryable (e.g. all cycles for a given unit; every unit across branches; a unit's
    # history across park/resume).
    db_path = str(tmp_path / "state.db")
    # two efforts, two units, multiple cycles, across branches (park/resume history)
    state.log_cycle(db_path, "sf", "impl-01", "impl-01", 1, "BLOCKED", "ESCALATE", "s1", "t1")
    state.log_cycle(db_path, "sf", "impl-01", "impl-01", 2, "PASS", "DONE", "s2", "t2")
    state.log_cycle(db_path, "sf", "impl-02", "impl-02", 1, "FAIL", "RETRY", "s3", "t3")
    state.log_cycle(db_path, "other", "impl-01", "impl-01", 1, "PASS", "DONE", "s4", "t4")

    # all cycles for a given unit (across park/resume) within one effort
    unit_rows = state.query_cycles(db_path, effort="sf", unit_id="impl-01")
    assert [r["cycle_no"] for r in unit_rows] == [1, 2]
    assert [r["verdict"] for r in unit_rows] == ["BLOCKED", "PASS"]

    # every unit across branches
    assert {r["unit_id"] for r in state.query_cycles(db_path)} == {"impl-01", "impl-02"}

    # effort column distinguishes efforts
    sf_rows = state.query_cycles(db_path, effort="sf")
    assert len(sf_rows) == 3
    other_rows = state.query_cycles(db_path, effort="other")
    assert len(other_rows) == 1


def test_config_db_path_defaults(tmp_path):
    # maps to: config.db_path defaults to <repo>/.factory/state.db (resolved from the
    # existing config, not a hardcoded absolute path).
    import config

    c = config.default(str(tmp_path), "software-factory", "g")
    assert c.db_path == str(tmp_path / ".factory" / "state.db")


def test_factory_dir_gitignored():
    # maps to: .factory/ is gitignored wholesale (the DB is local runtime state, never
    # committed).
    repo_root = Path(__file__).resolve().parents[3]
    gitignore = (repo_root / ".gitignore").read_text()
    assert ".factory/" in gitignore


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    effort=st.text(min_size=1),
    unit_id=st.text(min_size=1),
    branch=st.text(min_size=1),
    cycle_no=st.integers(min_value=1, max_value=100),
    verdict=st.sampled_from(VERDICTS),
    action=st.sampled_from(ACTIONS),
    commit_sha=st.text(min_size=1),
)
def test_logged_row_round_trips_through_query(
    tmp_path, effort, unit_id, branch, cycle_no, verdict, action, commit_sha
):
    # maps to: for any verdict in {PASS,FAIL,BLOCKED,UNPARSEABLE} and action in
    # {DONE,RETRY,ESCALATE,HUMAN_GATE,CAP_REACHED}, a logged row round-trips through a
    # query (property/fuzz).
    db_path = str(tmp_path / f"db-{next(_db_counter)}")
    state.log_cycle(
        db_path, effort, unit_id, branch, cycle_no, verdict, action, commit_sha, ts="t"
    )
    rows = state.query_cycles(db_path, unit_id=unit_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["effort"] == effort
    assert row["unit_id"] == unit_id
    assert row["branch"] == branch
    assert row["cycle_no"] == cycle_no
    assert row["verdict"] == verdict
    assert row["action"] == action
    assert row["commit_sha"] == commit_sha
