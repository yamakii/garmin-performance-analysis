"""Monthly target-month resolution and ensure_*: generate when missing, skip when present / incomplete, insufficient data."""

from datetime import date

import duckdb
import pytest

from garmin_mcp.form_baseline.trainer import (
    _month_end,
    _target_month_ends,
    ensure_form_baselines_for_date,
)
from tests.form_baseline.trainer._helpers import (
    _count_baseline_rows,
    _seed_two_month_window,
)


@pytest.mark.unit
def test_target_month_ends_current_and_prev():
    """_target_month_ends returns [current_month_end, prior_month_end]."""
    assert _target_month_ends("2026-06-14") == ["2026-06-30", "2026-05-31"]


@pytest.mark.unit
def test_month_end_december():
    """_month_end handles the year boundary (December)."""
    assert _month_end(date(2026, 12, 5)) == date(2026, 12, 31)


@pytest.mark.integration
def test_ensure_generates_when_missing(tmp_path):
    """ensure generates baselines for the activity month + prior month."""
    db_path = str(tmp_path / "ensure_gen.duckdb")
    activity_date = "2026-03-15"
    _seed_two_month_window(db_path, activity_date, splits_per_month=12)

    result = ensure_form_baselines_for_date(activity_date, db_path)

    assert len(result["generated"]) == 2, result
    assert result["skipped"] == []
    assert result["insufficient"] == []
    assert set(result["generated"]) == {"2026-03-31", "2026-02-28"}

    conn = duckdb.connect(db_path, read_only=True)
    try:
        for period_end in ("2026-03-31", "2026-02-28"):
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT metric) FROM form_baseline_history
                WHERE period_end = ? AND metric IN ('gct', 'vo', 'vr', 'cadence')
                """,
                [period_end],
            ).fetchone()
            assert row is not None
            assert (
                row[0] == 4
            ), f"gct/vo/vr/cadence expected for {period_end}, got {row[0]}"
    finally:
        conn.close()


@pytest.mark.integration
def test_ensure_skips_when_exists(tmp_path):
    """ensure is idempotent: a second call skips both periods, rows unchanged."""
    db_path = str(tmp_path / "ensure_skip.duckdb")
    activity_date = "2026-03-15"
    _seed_two_month_window(db_path, activity_date, splits_per_month=12)

    first = ensure_form_baselines_for_date(activity_date, db_path)
    assert len(first["generated"]) == 2

    count_after_first = _count_baseline_rows(db_path)

    second = ensure_form_baselines_for_date(activity_date, db_path)
    assert len(second["skipped"]) == 2, second
    assert second["generated"] == []
    assert second["insufficient"] == []
    assert set(second["skipped"]) == {"2026-03-31", "2026-02-28"}

    count_after_second = _count_baseline_rows(db_path)

    assert count_after_second == count_after_first, "row count must be unchanged"


@pytest.mark.integration
def test_ensure_insufficient_data(tmp_path):
    """ensure records insufficient periods when splits < 50, no rows, no raise."""
    db_path = str(tmp_path / "ensure_insufficient.duckdb")
    activity_date = "2026-03-15"
    # 1 activity/month -> 5 splits/month -> < 50 in each 2-month window.
    _seed_two_month_window(db_path, activity_date, splits_per_month=1)

    result = ensure_form_baselines_for_date(activity_date, db_path)

    assert result["generated"] == [], result
    assert result["skipped"] == []
    assert len(result["insufficient"]) == 2
    assert set(result["insufficient"]) == {"2026-03-31", "2026-02-28"}

    assert (
        _count_baseline_rows(db_path) == 0
    ), "no baseline rows should be created on insufficient data"


@pytest.mark.integration
def test_ensure_skips_only_when_all_four_metrics_present(tmp_path):
    """A period missing cadence (only gct/vo/vr) is re-trained, not skipped (#640)."""
    db_path = str(tmp_path / "ensure_partial.duckdb")
    activity_date = "2026-03-15"
    _seed_two_month_window(db_path, activity_date, splits_per_month=12)

    # Pre-seed only gct/vo/vr for the current-month period (cadence missing),
    # mimicking an older batch run that predated cadence support.
    conn = duckdb.connect(db_path)
    try:
        for metric in ("gct", "vo", "vr"):
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (user_id, condition_group, metric, model_type,
                     period_start, period_end, n_samples)
                VALUES ('default', 'flat_road', ?, 'linear',
                        '2026-02-01', '2026-03-31', 60)
                """,
                [metric],
            )
    finally:
        conn.close()

    result = ensure_form_baselines_for_date(activity_date, db_path)

    # Incomplete current-month period must be regenerated, not skipped.
    assert "2026-03-31" in result["generated"], result
    assert "2026-03-31" not in result["skipped"], result

    conn = duckdb.connect(db_path, read_only=True)
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM form_baseline_history
            WHERE period_end = '2026-03-31' AND metric = 'cadence'
            """).fetchone()
        assert row is not None and row[0] >= 1, "cadence baseline must now exist"
    finally:
        conn.close()
