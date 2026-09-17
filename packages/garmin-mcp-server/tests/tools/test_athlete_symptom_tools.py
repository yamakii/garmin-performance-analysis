"""Unit tests for the symptom-log tools (Issue #1220)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.athlete import SaveSymptomParams
from garmin_mcp.tools.registry import dispatch


@pytest.mark.unit
def test_save_symptom_rejects_severity_11_and_unknown_region() -> None:
    """Severity is a 0-10 scale and the region vocabulary is closed."""
    base: dict[str, object] = {
        "date": "2026-09-18",
        "body_region": "calf",
        "phase": "morning",
    }

    with pytest.raises(ValidationError):
        SaveSymptomParams.model_validate(base | {"severity": 11})

    with pytest.raises(ValidationError):
        SaveSymptomParams.model_validate(base | {"severity": -1})

    with pytest.raises(ValidationError):
        SaveSymptomParams.model_validate(
            base | {"body_region": "archilles", "severity": 3}
        )

    # The boundaries themselves are valid.
    assert SaveSymptomParams.model_validate(base | {"severity": 0}).severity == 0
    assert SaveSymptomParams.model_validate(base | {"severity": 10}).severity == 10


@pytest.mark.unit
def test_save_symptom_dispatches_to_inserter() -> None:
    """save_symptom writes through the inserter and returns the new id."""
    assert "save_symptom" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.db_path = ":memory:"
    with patch(
        "garmin_mcp.database.inserters.athlete.insert_symptom", return_value=7
    ) as insert_mock:
        result = dispatch(
            ALL_DEFS_BY_NAME,
            reader,
            "save_symptom",
            {
                "date": "2026-09-18",
                "body_region": "calf",
                "severity": 3,
                "phase": "morning",
                "side": "right",
            },
        )

    assert result == {"status": "saved", "symptom_id": 7}
    row = insert_mock.call_args.kwargs["row"]
    assert row["user_id"] == "default"
    assert row["body_region"] == "calf"
    assert row["severity"] == 3
    assert row["side"] == "right"
    assert row["activity_id"] is None


@pytest.mark.unit
def test_get_symptoms_dispatches_to_reader() -> None:
    """get_symptoms forwards the range/region filter to the athlete reader."""
    assert "get_symptoms" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.db_path = ":memory:"
    with patch("garmin_mcp.database.readers.athlete.AthleteReader") as athlete_cls:
        athlete_cls.return_value.get_symptoms.return_value = []
        result = dispatch(
            ALL_DEFS_BY_NAME,
            reader,
            "get_symptoms",
            {
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "body_region": "calf",
            },
        )
        athlete_cls.return_value.get_symptoms.assert_called_once_with(
            start_date="2026-09-01",
            end_date="2026-09-30",
            user_id="default",
            body_region="calf",
        )

    assert result == []
