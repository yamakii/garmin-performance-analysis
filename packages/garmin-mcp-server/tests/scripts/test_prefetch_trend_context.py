"""Integration tests for the prefetch_trend_context bundler (Issue #790).

Uses a real DuckDB schema (via GarminDBWriter) with direct activity inserts so
the trend readers run against production column names. ``get_db_path`` is
patched to the seeded temp DB. Each test uses unique activity IDs to stay
parallel-safe.
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.prefetch_trend_context import prefetch_trend_context


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("prefetch_trend_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "prefetch_trend_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target


def _insert_activity(
    db_path: Path,
    activity_id: int,
    activity_date: str,
    total_distance_km: float = 8.0,
) -> None:
    with get_write_connection(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO activities (activity_id, activity_date, total_distance_km)
            VALUES (?, ?, ?)
            """,
            (activity_id, activity_date, total_distance_km),
        )


@pytest.mark.integration
def test_prefetch_returns_period_keys(db_path: Path) -> None:
    """The bundle exposes every required period-keyed field."""
    with patch(
        "garmin_mcp.scripts.prefetch_trend_context.get_db_path",
        return_value=db_path,
    ):
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    assert "error" not in result
    for key in (
        "period_start",
        "period_end",
        "granularity",
        "activity_ids",
        "headline_metrics",
        "fusion_flags",
    ):
        assert key in result

    assert result["period_start"] == "2026-06-15"
    assert result["period_end"] == "2026-06-21"
    assert result["granularity"] == "week"
    assert isinstance(result["activity_ids"], list)
    assert "fusion_flags" in result["headline_metrics"]


@pytest.mark.integration
def test_prefetch_resolves_activity_ids_in_range(db_path: Path) -> None:
    """An activity seeded inside the window is resolved into activity_ids."""
    in_range_id = 790000001
    out_of_range_id = 790000002
    _insert_activity(db_path, in_range_id, "2026-06-17")
    _insert_activity(db_path, out_of_range_id, "2026-05-01")

    with patch(
        "garmin_mcp.scripts.prefetch_trend_context.get_db_path",
        return_value=db_path,
    ):
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    assert in_range_id in result["activity_ids"]
    assert out_of_range_id not in result["activity_ids"]


@pytest.mark.integration
def test_prefetch_monthly_recovery_null_when_out_of_window(db_path: Path) -> None:
    """A month whose period_end predates the recovery window -> null + note."""
    with patch(
        "garmin_mcp.scripts.prefetch_trend_context.get_db_path",
        return_value=db_path,
    ):
        result = prefetch_trend_context("2024-01-01", "2024-01-31", "month")

    assert result["recovery_trend"] is None
    assert result["recovery_trend_note"]
