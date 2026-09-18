"""Star scores read from float32 columns are rounded to one decimal (#1245).

``form_evaluations.gct_score`` / ``vo_score`` / ``vr_score`` / ``overall_score``
are ``FLOAT`` columns in the real schema, so a stored 4.1 comes back as
4.099999904632568. These tests use the real schema (not a hand-written DOUBLE
table) because the bug only exists with the float32 column type.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.form import FormReader

ACTIVITY_ID = 912450001
NULL_ACTIVITY_ID = 912450002


def _insert_row(
    db_path: Path,
    eval_id: int,
    activity_id: int,
    gct_score: float | None,
    vo_score: float | None,
    vr_score: float | None,
    overall_score: float | None,
) -> None:
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO form_evaluations (
            eval_id, activity_id,
            gct_ms_expected, vo_cm_expected, vr_pct_expected,
            gct_ms_actual, vo_cm_actual, vr_pct_actual,
            gct_delta_pct, vo_delta_cm, vr_delta_pct,
            gct_star_rating, gct_score, gct_needs_improvement,
            vo_star_rating, vo_score, vo_needs_improvement,
            vr_star_rating, vr_score, vr_needs_improvement,
            cadence_actual, cadence_minimum, cadence_achieved,
            overall_score, overall_star_rating,
            integrated_score, training_mode
        ) VALUES (
            ?, ?,
            257.3, 7.15, 9.11,
            259.7, 7.3, 9.22,
            0.93, 0.15, 1.23,
            '★★★★☆', ?, false,
            '★★★★★', ?, false,
            '★★★★★', ?, false,
            179.2, 180, false,
            ?, '★★★★☆',
            81.5, 'aerobic_base'
        )
        """,
        [eval_id, activity_id, gct_score, vo_score, vr_score, overall_score],
    )
    conn.close()


@pytest.mark.integration
def test_form_evaluations_scores_rounded_to_one_decimal(
    initialized_db_path: Path,
) -> None:
    _insert_row(initialized_db_path, 1, ACTIVITY_ID, 4.1, 4.7, 4.5, 4.4)

    result = FormReader(str(initialized_db_path)).get_form_evaluations(ACTIVITY_ID)

    assert result is not None
    # Exact equality on purpose: approx() would hide 4.099999904632568.
    assert result["gct"]["score"] == 4.1
    assert result["vo"]["score"] == 4.7
    assert result["vr"]["score"] == 4.5
    assert result["overall_score"] == 4.4


@pytest.mark.integration
def test_form_evaluations_null_scores_stay_none(initialized_db_path: Path) -> None:
    _insert_row(initialized_db_path, 2, NULL_ACTIVITY_ID, None, None, None, None)

    result = FormReader(str(initialized_db_path)).get_form_evaluations(NULL_ACTIVITY_ID)

    assert result is not None
    assert result["gct"]["score"] is None
    assert result["vo"]["score"] is None
    assert result["vr"]["score"] is None
    assert result["overall_score"] is None
