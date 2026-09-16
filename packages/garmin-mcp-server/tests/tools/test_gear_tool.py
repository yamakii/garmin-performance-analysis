"""Tests for the get_gear_wear tool (Issue #1209)."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool


def _insert(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    gear_model: str,
    gear_nickname: str | None,
    gear_uuid: str,
    gear_max_km: float | None,
    gear_status: str | None = "active",
    gear_since_date: str | None = None,
    gear_retired_date: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, total_distance_km,
            gear_type, gear_model, gear_nickname, gear_uuid,
            gear_max_km, gear_status, gear_since_date, gear_retired_date
        ) VALUES (?, ?, ?, 'Shoes', ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            activity_date,
            distance_km,
            gear_model,
            gear_nickname,
            gear_uuid,
            gear_max_km,
            gear_status,
            gear_since_date,
            gear_retired_date,
        ],
    )


@pytest.fixture
def gear_db(reader_db_path: Path) -> Path:
    """Two active shoes sharing a model name, plus one retired pair."""
    conn = duckdb.connect(str(reader_db_path))
    _insert(
        conn,
        1,
        "2026-01-10",
        300.0,
        "NB 1080",
        "v14",
        "u-v14",
        643.7,
        gear_since_date="2025-12-26",
    )
    _insert(
        conn,
        2,
        "2026-09-06",
        252.5,
        "NB 1080",
        "v14",
        "u-v14",
        643.7,
        gear_since_date="2025-12-26",
    )
    _insert(
        conn,
        3,
        "2026-09-08",
        37.6,
        "NB 1080",
        "v15",
        "u-v15",
        650.0,
        gear_since_date="2026-09-08",
    )
    _insert(
        conn,
        4,
        "2025-11-17",
        687.9,
        "skechers",
        None,
        "u-sk",
        643.7,
        gear_status="retired",
        gear_since_date="2022-11-11",
        gear_retired_date="2025-12-26",
    )
    conn.close()
    return reader_db_path


def _call(db_path: Path, **args: object) -> dict[str, Any]:
    reader = MagicMock()
    reader.db_path = str(db_path)
    result = dispatch_tool(reader, "get_gear_wear", args)
    data: dict[str, Any] = json.loads(result[0].text)
    return data


@pytest.mark.unit
def test_get_gear_wear_registered() -> None:
    assert "get_gear_wear" in ALL_DEFS_BY_NAME


@pytest.mark.integration
def test_get_gear_wear_excludes_retired_by_default(gear_db: Path) -> None:
    data = _call(gear_db, as_of="2026-09-16")

    assert data["success"] is True
    assert [g["gear_label"] for g in data["gear"]] == [
        "NB 1080 (v14)",
        "NB 1080 (v15)",
    ]


@pytest.mark.integration
def test_get_gear_wear_includes_retired_when_asked(gear_db: Path) -> None:
    data = _call(gear_db, include_retired=True, as_of="2026-09-16")

    assert len(data["gear"]) == 3


@pytest.mark.integration
def test_get_gear_wear_orders_by_wear_desc(gear_db: Path) -> None:
    data = _call(gear_db, include_retired=True, as_of="2026-09-16")

    assert [g["wear_pct"] for g in data["gear"]] == [106.9, 85.8, 5.8]


@pytest.mark.integration
def test_get_gear_wear_flags_replacement(gear_db: Path) -> None:
    """The worn pair is called out by label so the caller need not re-scan."""
    data = _call(gear_db, as_of="2026-09-16")

    assert data["replace_recommended"] == ["NB 1080 (v14)"]
    assert data["gear"][0]["wear_status"] == "due_soon"
    assert data["gear"][0]["replace_recommended"] is True
    assert data["gear"][1]["replace_recommended"] is False


@pytest.mark.integration
def test_get_gear_wear_separates_generations_of_one_model(gear_db: Path) -> None:
    """The v15 keeps its own mileage despite sharing gear_model with the v14."""
    data = _call(gear_db, as_of="2026-09-16")

    by_label = {g["gear_label"]: g for g in data["gear"]}
    assert by_label["NB 1080 (v15)"]["km"] == 37.6
    assert by_label["NB 1080 (v14)"]["km"] == 552.5


@pytest.mark.integration
def test_get_gear_wear_empty_without_gear(reader_db_path: Path) -> None:
    conn = duckdb.connect(str(reader_db_path))
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (1, '2026-09-10')"
    )
    conn.close()

    data = _call(reader_db_path)

    assert data["success"] is True
    assert data["gear"] == []
    assert data["replace_recommended"] == []
