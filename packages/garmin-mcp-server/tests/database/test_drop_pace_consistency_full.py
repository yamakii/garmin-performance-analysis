"""Tests for the ``drop_pace_consistency_full`` migration (v22, issue #972).

Verifies that the migration removes the fragment-inclusive raw pace CV column
from ``performance_trends``, that it is idempotent (safe to re-apply and safe on
a DB that never had the column), and that it is registered as the current head
of ``MIGRATIONS``.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.drop_pace_consistency_full import (
    drop_pace_consistency_full,
)
from garmin_mcp.database.migrations.registry import (
    MIGRATIONS,
    _wrap_drop_pace_consistency_full,
)


def _columns(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute("PRAGMA table_info('performance_trends')").fetchall()
    return [row[1] for row in rows]


def _create_legacy_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create a performance_trends table that still has the dropped column."""
    conn.execute("""
        CREATE TABLE performance_trends (
            activity_id BIGINT PRIMARY KEY,
            pace_consistency DOUBLE,
            hr_drift_percentage DOUBLE,
            pace_consistency_full DOUBLE
        )
    """)


@pytest.mark.unit
def test_drop_pace_consistency_full_idempotent(tmp_path: Path) -> None:
    """The column is dropped on first run; a second run is a no-op."""
    db_path = tmp_path / "drop_pace_cv.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        _create_legacy_table(conn)
        conn.execute("INSERT INTO performance_trends VALUES (1, 0.014, 2.5, 0.0374)")
        assert "pace_consistency_full" in _columns(conn)

        drop_pace_consistency_full(conn)

        assert "pace_consistency_full" not in _columns(conn)
        assert "pace_consistency" in _columns(conn)

        # Second application must not raise.
        drop_pace_consistency_full(conn)

        assert "pace_consistency_full" not in _columns(conn)
        # Surviving rows keep the representative CV.
        assert conn.execute(
            "SELECT pace_consistency FROM performance_trends WHERE activity_id = 1"
        ).fetchone() == (0.014,)
    finally:
        conn.close()


@pytest.mark.unit
def test_drop_pace_consistency_full_no_table(tmp_path: Path) -> None:
    """Applying to a DB without performance_trends is a no-op (no exception)."""
    db_path = tmp_path / "drop_pace_cv_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        drop_pace_consistency_full(conn)
    finally:
        conn.close()


@pytest.mark.unit
def test_drop_pace_consistency_full_registered_as_v22() -> None:
    """drop_pace_consistency_full is registered at version 22 (current head)."""
    assert (
        22,
        "drop_pace_consistency_full",
        _wrap_drop_pace_consistency_full,
    ) in MIGRATIONS
    assert max(version for version, _, _ in MIGRATIONS) == 22
