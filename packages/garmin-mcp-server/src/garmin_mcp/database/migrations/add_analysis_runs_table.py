"""Migration: add the ``analysis_runs`` bookkeeping table + durable run_id repair.

Issue #819. Every live analysis run since migration 14 allocated the *same*
``run_id`` (113): a session that only executes ``nextval`` does not persist the
sequence advance on DuckDB (state is serialized only when the same session also
writes real data/catalog changes; an explicit ``CHECKPOINT`` does not help).
``GarminDBWriter.next_run_id()`` opened a dedicated short-lived connection, ran
``nextval('seq_analysis_run_id')`` alone and closed — so the advance evaporated
every time and the persisted sequence stayed at its migration-time ``START 113``.

The fix pairs allocation with a real INSERT into ``analysis_runs`` in the same
connection, which makes the advance durable and doubles as an auditable run log.
This migration:

1. Creates ``analysis_runs`` (``run_id`` PK, ``started_at``).
2. Repairs the conflated run 113 in place: its rows are split by ``created_at``
   into clusters (>1 min gap = a separate run, each cluster = 5 sections of one
   activity). The oldest cluster keeps 113; subsequent clusters get 114, 115, …
3. Backfills ``analysis_runs`` from the distinct ``run_id`` values already in
   ``section_analyses`` (using each run's earliest ``created_at``).
4. Recreates ``seq_analysis_run_id`` starting at ``max(run_id) + 1`` via plain
   ``DROP SEQUENCE`` + ``CREATE SEQUENCE`` DDL (which persists).

Idempotent: ``CREATE TABLE IF NOT EXISTS``, the repair (skipped when run 113 has
≤5 rows / a single cluster) and the guarded backfill are all safe to re-run.
"""

from datetime import timedelta

import duckdb


def add_analysis_runs_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create ``analysis_runs``, repair run 113, backfill, and bump the sequence.

    Args:
        conn: Open DuckDB connection.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id BIGINT PRIMARY KEY,
            started_at TIMESTAMP
        )
        """)

    _repair_conflated_run_113(conn)

    # Backfill one analysis_runs row per distinct run_id already present, keyed
    # on each run's earliest section timestamp. Guarded so re-runs are no-ops.
    conn.execute("""
        INSERT INTO analysis_runs (run_id, started_at)
        SELECT run_id, MIN(created_at)
        FROM section_analyses
        WHERE run_id IS NOT NULL
          AND run_id NOT IN (SELECT run_id FROM analysis_runs)
        GROUP BY run_id
        """)

    # Recreate the sequence above every existing run_id. Plain DDL persists
    # (unlike a lone nextval), so a fresh writer allocates the correct next id.
    max_row = conn.execute(
        "SELECT COALESCE(MAX(run_id), 0) FROM section_analyses"
    ).fetchone()
    assert max_row is not None
    max_run = max_row[0]
    conn.execute("DROP SEQUENCE IF EXISTS seq_analysis_run_id")
    conn.execute(f"CREATE SEQUENCE seq_analysis_run_id START {max_run + 1}")


def _repair_conflated_run_113(conn: duckdb.DuckDBPyConnection) -> None:
    """Split the conflated ``run_id = 113`` into per-run clusters (issue #819).

    Rows sharing run_id 113 are ordered by ``created_at`` and grouped into
    clusters separated by more than a one-minute gap (one cluster = the 5
    sections of a single analysis run). The oldest cluster keeps 113; each
    subsequent cluster is reassigned the next free run_id (114, 115, …).

    No-op (idempotent) when run 113 has ≤5 rows or resolves to a single cluster.
    """
    rows = conn.execute(
        "SELECT analysis_id, created_at FROM section_analyses "
        "WHERE run_id = 113 ORDER BY created_at, analysis_id"
    ).fetchall()
    if len(rows) <= 5:
        return  # already a single run's worth of sections (or nothing) — skip.

    clusters: list[list[int]] = []
    prev_ts = None
    for analysis_id, ts in rows:
        if prev_ts is None or (ts - prev_ts) > timedelta(minutes=1):
            clusters.append([])
        clusters[-1].append(analysis_id)
        prev_ts = ts

    if len(clusters) <= 1:
        return  # one cluster: not actually conflated — nothing to split.

    max_row = conn.execute(
        "SELECT COALESCE(MAX(run_id), 0) FROM section_analyses"
    ).fetchone()
    assert max_row is not None
    next_run = max_row[0] + 1
    # Oldest cluster (clusters[0]) keeps 113; reassign the rest in age order.
    for cluster in clusters[1:]:
        placeholders = ",".join("?" for _ in cluster)
        conn.execute(
            "UPDATE section_analyses SET run_id = ? "
            f"WHERE analysis_id IN ({placeholders})",
            [next_run, *cluster],
        )
        next_run += 1
