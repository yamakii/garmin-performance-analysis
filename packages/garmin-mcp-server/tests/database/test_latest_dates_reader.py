"""Integration tests for GarminDBReader latest-ingest-date readers (#460).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture),
inserts rows directly into the relevant table, then asserts the reader returns
the MAX date as a ``YYYY-MM-DD`` string (or ``None`` for an empty table). No
real data or Garmin access.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_activity(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    total_distance_km: float | None = 5.0,
) -> None:
    """Insert one activities row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, total_distance_km) "
            "VALUES (?, ?, ?)",
            [activity_id, activity_date, total_distance_km],
        )
    finally:
        conn.close()


def _insert_weight(
    db_path: Path, *, measurement_id: int, date: str, weight_kg: float = 75.0
) -> None:
    """Insert one body_composition row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO body_composition (measurement_id, date, weight_kg) "
            "VALUES (?, ?, ?)",
            [measurement_id, date, weight_kg],
        )
    finally:
        conn.close()


def _insert_strength(db_path: Path, *, activity_id: int, activity_date: str) -> None:
    """Insert one strength_sessions row (minimal columns)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO strength_sessions (activity_id, activity_date) "
            "VALUES (?, ?)",
            [activity_id, activity_date],
        )
    finally:
        conn.close()


def _insert_wellness(db_path: Path, *, wellness_id: int, date: str) -> None:
    """Insert one daily_wellness row (minimal columns)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO daily_wellness (wellness_id, date) VALUES (?, ?)",
            [wellness_id, date],
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# get_latest_activity_date
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_latest_activity_date_returns_max(reader_db_path: Path) -> None:
    """Two distance rows -> the later date; a NULL-distance row is ignored."""
    _insert_activity(reader_db_path, activity_id=1, activity_date="2026-06-10")
    _insert_activity(reader_db_path, activity_id=2, activity_date="2026-06-12")
    # A later but distance-less row must not become the latest cursor.
    _insert_activity(
        reader_db_path,
        activity_id=3,
        activity_date="2026-06-20",
        total_distance_km=None,
    )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_latest_activity_date()

    assert result == "2026-06-12"
    assert isinstance(result, str)


@pytest.mark.integration
def test_latest_activity_date_empty_returns_none(reader_db_path: Path) -> None:
    """Empty activities table -> None."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    assert reader.get_latest_activity_date() is None


# ---------------------------------------------------------------------------
# get_latest_weight_date
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_latest_weight_date_returns_max(reader_db_path: Path) -> None:
    """Two body_composition days -> the later date (str)."""
    _insert_weight(reader_db_path, measurement_id=1, date="2026-06-05")
    _insert_weight(reader_db_path, measurement_id=2, date="2026-06-09")

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_latest_weight_date()

    assert result == "2026-06-09"
    assert isinstance(result, str)


@pytest.mark.integration
def test_latest_weight_date_empty_returns_none(reader_db_path: Path) -> None:
    """Empty body_composition table -> None."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    assert reader.get_latest_weight_date() is None


# ---------------------------------------------------------------------------
# get_latest_strength_date
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_latest_strength_date_returns_max(reader_db_path: Path) -> None:
    """Two strength_sessions days -> the later date (str)."""
    _insert_strength(reader_db_path, activity_id=101, activity_date="2026-06-03")
    _insert_strength(reader_db_path, activity_id=102, activity_date="2026-06-11")

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_latest_strength_date()

    assert result == "2026-06-11"
    assert isinstance(result, str)


@pytest.mark.integration
def test_latest_strength_date_empty_returns_none(reader_db_path: Path) -> None:
    """Empty strength_sessions table -> None."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    assert reader.get_latest_strength_date() is None


# ---------------------------------------------------------------------------
# get_latest_wellness_date (issue #508)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_latest_wellness_date_returns_max(reader_db_path: Path) -> None:
    """Two daily_wellness days -> the later date (str)."""
    _insert_wellness(reader_db_path, wellness_id=1, date="2026-06-01")
    _insert_wellness(reader_db_path, wellness_id=2, date="2026-06-20")

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_latest_wellness_date()

    assert result == "2026-06-20"
    assert isinstance(result, str)


@pytest.mark.unit
def test_get_latest_wellness_date_empty_returns_none(reader_db_path: Path) -> None:
    """Empty daily_wellness table -> None."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    assert reader.get_latest_wellness_date() is None
