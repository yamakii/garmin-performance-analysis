"""Integration tests: physiology reader output-shape snapshot + CLI smoke.

These run against the real DuckDB (fixture activity 20636804823) when available
and skip gracefully when the database or activity is missing, so CI without real
data stays green. They assert only key-sets and value *types* (not values).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from garmin_mcp.cli import app
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.physiology import PHYSIOLOGY_TOOLS_BY_NAME
from garmin_mcp.tools.registry import dispatch

FIXTURE_ACTIVITY_ID = 20636804823
FIXTURE_ACTIVITY_DATE = "2025-10-09"
_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "physiology_output_shape.json"
_ALL_DOMAINS_SNAPSHOT_PATH = (
    Path(__file__).parent / "snapshots" / "all_domains_output_shape.json"
)


def _resolve_real_db_path() -> Path | None:
    """Resolve the real DuckDB path independent of the test env isolation.

    The autouse ``isolate_data_dir`` fixture redirects ``GARMIN_DATA_DIR`` to a
    tmp dir, so we resolve via the original environment captured at import time,
    falling back to the conventional location. Returns None if no DB exists.
    """
    candidates: list[Path] = []
    data_dir = _ORIGINAL_DATA_DIR
    if data_dir:
        candidates.append(Path(data_dir) / "database" / "garmin_performance.duckdb")
    candidates.append(
        Path.home() / "garmin_data" / "data" / "database" / "garmin_performance.duckdb"
    )
    for c in candidates:
        if c.exists():
            return c
    return None


# Capture the real GARMIN_DATA_DIR before the autouse fixture rewrites it.
_ORIGINAL_DATA_DIR = os.environ.get("GARMIN_DATA_DIR")


def _shape(value: Any) -> Any:
    """Reduce a value to its structural shape (keys + type tokens, not values)."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return ["list", _shape(value[0])] if value else ["list"]
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "NoneType"
    return type(value).__name__


def _shapes_match(actual: Any, expected: Any) -> bool:
    """Compare two shape trees.

    Key-sets must match exactly. Type tokens must match, except that a
    ``NoneType`` on either side matches any type (nullable metrics are
    data-dependent and must not make the snapshot brittle).
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        if set(actual) != set(expected):
            return False
        return all(_shapes_match(actual[k], expected[k]) for k in expected)
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        # ["list"] (empty) or ["list", <elem shape>]
        if len(expected) != len(actual):
            return False
        return all(_shapes_match(a, e) for a, e in zip(actual, expected, strict=True))
    if expected == "NoneType" or actual == "NoneType":
        return True
    return bool(actual == expected)


@pytest.fixture(scope="module")
def real_reader() -> GarminDBReader:
    db_path = _resolve_real_db_path()
    if db_path is None:
        pytest.skip("Real DuckDB not available; skipping real-data integration test")
    reader = GarminDBReader(str(db_path))
    # Confirm the fixture activity exists; skip otherwise.
    probe = reader.get_hr_efficiency_analysis(FIXTURE_ACTIVITY_ID)
    if probe is None:
        pytest.skip(
            f"Fixture activity {FIXTURE_ACTIVITY_ID} not present in DB; skipping"
        )
    return reader


@pytest.mark.integration
def test_output_shape_snapshot_physiology(real_reader: GarminDBReader) -> None:
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))

    invocations: dict[str, dict[str, Any]] = {
        "get_form_efficiency_summary": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_form_evaluations": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_form_baseline_trend": {
            "activity_id": FIXTURE_ACTIVITY_ID,
            "activity_date": FIXTURE_ACTIVITY_DATE,
        },
        "get_hr_efficiency_analysis": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_heart_rate_zones_detail": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_vo2_max_data": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_lactate_threshold_data": {"activity_id": FIXTURE_ACTIVITY_ID},
    }

    assert set(invocations) == set(snapshot)

    for name, args in invocations.items():
        result = dispatch(PHYSIOLOGY_TOOLS_BY_NAME, real_reader, name, args)
        assert result is not None, f"{name} returned None"
        actual_shape = _shape(result)
        assert _shapes_match(
            actual_shape, snapshot[name]
        ), f"shape mismatch for {name}: {json.dumps(actual_shape, sort_keys=True)}"


@pytest.mark.integration
def test_cli_hr_efficiency_outputs_json(monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _resolve_real_db_path()
    if db_path is None:
        pytest.skip("Real DuckDB not available; skipping CLI integration test")

    # Point the CLI's get_db_path() at the real DB (env isolation rewrote it).
    monkeypatch.setenv(
        "GARMIN_DATA_DIR", str(db_path.parent.parent)
    )  # .../data/database -> .../data

    probe = GarminDBReader(str(db_path)).get_hr_efficiency_analysis(FIXTURE_ACTIVITY_ID)
    if probe is None:
        pytest.skip(
            f"Fixture activity {FIXTURE_ACTIVITY_ID} not present in DB; skipping"
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["physiology", "hr-efficiency", str(FIXTURE_ACTIVITY_ID), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "training_type" in payload
    assert payload["primary_zone"] == probe["primary_zone"]


@pytest.mark.integration
def test_cli_groups_cover_all_domains() -> None:
    """Every registry cli_group is registered and its --help exits cleanly."""
    runner = CliRunner()

    # Top-level help lists all groups and exits 0.
    top = runner.invoke(app, ["--help"])
    assert top.exit_code == 0, top.output

    expected_groups = {d.cli_group for d in ALL_DEFS}
    # All 14 domains must be present (12 prior + strength added in #450 +
    # ingest added in #463).
    assert expected_groups == {
        "export",
        "metadata",
        "splits",
        "analysis",
        "physiology",
        "performance",
        "time-series",
        "training-plan",
        "athlete",
        "race",
        "load",
        "durability",
        "strength",
        "ingest",
    }

    for group in sorted(expected_groups):
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0, f"{group} --help failed: {result.output}"


@pytest.mark.integration
def test_output_shape_snapshot_all(
    real_reader: GarminDBReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Activity-dependent tools across domains keep a stable output shape.

    Uses the fixture activity and skips gracefully when the DB/activity is
    missing (via the ``real_reader`` fixture). Asserts key-sets + value types,
    not values.

    Several of these tools construct their own analyzer (IntervalAnalyzer,
    FormAnomalyDetector, ...) that resolves the DB via ``get_db_path()`` rather
    than the passed reader, so point ``GARMIN_DATA_DIR`` at the real DB for the
    duration (the autouse isolation fixture otherwise rewrites it to a tmp dir).
    """
    db_path = _resolve_real_db_path()
    if db_path is None:
        pytest.skip("Real DuckDB not available; skipping all-domains snapshot test")
    monkeypatch.setenv("GARMIN_DATA_DIR", str(db_path.parent.parent))

    snapshot = json.loads(_ALL_DOMAINS_SNAPSHOT_PATH.read_text(encoding="utf-8"))

    invocations: dict[str, dict[str, object]] = {
        "get_splits_comprehensive": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_interval_analysis": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_performance_trends": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_weather_data": {"activity_id": FIXTURE_ACTIVITY_ID},
        "get_split_time_series_detail": {
            "activity_id": FIXTURE_ACTIVITY_ID,
            "split_number": 1,
        },
        "detect_form_anomalies_summary": {"activity_id": FIXTURE_ACTIVITY_ID},
    }

    assert set(invocations) == set(snapshot)

    for name, args in invocations.items():
        result = dispatch(ALL_DEFS_BY_NAME, real_reader, name, args)
        assert result is not None, f"{name} returned None"
        actual_shape = _shape(result)
        assert _shapes_match(
            actual_shape, snapshot[name]
        ), f"shape mismatch for {name}: {json.dumps(actual_shape, sort_keys=True)}"
