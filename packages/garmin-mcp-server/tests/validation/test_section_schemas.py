"""Tests for section analysis data validation schemas."""

import pytest

from garmin_mcp.validation.section_schemas import validate_section_data


@pytest.mark.unit
def test_unknown_section_type():
    valid, errors = validate_section_data("unknown", {"foo": "bar"})
    assert valid is False
    assert len(errors) > 0
    assert any("Unknown section_type: unknown" in e for e in errors)


# ---------------------------------------------------------------------------
# run_note -- the single coach review (Epic #1247, Issue #1251)
# ---------------------------------------------------------------------------


def _run_note_payload(**overrides: object) -> dict:
    """Minimal valid run_note payload: one good point, one timeline item."""
    data: dict = {
        "story": "今週の位置づけどおりの有酸素走で、狙った役割を果たせています。",
        "good_points": [
            {
                "text": "心拍を上限の内側に収めたまま走り切れています。",
                "evidence": "plan.hr_ceiling",
            }
        ],
        "growth_points": [],
        "next_challenge": "次回も150bpmを超えないように、140bpm前後で落ち着かせましょう。",
        "timeline": [{"moment_id": "m3", "text": "終始落ち着いたペースで進みました。"}],
        "notes": [],
    }
    data.update(overrides)
    return data


@pytest.mark.unit
def test_run_note_minimal_valid():
    valid, errors = validate_section_data("run_note", _run_note_payload())
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_run_note_schema_allows_zero_good_points():
    """A run with nothing legitimately strong leaves good_points empty (#1329)."""
    valid, errors = validate_section_data("run_note", _run_note_payload(good_points=[]))
    assert valid is True
    assert errors == []


@pytest.mark.unit
def test_run_note_rejects_four_good_points():
    point = {
        "text": "ペースが最後まで安定していました。",
        "evidence": "signals.pace_cv",
    }
    data = _run_note_payload(good_points=[point] * 4)

    valid, errors = validate_section_data("run_note", data)

    assert valid is False
    assert any("good_points" in e for e in errors)


@pytest.mark.unit
def test_run_note_rejects_bad_evidence_pattern():
    data = _run_note_payload(
        good_points=[{"text": "フォームが安定していました。", "evidence": "form"}]
    )

    valid, errors = validate_section_data("run_note", data)

    assert valid is False
    assert any("evidence" in e for e in errors)


@pytest.mark.unit
def test_validate_section_json_accepts_run_note():
    """The MCP-facing validator knows the new section type."""
    valid, errors = validate_section_data("run_note", _run_note_payload())
    assert (valid, errors) == (True, [])


@pytest.mark.unit
def test_section_schemas_reject_legacy_types():
    """Only run_note has a schema; a legacy type is an unknown type (#1256)."""
    valid, errors = validate_section_data("summary", {"summary": "x"})

    assert valid is False
    assert any("Unknown section_type: summary" in e for e in errors)

    assert validate_section_data("run_note", _run_note_payload()) == (True, [])
