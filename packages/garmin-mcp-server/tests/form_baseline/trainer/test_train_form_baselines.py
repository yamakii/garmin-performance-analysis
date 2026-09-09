"""train_form_baselines(): cadence row, min-samples gate, exclusion of GPS-fragment splits."""

from datetime import date, datetime, timedelta

import duckdb
import pytest

from garmin_mcp.form_baseline.trainer import (
    train_form_baselines,
)
from tests.form_baseline.trainer._helpers import (
    FRAGMENT_END_DATE,
    FULL_SPLIT_COUNT,
    _create_baseline_schema,
    _make_splits,
    _seed_baseline_db,
    _seed_fragment_contaminated_db,
)


@pytest.mark.integration
def test_train_form_baselines_inserts_cadence_row(tmp_path):
    """Regression for #219: cadence baseline INSERT must succeed.

    The cadence INSERT previously had an off-by-one placeholder (15 ? for
    14 values), causing DuckDB to fail and the cadence baseline to never
    persist. train_form_baselines swallows the error and returns None, so
    we assert directly against form_baseline_history.
    """
    db_path = str(tmp_path / "baseline.duckdb")
    _seed_baseline_db(db_path)

    result = train_form_baselines(
        user_id="default",
        condition_group="flat_road",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        window_months=2,
        db_path=db_path,
    )

    assert result is not None, "train_form_baselines should not fail on valid data"

    conn = duckdb.connect(db_path, read_only=True)
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM form_baseline_history WHERE metric = 'cadence'"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == 1, "Exactly one cadence baseline row expected"

        coef_row = conn.execute(
            "SELECT coef_a, coef_b FROM form_baseline_history WHERE metric = 'cadence'"
        ).fetchone()
        assert coef_row is not None
        assert coef_row[0] is not None, "cadence coef_a must be non-null"
        assert coef_row[1] is not None, "cadence coef_b must be non-null"

        # VO/VR baselines should be created alongside cadence.
        vo_vr_row = conn.execute(
            "SELECT COUNT(*) FROM form_baseline_history " "WHERE metric IN ('vo', 'vr')"
        ).fetchone()
        assert vo_vr_row is not None
        assert vo_vr_row[0] == 2, "VO and VR baselines should also be inserted"
    finally:
        conn.close()


@pytest.mark.integration
def test_train_form_baselines_respects_min_samples(tmp_path):
    """min_samples gates training: 60 in-window rows -> None at 100, trains at 50."""
    db_path = str(tmp_path / "min_samples.duckdb")
    end_date = "2026-03-31"  # 2-month window: 2026-02-01 .. 2026-03-31

    conn = duckdb.connect(db_path)
    _create_baseline_schema(conn)
    activity_rows = []
    split_rows = []
    for k in range(12):  # 12 activities * 5 splits = 60 in-window rows
        activity_id = 4000 + k
        act_date = date(2026, 3, 1) + timedelta(days=k)
        activity_rows.append((activity_id, act_date, 70.0))
        split_rows.extend(_make_splits(activity_id))
    conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", split_rows
    )
    conn.close()

    # 60 rows < min_samples=100 -> insufficient -> None.
    assert (
        train_form_baselines(
            end_date=end_date, window_months=2, db_path=db_path, min_samples=100
        )
        is None
    )

    # 60 rows >= min_samples=50 -> trains and persists.
    result = train_form_baselines(
        end_date=end_date, window_months=2, db_path=db_path, min_samples=50
    )
    assert result is not None
    assert "cadence" in result


@pytest.mark.integration
def test_train_form_baselines_excludes_fragment_splits(tmp_path):
    """GPS fragments must not invert the cadence slope (#873).

    Without the minimum-distance filter the 8 m fragments pull the Huber fit
    negative (faster => lower cadence), which is physiologically backwards.
    """
    db_path = str(tmp_path / "fragments_slope.duckdb")
    _seed_fragment_contaminated_db(db_path)

    result = train_form_baselines(
        end_date=FRAGMENT_END_DATE, window_months=2, db_path=db_path
    )

    assert result is not None
    assert result["cadence"]["b"] > 0, (
        "cadence slope must stay positive once GPS fragments are excluded, "
        f"got b={result['cadence']['b']}"
    )

    conn = duckdb.connect(db_path, read_only=True)
    try:
        row = conn.execute("""
            SELECT model_type, coef_b FROM form_baseline_history
            WHERE metric = 'cadence'
            """).fetchone()
        assert row is not None
        # A healthy fit is persisted as 'linear' (not the 'linear_flat'
        # fallback used when the slope had to be suppressed).
        assert row[0] == "linear"
        assert row[1] > 0
    finally:
        conn.close()


@pytest.mark.integration
def test_train_form_baselines_fragment_splits_excluded_from_n_samples(tmp_path):
    """Fragment laps are filtered out of the training window entirely."""
    db_path = str(tmp_path / "fragments_n.duckdb")
    _seed_fragment_contaminated_db(db_path)

    result = train_form_baselines(
        end_date=FRAGMENT_END_DATE, window_months=2, db_path=db_path
    )

    assert result is not None
    for metric in ("gct", "vo", "vr", "cadence"):
        assert result[metric]["n_samples"] == FULL_SPLIT_COUNT, (
            f"{metric} trained on {result[metric]['n_samples']} samples; "
            f"only the {FULL_SPLIT_COUNT} full 1 km splits are eligible"
        )
