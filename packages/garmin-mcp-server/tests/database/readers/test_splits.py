"""Tests for SplitsReader.

Covers get_splits_pace_hr, get_splits_form_metrics, get_splits_elevation,
get_splits_comprehensive (full + statistics_only), and get_splits_all (deprecated).
"""

import warnings
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.splits import SplitsReader

ACTIVITY_ID = 88880001
MISSING_ID = 99999999


def _insert_test_splits(db_path: Path, activity_id: int, n: int = 5) -> None:
    """Insert n test splits into the DB."""
    conn = duckdb.connect(str(db_path))
    # Need parent activity for some queries
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
        [activity_id, "2025-06-15"],
    )
    rows = []
    for i in range(1, n + 1):
        rows.append(
            (
                activity_id,
                i,  # split_index
                1.0,  # distance (km)
                300 + i * 5,  # duration_seconds
                None,  # start_time_gmt
                (i - 1) * 300,  # start_time_s
                i * 300,  # end_time_s
                "ACTIVE",  # intensity_type
                "run",  # role_phase
                f"{5 + i // 10}:{(i * 5) % 60:02d}",  # pace_str
                300 + i * 5,  # pace_seconds_per_km
                150 + i * 2,  # heart_rate
                f"Zone {min(i, 5)}",  # hr_zone
                175.0 + i * 0.5,  # cadence
                "良好",  # cadence_rating
                250 + i * 5,  # power
                "効率的",  # power_efficiency
                1.1 + i * 0.02,  # stride_length
                240 + i * 2,  # ground_contact_time
                7.0 + i * 0.2,  # vertical_oscillation
                8.0 + i * 0.1,  # vertical_ratio
                5 + i,  # elevation_gain
                2 + i * 0.5,  # elevation_loss
                "平坦",  # terrain_type
                "晴れ",  # environmental_conditions
                "微風",  # wind_impact
                "快適",  # temp_impact
                "良好",  # environmental_impact
                170 + i * 2,  # max_heart_rate
                180.0 + i,  # max_cadence
                280 + i * 5,  # max_power
                255 + i * 5,  # normalized_power
                3.3 + i * 0.05,  # average_speed
                3.4 + i * 0.05,  # grade_adjusted_speed
            )
        )
    conn.executemany(
        """INSERT INTO splits VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )""",
        rows,
    )
    conn.close()


@pytest.fixture
def splits_reader(reader_db_path: Path) -> SplitsReader:
    """SplitsReader with 5 test splits."""
    _insert_test_splits(reader_db_path, ACTIVITY_ID)
    return SplitsReader(db_path=str(reader_db_path))


@pytest.mark.unit
class TestGetSplitsPaceHr:
    """Tests for SplitsReader.get_splits_pace_hr()."""

    def test_full_mode_returns_splits_list(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_pace_hr(ACTIVITY_ID)
        assert "splits" in result
        assert len(result["splits"]) == 5

    def test_full_mode_keys(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_pace_hr(ACTIVITY_ID)
        split = result["splits"][0]
        assert "avg_pace_seconds_per_km" in split
        assert "avg_heart_rate" in split

    def test_statistics_only_mode(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_pace_hr(ACTIVITY_ID, statistics_only=True)
        assert "activity_id" in result
        assert "metrics" in result

    def test_missing_activity_full(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_pace_hr(MISSING_ID)
        assert result == {"splits": []}

    def test_missing_activity_statistics(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_pace_hr(MISSING_ID, statistics_only=True)
        assert result["activity_id"] == MISSING_ID


@pytest.mark.unit
class TestGetSplitsFormMetrics:
    """Tests for SplitsReader.get_splits_form_metrics()."""

    def test_full_mode_returns_splits(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_form_metrics(ACTIVITY_ID)
        assert "splits" in result
        assert len(result["splits"]) == 5

    def test_full_mode_has_gct_vo_vr(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_form_metrics(ACTIVITY_ID)
        split = result["splits"][0]
        assert "ground_contact_time_ms" in split
        assert "vertical_oscillation_cm" in split
        assert "vertical_ratio_percent" in split

    def test_statistics_only(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_form_metrics(
            ACTIVITY_ID, statistics_only=True
        )
        assert "metrics" in result


@pytest.mark.unit
class TestGetSplitsElevation:
    """Tests for SplitsReader.get_splits_elevation()."""

    def test_full_mode_has_terrain(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_elevation(ACTIVITY_ID)
        assert "splits" in result
        split = result["splits"][0]
        assert "elevation_gain_m" in split
        assert "elevation_loss_m" in split
        assert "terrain_type" in split

    def test_statistics_only(self, splits_reader: SplitsReader):
        result = splits_reader.get_splits_elevation(ACTIVITY_ID, statistics_only=True)
        assert "metrics" in result


@pytest.mark.unit
class TestGetSplitsAll:
    """Tests for SplitsReader.get_splits_all() (deprecated)."""

    def test_deprecation_warning(self, splits_reader: SplitsReader):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            splits_reader.get_splits_all(ACTIVITY_ID)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_max_output_size_exceeded(self, splits_reader: SplitsReader):
        """Very small max_output_size triggers ValueError."""
        with (
            pytest.raises(ValueError, match="exceeds max_output_size"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", DeprecationWarning)
            splits_reader.get_splits_all(ACTIVITY_ID, max_output_size=10)


BULK_ID_1 = 88880010
BULK_ID_2 = 88880011
BULK_ID_3 = 88880012


@pytest.mark.unit
class TestGetBulkMetricAverages:
    """Tests for SplitsReader.get_bulk_metric_averages()."""

    @pytest.fixture
    def bulk_reader(self, reader_db_path: Path) -> SplitsReader:
        """SplitsReader with 3 activities for bulk query testing."""
        _insert_test_splits(reader_db_path, BULK_ID_1, n=3)
        _insert_test_splits(reader_db_path, BULK_ID_2, n=3)
        _insert_test_splits(reader_db_path, BULK_ID_3, n=3)
        return SplitsReader(db_path=str(reader_db_path))

    def test_returns_dict_of_averages(self, bulk_reader: SplitsReader) -> None:
        """Basic return type and content."""
        result = bulk_reader.get_bulk_metric_averages(
            [BULK_ID_1, BULK_ID_2], "pace_seconds_per_km"
        )
        assert isinstance(result, dict)
        assert BULK_ID_1 in result
        assert BULK_ID_2 in result
        assert isinstance(result[BULK_ID_1], float)

    def test_all_allowed_columns(self, bulk_reader: SplitsReader) -> None:
        """All allowed columns should work without error."""
        for column in [
            "pace_seconds_per_km",
            "heart_rate",
            "cadence",
            "power",
            "ground_contact_time",
            "vertical_oscillation",
            "vertical_ratio",
            "elevation_gain",
        ]:
            result = bulk_reader.get_bulk_metric_averages([BULK_ID_1], column)
            assert isinstance(result, dict)

    def test_invalid_column_raises(self, bulk_reader: SplitsReader) -> None:
        """Invalid column name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid column"):
            bulk_reader.get_bulk_metric_averages([BULK_ID_1], "DROP TABLE splits")

    def test_empty_activity_ids(self, bulk_reader: SplitsReader) -> None:
        """Empty activity_ids should return empty dict."""
        result = bulk_reader.get_bulk_metric_averages([], "pace_seconds_per_km")
        assert result == {}

    def test_missing_activity_excluded(self, bulk_reader: SplitsReader) -> None:
        """Activity with no splits should not appear in result."""
        result = bulk_reader.get_bulk_metric_averages(
            [BULK_ID_1, MISSING_ID], "pace_seconds_per_km"
        )
        assert BULK_ID_1 in result
        assert MISSING_ID not in result

    def test_averages_are_correct(self, bulk_reader: SplitsReader) -> None:
        """Verify the average calculation is correct."""
        result = bulk_reader.get_bulk_metric_averages(
            [BULK_ID_1], "pace_seconds_per_km"
        )
        # _insert_test_splits inserts pace_seconds_per_km = 300 + i*5 for i=1..3
        # Values: 305, 310, 315 → avg = 310.0
        assert result[BULK_ID_1] == pytest.approx(310.0)
