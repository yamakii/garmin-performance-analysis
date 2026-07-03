"""Integration test for the surviving ``get_current_fitness_summary`` tool (#787).

Self-authored plan-creation tools were removed; this guards that the kept
fitness-summary tool still dispatches through the registry and returns the
expected assessment shape, with ``FitnessAssessor`` sourced from ``fitness/``.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter
from tests.handlers.conftest import dispatch_tool


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp_path: Path = tmp_path_factory.mktemp("db_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


@pytest.mark.integration
def test_get_current_fitness_summary_still_works(initialized_db_path: Path) -> None:
    """Fixture DB with recent activity + VO2max returns a fitness assessment."""
    recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    with get_write_connection(str(initialized_db_path)) as conn:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [9001, recent, 10.0, 3600, 360.0],
        )
        conn.execute(
            "INSERT INTO vo2_max (activity_id, precise_value) VALUES (?, ?)",
            [9001, 52.5],
        )

    reader = GarminDBReader(db_path=str(initialized_db_path))
    result = dispatch_tool(reader, "get_current_fitness_summary", {})
    data = json.loads(result[0].text)

    assert "error" not in data
    assert data["vdot"] > 0
    assert data["pace_zones"] is not None
    assert data["weekly_volume_km"] == pytest.approx(1.2)  # 10km / 8 weeks
