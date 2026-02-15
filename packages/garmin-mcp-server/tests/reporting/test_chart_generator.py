"""Unit tests for ChartGenerator class."""

from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.chart_generator import ChartGenerator


@pytest.fixture
def mock_db_reader():
    """Create a mock GarminDBReader."""
    return MagicMock(spec=GarminDBReader)


@pytest.fixture
def chart_generator(mock_db_reader):
    """Create a ChartGenerator instance with mock db_reader."""
    return ChartGenerator(db_reader=mock_db_reader)


# ==================== generate_mermaid_data tests ====================


@pytest.mark.unit
def test_generate_mermaid_data_returns_none_for_none_splits(chart_generator):
    """Test that generate_mermaid_data returns None when splits is None."""
    result = chart_generator.generate_mermaid_data(splits=None)
    assert result is None


@pytest.mark.unit
def test_generate_mermaid_data_returns_none_for_empty_splits(chart_generator):
    """Test that generate_mermaid_data returns None when splits is empty."""
    result = chart_generator.generate_mermaid_data(splits=[])
    assert result is None


@pytest.mark.unit
def test_generate_mermaid_data_extracts_data_correctly(chart_generator):
    """Test that generate_mermaid_data extracts data from splits correctly."""
    splits = [
        {"index": 1, "pace_seconds_per_km": 300, "heart_rate": 150, "power": 200},
        {"index": 2, "pace_seconds_per_km": 310, "heart_rate": 155, "power": 210},
        {"index": 3, "pace_seconds_per_km": 305, "heart_rate": 152, "power": 205},
    ]

    result = chart_generator.generate_mermaid_data(splits=splits)

    assert result is not None
    assert result["x_axis_labels"] == ["1", "2", "3"]
    assert result["pace_data"] == [300, 310, 305]
    assert result["heart_rate_data"] == [150, 155, 152]
    assert result["power_data"] == [200, 210, 205]


@pytest.mark.unit
def test_generate_mermaid_data_handles_none_power_values(chart_generator):
    """Test that generate_mermaid_data handles None power values as 0."""
    splits = [
        {"index": 1, "pace_seconds_per_km": 300, "heart_rate": 150, "power": None},
        {"index": 2, "pace_seconds_per_km": 310, "heart_rate": 155, "power": 210},
        {"index": 3, "pace_seconds_per_km": 305, "heart_rate": 152},  # Missing power
    ]

    result = chart_generator.generate_mermaid_data(splits=splits)

    assert result is not None
    assert result["power_data"] == [0, 210, 0]


@pytest.mark.unit
def test_generate_mermaid_data_calculates_pace_min_max_with_padding(chart_generator):
    """Test that pace_min and pace_max are calculated with 10% padding."""
    splits = [
        {"index": 1, "pace_seconds_per_km": 300, "heart_rate": 150, "power": 200},
        {"index": 2, "pace_seconds_per_km": 320, "heart_rate": 155, "power": 210},
    ]

    result = chart_generator.generate_mermaid_data(splits=splits)

    # pace_min = 300 * 0.9 = 270.0
    # pace_max = 320 * 1.1 = 352.0
    assert result is not None
    assert result["pace_min"] == 270.0
    assert result["pace_max"] == 352.0


@pytest.mark.unit
def test_generate_mermaid_data_calculates_hr_min_max_with_padding(chart_generator):
    """Test that hr_min and hr_max are calculated with 10% padding."""
    splits = [
        {"index": 1, "pace_seconds_per_km": 300, "heart_rate": 150, "power": 200},
        {"index": 2, "pace_seconds_per_km": 310, "heart_rate": 160, "power": 210},
    ]

    result = chart_generator.generate_mermaid_data(splits=splits)

    # hr_min = 150 * 0.9 = 135.0
    # hr_max = 160 * 1.1 = 176.0
    assert result is not None
    assert result["hr_min"] == 135.0
    assert result["hr_max"] == 176.0


@pytest.mark.unit
def test_generate_mermaid_data_rounds_to_one_decimal(chart_generator):
    """Test that min/max values are rounded to 1 decimal place."""
    splits = [
        {"index": 1, "pace_seconds_per_km": 333, "heart_rate": 147, "power": 200},
        {"index": 2, "pace_seconds_per_km": 337, "heart_rate": 153, "power": 210},
    ]

    result = chart_generator.generate_mermaid_data(splits=splits)

    # pace_min = 333 * 0.9 = 299.7
    # pace_max = 337 * 1.1 = 370.7
    # hr_min = 147 * 0.9 = 132.3
    # hr_max = 153 * 1.1 = 168.3
    assert result is not None
    assert result["pace_min"] == 299.7
    assert result["pace_max"] == 370.7
    assert result["hr_min"] == 132.3
    assert result["hr_max"] == 168.3


# ==================== generate_mermaid_analysis tests ====================


@pytest.mark.unit
def test_generate_mermaid_analysis_returns_none_for_non_interval(chart_generator):
    """Test that generate_mermaid_analysis returns None for non-interval workouts."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 300,
            "heart_rate": 150,
            "power": 200,
            "intensity_type": "INTERVAL",
        }
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="easy_run"
    )
    assert result is None


@pytest.mark.unit
def test_generate_mermaid_analysis_returns_none_for_no_work_splits(chart_generator):
    """Test that generate_mermaid_analysis returns None when no work splits."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 400,
            "heart_rate": 120,
            "power": 100,
            "intensity_type": "WARMUP",
        }
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )
    assert result is None


@pytest.mark.unit
def test_generate_mermaid_analysis_work_only_splits(chart_generator):
    """Test generate_mermaid_analysis with work-only splits."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 245,
            "heart_rate": 172,
            "power": 252,
            "intensity_type": "active",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "Work区間2本" in result
    assert "平均ペース4:02/km" in result
    assert "平均心拍171bpm" in result
    assert "平均パワー251W" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_work_and_recovery_splits(chart_generator):
    """Test generate_mermaid_analysis with work and recovery splits."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 360,
            "heart_rate": 130,
            "power": 100,
            "intensity_type": "RECOVERY",
        },
        {
            "index": 3,
            "pace_seconds_per_km": 245,
            "heart_rate": 172,
            "power": 252,
            "intensity_type": "active",
        },
        {
            "index": 4,
            "pace_seconds_per_km": 365,
            "heart_rate": 132,
            "power": 105,
            "intensity_type": "rest",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "Work区間2本" in result
    assert "Recovery区間2本" in result
    assert "平均ペース6:02/km" in result  # Recovery pace
    assert "十分な回復" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_consistency_evaluation_very_stable(
    chart_generator,
):
    """Test consistency evaluation for very stable pace (CV < 2.0%)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 242,
            "heart_rate": 171,
            "power": 251,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 3,
            "pace_seconds_per_km": 241,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "非常に安定" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_consistency_evaluation_stable(chart_generator):
    """Test consistency evaluation for stable pace (2.0% <= CV < 4.0%)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 250,
            "heart_rate": 171,
            "power": 251,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 3,
            "pace_seconds_per_km": 245,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "安定" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_consistency_evaluation_unstable(chart_generator):
    """Test consistency evaluation for unstable pace (CV >= 4.0%)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 270,
            "heart_rate": 171,
            "power": 251,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 3,
            "pace_seconds_per_km": 250,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "やや不安定" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_transition_quality_excellent(chart_generator):
    """Test transition quality for excellent HR recovery (drop > 30 bpm)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 360,
            "heart_rate": 130,
            "power": 100,
            "intensity_type": "RECOVERY",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "優秀な心拍リカバリー" in result
    assert "40bpm" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_transition_quality_good(chart_generator):
    """Test transition quality for good HR recovery (20 < drop <= 30 bpm)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 360,
            "heart_rate": 145,
            "power": 100,
            "intensity_type": "RECOVERY",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "良好な心拍リカバリー" in result
    assert "25bpm" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_transition_quality_insufficient(chart_generator):
    """Test transition quality for insufficient HR recovery (drop <= 20 bpm)."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "power": 250,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 360,
            "heart_rate": 155,
            "power": 100,
            "intensity_type": "RECOVERY",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "心拍リカバリーやや不十分" in result
    assert "15bpm" in result


@pytest.mark.unit
def test_generate_mermaid_analysis_no_power_data(chart_generator):
    """Test generate_mermaid_analysis when power data is not available."""
    splits = [
        {
            "index": 1,
            "pace_seconds_per_km": 240,
            "heart_rate": 170,
            "intensity_type": "INTERVAL",
        },
        {
            "index": 2,
            "pace_seconds_per_km": 245,
            "heart_rate": 172,
            "intensity_type": "INTERVAL",
        },
    ]

    result = chart_generator.generate_mermaid_analysis(
        splits=splits, training_type_category="interval_sprint"
    )

    assert result is not None
    assert "Work区間2本" in result
    assert "平均パワー" not in result


# ==================== generate_hr_zone_pie_data tests ====================


@pytest.mark.unit
def test_generate_hr_zone_pie_data_returns_formatted_data(
    chart_generator, mock_db_reader
):
    """Test that generate_hr_zone_pie_data returns formatted Mermaid pie data."""
    mock_db_reader.execute_read_query.return_value = [
        (1, 5.0),
        (2, 40.0),
        (3, 30.0),
        (4, 20.0),
        (5, 5.0),
    ]

    result = chart_generator.generate_hr_zone_pie_data(activity_id=12345)

    assert result is not None
    assert '"Zone 1 (回復)" : 5.00' in result
    assert '"Zone 2 (有酸素)" : 40.00' in result
    assert '"Zone 3 (テンポ)" : 30.00' in result
    assert '"Zone 4 (閾値)" : 20.00' in result
    assert '"Zone 5 (最大)" : 5.00' in result
    assert result.count("\n") == 4  # 5 zones = 4 newlines


@pytest.mark.unit
def test_generate_hr_zone_pie_data_calls_db_reader_with_correct_params(
    chart_generator, mock_db_reader
):
    """Test that generate_hr_zone_pie_data calls db_reader with correct SQL and params."""
    mock_db_reader.execute_read_query.return_value = [(1, 100.0)]

    chart_generator.generate_hr_zone_pie_data(activity_id=12345)

    mock_db_reader.execute_read_query.assert_called_once()
    call_args = mock_db_reader.execute_read_query.call_args
    sql_query = call_args[0][0]
    params = call_args[0][1]

    assert "SELECT" in sql_query
    assert "zone_number" in sql_query
    assert "zone_percentage" in sql_query
    assert "FROM heart_rate_zones" in sql_query
    assert "WHERE activity_id = ?" in sql_query
    assert "zone_percentage > 0" in sql_query
    assert "ORDER BY zone_number" in sql_query
    assert params == (12345,)


@pytest.mark.unit
def test_generate_hr_zone_pie_data_returns_none_for_empty_result(
    chart_generator, mock_db_reader
):
    """Test that generate_hr_zone_pie_data returns None when no data available."""
    mock_db_reader.execute_read_query.return_value = []

    result = chart_generator.generate_hr_zone_pie_data(activity_id=12345)

    assert result is None


@pytest.mark.unit
def test_generate_hr_zone_pie_data_returns_none_for_exception(
    chart_generator, mock_db_reader
):
    """Test that generate_hr_zone_pie_data returns None when exception occurs."""
    mock_db_reader.execute_read_query.side_effect = Exception("Database error")

    result = chart_generator.generate_hr_zone_pie_data(activity_id=12345)

    assert result is None


@pytest.mark.unit
def test_generate_hr_zone_pie_data_handles_partial_zones(
    chart_generator, mock_db_reader
):
    """Test that generate_hr_zone_pie_data handles partial zone data correctly."""
    # Only zones 2, 3, 4 have data
    mock_db_reader.execute_read_query.return_value = [
        (2, 25.5),
        (3, 50.25),
        (4, 24.25),
    ]

    result = chart_generator.generate_hr_zone_pie_data(activity_id=12345)

    assert result is not None
    assert '"Zone 2 (有酸素)" : 25.50' in result
    assert '"Zone 3 (テンポ)" : 50.25' in result
    assert '"Zone 4 (閾値)" : 24.25' in result
    assert "Zone 1" not in result
    assert "Zone 5" not in result
