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
