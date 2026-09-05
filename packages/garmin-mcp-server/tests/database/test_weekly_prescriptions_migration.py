"""Tests for migration v24 (add_weekly_prescriptions_table).

Verifies that applying v24 creates the prescription table with the
``status`` default and that re-applying it is a no-op.
"""

from pathlib import Path

import duckdb
import pytest

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
