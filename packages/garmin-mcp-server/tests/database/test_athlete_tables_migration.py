"""Integration tests for migration v7 (add_athlete_tables).

Verifies that applying the migration creates the four athlete-centric tables,
that the migration is idempotent, and that the weekly_reviews UNIQUE index on
(user_id, week_start_date) is enforced.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_athlete_tables import add_athlete_tables

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
def test_weekly_reviews_unique_week(tmp_path: Path) -> None:
    """Inserting the same (user_id, week_start_date) twice raises UNIQUE error."""
    db_path = tmp_path / "athlete_unique.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)

        conn.execute("""
            INSERT INTO weekly_reviews
                (review_id, user_id, week_start_date, week_end_date)
            VALUES
                (nextval('seq_weekly_reviews_id'), 'default',
                 DATE '2025-06-09', DATE '2025-06-15')
            """)

        with pytest.raises(duckdb.ConstraintException):
            conn.execute("""
                INSERT INTO weekly_reviews
                    (review_id, user_id, week_start_date, week_end_date)
                VALUES
                    (nextval('seq_weekly_reviews_id'), 'default',
                     DATE '2025-06-09', DATE '2025-06-15')
                """)
    finally:
        conn.close()
