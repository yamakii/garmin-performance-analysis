"""Migration v38: ``form_baseline_history.dynamics_source`` (#1631)."""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.form_baseline_sensor import (
    add_form_baseline_dynamics_source,
)

# The table as it was before v38: no dynamics_source, the old UNIQUE key.
_OLD_DDL = """
    CREATE TABLE form_baseline_history (
        history_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        condition_group VARCHAR DEFAULT 'flat_road',
        metric VARCHAR,
        model_type VARCHAR,
        coef_alpha FLOAT,
        coef_d FLOAT,
        coef_a FLOAT,
        coef_b FLOAT,
        power_a FLOAT,
        power_b FLOAT,
        power_rmse FLOAT,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        n_samples INTEGER,
        rmse FLOAT,
        speed_range_min FLOAT,
        speed_range_max FLOAT,
        UNIQUE(user_id, condition_group, metric, period_start, period_end)
    )
"""


@pytest.mark.integration
def test_migration_adds_dynamics_source_and_keeps_rows(tmp_path: Path) -> None:
    """5 old rows survive as 'all'; a 'wrist' row then fits the same period."""
    conn = duckdb.connect(str(tmp_path / "old.duckdb"))
    try:
        conn.execute(_OLD_DDL)
        for index, metric in enumerate(("gct", "vo", "vr", "cadence", "power")):
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (history_id, metric, model_type, coef_a, coef_b,
                     period_start, period_end, n_samples)
                VALUES (?, ?, 'linear', 1.5, -0.25, '2026-09-01', '2026-10-31', 90)
                """,
                [index + 1, metric],
            )

        add_form_baseline_dynamics_source(conn)

        rows = conn.execute(
            "SELECT dynamics_source, metric, coef_a, n_samples "
            "FROM form_baseline_history ORDER BY history_id"
        ).fetchall()
        assert len(rows) == 5
        assert {row[0] for row in rows} == {"all"}
        assert [row[1] for row in rows] == ["gct", "vo", "vr", "cadence", "power"]
        assert rows[0][2] == pytest.approx(1.5)
        assert rows[0][3] == 90

        # The same window now holds a per-sensor row next to the legacy one.
        conn.execute("""
            INSERT INTO form_baseline_history
                (history_id, dynamics_source, metric, model_type, coef_a, coef_b,
                 period_start, period_end, n_samples)
            VALUES (6, 'wrist', 'gct', 'linear', 2.0, -0.5,
                    '2026-09-01', '2026-10-31', 70)
            """)
        count = conn.execute("SELECT COUNT(*) FROM form_baseline_history").fetchone()
        assert count is not None and count[0] == 6

        # ... but the key still rejects a duplicate within one sensor.
        with pytest.raises(duckdb.ConstraintException):
            conn.execute("""
                INSERT INTO form_baseline_history
                    (history_id, dynamics_source, metric, model_type,
                     period_start, period_end)
                VALUES (7, 'wrist', 'gct', 'linear', '2026-09-01', '2026-10-31')
                """)

        # No backup table is left behind.
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert "form_baseline_history_backup_sensor" not in tables
    finally:
        conn.close()


@pytest.mark.integration
def test_migration_is_idempotent_and_skips_missing_table(tmp_path: Path) -> None:
    """A database without the table, or already migrated, is left alone."""
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    try:
        add_form_baseline_dynamics_source(conn)  # no table: no-op

        conn.execute(_OLD_DDL)
        add_form_baseline_dynamics_source(conn)
        add_form_baseline_dynamics_source(conn)  # second run: no-op

        columns = [
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'form_baseline_history'"
            ).fetchall()
        ]
        assert columns.count("dynamics_source") == 1
    finally:
        conn.close()
