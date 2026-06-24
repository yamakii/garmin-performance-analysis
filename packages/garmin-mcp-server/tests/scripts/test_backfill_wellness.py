"""Tests for the rate-limit-safe daily_wellness backfill runner (issue #510).

The pure helpers (``month_chunks``, ``backoff_seconds``, ``is_rate_limit_error``,
``jittered``) are exercised as unit tests. ``run_backfill`` is exercised as
integration with ``ingest_wellness_range`` monkeypatched (no Garmin / no real
ingest) and a no-op ``sleep`` injected so backoff incurs no real wait.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.scripts.backfill_wellness import (
    backoff_seconds,
    is_rate_limit_error,
    jittered,
    month_chunks,
    run_backfill,
)


class _FakeTooManyRequestsError(Exception):
    """Stand-in matching GarminConnectTooManyRequestsError by class name."""


# is_rate_limit_error classifies by class name, so spoof it.
_FakeTooManyRequestsError.__name__ = "GarminConnectTooManyRequestsError"


# --------------------------------------------------------------------------- #
# month_chunks
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_month_chunks_descending() -> None:
    """Window spanning 3 months splits newest->oldest with clamped edges."""
    assert month_chunks("2026-01-15", "2026-03-10") == [
        ("2026-03-01", "2026-03-10"),
        ("2026-02-01", "2026-02-28"),
        ("2026-01-15", "2026-01-31"),
    ]


@pytest.mark.unit
def test_month_chunks_single_month() -> None:
    """A single-month window yields exactly one clamped chunk."""
    assert month_chunks("2026-06-01", "2026-06-20") == [("2026-06-01", "2026-06-20")]


# --------------------------------------------------------------------------- #
# backoff_seconds
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_backoff_doubles() -> None:
    """Backoff doubles per attempt from the 60s base."""
    assert backoff_seconds(0) == 60
    assert backoff_seconds(1) == 120
    assert backoff_seconds(2) == 240


@pytest.mark.unit
def test_backoff_caps() -> None:
    """Backoff is capped at 600s for large attempts."""
    assert backoff_seconds(10) == 600


# --------------------------------------------------------------------------- #
# is_rate_limit_error
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_rate_limit_detects_429() -> None:
    """A '429 Too Many Requests' message is classified as rate-limit."""
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True


@pytest.mark.unit
def test_is_rate_limit_false_for_other() -> None:
    """An unrelated error is not classified as rate-limit."""
    assert is_rate_limit_error(ValueError("boom")) is False


# --------------------------------------------------------------------------- #
# jittered
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_jittered_within_bounds() -> None:
    """rand=0 maps to the lower bound, rand~1 to the upper bound."""
    assert jittered(8.0, 0.2, 0.0) == pytest.approx(6.4)
    assert jittered(8.0, 0.2, 1.0) == pytest.approx(9.6)


# --------------------------------------------------------------------------- #
# run_backfill (integration)
# --------------------------------------------------------------------------- #
def _patch_ingest(monkeypatch: pytest.MonkeyPatch, mock: Any) -> None:
    """Patch ingest_wellness_range at its source module (lazy import target)."""
    monkeypatch.setattr(
        "garmin_mcp.ingest.wellness_ingest.ingest_wellness_range",
        mock,
    )


@pytest.mark.integration
def test_run_backfill_stops_after_empty_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two newest chunks with data, then two empty -> stop, older chunks skipped."""

    def fake_ingest(chunk_start: str, chunk_end: str, **_kwargs: Any) -> dict[str, Any]:
        # Newest two months (May, Apr) have data; older are empty.
        with_data = 5 if chunk_start >= "2026-04-01" else 0
        return {"ingested_days": 30, "with_data": with_data, "dates": []}

    mock = MagicMock(side_effect=fake_ingest)
    _patch_ingest(monkeypatch, mock)

    result = run_backfill(
        start_date=None,
        end_date="2026-05-31",
        sleep=lambda _s: None,
        rand=lambda: 0.5,
    )

    # May(data), Apr(data), Mar(empty), Feb(empty) -> stop after 2 empties.
    assert result["chunks"] == 4
    assert result["with_data"] == 10
    assert result["aborted_reason"] is None
    assert result["floor_date"] == "2026-02-01"

    called_starts = [c.args[0] for c in mock.call_args_list]
    assert "2026-01-01" not in called_starts  # older chunk never reached


@pytest.mark.integration
def test_run_backfill_explicit_range_no_autofloor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit start_date disables auto-floor: all chunks run even if empty."""
    mock = MagicMock(return_value={"ingested_days": 28, "with_data": 0, "dates": []})
    _patch_ingest(monkeypatch, mock)

    result = run_backfill(
        start_date="2026-01-01",
        end_date="2026-04-30",
        sleep=lambda _s: None,
        rand=lambda: 0.5,
    )

    assert result["chunks"] == 4  # Jan, Feb, Mar, Apr all processed
    assert result["aborted_reason"] is None
    assert mock.call_count == 4


@pytest.mark.integration
def test_run_backfill_retries_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single 429 triggers backoff then a successful retry."""
    calls = {"n": 0}

    def fake_ingest(chunk_start: str, chunk_end: str, **_kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakeTooManyRequestsError("429 Too Many Requests")
        return {"ingested_days": 30, "with_data": 4, "dates": []}

    mock = MagicMock(side_effect=fake_ingest)
    _patch_ingest(monkeypatch, mock)

    sleep_mock = MagicMock()
    result = run_backfill(
        start_date="2026-06-01",
        end_date="2026-06-30",
        sleep=sleep_mock,
        rand=lambda: 0.5,
    )

    assert result["chunks"] == 1
    assert result["with_data"] == 4
    assert result["aborted_reason"] is None
    # Backoff for attempt 0 is 60s; injected sleep called with that value.
    sleep_mock.assert_called_once_with(60)


@pytest.mark.integration
def test_run_backfill_aborts_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continuous 429 exhausts retries -> clean abort with rate_limited reason."""

    def fake_ingest(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise _FakeTooManyRequestsError("429 Too Many Requests")

    mock = MagicMock(side_effect=fake_ingest)
    _patch_ingest(monkeypatch, mock)

    result = run_backfill(
        start_date="2026-06-01",
        end_date="2026-06-30",
        max_retries=2,
        sleep=lambda _s: None,
        rand=lambda: 0.5,
    )

    assert result["aborted_reason"] == "rate_limited"
    assert result["chunks"] == 0
    assert result["floor_date"] is None
