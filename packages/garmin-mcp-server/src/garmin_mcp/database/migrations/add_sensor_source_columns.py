"""Migration: Add sensor source columns (dynamics_source / hr_source) to activities.

Which external sensors a run used lives only in the raw ``activity.json`` ->
``metadataDTO.sensors`` list: the Running Dynamics Pod (``antplusDeviceType``
``RUN``) and the chest strap (``HEART_RATE`` over ANT+ or BLE). Without them in
the table, pod runs cannot be compared only with pod runs, and strap HR cannot
be told from optical HR.

Existing rows keep NULL until ``garmin_mcp.scripts.backfill_sensor_source`` (or
a re-ingest) fills them from the raw files.
"""

import duckdb

SENSOR_SOURCE_COLUMNS: list[tuple[str, str]] = [
    ("dynamics_source", "VARCHAR"),
    ("hr_source", "VARCHAR"),
]


def add_sensor_source_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Add dynamics_source / hr_source to activities (idempotent)."""
    for col_name, col_type in SENSOR_SOURCE_COLUMNS:
        conn.execute(
            f"ALTER TABLE activities ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )
