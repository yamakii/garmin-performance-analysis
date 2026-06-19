"""Tests for form baseline training scripts (weekly/monthly thin CLI wrappers).

Verifies the window-start derivation for each entry point and that both
delegate to the shared ``train_and_store_baseline`` body.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from garmin_mcp.scripts.train_form_baselines_monthly import parse_year_month
from garmin_mcp.scripts.train_form_baselines_weekly import parse_date


@pytest.mark.unit
def test_window_start_weekly() -> None:
    """Weekly window: 2025-10-06 -> start 2025-08-07, end 2025-10-06."""
    period_start, period_end = parse_date("2025-10-06")
    assert period_start == datetime(2025, 8, 7)
    assert period_end == datetime(2025, 10, 6)


@pytest.mark.unit
def test_window_start_monthly() -> None:
    """Monthly window: 2025-10 -> start 2025-09-01, end 2025-10-31."""
    period_start, period_end = parse_year_month("2025-10")
    assert period_start == datetime(2025, 9, 1)
    assert period_end == datetime(2025, 10, 31)


@pytest.mark.unit
def test_shared_training_body_invoked() -> None:
    """Both weekly and monthly delegate to the shared training body."""
    from garmin_mcp.scripts import (
        train_form_baselines_monthly as monthly,
    )
    from garmin_mcp.scripts import (
        train_form_baselines_weekly as weekly,
    )

    # Weekly invokes the shared body once with its derived window.
    with (
        patch.object(weekly, "train_and_store_baseline", return_value=0) as mock_body,
        patch(
            "sys.argv",
            ["prog", "--end-date", "2025-10-06", "--condition", "flat_road"],
        ),
    ):
        assert weekly.main() == 0
    assert mock_body.call_count == 1
    args, kwargs = mock_body.call_args
    assert args[0] == datetime(2025, 8, 7)
    assert args[1] == datetime(2025, 10, 6)
    assert kwargs["condition"] == "flat_road"

    # Monthly invokes the same shared body once with its derived window.
    with (
        patch.object(monthly, "train_and_store_baseline", return_value=0) as mock_body,
        patch(
            "sys.argv",
            ["prog", "--year-month", "2025-10", "--condition", "flat_road"],
        ),
    ):
        assert monthly.main() == 0
    assert mock_body.call_count == 1
    args, kwargs = mock_body.call_args
    assert args[0] == datetime(2025, 9, 1)
    assert args[1] == datetime(2025, 10, 31)
    assert kwargs["condition"] == "flat_road"

    # Both wrappers import the identical shared symbol (no duplicated body).
    assert (
        weekly.train_and_store_baseline.__module__
        == "garmin_mcp.scripts._form_baseline_training"
    )
    assert weekly.train_and_store_baseline is monthly.train_and_store_baseline
