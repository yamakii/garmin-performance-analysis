"""prefetch_weekly_review_context carries the logged energy balance (#1435)."""

from __future__ import annotations

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import _mock_prefetch


@pytest.mark.unit
def test_prefetch_includes_energy_balance() -> None:
    """The payload ships as-is, ending on min(W end, today - 1)."""
    # Mid-week: W = 2026-07-06..12, today 2026-07-10 -> window ends yesterday.
    with _mock_prefetch() as reader:
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["energy_balance"] == {"window": {"status": "ok"}}
    reader.get_energy_balance.assert_called_once_with(
        end_date="2026-07-09", window_days=7, as_of="2026-07-10"
    )

    # Past week: W = 2026-06-29..07-05 is over -> the window ends on W's last day.
    with _mock_prefetch() as reader:
        prefetch_weekly_review_context("2026-06-29", today="2026-07-10")

    reader.get_energy_balance.assert_called_once_with(
        end_date="2026-07-05", window_days=7, as_of="2026-07-10"
    )


@pytest.mark.unit
def test_prefetch_energy_balance_safe_on_error() -> None:
    """A failing energy reader nulls the key; the rest of the bundle survives."""
    with _mock_prefetch() as reader:
        reader.get_energy_balance.side_effect = RuntimeError("no daily_energy")
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    assert result["energy_balance"] is None
    assert result["acwr"] == {"acwr": 1.0}
    assert result["recovery"]["status"] == {"recommendation": "easy"}
    assert result["symptoms"]["status"] == {"flag": False}
    assert "training_block" in result
