"""Merge-time grounding gate for the run_note section (Issue #1253).

``merge_section_analyses`` is the last place a coach review can be stopped
before it reaches the page, so these tests drive the script end-to-end with a
stubbed reader / writer: a grounded review is inserted, an ungrounded one is
rejected with the offending key named and the temp dir kept, and a stray file
of a legacy section type is turned away by the schema guard.
"""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.scripts.merge_section_analyses import merge_section_analyses

ACTIVITY_ID = 24407019887
ACTIVITY_DATE = "2026-09-18"

# The deterministic report the review is checked against: two scenes, a plan
# whose volume axis came out on plan and whose hr_ceiling axis did not, and no
# adverse out-of-range signal (so a grounded review carries no note).
_REPORT: dict = {
    "activity_id": ACTIVITY_ID,
    "activity_date": ACTIVITY_DATE,
    "headline": {"label": "処方どおり"},
    "plan": {
        "checks": [
            {"axis": "volume", "on_plan": True},
            {"axis": "hr_ceiling", "on_plan": False},
        ]
    },
    "signals": [
        {"metric": "gct", "status": "within", "adverse": False},
        {"metric": "hr_drift", "status": "edge", "adverse": False},
    ],
    "moments": [
        {"id": "m1", "kind": "steady", "split_index": 1},
        {"id": "m2", "kind": "hr_ceiling_touch", "split_index": 4},
    ],
    "recurrence": [],
    "conditions": {"temp_c": 24.1},
    "vs_previous": {"pace_delta_s_per_km": -6.0},
}

_VALID_RUN_NOTE: dict = {
    "story": "週の中盤に置いたつなぎのランで、狙いどおり脚を回復させながら距離を踏めています。",
    "good_points": [
        {"text": "処方の距離をそのまま守り切れています。", "evidence": "plan.volume"}
    ],
    "growth_points": [
        {
            "text": "終盤で上限心拍に触れた分、入りをもう少し抑える余地があります。",
            "evidence": "plan.hr_ceiling",
        }
    ],
    "next_challenge": "入りの数kmは、上限の150に近づく前に意識してペースを抑えましょう。",
    "next_challenge_evidence": "plan.hr_ceiling",
    "timeline": [
        {
            "moment_id": "m1",
            "text": "序盤は淡々と同じリズムで刻めており、無駄な上げ下げがありません。",
        },
        {
            "moment_id": "m2",
            "text": "4km地点で上限心拍に触れましたが、その後は自分で落として立て直せています。",
        },
    ],
    "notes": [],
    "question": None,
}

# A legacy summary payload: schema-valid when the five legacy sections existed,
# unknown to Guard 0 now that run_note is the only section type.
_LEGACY_SUMMARY: dict = {
    "star_rating": "★★★★☆ 4.0/5.0",
    "summary": "全体的に良好なランに仕上がりました。",
    "key_strengths": ["安定したペース"],
    "improvement_areas": ["終盤の失速"],
    "next_action": "次回はイージーペースで回復を優先しましょう。",
    "next_run_target": {"recommended_type": "easy"},
    "recommendations": "回復を最優先にしましょう。",
}


def _write_section(temp_dir: Path, section_type: str, analysis_data: dict) -> None:
    payload = {
        "activity_id": ACTIVITY_ID,
        "activity_date": ACTIVITY_DATE,
        "section_type": section_type,
        "analysis_data": analysis_data,
    }
    (temp_dir / f"{section_type}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _run_note(**overrides) -> dict:
    """A grounded run_note payload with the given fields replaced."""
    data = copy.deepcopy(_VALID_RUN_NOTE)
    data.update(overrides)
    return data


@pytest.mark.integration
class TestMergeRunNoteGroundingGate:
    """The run_note section is inserted only when every claim resolves."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_inserts_valid_run_note(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(
            _REPORT
        )
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        _write_section(tmp_path, "run_note", _run_note())

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["succeeded"] == ["run_note"]
        assert result["failed"] == []
        mock_writer.insert_section_analysis.assert_called_once()
        kwargs = mock_writer.insert_section_analysis.call_args.kwargs
        assert kwargs["section_type"] == "run_note"
        assert kwargs["activity_id"] == ACTIVITY_ID

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_run_note_grounding_gate_still_applies(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        # A growth point on a signal that never left its normal range.
        mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(
            _REPORT
        )
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        _write_section(
            tmp_path,
            "run_note",
            _run_note(
                growth_points=[
                    {
                        "text": "接地時間をもう少し短くしていきたいところです。",
                        "evidence": "signals.gct",
                    }
                ]
            ),
        )

        result = merge_section_analyses(tmp_path, keep=False)

        assert result["failed"] == ["run_note"]
        assert result["succeeded"] == []
        assert any("signals.gct" in error for error in result["errors"])
        mock_writer.insert_section_analysis.assert_not_called()
        # The temp dir survives a failure so the review can be inspected.
        assert (tmp_path / "run_note.json").exists()

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_unknown_moment(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(
            _REPORT
        )
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        _write_section(
            tmp_path,
            "run_note",
            _run_note(
                timeline=[
                    {
                        "moment_id": "m9",
                        "text": "終盤にペースを上げ切った場面が光りました。",
                    }
                ]
            ),
        )

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["failed"] == ["run_note"]
        assert any("m9" in error for error in result["errors"])
        mock_writer.insert_section_analysis.assert_not_called()

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_run_note_without_report(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        # No report (deleted / not yet ingested activity) => nothing to verify
        # against, so the review is not inserted.
        mock_reader_cls.return_value.get_run_report.return_value = None
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        _write_section(tmp_path, "run_note", _run_note())

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["failed"] == ["run_note"]
        assert any("no run report" in error for error in result["errors"])
        mock_writer.insert_section_analysis.assert_not_called()


@pytest.mark.integration
class TestMergeRejectsLegacySections:
    """A legacy section type is an unknown type to Guard 0 (Issue #1256)."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_a_legacy_section_file(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(
            _REPORT
        )
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        _write_section(tmp_path, "run_note", _run_note())
        _write_section(tmp_path, "summary", copy.deepcopy(_LEGACY_SUMMARY))

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["succeeded"] == ["run_note"]
        assert result["failed"] == ["summary"]
        assert any(
            "summary" in error and "schema validation failed" in error
            for error in result["errors"]
        )
        inserted = {
            call.kwargs["section_type"]
            for call in mock_writer.insert_section_analysis.call_args_list
        }
        assert inserted == {"run_note"}


@pytest.mark.integration
@patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
@patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
def test_merge_saves_report_moments_snapshot(
    mock_writer_cls, mock_reader_cls, tmp_path
):
    """The scenes the note was checked against are stored with it (#1328)."""
    mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(_REPORT)
    mock_writer = MagicMock()
    mock_writer.insert_section_analysis.return_value = True
    mock_writer_cls.return_value = mock_writer
    _write_section(tmp_path, "run_note", _run_note())

    merge_section_analyses(tmp_path, keep=True)

    saved = mock_writer.insert_section_analysis.call_args.kwargs["analysis_data"]
    assert saved["report_moments"] == _REPORT["moments"]
    # The note itself is stored unchanged beside the snapshot.
    assert saved["timeline"] == _VALID_RUN_NOTE["timeline"]


@pytest.mark.integration
@patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
@patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
def test_merge_overwrites_agent_report_moments(
    mock_writer_cls, mock_reader_cls, tmp_path
):
    """An agent-written report_moments never survives: merge writes the key."""
    mock_reader_cls.return_value.get_run_report.return_value = copy.deepcopy(_REPORT)
    mock_writer = MagicMock()
    mock_writer.insert_section_analysis.return_value = True
    mock_writer_cls.return_value = mock_writer
    forged = [{"id": "m1", "kind": "fade"}]
    _write_section(tmp_path, "run_note", _run_note(report_moments=forged))

    merge_section_analyses(tmp_path, keep=True)

    saved = mock_writer.insert_section_analysis.call_args.kwargs["analysis_data"]
    assert saved["report_moments"] == _REPORT["moments"]
