"""Tests for evaluate_form_safely: the never-raising wrapper every ingest calls."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from garmin_mcp.form_baseline.evaluator import evaluate_form_safely

_TARGET = "garmin_mcp.form_baseline.evaluator.evaluate_and_store"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        (None, "success"),
        (FileNotFoundError("no model"), "model_not_found"),
        (ValueError("no splits"), "failed"),
        (RuntimeError("boom"), "error"),
    ],
)
def test_evaluate_form_safely_returns_status_on_error(
    side_effect: Exception | None, expected: str
) -> None:
    with patch(_TARGET, side_effect=side_effect) as evaluate:
        status = evaluate_form_safely(123, "2026-11-22", "/tmp/x.duckdb")

    assert status == expected
    evaluate.assert_called_once_with(
        activity_id=123, activity_date="2026-11-22", db_path="/tmp/x.duckdb"
    )
