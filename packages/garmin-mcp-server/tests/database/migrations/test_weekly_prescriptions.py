"""Tests for migrations v24 / v25 on weekly_prescriptions.

Verifies that applying v24 creates the prescription table with the ``status``
default, that v25 adds the nullable ``rating`` column (the coach verdict moved
out of the review prose, Issue #1021), and that re-applying either is a no-op.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_prescription_rating import (
    add_prescription_rating,
)
from garmin_mcp.database.migrations.add_weekly_prescriptions_table import (
    add_weekly_prescriptions_table,
)


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {row[0] for row in rows}


@pytest.mark.unit
def test_add_weekly_prescriptions_table_creates_table(tmp_path: Path) -> None:
    """v24 creates weekly_prescriptions; status defaults to 'prescribed'."""
    conn = duckdb.connect(str(tmp_path / "prescriptions.duckdb"))
    try:
        add_weekly_prescriptions_table(conn)
        # Idempotent: a second application must not raise.
        add_weekly_prescriptions_table(conn)

        assert "weekly_prescriptions" in _table_names(conn)
        sequences = {
            row[0]
            for row in conn.execute(
                "SELECT sequence_name FROM duckdb_sequences()"
            ).fetchall()
        }
        assert {
            "seq_weekly_prescriptions_id",
            "seq_weekly_prescription_batches",
        }.issubset(sequences)

        conn.execute(
            "INSERT INTO weekly_prescriptions "
            "(prescription_id, batch_id, user_id, week_start_date, date, "
            "session_type, title) VALUES "
            "(nextval('seq_weekly_prescriptions_id'), "
            "nextval('seq_weekly_prescription_batches'), 'default', "
            "DATE '2026-09-07', DATE '2026-09-13', 'long', 'ロング 25km')"
        )
        row = conn.execute(
            "SELECT status, target_km, updated_at FROM weekly_prescriptions"
        ).fetchone()
        assert row is not None
        assert row[0] == "prescribed"
        assert row[1] is None
        assert row[2] is None
    finally:
        conn.close()


@pytest.mark.unit
def test_add_prescription_rating_idempotent(tmp_path: Path) -> None:
    """v25 adds a single nullable rating column and re-applying is a no-op."""
    conn = duckdb.connect(str(tmp_path / "rating.duckdb"))
    try:
        add_weekly_prescriptions_table(conn)
        add_prescription_rating(conn)
        # Idempotent: a second application must not raise.
        add_prescription_rating(conn)

        columns = [
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'weekly_prescriptions' AND column_name = 'rating'"
            ).fetchall()
        ]
        assert columns == ["rating"]

        conn.execute(
            "INSERT INTO weekly_prescriptions "
            "(prescription_id, batch_id, user_id, week_start_date, date, "
            "session_type, title, rating) VALUES "
            "(nextval('seq_weekly_prescriptions_id'), "
            "nextval('seq_weekly_prescription_batches'), 'default', "
            "DATE '2026-09-07', DATE '2026-09-13', 'long', 'ロング 25km', '✅')"
        )
        row = conn.execute("SELECT rating FROM weekly_prescriptions").fetchone()
        assert row is not None
        assert row[0] == "✅"
    finally:
        conn.close()


@pytest.mark.unit
def test_add_prescription_rating_without_table_is_noop(tmp_path: Path) -> None:
    """v25 on a DB without weekly_prescriptions does nothing (no crash)."""
    conn = duckdb.connect(str(tmp_path / "no_table.duckdb"))
    try:
        add_prescription_rating(conn)
        assert "weekly_prescriptions" not in _table_names(conn)
    finally:
        conn.close()


@pytest.mark.unit
def test_add_registered_bookend_minutes_idempotent(tmp_path: Path) -> None:
    """v26 adds one nullable column and re-applying is a no-op (#1087)."""
    from garmin_mcp.database.migrations.add_prescription_registered_bookend_minutes import (  # noqa: E501
        add_prescription_registered_bookend_minutes,
    )

    conn = duckdb.connect(str(tmp_path / "bookends.duckdb"))
    try:
        add_weekly_prescriptions_table(conn)
        add_prescription_registered_bookend_minutes(conn)
        # Idempotent: a second application must not raise.
        add_prescription_registered_bookend_minutes(conn)

        columns = [
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'weekly_prescriptions' "
                "AND column_name = 'registered_bookend_minutes'"
            ).fetchall()
        ]
        assert columns == ["registered_bookend_minutes"]

        conn.execute(
            "INSERT INTO weekly_prescriptions "
            "(prescription_id, batch_id, user_id, week_start_date, date, "
            "session_type, title, registered_bookend_minutes) VALUES "
            "(nextval('seq_weekly_prescriptions_id'), "
            "nextval('seq_weekly_prescription_batches'), 'default', "
            "DATE '2026-09-07', DATE '2026-09-09', 'tempo', "
            "'5kmビルドアップ', 20)"
        )
        row = conn.execute(
            "SELECT registered_bookend_minutes FROM weekly_prescriptions"
        ).fetchone()
        assert row is not None
        assert row[0] == 20
    finally:
        conn.close()


@pytest.mark.unit
def test_add_registered_bookend_minutes_without_table_is_noop(tmp_path: Path) -> None:
    """v26 on a DB without weekly_prescriptions does nothing (no crash)."""
    from garmin_mcp.database.migrations.add_prescription_registered_bookend_minutes import (  # noqa: E501
        add_prescription_registered_bookend_minutes,
    )

    conn = duckdb.connect(str(tmp_path / "no_table_bookends.duckdb"))
    try:
        add_prescription_registered_bookend_minutes(conn)
        assert "weekly_prescriptions" not in _table_names(conn)
    finally:
        conn.close()
