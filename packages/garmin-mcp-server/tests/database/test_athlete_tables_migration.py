"""Integration tests for migrations v7 (add_athlete_tables) and v8
(drop_weekly_review_index).

Verifies that applying v7 creates the four athlete-centric tables, that the
migration is idempotent, that weekly_reviews allows multiple versions per week
(no UNIQUE index), and that v8 drops the legacy unique index so same-week
INSERTs succeed.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_athlete_tables import add_athlete_tables
from garmin_mcp.database.migrations.drop_weekly_review_index import (
    drop_weekly_review_index,
)

ATHLETE_TABLES = {
    "athlete_profile",
    "athlete_goals",
    "season_retrospectives",
    "weekly_reviews",
}


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {row[0] for row in rows}


@pytest.mark.integration
def test_migration_creates_athlete_tables(tmp_path: Path) -> None:
    """After applying v7, all four athlete tables exist in information_schema."""
    db_path = tmp_path / "athlete.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        tables = _table_names(conn)
    finally:
        conn.close()

    assert ATHLETE_TABLES.issubset(tables), f"Missing tables: {ATHLETE_TABLES - tables}"


@pytest.mark.integration
def test_migration_idempotent(tmp_path: Path) -> None:
    """Applying the migration twice does not raise and tables still exist."""
    db_path = tmp_path / "athlete_idempotent.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        # Second application must be a no-op (no exception).
        add_athlete_tables(conn)
        tables = _table_names(conn)
    finally:
        conn.close()

    assert ATHLETE_TABLES.issubset(tables)


@pytest.mark.integration
def test_weekly_reviews_allow_multiple_versions_per_week(tmp_path: Path) -> None:
    """v7 no longer creates a unique index: same-week INSERTs append rows."""
    db_path = tmp_path / "athlete_versions.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)

        for _ in range(2):
            conn.execute("""
                INSERT INTO weekly_reviews
                    (review_id, user_id, week_start_date, week_end_date)
                VALUES
                    (nextval('seq_weekly_reviews_id'), 'default',
                     DATE '2025-06-09', DATE '2025-06-15')
                """)

        count = conn.execute(
            "SELECT COUNT(*) FROM weekly_reviews "
            "WHERE user_id = 'default' AND week_start_date = DATE '2025-06-09'"
        ).fetchone()[0]
        assert count == 2
    finally:
        conn.close()


@pytest.mark.integration
def test_migration_v8_drops_unique_index(tmp_path: Path) -> None:
    """After v8, idx_weekly_reviews_week is gone and same-week INSERTs succeed."""
    db_path = tmp_path / "athlete_v8.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        # Simulate a legacy database that still carries the unique index.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_reviews_week "
            "ON weekly_reviews(user_id, week_start_date)"
        )

        # Apply v8 (idempotent).
        drop_weekly_review_index(conn)
        drop_weekly_review_index(conn)

        index_rows = conn.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE index_name = 'idx_weekly_reviews_week'"
        ).fetchall()
        assert index_rows == []

        # Same-week INSERT now yields multiple rows (no unique constraint).
        for _ in range(2):
            conn.execute("""
                INSERT INTO weekly_reviews
                    (review_id, user_id, week_start_date, week_end_date)
                VALUES
                    (nextval('seq_weekly_reviews_id'), 'default',
                     DATE '2025-06-09', DATE '2025-06-15')
                """)

        count = conn.execute(
            "SELECT COUNT(*) FROM weekly_reviews "
            "WHERE user_id = 'default' AND week_start_date = DATE '2025-06-09'"
        ).fetchone()[0]
        assert count == 2
    finally:
        conn.close()
