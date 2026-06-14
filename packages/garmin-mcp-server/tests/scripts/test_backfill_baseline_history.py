"""Unit tests for backfill_baseline_history script.

Covers the generalized year filter (2021 and 2025+) in generate_month_range
and the module-based subprocess invocation in train_month (issue #263).
"""

from datetime import datetime

import pytest

from garmin_mcp.scripts.backfill_baseline_history import (
    generate_month_range,
    train_month,
)


@pytest.mark.unit
def test_generate_month_range_includes_2026():
    """2025-12 through 2026-02 should all be included (2025+ gate)."""
    result = generate_month_range(datetime(2025, 12, 1), datetime(2026, 2, 1))
    assert result == ["2025-12", "2026-01", "2026-02"]


@pytest.mark.unit
def test_generate_month_range_excludes_gap_years():
    """Gap years 2022-2024 produce no months."""
    result = generate_month_range(datetime(2022, 1, 1), datetime(2024, 12, 1))
    assert result == []


@pytest.mark.unit
def test_generate_month_range_keeps_2021():
    """Historical 2021 data is still included."""
    result = generate_month_range(datetime(2021, 1, 1), datetime(2021, 3, 1))
    assert result == ["2021-01", "2021-02", "2021-03"]


@pytest.mark.unit
def test_train_month_uses_module_invocation(capsys):
    """train_month should invoke the trainer via `-m` module path, not stale path."""
    result = train_month(
        year_month="2026-01",
        db_path="data/database/garmin_performance.duckdb",
        condition_group="flat_road",
        min_samples=50,
        verbose=False,
        dry_run=True,
    )

    assert result is True

    captured = capsys.readouterr().out
    assert "-m" in captured
    assert "garmin_mcp.scripts.train_form_baselines_monthly" in captured
    assert "tools/scripts/" not in captured
