"""Migration: add ``run_id`` to section_analyses and backfill existing runs.

Issue #776. ``section_analyses`` is append-only, but a "version" was previously
inferred from ``created_at`` — and one analysis run inserts its 5 sections in
separate transactions, so each got a distinct sub-second-apart timestamp. The
version selector therefore counted a single run as 5 versions ("全5版").

This introduces an explicit ``run_id``: one analysis run = one run_id, shared by
every section written in that run. Grouping/versioning keys on run_id, so a run
is exactly one version regardless of per-section insert timing.

Backfill is exact, not heuristic: at migration time every activity has exactly
one analysis run (re-analysis had not happened), so each activity's rows are
assigned a single unique run_id. The ``seq_analysis_run_id`` sequence is then
created starting above the highest backfilled run_id, so future runs never
collide with legacy ones.

Idempotent: adding the column, the backfill (guarded on ``run_id IS NULL``) and
``CREATE SEQUENCE IF NOT EXISTS`` are all safe to re-run.
"""

import duckdb


def add_section_analysis_run_id(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``run_id``, backfill one run_id per existing activity, create the seq.

    Args:
        conn: Open DuckDB connection.
    """
    columns = [
        row[1] for row in conn.execute("PRAGMA table_info(section_analyses)").fetchall()
    ]
    if "run_id" not in columns:
        conn.execute("ALTER TABLE section_analyses ADD COLUMN run_id BIGINT")

    # Backfill: each existing activity is exactly one run today, so assign one
    # unique run_id per activity (deterministic order: earliest row first).
    conn.execute("""
        UPDATE section_analyses AS s
        SET run_id = m.rid
        FROM (
            SELECT activity_id,
                   ROW_NUMBER() OVER (ORDER BY MIN(created_at), activity_id) AS rid
            FROM section_analyses
            GROUP BY activity_id
        ) AS m
        WHERE s.activity_id = m.activity_id AND s.run_id IS NULL
        """)

    # Create the run_id sequence above every existing run_id. No-op if present;
    # on a fresh (empty) DB MAX is 0 so it starts at 1.
    max_row = conn.execute(
        "SELECT COALESCE(MAX(run_id), 0) FROM section_analyses"
    ).fetchone()
    assert max_row is not None
    max_run = max_row[0]
    conn.execute(
        f"CREATE SEQUENCE IF NOT EXISTS seq_analysis_run_id START {max_run + 1}"
    )
