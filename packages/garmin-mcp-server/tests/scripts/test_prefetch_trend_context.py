"""Integration tests for the prefetch_trend_context bundler (Issue #790).

Uses a real DuckDB schema (via GarminDBWriter) with direct activity inserts so
the trend readers run against production column names. ``get_db_path`` is
patched to the seeded temp DB. Each test uses unique activity IDs to stay
parallel-safe.
"""

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.prefetch_trend_context import prefetch_trend_context


@contextmanager
def _mock_prefetch(
    resolve_map: dict[tuple[str, str], list[int]],
) -> Iterator[tuple[MagicMock, MagicMock]]:
    """Patch the prefetch collaborators for granularity-branch unit tests.

    ``resolve_map`` maps ``(start, end)`` date bounds to the activity IDs
    ``_resolve_activity_ids`` should return for that window. The reader /
    analyzer methods return minimal valid shapes so the deterministic
    headline fold does not raise; individual tests override return values.
    """
    reader = MagicMock()
    reader.get_load_trend.return_value = {"weeks": []}
    reader.get_acwr.return_value = {}
    reader.get_recovery_trend.return_value = {}
    reader.get_durability_trend.return_value = {
        "activities": [],
        "trend": {"direction": "insufficient_data", "data_points": 0},
    }
    reader.get_heat_adjusted_trend.return_value = {"status": "insufficient_data"}
    reader.fitness_curve.get_objective_fitness_curve.return_value = {}

    analyzer = MagicMock()
    analyzer.analyze_metric_trend.return_value = {
        "metric": "pace",
        "trend": "stable",
        "slope": 0.0,
        "correlation": 0.0,
        "p_value": 1.0,
        "data_points": 0,
        "start_date": "",
        "end_date": "",
    }
    analyzer.summarize_metric_period.return_value = {
        "metric": "pace",
        "mode": "descriptive",
        "median": None,
        "prev_period_median": None,
        "delta_pct": None,
        "data_points": 0,
        "prev_data_points": 0,
    }

    def _resolve(_conn: object, start: str, end: str) -> list[int]:
        return list(resolve_map.get((start, end), []))

    with (
        patch(
            "garmin_mcp.scripts.prefetch_trend_context.get_db_path",
            return_value=Path("/tmp/prefetch_unit.duckdb"),
        ),
        patch("garmin_mcp.scripts.prefetch_trend_context.get_connection"),
        patch(
            "garmin_mcp.scripts.prefetch_trend_context._resolve_activity_ids",
            side_effect=_resolve,
        ),
        patch(
            "garmin_mcp.database.db_reader.GarminDBReader",
            return_value=reader,
        ),
        patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer",
            return_value=analyzer,
        ),
    ):
        yield reader, analyzer


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


# ── Issue #813: statistically-honest weekly windowing ────────────────────


@pytest.mark.unit
def test_weekly_metric_trends_descriptive_shape() -> None:
    """Weekly -> descriptive metric summary (no regression keys)."""
    resolve_map = {
        ("2026-06-15", "2026-06-21"): [1, 2, 3],  # current week
        ("2026-06-08", "2026-06-14"): [4, 5],  # previous week
    }
    with _mock_prefetch(resolve_map) as (_reader, analyzer):
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    pace = result["metric_trends"]["pace"]
    assert pace["mode"] == "descriptive"
    assert "slope" not in pace
    assert "p_value" not in pace
    assert "trend" not in pace
    # Descriptive path used, keyed on current + previous-week IDs.
    analyzer.summarize_metric_period.assert_any_call("pace", [1, 2, 3], [4, 5])
    analyzer.analyze_metric_trend.assert_not_called()


@pytest.mark.unit
def test_monthly_metric_trends_keeps_regression() -> None:
    """Monthly path is unchanged: keeps the in-period regression shape."""
    resolve_map = {("2026-06-01", "2026-06-30"): [1, 2, 3]}
    with _mock_prefetch(resolve_map) as (_reader, analyzer):
        result = prefetch_trend_context("2026-06-01", "2026-06-30", "month")

    pace = result["metric_trends"]["pace"]
    assert "slope" in pace
    assert "p_value" in pace
    analyzer.analyze_metric_trend.assert_any_call(
        "pace", "2026-06-01", "2026-06-30", [1, 2, 3]
    )
    analyzer.summarize_metric_period.assert_not_called()


@pytest.mark.unit
def test_weekly_durability_trailing_window() -> None:
    """Weekly durability fits over the trailing 8-week window + in-period IDs."""
    resolve_map = {("2026-06-15", "2026-06-21"): [10, 11]}
    with _mock_prefetch(resolve_map) as (reader, _analyzer):
        reader.get_durability_trend.return_value = {
            "activities": [
                {"activity_id": 10, "activity_date": "2026-06-18"},  # in period
                {"activity_id": 99, "activity_date": "2026-05-01"},  # trailing only
            ],
            "trend": {"direction": "stable", "data_points": 2},
        }
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    reader.get_durability_trend.assert_called_once_with("2026-04-27", "2026-06-21")
    dur = result["durability_trend"]
    assert dur["window"] == {"start": "2026-04-27", "end": "2026-06-21", "weeks": 8}
    assert dur["in_period_activity_ids"] == [10]


@pytest.mark.unit
def test_fitness_curve_window_fixed_90d() -> None:
    """Fitness curve is pinned to 90d for both week and month granularities."""
    for granularity, start, end in (
        ("week", "2026-06-15", "2026-06-21"),
        ("month", "2026-06-01", "2026-06-30"),
    ):
        with _mock_prefetch({(start, end): [1, 2, 3]}) as (reader, _analyzer):
            prefetch_trend_context(start, end, granularity)
        reader.fitness_curve.get_objective_fitness_curve.assert_called_once_with(
            window_days=90
        )


@pytest.mark.unit
def test_weekly_heat_trailing_fit_window() -> None:
    """Weekly heat hinge fits over the trailing 12-week window (period_end-83d)."""
    resolve_map = {
        ("2026-06-15", "2026-06-21"): [10, 11],  # current week
        ("2026-03-30", "2026-06-21"): [1, 2, 3, 10, 11],  # trailing 12 weeks
    }
    with _mock_prefetch(resolve_map) as (reader, _analyzer):
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    reader.get_heat_adjusted_trend.assert_called_once_with(
        [1, 2, 3, 10, 11], "2026-03-30", "2026-06-21"
    )
    assert result["heat_adjusted_trend"]["in_period_activity_ids"] == [10, 11]


@pytest.mark.integration
def test_prefetch_bundle_weekly_shapes(db_path: Path) -> None:
    """A seeded week -> json-serializable bundle with descriptive metric_trends."""
    for i, day in enumerate(range(15, 22)):  # 2026-06-15 .. 2026-06-21
        _insert_activity(db_path, 813000000 + i, f"2026-06-{day:02d}")

    with patch(
        "garmin_mcp.scripts.prefetch_trend_context.get_db_path",
        return_value=db_path,
    ):
        result = prefetch_trend_context("2026-06-15", "2026-06-21", "week")

    assert "error" not in result
    # Bundle stays json.dumps-able across the MCP boundary.
    json.dumps(result, default=str)

    for key in (
        "period_start",
        "period_end",
        "granularity",
        "activity_ids",
        "load_trend",
        "metric_trends",
        "fitness_curve",
        "recovery_trend",
        "recovery_trend_note",
        "durability_trend",
        "acwr",
        "heat_adjusted_trend",
        "headline_metrics",
        "fusion_flags",
    ):
        assert key in result

    pace = result["metric_trends"]["pace"]
    assert pace["mode"] == "descriptive"
    assert "slope" not in pace
    assert "prev_data_points" in pace
