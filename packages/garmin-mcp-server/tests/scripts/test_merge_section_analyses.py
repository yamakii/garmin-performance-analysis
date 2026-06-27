"""Integration tests for merge_section_analyses form_trend guard."""

import json
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.scripts.merge_section_analyses import merge_section_analyses


def _write_efficiency_json(temp_dir, form_trend: str) -> None:
    payload = {
        "activity_id": 23337872734,
        "activity_date": "2026-06-22",
        "section_type": "efficiency",
        "analysis_data": {"form_trend": form_trend},
    }
    (temp_dir / "efficiency.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.integration
class TestMergeFormTrendGuard:
    """Guard blocks inconsistent efficiency form_trend before insert."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_blocks_inconsistent_form_trend(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        # baseline comparison available (success=True), but form_trend skips.
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": True,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        _write_efficiency_json(
            tmp_path, "ベースラインデータが含まれていないため省略します。"
        )

        result = merge_section_analyses(tmp_path, keep=True)

        assert "efficiency" in result["failed"]
        assert "efficiency" not in result["succeeded"]
        mock_writer.insert_section_analysis.assert_not_called()


def _write_section_json(temp_dir, section_type: str, analysis_data: dict) -> None:
    payload = {
        "activity_id": 23337872734,
        "activity_date": "2026-06-22",
        "section_type": section_type,
        "analysis_data": analysis_data,
    }
    (temp_dir / f"{section_type}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.integration
class TestMergeNarrationNumericGuard:
    """Guard blocks out-of-range summary narration; other sections still insert."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_blocks_summary_on_bad_score(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": False,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        # summary has an out-of-range integrated_score -> must be skipped.
        _write_section_json(
            tmp_path,
            "summary",
            {"integrated_score": 120, "star_rating": "★★★★☆ 4.2/5.0"},
        )
        # 4 other valid sections must still be inserted.
        for section in ("efficiency", "phase", "environment", "split"):
            _write_section_json(tmp_path, section, {"note": f"{section} ok"})

        result = merge_section_analyses(tmp_path, keep=True)

        assert "summary" in result["failed"]
        assert "summary" not in result["succeeded"]
        assert sorted(result["succeeded"]) == [
            "efficiency",
            "environment",
            "phase",
            "split",
        ]
        inserted = {
            call.kwargs["section_type"]
            for call in mock_writer.insert_section_analysis.call_args_list
        }
        assert "summary" not in inserted
        assert inserted == {"efficiency", "phase", "environment", "split"}
