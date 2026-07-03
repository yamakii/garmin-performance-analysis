"""Tests for merge_section_analyses semantic + schema guards."""

import copy
import json
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.scripts.merge_section_analyses import merge_section_analyses

# Schema-valid analysis_data per section type. Guard 0 (schema re-validation,
# Issue #708) rejects payloads missing required fields, so tests that exercise
# the downstream semantic guards must start from schema-valid data.
_VALID_ANALYSIS_DATA: dict[str, dict] = {
    "efficiency": {
        "efficiency": "フォーム効率は全体的に良好な水準を維持しています。",
        "evaluation": "接地時間と上下動のバランスが取れており安定しています。",
        "form_trend": "ベースライン比で安定しています。",
    },
    "phase": {
        "warmup_evaluation": "ウォームアップは適切に実施されています。",
        "run_evaluation": "メイン走行区間は安定したペースを維持しています。",
        "cooldown_evaluation": "クールダウンは十分な時間を確保できています。",
        "evaluation_criteria": "各フェーズのHRとペースで評価しています。",
    },
    "environment": {
        "environmental": "気温と湿度の影響は軽微で走行に大きな支障はありませんでした。",
    },
    "split": {
        "highlights": "全体的に安定したペースで走行できています。",
        "analyses": {"split_1": "1km地点は良好なペースでした。"},
    },
    "summary": {
        "star_rating": "★★★★☆ 4.0/5.0",
        "integrated_score": 82.0,
        "summary": "全体的に良好なランに仕上がりました。",
        "key_strengths": ["安定したペース"],
        "improvement_areas": ["終盤の失速"],
        "next_action": "次回はイージーペースで回復を優先しましょう。",
        "next_run_target": {"recommended_type": "easy"},
        "recommendations": "回復を最優先にしましょう。",
    },
}


def _valid_data(section_type: str) -> dict:
    """Return a fresh copy of schema-valid analysis_data for the section."""
    return copy.deepcopy(_VALID_ANALYSIS_DATA[section_type])


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


def _write_efficiency_json(temp_dir, form_trend: str) -> None:
    data = _valid_data("efficiency")
    data["form_trend"] = form_trend
    _write_section_json(temp_dir, "efficiency", data)


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

        # Schema-valid summary, but star_rating numeric is out of range -> the
        # narration guard (not schema) must reject it.
        summary = _valid_data("summary")
        summary["star_rating"] = "★★★★★ 6.5/5.0"
        _write_section_json(tmp_path, "summary", summary)
        # 4 other valid sections must still be inserted.
        for section in ("efficiency", "phase", "environment", "split"):
            _write_section_json(tmp_path, section, _valid_data(section))

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
        summary = _valid_data("summary")
        summary["integrated_score"] = 85.0
        summary["star_rating"] = "★★★★☆ 4.5/5.0"
        summary["star_rating_breakdown"] = {
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
        }
        _write_section_json(tmp_path, "summary", summary)
        # Another valid section must still be inserted.
        _write_section_json(tmp_path, "split", _valid_data("split"))

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


@pytest.mark.unit
class TestMergeSchemaGuard:
    """Guard 0 re-validates each section against its schema before insert."""

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_schema_invalid_section(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": False,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        # Remove a required field ("summary") -> schema validation must fail.
        summary = _valid_data("summary")
        del summary["summary"]
        _write_section_json(tmp_path, "summary", summary)

        result = merge_section_analyses(tmp_path, keep=True)

        assert "summary" in result["failed"]
        assert "summary" not in result["succeeded"]
        assert any("schema validation failed" in err for err in result["errors"])
        inserted = {
            call.kwargs["section_type"]
            for call in mock_writer.insert_section_analysis.call_args_list
        }
        assert "summary" not in inserted

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_accepts_valid_sections(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": True,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        for section in ("efficiency", "phase", "environment", "split", "summary"):
            _write_section_json(tmp_path, section, _valid_data(section))

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["failed"] == []
        assert sorted(result["succeeded"]) == [
            "efficiency",
            "environment",
            "phase",
            "split",
            "summary",
        ]

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_shares_one_run_id_across_sections(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        """One merge = one run_id, passed to every section (#776)."""
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": True,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer.next_run_id.return_value = 42
        mock_writer_cls.return_value = mock_writer

        for section in ("efficiency", "phase", "environment", "split", "summary"):
            _write_section_json(tmp_path, section, _valid_data(section))

        result = merge_section_analyses(tmp_path, keep=True)

        assert result["failed"] == []
        # next_run_id allocated exactly once; every insert got that run_id.
        mock_writer.next_run_id.assert_called_once()
        assert mock_writer.insert_section_analysis.call_count == 5
        run_ids = {
            call.kwargs["run_id"]
            for call in mock_writer.insert_section_analysis.call_args_list
        }
        assert run_ids == {42}

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_rejects_unknown_section_type(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": False,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        # A stray filename yields section_type="stray", absent from SECTION_SCHEMAS.
        _write_section_json(tmp_path, "stray", {"foo": "bar"})

        result = merge_section_analyses(tmp_path, keep=True)

        assert "stray" in result["failed"]
        assert "stray" not in result["succeeded"]
        mock_writer.insert_section_analysis.assert_not_called()

    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBReader")
    @patch("garmin_mcp.scripts.merge_section_analyses.GarminDBWriter")
    def test_merge_keeps_temp_dir_on_schema_failure(
        self, mock_writer_cls, mock_reader_cls, tmp_path
    ):
        mock_reader_cls.return_value.physiology.get_form_baseline_trend.return_value = {
            "success": False,
            "metrics": {},
        }
        mock_writer = MagicMock()
        mock_writer.insert_section_analysis.return_value = True
        mock_writer_cls.return_value = mock_writer

        # One schema-invalid section -> failed is non-empty -> temp_dir kept
        # even though keep defaults to False.
        summary = _valid_data("summary")
        del summary["summary"]
        _write_section_json(tmp_path, "summary", summary)

        result = merge_section_analyses(tmp_path)

        assert "summary" in result["failed"]
        assert tmp_path.exists()
