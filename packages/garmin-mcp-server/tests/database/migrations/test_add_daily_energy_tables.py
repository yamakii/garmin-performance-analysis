"""Tests for the daily_energy + intake_confirmations migration (Issue #1433)."""

from __future__ import annotations

import duckdb
import pytest

from garmin_mcp.database.migrations.add_daily_energy_tables import (
    add_daily_energy_tables,
)
from garmin_mcp.database.migrations.registry import MIGRATIONS

_ENERGY_COLUMNS = [
    "date",
    "consumed_kcal",
    "includes_consumed",
    "total_kcal",
    "active_kcal",
    "bmr_kcal",
    "coverage_seconds",
    "awake_seconds",
    "asleep_seconds",
    "total_steps",
    "fetched_at",
    "first_fetched_at",
    "post_close_revisions",
    "consumed_changed_at",
]
_CONFIRMATION_COLUMNS = ["user_id", "date", "status", "note", "confirmed_at"]


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


@pytest.mark.unit
def test_add_daily_energy_tables_idempotent() -> None:
    """Running the migration twice leaves both tables well-formed, no error."""
    conn = duckdb.connect(":memory:")
    try:
        add_daily_energy_tables(conn)
        add_daily_energy_tables(conn)

        assert _columns(conn, "daily_energy") == _ENERGY_COLUMNS
        assert _columns(conn, "intake_confirmations") == _CONFIRMATION_COLUMNS

        conn.execute(
            "INSERT INTO intake_confirmations (date, status) "
            "VALUES ('2026-09-22', 'complete')"
        )
        row = conn.execute("SELECT user_id FROM intake_confirmations").fetchone()
        assert row == ("default",)
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_version_34() -> None:
    """The energy tables are registered as migration 34, the schema head."""
    assert (34, "add_daily_energy_tables") in [
        (version, name) for version, name, _ in MIGRATIONS
    ]
    assert max(version for version, _, _ in MIGRATIONS) == 34
