"""Tests for form_evaluation gap detection and year-agnostic reevaluation.

Covers:
- garmin_mcp.scripts.regenerate.validator.find_missing_form_evaluations
- garmin_mcp.scripts.reevaluate_all_activities.get_activities_to_reevaluate
  (year filter generalization: activities outside 2021/2025 are now eligible)

Uses a real DuckDB schema (via GarminDBWriter) with direct row inserts so the
detection queries run against production column names. Each test uses unique
activity IDs to stay parallel-safe.
"""

import shutil
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.reevaluate_all_activities import (
    get_activities_to_reevaluate,
)
from garmin_mcp.scripts.regenerate.validator import find_missing_form_evaluations

# ---------------------------------------------------------------------------
# Schema fixtures (module-scoped template + function-scoped copy)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("form_eval_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "form_eval_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------


def _insert_activity(conn, activity_id: int, activity_date: str) -> None:
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
        (activity_id, activity_date),
    )


def _insert_split_with_form(conn, activity_id: int, split_index: int = 1) -> None:
    """Insert a split row that carries GCT/VO/VR form metrics."""
    conn.execute(
        """
        INSERT INTO splits (
            activity_id, split_index,
            ground_contact_time, vertical_oscillation, vertical_ratio
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (activity_id, split_index, 240.0, 7.5, 8.0),
    )


def _insert_split_without_form(conn, activity_id: int, split_index: int = 1) -> None:
    """Insert a split row with NULL form metrics (should not be detected)."""
    conn.execute(
        """
        INSERT INTO splits (
            activity_id, split_index,
            ground_contact_time, vertical_oscillation, vertical_ratio
        ) VALUES (?, ?, NULL, NULL, NULL)
        """,
        (activity_id, split_index),
    )


def _insert_form_evaluation(conn, eval_id: int, activity_id: int) -> None:
    conn.execute(
        "INSERT INTO form_evaluations (eval_id, activity_id) VALUES (?, ?)",
        (eval_id, activity_id),
    )


def _insert_covering_baseline(
    conn,
    history_id: int,
    period_start: str,
    period_end: str,
) -> None:
    """Insert a form_baseline_history row covering the given period."""
    conn.execute(
        """
        INSERT INTO form_baseline_history (
            history_id, user_id, condition_group, metric,
            period_start, period_end
        ) VALUES (?, 'default', 'flat_road', 'gct', ?, ?)
        """,
        (history_id, period_start, period_end),
    )


# ---------------------------------------------------------------------------
# get_activities_to_reevaluate: year filter generalization
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reevaluate_eligibility_includes_other_years(db_path: Path) -> None:
    """A 2026 activity with covering baseline + form splits is now eligible.

    The old query hardcoded 2021/2025 and would have excluded this activity.
    """
    activity_id = 90260001
    with get_write_connection(db_path) as conn:
        _insert_activity(conn, activity_id, "2026-03-15")
        _insert_split_with_form(conn, activity_id)
        _insert_covering_baseline(
            conn,
            history_id=92600001,
            period_start="2026-01-01",
            period_end="2026-12-31",
        )

    result = get_activities_to_reevaluate(str(db_path))
    ids = [aid for aid, _ in result]
    assert activity_id in ids


# ---------------------------------------------------------------------------
# find_missing_form_evaluations
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_find_missing_form_evaluations_detects_gap(db_path: Path) -> None:
    """Activity with form splits but no form_evaluations row is detected."""
    activity_id = 90260010
    with get_write_connection(db_path) as conn:
        _insert_activity(conn, activity_id, "2026-04-01")
        _insert_split_with_form(conn, activity_id)

    missing = find_missing_form_evaluations(None, db_path)
    ids = [aid for aid, _ in missing]
    assert activity_id in ids
    # activity_date is returned as a str
    for aid, date in missing:
        if aid == activity_id:
            assert isinstance(date, str)
            assert date == "2026-04-01"


@pytest.mark.integration
def test_find_missing_form_evaluations_excludes_complete(db_path: Path) -> None:
    """Activity with a form_evaluations row is not detected as missing."""
    activity_id = 90260020
    with get_write_connection(db_path) as conn:
        _insert_activity(conn, activity_id, "2026-04-02")
        _insert_split_with_form(conn, activity_id)
        _insert_form_evaluation(conn, eval_id=92600020, activity_id=activity_id)

    missing = find_missing_form_evaluations(None, db_path)
    ids = [aid for aid, _ in missing]
    assert activity_id not in ids


@pytest.mark.integration
def test_find_missing_form_evaluations_scoped_by_ids(db_path: Path) -> None:
    """activity_ids restricts detection to the given IDs only."""
    in_scope = 90260030
    out_of_scope = 90260031
    with get_write_connection(db_path) as conn:
        _insert_activity(conn, in_scope, "2026-04-03")
        _insert_split_with_form(conn, in_scope)
        _insert_activity(conn, out_of_scope, "2026-04-04")
        _insert_split_with_form(conn, out_of_scope)

    missing = find_missing_form_evaluations([in_scope], db_path)
    ids = [aid for aid, _ in missing]
    assert in_scope in ids
    assert out_of_scope not in ids


@pytest.mark.integration
def test_find_missing_form_evaluations_excludes_no_form_splits(
    db_path: Path,
) -> None:
    """Activity whose splits have NULL form metrics is not a false positive."""
    activity_id = 90260040
    with get_write_connection(db_path) as conn:
        _insert_activity(conn, activity_id, "2026-04-05")
        _insert_split_without_form(conn, activity_id)

    missing = find_missing_form_evaluations(None, db_path)
    ids = [aid for aid, _ in missing]
    assert activity_id not in ids
