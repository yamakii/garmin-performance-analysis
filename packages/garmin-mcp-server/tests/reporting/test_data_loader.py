"""Unit tests for ReportDataLoader class."""

from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.data_loader import ReportDataLoader


@pytest.fixture
def mock_db_reader():
    """Create mock GarminDBReader."""
    return MagicMock(spec=GarminDBReader)


@pytest.fixture
def data_loader(mock_db_reader):
    """Create ReportDataLoader with mock db_reader."""
    return ReportDataLoader(db_reader=mock_db_reader)


class TestLoadSplits:
    """Test load_splits method."""

    @pytest.mark.unit
    def test_load_splits_normal_data(self, data_loader, mock_db_reader):
        """Test load_splits with normal data."""
        # Mock data: (index, pace, hr, cadence, power, stride, gct, vo, vr, elev_gain, elev_loss, intensity)
        mock_db_reader.execute_read_query.return_value = [
            (1, 300, 150, 180, 250, 12000, 240, 85, 8.5, 10, 5, "WARMUP"),
            (2, 280, 160, 182, 260, 12200, 238, 84, 8.4, 15, 3, "INTERVAL"),
            (3, 320, 155, 178, 240, 11800, 242, 86, 8.6, 8, 7, "RECOVERY"),
            (4, 310, 152, 179, 245, 12100, 241, 85, 8.5, 12, 6, "COOLDOWN"),
        ]

        result = data_loader.load_splits(activity_id=12345)

        assert len(result) == 4

        # Check first split (WARMUP)
        assert result[0]["index"] == 1
        assert result[0]["pace_seconds_per_km"] == 300
        assert result[0]["pace_formatted"] == "5:00/km"
        assert result[0]["heart_rate"] == 150
        assert result[0]["cadence"] == 180
        assert result[0]["power"] == 250
        assert result[0]["stride_length"] == 120.0  # 12000/100
        assert result[0]["ground_contact_time"] == 240
        assert result[0]["vertical_oscillation"] == 85
        assert result[0]["vertical_ratio"] == 8.5
        assert result[0]["elevation_gain"] == 10
        assert result[0]["elevation_loss"] == 5
        assert result[0]["intensity_type"] == "warmup"

        # Check second split (INTERVAL -> active)
        assert result[1]["intensity_type"] == "active"

        # Check third split (RECOVERY -> rest)
        assert result[2]["intensity_type"] == "rest"

        # Check fourth split (COOLDOWN -> cooldown)
        assert result[3]["intensity_type"] == "cooldown"

    @pytest.mark.unit
    def test_load_splits_empty_result(self, data_loader, mock_db_reader):
        """Test load_splits with empty result returns empty list."""
        mock_db_reader.execute_read_query.return_value = []

        result = data_loader.load_splits(activity_id=12345)

        assert result == []

    @pytest.mark.unit
    def test_load_splits_exception_returns_empty_list(
        self, data_loader, mock_db_reader
    ):
        """Test load_splits with exception returns empty list."""
        mock_db_reader.execute_read_query.side_effect = Exception("Database error")

        result = data_loader.load_splits(activity_id=12345)

        assert result == []

    @pytest.mark.unit
    def test_load_splits_intensity_type_normalization(
        self, data_loader, mock_db_reader
    ):
        """Test load_splits normalizes intensity_type correctly."""
        mock_db_reader.execute_read_query.return_value = [
            (1, 300, 150, 180, 250, 12000, 240, 85, 8.5, 10, 5, "WARMUP"),
            (2, 280, 160, 182, 260, 12200, 238, 84, 8.4, 15, 3, "INTERVAL"),
            (3, 320, 155, 178, 240, 11800, 242, 86, 8.6, 8, 7, "RECOVERY"),
            (4, 310, 152, 179, 245, 12100, 241, 85, 8.5, 12, 6, "COOLDOWN"),
            (5, 290, 158, 181, 255, 12050, 239, 84, 8.4, 11, 4, "ACTIVE"),
            (6, 285, 159, 182, 258, 12150, 237, 83, 8.3, 13, 5, "REST"),
            (7, 295, 157, 180, 252, 12000, 240, 85, 8.5, 10, 6, None),
        ]

        result = data_loader.load_splits(activity_id=12345)

        assert result[0]["intensity_type"] == "warmup"
        assert result[1]["intensity_type"] == "active"
        assert result[2]["intensity_type"] == "rest"
        assert result[3]["intensity_type"] == "cooldown"
        assert result[4]["intensity_type"] == "active"  # lowercase
        assert result[5]["intensity_type"] == "rest"  # lowercase
        assert result[6]["intensity_type"] is None

    @pytest.mark.unit
    def test_load_splits_none_stride_length(self, data_loader, mock_db_reader):
        """Test load_splits with None stride_length."""
        mock_db_reader.execute_read_query.return_value = [
            (1, 300, 150, 180, 250, None, 240, 85, 8.5, 10, 5, "WARMUP"),
        ]

        result = data_loader.load_splits(activity_id=12345)

        assert result[0]["stride_length"] is None

    @pytest.mark.unit
    def test_load_splits_zero_pace(self, data_loader, mock_db_reader):
        """Test load_splits with zero pace returns N/A."""
        mock_db_reader.execute_read_query.return_value = [
            (1, 0, 150, 180, 250, 12000, 240, 85, 8.5, 10, 5, "WARMUP"),
            (2, None, 160, 182, 260, 12200, 238, 84, 8.4, 15, 3, "INTERVAL"),
        ]

        result = data_loader.load_splits(activity_id=12345)

        assert result[0]["pace_formatted"] == "N/A"
        assert result[1]["pace_formatted"] == "N/A"

    @pytest.mark.unit
    def test_load_splits_calls_execute_read_query(self, data_loader, mock_db_reader):
        """Test load_splits calls execute_read_query with correct SQL."""
        mock_db_reader.execute_read_query.return_value = []

        data_loader.load_splits(activity_id=12345)

        mock_db_reader.execute_read_query.assert_called_once()
        call_args = mock_db_reader.execute_read_query.call_args
        assert "SELECT" in call_args[0][0]
        assert "FROM splits" in call_args[0][0]
        assert "WHERE activity_id = ?" in call_args[0][0]
        assert call_args[0][1] == (12345,)


class TestLoadSplitsData:
    """Test load_splits_data method."""

    @pytest.mark.unit
    def test_load_splits_data_normal_data(self, data_loader, mock_db_reader):
        """Test load_splits_data with normal data."""
        # Mock data: (index, distance, pace, hr, cadence, power, stride, gct, vo, vr, elev_gain, elev_loss, pace_str, intensity)
        mock_db_reader.execute_read_query.return_value = [
            (1, 1.0, 300, 150, 180, 250, 12000, 240, 85, 8.5, 10, 5, "5:00", "WARMUP"),
            (
                2,
                2.0,
                280,
                160,
                182,
                260,
                12200,
                238,
                84,
                8.4,
                15,
                3,
                "4:40",
                "INTERVAL",
            ),
        ]

        result = data_loader.load_splits_data(activity_id=12345)

        assert len(result) == 2

        # Check first split
        assert result[0]["index"] == 1
        assert result[0]["distance"] == 1.0
        assert result[0]["pace_seconds_per_km"] == 300
        assert result[0]["pace_formatted"] == "5:00"
        assert result[0]["heart_rate"] == 150
        assert result[0]["cadence"] == 180
        assert result[0]["power"] == 250
        assert result[0]["stride_length"] == 120.0  # 12000/100
        assert result[0]["ground_contact_time"] == 240
        assert result[0]["vertical_oscillation"] == 85
        assert result[0]["vertical_ratio"] == 8.5
        assert result[0]["elevation_gain"] == 10
        assert result[0]["elevation_loss"] == 5
        assert result[0]["intensity_type"] == "WARMUP"

        # Check second split
        assert result[1]["index"] == 2
        assert result[1]["pace_formatted"] == "4:40"

    @pytest.mark.unit
    def test_load_splits_data_empty_returns_none(self, data_loader, mock_db_reader):
        """Test load_splits_data with empty result returns None."""
        mock_db_reader.execute_read_query.return_value = []

        result = data_loader.load_splits_data(activity_id=12345)

        assert result is None

    @pytest.mark.unit
    def test_load_splits_data_exception_returns_none(self, data_loader, mock_db_reader):
        """Test load_splits_data with exception returns None."""
        mock_db_reader.execute_read_query.side_effect = Exception("Database error")

        result = data_loader.load_splits_data(activity_id=12345)

        assert result is None

    @pytest.mark.unit
    def test_load_splits_data_none_stride_length(self, data_loader, mock_db_reader):
        """Test load_splits_data with None stride_length."""
        mock_db_reader.execute_read_query.return_value = [
            (1, 1.0, 300, 150, 180, 250, None, 240, 85, 8.5, 10, 5, "5:00", "WARMUP"),
        ]

        result = data_loader.load_splits_data(activity_id=12345)

        assert result[0]["stride_length"] is None

    @pytest.mark.unit
    def test_load_splits_data_none_pace_str(self, data_loader, mock_db_reader):
        """Test load_splits_data with None pace_str returns N/A."""
        mock_db_reader.execute_read_query.return_value = [
            (1, 1.0, 300, 150, 180, 250, 12000, 240, 85, 8.5, 10, 5, None, "WARMUP"),
        ]

        result = data_loader.load_splits_data(activity_id=12345)

        assert result[0]["pace_formatted"] == "N/A"


class TestLoadSectionAnalyses:
    """Test load_section_analyses method."""

    @pytest.mark.unit
    def test_load_section_analyses_all_sections_present(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses with all sections present."""

        # Mock get_section_analysis to return different data for each section
        def mock_get_section(activity_id, section_type):
            sections = {
                "efficiency": {
                    "efficiency": "効率良好",
                    "evaluation": "心拍数効率評価",
                    "form_trend": "フォーム傾向",
                },
                "environment": {
                    "environmental": {
                        "temperature": "快適",
                        "wind": "微風",
                    }
                },
                "phase": {
                    "warmup": "適切",
                    "run": "安定",
                    "cooldown": "良好",
                    "rating": "****",
                },
                "split": {
                    "consistency": "高い",
                    "analysis": "均等ペース",
                },
                "summary": {
                    "activity_type": "ジョグ",
                    "overall_rating": "*****",
                    "key_strengths": "ペース安定\n\n心拍数適正\n\nフォーム良好",
                    "improvement_areas": "ケイデンス向上\n\nストライド改善",
                },
            }
            return sections.get(section_type)

        mock_db_reader.get_section_analysis.side_effect = mock_get_section

        result = data_loader.load_section_analyses(activity_id=12345)

        assert result is not None
        assert "efficiency" in result
        assert "environment_analysis" in result
        assert "phase_evaluation" in result
        assert "split_analysis" in result
        assert "summary" in result

        # Check efficiency data
        assert result["efficiency"]["efficiency"] == "効率良好"
        assert result["efficiency"]["evaluation"] == "心拍数効率評価"

        # Check environment data (nested under environmental)
        assert result["environment_analysis"]["temperature"] == "快適"
        assert result["environment_analysis"]["wind"] == "微風"

        # Check phase data
        assert result["phase_evaluation"]["rating"] == "****"

        # Check split data
        assert result["split_analysis"]["consistency"] == "高い"

        # Check summary data (string to list conversion)
        assert isinstance(result["summary"]["key_strengths"], list)
        assert len(result["summary"]["key_strengths"]) == 3
        assert result["summary"]["key_strengths"][0] == "ペース安定"
        assert result["summary"]["key_strengths"][1] == "心拍数適正"
        assert result["summary"]["key_strengths"][2] == "フォーム良好"

        assert isinstance(result["summary"]["improvement_areas"], list)
        assert len(result["summary"]["improvement_areas"]) == 2
        assert result["summary"]["improvement_areas"][0] == "ケイデンス向上"
        assert result["summary"]["improvement_areas"][1] == "ストライド改善"

    @pytest.mark.unit
    def test_load_section_analyses_partial_sections(self, data_loader, mock_db_reader):
        """Test load_section_analyses with partial sections."""

        def mock_get_section(activity_id, section_type):
            sections = {
                "efficiency": {"efficiency": "効率良好"},
                "environment": None,
                "phase": {"rating": "****"},
                "split": None,
                "summary": {"activity_type": "ジョグ"},
            }
            return sections.get(section_type)

        mock_db_reader.get_section_analysis.side_effect = mock_get_section

        result = data_loader.load_section_analyses(activity_id=12345)

        assert result is not None
        assert "efficiency" in result
        assert "environment_analysis" not in result
        assert "phase_evaluation" in result
        assert "split_analysis" not in result
        assert "summary" in result

    @pytest.mark.unit
    def test_load_section_analyses_summary_string_to_list_conversion(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses converts summary strings to lists."""

        def mock_get_section(activity_id, section_type):
            if section_type == "summary":
                return {
                    "activity_type": "ジョグ",
                    "key_strengths": "ペース安定\n\n心拍数適正",
                    "improvement_areas": "ケイデンス向上",
                }
            return None

        mock_db_reader.get_section_analysis.side_effect = mock_get_section

        result = data_loader.load_section_analyses(activity_id=12345)

        assert isinstance(result["summary"]["key_strengths"], list)
        assert len(result["summary"]["key_strengths"]) == 2
        assert result["summary"]["key_strengths"][0] == "ペース安定"

        assert isinstance(result["summary"]["improvement_areas"], list)
        assert len(result["summary"]["improvement_areas"]) == 1
        assert result["summary"]["improvement_areas"][0] == "ケイデンス向上"

    @pytest.mark.unit
    def test_load_section_analyses_summary_already_list(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses when summary fields are already lists."""

        def mock_get_section(activity_id, section_type):
            if section_type == "summary":
                return {
                    "activity_type": "ジョグ",
                    "key_strengths": ["ペース安定", "心拍数適正"],
                    "improvement_areas": ["ケイデンス向上"],
                }
            return None

        mock_db_reader.get_section_analysis.side_effect = mock_get_section

        result = data_loader.load_section_analyses(activity_id=12345)

        # Should not fail, lists remain as lists
        assert isinstance(result["summary"]["key_strengths"], list)
        assert len(result["summary"]["key_strengths"]) == 2

    @pytest.mark.unit
    def test_load_section_analyses_empty_returns_none(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses with no sections returns None."""
        mock_db_reader.get_section_analysis.return_value = None

        result = data_loader.load_section_analyses(activity_id=12345)

        assert result is None

    @pytest.mark.unit
    def test_load_section_analyses_with_performance_data(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses with performance_data and physiological_calculator."""
        mock_physiological_calculator = MagicMock()
        mock_physiological_calculator.build_form_efficiency_table.return_value = {
            "form_efficiency_table": "テーブルデータ",
        }

        def mock_get_section(activity_id, section_type):
            if section_type == "efficiency":
                return {
                    "efficiency": "効率良好",
                    "evaluation": "心拍数効率評価",
                    "form_trend": "フォーム傾向",
                }
            return None

        mock_db_reader.get_section_analysis.side_effect = mock_get_section

        performance_data = {
            "form_efficiency_pace_corrected": {
                "gct_expected": 240,
                "gct_actual": 238,
            }
        }

        result = data_loader.load_section_analyses(
            activity_id=12345,
            performance_data=performance_data,
            physiological_calculator=mock_physiological_calculator,
        )

        assert result is not None
        assert "efficiency" in result
        assert result["efficiency"]["form_efficiency_table"] == "テーブルデータ"
        assert result["efficiency"]["efficiency"] == "効率良好"
        assert result["efficiency"]["evaluation"] == "心拍数効率評価"

        # Verify build_form_efficiency_table was called
        mock_physiological_calculator.build_form_efficiency_table.assert_called_once_with(
            performance_data["form_efficiency_pace_corrected"]
        )

    @pytest.mark.unit
    def test_load_section_analyses_calls_get_section_analysis(
        self, data_loader, mock_db_reader
    ):
        """Test load_section_analyses calls get_section_analysis for all sections."""
        mock_db_reader.get_section_analysis.return_value = None

        data_loader.load_section_analyses(activity_id=12345)

        # Should call 5 times (efficiency, environment, phase, split, summary)
        assert mock_db_reader.get_section_analysis.call_count == 5

        # Check all section types were called
        call_args = [
            call[0] for call in mock_db_reader.get_section_analysis.call_args_list
        ]
        assert (12345, "efficiency") in call_args
        assert (12345, "environment") in call_args
        assert (12345, "phase") in call_args
        assert (12345, "split") in call_args
        assert (12345, "summary") in call_args
