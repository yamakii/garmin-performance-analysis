"""Migration: add ``dynamics_source`` to ``form_baseline_history`` (issue #1631).

The form expectation models used to be trained on splits from every dynamics
sensor (RD pod / chest strap / wrist) together. Sensors read GCT / VO / VR on
different scales, so a mixed model puts each sensor's deviations on a different
scale from period to period. The models are now trained and applied per
``activities.dynamics_source``.

DuckDB cannot alter a UNIQUE constraint, so the table is rebuilt with the CTAS
backup-and-recreate pattern from ``remove_fk_constraints.py``:
backup -> drop -> create (new UNIQUE key) -> restore -> verify -> cleanup.
Existing rows are kept as ``'all'`` (the legacy mixed-sensor models).
"""

import duckdb

BACKUP_TABLE = "form_baseline_history_backup_sensor"

CREATE_TABLE_DDL = """
    CREATE TABLE form_baseline_history (
        history_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        condition_group VARCHAR DEFAULT 'flat_road',
        dynamics_source VARCHAR NOT NULL DEFAULT 'all',
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

        UNIQUE(user_id, condition_group, dynamics_source, metric,
               period_start, period_end)
    )
"""


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    return [r[0] for r in rows]


def add_form_baseline_dynamics_source(conn: duckdb.DuckDBPyConnection) -> None:
    """Rebuild ``form_baseline_history`` with ``dynamics_source`` in the UNIQUE key.

    Idempotent: a missing table, or one that already has the column (fresh
    databases get it from ``_ensure_tables``), is left alone.
    """
    old_columns = _columns(conn, "form_baseline_history")
    if not old_columns or "dynamics_source" in old_columns:
        return

    conn.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")
    conn.execute(f"CREATE TABLE {BACKUP_TABLE} AS SELECT * FROM form_baseline_history")
    conn.execute("DROP TABLE form_baseline_history")
    conn.execute(CREATE_TABLE_DDL)

    new_columns = set(_columns(conn, "form_baseline_history"))
    common = [c for c in old_columns if c in new_columns]
    cols = ", ".join(common)
    conn.execute(
        f"INSERT INTO form_baseline_history ({cols}) "
        f"SELECT {cols} FROM {BACKUP_TABLE}"
    )

    old_count = conn.execute(f"SELECT COUNT(*) FROM {BACKUP_TABLE}").fetchone()
    new_count = conn.execute("SELECT COUNT(*) FROM form_baseline_history").fetchone()
    if old_count is None or new_count is None or old_count[0] != new_count[0]:
        raise AssertionError(
            "form_baseline_history row count changed during the dynamics_source "
            f"migration: backup={old_count}, new={new_count}"
        )

    conn.execute(f"DROP TABLE {BACKUP_TABLE}")
