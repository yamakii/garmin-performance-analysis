"""Integration tests for the base_weight backfill script.

Uses a real DuckDB schema (via GarminDBWriter) with direct row inserts so the
UPDATE / SELECT statements run against production column names. Body composition
lookups and form re-evaluation are mocked so the tests exercise the script's
branching (update / skip / dry-run) without depending on cached weight files,
trained models, or the Garmin Connect API.

Each test uses unique activity IDs to stay parallel-safe.
"""

import shutil
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_connection, get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts import backfill_base_weight as bbw

# ---------------------------------------------------------------------------
# Schema fixtures (module-scoped template + function-scoped copy)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("backfill_bw_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "backfill_bw_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target


# ---------------------------------------------------------------------------
# Insert / read helpers
# ---------------------------------------------------------------------------


def _insert_activity(
    conn, activity_id: int, activity_date: str, base_weight_kg: float | None = None
) -> None:
    conn.execute(
        """
        INSERT INTO activities (activity_id, activity_date, base_weight_kg)
        VALUES (?, ?, ?)
        """,
        (activity_id, activity_date, base_weight_kg),
    )


def _get_base_weight(db_path: Path, activity_id: int) -> float | None:
    with get_connection(str(db_path)) as conn:
        row = conn.execute(
            "SELECT base_weight_kg FROM activities WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
    return None if row is None else row[0]


class _StubWorker:
    """Minimal worker stub with a configurable median lookup."""

    def __init__(self, weights_by_date: dict[str, float | None]):
        self._weights = weights_by_date

    def _calculate_median_weight(self, date: str):
        weight = self._weights.get(date)
        if weight is None:
            return None
        return {"weight_kg": weight}


@pytest.fixture
def patched_eval(monkeypatch):
    """Patch evaluate_and_store to a no-op that records calls."""
    calls: list[int] = []

    def _fake_eval(activity_id, activity_date, db_path, condition_group="flat_road"):
        calls.append(activity_id)
        return {"power": {"avg_w": 234.0}}

    monkeypatch.setattr(bbw, "evaluate_and_store", _fake_eval)
    return calls


def _patch_worker(monkeypatch, weights_by_date: dict[str, float | None]) -> None:
    """Force the script to use a stub cache-only worker."""
    monkeypatch.setattr(
        bbw,
        "_make_cache_only_worker",
        lambda db_path: _StubWorker(weights_by_date),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_backfill_updates_null_base_weight(db_path, monkeypatch, patched_eval) -> None:
    """A NULL base_weight activity with a resolvable median gets updated."""
    activity_id = 910001
    activity_date = "2025-10-09"
    with get_write_connection(str(db_path)) as conn:
        _insert_activity(conn, activity_id, activity_date, base_weight_kg=None)

    _patch_worker(monkeypatch, {activity_date: 62.5})

    result = bbw.backfill_base_weight(db_path=str(db_path), dry_run=False)

    assert result["updated"] >= 1
    assert result["skipped"] == 0
    assert result["reevaluated"] == 1
    assert patched_eval == [activity_id]
    assert _get_base_weight(db_path, activity_id) == pytest.approx(62.5)


@pytest.mark.integration
def test_backfill_dry_run_no_write(db_path, monkeypatch, patched_eval) -> None:
    """dry_run reports counts but leaves the DB untouched and skips re-eval."""
    activity_id = 910002
    activity_date = "2025-10-10"
    with get_write_connection(str(db_path)) as conn:
        _insert_activity(conn, activity_id, activity_date, base_weight_kg=None)

    _patch_worker(monkeypatch, {activity_date: 63.0})

    result = bbw.backfill_base_weight(db_path=str(db_path), dry_run=True)

    assert result["updated"] == 1
    assert result["reevaluated"] == 0
    assert patched_eval == []  # evaluate_and_store not called in dry-run
    assert _get_base_weight(db_path, activity_id) is None  # DB unchanged


@pytest.mark.integration
def test_backfill_skips_unresolvable(db_path, monkeypatch, patched_eval) -> None:
    """An activity with no body composition in the window is skipped, left NULL."""
    activity_id = 910003
    activity_date = "2025-10-11"
    with get_write_connection(str(db_path)) as conn:
        _insert_activity(conn, activity_id, activity_date, base_weight_kg=None)

    # No median available for this date.
    _patch_worker(monkeypatch, {activity_date: None})

    result = bbw.backfill_base_weight(db_path=str(db_path), dry_run=False)

    assert result["skipped"] == 1
    assert result["updated"] == 0
    assert result["reevaluated"] == 0
    assert patched_eval == []
    assert _get_base_weight(db_path, activity_id) is None
