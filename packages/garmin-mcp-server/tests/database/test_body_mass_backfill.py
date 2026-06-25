"""Unit tests for ``backfill_body_mass`` (#528).

The re-runnable backfill sets ``activities.body_mass_kg`` to the nearest
``body_composition.weight_kg`` within ``+/- window_days`` of the activity date.

These tests seed a few known rows into ``activities`` and ``body_composition``
via direct SQL on a schema-initialized temp DB (``initialized_db_path``), then
assert the script picks the right weights / counts. They never touch the
production DB and use unique activity_ids so parallel runs stay deterministic.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.backfill_body_mass import backfill_body_mass


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with schema + migrations pre-initialized.

    ``GarminDBWriter.__init__`` runs ``_ensure_tables`` then ``_run_migrations``,
    so the ``body_mass_kg`` column (added by migration ``phase0_power_prep``) is
    present on this template.
    """
    tmp_path = tmp_path_factory.mktemp("body_mass_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB with schema pre-initialized via file copy."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


def _seed_activities(db_path: Path, rows: list[tuple[int, str]]) -> None:
    """Insert (activity_id, activity_date) rows into activities (body_mass NULL)."""
    conn = duckdb.connect(str(db_path))
    try:
        for activity_id, activity_date in rows:
            conn.execute(
                "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
                [activity_id, activity_date],
            )
    finally:
        conn.close()


def _seed_body_composition(db_path: Path, rows: list[tuple[str, float]]) -> None:
    """Insert (date, weight_kg) rows directly into body_composition."""
    conn = duckdb.connect(str(db_path))
    try:
        for i, (date, weight_kg) in enumerate(rows, start=1):
            conn.execute(
                "INSERT INTO body_composition (measurement_id, date, weight_kg) "
                "VALUES (?, ?, ?)",
                [i, date, weight_kg],
            )
    finally:
        conn.close()


def _get_body_mass(db_path: Path, activity_id: int) -> float | None:
    """Read back activities.body_mass_kg for an activity."""
    conn = duckdb.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT body_mass_kg FROM activities WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else row[0]


@pytest.mark.unit
def test_backfill_picks_nearest_within_window(initialized_db_path: Path) -> None:
    """Activity 2026-01-15 with measurements 01-10 (5d) and 01-13 (2d) → picks 01-13."""
    _seed_activities(initialized_db_path, [(900001, "2026-01-15")])
    _seed_body_composition(
        initialized_db_path,
        [
            ("2026-01-10", 70.0),  # 5 days before
            ("2026-01-13", 71.0),  # 2 days before  <- nearest
            ("2026-01-20", 72.0),  # 5 days after
        ],
    )

    result = backfill_body_mass(db_path=str(initialized_db_path), window_days=30)

    assert _get_body_mass(initialized_db_path, 900001) == 71.0
    assert result["total"] == 1
    assert result["populated"] == 1
    assert result["still_null"] == 0


@pytest.mark.unit
def test_backfill_skips_when_no_measurement_in_window(
    initialized_db_path: Path,
) -> None:
    """Only out-of-window measurements → body_mass_kg stays NULL, counted as still_null."""
    _seed_activities(initialized_db_path, [(900002, "2026-01-15")])
    # 40 / 60 days away — both outside the 30-day window.
    _seed_body_composition(
        initialized_db_path,
        [
            ("2025-12-06", 68.0),  # 40 days before
            ("2026-03-16", 69.0),  # 60 days after
        ],
    )

    result = backfill_body_mass(db_path=str(initialized_db_path), window_days=30)

    assert _get_body_mass(initialized_db_path, 900002) is None
    assert result["total"] == 1
    assert result["populated"] == 0
    assert result["still_null"] == 1


@pytest.mark.unit
def test_backfill_force_recomputes_existing(initialized_db_path: Path) -> None:
    """force=False leaves an existing value untouched; force=True recomputes it."""
    _seed_activities(initialized_db_path, [(900003, "2026-02-10")])
    _seed_body_composition(initialized_db_path, [("2026-02-12", 75.0)])

    # Pre-set an existing (stale) value to simulate the migration's leftover.
    conn = duckdb.connect(str(initialized_db_path))
    try:
        conn.execute(
            "UPDATE activities SET body_mass_kg = ? WHERE activity_id = ?",
            [99.0, 900003],
        )
    finally:
        conn.close()

    # force=False: row is not NULL, so it must be left as the stale value.
    no_force = backfill_body_mass(
        db_path=str(initialized_db_path), window_days=30, force=False
    )
    assert _get_body_mass(initialized_db_path, 900003) == 99.0
    assert no_force["populated"] == 1

    # force=True: recompute from body_composition (75.0, 2 days away).
    forced = backfill_body_mass(
        db_path=str(initialized_db_path), window_days=30, force=True
    )
    assert _get_body_mass(initialized_db_path, 900003) == 75.0
    assert forced["total"] == 1
    assert forced["populated"] == 1
    assert forced["still_null"] == 0


@pytest.mark.unit
def test_backfill_returns_counts(initialized_db_path: Path) -> None:
    """Mixed in/out-of-window activities → total/populated/still_null are consistent."""
    _seed_activities(
        initialized_db_path,
        [
            (900004, "2026-01-15"),  # in window → populated
            (900005, "2026-06-15"),  # no nearby measurement → still NULL
            (900006, "2026-03-01"),  # in window → populated
        ],
    )
    _seed_body_composition(
        initialized_db_path,
        [
            ("2026-01-14", 70.0),  # near 900004
            ("2026-02-28", 72.0),  # near 900006
        ],
    )

    result = backfill_body_mass(db_path=str(initialized_db_path), window_days=30)

    assert result["total"] == 3
    assert result["populated"] == 2
    assert result["still_null"] == 1
    # Counts must always partition the total.
    assert result["populated"] + result["still_null"] == result["total"]

    assert _get_body_mass(initialized_db_path, 900004) == 70.0
    assert _get_body_mass(initialized_db_path, 900006) == 72.0
    assert _get_body_mass(initialized_db_path, 900005) is None
