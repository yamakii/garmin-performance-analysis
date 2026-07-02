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


@pytest.mark.integration
class TestMergeStarWeightingGuard:
    """Guard blocks weighting-inconsistent star ratings before insert."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_summary_with_wrong_weighting(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": False,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        # Stated 4.5 but the breakdown recomputes to 3.7 -> must be skipped.
        _write_section_json(
            tmp_path,
            "summary",
            {
                "integrated_score": 85.0,
                "star_rating": "★★★★☆ 4.5/5.0",
                "star_rating_breakdown": {
                    "axis_scores": {
                        "effort": 4.0,
                        "performance": 3.0,
                        "efficiency": 5.0,
                        "execution": 2.0,
                    },
                    "weights": {
                        "effort": 0.4,
                        "performance": 0.3,
                        "efficiency": 0.2,
                        "execution": 0.1,
                    },
                },
            },
        )
        # Another valid section must still be inserted.
        _write_section_json(tmp_path, "split", {"note": "split ok"})

        result = merge_section_analyses(tmp_path, keep=True)

        assert "summary" in result["failed"]
        assert "summary" not in result["succeeded"]
        assert result["succeeded"] == ["split"]
        assert any("3.7" in err and "4.5" in err for err in result["errors"])
        inserted = {
            call.kwargs["section_type"]
            for call in mock_writer.insert_section_analysis.call_args_list
        }
        assert inserted == {"split"}
